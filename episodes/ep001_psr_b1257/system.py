"""PSR B1257+12: параметры реальной системы и их «экранный» масштаб — общие для 16:9 и 9:16 версий.

Реальность (Wolszczan & Frail 1992; Konacki & Wolszczan 2003):
    пульсар: P = 6.22 мс (161 об/с), ~1.4 M☉, «переработанный» MSP, ~2300 св. лет, Дева
    A Драугр:     0.020 M⊕, a = 0.19 а.е., P = 25.3 сут
    B Полтергейст: 4.3 M⊕,  a = 0.36 а.е., P = 66.5 сут
    C Фобетор:     3.9 M⊕,  a = 0.46 а.е., P = 98.2 сут   (B и C близки к резонансу 3:2)
Экран: ≈100 ед. = 1 а.е.; радиусы планет преувеличены; вращение замедлено до 0.6 об/с (~270×);
орбиты ускорены с сохранением отношений периодов (Драугр — 20 с ролика).
"""
from spacekit import orbits as ORB
from spacekit.bodies import neutron_star as NS
from spacekit.bodies import planets as PL

SPIN_HZ = 0.6
ALPHA = 78.0                       # магнитный наклон: лучи почти в плоскости орбит -> «прожектор» по планетам
REAL_PERIODS_D = {"draugr": 25.3, "poltergeist": 66.5, "phobetor": 98.2}
PERIODS_S = ORB.video_periods(REAL_PERIODS_D, ref="draugr", ref_seconds=20.0)
ORBITS = {
    # kind: (a, период в секундах ролика, радиус тела)
    "draugr": (19.0, PERIODS_S["draugr"], 0.8),
    "poltergeist": (36.0, PERIODS_S["poltergeist"], 2.4),
    "phobetor": (46.0, PERIODS_S["phobetor"], 2.2),
}
RING = dict(inner=55, outer=78, thickness=3.5, flare=1.1, seed=3,
            rotation_period_s=20.0 * (66.5 / 19.0) ** 1.5)  # кеплеровское вращение на r≈66
SEEDS = {"draugr": 7, "poltergeist": 11, "phobetor": 5}   # фиксированные: кадры воспроизводимы


def system_planets(sc, psr, frames, phases, detail=None):
    """Три планеты на круговых орбитах вокруг psr['root'], подсветка атмосфер ключами по свету пульсара."""
    detail = detail or {}
    out = {}
    for kind, (a, period, r) in ORBITS.items():
        p = PL.build_planet(sc, kind, radius=r, detail=detail.get(kind, "far"), frame_start=1,
                            frame_end=frames, seed=SEEDS[kind], light=psr["light"])
        ORB.add_orbit(sc, p["root"], center_parent=psr["root"], a=a, period_s=period,
                      phase_deg=phases[kind], frame_start=1, frame_end=frames)
        out[kind] = p
    for p in out.values():
        PL.key_sun_power(p, psr, 1, frames)
    return out


def system_pulsar(sc, n, beam_intensity=2.5, frame_start=1):
    """Пульсар для общих планов системы (detail='far')."""
    return NS.build_pulsar(sc, R=0.3, alpha_deg=ALPHA, spin_hz=SPIN_HZ, frame_start=frame_start, frame_end=n,
                           beam_length=110, beam_half_angle_deg=8, detail="far",
                           light_energy=20000.0, spot_energy=60000.0, beam_intensity=beam_intensity,
                           field_lines=False, particles=False)
