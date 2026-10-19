"""Кольцо изнутри (эп. 004+): поле ледяных частиц от сантиметров до метров в слое толщиной ~10 м. 1 ед. = 1 м.

    from spacekit.fx import ring_particles as RP
    pf = RP.build_field(sc, center=(0, 0, 0), tau=0.6, seed=4)
    # pf["objects"] — инстансеры по классам размеров, pf["counts"] — сколько частиц в каждом

Распределение размеров — степенной закон n(a) ∝ a^−q (q≈3, радиусы a_min…a_max; Zebker et al. 1985, Cuzzi et al.
2010) с нормировкой на нормальную оптическую толщину τ = ∫πa²n(a)da. Классы (a0, a1, R) — частицы этого диапазона
только в круге радиуса R вокруг center: мелочь — рядом с камерой, глыбы — до горизонта поля (дальше — диск
spacekit.bodies.rings с hole=). Высота над средней плоскостью — нормальная, σ от sigma_z[0] (крупные) до sigma_z[1]
(мелкие): крупные частицы лежат тоньше. wakes=(λ, θ°, w) — гравитационные «следы» кольца A (Colwell et al. 2006):
частицы гуще в полосах шагом λ под углом θ к оси X (w — глубина модуляции). Крупные не пересекаются (сетка).
Формы — 8 вариантов «рыхлых комьев» (икосфера + фрактальный шум + эллипсоид), инстансы GN по атрибутам
variant/rot/scale, материал — ледяной реголит, оттенок от Object Info → Random (на инстанс).
Частицы неподвижны: относительные скорости соседей — мм/с (за минуту — сантиметры).
"""
import math
import random

import bmesh
import bpy
import numpy as np
from mathutils import Vector, noise

from .. import core as C

COLL = "RingField"
# (a0, a1 — радиусы частиц, м; R — радиус области, м; подразбиение икосферы; вариантов формы)
# Мелочь (R ≤ near_r в build_field) — не кругом, а коридором шириной 2R вдоль пути камеры: луч сквозь плотное облако
# мелких инстансов дорог (ep004 v4: 218 тыс. частиц 3–30 см в круге 50–150 м — 150 с/кадр, коридором — в разы меньше)
CLASSES = [(2.0, 5.0, 1500.0, 4, 8), (0.8, 2.0, 900.0, 3, 8), (0.3, 0.8, 400.0, 3, 6),
           (0.1, 0.3, 50.0, 2, 5), (0.03, 0.1, 12.0, 1, 4)]


def _seg_dist(xy, path):
    """Расстояние в плоскости XY от точек xy (k×2) до ломаной path [(x, y), …]."""
    d = np.full(len(xy), np.inf)
    for (x0, y0), (x1, y1) in zip(path, path[1:]):
        p0, v = np.array([x0, y0]), np.array([x1 - x0, y1 - y0])
        t = np.clip(((xy - p0) @ v) / max(float(v @ v), 1e-9), 0.0, 1.0)
        d = np.minimum(d, np.linalg.norm(xy - (p0 + t[:, None] * v), axis=1))
    return d


def _corridor_area(path, R):
    L = sum(math.hypot(x1 - x0, y1 - y0) for (x0, y0), (x1, y1) in zip(path, path[1:]))
    return 2.0 * R * L + math.pi * R * R


def counts(tau, a_min, a_max, q, classes, area_scale=1.0, path=None, near_r=150.0):
    """Число частиц в каждом классе: площадь (πR² или коридор вдоль path) × ∫n(a)da по [a0, a1] при нормировке на τ."""
    if abs(q - 3.0) < 1e-6:
        i2 = math.log(a_max / a_min)
    else:
        i2 = (a_max ** (3 - q) - a_min ** (3 - q)) / (3 - q)
    c = tau / (math.pi * i2)
    out = []
    for (a0, a1, R, _sd, _nv) in classes:
        per_m2 = c / (q - 1.0) * (a0 ** (1 - q) - a1 ** (1 - q))
        area = _corridor_area(path, R) if (path and R <= near_r) else math.pi * R * R
        out.append(int(round(per_m2 * area * area_scale)))
    return out


def _sizes(rng, n, a0, a1, q):
    """Радиусы по закону a^−q на [a0, a1] (обратная функция распределения)."""
    u = rng.random(n)
    k = 1.0 - q
    return (a0 ** k + u * (a1 ** k - a0 ** k)) ** (1.0 / k)


def _rock_mesh(name, seed, subdiv):
    """Рыхлый ком радиуса ~1: икосфера, вытянутая в эллипсоид, с фрактальной неровностью и вмятинами."""
    rnd = random.Random(seed)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=1.0)
    ax = Vector((1.0, rnd.uniform(0.72, 0.95), rnd.uniform(0.55, 0.85)))
    off = Vector((rnd.uniform(0, 50), rnd.uniform(0, 50), rnd.uniform(0, 50)))
    for v in bm.verts:
        p = v.co.normalized()
        lump = noise.fractal(p * 1.3 + off, 0.75, 2.0, 4, noise_basis="PERLIN_ORIGINAL")
        dent = noise.noise(p * 3.1 + off * 1.7, noise_basis="VORONOI_F1")
        d = 1.0 + 0.24 * lump - 0.035 * max(0.0, 0.35 - dent)
        v.co = Vector((p.x * ax.x, p.y * ax.y, p.z * ax.z)) * d
    mean = sum(v.co.length for v in bm.verts) / len(bm.verts)
    for v in bm.verts:
        v.co /= mean
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    return me


