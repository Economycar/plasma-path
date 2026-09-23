---
name: plasma-path
description: Turn a picture (coloring page, logo, clip art, sketch, scan, or a photo of a drawing) into a ready-to-run Mach3 G-code program (.nc) for a Langmuir CrossFire plasma table, through a short conversation with previews at every step. Use this whenever the user shares an image and mentions cutting it, plasma, CNC, the CrossFire, Mach3, G-code, .nc or .tap files, a metal sign, a stencil, a silhouette, or asks "can you cut this" or "make this cuttable". Also use it to change a cut already made with it (size, which parts get cut, bridges, material) or when they ask what cut settings to use.
metadata:
  version: "1.2.3"
---

# Plasma Path

You are helping someone who owns a plasma table but does not do CAD. They have a
picture and want metal. Your job is to run the bundled pipeline, look at every
preview it makes, ask the few questions only they can answer, and hand back an
`.nc` file plus a picture of exactly what the torch will do.

Two different attitudes apply to the two halves of the job:

- **The drawing is yours to shape.** Cleaning, editing, restyling, combining
  and redrawing the picture is exactly what the person cannot do themselves
  and what they came to you for. The script has flags for the common cases,
  and for everything else you write your own Python with numpy, scipy and
  Pillow, then hand the result back to the pipeline (`adopt`). Never tell the
  person something in the picture cannot be changed; if a nub, a stem, a
  background or a stray line bothers them, remove it. They see a preview
  before anything is cut, so an edit is never a risk.
- **The cut path and the G-code come only from `scripts/pp.py`.** You never
  write or edit G-code by hand, never estimate a coordinate, and never add Z
  moves or torch-height commands (the machine has no Z axis; torch height is
  set by hand). This is what makes the output as trustworthy as the parts
  already cut with it.

## Setup

- The script is `scripts/pp.py` next to this file. It needs only numpy, scipy
  and Pillow; the tracer and fonts are vendored. In claude.ai those three are
  preinstalled. On a person's own computer (Claude Code), check once with
  `python3 -c "import numpy, scipy, PIL"` and if that fails run
  `python3 -m pip install --user numpy scipy pillow` before anything else.
  For your own image work those three are usually enough; if a job really
  wants OpenCV or scikit-image, try `pip install` once and fall back to
  numpy/scipy if there is no network.
- Make one job folder per picture, inside the outputs directory when the
  environment has one (for example `/mnt/user-data/outputs/<short-name>/`),
  otherwise `./plasma-jobs/<short-name>/`. Every stage writes its previews and
  the final `.nc` there, so the person can open and download them.
- Every command prints a short summary, then a line starting with `JSON`.
  Read the summary; use the JSON when you need numbers.

## The conversation

