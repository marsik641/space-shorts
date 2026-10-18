"""Небо: звёздное поле (point cloud на «бесконечности»), Млечный Путь (HDR в world), ориентация галактики.

Галактическая система координат (общая для звёзд и Млечного Пути):
    в «галактическом» кадре +X — на центр Галактики (l=0, b=0), +Z — северный галактический полюс.
    В мир переводится поворотом `galactic_plane_euler` (XYZ): world = R(euler) @ gal.

Типовое использование (одинаковое небо во всех шотах при разной экспозиции):
    stars = sky.build_sky(sc, cam, exposure=ex, gal=sky.gal_for_view(view_dir, tilt_deg=-30, l_center_deg=60))
    ...
    render.setup_star_layer(sc, stars)          # после создания всех объектов
Компоузер шота со звёздами: render.setup_compositor(sc, dispersion=sky.STAR_SAFE_DISPERSION).

Ассеты: assets/milkyway.exr (RGB — свет звёзд без пыли, A — оптическая толщина пыли, half/ZIP),
assets/milkyway_maps.npz (tau/яркость для звёзд). Генерируются при первом вызове (~8 с), кеш по MW_VERSION.
"""
import json
import math
import os

import bpy
import bmesh
import numpy as np
from mathutils import Euler, Matrix, Vector

from . import core as C

# Ориентация галактической плоскости по умолчанию (полоса наклонена к плоскости орбит)
GAL_EULER = (math.radians(62.0), math.radians(-18.0), math.radians(35.0))

MW_PATH = os.path.join(C.ASSETS, "milkyway.exr")
MW_MAPS_PATH = os.path.join(C.ASSETS, "milkyway_maps.npz")   # tau и яркость (для звёзд), 1024x2048
MW_META_PATH = os.path.join(C.ASSETS, "milkyway.json")
MW_SIZE = (4096, 2048)
MW_VERSION = 12          # менять при правке генератора -> текстура пересоберётся
_MW_GAIN = 0.06         # strength=1 -> ядро полосы ~0.06 лин. (диффуз ×0.65 + звёзды полосы) (очень тускло, пульсар на порядки ярче)
_REDDEN = (0.88, 1.0, 1.15)  # относительная экстинкция R,G,B (покраснение за пылью)
DUST_CAP = 2.5          # насыщение пыли: tau_eff = cap·(1−exp(−tau/cap)) -> в прожилках остаётся ~5–10% света
RESOLVED_FRAC = 0.35    # доля света полосы, отданная разрешённым звёздам (диффузный фон слабее на столько же)
# дисперсия компоузера, безопасная для звёзд: render.setup_compositor(dispersion=0.012) превращает
# звёзды у краёв кадра в радужные штрихи 5–7 px. В шотах со звёздами: render.setup_compositor(sc, dispersion=sky.STAR_SAFE_DISPERSION)
STAR_SAFE_DISPERSION = 0.002


# ---------------------------------------------------------------- галактические координаты

def galactic_to_world(l_deg, b_deg, galactic_plane_euler=GAL_EULER):
    """Единичный вектор в мире для галактических (l, b) в градусах."""
    l, b = math.radians(l_deg), math.radians(b_deg)
    g = Vector((math.cos(b) * math.cos(l), math.cos(b) * math.sin(l), math.sin(b)))
    return (Euler(galactic_plane_euler, "XYZ").to_matrix() @ g).normalized()


def galactic_camera_matrix(l_deg, b_deg, roll_deg=0.0, loc=(0, 0, 0), galactic_plane_euler=GAL_EULER):
    """matrix_world камеры, смотрящей на (l, b); roll=0 -> полоса горизонтальна, roll=30 -> диагональ."""
    f = galactic_to_world(l_deg, b_deg, (0, 0, 0))
    up0 = Vector((0, 0, 1))
    right = f.cross(up0)
    if right.length < 1e-6:
        right = Vector((0, 1, 0))
    right.normalize()
    up = right.cross(f).normalized()
    rot = Matrix.Rotation(math.radians(roll_deg), 3, f)
    right, up = rot @ right, rot @ up
    m = Matrix((right, up, -f)).transposed()               # столбцы: X=вправо, Y=вверх, Z=назад
    m = Euler(galactic_plane_euler, "XYZ").to_matrix() @ m
    out = m.to_4x4()
    out.translation = Vector(loc)
    return out


# ---------------------------------------------------------------- Млечный Путь: генерация текстуры

def _spectral_noise(rng, h, w, beta, stretch=1.0, cutoff=0.35, kmin=0.0):
    """Периодический шум со спектром k^-beta (FFT), полоса [kmin, cutoff] цикл/пиксель.
    stretch>1 — вытянут вдоль l (оси X). Нормирован: среднее 0, std=1."""
    wn = rng.standard_normal((h, w)).astype(np.float32)
    F = np.fft.rfft2(wn)
    ky = np.fft.fftfreq(h).astype(np.float32)[:, None]
    kx = np.fft.rfftfreq(w).astype(np.float32)[None, :]
    k = np.sqrt((kx * stretch) ** 2 + ky ** 2)
    k[0, 0] = 1.0
    amp = k ** (-beta * 0.5) * np.exp(-(k / cutoff) ** 2)
    if kmin > 0:
        amp *= 1.0 - np.exp(-(k / kmin) ** 2)
    amp[0, 0] = 0.0
    n = np.fft.irfft2(F * amp, s=(h, w)).astype(np.float32)
    n -= n.mean()
    n /= n.std() + 1e-12
    return n


