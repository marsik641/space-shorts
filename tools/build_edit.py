"""Монтажный лист для editkit/assemble.py из описания эпизода + субтитров озвучки.

    python tools/build_edit.py episodes/<id>/episode.json <lang> [--light]

Берёт: episode.json (порядок шотов, формат, оверлеи), <audio_dir>/captions_<lang>.json (секунды),
<audio_dir>/mix_<lang>.wav. Пишет episodes/<id>/edit_<fmt>_<lang>.json (кадры монтажа с 1).
Пути по умолчанию выводятся из id и format_name: frames_dir = out/<id>/<fmt>/frames,
audio_dir = out/<id>/<fmt>/audio, output = out/<id>/<fmt>/<id>_<lang>_<w>x<h>p<fps>.mp4. Явно заданные пути
должны содержать id, а id — совпадать с именем папки эпизода (иначе ошибка: защита от копии чужого эпизода).
Длина монтажа = Σ edit.frames − Σ xfade_in (наплывы укорачивают таймлайн, как в assemble.py).
Оверлей без length_s идёт от start_s до конца ролика; субтитры и оверлеи обрезаются по концу монтажа.
--light — копия для телефона: тот же монтаж, video {bitrate_kbps: 6000}, output с суффиксом _light,
лист edit_<fmt>_<lang>_light.json.
"""
import argparse
import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LIGHT_KBPS = 6000


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def ep_paths(ep, ep_path):
    """Пути эпизода с умолчаниями от id; проверка id == папка и что пути содержат id."""
    eid, fmt_name = ep["id"], ep.get("format_name", "9x16")
    folder = os.path.basename(os.path.dirname(os.path.abspath(ep_path)))
    if eid != folder:
        raise SystemExit(f"ERROR: id {eid!r} != папка эпизода {folder!r}")
    f = ep["format"]
    p = {
        "frames_dir": ep.get("frames_dir", f"out/{eid}/{fmt_name}/frames"),
        "audio_dir": ep.get("audio_dir", f"out/{eid}/{fmt_name}/audio"),
        "output": ep.get("output", f"out/{{id}}/{fmt_name}/{{id}}_{{lang}}_{f['w']}x{f['h']}p{f['fps']}.mp4"),
    }
    for k in ("script", "music_cues", "shots_script"):
        if k in ep:
            p[k] = ep[k]
    bad = [f"{k}={v}" for k, v in p.items() if eid not in v.format(id=eid, lang="xx")]
    if bad:
        raise SystemExit(f"ERROR: пути без id {eid!r}: " + ", ".join(bad))
    return p


def timeline_frames(edit, crossfade=0):
    """Длина монтажа в кадрах: Σ frames − Σ xfade_in (у первого шота наплыва нет)."""
    return sum(s["frames"] for s in edit) - sum(s.get("xfade_in", crossfade) for s in edit[1:])


def light_path(path):
    root, ext = os.path.splitext(path)
    return f"{root}_light{ext}"


def main(ep_path, lang, light=False):
    ep = load(ep_path)
    fmt = ep["format"]
    fps = fmt["fps"]
    paths = ep_paths(ep, ep_path)
    audio_dir = paths["audio_dir"]
    caps = load(os.path.join(REPO, audio_dir, f"captions_{lang}.json"))
    total = timeline_frames(ep["edit"])
    st = ep.get("caption_style", {})
    items = []
    for c in caps:
        a = max(1, int(round(c["start"] * fps)) + 1)
        b = min(total + 1, int(round(c["end"] * fps)) + 1)
        if b > a:
            items.append({"text": c["text"], "start": a, "end": b})
        else:
            print(f"WARN субтитр вне монтажа выброшен: {c['text']!r} ({c['start']}–{c['end']} с)")
    titles = []
    for o in ep.get("overlays", {}).get(lang, []):
        t = dict(o)
        t["start"] = max(1, int(round(o.get("start_s", 0) * fps)) + 1)
        room = total - t["start"] + 1
        t["length"] = int(round(o["length_s"] * fps)) if "length_s" in o else room
        if t["length"] > room:
            print(f"WARN оверлей {o['text']!r} обрезан по концу монтажа: {t['length']} -> {room} кадров")
            t["length"] = room
        t.pop("start_s", None)
        t.pop("length_s", None)
        if t["length"] > 0:
            titles.append(t)
    output = paths["output"].format(id=ep["id"], lang=lang)
    video = ep.get("video", {"bitrate_kbps": 40000})
    if light:
        output = light_path(output)
        video = dict(video, bitrate_kbps=LIGHT_KBPS)
        video.pop("crf", None)
    edit = {
        "output": output,
        "format": fmt,
        "video": video,
        "crossfade": 0, "fade_in": ep.get("fade_in", 0), "fade_out": ep.get("fade_out", 0), "tail": 0,
        "shots": [{"dir": f"{paths['frames_dir']}/{s['shot']}", "frames": s["frames"], "first": s.get("first", 1),
                   "xfade_in": s.get("xfade_in", 0)} for s in ep["edit"]],
        "titles": titles,
        "captions": dict(st, items=items),
        "audio": [{"path": f"{audio_dir}/mix_{lang}.wav", "start": 1, "volume": 1.0}],
    }
    name = f"edit_{ep['format_name']}_{lang}{'_light' if light else ''}.json"
    out = os.path.join(os.path.dirname(ep_path), name)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(edit, fh, ensure_ascii=False, indent=1)
    print(f"EDIT {out}: {total} кадров ({total / fps:.2f} с), {len(items)} субтитров, {len(titles)} оверлеев"
          + (f", light {LIGHT_KBPS} кбит/с" if light else ""))
    return out


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):      # кириллица в консоли/пайпе Windows
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="episode.json -> edit json для editkit/assemble.py")
    ap.add_argument("episode")
    ap.add_argument("lang")
    ap.add_argument("--light", action="store_true", help=f"копия {LIGHT_KBPS} кбит/с, суффикс _light")
    a = ap.parse_args()
    main(a.episode, a.lang, a.light)
