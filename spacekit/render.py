"""Рендер: форматы кадра, Cycles/OptiX, цвет (AgX), компоузер (блум), слой звёзд, денойз, вывод кадров.

Форматы: FORMATS["16x9"] = 1920×1080, FORMATS["9x16"] = 1080×1920 (Shorts). fps задаётся в setup_cycles(fps=...)
или core.reset_scene(fps=...); все модули берут fps из сцены.
"""
import os

import bpy

from . import core as C

RES = (1920, 1080)
FORMATS = {"16x9": (1920, 1080), "9x16": (1080, 1920)}


def setup_cycles(scene=None, samples=64, res=RES, pct=100, motion_blur=True, shutter=0.5,
                 denoise=True, adaptive_threshold=0.02, fps=None):
    scene = scene or bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.render.compositor_device = "GPU"      # блум 2 Мпикс на CPU стоит ~1 с/кадр
    if fps is not None:
        scene.render.fps, scene.render.fps_base = int(fps), 1.0
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = d.type == "OPTIX"
    cy = scene.cycles
    cy.device = "GPU"
    cy.samples = samples
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = adaptive_threshold
    cy.use_denoising = denoise
    if denoise:
        cy.denoiser = "OPTIX"
    cy.max_bounces = 4
    cy.diffuse_bounces = 2
    cy.glossy_bounces = 2
    cy.transmission_bounces = 4
    cy.transparent_max_bounces = 16
    cy.volume_bounces = 0
    cy.film_exposure = 1.0
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.resolution_percentage = pct
    scene.render.use_motion_blur = motion_blur
    scene.render.motion_blur_shutter = shutter
    scene.render.film_transparent = False
    return scene


def setup_color(scene=None, exposure=0.0, look="None", view="AgX"):
    scene = scene or bpy.context.scene
    vs = scene.view_settings
    vs.view_transform = view
    try:
        vs.look = look
    except TypeError:
        pass
    vs.exposure = exposure
    vs.gamma = 1.0
    scene.display_settings.display_device = "sRGB"


def setup_compositor(scene=None, bloom_strength=0.6, bloom_size=0.6, bloom_threshold=1.0,
                     fog_strength=0.25, dispersion=0.012):
    """Блум (Bloom) + мягкое гало (Fog Glow) + лёгкая хроматическая аберрация."""
    scene = scene or bpy.context.scene
    ng = bpy.data.node_groups.new(f"Comp_{scene.name}", "CompositorNodeTree")
    ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    scene.compositing_node_group = ng
    N, L = ng.nodes, ng.links
    rl = N.new("CompositorNodeRLayers"); rl.location = (-600, 0); rl.scene = scene
    g1 = N.new("CompositorNodeGlare"); g1.location = (-350, 0)
    g1.inputs["Type"].default_value = "Bloom"
    g1.inputs["Quality"].default_value = "High"
    g1.inputs["Threshold"].default_value = bloom_threshold
    g1.inputs["Strength"].default_value = bloom_strength
    g1.inputs["Size"].default_value = bloom_size
    g2 = N.new("CompositorNodeGlare"); g2.location = (-100, 0)
    g2.inputs["Type"].default_value = "Fog Glow"
    g2.inputs["Quality"].default_value = "High"
    g2.inputs["Threshold"].default_value = bloom_threshold * 2.0
    g2.inputs["Strength"].default_value = fog_strength
    g2.inputs["Size"].default_value = 0.8
    ld = N.new("CompositorNodeLensdist"); ld.location = (150, 0)
    ld.inputs["Dispersion"].default_value = dispersion
    ld.inputs["Distortion"].default_value = 0.0
    out = N.new("NodeGroupOutput"); out.location = (400, 0)
    L.new(rl.outputs["Image"], g1.inputs["Image"])
    L.new(g1.outputs[0], g2.inputs["Image"])
    L.new(g2.outputs[0], ld.inputs["Image"])
    L.new(ld.outputs[0], out.inputs[0])
    return ng


def render_still(path, frame=None, scene=None, pct=None):
    scene = scene or bpy.context.scene
    if frame is not None:
        scene.frame_set(frame)
    if pct is not None:
        scene.render.resolution_percentage = pct
    scene.render.image_settings.media_type = "IMAGE"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_depth = "8"
    scene.render.filepath = os.path.abspath(path)
    bpy.ops.render.render(write_still=True)
    return path


