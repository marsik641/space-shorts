"""Процедурные планеты: kind PSR B1257+12 (Драугр, Полтергейст, Фобетор) и безатмосферные миры эп. 003+
(ember, scorched, rust, frostrock, grooved, dirtyice — см. KINDS; brightice и add_big_crater — эп. 004).

Процедурные материалы (Principled + шумы/Вороной + bump), атмосфера — аналитическая оболочка
(поверхностный шейдер, без объёма → без шума), сияния — стопка эмиссионных оболочек-шапок у магнитных полюсов
(каждая — один отсчёт «ray march» по своему слою, см. _mat_aurora_shell).
Свет — только пульсар: направление на него берётся из пустышки `<имя>_SunRef` (Copy Location к лампе,
вращение единичное) через TexCoord/Object, так что орбита и смена фазы отрабатываются сами, без драйверов.
Яркость/цвет света для атмосферы — узлы sun_power/sun_color: при вспышках лампы и проходе лучей-прожекторов
их ключует key_sun_power (вызывать после add_orbit).

    from spacekit.bodies import planets as PL
    o = PL.build_planet(sc, "poltergeist", radius=1.0, light=psr["light"], frame_start=1, frame_end=360)
    PL.add_orbit(sc, o["root"], center_parent=psr["root"], a=30, period_s=40, phase_deg=20,
                 frame_start=1, frame_end=360)
    PL.key_sun_power(o, psr, 1, 360)        # psr — dict из NS.build_pulsar
    # setup_cycles сбрасывает transparent_max_bounces в 16 — после него: sc.cycles.transparent_max_bounces = 24
"""
import math

import bmesh
import bpy
from mathutils import Vector

from .. import core as C
from ..lighting import K_POINT, spot_factor as _spot_factor  # noqa: F401
from ..orbits import add_orbit  # noqa: F401  (совместимость: PL.add_orbit)

COLL = "Planets"
# калибровка Cycles: пиксель белого диффуза под точечным светом = K_POINT * energy / d^2

KINDS = {
    "draugr": dict(tilt=7.0, rot=50.0, atmo=None, aurora=False),
    "poltergeist": dict(
        tilt=18.0, rot=60.0, aurora=True,
        # H — шкала высоты (в R), tau — вертикальная оптическая толщина по RGB, mie — доля дымки, g — асимметрия
        atmo=dict(H=0.011, tau=(0.007, 0.012, 0.030), mie=0.18, g=0.62, tw=(-0.16, 0.10), tail=0.10)),
    "phobetor": dict(
        tilt=26.0, rot=75.0, aurora=True,
        atmo=dict(H=0.012, tau=(0.060, 0.066, 0.078), mie=0.65, g=0.72, tw=(-0.15, 0.10), tail=0.16)),
    # безатмосферные миры (эп. 003+): приливно захваченные — без наклона и суточного вращения по умолчанию
    "ember": dict(tilt=0.0, rot=1.0e9, atmo=None, aurora=False),        # тёмный вулканический базальт
    "scorched": dict(tilt=0.0, rot=1.0e9, atmo=None, aurora=False),     # серый кратерированный (как Меркурий)
    "rust": dict(tilt=0.0, rot=1.0e9, atmo=None, aurora=False),         # ржаво-охристая пустыня
    "frostrock": dict(tilt=0.0, rot=1.0e9, atmo=None, aurora=False),    # камень с инеем в холодных зонах
    "grooved": dict(tilt=0.0, rot=1.0e9, atmo=None, aurora=False),      # бороздчатый лёд (как Ганимед)
    "dirtyice": dict(tilt=0.0, rot=1.0e9, atmo=None, aurora=False),     # тёмный грязный лёд (как Каллисто)
    "brightice": dict(tilt=0.0, rot=1.0e9, atmo=None, aurora=False),    # яркий чистый лёд (как Мимас, Тефия) — эп. 004
}

# цвета эмиссии сияний (линейный Rec.709): 557,7 нм, 630 нм, N2+ кайма
AUR_GREEN = (0.12, 1.00, 0.22)
AUR_RED = (1.00, 0.06, 0.12)
AUR_PURPLE = (0.55, 0.22, 1.00)


# --------------------------------------------------------------------------- узлы

class _NB:
    """Мини-построитель шейдерных графов: сокет или число на любом входе."""

    def __init__(self, nt):
        self.nt, self.N, self.L = nt, nt.nodes, nt.links

    def put(self, sock, v):
        if v is None:
            return
        if isinstance(v, bpy.types.NodeSocket):
            self.L.new(v, sock)
        else:
            sock.default_value = v

    def node(self, typ, ins=None, **props):
        n = self.N.new(typ)
        for k, v in props.items():
            setattr(n, k, v)
        for k, v in (ins or {}).items():
            self.put(n.inputs[k], v)
        return n

    def m(self, op, a, b=None, c=None, clamp=False):
        n = self.N.new("ShaderNodeMath")
        n.operation = op
        n.use_clamp = clamp
        for i, v in enumerate((a, b, c)):
            self.put(n.inputs[i], v)
        return n.outputs[0]

    def v(self, op, a, b=None, c=None, scale=None):
        n = self.N.new("ShaderNodeVectorMath")
        n.operation = op
        for i, v in enumerate((a, b, c)):
            self.put(n.inputs[i], v)
        if scale is not None:
            self.put(n.inputs[3], scale)
        return n.outputs[1] if op in ("DOT_PRODUCT", "LENGTH", "DISTANCE") else n.outputs[0]

    def ss(self, x, lo, hi):
        """smoothstep(lo, hi, x); lo > hi — убывающая ступенька."""
        n = self.node("ShaderNodeMapRange", {0: x, 1: lo, 2: hi, 3: 0.0, 4: 1.0},
                      interpolation_type="SMOOTHSTEP", clamp=True)
        return n.outputs[0]

    def lin(self, x, lo, hi, a=0.0, b=1.0):
        return self.node("ShaderNodeMapRange", {0: x, 1: lo, 2: hi, 3: a, 4: b}, clamp=True).outputs[0]

    def mix(self, fac, a, b):
        """Смешение цветов (A при fac=0)."""
        n = self.N.new("ShaderNodeMix")
        n.data_type = "RGBA"
        self.put(n.inputs[0], fac)
        self.put(n.inputs[6], a if not isinstance(a, tuple) or len(a) == 4 else (*a, 1.0))
        self.put(n.inputs[7], b if not isinstance(b, tuple) or len(b) == 4 else (*b, 1.0))
        return n.outputs[2]

    def noise(self, vec, scale, detail=2.0, rough=0.5, lac=2.0, dist=0.0, w=None, typ="FBM"):
        n = self.node("ShaderNodeTexNoise",
                      {"Vector": vec, "Scale": scale, "Detail": detail, "Roughness": rough,
                       "Lacunarity": lac, "Distortion": dist},
                      noise_dimensions="4D" if w is not None else "3D", noise_type=typ)
        if w is not None:
            self.put(n.inputs["W"], w)
        return n

    def sep(self, vec):
        return self.node("ShaderNodeSeparateXYZ", {0: vec}).outputs

    def comb(self, x, y, z):
        return self.node("ShaderNodeCombineXYZ", {0: x, 1: y, 2: z}).outputs[0]

    def vexp_neg(self, vec):
        """exp(-v) покомпонентно."""
        s = self.sep(vec)
        return self.comb(*[self.m("EXPONENT", self.m("MULTIPLY", s[i], -1.0)) for i in range(3)])


def _seed_off(seed, k=0):
    """Псевдослучайный сдвиг координат шума для сида/слоя."""
    s = seed * 7.31 + k * 3.17
    return (math.sin(s * 12.9898) * 43.7 % 97.0, math.sin(s * 78.233) * 31.3 % 89.0,
            math.sin(s * 37.719) * 17.9 % 83.0)


# --------------------------------------------------------------------------- кратеры

def _crater_group():
    """Группа «один слой кратеров»: Вороной F1 (случайность 0.3 → кратер с валом целиком внутри
    своей ячейки, швов нет). Высота в единицах единичной сферы; Halo — свежие выбросы; Floor — днище."""
    g = bpy.data.node_groups.get("PL_Crater")
    if g is not None:
        return g
    g = bpy.data.node_groups.new("PL_Crater", "ShaderNodeTree")
    it = g.interface
    it.new_socket("Vector", in_out="INPUT", socket_type="NodeSocketVector")
    for nm in ("Scale", "Seed", "Density", "RMin", "RMax", "Depth", "Rim", "Flat", "Peak", "Fresh", "RayLen"):
        it.new_socket(nm, in_out="INPUT", socket_type="NodeSocketFloat")
    for nm in ("Height", "Halo", "Floor", "Rays"):
        it.new_socket(nm, in_out="OUTPUT", socket_type="NodeSocketFloat")
    b = _NB(g)
    gi = b.N.new("NodeGroupInput")
    go = b.N.new("NodeGroupOutput")
    i = gi.outputs
    sv = b.v("SCALE", (12.9898, 78.233, 37.719), scale=i["Seed"])
    p = b.v("ADD", i["Vector"], sv)
    vor = b.node("ShaderNodeTexVoronoi", {"Vector": p, "Scale": i["Scale"], "Randomness": 0.3},
                 voronoi_dimensions="3D", feature="F1", distance="EUCLIDEAN")
    r1, r2, r3 = b.node("ShaderNodeSeparateColor", {0: vor.outputs["Color"]}).outputs
    # много мелких, мало крупных
    rad = b.m("MULTIPLY_ADD", b.m("POWER", r1, 1.8), b.m("SUBTRACT", i["RMax"], i["RMin"]), i["RMin"])
    pres = b.m("LESS_THAN", r2, i["Density"])
    x = b.m("DIVIDE", vor.outputs["Distance"], rad)
    x2 = b.m("MULTIPLY", x, x)
    # чаша + вал: Rim*x^4 + Depth*(x^2-1); плоское днище; центральная горка
    h_in = b.m("MULTIPLY_ADD", b.m("MULTIPLY", x2, x2), i["Rim"],
               b.m("MULTIPLY", b.m("SUBTRACT", x2, 1.0), i["Depth"]))
    h_in = b.m("MAXIMUM", h_in, b.m("MULTIPLY", i["Depth"], b.m("SUBTRACT", i["Flat"], 1.0)))
    pk = b.m("MULTIPLY", b.m("EXPONENT", b.m("MULTIPLY", x2, -30.0)), b.m("MULTIPLY", i["Peak"], i["Depth"]))
    h_in = b.m("ADD", h_in, pk)
    t = b.m("SUBTRACT", x, 1.0)
    h_out = b.m("MULTIPLY", i["Rim"], b.m("EXPONENT", b.m("MULTIPLY", b.m("MULTIPLY", t, t), -16.0)))
    inside = b.m("LESS_THAN", x, 1.0)
    h = b.m("MULTIPLY_ADD", inside, b.m("SUBTRACT", h_in, h_out), h_out)
    scale_h = b.m("DIVIDE", b.m("MULTIPLY", pres, rad), i["Scale"])
    b.put(go.inputs["Height"], b.m("MULTIPLY", h, scale_h))
    fresh = b.m("GREATER_THAN", r3, b.m("SUBTRACT", 1.0, i["Fresh"]))
    b.put(go.inputs["Halo"], b.m("MULTIPLY", b.m("MULTIPLY", fresh, pres), b.ss(x, 1.5, 0.9)))
    b.put(go.inputs["Floor"], b.m("MULTIPLY", pres, b.ss(x, 0.95, 0.6)))
    # лучевая система (только если выход подключён — иначе Cycles выкидывает ветку):
    # шум по направлению от центра кратера → радиальные полосы, длина гуляет по азимуту,
    # к границе ячейки гаснет (швов нет)
    dirn = b.v("NORMALIZE", b.v("SUBTRACT", p, vor.outputs["Position"]))
    cc = vor.outputs["Color"]
    stk = b.noise(b.v("ADD", dirn, b.v("SCALE", cc, scale=13.0)), 4.5, detail=3, rough=0.6).outputs[0]
    streak = b.ss(stk, 0.50, 0.68)
    reach = b.m("MULTIPLY", i["RayLen"], b.lin(b.noise(b.v("ADD", dirn, b.v("SCALE", cc, scale=7.0)), 1.6,
                                                        detail=1).outputs[0], 0.3, 0.7, 0.35, 1.0))
    fall = b.m("MULTIPLY", b.m("SQRT", b.ss(x, reach, 1.0)), b.ss(vor.outputs["Distance"], 0.49, 0.25))
    # лучи — только у кратеров, реально лежащих на сфере (точка Вороного ближе радиуса к поверхности)
    hc = b.m("MULTIPLY", b.m("ABSOLUTE", b.m("SUBTRACT", b.v("LENGTH", b.v("SUBTRACT", vor.outputs["Position"], sv)),
                                             1.0)), i["Scale"])
    vis = b.ss(b.m("DIVIDE", hc, rad), 0.9, 0.5)
    b.put(go.inputs["Rays"], b.m("MULTIPLY", b.m("MULTIPLY", fresh, b.m("MULTIPLY", pres, vis)),
                                 b.m("MULTIPLY", fall, streak)))
    return g


