# Feature parity with iPhonotype Studio (macOS)

The Studio feature list below comes from the public iPhonotype website and support page
(iphonotype.com, Studio 2.2.2, checked October 2026). The Studio itself was not run. The
list therefore describes what the site says, not what was tested. PhenoForge is an
independent reimplementation. It uses none of iPhonotype's code, models or assets.

Status key: **Done** means it works and is tested on synthetic data. **Partial** means it
works but is narrower than the Studio feature. **Not yet** means it is missing. Statuses
were checked against the code in October 2026. "Tested" means automated tests on synthetic
data; real-plant validation is still the user's job (see the Validation tab).

| # | Studio feature (as described on the website) | PhenoForge | Status |
|---|---|---|---|
| 1 | Workspace library: experiments, trays, sessions and scan packages by type and date | Workspace dock: projects, sessions, scans, metadata and results (saved automatically for scans opened from the library); trait table export to CSV (`library.py`) | Done |
| 2 | Import iPhone captures (LiDAR scans, 3DGS packages, meshes) | iPhonotype `.ftscan` packages (splat cloud loaded upright; plant ID, light, scale provenance and the app's traits read by `ftscan.py`), PLY (including 3DGS splat), OBJ, GLB, USD/USDZ, LAS/LAZ, PCD, zip and folder packages; Android and DSLR photos, video and RAW (`io.py`, `capture.py`) | Done (wider) |
| 3 | Wi-Fi discovery of the iPhone and package handoff | The PC runs a small upload server and shows a QR code; the phone opens it in Safari and uploads files from the Files app; optional import into a library session (`handoff.py`, `phenoforge receive`). Plain HTTP with an access code, for trusted networks | Done (QR + browser upload, not automatic discovery) |
| 4 | 3D reconstruction from captures | COLMAP photogrammetry if COLMAP is installed; app exports load directly. There is no built-in Gaussian-splat training | Partial |
| 5 | Viewer: splat, points, hull and full-frame views, auto orbit | Point and mesh viewer with RGB, Splat, height, greenness, plant and leaf colours; convex hull overlay; auto orbit; Ctrl+click picking; snapshot; synced views on the Compare tab. Splat mode draws soft world-sized discs from the 3DGS scales and opacities | Done (approximate disc splats, not a full 3DGS rasteriser) |
| 6 | Verified metric scale before physical measurements | ArUco markers on a top-down render with per-marker refinement (under 0.1 % on tests); two-point manual scale; manual factor; the iPhonotype package's own scale source and confidence are read and shown. PLY/OBJ/GLB from LiDAR apps carry no units: "Already metric", the LiDAR preset or `--metric` treats them as metres | Done |
| 7 | Above-ground traits: height, canopy area, volume, colour-derived greenness | Height (max, p99, p95, mean), spread, footprint, projected area, hull and voxel volume, solidity, surface (leaf) area, lean, ExG, GLI, VARI and hue; side-by-side table against the app's own traits for packages | Done |
| 8 | Plant occupancy detection, plant count, plant-by-plant tray breakdowns, dense trays (for example Arabidopsis) | Watershed, pot-grid or DBSCAN instances with per-plant traits; 2D batch blob counts | Done |
| 9 | Leaf instances with bundled offline SAM 2.1 ("provisional visible candidates") | Geometric leaf candidates (connected components or region growing), or multi-view SAM 2.1 leaf instances back-projected onto the cloud (`leafsam.py`). SAM is not bundled: `pip install ultralytics`, and the 160 MB model downloads on first use, then runs offline. Tested with a stand-in segmenter on synthetic plants, not on a real-plant benchmark | Done (optional add-on) |
| 10 | Batch 2D phenotyping: per-image summaries, segmented overlays, CSV | Images tab and `phenoforge images`: vegetation mask, blobs, mm² from an ArUco card, overlays and CSV | Done |
| 11 | Root phenotyping: root masking, roots plus shoots, root-tip tracking over frames, narrated root video | 2D roots: mask, skeleton, primary and lateral lengths, tips, video frames. 3D roots: crowns (Sunvittayakul et al. 2022), fibrous systems and CT stacks. Narrated time-lapse video of a root photo series with captions, SRT subtitles and a traits CSV; speech uses the offline system voice through `pyttsx3` + `imageio-ffmpeg` (optional; silent video with subtitles otherwise). A tip-matching function exists (`roots.track_tips`) but is not used by the tab or CLI | Done (wider); narration Done (offline Windows voice, optional) |
| 12 | ColorChecker reference photo for colour normalisation | Colour tab: 24-patch detection (MCC or manual corners), 3×4 linear-RGB correction applied to images and point colours | Done |
| 13 | Benchmark validation: mask comparison, RGB frame comparison, overlays, area correction (R², MAE) | Validation tab: mask IoU and Dice; trait agreement (MAE, RMSE, R², CCC, Bland-Altman, linear calibration) with plots. Frame check: the scan is rendered from each camera pose in a package (`transforms.json`) and compared with the photo (IoU, Dice, precision, recall, overlays) (`framecheck.py`) | Done |
| 14 | Longitudinal comparison and growth review | Compare tab and `phenoforge compare`: both scans analysed with the same settings, synced side-by-side views and a trait change table. Registration (FPFH, RANSAC, ICP) and cloud-to-cloud distance exist in `compare.py` but are not used by the tab or the CLI, so scans are not aligned or differenced point by point | Partial |
| 15 | Scan to multi-colour print: learned colour mapping, 3MF and STL | Mesh reconstruction, k-means colour quantisation in Lab, 3MF with materials, STL per colour, OBJ | Done (k-means, not a learned mapping) |
| 16 | Local AI assistant via Ollama for questions about scans and traits | Assistant tab and Ollama client; sends the trait summary as context; offline | Done |
| 17 | QR-linked lots and GPS-tagged field records | QR text and EXIF GPS are decoded and shown per photo on the Images tab; they are not written to the CSV tables. Library metadata has `qr` and `gps` fields to fill by hand | Partial |
| 18 | Fruit and postharvest workflows: object dimensions on benches or processing lines | Per-object length, width, thickness, hull volume and area, equivalent diameter, sphericity, elongation, flatness and colour on a bench (`objects.py`, "Fruit / objects on a bench" preset). No processing-line (moving conveyor) mode and no fruit-specific models | Done for benches (generic) |
| 19 | Model training with optional tools, and Mac-side model orchestration | Train and run a YOLO wheat-head detector on your own labelled photos (YOLO format from Label Studio or CVAT), in the app and as `heads-train` / `heads-detect` (optional `ultralytics`). No other model training | Partial (YOLO head detector only) |
| 20 | Synchronised-video metric evidence | Per-frame audit of the ArUco card through a capture video: markers seen, sharpness, skew, mm/px, usable frames; CSV, plot and contact sheet (`videoevidence.py`, `phenoforge scale-evidence`). It records evidence; it does not rescale scans | Done (ArUco scale audit) |

## Additions not in the Studio

- Native Windows build and a command line for batch scripts and HPC, with `--preset` and a
  folder-wide `all_scans.csv`.
- A Start page with one button per job, ready-made presets, drag and drop, and an in-app user
  guide (F1).
- Android and DSLR capture routes with SOPs, RAW development and blur and exposure checks.
- Cassava-style 3D root crown traits, fibrous root skeletons and CT TIFF stacks.
- An open-hardware motorised turntable (printable parts, Pi 5 control) with automatic static-background masks.
- Synthetic scenes with known answers (Help > Load demo scan, Help > Load demo root crown) and an automated test suite.

## Wheat-specific gaps

| Trait | Status |
|---|---|
| Plant height | Done |
| Leaf (surface) area | Done; leaf counts are geometric or SAM candidates only |
| Virtual biomass (voxel or hull volume) | Done. Calibrate it against dry weight with the Validation tab |
| Head (spike) counts | Done (heuristic; validate). 3D: colour or shape candidates, spike-shaped clusters, within ±1 on synthetic plants. Photos: YOLO detector trained on your labels (optional add-on) |
| Tiller counts | Done (heuristic; validate). Stem cross-sections tracked through bands just above the ground; needs stems resolved in the scan (about 1 mm point spacing) |
