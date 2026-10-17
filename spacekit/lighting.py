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
