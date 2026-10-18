"""TRAPPIST-1: параметры реальной системы и их «экранный» масштаб — общие для всех шотов эпизода.

Реальность (числа и источники — facts.md; Agol et al. 2021, PSJ 2:1, табл. 2 и 5):
    звезда: R = 0.1192 R☉ (82 925 км), M = 0.0898 M☉, Teff = 2566 K, 40.7 св. года
    планета: P (сут), Rp/R★, a/R★ — ниже в PLANETS; a и Rp в км получаются умножением на R★.
Экран: 1 ед. = 1000 км (Мм) во всех шотах. Крупные планы (v1, v4) — реальные размеры и расстояния,
реальное время (планеты стоят). Схемы (v2, v3): орбиты в масштабе, звезда ×3, планеты — метки постоянного
экранного размера (не в масштабе); время ускорено: 1 сутки = 2 с ролика (×43 200), отношения периодов честные.
v5 — планеты в ряд для сравнения размеров (взаимный масштаб честный, расстановка условная).
Поверхности планет придуманы (готовые kind spacekit с оттенками эпизода): измерены только размеры, орбиты и свет.
spacekit не меняется (параллельная работа над ep002): звезда-диск, метки, контуры — хелперы этого файла.
"""
import math

import bmesh
import bpy
from mathutils import Vector

from spacekit import anim as A
from spacekit import core as C
from spacekit import lighting as LT
from spacekit.bodies import planets as PL
from spacekit.fx import label as LB

R_SUN_KM = 695700.0
AU_KM = 1.495978707e8
R_STAR = 0.1192 * R_SUN_KM / 1000.0          # Мм (82.93)
TEFF = 2566.0
STAR_RGB = LT.blackbody_rgb(TEFF)

# имя: (период, сут; Rp/R★; a/R★; kind spacekit; сид; оттенок поверхности (RGB-множитель))
# Поверхности — иллюстрация с опорой на данные: b тёмная (JWST: дневная сторона ~500 K при альбедо ≈ 0), c серый
# камень без плотной атмосферы, d — у внутреннего края зоны обитаемости, e — иней в холодных зонах, f–h — богатые
# водой (низкая плотность), чем дальше, тем холоднее и «грязнее» лёд.
PLANETS = {
    "b": (1.510826, 0.08590, 20.843, "ember", 31, (1.0, 1.0, 1.0)),
    "c": (2.421937, 0.08440, 28.549, "scorched", 17, (1.0, 1.0, 1.0)),
    "d": (4.049219, 0.06063, 40.216, "rust", 23, (1.0, 1.0, 1.0)),
    "e": (6.101013, 0.07079, 52.855, "frostrock", 41, (1.0, 1.0, 1.0)),
    "f": (9.207540, 0.08040, 69.543, "phobetor", 13, (0.85, 0.88, 0.95)),
    "g": (12.352446, 0.08692, 84.591, "grooved", 29, (1.0, 1.0, 1.0)),
    "h": (18.772866, 0.05809, 111.817, "dirtyice", 37, (1.0, 1.0, 1.0)),
}
WB_K = 3300.0                                 # баланс белого камеры (К): свет звезды тёплый, цвета поверхностей видны
NAMES = list(PLANETS)
A_MM = {n: p[2] * R_STAR for n, p in PLANETS.items()}       # большие полуоси, Мм (b 1728 … h 9272)
R_MM = {n: p[1] * R_STAR for n, p in PLANETS.items()}       # радиусы, Мм (h 4.82 … g 7.21)
P_D = {n: p[0] for n, p in PLANETS.items()}

DAY_S = 2.0                                   # схемы: 1 сутки = 2 с ролика (86400 / 2 = ×43 200)
SPEEDUP = 86400.0 / DAY_S
PERIOD_S = {n: P_D[n] * DAY_S for n in NAMES}

MERCURY_A_MM = 0.387098 * AU_KM / 1000.0      # 57 909 Мм = 6.25 орбиты h
JUPITER_R_MM = 71.492                          # экваториальный (NASA fact sheet)
EARTH_R_MM = 6.371
MOON_DEG = 0.518                              # средний угловой диаметр Луны с Земли
SUN_DEG = 0.533                               # Солнце с Земли

