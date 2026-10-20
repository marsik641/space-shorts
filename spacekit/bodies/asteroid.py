"""Каменистые малые тела: объёмный реголит и угловатые валуны.

Единицы геометрии — метры. Форма художественная, а не восстановленная
фотограмметрическая модель DART. ``axes`` задаёт полуоси относительно radius.
Все объекты находятся под root; материалы используют его систему координат,
поэтому камень не «плывёт» при вращении астероида.

    a = build_asteroid("Dimorphos", radius=75.5, axes=(1.17, 1.15, .768))
    point = a["surface_point"]((0, -1, .1))

close: 81 920 граней основы, сколотые блоки и GN-россыпь мелких фракций;
mid: 20 480 граней основы и не более 900 валунов.
"""
import math
import os
import random
from itertools import combinations

import bmesh
import bpy
from mathutils import Matrix, Quaternion, Vector, noise

from .. import core as C

COLL = "Asteroids"


def _math(nodes, links, operation, a, b=None):
    n = nodes.new("ShaderNodeMath")
    n.operation = operation
    for index, value in enumerate((a, b)):
        if value is None:
            continue
        if isinstance(value, (int, float)):
            n.inputs[index].default_value = value
        else:
            links.new(value, n.inputs[index])
    return n.outputs[0]


def _ramp(nodes, links, source, stops, name):
    n = nodes.new("ShaderNodeValToRGB")
    n.label = name
    r = n.color_ramp
    r.interpolation = "EASE"
    r.elements.remove(r.elements[1])
    r.elements[0].position = stops[0][0]
    r.elements[0].color = stops[0][1]
    for position, color in stops[1:]:
        e = r.elements.new(position)
        e.color = color
    links.new(source, n.inputs[0])
    return n.outputs[0]


