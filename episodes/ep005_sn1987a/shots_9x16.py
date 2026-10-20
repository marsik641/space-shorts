"""Эпизод 005 — SN 1987A, вертикаль 1080×1920 60 fps.

    blender -b --factory-startup -P episodes/ep005_sn1987a/shots_9x16.py -- <шот> [preview F,..] [pct=50] [samples=N] [outdir=DIR] [final] [save]
    ... -- <шот> draft [pct=25] [samples=4] [step=6]  — черновое видео (docs/approval.md, 1a)

Монтаж (кадры @60, склейки встык; камера v1/v6/v7 — «с Земли»: смотрим на звезду, север вверх):
    v1  300  холодный старт: голубой сверхгигант Sk −69 202 крупно → выход ударной волны (вспышка с одного края) →
             огненный шар с пальцами Рэлея–Тейлора заполняет кадр (EVENT breakout, blast)
    v2  540  «за часы до»: звезда в разрезе (октант), нырок к центру сквозь 7 слоёв (звезда/ядро ×5000 честно,
             толщины слоёв — схема): H → He → C → O → Ne → Si → железное ядро; подписи; контур Земли того же масштаба
    v3  420  коллапс ядра (замедлен): 6000 → 30 км (протонейтронная звезда), камера следом ×40; отскок (EVENT bounce) — всплеск нейтрино
             иглами сквозь камеру; полость с горящей оболочкой кремния
    v4  480  вся звезда в разрезе: нейтрино уходят за ~1.5 с экрана, ударная волна ползёт сквозь слои 1.8 ч (часы —
             титрами), перемешивает их; выход на поверхность — вспышка (EVENT breakout)
    v5  600  Kamiokande-II изнутри, 23.02.1987 07:35:35 UT: нейтрино снизу сквозь Землю (−19.7°), 12 событий в
             реальное время (после 2 с — ×3): кольца ФЭУ под 41° (EVENT nu), счётчик — титрами
    v6  600  «с Земли»: точка в БМО вспыхивает (EVENT light), вспышка зажигает три кольца; 1994 → 2016 — выброс
             растёт, «жемчужины» загораются по кольцу; поворот остатка на 25° раскрывает объём
    v7  630  2024: вытянутый выброс, вероятная нейтронная звезда (JWST, EVENT ns); перемотка 2024 → 1987 и нырок
             в звезду ×10⁵ — последний кадр = первый кадр v1 (петля)
Масштабы и условности — system.py. spacekit: bodies.star, bodies.star_layers, fx.explosion, fx.burst, fx.sn_rings.
"""
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
sys.path.insert(0, HERE)

import bmesh
import bpy
from mathutils import Quaternion, Vector

from spacekit import anim as A
from spacekit import camera as CAM
from spacekit import core as C
from spacekit import render as R
from spacekit import shot as S
from spacekit import sky as SKY
from spacekit.bodies import star as ST
from spacekit.bodies import star_layers as SL
from spacekit.bodies.planets import _NB
from spacekit.fx import burst as BU
from spacekit.fx import explosion as EX
from spacekit.fx import label as LB
from spacekit.fx import nebula_sky as NB
from spacekit.fx import shell as SH
from spacekit.fx import sn_rings as RG
from spacekit.fx import sn_shell as SS

import system as SY

EP = os.path.basename(HERE)
OUT = os.path.join(C.OUT, EP, "9x16")
S.OPT.update(fmt="9x16", fps=60)
LB.FONT = "C:/Windows/Fonts/framd.ttf"           # подписи — шрифтом субтитров (Franklin Gothic Medium)
SHOTS = {"v1": 300, "v2": 540, "v3": 420, "v4": 480, "v5": 600, "v6": 600, "v7": 630}
LOOK = "AgX - Punchy"
LABEL_COL = (0.92, 0.95, 1.0)
COMP = dict(streaks=0.0, vignette=0.28, fog_strength=0.32)
COMP_PT = dict(COMP, streaks=0.9, streaks_n=2, streaks_angle_deg=0.0, streaks_threshold=300.0, streaks_fade=0.993,
               streaks_tint=(0.62, 0.78, 1.0))
# анаморфный луч — только от точечной вспышки (v6/v7): от диска Glare Streaks даёт толстую полосу
NU_RGB = (0.55, 0.40, 1.0)

# --- поза «с Земли» (кадр 1 v1 = последний кадр v7)
LENS_E = 50.0
D_E = 9.0                                         # R★: звезда ≈ 55 % ширины кадра
STAR_UP = 0.07                                    # звезда чуть выше центра (субтитры снизу): цель ниже центра
EX_E = -0.6                                       # экспозиция кадра петли
FLOW0 = 1.0                                       # фаза грануляции в кадре 1 v1
FLOW_RATE = 0.0016                                # за кадр (v1 и конец v7 — одна скорость)
GAL_E = SKY.gal_for_view(Vector((0.35, 1.0, -0.55)), tilt_deg=-28, l_center_deg=70)


def smooth(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3.0 - 2.0 * u)


def lerp(a, b, s):
    return a + (b - a) * s


def exp_lerp(a, b, s):
    return math.exp(lerp(math.log(a), math.log(b), s))


def key_path(cam, tgt, f0, f1, pose, step=2):
    """Ключи камеры/цели по функции pose(f) -> (loc, target) каждые step кадров (LINEAR)."""
    frames = list(range(f0, f1 + 1, step))
    if frames[-1] != f1:
        frames.append(f1)
    for f in frames:
        loc, target = pose(f)
        cam.location = tuple(loc)
        cam.keyframe_insert("location", frame=f)
        tgt.location = tuple(target)
        tgt.keyframe_insert("location", frame=f)
    A.set_interpolation(cam, "LINEAR")
    A.set_interpolation(tgt, "LINEAR")


def key_scale(ob, s_of_f, f0, f1, step=1):
    for f in list(range(f0, f1 + 1, step)) + [f1]:
        s = s_of_f(f)
        ob.scale = (s, s, s)
        ob.keyframe_insert("scale", frame=f)
    A.set_interpolation(ob, "LINEAR", path_contains="scale")


def key_rot_z(ob, deg_of_f, f0, f1, step=4):
    for f in list(range(f0, f1 + 1, step)) + [f1]:
        ob.rotation_euler = (0.0, 0.0, math.radians(deg_of_f(f)))
        ob.keyframe_insert("rotation_euler", frame=f)
    A.set_interpolation(ob, "LINEAR", path_contains="rotation")


def key_values(nt, name, pairs, ipo="BEZIER"):
    s = nt.nodes[name].outputs[0]
    for f, v in pairs:
        s.default_value = v
        s.keyframe_insert("default_value", frame=f)
    A.set_interpolation(nt, ipo, path_contains=f'nodes["{name}"]')


def label(name, text, loc, cam, n, px=34, off=(0, 0), color=LABEL_COL, strength=2.4, parent=None, step=4,
          fade=None, align="CENTER"):
    lb = LB.build_label(name, text, tuple(loc), cam, px=px, offset_px=off, color=color, strength=strength,
                        parent=parent, align=align)
    LB.key_screen_size(lb, cam, 1, n, step=step)
    if fade:
        f_in, f_out = fade
        LB.key_fade(lb, 1.0, f_in=f_in, f_out=f_out, length=18)
    return lb


def event(shot, name, frames):
    print(f"EVENT {shot} {name}: " + ", ".join(str(int(f)) for f in frames))


def scene(n, ex, samples=16, adaptive=0.03, comp=COMP, lens=LENS_E, clip=(0.01, 1.0e6)):
    """16 spp: всё эмиссионное (объёмы без рассеяния) + денойз OptiX — шум как у 24, финал ≈ 5 ч вместо 7."""
    sc = S.base_scene(n, exposure=ex, samples=samples, adaptive=adaptive, look=LOOK, comp=comp)
    cam, tgt = CAM.camera_rig("Cam", lens=lens, clip_start=clip[0], clip_end=clip[1])
    return sc, cam, tgt


