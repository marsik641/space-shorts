"""SN 1987A: параметры реальной системы и их «экранный» масштаб — общие для всех шотов эпизода.

Реальность (числа и источники — facts.md):
    Sk −69 202 — голубой сверхгигант B3 I, R ≈ 43 R☉ (3·10⁷ км), Teff ≈ 16 000 K, ~20 M☉; БМО, 51.4 кпк ≈ 168 000 св. лет
    Слои перед коллапсом (H, He, C, O, Ne, Si, Fe): звезда и железное ядро — реальные (ядро «размером с Землю»,
    ×5000 меньше звезды, Woosley & Janka 2005), промежуточные радиусы — схема (LAYERS_KM, геометрическая лесенка)
    Железное ядро ≈ 1.5 M☉, коллапс < 1 с при ~¼ c до протонейтронной звезды R ≈ 30 км (≈ 10 км — за следующие
    секунды); ~10⁵⁸ нейтрино
    23.02.1987 07:35:35 UT — 12 событий в списке Kamiokande-II за 12.4 с (№6 — фон; засчитано 11; KII_T_S — Hirata 1987)
    SN 1987A под горизонтом детекторов: Камиока −19.7° (сквозь Землю ≈ 4300 км), IMB −42°, Баксан −55° (расчёт по
    координатам SN и детекторов на 07:35:35 UT, facts.md)
    Свет — ~3 ч позже (выход ударной волны на поверхность ~2 ч после коллапса)
    Кольца: экваториальное a = 0.66 св. года, наклон ≈ 44°, выброшено ~20 тыс. лет до взрыва; внешние — ×2.2–2.3,
    плоскости в ~1.3 св. года по обе стороны (песочные часы); горячие точки с 1995 г., 26 к 2022, максимум ~2009
Экран:
    v1/v6/v7 (звезда, остаток): 1 ед. = R★; кольца строятся в тех же ед. (ER ≈ 2·10⁵ ед.) под родителем WORLD,
          который масштабируется: камера стоит, мир «наезжает» (небо на бесконечности не плывёт);
    v2–v4 (разрез): 1 ед. = 1000 км под масштабируемым WORLD; звезда/ядро ×5000 — честно, толщины слоёв — схема;
          разрез — октант (условность);
    v3 (коллапс): замедление ×SLOW_COLLAPSE;
    v4: шкала времени ломаная (часы — титрами): нейтрино ×~60, ударная волна до поверхности (1.8 ч) — ×~1000;
    v5 (детектор): 1 ед. = 1 м, реальные размеры Kamiokande-II, времена событий реальные (после 1.9 с — ускорение ×3);
    v6: годы 1987 → 2016 за ~8 с.
Цвета слоёв и элементов — условные коды (линии излучения); нейтрино показаны видимыми иглами (условность).
"""
import math
import random

from mathutils import Matrix, Vector

R_SUN_KM = 695700.0
LY_KM = 9.4607e12
R_STAR_KM = 43.0 * R_SUN_KM                     # 2.99e7 км
TEFF = 16000.0
DIST_LY = 168000.0

# --- слои перед коллапсом (от центра наружу): имя, внешний радиус (км), цвет (лин. RGB), яркость, линия горения
LAYERS_KM = [
    ("Fe", 6.0e3, (1.00, 0.50, 0.12), 2.2, 0.0),             # «размером с Землю» (WJ05)
    ("Si", 1.4e4, (0.10, 0.42, 1.00), 1.25, 5.0),             # линия горения у основания — ярче (блум: «оболочки энергии»)
    ("Ne", 3.2e4, (0.52, 0.18, 1.00), 1.15, 4.6),
    ("O", 9.0e4, (0.02, 0.85, 0.66), 1.05, 4.2),
    ("C", 2.5e5, (0.50, 1.00, 0.10), 0.95, 4.0),
    ("He", 9.0e5, (1.00, 0.55, 0.04), 0.95, 3.8),
    ("H", R_STAR_KM, (1.00, 0.12, 0.25), 0.85, 3.4),          # 43 R☉
]
LAYER_NAMES = {"Fe": "Iron", "Si": "Silicon", "Ne": "Neon", "O": "Oxygen", "C": "Carbon", "He": "Helium",
               "H": "Hydrogen"}
