# Colour correction

Light changes from day to day, and every camera renders colour differently. That changes
greenness indices such as ExG. The **Colour** tab fixes this with a photo of a standard
24-patch colour chart (the classic ColorChecker layout). It fits a correction once and
applies it to scan colours or to a folder of photos, so colour traits stay comparable
between sessions.

## Take the chart photo

- Photograph the chart in the same light and with the same camera settings as the plants.
- Fill a good part of the photo with the chart, straight on, without glare.
- Do not over-expose: patches that are pure white or pure black are left out of the fit.

## Fit a correction

1. Open the **Colour** tab.
2. Click **Chart photo...** and choose the photo.
3. **Chart corners**: leave empty to find the chart automatically. If it is not found,
   enter the pixel positions of the chart's four outer corners as
   `x1 y1 x2 y2 x3 y3 x4 y4`, in the order top-left, top-right, bottom-right, bottom-left,
   with the dark-skin patch (patch 1) at the top left. You can read pixel positions in any
   image viewer, such as Paint.
4. **Reference values**: leave empty for the standard published 24-patch values. For a chart
   with its own certificate, give a JSON file with 24 `[r, g, b]` values (0–255, sRGB) in
   the same patch order, row by row from dark skin to black.
5. Click **Fit correction**.

The text under the button shows, for example, `RMSE 18.4 -> 3.1 (8-bit, 24 patches)`: the
average colour error before and after correction, on a 0–255 scale, and how many patches
were used. The corrected chart photo is shown on the right.

If PhenoForge says "Chart not found automatically. Enter its four corners (pixel
coordinates).", fill in **Chart corners** and click **Fit correction** again.

## Use the correction

- **Apply to current scan colours**: corrects the colours of the scan open on the 3D
  analysis tab. Then run the analysis again so greenness is recalculated.
- **Apply to an image folder...**: choose a folder of photos. Corrected copies are written
  as PNG files into a new `colour_corrected` folder inside it. The originals are not changed.
- **Save / load correction...**: when a correction is loaded, this saves it as a JSON file
  (default `colour_correction.json`). When no correction is loaded yet (for example just
  after starting PhenoForge), it loads one from a JSON file instead.

## How it works

The patch colours are converted to linear RGB. A 3 × 4 matrix (a linear map plus an offset)
is fitted by least squares from the measured patches to the reference values. The same
matrix is then applied to every pixel or point.

## From the command line

```
phenoforge colorcal chart.jpg --out colour_correction.json --apply img1.jpg img2.jpg
```

Corrected images are saved next to the originals with `_cc.png` at the end. See
[Command line](cli.md).
