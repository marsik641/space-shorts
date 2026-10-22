"""Энцелад: 1 единица = 1 км (общие/локальные планы).
Радиус252.10км,GM7.21037км³/с²,орбита238000км/32.9ч — facts.md.
Макро льдинки: условное увеличение; не измеренный размер. Поток времени
приблизительный, не газодинамика. Геометрия трещин — реконструкция.
Камерные ракурсы не воспроизводят конкретный пролёт Cassini.
"""
from spacekit import orbits as ORB
R_KM=252.10
GM_KM3_S2=7.21037
G_KM_S2=GM_KM3_S2/R_KM**2
SATURN_DIST_KM=238000.0
SATURN_R_KM=60268.0
REAL_PERIODS_D={"enceladus":32.9/24}
PERIODS_S=ORB.video_periods(REAL_PERIODS_D,ref="enceladus",ref_seconds=32.9*3600)
SEED=707