def _soft_tau(tau, cap=DUST_CAP):
    """Насыщение экстинкции (как в шейдере): реальные прожилки не чёрные — пропускают ~5–20%."""
    return cap * (1.0 - np.exp(-tau / cap))


def _milkyway_arrays(W, H, seed):
    """(light rgb [H,W,3] без пыли, tau [H,W]); строка 0 — b=-90° (низ картинки Blender), l=0 — центр."""
    rng = np.random.default_rng(seed)
    l = ((np.arange(W, dtype=np.float32) + 0.5) / W - 0.5) * 360.0
    b = ((np.arange(H, dtype=np.float32) + 0.5) / H - 0.5) * 180.0
    ld, bd = np.meshgrid(l, b)
    lr = np.radians(ld)
    abl = np.abs(ld)

    # волнистая средняя линия диска
    bmid = 0.8 * np.sin(lr + 0.7) + 0.4 * np.sin(3.0 * lr + 1.9)
    bb = bd - bmid

    K = 1.0 / 400.0                                            # убрать моды крупнее ~35°
    n_large = _spectral_noise(rng, H, W, 3.2, 2.0, 0.35, K)    # звёздные облака (крупные)
    n_mid = _spectral_noise(rng, H, W, 2.5, 2.4, 0.35, K * 2)  # звёздные облака (средние)
    n_d1 = _spectral_noise(rng, H, W, 3.0, 3.6, 0.35, K)       # пыль: крупные облака вдоль полосы
    n_d2 = _spectral_noise(rng, H, W, 2.3, 1.6, 0.25, K * 3)   # пыль: клочья/волокна
    n_wob = _spectral_noise(rng, H, W, 3.6, 6.0, 0.35, K)      # изгиб пылевой полосы
    n_fine = _spectral_noise(rng, H, W, 1.6, 1.0, 0.15)        # неразрешённые звёзды (мягкое зерно)
    n_hii = _spectral_noise(rng, H, W, 2.6, 1.2, 0.35, K)

    # --- свет звёзд (тонкий диск доминирует, фон вне полосы почти чёрный)
    f_l = (0.13 + 0.87 * np.exp(-(ld / 60.0) ** 2)
           + 0.22 * np.exp(-((abl - 78.0) / 20.0) ** 2))      # Лебедь/Киль — вторичные максимумы
    sig = (3.0 + 2.8 * np.exp(-(ld / 35.0) ** 2)) * np.exp(0.15 * n_large)
    thin = np.exp(-(bb / sig) ** 2)
    thick = np.exp(-np.abs(bb) / 8.0)
    disk = f_l * (0.88 * thin + 0.12 * thick)
    clouds = np.exp(0.6 * n_large + 0.45 * n_mid - 0.28)       # лог-нормальные звёздные облака, среднее ~1
    q = (ld / 11.0) ** 2 + (bb / 8.5) ** 2
    bulge = 3.0 * np.exp(-q ** 0.8) + 0.18 * np.exp(-((ld / 22.0) ** 2 + (bb / 12.0) ** 2))
    grain = np.exp(0.10 * n_fine)
    light = (disk * clouds + bulge * np.exp(0.25 * n_mid)) * grain
    light = light ** 1.2 + 0.0012                              # контраст полосы к краям

    # --- пыль (оптическая толщина): лог-нормальные облака в слое вдоль средней линии
    A_l = (0.30 + 1.5 * np.exp(-(ld / 60.0) ** 2)
           + 1.1 * np.exp(-((ld - 70.0) / 20.0) ** 2))         # «Большой разлом» к Лебедю
    b_d = 0.5 + 0.9 * n_wob
    w_d = 1.6 + 1.6 * np.exp(-(ld / 40.0) ** 2)
    env = np.exp(-((bb - b_d) / w_d) ** 2) + 0.35 * np.exp(-np.abs(bb - b_d) / 6.0)
    field = np.exp(1.0 * n_d1 + 0.6 * n_d2 - 0.55)
    tau = np.minimum(A_l * env * field, 5.0)
    # редкие тёмные туманности вне плоскости
    tau += 1.2 * np.exp(-np.abs(bb) / 15.0) * np.maximum(0.0, n_d2 - 2.0) * (0.4 + f_l)
    tau = tau.astype(np.float32)

    # --- цвет: тёплый балдж, нейтральные рукава
    lw = np.array([0.2126, 0.7152, 0.0722], np.float32)
    warm = np.array([1.0, 0.85, 0.68], np.float32); warm /= warm @ lw      # кремовый, не сепия
    neut = np.array([0.92, 0.97, 1.04], np.float32); neut /= neut @ lw
    w = bulge / (bulge + disk * clouds + 1e-6)
    w = np.clip(0.6 * w + 0.1 * np.exp(-(ld / 30.0) ** 2), 0.0, 0.6)[..., None]
    rgb = light[..., None] * (neut * (1.0 - w) + warm * w)
    # слабые области HII (едва заметный розовый)
    hii = np.maximum(0.0, n_hii - 2.3) * thin * f_l * 0.12
    rgb += hii[..., None] * np.array([1.0, 0.32, 0.42], np.float32)

    # нормировка: 99.7-й перцентиль видимой (с пылью) яркости в ядре -> 1
    vis = (rgb @ lw) * np.exp(-_soft_tau(tau))
    core = vis[(np.abs(bd) < 12) & (abl < 40)]
    rgb /= max(1e-6, float(np.percentile(core, 99.7)))
    return np.ascontiguousarray(rgb, np.float32), tau


