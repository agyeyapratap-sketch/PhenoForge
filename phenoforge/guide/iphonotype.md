# iPhonotype packages (.ftscan)

iPhonotype is an iPhone app that guides you around a plant, takes about 90–140 photos and
builds a 3D model on the phone. It exports everything as one **.ftscan** package (a zip
file of about 250–300 MB). PhenoForge opens the package directly and measures the plant.

PhenoForge is independent of iPhonotype. It reads the package files; it does not use any
iPhonotype code. The package layout described here is as found in app version 2.3.1. Older
or newer versions may differ: anything missing is simply skipped.

For capture instructions see SOP-7 in [Capture SOPs](sops.md).

## Get the package to the PC

Use any of these:

- [Wi-Fi transfer](wifi.md) from the phone (no cables).
- OneDrive, AirDrop to a Mac, or a USB cable.

You do not need to unzip the package. A `.ftscan`, a `.ftscan.zip` or the unzipped
`.ftscan` folder all work.

Tip: rename the package with the plant ID and date, for example `W123_2026-10-19.ftscan.zip`.
The file name becomes the scan name in your results.

## Open and analyse

The quickest way:

1. On the Start page click **Analyse an iPhonotype scan**.
2. Choose the package.
3. PhenoForge loads it and runs the analysis straight away with the
   "iPhonotype app (.ftscan)" settings.
4. The results open on the **vs iPhonotype** tab.

The other way:

1. Open the package with **File > Open scan...**, the **Open scan...** button, or by
   dragging it onto the window.
2. If the settings were "Single plant (general)", PhenoForge switches them to
   "iPhonotype app (.ftscan)" for you.
3. Check the settings (see below), then click **Run analysis**.

Loading a package takes a little while the first time, because the zip is unpacked. The
unpacked copy is kept in a temporary folder, so opening it again is fast (see
[Troubleshooting](troubleshooting.md)).

## What is in the package

| Part of the package | What it is | How PhenoForge uses it |
|---|---|---|
| Gaussian-splat cloud (`.ply`, for example `splats/iphone_splat_reconstruction.ply`) | The 3D model as millions of small coloured blobs, in metres | This is the geometry PhenoForge measures. Faint splats (opacity below 0.3) are dropped on loading. |
| Textured mesh (`mesh/photogrammetry_mesh.usdz`) | Apple photogrammetry mesh, includes the pot | Not used when you open the package. You can open the USDZ on its own if you want to. |
| `manifest.json` | Plant ID, genotype, treatment, operator, notes, device, capture times, coverage, light | Read automatically (see below). |
| `3dgs/workflow.json` | Where the splat's scale came from and how confident the app is | Read automatically; decides whether the scan counts as metric. |
| `logs/native_object_capture.json` | Number of photos taken and recommended | Read automatically. |
| `analysis/on_device_aggregate_traits.json` | The app's preliminary traits (cm) | Shown next to PhenoForge's results on the **vs iPhonotype** tab. |
| `logs/imprint_tray_metadata.json` | Text the app read in view (label reading) | Shown as `label_text` on the **Package** tab. |
| `3dgs/images`, `3dgs/transforms.json`, `rgb/` | The photos and the camera position of each photo | Used by **Check vs photos** (see below). |

PhenoForge loads the geometry file it finds first in this order of file types: PLY, USDZ,
GLB, GLTF, OBJ, USDC, USD, PCD, LAS, LAZ, XYZ, PTS, STL (the largest file of a type wins).
In an iPhonotype package that is the splat PLY.

## What is read automatically

When the package loads, the Log shows a line such as
`iPhonotype package: plant W123, 138 photos, coverage 0.86, light 610 lux`.

These details are read from the package and shown on the **Package** results tab:

| Field | Meaning |
|---|---|
| `plant_id`, `genotype`, `treatment`, `operator`, `notes` | What you typed in the app before the scan. Empty if you did not fill them in. |
| `session_id`, `started_utc`, `ended_utc`, `capture_seconds` | When the scan was taken (UTC) and how long it took. |
| `scan_mode`, `scan_workflow`, `scan_target` | The app's scan type. |
| `app_version`, `device`, `ios_version` | The app and phone. |
| `photos`, `photos_recommended`, `photos_minimum` | Photos taken, and the app's ideal and minimum numbers. |
| `coverage_estimate` | The app's estimate of how completely the plant was seen (0 to 1). SOP-7 suggests 0.8 or more. |
| `light_lux_mean`, `light_lux_min`, `light_lux_max` | Light level estimated by the phone during the scan, in lux. |
| `par_mean_umol_m2_s` | The app's estimate of PAR (µmol m⁻² s⁻¹). This is a proxy from the camera, not a quantum sensor reading. |
| `leaf_reflectance_mean_percent` | The app's estimated leaf reflectance. |
| `splat_units` | Units of the splat cloud, for example `meters`. |
| `scale_source`, `scale_confidence`, `scale_verified` | Where the app's metric scale came from, its confidence, and whether the app marked it verified. |
| `used_lidar` | Whether the package says LiDAR was a primary sensor. |
| `label_text` | Text the app read in view with confidence 0.5 or more. It may include unrelated signs; type the plant ID in the app instead of relying on it. |
| `warnings` | Quality warnings written by the app. |

Fields that are empty in the package are not shown.

