"""Газовые гиганты (эп. 004+): сплюснутый шар с зональными полосами, полярным шестиугольником и дымкой у лимба.

    from spacekit.bodies import gas_giant as GG
    g = GG.build_gas_giant(sc, "saturn", radius=60.268, sun_dir=SUN, sun_strength=4.0, frame_start=1, frame_end=n)
    # g["root"] — положение и ориентация (кольца — детьми root: экватор = плоскость XY root),
    # g["planet"] — меш (сжатие — масштаб Z, суточное вращение ключами), g["haze"] — оболочка дымки

Полосы: опорные точки цвета по планетографической широте (KINDS[kind]["bands"], sRGB) + тонкие полоски от сида →
1D-таблица (spacekit.lut, кэш в assets/gas_giant/). В шейдере широта искажается анизотропным шумом (медленно вдоль
параллели, быстро поперёк): волнистые края полос, штриховка, вихри. Шестиугольник: у северного полюса «радиус от
полюса» берётся по гексагональной метрике ρ·cos((θ mod 60°) − 30°)/cos 30° с плавным переходом к круговой — полосы у
~78° N идут шестиугольником, у самого полюса и ниже ~70° — кругами.
Координаты текстуры — единичная сфера до сжатия (параметрическая широта β), в таблицу идёт планетографическая
φ = atan(tan β / (1 − f)).
Свет — SUN-лампа сцены; направление sun_dir (в мире, НА звезду) статично и нужно шейдеру для потемнения к лимбу
(Минарт: (μ·μ0)^(k−1) поверх Ламберта) и дымки. Сменить — set_sun().
Дымка — аналитическая оболочка, как атмосфера planets (Чепмен, Рэлей + Хеньи–Гринстейн, только лицевая сторона),
но в системе объекта (сжатая сфера → сфера) и с параллельным светом: мягкий лимб и светлый ободок на просвет.
"""
import math

import bpy
import numpy as np
from mathutils import Vector

from .. import anim
from .. import core as C
from .. import lut
from .planets import _NB, _ghost, _sphere_mesh

COLL = "Planets"

# опорные точки полос: (планетографическая широта °, sRGB 0..255). Сатурн — по снимкам Cassini в естественных
# цветах (2004–2017) и Hubble OPAL: светлая кремовая экваториальная зона, охристые пояса, приглушённые средние
# широты, серо-голубые высокие, шестиугольник ~78° N со светлой струёй по краю, тёмный полярный вихрь.
SATURN_BANDS = [
    (-90.0, (88, 84, 80)), (-88.0, (104, 98, 90)), (-84.0, (128, 128, 122)), (-78.0, (138, 142, 138)),
    (-72.0, (150, 152, 142)), (-66.0, (166, 162, 144)), (-60.0, (178, 170, 146)), (-55.0, (190, 178, 148)),
    (-50.0, (200, 186, 152)), (-45.0, (186, 168, 132)), (-40.0, (206, 190, 152)), (-35.0, (196, 174, 130)),
    (-31.0, (214, 196, 152)), (-27.0, (204, 178, 128)), (-22.0, (196, 164, 112)), (-18.0, (184, 150, 100)),
    (-14.0, (206, 178, 128)), (-10.0, (224, 202, 154)), (-5.0, (234, 214, 168)), (0.0, (228, 208, 162)),
    (5.0, (236, 216, 170)), (9.0, (226, 204, 156)), (13.0, (204, 174, 122)), (17.0, (186, 152, 102)),
    (21.0, (196, 164, 112)), (25.0, (212, 188, 138)), (29.0, (200, 174, 126)), (33.0, (218, 200, 156)),
    (37.0, (196, 176, 134)), (41.0, (216, 198, 156)), (44.0, (200, 182, 142)), (47.0, (168, 150, 116)),
    (49.0, (204, 188, 150)), (54.0, (192, 178, 144)), (58.0, (178, 168, 138)), (62.0, (190, 180, 146)),
    (66.0, (170, 162, 134)), (70.0, (180, 172, 140)), (74.0, (166, 160, 132)), (76.0, (196, 188, 156)),
    (77.0, (206, 198, 166)), (78.0, (186, 178, 146)), (82.0, (150, 150, 128)), (85.0, (132, 136, 122)),
    (88.0, (112, 114, 106)), (90.0, (84, 84, 80)),
]

