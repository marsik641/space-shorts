"""Волокнистая оболочка взрыва: полупрозрачный пузырь из светящихся нитей (как остатки Cas A, SN 1006 на снимках).

    from spacekit.fx import sn_shell as SS
    sh = SS.build_shell_nebula("Blast", radius=1.0, seed=5, palette=SS.FIRE)
    SS.key_radius(sh, lambda f: 1.0 + 0.05 * f, 1, n)          # внешний край (мир) — гомологичное расширение
    SS.key_value(sh, "glow", [(1, 0.0), (20, 30.0), (n, 8.0)])  # яркость (∝ 1/R — постоянная поверхностная яркость)
    SS.key_value(sh, "hot", [(1, 1.0), (n, 0.2)])               # 1 — нити добела раскалены, 0 — цвета палитры

Объём только с эмиссией (без поглощения — прозрачный, сквозь него видно центр). Координаты объекта: 1 = внешний
край. Оболочка — слой [rb − thick, rb] с неровным краем rb(направление); внутри слоя — нити: гребни двух масштабов
искажённого fBm (1 − |2n − 1|)^k (тонкие яркие волокна), сгустки, слабая дымка (haze); внутри — голубое сияние
(inner) вокруг центра. Цвет — палитра по шуму и радиусу: FIRE (огонь: белое-жёлтое внутри → оранжевый → красный край),
CASA (многоцветные «линии элементов», как композитные снимки остатков: синий, голубой, жёлтый, зелёный, красный).
Цвета — условность (в описание). Шаг луча: нити тонкие — step ≈ 0.05–0.1.
"""
import bmesh
import bpy

from .. import anim
from .. import core as C
from ..bodies.planets import _NB, _ghost, _seed_off
from .explosion import _ramp

FIRE = [(0.00, (1.00, 0.96, 0.85)), (0.28, (1.00, 0.80, 0.35)), (0.52, (1.00, 0.45, 0.08)),
        (0.76, (0.95, 0.16, 0.05)), (1.00, (0.70, 0.04, 0.18))]
CASA = [(0.00, (0.20, 0.45, 1.00)), (0.17, (0.30, 0.90, 1.00)), (0.33, (1.00, 0.92, 0.30)),
        (0.48, (0.40, 1.00, 0.30)), (0.63, (1.00, 0.55, 0.12)), (0.80, (1.00, 0.16, 0.22)),
        (1.00, (0.70, 0.22, 1.00))]
INNER_RGB = (0.35, 0.55, 1.0)
VALUES = ("glow", "flow", "hot", "haze", "thick", "inner", "cover")


def _value(b, name, v):
    n = b.node("ShaderNodeValue", name=name, label=name)
    n.outputs[0].default_value = v
    return n.outputs[0]


def _ridge(b, n, k):
    return b.m("POWER", b.m("SUBTRACT", 1.0, b.m("ABSOLUTE", b.m("SUBTRACT", b.m("MULTIPLY", n, 2.0), 1.0))), k)


