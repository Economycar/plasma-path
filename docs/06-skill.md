# 06. The Claude skill

Written 2026-09-23. The goal changed from "a web app for me" to "something a
friend with no CAD background can use from Claude Desktop, that survives
Claude Desktop updates". This page records what was chosen and why, so the
reasoning does not have to be redone.

## Options considered

| Option | Verdict |
|---|---|
| Custom skill on claude.ai (runs in Anthropic's sandbox) | **Chosen.** Nothing installed on the friend's machine, same on web, desktop and phone, same pattern Anthropic's own docx/pptx skills use. |
| Remote MCP server on a VPS (custom connector) | No clean way to pass a chat-uploaded image to a remote tool; needs OAuth, TLS and uptime for one user; interactive MCP Apps UI for self-hosted connectors still had open rendering bugs in May 2026. |
| Local install driven by Cowork or Claude Code | Exactly the fragility to avoid: the June 2026 Windows desktop update moved the config path and dropped people's MCP servers. |
| Hosted copy of the web app | Fallback only. Rebuilds a chat the friend already has, and still puts the judgment on him. |

Sandbox facts that shaped the build (from Anthropic's docs, September 2026):
preinstalled numpy, scipy, pillow, scikit-learn; no OpenCV, shapely or
potrace; personal Pro/Max plans can pip install from PyPI, Team/Enterprise
cannot unless an admin allows it; 1 CPU, 5 GiB RAM, 30 MB file limit.

## What was built

`skill/plasma-path/`:

- `SKILL.md`: the conversation Claude runs (look at the picture, clean,
  ask mode/size/material together with a recommendation, design with
  numbered regions and lettered bridge options, generate, hand over with a
  loading checklist). The rule that matters: Claude never writes geometry
  or G-code, only picks settings and looks at previews.
- `scripts/pp.py`: the pipeline rewritten to need only numpy, scipy and
  Pillow. Design work is done in raster space at a fixed pixels-per-inch
  (kerf offset is a distance-transform dilation, bridges are drawn bars,
  unions are free), and the kerf-offset bitmap is traced once at the end by
  a vendored pure-Python potrace port (`scripts/vendor/potrace`, GPLv2+,
  from the `potracer` package). The Mach3 post is a verbatim port of
  `app/pipeline.py`'s.
- `scripts/pp.py make`: designs from nothing (shapes, cut or raised text in
  bundled Liberation fonts, mounting holes, a joining bar). `clean` also
  numbers marks for picking and can select or drop a colour.
- `references/`: cut chart (one verified row, the rest marked as starting
  points), cleanup recipes by symptom, Mach3 hand-over checklist, and text
  for a Claude Project.
- `evals/`: three test prompts and their images.

`skill/dist/plasma-path.skill` is the upload. `skill/README.md` has install
and update steps.

## Verification

- The new pipeline's silhouette program was overlaid on
  `samples/gcode/silhouette.nc` (the program that was cut on metal):
  identical shape, finished size within 0.015 in, a constant placement
  offset of about 0.03 in, differences otherwise at lead-ins only
  (`scripts/compare_nc.py`).
- Timing in a venv limited to numpy, scipy and Pillow: clean 1 s, design
  5 s, gcode 2 s for the 1187 x 1536 Snoopy page. Tracing a 2000 px bitmap
  takes about 1.5 s with the pure-Python tracer, so the 500x slowdown
  against C potrace does not matter at these sizes.
- Hard inputs tried: low-quality JPEG with halos (auto settings fine),
  light-on-dark logo (auto-inverted; stencil with `--auto-bridges 2` bridged
  every letter counter), noisy tilted scan with uneven lighting (needs
  `--adaptive 51 --blur 1 --speck 120`, then `--keep-largest`), a photo-like
  gradient image with soft shadow (Otsu alone was enough).
- Bridge suggestions for line art target the main body only. Connecting
  islands to each other was what produced the eye-to-nose cluster noted in
  the backlog.

## How the friend uses it

Upload the `.skill` file once (Customize > Skills), optionally make a
Project with the suggested instructions, then drop a picture in and answer
two or three questions. Files come back in the conversation's outputs.
Updates are a re-upload of the zip.

## Robustness reasoning

What could break and what was done about it:

- Sandbox package changes: nothing outside numpy/scipy/Pillow is used;
  the tracer is vendored.
- Plan without network: no pip at run time.
- Skill format changes: Anthropic's own skills use the same layout, so a
  migration would be documented.
- Per-turn tool-use limits: each stage is one script call that writes a
  preview and a state file; three calls make a part.
- Path conventions in the sandbox: the skill tells Claude to use the
  outputs folder when one exists and a local folder otherwise; the script
  does not hard-code either.
