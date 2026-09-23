#!/usr/bin/env python3
"""Plasma Path: image -> cleaned bitmap -> cut design -> Mach3 G-code.

Pure Python on numpy, scipy and Pillow, plus the vendored pure-Python potrace
port in ./vendor.  Nothing needs to be installed.

Stages (each one reads and updates <job>/state.json):

  pp.py clean  IMAGE --job DIR [clean options]
  pp.py design --job DIR --mode silhouette|lineart|stencil (--width W | --height H) [design options]
  pp.py gcode  --job DIR [g-code options]
  pp.py show   --job DIR

Every stage prints a short human summary followed by a JSON block, and writes
a preview PNG you should look at before asking the next question.

Geometry policy: all design work happens in raster space (a bitmap at a fixed
number of pixels per inch), so unions, kerf offsets and bridges are plain
morphology.  Vectors appear only at the very end, when the kerf-offset bitmap
is traced once and turned into G-code.  The post is XY only (Langmuir
CrossFire on Mach3, no Z axis, torch height set by hand): M3/M5 for the
torch, G4 for the pierce dwell, G0 rapids, G1 cuts.
"""
from __future__ import annotations

__version__ = "1.2.0"   # keep in step with SKILL.md metadata.version and CHANGELOG.md

import argparse
import json
import math
import os
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import potrace  # noqa: E402  (vendored pure-Python port)

MAX_SRC_PX = 2400        # long side of the cleaned bitmap
MAX_DESIGN_PX = 2000     # long side of the design bitmap
PPU_TARGET = {"in": 200.0, "mm": 8.0}
BED = {"in": (24.0, 24.0), "mm": (609.6, 609.6)}
LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # no I or O, they look like 1 and 0


# --------------------------------------------------------------------------
# state
# --------------------------------------------------------------------------

def load_state(job):
    p = os.path.join(job, "state.json")
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return {}


def save_state(job, st):
    os.makedirs(job, exist_ok=True)
    with open(os.path.join(job, "state.json"), "w") as f:
        json.dump(st, f, indent=2)


def out(job, name):
    return os.path.join(job, name)


def emit(summary_lines, data):
    for line in summary_lines:
        print(line)
    print("JSON " + json.dumps(data))


def fail(msg):
    print("ERROR " + msg)
    sys.exit(2)


# --------------------------------------------------------------------------
# small raster helpers
# --------------------------------------------------------------------------

def disk(r):
    r = int(math.ceil(r))
    if r <= 0:
        return np.ones((1, 1), bool)
    y, x = np.ogrid[-r:r + 1, -r:r + 1]
    return (x * x + y * y) <= r * r


def dilate(mask, r):
    """Grow by r pixels (Euclidean), via a distance transform of the outside."""
    if r <= 0:
        return mask.copy()
    d = ndi.distance_transform_edt(~mask)
    return mask | (d <= r)


def erode(mask, r):
    if r <= 0:
        return mask.copy()
    d = ndi.distance_transform_edt(mask)
    return d > r


def opening(mask, r):
    return dilate(erode(mask, r), r)


def label(mask):
    lab, n = ndi.label(mask, structure=np.ones((3, 3), int))
    return lab, n


def holes_of(mask):
    """Enclosed empty regions of a material mask."""
    return ndi.binary_fill_holes(mask) & ~mask


def otsu(gray):
    hist = np.bincount(gray.ravel(), minlength=256).astype(float)
    total = hist.sum()
    sum_all = (np.arange(256) * hist).sum()
    w_b = 0.0
    sum_b = 0.0
    best, thr = -1.0, 128
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b = sum_b / w_b
        m_f = (sum_all - sum_b) / w_f
        v = w_b * w_f * (m_b - m_f) ** 2
        if v > best:
            best, thr = v, t
    return thr


def font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        for cand in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                     "/usr/share/fonts/liberation/LiberationSans-Bold.ttf",
                     "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"):
            if os.path.exists(cand):
                return ImageFont.truetype(cand, size)
        return ImageFont.load_default()


def fit_preview(img, max_w=1400):
    if img.width > max_w:
        s = max_w / img.width
        img = img.resize((max_w, int(img.height * s)), Image.LANCZOS)
    return img


def draw_grid(img, ox=0):
    """Faint 10 x 10 grid with 0.1 labels, so a spot can be named as fractions (x, y) of the image."""
    d = ImageDraw.Draw(img)
    W, H = img.width - ox, img.height
    fs = font(max(9, int(W / 90)))
    for k in range(1, 10):
        x = ox + W * k / 10
        y = H * k / 10
        d.line([(x, 0), (x, H)], fill=(215, 215, 235), width=1)
        d.line([(ox, y), (ox + W, y)], fill=(215, 215, 235), width=1)
        d.text((x + 2, 2), f"{k / 10:.1f}", fill=(120, 120, 160), font=fs)
        d.text((ox + 2, y + 2), f"{k / 10:.1f}", fill=(120, 120, 160), font=fs)
    return img


def badge(draw, xy, text, fill, fnt, outline=(0, 0, 0)):
    x, y = xy
    w = draw.textlength(text, font=fnt)
    h = fnt.size if hasattr(fnt, "size") else 12
    pad = 4
    draw.rounded_rectangle([x - w / 2 - pad, y - h / 2 - pad, x + w / 2 + pad, y + h / 2 + pad],
                           radius=4, fill=fill, outline=outline)
    draw.text((x - w / 2, y - h / 2 - 1), text, fill=(255, 255, 255), font=fnt)


# --------------------------------------------------------------------------
# 1. clean
# --------------------------------------------------------------------------

def load_rgb(path):
    im = Image.open(path)
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        bg.alpha_composite(im)
        im = bg.convert("RGB")
    else:
        im = im.convert("RGB")
    if max(im.size) > MAX_SRC_PX:
        s = MAX_SRC_PX / max(im.size)
        im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
    return np.array(im)


def parse_color(spec):
    spec = spec.strip().lower()
    names = {"red": (220, 40, 40), "green": (40, 160, 60), "blue": (40, 80, 220), "yellow": (240, 220, 40),
             "orange": (240, 140, 30), "purple": (140, 60, 180), "pink": (240, 120, 180), "cyan": (40, 200, 220),
             "brown": (130, 80, 40), "black": (0, 0, 0), "white": (255, 255, 255), "gray": (128, 128, 128), "grey": (128, 128, 128)}
    if spec in names:
        return names[spec]
    if spec.startswith("#") and len(spec) == 7:
        return tuple(int(spec[i:i + 2], 16) for i in (1, 3, 5))
    parts = [int(float(v)) for v in spec.split(",")]
    if len(parts) == 3:
        return tuple(parts)
    raise ValueError("colour must be a name, #rrggbb or r,g,b")


def color_mask(rgb, spec, tol):
    """Pixels within `tol` of the colour, measured mostly by hue so shading does not matter."""
    target = np.array(parse_color(spec), float)
    px = rgb.astype(float)
    if spec.strip().lower() in ("black", "white", "gray", "grey") or abs(target.max() - target.min()) < 30:
        return np.sqrt(((px - target) ** 2).sum(axis=2)) < tol
    # chroma-normalised comparison: compare direction of the colour vector
    n_px = px / (np.linalg.norm(px, axis=2, keepdims=True) + 1e-6)
    n_t = target / (np.linalg.norm(target) + 1e-6)
    ang = np.degrees(np.arccos(np.clip((n_px * n_t).sum(axis=2), -1, 1)))
    sat = px.max(axis=2) - px.min(axis=2)
    return (ang < tol / 4) & (sat > 40)


def load_gray(path):
    im = Image.open(path)
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        bg.alpha_composite(im)
        im = bg.convert("L")
    else:
        im = im.convert("L")
    if max(im.size) > MAX_SRC_PX:
        s = MAX_SRC_PX / max(im.size)
        im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
    return np.array(im)


