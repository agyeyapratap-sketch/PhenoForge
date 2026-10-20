"""Check a 3D scan against the RGB frames it was reconstructed from.

Scan packages that ship their camera poses (iPhonotype ``.ftscan``: ``3dgs/transforms.json``
plus ``3dgs/images``; any nerfstudio / instant-ngp ``transforms.json``) let us project the
scan back into each photo and compare silhouettes:

1. the scan's points are splatted into the frame (z-buffered discs with their colours), giving
   a rendered RGB image and a rendered plant mask (pixels whose front-most point is plant-coloured);
2. the photo is segmented with the same vegetation index (``clean.vegetation_indices``, Otsu);
3. IoU / Dice / precision / recall between the two masks (``validate.mask_metrics``).

High IoU on every frame says the geometry, the colours and the poses agree; one bad frame is
usually a blurred photo or a pose outlier; IoU near 0 everywhere means the coordinates no longer
match the capture.

Conventions
-----------
* ``transform_matrix`` is camera-to-world in the OpenGL / ARKit convention (camera looks down
  -Z, +Y up). ``load_frames`` converts it to OpenCV (+Z forward, +Y down) so that
  ``u = fx X/Z + cx``, ``v = fy Y/Z + cy`` with the image origin top-left.
* Intrinsics (``fl_x, fl_y, cx, cy, w, h``) are read per frame, falling back to the top level.
  Distortion coefficients are ignored (iPhonotype writes zeros).
* Images are read with EXIF orientation applied (iPhonotype states that the camera basis is for
  the EXIF-oriented image). HEIC needs ``pillow-heif`` (``pip install pillow-heif``); without it
  HEIC frames are skipped and the summary says so.
* Pass the scan **as loaded** (``io.load``), before ground alignment, scaling or cropping.
  ``scan.metadata["package_transform"]`` (set on load when an iOS Y-up frame is converted to
  Z-up) is undone automatically; later pipeline transforms are not, and give IoU ~ 0 (flagged in
  the summary ``warning``).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .clean import vegetation_indices, otsu_threshold, vegetation_mask
from .scan import Scan
from .validate import mask_metrics

GL_TO_CV = np.diag([1.0, -1.0, -1.0, 1.0])


# ------------------------------------------------------------------ frames
def find_transforms(package_dir) -> Path | None:
    d = Path(package_dir)
    if d.is_file():
        return d
    for cand in (d / "3dgs" / "transforms.json", d / "transforms.json"):
        if cand.exists():
            return cand
    hits = sorted(d.rglob("transforms.json"), key=lambda p: len(p.parts))
    return hits[0] if hits else None


def load_frames(package_dir) -> list[dict]:
    """Frames from a nerfstudio-style ``transforms.json`` (a package folder or the file itself).

    Each frame: {"name", "image_path", "K" (3x3), "c2w" (4x4, OpenCV convention), "w", "h"}.
    """
    tf = find_transforms(package_dir)
    if tf is None:
        raise FileNotFoundError(f"No transforms.json in {package_dir}")
    meta = json.loads(Path(tf).read_text(errors="ignore"))
    top = {k: meta.get(k) for k in ("fl_x", "fl_y", "cx", "cy", "w", "h")}
    if top["fl_x"] is None and meta.get("camera_angle_x") is not None and top["w"]:
        top["fl_x"] = 0.5 * float(top["w"]) / np.tan(0.5 * float(meta["camera_angle_x"]))
    frames = []
    for i, f in enumerate(meta.get("frames", [])):
        g = {k: f.get(k, top[k]) for k in top}
        if g["fl_x"] is None and f.get("camera_angle_x") is not None and g["w"]:
            g["fl_x"] = 0.5 * float(g["w"]) / np.tan(0.5 * float(f["camera_angle_x"]))
        if g["fl_x"] is None or "transform_matrix" not in f:
            continue
        fx = float(g["fl_x"])
        fy = float(g["fl_y"]) if g["fl_y"] is not None else fx
        w = int(g["w"]) if g["w"] else None
        h = int(g["h"]) if g["h"] else None
        cx = float(g["cx"]) if g["cx"] is not None else (w or 0) / 2
        cy = float(g["cy"]) if g["cy"] is not None else (h or 0) / 2
        K = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], float)
        c2w = np.asarray(f["transform_matrix"], float).reshape(4, 4) @ GL_TO_CV
        rel = str(f.get("file_path", ""))
        img = _resolve_image(Path(tf).parent, rel)
        frames.append({"name": Path(rel).name or f"frame_{i:04d}", "image_path": None if img is None else str(img),
                       "K": K, "c2w": c2w, "w": w, "h": h})
    return frames


def _resolve_image(base: Path, rel: str) -> Path | None:
    if not rel:
        return None
    p = base / rel
    if p.exists():
        return p
    stem = Path(rel).stem
    for ext in ("", ".jpg", ".jpeg", ".png", ".heic", ".JPG", ".JPEG", ".PNG", ".HEIC"):
        for d in (base / "images", base):
            q = d / (Path(rel).name if not ext else stem + ext)
            if q.exists():
                return q
    return None


def read_image(path) -> tuple[np.ndarray | None, str]:
    """RGB uint8 with EXIF orientation applied, or (None, reason)."""
    from PIL import Image, ImageOps

    if path is None or not Path(path).exists():
        return None, "image missing"
    if Path(path).suffix.lower() in (".heic", ".heif"):
        try:
            import pillow_heif

            pillow_heif.register_heif_opener()
        except ImportError:
            return None, "HEIC needs pillow-heif (pip install pillow-heif)"
    try:
        im = Image.open(path)
        im = ImageOps.exif_transpose(im)
        return np.asarray(im.convert("RGB")), ""
    except Exception as e:
        return None, f"undecodable image ({type(e).__name__}: {e})"


# -------------------------------------------------------------- projection
def capture_points(scan: Scan) -> np.ndarray:
    """Scan points in package / capture coordinates (undo the transform applied on load)."""
    T = scan.metadata.get("package_transform")
    if T is None:
        return scan.points
    T = np.asarray(T, float)
    Ti = np.linalg.inv(T)
    return scan.points @ Ti[:3, :3].T + Ti[:3, 3]


def project_points(points_capture: np.ndarray, frame: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Pixel coordinates (N, 2), depth along the optical axis (N,), and in-image & in-front mask."""
    P = np.asarray(points_capture, float)
    c2w = np.asarray(frame["c2w"], float)
    R, t = c2w[:3, :3], c2w[:3, 3]
    Xc = (P - t) @ R  # = R^T (P - t)
    z = Xc[:, 2]
    zs = np.where(np.abs(z) > 1e-12, z, 1e-12)
    K = np.asarray(frame["K"], float)
    u = K[0, 0] * Xc[:, 0] / zs + K[0, 1] * Xc[:, 1] / zs + K[0, 2]
    v = K[1, 1] * Xc[:, 1] / zs + K[1, 2]
    uv = np.column_stack([u, v])
    vis = z > 1e-6
    if frame.get("w") and frame.get("h"):
        vis &= (u >= 0) & (u < frame["w"]) & (v >= 0) & (v < frame["h"])
    return uv, z, vis


