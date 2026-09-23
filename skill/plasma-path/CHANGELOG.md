# Plasma Path changelog

Versions follow MAJOR.MINOR.PATCH. The MINOR number goes up when the skill
can do something new (a new command, a new option). PATCH goes up for a fix
or a wording change that does not add capability. MAJOR would go up only if
the G-code output or the conversation changed in a way that makes old cuts
or habits wrong.

The version is in three places that must agree: `SKILL.md` frontmatter
(`metadata.version`), `scripts/pp.py` (`__version__`), and this file. The
second comment line of every `.nc` file records the version that made it.

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
