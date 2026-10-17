"""Анимация ключами (без драйверов — в фоне без autoexec они не исполняются).

Blender 5: у action слоты/слои/каналбэги — f-кривые берём через fcurves(), а не action.fcurves.
"""
import math

from . import core as C


def fcurves(id_data):
    """Все f-кривые action у id_data (объект, данные камеры, дерево узлов...)."""
    ad = getattr(id_data, "animation_data", None)
    if ad is None or ad.action is None:
        return []
    act = ad.action
    if hasattr(act, "fcurves") and len(getattr(act, "fcurves", [])):
        return list(act.fcurves)
    out = []
    for layer in getattr(act, "layers", []):
        for strip in layer.strips:
            for cb in getattr(strip, "channelbags", []):
                out.extend(cb.fcurves)
    return out


def set_interpolation(id_data, ipo="LINEAR", extrapolate=None, path_contains=None, handles="AUTO_CLAMPED"):
    """Интерполяция всех ключей (LINEAR — равномерные вращения/орбиты, BEZIER — операторский ход);
    extrapolate='LINEAR'|'CONSTANT' — поведение за пределами ключей."""
    for fc in fcurves(id_data):
        if path_contains and path_contains not in fc.data_path:
            continue
        if extrapolate:
            fc.extrapolation = extrapolate
        for kp in fc.keyframe_points:
            kp.interpolation = ipo
            if ipo == "BEZIER":
                kp.handle_left_type = kp.handle_right_type = handles
        fc.update()


def linearize(id_data, extrapolate=True, path_contains=None):
    set_interpolation(id_data, "LINEAR", "LINEAR" if extrapolate else None, path_contains)


def ease(id_data):
    set_interpolation(id_data, "BEZIER")


def key_rot_z(ob, z0, deg_per_s, frame_start, frame_end, scene=None):
    """Равномерное вращение вокруг локальной Z: два ключа LINEAR + линейная экстраполяция (fps — из сцены)."""
    fps = C.scene_fps(scene)
    ob.rotation_euler[2] = z0
    ob.keyframe_insert("rotation_euler", index=2, frame=frame_start)
    ob.rotation_euler[2] = z0 + math.radians(deg_per_s * (frame_end - frame_start) / fps)
    ob.keyframe_insert("rotation_euler", index=2, frame=frame_end)
    linearize(ob)


def key_value_node(node, v0, v1, frame_start, frame_end):
    """Ключи выхода Value-узла (время для шейдеров): LINEAR с экстраполяцией."""
    s = node.outputs[0]
    s.default_value = v0
    s.keyframe_insert("default_value", frame=frame_start)
    s.default_value = v1
    s.keyframe_insert("default_value", frame=frame_end)
