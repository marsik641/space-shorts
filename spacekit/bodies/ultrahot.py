"""Ультрагорячий газовый гигант: светящаяся фотосфера без твёрдого рельефа.

Температуры день/ночь задают иллюстративный градиент, не климатическое решение.
Самосвечение ~T^4, цвет чёрного тела, плавные газовые полосы и сдвиг течений.
Никаких лавы, кратеров, пламени и непрозрачной каменной корки.
Материалы и имена имеют префикс, остальные тела spacekit не изменяются.
"""
import bpy
from mathutils import Vector

from .. import anim
from .. import core as C
from .planets import _NB, _ghost
from .star import _sphere


def thermal_material(name, day_k=4566.0, night_k=2556.0, sun_dir=(1, 0, 0), seed=809,
                     strength=4.0, detail="close"):
    """Газовый рисунок — процедурная реконструкция. flow анимируется только ключами."""
    mat, nodes, links, out = C.new_material(name)
    b = _NB(mat.node_tree)
    tc = b.node("ShaderNodeTexCoord")
    p = b.v("NORMALIZE", tc.outputs["Object"])
    flow = b.node("ShaderNodeValue", name="flow", label="Illustrative flow")
    flow.outputs[0].default_value = seed * 0.013
    fw = flow.outputs[0]
    x, y, z = b.sep(p)
    # Струйные полосы с крупными волнами, без Bump/Displacement.
    warp = b.noise(p, 2.8, detail=3, rough=0.62, dist=0.4, w=fw).outputs["Color"]
    shifted = b.v("ADD", p, b.v("SCALE", b.v("SUBTRACT", warp, (0.5, 0.5, 0.5)), scale=0.24))
    broad = b.noise(shifted, 3.1, detail=3, rough=0.65, w=fw).outputs["Fac"]
    lat = b.m("ADD", z, b.m("MULTIPLY", b.m("SUBTRACT", broad, 0.5), 0.25))
    band = b.m("ADD", 0.5, b.m("MULTIPLY", b.m("SINE", b.m("MULTIPLY", lat, 44.0)), 0.5))
    cloud = b.noise(b.v("MULTIPLY", shifted, (5.0, 5.0, 22.0)), 3.0,
                    detail=3 if detail == "close" else 1, rough=0.55, w=fw).outputs["Fac"]
    pattern = b.m("ADD", 0.68, b.m("ADD", b.m("MULTIPLY", band, 0.16), b.m("MULTIPLY", cloud, 0.32)))
    mu = b.v("DOT_PRODUCT", p, tuple(Vector(sun_dir).normalized()))
    day = b.ss(mu, -0.65, 0.8)
    # Переход не выдаётся за восстановленную карту температуры.
    temp = b.m("MULTIPLY_ADD", day, day_k - night_k, night_k)
    bb = b.node("ShaderNodeBlackbody", {"Temperature": temp})
    thermal = b.m("ADD", (night_k / day_k) ** 4,
                  b.m("MULTIPLY", day, 1.0 - (night_k / day_k) ** 4))
    lw = b.node("ShaderNodeLayerWeight", {"Blend": 0.5})
    facing = b.m("SUBTRACT", 1.0, lw.outputs["Facing"], clamp=True)
    limb = b.m("MULTIPLY_ADD", facing, 0.64, 0.36)
    emit = b.node("ShaderNodeEmission", {"Color": bb.outputs["Color"],
                  "Strength": b.m("MULTIPLY", strength, b.m("MULTIPLY", thermal, b.m("MULTIPLY", pattern, limb)))})
    links.new(emit.outputs[0], out.inputs["Surface"])
    mat.cycles.emission_sampling = "NONE"
    return mat


def build_ultrahot(name, *, radius=1.0, location=(0, 0, 0), parent=None, day_k=4566.0,
                   night_k=2556.0, sun_dir=(1, 0, 0), seed=809, strength=4.0, detail="close"):
    """Возвращает root/body/mat; sun_dir задаётся в локальных осях тела."""
    root = C.empty(name, coll="Ultrahot", parent=parent, loc=location)
    segments = {"close": 192, "mid": 128, "far": 64}[detail]
    mesh = _sphere(name + "_Mesh", segments, segments // 2)
    mat = thermal_material(name + "_Thermal", day_k, night_k, sun_dir, seed, strength, detail)
    mesh.materials.append(mat)
    body = bpy.data.objects.new(name + "_Photosphere", mesh)
    C.link(body, "Ultrahot")
    body.parent = root
    body.scale = (radius,) * 3
    _ghost(body)
    return dict(root=root, body=body, mat=mat, radius=radius, day_k=day_k, night_k=night_k)


def key_flow(body, pairs):
    """Течение — ключи Value, работает без autoexec и Python-драйверов."""
    socket = body["mat"].node_tree.nodes["flow"].outputs[0]
    for frame, value in pairs:
        socket.default_value = value
        socket.keyframe_insert("default_value", frame=frame)
    anim.set_interpolation(body["mat"].node_tree, "LINEAR")