def _craters(b, vec, layers, seed, rays_layers=()):
    """Сумма слоёв кратеров. layers: (scale, density, rmin, rmax, depth, rim, flat, peak, fresh).
    rays_layers — те же кортежи + RayLen (в радиусах кратера): слои с лучевыми системами."""
    grp = _crater_group()
    H = halo = floor = rays = None
    allL = [(L, 0.0) for L in layers] + [(L[:9], L[9]) for L in rays_layers]
    for k, ((sc_, dens, rmin, rmax, depth, rim, flat, peak, fresh), rl) in enumerate(allL):
        g = b.node("ShaderNodeGroup")
        g.node_tree = grp
        vals = dict(Vector=vec, Scale=sc_, Seed=seed * 1.37 + k * 0.731, Density=dens, RMin=rmin,
                    RMax=rmax, Depth=depth, Rim=rim, Flat=flat, Peak=peak, Fresh=fresh, RayLen=rl)
        for nm, v in vals.items():
            b.put(g.inputs[nm], v)
        H = g.outputs["Height"] if H is None else b.m("ADD", H, g.outputs["Height"])
        halo = g.outputs["Halo"] if halo is None else b.m("MAXIMUM", halo, g.outputs["Halo"])
        if rmax * 1.0 / sc_ > 0.012:  # днища — только у крупных
            floor = g.outputs["Floor"] if floor is None else b.m("MAXIMUM", floor, g.outputs["Floor"])
        if rl > 0:
            rays = g.outputs["Rays"] if rays is None else b.m("MAXIMUM", rays, g.outputs["Rays"])
    return (H if H is not None else 0.0, halo if halo is not None else 0.0,
            floor if floor is not None else 0.0, rays if rays is not None else 0.0)


# предел масштаба деталей по уровню детализации: close / mid / far
_LOD_CRATER = (1e9, 40.0, 8.0)
_LOD_NOISE = (1e9, 60.0, 20.0)


def _crater_layers(scales, dens, rmin=0.07, rmax=0.22, fresh=0.08, depth_small=0.42, depth_big=0.16,
                   rim_k=0.22, dup=(), lod=0):
    """Набор слоёв: крупные — мелкие и плоские с горкой, мелкие — глубокие чаши.
    Профиль глубины считается по полному набору, lod лишь отбрасывает мелкие слои (mid: dup тоже)."""
    out = []
    smax = max(scales)
    lim = _LOD_CRATER[lod]
    for s in list(scales) + (list(dup) if lod == 0 else []):
        if s > lim:
            continue
        t = min(1.0, math.log(s / min(scales) + 1e-6) / math.log(smax / min(scales) + 1e-6))  # 0 крупные .. 1 мелкие
        depth = depth_big + (depth_small - depth_big) * t
        flat = 0.55 * (1 - t)
        peak = 0.5 * (1 - t) if t < 0.5 else 0.0
        out.append((s, dens, rmin, rmax, depth, depth * rim_k, flat, peak, fresh))
    return out


def _nz(b, lod, vec, scale, default=0.5, **kw):
    """Fac шума или константа, если масштаб мельче предела lod."""
    if scale > _LOD_NOISE[lod]:
        return default
    return b.noise(vec, scale, **kw).outputs[0]


# --------------------------------------------------------------------------- материалы поверхности

def _surface_base(name):
    mat, nodes, links, out = C.new_material(name)
    b = _NB(mat.node_tree)
    tc = b.node("ShaderNodeTexCoord")
    vec = b.v("NORMALIZE", tc.outputs["Object"])  # единичная сфера, вращается с планетой
    bsdf = b.node("ShaderNodeBsdfPrincipled")
    b.put(out.inputs["Surface"], bsdf.outputs[0])
    return mat, b, vec, bsdf


def _finish(b, bsdf, height, radius, bump_k, color, rough, diff_rough, spec):
    # у самого лимба bump гасим: иначе возмущённая нормаль «отворачивается» от камеры и даёт
    # чёрные серпы в кратерах даже при нулевой фазе
    geo = b.node("ShaderNodeNewGeometry")
    facing = b.m("ABSOLUTE", b.v("DOT_PRODUCT", geo.outputs["Normal"], geo.outputs["Incoming"]))
    bump = b.node("ShaderNodeBump", {"Strength": b.ss(facing, 0.02, 0.22), "Distance": radius * bump_k,
                                      "Height": height, "Filter Width": 0.6})
    # bump не умеет перспективного сокращения: склон, отвёрнутый от камеры, остаётся во весь рост и
    # чернеет. Не даём возмущённой нормали смотреть от камеры сильнее, чем 0.35·(N_geo·V)
    V = geo.outputs["Incoming"]
    nb = bump.outputs[0]
    add = b.m("MAXIMUM", b.m("SUBTRACT", b.m("MULTIPLY", facing, 0.35), b.v("DOT_PRODUCT", nb, V)), 0.0)
    nfix = b.v("NORMALIZE", b.v("ADD", nb, b.v("SCALE", V, scale=add)))
    b.put(bsdf.inputs["Normal"], nfix)
    b.put(bsdf.inputs["Base Color"], color)
    b.put(bsdf.inputs["Roughness"], rough)
    b.put(bsdf.inputs["Diffuse Roughness"], diff_rough)
    b.put(bsdf.inputs["Specular IOR Level"], spec)


def _grey(b, col, k):
    """col + k (серый), k — сокет/число."""
    return b.v("ADD", col, b.v("SCALE", (1.0, 1.0, 1.0), scale=k))


def _mat_draugr(name, seed, radius, lod=0):
    mat, b, vec, bsdf = _surface_base(name)
    v = b.v("ADD", vec, _seed_off(seed))
    # моря: крупные затопленные бассейны, кромка изрезана (заливы) шумом порога
    mn = b.noise(v, 1.2, detail=5, rough=0.55, dist=0.25).outputs[0]
    mj = b.m("MULTIPLY", b.m("SUBTRACT", b.noise(b.v("ADD", v, (4.4, 1.9, 6.1)), 6.0, detail=6,
                                                  rough=0.6).outputs[0], 0.5), 0.08)
    mare = b.ss(b.m("ADD", mn, mj), 0.52, 0.64)
    layers = _crater_layers([1.3, 2.0, 3.2, 5.0, 8.0, 13.0, 21.0, 34.0, 55.0, 90.0], 0.8,
                            dup=[2.6, 4.1, 6.5, 10.5, 17.0, 27.0, 44.0, 70.0, 120.0], fresh=0.07,
                            depth_big=0.20, depth_small=0.45, lod=lod)
    # редкие молодые кратеры с лучами (3–5 на видимом полушарии)
    rays_l = [] if lod == 2 else [(2.6, 0.45, 0.035, 0.06, 0.45, 0.1, 0.0, 0.0, 1.0, 18.0),
                                  (4.5, 0.30, 0.04, 0.08, 0.45, 0.1, 0.0, 0.0, 1.0, 12.0)]
    H, halo, floor, rays = _craters(b, vec, layers, seed, rays_layers=rays_l)
    # мелкий реголит и холмистость материков
    hill = b.m("MULTIPLY", b.noise(v, 7.0, detail=8 if lod < 2 else 4, rough=0.6).outputs[0], 0.006)
    fine = b.m("MULTIPLY", _nz(b, lod, v, 90.0, detail=4, rough=0.6), 0.0009)
    Hm = b.m("MULTIPLY", H, b.m("SUBTRACT", 1.0, b.m("MULTIPLY", mare, 0.75)))  # моря сглаживают рельеф
    height = b.m("ADD", b.m("ADD", Hm, b.m("MULTIPLY", hill, b.m("SUBTRACT", 1.0, mare))), fine)
    height = b.m("SUBTRACT", height, b.m("MULTIPLY", mare, 0.0025))
    # альбедо: материк ~0.15, море ~0.06, свежие выбросы и лучи ярче
    var = b.noise(v, 5.0, detail=10 if lod < 2 else 4, rough=0.62)
    grain = b.lin(_nz(b, lod, v, 45.0, detail=4, rough=0.6), 0.3, 0.7, 0.88, 1.1)
    tone = b.m("MULTIPLY", b.lin(var.outputs[0], 0.3, 0.7, 0.8, 1.17), grain)
    hi_col = b.mix(b.ss(b.noise(v, 2.4, detail=4).outputs[0], 0.4, 0.62), (0.150, 0.145, 0.136), (0.172, 0.168, 0.160))
    col = b.mix(mare, hi_col, (0.060, 0.061, 0.064))
    col = b.mix(b.m("MULTIPLY", floor, 0.25), col, (0.11, 0.108, 0.104))
    col = b.v("SCALE", col, scale=tone)
    col = _grey(b, col, b.m("MULTIPLY", rays, 0.075))
    speck = b.lin(_nz(b, lod, v, 160.0, detail=2), 0.35, 0.65, 0.2, 1.0)
    col = b.mix(b.m("MULTIPLY", b.m("MULTIPLY", halo, speck), 0.55), col, (0.25, 0.248, 0.242))
    _finish(b, bsdf, height, radius, 1.1, col, 0.97, 1.0, 0.12)
    return mat


def _rift_net(b, vec, scale, seed, warp=0.9, oct2=0.5):
    """Сеть разломов: расстояние до ребра Вороного на искривлённых координатах (в ед. сферы).
    Второй октав сдвига (oct2) ломает прямые отрезки и 120°-стыки."""
    o = _seed_off(seed, 5)
    w1 = b.noise(b.v("ADD", vec, o), scale * 0.8, detail=4).outputs["Color"]
    disp = b.v("SUBTRACT", w1, (0.5, 0.5, 0.5))
    if oct2 > 0:
        w2 = b.noise(b.v("ADD", vec, _seed_off(seed, 7)), scale * 2.5, detail=2).outputs["Color"]
        disp = b.v("ADD", disp, b.v("SCALE", b.v("SUBTRACT", w2, (0.5, 0.5, 0.5)), scale=oct2))
    p = b.v("ADD", vec, b.v("SCALE", disp, scale=warp / scale))
    vor = b.node("ShaderNodeTexVoronoi", {"Vector": b.v("ADD", p, _seed_off(seed, 6)), "Scale": scale,
                                           "Randomness": 1.0},
                 voronoi_dimensions="3D", feature="DISTANCE_TO_EDGE")
    return b.m("DIVIDE", vor.outputs["Distance"], scale)


