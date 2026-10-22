"""Агент рендера на удалённом ПК (запускается там через ssh; только стандартная библиотека Python 3.8+).

Корень — каталог над tools/ (туда tools/remote_render.py заливает spacekit/, episodes/<ep>/, assets/).

    python tools/remote/agent.py check  [--blender PATH]          окружение: Python, Blender, GPU, шрифты, диск
    python tools/remote/agent.py start  --ep EP --shots v1,v2,…   рендер в фоне (Windows: Планировщик заданий —
                                        [--blender PATH] [--device OPTIX|CUDA|…]   не умирает при обрыве ssh, без окон)
    python tools/remote/agent.py run                               сам рендер (его зовёт start; по out/remote_job.json)
    python tools/remote/agent.py status --ep EP                    JSON: кадры по шотам, идёт ли рендер, хвост лога
    python tools/remote/agent.py stop                              остановить рендер
    python tools/remote/agent.py pack   --ep EP --shot S --from N  tar с готовыми кадрами ≥ N -> печатает путь и число
    python tools/remote/agent.py rm     PATH                       удалить отданный tar

Рендер — как tools/render_episode.sh: шоты по очереди, `blender -b … -P episodes/<ep>/shots_9x16.py -- <шот> final`,
докачка (готовые кадры пропускаются), лог out/logs/<ep>/render_<шот>.log, при ошибке — один повтор шота.
Пока идёт рендер: out/RENDER.lock и out/remote_status.json; ПК не уходит в сон (SetThreadExecutionState, только на
время рендера, настройки питания не меняются).
"""
import argparse
import glob
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT = os.path.join(ROOT, "out")
CFG = os.path.join(OUT, "remote_config.json")
JOB = os.path.join(OUT, "remote_job.json")
STATUS = os.path.join(OUT, "remote_status.json")
LOCK = os.path.join(OUT, "RENDER.lock")
TASK = "OrbitfallRender"
WIN = os.name == "nt"
ERR_RX = re.compile(r"Traceback|Error:|CUDA error|OPTIX_ERROR|out of memory")