def earth_pose(D=D_E):
    """Камера на D R★ от звезды со стороны Земли; цель ниже центра — звезда над серединой кадра."""
    return -SY.VIEW_DIR * D, Vector((0.0, 0.0, -STAR_UP * D))


STAR_HOT = (0.78, 0.90, 1.0)                      # 16 000 K: бело-голубые ячейки
STAR_COOL = (0.16, 0.38, 1.0)                     # промежутки и край — глубокий синий (кинематографичная насыщенность)


def progenitor(n, flow_of_f, cam, detail="close", parent=None, strength=2.3, halo=0.0):
    """Sk −69 202: фотосфера (R = 1) + ореол-спрайт; выход ударной волны — с северо-восточного края, к камере."""
    bdir = Vector((-0.55, -0.60, 0.58)).normalized()
    st = ST.build_star("Sk69", radius=1.0, temp_k=SY.TEFF, parent=parent, seed=SY.SEEDS["star"], strength=strength,
                       gran_scale=42.0, contrast=0.3, limb_u=0.6, sat=1.8, detail=detail, breakout_dir=bdir,
                       halo=halo, glow=(1.2, 0.18), cam=cam, hot_rgb=STAR_HOT, cool_rgb=STAR_COOL)
    ST.key_value(st, "flow", [(f, flow_of_f(f)) for f in (1, n)], ipo="LINEAR")
    return st, bdir


NEB_E = (Vector((0.0, 1.0, 0.0)) + Vector((-0.30, 0.0, 0.22))).normalized()   # чуть выше и левее звезды


def earth_sky(sc, cam, ex=EX_E):
    """Небо «с Земли» (поле БМО — плотнее обычного, слабая H II-туманность за звездой) — одно для v1, v6, v7:
    склейки и петля без скачка неба."""
    stars = SKY.build_sky(sc, cam, ex, gal=GAL_E, mw_strength=0.25, star_brightness=1.6, mag_limit=12)
    sky_color(sc, SY.VIEW_DIR, ex, SY.SEEDS["star"])
    NB.add_nebula(sc, NEB_E, radius_deg=30.0, strength=0.3, exposure=ex, seed=SY.SEEDS["star"] + 40, scale=4.0)
    return stars


def sky_color(sc, look, ex, seed):
    """Глубокий сине-фиолетовый фон (свет диска БМО и газа вокруг) вместо чёрного — широкая слабая «туманность»."""
    NB.add_nebula(sc, look, radius_deg=80.0, strength=0.07, exposure=ex, seed=seed + 70, core_frac=0.6,
                  ha=(0.10, 0.16, 0.60), oiii=(0.28, 0.14, 0.75), filaments=0.25, dust=0.5, scale=1.6, name="NebBlue")


# ================================================================ v1: выход ударной волны и огненный шар
BREAK_F = 30


def ej_radius_v1(f):
    if f < BREAK_F + 6:
        return 1.0
    return 1.0 + 6.4 * (1.0 - math.exp(-(f - BREAK_F - 6) / 95.0))


def v1_dist(f, n=300):
    if f <= BREAK_F:
        return D_E - 0.2 * (f - 1) / (BREAK_F - 1)                 # медленный наезд (так же подходит конец v7)
    return lerp(D_E - 0.2, 24.0, smooth((f - BREAK_F) / (n - BREAK_F)) ** 0.8)


V1_STEP = 0.16                                    # шаг луча по оболочке (0.07 — 99 с/кадр на 100 %, нити те же)


def shot_v1():
    """Выход ударной волны → вспышка → волокнистая огненная оболочка (FIRE) вокруг раскалённого клубящегося ядра,
    в центре — ослепительная точка с анаморфным лучом, наружу летят искры-обломки (референсы владельца, 20.10.2026)."""
    n = SHOTS["v1"]
    ex = EX_E
    sc, cam, tgt = scene(n, ex, comp=COMP_PT, samples=12)
    key_path(cam, tgt, 1, n, lambda f: earth_pose(v1_dist(f, n)))
    stars = earth_sky(sc, cam)
    st, bdir = progenitor(n, lambda f: FLOW0 + FLOW_RATE * (f - 1), cam)
    f0 = BREAK_F
    ST.key_value(st, "front", [(f0, 0.0), (f0 + 14, 1.0)])
    ST.key_value(st, "flash", [(f0, 0.0), (f0 + 6, 14.0), (f0 + 40, 9.0)])         # < порога лучей (диск — не точка)
    ST.key_visible(st["disk"], [(1, True), (f0 + 30, False)])
    ST.key_visible(st["glow"], [(1, True), (f0 + 30, False)])
    R_of = ej_radius_v1
    # волокнистая оболочка: яркость ∝ 1/R (путь луча в объёме ∝ R) — поверхностная яркость держится
    sh = SS.build_shell_nebula("Blast", radius=1.0, seed=SY.SEEDS["ej"], palette=SS.FIRE, radial=0.7,
                               fil_scale=(1.8, 4.5), sharp=16.0, step=V1_STEP, glow=0.0, hot=1.0, haze=0.3,
                               thick=0.12, inner=0.0, cover=0.45, hollow=0.62)
    SS.key_radius(sh, lambda f: R_of(f) * 1.02, 1, n, step=2)
    SS.key_value(sh, "glow", [(f0 + 4, 0.0), (f0 + 12, 50.0)] +
                 [(f, 24.0 / R_of(f)) for f in range(f0 + 40, n + 1, 20)])
    SS.key_value(sh, "hot", [(f0, 1.0), (f0 + 60, 0.8), (n, 0.4)])
    # голубое сияние внутри — спрайт (оболочка полая: объём только в слое нитей)
    cg = core_glow("BlastGlow", cam, (0.40, 0.58, 1.0))
    key_scale(cg, lambda f: R_of(f) * 0.75, 1, n, step=2)
    key_values(cg.data.materials[0].node_tree, "strength", [(f0 + 10, 0.0), (f0 + 40, 0.9), (n, 0.45)])
    SS.key_value(sh, "flow", [(1, 0.0), (n, 0.7)], ipo="LINEAR")
    ST.key_visible(sh["ob"], [(1, False), (f0 + 4, True)])
    # раскалённое клубящееся ядро взрыва (корка/трещины, без тяжёлого поглощения — светит насквозь)
    ej = EX.build_explosion("Ej", radius=1.0, seed=SY.SEEDS["ej"], cells=7.5, fingers_max=0.6, step=0.25,
                            heat=1.0, glow=0.0, absorb=2.0, fingers=0.35, shell=0.6, core=0.6, rim=0.0)
    EX.key_radius(ej, lambda f: R_of(f) * 0.32, 1, n, step=2)
    EX.key_value(ej, "glow", [(1, 0.0), (f0 + 5, 0.0), (f0 + 14, 20.0)] +
                 [(f, 6.0 / R_of(f)) for f in range(f0 + 40, f0 + 81, 20)])
    EX.key_value(ej, "heat", [(f0, 1.0), (n, 0.8)])
    EX.key_value(ej, "absorb", [(f0, 10.0)] + [(f, 6.0 / R_of(f)) for f in range(f0 + 40, n + 1, 20)])
    EX.key_value(ej, "flow", [(1, 0.0), (n, 0.9)], ipo="LINEAR")
    EX.key_value(ej, "glow", [(f0 + 90, 30.0 / R_of(f0 + 90)), (f0 + 120, 0.0)])          # ядро гаснет — дальше сияние
    ST.key_visible(ej["ob"], [(1, False), (f0 + 5, True), (f0 + 122, False)])           # оболочки (inner) и точка
    # ослепительная точка в центре (анаморфный луч — COMP_PT, только от точки)
    pt = _glow_sphere("Core", 0.03, (0.80, 0.88, 1.0), 0.0)
    key_values(pt.data.materials[0].node_tree, "strength",
               [(f0 + 2, 0.0), (f0 + 8, 900.0), (f0 + 60, 300.0), (n, 140.0)])
    # искры-обломки: золотые иглы с короткими хвостами, головы разбросаны (lag)
    sp = BU.build_burst("Sparks", n=1400, r_min=0.9, r_max=16.0, cam=cam, px=0.7, color=(1.0, 0.70, 0.30),
                        strength=9.0, trail=0.22, lag=7.0, amp=(0.15, 1.0), seed=SY.SEEDS["ej"] + 3, k=24)
    BU.key_head(sp, [(f0 + 6, 0.9), (n, 22.0)], ipo="LINEAR")
    BU.key_strength(sp, [(f0 + 4, 0.0), (f0 + 14, 9.0), (n, 6.0)])
    event("v1", "breakout", [f0])
    event("v1", "blast", [f0 + 12])
    S.finish(sc, stars, denoise="far", star_samples=16)
    return sc, n