def _grabens(b, vec, v, seed, lod):
    """Грабены: ~6 длинных пологих дуг (малые круги, слегка искривлённые; плоское днище, приподнятые плечи,
    отрезки сужаются к концам) + радиальная система борозд вокруг вулканического центра (как Фарсида).
    Возвращает (днище 0..1, плечи 0..1)."""
    import random
    rnd = random.Random(500 + seed)
    wv = b.noise(v, 2.0, detail=2).outputs["Color"]
    nw = b.v("NORMALIZE", b.v("ADD", vec, b.v("SCALE", b.v("SUBTRACT", wv, (0.5, 0.5, 0.5)), scale=0.05)))
    wvar = b.lin(b.noise(b.v("ADD", v, _seed_off(seed, 33)), 9.0, detail=2).outputs[0], 0.3, 0.7, 0.4, 1.6)
    rift = flank = None
    segn = None
    for k in range(6):
        if k % 3 == 0:
            segn = b.sep(b.noise(b.v("ADD", v, _seed_off(seed, 70 + k)), 3.0, detail=2).outputs["Color"])
        a = Vector((rnd.gauss(0, 1), rnd.gauss(0, 1), rnd.gauss(0, 1))).normalized()
        c = rnd.uniform(-0.5, 0.5)
        w = rnd.uniform(0.004, 0.010)
        d = b.m("ABSOLUTE", b.m("SUBTRACT", b.v("DOT_PRODUCT", nw, tuple(a)), c))
        segf = b.ss(segn[k % 3], 0.50, 0.60)
        we = b.m("MULTIPLY", b.m("MULTIPLY", wvar, segf), w)
        r = b.ss(d, we, b.m("MULTIPLY", we, 0.55))
        f = b.m("MULTIPLY", b.ss(d, b.m("MULTIPLY", we, 2.6), we), b.m("SUBTRACT", 1.0, r))
        rift = r if rift is None else b.m("MAXIMUM", rift, r)
        flank = f if flank is None else b.m("MAXIMUM", flank, f)
    if lod < 2:
        a = Vector((rnd.gauss(0, 1), rnd.gauss(0, 1), rnd.gauss(0, 1))).normalized()
        e1 = a.orthogonal().normalized()
        e2 = a.cross(e1)
        th = b.m("ARCTAN2", b.v("DOT_PRODUCT", nw, tuple(e2)), b.v("DOT_PRODUCT", nw, tuple(e1)))
        th = b.m("MULTIPLY_ADD", b.m("SUBTRACT", b.noise(v, 3.0, detail=1).outputs[0], 0.5), 0.25, th)
        ca = b.v("DOT_PRODUCT", nw, tuple(a))
        rho = b.m("ARCCOSINE", b.m("MINIMUM", b.m("MAXIMUM", ca, -1.0), 1.0))
        K = 36
        ad = b.m("MULTIPLY", b.m("ABSOLUTE", b.m("SINE", b.m("MULTIPLY", th, K / 2.0))),
                 b.m("MULTIPLY", b.m("SINE", rho), 2.0 / K))
        seg = b.m("MULTIPLY", b.ss(b.noise(b.v("ADD", v, _seed_off(seed, 77)), 5.0, detail=2).outputs[0], 0.45, 0.6),
                  b.m("MULTIPLY", b.ss(rho, 0.10, 0.22), b.ss(rho, 0.65, 0.40)))
        we = b.m("MULTIPLY", b.m("MULTIPLY", wvar, seg), 0.0022)
        r = b.m("MULTIPLY", b.ss(ad, we, b.m("MULTIPLY", we, 0.4)), 0.8)
        f = b.m("MULTIPLY", b.m("MULTIPLY", b.ss(ad, b.m("MULTIPLY", we, 2.5), we), b.m("SUBTRACT", 1.0, r)), 0.8)
        rift = b.m("MAXIMUM", rift, r)
        flank = b.m("MAXIMUM", flank, f)
    return rift, flank


def _segments(b, v, seed, s1, s2):
    """Маска «отрезков»: разломы — изолированные куски, сужающиеся к концам (0..1)."""
    m1 = b.ss(b.noise(b.v("ADD", v, _seed_off(seed, 31)), s1, detail=3).outputs[0], 0.50, 0.60)
    m2 = b.ss(b.noise(b.v("ADD", v, _seed_off(seed, 32)), s2, detail=2).outputs[0], 0.42, 0.58)
    return b.m("MULTIPLY", m1, m2)


def _mat_poltergeist(name, seed, radius, lod=0):
    mat, b, vec, bsdf = _surface_base(name)
    v = b.v("ADD", vec, _seed_off(seed, 1))
    # континенты (старая кора) / базальтовые равнины
    cn = b.noise(v, 1.05, detail=7 if lod < 2 else 4, rough=0.58, dist=0.35)
    cont = b.ss(cn.outputs[0], 0.50, 0.56)
    # горные хребты на континентах
    rg = b.noise(v, 4.5, detail=7 if lod < 2 else 3, rough=0.55, typ="RIDGED_MULTIFRACTAL")
    ridges = b.m("MULTIPLY", b.lin(rg.outputs[0], 0.3, 1.6), cont)
    # грабены (дуги + радиальная система) и мелкие трещины
    rift, flank = _grabens(b, vec, v, seed + 1, lod)
    wvar = b.lin(b.noise(b.v("ADD", v, _seed_off(seed, 34)), 9.0, detail=2).outputs[0], 0.3, 0.7, 0.35, 1.6)
    if lod < 2:
        e2 = _rift_net(b, v, 7.0, seed + 2, warp=0.7, oct2=0.2)
        seg2 = _segments(b, v, seed + 2, 3.5, 10.0)
        frac = b.ss(e2, b.m("MULTIPLY", b.m("MULTIPLY", wvar, seg2), 0.0028), 0.0)
    else:
        frac = 0.0
    # морщинные гряды в лавовых равнинах
    wr_ = b.noise(v, 11.0, detail=3, rough=0.5, typ="RIDGED_MULTIFRACTAL")
    wrink = b.m("MULTIPLY", b.lin(wr_.outputs[0], 0.7, 1.4), b.m("SUBTRACT", 1.0, cont))
    layers = _crater_layers([3.0, 5.0, 8.5, 14.0, 24.0, 40.0, 70.0], 0.5, dup=[11.0, 19.0, 31.0, 55.0], fresh=0.12,
                            depth_small=0.36, depth_big=0.12, lod=lod)
    H, halo, floor, _r = _craters(b, vec, layers, seed + 11)
    fine = b.m("MULTIPLY", _nz(b, lod, v, 70.0, detail=6, rough=0.65), 0.0016)
    height = b.m("MULTIPLY", cont, 0.004)
    height = b.m("MULTIPLY_ADD", ridges, 0.0075, height)
    height = b.m("MULTIPLY_ADD", rift, -0.0035, height)
    height = b.m("MULTIPLY_ADD", flank, 0.0009, height)
    height = b.m("MULTIPLY_ADD", frac, -0.0008, height)
    height = b.m("MULTIPLY_ADD", wrink, 0.0012, height)
    height = b.m("ADD", b.m("ADD", height, H), fine)
    # альбедо: базальтовые равнины 0.08–0.095, старая кора 0.11–0.13 (серо-бурая, хрома < 15 %)
    var = b.noise(v, 4.0, detail=10 if lod < 2 else 4, rough=0.62)
    tone = b.lin(var.outputs[0], 0.3, 0.7, 0.85, 1.15)
    crust = b.mix(b.ss(b.noise(b.v("ADD", v, (3.1, 1.7, 0.4)), 2.2, detail=6).outputs[0], 0.45, 0.62),
                  (0.118, 0.112, 0.105), (0.132, 0.122, 0.112))
    plains = b.mix(b.ss(b.noise(v, 3.0, detail=5).outputs[0], 0.4, 0.65), (0.080, 0.080, 0.082), (0.095, 0.092, 0.090))
    col = b.mix(cont, plains, crust)
    # молодые лавовые потоки — самые тёмные языки на равнинах
    flows = b.m("MULTIPLY", b.ss(b.noise(b.v("ADD", v, (9.1, 3.3, 5.5)), 5.0, detail=8 if lod < 2 else 4,
                                         rough=0.62, dist=0.6).outputs[0], 0.50, 0.56),
                b.m("SUBTRACT", 1.0, cont))
    col = b.mix(b.m("MULTIPLY", flows, 0.8), col, (0.060, 0.060, 0.063))
    # грабены видны в основном рельефом: днище лишь чуть темнее (осыпи/тёмный базальт)
    col = b.mix(b.m("MULTIPLY", b.m("MAXIMUM", rift, b.m("MULTIPLY", frac, 0.6)), 0.45), col, (0.065, 0.065, 0.068))
    col = b.mix(b.m("MULTIPLY", flank, 0.2), col, (0.105, 0.100, 0.096))
    col = b.v("SCALE", col, scale=tone)
    col = b.mix(b.m("MULTIPLY", halo, 0.5), col, (0.150, 0.146, 0.140))
    _finish(b, bsdf, height, radius, 1.5, col, 0.93, 0.85, 0.2)
    return mat


def _mat_phobetor(name, seed, radius, lod=0):
    import random
    mat, b, vec, bsdf = _surface_base(name)
    v = b.v("ADD", vec, _seed_off(seed, 2))
    # лёгкое искривление для «живых» дуг
    wv = b.noise(v, 2.5, detail=3).outputs["Color"]
    nw = b.v("NORMALIZE", b.v("ADD", vec, b.v("SCALE", b.v("SUBTRACT", wv, (0.5, 0.5, 0.5)), scale=0.07)))
    # линеи: короткие дуги малых кругов (сегменты сужаются к концам), ширины по степенному закону,
    # часть — циклоиды (цепочки дуг с остриями), старые — бледнее; 4 широкие тёмные полосы
    rnd = random.Random(1000 + seed)
    nl = (40, 24, 12)[lod]
    wmods = [b.noise(b.v("ADD", v, _seed_off(seed, 60 + j)), 6.0, detail=2).outputs["Color"] for j in range(2)]
    wmods = [b.sep(c) for c in wmods]
    segn = []
    line = ridge = stain = None
    for k in range(nl):
        if k % 3 == 0:
            segn = b.sep(b.noise(b.v("ADD", v, _seed_off(seed, 20 + k)), 2.5, detail=2).outputs["Color"])
        a = Vector((rnd.gauss(0, 1), rnd.gauss(0, 1), rnd.gauss(0, 1))).normalized()
        e1 = a.orthogonal().normalized()
        e2 = a.cross(e1)
        c = rnd.uniform(-0.55, 0.55)
        wide = k < 4
        w = rnd.uniform(0.011, 0.020) if wide else 0.0015 * (1.0 + 6.0 * rnd.random() ** 4)
        age = 1.0 if wide else rnd.uniform(0.35, 1.0)
        dd = b.m("SUBTRACT", b.v("DOT_PRODUCT", nw, tuple(a)), c)
        if not wide and rnd.random() < 0.18:  # циклоида: цепочка дуг с остриями
            th = b.m("ARCTAN2", b.v("DOT_PRODUCT", nw, tuple(e2)), b.v("DOT_PRODUCT", nw, tuple(e1)))
            kk = float(rnd.randint(9, 16))  # целое — без шва на ±pi
            amp = rnd.uniform(0.012, 0.022)
            dd = b.m("SUBTRACT", dd, b.m("MULTIPLY", b.m("ABSOLUTE", b.m("SINE", b.m("MULTIPLY", th, kk))), amp))
        d = b.m("ABSOLUTE", dd)
        segf = b.ss(segn[k % 3], 0.50, 0.58) if not wide else b.ss(segn[k % 3], 0.42, 0.53)
        wv_ = b.m("MULTIPLY", w, b.m("MULTIPLY", b.lin(wmods[k % 2][k % 3], 0.3, 0.7, 0.6, 1.4), segf))
        core = b.ss(d, wv_, b.m("MULTIPLY", wv_, 0.3))
        st = b.ss(d, b.m("MULTIPLY", wv_, 4.0), b.m("MULTIPLY", wv_, 0.5))
        if wide:
            stain = st if stain is None else b.m("MAXIMUM", stain, st)
            continue
        rdg = b.m("SUBTRACT", b.ss(d, b.m("MULTIPLY", wv_, 2.2), wv_),
                  b.m("MULTIPLY", b.ss(d, b.m("MULTIPLY", wv_, 0.5), 0.0), 0.7))
        core = b.m("MULTIPLY", core, age)
        st = b.m("MULTIPLY", st, age)
        rdg = b.m("MULTIPLY", rdg, age)
        line = core if line is None else b.m("MAXIMUM", line, core)
        ridge = rdg if ridge is None else b.m("ADD", ridge, rdg)
        stain = st if stain is None else b.m("MAXIMUM", stain, st)
    # сеть мелких трещин
    e2n = _rift_net(b, v, 4.5, seed + 3, warp=0.8)
    fr2 = b.m("MULTIPLY", b.ss(e2n, 0.0022, 0.0), b.ss(b.noise(v, 2.2, detail=2).outputs[0], 0.5, 0.62))
    if lod < 2:
        e3n = _rift_net(b, v, 11.0, seed + 4, warp=0.8)
        fr3 = b.m("MULTIPLY", b.ss(e3n, 0.0010, 0.0), b.ss(b.noise(v, 4.0, detail=2).outputs[0], 0.52, 0.66))
    else:
        fr3 = 0.0
    # хаос-ландшафт: светлые плиты с приподнятыми краями в буроватой матрице
    chn = b.noise(v, 3.5, detail=6, rough=0.6, dist=0.4)
    chaos = b.ss(chn.outputs[0], 0.58, 0.68)
    hum = _nz(b, lod, v, 45.0, detail=4, rough=0.6)
    blocks = b.node("ShaderNodeTexVoronoi", {"Vector": v, "Scale": 28.0}, voronoi_dimensions="3D", feature="F1")
    bedge = b.node("ShaderNodeTexVoronoi", {"Vector": v, "Scale": 28.0}, voronoi_dimensions="3D",
                   feature="DISTANCE_TO_EDGE").outputs["Distance"]
    plate_rim = b.m("MULTIPLY", chaos, b.ss(bedge, 0.10, 0.02))
    layers = _crater_layers([4.0, 7.0, 12.0, 20.0, 34.0], 0.22, fresh=0.25, depth_small=0.32, depth_big=0.1, lod=lod)
    H, halo, floor, _r = _craters(b, vec, layers, seed + 21)
    height = b.m("MULTIPLY", ridge, 0.0012)
    height = b.m("MULTIPLY_ADD", fr2, -0.0006, height)
    height = b.m("MULTIPLY_ADD", fr3, -0.0003, height)
    height = b.m("MULTIPLY_ADD", b.m("MULTIPLY", chaos, hum), 0.003, height)
    height = b.m("MULTIPLY_ADD", plate_rim, 0.0012, height)
    height = b.m("ADD", height, b.m("MULTIPLY", H, b.m("SUBTRACT", 1.0, chaos)))
    height = b.m("MULTIPLY_ADD", _nz(b, lod, v, 60.0, detail=3), 0.0005, height)
    # альбедо: лёд 0.6–0.7, старые поля серее, бурые пятна вдоль линей и в хаосе
    var = b.noise(v, 3.5, detail=10 if lod < 2 else 4, rough=0.6)
    tone = b.lin(var.outputs[0], 0.3, 0.7, 0.9, 1.06)
    old = b.ss(b.noise(b.v("ADD", v, (5.3, 2.2, 7.7)), 1.6, detail=6, rough=0.6).outputs[0], 0.45, 0.62)
    col = b.mix(old, (0.68, 0.69, 0.70), (0.58, 0.555, 0.53))
    # пятнистый (mottled) рельеф: бурые крапины по регионам
    mott = b.m("MULTIPLY", b.ss(b.noise(v, 9.0, detail=6, rough=0.6).outputs[0], 0.52, 0.68),
               b.ss(b.noise(b.v("ADD", v, (2.7, 8.1, 0.9)), 1.4, detail=3).outputs[0], 0.48, 0.6))
    col = b.mix(b.m("MULTIPLY", mott, 0.5), col, (0.52, 0.45, 0.37))
    brown = (0.40, 0.29, 0.20)
    col = b.mix(b.m("MULTIPLY", stain, 0.6), col, (0.50, 0.40, 0.30))
    col = b.mix(b.m("MULTIPLY", line, 0.85), col, brown)
    col = b.mix(b.m("MULTIPLY", chaos, b.lin(b.node("ShaderNodeSeparateColor", {0: blocks.outputs["Color"]}).outputs[0],
                                               0.0, 1.0, 0.3, 0.6)), col, (0.46, 0.38, 0.30))
    col = _grey(b, col, b.m("MULTIPLY", plate_rim, 0.05))
    col = b.mix(b.m("MULTIPLY", b.m("MAXIMUM", fr2, fr3), 0.2), col, (0.50, 0.45, 0.40))
    col = b.v("SCALE", col, scale=tone)
    col = b.mix(b.m("MULTIPLY", halo, 0.5), col, (0.78, 0.79, 0.80))
    _finish(b, bsdf, height, radius, 1.4, col, 0.62, 0.6, 0.45)
    return mat


