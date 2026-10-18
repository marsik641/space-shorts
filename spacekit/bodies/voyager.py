"""Voyager (1 и 2 — одинаковые аппараты): процедурная модель для крупных и общих планов.

    from spacekit.bodies import voyager as VG
    vg = VG.build_voyager(sc, location=(0, 0, 0), detail="close")
    VG.aim(vg, direction=(0, 0, 1), roll_deg=0)       # ось тарелки (+Z модели) — на Землю/Солнце

Масштаб: 1 ед. = 1 м. Система модели: +Z — ось антенны высокого усиления (в полёте смотрит на Землю),
шина-десятигранник в начале координат, тарелка над ней. Штанги (азимут от +X против часовой):
    РИТЭГи      — AZ_RTG, три цилиндра с рёбрами в ряд на конце штанги;
    научная     — AZ_SCI (напротив РИТЭГов): CRS, LECP, PLS, на конце — сканирующая платформа (ISS NA/WA, IRIS, UVS, PPS);
    магнитометр — AZ_MAG, ферма-«астромачта» 13 м (треугольная решётка), датчики на конце и посередине;
    PRA/PWS     — две антенны-штыря по 10 м под 90° друг к другу.
Размеры — по открытым описаниям NASA/JPL (facts.md эпизода 002); мелкие детали (кронштейны, кабели) — условно.
Материалы: белая краска тарелки, чёрные термоодеяла (MLI, складки — шумом в bump), золотистый каптон,
серые РИТЭГи, светлая стеклопластиковая ферма, позолоченный чехол Золотой пластинки (с упрощённой гравировкой).
detail: "close" — ферма магнитометра решёткой, рёбра тарелки, гравировка; "far" — упрощённо (меньше полигонов).
"""
import math

import bmesh
import bpy
from mathutils import Matrix, Vector

from .. import core as C

COLL = "Voyager"

# основные размеры (м)
DISH_D = 3.66            # антенна высокого усиления
DISH_DEPTH = 0.50        # глубина параболоида (f/D ≈ 0.46) — по фотографиям, условно
BUS_ACROSS = 1.78        # шина: десятигранник, между гранями
BUS_H = 0.47
MAG_LEN = 13.0           # штанга магнитометра
PWS_LEN = 10.0           # антенны PRA/PWS
AZ_RTG, AZ_SCI, AZ_MAG = 180.0, 0.0, -100.0
AZ_RECORD = 72.0          # грань шины с Золотой пластинкой (грани — каждые 36° от 0°)


# --------------------------------------------------------------------------- материалы

def _principled(name, color, rough=0.5, metal=0.0, spec=0.5, coat=0.0):
    mat, N, L, out = C.new_material(name)
    b = N.new("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (*color, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Specular IOR Level"].default_value = spec
    b.inputs["Coat Weight"].default_value = coat
    L.new(b.outputs[0], out.inputs["Surface"])
    return mat, N, L, b


def _wrinkles(N, L, bsdf, scale=7.0, strength=0.35, distortion=1.2):
    """Складки термоодеяла: шум с искажением -> bump."""
    tc = N.new("ShaderNodeTexCoord")
    nz = N.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = scale
    nz.inputs["Detail"].default_value = 3.0           # 6 давало субпиксельную рябь: мерцание при движении камеры
    nz.inputs["Roughness"].default_value = 0.55
    nz.inputs["Distortion"].default_value = distortion
    L.new(tc.outputs["Object"], nz.inputs["Vector"])
    bump = N.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = strength
    bump.inputs["Distance"].default_value = 0.01
    L.new(nz.outputs["Fac"], bump.inputs["Height"])
    L.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    # пятна блеска: шероховатость гуляет
    mr = N.new("ShaderNodeMapRange")
    mr.inputs[1].default_value, mr.inputs[2].default_value = 0.3, 0.7
    mr.inputs[3].default_value = bsdf.inputs["Roughness"].default_value * 0.6
    mr.inputs[4].default_value = min(1.0, bsdf.inputs["Roughness"].default_value * 1.5)
    L.new(nz.outputs["Fac"], mr.inputs[0])
    L.new(mr.outputs[0], bsdf.inputs["Roughness"])


# --------------------------------------------------------------------------- чехол Золотой пластинки

COVER_RES = 1536
COVER_VERSION = 2          # менять при правке рисунка -> маска пересоберётся


