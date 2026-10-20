"""Кольца остатка сверхновой (SN 1987A): светящийся тор газа, «жемчужины» горячих точек, кольца песочных часов.

    from spacekit.fx import sn_rings as RG
    er = RG.build_ring("ER", a=60.0, width=4.0, thick=2.5, color=(1.0, 0.25, 0.32), strength=3.0, seed=2)
    RG.key_value(er, "glow", [(1, 0.0), (90, 1.0)])           # кольцо загорается (ионизация вспышкой)
    hs = RG.build_hotspots("HS", a=60.0, angles=[…], times=[…], size=1.2, seed=4)
    RG.key_time(hs, [(1, 1994.0), (n, 2012.0)])               # точка i вспыхивает при time ≥ times[i]

Кольцо — объём (эмиссия без рассеяния) в торе-домене: плотность exp(−(Δρ/width)² − (z/thick)²) × сгустки
по азимуту и 3D-клочья; плоскость кольца — XY объекта (наклон — rotation объекта). Цвет — линия Hα
(розово-красный), у внутреннего края — к оранжевому. Горячие точки — эмиссионные шарики в одном меше
(атрибут t_on — год/момент загорания, amp — яркость), шейдер: яркость = amp · smoothstep(t_on, t_on + rise, time)
· (1 + 0.5·exp(−(time − t_on)/decay)) — короткая вспышка при ударе и ровное свечение, fade — общее угасание
(кольцо разрушается). Не освещают сцену. Значения — узлы Value (glow, flow; time, fade).
"""
import math
import random

import bmesh
import bpy

from .. import anim
from .. import core as C
from ..bodies.planets import _NB, _ghost, _seed_off

ER_RGB = (1.0, 0.22, 0.30)
EDGE_RGB = (1.0, 0.55, 0.30)
SPOT_RGB = (1.0, 0.90, 0.75)


def _torus(name, a, m, nu=192, nv=24):
    """Замкнутый тор (домен объёма): большой радиус a, малый m, плоскость XY."""
    bm = bmesh.new()
    rows = []
    for i in range(nu):
        ph = 2.0 * math.pi * i / nu
        row = []
        for j in range(nv):
            th = 2.0 * math.pi * j / nv
            rr = a + m * math.cos(th)
            row.append(bm.verts.new((rr * math.cos(ph), rr * math.sin(ph), m * math.sin(th))))
        rows.append(row)
    for i in range(nu):
        for j in range(nv):
            i2, j2 = (i + 1) % nu, (j + 1) % nv
            bm.faces.new((rows[i][j], rows[i2][j], rows[i2][j2], rows[i][j2]))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me


def _value(b, name, v):
    n = b.node("ShaderNodeValue", name=name, label=name)
    n.outputs[0].default_value = v
    return n.outputs[0]


def _ring_material(name, a, width, thick, color, edge_color, strength, seed, clumps, step):
    mat, N, L, out = C.new_material(name)
    b = _NB(mat.node_tree)
    tc = b.node("ShaderNodeTexCoord")
    p = tc.outputs["Object"]
    vals = {k: _value(b, k, v) for k, v in (("glow", 1.0), ("flow", seed * 0.41))}
    x, y, z = b.sep(p)
    rho = b.m("SQRT", b.m("ADD", b.m("MULTIPLY", x, x), b.m("MULTIPLY", y, y)))
    dr = b.m("DIVIDE", b.m("SUBTRACT", rho, a), width)
    dz = b.m("DIVIDE", z, thick)
    q = b.m("ADD", b.m("MULTIPLY", dr, dr), b.m("MULTIPLY", dz, dz))
    prof = b.m("EXPONENT", b.m("MULTIPLY", q, -1.0))
    # сгустки по азимуту (кольцо в реальности комковатое) и клочья
    ps = b.v("ADD", b.v("SCALE", p, scale=1.0 / a), _seed_off(seed))
    c1 = b.noise(ps, clumps, detail=3.0, rough=0.6, w=vals["flow"]).outputs["Fac"]
    c2 = b.noise(ps, clumps * 4.0, detail=2.0, rough=0.5, w=b.m("MULTIPLY", vals["flow"], 1.7)).outputs["Fac"]
    cl = b.m("MULTIPLY", b.m("ADD", 0.15, b.m("MULTIPLY", b.ss(c1, 0.35, 0.75), 1.5)),
             b.m("ADD", 0.6, b.m("MULTIPLY", c2, 0.8)))
    dens = b.m("MULTIPLY", prof, cl)
    col = b.mix(b.ss(dr, 0.2, -1.2), color, edge_color)       # к внутреннему краю — оранжевее (там удар)
    es = b.m("MULTIPLY", b.m("MULTIPLY", dens, strength), vals["glow"])
    em = b.node("ShaderNodeEmission", {"Color": col, "Strength": es})
    L.new(em.outputs[0], out.inputs["Volume"])
    mc = mat.cycles
    for k, v in (("volume_sampling", "DISTANCE"), ("volume_interpolation", "LINEAR"), ("volume_step_rate", step)):
        try:
            setattr(mc, k, v)
        except (AttributeError, TypeError):
            pass
    return mat


