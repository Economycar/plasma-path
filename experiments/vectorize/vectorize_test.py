"""Experiment 1 (2026-09-21): how cleanly does potrace vectorize the Snoopy line art?

Steps: clean the bitmap (drop frame, watermark, specks) -> potrace -> rasterize the
SVG back at the same resolution -> compare pixel-for-pixel -> write an overlay.

Run from the project root:
    .venv/bin/python experiments/vectorize/vectorize_test.py [image] [results_dir]

Outputs (results_dir, default experiments/vectorize/results):
    01_clean.png        cleaned 1-bit bitmap used as potrace input
    02_trace.svg/.dxf   the vector
    03_rerender.png     the SVG rasterized back (deleted after comparison unless --keep)
    04_overlay.png      black = agreement, blue = ink lost, red = ink added
    05_zoom4x_paw.png   4x render of a detail, to inspect curve smoothness
    metrics.txt         IoU, boundary deviation, segment count, stroke width
"""
import os
import subprocess
import sys

import cairosvg
import cv2
import numpy as np
from svgpathtools import svg2paths

src = sys.argv[1] if len(sys.argv) > 1 else "images/fish.png"
out = sys.argv[2] if len(sys.argv) > 2 else "experiments/vectorize/results"
os.makedirs(out, exist_ok=True)
P = lambda n: os.path.join(out, n)

# ---- 1. clean ------------------------------------------------------------
img = cv2.imread(src, cv2.IMREAD_UNCHANGED)
if img.ndim == 3 and img.shape[2] == 4:
    a = img[:, :, 3:4] / 255.0
    img = (img[:, :, :3] * a + 255 * (1 - a)).astype(np.uint8)
g = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
_, bw = cv2.threshold(g, 128, 255, cv2.THRESH_BINARY_INV)  # ink = 255
n, lab, stats, _ = cv2.connectedComponentsWithStats(bw, 8)
H, W = bw.shape
keep = np.zeros_like(bw)
lines = [f"components: {n - 1}"]
for i in range(1, n):
    x, y, w, h, area = stats[i]
    tag = ""
    if w > 0.8 * W or h > 0.8 * H:
        tag = "FRAME"
    elif y > 0.94 * H:
        tag = "WATERMARK"
    elif area < 30:
        tag = "SPECK"
    lines.append(f"  {i}: bbox=({x},{y},{w},{h}) area={area} {tag}")
    if not tag:
        keep[lab == i] = 255
cv2.imwrite(P("01_clean.png"), 255 - keep)
cv2.imwrite(P("01_clean.pbm"), 255 - keep)

# ---- 2. trace ------------------------------------------------------------
common = ["potrace", P("01_clean.pbm"), "--turdsize", "10", "--alphamax", "1.0", "--opttolerance", "0.2"]
subprocess.run(common + ["-s", "-o", P("02_trace.svg")], check=True)
subprocess.run(common + ["-b", "dxf", "-o", P("02_trace.dxf")], check=True)
os.remove(P("01_clean.pbm"))

# ---- 3. compare ----------------------------------------------------------
svg = open(P("02_trace.svg")).read()
cairosvg.svg2png(bytestring=svg.encode(), write_to=P("03_rerender.png"), output_width=W, output_height=H, background_color="white")
orig = keep > 0
rend = cv2.imread(P("03_rerender.png"), 0) < 128
inter, union = (orig & rend).sum(), (orig | rend).sum()
lines.append(f"ink px original={orig.sum()} traced={rend.sum()} IoU={inter / union:.4f}")
lines.append(f"px only in original={(orig & ~rend).sum()} only in trace={(~orig & rend).sum()}")

def boundary(m):
    m8 = m.astype(np.uint8) * 255
    return (m8 - cv2.erode(m8, np.ones((3, 3), np.uint8))) > 0

dt = cv2.distanceTransform((~boundary(orig)).astype(np.uint8), cv2.DIST_L2, 5)
d = dt[boundary(rend)]
lines.append(f"trace boundary vs original: mean={d.mean():.2f}px 95%={np.percentile(d, 95):.2f}px max={d.max():.2f}px")
ov = np.full((H, W, 3), 255, np.uint8)
ov[orig & ~rend] = (255, 0, 0)
ov[~orig & rend] = (0, 0, 255)
ov[orig & rend] = (0, 0, 0)
cv2.imwrite(P("04_overlay.png"), ov)
cv2.imwrite(P("04_overlay_face.png"), ov[230:650, 520:1020])

paths, _ = svg2paths(P("02_trace.svg"))
lines.append(f"paths={len(paths)} closed subpaths={sum(len(p.continuous_subpaths()) for p in paths)} "
             f"bezier segments={sum(len(p) for p in paths)}")
dtk = cv2.distanceTransform(orig.astype(np.uint8), cv2.DIST_L2, 5)[orig]
lines.append(f"stroke half-width median={np.median(dtk[dtk > 0]):.1f}px -> typical stroke ~{2 * np.percentile(dtk, 90):.0f}px")

# enclosed white regions: these drop out if the ink is cut as slots
white = (~orig).astype(np.uint8)
n2, lab2, st2, _ = cv2.connectedComponentsWithStats(white, 4)
islands = [st2[i] for i in range(1, n2) if not (st2[i][0] == 0 or st2[i][1] == 0 or st2[i][0] + st2[i][2] == W or st2[i][1] + st2[i][3] == H)]
lines.append(f"enclosed white regions: {len(islands)}")

# ---- 4. zoom -------------------------------------------------------------
cairosvg.svg2png(bytestring=svg.encode(), write_to=P("05_zoom4x.png"), output_width=W * 4, output_height=H * 4, background_color="white")
z = cv2.imread(P("05_zoom4x.png"))
cv2.imwrite(P("05_zoom4x_paw.png"), z[3900:4800, 1200:2600])
os.remove(P("05_zoom4x.png"))
if "--keep" not in sys.argv:
    os.remove(P("03_rerender.png"))

open(P("metrics.txt"), "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
