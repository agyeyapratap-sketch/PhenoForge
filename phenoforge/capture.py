"""Input from different capture devices.

Device profiles say what each device produces and how PhenoForge turns it into a scan:

iphone_lidar  iPhone / iPad Pro with LiDAR. Scanner apps (3d Scanner App, Polycam,
              Scaniverse, Record3D, iPhonotype exports) give metric PLY / OBJ / GLB / USDZ.
              Load directly; the scale is already metric (check it with markers).
android       Android phones. Most have no LiDAR, so either (a) a scanning app that runs
              photogrammetry or Gaussian splatting (Polycam, Scaniverse, KIRI Engine,
              RealityScan) exports OBJ / GLB / PLY / splat PLY, or (b) record a slow 4K video
              or take 60-120 photos and reconstruct here with COLMAP. Not metric: use ArUco.
turntable     the PhenoForge motorised turntable (hardware/turntable): a fixed camera, the sample
              rotates. Static-background masks are made for COLMAP so the room is ignored.
dslr          DSLR / mirrorless on a tripod and turntable. RAW (CR2/CR3/NEF/ARW/DNG/RAF/ORF)
              or JPEG photos are developed, checked for blur and exposure, resized, and
              reconstructed with COLMAP. Not metric: use ArUco or a reference object.

``prepare_photos`` and ``video_to_frames`` produce a clean image folder for
:func:`phenoforge.reconstruct.run_colmap`.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

RAW_EXT = {".cr2", ".cr3", ".nef", ".arw", ".dng", ".raf", ".orf", ".rw2", ".pef", ".srw"}
JPEG_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".heic", ".heif"}
VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".3gp", ".webm"}


@dataclass
class DeviceProfile:
    key: str
    name: str
    outputs: list[str]
    metric: bool
    route: str
    tips: list[str] = field(default_factory=list)


PROFILES = {
    "iphone_lidar": DeviceProfile(
        "iphone_lidar", "iPhone / iPad with LiDAR", [".ply", ".obj", ".glb", ".usdz", ".zip"], True,
        "Load the exported scan directly (3D analysis tab > Open scan).",
        ["Scan at 30-50 cm, walk a full circle at two heights", "Export as PLY (points) or OBJ/USDZ (mesh)",
         "Keep markers in view to verify the LiDAR scale"]),
    "android": DeviceProfile(
        "android", "Android phone", [".ply", ".obj", ".glb", ".mp4", ".jpg"], False,
        "Load an app export directly, or reconstruct photos/video with COLMAP (Tools tab), then scale with ArUco.",
        ["4K video at 30 fps, move slowly (one circle in ~40 s), three rings", "Or 60-120 photos with ~70 % overlap",
         "Lock exposure/focus (AE/AF lock), turn off HDR and beauty filters", "Include the ArUco card in every view"]),
    "dslr": DeviceProfile(
        "dslr", "DSLR / mirrorless camera", [".cr2", ".cr3", ".nef", ".arw", ".dng", ".jpg"], False,
        "Prepare photos (RAW development, blur check), reconstruct with COLMAP, then scale with ArUco.",
        ["Tripod + turntable, 10 degree steps (36 shots per ring), three camera heights",
         "Manual exposure, f/8-f/11, ISO 100-400, fixed focus, no lens stabiliser on a tripod",
         "Diffuse light from two sides, plain non-green backdrop", "Shoot RAW + JPEG"]),
    "turntable": DeviceProfile(
        "turntable", "PhenoForge turntable rig", [".jpg", ".cr2", ".nef", ".arw", ".dng", "turntable.json"], False,
        "Choose the session folder written by turntable_capture.py; masks hide the static room, then COLMAP and ArUco.",
        ["36 stops per ring (10 degrees), 1.5 s settle, 2-3 camera heights",
         "Camera fixed on a tripod; lock focus, exposure and white balance",
         "ArUco markers on the platter so they turn with the sample",
         "Plain backdrop, nothing else moving in view"]),
}


def detect_device(paths) -> str:
    """Guess the device type from files (extensions and EXIF make/model)."""
    paths = list(paths)
    if any(Path(p).name == "turntable.json" or (Path(p).is_dir() and (Path(p) / "turntable.json").exists()) for p in paths):
        return "turntable"
    exts = {Path(p).suffix.lower() for p in paths}
    if exts & RAW_EXT:
        return "dslr"
    makes = {(_exif(p).get("Make") or "").strip().lower() for p in list(paths)[:5] if Path(p).suffix.lower() in JPEG_EXT}
    if "apple" in makes:
        return "iphone_lidar"
    if makes & {"canon", "nikon", "nikon corporation", "sony", "fujifilm", "olympus corporation", "om digital solutions",
                "panasonic", "pentax", "ricoh imaging company, ltd."}:
        return "dslr"
    if exts & ({".usdz"}):
        return "iphone_lidar"
    return "android"


def _exif(path) -> dict:
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS

        ex = Image.open(path).getexif()
        return {TAGS.get(k, k): v for k, v in ex.items()}
    except Exception:
        return {}


def sharpness(gray: np.ndarray) -> float:
    """Variance of the Laplacian on a 1000 px wide copy (higher = sharper)."""
    import cv2

    h, w = gray.shape[:2]
    if w > 1000:
        gray = cv2.resize(gray, (1000, int(h * 1000 / w)), interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def develop_raw(path, half_size: bool = False) -> np.ndarray:
    """Develop a camera RAW file to 8-bit sRGB with camera white balance (needs rawpy)."""
    try:
        import rawpy
    except ImportError as e:
        raise ImportError("RAW files need the 'rawpy' package (pip install rawpy), or shoot RAW+JPEG") from e
    with rawpy.imread(str(path)) as raw:
        return raw.postprocess(use_camera_wb=True, no_auto_bright=True, output_bps=8, half_size=half_size)


@dataclass
class PrepReport:
    kept: list[str]
    rejected: list[dict]
    device: str
    out_dir: str

    def summary(self) -> str:
        return f"{len(self.kept)} images kept, {len(self.rejected)} rejected ({self.device}) -> {self.out_dir}"


def prepare_photos(src, out_dir, device: str | None = None, max_side: int = 3200, blur_ratio: float = 0.35,
                   colour_correction: dict | None = None, log=print) -> PrepReport:
    """Make a clean image folder for photogrammetry from phone or camera photos.

    RAW files are developed (JPEGs of the same name are skipped), images are downsized to
    ``max_side``, and blurred frames (sharpness below ``blur_ratio`` x the median) or clipped
    frames are rejected. An optional colour correction (from the Colour tab) is applied.
    """
    import cv2

    from .colorcal import correct_image
    from .phenotype2d import read_image, write_image

    src, out = Path(src), Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files = sorted(f for f in (src.iterdir() if src.is_dir() else [src]) if f.suffix.lower() in RAW_EXT | JPEG_EXT)
    raw_stems = {f.stem for f in files if f.suffix.lower() in RAW_EXT}
    files = [f for f in files if f.suffix.lower() in RAW_EXT or f.stem not in raw_stems]
    device = device or detect_device(files)
    scores, imgs = [], []
    for f in files:
        try:
            rgb = develop_raw(f) if f.suffix.lower() in RAW_EXT else read_image(f)
        except Exception as e:
            log(f"skip {f.name}: {e}")
            continue
        h, w = rgb.shape[:2]
        if max(h, w) > max_side:
            s = max_side / max(h, w)
            rgb = cv2.resize(rgb, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
        g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        scores.append(sharpness(g))
        clip = float(np.mean(g >= 250))
        imgs.append((f, rgb, clip))
    med = float(np.median(scores)) if scores else 0.0
    kept, rejected = [], []
    for (f, rgb, clip), sc in zip(imgs, scores):
        if sc < blur_ratio * med:
            rejected.append({"file": f.name, "reason": f"blurred (sharpness {sc:.0f} vs median {med:.0f})"})
            continue
        if clip > 0.25:
            rejected.append({"file": f.name, "reason": f"overexposed ({clip:.0%} clipped)"})
            continue
        if colour_correction:
            rgb = correct_image(rgb, colour_correction["M"])
        p = out / f"{f.stem}.jpg"
        write_image(p, rgb)
        kept.append(str(p))
    rep = PrepReport(kept, rejected, device, str(out))
    (out / "capture_report.json").write_text(json.dumps(asdict(rep), indent=2))
    log(rep.summary())
    return rep


def video_to_frames(video, out_dir, target_frames: int = 120, window: int = 5, max_side: int = 3200, log=print) -> PrepReport:
    """Pick ~``target_frames`` evenly spaced, sharp frames from a walk-around video: the video is
    split into equal segments and the sharpest of ``window`` candidates near each segment
    centre is kept (motion blur is the main failure with phone video)."""
    import cv2

    from .phenotype2d import write_image

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    if n <= 0:
        raise RuntimeError(f"Cannot read video {video}")
    step = max(1, n // target_frames)
    kept = []
    for k in range(0, n, step):
        best, best_s = None, -1.0
        for j in range(k, min(k + min(window, step), n)):
            cap.set(cv2.CAP_PROP_POS_FRAMES, j)
            ok, fr = cap.read()
            if not ok:
                continue
            s = sharpness(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY))
            if s > best_s:
                best, best_s = fr, s
        if best is None:
            continue
        h, w = best.shape[:2]
        if max(h, w) > max_side:
            sc = max_side / max(h, w)
            best = cv2.resize(best, (int(w * sc), int(h * sc)), interpolation=cv2.INTER_AREA)
        p = out / f"frame_{k:06d}.jpg"
        write_image(p, cv2.cvtColor(best, cv2.COLOR_BGR2RGB))
        kept.append(str(p))
    cap.release()
    rep = PrepReport(kept, [], "android", str(out))
    log(rep.summary())
    return rep


def turntable_groups(folder, files) -> dict[str, list]:
    """Group a turntable session's images by ring (camera position).

    Uses ``turntable.json`` when present, otherwise the file-name prefix before the first
    underscore (``low_000_000.0.jpg``); several cameras (``_cam2``) form separate groups.
    """
    import re

    groups: dict[str, list] = {}
    for f in files:
        stem = Path(f).stem
        ring = stem.split("_")[0] if "_" in stem else "ring1"
        cam = re.search(r"_cam(\w+)$", stem)
        groups.setdefault(ring + (f"_cam{cam.group(1)}" if cam else ""), []).append(f)
    return groups


def turntable_masks(images, mask_dir, threshold: float = 18.0, dilate_px: int = 15, min_fraction: float = 0.002,
                    log=print) -> int:
    """COLMAP masks for one fixed camera looking at a rotating sample.

    The room is identical in every photo, so the per-pixel median of the series is the static
    background, and pixels that differ from it in any photo lie in the space swept by the
    turning sample (and the platter with its markers). That swept region, with holes filled
    (parts that look the same from every side, such as a round pot or the stem on the axis),
    is the mask for every photo of the series. Keep other moving things (people, leaves in a
    fan draught) out of view, or they widen the mask. Masks are written as ``<image name>.png``
    (white = use, black = ignore), the layout COLMAP expects for ``--mask_path``.
    Returns the number of masks written.
    """
    import cv2
    from scipy import ndimage as ndi

    from .phenotype2d import read_image

    images = [Path(p) for p in images]
    if len(images) < 3:
        return 0
    mask_dir = Path(mask_dir)
    mask_dir.mkdir(parents=True, exist_ok=True)
    small = []
    for p in images:
        im = read_image(p)
        h, w = im.shape[:2]
        s = 800 / max(h, w)
        small.append(cv2.resize(im, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA).astype(np.int16))
    stack = np.stack(small)
    med = np.median(stack, axis=0)
    swept = np.zeros(stack.shape[1:3], bool)
    open3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    for im in stack:
        diff = np.abs(im - med).max(axis=2).astype(np.float32)
        m = (cv2.GaussianBlur(diff, (5, 5), 0) > threshold).astype(np.uint8)
        swept |= cv2.morphologyEx(m, cv2.MORPH_OPEN, open3).astype(bool)
    k = max(3, int(dilate_px * 800 / max(h, w)) | 1)
    kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    m = cv2.morphologyEx(swept.astype(np.uint8), cv2.MORPH_CLOSE, kern)
    # the sample turns about a vertical axis, so each image row of the swept space is one
    # interval: fill between the outermost moving pixels (also fills the axis gap)
    rows = np.flatnonzero(m.any(axis=1))
    for r in rows:
        c = np.flatnonzero(m[r])
        m[r, c[0]:c[-1] + 1] = 1
    m = ndi.binary_fill_holes(m).astype(np.uint8)
    m = cv2.dilate(m, kern)
    if m.mean() < min_fraction:  # nothing moved: keep the whole frame
        m[:] = 1
    full = cv2.resize(m * 255, (w, h), interpolation=cv2.INTER_NEAREST)
    for p in images:
        cv2.imwrite(str(mask_dir / f"{p.name}.png"), full)
    log(f"turntable masks: {len(images)} written to {mask_dir} ({m.mean():.0%} of the frame kept)")
    return len(images)


def prepare_turntable(src, out_dir, log=print) -> tuple[PrepReport, Path]:
    """Clean photo folder plus static-background masks for a turntable session."""
    src, out = Path(src), Path(out_dir)
    rep = prepare_photos(src, out / "images", device="turntable", log=log)
    meta = src / "turntable.json"
    if meta.exists():
        (out / "images" / "turntable.json").write_text(meta.read_text())
    masks = out / "masks"
    for ring, files in turntable_groups(src, rep.kept).items():
        turntable_masks(files, masks, log=log)
    return rep, masks


def import_capture(paths, work_dir, device: str | None = None, colmap: str | None = None, quality: str = "medium",
                   log=print):
    """One call from 'files off a device' to a loaded Scan.

    * a single scan file (PLY/OBJ/GLB/USDZ/zip ...) is loaded directly
    * a video is reduced to sharp frames and reconstructed
    * a folder or list of photos (JPEG or RAW) is prepared and reconstructed
    Returns (scan, info dict).
    """
    from . import io
    from .reconstruct import run_colmap

    paths = [Path(p) for p in (paths if isinstance(paths, (list, tuple)) else [paths])]
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    if len(paths) == 1 and paths[0].is_file() and paths[0].suffix.lower() in io.SUPPORTED:
        scan = io.load(paths[0])
        dev = device or ("iphone_lidar" if scan.metric else "android")
        return scan, {"device": dev, "route": "direct", "metric": scan.metric}
    masks = None
    if len(paths) == 1 and paths[0].suffix.lower() in VIDEO_EXT:
        rep = video_to_frames(paths[0], work / "frames", log=log)
    elif len(paths) == 1 and paths[0].is_dir() and (device == "turntable" or detect_device(paths) == "turntable"):
        rep, masks = prepare_turntable(paths[0], work, log=log)
    else:
        src = paths[0] if len(paths) == 1 and paths[0].is_dir() else None
        if src is None:
            src = work / "input"
            src.mkdir(exist_ok=True)
            for p in paths:
                shutil.copy2(p, src / p.name)
        rep = prepare_photos(src, work / "images", device, log=log)
    if len(rep.kept) < 10:
        raise RuntimeError(f"Only {len(rep.kept)} usable images; at least 10 are needed and 60-120 give good models")
    model = run_colmap(rep.out_dir, work / "colmap", colmap, quality, log=log, mask_dir=masks,
                       single_camera=rep.device in ("turntable", "dslr"))
    scan = io.load(model)
    scan.metric = False
    return scan, {"device": rep.device, "route": "photogrammetry", "images": len(rep.kept),
                  "rejected": rep.rejected, "model": str(model), "metric": False}
