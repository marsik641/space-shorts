"""Светящаяся оболочка-граница: гелиопауза, ударная волна, фронт света/сигнала, магнитосфера.

    from spacekit.fx import shell as SH
    hp = SH.build_shell("Heliopause", radius=5000, color=(0.35, 0.6, 1.0), strength=2.0, rim_power=2.5,
                        noise_scale=0.004, noise_amp=0.8)
    SH.key_radius(front, r0, r1, f0, f1, ease=1.0)   # расширяющийся фронт
    SH.key_strength(hp, [(1, 0.0), (60, 2.0)])       # появление/исчезновение

Поверхность (не объём — без шума Монте-Карло): эмиссия × «скользящий» множитель Layer Weight Facing^rim_power
(край сферы/плоскость под углом ярче, лицом к камере — почти прозрачна) × (1 + noise_amp·(шум − 0.5)) —
волокна плазмы; поверх — прозрачность (яркость складывается с фоном). Невидимое показано видимым — условность
(в описание ролика). Не освещает сцену, не даёт теней. Шум — в координатах объекта (масштаб noise_scale — на
единицу радиуса 1, т.е. при radius=R зерно ≈ 1/(noise_scale·R) по размеру); W шума — ключами (key_flow).
"""
import math

import bmesh
import bpy

from .. import anim
from .. import core as C


def _material(name, color, color_edge, strength, rim_power, face_floor, noise_scale, noise_amp, seed):
    mat, N, L, out = C.new_material(name)
    lw = N.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.5
    rim = C.math_node(N, L, "POWER", lw.outputs["Facing"], rim_power)
    rim = C.math_node(N, L, "ADD", C.math_node(N, L, "MULTIPLY", rim, 1.0 - face_floor), face_floor)
    tc = N.new("ShaderNodeTexCoord")
    nz = N.new("ShaderNodeTexNoise")
    nz.noise_dimensions = "4D"
    nz.inputs["Scale"].default_value = noise_scale
    nz.inputs["Detail"].default_value = 8.0
    nz.inputs["Roughness"].default_value = 0.6
    nz.inputs["Distortion"].default_value = 1.5
    w = N.new("ShaderNodeValue")
    w.name = w.label = "flow"
    w.outputs[0].default_value = seed * 1.37
    L.new(w.outputs[0], nz.inputs["W"])
    L.new(tc.outputs["Object"], nz.inputs["Vector"])
    # волокна: резкий контраст шума
    fil = N.new("ShaderNodeMapRange")
    fil.inputs[1].default_value, fil.inputs[2].default_value = 0.35, 0.75
    fil.inputs[3].default_value, fil.inputs[4].default_value = 1.0 - noise_amp, 1.0 + noise_amp
    L.new(nz.outputs["Fac"], fil.inputs[0])
    br = C.math_node(N, L, "MULTIPLY", rim, fil.outputs[0])
    k = N.new("ShaderNodeValue")
    k.name = k.label = "strength"
    k.outputs[0].default_value = strength
    br = C.math_node(N, L, "MULTIPLY", br, k.outputs[0])
    # цвет: к краю — color_edge
    mix = N.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    L.new(lw.outputs["Facing"], mix.inputs[0])
    mix.inputs[6].default_value = (*color, 1.0)
    mix.inputs[7].default_value = (*(color_edge or color), 1.0)
    em = N.new("ShaderNodeEmission")
    L.new(mix.outputs[2], em.inputs["Color"])
    L.new(br, em.inputs["Strength"])
    tr = N.new("ShaderNodeBsdfTransparent")
    add = N.new("ShaderNodeAddShader")
    L.new(em.outputs[0], add.inputs[0])
    L.new(tr.outputs[0], add.inputs[1])
    L.new(add.outputs[0], out.inputs["Surface"])
    mat.cycles.emission_sampling = "NONE"
    mat.use_backface_culling = False
    return mat


