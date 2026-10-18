"""Сборка пакета к загрузке: out/<id>/release/ — мастер MP4 и publish_<lang>.md по каждому языку, больше ничего.

    python tools/release.py episodes/<id>/episode.json [--dry-run]

MP4 — по output из episode.json (как в build_edit); publish_<lang>.md — из папки эпизода. Нет одного из них — FAIL
(код 1). _light/_preview в пакет не входят (решение владельца 18.10.2026: пакет = мастер + md).
Копирование с сохранением времени (shutil.copy2); файлы release/, которых нет в текущем составе, удаляются (DEL).
Перед сборкой — tools/qa.py по каждому языку.
"""
import argparse
import json
import os
import shutil
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_edit import ep_paths  # noqa: E402


def R(path):
    return path if os.path.isabs(path) else os.path.join(REPO, path)


def main():
    for _s in (sys.stdout, sys.stderr):      # кириллица в консоли/пайпе Windows
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="out/<id>/release/: мастер MP4 и publish_*.md")
    ap.add_argument("episode")
    ap.add_argument("--dry-run", action="store_true", help="только показать, что будет скопировано")
    a = ap.parse_args()

    with open(a.episode, encoding="utf-8") as fh:
        ep = json.load(fh)
    paths = ep_paths(ep, a.episode)
    eid = ep["id"]
    dest = R(f"out/{eid}/release")
    ep_dir = os.path.dirname(os.path.abspath(a.episode))
    plan, fails = [], 0
    for lang in ep.get("languages", ["en"]):
        main_mp4 = paths["output"].format(id=eid, lang=lang)
        for src in (main_mp4, os.path.join(ep_dir, f"publish_{lang}.md")):
            if os.path.isfile(R(src)):
                plan.append(R(src))
            else:
                print(f"FAIL нет {src}")
                fails += 1
    # чистый релиз: только файлы текущего состава (старые языки/версии не копятся)
    if not a.dry_run and os.path.isdir(dest):
        keep = {os.path.basename(p) for p in plan}
        for f in os.listdir(dest):
            if f not in keep:
                os.remove(os.path.join(dest, f))
                print(f"DEL  {f} (нет в текущем составе релиза)")
    if not a.dry_run:
        os.makedirs(dest, exist_ok=True)
    for src in plan:
        mb = os.path.getsize(src) / 1e6
        print(f"{'PLAN' if a.dry_run else 'COPY'} {os.path.basename(src)} ({mb:.1f} МБ)")
        if not a.dry_run:
            shutil.copy2(src, os.path.join(dest, os.path.basename(src)))
    print(f"{'FAIL' if fails else 'OK'} release {os.path.relpath(dest, REPO)}: {len(plan)} файлов, {fails} нет")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