EARTH_DIR = Vector((0.0, -1.0, 0.0))          # направление на Землю в плоскости орбит (система видна с ребра)
EARTH_ANG = math.degrees(math.atan2(EARTH_DIR.y, EARTH_DIR.x)) % 360.0

# схемы v2→v3: фазы (град, в кадре 1 шота v2) подобраны случайным поиском под ровный ритм транзитов на 22 с
# схем: первый удар через 0.52 с после склейки, все 7 планет хоть раз, удары не ближе 0.37 с, паузы ≤ 2.2 с
MAP_PHASE = {"b": 95.0, "c": 10.0, "d": 350.0, "e": 280.0, "f": 160.0, "g": 195.0, "h": 265.0}


def planet_angle(name, t_s, phase=None):
    """Угол планеты (град) на круговой орбите через t_s секунд ролика от фазы phase (по умолчанию MAP_PHASE)."""
    ph = MAP_PHASE[name] if phase is None else phase
    return (ph + 360.0 * t_s / PERIOD_S[name]) % 360.0


def transits(t0, t1, phase=None):
    """Транзиты (планета проходит перед звездой для Земли) в окне [t0, t1) с ролика схемы: [(t, имя)]."""
    out = []
    for n in NAMES:
        ph = MAP_PHASE[n] if phase is None else phase[n]
        w = 360.0 / PERIOD_S[n]
        k0 = math.ceil((t0 * w + ph - EARTH_ANG) / 360.0)
        t = (EARTH_ANG + 360.0 * k0 - ph) / w
        while t < t1:
            if t >= t0:
                out.append((t, n))
            t += PERIOD_S[n]
    return sorted(out)


# ---------------------------------------------------------------- звезда (диск) и свет
def star_material(name, strength, seed=3, spots=0.55):
    """Красный карлик: чёрное тело 2566 K, сильное потемнение к краю (покраснение у лимба), мелкая зернистость,
    крупные тёмные пятна (вероятны у активной M-звезды; рисунок условный). Эмиссия, сцену не освещает."""
    mat, N, L, out = C.new_material(name)
    geo = N.new("ShaderNodeNewGeometry")
    dp = N.new("ShaderNodeVectorMath")
    dp.operation = "DOT_PRODUCT"
    L.new(geo.outputs["Normal"], dp.inputs[0])
    L.new(geo.outputs["Incoming"], dp.inputs[1])
    mu = C.math_node(N, L, "ABSOLUTE", dp.outputs["Value"])                     # μ = cos угла к лучу зрения
    om = C.math_node(N, L, "SUBTRACT", 1.0, mu)                                  # 1 − μ
    # квадратичный закон: I(μ) = 1 − u1(1−μ) − u2(1−μ)²  (u1 0.65, u2 0.28 — сильное потемнение M-карлика)
    limb = C.math_node(N, L, "SUBTRACT", C.math_node(N, L, "SUBTRACT", 1.0, C.math_node(N, L, "MULTIPLY", om, 0.65)),
                       C.math_node(N, L, "MULTIPLY", C.math_node(N, L, "MULTIPLY", om, om), 0.28))
    limb = C.math_node(N, L, "MAXIMUM", limb, 0.04)
    tc = N.new("ShaderNodeTexCoord")
    off = (seed * 1.37, seed * 2.11, seed * 0.73)

    def noise(scale, detail, rough, offset):
        vm = N.new("ShaderNodeVectorMath")
        vm.operation = "ADD"
        L.new(tc.outputs["Object"], vm.inputs[0])
        vm.inputs[1].default_value = offset
        nz = N.new("ShaderNodeTexNoise")
        nz.noise_dimensions = "3D"
        nz.inputs["Scale"].default_value = scale
        nz.inputs["Detail"].default_value = detail
        nz.inputs["Roughness"].default_value = rough
        L.new(vm.outputs[0], nz.inputs["Vector"])
        return nz.outputs["Fac"]

    gran = noise(60.0 / R_STAR, 8.0, 0.62, off)                                   # зерно ~1/60 радиуса
    gran = C.math_node(N, L, "ADD", C.math_node(N, L, "MULTIPLY", gran, 0.30), 0.70)   # 0.85..1.15 (Fac ~0.5±0.5)
    spot_n = noise(2.4 / R_STAR, 4.0, 0.55, (off[1], off[2], off[0]))
    sp = N.new("ShaderNodeMapRange")
    sp.interpolation_type = "SMOOTHSTEP"
    L.new(spot_n, sp.inputs["Value"])
    sp.inputs["From Min"].default_value = 0.66
    sp.inputs["From Max"].default_value = 0.74
    spot = C.math_node(N, L, "SUBTRACT", 1.0, C.math_node(N, L, "MULTIPLY", sp.outputs[0], spots))
    br = C.math_node(N, L, "MULTIPLY", C.math_node(N, L, "MULTIPLY", limb, gran), spot)
    # цвет: у лимба холоднее (красные слои выше) — смешать с чёрным телом 2150 K
    mix = N.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs[6].default_value = (*STAR_RGB, 1.0)
    mix.inputs[7].default_value = (*LT.blackbody_rgb(2150.0), 1.0)
    L.new(C.math_node(N, L, "POWER", om, 1.6), mix.inputs[0])
    em = N.new("ShaderNodeEmission")
    L.new(mix.outputs[2], em.inputs["Color"])
    k = N.new("ShaderNodeValue")
    k.name = k.label = "strength"
    k.outputs[0].default_value = strength
    L.new(C.math_node(N, L, "MULTIPLY", br, k.outputs[0]), em.inputs["Strength"])
    L.new(em.outputs[0], out.inputs["Surface"])
    mat.cycles.emission_sampling = "NONE"
    return mat


