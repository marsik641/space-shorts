"""Пылевое кольцо: тонкий клочковатый пояс, освещённый пульсаром аналитически (эмиссионный объём:
без шума и мерцания). Лучи-прожекторы рисуют на нём бегущие световые дуги («маяк»).

    from spacekit.fx import dust_ring
    dust_ring.build_dust_ring(sc, parent=psr["root"], inner=55, outer=78, thickness=3.5, ring_radiance=2.0,
                              anisotropy=0.3, lights=[psr["light"], *psr["spots"]], frame_start=1, frame_end=n)
Вызывать после пульсара (лампы читаются в момент вызова). Ставит scene.cycles.volume_biased.
"""
import math

import bpy
import bmesh
from mathutils import Vector

from .. import core as C

# ---------------------------------------------------------------- пылевое кольцо

def _ring_domain(name, r0, r1, h0, h1, seg=256):
    """Меш-домен: кольцевая призма с трапециевидным сечением (полувысота h0 у r0, h1 у r1), замкнутая."""
    bm = bmesh.new()
    rings = []
    for rr, zz in ((r0, -h0), (r1, -h1), (r1, h1), (r0, h0)):
        rings.append([bm.verts.new((rr * math.cos(2 * math.pi * i / seg),
                                    rr * math.sin(2 * math.pi * i / seg), zz)) for i in range(seg)])
    for a in range(4):
        A, B = rings[a], rings[(a + 1) % 4]
        for i in range(seg):
            j = (i + 1) % seg
            bm.faces.new((A[i], A[j], B[j], B[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me


def _mr(N, L, val, a, b, c, d, interp="SMOOTHSTEP", loc=(0, 0)):
    n = N.new("ShaderNodeMapRange"); n.location = loc
    n.interpolation_type = interp
    n.clamp = True
    L.new(val, n.inputs["Value"])
    for i, x in zip((1, 2, 3, 4), (a, b, c, d)):
        n.inputs[i].default_value = x
    return n.outputs["Result"]


def _noise(N, L, vec, scale, detail, rough, dims="3D", w=None, distortion=0.0, loc=(0, 0)):
    n = N.new("ShaderNodeTexNoise"); n.location = loc
    n.noise_dimensions = dims
    n.inputs["Scale"].default_value = scale
    n.inputs["Detail"].default_value = detail
    n.inputs["Roughness"].default_value = rough
    n.inputs["Distortion"].default_value = distortion
    if dims != "1D":
        L.new(vec, n.inputs["Vector"])
    if w is not None:
        if isinstance(w, (int, float)):
            n.inputs["W"].default_value = w
        else:
            L.new(w, n.inputs["W"])
    return n.outputs["Fac"]


def build_dust_ring(scene, parent=None, inner=48.0, outer=72.0, thickness=6.0, density=1.0, seed=1,
                    anisotropy=0.6, color=(0.95, 0.83, 0.66), rotation_period_s=None,
                    frame_start=1, frame_end=300, lights=None, mode="emission", flare=1.3, tilt_deg=4.0,
                    ring_radiance=4.0, arc_gain=3.0, arc_sigma=0.6, arc_cone=0.4, biased=True, coll="Env"):
    """Тонкое клочковатое пылевое кольцо в плоскости XY родителя, однократное рассеяние вперёд (HG, g=anisotropy).

    Геометрия: гауссов профиль по высоте с полутолщиной h(r) = 0.5·thickness·(r/inner)^flare (диск
    расширяется наружу, H/r≈0.12 — как у реальных пылевых дисков), наклон tilt_deg вокруг локальной X
    родителя: с α=78° (ось луча на 12° над плоскостью) лучи задевают пыль, и яркость дуг меняется по азимуту.
    mode="emission" (по умолчанию): освещение источниками в центре кольца считается аналитически в шейдере
        (1/r², фаза HG по направлению на камеру, конус каждого spot — по его текущей ориентации через
        Texture Coordinate/Object). Объём только излучает -> без шума и мерцания, в разы дешевле.
        Яркость НЕ зависит от абсолютной мощности ламп: нормировка на точечный свет —
        ring_radiance — «освещённость» на среднем радиусе (2.2 ≈ 1e5 Вт на r=60, прежний вид),
        отношение spot/point берётся из ламп пульсара, arc_gain — доп. множитель только для spot (дуги).
        Профиль дуги по углу θ от оси spot: exp(−(θ/(arc_sigma·θh))²) + arc_cone·кольцо на 0.8θh
        (ядро + полый конус, как у лучей neutron_star), θh — полуугол spot.
        lights — список объектов-ламп (POINT/SPOT) в центре; None — найти лампы ближе 0.25·inner к центру.
        Цвет/конус/отношение мощностей берутся в момент вызова (ключи energy не подхватываются). Тени нет.
    mode="scatter": честный Volume Scatter (любые лампы, тени, абсолютные мощности; ring_radiance/arc_gain
        не действуют), но дорого (~20 с/кадр 1080p) и шумнее.
    Края по радиусу и по высоте мягкие, плотность внутри домена спадает до нуля (граница домена не видна).
    density — множитель плотности (яркость ∝ density).
    rotation_period_s — медленное (кеплеровское) вращение кольца вокруг своей оси (ключи LINEAR), None — неподвижно.
    Масштаб объекта/родителя: яркость на среднем радиусе от него не зависит (кроме длины пути в объёме).
    biased=True (emission) — включить scene.cycles.volume_biased (ray marching, общая настройка сцены, её же
        ставит NS.setup_volume_denoise(sc, 'far')): эмиссионный объём интегрируется детерминированно —
        шум между сидами 28% -> 9% (как фон со звёздами), и быстрее. Без него на ходу камеры пыль «кипит».
    """
    width = outer - inner
    h0 = 0.5 * thickness
    warp_a = 0.35 * thickness                                   # амплитуда волнистости слоя
    r0, r1 = max(0.1, inner - 0.05 * width), outer + 0.05 * width
    hz = lambda rr: h0 * (rr / inner) ** flare
    me = _ring_domain("DustRing", r0, r1, 2.2 * hz(r0) + warp_a, 2.2 * hz(r1) + warp_a)
    ob = bpy.data.objects.new("DustRing", me)
    C.link(ob, coll)
    if parent is not None:
        ob.parent = parent
    # ZXY: сначала поворот вокруг своей оси (ключи Z), затем наклон по X — узлы наклона неподвижны
    ob.rotation_mode = "ZXY"
    ob.rotation_euler = (math.radians(tilt_deg), 0.0, 0.0)
    ob.visible_shadow = False
    ob.visible_diffuse = False
    ob.visible_glossy = False

    mat, N, L, out = C.new_material("DustRing")
    mat.cycles.volume_interpolation = "LINEAR"
    mat.cycles.volume_sampling = "DISTANCE"                     # в 2-3 раза быстрее MIS/equiangular, шум тот же
    tc = N.new("ShaderNodeTexCoord"); tc.location = (-1800, 0)
    P = tc.outputs["Object"]
    sep = N.new("ShaderNodeSeparateXYZ"); sep.location = (-1600, 0)
    L.new(P, sep.inputs[0])
    xy = N.new("ShaderNodeCombineXYZ"); xy.location = (-1400, 200)
    L.new(sep.outputs[0], xy.inputs[0]); L.new(sep.outputs[1], xy.inputs[1])
    ln = N.new("ShaderNodeVectorMath"); ln.operation = "LENGTH"; ln.location = (-1200, 250)
    L.new(xy.outputs[0], ln.inputs[0])
    r = ln.outputs["Value"]
    un = N.new("ShaderNodeVectorMath"); un.operation = "NORMALIZE"; un.location = (-1200, 100)
    L.new(xy.outputs[0], un.inputs[0])
    so = float(seed) * 17.31
    # сдвиг координат по seed (3D-шум дешевле 4D)
    ofs = N.new("ShaderNodeVectorMath"); ofs.operation = "ADD"; ofs.location = (-1400, -500)
    L.new(P, ofs.inputs[0]); ofs.inputs[1].default_value = (so, 0.7 * so, 1.3 * so)
    Ps = ofs.outputs[0]

    # нормированный радиус и радиальная огибающая (мягкие края)
    rn = C.math_node(N, L, "MULTIPLY_ADD", r, 1.0 / width, loc=(-1000, 300))
    rn.node.inputs[2].default_value = -inner / width
    e_in = _mr(N, L, rn, -0.02, 0.38, 0.0, 1.0, "SMOOTHERSTEP", loc=(-800, 400))
    e_out = _mr(N, L, rn, 0.55, 1.02, 1.0, 0.0, "SMOOTHERSTEP", loc=(-800, 250))
    e_r = C.math_node(N, L, "MULTIPLY", e_in, e_out, loc=(-600, 300))

    # тонкие радиальные «колечки» (1D шум по r)
    ring_n = _noise(N, L, P, 1.0, 5.0, 0.55, dims="1D", loc=(-800, 600))
    wr = C.math_node(N, L, "MULTIPLY_ADD", r, 0.55, loc=(-1000, 600))
    wr.node.inputs[2].default_value = so
    L.new(wr, ring_n.node.inputs["W"])
    ringlet = _mr(N, L, ring_n, 0.30, 0.70, 0.65, 1.0, loc=(-600, 600))

    # вытянутые по азимуту дуги/струи: 4D шум (u.x*A, u.y*A, r*B), W = z (бесшовно по азимуту)
    sA = N.new("ShaderNodeVectorMath"); sA.operation = "SCALE"; sA.location = (-1000, 100)
    L.new(un.outputs[0], sA.inputs[0]); sA.inputs["Scale"].default_value = 5.0
    rB = C.math_node(N, L, "MULTIPLY", r, 0.55, loc=(-1000, -50))
    cmb = N.new("ShaderNodeCombineXYZ"); cmb.location = (-800, 50)
    sx = N.new("ShaderNodeSeparateXYZ"); sx.location = (-900, 120)
    L.new(sA.outputs[0], sx.inputs[0])
    L.new(sx.outputs[0], cmb.inputs[0]); L.new(sx.outputs[1], cmb.inputs[1]); L.new(rB, cmb.inputs[2])
    wz = C.math_node(N, L, "MULTIPLY_ADD", sep.outputs[2], 0.35 * 3.0 / thickness, loc=(-1000, -150))
    wz.node.inputs[2].default_value = so + 3.7
    streak = _noise(N, L, cmb.outputs[0], 1.0, 6.0, 0.68, dims="4D", w=wz, distortion=0.1, loc=(-600, 50))
    clump = _mr(N, L, streak, 0.45, 0.72, 0.0, 1.0, "SMOOTHERSTEP", loc=(-400, 50))
    clump = C.math_node(N, L, "POWER", clump, 1.3, loc=(-250, 50))

    # изотропные клочья: модуляция плотности (не порог) -> рваные края струй
    wisp = _noise(N, L, Ps, 1.0 / 5.0, 5.0, 0.6, distortion=0.4, loc=(-600, -150))
    wmod = _mr(N, L, wisp, 0.30, 0.70, 0.2, 1.0, loc=(-400, -150))
    clump = C.math_node(N, L, "MULTIPLY", clump, wmod, loc=(-100, 0))
    # мелкая «пылевая» фактура (~1 ед.), чтобы струи не выглядели мазками кисти
    fine = _noise(N, L, Ps, 0.6, 3.0, 0.65, distortion=0.3, loc=(-600, -800))
    fmod = _mr(N, L, fine, 0.30, 0.70, 0.15, 1.0, "SMOOTHSTEP", loc=(-400, -800))
    clump = C.math_node(N, L, "MULTIPLY", clump, fmod, loc=(-50, -100))
    # зерно (~0.4 ед.): частицы, а не мазок
    grit = _noise(N, L, Ps, 2.5, 2.0, 0.7, loc=(-600, -1000))
    gmod = _mr(N, L, grit, 0.35, 0.65, 0.55, 1.0, "LINEAR", loc=(-400, -1000))
    clump = C.math_node(N, L, "MULTIPLY", clump, gmod, loc=(-30, -150))
    # крупномасштабная неоднородность по азимуту: плотные дуги и почти пустые участки
    sB = N.new("ShaderNodeVectorMath"); sB.operation = "SCALE"; sB.location = (-1000, -600)
    L.new(un.outputs[0], sB.inputs[0]); sB.inputs["Scale"].default_value = 0.9
    sB2 = N.new("ShaderNodeVectorMath"); sB2.operation = "ADD"; sB2.location = (-900, -650)
    L.new(sB.outputs[0], sB2.inputs[0]); sB2.inputs[1].default_value = (0.0, 0.0, so + 21.0)
    big = _noise(N, L, sB2.outputs[0], 1.0, 2.0, 0.5, loc=(-800, -600))
    bmod = _mr(N, L, big, 0.36, 0.64, 0.2, 1.0, loc=(-600, -600))
    clump = C.math_node(N, L, "MULTIPLY", clump, bmod, loc=(0, -50))

    # волнистость слоя по высоте (±warp_a) и расширение наружу h(r)
    warp = _noise(N, L, Ps, 1.0 / 45.0, 2.0, 0.5, loc=(-1000, -350))
    zw = C.math_node(N, L, "MULTIPLY_ADD", warp, -2.0 * warp_a, loc=(-800, -350))
    zw.node.inputs[2].default_value = warp_a
    zz = C.math_node(N, L, "ADD", sep.outputs[2], zw, loc=(-650, -350))
    hr = C.math_node(N, L, "POWER", C.math_node(N, L, "DIVIDE", r, inner, loc=(-800, -450)), flare,
                     loc=(-700, -450))
    hr = C.math_node(N, L, "MULTIPLY", hr, h0, loc=(-600, -450))
    zq = C.math_node(N, L, "DIVIDE", zz, hr, loc=(-500, -350))
    e_z = C.math_node(N, L, "EXPONENT",
                      C.math_node(N, L, "MULTIPLY", C.math_node(N, L, "MULTIPLY", zq, zq, loc=(-400, -350)),
                                  -1.0, loc=(-300, -350)), loc=(-200, -350))

    d = C.math_node(N, L, "MULTIPLY", e_r, e_z, loc=(0, 200))
    d = C.math_node(N, L, "MULTIPLY", d, clump, loc=(100, 150))
    d = C.math_node(N, L, "MULTIPLY", d, ringlet, loc=(200, 150))
    d = C.math_node(N, L, "MULTIPLY", d, 0.5 * density, loc=(300, 150))

    if mode == "scatter":
        vs = N.new("ShaderNodeVolumeScatter"); vs.location = (400, 0)
        vs.inputs["Color"].default_value = (*color, 1.0)
        vs.inputs["Anisotropy"].default_value = anisotropy
        L.new(d, vs.inputs["Density"])
        L.new(vs.outputs[0], out.inputs["Volume"])
    else:
        if lights is None:
            lights = _central_lights(ob, 0.25 * inner)
        r_mid = 0.5 * (inner + outer)
        k = 1.0
        if ring_radiance is not None and lights:
            pts = [lo.data.energy for lo in lights if lo.data.type == "POINT"]
            p_ref = sum(pts) if pts else max(lo.data.energy for lo in lights)
            k = ring_radiance * 4.0 * math.pi * r_mid ** 2 / max(p_ref, 1e-9)
        em = _ring_emission(N, L, P, d, lights, anisotropy, color, eps=0.1 * inner, k=k,
                            arc_gain=arc_gain, arc_sigma=arc_sigma, arc_cone=arc_cone)
        L.new(em, out.inputs["Volume"])
        ob["ring_k"] = k
        if biased and not scene.cycles.volume_biased:
            scene.cycles.volume_biased = True
            print("[dust_ring] build_dust_ring: scene.cycles.volume_biased = True (ray marching)")
    ob["ring_lights"] = ", ".join(lo.name for lo in (lights or []))
    me.materials.append(mat)

    if rotation_period_s:
        fps = scene.render.fps / scene.render.fps_base
        for f in (frame_start, frame_end):
            ob.rotation_euler[2] = 2 * math.pi * (f - frame_start) / (rotation_period_s * fps)
            ob.keyframe_insert("rotation_euler", index=2, frame=f)
        _linear(ob)
    return ob


# Калибровка: Cycles-лампа мощностью P даёт интенсивность P/(4π) Вт/ср (сверено с mode="scatter": 1.00±0.03)
_LIGHT_K = 1.0


def _central_lights(ring, radius):
    """Лампы (POINT/SPOT), стоящие у центра кольца."""
    bpy.context.view_layer.update()
    c = ring.matrix_world.translation
    out = []
    for o in bpy.context.scene.objects:
        if o.type == "LIGHT" and o.data.type in ("POINT", "SPOT"):
            if (o.matrix_world.translation - c).length <= radius:
                out.append(o)
    return out


def _vm(N, L, op, a, b=None, loc=(0, 0)):
    n = N.new("ShaderNodeVectorMath"); n.operation = op; n.location = loc
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (tuple, list)):
            n.inputs[i].default_value = v
        else:
            L.new(v, n.inputs[i])
    return n


def _ring_emission(N, L, P, dens, lights, g, albedo, eps, k=1.0, arc_gain=1.0, arc_sigma=0.6, arc_cone=0.4):
    """Аналитическое однократное рассеяние света из центра кольца -> Emission объёма.
    k — нормировка мощностей (см. build_dust_ring), arc_gain — множитель spot-ламп."""
    # направление от центра (в мире) и фаза Хеньи–Гринстейна относительно направления на камеру
    nrm = _vm(N, L, "NORMALIZE", P, loc=(500, -500))
    vt = N.new("ShaderNodeVectorTransform"); vt.location = (650, -500)
    vt.vector_type = "VECTOR"; vt.convert_from = "OBJECT"; vt.convert_to = "WORLD"
    L.new(nrm.outputs[0], vt.inputs[0])
    nw = _vm(N, L, "NORMALIZE", vt.outputs[0], loc=(800, -500))
    geo = N.new("ShaderNodeNewGeometry"); geo.location = (650, -700)
    cth = _vm(N, L, "DOT_PRODUCT", nw.outputs[0], geo.outputs["Incoming"], loc=(950, -550)).outputs["Value"]
    den = C.math_node(N, L, "MULTIPLY_ADD", cth, -2.0 * g, loc=(1100, -550))
    den.node.inputs[2].default_value = 1.0 + g * g
    den = C.math_node(N, L, "POWER", den, 1.5, loc=(1250, -550))
    phase = C.math_node(N, L, "DIVIDE", (1.0 - g * g) / (4.0 * math.pi), den, loc=(1400, -550))
    # 1/r² в координатах кольца (смягчено eps у центра); с нормировкой k яркость масштабо-независима
    r2 = _vm(N, L, "DOT_PRODUCT", P, P, loc=(500, -850)).outputs["Value"]
    r2 = C.math_node(N, L, "ADD", r2, eps * eps, loc=(650, -850))
    strength = C.math_node(N, L, "DIVIDE", phase, r2, loc=(1550, -600))
    strength = C.math_node(N, L, "MULTIPLY", strength, dens, loc=(1700, -500))
    # сумма источников: цвет·интенсивность·маска конуса
    acc = None
    for i, lo in enumerate(lights):
        ld = lo.data
        inten = ld.energy / (4.0 * math.pi) * _LIGHT_K * k
        if ld.type == "SPOT":
            inten *= arc_gain
        col = tuple(c * inten for c in ld.color)
        y = -1200 - 300 * i
        if ld.type == "SPOT":
            tcl = N.new("ShaderNodeTexCoord"); tcl.location = (300, y); tcl.object = lo
            ps = tcl.outputs["Object"]
            ln = _vm(N, L, "LENGTH", ps, loc=(450, y)).outputs["Value"]
            sz = N.new("ShaderNodeSeparateXYZ"); sz.location = (450, y - 100)
            L.new(ps, sz.inputs[0])
            ca = C.math_node(N, L, "DIVIDE", sz.outputs[2],
                             C.math_node(N, L, "MAXIMUM", ln, 1e-6, loc=(550, y)), loc=(650, y))
            ca = C.math_node(N, L, "MULTIPLY", ca, -1.0, loc=(700, y), clamp=False)   # ось spot — локальная -Z
            ca = C.math_node(N, L, "MINIMUM", C.math_node(N, L, "MAXIMUM", ca, -1.0, loc=(720, y)), 1.0,
                             loc=(740, y))
            th = C.math_node(N, L, "ARCCOSINE", ca, loc=(780, y))                    # угол от оси, рад
            thh = 0.5 * ld.spot_size
            # ядро — гаусс по углу, + полое коническое кольцо (как профиль лучей пульсара); без резких краёв
            q = C.math_node(N, L, "DIVIDE", th, arc_sigma * thh, loc=(820, y))
            mask = C.math_node(N, L, "EXPONENT", C.math_node(N, L, "MULTIPLY", C.math_node(
                N, L, "MULTIPLY", q, q, loc=(860, y)), -1.0, loc=(900, y)), loc=(940, y))
            if arc_cone > 0:
                q2 = C.math_node(N, L, "MULTIPLY_ADD", th, 1.0 / (0.15 * thh), loc=(820, y - 120))
                q2.node.inputs[2].default_value = -0.8 / 0.15
                cone = C.math_node(N, L, "EXPONENT", C.math_node(N, L, "MULTIPLY", C.math_node(
                    N, L, "MULTIPLY", q2, q2, loc=(860, y - 120)), -1.0, loc=(900, y - 120)), loc=(940, y - 120))
                ma = C.math_node(N, L, "MULTIPLY_ADD", cone, arc_cone, loc=(980, y))
                L.new(mask, ma.node.inputs[2])
                mask = ma
            term = _vm(N, L, "SCALE", col, None, loc=(1050, y))
            L.new(mask, term.inputs["Scale"])
            term = term.outputs[0]
        else:
            term = _vm(N, L, "ADD", col, (0.0, 0.0, 0.0), loc=(1050, y)).outputs[0]
        acc = term if acc is None else _vm(N, L, "ADD", acc, term, loc=(1200, y)).outputs[0]
    em = N.new("ShaderNodeEmission"); em.location = (1900, -400)
    if acc is not None:
        colv = _vm(N, L, "MULTIPLY", acc, tuple(albedo), loc=(1500, -900))
        L.new(colv.outputs[0], em.inputs["Color"])
        L.new(strength, em.inputs["Strength"])
    else:
        em.inputs["Strength"].default_value = 0.0
    return em.outputs[0]


def _linear(ob):
    ad = ob.animation_data
    if ad is None or ad.action is None:
        return
    act = ad.action
    curves = []
    if hasattr(act, "fcurves"):
        try:
            curves = list(act.fcurves)
        except Exception:
            curves = []
    if not curves and hasattr(act, "layers"):
        for lay in act.layers:
            for st in lay.strips:
                for cb in st.channelbags:
                    curves.extend(cb.fcurves)
    for fc in curves:
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
