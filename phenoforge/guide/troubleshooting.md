# Troubleshooting

Start by reading the **Log** panel at the bottom of the window. Most problems are explained
there. Error messages also appear in a pop-up; the full technical details are in the Log.

## The plant lies on its side

The scan uses a "Y-up" coordinate system (common for glTF/GLB files and phone app exports),
but PhenoForge expects z to point up.

- Tick **Input is Y-up (glTF / phone app export)** in **1 Clean and frame** and click
  **Run analysis**.
- Do **not** tick it for iPhonotype packages or USDZ files: they are turned upright
  automatically, and ticking it lays them on their side. If an iPhonotype package lies on its
  side, untick Y-up.
- If you opened the splat `.ply` from inside an iPhonotype package on its own, tick Y-up, or
  better, open the whole package instead.
- If the plant is upright but tilted, keep **Fit ground plane, set z = 0** ticked so the table
  or soil is levelled.

## "Not metric" or values in scan units

The Log says "Note: the scan is not metric, so values are in scan units", and the results say
`scan units (not scaled)`. The numbers are then not in metres.

- Photos, videos and photogrammetry are never metric. Use **ArUco markers** or **Two picked
  points** in **2 Metric scale**.
- PLY, OBJ and GLB files carry no units. If you know the file is in metres (for example a
  LiDAR app export), choose **Already metric (LiDAR)** as the scale source, or use the
  "iPhone LiDAR app (PLY / OBJ / USDZ)" preset. On the command line, add `--metric`.
- If the file is in millimetres, use **Manual factor** 0.001.
- iPhonotype packages are metric only when the app marked the scale as verified. Otherwise use
  ArUco (see [iPhonotype](iphonotype.md)).
- The **vs iPhonotype** table is empty (NaN) in the PhenoForge column when the scan is not
  metric.

## ArUco markers not found

The message is "No ArUco markers detected. Check the dictionary, that markers are visible and
flat in the chosen view, and that the scan is coloured."

Check:

1. **Dictionary**: it must match the printed markers (PhenoForge sheets use DICT_4X4_50 by
   default).
2. **Marker IDs**: leave empty unless you need it. A wrong ID list hides the markers.
3. **Colour**: the scan must have colours. Scans without colour cannot be scaled with markers.
4. **Flat and seen from above**: PhenoForge looks for markers in a top view after levelling the
   ground. Markers standing upright, or on a steep slope, are not found. Lay them flat on the
   bench, tray or soil.
5. **Resolution**: each marker must be covered by enough points to see its black and white
   squares. Use bigger markers (50 mm or more) for room-scale or phone LiDAR scans, and scan
   closer.
6. Click **Markers image** to see the top view and what was found.
7. Glare or a glossy card can wash out the pattern. Print on matte paper.

If some markers are rejected (listed in the Log), they differ by more than 4 % from the others,
usually because they are tilted, bent or partly hidden.

## The vegetation filter removes everything (or nothing)

After **Run analysis**, the Log line "vegetation filter -> N points" shows how many points were
kept. If almost nothing is left:

- The plant is not green enough for **exg** (yellow, red, senesced or purple plants, wheat heads).
  Try **hue** (keeps green to straw-yellow) or **none**.
- The colours are dark or tinted. Try **gli** or **vari**, or correct the colours on the
  [Colour](colour.md) tab.
- Type a lower number in **Index threshold** (for exg, for example 0.02).
- Fruit, tubers and roots: set **Vegetation index** to **none**.

If too much background is kept (soil, pot, bench), type a higher **Index threshold** or tick
**Keep largest cluster(s) only**.

## AI leaf separation (SAM) is not installed

The message is "AI leaf separation is an optional add-on: install with: pip install
ultralytics ...". Choose **components** to continue without it, or install the add-on (see
[Optional add-ons](addons.md)). The add-ons cannot be added to the Windows zip version.

The first run downloads the model (about 160 MB). If the PC is offline, run it once on a
connected network.

The wheat-head detector window shows "Optional add-on not installed." for the same reason.

## HEIC photos (iPhone)

iPhones save photos as HEIC by default. PhenoForge reads HEIC and HEIF photos everywhere it
reads photos, and turns them the right way up from their EXIF orientation. If a HEIC file
still gives "Cannot read image", the `pillow-heif` package is missing from your installation:
reinstall the requirements (see [Getting started](getting-started.md)).

