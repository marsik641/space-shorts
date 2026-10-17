"""Монтаж: PNG-секвенции шотов + титры + субтитры + звук -> MP4 (H.264 + AAC) через VSE Blender.

    blender -b --factory-startup -P editkit/assemble.py -- <edit.json>

edit.json (пути — абсолютные или относительно корня репозитория; кадры монтажа нумеруются с 1):
{
  "output": "out/ep001_psr_b1257/9x16/ep001_en.mp4",
  "format": {"w": 1080, "h": 1920, "fps": 60},          # по умолчанию 1920×1080@30
  "video": {"bitrate_kbps": 50000} | {"crf": 15},      # высокий битрейт для загрузки на YouTube
  "crossfade": 0, "fade_in": 30, "fade_out": 45, "tail": 0,
  "shots": [{"dir": "out/.../frames/v1", "frames": 300, "first": 1, "xfade_in": 0}, ...],
  "titles": [{"text": "...", "start": 30, "length": 150, "size": 64, "x": 0.5, "y": 0.5, "fade": 20,
              "font": "C:/Windows/Fonts/segoeuisl.ttf", "align": "CENTER", "outline": 0, "color": [1,1,1],
              "shadow": true, "wrap": null}],
  "captions": {"items": [{"text": "...", "start": 61, "end": 120}], "size": 72, "x": 0.5, "y": 0.36,
               "font": "C:/Windows/Fonts/seguisb.ttf", "outline": 6, "wrap": 0.86, "color": [1,1,1],
               "shadow": true},
  "audio": [{"path": "out/.../vo_en.wav", "start": 1, "volume": 1.0, "fade_in": 0, "fade_out": 0}]
}
shots[].first — номер первого кадра секвенции (число в имени файла: 0001.png = 1; обрезка начала).
  Берутся строго кадры first..first+frames-1: нет файла или файл 0 байт (плейсхолдер Blender после
  аварийного рендера) — ошибка со списком кадров. xfade_in — наплыв В этот шот (0 — встык); каждый наплыв
  укорачивает таймлайн на xfade_in кадров.
tail — кадры чёрного после затемнения. captions — субтитры фразами (обычно из tools/tts.py).
Титры/субтитры: x, y — доли кадра, y отсчитывается от НИЗА (0.955 — у верхнего края, 0.30 — 30% от низа).
  outline — толщина обводки: 0..1 — доля (как outline_width в Blender), значения > 1 — проценты (8 -> 0.08).
  fade (титры) и fade_in/fade_out (видео, звук) ограничиваются половиной длины клипа.
  Нет файла шрифта — WARN и шрифт Blender по умолчанию. Лишние ключи (max_chars и т.п.) игнорируются.
fps: целый (24/25/30/50/60) или NTSC-дробный (23.976, 29.97, 59.94 -> fps=N, fps_base=1.001); иное — ошибка.
"""
import json
import os
import re
import sys

import bpy

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def P(path):
    return path if os.path.isabs(path) else os.path.join(REPO, path)


def fps_pair(fps):
    """fps из edit.json -> (render.fps, render.fps_base). Дробные — только NTSC (N*1000/1001)."""
    fps = float(fps)
    if abs(fps - round(fps)) < 1e-6:
        return int(round(fps)), 1.0
    n = round(fps * 1.001)
    if abs(n / 1.001 - fps) < 0.01:
        return n, 1.001
    raise ValueError(f"fps {fps}: поддерживаются целые и NTSC-дробные (29.97, 59.94)")


def shot_files(d, first, frames):
    """Имена кадров first..first+frames-1 по номеру в имени файла; пропуски и 0-байтные файлы — ошибка."""
    by_num = {}
    for f in os.listdir(d):
        m = re.match(r"^(.*?)(\d+)\.png$", f, re.IGNORECASE)
        if m:
            by_num.setdefault(int(m.group(2)), f)
    need = range(first, first + frames)
    missing = [n for n in need if n not in by_num]
    empty = [n for n in need if n in by_num and os.path.getsize(os.path.join(d, by_num[n])) == 0]
    if missing or empty:
        raise RuntimeError(f"{d}: кадры {first}..{first + frames - 1}: нет {len(missing)} {missing[:10]}, "
                           f"0 байт {len(empty)} {empty[:10]} — 0-байтные удалить и дорендерить")
    return [by_num[n] for n in need]


