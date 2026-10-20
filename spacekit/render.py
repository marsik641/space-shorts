"""Рендер: форматы кадра, Cycles/OptiX, цвет (AgX), компоузер (блум), слой звёзд, денойз, вывод кадров.

Форматы: FORMATS["16x9"] = 1920×1080, FORMATS["9x16"] = 1080×1920 (Shorts). fps задаётся в setup_cycles(fps=...)
или core.reset_scene(fps=...); все модули берут fps из сцены.
"""
import math
import os

import bpy

from . import core as C

RES = (1920, 1080)
FORMATS = {"16x9": (1920, 1080), "9x16": (1080, 1920)}


DEVICE_ORDER = ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL")
_DEVICE = None


def pick_device():
    """Устройство Cycles: env SPACEKIT_DEVICE (OPTIX|CUDA|HIP|ONEAPI|METAL|CPU) или первое доступное по DEVICE_ORDER
    (на RTX 3060 — OptiX, как раньше). Выбор печатается один раз: «[render] device …»."""
    global _DEVICE
    if _DEVICE:
        return _DEVICE
    prefs = bpy.context.preferences.addons["cycles"].preferences
    want = os.environ.get("SPACEKIT_DEVICE", "").strip().upper()
    order = (want,) if want else DEVICE_ORDER
    _DEVICE = "CPU"
    for t in order:
        if t == "CPU":
            break
        try:
            prefs.compute_device_type = t
        except TypeError:
            continue
        prefs.get_devices()
        if any(d.type == t for d in prefs.devices):
            for d in prefs.devices:
                d.use = d.type == t
            _DEVICE = t
            break
    names = [d.name for d in prefs.devices if d.use] if _DEVICE != "CPU" else ["CPU"]
    print(f"[render] device {_DEVICE}: {', '.join(names)}")
    return _DEVICE


def setup_cycles(scene=None, samples=64, res=RES, pct=100, motion_blur=True, shutter=0.5,
                 denoise=True, adaptive_threshold=0.02, fps=None):
    scene = scene or bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.render.compositor_device = "GPU"      # блум 2 Мпикс на CPU стоит ~1 с/кадр
    if fps is not None:
        scene.render.fps, scene.render.fps_base = int(fps), 1.0
    dev = pick_device()
    if dev == "CPU":
        scene.render.compositor_device = "CPU"
    cy = scene.cycles
    cy.device = "CPU" if dev == "CPU" else "GPU"
    cy.samples = samples
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = adaptive_threshold
    cy.use_denoising = denoise
    if denoise:
        # OptiX-денойзер — только на NVIDIA; на другом железе — OIDN (вид чуть другой: шоты одного ролика
        # рендерить на одной машине)
        cy.denoiser = "OPTIX" if dev == "OPTIX" else "OPENIMAGEDENOISE"
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


def setup_color(scene=None, exposure=0.0, look="None", view="AgX", white_balance=None):
    """AgX, экспозиция; white_balance — баланс белого камеры, К (None — выкл.): у красной звезды (≈2600 K) камера,
    выставленная на ~3300 K, оставляет свет тёплым, но не топит собственные цвета поверхностей в оранжевом."""
    scene = scene or bpy.context.scene
    vs = scene.view_settings
    vs.view_transform = view
    try:
        vs.look = look
    except TypeError:
        pass
    vs.exposure = exposure
    vs.gamma = 1.0
    if white_balance:
        vs.use_white_balance = True
        vs.white_balance_temperature = float(white_balance)
        vs.white_balance_tint = 0.0
    else:
        vs.use_white_balance = False
    scene.display_settings.display_device = "sRGB"


def _set_in(node, name, value):
    """Вход узла по имени (Blender 5: параметры узлов компоузера — сокеты); нет такого — предупреждение."""
    sock = node.inputs.get(name)
    if sock is None:
        print(f"[render] WARNING: у {node.bl_idname} нет входа {name!r}")
        return
    sock.default_value = value


def _vignette_image(scene, amount, power=2.2, name="Vignette"):
    """Картинка-виньетка под размер кадра (с процентом): 1 в центре → 1 − amount в углах (по эллипсу кадра)."""
    import numpy as np
    r = scene.render
    w = max(2, int(r.resolution_x * r.resolution_percentage / 100))
    h = max(2, int(r.resolution_y * r.resolution_percentage / 100))
    img = bpy.data.images.get(name)
    if img is not None:
        bpy.data.images.remove(img)
    img = bpy.data.images.new(name, w, h, alpha=False, float_buffer=True)
    img.colorspace_settings.name = "Non-Color"
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    u = (xx + 0.5) / w * 2.0 - 1.0
    v = (yy + 0.5) / h * 2.0 - 1.0
    d = np.clip(np.sqrt(u * u + v * v) / np.sqrt(2.0), 0.0, 1.0)
    g = 1.0 - amount * d ** power
    px = np.ones((h, w, 4), np.float32)
    px[..., 0] = px[..., 1] = px[..., 2] = g
    img.pixels.foreach_set(px.ravel())
    img.update()
    try:
        img.pack()                                   # пиксели живут в .blend (save) и при перезагрузке
    except RuntimeError:
        pass
    return img


def setup_compositor(scene=None, bloom_strength=0.6, bloom_size=0.6, bloom_threshold=1.0,
                     fog_strength=0.25, dispersion=0.012, streaks=0.0, streaks_n=2, streaks_angle_deg=0.0,
                     streaks_threshold=None, streaks_fade=0.9, vignette=0.0):
    """Блум (Bloom) + мягкое гало (Fog Glow) + лёгкая хроматическая аберрация.
    streaks > 0 — анаморфные лучи (Glare Streaks, только яркое выше streaks_threshold, сложением);
    vignette — затемнение углов (доля, 0.25 — мягко)."""
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
    last = g2.outputs[0]
    if streaks > 0:
        g3 = N.new("CompositorNodeGlare"); g3.location = (-350, -300)
        _set_in(g3, "Type", "Streaks")
        _set_in(g3, "Quality", "High")
        _set_in(g3, "Threshold", streaks_threshold if streaks_threshold is not None else bloom_threshold * 3.0)
        _set_in(g3, "Strength", 1.0)
        _set_in(g3, "Streaks", int(streaks_n))
        _set_in(g3, "Streaks Angle", math.radians(streaks_angle_deg))
        _set_in(g3, "Fade", streaks_fade)
        L.new(rl.outputs["Image"], g3.inputs["Image"])
        gl = g3.outputs.get("Glare")
        if gl is None:
            print("[render] WARNING: у Glare нет выхода 'Glare' — лучи не добавлены")
        else:
            mx = N.new("ShaderNodeMix"); mx.location = (0, -300)
            mx.data_type = "RGBA"
            mx.blend_type = "ADD"
            mx.inputs["Factor"].default_value = streaks
            L.new(last, mx.inputs[6])
            L.new(gl, mx.inputs[7])
            last = mx.outputs[2]
    if vignette > 0:
        im = N.new("CompositorNodeImage"); im.location = (0, -550)
        im.image = _vignette_image(scene, vignette)
        mv = N.new("ShaderNodeMix"); mv.location = (150, -300)
        mv.data_type = "RGBA"
        mv.blend_type = "MULTIPLY"
        mv.inputs["Factor"].default_value = 1.0
        L.new(last, mv.inputs[6])
        L.new(im.outputs["Image"], mv.inputs[7])
        last = mv.outputs[2]
    L.new(last, ld.inputs["Image"])
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
