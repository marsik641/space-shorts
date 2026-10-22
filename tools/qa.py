"""QA готового ролика: кадры для просмотра + проверка параметров MP4 с вердиктом PASS / FAIL.

    python tools/qa.py episodes/<id>/episode.json <lang> [--light] [--video PATH] [--out DIR]
                       [--dry-run] [--from-log LOG] [--force]

Кадры QA (номера монтажа, с 1): 2; каждая склейка ±1 (c−1, c, c+1); середина каждого шота; середина
длинных (> 3 с) субтитров из edit_<fmt>_<lang>.json; последний.
Запускает Blender (это и есть команда, которую можно выполнить руками):
    "$BLENDER" -b --factory-startup -P editkit/verify_video.py -- <video.mp4> <out_dir> <f1,f2,...>
BLENDER — переменная окружения, по умолчанию D:/Blender/blender.exe. Лог — <out_dir>/verify.log,
PNG — <out_dir>/frame_NNNN.png (смотреть глазами: зоны интерфейса, субтитры, петля конец = начало).
Если есть out/RENDER.lock или запущен blender.exe — Blender не стартует (идёт рендер), только печать
команды; --force оставлен для совместимости и не обходит блокировку. --dry-run — только кадры и команда. --from-log — разобрать
готовый лог verify_video без запуска.
Проверки по строкам VIDEO/AUDIO: размер == format (1080x1920), fps == format.fps, кадры == длина
монтажа (Σ edit.frames − Σ xfade_in), видео ≤ 30.0 с, звук есть и ≤ 30.0 с (контейнер ≈ max(видео, звук)),
расхождение звук/видео > 0.1 с — WARN. Код выхода: 0 PASS, 1 FAIL, 2 не запускалось.
"""
import argparse
import json
import os
import re
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_edit import ep_paths, light_path, timeline_frames  # noqa: E402
from queue_runtime import Busy, inherited_resource, queue_home, resource  # noqa: E402

MAX_S = 30.0
RX_VIDEO = re.compile(r"VIDEO size \((\d+), (\d+)\) fps ([\d.]+) frames (\d+) seconds ([\d.]+)")
RX_AUDIO = re.compile(r"AUDIO seconds ([\d.]+)")


def R(path):
    return os.path.normpath(path if os.path.isabs(path) else os.path.join(REPO, path))


def qa_frames(edit, fps, caption_items=()):
    """Кадры монтажа для QA: 2, склейки ±1, середины шотов, середины длинных субтитров, последний."""
    total = timeline_frames(edit)
    fr, start = {2, total}, 1
    for i, s in enumerate(edit):
        if i:
            start -= s.get("xfade_in", 0)
            fr |= {start - 1, start, start + 1}
        fr.add(start + s["frames"] // 2)
        start += s["frames"]
    for it in caption_items:
        if it["end"] - it["start"] > 3 * fps:
            fr.add((it["start"] + it["end"]) // 2)
    return sorted(f for f in fr if 1 <= f <= total)


def verdict(log_text, fmt, total, need_audio=True):
    """-> (pass?, строки отчёта) по выводу verify_video.py."""
    lines, ok = [], True

    def chk(cond, msg):
        nonlocal ok
        ok &= bool(cond)
        lines.append(("OK   " if cond else "FAIL ") + msg)

    m = RX_VIDEO.search(log_text)
    if not m:
        return False, ["FAIL нет строки VIDEO в выводе verify_video"]
    w, h, fps, frames, sec = int(m[1]), int(m[2]), float(m[3]), int(m[4]), float(m[5])
    chk((w, h) == (fmt["w"], fmt["h"]), f"размер {w}x{h} (нужно {fmt['w']}x{fmt['h']})")
    chk(abs(fps - fmt["fps"]) < 0.01, f"fps {fps:g} (нужно {fmt['fps']})")
    chk(frames == total, f"кадров {frames} (нужно {total} = Σ edit)")
    chk(sec <= MAX_S, f"видео {sec:.3f} с (≤ {MAX_S})")
    a = RX_AUDIO.search(log_text)
    if a:
        asec = float(a[1])
        chk(asec <= MAX_S, f"звук {asec:.3f} с (≤ {MAX_S}); контейнер ≈ {max(sec, asec):.3f} с")
        if abs(asec - sec) > 0.1:
            lines.append(f"WARN звук и видео расходятся на {asec - sec:+.3f} с")
    elif need_audio:
        chk(False, "звуковой дорожки нет (AUDIO none)")
    return ok, lines


def main():
    for _s in (sys.stdout, sys.stderr):      # кириллица в консоли/пайпе Windows
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="QA MP4 эпизода: кадры + PASS/FAIL")
    ap.add_argument("episode")
    ap.add_argument("lang")
    ap.add_argument("--light", action="store_true", help="проверять _light-копию")
    ap.add_argument("--video", help="путь к MP4 (по умолчанию output из episode.json)")
    ap.add_argument("--out", help="папка для PNG и лога (по умолчанию out/<id>/<fmt>/qa_<lang>[_light])")
    ap.add_argument("--dry-run", action="store_true", help="только кадры и команда")
    ap.add_argument("--from-log", help="разобрать готовый вывод verify_video.py")
    ap.add_argument("--force", action="store_true", help="устарел; общую блокировку не обходит")
    a = ap.parse_args()

    with open(a.episode, encoding="utf-8") as fh:
        ep = json.load(fh)
    paths = ep_paths(ep, a.episode)
    fmt, fmt_name, eid = ep["format"], ep.get("format_name", "9x16"), ep["id"]
    total = timeline_frames(ep["edit"])
    video = a.video or paths["output"].format(id=eid, lang=a.lang)
    if a.light and not a.video:
        video = light_path(video)
    suffix = "_light" if a.light else ""
    out_dir = a.out or f"out/{eid}/{fmt_name}/qa_{a.lang}{suffix}"
    caps = []
    edit_json = os.path.join(os.path.dirname(a.episode), f"edit_{fmt_name}_{a.lang}.json")
    if os.path.isfile(edit_json):
        with open(edit_json, encoding="utf-8") as fh:
            caps = json.load(fh).get("captions", {}).get("items", [])
    frames = qa_frames(ep["edit"], fmt["fps"], caps)
    blender = os.environ.get("BLENDER", "D:/Blender/blender.exe")
    cmd = [blender, "-b", "--factory-startup", "-P", R("editkit/verify_video.py"), "--",
           R(video), R(out_dir), ",".join(map(str, frames))]
    print(f"QA {eid} {a.lang}{suffix}: {video}, ожидается {total} кадров ({total / fmt['fps']:.3f} с)")
    print("FRAMES", ",".join(map(str, frames)))
    print("CMD", subprocess.list2cmdline(cmd))
    if a.from_log:
        with open(a.from_log, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    else:
        if a.dry_run:
            return 0
        if not os.path.isfile(R(video)):
            print(f"FAIL нет файла {video}")
            return 1
        os.makedirs(R(out_dir), exist_ok=True)
        from contextlib import nullcontext
        gate = nullcontext() if inherited_resource() else resource(queue_home(REPO), f"qa {eid}")
        try:
            with gate:
                p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        except Busy as e:
            print(f"SKIP ресурс занят ({e}); поставь QA/финал через tools/render_queue.py")
            return 2
        text = p.stdout + p.stderr
        with open(os.path.join(R(out_dir), "verify.log"), "w", encoding="utf-8") as fh:
            fh.write(text)
    ok, lines = verdict(text, fmt, total)
    for ln in lines:
        print(ln)
    if not a.from_log:
        print(f"PNG: {out_dir}/frame_NNNN.png — проверить глазами")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
