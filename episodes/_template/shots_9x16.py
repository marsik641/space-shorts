"""Эпизод NNN — <ОБЪЕКТ>, вертикаль 1080×1920 60 fps (шаблон: скопировать в episodes/epNNN_<slug>/).

    blender -b --factory-startup -P episodes/epNNN_<slug>/shots_9x16.py -- <шот> [preview F,..] [pct=50] [samples=N] [outdir=DIR] [final] [save]

    preview F,..  — кадры превью (pct=50 по умолчанию) в out/<ep>/9x16/previews/<шот>_fNNNN.png (outdir= — другая папка)
    final         — PNG-секвенция out/<ep>/9x16/frames/<шот>/####.png с докачкой (обычно через tools/render_episode.sh)
    save          — .blend в out/<ep>/9x16/scenes/<шот>.blend
    Лог превью — перенаправлять в out/<ep>/9x16/logs/prev_<шот>.log (по нему tools/cues.py). Один Blender за раз.

Монтаж (кадры @60): перечислить шоты, длительность и смысл каждого; где склейки и на каких событиях.
SHOTS = episode.json → edit[].frames (проверяет tools/check_episode.py); цель Σ ≤ 1770 кадров (29,5 с).
Шоты с пульсаром: S.report_flash(<шот>, NS.key_pulse_flash(...)); другие события для музыки — print строки
«EVENT <шот> <имя>: кадр[:значение], ...» (формат — docstring tools/cues.py).
fps — из сцены (C.scene_fps(sc)), не из S.OPT. Общие параметры — system.py (from system import ...).
API — docs/spacekit.md.
Каждый эпизод — своя драматургия и раскладка: этот файл — только каркас, не шаблон ролика.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
sys.path.insert(0, HERE)

from mathutils import Vector

from spacekit import camera as CAM
from spacekit import core as C
from spacekit import shot as S
from spacekit import sky as SKY

EP = os.path.basename(HERE)
OUT = os.path.join(C.OUT, EP, "9x16")
S.OPT.update(fmt="9x16", fps=60)
SHOTS = {"v1": 180, "v2": 300, "v3": 360, "v4": 300, "v5": 300, "v6": 330}  # 1770 кадров
sph = CAM.sph


def shot_v1():
    n = SHOTS["v1"]
    ex = 0.0
    sc = S.base_scene(n, exposure=ex, samples=40, adaptive=0.03)
    cam, tgt = CAM.camera_rig("Cam_V1", lens=35)
    CAM.key_camera(cam, tgt, [
        dict(frame=1, loc=sph(10, -90, 10), target=(0, 0, 0), lens=35),
        dict(frame=n, loc=sph(7, -70, 12), target=(0, 0, 0), lens=35),
    ])
    stars = SKY.build_sky(sc, cam, ex, gal=SKY.gal_for_view(-Vector(sph(1, -80, 10)), tilt_deg=30, l_center_deg=60))
    # ... объекты сцены: spacekit.bodies.*, spacekit.fx.*, spacekit.orbits, spacekit.lighting ...
    S.finish(sc, stars, star_samples=24)
    return sc, n


BUILDERS = {"v1": shot_v1}

if __name__ == "__main__":
    S.run(BUILDERS, out_dir=OUT)
