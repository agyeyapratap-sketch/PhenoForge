"""Plant-level 3D traits.

All lengths are in scan units (metres once the scan is metric); areas in units^2 and
volumes in units^3. Results are returned as a flat dict so they drop straight into a CSV.

Notes on what each number means
-------------------------------
height_*           : distance above the ground plane (z = 0 after align_to_ground) at the
                     max / 99th / 95th percentile; percentiles are robust to stray points.
footprint_hull_m2  : area of the 2D convex hull of the top-down projection.
projected_area_m2  : area of occupied cells in a top-down grid (canopy cover, no gaps filled).
hull_volume_m3     : volume of the 3D convex hull.
voxel_volume_m3    : occupied voxels x voxel volume (a "virtual biomass" proxy; calibrate
                     against harvest dry weight).
surface_area_m2    : mesh area when the scan has a mesh of the plant, else a point-density
                     estimate: points are first projected onto a local plane fitted to their
                     60 nearest neighbours (moving least squares, removes scan noise across
                     the surface), then each point covers pi r_k^2 / k on that plane, with r_k
                     the distance to its k-th neighbour. On synthetic leaves this is within
                     ~5 % for noise up to half the point spacing (+13 % at 1.25x spacing).
                     For thin leaves it is the one-sided area. It counts only surfaces that
                     were seen, so overlapping leaves are underestimated.
"""

from __future__ import annotations

import numpy as np
from scipy.spatial import ConvexHull, cKDTree

from .clean import vegetation_indices
from .scan import Scan, median_spacing


def compute_traits(scan: Scan, grid: float | None = None, voxel: float | None = None,
                   ground_z: float | None = None, prefix: str = "") -> dict:
    pts = scan.points
    out: dict = {}
    n = len(pts)
    out["n_points"] = int(n)
    out["metric"] = bool(scan.metric)
    if n < 4:
        return {prefix + k: v for k, v in out.items()}
    gz = ground_z if ground_z is not None else (scan.ground_z if scan.ground_z is not None else float(pts[:, 2].min()))
    h = pts[:, 2] - gz
    spacing = median_spacing(pts)
    if grid is None:
        grid = max(spacing * 2.0, 1e-6)
    if voxel is None:
        voxel = grid

    out["height_max"] = float(h.max())
    out["height_p99"] = float(np.quantile(h, 0.99))
    out["height_p95"] = float(np.quantile(h, 0.95))
    out["height_mean"] = float(h.mean())

    xy = pts[:, :2]
    lo, hi = np.quantile(xy, 0.01, axis=0), np.quantile(xy, 0.99, axis=0)
    out["spread_x"] = float(hi[0] - lo[0])
    out["spread_y"] = float(hi[1] - lo[1])
    ctr = xy.mean(0)
    out["spread_max_diameter"] = float(2 * np.quantile(np.linalg.norm(xy - ctr, axis=1), 0.99))

    try:
        hull2 = ConvexHull(xy)
        out["footprint_hull_m2"] = float(hull2.volume)  # 2D 'volume' is area
        out["footprint_perimeter_m"] = float(hull2.area)
    except Exception:
        out["footprint_hull_m2"] = 0.0
        out["footprint_perimeter_m"] = 0.0
    cells = np.unique(np.floor(xy / grid).astype(np.int64), axis=0)
    out["projected_area_m2"] = float(len(cells) * grid * grid)
    out["grid_size"] = float(grid)
    try:
        hull3 = ConvexHull(pts)
        out["hull_volume_m3"] = float(hull3.volume)
        out["hull_surface_m2"] = float(hull3.area)
    except Exception:
        out["hull_volume_m3"] = 0.0
        out["hull_surface_m2"] = 0.0
    vox = np.unique(np.floor(pts / voxel).astype(np.int64), axis=0)
    out["voxel_volume_m3"] = float(len(vox) * voxel ** 3)
    out["voxel_size"] = float(voxel)
    out["solidity"] = float(out["voxel_volume_m3"] / out["hull_volume_m3"]) if out["hull_volume_m3"] > 0 else 0.0

    out["surface_area_m2"] = float(surface_area(scan))
    out["surface_area_method"] = "mesh" if scan.has_mesh else "mls-density"

    # lean: angle between vertical and the line from the base centre to the top centroid
    base = pts[h <= np.quantile(h, 0.1)]
    top = pts[h >= np.quantile(h, 0.9)]
    v = top.mean(0) - base.mean(0)
    out["lean_deg"] = float(np.degrees(np.arccos(abs(v[2]) / (np.linalg.norm(v) + 1e-12))))
    out["centroid_height"] = float(h.mean())

    if scan.colors is not None:
        vi = vegetation_indices(scan.colors)
        out["exg_mean"] = float(vi["exg"].mean())
        out["gli_mean"] = float(vi["gli"].mean())
        out["vari_mean"] = float(vi["vari"].mean())
        out["green_fraction"] = float(np.mean(vi["gli"] > 0.05))
        out["rgb_mean"] = [float(x) for x in scan.colors.mean(0).round(4)]
    if scan.labels is not None:
        out["n_labels"] = int(len(np.unique(scan.labels[scan.labels >= 0])))
    return {prefix + k: v for k, v in out.items()}


