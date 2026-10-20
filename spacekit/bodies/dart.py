"""DART: подробная процедурная модель аппарата в метрах.

    ship = build_dart(name="DART", detail="close")
    ship["root"].rotation_euler = (0, 0, 0)

Локальные оси: +Z — оптическая ось DRACO/направление подхода к цели;
X — размах двух ROSA; солнечная сторона панелей смотрит в +Z.
Ориентация панелей в финальном пролёте условная: приводов сопровождения нет.
Корпус 1.2 × 1.3 × 1.3 м, размах 19 м, длина каждого крыла около 8.4 м.
Диаметр апертуры DRACO 0.208 м. Это геометрическая реконструкция по открытым
схемам, а не полётная CAD-модель: мелкая арматура, складки и кабели условные.
Плоская круглая RLSA — антенна с радиальными щелями, не параболическая тарелка.

Источники геометрии и компоновки:
https://www.jhuapl.edu/news/news-releases/210812-dart-solar-array-imager-installation
https://www.jhuapl.edu/destinations/instruments/draco
https://www.jhuapl.edu/sites/default/files/2024-09/35-04-Adams.pdf (рис. 7)
https://science.nasa.gov/mission/dart/spacecraft/
Официальный NASA 3D resource на 20.10.2026 содержит STL для печати, без PBR;
здесь вместо него построена воспроизводимая модель с объёмной MLI и ROSA.
"""

import math
import random

import bpy
from mathutils import Vector

from .. import core as C


BUS_SIZE = (1.2, 1.3, 1.3)
SPAN = 19.0
DRACO_APERTURE = 0.208


def _material(name, color, roughness, metallic=0.0, coat=0.0):
    mat, nodes, links, out = C.new_material(name)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Coat Weight"].default_value = coat
    bsdf.inputs["Coat Roughness"].default_value = 0.13
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat, nodes, links, bsdf


def _materials(prefix):
    """Металлы получают свет сцены; у фольги нет собственного свечения."""
    result = {}
    specs = {
        "gold": ((0.68, 0.36, 0.058), 0.33, 0.82),
        "gold_dark": ((0.31, 0.145, 0.018), 0.38, 0.82),
        "silver": ((0.57, 0.61, 0.64), 0.27, 0.95),
        "titanium": ((0.19, 0.22, 0.25), 0.33, 0.92),
        "black": ((0.008, 0.012, 0.017), 0.40, 0.25),
        "blanket": ((0.015, 0.019, 0.022), 0.48, 0.12),
        "white": ((0.72, 0.74, 0.72), 0.47, 0.05),
        "wire": ((0.11, 0.065, 0.018), 0.31, 0.62),
        "glass": ((0.007, 0.012, 0.026), 0.13, 0.28),
    }
    for key, (col, rough, metal) in specs.items():
        mat, nodes, links, bsdf = _material(prefix + "_" + key, col, rough, metal)
        result[key] = mat
        if key in ("gold", "gold_dark", "silver", "blanket"):
            tex = nodes.new("ShaderNodeTexNoise")
            tex.inputs["Scale"].default_value = 37
            tex.inputs["Detail"].default_value = 2
            tex.inputs["Roughness"].default_value = 0.56
            tex.inputs["Distortion"].default_value = 0.9
            bump = nodes.new("ShaderNodeBump")
            bump.inputs["Strength"].default_value = 0.23 if key != "blanket" else 0.1
            bump.inputs["Distance"].default_value = 0.0022
            links.new(tex.outputs["Fac"], bump.inputs["Height"])
            links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
            ramp = nodes.new("ShaderNodeMapRange")
            ramp.inputs["From Min"].default_value = 0.15
            ramp.inputs["From Max"].default_value = 0.85
            ramp.inputs["To Min"].default_value = rough * 0.74
            ramp.inputs["To Max"].default_value = rough * 1.4
            links.new(tex.outputs["Fac"], ramp.inputs["Value"])
            links.new(ramp.outputs["Result"], bsdf.inputs["Roughness"])
    for i in range(4):
        # Тёмное стекло ячеек: небольшая вариация, без шахматной раскраски.
        f = 0.86 + i * 0.075
        mat, nodes, links, bsdf = _material(
            prefix + "_cell" + str(i), (0.012 * f, 0.022 * f, 0.047 * f), 0.22, 0.32, 0.32)
        noise = nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 8
        noise.inputs["Detail"].default_value = 1
        ramp = nodes.new("ShaderNodeMapRange")
        ramp.inputs["To Min"].default_value = 0.16
        ramp.inputs["To Max"].default_value = 0.24
        links.new(noise.outputs["Fac"], ramp.inputs["Value"])
        links.new(ramp.outputs["Result"], bsdf.inputs["Roughness"])
        result["cell" + str(i)] = mat
    return result


