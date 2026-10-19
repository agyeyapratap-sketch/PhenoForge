"""Root phenotyping from Petri-dish / rhizotron photos and videos.

Pipeline: (video -> frames -> optional stitched panorama) -> root mask -> skeleton ->
skeleton graph -> traits: total length, primary root length (longest tip-to-tip path, or
from the top-most tip), number of tips and branch points, lateral count, convex hull
area, depth and width. Lengths are in px, and in mm when a scale is given.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy import ndimage as ndi

from .clean import otsu_threshold


def extract_frames(video_path, out_dir, every_n: int = 10, max_frames: int = 500) -> list[str]:
    import cv2

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video_path))
    paths, i = [], 0
    while len(paths) < max_frames:
        ok, frame = cap.read()
        if not ok:
            break
        if i % every_n == 0:
            p = out / f"frame_{i:06d}.png"
            cv2.imwrite(str(p), frame)
            paths.append(str(p))
        i += 1
    cap.release()
    return paths


def stitch(images: list[np.ndarray], mode: str = "scans") -> np.ndarray:
    """Stitch overlapping frames (RGB). 'scans' suits a camera sliding over a flat dish."""
    import cv2

    st = cv2.Stitcher_create(cv2.Stitcher_SCANS if mode == "scans" else cv2.Stitcher_PANORAMA)
    status, pano = st.stitch([cv2.cvtColor(i, cv2.COLOR_RGB2BGR) for i in images])
    if status != cv2.Stitcher_OK:
        raise RuntimeError(f"Stitching failed (OpenCV status {status}); add overlap or fewer frames")
    return cv2.cvtColor(pano, cv2.COLOR_BGR2RGB)


def root_mask(rgb: np.ndarray, roots_dark: bool | None = None, background_sigma: float = 25.0,
              threshold: float | None = None, min_area_px: int = 50, roi_circle: bool = False) -> np.ndarray:
    """Segment thin roots: flatten the background, then Otsu. ``roots_dark=None`` guesses
    (white roots on a dark/backlit background vs dark roots on paper)."""
    g = rgb.astype(np.float32).mean(2) if rgb.ndim == 3 else rgb.astype(np.float32)
    bg = ndi.gaussian_filter(g, background_sigma)
    d = g - bg
    if roots_dark is None:
        # roots are the minority class: the tail with more extreme values
        roots_dark = abs(np.quantile(d, 0.01)) > abs(np.quantile(d, 0.99))
    if roots_dark:
        d = -d
    thr = otsu_threshold(d[::2, ::2].ravel()) if threshold is None else threshold
    m = d > max(thr, 1e-3)
    if roi_circle:
        h, w = m.shape
        yy, xx = np.ogrid[:h, :w]
        m &= (yy - h / 2) ** 2 + (xx - w / 2) ** 2 <= (0.48 * min(h, w)) ** 2
    lab, n = ndi.label(m, structure=np.ones((3, 3)))
    if n:
        sizes = ndi.sum(m, lab, range(1, n + 1))
        m = np.isin(lab, np.where(sizes >= min_area_px)[0] + 1)
    return m


def skeleton_graph(mask: np.ndarray):
    """Skeletonise; return (skeleton, tips (N,2 rc), branch points (M,2 rc), sparse graph, node coords)."""
    from scipy.sparse import coo_matrix
    from skimage.morphology import skeletonize

    sk = skeletonize(mask)
    k = np.ones((3, 3), int)
    k[1, 1] = 0
    nb = ndi.convolve(sk.astype(int), k, mode="constant") * sk
    tips = np.argwhere((nb == 1))
    branches = np.argwhere((nb >= 3))
    coords = np.argwhere(sk)
    index = -np.ones(sk.shape, int)
    index[coords[:, 0], coords[:, 1]] = np.arange(len(coords))
    rows, cols, w = [], [], []
    for dr, dc, wt in ((0, 1, 1.0), (1, 0, 1.0), (1, 1, np.sqrt(2)), (1, -1, np.sqrt(2))):
        r2, c2 = coords[:, 0] + dr, coords[:, 1] + dc
        ok = (r2 >= 0) & (r2 < sk.shape[0]) & (c2 >= 0) & (c2 < sk.shape[1])
        j = np.full(len(coords), -1)
        j[ok] = index[r2[ok], c2[ok]]
        ok &= j >= 0
        rows.append(np.where(ok)[0])
        cols.append(j[ok])
        w.append(np.full(ok.sum(), wt))
    G = coo_matrix((np.concatenate(w), (np.concatenate(rows), np.concatenate(cols))),
                   shape=(len(coords), len(coords))).tocsr()
    G = G.maximum(G.T)
    return sk, tips, _merge_close(branches), G, coords, index


def _merge_close(pts: np.ndarray, r: float = 3.0) -> np.ndarray:
    if len(pts) == 0:
        return pts
    from scipy.spatial import cKDTree

    t = cKDTree(pts)
    groups = t.query_ball_point(pts, r)
    seen, out = set(), []
    for i, g in enumerate(groups):
        if i in seen:
            continue
        seen.update(g)
        out.append(pts[g].mean(0))
    return np.array(out)


def root_traits(mask: np.ndarray, mm_per_px: float | None = None, primary_from_top: bool = True) -> tuple[dict, dict]:
    """Returns (traits dict, drawing dict with skeleton/tips/branches/primary path)."""
    from scipy.sparse.csgraph import dijkstra

    sk, tips, branches, G, coords, index = skeleton_graph(mask)
    total_len = float(G.sum() / 2)
    out = {"total_length_px": total_len, "n_tips": int(len(tips)), "n_branch_points": int(len(branches)),
           "mask_area_px": int(mask.sum())}
    primary_path = np.zeros((0, 2), int)
    if len(tips) >= 2 and len(coords):
        tip_idx = index[tips[:, 0], tips[:, 1]]
        if primary_from_top:
            start = tip_idx[np.argmin(tips[:, 0])]  # hypocotyl end is usually at the top
            dist, pred = dijkstra(G, directed=False, indices=start, return_predecessors=True)
        else:
            dist0 = dijkstra(G, directed=False, indices=tip_idx[0])
            start = tip_idx[np.argmax(np.where(np.isfinite(dist0[tip_idx]), dist0[tip_idx], -1))]
            dist, pred = dijkstra(G, directed=False, indices=start, return_predecessors=True)
        dt = np.where(np.isfinite(dist[tip_idx]), dist[tip_idx], -1)
        end = tip_idx[np.argmax(dt)]
        out["primary_length_px"] = float(dist[end])
        path = [end]
        while path[-1] != start and pred[path[-1]] >= 0:
            path.append(pred[path[-1]])
        primary_path = coords[np.array(path)]
        # laterals: tips other than the two primary ends
        out["n_laterals"] = int(max(len(tips) - 2, 0))
        out["lateral_length_px"] = float(max(total_len - out["primary_length_px"], 0))
    else:
        out["primary_length_px"] = total_len
        out["n_laterals"] = 0
        out["lateral_length_px"] = 0.0
    if mask.any():
        ys, xs = np.nonzero(mask)
        out["depth_px"] = float(ys.max() - ys.min())
        out["width_px"] = float(xs.max() - xs.min())
        try:
            from scipy.spatial import ConvexHull

            out["hull_area_px"] = float(ConvexHull(np.column_stack([xs, ys])[:: max(1, len(xs) // 20000)]).volume)
        except Exception:
            out["hull_area_px"] = 0.0
    if mm_per_px:
        for k in list(out):
            if k.endswith("_length_px") or k in ("depth_px", "width_px"):
                out[k.replace("_px", "_mm")] = out[k] * mm_per_px
            if k.endswith("area_px"):
                out[k.replace("_px", "_mm2")] = out[k] * mm_per_px ** 2
        out["mm_per_px"] = mm_per_px
    draw = {"skeleton": sk, "tips": tips, "branches": branches, "primary": primary_path}
    return out, draw


def draw_overlay(rgb: np.ndarray, mask: np.ndarray, draw: dict) -> np.ndarray:
    import cv2

    ov = rgb.copy()
    ov[mask] = (0.5 * ov[mask] + 0.5 * np.array([0, 160, 255])).astype(np.uint8)
    ov[draw["skeleton"]] = (255, 255, 0)
    for r, c in draw["primary"]:
        ov[r, c] = (255, 0, 0)
    for r, c in draw["tips"]:
        cv2.circle(ov, (int(c), int(r)), 4, (0, 255, 0), -1)
    for r, c in draw["branches"]:
        cv2.circle(ov, (int(c), int(r)), 4, (255, 0, 255), 1)
    return ov


def track_tips(tips_prev: np.ndarray, tips_next: np.ndarray, max_move_px: float = 30.0) -> list[tuple[int, int, float]]:
    """Match root tips between consecutive frames (Hungarian assignment within a radius).
    Returns (index_prev, index_next, displacement_px) for each matched tip: growth per frame."""
    from scipy.optimize import linear_sum_assignment
    from scipy.spatial.distance import cdist

    if len(tips_prev) == 0 or len(tips_next) == 0:
        return []
    D = cdist(tips_prev, tips_next)
    D2 = np.where(D <= max_move_px, D, 1e9)
    r, c = linear_sum_assignment(D2)
    return [(int(i), int(j), float(D[i, j])) for i, j in zip(r, c) if D[i, j] <= max_move_px]
