"""Оформление канала из сцен spacekit: аватар 800×800 и баннер 2560×1440 (с названием и слоганом).

    blender -b --factory-startup -P tools/brand.py -- avatar|plate|banner [--name "Neutron Frames"] [--tagline "..."]

avatar — крупный план пульсара (лучи по диагонали, читается в круге 48 px) -> out/brand/avatar_800.png
plate  — подложка баннера: пульсар, пылевое кольцо, планеты; композиция по центру безопасной зоны 1546×423
banner — plate + текст (VSE): название и слоган в безопасной зоне -> out/brand/banner_2560x1440.png
Перед запуском: GPU свободен (нет out/RENDER.lock и blender.exe).
"""
import math
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "episodes", "ep001_psr_b1257"))

import bpy
from mathutils import Euler, Vector

from spacekit import camera as CAM
from spacekit import core as C
from spacekit import render as R
from spacekit import shot as S
from spacekit import sky as SKY
from spacekit.bodies import neutron_star as NS
from spacekit.fx import dust_ring as DR

OUT = os.path.join(C.OUT, "brand")


def _arg(name, default):
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return a[a.index(name) + 1] if name in a else default


def _size(sc, w, h):
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, 100


def avatar():
    S.OPT.update(fmt="16x9", fps=30, pct=100)
    sc = S.base_scene(2, exposure=0.0, samples=128, bloom_strength=0.7)
    _size(sc, 800, 800)
    sc.render.use_motion_blur = False
    tilt = Euler((0.0, math.radians(90.0), math.radians(-35.0)))   # лучи по диагонали квадрата
    cam, tgt = CAM.camera_rig("Cam_Avatar", lens=50)
    loc = tuple(tilt.to_matrix() @ Vector(CAM.sph(9.5, 0, 14)))      # сбоку от магнитной оси: лучи видны целиком
    CAM.key_camera(cam, tgt, [dict(frame=1, loc=loc, target=(0, 0, 0), lens=50)])
    stars = SKY.build_sky(sc, cam, 0.0, mw_strength=0.2, star_brightness=0.6,
                          gal=SKY.gal_for_view(-Vector(loc), tilt_deg=40, l_center_deg=120))
    psr = NS.build_pulsar(sc, tilt_euler=tilt, R=1.0, alpha_deg=60.0, spin_hz=0.0, frame_start=1, frame_end=2,
                          beam_length=30, beam_half_angle_deg=9, detail="close", field_lines=True,
                          particles=False, surface_strength=2.2, field_strength=2.0)
    S.finish(sc, stars, star_samples=32)
    os.makedirs(OUT, exist_ok=True)
    R.render_still(os.path.join(OUT, "avatar_800.png"), frame=1)


def plate():
    from system import ALPHA, RING, system_planets
    S.OPT.update(fmt="16x9", fps=30, pct=100)
    sc = S.base_scene(2, exposure=0.6, samples=96, bloom_strength=0.8)
    _size(sc, 2560, 1440)
    sc.render.use_motion_blur = False
    cam, tgt = CAM.camera_rig("Cam_Banner", lens=50)
    loc = CAM.sph(230, -82, 17)
    # цель правее центра системы: пульсар уходит влево, справа — место под текст
    CAM.key_camera(cam, tgt, [dict(frame=1, loc=loc, target=(38, 0, -2), lens=50)])
    stars = SKY.build_sky(sc, cam, 0.6, mw_strength=0.35,
                          gal=SKY.gal_for_view(-Vector(loc), tilt_deg=-55, l_center_deg=70))
    # фаза: ось луча поперёк взгляда (азимут луча = −90° + phase0 ≈ азимут камеры + 90°)
    psr = NS.build_pulsar(sc, R=0.3, alpha_deg=ALPHA, spin_hz=0.6, phase0_deg=98.0, frame_start=1, frame_end=2,
                          beam_length=110, beam_half_angle_deg=8, detail="far", light_energy=20000.0,
                          spot_energy=60000.0, beam_intensity=3.5, field_lines=False, particles=False)
    system_planets(sc, psr, 2, {"draugr": 160, "poltergeist": 25, "phobetor": 140})
    DR.build_dust_ring(sc, parent=psr["root"], ring_radiance=3.0, anisotropy=0.3, arc_gain=4.0,
                       frame_start=1, frame_end=2, lights=[psr["light"]] + list(psr["spots"]), **RING)
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
    # безопасная зона 1546×423 по центру: y 0.353..0.647, x 0.198..0.802 — текст справа от пульсара
    for i, (txt, size, y, f) in enumerate(((name, 110, 0.535, "t"), (tagline, 44, 0.455, "s"), (sub, 30, 0.405, "s"))):
        ts = sed.strips.new_effect(f"t{i}", "TEXT", channel=2 + i, frame_start=1, length=1)
        ts.text, ts.font_size, ts.location = txt, size, (0.79, y)
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
        banner(_arg("--name", "Neutron Frames"), _arg("--tagline", "Real objects. Real numbers. Rendered."),
               _arg("--sub", "New Shorts weekly · data-driven space visualizations"))
