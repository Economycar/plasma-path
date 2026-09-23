# Handing over the file

Give the person the `.nc` file and the toolpath picture, then this checklist
in your own words. Keep it short; they have done this before.

1. Copy the `.nc` file to the Mach3 computer and load it with **File > Load
   G-Code**. The preview in Mach3 should look like the toolpath picture.
2. Put the sheet on the table. The program starts at X0 Y0 and the part sits
   a margin (0.5 in unless changed) up and right of that, so X0 Y0 goes at
   the sheet's bottom-left with the part fully on the sheet. Jog there and
   **Zero X** and **Zero Y**.
3. Set the torch height by hand (the machine has no Z axis).
4. First time on a new drawing or material: run it once with the torch
   disabled (plasma unit off, or M3 output disabled) and watch that it stays
   on the sheet and follows the picture.
5. Check the pierce pause: the program uses `G4 P0.5` for half a second. If
   Mach3 barely pauses, its dwell is set to milliseconds; either change the
   Mach3 setting or regenerate with `--dwell-ms`.
6. Cut. Cutouts go first, the outline last, so the part is held until the
   end.

If they report the part came out too big or too small by a constant amount,
that is kerf: adjust `--kerf` (bigger kerf makes outer shapes smaller and
holes bigger in the program, which makes the metal come out truer) and
regenerate.
