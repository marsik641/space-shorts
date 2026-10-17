"""Эпизод 001 — PSR B1257+12, горизонтальная версия 16:9 1080p30 (оригинальный ролик, 47 с).

    blender -b --factory-startup -P episodes/ep001_psr_b1257/shots_16x9.py -- <s1|s2|s3|s4> [preview F,..] [final] [save]
Кадры: out/ep001_psr_b1257/16x9/frames/<шот>/; склейка — editkit/assemble.py с edit_16x9.json.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
sys.path.insert(0, HERE)

from mathutils import Vector

from spacekit import camera as CAM
from spacekit import core as C
from spacekit import shot as S
from spacekit import sky as SKY
from spacekit.bodies import neutron_star as NS
from spacekit.bodies import planets as PL
from spacekit.fx import dust_ring as DR

from system import ALPHA, ORBITS, RING, SEEDS, SPIN_HZ, system_planets, system_pulsar

OUT = os.path.join(C.OUT, "ep001_psr_b1257", "16x9")
S.OPT.update(fmt="16x9", fps=30)
SHOTS = {"s1": 300, "s2": 360, "s3": 360, "s4": 300}
RENDER_END = {"s2": 314}  # S2 обрезан на пике вспышки (f314) — склейка встык с S3
sph = CAM.sph


# ---------------------------------------------------------------- S1: общий план, наплыв
def shot_s1():
    n = SHOTS["s1"]
    ex = 0.4
    sc = S.base_scene(n, exposure=ex)
    cam, tgt = CAM.camera_rig("Cam_S1", lens=35)
    CAM.key_camera(cam, tgt, [
        dict(frame=1, loc=sph(190, -100, 13), target=(0, 0, 3), lens=35),
        dict(frame=n, loc=sph(125, -76, 22), target=(0, 0, -3), lens=32),
    ])
    stars = SKY.build_sky(sc, cam, ex, gal=SKY.gal_for_view(-Vector(sph(1, -88, 17)), tilt_deg=-60, l_center_deg=70))
    psr = system_pulsar(sc, n)
    S.report_flash("s1", NS.key_pulse_flash(psr, cam, 1, n))
    system_planets(sc, psr, n, {"draugr": 150, "poltergeist": -20, "phobetor": 115})
    DR.build_dust_ring(sc, parent=psr["root"], ring_radiance=2.0, anisotropy=0.3, frame_start=1, frame_end=n,
                       lights=[psr["light"]] + list(psr["spots"]), **RING)
    S.finish(sc, stars)
    return sc, n


# ---------------------------------------------------------------- S2: нейтронная звезда крупно
def shot_s2():
    n = SHOTS["s2"]
    ex = 0.0
    sc = S.base_scene(n, exposure=ex, samples=96)
    sc.render.motion_blur_shutter = 0.3          # линии поля не размазываются в ленты, лучи всё равно мягкие
    cam, tgt = CAM.camera_rig("Cam_S2", lens=35)
    # продолжение наезда S1 и дуга по широте к широте луча (12°) — в конце луч проходит через камеру
    CAM.key_camera(cam, tgt, [
        dict(frame=1, loc=sph(11.0, -60, 22), target=(0, 0, 0), lens=35),
        dict(frame=180, loc=sph(7.6, -25, 17), target=(0.25, 0, 0.08), lens=35),
        dict(frame=n, loc=sph(5.6, 10, 13), target=(0.5, 0, 0.15), lens=35),
    ])
    stars = SKY.build_sky(sc, cam, ex, gal=SKY.gal_for_view(-Vector(sph(1, -25, 18)), tilt_deg=-35, l_center_deg=120))
    psr = NS.build_pulsar(sc, R=1.0, alpha_deg=ALPHA, spin_hz=SPIN_HZ, frame_start=1, frame_end=n,
                          beam_length=40, beam_half_angle_deg=8, detail="close", field_lines=True,
                          particles=False, surface_strength=2.5, field_strength=2.5)
    S.report_flash("s2", NS.key_pulse_flash(psr, cam, 1, n))
    S.finish(sc, stars)
    return sc, n


# ---------------------------------------------------------------- S3: Полтергейст и сияния
def shot_s3():
    n = SHOTS["s3"]
    ex = 0.8
    sc = S.base_scene(n, exposure=ex, bloom_strength=0.8)
    psr_loc = (55.0, 110.0, 18.0)
    d = Vector(psr_loc).length
    cam, tgt = CAM.camera_rig("Cam_S3", lens=22)
    # медленная дуга к дневной стороне: серп «растёт»
    k1, view = CAM.frame_two_subjects(psr_loc, phase_deg=134, dist=5.8, up_deg=14, w_near=0.55)
    k2, _ = CAM.frame_two_subjects(psr_loc, phase_deg=121, dist=4.7, up_deg=10, w_near=0.50)
    CAM.key_camera(cam, tgt, [dict(frame=1, lens=22, **k1), dict(frame=n, lens=22, **k2)])
    # Фобетор — далёкий серп в верхней части кадра, между планетой и пульсаром
    c1 = Vector(k1["loc"])
    up_s = (Vector((0, 0, 1)) - view * view.z).normalized()
    ph_loc = tuple(c1 + (view * math.cos(math.radians(13)) + up_s * math.sin(math.radians(13))).normalized() * 70.0)
    # полоса Млечного Пути — за ночной стороной: силуэт планеты читается
    stars = SKY.build_sky(sc, cam, ex, gal=SKY.gal_for_view(view, tilt_deg=-18, l_center_deg=15), star_brightness=0.8)
    s2 = (d / 40.0) ** 2
    # ось вращения наклонена к нормали орбит на ~12°: иначе при α=78° луч не задевает планету
    psr = NS.build_pulsar(sc, location=psr_loc, tilt_euler=CAM.tilt_for_target(psr_loc, (0, 0, 0), ALPHA),
                          R=0.3, alpha_deg=ALPHA, spin_hz=SPIN_HZ, frame_start=1, frame_end=n,
                          beam_length=220, beam_half_angle_deg=8, detail="far",
                          light_energy=30000.0 * s2, spot_energy=36000.0 * s2,
                          field_lines=False, particles=False)
    S.report_flash("s3", NS.key_pulse_flash(psr, cam, 1, n, width_deg=16))
    # северный полюс наклонён к камере -> овал сияний виден на ночной стороне, а не только на лимбе
    tilt_az = math.degrees(math.atan2(c1.x, -c1.y))
    pg = PL.build_planet(sc, "poltergeist", radius=1.0, location=(0, 0, 0), detail="close", seed=SEEDS["poltergeist"],
                         axial_tilt_deg=22, tilt_azimuth_deg=tilt_az, rot_period_s=90.0,
                         frame_start=1, frame_end=n, aurora_strength=1.0, light=psr["light"])
    ph = PL.build_planet(sc, "phobetor", radius=0.95, location=ph_loc, detail="far", seed=SEEDS["phobetor"],
                         axial_tilt_deg=10, rot_period_s=60.0, frame_start=1, frame_end=n,
                         aurora_strength=0.6, light=psr["light"])
    for p in (pg, ph):
        PL.key_sun_power(p, psr, 1, n)
    S.finish(sc, stars)
    return sc, n


# ---------------------------------------------------------------- S4: отъезд над системой
def shot_s4():
    n = SHOTS["s4"]
    ex = 0.4
    sc = S.base_scene(n, exposure=ex)
    cam, tgt = CAM.camera_rig("Cam_S4", lens=30)
    # старт: Полтергейст справа-внизу, пульсар слева-вверху (как в конце S3); финал — общий план над системой
    CAM.key_camera(cam, tgt, [
        dict(frame=1, loc=sph(62, 200, 4), target=(-19.3, -13.3, -0.4), lens=30),
        dict(frame=n, loc=sph(235, 240, 26), target=(0, 0, -18), lens=30),
    ])
    stars = SKY.build_sky(sc, cam, ex, gal=SKY.gal_for_view(-Vector(sph(1, 235, 26)), tilt_deg=35, l_center_deg=60))
    psr = system_pulsar(sc, n, beam_intensity=3.2)
    S.report_flash("s4", NS.key_pulse_flash(psr, cam, 1, n))
    system_planets(sc, psr, n, {"draugr": 120, "poltergeist": 212, "phobetor": 15},
                   detail={"poltergeist": "mid"})
    DR.build_dust_ring(sc, parent=psr["root"], ring_radiance=4.0, anisotropy=0.35, arc_gain=4.0,
                       frame_start=1, frame_end=n, lights=[psr["light"]] + list(psr["spots"]), **RING)
    S.finish(sc, stars)
    return sc, n


BUILDERS = {"s1": shot_s1, "s2": shot_s2, "s3": shot_s3, "s4": shot_s4}

if __name__ == "__main__":
    S.run(BUILDERS, out_dir=OUT, render_end=RENDER_END)