def build_shell(name, radius=1.0, location=(0, 0, 0), color=(0.4, 0.65, 1.0), color_edge=None, strength=2.0,
                rim_power=2.0, face_floor=0.02, noise_scale=3.0, noise_amp=0.6, seed=1, segments=128,
                scale=(1.0, 1.0, 1.0), parent=None, coll="FX"):
    """Сфера радиуса radius (scale — вытянуть в эллипсоид/«каплю» гелиосферы). Возвращает объект."""
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=segments // 2, radius=1.0)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    mat = _material(f"{name}_Mat", color, color_edge, strength, rim_power, face_floor, noise_scale, noise_amp, seed)
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    C.link(ob, coll)
    ob.location = location
    ob.scale = tuple(radius * s for s in scale)
    if parent is not None:
        ob.parent = parent
    ob["shell_mat"] = mat.name
    ob["base_scale"] = list(scale)
    ob.visible_shadow = False
    ob.visible_diffuse = ob.visible_glossy = ob.visible_transmission = ob.visible_volume_scatter = False
    return ob


def build_sheet(name, size=1.0, location=(0, 0, 0), normal=(0, 0, 1), subdiv=64, bend=0.0, **kw):
    """Плоский лист (участок оболочки огромного радиуса): квадрат size×size, нормаль normal;
    bend — прогиб к краям (доля size), чтобы край уходил «за горизонт» как у сферы. kw — как у build_shell."""
    from mathutils import Vector
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=subdiv, y_segments=subdiv, size=0.5)
    for v in bm.verts:
        r2 = v.co.x ** 2 + v.co.y ** 2
        v.co.z = -bend * r2
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    keys = ("color", "color_edge", "strength", "rim_power", "face_floor", "noise_scale", "noise_amp", "seed")
    defaults = dict(color=(0.4, 0.65, 1.0), color_edge=None, strength=2.0, rim_power=2.0, face_floor=0.02,
                    noise_scale=3.0, noise_amp=0.6, seed=1)
    p = {k: kw.get(k, defaults[k]) for k in keys}
    mat = _material(f"{name}_Mat", **p)
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    C.link(ob, kw.get("coll", "FX"))
    ob.location = location
    ob.scale = (size, size, size)
    ob.rotation_mode = "QUATERNION"
    ob.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(Vector(normal).normalized())
    if kw.get("parent") is not None:
        ob.parent = kw["parent"]
    ob["shell_mat"] = mat.name
    ob.visible_shadow = False
    ob.visible_diffuse = ob.visible_glossy = ob.visible_transmission = ob.visible_volume_scatter = False
    return ob


def _ring_material(name, color, strength, fill, fill_power):
    mat, N, L, out = C.new_material(name)
    tc = N.new("ShaderNodeTexCoord")
    sep = N.new("ShaderNodeSeparateXYZ")
    L.new(tc.outputs["Object"], sep.inputs[0])
    rho = C.math_node(N, L, "SQRT", C.math_node(N, L, "ADD", C.math_node(N, L, "MULTIPLY", sep.outputs[0], sep.outputs[0]),
                                                C.math_node(N, L, "MULTIPLY", sep.outputs[1], sep.outputs[1])))
    w = N.new("ShaderNodeValue")
    w.name = w.label = "width"
    w.outputs[0].default_value = 0.01
    # линия: гаусс по (1 − ρ)/w; заливка внутри: ρ^fill_power
    x = C.math_node(N, L, "DIVIDE", C.math_node(N, L, "SUBTRACT", 1.0, rho), w.outputs[0])
    line = C.math_node(N, L, "EXPONENT", C.math_node(N, L, "MULTIPLY", C.math_node(N, L, "MULTIPLY", x, x), -1.0))
    inner = C.math_node(N, L, "MULTIPLY", C.math_node(N, L, "POWER", C.math_node(N, L, "MINIMUM", rho, 1.0), fill_power), fill)
    inside = C.math_node(N, L, "LESS_THAN", rho, 1.0)
    br = C.math_node(N, L, "ADD", line, C.math_node(N, L, "MULTIPLY", inner, inside))
    k = N.new("ShaderNodeValue")
    k.name = k.label = "strength"
    k.outputs[0].default_value = strength
    br = C.math_node(N, L, "MULTIPLY", br, k.outputs[0])
    em = N.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1.0)
    L.new(br, em.inputs["Strength"])
    tr = N.new("ShaderNodeBsdfTransparent")
    add = N.new("ShaderNodeAddShader")
    L.new(em.outputs[0], add.inputs[0])
    L.new(tr.outputs[0], add.inputs[1])
    L.new(add.outputs[0], out.inputs["Surface"])
    mat.cycles.emission_sampling = "NONE"
    return mat