def key_prop(strip, prop, pairs):
    for f, v in pairs:
        setattr(strip, prop, v)
        strip.keyframe_insert(prop, frame=f)


def text_strip(sed, name, channel, start, length, text, size, x, y, font=None, align="CENTER",
               color=(0.92, 0.94, 1.0), outline=0, shadow=True, wrap=None):
    ts = sed.strips.new_effect(name, "TEXT", channel=channel, frame_start=start, length=length)
    ts.text = text
    ts.font_size = size
    ts.location = (x, y)
    ts.alignment_x = align
    ts.anchor_x = align
    ts.anchor_y = "CENTER"
    ts.color = (*color, 1.0)
    if wrap:
        ts.wrap_width = wrap
    if outline:
        ts.use_outline = True
        ts.outline_color = (0, 0, 0, 1)
        ts.outline_width = outline / 100.0 if outline > 1 else outline   # 0..1 — доля, > 1 — проценты
    ts.use_shadow = shadow
    if shadow:
        ts.shadow_color = (0, 0, 0, 0.6)
        ts.shadow_blur = 0.6
    if font:
        if os.path.exists(font):
            ts.font = bpy.data.fonts.load(font, check_existing=True)
        else:
            print(f"WARN: шрифт не найден: {font} ({name}) — шрифт Blender по умолчанию")
    ts.blend_type = "ALPHA_OVER"
    return ts


