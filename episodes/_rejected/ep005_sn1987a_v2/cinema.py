"""Локальные материалы ep006: многомасштабная плазма и клочковатый газ.

Не меняем общие модули: новый визуал проверяется отдельно от ep005.
"""
import math

import bpy
from mathutils import Vector

from spacekit import anim as A
from spacekit import core as C
from spacekit.bodies.planets import _NB, _ghost
from spacekit.fx.sn_rings import _torus


def val(b, name, value):
    n = b.node("ShaderNodeValue", name=name)
    n.outputs[0].default_value = value
    return n.outputs[0]


def keys(mat, name, pairs):
    s = mat.node_tree.nodes[name].outputs[0]
    for frame, v in pairs:
        s.default_value = v
        s.keyframe_insert("default_value", frame=frame)
    A.set_interpolation(mat.node_tree, "LINEAR")


def ramp(b, x, stops):
    n = b.node("ShaderNodeValToRGB", {"Fac": x})
    cr = n.color_ramp
    for e in list(cr.elements)[2:]:
        cr.elements.remove(e)
    for i, (pos, rgb) in enumerate(stops):
        e = cr.elements[i] if i < 2 else cr.elements.new(pos)
        e.position, e.color = pos, (*rgb, 1)
    cr.interpolation = "EASE"
    return n.outputs["Color"]


def product(b, *args):
    x = args[0]
    for a in args[1:]:
        x = b.m("MULTIPLY", x, a)
    return x


def ridge(b, noise, power):
    return b.m("POWER", b.m("SUBTRACT", 1, b.m("ABSOLUTE", b.m("SUBTRACT", b.m("MULTIPLY", noise, 2), 1))), power)


def plasma():
    """Холодные каналы, горячие волокна и мелкое зерно; без глянца/плиток Вороного."""
    bpy.ops.mesh.primitive_uv_sphere_add(segments=256, ring_count=128, radius=1)
    ob = bpy.context.object
    ob.name = "E6_Photosphere"
    for p in ob.data.polygons:
        p.use_smooth = True
    mat, _, L, out = C.new_material("E6_Plasma")
    b = _NB(mat.node_tree)
    p = b.node("ShaderNodeTexCoord").outputs["Object"]
    flow, gain = val(b, "flow", 0.12), val(b, "gain", 1.0)
    fl = val(b, "flash", 0)
    warp = b.noise(p, 3.8, detail=4, rough=.7, w=flow).outputs["Color"]
    q = b.v("ADD", p, b.v("SCALE", b.v("SUBTRACT", warp, (.5, .5, .5)), scale=.24))
    large = b.noise(q, 8.0, detail=5, rough=.7, dist=.8, w=flow).outputs["Fac"]
    med = b.noise(q, 47, detail=4, rough=.72, dist=1.8, w=flow).outputs["Fac"]
    fine = b.noise(q, 210, detail=2.5, rough=.7, w=flow).outputs["Fac"]
    fil = ridge(b, med, 5.5)
    signal = b.m("ADD", product(b, large, .72), product(b, med, .28))
    col = ramp(b, signal, [(0, (.001, .004, .016)), (.39, (.005, .025, .11)),
                           (.54, (.018, .14, .52)), (.66, (.2, .6, 1)), (1, (.8, .93, 1))])
    lw = b.node("ShaderNodeLayerWeight", {"Blend": .5})
    mu = b.m("SUBTRACT", 1, lw.outputs["Facing"])
    texture = b.m("ADD", product(b, b.m("POWER", large, 4.2), 10), product(b, fil, fine, 1.7))
    intensity = product(b, b.m("ADD", .16, texture), b.m("ADD", .23, product(b, mu, .77)), gain)
    em = b.node("ShaderNodeEmission", {"Color": col, "Strength": intensity})
    burst = b.node("ShaderNodeEmission", {"Color": (.7, .86, 1, 1), "Strength": fl})
    ad = b.node("ShaderNodeAddShader", {0: em.outputs[0], 1: burst.outputs[0]})
    breakup = val(b, "breakup", 0)
    alpha = b.ss(b.m("SUBTRACT", large, breakup), -.08, .08)
    transparent = b.node("ShaderNodeBsdfTransparent")
    mix = b.node("ShaderNodeMixShader", {0: alpha, 1: transparent.outputs[0], 2: ad.outputs[0]})
    L.new(mix.outputs[0], out.inputs["Surface"])
    ob.data.materials.append(mat)
    mat.cycles.emission_sampling = "NONE"
    # Тонкий неоднородный слой над лимбом. Не модель солнечных магнитных петель.
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=4, radius=1.095)
    skin = bpy.context.object
    skin.name = "E6_LimbGas"
    vm, _, VL, vo = C.new_material("E6_LimbMat")
    vb = _NB(vm.node_tree)
    vp = vb.node("ShaderNodeTexCoord").outputs["Object"]
    rr = vb.v("LENGTH", vp)
    ns = vb.noise(vp, 37, detail=3.5, rough=.7).outputs["Fac"]
    bound = vb.m("ADD", 1.012, product(vb, vb.m("SUBTRACT", ns, .5), .04))
    above = vb.m("MAXIMUM", vb.m("SUBTRACT", rr, bound), 0)
    profile = product(vb, vb.ss(rr, 1.002, 1.009), vb.m("EXPONENT", product(vb, above, -95)))
    gain_limb = val(vb, "gain", 1)
    ve = vb.node("ShaderNodeEmission", {"Color": (.015, .2, .8, 1), "Strength": product(vb, profile, ns, 20, gain_limb)})
    VL.new(ve.outputs[0], vo.inputs["Volume"])
    vm.cycles.volume_step_rate = .045
    skin.data.materials.append(vm)
    return ob, mat