def render_points(uv: np.ndarray, depth: np.ndarray, colors: np.ndarray, size: tuple[int, int],
                  radius: int = 2, flags: np.ndarray | None = None):
    """Z-buffered disc splats. Returns (rgb uint8 HxWx3, covered mask, flag-of-front-point mask)."""
    W, H = size
    ok = (depth > 1e-6) & np.isfinite(uv).all(1)
    uv, depth, colors = uv[ok], depth[ok], colors[ok]
    flags = np.ones(ok.sum(), bool) if flags is None else np.asarray(flags, bool)[ok]
    ui, vi = np.round(uv[:, 0]).astype(np.int64), np.round(uv[:, 1]).astype(np.int64)
    r = max(int(radius), 0)
    offs = [(dx, dy) for dx in range(-r, r + 1) for dy in range(-r, r + 1) if dx * dx + dy * dy <= r * r + r]
    pix, dep, src = [], [], []
    base = np.arange(len(ui))
    for dx, dy in offs:
        x, y = ui + dx, vi + dy
        m = (x >= 0) & (x < W) & (y >= 0) & (y < H)
        pix.append(y[m] * W + x[m])
        dep.append(depth[m])
        src.append(base[m])
    rgb = np.zeros((H, W, 3), np.uint8)
    cov = np.zeros(H * W, bool)
    flg = np.zeros(H * W, bool)
    if not pix:
        return rgb, cov.reshape(H, W), flg.reshape(H, W)
    pix, dep, src = np.concatenate(pix), np.concatenate(dep), np.concatenate(src)
    if len(pix) == 0:
        return rgb, cov.reshape(H, W), flg.reshape(H, W)
    order = np.lexsort((dep, pix))  # by pixel, then nearest first
    pix_s = pix[order]
    first = np.r_[True, pix_s[1:] != pix_s[:-1]]
    p, s = pix_s[first], src[order][first]
    flat = rgb.reshape(-1, 3)
    flat[p] = np.round(np.clip(colors[s], 0, 1) * 255).astype(np.uint8)
    cov[p] = True
    flg[p] = flags[s]
    return rgb, cov.reshape(H, W), flg.reshape(H, W)