def jdump(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def jload(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


# ---------------------------------------------------------------- Blender
def find_blender(explicit=None):
    cands = [explicit, os.environ.get("BLENDER"), (jload(CFG, {}) or {}).get("blender")]
    if WIN:
        bases = [os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", "")]
        for drv in "CDEFGH":                                       # Blender часто ставят не на C:
            bases += [f"{drv}:/Program Files", f"{drv}:/Program Files (x86)", f"{drv}:/"]
        for base in bases:
            if base and os.path.isdir(base):
                cands += sorted(glob.glob(os.path.join(base, "Blender Foundation", "Blender *", "blender.exe")),
                                reverse=True)
                cands += sorted(glob.glob(os.path.join(base, "Blender*", "blender.exe")), reverse=True)
                for steam in ("Steam", "SteamLibrary"):
                    cands.append(os.path.join(base, steam, "steamapps", "common", "Blender", "blender.exe"))
    else:
        cands += [shutil.which("blender")] + sorted(glob.glob(os.path.expanduser("~/blender*/blender")), reverse=True)
        cands.append("/Applications/Blender.app/Contents/MacOS/Blender")
    for c in cands:
        if c and os.path.isfile(c):
            return os.path.abspath(c)
    return None


def blender_version(b):
    try:
        out = subprocess.run([b, "--version"], capture_output=True, text=True, errors="replace", timeout=120).stdout
    except (OSError, subprocess.SubprocessError) as e:
        return f"ошибка запуска: {e}"
    return out.splitlines()[0].strip() if out else "?"


DEVICES_PY = r"""
import bpy
p = bpy.context.preferences.addons["cycles"].preferences
for t in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
    try:
        p.compute_device_type = t
    except TypeError:
        continue
    p.get_devices()
    ds = [d.name for d in p.devices if d.type == t]
    if ds:
        print("DEVICE", t, "|", "; ".join(ds))
"""


def cmd_check(a):
    b = find_blender(a.blender)
    info = {"root": ROOT, "os": platform.platform(), "python": sys.version.split()[0], "blender": b}
    if b:
        info["blender_version"] = blender_version(b)
        try:
            r = subprocess.run([b, "-b", "--factory-startup", "--python-expr", DEVICES_PY], capture_output=True,
                               text=True, errors="replace", timeout=300)
            info["devices"] = [l[7:] for l in r.stdout.splitlines() if l.startswith("DEVICE ")]
        except (OSError, subprocess.SubprocessError) as e:
            info["devices"] = [f"ошибка: {e}"]
        cfg = jload(CFG, {}) or {}
        cfg["blender"] = b
        jdump(cfg, CFG)
    du = shutil.disk_usage(ROOT)
    info["disk_free_gb"] = round(du.free / 1e9, 1)
    if WIN:
        fonts = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
        info["fonts"] = {f: os.path.exists(os.path.join(fonts, f)) for f in ("bahnschrift.ttf", "segoeui.ttf")}
    info["root_ascii"] = ROOT.isascii() and len(ROOT) < 60
    info["episodes"] = sorted(os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "episodes", "ep*")))
    st = status_dict(None)
    info["rendering"] = st["running"]
    print(json.dumps(info, ensure_ascii=False, indent=1))


# ---------------------------------------------------------------- кадры и статус
def frames_dir(ep, shot):
    return os.path.join(OUT, ep, "9x16", "frames", shot)


def expected_frames(ep):
    ep_json = jload(os.path.join(ROOT, "episodes", ep, "episode.json"), {}) or {}
    return {e["shot"]: int(e["frames"]) for e in ep_json.get("edit", [])}


def complete_frames(ep, shot, settle_s=10.0):
    """Номера готовых кадров: PNG ненулевого размера, с концом IEND, не моложе settle_s (не дописывается)."""
    d = frames_dir(ep, shot)
    done = []
    now = time.time()
    for f in os.listdir(d) if os.path.isdir(d) else []:
        if not re.fullmatch(r"\d{4}\.png", f):
            continue
        p = os.path.join(d, f)
        try:
            st = os.stat(p)
        except OSError:
            continue
        if st.st_size < 1000 or now - st.st_mtime < settle_s:
            continue
        with open(p, "rb") as fh:
            fh.seek(-12, 2)
            if b"IEND" not in fh.read():
                continue
        done.append(int(f[:4]))
    return sorted(done)


def pid_alive(pid):
    if not pid:
        return False
    if WIN:
        # байты: вывод tasklist в OEM-кодировке (cp866), а Python 3.15 по умолчанию читает текст как UTF-8
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True)
        return str(pid).encode() in r.stdout
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def status_dict(ep):
    st = jload(STATUS, {}) or {}
    lease = jload(LOCK, {}) or {}
    queue_running = lease.get("queue") and pid_alive(lease.get("pid"))
    processes = False
    if WIN:
        processes = b"blender.exe" in subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq blender.exe", "/NH"], capture_output=True).stdout.lower()
    running = bool(os.path.exists(LOCK) or queue_running or processes)
    res = {"running": running, "state": st.get("state"), "current": st.get("current"), "started": st.get("started"),
           "errors": st.get("errors", []), "device": st.get("device")}
    if lease.get("queue"):
        res.update(state="queue", current=lease.get("label"), started=None)
    ep = ep or st.get("ep")
    if ep:
        exp = expected_frames(ep)
        res["ep"] = ep
        res["shots"] = {}
        for shot, n in exp.items():
            done = complete_frames(ep, shot, settle_s=0)
            res["shots"][shot] = {"done": len(done), "of": n}
        cur = st.get("current")
        if cur:
            log = os.path.join(OUT, "logs", ep, f"render_{cur}.log")
            try:
                with open(log, encoding="utf-8", errors="replace") as fh:
                    res["log_tail"] = [l.rstrip() for l in fh.readlines()[-3:]]
            except OSError:
                pass
    return res


def cmd_status(a):
    print(json.dumps(status_dict(a.ep), ensure_ascii=False, indent=1))


# ---------------------------------------------------------------- запуск/остановка
def cmd_start(a):
    print("ОШИБКА: прямой start заменён очередью. На клиенте: tools/render_queue.py submit frames <episode.json> --approved <одобрение>")
    sys.exit(2)


def keep_awake(on):
    if not WIN:
        return
    import ctypes
    ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0))


