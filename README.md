# Plasma Path: raster image to plasma-cut G-code

An experiment that became a tool. Start with a raster image (the test case is
`images/fish.png`, an original line drawing), vectorize it, decide what is metal and what is removed,
offset for kerf, and produce G-code for a **Langmuir CrossFire (original)
running Mach3 with no Z axis**. The tool is a local web app called Plasma Path.

Started 2026-09-21. See `docs/05-session-log.md` for what happened when.

## Quick start

    sudo pacman -S potrace                                   # system dependency (Arch)
    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
    ./run.sh                                                 # open http://127.0.0.1:5077

Put source images in `images/` or use the Upload button. Saved outputs land in `out/`.

Headless checks, no browser needed:

    .venv/bin/python scripts/smoke_test.py                   # all three modes, prints numbers
    .venv/bin/python experiments/vectorize/vectorize_test.py # the original trace-quality test

## Folder layout

    app/                     the web app
      pipeline.py            geometry: clean, trace, cut design, bridges, kerf, G-code
      server.py              Flask API, caching, save-to-disk
      static/index.html      single-page UI (vanilla JS, no build step)
    docs/                    everything written about the project
      01-vectorization-results.md   how clean the trace came out, with numbers
      02-workflow.md                the six-stage approach and the machine facts
      03-app-guide.md               what every control does, current limits
      04-backlog.md                 agreed and proposed next features
      05-session-log.md             dated record of work
      screenshots/                  UI in each cut mode
    experiments/vectorize/   the first experiment as a standalone script + its results
    scripts/smoke_test.py    run the pipeline headless in all modes
    samples/gcode/           reference .nc output for each mode, 10 in tall fish, made by the skill
    images/                  source images
    out/                     files the app saves (yours to keep or clear)
    uploads/                 images added through the browser (created on demand)
    .venv/                   Python environment (not for version control)

## Status at a glance

- Vectorization: done and verified, within 1 px of the source.
- Cut design: three modes work, auto-bridging keeps every mode to one piece.
- G-code: Mach3 dialect, XY only, torch on M3 / off M5, holes first.
- Not yet done: cut on real metal, per-path overrides, width-locked sizing,
  bed outline in the preview. Details in `docs/04-backlog.md`.

## Machine facts that shape the output

Langmuir CrossFire, original model. Mach3, not FireControl. No Z axis: torch
height is set by hand before each run, so the G-code has no Z moves and no
torch height control. Kerf assumed 0.055 in (45 A consumable); change it in
the Size and kerf panel. Bed assumed 24 x 24 in.

## Claude skill

`skill/plasma-path/` packages the pipeline as a Claude skill for someone
who only has Claude Desktop: pure Python, no installs, conversational.
See `skill/README.md` and `docs/06-skill.md`.

To use it in claude.ai or the Claude desktop app: download
https://github.com/Economycar/plasma-path/releases/latest/download/plasma-path.skill
and upload it under Customize > Skills (with code execution turned on).
