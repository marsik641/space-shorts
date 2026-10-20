"""Звезда в разрезе: «луковица» слоёв (H, He, C, O, Ne, Si, Fe) с вырезанным октантом.

    from spacekit.bodies import star_layers as SL
    cut = SL.build_cutaway("Onion", [dict(name="Fe", r=2.0, color=…), dict(name="Si", r=4.5, …), …],
                           photo=dict(temp_k=16000, strength=5.0, seed=3))
    SL.key_values(cut, "shock", [(1, 0.0), (n, 30000.0)])    # фронт ударной волны (радиус, ед. сцены) во всех слоях
    SL.key_values(cut, "shock_amp", [(1, 0.0), (20, 1.0)])

Геометрия — в единицах сцены, без масштаба объекта (радиусы слоёв реальные: отношения до 10⁴, точность float
хватает). Вырезан октант x > 0, y > 0, z > 0: срезы — три четверти кольца на плоскостях x = 0, y = 0, z = 0,
камера смотрит в угол вдоль (1, 1, 1). Внешняя сфера — фотосфера (bodies.star.photosphere_material, без
октанта); полосы срезов — эмиссия цвета слоя с турбулентностью масштаба своего слоя (зерно видно на любом
увеличении), у основания каждого слоя — горячая линия (горение идёт в тонкой оболочке на границе с внутренним
слоем). Самый внутренний слой (железное ядро) — целая сфера, выступает в вырез. Цвета слоёв — условность
(коды элементов, в описание).
Ударная волна (shock, shock_amp, ед. сцены): яркая рваная полоса на |p| = shock, за ней — горячее перемешанное
вещество (цвет слоя смещается к белому, турбулентность сильнее). Узлы Value в каждом материале: flow, shock,
shock_amp, glow (общий множитель яркости полос) — `key_values` ставит ключи сразу во всех.
"""
import math

import bmesh
import bpy

from .. import anim
from .. import core as C
from .planets import _NB, _ghost, _seed_off
from .star import photosphere_material

HOT_RGB = (1.0, 0.93, 0.80)
CAP_VALUES = ("flow", "shock", "shock_amp", "glow")


def _value(b, name, v):
    n = b.node("ShaderNodeValue", name=name, label=name)
    n.outputs[0].default_value = v
    return n.outputs[0]