# ================================================================ v2–v4: звезда в разрезе
D_CUT = 10.0
LENS_CUT = 35.0
HH_CUT = D_CUT * 18.0 / LENS_CUT                  # полувысота кадра на расстоянии угла разреза
CUT_BREAKOUT = (0.55, -0.45, 0.70)                # выход ударной волны в v4: на видимой коже, вне выреза
GAL_CUT = SKY.gal_for_view(-Vector((1.0, 1.0, 0.6)).normalized(), tilt_deg=25, l_center_deg=40)


def star_glow(world, cam, R, strength=1.2, width=0.18):
    """Ореол-спрайт вокруг звезды радиуса R (ед. мира WORLD): мягкое голубое сияние, как у v1."""
    me = bpy.data.meshes.new("StarGlow")
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, cap_tris=False, segments=96, radius=1.0 + 6.0 * width)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(ST._glow_material("StarGlowMat", STAR_COOL, strength, width))
    ob = bpy.data.objects.new("StarGlow", me)
    C.link(ob, "Star")
    ob.parent = world
    ob.scale = (R, R, R)
    con = ob.constraints.new("COPY_ROTATION")
    con.target = cam
    ob.visible_shadow = False
    ob.visible_diffuse = ob.visible_glossy = ob.visible_transmission = ob.visible_volume_scatter = False
    return ob


def cutaway(world, photo_strength=2.3):
    return SL.build_cutaway("Onion", SY.layers_for_kit(), parent=world, seed=SY.SEEDS["cut"], skin_u=256,
                            tex_scale=6.0, photo=dict(temp_k=SY.TEFF, strength=photo_strength, seed=SY.SEEDS["star"],
                                                      gran_scale=42.0, contrast=0.3, limb_u=0.6, sat=1.8, lod=0,
                                                      breakout_dir=CUT_BREAKOUT, hot_rgb=STAR_HOT,
                                                      cool_rgb=STAR_COOL))


def cut_dir(az_off=0.0, el=35.264):
    a, e = math.radians(45.0 + az_off), math.radians(el)
    return Vector((math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)))


def cut_cam_pose(az_off=0.0, el=35.264, D=D_CUT, aim_drop=0.06):
    """Камера смотрит в угол разреза (центр звезды) с направления az/el; цель чуть ниже угла."""
    d = cut_dir(az_off, el)
    up = Vector((0, 0, 1))
    up = (up - d * up.dot(d)).normalized()
    return d * D, -up * D * aim_drop


def cut_sky(sc, cam, ex, look=(-1.0, -1.0, -1.0)):
    """Небо разреза: туманность БМО за звездой (look — направление взгляда камеры), чуть выше и левее центра."""
    stars = SKY.build_sky(sc, cam, ex, gal=GAL_CUT, mw_strength=0.3, star_brightness=1.0)
    lk = Vector(look).normalized()
    sky_color(sc, lk, ex, SY.SEEDS["cut"])
    side = lk.cross(Vector((0, 0, 1))).normalized()
    nd = (lk + Vector((0, 0, 0.42)) - side * 0.3).normalized()
    NB.add_nebula(sc, nd, radius_deg=34.0, strength=0.45, exposure=ex, seed=SY.SEEDS["cut"] + 40, scale=3.5)
    return stars


V2_S0 = 2.45 / SY.layer_radii()[-1]               # звезда целиком: R★ ≈ 0.34 высоты кадра
V2_S1 = 1.10 / SY.layer_radii()[0]                # ядро ≈ 0.15 высоты кадра
V2_POSE = (lambda f, n: dict(az_off=lerp(-6.0, 6.0, f / n), el=lerp(33.0, 37.0, f / n)))


def v2_scale(f, n=540):
    u = min(max((f - 40) / (n - 70), 0.0), 1.0)
    return exp_lerp(V2_S0, V2_S1, 0.35 * smooth(u) + 0.65 * u)


def shot_v2():
    n = SHOTS["v2"]
    ex = -0.4
    sc, cam, tgt = scene(n, ex, lens=LENS_CUT)
    world = C.empty("WORLD", coll="Star")
    key_scale(world, lambda f: v2_scale(f, n), 1, n)
    key_path(cam, tgt, 1, n, lambda f: cut_cam_pose(**V2_POSE(f, n)))
    stars = cut_sky(sc, cam, ex, look=-cut_dir(0.0, 35.0))
    cut = cutaway(world)
    star_glow(world, cam, SY.layer_radii()[-1])
    SL.key_values(cut, "flow", [(1, 0.0), (n, 0.6)], ipo="LINEAR")
    SL.key_values(cut, "hot", [(1, 0.35)], which=["Fe"])                       # ядро раскалено (бело-жёлтое)
    ST.key_value(None, "flow", [(1, FLOW0), (n, FLOW0 + 0.4)], ipo="LINEAR", mat=cut["photo"])
    # подписи слоёв (на верхних гранях, середина полосы — среднее геометрическое): видны, пока полоса — 18–85 % кадра
    radii = cut["radii"]
    c45 = math.cos(math.radians(45.0))
    for i in range(1, len(radii)):
        name = cut["layers"][i]["name"]
        rm = min(radii[i - 1] * 1.7, math.sqrt(radii[i - 1] * radii[i]))   # у внутренней границы — ближе к центру кадра
        p = Vector((0.0, rm * c45, rm * c45)) if i % 2 else Vector((rm * c45, 0.0, rm * c45))
        p = p + Vector((1.0, 1.0, 1.0)).normalized() * rm * 0.45      # над гранью, к камере (не тонет в плоскости)
        fr = [f for f in range(1, n + 1) if 0.18 * HH_CUT < rm * v2_scale(f, n) < 0.85 * HH_CUT]
        if len(fr) < 50:
            continue
        f_out = min(n - 135, fr[-1] - 12)                    # до подписи ядра (n − 110) — без наложений
        if f_out - max(1, fr[0] - 6) < 40:
            continue
        label(f"Lbl_{name}", SY.LAYER_NAMES[name], p, cam, n, px=40, parent=world,
              fade=(max(1, fr[0] - 6), f_out))
    # ядро: подпись и контур Земли того же масштаба (кольцо ⟂ взгляду)
    rfe = radii[0]
    lift = Vector((1.0, 1.0, 1.0)).normalized() * rfe * 3.0
    label("Lbl_Fe", "Iron core\n~1.5 Suns of mass", lift + Vector((0, 0, rfe)), cam, n, px=36, off=(0, 110),
          parent=world, fade=(n - 110, n + 40))
    er = SY.EARTH_R_KM / SY.CUT_UNIT_KM
    ring = SH.build_ring("EarthRing", cam, radius=er, location=tuple(lift), color=(0.55, 0.85, 1.0), strength=0.0,
                         fill=0.0, parent=world)
    # контур — перед ядром (в плоскости через центр он внутри «сплошной» звезды); радиус — под тот же угловой размер
    cam_end = cut_cam_pose(**V2_POSE(n, n))[0]
    SH.key_ring(ring, cam, lambda f: er * (cam_end - lift * v2_scale(f, n)).length / cam_end.length, 2.0, 1, n,
                step=4)
    SH.key_strength(ring, [(1, 0.0), (n - 120, 0.0), (n - 90, 3.0)])
    loc, tg = cut_cam_pose(**V2_POSE(n, n))
    fwd = (tg - loc).normalized()
    up = (Vector((0, 0, 1)) - fwd * fwd.z).normalized()
    label("Lbl_Earth", "Earth, same scale", lift - up * er, cam, n, px=30, off=(0, -30), parent=world,
          color=(0.55, 0.85, 1.0), fade=(n - 90, n + 40))
    event("v2", "core", [n - 110])
    S.finish(sc, stars, denoise="far", star_samples=16)
    return sc, n