# ------------------------------------------------------------- comparison
_PHOTO_MIN_THRESHOLD = {"exg": 0.03, "gli": 0.02, "vari": 0.02}


def photo_vegetation_mask(rgb: np.ndarray, method: str = "exg", roi: np.ndarray | None = None) -> np.ndarray:
    """Plant pixels of a photo: vegetation index > Otsu threshold (computed inside ``roi``),
    floored so a photo with little vegetation is not split inside its background."""
    from scipy import ndimage as ndi

    c = rgb.reshape(-1, 3).astype(float) / 255.0
    idx = vegetation_indices(c)
    sel = np.ones(len(c), bool) if roi is None else np.asarray(roi, bool).reshape(-1)
    if method == "hue":
        h = idx["hue"]
        m = (h >= 35) & (h <= 170) & (c.max(1) - c.min(1) > 0.08)
    else:
        v = idx[method]
        thr = otsu_threshold(v[sel]) if sel.any() else otsu_threshold(v)
        m = v > max(thr, _PHOTO_MIN_THRESHOLD.get(method, -np.inf))
    m = (m & sel).reshape(rgb.shape[:2])
    return ndi.binary_opening(m, iterations=1)


def compare_frame(scan: Scan, frame: dict, vegetation: str = "exg", point_radius_px: int = 2,
                  max_side: int = 1024, photo: np.ndarray | None = None,
                  roi_margin: float | None = 0.05) -> dict:
    """Render the scan into one frame and compare its plant silhouette with the photo's.

    Works at a reduced resolution (long side ``max_side``). The photo mask is limited to the
    bounding box of the projected scan grown by ``roi_margin`` x the image size (None = whole
    photo), so plant-coloured background that was never scanned does not count against it.
    Returns metrics plus images:
    "rendered" (RGB), "photo" (RGB), "overlay" (photo | render | agreement map, uint8).
    Agreement colours: green = both, magenta = scan only, yellow = photo only.
    """
    from PIL import Image
    from scipy import ndimage as ndi

    out = {"name": frame.get("name", "")}
    reason = ""
    if photo is None:
        photo, reason = read_image(frame.get("image_path"))
    if photo is None:
        out["error"] = reason
        return out
    w, h = frame.get("w") or photo.shape[1], frame.get("h") or photo.shape[0]
    if (photo.shape[1], photo.shape[0]) != (w, h):
        if abs(photo.shape[1] / photo.shape[0] - w / h) > 0.02:
            out["error"] = f"image size {photo.shape[1]}x{photo.shape[0]} does not match intrinsics {w}x{h}"
            return out
    s = min(1.0, max_side / max(w, h))
    W, H = max(1, int(round(w * s))), max(1, int(round(h * s)))
    photo_s = np.asarray(Image.fromarray(photo).resize((W, H), Image.BILINEAR))
    fr = dict(frame)
    K = np.asarray(frame["K"], float).copy()
    K[:2] *= np.array([[W / w], [H / h]])
    fr.update(K=K, w=W, h=H)

    pts = capture_points(scan)
    uv, z, vis = project_points(pts, fr)
    cols = scan.colors if scan.colors is not None else np.full((len(pts), 3), 0.6)
    veg = vegetation_mask(scan, vegetation) if scan.colors is not None else np.ones(len(pts), bool)
    rgb, cov, flg = render_points(uv[vis], z[vis], cols[vis], (W, H), point_radius_px, veg[vis])
    rmask = ndi.binary_closing(flg, iterations=max(1, point_radius_px)) & cov
    roi = None
    if roi_margin is not None and cov.any():
        # compare only near the scanned object: background plants / green-yellow objects that
        # were never reconstructed are not scan errors
        ys, xs = np.nonzero(cov)
        mg = int(round(roi_margin * max(W, H)))
        roi = np.zeros_like(cov)
        roi[max(ys.min() - mg, 0):ys.max() + mg + 1, max(xs.min() - mg, 0):xs.max() + mg + 1] = True
        out["roi_px"] = int(roi.sum())
    pmask = photo_vegetation_mask(photo_s, vegetation, roi)
    if roi is not None:
        # drop photo blobs that never touch the projected scan (unscanned background objects)
        comp, n = ndi.label(pmask)
        if n:
            touch = np.unique(comp[ndi.binary_dilation(cov, iterations=3) & (comp > 0)])
            pmask = np.isin(comp, touch)
    met = mask_metrics(rmask, pmask)
    out.update({k: met[k] for k in ("iou", "dice", "precision", "recall")})
    out["points_in_view"] = int(vis.sum())
    out["rendered_px"], out["photo_px"] = met["area_pred_px"], met["area_ref_px"]
    out["rendered"], out["photo"] = rgb, photo_s
    out["overlay"] = _overlay(photo_s, rgb, cov, rmask, pmask)
    return out


