"""KELT-9b: набор Borsa2019 + температуры яркости Mansfield2020.

Общие планы: 1 ед. = 1e6 км. Радиусы и полуось в одном масштабе.
Крупные планы: радиус планеты = 1, звезда по +X, ось планеты Z.
Тепловая карта — иллюстрация, НЕ измеренная локальная температура газа.
4566/2556 К — яркость полушарий в полосе 4.5 мкм. Течения художественные.
Синхронное вращение принято как модель. Нормаль орбиты около 87° к оси
звезды по Ahlers2020; это не земной транзитный наклон i.
Сплюснутость Ahlers добавляется как иллюстрация, не единый fit с Borsa.
1.4811235 суток → 8 экранных секунд; размеры общих планов не увеличены.
"""
import math
from spacekit import orbits as ORB

AU_KM = 149597870.7
R_SUN_KM = 695700.0
R_JUP_KM = 71492.0
R_STAR_SOL = 2.418
M_STAR_SOL = 2.32
R_PLANET_JUP = 1.936
M_PLANET_JUP = 2.88
A_AU = 0.03368
PERIOD_D = 1.4811235
OBLIQUITY_DEG = 87.0
STAR_FLATTENING = 1.0 / 1.089
T_STAR_K = 9600.0
T_DAY_K = 4566.0
T_NIGHT_K = 2556.0
R_STAR = R_STAR_SOL * R_SUN_KM / 1e6
R_PLANET = R_PLANET_JUP * R_JUP_KM / 1e6
A = A_AU * AU_KM / 1e6
PERIODS_S = ORB.video_periods({"b": PERIOD_D}, ref="b", ref_seconds=8.0)
SEED = 809


def orbit_position(t_s):
    """Круговая орбита, нормаль наклонена к оси звезды на 87°."""
    ang = 2.0 * math.pi * t_s / PERIODS_S["b"] + 0.35
    inc = math.radians(OBLIQUITY_DEG)
    return (A * math.cos(ang), A * math.sin(ang) * math.cos(inc),
            A * math.sin(ang) * math.sin(inc))