# v3: коллапс ядра
V3_COL0, V3_COL1 = 70, 250                        # последние ~0.3 с падения × SLOW_COLLAPSE = 3 с
V3_BOUNCE = V3_COL1


def v3_core_r(f):
    rfe = SY.layer_radii()[0]
    rns = SY.PNS_R_KM / SY.CUT_UNIT_KM                        # за < 1 с — протонейтронная звезда R ≈ 30 км (WJ05)
    if f <= V3_COL0:
        return rfe
    u = min((f - V3_COL0) / (V3_COL1 - V3_COL0), 1.0)
    return rns + (rfe - rns) * (1.0 - u * u) ** 1.5           # свободное падение ускоряется


def v3_scale(f):
    if f <= V3_COL0:
        return V2_S1
    u = min((f - V3_COL0) / (V3_COL1 + 30 - V3_COL0), 1.0)
    return exp_lerp(V2_S1, V2_S1 * 7.5, smooth(u))                # камера остаётся снаружи полости: смотрим в «дыру»


def shot_v3():
    n = SHOTS["v3"]
    ex = -0.4
    sc, cam, tgt = scene(n, ex, lens=LENS_CUT)
    world = C.empty("WORLD", coll="Star")
    key_scale(world, v3_scale, 1, n)
    p_end = V2_POSE(SHOTS["v2"], SHOTS["v2"])                  # поза конца v2
    key_path(cam, tgt, 1, n, lambda f: cut_cam_pose(az_off=p_end["az_off"] + 4.0 * f / n,
                                                     el=p_end["el"] + 1.5 * f / n,
                                                     aim_drop=0.06 * (1.0 - smooth(f / 120.0))))
    stars = cut_sky(sc, cam, ex)
    cut = cutaway(world)
    SL.key_values(cut, "flow", [(1, 0.6), (n, 0.95)], ipo="LINEAR")
    core = cut["core"]
    rfe = SY.layer_radii()[0]
    for f in list(range(1, n + 1, 2)) + [n]:
        s = v3_core_r(f) / rfe
        core.scale = (s, s, s)
        core.keyframe_insert("scale", frame=f)
    A.set_interpolation(core, "LINEAR", path_contains="scale")
    SL.key_values(cut, "hot", [(1, 0.35), (V3_COL0, 0.5), (V3_COL1 - 10, 1.0), (V3_COL1 + 4, 3.0), (n, 1.2)],
                  which=["Fe"])
    # отскок: пузырь ударной волны (до ~150 км и стоит) и нейтринный всплеск сквозь камеру
    rns = SY.PNS_R_KM / SY.CUT_UNIT_KM
    bub = SH.build_shell("Bounce", radius=rns, color=(1.0, 0.85, 0.6), color_edge=(0.6, 0.55, 1.0), strength=0.0,
                         rim_power=2.5, face_floor=0.05, noise_scale=4.0, noise_amp=0.8, seed=4, parent=world)
    SH.key_radius(bub, lambda f: rns if f < V3_BOUNCE else rns + 0.12 * (1 - math.exp(-(f - V3_BOUNCE) / 25.0)),
                  1, n, step=2)
    SH.key_strength(bub, [(V3_BOUNCE - 1, 0.0), (V3_BOUNCE + 3, 30.0), (V3_BOUNCE + 60, 9.0), (n, 6.0)])
    # нейтрино: поток игл, головы разбросаны (lag) — всё время что-то летит через кадр и мимо камеры
    nu = BU.build_burst("Nu", n=1300, r_min=rns, r_max=60.0, cam=cam, px=1.0, color=NU_RGB, strength=6.0,
                        trail=2.5, lag=45.0, seed=SY.SEEDS["nu"], parent=world, k=32)
    BU.key_head(nu, [(V3_BOUNCE, 0.0), (n, 45.0)])            # излучение идёт секундами: головы всё время у центра
    event("v3", "bounce", [V3_BOUNCE])
    S.finish(sc, stars, denoise="far", star_samples=16)
    return sc, n


# v4: нейтрино уходят, ударная волна ползёт сквозь слои
V4_NU0, V4_NU_EXIT = 20, 110                      # всплеск нейтрино: старт и выход за звезду
V4_BREAK = 440


def v4_shock(f):
    radii = SY.layer_radii()
    if f < 60:
        return 0.0
    if f < 120:
        return exp_lerp(0.15, radii[-2], (f - 60) / 60.0)                 # ядро → край гелия, ~минуты
    u = (f - 120) / (V4_BREAK - 120)
    return lerp(radii[-2], radii[-1] * 1.002, 0.3 * smooth(u) + 0.7 * u)  # водородная оболочка, ~2 ч


def shot_v4():
    n = SHOTS["v4"]
    ex = -0.4
    sc, cam, tgt = scene(n, ex, lens=LENS_CUT)
    world = C.empty("WORLD", coll="Star")
    s = 2.3 / SY.layer_radii()[-1]
    world.scale = (s, s, s)
    key_path(cam, tgt, 1, n, lambda f: cut_cam_pose(az_off=lerp(-28.0, -20.0, f / n), el=lerp(22.0, 26.0, f / n),
                                                     D=lerp(D_CUT, D_CUT * 0.93, smooth(f / n)), aim_drop=0.07))
    stars = cut_sky(sc, cam, ex, look=-cut_dir(-24.0, 24.0))
    cut = cutaway(world)
    star_glow(world, cam, SY.layer_radii()[-1])
    SL.key_values(cut, "flow", [(1, 0.95), (n, 1.6)], ipo="LINEAR")
    ST.key_value(None, "flow", [(1, FLOW0 + 0.4), (n, FLOW0 + 0.9)], ipo="LINEAR", mat=cut["photo"])
    rs = SY.layer_radii()
    SL.key_values(cut, "shock", [(f, v4_shock(f)) for f in range(1, n + 1, 2)], ipo="LINEAR")
    SL.key_values(cut, "shock_amp", [(58, 0.0), (68, 1.0), (V4_BREAK, 1.0), (n, 0.6)])
    cut["core"].hide_render = True                                         # ядро уже стало нейтронной звездой
    nu = BU.build_burst("Nu4", n=1400, r_min=0.0, r_max=rs[-1] * 2.4, cam=cam, px=0.9, color=NU_RGB,
                        strength=6.0, trail=rs[-1] * 0.12, lag=rs[-1] * 0.25, seed=SY.SEEDS["nu"] + 1,
                        parent=world, k=32)
    BU.key_head(nu, [(V4_NU0, 0.0), (V4_NU_EXIT + 40, rs[-1] * 2.8)])
    BU.key_strength(nu, [(1, 6.0), (V4_NU_EXIT + 30, 6.0), (V4_NU_EXIT + 50, 0.0)])
    # выход ударной волны на поверхность: вспышка фотосферы (front — от точки на краю ко всему диску)
    pm = cut["photo"].node_tree
    key_values(pm, "front", [(V4_BREAK - 4, 0.0), (V4_BREAK + 14, 1.0)])
    key_values(pm, "flash", [(V4_BREAK - 4, 0.0), (V4_BREAK + 4, 16.0), (n, 6.0)])
    # выход на поверхность: из звезды вырывается огненная оболочка и искры (рифма с холодным стартом v1)
    R = rs[-1]
    sh = SS.build_shell_nebula("Blast4", radius=R, seed=SY.SEEDS["ej"] + 5, palette=SS.FIRE, radial=0.7,
                               fil_scale=(1.8, 4.5), sharp=16.0, step=0.07, glow=0.0, hot=1.0, haze=0.3, thick=0.12,
                               inner=0.0, cover=0.45, parent=world)
    SS.key_radius(sh, lambda f: R * (1.0 + 0.45 * smooth((f - V4_BREAK) / (n - V4_BREAK))), 1, n, step=2)
    SS.key_value(sh, "glow", [(V4_BREAK, 0.0), (V4_BREAK + 8, 40.0 / (R * s)), (n, 22.0 / (R * s))])
    ST.key_visible(sh["ob"], [(1, False), (V4_BREAK, True)])
    sp = BU.build_burst("Sparks4", n=900, r_min=R * 0.98, r_max=R * 2.6, cam=cam, px=0.7, color=(1.0, 0.70, 0.30),
                        strength=9.0, trail=R * 0.05, lag=R * 0.6, amp=(0.15, 1.0), seed=SY.SEEDS["ej"] + 6,
                        parent=world, k=20)
    BU.key_head(sp, [(V4_BREAK, R * 0.98), (n, R * 2.4)])
    BU.key_strength(sp, [(V4_BREAK, 0.0), (V4_BREAK + 6, 9.0), (n, 7.0)])
    event("v4", "nu_exit", [V4_NU_EXIT])
    event("v4", "breakout", [V4_BREAK])
    S.finish(sc, stars, denoise="far", star_samples=16)
    return sc, n


