"""Орбиты: круговые (пивот + вращение), кеплеровские эллипсы (ключи по кадрам), масштаб времени.

Время в роликах условное: реальные периоды сжимаются в секунды ролика с сохранением ОТНОШЕНИЙ
(резонансы и порядок планет остаются честными):
    periods = video_periods({"b": 25.3, "c": 66.5, "d": 98.2}, ref="b", ref_seconds=20.0)
"""
import math

from mathutils import Vector

from . import anim
from . import core as C

AU_KM = 1.495978707e8
G_AU3_MSUN_DAY2 = 2.959122082855911e-4     # гравитационная постоянная в а.е.³/(M☉·сут²)


# ---------------------------------------------------------------- масштаб времени и законы Кеплера
def video_periods(real_periods, ref, ref_seconds):
    """{имя: реальный период (любые ед.)} -> {имя: период в секундах ролика}; ref получает ref_seconds."""
    k = ref_seconds / real_periods[ref]
    return {n: p * k for n, p in real_periods.items()}


def kepler_period_days(a_au, m_central_msun):
    """Период по 3-му закону Кеплера (сутки)."""
    return 2.0 * math.pi * math.sqrt(a_au ** 3 / (G_AU3_MSUN_DAY2 * m_central_msun))


def kepler_a_au(period_days, m_central_msun):
    """Большая полуось (а.е.) по периоду."""
    return (G_AU3_MSUN_DAY2 * m_central_msun * (period_days / (2.0 * math.pi)) ** 2) ** (1.0 / 3.0)


def solve_kepler(M, e, tol=1e-10):
    """Эксцентрическая аномалия E из M = E − e·sin E (Ньютон)."""
    E = M if e < 0.8 else math.pi
    for _ in range(50):
        d = (E - e * math.sin(E) - M) / (1.0 - e * math.cos(E))
        E -= d
        if abs(d) < tol:
            break
    return E


def kepler_xy(a, e, mean_anomaly, omega_deg=0.0):
    """Положение на эллипсе в плоскости орбиты (фокус — центр масс в начале координат)."""
    E = solve_kepler(mean_anomaly % (2 * math.pi), e)
    x = a * (math.cos(E) - e)
    y = a * math.sqrt(1.0 - e * e) * math.sin(E)
    w = math.radians(omega_deg)
    return x * math.cos(w) - y * math.sin(w), x * math.sin(w) + y * math.cos(w)


# ---------------------------------------------------------------- орбиты в сцене
def _body_root(body):
    """Планеты из bodies.planets: на орбиту ставится root (наклон оси), а не меш."""
    import bpy
    if "pl_root_name" in body.keys():
        return bpy.data.objects[body["pl_root_name"]]
    return body


def add_orbit(scene, body, *, center_parent, a, period_s, phase_deg=0.0, frame_start=1, frame_end=300,
              incl_deg=0.0, inertial_axis=True):
    """Круговая орбита: пивот (ребёнок center_parent) вращается вокруг Z ключами LINEAR; body — его ребёнок
    на расстоянии a. inertial_axis: встречное вращение body, чтобы ось планеты не «прецессировала» с орбитой.
    body — root из build_planet (если передан меш планеты, берётся его root). Возвращает пивот."""
    body = _body_root(body)
    pivot = C.empty(f"{body.name}_OrbitPivot", coll="Planets", parent=center_parent, size=a * 0.05)
    pivot.rotation_mode = "ZYX"  # сначала вращение по Z, затем наклон орбиты по X
    pivot.rotation_euler = (math.radians(incl_deg), 0.0, 0.0)
    w = 360.0 / period_s
    anim.key_rot_z(pivot, math.radians(phase_deg), w, frame_start, frame_end, scene)
    body.parent = pivot
    body.location = (a, 0.0, 0.0)
    if inertial_axis:
        body.rotation_mode = "XYZ"
        z0 = body.rotation_euler[2] - math.radians(phase_deg)
        anim.key_rot_z(body, z0, -w, frame_start, frame_end, scene)
    return pivot


def add_kepler_orbit(scene, body, *, center_parent, a, e, period_s, phase_deg=0.0, omega_deg=0.0,
                     incl_deg=0.0, node_deg=0.0, frame_start=1, frame_end=300, step=1):
    """Эллиптическая орбита (закон площадей честный): плоскость-пивот (наклон incl вокруг линии узлов node),
    body — ребёнок с ключами положения через каждые step кадров (LINEAR между ключами).
    phase_deg — средняя аномалия в frame_start, omega_deg — аргумент перицентра. Возвращает пивот."""
    body = _body_root(body)
    plane = C.empty(f"{body.name}_OrbitPlane", coll="Planets", parent=center_parent, size=a * 0.05)
    plane.rotation_mode = "ZXY"
    plane.rotation_euler = (math.radians(incl_deg), 0.0, math.radians(node_deg))
    body.parent = plane
    fps = C.scene_fps(scene)
    n = 2.0 * math.pi / (period_s * fps)          # рад/кадр
    M0 = math.radians(phase_deg)
    f = frame_start
    while f <= frame_end + step:
        x, y = kepler_xy(a, e, M0 + n * (f - frame_start), omega_deg)
        body.location = (x, y, 0.0)
        body.keyframe_insert("location", frame=f)
        f += step
    anim.set_interpolation(body, "LINEAR", path_contains="location")
    return plane


def position_on_orbit(a, period_s, phase_deg, t_s, e=0.0, omega_deg=0.0):
    """Положение тела (в плоскости орбиты) в момент t_s секунд ролика — для расчёта кадрирования заранее."""
    M = math.radians(phase_deg) + 2.0 * math.pi * t_s / period_s
    if e == 0.0:
        return Vector((a * math.cos(M), a * math.sin(M), 0.0))
    x, y = kepler_xy(a, e, M, omega_deg)
    return Vector((x, y, 0.0))
