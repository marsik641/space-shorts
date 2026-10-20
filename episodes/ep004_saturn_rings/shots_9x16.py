"""Эпизод 004 — кольца Сатурна (TRUE SCALE), вертикаль 1080×1920 60 fps.

    blender -b --factory-startup -P episodes/ep004_saturn_rings/shots_9x16.py -- <шот> [preview F,..] [pct=50] [samples=N] [outdir=DIR] [final] [save]

    preview F,..  — кадры превью (pct=50) в out/ep004_saturn_rings/9x16/previews/<шот>_fNNNN.png
    final         — PNG-секвенция out/ep004_saturn_rings/9x16/frames/<шот>/####.png с докачкой (tools/render_episode.sh)
    save          — .blend в out/ep004_saturn_rings/9x16/scenes/<шот>.blend
    draft         — черновое видеопревью: pct 25, 4 spp, каждый 6-й кадр в out/ep004_saturn_rings/9x16/draft/<шот>/
    Лог превью — в out/ep004_saturn_rings/9x16/logs/prev_<шот>.log (по нему tools/cues.py: строки EVENT).

Монтаж (кадры @60, склейки встык; время в ролике):
    v1  330  0–5.5 с     хук: камера в плоскости колец — кольца волосяной линией поперёк диска, тень колец широкой
                         полосой на южном полушарии; подъём на 19° — кольца раскрываются (кольца в кадре по диагонали)
    v2  600  5.5–15.5 с  истинный масштаб: Земля под левым краем кольца A, отъезд — Луна далеко за правым краем;
                         линейки 384 400 км (Земля–Луна) и 273 600 км (кольца); затем спуск к плоскости («лист бумаги»)
    v3  660  15.5–26.5 с низкий пролёт над кольцами к Сатурну: щель Килера → щель Энке с Паном (28 км) → деление
                         Кассини (сквозь него — южное полушарие) → B; EVENT gap — тик в музыке; склейка на «They're not solid:»
    v4  840  26.5–40.5 с внутри кольца A (1 ед. = 1 м): ледяные комья от сантиметров до ~10 м, Солнце на 15° — длинные
                         тени, Сатурн виден и снизу сквозь тонкий слой; подъём над слоем (EVENT emerge, ~2.9 с), затем
                         крен 12° и поворот 15° — горизонт по диагонали, до горизонта «пол» из глыб
    v5  540  40.5–49.5 с весь лёд колец одним шаром (~320 км) — собирается на «into one ball» — рядом с Мимасом (396 км,
                         кратер Гершель) на его орбите, Сатурн позади
    v6  600  49.5–59.5 с облёт с фазы ~90° (освещённая сторона, длинная тень планеты на кольцах) к ракурсу v1 и спуск
                         в плоскость колец; последние 90 кадров — линейный наезд, который продолжается в v1: кадр 601 =
                         кадр 1 v1 (в монтаж 600; поворот Сатурна — «до» v1)
Масштабы и данные — system.py; кит — spacekit.bodies.gas_giant / rings, spacekit.fx.ring_particles.
SHOTS = episode.json -> edit[].frames (tools/check_episode.py).
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
sys.path.insert(0, HERE)

import bpy
from mathutils import Matrix, Quaternion, Vector

from spacekit import anim as A
from spacekit import camera as CAM
from spacekit import core as C
from spacekit import lighting as LT
from spacekit import shot as S
from spacekit import sky as SKY
from spacekit.bodies import gas_giant as GG
from spacekit.bodies import planets as PL
from spacekit.bodies import rings as RG
from spacekit.fx import label as LB
from spacekit.fx import path_line as PLN
from spacekit.fx import ring_particles as RP

import system as SY

EP = os.path.basename(HERE)
OUT = os.path.join(C.OUT, EP, "9x16")
S.OPT.update(fmt="9x16", fps=60)
LB.FONT = "C:/Windows/Fonts/Candara.ttf"         # подписи в кадре — шрифт эпизода (как титры)
SHOTS = {"v1": 330, "v2": 600, "v3": 660, "v4": 840, "v5": 540, "v6": 601}   # v6: 601-й = кадр 1 v1, в монтаж — 600
U = SY.U_KM
SEED = 4
LON0 = 35.0                  # долгота Сатурна (вращение) в кадре 1 v1
T_V6_END = 0.0               # v6 кончается «в момент» кадра 1 v1 (петля)
LABEL_COL = (0.93, 0.95, 1.0)
RULER_COL = (0.70, 0.86, 1.0)
EARTH_COL = (0.55, 0.78, 1.0)


def smooth(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def smoother(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * t * (t * (6 * t - 15) + 10)


def key_path(cam, tgt, n, fn, step=2, lens=None):
    """Ключи камеры и цели по функции fn(frame) -> (loc, target[, lens]) каждые step кадров, LINEAR."""
    fr = list(range(1, n + 1, step))
    if fr[-1] != n:
        fr.append(n)
    for f in fr:
        r = fn(f)
        cam.location = r[0]
        cam.keyframe_insert("location", frame=f)
        tgt.location = r[1]
        tgt.keyframe_insert("location", frame=f)
        if len(r) > 2:
            cam.data.lens = r[2]
            cam.data.keyframe_insert("lens", frame=f)
    for idd in (cam, tgt, cam.data):
        A.set_interpolation(idd, "LINEAR")


def event(shot, name, frames):
    print(f"EVENT {shot} {name}: " + ", ".join(str(int(f)) for f in frames))


def sun(sc, cam, sun_w, star_dist):
    """Солнце: лампа (тени и свет) + точка-звезда ~3 px (в кадре почти не бывает)."""
    r = 3.0 * LB.pixel_angle(cam, sc) * star_dist
    return LT.add_distant_sun("Sun", sun_w, strength=SY.SUN_STRENGTH, angle_deg=0.056, star_dist=star_dist,
                              star_radius=r, star_strength=60.0 * (4.0 / 3.0) ** 2)


def saturn(sc, M, n, lon0, detail="close", unit_km=U, hole=None, location=(0, 0, 0), grain=None):
    """Сатурн + кольца в системе S, повёрнутой в мир матрицей M. Возвращает (g, rg, sun_w)."""
    sun_w = (M @ SY.SUN_S).normalized()
    g = GG.build_gas_giant(sc, "saturn", radius=SY.R_EQ / unit_km, location=location,
                           rotation_euler=tuple(M.to_euler("XYZ")), sun_dir=sun_w, sun_strength=SY.SUN_STRENGTH,
                           lon0_deg=lon0, seed=SEED, detail=detail, frame_start=1, frame_end=n)
    rg = RG.build_rings(sc, "saturn", parent=g["root"], unit_km=unit_km, sun_dir=sun_w, seed=SEED, detail=detail,
                        hole=hole, grain=grain)
    return g, rg, sun_w


def wide_scene(n, lens=50.0, exposure=0.0, samples=32, clip_start=0.5):
    sc = S.base_scene(n, exposure=exposure, samples=samples, adaptive=0.02, bloom_strength=0.35)
    cam, tgt = CAM.camera_rig("Cam", lens=lens, clip_start=clip_start, clip_end=5.0e6)
    return sc, cam, tgt


def lon_v(shot_start_s):
    """Долгота Сатурна в начале шота, начинающегося на shot_start_s секунде ролика (реальное вращение)."""
    return LON0 + 360.0 * shot_start_s / SY.ROT_S


# ---------------------------------------------------------------- v1 / v6: хук и петля
HOOK = dict(D=372.0, az=-50.0, el=0.16, roll=48.0, lens=50.0)   # el 0.16°: передняя дуга колец ~1.3 px
M_HOOK = SY.sys_rot(-SY.sph_s(1.0, HOOK["az"], 9.0), HOOK["roll"])
DOLLY = 0.08            # ед./кадр: наезд идёт через шов петли (последние 90 кадров v6 → первые 150 v1) без остановки


def hook_pose(D, az, el):
    return M_HOOK @ SY.sph_s(D, az, el)


def hook_world(sc, cam, n, lon0):
    g, rg, sun_w = saturn(sc, M_HOOK, n, lon0)
    lamp, disk = sun(sc, cam, sun_w, 4.0e5)
    view = (Vector((0, 0, 0)) - hook_pose(HOOK["D"], HOOK["az"], HOOK["el"])).normalized()
    stars = SKY.build_sky(sc, cam, 0.0, gal=SKY.gal_for_view(view, tilt_deg=-35.0, l_center_deg=70.0),
                          star_brightness=0.8)
    return g, rg, stars, disk


def shot_v1():
    n = SHOTS["v1"]
    sc, cam, tgt = wide_scene(n, lens=HOOK["lens"])

    def fn(f):
        # 0–2.5 с: в плоскости колец (волосяная линия, «10 m») с медленным наездом; затем подъём на 19°
        t1 = smooth((f - 1) / 150.0) * 0.6
        t2 = smoother((f - 150) / (n - 150.0))
        el = HOOK["el"] + 0.25 * t1 + (19.0 - HOOK["el"] - 0.15) * t2
        az = HOOK["az"] + 4.0 * t2
        D = HOOK["D"] - DOLLY * (f - 1) - 4.0 * t2
        return hook_pose(D, az, el), (0.0, 0.0, 0.0)

    key_path(cam, tgt, n, fn)
    g, rg, stars, disk = hook_world(sc, cam, n, lon_v(0.0))
    event("v1", "open", [150])
    S.finish(sc, [stars, disk], denoise="far", star_samples=32)
    return sc, n


def shot_v6():
    n = SHOTS["v6"]
    sc, cam, tgt = wide_scene(n, lens=HOOK["lens"])
    az0, el0, D0 = 100.0, 24.0, 570.0

    def fn(f):
        t = smoother((f - 1) / (n - 1.0))
        az = az0 + (HOOK["az"] - az0) * t
        # возвышение спускается позже азимута: к концу — в плоскость колец (кадр n = кадр 1 v1)
        te = smoother((f - 1) / (n - 1.0)) ** 1.6
        el = el0 + (HOOK["el"] - el0) * te
        # дальность: к кадру n−90 выходит на линейный наезд DOLLY — он продолжается в v1
        lin = HOOK["D"] + DOLLY * (n - f)
        tb = smoother((f - 1) / (n - 91.0))
        D = lin + (D0 - HOOK["D"] - DOLLY * (n - 1)) * (1.0 - tb)
        return hook_pose(D, az, el), (0.0, 0.0, 0.0)

    key_path(cam, tgt, n, fn)
    # вращение Сатурна: последний кадр v6 — тот же поворот, что кадр 1 v1
    g, rg, stars, disk = hook_world(sc, cam, n, LON0 - 360.0 * (n - 1) / 60.0 / SY.ROT_S)
    event("v6", "edge", [n])
    S.finish(sc, [stars, disk], denoise="far", star_samples=32)
    return sc, n


# ---------------------------------------------------------------- v2: Земля и Луна в масштабе
V2 = dict(az=-62.0, el0=52.0, el1=24.0, lens=50.0)


def _earth_material(name):
    """Земля издалека: океан с бликом, материки (шум), ледяные шапки, облака — для диска ~30–150 px."""
    mat, N, L, out = C.new_material(name)
    b = PL._NB(mat.node_tree)
    tc = b.node("ShaderNodeTexCoord")
    v = b.v("NORMALIZE", tc.outputs["Object"])
    z = b.sep(v)[2]
    land_n = b.noise(b.v("ADD", v, (3.1, 7.7, 1.3)), 1.6, detail=7, rough=0.62, dist=0.35).outputs[0]
    land = b.ss(land_n, 0.53, 0.56)
    dry = b.ss(b.noise(b.v("ADD", v, (9.2, 2.4, 5.5)), 2.5, detail=4).outputs[0], 0.45, 0.62)
    lat = b.m("ABSOLUTE", z)
    ice = b.ss(lat, 0.93, 0.96)
    green = b.mix(dry, (0.035, 0.065, 0.025), (0.20, 0.15, 0.08))
    col = b.mix(land, (0.006, 0.018, 0.055), green)
    col = b.mix(ice, col, (0.75, 0.78, 0.80))
    cl_n = b.noise(b.v("ADD", v, (1.9, 4.4, 8.8)), 3.2, detail=6, rough=0.58, dist=0.9).outputs[0]
    cloud = b.ss(cl_n, 0.50, 0.66)
    col = b.mix(cloud, col, (0.82, 0.83, 0.85))
    rough = b.mix(b.m("MAXIMUM", land, cloud), (0.28, 0.28, 0.28), (0.95, 0.95, 0.95))
    bsdf = b.node("ShaderNodeBsdfPrincipled", {"Base Color": col, "Roughness": b.sep(rough)[0]})
    b.put(bsdf.inputs["Specular IOR Level"], 0.5)
    b.put(out.inputs["Surface"], bsdf.outputs[0])
    return mat


def earth_moon(sc, sun_w, E_loc, M_loc):
    e = PL.build_planet(sc, "poltergeist", radius=SY.EARTH_R / U, location=tuple(E_loc), detail="mid",
                        aurora_strength=0.0, name="Earth", axial_tilt_deg=23.4, rot_period_s=1.0e9)
    e["planet"].data.materials[0] = _earth_material("EarthSurface")
    PL.set_sun_dir(e, sun_w, irradiance=SY.SUN_STRENGTH / math.pi)
    m = PL.build_planet(sc, "draugr", radius=SY.MOON_R / U, location=tuple(M_loc), detail="far", name="Moon",
                        axial_tilt_deg=0.0, rot_period_s=1.0e9)
    return e, m


def ruler(name, p0, p1, cam, color, f0, f1, px=1.6, tick=6.0, up=Vector((0, 0, 1))):
    """Линейка p0–p1: линия постоянной экранной толщины + засечки на концах; прорисовка f0..f1."""
    pts = [Vector(p0).lerp(Vector(p1), i / 64.0) for i in range(65)]
    ln = PLN.build_path_line(name, pts, color=color, strength=5.0, head=0.0, trail=1.0, floor=1.0, cam=cam, px=px)
    PLN.key_head(ln, 0.0, 1.0, f0, f1)
    out = [ln]
    for k, (p, f) in enumerate(((p0, f0), (p1, f1))):
        tk = PLN.build_path_line(f"{name}_t{k}", [Vector(p) - up * tick, Vector(p) + up * tick], color=color,
                                 strength=5.0, head=0.0, trail=1.0, floor=1.0, cam=cam, px=px)
        PLN.key_head(tk, 0.0, 1.0, f - 6, f + 6)
        out.append(tk)
    return out


def fade_line(ob, f0, f1, s0=5.0):
    """Погасить линию path_line (сила эмиссии s0 → 0 за кадры f0..f1)."""
    mat = bpy.data.materials[ob["path_mat"]]
    em = next(nd for nd in mat.node_tree.nodes if nd.bl_idname == "ShaderNodeEmission")
    sock = em.inputs["Strength"].links[0].from_node.inputs[1]
    sock.default_value = s0
    sock.keyframe_insert("default_value", frame=f0)
    sock.default_value = 0.0
    sock.keyframe_insert("default_value", frame=f1)
    A.set_interpolation(mat.node_tree, "LINEAR", extrapolate="CONSTANT")


def shot_v2():
    n = SHOTS["v2"]
    sc, cam, tgt = wide_scene(n, lens=V2["lens"])
    Mi = Matrix.Identity(3)
    d0 = -SY.sph_s(1.0, V2["az"], V2["el0"])
    right = d0.cross(Vector((0, 0, 1))).normalized()
    up_c = right.cross(d0).normalized()                          # «вверх» кадра
    a_out = SY.RING_A_OUT / U
    # Земля, Луна и обе линейки — в плоскости через центр Сатурна поперёк взгляда: на экране отношение линеек
    # 273 560 / 384 400 = 0.71 и размер Земли к Сатурну — истинные (критик физики, круг 1)
    E = -right * a_out - up_c * 150.0                             # Земля — под левым краем кольца A
    Mo = E + right * (SY.EARTH_MOON / U)
    R0, R1 = -right * a_out + up_c * 128.0, right * a_out + up_c * 128.0   # линейка колец — над кольцами
    mid = (E + Mo) * 0.5 + up_c * 40.0 + right * 20.0             # центр линейки — на x ≈ 0.465 (вне кнопок)
    sat_c = right * -6.0

    def fn(f):
        # 0–3.3 с: отъезд от Земли к общему плану (цель отстаёт: Земля дольше в кадре), Луна входит к ~8.5 с;
        # с f400 линейки гаснут, наезд и спуск к плоскости — кольца ложатся тонким листом («paper»)
        t = smoother((f - 1) / 200.0)
        tg = E.lerp(mid, t ** 1.5)
        D = 230.0 * (1540.0 / 230.0) ** t
        t3 = smoother((f - 410) / (n - 410.0))
        tg = tg.lerp(sat_c, t3)
        D = D + (780.0 - D) * t3
        el = V2["el0"] + (6.0 - V2["el0"]) * smoother((f - 380) / (n - 380.0))
        return tuple(tg + SY.sph_s(D, V2["az"] + 8.0 * t3, el)), tuple(tg)

    key_path(cam, tgt, n, fn)
    g, rg, sun_w = saturn(sc, Mi, n, lon_v(5.5), detail="close")
    lamp, disk = sun(sc, cam, sun_w, 4.0e5)
    e, m = earth_moon(sc, sun_w, E, Mo)
    rl = ruler("RulerEM", E, Mo, cam, EARTH_COL, 90, 170)
    rr = ruler("RulerRings", R0, R1, cam, RULER_COL, 110, 190)
    for ln in rl + rr:
        fade_line(ln, 400, 430)
    # для tools/framecheck: линейки и подписи появляются и гаснут — скачок размера PNG задуман (финал ep004: f112, f427).
    # tools/cues.py с --events-to pulses превратит их в удары — для v2 исключать: --exclude v2:1-600
    event("v2", "overlay", [112, 427])
    labels = [
        LB.build_label("Lbl_Earth", "EARTH", tuple(E), cam, px=40, offset_px=(0, -44), color=LABEL_COL),
        LB.build_label("Lbl_Moon", "MOON", tuple(Mo), cam, px=40, offset_px=(0, -36), color=LABEL_COL),
        LB.build_label("Lbl_EM", "384,400 km", tuple((E + Mo) * 0.5), cam, px=46, offset_px=(0, 40),
                       color=EARTH_COL),
        LB.build_label("Lbl_Rings", "273,560 km", tuple((R0 + R1) * 0.5), cam, px=46, offset_px=(0, 40),
                       color=RULER_COL),
    ]
    for k, lb in enumerate(labels):
        LB.key_screen_size(lb, cam, 1, n, step=4)
        LB.key_fade(lb, 1.0, f_in=(40 if k == 0 else (130 if k == 1 else 120)), f_out=400, length=24)
    view = (Vector(mid) - Vector(fn(200)[0])).normalized()
    stars = SKY.build_sky(sc, cam, 0.0, gal=SKY.gal_for_view(view, tilt_deg=20.0, l_center_deg=110.0),
                          star_brightness=0.8)
    S.finish(sc, [stars, disk], denoise="far", star_samples=32)
    return sc, n


# ---------------------------------------------------------------- v3: полёт над кольцами
V3 = dict(az=60.0, r0=136.6, r1=112.0, h0=2.2, h1=1.6, p0=-12.0, p1=-7.0, lens=24.0, shutter=0.3, ease=2.24,
          pan_side=0.3, pan_ahead=0.0)
PAN_KM = (17.2, 15.7, 10.4)           # полуоси Пана, км (средний радиус 14.1 км — NASA)


def v3_r(f, n):
    """Радиус камеры: разгон (t^ease) — щель Энке с Паном видна внизу кадра и уходит под камеру к ~19.8 с
    (голос «one kept open by a moon»), края деления Кассини — на 24.2 и 25.3 с."""
    t = (f - 1) / (n - 1.0)
    return V3["r0"] + (V3["r1"] - V3["r0"]) * t ** V3["ease"]


def shot_v3():
    n = SHOTS["v3"]
    sc, cam, tgt = wide_scene(n, lens=V3["lens"], clip_start=0.02)
    a = math.radians(V3["az"])
    rad = Vector((math.cos(a), math.sin(a), 0.0))
    side = Vector((0, 0, 1)).cross(rad).normalized()

    def fn(f):
        # низкий пролёт над A → щель Энке (Пан) → деление Кассини → B: полосы несутся под камерой
        td = smoother((f - 1) / (n - 1.0))
        h = V3["h0"] + (V3["h1"] - V3["h0"]) * td
        loc = rad * v3_r(f, n) + Vector((0, 0, h))
        p = math.radians(V3["p0"] + (V3["p1"] - V3["p0"]) * td)
        aim = loc + (-rad * math.cos(p) + Vector((0, 0, math.sin(p)))) * 50.0
        return tuple(loc), tuple(aim)

    key_path(cam, tgt, n, fn)
    sc.render.motion_blur_shutter = V3["shutter"]                 # ~2 800 км/с: полосы не размазывать
    g, rg, sun_w = saturn(sc, Matrix.Identity(3), n, lon_v(15.5), detail="close")
    lamp, disk = sun(sc, cam, sun_w, 4.0e5)
    # Пан в щели Энке (держит её открытой — NASA), сбоку от пути камеры
    pan_r = 133.584 - V3["pan_ahead"]
    pan = PL.build_planet(sc, "brightice", radius=14.1 / U, location=tuple(rad * pan_r + side * V3["pan_side"]),
                          detail="far", seed=3, name="Pan", axial_tilt_deg=0.0, rot_period_s=1.0e9,
                          tilt_azimuth_deg=V3["az"])                 # длинная ось — на Сатурн (приливный захват)
    pan["planet"].scale = tuple(k / 14.1 for k in PAN_KM)
    # тики в музыке: камера проходит щель Энке и края деления Кассини
    marks = {"keeler": 136.504, "encke": 133.584, "cd_out": SY.RING_A_IN / U, "cd_in": SY.RING_B_OUT / U}
    frs = []
    for nm, rr in marks.items():
        for f in range(1, n):
            if v3_r(f, n) >= rr > v3_r(f + 1, n):
                frs.append(f)
    event("v3", "gap", frs)
    view = (-rad + Vector((0, 0, 0.1))).normalized()
    stars = SKY.build_sky(sc, cam, 0.0, gal=SKY.gal_for_view(view, tilt_deg=-25.0, l_center_deg=30.0),
                          star_brightness=0.7)
    S.finish(sc, [stars, disk], denoise="far", star_samples=32)
    return sc, n


# ---------------------------------------------------------------- v4: внутри кольца A (1 ед. = 1 м)
V4 = dict(r_km=128000.0, site_az=-65.0, lens=24.0, z0=0.4, z1=38.0, run=26.0, tau=0.6, samples=32,
          grain=(5.0, 0.42))


def shot_v4():
    n = SHOTS["v4"]
    sc = S.base_scene(n, exposure=0.0, samples=V4["samples"], adaptive=0.03, bloom_strength=0.3)
    # внутри поля отскоки дороги: один диффузный отскок (свет Сатурна и соседей), без глянца
    sc.cycles.max_bounces, sc.cycles.diffuse_bounces, sc.cycles.glossy_bounces = 3, 1, 0
    cam, tgt = CAM.camera_rig("Cam", lens=V4["lens"], clip_start=0.05, clip_end=3.0e9)
    a = math.radians(V4["site_az"])
    site = Vector((math.cos(a), math.sin(a), 0.0)) * V4["r_km"] * 1000.0    # место камеры в S, м
    to_sat = -site.normalized()
    side = to_sat.cross(Vector((0, 0, 1))).normalized()
    p0 = Vector((0, 0, V4["z0"]))
    p1 = to_sat * V4["run"] + Vector((0, 0, V4["z1"]))

    def fn(f):
        t = (f - 1) / (n - 1.0)
        up = smoother((t - 0.02) / 0.62)                           # первые ~2.8 с — внутри слоя (дорого: ~30 с/кадр)
        loc = p0 + to_sat * (V4["run"] * t) + Vector((0, 0, (V4["z1"] - V4["z0"]) * up)) + side * (1.5 * t)
        pitch = math.radians(-4.0 + 13.0 * smooth((t - 0.2) / 0.7))
        aim = loc + (to_sat * math.cos(pitch) + Vector((0, 0, math.sin(pitch)))) * 100.0 + side * 6.0
        return tuple(loc), tuple(aim)

    key_path(cam, tgt, n, fn)
    # после выхода из слоя — крен до 12° и поворот на 15°: горизонт по диагонали, гребни «следов» поперёк кадра
    # (камера без Track To: вращение ключами)
    cam.constraints.clear()
    cam.rotation_mode = "QUATERNION"
    prev = None
    fr = list(range(1, n + 1, 2)) + ([n] if n % 2 == 0 else [])
    for f in fr:
        t = (f - 1) / (n - 1.0)
        loc, aim = (Vector(v) for v in fn(f))
        yaw = math.radians(15.0 * smooth((t - 0.25) / 0.75))
        d = aim - loc
        d = Vector((d.x * math.cos(yaw) - d.y * math.sin(yaw), d.x * math.sin(yaw) + d.y * math.cos(yaw), d.z))
        qv = d.to_track_quat("-Z", "Y")
        roll = math.radians(12.0 * smooth((t - 0.22) / 0.70))
        qq = Quaternion(d.normalized(), roll) @ qv
        if prev is not None and prev.dot(qq) < 0:
            qq.negate()
        prev = qq
        cam.rotation_quaternion = qq
        cam.keyframe_insert("rotation_quaternion", frame=f)
    A.set_interpolation(cam, "LINEAR")
    hole = (cam, 700.0, 1450.0)
    g, rg, sun_w = saturn(sc, Matrix.Identity(3), n, lon_v(26.5), unit_km=0.001, hole=hole,
                          location=tuple(-site), grain=V4["grain"])
    # дальнее поле слоя — две плоскости (верх и низ слоя, ±4 м): изнутри по горизонту непрозрачная полоса (слой с
    # ребра), снаружи — верхняя плоскость как продолжение «пола» до горизонта
    rg["ring"].location = (0.0, 0.0, 4.0)
    RG.set_albedo(rg, 0.90)
    rg2 = RG.build_rings(sc, "saturn", parent=g["root"], unit_km=0.001, sun_dir=sun_w, seed=SEED, hole=hole,
                         name="Rings_low", location=(0.0, 0.0, -4.0), grain=V4["grain"])
    RG.set_albedo(rg2, 0.85)
    # видимые плоскости — только для камеры: иначе каждый теневой и отражённый луч от каждой глыбы вычисляет
    # шейдер колец (47 с/кадр внутри слоя). Тень колец на Сатурне — отдельная плоскость на 12 м ниже слоя с простым
    # шейдером: лучи от глыб к Солнцу (вверх) её не пересекают
    for r_ in (rg, rg2):
        o = r_["ring"]
        o.visible_shadow = o.visible_diffuse = o.visible_glossy = o.visible_transmission = False
    rg3 = RG.build_rings(sc, "saturn", parent=g["root"], unit_km=0.001, sun_dir=sun_w, seed=SEED, detail="far",
                         name="Rings_shadow", location=(0.0, 0.0, -12.0))
    o = rg3["ring"]
    o.visible_camera = o.visible_diffuse = o.visible_glossy = o.visible_transmission = False
    lamp, disk = sun(sc, cam, sun_w, 2.0e9)
    path = [Vector(fn(f)[0]) for f in list(range(1, n, 40)) + [n]]
    clear = [(tuple(a_), tuple(b_), 1.3) for a_, b_ in zip(path, path[1:])]
    clear.append((tuple(path[0] - to_sat * 3.0), tuple(path[0]), 1.3))          # за спиной в кадре 1 (motion blur)
    # «следы» кольца A: гребни под ~22° к орбитальному направлению (азимут места + 90°), шаг ~60 м
    wk = (60.0, V4["site_az"] + 90.0 + 22.0 + 90.0, 0.55)
    pf = RP.build_field(sc, center=(0, 0, 0), tau=V4["tau"], seed=SEED, clear=clear, wakes=wk,
                        path=[(p.x, p.y) for p in path])
    # момент выхода из слоя: камера выше 2σ мелких частиц (~6.5 м)
    for f in range(1, n + 1):
        if fn(f)[0][2] > 6.5:
            event("v4", "emerge", [f])
            break
    stars = SKY.build_sky(sc, cam, 0.0, gal=SKY.gal_for_view(to_sat + Vector((0, 0, 0.5)), tilt_deg=40.0,
                                                             l_center_deg=90.0), star_brightness=0.7)
    occ = star_occluder(cam, -site, SY.R_EQ * 1000.0, g["f"])
    S.finish(sc, [stars, disk], denoise="far", star_samples=32)
    sc.view_layers[0].layer_collection.children[occ.users_collection[0].name].exclude = True
    return sc, n


def star_occluder(cam, center, R, f, dist=4.0e4):
    """Заслон звёзд для слоя звёзд: сфера звёзд — 50 км от камеры (sky: R ≤ 5·10⁴ ед.), а Сатурн при 1 ед. = 1 м —
    в 1.3·10⁸ м, holdout его не закрывает и звёзды ложатся поверх диска. Масштаб сферы звёзд ×4·10⁴ помогает, но
    стоит +50 % времени (46 вместо 31 с/кадр). Поэтому: сжатая сфера того же углового размера на dist перед камерой
    (Copy Location со сдвигом — без параллакса), в слое звёзд — holdout, в основном слое коллекция исключается."""
    import bmesh
    v = Vector(center) - cam.matrix_world.translation
    k = dist / v.length
    me = bpy.data.meshes.new("StarOccluder")
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=128, v_segments=64, radius=R * k)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("StarOccluder", me)
    C.link(ob, "StarOccluder")
    ob.scale = (1.0, 1.0, 1.0 - f)
    ob.location = v * k
    con = ob.constraints.new("COPY_LOCATION")
    con.target = cam
    con.use_offset = True
    return ob


# ---------------------------------------------------------------- v5: весь лёд колец — один шар у Мимаса
# Геометрия подобрана расчётом: Мимас на азимуте −15° от Солнца, камера в 38° от направления «от Сатурна» в сторону
# движения и на 5° выше плоскости орбиты — Гершель (104° з. д.) виден под ~38° к лучу зрения и освещён под ~62°
# (рельеф читается), Мимас и шар почти в полной фазе (размеры сравнимы), Сатурн — в правом верхнем углу (крен системы).
V5 = dict(az=-15.0, z=1.2, beta0=26.0, beta1=34.0, eps=5.0, d0=2.10, d1=1.85, sat_angle=60.0, ball_angle=200.0,
          gap=0.60, lens=32.0, look_k=0.55, grow=(30, 140))


def v5_geometry():
    """(M5, позиции в S: Мимас, шар, функция камеры c(t), направление на Гершель)."""
    a = math.radians(V5["az"])
    rad = Vector((math.cos(a), math.sin(a), 0.0))
    lead = Vector((-math.sin(a), math.cos(a), 0.0))               # направление движения по орбите (прямое)
    mim = rad * (SY.MIMAS_A / U) + Vector((0, 0, V5["z"]))

    def cdir(beta):
        b, e = math.radians(beta), math.radians(V5["eps"])
        return ((rad * math.cos(b) + lead * math.sin(b)) * math.cos(e) + Vector((0, 0, math.sin(e)))).normalized()

    v = -cdir(0.75 * V5["beta1"] + 0.25 * V5["beta0"])            # взгляд камеры (S) во второй половине шота
    right = v.cross(Vector((0, 0, 1))).normalized()
    up = right.cross(v).normalized()
    s_dir = (-mim).normalized()                                   # на центр Сатурна
    th = math.degrees(math.atan2(s_dir.dot(up), s_dir.dot(right)))
    roll = V5["sat_angle"] - th
    M = SY.sys_rot(v, roll)
    pb = math.radians(V5["ball_angle"] - roll)                    # шар — по экрану слева от Мимаса
    ball = mim + (right * math.cos(pb) + up * math.sin(pb)) * V5["gap"]
    lam = math.radians(104.0)                                     # Гершель: 0° — на Сатурн, 90° з. д. — по ходу
    n_h = (-rad * math.cos(lam) + lead * math.sin(lam)).normalized()
    return M, mim, ball, cdir, n_h


def _ice_ball_material(name):
    mat, N, L, out = C.new_material(name)
    b = PL._NB(mat.node_tree)
    tc = b.node("ShaderNodeTexCoord")
    v = tc.outputs["Object"]
    # плотный лёд, а не снег: голубоватый, с бликом и лёгкой полупрозрачностью у края (в отличие от реголита Мимаса)
    frost = b.lin(b.noise(v, 30.0, detail=5, rough=0.6).outputs[0], 0.3, 0.7, 0.90, 1.04)
    col = b.v("SCALE", (0.62, 0.76, 0.90), scale=frost)
    h = b.noise(v, 60.0, detail=4, rough=0.6).outputs[0]
    bump = b.node("ShaderNodeBump", {"Strength": 0.2, "Distance": 0.002, "Height": h})
    bsdf = b.node("ShaderNodeBsdfPrincipled", {"Base Color": col, "Roughness": 0.38, "Normal": bump.outputs[0]})
    b.put(bsdf.inputs["Specular IOR Level"], 0.5)
    b.put(bsdf.inputs["Coat Weight"], 0.25)
    b.put(bsdf.inputs["Coat Roughness"], 0.25)
    b.put(out.inputs["Surface"], bsdf.outputs[0])
    return mat


def shot_v5():
    n = SHOTS["v5"]
    sc, cam, tgt = wide_scene(n, lens=V5["lens"], clip_start=0.005)
    M, mim, ball, cdir, n_h = v5_geometry()
    look = ball.lerp(mim, V5["look_k"])                         # группа левее центра: Мимас не под кнопками Shorts

    def fn(f):
        t = smooth((f - 1) / (n - 1.0))
        beta = V5["beta0"] + (V5["beta1"] - V5["beta0"]) * t
        d = V5["d0"] + (V5["d1"] - V5["d0"]) * t
        return tuple(M @ (mim + cdir(beta) * d)), tuple(M @ look)

    key_path(cam, tgt, n, fn)
    g, rg, sun_w = saturn(sc, M, n, lon_v(40.5), detail="mid")
    lamp, disk = sun(sc, cam, sun_w, 4.0e5)
    mm = PL.build_planet(sc, "brightice", radius=SY.MIMAS_R / U, location=tuple(M @ mim), detail="close", seed=7,
                         name="Mimas", axial_tilt_deg=0.0, rot_period_s=1.0e9)
    PL.add_big_crater(mm, M @ n_h, radius_km=65.0, rim_km=5.0, floor_km=5.0, peak_km=6.0, unit_km=U)  # Гершель 130 км
    import bmesh
    me = bpy.data.meshes.new("IceBall")
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=192, v_segments=96, radius=SY.ICE_BALL_R_KM / U)
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    ib = bpy.data.objects.new("IceBall", me)
    C.link(ib, "Planets")
    ib.location = M @ ball
    me.materials.append(_ice_ball_material("IceBallMat"))
    # «сжать весь лёд в один шар»: шар собирается на словах «into one ball» (ease-out)
    g0, g1 = V5["grow"]
    for f in range(g0, g1 + 1, 2):
        u = (f - g0) / float(g1 - g0)
        k = max(1.0 - (1.0 - u) ** 3, 1e-3)
        ib.scale = (k, k, k)
        ib.keyframe_insert("scale", frame=f)
    A.set_interpolation(ib, "LINEAR", extrapolate="CONSTANT")
    labels = [
        LB.build_label("Lbl_Mimas", "MIMAS · 396 km", tuple(M @ mim), cam, px=42, offset_px=(0, -300),
                       color=LABEL_COL),
        LB.build_label("Lbl_Ball", "ALL RING ICE · ~320 km", tuple(M @ ball), cam, px=42, offset_px=(0, -250),
                       color=(0.80, 0.90, 1.0)),
    ]
    for lb, fi in zip(labels, (40, V5["grow"][1])):
        LB.key_screen_size(lb, cam, 1, n, step=4)
        LB.key_fade(lb, 1.0, f_in=fi, f_out=None, length=24)
    view = (M @ look - Vector(fn(1)[0])).normalized()
    stars = SKY.build_sky(sc, cam, 0.0, gal=SKY.gal_for_view(view, tilt_deg=30.0, l_center_deg=140.0),
                          star_brightness=0.7)
    S.finish(sc, [stars, disk], denoise="far", star_samples=32)
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
