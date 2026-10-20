"""Видимая звезда: фотосфера (грануляция, потемнение к краю, цвет чёрного тела), ореол, вспышка выхода ударной волны.

    from spacekit.bodies import star as ST
    st = ST.build_star("Sk69", radius=1.0, temp_k=16000, location=(0, 0, 0), seed=3)
    ST.key_value(st, "flow", [(1, 0.0), (n, 0.5)], ipo="LINEAR")      # «кипение» грануляции (W шума)
    ST.key_value(st, "flash", [(30, 0.0), (36, 25.0), (90, 6.0)])      # выход ударной волны на поверхность
    ST.key_value(st, "front", [(30, 0.0), (42, 1.0)])                  # фронт вспышки бежит от breakout_dir по диску

Фотосфера — эмиссионная поверхность (светится сама, сцену не освещает; свет на сцену — опц. лампа `light=`).
Меш — сфера радиуса 1, объект масштабирован на radius: координаты шума в долях радиуса (зерно не зависит от
единиц сцены). Яркость I(μ) = 1 − u·(1 − μ) (линейный закон потемнения к краю, μ = cos угла к лучу зрения; у
горячих звёзд u ≈ 0.3–0.4, у Солнца ≈ 0.6), цвет края — чуть холоднее (T·limb_cool). Грануляция — Вороной 4D
(тёмные межгранульные промежутки по расстоянию до края ячейки) + крупная «супергрануляция» и мелкая рябь; W шума —
ключами (`flow`). Структура поверхности голубого сверхгиганта не наблюдается — грануляция условна (в описание).
Вспышка: маска по углу от breakout_dir, граница cos θ = 1 − 2·front (front 0 → точка, 1 → весь диск) — выход
ударной волны начинается с одной стороны и обегает звезду; цвет вспышки — горячий бело-фиолетовый (УФ).
`photosphere_material` — тот же шейдер для «кожи» разреза звезды (bodies.star_layers).
"""
import bmesh
import bpy
from mathutils import Vector

from .. import anim
from .. import core as C
from ..lighting import blackbody_rgb
from .planets import _NB, _ghost, _seed_off

FLASH_RGB = (0.80, 0.86, 1.0)


def _norm_rgb(rgb, sat=1.0):
    """Цвет к max=1; sat > 1 — насыщеннее (кинематографичный оттенок вокруг чёрного тела)."""
    m = max(rgb) or 1.0
    c = [x / m for x in rgb]
    g = sum(c) / 3.0
    c = [max(0.0, g + (x - g) * sat) for x in c]
    m = max(c) or 1.0
    return tuple(x / m for x in c)