def _stone_material(name, root, radius, *, dust=False, texture=None):
    """Сухой силикат: пятна, сколы, миллиметровое зерно и тонкие трещины."""
    mat, nodes, links, out = C.new_material(name)
    mat.diffuse_color = (.135, .130, .119, 1)
    mat.roughness = .9
    bs = nodes.new("ShaderNodeBsdfPrincipled")
    bs.inputs["Roughness"].default_value = .9
    bs.inputs["IOR"].default_value = 1.48
    bs.inputs["Specular IOR Level"].default_value = .26
    links.new(bs.outputs[0], out.inputs["Surface"])
    coord = nodes.new("ShaderNodeTexCoord")
    coord.object = root
    pos = coord.outputs["Object"]

    def tex(scale, detail=3, rough=.68):
        n = nodes.new("ShaderNodeTexNoise")
        n.noise_dimensions = "3D"
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = rough
        links.new(pos, n.inputs["Vector"])
        return n

    # Масштабы в метрах; нормируем лишь крупную цветовую неоднородность.
    broad = tex(14 / radius, 4)
    chip = tex(3.8, 3)
    grain = tex(48, 2, .8)
    micro = tex(215, 1, .7)
    tone = _math(nodes, links, "MULTIPLY_ADD", broad.outputs["Fac"], .74)
    # Для MULTIPLY_ADD третий вход задаётся отдельно.
    tone.node.inputs[2].default_value = .10
    color = _ramp(nodes, links, tone, [
        (.20, (.045, .046, .046, 1)),
        (.41, (.100, .102, .103, 1)),
        (.60, (.185, .188, .187, 1)),
        (.83, (.275, .278, .275, 1)),
    ], "Силикатные обломки")

    # Редкие прерывистые трещины, без регулярной сетки «брусчатки».
    warp = tex(.78, 2)
    mul = nodes.new("ShaderNodeVectorMath")
    mul.operation = "SCALE"
    mul.inputs[3].default_value = .5
    links.new(warp.outputs["Color"], mul.inputs[0])
    add = nodes.new("ShaderNodeVectorMath")
    add.operation = "ADD"
    links.new(pos, add.inputs[0])
    links.new(mul.outputs[0], add.inputs[1])
    vor = nodes.new("ShaderNodeTexVoronoi")
    vor.feature = "DISTANCE_TO_EDGE"
    vor.voronoi_dimensions = "3D"
    vor.inputs["Scale"].default_value = .75
    links.new(add.outputs[0], vor.inputs["Vector"])
    fissure = _ramp(nodes, links, vor.outputs["Distance"], [
        (.004, (1, 1, 1, 1)), (.018, (0, 0, 0, 1)),
    ], "Тонкие щели")
    fissure = _math(nodes, links, "MULTIPLY", fissure,
                    _math(nodes, links, "GREATER_THAN", chip.outputs["Fac"], .53))
    dark = nodes.new("ShaderNodeMixRGB")
    dark.blend_type = "MIX"
    links.new(_math(nodes, links, "MULTIPLY", fissure, .65), dark.inputs[0])
    links.new(color, dark.inputs[1])
    dark.inputs[2].default_value = (.035, .030, .024, 1)
    color = dark.outputs[0]

    if dust:
        attr = nodes.new("ShaderNodeAttribute")
        attr.attribute_name = "AsteroidDust"
        powder = nodes.new("ShaderNodeMixRGB")
        links.new(_math(nodes, links, "MULTIPLY", attr.outputs["Fac"], .32), powder.inputs[0])
        links.new(color, powder.inputs[1])
        powder.inputs[2].default_value = (.145, .145, .141, 1)
        color = powder.outputs[0]
    else:
        # Разные валуны читаются отдельными фрагментами, а не одной коркой.
        info = nodes.new("ShaderNodeObjectInfo")
        tint = _ramp(nodes, links, info.outputs["Random"], [
            (.03, (.50, .52, .53, 1)), (.48, (.84, .85, .84, 1)),
            (.91, (.99, .97, .92, 1)),
        ], "Разная свежесть обломков")
        stone = nodes.new("ShaderNodeMixRGB")
        stone.blend_type = "MULTIPLY"
        stone.inputs[0].default_value = 1
        links.new(color, stone.inputs[1])
        links.new(tint, stone.inputs[2])
        color = stone.outputs[0]
    variation = nodes.new("ShaderNodeMixRGB")
    variation.blend_type = "MULTIPLY"
    variation.inputs[0].default_value = .40
    links.new(color, variation.inputs[1])
    mottling = _ramp(nodes, links, chip.outputs['Fac'], [
        (.25, (.30, .31, .32, 1)), (.48, (.80, .81, .82, 1)),
        (.72, (1.3, 1.29, 1.26, 1)),
    ], 'Пятна и свежие сколы')
    links.new(mottling, variation.inputs[2])
    surface_color = variation.outputs[0]
    stone_scan = None
    if texture:
        stone_scan = nodes.new('ShaderNodeTexImage')
        stone_scan.image = bpy.data.images.load(os.path.abspath(texture), check_existing=True)
        stone_scan.projection = 'BOX'
        stone_scan.projection_blend = .28
        stone_scan.extension = 'REPEAT'
        scale = nodes.new('ShaderNodeVectorMath')
        scale.operation = 'SCALE'
        scale.inputs['Scale'].default_value = .25 if dust else .55
        links.new(pos, scale.inputs[0])
        links.new(scale.outputs['Vector'], stone_scan.inputs['Vector'])
        gain = nodes.new('ShaderNodeVectorMath')
        gain.operation = 'SCALE'
        gain.inputs['Scale'].default_value = 5.0
        links.new(stone_scan.outputs['Color'], gain.inputs[0])
        blend = nodes.new('ShaderNodeMixRGB')
        blend.blend_type = 'MULTIPLY'
        blend.inputs[0].default_value = .88 if dust else .72
        links.new(surface_color, blend.inputs[1])
        links.new(gain.outputs['Vector'], blend.inputs[2])
        surface_color = blend.outputs[0]
    links.new(surface_color, bs.inputs["Base Color"])
    roughness = _math(nodes, links, "MULTIPLY_ADD", grain.outputs["Fac"], .16)
    roughness.node.inputs[2].default_value = .79
    links.new(roughness, bs.inputs["Roughness"])

    # Микрорельеф дополняет геометрию и не заменяет силуэт настоящих камней.
    height = _math(nodes, links, "SUBTRACT", chip.outputs["Fac"],
                   _math(nodes, links, "MULTIPLY", fissure, .68))
    bump1 = nodes.new("ShaderNodeBump")
    bump1.inputs["Strength"].default_value = .62
    bump1.inputs["Distance"].default_value = .09
    links.new(height, bump1.inputs["Height"])
    bump2 = nodes.new("ShaderNodeBump")
    bump2.inputs["Strength"].default_value = .42
    bump2.inputs["Distance"].default_value = .014
    links.new(grain.outputs["Fac"], bump2.inputs["Height"])
    links.new(bump1.outputs["Normal"], bump2.inputs["Normal"])
    bump3 = nodes.new("ShaderNodeBump")
    bump3.inputs["Strength"].default_value = .21
    bump3.inputs["Distance"].default_value = .003
    links.new(micro.outputs["Fac"], bump3.inputs["Height"])
    links.new(bump2.outputs["Normal"], bump3.inputs["Normal"])
    if stone_scan:
        grain_bump = nodes.new('ShaderNodeBump')
        grain_bump.inputs['Strength'].default_value = .55
        grain_bump.inputs['Distance'].default_value = .07 if dust else .025
        links.new(stone_scan.outputs['Color'], grain_bump.inputs['Height'])
        links.new(bump3.outputs['Normal'], grain_bump.inputs['Normal'])
        links.new(grain_bump.outputs['Normal'], bs.inputs['Normal'])
    else:
        links.new(bump3.outputs["Normal"], bs.inputs["Normal"])
    return mat


