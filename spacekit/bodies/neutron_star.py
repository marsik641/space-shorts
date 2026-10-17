"""Пульсар: нейтронная звезда, лучи, прожекторы, линии поля, частицы (Blender 5.2, Cycles).

Иерархия: PSR_Root (empty, центр системы, Z = ось вращения)
            > PSR_Spin (ключи LINEAR вращения вокруг Z, экстраполяция)
              > PSR_Mag (наклон alpha вокруг X; его +Z = северный магнитный полюс/луч)
Поверхность, лучи, прожекторы, линии поля и частицы — дети PSR_Mag (коротируют).

Импорт:  import neutron_star as NS;  objs = NS.build_pulsar(scene, ...)
"""
import math
import random

import bpy
import bmesh
from mathutils import Matrix, Vector

from .. import core as C
from ..render import setup_star_layer, setup_volume_denoise  # noqa: F401  (совместимость: NS.setup_*)

COLL = "PSR"
# цвета (линейный Rec.709)
BEAM_CORE_RGB = (0.62, 0.78, 1.00)    # ядро луча — бело-голубое
BEAM_EDGE_RGB = (0.30, 0.42, 1.00)    # край/кольцо — фиолетово-синий
FIELD_RGB = (0.45, 0.85, 1.00)        # линии поля — бледный циан
SURF_TEMP = 32000.0                   # «цвет» поверхности (предел чёрного тела ~ голубовато-белый)


# ---------------------------------------------------------------- узлы: мелкие помощники
class _NB:
    """Короткие обёртки над узлами шейдера/GN, чтобы граф читался как формула."""

    def __init__(self, nodes, links):
        self.n, self.l = nodes, links

    def m(self, op, a, b=None, clamp=False):
        return C.math_node(self.n, self.l, op, a, b, clamp=clamp)

    def add(self, a, b): return self.m("ADD", a, b)
    def sub(self, a, b): return self.m("SUBTRACT", a, b)
    def mul(self, a, b): return self.m("MULTIPLY", a, b)
    def div(self, a, b): return self.m("DIVIDE", a, b)

    def sep(self, vec):
        s = self.n.new("ShaderNodeSeparateXYZ")
        self.l.new(vec, s.inputs[0])
        return s.outputs[0], s.outputs[1], s.outputs[2]

    def comb(self, x, y, z):
        c = self.n.new("ShaderNodeCombineXYZ")
        for i, v in enumerate((x, y, z)):
            if isinstance(v, (int, float)):
                c.inputs[i].default_value = v
            else:
                self.l.new(v, c.inputs[i])
        return c.outputs[0]

    def vm(self, op, a, b=None):
        v = self.n.new("ShaderNodeVectorMath")
        v.operation = op
        for i, s in enumerate((a, b)):
            if s is None:
                continue
            if isinstance(s, (tuple, list)):
                v.inputs[i].default_value = s
            else:
                self.l.new(s, v.inputs[i])
        return v.outputs["Value"] if op in ("LENGTH", "DOT_PRODUCT", "DISTANCE") else v.outputs["Vector"]

    def smooth(self, e0, e1, x):
        """smoothstep(e0, e1, x) через Map Range (e0 > e1 — обратная ступень)."""
        r = self.n.new("ShaderNodeMapRange")
        r.interpolation_type = "SMOOTHSTEP"
        r.clamp = True
        self.l.new(x, r.inputs[0])
        r.inputs[1].default_value = e0
        r.inputs[2].default_value = e1
        r.inputs[3].default_value = 0.0
        r.inputs[4].default_value = 1.0
        return r.outputs[0]

    def noise(self, vec, scale=1.0, detail=2.0, rough=0.5, dist=0.0):
        t = self.n.new("ShaderNodeTexNoise")
        t.noise_dimensions = "3D"
        self.l.new(vec, t.inputs["Vector"])
        t.inputs["Scale"].default_value = scale
        t.inputs["Detail"].default_value = detail
        t.inputs["Roughness"].default_value = rough
        t.inputs["Distortion"].default_value = dist
        return t.outputs["Fac"]

    def mix_rgb(self, fac, a, b):
        mx = self.n.new("ShaderNodeMix")
        mx.data_type = "RGBA"
        self.l.new(fac, mx.inputs["Factor"])
        for sock, v in ((mx.inputs[6], a), (mx.inputs[7], b)):
            if isinstance(v, (tuple, list)):
                sock.default_value = (*v[:3], 1.0)
            else:
                self.l.new(v, sock)
        return mx.outputs[2]

    def value(self, name, v=0.0):
        n = self.n.new("ShaderNodeValue")
        n.name = n.label = name
        n.outputs[0].default_value = v
        return n


def _channel_fcurves(id_data):
    """F-кривые ID (слотовые экшены Blender 5.x)."""
    ad = id_data.animation_data
    if ad is None or ad.action is None:
        return []
    from bpy_extras import anim_utils
    cb = anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)
    return list(cb.fcurves) if cb else []


