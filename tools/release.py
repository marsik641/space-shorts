"""Сборка пакета к загрузке: out/<id>/release/ — MP4 по всем языкам (+ _light-копии) и publish_*.md.

    python tools/release.py episodes/<id>/episode.json [--dry-run]

MP4 берутся по output из episode.json (как в build_edit), light — с суффиксом _light (build_edit --light).
publish_<lang>.md — из папки эпизода. Нет основного MP4 или publish — FAIL (код 1); нет light — WARN.
Копирование с сохранением времени (shutil.copy2); существующие файлы в release/ перезаписываются.
Перед сборкой — tools/qa.py по каждому языку.
"""
import argparse
import json
import os
import shutil
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_edit import ep_paths, light_path  # noqa: E402


def R(path):
    return path if os.path.isabs(path) else os.path.join(REPO, path)


def main():
    for _s in (sys.stdout, sys.stderr):      # кириллица в консоли/пайпе Windows
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="out/<id>/release/: MP4 (+_light) и publish_*.md")
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
        for src, required in ((main_mp4, True), (light_path(main_mp4), False),
                              (os.path.join(ep_dir, f"publish_{lang}.md"), True)):
            if os.path.isfile(R(src)):
                plan.append(R(src))
            elif required:
                print(f"FAIL нет {src}")
                fails += 1
            else:
                print(f"WARN нет {src} (python tools/build_edit.py {a.episode} {lang} --light + assemble)")
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