def _uv_sphere(name, radius, u=96, v=48):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=u, v_segments=v, radius=radius)
    for f in bm.faces:
        f.smooth = True
    bm.to_mesh(me)
    bm.free()
    return me


def build_star(sc, scale=1.0, strength=6.0, light_irr=5.0, irr_at=None, location=(0, 0, 0)):
    """Диск звезды (радиус R★·scale, только для камеры) + сферическая лампа радиуса R★ в центре.
    Мощность лампы: освещённость light_irr (пиксель белого диффуза, lighting.K_POINT) на расстоянии irr_at
    (по умолчанию — орбита b). Возвращает (диск, лампа)."""
    me = _uv_sphere("T1_Star", R_STAR * scale)
    me.materials.append(star_material("T1_StarMat", strength))
    disk = bpy.data.objects.new("T1_Star", me)
    C.link(disk, "Star")
    disk.location = location
    disk.visible_shadow = False
    disk.visible_diffuse = disk.visible_glossy = disk.visible_transmission = disk.visible_volume_scatter = False
    d = irr_at if irr_at is not None else A_MM["b"]
    lamp = LT.add_point_star("T1_Light", LT.point_energy_for(light_irr, d), temp_k=TEFF, radius=R_STAR,
                             location=location)
    lamp.visible_camera = False
    return disk, lamp


def key_star_strength(disk, pairs):
    s = disk.data.materials[0].node_tree.nodes["strength"].outputs[0]
    for f, v in pairs:
        s.default_value = v
        s.keyframe_insert("default_value", frame=f)
    A.set_interpolation(disk.data.materials[0].node_tree, "BEZIER")


# ---------------------------------------------------------------- планеты
def tint(mat, rgb):
    """Оттенок поверхности поверх готового материала kind: множитель на входе Base Color (только в этом эпизоде)."""
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    sock = bsdf.inputs["Base Color"]
    if not sock.is_linked:
        return
    src = sock.links[0].from_socket
    vm = nt.nodes.new("ShaderNodeVectorMath")
    vm.operation = "MULTIPLY"
    vm.inputs[1].default_value = rgb
    nt.links.new(src, vm.inputs[0])
    nt.links.new(vm.outputs[0], sock)


