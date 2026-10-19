"""Кольца планеты (эп. 004+): диск в плоскости экватора с реальным радиальным профилем оптической толщины.

    from spacekit.bodies import rings as RG
    rg = RG.build_rings(sc, "saturn", parent=g["root"], unit_km=1000.0, sun_dir=SUN)   # 1 ед. = 1000 км
    # rg["ring"] — меш-кольцо (ребёнок root планеты: плоскость XY root), rg["material"], rg["image"]

Профиль (PROFILES[kind], радиусы в км от центра планеты): нормальная оптическая толщина τ(r) по опорным точкам
(резкие края — две точки рядом), щели и ringlet'ы, альбедо частиц и цвет, пыль (τ_d) — для вида на просвет.
Из него — LUT 8192×2 (spacekit.lut: строка 0 — ϖ·цвет и τ, строка 1 — τ_d), мельче шага таблицы (~9 км) —
1D-шум по радиусу. Узор осесимметричный (без «спиц» и волн плотности по азимуту).

Шейдер — однократное рассеяние в плоском слое (μ — косинус к камере, μ0 — к Солнцу, α — фазовый угол):
    пропускание             T = exp(−τ/μ) — Transparent (и тень колец на планете: для луча тени μ = μ0)
    освещённая сторона      I/F = ϖP(α)/4 · μ0/(μ+μ0) · (1 − exp(−τ(1/μ + 1/μ0)))           — Diffuse
    неосвещённая сторона    I/F = ϖP(α)/4 · μ0/(μ−μ0) · (exp(−τ/μ) − exp(−τ/μ0))            — Translucent
Частицы — фаза ламбертовой сферы (сильно назад), пыль — Хеньи–Гринстейн g≈0.7 (вперёд: светится на просвет).
Diffuse/Translucent сами берут свет только со своей стороны: тень планеты на кольцах и свет Сатурна на
кольцах — честные (лампа и GI). ϖ — эффективное (с многократным рассеянием толстого кольца B), подобрано по
снимкам Cassini: B ярче всех, A чуть темнее, C и деление Кассини — тёмные серые.
hole=(cam, r0, r1) — вокруг камеры кольцо прозрачно (r0..r1 — плавный край, ед. сцены): там поле частиц
(spacekit.fx.ring_particles), диск — его продолжение до горизонта.
"""
import math

import bpy
import numpy as np

from .. import core as C
from .. import lut
from .planets import _NB

COLL = "Rings"