def _cover_mask(res=COVER_RES):
    """Гравировка чехла Золотой пластинки по фото NASA (science.nasa.gov/mission/voyager/golden-record-cover/):
    вверху слева — пластинка с иглой и двоичным временем оборота, под ней — вид сбоку; вверху справа — сигнал начала
    кадра, строки 1–3, «чересстрочная» пила, растр и первая картинка (круг); внизу слева — карта пульсаров (14 лучей +
    линия к центру Галактики); внизу справа — атом водорода; в центре — отверстие. Координаты u, v ∈ [−1, 1] (v вверх),
    линия — 1, фон — 0. Векторная отрисовка с антиалиасингом (расстояние до отрезка), только в рамке отрезка."""
    import random

    import numpy as np
    img = np.zeros((res, res), np.float32)
    W = 0.0045                                   # полутолщина линии (в ед. радиуса): тонко, как на оригинале

    def to_px(u, v):
        return (u + 1) * 0.5 * res, (1 - v) * 0.5 * res

    def seg(p, q, w=W):
        (x0, y0), (x1, y1) = to_px(*p), to_px(*q)
        wp = w * 0.5 * res
        lo_x, hi_x = int(max(0, min(x0, x1) - wp - 2)), int(min(res, max(x0, x1) + wp + 3))
        lo_y, hi_y = int(max(0, min(y0, y1) - wp - 2)), int(min(res, max(y0, y1) + wp + 3))
        if lo_x >= hi_x or lo_y >= hi_y:
            return
        yy, xx = np.mgrid[lo_y:hi_y, lo_x:hi_x].astype(np.float32) + 0.5
        dx, dy = x1 - x0, y1 - y0
        L2 = dx * dx + dy * dy or 1e-9
        t = np.clip(((xx - x0) * dx + (yy - y0) * dy) / L2, 0.0, 1.0)
        d = np.hypot(xx - (x0 + t * dx), yy - (y0 + t * dy))
        a = np.clip(wp + 0.5 - d, 0.0, 1.0)
        img[lo_y:hi_y, lo_x:hi_x] = np.maximum(img[lo_y:hi_y, lo_x:hi_x], a)

    def poly(pts, w=W, closed=False):
        for p, q in zip(pts, pts[1:] + ([pts[0]] if closed else [])):
            seg(p, q, w)

    def arc(c, r, a0, a1, w=W):
        n = max(8, int(abs(a1 - a0) * r * 400))
        poly([(c[0] + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
               c[1] + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)], w)

    def ring(c, r, w=W):
        arc(c, r, 0, 360, w)

    def rect(u0, v0, u1, v1, w=W):
        poly([(u0, v0), (u1, v0), (u1, v1), (u0, v1)], w, closed=True)

    def binary(u0, v, n, step, bits, h=0.022, w=W * 0.8):
        """Ряд двоичных знаков: «|» — 1, «—» — 0 (как на чехле)."""
        for i in range(n):
            x = u0 + i * step
            if bits[i % len(bits)] == "1":
                seg((x, v - h / 2), (x, v + h / 2), w)
            else:
                seg((x - step * 0.32, v), (x + step * 0.32, v), w)

    # пластинка с иглой (вверху слева) и двоичное время оборота по окружности
    c = (-0.50, 0.40)
    ring(c, 0.238)
    ring(c, 0.032)
    ring(c, 0.010, w=W * 1.4)
    for k in range(44):                                          # пунктир вокруг (слева и снизу)
        a0 = 118 + k * 5.6
        arc(c, 0.268, a0, a0 + 3.2, w=W * 0.8)
    for k, bit in enumerate("1001101101010011"):                 # двоичные знаки по верхней дуге
        a = 115 - k * 3.6
        p = (c[0] + 0.268 * math.cos(math.radians(a)), c[1] + 0.268 * math.sin(math.radians(a)))
        if bit == "1":
            seg(p, (c[0] + 0.30 * math.cos(math.radians(a)), c[1] + 0.30 * math.sin(math.radians(a))), W * 0.8)
        else:
            arc(c, 0.284, a - 1.2, a + 1.2, w=W * 0.8)
    rect(-0.278, 0.36, -0.250, 0.50)                             # игла (тонарм) у правого края
    ring((-0.264, 0.345), 0.012)
    seg((-0.264, 0.50), (-0.264, 0.53))
    # вид сбоку: пластинка, игла, двоичное время одной стороны (~1 ч)
    seg((-0.72, -0.04), (-0.23, -0.04))
    rect(-0.285, -0.035, -0.250, 0.02)
    for row, bits in enumerate(("1101001110", "0110110101", "1011010011")):
        binary(-0.47, -0.075 - row * 0.026, 12, 0.021, bits, h=0.016)
    # сигнал начала кадра: «пружина», ступенька, шумный сигнал, отметки
    pts = [(-0.035, 0.565)]
    for k in range(7):
        pts += [(-0.035 + 0.013 * k + 0.0065, 0.60), (-0.035 + 0.013 * (k + 1), 0.53)]
    pts += [(0.06, 0.565), (0.085, 0.565), (0.085, 0.52), (0.135, 0.52), (0.135, 0.565), (0.15, 0.565)]
    rnd = random.Random(1977)
    x = 0.15
    while x < 0.72:
        x += rnd.uniform(0.008, 0.02)
        pts.append((min(x, 0.72), rnd.uniform(0.535, 0.66) if rnd.random() < 0.8 else 0.565))
    poly(pts, W * 0.8)
    for xm in (0.18, 0.33, 0.47, 0.60):
        seg((xm, 0.675), (xm, 0.705), W * 0.8)
    # номера строк 1–3 двоичным кодом
    binary(0.17, 0.455, 11, 0.02, "1011011010", h=0.018)
    binary(0.17, 0.425, 11, 0.02, "0110101101", h=0.018)
    # чересстрочная развёртка: пила с кружками на вершинах и знаками
    zz = [(0.19, 0.37)]
    for k in range(3):
        zz += [(0.19 + 0.175 * k + 0.15, 0.245), (0.19 + 0.175 * (k + 1), 0.37)]
    poly(zz)
    for k in range(3):
        ring((0.19 + 0.175 * (k + 1) - 0.004, 0.338), 0.013, W * 0.8)
        seg((0.19 + 0.175 * k + 0.08, 0.385), (0.19 + 0.175 * k + 0.08, 0.41), W * 0.8)
    # растр (512 вертикальных строк — показаны штрихами) и первая картинка — круг
    rect(0.11, -0.075, 0.38, 0.13)
    for k in range(16):
        u = 0.125 + k * 0.0075
        seg((u, -0.06), (u, 0.115), W * 0.55)
    seg((0.37, 0.13), (0.37, 0.175))
    rect(0.11, -0.32, 0.38, -0.12)
    ring((0.245, -0.22), 0.065)
    # центр
    ring((0.0, -0.025), 0.034)
    ring((0.0, -0.025), 0.015)
    # карта пульсаров: 14 лучей разной длины из положения Солнца + линия к центру Галактики
    pc = (-0.415, -0.52)
    seg((-0.74, -0.525), (0.49, -0.525), W * 0.8)
    rays = [(52, 0.50), (74, 0.22), (93, 0.20), (118, 0.16), (148, 0.24), (172, 0.30), (198, 0.18), (214, 0.12),
            (238, 0.26), (259, 0.34), (284, 0.22), (318, 0.28), (338, 0.36), (18, 0.30)]
    for k, (a, ln) in enumerate(rays):
        ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
        seg(pc, (pc[0] + ln * ca, pc[1] + ln * sa), W * 0.75)
        for j in range(3 + k % 4):                                # двоичный период — чёрточки у конца луча
            if (k + j) % 3:
                t = ln * (1.0 - 0.06 * (j + 1))
                m = (pc[0] + t * ca, pc[1] + t * sa)
                seg((m[0] + 0.009 * sa, m[1] - 0.009 * ca), (m[0] - 0.009 * sa, m[1] + 0.009 * ca), W * 0.6)
    # атом водорода в двух состояниях, линия перехода с «1»
    for cx in (0.294, 0.472):
        ring((cx, -0.747), 0.042)
        seg((cx, -0.765), (cx, -0.729), W * 0.8)
    seg((0.336, -0.747), (0.43, -0.747), W * 0.8)
    seg((0.383, -0.735), (0.383, -0.759), W * 0.8)
    return img


