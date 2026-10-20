"""Объёмный выброс сверхновой: гомологичное расширение (v ∝ r), пальцы Рэлея–Тейлора, перемешанные слои элементов.

    from spacekit.fx import explosion as EX
    ex = EX.build_explosion("SN_Ej", radius=1.0, location=(0, 0, 0), seed=5)
    EX.key_radius(ex, lambda f: r0 * (1 + 0.02 * f), 1, n)       # внешний край выброса (мир) по кадрам
    EX.key_value(ex, "heat", [(1, 1.0), (n, 0.3)])               # 1 — огненный шар, 0 — небулярные цвета элементов
    EX.key_value(ex, "glow", [(1, 0.0), (12, 40.0), (n, 8.0)])   # яркость эмиссии
    EX.key_value(ex, "flow", [(1, 0.0), (n, 0.6)], ipo="LINEAR") # течение турбулентности (W шумов)

Расширение — масштаб объекта (выброс сверхновой через сутки расширяется гомологично, v ∝ r: картина
самоподобна), поэтому шейдер работает в координатах объекта: единица = внешний край основного выброса.
Плотность: плотная оболочка (shell…1) + пальцы — край по направлению R_b(d) = 0.8 + fingers·plume(d), plume —
центры ячеек Вороного на сфере направлений (гриб-«пальцы» РТ-неустойчивости), + сгустки внутри (core),
× клочья (fBm) × волокна (гребни шума). Цвет: thermal (heat → 1: бело-голубое ядро → оранжевый → красный край)
и небулярный состав по радиусу (внутри Fe/Ni золотой → Si голубой → Ne фиолетовый → O бирюзовый → He янтарный →
H розово-красный, как полосы разреза bodies.star_layers), перемешанный шумом. Эмиссия + поглощение (absorb —
тёмные пылевые прожилки), без рассеяния: не освещается лампами и не светит на сцену. Цвета элементов — условность
(линии излучения, в описание). `rim` — тонкий сине-фиолетовый край ударной волны.
Цена: 5 шумов на шаг луча; scene.cycles.volume_biased (ray marching) — ставит S.finish; step — шаг луча
(mat.cycles.volume_step_rate).
"""
import bmesh
import bpy

from .. import anim
from .. import core as C
from ..bodies.planets import _NB, _ghost, _seed_off

# радиальный состав выброса (позиция ColorRamp, линейный RGB) — от центра к краю
COMP = [(0.00, (1.00, 0.80, 0.42)),    # Fe/Ni — золото
        (0.24, (0.25, 0.52, 1.00)),    # Si/S — лазурь
        (0.40, (0.58, 0.30, 1.00)),    # Ne/Mg — фиолет
        (0.56, (0.08, 0.86, 0.72)),    # O — бирюза
        (0.72, (1.00, 0.62, 0.12)),    # He — янтарь
        (0.88, (1.00, 0.20, 0.32))]    # H — розово-красный (Hα)
THERMAL = [(0.00, (0.32, 0.02, 0.01)), (0.25, (0.90, 0.16, 0.03)), (0.45, (1.00, 0.45, 0.08)),
           (0.65, (1.00, 0.80, 0.45)), (0.85, (1.00, 0.95, 0.88)), (1.00, (0.78, 0.86, 1.00))]
RIM_RGB = (0.45, 0.42, 1.0)
VALUES = ("heat", "glow", "flow", "absorb", "fingers", "shell", "core", "rim")


def _ramp(b, fac, stops, interp="LINEAR"):
    r = b.node("ShaderNodeValToRGB", {0: fac})
    cr = r.color_ramp
    cr.interpolation = interp
    while len(cr.elements) > 1:
        cr.elements.remove(cr.elements[-1])
    cr.elements[0].position = stops[0][0]
    cr.elements[0].color = (*stops[0][1], 1.0)
    for pos, col in stops[1:]:
        e = cr.elements.new(pos)
        e.color = (*col, 1.0)
    return r.outputs["Color"]


def _value(b, name, v):
    n = b.node("ShaderNodeValue", name=name, label=name)
    n.outputs[0].default_value = v
    return n.outputs[0]