def _mesh(name, verts, faces, mat, root, collection, smooth=False):
    data = bpy.data.meshes.new(name + "_mesh")
    data.from_pydata(verts, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    obj.parent = root
    if mat is not None:
        data.materials.append(mat)
    if smooth:
        for poly in data.polygons:
            poly.use_smooth = True
    return obj


def _box(name, center, dims, mat, root, coll, bevel=0.0):
    x, y, z = (d / 2 for d in dims)
    c = Vector(center)
    verts = [tuple(c + Vector(v)) for v in (
        (-x, -y, -z), (x, -y, -z), (x, y, -z), (-x, y, -z),
        (-x, -y, z), (x, -y, z), (x, y, z), (-x, y, z))]
    obj = _mesh(name, verts, [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
                             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)], mat, root, coll)
    if bevel:
        mod = obj.modifiers.new(name + "_bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 2
    return obj


def _tube(name, a, b, radius, mat, root, coll, n=16, end_radius=None):
    """Цилиндр/усечённый конус между двумя точками, без bpy.ops."""
    a, b = Vector(a), Vector(b)
    axis = (b - a).normalized()
    guide = Vector((0, 1, 0)) if abs(axis.y) < 0.9 else Vector((1, 0, 0))
    u = axis.cross(guide).normalized()
    v = axis.cross(u)
    radius2 = radius if end_radius is None else end_radius
    verts = [tuple(c + r * (math.cos(i * math.tau / n) * u + math.sin(i * math.tau / n) * v))
             for c, r in ((a, radius), (b, radius2)) for i in range(n)]
    faces = [tuple(reversed(range(n))), tuple(range(n, 2 * n))]
    faces.extend((i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n))
    ob = _mesh(name, verts, faces, mat, root, coll)
    for poly in ob.data.polygons[2:]:
        poly.use_smooth = True
    return ob


def _wire(name, points, radius, mat, root, coll):
    data = bpy.data.curves.new(name + "_curve", "CURVE")
    data.dimensions = "3D"
    data.resolution_u = 8
    data.bevel_depth = radius
    data.bevel_resolution = 2
    spline = data.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for point, value in zip(spline.bezier_points, points):
        point.co = value
        point.handle_left_type = point.handle_right_type = "AUTO"
    ob = bpy.data.objects.new(name, data)
    coll.objects.link(ob)
    ob.parent = root
    data.materials.append(mat)
    return ob


def _hollow_z(name, center, z0, z1, outer, inner, mat, root, coll, n=64):
    """Открытый с двух сторон тубус: апертура имеет настоящую глубину."""
    x, y = center
    verts = [(x + r * math.cos(i * math.tau / n), y + r * math.sin(i * math.tau / n), z)
             for z, r in ((z0, outer), (z1, outer), (z0, inner), (z1, inner)) for i in range(n)]
    faces = []
    for i in range(n):
        j = (i + 1) % n
        faces.extend(((i, j, j + n, i + n),
                      (i + n * 2, i + n * 3, j + n * 3, j + n * 2),
                      (i + n, j + n, j + n * 3, i + n * 3),
                      (i, i + n * 2, j + n * 2, j)))
    return _mesh(name, verts, faces, mat, root, coll)


def _blanket(name, axis, sign, dims, mat, root, coll, seed, close):
    """Натянутые края, объёмные диагональные заломы и неровная середина."""
    rng = random.Random(seed)
    axes = [a for a in range(3) if a != axis]
    na = 52 if close else 24
    nb = 52 if close else 24
    phase = rng.random() * math.tau
    creases = [(rng.uniform(-0.7, 0.7), rng.uniform(-1.8, 1.8), rng.uniform(0.007, 0.014))
               for _ in range(8)]
    verts = []
    for j in range(nb + 1):
        v = j / nb
        for i in range(na + 1):
            u = i / na
            p, q = (u - 0.5) * dims[axes[0]], (v - 0.5) * dims[axes[1]]
            edge = min(u, 1 - u, v, 1 - v)
            fall = min(1.0, edge / 0.065)
            wrinkles = 0.0038 * math.sin(p * 71 + math.sin(q * 16 + phase) * 2.7)
            wrinkles += 0.0024 * math.sin(q * 103 + p * 41 + phase)
            wrinkles += 0.0045 * math.sin(p * 18 + q * 14 + phase)
            for offset, slope, height in creases:
                d = p - slope * q - offset
                wrinkles += height * math.exp(-abs(d) / 0.013)
            billow = 0.011 * math.sin(math.pi * u) * math.sin(math.pi * v)
            loc = [0.0, 0.0, 0.0]
            loc[axis] = sign * (dims[axis] / 2 + 0.009 + fall * (wrinkles + billow))
            loc[axes[0]], loc[axes[1]] = p, q
            verts.append(tuple(loc))
    faces = []
    for j in range(nb):
        for i in range(na):
            a = j * (na + 1) + i
            face = (a, a + 1, a + na + 2, a + na + 1)
            # Перестановка осей меняет направление нормали.
            if (sign < 0) != (axis == 1):
                face = tuple(reversed(face))
            faces.append(face)
    return _mesh(name, verts, faces, mat, root, coll, smooth=True)


def _solar_wing(prefix, side, mats, root, coll, close):
    """Гибкая ROSA: тонкая подложка, отдельные стеклянные ячейки и два крайних бума."""
    inner, outer, half_width = 1.1, SPAN / 2, 0.65
    lo, hi = sorted((side * inner, side * outer))
    mid = (lo + hi) / 2
    _box(prefix + "_back", (mid, 0, -0.013), (hi - lo, 1.30, 0.025),
         mats["blanket"], root, coll, 0.008)
    verts, faces, mi = [], [], []
    columns = 64 if close else 48
    rows = 10
    dx, dy = (hi - lo - 0.12) / columns, (half_width * 2 - 0.12) / rows
    rng = random.Random(291 + (side + 1))
    for ix in range(columns):
        for iy in range(rows):
            x = lo + 0.06 + (ix + 0.5) * dx
            y = -half_width + 0.06 + (iy + 0.5) * dy
            hx, hy, cut = dx * 0.475, dy * 0.465, 0.010
            z = 0.006 + 0.003 * math.sin((x - lo) * 2.0)
            corners = [(-hx + cut, -hy), (hx - cut, -hy), (hx, -hy + cut),
                       (hx, hy - cut), (hx - cut, hy), (-hx + cut, hy),
                       (-hx, hy - cut), (-hx, -hy + cut)]
            k = len(verts)
            verts.extend((x + a, y + b, z) for a, b in corners)
            faces.append(tuple(range(k, k + 8)))
            mi.append(rng.randrange(4))
    cells = _mesh(prefix + "_cells", verts, faces, None, root, coll)
    for i in range(4):
        cells.data.materials.append(mats["cell" + str(i)])
    for face, matidx in zip(cells.data.polygons, mi):
        face.material_index = matidx
    # Контактные полосы — общая лёгкая сетка, не тысячи отдельных объектов.
    verts, faces = [], []
    def strip(x0, x1, y0, y1, z):
        k = len(verts)
        verts.extend(((x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)))
        faces.append((k, k + 1, k + 2, k + 3))
    for iy in range(rows):
        yc = -half_width + 0.06 + (iy + 0.5) * dy
        for offset in (-0.025, 0.025):
            strip(lo + 0.07, hi - 0.07, yc + offset - 0.0007, yc + offset + 0.0007, 0.011)
    for ix in range(0, columns + 1, 8):
        x = lo + 0.06 + ix * dx
        strip(x - 0.005, x + 0.005, -half_width + 0.03, half_width - 0.03, 0.014)
    _mesh(prefix + "_contacts", verts, faces, mats["silver"], root, coll)
    for y in (-half_width, half_width):
        _tube(prefix + ("_boomL" if y < 0 else "_boomR"),
              (lo, y, 0.0), (hi, y, 0.0), 0.024, mats["black"], root, coll, 12)
    for x in (lo, hi):
        _tube(prefix + "_end_" + str(round(x, 2)), (x, -half_width, 0), (x, half_width, 0),
              0.035, mats["titanium"], root, coll, 12)
    # Поворотный шарнир, золочёный вал ROSA и треугольные опоры.
    _tube(prefix + "_drive", (side * 0.63, 0, 0), (side * 1.10, 0, 0),
          0.11, mats["silver"], root, coll, 32)
    _tube(prefix + "_spool", (side * 1.08, -0.75, 0), (side * 1.08, 0.75, 0),
          0.105, mats["gold"], root, coll, 32)
    for y in (-0.52, 0.52):
        _tube(prefix + "_strut_" + str(y), (side * 0.6, y, -0.35), (side * 1.08, y, 0),
              0.026, mats["silver"], root, coll, 12)
    _wire(prefix + "_power", [(side * 0.58, 0.3, -0.05), (side * 0.83, 0.35, 0.17),
                              (side * 1.06, 0.32, 0.05)], 0.012, mats["wire"], root, coll)
    return cells


def build_dart(name="DART", location=(0, 0, 0), scale=1.0, parent=None, detail="close"):
    """Вернуть root/body/panels/materials; +Z — нос, X — крылья, 1 ед. = 1 м.

    Масштаб и перенос задаются только root: вся геометрия остаётся в локале.
    detail='far' уменьшает сетку складок/ячеек и снимает мелкий крепёж.
    """
    if detail not in ("close", "far"):
        raise ValueError("detail должен быть 'close' или 'far'")
    close = detail == "close"
    coll = C.collection(name)
    root = C.empty(name + "_root", coll=name, parent=parent, loc=location)
    root.scale = (scale, scale, scale)
    mats = _materials(name)
    body = _box(name + "_bus", (0, 0, 0), BUS_SIZE, mats["black"], root, coll, 0.035)
    # Фольга создаёт собственный силуэт и отражает ключевой свет заломами.
    for axis in range(3):
        for sign in (-1, 1):
            key = "gold" if (axis, sign) != (1, -1) else "gold_dark"
            _blanket(name + "_MLI_" + str(axis) + "_" + str(sign), axis, sign,
                     BUS_SIZE, mats[key], root, coll, 711 + axis * 7 + sign, close)
    # Несущие углы и полосы крепления термоодеял.
    for x in (-0.606, 0.606):
        for y in (-0.656, 0.656):
            _box(name + "_rail_" + str(x) + "_" + str(y), (x, y, 0),
                 (0.032, 0.032, 1.30), mats["silver"], root, coll, 0.005)
    for z in (-0.654, 0.654):
        for y in (-0.65, 0.65):
            _box(name + "_rimX_" + str(z) + "_" + str(y), (0, y, z),
                 (1.20, 0.027, 0.024), mats["titanium"], root, coll, 0.003)
        for x in (-0.60, 0.60):
            _box(name + "_rimY_" + str(z) + "_" + str(x), (x, 0, z),
                 (0.027, 1.30, 0.024), mats["titanium"], root, coll, 0.003)
    # Швы одеял: чёрная окантовка и отдельные узкие золотые ленты.
    for x in (-0.25, 0.28):
        _box(name + "_seam_" + str(x), (x, -0.677, 0), (0.024, 0.008, 1.18),
             mats["blanket"], root, coll)
    # Радиатор и лувры на задней стороне: глубина видна при боковом пролёте.
    _box(name + "_radiator", (0, 0, -0.685), (0.91, 0.96, 0.04),
         mats["white"], root, coll, 0.02)
    for i in range(9):
        _box(name + "_radiator_fin_" + str(i), (0, -0.39 + i * 0.095, -0.714),
             (0.81, 0.012, 0.025), mats["silver"], root, coll, 0.002)
    panels = [_solar_wing(name + "_ROSA_" + label, side, mats, root, coll, close)
              for label, side in (("L", -1), ("R", 1))]
    # DRACO: длинный чёрный бленд, внутренняя апертура 20.8 см.
    cx, cy = 0.31, 0.30
    _box(name + "_DRACO_mount", (cx, cy, 0.65), (0.38, 0.37, 0.12),
         mats["silver"], root, coll, 0.016)
    _hollow_z(name + "_DRACO_barrel", (cx, cy), 0.65, 1.19,
              0.145, 0.119, mats["black"], root, coll)
    _hollow_z(name + "_DRACO_rim", (cx, cy), 1.186, 1.22,
              0.152, 0.119, mats["titanium"], root, coll)
    # Впадина оптики: внешнее кольцо и апертура ниже края дают реальный параллакс.
    _hollow_z(name + "_DRACO_inner", (cx, cy), 1.08, 1.19,
              0.120, DRACO_APERTURE / 2, mats["black"], root, coll)
    _tube(name + "_DRACO_glass", (cx, cy, 1.10), (cx, cy, 1.104),
          DRACO_APERTURE / 2, mats["glass"], root, coll, 64)
    for z in (0.77, 0.89, 1.05):
        _hollow_z(name + "_DRACO_band_" + str(z), (cx, cy), z, z + 0.018,
                  0.149, 0.141, mats["titanium"], root, coll, 48)
    # Плоская RLSA: металлическая круглая щелевая антенна, правильный силуэт.
    ax, ay = -0.20, -0.22
    _tube(name + "_RLSA_pedestal", (ax, ay, 0.65), (ax, ay, 0.78),
          0.12, mats["titanium"], root, coll, 24)
    _tube(name + "_RLSA_back", (ax, ay, 0.76), (ax, ay, 0.80),
          0.33, mats["titanium"], root, coll, 64)
    _tube(name + "_RLSA_plate", (ax, ay, 0.80), (ax, ay, 0.813),
          0.32, mats["gold"], root, coll, 96)
    # Радиальные щели собраны одним мешем: читаются на сверхкрупном плане.
    if close:
        verts, faces = [], []
        for ring, count in ((0.09, 14), (0.15, 22), (0.21, 30), (0.27, 38)):
            for k in range(count):
                a = math.tau * (k + ring * 0.7) / count
                u, v = Vector((math.cos(a), math.sin(a), 0)), Vector((-math.sin(a), math.cos(a), 0))
                c = Vector((ax, ay, 0.8138)) + u * ring
                start = len(verts)
                verts.extend(tuple(c + u * x + v * y) for x, y in
                             ((-0.010, -0.0013), (0.010, -0.0013), (0.010, 0.0013), (-0.010, 0.0013)))
                faces.append((start, start + 1, start + 2, start + 3))
        _mesh(name + "_RLSA_slots", verts, faces, mats["black"], root, coll)
    # NEXT-C: задний металлический двигатель, без факела в терминальном полёте.
    _tube(name + "_NEXT_base", (-0.28, 0.25, -0.7), (-0.28, 0.25, -0.94),
          0.19, mats["titanium"], root, coll, 48, end_radius=0.24)
    _tube(name + "_NEXT_grid", (-0.28, 0.25, -0.94), (-0.28, 0.25, -0.951),
          0.225, mats["black"], root, coll, 48)
    # Звёздные датчики и короткая антенна на стороне +Y.
    for x in (-0.27, 0.23):
        _box(name + "_startracker_" + str(x), (x, 0.73, 0.16), (0.18, 0.22, 0.17),
             mats["black"], root, coll, 0.015)
        _tube(name + "_tracker_lens_" + str(x), (x, 0.75, 0.23), (x, 0.80, 0.32),
              0.058, mats["glass"], root, coll, 24)
    _tube(name + "_antenna_stub", (-0.43, 0.32, 0.68), (-0.43, 0.32, 1.06),
          0.013, mats["silver"], root, coll, 12)
    # Газовые микродвигатели — четыре угловых блока, условная мелкая компоновка.
    for i, (x, y) in enumerate(((-0.52, -0.53), (0.52, -0.53), (-0.52, 0.53), (0.52, 0.53))):
        _box(name + "_RCS_block_" + str(i), (x, y, -0.54), (0.17, 0.16, 0.12),
             mats["titanium"], root, coll, 0.012)
        _tube(name + "_RCS_nozzle_" + str(i), (x, y, -0.59), (x, y, -0.72),
              0.026, mats["black"], root, coll, 16, end_radius=0.052)
    _wire(name + "_harnessA", [(-0.48, -0.68, -0.3), (-0.44, -0.72, 0.1),
                              (-0.38, -0.70, 0.46), (-0.28, -0.66, 0.61)],
          0.011, mats["wire"], root, coll)
    _wire(name + "_harnessB", [(0.40, 0.38, 0.67), (0.47, 0.56, 0.69),
                              (0.53, 0.67, 0.49), (0.51, 0.68, 0.06)],
          0.012, mats["wire"], root, coll)
    if close:
        # Болты на рамке и шайбы: общий меш, чтобы не множить depsgraph.
        verts, faces = [], []
        for z in (-0.674, 0.674):
            for i in range(9):
                for x, y in ((-0.54 + i * 0.135, -0.65), (-0.54 + i * 0.135, 0.65)):
                    start = len(verts)
                    for zz, r in ((z, 0.010), (z + (0.004 if z > 0 else -0.004), 0.008)):
                        verts.extend((x + r * math.cos(k * math.tau / 6),
                                      y + r * math.sin(k * math.tau / 6), zz) for k in range(6))
                    faces.append(tuple(range(start + 6, start + 12)))
                    faces.extend((start + k, start + (k + 1) % 6,
                                  start + (k + 1) % 6 + 6, start + k + 6) for k in range(6))
        _mesh(name + "_fasteners", verts, faces, mats["silver"], root, coll)
    return {"root": root, "body": body, "panels": panels, "materials": mats}
