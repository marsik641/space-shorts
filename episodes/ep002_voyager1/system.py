"""Voyager 1: реальные данные (JPL Horizons) и «экранные» масштабы — общие для всех шотов эпизода.

Реальность (числа и источники — facts.md; траектории — trajectory.json, JPL Horizons, запрос 2026-10-18):
    Voyager 1 (-31): гелиоцентрические положения, эклиптика J2000, а.е.; 1977-09-05 … 2027-01-01
    Voyager 2 (-32): то же, 1977-08-20 … 2027-01-01
    1 световой день = 173.1446 а.е.; геометрическое расстояние Земля–V1 достигает его 2026-11-18 10:16:07 UTC (MILESTONE_UTC, NASA)
    планеты: оскулирующие элементы на 2026-11-15 (a, e, i, Ω, ω, M)
Экран:
    карта (v2, v3): 1 ед. = 1 а.е., оси мира = эклиптика J2000 (x — на точку весны, z — северный полюс эклиптики);
                    размеры тел и толщины линий — условные (на деле планеты и аппарат — точки);
    крупные планы:  1 ед. = 1 м, оси мира те же; Солнце — параллельный свет с направления SUN_DIR (из data),
                    видимая точка-звезда; ось тарелки — на Землю (± 0.33° от Солнца — в кадре неразличимо).
    небо: Млечный Путь ориентирован по-настоящему (GAL_ECL — галактика -> эклиптика), звёзды поля — процедурные.
Время: фронт сигнала и прорисовка траектории — со сжатием (нелинейная шкала), реальные моменты — подписями.
"""
import json
import math
import os

from mathutils import Matrix, Vector

from spacekit.sky import A_ICRS_GAL

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = json.load(open(os.path.join(HERE, "trajectory.json"), encoding="utf-8"))

AU_KM = 149597870.7
LIGHT_DAY_AU = 173.144633
LIGHT_S_PER_AU = 499.004784            # с на 1 а.е.
# Веха по NASA — ГЕОМЕТРИЧЕСКОЕ расстояние от центра Земли = 1 св. день (facts.md); видимая дальность с
# поправкой на время света (Horizons OBSERVER, trajectory.json light_day) пересекает его позже — 19.11 02:17 UTC.
MILESTONE_UTC = "2026-11-18 10:16:07"
MILESTONE_JD = 2461362.5 + (10 + 16 / 60 + 7 / 3600) / 24 + 69.184 / 86400.0   # JD TDB (UTC + 69.184 с)

PLANETS = {"199": "MERCURY", "299": "VENUS", "399": "EARTH", "499": "MARS", "599": "JUPITER",
           "699": "SATURN", "799": "URANUS", "899": "NEPTUNE"}
SEEDS = {"sky": 7, "wind": 3, "heliopause": 5}


def jd_from_date(y, m, d, h=0.0):
    """Юлианская дата (григорианский календарь, UT/TDB — как подано)."""
    if m <= 2:
        y, m = y - 1, m + 12
    a = y // 100
    b = 2 - a + a // 4
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + h / 24.0 + b - 1524.5


def _interp(series, jd):
    """Линейная интерполяция [jd, x, y, z] по времени."""
    if jd <= series[0][0]:
        return Vector(series[0][1:])
    for a, b in zip(series, series[1:]):
        if jd <= b[0]:
            u = (jd - a[0]) / (b[0] - a[0])
            return Vector(a[1:]).lerp(Vector(b[1:]), u)
    return Vector(series[-1][1:])


def v1_at(jd):
    return _interp(DATA["v1"], jd)


def v2_at(jd):
    return _interp(DATA["v2"], jd)


def resample(series, jd0, jd1, n):
    """n точек траектории равномерно по времени jd0..jd1 -> (точки, jd)."""
    jds = [jd0 + (jd1 - jd0) * i / (n - 1) for i in range(n)]
    return [_interp(series, j) for j in jds], jds


# ---------------------------------------------------------------- планеты (Кеплер по элементам Horizons)
def _solve_kepler(M, e):
    E = M if e < 0.8 else math.pi
    for _ in range(30):
        E -= (E - e * math.sin(E) - M) / (1.0 - e * math.cos(E))
    return E


def planet_at(pid, jd):
    """Гелиоцентрическое положение планеты (а.е., эклиптика J2000) по оскулирующим элементам на 2026-11-15."""
    el = DATA["elements"][pid]
    M = math.radians(el["MA"] + 360.0 * (jd - el["jd_tdb"]) / el["period_d"])
    e, a = el["e"], el["a"]
    E = _solve_kepler(math.fmod(M, 2 * math.pi), e)
    x = a * (math.cos(E) - e)
    y = a * math.sqrt(1 - e * e) * math.sin(E)
    R = (Matrix.Rotation(math.radians(el["OM"]), 3, "Z") @ Matrix.Rotation(math.radians(el["i"]), 3, "X")
         @ Matrix.Rotation(math.radians(el["W"]), 3, "Z"))
    return R @ Vector((x, y, 0.0))


V1_NOW = v1_at(MILESTONE_JD)                       # положение Voyager 1 в момент вехи
EARTH_NOW = planet_at("399", MILESTONE_JD)
SUN_DIR = (-V1_NOW).normalized()                   # с Voyager на Солнце
EARTH_DIR = (EARTH_NOW - V1_NOW).normalized()      # с Voyager на Землю (ось тарелки)
EVENTS = DATA["events"]


# ---------------------------------------------------------------- реальная ориентация Млечного Пути
# ICRS -> галактические (sky.A_ICRS_GAL); экватор -> эклиптика J2000 (ε = 23.4392911°)
_A_G = Matrix([tuple(r) for r in A_ICRS_GAL])
_EPS = math.radians(23.4392911)
_EQ2ECL = Matrix(((1, 0, 0), (0, math.cos(_EPS), math.sin(_EPS)), (0, -math.sin(_EPS), math.cos(_EPS))))
GAL_ECL = tuple((_EQ2ECL @ _A_G.transposed()).to_euler("XYZ"))   # galactic -> world (эклиптика)


# ---------------------------------------------------------------- система карты (шоты v3, v4)
# Поворот эклиптики так, чтобы линия Земля -> Voyager 1 (на момент вехи) смотрела вверх (+Z мира):
# в вертикальном кадре 9:16 путь в 173 а.е. ложится по длинной стороне.
MAP_ROT = (V1_NOW - EARTH_NOW).normalized().rotation_difference(Vector((0, 0, 1))).to_matrix()
GAL_MAP = tuple((MAP_ROT @ (_EQ2ECL @ _A_G.transposed())).to_euler("XYZ"))


def to_map(p):
    """Эклиптика (а.е.) -> система карты (а.е.)."""
    return MAP_ROT @ Vector(p)


def ecl_to_radec(v):
    """Направление (эклиптика J2000) -> (RA°, Dec°) — для проверок."""
    q = _EQ2ECL.transposed() @ Vector(v).normalized()
    return math.degrees(math.atan2(q.y, q.x)) % 360.0, math.degrees(math.asin(q.z))


def light_time_h(p, q):
    """Время света между точками (а.е.) в часах."""
    return (Vector(p) - Vector(q)).length * LIGHT_S_PER_AU / 3600.0
