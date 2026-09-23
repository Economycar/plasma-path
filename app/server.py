"""Local web UI for the raster -> plasma G-code workflow.

Run:  .venv/bin/python app/server.py   then open http://127.0.0.1:5077
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from functools import lru_cache

from flask import Flask, jsonify, request, send_from_directory

sys.path.insert(0, os.path.dirname(__file__))
import pipeline as P  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "out")
UPLOAD_DIR = os.path.join(ROOT, "uploads")
IMAGES_DIR = os.path.join(ROOT, "images")
IMAGE_EXT = (".webp", ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff")

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), "static"), static_url_path="")

DEFAULTS = {
    "source": "",
    # preprocess
    "threshold": 128, "invert": False, "speck": 30, "remove_frame": True,
    "bottom_band": 0.05, "top_band": 0.0, "blur": 0,
    # trace
    "turdsize": 10, "alphamax": 1.0, "opttolerance": 0.2,
    # design
    "mode": "silhouette", "auto_bridges": 2, "bridge_width_in": 0.2,
    "stencil_margin_in": 0.5, "bridges": [],
    # size / kerf
    "units": "in", "height": 12.0, "kerf": 0.055, "min_material": 0.1,
    "margin": 0.5, "bed_w": 24.0, "bed_h": 24.0,
    # gcode
    "feed": 60.0, "pierce_delay": 0.5, "dwell_ms": False, "lead_in": 0.1,
    "overcut": 0.05, "simplify": 0.003, "disabled": [], "comments": True,
    "name": "part",
}


def list_images():
    out = []
    for d in (IMAGES_DIR, ROOT, UPLOAD_DIR):
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.lower().endswith(IMAGE_EXT):
                out.append(os.path.relpath(os.path.join(d, f), ROOT))
    return out


def resolve(rel):
    p = os.path.abspath(os.path.join(ROOT, rel))
    if not p.startswith(ROOT + os.sep) or not os.path.isfile(p):
        raise ValueError("bad source path")
    return p


@lru_cache(maxsize=8)
def _gray(path, mtime):
    return P.load_gray(path)


@lru_cache(maxsize=32)
def _stage_trace(path, mtime, threshold, invert, speck, remove_frame, bottom_band, top_band, blur,
                 turdsize, alphamax, opttolerance):
    gray = _gray(path, mtime)
    ink, removed = P.preprocess(gray, threshold, invert, speck, remove_frame, bottom_band, top_band, blur)
    svg, dxf = P.trace(ink, turdsize, alphamax, opttolerance)
    ink_geom = P.svg_to_ink(svg, ink.shape[0])
    return gray, ink, removed, svg, dxf, ink_geom


def params_from(req):
    p = dict(DEFAULTS)
    p.update({k: v for k, v in (req or {}).items() if k in DEFAULTS})
    return p


def run(p):
    t0 = time.time()
    path = resolve(p["source"])
    mtime = os.path.getmtime(path)
    gray, ink, removed, svg, dxf, ink_geom = _stage_trace(
        path, mtime, float(p["threshold"]), bool(p["invert"]), int(p["speck"]), bool(p["remove_frame"]),
        float(p["bottom_band"]), float(p["top_band"]), int(p["blur"]),
        int(p["turdsize"]), float(p["alphamax"]), float(p["opttolerance"]))
    H, W = ink.shape
    units = p["units"]
    # scale: pixels -> machine units, from requested art height
    minx, miny, maxx, maxy = ink_geom.bounds
    art_h_px = max(1.0, maxy - miny)
    scale = float(p["height"]) / art_h_px
    px = lambda v: float(v) / scale  # machine units -> px

    kept0 = P.base_kept(ink_geom, p["mode"], px(p["stencil_margin_in"]))
    kept, bridges = P.add_bridges(kept0, p["bridges"], int(p["auto_bridges"]), px(p["bridge_width_in"]))

    g, off, cuts, rapids, info = P.build_toolpath(
        kept, scale=scale, H_px=H, margin=float(p["margin"]), kerf=float(p["kerf"]),
        lead_in=float(p["lead_in"]), overcut=float(p["overcut"]), simplify_tol=float(p["simplify"]),
        disabled_ids=p["disabled"], min_material=float(p["min_material"]))
    if info["bounds"][2] > float(p["bed_w"]) or info["bounds"][3] > float(p["bed_h"]):
        info["warnings"].append(
            f"Part extends to {info['bounds'][2]:.2f} x {info['bounds'][3]:.2f}, beyond the {p['bed_w']:g} x {p['bed_h']:g} bed.")
    nc = P.gcode(cuts, rapids, units=units, feed=float(p["feed"]), pierce_delay=float(p["pierce_delay"]),
                 dwell_ms=bool(p["dwell_ms"]), program_name=p["name"], comments=bool(p["comments"]))
    rapid_ipm = 200.0 if units == "in" else 5000.0
    est = info["cut_length"] / float(p["feed"]) + info["rapid_length"] / rapid_ipm + \
        info["pierces"] * (float(p["pierce_delay"]) + 1.0) / 60.0

    # machine -> pixel transform for the preview overlay
    from shapely import affinity
    gx, gy, _, _ = affinity.affine_transform(kept, [scale, 0, 0, -scale, 0, H * scale]).bounds
    def m2px(pt):
        x, y = pt
        return [(x - float(p["margin"]) + gx) / scale, H - (y - float(p["margin"]) + gy) / scale]

    return {
        "image": {"w": W, "h": H, "gray": P.gray_png_b64(gray), "clean": P.png_b64(ink)},
        "removed": removed,
        "trace": {"paths": len(ink_geom.geoms), "holes": sum(len(q.interiors) for q in ink_geom.geoms),
                  "svg_bytes": len(svg), "ink_px": int((ink > 0).sum())},
        "scale": scale,
        "design": {"kept": P.multi_to_json(kept), "bridges": [list(b.exterior.coords) for b in bridges],
                   "pieces": len(kept.geoms), "mode_help": P.MODES[p["mode"]]},
        "toolpath": {
            "cuts": [{"id": c["id"], "type": c["type"], "pts_px": [m2px(q) for q in c["pts"]]} for c in cuts],
            "rapids": [[m2px(a), m2px(b)] for a, b in rapids],
            "info": info, "est_minutes": est,
        },
        "gcode": nc,
        "ms": int((time.time() - t0) * 1000),
        "_artifacts": {"svg": svg, "dxf": dxf, "ink": ink, "kept": kept, "bridges": bridges,
                       "cuts": cuts, "rapids": rapids, "size": info["size"], "W": W, "H": H},
    }


@app.get("/api/images")
def api_images():
    return jsonify({"images": list_images(), "defaults": DEFAULTS})


@app.post("/api/upload")
def api_upload():
    f = request.files["file"]
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    name = re.sub(r"[^A-Za-z0-9._-]", "_", f.filename or "upload.png")
    dest = os.path.join(UPLOAD_DIR, name)
    f.save(dest)
    return jsonify({"path": os.path.relpath(dest, ROOT)})


@app.post("/api/process")
def api_process():
    try:
        p = params_from(request.get_json(force=True))
        r = run(p)
        r.pop("_artifacts")
        return jsonify(r)
    except Exception as e:  # surface to the UI
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 400


@app.post("/api/save")
def api_save():
    body = request.get_json(force=True)
    p = params_from(body.get("params"))
    want = set(body.get("outputs") or [])
    r = run(p)
    a = r["_artifacts"]
    os.makedirs(OUT_DIR, exist_ok=True)
    base = re.sub(r"[^A-Za-z0-9._-]", "_", p["name"] or "part")
    saved = []
    def w(suffix, text, mode="w"):
        fp = os.path.join(OUT_DIR, base + suffix)
        with open(fp, mode) as fh:
            fh.write(text)
        saved.append(os.path.relpath(fp, ROOT))
    if "clean" in want:
        import cv2
        fp = os.path.join(OUT_DIR, base + "_clean.png")
        cv2.imwrite(fp, 255 - a["ink"])
        saved.append(os.path.relpath(fp, ROOT))
    if "svg" in want:
        w("_trace.svg", a["svg"])
    if "dxf" in want:
        w("_trace.dxf", a["dxf"])
    if "design" in want:
        w("_design.svg", P.design_svg(a["kept"], a["bridges"], a["W"], a["H"]))
    if "toolpath" in want:
        w("_toolpath.svg", P.paths_svg(a["cuts"], a["rapids"], a["size"], p["units"]))
    if "gcode" in want:
        w(".nc", r["gcode"])
    if "settings" in want:
        w("_settings.json", json.dumps(p, indent=2))
    return jsonify({"saved": saved})


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5077))
    print(f"open http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)