def photosphere_material(name, temp_k=5772.0, strength=6.0, seed=1, gran_scale=26.0, contrast=0.35, limb_u=0.45,
                         limb_cool=0.8, sat=1.25, lod=0, breakout_dir=(1.0, 0.0, 0.0), unit=1.0, hot_rgb=None,
                         cool_rgb=None):
    """Шейдер фотосферы (эмиссия). Значения для ключей — узлы Value: strength, flow, flash, front.
    lod 0 — грануляция, 1 — без мелкой ряби, 2 — только потемнение к краю и крупные пятна (далёкий план).
    unit — радиус звезды в координатах объекта (меш не единичный — например, разрез bodies.star_layers).
    hot_rgb/cool_rgb — свои цвета ячеек и промежутков/края (иначе — чёрное тело T и T·limb_cool)."""
    mat, N, L, out = C.new_material(name)
    b = _NB(mat.node_tree)
    tc = b.node("ShaderNodeTexCoord")
    off = _seed_off(seed)
    p = b.v("ADD", b.v("SCALE", tc.outputs["Object"], scale=1.0 / unit), off)
    flow = b.node("ShaderNodeValue", name="flow", label="flow")
    flow.outputs[0].default_value = seed * 0.37
    fw = flow.outputs[0]
    # крупные пятна/супергрануляция
    sup = b.noise(p, 2.4, detail=3.0, rough=0.55, w=b.m("MULTIPLY", fw, 0.25)).outputs["Fac"]
    tex = b.m("ADD", 1.0, b.m("MULTIPLY", b.m("SUBTRACT", sup, 0.5), 0.45))
    g = None
    if lod < 2:
        # грануляция: координаты слегка искажены шумом — ячейки неправильной формы
        dist = b.noise(p, 4.0, detail=2.0, w=b.m("MULTIPLY", fw, 0.5)).outputs["Color"]
        pd = b.v("ADD", p, b.v("SCALE", b.v("SUBTRACT", dist, (0.5, 0.5, 0.5)), scale=0.22))
        edge = b.node("ShaderNodeTexVoronoi", {"Vector": pd, "Scale": gran_scale, "W": fw, "Randomness": 1.0},
                      voronoi_dimensions="4D", feature="DISTANCE_TO_EDGE")
        f1 = b.node("ShaderNodeTexVoronoi", {"Vector": pd, "Scale": gran_scale, "W": fw, "Randomness": 1.0},
                    voronoi_dimensions="4D", feature="F1")
        lanes = b.ss(edge.outputs["Distance"], 0.0, 0.22)                 # мягкие промежутки (не «плитка»)
        core = b.m("SUBTRACT", 1.0, b.m("MULTIPLY", b.ss(f1.outputs["Distance"], 0.1, 0.8), 0.35))
        g = b.m("MULTIPLY", b.m("ADD", 0.35, b.m("MULTIPLY", lanes, 0.65)), core)
        # плазма: турбулентные жилы среднего масштаба (видны и на общем плане) + яркие факелы
        fac = b.noise(pd, 5.5, detail=6.0, rough=0.65, dist=1.2, w=b.m("MULTIPLY", fw, 0.7)).outputs["Fac"]
        g = b.m("ADD", b.m("MULTIPLY", g, b.m("ADD", 0.55, b.m("MULTIPLY", fac, 0.9))),
                b.m("MULTIPLY", b.ss(fac, 0.6, 0.82), 0.45))
        tex = b.m("MULTIPLY", tex, b.m("ADD", 1.0 - contrast, b.m("MULTIPLY", g, contrast)))
        if lod < 1:
            fine = b.noise(p, gran_scale * 3.1, detail=2.0, w=b.m("MULTIPLY", fw, 1.7)).outputs["Fac"]
            tex = b.m("MULTIPLY", tex, b.m("ADD", 1.0, b.m("MULTIPLY", b.m("SUBTRACT", fine, 0.5), 0.16)))
    # потемнение к краю
    lw = b.node("ShaderNodeLayerWeight", {"Blend": 0.5})
    mu = b.m("SUBTRACT", 1.0, lw.outputs["Facing"], clamp=True)
    limb = b.m("SUBTRACT", 1.0, b.m("MULTIPLY", b.m("SUBTRACT", 1.0, mu), limb_u))
    hot = hot_rgb or _norm_rgb(blackbody_rgb(temp_k), sat)
    cool = cool_rgb or _norm_rgb(blackbody_rgb(temp_k * limb_cool), sat * 1.1)
    cf = b.m("MULTIPLY", g if g is not None else 0.8, b.m("ADD", 0.45, b.m("MULTIPLY", mu, 0.55)))
    col = b.mix(cf, cool, hot)
    k = b.node("ShaderNodeValue", name="strength", label="strength")
    k.outputs[0].default_value = strength
    em_s = b.m("MULTIPLY", b.m("MULTIPLY", tex, limb), k.outputs[0])
    # вспышка выхода ударной волны
    nd = b.v("NORMALIZE", tc.outputs["Object"])
    cosang = b.v("DOT_PRODUCT", nd, tuple(Vector(breakout_dir).normalized()))
    front = b.node("ShaderNodeValue", name="front", label="front")
    front.outputs[0].default_value = 0.0
    edge_c = b.m("SUBTRACT", 1.0, b.m("MULTIPLY", front.outputs[0], 2.0))
    mask = b.node("ShaderNodeMapRange", {0: cosang, 1: b.m("SUBTRACT", edge_c, 0.18), 2: b.m("ADD", edge_c, 0.04),
                                         3: 0.0, 4: 1.0}, interpolation_type="SMOOTHSTEP", clamp=True).outputs[0]
    fl = b.node("ShaderNodeValue", name="flash", label="flash")
    fl.outputs[0].default_value = 0.0
    ftex = b.noise(p, 7.0, detail=4.0, rough=0.6, w=b.m("MULTIPLY", fw, 3.0)).outputs["Fac"]
    fem = b.m("MULTIPLY", b.m("MULTIPLY", fl.outputs[0], mask), b.m("ADD", 0.4, b.m("MULTIPLY", ftex, 1.2)))
    tot = b.m("ADD", em_s, fem)
    col = b.mix(b.m("DIVIDE", fem, b.m("ADD", tot, 1e-3), clamp=True), col, FLASH_RGB)
    em = b.node("ShaderNodeEmission", {"Color": col, "Strength": tot})
    L.new(em.outputs[0], out.inputs["Surface"])
    mat.cycles.emission_sampling = "NONE"
    return mat


def _sphere(name, u, v):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=u, v_segments=v, radius=1.0)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    return me