def _cover_image():
    """bpy-картинка маски чехла (кеш assets/voyager_cover_v<N>.npy — сгенерированный ассет, в git не идёт)."""
    import os

    import numpy as np
    name = f"VG_CoverMask_v{COVER_VERSION}"
    im = bpy.data.images.get(name)
    if im is not None:
        return im
    path = os.path.join(C.ASSETS, f"voyager_cover_v{COVER_VERSION}.npy")
    if os.path.exists(path):
        m = np.load(path)
    else:
        m = _cover_mask()
        os.makedirs(C.ASSETS, exist_ok=True)
        np.save(path, m)
    res = m.shape[0]
    im = bpy.data.images.new(name, res, res, alpha=False, float_buffer=False)
    im.colorspace_settings.name = "Non-Color"
    rgba = np.ones((res, res, 4), np.float32)
    flip = m[::-1]                                   # строки картинки Blender — снизу вверх
    rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = flip
    im.pixels.foreach_set(rgba.ravel())
    im.pack()
    return im


def _record_material(name, detail):
    """Чехол Золотой пластинки: позолоченный алюминий, гравировка схем как на оригинале (_cover_mask) — линии
    светлее фона и глаже (как на фото NASA), чуть утоплены; лёгкая неоднородность позолоты."""
    mat, N, L, b = _principled(name, (1.0, 0.74, 0.34), rough=0.32, metal=0.9)
    if detail != "close":
        return mat
    tc = N.new("ShaderNodeTexCoord")
    mp = N.new("ShaderNodeMapping")
    mp.inputs["Location"].default_value = (0.5, 0.5, 0.0)
    mp.inputs["Scale"].default_value = (0.5, 0.5, 1.0)
    L.new(tc.outputs["Object"], mp.inputs["Vector"])
    tex = N.new("ShaderNodeTexImage")
    tex.image = _cover_image()
    tex.interpolation = "Linear"
    tex.extension = "CLIP"
    L.new(mp.outputs["Vector"], tex.inputs["Vector"])
    mark = tex.outputs["Color"]
    nz = N.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 3.0
    nz.inputs["Detail"].default_value = 4.0
    L.new(tc.outputs["Object"], nz.inputs["Vector"])
    base = N.new("ShaderNodeMix")
    base.data_type = "RGBA"
    L.new(nz.outputs["Fac"], base.inputs[0])
    base.inputs[6].default_value = (0.86, 0.60, 0.24, 1.0)
    base.inputs[7].default_value = (1.0, 0.80, 0.40, 1.0)
    col = N.new("ShaderNodeMix")
    col.data_type = "RGBA"
    L.new(mark, col.inputs[0])
    L.new(base.outputs[2], col.inputs[6])
    col.inputs[7].default_value = (1.0, 0.93, 0.74, 1.0)
    L.new(col.outputs[2], b.inputs["Base Color"])
    rough = N.new("ShaderNodeMapRange")
    L.new(mark, rough.inputs[0])
    rough.inputs[3].default_value, rough.inputs[4].default_value = 0.34, 0.40
    L.new(rough.outputs[0], b.inputs["Roughness"])
    bump = N.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.10
    bump.inputs["Distance"].default_value = 0.001
    L.new(C.math_node(N, L, "MULTIPLY", mark, -1.0), bump.inputs["Height"])
    L.new(bump.outputs["Normal"], b.inputs["Normal"])
    return mat