def cmd_run(a):
    job = jload(JOB)
    if not job:
        print("нет out/remote_job.json")
        sys.exit(2)
    ep, shots, b = job["ep"], job["shots"], job["blender"]
    os.makedirs(OUT, exist_ok=True)
    with open(LOCK, "w", encoding="utf-8") as fh:
        fh.write(f"{os.getpid()} {time.strftime('%F_%T')} {ep} {' '.join(shots)}\n")
    st = {"ep": ep, "shots": shots, "pid": os.getpid(), "started": time.strftime("%F %T"), "state": "rendering",
          "current": None, "done": [], "errors": [], "device": job.get("device") or "auto"}
    jdump(st, STATUS)
    env = dict(os.environ, PYTHONUNBUFFERED="1")
    if job.get("device"):
        env["SPACEKIT_DEVICE"] = job["device"]
    script = os.path.join(ROOT, "episodes", ep, "shots_9x16.py")
    log_dir = os.path.join(OUT, "logs", ep)
    os.makedirs(log_dir, exist_ok=True)
    flags = 0x08000000 if WIN else 0                              # CREATE_NO_WINDOW
    keep_awake(True)
    try:
        for shot in shots:
            st["current"] = shot
            jdump(st, STATUS)
            ok = False
            for attempt in (1, 2):                                # один повтор: докачка продолжит с места
                log = os.path.join(log_dir, f"render_{shot}.log")
                with open(log, "a", encoding="utf-8", errors="replace") as fh:
                    fh.write(f"=== {time.strftime('%F %T')} start {shot} (attempt {attempt})\n")
                    fh.flush()
                    rc = subprocess.run([b, "-b", "--factory-startup", "--python-exit-code", "1", "-P", script,
                                         "--", shot, "final"], stdout=fh, stderr=subprocess.STDOUT, cwd=ROOT,
                                        env=env, creationflags=flags).returncode
                with open(log, encoding="utf-8", errors="replace") as fh:
                    tail = fh.readlines()[-200:]
                bad = rc != 0 or any(ERR_RX.search(l) for l in tail)
                if not bad:
                    ok = True
                    break
            (st["done"] if ok else st["errors"]).append(shot)
            jdump(st, STATUS)
        st["state"] = "finished" if not st["errors"] else "finished_with_errors"
    finally:
        st["current"] = None
        st["finished"] = time.strftime("%F %T")
        if st["state"] == "rendering":
            st["state"] = "stopped"
        jdump(st, STATUS)
        keep_awake(False)
        try:
            os.remove(LOCK)
        except OSError:
            pass
        if WIN:
            subprocess.run(["schtasks", "/Delete", "/F", "/TN", TASK], capture_output=True)


def cmd_stop(a):
    if (jload(LOCK, {}) or {}).get("queue"):
        print("ОШИБКА: это задание очереди; отменяй его через render_queue.py cancel JOB")
        sys.exit(2)
    st = jload(STATUS, {}) or {}
    pid = st.get("pid")
    if WIN:
        subprocess.run(["schtasks", "/End", "/TN", TASK], capture_output=True)
        if pid:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        subprocess.run(["schtasks", "/Delete", "/F", "/TN", TASK], capture_output=True)
    elif pid:
        try:
            os.killpg(os.getpgid(pid), 15)
        except OSError:
            pass
    st["state"] = "stopped"
    jdump(st, STATUS)
    try:
        os.remove(LOCK)
    except OSError:
        pass
    print("OK: остановлено (готовые кадры остаются, start продолжит с места)")


# ---------------------------------------------------------------- отдача кадров
def cmd_pack(a):
    done = [f for f in complete_frames(a.ep, a.shot) if f >= a.from_]
    if a.max:
        done = done[: a.max]
    if not done:
        print(json.dumps({"path": None, "count": 0}))
        return
    xfer = os.path.join(OUT, "_xfer")
    os.makedirs(xfer, exist_ok=True)
    path = os.path.join(xfer, f"{a.ep}_{a.shot}_{done[0]:04d}-{done[-1]:04d}.tar")
    with tarfile.open(path, "w") as tf:
        for f in done:
            tf.add(os.path.join(frames_dir(a.ep, a.shot), f"{f:04d}.png"), arcname=f"{f:04d}.png")
    print(json.dumps({"path": path.replace("\\", "/"), "count": len(done), "first": done[0], "last": done[-1]}))


def cmd_rm(a):
    p = os.path.abspath(a.path)
    if os.path.dirname(p) == os.path.join(OUT, "_xfer") and p.endswith(".tar"):
        os.remove(p)
        print("OK")
    else:
        print("ОШИБКА: удаляю только out/_xfer/*.tar")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check")
    p.add_argument("--blender")
    p = sub.add_parser("start")
    p.add_argument("--ep", required=True)
    p.add_argument("--shots", required=True)
    p.add_argument("--blender")
    p.add_argument("--device")
    sub.add_parser("run")
    p = sub.add_parser("status")
    p.add_argument("--ep")
    sub.add_parser("stop")
    p = sub.add_parser("pack")
    p.add_argument("--ep", required=True)
    p.add_argument("--shot", required=True)
    p.add_argument("--from", dest="from_", type=int, default=1)
    p.add_argument("--max", type=int, default=0)
    p = sub.add_parser("rm")
    p.add_argument("path")
    a = ap.parse_args()
    {"check": cmd_check, "start": cmd_start, "run": cmd_run, "status": cmd_status, "stop": cmd_stop,
     "pack": cmd_pack, "rm": cmd_rm}[a.cmd](a)


if __name__ == "__main__":
    main()