# --------------------------------------------------------------------------- скалистые и ледяные миры (эп. 003+)
# Безатмосферные поверхности со своими цветами и морфологией (свет звезды окрашивает их сам). Аналоги из Солнечной
# системы — только как образец рельефа: базальт (b TRAPPIST-1), Меркурий, Марс, иней в холодных ловушках, Ганимед,
# Каллисто. Иней (frostrock) зависит от направления на звезду — узел SunCoord, его объект подставляет build_planet.

def _sun_coord(b):
    """Вектор «звезда → точка» в мире: TexCoord/Object от пустышки SunRef (без вращения)."""
    tc = b.node("ShaderNodeTexCoord")
    tc.name = tc.label = "SunCoord"
    return tc.outputs["Object"]


def _day_factor(b):
    """μ — косинус высоты звезды над местным горизонтом (геометрическая нормаль): 1 — подзвёздная точка, < 0 — ночь.
    У приливно захваченной планеты эта география постоянна."""
    geo = b.node("ShaderNodeNewGeometry")
    d = b.v("NORMALIZE", _sun_coord(b))
    return b.m("MULTIPLY", b.v("DOT_PRODUCT", geo.outputs["Normal"], d), -1.0)


def _mat_ember(name, seed, radius, lod=0):
    """Тёмный вулканический базальт (горячая безатмосферная планета): лавовые поля разного возраста с лопастными
    краями, щитовые вулканы с кальдерами, морщинные гряды, редкие кратеры; молодое лавовое стекло — с бликом."""
    mat, b, vec, bsdf = _surface_base(name)
    v = b.v("ADD", vec, _seed_off(seed, 3))
    det = 8 if lod < 2 else 4
    age = b.noise(v, 1.4, detail=6, rough=0.6, dist=0.6).outputs[0]
    young = b.ss(age, 0.50, 0.57)
    lob = b.ss(b.noise(b.v("ADD", v, (2.1, 7.3, 4.4)), 3.2, detail=det, rough=0.62, dist=1.4).outputs[0], 0.53, 0.56)
    # щиты: Вороной F1 — пологий купол и кальдера у ~40 % ячеек
    vor = b.node("ShaderNodeTexVoronoi", {"Vector": b.v("ADD", v, (5.5, 1.2, 9.9)), "Scale": 3.0,
                                           "Randomness": 0.85}, voronoi_dimensions="3D", feature="F1")
    rr = b.node("ShaderNodeSeparateColor", {0: vor.outputs["Color"]}).outputs
    has = b.ss(rr[0], 0.58, 0.62)
    x = b.m("DIVIDE", vor.outputs["Distance"], b.lin(rr[1], 0.0, 1.0, 0.18, 0.34))
    dome = b.m("MULTIPLY", b.ss(x, 1.0, 0.0), has)
    cald = b.m("MULTIPLY", b.ss(x, 0.16, 0.10), has)
    wr = b.lin(b.noise(v, 10.0, detail=4, rough=0.5, typ="RIDGED_MULTIFRACTAL").outputs[0], 0.75, 1.5)
    layers = _crater_layers([5.0, 9.0, 16.0, 28.0, 50.0, 90.0], 0.30, fresh=0.18, depth_small=0.42,
                            depth_big=0.14, dup=[13.0, 22.0, 40.0, 70.0], lod=lod)
    H, halo, floor, _r = _craters(b, vec, layers, seed + 5)
    height = b.m("MULTIPLY", dome, 0.0055)
    height = b.m("MULTIPLY_ADD", cald, -0.0045, height)
    height = b.m("MULTIPLY_ADD", lob, 0.0012, height)
    height = b.m("MULTIPLY_ADD", wr, 0.0009, height)
    height = b.m("ADD", height, b.m("MULTIPLY", H, b.m("SUBTRACT", 1.0, b.m("MULTIPLY", young, 0.8))))
    height = b.m("ADD", height, b.m("MULTIPLY", _nz(b, lod, v, 110.0, detail=4, rough=0.65), 0.0008))
    # альбедо ~0.04–0.09: молодые потоки чернее и холоднее, старые — буроватые, свежие выбросы светлее
    var = b.lin(b.noise(v, 6.0, detail=det, rough=0.6).outputs[0], 0.3, 0.7, 0.85, 1.15)
    old = b.mix(b.ss(b.noise(b.v("ADD", v, (8.8, 0.3, 2.2)), 2.5, detail=4).outputs[0], 0.4, 0.62),
                (0.055, 0.049, 0.045), (0.067, 0.058, 0.050))
    col = b.mix(young, old, (0.029, 0.030, 0.034))
    col = b.mix(b.m("MULTIPLY", lob, 0.35), col, (0.042, 0.041, 0.042))
    col = b.mix(cald, col, (0.022, 0.021, 0.022))
    col = b.v("SCALE", col, scale=var)
    col = b.mix(b.m("MULTIPLY", halo, 0.6), col, (0.10, 0.096, 0.092))
    _finish(b, bsdf, height, radius, 1.2, col, b.lin(young, 0.0, 1.0, 0.88, 0.62), 0.9, 0.35)
    return mat


def _mat_scorched(name, seed, radius, lod=0):
    """Серый кратерированный камень (как Меркурий): гладкие межкратерные равнины, насыщенные кратеры, свежие
    кратеры с яркими лучами, лопастные уступы (сжатие коры), тёмный синеватый «низкоотражающий» материал."""
    import random
    mat, b, vec, bsdf = _surface_base(name)
    v = b.v("ADD", vec, _seed_off(seed, 4))
    det = 8 if lod < 2 else 4
    plains = b.ss(b.noise(v, 1.3, detail=5, rough=0.55, dist=0.3).outputs[0], 0.55, 0.63)
    layers = _crater_layers([1.6, 2.6, 4.2, 6.8, 11.0, 18.0, 30.0, 50.0, 85.0, 140.0], 1.0,
                            dup=[3.4, 5.5, 9.0, 14.5, 24.0, 40.0, 68.0, 110.0], fresh=0.06,
                            depth_big=0.18, depth_small=0.46, lod=lod)
    rays_l = [] if lod == 2 else [(3.2, 0.55, 0.04, 0.07, 0.45, 0.1, 0.0, 0.0, 1.0, 22.0),
                                  (6.0, 0.45, 0.04, 0.08, 0.45, 0.1, 0.0, 0.0, 1.0, 14.0),
                                  (11.0, 0.35, 0.05, 0.09, 0.45, 0.1, 0.0, 0.0, 1.0, 9.0)]
    H, halo, floor, rays = _craters(b, vec, layers, seed + 9, rays_layers=rays_l)
    # лопастные уступы: длинные дуги малых кругов — пологий подъём и крутой фронт, отрезками
    rnd = random.Random(900 + seed)
    wv = b.noise(v, 2.2, detail=2).outputs["Color"]
    nw = b.v("NORMALIZE", b.v("ADD", vec, b.v("SCALE", b.v("SUBTRACT", wv, (0.5, 0.5, 0.5)), scale=0.06)))
    scarp = None
    for k in range(5):
        a = Vector((rnd.gauss(0, 1), rnd.gauss(0, 1), rnd.gauss(0, 1))).normalized()
        dd = b.m("SUBTRACT", b.v("DOT_PRODUCT", nw, tuple(a)), rnd.uniform(-0.6, 0.6))
        h = b.m("MULTIPLY", b.ss(dd, -0.035, 0.0), b.m("SUBTRACT", 1.0, b.ss(dd, 0.0, 0.0025)))
        h = b.m("MULTIPLY", h, b.ss(b.noise(b.v("ADD", v, _seed_off(seed, 40 + k)), 2.0, detail=2).outputs[0],
                                    0.48, 0.58))
        scarp = h if scarp is None else b.m("MAXIMUM", scarp, h)
    Hm = b.m("MULTIPLY", H, b.m("SUBTRACT", 1.0, b.m("MULTIPLY", plains, 0.6)))
    height = b.m("ADD", Hm, b.m("MULTIPLY", scarp, 0.0025))
    height = b.m("ADD", height, b.m("MULTIPLY", _nz(b, lod, v, 120.0, detail=4, rough=0.6), 0.0008))
    # альбедо ~0.10–0.16, серое; лучи и свежие выбросы ярче, LRM темнее и синее
    var = b.lin(b.noise(v, 5.0, detail=det, rough=0.62).outputs[0], 0.3, 0.7, 0.86, 1.14)
    base = b.mix(b.ss(b.noise(b.v("ADD", v, (1.7, 4.4, 8.2)), 2.0, detail=5).outputs[0], 0.42, 0.62),
                 (0.128, 0.122, 0.114), (0.150, 0.144, 0.134))
    col = b.mix(plains, base, (0.160, 0.152, 0.140))
    lrm = b.ss(b.noise(b.v("ADD", v, (6.1, 2.8, 0.5)), 3.0, detail=5, rough=0.6).outputs[0], 0.60, 0.68)
    col = b.mix(b.m("MULTIPLY", lrm, 0.7), col, (0.085, 0.090, 0.098))
    col = b.mix(b.m("MULTIPLY", floor, 0.3), col, (0.12, 0.118, 0.115))
    col = b.v("SCALE", col, scale=var)
    col = _grey(b, col, b.m("MULTIPLY", rays, 0.11))
    col = b.mix(b.m("MULTIPLY", halo, 0.6), col, (0.26, 0.255, 0.25))
    _finish(b, bsdf, height, radius, 1.15, col, 0.95, 1.0, 0.15)
    return mat