def _materials(detail):
    m = {}
    mat, N, L, b = _principled("VG_White", (0.80, 0.80, 0.77), rough=0.48, spec=0.4)
    m["white"] = mat
    mat, N, L, b = _principled("VG_DishBack", (0.70, 0.70, 0.68), rough=0.6, spec=0.3)
    m["dishback"] = mat
    mat, N, L, b = _principled("VG_MLI", (0.018, 0.018, 0.02), rough=0.32, spec=0.6)
    if detail == "close":
        _wrinkles(N, L, b, scale=6.0, strength=0.4)
    m["mli"] = mat
    mat, N, L, b = _principled("VG_Kapton", (0.85, 0.52, 0.16), rough=0.28, metal=0.85)
    if detail == "close":
        _wrinkles(N, L, b, scale=5.0, strength=0.45, distortion=1.6)
    m["kapton"] = mat
    m["alu"] = _principled("VG_Alu", (0.86, 0.87, 0.88), rough=0.32, metal=1.0)[0]
    m["louver"] = _principled("VG_Louver", (0.95, 0.95, 0.96), rough=0.28, metal=1.0)[0]   # 0.12 — искрили кромки
    m["rtg"] = _principled("VG_RTG", (0.035, 0.035, 0.04), rough=0.5, metal=0.3)[0]       # бериллий в чёрном покрытии
    m["truss"] = _principled("VG_Truss", (0.62, 0.58, 0.48), rough=0.55)[0]
    m["dark"] = _principled("VG_Dark", (0.04, 0.04, 0.045), rough=0.45, spec=0.5)[0]
    m["lens"] = _principled("VG_Lens", (0.01, 0.012, 0.02), rough=0.05, spec=1.0, coat=1.0)[0]
    m["record"] = _record_material("VG_Record", detail)
    return m


# --------------------------------------------------------------------------- геометрия

def _obj(name, bm, mats, parent, smooth=False):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for mt in mats:
        me.materials.append(mt)
    if smooth:
        me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    C.link(ob, COLL)
    ob.parent = parent
    return ob


def _frame(p0, p1):
    """Матрица: ось Z — от p0 к p1, начало — середина отрезка; длина отрезка."""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    q = Vector((0, 0, 1)).rotation_difference(d.normalized())
    return Matrix.Translation((p0 + p1) * 0.5) @ q.to_matrix().to_4x4(), d.length


def _rod(bm, p0, p1, r, seg=8, r1=None, mat=0, caps=True):
    """Цилиндр/усечённый конус между точками (материал — индекс)."""
    M, length = _frame(p0, p1)
    res = bmesh.ops.create_cone(bm, cap_ends=caps, cap_tris=False, segments=seg, radius1=r,
                                radius2=r if r1 is None else r1, depth=length, matrix=M)
    for f in {f for v in res["verts"] for f in v.link_faces}:
        f.material_index = mat
    return res


def _box(bm, center, size, rot=None, mat=0):
    M = Matrix.Translation(center) @ (rot.to_4x4() if rot is not None else Matrix.Identity(4)) @ \
        Matrix.Diagonal((*size, 1.0))
    res = bmesh.ops.create_cube(bm, size=1.0, matrix=M)
    for f in {f for v in res["verts"] for f in v.link_faces}:
        f.material_index = mat
    return res


