"""Вход в Blender из очереди. Диапазон режет рендер, сохраняя полный таймлайн и анимацию шота."""
import os
from pathlib import Path
import runpy
import sys

args = sys.argv[sys.argv.index("--") + 1:]
script, args = args[0], args[1:]
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
sys.path.insert(0, str((root / script).parent))
ranges = [a for a in args if a.startswith("queue_range=")]
called = False
if ranges:
    from spacekit import render
    first, last = map(int, ranges[0].split("=", 1)[1].split("-"))
    original = render.render_sequence

    def sequence(out_dir, frame_start, frame_end, *pos, **kw):
        global called
        if not frame_start <= first <= last <= frame_end:
            raise ValueError(f"Диапазон очереди {first}-{last} вне шота {frame_start}-{frame_end}")
        called = True
        return original(out_dir, first, last, *pos, **kw)

    render.render_sequence = sequence
args = [a for a in args if not a.startswith("queue_range=")]
sys.argv = [str(root / script), "--"] + args
runpy.run_path(str(root / script), run_name="__main__")
if ranges and not called:
    raise RuntimeError("Шот не использовал spacekit.render.render_sequence: диапазон не применён")