def _mat_rust(name, seed, radius, lod=0):
    """Окисленная каменистая пустыня (ржаво-охристая, без атмосферы): светлые пыльные области и тёмные базальтовые
    поля с дюнами, каньоны, плато и низины, умеренно кратерированная поверхность, тёмный песок в днищах."""
    mat, b, vec, bsdf = _surface_base(name)
    v = b.v("ADD", vec, _seed_off(seed, 6))
    det = 8 if lod < 2 else 4
    dark = b.ss(b.noise(v, 1.1, detail=6, rough=0.6, dist=0.8).outputs[0], 0.50, 0.60)
    rift, flank = _grabens(b, vec, v, seed + 2, lod)
    layers = _crater_layers([2.4, 4.0, 6.5, 11.0, 18.0, 30.0, 52.0, 90.0], 0.55, dup=[8.5, 14.0, 24.0, 42.0, 70.0],
                            fresh=0.08, depth_big=0.14, depth_small=0.38, lod=lod)
    H, halo, floor, _r = _craters(b, vec, layers, seed + 13)
    height = b.m("ADD", H, b.m("MULTIPLY", _nz(b, lod, v, 100.0, detail=4, rough=0.65), 0.0010))
    height = b.m("MULTIPLY_ADD", rift, -0.0060, height)
    height = b.m("MULTIPLY_ADD", flank, 0.0010, height)
    height = b.m("MULTIPLY_ADD", b.noise(v, 3.0, detail=6, rough=0.55).outputs[0], 0.004, height)  # плато и низины
    if lod < 2:
        dn = b.noise(b.v("MULTIPLY", v, (1.0, 1.0, 3.5)), 40.0, detail=2, rough=0.5, typ="RIDGED_MULTIFRACTAL")
        dunes = b.m("MULTIPLY", b.lin(dn.outputs[0], 0.8, 1.4),
                    b.m("MULTIPLY", dark, b.ss(b.noise(v, 4.0, detail=2).outputs[0], 0.5, 0.6)))
        height = b.m("MULTIPLY_ADD", dunes, 0.0004, height)
    var = b.lin(b.noise(v, 5.0, detail=det, rough=0.62).outputs[0], 0.3, 0.7, 0.85, 1.15)
    dust = b.mix(b.ss(b.noise(b.v("ADD", v, (3.3, 8.1, 1.4)), 2.4, detail=5).outputs[0], 0.4, 0.62),
                 (0.31, 0.18, 0.095), (0.37, 0.23, 0.12))
    col = b.mix(dark, dust, (0.10, 0.072, 0.055))
    col = b.mix(b.m("MULTIPLY", rift, 0.6), col, (0.16, 0.085, 0.05))
    col = b.mix(b.m("MULTIPLY", floor, 0.45), col, (0.14, 0.08, 0.05))
    col = b.v("SCALE", col, scale=var)
    col = b.mix(b.m("MULTIPLY", halo, 0.5), col, (0.40, 0.26, 0.16))
    _finish(b, bsdf, height, radius, 1.3, col, 0.92, 0.95, 0.15)
    return mat


def _mat_frostrock(name, seed, radius, lod=0):
    """Тёмный серо-синий камень с инеем: иней там, где звезда низко или не всходит (μ < ~0.3), пятнами, в днищах
    кратеров — дальше в день (холодные ловушки). Направление на звезду — SunCoord (см. build_planet)."""
    mat, b, vec, bsdf = _surface_base(name)
    v = b.v("ADD", vec, _seed_off(seed, 8))
    det = 8 if lod < 2 else 4
    high = b.ss(b.noise(v, 1.5, detail=6, rough=0.58, dist=0.4).outputs[0], 0.50, 0.58)
    ridges = b.m("MULTIPLY", b.lin(b.noise(v, 5.0, detail=det, rough=0.55, typ="RIDGED_MULTIFRACTAL").outputs[0],
                                   0.4, 1.6), high)
    layers = _crater_layers([2.8, 4.6, 7.5, 12.5, 21.0, 36.0, 60.0, 100.0], 0.65, dup=[10.0, 17.0, 29.0, 48.0, 80.0],
                            fresh=0.10, depth_big=0.15, depth_small=0.40, lod=lod)
    H, halo, floor, _r = _craters(b, vec, layers, seed + 17)
    height = b.m("ADD", b.m("MULTIPLY", high, 0.003), b.m("MULTIPLY", ridges, 0.004))
    height = b.m("ADD", height, b.m("ADD", H, b.m("MULTIPLY", _nz(b, lod, v, 100.0, detail=4, rough=0.65), 0.0009)))
    patchy = b.lin(b.noise(b.v("ADD", v, (4.2, 9.1, 3.3)), 9.0, detail=det, rough=0.6).outputs[0],
                   0.35, 0.65, -0.12, 0.12)
    thr = b.m("ADD", b.m("ADD", _day_factor(b), patchy), b.m("MULTIPLY", floor, -0.18))
    frost = b.ss(thr, 0.32, 0.08)
    var = b.lin(b.noise(v, 5.0, detail=det, rough=0.62).outputs[0], 0.3, 0.7, 0.85, 1.15)
    rock = b.v("SCALE", b.mix(high, (0.085, 0.088, 0.095), (0.13, 0.13, 0.135)), scale=var)
    rock = b.mix(b.m("MULTIPLY", halo, 0.5), rock, (0.22, 0.22, 0.23))
    ice = b.v("SCALE", (0.62, 0.66, 0.72), scale=b.lin(_nz(b, lod, v, 30.0, detail=3), 0.3, 0.7, 0.9, 1.05))
    col = b.mix(frost, rock, ice)
    _finish(b, bsdf, height, radius, 1.25, col, b.lin(frost, 0.0, 1.0, 0.92, 0.78), 0.85, 0.2)
    return mat


def _mat_grooved(name, seed, radius, lod=0):
    """Ледяная кора как у Ганимеда: древние тёмные полигоны и светлые полосы бороздчатого льда (параллельные
    борозды своего направления в каждой полосе, чуть ниже полигонов), кратеры с яркими выбросами."""
    mat, b, vec, bsdf = _surface_base(name)
    v = b.v("ADD", vec, _seed_off(seed, 10))
    det = 8 if lod < 2 else 4
    wv = b.noise(v, 1.8, detail=3).outputs["Color"]
    pw = b.v("ADD", v, b.v("SCALE", b.v("SUBTRACT", wv, (0.5, 0.5, 0.5)), scale=0.35))
    cells = b.node("ShaderNodeTexVoronoi", {"Vector": pw, "Scale": 2.2, "Randomness": 1.0},
                   voronoi_dimensions="3D", feature="F1")
    cc = cells.outputs["Color"]
    cr = b.node("ShaderNodeSeparateColor", {0: cc}).outputs
    bright = b.ss(cr[0], 0.42, 0.48)
    edge = b.node("ShaderNodeTexVoronoi", {"Vector": pw, "Scale": 2.2, "Randomness": 1.0},
                  voronoi_dimensions="3D", feature="DISTANCE_TO_EDGE").outputs["Distance"]
    rim = b.ss(edge, 0.05, 0.0)
    if lod < 2:
        dirc = b.v("NORMALIZE", b.v("SUBTRACT", cc, (0.5, 0.5, 0.5)))
        ph = b.m("MULTIPLY", b.v("DOT_PRODUCT", pw, dirc), b.lin(cr[1], 0.0, 1.0, 140.0, 260.0))
        gr = b.m("MULTIPLY", b.m("ADD", b.m("SINE", ph), 1.0), 0.5)
        grooves = b.m("MULTIPLY", b.m("POWER", gr, 3.0), bright)
    else:
        grooves = 0.0
    layers = _crater_layers([3.0, 5.0, 8.5, 14.0, 24.0, 40.0, 68.0], 0.5, dup=[11.0, 19.0, 32.0, 54.0],
                            fresh=0.20, depth_big=0.12, depth_small=0.36, lod=lod)
    H, halo, floor, _r = _craters(b, vec, layers, seed + 23)
    height = b.m("ADD", b.m("MULTIPLY", grooves, 0.0009), b.m("ADD", H, b.m("MULTIPLY", _nz(b, lod, v, 90.0, detail=4,
                                                                                             rough=0.6), 0.0007)))
    height = b.m("MULTIPLY_ADD", bright, -0.0015, height)
    height = b.m("MULTIPLY_ADD", rim, 0.0010, height)
    var = b.lin(b.noise(v, 6.0, detail=det, rough=0.6).outputs[0], 0.3, 0.7, 0.88, 1.12)
    darkt = b.mix(b.ss(b.noise(b.v("ADD", v, (2.2, 5.5, 7.1)), 3.0, detail=5).outputs[0], 0.4, 0.62),
                  (0.17, 0.15, 0.13), (0.21, 0.185, 0.16))
    brightt = b.mix(b.m("MULTIPLY", grooves, 0.5), (0.44, 0.44, 0.45), (0.36, 0.36, 0.38))
    col = b.mix(bright, darkt, brightt)
    col = b.v("SCALE", col, scale=var)
    col = b.mix(b.m("MULTIPLY", halo, 0.8), col, (0.62, 0.63, 0.66))
    _finish(b, bsdf, height, radius, 1.2, col, 0.8, 0.7, 0.35)
    return mat


def _mat_dirtyice(name, seed, radius, lod=0):
    """Тёмный грязный лёд как у Каллисто: насыщенная кратерами древняя кора, светлые ледяные валы и свежие
    кратеры, тёмная пыль в низинах и днищах, многокольцевой ударный бассейн."""
    import random
    mat, b, vec, bsdf = _surface_base(name)
    v = b.v("ADD", vec, _seed_off(seed, 12))
    det = 8 if lod < 2 else 4
    layers = _crater_layers([2.0, 3.3, 5.4, 9.0, 15.0, 25.0, 42.0, 70.0, 116.0], 1.0,
                            dup=[4.3, 7.0, 12.0, 20.0, 33.0, 55.0, 92.0], fresh=0.07, depth_big=0.12,
                            depth_small=0.32, rim_k=0.30, lod=lod)
    H, halo, floor, _r = _craters(b, vec, layers, seed + 29)
    rnd = random.Random(1200 + seed)
    a = Vector((rnd.gauss(0, 1), rnd.gauss(0, 1), rnd.gauss(0, 1))).normalized()
    rho = b.m("ARCCOSINE", b.m("MINIMUM", b.m("MAXIMUM", b.v("DOT_PRODUCT", vec, tuple(a)), -1.0), 1.0))
    rho_w = b.m("MULTIPLY_ADD", b.m("SUBTRACT", b.noise(v, 6.0, detail=2).outputs[0], 0.5), 0.03, rho)
    rings = b.m("MULTIPLY", b.ss(b.m("SINE", b.m("MULTIPLY", rho_w, 60.0)), 0.6, 1.0),
                b.m("MULTIPLY", b.ss(rho, 0.08, 0.14), b.ss(rho, 0.75, 0.45)))
    core = b.ss(rho, 0.10, 0.04)
    height = b.m("ADD", H, b.m("ADD", b.m("MULTIPLY", rings, 0.0012),
                                b.m("MULTIPLY", _nz(b, lod, v, 100.0, detail=4, rough=0.6), 0.0007)))
    lows = b.ss(b.noise(b.v("ADD", v, (7.7, 3.1, 5.9)), 2.8, detail=5, rough=0.6).outputs[0], 0.55, 0.40)
    var = b.lin(b.noise(v, 6.0, detail=det, rough=0.6).outputs[0], 0.3, 0.7, 0.86, 1.14)
    col = b.mix(lows, (0.10, 0.085, 0.072), (0.15, 0.13, 0.11))
    col = b.mix(b.m("MULTIPLY", floor, 0.4), col, (0.075, 0.065, 0.057))
    col = b.mix(b.m("MULTIPLY", rings, 0.6), col, (0.30, 0.29, 0.28))
    col = b.mix(b.m("MULTIPLY", core, 0.7), col, (0.42, 0.42, 0.43))
    col = b.v("SCALE", col, scale=var)
    col = b.mix(b.m("MULTIPLY", halo, 0.7), col, (0.55, 0.56, 0.58))
    _finish(b, bsdf, height, radius, 1.15, col, 0.85, 0.85, 0.3)
    return mat