def _glow_material(name, color, strength, size):
    """Ореол-спрайт: диск ⟂ камере, яркость exp(−(ρ − 1)/w) снаружи звезды (ρ в радиусах звезды), внутри — 0."""
    mat, N, L, out = C.new_material(name)
    b = _NB(mat.node_tree)
    tc = b.node("ShaderNodeTexCoord")
    rho = b.v("LENGTH", tc.outputs["Object"])
    k = b.node("ShaderNodeValue", name="strength", label="strength")
    k.outputs[0].default_value = strength
    out_ = b.m("GREATER_THAN", rho, 0.995)
    g1 = b.m("EXPONENT", b.m("DIVIDE", b.m("SUBTRACT", rho, 1.0), -0.06))            # тонкий яркий край
    g2 = b.m("EXPONENT", b.m("DIVIDE", b.m("SUBTRACT", rho, 1.0), -size))            # широкое сияние
    br = b.m("MULTIPLY", b.m("MULTIPLY", b.m("ADD", b.m("MULTIPLY", g1, 0.6), g2), out_), k.outputs[0])
    em = b.node("ShaderNodeEmission", {"Color": (*color, 1.0), "Strength": br})
    tr = b.node("ShaderNodeBsdfTransparent")
    ad = b.node("ShaderNodeAddShader", {0: em.outputs[0], 1: tr.outputs[0]})
    L.new(ad.outputs[0], out.inputs["Surface"])
    mat.cycles.emission_sampling = "NONE"
    return mat


def build_star(name, radius=1.0, temp_k=5772.0, location=(0, 0, 0), parent=None, seed=1, strength=6.0,
               gran_scale=26.0, contrast=0.35, limb_u=0.45, sat=1.25, detail="close", breakout_dir=(1, 0, 0),
               halo=0.6, halo_scale=1.07, light=None, glow=None, cam=None, hot_rgb=None, cool_rgb=None, coll="Star"):
    """Звезда: фотосфера + ореол (fx.shell, яркий край) + опц. точечная лампа (light=(энергия, Вт) — светит на
    сцену, в кадре не видна). detail: close (грануляция), mid (без ряби), far (только потемнение к краю).
    glow=(яркость, ширина в R) + cam — ореол-спрайт ⟂ камере (мягкое сияние без «стеклянной» оболочки).
    Возвращает dict(root, disk, halo, glow, light, mat, radius, temp_k)."""
    from ..fx import shell as SH
    lod = {"close": 0, "mid": 1, "far": 2}[detail]
    root = C.empty(name, coll=coll, parent=parent, loc=location)
    u = {0: 192, 1: 128, 2: 64}[lod]
    me = _sphere(f"{name}_Disk", u, u // 2)
    mat = photosphere_material(f"{name}_Photo", temp_k, strength, seed, gran_scale, contrast, limb_u, sat=sat,
                               lod=lod, breakout_dir=breakout_dir, hot_rgb=hot_rgb, cool_rgb=cool_rgb)
    me.materials.append(mat)
    disk = bpy.data.objects.new(f"{name}_Disk", me)
    C.link(disk, coll)
    disk.parent = root
    disk.scale = (radius,) * 3
    _ghost(disk)
    hl = None
    if halo > 0:
        col = _norm_rgb(blackbody_rgb(temp_k), sat * 1.2)
        # мягкий ореол: широкая оболочка, яркость растёт к краю плавно (без жёсткого контура у лимба)
        hl = SH.build_shell(f"{name}_Halo", radius=radius * halo_scale, color=col, color_edge=col, strength=halo,
                            rim_power=1.6, face_floor=0.0, noise_scale=3.0, noise_amp=0.35, seed=seed, segments=96,
                            parent=root, coll=coll)
    gl = None
    if glow and cam is not None:
        import bmesh as _bm
        bm = _bm.new()
        _bm.ops.create_circle(bm, cap_ends=True, cap_tris=False, segments=96, radius=1.0 + 6.0 * glow[1])
        gme = bpy.data.meshes.new(f"{name}_Glow")
        bm.to_mesh(gme)
        bm.free()
        gme.materials.append(_glow_material(f"{name}_GlowMat", _norm_rgb(blackbody_rgb(temp_k), sat * 1.3),
                                            glow[0], glow[1]))
        gl = bpy.data.objects.new(f"{name}_Glow", gme)
        C.link(gl, coll)
        gl.parent = root
        gl.scale = (radius,) * 3
        con = gl.constraints.new("COPY_ROTATION")
        con.target = cam
        _ghost(gl)
    lamp = None
    if light:
        from .. import lighting as LT
        lamp = LT.add_point_star(f"{name}_Light", float(light), temp_k=temp_k, radius=radius, parent=root)
        lamp.visible_camera = False
    return dict(root=root, disk=disk, halo=hl, glow=gl, light=lamp, mat=mat, radius=radius, temp_k=temp_k)


def key_value(st, name, pairs, ipo="BEZIER", mat=None):
    """Ключи узла Value name (strength, flow, flash, front) в материале фотосферы: pairs [(кадр, значение)]."""
    m = mat or st["mat"]
    s = m.node_tree.nodes[name].outputs[0]
    for f, v in pairs:
        s.default_value = v
        s.keyframe_insert("default_value", frame=f)
    anim.set_interpolation(m.node_tree, ipo, path_contains=f'nodes["{name}"]')


def key_visible(ob, pairs):
    """Видимость объекта в рендере ключами: pairs [(кадр, True/False)] (CONSTANT)."""
    for f, v in pairs:
        ob.hide_render = not v
        ob.keyframe_insert("hide_render", frame=f)
    anim.set_interpolation(ob, "CONSTANT", path_contains="hide_render")