def _surface_functions(radius, axes, seed):
    rng = random.Random(seed * 73 + 9127)
    offset = Vector(tuple(rng.uniform(20, 180) for _ in range(3)))
    axes = Vector(axes)

    def field(direction):
        d = Vector(direction).normalized()
        # Нет случайного шума по вершинам: все LOD совпадают по форме.
        values = [noise.noise(d * frequency + offset,
                              noise_basis="PERLIN_ORIGINAL")
                  for frequency in (2.2, 5.1, 13.0, 36.0, 91.0)]
        radial = 1 + sum(a * v for a, v in zip((.085, .039, .018), values[:3]))
        # Изломанные гребни вместо округлых бугорков пластилина.
        radial += .014 * (abs(values[3]) - .20) + .005 * (abs(values[4]) - .20)
        return d, radial, values

    def point(direction):
        d, radial, _ = field(direction)
        return Vector((d.x * axes.x, d.y * axes.y, d.z * axes.z)) * (radius * radial)

    def normal(direction):
        d = Vector(direction).normalized()
        tangent = d.cross(Vector((0, 0, 1)))
        if tangent.length_squared < .001:
            tangent = d.cross(Vector((0, 1, 0)))
        tangent.normalize()
        bitangent = d.cross(tangent).normalized()
        step = .002
        dt = point((d + tangent * step).normalized()) - point((d - tangent * step).normalized())
        db = point((d + bitangent * step).normalized()) - point((d - bitangent * step).normalized())
        n = dt.cross(db).normalized()
        return n if n.dot(d) > 0 else -n

    return point, normal, field


def _rock_mesh(name, seed, material, slab=False):
    """Пересечение плоскостей раскола: широкие грани, сколы и узкие кромки."""
    rng = random.Random(seed)
    stretch = Vector((rng.uniform(.85, 1.25), rng.uniform(.74, 1.15),
                      rng.uniform(.35, .58) if slab else rng.uniform(.72, 1.08)))
    offset = Vector(tuple(rng.uniform(17, 211) for _ in range(3)))
    planes = []
    for axis in range(3):
        for sign in (-1, 1):
            n = Vector(tuple(rng.uniform(-.20, .20) for _ in range(3)))
            n[axis] = sign
            planes.append((n.normalized(), rng.uniform(.73, 1.02)))
    for _ in range(7):
        n = Vector(tuple(rng.uniform(-1, 1) for _ in range(3))).normalized()
        planes.append((n, rng.uniform(1.03, 1.29)))
    coordinates = []
    for triple in combinations(planes, 3):
        m = Matrix([p[0] for p in triple])
        if abs(m.determinant()) < 1e-5:
            continue
        p = m.inverted() @ Vector([q[1] for q in triple])
        if all(n.dot(p) <= d + 1e-5 for n, d in planes):
            coordinates.append(p)
    bm = bmesh.new()
    for p in coordinates:
        bm.verts.new(p)
    bmesh.ops.convex_hull(bm, input=list(bm.verts), use_existing_faces=False)
    bmesh.ops.dissolve_limit(bm, angle_limit=.002, verts=list(bm.verts),
                              edges=list(bm.edges), delimit={'NORMAL'})
    # Кромка узкая: камень не надувается и не превращается в шар.
    bmesh.ops.bevel(bm, geom=list(bm.edges), offset=.060, segments=2,
                    affect='EDGES', clamp_overlap=True)
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    bmesh.ops.subdivide_edges(bm, edges=list(bm.edges), cuts=2, use_grid_fill=True)
    bm.normal_update()
    for v in bm.verts:
        p = v.co.copy()
        relief = .070 * noise.noise(p * 5.3 + offset, noise_basis='PERLIN_ORIGINAL')
        relief += .060 * noise.noise(p * 1.7 + offset * 1.3, noise_basis='PERLIN_ORIGINAL')
        v.co += v.normal * relief
        v.co.x *= stretch.x
        v.co.y *= stretch.y
        v.co.z *= stretch.z
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(material)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    mesh.set_sharp_from_angle(angle=math.radians(30))
    mesh.update()
    return mesh


