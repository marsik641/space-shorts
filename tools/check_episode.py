"""Проверка согласованности эпизода (stdlib, без Blender): запускать перед превью и перед финалом.

    python tools/check_episode.py episodes/<id>/episode.json

Проверяет:
  • id == имени папки, явные пути episode.json содержат id, файлы script / music_cues / shots_script есть;
  • длина монтажа (Σ edit.frames − Σ xfade_in) / fps ≤ 60.0 с (> 59.5 — WARN: запас на AAC) и равна
    script.duration_s и music_cues.duration_s;
  • edit против SHOTS в shots_<fmt>.py (разбор ast, без импорта): шот есть, first+frames−1 ≤ SHOTS;
  • сегменты сценария: at возрастает, лежит внутри своего шота, есть текст на всех languages и голос;
  • аккорды: время возрастает и < длительности, имя парсится tools/music.parse_chord (если music.py
    импортируется — нужен numpy, т.е. .venv; иначе только синтаксис), pulses/risers внутри ролика;
  • шрифты caption_style и overlays существуют, оверлеи есть для каждого языка.
Печатает OK / WARN / FAIL по пунктам и итог PASS / FAIL (код выхода 0 / 1).
"""
import ast
import json
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_edit import timeline_frames  # noqa: E402  (stdlib-only модуль)

MAX_S, SAFE_S = 60.0, 59.5
CHORD_RX = re.compile(r"^[A-G][#b]?[A-Za-z0-9#+]*$")


class Report:
    def __init__(self):
        self.fails = self.warns = 0

    def ok(self, msg):
        print("OK  ", msg)

    def warn(self, msg):
        self.warns += 1
        print("WARN", msg)

    def fail(self, msg):
        self.fails += 1
        print("FAIL", msg)

    def check(self, cond, ok_msg, fail_msg):
        (self.ok(ok_msg) if cond else self.fail(fail_msg))
        return cond


def R(path):
    return path if os.path.isabs(path) else os.path.join(REPO, path)