# ================================================================ v5: Kamiokande-II
V5_T0 = 1.5                                         # первое событие — на 1.5 с шота
V5_FF = 3.0                                         # после 2 с всплеска — ускорение ×3


def kii_shot_time(t):
    return V5_T0 + (t if t <= 2.0 else 2.0 + (t - 2.0) / V5_FF)


def kii_frames():
    return [int(round(kii_shot_time(e["t"]) * 60.0)) + 1 for e in SY.kii_events()]


def _pmt_positions():
    """Центры ФЭУ: стена (ряды по высоте, шахматно), крышка и дно (квадратная сетка в круге); нормаль внутрь."""
    out = []
    Rt, H, p = SY.TANK_R_M, SY.TANK_H_M, SY.PMT_PITCH_M
    nphi = int(2 * math.pi * Rt / p)
    nz = int(H / p)
    for k in range(nz):
        z = -H / 2 + p * (k + 0.5)
        for j in range(nphi):
            a = 2 * math.pi * (j + 0.5 * (k % 2)) / nphi
            out.append((Vector((Rt * math.cos(a), Rt * math.sin(a), z)), Vector((-math.cos(a), -math.sin(a), 0))))
    m = int(Rt / p)
    for zz, nn in ((H / 2, Vector((0, 0, -1))), (-H / 2, Vector((0, 0, 1)))):
        for i in range(-m, m + 1):
            for j in range(-m, m + 1):
                x, y = i * p, j * p
                if x * x + y * y < (Rt - 0.6) ** 2:
                    out.append((Vector((x, y, zz)), nn))
    return out


def _pmt_material(events, strength=40.0):
    """Стекло ФЭУ (бронзовый фотокатод под колпаком) + вспышка: для события k — кольцо под углом Черенкова от
    вершины v_k вокруг направления d_k, по центру ФЭУ (атрибут ctr, весь колпак светится целиком); амплитуда — узел e<k>."""
    mat, N, L, out = C.new_material("PMT")
    b = _NB(mat.node_tree)
    ctr = b.node("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name="ctr").outputs["Vector"]
    tot = None
    cth = math.cos(math.radians(SY.CHERENKOV_DEG))
    for k, e in enumerate(events):
        w = b.v("NORMALIZE", b.v("SUBTRACT", ctr, tuple(e["v"])))
        c = b.v("DOT_PRODUCT", w, tuple(e["d"]))
        x = b.m("DIVIDE", b.m("SUBTRACT", c, cth), 0.032)
        ring = b.m("EXPONENT", b.m("MULTIPLY", b.m("MULTIPLY", x, x), -1.0))
        inner = b.m("MULTIPLY", b.ss(c, cth, cth + 0.15), 0.07)            # слабая засветка внутри кольца
        a = b.node("ShaderNodeValue", name=f"e{k}", label=f"e{k}")
        a.outputs[0].default_value = 0.0
        term = b.m("MULTIPLY", b.m("ADD", ring, inner), b.m("MULTIPLY", a.outputs[0], e["amp"]))
        tot = term if tot is None else b.m("ADD", tot, term)
    bs = b.node("ShaderNodeBsdfPrincipled", {"Base Color": (0.42, 0.26, 0.10, 1.0), "Metallic": 0.55,
                                             "Roughness": 0.18, "Coat Weight": 1.0, "Coat Roughness": 0.03})
    em = b.node("ShaderNodeEmission", {"Color": (0.62, 0.80, 1.0, 1.0), "Strength": b.m("MULTIPLY", tot, strength)})
    add = b.node("ShaderNodeAddShader", {0: bs.outputs[0], 1: em.outputs[0]})
    L.new(add.outputs[0], out.inputs["Surface"])
    mat.cycles.emission_sampling = "NONE"
    return mat


def _cyl(name, r, h, seg, inward=False, caps=True):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=caps, cap_tris=False, segments=seg, radius1=r, radius2=r, depth=h)
    if inward:
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me


