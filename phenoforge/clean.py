"""Cleaning and framing: outliers, downsampling, cropping, ground plane, vegetation filter."""

from __future__ import annotations

import numpy as np

from .scan import Scan, cluster_eps, median_spacing


def voxel_downsample(scan: Scan, voxel: float) -> Scan:
    """Average points per voxel (keeps colours, recomputes normals later if needed)."""
    pc = scan.to_o3d().voxel_down_sample(voxel)
    out = Scan.from_o3d(pc, name=scan.name, source=scan.source, metric=scan.metric,
                        ground_z=scan.ground_z, metadata=dict(scan.metadata), history=list(scan.history))
    out.mesh_vertices, out.mesh_triangles, out.mesh_colors = scan.mesh_vertices, scan.mesh_triangles, scan.mesh_colors
    out.history.append(f"voxel downsample {voxel:g} -> {len(out)} points")
    return out


def remove_statistical_outliers(scan: Scan, nb_neighbors: int = 20, std_ratio: float = 2.0) -> Scan:
    _, idx = scan.to_o3d().remove_statistical_outlier(nb_neighbors=nb_neighbors, std_ratio=std_ratio)
    mask = np.zeros(len(scan), bool)
    mask[np.asarray(idx, int)] = True
    return scan.subset(mask, f"statistical outliers (k={nb_neighbors}, std={std_ratio}) removed {np.sum(~mask)}")


def remove_radius_outliers(scan: Scan, nb_points: int = 8, radius: float | None = None) -> Scan:
    if radius is None:
        radius = 4 * median_spacing(scan.points)
    _, idx = scan.to_o3d().remove_radius_outlier(nb_points=nb_points, radius=radius)
    mask = np.zeros(len(scan), bool)
    mask[np.asarray(idx, int)] = True
    return scan.subset(mask, f"radius outliers (n={nb_points}, r={radius:.4g}) removed {np.sum(~mask)}")


def crop_box(scan: Scan, lo, hi) -> Scan:
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    m = np.all((scan.points >= lo) & (scan.points <= hi), axis=1)
    return scan.subset(m, f"crop box {lo.round(4).tolist()} - {hi.round(4).tolist()}")


def crop_cylinder(scan: Scan, center_xy, radius: float, zmin: float = -np.inf, zmax: float = np.inf) -> Scan:
    c = np.asarray(center_xy, float)
    r = np.linalg.norm(scan.points[:, :2] - c, axis=1)
    m = (r <= radius) & (scan.points[:, 2] >= zmin) & (scan.points[:, 2] <= zmax)
    return scan.subset(m, f"crop cylinder r={radius:g} at {c.round(4).tolist()}")


def fit_ground_plane(scan: Scan, distance: float | None = None, iterations: int = 2000,
                     prefer_low: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """RANSAC the dominant plane (soil, pot rims, table, tray).

    Returns (plane abcd with unit normal pointing to the plant side, inlier mask).
    When ``prefer_low`` is set, the plane is searched among the lowest 40 % of points along
    the current up axis estimate so that a big leaf is not mistaken for the ground.
    """
    pts = scan.points
    if distance is None:
        distance = 2.0 * median_spacing(pts)
    import open3d as o3d

    cand = np.arange(len(pts))
    if prefer_low:
        up = _guess_up(scan)
        h = pts @ up
        cand = np.where(h <= np.quantile(h, 0.4))[0]
    pc = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(pts[cand]))
    plane, _ = pc.segment_plane(distance_threshold=distance, ransac_n=3, num_iterations=iterations)
    plane = np.asarray(plane, float)
    plane /= np.linalg.norm(plane[:3])
    d = pts @ plane[:3] + plane[3]
    # orient the normal towards the side with most points (the plant)
    if np.sum(d > distance) < np.sum(d < -distance):
        plane = -plane
        d = -d
    inliers = np.abs(d) <= distance
    return plane, inliers


def _guess_up(scan: Scan) -> np.ndarray:
    """Up direction guess: +Z unless the cloud's smallest principal axis says otherwise
    (USD/GLB scans are usually Y-up before conversion)."""
    meta_up = scan.metadata.get("up_axis")
    if meta_up is not None:
        return np.asarray(meta_up, float)
    return np.array([0.0, 0.0, 1.0])


def align_to_ground(scan: Scan, plane: np.ndarray | None = None, remove: bool = True,
                    margin: float | None = None) -> Scan:
    """Rotate/translate so the ground plane is z = 0 with the plant above it.

    With ``remove`` the ground inliers (and anything below them) are dropped.
    """
    s = scan.copy()
    if plane is None:
        plane, _ = fit_ground_plane(s)
    n = plane[:3] / np.linalg.norm(plane[:3])
    R = _rotation_from_to(n, np.array([0.0, 0.0, 1.0]))
    T = np.eye(4)
    T[:3, :3] = R
    # a point on the plane
    p0 = -plane[3] * n
    T[:3, 3] = -(R @ p0)
    s.transform(T)
    s.ground_z = 0.0
    s.history.append(f"aligned ground plane to z=0 (normal {n.round(3).tolist()})")
    s.metadata["ground_transform"] = T.tolist()
    if remove:
        if margin is None:
            margin = 2.0 * median_spacing(s.points)
        keep = s.points[:, 2] > margin
        s = s.subset(keep, f"removed ground/below-ground points (margin {margin:.4g}): {np.sum(~keep)}")
    return s


