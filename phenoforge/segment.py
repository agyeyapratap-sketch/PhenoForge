"""Segmentation of scans into plants (instances) and leaf / organ candidates.

Plants
  * ``plants_watershed``  : top-down height map, one seed per local canopy maximum, marker
                            watershed on the occupancy mask. Handles touching rosettes in trays.
  * ``plants_pot_grid``   : known pot layout (rows x cols, pitch, origin) or explicit centres;
                            each point goes to the nearest pot centre within a radius
                            (Voronoi cells), the layout used for equidistant pots on a bench.
  * ``plants_dbscan``     : connected components in XY for well-separated plants.

Leaves / organs
  * ``leaf_candidates_components`` : 3D connected components after removing a stem core.
  * ``leaf_candidates_region_growing`` : smooth-surface region growing on normals; splits
                            leaves that touch at an angle. Like any geometric method it
                            gives visible-leaf candidates, not guaranteed biological leaves.
  * ``organs_by_colour``  : hue / brightness classes, e.g. straw-coloured wheat heads against
                            green leaves.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage as ndi
from scipy.spatial import cKDTree

from .clean import vegetation_indices
from .scan import Scan, median_spacing


# ------------------------------------------------------------------ plants
def height_map(scan: Scan, cell: float):
    """Max height per XY cell. Returns (H array with NaN for empty, origin, rows, cols of points)."""
    xy = scan.points[:, :2]
    lo = xy.min(0)
    ij = np.floor((xy - lo) / cell).astype(int)
    shape = ij.max(0) + 1
    hm = np.full((shape[1], shape[0]), -np.inf)
    np.maximum.at(hm, (ij[:, 1], ij[:, 0]), scan.points[:, 2])
    hm[np.isinf(hm)] = np.nan
    return hm, lo, ij


def plants_watershed(scan: Scan, cell: float | None = None, min_distance: float | None = None,
                     smooth: float = 1.5, min_points: int = 50, expected: int | None = None) -> np.ndarray:
    """Instance labels per point (0..n-1, -1 = unassigned)."""
    from skimage.segmentation import watershed
    from skimage.feature import peak_local_max

    if cell is None:
        cell = 3 * median_spacing(scan.points)
    hm, lo, ij = height_map(scan, cell)
    occ = np.isfinite(hm)
    occ = ndi.binary_closing(occ, iterations=2) | occ
    occ = ndi.binary_fill_holes(occ)
    filled = np.where(np.isfinite(hm), hm, np.nanmin(hm) if np.isfinite(hm).any() else 0)
    # fill empty cells inside the mask from neighbours so the surface is continuous
    if (~np.isfinite(hm) & occ).any():
        idx = ndi.distance_transform_edt(~np.isfinite(hm), return_distances=False, return_indices=True)
        filled = filled[tuple(idx)]
    sm = ndi.gaussian_filter(filled, smooth)
    if min_distance is None:
        ext = np.ptp(scan.points[:, :2], axis=0).max()
        min_distance = ext / max(2 * np.sqrt(expected), 2) if expected else 10 * cell
    md = max(1, int(round(min_distance / cell)))
    # local maxima in a small window, then keep the highest ones that are at least
    # min_distance apart (a big max-filter window lets a tall neighbour's leaves hide a
    # shorter plant's top)
    img = np.where(occ, sm, np.nanmin(sm) - 1)
    cand = peak_local_max(img, min_distance=max(1, md // 4), labels=occ.astype(int), exclude_border=False)
    cand = cand[np.argsort(-img[cand[:, 0], cand[:, 1]])] if len(cand) else cand
    peaks = []
    for p in cand:
        if all(np.hypot(*(p - q)) >= md for q in peaks):
            peaks.append(p)
            if expected and len(peaks) >= expected:
                break
    markers = np.zeros(hm.shape, int)
    for k, (r, c) in enumerate(peaks, start=1):
        markers[r, c] = k
    if markers.max() == 0:
        return np.zeros(len(scan), int)
    lab_img = watershed(-sm, markers, mask=occ)
    # occupied islands that received no seed become their own instance
    islands, n_isl = ndi.label(occ & (lab_img == 0))
    if n_isl:
        lab_img = np.where(islands > 0, islands + lab_img.max(), lab_img)
    lab = lab_img[ij[:, 1], ij[:, 0]] - 1
    return _drop_small(lab, min_points)


def pot_grid_centres(rows: int, cols: int, pitch_x: float, pitch_y: float | None = None,
                     origin=(0.0, 0.0)) -> np.ndarray:
    pitch_y = pitch_x if pitch_y is None else pitch_y
    ox, oy = origin
    return np.array([[ox + c * pitch_x, oy + r * pitch_y] for r in range(rows) for c in range(cols)], float)


def auto_grid_origin(scan: Scan, rows: int, cols: int, pitch_x: float, pitch_y: float | None = None):
    """Centre a rows x cols grid on the canopy (the median of plant points)."""
    pitch_y = pitch_x if pitch_y is None else pitch_y
    c = np.median(scan.points[:, :2], axis=0)
    return (c[0] - (cols - 1) * pitch_x / 2, c[1] - (rows - 1) * pitch_y / 2)


def plants_pot_grid(scan: Scan, centres: np.ndarray, max_radius: float | None = None,
                    connectivity_fix: bool = True) -> np.ndarray:
    """Assign each point to its nearest pot centre (XY), then optionally move points whose
    connected 3D component mostly belongs to another pot (leaning heads crossing cells)."""
    centres = np.asarray(centres, float)
    d, lab = cKDTree(centres).query(scan.points[:, :2])
    if max_radius is not None:
        lab = np.where(d <= max_radius, lab, -1)
    lab = lab.astype(int)
    if connectivity_fix and len(scan) > 50:
        lab = _connectivity_fix(scan, lab)
    return lab


def _connectivity_fix(scan: Scan, lab: np.ndarray) -> np.ndarray:
    """Components that touch the ground region of one pot are given to that pot."""
    eps = 2.5 * median_spacing(scan.points)
    comp = np.asarray(scan.to_o3d().cluster_dbscan(eps=eps, min_points=3), int)
    z = scan.points[:, 2]
    zlow = np.quantile(z, 0.15)
    out = lab.copy()
    for c in np.unique(comp[comp >= 0]):
        m = comp == c
        base = m & (z <= zlow)
        ref = lab[base] if base.any() else lab[m]
        ref = ref[ref >= 0]
        if len(ref) == 0:
            continue
        owner = np.bincount(ref).argmax()
        share = np.mean(lab[m] == owner)
        # only overrule when the component is a single connected plant part mostly in one pot
        if base.any() and share > 0.5:
            out[m] = owner
    return out


def plants_dbscan(scan: Scan, eps: float | None = None, min_points: int = 50) -> np.ndarray:
    if eps is None:
        eps = 4 * median_spacing(scan.points)
    flat = scan.points.copy()
    flat[:, 2] = 0
    import open3d as o3d

    pc = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(flat))
    lab = np.asarray(pc.cluster_dbscan(eps=eps, min_points=5), int)
    return _drop_small(lab, min_points)


def _drop_small(lab: np.ndarray, min_points: int) -> np.ndarray:
    lab = lab.copy()
    valid = lab >= 0
    if not valid.any():
        return lab
    sizes = np.bincount(lab[valid])
    small = np.where(sizes < min_points)[0]
    lab[np.isin(lab, small)] = -1
    # relabel to 0..n-1 ordered by x then y of the centroid (reading order)
    ids = np.unique(lab[lab >= 0])
    return _relabel(lab, ids)


def _relabel(lab, ids):
    out = -np.ones_like(lab)
    for new, old in enumerate(ids):
        out[lab == old] = new
    return out


def order_labels_reading(scan: Scan, lab: np.ndarray, row_tol: float | None = None) -> np.ndarray:
    """Renumber instances in reading order (rows top to bottom by y, then left to right)."""
    ids = [i for i in np.unique(lab) if i >= 0]
    if not ids:
        return lab
    cents = np.array([scan.points[lab == i, :2].mean(0) for i in ids])
    if row_tol is None:
        row_tol = 0.5 * np.median(np.diff(np.sort(cents[:, 1]))[np.diff(np.sort(cents[:, 1])) > 0]) \
            if len(ids) > 1 else 1.0
        row_tol = max(row_tol, 1e-9)
    rows = np.round((cents[:, 1].max() - cents[:, 1]) / max(row_tol * 2, 1e-9))
    order = np.lexsort((cents[:, 0], rows))
    out = -np.ones_like(lab)
    for new, k in enumerate(order):
        out[lab == ids[k]] = new
    return out


# ----------------------------------------------------------------- leaves
def leaf_candidates_components(scan: Scan, eps: float | None = None, min_points: int = 30,
                               stem_radius: float | None = None) -> np.ndarray:
    """Connected components after removing a thin vertical core around the plant axis
    (so leaves joined only at the stem separate)."""
    pts = scan.points
    keep = np.ones(len(pts), bool)
    if stem_radius:
        base = pts[pts[:, 2] <= np.quantile(pts[:, 2], 0.05), :2].mean(0)
        keep = np.linalg.norm(pts[:, :2] - base, axis=1) > stem_radius
    if eps is None:
        eps = 2.5 * median_spacing(pts)
    import open3d as o3d

    pc = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(pts[keep]))
    sub = np.asarray(pc.cluster_dbscan(eps=eps, min_points=4), int)
    lab = -np.ones(len(pts), int)
    lab[keep] = sub
    return _drop_small(lab, min_points)


def leaf_candidates_region_growing(scan: Scan, angle_deg: float = 20.0, k: int = 15,
                                   curvature_quantile: float = 0.9, min_points: int = 30) -> np.ndarray:
    """Region growing on normals (Rabbani et al. 2006): seed from flattest points, add a
    neighbour when its normal is within ``angle_deg`` of the current point; continue growing
    only through points of low curvature."""
    s = scan
    s.ensure_normals()
    pts, nrm = s.points, s.normals
    tree = cKDTree(pts)
    _, nb = tree.query(pts, k=k + 1)
    nb = nb[:, 1:]
    # curvature = smallest eigenvalue / sum over the neighbourhood
    P = pts[nb] - pts[nb].mean(1, keepdims=True)
    C = np.einsum("nki,nkj->nij", P, P)
    ev = np.linalg.eigvalsh(C)
    curv = ev[:, 0] / (ev.sum(1) + 1e-12)
    cthr = np.quantile(curv, curvature_quantile)
    cos_t = np.cos(np.radians(angle_deg))
    lab = -np.ones(len(pts), int)
    cur = 0
    for seed in np.argsort(curv):
        if lab[seed] >= 0:
            continue
        lab[seed] = cur
        stack = [seed]
        while stack:
            i = stack.pop()
            for j in nb[i]:
                if lab[j] >= 0:
                    continue
                if abs(np.dot(nrm[i], nrm[j])) >= cos_t:
                    lab[j] = cur
                    if curv[j] < cthr:
                        stack.append(j)
        cur += 1
    return _drop_small(lab, min_points)


def organs_by_colour(scan: Scan, classes: dict[str, tuple[float, float]] | None = None) -> tuple[np.ndarray, list[str]]:
    """Label points by hue ranges (degrees). Default: green leaves vs yellow/straw organs
    (ripening heads, senesced leaves). Returns (labels, class names)."""
    if scan.colors is None:
        return np.zeros(len(scan), int), ["all"]
    if classes is None:
        classes = {"green": (70.0, 170.0), "yellow_straw": (25.0, 70.0)}
    hue = vegetation_indices(scan.colors)["hue"]
    lab = -np.ones(len(scan), int)
    names = list(classes)
    for k, (lo, hi) in enumerate(classes.values()):
        lab[(hue >= lo) & (hue < hi) & (lab < 0)] = k
    return lab, names