def cmd_clean(a):
    job = a.job
    os.makedirs(job, exist_ok=True)
    gray = load_gray(a.image)
    rgb = load_rgb(a.image) if (a.color_keep or a.color_drop) else None
    if rgb is not None and a.color_drop:
        gray = np.where(color_mask(rgb, a.color_drop, a.color_tol), 255, gray).astype(np.uint8)
    if a.rotate:
        if rgb is not None:
            rgb = np.array(Image.fromarray(rgb).rotate(a.rotate, resample=Image.BILINEAR, expand=True, fillcolor=(255, 255, 255)))
        # straighten a tilted scan; fill the corners with the paper's edge brightness
        fill = int(np.median(np.concatenate([gray[0], gray[-1], gray[:, 0], gray[:, -1]])))
        gray = np.array(Image.fromarray(gray).rotate(a.rotate, resample=Image.BILINEAR, expand=True, fillcolor=fill))
    H, W = gray.shape
    g = gray.astype(float)

    crop = None
    if a.crop:
        x0, y0, x1, y1 = [float(v) for v in a.crop.split(",")]
        crop = (int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H))

    if a.blur and a.blur > 0:
        g = ndi.gaussian_filter(g, a.blur)

    # ---- threshold (or colour pick)
    if rgb is not None and a.color_keep:
        dark = color_mask(rgb, a.color_keep, a.color_tol)
        thr_used = f"colour {a.color_keep} (tolerance {a.color_tol:g})"
        if a.invert == "auto":
            a.invert = "off"
    elif a.adaptive and a.adaptive > 0:
        win = int(a.adaptive) | 1
        local = ndi.uniform_filter(g, win)
        dark = g < (local - a.offset)
        thr_used = f"adaptive(window {win}, offset {a.offset:g})"
    else:
        thr = otsu(gray) if a.threshold == "auto" else int(float(a.threshold))
        dark = g < thr
        thr_used = str(thr)

    # ---- polarity: ink is normally the dark minority
    invert = a.invert
    dark_frac = float(dark.mean())
    if invert == "auto":
        invert = "on" if dark_frac > 0.5 else "off"
    ink = ~dark if invert == "on" else dark

    if crop:
        m = np.zeros_like(ink)
        m[crop[1]:crop[3], crop[0]:crop[2]] = True
        ink &= m

    # ---- morphology
    if a.close and a.close > 0:
        ink = ndi.binary_closing(ink, structure=disk(a.close))
    if a.open and a.open > 0:
        ink = ndi.binary_opening(ink, structure=disk(a.open))

    # ---- component filter
    lab, n = label(ink)
    removed = []
    keep = np.zeros_like(ink)
    if n:
        objs = ndi.find_objects(lab)
        areas = ndi.sum(ink, lab, index=np.arange(1, n + 1))
        order = np.argsort(-areas)
        rank = {int(i) + 1: r for r, i in enumerate(order)}
        for i in range(1, n + 1):
            sl = objs[i - 1]
            y, x = sl[0].start, sl[1].start
            h, w = sl[0].stop - y, sl[1].stop - x
            area = int(areas[i - 1])
            tag = None
            if a.frame == "on" and (w > 0.8 * W or h > 0.8 * H) and area < 0.1 * W * H:
                tag = "frame"
            elif a.bottom > 0 and y > (1 - a.bottom) * H:
                tag = "bottom band"
            elif a.top > 0 and y + h < a.top * H:
                tag = "top band"
            elif area < a.speck:
                tag = "speck"
            elif a.keep_largest and rank[i] >= a.keep_largest:
                tag = "not among largest"
            if tag:
                removed.append({"bbox": [int(x), int(y), int(w), int(h)], "area": area, "reason": tag})
            else:
                keep[lab == i] = True
    ink = keep
    # ---- numbered marks: let the person point at one ("drop mark 3")
    lab, n = label(ink)
    marks = []
    if n:
        areas = ndi.sum(ink, lab, index=np.arange(1, n + 1))
        cents = ndi.center_of_mass(ink, lab, index=np.arange(1, n + 1))
        order = np.argsort(-areas)
        drop = {m.upper().lstrip("M") for m in (a.drop_mark or [])}
        keep_only = {m.upper().lstrip("M") for m in (a.keep_mark or [])}
        for r, i in enumerate(order):
            num = str(r + 1)
            gone = (num in drop) or (keep_only and num not in keep_only)
            marks.append({"label": f"M{num}", "area": int(areas[i]), "centroid": [float(cents[i][1]), float(cents[i][0])],
                          "dropped": bool(gone)})
            if gone:
                ink &= ~(lab == i + 1)
                removed.append({"bbox": None, "area": int(areas[i]), "reason": "picked"})
    # white specks inside ink (scanner grain, JPEG noise) would become slivers of metal later
    hmask = holes_of(ink)
    lab_h, n_h = label(hmask)
    filled_specks = 0
    if n_h:
        h_areas = ndi.sum(hmask, lab_h, index=np.arange(1, n_h + 1))
        small = np.nonzero(h_areas < a.speck)[0] + 1
        if len(small):
            ink |= np.isin(lab_h, small)
            filled_specks = int(len(small))
    lab, n_kept = label(ink)

    Image.fromarray(np.where(ink, 0, 255).astype(np.uint8)).save(out(job, "clean.png"))

    # ---- preview: original with removals boxed | cleaned
    left = Image.fromarray(rgb) if rgb is not None else Image.fromarray(gray).convert("RGB")
    d = ImageDraw.Draw(left)
    for r in removed:
        if not r["bbox"]:
            continue
        x, y, w, h = r["bbox"]
        d.rectangle([x, y, x + w, y + h], outline=(220, 40, 40), width=max(2, W // 400))
    if crop:
        d.rectangle(crop, outline=(40, 120, 220), width=max(2, W // 300))
    right = Image.fromarray(np.where(ink, 0, 255).astype(np.uint8)).convert("RGB")
    draw_grid(right)
    if 1 < len(marks) <= 60:
        dr = ImageDraw.Draw(right)
        fm = font(max(11, int(W / 55)))
        for m in marks:
            badge(dr, tuple(m["centroid"]), m["label"], (120, 120, 120) if m["dropped"] else (40, 80, 200), fm)
    gap = 16
    pv = Image.new("RGB", (W * 2 + gap, H), (200, 200, 200))
    pv.paste(left, (0, 0))
    pv.paste(right, (W + gap, 0))
    pv = fit_preview(pv, 1600)
    pv.save(out(job, "clean_preview.png"))

    by_reason = {}
    for r in removed:
        by_reason[r["reason"]] = by_reason.get(r["reason"], 0) + 1
    ink_frac = float(ink.mean())
    levels = int(len(np.unique(gray[::4, ::4])))
    notes = []
    if a.invert == "auto" and invert == "on":
        notes.append("Image looked light-on-dark, so it was inverted. Pass --invert off if that is wrong.")
    if levels > 200 and not a.adaptive:
        notes.append("Many gray levels: this may be a photo or scan. If the result is patchy, try --adaptive 51 --blur 1, or --keep-largest N.")
    if n_kept > 60:
        notes.append(f"{n_kept} separate marks kept. Raise --speck or use --keep-largest if most are noise.")
    if n_kept == 0:
        notes.append("Nothing kept. Try --invert on, a different --threshold, or --frame off.")

    st = load_state(job)
    st["source"] = os.path.abspath(a.image)
    st["image"] = {"w": W, "h": H}
    st["clean"] = {
        "threshold": thr_used, "invert": invert, "speck": a.speck, "blur": a.blur,
        "adaptive": a.adaptive, "offset": a.offset, "open": a.open, "close": a.close,
        "frame": a.frame, "top": a.top, "bottom": a.bottom, "crop": a.crop, "rotate": a.rotate,
        "keep_largest": a.keep_largest, "color_keep": a.color_keep, "color_drop": a.color_drop,
        "color_tol": a.color_tol, "drop_mark": a.drop_mark, "keep_mark": a.keep_mark,
        "result": {"marks": int(n_kept), "removed": by_reason, "ink_fraction": round(ink_frac, 4),
                   "gray_levels": levels,
                   "mark_labels": [{"label": m["label"], "area": m["area"], "dropped": m["dropped"]} for m in marks[:60]]},
    }
    st.pop("design", None)
    st.pop("gcode", None)
    save_state(job, st)

    emit([
        f"clean: {W}x{H} px, threshold {thr_used}, invert {invert}",
        f"kept {n_kept} marks, removed {sum(by_reason.values())} ({', '.join(f'{v} {k}' for k, v in by_reason.items()) or 'none'})"
        + (f", filled {filled_specks} white speck(s) inside lines" if filled_specks else ""),
        f"preview: {out(job, 'clean_preview.png')}  (left: original with removed parts boxed in red; right: what will be used"
        + (", marks numbered M1.. largest first; --drop-mark 3 removes one)" if 1 < len(marks) <= 60 else ")"),
        *notes,
    ], {"stage": "clean", "marks": n_kept, "removed": by_reason, "ink_fraction": ink_frac,
        "notes": notes, "preview": out(job, "clean_preview.png")})


# --------------------------------------------------------------------------
# 2. design
# --------------------------------------------------------------------------

def art_bbox(mask):
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def design_raster(ink_full, bbox, ppu, units, width, height):
    """Resample the cleaned ink so the art measures width x height at ppu px/unit.

    Returns (ink, ppu) where ink is the design bitmap with a 1-unit-ish margin
    of empty pixels, plus the transform from clean-px to design-px.
    """
    x0, y0, x1, y1 = bbox
    art = ink_full[y0:y1, x0:x1]
    aw, ah = x1 - x0, y1 - y0
    if width is None:
        width = height * aw / ah
    if height is None:
        height = width * ah / aw
    long_units = max(width, height)
    ppu = min(ppu, MAX_DESIGN_PX / long_units)
    tw, th = max(2, int(round(width * ppu))), max(2, int(round(height * ppu)))
    im = Image.fromarray((art * 255).astype(np.uint8)).resize((tw, th), Image.BILINEAR)
    ink = np.array(im) >= 128
    pad = int(math.ceil(ppu * (1.0 if units == "in" else 25.4)))  # room for stencil plate and bridges
    ink = np.pad(ink, pad, constant_values=False)
    sx, sy = tw / aw, th / ah
    xf = {"x0": x0, "y0": y0, "sx": sx, "sy": sy, "pad": pad}
    return ink, ppu, width, height, xf


def base_material(ink, mode, plate_margin_px):
    if mode in ("lineart", "direct"):
        return ink.copy()
    if mode == "stencil":
        bb = art_bbox(ink)
        m = int(round(plate_margin_px))
        plate = np.zeros_like(ink)
        plate[max(0, bb[1] - m):bb[3] + m, max(0, bb[0] - m):bb[2] + m] = True
        return plate & ~ink
    if mode == "silhouette":
        filled = ndi.binary_fill_holes(ink)
        boundary = filled & ~ndi.binary_erosion(filled, structure=np.ones((3, 3), bool))
        lab, n = label(ink)
        if n == 0:
            return filled
        touches = ndi.maximum(boundary, lab, index=np.arange(1, n + 1))
        islands = np.zeros_like(ink)
        for i in range(1, n + 1):
            if not touches[i - 1]:
                islands |= lab == i
        return filled & ~islands
    raise ValueError(mode)


def regions(kept):
    """Number pieces (material) and holes (enclosed cutouts), largest first."""
    lab_p, n_p = label(kept)
    pieces = []
    if n_p:
        areas = ndi.sum(kept, lab_p, index=np.arange(1, n_p + 1))
        cents = ndi.center_of_mass(kept, lab_p, index=np.arange(1, n_p + 1))
        objs = ndi.find_objects(lab_p)
        order = np.argsort(-areas)
        for r, i in enumerate(order):
            sl = objs[i]
            pieces.append({"label": f"P{r + 1}", "id": int(i + 1), "area_px": int(areas[i]),
                           "centroid": [float(cents[i][1]), float(cents[i][0])],
                           "bbox": [sl[1].start, sl[0].start, sl[1].stop, sl[0].stop]})
    hmask = holes_of(kept)
    lab_h, n_h = label(hmask)
    holes = []
    if n_h:
        areas = ndi.sum(hmask, lab_h, index=np.arange(1, n_h + 1))
        cents = ndi.center_of_mass(hmask, lab_h, index=np.arange(1, n_h + 1))
        objs = ndi.find_objects(lab_h)
        order = np.argsort(-areas)
        for r, i in enumerate(order):
            sl = objs[i]
            holes.append({"label": f"H{r + 1}", "id": int(i + 1), "area_px": int(areas[i]),
                          "centroid": [float(cents[i][1]), float(cents[i][0])],
                          "bbox": [sl[1].start, sl[0].start, sl[1].stop, sl[0].stop]})
    return pieces, lab_p, holes, lab_h


def boundary_points(mask):
    b = mask & ~ndi.binary_erosion(mask, structure=np.ones((3, 3), bool))
    ys, xs = np.nonzero(b)
    return xs, ys


def bridge_candidates(island, attached, n_sectors=8, max_len_px=None):
    """Short connections from an island to the attached material, spread around it."""
    d, (iy, ix) = ndi.distance_transform_edt(~attached, return_indices=True)
    xs, ys = boundary_points(island)
    if len(xs) == 0:
        return []
    cx, cy = xs.mean(), ys.mean()
    ang = np.arctan2(ys - cy, xs - cx)
    dist = d[ys, xs]
    sector = ((ang + math.pi) / (2 * math.pi) * n_sectors).astype(int) % n_sectors
    cands = []
    for s in range(n_sectors):
        sel = np.nonzero(sector == s)[0]
        if len(sel) == 0:
            continue
        k = sel[np.argmin(dist[sel])]
        L = float(dist[k])
        if max_len_px is not None and L > max_len_px:
            continue
        px, py = int(xs[k]), int(ys[k])
        cands.append({"a": [px, py], "b": [int(ix[py, px]), int(iy[py, px])], "len_px": L,
                      "angle": float(ang[k])})
    cands.sort(key=lambda c: c["len_px"])
    return cands


def pick_spread(cands, n, min_sep=math.pi / 2.5):
    chosen = []
    for c in cands:
        if all(abs((c["angle"] - o["angle"] + math.pi) % (2 * math.pi) - math.pi) >= min_sep for o in chosen):
            chosen.append(c)
        if len(chosen) >= n:
            break
    return chosen


def draw_bridge(mask, a, b, width_px):
    """Add a bar of material from a to b, extended a little past each end."""
    ax, ay = a
    bx, by = b
    L = math.hypot(bx - ax, by - ay)
    ext = width_px * 0.6
    if L < 1e-6:
        ux, uy = 1.0, 0.0
    else:
        ux, uy = (bx - ax) / L, (by - ay) / L
    p = (ax - ux * ext, ay - uy * ext)
    q = (bx + ux * ext, by + uy * ext)
    im = Image.fromarray(mask.astype(np.uint8) * 255)
    ImageDraw.Draw(im).line([p, q], fill=255, width=max(1, int(round(width_px))))
    return np.array(im) > 0


def to_norm(xy, xf, bbox_art_px):
    """design px -> normalized art coords (0..1 across the clean-px art box)."""
    x = (xy[0] - xf["pad"]) / xf["sx"] / (bbox_art_px[2] - bbox_art_px[0])
    y = (xy[1] - xf["pad"]) / xf["sy"] / (bbox_art_px[3] - bbox_art_px[1])
    return [round(x, 5), round(y, 5)]


def from_norm(uv, xf, bbox_art_px):
    x = uv[0] * (bbox_art_px[2] - bbox_art_px[0]) * xf["sx"] + xf["pad"]
    y = uv[1] * (bbox_art_px[3] - bbox_art_px[1]) * xf["sy"] + xf["pad"]
    return [int(round(x)), int(round(y))]


def cmd_design(a):
    job = a.job
    st = load_state(job)
    if "clean" not in st or not os.path.exists(out(job, "clean.png")):
        fail("run `clean` first")
    prev = st.get("design", {})
    P = {k: prev.get(k) for k in ("mode", "units", "width", "height", "kerf", "bridge_width",
                                  "auto_bridges", "plate_margin", "min_material")}
    for k in P:
        v = getattr(a, k, None)
        if v is not None:
            P[k] = v
    if a.width is not None:
        P["height"] = None
    if a.height is not None:
        P["width"] = None
    P["units"] = P["units"] or "in"
    u = P["units"]
    defaults = {"kerf": 0.055 if u == "in" else 1.4, "bridge_width": 0.2 if u == "in" else 5.0,
                "auto_bridges": 0, "plate_margin": 0.5 if u == "in" else 12.0,
                "min_material": 0.1 if u == "in" else 2.5, "mode": "silhouette"}
    for k, v in defaults.items():
        if P[k] is None:
            P[k] = v
    made = st["clean"].get("made")
    if P["width"] is None and P["height"] is None and made:
        P["width"], P["units"] = made["width"], made["units"]
        u = P["units"]
        if a.mode is None and prev.get("mode") is None:
            P["mode"] = "direct"
    if P["width"] is None and P["height"] is None:
        fail("give --width or --height (finished size of the artwork, in " + u + ")")
    if P["mode"] not in ("silhouette", "lineart", "stencil", "direct"):
        fail("mode must be silhouette, lineart, stencil or direct")

    edits = prev.get("edits", {"drop": [], "fill": [], "bridges": []})
    if a.reset_edits:
        edits = {"drop": [], "fill": [], "bridges": []}
    for lab_ in a.drop or []:
        if lab_.upper() not in edits["drop"]:
            edits["drop"].append(lab_.upper())
    for lab_ in a.undrop or []:
        edits["drop"] = [x for x in edits["drop"] if x != lab_.upper()]
    for lab_ in a.fill or []:
        if lab_.upper() not in edits["fill"]:
            edits["fill"].append(lab_.upper())
    for lab_ in a.unfill or []:
        edits["fill"] = [x for x in edits["fill"] if x != lab_.upper()]
    for idx in a.remove_bridge or []:
        edits["bridges"] = [b for j, b in enumerate(edits["bridges"]) if j + 1 != int(idx)]

    ink_full = np.array(Image.open(out(job, "clean.png")).convert("L")) < 128
    bbox = art_bbox(ink_full)
    if bbox is None:
        fail("the cleaned image is empty; re-run clean with different settings")
    ink, ppu, width, height, xf = design_raster(ink_full, bbox, PPU_TARGET[u], u, P["width"], P["height"])
    P["width"], P["height"] = round(width, 3), round(height, 3)

    kerf_px = P["kerf"] * ppu
    bw_px = P["bridge_width"] * ppu
    base = base_material(ink, P["mode"], P["plate_margin"] * ppu)

    # ---- stable labels come from the base design, before any edits
    pieces, lab_p, holes, lab_h = regions(base)
    by_label = {r["label"]: r for r in pieces + holes}
    kept = base.copy()
    for lab_ in edits["drop"]:
        r = by_label.get(lab_)
        if r and lab_.startswith("P"):
            kept &= ~(lab_p == r["id"])
    for lab_ in edits["fill"]:
        r = by_label.get(lab_)
        if r and lab_.startswith("H"):
            kept |= lab_h == r["id"]
    unknown = [x for x in edits["drop"] + edits["fill"] if x not in by_label]
    # specks of metal smaller than a couple of min-feature squares are grain, not design
    sliver_px = 8 * (P["min_material"] * ppu) ** 2
    slivers = []
    for r in pieces:
        if r["area_px"] < sliver_px and r["label"] not in edits["drop"] and not a.keep_slivers:
            kept &= ~(lab_p == r["id"])
            slivers.append(r["label"])

    # ---- pending letter picks from the last preview
    picks = []
    for letter in a.bridge or []:
        letter = letter.upper()
        cand = (prev.get("candidates") or {}).get(letter)
        if not cand:
            fail(f"no bridge candidate {letter} in the last preview; re-run design and pick from the new letters")
        picks.append({"a": cand["a"], "b": cand["b"], "how": "picked " + letter})
    for spec in a.bridge_at or []:
        # two points in finished-part units, x,y,x,y, measured from the art's bottom-left corner
        x1, y1, x2, y2 = [float(v) for v in spec.split(",")]
        ax = xf["pad"] + x1 * ppu
        ay = xf["pad"] + (height - y1) * ppu
        bx = xf["pad"] + x2 * ppu
        by = xf["pad"] + (height - y2) * ppu
        picks.append({"a": to_norm((ax, ay), xf, bbox), "b": to_norm((bx, by), xf, bbox), "how": "coordinates"})
    edits["bridges"] += picks

    # ---- apply saved bridges (material bars)
    applied = []
    for j, b in enumerate(edits["bridges"]):
        pa, pb = from_norm(b["a"], xf, bbox), from_norm(b["b"], xf, bbox)
        kept = draw_bridge(kept, pa, pb, bw_px)
        applied.append({"n": j + 1, "a": pa, "b": pb})

    # ---- automatic bridges: attach each island to the growing main body
    auto = []
    lab_k, n_k = label(kept)
    if P["auto_bridges"] > 0 and n_k > 1:
        areas = ndi.sum(kept, lab_k, index=np.arange(1, n_k + 1))
        order = list(np.argsort(-areas) + 1)
        attached = lab_k == order[0]
        for i in order[1:]:
            isl = lab_k == i
            cands = pick_spread(bridge_candidates(isl, attached), int(P["auto_bridges"]))
            for c in cands:
                kept = draw_bridge(kept, c["a"], c["b"], bw_px)
                auto.append(c)
            attached = attached | isl
            for c in cands:
                attached = draw_bridge(attached, c["a"], c["b"], bw_px)
        lab_k, n_k = label(kept)

    # ---- what is left disconnected, and lettered suggestions for it
    candidates = {}
    loose = []
    if n_k > 1:
        areas = ndi.sum(kept, lab_k, index=np.arange(1, n_k + 1))
        order = list(np.argsort(-areas) + 1)
        main = lab_k == order[0]
        li = 0
        n_loose = len(order) - 1
        per_island = 3 if n_loose <= 3 else (2 if n_loose <= 6 else 1)
        for i in order[1:]:
            isl = lab_k == i
            # suggestions go to the main body only: island-to-island tabs (eye to eye,
            # eye to nose) look wrong on line art and still leave the cluster loose
            cs = pick_spread(bridge_candidates(isl, main), per_island, min_sep=math.pi / 3)
            cy, cx = ndi.center_of_mass(isl)
            loose.append({"piece_at": to_units((cx, cy), xf, ppu, height), "area": round(float(areas[i - 1]) / ppu / ppu, 3),
                          "letters": []})
            for c in cs:
                if li >= len(LETTERS):
                    break
                L = LETTERS[li]
                li += 1
                candidates[L] = {"a": to_norm(c["a"], xf, bbox), "b": to_norm(c["b"], xf, bbox),
                                 "len": round(c["len_px"] / ppu, 3), "_a": c["a"], "_b": c["b"]}
                loose[-1]["letters"].append(L)

    # ---- checks
    warnings = []
    mm = P["min_material"] * ppu
    thin = kept & ~opening(kept, mm / 2)
    thin = ndi.binary_opening(thin, structure=disk(1))   # ignore 1-px edge fuzz from grainy sources
    thin_area = float(thin.sum()) / ppu / ppu
    if thin_area > (P["min_material"] ** 2) * 4:
        warnings.append(f"Some material is thinner than {P['min_material']:g} {u} (about {thin_area:.2f} sq {u} in total, shown red). It may burn away; make the part bigger or fill/drop it.")
    off = dilate(kept, kerf_px / 2)
    lost_holes = len(regions(kept)[2]) - len(regions(off)[2])
    if lost_holes > 0:
        warnings.append(f"{lost_holes} cutout(s) are narrower than the kerf and will not exist in metal (they are simply skipped).")
    if n_k > 1:
        warnings.append(f"{n_k - 1} piece(s) are not connected to the main part and would fall out of the sheet. Pick bridge letters, drop them, or accept loose pieces."
                        + (" With this many, --auto-bridges 1 or 2 is usually the quickest; for raised text, re-make with --bar." if n_k > 5 else ""))
    bed = BED[u]
    fw, fh = width + (2 * P["plate_margin"] if P["mode"] == "stencil" else 0), height + (2 * P["plate_margin"] if P["mode"] == "stencil" else 0)
    if fw > bed[0] or fh > bed[1]:
        warnings.append(f"Finished size {fw:.2f} x {fh:.2f} {u} exceeds the {bed[0]:g} x {bed[1]:g} {u} bed.")

    # ---- persist masks for the g-code stage
    np.savez_compressed(out(job, "design.npz"), kept=kept, ppu=ppu, pad=xf["pad"], height=height, width=width)

    # ---- preview
    pv = render_design(kept, base, lab_p, lab_h, pieces, holes, edits, applied, auto, candidates, thin, ppu, u,
                       P, warnings, width, height, slivers)
    pv.save(out(job, "design_preview.png"))

    present_pieces = [r["label"] for r in pieces if r["label"] not in edits["drop"]]
    st["design"] = {**P, "edits": edits, "ppu": ppu, "xf": xf, "bbox": bbox,
                    "candidates": {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")} for k, v in candidates.items()},
                    "result": {"pieces_total": int(n_k), "warnings": warnings,
                               "size": [round(fw, 3), round(fh, 3)],
                               "labels": {"pieces": [{"label": r["label"], "area": round(r["area_px"] / ppu / ppu, 3),
                                                      "at": to_units(r["centroid"], xf, ppu, height)} for r in pieces],
                                          "holes": [{"label": r["label"], "area": round(r["area_px"] / ppu / ppu, 3),
                                                     "at": to_units(r["centroid"], xf, ppu, height)} for r in holes]},
                               "loose": loose}}
    st.pop("gcode", None)
    save_state(job, st)

    lines = [
        f"design: mode {P['mode']}, artwork {width:.2f} x {height:.2f} {u}" + (f", plate {fw:.2f} x {fh:.2f} {u}" if P['mode'] == 'stencil' else ""),
        f"kerf {P['kerf']:g} {u}, bridge width {P['bridge_width']:g} {u}, auto bridges per island {P['auto_bridges']}",
        f"regions: {len(pieces)} piece(s) P1..P{len(pieces)}, {len(holes)} cutout(s) H1..H{len(holes)}; "
        f"after edits and bridges: {n_k} connected piece(s)",
    ]
    if edits["drop"] or edits["fill"] or applied:
        lines.append(f"edits: dropped {edits['drop'] or 'none'}, filled {edits['fill'] or 'none'}, bridges {len(applied)} picked + {len(auto)} automatic")
    if unknown:
        lines.append(f"ignored unknown labels: {unknown}")
    if slivers:
        lines.append(f"dropped {len(slivers)} speck(s) of metal smaller than {8 * P['min_material'] ** 2:.3f} sq {u} ({', '.join(slivers)}); pass --keep-slivers to keep them")
    if candidates:
        for l_ in loose:
            lines.append(f"loose piece at ({l_['piece_at'][0]:.2f}, {l_['piece_at'][1]:.2f}) {u}, {l_['area']:g} sq {u}: bridge options {', '.join(l_['letters'])}")
    for w_ in warnings:
        lines.append("WARNING " + w_)
    lines.append(f"preview: {out(job, 'design_preview.png')}  (gray = metal, white = removed, numbers = regions, green = bridges, orange letters = bridge options, red = too thin)")
    emit(lines, {"stage": "design", **st["design"]["result"], "candidates": list(candidates.keys()),
                 "params": P, "preview": out(job, "design_preview.png")})


def to_units(xy, xf, ppu, height):
    """design px -> finished-part coordinates, x right, y up, from the art's bottom-left."""
    return [round((xy[0] - xf["pad"]) / ppu, 3), round(height - (xy[1] - xf["pad"]) / ppu, 3)]


def render_design(kept, base, lab_p, lab_h, pieces, holes, edits, applied, auto, candidates, thin, ppu, u, P,
                  warnings, width, height, slivers=()):
    H, W = kept.shape
    rgb = np.full((H, W, 3), 255, np.uint8)
    rgb[kept] = (110, 110, 118)
    rgb[thin] = (220, 60, 60)
    for lab_ in edits["drop"] + slivers:
        r = next((p for p in pieces if p["label"] == lab_), None)
        if r:
            m = (lab_p == r["id"]) & ~kept
            rgb[m] = (238, 224, 224)
    im = Image.fromarray(rgb)
    d = ImageDraw.Draw(im)
    s = max(10, int(W / 60))
    fb = font(s)
    fs = font(max(9, int(s * 0.8)))
    lw = max(2, int(ppu * (0.02 if u == "in" else 0.5)))
    for b in applied:
        d.line([tuple(b["a"]), tuple(b["b"])], fill=(30, 160, 60), width=lw * 2)
        mx, my = (b["a"][0] + b["b"][0]) / 2, (b["a"][1] + b["b"][1]) / 2
        badge(d, (mx, my), f"B{b['n']}", (30, 130, 50), fs)
    for c in auto:
        d.line([tuple(c["a"]), tuple(c["b"])], fill=(30, 160, 60), width=lw * 2)
    for L, c in candidates.items():
        a_, b_ = c["_a"], c["_b"]
        d.line([tuple(a_), tuple(b_)], fill=(235, 140, 20), width=lw)
        # label near the far (main-body) end so short options on one small piece stay readable
        t = 0.7 if math.dist(a_, b_) > 6 * s else 0.5
        mx, my = a_[0] + (b_[0] - a_[0]) * t, a_[1] + (b_[1] - a_[1]) * t
        badge(d, (mx, my), L, (225, 120, 10), fb)
    for r in pieces:
        col = (40, 80, 200) if r["label"] not in edits["drop"] + list(slivers) else (150, 150, 150)
        badge(d, tuple(r["centroid"]), r["label"], col, fb)
    for r in holes:
        col = (160, 40, 120) if r["label"] not in edits["fill"] else (150, 150, 150)
        badge(d, tuple(r["centroid"]), r["label"], col, fs)
    # scale bar and caption
    bar = ppu * (1 if u == "in" else 25.4)
    d.line([(20, H - 20), (20 + bar, H - 20)], fill=(0, 0, 0), width=3)
    d.text((24, H - 20 - s - 4), "1 in" if u == "in" else "25 mm", fill=(0, 0, 0), font=fs)
    cap = f"{P['mode']}  {width:.2f} x {height:.2f} {u}   gray=metal  white=cut away  green=bridge  orange=bridge option  red=too thin"
    d.text((20, 8), cap, fill=(0, 0, 0), font=fs)
    return fit_preview(im, 1400)


# --------------------------------------------------------------------------
# 3. g-code
# --------------------------------------------------------------------------

def flatten_curve(curve, step_px=1.0):
    pts = []
    p0 = (curve.start_point.x, curve.start_point.y)
    pts.append(p0)
    for seg in curve.segments:
        if seg.is_corner:
            c = (seg.c.x, seg.c.y)
            e = (seg.end_point.x, seg.end_point.y)
            pts += [c, e]
            p0 = e
        else:
            c1 = (seg.c1.x, seg.c1.y)
            c2 = (seg.c2.x, seg.c2.y)
            e = (seg.end_point.x, seg.end_point.y)
            L = math.dist(p0, c1) + math.dist(c1, c2) + math.dist(c2, e)
            n = max(2, int(math.ceil(L / step_px)))
            for k in range(1, n + 1):
                t = k / n
                mt = 1 - t
                x = mt ** 3 * p0[0] + 3 * mt * mt * t * c1[0] + 3 * mt * t * t * c2[0] + t ** 3 * e[0]
                y = mt ** 3 * p0[1] + 3 * mt * mt * t * c1[1] + 3 * mt * t * t * c2[1] + t ** 3 * e[1]
                pts.append((x, y))
            p0 = e
    if len(pts) > 1 and math.dist(pts[0], pts[-1]) < 1e-9:
        pts.pop()
    return pts


def rdp(pts, eps):
    """Douglas-Peucker on a closed ring (treated as open from index 0)."""
    if eps <= 0 or len(pts) < 4:
        return pts
    P = np.asarray(pts, float)
    keep = np.zeros(len(P), bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(P) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = P[i], P[j]
        ab = b - a
        L = np.hypot(*ab)
        seg = P[i + 1:j]
        if L < 1e-12:
            dists = np.hypot(*(seg - a).T)
        else:
            dists = np.abs(ab[0] * (seg[:, 1] - a[1]) - ab[1] * (seg[:, 0] - a[0])) / L
        k = int(np.argmax(dists))
        if dists[k] > eps:
            keep[i + 1 + k] = True
            stack += [(i, i + 1 + k), (i + 1 + k, j)]
    return [tuple(p) for p in P[keep]]


def signed_area(pts):
    a = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return a / 2


def point_in_ring(pt, ring):
    x, y = pt
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if xi > x:
                inside = not inside
    return inside


def ring_length(pts):
    return sum(math.dist(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts)))


def pick_start(coords, scrap_test, lead_in):
    n = len(coords)
    L = lead_in
    while L >= lead_in / 8:
        for k in range(0, n, max(1, n // 24)):
            p0, p1 = coords[k], coords[(k + 1) % n]
            tx, ty = p1[0] - p0[0], p1[1] - p0[1]
            d = math.hypot(tx, ty)
            if d < 1e-9:
                continue
            tx, ty = tx / d, ty / d
            nx, ny = -ty, tx  # scrap is on the left of travel
            s = (p0[0] + nx * L, p0[1] + ny * L)
            if scrap_test(s):
                return k, s, L
        L /= 2
    return 0, coords[0], 0.0


def cmd_gcode(a):
    job = a.job
    st = load_state(job)
    if "design" not in st or not os.path.exists(out(job, "design.npz")):
        fail("run `design` first")
    D = st["design"]
    u = D["units"]
    prev = st.get("gcode", {})
    G = {k: prev.get(k) for k in ("feed", "pierce_delay", "dwell_ms", "lead_in", "overcut", "simplify",
                                  "origin_margin", "name", "comments")}
    for k in G:
        v = getattr(a, k, None)
        if v is not None:
            G[k] = v
    dflt = {"feed": 60.0 if u == "in" else 1500.0, "pierce_delay": 0.5, "dwell_ms": False,
            "lead_in": 0.1 if u == "in" else 2.5, "overcut": 0.05 if u == "in" else 1.2,
            "simplify": 0.003 if u == "in" else 0.08, "origin_margin": 0.5 if u == "in" else 12.0,
            "name": "part", "comments": True}
    for k, v in dflt.items():
        if G[k] is None:
            G[k] = v

    z = np.load(out(job, "design.npz"))
    kept = z["kept"]
    ppu = float(z["ppu"])
    kerf_px = D["kerf"] * ppu
    H, W = kept.shape

    # ---- kerf offset in raster space, then one trace
    off = dilate(kept, kerf_px / 2)
    t0 = time.time()
    path = potrace.Bitmap(~off).trace(turdsize=2, alphamax=1.0, opticurve=True, opttolerance=0.2)
    trace_s = time.time() - t0
    rings_px = [flatten_curve(c, 1.0) for c in path.curves]
    rings_px = [r for r in rings_px if len(r) >= 3]

    # ---- machine coordinates: y up, part corner at the origin margin
    def to_m(p):
        return (p[0] / ppu, (H - p[1]) / ppu)
    rings_m = [[to_m(p) for p in r] for r in rings_px]
    allx = [p[0] for r in rings_m for p in r]
    ally = [p[1] for r in rings_m for p in r]
    minx, miny = min(allx), min(ally)
    m = G["origin_margin"]
    rings_m = [[(p[0] - minx + m, p[1] - miny + m) for p in r] for r in rings_m]
    rings_m = [rdp(r, G["simplify"]) for r in rings_m]

    # ---- nesting: even depth = outer, odd depth = hole (largest first)
    order = sorted(range(len(rings_m)), key=lambda i: -abs(signed_area(rings_m[i])))
    depth, parent = {}, {}
    for idx, i in enumerate(order):
        pt = rings_m[i][0]
        # nudge the test point slightly inside using the centroid direction is overkill; use a vertex midpoint
        p2 = rings_m[i][1]
        test = ((pt[0] + p2[0]) / 2, (pt[1] + p2[1]) / 2)
        containers = [j for j in order[:idx] if point_in_ring(test, rings_m[j])]
        depth[i] = len(containers)
        parent[i] = min(containers, key=lambda j: abs(signed_area(rings_m[j]))) if containers else None
    outers = [i for i in order if depth[i] % 2 == 0]
    holes = [i for i in order if depth[i] % 2 == 1]

    # raster scrap test for outer lead-ins: the pierce point must lie clear of metal
    clear = ~dilate(kept, kerf_px * 0.75)

    def m_to_px(p):
        return (int(round((p[0] - m + minx) * ppu)), int(round(H - (p[1] - m + miny) * ppu)))

    def in_clear(p):
        x, y = m_to_px(p)
        return 0 <= x < W and 0 <= y < H and bool(clear[y, x])

    rings = []
    pi_map = {}
    for n_o, i in enumerate(outers):
        pi_map[i] = n_o
    for hi, i in enumerate(holes):
        r = rings_m[i]
        if signed_area(r) < 0:   # holes CCW (y-up)
            r = r[::-1]
        pidx = pi_map.get(parent[i], 0)
        ring = r
        k, start, L = pick_start(ring, lambda s, hr=ring: point_in_ring(s, hr), G["lead_in"])
        rings.append({"id": f"hole-{pidx}-{hi}", "type": "hole", "coords": ring[k:] + ring[:k], "pierce": start,
                      "lead_len": L})
    for n_o, i in enumerate(outers):
        r = rings_m[i]
        if signed_area(r) > 0:   # exteriors CW (y-up)
            r = r[::-1]
        ring = r
        k, start, L = pick_start(ring, in_clear, G["lead_in"])
        rings.append({"id": f"outer-{n_o}", "type": "outer", "coords": ring[k:] + ring[:k], "pierce": start,
                      "lead_len": L})
    for r in rings:
        r["length"] = ring_length(r["coords"])

    def nn(items, start):
        res, cur = [], start
        pool = list(items)
        while pool:
            nxt = min(pool, key=lambda r: math.dist(cur, r["pierce"]))
            pool.remove(nxt)
            res.append(nxt)
            cur = nxt["coords"][0]
        return res
    ordered = nn([r for r in rings if r["type"] == "hole"], (0, 0))
    ordered += nn([r for r in rings if r["type"] == "outer"], ordered[-1]["coords"][0] if ordered else (0, 0))

    cuts, rapids, cur = [], [], (0.0, 0.0)
    for r in ordered:
        pts = [r["pierce"]] + r["coords"] + [r["coords"][0]]
        rem = G["overcut"]
        i = 0
        while rem > 0 and i < len(r["coords"]) - 1:
            p, q = r["coords"][i], r["coords"][i + 1]
            d = math.dist(p, q)
            if d >= rem:
                t = rem / d
                pts.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t))
                rem = 0
            else:
                pts.append(q)
                rem -= d
            i += 1
        rapids.append([cur, r["pierce"]])
        cuts.append({"id": r["id"], "type": r["type"], "pts": pts})
        cur = pts[-1]
    rapids.append([cur, (0.0, 0.0)])

    nc = gcode_text(cuts, rapids, units=u, feed=G["feed"], pierce_delay=G["pierce_delay"], dwell_ms=G["dwell_ms"],
                    program_name=G["name"], comments=G["comments"])
    nc_path = out(job, f"{G['name']}.nc")
    with open(nc_path, "w") as f:
        f.write(nc)

    cut_len = sum(sum(math.dist(c["pts"][i], c["pts"][i + 1]) for i in range(len(c["pts"]) - 1)) for c in cuts)
    rapid_len = sum(math.dist(p, q) for p, q in rapids)
    rapid_feed = 300.0 if u == "in" else 7600.0
    est_min = cut_len / G["feed"] + rapid_len / rapid_feed + len(cuts) * (G["pierce_delay"] + 0.5) / 60
    maxx = max(p[0] for c in cuts for p in c["pts"])
    maxy = max(p[1] for c in cuts for p in c["pts"])
    warnings = list(D["result"].get("warnings", []))
    no_lead = [c["id"] for c, r in zip(cuts, ordered) if r["lead_len"] == 0]
    if no_lead:
        warnings.append(f"{len(no_lead)} cut(s) start on the line with no lead-in (no clear scrap nearby): {', '.join(no_lead)}")

    # ---- independent check: re-read the .nc file and draw it over the design
    pv = render_toolpath(nc_path, kept, ppu, minx, miny, m, H, u, cuts)
    pv.save(out(job, "toolpath_preview.png"))

    st["gcode"] = {**G, "result": {"file": nc_path, "pierces": len(cuts), "cut_length": round(cut_len, 2),
                                   "rapid_length": round(rapid_len, 2), "est_minutes": round(est_min, 1),
                                   "extent": [round(maxx, 3), round(maxy, 3)], "segments": sum(len(c["pts"]) - 1 for c in cuts),
                                   "trace_seconds": round(trace_s, 1), "warnings": warnings}}
    save_state(job, st)
    emit([
        f"gcode: {nc_path}",
        f"{len(cuts)} pierces ({len(holes)} cutouts first, then {len(outers)} outlines), cut length {cut_len:.1f} {u}, rapids {rapid_len:.1f} {u}, about {est_min:.1f} min at F{G['feed']:g}",
        f"program extent: X 0 to {maxx:.2f}, Y 0 to {maxy:.2f} {u} (origin margin {m:g}); feed {G['feed']:g} {u}/min, pierce delay {G['pierce_delay']:g} s, lead-in {G['lead_in']:g}, overcut {G['overcut']:g}",
        *("WARNING " + w for w in warnings),
        f"preview: {out(job, 'toolpath_preview.png')}  (drawn from the saved .nc file itself: red = outlines, blue = cutouts, dashed = rapids, numbers = cut order)",
    ], {"stage": "gcode", **st["gcode"]["result"], "preview": out(job, "toolpath_preview.png")})


def gcode_text(cuts, rapids, *, units, feed, pierce_delay, dwell_ms, program_name, comments):
    f = (lambda v: f"{v:.4f}") if units == "in" else (lambda v: f"{v:.3f}")
    lines = []
    c = (lambda s: f"({s})") if comments else (lambda s: None)

    def put(s):
        if s is not None:
            lines.append(s)
    put(c(f"{program_name} - generated for Langmuir CrossFire / Mach3, no Z axis"))
    put(c(f"plasma-path {__version__}"))
    put(c(f"units {units}, feed {feed:g}, pierce delay {pierce_delay:g}s, {len(cuts)} pierces"))
    put("G20" if units == "in" else "G21")
    put("G90 G94 G40 G17 G64")
    put("M5")
    put(f"F{feed:g}")
    dwell = f"G4 P{int(pierce_delay * 1000)}" if dwell_ms else f"G4 P{pierce_delay:g}"
    for i, (cut, rap) in enumerate(zip(cuts, rapids)):
        pts = cut["pts"]
        put("")
        put(c(f"cut {i + 1}: {cut['type']} {cut['id']}"))
        put(f"G0 X{f(pts[0][0])} Y{f(pts[0][1])}")
        put("M3")
        put(dwell)
        for x, y in pts[1:]:
            put(f"G1 X{f(x)} Y{f(y)}")
        put("M5")
    put("")
    put(c("return home"))
    put("G0 X0 Y0")
    put("M30")
    return "\n".join(lines) + "\n"


def parse_nc(path):
    """Minimal reader for our own output: returns list of (kind, x, y) moves."""
    moves = []
    x = y = 0.0
    torch = False
    with open(path) as fh:
        for raw in fh:
            s = raw.strip()
            if not s or s.startswith("("):
                continue
            w = s.split()
            if w[0] == "M3":
                torch = True
                continue
            if w[0] == "M5":
                torch = False
                continue
            if w[0] in ("G0", "G1"):
                for t in w[1:]:
                    if t[0] == "X":
                        x = float(t[1:])
                    elif t[0] == "Y":
                        y = float(t[1:])
                moves.append(("cut" if (w[0] == "G1" and torch) else "rapid", x, y))
    return moves


def render_toolpath(nc_path, kept, ppu, minx, miny, m, H, u, cuts):
    Hh, W = kept.shape
    rgb = np.full((Hh, W, 3), 255, np.uint8)
    rgb[kept] = (205, 205, 210)
    im = Image.fromarray(rgb)
    d = ImageDraw.Draw(im)

    def px(x, y):
        return ((x - m + minx) * ppu, H - (y - m + miny) * ppu)
    moves = parse_nc(nc_path)
    lw = max(1, int(ppu * (0.02 if u == "in" else 0.5)))
    prev = (0.0, 0.0)
    n_cut = 0
    fs = font(max(10, int(W / 70)))
    in_cut = False
    for kind, x, y in moves:
        a, b = px(*prev), px(x, y)
        if kind == "rapid":
            # dashed
            L = math.dist(a, b)
            n = max(1, int(L / (ppu * 0.1)))
            for k in range(0, n, 2):
                t0, t1 = k / n, min(1, (k + 1) / n)
                d.line([(a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0),
                        (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)], fill=(150, 150, 150), width=1)
            in_cut = False
        else:
            if not in_cut:
                n_cut += 1
                badge(d, a, str(n_cut), (20, 20, 20), fs)
                in_cut = True
            typ = cuts[n_cut - 1]["type"] if n_cut - 1 < len(cuts) else "outer"
            d.line([a, b], fill=(210, 40, 40) if typ == "outer" else (40, 80, 210), width=lw)
        prev = (x, y)
    return fit_preview(im, 1400)


# --------------------------------------------------------------------------
# make: shapes and text from nothing
# --------------------------------------------------------------------------

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor", "fonts")
FONTS = {"sans": "LiberationSans-Regular.ttf", "sans-bold": "LiberationSans-Bold.ttf",
         "serif-bold": "LiberationSerif-Bold.ttf", "mono-bold": "LiberationMono-Bold.ttf",
         "arial": "LiberationSans-Regular.ttf", "arial-bold": "LiberationSans-Bold.ttf",
         "helvetica": "LiberationSans-Regular.ttf", "times": "LiberationSerif-Bold.ttf", "courier": "LiberationMono-Bold.ttf"}


def text_font(name, cap_px):
    """A font whose capital letters are cap_px tall."""
    key = (name or "sans-bold").lower().replace(" ", "-")
    path = name if name and os.path.exists(name) else os.path.join(FONT_DIR, FONTS.get(key, FONTS["sans-bold"]))
    probe = ImageFont.truetype(path, 100)
    l, t, r, b = probe.getbbox("H")
    size = int(round(100 * cap_px / max(1, b - t)))
    return ImageFont.truetype(path, size), os.path.basename(path)


def cmd_make(a):
    job = a.job
    os.makedirs(job, exist_ok=True)
    u = a.units
    ppu = PPU_TARGET[u]
    parts = [float(v) for v in a.size.split(",")] if a.size else []
    if a.shape != "none" and not parts:
        fail("--size is needed for a shape (one number for a circle or square, W,H for a rectangle)")
    W_u = parts[0] if parts else 0
    H_u = parts[1] if len(parts) > 1 else W_u
    if a.shape == "none":
        # size the canvas around the text
        W_u = H_u = max(1.0, a.text_height * 20)
    long_units = max(W_u, H_u)
    ppu = min(ppu, MAX_DESIGN_PX / long_units)
    pad = int(ppu * (0.5 if u == "in" else 12))
    W, H = int(W_u * ppu) + 2 * pad, int(H_u * ppu) + 2 * pad
    canvas = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(canvas)
    x0, y0, x1, y1 = pad, pad, pad + W_u * ppu, pad + H_u * ppu
    if a.shape == "circle":
        d.ellipse([x0, y0, x1, y1], fill=255)
    elif a.shape == "rect":
        d.rounded_rectangle([x0, y0, x1, y1], radius=a.corner * ppu, fill=255)
    elif a.shape == "ring":
        d.ellipse([x0, y0, x1, y1], fill=255)
        w = a.ring_width * ppu
        d.ellipse([x0 + w, y0 + w, x1 - w, y1 - w], fill=0)
    metal = np.array(canvas) > 0

    info = {"shape": a.shape, "width": round(W_u, 3), "height": round(H_u, 3), "units": u}
    if a.text:
        fnt, fname = text_font(a.font, a.text_height * ppu)
        lines = a.text.replace("\\n", "\n").split("\n") if "\\n" in a.text or "\n" in a.text else a.text.split("|")
        gap = a.line_gap * ppu
        heights, widths = [], []
        for ln in lines:
            l, t, r, b = d.textbbox((0, 0), ln, font=fnt)
            widths.append(r - l)
            heights.append(b - t)
        total_h = sum(heights) + gap * (len(lines) - 1)
        cx = (x0 + x1) / 2 + a.text_at[0] * ppu
        cy = (y0 + y1) / 2 - a.text_at[1] * ppu
        tcanvas = Image.new("L", (W, H), 0)
        td = ImageDraw.Draw(tcanvas)
        y = cy - total_h / 2
        for ln, hh, ww in zip(lines, heights, widths):
            l, t, r, b = td.textbbox((0, 0), ln, font=fnt)
            td.text((cx - ww / 2 - l, y - t), ln, fill=255, font=fnt)
            y += hh + gap
        tmask = np.array(tcanvas) > 0
        if a.bar and a.bar > 0 and a.text_mode == "raised":
            # a connecting bar along the bottom of the text so separate letters become one part
            tb = art_bbox(tmask)
            t_px = a.bar * ppu
            bar = Image.new("L", (W, H), 0)
            ImageDraw.Draw(bar).rectangle([tb[0] - t_px, tb[3] - t_px * 0.35, tb[2] + t_px, tb[3] + t_px * 0.65], fill=255)
            tmask |= np.array(bar) > 0
            info["bar"] = a.bar
        if a.text_mode == "cut":
            metal &= ~tmask
        else:
            metal |= tmask
        info.update({"text": a.text, "font": fname, "text_height": a.text_height, "text_mode": a.text_mode,
                     "text_size": [round(max(widths) / ppu, 3), round(total_h / ppu, 3)]})
        if a.shape != "none" and max(widths) > (x1 - x0) * 0.95:
            info["warning"] = "text is wider than the shape"
    holes = []
    for spec in a.hole or []:
        dia, hx, hy = [float(v) for v in spec.split(",")]
        px_ = (x0 + x1) / 2 + hx * ppu
        py_ = (y0 + y1) / 2 - hy * ppu
        r = dia * ppu / 2
        hm = Image.new("L", (W, H), 0)
        ImageDraw.Draw(hm).ellipse([px_ - r, py_ - r, px_ + r, py_ + r], fill=255)
        metal &= ~(np.array(hm) > 0)
        holes.append({"dia": dia, "at": [hx, hy]})
    if holes:
        info["holes"] = holes

    # crop the canvas to the metal plus a margin, save as the "cleaned" image (black = metal)
    bb = art_bbox(metal)
    if bb is None:
        fail("nothing to cut: the text or shape produced no metal")
    m = pad
    metal = metal[max(0, bb[1] - m):bb[3] + m, max(0, bb[0] - m):bb[2] + m]
    Image.fromarray(np.where(metal, 0, 255).astype(np.uint8)).save(out(job, "clean.png"))
    pv = Image.fromarray(np.where(metal, 90, 255).astype(np.uint8)).convert("RGB")
    fit_preview(pv, 1200).save(out(job, "clean_preview.png"))
    made_w = (bb[2] - bb[0]) / ppu
    made_h = (bb[3] - bb[1]) / ppu
    info.update({"made_width": round(made_w, 3), "made_height": round(made_h, 3)})

    st = load_state(job)
    st["source"] = "made"
    st["image"] = {"w": int(metal.shape[1]), "h": int(metal.shape[0])}
    st["clean"] = {"made": {**info, "width": round(made_w, 3), "height": round(made_h, 3)},
                   "result": {"marks": int(label(metal)[1]), "removed": {}, "ink_fraction": round(float(metal.mean()), 4)}}
    st.pop("design", None)
    st.pop("gcode", None)
    save_state(job, st)
    emit([
        (f"make: {a.shape} {W_u:g} x {H_u:g} {u}" if a.shape != "none" else "make: text only") + (f", text '{a.text}' {a.text_height:g} {u} tall ({info.get('font')}), {a.text_mode}" if a.text else "")
        + (f", {len(holes)} hole(s)" if holes else ""),
        f"metal extent {made_w:.2f} x {made_h:.2f} {u}; next: design --job {job} (mode direct and this size are the defaults)",
        *(["WARNING " + info["warning"]] if "warning" in info else []),
        f"preview: {out(job, 'clean_preview.png')}  (gray = metal)",
    ], {"stage": "make", **info, "preview": out(job, "clean_preview.png")})


# --------------------------------------------------------------------------
# show
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# edit and adopt: shape the drawing freely
# --------------------------------------------------------------------------

def _poly_px(spec, W, H):
    pts = []
    for tok in spec.replace(";", " ").split():
        x, y = tok.split(",")
        pts.append((float(x) * W, float(y) * H))
    return pts


def _rect_px(spec, W, H):
    x0, y0, x1, y1 = [float(v) for v in spec.split(",")]
    return [x0 * W, y0 * H, x1 * W, y1 * H]


def cmd_edit(a):
    """Apply simple edits to the cleaned bitmap (black = ink). Coordinates are fractions of the image."""
    job = a.job
    st = load_state(job)
    if not os.path.exists(out(job, "clean.png")):
        fail("nothing to edit yet: run clean, make or adopt first")
    ink = np.array(Image.open(out(job, "clean.png")).convert("L")) < 128
    before = ink.copy()
    H, W = ink.shape
    applied = []

    def mask_from(draw_fn):
        m = Image.new("L", (W, H), 0)
        draw_fn(ImageDraw.Draw(m))
        return np.array(m) > 0

    for spec in a.erase or []:
        ink &= ~mask_from(lambda d: d.rectangle(_rect_px(spec, W, H), fill=255))
        applied.append(f"erase rect {spec}")
    for spec in a.erase_poly or []:
        ink &= ~mask_from(lambda d: d.polygon(_poly_px(spec, W, H), fill=255))
        applied.append(f"erase polygon {spec}")
    for spec in a.erase_circle or []:
        cx, cy, r = [float(v) for v in spec.split(",")]
        rp = r * W  # radius as a fraction of the width
        ink &= ~mask_from(lambda d: d.ellipse([cx * W - rp, cy * H - rp, cx * W + rp, cy * H + rp], fill=255))
        applied.append(f"erase circle {spec}")
    for spec in a.keep_poly or []:
        ink &= mask_from(lambda d: d.polygon(_poly_px(spec, W, H), fill=255))
        applied.append(f"keep only polygon {spec}")
    for spec in a.keep_rect or []:
        ink &= mask_from(lambda d: d.rectangle(_rect_px(spec, W, H), fill=255))
        applied.append(f"keep only rect {spec}")
    for spec in a.paint_poly or []:
        ink |= mask_from(lambda d: d.polygon(_poly_px(spec, W, H), fill=255))
        applied.append(f"paint polygon {spec}")
    for spec in a.paint_rect or []:
        ink |= mask_from(lambda d: d.rectangle(_rect_px(spec, W, H), fill=255))
        applied.append(f"paint rect {spec}")
    for spec in a.paint_line or []:
        parts = spec.split(":")
        width = float(parts[1]) * W if len(parts) > 1 else max(2, W / 150)
        ink |= mask_from(lambda d: d.line(_poly_px(parts[0], W, H), fill=255, width=int(width)))
        applied.append(f"paint line {spec}")
    for spec in a.smooth_region or []:
        # opening then closing inside a rectangle, to knock off nubs and fill nicks
        x0, y0, x1, y1 = [int(v) for v in _rect_px(spec.split(":")[0], W, H)]
        r = float(spec.split(":")[1]) if ":" in spec else 3
        sub = ink[y0:y1, x0:x1]
        sub = ndi.binary_closing(ndi.binary_opening(sub, structure=disk(r)), structure=disk(r))
        ink[y0:y1, x0:x1] = sub
        applied.append(f"smooth region {spec}")
    if a.smooth:
        ink = ndi.binary_closing(ndi.binary_opening(ink, structure=disk(a.smooth)), structure=disk(a.smooth))
        applied.append(f"smooth all {a.smooth}px")
    if a.thicken:
        ink = dilate(ink, a.thicken)
        applied.append(f"thicken {a.thicken}px")
    if a.thin:
        ink = erode(ink, a.thin)
        applied.append(f"thin {a.thin}px")
    if a.fill_holes_under:
        hm = holes_of(ink)
        lab, n = label(hm)
        if n:
            areas = ndi.sum(hm, lab, index=np.arange(1, n + 1))
            small = np.nonzero(areas < a.fill_holes_under)[0] + 1
            ink |= np.isin(lab, small)
        applied.append(f"fill holes under {a.fill_holes_under}px")
    if a.fill_all_holes:
        ink = ndi.binary_fill_holes(ink)
        applied.append("fill all enclosed areas")
    if a.outline:
        ink = ink & ~erode(ink, a.outline)
        applied.append(f"outline only, {a.outline}px wide")
    if a.invert:
        ink = ~ink
        applied.append("invert")
    if a.mirror:
        ink = ink[:, ::-1]
        applied.append("mirror left-right")
    if a.rotate:
        im = Image.fromarray((ink * 255).astype(np.uint8)).rotate(a.rotate, resample=Image.BILINEAR, expand=True, fillcolor=0)
        ink = np.array(im) > 127
        applied.append(f"rotate {a.rotate}")
    if not applied:
        fail("no edit given; see --help for the operations")

    Image.fromarray(np.where(ink, 0, 255).astype(np.uint8)).save(out(job, "clean.png"))
    _edit_preview(before, ink, job)
    st.setdefault("clean", {}).setdefault("edits", []).extend(applied)
    st["clean"].setdefault("result", {})["marks"] = int(label(ink)[1])
    st.pop("design", None)
    st.pop("gcode", None)
    save_state(job, st)
    changed = int((before != ink).sum())
    emit([f"edit: {'; '.join(applied)}", f"changed {changed} px; {label(ink)[1]} marks now",
          f"preview: {out(job, 'clean_preview.png')}  (left: before, red = removed, green = added; right: after, with the coordinate grid)"],
         {"stage": "edit", "applied": applied, "changed_px": changed, "preview": out(job, "clean_preview.png")})


def _edit_preview(before, after, job):
    H, W = after.shape
    Hb, Wb = before.shape
    left = np.full((Hb, Wb, 3), 255, np.uint8)
    left[before] = (0, 0, 0)
    if before.shape == after.shape:
        left[before & ~after] = (230, 60, 60)
        left[after & ~before] = (40, 170, 70)
    right = Image.fromarray(np.where(after, 0, 255).astype(np.uint8)).convert("RGB")
    draw_grid(right)
    gap = 16
    pv = Image.new("RGB", (Wb + W + gap, max(Hb, H)), (200, 200, 200))
    pv.paste(Image.fromarray(left), (0, 0))
    pv.paste(right, (Wb + gap, 0))
    fit_preview(pv, 1600).save(out(job, "clean_preview.png"))


def cmd_adopt(a):
    """Take any black-and-white image you made yourself as the cleaned drawing (black = ink)."""
    job = a.job
    os.makedirs(job, exist_ok=True)
    gray = load_gray(a.image)
    ink = gray < a.threshold
    if a.invert:
        ink = ~ink
    if ink.mean() > 0.5 and not a.invert and a.auto_invert:
        ink = ~ink
    Image.fromarray(np.where(ink, 0, 255).astype(np.uint8)).save(out(job, "clean.png"))
    right = Image.fromarray(np.where(ink, 0, 255).astype(np.uint8)).convert("RGB")
    draw_grid(right)
    fit_preview(right, 1200).save(out(job, "clean_preview.png"))
    st = load_state(job)
    st["source"] = os.path.abspath(a.image)
    st["image"] = {"w": int(ink.shape[1]), "h": int(ink.shape[0])}
    st["clean"] = {"adopted": os.path.abspath(a.image), "threshold": a.threshold,
                   "result": {"marks": int(label(ink)[1]), "removed": {}, "ink_fraction": round(float(ink.mean()), 4)}}
    st.pop("design", None)
    st.pop("gcode", None)
    save_state(job, st)
    emit([f"adopt: {a.image} -> {ink.shape[1]}x{ink.shape[0]} px, {label(ink)[1]} marks, ink fraction {ink.mean():.3f}",
          f"preview: {out(job, 'clean_preview.png')}"],
         {"stage": "adopt", "marks": int(label(ink)[1]), "preview": out(job, "clean_preview.png")})


def cmd_show(a):
    st = load_state(a.job)
    if not st:
        fail("no job at " + a.job)
    print(json.dumps(st, indent=2))


# --------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("clean", help="threshold and clean the image")
    c.add_argument("image")
    c.add_argument("--job", required=True)
    c.add_argument("--threshold", default="auto", help="0-255 or auto (Otsu)")
    c.add_argument("--invert", default="auto", choices=["auto", "on", "off"], help="on for light art on a dark background")
    c.add_argument("--adaptive", type=int, default=0, help="local threshold window in px (odd), for photos/scans with uneven light")
    c.add_argument("--offset", type=float, default=10, help="how much darker than local mean counts as ink (with --adaptive)")
    c.add_argument("--blur", type=float, default=0, help="gaussian blur sigma in px before thresholding (1-2 tames JPEG halos)")
    c.add_argument("--open", type=int, default=0, help="morphological opening radius px (removes thin noise)")
    c.add_argument("--close", type=int, default=0, help="morphological closing radius px (bridges small gaps in lines)")
    c.add_argument("--speck", type=int, default=30, help="drop marks smaller than this many px")
    c.add_argument("--keep-largest", type=int, default=0, help="keep only the N largest marks")
    c.add_argument("--frame", default="on", choices=["on", "off"], help="drop a thin border frame around the image")
    c.add_argument("--top", type=float, default=0.0, help="ignore marks entirely within the top fraction of the image")
    c.add_argument("--bottom", type=float, default=0.0, help="ignore marks starting within the bottom fraction (watermarks)")
    c.add_argument("--crop", default=None, help="x0,y0,x1,y1 as fractions 0-1: keep only this region")
    c.add_argument("--rotate", type=float, default=0.0, help="degrees counter-clockwise to straighten a tilted scan")
    c.add_argument("--color-keep", dest="color_keep", help="keep only this colour as ink: a name (red, blue...), #rrggbb or r,g,b")
    c.add_argument("--color-drop", dest="color_drop", help="treat this colour as background before thresholding")
    c.add_argument("--color-tol", dest="color_tol", type=float, default=80, help="colour tolerance (default 80; 40 strict, 120 loose)")
    c.add_argument("--drop-mark", dest="drop_mark", action="append", metavar="N", help="remove mark number N from the last preview")
    c.add_argument("--keep-mark", dest="keep_mark", action="append", metavar="N", help="keep only these mark numbers")
    c.set_defaults(fn=cmd_clean)

    d = sub.add_parser("design", help="decide what is metal and what is cut away")
    d.add_argument("--job", required=True)
    d.add_argument("--mode", choices=["silhouette", "lineart", "stencil", "direct"], help="direct: black in the cleaned image is the metal, as drawn (used after `make`)")
    d.add_argument("--units", choices=["in", "mm"])
    d.add_argument("--width", type=float, help="finished artwork width")
    d.add_argument("--height", type=float, help="finished artwork height")
    d.add_argument("--kerf", type=float, help="kerf width (0.055 in default)")
    d.add_argument("--bridge-width", type=float, dest="bridge_width")
    d.add_argument("--auto-bridges", type=int, dest="auto_bridges", help="automatic bridges per loose piece (0 = suggest letters instead)")
    d.add_argument("--plate-margin", type=float, dest="plate_margin", help="stencil plate margin around the art")
    d.add_argument("--min-material", type=float, dest="min_material", help="warn about features thinner than this")
    d.add_argument("--drop", action="append", metavar="P#", help="remove a piece (do not cut it)")
    d.add_argument("--undrop", action="append", metavar="P#")
    d.add_argument("--fill", action="append", metavar="H#", help="make a cutout solid metal")
    d.add_argument("--unfill", action="append", metavar="H#")
    d.add_argument("--bridge", action="append", metavar="LETTER", help="add a bridge option shown in the last preview")
    d.add_argument("--bridge-at", action="append", dest="bridge_at", metavar="x1,y1,x2,y2", help="bridge between two points in finished-part units")
    d.add_argument("--remove-bridge", action="append", dest="remove_bridge", metavar="N")
    d.add_argument("--reset-edits", action="store_true", dest="reset_edits")
    d.add_argument("--keep-slivers", action="store_true", dest="keep_slivers", help="keep specks of metal that would normally be dropped")
    d.set_defaults(fn=cmd_design)

    g = sub.add_parser("gcode", help="write the Mach3 program")
    g.add_argument("--job", required=True)
    g.add_argument("--feed", type=float, help="cut feed, units per minute")
    g.add_argument("--pierce-delay", type=float, dest="pierce_delay", help="seconds")
    g.add_argument("--dwell-ms", action="store_const", const=True, dest="dwell_ms", help="write G4 P in milliseconds")
    g.add_argument("--lead-in", type=float, dest="lead_in")
    g.add_argument("--overcut", type=float)
    g.add_argument("--simplify", type=float, help="path simplification tolerance")
    g.add_argument("--origin-margin", type=float, dest="origin_margin", help="distance from X0 Y0 to the part")
    g.add_argument("--name", help="program name, also the .nc file name")
    g.add_argument("--no-comments", action="store_const", const=False, dest="comments")
    g.set_defaults(fn=cmd_gcode)

    mk = sub.add_parser("make", help="draw a shape and/or text instead of starting from a picture")
    mk.add_argument("--job", required=True)
    mk.add_argument("--units", choices=["in", "mm"], default="in")
    mk.add_argument("--shape", choices=["circle", "rect", "ring", "none"], default="none")
    mk.add_argument("--size", help="circle diameter or square side, or W,H for a rectangle")
    mk.add_argument("--corner", type=float, default=0.0, help="corner radius for rect")
    mk.add_argument("--ring-width", dest="ring_width", type=float, default=1.0)
    mk.add_argument("--text", help="text; use | between lines")
    mk.add_argument("--font", default="sans-bold", help="sans, sans-bold, serif-bold, mono-bold, arial, arial-bold, times, courier, or a .ttf path")
    mk.add_argument("--text-height", dest="text_height", type=float, default=1.0, help="capital letter height in units")
    mk.add_argument("--text-mode", dest="text_mode", choices=["cut", "raised"], default="cut", help="cut: text removed from the shape; raised: text is metal")
    mk.add_argument("--text-at", dest="text_at", type=lambda v: [float(x) for x in v.split(",")], default=[0.0, 0.0], help="x,y offset of the text centre from the shape centre")
    mk.add_argument("--line-gap", dest="line_gap", type=float, default=0.25, help="gap between text lines in units")
    mk.add_argument("--hole", action="append", metavar="DIA,X,Y", help="round hole: diameter and centre offset from the shape centre")
    mk.add_argument("--bar", type=float, default=0.0, help="raised text only: thickness of a bar under the letters that joins them into one part")
    mk.set_defaults(fn=cmd_make)

    e = sub.add_parser("edit", help="edit the cleaned drawing; coordinates are fractions 0-1 of width and height, read off the preview grid")
    e.add_argument("--job", required=True)
    e.add_argument("--erase", action="append", metavar="x0,y0,x1,y1", help="erase a rectangle")
    e.add_argument("--erase-poly", dest="erase_poly", action="append", metavar='"x,y x,y x,y"', help="erase a polygon")
    e.add_argument("--erase-circle", dest="erase_circle", action="append", metavar="cx,cy,r", help="erase a circle (r as a fraction of width)")
    e.add_argument("--keep-rect", dest="keep_rect", action="append", metavar="x0,y0,x1,y1", help="erase everything outside a rectangle")
    e.add_argument("--keep-poly", dest="keep_poly", action="append", metavar='"x,y x,y x,y"', help="erase everything outside a polygon")
    e.add_argument("--paint-rect", dest="paint_rect", action="append", metavar="x0,y0,x1,y1", help="add ink in a rectangle")
    e.add_argument("--paint-poly", dest="paint_poly", action="append", metavar='"x,y x,y x,y"', help="add ink in a polygon")
    e.add_argument("--paint-line", dest="paint_line", action="append", metavar='"x,y x,y[:width]"', help="draw a line (width as a fraction of width)")
    e.add_argument("--smooth-region", dest="smooth_region", action="append", metavar="x0,y0,x1,y1[:px]", help="knock nubs and nicks off inside a rectangle")
    e.add_argument("--smooth", type=float, default=0, help="smooth everything by this many px")
    e.add_argument("--thicken", type=float, default=0, help="grow all ink by px")
    e.add_argument("--thin", type=float, default=0, help="shrink all ink by px")
    e.add_argument("--fill-holes-under", dest="fill_holes_under", type=int, default=0, help="fill enclosed white areas smaller than N px")
    e.add_argument("--fill-all-holes", dest="fill_all_holes", action="store_true", help="fill every enclosed white area (outline becomes solid)")
    e.add_argument("--outline", type=float, default=0, help="keep only an outline this many px wide (solid becomes line art)")
    e.add_argument("--invert", action="store_true")
    e.add_argument("--mirror", action="store_true", help="mirror left-right (for cutting from the back)")
    e.add_argument("--rotate", type=float, default=0, help="degrees counter-clockwise")
    e.set_defaults(fn=cmd_edit)

    ad = sub.add_parser("adopt", help="use a black-and-white image you produced yourself as the cleaned drawing (black = ink)")
    ad.add_argument("image")
    ad.add_argument("--job", required=True)
    ad.add_argument("--threshold", type=int, default=128)
    ad.add_argument("--invert", action="store_true")
    ad.add_argument("--no-auto-invert", dest="auto_invert", action="store_false", help="do not flip when the image is mostly black")
    ad.set_defaults(fn=cmd_adopt)

    s = sub.add_parser("show", help="print the job state")
    s.add_argument("--job", required=True)
    s.set_defaults(fn=cmd_show)

    v = sub.add_parser("version", help="print the skill version")
    v.set_defaults(fn=lambda a: print(f"plasma-path {__version__}"))

    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
