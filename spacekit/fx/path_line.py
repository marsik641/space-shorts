"""Светящаяся линия по произвольным точкам (траектория аппарата, путь сигнала) с «прорисовкой» во времени.

    from spacekit.fx import path_line as PLN
    ob = PLN.build_path_line("Traj_V1", pts, width=0.3, color=(1.0, 0.75, 0.35), strength=8.0,
                             head=1.0, trail=0.15, floor=0.35)
    PLN.key_head(ob, 0.0, 1.0, f0, f1)              # линия «рисуется» от начала к концу
    PLN.key_follow(marker, pts, 0.0, 1.0, f0, f1)   # объект-голова едет по линии синхронно

Геометрия — трубка (меш, кольца по `sides` вершин, рамки без закрутки), у каждой вершины атрибут `t` 0..1:
по умолчанию доля пройденной длины; `t=` — свой параметр (например, время: точки траектории по датам).
Шейдер: видна часть t ≤ head; яркость = strength · max(floor, exp(−(head − t)/trail)) — ярче у головы,
к прошлому гаснет до floor. floor=0 и малый trail — «импульс» (короткий светящийся отрезок бежит по линии).
Эмиссия + прозрачность: не освещает сцену, не даёт теней (как fx.orbit_line).
"""
import math

import bpy
from mathutils import Vector

from .. import anim
from .. import core as C


def _cum_t(pts):
    d = [0.0]
    for a, b in zip(pts, pts[1:]):
        d.append(d[-1] + (Vector(b) - Vector(a)).length)
    tot = d[-1] or 1.0
    return [x / tot for x in d]


def _material(name, color, strength, head, trail, floor, end_fade):
    mat, N, L, out = C.new_material(name)
    at = N.new("ShaderNodeAttribute")
    at.attribute_type = "GEOMETRY"
    at.attribute_name = "t"
    hv = N.new("ShaderNodeValue")
    hv.name = hv.label = "head"
    hv.outputs[0].default_value = head
    d = C.math_node(N, L, "SUBTRACT", hv.outputs[0], at.outputs["Fac"])         # отставание от головы
    vis = C.math_node(N, L, "GREATER_THAN", d, -1e-4)                          # t <= head
    k = 1.0 / max(trail, 1e-4)
    glow = C.math_node(N, L, "EXPONENT", C.math_node(N, L, "MULTIPLY", C.math_node(N, L, "MAXIMUM", d, 0.0), -k))
    br = C.math_node(N, L, "MAXIMUM", glow, floor)
    if end_fade > 0:
        # плавное появление у самого начала линии (t < end_fade)
        st = C.math_node(N, L, "MINIMUM", C.math_node(N, L, "DIVIDE", at.outputs["Fac"], end_fade), 1.0)
        br = C.math_node(N, L, "MULTIPLY", br, st)
    br = C.math_node(N, L, "MULTIPLY", br, vis)
    em = N.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1.0)
    L.new(C.math_node(N, L, "MULTIPLY", br, strength), em.inputs["Strength"])
    tr = N.new("ShaderNodeBsdfTransparent")
    mix = N.new("ShaderNodeMixShader")
    L.new(vis, mix.inputs[0])
    L.new(tr.outputs[0], mix.inputs[1])
    add = N.new("ShaderNodeAddShader")
    L.new(em.outputs[0], add.inputs[0])
    L.new(tr.outputs[0], add.inputs[1])
    L.new(add.outputs[0], mix.inputs[2])
    L.new(mix.outputs[0], out.inputs["Surface"])
    mat.cycles.emission_sampling = "NONE"
    return mat


def _screen_width_group(name, cam):
    """GN: вершины трубки лежат на оси, атрибут dir — направление от оси; смещение = dir · K · |P − камера|
    (K = радиус в пикселях × угол пикселя): постоянная толщина на экране вдоль всей линии и при любом отъезде."""
    ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = ng.nodes, ng.links
    gi = N.new("NodeGroupInput")
    go = N.new("NodeGroupOutput")
    oi = N.new("GeometryNodeObjectInfo")
    oi.transform_space = "RELATIVE"                 # положение камеры в системе объекта линии
    oi.inputs["Object"].default_value = cam
    k = N.new("ShaderNodeValue")
    k.name = k.label = "K"
    pos = N.new("GeometryNodeInputPosition")
    na = N.new("GeometryNodeInputNamedAttribute")
    na.data_type = "FLOAT_VECTOR"
    na.inputs["Name"].default_value = "dir"
    dist = N.new("ShaderNodeVectorMath")
    dist.operation = "DISTANCE"
    L.new(pos.outputs["Position"], dist.inputs[0])
    L.new(oi.outputs["Location"], dist.inputs[1])
    mul = N.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    L.new(dist.outputs["Value"], mul.inputs[0])
    L.new(k.outputs[0], mul.inputs[1])
    sc = N.new("ShaderNodeVectorMath")
    sc.operation = "SCALE"
    L.new(na.outputs["Attribute"], sc.inputs[0])
    L.new(mul.outputs[0], sc.inputs["Scale"])
    sp = N.new("GeometryNodeSetPosition")
    L.new(gi.outputs["Geometry"], sp.inputs["Geometry"])
    L.new(sc.outputs["Vector"], sp.inputs["Offset"])
    L.new(sp.outputs["Geometry"], go.inputs["Geometry"])
    return ng


