"""Светящаяся линия орбиты со «следом» (для схем орбит, оформления, наложений поверх сцены).

    from spacekit.fx import orbit_line
    ob = orbit_line.build_orbit_line("Orbit_b", a=2.0, e=0.1, parent=planet_root, incl_deg=12, node_deg=30,
                                     trail_head_deg=40, trail_len_deg=220, strength=6.0)
Линия — кривая с тонким скосом (bevel) и эмиссией. След: яркость максимальна у «головы» (аномалия
trail_head_deg) и экспоненциально гаснет назад по орбите на trail_len_deg; без следа — ровная линия.
Ориентация: плоскость орбиты = XY объекта, поворот Rz(node)·Rx(incl) (как orbits.add_kepler_orbit).
Тени не отбрасывает и не освещает сцену (только камера). Анимация «бегущего» следа — ключами trail_head
(`key_trail(ob, deg0, deg1, f0, f1)`).
"""
import math

import bpy

from .. import anim
from .. import core as C
from ..orbits import kepler_xy


def _material(name, color, strength, head_deg, len_deg, floor):
    mat, N, L, out = C.new_material(name)
    tc = N.new("ShaderNodeTexCoord")
    sep = N.new("ShaderNodeSeparateXYZ")
    L.new(tc.outputs["Object"], sep.inputs[0])
    # угол точки на орбите (вокруг фокуса), 0..2π
    at2 = N.new("ShaderNodeMath"); at2.operation = "ARCTAN2"
    L.new(sep.outputs[1], at2.inputs[0]); L.new(sep.outputs[0], at2.inputs[1])
    head = N.new("ShaderNodeValue"); head.name = head.label = "trail_head"
    head.outputs[0].default_value = math.radians(head_deg)
    # отставание от головы назад по орбите: d = (head − θ) mod 2π
    d = C.math_node(N, L, "SUBTRACT", head.outputs[0], at2.outputs[0])
    d = C.math_node(N, L, "FLOORED_MODULO", d, 2 * math.pi)
    if len_deg > 0:
        k = 3.0 / math.radians(len_deg)
        fade = C.math_node(N, L, "EXPONENT", C.math_node(N, L, "MULTIPLY", d, -k))
        fade = C.math_node(N, L, "MAXIMUM", fade, floor)
    else:
        fade = None
    em = N.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1.0)
    if fade is not None:
        L.new(C.math_node(N, L, "MULTIPLY", fade, strength), em.inputs["Strength"])
    else:
        em.inputs["Strength"].default_value = strength
    # мягкий край: полупрозрачная примесь (яркость складывается с фоном)
    tr = N.new("ShaderNodeBsdfTransparent")
    add = N.new("ShaderNodeAddShader")
    L.new(em.outputs[0], add.inputs[0]); L.new(tr.outputs[0], add.inputs[1])
    L.new(add.outputs[0], out.inputs["Surface"])
    mat.cycles.emission_sampling = "NONE"
    return mat, head


def build_orbit_line(name, a, e=0.0, parent=None, incl_deg=0.0, node_deg=0.0, omega_deg=0.0,
                     width=0.006, color=(0.62, 0.86, 1.0), strength=6.0, trail_head_deg=0.0, trail_len_deg=0.0,
                     floor=0.06, segments=720, coll="FX"):
    """Эллипс (фокус в начале координат родителя) толщиной width; trail_len_deg>0 — гаснущий след от головы."""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = width
    cu.bevel_resolution = 2
    sp = cu.splines.new("POLY")
    sp.points.add(segments - 1)
    for i in range(segments):
        x, y = kepler_xy(a, e, 2 * math.pi * i / segments, omega_deg)   # равномерно по средней аномалии
        sp.points[i].co = (x, y, 0.0, 1.0)
    sp.use_cyclic_u = True
    ob = bpy.data.objects.new(name, cu)
    C.link(ob, coll)
    if parent is not None:
        ob.parent = parent
    ob.rotation_mode = "YXZ"
    ob.rotation_euler = (math.radians(incl_deg), 0.0, math.radians(node_deg))
    mat, head = _material(f"{name}_Mat", color, strength, trail_head_deg, trail_len_deg, floor)
    cu.materials.append(mat)
    ob["trail_mat"] = mat.name
    vis = ob.visible_shadow = False
    ob.visible_diffuse = ob.visible_glossy = ob.visible_transmission = ob.visible_volume_scatter = vis
    return ob


def key_trail(ob, deg0, deg1, frame_start, frame_end):
    """Анимация головы следа (LINEAR): след бежит по орбите вместе с телом."""
    mat = bpy.data.materials[ob["trail_mat"]]
    node = mat.node_tree.nodes["trail_head"]
    anim.key_value_node(node, math.radians(deg0), math.radians(deg1), frame_start, frame_end)
    anim.linearize(mat.node_tree)


def point_on_orbit(a, e=0.0, mean_anomaly_deg=0.0, omega_deg=0.0):
    """Точка на эллипсе в плоскости орбиты (для постановки тела на линию)."""
    return (*kepler_xy(a, e, math.radians(mean_anomaly_deg), omega_deg), 0.0)
