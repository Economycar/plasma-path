# Plasma Path changelog

Versions follow MAJOR.MINOR.PATCH. The MINOR number goes up when the skill
can do something new (a new command, a new option). PATCH goes up for a fix
or a wording change that does not add capability. MAJOR would go up only if
the G-code output or the conversation changed in a way that makes old cuts
or habits wrong.

The version is in three places that must agree: `SKILL.md` frontmatter
(`metadata.version`), `scripts/pp.py` (`__version__`), and this file. The
second comment line of every `.nc` file records the version that made it.

## 1.2.3 - 2026-09-23

Changed
- Instructions for pictures that do not exist yet: use an image-generation
  connector when one is attached, otherwise hand the person a ready-made
  prompt for their own generator and take the result. Silhouette-friendly
  prompt wording is spelled out. INSTALL.md gains a section on the three
  ways to get a picture (Gemini in a Google account, the Hugging Face
  connector inside Claude, or an API key setup that is not recommended).

## 1.2.2 - 2026-09-23

Changed
- The repository is now a Claude Code plugin marketplace, so the skill can
  be installed in Claude Code straight from GitHub and updated with one
  command. No change to what the skill does.
- Setup note for running on a person's own computer: install numpy, scipy
  and Pillow once if the import check fails.

## 1.2.1 - 2026-09-23

Fixed
- `edit --smooth-region` no longer erases a frame around its rectangle
  (the morphology now runs on the whole image and only the inside of the
  rectangle is written back).
- `gcode` skips loops smaller than two kerf widths, which the tracer
  produced at pinched gaps, and says so.
- `design` warns when a narrow gap closes under the kerf and leaves an
  enclosed pocket that would be cut as a small window, with the edit to
  make if that is unwanted.

## 1.2.0 - 2026-09-23

Added
- `edit` stage: erase or keep rectangles, polygons and circles; paint
  shapes and lines; smooth a region or everything; thicken, thin, fill holes,
  outline, invert, mirror, rotate. Before/after preview.
- `adopt` stage: hand any black-and-white image made with your own Python
  back into the pipeline as the cleaned drawing.
- A faint 0.1 coordinate grid on the cleanup preview so spots can be named
  as fractions.

Changed
- Instructions rewritten: the drawing is Claude's to shape however the
  person wants (own numpy/scipy/Pillow code encouraged; pip allowed as a
  fallback); only the cut path and G-code stay locked to the script. Claude
  is told never to say a part of the picture cannot be changed.

## 1.1.0 - 2026-09-23

Added
- `make` command: circles, rectangles, rings or text alone, with text cut
  through or raised, multi-line text, mounting holes, and a joining bar for
  raised letters. Bundled Liberation fonts (Arial, Times and Courier metric
  twins); a person can also supply a `.ttf`.
- `direct` design mode: black in the cleaned image is the metal, as is.
- Numbered marks on the cleanup preview with `--drop-mark` and `--keep-mark`.
- `--color-keep` and `--color-drop` for coloured sources.
- `--rotate` to straighten tilted scans.
- `version` command; the version is written into every `.nc` file.

Changed
- White specks inside lines are filled during cleanup; slivers of metal
  smaller than eight minimum-feature squares are dropped automatically
  (`--keep-slivers` keeps them).
- The thin-material check ignores one-pixel edge fuzz from grainy sources.
- Bridge suggestions go to the main body only and are capped per piece when
  many pieces are loose.
- Skill text: never show the person command flags; a stencil size is read
  as the plate size.

## 1.0.0 - 2026-09-23

First packaged version. Cleanup (threshold, adaptive threshold, blur,
open/close, crop, bands, specks, keep-largest, invert), three cut modes
(silhouette, line art, stencil), numbered regions with drop and fill,
lettered bridge options, kerf offset, Mach3 post for the CrossFire (XY only,
M3/M5, G4 dwell). Output verified against the program cut on 2026-09-21.
