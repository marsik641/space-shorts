"""Свет: цвет чёрного тела, калибровка освещённости точечного источника, прожекторы.

Калибровка (Cycles, AgX, exposure 0): пиксель белого диффуза под точечным светом мощностью P (Вт)
на расстоянии d = K_POINT · P / d². Отсюда подбор мощности звезды под нужную яркость планеты:
    P = point_energy_for(irradiance, d)
Ориентиры из эпизода 001: тёмная базальтовая планета хорошо читается при irradiance ≈ 4–6
(планета на 40 ед. — 20000–30000 Вт), светлая ледяная — при 2–3.
"""
import math

from mathutils import Vector

K_POINT = 0.0303


def blackbody_rgb(temp_k):
    """Приблизительный линейный RGB (Rec.709) для цветовой температуры, нормированный по max=1.
    Аппроксимация Tanner Helland в sRGB -> линеаризация."""
    t = max(1000.0, min(40000.0, temp_k)) / 100.0
    if t <= 66:
        r = 255.0
        g = 99.4708025861 * math.log(t) - 161.1195681661
    else:
        r = 329.698727446 * ((t - 60) ** -0.1332047592)
        g = 288.1221695283 * ((t - 60) ** -0.0755148492)
    if t >= 66:
        b = 255.0
    elif t <= 19:
        b = 0.0
    else:
        b = 138.5177312231 * math.log(t - 10) - 305.0447927307

    def lin(c):
        c = max(0.0, min(255.0, c)) / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    rgb = [lin(r), lin(g), lin(b)]
    m = max(rgb)
    return tuple(c / m for c in rgb)


def point_irradiance(energy, distance):
    """Яркость белого диффуза (лин.) под точечным светом energy на расстоянии distance."""
    return K_POINT * energy / max(distance, 1e-9) ** 2


def point_energy_for(irradiance, distance):
    """Мощность точечного света (Вт), дающая заданную яркость белого диффуза на расстоянии distance."""
    return irradiance * distance ** 2 / K_POINT


def spot_factor(spot_ob, target):
    """Доля мощности прожектора в направлении target (как в Cycles: smoothstep по spot_blend).
    Возвращает (доля 0..1, расстояние)."""
    mw = spot_ob.matrix_world
    pos = mw.translation
    axis = (mw.to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()
    to = target - pos
    dist = to.length
    if dist < 1e-9:
        return 0.0, dist
    cosang = axis.dot(to / dist)
    sd = spot_ob.data
    cos_half = math.cos(sd.spot_size * 0.5)
    if cosang <= cos_half:
        return 0.0, dist
    smooth = (1.0 - cos_half) * sd.spot_blend
    t = cosang - cos_half
    if smooth > 0.0 and t < smooth:
        x = t / smooth
        return x * x * (3.0 - 2.0 * x), dist
    return 1.0, dist


def add_distant_sun(name, direction, strength=3.0, temp_k=5772.0, angle_deg=0.05, star_dist=5.0e4,
                    star_radius=None, star_strength=4.0e3, coll="Lights"):
    """Далёкое Солнце (вид из внешней Солнечной системы): параллельный свет SUN с направления direction
    (вектор НА звезду) + видимая звезда — эмиссионная сфера на star_dist (по умолчанию угловой радиус
    ≈ 1.5 пикселя при 35 мм/1080p; блум и Fog Glow дают ореол). strength — освещённость (Вт/м², как SUN Cycles).
    Сфера не отбрасывает тени и не светит на сцену (свет — только от лампы). Возвращает (лампа, сфера)."""
    import bpy
    from . import core as C
    d = Vector(direction).normalized()
    ld = bpy.data.lights.new(name, "SUN")
    ld.energy = strength
    ld.angle = math.radians(angle_deg)
    ld.color = blackbody_rgb(temp_k)
    lamp = bpy.data.objects.new(name, ld)
    C.link(lamp, coll)
    lamp.rotation_mode = "QUATERNION"
    lamp.rotation_quaternion = Vector((0, 0, -1)).rotation_difference(-d)
    r = star_radius if star_radius is not None else star_dist * 4.0e-4
    me = bpy.data.meshes.new(f"{name}_Disk")
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=r)
    bm.to_mesh(me)
    bm.free()
    mat, N, L, out = C.new_material(f"{name}_DiskMat")
    em = N.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*blackbody_rgb(temp_k), 1.0)
    em.inputs["Strength"].default_value = star_strength
    L.new(em.outputs[0], out.inputs["Surface"])
    mat.cycles.emission_sampling = "NONE"
    me.materials.append(mat)
    disk = bpy.data.objects.new(f"{name}_Disk", me)
    C.link(disk, coll)
    disk.location = d * star_dist
    disk.visible_shadow = False
    disk.visible_diffuse = disk.visible_glossy = disk.visible_transmission = disk.visible_volume_scatter = False
    return lamp, disk


def add_point_star(name, energy, temp_k=6000.0, radius=0.3, location=(0, 0, 0), parent=None, coll="Lights"):
    """Точечный источник-звезда с цветом чёрного тела. Возвращает объект лампы."""
    import bpy
    from . import core as C
    ld = bpy.data.lights.new(name, "POINT")
    ld.energy = energy
    ld.shadow_soft_size = radius
    ld.color = blackbody_rgb(temp_k)
    ob = bpy.data.objects.new(name, ld)
    C.link(ob, coll)
    ob.location = location
    if parent is not None:
        ob.parent = parent
    return ob
