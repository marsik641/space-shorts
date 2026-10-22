"""Общие примитивы очереди: один ресурс на ПК, атомарные файлы, запуск дерева процессов."""
import contextlib
import ctypes
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time
import uuid

WIN = os.name == "nt"
NO_WINDOW = 0x08000000 if WIN else 0


class Busy(RuntimeError):
    pass


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex[:8] + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def queue_home(source):
    """Все git worktree используют out/q основной рабочей копии."""
    if os.environ.get("SPACEKIT_QUEUE_HOME"):
        return Path(os.environ["SPACEKIT_QUEUE_HOME"]).absolute()
    source = Path(source).absolute()
    r = subprocess.run(["git", "-C", str(source), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                       capture_output=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    return (Path(r.stdout.strip()).parent if r.returncode == 0 else source) / "out" / "q"


def alive(pid):
    if not pid:
        return False
    if WIN:
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        handle = kernel.OpenProcess(0x1000, False, int(pid))
        if handle:
            code = ctypes.c_ulong()
            ok = kernel.GetExitCodeProcess(handle, ctypes.byref(code))
            kernel.CloseHandle(handle)
            return bool(ok) and code.value == 259
        return kernel.GetLastError() == 5
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def blender_processes():
    if WIN:
        from ctypes import wintypes as w

        class Process(ctypes.Structure):
            _fields_ = [("size", w.DWORD), ("usage", w.DWORD), ("pid", w.DWORD), ("heap", ctypes.c_size_t),
                        ("module", w.DWORD), ("threads", w.DWORD), ("parent", w.DWORD), ("priority", w.LONG),
                        ("flags", w.DWORD), ("exe", w.WCHAR * 260)]

        kernel = ctypes.windll.kernel32
        kernel.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
        kernel.Process32FirstW.argtypes = kernel.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.POINTER(Process)]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.CreateToolhelp32Snapshot(2, 0)
        if handle == ctypes.c_void_p(-1).value:
            raise Busy("Не удалось проверить процессы Windows")
        try:
            entry = Process()
            entry.size = ctypes.sizeof(entry)
            more = kernel.Process32FirstW(handle, ctypes.byref(entry))
            while more:
                if entry.exe.lower() == "blender.exe":
                    return True
                more = kernel.Process32NextW(handle, ctypes.byref(entry))
            if kernel.GetLastError() != 18:  # ERROR_NO_MORE_FILES
                raise Busy("Не удалось перечислить все процессы Windows")
            return False
        finally:
            kernel.CloseHandle(handle)
    r = subprocess.run(["pgrep", "-x", "blender"], capture_output=True, timeout=15)
    return r.returncode == 0


@contextlib.contextmanager
def file_lock(path):
    """Блокировка ОС: не протухает по таймеру, снимается при смерти процесса."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "a+b")
    locked = False
    try:
        if path.stat().st_size == 0:
            fh.write(b"0")
            fh.flush()
        fh.seek(0)
        try:
            if WIN:
                import msvcrt
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError as e:
            raise Busy(str(path)) from e
        yield
    finally:
        if locked:
            fh.seek(0)
            if WIN:
                import msvcrt
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


def busy_reason(home):
    lock = Path(home).parent / "RENDER.lock"
    if lock.exists():
        return "RENDER.lock: " + lock.read_text(encoding="utf-8", errors="replace").strip()
    return "blender.exe" if blender_processes() else None


@contextlib.contextmanager
def resource(home, label):
    """Общий шлюз для Blender и тяжёлого звука; старые lock не удаляем автоматически."""
    home = Path(home)
    lock = home.parent / "RENDER.lock"
    with file_lock(home / "gpu.lck"):
        old = read_json(lock)
        # Только собственный умерший владелец; живой Blender всегда блокирует восстановление.
        if old and old.get("queue") and not alive(old.get("pid")) and not alive(old.get("child_pid")) and not blender_processes():
            lock.unlink(missing_ok=True)
        reason = busy_reason(home)
        if reason:
            raise Busy(reason)
        token = uuid.uuid4().hex
        data = dict(queue=True, pid=os.getpid(), token=token, label=label, started=time.time())
        try:
            with open(lock, "x", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False)
        except FileExistsError as e:
            raise Busy("RENDER.lock") from e
        keep_awake(True)
        try:
            yield {"SPACEKIT_QUEUE_HOME": str(home), "SPACEKIT_RENDER_TOKEN": token}
        finally:
            keep_awake(False)
            if (read_json(lock) or {}).get("token") == token:
                lock.unlink(missing_ok=True)


def inherited_resource():
    home, token = os.environ.get("SPACEKIT_QUEUE_HOME"), os.environ.get("SPACEKIT_RENDER_TOKEN")
    if not home or not token:
        return False
    owner = read_json(Path(home).parent / "RENDER.lock", {})
    return owner.get("token") == token and alive(owner.get("pid"))


def keep_awake(on):
    if WIN:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | (1 if on else 0))


def find_blender():
    cfg = read_json(Path(__file__).resolve().parents[1] / "out" / "remote_config.json", {})
    candidates = [os.environ.get("BLENDER"), cfg.get("blender"), "D:/Blender/blender.exe", shutil.which("blender")]
    for base in (Path("C:/Program Files/Blender Foundation"), Path("D:/Blender Foundation")):
        if WIN and base.is_dir():
            candidates += sorted(base.glob("Blender */blender.exe"), reverse=True)
    for p in candidates:
        if p and Path(p).is_file():
            return str(Path(p).absolute())
    raise RuntimeError("Blender не найден: задай BLENDER")


class WindowsTree:
    """ОС владеет деревом: даже авария worker закрывает job и завершает всех потомков."""
    def __init__(self):
        from ctypes import wintypes as w

        class Limits(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong), ("flags", w.DWORD),
                        ("min_ws", ctypes.c_size_t), ("max_ws", ctypes.c_size_t), ("active", w.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD)]

        class Extended(ctypes.Structure):
            _fields_ = [("basic", Limits), ("io", ctypes.c_ulonglong * 6), ("process_memory", ctypes.c_size_t),
                        ("job_memory", ctypes.c_size_t), ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]

        self.kernel = ctypes.windll.kernel32
        k = self.kernel
        k.CreateJobObjectW.restype = ctypes.c_void_p
        k.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        k.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        k.TerminateJobObject.argtypes = [ctypes.c_void_p, w.UINT]
        k.QueryInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p]
        k.CloseHandle.argtypes = [ctypes.c_void_p]
        self.handle = k.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError()
        info = Extended()
        info.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not k.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            error = ctypes.WinError()
            self.close()
            raise error

    def attach_and_resume(self, proc):
        from ctypes import wintypes as w

        class Thread(ctypes.Structure):
            _fields_ = [("size", w.DWORD), ("usage", w.DWORD), ("tid", w.DWORD), ("pid", w.DWORD),
                        ("base", w.LONG), ("delta", w.LONG), ("flags", w.DWORD)]

        k = self.kernel
        if not k.AssignProcessToJobObject(self.handle, int(proc._handle)):
            raise ctypes.WinError()
        k.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
        k.Thread32First.argtypes = k.Thread32Next.argtypes = [ctypes.c_void_p, ctypes.POINTER(Thread)]
        k.OpenThread.restype = ctypes.c_void_p
        k.ResumeThread.argtypes = [ctypes.c_void_p]
        k.ResumeThread.restype = w.DWORD
        snapshot = k.CreateToolhelp32Snapshot(4, 0)
        if snapshot == ctypes.c_void_p(-1).value:
            raise ctypes.WinError()
        try:
            entry = Thread()
            entry.size = ctypes.sizeof(entry)
            more = k.Thread32First(snapshot, ctypes.byref(entry))
            while more:
                if entry.pid == proc.pid:
                    handle = k.OpenThread(2, False, entry.tid)  # THREAD_SUSPEND_RESUME
                    if not handle:
                        raise ctypes.WinError()
                    try:
                        if k.ResumeThread(handle) == 0xFFFFFFFF:
                            raise ctypes.WinError()
                        return
                    finally:
                        k.CloseHandle(handle)
                more = k.Thread32Next(snapshot, ctypes.byref(entry))
            raise RuntimeError("Не найден начальный поток дочернего процесса")
        finally:
            k.CloseHandle(snapshot)

    def terminate(self):
        if not self.kernel.TerminateJobObject(self.handle, 1):
            raise ctypes.WinError()
        # Не возвращаем ресурс, пока ОС не закончила закрывать потомков и их файлы.
        class Accounting(ctypes.Structure):
            _fields_ = [("times", ctypes.c_longlong * 4), ("faults", ctypes.c_ulong), ("total", ctypes.c_ulong),
                        ("active", ctypes.c_ulong), ("terminated", ctypes.c_ulong)]
        state = Accounting()
        until = time.monotonic() + 10
        while self.kernel.QueryInformationJobObject(self.handle, 1, ctypes.byref(state), ctypes.sizeof(state), None):
            if not state.active:
                return
            if time.monotonic() >= until:
                raise RuntimeError("ОС ещё не завершила процессы задания")
            time.sleep(0.01)

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def kill_tree(proc, tree=None):
    if proc.poll() is not None:
        return
    if WIN:
        if tree is None:
            raise RuntimeError("У процесса нет Windows Job Object")
        tree.terminate()
    else:
        os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def execute(snapshot, step, python, home, cancel=lambda: False):
    """Только argv, без shell. Проверяем ошибки исключительно текущего запуска."""
    snapshot = Path(snapshot)
    log = snapshot / step["log"]
    log.parent.mkdir(parents=True, exist_ok=True)
    with resource(home, snapshot.name + " " + step["name"]) as lease:
        argv = list(step["argv"])
        argv[0] = find_blender() if argv[0] == "BLENDER" else python
        if any(a.startswith("queue_range=") for a in argv):
            for rel in step.get("outputs", []):
                path = snapshot / rel
                if path.is_file():
                    with open(path, "rb") as fh:
                        head = fh.read(8)
                        fh.seek(max(0, path.stat().st_size - 12))
                        tail = fh.read()
                    if head != b"\x89PNG\r\n\x1a\n" or tail != b"\x00\x00\x00\x00IEND\xaeB`\x82":
                        if not path.resolve().is_relative_to(snapshot.resolve()):
                            raise ValueError("Кадр вне снимка")
                        path.unlink()
        env = dict(os.environ, **lease, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
        with open(log, "ab") as fh:
            start = fh.tell()
            fh.write(("\n=== " + time.strftime("%F %T") + " " + step["name"] + "\n").encode())
            fh.flush()
            tree = WindowsTree() if WIN else None
            proc = None
            try:
                proc = subprocess.Popen(argv, cwd=snapshot, env=env, stdout=fh, stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL, creationflags=NO_WINDOW | (4 if WIN else 0),
                                        start_new_session=not WIN)
                lock_path = Path(home).parent / "RENDER.lock"
                owner = read_json(lock_path, {})
                if owner.get("token") == lease["SPACEKIT_RENDER_TOKEN"]:
                    write_json(lock_path, dict(owner, child_pid=proc.pid))
                if tree:
                    tree.attach_and_resume(proc)
                while proc.poll() is None:
                    if cancel():
                        kill_tree(proc, tree)
                        raise RuntimeError("Задание отменено")
                    time.sleep(0.25)
            finally:
                if tree:
                    try:
                        tree.terminate()
                    finally:
                        tree.close()
                        if proc:
                            if proc.poll() is None:
                                proc.kill()  # также закрывает suspended-процесс при ошибке AssignProcessToJobObject
                            proc.wait()
                elif proc and proc.poll() is None:
                    kill_tree(proc)
        with open(log, "rb") as fh:
            fh.seek(start)
            text = fh.read().decode("utf-8", "replace")
        errors = ("Traceback (most recent call last)", "CUDA error", "OPTIX_ERROR", "out of memory", "OVERRUN")
        if proc.returncode or any(e in text for e in errors):
            raise RuntimeError(f"{step['name']}: код {proc.returncode}; {log}")
        missing = [p for p in step.get("outputs", []) if not (snapshot / p).is_file() or not (snapshot / p).stat().st_size]
        if missing:
            raise RuntimeError("Нет результатов: " + ", ".join(missing[:5]))


def extract_tar(tf, dest):
    """Принимаем только обычные файлы внутри каталога результата."""
    dest = Path(dest).resolve()
    for member in tf.getmembers():
        path = (dest / member.name).resolve()
        if not member.isfile() or not path.is_relative_to(dest):
            raise ValueError(f"Недопустимый путь архива: {member.name}")
        path.parent.mkdir(parents=True, exist_ok=True)
        with tf.extractfile(member) as src, open(path, "wb") as dst:
            shutil.copyfileobj(src, dst)