KINDS = {
    "saturn": dict(
        f=0.09796,                      # сжатие (R_экв 60 268 км, R_пол 54 364 км — уровень 1 бар)
        rot_s=38018.0,                  # 10 ч 33 мин 38 с (Mankovich et al. 2019)
        bands=SATURN_BANDS, streaks=160, streak_amp=0.035, streak_hue=0.03,
        # искажение широты: (масштаб вдоль параллели, поперёк — по φ в рад, амплитуда °), от крупного к мелкому
        warp=((2.2, 16.0, 0.38), (8.0, 80.0, 0.12), (26.0, 300.0, 0.05)),
        mottle=(22.0, 0.035),           # пятнистость яркости: масштаб, амплитуда
        minnaert=1.10,
        hexagon=dict(lat=77.0, rot=0.0, inner=(0.03, 0.10), outer=(0.36, 0.29)),   # ~77° N (JPL 2009)
        haze=dict(H=0.0032, tau=(0.030, 0.040, 0.065), mie=0.75, g=0.70, tw=(-0.12, 0.08), tail=0.12),
    ),
}

_LOD_WARP = (3, 2, 1)       # сколько октав искажения на close / mid / far


# --------------------------------------------------------------------------- таблица полос

def _band_rgba(cfg, seed, n=4096):
    lat = np.linspace(-90.0, 90.0, n)
    la = np.array([p[0] for p in cfg["bands"]])
    col = lut.srgb_to_linear(np.array([p[1] for p in cfg["bands"]], np.float64) / 255.0)
    rgb = np.stack([np.interp(lat, la, col[:, k]) for k in range(3)], -1)
    rng = np.random.default_rng(1000 + seed)
    k = np.ones(n)
    hue = np.zeros(n)
    for _ in range(cfg["streaks"]):
        c = rng.uniform(-87.0, 87.0)
        w = rng.uniform(0.10, 0.75)
        g = np.exp(-0.5 * ((lat - c) / w) ** 2)
        k += rng.normal(0.0, cfg["streak_amp"]) * g
        hue += rng.normal(0.0, cfg["streak_hue"]) * g
    rgb *= k[:, None]
    rgb[:, 0] *= 1.0 + hue           # тёплее/холоднее: красный вверх, синий вниз
    rgb[:, 2] *= 1.0 - hue
    out = np.ones((1, n, 4), np.float32)
    out[0, :, :3] = np.clip(rgb, 0.0, 1.0)
    return out


def _band_image(kind, cfg, seed):
    meta = dict(v=1, kind=kind, seed=seed, bands=cfg["bands"], streaks=cfg["streaks"], amp=cfg["streak_amp"],
                hue=cfg["streak_hue"])
    return lut.ensure("gas_giant", f"{kind}_bands", meta, lambda: _band_rgba(cfg, seed))


# --------------------------------------------------------------------------- поверхность

def _sun_vec(b, sun_dir, name="sun_dir"):
    n = b.node("ShaderNodeCombineXYZ", name=name, label=name)
    for i in range(3):
        n.inputs[i].default_value = float(sun_dir[i])
    return b.v("NORMALIZE", n.outputs[0])