## The phone cannot open the Wi-Fi page

- Make sure the phone and the PC are on the **same network**.
- Allow PhenoForge (or Python) through the **Windows firewall** for **private networks**. When
  Windows asks the first time, tick **Private networks** and click **Allow access**. To fix it
  later: **Windows Security > Firewall & network protection > Allow an app through firewall**.
  On managed PCs, ask IT.
- If Windows calls your network "Public", the firewall may block it even when allowed for
  private networks. Ask IT before changing the network type.
- Try another **Port** (for example 8800), then **Start** again.
- Disconnect a VPN: the link may use the VPN address.
- Scan the QR code again after each **Start**; the access code changes.

See [Wi-Fi transfer](wifi.md).

## pip fails on a network drive (WinError 59)

`pip install` into a Python environment on a network share (such as `Y:`) often fails with
`OSError: [WinError 59] An unexpected network error occurred`.

Create the environment on a local disk instead, for example:

```
py -3.12 -m venv $env:LOCALAPPDATA\venvs\phenoforge
& $env:LOCALAPPDATA\venvs\phenoforge\Scripts\python.exe -m pip install -r requirements.txt
```

The PhenoForge source folder itself can stay on the network drive. See
[Getting started](getting-started.md).

## COLMAP not found

The message is "COLMAP not found. Install it from https://colmap.github.io and set its path in
the COLMAP box on the Tools tab (or pass --colmap on the command line)."

1. Download COLMAP for Windows (github.com/colmap/colmap/releases) and unzip it.
2. On the Tools tab, in **COLMAP**, enter the full path to `COLMAP.bat`, for example
   `C:\COLMAP\COLMAP.bat`.
3. Try again. PhenoForge remembers the path.

Alternatives: put the COLMAP folder on the Windows PATH, or set the environment variable
`COLMAP_PATH` to the full path of `COLMAP.bat`. On the command line, use `--colmap`.

If COLMAP runs but the model is poor or sparse: COLMAP needs an NVIDIA GPU (CUDA) for dense
reconstruction; without it only a sparse cloud is made.

## Slow on large scans

- Set **Voxel downsample** in **1 Clean and frame**. The value is in the scan's own units
  (metres for metric scans): 0.002 averages the points in 2 mm cubes, which often cuts the
  number of points many times with little effect on height or volume. Leaf area and fine
  details become coarser with larger values.
- Use **Leaf candidates** **none** or **components** instead of **region** or **sam**.
- Untick **Count wheat heads** and **Count tillers** if you do not need them.
- Open scans from a local disk, not a network drive.
- The 3D view shows at most 1.5 million points (300,000 in Splat mode), so the view stays
  responsive even when the analysis is slow.

## Temporary space for packages

When you open a `.ftscan` or `.zip` package, PhenoForge unpacks it into
`%TEMP%\phenoforge_packages` (for example `C:\Users\<you>\AppData\Local\Temp\phenoforge_packages`).
Opening the same file again reuses the unpacked copy, so it is fast.

Packages can be about 1 GB each when unpacked. PhenoForge keeps the **4** most recently used
packages and deletes older ones automatically. If disk space is short, you can delete the
`phenoforge_packages` folder while PhenoForge is closed; it is recreated when needed.

## Nothing happens when I double-click in the library

Only scans (the third level of the tree) open with a double-click. If a scan's file was moved
or deleted, it cannot be opened. See [The workspace library](library.md).

## Results were not saved to the library

Results are saved to the library only when the scan was opened from the library: by
double-clicking it in the library tree, or received over Wi-Fi with **Add each scan to the
library session** ticked. Scans opened with Open scan, drag and drop, the Start page or Recent
scans are not linked, even if a copy is in the library. Double-click the scan in the tree, then run the
analysis again.

## The app does not start (Windows zip)

Run `phenoforge-cli.exe gui` from a PowerShell window in the PhenoForge folder to see the error
message. Make sure the whole zip was unzipped, not run from inside the zip.

## Still stuck?

Save the Log text (select it, Ctrl+C) and the scan's `<scan>_traits.json`, and send them to
whoever supports PhenoForge in your facility.
