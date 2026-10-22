"""Проверка очереди без Blender/GPU/SSH: python -m unittest discover -s tests -v."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import render_queue as q
import queue_runtime as rt
import queue_remote as qr


class QueueTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "out").mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="qt_", dir=ROOT / "out")
        self.root = Path(self.tmp.name)
        self.store = q.Store(self.root / "out/q")
        self.no_blender = patch.object(rt, "blender_processes", return_value=False)
        self.no_blender.start()

    def tearDown(self):
        self.no_blender.stop()
        self.tmp.cleanup()

    def job(self, jid="aaaaaaaaaa", kind="preview", priority=0, target="local", steps=None):
        snap = self.store.home / jid
        snap.mkdir(exist_ok=True)
        (snap / "fake.py").write_text(
            "import pathlib,sys,time\n"
            "p=pathlib.Path(sys.argv[1]); p.parent.mkdir(parents=True,exist_ok=True)\n"
            "p.write_text('ok')\n"
            "time.sleep(float(sys.argv[2]) if len(sys.argv)>2 else 0)\n", encoding="utf-8")
        steps = steps or [q.step("fake", ["PYTHON", "fake.py", f"out/ep_test/{jid}.png"], "out/fake.log",
                                outputs=[f"out/ep_test/{jid}.png"])]
        with self.store.db() as db:
            db.execute("INSERT INTO jobs (id,kind,episode,source,created,priority,target,state,plan) "
                       "VALUES (?,?,?,?,?,?,?,'queued',?)", (jid, kind, "ep_test", str(self.root), time.time(), priority,
                                                            target, json.dumps(steps)))
        return self.store.get(jid)

    def test_atomic_claim_between_many_chats(self):
        self.job()
        with ThreadPoolExecutor(max_workers=12) as pool:
            claims = list(pool.map(lambda _: self.store.claim("local"), range(20)))
        self.assertEqual(sum(c is not None for c in claims), 1)

    def test_preview_has_priority_and_fifo(self):
        self.job("1111111111", priority=0)
        self.job("2222222222", priority=100)
        self.job("3333333333", priority=100)
        self.assertEqual(self.store.claim("local")[0]["id"], "2222222222")
        self.assertEqual(self.store.claim("local")[0]["id"], "3333333333")

    def test_remote_preference_and_machine_pinning(self):
        plan = [q.step("render", ["BLENDER"], "out/log", "render"), q.step("render2", ["BLENDER"], "out/log2", "render")]
        self.job(target="auto", steps=plan)
        self.assertIsNone(self.store.claim("local", remote_free=True))
        job, _ = self.store.claim("remote", remote_free=True)
        q.finish_step(self.store, job)
        self.assertIsNone(self.store.claim("local", remote_free=False))
        self.assertIsNotNone(self.store.claim("remote", remote_free=False))

    def test_coordinator_stays_awake_while_remote_works(self):
        self.job(target="remote", steps=[q.step("render", ["BLENDER"], "out/remote.log", "render")])
        remote = unittest.mock.Mock(cfg={"host": "test"}, ready=True, last_probe=time.time())
        with patch.object(q, "keep_awake") as awake:
            q.worker_loop(self.store, "remote", remote, idle_exit=0.1)
        self.assertEqual([c.args for c in awake.call_args_list], [(True,), (False,)])

    def test_resource_lock_across_processes(self):
        code = ("import sys;sys.path.insert(0,sys.argv[1]);from queue_runtime import file_lock,Busy\n"
                "try:\n with file_lock(sys.argv[2]): print('wrong')\n"
                "except Busy: print('busy')\n")
        with rt.file_lock(self.store.home / "gpu.lck"):
            r = subprocess.run([sys.executable, "-c", code, str(ROOT / "tools"), str(self.store.home / "gpu.lck")],
                               capture_output=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "busy")

    def test_existing_legacy_lock_never_removed(self):
        lock = self.store.home.parent / "RENDER.lock"
        lock.write_text("12345 legacy-render", encoding="utf-8")
        with self.assertRaises(rt.Busy):
            with rt.resource(self.store.home, "test"):
                self.fail("Ресурс захвачен поверх старого рендера")
        self.assertEqual(lock.read_text(), "12345 legacy-render")

    def test_inherited_resource_and_stale_recovery(self):
        with rt.resource(self.store.home, "test") as env, patch.dict(os.environ, env):
            self.assertTrue(rt.inherited_resource())
            with self.assertRaises(rt.Busy):
                with rt.resource(self.store.home, "other"):
                    pass
        self.assertFalse((self.store.home.parent / "RENDER.lock").exists())
        rt.write_json(self.store.home.parent / "RENDER.lock", dict(queue=True, pid=0, token="old"))
        with rt.resource(self.store.home, "new"):
            pass

    def test_foreign_blender_blocks_even_without_file(self):
        with patch.object(rt, "blender_processes", return_value=True), self.assertRaises(rt.Busy):
            with rt.resource(self.store.home, "test"):
                pass

    def test_orphan_sound_process_blocks_stale_lease_cleanup(self):
        lock = self.store.home.parent / "RENDER.lock"
        rt.write_json(lock, dict(queue=True, pid=0, child_pid=os.getpid(), token="orphan"))
        with self.assertRaises(rt.Busy):
            with rt.resource(self.store.home, "next"):
                pass
        self.assertTrue(lock.exists())

    def test_only_current_log_attempt_is_checked(self):
        job = self.job()
        snap = self.store.home / job["id"]
        (snap / "out").mkdir()
        (snap / "out/fake.log").write_text("Traceback (most recent call last)\nold failure\n")
        rt.execute(snap, json.loads(job["plan"])[0], sys.executable, self.store.home)

    def test_cancel_terminates_child_and_releases_resource(self):
        job = self.job(steps=[q.step("slow", ["PYTHON", "fake.py", "out/started", "20"], "out/slow.log")])
        snap = self.store.home / job["id"]
        with self.assertRaisesRegex(RuntimeError, "отменено"):
            rt.execute(snap, json.loads(job["plan"])[0], sys.executable, self.store.home,
                       lambda: (snap / "out/started").exists())
        self.assertFalse((self.store.home.parent / "RENDER.lock").exists())

    @unittest.skipUnless(os.name == "nt", "Проверка дерева taskkill на Windows")
    def test_cancel_kills_grandchild_too(self):
        job = self.job(steps=[q.step("tree", ["PYTHON", "tree.py"], "out/tree.log")])
        snap = self.store.home / job["id"]
        (snap / "tree.py").write_text(
            "import pathlib,subprocess,sys,time\n"
            "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'])\n"
            "pathlib.Path('grandchild.pid').write_text(str(p.pid))\n"
            "time.sleep(30)\n", encoding="utf-8")
        pidfile = snap / "grandchild.pid"
        with self.assertRaisesRegex(RuntimeError, "отменено"):
            rt.execute(snap, json.loads(job["plan"])[0], sys.executable, self.store.home, pidfile.exists)
        self.assertFalse(rt.alive(int(pidfile.read_text())))

    @unittest.skipUnless(os.name == "nt", "Гарантия KILL_ON_JOB_CLOSE на Windows")
    def test_worker_crash_kills_owned_descendants(self):
        job = self.job(steps=[q.step("orphan", ["PYTHON", "orphan.py"], "out/orphan.log")])
        snap = self.store.home / job["id"]
        (snap / "orphan.py").write_text(
            "import pathlib,os,time\npathlib.Path('child.pid').write_text(str(os.getpid()))\ntime.sleep(30)\n", encoding="utf-8")
        # patch из setUp в подпроцесс не проходит: глушим поиск blender.exe там же, иначе живой рендер даёт Busy
        code = ("import sys,json;sys.path.insert(0,sys.argv[1]);import queue_runtime as rt;"
                "rt.blender_processes=lambda:False;"
                "rt.execute(sys.argv[2],json.loads(sys.argv[3]),sys.executable,sys.argv[4])")
        proc = subprocess.Popen([sys.executable, "-c", code, str(ROOT / "tools"), str(snap),
                                 json.dumps(json.loads(job["plan"])[0]), str(self.store.home)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            until = time.monotonic() + 10
            while not (snap / "child.pid").exists() and proc.poll() is None and time.monotonic() < until:
                time.sleep(0.05)
            self.assertTrue((snap / "child.pid").exists())
            child = int((snap / "child.pid").read_text())
            proc.kill()
            proc.wait(timeout=5)
            until = time.monotonic() + 5
            while rt.alive(child) and time.monotonic() < until:
                time.sleep(0.05)
            self.assertFalse(rt.alive(child))
            with rt.resource(self.store.home, "recovered"):
                pass
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()

    def test_worker_finishes_without_chat_and_survives_failed_job(self):
        bad = [q.step("bad", ["PYTHON", "-c", "raise RuntimeError('test')"], "out/bad.log")]
        self.job("1111111111", priority=100, steps=bad)
        self.job("2222222222", kind="final")
        q.work(self.store, idle_exit=0.1)
        self.assertEqual(self.store.get("1111111111")["state"], "failed")
        self.assertEqual(self.store.get("2222222222")["state"], "needs_review")
        self.assertTrue((self.root / "out/ep_test/2222222222.png").exists())
        q.control_job(self.store, "accept", "2222222222")
        self.assertEqual(self.store.get("2222222222")["state"], "done")

    def test_recovery_preserves_completed_steps(self):
        steps = [q.step("must_not_run", ["PYTHON", "-c", "raise RuntimeError('replayed')"], "out/log1"),
                 q.step("finish", ["PYTHON", "fake.py", "out/ep_test/result"], "out/log2")]
        job = self.job(steps=steps)
        self.store.change(job["id"], cursor=1, state="running", active="local")
        q.work(self.store, idle_exit=0.1)
        self.assertEqual(self.store.get(job["id"])["state"], "done")

    def test_pause_waits_for_step_and_cancel_queued_is_immediate(self):
        job = self.job(steps=[q.step("a", ["PYTHON"], "out/a"), q.step("b", ["PYTHON"], "out/b")])
        claimed, _ = self.store.claim("local")
        q.control_job(self.store, "pause", job["id"])
        q.finish_step(self.store, claimed)
        self.assertEqual(self.store.get(job["id"])["state"], "paused")
        self.assertEqual(self.store.get(job["id"])["cursor"], 1)
        q.control_job(self.store, "cancel", job["id"])
        self.assertEqual(self.store.get(job["id"])["state"], "cancelled")

    def test_chunks_keep_first_frame_offsets_and_output_ranges(self):
        ep = dict(id="ep_test", edit=[dict(shot="v1", first=10, frames=250)])
        plan = q.plan_episode(ep, "episodes/ep_test/episode.json", "frames", chunk=120)
        renders = [s for s in plan if s["lane"] == "render"]
        self.assertEqual([s["argv"][-1] for s in renders], ["queue_range=10-129", "queue_range=130-249", "queue_range=250-259"])
        self.assertEqual(sum(len(s["outputs"]) for s in renders), 250)

    def test_retry_framecheck_can_return_to_render_chunks(self):
        ep = dict(id="ep_test", edit=[dict(shot="v1", frames=250), dict(shot="v2", frames=250)])
        plan = q.plan_episode(ep, "episodes/ep_test/episode.json", "frames", chunk=120)
        job = self.job(kind="frames", steps=plan)
        self.store.change(job["id"], state="failed", cursor=len(plan)-1, render_host="remote")
        remote = unittest.mock.Mock()
        with patch.object(q, "Remote", return_value=remote), patch.object(q, "start_worker"):
            q.control_job(self.store, "retry", job["id"], rerender_shots="v2")
        current = self.store.get(job["id"])
        self.assertEqual(current["cursor"], 4)
        self.assertEqual(current["state"], "queued")
        self.assertEqual(remote.rpc.call_count, 3)
        self.assertEqual(remote.rpc.call_args_list[0].args, ("reset", job["id"], "4"))

    def test_worktrees_resolve_same_queue(self):
        root = self.root / "gitrepo"
        root.mkdir()
        commands = [["git", "init", str(root)],
                    ["git", "-C", str(root), "-c", "user.name=Queue Test", "-c", "user.email=test@example.invalid",
                     "commit", "--allow-empty", "-m", "test"],
                    ["git", "-C", str(root), "worktree", "add", "--detach", str(self.root / "worktree")]]
        for cmd in commands:
            subprocess.run(cmd, check=True, capture_output=True)
        with patch.dict(os.environ):
            os.environ.pop("SPACEKIT_QUEUE_HOME", None)
            self.assertEqual(rt.queue_home(root), rt.queue_home(self.root / "worktree"))

    def test_plan_respects_preview_frames_and_no_final_without_full_episode(self):
        ep = dict(id="ep_test", edit=[dict(shot="v1", frames=240)])
        plan = q.plan_episode(ep, "episodes/ep_test/episode.json", "preview", frames="1,240", pct=25, samples=4)
        self.assertIn("pct=25", plan[1]["argv"])
        self.assertIn("samples=4", plan[1]["argv"])
        self.assertEqual(len(plan[1]["outputs"]), 2)
        with self.assertRaises(ValueError):
            q.plan_episode(ep, "episode.json", "final", shots="v1")
        with self.assertRaises(ValueError):
            q.plan_episode(dict(ep, shots_script="../escape.py"), "episode.json", "preview")

    def test_tar_traversal_and_links_rejected(self):
        for name, typ in (("../escape", tarfile.REGTYPE), ("link", tarfile.SYMTYPE)):
            data = io.BytesIO()
            with tarfile.open(fileobj=data, mode="w") as tf:
                info = tarfile.TarInfo(name)
                info.type = typ
                tf.addfile(info, io.BytesIO())
            data.seek(0)
            with tarfile.open(fileobj=data) as tf, self.assertRaises(ValueError):
                rt.extract_tar(tf, self.root / "target")

    def test_snapshot_freezes_code_and_duplicate_submission(self):
        source = self.root / "source"
        for folder in ("spacekit", "tools", "editkit", "episodes/ep_test"):
            (source / folder).mkdir(parents=True)
            (source / folder / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
        epfile = source / "episodes/ep_test/episode.json"
        epfile.write_text(json.dumps(dict(id="ep_test", languages=["en"], edit=[dict(shot="v1", frames=240)])))
        args = argparse.Namespace(episode=str(epfile), kind="preview", approved=None, shots=None, frames=None,
                                  pct=50, samples=None, chunk=120, with_tts=False, priority=None, target="local", no_start=True)
        jid = q.submit(self.store, args)
        self.assertEqual(q.submit(self.store, args), jid)
        self.assertEqual(len(self.store.jobs()), 1)
        (source / "spacekit/sample.py").write_text("VALUE = 2\n")
        self.assertEqual((self.store.home / jid / "spacekit/sample.py").read_text(), "VALUE = 1\n")
        args.frames = "1"
        self.assertNotEqual(q.submit(self.store, args), jid)

    def test_remote_execution_and_idempotent_reconnect(self):
        jid = "aaaaaaaaaa"
        job = self.job(jid, steps=[q.step("remote", ["BLENDER", "fake.py", "out/ep_test/remote.png"], "out/remote.log", "render",
                                        ["out/ep_test/remote.png"])])
        snap = self.store.home / jid
        rt.write_json(snap / "job.json", dict(plan=json.loads(job["plan"])))
        with patch.object(qr, "HOME", self.store.home), patch.object(rt, "find_blender", return_value=sys.executable):
            qr.run(jid, 0)
            self.assertEqual(qr.status(jid, 0)["state"], "done")
            self.assertEqual(qr.start(jid, 0)["state"], "done")
            (snap / "out/ep_test/remote.png").write_text("sentinel")
            qr.run(jid, 0)
            self.assertEqual((snap / "out/ep_test/remote.png").read_text(), "sentinel")


if __name__ == "__main__":
    unittest.main()