def main(cfg):
    fmt = cfg.get("format", {"w": 1920, "h": 1080, "fps": 30})
    fps_i, fps_base = fps_pair(fmt["fps"])
    fps = fps_i / fps_base
    sc = bpy.context.scene
    sc.render.fps, sc.render.fps_base = fps_i, fps_base
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = fmt["w"], fmt["h"], 100
    # PNG уже прошли AgX при рендере — здесь только Standard, без повторного тонмаппинга
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = 0.0
    sc.render.dither_intensity = 1.0
    sed = sc.sequence_editor_create()

    xf_def = cfg.get("crossfade", 0)
    strips, xfs = [], []
    for i, shot in enumerate(cfg["shots"]):
        xf = 0 if i == 0 else shot.get("xfade_in", xf_def)
        cursor = 1 if i == 0 else strips[-1].frame_final_end - xf
        d = P(shot["dir"])
        files = shot_files(d, shot.get("first", 1), shot["frames"])
        st = sed.strips.new_image(f"shot{i + 1}", os.path.join(d, files[0]),
                                  channel=1 + (i % 2), frame_start=cursor, fit_method="FIT")
        for f in files[1:]:
            st.elements.append(f)
        st.blend_type = "REPLACE"
        strips.append(st)
        xfs.append(xf)
    end = strips[-1].frame_final_end - 1

    for i in range(1, len(strips)):
        if xfs[i] > 0:
            a, b = strips[i - 1], strips[i]
            sed.strips.new_effect(f"x{i}", "CROSS", channel=3, frame_start=b.frame_final_start, length=xfs[i],
                                  input1=a, input2=b)

    fi, fo = cfg.get("fade_in", 0), cfg.get("fade_out", 0)
    fi = min(fi, strips[0].frame_final_duration // 2)
    fo = min(fo, strips[-1].frame_final_duration // 2)
    if fi:
        key_prop(strips[0], "color_multiply", [(1, 0.0), (1 + fi, 1.0)])
    if fo:
        key_prop(strips[-1], "color_multiply", [(end - fo, 1.0), (end, 0.0)])
    end += cfg.get("tail", 0)

    ch = 5
    for j, t in enumerate(cfg.get("titles", [])):
        ts = text_strip(sed, f"title{j}", ch, t["start"], t["length"], t["text"], t.get("size", 56),
                        t.get("x", 0.5), t.get("y", 0.5), t.get("font"), t.get("align", "CENTER"),
                        tuple(t.get("color", (0.92, 0.94, 1.0))), t.get("outline", 0), t.get("shadow", True),
                        t.get("wrap"))
        fd = min(t.get("fade", 20), t["length"] // 2)    # иначе ключи альфы идут не по порядку
        s0, s1 = t["start"], t["start"] + t["length"] - 1
        if fd:
            key_prop(ts, "blend_alpha", [(s0, 0.0), (s0 + fd, 1.0), (s1 - fd, 1.0), (s1, 0.0)])
        ch += 1

    cap = cfg.get("captions")
    if cap:
        # чередование двух каналов — соседние фразы могут касаться друг друга
        for j, it in enumerate(cap["items"]):
            length = max(1, it["end"] - it["start"])
            ts = text_strip(sed, f"cap{j}", ch + (j % 2), it["start"], length, it["text"], cap.get("size", 72),
                            cap.get("x", 0.5), cap.get("y", 0.36), cap.get("font"), "CENTER",
                            tuple(it.get("color", cap.get("color", (1.0, 1.0, 1.0)))), cap.get("outline", 6),
                            cap.get("shadow", True), cap.get("wrap", 0.86))
        ch += 2

    for j, a in enumerate(cfg.get("audio", [])):
        s = sed.strips.new_sound(f"audio{j}", P(a["path"]), channel=ch + j, frame_start=a.get("start", 1))
        vol = a.get("volume", 1.0)
        s.volume = vol
        s0, s1 = s.frame_final_start, min(s.frame_final_end - 1, end)
        if s.frame_final_end - 1 > end:
            s.frame_final_end = end + 1
        pairs, half = [], max(0, (s1 - s0) // 2)
        if a.get("fade_in"):
            pairs += [(s0, 0.0), (s0 + min(a["fade_in"], half), vol)]
        if a.get("fade_out"):
            pairs += [(s1 - min(a["fade_out"], half), vol), (s1, 0.0)]
        if pairs:
            key_prop(s, "volume", pairs)

    sc.frame_start, sc.frame_end = 1, end
    r = sc.render
    r.use_sequencer = True
    r.use_compositing = False
    ims = r.image_settings
    ims.media_type = "VIDEO"
    ims.file_format = "FFMPEG"
    ims.color_mode = "RGB"
    ff = r.ffmpeg
    ff.format = "MPEG4"
    ff.codec = "H264"
    v = cfg.get("video", {"crf": cfg.get("crf", 15)})
    if "bitrate_kbps" in v:
        br = int(v["bitrate_kbps"])
        ff.constant_rate_factor = "NONE"
        ff.video_bitrate = br
        ff.minrate = int(br * 0.5)
        ff.maxrate = int(br * 1.5)
        ff.buffersize = min(int(br * 2), 2000)    # предел свойства в Blender 5.2 — 0..2000
    else:
        ff.constant_rate_factor = "CUSTOM"
        ff.custom_constant_rate_factor = int(v.get("crf", 15))
    ff.ffmpeg_preset = v.get("preset", "BEST")
    ff.gopsize = int(v.get("gop", fps_i // 2))     # GOP ≤ половины частоты кадров (рекомендация YouTube)
    ff.use_max_b_frames = True
    ff.max_b_frames = 2
    if cfg.get("audio"):
        ff.audio_codec = "AAC"
        ff.audio_bitrate = 320
        ff.audio_mixrate = 48000
        ff.audio_channels = "STEREO"
    else:
        ff.audio_codec = "NONE"
    out = P(cfg["output"])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    r.filepath = out
    bpy.ops.render.render(animation=True)
    print("ASSEMBLED", out, "frames", end, "seconds", round(end / fps, 2))


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    with open(argv[0], encoding="utf-8") as fh:
        main(json.load(fh))
