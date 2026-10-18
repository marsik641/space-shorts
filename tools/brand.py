"""Оформление канала Orbitfall из сцен spacekit: аватар 800×800 и баннер 2560×1440.

    blender -b --factory-startup -P tools/brand.py -- avatar|plate|banner [--name ORBITFALL] [--tagline "..."] [--sub "..."]

Мотив «Orbitfall»: серп планеты в контровом свете далёкой звезды, светящаяся орбита со следом и
спутник на ней — «падение по орбите». Ничего не завязано на конкретный объект (канал — про весь космос).
avatar — крупный план, читается в круге 48 px -> out/brand/avatar_800.png
plate  — широкая подложка баннера (планета слева, орбиты уходят вправо) -> out/brand/banner_plate.png
banner — plate + текст (VSE) в безопасной зоне 1546×423 -> out/brand/banner_2560x1440.png
Перед запуском: GPU свободен (нет out/RENDER.lock и blender.exe).
"""
import math
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO)

import bpy
from mathutils import Euler, Vector

from spacekit import camera as CAM
from spacekit import core as C
from spacekit import lighting as LT
from spacekit import render as R
from spacekit import shot as S
from spacekit import sky as SKY
from spacekit.bodies import planets as PL
from spacekit.fx import orbit_line as OL

OUT = os.path.join(C.OUT, "brand")
STAR_TEMP = 5600.0                # жёлто-белая звезда: «обычный» космос, не пульсар


def _arg(name, default):
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return a[a.index(name) + 1] if name in a else default


def _size(sc, w, h):
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, 100


def _star(loc, radius, energy):
    """Далёкая звезда: светящийся диск (камера) + точечный свет (планета)."""
    me = bpy.data.meshes.new("Star")
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=radius)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("Star", me)
    C.link(ob, "Lights")
    ob.location = loc
    ob.visible_shadow = False
    mat, N, L, out = C.new_material("StarMat")
    em = N.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*LT.blackbody_rgb(STAR_TEMP), 1.0)
    em.inputs["Strength"].default_value = 60.0
    L.new(em.outputs[0], out.inputs["Surface"])
    me.materials.append(mat)
    return LT.add_point_star("StarLight", energy, STAR_TEMP, radius=radius, location=loc)


def _scene(w, h, exposure, samples):
    S.OPT.update(fmt="16x9", fps=30, pct=100)
    sc = S.base_scene(2, exposure=exposure, samples=samples, bloom_strength=0.9)
    _size(sc, w, h)
    sc.render.use_motion_blur = False
    return sc


def _orbit_with_moon(name, a, incl, node, head_deg, trail_len, strength, moon_r, light, width=None):
    rot = Euler((math.radians(incl), 0.0, math.radians(node)), "YXZ").to_matrix()
    OL.build_orbit_line(name, a=a, incl_deg=incl, node_deg=node, width=width or 0.0045 * a, strength=strength,
                        trail_head_deg=head_deg, trail_len_deg=trail_len)
    if moon_r > 0:
        p = rot @ Vector(OL.point_on_orbit(a, 0.0, head_deg))
        PL.build_planet(bpy.context.scene, "draugr", radius=moon_r, location=tuple(p), detail="far",
                        seed=3, frame_start=1, frame_end=2, light=light, name=f"{name}_Moon")


def avatar():
    sc = _scene(800, 800, exposure=0.3, samples=128)
    star_dir = Vector((0.55, 1.0, 0.42)).normalized()
    d_star = 90.0
    light = _star(tuple(star_dir * d_star), 0.9, LT.point_energy_for(5.0, d_star))
    PL.build_planet(sc, "phobetor", radius=1.0, detail="close", seed=5, axial_tilt_deg=15,
                    frame_start=1, frame_end=2, aurora_strength=0.0, light=light)
    _orbit_with_moon("Orbit_A", 1.75, incl=17, node=-22, head_deg=-35, trail_len=250, strength=7.0,
                     moon_r=0.085, light=light)
    cam, tgt = CAM.camera_rig("Cam_Avatar", lens=50)
    loc = (0.15, -5.4, 0.75)
    CAM.key_camera(cam, tgt, [dict(frame=1, loc=loc, target=(0.05, 0, 0.12), lens=50)])
    stars = SKY.build_sky(sc, cam, 0.3, mw_strength=0.25, star_brightness=0.7,
                          gal=SKY.gal_for_view((0.2, 1.0, 0.1), tilt_deg=-40, l_center_deg=100))
    S.finish(sc, stars, star_samples=32)
    os.makedirs(OUT, exist_ok=True)
    R.render_still(os.path.join(OUT, "avatar_800.png"), frame=1)


