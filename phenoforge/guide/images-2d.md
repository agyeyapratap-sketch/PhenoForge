# Photos from above (2D)

The **Images (2D)** tab measures plants in ordinary photos, for example top-view photos of
trays or plots. For every photo it finds the plant pixels and reports canopy cover, canopy
area and the size of each separate patch of plant ("blob"). With an ArUco marker in the
photo, areas are given in mm².

## Take the photos

- Shoot straight down from above, with the whole tray or plot in view.
- Put a printed ArUco marker (DICT_4X4_50, from the [Tools](tools.md) tab) flat at plant
  level in every photo if you want mm². Measure the printed marker with a ruler.
- Use even, diffuse light and a background that is not green.
- Save as JPEG, PNG, TIFF, BMP or HEIC/HEIF (iPhone photos). Photos are turned the right
  way up from their EXIF orientation.

## Steps

1. Put the photos in one folder. Sub-folders are not searched.
2. Open the **Images (2D)** tab.
3. **Images**: click **Folder...** and choose the folder.
4. **Output folder**: where results go. By default `images_out` in the `PhenoForge` folder in
   your home folder.
5. **Plant mask**: **exg** (Excess Green with an automatic threshold, good for most green
   plants) or **hsv** (a fixed green colour range).
6. **ArUco marker side (0 = none)**: the printed marker side in mm, or 0 for pixels only.
7. **Min plant size (px)**: patches smaller than this many pixels are ignored (dirt, weeds,
   noise). Default 200.
8. Click **Run batch**.

When it finishes, the table at the bottom right shows one row per photo, and the list on the
left shows the photo names.

## Look at each photo

Click a photo name in the list. The right side shows the overlay: plant pixels tinted
magenta, each blob's convex hull outlined in yellow and numbered. Check that the mask covers
the plants and not the background.

Below the list, **QR / GPS** shows any QR code text found in the photo and the GPS position
from the photo's EXIF data, if there is one. These are shown on screen only; they are not
written to the CSV files.

## Output files

In the output folder:

| File | Contents |
|---|---|
| `images_summary.csv` | One row per photo. |
| `images_blobs.csv` | One row per blob (patch of plant) per photo. |
| `<photo>_overlay.png` | The overlay picture. |
| `<photo>_mask.png` | The plant mask (white = plant). |

### images_summary.csv columns

| Column | Meaning |
|---|---|
| `image` | Photo file name. |
| `width_px`, `height_px` | Photo size in pixels. |
| `canopy_area_px` | Number of plant pixels (after removing small blobs). |
| `canopy_cover` | Fraction of the photo that is plant (0 to 1), after removing small blobs. |
| `n_blobs` | Number of blobs larger than the minimum size. |
| `mm_per_px` | Scale from the ArUco markers (empty if none). |
| `n_markers` | Number of markers found. |
| `exg_mean_canopy` | Mean Excess Green of the plant pixels. |
| `canopy_area_mm2` | Plant area in mm² (only with a scale). |

### images_blobs.csv columns

| Column | Meaning |
|---|---|
| `image`, `blob` | Photo name and blob number (as drawn on the overlay). |
| `area_px`, `area_mm2` | Blob area. |
| `hull_area_px`, `hull_area_mm2` | Area of the blob's convex hull. |
| `perimeter_px` | Outline length in pixels. |
| `cx`, `cy` | Blob centre in pixels. |
| `length_px`, `width_px`, `length_mm` | Long and short side of the smallest rotated rectangle around the blob. |
| `solidity` | Area divided by hull area (1 = compact, lower = lobed or open). |

## Limits

- Touching plants form one blob. Blobs are patches of plant, not always single plants.
- mm² is correct only for plant parts at the same height as the marker. Taller parts closer
  to the camera look bigger.
- The ArUco dictionary is DICT_4X4_50 on this tab. The command line has `--aruco-dict` for
  other dictionaries.

## From the command line

```
phenoforge images D:\photos\tray3 --aruco-mm 40 --out D:\results\tray3
```

See [Command line](cli.md).
