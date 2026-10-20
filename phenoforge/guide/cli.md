# Command line

Everything important in PhenoForge can also be run from a command line (PowerShell or a
terminal). This is useful for many files, for repeating exactly the same analysis, and for
running on a server or HPC.

## How to start it

| Installation | Command |
|---|---|
| Windows zip | `phenoforge-cli.exe <command> ...` in the PhenoForge folder |
| From source | `python -m phenoforge <command> ...` (with the PhenoForge environment's Python) |
| Installed with `pip install .` | `phenoforge <command> ...` |

The examples below use `phenoforge`. Replace it with the command for your installation.

- `phenoforge -h` lists all commands.
- `phenoforge <command> -h` lists the options of one command.
- `phenoforge` with no command, or `phenoforge gui`, starts the desktop app.

Put paths that contain spaces in quotes, for example `"D:\My scans\plant 1.ply"`.

## Command list

| Command | What it does |
|---|---|
| `analyse` | 3D traits for scans (files or folders) |
| `images` | 2D canopy phenotyping of photos |
| `roots` | root traits from images or videos |
| `roots3d` | 3D root traits: root crowns, fibrous systems, CT stacks |
| `colorcal` | fit a colour correction from a colour-checker photo |
| `validate` | agreement between predicted and reference CSVs |
| `compare` | trait change between two scans |
| `print` | multi-colour 3D print bundle (3MF, STL per colour, OBJ) |
| `markers` | printable ArUco marker sheet |
| `reconstruct` | photogrammetry with COLMAP (if installed) |
| `capture` | import from iPhone LiDAR, Android, DSLR or the turntable rig |
| `presets` | list the ready-made analysis settings |
| `info` | what is in a scan or iPhonotype package |
| `receive` | receive scans from a phone over Wi-Fi |
| `heads-train` | train a wheat-head detector on labelled photos (add-on) |
| `heads-detect` | count wheat heads in photos with a trained detector (add-on) |
| `rootvideo` | narrated video of a root image time series |
| `scale-evidence` | check the ArUco scale through a capture video |
| `framecheck` | compare an iPhonotype scan with its own photos |
| `demo` | write a synthetic tray scan with ArUco markers |
| `gui` | start the desktop app |

## analyse

3D traits for one or more scans. Inputs can be files or folders. A folder is expanded to the
scan files directly inside it (not sub-folders); an `.ftscan` folder counts as one scan.

```
phenoforge analyse plant.ply --aruco-mm 50 --out results
phenoforge analyse W123.ftscan.zip --preset iphonotype --out results
phenoforge analyse tray.ply --aruco-mm 50 --plants watershed --expected 6 --leaves none --out results
phenoforge analyse D:\scans\2026-10-20 --preset iphonotype --out D:\results\2026-10-20
```

For each scan it writes the same files as **Save results** in the app (`<scan>_traits.json`,
`<scan>_plant.csv` and the other tables) and prints the main traits. With more than one scan it
also writes **`all_scans.csv`**: one row per scan with `scan`, `plant_id`, `genotype`,
`treatment` (for packages) and the whole-scan traits. See [Analyse a whole folder](batch.md).

Options (the same options are used by `compare` and `print`):

| Option | Meaning | Default |
|---|---|---|
| `--preset NAME` | Ready-made settings; any part of a preset name, e.g. `iphonotype`, `wheat`, `tray`, `fruit`, `grid`, `lidar`, `aruco`, `single`. Options you give explicitly still win. | none |
| `--out FOLDER` | Output folder. | `phenoforge_results` |
| `--voxel V` | Downsample voxel in scan units; 0 = off. | 0 |
| `--no-outliers` | Do not remove stray points. | |
| `--no-ground` | Do not fit or align the ground plane. | |
| `--keep-ground` | Align to the ground but keep the ground points. | |
| `--y-up` | Input is Y-up (glTF/USDZ from phone apps). | |
| `--vegetation {exg,gli,vari,hue,none}` | Vegetation filter. | exg |
| `--veg-threshold T` | Fixed index threshold (default automatic). | auto |
| `--aruco-mm MM` | Printed ArUco marker side in mm; turns on ArUco scaling. | 0 (off) |
| `--aruco-dict NAME` | ArUco dictionary. | DICT_4X4_50 |
| `--aruco-ids LIST` | Comma-separated marker IDs to accept, e.g. `0,1,2,3`. | all |
| `--scale F` | Manual scale factor (multiplies coordinates). | 0 (off) |
| `--metric` | The file is already in metres (LiDAR app export): report metric units without scaling. Also set by `--preset lidar`. | |
| `--plants {single,watershed,grid,dbscan}` | Plant separation. | single |
| `--expected N` | Expected number of plants. | auto |
| `--grid ROWS COLS` | Pot grid rows and columns (with `--plants grid`). | |
| `--pitch-mm MM` | Pot pitch in mm (with `--plants grid`). | 0 |
| `--leaves {none,components,region,sam}` | Leaf candidates; `sam` needs the AI add-on. | components |
| `--heads` | Count wheat heads (heuristic). | |
| `--tillers` | Count tillers. | |
| `--objects` | Dimensions of each separate object. | |
| `--largest-cluster` | Keep only the largest connected part(s). | |
| `--save-cloud` | Also write the cleaned, labelled cloud as `<scan>_clean.ply`. | |

Note on `--preset`: the preset fills in every option that you left at its default value. If you
type an option with the same value as its default (for example `--vegetation exg` together with
`--preset wheat`), the preset's value is used.

## presets

```
phenoforge presets
```

Lists the preset names, their descriptions and the options they set. See
[The 3D analysis tab](3d-analysis.md).

## info

```
phenoforge info W123.ftscan.zip
phenoforge info D:\scans\inbox
```

For each scan: number of points, mesh or not, metric or not, file format. For iPhonotype
packages also every package field (plant ID, light, scale source and so on) and the app's
traits (prefixed `app_`). See [iPhonotype](iphonotype.md).

## images

2D canopy phenotyping of photos (files or folders).

```
phenoforge images D:\photos\tray3 --aruco-mm 40 --out D:\results\tray3
phenoforge images top_view.jpg --method hsv --min-blob 500
```

| Option | Meaning | Default |
|---|---|---|
| `--out` | Output folder. | `phenoforge_images` |
| `--aruco-mm` | Marker side in mm (0 = pixels only). | 0 |
| `--aruco-dict` | ArUco dictionary. | DICT_4X4_50 |
| `--method {exg,hsv}` | Plant mask. | exg |
| `--min-blob` | Minimum blob size in pixels. | 200 |

Writes `images_summary.csv`, `images_blobs.csv` and an overlay and mask per photo. See
[Photos from above](images-2d.md).

## roots

Root traits from photos, folders of photos or videos.

```
phenoforge roots D:\dishes --aruco-mm 20 --roots dark --out root_results
phenoforge roots growth.mp4 --every 15 --stitch --out root_results
```

| Option | Meaning | Default |
|---|---|---|
| `--out` | Output folder. | `phenoforge_roots` |
| `--mm-per-px` | Known scale in mm per pixel. | none |
| `--aruco-mm` | Marker side in mm (used when `--mm-per-px` is not given). | 0 |
| `--roots {auto,dark,light}` | Root colour against the background. | auto |
| `--every N` | Keep every Nth video frame. | 10 |
| `--stitch` | Stitch video frames into one panorama. | |

Writes `roots.csv` and `<image>_roots.png` overlays. Without `--stitch`, every kept video frame
is measured. See [Root photos and video](roots-2d.md).

## rootvideo

Narrated time-lapse video of root photos, in time order (sorted by file name).

```
phenoforge rootvideo D:\rhizotron3 --aruco-mm 20 --title "Rhizotron 3" --out rhizotron3.mp4
phenoforge rootvideo D:\rhizotron3 --mm-per-px 0.05 --silent --seconds 2
```

| Option | Meaning | Default |
|---|---|---|
| `--out` | Video file. | `roots_video.mp4` |
| `--mm-per-px` | Known scale. | none |
| `--aruco-mm` | Marker side in mm. | 0 |
| `--roots {auto,dark,light}` | Root colour. | auto |
| `--seconds` | Seconds per image. | 3 |
| `--title` | Title in the caption. | empty |
| `--silent` | No spoken narration (subtitles only). | |

Writes the MP4, an `.srt` subtitle file and `<name>_traits.csv`, and prints a summary.

## roots3d

3D root traits.

```
phenoforge roots3d crown.ply --mode crown --aruco-mm 30 --stem-mm 60 --sectors 2 --out roots
phenoforge roots3d washed.ply --mode fibrous --axis -z --voxel-mm 1 --out roots
phenoforge roots3d stack.tif --mode ct --ct-voxel-mm 0.1 --ct-invert --out ct_roots
```

| Option | Meaning | Default |
|---|---|---|
| `--mode {crown,fibrous,ct}` | Root crown, fibrous root system, or CT/MRI TIFF stack (file or folder of slices). | crown |
| `--out` | Output folder. | `phenoforge_roots3d` |
| `--axis` | Direction from roots to stem: z, -z, x, -x, y, -y or pca. | z |
| `--stem-mm` | Length of stem stub to cut off the top (crown). | 0 |
| `--no-green` | Do not remove a green background sheet (crown). | |
| `--no-plane` | Do not remove a flat background plane (crown). | |
| `--aruco-mm`, `--aruco-dict` | ArUco scaling. | 0, DICT_4X4_50 |
| `--scale` | Manual scale factor. | 0 |
| `--voxel-mm` | Voxel size in mm; 0 = automatic. | 0 |
| `--depth` | Remesh depth for the automatic voxel. | 8 |
| `--sectors` | 1 = whole crown, 2 = split in half as in the paper. | 1 |
| `--core-mm` | Crown core radius in mm; 0 = automatic. | 0 |
| `--weight-kg` | Fresh root weight for root density. | 0 |
| `--ct-voxel-mm` | CT voxel size in mm. | 0.1 |
| `--ct-invert` | Roots are darker than the background (CT). | |
| `--save-cloud` | Write the labelled crown cloud and the remeshed surface (crown). | |

Writes `roots3d.csv` (one row per input) and, for crowns, `roots3d_individual_roots.csv`. See
[Roots in 3D](roots-3d.md).

## colorcal

Fit a colour correction from a 24-patch colour chart photo.

```
phenoforge colorcal chart.jpg --out colour_correction.json
phenoforge colorcal chart.jpg --corners 102 88 1630 95 1622 1110 98 1102 --apply img1.jpg img2.jpg
```

| Option | Meaning | Default |
|---|---|---|
| `--out` | Correction file (JSON). | `colour_correction.json` |
| `--corners` | Eight numbers: chart corners x y in the order top-left, top-right, bottom-right, bottom-left. Needed when the chart is not found automatically. | |
| `--reference` | JSON with 24 sRGB values for your chart. | standard values |
| `--apply` | Images to correct; written as `<name>_cc.png`. | |

See [Colour correction](colour.md).

## validate

Agreement between a predicted and a reference CSV.

```
phenoforge validate all_scans.csv hand_measurements.csv --key scan --columns height_max,surface_area_m2 --out agreement.json
```

| Option | Meaning | Default |
|---|---|---|
| `--key` | Join column present in both files. | scan |
| `--columns` | Comma-separated columns; empty = all shared numeric columns. | all |
| `--out` | Save the result as JSON. | not saved |

Prints MAE, RMSE, bias, R², CCC, limits of agreement and calibration per trait. See
[Validation](validation.md).

## compare

Trait change between two scans, analysed with the same options as `analyse`.

```
phenoforge compare week1.ply week3.ply --aruco-mm 50 --out growth
```

Prints each trait as `a -> b (change %)` and writes `comparison.csv` in the `--out` folder
(default `phenoforge_results`). See [Compare](compare.md).

## print

Multi-colour 3D print bundle. Takes the same options as `analyse` for cleaning, plus:

```
phenoforge print plant.ply --colours 4 --height-mm 120 --out print_files
phenoforge print plant.obj --raw --mesh existing --height-mm 0 --out print_files
```

| Option | Meaning | Default |
|---|---|---|
| `--raw` | Skip cleaning, print the scan as is. | |
| `--colours` | Number of colours. | 4 |
| `--height-mm` | Print height; 0 = true size. | 120 |
| `--mesh {poisson,alpha,ball,existing}` | Surface method. | poisson |
| `--depth` | Poisson depth. | 9 |
| `--base-mm` | Base plate thickness. | 2 |

See [3D print export](print.md).

## markers

Printable ArUco marker sheet.

```
phenoforge markers --mm 50 --out aruco_sheet.png
phenoforge markers --first 10 --count 4 --mm 30 --out small_markers.png
```

| Option | Meaning | Default |
|---|---|---|
| `--out` | PNG file. | `aruco_sheet.png` |
| `--aruco-dict` | Dictionary. | DICT_4X4_50 |
| `--first` | First marker ID. | 0 |
| `--count` | Number of markers. | 9 |
| `--mm` | Marker side in mm. | 50 |
| `--dpi` | Print resolution. | 300 |

Print at 100 % and measure a marker with a ruler.

## reconstruct

Photogrammetry with COLMAP (must be installed separately).

```
phenoforge reconstruct D:\photos\plant1 --colmap "C:\COLMAP\COLMAP.bat" --quality high --out plant1_colmap
```

| Option | Meaning | Default |
|---|---|---|
| `--out` | Work folder. | `colmap_work` |
| `--colmap` | Path to COLMAP (or put it on PATH, or set the `COLMAP_PATH` environment variable). | search |
| `--quality {low,medium,high,extreme}` | Quality. | medium |

Prints the path of the model (`fused.ply`, or `sparse.ply` without a GPU).

## capture

Import from a capture device: scan files are loaded, photos and videos are prepared and
reconstructed with COLMAP.

```
phenoforge capture plant_video.mp4 --device android --out plant1
phenoforge capture D:\dslr\plant1 --device dslr --colmap "C:\COLMAP\COLMAP.bat" --out plant1
phenoforge capture D:\turntable\session_04 --prepare-only --out session_04_prepared
```

| Option | Meaning | Default |
|---|---|---|
| `--device {auto,iphone_lidar,android,dslr,turntable}` | Device type. | auto |
| `--out` | Work folder. | `phenoforge_capture` |
| `--prepare-only` | Only make the clean photo or frame folder (and turntable masks); no COLMAP. | |
| `--frames` | Frames to keep from a video. | 120 |
| `--colmap` | Path to COLMAP. | search |
| `--quality` | COLMAP quality. | medium |

Writes `<name>_scan.ply` in the output folder. Photogrammetry scans are not metric: scale them
with `--aruco-mm` when you analyse them. See [Tools](tools.md).

## receive

Receive files from a phone over Wi-Fi.

```
phenoforge receive --inbox D:\scans\inbox
phenoforge receive --inbox D:\scans\inbox --port 8800
```

| Option | Meaning | Default |
|---|---|---|
| `--inbox` | Folder for received files. | `phenoforge_inbox` |
| `--port` | Network port. | 8765 |
| `--token` | Fixed access code in the link. | random |

Prints a QR code in the terminal and the address to open on the phone. Press Ctrl+C to stop.
See [Wi-Fi transfer](wifi.md).

## heads-train

Train a wheat-head detector (needs the `ultralytics` add-on).

```
phenoforge heads-train D:\labels\my_heads --epochs 100 --out D:\models\heads
phenoforge heads-train D:\labels\my_heads\dataset.yaml --model yolov8s.pt --imgsz 1280
```

| Option | Meaning | Default |
|---|---|---|
| `data` | A folder with `images/` and `labels/` (YOLO format), or a `dataset.yaml`. | |
| `--out` | Output folder. | `head_detector` |
| `--epochs` | Training epochs. | 100 |
| `--model` | Starting model. | `yolov8n.pt` |
| `--imgsz` | Training image size in pixels. | 1024 |

Prints the path of `best.pt`. See [Wheat](wheat.md).

## heads-detect

Count heads in photos with a trained detector.

```
phenoforge heads-detect D:\photos\plot12 --weights D:\models\heads\heads\weights\best.pt --out D:\results\plot12
```

| Option | Meaning | Default |
|---|---|---|
| `--weights` | `best.pt` from `heads-train` (required). | |
| `--out` | Output folder. | `heads_detected` |
| `--conf` | Minimum box confidence. | 0.25 |

Writes `heads.csv`, `head_boxes.csv` and `<photo>_heads.png`.

## scale-evidence

Check that the ArUco card stayed visible and consistent through a capture video.

```
phenoforge scale-evidence capture.mp4 --mm 50 --out evidence
phenoforge scale-evidence capture.mp4 --mm 50 --every 2 --aruco-dict DICT_4X4_50
```

| Option | Meaning | Default |
|---|---|---|
| `--mm` | Printed marker side in mm (required). | |
| `--aruco-dict` | Dictionary. | DICT_4X4_50 |
| `--every` | Check every Nth frame. | 5 |
| `--out` | Output folder. | `scale_evidence` |

Writes a CSV, a plot and a picture of the sharpest frames, and prints the summary. See
[Tools](tools.md).

## framecheck

Compare an iPhonotype scan with its own photos.

```
phenoforge framecheck W123.ftscan.zip --out frame_check
phenoforge framecheck W123.ftscan.zip --frames 30 --out frame_check
```

| Option | Meaning | Default |
|---|---|---|
| `--frames` | Maximum number of photos to compare (evenly spaced). | 12 |
| `--out` | Output folder. | `frame_check` |

Writes `frame_check.csv` (one row per photo) and `overlay_<photo>.png` for the three worst
photos, and prints the summary (mean, median and minimum IoU). See [Validation](validation.md).

## demo

```
phenoforge demo --out demo_tray.ply
phenoforge analyse demo_tray.ply --aruco-mm 50 --plants watershed --expected 6
```

Writes a synthetic tray of six plants with three 50 mm DICT_4X4_50 markers, deliberately
unscaled, and prints the true scale factor so you can check the ArUco result.

## gui

```
phenoforge gui
```

Starts the desktop app (the same as running `phenoforge` with no command).

## Batch tips

- `analyse` on a folder plus `all_scans.csv` is the simplest batch job.
- In PowerShell, a loop over several folders:

  ```
  foreach ($d in Get-ChildItem D:\scans -Directory) { phenoforge analyse $d.FullName --preset iphonotype --out "D:\results\$($d.Name)" }
  ```

- Keep the exact command you used with your results, so the analysis can be repeated.
