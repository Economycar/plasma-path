# 01. Vectorization results

Date: 2026-09-21. Source: `images/snoopy1.webp`, 1187 x 1536 px, lossless WebP,
8 colours, black line art with a border frame and a "ColorwithAnne.com" watermark.
Script: `experiments/vectorize/vectorize_test.py`. Results in
`experiments/vectorize/results/`.

## Method

1. Flatten alpha onto white, greyscale, threshold at 128.
2. Connected-component filter: drop any component wider or taller than 80 % of
   the image (the frame), anything in the bottom 6 % (the watermark), anything
   under 30 px² (specks). 5 components survive: body outline, head tuft, two
   eyes, nose.
3. potrace with `--turdsize 10 --alphamax 1.0 --opttolerance 0.2`, SVG and DXF.
4. Rasterize the SVG back at the source resolution and compare pixel-for-pixel.

## Numbers

| Metric | Value |
|---|---|
| Ink overlap (intersection over union) | 98.6 % |
| Pixels lost / gained | 1211 / 948 of 153 501 |
| Boundary deviation, mean | 0.14 px |
| Boundary deviation, 95th percentile | 1.00 px |
| Boundary deviation, max | 1.00 px |
| Paths / closed contours / Bézier segments | 5 / 9 / 363 |
| SVG size | 8.9 kB |
| Typical stroke width | ~24 px |
| Enclosed white regions | 4 (head, body, hand gap, arm gap) |

## Reading the results

- `04_overlay.png`: black where trace and source agree, blue where ink was lost,
  red where ink was added. It is almost entirely black; the coloured pixels are
  single-pixel edge differences.
- `05_zoom4x_paw.png`: the vector rendered at 4x. Curves are smooth, no staircase.
- A 1 px maximum deviation is the limit of what a bitmap can express, so this is
  as clean as a trace gets.

## Why it was easy, and what would not be

The source is ideal: lossless, high contrast, no anti-aliasing noise, no grey.
A JPEG with compression halos, a photo, or a scan would need real work in the
clean-up stage: blur, adaptive threshold, morphological open/close, and manual
touch-up. The app exposes blur, threshold and speck size for that, but has not
been tested on a difficult source yet.

## The design problem the trace revealed

The strokes form closed loops. If the ink is cut away as slots, the 4 enclosed
white regions fall out. This is what forced the three cut modes in the app; see
`02-workflow.md`.