def surface_area(scan: Scan) -> float:
    if scan.has_mesh:
        V, F = scan.mesh_vertices, scan.mesh_triangles
        a = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
        return float(0.5 * np.linalg.norm(a, axis=1).sum())
    return point_density_area(scan.points)


def mls_project(points: np.ndarray, k: int = 60, chunk: int = 40000):
    """Project each point onto the PCA plane of its k nearest neighbours.
    Returns (projected points, unit normals)."""
    pts = np.asarray(points, float)
    k = min(k, len(pts))
    tree = cKDTree(pts)
    out = np.empty_like(pts)
    nrm = np.empty_like(pts)
    for s in range(0, len(pts), chunk):
        p = pts[s:s + chunk]
        _, nb = tree.query(p, k=k)
        N = pts[nb]
        mu = N.mean(1)
        Q = N - mu[:, None]
        C = np.einsum("nki,nkj->nij", Q, Q)
        _, V = np.linalg.eigh(C)
        n = V[:, :, 0]
        out[s:s + chunk] = p - ((p - mu) * n).sum(1)[:, None] * n
        nrm[s:s + chunk] = n
    return out, nrm


def point_density_area(points: np.ndarray, k: int = 10, k_mls: int = 60, chunk: int = 40000) -> float:
    """Surface area from local sampling density on the MLS-smoothed surface: each point
    covers pi r_k^2 / k of the local tangent plane."""
    pts = np.asarray(points, float)
    if len(pts) <= max(k, 4):
        return 0.0
    ps, n = mls_project(pts, k=k_mls, chunk=chunk)
    tree = cKDTree(ps)
    rk = np.empty(len(ps))
    for s in range(0, len(ps), chunk):
        _, nb = tree.query(ps[s:s + chunk], k=k + 1)
        D = ps[nb[:, 1:]] - ps[s:s + chunk, None, :]
        nn = n[s:s + chunk, None, :]
        D2 = D - (D * nn).sum(-1, keepdims=True) * nn
        rk[s:s + chunk] = np.linalg.norm(D2, axis=-1).max(1)
    # cap isolated points so a few strays do not dominate
    rk = np.minimum(rk, np.quantile(rk, 0.98))
    return float(np.sum(np.pi * rk ** 2 / k))


def longest_path_length(points: np.ndarray, radius: float | None = None) -> float:
    """Geodesic length of a component along a k-NN graph: the longest shortest path between
    two extreme points (double sweep). For a leaf this approximates midrib length."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import dijkstra, connected_components

    pts = np.asarray(points)
    if len(pts) < 3:
        return float(np.linalg.norm(pts.max(0) - pts.min(0))) if len(pts) else 0.0
    if len(pts) > 4000:
        pts = pts[np.random.default_rng(0).choice(len(pts), 4000, replace=False)]
    if radius is None:
        radius = 3 * median_spacing(pts, sample=2000)
    tree = cKDTree(pts)
    pairs = tree.query_pairs(radius, output_type="ndarray")
    if len(pairs) == 0:
        return 0.0
    w = np.linalg.norm(pts[pairs[:, 0]] - pts[pairs[:, 1]], axis=1)
    G = coo_matrix((w, (pairs[:, 0], pairs[:, 1])), shape=(len(pts), len(pts))).tocsr()
    ncomp, lab = connected_components(G, directed=False)
    big = np.argmax(np.bincount(lab))
    nodes = np.where(lab == big)[0]
    start = nodes[0]
    d0 = dijkstra(G, directed=False, indices=start)
    a = nodes[np.argmax(np.where(np.isfinite(d0[nodes]), d0[nodes], -1))]
    d1 = dijkstra(G, directed=False, indices=a)
    return float(np.nanmax(np.where(np.isfinite(d1[nodes]), d1[nodes], np.nan)))


def component_traits(scan: Scan, labels: np.ndarray, min_points: int = 30, geodesic: bool = True) -> list[dict]:
    """Per-label traits (for leaf candidates or plant instances)."""
    rows = []
    for lab in np.unique(labels):
        if lab < 0:
            continue
        m = labels == lab
        if m.sum() < min_points:
            continue
        p = scan.points[m]
        row = {"label": int(lab), "n_points": int(m.sum())}
        row["area_m2"] = point_density_area(p) if not scan.has_mesh else float("nan")
        ext = np.ptp(p, axis=0)
        evals = np.sort(np.linalg.eigvalsh(np.cov((p - p.mean(0)).T)))[::-1] if len(p) > 3 else np.zeros(3)
        row["pca_length"] = float(4 * np.sqrt(max(evals[0], 0)))  # ~ full length for uniform spread
        row["bbox_x"], row["bbox_y"], row["bbox_z"] = (float(e) for e in ext)
        row["length_geodesic"] = longest_path_length(p) if geodesic else float("nan")
        c = p.mean(0)
        row["cx"], row["cy"], row["cz"] = (float(x) for x in c)
        row["top_z"] = float(p[:, 2].max())
        rows.append(row)
    return rows
