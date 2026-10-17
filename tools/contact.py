"""Контактный лист: blender -b -P tools/contact.py -- <out.png> <cols> <cell_w> <img1> <img2> ..."""
import sys, bpy, numpy as np
a = sys.argv[sys.argv.index("--") + 1:]
out, cols, cw, files = a[0], int(a[1]), int(a[2]), a[3:]
_im0 = bpy.data.images.load(files[0]); ch = cw * _im0.size[1] // _im0.size[0]
rows = (len(files) + cols - 1) // cols
sheet = np.zeros((rows * ch, cols * cw, 4), np.float32); sheet[..., 3] = 1
for i, f in enumerate(files):
    im = bpy.data.images.load(f); im.colorspace_settings.name = "Non-Color"
    w, h = im.size
    px = np.array(im.pixels[:], np.float32).reshape(h, w, 4)
    ys = (np.arange(ch) * h // ch); xs = (np.arange(cw) * w // cw)
    small = px[ys][:, xs]
    r, c = divmod(i, cols)
    sheet[(rows - 1 - r) * ch:(rows - r) * ch, c * cw:(c + 1) * cw] = small
img = bpy.data.images.new("sheet", cols * cw, rows * ch, alpha=False)
img.colorspace_settings.name = "Non-Color"
img.pixels.foreach_set(sheet.ravel()); img.filepath_raw = out; img.file_format = "PNG"; img.save()
print("SHEET", out)