def build_tank(events, frames):
    Rt, H = SY.TANK_R_M, SY.TANK_H_M
    # ФЭУ — колпаки (полусферы от стены внутрь), один меш с атрибутом центра. Без bmesh: сотни create_uvsphere в
    # один bmesh со своим слоем роняют Blender 5.2 (access violation) — шаблон колпака и копии через from_pydata
    nu_, nv_ = 18, 6
    tv = [(0.0, 0.0, SY.PMT_R_M * 0.85)]
    for i in range(1, nv_ + 1):
        th = 0.5 * math.pi * i / nv_
        for j in range(nu_):
            a = 2.0 * math.pi * j / nu_
            tv.append((SY.PMT_R_M * math.sin(th) * math.cos(a), SY.PMT_R_M * math.sin(th) * math.sin(a),
                       SY.PMT_R_M * math.cos(th) * 0.85))
    tf = [(0, 1 + j, 1 + (j + 1) % nu_) for j in range(nu_)]
    for i in range(nv_ - 1):
        r0, r1 = 1 + i * nu_, 1 + (i + 1) * nu_
        tf += [(r0 + j, r1 + j, r1 + (j + 1) % nu_, r0 + (j + 1) % nu_) for j in range(nu_)]
    verts, faces, ctr = [], [], []
    for p, nrm in _pmt_positions():
        q = (Quaternion((1.0, 0.0, 0.0), math.pi) if nrm.z < -0.999 else
             Quaternion() if nrm.z > 0.999 else Vector((0, 0, 1)).rotation_difference(nrm))
        base = len(verts)
        c = p + nrm * 0.1
        for co in tv:
            verts.append(tuple(q @ Vector(co) + p))
            ctr.extend(c)
        faces += [tuple(base + k for k in f) for f in tf]
    me = bpy.data.meshes.new("PMTs")
    me.from_pydata(verts, [], faces)
    at = me.attributes.new("ctr", "FLOAT_VECTOR", "POINT")
    at.data.foreach_set("vector", ctr)
    me.update()
    me.shade_smooth()
    me.materials.append(_pmt_material(events))
    pm = bpy.data.objects.new("PMTs", me)
    C.link(pm, "Tank")
    # стены: чёрный пластик изнутри цилиндра
    wme = _cyl("TankWall", Rt + 0.05, H + 0.1, 128, inward=True)
    wm, N, L, out = C.new_material("TankWall")
    bw = _NB(wm.node_tree)
    tc = bw.node("ShaderNodeTexCoord")
    nz = bw.noise(tc.outputs["Object"], 3.0, detail=2.0).outputs["Fac"]
    bs = bw.node("ShaderNodeBsdfPrincipled", {"Base Color": (0.012, 0.013, 0.016, 1.0),
                                              "Roughness": bw.lin(nz, 0.3, 0.7, 0.35, 0.6)})
    L.new(bs.outputs[0], out.inputs["Surface"])
    wme.materials.append(wm)
    C.link(bpy.data.objects.new("TankWall", wme), "Tank")
    # вода: слабое поглощение (красное гаснет, дальняя стена синеет)
    vme = _cyl("Water", Rt - 0.35, H - 0.7, 64)
    vm, N, L, out = C.new_material("Water")
    ab = N.new("ShaderNodeVolumeAbsorption")
    ab.inputs["Color"].default_value = (0.55, 0.85, 0.95, 1.0)
    ab.inputs["Density"].default_value = 0.06
    L.new(ab.outputs[0], out.inputs["Volume"])
    try:
        vm.cycles.homogeneous_volume = True
    except AttributeError:
        pass
    vme.materials.append(vm)
    C.link(bpy.data.objects.new("Water", vme), "Tank")
    # черенковские конусы в воде: голубая вспышка от вершины, гаснет за ~8 кадров
    cones = []
    for k, e in enumerate(events):
        Lc = 4.5
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=False, cap_tris=False, segments=48, radius1=0.0,
                              radius2=Lc * math.tan(math.radians(SY.CHERENKOV_DEG)), depth=Lc)
        for v in bm.verts:
            v.co.z += Lc / 2.0
        cme = bpy.data.meshes.new(f"Cone{k}")
        bm.to_mesh(cme)
        bm.free()
        cm, N, L, out = C.new_material(f"Cone{k}")
        bc = _NB(cm.node_tree)
        tc = bc.node("ShaderNodeTexCoord")
        z = bc.sep(tc.outputs["Object"])[2]
        a = bc.node("ShaderNodeValue", name="amp", label="amp")
        a.outputs[0].default_value = 0.0
        fall = bc.m("MULTIPLY", bc.m("POWER", bc.ss(z, Lc, 0.0), 2.0), bc.ss(z, 0.0, 0.3))
        em = bc.node("ShaderNodeEmission", {"Color": (0.40, 0.62, 1.0, 1.0),
                                            "Strength": bc.m("MULTIPLY", fall, bc.m("MULTIPLY", a.outputs[0], 0.6))})
        tr = bc.node("ShaderNodeBsdfTransparent")
        ad = bc.node("ShaderNodeAddShader", {0: em.outputs[0], 1: tr.outputs[0]})
        L.new(ad.outputs[0], out.inputs["Surface"])
        cm.cycles.emission_sampling = "NONE"
        cme.materials.append(cm)
        co = bpy.data.objects.new(f"Cone{k}", cme)
        C.link(co, "Tank")
        co.location = e["v"]
        co.rotation_mode = "QUATERNION"
        co.rotation_quaternion = (Vector((0, 0, 1)).rotation_difference(e["d"]) if e["d"].z > -0.999 else
                                  Quaternion((1.0, 0.0, 0.0), math.pi))
        co.visible_shadow = False
        co.visible_diffuse = co.visible_glossy = False
        cones.append(co)
    # ключи вспышек (событие ниже порога анализа — тусклее)
    nt = pm.data.materials[0].node_tree
    for k, (e, f) in enumerate(zip(events, frames)):
        peak = 0.45 if e["skip"] else 1.0
        key_values(nt, f"e{k}", [(f - 1, 0.0), (f + 1, peak), (f + 6, 0.3 * peak), (f + 22, 0.0)])
        key_values(cones[k].data.materials[0].node_tree, "amp", [(f - 1, 0.0), (f + 1, peak), (f + 5, 0.0)])
    return pm, cones


def shot_v5():
    n = SHOTS["v5"]
    ex = 0.6
    sc, cam, tgt = scene(n, ex, samples=16, comp=dict(COMP, vignette=0.38), lens=18.0,
                         clip=(0.05, 200.0))
    wd = sc.world or bpy.data.worlds.new("World")
    sc.world = wd
    wd.use_nodes = True
    bg = wd.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs["Strength"].default_value = 0.0
    Rt, H = SY.TANK_R_M, SY.TANK_H_M
    key_path(cam, tgt, 1, n, lambda f: (Vector((0.0, -Rt + 1.6, -H / 2 + 2.0 + 1.0 * smooth(f / n))),
                                       Vector((0.4 * f / n, Rt, lerp(1.2, 1.8, f / n)))))
    cam.data.dof.use_dof = True
    cam.data.dof.focus_distance = 9.0
    cam.data.dof.aperture_fstop = 5.6
    events = SY.kii_events()
    frames = kii_frames()
    build_tank(events, frames)
    # рабочий свет сверху (условность: в работе бак тёмный) — колпаки ФЭУ читаются бликами
    ld = bpy.data.lights.new("TopLight", "AREA")
    ld.energy = 900.0
    ld.size = 10.0
    ld.color = (0.75, 0.85, 1.0)
    lt = bpy.data.objects.new("TopLight", ld)
    C.link(lt, "Lights")
    lt.location = (0, 0, H / 2 - 0.6)
    # нейтрино снизу сквозь Землю: параллельные иглы из-под пола (центр «всплеска» в 2 км по направлению на SN)
    sdir = SY.sn_dir_local()
    far = 2000.0
    rnd = random.Random(SY.SEEDS["nu"] + 5)
    dirs = [(-sdir + Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1))) * (Rt * 1.1 / far))
            .normalized() for _ in range(420)]
    nu = BU.build_burst("NuRain", n=len(dirs), dirs=dirs, r_min=far - 30.0, r_max=far + 30.0, cam=cam, px=0.8,
                        color=NU_RGB, strength=3.0, trail=2.5, lag=60.0, seed=SY.SEEDS["nu"] + 5,
                        location=tuple(sdir * far), k=24)
    BU.key_head(nu, [(1, far - 25.0), (n, far + 95.0)])
    BU.key_strength(nu, [(1, 0.0), (40, 3.0), (frames[-1] + 40, 3.0), (n, 1.0)])
    event("v5", "nu", [f for f, e in zip(frames, events) if not e["skip"]])
    R.setup_volume_denoise(sc, "far")
    sc.cycles.transparent_max_bounces = 24
    return sc, n


# ================================================================ v6–v7: остаток «с Земли»
V6_S = 0.62 / SY.ER_A                              # ER: поперечник ≈ 0.34 ширины кадра, внешние кольца — в кадре
LIGHT_F = 45
YEAR0, YEAR1 = 1987.15, 2016.0


V6_Y94 = 260                                      # кадр v6, где 1994.5: дальше годы идут ровно (удар о кольцо — под фразу)


def v6_year(f):
    if f < V6_Y94:
        return lerp(YEAR0, 1994.5, smooth((f - LIGHT_F) / (V6_Y94 - LIGHT_F)) if f > LIGHT_F else 0.0)
    return lerp(1994.5, YEAR1, min((f - V6_Y94) / (580 - V6_Y94), 1.0))


def ring_fade(y):
    """Свечение пятен и кольца: растёт до ~2009, потом кольцо тускнеет (Fransson 2015, Rosu 2024)."""
    return 1.0 if y <= SY.HOT_PEAK else max(0.45, 1.0 - 0.035 * (y - SY.HOT_PEAK))


def ej_frac_of_year(y):
    """Внешний край яркого выброса / радиус ER: гомологично ∝ (y − 1987), к 2024 — EJ_FRAC_2024."""
    return 0.0 if y <= 1987.0 else SY.EJ_FRAC_2024 * min((y - 1987.0) / 37.0, 1.0)