def _material(name, seed, palette, radial, fil_scale, sharp, step):
    mat, N, L, out = C.new_material(name)
    b = _NB(mat.node_tree)
    tc = b.node("ShaderNodeTexCoord")
    p0 = tc.outputs["Object"]
    p = b.v("ADD", p0, _seed_off(seed))
    vals = {k: _value(b, k, v) for k, v in (("glow", 10.0), ("flow", seed * 0.23), ("hot", 0.5), ("haze", 1.0),
                                             ("thick", 0.32), ("inner", 0.0), ("cover", 0.32))}
    fw = vals["flow"]
    r = b.v("LENGTH", p0)
    w1 = b.noise(p, 1.3, detail=1.0, rough=0.5, w=b.m("MULTIPLY", fw, 0.5)).outputs["Color"]
    pw = b.v("ADD", p, b.v("SCALE", b.v("SUBTRACT", w1, (0.5, 0.5, 0.5)), scale=0.55))
    # неровный внешний край
    knob = b.noise(b.v("NORMALIZE", pw), 2.5, detail=2.0, rough=0.6, w=b.m("MULTIPLY", fw, 0.4)).outputs["Fac"]
    rb = b.m("ADD", 0.93, b.m("MULTIPLY", b.m("SUBTRACT", knob, 0.5), 0.24))
    th = vals["thick"]
    band = b.m("MULTIPLY",
               b.node("ShaderNodeMapRange", {0: r, 1: b.m("SUBTRACT", rb, th), 2: b.m("SUBTRACT", rb, b.m("MULTIPLY", th, 0.35)),
                                             3: 0.0, 4: 1.0}, interpolation_type="SMOOTHSTEP", clamp=True).outputs[0],
               b.m("SUBTRACT", 1.0, b.node("ShaderNodeMapRange", {0: r, 1: b.m("SUBTRACT", rb, 0.03),
                                                                  2: b.m("ADD", rb, 0.05), 3: 0.0, 4: 1.0},
                                           interpolation_type="SMOOTHSTEP", clamp=True).outputs[0]))
    # нити двух масштабов + сгустки
    n1 = b.noise(pw, fil_scale[0], detail=3.0, rough=0.55, dist=0.4, w=fw).outputs["Fac"]
    n2 = b.noise(b.v("ADD", pw, (2.7, 1.3, 4.1)), fil_scale[1], detail=2.0, rough=0.5,
                 w=b.m("MULTIPLY", fw, 1.4)).outputs["Fac"]
    f1 = _ridge(b, n1, sharp)
    f2 = _ridge(b, n2, sharp * 1.3)
    # покрытие: нити есть не везде — клочья с просветами (cover — порог, выше — реже)
    cn = b.noise(pw, 1.8, detail=2.0, rough=0.55, w=b.m("MULTIPLY", fw, 0.6)).outputs["Fac"]
    cv = vals["cover"]
    cl = b.node("ShaderNodeMapRange", {0: cn, 1: cv, 2: b.m("ADD", cv, 0.28), 3: 0.0, 4: 1.0},
                interpolation_type="SMOOTHSTEP", clamp=True).outputs[0]
    fil = b.m("MULTIPLY", b.m("ADD", f1, b.m("MULTIPLY", f2, 0.55)), b.m("ADD", 0.04, b.m("MULTIPLY", cl, 1.3)))
    dens = b.m("MULTIPLY", band, b.m("ADD", fil, b.m("MULTIPLY", vals["haze"], 0.06)))
    # цвет: палитра по шуму (+ радиус), к пикам нитей — добела по hot
    nc = b.noise(pw, 1.1, detail=1.0, rough=0.5, w=b.m("MULTIPLY", fw, 0.3)).outputs["Fac"]
    ci = b.m("ADD", b.m("MULTIPLY", b.m("DIVIDE", r, rb), radial),
             b.m("MULTIPLY", b.m("SUBTRACT", nc, 0.5), 1.0 - radial + 0.35), clamp=True)
    if radial < 0.5:
        ci = b.m("ADD", ci, b.m("MULTIPLY", b.m("SUBTRACT", nc, 0.5), 0.6), clamp=True)
    col = _ramp(b, ci, palette, interp="EASE")
    col = b.mix(b.m("MULTIPLY", vals["hot"], b.m("MULTIPLY", f1, f1), clamp=True), col, (1.0, 0.97, 0.9))
    es = b.m("MULTIPLY", b.m("MULTIPLY", dens, vals["glow"]), b.m("ADD", 0.6, b.m("MULTIPLY", cl, 0.8)))
    em = b.node("ShaderNodeEmission", {"Color": col, "Strength": es})
    # голубое сияние внутри (свет центрального источника в разрежённом газе)
    inner = b.m("MULTIPLY", b.m("SUBTRACT", 1.0, b.ss(r, 0.0, b.m("MULTIPLY", rb, 0.85))), vals["inner"])
    em2 = b.node("ShaderNodeEmission", {"Color": (*INNER_RGB, 1.0), "Strength": inner})
    ad = b.node("ShaderNodeAddShader", {0: em.outputs[0], 1: em2.outputs[0]})
    L.new(ad.outputs[0], out.inputs["Volume"])
    mc = mat.cycles
    for k, v in (("volume_sampling", "DISTANCE"), ("volume_interpolation", "LINEAR"), ("volume_step_rate", step)):
        try:
            setattr(mc, k, v)
        except (AttributeError, TypeError):
            pass
    return mat


def build_shell_nebula(name, radius=1.0, location=(0, 0, 0), parent=None, seed=1, palette=FIRE, radial=0.7,
                       fil_scale=(3.2, 8.0), sharp=7.0, stretch=(1, 1, 1), step=0.08, hollow=0.0, coll="FX", **values):
    """Объём-оболочка: домен — икосфера радиуса 1.1 (ед. объекта), объект масштабирован на radius·stretch.
    radial — доля радиуса в индексе палитры (FIRE: 0.7 — белое внутри, красное снаружи; CASA: 0.2 — пятнами).
    values — начальные значения VALUES. hollow > 0 — полый домен (внутренняя сфера радиуса hollow с вывернутыми
    нормалями): луч шагает только в слое нитей — в разы дешевле; inner (сияние внутри) тогда не работает — свет
    центра давать спрайтом. Возвращает dict(ob, mat, stretch)."""
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=3, radius=1.1)
    if hollow > 0:
        res = bmesh.ops.create_icosphere(bm, subdivisions=3, radius=hollow)
        bmesh.ops.reverse_faces(bm, faces=[f for f in bm.faces if all(v in res["verts"] for v in f.verts)])
    me = bpy.data.meshes.new(f"{name}_Dom")
    bm.to_mesh(me)
    bm.free()
    mat = _material(f"{name}_Mat", seed, palette, radial, fil_scale, sharp, step)
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    C.link(ob, coll)
    ob.location = location
    if parent is not None:
        ob.parent = parent
    ob.scale = tuple(radius * s for s in stretch)
    _ghost(ob)
    sh = dict(ob=ob, mat=mat, stretch=tuple(stretch))
    for k, v in values.items():
        sh["mat"].node_tree.nodes[k].outputs[0].default_value = v
    return sh


def key_value(sh, name, pairs, ipo="BEZIER"):
    s = sh["mat"].node_tree.nodes[name].outputs[0]
    for f, v in pairs:
        s.default_value = v
        s.keyframe_insert("default_value", frame=f)
    anim.set_interpolation(sh["mat"].node_tree, ipo, path_contains=f'nodes["{name}"]')


def key_radius(sh, r_of_frame, frame_start, frame_end, step=1):
    ob, st = sh["ob"], sh["stretch"]
    for f in list(range(frame_start, frame_end + 1, step)) + [frame_end]:
        r = r_of_frame(f)
        ob.scale = tuple(r * s for s in st)
        ob.keyframe_insert("scale", frame=f)
    anim.set_interpolation(ob, "LINEAR", path_contains="scale")
