"""Эпизод NNN — <ОБЪЕКТ>, вертикаль 1080×1920 60 fps (шаблон: скопировать в episodes/epNNN_<obj>/).

    blender -b --factory-startup -P episodes/epNNN_<obj>/shots_9x16.py -- <шот> [preview F,..] [final] [save]

Монтаж (кадры @60): перечислить шоты, длительность и смысл каждого; где склейки и на каких событиях.
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
SHOTS = {"v1": 300}
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
