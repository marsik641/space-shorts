"""Ep009: обнаружение кометы через геометрию наблюдений, 59,5 с EN.

v1 0–6,5: результат; v2 6,5–16: накопление за экспозицию;
v3 16–24: поиск следа; v4 24–34: предсказание и повторные изображения;
v5 34–42: кома; v6 42–51: каталоги и подтверждение; v7 51–59,5: имя и петля.
Всё — реконструкция: координаты, фон, фотометрия и интерфейс условны.
Сканирующая полоса v3 — обозначение работы ПО, не луч телескопа.
Новые функции пока локальны: при чужом Blender spacekit не менять.
Только ключи; драйверов и обработчиков кадров нет.
"""
import math
import os
import random
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
sys.path.insert(0, HERE)

from spacekit import anim
from spacekit import camera as CAM
from spacekit import core as C
from spacekit import shot as S
from comet_coma import emissive, gaussian_material, integrated_streak, key_location, key_scale, sprite, unresolved, visible_between
from system import EXPOSURE_S, FIELD_BOUNDS, HERO_END, HERO_START, PALETTE as P, SEED

EP = os.path.basename(HERE)
OUT = os.path.join(C.OUT, EP, "9x16")
S.OPT.update(fmt="9x16", fps=60)
SHOTS = {"v1": 390, "v2": 570, "v3": 480, "v4": 600, "v5": 480, "v6": 540, "v7": 510}
FONT = "C:/Windows/Fonts/seguisb.ttf"
_FONTS = {}


def sec(scene, value):
    return round(value * C.scene_fps(scene)) + 1


def text(name, body, x, z, size=0.25, color="white", parent=None, align="CENTER"):
    curve = bpy.data.curves.new(name, "FONT")
    curve.body, curve.align_x, curve.align_y = body, align, "CENTER"
    curve.size = size
    if FONT not in _FONTS:
        _FONTS[FONT] = bpy.data.fonts.load(FONT, check_existing=True)
    curve.font = _FONTS[FONT]
    ob = bpy.data.objects.new(name, curve)
    C.link(ob, "Labels")
    ob.parent = parent
    ob.location = (x, -0.55, z)
    ob.rotation_euler = (math.pi / 2, 0, 0)
    ob.data.materials.append(emissive(name + "Mat", P[color]))
    return ob


def line(name, coords, *, color="muted", width=0.012, parent=None, y=-0.35, cyclic=False):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions, curve.bevel_depth, curve.bevel_resolution = "3D", width, 1
    spl = curve.splines.new("POLY")
    spl.points.add(len(coords) - 1)
    for point, (x, z) in zip(spl.points, coords):
        point.co = (x, 0, z, 1)
    spl.use_cyclic_u = cyclic
    ob = bpy.data.objects.new(name, curve)
    C.link(ob, "Observation")
    ob.parent, ob.location.y = parent, y
    ob.data.materials.append(emissive(name + "Mat", P[color]))
    return ob


def box(name, x, z, w, h, **kwargs):
    return line(name, [(x-w/2, z-h/2), (x+w/2, z-h/2), (x+w/2, z+h/2), (x-w/2, z+h/2)], cyclic=True, **kwargs)


def circle(name, x, z, radius, **kwargs):
    return line(name, [(x + radius*math.cos(i*math.tau/64), z + radius*math.sin(i*math.tau/64)) for i in range(64)], cyclic=True, **kwargs)


def paper(name, x, z, w, h, *, parent=None, y=0.4, color="panel"):
    ob = sprite(name, x, z, 1, emissive(name + "Mat", P[color]), parent=parent, y=y)
    ob.scale = (w/2, 1, h/2)
    return ob


def base(name, n):
    sc = S.base_scene(n, exposure=-0.2, samples=24, adaptive=0.03, bloom_strength=0.12,
                      comp={"dispersion": 0})
    sc.cycles.use_denoising = False
    sc.cycles.transparent_max_bounces = 32
    sc.render.use_persistent_data = True
    cam = CAM.camera("Cam_" + name, loc=(0, -24, 0), look_at=(0, 0, 0))
    cam.data.type, cam.data.ortho_scale = "ORTHO", 11.6
    paper("Backdrop", 0, 0, 30, 30, y=2, color="paper")
    return sc, n


def field(name, *, parent=None, seed=SEED, bounds=FIELD_BOUNDS, count=145, clear_hero=True):
    root = C.empty(name, coll="Observation", parent=parent)
    xmin, xmax, zmin, zmax = bounds
    paper(name + "Plate", (xmin+xmax)/2, (zmin+zmax)/2, xmax-xmin, zmax-zmin, parent=root)
    box(name + "Frame", (xmin+xmax)/2, (zmin+zmax)/2, xmax-xmin, zmax-zmin, parent=root)
    rng = random.Random(seed)
    mat = gaussian_material(name + "StarsMat", strength=1.7)
    for i in range(count):
        x, z = rng.uniform(xmin+0.12, xmax-0.12), rng.uniform(zmin+0.12, zmax-0.12)
        # Коридор оставляет обнаружение читаемым: это не реальный кадр.
        if clear_hero and -1.45 < x < 1.25 and 0.35 < z < 1.5:
            z = rng.choice((rng.uniform(zmin+0.15, 0.1), rng.uniform(1.75, zmax-0.15)))
        sprite(f"{name}_star{i}", x, z, rng.uniform(0.022, 0.09), mat, parent=root)
    return root


