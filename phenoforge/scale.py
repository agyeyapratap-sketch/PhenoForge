"""Metric scale: ArUco markers, two-point reference, or a known object size.

Phone LiDAR scans are already metric. Photogrammetry and splat reconstructions are not, so
the scale comes from markers of known size lying in the scene. The approach here works on
any coloured scan: render a top-down orthographic image of the cloud, detect ArUco markers
in it, and compare the measured marker side (in scan units) with the printed size.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .scan import Scan, median_spacing

ARUCO_DICTS = [
    "DICT_4X4_50", "DICT_4X4_100", "DICT_4X4_250", "DICT_4X4_1000",
    "DICT_5X5_50", "DICT_5X5_100", "DICT_5X5_250", "DICT_5X5_1000",
    "DICT_6X6_50", "DICT_6X6_250", "DICT_7X7_50", "DICT_ARUCO_ORIGINAL",
    "DICT_APRILTAG_16h5", "DICT_APRILTAG_25h9", "DICT_APRILTAG_36h10", "DICT_APRILTAG_36h11",
]


@dataclass
class MarkerScale:
    factor: float                       # multiply scan coordinates by this to get metres
    marker_sizes_units: dict[int, float] = field(default_factory=dict)
    cv_percent: float = 0.0             # spread of the per-marker estimates
    n_markers: int = 0
    rejected: list[int] = field(default_factory=list)
    image: np.ndarray | None = None     # the orthographic render with detections drawn
    pixel_size: float = 0.0

    def summary(self) -> str:
        return (f"{self.n_markers} marker(s), scale x{self.factor:.6g}, "
                f"spread {self.cv_percent:.2f}% (rejected {self.rejected})")


def orthographic_render(scan: Scan, pixel_size: float | None = None, max_side: int = 3000,
                        axis: int = 2, top: bool = True, fill: int = 2):
    """Render colours seen from +axis (top view by default) into an RGB uint8 image.

    Returns (image, pixel_size, origin_xy) where pixel (r, c) maps to
    x = origin[0] + c * pixel_size, y = origin[1] + (H - 1 - r) * pixel_size.
    """
    if scan.colors is None:
        raise ValueError("Scan has no colours; markers cannot be found")
    keep_axes = [a for a in range(3) if a != axis]
    xy = scan.points[:, keep_axes]
    z = scan.points[:, axis] if top else -scan.points[:, axis]
    lo, hi = xy.min(0), xy.max(0)
    ext = (hi - lo).max()
    if pixel_size is None:
        pixel_size = max(median_spacing(scan.points) * 1.5, ext / max_side)
    W = int(np.ceil((hi[0] - lo[0]) / pixel_size)) + 1
    H = int(np.ceil((hi[1] - lo[1]) / pixel_size)) + 1
    c = ((xy[:, 0] - lo[0]) / pixel_size).astype(int)
    r = (H - 1 - (xy[:, 1] - lo[1]) / pixel_size).astype(int)
    # z-buffer: sort ascending so the highest point is written last
    order = np.argsort(z)
    img = np.zeros((H, W, 3), np.float32)
    filled = np.zeros((H, W), np.float32)
    img[r[order], c[order]] = scan.colors[order]
    filled[r, c] = 1.0
    if fill:
        import cv2

        # normalised convolution: fill holes with the mean of nearby rendered pixels without
        # biasing edges towards light or dark (a max/min filter would shrink marker cells)
        k = 2 * fill + 1
        num = cv2.blur(img * filled[..., None], (k, k))
        den = cv2.blur(filled, (k, k))
        hole = (filled == 0) & (den > 0)
        img[hole] = num[hole] / den[hole][:, None]
    img = (np.clip(img, 0, 1) * 255).astype(np.uint8)
    return img, float(pixel_size), lo


def detect_aruco(image: np.ndarray, dictionary: str = "DICT_4X4_50", allowed_ids=None):
    """Detect markers in an RGB/BGR uint8 image. Returns (corners list (4x2), ids array)."""
    import cv2

    d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dictionary))
    params = cv2.aruco.DetectorParameters()
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    det = cv2.aruco.ArucoDetector(d, params)
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    corners, ids, _ = det.detectMarkers(gray)
    if ids is None:
        return [], np.array([], int)
    ids = ids.ravel().astype(int)
    corners = [c.reshape(4, 2) for c in corners]
    if allowed_ids is not None:
        allowed = set(int(i) for i in allowed_ids)
        keep = [k for k, i in enumerate(ids) if i in allowed]
        corners = [corners[k] for k in keep]
        ids = ids[keep]
    return corners, ids


def marker_side_px(corners: np.ndarray) -> float:
    c = np.asarray(corners, float)
    return float(np.mean([np.linalg.norm(c[i] - c[(i + 1) % 4]) for i in range(4)]))


def scale_from_aruco(scan: Scan, marker_size_m: float, dictionary: str = "DICT_4X4_50",
                     allowed_ids=None, pixel_size: float | None = None,
                     reject_percent: float = 4.0, views=("top",)) -> MarkerScale:
    """Measure markers in orthographic renders and return the scale factor to metres.

    Markers should lie roughly flat in the view (on the soil, tray, pot rims or deck after
    ``align_to_ground``). Per-marker estimates more than ``reject_percent`` from the median
    are rejected, as a tilted or partly occluded marker reads short.
    """
    import cv2

    shown = None
    used_px = 0.0
    view_axes = {"top": (2, True), "front": (1, False), "back": (1, True), "left": (0, False), "right": (0, True)}
    per_marker: dict[int, list[float]] = {}
    base_px = pixel_size or median_spacing(scan.points)
    # several render resolutions: sparse scans need coarser pixels, dense ones finer
    factors = (1.0,) if pixel_size else (1.5, 2.5, 4.0)
    for v in views:
        axis, top = view_axes[v]
        for f in factors:
            px_try = base_px * f
            try:
                img, px, _ = orthographic_render(scan, pixel_size=px_try, axis=axis, top=top, fill=3)
            except ValueError:
                raise
            img = cv2.medianBlur(img, 3)
            corners, ids = detect_aruco(img, dictionary, allowed_ids)
            if shown is None or len(ids) > len(per_marker):
                shown = img.copy()
                used_px = px
                if len(ids):
                    bgr = cv2.cvtColor(shown, cv2.COLOR_RGB2BGR)
                    cv2.aruco.drawDetectedMarkers(bgr, [c.reshape(1, 4, 2).astype(np.float32) for c in corners],
                                                  ids.reshape(-1, 1))
                    shown = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            for c, i in zip(corners, ids):
                # remember the marker's world position for the refinement pass
                ctr = c.mean(0)
                per_marker.setdefault(int(i), []).append((axis, top, ctr, marker_side_px(c) * px, img.shape[0], px))
    # refinement: re-render a crop around each marker so it spans ~150 px, then measure
    sizes = {}
    for i, dets in per_marker.items():
        axis, top, ctr, side, H, px = max(dets, key=lambda d: d[3] / d[5])  # most pixels
        refined = _refine_marker(scan, axis, top, ctr, side, H, px, dictionary, i)
        sizes[i] = refined if refined else float(np.median([d[3] for d in dets]))
    if not sizes:
        raise RuntimeError("No ArUco markers detected. Check the dictionary, that markers are "
                           "visible and flat in the chosen view, and that the scan is coloured.")
    vals = np.array(list(sizes.values()))
    med = np.median(vals)
    good = {i: s for i, s in sizes.items() if abs(s - med) / med * 100 <= reject_percent}
    rejected = sorted(set(sizes) - set(good))
    g = np.array(list(good.values()))
    factor = marker_size_m / float(np.mean(g))
    cv = float(np.std(g) / np.mean(g) * 100) if len(g) > 1 else 0.0
    return MarkerScale(factor=factor, marker_sizes_units=sizes, cv_percent=cv, n_markers=len(good),
                       rejected=rejected, image=shown, pixel_size=used_px)


def _refine_marker(scan, axis, top, ctr_px, side, H, px, dictionary, marker_id):
    """Measure one marker on a high-resolution crop. Returns side length in scan units."""
    keep_axes = [a for a in range(3) if a != axis]
    xy = scan.points[:, keep_axes]
    lo = xy.min(0)
    cx = lo[0] + ctr_px[0] * px
    cy = lo[1] + (H - 1 - ctr_px[1]) * px
    half = side * 1.2
    m = (np.abs(xy[:, 0] - cx) < half) & (np.abs(xy[:, 1] - cy) < half)
    if m.sum() < 100:
        return None
    sub = scan.subset(m)
    spacing = median_spacing(sub.points)
    best = None
    for target in (150, 110, 200):
        p2 = max(side / target, spacing * 0.6)
        fill = int(max(2, np.ceil(1.5 * spacing / p2)))
        img, p2, _ = orthographic_render(sub, pixel_size=p2, axis=axis, top=top, fill=fill)
        corners, ids = detect_aruco(img, dictionary, [marker_id])
        if len(ids):
            best = edge_fit_side_px(img, corners[0]) * p2
            break
    return best


def edge_fit_side_px(image: np.ndarray, corners: np.ndarray, samples: int = 40, search: float = 0.08) -> float:
    """Marker side from straight-line fits to the middle of each edge.

    Corner positions are pulled inwards when the marker edges are blurred (scan noise
    rounds the corners), which biases the size low. Fitting the four edges away from the
    corners and measuring the distance between opposite edge lines avoids that.
    """
    import cv2
    from scipy.ndimage import map_coordinates

    g = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    g = cv2.GaussianBlur(g.astype(np.float32), (0, 0), 0.8)
    c = np.asarray(corners, float)
    side = marker_side_px(c)
    ctr = c.mean(0)
    lines = []
    for k in range(4):
        a, b = c[k], c[(k + 1) % 4]
        t = np.linspace(0.2, 0.8, samples)
        pts = a + np.outer(t, b - a)
        d = (b - a) / np.linalg.norm(b - a)
        n = np.array([-d[1], d[0]])
        if np.dot(ctr - a, n) > 0:
            n = -n  # outward normal
        offs = np.linspace(-search * side, search * side, 41)
        edge_pts = []
        for p in pts:
            q = p + np.outer(offs, n)
            prof = map_coordinates(g, [q[:, 1], q[:, 0]], order=1, mode="nearest")
            grad = np.gradient(prof)
            j = int(np.argmax(np.abs(grad)))
            if 0 < j < len(grad) - 1:
                y0, y1, y2 = np.abs(grad[j - 1:j + 2])
                den = y0 - 2 * y1 + y2
                frac = 0.5 * (y0 - y2) / den if den != 0 else 0.0
            else:
                frac = 0.0
            o = offs[j] + frac * (offs[1] - offs[0])
            edge_pts.append(p + o * n)
        E = np.array(edge_pts)
        m = E.mean(0)
        _, _, vt = np.linalg.svd(E - m)
        lines.append((m, vt[0]))  # point, direction
    dists = []
    for k in (0, 1):
        (m1, d1), (m2, d2) = lines[k], lines[k + 2]
        dd = (d1 + (d2 if np.dot(d1, d2) > 0 else -d2)) / 2
        nn = np.array([-dd[1], dd[0]]) / np.linalg.norm(dd)
        dists.append(abs(np.dot(m2 - m1, nn)))
    est = float(np.mean(dists))
    # fall back to the corner estimate if the edge search went astray
    return est if abs(est - side) / side < 0.1 else side


def apply_aruco_scale(scan: Scan, marker_size_m: float, **kw) -> tuple[Scan, MarkerScale]:
    res = scale_from_aruco(scan, marker_size_m, **kw)
    s = scan.copy()
    s.scale(res.factor, note=f"ArUco scale: {res.summary()}")
    s.metadata["scale"] = {"method": "aruco", "factor": res.factor, "markers": res.marker_sizes_units,
                           "cv_percent": res.cv_percent, "marker_size_m": marker_size_m}
    return s, res


def scale_from_two_points(p1, p2, true_distance_m: float) -> float:
    d = float(np.linalg.norm(np.asarray(p1, float) - np.asarray(p2, float)))
    if d <= 0:
        raise ValueError("The two points coincide")
    return true_distance_m / d


def apply_factor(scan: Scan, factor: float, method: str) -> Scan:
    s = scan.copy()
    s.scale(factor, note=f"{method} scale x{factor:.6g}")
    s.metadata["scale"] = {"method": method, "factor": factor}
    return s


def image_mm_per_px(image: np.ndarray, marker_size_mm: float, dictionary: str = "DICT_4X4_50",
                    allowed_ids=None) -> tuple[float | None, int]:
    """mm per pixel for a 2D photo from the ArUco markers in it (None if none found)."""
    corners, ids = detect_aruco(image, dictionary, allowed_ids)
    if not len(ids):
        return None, 0
    side = np.median([marker_side_px(c) for c in corners])
    return marker_size_mm / side, len(ids)


def make_marker_sheet(path: str, dictionary: str = "DICT_4X4_50", ids=range(9), marker_mm: float = 50.0,
                      dpi: int = 300, cols: int = 3) -> None:
    """Write a printable PNG sheet of markers with their IDs and the printed size."""
    import cv2

    d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dictionary))
    px = int(round(marker_mm / 25.4 * dpi))
    gap = px // 3
    ids = list(ids)
    rows = int(np.ceil(len(ids) / cols))
    W = cols * px + (cols + 1) * gap
    H = rows * (px + gap) + gap + 60
    sheet = np.full((H, W), 255, np.uint8)
    for k, i in enumerate(ids):
        r, c = divmod(k, cols)
        m = cv2.aruco.generateImageMarker(d, int(i), px)
        y, x = gap + r * (px + gap), gap + c * (px + gap)
        sheet[y:y + px, x:x + px] = m
        cv2.putText(sheet, f"id {i}", (x, y + px + gap // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.8, 0, 2)
    cv2.putText(sheet, f"{dictionary}  marker side {marker_mm:g} mm at {dpi} dpi (print at 100%)",
                (gap, H - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, 0, 2)
    cv2.imwrite(path, sheet)
