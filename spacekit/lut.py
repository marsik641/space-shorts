"""Таблицы-текстуры (LUT) для шейдеров: numpy-массив → EXR в assets/<папка>/ с кэшем по хешу параметров.

    from spacekit import lut
    img = lut.ensure("gas_giant", "saturn_bands", meta, lambda: rgba)   # rgba: (H, W, 4) float32
    # узел: ShaderNodeTexImage(image=img, interpolation="Linear", extension="EXTEND")

Изображение — линейные данные (Non-Color, альфа «как есть»): цвет, оптическая толщина и т.п. Хеш — md5 от
json(meta), не hash() (тот рандомизирован между запусками). Запись — через save_render (EXR half, ZIP: без потерь),
как у Млечного Пути в sky.py.
"""
import hashlib
import json
import os

import bpy
import numpy as np

from . import core as C


def _key(meta):
    return hashlib.md5(json.dumps(meta, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:10]


def _save_exr(path, rgba, scene=None):
    H, W = rgba.shape[:2]
    img = bpy.data.images.new("_lut_tmp", width=W, height=H, alpha=True, float_buffer=True)
    img.alpha_mode = "CHANNEL_PACKED"
    img.pixels.foreach_set(np.ascontiguousarray(rgba, np.float32).ravel())
    sc = scene or bpy.context.scene
    ims = sc.render.image_settings
    keep = (ims.media_type, ims.file_format, ims.color_mode, ims.color_depth, ims.exr_codec)
    ims.media_type = "IMAGE"
    ims.file_format = "OPEN_EXR"
    ims.color_mode = "RGBA"
    ims.color_depth = "32"
    ims.exr_codec = "ZIP"
    try:
        img.save_render(path, scene=sc)
    finally:
        ims.media_type, ims.file_format = keep[0], keep[1]
        ims.color_mode, ims.color_depth, ims.exr_codec = keep[2], keep[3], keep[4]
    bpy.data.images.remove(img)


def ensure(folder, name, meta, make, scene=None):
    """Загрузить LUT из assets/<folder>/<name>_<хеш>.exr или построить make() → (H, W, 4) float32 и сохранить.
    Строки массива — снизу вверх (как пиксели Blender: v=0 — первая строка). Возвращает bpy.types.Image."""
    d = os.path.join(C.ASSETS, folder)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{name}_{_key(meta)}.exr")
    if not os.path.exists(path):
        rgba = np.asarray(make(), np.float32)
        if rgba.ndim == 2:
            rgba = rgba[None]
        _save_exr(path, rgba, scene)
    img = bpy.data.images.load(path, check_existing=True)
    img.colorspace_settings.name = "Non-Color"
    img.alpha_mode = "CHANNEL_PACKED"
    return img


def image_node(b, img, u, v=0.5):
    """Узел текстуры LUT по координате u (сокет) в строке v. b — построитель _NB (planets). Возвращает узел."""
    uv = b.comb(u, v, 0.0)
    return b.node("ShaderNodeTexImage", {"Vector": uv}, image=img, interpolation="Linear", extension="EXTEND")


def srgb_to_linear(c):
    c = np.asarray(c, np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
