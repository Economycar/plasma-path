# 05. Session log

## 2026-09-21

**Goal set by the user.** Take a raster Snoopy image, vectorize it cleanly,
and work out a workflow that ends in G-code for a Langmuir plasma table
running Mach3. Multi-part test: judge each stage before trusting the next.

**Vectorization.** Installed potrace. Cleaned the image (frame, watermark,
specks removed by connected-component filtering), traced, rasterized the
result back and compared. 98.6 % overlap, 1 px max boundary deviation. Judged
as clean as a bitmap allows. Details: `01-vectorization-results.md`.

**Workflow design.** Six stages proposed and later implemented. Key finding:
the drawing's closed loops mean a naive slot cut drops out four regions, so
the cut design stage needs bridges or a silhouette approach. Details:
`02-workflow.md`.

**Machine facts confirmed by the user.** Original Langmuir CrossFire, Mach3,
no Z axis, torch height manual. This fixed the G-code dialect: XY only,
M3/M5, G4 dwell.

**Web interface.** User asked for a web UI to choose paths, modes and what to
save. Built Plasma Path: Flask backend around `pipeline.py`, single-page
frontend. Three cut modes, auto and click-placed bridges, kerf offset,
per-path enable, warnings, save panel. Screenshotted all three modes
headlessly with Chromium. Improved auto-bridging to attach islands to the
growing union (fixed a long bridge at the hand and a lost-hole warning in
line-art mode). Details: `03-app-guide.md`.

**Questions answered, features not yet built.** How to set per-path
behaviour (only on/off exists), and how size is determined (art height only,
no stock or bed display). Both written up as proposals in `04-backlog.md`,
awaiting the user's choice.

**Consolidation.** User asked for everything documented and kept in this
folder. Restructured into app, docs, experiments, scripts, samples, images.
Scratch scripts rewritten as `experiments/vectorize/vectorize_test.py` and
`scripts/smoke_test.py`, both re-run from their new homes. Reference G-code
for each mode regenerated into `samples/gcode/`.

**Not done.** No metal has been cut. No git repository yet.

## 2026-09-23

**Metal was cut.** The user reports the Snoopy program from the web app was
cut on the CrossFire and came out as the preview showed.

**New goal.** The tool is for a friend who does not know CAD and has Claude
Desktop, not for the user. The web app has too many controls for him. The
user asked for research on the best way to deliver this, wanting something
that survives Claude Desktop updates and stays simple.

**Decision.** A custom Claude skill running in claude.ai's sandbox, plus a
Claude Project holding his usual material. Rejected: remote MCP on a VPS,
local install via Cowork, hosted web app. Reasoning and sandbox facts in
`06-skill.md`.

**Built.** `skill/plasma-path/`: pipeline rewritten to numpy, scipy and
Pillow only (raster-space design, vendored pure-Python potrace, verbatim
Mach3 post), a SKILL.md that runs the interview with numbered previews and
lettered bridge options, references (cut chart, cleanup recipes, hand-over
checklist, project text), three evals. Packaged as
`skill/dist/plasma-path.skill`.

**Verified.** New silhouette program overlaid on the cut one: same shape,
size within 0.015 in (`scripts/compare_nc.py`). All three modes, the bridge
pick/remove flow, mm units, and four hard test images exercised. Eval runs
with and without the skill were launched through subagents; results in
`skill/plasma-path-workspace/iteration-1/`.

**Eval results (iteration 1).** Three prompts, each run by a subagent with
the skill and one without: with the skill 23/23 assertions passed in about
2.6 min per run; without it 21/23 in about 7.7 min, and the baselines relied
on the system potrace binary or hand-written tracers that would not exist in
claude.ai's sandbox. Review page:
`skill/plasma-path-workspace/iteration-1/review.html`. Fixes made from the
runs: `--rotate` for tilted scans, white specks inside lines filled during
cleanup, slivers of metal auto-dropped, grain ignored by the thin-material
check, and SKILL.md told not to show the person command flags and to treat a
stencil size as the plate size.

**Second pass, same day.** The user tested the skill on claude.ai (it
works) and asked for more freedom in image handling and for generated
shapes and text. Added to `pp.py`: numbered marks on the cleanup preview
with `--drop-mark`/`--keep-mark`, `--color-keep`/`--color-drop`, and a
`make` command (circle, rectangle, ring or text only; text cut out or
raised; mounting holes; a joining bar for raised letters) with bundled
Liberation fonts (OFL, metric twins of Arial, Times and Courier). A
`direct` design mode uses the made bitmap as the metal. Bridge suggestions
are capped per piece when many pieces are loose. Package grew to about 850
KB because of the fonts.

**Versioning.** The user asked to start versioning because updates will go
back and forth with the friend. Added: a version in three places that must
agree (`SKILL.md` metadata, `pp.py`, `CHANGELOG.md`), the version stamped
into every `.nc` header, a `version` command, `skill/release.sh` that checks
agreement and builds `dist/plasma-path-<ver>.skill`, and git with tags
`skill-v<ver>`. First tag: skill-v1.1.0 (1.0.0 was the untagged first
package earlier the same day). `skill/README.md` documents the update
procedure on both sides, including removing the old skill before uploading.

**Published.** The repository went public on GitHub as `plasma-path`. The
Snoopy coloring page and everything derived from it (eval images, sample
programs) were removed from the history first and replaced by
`images/fish.png`, an original test drawing with the same features (thick
strokes, enclosed eye, inner lines, a frame, a watermark). Sample programs
were regenerated from it with the skill pipeline. Releases carry the
`.skill` files.
