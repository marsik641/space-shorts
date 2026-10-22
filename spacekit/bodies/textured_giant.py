"""Объёмное тело с наблюдательной цилиндрической картой, для сравнений масштаба."""
import math
import os
import bpy
from .. import core as C
from .planets import _NB
from .star import _sphere


def build_textured_giant(name, *, texture, radius=1.0, location=(0, 0, 0), polar_limit=80):
    """Номинальная сфера; неизвестные полюса заполняются ближайшей валидной широтой."""
    if not os.path.isfile(texture):
        raise FileNotFoundError(texture)
    mat, nodes, links, out = C.new_material(name + "Map")
    b = _NB(mat.node_tree)
    p = b.v("NORMALIZE", b.node("ShaderNodeTexCoord").outputs["Object"])
    x, y, z = b.sep(p)
    u = b.m("MULTIPLY_ADD", b.m("ARCTAN2", y, x), 1 / (2 * math.pi), .5)
    v = b.m("MULTIPLY_ADD", b.m("ARCSINE", z), 1 / math.pi, .5)
    edge = (90 - polar_limit) / 180 + .004
    v = b.m("MINIMUM", b.m("MAXIMUM", v, edge), 1 - edge)
    tex = b.node("ShaderNodeTexImage", {"Vector": b.comb(u, v, 0)},
                 image=bpy.data.images.load(texture, check_existing=True), interpolation="Linear")
    diffuse = b.node("ShaderNodeBsdfDiffuse", {"Color": tex.outputs["Color"], "Roughness": .1})
    links.new(diffuse.outputs[0], out.inputs["Surface"])
    mesh = _sphere(name + "Mesh", 192, 96)
    mesh.materials.append(mat)
    ob = bpy.data.objects.new(name, mesh)
    C.link(ob, "Comparison")
    ob.location = location
    ob.scale = (radius,) * 3
    return ob
