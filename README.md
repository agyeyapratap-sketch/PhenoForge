# PhenoForge

Open-source 3D plant phenotyping for Windows (also runs on Linux and macOS from source).
MIT licence.

PhenoForge is an independent reimplementation of the kind of workflow offered by
portable 3D phenotyping studios such as iPhonotype Studio. It contains none of their code,
assets or branding. See [FEATURES.md](FEATURES.md) for what is covered and what is not yet.

## What it does

- **Input from any capture device**
  - iPhone/iPad LiDAR exports: PLY, OBJ, GLB, USDZ, zip packages, 3D Gaussian-splat PLY.
  - Android scanning-app exports.
  - Android phone video or photos, and DSLR or mirrorless photos (RAW or JPEG). These are
    reconstructed with COLMAP after blur and exposure checks.
  - LAS/LAZ and PCD files, and CT TIFF stacks for roots.
- **ArUco scaling**: markers are detected on a rendered top view and refined per marker.
  Scale error is under 0.1 % on synthetic data.
- **Cleaning**: downsampling, outlier removal, cropping, ground-plane levelling and removal,
  and a vegetation colour filter (ExG, GLI, VARI, hue).
- **3D shoot traits**: height (max/p99/p95/mean), spread, footprint, projected area,
  convex-hull volume, voxel volume (virtual biomass), solidity, leaf surface area, lean
  and colour indices.
- **Plant instances**: one plant, watershed on a height map, a pot grid, or DBSCAN.
  **Leaf candidates**: connected components or region growing.
- **3D roots**:
  - Root crowns as in Sunvittayakul et al. 2022 (Sci Rep 12:10030): crown volume,
    number of storage roots, length, diameter, angle and volume per root, spread and depth.
  - Fibrous root systems via a 3D skeleton: total length, tips, branching.
  - CT stacks.
- **2D phenotyping**: batch canopy cover and area in mm² from photos with an ArUco card, QR
  labels and GPS from EXIF. 2D root images and videos: primary and lateral length, tip tracking.
- **Colour checker correction** (24 patches), **validation** against manual measurements
  (R², RMSE, CCC, Bland-Altman), **scan comparison** over time (registration and trait change).
- **3D print export**: colour-quantised 3MF, STL per colour, OBJ.
- **Optional local AI assistant** through Ollama (runs offline).
- **Workspace library**: projects, then sessions, then scans, with a trait table export to CSV.

## Install

Windows: download `PhenoForge-windows-x64.zip` from a release (or build it, see
[BUILD.md](BUILD.md)), unzip and run `PhenoForge.exe`. Nothing else is needed. COLMAP and
Ollama are optional extras.

From source (Python 3.10–3.12):

```
python -m pip install -r requirements.txt
python -m phenoforge            # desktop app
python -m phenoforge --help     # command line
```

## Quick start

1. Print a marker sheet: Tools tab > Marker sheet, or `phenoforge markers --mm 50`.
   Measure the printed side with a ruler.
2. Capture. Follow the SOP for your device in `docs/sop/`:
   - `SOP-1_iPhone_LiDAR.pdf`
   - `SOP-2_Android_phone.pdf`
   - `SOP-3_DSLR_mirrorless.pdf`
   - `SOP-4_3D_roots.pdf`
   - `SOP-0_Overview_capture_to_traits.pdf` for the whole flow.
3. Import: Tools tab > Import from device, or `phenoforge capture <file|video|folder> --device auto`.
4. Analyse: on the 3D analysis tab set the marker size and plant mode, then Run. Or from
   the command line:

```
phenoforge analyse scan.ply --aruco-mm 50 --plants watershed --expected 6 --leaves components --out results
phenoforge roots3d crown.ply --mode crown --aruco-mm 30 --out roots
phenoforge images photos\ --aruco-mm 40 --out canopy.csv
```

Help > Demo scan and Help > Demo root crown load synthetic examples with known answers.

## Wheat notes

- Height uses `height_max` and `height_p99`. Prefer p99 for noisy phone scans.
- Leaf area uses `surface_area_m2`, an MLS-smoothed point-density estimate, or the mesh
  area when the scan is a mesh.
- Virtual biomass uses `voxel_volume_m3` and `hull_volume_m3`. Calibrate these against
  harvested dry weight with the Validation tab.
- Head counts are not automatic yet. Use the hue vegetation filter to keep straw-coloured
  heads, then the leaf candidates or DBSCAN instances as a starting point.

## Accuracy on synthetic data (tests/)

| Check | Result |
|---|---|
| ArUco scale, 3 markers, unknown scale ×3.7, 12° tilt | < 0.1 % error |
| Plant height, 6 plants | within 3 % |
| Plants found by watershed | 6 / 6 |
| Leaf surface area | about +4 % (clean), +13 % (heavy noise) |
| Root crown volume | within 1.5–3 % |
| Storage roots found, angle, length | all found, about ±4°, within 5–10 % |
| Fibrous root length, tips | +9 %, 21 found (truth 20) |

These are synthetic tests. Validate against your own manual measurements before you
publish numbers.

## Credits

Open3D, OpenCV (ArUco, MCC), scikit-image, SciPy, trimesh, PySide6, pyqtgraph, usd-core,
laspy, rawpy, COLMAP (optional, separate install) and Ollama (optional). Root crown traits
follow Sunvittayakul et al. 2022, *Sci Rep* 12:10030. SOP illustrations were made with BioRender.
