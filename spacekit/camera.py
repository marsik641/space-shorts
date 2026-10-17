"""Камера: rig «камера + цель» (Track To), ключи пути, кадрирование.

Ход камеры — ключи положения камеры и цели с BEZIER (auto-clamped): мягкий операторский ход
и корректный motion blur. Bezier-экстраполяция постоянная: после последнего ключа камера стоит.
"""
import math

import bpy
from mathutils import Vector

from . import anim
from . import core as C


def sph(dist, az_deg, el_deg, center=(0, 0, 0)):
    """Точка в сферических координатах вокруг center: азимут от +X против часовой, возвышение над XY."""
    az, el = math.radians(az_deg), math.radians(el_deg)
    return tuple(c + v for c, v in zip(center, (dist * math.cos(el) * math.cos(az),
                                                 dist * math.cos(el) * math.sin(az),
                                                 dist * math.sin(el))))


def point_at(ob, target, up="Y"):
    d = Vector(target) - ob.location
    ob.rotation_mode = "XYZ"
    ob.rotation_euler = d.to_track_quat("-Z", up).to_euler()


def camera(name="Cam", loc=(0, -10, 0), look_at=(0, 0, 0), lens=35.0, coll="Cameras", clip_end=1.0e6):
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cd.clip_start = 0.01
    cd.clip_end = clip_end
    cd.sensor_width = 36.0
    ob = bpy.data.objects.new(name, cd)
    C.link(ob, coll)
    ob.location = loc
    point_at(ob, look_at)
    bpy.context.scene.camera = ob
    return ob


def camera_rig(name="Cam", lens=35.0, clip_start=0.05, clip_end=1.0e6, sensor_fit="AUTO"):
    """Камера + цель. Возвращает (cam, target). sensor_width 36 мм: фокусное — по БОЛЬШЕЙ стороне кадра
    (в вертикальном 9:16 35 мм дают тот же угол по высоте, что в 16:9 по ширине)."""
    tgt = C.empty(f"{name}_Target", coll="Cameras", display="SPHERE", size=0.5)
    cam = camera(name, loc=(0, -10, 0), look_at=(0, 0, 0), lens=lens)
    cam.data.clip_start = clip_start
    cam.data.clip_end = clip_end
    cam.data.sensor_fit = sensor_fit
    con = cam.constraints.new("TRACK_TO")
    con.target = tgt
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    return cam, tgt


def key_camera(cam, tgt, keys, ipo="BEZIER"):
    """keys: [{frame, loc, target, lens?}] — ключи положения камеры, цели и фокусного."""
    for k in keys:
        f = k["frame"]
        cam.location = k["loc"]
        cam.keyframe_insert("location", frame=f)
        tgt.location = k["target"]
        tgt.keyframe_insert("location", frame=f)
        if "lens" in k:
            cam.data.lens = k["lens"]
            cam.data.keyframe_insert("lens", frame=f)
    for idd in (cam, tgt, cam.data):
        anim.set_interpolation(idd, ipo)


def look_dir(cam_loc, target):
    return (Vector(target) - Vector(cam_loc)).normalized()


def frame_two_subjects(subject_far, phase_deg, dist, up_deg, w_near=0.56, drop_deg=3.0, center=(0, 0, 0)):
    """Камера у тела в center, под фазовым углом phase_deg к далёкому объекту subject_far (звезде):
    тело с одной стороны кадра, звезда — с другой; взгляд — на «биссектрису» с весом w_near на тело.
    phase 180° — тело точно между камерой и звездой (тонкий серп), 90° — полуфаза.
    Угол между телом и звездой в кадре ≈ 180° − phase: подбирать объектив, чтобы оба влезли.
    Возвращает (dict(loc, target) для key_camera, вектор взгляда)."""
    ctr = Vector(center)
    u = (Vector(subject_far) - ctr).normalized()
    z = Vector((0, 0, 1))
    side = u.cross(z).normalized()
    upv = side.cross(u).normalized()
    e = math.radians(up_deg)
    v = (-side * math.cos(e) + upv * math.sin(e)).normalized()
    ph = math.radians(phase_deg)
    c = ctr + (u * math.cos(ph) + v * math.sin(ph)) * dist
    dp = (ctr - c).normalized()
    dq = (Vector(subject_far) - c).normalized()
    look = (dp * w_near + dq * (1.0 - w_near)).normalized()
    look = (look - z * math.sin(math.radians(drop_deg))).normalized()
    return dict(loc=tuple(c), target=tuple(c + look * 10.0)), look


def tilt_for_target(src_loc, target, alpha_deg):
    """Ориентация оси вращения (Euler для root пульсара), при которой луч с углом alpha к оси
    раз за оборот проходит точно через target; ось — максимально близко к мировой Z."""
    u = (Vector(target) - Vector(src_loc)).normalized()
    z = Vector((0, 0, 1))
    w = (z - u * z.dot(u)).normalized()
    a = math.radians(alpha_deg)
    s = (u * math.cos(a) + w * math.sin(a)).normalized()
    return z.rotation_difference(s).to_euler()
