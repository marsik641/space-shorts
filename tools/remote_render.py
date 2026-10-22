"""Рендер эпизода на другом ПК по ssh (агент — tools/remote/agent.py; настройка удалённого ПК — docs/remote_render.md).

    python tools/remote_render.py keygen                                   ключ ~/.ssh/orbitfall_render (+ показать .pub)
    python tools/remote_render.py setup  --host user@100.x.y.z [--root D:/orbitfall] [--py python] [--ep EP]
    python tools/remote_render.py push   [--ep EP] [--assets]             залить код (после правок шотов/библиотеки)
    python tools/remote_render.py check                                    окружение там: Blender, GPU, шрифты, диск
    python tools/remote_render.py start  [--ep EP] [--shots v1,v2] [--device OPTIX]
    python tools/remote_render.py status [--ep EP]
    python tools/remote_render.py pull   [--ep EP] [--watch] [--every 300] забрать готовые кадры (с проверкой PNG;
                                                                           все пришли — tools/framecheck.py, FAIL → код 1)
    python tools/remote_render.py stop
    python tools/remote_render.py free                                     какой ПК свободен (этот / удалённый)

host/root/py/ключ запоминаются в out/remote.json после setup (дальше --host не нужен). Эпизод по умолчанию —
последний episodes/ep*. Кадры ложатся туда же, куда кладёт локальный рендер: out/<ep>/9x16/frames/<шот>/####.png —
дальше конвейер как обычно (tools/cues.py, tts, music, build_edit, assemble, qa). Удалённый рендер не трогает
локальный GPU: out/RENDER.lock здесь не ставится. Шоты одного ролика рендерить на одной машине (денойзер, драйверы).
Нужны ssh и scp в PATH (Git Bash/OpenSSH Windows).
"""
import argparse
import glob
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONF = os.path.join(REPO, "out", "remote.json")
KEY = os.path.expanduser("~/.ssh/orbitfall_render")


def conf(a=None):
    c = {"host": None, "root": "D:/orbitfall", "py": "python", "key": KEY}
    try:
        c.update(json.load(open(CONF, encoding="utf-8")))
    except (OSError, ValueError):
        pass
    if a is not None:
        for k in ("host", "root", "py"):
            if getattr(a, k, None):
                c[k] = getattr(a, k)
    return c


def save_conf(c):
    os.makedirs(os.path.dirname(CONF), exist_ok=True)
    json.dump(c, open(CONF, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def ssh_base(c):
    opts = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "-o", "ServerAliveInterval=30",
            "-o", "StrictHostKeyChecking=accept-new"]
    if c.get("key") and os.path.exists(c["key"]):
        opts += ["-i", c["key"]]
    return opts


def ssh(c, cmd, capture=True, check=True):
    """Команда на удалённом ПК (там cmd.exe или sh — пишем без конструкций оболочки)."""
    r = subprocess.run(["ssh"] + ssh_base(c) + [c["host"], cmd], capture_output=capture, text=True)
    if check and r.returncode != 0:
        sys.exit(f"ssh: код {r.returncode}\n{(r.stderr or '').strip()}\n{(r.stdout or '').strip()}")
    return r.stdout if capture else ""


def rpath(c, path):
    """Путь на удалённом ПК для scp: у Win32-OpenSSH (SFTP) диск пишется как /C:/…"""
    p = path.replace("\\", "/")
    return f'{c["host"]}:/{p}' if len(p) > 1 and p[1] == ":" else f'{c["host"]}:{p}'


def scp(c, src, dst):
    r = subprocess.run(["scp", "-q"] + ssh_base(c) + [src, dst], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"scp {src} -> {dst}: {r.stderr.strip()}")


def agent(c, args, capture=True):
    return ssh(c, f'{c["py"]} "{c["root"]}/tools/remote/agent.py" {args}', capture=capture)


def default_ep():
    eps = sorted(os.path.basename(p) for p in glob.glob(os.path.join(REPO, "episodes", "ep[0-9]*")))
    return eps[-1]


def expected(ep):
    e = json.load(open(os.path.join(REPO, "episodes", ep, "episode.json"), encoding="utf-8"))
    return {s["shot"]: int(s["frames"]) for s in e["edit"]}


# ---------------------------------------------------------------- ключ
def cmd_keygen(a):
    if not os.path.exists(KEY):
        os.makedirs(os.path.dirname(KEY), exist_ok=True)
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "orbitfall-render", "-f", KEY], check=True)
        print("создан ключ", KEY)
    print(open(KEY + ".pub", encoding="utf-8").read().strip())