def _ensure_milkyway(seed=3, regenerate=False, scene=None):
    """Создаёт assets/milkyway.exr (RGB — свет, A — tau пыли) и milkyway_maps.npz, если их нет/устарели."""
    meta = {"seed": seed, "size": list(MW_SIZE), "version": MW_VERSION}
    ok = (not regenerate and os.path.exists(MW_PATH) and os.path.exists(MW_MAPS_PATH)
          and os.path.exists(MW_META_PATH))
    if ok:
        try:
            with open(MW_META_PATH) as f:
                ok = json.load(f) == meta
        except Exception:
            ok = False
    if ok:
        return MW_PATH
    os.makedirs(C.ASSETS, exist_ok=True)
    W, H = MW_SIZE
    rgb, tau = _milkyway_arrays(W, H, seed)
    rgba = np.empty((H, W, 4), np.float32)
    rgba[..., :3] = rgb
    rgba[..., 3] = tau
    img = bpy.data.images.new("MilkyWay_gen", width=W, height=H, alpha=True, float_buffer=True)
    img.alpha_mode = "CHANNEL_PACKED"
    img.pixels.foreach_set(rgba.ravel())
    # запись через save_render: half float + ZIP (без потерь: DWAB давал блоки 8×8 на теле), EXR линейный
    sc = scene or bpy.context.scene
    ims = sc.render.image_settings
    keep = (ims.media_type, ims.file_format, ims.color_mode, ims.color_depth, ims.exr_codec)
    ims.media_type = "IMAGE"
    ims.file_format = "OPEN_EXR"
    ims.color_mode = "RGBA"
    ims.color_depth = "16"
    ims.exr_codec = "ZIP"
    try:
        img.save_render(MW_PATH, scene=sc)
    finally:
        ims.media_type, ims.file_format = keep[0], keep[1]
        ims.color_mode, ims.color_depth, ims.exr_codec = keep[2], keep[3], keep[4]
    bpy.data.images.remove(img)
    # карты для звёзд: экстинкция и видимая яркость (1024x2048)
    lum = (rgb @ np.array([0.2126, 0.7152, 0.0722], np.float32)) * np.exp(-_soft_tau(tau))
    t2 = tau.reshape(H // 2, 2, W // 2, 2).mean((1, 3))
    l2 = lum.reshape(H // 2, 2, W // 2, 2).mean((1, 3))
    np.savez(MW_MAPS_PATH, tau=t2.astype(np.float16), lum=l2.astype(np.float32))
    with open(MW_META_PATH, "w") as f:
        json.dump(meta, f)
    return MW_PATH


def build_milky_way(scene, strength=1.0, galactic_plane_euler=GAL_EULER, seed=3, grain=0.12,
                    dust_detail=0.9, regenerate=False, resolved_frac=RESOLVED_FRAC, dust_cap=DUST_CAP):
    """World-шейдер: эквиректангулярная HDR Млечного Пути. strength=1 — очень тускло (калибровано).

    Пыль применяется в шейдере: tau_d = tau·detail (detail — фрактальный шум по направлению: чёткие края
    прожилок и на 85 мм), насыщение tau_eff = cap·(1−exp(−tau_d/cap)), col = light·exp(−tau_eff·k_rgb):
    прожилки пропускают ~5–10% (не чёрные дыры).
    resolved_frac — доля света полосы, которую несут звёзды-«полоса» build_starfield (тот же resolved_frac
    и mw_strength=strength туда же): диффузный фон ослаблен на (1−resolved_frac).
    grain — едва заметная «зернистость» неразрешённых звёзд (мельче пикселя на 24 мм, ~2 px на 85 мм).
    """
    path = _ensure_milkyway(seed, regenerate, scene)
    img = bpy.data.images.load(path, check_existing=True)
    img.alpha_mode = "CHANNEL_PACKED"
    try:
        img.colorspace_settings.name = "Linear Rec.709"
    except TypeError:
        pass

    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    N, L = nt.nodes, nt.links
    N.clear()
    out = N.new("ShaderNodeOutputWorld"); out.location = (1300, 0)
    bg = N.new("ShaderNodeBackground"); bg.location = (1100, 0)
    tc = N.new("ShaderNodeTexCoord"); tc.location = (-900, 0)
    # мир -> галактический кадр
    vr = N.new("ShaderNodeVectorRotate"); vr.location = (-700, 0)
    vr.rotation_type = "EULER_XYZ"
    vr.invert = True
    vr.inputs["Rotation"].default_value = galactic_plane_euler
    L.new(tc.outputs["Generated"], vr.inputs["Vector"])
    sep = N.new("ShaderNodeSeparateXYZ"); sep.location = (-500, 0)
    L.new(vr.outputs[0], sep.inputs[0])
    # u = atan2(y,x)/2pi + 0.5 ; v = asin(z)/pi + 0.5 (своя развёртка, совпадает с генератором)
    at = C.math_node(N, L, "ARCTAN2", sep.outputs[1], sep.outputs[0], loc=(-300, 100))
    u = C.math_node(N, L, "MULTIPLY_ADD", at, 1.0 / (2.0 * math.pi), loc=(-150, 100))
    u.node.inputs[2].default_value = 0.5
    zc = C.math_node(N, L, "MINIMUM", C.math_node(N, L, "MAXIMUM", sep.outputs[2], -1.0, loc=(-300, -100)),
                     1.0, loc=(-200, -100))
    asn = C.math_node(N, L, "ARCSINE", zc, loc=(-100, -100))
    v = C.math_node(N, L, "MULTIPLY_ADD", asn, 1.0 / math.pi, loc=(0, -100))
    v.node.inputs[2].default_value = 0.5
    cmb = N.new("ShaderNodeCombineXYZ"); cmb.location = (150, 0)
    L.new(u, cmb.inputs[0]); L.new(v, cmb.inputs[1])
    tex = N.new("ShaderNodeTexImage"); tex.location = (300, 0)
    tex.image = img
    tex.interpolation = "Cubic"
    tex.extension = "REPEAT"
    L.new(cmb.outputs[0], tex.inputs["Vector"])

    # фрактальная детализация пыли: tau * (1 - d + 2d*noise)
    nd = N.new("ShaderNodeTexNoise"); nd.location = (-300, -350)
    nd.noise_dimensions = "3D"
    nd.inputs["Scale"].default_value = 140.0                     # мельчайшая октава ~2 px на 85 мм/1080p
    nd.inputs["Detail"].default_value = 4.0
    nd.inputs["Roughness"].default_value = 0.62
    nd.inputs["Distortion"].default_value = 0.25
    L.new(vr.outputs[0], nd.inputs["Vector"])
    dm = C.math_node(N, L, "MULTIPLY_ADD", nd.outputs["Fac"], 2.0 * dust_detail, loc=(-100, -350))
    dm.node.inputs[2].default_value = 1.0 - dust_detail
    dm = C.math_node(N, L, "MAXIMUM", dm, 0.0, loc=(0, -350))
    tau = C.math_node(N, L, "MULTIPLY", tex.outputs["Alpha"], dm, loc=(300, -300))
    # насыщение: cap·(1−exp(−tau/cap))
    tau = C.math_node(N, L, "EXPONENT", C.math_node(N, L, "MULTIPLY", tau, -1.0 / dust_cap, loc=(380, -300)),
                      loc=(440, -300))
    tau = C.math_node(N, L, "MULTIPLY_ADD", tau, -dust_cap, loc=(500, -300))
    tau.node.inputs[2].default_value = dust_cap
    ext = N.new("ShaderNodeCombineXYZ"); ext.location = (800, -300)
    for i, k in enumerate(_REDDEN):
        e = C.math_node(N, L, "EXPONENT", C.math_node(N, L, "MULTIPLY", tau, -k, loc=(600, -250 - 80 * i)),
                        loc=(700, -250 - 80 * i))
        L.new(e, ext.inputs[i])
    col = N.new("ShaderNodeVectorMath"); col.operation = "MULTIPLY"; col.location = (900, 0)
    L.new(tex.outputs["Color"], col.inputs[0]); L.new(ext.outputs[0], col.inputs[1])

    # зерно неразрешённых звёзд (стабильно: зависит только от направления)
    nz = N.new("ShaderNodeTexNoise"); nz.location = (-300, -650)
    nz.noise_dimensions = "3D"
    nz.inputs["Scale"].default_value = 2500.0                    # ~2 px на 85 мм; на 24 мм мельче пикселя —
    nz.inputs["Detail"].default_value = 0.0                      # усредняется фильтром пикселя (без мерцания)
    nz.inputs["Roughness"].default_value = 0.6
    L.new(vr.outputs[0], nz.inputs["Vector"])
    g = C.math_node(N, L, "MULTIPLY_ADD", nz.outputs["Fac"], 2.0 * grain, loc=(-100, -650))
    g.node.inputs[2].default_value = 1.0 - grain
    sc_ = N.new("ShaderNodeVectorMath"); sc_.operation = "SCALE"; sc_.location = (1000, 0)
    L.new(col.outputs[0], sc_.inputs[0])
    L.new(C.math_node(N, L, "MAXIMUM", g, 0.0, loc=(100, -650)), sc_.inputs["Scale"])
    L.new(sc_.outputs[0], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = strength * _MW_GAIN * (1.0 - resolved_frac)
    L.new(bg.outputs[0], out.inputs["Surface"])
    return world


# ---------------------------------------------------------------- звёздное поле

_LUMA = np.array([0.2126, 0.7152, 0.0722])


def _bb_table():
    ts = np.linspace(2500.0, 30000.0, 512)
    rgb = np.array([C.blackbody_rgb(t) for t in ts])
    return ts, rgb


def _pixel_angle(scene, lens):
    """Угловой размер пикселя (рад) при текущем разрешении сцены (с учётом процента)."""
    r = scene.render
    rx = r.resolution_x * r.resolution_percentage / 100.0
    ry = r.resolution_y * r.resolution_percentage / 100.0
    fov = 2.0 * math.atan(36.0 / (2.0 * lens))
    return fov / max(rx, ry)


def _mags(rng, n, m0, m1, k=0.45):
    """Звёздные величины с N(<m) ∝ 10^(k m): много слабых, мало ярких."""
    a0, a1 = 10.0 ** (k * m0), 10.0 ** (k * m1)
    return np.log10(a0 + rng.random(n) * (a1 - a0)) / k


# ---------------------------------------------------------------- реальные яркие звёзды
# ICRS -> галактические (Hipparcos, ESA 1997, т. 1, §1.5.3)
A_ICRS_GAL = np.array(((-0.0548755604162154, -0.8734370902348850, -0.4838350155487132),
                       (0.4941094278755837, -0.4448296299600112, 0.7469822444972189),
                       (-0.8676661490190047, -0.1980763734312015, 0.4559837761750669)))
# (имя, RA°, Dec° J2000, V, B−V) — Орион и соседи (Yale Bright Star Catalogue / Hipparcos, округлено)
BRIGHT_ORION = (
    ("Betelgeuse", 88.793, 7.407, 0.42, 1.85), ("Rigel", 78.634, -8.202, 0.13, -0.03),
    ("Bellatrix", 81.283, 6.350, 1.64, -0.22), ("Alnilam", 84.053, -1.202, 1.69, -0.18),
    ("Alnitak", 85.190, -1.943, 1.77, -0.21), ("Mintaka", 83.002, -0.299, 2.23, -0.22),
    ("Saiph", 86.939, -9.670, 2.09, -0.17), ("Meissa", 83.784, 9.934, 3.33, -0.16),
    ("Hatysa", 83.858, -5.910, 2.77, -0.24), ("Pi3 Ori", 72.460, 6.961, 3.19, 0.45),
    ("Sirius", 101.287, -16.716, -1.46, 0.00), ("Procyon", 114.825, 5.225, 0.34, 0.42),
    ("Aldebaran", 68.980, 16.509, 0.86, 1.54), ("Elnath", 81.573, 28.608, 1.65, -0.13),
    ("Arneb", 83.183, -17.822, 2.58, 0.21), ("Nihal", 82.061, -20.759, 2.84, 0.82),
    ("Cursa", 76.963, -5.086, 2.79, 0.13), ("Mirzam", 95.675, -17.956, 1.98, -0.23),
    ("Adhara", 104.656, -28.972, 1.50, -0.21), ("Wezen", 107.098, -26.393, 1.83, 0.68),
    ("Eps Lep", 76.365, -22.371, 3.19, 1.46), ("Mu Lep", 78.233, -16.206, 3.31, -0.11),
)


def radec_to_gal(ra_deg, dec_deg):
    """Единичный вектор в галактической системе (как у звёзд/Млечного Пути) по RA/Dec J2000."""
    ra, de = np.radians(ra_deg), np.radians(dec_deg)
    v = np.stack([np.cos(de) * np.cos(ra), np.cos(de) * np.sin(ra), np.sin(de)], -1)
    return v @ A_ICRS_GAL.T


def _bv_temp(bv):
    """Температура по B−V (Ballesteros 2012)."""
    bv = np.asarray(bv, float)
    return 4600.0 * (1.0 / (0.92 * bv + 1.7) + 1.0 / (0.92 * bv + 0.62))


def build_starfield(scene, camera=None, n_stars=300000, seed=7, brightness=1.0,
                    galactic_plane_euler=GAL_EULER, band_frac=0.75, mag_limit=11.0, star_px=0.9,
                    contrast=1.0, lens=None, mw_seed=3, mw_strength=1.0, resolved_frac=RESOLVED_FRAC,
                    band_mag=(7.0, 13.5), coll="Env", catalog=None, catalog_cone_deg=40.0, catalog_cut=3.6):
    """Point cloud звёзд на сфере большого радиуса (Copy Location к камере).

    catalog — реальные звёзды [(имя, RA°, Dec°, V, B−V)] (например BRIGHT_ORION): ставятся по настоящим
    координатам; процедурные звёзды ярче catalog_cut в конусе catalog_cone_deg вокруг центра каталога убираются
    (созвездие узнаётся без «лишних» ярких). Без catalog поле — как раньше (ep001 не меняется).

    Две популяции:
      «поле» (1−band_frac): все величины до mag_limit, изотропно + концентрация к плоскости (сильнее для
        слабых); за пылью приглушаются слабо (это в основном звёзды переднего плана — они и «населяют» прожилки);
      «полоса» (band_frac): слабые звёзды band_mag, плотность по карте видимой яркости Млечного Пути.
        Их суммарный свет = resolved_frac × свет полосы (build_milky_way с тем же strength=mw_strength и
        resolved_frac ослабляет диффузный фон на столько же). Яркость полосы масштабируется физично
        (∝ 1/телесный угол пикселя): на 85 мм облака распадаются на зернистое море звёзд, на 24 мм
        сливаются в ровное свечение.
    Блеск — яркостью, не размером: угловой радиус точки = star_px пикселя текущего разрешения;
    ~50 самых ярких (mag<3) чуть крупнее (до ×1.6, поток сохраняется) — как в реальной оптике.
    Вызывать ПОСЛЕ setup_cycles(pct=...) и создания камеры; при смене объектива/процента — update_starfield().
    Компоузер шота: render.setup_compositor(sc, dispersion=STAR_SAFE_DISPERSION) (0.012 даёт радужные штрихи).
    """
    rng = np.random.default_rng(seed)
    n = int(n_stars)
    nb = int(n * band_frac)
    nf = n - nb
    m0 = -1.0
    _ensure_milkyway(mw_seed, scene=scene)
    maps = np.load(MW_MAPS_PATH)
    tau_map = maps["tau"].astype(np.float32)
    lum_map = maps["lum"].astype(np.float64)
    th, tw = tau_map.shape

    # --- популяция «поле»
    mag_f = _mags(rng, nf, m0, mag_limit)
    faint = (mag_f - m0) / (mag_limit - m0)                   # 0 — яркие (близкие), 1 — слабые (далёкие)
    p_disk = 0.25 + 0.60 * faint
    lon = rng.uniform(-math.pi, math.pi, nf)
    lat = np.arcsin(rng.uniform(-1.0, 1.0, nf))
    disk = rng.random(nf) < p_disk
    nd = int(disk.sum())
    ld = np.where(rng.random(nd) < 0.4, rng.normal(0.0, math.radians(50.0), nd),
                  rng.uniform(-math.pi, math.pi, nd))
    lon[disk] = (ld + math.pi) % (2 * math.pi) - math.pi
    lat[disk] = rng.laplace(0.0, math.radians(3.0) + math.radians(12.0) * (1 - faint[disk]), nd)
    lat = np.clip(lat, -math.pi / 2, math.pi / 2)
    behind_f = 0.05 + 0.5 * faint * disk
    flux_f = 10.0 ** (-0.4 * contrast * (mag_f - 6.0))

    # --- популяция «полоса»: выборка по карте видимой яркости (с учётом телесного угла)
    bcen = ((np.arange(th) + 0.5) / th - 0.5) * math.pi
    w = (lum_map * np.cos(bcen)[:, None]).ravel()
    w = np.maximum(w - np.percentile(w, 60), 0.0)              # только сама полоса
    idx = rng.choice(w.size, size=nb, p=w / w.sum())
    jj, ii = np.divmod(idx, tw)
    lon_b = ((ii + rng.random(nb)) / tw - 0.5) * 2 * math.pi
    lat_b = ((jj + rng.random(nb)) / th - 0.5) * math.pi
    mag_b = _mags(rng, nb, band_mag[0], band_mag[1], k=0.55)
    flux_b = 10.0 ** (-0.4 * contrast * (mag_b - 6.0))
    if resolved_frac > 0 and nb > 0:
        # калибровка: средняя яркость звёзд полосы = resolved_frac × диффузный свет (при 35 мм/960 px;
        # для полосы усиление ∝ 1/Ω_px, так что равенство держится при любом объективе/проценте)
        sky = resolved_frac * mw_strength * _MW_GAIN * w.sum() * (2 * math.pi / tw) * (math.pi / th)
        flux_b *= sky / (flux_b.sum() * _PX_OMEGA_REF)

    lon = np.concatenate([lon, lon_b]); lat = np.concatenate([lat, lat_b])
    mag = np.concatenate([mag_f, mag_b])
    flux = np.concatenate([flux_f, flux_b])
    behind = np.concatenate([behind_f, np.full(nb, 0.25)])     # полоса уже выбрана по яркости с пылью
    pop = np.concatenate([np.zeros(nf), np.ones(nb)])
    dirs = np.stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)], 1)
    ii = np.clip(((lon / (2 * math.pi) + 0.5) * tw).astype(int), 0, tw - 1)
    jj = np.clip(((lat / math.pi + 0.5) * th).astype(int), 0, th - 1)
    flux *= np.exp(-0.8 * tau_map[jj, ii] * behind)            # далёкие звёзды прячутся за пылью
    # самые яркие — чуть крупнее (ореол оптики), поток сохраняется
    sz = 1.0 + 0.6 * np.clip((3.0 - mag) / 4.0, 0.0, 1.0)
    flux /= sz ** 2

    # --- цвет по температуре: большинство F/G/K (слегка тёплые), немного A/B (голубоватые), M (оранжевые)
    r = rng.random(n)
    temp = np.where(r < 0.12, rng.uniform(3200, 4200, n),          # K-M
           np.where(r < 0.40, rng.uniform(4200, 5300, n),          # K-G
           np.where(r < 0.80, rng.uniform(5300, 6800, n),          # G-F
           np.where(r < 0.93, rng.uniform(6800, 9500, n),          # F-A
                    rng.uniform(9500, 25000, n)))))                # B
    ts, tab = _bb_table()
    rgb = np.stack([np.interp(temp, ts, tab[:, c]) for c in range(3)], 1)
    rgb /= np.array(C.blackbody_rgb(6500))                         # баланс белого: 6500 K -> белый
    sat = 0.35 + 0.30 * np.clip(1.0 - (mag + 1.0) / 8.0, 0, 1)     # у ярких цвет заметнее
    rgb = sat[:, None] * rgb + (1 - sat[:, None]) * (rgb @ _LUMA)[:, None]
    rgb /= (rgb @ _LUMA)[:, None]

    if catalog:
        # реальные звёзды: убрать процедурные яркие в конусе вокруг каталога, добавить настоящие
        cat_dirs = radec_to_gal([c[1] for c in catalog], [c[2] for c in catalog])
        ctr = cat_dirs.mean(0)
        ctr /= np.linalg.norm(ctr)
        keep = ~((dirs @ ctr > math.cos(math.radians(catalog_cone_deg))) & (mag < catalog_cut))
        dirs, flux, mag, rgb, pop, sz = dirs[keep], flux[keep], mag[keep], rgb[keep], pop[keep], sz[keep]
        cm = np.array([c[3] for c in catalog])
        csz = 1.0 + 0.6 * np.clip((3.0 - cm) / 4.0, 0.0, 1.0)
        cflux = 10.0 ** (-0.4 * contrast * (cm - 6.0)) / csz ** 2
        ts, tab = _bb_table()
        ct = _bv_temp([c[4] for c in catalog])
        crgb = np.stack([np.interp(ct, ts, tab[:, k]) for k in range(3)], 1) / np.array(C.blackbody_rgb(6500))
        csat = 0.35 + 0.30 * np.clip(1.0 - (cm + 1.0) / 8.0, 0, 1)
        crgb = csat[:, None] * crgb + (1 - csat[:, None]) * (crgb @ _LUMA)[:, None]
        crgb /= (crgb @ _LUMA)[:, None]
        dirs = np.concatenate([dirs, cat_dirs]); flux = np.concatenate([flux, cflux])
        rgb = np.concatenate([rgb, crgb]); pop = np.concatenate([pop, np.zeros(len(catalog))])
        sz = np.concatenate([sz, csz]); mag = np.concatenate([mag, cm])
        n = len(dirs)

    pc = bpy.data.pointclouds.new("Stars")
    pc.resize(n)
    pc.attributes["position"].data.foreach_set("vector", dirs.astype(np.float32).ravel())
    ra = pc.attributes.get("radius") or pc.attributes.new("radius", "FLOAT", "POINT")
    ra.data.foreach_set("value", np.ones(n, np.float32))
    for nm, typ, val in (("star_col", "FLOAT_VECTOR", rgb), ("star_flux", "FLOAT", flux),
                         ("star_pop", "FLOAT", pop), ("star_sz", "FLOAT", sz)):
        a = pc.attributes.new(nm, typ, "POINT")
        a.data.foreach_set("vector" if typ == "FLOAT_VECTOR" else "value", val.astype(np.float32).ravel())
    ob = bpy.data.objects.new("Stars", pc)
    C.link(ob, coll)
    ob.rotation_mode = "XYZ"
    ob.rotation_euler = galactic_plane_euler
    for attr in ("visible_diffuse", "visible_glossy", "visible_transmission",
                 "visible_volume_scatter", "visible_shadow"):
        setattr(ob, attr, False)
    if camera is not None:
        con = ob.constraints.new("COPY_LOCATION")
        con.target = camera

    mat, N, L, out = C.new_material("Stars")
    mat.cycles.emission_sampling = "NONE"                         # 3e5 точек не идут в дерево источников
    at_c = N.new("ShaderNodeAttribute"); at_c.attribute_name = "star_col"; at_c.location = (-400, 100)
    at_f = N.new("ShaderNodeAttribute"); at_f.attribute_name = "star_flux"; at_f.location = (-400, -100)
    at_p = N.new("ShaderNodeAttribute"); at_p.attribute_name = "star_pop"; at_p.location = (-600, -300)
    gain = N.new("ShaderNodeValue"); gain.name = "StarGain"; gain.location = (-600, -450)
    gainb = N.new("ShaderNodeValue"); gainb.name = "StarGainBand"; gainb.location = (-600, -550)
    # усиление по популяции: поле -> StarGain, полоса -> StarGainBand
    g = N.new("ShaderNodeMix"); g.data_type = "FLOAT"; g.location = (-300, -400)
    L.new(at_p.outputs["Fac"], g.inputs["Factor"])
    L.new(gain.outputs[0], g.inputs["A"]); L.new(gainb.outputs[0], g.inputs["B"])
    em = N.new("ShaderNodeEmission"); em.location = (300, 0)
    L.new(at_c.outputs["Vector"], em.inputs["Color"])
    L.new(C.math_node(N, L, "MULTIPLY", at_f.outputs["Fac"], g.outputs["Result"], loc=(0, -150)),
          em.inputs["Strength"])
    # прозрачная + эмиссия: точка только добавляет свет и не заслоняет Млечный Путь (иначе — чёрные точки)
    tr = N.new("ShaderNodeBsdfTransparent"); tr.location = (300, 150)
    add = N.new("ShaderNodeAddShader"); add.location = (450, 0)
    L.new(tr.outputs[0], add.inputs[0]); L.new(em.outputs[0], add.inputs[1])
    L.new(add.outputs[0], out.inputs["Surface"])
    pc.materials.append(mat)

    ob["star_px"] = star_px
    ob["brightness"] = brightness
    update_starfield(scene, ob, camera, lens)
    return ob