def _mat_ice(name, tint_a, tint_b, rough=0.92):
    """Ледяной реголит: оттенок на инстанс (Random), пятна и мелкая шероховатость в координатах объекта."""
    mat, N, L, out = C.new_material(name)
    from ..bodies.planets import _NB
    b = _NB(mat.node_tree)
    oi = b.node("ShaderNodeObjectInfo")
    tc = b.node("ShaderNodeTexCoord")
    p = tc.outputs["Object"]
    col = b.mix(oi.outputs["Random"], tint_a, tint_b)
    # шейдер лёгкий: внутри поля луч отскакивает между частицами — каждая октава шума умножается на отскоки
    nz = b.noise(p, 4.0, detail=3, rough=0.6)
    blot = b.lin(b.sep(nz.outputs["Color"])[0], 0.3, 0.7, 0.84, 1.10)
    col = b.v("SCALE", col, scale=blot)
    bump = b.node("ShaderNodeBump", {"Strength": 0.5, "Distance": 0.06, "Height": nz.outputs[0]})
    bsdf = b.node("ShaderNodeBsdfPrincipled", {"Base Color": col, "Roughness": rough, "Normal": bump.outputs[0]})
    b.put(bsdf.inputs["Specular IOR Level"], 0.25)
    b.put(bsdf.inputs["Diffuse Roughness"], 1.0)
    b.put(out.inputs["Surface"], bsdf.outputs[0])
    return mat


def _instancer_group(name, coll):
    ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = ng.nodes, ng.links
    gi = N.new("NodeGroupInput")
    go = N.new("NodeGroupOutput")
    ci = N.new("GeometryNodeCollectionInfo")
    ci.transform_space = "ORIGINAL"
    ci.inputs["Collection"].default_value = coll
    ci.inputs["Separate Children"].default_value = True
    ci.inputs["Reset Children"].default_value = True
    iop = N.new("GeometryNodeInstanceOnPoints")
    iop.inputs["Pick Instance"].default_value = True

    def attr(nm, typ):
        a = N.new("GeometryNodeInputNamedAttribute")
        a.data_type = typ
        a.inputs["Name"].default_value = nm
        return a.outputs["Attribute"]

    e2r = N.new("FunctionNodeEulerToRotation")
    L.new(attr("rot", "FLOAT_VECTOR"), e2r.inputs["Euler"])
    L.new(gi.outputs["Geometry"], iop.inputs["Points"])
    L.new(ci.outputs["Instances"], iop.inputs["Instance"])
    L.new(attr("variant", "INT"), iop.inputs["Instance Index"])
    L.new(e2r.outputs["Rotation"], iop.inputs["Rotation"])
    L.new(attr("scale", "FLOAT_VECTOR"), iop.inputs["Scale"])
    L.new(iop.outputs["Instances"], go.inputs["Geometry"])
    return ng


def _no_overlap(xyz, a, cell):
    """Отбросить пересекающиеся (жадно, крупные первыми): сетка по XY с шагом cell."""
    order = np.argsort(-a)
    grid = {}
    keep = np.zeros(len(a), bool)
    for i in order:
        x, y, z = xyz[i]
        gx, gy = int(math.floor(x / cell)), int(math.floor(y / cell))
        ok = True
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in grid.get((gx + dx, gy + dy), ()):
                    d = xyz[j] - xyz[i]
                    if d[0] * d[0] + d[1] * d[1] + d[2] * d[2] < (0.92 * (a[i] + a[j])) ** 2:
                        ok = False
                        break
                if not ok:
                    break
            if not ok:
                break
        if ok:
            keep[i] = True
            grid.setdefault((gx, gy), []).append(i)
    return keep


def _clear_mask(xyz, a, clear):
    """True — частица не задевает «коридоры» камеры: clear = [(p0, p1, r)] — отрезки p0–p1 с зазором r (м)."""
    ok = np.ones(len(a), bool)
    for p0, p1, r in clear:
        p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
        d = p1 - p0
        L2 = max(float(d @ d), 1e-9)
        t = np.clip(((xyz - p0) @ d) / L2, 0.0, 1.0)
        dist = np.linalg.norm(xyz - (p0 + t[:, None] * d), axis=1)
        ok &= dist > (r + a)
    return ok


