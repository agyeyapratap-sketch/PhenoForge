"""Above-ground 2D phenotyping of photos (top-view trays, side views, field plots).

For each image: vegetation mask (ExG + Otsu, or HSV range), canopy area in pixels and
in mm^2 when ArUco markers give the scale, plant / blob count, per-blob area and convex
hull, greenness, and an overlay PNG. ``batch`` writes one CSV row per image and one per blob.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

import numpy as np

from .clean import otsu_threshold
from .scale import image_mm_per_px

IMG_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".heic", ".heif"}


def read_image(path) -> np.ndarray:
    """RGB uint8; handles unicode paths on Windows."""
    import cv2

    data = np.fromfile(str(path), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:  # e.g. iPhone HEIC photos, which OpenCV cannot decode
        try:
            from PIL import Image, ImageOps

            try:
                import pillow_heif

                pillow_heif.register_heif_opener()
            except ImportError:
                pass
            return np.asarray(ImageOps.exif_transpose(Image.open(path)).convert("RGB"))
        except Exception as e:
            raise ValueError(f"Cannot read image {path}") from e
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def write_image(path, rgb: np.ndarray) -> None:
    import cv2

    ext = Path(path).suffix or ".png"
    ok, buf = cv2.imencode(ext, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR) if rgb.ndim == 3 else rgb)
    if ok:
        buf.tofile(str(path))


def vegetation_mask_image(rgb: np.ndarray, method: str = "exg", threshold: float | None = None,
                          hsv_range=((30, 40, 30), (90, 255, 255)), open_px: int = 2) -> np.ndarray:
    import cv2

    if method == "hsv":
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        m = cv2.inRange(hsv, np.array(hsv_range[0], np.uint8), np.array(hsv_range[1], np.uint8)) > 0
    else:
        f = rgb.astype(np.float32) / 255.0
        s = f.sum(2) + 1e-6
        r, g, b = f[..., 0] / s, f[..., 1] / s, f[..., 2] / s
        exg = 2 * g - r - b
        if threshold is None:
            threshold = max(otsu_threshold(exg[::4, ::4].ravel()), 0.02)
        m = exg > threshold
    if open_px:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * open_px + 1, 2 * open_px + 1))
        m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, k) > 0
    return m


def analyse_image(rgb: np.ndarray, marker_size_mm: float | None = None, dictionary: str = "DICT_4X4_50",
                  method: str = "exg", threshold: float | None = None, min_blob_px: int = 200,
                  mm_per_px: float | None = None, roi=None):
    """Returns (summary dict, list of blob dicts, mask, overlay RGB)."""
    import cv2

    img = rgb
    if roi is not None:
        x0, y0, x1, y1 = roi
        img = rgb[y0:y1, x0:x1]
    n_markers = 0
    if mm_per_px is None and marker_size_mm:
        mm_per_px, n_markers = image_mm_per_px(img, marker_size_mm, dictionary)
    mask = vegetation_mask_image(img, method, threshold)
    n, lab, stats, cents = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    blobs = []
    overlay = img.copy()
    tint = overlay.copy()
    tint[mask] = (0.4 * tint[mask] + 0.6 * np.array([255, 0, 200])).astype(np.uint8)
    overlay = tint
    a2 = (mm_per_px ** 2) if mm_per_px else None
    for k in range(1, n):
        area = int(stats[k, cv2.CC_STAT_AREA])
        if area < min_blob_px:
            mask[lab == k] = False
            continue
        comp = (lab == k).astype(np.uint8)
        cnts, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        hull = cv2.convexHull(np.vstack(cnts))
        hull_area = float(cv2.contourArea(hull))
        perim = float(sum(cv2.arcLength(c, True) for c in cnts))
        (cx, cy) = cents[k]
        _, (w, h), _ = cv2.minAreaRect(np.vstack(cnts))
        b = {"blob": len(blobs), "area_px": area, "hull_area_px": hull_area, "perimeter_px": perim,
             "cx": float(cx), "cy": float(cy), "length_px": float(max(w, h)), "width_px": float(min(w, h)),
             "solidity": area / hull_area if hull_area else 0.0}
        if a2:
            b["area_mm2"] = area * a2
            b["hull_area_mm2"] = hull_area * a2
            b["length_mm"] = b["length_px"] * mm_per_px
        blobs.append(b)
        cv2.drawContours(overlay, [hull], -1, (255, 255, 0), 2)
        cv2.putText(overlay, str(b["blob"]), (int(cx), int(cy)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    f = img.astype(np.float32)
    gsum = f.sum(2) + 1e-6
    exg = (2 * f[..., 1] - f[..., 0] - f[..., 2]) / gsum
    summary = {
        "width_px": img.shape[1], "height_px": img.shape[0],
        "canopy_area_px": int(mask.sum()), "canopy_cover": float(mask.mean()),
        "n_blobs": len(blobs), "mm_per_px": mm_per_px, "n_markers": n_markers,
        "exg_mean_canopy": float(exg[mask].mean()) if mask.any() else 0.0,
    }
    if a2:
        summary["canopy_area_mm2"] = float(mask.sum() * a2)
    return summary, blobs, mask, overlay


def batch(paths, out_dir, **kw) -> tuple[str, str]:
    """Analyse many images. Returns (summary CSV path, blob CSV path)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            files += sorted(f for f in p.iterdir() if f.suffix.lower() in IMG_EXT)
        else:
            files.append(p)
    srows, brows = [], []
    for f in files:
        rgb = read_image(f)
        summ, blobs, mask, overlay = analyse_image(rgb, **kw)
        summ = {"image": f.name, **summ}
        srows.append(summ)
        for b in blobs:
            brows.append({"image": f.name, **b})
        write_image(out / f"{f.stem}_overlay.png", overlay)
        write_image(out / f"{f.stem}_mask.png", (mask * 255).astype(np.uint8))
    sp, bp = out / "images_summary.csv", out / "images_blobs.csv"
    write_csv(sp, srows)
    write_csv(bp, brows)
    return str(sp), str(bp)


def write_csv(path, rows: list[dict]) -> None:
    keys: list[str] = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: (",".join(map(str, v)) if isinstance(v, (list, tuple)) else v) for k, v in r.items()})


def read_qr(rgb: np.ndarray) -> list[str]:
    """Decode QR codes in an image (tray / pot / lot labels)."""
    import cv2

    det = cv2.QRCodeDetector()
    try:
        ok, texts, _, _ = det.detectAndDecodeMulti(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        if ok:
            return [t for t in texts if t]
    except Exception:
        pass
    t, _, _ = det.detectAndDecode(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    return [t] if t else []


def exif_gps(path) -> dict | None:
    """Latitude / longitude / altitude from photo EXIF, if present."""
    try:
        from PIL import Image
        from PIL.ExifTags import GPSTAGS

        img = Image.open(path)
        exif = img.getexif()
        gps = exif.get_ifd(0x8825)
        if not gps:
            return None
        g = {GPSTAGS.get(k, k): v for k, v in gps.items()}

        def dms(v, ref):
            d = float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600
            return -d if ref in ("S", "W") else d

        out = {"lat": dms(g["GPSLatitude"], g.get("GPSLatitudeRef", "N")),
               "lon": dms(g["GPSLongitude"], g.get("GPSLongitudeRef", "E"))}
        if "GPSAltitude" in g:
            out["alt"] = float(g["GPSAltitude"])
        return out
    except Exception:
        return None