# ---------------------------------------------------------------- заливка кода
def build_tar(ep, assets):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        def add(rel):
            p = os.path.join(REPO, rel)
            if os.path.isdir(p):
                for root, dirs, files in os.walk(p):
                    dirs[:] = [d for d in dirs if d != "__pycache__"]
                    for f in files:
                        if not f.endswith(".pyc"):
                            fp = os.path.join(root, f)
                            tf.add(fp, arcname=os.path.relpath(fp, REPO).replace("\\", "/"))
            elif os.path.exists(p):
                tf.add(p, arcname=rel)
        for rel in ("spacekit", f"episodes/{ep}", "tools/remote/agent.py"):
            add(rel)
        if assets:
            for f in ("milkyway.exr", "milkyway_maps.npz", "milkyway.json"):
                add(f"assets/{f}")
            for p in glob.glob(os.path.join(REPO, "assets", "voyager_cover_v*.npy")):
                add("assets/" + os.path.basename(p))
    return buf.getvalue()


def cmd_push(a, c=None):
    c = c or conf(a)
    ep = a.ep or default_ep()
    data = build_tar(ep, a.assets)
    root = c["root"]
    ssh(c, f'{c["py"]} -c "import os;os.makedirs(r\'{root}\',exist_ok=True)"')
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "push.tar")
        open(p, "wb").write(data)
        scp(c, p, rpath(c, f"{root}/_push.tar"))
    ssh(c, f'tar -xf "{root}/_push.tar" -C "{root}"')
    ssh(c, f'{c["py"]} -c "import os;os.remove(r\'{root}/_push.tar\')"')
    print(f"OK: залито {len(data) / 1e6:.1f} МБ ({ep}{', ассеты' if a.assets else ''}) -> {c['host']}:{root}")


def cmd_setup(a):
    c = conf(a)
    if not c["host"]:
        sys.exit("нужен --host user@адрес")
    save_conf(c)
    print(ssh(c, "whoami").strip(), "@", c["host"])
    a.assets = True
    cmd_push(a, c)
    print(agent(c, "check"))


def cmd_check(a):
    print(agent(conf(a), "check"))


# ---------------------------------------------------------------- рендер
def cmd_start(a):
    c = conf(a)
    ep = a.ep or default_ep()
    shots = a.shots or ",".join(expected(ep))
    dev = f" --device {a.device}" if a.device else ""
    print(agent(c, f"start --ep {ep} --shots {shots}{dev}").strip())


def local_done(ep, shot):
    d = os.path.join(REPO, "out", ep, "9x16", "frames", shot)
    ok = set()
    for p in glob.glob(os.path.join(d, "[0-9][0-9][0-9][0-9].png")):
        if valid_png(p):
            ok.add(int(os.path.basename(p)[:4]))
    return ok


def valid_png(p):
    try:
        if os.path.getsize(p) < 1000:
            return False
        with open(p, "rb") as fh:
            head = fh.read(8)
            fh.seek(-12, 2)
            return head == b"\x89PNG\r\n\x1a\n" and b"IEND" in fh.read()
    except OSError:
        return False


def remote_status(c, ep):
    return json.loads(agent(c, f"status --ep {ep}"))