CUT_UNIT_KM = 1000.0                            # v2–v4: 1 ед. = 1000 км
FE_MSUN = 1.5
NS_R_KM = 10.0                                  # радиус нейтронной звезды (~20 км в поперечнике)
PNS_R_KM = 30.0                                 # протонейтронная звезда сразу после отскока
EARTH_R_KM = 6371.0
SLOW_COLLAPSE = 10.0                            # v3: последние ~0.3 с падения → 3 с экрана («under a second»)

# --- нейтринный всплеск в Kamiokande-II (Hirata et al. 1987, PRL 58, 1490): времена событий от первого, с
KII_T_S = [0.000, 0.107, 0.303, 0.324, 0.507, 0.686, 1.541, 1.728, 1.915, 9.219, 10.433, 12.439]
KII_SKIP = (5,)                                 # №6 — фон (Fiorillo 2023): засчитано 11, в списке 12 (Нобелевский комитет — 12)
KII_POINT = {0: 18.0, 1: 15.0}                  # первые два события «смотрят» от БМО: 18° и 15° (IAUC 4338, Hirata 1987;
                                                # в Hirata 1988 у №2 уже 40 ± 27°) — направления позитронов в кадре
KII_UT = "07:35:35 UT"
SN_ALT_DEG = -19.7                              # SN 1987A под горизонтом Камиоки в 07:35:35 UT (Fiorillo 2023, A.8; расчёт)
SN_AZ_DEG = 166.0                               # азимут от севера (расчёт по координатам SN, IAUC 4316)
EARTH_CHORD_KM = 4295.0                         # путь сквозь Землю (Fiorillo 2023; 4363 км — Lunardini & Smirnov 2001)

# --- Kamiokande-II (внутренний детектор)
TANK_R_M = 7.2
TANK_H_M = 13.1
PMT_R_M = 0.254                                 # 20 дюймов
PMT_PITCH_M = 1.0
CHERENKOV_DEG = 41.4                            # cos θ = 1/(nβ), n = 1.333, β → 1

# --- кольца (ед. R★ в v6/v7)
ER_LY = 0.66                                    # 6.23e17 см (Panagia 2003)
ER_A = ER_LY * LY_KM / R_STAR_KM                # ≈ 2.1e5 R★
ER_INCL_DEG = 44.0
ER_PA_DEG = 83.0                                # позиционный угол большой оси (от севера к востоку), по снимкам HST
OR_SCALE = (2.27, 2.19)                         # внешние кольца (С, Ю): большие полуоси 1.84″ и 1.77″ против 0.81″
OR_INCL = (45.0, 38.0)
OR_OFFSET = 1.3 / ER_LY                         # плоскости — в ~1.3 св. года по обе стороны (Burrows 1995, Crotts & Heathcote 2000)
HOT_FIRST = 1995.4                              # первая горячая точка (PA 29°), найдена ретроспективно (France 2010)
HOT_ALL = 2003.5                                # ≥ 20 пятен к ноябрю 2003 (Panagia 2004)
HOT_N = 26                                      # 26 пятен за 1994–2022 (Tegkelidis 2024)
HOT_PEAK = 2009.0                               # максимум свечения пятен; дальше кольцо тускнеет (Fransson 2015)
EJ_FRAC_2024 = 0.55                             # внешний край яркого выброса / радиус ER (снимки JWST/HST)
STAR2 = (-1.72, 0.55, 18000.0)                  # соседние звёзды: (восток, север) в радиусах ER, Teff — по HST
STAR3 = (1.10, -0.35, 22000.0)

SEEDS = {"star": 3, "cut": 5, "ej": 7, "ring": 11, "or_n": 13, "or_s": 17, "hot": 19, "nu": 23, "kii": 29}

# --- вид «с Земли»: камера v1/v6/v7 смотрит на звезду вдоль +Y, север — +Z, восток — −X (небо изнутри)
VIEW_DIR = Vector((0.0, 1.0, 0.0))
NORTH = Vector((0.0, 0.0, 1.0))
EAST = Vector((-1.0, 0.0, 0.0))


def sky_pa(v):
    """Позиционный угол (град, от севера к востоку) проекции вектора v на картинную плоскость."""
    return math.degrees(math.atan2(v.dot(EAST), v.dot(NORTH))) % 360.0