# телесный угол пикселя при 35 мм, 960 px по ширине (опорный для калибровки полосы)
_PX_OMEGA_REF = (2.0 * math.atan(18.0 / 35.0) / 960.0) ** 2


def update_starfield(scene, stars, camera=None, lens=None):
    """Пересчитать радиус точек и нормировку яркости под текущий объектив/разрешение."""
    lens = lens or (camera.data.lens if camera is not None else 35.0)
    clip = camera.data.clip_end if camera is not None else 1.0e6
    R = min(5.0e4, 0.9 * clip)
    if camera is not None:
        # звёзды — Transparent+Emission: всё, что дальше сферы, будет «прошито» точками
        bpy.context.view_layer.update()
        cam_p = camera.matrix_world.translation
        far = max([(o.matrix_world.translation - cam_p).length + 0.5 * max(o.dimensions)
                   for o in scene.objects
                   if o.type in ("MESH", "LIGHT", "CURVES", "VOLUME", "CURVE") and o != stars] or [0.0])
        if clip < 1.0e4 or R < 20.0 * far:
            print(f"[sky] WARNING: звёздная сфера R={R:.0f} близко (clip_end={clip:.0f}, "
                  f"дальний объект {far:.0f}); поднимите camera.clip_end")
    px = _pixel_angle(scene, lens)
    star_px = float(stars.get("star_px", 0.9))
    pc = stars.data
    n = len(pc.points)
    dirs = np.empty(n * 3, np.float32)
    pc.attributes["position"].data.foreach_get("vector", dirs)
    dirs = dirs.reshape(-1, 3)
    dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
    pc.attributes["position"].data.foreach_set("vector", (dirs * R).astype(np.float32).ravel())
    sz = np.ones(n, np.float32)
    if pc.attributes.get("star_sz") is not None:
        pc.attributes["star_sz"].data.foreach_get("value", sz)
    rad = (R * np.tan(star_px * px * sz)).astype(np.float32)
    pc.attributes["radius"].data.foreach_set("value", rad)
    # яркость поля: сумма по пикселям = flux·(rx/960)²·(lens/35)^0.6 — превью 50% и финал 100% совпадают,
    # лёгкий рост с фокусным (апертура). Полоса: ∝ 1/Ω_px (физично) — средняя яркость не зависит от объектива.
    r_ = scene.render
    rx = r_.resolution_x * r_.resolution_percentage / 100.0
    b = float(stars.get("brightness", 1.0)) / (math.pi * star_px ** 2)
    nodes = pc.materials[0].node_tree.nodes
    nodes["StarGain"].outputs[0].default_value = b * (lens / 35.0) ** 0.6 * (rx / 960.0) ** 2
    if "StarGainBand" in nodes:
        nodes["StarGainBand"].outputs[0].default_value = b * _PX_OMEGA_REF / px ** 2
    pc.update_tag()
    return stars


