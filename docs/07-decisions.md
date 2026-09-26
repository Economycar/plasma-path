# 07. Decisions

Dated log of choices, with the why and what was rejected. Add to the top.
Reasoning that is long-form lives in `06-skill.md`; this is the index of
what was decided.

## 2026-09-24

- **Text in `make` shrinks to fit the shape by default.** A 1.6 in
  WELCOME ran off a 10 in disc in the guide example. Forcing the size is
  `--no-fit`. Why: a person names a height by feel; running off the edge
  is never what they meant.
- **A capability tour (`GUIDE.md`) with real previews ships in the repo.**
  Previews are generated from `images/fish.png` and from `make`, so
  nothing in the public repo is anyone else's art.

## 2026-09-23

- **Delivery is a claude.ai custom skill, not a hosted app, remote MCP or
  local install.** Runs in Anthropic's sandbox; nothing on the friend's
  machine; survives desktop app updates. Rejected: remote MCP on a VPS (no
  clean way to pass a chat image to it, needs OAuth and uptime), Cowork or
  Claude Code local install (the fragility to avoid), a hosted web app
  (rebuilds a chat he already has). Detail in `06-skill.md`.
- **Pipeline needs only numpy, scipy and Pillow.** Design work is done in
  raster space; the kerf-offset bitmap is traced once by a vendored
  pure-Python potrace (GPLv2+). Rejected: pip at run time as a requirement
  (kept only as an optional fallback for image work on personal plans).
- **Geometry and G-code are locked to the script; the drawing is not.**
  Claude never writes coordinates or G-code, so output stays as
  trustworthy as the parts already cut. Everything before that (cleanup,
  editing, restyling, redrawing with its own code) is free, because the
  person sees a preview before anything is cut. The first draft locked
  both and produced refusals like "I can't remove the stem"; reversed in
  1.2.0.
- **No image generation inside the skill.** Anthropic has no image model
  (checked through 2026-09-23). Chosen order: the person generates in
  Gemini with their Google account and drops the picture in; second, the
  Hugging Face connector (sign-in only, free credits, paid Claude plan);
  rejected for now: a Gemini API key with a local server (breaks with app
  updates, needs a key on his machine).
- **Versioning.** One version in three places (`SKILL.md` metadata,
  `pp.py`, `CHANGELOG.md`), checked by `skill/release.sh`; every `.nc`
  carries it; git tags `skill-v<ver>`; GitHub releases carry the numbered
  file plus an unversioned copy so `releases/latest/download/plasma-path.skill`
  is a stable link. MINOR for capability, PATCH for fixes and wording.
- **Two install channels, one primary.** Primary: upload the `.skill` file
  in claude.ai (the only way into the web and desktop apps). Secondary:
  the repo is a Claude Code plugin marketplace for people who use Claude
  Code. A claude.ai upload syncs into Claude Code; not the reverse.
- **Public repository rules.** The developer's local folder name must not
  appear anywhere in the repo (history was rewritten before the first
  push). No third-party images: the Snoopy coloring page and everything
  derived from it were purged and replaced with original test art.
- **Bridge suggestions target the main body only,** capped per piece when
  many pieces are loose. Island-to-island tabs were the source of the ugly
  eye-to-nose clusters. Automatic bridging is the default advice for text
  and logos; lettered choices for drawings.
- **Cleanup fills white specks inside lines and the design stage drops
  slivers of metal under eight minimum-feature squares.** Scanner grain
  otherwise became loose pieces. `--keep-slivers` overrides.
- **G-code skips loops under two kerf widths** (tracer artefacts at
  pinched gaps) and the design stage warns when a narrow gap closes under
  the kerf and leaves a pocket that would be cut as a window.
- **Cut chart: one verified row.** Only the settings from the 2026-09-21
  cut (feed 60, pierce 0.5 s, kerf 0.055 in) are marked verified; the
  material is not recorded and must be asked. All other rows are typical
  values marked as starting points; the skill says so when it uses one.
- **The web app keeps its own shapely pipeline for now.** Two copies of
  the pipeline exist; retiring or porting is deferred (see backlog).

## 2026-09-21

- **Machine facts fix the G-code dialect.** Original Langmuir CrossFire on
  Mach3, no Z axis, torch height by hand: XY only, M3/M5, G4 dwell.
- **Three cut modes** (silhouette, line art, stencil) with bridges, because
  a closed-loop drawing drops regions out of the sheet under a naive
  slot cut.
