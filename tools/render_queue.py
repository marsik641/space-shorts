"""Постоянная очередь Blender и звука для независимых чатов. См. docs/render_queue.md.

    python tools/render_queue.py submit preview episodes/<ep>/episode.json
    python tools/render_queue.py submit final episodes/<ep>/episode.json --approved "ок пользователя, дата"
    python tools/render_queue.py status [--json]
    python tools/render_queue.py pause|resume|cancel|retry|accept JOB
    python tools/render_queue.py start|stop

Стандартная библиотека Python 3.10+. Состояние и короткие снимки — out/q основной git worktree.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
from pathlib import PureWindowsPath
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import time
import uuid

from queue_runtime import (Busy, NO_WINDOW, alive, execute, extract_tar, file_lock, queue_home,
                           keep_awake, read_json, write_json)

ROOT = Path(__file__).resolve().parents[1]
TERMINAL = ("done", "needs_review", "cancelled", "failed")


class Store:
    def __init__(self, home):
        self.home = Path(home).absolute()
        self.home.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, kind TEXT, episode TEXT, source TEXT, created REAL,
                    priority INTEGER, target TEXT, render_host TEXT, state TEXT, cursor INTEGER DEFAULT 0,
                    active TEXT, plan TEXT, approval TEXT, error TEXT, control TEXT, fingerprint TEXT
                );
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
            """)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.home / "queue.sqlite3", timeout=30)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA busy_timeout=30000")
            with db:
                yield db
        finally:
            db.close()

    def jobs(self):
        with self.db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM jobs ORDER BY priority DESC, created, id")]

    def get(self, jid):
        with self.db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
        if row is None:
            raise ValueError(f"Нет задания {jid}")
        return dict(row)

    def setting(self, key, value=None):
        with self.db() as db:
            if value is not None:
                db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, str(value)))
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def change(self, jid, **kw):
        with self.db() as db:
            db.execute("UPDATE jobs SET " + ",".join(k + "=?" for k in kw) + " WHERE id=?", (*kw.values(), jid))

    def claim(self, lane, remote_free=False):
        """Выбор и резервирование одним BEGIN IMMEDIATE; состояние не зависит от чатов."""
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT * FROM jobs WHERE state IN ('queued','running') AND active IS NULL "
                              "AND control IS NULL ORDER BY priority DESC, created, id").fetchall()
            for row in rows:
                job = dict(row)
                step = json.loads(job["plan"])[job["cursor"]]
                if step["lane"] == "local":
                    if lane != "local":
                        continue
                else:
                    host = job["render_host"] or job["target"]
                    if host != "auto" and host != lane:
                        continue
                    if host == "auto" and lane == "remote" and not remote_free:
                        continue
                    if host == "auto" and lane == "local" and remote_free:
                        continue
                # У одного задания нет двух активных шагов; GPU зарезервирован ресурсным lock.
                pinned = job["render_host"]
                if step["lane"] == "render" and not pinned:
                    pinned = lane
                db.execute("UPDATE jobs SET state='running', active=?, render_host=? WHERE id=?",
                           (lane, pinned, job["id"]))
                job.update(active=lane, render_host=pinned, state="running")
                return job, step
        return None


def step(name, argv, log, lane="local", outputs=()):
    return dict(name=name, argv=list(map(str, argv)), log=log, lane=lane, outputs=list(outputs))


