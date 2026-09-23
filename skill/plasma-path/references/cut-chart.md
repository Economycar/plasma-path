# Cut chart

Values passed to `design` (`--kerf`, `--bridge-width`, `--min-material`) and
`gcode` (`--feed`, `--pierce-delay`, `--lead-in`, `--overcut`).

Only the first row has been cut on this machine. Every row marked *starting
point* is a typical value for a 40-45 A hand torch on a CrossFire and must be
checked on scrap before trusting it. When you use a starting-point row, say so
and suggest a 1 in test square first (cut a 1 in square hole and a 1 in square
plate; if the hole is small and the plate is big, increase the kerf; if the
reverse, decrease it).

Units: inches, in/min, seconds.

| Material | Thickness | Feed | Pierce delay | Kerf | Bridge width | Min feature | Status |
|---|---|---|---|---|---|---|---|
| (the material used on 2026-09-21; ask the owner which) | | 60 | 0.5 | 0.055 | 0.20 | 0.10 | **cut successfully** (Snoopy silhouette, 12 in) |
| Mild steel | 22 ga (0.030) | 150 | 0.3 | 0.045 | 0.15 | 0.08 | starting point |
| Mild steel | 18 ga (0.048) | 120 | 0.4 | 0.050 | 0.20 | 0.10 | starting point |
| Mild steel | 16 ga (0.060) | 100 | 0.4 | 0.050 | 0.20 | 0.10 | starting point |
| Mild steel | 14 ga (0.075) | 80 | 0.5 | 0.055 | 0.20 | 0.12 | starting point |
| Mild steel | 11 ga (0.120) | 55 | 0.6 | 0.060 | 0.25 | 0.15 | starting point |
| Mild steel | 3/16 (0.188) | 35 | 0.8 | 0.065 | 0.30 | 0.20 | starting point |
| Mild steel | 1/4 (0.250) | 25 | 1.0 | 0.070 | 0.35 | 0.25 | starting point |
| Aluminum | 1/8 (0.125) | 70 | 0.5 | 0.060 | 0.25 | 0.15 | starting point |
| Stainless | 16 ga (0.060) | 90 | 0.4 | 0.050 | 0.20 | 0.10 | starting point |

Lead-in 0.10 in and overcut 0.05 in are fine for all of these. Bridge width
is the width of the metal tab that holds a loose piece; thicker material can
use narrower tabs relative to its strength, but 0.2 in is a good default the
owner can snap off or grind.

## Owner's notes

Add measured results here as rows above are verified, with the date, the
consumables (nozzle amps) and anything learned. Replace a *starting point*
row rather than adding a second one for the same material.
