# Cleanup recipes

What the `clean` stage does, in order: optional blur, threshold (global Otsu
or local adaptive), polarity (ink is the dark minority unless told
otherwise), optional crop, closing then opening, then a filter that drops
frames, bands, specks and (optionally) everything but the N largest marks.

Look at `clean_preview.png` after every run. The left half shows the
original with every removed mark boxed in red; the right half is exactly what
goes forward. The summary also prints notes when it sees something suspicious
(many gray levels, an inversion, too many marks).

## Symptoms and fixes

| What you see | Do this |
|---|---|
| Website watermark or caption along the bottom edge | `--bottom 0.06` (fraction of the image height to ignore) |
| Title or caption along the top | `--top 0.08` |
| A thin border around the whole page | on by default (`--frame on`); a rotated or double border may leave slivers, then add `--crop` or `--keep-largest` |
| Light art on a dark background came out as a black slab | it should auto-invert; if not, `--invert on` |
| Dark art on light came out inverted (mostly black) | `--invert off` |
| JPEG: fuzzy gray halos around lines, small dots near edges | `--blur 1 --speck 60`; if lines look ragged, add `--close 1` |
| Scan or phone photo of a drawing: one side dark, speckled | `--adaptive 51 --blur 1 --speck 120`; raise `--speck` or add `--keep-largest 8` if noise remains; `--offset 15` if paper texture still shows, `--offset 6` if faint lines vanish |
| Photo of an object with gradient background and shadow | `--threshold 80` (try 60-110) or `--adaptive 101 --offset 20`; then `--keep-largest 1` |
| Scan is tilted | `--rotate 3` (degrees counter-clockwise; estimate from the page edge or a straight line in the drawing, check the preview, adjust) |
| One specific mark to remove (a signature, a stray doodle) | note its number on the right half of the preview, then `--drop-mark N`; or `--keep-mark` for the ones to keep |
| Coloured drawing: keep only one colour's lines | `--color-keep red` (or `#c02020`, or `200,30,30`); `--color-tol 40` if it grabs too much, `120` if lines break up |
| Coloured background, grid paper, blue pencil guide lines | `--color-drop blue` (then the normal threshold runs on what is left) |
| Clutter or other drawings in the picture | `--crop x0,y0,x1,y1` as fractions of width and height, e.g. `--crop 0.1,0.05,0.9,0.95`; the crop box is drawn blue on the left of the preview |
| Lines broken into dashes (faint pen, low contrast) | `--close 2`, or lower the threshold; check that closing did not merge neighbouring lines |
| Thin lines vanish | lower `--threshold` (e.g. 160 for a light gray drawing) or `--offset 6` with adaptive; do not blur |
| Tiny enclosed white dots inside thick lines | harmless; the design stage skips cutouts narrower than the kerf and says so |
| Hundreds of marks kept | `--speck 100` and up, or `--keep-largest N` with N = the number of separate parts of the drawing you can count |
| Nothing kept | `--invert on`, a different `--threshold`, or `--frame off` if the drawing itself spans the page |

`--speck` is in pixels of the (possibly downscaled) image; the image is
limited to 2400 px on the long side, so 30 px is a dust speck and 300 px is a
small mark like an apostrophe.

## Things the pipeline cannot fix

- Colour drawings where the lines are a light colour on white: threshold
  finds the darkest parts only. Ask for a black-and-white version or a
  darker photo.
- Shading, halftone or pencil texture: it becomes noise or a blob. Ask the
  person which outline they want and treat it as a silhouette.
- Very low resolution (under 300 px on the long side): edges come out lumpy.
  Ask for a bigger image if one exists; otherwise warn that curves will be
  a little wobbly.
