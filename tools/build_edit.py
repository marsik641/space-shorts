"""Монтажный лист для editkit/assemble.py из описания эпизода + субтитров озвучки.

    python tools/build_edit.py episodes/<id>/episode.json <lang>

Берёт: episode.json (порядок шотов, формат, оверлеи), <audio_dir>/captions_<lang>.json (секунды),
<audio_dir>/mix_<lang>.wav. Пишет episodes/<id>/edit_<fmt>_<lang>.json (кадры монтажа с 1).
"""
import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def main(ep_path, lang):
    ep = json.load(open(ep_path, encoding="utf-8"))
    fmt = ep["format"]
    fps = fmt["fps"]
    audio_dir = ep["audio_dir"]
    caps_path = os.path.join(REPO, audio_dir, f"captions_{lang}.json")
    caps = json.load(open(caps_path, encoding="utf-8"))
    total = sum(s["frames"] for s in ep["edit"])
    st = ep.get("caption_style", {})
    items = []
    for c in caps:
        a = int(round(c["start"] * fps)) + 1
        b = min(total + 1, int(round(c["end"] * fps)) + 1)
        if b > a:
            items.append({"text": c["text"], "start": a, "end": b})
    titles = []
    for o in ep.get("overlays", {}).get(lang, []):
        t = dict(o)
        t["start"] = int(round(o.get("start_s", 0) * fps)) + 1
        t["length"] = int(round(o.get("length_s", total / fps) * fps)) if "length_s" in o else total
        t.pop("start_s", None)
        t.pop("length_s", None)
        titles.append(t)
    edit = {
        "output": ep["output"].format(id=ep["id"], lang=lang),
        "format": fmt,
        "video": ep.get("video", {"bitrate_kbps": 40000}),
        "crossfade": 0, "fade_in": ep.get("fade_in", 0), "fade_out": ep.get("fade_out", 0), "tail": 0,
        "shots": [{"dir": f"{ep['frames_dir']}/{s['shot']}", "frames": s["frames"], "first": s.get("first", 1),
                   "xfade_in": s.get("xfade_in", 0)} for s in ep["edit"]],
        "titles": titles,
        "captions": dict(st, items=items),
        "audio": [{"path": f"{audio_dir}/mix_{lang}.wav", "start": 1, "volume": 1.0}],
    }
    out = os.path.join(os.path.dirname(ep_path), f"edit_{ep['format_name']}_{lang}.json")
    json.dump(edit, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"EDIT {out}: {total} кадров ({total / fps:.2f} с), {len(items)} субтитров, {len(titles)} оверлеев")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
