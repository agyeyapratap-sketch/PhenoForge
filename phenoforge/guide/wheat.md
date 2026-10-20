# Wheat: heads and tillers

PhenoForge offers two ways to count wheat heads (spikes):

1. **In a 3D scan** of one plant, with a rule-based method (a heuristic). No training is
   needed. Tillers can be counted the same way.
2. **In photos**, with a head detector that you train yourself on your own labelled photos
   (optional add-on).

Both give estimates. Check them against hand counts on a subset of your plants before you
use them as data (see [Validation](validation.md)).

Other wheat traits come from the normal analysis: height (`height_max`, `height_p99`),
leaf area (`surface_area_m2`) and virtual biomass (`voxel_volume_m3`, `hull_volume_m3`).
See the [Trait glossary](traits.md).

## Heads and tillers in a 3D scan

### Steps

1. On the Start page click **Wheat: heads and tillers** and choose the scan. Or open the scan
   and choose the preset **Wheat: heads and tillers** on the 3D analysis tab.
2. The preset ticks **Count wheat heads (spikes)** and **Count tillers**, keeps leaf
   candidates on, keeps one plant, and sets **Vegetation index** to **none** so straw-coloured
   heads are not filtered out.
3. Set the scale in **2 Metric scale** (see [The 3D analysis tab](3d-analysis.md)).
4. Click **Run analysis**.

The results open on the **Heads** tab. The **Scan** tab gets `head_count` and `tiller_count`
and the other summary values below. The Log shows each step, including clusters that were
rejected and why.

The method assumes one plant per scan, standing upright on the ground, with the ground
fitted (keep **Fit ground plane, set z = 0** ticked).

### How heads are found

1. Only the upper half of the plant (above half the plant height) is searched.
2. Candidate points are chosen by colour: straw or yellow hue (35–65 degrees) with some
   colour saturation. Green leaves are about 80–140 degrees. If no straw-coloured heads are
   found, or the scan has no colour, PhenoForge uses shape instead: points whose
   neighbourhood is "bulky" (volumetric) rather than flat like a leaf or thin like a stem.
   The Scan tab shows which was used in `method` (`auto:colour` or `auto:shape`).
3. Candidate points are grouped into clusters.
4. A cluster is kept as a head when it is shaped like a spike: 3–15 cm long, 0.6–3 cm wide,
   2 to 10 times longer than wide, and round rather than flat in cross-section (this rejects
   yellow leaf tips). For scans that are not metric, these limits are scaled by plant height,
   assuming a 0.6 m plant.
5. Clusters low in the canopy, or much smaller than a typical head, are dropped. Clusters
   that look like two or more touching heads are split when each part looks like a head.

### How tillers are found

1. PhenoForge looks at two horizontal bands just above the ground: 5–15 % and 15–25 % of plant
   height.
2. Each band is cut into thin slices (about 1 cm). In each slice, small round blobs of stem
   size (1.2–10 mm across) are kept. Leaves crossing the slice give long or flat shapes and
   are rejected.
3. Blobs are linked from slice to slice. A tiller is a blob that continues through at least
   half of the slices of the band.
4. The band with the higher count is reported, because leaves hide stems more often than
   they fake one.

### Results

**Heads** tab, one row per head (lengths in m when metric):

| Column | Meaning |
|---|---|
| `head_id` | Head number. |
| `length`, `width`, `thickness` | Size along the head's long axis and across it. |
| `aspect` | length / width. |
| `top_height` | Height of the top of the head above the ground. |
| `centroid_x`, `centroid_y`, `centroid_z` | Centre of the head. |
| `tilt_deg` | Angle of the head from vertical. |
| `n_points` | Points in the head. |
| `mean_r`, `mean_g`, `mean_b` | Mean colour (0–1). |

Added to the **Scan** tab: `head_count`, `head_length_mean`, `head_length_sd`,
`head_width_mean`, `head_top_height_mean`, `tiller_count`, `band_low`, `band_high`
(the band used), `band_coverage`, `stem_diameter_mean`, `plant_height`, `method` and
`heuristic` (always True, as a reminder).

### Honest limits

These are heuristics. They were tuned on synthetic wheat plants (`synthetic.make_wheat`), where
they count heads and tillers to within one. Real plants are harder:

- **Touching or overlapping heads** merge into one cluster. Some are split again, but dense
  canopies are usually **undercounted**.
- **Green heads** (before ripening) have leaf colour, so the colour method finds nothing and
  the shape method is used, which is less reliable.
- **Awns** make heads look wider; very long awns can push a head outside the size limits.
- **Yellow leaf tips** can be taken for heads if they are bulky.
- **Tillers** must be visible as separate stems in the scan, with point noise well below the
  stem radius (about 1 mm point spacing). Tillers still inside a common sheath at band height
  count as one. Stems that were never seen are missed. Phone LiDAR scans are usually too
  coarse for tillers.
- Thin parts (stems, awns) are often lost or thickened in phone scans (SOP-7 notes that parts
  thinner than about 3 mm can be thickened or lost).

Use counts from a scan only after checking them against hand counts on your own plants.

## Count heads in photos with a trained detector

For field plots, dense canopies, or when you have many photos, a detector trained on your own
photos is usually more reliable than the 3D heuristic. PhenoForge uses a YOLO object detector
(from the `ultralytics` package). You draw boxes around heads in some photos, train the
detector, then use it to count heads in new photos.

This needs the optional add-on. Without it, the window shows
"Optional add-on not installed." and its tabs are greyed out. See
[Optional add-ons](addons.md). Training is much faster with an NVIDIA graphics card (GPU); on a
normal PC it works but can take hours.

The first time you train, the starting model (`yolov8n.pt`) is downloaded from the internet.

### 1 Label photos

1. Choose 50–200 photos that represent your conditions (growth stages, light, cultivars).
2. Label them with a free tool such as **Label Studio** or **CVAT**. Draw one box around each
   head. Use one label class (for example `head`).
3. Export in **YOLO** format. You get one `.txt` file per photo, with the same name as the
   photo.
4. Arrange the files like this:

```
my_heads/
    images/    photo001.jpg, photo002.jpg, ...
    labels/    photo001.txt, photo002.txt, ...
```

Photos are JPEG, PNG, TIFF or BMP. Photos without a label file are used as "no heads"
examples.

### 2 Train

1. Open **Tools > Wheat-head detector (photos)...** (or the Tools tab button
   **Wheat-head detector (photos)…**).
2. On the **1 Train** tab, **Labelled photos**: choose the `my_heads` folder (the one that
   contains `images` and `labels`). You can also type the path of a `dataset.yaml` file.
3. **Save model to**: where the trained model goes (default `head_detector` in the `PhenoForge`
   folder in your home folder).
4. **Epochs**: how many passes over the photos (default 100). More can help with few photos,
   but takes longer.
5. Click **Train**.

PhenoForge writes `dataset.yaml` into your labelled folder and keeps 20 % of the photos aside to
check the model during training. Training runs in the background; the Log shows progress.
When it finishes, the Log says `head detector saved: ...\heads\weights\best.pt`, and the model
path is filled in on the second tab.

### 3 Count heads

1. On the **2 Count heads** tab, **Photos**: choose a folder of new photos.
2. **Model**: the `best.pt` file from training (remembered from last time).
3. **Results folder**: where results go (default `heads_detected` in the `PhenoForge` folder).
4. **Confidence**: boxes with a lower score are ignored (default 0.25). Raise it if the
   detector finds heads that are not there; lower it if it misses heads.
5. Click **Count heads**.

The Log says, for example, `412 heads in 20 photos`. The results folder contains:

| File | Contents |
|---|---|
| `heads.csv` | One row per photo: `image`, `head_count`, `mean_conf` (mean box score). |
| `head_boxes.csv` | One row per box: `image`, `box`, `x1`, `y1`, `x2`, `y2` (pixels) and `conf`. |
| `<photo>_heads.png` | The photo with boxes drawn and the count written on it. |

Look at some `_heads.png` pictures to check the detector. Validate the counts against hand
counts on photos that were **not** used for training.

### From the command line

```
phenoforge heads-train D:\labels\my_heads --epochs 100 --out D:\models\heads
phenoforge heads-detect D:\photos\plot12 --weights D:\models\heads\heads\weights\best.pt --out D:\results\plot12
```

`heads-train` also has `--model` (starting model, default `yolov8n.pt`) and `--imgsz` (image
size used for training, default 1024). See [Command line](cli.md).