def _material(name, seed, cells, comp, thermal, step, mix_comp):
    mat, N, L, out = C.new_material(name)
    b = _NB(mat.node_tree)
    tc = b.node("ShaderNodeTexCoord")
    p0 = tc.outputs["Object"]
    p = b.v("ADD", p0, _seed_off(seed))
    vals = {k: _value(b, k, v) for k, v in (("heat", 1.0), ("glow", 10.0), ("flow", seed * 0.29), ("absorb", 0.6),
                                             ("fingers", 0.42), ("shell", 0.55), ("core", 0.5), ("rim", 0.0))}
    fw = vals["flow"]
    r = b.v("LENGTH", p0)
    d = b.v("NORMALIZE", p0)
    # крупные клубы: координаты искажены медленным шумом (domain warp)
    w1 = b.noise(p, 1.6, detail=2.0, rough=0.5, w=b.m("MULTIPLY", fw, 0.6)).outputs["Color"]
    pw = b.v("ADD", p, b.v("SCALE", b.v("SUBTRACT", w1, (0.5, 0.5, 0.5)), scale=0.5))
    dd = b.v("ADD", b.v("NORMALIZE", pw), _seed_off(seed, 1))
    # край «цветной капустой»: многомасштабные бугры по направлению + редкие пальцы РТ (ячейки Вороного)
    knob = b.noise(dd, 3.2, detail=6.0, rough=0.62, dist=0.3, w=b.m("MULTIPLY", fw, 0.5)).outputs["Fac"]
    vor = b.node("ShaderNodeTexVoronoi", {"Vector": dd, "Scale": cells, "W": b.m("MULTIPLY", fw, 0.4),
                                          "Randomness": 1.0}, voronoi_dimensions="4D", feature="F1")
    plume = b.m("SUBTRACT", 1.0, b.ss(vor.outputs["Distance"], 0.0, 0.33))
    nf = b.noise(dd, 9.0, detail=3.0, rough=0.55, w=fw).outputs["Fac"]
    kn = b.ss(knob, 0.40, 0.64)
    rb = b.m("ADD", 0.78, b.m("MULTIPLY", vals["fingers"],
                              b.m("ADD", b.m("MULTIPLY", kn, 0.55),
                                  b.m("MULTIPLY", b.m("MULTIPLY", plume, plume), b.m("ADD", 0.3, b.m("MULTIPLY", nf, 0.9))))))
    outer = b.m("SUBTRACT", 1.0, b.node("ShaderNodeMapRange", {0: r, 1: b.m("SUBTRACT", rb, 0.10), 2: rb, 3: 0.0, 4: 1.0},
                                        interpolation_type="SMOOTHSTEP", clamp=True).outputs[0])
    sh = vals["shell"]
    wall = b.node("ShaderNodeMapRange", {0: r, 1: b.m("SUBTRACT", sh, 0.2), 2: b.m("ADD", sh, 0.05), 3: 0.0, 4: 1.0},
                  interpolation_type="SMOOTHSTEP", clamp=True).outputs[0]
    # оболочка рвётся на клубы: плотность — степень искажённого fBm
    bil = b.noise(pw, 4.2, detail=5.0, rough=0.62, dist=0.25, w=b.m("MULTIPLY", fw, 0.5)).outputs["Fac"]
    B = b.ss(bil, 0.44, 0.62)
    shell_d = b.m("MULTIPLY", b.m("MULTIPLY", outer, wall), b.m("ADD", 0.03, b.m("MULTIPLY", b.m("POWER", B, 3.0), 1.8)))
    # внутри — пузыри никеля
    cn = b.noise(pw, 3.5, detail=3.0, rough=0.55, w=b.m("MULTIPLY", fw, 0.7)).outputs["Fac"]
    core_d = b.m("MULTIPLY", b.m("MULTIPLY", b.m("SUBTRACT", 1.0, wall), vals["core"]),
                 b.m("ADD", 0.4, b.m("MULTIPLY", b.ss(cn, 0.42, 0.75), 0.8)))
    core_d = b.m("MULTIPLY", core_d, b.m("SUBTRACT", 1.0, b.ss(r, 0.7, 0.95)))
    # тонкие волокна (гребни мелкого шума)
    fn = b.noise(pw, 9.0, detail=3.0, rough=0.55, w=b.m("MULTIPLY", fw, 1.3)).outputs["Fac"]
    ridge = b.m("SUBTRACT", 1.0, b.m("ABSOLUTE", b.m("SUBTRACT", b.m("MULTIPLY", fn, 2.0), 1.0)))
    fil = b.m("ADD", 0.6, b.m("MULTIPLY", b.m("POWER", ridge, 4.0), 1.0))
    rho = b.m("MULTIPLY", b.m("ADD", shell_d, core_d), fil)
    # температура: горячее ядро светит сквозь трещины холодной корки; яркость ∝ T³ (контраст огня)
    heat = vals["heat"]
    hb = b.ss(b.noise(pw, 5.0, detail=4.0, rough=0.6, w=b.m("MULTIPLY", fw, 0.9)).outputs["Fac"], 0.35, 0.75)
    t_sh = b.m("ADD", 0.30, b.m("MULTIPLY", b.m("POWER", hb, 1.5), 0.78))
    T = b.m("MULTIPLY", heat, b.mix_f(wall, 1.3, t_sh) if hasattr(b, "mix_f") else
            b.m("ADD", b.m("MULTIPLY", wall, t_sh), b.m("MULTIPLY", b.m("SUBTRACT", 1.0, wall), 1.12)))
    tcol = _ramp(b, b.m("MULTIPLY", T, 0.85, clamp=True), thermal)
    nc = b.noise(p, 2.3, detail=3.0, rough=0.55, w=b.m("MULTIPLY", fw, 0.5)).outputs["Fac"]
    ci = b.m("ADD", b.m("MULTIPLY", b.m("DIVIDE", r, rb), 0.92),
             b.m("MULTIPLY", b.m("SUBTRACT", nc, 0.5), mix_comp), clamp=True)
    ccol = _ramp(b, ci, comp, interp="EASE")
    hw = b.ss(heat, 0.2, 0.75)
    col = b.mix(hw, ccol, tcol)
    lum = b.m("ADD", b.m("MULTIPLY", b.m("POWER", b.m("MAXIMUM", T, 0.0), 3.0), 2.5),
              b.m("MULTIPLY", b.m("SUBTRACT", 1.0, hw), b.m("ADD", 0.35, b.m("MULTIPLY", hb, 0.5))))
    es = b.m("MULTIPLY", b.m("MULTIPLY", rho, vals["glow"]), lum)
    # край ударной волны
    rim_x = b.m("DIVIDE", b.m("SUBTRACT", r, b.m("ADD", rb, 0.03)), 0.035)
    rim = b.m("MULTIPLY", b.m("EXPONENT", b.m("MULTIPLY", b.m("MULTIPLY", rim_x, rim_x), -1.0)),
              b.m("MULTIPLY", vals["rim"], b.m("ADD", 0.3, nf)))
    em1 = b.node("ShaderNodeEmission", {"Color": col, "Strength": es})
    em2 = b.node("ShaderNodeEmission", {"Color": (*RIM_RGB, 1.0), "Strength": rim})
    ab = b.node("ShaderNodeVolumeAbsorption", {"Color": (0.70, 0.62, 0.55, 1.0),
                                               "Density": b.m("MULTIPLY", rho, vals["absorb"])})
    a1 = b.node("ShaderNodeAddShader", {0: em1.outputs[0], 1: em2.outputs[0]})
    a2 = b.node("ShaderNodeAddShader", {0: a1.outputs[0], 1: ab.outputs[0]})
    L.new(a2.outputs[0], out.inputs["Volume"])
    mc = mat.cycles
    for k, v in (("volume_sampling", "DISTANCE"), ("volume_interpolation", "LINEAR"), ("volume_step_rate", step)):
        try:
            setattr(mc, k, v)
        except (AttributeError, TypeError):
            pass
    return mat


