"""Базовые помощники сцены: очистка, коллекции, empty, материалы, math-узлы, пути."""
import os

import bpy

from . import REPO
from .lighting import blackbody_rgb  # noqa: F401  (исторический путь C.blackbody_rgb)

FPS = 30                                   # fps по умолчанию; модули берут fps из сцены (scene_fps)
ASSETS = os.path.join(REPO, "assets")       # сгенерированные текстуры (Млечный Путь и т.п.), в git не идут
OUT = os.path.join(REPO, "out")             # кадры, видео, превью — в git не идут


def scene_fps(scene=None):
    scene = scene or bpy.context.scene
    return scene.render.fps / scene.render.fps_base


def reset_scene(fps=FPS):
    """Пустая сцена: удалить все объекты/данные заводского стартапа."""
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras,
                 bpy.data.curves, bpy.data.pointclouds, bpy.data.node_groups, bpy.data.images):
        for d in list(coll):
            coll.remove(d)
    sc = bpy.context.scene
    sc.render.fps = int(fps)
    sc.render.fps_base = 1.0
    return sc


def collection(name, scene=None):
    scene = scene or bpy.context.scene
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
    if coll.name not in scene.collection.children:
        scene.collection.children.link(coll)
    return coll


def link(obj, coll_name):
    coll = collection(coll_name)
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    coll.objects.link(obj)
    return obj


def empty(name, coll="PSR", parent=None, loc=(0, 0, 0), display="PLAIN_AXES", size=1.0):
    ob = bpy.data.objects.new(name, None)
    ob.empty_display_type = display
    ob.empty_display_size = size
    ob.location = loc
    link(ob, coll)
    if parent is not None:
        ob.parent = parent
    return ob


def new_material(name):
    """Материал с пустым деревом и выходом. Возвращает (mat, nodes, links, out)."""
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (600, 0)
    return mat, nt.nodes, nt.links, out


def math_node(nodes, links, op, a=None, b=None, loc=(0, 0), clamp=False):
    """Узел Math; a/b — сокет или число."""
    n = nodes.new("ShaderNodeMath")
    n.operation = op
    n.use_clamp = clamp
    n.location = loc
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = v
        else:
            links.new(v, n.inputs[i])
    return n.outputs[0]