def _cap_material(name, r0, r1, color, strength, line, seed, tex_scale, neighbor):
    """Полоса среза слоя r0..r1: эмиссия + турбулентность (масштаб ∝ 1/r1) + горячая линия у r0 + ударная волна."""
    mat, N, L, out = C.new_material(name)
    b = _NB(mat.node_tree)
    tc = b.node("ShaderNodeTexCoord")
    p0 = tc.outputs["Object"]
    vals = {k: _value(b, k, v) for k, v in (("flow", seed * 0.31), ("shock", 0.0), ("shock_amp", 0.0),
                                             ("glow", 1.0))}
    fw = vals["flow"]
    rho = b.v("LENGTH", p0)
    # текстура в лог-полярных координатах: направление × log ρ — зерно ∝ радиусу на любом увеличении
    d = b.v("ADD", b.v("SCALE", b.v("NORMALIZE", p0), scale=tex_scale), _seed_off(seed))
    lr = b.m("MULTIPLY", b.m("LOGARITHM", b.m("MAXIMUM", rho, 1e-6), math.e), tex_scale * 0.55)
    t1 = b.noise(d, 1.0, detail=5.0, rough=0.62, dist=0.5, w=b.m("ADD", lr, fw)).outputs["Fac"]
    t2 = b.noise(d, 3.3, detail=3.0, rough=0.5, w=b.m("ADD", b.m("MULTIPLY", lr, 3.3),
                                                        b.m("MULTIPLY", fw, 1.6))).outputs["Fac"]
    tex = b.m("MULTIPLY", b.m("ADD", 0.45, b.m("MULTIPLY", t1, 1.05)), b.m("ADD", 0.8, b.m("MULTIPLY", t2, 0.4)))
    # к внешней границе темнее (полосы читаются), у основания — линия горения толщиной ~6 % r0
    band = b.m("MULTIPLY", tex, b.m("SUBTRACT", 1.0, b.m("MULTIPLY", b.ss(b.m("DIVIDE", rho, r1), 0.86, 1.0), 0.45)))
    burn = b.m("MULTIPLY", b.m("EXPONENT", b.m("DIVIDE", b.m("SUBTRACT", rho, r0), -0.06 * r0)), line)
    # ударная волна: полоса у |p| = shock, за ней горячее перемешанное вещество
    s = vals["shock"]
    ws = b.m("MAXIMUM", b.m("MULTIPLY", s, 0.035), 1e-6)
    tn = b.noise(d, 0.8, detail=4.0, rough=0.6, w=b.m("ADD", b.m("MULTIPLY", lr, 0.8),
                                                      b.m("MULTIPLY", fw, 2.0))).outputs["Fac"]
    srad = b.m("ADD", s, b.m("MULTIPLY", b.m("SUBTRACT", tn, 0.5), b.m("MULTIPLY", ws, 4.0)))   # рваный фронт
    x = b.m("DIVIDE", b.m("SUBTRACT", rho, srad), ws)
    front = b.m("EXPONENT", b.m("MULTIPLY", b.m("MULTIPLY", x, x), -1.0))
    behind = b.m("MULTIPLY", b.m("LESS_THAN", rho, srad), vals["shock_amp"])
    sa = vals["shock_amp"]
    col = b.mix(b.m("MULTIPLY", behind, b.m("MULTIPLY", tn, 0.9), clamp=True), color, neighbor)
    col = b.mix(b.m("MULTIPLY", behind, 0.55), col, (1.0, 0.52, 0.16))       # за фронтом — раскалённое, оранжевое
    col = b.mix(b.m("MULTIPLY", front, sa, clamp=True), col, HOT_RGB)
    # грани разреза различаются яркостью (как будто свет сбоку) — иначе три плоскости сливаются в одну
    geo = b.node("ShaderNodeNewGeometry")
    face = b.m("ABSOLUTE", b.v("DOT_PRODUCT", geo.outputs["True Normal"], (0.32, 0.55, 0.77)))
    k = b.m("MULTIPLY", b.m("MULTIPLY", strength, vals["glow"]), b.m("ADD", 0.45, b.m("MULTIPLY", face, 0.75)))
    es = b.m("MULTIPLY", b.m("ADD", band, burn), k)
    es = b.m("MULTIPLY", es, b.m("ADD", 1.0, b.m("MULTIPLY", behind, b.m("ADD", 1.2, b.m("MULTIPLY", tn, 1.5)))))
    es = b.m("ADD", es, b.m("MULTIPLY", b.m("MULTIPLY", front, sa), b.m("MULTIPLY", strength, 9.0)))
    em = b.node("ShaderNodeEmission", {"Color": col, "Strength": es})
    L.new(em.outputs[0], out.inputs["Surface"])
    mat.cycles.emission_sampling = "NONE"
    mat.use_backface_culling = False
    return mat


def _core_material(name, color, strength, seed, r):
    """Железное ядро: раскалённая сфера с конвективными ячейками (Вороной) и дрожью (flow)."""
    mat, N, L, out = C.new_material(name)
    b = _NB(mat.node_tree)
    tc = b.node("ShaderNodeTexCoord")
    vals = {k: _value(b, k, v) for k, v in (("flow", seed * 0.31), ("shock", 0.0), ("shock_amp", 0.0),
                                             ("glow", 1.0), ("hot", 0.0))}
    pn = b.v("ADD", b.v("SCALE", tc.outputs["Object"], scale=1.0 / r), _seed_off(seed, 2))
    # раскалённая плазма: турбулентный шум с искажением (без «плитки» ячеек)
    nz = b.noise(pn, 3.5, detail=6.0, rough=0.62, dist=1.1, w=b.m("MULTIPLY", vals["flow"], 1.5)).outputs["Fac"]
    nz2 = b.noise(pn, 11.0, detail=3.0, rough=0.5, w=b.m("MULTIPLY", vals["flow"], 2.2)).outputs["Fac"]
    tex = b.m("MULTIPLY", b.m("ADD", 0.45, b.m("MULTIPLY", b.ss(nz, 0.3, 0.75), 0.9)),
              b.m("ADD", 0.8, b.m("MULTIPLY", nz2, 0.4)))
    lwn = b.node("ShaderNodeLayerWeight", {"Blend": 0.5})
    limb = b.m("ADD", 0.55, b.m("MULTIPLY", lwn.outputs["Facing"], 0.9))     # раскалённый край ярче (ореол)
    hot = vals["hot"]
    col = b.mix(b.m("ADD", b.m("MULTIPLY", lwn.outputs["Facing"], 0.4), b.m("MULTIPLY", hot, 0.8), clamp=True),
                color, HOT_RGB)
    es = b.m("MULTIPLY", b.m("MULTIPLY", tex, limb), b.m("MULTIPLY", strength, vals["glow"]))
    es = b.m("MULTIPLY", es, b.m("ADD", 1.0, b.m("MULTIPLY", hot, 6.0)))
    em = b.node("ShaderNodeEmission", {"Color": col, "Strength": es})
    L.new(em.outputs[0], out.inputs["Surface"])
    mat.cycles.emission_sampling = "NONE"
    return mat