If the workspace library form on the left has empty **plant id**, **genotype**,
**treatment** or **notes** boxes, PhenoForge fills them from the package. To keep them in
the library, open the scan from the library and click **Save metadata** (see
[The workspace library](library.md)).

When you save results, the plant table (`<scan>_plant.csv`) starts with `plant_id`,
`genotype`, `treatment`, `operator` and `started_utc`, and the whole Package table is saved as
`<scan>_package.csv`.

## Orientation is handled for you

iPhone captures use a "Y-up" coordinate frame, so a plant would lie on its side if loaded
as is. When the package's `manifest.json` says it was captured in an iOS (ARKit) frame,
PhenoForge turns the cloud upright on loading. The Log and the scan history say
"converted Y-up to Z-up".

So: leave **Input is Y-up (glTF / phone app export)** unticked for packages. Ticking it
lays the plant on its side. If you open the splat `.ply` on its own (outside the package),
it is not turned upright, and then you do tick Y-up.

## Metric scale from the package

The splat cloud is in metres, scaled by the app from the camera path. PhenoForge marks the
scan as metric only when all of these are true:

- the geometry is a Gaussian-splat cloud,
- `3dgs/workflow.json` says the splat units are `meters`, and
- `3dgs/workflow.json` says the metric scale is verified.

Then the Log shows "metric" and the scan history says "metric from the package (source,
confidence)". The scale source is set to **Already metric (LiDAR)**.

If the package does not say the scale is verified, the scan is treated as unscaled. Set
the scale with ArUco markers or two picked points (see
[The 3D analysis tab](3d-analysis.md)).

## Check the scale with an ArUco card

The app's scale comes from the phone's motion sensors. A printed ArUco card in view is the
only independent check. SOP-7 recommends a 50 mm DICT_4X4_50 card beside the pot.

1. Open the package.
2. In **2 Metric scale**, set **Scale source** to **ArUco markers**.
3. Set **Marker side** to the size you measured on the printed card with a ruler.
4. Click **Markers image**. Check that each marker has a green outline and an ID, and that
   the "Marker sides after scaling" are close to your marker size.
5. Click **Run analysis**.
6. Read the ArUco line in the Log, for example `2 marker(s), scale x1.012, spread 0.40%`.

Because the package is already in metres, the scale factor should be close to 1. A factor
of 1.012 means the app's model was 1.2 % too small. SOP-7 suggests the marker size should be
within ±2 %.

## The results tabs for packages

Two result tabs on the 3D analysis tab are only filled for iPhonotype packages.

### vs iPhonotype

A side-by-side table of PhenoForge's whole-scan traits and the app's own traits. Columns:
`trait`, `PhenoForge`, `iPhonotype app` and `difference_percent` (PhenoForge minus app, as
a percentage of the app's value).

| Row | PhenoForge trait | App trait |
|---|---|---|
| height (cm) | `height_max` | `heightCm` |
| width (cm) | `spread_x` | `widthCm` |
| depth (cm) | `spread_y` | `depthCm` |
| convex hull volume (cm3) | `hull_volume_m3` | `hullVolumeCm3` |
| convex hull surface (cm2) | `hull_surface_m2` | `hullSurfaceCm2` |
| footprint (cm2) | `footprint_hull_m2` | `footprintCm2` |
| projected / canopy area (cm2) | `projected_area_m2` | `canopyCoverCm2` |
| greenness ExG | `exg_mean` | `plantGreennessExG` |

Only rows where both values exist are shown. PhenoForge values are converted from metres to
cm. If the scan is not metric, the PhenoForge column is empty (NaN), because the units are
unknown.

### Package

Everything listed in "What is read automatically" above. You can also jump here with
**Tools > Package information...**.

## Why PhenoForge and the app give different numbers

Expect differences. Reasons include:

- **Different cleaning.** PhenoForge removes stray points, fits the soil or table plane,
  removes the ground and keeps plant-coloured points (vegetation filter). The app does its
  own cleaning. Whether the pot is counted makes a big difference to height and volume.
- **Different definitions.** For example, PhenoForge's width and depth are the extents
  along the scan's x and y axes between the 1st and 99th percentile of points, so a few
  stray points are ignored. The app's exact definitions are not stated in the package.
- **Different data.** The app may use the mesh or top-view masks. PhenoForge uses the splat
  cloud. Sparse leaf edges are treated differently, which changes projected area and leaf
  area.
- **Different scale.** If you scale with ArUco, PhenoForge uses the card; the app uses its
  own camera-based scale.

The app's on-device traits are a preliminary estimate. Use the PhenoForge results, analyse
all scans of an experiment with the same settings, and validate them against hand
measurements before relying on them (see [Validation](validation.md)).

## Check the scan against its photos

The package contains the photos and the camera position of each photo. **Check vs photos**
draws the 3D model from each camera position and compares it with the photo. It shows
whether the model matches what the camera saw. See [Validation](validation.md) for how to
read the IoU numbers.

## From the command line

- `phenoforge info W123.ftscan.zip` prints the package details and the app's traits.
- `phenoforge analyse W123.ftscan.zip --preset iphonotype --out results` analyses it.
- `phenoforge framecheck W123.ftscan.zip --out frame_check` runs the photo check.

See [Command line](cli.md).
