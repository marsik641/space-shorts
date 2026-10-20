"""3D-подписи в кадре (названия планет, «VOYAGER 1», даты): текст всегда параллелен кадру и читается.

    from spacekit.fx import label as LB
    lb = LB.build_label("Lbl_Jupiter", "JUPITER", location=(5.2, 0, 0), cam=cam, px=34, offset_px=(0, 28))
    LB.key_screen_size(lb, cam, 1, n)          # если камера едет: ключи масштаба -> постоянный кегль в пикселях
    LB.key_fade(lb, 1.0, f_in=30, f_out=None)  # появление/исчезновение (ключи прозрачности)

Текст — FONT-объект, эмиссия + прозрачность (не освещает сцену, без теней), Copy Rotation от камеры
(плоскость текста параллельна кадру). Кегль px — высота заглавной буквы в пикселях итогового кадра
(финальное разрешение 100 %, превью pct — в тех же пропорциях). offset_px — сдвиг от точки привязки в пикселях
кадра (x вправо, y вверх).
Шрифт — .ttf из Windows (Segoe UI), если файла нет — встроенный шрифт Blender.
"""
import math
import os

import bpy
from mathutils import Vector

from .. import anim
from .. import core as C

FONT = "C:/Windows/Fonts/segoeui.ttf"
CAP_H = 0.70            # высота заглавной (в ед. size FONT-объекта) для Segoe UI ≈ 0.7


def _font(path):
    if path and os.path.exists(path):
        for f in bpy.data.fonts:
            if os.path.normcase(bpy.path.abspath(f.filepath)) == os.path.normcase(path):
                return f
        return bpy.data.fonts.load(path)
    return None


def _material(name, color, strength):
    """Эмиссия × alpha поверх полной прозрачности: появление/исчезновение — яркостью, без шума смешивания
    с Transparent BSDF (при малых сэмплах карт фейд «зернил»)."""
    mat, N, L, out = C.new_material(name)
    em = N.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1.0)
    a = N.new("ShaderNodeValue")
    a.name = a.label = "alpha"
    a.outputs[0].default_value = 1.0
    L.new(C.math_node(N, L, "MULTIPLY", a.outputs[0], strength), em.inputs["Strength"])
    tr = N.new("ShaderNodeBsdfTransparent")
    add = N.new("ShaderNodeAddShader")
    L.new(tr.outputs[0], add.inputs[0])
    L.new(em.outputs[0], add.inputs[1])
    L.new(add.outputs[0], out.inputs["Surface"])
    mat.cycles.emission_sampling = "NONE"
    return mat


def pixel_angle(cam, scene=None):
    """Угловой размер пикселя ИТОГОВОГО кадра 100 % (рад) — для объектива камеры. resolution_percentage не учитывается:
    все экранные размеры (подписи, толщины линий и колец, точки) задаются в пикселях финального кадра, и превью
    pct=50 показывает те же пропорции, что финал."""
    scene = scene or bpy.context.scene
    r = scene.render
    w, h = r.resolution_x, r.resolution_y
    big = max(w, h)
    half = math.atan(cam.data.sensor_width * 0.5 / cam.data.lens)
    return 2.0 * half / big


def build_label(name, text, location, cam, px=32.0, offset_px=(0.0, 0.0), color=(0.85, 0.9, 1.0),
                strength=3.0, font=None, align="CENTER", parent=None, coll="Labels", spacing=1.08):
    """Подпись в точке location (мир или система parent); размер — под текущее положение камеры."""
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = text
    cu.align_x = align
    cu.align_y = "CENTER"
    cu.space_character = spacing
    f = _font(font or FONT)
    if f is not None:
        cu.font = f
    ob = bpy.data.objects.new(name, cu)
    C.link(ob, coll)
    if parent is not None:
        ob.parent = parent
    anchor = C.empty(f"{name}_Anchor", coll=coll, loc=location, size=0.1)
    if parent is not None:
        anchor.parent = parent
    ob.parent = anchor
    con = ob.constraints.new("COPY_ROTATION")
    con.target = cam
    mat = _material(f"{name}_Mat", color, strength)
    cu.materials.append(mat)
    ob.visible_shadow = False
    ob.visible_diffuse = ob.visible_glossy = ob.visible_transmission = ob.visible_volume_scatter = False
    ob["label_mat"] = mat.name
    ob["px"] = float(px)
    ob["offset_px"] = list(offset_px)
    _apply_size(ob, cam, bpy.context.scene.frame_current)
    return ob


def _apply_size(ob, cam, frame, insert=False):
    """Масштаб и сдвиг подписи под расстояние до камеры в кадре frame."""
    sc = bpy.context.scene
    sc.frame_set(frame)
    anchor = ob.parent
    dist = (cam.matrix_world.translation - anchor.matrix_world.translation).length
    pa = pixel_angle(cam, sc)
    unit = dist * pa                                   # мир на 1 пиксель на этом расстоянии
    size = ob["px"] * unit / CAP_H / max(anchor.matrix_world.to_scale()[0], 1e-12)   # родитель может быть масштабирован
    ob.data.size = 1.0
    ob.scale = (size, size, size)
    # сдвиг в плоскости кадра: оси камеры
    rot = cam.matrix_world.to_3x3()
    ox, oy = ob["offset_px"]
    off_w = (rot @ Vector((1, 0, 0))) * ox * unit + (rot @ Vector((0, 1, 0))) * oy * unit
    inv = anchor.matrix_world.to_3x3().inverted()
    ob.location = inv @ off_w
    if insert:
        ob.keyframe_insert("scale", frame=frame)
        ob.keyframe_insert("location", frame=frame)


def key_screen_size(ob, cam, frame_start, frame_end, step=4):
    """Ключи масштаба/сдвига каждые step кадров: постоянный кегль при движении камеры."""
    for f in list(range(frame_start, frame_end + 1, step)) + [frame_end]:
        _apply_size(ob, cam, f, insert=True)
    anim.set_interpolation(ob, "LINEAR")
    bpy.context.scene.frame_set(frame_start)


def key_fade(ob, peak=1.0, f_in=None, f_out=None, length=20):
    """Появление (f_in..f_in+length) и/или исчезновение (f_out..f_out+length) ключами alpha."""
    mat = bpy.data.materials[ob["label_mat"]]
    s = mat.node_tree.nodes["alpha"].outputs[0]
    if f_in is not None:
        s.default_value = 0.0
        s.keyframe_insert("default_value", frame=f_in)
        s.default_value = peak
        s.keyframe_insert("default_value", frame=f_in + length)
    if f_out is not None:
        s.default_value = peak
        s.keyframe_insert("default_value", frame=f_out)
        s.default_value = 0.0
        s.keyframe_insert("default_value", frame=f_out + length)
    anim.set_interpolation(mat.node_tree, "BEZIER")
