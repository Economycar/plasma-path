# 02. Workflow: raster to plasma G-code

Six stages, each producing something you can inspect before moving on. The app
in `app/` implements all six; `app/pipeline.py` is the geometry, with no web
code in it, so it can be driven from a script too.

## Stage 1. Preprocess

Flatten alpha to white, greyscale, optional blur, threshold. Remove specks,
the border frame (any component spanning more than 80 % of the image), and
optional top or bottom bands (watermarks, captions). Output: a 1-bit ink mask.

## Stage 2. Trace

potrace turns the mask into filled Bézier regions. Filled regions are the right
representation for plasma: the torch removes material, it cannot draw a line.
Centreline tracing (autotrace) was rejected for that reason.

potrace's SVG uses 1/10 px units with a flipped Y transform; `svg_to_ink`
undoes that and samples each curve at 1 px spacing into Shapely polygons.
Nesting is resolved even-odd: rings at even depth are shells, odd depth are
holes.

## Stage 3. Cut design

The step that is not automatic. The ink of a line drawing forms closed loops,
and a plasma torch cannot cut a loop without freeing what is inside it. Three
answers, chosen per job:

| Mode | Metal is | Removed is | Needs bridges |
|---|---|---|---|
| Silhouette plate | outer shape, filled | enclosed marks (eyes, nose, tuft) as holes | rarely |
| Line art | the ink strokes | all white | yes: loose marks get tabs to the main body |
| Stencil | a rectangular plate minus the ink | the ink, as slots | yes: enclosed regions get bridges across the strokes |

Everything downstream works on one object, `kept`: a multipolygon of what
stays. A bridge is simply material added to `kept`: a rectangle of the chosen
width between the nearest points of two disconnected pieces. That single
definition covers both tabs (line art) and bridges (stencil).

Auto-bridging: sort pieces by area, take the largest as attached, then for each
remaining island place N bridges from evenly spaced points on its boundary to
the nearest point of the already-attached union. Attaching to the growing
union, not just the main piece, keeps bridges short (the hand gap bridges to
the body, not out to the plate). Manual bridges: a click connects the two
pieces nearest the click.

The app reports the piece count. One piece means nothing drops out.

## Stage 4. Scale and kerf

Art height (user input) over the ink bounding-box height in pixels gives the
scale. Width follows. Machine space is Y-up, so pixel Y is flipped, and the
part is translated to sit a margin from the origin.

Kerf offset is one operation: buffer `kept` outward by half the kerf. The
exterior rings of the result are the outer torch paths, the interior rings are
the hole paths. Holes narrower than the kerf vanish in the buffer and are
reported as lost. Thin material is checked with an erode-then-dilate test.

## Stage 5. Toolpath and G-code

- Direction: exterior rings clockwise, holes counter-clockwise (Y-up). With a
  clockwise plasma swirl this puts the square edge on the part side.
- Order: all holes first, then outers, nearest-neighbour from the origin.
- Pierce and lead-in: try start vertices around the ring until one has a
  lead-in start point that lies in scrap (outside the part for outers, inside
  the hole for holes). The lead-in comes in perpendicular from the left of the
  travel direction, which is the scrap side for both ring types. Lead-in
  length halves until it fits, so small holes get short lead-ins.
- Overcut: continue past the closing point by a short distance.
- Simplify: Douglas-Peucker at the chosen tolerance to keep the G1 count sane
  for Mach3's look-ahead.

Mach3 dialect for the original CrossFire:

    G20            inch (G21 for mm)
    G90 G94 G40 G17 G64
    M5
    F60
    G0 X.. Y..     rapid to pierce point
    M3             torch on
    G4 P0.5        pierce delay (seconds, or ms if Mach3 is configured that way)
    G1 X.. Y..     lead-in, contour, overcut
    M5             torch off
    ...
    G0 X0 Y0
    M30

No Z moves, no THC. Torch height is set by hand before the run.

## Stage 6. Verify and save

The preview shows the material, bridges, torch paths, rapids and numbered
pierce points over the original image. Save writes any subset of: cleaned
PNG, trace SVG, trace DXF, design SVG with bridges, toolpath SVG in machine
units, the `.nc` file, and a settings JSON that reproduces the job.

Still to do: a dry run on the table with the torch disabled, then a cut in
scrap. Nothing has been cut yet.