def plate():
    sc = _scene(2560, 1440, exposure=0.35, samples=96)
    star_dir = Vector((-0.35, 1.0, 0.38)).normalized()
    d_star = 90.0
    light = _star(tuple(star_dir * d_star), 1.1, LT.point_energy_for(5.0, d_star))
    PL.build_planet(sc, "phobetor", radius=1.0, detail="close", seed=5, axial_tilt_deg=15,
                    frame_start=1, frame_end=2, aurora_strength=0.0, light=light)
    _orbit_with_moon("Orbit_A", 1.6, incl=14, node=-18, head_deg=-40, trail_len=240, strength=7.0,
                     moon_r=0.06, light=light, width=0.0065)
    _orbit_with_moon("Orbit_B", 2.15, incl=10, node=-8, head_deg=-95, trail_len=200, strength=5.0,
                     moon_r=0.04, light=light, width=0.005)
    cam, tgt = CAM.camera_rig("Cam_Banner", lens=35)
    loc = (0.7, -8.4, 0.95)
    # цель правее планеты: планета с орбитами слева, справа — чистое небо под текст в безопасной зоне
    CAM.key_camera(cam, tgt, [dict(frame=1, loc=loc, target=(2.35, 0, 0.05), lens=35)])
    stars = SKY.build_sky(sc, cam, 0.35, mw_strength=0.35, star_brightness=0.8,
                          gal=SKY.gal_for_view((0.45, 1.0, 0.05), tilt_deg=-28, l_center_deg=70))
    S.finish(sc, stars, star_samples=48)
    os.makedirs(OUT, exist_ok=True)
    R.render_still(os.path.join(OUT, "banner_plate.png"), frame=1)


def banner(name, tagline, sub):
    """Подложка + текст через VSE (без повторного тонмаппинга)."""
    sc = bpy.context.scene
    _size(sc, 2560, 1440)
    sc.view_settings.view_transform = "Standard"
    sed = sc.sequence_editor_create()
    sed.strips.new_image("plate", os.path.join(OUT, "banner_plate.png"), channel=1, frame_start=1, fit_method="FIT")
    fonts = {"t": "C:/Windows/Fonts/segoeuisl.ttf", "s": "C:/Windows/Fonts/segoeui.ttf"}
    # безопасная зона 1546×423 по центру: y 0.353..0.647, x 0.198..0.802 — текст справа
    for i, (txt, size, y, f) in enumerate(((name, 120, 0.545, "t"), (tagline, 44, 0.46, "s"), (sub, 30, 0.408, "s"))):
        ts = sed.strips.new_effect(f"t{i}", "TEXT", channel=2 + i, frame_start=1, length=1)
        ts.text, ts.font_size, ts.location = txt, size, (0.795, y)
        ts.alignment_x = ts.anchor_x = "RIGHT"
        ts.anchor_y = "CENTER"
        ts.color = (0.93, 0.95, 1.0, 1.0)
        ts.use_shadow, ts.shadow_color, ts.shadow_blur = True, (0, 0, 0, 0.7), 0.7
        if os.path.exists(fonts[f]):
            ts.font = bpy.data.fonts.load(fonts[f], check_existing=True)
        ts.blend_type = "ALPHA_OVER"
    sc.frame_start = sc.frame_end = 1
    sc.render.use_sequencer, sc.render.use_compositing = True, False
    sc.render.image_settings.media_type = "IMAGE"
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = os.path.join(OUT, "banner_2560x1440.png")
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    mode = (sys.argv[sys.argv.index("--") + 1:] or ["avatar"])[0]
    if mode == "avatar":
        avatar()
    elif mode == "plate":
        plate()
    elif mode == "banner":
        banner(_arg("--name", "ORBITFALL"), _arg("--tagline", "Real objects. Real numbers. Rendered."),
               _arg("--sub", "Cinematic space visualizations · new Shorts every week"))
