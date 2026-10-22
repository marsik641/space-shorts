"""SN 1987A — ep006, новая постановка: 40 с, 5 шотов, 1080×1920p60.

v1 270: светящийся газ и нити кольца, пролёт с ближним передним планом.
v2 450: плазма голубого сверхгиганта, близко к лимбу, медленное раскрытие.
v3 480: вспышка выхода ударной волны и расширение неоднородного выброса.
v4 600: удар по старому газу, неровное кольцо и центральные обломки.
v5 600 (+1 контрольный): раскрытие остатка; возвращение к первому кадру v1.

Без учебных срезов, счётчиков и лучей нейтрино. Микроструктура —
художественная реконструкция, условности в system.py/facts.md.
CLI: -- v1 preview 1,120,240,360 [pct=50] | draft | final
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
sys.path.insert(0, HERE)

import bpy
from mathutils import Vector

from spacekit import anim as A
from spacekit import camera as CAM
from spacekit import core as C
from spacekit import render as R
from spacekit import shot as S
from spacekit import sky as SKY
from spacekit.fx import sn_shell as SS

import cinema as CI
import system as SY

EP = os.path.basename(HERE)
OUT = os.path.join(C.OUT, EP, "9x16")
SHOTS = {"v1": 270, "v2": 450, "v3": 480, "v4": 600, "v5": 601}
S.OPT.update(fmt="9x16", fps=60)


def scene(n, exposure=-.1):
    sc = S.base_scene(n, exposure=exposure, samples=16, adaptive=.025, look="AgX - Medium High Contrast",
        bloom_strength=.14, comp=dict(fog_strength=.045, vignette=.17, dispersion=0))
    sc.render.use_motion_blur = False
    cam, target = CAM.camera_rig("E6_Camera", lens=42, clip_start=.002)
    return sc, cam, target


def path(cam, target, n, pose):
    for f in sorted(set([1, n] + list(range(1, n + 1, 3)))):
        loc, aim = pose((f - 1) / max(1, n - 1))
        cam.location, target.location = loc, aim
        cam.keyframe_insert("location", frame=f)
        target.keyframe_insert("location", frame=f)
    A.set_interpolation(cam, "LINEAR")
    A.set_interpolation(target, "LINEAR")


def sky(sc, cam, exposure):
    stars = SKY.build_sky(sc, cam, exposure, mw_strength=.045, star_brightness=.65, mag_limit=8)
    # Единый проход: фон проходит через поглощение газа/пыли. Аддитивный
    # отдельный слой Stars обошёл бы объёмы и оставил звёзды поверх пыли.
    R.setup_volume_denoise(sc, "far")
    sc.cycles.volume_biased = True
    sc.cycles.use_denoising = False


def interp(a, b, u):
    return tuple(x + (y - x) * u for x, y in zip(a, b))


def near_pose(u):
    from mathutils import Euler
    rot = Euler((math.radians(43), math.radians(-9), math.radians(-18))).to_matrix()
    angle = math.radians(-48 + u * 6)
    spot = rot @ Vector((math.cos(angle), math.sin(angle), 0))
    return tuple(spot + Vector((.18, -.68, .40))), tuple(spot)


def v1():
    n = SHOTS["v1"]
    sc, cam, tgt = scene(n, .15)
    CI.ring_system()
    cam.data.lens = 80
    path(cam, tgt, n, near_pose)
    sky(sc, cam, .15)
    return sc, n


def star_pose(u):
    return interp((.18, -1.67, .48), (.12, -2.28, .58), u), interp((-.13, .03, .29), (-.08, 0, .11), u)


def v2():
    n = SHOTS["v2"]
    sc, cam, tgt = scene(n, -.35)
    _, mat = CI.plasma()
    CI.keys(mat, "flow", [(1, .12), (n, .3)])
    cam.data.lens = 34
    path(cam, tgt, n, star_pose)
    sky(sc, cam, -.35)
    return sc, n


def v3():
    n = SHOTS["v3"]
    sc, cam, tgt = scene(n, -.45)
    star, mat = CI.plasma()
    CI.keys(mat, "flow", [(1, .3), (n, .5)])
    CI.keys(mat, "flash", [(1, 0), (38, 0), (45, 16), (62, 1), (90, 0), (n, 0)])
    CI.keys(mat, "gain", [(1, 1), (48, 1), (120, .1), (n, .05)])
    CI.keys(mat, "breakup", [(1, 0), (45, 0), (65, .95), (69, 1), (n, 1)])
    CI.keys(bpy.data.materials["E6_LimbMat"], "gain", [(1, 1), (38, 1), (45, 0), (n, 0)])
    for ob in (star, bpy.data.objects["E6_LimbGas"]):
        for frame, hidden in ((1, False), (68, False), (69, True)):
            ob.hide_render = hidden
            ob.keyframe_insert("hide_render", frame=frame)
        A.set_interpolation(ob, "CONSTANT", path_contains="hide_render")
    sh = SS.build_shell_nebula("E6_Shock", radius=1.05, seed=8712,
        palette=[(0, (.6, .76, .95)), (.35, (.17, .5, .8)), (.65, (.22, .62, .72)), (1, (.58, .28, .12))],
        radial=.55, fil_scale=(7, 24), sharp=18, stretch=(1.06, .96, 1.03), step=.08,
        hollow=.68, glow=0, haze=.015, thick=.16, cover=.5, hot=.05)
    SS.key_value(sh, "glow", [(1, 0), (44, 0), (55, 7), (150, 4), (n, 2.1)])
    SS.key_radius(sh, lambda f: 1.04 + max(0, f - 45) / 375 * 3.9, 1, n, step=3)
    path(cam, tgt, n, lambda u: (interp((.12, -2.28, .58), (.4, -12.3, 3.6), u), (0, 0, .08)))
    cam.data.lens = 34
    sky(sc, cam, -.45)
    print("EVENT v3 shock_breakout: 45:1.0")
    return sc, n


def v4():
    n = SHOTS["v4"]
    sc, cam, tgt = scene(n, .05)
    root, gas, fil, ej = CI.ring_system()
    CI.keys(gas, "hit", [(1, 0), (200, .35), (400, .7), (n, 1)])
    for mat in fil:
        CI.keys(mat, "hit", [(1, 0), (200, .35), (400, .7), (n, 1)])
    # Небольшой облёт: микроструктура раскрывается параллаксом.
    path(cam, tgt, n, lambda u: (interp((.3, -5.5, .4), (-.3, -5.7, .4), u), (0, 0, .08)))
    cam.data.lens = 50
    sky(sc, cam, .05)
    print("EVENT v4 ring_collision: 120:0.6, 270:0.7, 420:0.6")
    return sc, n


def v5():
    n = SHOTS["v5"]
    sc, cam, tgt = scene(n, .15)
    CI.ring_system()
    cam.data.lens = 60
    end = near_pose(0)
    wide = ((-.3, -11.0, .4), (0, 0, .06))
    for f, lens in ((1, 60), (400, 70), (n, 80)):
        cam.data.lens = lens
        cam.data.keyframe_insert("lens", frame=f)
    A.set_interpolation(cam.data, "BEZIER")
    ahead = near_pose(.0001)
    derivatives = [tuple((y - x) / .0001 * (n - 1) / (SHOTS["v1"] - 1) for x, y in zip(a, b))
                   for a, b in zip(end, ahead)]
    def pose(u):
        # Кубическая интерполяция с конечной скоростью v1. 601-й кадр —
        # контрольный дубль первого v1; в монтаж идут 600 кадров.
        h0, h1, hv = 2*u**3 - 3*u*u + 1, -2*u**3 + 3*u*u, u**3 - u*u
        return tuple(tuple(h0*x + h1*y + hv*d for x, y, d in zip(a, b, v))
                     for a, b, v in zip(wide, end, derivatives))
    path(cam, tgt, n, pose)
    sky(sc, cam, .15)
    return sc, n


BUILDERS = {"v1": v1, "v2": v2, "v3": v3, "v4": v4, "v5": v5}


def draft(argv):
    import shutil
    step = next((int(a[5:]) for a in argv if a.startswith("step=")), 6)
    argv = [a for a in argv if a != "draft" and not a.startswith("step=")]
    if not any(a.startswith("pct=") for a in argv):
        argv.append("pct=25")
    if not any(a.startswith("samples=") for a in argv):
        argv.append("samples=4")
    S.run(BUILDERS, out_dir=OUT, argv=argv)
    shot = argv[0]
    n = SHOTS[shot]
    d = os.path.join(OUT, "draft", shot)
    R.render_sequence(d, 1, n, step=step)
    for f in range(1, n + 1, step):
        for g in range(f + 1, min(f + step, n + 1)):
            shutil.copyfile(os.path.join(d, f"{f:04d}.png"), os.path.join(d, f"{g:04d}.png"))


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:]
    if "draft" in argv:
        draft(argv)
    else:
        S.run(BUILDERS, out_dir=OUT, render_end={"v5": 600})

