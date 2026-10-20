"""Радиальный всплеск штрихов: нейтрино из ядра, частицы от вспышки — тонкие светящиеся «иглы», бегущие от центра.

    from spacekit.fx import burst as BU
    bu = BU.build_burst("Nu", n=700, r_max=50.0, cam=cam, px=1.1, color=(0.75, 0.6, 1.0), strength=12.0,
                        trail=3.0, lag=4.0, seed=3)
    BU.key_head(bu, [(f0, 0.0), (f1, 60.0)])          # фронт (ед. объекта) — у каждой иглы свой отстающий хвост

Геометрия статична: n лучей от r_min до r_max (направления — равномерно по сфере, «золотая» спираль + шум),
на каждом луче K узлов; толщина — постоянная в пикселях (GN fx.path_line, камера cam). Шейдер, как у
fx.path_line, показывает только бегущий отрезок: у луча своя голова h = head − lag_i (lag_i ∈ [0, lag]),
яркость exp(−(h − t)/trail) при t ≤ h (t — расстояние от центра), 0 впереди головы; яркость луча ×amp_i.
Не освещает сцену и не даёт теней. Видимость нейтрино — условность (в описание).
"""
import math
import random

import bpy
from mathutils import Vector

from .. import anim
from .. import core as C
from . import path_line as PLN


def _material(name, color, strength, trail, fade_in):
    mat, N, L, out = C.new_material(name)
    def attr(nm):
        a = N.new("ShaderNodeAttribute")
        a.attribute_type = "GEOMETRY"
        a.attribute_name = nm
        return a.outputs["Fac"]
    t, lag, amp = attr("t"), attr("lag"), attr("amp")
    hv = N.new("ShaderNodeValue")
    hv.name = hv.label = "head"
    hv.outputs[0].default_value = 0.0
    h = C.math_node(N, L, "SUBTRACT", hv.outputs[0], lag)
    d = C.math_node(N, L, "SUBTRACT", h, t)                                   # отставание точки от головы
    vis = C.math_node(N, L, "GREATER_THAN", d, -1e-4)
    glow = C.math_node(N, L, "EXPONENT", C.math_node(N, L, "MULTIPLY", C.math_node(N, L, "MAXIMUM", d, 0.0),
                                                     -1.0 / max(trail, 1e-6)))
    br = C.math_node(N, L, "MULTIPLY", C.math_node(N, L, "MULTIPLY", glow, vis), amp)
    if fade_in > 0:
        br = C.math_node(N, L, "MULTIPLY", br, C.math_node(N, L, "MINIMUM",
                                                          C.math_node(N, L, "DIVIDE", t, fade_in), 1.0))
    k = N.new("ShaderNodeValue")
    k.name = k.label = "strength"
    k.outputs[0].default_value = strength
    em = N.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1.0)
    L.new(C.math_node(N, L, "MULTIPLY", br, k.outputs[0]), em.inputs["Strength"])
    tr = N.new("ShaderNodeBsdfTransparent")
    add = N.new("ShaderNodeAddShader")
    L.new(em.outputs[0], add.inputs[0])
    L.new(tr.outputs[0], add.inputs[1])
    L.new(add.outputs[0], out.inputs["Surface"])
    mat.cycles.emission_sampling = "NONE"
    return mat


def directions(n, seed=1, jitter=0.6):
    """n направлений почти равномерно по сфере (спираль Фибоначчи + сдвиг)."""
    rnd = random.Random(seed)
    ga = math.pi * (3.0 - math.sqrt(5.0))
    out = []
    for i in range(n):
        z = 1.0 - 2.0 * (i + 0.5 + jitter * (rnd.random() - 0.5)) / n
        z = max(-1.0, min(1.0, z))
        rr = math.sqrt(max(0.0, 1.0 - z * z))
        a = ga * i + jitter * (rnd.random() - 0.5)
        out.append(Vector((rr * math.cos(a), rr * math.sin(a), z)))
    return out


def build_burst(name, n=600, r_min=0.0, r_max=10.0, cam=None, px=1.0, color=(0.75, 0.6, 1.0), strength=10.0,
                trail=1.0, lag=1.0, amp=(0.35, 1.0), k=24, sides=4, seed=1, dirs=None, fade_in=0.0,
                location=(0, 0, 0), parent=None, coll="FX"):
    """n лучей-игл; cam — экранная толщина (радиус px пикселей), без cam — толщина px в ед. объекта.
    dirs — свои направления (иначе равномерно). Возвращает объект (ob['burst_mat'] — материал)."""
    rnd = random.Random(seed * 7 + 1)
    dirs = dirs or directions(n, seed)
    verts, faces, tv, lv, av, dv = [], [], [], [], [], []
    for d in dirs:
        d = Vector(d).normalized()
        ref = Vector((0, 0, 1)) if abs(d.z) < 0.9 else Vector((1, 0, 0))
        e1 = d.cross(ref).normalized()
        e2 = d.cross(e1).normalized()
        lg = rnd.random() * lag
        am = amp[0] + (amp[1] - amp[0]) * rnd.random() ** 2
        base = len(verts)
        for i in range(k):
            # узлы гуще у центра (там лучи ближе друг к другу и к камере в крупном плане)
            u = i / (k - 1)
            r = r_min + (r_max - r_min) * u * u
            for s in range(sides):
                a = 2.0 * math.pi * s / sides
                off = e1 * math.cos(a) + e2 * math.sin(a)
                verts.append(d * r if cam is not None else d * r + off * px)
                dv.extend(off)
                tv.append(r)
                lv.append(lg)
                av.append(am)
        for i in range(k - 1):
            for s in range(sides):
                s2 = (s + 1) % sides
                faces.append((base + i * sides + s, base + i * sides + s2, base + (i + 1) * sides + s2,
                              base + (i + 1) * sides + s))
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    for nm, vals in (("t", tv), ("lag", lv), ("amp", av)):
        at = me.attributes.new(nm, "FLOAT", "POINT")
        at.data.foreach_set("value", vals)
    if cam is not None:
        da = me.attributes.new("dir", "FLOAT_VECTOR", "POINT")
        da.data.foreach_set("vector", dv)
    me.update()
    mat = _material(f"{name}_Mat", color, strength, trail, fade_in)
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    C.link(ob, coll)
    ob.location = location
    if parent is not None:
        ob.parent = parent
    ob["burst_mat"] = mat.name
    if cam is not None:
        mod = ob.modifiers.new("ScreenWidth", "NODES")
        mod.node_group = PLN._screen_width_group(f"{name}_SW", cam)
        PLN.set_screen_width(ob, cam, px)
    ob.visible_shadow = False
    ob.visible_diffuse = ob.visible_glossy = ob.visible_transmission = ob.visible_volume_scatter = False
    return ob


def key_head(ob, pairs, ipo="LINEAR"):
    """Ключи фронта (ед. объекта): pairs [(кадр, радиус)]."""
    nt = bpy.data.materials[ob["burst_mat"]].node_tree
    s = nt.nodes["head"].outputs[0]
    for f, v in pairs:
        s.default_value = v
        s.keyframe_insert("default_value", frame=f)
    anim.set_interpolation(nt, ipo, extrapolate="CONSTANT", path_contains='nodes["head"]')


def key_strength(ob, pairs, ipo="BEZIER"):
    nt = bpy.data.materials[ob["burst_mat"]].node_tree
    s = nt.nodes["strength"].outputs[0]
    for f, v in pairs:
        s.default_value = v
        s.keyframe_insert("default_value", frame=f)
    anim.set_interpolation(nt, ipo, path_contains='nodes["strength"]')