def _mat_surface(name, cfg, img, seed, lod, sun_dir):
    mat, nodes, links, out = C.new_material(name)
    b = _NB(mat.node_tree)
    tc = b.node("ShaderNodeTexCoord")
    n = b.v("NORMALIZE", tc.outputs["Object"])
    x, y, z = b.sep(n)
    f = cfg["f"]
    rho = b.m("SQRT", b.m("MAXIMUM", b.m("SUBTRACT", 1.0, b.m("MULTIPLY", z, z)), 0.0))
    north = b.m("GREATER_THAN", z, 0.0)
    rho_e = rho
    hx = cfg.get("hexagon")
    if hx:
        # гексагональная «дистанция от полюса»: на вершинах = ρ, на серединах сторон = ρ / cos 30°
        th = b.m("ARCTAN2", y, x)
        ang = b.m("SUBTRACT", b.m("FLOORED_MODULO", b.m("ADD", th, math.radians(hx["rot"])), math.pi / 3.0),
                  math.pi / 6.0)
        dh = b.m("DIVIDE", b.m("MULTIPLY", rho, b.m("COSINE", ang)), math.cos(math.pi / 6.0))
        w = b.m("MULTIPLY", b.ss(rho, hx["inner"][0], hx["inner"][1]), b.ss(rho, hx["outer"][0], hx["outer"][1]))
        rho_e = b.m("MULTIPLY_ADD", b.m("MULTIPLY", w, north), b.m("SUBTRACT", dh, rho), rho)
    z_e = b.m("SQRT", b.m("MAXIMUM", b.m("SUBTRACT", 1.0, b.m("MULTIPLY", rho_e, rho_e)), 0.0))
    z_e = b.m("MULTIPLY", z_e, b.m("SUBTRACT", b.m("MULTIPLY", north, 2.0), 1.0))   # знак полушария
    phi = b.m("ARCTAN2", z_e, b.m("MULTIPLY", rho_e, 1.0 - f))                       # планетографическая, рад
    # искажение широты анизотропным шумом
    off = Vector(((seed * 7.31) % 13.0, (seed * 3.17) % 11.0, (seed * 5.71) % 17.0))
    dphi = None
    for k, (sa, sc_, amp) in enumerate(cfg["warp"][:_LOD_WARP[lod]]):
        q = b.comb(b.m("MULTIPLY", x, sa), b.m("MULTIPLY", y, sa), b.m("MULTIPLY", phi, sc_))
        nz = b.noise(b.v("ADD", q, tuple(off * (k + 1))), 1.0, detail=4 - k, rough=0.55, dist=0.5 + 0.3 * k)
        d = b.m("MULTIPLY", b.m("SUBTRACT", nz.outputs[0], 0.5), 2.0 * math.radians(amp))
        dphi = d if dphi is None else b.m("ADD", dphi, d)
    u = b.m("ADD", b.m("DIVIDE", b.m("ADD", phi, dphi), math.pi), 0.5)
    col = lut.image_node(b, img, u).outputs["Color"]
    if lod < 2:
        ms, ma = cfg["mottle"]
        mn = b.noise(b.v("ADD", b.comb(b.m("MULTIPLY", x, ms), b.m("MULTIPLY", y, ms), b.m("MULTIPLY", z, ms * 3.0)),
                         tuple(off)), 1.0, detail=3, rough=0.5).outputs[0]
        col = b.v("SCALE", col, scale=b.m("MULTIPLY_ADD", b.m("SUBTRACT", mn, 0.5), 2.0 * ma, 1.0))
    # Минарт поверх Ламберта: (μ·μ0)^(k−1)
    geo = b.node("ShaderNodeNewGeometry")
    L = _sun_vec(b, sun_dir)
    mu = b.m("MAXIMUM", b.v("DOT_PRODUCT", geo.outputs["Normal"], geo.outputs["Incoming"]), 0.02)
    mu0 = b.m("MAXIMUM", b.v("DOT_PRODUCT", geo.outputs["Normal"], L), 0.02)
    fac = b.m("POWER", b.m("MULTIPLY", mu, mu0), cfg["minnaert"] - 1.0)
    col = b.v("SCALE", col, scale=fac)
    bsdf = b.node("ShaderNodeBsdfDiffuse", {"Color": col, "Roughness": 0.0})
    b.put(out.inputs["Surface"], bsdf.outputs[0])
    return mat


# --------------------------------------------------------------------------- дымка

