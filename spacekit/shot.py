"""Обвязка шотов эпизода: базовая сцена, финализация, единый CLI.

Скрипт эпизода объявляет функции-шоты (каждая возвращает (scene, n_frames)) и вызывает run():

    BUILDERS = {"s1": shot_s1, ...}
    if __name__ == "__main__":
        shot.run(BUILDERS, out_dir=<папка вывода эпизода>, render_end={"s2": 314})

CLI (после `--`):  <шот> [preview F1,F2,...] [pct=50] [samples=N] [outdir=DIR] [final] [save]
    preview — превью-кадры (pct=50 по умолчанию; звёзды строятся под итоговый pct)
    final   — PNG-секвенция в <out_dir>/frames/<шот>/####.png с докачкой
    save    — .blend в <out_dir>/scenes/<шот>.blend (открыть руками в Blender)
"""
import os
import sys

import bpy

from . import core as C
from . import render as R
from . import sky as SKY

# Параметры запуска: заполняются в run() до сборки (звёзды строятся под итоговый процент/формат)
OPT = {"pct": 100, "samples": 64, "fmt": "16x9", "fps": 30}


def base_scene(frames, exposure=0.0, samples=None, bloom_strength=0.6, fmt=None, fps=None, adaptive=0.02,
               white_balance=None, look="None", comp=None):
    """Чистая сцена: Cycles/OptiX, формат кадра и fps из OPT (или явно), AgX (+ look, баланс белого, К), компоузер
    с блумом (comp — доп. параметры render.setup_compositor: streaks, vignette, fog_strength, …)."""
    fps = fps or OPT["fps"]
    sc = C.reset_scene(fps=fps)
    R.setup_cycles(sc, samples=samples or OPT["samples"], pct=OPT["pct"],
                   res=R.FORMATS[fmt or OPT["fmt"]], fps=fps, adaptive_threshold=adaptive)
    R.setup_color(sc, exposure=exposure, white_balance=white_balance, look=look)
    kw = dict(dispersion=SKY.STAR_SAFE_DISPERSION, bloom_strength=bloom_strength)
    kw.update(comp or {})
    R.setup_compositor(sc, **kw)
    sc.frame_start, sc.frame_end = 1, frames
    return sc


def finish(sc, stars, denoise="close", star_samples=64, transparent_bounces=24):
    """После создания всех объектов: отдельный слой звёзд (без денойза), денойз основного слоя, лимиты."""
    R.setup_star_layer(sc, stars, samples=star_samples)
    R.setup_volume_denoise(sc, denoise)
    sc.cycles.volume_biased = True
    sc.cycles.transparent_max_bounces = max(sc.cycles.transparent_max_bounces, transparent_bounces)


def report_flash(shot, peaks):
    """Печать пиков вспышек пульсара — по ним ставят склейки «на вспышке»."""
    print(f"FLASH {shot}: " + ", ".join(f"{f}:{v:.2f}" for f, v in peaks))


def frames_s(seconds, scene=None):
    """Секунды ролика -> число кадров при fps сцены (вызывать после base_scene)."""
    return int(round(seconds * C.scene_fps(scene)))


def run(builders, out_dir, render_end=None, argv=None):
    argv = argv if argv is not None else (sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    render_end = render_end or {}
    shot = argv[0]
    for a in argv:
        if a.startswith("pct="):
            OPT["pct"] = int(a[4:])
        if a.startswith("samples="):
            OPT["samples"] = int(a[8:])
    if "preview" in argv and not any(a.startswith("pct=") for a in argv):
        OPT["pct"] = 50
    sc, n = builders[shot]()
    if any(a.startswith("samples=") for a in argv):
        sc.cycles.samples = OPT["samples"]
    if "save" in argv:
        os.makedirs(os.path.join(out_dir, "scenes"), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, "scenes", f"{shot}.blend"))
    if "preview" in argv:
        frames = [int(f) for f in argv[argv.index("preview") + 1].split(",")]
        out = next((a[7:] for a in argv if a.startswith("outdir=")), os.path.join(out_dir, "previews"))
        os.makedirs(out, exist_ok=True)
        for f in frames:
            R.render_still(os.path.join(out, f"{shot}_f{f:04d}.png"), frame=f)
    if "final" in argv:
        R.render_sequence(os.path.join(out_dir, "frames", shot), 1, render_end.get(shot, n))