# Сатурн, радиусы — км от центра по PDS Ring-Moon Systems Node, «Vital Statistics for Saturn's Rings» (абсолютная
# шкала French et al. 2017; NSSDC расходится до 290 км у края A). τ — нормальная оптическая толщина: C 0.05–0.35,
# B 0.4–5 (B3 104–110 тыс. км — медиана 3.6), деление Кассини 0–0.2, A 0.4–1.0, F 0.01–0.2 (PDS); альбедо частиц
# C 0.12–0.30, B и A 0.4–0.6 (NSSDC) — здесь эффективное ϖ (с многократным рассеянием), подобрано по снимкам Cassini.
SATURN = dict(
    r0=66000.0, r1=141500.0, n=8192,
    tau=[
        (66900, 0.0), (74400, 0.0),                                   # D — только пыль
        (74491, 0.03), (76000, 0.05), (79000, 0.08), (82000, 0.07), (84500, 0.10), (85000, 0.08),
        (86500, 0.12), (88600, 0.10), (90000, 0.13), (91500, 0.16), (91965, 0.20),
        (91985, 1.10), (95000, 1.4), (98500, 1.8), (99500, 2.4), (103000, 3.0), (104000, 3.6),
        (110000, 4.2), (110500, 2.4), (114000, 2.0), (117000, 2.5), (117510, 2.2),   # B: внешний край резкий
        (117530, 0.02), (118200, 0.05), (119000, 0.08), (120000, 0.10), (120900, 0.13),
        (121500, 0.17), (122040, 0.20),                                # пандус деления Кассини (τ ≤ 0.2, PDS)
        (122060, 1.0), (124000, 0.92), (126000, 0.80), (128000, 0.68), (130000, 0.60),
        (132000, 0.55), (134000, 0.50), (136200, 0.45), (136760, 0.42),
        (136775, 0.0), (141500, 0.0),
    ],
    # плато кольца C (τ ~0.3–0.4)
    plateaus=[(84800, 85300, 0.35), (86300, 86700, 0.30), (88900, 89150, 0.28), (89300, 89900, 0.38),
              (90300, 90600, 0.30)],
    # щели: (центр, ширина, τ внутри) — PDS
    gaps=[(77837, 178, 0.0), (87476, 267, 0.0), (88704, 37, 0.0), (90210, 21, 0.0),           # C: Colombo, Maxwell, Bond, Dawes
          (117725, 410, 0.0), (118236, 96, 0.0), (118609, 38, 0.0), (118948, 37, 0.0),        # Кассини: Huygens, Herschel, Russell, Jeffreys
          (119404, 4, 0.0), (119965, 241, 0.0), (120237, 13, 0.0), (120310, 12, 0.0),         # Kuiper, Laplace, Bessel, Barnard
          (133584, 322, 0.0), (136504, 35, 0.0)],                                            # A: Encke (Пан), Keeler (Дафнис)
    # ringlet'ы: (центр, ширина, τ)
    ringlets=[(77878, 23, 2.0), (87510, 59, 2.0), (117815, 18, 1.5), (140224, 40, 0.3)],       # Titan, Maxwell, Huygens, ядро F
    # нерегулярная структура: (r0, r1, амплитуда ln τ, характерный масштаб км)
    texture=[(74491, 91975, 0.20, 120.0), (91975, 117510, 0.45, 260.0), (117530, 122050, 0.25, 60.0),
             (122060, 136770, 0.10, 90.0)],
    # полосы альбедо (у толстого B яркость от τ почти не зависит — структуру видно по альбедо): (r0, r1, амплитуда
    # ln ϖ, средняя ширина полосы км) — ступенчатые случайные полосы с резкими (~4 км) краями
    bands=[(74491, 91975, 0.22, 220.0), (91975, 99000, 0.20, 380.0), (99000, 104000, 0.26, 160.0),
           (104000, 110000, 0.16, 300.0), (110000, 117510, 0.24, 220.0), (117530, 122050, 0.30, 90.0),
           (122060, 130000, 0.06, 500.0), (130000, 136770, 0.10, 45.0)],
    # альбедо ϖ (эффективное) и цвет sRGB по радиусу: C и деление Кассини серее и темнее («dirtier», Cuzzi 2014);
    # зоны B: B1 (92–99 тыс.) темнее, B2 полосатое, B3 (104–110) — самое плотное и светлое, B4 чуть темнее
    albedo=[(74491, 0.30, (168, 160, 150)), (91900, 0.34, (176, 166, 152)), (92000, 0.72, (230, 208, 178)),
            (98900, 0.80, (236, 214, 184)), (99100, 0.90, (240, 218, 186)), (103900, 0.92, (242, 220, 188)),
            (104100, 1.00, (246, 226, 194)), (109900, 1.00, (246, 226, 194)), (110100, 0.90, (240, 218, 188)),
            (117500, 0.88, (238, 216, 186)), (117600, 0.34, (178, 172, 164)), (122000, 0.42, (196, 186, 172)),
            (122100, 0.72, (226, 212, 190)), (133400, 0.66, (222, 208, 188)), (136770, 0.62, (218, 206, 188))],
    # пыль τ_d (вид на просвет): D, деление Роша, F (139 826–140 612)
    dust=[(66900, 0.0), (67500, 2e-4), (73000, 3e-4), (74491, 1e-4), (136770, 0.0), (137000, 1e-4),
          (139000, 2e-4), (139826, 6e-4), (140224, 3e-3), (140612, 6e-4), (141400, 0.0)],
    dust_albedo=(0.85, 0.85, 0.88), dust_g=0.72,
)
PROFILES = {"saturn": SATURN}


def _smooth_box(r, a, b, edge):
    """1 внутри [a, b], плавные края шириной edge (км)."""
    return np.clip((r - a) / edge + 0.5, 0, 1) * np.clip((b - r) / edge + 0.5, 0, 1)