def _mat_haze(name, Rp, cfg, sun_dir, E):
    """Как planets._mat_atmosphere, но P и I — в системе объекта (сжатая оболочка → сфера радиуса Rp), свет
    параллельный: L — sun_dir (в мире → в объект), освещённость E — пиксель белого диффуза (узел sun_E)."""
    mat, nodes, links, out = C.new_material(name)
    b = _NB(mat.node_tree)
    H = cfg["H"] * Rp
    geo = b.node("ShaderNodeNewGeometry")
    P = b.node("ShaderNodeVectorTransform", {"Vector": geo.outputs["Position"]}, vector_type="POINT",
               convert_from="WORLD", convert_to="OBJECT").outputs[0]
    I = b.v("NORMALIZE", b.node("ShaderNodeVectorTransform", {"Vector": geo.outputs["Incoming"]},
                                vector_type="VECTOR", convert_from="WORLD", convert_to="OBJECT").outputs[0])
    L = b.v("NORMALIZE", b.node("ShaderNodeVectorTransform", {"Vector": _sun_vec(b, sun_dir)}, vector_type="VECTOR",
                                convert_from="WORLD", convert_to="OBJECT").outputs[0])
    pI = b.v("DOT_PRODUCT", P, I)
    b2 = b.m("MAXIMUM", b.m("SUBTRACT", b.v("DOT_PRODUCT", P, P), b.m("MULTIPLY", pI, pI)), 0.0)
    bb = b.m("SQRT", b2)
    chmax = math.sqrt(math.pi * Rp / (2.0 * H))
    mu = b.m("SQRT", b.m("MAXIMUM", b.m("SUBTRACT", 1.0, b.m("DIVIDE", b2, Rp * Rp)), 1e-8))
    c_disk = b.m("MINIMUM", b.m("DIVIDE", 1.0, mu), chmax)
    c_limb = b.m("MULTIPLY", 2.0 * chmax,
                 b.m("EXPONENT", b.m("MINIMUM", b.m("DIVIDE", b.m("SUBTRACT", Rp, bb), H), 0.0)))
    above = b.m("GREATER_THAN", bb, Rp)
    col = b.m("MULTIPLY_ADD", above, b.m("SUBTRACT", c_limb, c_disk), c_disk)
    t = b.m("SUBTRACT", pI, b.m("SQRT", b.m("MAXIMUM", b.m("SUBTRACT", Rp * Rp, b2), 0.0)))
    X = b.v("NORMALIZE", b.v("SUBTRACT", P, b.v("SCALE", I, scale=t)))
    mus = b.v("DOT_PRODUCT", X, L)
    cs = b.v("DOT_PRODUCT", b.v("SCALE", L, scale=-1.0), I)
    tail = b.m("MULTIPLY", b.m("MULTIPLY", b.ss(mus, -0.65, 0.0), b.ss(cs, 0.35, 0.9)),
               b.m("MULTIPLY", above, cfg["tail"]))
    lit = b.m("ADD", tail, b.ss(mus, cfg["tw"][0], cfg["tw"][1]))
    pr = b.m("MULTIPLY", b.m("MULTIPLY_ADD", cs, cs, 1.0), 3.0 / 16.0)
    g = cfg["g"]
    hg_den = b.m("POWER", b.m("MAXIMUM", b.m("MULTIPLY_ADD", cs, -2.0 * g, 1.0 + g * g), 1e-4), 1.5)
    hg = b.m("DIVIDE", (1.0 - g * g) / 4.0, hg_den)
    ph = b.m("ADD", b.m("MULTIPLY", pr, 1.0 - cfg["mie"]), b.m("MULTIPLY", hg, cfg["mie"]))
    tau = b.v("SCALE", cfg["tau"], scale=col)
    one_m = b.v("SUBTRACT", (1.0, 1.0, 1.0), b.vexp_neg(tau))
    c_in = b.m("MINIMUM", b.m("DIVIDE", 1.0, b.m("MAXIMUM", b.m("ADD", mus, 0.03), 1e-3)), 2.0 * chmax)
    t_in = b.vexp_neg(b.v("SCALE", cfg["tau"], scale=b.m("MULTIPLY", c_in, 0.5)))
    front = b.m("SUBTRACT", 1.0, geo.outputs["Backfacing"])
    en = b.node("ShaderNodeValue", name="sun_E", label="sun_E")
    en.outputs[0].default_value = E
    k = b.m("MULTIPLY", b.m("MULTIPLY", b.m("MULTIPLY", en.outputs[0], ph), lit), front)
    emis = b.v("SCALE", b.v("MULTIPLY", one_m, t_in), scale=k)
    trans = b.v("ADD", b.v("SCALE", b.vexp_neg(tau), scale=front),
                b.v("SCALE", (1.0, 1.0, 1.0), scale=geo.outputs["Backfacing"]))
    em = b.node("ShaderNodeEmission", {"Color": emis, "Strength": 1.0})
    tr = b.node("ShaderNodeBsdfTransparent", {"Color": trans})
    add = b.node("ShaderNodeAddShader", {0: em.outputs[0], 1: tr.outputs[0]})
    b.put(out.inputs["Surface"], add.outputs[0])
    mat.cycles.emission_sampling = "NONE"
    return mat


# --------------------------------------------------------------------------- API