def cmd_status(a):
    c = conf(a)
    ep = a.ep or default_ep()
    st = remote_status(c, ep)
    exp = expected(ep)
    tot_r = sum(v["done"] for v in st.get("shots", {}).values())
    tot = sum(exp.values())
    print(f"{ep}: там {tot_r}/{tot} кадров, рендер {'идёт' if st['running'] else 'не идёт'} "
          f"({st.get('state')}, шот {st.get('current')}, устройство {st.get('device')})")
    for shot, n in exp.items():
        r = st.get("shots", {}).get(shot, {}).get("done", 0)
        print(f"  {shot}: там {r:4d}/{n}  здесь {len(local_done(ep, shot)):4d}/{n}")
    if st.get("errors"):
        print("ОШИБКИ в шотах:", st["errors"])
    for l in st.get("log_tail", []):
        print("  | " + l[:150])
    if st.get("started") and st["running"] and tot_r:
        t0 = time.mktime(time.strptime(st["started"], "%Y-%m-%d %H:%M:%S"))
        spf = (time.time() - t0) / max(tot_r, 1)          # грубо: включая уже бывшие кадры до перезапуска
        print(f"  ≈ {spf:.1f} с/кадр, осталось ≈ {(tot - tot_r) * spf / 3600:.1f} ч (оценка по средней)")


def pull_once(c, ep, shots):
    got = 0
    for shot in shots:
        n = expected(ep)[shot]
        while True:
            have = local_done(ep, shot)
            missing = [f for f in range(1, n + 1) if f not in have]
            if not missing:
                break
            r = json.loads(agent(c, f"pack --ep {ep} --shot {shot} --from {missing[0]} --max 300"))
            if not r.get("count"):
                break
            dst = os.path.join(REPO, "out", ep, "9x16", "frames", shot)
            os.makedirs(dst, exist_ok=True)
            with tempfile.TemporaryDirectory() as td:
                tp = os.path.join(td, "x.tar")
                scp(c, rpath(c, r["path"]), tp)
                with tarfile.open(tp) as tf:
                    for m in tf.getmembers():
                        if m.isfile() and len(m.name) == 8 and m.name.endswith(".png") and "/" not in m.name:
                            tf.extract(m, dst)
            agent(c, f'rm "{r["path"]}"')
            bad = [f for f in range(r["first"], r["last"] + 1)
                   if os.path.exists(os.path.join(dst, f"{f:04d}.png")) and not valid_png(os.path.join(dst, f"{f:04d}.png"))]
            for f in bad:
                os.remove(os.path.join(dst, f"{f:04d}.png"))
            got += r["count"] - len(bad)
            print(f"  {shot}: +{r['count'] - len(bad)} ({r['first']}–{r['last']}){'  битых: ' + str(bad) if bad else ''}")
            if r["count"] < 300:
                break
    return got