def build_planet(sc, name, n_frames, light, detail="close", location=(0, 0, 0), radius=None, spin_deg=0.0,
                 atmosphere=True):
    """Планета TRAPPIST-1 <name> (реальный радиус, Мм): kind/сид/оттенок из PLANETS, без сияний, без вращения
    (приливной захват: в реальном времени шота поворот незаметен), ось без наклона."""
    _p, _k, _a, kind, seed, rgb = PLANETS[name]
    p = PL.build_planet(sc, kind, radius=radius or R_MM[name], location=location, detail=detail, seed=seed,
                        axial_tilt_deg=0.0, rot_period_s=1.0e9, frame_start=1, frame_end=n_frames,
                        aurora_strength=0.0, light=light, name=f"T1{name}")
    p["planet"].animation_data_clear()                       # build_planet ставит ключи суточного вращения
    p["planet"].rotation_euler[2] = math.radians(spin_deg + seed * 37.0)
    tint(p["materials"]["surface"], rgb)
    if p["atmosphere"] is not None and not atmosphere:
        p["atmosphere"].hide_render = True
    return p


def pos(name, ang_deg, z=0.0):
    """Точка на круговой орбите планеты (Мм) под углом ang_deg (от +X против часовой, вид с +Z)."""
    a = A_MM[name]
    t = math.radians(ang_deg)
    return Vector((a * math.cos(t), a * math.sin(t), z))


# ---------------------------------------------------------------- схемы: метки, орбиты, контуры
def dot(name, color, strength, parent=None, loc=(0, 0, 0)):
    """Метка-точка (эмиссия, сцену не освещает); узел «k» — множитель яркости (вспышки транзитов)."""
    me = _uv_sphere(name, 1.0, 16, 8)
    mat, N, L, out = C.new_material(f"{name}_Mat")
    em = N.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1.0)
    k = N.new("ShaderNodeValue")
    k.name = k.label = "k"
    k.outputs[0].default_value = 1.0
    L.new(C.math_node(N, L, "MULTIPLY", k.outputs[0], strength), em.inputs["Strength"])
    L.new(em.outputs[0], out.inputs["Surface"])
    mat.cycles.emission_sampling = "NONE"
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    C.link(ob, "FX")
    ob.parent = parent
    ob.location = tuple(loc)
    ob.visible_shadow = False
    ob.visible_diffuse = ob.visible_glossy = ob.visible_transmission = ob.visible_volume_scatter = False
    return ob


def key_dot_px(ob, cam, px, f0, f1, step=3):
    """Постоянный экранный радиус метки (px итогового кадра) при движении камеры и тела."""
    sc = bpy.context.scene
    for f in list(range(f0, f1 + 1, step)) + [f1]:
        sc.frame_set(f)
        d = (cam.matrix_world.translation - ob.matrix_world.translation).length
        r = px * d * LB.pixel_angle(cam, sc)
        ob.scale = (r, r, r)
        ob.keyframe_insert("scale", frame=f)
    A.set_interpolation(ob, "LINEAR", path_contains="scale")
    sc.frame_set(f0)


def key_dot_flash(ob, frames, peak=5.0, rise=2, fall=24):
    """Вспышки метки в кадрах frames (транзит): быстрый подъём, плавный спад."""
    mat = ob.data.materials[0]
    s = mat.node_tree.nodes["k"].outputs[0]
    last = -10 ** 9
    for f in frames:
        if f - rise > last:
            s.default_value = 1.0
            s.keyframe_insert("default_value", frame=f - rise)
        s.default_value = peak
        s.keyframe_insert("default_value", frame=f)
        s.default_value = 1.0
        s.keyframe_insert("default_value", frame=f + fall)
        last = f + fall
    A.set_interpolation(mat.node_tree, "LINEAR")


def circle_points(radius, n=720, z=0.0):
    return [Vector((radius * math.cos(2 * math.pi * k / n), radius * math.sin(2 * math.pi * k / n), z))
            for k in range(n + 1)]


def ring_radius_for(cam_loc, center, ang_diam_deg):
    """Радиус контура, видимого из cam_loc под угловым диаметром ang_diam_deg на расстоянии до center."""
    d = (Vector(center) - Vector(cam_loc)).length
    return d * math.tan(math.radians(ang_diam_deg) * 0.5)