def _lathe(bm, profile, seg, mat=0, z_axis_matrix=None):
    """Тело вращения: profile [(r, z), ...] вокруг оси Z; r=0 — полюс (сходится в точку)."""
    M = z_axis_matrix or Matrix.Identity(4)
    rings = []
    for r, z in profile:
        if r < 1e-6:
            rings.append([bm.verts.new(M @ Vector((0, 0, z)))])
        else:
            rings.append([bm.verts.new(M @ Vector((r * math.cos(2 * math.pi * i / seg),
                                                   r * math.sin(2 * math.pi * i / seg), z))) for i in range(seg)])
    for a, b in zip(rings, rings[1:]):
        if len(a) == 1 and len(b) == 1:
            continue
        for i in range(seg):
            j = (i + 1) % seg
            if len(a) == 1:
                f = bm.faces.new((a[0], b[i], b[j]))
            elif len(b) == 1:
                f = bm.faces.new((a[i], b[0], a[j]))
            else:
                f = bm.faces.new((a[i], b[i], b[j], a[j]))
            f.material_index = mat
    return rings


def _dir(az_deg, el_deg):
    az, el = math.radians(az_deg), math.radians(el_deg)
    return Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)))


def _bus_radius():
    return (BUS_ACROSS / 2.0) / math.cos(math.radians(18.0))      # описанная окружность десятигранника


# --------------------------------------------------------------------------- части

def _dish(root, m, detail):
    """Параболоид (вогнутость к +Z), обод, рёбра сзади, контррефлектор на трёх стойках, рупор, малая антенна."""
    seg = 96 if detail == "close" else 48
    nr = 24 if detail == "close" else 12
    R = DISH_D / 2.0
    f = R * R / (4.0 * DISH_DEPTH)
    z0 = BUS_H / 2.0 + 0.10                     # вершина параболоида над шиной
    t = 0.035                                   # толщина «скорлупы»
    bm = bmesh.new()
    front = [(R * i / nr, z0 + (R * i / nr) ** 2 / (4 * f)) for i in range(nr + 1)]
    back = [(r, z - t - 0.04 * (1 - r / R)) for r, z in reversed(front)]   # тыльная сторона толще к центру
    prof = front + [(R + 0.012, front[-1][1] - t * 0.5)] + back
    _lathe(bm, prof, seg, mat=0)
    # тыльная сторона — свой материал
    for fc in bm.faces:
        if fc.normal.z < -0.2 or fc.calc_center_median().z < z0 + DISH_DEPTH * 0.0 - 0.0:
            pass
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for fc in bm.faces:
        c = fc.calc_center_median()
        rr = math.hypot(c.x, c.y)
        zf = z0 + rr * rr / (4 * f)
        if c.z < zf - t * 0.5:
            fc.material_index = 1
    dish = _obj("VG_Dish", bm, [m["white"], m["dishback"]], root, smooth=True)

    bm = bmesh.new()
    # рёбра жёсткости сзади и опорное кольцо к шине
    if detail == "close":
        for k in range(16):
            a = 2 * math.pi * (k + 0.5) / 16
            pts = []
            for i in range(1, 9):
                r = 0.25 + (R - 0.3) * i / 8
                pts.append(Vector((r * math.cos(a), r * math.sin(a), z0 + r * r / (4 * f) - t - 0.05 * (1 - r / R) - 0.03)))
            for p, q in zip(pts, pts[1:]):
                _rod(bm, p, q, 0.012, seg=4, mat=0)
    # переходник шина -> тарелка
    _lathe(bm, [(0.0, BUS_H / 2.0), (0.62, BUS_H / 2.0), (0.42, z0 - 0.02), (0.0, z0 - 0.02)], 32, mat=0)
    # контррефлектор (выпуклый, гиперболоид — условно сферический сегмент) на трёх стойках
    zs = z0 + 1.38
    rs = 0.26
    sub = [(0.0, zs + 0.0), (rs * 0.5, zs + 0.012), (rs, zs + 0.05), (rs, zs + 0.075), (0.0, zs + 0.09)]
    _lathe(bm, sub, 48, mat=1)
    for k in range(3):
        a = 2 * math.pi * k / 3 + math.pi / 6
        r_f = 1.15
        p0 = Vector((r_f * math.cos(a), r_f * math.sin(a), z0 + r_f * r_f / (4 * f)))
        p1 = Vector((rs * 0.9 * math.cos(a), rs * 0.9 * math.sin(a), zs + 0.04))
        _rod(bm, p0, p1, 0.016, seg=8, mat=0)
    # рупор облучателя в центре тарелки
    _rod(bm, (0, 0, z0 - 0.01), (0, 0, z0 + 0.42), 0.10, seg=24, r1=0.065, mat=0)
    # малая антенна (LGA) поверх контррефлектора: стакан + диск
    _rod(bm, (0, 0, zs + 0.09), (0, 0, zs + 0.20), 0.055, seg=20, mat=0)
    _rod(bm, (0, 0, zs + 0.20), (0, 0, zs + 0.215), 0.11, seg=24, mat=0)
    parts = _obj("VG_DishParts", bm, [m["white"], m["alu"]], root, smooth=False)
    return dish, parts, z0