def badge(name, body, x, z, first, last, n, color="cyan", size=0.26):
    ob = text(name, body, x, z, size, color)
    visible_between(ob, first, last, end=n)
    return ob


def hero_static(parent=None, name="Hero"):
    return integrated_streak(name, HERO_START, HERO_END, first=1, last=1, parent=parent)


def finish(sc, n, shot, events):
    for event, frames in events.items():
        print(f"EVENT {shot} {event}: " + ", ".join(f"{f}:0.8" for f in frames))
    sc.frame_set(1)
    return sc, n


def shot_v1():
    sc, n = base("v1", SHOTS["v1"])
    root = field("DiscoveryField")
    hero_static(root)
    marker = circle("Found", -0.1, 0.9, 1.25, color="amber", parent=root)
    visible_between(marker, sec(sc, 1.5), sec(sc, 4.5), end=n)
    text("Hook", "ONE MOVING STREAK", 0, 3.45, 0.29)
    text("HookSmall", "A new comet in Euclid data", 0, -1.42, 0.23, "cyan")
    return finish(sc, n, "v1", {"streak_found": [sec(sc, 1.5)]})


def shot_v2():
    sc, n = base("v2", SHOTS["v2"])
    root = field("ExposureField")
    text("ExposureTitle", "WHY A STREAK?", 0, 3.45, 0.3)
    moving = unresolved("MovingSource", *HERO_START, parent=root, coma=False)
    first, last = sec(sc, 1.2), sec(sc, 7.3)
    key_location(moving["root"], [(1, *HERO_START), (first, *HERO_START), (last, *HERO_END), (n, *HERO_END)])
    integrated_streak("RecordedLight", HERO_START, HERO_END, first=first, last=last, parent=root)
    text("Fixed", "Distant stars stay fixed", 0, 2.32, 0.23, "cyan")
    text("Recording", "Light accumulates as the object moves", 0, -0.65, 0.21)
    # Ступенчатые часы — реальное время экспозиции, не скорость кометы.
    for i in range(7):
        f0 = round(first + (last-first)*i/6)
        f1 = round(first + (last-first)*(i+1)/6) - 1 if i < 6 else n
        value = EXPOSURE_S*i/6
        badge(f"ExposureClock{i}", f"EXPOSURE  {value:.2f} s", 0, -1.42, f0, f1, n, size=0.25)
    return finish(sc, n, "v2", {"exposure_complete": [last]})


def shot_v3():
    sc, n = base("v3", SHOTS["v3"])
    root = field("SoftwareField")
    hero_static(root)
    text("SoftwareTitle", "SEARCH THE IMAGE", 0, 3.45, 0.3)
    scan = line("SoftwareScan", [(-2.3, -1.7), (2.3, -1.7)], color="cyan", parent=root, width=0.008)
    key_location(scan, [(1, 0, 0), (sec(sc, 5), 0, 4.1)])
    candidate = box("Candidate", -0.1, 0.9, 2.55, 0.86, color="amber", parent=root, width=0.018)
    visible_between(candidate, sec(sc, 4.8), n, end=n)
    badge("CandidateLabel", "MOVING-OBJECT CANDIDATE", 0, -1.42, sec(sc, 4.8), n, n, "amber", 0.23)
    text("SearchNote", "Software search · schematic", 0, 2.32, 0.21, "muted")
    return finish(sc, n, "v3", {"candidate_flagged": [sec(sc, 4.8)]})


def shot_v4():
    sc, n = base("v4", SHOTS["v4"])
    text("FindTitle", "FIND IT AGAIN", 0, 3.45, 0.3)
    # Пять условных полей; положения источника не являются астрометрией.
    for j, z in enumerate((2.2, 1.4, 0.6, -0.2, -1.0)):
        root = field(f"Repeat{j}", seed=SEED+j+1, bounds=(-2.3, 2.3, z-0.31, z+0.31), count=22, clear_hero=False)
        x = -1.5 + 0.75*j
        integrated_streak(f"RepeatTrace{j}", (x-0.3, z-0.08), (x+0.3, z+0.08), first=1, last=1, parent=root, samples=20)
        aim = circle(f"Prediction{j}", x, z, 0.25, color="cyan", parent=root)
        visible_between(aim, sec(sc, 0.6+j*0.85), n, end=n)
    badge("Counts", "16 EXPOSURES / 5 FIELDS", 0, -1.65, sec(sc, 5.1), n, n, size=0.25)
    text("RepeatNote", "Predicted positions → additional images", 0, 2.9, 0.2, "cyan")
    # 16 меток наблюдений, а не 16 одинаковых детекций или измерений ядра.
    for i in range(16):
        mark = line(f"ExposureTick{i}", [(-2.1+i*0.28, -2.0), (-2.1+i*0.28, -1.88)], color="cyan", width=0.018)
        visible_between(mark, sec(sc, 5.1+i*0.2), n, end=n)
    return finish(sc, n, "v4", {"repeat_match": [sec(sc, 0.6+j*0.85) for j in range(5)], "sixteen_images": [sec(sc, 5.1)]})


