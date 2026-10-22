"""Очередь из worktree: веса TTS и .venv основной копии, hero-кадры отдельно от превью тайминга."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import render_queue as q  # noqa: E402


class QueueFromWorktree(unittest.TestCase):
    def setUp(self):
        (ROOT / "out").mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="qw_", dir=ROOT / "out")
        self.root = Path(self.tmp.name)
        self.main = self.root / "main"
        (self.main / "assets/tts").mkdir(parents=True)
        (self.main / "assets/tts/kokoro.onnx").write_bytes(b"w")
        (self.main / ".venv/Scripts").mkdir(parents=True)
        (self.main / ".venv/Scripts/python.exe").write_bytes(b"")
        self.wt = self.root / "wt"
        for folder in ("spacekit", "editkit", "tools", "episodes/ep_test"):
            (self.wt / folder).mkdir(parents=True)
        (self.wt / "episodes/ep_test/episode.json").write_text(json.dumps(dict(id="ep_test")), encoding="utf-8")
        self.patch = patch.object(q, "main_root", return_value=self.main)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_snapshot_takes_tts_from_main(self):
        dest = self.root / "snap"
        dest.mkdir()
        q.snapshot(self.wt, dest, "episodes/ep_test/episode.json")
        self.assertEqual((dest / "assets/tts/kokoro.onnx").read_bytes(), b"w")

    def test_python_from_main_venv(self):
        self.assertEqual(Path(q.python_for(dict(source=str(self.wt)))), self.main / ".venv/Scripts/python.exe")

    def test_hero_plan_separate_from_timing_preview(self):
        ep = dict(id="ep_test", edit=[dict(shot="v1", frames=240), dict(shot="v2", frames=240)])
        plan = q.plan_episode(ep, "episodes/ep_test/episode.json", "preview", frames="100,101,102", pct=100, hero=True)
        renders = [s for s in plan if s["lane"] == "render"]
        self.assertIn("outdir=out/ep_test/9x16/hero", renders[0]["argv"])
        self.assertEqual(renders[0]["outputs"][0], "out/ep_test/9x16/hero/v1_f0100.png")
        self.assertEqual(renders[0]["log"], "out/ep_test/9x16/logs/hero_v1.log")
        contact = plan[-1]
        self.assertEqual(contact["outputs"], ["out/ep_test/9x16/sheet_hero.png"])
        self.assertEqual([a for a in contact["argv"] if a.endswith(".png")][1:],
                         ["out/ep_test/9x16/hero/v1_f0100.png", "out/ep_test/9x16/hero/v2_f0100.png"])
        with self.assertRaises(ValueError):
            q.plan_episode(ep, "episodes/ep_test/episode.json", "final", hero=True)


if __name__ == "__main__":
    unittest.main()