def build_gas_giant(scene, kind="saturn", *, radius=1.0, location=(0, 0, 0), parent=None, sun_dir=(1, 0, 0),
                    sun_strength=3.0, rotation_euler=(0.0, 0.0, 0.0), rot_period_s=None, lon0_deg=0.0, seed=0,
                    detail="close", frame_start=1, frame_end=300, name=None, haze=True):
    """Газовый гигант kind ∈ KINDS. radius — экваториальный (ед. сцены), полярный = radius·(1 − f).
    rotation_euler — ориентация root (экватор = XY root): наклон оси, поворот системы под кадр.
    sun_dir — направление НА звезду в мире (статично), sun_strength — сила SUN-лампы (для дымки: E = S/π).
    detail: close (≥ ~40 % кадра: 3 октавы искажения, меш 384×192), mid, far (1 октава, без пятнистости).
    rot_period_s — None: реальный период (rot_s), секунды ролика = секунды реального времени.
    Возвращает dict(root, planet, haze, materials, kind, radius, polar_radius, f)."""
    if kind not in KINDS:
        raise ValueError(f"unknown gas giant kind {kind!r}")
    cfg = KINDS[kind]
    lod = {"close": 0, "mid": 1, "far": 2}[detail]
    name = name or kind.capitalize()
    R = float(radius)
    f = cfg["f"]
    root = C.empty(f"GG_{name}", coll=COLL, parent=parent, loc=location, size=R * 1.5)
    root.rotation_mode = "XYZ"
    root.rotation_euler = rotation_euler
    u, v = ((384, 192), (192, 96), (96, 48))[lod]
    planet = bpy.data.objects.new(f"GG_{name}_Body", _sphere_mesh(f"GG_{name}_mesh", R, u, v))
    C.link(planet, COLL)
    planet.parent = root
    planet.scale = (1.0, 1.0, 1.0 - f)
    img = _band_image(kind, cfg, seed)
    mat = _mat_surface(f"GG_{name}_Surface", cfg, img, seed, lod, sun_dir)
    planet.data.materials.append(mat)
    per = cfg["rot_s"] if rot_period_s is None else rot_period_s
    anim.key_rot_z(planet, math.radians(lon0_deg), 360.0 / per, frame_start, frame_end, scene)
    mats = {"surface": mat}
    hz = None
    if haze and cfg.get("haze"):
        hc = cfg["haze"]
        Rs = R * (1.0 + 7.5 * hc["H"])
        au, av = ((256, 128), (160, 80), (96, 48))[lod]
        hz = bpy.data.objects.new(f"GG_{name}_Haze", _sphere_mesh(f"GG_{name}_haze", Rs, au, av))
        C.link(hz, COLL)
        hz.parent = root
        hz.scale = (1.0, 1.0, 1.0 - f)
        _ghost(hz)
        hm = _mat_haze(f"GG_{name}_HazeMat", R, hc, sun_dir, sun_strength / math.pi)
        hz.data.materials.append(hm)
        mats["haze"] = hm
        cy = scene.cycles
        cy.transparent_max_bounces = max(cy.transparent_max_bounces, 24)
    return dict(root=root, planet=planet, haze=hz, materials=mats, kind=kind, radius=R, polar_radius=R * (1.0 - f),
                f=f)


def set_sun(objs, sun_dir=None, strength=None):
    """Новое направление (в мире, НА звезду) и/или сила SUN-лампы — в материалах поверхности и дымки."""
    for m in objs["materials"].values():
        nn = m.node_tree.nodes
        if sun_dir is not None and "sun_dir" in nn:
            for i in range(3):
                nn["sun_dir"].inputs[i].default_value = float(sun_dir[i])
        if strength is not None and "sun_E" in nn:
            nn["sun_E"].outputs[0].default_value = strength / math.pi


def surface_point(objs, lat_deg, lon_deg, alt=0.0):
    """Точка на поверхности (планетографическая широта, долгота от +X root, высота над уровнем 1 бар) — в мире.
    Вращение планеты не учитывается (за минуту Сатурн поворачивается на ~0.6°)."""
    R, f = objs["radius"], objs["f"]
    ph = math.radians(lat_deg)
    beta = math.atan((1.0 - f) * math.tan(ph)) if abs(lat_deg) < 89.999 else math.copysign(math.pi / 2, lat_deg)
    lo = math.radians(lon_deg)
    p = Vector((R * math.cos(beta) * math.cos(lo), R * math.cos(beta) * math.sin(lo), R * (1.0 - f) * math.sin(beta)))
    nrm = Vector((math.cos(ph) * math.cos(lo), math.cos(ph) * math.sin(lo), math.sin(ph)))
    return objs["root"].matrix_world @ (p + nrm * alt)