def profile_arrays(kind="saturn", seed=0):
    """Радиальный профиль: (r_km, τ, ϖ·rgb (n×3), τ_d) — для LUT и для расчётов в шотах."""
    p = PROFILES[kind]
    r = np.linspace(p["r0"], p["r1"], p["n"])
    pts = np.array(p["tau"], np.float64)
    tau = np.interp(r, pts[:, 0], pts[:, 1])
    rng = np.random.default_rng(500 + seed)
    for (a, b, amp, lam) in p["texture"]:
        # полосовой шум ln τ: сумма синусоид со случайными фазами, масштабы lam/4..lam·4
        m = (r >= a) & (r <= b)
        acc = np.zeros(m.sum())
        rr = r[m]
        for k in range(24):
            L = lam * 2.0 ** rng.uniform(-2.0, 2.0)
            acc += rng.normal() * np.sin(2 * np.pi * rr / L + rng.uniform(0, 2 * np.pi))
        acc /= np.sqrt(24.0)
        tau[m] *= np.exp(amp * acc)
    for (a, b, t) in p["plateaus"]:
        w = _smooth_box(r, a, b, 25.0)
        tau = tau * (1 - w) + t * w
    for (c, w, t) in p["gaps"]:
        k = _smooth_box(r, c - w / 2, c + w / 2, max(2.0, w * 0.06))
        tau = tau * (1 - k) + t * k
    for (c, w, t) in p["ringlets"]:
        k = _smooth_box(r, c - w / 2, c + w / 2, max(2.0, w * 0.15))
        tau = np.maximum(tau, t * k)
    al = np.array([a[1] for a in p["albedo"]])
    ra = np.array([a[0] for a in p["albedo"]])
    col = lut.srgb_to_linear(np.array([a[2] for a in p["albedo"]], np.float64) / 255.0)
    w = np.interp(r, ra, al)
    dr = (p["r1"] - p["r0"]) / (p["n"] - 1)
    for (a, b, amp, width) in p.get("bands", ()):
        # ступеньки: границы — пуассоновский поток со средним шагом width, уровни — нормальные; края ~4 км
        edges = [a]
        while edges[-1] < b:
            edges.append(edges[-1] + rng.exponential(width))
        lev = rng.normal(0.0, 1.0, len(edges))
        m = (r >= a) & (r <= b)
        idx = np.searchsorted(edges, r[m]) - 1
        step = lev[np.clip(idx, 0, len(lev) - 1)]
        k = max(1, int(round(4.0 / dr)))
        step = np.convolve(step, np.ones(k) / k, mode="same")
        w[m] *= np.exp(amp * step)
    rgb = np.stack([np.interp(r, ra, col[:, k]) for k in range(3)], -1) * w[:, None]
    d = np.array(p["dust"], np.float64)
    tau_d = np.interp(r, d[:, 0], d[:, 1])
    return r, np.clip(tau, 0.0, 20.0), rgb, tau_d


def _lut_rgba(kind, seed):
    r, tau, rgb, tau_d = profile_arrays(kind, seed)
    n = len(r)
    out = np.zeros((2, n, 4), np.float32)
    out[0, :, :3] = rgb
    out[0, :, 3] = tau
    out[1, :, 0] = tau_d
    out[1, :, 3] = 1.0
    return out


def tau_at(r_km, kind="saturn", seed=0):
    """τ на радиусе (по той же таблице, что в шейдере, без мелкого шума)."""
    r, tau, _rgb, _d = profile_arrays(kind, seed)
    return float(np.interp(r_km, r, tau))


def _annulus(name, r_in, r_out, segs, rings_n=8):
    verts, faces = [], []
    for i in range(rings_n + 1):
        rr = r_in + (r_out - r_in) * i / rings_n
        for k in range(segs):
            a = 2 * math.pi * k / segs
            verts.append((rr * math.cos(a), rr * math.sin(a), 0.0))
    for i in range(rings_n):
        for k in range(segs):
            j = (k + 1) % segs
            faces.append((i * segs + k, i * segs + j, (i + 1) * segs + j, (i + 1) * segs + k))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    return me


