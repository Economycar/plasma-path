# 03. Plasma Path app guide

Start with `./run.sh`, open http://127.0.0.1:5077. Every control re-runs the
pipeline on change (about 100 to 200 ms) and redraws. Settings persist in the
browser. URL parameters override them, e.g. `?mode=stencil&height=10`.

Screenshots of each mode are in `screenshots/`.

## Layout

- **Header**: source image picker (lists `images/`, the project root and
  `uploads/`), Upload button, status with processing time.
- **Left column**: the six stage panels, collapsible.
- **Centre**: preview. Drag to pan, wheel to zoom, Fit to reset. Layer chips
  toggle Original, Cleaned, Material, Bridges, Cut paths, Rapids, Pierces.
  Status bar underneath: finished size, pieces, pierces, cut length, rapid
  length, segment count, estimated time, scale.
- **Right column**: warnings, the cut-path table, and the G-code with Copy.

## Panels

**1. Source and clean-up.** Threshold (slider), blur radius, speck size, ignore
bottom/top band as a fraction of image height, remove border frame, invert
for light-on-dark sources. Shows what was removed and why.

**2. Trace.** potrace's turdsize (drop blobs under N px²), alphamax (corner
threshold, 0 sharp to 1.33 smooth), opttolerance (curve fit tolerance). Shows
shape and enclosed-region counts.

**3. Cut design.** Mode radio (silhouette, line art, stencil). Auto bridges
per island, bridge width in machine units, stencil plate margin. "Add bridge
by clicking" toggles a crosshair; each click on the preview connects the two
nearest pieces. Manual bridges are listed with delete buttons; Clear manual
removes them all.

**4. Size and kerf.** Units, art height, kerf width, thin-material warning
threshold, margin from origin, bed size (warning only).

**5. G-code.** Feed, pierce delay, dwell-in-milliseconds toggle, lead-in,
overcut, simplify tolerance, comments on/off.

**6. Save.** Base name and checkboxes for each output. Files go to `out/` as
`<name>_clean.png`, `<name>_trace.svg`, `<name>_trace.dxf`,
`<name>_design.svg`, `<name>_toolpath.svg`, `<name>.nc`,
`<name>_settings.json`. Download .nc saves through the browser instead.

## Per-path control, as it stands

The cut-path table has one row per contour after kerf offset, tagged outer or
hole, with its length and its position in the cut order. Hover a row to
highlight it in the preview. Uncheck it to leave it out of the G-code; the
order renumbers. That is the only per-path control today. Direction,
lead-in, pierce point, kerf side and sequence are all global rules. What a
per-path override system would add is in `04-backlog.md`.

## Sizing, as it stands

Art height is the single input. The ink bounding box is scaled to that
height; width follows the image proportions. In stencil mode the plate is the
art box plus the margin on every side. Margin from origin moves the part;
bed size only warns. The status bar shows the resulting size and scale. There
is no stock rectangle, no bed outline in the preview, no width input and no
dimension callouts. Also in `04-backlog.md`.

## Warnings you may see

- *N separate pieces*: something will drop out. Raise auto bridges or click
  bridges in.
- *Hole(s) narrower than the kerf were lost*: a slot too thin to cut was
  dropped. Increase art height or accept.
- *Material thinner than X*: features that may burn away. Lower the threshold
  if you accept the risk, or scale up.
- *Part extends beyond the bed*: reduce height or margin.

## Useful defaults for the first 12 in test (a coloring-page style drawing)

| Setting | Value |
|---|---|
| Kerf | 0.055 in |
| Feed | 60 in/min |
| Pierce delay | 0.5 s |
| Lead-in / overcut | 0.10 / 0.05 in |
| Bridge width | 0.20 in |
| Auto bridges per island | 2 (stencil), 0 with manual tabs (line art) |
