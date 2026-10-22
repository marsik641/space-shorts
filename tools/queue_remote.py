"""Транспорт очереди на рендер-ПК. Никаких общих remote_job.json и перезаписи активного кода."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time

from queue_runtime import (Busy, NO_WINDOW, alive, busy_reason, execute, extract_tar, file_lock,
                           read_json, write_json)

ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "out/q"


def location(jid, index=None):
    if len(jid) != 10 or any(c not in "0123456789abcdef" for c in jid):
        raise ValueError("Некорректный id")
    snap = HOME / jid
    if index is not None and not 0 <= index < len(read_json(snap / "job.json")["plan"]):
        raise ValueError("Некорректный шаг")
    return snap, snap / f"step_{index}.json"


def status(jid, index):
    snap, path = location(jid, index)
    st = read_json(path, {"state": "missing"})
    if st["state"] in ("starting", "running", "waiting"):
        if st.get("pid") and not alive(st["pid"]):
            st.update(state="failed", error="Удалённый исполнитель завершился; retry продолжит кадры")
            write_json(path, st)
        elif not st.get("pid") and time.time() - st.get("started", 0) > 60:
            st.update(state="failed", error="Удалённый исполнитель не запустился за 60 с")
            write_json(path, st)
    return st


def start(jid, index):
    snap, path = location(jid, index)
    with file_lock(snap / f"start_{index}.lck"):
        st = status(jid, index)
        if st["state"] != "missing":
            return st
        st = dict(state="starting", started=time.time())
        write_json(path, st)
        args = [sys.executable, str(Path(__file__).resolve()), "run", jid, str(index)]
        if os.name == "nt":
            # Планировщик переживает закрытие ssh; /ST лишь обязательное поле, запуск — /Run.
            pyw = Path(sys.executable).with_name("pythonw.exe")
            if pyw.is_file():
                args[0] = str(pyw)
            task = f"SpaceShorts-{jid}-{index}"
            command = subprocess.list2cmdline(args)
            if len(command) > 255:
                raise ValueError("Слишком длинный путь задания Планировщика")
            subprocess.run(["schtasks", "/Create", "/F", "/TN", task, "/SC", "ONCE", "/ST", "23:59", "/TR", command],
                           check=True, capture_output=True, creationflags=NO_WINDOW)
            subprocess.run(["schtasks", "/Run", "/TN", task], check=True, capture_output=True, creationflags=NO_WINDOW)
        else:
            with open(snap / "agent.log", "ab") as log:
                subprocess.Popen(args, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
        return st


def run(jid, index):
    snap, path = location(jid, index)
    cancel = snap / f"cancel_{index}"
    with file_lock(snap / f"run_{index}.lck"):
        if status(jid, index)["state"] in ("done", "cancelled"):
            return
        st = dict(state="waiting", pid=os.getpid(), started=time.time())
        write_json(path, st)
        step = read_json(snap / "job.json")["plan"][index]
        try:
            if step["lane"] != "render" or step["argv"][0] != "BLENDER":
                raise ValueError("На удалённый ПК передаются только шаги рендера Blender")
            while True:
                if cancel.exists():
                    raise RuntimeError("Задание отменено")
                try:
                    st.update(state="running")
                    write_json(path, st)
                    execute(snap, step, sys.executable, HOME, cancel.exists)
                    st.update(state="done", error=None)
                    break
                except Busy as e:
                    st.update(state="waiting", error=str(e))
                    write_json(path, st)
                    time.sleep(2)
        except Exception as e:
            st.update(state="cancelled" if cancel.exists() else "failed", error=str(e))
        finally:
            st["finished"] = time.time()
            write_json(path, st)
            if os.name == "nt":
                subprocess.run(["schtasks", "/Delete", "/F", "/TN", f"SpaceShorts-{jid}-{index}"],
                               capture_output=True, creationflags=NO_WINDOW)


def main():
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmd", choices=("probe", "unpack", "start", "run", "status", "cancel", "retry", "reset", "pack"))
    ap.add_argument("jid", nargs="?")
    ap.add_argument("index", nargs="?", type=int)
    a = ap.parse_args()
    HOME.mkdir(parents=True, exist_ok=True)
    if a.cmd == "probe":
        reason = busy_reason(HOME)
        result = dict(busy=bool(reason), reason=reason)
    elif a.cmd == "unpack":
        snap, _ = location(a.jid)
        # Повторная распаковка после потерянного ответа не меняет уже работающий снимок.
        with file_lock(snap / "unpack.lck"):
            if not (snap / "unpacked").exists():
                with tarfile.open(snap / "input.tar") as tf:
                    extract_tar(tf, snap)
                (snap / "unpacked").touch()
            (snap / "input.tar").unlink(missing_ok=True)
        result = dict(ok=True)
    elif a.cmd == "start":
        result = start(a.jid, a.index)
    elif a.cmd == "run":
        run(a.jid, a.index)
        return
    elif a.cmd == "status":
        result = status(a.jid, a.index)
    elif a.cmd == "cancel":
        snap, _ = location(a.jid, a.index)
        (snap / f"cancel_{a.index}").touch()
        result = status(a.jid, a.index)
    elif a.cmd in ("retry", "reset"):
        snap, path = location(a.jid, a.index)
        with file_lock(snap / f"start_{a.index}.lck"), file_lock(snap / f"run_{a.index}.lck"):
            allowed = ("failed", "cancelled", "missing", "done") if a.cmd == "reset" else ("failed", "cancelled", "missing")
            if status(a.jid, a.index)["state"] not in allowed:
                raise ValueError("Удалённый шаг ещё работает или уже выполнен")
            path.unlink(missing_ok=True)
            (snap / f"cancel_{a.index}").unlink(missing_ok=True)
        result = dict(ok=True)
    else:
        snap, _ = location(a.jid, a.index)
        if status(a.jid, a.index)["state"] != "done":
            raise ValueError("Шаг ещё не завершён")
        step = read_json(snap / "job.json")["plan"][a.index]
        path = snap / f"result_{a.index}.tar"
        with tarfile.open(path, "w") as tf:
            for rel in [*step.get("outputs", []), step["log"]]:
                tf.add(snap / rel, arcname=rel)
        result = dict(path=path.as_posix())
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