def plan_episode(ep, episode_rel, kind, shots=None, frames=None, pct=50, samples=None, chunk=120, with_tts=False):
    eid, fmt = ep["id"], ep.get("format_name", "9x16")
    base = f"out/{eid}/{fmt}"
    script = ep.get("shots_script", f"episodes/{eid}/shots_{fmt}.py")
    script_json = ep.get("script", f"episodes/{eid}/script_{fmt}.json")
    cues = ep.get("music_cues", f"episodes/{eid}/music_cues.json")
    audio = ep.get("audio_dir", base + "/audio")
    frame_base = ep.get("frames_dir", base + "/frames")
    for path in (script, script_json, cues, audio, frame_base, ep.get("output", base + "/{id}_{lang}.mp4")):
        if Path(path).is_absolute() or PureWindowsPath(path).is_absolute() or ".." in Path(path).parts or "\\" in path:
            raise ValueError(f"Для снимка нужны относительные пути без '..' и обратных слешей: {path}")
    entries = {e["shot"]: e for e in ep["edit"]}
    selected = shots.split(",") if shots else list(entries)
    if len(selected) != len(set(selected)) or not selected or set(selected) - entries.keys():
        raise ValueError("Некорректный список шотов")
    if kind == "final" and shots:
        raise ValueError("final всегда включает весь эпизод; для части кадров — frames")
    plan = [step("check_episode", ["PYTHON", "tools/check_episode.py", episode_rel], "out/queue_check.log")]
    for shot in selected:
        e = entries[shot]
        first, end = e.get("first", 1), e.get("first", 1) + e["frames"] - 1
        cmd = ["BLENDER", "-b", "--factory-startup", "--python-exit-code", "1", "-P", "tools/queue_blender.py", "--", script, shot]
        if kind == "preview":
            fs = sorted(set(map(int, frames.split(",")))) if frames else sorted({first, first + (end-first)//3, first + 2*(end-first)//3, end})
            if not fs or min(fs) < first or max(fs) > end:
                raise ValueError(f"Кадры превью вне {shot}: {first}…{end}")
            args = ["preview", ",".join(map(str, fs)), f"pct={pct}"]
            if samples is not None:
                args += [f"samples={samples}"]
            outputs = [f"{base}/previews/{shot}_f{f:04d}.png" for f in fs]
            plan.append(step(f"preview {shot}", cmd + args, f"{base}/logs/prev_{shot}.log", "render", outputs))
        else:
            for start in range(first, end + 1, chunk):
                last = min(end, start + chunk - 1)
                outputs = [f"{frame_base}/{shot}/{f:04d}.png" for f in range(start, last + 1)]
                plan.append(step(f"render {shot} {start}-{last}", cmd + ["final", f"queue_range={start}-{last}"],
                                 f"out/logs/{eid}/render_{shot}.log", "render", outputs))
    if kind == "preview":
        images = [p for s in plan for p in s["outputs"]]
        plan.append(step("contact", ["BLENDER", "-b", "--factory-startup", "--python-exit-code", "1", "-P", "tools/contact.py", "--",
                                     base + "/sheet_prev.png", "4", "270", *images], "out/queue_contact.log", outputs=[base + "/sheet_prev.png"]))
    else:
        args = ["--shots", ",".join(selected)] if kind == "frames" else []
        plan.append(step("framecheck", ["PYTHON", "tools/framecheck.py", episode_rel, *args], "out/queue_frames.log"))
    if with_tts or kind == "final":
        plan.append(step("tts", ["PYTHON", "tools/tts.py", script_json, "en", audio], "out/queue_tts.log",
                         outputs=[audio + "/vo_en.wav", audio + "/captions_en.json"]))
    if kind == "final":
        # Cue уже согласован по превью. Автоматически менять гармонию/события после одобрения нельзя.
        plan.extend([
            step("music", ["PYTHON", "tools/music.py", cues, audio + "/music.wav"], "out/queue_music.log"),
            step("mix", ["PYTHON", "tools/mix.py", audio + "/vo_en.wav", audio + "/music.wav", audio + "/mix_en.wav"], "out/queue_mix.log"),
            step("build_edit", ["PYTHON", "tools/build_edit.py", episode_rel, "en"], "out/queue_edit.log"),
            step("assemble", ["BLENDER", "-b", "--factory-startup", "--python-exit-code", "1", "-P", "editkit/assemble.py", "--",
                              f"episodes/{eid}/edit_{fmt}_en.json"], "out/queue_assemble.log"),
            step("qa", ["PYTHON", "tools/qa.py", episode_rel, "en"], "out/queue_qa.log"),
            step("release", ["PYTHON", "tools/release.py", episode_rel], "out/queue_release.log"),
        ])
    return plan


def snapshot(source, dest, episode_rel):
    """Код и обычные ассеты копируются. Большие веса TTS доступны только для чтения через hardlink."""
    episode_dir = Path(episode_rel).parent
    paths = ["spacekit", "editkit", "tools", str(episode_dir)]
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "*.blend", ".git")
    for rel in paths:
        shutil.copytree(source / rel, dest / rel, ignore=ignore)
    # Шлюз берём из реализации очереди, даже если старый worktree ещё не содержит его.
    for name in ("queue_runtime.py", "queue_blender.py", "queue_remote.py", "render_queue.py", "qa.py"):
        shutil.copy2(ROOT / "tools" / name, dest / "tools" / name)
    if (source / "assets").is_dir():
        shutil.copytree(source / "assets", dest / "assets", ignore=shutil.ignore_patterns("tts", "__pycache__"))
    tts_root = source / "assets" / "tts"
    if not tts_root.is_dir():
        tts_root = ROOT / "assets" / "tts"
    if tts_root.is_dir():
        (dest / "assets" / "tts").mkdir(parents=True)
        for p in tts_root.iterdir():
            if p.is_file():
                try:
                    os.link(p, dest / "assets" / "tts" / p.name)
                except OSError:
                    shutil.copy2(p, dest / "assets" / "tts" / p.name)
    hashes = {}
    for rel in paths + ["assets"]:
        for p in sorted((dest / rel).rglob("*")):
            if p.is_file() and not p.is_relative_to(dest / "assets/tts"):
                hashes[p.relative_to(dest).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    write_json(dest / "inputs.json", hashes)
    return hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()


def submit(store, a):
    episode_path = Path(a.episode).absolute()
    source = episode_path.parents[2]
    episode_rel = episode_path.relative_to(source).as_posix()
    if episode_path.parent.parent.name != "episodes" or episode_path.name != "episode.json":
        raise ValueError("Нужен episodes/<ep>/episode.json")
    ep = read_json(episode_path)
    if ep is None or ep.get("id") != episode_path.parent.name:
        raise ValueError("id эпизода должен совпадать с папкой")
    if ep.get("languages") != ["en"]:
        raise ValueError("Очередь выпускает только EN")
    if a.kind in ("frames", "final") and not (a.approved or "").strip():
        raise ValueError("Для frames/final нужен --approved с записью уже полученного одобрения пользователя")
    if a.kind == "final" and not (episode_path.parent / "publish_en.md").is_file():
        raise ValueError("До постановки final подготовь publish_en.md")
    # Снимок одной и той же версии не должен попасть в очередь дважды при одновременной отправке.
    jid = uuid.uuid4().hex[:10]
    dest = store.home / jid
    dest.mkdir()
    fingerprint = snapshot(source, dest, episode_rel)
    frozen_ep = read_json(dest / episode_rel)
    if a.kind == "task":
        script = a.script or ""
        if not script or Path(script).is_absolute() or PureWindowsPath(script).is_absolute() or ".." in Path(script).parts:
            raise ValueError("task требует --script с относительным путём внутри снимка")
        if not (dest / script).is_file():
            raise ValueError(f"В снимке нет скрипта {script}")
        if "final" in a.args and not (a.approved or "").strip():
            raise ValueError("Для task с final нужен --approved из чата")
        if a.target == "remote":
            raise ValueError("Произвольный task поддержан на local; preview/frames/final — на обоих ПК")
        a.target = "local"
        plan = [step("task " + script, ["BLENDER", "-b", "--factory-startup", "--python-exit-code", "1", "-P",
                                       "tools/queue_blender.py", "--", script, *a.args], "out/queue_task.log")]
    else:
        plan = plan_episode(frozen_ep, episode_rel, a.kind, a.shots, a.frames, a.pct, a.samples, a.chunk, a.with_tts)
    fingerprint = hashlib.sha256((fingerprint + json.dumps(plan, sort_keys=True)).encode()).hexdigest()
    if a.kind in ("frames", "final"):
        # Только снимок, прошедший preflight, получает разрешение расходовать GPU.
        check = subprocess.run([sys.executable, "-S", str(dest / "tools/check_episode.py"), str(dest / episode_rel)],
                               capture_output=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        (dest / "preflight.log").write_text(check.stdout + check.stderr, encoding="utf-8")
        if check.returncode:
            raise ValueError(f"check_episode FAIL: {dest / 'preflight.log'}")
    approval = (a.approved or "").strip()
    priority = a.priority if a.priority is not None else (100 if a.kind == "preview" else 0)
    write_json(dest / "job.json", dict(id=jid, episode=ep["id"], kind=a.kind, source=str(source),
                                       fingerprint=fingerprint, approval=approval, plan=plan))
    existing = None
    with store.db() as db:
        db.execute("BEGIN IMMEDIATE")
        same = db.execute("SELECT id, fingerprint, kind FROM jobs WHERE episode=? AND state IN ('queued','running','paused')",
                          (ep["id"],)).fetchall()
        for old in same:
            if old["fingerprint"] == fingerprint and old["kind"] == a.kind:
                existing = old["id"]
                break
            if old["kind"] in ("frames", "final") and a.kind in ("frames", "final"):
                raise ValueError(f"У {ep['id']} уже есть финальное задание {old['id']}; cancel перед заменой")
        if not existing:
            db.execute("INSERT INTO jobs (id,kind,episode,source,created,priority,target,state,plan,approval,fingerprint) "
                       "VALUES (?,?,?,?,?,?,?,'queued',?,?,?)",
                       (jid, a.kind, ep["id"], str(source), time.time(), priority, a.target,
                        json.dumps(plan, ensure_ascii=False), approval, fingerprint))
    if existing:
        if dest.resolve().parent != store.home.resolve():
            raise ValueError("Снимок за пределами очереди")
        shutil.rmtree(dest)
        print(f"EXISTS {existing}")
        if not a.no_start:
            start_worker(store)
        return existing
    print(f"QUEUED {jid}: {ep['id']} {a.kind}, {len(plan)} шагов, target={a.target}")
    if not a.no_start:
        start_worker(store)
    return jid


def link_result(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    temp = dst.with_name(dst.name + "." + uuid.uuid4().hex[:6] + ".tmp")
    try:
        os.link(src, temp)
    except OSError:
        shutil.copy2(src, temp)
    os.replace(temp, dst)


def publish_results(store, job):
    snap, source = store.home / job["id"], Path(job["source"])
    eid = job["episode"]
    for folder in (f"out/{eid}", f"out/logs/{eid}"):
        if (snap / folder).is_dir():
            for p in (snap / folder).rglob("*"):
                if p.is_file():
                    link_result(p, source / p.relative_to(snap))
    # Монтажный лист переносится лишь если автор не успел изменить исходники эпизода.
    hashes = read_json(snap / "inputs.json", {})
    ep_prefix = f"episodes/{eid}/"
    unchanged = all((source / rel).is_file() and hashlib.sha256((source / rel).read_bytes()).hexdigest() == h
                    for rel, h in hashes.items() if rel.startswith(ep_prefix))
    if unchanged and job["kind"] == "final":
        for p in (snap / "episodes" / eid).glob("edit_*_en.json"):
            shutil.copy2(p, source / "episodes" / eid / p.name)
    write_json(source / "out" / eid / "queue_result.json",
               dict(job=job["id"], snapshot=str(snap), kind=job["kind"], render_host=job["render_host"],
                    fingerprint=job["fingerprint"], approval=job["approval"], review_required=job["kind"] == "final"))


class Remote:
    """SSH — только транспорт. Сам Blender живёт в отдельном процессе на удалённом ПК."""
    def __init__(self, store):
        self.store = store
        self.cfg = read_json(store.home.parent / "remote.json", {})
        self.ready = False
        self.last_probe = 0
        self.error = ""
        self.deployed = False

    def transport(self, exe, args, timeout=60):
        c = self.cfg
        opts = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=10", "-o", "ServerAliveCountMax=2"]
        if c.get("key"):
            opts += ["-i", c["key"]]
        r = subprocess.run([exe, *opts, *args], capture_output=True, encoding="utf-8", errors="replace",
                           timeout=timeout, creationflags=NO_WINDOW)
        if r.returncode:
            raise ConnectionError(f"{exe}: {r.stderr.strip()[-500:]}")
        return r.stdout

    def ssh(self, args, timeout=60):
        return self.transport("ssh", [self.cfg["host"], subprocess.list2cmdline(list(map(str, args)))], timeout)

    def rpc(self, *args):
        c = self.cfg
        result = self.ssh([c["py"], c["root"] + "/tools/queue_remote.py", *args])
        return json.loads(result)

    def remote_path(self, path):
        return self.cfg["host"] + (":/" if len(path) > 1 and path[1] == ":" else ":") + path

    def probe(self):
        if not self.cfg.get("host"):
            return False
        try:
            # Обновляем только новые файлы транспорта; текущую библиотеку/эпизоды не трогаем.
            c = self.cfg
            remote_tools = c["root"] + "/tools"
            if not self.deployed:
                self.ssh([c["py"], "-c", f"import os;os.makedirs({remote_tools!r},exist_ok=True)"])
                for name in ("queue_remote.py", "queue_runtime.py"):
                    self.transport("scp", [str(ROOT / "tools" / name), self.remote_path(remote_tools + "/" + name)])
                self.deployed = True
            st = self.rpc("probe")
            self.ready = not st["busy"]
            self.error = st.get("reason") or ""
        except (OSError, ValueError, subprocess.SubprocessError, ConnectionError) as e:
            self.ready, self.error = False, str(e)
        self.last_probe = time.time()
        write_json(self.store.home / "remote_state.json", dict(ready=self.ready, checked=self.last_probe, error=self.error))
        return self.ready

    def upload(self, job):
        jid, c = job["id"], self.cfg
        snap = self.store.home / jid
        remote_snap = c["root"] + "/out/q/" + jid
        marker = snap / "uploaded.json"
        if read_json(marker, {}).get("destination") == remote_snap:
            return
        archive = self.store.home / (jid + ".tar")
        with tarfile.open(archive, "w") as tf:
            for folder in ("spacekit", "editkit", "tools", "episodes", "assets"):
                for p in (snap / folder).rglob("*"):
                    if p.is_file() and "__pycache__" not in p.parts and not p.is_relative_to(snap / "assets/tts"):
                        tf.add(p, arcname=p.relative_to(snap).as_posix(), recursive=False)
            tf.add(snap / "job.json", arcname="job.json")
        try:
            self.ssh([c["py"], "-c", f"import os;os.makedirs({remote_snap!r},exist_ok=True)"])
            self.transport("scp", [str(archive), self.remote_path(remote_snap + "/input.tar")], timeout=600)
            self.rpc("unpack", jid)
            write_json(marker, dict(destination=remote_snap))
        finally:
            archive.unlink(missing_ok=True)

    def run(self, job, step):
        jid, index = job["id"], job["cursor"]
        # При обрыве связи не перепоручаем кадры другой машине и не считаем задание законченным.
        while True:
            try:
                self.upload(job)
                st = self.rpc("start", jid, str(index))
                while st["state"] in ("starting", "running", "waiting"):
                    if self.store.get(jid)["control"] == "cancel":
                        self.rpc("cancel", jid, str(index))
                    time.sleep(2)
                    st = self.rpc("status", jid, str(index))
                if st["state"] != "done":
                    raise RuntimeError(st.get("error") or f"Удалённый шаг: {st['state']}")
                result = self.rpc("pack", jid, str(index))
                archive = self.store.home / (jid + ".result.tar")
                self.transport("scp", [self.remote_path(result["path"]), str(archive)], timeout=600)
                try:
                    with tarfile.open(archive) as tf:
                        extract_tar(tf, self.store.home / jid)
                finally:
                    archive.unlink(missing_ok=True)
                self.store.change(jid, error=None)
                return
            except (ConnectionError, subprocess.SubprocessError, OSError) as e:
                self.store.change(jid, error="Связь с remote: " + str(e))
                time.sleep(10)


def python_for(job):
    source = Path(job["source"])
    for root in (source, ROOT):
        for rel in (".venv/Scripts/python.exe", ".venv/bin/python"):
            if (root / rel).is_file():
                return str(root / rel)
    return sys.executable


def finish_step(store, job):
    cursor = job["cursor"] + 1
    count = len(json.loads(job["plan"]))
    if cursor == count and store.get(job["id"])["control"] != "cancel":
        publish_results(store, job)
    with store.db() as db:
        db.execute("BEGIN IMMEDIATE")
        control = db.execute("SELECT control FROM jobs WHERE id=?", (job["id"],)).fetchone()[0]
        if control == "cancel":
            state = "cancelled"
        elif cursor == count:
            state = "needs_review" if job["kind"] == "final" else "done"
        else:
            state = "paused" if control == "pause" else "queued"
        db.execute("UPDATE jobs SET cursor=?,state=?,active=NULL,error=NULL,control=NULL WHERE id=?",
                   (cursor, state, job["id"]))


def worker_loop(store, lane, remote, idle_exit):
    idle_since = time.time()
    while store.setting("stop") != "1":
        if lane == "remote":
            if not remote.cfg.get("host"):
                return
            if time.time() - remote.last_probe > 20:
                remote.probe()
            reconnect = any(j["render_host"] == "remote" and j["state"] in ("queued", "running")
                            and json.loads(j["plan"])[j["cursor"]]["lane"] == "render" for j in store.jobs())
            if not remote.ready and not reconnect:
                if idle_exit and time.time() - idle_since > idle_exit:
                    return
                time.sleep(2)
                continue
        remote_free = remote.ready and not any(j["active"] == "remote" for j in store.jobs())
        claimed = store.claim(lane, remote_free)
        if not claimed:
            if idle_exit and time.time() - idle_since > idle_exit:
                return
            time.sleep(0.5)
            continue
        job, task = claimed
        idle_since = time.time()
        try:
            if lane == "remote":
                remote.ready = False
                # Координатор не должен уснуть посреди удалённого рендера/скачивания.
                keep_awake(True)
                try:
                    remote.run(job, task)
                finally:
                    keep_awake(False)
                remote.ready = True
            else:
                execute(store.home / job["id"], task, python_for(job), store.home,
                        lambda: store.get(job["id"])["control"] == "cancel")
            finish_step(store, job)
        except Busy as e:
            latest = store.get(job["id"])
            control = latest["control"]
            store.change(job["id"], active=None, state={"pause": "paused", "cancel": "cancelled"}.get(control, "queued"),
                         control=None, error="Ожидание ресурса: " + str(e))
            time.sleep(2)
        except Exception as e:
            cancelled = store.get(job["id"])["control"] == "cancel"
            store.change(job["id"], active=None, state="cancelled" if cancelled else "failed", control=None, error=str(e))
            print(f"FAIL {job['id']}: {e}", flush=True)


def work(store, idle_exit=0):
    try:
        with file_lock(store.home / "worker.lck"):
            store.setting("pid", os.getpid())
            # Здесь гарантированно нет другого координатора. Удалённый шаг переподключится по id.
            with store.db() as db:
                db.execute("UPDATE jobs SET active=NULL WHERE active IS NOT NULL")
            remote = Remote(store)
            remote.probe()
            try:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [pool.submit(worker_loop, store, lane, remote, idle_exit) for lane in ("local", "remote")]
                    for future in futures:
                        future.result()
            finally:
                store.setting("pid", "0")
    except Busy:
        return


def start_worker(store):
    store.setting("stop", "0")
    # OS lock — окончательный арбитр; PID нужен лишь для дешёвой проверки статуса.
    try:
        with file_lock(store.home / "worker.lck"):
            pass
    except Busy:
        return
    py = Path(sys.executable)
    pyw = py.with_name("pythonw.exe")
    if os.name == "nt" and pyw.is_file():
        py = pyw
    if os.name == "nt":
        # Планировщик создаёт процесс вне дерева чата/ssh и не ограничивает его 72 часами.
        # Отдельные Execute/Arguments также обходят лимит schtasks /TR в 255 символов.
        quote = lambda value: "'" + str(value).replace("'", "''") + "'"
        args = subprocess.list2cmdline([str(ROOT / "tools/render_queue.py"), "--home", str(store.home), "work"])
        name = "SpaceShortsQueue-" + hashlib.sha256(str(store.home).lower().encode()).hexdigest()[:12]
        script = (
            "$ErrorActionPreference='Stop';"
            f"$action=New-ScheduledTaskAction -Execute {quote(py)} -Argument {quote(args)} -WorkingDirectory {quote(ROOT)};"
            "$sid=[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value;"
            "$principal=New-ScheduledTaskPrincipal -UserId $sid -LogonType Interactive -RunLevel Limited;"
            "$trigger=New-ScheduledTaskTrigger -AtLogOn -User $sid;"
            "$settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) "
            "-MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
            "-StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1);"
            f"Register-ScheduledTask -TaskName {quote(name)} -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null;"
            f"Start-ScheduledTask -TaskName {quote(name)};"
        )
        import base64
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                           capture_output=True, creationflags=NO_WINDOW, timeout=45)
        if r.returncode:
            raise RuntimeError("Не удалось запустить worker через Планировщик Windows. Задание сохранено; "
                               "повтори render_queue.py start вне песочницы чата. " + r.stderr.decode("utf-8", "replace")[-700:])
        return
    env = dict(os.environ, SPACEKIT_QUEUE_HOME=str(store.home), PYTHONIOENCODING="utf-8")
    with open(store.home / "worker.log", "ab") as log:
        subprocess.Popen([str(py), str(ROOT / "tools/render_queue.py"), "work"], cwd=ROOT,
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log, env=env,
                         creationflags=(0x00000008 | 0x00000200 | NO_WINDOW) if os.name == "nt" else 0,
                         start_new_session=os.name != "nt")


def control_job(store, cmd, jid, rerender_shots=None):
    job = store.get(jid)
    if cmd in ("pause", "cancel"):
        with store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            job = dict(db.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone())
            if job["state"] in TERMINAL:
                raise ValueError(f"Задание уже {job['state']}")
            if job["active"]:
                db.execute("UPDATE jobs SET control=? WHERE id=?", (cmd, jid))
            else:
                db.execute("UPDATE jobs SET state=?,control=NULL WHERE id=?", ("paused" if cmd == "pause" else "cancelled", jid))
    elif cmd in ("resume", "retry"):
        allowed = ("paused",) if cmd == "resume" else ("failed",)
        if job["state"] not in allowed:
            raise ValueError(f"{cmd} неприменим к {job['state']}")
        plan = json.loads(job["plan"])
        cursor = job["cursor"]
        if rerender_shots:
            shots = set(rerender_shots.split(","))
            indexes = [i for i, s in enumerate(plan) if s["name"].startswith("render ") and s["name"].split()[1] in shots]
            found = {plan[i]["name"].split()[1] for i in indexes}
            if cmd != "retry" or not indexes or found != shots:
                raise ValueError("--rerender-shots применим к retry с шотами финального рендера")
            cursor = min(indexes)
            if job["render_host"] == "remote":
                remote = Remote(store)
                for i, s in enumerate(plan[cursor:], cursor):
                    if s["lane"] == "render":
                        remote.rpc("reset", jid, str(i))
        elif cmd == "retry" and job["render_host"] == "remote" and plan[cursor]["lane"] == "render":
            # Удалённый неуспешный шаг сбрасывается отдельной RPC; готовые кадры остаются.
            Remote(store).rpc("retry", jid, str(job["cursor"]))
        store.change(jid, state="queued", control=None, error=None, cursor=cursor)
        start_worker(store)
    elif cmd == "accept":
        if job["state"] != "needs_review":
            raise ValueError("accept — только после машинного QA и просмотра PNG/мастера")
        store.change(jid, state="done")
        result_path = Path(job["source"]) / "out" / job["episode"] / "queue_result.json"
        result = read_json(result_path, {})
        if result.get("job") == jid:
            write_json(result_path, dict(result, review_required=False, reviewed=time.time()))
    print(f"{jid}: {store.get(jid)['state']}")


def status(store, as_json=False):
    jobs = store.jobs()
    for j in jobs:
        plan = json.loads(j.pop("plan"))
        j["steps"] = len(plan)
        j["step"] = plan[j["cursor"]]["name"] if j["cursor"] < len(plan) else None
        j["snapshot"] = str(store.home / j["id"])
    data = dict(home=str(store.home), worker_pid=int(store.setting("pid") or 0),
                worker_running=alive(int(store.setting("pid") or 0)), jobs=jobs,
                remote=read_json(store.home / "remote_state.json"))
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(f"Очередь: {store.home}; worker {'работает' if data['worker_running'] else 'остановлен'}")
        for j in jobs:
            print(f"{j['id']} {j['state']:12} {j['episode']} {j['kind']} {j['cursor']}/{j['steps']} "
                  f"{j['active'] or j['render_host'] or j['target']} | {j['step'] or '-'}")
            if j["error"]:
                print("  " + j["error"])


def main():
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--home", help=argparse.SUPPRESS)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("submit")
    p.add_argument("kind", choices=("preview", "frames", "final", "task"))
    p.add_argument("episode")
    p.add_argument("--approved", help="запись одобрения из чата; флаг сам по себе не является согласием пользователя")
    p.add_argument("--target", choices=("auto", "local", "remote"), default="auto")
    p.add_argument("--shots")
    p.add_argument("--frames", help="кадры превью; по умолчанию четыре на каждый шот")
    p.add_argument("--pct", type=int, default=50)
    p.add_argument("--samples", type=int)
    p.add_argument("--chunk", type=int, default=120)
    p.add_argument("--with-tts", action="store_true")
    p.add_argument("--priority", type=int)
    p.add_argument("--no-start", action="store_true", help="поставить без пробуждения worker")
    p.add_argument("--script", help="task: скрипт Blender внутри снимка")
    p.add_argument("--args", nargs=argparse.REMAINDER, default=[], help="task: аргументы скрипта после --; указывать последними")
    p = sub.add_parser("status")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("work")
    p.add_argument("--idle-exit", type=float, default=0, help=argparse.SUPPRESS)
    for cmd in ("start", "stop"):
        sub.add_parser(cmd)
    for cmd in ("pause", "resume", "cancel", "retry", "accept"):
        p = sub.add_parser(cmd)
        p.add_argument("job")
        if cmd == "retry":
            p.add_argument("--rerender-shots", help="вернуться к рендеру v1,v2 после удаления плохих кадров в снимке и на remote")
    a = ap.parse_args()
    if a.cmd == "submit" and (a.chunk < 1 or not 1 <= a.pct <= 100 or (a.samples is not None and a.samples < 1)):
        ap.error("chunk/samples > 0; pct в диапазоне 1…100")
    store = Store(Path(a.home) if a.home else queue_home(ROOT))
    if a.cmd == "work" and sys.stdout is None:
        sys.stdout = open(store.home / "worker.log", "a", encoding="utf-8", buffering=1)
        sys.stderr = sys.stdout
    try:
        if a.cmd == "submit":
            submit(store, a)
        elif a.cmd == "status":
            status(store, a.json)
        elif a.cmd == "work":
            work(store, a.idle_exit)
        elif a.cmd == "start":
            start_worker(store)
            print("Worker запускается; status — состояние, out/q/worker.log — ошибки")
        elif a.cmd == "stop":
            store.setting("stop", "1")
            print("Worker завершится после текущих порций; задания и кадры сохраняются")
        else:
            control_job(store, a.cmd, a.job, getattr(a, "rerender_shots", None))
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError, sqlite3.Error) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