def render_sequence(out_dir, frame_start, frame_end, scene=None, step=1):
    """Рендер PNG-секвенции out_dir/####.png; уже готовые кадры пропускаются (докачка)."""
    scene = scene or bpy.context.scene
    os.makedirs(out_dir, exist_ok=True)
    r = scene.render
    r.image_settings.media_type = "IMAGE"
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGB"
    r.image_settings.color_depth = "8"
    r.use_overwrite = False
    r.use_persistent_data = True               # BVH/шейдеры между кадрами не пересобираются
    r.use_placeholder = True
    r.use_file_extension = True
    r.filepath = os.path.join(os.path.abspath(out_dir), "####")
    # 0-байтные плейсхолдеры от прерванного рендера иначе считаются готовыми кадрами и пропускаются
    for f in os.listdir(out_dir):
        p = os.path.join(out_dir, f)
        if f.lower().endswith(".png") and os.path.getsize(p) == 0:
            os.remove(p)
    scene.frame_start, scene.frame_end, scene.frame_step = frame_start, frame_end, step
    bpy.ops.render.render(animation=True)


# ---------------------------------------------------------------- денойз и слой звёзд
def setup_volume_denoise(scene, mode="far"):
    """Денойз под шот (настройки общие на сцену — выбирать по шоту):
      'close' — S2 (лучи на пол-кадра): OptiX только по RGB. С albedo+normal в эмиссионных объёмах
                остаются пятна зерна (проверено 1080p/64 спп, в т.ч. с volume_biased). Цена — слабые
                звёзды частично съедаются (≈−30% звёзд >0.05), в крупном плане их перекрывают лучи.
      'far'   — S1/S3/S4: albedo+normal (звёзды и мелкие текстуры планет целы) + volume_biased
                (ray marching): тонкие лучи без зерна. volume_biased действует и на пылевое кольцо.
    Можно передать и сырой режим Cycles ('RGB', 'RGB_ALBEDO_NORMAL', ...). Возвращает режим."""
    cy = scene.cycles
    if mode == "close":
        cy.denoising_input_passes = "RGB"
    elif mode == "far":
        cy.denoising_input_passes = "RGB_ALBEDO_NORMAL"
        cy.volume_biased = True
    else:
        cy.denoising_input_passes = mode
    return mode


def _volume_only(ob):
    """Все материалы объекта — только Volume (Surface не подключён)."""
    mats = [m for m in ob.data.materials if m is not None]
    if not mats:
        return False
    for m in mats:
        if not m.use_nodes:
            return False
        outs = [n for n in m.node_tree.nodes if n.bl_idname == "ShaderNodeOutputMaterial"]
        if not outs or any(o.inputs["Surface"].is_linked or not o.inputs["Volume"].is_linked for o in outs):
            return False
    return True


def setup_star_layer(scene, stars, samples=16, coll_name="StarLayer", layer_name="Stars"):
    """Звёзды — отдельным view layer без денойза, сложение (Add) с основным слоем ДО блума.
    Тогда основной слой можно денойзить только по RGB (чистые лучи), а звёзды не съедаются.

    stars — объект(ы) звёзд (переносятся в коллекцию coll_name). В слое звёзд остальные коллекции —
    holdout (планеты/звезда заслоняют звёзды), фон (world) выключен, samples — свои.
    Объёмная эмиссия holdout'ом не гасится (проверено), поэтому объекты «только объём» (лучи, пылевое
    кольцо) переносятся в коллекцию coll_name+'_Vol', исключённую из слоя звёзд (звёзды за ними видны).
    Вызывать ПОСЛЕ setup_compositor и после создания всех объектов сцены. Возвращает слой звёзд."""
    if not isinstance(stars, (list, tuple)):
        stars = [stars]
    C.collection(coll_name, scene)
    for ob in stars:
        C.link(ob, coll_name)
    vol_name = coll_name + "_Vol"
    C.collection(vol_name, scene)
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob not in stars and _volume_only(ob):
            C.link(ob, vol_name)
    main = scene.view_layers[0]
    sl = scene.view_layers.get(layer_name) or scene.view_layers.new(layer_name)
    main.layer_collection.children[coll_name].exclude = True
    for lc in sl.layer_collection.children:
        if lc.name == coll_name:
            lc.exclude = False
        elif lc.name == vol_name:
            lc.exclude = True
        else:
            lc.holdout = True
    sl.use_volumes = False
    sl.use_sky = False                      # Млечный Путь — только в основном слое
    sl.samples = samples
    sl.cycles.use_denoising = False
    # компоузер: Render Layers(основной) + Render Layers(звёзды) -> Add -> туда же, куда шёл основной
    ng = scene.compositing_node_group
    rl = next(n for n in ng.nodes if n.bl_idname == "CompositorNodeRLayers")
    rl.layer = main.name
    targets = [lk.to_socket for lk in rl.outputs["Image"].links]
    rs = ng.nodes.new("CompositorNodeRLayers")
    rs.scene = scene
    rs.layer = sl.name
    rs.location = (rl.location.x, rl.location.y - 300)
    mix = ng.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "ADD"
    mix.inputs["Factor"].default_value = 1.0
    mix.location = (rl.location.x + 150, rl.location.y - 150)
    ng.links.new(rl.outputs["Image"], mix.inputs[6])
    ng.links.new(rs.outputs["Image"], mix.inputs[7])
    for t in targets:
        ng.links.new(mix.outputs[2], t)
    return sl