def gas_ring(parent, seed=198706, name="E6_RingGas"):
    """Кольцо с неровной кромкой и тремя масштабами структуры, не гладкий тор."""
    mat, _, L, out = C.new_material(name)
    b = _NB(mat.node_tree)
    p = b.node("ShaderNodeTexCoord").outputs["Object"]
    flow, gain = val(b, "flow", .13), val(b, "gain", 1.0)
    hit = val(b, "hit", 1.0)
    x, y, z = b.sep(p)
    rho = b.m("SQRT", b.m("ADD", product(b, x, x), product(b, y, y)))
    warp = b.noise(p, 4.8, detail=2, w=flow).outputs["Color"]
    q = b.v("ADD", p, b.v("SCALE", b.v("SUBTRACT", warp, (.5, .5, .5)), scale=.13))
    qx, qy, qz = b.sep(q)
    qr = b.m("SQRT", b.m("ADD", product(b, qx, qx), product(b, qy, qy)))
    dr = b.m("DIVIDE", b.m("SUBTRACT", qr, 1), .064)
    dz = b.m("DIVIDE", qz, .049)
    cross_r = b.m("SQRT", b.m("ADD", product(b, dr, dr), product(b, dz, dz)))
    shell_d = b.m("DIVIDE", b.m("SUBTRACT", cross_r, .9), .18)
    profile = b.m("EXPONENT", product(b, shell_d, shell_d, -1))
    cloud = b.noise(q, 14, detail=3.5, rough=.7, w=flow).outputs["Fac"]
    fine = b.noise(q, 80, detail=2, rough=.7, w=flow).outputs["Fac"]
    thin = product(b, ridge(b, b.noise(q, 22, detail=3, rough=.72, dist=.3, w=flow).outputs["Fac"], 12),
                      ridge(b, b.noise(b.v("ADD", q, (3.1, 5.7, 1.8)), 36, detail=2, w=flow).outputs["Fac"], 9))
    dens = product(b, profile, b.m("POWER", b.ss(cloud, .29, .72), 1.8), b.m("ADD", .18, product(b, fine, 1.8)))
    color = ramp(b, cloud, [(0, (.045, .008, .007)), (.35, (.21, .025, .012)),
                           (.54, (.86, .16, .06)), (.68, (1, .51, .27)), (1, (.8, .92, 1))])
    sector = b.noise(b.v("NORMALIZE", p), 9, detail=1.0).outputs["Fac"]
    onset = b.lin(sector, .28, .72, .02, .82)
    local_hit = b.ss(b.m("SUBTRACT", hit, onset), 0, .14)
    strength = product(b, dens, b.m("ADD", .25, product(b, thin, 750)), gain,
                       b.m("ADD", .15, product(b, local_hit, .85)))
    em = b.node("ShaderNodeEmission", {"Color": color, "Strength": strength})
    absorb = b.node("ShaderNodeVolumeAbsorption", {"Color": (.15, .045, .02, 1), "Density": product(b, dens, 1.4)})
    ad = b.node("ShaderNodeAddShader", {0: em.outputs[0], 1: absorb.outputs[0]})
    L.new(ad.outputs[0], out.inputs["Volume"])
    mat.cycles.volume_step_rate = .08
    me = _torus("E6_RingDomain", 1, .135, nu=128, nv=20)
    me.materials.append(mat)
    ob = bpy.data.objects.new("E6_Ring", me)
    C.link(ob, "FX")
    ob.parent = parent
    _ghost(ob)
    return ob, mat