def _linearize(id_data, extrapolate=True, path_contains=None):
    for fc in _channel_fcurves(id_data):
        if path_contains and path_contains not in fc.data_path:
            continue
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
        if extrapolate:
            fc.extrapolation = "LINEAR"


def _camera_only(ob):
    """Объект виден только камере: не светит, не отбрасывает тени, не отражается."""
    ob.visible_shadow = False
    ob.visible_diffuse = False
    ob.visible_glossy = False
    ob.visible_transmission = False
    ob.visible_volume_scatter = False


def _smooth_sphere(name, radius, segs=192, rings=96):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=rings, radius=radius)
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    return me


def _cone_domain(name, z_apex, z_end, tan_half, segs=96):
    """Закрытый усечённый конус от z=0 до z_end; вершина (виртуальная) в z=-z_apex."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    r0 = z_apex * tan_half
    r1 = (z_end + z_apex) * tan_half
    nz = 12                                   # продольные кольца — ровный силуэт без длинных треугольников
    rings = []
    for k in range(nz + 1):
        z = z_end * k / nz
        r = r0 + (r1 - r0) * k / nz
        rings.append([bm.verts.new((r * math.cos(2 * math.pi * i / segs),
                                    r * math.sin(2 * math.pi * i / segs), z)) for i in range(segs)])
    for k in range(nz):
        a, b = rings[k], rings[k + 1]
        for i in range(segs):
            j = (i + 1) % segs
            bm.faces.new((a[i], a[j], b[j], b[i]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    return me


# ---------------------------------------------------------------- материалы
def _surface_material(name, R, alpha_cap_deg=11.0, base_strength=2.4, cap_gain=2.5, far=False):
    """Эмиссия поверхности: шапки у магнитных полюсов, слабая пятнистость, потемнение к краю."""
    mat, nodes, links, out = C.new_material(name)
    b = _NB(nodes, links)
    tc = nodes.new("ShaderNodeTexCoord")
    geo = nodes.new("ShaderNodeNewGeometry")
    n = b.vm("NORMALIZE", tc.outputs["Object"])
    _, _, nz = b.sep(n)
    anz = b.m("ABSOLUTE", nz)
    # горячая шапка (ядро) + тёплый ореол вокруг
    cap = b.smooth(math.cos(math.radians(alpha_cap_deg)), math.cos(math.radians(alpha_cap_deg * 0.35)), anz)
    halo = b.smooth(math.cos(math.radians(alpha_cap_deg * 2.6)), math.cos(math.radians(alpha_cap_deg * 0.8)), anz)
    # пятнистость: две октавы, низкий контраст (после AgX ≈ ±0.05 дисплейной яркости — вращение читается)
    n1 = b.noise(n, scale=2.0, detail=2.0, rough=0.5)
    n2 = b.noise(n, scale=10.0, detail=1.5, rough=0.5, dist=0.3)
    mot = b.add(b.mul(b.sub(n1, 0.5), 0.45), b.mul(b.sub(n2, 0.5), 0.15))   # ~ ±0.08: гладкая раскалённая поверхность
    # потемнение к краю: mu = N·V; пол 0.22 — гравитационный изгиб лучей ослабляет потемнение
    # (и нет «стеклянного пузыря» с тёмным контуром на фоне луча)
    mu = b.m("MAXIMUM", b.vm("DOT_PRODUCT", geo.outputs["Normal"], geo.outputs["Incoming"]), 0.0)
    limb = b.add(0.22, b.mul(0.78, b.m("POWER", mu, 1.2)))
    # яркость
    s = b.mul(b.add(1.0, mot), limb)
    s = b.mul(s, b.add(1.0, b.add(b.mul(cap, cap_gain), b.mul(halo, 0.45))))
    flash = b.value("PSR_Flash", 0.0)
    if far:
        s = b.mul(s, b.add(1.0, b.mul(flash.outputs[0], 10.0)))
    else:  # импульс — пучковое излучение из области шапки: вспышка сосредоточена у неё
        foc = b.add(0.35, b.mul(0.65, b.m("MAXIMUM", cap, halo)))
        s = b.mul(s, b.add(1.0, b.mul(b.mul(flash.outputs[0], foc), 3.0)))
    s = b.mul(s, base_strength)
    # цвет: голубовато-белый, пятна чуть теплее/холоднее, шапки белее
    c_cool = C.blackbody_rgb(SURF_TEMP * 1.3)
    c_warm = C.blackbody_rgb(SURF_TEMP * 0.8)
    tcol = b.mix_rgb(b.smooth(-0.3, 0.3, mot), c_warm, c_cool)
    # лимб: внешние, более холодные слои — чуть теплее оттенок (fac ≤ 0.3)
    tcol = b.mix_rgb(b.mul(b.smooth(0.75, 0.05, mu), 0.3), tcol, C.blackbody_rgb(SURF_TEMP * 0.7))
    col = b.mix_rgb(b.m("MAXIMUM", cap, b.mul(halo, 0.3)), tcol, (0.92, 0.95, 1.0))
    em = nodes.new("ShaderNodeEmission")
    links.new(col, em.inputs["Color"])
    links.new(s, em.inputs["Strength"])
    links.new(em.outputs[0], out.inputs["Surface"])
    mat.cycles.emission_sampling = "NONE"
    return mat


def _beam_material(name, *, R, L, tan_core, z_apex, intensity, z0, speed, seed=0.0, angular_fade=False, flash_gain=1.5):
    """Объёмная эмиссия луча в координатах объекта-домена (+Z — ось луча).

    Профиль в угловых единицах ядра rho = r / ((z+z_apex)·tan_core):
      ядро exp(-(rho/0.35)^2) + полое коническое кольцо на rho≈1.35 (амплитуда 0.4) + слабый ореол,
      гладкое затухание к rho=2.2 (стенка домена на 2.6) и к дальнему концу;
      вдоль оси ~ 1/(z^2+z0^2); струйки — шум в (u, v, ln z − speed·t), бегущий наружу.
    Камера внутри луча: объём гасится по ViewDistance/zz (относительно расстояния до звезды),
    иначе весь кадр заливает плоская серая пелена.
    """
    mat, nodes, links, out = C.new_material(name)
    b = _NB(nodes, links)
    tc = nodes.new("ShaderNodeTexCoord")
    x, y, z = b.sep(tc.outputs["Object"])
    zz = b.m("MAXIMUM", b.add(z, z_apex), 1e-3)
    k = b.mul(zz, tan_core)
    u = b.div(x, k)
    v = b.div(y, k)
    rho = b.m("SQRT", b.add(b.mul(u, u), b.mul(v, v)))
    # профиль ядро + кольцо
    core = b.m("EXPONENT", b.mul(b.mul(rho, rho), -1.0 / 0.35 ** 2))
    dr = b.div(b.sub(rho, 1.35), 0.22)
    ring = b.mul(b.m("EXPONENT", b.mul(b.mul(dr, dr), -1.0)), 0.40)
    halo = b.mul(b.m("EXPONENT", b.mul(b.mul(rho, rho), -1.0 / 1.6 ** 2)), 0.05)
    wall = b.smooth(2.3, 1.4, rho)                    # 1 внутри, 0 у стенки (мягко)
    # время (ключи LINEAR) и струйки
    tnode = b.value("PSR_Time", 0.0)
    t = tnode.outputs[0]
    lz = b.m("LOGARITHM", b.div(zz, R), math.e)
    w = b.sub(lz, b.mul(t, speed))
    knots = b.noise(b.comb(b.mul(u, 0.9), b.mul(v, 0.9), b.add(b.mul(w, 2.4), seed)), scale=1.0, detail=2.0, rough=0.5)
    fil = b.noise(b.comb(b.mul(u, 3.2), b.mul(v, 3.2), b.add(b.mul(w, 0.8), seed + 7.3)), scale=1.0, detail=1.0, rough=0.5)
    mk = b.add(0.35, b.mul(1.3, b.smooth(0.30, 0.72, knots)))     # 0.35..1.65 — сгустки
    mf = b.add(0.75, b.mul(0.5, b.smooth(0.35, 0.65, fil)))       # 0.75..1.25 — волокна
    mod = b.mul(mk, mf)
    # кольцо модулируется слабо (ровный полый конус, не тонет в сгустках)
    prof = b.add(b.mul(core, mod), b.mul(b.add(ring, halo), b.add(0.8, b.mul(0.2, mod))))
    # вдоль оси: 1/(z^2+z0^2), нормировано на z0; дальнее затухание
    fall = b.div(z0 * z0, b.add(b.mul(zz, zz), z0 * z0))
    far = b.smooth(L * 0.98, L * 0.45, z)
    near = b.smooth(0.0, R * 0.6, z)                    # не светить из-под центра
    cam = nodes.new("ShaderNodeCameraData")             # камера внутри луча: гасим ближний объём,
    vd = cam.outputs["View Distance"]                   # иначе серая пелена на весь кадр
    near = b.mul(near, b.smooth(0.5 * R, 5.0 * R, vd))                  # абсолютно — у самой камеры
    if angular_fade:
        # крупный план: гасим только лучи зрения почти вдоль оси луча (без «пузыря» вокруг камеры)
        geo = nodes.new("ShaderNodeNewGeometry")
        vt = nodes.new("ShaderNodeVectorTransform")
        vt.vector_type = "VECTOR"
        vt.convert_from = "WORLD"
        vt.convert_to = "OBJECT"
        links.new(geo.outputs["Incoming"], vt.inputs[0])
        _, _, iz = b.sep(b.vm("NORMALIZE", vt.outputs[0]))
        near = b.mul(near, b.smooth(0.975, 0.86, b.m("ABSOLUTE", iz)))
    else:
        near = b.mul(near, b.smooth(0.15, 0.7, b.div(vd, zz)))          # относительно — дальше по лучу
    flash = b.value("PSR_Flash", 0.0)
    gain = b.mul(b.add(1.0, b.mul(flash.outputs[0], flash_gain)), intensity)
    dens = b.mul(b.mul(b.mul(b.mul(prof, wall), fall), b.mul(far, near)), gain)
    # цвет: ядро бело-голубое -> края фиолетово-синие
    col = b.mix_rgb(b.smooth(0.25, 1.3, rho), BEAM_CORE_RGB, BEAM_EDGE_RGB)
    em = nodes.new("ShaderNodeEmission")
    links.new(col, em.inputs["Color"])
    links.new(dens, em.inputs["Strength"])
    links.new(em.outputs[0], out.inputs["Volume"])
    mat.cycles.volume_sampling = "DISTANCE"
    mat.cycles.volume_interpolation = "LINEAR"
    mat.cycles.volume_step_rate = 0.5
    return mat, tnode, flash


def _field_material(name, R, strength, r_fade_in, r_fade_out, falloff=1.2, apex_dim=0.0):
    """Аддитивная эмиссия линий поля (Transparent + Emission), гаснет с расстоянием.
    apex_dim — насколько тускнеет вершина петли (у магнитного экватора, |z|/r → 0)."""
    mat, nodes, links, out = C.new_material(name)
    b = _NB(nodes, links)
    tc = nodes.new("ShaderNodeTexCoord")
    rr = b.vm("LENGTH", tc.outputs["Object"])
    r = b.div(rr, R)
    s = b.m("POWER", b.m("MAXIMUM", r, 1.0), -falloff)
    s = b.mul(s, b.smooth(r_fade_out, r_fade_in, r))
    if apex_dim > 0.0:
        _, _, oz = b.sep(tc.outputs["Object"])
        lat = b.div(b.m("ABSOLUTE", oz), b.m("MAXIMUM", rr, 1e-4))
        s = b.mul(s, b.add(1.0 - apex_dim, b.mul(apex_dim, b.smooth(0.0, 0.75, lat))))
    cam = nodes.new("ShaderNodeCameraData")
    # гасить у камеры: вблизи нить толстая, и моушн-блюр вращения делает из неё ленту с двойной кромкой
    s = b.mul(s, b.smooth(1.5 * R, 4.0 * R, cam.outputs["View Distance"]))
    s = b.mul(s, strength)
    em = nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*FIELD_RGB, 1.0)
    links.new(s, em.inputs["Strength"])
    tr = nodes.new("ShaderNodeBsdfTransparent")
    ad = nodes.new("ShaderNodeAddShader")
    links.new(tr.outputs[0], ad.inputs[0])
    links.new(em.outputs[0], ad.inputs[1])
    links.new(ad.outputs[0], out.inputs["Surface"])
    mat.cycles.emission_sampling = "NONE"
    return mat


# ---------------------------------------------------------------- линии поля
def _dipole_points(L, phi, R, theta_lo, theta_hi, n):
    pts = []
    for i in range(n):
        th = theta_lo + (theta_hi - theta_lo) * i / (n - 1)
        r = L * R * math.sin(th) ** 2
        pts.append((r * math.sin(th) * math.cos(phi), r * math.sin(th) * math.sin(phi), r * math.cos(th)))
    return pts


def _add_poly(cu, pts, mat_index=0):
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for p, c in zip(sp.points, pts):
        p.co = (*c, 1.0)
    sp.material_index = mat_index


FIELD_GAINS = (0.35, 0.6, 1.0)         # случайная яркость сплайна (через слоты материалов)


def _field_mats(cu, name, R, strength, r_fade_out, falloff, apex_dim):
    for k, g in enumerate(FIELD_GAINS):
        cu.materials.append(_field_material(f"{name}_{k}", R, strength * g, 1.0, r_fade_out,
                                            falloff=falloff, apex_dim=apex_dim))


def _build_field_lines(mag, R, seed=3, thickness=0.002, strength=1.0, Ls=(1.9, 2.6, 3.5, 4.7),
                       r_fade_out=6.0):
    """Тонкие нити: замкнутые дипольные оболочки r = L sin^2(theta) + открытые линии из шапок.
    Внешние петли гаснут к r_fade_out: при моушн-блюре вращения они иначе становятся лентами."""
    rnd = random.Random(seed)
    cu = bpy.data.curves.new("PSR_FieldClosed", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = thickness * R
    cu.bevel_resolution = 1
    cu.use_fill_caps = False
    for j, Lv in enumerate(Ls):
        n_az = 4 if Lv < 5 else 3
        base = rnd.uniform(0, 2 * math.pi)
        for a in range(n_az):
            phi = base + 2 * math.pi * a / n_az + rnd.uniform(-0.35, 0.35)
            th0 = math.asin(math.sqrt(min(0.98 / Lv, 1.0)))
            n = int(80 + 22 * Lv)
            _add_poly(cu, _dipole_points(Lv, phi, R, th0, math.pi - th0, n), rnd.randrange(len(FIELD_GAINS)))
    closed = bpy.data.objects.new("PSR_FieldClosed", cu)
    C.link(closed, COLL)
    closed.parent = mag
    _field_mats(cu, "PSR_FieldClosed", R, 0.22 * strength, r_fade_out, 1.1, 0.5)
    _camera_only(closed)
    closed.cycles.motion_steps = 3          # блюр вращения — дугой, а не хордой
    # открытые: из полярных шапок, L > радиуса светового цилиндра (~27 R), веером в луч
    cu2 = bpy.data.curves.new("PSR_FieldOpen", "CURVE")
    cu2.dimensions = "3D"
    cu2.bevel_depth = thickness * 0.8 * R
    cu2.bevel_resolution = 1
    cu2.use_fill_caps = False
    r_max = 11.0
    for pole in (1, -1):
        for Lv in (30.0, 48.0, 80.0, 150.0):
            base = rnd.uniform(0, 2 * math.pi)
            for a in range(4):
                phi = base + 2 * math.pi * a / 4 + rnd.uniform(-0.4, 0.4)
                th0 = math.asin(math.sqrt(0.98 / Lv))
                th1 = math.asin(math.sqrt(r_max / Lv))
                pts = _dipole_points(Lv, phi, R, th0, th1, 90)
                if pole < 0:
                    pts = [(px, py, -pz) for px, py, pz in pts]
                _add_poly(cu2, pts, rnd.randrange(len(FIELD_GAINS)))
    opn = bpy.data.objects.new("PSR_FieldOpen", cu2)
    C.link(opn, COLL)
    opn.parent = mag
    _field_mats(cu2, "PSR_FieldOpen", R, 0.24 * strength, r_max * 0.85, 0.9, 0.0)
    _camera_only(opn)
    opn.cycles.motion_steps = 3
    return closed, opn


# ---------------------------------------------------------------- частицы вдоль лучей
def _build_particles(mag, R, tan_core, z_apex, count=36, z_min=1.15, z_max=7.0, rate=0.45,
                     radius=0.0018, strength=0.25, streak=0.025, seed=11):
    """Короткие светящиеся штрихи (hair curves, 4 точки) бегут наружу вдоль обоих лучей.
    Время — Scene Time в GN (без драйверов). Голова штриха: zz = zz0·(zz1/zz0)^f, f = fract(ph + rate·t);
    хвост отстаёт на streak в той же лог-шкале -> штрих всегда вдоль траектории в конусе.
    Яркость — случайная на штрих (атрибут br, lognormal), цвет — по rho (ядро/кольцо): без «варп-эффекта».
    Motion blur объекта выключен: иначе вращение размазывает штрихи поперёк луча («дождь»)."""
    rnd = random.Random(seed)
    npt = 4
    hc = bpy.data.hair_curves.new("PSR_Particles")
    hc.add_curves([npt] * count)
    def cattr(nm, dom):
        return hc.attributes.get(nm) or hc.attributes.new(nm, "FLOAT", dom)
    U, V, PH, SG, SZ, BR, RR = [], [], [], [], [], [], []
    for i in range(count):
        rr = abs(rnd.gauss(0, 0.40)) if rnd.random() < 0.75 else rnd.gauss(1.35, 0.15)  # ядро / кольцо
        ang = rnd.uniform(0, 2 * math.pi)
        U.append(rr * math.cos(ang)); V.append(rr * math.sin(ang))
        PH.append(rnd.random()); SG.append(1.0 if i % 2 == 0 else -1.0)
        SZ.append(rnd.lognormvariate(0.0, 0.4))
        BR.append(min(3.0, rnd.lognormvariate(-0.5, 0.5)))
        RR.append(abs(rr))
    for nm, arr in (("u", U), ("v", V), ("ph", PH), ("sg", SG), ("sz", SZ), ("br", BR), ("rr", RR)):
        cattr(nm, "CURVE").data.foreach_set("value", arr)
    cattr("tq", "POINT").data.foreach_set("value", [k / (npt - 1) for _ in range(count) for k in range(npt)])
    ob = bpy.data.objects.new("PSR_Particles", hc)
    C.link(ob, COLL)
    ob.parent = mag
    _camera_only(ob)
    ob.cycles.use_motion_blur = False

    ng = bpy.data.node_groups.new("PSR_ParticleStream", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, Lk = ng.nodes, ng.links
    b = _NB(N, Lk)
    gi = N.new("NodeGroupInput")
    go = N.new("NodeGroupOutput")

    def attr(nm):
        a = N.new("GeometryNodeInputNamedAttribute")
        a.data_type = "FLOAT"
        a.inputs["Name"].default_value = nm
        return a.outputs["Attribute"]

    st = N.new("GeometryNodeInputSceneTime")
    tq = attr("tq")                                            # 0 — хвост, 1 — голова
    f = b.m("FRACT", b.add(attr("ph"), b.mul(st.outputs["Seconds"], rate)))
    fp = b.sub(f, b.mul(b.sub(1.0, tq), streak))
    zz = b.mul(b.m("EXPONENT", b.mul(fp, math.log(z_max / z_min))), (z_min * R + z_apex))
    k = b.mul(zz, tan_core)
    pos = b.comb(b.mul(attr("u"), k), b.mul(attr("v"), k), b.mul(b.sub(zz, z_apex), attr("sg")))
    fade = b.mul(b.smooth(0.03, 0.2, f), b.smooth(0.97, 0.6, f))
    taper = b.m("POWER", tq, 0.6)
    rad = b.mul(b.mul(b.mul(attr("sz"), radius * R), b.m("POWER", b.div(zz, R), 0.3)), b.mul(fade, taper))
    sp = N.new("GeometryNodeSetPosition")
    Lk.new(gi.outputs[0], sp.inputs["Geometry"])
    Lk.new(pos, sp.inputs["Position"])
    sr = N.new("GeometryNodeSetCurveRadius")
    Lk.new(sp.outputs[0], sr.inputs["Curve"])
    Lk.new(rad, sr.inputs["Radius"])
    Lk.new(sr.outputs[0], go.inputs[0])
    mod = ob.modifiers.new("Stream", "NODES")
    mod.node_group = ng

    mat, nodes, links, out = C.new_material("PSR_Particles")
    nb = _NB(nodes, links)
    em = nodes.new("ShaderNodeEmission")
    a_br = nodes.new("ShaderNodeAttribute"); a_br.attribute_name = "br"
    a_rr = nodes.new("ShaderNodeAttribute"); a_rr.attribute_name = "rr"
    links.new(nb.mix_rgb(nb.smooth(0.25, 1.3, a_rr.outputs["Fac"]), BEAM_CORE_RGB, BEAM_EDGE_RGB), em.inputs["Color"])
    cam = nodes.new("ShaderNodeCameraData")
    hi = nodes.new("ShaderNodeHairInfo")
    tc = nodes.new("ShaderNodeTexCoord")
    _, _, oz = nb.sep(tc.outputs["Object"])
    zz = nb.add(nb.m("ABSOLUTE", oz), z_apex)
    vd = cam.outputs["View Distance"]
    s = nb.mul(nb.smooth(1.0 * R, 4.0 * R, vd), strength)
    s = nb.mul(s, nb.smooth(0.15, 0.7, nb.div(vd, zz)))          # камера в луче — как в объёме
    s = nb.mul(s, a_br.outputs["Fac"])
    s = nb.mul(s, nb.m("POWER", hi.outputs["Intercept"], 1.5))   # хвост гаснет
    links.new(s, em.inputs["Strength"])
    tr = nodes.new("ShaderNodeBsdfTransparent")
    ad = nodes.new("ShaderNodeAddShader")
    links.new(tr.outputs[0], ad.inputs[0])
    links.new(em.outputs[0], ad.inputs[1])
    links.new(ad.outputs[0], out.inputs["Surface"])
    mat.cycles.emission_sampling = "NONE"
    hc.materials.append(mat)
    return ob


# ---------------------------------------------------------------- сборка
def build_pulsar(scene, *, location=(0, 0, 0), tilt_euler=(0, 0, 0), R=1.0, alpha_deg=78.0, spin_hz=0.6,
                 phase0_deg=0.0, frame_start=1, frame_end=300, beam_length=40.0, beam_half_angle_deg=8.0,
                 beam_intensity=1.0, light_energy=20000.0, spot_energy=None, detail="close",
                 field_lines=True, particles=True, surface_strength=None, field_strength=1.0, seed=0):
    """Собрать пульсар. Возвращает dict: root, spin, mag, surface, beams[N,S], spots[N,S], light,
    field_lines (list|None), particles (obj|None), mats{surface, beams[N,S]}, params{...}.

    beam_intensity — общий множитель яркости лучей (база: close 4.8, far 14 — калибровка AgX по-разному);
    light_energy — точечный свет в центре (Вт); spot_energy — прожекторы вдоль лучей (по умолчанию 4×light_energy).
      Ориентир: планета на ~40 ед. — light_energy ≈ 6000–8000, spot_energy ≈ 3×, тогда освещённая
      сторона ≤ 0.85 на дисплее с видимым градиентом к терминатору (энергия ∝ расстояние²).
    surface_strength — яркость поверхности (по умолчанию close 1.2 — центр диска ≈ 0.7 после AgX; far 9);
    detail='far' — без линий поля и частиц, поверхность — яркая точка (усиленная эмиссия).
    Для любых шотов, где луч может пройти через камеру (в т.ч. S2), вызывать key_pulse_flash."""
    far = detail == "far"
    fps = scene.render.fps / scene.render.fps_base
    tan_core = math.tan(math.radians(beam_half_angle_deg))
    z_apex = 0.7 * R * math.tan(math.radians(8.0)) / tan_core     # шапка ~0.24 R при любом угле
    root = C.empty("PSR_Root", COLL, loc=location, display="SPHERE", size=R * 1.5)
    root.rotation_euler = tilt_euler
    spin = C.empty("PSR_Spin", COLL, parent=root, display="ARROWS", size=R * 2)
    mag = C.empty("PSR_Mag", COLL, parent=spin, display="SINGLE_ARROW", size=R * 3)
    mag.rotation_euler = (math.radians(alpha_deg), 0.0, 0.0)

    # вращение: два ключа LINEAR + линейная экстраполяция за диапазон
    spin.rotation_mode = "XYZ"
    a0 = math.radians(phase0_deg)
    a1 = a0 + 2 * math.pi * spin_hz * (frame_end - frame_start) / fps
    spin.rotation_euler = (0, 0, a0)
    spin.keyframe_insert("rotation_euler", index=2, frame=frame_start)
    spin.rotation_euler = (0, 0, a1)
    spin.keyframe_insert("rotation_euler", index=2, frame=frame_end)
    _linearize(spin)

    # поверхность
    surf = bpy.data.objects.new("PSR_Surface", _smooth_sphere("PSR_Surface", R))
    C.link(surf, COLL)
    surf.parent = mag
    if surface_strength is None:
        surface_strength = 9.0 if far else 1.2
    smat = _surface_material("PSR_Surface", R, base_strength=surface_strength, far=far)
    surf.data.materials.append(smat)
    surf.visible_shadow = False          # свет в центре проходит сквозь
    surf.visible_diffuse = False         # освещение планет — только точечный свет (без шума от меш-света)
    surf.visible_volume_scatter = False

    # точечный свет в центре
    ld = bpy.data.lights.new("PSR_Light", "POINT")
    ld.energy = light_energy
    ld.shadow_soft_size = R
    ld.color = C.blackbody_rgb(SURF_TEMP)
    light = bpy.data.objects.new("PSR_Light", ld)
    C.link(light, COLL)
    light.parent = mag
    light.visible_camera = False

    # лучи: конусы-домены вдоль ±Z PSR_Mag
    L = beam_length
    z0 = 1.3 * R
    speed = 0.45                     # ln(z)/с — струйки удваивают расстояние за ~1.5 с
    beams, bmats, spots = [], [], []
    tan_dom = tan_core * 2.6
    for i, (nm, rot) in enumerate((("N", (0.0, 0.0, 0.0)), ("S", (math.pi, 0.0, 0.0)))):
        me = _cone_domain(f"PSR_Beam{nm}", z_apex, L, tan_dom)
        ob = bpy.data.objects.new(f"PSR_Beam{nm}", me)
        C.link(ob, COLL)
        ob.parent = mag
        ob.rotation_euler = rot
        bi = beam_intensity * (14.0 if far else 4.8)
        mat, tnode, fnode = _beam_material(f"PSR_Beam{nm}", R=R, L=L, tan_core=tan_core, z_apex=z_apex,
                                           intensity=bi, z0=z0, speed=speed, seed=13.7 * i + seed,
                                           angular_fade=not far, flash_gain=3.0 if far else 1.5)
        me.materials.append(mat)
        _camera_only(ob)
        # время шейдера: ключи LINEAR в секундах + экстраполяция
        tnode.outputs[0].default_value = 0.0
        tnode.outputs[0].keyframe_insert("default_value", frame=frame_start)
        tnode.outputs[0].default_value = (frame_end - frame_start) / fps
        tnode.outputs[0].keyframe_insert("default_value", frame=frame_end)
        _linearize(mat.node_tree, path_contains="PSR_Time")
        beams.append(ob)
        bmats.append(mat)
        # прожектор: светит вдоль луча (spot смотрит по своей −Z)
        sd = bpy.data.lights.new(f"PSR_Spot{nm}", "SPOT")
        sd.energy = spot_energy if spot_energy is not None else 4.0 * light_energy
        sd.color = BEAM_CORE_RGB
        sd.spot_size = min(math.radians(4.0 * beam_half_angle_deg), math.pi * 0.9)
        sd.spot_blend = 0.85
        sd.shadow_soft_size = 0.3 * R
        so = bpy.data.objects.new(f"PSR_Spot{nm}", sd)
        C.link(so, COLL)
        so.parent = mag
        so.rotation_euler = (math.pi, 0, 0) if nm == "N" else (0, 0, 0)
        so.visible_camera = False
        spots.append(so)

    fl = None
    if field_lines and not far:
        fl = list(_build_field_lines(mag, R, seed=3 + seed, strength=field_strength))
    parts = None
    if particles and not far:
        parts = _build_particles(mag, R, tan_core, z_apex, seed=11 + seed,
                                 z_max=min(7.0, 0.4 * L / R))

    return dict(root=root, spin=spin, mag=mag, surface=surf, beams=beams, spots=spots, light=light,
                field_lines=fl, particles=parts, mats=dict(surface=smat, beams=bmats),
                params=dict(R=R, alpha_deg=alpha_deg, spin_hz=spin_hz, phase0_deg=phase0_deg,
                            frame_start=frame_start, frame_end=frame_end, fps=fps, beam_length=L,
                            beam_half_angle_deg=beam_half_angle_deg, detail=detail, z_apex=z_apex))


# ---------------------------------------------------------------- анимационные помощники
def beam_axes_world(objs, frame):
    """(север, юг) — единичные векторы осей лучей в мире на кадре frame (можно дробный)."""
    sc = bpy.context.scene
    keep = (sc.frame_current, sc.frame_subframe)
    fi = int(math.floor(frame))
    sc.frame_set(fi, subframe=float(frame - fi))
    m = objs["mag"].matrix_world.to_3x3()
    north = (m @ Vector((0, 0, 1))).normalized()
    sc.frame_set(keep[0], subframe=keep[1])
    return north, -north


def beam_frame_for_azimuth(objs, azimuth_deg, after_frame=None):
    """Ближайший (дробный) кадр ≥ after_frame, когда северный луч в плоскости PSR_Root смотрит на azimuth_deg.
    Азимут отсчитывается от +X Root против часовой. Для α<90° луч — над плоскостью на (90−α)°."""
    p = objs["params"]
    f0 = p["frame_start"] if after_frame is None else after_frame
    # ось N в Spin: Rx(α)·Z = (0, −sin α, cos α) -> азимут (−90° + угол вращения)
    psi = (azimuth_deg + 90.0 - p["phase0_deg"]) % 360.0
    period_f = p["fps"] / p["spin_hz"]
    f = p["frame_start"] + psi / 360.0 * period_f
    while f < f0:
        f += period_f
    return f


def key_pulse_flash(objs, camera, frame_start, frame_end, width_deg=None, substeps=4, gamma=0.7,
                    light_gain=0.0):
    """Ключи вспышки (узлы PSR_Flash в материалах поверхности и лучей), когда ось луча проходит
    около направления на камеру. Значение — (среднее по выдержке (shutter 0.5) гауссианы угла)^gamma.
    width_deg по умолчанию 1.6·beam_half_angle — совпадает с видимой шириной объёма луча.
    Вне [frame_start, frame_end] значение 0 (ключи-нули на краях).
    light_gain > 0 — ещё и ключи энергии PSR_Light ×(1 + light_gain·v) (по умолчанию выкл.:
    изотропный свет не должен пульсировать в такт вспышке, видимой только камере).
    Возвращает список (кадр, значение) с пиками > 0.05."""
    p = objs["params"]
    w = math.radians(width_deg if width_deg is not None else p["beam_half_angle_deg"] * 1.6)
    sc = bpy.context.scene
    keep = (sc.frame_current, sc.frame_subframe)
    vals_n, vals_s = [], []
    for f in range(frame_start, frame_end + 1):
        an = as_ = 0.0
        for s in range(substeps):
            ff = f - 0.25 + 0.5 * (s + 0.5) / substeps
            fi = int(math.floor(ff))
            sc.frame_set(fi, subframe=ff - fi)
            mw = objs["mag"].matrix_world
            ax = (mw.to_3x3() @ Vector((0, 0, 1))).normalized()
            d = (camera.matrix_world.translation - mw.translation).normalized()
            ang_n = ax.angle(d)
            ang_s = math.pi - ang_n
            an += math.exp(-(ang_n / w) ** 2)
            as_ += math.exp(-(ang_s / w) ** 2)
        vals_n.append((an / substeps) ** gamma)
        vals_s.append((as_ / substeps) ** gamma)
    sc.frame_set(keep[0], subframe=keep[1])

    def key_sock(owner, path, vals, base=0.0, gain=1.0):
        # нули на frame_start-1 и frame_end+1: вне диапазона вспышка не «залипает»
        seq = [(frame_start - 1, 0.0)] + [(frame_start + i, v) for i, v in enumerate(vals)] + [(frame_end + 1, 0.0)]
        for f, v in seq:
            setattr(owner, path, base * (1.0 + gain * v) if base else v)
            owner.keyframe_insert(path, frame=f)

    def key(mat, vals):
        sock = mat.node_tree.nodes.get("PSR_Flash").outputs[0]
        key_sock(sock, "default_value", vals)
        sock.default_value = 0.0
        _linearize(mat.node_tree, extrapolate=False, path_contains="PSR_Flash")

    vmax = [max(a, b) for a, b in zip(vals_n, vals_s)]
    key(objs["mats"]["surface"], vmax)
    key(objs["mats"]["beams"][0], vals_n)
    key(objs["mats"]["beams"][1], vals_s)
    if light_gain > 0.0:
        ld = objs["light"].data
        key_sock(ld, "energy", vmax, base=ld.energy, gain=light_gain)
        _linearize(ld, extrapolate=False, path_contains="energy")
    peaks = []
    for i, v in enumerate(max(a, b) for a, b in zip(vals_n, vals_s)):
        prev = max(vals_n[i - 1], vals_s[i - 1]) if i > 0 else -1
        nxt = max(vals_n[i + 1], vals_s[i + 1]) if i + 1 < len(vals_n) else -1
        if v > 0.05 and v >= prev and v >= nxt:
            peaks.append((frame_start + i, round(v, 3)))
    return peaks
