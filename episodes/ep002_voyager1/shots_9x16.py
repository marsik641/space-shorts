"""Эпизод 002 — Voyager 1: один световой день от Земли (18.11.2026, 10:16 UTC), вертикаль 1080×1920 60 fps.

    blender -b --factory-startup -P episodes/ep002_voyager1/shots_9x16.py -- <шот> [preview F,..] [pct=50] [samples=N] [outdir=DIR] [final] [save]

    preview F,..  — кадры превью (pct=50) в out/ep002_voyager1/9x16/previews/<шот>_fNNNN.png
    final         — PNG-секвенция out/ep002_voyager1/9x16/frames/<шот>/####.png с докачкой (tools/render_episode.sh)
    save          — .blend в out/ep002_voyager1/9x16/scenes/<шот>.blend
    Лог превью — в out/ep002_voyager1/9x16/logs/prev_<шот>.log (по нему tools/cues.py: строки EVENT).

Монтаж (кадры @60, склейки встык; время в ролике):
    v1  300  0–5 с     хук: Voyager 1 сбоку-сзади, медленный наезд; титры VOYAGER 1 + дата вехи (episode.json)
    v2  600  5–15 с    взгляд назад: из-за обода тарелки «восходит» Солнце (EVENT sunrise) — звезда −15.6, в 4° от
                       Ригеля; подписи THE SUN, ORION и выноска EARTH (Земля в 0.2–0.3° от Солнца, в блике)
    v3  690  15–26.5 с   карта, истинный масштаб: кольцо-фронт сигнала от Земли (логарифмическая шкала времени,
                       EVENT front_*); список времени света — титрами монтажа (episode.json) по кадрам EVENT
    v4  690  26.5–38 с   карта: путь Voyager 1 по JPL Horizons 1977 -> 18.11.2026 (нелинейная шкала: пролёты — первые
                       30 %), подписи вех (EVENT launch/jupiter/saturn/heliopause), кольцо-схема гелиопаузы через точку 2012 г.
    v5  760  38–50.7 с РИТЭГи крупно -> общий план аппарата -> Золотая пластинка (EVENT record); свет на камере
    v6  530  50.7–59.5 с облёт с солнечной стороны (Млечный Путь по ходу полёта) -> шаг до первого кадра v1 (петля)
Миры: крупные планы — 1 ед. = 1 м, оси = эклиптика J2000 (Солнце — SUN_DIR, реальное небо: GAL_ECL + Орион);
карта — 1 ед. = 1 а.е., повёрнута MAP_ROT (Земля -> Voyager вверх по кадру). Данные и масштабы — system.py.
SHOTS = episode.json -> edit[].frames (tools/check_episode.py).
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
sys.path.insert(0, HERE)

import bmesh
import bpy
from mathutils import Vector

from spacekit import anim as A
from spacekit import camera as CAM
from spacekit import core as C
from spacekit import lighting as LT
from spacekit import shot as S
from spacekit import sky as SKY
from spacekit.bodies import voyager as VG
from spacekit.fx import label as LB
from spacekit.fx import orbit_line as OL
from spacekit.fx import path_line as PLN
from spacekit.fx import shell as SH

import system as SY

EP = os.path.basename(HERE)
OUT = os.path.join(C.OUT, EP, "9x16")
S.OPT.update(fmt="9x16", fps=60)
LB.FONT = "C:/Windows/Fonts/bahnschrift.ttf"     # подписи в кадре — тем же шрифтом, что титры и субтитры
SHOTS = {"v1": 300, "v2": 600, "v3": 690, "v4": 690, "v5": 760, "v6": 530}

SD = SY.SUN_DIR
_Z = Vector((0, 0, 1))
SIDE = SD.cross(_Z).normalized()          # вправо в кадре, если смотреть на Солнце «головой» к северу эклиптики
UP = SIDE.cross(SD).normalized()
SUN_STRENGTH = 5.0
FILL_COLOR = (0.72, 0.82, 1.0)


def B(a, u=0.0, s=0.0):
    """Точка в базисе (на Солнце, вверх, вбок), м."""
    return SD * a + UP * u + SIDE * s


def D(u_deg, s_deg):
    """Направление: u — вверх, s — вбок (градусы) от направления на Солнце."""
    u, s = math.radians(u_deg), math.radians(s_deg)
    return (SD * math.cos(u) * math.cos(s) + UP * math.sin(u) + SIDE * math.sin(s) * math.cos(u)).normalized()


# ---------------------------------------------------------------- общие кирпичи крупных планов
def fill_light(direction, strength, name="Fill", angle=25.0):
    """Заполняющий свет (условность: в реальности теневая сторона почти чёрная) — с направления direction."""
    ld = bpy.data.lights.new(name, "SUN")
    ld.energy = strength
    ld.angle = math.radians(angle)
    ld.color = FILL_COLOR
    ob = bpy.data.objects.new(name, ld)
    C.link(ob, "Lights")
    ob.rotation_mode = "QUATERNION"
    ob.rotation_quaternion = Vector((0, 0, -1)).rotation_difference(-Vector(direction).normalized())
    return ob


def close_scene(n, exposure=0.0, samples=56, lens=35.0, bloom=0.6):
    """Крупный план аппарата. Против мерцания на движении камеры (замер на финальном качестве, эп. 002):
    56 spp и порог 0.02 (денойз стабильнее на складках MLI и решётках), Filter Glossy и clamp — блики жалюзи
    и позолоты не «искрят» от кадра к кадру."""
    sc = S.base_scene(n, exposure=exposure, samples=samples, adaptive=0.02, bloom_strength=bloom)
    sc.cycles.blur_glossy = 1.0
    sc.cycles.sample_clamp_indirect = 8.0
    cam, tgt = CAM.camera_rig("Cam", lens=lens, clip_start=0.05)
    return sc, cam, tgt


SUN_FLUX = 2.0e5 * 2.0 ** 2      # яркость × площадь видимой точки-Солнца (ореол как у сферы r=2 м с силой 2e5)
SUN_PX = 4.0                     # радиус точки-Солнца, пиксели финального кадра: при ~1 px доля покрытия пикселей
                                 # шумит от кадра к кадру (24–64 spp в слое звёзд без денойза) — ореол «дышит» ±5 %


def close_world(sc, cam, exposure, fill_dir=None, fill=0.0):
    """Небо (реальная ориентация + Орион), Voyager (тарелка на Землю), Солнце, заполняющий свет."""
    stars = SKY.build_sky(sc, cam, exposure, gal=SY.GAL_ECL, catalog=SKY.BRIGHT_ORION)
    vg = VG.build_voyager(sc, detail="close")
    VG.aim(vg, SY.EARTH_DIR, roll_deg=0.0)
    r_sun = SUN_PX * LB.pixel_angle(cam, sc) * 5000.0
    lamp, disk = LT.add_distant_sun("Sun", SD, strength=SUN_STRENGTH, star_dist=5000.0, star_radius=r_sun,
                                    star_strength=SUN_FLUX / r_sun ** 2)
    if fill_dir is not None and fill > 0:
        fill_light(fill_dir, SUN_STRENGTH * fill)
    return stars, vg, lamp, disk


# ---------------------------------------------------------------- v1: хук
V1_KEYS = [dict(loc=tuple(B(-1.2, 2.6, 8.4)), target=tuple(B(0.3, 0.25, -0.2)), lens=35),
           dict(loc=tuple(B(-0.3, 1.6, 5.8)), target=tuple(B(0.3, 0.15, -0.2)), lens=35)]
V1_FILL = B(-0.3, 0.6, 1.0)


def shot_v1():
    n = SHOTS["v1"]
    sc, cam, tgt = close_scene(n)
    CAM.key_camera(cam, tgt, [dict(frame=1, **V1_KEYS[0]), dict(frame=n, **V1_KEYS[1])], ipo="LINEAR")
    stars, vg, lamp, disk = close_world(sc, cam, 0.0, fill_dir=V1_FILL, fill=0.14)
    S.finish(sc, [stars, disk], star_samples=128)
    return sc, n


# ---------------------------------------------------------------- v2: взгляд назад — Солнце у Ориона
def shot_v2():
    n = SHOTS["v2"]
    sc, cam, tgt = close_scene(n, lens=40)
    # камера за тарелкой: Солнце сначала скрыто ободом, к ~1 с выходит из-за края, затем медленный дрейф
    c1, c2, c3 = B(-12.0, 1.35, 0.9), B(-12.0, 2.6, 1.2), B(-11.0, 3.4, 1.6)
    t1, t2 = D(6.0, -3.0) * 40.0, D(7.5, -3.5) * 40.0
    CAM.key_camera(cam, tgt, [dict(frame=1, loc=tuple(c1), target=tuple(c1 + t1)),
                              dict(frame=90, loc=tuple(c2), target=tuple(c2 + t1)),
                              dict(frame=n, loc=tuple(c3), target=tuple(c3 + t2))])
    stars, vg, lamp, disk = close_world(sc, cam, 0.0, fill_dir=B(-1.0, 0.3, 0.2), fill=0.025)
    # «восход»: момент выхода Солнца из-за обода (луч камера -> Солнце перестаёт задевать аппарат)
    rise = None
    for f in range(1, 200):
        sc.frame_set(f)
        hit, _, _, _, ob, _ = sc.ray_cast(bpy.context.evaluated_depsgraph_get(), cam.matrix_world.translation, SD)
        if not hit or ob.name.startswith("Sun"):
            rise = f
            break
    print(f"EVENT v2 sunrise: {rise}")
    # подписи на «бесконечности» (в 4 км по направлению)
    far = 4000.0
    lb_sun = LB.build_label("Lbl_Sun", "THE SUN", tuple(SD * far), cam, px=34, offset_px=(-93, -6),
                            color=(1.0, 0.92, 0.8), strength=2.5, align="RIGHT")
    # Земля в 0.2–0.3° от Солнца — внутри блика: выноска из блика к подписи
    eu, es = math.degrees(math.asin(SY.EARTH_DIR.dot(UP))), math.degrees(math.asin(SY.EARTH_DIR.dot(SIDE)))
    p0, p1 = D(eu - 0.45, es + 0.45) * far, D(eu - 1.7, es + 1.7) * far
    lead = PLN.build_path_line("Lead_Earth", [p0, p1], color=(0.6, 0.8, 1.0), strength=3.0, head=1.0,
                               trail=10.0, floor=1.0, cam=cam, px=1.6)
    lb_e = LB.build_label("Lbl_Earth", "EARTH", tuple(p1), cam, px=28, offset_px=(16, -6),
                          color=(0.6, 0.8, 1.0), strength=2.5, align="LEFT")
    belt = SKY.radec_to_gal([84.053], [-1.202])[0]
    lb_o = LB.build_label("Lbl_Orion", "ORION", tuple(_gal_dir(belt) * far), cam, px=30, offset_px=(0, 74),
                          color=(0.75, 0.82, 1.0), strength=2.0)
    for lb, f_in in ((lb_sun, 66), (lb_o, 150), (lb_e, 330)):
        LB.key_screen_size(lb, cam, 1, n, step=10)
        LB.key_fade(lb, 1.0, f_in=f_in, f_out=n - 30, length=24)
    PLN.key_head(lead, 0.0, 1.0, 318, 336)
    PLN.key_head(lead, 1.0, 0.0, n - 30, n - 8)       # гаснет вместе с подписями
    S.finish(sc, [stars, disk], star_samples=128)
    return sc, n


def _gal_dir(g):
    """Вектор галактической системы -> мир (эклиптика)."""
    from mathutils import Euler
    return Euler(SY.GAL_ECL, "XYZ").to_matrix() @ Vector(tuple(g))


# ---------------------------------------------------------------- карта: общие кирпичи
def map_root():
    root = C.empty("MapRoot", coll="FX")
    root.rotation_mode = "QUATERNION"
    root.rotation_quaternion = SY.MAP_ROT.to_quaternion()
    return root


def dot(name, loc, color, strength, parent, radius=1.0):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=1.0)
    bm.to_mesh(me)
    bm.free()
    mat, N, L, out = C.new_material(f"{name}_Mat")
    em = N.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1.0)
    em.inputs["Strength"].default_value = strength
    L.new(em.outputs[0], out.inputs["Surface"])
    mat.cycles.emission_sampling = "NONE"
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    C.link(ob, "FX")
    ob.parent = parent
    ob.location = tuple(loc)
    ob.scale = (radius,) * 3
    ob.visible_shadow = False
    ob.visible_diffuse = ob.visible_glossy = ob.visible_transmission = ob.visible_volume_scatter = False
    return ob


def key_dot_px(ob, cam, px, f0, f1, step=4):
    """Постоянный экранный радиус точки (px) при движении камеры."""
    sc = bpy.context.scene
    for f in list(range(f0, f1 + 1, step)) + [f1]:
        sc.frame_set(f)
        d = (cam.matrix_world.translation - ob.matrix_world.translation).length
        r = px * d * LB.pixel_angle(cam, sc)
        ob.scale = (r, r, r)
        ob.keyframe_insert("scale", frame=f)
    A.set_interpolation(ob, "LINEAR")
    sc.frame_set(f0)


def orbit_points(pid, n=720):
    """Эллипс планеты по оскулирующим элементам (а.е., эклиптика): n точек + замыкание."""
    el = SY.DATA["elements"][pid]
    R = (SY.Matrix.Rotation(math.radians(el["OM"]), 3, "Z") @ SY.Matrix.Rotation(math.radians(el["i"]), 3, "X")
         @ SY.Matrix.Rotation(math.radians(el["W"]), 3, "Z"))
    a, e = el["a"], el["e"]
    pts = []
    for k in range(n + 1):
        E = 2 * math.pi * k / n
        pts.append(R @ Vector((a * (math.cos(E) - e), a * math.sqrt(1 - e * e) * math.sin(E), 0.0)))
    return pts


def map_orbits(root, cam, f0, f1, px=1.4, strength=2.2, keep=None):
    """Орбиты планет — линии постоянной экранной толщины (GN по расстоянию каждой вершины до камеры)."""
    out = {}
    for pid, nm in SY.PLANETS.items():
        if keep and nm not in keep:
            continue
        out[nm] = PLN.build_path_line(f"Orb_{nm}", orbit_points(pid), color=(0.50, 0.70, 1.0), strength=strength,
                                      head=1.0, trail=10.0, floor=1.0, parent=root, cam=cam, px=px, sides=6)
    return out


def map_scene(n, lens):
    sc = S.base_scene(n, exposure=0.0, samples=16, adaptive=0.05, bloom_strength=0.5)
    sc.cycles.use_denoising = False          # только эмиссия и фон — шума нет, денойз съел бы тонкие линии
    cam, tgt = CAM.camera_rig("Cam", lens=lens, clip_start=0.001, clip_end=1.0e6)
    return sc, cam, tgt


def fmt_lt(hours):
    m = hours * 60.0
    if m < 60:
        return f"{m:.0f} MIN"
    h = int(m // 60)
    return f"{h} H {m - 60 * h:02.0f} MIN"


# ---------------------------------------------------------------- v3: фронт сигнала от Земли
V3_R0, V3_R1 = 0.12, SY.LIGHT_DAY_AU
V3_F_END = 540                               # кадр, когда фронт доходит до Voyager 1


def v3_radius(f):
    u = min(max((f - 1) / (V3_F_END - 1), 0.0), 1.0)
    return V3_R0 * (V3_R1 / V3_R0) ** u


def v3_frame_for(r):
    return 1 + (V3_F_END - 1) * math.log(r / V3_R0) / math.log(V3_R1 / V3_R0)


def shot_v3():
    n = SHOTS["v3"]
    sc, cam, tgt = map_scene(n, lens=30)
    root = map_root()
    E = SY.to_map(SY.EARTH_NOW)
    V = SY.to_map(SY.V1_NOW)
    # взгляд горизонтальный (⟂ линии Земля -> V1): кольцо, обращённое к камере, проходит через V1 точно;
    # азимут 30° — орбиты раскрыты (|h·n_экл| ≈ 0.56), Солнце у центра кадра, когда фронт его проходит
    view = Vector((math.cos(math.radians(30.0)), math.sin(math.radians(30.0)), 0.0))
    tan_h = 18.0 / 30.0                                      # tg половины вертикального угла (30 мм, 9:16)
    Y_E, Y_TOP = 0.34, 0.85                                  # Земля и верх кольца (в конце — Voyager 1), доли высоты
    keys = []
    for f in list(range(1, V3_F_END + 1, 10)) + [V3_F_END]:
        R = max(v3_radius(f), 1.3)                           # до ~f190 кадр стоит (Земля + Солнце), дальше отъезд
        H = R / (Y_TOP - Y_E)                                # высота кадра в а.е. на глубине Земли
        tz = E + Vector((0, 0, (0.5 - Y_E) * H))
        keys.append(dict(frame=f, loc=tuple(tz + view * (H / (2 * tan_h))), target=tuple(tz), lens=30))
    # после прихода фронта — медленный наезд на Voyager 1 (кадр ×0.78, центр к V1), без 2.5 с статики
    H_end = V3_R1 / (Y_TOP - Y_E)
    tz0 = E + Vector((0, 0, (0.5 - Y_E) * H_end))
    tz1 = tz0.lerp(V, 0.35)
    keys.append(dict(frame=n, loc=tuple(tz1 + view * (0.78 * H_end / (2 * tan_h))), target=tuple(tz1), lens=30))
    CAM.key_camera(cam, tgt, keys)
    A.set_interpolation(cam, "LINEAR")
    A.set_interpolation(tgt, "LINEAR")
    stars = SKY.build_sky(sc, cam, 0.0, gal=SY.GAL_MAP)
    map_orbits(root, cam, 1, n)
    sun = dot("Sun", (0, 0, 0), (1.0, 0.93, 0.8), 60.0, root)
    key_dot_px(sun, cam, 5.5, 1, n)
    earth = dot("Earth", SY.EARTH_NOW, (0.35, 0.6, 1.0), 40.0, root)
    key_dot_px(earth, cam, 4.8, 1, n)
    vgr = dot("Voyager", SY.V1_NOW, (1.0, 0.78, 0.4), 60.0, root)
    key_dot_px(vgr, cam, 4.8, 1, n)
    front = SH.build_ring("Front", cam, radius=V3_R0, location=tuple(SY.EARTH_NOW), color=(0.55, 0.85, 1.0),
                          strength=5.0, fill=0.0, parent=root)
    SH.key_ring(front, cam, v3_radius, 4.0, 1, n, step=3)
    SH.key_strength(front, [(1, 5.0), (150, 5.0), (175, 3.0)])     # после Солнца — тише: под дугой список титров
    # подписи: момент, когда фронт проходит тело (реальное время света от Земли)
    marks = [("SUN", Vector((0, 0, 0)), None)]
    for pid in ("599", "699", "899"):
        marks.append((SY.PLANETS[pid], SY.planet_at(pid, SY.MILESTONE_JD), pid))
    lbl_e = LB.build_label("Lbl_Earth", "EARTH", tuple(SY.EARTH_NOW), cam, px=30, offset_px=(38, 42), align="LEFT",
                           color=(0.6, 0.8, 1.0), strength=2.5, parent=root)
    LB.key_screen_size(lbl_e, cam, 1, n, step=6)
    LB.key_fade(lbl_e, 1.0, f_in=1, f_out=150, length=20)
    # подписи времени света — списком-титрами монтажа (episode.json, строки по EVENT ниже): внешние планеты
    # в момент прохода фронта за краем кадра, 3D-подпись к ним не привязать
    def screen_hit(p_ecl):
        """Кадр, когда кольцо на экране доходит до точки: луч камера -> точка ∩ плоскость кольца (через Землю)."""
        P, Em = SY.to_map(p_ecl), E
        for f in range(1, V3_F_END + 1):
            sc.frame_set(f)
            cm = cam.matrix_world
            c, fwd = cm.translation, -(cm.to_3x3() @ Vector((0, 0, 1)))
            t = (Em - c).dot(fwd) / max((P - c).dot(fwd), 1e-9)
            if (c + (P - c) * t - Em).length <= v3_radius(f):
                return f
        return V3_F_END
    for nm, p, pid in marks:
        hrs = SY.light_time_h(p, SY.EARTH_NOW)
        f_hit = screen_hit(p) if nm == "SUN" else int(round(v3_frame_for((p - SY.EARTH_NOW).length)))
        d = dot(f"P_{nm}", p, (0.8, 0.85, 0.95), 25.0, root) if pid else None
        if d is not None:
            key_dot_px(d, cam, 3.7, 1, n)
        print(f"EVENT v3 front_{nm.lower()}: {f_hit}")
        print(f"LT {nm} {fmt_lt(hrs)}")
    lb_v = LB.build_label("Lbl_V1", "VOYAGER 1", tuple(SY.V1_NOW), cam, px=32, offset_px=(32, 38), align="LEFT",
                          color=(1.0, 0.85, 0.6), strength=3.0, parent=root)
    LB.key_screen_size(lb_v, cam, 1, n, step=6)
    LB.key_fade(lb_v, 1.0, f_in=V3_F_END - 8, length=18)
    print(f"EVENT v3 front_voyager: {V3_F_END}")
    S.finish(sc, stars, star_samples=64)
    return sc, n


# ---------------------------------------------------------------- v4: путь 1977 -> 2026
def _dates_to_u(jd):
    """Нелинейная шкала: 1977-09 … 1981-01 (пролёты) — первые 30 % шота, дальше — равномерно до вехи."""
    j0, j1, j2 = SY.DATA["v1"][0][0], SY.jd_from_date(1981, 1, 1), SY.MILESTONE_JD
    if jd <= j1:
        return 0.30 * (jd - j0) / (j1 - j0)
    return 0.30 + 0.70 * (jd - j1) / (j2 - j1)


def shot_v4():
    n = SHOTS["v4"]
    sc, cam, tgt = map_scene(n, lens=30)
    root = map_root()
    f_draw0, f_draw1 = 20, n - 80
    # точки траектории: плотно у пролётов, t — доля шота по нелинейной шкале
    j0 = SY.DATA["v1"][0][0]
    pts, jds = SY.resample(SY.DATA["v1"], j0, SY.MILESTONE_JD, 1600)
    ts = [_dates_to_u(j) for j in jds]
    v1 = PLN.build_path_line("Traj_V1", pts, t=ts, color=(1.0, 0.72, 0.32), strength=8.0,
                             head=0.0, trail=0.06, floor=0.45, parent=root, cam=cam, px=2.4)
    PLN.key_head(v1, 0.0, 1.0, f_draw0, f_draw1)
    head = dot("V1Head", pts[0], (1.0, 0.85, 0.55), 80.0, root)
    PLN.key_follow(head, pts, 0.0, 1.0, f_draw0, f_draw1, t=ts, step=2)
    # камера: от внутренней системы (пролёты) к общему плану всего пути
    E = SY.to_map(SY.EARTH_NOW)
    Vm = SY.to_map(SY.V1_NOW)
    # азимут 120°: изломы у Юпитера (≈42°) и Сатурна (≈41°) оба видны на экране, |view·n_экл| ≈ 0.60;
    # при 30° (как в v3) поворот у Сатурна на экране всего ≈3° — а голос говорит именно про него
    view = Vector((math.cos(math.radians(120.0)), math.sin(math.radians(120.0)), 0.0))
    tan_h = 18.0 / 30.0

    def frame_of(jd):
        return f_draw0 + (f_draw1 - f_draw0) * _dates_to_u(jd)

    def k(f, center, H):
        """Ключ: центр кадра center, высота кадра H (а.е.) на его глубине."""
        return dict(frame=int(f), loc=tuple(center + view * (H / (2 * tan_h))), target=tuple(center), lens=30)

    def follow(f, y_head=0.78, y_sun=0.33):
        """Общий план: Солнце на y_sun, голова пути на y_head (доли высоты кадра)."""
        u = min(max((f - f_draw0) / (f_draw1 - f_draw0), 0.0), 1.0)
        zh = SY.to_map(PLN.point_at(pts, u, ts)).z
        H = zh / (y_head - y_sun)
        return k(f, Vector((0, 0, (0.5 - y_sun) * H)), H)
    jup = SY.to_map(Vector(SY.EVENTS["jupiter"]["pos"]))
    sat = SY.to_map(Vector(SY.EVENTS["saturn"]["pos"]))

    def hold(H, y_turn=0.55):
        """Поворот у Сатурна на y_turn высоты кадра (выше субтитров), по горизонтали — между Солнцем и Сатурном."""
        return Vector((sat.x * 0.6, sat.y * 0.6, sat.z + (0.5 - y_turn) * H))
    f_sat = frame_of(SY.EVENTS["saturn"]["jd_tdb"])
    f_hp = int(frame_of(SY.EVENTS["heliopause"]["jd_tdb"]))
    # внутренняя система держится, пока звучит «Saturn's gravity bent its path north» (путь уходит за верх кадра),
    # затем быстрый отъезд: к пересечению гелиопаузы виден весь путь
    keys = [k(1, E * 0.5, 14.0), k(frame_of(SY.EVENTS["jupiter"]["jd_tdb"]), jup * 0.5, 13.0),
            k(f_sat + 20, hold(19.0), 19.0), k(f_hp - 110, hold(24.0), 24.0),
            follow(f_hp), follow((f_hp + f_draw1) // 2), follow(f_draw1), follow(n)]
    CAM.key_camera(cam, tgt, keys)
    stars = SKY.build_sky(sc, cam, 0.0, gal=SY.GAL_MAP)
    map_orbits(root, cam, 1, n, keep=("EARTH", "JUPITER", "SATURN", "URANUS", "NEPTUNE"))
    sun = dot("Sun", (0, 0, 0), (1.0, 0.93, 0.8), 60.0, root)
    key_dot_px(sun, cam, 5.5, 1, n)
    key_dot_px(head, cam, 5.9, 1, n)
    # гелиопауза (схема): кольцо вокруг Солнца, проходящее через точку пересечения 2012 г. в проекции на кадр
    p_hp = SY.to_map(Vector(SY.EVENTS["heliopause"]["pos"]))
    radii = {}
    for f in range(1, n + 1, 6):
        sc.frame_set(f)
        cm = cam.matrix_world
        c, fwd = cm.translation, -(cm.to_3x3() @ Vector((0, 0, 1)))
        t = -c.dot(fwd) / max((p_hp - c).dot(fwd), 1e-9)          # плоскость кольца — через Солнце, ⟂ оси камеры
        radii[f] = (c + (p_hp - c) * t).length
    sc.frame_set(1)
    hp = SH.build_ring("Heliopause", cam, radius=radii[1], color=(0.35, 0.55, 1.0), strength=0.0, fill=0.02,
                       fill_power=12.0, parent=None)
    SH.key_ring(hp, cam, lambda f: radii[min(radii, key=lambda k: abs(k - f))], 3.3, 1, n, step=6)
    f_hp = int(frame_of(SY.EVENTS["heliopause"]["jd_tdb"]))
    SH.key_strength(hp, [(1, 0.0), (f_hp - 60, 0.0), (f_hp - 10, 3.0), (n, 2.2)])
    # подписи вех
    ev = SY.EVENTS
    marks = [("launch", "1977 · LAUNCH", (38, -13), "LEFT"), ("jupiter", "1979 · JUPITER", (38, 0), "LEFT"),
             ("saturn", "1980 · SATURN", (-38, 13), "RIGHT"), ("heliopause", "2012 · INTERSTELLAR SPACE", (0, 54), "CENTER")]
    for key, text, off, al in marks:
        jd = ev[key].get("launch_jd_tdb", ev[key]["jd_tdb"]) if key == "launch" else ev[key]["jd_tdb"]
        f_hit = int(frame_of(jd))
        lb = LB.build_label(f"Lbl_{key}", text, tuple(ev[key]["pos"]), cam, px=30, offset_px=off, align=al,
                            color=(1.0, 0.88, 0.7), strength=2.5, parent=root)
        LB.key_screen_size(lb, cam, 1, n, step=6)
        life = {"launch": 130, "jupiter": 70, "saturn": 150}.get(key, f_draw1 - 22 - f_hit)
        LB.key_fade(lb, 1.0, f_in=max(1, f_hit - 4), f_out=min(n - 25, f_hit + life), length=16)
        print(f"EVENT v4 {key}: {f_hit}")
    lb_now = LB.build_label("Lbl_now", "2026 · 1 LIGHT-DAY FROM EARTH", tuple(SY.V1_NOW), cam, px=32,
                            offset_px=(0, 64),
                            color=(1.0, 0.85, 0.6), strength=3.0, parent=root)
    LB.key_screen_size(lb_now, cam, 1, n, step=6)
    LB.key_fade(lb_now, 1.0, f_in=f_draw1 - 6, length=16)
    S.finish(sc, stars, star_samples=64)
    return sc, n


# ---------------------------------------------------------------- v5: «машина» крупно
def camera_softbox(cam, power=18.0, size=2.0, offset=(0.35, 0.45, 0.6)):
    """Мягкий свет на камере (условность «продуктовой» съёмки): металл пластинки отражает его, а не чёрное небо."""
    ld = bpy.data.lights.new("Softbox", "AREA")
    ld.energy = power
    ld.size = size
    ld.color = (1.0, 0.96, 0.9)
    ob = bpy.data.objects.new("Softbox", ld)
    C.link(ob, "Lights")
    ob.parent = cam
    ob.location = offset
    return ob


def shot_v5():
    n = SHOTS["v5"]
    sc, cam, tgt = close_scene(n, lens=35)
    stars, vg, lamp, disk = close_world(sc, cam, 0.0)
    W = lambda p: tuple(VG.world_point(vg, p))
    # точки модели: РИТЭГи (AZ_RTG), шина, пластинка (AZ_RECORD)
    a_rec = math.radians(VG.AZ_RECORD)
    n_rec = Vector((math.cos(a_rec), math.sin(a_rec), 0.0))
    t_rec = Vector((-n_rec.y, n_rec.x, 0.0))
    rec = n_rec * (VG.BUS_ACROSS / 2.0)
    rtg = Vector((-2.6, 0.0, -0.5))

    def pol(az, r, z):
        return Vector((r * math.cos(math.radians(az)), r * math.sin(math.radians(az)), z))
    # РИТЭГи крупно -> отъезд на общий план (весь аппарат) -> наезд на Золотую пластинку (az 72°)
    keys = [dict(frame=1, loc=W(pol(206, 3.4, 0.45)), target=W(rtg + Vector((0.3, 0, 0))), lens=35),
            dict(frame=280, loc=W(pol(128, 8.6, -1.4)), target=W(Vector((-0.3, 0.0, 0.1))), lens=35),
            dict(frame=n, loc=W(rec + n_rec * 1.1 - t_rec * 0.25 + Vector((0, 0, -0.1))), target=W(rec), lens=35)]
    CAM.key_camera(cam, tgt, keys)
    # пластинка «в кадре»: центр в кадре и луч камера -> центр попадает в саму пластинку
    from bpy_extras.object_utils import world_to_camera_view
    rec_ob = vg["parts"]["record"]
    f_rec = n
    for f in range(240, n + 1, 5):
        sc.frame_set(f)
        c = cam.matrix_world.translation
        p = rec_ob.matrix_world.translation
        q = world_to_camera_view(sc, cam, p)
        n_w = (rec_ob.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized()
        if 0.1 < q.x < 0.9 and 0.2 < q.y < 0.85 and n_w.dot((c - p).normalized()) > 0.6 and (c - p).length < 3.5:
            hit, _, _, _, ob, _ = sc.ray_cast(bpy.context.evaluated_depsgraph_get(), c, (p - c).normalized())
            if hit and ob == rec_ob:
                f_rec = f
                break
    print(f"EVENT v5 record: {f_rec}")
    sc.frame_set(1)
    box = camera_softbox(cam)
    for f, w in ((1, 6.0), (150, 6.0), (240, 18.0)):     # на РИТЭГах — почти без софтбокса (они чёрные)
        box.data.energy = w
        box.data.keyframe_insert("energy", frame=f)
    # общий план снизу — силуэт в тени тарелки: заполняющий свет со стороны камеры (условность, как в v1/v6)
    sc.frame_set(280)
    fill_light(cam.matrix_world.translation - Vector(W(Vector((0, 0, 0)))), SUN_STRENGTH * 0.13)
    sc.frame_set(1)
    S.finish(sc, [stars, disk], star_samples=128)
    return sc, n


# ---------------------------------------------------------------- v6: облёт -> первый кадр v1 (петля)
def shot_v6():
    n = SHOTS["v6"]
    sc, cam, tgt = close_scene(n)
    k1 = V1_KEYS[0]
    # старт: с солнечной стороны сверху — за зондом ядро Млечного Пути (направление полёта), затем облёт к v1
    start = dict(loc=tuple(B(6.2, 5.2, -2.2)), target=tuple(B(-0.6, -0.9, 0.4)), lens=32)
    mid = dict(loc=tuple(B(2.2, 7.0, 4.2)), target=tuple(B(0.3, -0.1, 0.0)), lens=34)
    # последние TAIL кадров — прямая с той же скоростью, что у v1 (LINEAR): на шве петли нет остановки
    TAIL, n1 = 90, SHOTS["v1"]
    k2 = V1_KEYS[1]
    pre = {key: tuple(Vector(k1[key]) - (TAIL - 1) * (Vector(k2[key]) - Vector(k1[key])) / (n1 - 1))
           for key in ("loc", "target")}
    CAM.key_camera(cam, tgt, [dict(frame=1, **start), dict(frame=int(n * 0.5), **mid),
                              dict(frame=n + 1 - TAIL, lens=35, **pre), dict(frame=n + 1, **k1)])
    for idd in (cam, tgt):
        for fc in A.fcurves(idd):
            for kp in fc.keyframe_points:
                if int(round(kp.co.x)) >= n + 1 - TAIL:
                    kp.interpolation = "LINEAR"
    stars, vg, lamp, disk = close_world(sc, cam, 0.0, fill_dir=V1_FILL, fill=0.14)
    S.finish(sc, [stars, disk], star_samples=128)
    return sc, n


BUILDERS = {"v1": shot_v1, "v2": shot_v2, "v3": shot_v3, "v4": shot_v4, "v5": shot_v5, "v6": shot_v6}

if __name__ == "__main__":
    S.run(BUILDERS, out_dir=OUT)
