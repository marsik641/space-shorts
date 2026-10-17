"""Проверка готового MP4: размер, fps, длительность видео и звука + выгрузка указанных кадров в PNG.

    blender -b --factory-startup -P editkit/verify_video.py -- <video.mp4> <out_dir> [<frame> ...]

Кадры — через пробел или запятую (2 269,270,271 3600); без кадров — только строки VIDEO/AUDIO.
Печатает (разбирает tools/qa.py — формат строк не менять):
    VIDEO size (1080, 1920) fps 60.0 frames 3600 seconds 60.0 bytes 312345678
    AUDIO seconds 60.021 rate 48000 channels 2      | AUDIO none
    EXTRACTED <n>
Длительность звука — по потоку через aud.Sound (длина в сэмплах / частота), запасной путь — звуковой
стрип VSE (точность до кадра). Длительность контейнера Blender не отдаёт: считать её max(видео, звук).
Вердикта нет — PASS/FAIL ставит tools/qa.py.
"""
import os
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
path, out_dir = argv[0], argv[1]
frames = [int(f) for a in argv[2:] for f in a.split(",") if f.strip()]
os.makedirs(out_dir, exist_ok=True)

clip = bpy.data.movieclips.load(path)
fps = clip.fps
print("VIDEO size", tuple(clip.size), "fps", fps, "frames", clip.frame_duration,
      "seconds", round(clip.frame_duration / max(fps, 1), 3), "bytes", os.path.getsize(path))


def audio_info():
    """(секунды, частота, каналы) звуковой дорожки или None."""
    try:
        import aud
        snd = aud.Sound(path)
        rate, ch = snd.specs
        if snd.length > 0 and rate > 0:
            return snd.length / rate, int(rate), int(ch)
    except Exception as e:          # нет дорожки или aud не открыл контейнер — пробуем через VSE
        print("WARN aud:", e)
    try:
        sc = bpy.context.scene
        sc.render.fps, sc.render.fps_base = round(fps), 1.0
        sed = sc.sequence_editor_create()
        s = sed.strips.new_sound("a_probe", path, channel=9, frame_start=1)
        sec = s.frame_final_duration / max(fps, 1)
        sed.strips.remove(s)
        return (sec, 0, 0) if sec > 0 else None
    except Exception as e:
        print("WARN vse sound:", e)
        return None


a = audio_info()
if a:
    print("AUDIO seconds", round(a[0], 3), "rate", a[1], "channels", a[2])
else:
    print("AUDIO none")

sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y = clip.size
sc.render.resolution_percentage = 100
sc.view_settings.view_transform = "Standard"
sed = sc.sequence_editor_create()
st = sed.strips.new_movie("v", path, channel=1, frame_start=1)
sc.frame_start, sc.frame_end = 1, st.frame_final_end - 1
sc.render.use_sequencer = True
sc.render.image_settings.media_type = "IMAGE"
sc.render.image_settings.file_format = "PNG"
n = 0
for f in frames:
    if not 1 <= f <= sc.frame_end:
        print(f"WARN кадр {f} вне 1..{sc.frame_end} — пропущен")
        continue
    sc.frame_set(f)
    sc.render.filepath = os.path.join(out_dir, f"frame_{f:04d}.png")
    bpy.ops.render.render(write_still=True)
    n += 1
print("EXTRACTED", n)