def _mat_rings(name, p, img, unit_km, sun_dir, lod, hole, grain=None):
    mat, nodes, links, out = C.new_material(name)
    b = _NB(mat.node_tree)
    tc = b.node("ShaderNodeTexCoord")
    x, y, _z = b.sep(tc.outputs["Object"])
    r_km = b.m("MULTIPLY", b.m("SQRT", b.m("ADD", b.m("MULTIPLY", x, x), b.m("MULTIPLY", y, y))), unit_km)
    u = b.m("DIVIDE", b.m("SUBTRACT", r_km, p["r0"]), p["r1"] - p["r0"])
    t0 = lut.image_node(b, img, u, 0.25)
    t1 = lut.image_node(b, img, u, 0.75)
    alb = t0.outputs["Color"]
    tau = t0.outputs["Alpha"]
    tau_d = b.sep(t1.outputs["Color"])[0]
    kk = b.node("ShaderNodeValue", name="albedo_k", label="albedo_k")
    kk.outputs[0].default_value = 1.25
    alb_k = kk.outputs[0]
    if lod < 2:
        # структура мельче шага таблицы: 1D-шумы по радиусу (λ ~ 30, 5, 0.8 км) — множители τ и альбедо
        acc = None
        for lam, amp in ((30.0, 0.22), (5.0, 0.14), (0.8, 0.10))[: (3 if lod == 0 else 1)]:
            nz = b.node("ShaderNodeTexNoise", {"W": b.m("DIVIDE", r_km, lam), "Scale": 1.0, "Detail": 3.0,
                                               "Roughness": 0.6}, noise_dimensions="1D").outputs[0]
            d = b.m("MULTIPLY", b.m("SUBTRACT", nz, 0.5), 2.0 * amp)
            acc = d if acc is None else b.m("ADD", acc, d)
        tau = b.m("MULTIPLY", tau, b.m("EXPONENT", acc))
        alb_k = b.m("MULTIPLY", alb_k, b.m("MULTIPLY_ADD", acc, 0.55, 1.0))
        if lod == 0:
            # «солома»: слабая неоднородность, вытянутая по азимуту (~15 км по радиусу × ~600 км по орбите)
            th = b.m("ARCTAN2", y, x)
            q = b.comb(b.m("DIVIDE", r_km, 15.0), b.m("MULTIPLY", th, b.m("DIVIDE", r_km, 600.0)), 0.0)
            st = b.noise(q, 1.0, detail=3, rough=0.55).outputs[0]
            alb_k = b.m("MULTIPLY", alb_k, b.m("MULTIPLY_ADD", b.m("SUBTRACT", st, 0.5), 0.16, 1.0))
    if grain is not None:
        # зерно неразрешённых глыб (кольцо изнутри, вдали от поля частиц): 2D-шум в ед. сцены, тени между глыбами
        gs, ga = grain
        gq = b.comb(b.m("DIVIDE", x, gs), b.m("DIVIDE", y, gs), 0.0)
        gn = b.noise(gq, 1.0, detail=4, rough=0.65).outputs[0]
        alb_k = b.m("MULTIPLY", alb_k, b.m("MAXIMUM", b.m("MULTIPLY_ADD", b.m("SUBTRACT", gn, 0.5), 2.0 * ga, 1.0), 0.05))
    alb = b.v("SCALE", alb, scale=alb_k)
    geo = b.node("ShaderNodeNewGeometry")
    sd = b.node("ShaderNodeCombineXYZ", name="sun_dir", label="sun_dir")
    for i in range(3):
        sd.inputs[i].default_value = float(sun_dir[i])
    L = b.v("NORMALIZE", sd.outputs[0])
    N, I = geo.outputs["Normal"], geo.outputs["Incoming"]
    mu = b.m("MAXIMUM", b.m("ABSOLUTE", b.v("DOT_PRODUCT", N, I)), 1e-3)
    mu0 = b.m("MAXIMUM", b.m("ABSOLUTE", b.v("DOT_PRODUCT", N, L)), 1e-3)
    ca = b.m("MINIMUM", b.m("MAXIMUM", b.v("DOT_PRODUCT", L, I), -1.0), 1.0)      # cos фазового угла
    al = b.m("ARCCOSINE", ca)
    # фаза ламбертовой сферы: 8/(3π)·(sin α + (π − α)·cos α)
    pl = b.m("MULTIPLY", b.m("ADD", b.m("SINE", al), b.m("MULTIPLY", b.m("SUBTRACT", math.pi, al), ca)),
             8.0 / (3.0 * math.pi))
    g = p["dust_g"]
    pd = b.m("DIVIDE", 1.0 - g * g, b.m("POWER", b.m("MULTIPLY_ADD", ca, 2.0 * g, 1.0 + g * g), 1.5))
    am = b.v("SCALE", alb, scale=pl)                                                # ϖ·цвет·P, частицы
    ad = b.v("SCALE", p["dust_albedo"], scale=pd)                                   # пыль
    inv = b.m("ADD", b.m("DIVIDE", 1.0, mu), b.m("DIVIDE", 1.0, mu0))
    er_m = b.m("SUBTRACT", 1.0, b.m("EXPONENT", b.m("MULTIPLY", b.m("MULTIPLY", tau, inv), -1.0)))
    er_d = b.m("SUBTRACT", 1.0, b.m("EXPONENT", b.m("MULTIPLY", b.m("MULTIPLY", tau_d, inv), -1.0)))
    k_r = b.m("DIVIDE", 0.25, b.m("ADD", mu, mu0))
    c_r = b.v("SCALE", b.v("ADD", b.v("SCALE", am, scale=er_m), b.v("SCALE", ad, scale=er_d)), scale=k_r)

    def trans(t):
        # τ·exp(−τ/μ)·g(x)/(μ·μ0), g(x) = (1 − e^−x)/x, x = τ(1/μ0 − 1/μ) — без особенности при μ = μ0
        xx = b.m("MULTIPLY", t, b.m("SUBTRACT", b.m("DIVIDE", 1.0, mu0), b.m("DIVIDE", 1.0, mu)))
        big = b.m("GREATER_THAN", b.m("ABSOLUTE", xx), 1e-3)
        xs = b.m("MULTIPLY_ADD", big, b.m("SUBTRACT", xx, 1e-3), 1e-3)             # |x| < 1e-3 → 1e-3
        gx = b.m("DIVIDE", b.m("SUBTRACT", 1.0, b.m("EXPONENT", b.m("MULTIPLY", xs, -1.0))), xs)
        ev = b.m("EXPONENT", b.m("MULTIPLY", b.m("DIVIDE", t, mu), -1.0))
        return b.m("DIVIDE", b.m("MULTIPLY", b.m("MULTIPLY", t, ev), gx), b.m("MULTIPLY", mu, mu0))

    c_t = b.v("SCALE", b.v("ADD", b.v("SCALE", am, scale=trans(tau)), b.v("SCALE", ad, scale=trans(tau_d))),
              scale=0.25)
    T = b.m("EXPONENT", b.m("MULTIPLY", b.m("DIVIDE", b.m("ADD", tau, tau_d), mu), -1.0))
    if hole is not None:
        cam, h0, h1 = hole
        tcc = b.node("ShaderNodeTexCoord", object=cam)
        m = b.ss(b.v("LENGTH", tcc.outputs["Object"]), h0, h1)
        c_r = b.v("SCALE", c_r, scale=m)
        c_t = b.v("SCALE", c_t, scale=m)
        T = b.m("SUBTRACT", 1.0, b.m("MULTIPLY", m, b.m("SUBTRACT", 1.0, T)))
    tr = b.node("ShaderNodeBsdfTransparent", {"Color": b.comb(T, T, T)})
    df = b.node("ShaderNodeBsdfDiffuse", {"Color": c_r, "Roughness": 0.0})
    tl = b.node("ShaderNodeBsdfTranslucent", {"Color": c_t})
    a1 = b.node("ShaderNodeAddShader", {0: tr.outputs[0], 1: df.outputs[0]})
    a2 = b.node("ShaderNodeAddShader", {0: a1.outputs[0], 1: tl.outputs[0]})
    b.put(out.inputs["Surface"], a2.outputs[0])
    return mat


