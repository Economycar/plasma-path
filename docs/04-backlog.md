# 04. Backlog

Ordered roughly by how much they change what you can cut. Items marked
*discussed* came up in the 2026-09-21 session and were described but not
built; the user has not yet chosen among them.

## Before the first real cut

*2026-09-23: the Snoopy program was cut and matched the preview. The kerf
check and bridge test below are still worth doing on each new material.*

- **Dry run on the table** with the torch disabled, using
  `samples/gcode/silhouette.nc` (the simplest mode: 5 pierces). Confirm the
  Mach3 profile accepts the header, M3/M5 fire the torch relay, and G4 P0.5
  waits half a second (if it waits 0.0005 s, tick the dwell-in-milliseconds
  option).
- **Kerf check.** Cut a 1 in square hole and a 1 in square plate from scrap
  and measure. Adjust the kerf setting until both hit size.
- **Bridge strength.** Try 0.15 and 0.20 in bridges on the stencil in the
  actual material thickness.

## Per-path behaviour (discussed)

A settings drawer that opens from a row in the cut-path table, each override
with a reset to the global rule, keyed by path id, saved in the settings JSON:

- Cut or skip (exists today as the checkbox).
- Direction: auto, clockwise, counter-clockwise.
- Kerf side: outside, inside, on the line (for scores and exact-width slots).
- Lead-in length and overcut per path.
- Pierce point: click on the contour in the preview to move it.
- Order: drag rows to set sequence, auto as default.

Path ids are stable while mode and trace settings stay fixed. Changing those
regenerates contours; the app should report overrides that no longer match.
Estimated effort for all six: about an hour.

## Sizing and stock (discussed)

- Lock by width or height: type either, the other follows.
- Bed outline drawn in the preview with the part at its true position.
- Dimension callouts for width, height, and stencil plate size.
- Stock rectangle: the sheet actually loaded, drawn separately, with a
  fit warning.
- Drag handles to move or resize the part in the preview, snapping to a step.

The first three are small. The last is the largest piece of UI work in the
list.

## Quality of results

- **Line-art auto tabs are ugly.** They connect the eyes and nose in a
  cluster. *Done in the skill (2026-09-23):* suggestions target the main body
  only and are offered as lettered options to pick. The web app still has the
  old behaviour.
- **Arc fitting.** Emit G2/G3 instead of dense G1 for smoother motion on
  Mach3. Simplify tolerance is the stopgap.
- **Pierce placement on straight runs.** Currently the first valid vertex in a
  sweep. Prefer low-curvature spots away from corners.
- **Difficult sources.** *Done in the skill (2026-09-23):* adaptive
  threshold, blur, open/close, crop and keep-largest, tested on a JPEG with
  halos, a noisy scan, a light-on-dark logo and a photo-like image. The web
  app has not been updated.

## Tooling

- Render the saved `.nc` back to an image and overlay it on the design, as an
  independent check of the post. *Done in the skill:* `toolpath_preview.png`
  is drawn from the saved file; `scripts/compare_nc.py` overlays two programs.
- Git init and a first commit. *Done 2026-09-23*; skill releases are tagged
  `skill-v<version>` and built by `skill/release.sh`.

## Skill (added 2026-09-23, updated 2026-09-25)

- Send the friend `INSTALL.md`; watch the first real conversation and
  note where the questions confuse him.
- After the claude.ai chat/Cowork merge lands, re-check the menu names in
  `INSTALL.md` and whether re-uploading a skill replaces or duplicates.
- Re-run the evals on the current version before the next geometry
  change (last run on 1.2.0/1.2.1); tighten the assertions the graders
  flagged (pierce counts, stencil plate vs artwork width).
- Numbered marks on the cleanup preview stop at 60; a photo with hundreds
  of specks falls back to size filters only.
- Fill the cut chart (`skill/plasma-path/references/cut-chart.md`) with
  verified rows as materials are tested; only one row is verified today.
- Eval loop: review `skill/plasma-path-workspace/iteration-1/` results,
  revise SKILL.md wording, re-run. Description optimisation for triggering
  not yet run.
- The web app and the skill now have two copies of the pipeline. Either port
  the skill's raster pipeline back into the app, or retire the app's shapely
  version and keep it only as a viewer.