def shot_v5():
    sc, n = base("v5", SHOTS["v5"])
    text("ComaTitle", "THE COMET CLUE", 0, 3.45, 0.3)
    paper("ComparePlate", 0, 0.5, 4.85, 4.4)
    left = unresolved("PointLikeStar", -1.25, 0.7, scale=2.6, coma=False)
    right = unresolved("CometCloud", 1.05, 0.7, scale=2.6)
    circle("CloudBoundary", 1.05, 0.7, 0.85, color="cyan")
    text("StarLabel", "STAR", -1.25, 2.2, 0.23)
    text("ComaLabel", "COMET", 1.05, 2.2, 0.23)
    text("CloudCallout", "Diffuse coma", 0.95, -0.65, 0.23, "cyan")
    text("CloudMatter", "Dust + gas", 0.95, -1.05, 0.24, "cyan")
    text("CoreNote", "Bright center remains unresolved", 0, -1.62, 0.2, "muted")
    return finish(sc, n, "v5", {"coma_identified": [sec(sc, 2.3)]})


def shot_v6():
    sc, n = base("v6", SHOTS["v6"])
    text("CatalogTitle", "IS IT ALREADY KNOWN?", 0, 3.45, 0.28)
    text("Catalog", "KNOWN-OBJECT CATALOGS", 0, 2.45, 0.23, "muted")
    # Различные условные следы: ни один не связан с реальным именованным объектом.
    for i in range(4):
        z = 1.85-i*0.62
        line(f"CatalogTrack{i}", [(-1.8, z-0.1), (-0.6, z+0.1)], width=0.018)
        line(f"CatalogDash{i}", [(0.1, z), (1.8, z)], width=0.008)
    badge("NoMatch", "NO CATALOG MATCH", 0, -0.9, sec(sc, 2.2), sec(sc, 5.2), n, "amber", 0.28)
    ground = text("FollowUp", "GROUND-BASED FOLLOW-UP", 0, -0.3, 0.25, "cyan")
    visible_between(ground, sec(sc, 5.3), n, end=n)
    badge("Confirmed", "MPC CONFIRMED · 08 OCT 2026", 0, -1.35, sec(sc, 6.6), n, n, "green", 0.23)
    return finish(sc, n, "v6", {"catalog_unmatched": [sec(sc, 2.2)], "mpc_confirmation": [sec(sc, 6.6)]})


def shot_v7():
    sc, n = base("v7", SHOTS["v7"] + 1)
    root = field("DiscoveryField")
    hero_static(root)
    # Начало содержит открытие, затем исчезает пояснение: n+1 точно повторяет v1 f1.
    heading = text("Hook", "ONE MOVING STREAK", 0, 3.45, 0.29)
    small = text("HookSmall", "A new comet in Euclid data", 0, -1.42, 0.23, "cyan")
    name = badge("NewName", "C/2026 S1 (EUCLID)", 0, 2.18, 1, sec(sc, 4.4), n, size=0.29)
    badge("Announced", "ANNOUNCED · 19 OCT 2026", 0, 1.78, 1, sec(sc, 4.4), n, "muted", 0.19)
    # Метаданные VSE также отсутствуют на переходе после 54,8 с.
    return finish(sc, n, "v7", {"name_revealed": [1]})


BUILDERS = {f"v{i}": globals()[f"shot_v{i}"] for i in range(1, 8)}


def draft(shot):
    """Редкие кадры только в draft/, без подмены финальных PNG."""
    from spacekit import render as R
    import shutil

    S.OPT.update(pct=25, samples=4)
    sc, _ = BUILDERS[shot]()
    sc.cycles.samples = 4
    folder = os.path.join(OUT, "draft", shot)
    os.makedirs(folder, exist_ok=True)
    for frame in range(1, SHOTS[shot]+1, 6):
        path = os.path.join(folder, f"{frame:04d}.png")
        R.render_still(path, frame=frame)
        for following in range(frame+1, min(frame+6, SHOTS[shot]+1)):
            shutil.copyfile(path, os.path.join(folder, f"{following:04d}.png"))


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
    if not args or args[0] not in BUILDERS:
        raise SystemExit("Нужен шот v1…v7: preview / save / final / draft")
    if "draft" in args:
        draft(args[0])
    else:
        S.run(BUILDERS, out_dir=OUT, render_end={"v7": SHOTS["v7"]})