def build_rings(scene, kind="saturn", *, parent=None, unit_km=1000.0, sun_dir=(1, 0, 0), r_in_km=None,
                r_out_km=None, segments=1024, seed=0, detail="close", hole=None, name=None, location=(0, 0, 0),
                grain=None):
    """Кольца kind ∈ PROFILES в плоскости XY parent (root газового гиганта). unit_km — км в одной единице сцены
    (1000 — 1 ед. = 1000 км; 0.001 — 1 ед. = 1 м). sun_dir — НА звезду, в мире (статично; сменить — set_sun).
    hole=(cam, r0, r1) — прозрачная окрестность камеры (ед. сцены). location — сдвиг диска в системе parent
    (например, на верх слоя частиц); grain=(масштаб в ед. сцены, амплитуда) — зерно неразрешённых глыб для вида
    изнутри кольца. Возвращает dict(ring, material, image, unit_km, kind)."""
    p = PROFILES[kind]
    lod = {"close": 0, "mid": 1, "far": 2}[detail]
    name = name or f"Rings_{kind}"
    meta = dict(v=1, kind=kind, seed=seed, p={k: p[k] for k in p})
    img = lut.ensure("rings", f"{kind}_profile", meta, lambda: _lut_rgba(kind, seed))
    r_in = (r_in_km or p["r0"]) / unit_km
    r_out = (r_out_km or p["r1"]) / unit_km
    ob = bpy.data.objects.new(name, _annulus(f"{name}_mesh", r_in, r_out, segments))
    C.link(ob, COLL)
    if parent is not None:
        ob.parent = parent
    ob.location = location
    mat = _mat_rings(f"{name}_Mat", p, img, unit_km, sun_dir, lod, hole, grain)
    ob.data.materials.append(mat)
    cy = scene.cycles
    cy.transparent_max_bounces = max(cy.transparent_max_bounces, 24)
    return dict(ring=ob, material=mat, image=img, unit_km=unit_km, kind=kind)


def set_sun(rg, sun_dir):
    nn = rg["material"].node_tree.nodes
    for i in range(3):
        nn["sun_dir"].inputs[i].default_value = float(sun_dir[i])


def set_albedo(rg, k):
    """Множитель альбедо (подгонка яркости диска под поле частиц в одном кадре)."""
    rg["material"].node_tree.nodes["albedo_k"].outputs[0].default_value = k