def _cavity_material(name, color, strength, seed):
    """Стенка полости (внутренняя граница второго слоя, видна при коллапсе ядра): тёмный цвет слоя с горящими
    турбулентными жилами (шум по направлению — зерно не зависит от увеличения)."""
    mat, N, L, out = C.new_material(name)
    b = _NB(mat.node_tree)
    tc = b.node("ShaderNodeTexCoord")
    fw = _value(b, "flow", seed * 0.31)
    d = b.v("ADD", b.v("SCALE", b.v("NORMALIZE", tc.outputs["Object"]), scale=2.6), _seed_off(seed, 3))
    n1 = b.noise(d, 1.0, detail=6.0, rough=0.6, dist=0.8, w=fw).outputs["Fac"]
    ridge = b.m("POWER", b.m("SUBTRACT", 1.0, b.m("ABSOLUTE", b.m("SUBTRACT", b.m("MULTIPLY", n1, 2.0), 1.0))), 12.0)
    base = b.m("ADD", 0.05, b.m("MULTIPLY", b.ss(n1, 0.4, 0.75), 0.18))
    col = b.mix(b.m("MULTIPLY", ridge, 0.9, clamp=True), color, (1.0, 0.55, 0.2))      # горящие трещины — оранжевые
    es = b.m("MULTIPLY", b.m("ADD", base, b.m("MULTIPLY", ridge, 2.2)), strength)
    em = b.node("ShaderNodeEmission", {"Color": col, "Strength": es})
    L.new(em.outputs[0], out.inputs["Surface"])
    mat.cycles.emission_sampling = "NONE"
    mat.use_backface_culling = False
    return mat


def _quarter_annulus(bm, plane, r0, r1, nphi, mat_index):
    """Четверть кольца r0..r1 в плоскости plane ('xy' — z = 0, x, y ≥ 0; 'yz'; 'xz'): одна полоса квадов
    (плоская грань — радиальные узлы не нужны; шейдер считает по координатам)."""
    rows = []
    for rr in (r0, r1):
        row = []
        for j in range(nphi + 1):
            a = 0.5 * math.pi * j / nphi
            c, s = rr * math.cos(a), rr * math.sin(a)
            co = {"xy": (c, s, 0.0), "yz": (0.0, c, s), "xz": (c, 0.0, s)}[plane]
            row.append(bm.verts.new(co))
        rows.append(row)
    for j in range(nphi):
        f = bm.faces.new((rows[0][j], rows[0][j + 1], rows[1][j + 1], rows[1][j]))
        f.material_index = mat_index
        f.smooth = False


def _skin(bm, r, u, v, mat_index):
    """Сфера радиуса r без октанта x, y, z > 0 (сетка по φ, θ совпадает с плоскостями среза; u кратно 4, v — 2)."""
    north = bm.verts.new((0.0, 0.0, r))
    south = bm.verts.new((0.0, 0.0, -r))
    grid = []
    for k in range(1, v):
        th = math.pi * k / v
        grid.append([bm.verts.new((r * math.sin(th) * math.cos(2.0 * math.pi * j / u),
                                   r * math.sin(th) * math.sin(2.0 * math.pi * j / u), r * math.cos(th)))
                     for j in range(u)])
    q = u // 4
    for k in range(v):
        for j in range(u):
            if j < q and k < v // 2:
                continue                                     # вырезанный октант
            j2 = (j + 1) % u
            if k == 0:
                vs = (north, grid[0][j], grid[0][j2])
            elif k == v - 1:
                vs = (grid[k - 1][j], south, grid[k - 1][j2])
            else:
                vs = (grid[k - 1][j], grid[k][j], grid[k][j2], grid[k - 1][j2])
            f = bm.faces.new(vs)
            f.material_index = mat_index
            f.smooth = True