def _mat_brightice(name, seed, radius, lod=0):
    """Яркий чистый лёд, как у Мимаса, Тефии, Реи: альбедо ~0.7–0.8, кора насыщена кратерами с оплывшими валами,
    днища чуть темнее (осевшая пыль), свежие выбросы голубоватые."""
    mat, b, vec, bsdf = _surface_base(name)
    v = b.v("ADD", vec, _seed_off(seed, 21))
    det = 8 if lod < 2 else 4
    layers = _crater_layers([2.2, 3.6, 6.0, 10.0, 16.0, 27.0, 45.0, 75.0, 125.0], 1.0,
                            dup=[4.6, 7.6, 12.8, 21.0, 35.0, 58.0, 98.0], fresh=0.05, depth_big=0.14,
                            depth_small=0.36, rim_k=0.26, lod=lod)
    H, halo, floor, _r = _craters(b, vec, layers, seed + 41)
    height = b.m("ADD", H, b.m("MULTIPLY", _nz(b, lod, v, 90.0, detail=4, rough=0.6), 0.0008))
    var = b.lin(b.noise(v, 5.0, detail=det, rough=0.6).outputs[0], 0.3, 0.7, 0.93, 1.05)
    tint = b.lin(b.noise(b.v("ADD", v, (2.2, 6.1, 3.3)), 1.4, detail=3).outputs[0], 0.35, 0.65, 0.0, 1.0)
    col = b.mix(tint, (0.72, 0.73, 0.75), (0.76, 0.77, 0.80))
    col = b.mix(b.m("MULTIPLY", floor, 0.35), col, (0.62, 0.62, 0.63))
    col = b.v("SCALE", col, scale=var)
    col = b.mix(b.m("MULTIPLY", halo, 0.6), col, (0.80, 0.84, 0.90))
    _finish(b, bsdf, height, radius, 1.1, col, 0.80, 0.90, 0.35)
    return mat


SURFACE = {"draugr": _mat_draugr, "poltergeist": _mat_poltergeist, "phobetor": _mat_phobetor,
           "ember": _mat_ember, "scorched": _mat_scorched, "rust": _mat_rust, "frostrock": _mat_frostrock,
           "grooved": _mat_grooved, "dirtyice": _mat_dirtyice, "brightice": _mat_brightice}


# --------------------------------------------------------------------------- солнце (пульсар)

def _sun_nodes(b, sunref, power_name="sun_power", power=1.0):
    """L (единичный вектор на пульсар), освещённость E (пиксель белого диффуза)."""
    tc = b.node("ShaderNodeTexCoord", object=sunref)
    s = b.v("SCALE", tc.outputs["Object"], scale=-1.0)
    dist = b.v("LENGTH", s)
    L = b.v("SCALE", s, scale=b.m("DIVIDE", 1.0, b.m("MAXIMUM", dist, 1e-4)))
    pw = b.node("ShaderNodeValue", name=power_name, label=power_name)
    pw.outputs[0].default_value = power
    E = b.m("DIVIDE", pw.outputs[0], b.m("MAXIMUM", b.m("MULTIPLY", dist, dist), 1e-6))
    return L, E


# --------------------------------------------------------------------------- атмосфера

def _mat_atmosphere(name, Rp, cfg, sunref, power, sun_color=(1.0, 1.0, 1.0)):
    """Оболочка: по точке входа луча аналитически считаем прицельный параметр b, столб воздуха
    (Чепмен для экспоненциальной атмосферы), освещённость точки рассеяния и фазовую функцию.
    Эмиссия = однократное рассеяние, прозрачность = exp(-tau). Только лицевая сторона."""
    mat, nodes, links, out = C.new_material(name)
    b = _NB(mat.node_tree)
    H = cfg["H"] * Rp
    geo = b.node("ShaderNodeNewGeometry")
    obi = b.node("ShaderNodeObjectInfo")
    P = b.v("SUBTRACT", geo.outputs["Position"], obi.outputs["Location"])
    I = geo.outputs["Incoming"]
    pI = b.v("DOT_PRODUCT", P, I)
    b2 = b.m("MAXIMUM", b.m("SUBTRACT", b.v("DOT_PRODUCT", P, P), b.m("MULTIPLY", pI, pI)), 0.0)
    bb = b.m("SQRT", b2)
    chmax = math.sqrt(math.pi * Rp / (2.0 * H))  # половина касательного столба, в вертикальных толщах
    mu = b.m("SQRT", b.m("MAXIMUM", b.m("SUBTRACT", 1.0, b.m("DIVIDE", b2, Rp * Rp)), 1e-8))
    c_disk = b.m("MINIMUM", b.m("DIVIDE", 1.0, mu), chmax)
    c_limb = b.m("MULTIPLY", 2.0 * chmax,
                 b.m("EXPONENT", b.m("MINIMUM", b.m("DIVIDE", b.m("SUBTRACT", Rp, bb), H), 0.0)))
    above = b.m("GREATER_THAN", bb, Rp)
    col = b.m("MULTIPLY_ADD", above, b.m("SUBTRACT", c_limb, c_disk), c_disk)
    # точка рассеяния: касательная точка (над лимбом) или точка поверхности (над диском)
    t = b.m("SUBTRACT", pI, b.m("SQRT", b.m("MAXIMUM", b.m("SUBTRACT", Rp * Rp, b2), 0.0)))
    X = b.v("NORMALIZE", b.v("SUBTRACT", P, b.v("SCALE", I, scale=t)))
    L, E = _sun_nodes(b, sunref, power=power)
    mus = b.v("DOT_PRODUCT", X, L)
    # сумерки + слабый «хвост» многократного рассеяния → тонкое кольцо на просвет
    cs = b.v("DOT_PRODUCT", b.v("SCALE", L, scale=-1.0), I)  # косинус угла рассеяния (1 — вперёд)
    tail = b.m("MULTIPLY", b.m("MULTIPLY", b.ss(mus, -0.65, 0.0), b.ss(cs, 0.35, 0.9)),
               b.m("MULTIPLY", above, cfg["tail"]))  # только над лимбом и только на просвет
    lit = b.m("ADD", tail, b.ss(mus, cfg["tw"][0], cfg["tw"][1]))
    # фаза: Рэлей + Хеньи–Гринстейн (вперёд — серп «на просвет»)
    pr = b.m("MULTIPLY", b.m("MULTIPLY_ADD", cs, cs, 1.0), 3.0 / 16.0)  # уже умножено на pi
    g = cfg["g"]
    hg_den = b.m("POWER", b.m("MAXIMUM", b.m("MULTIPLY_ADD", cs, -2.0 * g, 1.0 + g * g), 1e-4), 1.5)
    hg = b.m("DIVIDE", (1.0 - g * g) / 4.0, hg_den)
    ph = b.m("ADD", b.m("MULTIPLY", pr, 1.0 - cfg["mie"]), b.m("MULTIPLY", hg, cfg["mie"]))
    tau = b.v("SCALE", cfg["tau"], scale=col)
    one_m = b.v("SUBTRACT", (1.0, 1.0, 1.0), b.vexp_neg(tau))
    # покраснение падающего света у терминатора (скользящий путь)
    c_in = b.m("MINIMUM", b.m("DIVIDE", 1.0, b.m("MAXIMUM", b.m("ADD", mus, 0.03), 1e-3)), 2.0 * chmax)
    t_in = b.vexp_neg(b.v("SCALE", cfg["tau"], scale=b.m("MULTIPLY", c_in, 0.5)))
    front = b.m("SUBTRACT", 1.0, geo.outputs["Backfacing"])
    k = b.m("MULTIPLY", b.m("MULTIPLY", b.m("MULTIPLY", E, ph), lit), front)
    emis = b.v("SCALE", b.v("MULTIPLY", one_m, t_in), scale=k)
    # цвет света пульсара (K_POINT откалиброван белым светом → цвет — множитель, как у поверхности)
    sc_ = b.node("ShaderNodeRGB", name="sun_color", label="sun_color")
    sc_.outputs[0].default_value = (*sun_color[:3], 1.0)
    emis = b.v("MULTIPLY", emis, sc_.outputs[0])
    trans = b.v("ADD", b.v("SCALE", b.vexp_neg(tau), scale=front),
                b.v("SCALE", (1.0, 1.0, 1.0), scale=geo.outputs["Backfacing"]))
    em = b.node("ShaderNodeEmission", {"Color": emis, "Strength": 1.0})
    tr = b.node("ShaderNodeBsdfTransparent", {"Color": trans})
    add = b.node("ShaderNodeAddShader", {0: em.outputs[0], 1: tr.outputs[0]})
    b.put(out.inputs["Surface"], add.outputs[0])
    return mat


# --------------------------------------------------------------------------- сияния