def remnant(parent, n, year_of_f, glow_of_f, scale_of_f):
    """Три кольца, горячие точки, выброс, соседние звёзды 2 и 3 — в ед. R★ под parent (WORLD). Яркость объёмов
    компенсирована на масштаб мира (путь луча в объёме ∝ scale)."""
    M = SY.ring_basis()
    eul = M.to_euler("XYZ")
    a = SY.ER_A
    nrm = M.col[2]
    er = RG.build_ring("ER", a=a, width=0.055 * a, thick=0.035 * a, strength=22.0, seed=SY.SEEDS["ring"],
                       clumps=9.0, step=0.04, rotation=eul, parent=parent)
    outer = []
    for nm, k, inc, sg, sd in (("NOR", SY.OR_SCALE[0], SY.OR_INCL[0], 1.0, SY.SEEDS["or_n"]),
                               ("SOR", SY.OR_SCALE[1], SY.OR_INCL[1], -1.0, SY.SEEDS["or_s"])):
        ao = a * k
        rg = RG.build_ring(nm, a=ao, width=0.028 * ao, thick=0.022 * ao, color=(1.0, 0.18, 0.55),
                           edge_color=(0.75, 0.30, 1.0), strength=3.2, seed=sd, clumps=7.0, step=0.03,
                           location=tuple(nrm * a * SY.OR_OFFSET * sg),
                           rotation=SY.ring_basis(incl_deg=inc).to_euler("XYZ"), parent=parent)
        outer.append(rg)
    orn, ors = outer
    s_ref = V6_S
    gk = [(f, glow_of_f(f) * s_ref / scale_of_f(f)) for f in range(1, n + 1, 4)]
    for rg in (er, orn, ors):
        RG.key_value(rg, "glow", gk, ipo="LINEAR")
        RG.key_value(rg, "flow", [(1, 0.0), (n, 0.25)], ipo="LINEAR")
    angs, yrs = SY.hot_spots()
    hs = RG.build_hotspots("HS", a=a, angles_deg=angs, times=yrs, size=0.035 * a, seed=SY.SEEDS["hot"],
                           rotation=eul, parent=parent, rise=0.8, decay=1.2, flare=1.4)
    RG.key_value(hs, "strength", [(1, 25.0)])
    RG.key_time(hs, [(f, year_of_f(f)) for f in range(1, n + 1, 2)])
    RG.key_value(hs, "fade", [(f, ring_fade(year_of_f(f))) for f in range(1, n + 1, 4)], ipo="LINEAR")
    # выброс внутри кольца — многоцветные нити (палитра «линий элементов», как композитные снимки остатков)
    ej = SS.build_shell_nebula("Ej", radius=1.0, seed=SY.SEEDS["ej"] + 1, palette=SS.CASA, radial=0.4,
                               fil_scale=(2.0, 5.0), sharp=12.0, stretch=(0.72, 0.72, 1.3), step=0.07, glow=0.0,
                               hot=0.0, haze=0.0, thick=0.3, inner=0.0, cover=0.42, parent=parent)
    ej["ob"].rotation_euler = (math.radians(12.0), math.radians(-18.0), 0.0)
    SS.key_radius(ej, lambda f: max(ej_frac_of_year(year_of_f(f)), 1e-5) * a, 1, n, step=2)
    SS.key_value(ej, "flow", [(1, 0.0), (n, 0.35)], ipo="LINEAR")
    # соседние звёзды 2 и 3 — в картинной плоскости, чуть дальше остатка
    neigh = []
    for nm, (e_, n_, T) in (("Star2", SY.STAR2), ("Star3", SY.STAR3)):
        ob = _glow_sphere(nm, a * 0.012, ST._norm_rgb(ST.blackbody_rgb(T), 1.3), 60.0, parent)
        ob.location = (SY.EAST * e_ + SY.NORTH * n_) * a + SY.VIEW_DIR * a * 0.6
        neigh.append(ob)
    return dict(er=er, orn=orn, ors=ors, hs=hs, ej=ej, neigh=neigh)


def _glow_sphere(name, r, color, strength, parent=None):
    """Эмиссионная сфера (звезда-точка); яркость — узел strength."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=r)
    bm.to_mesh(me)
    bm.free()
    mt, N, L, out = C.new_material(f"{name}_Mat")
    em = N.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1.0)
    k = N.new("ShaderNodeValue")
    k.name = k.label = "strength"
    k.outputs[0].default_value = strength
    L.new(k.outputs[0], em.inputs["Strength"])
    tr = N.new("ShaderNodeBsdfTransparent")                    # при нулевой яркости — невидима (не чёрный кружок)
    ad = N.new("ShaderNodeAddShader")
    L.new(em.outputs[0], ad.inputs[0])
    L.new(tr.outputs[0], ad.inputs[1])
    L.new(ad.outputs[0], out.inputs["Surface"])
    mt.cycles.emission_sampling = "NONE"
    me.materials.append(mt)
    ob = bpy.data.objects.new(name, me)
    C.link(ob, "FX")
    if parent is not None:
        ob.parent = parent
    ob.visible_shadow = False
    ob.visible_diffuse = ob.visible_glossy = False
    return ob


def core_glow(name, cam, color, strength=0.0, parent=None):
    """Сияние-спрайт ⟂ камере: яркость exp(−(ρ/0.45)²) (ρ — радиус диска), прозрачное; радиус — масштабом объекта."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, cap_tris=False, segments=64, radius=1.0)
    bm.to_mesh(me)
    bm.free()
    mt, N, L, out = C.new_material(f"{name}_Mat")
    b = _NB(mt.node_tree)
    tc = b.node("ShaderNodeTexCoord")
    rho = b.m("DIVIDE", b.v("LENGTH", tc.outputs["Object"]), 0.45)
    k = b.node("ShaderNodeValue", name="strength", label="strength")
    k.outputs[0].default_value = strength
    br = b.m("MULTIPLY", b.m("EXPONENT", b.m("MULTIPLY", b.m("MULTIPLY", rho, rho), -1.0)), k.outputs[0])
    em = b.node("ShaderNodeEmission", {"Color": (*color, 1.0), "Strength": br})
    tr = b.node("ShaderNodeBsdfTransparent")
    ad = b.node("ShaderNodeAddShader", {0: em.outputs[0], 1: tr.outputs[0]})
    L.new(ad.outputs[0], out.inputs["Surface"])
    mt.cycles.emission_sampling = "NONE"
    me.materials.append(mt)
    ob = bpy.data.objects.new(name, me)
    C.link(ob, "FX")
    if parent is not None:
        ob.parent = parent
    con = ob.constraints.new("COPY_ROTATION")
    con.target = cam
    ob.visible_shadow = False
    ob.visible_diffuse = ob.visible_glossy = ob.visible_transmission = ob.visible_volume_scatter = False
    return ob


SN_PT_R = 0.016                                     # «точка» сверхновой: радиус в мире (камера стоит) ≈ 4 px


def v6_scale(f, n=600):
    return V6_S * lerp(0.92, 1.12, smooth(f / n))


