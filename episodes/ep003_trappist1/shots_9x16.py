"""Эпизод 003 — TRAPPIST-1, вертикаль 1080×1920 60 fps.

    blender -b --factory-startup -P episodes/ep003_trappist1/shots_9x16.py -- <шот> [preview F,..] [pct=50] [samples=N] [outdir=DIR] [final] [save]

Монтаж (кадры @60, склейки встык):
    v1  330  хук: «c-rise» — полная TRAPPIST-1c встаёт над лимбом b (b у терминатора), 240 мм,
             контур полной Луны с Земли в той же угловой мере (c шире в 2.4 раза)
    v2  632  схема сверху: 7 орбит прорисовываются, планеты-метки в ускоренном времени (1 сут = 2 с); линия «на Землю»;
             каждый транзит — вспышка метки и удар в музыке (EVENT transit)
    v3  688  (склейка на транзите, 16.03 с) звезда крупно рядом с контуром Юпитера → отъезд ×250 → вокруг системы рисуется орбита Меркурия
             (то же время, транзиты продолжаются)
    v4  720  TRAPPIST-1e: тонкий серп внизу (без атмосферы — не измерена), звезда над лимбом — поперёк неё встают 4 контура
             Солнца с Земли (звезда в 4.07 раза шире); затем облёт и отъезд к полуфазе: вечный терминатор
    v5  720  семь планет в ряд (взаимный масштаб честный, планеты не бросают тени друг на друга) + контур Земли
    v6  480  наезд к b: c опускается за лимб; следующий кадр — первый кадр v1 (бесшовная петля)
Крупные планы — реальные размеры, расстояния и реальное время; схемы — масштаб и время из system.py.
spacekit не меняется: всё недостающее — хелперы system.py.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
sys.path.insert(0, HERE)

from mathutils import Matrix, Quaternion, Vector

from spacekit import anim as A
from spacekit import camera as CAM
from spacekit import core as C
from spacekit import lighting as LT
from spacekit import orbits as ORB
from spacekit import shot as S
from spacekit import sky as SKY
from spacekit.fx import label as LB
from spacekit.fx import path_line as PLN
from spacekit.fx import shell as SH

import system as SY

EP = os.path.basename(HERE)
OUT = os.path.join(C.OUT, EP, "9x16")
S.OPT.update(fmt="9x16", fps=60)
LB.FONT = "C:/Windows/Fonts/corbel.ttf"          # подписи — шрифтом субтитров эпизода (Corbel)
SHOTS = {"v1": 330, "v2": 632, "v3": 688, "v4": 720, "v5": 720, "v6": 480}
FPS = 60

OUTLINE = (0.70, 0.86, 1.0)                      # контуры «для масштаба» и подписи к ним
ORBIT_COL = (1.0, 0.60, 0.36)
DOT_COL = {"b": (1.0, 0.55, 0.40), "c": (1.0, 0.70, 0.45), "d": (0.95, 0.85, 0.55), "e": (0.55, 0.95, 0.70),
           "f": (0.50, 0.85, 1.0), "g": (0.55, 0.70, 1.0), "h": (0.78, 0.68, 1.0)}


def smooth(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3.0 - 2.0 * u)


def lerp(a, b, s):
    return a + (b - a) * s


def rot_toward(v, w, ang_deg):
    """Повернуть направление v к w на ang_deg градусов (в плоскости v, w)."""
    axis = v.cross(w)
    if axis.length < 1e-12:
        return v.copy()
    return (Matrix.Rotation(math.radians(ang_deg), 3, axis.normalized()) @ v).normalized()


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


def cam_right(loc, target):
    fwd = (Vector(target) - Vector(loc)).normalized()
    return fwd.cross(Vector((0, 0, 1))).normalized()


def outline(name, cam, center, ang_deg, n, px=1.4, strength=2.4, cam_loc=None):
    """Контур «того же масштаба» (Луна, Солнце, Юпитер, Земля): кольцо, параллельное кадру. ang_deg — угловой
    диаметр из cam_loc (если задан), иначе радиус = ang_deg (мировые ед.)."""
    r = SY.ring_radius_for(cam_loc, center, ang_deg) if cam_loc is not None else ang_deg
    ring = SH.build_ring(name, cam, radius=r, location=tuple(center), color=OUTLINE, strength=strength, fill=0.0)
    SH.key_ring(ring, cam, lambda f: r, px, 1, n, step=6)
    return ring, r


def label(name, text, loc, cam, n, px=24, off=(0, 0), color=OUTLINE, strength=2.6, parent=None, step=6):
    lb = LB.build_label(name, text, tuple(loc), cam, px=px, offset_px=off, color=color, strength=strength,
                        parent=parent)
    LB.key_screen_size(lb, cam, 1, n, step=step)
    return lb


# ================================================================ v1 / v6: c над лимбом b
B = SY.pos("b", 0.0)
CC = SY.pos("c", 0.0)                            # b и c в соединении: c в противостоянии для b — диск полный
RB, RC = SY.R_MM["b"], SY.R_MM["c"]
LENS_BC = 240.0
VFOV_BC = math.degrees(2.0 * math.atan(18.0 / LENS_BC))
LIMB_Y = 0.35                                    # лимб b — на 35 % высоты кадра от низа (субтитры ниже)
GAL_BC = SKY.gal_for_view(Vector((1, 0, 0)), tilt_deg=32, l_center_deg=95)
V1_DELTA = (0.15, 2.8)                           # центр c над лимбом b, град: начало и конец v1
V1_D = 20.0                                      # расстояние камеры от центра b, Мм (высота ~12 900 км)


def bc_cam(D, alpha, beta=0.0):
    """Камера на расстоянии D от b: alpha — подъём над плоскостью орбит со стороны звезды, beta — азимут."""
    a, b = math.radians(alpha), math.radians(beta)
    return B + Vector((-math.cos(a) * math.cos(b), -math.cos(a) * math.sin(b), math.sin(a))) * D


def bc_delta(P):
    db = (B - P).normalized()
    dc = (CC - P).normalized()
    return math.degrees(db.angle(dc)) - math.degrees(math.asin(RB / (B - P).length))


def bc_pose(D, delta, beta=0.0):
    """Камера, при которой центр c на delta градусов над лимбом b; лимб — на LIMB_Y высоты кадра."""
    lo, hi = math.degrees(math.asin(RB / D)) - 2.0, 89.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if bc_delta(bc_cam(D, mid, beta)) < delta:
            lo = mid
        else:
            hi = mid
    P = bc_cam(D, 0.5 * (lo + hi), beta)
    db = (B - P).normalized()
    dc = (CC - P).normalized()
    th_l = math.degrees(math.asin(RB / (B - P).length))
    look = rot_toward(db, dc, th_l + (0.5 - LIMB_Y) * VFOV_BC)
    return P, P + look * 600.0


def bc_scene(n, ex):
    sc = S.base_scene(n, exposure=ex, samples=28, adaptive=0.03,    # 28 spp: шум как у 40 после денойза, −20 % времени
                      white_balance=SY.WB_K)
    cam, tgt = CAM.camera_rig("Cam", lens=LENS_BC, clip_start=0.05, clip_end=1.0e6)
    return sc, cam, tgt


def bc_world(sc, cam, n, ex):
    stars = SKY.build_sky(sc, cam, ex, gal=GAL_BC, star_brightness=0.9)
    _disk, lamp = SY.build_star(sc, light_irr=5.0)          # звезда за камерой: светит, в кадр не попадает
    SY.build_planet(sc, "b", n, lamp, detail="close", location=B, spin_deg=250.0)   # гигантские кратеры — не под субтитрами
    SY.build_planet(sc, "c", n, lamp, detail="mid", location=CC, spin_deg=40.0)
    return stars


def moon_outline(sc, cam, n, fade=None):
    """Контур полной Луны с Земли справа от c и чуть выше центра c (виден целиком, пока c встаёт): отношение
    диаметров в кадре = c с поверхности b / Луна (2.45). Положение и размер — от позы первого кадра v1
    (общие для v1 и конца v6: петля без скачка). fade=(f0, f1) — появление, иначе виден с кадра 1."""
    P, T = bc_pose(V1_D, V1_DELTA[0])
    c_cam = 2.0 * math.degrees(math.atan(RC / (CC - P).length))
    c_surf = 2.0 * math.degrees(math.atan(RC / ((CC - B).length - RB)))
    ang = SY.MOON_DEG * c_cam / c_surf
    r = (CC - P).length * math.tan(math.radians(ang) * 0.5)
    right = cam_right(P, T)
    up = right.cross((Vector(T) - P).normalized()).normalized()
    ctr = CC + right * (RC + 3.0 + r) + up * (RC * 0.9)
    ring, r = outline("MoonRing", cam, ctr, ang, n, cam_loc=P)
    px_r = math.degrees(math.atan(r / (ctr - P).length)) / math.degrees(LB.pixel_angle(cam, sc))
    lb = label("LblMoon", "Full Moon\nfrom Earth", ctr, cam, n, px=32, off=(0, -px_r - 62))
    if fade is not None:
        SH.key_strength(ring, [(1, 0.0), (fade[0], 0.0), (fade[1], 2.4)])
        LB.key_fade(lb, 1.0, f_in=fade[0], length=fade[1] - fade[0])
    print(f"V1 c from camera {c_cam:.3f} deg, from b surface {c_surf:.3f} deg, Moon ring {ang:.3f} deg "
          f"(ratio {c_surf / SY.MOON_DEG:.2f})")


def shot_v1():
    n = SHOTS["v1"]
    ex = 0.3
    sc, cam, tgt = bc_scene(n, ex)
    key_path(cam, tgt, 1, n, lambda f: bc_pose(V1_D, lerp(*V1_DELTA, smooth((f - 1) / (n - 1)))))
    stars = bc_world(sc, cam, n, ex)
    moon_outline(sc, cam, n)
    S.finish(sc, stars, denoise="far", star_samples=24)
    return sc, n


def shot_v6():
    n = SHOTS["v6"]
    ex = 0.3
    sc, cam, tgt = bc_scene(n, ex)

    def pose(f):
        s = smooth((f - 1) / n)                  # кадр n+1 = первый кадр v1
        D = math.exp(lerp(math.log(46.0), math.log(V1_D), s))
        return bc_pose(D, lerp(3.6, V1_DELTA[0], s), beta=lerp(6.0, 0.0, s))
    key_path(cam, tgt, 1, n + 1, pose)
    stars = bc_world(sc, cam, n, ex)
    moon_outline(sc, cam, n, fade=(n - 100, n - 20))      # к шву петли контур уже стоит, как в кадре 1 v1
    S.finish(sc, stars, denoise="far", star_samples=24)
    return sc, n


# ================================================================ v2 / v3: схема системы
STAR_MAP = 14.0
V2_T0 = 0.0                                      # время схемы (с) в кадре 1 v2
V3_T0 = SHOTS["v2"] / FPS                        # v3 продолжает время v2


def map_scene(n):
    sc = S.base_scene(n, exposure=0.0, samples=16, adaptive=0.05, bloom_strength=0.7)   # схема: без баланса белого
    sc.cycles.use_denoising = False              # только эмиссия и фон: денойз съел бы тонкие линии
    cam, tgt = CAM.camera_rig("Cam", lens=35, clip_start=1.0, clip_end=2.0e6)
    return sc, cam, tgt


def map_system(sc, cam, n, t0, star_scale=3.0, letters=True, draw_in=None):
    """Звезда, 7 орбит (постоянная экранная толщина), метки на орбитах в ускоренном времени, подписи-буквы,
    вспышки меток на транзитах. Печатает EVENT <шот> transit для tools/cues.py. -> dict."""
    root = C.empty("T1_Root", coll="FX")
    disk, _lamp = SY.build_star(sc, scale=star_scale, strength=STAR_MAP)
    out = dict(root=root, disk=disk, orbits={}, dots={}, labels={}, pivots={})
    for i, nm in enumerate(SY.NAMES):
        orb = PLN.build_path_line(f"Orb_{nm}", SY.circle_points(SY.A_MM[nm]), color=ORBIT_COL, strength=1.3,
                                  head=1.0, trail=10.0, floor=1.0, parent=root, cam=cam, px=1.0, sides=6)
        if draw_in is not None:                  # прорисовка орбит с кадра draw_in (изнутри наружу)
            PLN.key_head(orb, 0.0, 1.0, draw_in + 4 * i, draw_in + 49 + 4 * i)
        d = SY.dot(f"Dot_{nm}", DOT_COL[nm], 6.0)
        pv = ORB.add_orbit(sc, d, center_parent=root, a=SY.A_MM[nm], period_s=SY.PERIOD_S[nm],
                           phase_deg=SY.planet_angle(nm, t0), frame_start=1, frame_end=n, inertial_axis=False)
        SY.key_dot_px(d, cam, 5.0, 1, n)
        out["orbits"][nm], out["dots"][nm], out["pivots"][nm] = orb, d, pv
        if letters:
            out["labels"][nm] = label(f"Lbl_{nm}", nm, (SY.A_MM[nm], 0, 0), cam, n, px=34, off=(0, 26),
                                      color=DOT_COL[nm], parent=pv, step=4)
    ev = []
    per = {nm: [] for nm in SY.NAMES}
    for t, nm in SY.transits(t0, t0 + n / FPS):
        f = int(round((t - t0) * FPS)) + 1
        if 1 <= f <= n:
            per[nm].append(f)
            ev.append(f)
    for nm, fr in per.items():
        if fr:
            SY.key_dot_flash(out["dots"][nm], fr)
    out["transits"] = sorted(ev)
    return out


def map_sky(sc, cam, view_dir):
    return SKY.build_sky(sc, cam, 0.0, mw_strength=0.3, star_brightness=0.7,
                         gal=SKY.gal_for_view(view_dir, tilt_deg=55, l_center_deg=70))


def shot_v2():
    n = SHOTS["v2"]
    sc, cam, tgt = map_scene(n)

    def pose(f):
        s = smooth((f - 1) / (n - 1))
        # эллипс орбит ≈0.13–0.87 ширины, звезда на ~0.55 высоты (низ орбит выше субтитров)
        return CAM.sph(lerp(47500.0, 43000.0, s), lerp(90.0, 84.0, s), lerp(62.0, 58.0, s)), (0.0, 3200.0, 0.0)
    key_path(cam, tgt, 1, n, pose, step=4)
    stars = map_sky(sc, cam, -Vector(CAM.sph(1, 90, 62)))
    m = map_system(sc, cam, n, V2_T0, draw_in=1)
    # линия на Землю (транзит = планета пересекает её) — появляется к фразе «Each beat…»
    far = SY.EARTH_DIR * 14500.0
    line = PLN.build_path_line("ToEarth", [Vector((0, 0, 0)), far], color=OUTLINE, strength=1.1, head=0.0,
                               trail=10.0, floor=1.0, parent=m["root"], cam=cam, px=0.8, sides=6)
    PLN.key_head(line, 0.0, 1.0, 290, 350)
    lb = label("LblEarth", "to Earth · 40 ly", far, cam, n, px=32, off=(0, 34))
    LB.key_fade(lb, 1.0, f_in=330, length=30)
    print(f"EVENT v2 transit: " + ", ".join(str(f) for f in m["transits"]))
    S.finish(sc, stars, star_samples=24)
    return sc, n


V3_JUP_GAP = 30.0


def shot_v3():
    n = SHOTS["v3"]
    sc, cam, tgt = map_scene(n)
    d0, d1 = 900.0, 285000.0
    c0 = Vector(CAM.sph(d0, -62, 20))
    fwd0 = (-c0).normalized()
    right0 = cam_right(c0, (0, 0, 0))
    up0 = right0.cross(fwd0).normalized()

    def beside(ang):                                               # точка на глубине звезды, ang рад вправо
        return c0 + (Matrix.Rotation(-ang, 3, up0) @ fwd0) * d0
    jup = beside((SY.R_STAR + V3_JUP_GAP + SY.JUPITER_R_MM) / d0)
    t_pair = beside((SY.JUPITER_R_MM + V3_JUP_GAP * 0.5) / d0)      # центр пары «звезда + Юпитер»

    def pose(f):
        s = smooth((f - 170) / 430.0)                               # отъезд 170 → 600, затем стоп
        drift = (f - 1) / (n - 1)
        D = d0 * (d1 / d0) ** s
        loc = CAM.sph(D, lerp(-62.0, -84.0, s) + 3.0 * drift, lerp(20.0, 70.0, s))
        return loc, tuple(t_pair * (1.0 - s))
    key_path(cam, tgt, 1, n, pose)
    stars = map_sky(sc, cam, Vector((0, 0, -1)))
    # камера крупного плана внутри орбит: орбиты видны с ребра полосами — рисуем их уже на отъезде
    m = map_system(sc, cam, n, V3_T0, star_scale=1.0, letters=False, draw_in=250)
    # звезда к концу отъезда ×3 (на общем плане — точка), как на схеме v2
    disk = m["disk"]
    disk.scale = (1, 1, 1)
    disk.keyframe_insert("scale", frame=330)
    disk.scale = (3, 3, 3)
    disk.keyframe_insert("scale", frame=520)
    SY.key_star_strength(disk, [(1, 0.3), (200, 0.3), (420, STAR_MAP)])
    # Юпитер в том же масштабе
    ring = SH.build_ring("JupRing", cam, radius=SY.JUPITER_R_MM, location=tuple(jup), color=OUTLINE,
                         strength=2.4, fill=0.0)
    SH.key_ring(ring, cam, lambda f: SY.JUPITER_R_MM, 1.4, 1, n, step=4)
    SH.key_strength(ring, [(1, 2.4), (230, 2.4), (290, 0.0)])
    pa = LB.pixel_angle(cam, sc)
    px_j = math.atan(SY.JUPITER_R_MM / d0) / pa
    px_s = math.atan(SY.R_STAR / d0) / pa
    y_lbl = -(max(px_j, px_s) + 80)                                 # обе подписи на одной строке под дисками
    lj = label("LblJup", "Jupiter\n(same scale)", jup, cam, n, px=34, off=(0, y_lbl - 22), step=4)
    LB.key_fade(lj, 1.0, f_out=220, length=40)
    ls = label("LblStar", "TRAPPIST-1", (0, 0, 0), cam, n, px=34, off=(0, y_lbl), color=(1.0, 0.75, 0.55), step=4)
    LB.key_fade(ls, 1.0, f_out=220, length=40)
    # орбита Меркурия в том же масштабе — рисуется вокруг системы
    merc = PLN.build_path_line("Mercury", SY.circle_points(SY.MERCURY_A_MM, n=1440), color=OUTLINE, strength=1.6,
                               head=0.0, trail=10.0, floor=1.0, parent=m["root"], cam=cam, px=1.3, sides=6)
    PLN.key_head(merc, 0.0, 1.0, 470, 600)
    p_m = SY.pos("b", 99.0) * (SY.MERCURY_A_MM / SY.A_MM["b"])                  # верх дуги в кадре (камера с −Y)
    lm = label("LblMerc", "Mercury's orbit\n(same scale)", p_m, cam, n, px=34, off=(0, 70), step=4)
    LB.key_fade(lm, 1.0, f_in=560, length=40)
    lt = label("LblSys", "all 7 orbits", (0, 0, 0), cam, n, px=32, off=(0, -120), color=(1.0, 0.75, 0.55), step=4)
    LB.key_fade(lt, 1.0, f_in=600, length=40)
    print(f"EVENT v3 transit: " + ", ".join(str(f) for f in m["transits"]))
    S.finish(sc, stars, star_samples=24)
    return sc, n


# ================================================================ v4: TRAPPIST-1e и её солнце
E = SY.pos("e", 0.0)
RE = SY.R_MM["e"]
LENS_E = 100.0
VFOV_E = math.degrees(2.0 * math.atan(18.0 / LENS_E))
V4_STAR_ABOVE = 5.5                              # центр звезды над лимбом e, град
V4_LIMB_Y = 0.38                                 # ободок выше полосы субтитров
V4_HALF = Vector((-math.cos(math.radians(95.0)), math.sin(math.radians(95.0)) * math.cos(math.radians(12.0)),
                  math.sin(math.radians(95.0)) * math.sin(math.radians(12.0))))   # полуфаза: фазовый угол 95°


def e_cam(D, phi, psi):
    p, s = math.radians(phi), math.radians(psi)
    return E + Vector((math.cos(p) * math.cos(s), math.cos(p) * math.sin(s), math.sin(p))) * D


def e_pose(D, psi):
    """Камера над плоскостью орбит с внешней стороны e: звезда на V4_STAR_ABOVE над лимбом (серп ~150°)."""
    def above(P):
        de = (E - P).normalized()
        ds = (-P).normalized()
        return math.degrees(de.angle(ds)) - math.degrees(math.asin(RE / (E - P).length))
    lo, hi = 0.0, 80.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if above(e_cam(D, mid, psi)) < V4_STAR_ABOVE:
            lo = mid
        else:
            hi = mid
    P = e_cam(D, 0.5 * (lo + hi), psi)
    de = (E - P).normalized()
    ds = (-P).normalized()
    th_l = math.degrees(math.asin(RE / (E - P).length))
    look = rot_toward(de, ds, th_l + (0.5 - V4_LIMB_Y) * VFOV_E)
    return P, P + look * 600.0


def v4_pose(f):
    """1–330: серп e, звезда над лимбом (медленный дрейф); 330–600: облёт к полуфазе и отъезд 14 → 90 Мм
    (направление камеры — slerp, цель — точкой); 600–720: полуфаза, терминатор на месте (приливной захват)."""
    if f <= 330:
        s = smooth((f - 1) / 329.0)
        return e_pose(lerp(14.6, 14.0, s), lerp(-4.0, 0.0, s))
    pa, ta = e_pose(14.0, 0.0)
    va = (pa - E).normalized()
    la = (Vector(ta) - pa).normalized()
    # центр кадра — середина освещённой половины (тёмная сторона сливается с небом)
    sd = Vector((-1.0, 0.0, 0.0))
    tb = E + (sd - V4_HALF * sd.dot(V4_HALF)).normalized() * (0.42 * RE)
    if f <= 600:
        s = smooth((f - 330) / 270.0)
        v = Quaternion().slerp(va.rotation_difference(V4_HALF), s) @ va
        P = E + v * math.exp(lerp(math.log(14.0), math.log(90.0), s))
        t0 = pa + la * (E - pa).length                       # цель ведётся точкой: e не уходит из кадра
        return P, t0.lerp(tb, s)
    s = smooth((f - 600) / 120.0)
    P = E + V4_HALF * lerp(90.0, 87.0, s)
    return P, tb


def shot_v4():
    n = SHOTS["v4"]
    ex = 0.6
    sc = S.base_scene(n, exposure=ex, samples=28, adaptive=0.03, bloom_strength=0.45, white_balance=SY.WB_K)
    cam, tgt = CAM.camera_rig("Cam", lens=LENS_E, clip_start=0.05, clip_end=1.0e6)
    key_path(cam, tgt, 1, n, v4_pose)
    stars = SKY.build_sky(sc, cam, ex, star_brightness=0.8,
                          gal=SKY.gal_for_view(Vector((-1, 0.6, 0.1)), tilt_deg=-40, l_center_deg=30))
    disk, lamp = SY.build_star(sc, strength=0.28, light_irr=4.5, irr_at=SY.A_MM["e"])   # без пересвета: диск оранжевый
    SY.build_planet(sc, "e", n, lamp, detail="close", location=E, spin_deg=120.0, atmosphere=False)
    # 4 контура Солнца с Земли поперёк диска звезды (звезда с e шире в 4.07 раза) — на фразе «4× wider»
    P, T = v4_pose(200)
    right = cam_right(P, T)
    ctr0 = (P - Vector((0, 0, 0))).normalized() * (1.5 * SY.R_STAR)    # чуть перед диском, к камере
    r = SY.ring_radius_for(P, ctr0, SY.SUN_DEG)
    for k, x in enumerate((-1.5, -0.5, 0.5, 1.5)):
        ring, _r = outline(f"SunRing{k}", cam, ctr0 + right * (2.0 * r * x), SY.SUN_DEG, n, px=1.6, strength=3.0,
                           cam_loc=P)
        f0 = 190 + 15 * k
        SH.key_strength(ring, [(1, 0.0), (f0, 0.0), (f0 + 12, 3.0), (330, 3.0), (380, 0.0)])
    px_s = math.atan(SY.R_STAR / P.length) / LB.pixel_angle(cam, sc)
    lb = label("LblSun", "4 × the Sun as seen from Earth", (0, 0, 0), cam, n, px=30, off=(0, -px_s - 56))
    LB.key_fade(lb, 1.0, f_in=240, f_out=320, length=30)
    print(f"V4 star from e {2 * math.degrees(math.atan(SY.R_STAR / P.length)):.3f} deg, Sun rings {SY.SUN_DEG} deg")
    S.finish(sc, stars, denoise="far", star_samples=24)
    return sc, n


# ================================================================ v5: семь планет в ряд
V5_GAP = 6.0


def lineup():
    xs, x, prev = {}, 0.0, None
    for nm in SY.NAMES:
        if prev is not None:
            x += SY.R_MM[prev] + V5_GAP + SY.R_MM[nm]
        xs[nm] = x
        prev = nm
    x_earth = x + SY.R_MM[prev] + V5_GAP + SY.EARTH_R_MM
    return xs, x_earth


def shot_v5():
    n = SHOTS["v5"]
    ex = 0.25
    sc = S.base_scene(n, exposure=ex, samples=28, adaptive=0.03, bloom_strength=0.2, white_balance=SY.WB_K)
    cam, tgt = CAM.camera_rig("Cam", lens=85, clip_start=0.05, clip_end=1.0e6)
    xs, x_earth = lineup()
    xe = 0.5 * (xs["h"] + x_earth)
    keys = [(1, 0.5 * (xs["b"] + xs["c"])), (300, 0.5 * (xs["d"] + xs["e"])), (420, 0.5 * (xs["f"] + xs["g"])),
            (520, xe), (n, xe)]                                # к «Earth for scale» (47.6 с ≈ f490) — h и Земля
    CAM.key_camera(cam, tgt, [dict(frame=f, loc=(x, -170.0, 0.0), target=(x, 0.0, 0.0)) for f, x in keys])
    stars = SKY.build_sky(sc, cam, ex, star_brightness=0.8,
                          gal=SKY.gal_for_view(Vector((0.4, 1, 0)), tilt_deg=20, l_center_deg=60))
    ldir = Vector((-0.30, -0.90, 0.30)).normalized()      # фаза ~25°: диски почти полные
    ld = 30000.0
    lamp = LT.add_point_star("T1_Light", LT.point_energy_for(5.0, ld), temp_k=SY.TEFF, radius=SY.R_STAR,
                             location=tuple(Vector((60.0, 0, 0)) + ldir * ld))
    lamp.visible_camera = False
    for nm in SY.NAMES:
        p = SY.build_planet(sc, nm, n, lamp, detail="close", location=(xs[nm], 0.0, 0.0), spin_deg=90.0,
                            atmosphere=False)                 # атмосферы не измерены — не рисуем
        p["planet"].visible_shadow = False                    # общий свет: соседи не затеняют друг друга
        label(f"Lbl_{nm}", nm, (xs[nm], 0.0, SY.R_MM[nm] + 1.5), cam, n, px=40, off=(0, 24), color=DOT_COL[nm])
    ring = SH.build_ring("EarthRing", cam, radius=SY.EARTH_R_MM, location=(x_earth, 0.0, 0.0), color=OUTLINE,
                         strength=2.4, fill=0.0)
    SH.key_ring(ring, cam, lambda f: SY.EARTH_R_MM, 1.4, 1, n, step=4)
    label("LblEarth", "Earth\n(same scale)", (x_earth, 0.0, -SY.EARTH_R_MM - 1.5), cam, n, px=32, off=(0, -48))
    S.finish(sc, stars, denoise="far", star_samples=24)
    return sc, n


BUILDERS = {"v1": shot_v1, "v2": shot_v2, "v3": shot_v3, "v4": shot_v4, "v5": shot_v5, "v6": shot_v6}

def draft(argv):
    """Черновой ролик на согласование до финала: `-- vN draft [pct=25] [samples=4] [step=6]` — каждый step-й кадр
    в out/<ep>/9x16/draft/<шот>/ (не в frames/: докачка финала не примет черновые кадры за готовые); кадр
    копируется в следующие step−1 (60/step к/с в 60-кадровой секвенции: монтаж и звук — как в финале)."""
    import shutil
    from spacekit import render as R
    step = next((int(a[5:]) for a in argv if a.startswith("step=")), 6)
    argv = [a for a in argv if a != "draft" and not a.startswith("step=")]
    if not any(a.startswith("pct=") for a in argv):
        argv.append("pct=25")
    if not any(a.startswith("samples=") for a in argv):
        argv.append("samples=4")
    S.run(BUILDERS, out_dir=OUT, argv=argv)                 # только сборка сцены (без preview/final)
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
