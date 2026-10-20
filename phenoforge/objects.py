"""Object dimensions for fruit, tubers, seeds and postharvest produce on a bench or line.

``object_dimensions`` separates objects (DBSCAN, or labels you pass in) and measures each:

length / width / thickness : extents along the object's principal axes (PCA), taken between
                             the 1st and 99th percentile of the points so a few stray points do
                             not inflate them. On a sampled surface this reads ~2 % short of the
                             true calliper size (a sphere's surface is uniform along any axis).
equiv_diameter             : diameter of the sphere with the same convex-hull volume.
hull_volume / hull_area    : 3D convex hull (closed scans; a one-sided scan of an object lying
                             on a bench gives the hull of what was seen).
sphericity                 : pi^(1/3) (6 V)^(2/3) / A  (Wadell); 1 for a sphere, lower for
                             elongated or flat objects. Uses the convex hull, so concavities
                             are bridged.
elongation / flatness      : length / width and width / thickness.
height_max                 : top of the object above the ground (z = 0 after align_to_ground).

Lengths follow the scan units (metres once ``scan.metric``); areas units^2, volumes units^3.
Remove the ground / bench before calling (``clean.align_to_ground(remove=True)``), otherwise
the bench joins all objects into one.
"""

from __future__ import annotations

import numpy as np
from scipy.spatial import ConvexHull

from .clean import vegetation_indices
from .scan import Scan, cluster_eps
from .segment import _drop_small


def separate_objects(scan: Scan, eps: float | None = None, min_points: int = 50) -> np.ndarray:
    """DBSCAN instance labels (0..n-1, -1 = noise / too small)."""
    if eps is None:
        eps = cluster_eps(scan.points, 10)
    lab = np.asarray(scan.to_o3d().cluster_dbscan(eps=eps, min_points=10), int)
    return _drop_small(lab, min_points)


def object_dimensions(scan: Scan, labels: np.ndarray | None = None, min_points: int = 50,
                      log=print) -> tuple[np.ndarray, list[dict]]:
    """Measure each object. Returns (labels per point, one row per object)."""
    if labels is None:
        labels = separate_objects(scan, min_points=min_points)
    else:
        labels = _drop_small(np.asarray(labels, int).reshape(-1), min_points)
    gz = scan.ground_z if scan.ground_z is not None else 0.0
    rows = []
    for k in np.unique(labels[labels >= 0]):
        m = labels == k
        row = {"object_id": int(k)}
        row.update(measure_object(scan.points[m], None if scan.colors is None else scan.colors[m], gz))
        row["metric"] = bool(scan.metric)
        rows.append(row)
    log(f"objects: {len(rows)} measured ({np.sum(labels < 0)} points unassigned)")
    return labels, rows


def measure_object(pts: np.ndarray, colors: np.ndarray | None = None, ground_z: float = 0.0) -> dict:
    pts = np.asarray(pts, float)
    out: dict = {"n_points": int(len(pts))}
    c = pts.mean(0)
    out["centroid_x"], out["centroid_y"], out["centroid_z"] = (float(v) for v in c)
    if len(pts) >= 3:
        evals, evecs = np.linalg.eigh(np.cov((pts - c).T))
        axes = evecs[:, np.argsort(evals)[::-1]]
        proj = (pts - c) @ axes
        ext = np.quantile(proj, 0.99, axis=0) - np.quantile(proj, 0.01, axis=0)
    else:
        axes, ext = np.eye(3), np.zeros(3)
    L, W, T = (float(v) for v in ext)
    out["length"], out["width"], out["thickness"] = L, W, T
    out["axis_length_x"], out["axis_length_y"], out["axis_length_z"] = (float(v) for v in axes[:, 0])
    vol = area = 0.0
    if len(pts) >= 4:
        try:
            hull = ConvexHull(pts)
            vol, area = float(hull.volume), float(hull.area)
        except Exception:  # coplanar / degenerate
            pass
    out["hull_volume"], out["hull_area"] = vol, area
    if vol > 0:
        out["equiv_diameter"] = float((6 * vol / np.pi) ** (1 / 3))
    else:
        out["equiv_diameter"] = float(np.cbrt(max(L * W * T, 0.0)))
    out["sphericity"] = float(np.pi ** (1 / 3) * (6 * vol) ** (2 / 3) / area) if area > 0 else float("nan")
    out["elongation"] = float(L / W) if W > 0 else float("nan")
    out["flatness"] = float(W / T) if T > 0 else float("nan")
    out["height_max"] = float(pts[:, 2].max() - ground_z)
    out["height_min"] = float(pts[:, 2].min() - ground_z)
    if colors is not None and len(colors):
        rgb = np.asarray(colors, float).mean(0)
        out["mean_r"], out["mean_g"], out["mean_b"] = (float(v) for v in rgb)
        out["hue_deg"] = float(vegetation_indices(rgb[None])["hue"][0])
    return out