def pull_logs(c, ep):
    """Логи рендера (render_<шот>.log) — в out/logs/<ep>/: из них tools/cues.py берёт FLASH/EVENT."""
    dst = os.path.join(REPO, "out", "logs", ep)
    os.makedirs(dst, exist_ok=True)
    r = subprocess.run(["scp", "-q"] + ssh_base(c) + [rpath(c, f'{c["root"]}/out/logs/{ep}/render_*.log'), dst],
                       capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        print("WARN: логи не забраны:", r.stderr.strip()[-200:])


def cmd_pull(a):
    c = conf(a)
    ep = a.ep or default_ep()
    exp = expected(ep)
    shots = a.shots.split(",") if a.shots else list(exp)
    while True:
        got = pull_once(c, ep, shots)
        pull_logs(c, ep)
        complete = all(len(local_done(ep, s)) >= exp[s] for s in shots)
        st = remote_status(c, ep)
        print(f"[{time.strftime('%H:%M:%S')}] забрано {got}; здесь "
              + ", ".join(f"{s} {len(local_done(ep, s))}/{exp[s]}" for s in shots)
              + f"; там рендер {'идёт' if st['running'] else 'не идёт'}")
        if complete:
            print("OK: все кадры здесь — framecheck (сбои рендера по скачкам размера PNG):", flush=True)
            fc = [sys.executable, os.path.join(REPO, "tools", "framecheck.py"),
                  os.path.join(REPO, "episodes", ep, "episode.json")] + (["--shots", a.shots] if a.shots else [])
            if subprocess.run(fc).returncode:
                sys.exit("framecheck FAIL: кадры из строк RERENDER удалить здесь и там, start (докачка) и pull "
                         "(или перерендерить здесь) — docs/remote_render.md")
            return
        if not a.watch:
            return
        if not st["running"] and got == 0:
            sys.exit("рендер там не идёт, а кадров не хватает — смотрите status (ошибки) и start")
        time.sleep(a.every)


def cmd_stop(a):
    print(agent(conf(a), "stop").strip())


# ---------------------------------------------------------------- какой ПК свободен
def local_busy():
    """Здесь занято: out/RENDER.lock или любой blender.exe (рендер, превью, сборка — один Blender за раз)."""
    why = []
    if os.path.exists(os.path.join(REPO, "out", "RENDER.lock")):
        why.append("out/RENDER.lock: " + open(os.path.join(REPO, "out", "RENDER.lock"), encoding="utf-8",
                                               errors="replace").read().strip())
    if os.name == "nt":
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq blender.exe", "/NH"], capture_output=True)
        if b"blender.exe" in r.stdout.lower():
            why.append("blender.exe в процессах")
    return why


def cmd_free(a):
    """Оба ПК: занят/свободен; последняя строка — FREE <ПК> или BUSY (оба свободны → удалённый: этот остаётся
    владельцу и для части B — звук и сборка идут здесь)."""
    c = conf(a)
    why = local_busy()
    print(f"этот ПК: {'занят — ' + '; '.join(why) if why else 'свободен'}")
    remote = None
    if c.get("host"):
        r = subprocess.run(["ssh"] + ssh_base(c) + ["-o", "ConnectTimeout=10", c["host"],
                            f'{c["py"]} "{c["root"]}/tools/remote/agent.py" status'], capture_output=True, text=True,
                           errors="replace")
        try:
            st = json.loads(r.stdout)
        except ValueError:
            print(f"{c['host']}: недоступен (ssh {r.returncode}: {(r.stderr or '').strip()[-150:]}) — у владельца ПК "
                  "выключен прокси? ПК не спит? (docs/remote_render.md)")
        else:
            if st["running"]:
                done = sum(v["done"] for v in st.get("shots", {}).values())
                tot = sum(v["of"] for v in st.get("shots", {}).values())
                print(f"{c['host']}: занят — {st.get('ep')}, шот {st.get('current')}, {done}/{tot} кадров, "
                      f"с {st.get('started')}")
            else:
                print(f"{c['host']}: свободен")
                remote = c["host"]
    else:
        print("удалённый ПК не настроен (remote_render.py setup)")
    if remote:
        print(f"FREE remote {remote}")
    elif not why:
        print("FREE local")
    else:
        print("BUSY оба ПК заняты")


def main():
    for s in (sys.stdout, sys.stderr):                     # в пайп/лог Windows пишет cp1251 — без «≈» и с кракозябрами
        s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("keygen")
    for name in ("setup", "push", "check", "start", "status", "pull", "stop", "free"):
        p = sub.add_parser(name)
        p.add_argument("--host")
        p.add_argument("--root")
        p.add_argument("--py")
        p.add_argument("--ep")
        if name in ("setup", "push"):
            p.add_argument("--assets", action="store_true", help="залить и ассеты неба (34 МБ; иначе сгенерятся там)")
        if name in ("start", "pull"):
            p.add_argument("--shots")
        if name == "start":
            p.add_argument("--device", help="OPTIX|CUDA|HIP|ONEAPI|METAL|CPU (по умолчанию — первое доступное)")
        if name == "pull":
            p.add_argument("--watch", action="store_true")
            p.add_argument("--every", type=int, default=300)
    a = ap.parse_args()
    {"keygen": cmd_keygen, "setup": cmd_setup, "push": cmd_push, "check": cmd_check, "start": cmd_start,
     "status": cmd_status, "pull": cmd_pull, "stop": cmd_stop, "free": cmd_free}[a.cmd](a)


if __name__ == "__main__":
    main()
