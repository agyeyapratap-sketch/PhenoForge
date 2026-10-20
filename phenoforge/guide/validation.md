# Validation

Validation tells you how far you can trust PhenoForge's numbers for your plants and your
capture method. This page covers three checks:

1. **Trait agreement**: PhenoForge's traits against your hand measurements (Validation tab).
2. **Mask comparison**: a plant mask from PhenoForge against a reference mask (Validation tab).
3. **Scan against photos**: does the 3D model of an iPhonotype package match its own photos
   (frame check)?

## 1 Trait agreement

### Prepare two CSV files

- **Predicted CSV**: PhenoForge's results, for example `all_scans.csv` from
  [Analyse a whole folder](batch.md) or a `<scan>_plant.csv`.
- **Reference CSV**: your hand or facility measurements, made in Excel and saved as CSV.

Both files need a column with the same name that identifies each scan, with matching values
in both files. PhenoForge's batch table calls it `scan` (the file name without extension).
The trait columns you want to compare must have the **same names** in both files. For
example, if you measured height with a ruler in metres, name the column `height_max` in your
reference file.

Watch the units: PhenoForge reports metres, m² and m³. Convert your reference values (or
PhenoForge's) so both use the same unit.

### Run the comparison

1. Open the **Validation** tab.
2. **Predicted CSV**: click **...** and choose PhenoForge's file.
3. **Reference CSV (manual / facility)**: choose your file.
4. **Join column**: the column that identifies each scan (default `scan`).
5. **Columns**: leave empty to compare every column that both files share and that holds
   numbers. Or type a list, for example `height_max,surface_area_m2`.
6. Click **Compare traits**.

The Log shows how many rows matched, and how many rows are only in one file (check the
spelling of the IDs if many are unmatched).

### Reading the table

One row per trait:

| Column | Meaning |
|---|---|
| `n` | Number of matched scans. |
| `mae` | Mean absolute error: the average size of the difference. |
| `rmse` | Root mean square error: like MAE, but large errors count more. |
| `bias` | Mean of (predicted − reference). Positive = PhenoForge reads high. |
| `mape_percent` | Mean absolute percentage error. |
| `r2` | Coefficient of determination against the 1:1 line (how close points are to predicted = reference). Can be negative if the agreement is poor. |
| `pearson_r` | Correlation. High r with a large bias means a consistent offset you can calibrate out. |
| `ccc` | Lin's concordance correlation coefficient: agreement with the 1:1 line (1 = perfect). |
| `slope`, `intercept` | Straight-line fit of predicted against reference. |
| `loa_low`, `loa_high` | Bland-Altman 95 % limits of agreement: most differences fall between these. |
| `calib_a`, `calib_b` | Calibration: reference ≈ calib_a × predicted + calib_b. Use it to convert PhenoForge values to your reference scale, for example voxel volume to dry weight. |

The picture on the right shows the **first** trait in the table: a scatter plot against
the 1:1 line, and a Bland-Altman plot (difference against mean, with the bias and limits of
agreement). The picture is also saved as `validation.png` in the `PhenoForge` folder in your
home folder. To plot another trait, type only that trait in **Columns** and click
**Compare traits** again.

### Good practice

- Measure at least 20–30 plants that cover the full range of sizes.
- Use the same capture and analysis settings that you will use for the experiment.
- For biomass, calibrate `voxel_volume_m3` or `hull_volume_m3` against harvested dry weight
  with `calib_a` and `calib_b`, and report R² and RMSE of the calibrated values.

## 2 Mask comparison

Compare a plant mask from PhenoForge (for example a `_mask.png` from the
[Images (2D)](images-2d.md) tab) with a reference mask (for example hand-drawn, or from
another facility).

1. In **Mask pair (PNG)**, type the path of the predicted mask in the first box and the
   reference mask in the second box. Both must be the same size. White (brighter than mid
   grey) is plant.
2. Click **Compare masks**.

| Result | Meaning |
|---|---|
| `iou` | Intersection over union: overlap area divided by the combined area. 1 = identical, 0 = no overlap. |
| `dice` | Dice coefficient: 2 × overlap / (sum of both areas). Always at least as high as IoU. |
| `precision` | Fraction of predicted plant pixels that are plant in the reference. Low = extra pixels. |
| `recall` | Fraction of reference plant pixels that were found. Low = missed pixels. |
| `area_pred_px`, `area_ref_px` | Plant pixels in each mask. |
| `area_error_percent` | (predicted − reference) / reference × 100. |

## 3 Check a scan against its photos (frame check)

An iPhonotype package contains the photos used to build the 3D model and the camera
position of each photo. The frame check draws the 3D scan from each camera position and
compares its outline with the plant in the photo.

### Run it

1. Open an iPhonotype package on the 3D analysis tab.
2. Click **Check vs photos** (or **Tools > Check scan against its photos (iPhonotype)...**, or
   the Start page button **Check a scan against its photos**). If no package is open,
   PhenoForge asks you to choose one.
3. A window "Scan vs photos" opens and works for a while. Up to 12 photos, spread evenly
   through the capture, are compared.

### What it does

For each photo:

1. The scan's points are drawn into the photo's view from the recorded camera position, as
   small coloured discs. This gives a "rendered" picture and a rendered plant outline (pixels
   where the front-most point is plant-coloured).
2. The photo is split into plant and background with the same Excess Green index.
3. Only the area around the scanned plant is compared, so other plants in the background do
   not count against the scan.
4. The two outlines are compared.

### Reading the results

The table has one row per photo:

| Column | Meaning |
|---|---|
| `name` | Photo file name. |
| `iou` | Overlap of the scan outline and the photo outline (0 to 1). |
| `dice` | Dice coefficient (as above). |
| `precision` | Fraction of the scan outline that is plant in the photo. Low = the scan has geometry the camera did not see (extra blobs, floaters). |
| `recall` | Fraction of the plant in the photo that the scan covers. Low = parts missing from the scan (thin leaves, awns). |
| `points_in_view` | Scan points that fall inside the photo. |
| `rendered_px`, `photo_px` | Plant pixels in the scan outline and in the photo. |
| `roi_px` | Size of the area compared. |
| `error` | Why a photo was skipped, if it was. |

Click a row to see that photo. The picture has three panels side by side: the photo, the
scan drawn from the same position, and an agreement map: **green** where both agree,
**magenta** where only the scan has plant, **yellow** where only the photo has plant.

The line under the table summarises: frames in the package, frames compared and skipped,
mean, median and minimum IoU, mean Dice, the three worst frames, and any warning.

How to read IoU:

- **IoU near 1 on every photo**: the model matches what the camera saw.
- **One or two low photos**: usually a blurred photo or a wrong camera position for that
  frame. Not a problem for the traits.
- **Low IoU on many photos**: missing or extra geometry, or the plant moved (wind, touching)
  during capture. Treat the traits with caution, or rescan.
- **IoU near 0 everywhere**: the scan no longer lines up with the photos (see the warning).

PhenoForge does not set a pass mark. Compare scans of the same kind with each other. Thin
leaves give lower IoU than broad leaves, because small errors are large compared to a thin
outline.

The check always uses the scan exactly as it was loaded, before ground levelling or scaling.
HEIC photos in the package are read like any other photo.

### From the command line

```
phenoforge framecheck W123.ftscan.zip --frames 12 --out frame_check
```

This writes `frame_check.csv` and overlay pictures of the three worst frames, and prints the
summary. See [Command line](cli.md).