def shot_v6():
    n = SHOTS["v6"]
    ex = EX_E
    sc, cam, tgt = scene(n, ex, comp=COMP_PT)
    key_path(cam, tgt, 1, n, lambda f: earth_pose(D_E))
    world = C.empty("WORLD", coll="FX")
    key_scale(world, lambda f: v6_scale(f, n), 1, n, step=2)
    key_rot_z(world, lambda f: 25.0 * smooth((f - 1) / (n - 1)), 1, n)
    stars = earth_sky(sc, cam, ex)

    def ring_glow(f):
        if f < LIGHT_F + 40:
            return 0.0
        y = v6_year(f)
        return smooth((f - LIGHT_F - 40) / 150.0) * lerp(0.85, 1.25, smooth((y - 1995.0) / 14.0)) * ring_fade(y)

    rem = remnant(world, n, v6_year, ring_glow, lambda f: v6_scale(f, n))
    SS.key_value(rem["ej"], "glow", [(LIGHT_F, 0.0), (LIGHT_F + 60, 14.0), (n, 6.0)])
    SS.key_value(rem["ej"], "inner", [(LIGHT_F, 0.0), (LIGHT_F + 60, 0.8), (n, 0.3)])
    pt = _glow_sphere("SNPoint", SN_PT_R, (0.85, 0.90, 1.0), 3.0)
    key_values(pt.data.materials[0].node_tree, "strength",
               [(1, 3.0), (LIGHT_F - 2, 3.0), (LIGHT_F + 4, 900.0), (LIGHT_F + 40, 300.0), (200, 20.0), (300, 4.0)])
    event("v6", "light", [LIGHT_F])
    angs, yrs = SY.hot_spots()
    first = sorted(yrs)[:6]
    hf = sorted({min(range(1, n + 1), key=lambda f: abs(v6_year(f) - y)) for y in first})
    event("v6", "pearl", hf)
    S.finish(sc, [stars, *rem["neigh"], pt], denoise="far", star_samples=16)
    return sc, n


# v7: 2024 → перемотка → нырок в звезду (последний кадр = кадр 1 v1)
V7_NS = 120
V7_REW0, V7_REW1 = 300, 500                       # перемотка 2024 → 1987.3
V7_FLASH = 548                                    # вспышка «назад»: точка ярчает и уходит в звезду
V7_DIVE0 = 470


def v7_year(f):
    if f < V7_REW0:
        return lerp(YEAR1, 2024.2, smooth(f / 200.0))
    if f < V7_REW1:
        return lerp(2024.2, 1987.3, smooth((f - V7_REW0) / (V7_REW1 - V7_REW0)))
    return lerp(1987.3, 1986.9, min((f - V7_REW1) / (V7_FLASH - V7_REW1), 1.0))


def v7_scale(f, n=630):
    """Масштаб мира: наезд ×2 на остаток, затем нырок в звезду ×10⁵. Видимое расстояние до звезды D = D_E/s (R★):
    ln D = ln D_E + (ln D0 − ln D_E − c)·w(u) + c(1 − u), w = (1 − u)^p(1 + pu) — плавный старт и в конце та же
    скорость, что в начале v1 (0.2 R★ за 29 кадров): петля без рывка."""
    s0 = v6_scale(SHOTS["v6"])
    if f < V7_DIVE0:
        return s0 * lerp(1.0, 2.0, smooth(f / V7_DIVE0))
    u = (f - V7_DIVE0) / (n - V7_DIVE0)
    c = (0.2 / 29.0) / D_E * (n - V7_DIVE0)
    l0, l1 = math.log(D_E / (2.0 * s0)), math.log(D_E)
    p = 2.6
    w = (1.0 - u) ** p * (1.0 + p * u)
    return D_E / math.exp(l1 + (l0 - l1 - c) * w + c * (1.0 - u))


def shot_v7():
    n = SHOTS["v7"]
    sc, cam, tgt = scene(n, EX_E, comp=COMP_PT)
    key_path(cam, tgt, 1, n, lambda f: earth_pose(D_E))
    world = C.empty("WORLD", coll="FX")
    key_scale(world, lambda f: v7_scale(f, n), 1, n, step=1)
    key_rot_z(world, lambda f: 25.0 * (1.0 - smooth(f / 300.0)), 1, n)
    stars = earth_sky(sc, cam)
    a = SY.ER_A

    def ring_glow(f):
        y = v7_year(f)
        return 1.25 * smooth((y - 1987.4) / 3.0) * lerp(0.68, 1.0, smooth((y - 1995.0) / 14.0)) * ring_fade(y)

    rem = remnant(world, n, v7_year, ring_glow, lambda f: v7_scale(f, n))
    SS.key_value(rem["ej"], "glow", [(1, 6.0), (V7_REW0, 6.0), (V7_REW1 - 20, 14.0), (V7_REW1 + 20, 0.0)])
    SS.key_value(rem["ej"], "inner", [(1, 0.3), (V7_REW0, 0.3), (V7_REW1, 1.0), (V7_REW1 + 20, 0.0)])
    ST.key_visible(rem["ej"]["ob"], [(1, True), (V7_REW1 + 24, False)])
    for nb in rem["neigh"]:
        ST.key_visible(nb, [(1, True), (V7_DIVE0 + 60, False)])
    for k in ("er", "orn", "ors", "hs"):                   # до 1987 кольца тёмные; при нырке уходят за сферу неба
        ST.key_visible(rem[k]["ob"], [(1, True), (V7_DIVE0 + 40, False)])
    # вероятная нейтронная звезда (JWST 2024): компактное свечение в центре выброса
    ns = _glow_sphere("NSGlow", a * 0.008, (0.75, 0.85, 1.0), 0.0, world)
    key_values(ns.data.materials[0].node_tree, "strength",
               [(V7_NS - 10, 0.0), (V7_NS + 20, 40.0), (V7_REW0, 40.0), (V7_REW0 + 60, 0.0)])
    label("Lbl_NS", "likely neutron star\nJWST, 2024", Vector((0, 0, 0)), cam, n, px=32, off=(250, 330),
          parent=world, fade=(V7_NS + 10, V7_REW0 - 10))
    # вспышка «назад»: точка разгорается и уходит в звезду (звезда — уже до взрыва)
    pt = _glow_sphere("SNPoint", SN_PT_R, (0.85, 0.90, 1.0), 0.0)
    key_values(pt.data.materials[0].node_tree, "strength",
               [(V7_REW1 - 40, 0.0), (V7_FLASH - 30, 120.0), (V7_FLASH - 4, 900.0), (V7_FLASH + 2, 0.0)])
    st, _ = progenitor(n, lambda f: FLOW0 + FLOW_RATE * (f - n), cam, parent=world)
    ST.key_visible(st["glow"], [(1, False), (V7_FLASH - 2, True)])
    ST.key_visible(st["disk"], [(1, False), (V7_FLASH - 2, True)])
    event("v7", "ns", [V7_NS])
    event("v7", "rewind", [V7_REW0])
    event("v7", "unflash", [V7_FLASH])
    S.finish(sc, [stars, *rem["neigh"], pt], denoise="far", star_samples=16)
    return sc, n


BUILDERS = {"v1": shot_v1, "v2": shot_v2, "v3": shot_v3, "v4": shot_v4, "v5": shot_v5, "v6": shot_v6,
            "v7": shot_v7}


def draft(argv):
    """Черновой ролик на согласование до финала: `-- vN draft [pct=25] [samples=4] [step=6]` — каждый step-й кадр
    в out/<ep>/9x16/draft/<шот>/ (не в frames/: докачка финала не примет черновые кадры за готовые); кадр
    копируется в следующие step−1 (60/step к/с в 60-кадровой секвенции: монтаж и звук — как в финале)."""
    import shutil
    step = next((int(a[5:]) for a in argv if a.startswith("step=")), 6)
    argv = [a for a in argv if a != "draft" and not a.startswith("step=")]
    if not any(a.startswith("pct=") for a in argv):
        argv.append("pct=25")
    if not any(a.startswith("samples=") for a in argv):
        argv.append("samples=4")
    S.run(BUILDERS, out_dir=OUT, argv=argv)
    shot, n = argv[0], SHOTS[argv[0]]
    d = os.path.join(OUT, "draft", shot)
    R.render_sequence(d, 1, n, step=step)
    for f in range(1, n + 1, step):
        src = os.path.join(d, f"{f:04d}.png")
        for g in range(f + 1, min(f + step, n + 1)):
            dst = os.path.join(d, f"{g:04d}.png")
            if os.path.getsize(src) > 0 and not os.path.exists(dst):
                shutil.copyfile(src, dst)


if __name__ == "__main__":
    _argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if "draft" in _argv:
        draft(_argv)
    else:
        S.run(BUILDERS, out_dir=OUT)