def _gravel(name, root, radius, axes, seed, point, prototypes, count):
    """Мелкие сколотые фракции одним GN-объектом, без тысяч объектов сцены."""
    rng = random.Random(seed + 63071)
    verts, scales, rotations, variants = [], [], [], []
    golden = math.pi * (3 - math.sqrt(5))
    for i in range(count):
        z = 1 - 2 * (i + rng.random()) / count
        angle = i * golden + rng.uniform(-.08, .08)
        ring = math.sqrt(max(0, 1-z*z))
        d = Vector((ring*math.cos(angle), ring*math.sin(angle), z))
        n = Vector((d.x/axes[0], d.y/axes[1], d.z/axes[2])).normalized()
        if i % 2 == 0:
            size = radius * (.0020 + .0060 * rng.random()**1.8)
        else:
            size = radius * (.0004 + .0016 * rng.random()**1.4)
        verts.append(point(d) - n * size * .35)
        scales.extend((size*rng.uniform(.75, 1.25), size*rng.uniform(.75, 1.2), size))
        rot = n.to_track_quat('Z', 'Y') @ Quaternion((0,0,1), rng.uniform(0, math.tau))
        rotations.extend(rot.to_euler())
        variants.append(rng.randrange(len(prototypes)))
    me = bpy.data.meshes.new(name+'_Points')
    me.from_pydata(verts, [], [])
    for nm, typ, field, data in [('scale','FLOAT_VECTOR','vector',scales),
                               ('rotation','FLOAT_VECTOR','vector',rotations),
                               ('variant','INT','value',variants)]:
        a = me.attributes.new(nm, typ, 'POINT')
        a.data.foreach_set(field, data)
    ob = bpy.data.objects.new(name, me)
    C.link(ob, COLL)
    ob.parent = root
    templates = bpy.data.collections.new(name+'_Templates')
    for i, mesh in enumerate(prototypes):
        templates.objects.link(bpy.data.objects.new(name+f'_Prototype{i}', mesh))
    ng = bpy.data.node_groups.new(name+'_GN', 'GeometryNodeTree')
    ng.interface.new_socket('Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
    ng.interface.new_socket('Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    N, L = ng.nodes, ng.links
    gi, go = N.new('NodeGroupInput'), N.new('NodeGroupOutput')
    ci = N.new('GeometryNodeCollectionInfo')
    ci.inputs['Collection'].default_value = templates
    ci.inputs['Separate Children'].default_value = True
    ci.inputs['Reset Children'].default_value = True
    ip = N.new('GeometryNodeInstanceOnPoints')
    ip.inputs['Pick Instance'].default_value = True
    L.new(gi.outputs['Geometry'], ip.inputs['Points'])
    L.new(ci.outputs['Instances'], ip.inputs['Instance'])
    for nm, typ, socket in [('scale','FLOAT_VECTOR','Scale'),
                            ('variant','INT','Instance Index')]:
        a = N.new('GeometryNodeInputNamedAttribute')
        a.data_type = typ
        a.inputs['Name'].default_value = nm
        L.new(a.outputs['Attribute'], ip.inputs[socket])
    a = N.new('GeometryNodeInputNamedAttribute')
    a.data_type = 'FLOAT_VECTOR'
    a.inputs['Name'].default_value = 'rotation'
    er = N.new('FunctionNodeEulerToRotation')
    L.new(a.outputs['Attribute'], er.inputs['Euler'])
    L.new(er.outputs['Rotation'], ip.inputs['Rotation'])
    L.new(ip.outputs['Instances'], go.inputs['Geometry'])
    ob.modifiers.new('Gravel', 'NODES').node_group = ng
    return ob


def build_asteroid(name, radius=75.5, location=(0, 0, 0), axes=(1.1, 1.08, .77),
                   seed=6, detail="close", boulder_count=2500, parent=None, texture=None):
    """Создать локальную модель rubble pile; ключи движения ставить на root.

    ``boulders`` — список объектов с общими данными mesh, ``materials`` — словарь.
    ``surface_point``/``surface_normal`` принимают направление в локальной
    системе root и возвращают точку/нормаль без учёта вынесенных валунов.
    ``radius`` — исходный масштаб, не максимальное расстояние до поверхности.
    """
    if radius <= 0 or len(axes) != 3 or min(axes) <= 0:
        raise ValueError("Положительные radius и три полуоси обязательны")
    if detail not in {"close", "mid"}:
        raise ValueError("detail: close или mid")
    if boulder_count < 0:
        raise ValueError("boulder_count не может быть отрицательным")
    radius = float(radius)
    seed = int(seed)
    root = C.empty(name + "_Root", coll=COLL, parent=parent, loc=location,
                   display="SPHERE", size=radius * .1)
    root["asteroid_radius_m"] = radius
    root["asteroid_seed"] = seed
    root["asteroid_axes"] = list(axes)
    root["shape_note"] = "Procedural scientific illustration; not a reconstructed DART shape model"
    mats = {
        "body": _stone_material(name + "_Regolith", root, radius, dust=True, texture=texture),
        "rock": _stone_material(name + "_Rock", root, radius, texture=texture),
    }
    point, normal, field = _surface_functions(radius, axes, seed)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=7 if detail == "close" else 6, radius=1)
    bm.verts.ensure_lookup_table()
    dust_values = []
    for v in bm.verts:
        direction = v.co.normalized()
        _, _, values = field(direction)
        v.co = point(direction)
        # Мелкая пыль скапливается в впадинах, а не равномерно красит рельеф.
        dust_values.append(max(0.0, min(1.0, .42 - values[2] * 1.4 - values[3] * 1.7)))
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    mesh = bpy.data.meshes.new(name + "_Terrain")
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(mats["body"])
    # Индексы BMesh сохраняются при to_mesh без удаления/добавления вершин.
    attr = mesh.attributes.new(name="AsteroidDust", type="FLOAT", domain="POINT")
    for i, value in enumerate(dust_values):
        attr.data[i].value = value
    for p in mesh.polygons:
        p.use_smooth = True
    body = bpy.data.objects.new(name + "_Body", mesh)
    C.link(body, COLL)
    body.parent = root
    mesh.update()

    rng = random.Random(seed * 8137 + 31)
    prototypes = [_rock_mesh(name + f"_RockMesh_{i:02d}", seed * 1013 + i,
                             mats["rock"], slab=i >= 20) for i in range(24)]
    count = int(boulder_count) if detail == "close" else min(int(boulder_count), 900)
    boulders = []
    golden = math.pi * (3 - math.sqrt(5))
    for i in range(count):
        # Равномерный рисунок Фибоначчи с джиттером не даёт голых полюсов.
        z = 1 - 2 * (i + rng.uniform(.15, .85)) / max(count, 1)
        angle = i * golden + rng.uniform(-.07, .07)
        ring = math.sqrt(max(0, 1 - z * z))
        direction = Vector((ring * math.cos(angle), ring * math.sin(angle), z))
        n = normal(direction)
        # Много мелких обломков, редкие валуны до нескольких метров.
        size = radius * (.003 + .021 * rng.random() ** 3.0)
        if i % 109 == 0:
            size = radius * rng.uniform(.025, .047)
        prototype = prototypes[rng.randrange(len(prototypes))]
        ob = bpy.data.objects.new(name + f"_Boulder_{i:04d}", prototype)
        C.link(ob, COLL)
        ob.parent = root
        ob.location = point(direction) - n * (size * .30)
        ob.rotation_mode = "QUATERNION"
        ob.rotation_quaternion = n.to_track_quat("Z", "Y") @ Quaternion((0, 0, 1), rng.uniform(0, math.tau))
        ob.scale = (size * rng.uniform(.8, 1.3), size * rng.uniform(.75, 1.2), size * rng.uniform(.7, 1.05))
        boulders.append(ob)

    gravel = _gravel(name+'_Gravel', root, radius, axes, seed, point, prototypes,
                     100000 if detail == 'close' else 12000)

    return {
        "root": root, "body": body, "boulders": boulders, "materials": mats,
        "radius": radius, "axes": tuple(axes), "surface_point": point,
        "surface_normal": normal, "rock_meshes": prototypes,
        "gravel": gravel,
    }
