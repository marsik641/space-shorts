"""Эпизод 001 — PSR B1257+12, вертикальная версия для Shorts: 1080×1920, 60 fps, 60 с.

    blender -b --factory-startup -P episodes/ep001_psr_b1257/shots_9x16.py -- <v1..v6> [preview F,..] [final] [save]

Монтаж (кадры @60, склейки встык, многие — на вспышках маяка):
    v1  270  хук: луч проходит через камеру, вспышка на ~0.75 с
    v2  690  анатомия: отъезд и облёт — линии поля, оба луча вертикальными спицами
    v3  720  система сверху: лучи-прожекторы метут пылевое кольцо, три планеты на орбитах
    v4  960  Полтергейст внизу, пульсар над ним; сияния на ночной стороне, луч «прожектором» по планете
    v5  600  «восход пульсара» из-за лимба Фобетора (контровой свет в дымке)
    v6  360  разгон к звезде; последний кадр = первый кадр v1 (бесшовная петля Shorts)
В крупных планах ось вращения пульсара лежит горизонтально в кадре (tilt Ry 90°): лучи вращаются
в вертикальной плоскости и пересекают высокий кадр целиком.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
sys.path.insert(0, HERE)

from mathutils import Euler, Vector

from spacekit import camera as CAM
from spacekit import core as C
from spacekit import shot as S
from spacekit import sky as SKY
from spacekit.bodies import neutron_star as NS
from spacekit.bodies import planets as PL
from spacekit.fx import dust_ring as DR

from system import ALPHA, RING, SEEDS, SPIN_HZ, system_planets, system_pulsar

OUT = os.path.join(C.OUT, "ep001_psr_b1257", "9x16")
S.OPT.update(fmt="9x16", fps=60)
SHOTS = {"v1": 270, "v2": 690, "v3": 720, "v4": 960, "v5": 600, "v6": 360}
sph = CAM.sph

# крупные планы: ось вращения -> мировая +X (горизонталь кадра)
CLOSE_TILT = Euler((0.0, math.radians(90.0), 0.0))
V1_PHASE0 = -110.0          # фаза вращения: первая вспышка (луч в камеру) около 0.75 с
V1_START = dict(d=9.0, az=-90.0, el=13.0)


def local(dist, az, el, tilt=CLOSE_TILT):
    """Точка в системе пульсара (сферические коорд. относительно оси вращения) -> мир."""
    return tuple(tilt.to_matrix() @ Vector(sph(dist, az, el)))


def close_pulsar(sc, n, phase0, surface=2.5):
    return NS.build_pulsar(sc, tilt_euler=CLOSE_TILT, R=1.0, alpha_deg=ALPHA, spin_hz=SPIN_HZ, phase0_deg=phase0,
                           frame_start=1, frame_end=n, beam_length=40, beam_half_angle_deg=8, detail="close",
                           field_lines=True, particles=False, surface_strength=surface, field_strength=2.5)


GAL_CLOSE = None


def gal_close():
    """Одна ориентация неба для v1/v2/v6 (петля v6->v1 без скачка звёзд)."""
    return SKY.gal_for_view(Vector(local(1, -90 + 180, -13)), tilt_deg=25, l_center_deg=110)


# ---------------------------------------------------------------- v1: хук
def shot_v1():
    n = SHOTS["v1"]
    ex = 0.0
    sc = S.base_scene(n, exposure=ex, samples=40, adaptive=0.03)
    sc.render.motion_blur_shutter = 0.4
    cam, tgt = CAM.camera_rig("Cam_V1", lens=35)
    s = V1_START
    CAM.key_camera(cam, tgt, [
        dict(frame=1, loc=local(s["d"], s["az"], s["el"]), target=(0, 0, 0), lens=35),
        dict(frame=n, loc=local(6.8, -72, 12), target=(0, 0, 0.25), lens=35),
    ])
    stars = SKY.build_sky(sc, cam, ex, gal=gal_close())
    psr = close_pulsar(sc, n, V1_PHASE0)
    S.report_flash("v1", NS.key_pulse_flash(psr, cam, 1, n))
    S.finish(sc, stars, star_samples=24)
    return sc, n


# ---------------------------------------------------------------- v2: анатомия пульсара
def shot_v2():
    n = SHOTS["v2"]
    ex = 0.0
    sc = S.base_scene(n, exposure=ex, samples=40, adaptive=0.03)
    sc.render.motion_blur_shutter = 0.4
    cam, tgt = CAM.camera_rig("Cam_V2", lens=35)
    CAM.key_camera(cam, tgt, [
        dict(frame=1, loc=local(6.8, -72, 12), target=(0, 0, 0.25), lens=35),
        dict(frame=380, loc=local(9.5, -30, 26), target=(0, 0, 0.1), lens=32),
        dict(frame=n, loc=local(12.5, 15, 34), target=(0, 0, 0), lens=30),
    ])
    stars = SKY.build_sky(sc, cam, ex, gal=gal_close())
    # фаза — продолжение v1 (склейка встык без скачка вращения)
    psr = close_pulsar(sc, n, V1_PHASE0 + 360.0 * SPIN_HZ * SHOTS["v1"] / S.OPT["fps"])
    S.report_flash("v2", NS.key_pulse_flash(psr, cam, 1, n))
    S.finish(sc, stars, star_samples=24)
    return sc, n


# ---------------------------------------------------------------- v3: система сверху
def shot_v3():
    n = SHOTS["v3"]
    ex = 0.9
    sc = S.base_scene(n, exposure=ex, samples=40, adaptive=0.03)
    cam, tgt = CAM.camera_rig("Cam_V3", lens=24)
    CAM.key_camera(cam, tgt, [
        dict(frame=1, loc=sph(190, -70, 68), target=(0, 0, 0), lens=24),
        dict(frame=n, loc=sph(140, -40, 52), target=(0, 0, -4), lens=24),
    ])
    stars = SKY.build_sky(sc, cam, ex, gal=SKY.gal_for_view(-Vector(sph(1, -55, 62)), tilt_deg=70, l_center_deg=60))
    psr = system_pulsar(sc, n, beam_intensity=4.0)
    S.report_flash("v3", NS.key_pulse_flash(psr, cam, 1, n))
    system_planets(sc, psr, n, {"draugr": 40, "poltergeist": 200, "phobetor": 300})
    DR.build_dust_ring(sc, parent=psr["root"], ring_radiance=5.0, anisotropy=0.3, arc_gain=4.0,
                       frame_start=1, frame_end=n, lights=[psr["light"]] + list(psr["spots"]), **RING)
    S.finish(sc, stars, star_samples=24)
    return sc, n


# ---------------------------------------------------------------- v4: Полтергейст, пульсар над ним
V4_PSR = (0.0, 32.0, 118.0)


def v4_camera(phase_deg, dist, w_near):
    """Пульсар почти над планетой: разнос по вертикали кадра. Камера под планетой со стороны −Y."""
    u = Vector(V4_PSR).normalized()
    v = Vector((0, -1, 0))
    v = (v - u * v.dot(u)).normalized()
    ph = math.radians(phase_deg)
    c = (u * math.cos(ph) + v * math.sin(ph)) * dist
    dp = (-c).normalized()
    dq = (Vector(V4_PSR) - c).normalized()
    look = (dp * w_near + dq * (1.0 - w_near)).normalized()
    return dict(loc=tuple(c), target=tuple(c + look * 10.0)), look


def shot_v4():
    n = SHOTS["v4"]
    ex = 0.8
    sc = S.base_scene(n, exposure=ex, samples=48, bloom_strength=0.8, adaptive=0.03)
    d = Vector(V4_PSR).length
    cam, tgt = CAM.camera_rig("Cam_V4", lens=26)
    k1, view = v4_camera(132, 4.5, 0.50)
    k2, _ = v4_camera(122, 3.8, 0.47)
    CAM.key_camera(cam, tgt, [dict(frame=1, lens=26, **k1), dict(frame=n, lens=26, **k2)])
    c1 = Vector(k1["loc"])
    # Фобетор — далёкий серп слева, на полпути к пульсару
    side = view.cross(Vector((0, 0, 1))).normalized()
    ph_loc = tuple(c1 + (view + side * 0.28 + Vector((0, 0, 0.12))).normalized() * 70.0)
    stars = SKY.build_sky(sc, cam, ex, gal=SKY.gal_for_view(view, tilt_deg=70, l_center_deg=20), star_brightness=0.8)
    s2 = (d / 40.0) ** 2
    psr = NS.build_pulsar(sc, location=V4_PSR, tilt_euler=CAM.tilt_for_target(V4_PSR, (0, 0, 0), ALPHA),
                          R=0.3, alpha_deg=ALPHA, spin_hz=SPIN_HZ, frame_start=1, frame_end=n,
                          beam_length=220, beam_half_angle_deg=8, detail="far",
                          light_energy=30000.0 * s2, spot_energy=36000.0 * s2, field_lines=False, particles=False)
    S.report_flash("v4", NS.key_pulse_flash(psr, cam, 1, n, width_deg=16))
    # камера под планетой: ось наклонена так, что южный полюс смотрит к камере — овал сияний на ночной стороне
    pg = PL.build_planet(sc, "poltergeist", radius=1.0, location=(0, 0, 0), detail="close", seed=SEEDS["poltergeist"],
                         axial_tilt_deg=25, tilt_azimuth_deg=180.0, rot_period_s=90.0,
                         frame_start=1, frame_end=n, aurora_strength=1.0, light=psr["light"])
    ph = PL.build_planet(sc, "phobetor", radius=0.95, location=ph_loc, detail="far", seed=SEEDS["phobetor"],
                         axial_tilt_deg=10, rot_period_s=60.0, frame_start=1, frame_end=n,
                         aurora_strength=0.6, light=psr["light"])
    for p in (pg, ph):
        PL.key_sun_power(p, psr, 1, n)
    S.finish(sc, stars, star_samples=24)
    return sc, n


# ---------------------------------------------------------------- v5: «восход пульсара» над Фобетором
V5_PSR = (0.0, 115.0, 22.0)


def shot_v5():
    n = SHOTS["v5"]
    ex = 0.6
    sc = S.base_scene(n, exposure=ex, samples=48, bloom_strength=0.8, adaptive=0.03)
    u = Vector(V5_PSR).normalized()
    cam, tgt = CAM.camera_rig("Cam_V5", lens=30)
    # камера за планетой (пульсар скрыт диском), затем поднимается — пульсар выходит из-за лимба
    c1 = -u * 3.4 + Vector((0.35, 0, -0.55))
    c2 = -u * 3.0 + Vector((-0.25, 0, 1.15))
    t1 = Vector((0, 0, 0.55))
    t2 = Vector(V5_PSR) * 0.02 + Vector((0, 0, 0.85))
    CAM.key_camera(cam, tgt, [dict(frame=1, loc=tuple(c1), target=tuple(t1), lens=30),
                              dict(frame=n, loc=tuple(c2), target=tuple(t2), lens=30)])
    stars = SKY.build_sky(sc, cam, ex, gal=SKY.gal_for_view(u, tilt_deg=-55, l_center_deg=90), star_brightness=0.8)
    d = Vector(V5_PSR).length
    s2 = (d / 40.0) ** 2
    psr = NS.build_pulsar(sc, location=V5_PSR, tilt_euler=CAM.tilt_for_target(V5_PSR, tuple(c2), ALPHA),
                          R=0.3, alpha_deg=ALPHA, spin_hz=SPIN_HZ, frame_start=1, frame_end=n,
                          beam_length=200, beam_half_angle_deg=8, detail="far",
                          light_energy=18000.0 * s2, spot_energy=24000.0 * s2, field_lines=False, particles=False)
    S.report_flash("v5", NS.key_pulse_flash(psr, cam, 1, n, width_deg=14))
    ph = PL.build_planet(sc, "phobetor", radius=1.0, location=(0, 0, 0), detail="close", seed=SEEDS["phobetor"],
                         axial_tilt_deg=20, tilt_azimuth_deg=180.0, rot_period_s=70.0,
                         frame_start=1, frame_end=n, aurora_strength=0.8, light=psr["light"])
    PL.key_sun_power(ph, psr, 1, n)
    S.finish(sc, stars, star_samples=24)
    return sc, n


# ---------------------------------------------------------------- v6: разгон к звезде -> петля в v1
def shot_v6():
    n = SHOTS["v6"]
    ex = 0.0
    sc = S.base_scene(n, exposure=ex, samples=40, adaptive=0.03)
    sc.render.motion_blur_shutter = 0.4
    cam, tgt = CAM.camera_rig("Cam_V6", lens=35)
    s = V1_START
    # конечный кадр совпадает с первым кадром v1: то же положение, цель, объектив, небо и фаза вращения
    CAM.key_camera(cam, tgt, [
        dict(frame=1, loc=local(70.0, -118, 30), target=(0, 0, 0), lens=35),
        dict(frame=n + 1, loc=local(s["d"], s["az"], s["el"]), target=(0, 0, 0), lens=35),
    ])
    stars = SKY.build_sky(sc, cam, ex, gal=gal_close())
    phase0 = V1_PHASE0 - 360.0 * SPIN_HZ * n / S.OPT["fps"]
    psr = close_pulsar(sc, n, phase0)
    S.report_flash("v6", NS.key_pulse_flash(psr, cam, 1, n))
    S.finish(sc, stars, star_samples=24)
    return sc, n


BUILDERS = {"v1": shot_v1, "v2": shot_v2, "v3": shot_v3, "v4": shot_v4, "v5": shot_v5, "v6": shot_v6}

if __name__ == "__main__":
    S.run(BUILDERS, out_dir=OUT)
