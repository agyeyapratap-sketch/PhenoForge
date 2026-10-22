# PhenoForge

Open-source 3D plant phenotyping for Windows (also runs on Linux and macOS from source).
MIT licence.

PhenoForge is an independent reimplementation of the kind of workflow offered by
portable 3D phenotyping studios such as iPhonotype Studio. See [FEATURES.md](FEATURES.md) for what is covered and what is not yet.

[![Latest release](https://img.shields.io/github/v/release/agyeyapratap-sketch/PhenoForge?label=download)](https://github.com/agyeyapratap-sketch/PhenoForge/releases/latest)

## Download

| What | Link |
|---|---|
| Windows app (unzip, run `PhenoForge.exe`) | [PhenoForge-windows-x64.zip](https://github.com/agyeyapratap-sketch/PhenoForge/releases/latest/download/PhenoForge-windows-x64.zip) |
| Illustrated capture SOPs (iPhone, Android, DSLR, 3D roots, turntable, iPhone roots on a spike, iPhonotype app) | [PhenoForge-SOPs.zip](https://github.com/agyeyapratap-sketch/PhenoForge/releases/latest/download/PhenoForge-SOPs.zip) |
| Turntable print files (Bambu Studio 3MF, STL, OpenSCAD, Pi script) | [PhenoForge-turntable-print-files.zip](https://github.com/agyeyapratap-sketch/PhenoForge/releases/latest/download/PhenoForge-turntable-print-files.zip) |

All versions are on the [Releases page](https://github.com/agyeyapratap-sketch/PhenoForge/releases).

## Documentation

- **User guide**: [phenoforge/guide/index.md](phenoforge/guide/index.md). The same pages open
  inside the app: press **F1** on any tab for help on that screen, or use **Help > User guide**.
- **Capture SOPs**: illustrated PDFs in [docs/sop](docs/sop) (SOP-0 overview to SOP-7
  iPhonotype app), also in the SOP zip above.
- **Command line**: [phenoforge/guide/cli.md](phenoforge/guide/cli.md), or `phenoforge -h`.
- **What every output column means**: [phenoforge/guide/traits.md](phenoforge/guide/traits.md).

## What it does

- **Start page**: one button per job (iPhonotype scan, 3D scan, Wi-Fi receive, photos to 3D,
  whole folder, tray, wheat, fruit, roots, 2D photos, compare, validate, frame check, demo).
  Drag and drop a scan onto the window to open it.
- **Presets** for common jobs (single plant, iPhonotype package, LiDAR app, ArUco photogrammetry,
  tray, pot grid, wheat, fruit), in the app and as `--preset` on the command line.
- **Input from any capture device**
  - iPhonotype **.ftscan packages**: the Gaussian-splat cloud is loaded upright and metric when
    the app verified the scale; plant ID, genotype, treatment, operator, light/PAR estimate,
    scale source and confidence, and the app's own traits are read and shown next to
    PhenoForge's results.
  - iPhone/iPad LiDAR exports: PLY, OBJ, GLB, USDZ, zip packages, 3D Gaussian-splat PLY.
  - Android scanning-app exports; Android phone video or photos, and DSLR or mirrorless photos
    (RAW or JPEG), reconstructed with COLMAP after blur and exposure checks.
  - LAS/LAZ and PCD files, and CT TIFF stacks for roots.
  - The PhenoForge motorised turntable (`hardware/turntable`), with static-room masks for COLMAP.
- **Wi-Fi transfer** from the phone: the PC shows a QR code, the phone uploads in its browser
  (no cables, no cloud; trusted networks only, not encrypted).
- **Viewer**: RGB, approximate Gaussian **splat** view, height, greenness, plant and leaf
  colours, convex hull, auto orbit, point picking.
- **ArUco scaling**: markers are detected on a rendered top view and refined per marker.
  Scale error is under 0.1 % on synthetic data. Two-point and manual scaling too.
- **Cleaning**: downsampling, outlier removal, ground-plane levelling and removal, and a
  vegetation colour filter (ExG, GLI, VARI, hue).
- **3D shoot traits**: height (max/p99/p95/mean), spread, footprint, projected area,
  convex-hull volume, voxel volume (virtual biomass), solidity, leaf surface area, lean
  and colour indices.
- **Plant instances**: one plant, watershed for touching plants in a tray, a pot grid, or
  DBSCAN. **Leaf candidates**: connected components, region growing, or **AI leaf instances**
  with SAM 2.1 (optional add-on).
- **Wheat**: heuristic head (spike) and tiller counts from 3D scans (validate against hand
  counts), and a YOLO **head detector** you train on your own labelled photos (optional add-on).
- **Objects**: length, width, thickness, hull volume, sphericity and colour of each fruit,
  tuber or seed on a bench.
- **3D roots**: root crowns as in Sunvittayakul et al. 2022 (Sci Rep 12:10030), fibrous root
  systems via a 3D skeleton, and CT stacks.
- **2D phenotyping**: canopy cover and area in mm² from photos with an ArUco card; root
  images and videos (primary and lateral length, tips), and a **narrated root time-lapse
  video** with subtitles (spoken narration is an optional add-on).
- **Checks**: **frame check** of an iPhonotype scan against its own photos (IoU per frame),
  **video scale evidence** (was the ArUco card visible and consistent through the capture),
  colour checker correction (24 patches), validation against manual measurements (R², RMSE,
  CCC, Bland-Altman), and trait change between two scans.
- **Batch**: analyse a whole folder with one preset; one `all_scans.csv` row per scan.
- **3D print export**: colour-quantised 3MF, STL per colour, OBJ.
- **Optional local AI assistant** through Ollama (runs offline).
- **Workspace library**: projects, then sessions, then scans, with metadata, results saved
  automatically, and a trait table export to CSV.

## Install

Windows: download [PhenoForge-windows-x64.zip](https://github.com/agyeyapratap-sketch/PhenoForge/releases/latest/download/PhenoForge-windows-x64.zip)
(or build it, see [BUILD.md](BUILD.md)), unzip and run `PhenoForge.exe`. Nothing else is needed. COLMAP and
Ollama are optional extras.

From source (Python 3.10–3.12; commands for the Windows Command Prompt). Create the
environment on a local disk, not a network drive (pip often fails there with WinError 59):

```
py -3.12 -m venv %LOCALAPPDATA%\venvs\phenoforge
%LOCALAPPDATA%\venvs\phenoforge\Scripts\python -m pip install -r requirements.txt
%LOCALAPPDATA%\venvs\phenoforge\Scripts\python -m phenoforge            # desktop app
%LOCALAPPDATA%\venvs\phenoforge\Scripts\python -m phenoforge --help     # command line
```

Optional add-ons (from source only): `pip install -r requirements-ai.txt` adds SAM 2.1 leaf
instances and the wheat-head detector (`ultralytics`, with PyTorch) and spoken narration for
root videos (`pyttsx3`, `imageio-ffmpeg`). HEIC support (`pillow-heif`) is in the standard
requirements.

## Quick start

1. Print a marker sheet: Tools tab > Printable ArUco marker sheet, or
   `phenoforge markers --mm 50`. Measure the printed side with a ruler.
2. Capture. Follow the SOP for your device in `docs/sop/` (start with
   `SOP-0_Overview_capture_to_traits.pdf`).
3. Open PhenoForge and pick the job on the **Start** page, or drop the scan on the window.
   Help > Load demo scan loads a synthetic tray with known answers.
4. Check the settings on the 3D analysis tab and click **Run analysis**. Or from the command
   line:

```
phenoforge analyse W123.ftscan.zip --preset iphonotype --out results
phenoforge analyse scans\ --aruco-mm 50 --plants watershed --expected 6 --out results   # all_scans.csv
phenoforge roots3d crown.ply --mode crown --aruco-mm 30 --out roots
phenoforge images photos\ --aruco-mm 40 --out canopy
```

## Wheat notes

- Height uses `height_max` and `height_p99`. Prefer p99 for noisy phone scans.
- Leaf area uses `surface_area_m2`, an MLS-smoothed point-density estimate, or the mesh
  area when the scan is a mesh.
- Virtual biomass uses `voxel_volume_m3` and `hull_volume_m3`. Calibrate these against
  harvested dry weight with the Validation tab.
- Head and tiller counts from 3D scans are heuristics tuned on synthetic plants. Touching
  heads, green heads and tillers in a common sheath bias them (usually low). For photos,
  train the head detector on your own labelled images. Validate either against hand counts.

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
| Wheat heads and tillers (synthetic plants) | within ±1 of the truth |

These are synthetic tests. Validate against your own manual measurements before you
publish numbers.

## Credits

Open3D, OpenCV (ArUco, MCC), scikit-image, SciPy, trimesh, PySide6, pyqtgraph, usd-core,
laspy, rawpy, pillow-heif, COLMAP (optional, separate install), Ollama (optional), and the
optional add-ons ultralytics (SAM 2.1, YOLO), pyttsx3 and imageio-ffmpeg. Root crown traits
follow Sunvittayakul et al. 2022, *Sci Rep* 12:10030. SOP illustrations were made with BioRender.