def build_cutaway(name, layers, photo=None, location=(0, 0, 0), parent=None, seed=1, skin_u=256, tex_scale=6.0,
                  cavity=True, coll="Star"):
    """layers — от центра наружу: dict(name, r, color, strength=4, line=2.5); первый — ядро (целая сфера).
    photo — параметры фотосферы (bodies.star.photosphere_material: temp_k, strength, seed, gran_scale, …).
    cavity — внутренняя стенка второго слоя (сфера 0.995·r ядра без октанта, материал второго слоя): когда ядро
    сжимается (коллапс), видна полость с горящей оболочкой, а не пустота до фотосферы.
    Возвращает dict(ob (кожа + срезы), core, mats {имя слоя: mat}, radii)."""
    photo = dict(photo or {})
    bm = bmesh.new()
    mats = []
    radii = [L_["r"] for L_ in layers]
    rout = radii[-1]
    pm = photosphere_material(f"{name}_Photo", unit=rout, **photo)
    mats.append(pm)
    _skin(bm, rout, skin_u, skin_u // 2, 0)
    cap_mats = {}
    for i in range(1, len(layers)):
        L_ = layers[i]
        r0, r1 = radii[i - 1], radii[i]
        nb = layers[i - 1]["color"] if i > 0 else L_["color"]
        m = _cap_material(f"{name}_{L_['name']}", r0, r1, L_["color"], L_.get("strength", 4.0), L_.get("line", 2.5),
                          seed + i, tex_scale, nb)
        mats.append(m)
        cap_mats[L_["name"]] = m
        for pl in ("xy", "yz", "xz"):
            _quarter_annulus(bm, pl, r0, r1, skin_u // 4, len(mats) - 1)   # дуги — как рёбра кожи (без щелей)
        if i == 1 and cavity:
            cav = _cavity_material(f"{name}_Cavity", L_["color"], L_.get("strength", 4.0), seed + 50)
            mats.append(cav)
            cap_mats[f"{L_['name']}_cavity"] = cav
            _skin(bm, r0 * 0.995, skin_u // 2, skin_u // 4, len(mats) - 1)
    me = bpy.data.meshes.new(f"{name}_Mesh")
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    C.link(ob, coll)
    ob.location = location
    if parent is not None:
        ob.parent = parent
    _ghost(ob)
    # ядро — целая сфера
    L0 = layers[0]
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=128, v_segments=64, radius=radii[0])
    cme = bpy.data.meshes.new(f"{name}_CoreMesh")
    bm.to_mesh(cme)
    bm.free()
    cme.shade_smooth()
    cm = _core_material(f"{name}_{L0['name']}", L0["color"], L0.get("strength", 6.0), seed, radii[0])
    cme.materials.append(cm)
    core = bpy.data.objects.new(f"{name}_Core", cme)
    C.link(core, coll)
    core.parent = ob
    _ghost(core)
    cap_mats[L0["name"]] = cm
    return dict(ob=ob, core=core, mats=cap_mats, photo=pm, radii=radii, layers=layers)


def key_values(cut, name, pairs, ipo="BEZIER", which=None):
    """Ключи узла name (CAP_VALUES; у ядра ещё 'hot') во всех материалах слоёв (which — список имён слоёв)."""
    for ln, m in cut["mats"].items():
        if which is not None and ln not in which:
            continue
        nd = m.node_tree.nodes.get(name)
        if nd is None:
            continue
        s = nd.outputs[0]
        for f, v in pairs:
            s.default_value = v
            s.keyframe_insert("default_value", frame=f)
        anim.set_interpolation(m.node_tree, ipo, path_contains=f'nodes["{name}"]')