def _icosphere(name, r, subdiv=3):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=r)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me


def build_explosion(name, radius=1.0, location=(0, 0, 0), parent=None, seed=1, cells=7.0, stretch=(1, 1, 1),
                    fingers_max=0.5, comp=COMP, thermal=THERMAL, mix_comp=0.45, step=1.0, coll="FX", **values):
    """Объём выброса: сфера-домен радиуса 1 + fingers_max (в ед. объекта), объект масштабирован на radius·stretch
    (stretch — вытянутый выброс, «замочная скважина»). values — начальные значения VALUES (heat=…, glow=…).
    Возвращает dict(ob, mat, stretch)."""
    me = _icosphere(f"{name}_Dom", 1.0 + fingers_max + 0.05)
    mat = _material(f"{name}_Mat", seed, cells, comp, thermal, step, mix_comp)
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    C.link(ob, coll)
    ob.location = location
    if parent is not None:
        ob.parent = parent
    ob.scale = tuple(radius * s for s in stretch)
    _ghost(ob)
    ex = dict(ob=ob, mat=mat, stretch=tuple(stretch))
    for k, v in values.items():
        set_value(ex, k, v)
    return ex


def set_value(ex, name, v):
    ex["mat"].node_tree.nodes[name].outputs[0].default_value = v


def key_value(ex, name, pairs, ipo="BEZIER"):
    """Ключи узла name (VALUES): pairs [(кадр, значение)]."""
    s = ex["mat"].node_tree.nodes[name].outputs[0]
    for f, v in pairs:
        s.default_value = v
        s.keyframe_insert("default_value", frame=f)
    anim.set_interpolation(ex["mat"].node_tree, ipo, path_contains=f'nodes["{name}"]')


def key_radius(ex, r_of_frame, frame_start, frame_end, step=1):
    """Ключи масштаба: внешний край основного выброса = r_of_frame(f) (мировые ед. родителя)."""
    ob, st = ex["ob"], ex["stretch"]
    for f in list(range(frame_start, frame_end + 1, step)) + [frame_end]:
        r = r_of_frame(f)
        ob.scale = tuple(r * s for s in st)
        ob.keyframe_insert("scale", frame=f)
    anim.set_interpolation(ob, "LINEAR", path_contains="scale")
