"""Контактный лист: blender -b -P tools/contact.py -- <out.png> <cols> <cell_w> <img1> <img2> ... [--no-label]

Ячейки по строкам слева направо, размер ячейки — cell_w × (cell_w · h/w первого кадра).
Внизу каждой ячейки — подпись: имя файла без расширения (v2_f0230), растровым шрифтом 3×5
(латиница, цифры, _ - .; прочие символы — «?»). --no-label — без подписей (как раньше).
"""
import os
import sys

import bpy
import numpy as np

GLYPHS = {   # 3×5, строки сверху вниз
    "0": "111101101101111", "1": "010110010010111", "2": "111001111100111", "3": "111001111001111",
    "4": "101101111001001", "5": "111100111001111", "6": "111100111101111", "7": "111001001010010",
    "8": "111101111101111", "9": "111101111001111", "a": "010101111101101", "b": "110101110101110",
    "c": "011100100100011", "d": "110101101101110", "e": "111100110100111", "f": "111100110100100",
    "g": "011100101101011", "h": "101101111101101", "i": "111010010010111", "j": "001001001101010",
    "k": "101101110101101", "l": "100100100100111", "m": "101111111101101", "n": "110101101101101",
    "o": "010101101101010", "p": "110101110100100", "q": "010101101110011", "r": "110101110101101",
    "s": "011100010001110", "t": "111010010010010", "u": "101101101101111", "v": "101101101101010",
    "w": "101101111111101", "x": "101101010101101", "y": "101101010010010", "z": "111001010100111",
    "_": "000000000000111", "-": "000000111000000", ".": "000000000000010", "": "000000000000000",
    "?": "111001010000010",
}


def draw_label(cell, text, s):
    """Подпись в нижней полосе ячейки (массив h×w×4, строки снизу вверх как в Blender), масштаб s px."""
    h, w = cell.shape[:2]
    sh = 7 * s
    cell[:sh, :, :3] *= 0.35                        # затемнённая полоса под текстом
    x0 = 2 * s
    for ch in text.lower():
        if x0 + 3 * s > w:
            break
        g = GLYPHS.get(ch, GLYPHS["?"])
        for gy in range(5):
            for gx in range(3):
                if g[gy * 3 + gx] == "1":
                    y = s + (4 - gy) * s
                    cell[y:y + s, x0 + gx * s:x0 + (gx + 1) * s, :3] = 1.0
        x0 += 4 * s


a = sys.argv[sys.argv.index("--") + 1:]
label = "--no-label" not in a
a = [x for x in a if x != "--no-label"]
out, cols, cw, files = a[0], int(a[1]), int(a[2]), a[3:]
_im0 = bpy.data.images.load(files[0]); ch = cw * _im0.size[1] // _im0.size[0]
rows = (len(files) + cols - 1) // cols
scale = max(2, cw // 120)
sheet = np.zeros((rows * ch, cols * cw, 4), np.float32); sheet[..., 3] = 1
for i, f in enumerate(files):
    im = bpy.data.images.load(f); im.colorspace_settings.name = "Non-Color"
    w, h = im.size
    px = np.array(im.pixels[:], np.float32).reshape(h, w, 4)
    ys = (np.arange(ch) * h // ch); xs = (np.arange(cw) * w // cw)
    small = px[ys][:, xs].copy()
    if label:
        draw_label(small, os.path.splitext(os.path.basename(f))[0], scale)
    r, c = divmod(i, cols)
    sheet[(rows - 1 - r) * ch:(rows - r) * ch, c * cw:(c + 1) * cw] = small
img = bpy.data.images.new("sheet", cols * cw, rows * ch, alpha=False)
img.colorspace_settings.name = "Non-Color"
img.pixels.foreach_set(sheet.ravel()); img.filepath_raw = out; img.file_format = "PNG"; img.save()
print("SHEET", out)