def _aurora_group(name, frame_start, frame_end, seed=0, speed=1.0):
    """Узор сияний в магнитной системе: гладкий овал (сдвинут к ночной стороне), тонкие дуги-шторы
    с лучами вдоль овала, диффузная полоса; выход — интенсивности зелёной, красной и фиолетовой
    компонент. Лучи зависят только от азимута → строго вертикальны по высоте; овал с высотой
    уходит к экватору (наклон силовых линий диполя ~13°)."""
    g = bpy.data.node_groups.new(name, "ShaderNodeTree")
    it = g.interface
    it.new_socket("Vector", in_out="INPUT", socket_type="NodeSocketVector")
    it.new_socket("Alt", in_out="INPUT", socket_type="NodeSocketFloat")
    it.new_socket("NightDot", in_out="INPUT", socket_type="NodeSocketFloat")
    it.new_socket("Smear", in_out="INPUT", socket_type="NodeSocketFloat")
    for nm in ("Green", "Red", "Purple"):
        it.new_socket(nm, in_out="OUTPUT", socket_type="NodeSocketFloat")
    b = _NB(g)
    gi = b.N.new("NodeGroupInput")
    go = b.N.new("NodeGroupOutput")
    i = gi.outputs
    # время для ряби — ключи LINEAR
    tv = b.node("ShaderNodeValue", name="aurora_time", label="aurora_time")
    tv.outputs[0].default_value = 0.0
    tv.outputs[0].keyframe_insert("default_value", frame=frame_start)
    tv.outputs[0].default_value = (frame_end - frame_start) / C.scene_fps() * speed
    tv.outputs[0].keyframe_insert("default_value", frame=frame_end)
    _linearize(g)
    T = tv.outputs[0]
    so = [_seed_off(seed, 90 + k) for k in range(6)]  # у каждой планеты свой узор
    n = b.v("NORMALIZE", i["Vector"])
    ns = lambda k: b.v("ADD", n, so[k])  # noqa: E731
    sx = b.sep(n)
    colat = b.m("ARCCOSINE", b.m("ABSOLUTE", sx[2]))
    alt = i["Alt"]
    # овал: гладкий, крупные складки; ночью шире и ниже по широте; с высотой — к экватору
    wav = b.m("SUBTRACT", b.noise(ns(0), 1.3, detail=1, w=b.m("MULTIPLY", T, 0.05)).outputs[0], 0.5)
    wav2 = b.m("SUBTRACT", b.noise(ns(1), 2.2, detail=1, w=b.m("MULTIPLY", T, 0.10)).outputs[0], 0.5)
    c0 = b.m("MULTIPLY_ADD", wav, 0.34, 0.31)
    c0 = b.m("MULTIPLY_ADD", i["NightDot"], -0.05, c0)
    c0 = b.m("MULTIPLY_ADD", alt, 0.010, c0)
    d = b.m("SUBTRACT", colat, c0)

    def gauss(x, w):
        return b.m("EXPONENT", b.m("MULTIPLY", b.m("MULTIPLY", x, x), -1.0 / (w * w)))

    sm2 = b.m("MULTIPLY", b.m("MULTIPLY", i["Smear"], i["Smear"]), 1.0 / 6.0)

    def gauss_s(x, w):
        """Профиль, размытый по широте на ход луча внутри слоя оболочки (интеграл сохраняется):
        соседние оболочки сливаются в сплошную штору, а не в стопку линий."""
        we = b.m("SQRT", b.m("ADD", sm2, w * w))
        e = b.m("EXPONENT", b.m("DIVIDE", b.m("MULTIPLY", x, x), b.m("MULTIPLY", b.m("MULTIPLY", we, we), -1.0)))
        return b.m("MULTIPLY", e, b.m("DIVIDE", w, we))
    # мелкие складки только у главной дуги
    fold = b.m("MULTIPLY", b.m("SUBTRACT", b.noise(ns(2), 14.0, detail=2, w=b.m("MULTIPLY", T, 0.3)).outputs[0],
                               0.5), 0.012)
    a1 = gauss_s(b.m("ADD", d, fold), 0.010)
    # вторая дуга — обрывками, не сплошным кольцом
    a2on = b.ss(b.noise(ns(3), 2.6, detail=1, w=b.m("MULTIPLY", T, 0.07)).outputs[0], 0.42, 0.60)
    a2 = b.m("MULTIPLY", gauss_s(b.m("ADD", d, b.m("MULTIPLY_ADD", wav2, 0.04, 0.035)), 0.008),
             b.m("MULTIPLY", a2on, 0.55))
    # диффузная полоса к экватору, на ночной стороне шире и дальше
    nshift = b.m("MAXIMUM", b.m("MULTIPLY", i["NightDot"], -1.0), 0.0)
    a3 = b.m("MULTIPLY", gauss_s(b.m("SUBTRACT", d, b.m("MULTIPLY_ADD", nshift, 0.025, 0.014)), 0.035), 0.15)
    # лучи-шторы: шум на окружности азимута (без широты/высоты) → ~150 лучей вдоль овала
    rxy = b.m("MAXIMUM", b.m("SQRT", b.m("MULTIPLY_ADD", sx[0], sx[0], b.m("MULTIPLY", sx[1], sx[1]))), 1e-5)
    ring = b.v("ADD", b.comb(b.m("MULTIPLY", b.m("DIVIDE", sx[0], rxy), 4.0),
                             b.m("MULTIPLY", b.m("DIVIDE", sx[1], rxy), 4.0), 0.0), so[3])
    rn = b.m("MULTIPLY", b.noise(ring, 6.0, detail=3, rough=0.55, w=b.m("MULTIPLY", T, 0.6)).outputs[0],
             b.lin(b.noise(ring, 1.5, detail=2, w=b.m("MULTIPLY", T, 0.3)).outputs[0], 0.3, 0.7, 0.6, 1.5))
    rays = b.m("ADD", 0.2, b.m("MULTIPLY", b.ss(rn, 0.42, 0.72), 1.5))
    # пятнистость по длине овала (низкая частота) + усиление к полуночи
    pm = b.noise(ns(4), 4.0, detail=2, w=b.m("MULTIPLY", T, 0.15)).outputs[0]
    patch = b.m("ADD", 0.25, b.m("MULTIPLY", b.ss(pm, 0.45, 0.78), 0.9))
    arcs = b.m("MULTIPLY", b.m("ADD", a1, a2), rays)
    I = b.m("MULTIPLY", b.m("ADD", arcs, a3), patch)
    # нижняя кромка гуляет; зелёный — у кромки, красный 630 нм — выше, фиолетовая кайма — снизу
    bot = b.m("MULTIPLY", b.noise(ns(5), 12.0, detail=2, w=b.m("MULTIPLY", T, 0.3)).outputs[0], 0.25)
    above = b.m("SUBTRACT", alt, bot)
    green = b.m("MULTIPLY", b.ss(above, -0.04, 0.06),
                b.m("EXPONENT", b.m("MULTIPLY", b.m("MAXIMUM", above, 0.0), -1.0 / 0.22)))
    red = b.m("MULTIPLY", b.ss(alt, 0.50, 0.82), b.ss(alt, 1.08, 0.92))
    purple = gauss(b.m("ADD", above, 0.05), 0.07)
    night = b.m("MULTIPLY", b.ss(i["NightDot"], 0.12, -0.18),
                b.m("MULTIPLY_ADD", b.ss(i["NightDot"], 0.0, -0.6), 0.8, 0.2))
    # красный — верхушки штор (и чуть диффузной полосы); слабый, иначе в проекции зелёный+красный = бурый
    Ir = b.m("MULTIPLY", b.m("ADD", b.m("MULTIPLY", arcs, 0.7), b.m("MULTIPLY", a3, 0.8)), patch)
    b.put(go.inputs["Green"], b.m("MULTIPLY", b.m("MULTIPLY", I, green), night))
    b.put(go.inputs["Red"], b.m("MULTIPLY", b.m("MULTIPLY", Ir, red), b.m("MULTIPLY", night, 0.20)))
    b.put(go.inputs["Purple"], b.m("MULTIPLY", b.m("MULTIPLY", I, purple), b.m("MULTIPLY", night, 0.35)))
    return g


def _mat_aurora_shell(name, grp, R, r_k, r_lo, density, sunref):
    """Оболочка радиуса r_k (в R) — верхняя граница слоя r_lo..r_k. Один отсчёт «ray march» на слой:
    берём отрезок луча внутри слоя (до нижней границы или до точки касания, если луч не дошёл),
    узор — в его середине M, яркость ∝ длине отрезка. Слои стыкуются без зазоров и у лимба,
    и при взгляде вдоль овала (без «стопки» копий дуги)."""
    mat, nodes, links, out = C.new_material(name)
    b = _NB(mat.node_tree)
    tc = b.node("ShaderNodeTexCoord")
    geo = b.node("ShaderNodeNewGeometry")
    Ls, _E = _sun_nodes(b, sunref, power_name="unused")
    nd = b.v("DOT_PRODUCT", b.v("NORMALIZE", geo.outputs["Normal"]), Ls)
    P = b.v("SCALE", tc.outputs["Object"], scale=1.0 / R)  # в единицах R, система магнитной оси
    Io = b.node("ShaderNodeVectorTransform", {0: geo.outputs["Incoming"]}, vector_type="VECTOR",
                convert_from="WORLD", convert_to="OBJECT").outputs[0]
    D = b.v("SCALE", b.v("NORMALIZE", Io), scale=-1.0)  # направление луча
    ts = b.m("MULTIPLY", b.v("DOT_PRODUCT", P, D), -1.0)  # до точки касания (>0 — луч ещё снижается)
    b2 = b.m("SUBTRACT", b.v("DOT_PRODUCT", P, P), b.m("MULTIPLY", ts, ts))
    disc2 = b.m("SUBTRACT", r_lo * r_lo, b2)
    disc = b.m("SQRT", b.m("MAXIMUM", disc2, 0.0))
    Lseg = b.m("MAXIMUM", b.m("SUBTRACT", b.m("ABSOLUTE", ts), disc), 0.0)
    half = b.m("MULTIPLY", b.m("MULTIPLY", Lseg, 0.5), b.m("SIGN", ts))
    M = b.v("ADD", P, b.v("SCALE", D, scale=half))
    rM = b.v("LENGTH", M)
    alt = b.m("DIVIDE", b.m("SUBTRACT", rM, AUR_R0), AUR_R1 - AUR_R0)
    # ход отрезка вдоль меридиана (рад) → размытие дуг по широте внутри слоя
    n = b.v("NORMALIZE", M)
    nz = b.sep(n)[2]
    eth = b.v("SUBTRACT", b.v("SCALE", n, scale=nz), (0.0, 0.0, 1.0))  # ∝ e_θ (знак не важен)
    sth = b.m("MAXIMUM", b.m("SQRT", b.m("MAXIMUM", b.m("MULTIPLY_ADD", nz, b.m("MULTIPLY", nz, -1.0), 1.0), 0.0)), 0.05)
    smear = b.m("MINIMUM", b.m("MULTIPLY", b.m("ABSOLUTE", b.m("DIVIDE", b.v("DOT_PRODUCT", D, eth), sth)), Lseg), 0.03)
    g = b.node("ShaderNodeGroup")
    g.node_tree = grp
    b.put(g.inputs["Vector"], M)
    b.put(g.inputs["Alt"], alt)
    b.put(g.inputs["NightDot"], nd)
    b.put(g.inputs["Smear"], smear)
    colr = b.v("SCALE", AUR_GREEN, scale=g.outputs["Green"])
    colr = b.v("ADD", colr, b.v("SCALE", AUR_RED, scale=g.outputs["Red"]))
    colr = b.v("ADD", colr, b.v("SCALE", AUR_PURPLE, scale=g.outputs["Purple"]))
    k = b.m("MULTIPLY", Lseg, density)
    em = b.node("ShaderNodeEmission", {"Color": colr, "Strength": k})
    tr = b.node("ShaderNodeBsdfTransparent", {"Color": (1, 1, 1, 1)})
    add = b.node("ShaderNodeAddShader", {0: em.outputs[0], 1: tr.outputs[0]})
    b.put(out.inputs["Surface"], add.outputs[0])
    return mat


# --------------------------------------------------------------------------- геометрия/анимация

def _sphere_mesh(name, r, u, v, cap=None):
    """UV-сфера; cap=(c_in, c_out) — оставить только кольцо-шапку c_in..c_out (косинусы) у обоих полюсов."""
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=u, v_segments=v, radius=r)
    if cap is not None:
        c_in, c_out = cap
        bad = [vt for vt in bm.verts if not (c_out * r <= abs(vt.co.z) <= c_in * r)]
        bmesh.ops.delete(bm, geom=bad, context="VERTS")
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    return me


def _ghost(ob):
    """Оболочки видны только камере (и прозрачным путям), не дают тени и вторичного света."""
    ob.visible_shadow = False
    ob.visible_diffuse = False
    ob.visible_glossy = False
    ob.visible_transmission = False
    ob.visible_volume_scatter = False


def _fcurves(id_data):
    ad = id_data.animation_data
    if ad is None or ad.action is None:
        return []
    act = ad.action
    if hasattr(act, "fcurves"):
        return list(act.fcurves)
    out = []
    for layer in act.layers:
        for strip in layer.strips:
            for cb in strip.channelbags:
                out.extend(cb.fcurves)
    return out


def _linearize(id_data, extrapolate=True):
    for fc in _fcurves(id_data):
        if extrapolate:
            fc.extrapolation = "LINEAR"
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"


def _key_rot_z(ob, z0, deg_per_s, frame_start, frame_end):
    """Равномерное вращение вокруг локальной Z ключами LINEAR (+линейная экстраполяция)."""
    fps = C.scene_fps()
    ob.rotation_euler[2] = z0
    ob.keyframe_insert("rotation_euler", index=2, frame=frame_start)
    ob.rotation_euler[2] = z0 + math.radians(deg_per_s * (frame_end - frame_start) / fps)
    ob.keyframe_insert("rotation_euler", index=2, frame=frame_end)
    _linearize(ob)


def _find_light(scene):
    for ob in scene.objects:
        if ob.type == "LIGHT" and ob.data.type == "POINT":
            return ob
    return None


# --------------------------------------------------------------------------- API

# высоты оболочек сияний (доли толщины слоя r0..r1) — границы слоёв
_AUR_ALTS = {0: (0.0, 0.12, 0.28, 0.48, 0.72, 1.0), 1: (0.0, 0.4, 1.0)}
AUR_R0, AUR_R1 = 1.010, 1.055
# прозрачных пересечений на луч у лимба: 2 (атмосфера) + 2×6 (сияния) = 14; + лучи/кольцо в шотах
TRANSPARENT_BOUNCES = 24