def _bus(root, m, detail):
    """Десятигранная шина: отсеки с термоодеялами, жалюзи, каптон; снизу — блок двигателей ориентации."""
    Rc = _bus_radius()
    h = BUS_H
    bm = bmesh.new()
    # десятигранник: вершины на 18° + 36°k, центры граней — на 36°k (грань 0° — под научной штангой)
    _lathe(bm, [(0.0, -h / 2), (Rc, -h / 2), (Rc, h / 2), (0.0, h / 2)], 10, mat=1,
           z_axis_matrix=Matrix.Rotation(math.radians(18.0), 4, "Z"))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.normal_update()
    sides = [f for f in bm.faces if abs(f.normal.z) < 0.5]
    # вставки-панели на гранях
    bmesh.ops.inset_individual(bm, faces=sides, thickness=0.035, depth=-0.012)
    # отсек k (грань на азимуте 36°·k): 1 — чёрный MLI, 2 — жалюзи (4 из 10 отсеков), 3 — золотая фольга (небольшой участок)
    plan = {0: 3, 1: 1, 2: 1, 3: 2, 4: 1, 5: 2, 6: 1, 7: 2, 8: 1, 9: 2}
    for f in sides:
        c = f.calc_center_median()
        k = int(round(math.degrees(math.atan2(c.y, c.x)) / 36.0)) % 10
        f.material_index = plan[k]
    for f in bm.faces:
        if abs(f.normal.z) > 0.5:
            f.material_index = 1
    bus = _obj("VG_Bus", bm, [m["alu"], m["mli"], m["louver"], m["kapton"]], root)
    # жалюзи — рейки поверх граней с материалом 2
    bm = bmesh.new()
    if detail == "close":
        for k_face in (3, 5, 7, 9):
            a = math.radians(36.0 * k_face)
            n = Vector((math.cos(a), math.sin(a), 0.0))
            tng = Vector((-n.y, n.x, 0.0))
            rflat = BUS_ACROSS / 2.0 + 0.004
            for k in range(8):
                zc = -h / 2 + 0.06 + k * (h - 0.12) / 7
                c = n * rflat + Vector((0, 0, zc))
                rot = Matrix((tng, n, Vector((0, 0, 1)))).transposed()
                _box(bm, c, (0.42, 0.012, 0.035), rot=rot, mat=0)
    # блок под шиной (двигатели ориентации, бак) и сопла
    _rod(bm, (0, 0, -h / 2), (0, 0, -h / 2 - 0.22), 0.46, seg=32, r1=0.40, mat=1)
    for k in range(4):
        a = 2 * math.pi * k / 4 + math.pi / 4
        p = Vector((0.36 * math.cos(a), 0.36 * math.sin(a), -h / 2 - 0.22))
        _rod(bm, p, p + Vector((0, 0, -0.07)), 0.025, seg=12, r1=0.045, mat=0)
    under = _obj("VG_BusParts", bm, [m["louver"], m["mli"]], root)
    return bus, under


def _rtg_unit(bm, p0, axis, mat_body):
    """Один РИТЭГ MHW: цилиндр Ø0.40 × 0.51 м с шестью радиальными рёбрами."""
    L, r = 0.51, 0.20
    p1 = p0 + axis * L
    _rod(bm, p0, p1, r, seg=24, mat=mat_body)
    up = Vector((0, 0, 1)) if abs(axis.z) < 0.9 else Vector((1, 0, 0))
    u = axis.cross(up).normalized()
    v = axis.cross(u).normalized()
    q = axis.to_track_quat("Z", "Y").to_matrix()
    for k in range(6):
        a = 2 * math.pi * k / 6
        d = u * math.cos(a) + v * math.sin(a)
        c = (p0 + p1) * 0.5 + d * (r + 0.06)
        # ребро: длинная сторона вдоль оси, ширина радиально, тонкое по касательной
        tangent = axis.cross(d).normalized()
        rot = Matrix((tangent, d, axis)).transposed()
        _box(bm, c, (0.008, 0.14, L * 0.96), rot=rot, mat=mat_body)
    # фланцы
    _rod(bm, p0 - axis * 0.01, p0 + axis * 0.02, r + 0.02, seg=24, mat=mat_body)
    _rod(bm, p1 - axis * 0.02, p1 + axis * 0.01, r + 0.02, seg=24, mat=mat_body)
    return p1


def _truss_boom(bm, p0, p1, width, bays, mat, close=True):
    """Ферма треугольного сечения от p0 до p1 (пояса + раскосы)."""
    p0, p1 = Vector(p0), Vector(p1)
    ax = (p1 - p0).normalized()
    up = Vector((0, 0, 1)) if abs(ax.z) < 0.9 else Vector((1, 0, 0))
    u = ax.cross(up).normalized()
    v = ax.cross(u).normalized()
    rr = width / math.sqrt(3.0)
    offs = [u * rr * math.cos(2 * math.pi * k / 3) + v * rr * math.sin(2 * math.pi * k / 3) for k in range(3)]
    if not close:
        _rod(bm, p0, p1, width * 0.25, seg=6, mat=mat)
        return
    rl = width * 0.06
    for o in offs:
        _rod(bm, p0 + o, p1 + o, rl, seg=5, mat=mat, caps=False)
    L = (p1 - p0).length
    for i in range(bays + 1):
        c = p0 + ax * (L * i / bays)
        for k in range(3):
            a, b = offs[k], offs[(k + 1) % 3]
            _rod(bm, c + a, c + b, rl * 0.7, seg=4, mat=mat, caps=False)
            if i < bays:
                c2 = p0 + ax * (L * (i + 1) / bays)
                _rod(bm, c + a, c2 + b, rl * 0.45, seg=4, mat=mat, caps=False)