def build_field(scene, *, center=(0.0, 0.0, 0.0), tau=0.6, a_min=0.01, a_max=5.0, q=3.0, classes=None,
                sigma_z=(1.6, 3.2), wakes=(60.0, 25.0, 0.55), seed=1, tint_a=(0.56, 0.47, 0.38),
                tint_b=(0.66, 0.62, 0.57), area_scale=1.0, coll=COLL, max_class=None, clear=(), path=None,
                near_r=150.0):
    """Поле частиц кольца (1 ед. = 1 м) вокруг center в плоскости XY. clear — коридоры камеры [(p0, p1, зазор)],
    в мировых м; path — путь камеры в XY [(x, y), …]: классы с R ≤ near_r раздаются коридором вдоль него.
    Возвращает dict(objects, counts, material)."""
    classes = classes or CLASSES
    if max_class is not None:
        classes = classes[:max_class]
    rng = np.random.default_rng(9000 + seed)
    mat = _mat_ice(f"RP_Ice_{seed}", tint_a, tint_b)
    nums = counts(tau, a_min, a_max, q, classes, area_scale, path, near_r)
    cx, cy, cz = center
    objs = []
    for ci, ((a0, a1, R, subdiv, nv), n) in enumerate(zip(classes, nums)):
        # кандидаты с запасом под отбор следов и пересечений
        m = int(n * (1.0 + (wakes[2] if wakes else 0.0)) * 1.25) + 16
        if path and R <= near_r:
            # коридор: равномерно в охватывающем прямоугольнике, отбор по расстоянию до пути
            px, py = np.array([p[0] for p in path]), np.array([p[1] for p in path])
            bx0, bx1, by0, by1 = px.min() - R, px.max() + R, py.min() - R, py.max() + R
            frac = _corridor_area(path, R) / ((bx1 - bx0) * (by1 - by0))
            mm = int(m / max(frac, 1e-3)) + 16
            cand = np.stack([rng.uniform(bx0, bx1, mm), rng.uniform(by0, by1, mm)], -1)
            cand = cand[_seg_dist(cand, path) <= R][:m]
            x, y = cand[:, 0] - cx, cand[:, 1] - cy
        else:
            r = R * np.sqrt(rng.random(m))
            ph = rng.random(m) * 2 * np.pi
            x, y = r * np.cos(ph), r * np.sin(ph)
        if wakes:
            lam, th, w = wakes
            t = math.radians(th)
            s = x * math.cos(t) + y * math.sin(t)
            sn = -x * math.sin(t) + y * math.cos(t)
            s = s + 0.25 * lam * np.sin(2 * np.pi * sn / (4.3 * lam) + seed)
            pr = (1.0 + w * np.cos(2 * np.pi * s / lam)) / (1.0 + w)
            ok = rng.random(m) < pr
            x, y = x[ok], y[ok]
        a = _sizes(rng, len(x), a0, a1, q)
        la = (math.log(0.5 * (a0 + a1)) - math.log(a_max)) / (math.log(a_min) - math.log(a_max))
        sz = sigma_z[0] + (sigma_z[1] - sigma_z[0]) * min(max(la, 0.0), 1.0)
        z = np.clip(rng.normal(0.0, sz, len(x)), -2.5 * sz, 2.5 * sz)
        xyz = np.stack([x + cx, y + cy, z + cz], -1)
        if clear:
            keep = _clear_mask(xyz, a, clear)
            xyz, a = xyz[keep], a[keep]
        if a0 >= 0.8:
            keep = _no_overlap(xyz, a, 2.0 * a1)
            xyz, a = xyz[keep], a[keep]
        xyz, a = xyz[:n], a[:n]
        k = len(a)
        # формы: свой набор вариантов на класс (подразбиение под размер на экране)
        vc = bpy.data.collections.new(f"RP_Shapes{ci}")           # не в сцене: только источник инстансов
        for vi in range(nv):
            ob = bpy.data.objects.new(f"RP_Rock{ci}_{vi}", _rock_mesh(f"RP_rock{ci}_{vi}", seed * 101 + ci * 13 + vi,
                                                                      subdiv))
            ob.data.materials.append(mat)
            vc.objects.link(ob)
        me = bpy.data.meshes.new(f"RP_Points{ci}")
        me.vertices.add(k)
        me.vertices.foreach_set("co", xyz.astype(np.float32).ravel())
        av = me.attributes.new("variant", "INT", "POINT")
        av.data.foreach_set("value", rng.integers(0, nv, k).astype(np.int32))
        ar = me.attributes.new("rot", "FLOAT_VECTOR", "POINT")
        ar.data.foreach_set("vector", (rng.random((k, 3)) * 2 * np.pi).astype(np.float32).ravel())
        asc = me.attributes.new("scale", "FLOAT_VECTOR", "POINT")
        asc.data.foreach_set("vector", np.repeat(a[:, None], 3, 1).astype(np.float32).ravel())
        me.update()
        ob = bpy.data.objects.new(f"RP_Field{ci}", me)
        C.link(ob, coll)
        mod = ob.modifiers.new("Instances", "NODES")
        mod.node_group = _instancer_group(f"RP_Inst{ci}", vc)
        objs.append(ob)
        print(f"[ring_particles] class {ci}: a {a0}-{a1} m, R {R:.0f} m -> {k} particles")
    return dict(objects=objs, counts=[len(o.data.vertices) for o in objs], material=mat)