def cooling_sheets(parent, prefix="E6_Cooling", widths=(.048, .072, .098), gain=1.0, phase=0.0):
    """Тонкие рваные светящиеся слои: нити сохраняются без интеграции в дымку.

    Несколько поверхностей с прозрачностью — приближение узких зон излучения,
    не твёрдая оболочка. Координаты/фазы фиксированы для петли.
    """
    mats = []
    for i, width in enumerate(widths):
        mat, _, L, out = C.new_material(f"{prefix}{i}")
        b = _NB(mat.node_tree)
        p = b.node("ShaderNodeTexCoord").outputs["Object"]
        warp = b.noise(p, 7, detail=3, rough=.68).outputs["Color"]
        q = b.v("ADD", b.v("ADD", p, (i * 1.71 + phase, i * 2.31, i * 3.13)),
                b.v("SCALE", b.v("SUBTRACT", warp, (.5, .5, .5)), scale=.12))
        large = b.noise(q, 18, detail=3, rough=.7).outputs["Fac"]
        a = ridge(b, b.noise(q, 45, detail=3.5, rough=.72, dist=.35).outputs["Fac"], 15)
        c = ridge(b, b.noise(q, 127, detail=2.5, rough=.67).outputs["Fac"], 18)
        web = b.m("ADD", product(b, a, .85), product(b, c, .45), clamp=True)
        lw = b.node("ShaderNodeLayerWeight", {"Blend": .5})
        feather = b.m("POWER", b.m("SUBTRACT", 1, lw.outputs["Facing"]), .6)
        mask = product(b, b.m("POWER", web, 2), b.ss(large, .44, .68), feather)
        color = ramp(b, large, [(0, (.08, .016, .01)), (.4, (.25, .065, .025)),
            (.55, (.85, .35, .12)), (.7, (.9, .72, .48)), (1, (.44, .7, .78))])
        hit = val(b, "hit", 1)
        sector = b.noise(b.v("NORMALIZE", p), 9, detail=1).outputs["Fac"]
        onset = b.lin(sector, .28, .72, .02, .82)
        local = b.m("ADD", .12, product(b, b.ss(b.m("SUBTRACT", hit, onset), 0, .14), .88))
        em = b.node("ShaderNodeEmission", {"Color": color, "Strength": product(b, local, .85 * gain)})
        tr = b.node("ShaderNodeBsdfTransparent")
        mx = b.node("ShaderNodeMixShader", {0: mask, 1: tr.outputs[0], 2: em.outputs[0]})
        L.new(mx.outputs[0], out.inputs["Surface"])
        mat.cycles.emission_sampling = "NONE"
        me = _torus(f"{prefix}Mesh{i}", 1, width, nu=384, nv=40)
        for v in me.vertices:
            ph = math.atan2(v.co.y, v.co.x)
            ripple = .012 * math.sin(ph * 17 + i) + .008 * math.sin(ph * 43 + i * 2)
            v.co.x *= 1 + ripple
            v.co.y *= 1 + ripple
            v.co.z += .012 * math.sin(ph * 21 + i * 3)
        me.materials.append(mat)
        for poly in me.polygons:
            poly.use_smooth = True
        ob = bpy.data.objects.new(f"{prefix}Sheet{i}", me)
        C.link(ob, "FX")
        ob.parent = parent
        _ghost(ob)
        mats.append(mat)
    return mats