def build_ring(name, a=1.0, width=0.06, thick=0.04, color=ER_RGB, edge_color=EDGE_RGB, strength=3.0, seed=1,
               clumps=9.0, step=1.0, location=(0, 0, 0), rotation=(0, 0, 0), parent=None, coll="FX"):
    """Тор-кольцо (объём): a — радиус, width/thick — гауссовы полуширины по радиусу и по высоте (ед. сцены).
    Возвращает dict(ob, mat)."""
    m = 2.6 * max(width, thick)
    me = _torus(f"{name}_Dom", a, m)
    mat = _ring_material(f"{name}_Mat", a, width, thick, color, edge_color, strength, seed, clumps, step)
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    C.link(ob, coll)
    ob.location = location
    ob.rotation_euler = rotation
    if parent is not None:
        ob.parent = parent
    _ghost(ob)
    return dict(ob=ob, mat=mat)


def _spot_material(name, color, rise, decay, flare):
    mat, N, L, out = C.new_material(name)
    b = _NB(mat.node_tree)
    def attr(nm):
        return b.node("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name=nm).outputs["Fac"]
    t_on, amp = attr("t_on"), attr("amp")
    vals = {k: _value(b, k, v) for k, v in (("time", -1e9), ("fade", 1.0), ("strength", 30.0))}
    dt = b.m("SUBTRACT", vals["time"], t_on)
    on = b.ss(dt, 0.0, rise)
    burst = b.m("ADD", 1.0, b.m("MULTIPLY", b.m("EXPONENT", b.m("DIVIDE", b.m("MAXIMUM", dt, 0.0), -decay)), flare))
    lw = b.node("ShaderNodeLayerWeight", {"Blend": 0.5})
    core = b.m("ADD", 0.35, b.m("MULTIPLY", b.m("SUBTRACT", 1.0, lw.outputs["Facing"]), 0.65))
    es = b.m("MULTIPLY", b.m("MULTIPLY", b.m("MULTIPLY", on, burst), b.m("MULTIPLY", amp, core)),
             b.m("MULTIPLY", vals["strength"], vals["fade"]))
    em = b.node("ShaderNodeEmission", {"Color": (*color, 1.0), "Strength": es})
    L.new(em.outputs[0], out.inputs["Surface"])
    mat.cycles.emission_sampling = "NONE"
    return mat


def build_hotspots(name, a, angles_deg, times, size=0.02, amps=None, color=SPOT_RGB, rise=0.6, decay=1.5,
                   flare=1.2, inner=0.97, seed=1, parent=None, location=(0, 0, 0), rotation=(0, 0, 0), coll="FX"):
    """Горячие точки на внутреннем краю кольца (радиус a·inner) по азимутам angles_deg, загораются в моменты times
    (те же единицы, что ключи time). Каждая — кучка из 2–4 шариков (неровное пятно). Возвращает dict(ob, mat)."""
    rnd = random.Random(seed)
    amps = amps or [0.6 + 0.4 * rnd.random() for _ in angles_deg]
    bm = bmesh.new()
    t_l, a_l = bm.verts.layers.float.new("t_on"), bm.verts.layers.float.new("amp")
    for ang, t, am in zip(angles_deg, times, amps):
        ph = math.radians(ang)
        for k in range(rnd.randint(2, 4)):
            jr = a * inner + size * (rnd.random() - 0.6) * 1.5
            jp = ph + (rnd.random() - 0.5) * size * 2.5 / a
            jz = size * (rnd.random() - 0.5) * 1.2
            rr = size * (0.45 + 0.6 * rnd.random()) * (1.0 if k == 0 else 0.7)
            res = bmesh.ops.create_icosphere(bm, subdivisions=2, radius=rr)
            for v in res["verts"]:
                v.co.x += jr * math.cos(jp)
                v.co.y += jr * math.sin(jp)
                v.co.z += jz
                v[t_l] = t + 0.15 * k * rnd.random()
                v[a_l] = am * (1.0 if k == 0 else 0.6)
    me = bpy.data.meshes.new(f"{name}_Mesh")
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    mat = _spot_material(f"{name}_Mat", color, rise, decay, flare)
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    C.link(ob, coll)
    ob.location = location
    ob.rotation_euler = rotation
    if parent is not None:
        ob.parent = parent
    _ghost(ob)
    return dict(ob=ob, mat=mat)


def key_value(obj, name, pairs, ipo="BEZIER"):
    """Ключи узла Value name в материале кольца/точек: pairs [(кадр, значение)]."""
    nt = obj["mat"].node_tree
    s = nt.nodes[name].outputs[0]
    for f, v in pairs:
        s.default_value = v
        s.keyframe_insert("default_value", frame=f)
    anim.set_interpolation(nt, ipo, path_contains=f'nodes["{name}"]')


def key_time(hs, pairs, ipo="LINEAR"):
    """Время (годы или кадры — как times у build_hotspots) по кадрам."""
    key_value(hs, "time", pairs, ipo)
