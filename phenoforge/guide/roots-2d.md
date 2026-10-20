# Root photos and video (2D)

The **Roots** tab measures roots in photos of Petri dishes, rhizotrons, root boxes or washed
roots on a scanner, and in videos. It finds the roots, reduces them to centre lines (a
skeleton) and measures total length, primary root length, laterals, tips and branch points.

It can also make a **narrated time-lapse video** from a series of root photos taken over days.

## Take the photos

- Roots must contrast with the background: white roots on a dark background, or dark roots on
  white paper or a light box.
- Light the background evenly. Shadows and reflections can be taken for roots.
- For mm instead of pixels, put a printed ArUco marker (DICT_4X4_50) in the photo at the same
  level as the roots, or know the scale of your scanner (mm per pixel).
- Use JPEG, PNG, TIFF or HEIC. Videos can be MP4, MOV or AVI.

## Measure one photo or video

1. Open the **Roots** tab.
2. **Input**: click **Image or video...** and choose a photo or video.
3. **Roots are**: **auto** (PhenoForge guesses), **dark** (dark roots on a light background) or
   **light** (light roots on a dark background).
4. Scale: either
   - **Scale (0 = px / ArUco)**: the known scale in mm per pixel, for example from a flatbed
     scanner (25.4 / dpi), or
   - **ArUco marker side**: the printed marker side in mm, with **Scale** left at 0.
   Leave both at 0 for results in pixels.
5. For a video:
   - **Video: every Nth frame**: keep one frame in N (default 10).
   - **Video: stitch frames into a panorama**: tick this when the camera slides over a large
     dish or root box, to join the frames into one picture. Otherwise the middle frame of the
     video is analysed.
6. **Ignore outside a centred circular dish**: tick this for round Petri dishes, to ignore the
   dish rim and anything outside it.
7. Click **Analyse roots**.

The overlay on the right shows the roots tinted blue, the skeleton in yellow, the primary root
in red, tips as green dots and branch points as magenta circles. The table lists the traits.

Video frames are saved in `PhenoForge\root_frames\<video name>` in your home folder.

### Traits

Lengths are in pixels (`_px`) and, with a scale, also in mm (`_mm`, `_mm2`).

| Trait | Meaning |
|---|---|
| `total_length_px` / `_mm` | Length of all roots (the whole skeleton). |
| `primary_length_px` / `_mm` | Length of the primary root: from the top-most tip to the tip farthest along the roots. |
| `lateral_length_px` / `_mm` | Total length minus primary length. |
| `n_tips` | Root tips (skeleton end points). |
| `n_laterals` | Tips minus the two ends of the primary root. |
| `n_branch_points` | Points where roots branch. |
| `mask_area_px` / `_mm2` | Area covered by roots. |
| `depth_px` / `_mm` | Vertical extent of the roots in the image. |
| `width_px` / `_mm` | Horizontal extent. |
| `hull_area_px` / `_mm2` | Area of the convex hull around all roots. |
| `mm_per_px` | The scale used. |

The primary root is assumed to start at the top of the image (the end nearest the seed or
hypocotyl). Roots that cross each other create extra branch points and can shorten or lengthen
the primary path. Root hairs and noise create short side branches that count as tips.

## Make a narrated time-lapse video

This turns a folder of root photos taken over time into an MP4 video. Each photo is shown with
the root overlay and a caption bar with total and primary length, laterals, tips and the change
since the previous photo. Subtitles are always written. On Windows, with the optional
narration add-on, a computer voice reads one sentence per photo, for example
"Day 3: total root length 412 millimetres, up 18 percent; 14 tips."

### Prepare the photos

- Put all photos of one root system in one folder.
- Name them so they sort in time order, for example `day01.jpg`, `day02.jpg`, … or
  `2026-10-01.jpg`, `2026-10-02.jpg`. The file name (with `_` and `-` read as spaces) is
  spoken at the start of each sentence, so `day_3` is read as "Day 3".
- Keep the camera and the scale the same in every photo.

### Steps

1. On the Roots tab click **Make a narrated time-lapse video…** (or **Tools > Narrated root
   video...**).
2. **Photos**: choose the folder.
3. **Save video as**: the MP4 file name (default `roots_video.mp4` in the `PhenoForge` folder in
   your home folder).
4. **Title**: optional text shown in the caption, for example `Rhizotron 3, genotype W123`.
5. **Scale (0 = ArUco or pixels)**: mm per pixel if known.
6. **ArUco marker side**: the marker side in mm, if there is a marker in each photo. Used when
   Scale is 0.
7. **Time per photo**: how long each photo is shown (default 3 s). With narration, a photo
   stays longer if its sentence takes longer to say.
8. **Spoken narration (Windows voice; subtitles are always written)**: tick for a spoken
   commentary.
9. Click **Make video**. The window closes and the work continues in the background.

When it finishes, the video opens in your default video player. Roots are detected
automatically (**auto**) in this window.

### Output files

Next to the video:

| File | Contents |
|---|---|
| `roots_video.mp4` | The video. |
| `roots_video.srt` | Subtitles: one sentence per photo, timed to the video. Most video players show them automatically when the file names match. |
| `roots_video_traits.csv` | One row per photo: frame number, image, name, all root traits, `change_total_pct` (change in total length since the previous photo), the spoken sentence, and the start time and duration in the video. |

### If there is no voice

Narration needs two optional packages, `pyttsx3` (uses the voices built into Windows, offline)
and `imageio-ffmpeg` (to add sound to the video). See [Optional add-ons](addons.md). They are
not in the Windows zip version.

If they are missing, or speech fails, PhenoForge still makes the video with subtitles but
without sound. The Log then says `video: ... (no voice: silent video: ...)` with the reason.
Narration never stops the video from being made.

### From the command line

```
phenoforge rootvideo D:\rhizotron3 --aruco-mm 20 --title "Rhizotron 3" --out rhizotron3.mp4
```

Add `--silent` for subtitles only, `--roots dark` or `--roots light` to set the root colour, and
`--seconds 2` to change the time per photo. See [Command line](cli.md).

## From the command line (measurements)

```
phenoforge roots D:\dishes --aruco-mm 20 --roots dark --out root_results
phenoforge roots growth.mp4 --every 15 --stitch --out root_results
```

This writes `roots.csv` (one row per image) and an overlay PNG per image. Unlike the tab, a
video without `--stitch` analyses every kept frame. See [Command line](cli.md).