def _booms(root, m, detail, z_dish):
    close = detail == "close"
    Rc = _bus_radius()
    Rf = BUS_ACROSS / 2.0
    out = {}

    # --- РИТЭГи
    bm = bmesh.new()
    d = _dir(AZ_RTG, -14.0)
    base = _dir(AZ_RTG, 0.0) * Rf + Vector((0, 0, -0.08))
    start = base + d * 1.05
    _truss_boom(bm, base, start + d * 0.05, 0.16, 5, mat=1, close=close)
    p = start
    for k in range(3):
        p = _rtg_unit(bm, p + d * 0.06, d, mat_body=0)
    # подкос к шине
    _rod(bm, base + Vector((0, 0, -0.18)), start + d * 0.02 + Vector((0, 0, -0.1)), 0.015, seg=6, mat=1)
    out["rtg"] = _obj("VG_RTG", bm, [m["rtg"], m["truss"]], root)

    # --- научная штанга + сканирующая платформа
    bm = bmesh.new()
    d = _dir(AZ_SCI, -8.0)
    base = _dir(AZ_SCI, 0.0) * Rf + Vector((0, 0, -0.04))
    end = base + d * 2.30
    _truss_boom(bm, base, end, 0.18, 7, mat=1, close=close)
    side = Vector((0, 0, 1)).cross(d).normalized()
    # CRS: коробка с «телескопами» (смотрят вбок)
    c = base + d * 0.75 + Vector((0, 0, 0.18))
    rot = Matrix((d, side, d.cross(side))).transposed()
    _box(bm, c, (0.30, 0.26, 0.20), rot=rot, mat=2)
    for k in range(4):
        q0 = c + side * 0.12 + d * (-0.09 + 0.06 * k) + Vector((0, 0, 0.03))
        _rod(bm, q0, q0 + side * 0.07, 0.022, seg=10, mat=0)
    # LECP: цилиндр-барабан на поворотной платформе
    c = base + d * 1.35 + Vector((0, 0, 0.19))
    _rod(bm, c - Vector((0, 0, 0.12)), c + Vector((0, 0, 0.12)), 0.12, seg=20, mat=2)
    _rod(bm, c + Vector((0, 0, 0.12)), c + Vector((0, 0, 0.15)), 0.135, seg=20, mat=0)
    # PLS: блок с «чашками Фарадея», смотрит к +Z (на Землю)
    c = base + d * 0.35 + Vector((0, 0, 0.25))
    _rod(bm, c, c + Vector((0, 0, 0.12)), 0.11, seg=6, mat=2)
    for k in range(3):
        a = 2 * math.pi * k / 3
        q0 = c + Vector((0.055 * math.cos(a), 0.055 * math.sin(a), 0.12))
        _rod(bm, q0, q0 + Vector((0, 0, 0.06)), 0.04, seg=12, r1=0.05, mat=0)
    # сканирующая платформа: блок на двухосном шарнире
    pc = end + d * 0.12 + Vector((0, 0, -0.05))
    _rod(bm, end, pc, 0.07, seg=12, mat=2)
    plat = pc + d * 0.25
    _box(bm, plat, (0.42, 0.50, 0.32), rot=rot, mat=2)
    look = (Vector((0, 0, 1)) * 0.2 + side * -0.3 + d * 0.9).normalized()   # платформа смотрит наружу-вниз
    look = (d * 0.35 + Vector((0, 0, -0.25)) + side * 0.9).normalized()
    # ISS NA (длинная бленда), ISS WA, IRIS (крупный телескоп), UVS, PPS
    def inst(off, length, r, rr=None, lens=True):
        q0 = plat + off
        q1 = q0 + look * length
        _rod(bm, q0, q1, r, seg=20, r1=rr, mat=0)
        if lens:
            _rod(bm, q1 - look * 0.005, q1 + look * 0.002, (rr or r) * 0.8, seg=20, mat=3)
    up2 = look.cross(d).normalized()
    inst(up2 * 0.10 + d * 0.06, 0.95, 0.085, 0.10)          # NA
    inst(up2 * 0.10 - d * 0.14, 0.50, 0.065, 0.075)         # WA
    inst(-up2 * 0.16 + d * 0.02, 0.55, 0.26, 0.27)          # IRIS
    inst(-up2 * 0.02 - d * 0.22, 0.30, 0.05, 0.06)          # PPS
    _box(bm, plat + look * 0.25 + up2 * 0.26 - d * 0.05, (0.12, 0.30, 0.12),
         rot=Matrix((d, look, d.cross(look))).transposed(), mat=0)   # UVS
    out["sci"] = _obj("VG_Science", bm, [m["dark"], m["truss"], m["mli"], m["lens"]], root)

    # --- магнитометр: канистра на выносной ферме РИТЭГ (сторона, противоположная научной штанге) + ферма 13 м
    bm = bmesh.new()
    d = _dir(AZ_MAG, -20.0)
    base = _dir(AZ_RTG, -14.0) * 0.55 + _dir(AZ_RTG, 0.0) * Rf + Vector((0, 0, -0.2))
    _rod(bm, base - d * 0.05, base + d * 0.6, 0.114, seg=20, mat=2)
    p0 = base + d * 0.6
    p1 = p0 + d * MAG_LEN
    _truss_boom(bm, p0, p1, 0.18, 52 if close else 1, mat=1, close=close)
    for frac, s in ((0.48, 0.07), (1.0, 0.10)):
        c = p0 + d * (MAG_LEN * frac)
        _box(bm, c + d * (0.04 if frac == 1.0 else 0.0), (s, s, s * 1.4),
             rot=Matrix((d.cross(Vector((0, 0, 1))).normalized(), Vector((0, 0, 1)), d)).transposed(), mat=0)
    out["mag"] = _obj("VG_Mag", bm, [m["white"], m["truss"], m["mli"]], root)

    # --- антенны PRA/PWS: два штыря 10 м под 90°
    bm = bmesh.new()
    for az in (AZ_RTG - 45.0, AZ_RTG + 45.0):
        dd = _dir(az, -40.0)
        b0 = _dir(az, 0.0) * Rf * 0.98 + Vector((0, 0, BUS_H / 2 - 0.02))
        _rod(bm, b0, b0 + dd * 0.12, 0.03, seg=10, mat=0)
        _rod(bm, b0 + dd * 0.12, b0 + dd * PWS_LEN, 0.0065, seg=6, mat=0, caps=False)
    out["pws"] = _obj("VG_PWS", bm, [m["alu"]], root)

    # --- Золотая пластинка на грани шины (смотрит наружу)
    a = math.radians(AZ_RECORD)
    n = Vector((math.cos(a), math.sin(a), 0.0))
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=64, radius1=1.0, radius2=1.0, depth=0.06)
    rec = _obj("VG_GoldenRecord", bm, [m["record"]], root, smooth=False)
    rec.scale = (0.165, 0.165, 0.165)                       # пластинка 12" (30 см) в чехле ~33 см
    # оси диска: Z — наружу (n), Y — от тарелки (−Z модели): на крупном плане снизу (ep002 v5, тарелка внизу кадра)
    # схема стоит ровно; X = Y × Z — вправо для зрителя снаружи (не зеркально)
    rec.rotation_mode = "QUATERNION"
    rec.rotation_quaternion = Matrix((Vector((n.y, -n.x, 0.0)), Vector((0, 0, -1)), n)).transposed().to_quaternion()
    rec.location = n * (Rf + 0.012) + Vector((0, 0, 0.0))
    out["record"] = rec
    return out