def _overlay(photo, rgb, cov, rmask, pmask) -> np.ndarray:
    grey = photo.mean(2, keepdims=True).repeat(3, 2) * 0.5
    agree = grey.copy()
    for m, c in ((rmask & pmask, (40, 220, 40)), (rmask & ~pmask, (230, 40, 230)), (~rmask & pmask, (240, 220, 30))):
        agree[m] = 0.35 * agree[m] + 0.65 * np.array(c, float)
    render = np.where(cov[..., None], rgb, (photo * 0.25).astype(np.uint8))
    gap = np.full((photo.shape[0], 6, 3), 255, np.uint8)
    return np.hstack([photo, gap, render, gap, agree.astype(np.uint8)])


def compare_package(scan: Scan, max_frames: int = 12, log=print, vegetation: str = "exg",
                    point_radius_px: int = 2, keep_images: bool = False) -> tuple[list[dict], dict]:
    """Compare the as-loaded scan with up to ``max_frames`` evenly spaced package frames.

    Returns (rows without images, summary). ``keep_images`` keeps the overlay per row.
    """
    pkg = scan.metadata.get("package")
    if not pkg:
        raise ValueError("Scan has no package folder (load a package folder / .zip with io.load)")
    frames = load_frames(pkg)
    if not frames:
        raise ValueError("transforms.json has no usable frames")
    pick = np.unique(np.linspace(0, len(frames) - 1, min(max_frames, len(frames))).round().astype(int))
    rows, skipped = [], {}
    for i in pick:
        r = compare_frame(scan, frames[i], vegetation, point_radius_px)
        if "error" in r:
            skipped[r["error"]] = skipped.get(r["error"], 0) + 1
            log(f"framecheck: {r['name']} skipped ({r['error']})")
            rows.append({"name": r["name"], "error": r["error"]})
            continue
        if not keep_images:
            for k in ("rendered", "photo", "overlay"):
                r.pop(k, None)
        rows.append(r)
        log(f"framecheck: {r['name']} IoU {r['iou']:.3f}")
    ok = [r for r in rows if "iou" in r]
    summary: dict = {"frames_total": len(frames), "frames_compared": len(ok),
                     "frames_skipped": len(rows) - len(ok), "skip_reasons": skipped}
    if ok:
        ious = np.array([r["iou"] for r in ok])
        summary.update(mean_iou=float(ious.mean()), median_iou=float(np.median(ious)), min_iou=float(ious.min()),
                       mean_dice=float(np.mean([r["dice"] for r in ok])),
                       worst_frames=[r["name"] for r in sorted(ok, key=lambda r: r["iou"])[:3]])
        if ious.max() < 0.05:
            summary["warning"] = ("scan does not line up with the capture frames (IoU ~ 0 on every frame): pass the "
                                  "scan as loaded from the package, before ground alignment / scaling / cropping")
    elif skipped:
        summary["warning"] = "no frame could be read: " + "; ".join(skipped)
    moved = [h for h in scan.history if h.startswith(("aligned ground", "scaled", "crop"))]
    if "ground_transform" in scan.metadata or moved:
        summary.setdefault("warning", "scan was transformed after loading; compare the as-loaded scan")
    log(f"framecheck: {summary.get('frames_compared')} frames, mean IoU {summary.get('mean_iou', float('nan')):.3f}"
        + (f"  WARNING: {summary['warning']}" if "warning" in summary else ""))
    return rows, summary
