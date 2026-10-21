"""Эп. 008 — KELT-9b, 1080×1920p60, 3570 кадров / 59.5 с.

v1 0–6: раскалённый газовый гигант, хук. v2 6–17: день→ночь.
v3 17–27: модель H₂→2H. v4 27–37: обратная сборка, перенос энергии.
v5 37–48: почти полярная орбита в номинальном масштабе.
v6 48–59.5: возврат к тепловой фотосфере; f691 совпадает с v1 f1.
Камера/шум в v1/v6 — одна аналитическая траектория с ключами, без драйверов.
Молекулы — явно подписанная схема, не буквальная микросъёмка атмосферы.
CLI: -- vN preview F,.. pct=50 | draft step=6 | final | save.
"""
import math
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
sys.path.insert(0, HERE)

import bpy
from mathutils import Vector
from spacekit import anim
from spacekit import camera as CAM
from spacekit import core as C
from spacekit import shot as S
from spacekit import sky as SKY
from spacekit.bodies import star as ST
from spacekit.bodies import ultrahot as UH
from spacekit.fx import label as LB
import system as SY

EP = "ep008_kelt9b"
OUT = os.path.join(C.OUT, EP, "9x16")
S.OPT.update(fmt="9x16", fps=60)
SHOTS = {"v1": 360, "v2": 660, "v3": 600, "v4": 600, "v5": 660, "v6": 690}


def base(n, exposure=-0.9, samples=28):
    return S.base_scene(n, exposure=exposure, samples=samples, adaptive=0.035,
                        bloom_strength=0.22, look="AgX - Medium High Contrast",
                        comp=dict(vignette=0.08))


def sky(sc, cam, ex):
    direction = Vector((0.25, 1.0, 0.12))
    return SKY.build_sky(sc, cam, ex, mw_strength=0.16, star_brightness=0.55,
                         n_stars=100000, gal=SKY.gal_for_view(direction, tilt_deg=-20, l_center_deg=105))


def planet(name="K9", radius=1.0, location=(0, 0, 0), detail="close", strength=4.0):
    return UH.build_ultrahot(name, radius=radius, location=location, day_k=SY.T_DAY_K,
                            night_k=SY.T_NIGHT_K, seed=SY.SEED, detail=detail, strength=strength)


def finish(sc, stars):
    sc.cycles.max_bounces = 4
    sc.cycles.diffuse_bounces = 1
    sc.cycles.glossy_bounces = 2
    S.finish(sc, stars, denoise="far", star_samples=24)


def hero_camera(t_s):
    return dict(loc=CAM.sph(7.25 - 0.008 * t_s, -48.0 + 0.26 * t_s, 12.0 + 0.03 * t_s),
                target=(0, 0, -0.13), lens=55)


def hero(shot, offset):
    n = SHOTS[shot]
    ex = -0.9
    sc = base(n, ex)
    cam, tgt = CAM.camera_rig("K9_Hero", lens=55)
    fps = C.scene_fps(sc)
    frames = sorted(set([1, n, n + 1] + list(range(1, n + 2, 6))))
    CAM.key_camera(cam, tgt, [dict(frame=f, **hero_camera(offset + (f - 1) / fps))
                              for f in frames], ipo="LINEAR")
    p = planet()
    UH.key_flow(p, [(f, 0.42 + 0.01 * (offset + (f - 1) / fps)) for f in (1, n + 1)])
    stars = sky(sc, cam, ex)
    finish(sc, stars)
    return sc, n


def shot_v1():
    return hero("v1", 0.0)


def shot_v6():
    return hero("v6", -SHOTS["v6"] / 60.0)


def shot_v2():
    n = SHOTS["v2"]
    ex = -0.8
    sc = base(n, ex)
    cam, tgt = CAM.camera_rig("K9_Terminator", lens=58)
    CAM.key_camera(cam, tgt, [
        dict(frame=1, loc=CAM.sph(7.5, -58, 11), target=(0, 0, -0.1), lens=58),
        dict(frame=320, loc=CAM.sph(7.0, -97, 9), target=(0, 0, -0.1)),
        dict(frame=n, loc=CAM.sph(7.4, -143, 7), target=(0, 0, -0.1)),
    ], ipo="LINEAR")
    p = planet()
    UH.key_flow(p, [(1, 0.48), (n, 0.59)])
    stars = sky(sc, cam, ex)
    finish(sc, stars)
    print("EVENT v2 nightside: 328:0.65")
    return sc, n


def emission(name, color, strength=1.0):
    mat, nodes, links, out = C.new_material(name)
    em = nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1)
    em.inputs["Strength"].default_value = strength
    links.new(em.outputs[0], out.inputs["Surface"])
    mat.cycles.emission_sampling = "NONE"
    return mat