# ---------------------------------------------------------------- удобные обёртки для шотов
def gal_for_view(view_dir, tilt_deg=30.0, l_center_deg=15.0):
    """Ориентация галактики: точка (l_center, b=0) — в направлении взгляда, полоса наклонена на tilt к горизонту кадра.
    l_center≈0 — балдж с пылевыми прожилками (насыщенно), 60–120 — спокойная полоса, 180 — антицентр (тускло)."""
    d = Vector(view_dir).normalized()
    z = Vector((0, 0, 1))
    up = (z - d * z.dot(d)).normalized()
    right = d.cross(up).normalized()
    t = math.radians(tilt_deg)
    n = (up * math.cos(t) + right * math.sin(t)).normalized()
    l = math.radians(l_center_deg)
    a = Vector((math.cos(l), math.sin(l), 0.0))
    c = Vector((0.0, 0.0, 1.0))
    G = Matrix((a, c.cross(a), c)).transposed()
    W = Matrix((d, n.cross(d), n)).transposed()
    return tuple((W @ G.transposed()).to_euler("XYZ"))


def build_sky(sc, cam, exposure, ref_exposure=0.4, mw_strength=0.45, gal=GAL_EULER, star_brightness=1.0,
              mag_limit=10.0, **star_kw):
    """Млечный Путь + звёзды с компенсацией экспозиции шота: небо одинаковой яркости во всех шотах
    (k = 2^(ref_exposure − exposure)). Вызывать после setup_cycles(pct=...) и создания камеры.
    Возвращает объект звёзд (передать в render.setup_star_layer)."""
    k = 2.0 ** (ref_exposure - exposure)
    build_milky_way(sc, strength=mw_strength * k, galactic_plane_euler=gal)
    return build_starfield(sc, camera=cam, galactic_plane_euler=gal, mw_strength=mw_strength * k,
                           brightness=star_brightness * k, mag_limit=mag_limit, **star_kw)