# --------------------------------------------------------------------------- API

def build_voyager(scene, *, location=(0, 0, 0), detail="close", name="Voyager", parent=None):
    """Модель аппарата. Возвращает dict root, parts{dish, dish_parts, bus, bus_parts, rtg, sci, mag, pws, record},
    mats, dims (размеры, м), z_dish (высота вершины тарелки). root ориентировать через aim()."""
    C.collection(COLL, scene)
    root = C.empty(f"{name}_Root", coll=COLL, loc=location, display="ARROWS", size=2.0)
    if parent is not None:
        root.parent = parent
    m = _materials(detail)
    dish, dparts, z0 = _dish(root, m, detail)
    bus, under = _bus(root, m, detail)
    booms = _booms(root, m, detail, z0)
    parts = dict(dish=dish, dish_parts=dparts, bus=bus, bus_parts=under, **booms)
    return dict(root=root, parts=parts, mats=m, z_dish=z0,
                dims=dict(dish_d=DISH_D, bus_across=BUS_ACROSS, bus_h=BUS_H, mag=MAG_LEN, pws=PWS_LEN))


def aim(vg, direction, roll_deg=0.0):
    """Ось тарелки (+Z модели) — в направлении direction; roll — поворот вокруг этой оси."""
    root = vg["root"] if isinstance(vg, dict) else vg
    d = Vector(direction).normalized()
    q = Vector((0, 0, 1)).rotation_difference(d)
    q = q @ Matrix.Rotation(math.radians(roll_deg), 3, "Z").to_quaternion()
    root.rotation_mode = "QUATERNION"
    root.rotation_quaternion = q
    return q


def world_point(vg, local):
    """Точка модели (м, система модели) -> мир (с учётом текущих location/rotation root)."""
    root = vg["root"] if isinstance(vg, dict) else vg
    bpy.context.view_layer.update()
    return root.matrix_world @ Vector(local)