def debris(parent):
    """Комковатый заполненный выброс с пылевыми прожилками, без полой скорлупы."""
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=1.1)
    ob = bpy.context.object
    ob.name = "E6_Ejecta"
    ob.parent = parent
    ob.scale = (.29, .25, .64)
    ob.rotation_euler = (0, .25, .15)
    mat, _, L, out = C.new_material("E6_EjectaMat")
    b = _NB(mat.node_tree)
    p = b.node("ShaderNodeTexCoord").outputs["Object"]
    warp = b.noise(p, 2.4, detail=2).outputs["Color"]
    q = b.v("ADD", p, b.v("SCALE", b.v("SUBTRACT", warp, (.5, .5, .5)), scale=.5))
    r = b.v("LENGTH", q)
    profile = b.ss(r, 1.05, .55)
    lumps = b.noise(q, 4.5, detail=3, rough=.72, dist=.6).outputs["Fac"]
    cl = b.m("POWER", b.ss(lumps, .46, .69), 2.0)
    fil = ridge(b, b.noise(q, 18, detail=2.5, rough=.7).outputs["Fac"], 8)
    dens = product(b, profile, cl, b.m("ADD", .035, product(b, fil, 2.2)))
    colors = ramp(b, lumps, [(0, (.018, .025, .03)), (.38, (.025, .17, .21)),
                             (.54, (.22, .5, .58)), (.68, (.65, .72, .7)), (1, (.46, .17, .055))])
    x, y, z = b.sep(p)
    hx = b.m("DIVIDE", b.m("ADD", x, .08), .26)
    hz = b.m("DIVIDE", b.m("SUBTRACT", z, .08), .38)
    dust_lane = b.m("EXPONENT", product(b, b.m("ADD", product(b, hx, hx), product(b, hz, hz)), -1))
    emission = product(b, dens, 14, b.m("SUBTRACT", 1, product(b, dust_lane, .94)))
    em = b.node("ShaderNodeEmission", {"Color": colors, "Strength": emission})
    dust = b.noise(q, 6.4, detail=2, rough=.7).outputs["Fac"]
    absorb = b.node("ShaderNodeVolumeAbsorption", {"Color": (.18, .075, .02, 1),
        "Density": product(b, profile, b.ss(dust, .43, .7), 3)})
    ad = b.node("ShaderNodeAddShader", {0: em.outputs[0], 1: absorb.outputs[0]})
    L.new(ad.outputs[0], out.inputs["Volume"])
    mat.cycles.volume_step_rate = .065
    ob.data.materials.append(mat)
    return dict(ob=ob, mat=mat)


def ring_system():
    root = C.empty("E6_Remnant")
    root.rotation_euler = (math.radians(43), math.radians(-9), math.radians(-18))
    _, gas = gas_ring(root)
    gas.node_tree.nodes["gain"].outputs[0].default_value = .12
    fil = cooling_sheets(root)
    ej = debris(root)
    for i, z in enumerate((1.12, -1.12)):
        # Слабые внешние дуги оптически тонкие: прозрачная поверхность
        # вместо дорогого пустого объёма на большой части кадра.
        anchor = C.empty(f"E6_Outer{i}", parent=root, loc=(0, 0, z))
        anchor.scale = (1.25, 1.25, .55)
        cooling_sheets(anchor, prefix=f"E6_OuterSheet{i}_", widths=(.072,), gain=.14, phase=17.3 * (i + 1))
    return root, gas, fil, ej

