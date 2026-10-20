"""Эмиссионная туманность на небе (области H II: Hα, [O III], пылевые прожилки) — добавка к world-шейдеру неба.

    from spacekit import sky as SKY
    from spacekit.fx import nebula_sky as NB
    stars = SKY.build_sky(sc, cam, ex, ...)                 # сначала небо (world с Млечным Путём)
    NB.add_nebula(sc, direction=(0.3, 1.0, 0.2), radius_deg=28, strength=0.6, exposure=ex, seed=4)

Работает по направлению взгляда (TexCoord.Generated мира): туманность «на бесконечности», не плывёт при
наезде и одинакова во всех шотах с той же ориентацией камеры; world в слое звёзд выключен — звёзды не
перекрываются (holdout не нужен). Сцену почти не освещает (world слабый).
Свет туманности — отдельный Background, сложенный с фоном (Млечным Путём) шейдером Add. Структура — шумы по
направлению: крупные облака (fBm с искажением) → Hα (розово-красный, широко) и [O III] (бирюзовый, ядро), яркие
волокна (гребни шума), тёмные пылевые прожилки (умножение). Цвета — линии излучения
H II-областей; форма — процедурная (в описании: «nebula backdrop — artist's impression»).
"""
import math

from mathutils import Vector

HA_RGB = (1.0, 0.20, 0.40)
OIII_RGB = (0.12, 0.88, 0.85)


def _world_parts(scene):
    w = scene.world
    if w is None or not w.use_nodes:
        raise RuntimeError("nebula_sky: сначала sky.build_sky / build_milky_way (нужен world с узлами)")
    nt = w.node_tree
    bg = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBackground")
    return nt, bg


def add_nebula(scene, direction, radius_deg=25.0, strength=0.5, exposure=0.0, ref_exposure=0.4, seed=1,
               core_frac=0.45, ha=HA_RGB, oiii=OIII_RGB, filaments=1.0, dust=0.8, scale=5.0, name="Neb"):
    """Туманность с центром в направлении direction (мир), угловой радиус radius_deg. strength — яркость
    при ref_exposure (компенсация экспозиции шота, как у sky.build_sky). Возвращает узел Value '<name>_k'
    (яркость — можно ставить ключи)."""
    nt, bg = _world_parts(scene)
    N, L = nt.nodes, nt.links
    from ..bodies.planets import _NB, _seed_off
    b = _NB(nt)
    tc = next((n for n in N if n.bl_idname == "ShaderNodeTexCoord"), None) or b.node("ShaderNodeTexCoord")
    d = b.v("NORMALIZE", tc.outputs["Generated"])
    c = tuple(Vector(direction).normalized())
    ang = b.m("ARCCOSINE", b.m("MINIMUM", b.m("MAXIMUM", b.v("DOT_PRODUCT", d, c), -1.0), 1.0))
    r = math.radians(radius_deg)
    mask = b.ss(ang, r, 0.0)                                       # 1 в центре → 0 на краю
    mask = b.m("MULTIPLY", mask, mask)
    core = b.ss(ang, r * core_frac, 0.0)
    ds = b.v("ADD", b.v("SCALE", d, scale=scale), _seed_off(seed))
    warp = b.noise(ds, 1.6, detail=3.0, rough=0.55).outputs["Color"]
    dw = b.v("ADD", ds, b.v("SCALE", b.v("SUBTRACT", warp, (0.5, 0.5, 0.5)), scale=0.9))
    n1 = b.noise(dw, 1.0, detail=6.0, rough=0.62, dist=0.6).outputs["Fac"]
    clouds = b.ss(b.m("ADD", n1, b.m("MULTIPLY", b.m("SUBTRACT", mask, 0.5), 0.35)), 0.42, 0.82)
    n2 = b.noise(dw, 3.2, detail=4.0, rough=0.55, dist=0.3).outputs["Fac"]
    ridge = b.m("POWER", b.m("SUBTRACT", 1.0, b.m("ABSOLUTE", b.m("SUBTRACT", b.m("MULTIPLY", n2, 2.0), 1.0))), 5.0)
    n3 = b.noise(b.v("ADD", dw, (3.1, 1.7, 5.3)), 2.2, detail=5.0, rough=0.6).outputs["Fac"]
    lanes = b.m("SUBTRACT", 1.0, b.m("MULTIPLY", b.ss(n3, 0.52, 0.72), dust))
    ha_i = b.m("MULTIPLY", b.m("MULTIPLY", b.m("ADD", clouds, b.m("MULTIPLY", ridge, filaments)), mask), lanes)
    o_i = b.m("MULTIPLY", b.m("MULTIPLY", b.ss(n1, 0.55, 0.9), core), lanes)
    k = b.node("ShaderNodeValue", name=f"{name}_k", label=f"{name}_k")
    k.outputs[0].default_value = strength * 2.0 ** (ref_exposure - exposure)
    col_ha = b.node("ShaderNodeMix", {"Factor": 1.0}, data_type="RGBA", blend_type="MULTIPLY")
    b.put(col_ha.inputs[6], (*ha, 1.0))
    b.put(col_ha.inputs[7], b.comb(ha_i, ha_i, ha_i))
    col_o = b.node("ShaderNodeMix", {"Factor": 1.0}, data_type="RGBA", blend_type="MULTIPLY")
    b.put(col_o.inputs[6], (*oiii, 1.0))
    b.put(col_o.inputs[7], b.comb(o_i, o_i, o_i))
    neb = b.node("ShaderNodeMix", {"Factor": 1.0}, data_type="RGBA", blend_type="ADD")
    L.new(col_ha.outputs[2], neb.inputs[6])
    L.new(col_o.outputs[2], neb.inputs[7])
    kk = b.node("ShaderNodeMix", {"Factor": 1.0}, data_type="RGBA", blend_type="MULTIPLY")
    L.new(neb.outputs[2], kk.inputs[6])
    L.new(b.comb(k.outputs[0], k.outputs[0], k.outputs[0]), kk.inputs[7])
    # отдельный Background (яркость туманности не зависит от Strength фона Млечного Пути) + сложение шейдеров
    out = next(n for n in N if n.bl_idname == "ShaderNodeOutputWorld")
    bg2 = b.node("ShaderNodeBackground", {"Strength": 1.0})
    L.new(kk.outputs[2], bg2.inputs["Color"])
    # цепочкой: несколько туманностей складываются с тем, что уже идёт в выход мира
    src = out.inputs["Surface"].links[0].from_socket if out.inputs["Surface"].is_linked else bg.outputs[0]
    add = b.node("ShaderNodeAddShader", {0: src, 1: bg2.outputs[0]})
    L.new(add.outputs[0], out.inputs["Surface"])
    return k
