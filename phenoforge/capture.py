"""Input from different capture devices.

Device profiles say what each device produces and how PhenoForge turns it into a scan:

iphone_lidar  iPhone / iPad Pro with LiDAR. Scanner apps (3d Scanner App, Polycam,
              Scaniverse, Record3D, iPhonotype exports) give metric PLY / OBJ / GLB / USDZ.
              Load directly; the scale is already metric (check it with markers).
android       Android phones. Most have no LiDAR, so either (a) a scanning app that runs
              photogrammetry or Gaussian splatting (Polycam, Scaniverse, KIRI Engine,
              RealityScan) exports OBJ / GLB / PLY / splat PLY, or (b) record a slow 4K video
              or take 60-120 photos and reconstruct here with COLMAP. Not metric: use ArUco.
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
}


def detect_device(paths) -> str:
    """Guess the device type from files (extensions and EXIF make/model)."""
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
    if len(paths) == 1 and paths[0].suffix.lower() in VIDEO_EXT:
        rep = video_to_frames(paths[0], work / "frames", log=log)
    else:
        src = paths[0] if len(paths) == 1 and paths[0].is_dir() else None
        if src is None:
            src = work / "input"
            src.mkdir(exist_ok=True)
            for p in paths:
                shutil.copy2(p, src / p.name)
        rep = prepare_photos(src, work / "images", device, log=log)
    if len(rep.kept) < 10:
        raise RuntimeError(f"Only {len(rep.kept)} usable images; photogrammetry needs 25 or more")
    model = run_colmap(rep.out_dir, work / "colmap", colmap, quality, log=log)
    scan = io.load(model)
    scan.metric = False
    return scan, {"device": rep.device, "route": "photogrammetry", "images": len(rep.kept),
                  "rejected": rep.rejected, "model": str(model), "metric": False}
