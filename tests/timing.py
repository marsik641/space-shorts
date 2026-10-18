"""Замер времени кадра в вариантах настроек (оптимизация рендера).

    blender -b --factory-startup -P tests/timing.py -- <episode_shots.py> <shot> <frame> <variant> [<variant> ...]
variant: base | compgpu | lowspp | fast (= compgpu + lowspp) | coarsevol (шаг объёма ×4) | fast2 (32 spp + coarsevol) | fast3 (20 spp)
"""
import importlib.util
import os
import sys
import time

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
script, shot, frame, variants = argv[0], argv[1], int(argv[2]), argv[3:]
spec = importlib.util.spec_from_file_location("ep", script)
ep = importlib.util.module_from_spec(spec)
sys.argv = [sys.argv[0]]
spec.loader.exec_module(ep)

from spacekit import core as C  # noqa: E402
from spacekit import render as R  # noqa: E402

for v in variants:
    sc, n = ep.BUILDERS[shot]()
    if v in ("compgpu", "fast"):
        sc.render.compositor_device = "GPU"
    if v in ("lowspp", "fast"):
        sc.cycles.samples = 40
        sc.cycles.adaptive_threshold = 0.03
        lay = sc.view_layers.get("Stars")
        if lay:
            lay.samples = 24
    if v in ("coarsevol", "fast2"):
        sc.cycles.volume_step_rate = 4.0
    if v == "fast2":
        sc.cycles.samples = 32
        sc.cycles.adaptive_threshold = 0.04
    if v == "fast3":                      # 20 spp, мягкий адаптивный порог, слой звёзд 16
        sc.cycles.samples = 20
        sc.cycles.adaptive_threshold = 0.05
        lay = sc.view_layers.get("Stars")
        if lay:
            lay.samples = 16
    out = os.path.join(C.OUT, "timing", f"{shot}_{frame}_{v}.png")
    t = time.time()
    R.render_still(out, frame=frame)
    print(f"TIMING {shot} f{frame} {v}: {time.time() - t:.2f} s")
