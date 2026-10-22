"""Кандидат fx.comet_coma: плоская PSF, слабая кома, накопление движения.

Локальная версия до освобождения GPU: действующий spacekit не меняем.
Не фотометрический симулятор и не изображение измеренного ядра.
"""
import math

import bpy

from spacekit import anim
from spacekit import core as C


def emissive(name, color, strength=1.0):
    mat, nodes, links, out = C.new_material(name)
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (*color, 1)
    emission.inputs["Strength"].default_value = strength
    links.new(emission.outputs[0], out.inputs["Surface"])
    return mat


def gaussian_material(name, color=(0.8, 0.86, 1.0), strength=1.0, opacity=1.0):
    mat, nodes, links, out = C.new_material(name)
    uv = nodes.new("ShaderNodeTexCoord")
    dist = nodes.new("ShaderNodeVectorMath")
    dist.operation = "DISTANCE"
    links.new(uv.outputs["UV"], dist.inputs[0])
    dist.inputs[1].default_value = (0.5, 0.5, 0)
    square = C.math_node(nodes, links, "MULTIPLY", dist.outputs["Value"], dist.outputs["Value"])
    power = C.math_node(nodes, links, "MULTIPLY", square, -24.0)
    alpha = C.math_node(nodes, links, "EXPONENT", power)
    alpha = C.math_node(nodes, links, "SUBTRACT", alpha, 0.003, clamp=True)
    alpha = C.math_node(nodes, links, "MULTIPLY", alpha, opacity)
    trans = nodes.new("ShaderNodeBsdfTransparent")
    emit = nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = (*color, 1)
    emit.inputs["Strength"].default_value = strength
    mix = nodes.new("ShaderNodeMixShader")
    links.new(alpha, mix.inputs[0])
    links.new(trans.outputs[0], mix.inputs[1])
    links.new(emit.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], out.inputs["Surface"])
    return mat


def sprite(name, x, z, radius, mat, *, y=0, parent=None):
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata([(-1, 0, -1), (1, 0, -1), (1, 0, 1), (-1, 0, 1)], [], [(0, 1, 2, 3)])
    mesh.update()
    uv = mesh.uv_layers.new(name="UVMap")
    for i, coord in enumerate(((0, 0), (1, 0), (1, 1), (0, 1))):
        uv.data[i].uv = coord
    ob = bpy.data.objects.new(name, mesh)
    C.link(ob, "Observation")
    ob.parent = parent
    ob.location = (x, y, z)
    ob.scale = (radius, 1, radius)
    ob.data.materials.append(mat)
    return ob


def unresolved(name, x, z, *, scale=1.0, parent=None, coma=True):
    root = C.empty(name, coll="Observation", parent=parent, loc=(x, -0.12, z))
    core_mat = gaussian_material(name + "CoreMat", strength=2.2)
    core = sprite(name + "Core", 0, 0, 0.10 * scale, core_mat, y=-0.03, parent=root)
    halo = None
    if coma:
        halo_mat = gaussian_material(name + "ComaMat", strength=0.7, opacity=0.25)
        halo = sprite(name + "Coma", 0, 0, 0.55 * scale, halo_mat, parent=root)
    return {"root": root, "core": core, "coma": halo}


def key_location(ob, keys):
    for frame, x, z in keys:
        ob.location.x, ob.location.z = x, z
        ob.keyframe_insert("location", frame=frame)
    anim.set_interpolation(ob, "LINEAR")


def visible_between(ob, first, last, *, end):
    for frame, hide in ((1, first > 1), (max(1, first - 1), True), (first, False), (last, False), (last + 1, True)):
        if frame <= end:
            ob.hide_render = hide
            ob.keyframe_insert("hide_render", frame=frame)
    anim.set_interpolation(ob, "CONSTANT")


def key_scale(ob, keys):
    for frame, value in keys:
        ob.scale = (value, value, value)
        ob.keyframe_insert("scale", frame=frame)
    anim.set_interpolation(ob, "LINEAR")


def integrated_streak(name, start, stop, *, first=1, last=100, samples=42, parent=None, radius=0.11):
    """Последовательное накопление PSF; точки сохраняются до конца сцены.

    Это иллюстрация интегрирования, не реальная чувствительность VIS.
    """
    root = C.empty(name, coll="Observation", parent=parent)
    material = gaussian_material(name + "Mat", strength=1.25, opacity=0.3)
    objects = []
    for i in range(samples):
        u = i / max(1, samples - 1)
        x, z = (a + (b - a) * u for a, b in zip(start, stop))
        ob = sprite(f"{name}_{i:03}", x, z, radius, material, parent=root)
        at = round(first + (last - first) * u)
        if at > 1:
            ob.hide_render = True
            ob.keyframe_insert("hide_render", frame=1)
            ob.keyframe_insert("hide_render", frame=at - 1)
        ob.hide_render = False
        ob.keyframe_insert("hide_render", frame=at)
        anim.set_interpolation(ob, "CONSTANT")
        objects.append(ob)
    return {"root": root, "samples": objects}
