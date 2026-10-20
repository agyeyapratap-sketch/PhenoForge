# Tools

The **Tools** tab collects jobs that prepare data or check it: importing from capture devices,
printing ArUco markers, 3D reconstruction from photos with COLMAP, and a group of
**More tools**. The **Tools** menu at the top of the window has some of the same jobs.

## Import from a capture device

Use this to bring in a capture from an iPhone with LiDAR, an Android phone, a DSLR or
mirrorless camera, or the PhenoForge turntable rig. Photos and videos are turned into a 3D scan
with COLMAP (see below); scan files from apps are loaded directly.

1. **Device**: choose the device, or **Auto-detect** (PhenoForge guesses from the file types and
   the photos' EXIF data). Choosing a device shows tips for it under the input box.
2. **Input**: click **File/video...** for a scan file or a video, or **Photo folder...** for a
   folder of photos (JPEG or RAW). For the turntable rig, choose the session folder written by
   the capture script.
3. Click **Import (reconstructs photos/video with COLMAP when needed)**.

What happens:

- **Scan files** (PLY, OBJ, GLB, USDZ, ZIP, LAS): loaded directly.
- **Videos**: sharp frames are picked (about 120, the sharpest of each short window), then
  reconstructed with COLMAP.
- **Photos**: RAW files are developed; photos are resized if very large; blurred photos and
  over-exposed photos are rejected; then reconstructed with COLMAP.
- **Turntable sessions**: masks are made that hide the parts of the picture that do not move
  (the room), so COLMAP only reconstructs the turning sample.

Working files go into a new folder next to the input, named `<input>_phenoforge`. When the
import finishes, the scan opens on the [3D analysis](3d-analysis.md) tab. The Log lists any
rejected photos with the reason. Photo and video reconstructions are not metric: PhenoForge
sets the scale source to **ArUco markers**; set the marker size and click **Run analysis**.
The same happens for scan files without a known scale (such as PLY files); if you know the
file is in metres, choose **Already metric (LiDAR)** instead (see
[The 3D analysis tab](3d-analysis.md)).

If fewer than 10 photos or frames are usable, the import stops with the message "Only N usable
images; at least 10 are needed and 60-120 give good models". Aim for 60–120 sharp,
well-exposed photos.

Photos can be JPEG, PNG, TIFF, HEIC/HEIF or RAW.

## Printable ArUco marker sheet

ArUco markers are black-and-white squares that PhenoForge recognises in scans and photos. A
marker of known size gives the real-world scale.

1. **Dictionary**: the marker family. Keep **DICT_4X4_50** unless you have a reason to change it.
2. **First ID** and **Count**: which marker numbers to print (default 0 to 8, nine markers).
3. **Side**: the printed marker size in mm (default 50).
4. Click **Save sheet (PNG, 300 dpi)...** and choose a file name.
5. Print the PNG at **100 %** (no "fit to page").
6. Measure one printed marker with a ruler (the black square, without the white border). Use
   this measured value as the marker side in PhenoForge.

Glue the markers to stiff, flat, matte card. Use different IDs for markers in the same scene.

## Photogrammetry from photos or video frames (COLMAP)

COLMAP is free 3D reconstruction software (photogrammetry). It is not included with PhenoForge;
install it separately.

1. Download COLMAP for Windows from the COLMAP releases page on GitHub
   (github.com/colmap/colmap/releases). Choose the CUDA version if you have an NVIDIA graphics
   card. Unzip it.
2. In **COLMAP**, enter the path to `COLMAP.bat` (or `colmap.exe`), or leave it empty if COLMAP
   is on the PATH. PhenoForge remembers it.
3. **Images**: click **Image folder...** and choose a folder of photos.
4. **Quality**: low, medium, high or extreme. Higher quality is slower. Default medium.
5. Click **Reconstruct and open**.

The work folder is `<image folder>_colmap` next to the image folder. When COLMAP finishes, the
model opens on the 3D analysis tab. Without an NVIDIA GPU, COLMAP can only make a sparse cloud,
which is loaded instead and gives poorer traits.

Photogrammetry results are not metric. Include ArUco markers in the photos and use ArUco
scaling.

This box uses your photos as they are. For blur checks, RAW development and turntable masks,
use **Import from a capture device** above, which also runs COLMAP.

## More tools

| Button | What it does | Help |
|---|---|---|
| **Receive from phone (Wi-Fi)…** | Send scans from the phone to this PC without cables. | [Wi-Fi](wifi.md) |
| **Analyse a whole folder…** | One preset for every scan in a folder; one CSV at the end. | [Batch](batch.md) |
| **Check scan against its photos…** | iPhonotype: compare the 3D model with each photo (IoU). | [Validation](validation.md) |
| **Wheat-head detector (photos)…** | Train a detector on your labelled photos, then count heads. | [Wheat](wheat.md) |
| **Narrated root video…** | Time-lapse of root photos with traits and narration. | [Roots 2D](roots-2d.md) |
| **Scale evidence from a video…** | Was the ArUco card visible and consistent throughout the capture? | See below |

## Scale evidence from a capture video

This makes a record that the scale reference (an ArUco card) was visible and sharp throughout a
capture video. Keep it with the data as evidence that the scale is sound.

1. Click **Scale evidence from a video…** (or **Tools > Scale evidence from a capture video...**).
2. **Video**: choose the capture video (MP4, MOV, AVI, MKV or M4V).
3. **Marker side**: the printed marker size in mm, measured with a ruler.
4. **Dictionary**: the marker family (default DICT_4X4_50).
5. **Results folder**: where the results go (default `scale_evidence` in the `PhenoForge` folder
   in your home folder).
6. Click **Check video**. When it finishes, the results folder opens.

Every 5th frame is checked. For each one PhenoForge records the time, the sharpness, the
markers found, the marker size in pixels, mm per pixel and the skew (how far the marker is from
square: about 0 for a flat marker seen straight on).

A frame is counted as **usable** when a marker is found, the frame is reasonably sharp (at least
30 % of the median sharpness of the marker frames), the skew is under 10 %, and its mm per
pixel is within 5 % of the median of the whole video.

Files written (`<video>` is the video name):

| File | Contents |
|---|---|
| `<video>_scale_evidence.csv` | One row per checked frame: `frame`, `time_s`, `sharpness`, `n_markers`, `marker_ids`, `marker_side_px`, `mm_per_px`, `mm_per_px_each`, `skew_pct`, `usable`. |
| `<video>_scale_evidence_plot.png` | mm per pixel (with a ±2 % band around the median) and sharpness against time. |
| `<video>_scale_evidence_sharpest.png` | The six sharpest frames with a marker, with the markers outlined. |

The Log gives the summary, for example
`Scale evidence: markers in 140/180 sampled frames, median 0.21 mm/px, CV 3.10%, usable 72%`.

How to read it:

- **Fraction of frames with markers**: high is good. Gaps show when the card was out of view.
- **Skew**: large values mean the card was seen at a steep angle or was not flat.
- **mm per pixel and its CV** (coefficient of variation, the spread as a percentage): only
  stable when the camera stays at the same distance from the card, as on a turntable or
  tripod. In a hand-held orbit the camera distance changes, so mm per pixel changes too and
  fewer frames count as usable. That is expected and does not mean the scale is wrong.

This check is about the video. It does not change the scale of any scan.

From the command line: `phenoforge scale-evidence capture.mp4 --mm 50 --out evidence`
(add `--every 2` to check more frames). See [Command line](cli.md).

## Other items in the Tools menu

- **Check scan against its photos (iPhonotype)...**: see [Validation](validation.md).
- **Package information...**: shows the Package tab for an open iPhonotype package. See
  [iPhonotype](iphonotype.md).