def ring_basis(incl_deg=ER_INCL_DEG, pa_deg=ER_PA_DEG, near="N"):
    """Базис плоскости кольца: (major, y, normal) — большая ось по PA в картинной плоскости, нормаль наклонена к лучу
    зрения на incl; near — какой край ближе к Земле (север). Возвращает Matrix 3×3 (столбцы — оси объекта)."""
    pa = math.radians(pa_deg)
    major = (NORTH * math.cos(pa) + EAST * math.sin(pa)).normalized()
    minor = VIEW_DIR.cross(major).normalized()
    if minor.dot(NORTH) < 0:
        minor = -minor
    i = math.radians(incl_deg)
    toward = -VIEW_DIR                           # к наблюдателю
    # точка кольца в направлении minor (север) ближе к Земле: смещена к наблюдателю → в плоскости кольца вектор
    # m' = minor·cos i + toward·sin i; нормаль ⟂ major и m'
    mp = (minor * math.cos(i) + toward * math.sin(i) * (1.0 if near == "N" else -1.0)).normalized()
    nrm = major.cross(mp).normalized()
    return Matrix((major, mp, nrm)).transposed()


def ring_euler(**kw):
    return ring_basis(**kw).to_euler("XYZ")


def ring_angle_for_pa(pa_deg, basis=None):
    """Азимут в плоскости кольца (от большой оси), который на небе даёт позиционный угол pa_deg."""
    M = basis or ring_basis()
    best, err = 0.0, 1e9
    for k in range(3600):
        a = 0.1 * k
        v = M @ Vector((math.cos(math.radians(a)), math.sin(math.radians(a)), 0.0))
        e = abs((sky_pa(v) - pa_deg + 180.0) % 360.0 - 180.0)
        if e < err:
            best, err = a, e
    return best


def hot_spots(n=HOT_N, seed=SEEDS["hot"]):
    """Азимуты (град, в плоскости кольца) и годы загорания: первая — PA ≈ 29° (1995.4), дальше по кольцу в обе стороны
    с разбросом, все — к HOT_ALL."""
    rnd = random.Random(seed)
    first = ring_angle_for_pa(29.0)
    angs, yrs = [], []
    for k in range(n):
        angs.append(first + 360.0 * k / n + rnd.uniform(-4.0, 4.0))
        dist = min(k, n - k) / (n / 2.0)                    # 0 у первой, 1 — напротив
        yrs.append(HOT_FIRST + (HOT_ALL - HOT_FIRST) * min(1.0, 0.12 * rnd.random() + 0.88 * dist ** 0.8))
    yrs[0] = HOT_FIRST
    return angs, yrs


def layer_radii(unit_km=CUT_UNIT_KM):
    return [r / unit_km for _, r, *_ in LAYERS_KM]


def layers_for_kit(unit_km=CUT_UNIT_KM):
    """LAYERS_KM → формат bodies.star_layers.build_cutaway."""
    return [dict(name=nm, r=r / unit_km, color=col, strength=s, line=ln) for nm, r, col, s, ln in LAYERS_KM]


def kii_events(seed=SEEDS["kii"]):
    """События Kamiokande-II для визуализации: (t, вершина, направление позитрона, амплитуда). Вершины — случайно в
    фидуциальном объёме (2 м от стен), направления — почти изотропны (обратный β-распад), амплитуда ~ энергия."""
    rnd = random.Random(seed)
    out = []
    for i, t in enumerate(KII_T_S):
        while True:
            x, y = rnd.uniform(-1, 1), rnd.uniform(-1, 1)
            if x * x + y * y < 1:
                break
        R = TANK_R_M - 2.0
        v = Vector((x * R, y * R, rnd.uniform(-TANK_H_M / 2 + 2.0, TANK_H_M / 2 - 2.0)))
        while True:
            d = Vector((rnd.gauss(0, 1), rnd.gauss(0, 1), rnd.gauss(0, 1)))
            if d.length > 1e-3:
                break
        d = d.normalized()
        if i in KII_POINT:                                  # позитрон «смотрит» от БМО (вдоль полёта нейтрино)
            back = -sn_dir_local()
            ax = back.cross(Vector((0, 0, 1))).normalized()
            d = (Matrix.Rotation(math.radians(KII_POINT[i]), 3, ax) @ back).normalized()
        out.append(dict(t=t, v=v, d=d, amp=0.6 + 0.4 * rnd.random(), skip=i in KII_SKIP))
    return out


def sn_dir_local():
    """Направление НА SN 1987A в системе бака (z — вверх, y — север): под горизонтом на |SN_ALT_DEG|."""
    alt, az = math.radians(SN_ALT_DEG), math.radians(SN_AZ_DEG)
    return Vector((math.cos(alt) * math.sin(az), math.cos(alt) * math.cos(az), math.sin(alt))).normalized()
