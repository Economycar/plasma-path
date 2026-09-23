"""Raster -> vector -> cut design -> kerf-offset toolpath -> Mach3 G-code.

All geometry is kept in Shapely.  Image space is pixels, y-down.  Machine space
is inches (or mm), y-up, part placed at a positive margin from the origin.
"""
from __future__ import annotations

import base64
import io
import math
import os
import subprocess
import tempfile

import cv2
import numpy as np
from shapely import affinity
from shapely.geometry import (LineString, MultiPolygon, Point, Polygon, box)
from shapely.geometry.polygon import orient
from shapely.ops import nearest_points, unary_union
from svgpathtools import parse_path
import re


# --------------------------------------------------------------------------
# 1. Preprocess
# --------------------------------------------------------------------------

def load_gray(path: str) -> np.ndarray:
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"cannot read {path}")
    if img.ndim == 2:
        return img
    if img.shape[2] == 4:  # flatten alpha onto white
        a = img[:, :, 3:4] / 255.0
        img = (img[:, :, :3] * a + 255 * (1 - a)).astype(np.uint8)
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def preprocess(gray: np.ndarray, threshold=128, invert=False, speck=30,
               remove_frame=True, bottom_band=0.0, top_band=0.0, blur=0):
    """Return (ink mask uint8 0/255, list of removed components)."""
    g = gray
    if blur and blur > 0:
        k = int(blur) * 2 + 1
        g = cv2.GaussianBlur(g, (k, k), 0)
    mode = cv2.THRESH_BINARY if invert else cv2.THRESH_BINARY_INV
    _, ink = cv2.threshold(g, int(threshold), 255, mode)
    H, W = ink.shape
    n, lab, stats, _ = cv2.connectedComponentsWithStats(ink, 8)
    keep = np.zeros_like(ink)
    removed = []
    for i in range(1, n):
        x, y, w, h, area = (int(v) for v in stats[i])
        tag = None
        if remove_frame and (w > 0.8 * W or h > 0.8 * H) and area < 0.1 * W * H:
            tag = "frame"
        elif bottom_band > 0 and y > (1 - bottom_band) * H:
            tag = "bottom band"
        elif top_band > 0 and y + h < top_band * H:
            tag = "top band"
        elif area < speck:
            tag = "speck"
        if tag:
            removed.append({"bbox": [x, y, w, h], "area": area, "reason": tag})
        else:
            keep[lab == i] = 255
    return keep, removed


