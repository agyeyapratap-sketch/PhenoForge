# Feature parity with iPhonotype Studio (macOS)

The Studio feature list below comes from the public iPhonotype website and support page
(iphonotype.com, Studio 2.2.2, checked October 2026). The Studio itself was not run. The
list therefore describes what the site says, not what was tested. PhenoForge is an
independent reimplementation. It uses none of iPhonotype's code, models or assets.

Status key: **Done** means it works and is tested on synthetic data. **Partial** means it
works but is narrower than the Studio feature. **Not yet** means it is missing.

| # | Studio feature (as described on the website) | PhenoForge | Status |
|---|---|---|---|
| 1 | Workspace library: experiments, trays, sessions and scan packages by type and date | Workspace dock: projects, sessions, scans and results; trait table export to CSV (`library.py`) | Done |
| 2 | Import iPhone captures (LiDAR scans, 3DGS packages, meshes) | PLY (including 3DGS splat), OBJ, GLB, USD/USDZ, LAS/LAZ, PCD, zip and folder packages; Android and DSLR photos, video and RAW (`io.py`, `capture.py`) | Done (wider) |
| 3 | Wi-Fi discovery of the iPhone and package handoff | Files are copied over by USB, cloud folder or AirDrop, then imported | Not yet |
| 4 | 3D reconstruction from captures | COLMAP photogrammetry if COLMAP is installed; app exports load directly. There is no built-in Gaussian-splat training | Partial |
| 5 | Viewer: splat, points, hull and full-frame views, auto orbit | Point and mesh viewer with RGB, height, label and greenness colours, hull overlay, picking, snapshot and synced views | Partial (no splat rendering) |
| 6 | Verified metric scale before physical measurements | ArUco markers on a top-down render with per-marker refinement (under 0.1 % on tests); two-point manual scale; manual factor | Done |
| 7 | Above-ground traits: height, canopy area, volume, colour-derived greenness | Height (max, p99, p95, mean), spread, footprint, projected area, hull and voxel volume, solidity, surface (leaf) area, lean, ExG, GLI, VARI and hue | Done |
| 8 | Plant occupancy detection, plant count, plant-by-plant tray breakdowns, dense trays (for example Arabidopsis) | Watershed, pot-grid or DBSCAN instances with per-plant traits; 2D batch blob counts | Done |
| 9 | Leaf instances with bundled offline SAM 2.1 ("provisional visible candidates") | Geometric leaf candidates from connected components or region growing. No SAM model is bundled | Partial |
| 10 | Batch 2D phenotyping: per-image summaries, segmented overlays, CSV | Images tab and `phenoforge images`: vegetation mask, blobs, mm² from an ArUco card, overlays and CSV | Done |
| 11 | Root phenotyping: root masking, roots plus shoots, root-tip tracking over frames, narrated root video | 2D roots: mask, skeleton, primary and lateral lengths, tip tracking from video frames. 3D roots: crowns (Sunvittayakul et al. 2022), fibrous systems and CT stacks. No audio narration | Done (wider), narration not yet |
| 12 | ColorChecker reference photo for colour normalisation | Colour tab: 24-patch detection (MCC or manual corners), 3×4 linear-RGB correction applied to images and point colours | Done |
| 13 | Benchmark validation: mask comparison, RGB frame comparison, overlays, area correction (R², MAE) | Validation tab: mask IoU and Dice; trait agreement (MAE, RMSE, R², CCC, Bland-Altman, linear calibration) with plots. No side-by-side RGB frame aligner | Partial |
| 14 | Longitudinal comparison and growth review | Compare tab: registration (FPFH, RANSAC and ICP), cloud-to-cloud distance and trait change table | Done |
| 15 | Scan to multi-colour print: learned colour mapping, 3MF and STL | Mesh reconstruction, k-means colour quantisation in Lab, 3MF with materials, STL per colour, OBJ | Done (k-means, not a learned mapping) |
| 16 | Local AI assistant via Ollama for questions about scans and traits | Assistant tab and Ollama client; sends the trait summary as context; offline | Done |
| 17 | QR-linked lots and GPS-tagged field records | QR decoding from photos and EXIF GPS into the trait table | Done |
| 18 | Fruit and postharvest workflows: object dimensions on benches or processing lines | Generic per-object traits through DBSCAN instances (size, volume, colour). No fruit-specific models | Partial |
| 19 | Model training with optional tools, and Mac-side model orchestration | None | Not yet |
| 20 | Synchronised-video metric evidence | Sharp-frame extraction from video for photogrammetry only | Partial |

## Additions not in the Studio

- Native Windows build and a command line for batch scripts and HPC.
- Android and DSLR capture routes with SOPs, RAW development and blur and exposure checks.
- Cassava-style 3D root crown traits, fibrous root skeletons and CT TIFF stacks.
- Synthetic scenes with known answers (Help > Demo) and an automated test suite.

## Wheat-specific gaps

| Trait | Status |
|---|---|
| Plant height | Done |
| Leaf (surface) area | Done; leaf counts are geometric candidates only |
| Virtual biomass (voxel or hull volume) | Done. Calibrate it against dry weight with the Validation tab |
| Head (spike) counts | Not yet. A trained detector is needed (2D YOLO on photos, or 3D on clouds). The hue filter and DBSCAN give a manual starting point |
| Tiller counts | Not yet |
