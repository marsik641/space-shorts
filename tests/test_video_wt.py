"""Жизненный цикл worktree ролика на временном репо: номера, ассеты, DoD finish, ff main, уборка."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "video_wt.py"
sys.path.insert(0, str(ROOT / "tools"))
import video_wt as vw  # noqa: E402


def sh(cwd, *cmd):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise AssertionError(f"{cmd}: {r.stdout}{r.stderr}")
    return r.stdout


class VideoWorktree(unittest.TestCase):
    def setUp(self):
        (ROOT / "out").mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="vw_", dir=ROOT / "out")
        self.main = Path(self.tmp.name) / "repo"
        self.env = dict(os.environ, SS_WT_ROOT=str(Path(self.tmp.name) / "wt"))
        m = self.main
        (m / "episodes/ep001_first").mkdir(parents=True)
        (m / "episodes/ep001_first/episode.json").write_text("{}", encoding="utf-8")
        (m / "tests").mkdir()
        (m / "tests/test_ok.py").write_text("import unittest\nclass T(unittest.TestCase):\n def test(self): pass\n")
        (m / "assets/tts").mkdir(parents=True)
        (m / "assets/sky.exr").write_bytes(b"sky")
        (m / "assets/tts/model.onnx").write_bytes(b"w")
        (m / ".gitignore").write_text("out/\nassets/sky.exr\nassets/tts/\n")
        sh(m, "git", "init", "-q", "-b", "main")
        sh(m, "git", "config", "user.email", "t@t")
        sh(m, "git", "config", "user.name", "t")
        sh(m, "git", "add", ".")
        sh(m, "git", "commit", "-qm", "init")

    def tearDown(self):
        subprocess.run(["git", "worktree", "prune"], cwd=self.main, capture_output=True)
        self.tmp.cleanup()

    def run_tool(self, cwd, *args, ok=True):
        r = subprocess.run([sys.executable, str(TOOL), *args], cwd=cwd, env=self.env, capture_output=True,
                           encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode == 0, ok, r.stdout + r.stderr)
        return r.stdout + r.stderr

    def wt(self, name):
        return Path(self.env["SS_WT_ROOT"]) / name

    def test_numbers_unique_under_race_and_never_reused(self):
        with ThreadPoolExecutor(max_workers=6) as pool:
            nums = list(pool.map(lambda _: vw.reserve(self.main), range(6)))
        self.assertEqual(sorted(nums), list(range(2, 8)))
        self.run_tool(self.main, "start")
        self.assertTrue(self.wt("ep008").is_dir())

    def test_start_copies_assets_but_not_tts(self):
        self.run_tool(self.main, "start")
        w = self.wt("ep002")
        self.assertEqual((w / "assets/sky.exr").read_bytes(), b"sky")
        self.assertFalse((w / "assets/tts").exists())
        self.run_tool(w, "start", ok=False)               # из worktree новый start не делается

    def test_finish_requires_clean_tree_release_then_merges(self):
        self.run_tool(self.main, "start")
        w = self.wt("ep002")
        self.run_tool(w, "claim", "Bad-Slug", ok=False)
        self.run_tool(w, "claim", "comet")
        (w / "episodes/ep002_comet").mkdir()
        (w / "episodes/ep002_comet/notes.md").write_text("x")
        self.assertIn("грязное", self.run_tool(w, "finish", ok=False))
        sh(w, "git", "add", ".")
        sh(w, "git", "commit", "-qm", "feat(ep002): заметки")
        self.assertIn("нет пакета", self.run_tool(w, "finish", ok=False))
        rel = w / "out/ep002_comet/release"
        rel.mkdir(parents=True)
        (rel / "ep002_comet_en.mp4").write_bytes(b"v")
        (rel / "publish_en.md").write_text("p")
        (self.main / "late.md").write_text("main сдвинулся")   # параллельный агент влил своё
        sh(self.main, "git", "add", "late.md")
        sh(self.main, "git", "commit", "-qm", "docs: параллельно")
        self.run_tool(w, "finish")
        self.assertTrue((self.main / "episodes/ep002_comet/notes.md").is_file())
        self.assertTrue((self.main / "out/ep002_comet/release/publish_en.md").is_file())
        self.run_tool(self.main, "remove", "ep002")
        self.assertFalse(w.exists())
        self.assertNotIn("video/ep002_comet", sh(self.main, "git", "branch"))
        self.run_tool(self.main, "start")
        self.assertTrue(self.wt("ep003").is_dir())       # номер 002 не вернулся

    def test_remove_keeps_unmerged_branch(self):
        self.run_tool(self.main, "start", "--task", "docs-fix")
        w = self.wt("task-docs-fix")
        (w / "a.md").write_text("a")
        sh(w, "git", "add", ".")
        sh(w, "git", "commit", "-qm", "docs: a")
        self.run_tool(self.main, "remove", "task-docs-fix", ok=False)
        self.run_tool(self.main, "remove", "task-docs-fix", "--abandon")
        self.assertIn("task/docs-fix", sh(self.main, "git", "branch"))


if __name__ == "__main__":
    unittest.main()
