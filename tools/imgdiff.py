"""Попиксельное сравнение пар картинок (регресс-тест библиотеки).

    blender -b --factory-startup -P tools/imgdiff.py -- <a1.png> <b1.png> [<a2.png> <b2.png> ...]
Печатает DIFF: среднее/p99.9/макс |a−b| (0..1) и долю пикселей с разницей > 2/255.
"""
import sys

import bpy
import numpy as np


def load(p):
    im = bpy.data.images.load(p)
    im.colorspace_settings.name = "Non-Color"
    w, h = im.size
    return np.array(im.pixels[:], np.float32).reshape(h, w, 4)[..., :3]


a = sys.argv[sys.argv.index("--") + 1:]
for x, y in zip(a[0::2], a[1::2]):
    d = np.abs(load(x) - load(y)).max(axis=2)
    print(f"DIFF {x.split('/')[-1]}: mean={d.mean():.5f} p99.9={np.percentile(d, 99.9):.4f} "
          f"max={d.max():.4f} frac>2/255={np.mean(d > 2 / 255):.5f}")
