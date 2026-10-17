"""Проверка готового MP4: размер, fps, длительность + выгрузка указанных кадров в PNG.

    blender -b --factory-startup -P verify_video.py -- <video.mp4> <out_dir> <frame> [<frame> ...]
"""
import os
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
path, out_dir, frames = argv[0], argv[1], [int(f) for f in argv[2:]]
os.makedirs(out_dir, exist_ok=True)

clip = bpy.data.movieclips.load(path)
print("VIDEO size", tuple(clip.size), "fps", clip.fps, "frames", clip.frame_duration,
      "seconds", round(clip.frame_duration / max(clip.fps, 1), 2), "bytes", os.path.getsize(path))

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
for f in frames:
    sc.frame_set(f)
    sc.render.filepath = os.path.join(out_dir, f"frame_{f:04d}.png")
    bpy.ops.render.render(write_still=True)
print("EXTRACTED", len(frames))
