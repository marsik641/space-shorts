"""Только 16 кадров для согласования; финальный рендер/MP4 не запускает.

Blender -b --factory-startup -P <этот файл> -- raw v2
Blender -b --factory-startup -P <этот файл> -- layout
"""
import json
import os
from pathlib import Path
import sys

import bpy

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))
import shots_9x16 as SH
from spacekit import render as R

OUT = REPO / 'out' / HERE.name / '9x16' / 'storyboard3'
SELECTION = {'v1': [1, 150, 300], 'v2': [1, 180, 360],
             'v3': [35, 140, 420], 'v4': [1, 210, 420],
             'v5': [70, 420], 'v6': [80, 480]}


def manifest():
    items, offset = [], 0
    for shot, frames in SELECTION.items():
        for f in frames:
            timeline = offset + f
            items.append(dict(index=len(items)+1, shot=shot, frame=f,
                              timeline_frame=timeline, seconds=(timeline-1)/60,
                              raw=str(OUT / 'raw' / f'{shot}_f{f:04d}.png')))
        offset += min(SH.SHOTS[shot], 480) if shot == 'v6' else SH.SHOTS[shot]
    assert len(items) == 16
    return items


def raw(shot):
    SH.S.OPT['pct'] = 100
    sc, _ = SH.BUILDERS[shot]()
    sc.render.use_persistent_data = True
    (OUT / 'raw').mkdir(parents=True, exist_ok=True)
    for f in SELECTION[shot]:
        R.render_still(str(OUT / 'raw' / f'{shot}_f{f:04d}.png'), frame=f)


def layout():
    items = manifest()
    flat, frames = OUT / 'flat', OUT / 'frames'
    flat.mkdir(parents=True, exist_ok=True)
    frames.mkdir(parents=True, exist_ok=True)
    for it in items:
        src = Path(it['raw'])
        if not src.is_file() or src.stat().st_size == 0:
            raise RuntimeError(f'Нет исходного кадра: {src}')
        dst = flat / f"{it['index']:04d}.png"
        if dst.exists():
            dst.unlink()
        os.link(src, dst)
    cfg = json.loads((HERE / 'edit_9x16_en.json').read_text(encoding='utf-8'))
    cfg['shots'] = [dict(dir=str(flat), first=it['index'], frames=1, xfade_in=0)
                    for it in items]
    cfg['audio'] = []
    cfg['output'] = str(OUT / 'unused.mp4')
    source_path = REPO / 'editkit' / 'assemble.py'
    source = source_path.read_text(encoding='utf-8')
    animation_call = '    bpy.ops.render.render(animation=True)'
    if source.count(animation_call) != 1:
        raise RuntimeError('assemble.py изменился: нужно проверить безопасную сборку stills')
    source = source.replace(animation_call, '    pass # Только 16 stills, без MP4')
    source = source.replace('print("ASSEMBLED", out, "frames", end, "seconds", round(end / fps, 2))',
                            'print("STILLS LAYOUT PREPARED")')
    ns = {'__name__': 'storyboard_assemble', '__file__': str(source_path)}
    exec(compile(source, str(source_path), 'exec'), ns)
    ns['main'](cfg)
    sc = bpy.context.scene
    for it in items:
        sc.sequence_editor.strips[f"shot{it['index']}"].frame_start = it['timeline_frame']
    sc.frame_end = 2520
    sc.render.image_settings.media_type = 'IMAGE'
    sc.render.image_settings.file_format = 'PNG'
    for it in items:
        out = frames / f"{it['index']:02d}_{it['seconds']:05.2f}s_{it['shot']}.png"
        sc.frame_set(it['timeline_frame'])
        sc.render.filepath = str(out)
        bpy.ops.render.render(write_still=True)
        it['image'] = str(out)
    (OUT / 'manifest.json').write_text(json.dumps(items, indent=2), encoding='utf-8')
    print('STORYBOARD 16 frames; no final render, no MP4', flush=True)


if __name__ == '__main__':
    args = sys.argv[sys.argv.index('--')+1:]
    if args[0] == 'raw':
        raw(args[1])
    elif args[0] == 'layout':
        layout()
    else:
        raise ValueError('raw <shot> | layout')