def build_planet(scene, kind, *, radius=1.0, location=(0, 0, 0), parent=None, detail="close", seed=0,
                 axial_tilt_deg=None, rot_period_s=None, frame_start=1, frame_end=300, aurora_strength=1.0,
                 light=None, name=None, tilt_azimuth_deg=0.0, mag_offset_deg=10.0):
    """Планета kind ∈ KINDS: draugr, poltergeist, phobetor (PSR B1257+12, с атмосферой/сияниями у двух последних);
    ember, scorched, rust, frostrock, grooved, dirtyice — безатмосферные миры (базальт, Меркурий, ржавая пустыня,
    иней в холодных зонах по направлению на звезду, бороздчатый и грязный лёд).

    detail: "close" (планета ≥ ~25 % высоты кадра), "mid" (< 25 %: без мелких кратеров/шумов, 3 оболочки
    сияний), "far" (точка/диск: крупные детали, без сияний, сетка 64×32).
    Иерархия: root (наклон оси, ставится на орбиту) → planet (меш, суточное вращение ключами)
    → aurora (пустышка, магнитная ось смещена на mag_offset_deg) → оболочки сияний; atmosphere — ребёнок root.
    light — точечная лампа пульсара (по умолчанию первая точечная в сцене): к ней привязан SunRef,
    мощность и цвет для атмосферы берутся из light.data (смена — set_sun / key_sun_power).
    Поднимает scene.cycles.transparent_max_bounces до TRANSPARENT_BOUNCES (если меньше).
    Возвращает dict(root, planet, atmosphere, aurora, aurora_shells, sunref, materials, kind, radius).
    """
    if kind not in KINDS:
        raise ValueError(f"unknown planet kind {kind!r}")
    if detail not in ("close", "mid", "far"):
        raise ValueError(f"unknown detail {detail!r}")
    cfg = KINDS[kind]
    name = name or kind.capitalize()
    base_name, k = name, 1
    while bpy.data.objects.get(f"PL_{name}") is not None:  # вторая планета того же вида — свои материалы
        k += 1
        name = f"{base_name}{k}"
    tilt = cfg["tilt"] if axial_tilt_deg is None else axial_tilt_deg
    rot = cfg["rot"] if rot_period_s is None else rot_period_s
    lod = {"close": 0, "mid": 1, "far": 2}[detail]
    R = float(radius)

    root = C.empty(f"PL_{name}", coll=COLL, parent=parent, loc=location, size=R * 1.5)
    root.rotation_mode = "XYZ"
    root.rotation_euler = (math.radians(tilt), 0.0, math.radians(tilt_azimuth_deg))
    root["pl_kind"] = kind

    # пустышка-направление на пульсар (без вращения → TexCoord/Object = P - P_sun в мире)
    sunref = C.empty(f"PL_{name}_SunRef", coll=COLL, size=R * 0.5)
    light = light or _find_light(scene)
    sun_col = (1.0, 1.0, 1.0)
    if light is not None:
        con = sunref.constraints.new("COPY_LOCATION")
        con.target = light
        power = K_POINT * light.data.energy
        sun_col = tuple(light.data.color)
    else:
        sunref.location = Vector(location) + Vector((1.0, 0.0, 0.0)) * 150.0 * R
        power = 4.0 * (150.0 * R) ** 2

    u, v = ((256, 128), (128, 64), (64, 32))[lod]
    me = _sphere_mesh(f"PL_{name}_mesh", R, u, v)
    planet = bpy.data.objects.new(f"PL_{name}_Body", me)
    C.link(planet, COLL)
    planet.parent = root
    planet["pl_root_name"] = root.name
    mat = SURFACE[kind](f"PL_{name}_Surface", seed, R, lod)
    sc_node = mat.node_tree.nodes.get("SunCoord")        # материалы, зависящие от направления на звезду (иней)
    if sc_node is not None:
        sc_node.object = sunref
    me.materials.append(mat)
    _key_rot_z(planet, math.radians(seed * 37.0 % 360.0), 360.0 / rot, frame_start, frame_end)
    mats = {"surface": mat}

    atmo = None
    if cfg["atmo"]:
        a = cfg["atmo"]
        Rs = R * (1.0 + 7.5 * a["H"])
        au, av = ((192, 96), (128, 64), (64, 32))[lod]
        atmo = bpy.data.objects.new(f"PL_{name}_Atmo", _sphere_mesh(f"PL_{name}_atmo", Rs, au, av))
        C.link(atmo, COLL)
        atmo.parent = root
        _ghost(atmo)
        am = _mat_atmosphere(f"PL_{name}_Atmosphere", R, a, sunref, power, sun_col)
        atmo.data.materials.append(am)
        mats["atmosphere"] = am

    aur = None
    shells = []
    if cfg["aurora"] and lod < 2 and aurora_strength > 0:
        aur = C.empty(f"PL_{name}_AuroraAxis", coll=COLL, parent=planet, size=R * 1.3)
        aur.rotation_euler = (math.radians(mag_offset_deg), 0.0, math.radians(40.0 + seed * 53.0 % 360.0))
        grp = _aurora_group(f"PL_{name}_AuroraPattern", frame_start, frame_end,
                            seed=seed + 17 * list(KINDS).index(kind))
        alts = _AUR_ALTS[lod]
        # плотность эмиссии на единицу длины луча (в R): прежняя яркость 0.3/слой при толщине слоя ~0.0075 R
        dens = 0.30 * aurora_strength / ((AUR_R1 - AUR_R0) / 6.0)
        # кольцо-шапка 7°..36° от магнитного полюса (овал ~18°±8°) — меньше лишних пересечений
        cap = (math.cos(math.radians(7.0)), math.cos(math.radians(36.0)))
        su, sv = ((180, 90), (128, 64))[lod]
        for k, al in enumerate(alts):
            r_k = AUR_R0 + (AUR_R1 - AUR_R0) * al
            r_lo = AUR_R0 + (AUR_R1 - AUR_R0) * alts[k - 1] if k > 0 else AUR_R0 - 0.004
            rr = R * r_k
            sh = bpy.data.objects.new(f"PL_{name}_Aurora{k}",
                                      _sphere_mesh(f"PL_{name}_aur{k}", rr, su, sv, cap=cap))
            C.link(sh, COLL)
            sh.parent = aur
            _ghost(sh)
            m = _mat_aurora_shell(f"PL_{name}_AuroraMat{k}", grp, R, r_k, r_lo, dens, sunref)
            sh.data.materials.append(m)
            shells.append(sh)
        mats["aurora_pattern"] = grp
    if atmo is not None or shells:
        cy = scene.cycles
        cy.transparent_max_bounces = max(cy.transparent_max_bounces, TRANSPARENT_BOUNCES)
    return dict(root=root, planet=planet, atmosphere=atmo, aurora=aur, aurora_shells=shells,
                sunref=sunref, materials=mats, kind=kind, radius=R)


def add_big_crater(objs, direction, *, radius_km, rim_km, floor_km, peak_km=0.0, unit_km=1.0, flat=0.42,
                   peak_r=0.12, segments=(768, 384)):
    """Крупный ударный кратер геометрией (Гершель на Мимасе, Одиссей на Тефии, Стикни на Фобосе): меш тела
    пересобирается плотнее (segments), вершины смещаются по профилю: плоское днище (−floor_km) с центральной горкой
    (peak_km над днищем, радиус peak_r·R_кр), стенка до вала (+rim_km на краю), валы и выбросы гаснут за краем.
    direction — центр кратера из центра тела (в мире), размеры — км, unit_km — км в 1 ед. сцены. Кратеры материала
    (bump) остаются поверх. Вызывать после build_planet; кадр — текущий (поворот тела берётся из matrix_world)."""
    planet = objs["planet"]
    R = objs["radius"]
    bpy.context.view_layer.update()
    c = (planet.matrix_world.to_3x3().inverted() @ Vector(direction)).normalized()
    rc = radius_km / unit_km / R                         # угловой радиус кратера (рад)
    k = 1.0 / unit_km
    me = _sphere_mesh(planet.data.name + "_crater", R, *segments)
    for vt in me.vertices:
        n = vt.co.normalized()
        x = math.acos(max(-1.0, min(1.0, n.dot(c)))) / rc
        if x < flat:
            h = -floor_km + peak_km * math.exp(-(x / peak_r) ** 2)
        elif x < 1.0:
            t = (x - flat) / (1.0 - flat)
            h = -floor_km + (rim_km + floor_km) * t ** 1.7
        else:
            h = rim_km * math.exp(-((x - 1.0) / 0.32) ** 2)
        vt.co = n * (R + h * k)
    me.update()
    for m in planet.data.materials:
        me.materials.append(m)
    old = planet.data
    planet.data = me
    if old.users == 0:
        bpy.data.meshes.remove(old)
    return me


def _atmo_nodes(objs):
    m = objs["materials"].get("atmosphere")
    if m is None:
        return None, None
    nn = m.node_tree.nodes
    return nn["sun_power"], nn["sun_color"]


def set_sun(objs, light=None, energy=None, color=None):
    """Перепривязать направление/мощность/цвет пульсара (после смены лампы, её энергии или цвета).
    Без аргументов — перечитать energy/color у текущей цели SunRef."""
    sr = objs["sunref"]
    if light is not None:
        for c in list(sr.constraints):
            sr.constraints.remove(c)
        con = sr.constraints.new("COPY_LOCATION")
        con.target = light
    else:
        tg = [c.target for c in sr.constraints if c.type == "COPY_LOCATION" and c.target is not None]
        light = tg[0] if tg else None
    if light is not None and light.type == "LIGHT":
        energy = light.data.energy if energy is None else energy
        color = tuple(light.data.color) if color is None else color
    pw, sc = _atmo_nodes(objs)
    if pw is not None:
        if energy is not None:
            pw.outputs[0].default_value = K_POINT * energy
        if color is not None:
            sc.outputs[0].default_value = (*tuple(color)[:3], 1.0)


def set_sun_dir(objs, direction, irradiance=4.0, distance=1.0e4):
    """Без лампы: задать направление на пульсар вектором sun_dir (статично) и освещённость (пиксель белого)."""
    sr = objs["sunref"]
    for c in list(sr.constraints):
        sr.constraints.remove(c)
    p = objs["root"].matrix_world.translation
    sr.location = p + Vector(direction).normalized() * distance
    pw, _sc = _atmo_nodes(objs)
    if pw is not None:
        pw.outputs[0].default_value = irradiance * distance ** 2


def key_sun_power(objs, psr, frame_start, frame_end, substeps=2, scene=None):
    """Ключи sun_power/sun_color атмосферы по кадрам: E = точечный свет + Σ прожекторы·f(угол).
    psr — dict из NS.build_pulsar (нужны 'light' и 'spots') или список ламп-объектов.
    Учитывает ключи энергии лампы (вспышки) и проход лучей-прожекторов по планете. Только ключи (без драйверов),
    substeps — ключей на кадр (для motion blur при быстром проходе луча). Вызывать ПОСЛЕ add_orbit и
    после любых изменений энергии ламп. Возвращает список (кадр, E) для проверки."""
    pw, sc = _atmo_nodes(objs)
    scene = scene or bpy.context.scene
    lamps = list(psr) if isinstance(psr, (list, tuple)) else [psr["light"]] + list(psr.get("spots") or [])
    point = [o for o in lamps if o.data.type == "POINT"]
    spots = [o for o in lamps if o.data.type == "SPOT"]
    ref = point[0] if point else None
    if ref is not None:
        set_sun(objs, light=ref)
    log = []
    if pw is None:
        return log
    for fc in _fcurves(pw.id_data):  # сбросить старые ключи
        if fc.data_path.startswith(('nodes["sun_power"]', 'nodes["sun_color"]')):
            fc.keyframe_points.clear()
    f_cur = scene.frame_current
    n = int(round((frame_end - frame_start) * substeps))
    for s in range(n + 1):
        fr = frame_start + s / substeps
        scene.frame_set(int(math.floor(fr)), subframe=fr - math.floor(fr))
        tgt = objs["root"].matrix_world.translation.copy()
        dl = (tgt - ref.matrix_world.translation).length if ref else 1.0
        e_sum = 0.0
        rgb = [0.0, 0.0, 0.0]
        for o in point:
            e = o.data.energy * (dl / max((tgt - o.matrix_world.translation).length, 1e-6)) ** 2
            e_sum += e
            for c in range(3):
                rgb[c] += e * o.data.color[c]
        for o in spots:
            f, ds = _spot_factor(o, tgt)
            e = o.data.energy * f * (dl / max(ds, 1e-6)) ** 2
            e_sum += e
            for c in range(3):
                rgb[c] += e * o.data.color[c]
        col = tuple(x / e_sum for x in rgb) if e_sum > 0 else (1.0, 1.0, 1.0)
        pw.outputs[0].default_value = K_POINT * e_sum
        pw.outputs[0].keyframe_insert("default_value", frame=fr)
        sc.outputs[0].default_value = (*col, 1.0)
        sc.outputs[0].keyframe_insert("default_value", frame=fr)
        log.append((fr, e_sum))
    _linearize(pw.id_data, extrapolate=False)
    scene.frame_set(f_cur)
    return log