def _rotation_from_to(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    v = np.cross(a, b)
    c = float(np.dot(a, b))
    if np.linalg.norm(v) < 1e-12:
        if c > 0:
            return np.eye(3)
        # 180 degrees: rotate about any axis perpendicular to a
        axis = np.array([1.0, 0, 0]) if abs(a[0]) < 0.9 else np.array([0, 1.0, 0])
        axis = np.cross(a, axis)
        axis /= np.linalg.norm(axis)
        return 2 * np.outer(axis, axis) - np.eye(3)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * (1 / (1 + c))


def convert_y_up(scan: Scan) -> Scan:
    """Convert a Y-up scan (glTF / Apple / most phone apps) to Z-up."""
    s = scan.copy()
    R = np.array([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float)
    s.transform(R)
    s.history.append("converted Y-up to Z-up")
    return s


# ------------------------------------------------------------- vegetation index
def vegetation_indices(colors: np.ndarray) -> dict[str, np.ndarray]:
    """Per-point colour indices from RGB in [0, 1].

    ExG  = 2g - r - b on chromatic coordinates (Woebbecke et al. 1995)
    GLI  = (2G - R - B) / (2G + R + B)            (Louhaichi et al. 2001)
    VARI = (G - R) / (G + R - B)                  (Gitelson et al. 2002)
    hue  = HSV hue in degrees
    """
    c = np.asarray(colors, float)
    R, G, B = c[:, 0], c[:, 1], c[:, 2]
    s = R + G + B + 1e-9
    r, g, b = R / s, G / s, B / s
    exg = 2 * g - r - b
    gli = (2 * G - R - B) / (2 * G + R + B + 1e-9)
    den = G + R - B
    vari = np.where(np.abs(den) > 1e-3, (G - R) / np.where(np.abs(den) > 1e-3, den, 1), 0.0)
    mx, mn = c.max(1), c.min(1)
    delta = mx - mn + 1e-9
    hue = np.where(mx == R, ((G - B) / delta) % 6, np.where(mx == G, (B - R) / delta + 2, (R - G) / delta + 4)) * 60
    return {"exg": exg, "gli": gli, "vari": np.clip(vari, -1, 1), "hue": hue}


def vegetation_mask(scan: Scan, method: str = "exg", threshold: float | None = None) -> np.ndarray:
    """Boolean mask of plant-coloured points. ``threshold=None`` picks Otsu on the index."""
    if scan.colors is None:
        return np.ones(len(scan), bool)
    idx = vegetation_indices(scan.colors)
    if method == "hue":  # green to yellow-green and senesced straw (wheat): 35-170 deg
        h = idx["hue"]
        lo, hi = (35, 170) if threshold is None else (threshold, 170)
        return (h >= lo) & (h <= hi)
    v = idx[method]
    if threshold is None:
        # Otsu, capped: once the ground is removed the histogram is plant-only and Otsu
        # would split pale stems from leaves instead of plant from soil
        threshold = min(otsu_threshold(v), _VEG_MAX_THRESHOLD.get(method, np.inf))
    return v > threshold


_VEG_MAX_THRESHOLD = {"exg": 0.10, "gli": 0.05, "vari": 0.05}


def keep_vegetation(scan: Scan, method: str = "exg", threshold: float | None = None) -> Scan:
    m = vegetation_mask(scan, method, threshold)
    return scan.subset(m, f"kept vegetation ({method}, thr={threshold}) {m.sum()} / {len(m)}")


def otsu_threshold(values: np.ndarray, bins: int = 256) -> float:
    v = np.asarray(values, float)
    v = v[np.isfinite(v)]
    if len(v) == 0:
        return 0.0
    hist, edges = np.histogram(v, bins=bins)
    centers = (edges[:-1] + edges[1:]) / 2
    w0 = np.cumsum(hist)
    w1 = w0[-1] - w0
    m0 = np.cumsum(hist * centers) / np.maximum(w0, 1)
    mt = (hist * centers).sum()
    m1 = (mt - np.cumsum(hist * centers)) / np.maximum(w1, 1)
    between = w0 * w1 * (m0 - m1) ** 2
    return float(centers[np.argmax(between)])


def largest_clusters(scan: Scan, eps: float | None = None, min_points: int = 10, keep: int = 1,
                     min_fraction: float = 0.0) -> Scan:
    """Keep the ``keep`` largest DBSCAN clusters (drops floating debris)."""
    if eps is None:
        eps = cluster_eps(scan.points, min_points)
    lab = np.asarray(scan.to_o3d().cluster_dbscan(eps=eps, min_points=min_points), int)
    if lab.max(initial=-1) < 0:
        return scan.copy()
    sizes = np.bincount(lab[lab >= 0])
    order = np.argsort(sizes)[::-1]
    chosen = [i for i in order[:keep] if sizes[i] >= min_fraction * len(scan)]
    m = np.isin(lab, chosen)
    return scan.subset(m, f"kept {len(chosen)} largest cluster(s) (eps={eps:.4g})")
