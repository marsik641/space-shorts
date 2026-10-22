"""Харнесс агентов не расходится: одни правила для Claude и Codex, одинаковые скиллы, живые ссылки."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOCS = [ROOT / "AGENTS.md", ROOT / "CLAUDE.md", *ROOT.glob(".claude/skills/*/SKILL.md"), ROOT / "docs/workflows.md",
        ROOT / "docs/pipeline.md", ROOT / "docs/approval.md", ROOT / "docs/quality.md"]


def text(p):
    return p.read_text(encoding="utf-8").replace("\r\n", "\n")


class Harness(unittest.TestCase):
    def test_claude_reads_agents(self):
        self.assertEqual(text(ROOT / "CLAUDE.md").splitlines()[0], "@AGENTS.md")

    def test_skill_copies_identical(self):
        claude = {p.parent.name for p in ROOT.glob(".claude/skills/*/SKILL.md")}
        codex = {p.parent.name for p in ROOT.glob(".agents/skills/*/SKILL.md")}
        self.assertEqual(claude, codex)
        for name in claude:
            self.assertEqual(text(ROOT / f".claude/skills/{name}/SKILL.md"), text(ROOT / f".agents/skills/{name}/SKILL.md"),
                             f"{name}: правь .claude/skills и копируй в .agents/skills")

    def test_referenced_paths_exist(self):
        for doc in DOCS:
            for rel in re.findall(r"`((?:docs|tools|tests|episodes/_template|ideas)/[\w./-]+\.(?:md|py|json))`", text(doc)):
                self.assertTrue((ROOT / rel).exists(), f"{doc.relative_to(ROOT)}: нет {rel}")

    def test_no_stale_paths(self):
        for doc in DOCS:
            t = text(doc)
            for bad in (".Codex/", ".claude/workflows.md", "cygpath"):
                self.assertFalse(bad in t, f"{doc.relative_to(ROOT)}: устаревшее {bad}")


if __name__ == "__main__":
    unittest.main()