def png_b64(mask_ink_255: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", 255 - mask_ink_255)
    return "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode()


def gray_png_b64(gray: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", gray)
    return "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode()


# --------------------------------------------------------------------------
# 2. Trace (potrace)
# --------------------------------------------------------------------------

def trace(ink: np.ndarray, turdsize=10, alphamax=1.0, opttolerance=0.2):
    """Run potrace, return (svg_text, dxf_text)."""
    with tempfile.TemporaryDirectory() as d:
        pbm = os.path.join(d, "in.pbm")
        cv2.imwrite(pbm, 255 - ink)  # PBM: black pixels = ink
        common = ["potrace", pbm, "--turdsize", str(int(turdsize)),
                  "--alphamax", str(alphamax), "--opttolerance", str(opttolerance)]
        svg = os.path.join(d, "out.svg")
        dxf = os.path.join(d, "out.dxf")
        subprocess.run(common + ["-s", "-o", svg], check=True, capture_output=True)
        subprocess.run(common + ["-b", "dxf", "-o", dxf], check=True, capture_output=True)
        return open(svg).read(), open(dxf).read()


def svg_to_ink(svg_text: str, H: int, step_px=1.0):
    """Convert potrace SVG into a Shapely MultiPolygon in pixel space (y-down).

    potrace writes coordinates in 1/10 px with a translate(0,H) scale(.1,-.1)
    group transform; we undo that by hand.
    """
    rings = []
    for d in re.findall(r'd="([^"]+)"', svg_text):
        path = parse_path(d.replace("\n", " "))
        for sub in path.continuous_subpaths():
            pts = []
            for seg in sub:
                L = seg.length()
                n = max(2, int(math.ceil(L / (step_px * 10))))  # 1/10 px units
                for k in range(n):
                    z = seg.point(k / n)
                    pts.append((0.1 * z.real, H - 0.1 * z.imag))
            if len(pts) >= 3:
                rings.append(pts)
    return rings_to_multipolygon(rings)


def rings_to_multipolygon(rings) -> MultiPolygon:
    """Even-odd nesting: depth-even rings are shells, depth-odd are holes."""
    polys = [Polygon(r).buffer(0) for r in rings]
    polys = [p if p.geom_type == "Polygon" else max(p.geoms, key=lambda q: q.area)
             for p in polys if not p.is_empty]
    order = sorted(range(len(polys)), key=lambda i: -polys[i].area)
    depth, parent = {}, {}
    for idx, i in enumerate(order):
        pt = polys[i].representative_point()
        containers = [j for j in order[:idx] if polys[j].contains(pt)]
        depth[i] = len(containers)
        parent[i] = min(containers, key=lambda j: polys[j].area) if containers else None
    result = []
    for i in order:
        if depth[i] % 2 == 0:
            holes = [polys[j].exterior.coords for j in order
                     if parent.get(j) == i and depth[j] % 2 == 1]
            result.append(Polygon(polys[i].exterior.coords, holes).buffer(0))
    return as_multi(unary_union(result))


def as_multi(g) -> MultiPolygon:
    if g.is_empty:
        return MultiPolygon([])
    if g.geom_type == "Polygon":
        return MultiPolygon([g])
    if g.geom_type == "MultiPolygon":
        return g
    return MultiPolygon([p for p in getattr(g, "geoms", []) if p.geom_type == "Polygon"])


# --------------------------------------------------------------------------
# 3. Cut design (what is metal, what is removed)
# --------------------------------------------------------------------------

MODES = {
    "silhouette": "Silhouette plate: outer shape is solid metal, enclosed ink marks (eyes, nose) become holes.",
    "lineart":    "Line art: the ink lines ARE the metal, all white is removed. Separate marks need tabs.",
    "stencil":    "Stencil: the ink lines are cut out of a rectangular plate. Enclosed regions need bridges.",
}


def silhouette(ink: MultiPolygon) -> MultiPolygon:
    filled = [Polygon(p.exterior.coords) for p in ink.geoms]
    filled_sorted = sorted(filled, key=lambda p: -p.area)
    outer, islands = [], []
    for p in filled_sorted:
        pt = p.representative_point()
        if any(o.contains(pt) for o in outer):
            islands.append(p)
        else:
            outer.append(p)
    kept = unary_union(outer)
    if islands:
        # subtract the actual ink shape of each island (with its own holes)
        island_ink = [q for q in ink.geoms if any(i.contains(q.representative_point()) for i in islands)]
        kept = kept.difference(unary_union(island_ink))
    return as_multi(kept)


def base_kept(ink: MultiPolygon, mode: str, stencil_margin_px: float) -> MultiPolygon:
    if mode == "silhouette":
        return silhouette(ink)
    if mode == "lineart":
        return ink
    if mode == "stencil":
        minx, miny, maxx, maxy = ink.bounds
        m = stencil_margin_px
        return as_multi(box(minx - m, miny - m, maxx + m, maxy + m).difference(ink))
    raise ValueError(mode)


def _bridge(p: Point, q: Point, width: float) -> Polygon:
    """Rectangle of `width` from p to q, extended a little past each end."""
    dx, dy = q.x - p.x, q.y - p.y
    L = math.hypot(dx, dy)
    if L < 1e-6:
        return p.buffer(width / 2)
    ux, uy = dx / L, dy / L
    ext = width * 0.6
    line = LineString([(p.x - ux * ext, p.y - uy * ext), (q.x + ux * ext, q.y + uy * ext)])
    return line.buffer(width / 2, cap_style=2)


def add_bridges(kept: MultiPolygon, manual_pts, auto_per_island: int, width: float):
    """Bridges are *material* added between disconnected pieces of `kept`."""
    bridges = []
    # ---- automatic: connect each island to the largest piece
    if auto_per_island > 0 and len(kept.geoms) > 1:
        pieces = sorted(kept.geoms, key=lambda p: -p.area)
        attached = pieces[0]  # grows as islands are connected, so each island
        for isl in pieces[1:]:  # bridges to its nearest already-attached neighbour
            ring = isl.exterior
            n = int(auto_per_island)
            new = []
            for k in range(n):
                c = ring.interpolate((k + 0.5) / n, normalized=True)
                _, q = nearest_points(c, attached)
                new.append(_bridge(c, q, width))
            bridges += new
            attached = unary_union([attached, isl] + new)
    # ---- manual clicks: connect the two nearest pieces around the click
    for xy in manual_pts or []:
        c = Point(xy["x"], xy["y"])
        pieces = sorted(kept.geoms, key=lambda p: p.distance(c))
        if len(pieces) < 2:
            continue
        a, b = pieces[0], pieces[1]
        pa = nearest_points(c, a)[1]
        pb = nearest_points(c, b)[1]
        bridges.append(_bridge(pa, pb, width))
    if bridges:
        kept = as_multi(unary_union([kept, unary_union(bridges)]))
    return kept, bridges


# --------------------------------------------------------------------------
# 4. Toolpath (kerf offset, ordering, lead-ins) and G-code
# --------------------------------------------------------------------------

def to_machine(g, scale, H_px, margin):
    """pixels y-down -> machine units y-up, translated to a margin from origin."""
    g = affinity.affine_transform(g, [scale, 0, 0, -scale, 0, H_px * scale])
    minx, miny, _, _ = g.bounds
    return affinity.translate(g, margin - minx, margin - miny)


def _ring_coords(ring):
    c = list(ring.coords)
    if c[0] == c[-1]:
        c = c[:-1]
    return c


def _pick_start(coords, scrap_test, lead_in):
    """Find a start vertex whose lead-in start point lies in scrap."""
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


def build_toolpath(kept: MultiPolygon, *, scale, H_px, margin, kerf, lead_in,
                   overcut, simplify_tol, disabled_ids, min_material):
    warnings = []
    g = to_machine(kept, scale, H_px, margin)
    pieces = len(g.geoms)
    if pieces > 1:
        warnings.append(f"{pieces} separate pieces: {pieces - 1} will drop out of the sheet. Add bridges.")
    holes_before = sum(len(p.interiors) for p in g.geoms)
    off = as_multi(g.buffer(kerf / 2, join_style=1))
    if simplify_tol > 0:
        off = as_multi(off.simplify(simplify_tol, preserve_topology=True))
    holes_after = sum(len(p.interiors) for p in off.geoms)
    if holes_after < holes_before:
        warnings.append(f"{holes_before - holes_after} hole(s) narrower than the kerf were lost.")
    if min_material > 0:
        thin = g.buffer(-min_material / 2).buffer(min_material / 2)
        lost = g.area - thin.area
        if lost > min_material * min_material * 4:
            warnings.append(f"Some material is thinner than {min_material:g} (area {lost:.3f} sq units). It may burn away.")

    # enumerate rings with stable ids, enforce direction
    rings = []
    for pi, poly in enumerate(sorted(off.geoms, key=lambda p: (round(p.centroid.y, 3), round(p.centroid.x, 3)))):
        poly = orient(poly, -1.0)  # exterior CW, holes CCW (y-up)
        for hi, hole in enumerate(sorted(poly.interiors, key=lambda r: (round(r.centroid.y, 3), round(r.centroid.x, 3)))):
            rings.append({"id": f"hole-{pi}-{hi}", "type": "hole", "coords": _ring_coords(hole),
                          "poly": Polygon(hole)})
        rings.append({"id": f"outer-{pi}", "type": "outer", "coords": _ring_coords(poly.exterior),
                      "poly": Polygon(poly.exterior)})

    off_union = unary_union(off)
    for r in rings:
        r["length"] = LineString(r["coords"] + [r["coords"][0]]).length
        r["enabled"] = r["id"] not in (disabled_ids or [])
        if r["type"] == "hole":
            test = lambda s, hp=r["poly"]: hp.contains(Point(s))
        else:
            test = lambda s: not off_union.buffer(kerf / 4).contains(Point(s))
        k, start, L = _pick_start(r["coords"], test, lead_in)
        r["coords"] = r["coords"][k:] + r["coords"][:k]
        r["pierce"] = start
        r["lead_len"] = L

    # order: holes first, then outers, nearest-neighbour from origin
    def nn(items, start):
        out, cur = [], start
        pool = list(items)
        while pool:
            nxt = min(pool, key=lambda r: math.dist(cur, r["pierce"]))
            pool.remove(nxt)
            out.append(nxt)
            cur = nxt["coords"][0]
        return out
    active = [r for r in rings if r["enabled"]]
    ordered = nn([r for r in active if r["type"] == "hole"], (0, 0))
    ordered += nn([r for r in active if r["type"] == "outer"], ordered[-1]["coords"][0] if ordered else (0, 0))

    # build cut segments with overcut
    cuts, rapids, cur = [], [], (0.0, 0.0)
    for r in ordered:
        pts = [r["pierce"]] + r["coords"] + [r["coords"][0]]
        # overcut: continue along the ring past the closing point
        rem = overcut
        i = 0
        while rem > 0 and i < len(r["coords"]) - 1:
            a, b = r["coords"][i], r["coords"][i + 1]
            d = math.dist(a, b)
            if d >= rem:
                t = rem / d
                pts.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
                rem = 0
            else:
                pts.append(b)
                rem -= d
            i += 1
        rapids.append([cur, r["pierce"]])
        cuts.append({"id": r["id"], "type": r["type"], "pts": pts})
        cur = pts[-1]
    rapids.append([cur, (0.0, 0.0)])

    bounds = off.bounds
    info = {
        "pieces": pieces,
        "rings": [{k: r[k] for k in ("id", "type", "length", "enabled")} for r in rings],
        "bounds": bounds,
        "size": [bounds[2] - bounds[0], bounds[3] - bounds[1]],
        "cut_length": sum(LineString(c["pts"]).length for c in cuts),
        "rapid_length": sum(math.dist(a, b) for a, b in rapids),
        "pierces": len(cuts),
        "segments": sum(len(c["pts"]) - 1 for c in cuts),
        "warnings": warnings,
    }
    return g, off, cuts, rapids, info


def gcode(cuts, rapids, *, units, feed, pierce_delay, dwell_ms, rapid_feed=None,
          program_name="part", comments=True):
    f = (lambda v: f"{v:.4f}") if units == "in" else (lambda v: f"{v:.3f}")
    lines = []
    c = (lambda s: f"({s})") if comments else (lambda s: None)
    def emit(s):
        if s is not None:
            lines.append(s)
    emit(c(f"{program_name} - generated for Langmuir CrossFire / Mach3, no Z axis"))
    emit(c(f"units {units}, feed {feed:g}, pierce delay {pierce_delay:g}s, {len(cuts)} pierces"))
    emit("G20" if units == "in" else "G21")
    emit("G90 G94 G40 G17 G64")
    emit("M5")
    emit(f"F{feed:g}")
    dwell = f"G4 P{int(pierce_delay * 1000)}" if dwell_ms else f"G4 P{pierce_delay:g}"
    for i, (cut, rap) in enumerate(zip(cuts, rapids)):
        pts = cut["pts"]
        emit("")
        emit(c(f"cut {i + 1}: {cut['type']} {cut['id']}"))
        emit(f"G0 X{f(pts[0][0])} Y{f(pts[0][1])}")
        emit("M3")
        emit(dwell)
        for x, y in pts[1:]:
            emit(f"G1 X{f(x)} Y{f(y)}")
        emit("M5")
    emit("")
    emit(c("return home"))
    emit("G0 X0 Y0")
    emit("M30")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# 5. Serialisation helpers for the UI and for saved files
# --------------------------------------------------------------------------

def multi_to_json(g: MultiPolygon):
    return [{"exterior": list(p.exterior.coords), "holes": [list(h.coords) for h in p.interiors]}
            for p in g.geoms]


def paths_svg(cuts, rapids, size, units):
    """Toolpath as an SVG in machine units (y flipped back for display)."""
    w, h = size
    sw = 0.01 if units == "in" else 0.25
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.3f}{units if units=="in" else "mm"}" '
             f'height="{h:.3f}{units if units=="in" else "mm"}" viewBox="0 0 {w:.4f} {h:.4f}">',
             f'<g transform="translate(0,{h:.4f}) scale(1,-1)" fill="none" stroke-width="{sw}">']
    for a, b in rapids:
        parts.append(f'<line x1="{a[0]:.4f}" y1="{a[1]:.4f}" x2="{b[0]:.4f}" y2="{b[1]:.4f}" stroke="#888" stroke-dasharray="{sw*4},{sw*4}"/>')
    for c in cuts:
        d = "M " + " L ".join(f"{x:.4f},{y:.4f}" for x, y in c["pts"])
        parts.append(f'<path d="{d}" stroke="{"#d33" if c["type"]=="outer" else "#36c"}"/>')
    parts.append("</g></svg>")
    return "\n".join(parts)


def design_svg(kept: MultiPolygon, bridges, W, H):
    def poly_d(p):
        d = "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in p.exterior.coords) + " Z"
        for hole in p.interiors:
            d += " M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in hole.coords) + " Z"
        return d
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
             '<rect width="100%" height="100%" fill="white"/>']
    for p in kept.geoms:
        parts.append(f'<path d="{poly_d(p)}" fill="#555" fill-rule="evenodd"/>')
    for b in bridges:
        parts.append(f'<path d="{poly_d(b)}" fill="#e6a100" opacity="0.8"/>')
    parts.append("</svg>")
    return "\n".join(parts)