def set_screen_width(ob, cam, px, scene=None):
    """Толщина линии ≈ 2·px пикселей (px — радиус) при текущем объективе/разрешении (линия собрана с cam=)."""
    from . import label as _LB
    ng = ob.modifiers["ScreenWidth"].node_group
    ng.nodes["K"].outputs[0].default_value = px * _LB.pixel_angle(cam, scene or bpy.context.scene)


def build_path_line(name, points, width=0.01, color=(0.62, 0.86, 1.0), strength=6.0, t=None,
                    head=1.0, trail=0.2, floor=0.25, end_fade=0.0, sides=8, parent=None, coll="FX",
                    cam=None, px=1.2):
    """Трубка радиуса width по точкам (мир или система parent). Возвращает объект (ob['path_mat'] — имя материала).
    cam= — экранная толщина (радиус px пикселей) через GN-модификатор, width не используется."""
    pts = [Vector(p) for p in points]
    ts = list(t) if t is not None else _cum_t(pts)
    n = len(pts)
    # касательные и рамки параллельного переноса (без закрутки)
    tang = []
    for i in range(n):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, n - 1)]
        tang.append((b - a).normalized())
    ref = Vector((0, 0, 1)) if abs(tang[0].z) < 0.9 else Vector((1, 0, 0))
    nrm = (ref - tang[0] * ref.dot(tang[0])).normalized()
    verts, faces, tv, dirs = [], [], [], []
    for i in range(n):
        T = tang[i]
        nrm = (nrm - T * nrm.dot(T))
        if nrm.length < 1e-9:
            nrm = (ref - T * ref.dot(T))
        nrm.normalize()
        bnm = T.cross(nrm)
        for k in range(sides):
            a = 2 * math.pi * k / sides
            dv = nrm * math.cos(a) + bnm * math.sin(a)
            verts.append(pts[i] if cam is not None else pts[i] + dv * width)
            dirs.extend(dv)
            tv.append(ts[i])
    for i in range(n - 1):
        for k in range(sides):
            j = (k + 1) % sides
            faces.append((i * sides + k, i * sides + j, (i + 1) * sides + j, (i + 1) * sides + k))
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    attr = me.attributes.new("t", "FLOAT", "POINT")
    attr.data.foreach_set("value", tv)
    if cam is not None:
        da = me.attributes.new("dir", "FLOAT_VECTOR", "POINT")
        da.data.foreach_set("vector", dirs)
    me.update()
    mat = _material(f"{name}_Mat", color, strength, head, trail, floor, end_fade)
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    C.link(ob, coll)
    if parent is not None:
        ob.parent = parent
    ob["path_mat"] = mat.name
    if cam is not None:
        mod = ob.modifiers.new("ScreenWidth", "NODES")
        mod.node_group = _screen_width_group(f"{name}_SW", cam)
        set_screen_width(ob, cam, px)
    ob.visible_shadow = False
    ob.visible_diffuse = ob.visible_glossy = ob.visible_transmission = ob.visible_volume_scatter = False
    return ob


def key_head(ob, h0, h1, frame_start, frame_end, ipo="LINEAR"):
    """Ключи головы (доля t): линия прорисовывается от h0 до h1 за кадры frame_start..frame_end."""
    mat = bpy.data.materials[ob["path_mat"]]
    node = mat.node_tree.nodes["head"]
    s = node.outputs[0]
    s.default_value = h0
    s.keyframe_insert("default_value", frame=frame_start)
    s.default_value = h1
    s.keyframe_insert("default_value", frame=frame_end)
    anim.set_interpolation(mat.node_tree, ipo, extrapolate="CONSTANT")


def point_at(points, frac, t=None):
    """Точка на ломаной при параметре frac (доля длины или свой t)."""
    pts = [Vector(p) for p in points]
    ts = list(t) if t is not None else _cum_t(pts)
    if frac <= ts[0]:
        return pts[0].copy()
    for i in range(1, len(pts)):
        if frac <= ts[i]:
            u = (frac - ts[i - 1]) / max(ts[i] - ts[i - 1], 1e-12)
            return pts[i - 1].lerp(pts[i], u)
    return pts[-1].copy()


def key_follow(ob, points, h0, h1, frame_start, frame_end, t=None, step=1):
    """Ключи положения объекта по ломаной синхронно с key_head (LINEAR по кадрам)."""
    for f in range(frame_start, frame_end + 1, step):
        u = (f - frame_start) / max(frame_end - frame_start, 1)
        ob.location = point_at(points, h0 + (h1 - h0) * u, t)
        ob.keyframe_insert("location", frame=f)
    anim.set_interpolation(ob, "LINEAR")