def sphere(name, radius, location, mat, segments=32):
    mesh = ST._sphere(name + "_Mesh", segments, segments // 2)
    mesh.materials.append(mat)
    ob = bpy.data.objects.new(name, mesh)
    C.link(ob, "MolecularIllustration")
    ob.location = location
    ob.scale = (radius,) * 3
    ob.visible_shadow = False
    return ob


def curve(name, points, width, mat, coll="Diagrams"):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.resolution_u = 1
    cu.bevel_depth = width
    cu.bevel_resolution = 2
    sp = cu.splines.new("POLY")
    sp.points.add(len(points) - 1)
    for pt, pos in zip(sp.points, points):
        pt.co = (*pos, 1)
    cu.materials.append(mat)
    ob = bpy.data.objects.new(name, cu)
    C.link(ob, coll)
    ob.visible_shadow = False
    return ob


def atom_material(name, color):
    mat, nodes, links, out = C.new_material(name)
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Roughness"].default_value = 0.3
    shader.inputs["Metallic"].default_value = 0.15
    shader.inputs["Emission Color"].default_value = (*color, 1)
    shader.inputs["Emission Strength"].default_value = 0.28
    links.new(shader.outputs[0], out.inputs["Surface"])
    return mat


def diagram_light(name, loc, energy, color, size):
    data = bpy.data.lights.new(name, "AREA")
    data.energy, data.color, data.shape, data.size = energy, color, "DISK", size
    ob = bpy.data.objects.new(name, data)
    C.link(ob, "DiagramLights")
    ob.location = loc
    CAM.point_at(ob, (0, 0, 0.5))


def molecular(shot, recombine=False):
    n = SHOTS[shot]
    ex = -0.55
    sc = base(n, ex, samples=24)
    cam, tgt = CAM.camera_rig("K9_Molecule", lens=50)
    CAM.key_camera(cam, tgt, [
        dict(frame=1, loc=(0.15, -12.7, 2.0), target=(0, 0, 0.5)),
        dict(frame=n, loc=(-0.15, -12.2, 2.05), target=(0, 0, 0.5)),
    ], ipo="LINEAR")
    bg = planet("K9_Background", radius=8.0, location=(0, 10, -6.8), detail="mid", strength=2.0)
    bg["root"].rotation_euler[2] = math.radians(-100 if recombine else -35)
    UH.key_flow(bg, [(1, 0.7), (n, 0.8)])
    diagram_light("MoleculeKey", (-3, -4, 5), 700, (1.0, 0.75, 0.45), 5)
    diagram_light("MoleculeRim", (3, 2, 3), 900, (0.7, 0.8, 1.0), 4)
    mat = atom_material("Hydrogen", (0.95, 0.63, 0.35))
    bond_mat = emission("Bond", (1.0, 0.77, 0.40), 0.75)
    # Центральная пара и небольшие группы в глубине: масштаб условный.
    groups = [(0, 0.0, 0.7, 0.34), (-1.35, 1.8, 1.5, 0.15),
              (1.45, 2.2, 0.1, 0.16), (-1.05, 3.5, -0.65, 0.13), (0.9, 4.2, 1.9, 0.12)]
    for k, (cx, cy, cz, r) in enumerate(groups):
        unbound = 1.18 if k == 0 else 0.55
        split_a, split_b = (unbound, r * 1.45) if recombine else (r * 1.45, unbound)
        atoms = [sphere(f"H_{k}_{side}", r, (cx, cy, cz), mat) for side in (0, 1)]
        for f, s in [(1, split_a), (145, split_a), (355, split_b), (n, split_b)]:
            for side, ob in enumerate(atoms):
                sign = 2 * side - 1
                ob.location = (cx + sign * s, cy, cz + sign * (s - min(split_a, split_b)) * 0.22)
                ob.keyframe_insert("location", frame=f)
        for ob in atoms:
            anim.set_interpolation(ob, "BEZIER")
        bond = curve(f"H2_Bond_{k}", [(-1, 0, 0), (1, 0, 0)], 0.045 if k == 0 else 0.018, bond_mat)
        bond.location = (cx, cy, cz)
        for f, size in ([(1, 0.0001), (290, 0.0001), (355, split_b), (n, split_b)] if recombine else
                        [(1, split_a), (145, split_a), (205, 0.0001), (n, 0.0001)]):
            bond.scale = (size, 1, 1)
            bond.keyframe_insert("scale", frame=f)
        anim.set_interpolation(bond, "BEZIER")
    lab = LB.build_label("ChemicalEquation", "2 H  →  H₂" if recombine else "H₂  →  2 H",
                         location=(0, 0, 2.05), cam=cam, px=52, color=(1, 0.8, 0.54), strength=1.3,
                         font="C:/Windows/Fonts/segoeui.ttf")
    LB.key_screen_size(lab, cam, 1, n, step=6)
    stars = sky(sc, cam, ex)
    finish(sc, stars)
    print(f"EVENT {shot} {'recombination' if recombine else 'dissociation'}: 290:0.75")
    return sc, n


def shot_v3():
    return molecular("v3", False)


def shot_v4():
    return molecular("v4", True)


def shot_v5():
    n = SHOTS["v5"]
    ex = -1.1
    sc = base(n, ex, samples=24)
    cam, tgt = CAM.camera_rig("K9_System", lens=48)
    CAM.key_camera(cam, tgt, [
        dict(frame=1, loc=(10, -30, 7), target=(0, 0, -0.25)),
        dict(frame=n, loc=(8, -29, 6), target=(0, 0, -0.25)),
    ], ipo="LINEAR")
    st = ST.build_star("KELT9", radius=SY.R_STAR, temp_k=SY.T_STAR_K, strength=4.5,
                       seed=809, detail="mid", halo=0.12, halo_scale=1.025, contrast=0.16, gran_scale=70)
    # Сохраняем объём радиуса Borsa; форма Ahlers — иллюстративная добавка.
    q = SY.STAR_FLATTENING
    st["root"].scale = (q ** (-1 / 3), q ** (-1 / 3), q ** (2 / 3))
    ST.key_value(st, "flow", [(1, 0.7), (n, 0.9)], ipo="LINEAR")
    line_mat = emission("K9_OrbitMat", (0.43, 0.68, 1.0), 1.2)
    pts = [SY.orbit_position(SY.PERIODS_S["b"] * k / 256) for k in range(257)]
    curve("NearPolarOrbit", pts, 0.012, line_mat)
    p = planet("K9_Orbiting", radius=SY.R_PLANET, detail="mid", strength=4.0)
    fps = C.scene_fps(sc)
    frames = sorted(set([1, n] + list(range(1, n + 1, 3))))
    for f in frames:
        pos = Vector(SY.orbit_position((f - 1) / fps))
        p["root"].location = pos
        p["root"].rotation_mode = "QUATERNION"
        p["root"].rotation_quaternion = Vector((1, 0, 0)).rotation_difference(-pos.normalized())
        p["root"].keyframe_insert("location", frame=f)
        p["root"].keyframe_insert("rotation_quaternion", frame=f)
    anim.set_interpolation(p["root"], "LINEAR")
    # Большой маркер — отдельное условное обозначение, не увеличенная планета.
    marker = curve("PlanetLocator", [(0.23 * math.cos(t), -0.025, 0.23 * math.sin(t))
                                     for t in [2 * math.pi * k / 64 for k in range(65)]], 0.006, line_mat)
    marker.parent = p["root"]
    marker.rotation_euler = (0, 0, 0)
    axis_mat = emission("SpinAxisMat", (0.57, 0.67, 0.83), 0.55)
    curve("StarSpinAxis", [(0, 0, -2.25), (0, 0, 2.25)], 0.008, axis_mat)
    stars = sky(sc, cam, ex)
    finish(sc, stars)
    print("EVENT v5 orbit_complete: 481:0.55")
    return sc, n


BUILDERS = {"v1": shot_v1, "v2": shot_v2, "v3": shot_v3,
            "v4": shot_v4, "v5": shot_v5, "v6": shot_v6}


def draft(argv):
    """Последовательный черновик в draft/, отдельно от кадров финала."""
    from spacekit import render as R
    step = next((int(a[5:]) for a in argv if a.startswith("step=")), 6)
    argv = [a for a in argv if a != "draft" and not a.startswith("step=")]
    if not any(a.startswith("pct=") for a in argv):
        argv.append("pct=25")
    if not any(a.startswith("samples=") for a in argv):
        argv.append("samples=4")
    S.run(BUILDERS, out_dir=OUT, argv=argv)
    shot = argv[0]
    n = SHOTS[shot]
    folder = os.path.join(OUT, "draft", shot)
    R.render_sequence(folder, 1, n, step=step)
    for f in range(1, n + 1, step):
        source = os.path.join(folder, f"{f:04d}.png")
        for g in range(f + 1, min(f + step, n + 1)):
            dest = os.path.join(folder, f"{g:04d}.png")
            if not os.path.exists(dest):
                shutil.copyfile(source, dest)


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if "draft" in args:
        draft(args)
    else:
        S.run(BUILDERS, out_dir=OUT)
