"""Временной шум: |f1 - (f0+f2)/2| по трём соседним кадрам. -- <f0> <f1> <f2> <out_diff.png>"""
import sys, bpy, numpy as np
a = sys.argv[sys.argv.index("--") + 1:]
def load(p):
    im = bpy.data.images.load(p); im.colorspace_settings.name = "Non-Color"
    w, h = im.size; return np.array(im.pixels[:], np.float32).reshape(h, w, 4)[..., :3]
f0, f1, f2 = (load(p) for p in a[:3])
d = np.abs(f1 - 0.5 * (f0 + f2)).mean(axis=2)
lum = f1.mean(axis=2)
for name, m in (("all", np.ones_like(lum, bool)), ("bright>0.2", lum > 0.2), ("mid 0.05-0.2", (lum > 0.05) & (lum <= 0.2))):
    v = d[m]
    print(f"FLICK {name}: n={v.size} mean={v.mean():.4f} p99={np.percentile(v, 99):.4f}" if v.size else f"FLICK {name}: none")
h, w = d.shape
img = bpy.data.images.new("d", w, h, alpha=False); img.colorspace_settings.name = "Non-Color"
o = np.ones((h, w, 4), np.float32); o[..., :3] = np.clip(d * 8.0, 0, 1)[..., None]
img.pixels.foreach_set(o.ravel()); img.filepath_raw = a[3]; img.file_format = "PNG"; img.save()