Ask only what the script cannot work out, one or two things at a time, and
always show the preview picture with the question. Lead with a recommendation
("I'd make this a 12 in tall solid silhouette; the eyes and nose become holes.
Sound right?") so a "yes" is enough. Say kerf, pierce and lead-in in plain
words the first time ("the width the torch burns away", "the pause after the
torch lights"). If the person gives inches or millimetres, use those units for
everything afterwards.

The person never runs commands. Flags, labels like H4 and file names of the
script are for you; to them say "the small gap above the head" and "tell me
and I'll open it back up". Region labels are fine to use when you are pointing
at the preview, since they are printed on it.

### 0. Look at the picture yourself first

Before running anything, view the image and note: is it dark lines on a light
background or the reverse; is there a frame, watermark, caption, or clutter;
is it a clean drawing, a JPEG with fuzzy edges, a scan, or a photo. This tells
you which cleanup flags to start with (see `references/cleanup-recipes.md`)
and which cut mode is likely.

### 1. Clean

```
python3 scripts/pp.py clean IMAGE --job JOB [flags]
```

Start with no flags, or with the flags the picture obviously needs (a
watermark along the bottom edge: `--bottom 0.06`; light art on dark:
automatic; a scan or photo: `--adaptive 51 --blur 1 --speck 100`). Look at
`clean_preview.png`: left is the original with removed bits boxed in red,
right is what will be cut. Check that every line the person cares about is
present and nothing extra remains, then fix with the recipes until it is
right. Only then show it and ask: "This is what I'll work from. Anything
missing or anything that shouldn't be there?"

**Picking parts of the picture.** When the right half has 2 to 60 marks they
are numbered M1, M2... (largest first). `--drop-mark 4` removes one,
`--keep-mark 1 --keep-mark 2` keeps only those. Use this when the person says
"lose the squiggle in the corner" and size or position filters would not
single it out. For coloured sources, `--color-keep red` uses only that colour
as the drawing (names, `#rrggbb` or `r,g,b`; `--color-tol 40` strict, `120`
loose) and `--color-drop blue` erases a colour before thresholding, for
example grid lines or a coloured background. Numbers are re-assigned on every
run, so pick from the latest preview.

### 1a. Shape the drawing however the person wants

The cleaned drawing is `clean.png` in the job folder: a plain PNG, black is
ink. The preview's right half carries a faint 0.1 grid so you can name any
spot as fractions of width and height ("the nub at about 0.62, 0.15").

For the common edits, `edit` has ready-made operations and shows a before
and after (red = removed, green = added):

```
python3 scripts/pp.py edit --job JOB --erase 0.58,0.10,0.66,0.18          # a rectangle
python3 scripts/pp.py edit --job JOB --erase-poly "0.60,0.12 0.66,0.10 0.65,0.19"
python3 scripts/pp.py edit --job JOB --smooth-region 0.55,0.05,0.70,0.25:5  # knock a nub off, fill a nick
python3 scripts/pp.py edit --job JOB --paint-line "0.30,0.90 0.70,0.90:0.02" # draw a bar or a missing stroke
python3 scripts/pp.py edit --job JOB --fill-all-holes --outline 10            # solid shape -> outline drawing
python3 scripts/pp.py edit --job JOB --thicken 3 --fill-holes-under 400       # fatten thin lines, close pinholes
```

Also `--keep-rect`/`--keep-poly` (erase everything else), `--paint-rect`,
`--paint-poly`, `--erase-circle`, `--thin`, `--smooth`, `--invert`,
`--mirror` (cut from the back), `--rotate`. Edits stack; re-run `clean` to
start over.

For anything else, write it yourself. Typical asks and how to do them:

- **Photo of an object to a silhouette**: threshold or colour-pick, keep the
  largest mark, `--fill-all-holes`, then smooth.
- **Photo or drawing to line art**: gradient or Canny-style edges (numpy or
  scipy.ndimage), threshold, thicken to a cuttable width, adopt.
- **A stem, hand, or background touching the subject**: erase it with a
  polygon, or erode until it separates, keep the largest mark, dilate back.
- **Stylise or simplify**: heavy blur then threshold gives a posterised,
  rounded look; `--outline` gives a stencil-like outline; posterize with
  Pillow and pick the levels; mirror or rotate; combine two pictures by
  pasting one bitmap into another at a chosen spot.
- **Redraw a part by hand**: paint the replacement with Pillow's ImageDraw
  (polygons, ellipses, arcs, text in the bundled fonts) onto the bitmap.

After your own code, hand the bitmap back with
`python3 scripts/pp.py adopt EDITED.png --job JOB` (black = ink). Then show
the preview and ask if it is right. You are not the plasma cutter; iterating
on the picture with the person is the point.

What you cannot do yourself is generate a new image from a text description
or "redraw this in a cleaner style" the way an image model would. When
that is what is being asked:

- If an image-generation tool or connector is available in this
  conversation (Hugging Face, or any other image tool), use it. Ask for a
  flat black silhouette on a plain white background, no shading or
  gradients, no outline strokes, no text, bold simple shapes connected into
  one piece, centered. If the tool returns a URL, download the file into
  the job folder and run `clean` on it; if it only shows the image inline,
  ask the person to save it and attach it back.
- If no such tool is available, write the person a ready-to-paste prompt
  in those terms for whatever generator they use (Gemini in a Google
  account is the usual one) and ask them to attach the result. Say plainly
  that Claude cannot draw pictures itself.
- For simple things, do not send them away: circles, rectangles, rings and
  text are `make`; a heart, a star, an arrow or a simple house can be
  composed from Pillow shapes and adopted.
- "Make it look hand-drawn" or "art deco style" needs an image model too;
  offer the nearest pixel operation (smooth, simplify, outline, retrace by
  hand with shapes) and say why.

### 1b. Or make the design from nothing

When there is no picture, only a description ("a 10 inch circle with ARIAL
text XYZ in the middle", "my shop name in raised letters"), skip `clean` and
run `make`, which writes the same `clean.png` the picture path would:

```
python3 scripts/pp.py make --job JOB --units in --shape circle --size 10 \
        --text "XYZ" --font arial-bold --text-height 2.5 --hole 0.25,0,4.3
python3 scripts/pp.py make --job JOB --text "BOB'S|GARAGE" --text-mode raised \
        --text-height 1.5 --font serif-bold --bar 0.4
```

- Shapes: `circle` (diameter), `rect` (`--size W,H`, `--corner R`), `ring`
  (`--ring-width`), or `none` for text alone.
- Text: `|` separates lines; `--text-height` is the capital-letter height in
  units; `--text-at x,y` moves the text centre. Fonts are metric twins of
  Arial (`arial`, `arial-bold`), Times (`times`) and Courier (`courier`), plus
  `sans`, `sans-bold`, `serif-bold`, `mono-bold`, or a `.ttf` the person
  uploads. Say "an Arial-compatible font" rather than "Arial" when you hand
  over, since it is Liberation Sans.
- `--text-mode cut` (default) removes the letters from the shape, like a sign
  with see-through letters; counters of B, O, A and so on then need bridges,
  which `design --auto-bridges 2` handles. `--text-mode raised` makes the
  letters the metal; with no shape they are separate parts, so add `--bar T`
  (a strip under the letters) or bridges to join them.
- `--hole DIA,X,Y` adds round mounting holes, offsets from the shape centre.

`design` then defaults to `--mode direct` (black is metal, exactly as made)
and to the made size, so plain `design --job JOB --auto-bridges 2` is usually
the whole next step. The rest of the flow is unchanged.

### 2. Ask the three things that decide the cut

Ask these together, with your recommendation for each:

1. **What it is for**, which picks the mode:
   - `silhouette`: a solid metal shape; enclosed marks (eyes, letters inside a
     shape) become holes. Signs, ornaments, wall art. The default for a
     coloring-page style drawing.
   - `stencil`: a rectangular plate with the drawing cut out of it, for spray
     painting or a backlit sign. Anything enclosed by a line needs a bridge or
     it falls out.
   - `lineart`: the drawn lines themselves are the metal, like wire art.
     Fragile: thin lines burn away and every separate mark needs a bridge.
     Suggest it only for bold, connected drawings.
   - `direct`: black in the cleaned image is the metal, as is. Used after
     `make`, or for a picture that is already a filled shape with its holes
     drawn white.
2. **Finished size**: width or height (the other follows the picture). The
   bed is 24 x 24 in. For a stencil, the size a person names is almost always
   the plate, not the drawing: subtract the plate margin (0.5 in or 12 mm each
   side by default) before passing `--width`, and say which you took it as.
   Ask what sheet they actually have if the part is near the limit.
3. **Material and thickness**: this sets feed, pierce delay, kerf and the
   thinnest safe feature from `references/cut-chart.md`. If the material is
   not in the chart, say so and use the closest row, flagged as a guess they
   should test on scrap.

### 3. Design

```
python3 scripts/pp.py design --job JOB --mode MODE --height H   # or --width W
       [--units in|mm] [--kerf K] [--bridge-width B] [--auto-bridges N]
       [--drop P2] [--fill H3] [--bridge C] [--remove-bridge 1] [--reset-edits]
```

Settings persist between runs; pass only what changes. Look at
`design_preview.png` before saying anything:

- Gray is metal, white is cut away.
- **P1, P2...** are separate pieces of metal, largest first. **H1, H2...**
  are enclosed cutouts. Labels are stable across edits, so "drop P3" keeps
  meaning the same thing.
- **Orange letters** are suggested bridges for pieces that would otherwise
  fall out of the sheet. Pick with `--bridge B` (one flag per letter). Chosen
  bridges show as green **B1, B2...** and can be removed with
  `--remove-bridge 2`. Letters are recomputed every run, so only pick from the
  latest preview.
- **Red** is material thinner than the safe minimum; it may burn away.
- `--drop P4` removes a piece (it is not cut at all). `--fill H2` turns a
  cutout back into solid metal. For a stencil of text or a logo with many
  enclosed pieces, `--auto-bridges 2` is usually the right start; for a
  drawing, letters chosen by eye look better than automatic ones.

Then tell the person, in plain words, what will be metal and what will be
cut away, what is loose and what you suggest for it, and ask. Typical
questions: "The eyes and nose come out as holes; want that, or solid?" "The
inside of the ear would fall out of the stencil. I'd bridge it at A and C
(short, hidden in the outline). OK?" Re-run and re-check after every answer
until the summary reports one connected piece (or the person accepts loose
pieces on purpose) and no warnings they have not agreed to.

### 4. G-code

```
python3 scripts/pp.py gcode --job JOB --name NAME --feed F --pierce-delay S
       [--lead-in L] [--overcut O] [--origin-margin M] [--dwell-ms]
```

Use the cut-chart values for the material. Look at `toolpath_preview.png`:
it is drawn from the saved `.nc` file itself, so it is an honest check. Red
is outline cuts, blue is cutouts, dashed gray is rapids, numbers are cut
order (cutouts first, outline last, so the part stays held until the end).
Confirm bridges appear as gaps in the cut lines and the extent fits the
sheet.

Hand over: the `.nc` file, the toolpath picture, and the numbers that matter
(finished size, pierces, estimated minutes). Then give the short loading
checklist from `references/mach3-loading.md`. Say plainly that a first cut on
new material should be a dry run with the torch off.

## Changing things later

Everything is in the job folder's `state.json`. To resize, re-run `design`
with the new `--height`; edits and bridges are stored relative to the artwork
so they survive. To change material, re-run `design` with the new `--kerf`
and `gcode` with the new feed and pierce. To start over on the cleanup,
re-run `clean` (this clears the design).

## When it goes wrong

- The cleaned picture is patchy, noisy or missing lines: see
  `references/cleanup-recipes.md`. Fix the cleanup before anything else;
  every later stage inherits it.
- The summary says pieces are not connected: bridge, drop or fill until it
  says one piece, unless the person wants separate parts.
- "Narrower than the kerf" cutouts are simply skipped; if they matter, make
  the part bigger.
- A cut "starts on the line with no lead-in": acceptable for a hole, but tell
  the person the start point may show a small dimple; a bigger part or a
  smaller `--lead-in` usually clears it.
- The script prints `ERROR ...` and stops: read the message, it says what to
  run first or what flag is wrong.

## Which version is this

If the person asks what version they have, or something behaves differently
from what they remember, run `python3 scripts/pp.py version` and tell them.
`CHANGELOG.md` next to this file lists what changed in each version. Every
`.nc` file carries the version in its second comment line, so a cut can be
traced back to the version that made it.

## Machine facts (do not change without being told)

Langmuir CrossFire, original model, controlled by Mach3. No Z axis and no
torch height control, so the program is XY only: `M3` torch on, `G4` pierce
dwell, `G1` cuts, `M5` torch off, `G0` rapids, `M30` end. Units are set by
`G20`/`G21`. The part is placed with its bottom-left corner at the origin
margin (0.5 in default) from X0 Y0.