def load_json(rep, path, what):
    try:
        with open(R(path), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as e:
        rep.fail(f"{what}: {path}: {e}")
        return None


def shots_from_ast(path):
    """SHOTS = {...} из скрипта шотов без импорта (там bpy)."""
    with open(R(path), encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "SHOTS" for t in node.targets):
            return ast.literal_eval(node.value)
    return None


def chord_parser():
    try:
        import music
        return music.parse_chord
    except Exception as e:       # нет numpy/soundfile вне .venv
        print(f"NOTE tools/music.py не импортируется ({type(e).__name__}: {e}) — аккорды только по синтаксису")
        return None


def main(ep_path):
    for _s in (sys.stdout, sys.stderr):      # кириллица в консоли/пайпе Windows
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    rep = Report()
    ep = load_json(rep, ep_path, "episode.json")
    if ep is None:
        print("FAIL")
        return 1
    eid, fmt_name = ep.get("id", "?"), ep.get("format_name", "9x16")
    folder = os.path.basename(os.path.dirname(os.path.abspath(ep_path)))
    rep.check(eid == folder, f"id {eid} == папка", f"id {eid!r} != папка {folder!r}")

    # пути
    paths = {k: ep[k] for k in ("frames_dir", "audio_dir", "script", "music_cues", "shots_script", "output")
             if k in ep}
    bad = [f"{k}={v}" for k, v in paths.items() if eid not in v.format(id=eid, lang="xx")]
    rep.check(not bad, "явные пути содержат id", "пути без id: " + ", ".join(bad))
    script_p = ep.get("script", f"episodes/{eid}/script_{fmt_name}.json")
    cues_p = ep.get("music_cues", f"episodes/{eid}/music_cues.json")
    shots_p = ep.get("shots_script", f"episodes/{eid}/shots_{fmt_name}.py")

    # формат и длительность
    fmt = ep.get("format", {})
    fps = fmt.get("fps", 0)
    rep.check(isinstance(fps, int) and fps > 0, f"fps {fps}", f"fps {fps!r}: нужен целый > 0")
    if fmt_name == "9x16" and (fmt.get("w"), fmt.get("h")) != (1080, 1920):
        rep.warn(f"формат 9x16, но {fmt.get('w')}x{fmt.get('h')} (ожидалось 1080x1920)")
    edit = ep.get("edit", [])
    if not edit or any(not isinstance(s.get("frames"), int) or s["frames"] <= 0 for s in edit):
        rep.fail("edit пуст или frames не целые > 0")
        print("FAIL")
        return 1
    fps = fps or 60
    total = timeline_frames(edit)
    dur = total / fps
    if dur > MAX_S + 1e-9:
        rep.fail(f"монтаж {total} кадров = {dur:.3f} с > {MAX_S}")
    elif dur > SAFE_S:
        rep.warn(f"монтаж {total} кадров = {dur:.3f} с: ≤ {MAX_S}, но > {SAFE_S} (запас на AAC priming)")
    else:
        rep.ok(f"монтаж {total} кадров = {dur:.3f} с")
    starts, t = {}, 0
    for i, s in enumerate(edit):
        if i:
            t -= s.get("xfade_in", 0)
        starts[s["shot"]] = (t / fps, (t + s["frames"]) / fps)
        t += s["frames"]
    if len(starts) != len(edit):
        rep.warn("шот повторяется в edit — проверка сегментов по последнему вхождению")

    # SHOTS
    if os.path.isfile(R(shots_p)):
        try:
            shots = shots_from_ast(shots_p)
            if shots is None:
                rep.warn(f"в {shots_p} нет литерала SHOTS = {{...}}")
        except (SyntaxError, ValueError) as e:
            shots = None
            rep.warn(f"SHOTS в {shots_p} не разобрать: {e}")
        if shots is not None:
            for s in edit:
                n, last = shots.get(s["shot"]), s.get("first", 1) + s["frames"] - 1
                if n is None:
                    rep.fail(f"edit {s['shot']}: нет в SHOTS ({shots_p})")
                elif last > n:
                    rep.fail(f"edit {s['shot']}: кадры до {last}, а в SHOTS {n}")
                elif last < n or s.get("first", 1) > 1:
                    rep.warn(f"edit {s['shot']}: берётся {s.get('first', 1)}..{last} из {n} (обрезка)")
            extra = sorted(set(shots) - {s["shot"] for s in edit})
            if extra:
                rep.warn(f"SHOTS без места в edit: {extra}")
            rep.ok(f"SHOTS сверены: {shots}")
    else:
        rep.fail(f"нет скрипта шотов {shots_p}")

    # сценарий
    langs = ep.get("languages", ["en"])
    sc = load_json(rep, script_p, "script") if os.path.isfile(R(script_p)) else None
    if sc is None and not os.path.isfile(R(script_p)):
        rep.fail(f"нет сценария {script_p}")
    if sc:
        sd = sc.get("duration_s")
        rep.check(sd is not None and abs(sd - dur) < 0.5 / fps, f"script.duration_s {sd} == монтаж",
                  f"script.duration_s {sd} != монтаж {dur:.3f} с")
        for lang in langs:
            if lang not in sc.get("voices", {}):
                rep.fail(f"script.voices: нет голоса {lang}")
        prev, n_bad = -1.0, 0
        for k, seg in enumerate(sc.get("segments", [])):
            at, shot, tag = seg.get("at"), seg.get("shot"), f"сегмент {k + 1}"
            if not isinstance(at, (int, float)):
                rep.fail(f"{tag}: нет at")
                n_bad += 1
                continue
            if at <= prev:
                rep.fail(f"{tag}: at {at} не возрастает (предыдущий {prev})")
                n_bad += 1
            prev = at
            if not 0 <= at < dur:
                rep.fail(f"{tag}: at {at} вне 0..{dur:.2f}")
                n_bad += 1
            if shot not in starts:
                rep.fail(f"{tag}: шот {shot!r} не в edit")
                n_bad += 1
            elif not starts[shot][0] <= at < starts[shot][1]:
                a, b = starts[shot]
                rep.fail(f"{tag}: at {at} вне своего шота {shot} [{a:.2f}, {b:.2f})")
                n_bad += 1
            for lang in langs:
                if not str(seg.get(lang, "")).strip():
                    rep.fail(f"{tag}: нет текста {lang}")
                    n_bad += 1
        if not n_bad:
            rep.ok(f"сегменты: {len(sc.get('segments', []))}, языки {langs}")
    # музыка
    cues = load_json(rep, cues_p, "music_cues") if os.path.isfile(R(cues_p)) else None
    if cues is None and not os.path.isfile(R(cues_p)):
        rep.fail(f"нет {cues_p}")
    if cues:
        cd = cues.get("duration_s")
        rep.check(cd is not None and abs(cd - dur) < 0.5 / fps, f"music_cues.duration_s {cd} == монтаж",
                  f"music_cues.duration_s {cd} != монтаж {dur:.3f} с")
        parse = chord_parser()
        names = [c[1] for c in cues.get("chords", [])]
        times = [c[0] for c in cues.get("chords", [])]
        n_bad = 0
        if times and (times != sorted(times) or len(set(times)) != len(times) or times[-1] >= dur):
            rep.fail(f"chords: время не возрастает или ≥ длительности: {times}")
            n_bad += 1
        if times and times[0] != 0:
            rep.warn(f"chords: первый аккорд с {times[0]} с, а не с 0")
        key = cues.get("key", "A")
        for nm in names + [key]:
            if not CHORD_RX.match(str(nm)):
                rep.fail(f"аккорд {nm!r}: не похоже на имя аккорда")
                n_bad += 1
            elif parse:
                try:
                    parse(nm)
                except Exception as e:
                    rep.fail(f"аккорд {nm!r}: parse_chord: {type(e).__name__}: {e}")
                    n_bad += 1
        for k in ("pulses", "risers"):
            out = [x for x in cues.get(k, []) if not 0 <= x <= dur]
            if out:
                rep.fail(f"{k} вне ролика: {out}")
                n_bad += 1
        if not n_bad:
            rep.ok(f"music_cues: {len(names)} аккордов, {len(cues.get('pulses', []))} pulses, "
                   f"{len(cues.get('risers', []))} risers")

    # шрифты и оверлеи
    fonts = [("caption_style", ep.get("caption_style", {}).get("font"))]
    ov = ep.get("overlays", {})
    for lang in langs:
        if lang not in ov:
            rep.warn(f"overlays: нет языка {lang}")
        fonts += [(f"overlays.{lang}[{i}]", o.get("font")) for i, o in enumerate(ov.get(lang, []))]
    missing = [f"{w}: {f}" for w, f in fonts if f and not os.path.isfile(f)]
    rep.check(not missing, f"шрифты: {len({f for _, f in fonts if f})} файлов на месте",
              "нет шрифтов: " + "; ".join(missing))

    verdict = "PASS" if not rep.fails else "FAIL"
    print(f"{verdict} {eid}: {rep.fails} FAIL, {rep.warns} WARN")
    return 0 if not rep.fails else 1


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):      # кириллица/Σ в консоли cp1251 и пайпе Git Bash
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
