"""Оформление канала The Universe Inside Out из сцен spacekit: аватар 800×800 и баннер 2560×1440.

    blender -b --factory-startup -P tools/brand.py -- avatar|plate|banner [--name "THE UNIVERSE|INSIDE OUT"]
        [--tagline "..."] [--sub "..."]

Мотив «наизнанку»: каменная планета в контровом свете далёкой звезды, из неё вырезан сектор (октант),
в разрезе светятся слои — кора, мантия, внешнее и внутреннее ядро. Ничего не завязано на конкретный объект
(канал — про весь космос); в круге 48 px читается как тёмный диск с ярким клином.
avatar — крупный план -> out/brand/avatar_800.png
plate  — широкая подложка баннера (планета слева, справа небо под текст) -> out/brand/banner_plate.png
banner — plate + текст (VSE) в безопасной зоне 1546×423 -> out/brand/banner_2560x1440.png;
         «|» в --name — перенос строки
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


def _scene(w, h, exposure, samples, bloom=0.9):
    S.OPT.update(fmt="16x9", fps=30, pct=100)
    sc = S.base_scene(2, exposure=exposure, samples=samples, bloom_strength=bloom)
    _size(sc, w, h)
    sc.render.use_motion_blur = False
    return sc


# слои в разрезе: (r/R, цвет, яркость эмиссии) — кора, мантия, внешнее ядро, внутреннее ядро
LAYERS = ((1.00, (0.09, 0.09, 0.10), 0.0), (0.92, (0.09, 0.09, 0.10), 0.0), (0.90, (0.45, 0.05, 0.015), 0.12),
          (0.60, (0.80, 0.12, 0.02), 0.35), (0.57, (1.00, 0.35, 0.05), 1.0), (0.34, (1.00, 0.50, 0.10), 1.6),
          (0.31, (1.00, 0.80, 0.45), 3.0), (0.0, (1.00, 0.93, 0.80), 4.0))


def _cut_material(R):
    """Материал среза: слои по расстоянию от центра планеты (планета в начале координат)."""
    mat, N, L, out = C.new_material("CutLayers")
    geo = N.new("ShaderNodeNewGeometry")
    ln = N.new("ShaderNodeVectorMath")
    ln.operation = "LENGTH"
    L.new(geo.outputs["Position"], ln.inputs[0])
    div = N.new("ShaderNodeMath")
    div.operation = "DIVIDE"
    div.inputs[1].default_value = R
    L.new(ln.outputs["Value"], div.inputs[0])
    col = N.new("ShaderNodeValToRGB")
    stg = N.new("ShaderNodeValToRGB")
    pts = sorted(LAYERS, key=lambda t: t[0])
    for ramp, val in ((col, lambda t: (*t[1], 1.0)), (stg, lambda t: (t[2] / 4.0,) * 3 + (1.0,))):
        el = ramp.color_ramp.elements
        el[0].position, el[0].color = pts[0][0], val(pts[0])
        el[1].position, el[1].color = pts[1][0], val(pts[1])
        for t in pts[2:]:
            e = el.new(t[0])
            e.color = val(t)
        ramp.color_ramp.interpolation = "LINEAR"
        L.new(div.outputs[0], ramp.inputs["Fac"])
    sx = N.new("ShaderNodeSeparateColor")
    L.new(stg.outputs["Color"], sx.inputs[0])
    # грани разреза (нормали +X, −Y, +Z) — разной яркости, чтобы клин читался объёмным
    dot = N.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    dot.inputs[1].default_value = tuple(Vector((0.2, -1.0, 0.6)).normalized())
    L.new(geo.outputs["Normal"], dot.inputs[0])
    shade = N.new("ShaderNodeMath")
    shade.operation = "MULTIPLY_ADD"
    shade.inputs[1].default_value, shade.inputs[2].default_value = 0.6 * 4.0, 0.45 * 4.0
    L.new(dot.outputs["Value"], shade.inputs[0])
    k = N.new("ShaderNodeMath")
    k.operation = "MULTIPLY"
    L.new(sx.outputs[0], k.inputs[0])
    L.new(shade.outputs[0], k.inputs[1])
    em = N.new("ShaderNodeEmission")
    L.new(col.outputs["Color"], em.inputs["Color"])
    L.new(k.outputs[0], em.inputs["Strength"])
    dif = N.new("ShaderNodeBsdfDiffuse")
    L.new(col.outputs["Color"], dif.inputs["Color"])
    add = N.new("ShaderNodeAddShader")
    L.new(dif.outputs[0], add.inputs[0])
    L.new(em.outputs[0], add.inputs[1])
    L.new(add.outputs[0], out.inputs["Surface"])
    return mat


def _cutaway_planet(sc, light, R=1.0, kind="frostrock", seed=5):
    """Планета с вырезанным октантом x>0, y<0, z>0 (к камере, вверх-вправо); срез — материал слоёв."""
    pl = PL.build_planet(sc, kind, radius=R, detail="close", seed=seed, axial_tilt_deg=0.0,
                         frame_start=1, frame_end=2, aurora_strength=0.0, light=light)
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=(1.5 * R, -1.5 * R, 1.5 * R))
    cut = bpy.context.active_object
    cut.name = "Cutter"
    cut.scale = (1.5 * R, 1.5 * R, 1.5 * R)
    cut.data.materials.append(_cut_material(R))
    cut.hide_render = True
    body = pl["planet"]
    m = body.modifiers.new("Cutaway", "BOOLEAN")
    m.operation, m.solver, m.object = "DIFFERENCE", "EXACT", cut
    m.material_mode = "TRANSFER"
    return pl


def avatar():
    sc = _scene(800, 800, exposure=0.3, samples=128, bloom=0.3)
    star_dir = Vector((-0.6, 0.85, 0.45)).normalized()   # сзади-слева: серп слева, разрез справа
    d_star = 90.0
    light = _star(tuple(star_dir * d_star), 0.9, LT.point_energy_for(5.0, d_star))
    _cutaway_planet(sc, light)
    cam, tgt = CAM.camera_rig("Cam_Avatar", lens=50)
    CAM.key_camera(cam, tgt, [dict(frame=1, loc=(1.25, -3.65, 2.05), target=(0.05, 0.0, -0.08), lens=50)])
    stars = SKY.build_sky(sc, cam, 0.3, mw_strength=0.25, star_brightness=0.7,
                          gal=SKY.gal_for_view((0.2, 1.0, 0.1), tilt_deg=-40, l_center_deg=100))
    S.finish(sc, stars, star_samples=32)
    os.makedirs(OUT, exist_ok=True)
    R.render_still(os.path.join(OUT, "avatar_800.png"), frame=1)


def plate():
    sc = _scene(2560, 1440, exposure=0.35, samples=96, bloom=0.3)
    star_dir = Vector((-0.7, 0.75, 0.4)).normalized()
    d_star = 90.0
    light = _star(tuple(star_dir * d_star), 1.1, LT.point_energy_for(5.0, d_star))
    _cutaway_planet(sc, light)
    cam, tgt = CAM.camera_rig("Cam_Banner", lens=35)
    # планета — в левой части безопасной зоны (видна и на телефоне), справа — небо под текст
    CAM.key_camera(cam, tgt, [dict(frame=1, loc=(2.92, -10.82, 4.82), target=(2.51, 0.38, 0.0), lens=35)])
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
    lines = [(t, 96, 0.598 - 0.072 * k, "t") for k, t in enumerate(name.split("|"))]
    lines += [(tagline, 42, lines[-1][2] - 0.075, "s"), (sub, 29, lines[-1][2] - 0.122, "s")]
    for i, (txt, size, y, f) in enumerate(lines):
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
        banner(_arg("--name", "THE UNIVERSE|INSIDE OUT"),
               _arg("--tagline", "Real objects. Real numbers. Turned inside out."),
               _arg("--sub", "Cinematic space visualizations · a new Short every day"))