def build_ring(name, cam, radius=1.0, location=(0, 0, 0), color=(0.6, 0.85, 1.0), strength=4.0, fill=0.08,
               fill_power=6.0, parent=None, coll="FX", segments=256):
    """Силуэт сферы-оболочки в виде кольца, всегда параллельного кадру (Copy Rotation от камеры): фронт света,
    граница гелиосферы на схеме. Тонкая линия (толщина в пикселях — key_ring) + слабая заливка к краю.
    Видимый радиус = radius (для близкой камеры это схема, не точная проекция сферы)."""
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, cap_tris=False, segments=segments, radius=1.06)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    mat = _ring_material(f"{name}_Mat", color, strength, fill, fill_power)
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    C.link(ob, coll)
    ob.location = location
    ob.scale = (radius,) * 3
    if parent is not None:
        ob.parent = parent
    con = ob.constraints.new("COPY_ROTATION")
    con.target = cam
    ob["shell_mat"] = mat.name
    ob.visible_shadow = False
    ob.visible_diffuse = ob.visible_glossy = ob.visible_transmission = ob.visible_volume_scatter = False
    return ob


def key_ring(ob, cam, r_of_frame, px, frame_start, frame_end, step=2):
    """Ключи радиуса (мировые ед. родителя) и толщины линии ≈ px пикселей при движении камеры."""
    from . import label as _LB
    sc = bpy.context.scene
    w = _node(ob, "width")
    for f in list(range(frame_start, frame_end + 1, step)) + [frame_end]:
        r = r_of_frame(f)
        ob.scale = (r, r, r)
        ob.keyframe_insert("scale", frame=f)
        sc.frame_set(f)
        d = (cam.matrix_world.translation - ob.matrix_world.translation).length
        rw = ob.matrix_world.to_scale()[0]
        w.default_value = max(px * d * _LB.pixel_angle(cam, sc) / max(rw, 1e-9), 1e-5)
        w.keyframe_insert("default_value", frame=f)
    anim.set_interpolation(ob, "LINEAR")
    anim.set_interpolation(bpy.data.materials[ob["shell_mat"]].node_tree, "LINEAR")
    sc.frame_set(frame_start)


def _node(ob, name):
    return bpy.data.materials[ob["shell_mat"]].node_tree.nodes[name].outputs[0]


def key_strength(ob, pairs, ipo="BEZIER"):
    """pairs [(кадр, сила)] — ключи яркости."""
    s = _node(ob, "strength")
    for f, v in pairs:
        s.default_value = v
        s.keyframe_insert("default_value", frame=f)
    anim.set_interpolation(bpy.data.materials[ob["shell_mat"]].node_tree, ipo)


def key_flow(ob, w0, w1, frame_start, frame_end):
    """Течение волокон: W шума линейно (медленная турбулентность)."""
    s = _node(ob, "flow")
    s.default_value = w0
    s.keyframe_insert("default_value", frame=frame_start)
    s.default_value = w1
    s.keyframe_insert("default_value", frame=frame_end)
    anim.linearize(bpy.data.materials[ob["shell_mat"]].node_tree)


def key_radius(ob, r_of_frame, frame_start, frame_end, step=1):
    """Ключи радиуса по функции r_of_frame(f) (расширяющийся фронт; любая нелинейная шкала времени)."""
    base = ob.get("base_scale", [1.0, 1.0, 1.0])
    for f in list(range(frame_start, frame_end + 1, step)) + [frame_end]:
        r = r_of_frame(f)
        ob.scale = tuple(r * b for b in base)
        ob.keyframe_insert("scale", frame=f)
    anim.set_interpolation(ob, "LINEAR")


def light_front_radius(t_s, c_au_per_s=1.0 / 499.004784):
    """Радиус фронта света (а.е.) через t секунд реального времени (свет проходит 1 а.е. за 499.0 с)."""
    return t_s * c_au_per_s
