"""AI leaf instances: multi-view SAM 2.1 segmentation back-projected onto the point cloud.

The cloud of one (cleaned, vegetation-only) plant is rendered from a top view and several
oblique views into RGB images with a z-buffer, keeping for every pixel the index of the
nearest point. A segment-anything model proposes masks on each image (automatic mask
generation, no prompts). Each mask maps back to the points it shows, and the per-view
segments are merged across views into leaf instances by majority co-association:

  1. Per view, masks hitting mostly background, too few points, or more than
     ``MAX_FRACTION`` of the visible plant (SAM's whole-plant mask) are dropped; the rest are
     painted large-to-small so the finest mask wins where masks overlap. That gives each
     visible point one segment id per view.
  2. Points with the same tuple of segment ids over all views form "atoms". For every pair
     of atoms, ``together`` = views where both are in the same segment, ``apart`` = views
     where both are segmented but differently; distance = apart / (together + apart).
  3. Average-linkage clustering cut below 0.5 merges atoms that most views keep together
     (one view that lumps two leaves cannot chain them, unlike union-find on mask overlap).
     Instances under ``min_points`` are dropped, then unlabelled points (hidden undersides,
     mask borders) take the label of the nearest labelled point within a few point spacings.

Like the geometric methods these are provisional *visible* leaf candidates.

Backends are optional and detected lazily: the ``ultralytics`` package (``SAM("sam2.1_b.pt")``
downloads the weights once to its cache, then runs offline) or Meta's ``sam2`` package
(``SAM2AutomaticMaskGenerator``). Any callable ``rgb (H, W, 3) uint8 -> list of bool masks``
can be passed as ``segmenter`` instead.
"""

from __future__ import annotations

import importlib.util
import time

import numpy as np
from scipy.spatial import cKDTree

from .scan import Scan, median_spacing
from .segment import _drop_small

INSTALL_HINT = "install with: pip install ultralytics  (downloads sam2.1_b.pt, ~160 MB, on first use)"
BACKGROUND = (255, 255, 255)   # plant pixels are clipped below this so the background is unique
DEFAULT_COLOUR = (0.25, 0.55, 0.2)
MARGIN = 0.04                  # fraction of the image left empty on each side
ELEVATION_DEG = 40.0           # oblique camera elevation above the horizontal
MAX_FRACTION = 0.6             # masks covering more of the visible plant are background-sized
MIN_HIT = 0.5                  # fraction of mask pixels that must show a point
MERGE_DIST = 0.499             # merge atoms kept together by a strict majority of views
UNOBSERVED_DIST = 0.6          # distance between atoms never segmented in the same view
ATOM_MIN = 3                   # atoms smaller than this are left to the nearest-neighbour fill
MAX_ATOMS = 2500               # cap on the pairwise atom matrix

_SEGMENTERS: dict = {}


# ------------------------------------------------------------------ backends
def _has(mod: str) -> bool:
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError):
        return False


def available() -> tuple[bool, str]:
    """(True, backend name) when a SAM backend can be imported, else (False, install hint)."""
    if _has("ultralytics") and _has("torch"):
        return True, "ultralytics SAM"
    if _has("sam2") and _has("torch"):
        return True, "Meta sam2"
    return False, INSTALL_HINT


def _ultralytics_segmenter(model_name: str):
    """Segment-everything with ultralytics SAM: calling the model without prompts runs its
    automatic mask generator. Returns fn(rgb) -> list of (H, W) bool masks."""
    from ultralytics import SAM

    model = SAM(model_name)

    def fn(rgb: np.ndarray) -> list[np.ndarray]:
        # ultralytics treats numpy images as BGR
        res = model(np.ascontiguousarray(rgb[..., ::-1]), verbose=False)
        if not res or res[0].masks is None:
            return []
        data = res[0].masks.data
        data = data.cpu().numpy() if hasattr(data, "cpu") else np.asarray(data)
        return [m > 0.5 for m in data]

    return fn


_SAM2_HF = {"t": "facebook/sam2.1-hiera-tiny", "s": "facebook/sam2.1-hiera-small",
            "b": "facebook/sam2.1-hiera-base-plus", "l": "facebook/sam2.1-hiera-large"}


def _sam2_segmenter(model_name: str):
    """Meta sam2 automatic mask generator (weights from the Hugging Face hub, cached)."""
    from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator

    key = model_name.replace(".pt", "").split("_")[-1][:1] if "/" not in model_name else ""
    gen = SAM2AutomaticMaskGenerator.from_pretrained(_SAM2_HF.get(key, model_name) if key else model_name)

    def fn(rgb: np.ndarray) -> list[np.ndarray]:
        return [np.asarray(m["segmentation"], bool) for m in gen.generate(np.ascontiguousarray(rgb))]

    return fn


def _default_segmenter(model: str):
    ok, name = available()
    if not ok:
        raise RuntimeError(f"No SAM backend for AI leaf instances; {name}")
    key = (name, model)
    if key not in _SEGMENTERS:
        _SEGMENTERS[key] = _ultralytics_segmenter(model) if name == "ultralytics SAM" else _sam2_segmenter(model)
    return _SEGMENTERS[key]


# ------------------------------------------------------------------ rendering
def _view_frames(n_views: int, elevation_deg: float = ELEVATION_DEG):
    """(name, forward, right, up) for a top view plus oblique views evenly around the plant."""
    frames = [("top", np.array([0.0, 0.0, -1.0]), np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0]))]
    k = max(int(n_views) - 1, 0)
    el = np.radians(elevation_deg)
    z = np.array([0.0, 0.0, 1.0])
    for i in range(k):
        az = 2 * np.pi * i / k
        f = -np.array([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)])
        u = np.cross(f, z)
        u /= np.linalg.norm(u)
        v = np.cross(u, f)
        frames.append((f"oblique_az{int(round(np.degrees(az))):03d}", f, u, v))
    return frames[:max(int(n_views), 1)]


def _splat(a, b, d, R, px, rs):
    """Z-buffered disc splats. Returns (index, depth) images of side R."""
    n = len(a)
    ci = np.floor(a).astype(np.int64)
    ri = np.floor(b).astype(np.int64)
    oy, ox = np.mgrid[-rs:rs + 1, -rs:rs + 1]
    disc = oy ** 2 + ox ** 2 <= rs * rs + 0.5
    oy, ox = oy[disc], ox[disc]
    rr = ri[:, None] + oy[None]
    cc = ci[:, None] + ox[None]
    # a point's own centre beats a neighbour's splat at nearly the same depth
    dd = d[:, None] + np.hypot(oy, ox)[None] * px * 0.5
    pid = np.broadcast_to(np.arange(n)[:, None], rr.shape)
    ok = (rr >= 0) & (rr < R) & (cc >= 0) & (cc < R)
    pix = (rr * R + cc)[ok]
    dd, pid = dd[ok], pid[ok]
    order = np.lexsort((dd, pix))
    ps = pix[order]
    first = np.r_[True, ps[1:] != ps[:-1]]
    sel = order[first]
    index = np.full(R * R, -1, np.int32)
    depth = np.full(R * R, np.inf)
    index[pix[sel]] = pid[sel]
    depth[pix[sel]] = dd[sel]
    return index.reshape(R, R), depth.reshape(R, R)


def render_views(scan: Scan, n_views: int = 6, image_size: int = 1024) -> list[dict]:
    """Orthographic renders of the cloud: a top view plus ``n_views - 1`` oblique views.

    Each item is {"rgb": (S, S, 3) uint8, "index": (S, S) int32 point index (-1 = empty),
    "name": str, "pixel_size": scan units per pixel, "forward": view direction}. Points are
    splatted as small discs and shaded by depth, with dark lines where a nearer surface
    occludes a farther one, so overlapping leaves stay distinguishable. The background is
    pure ``BACKGROUND`` (white)."""
    pts = np.asarray(scan.points, float)
    if len(pts) == 0:
        return []
    S = int(image_size)
    spacing = median_spacing(pts)
    cols = np.asarray(scan.colors, float) if scan.colors is not None else np.tile(DEFAULT_COLOUR, (len(pts), 1))
    P = pts - (pts.min(0) + pts.max(0)) / 2
    out = []
    for name, f, u, v in _view_frames(n_views):
        a, b, d = P @ u, P @ v, P @ f
        ext = max(np.ptp(a), np.ptp(b), 1e-9)
        # render no finer than half the point spacing, then upsample: fills the image cheaply
        px = max(ext / (S * (1 - 2 * MARGIN)), spacing / 2.0)
        R = int(np.clip(np.ceil(ext / px / (1 - 2 * MARGIN)) + 1, 8, S))
        px = max(px, ext / (R * (1 - 2 * MARGIN)))
        ac = (a - (a.min() + a.max()) / 2) / px + R / 2
        bc = R / 2 - (b - (b.min() + b.max()) / 2) / px
        rs = int(np.clip(np.ceil(0.75 * spacing / px), 1, 4))
        index, depth = _splat(ac, bc, d, R, px, rs)
        filled = index >= 0
        img = np.zeros((R, R, 3))
        if filled.any():
            dz = depth[filled]
            dn = (dz - dz.min()) / max(np.ptp(dz), 1e-12)
            img[filled] = cols[index[filled]] * (1.0 - 0.35 * dn)[:, None]
            # occlusion edges: darken pixels lying just behind a nearer neighbour
            thr = 4 * spacing
            edge = np.zeros((R, R), bool)
            D = np.where(filled, depth, np.inf)
            for sl_a, sl_b in (((slice(1, None), slice(None)), (slice(None, -1), slice(None))),
                               ((slice(None, -1), slice(None)), (slice(1, None), slice(None))),
                               ((slice(None), slice(1, None)), (slice(None), slice(None, -1))),
                               ((slice(None), slice(None, -1)), (slice(None), slice(1, None)))):
                edge[sl_a] |= filled[sl_a] & (D[sl_b] < D[sl_a] - thr)
            img[edge] *= 0.45
        rgb = (np.clip(img, 0, 250 / 255) * 255).astype(np.uint8)
        rgb[~filled] = BACKGROUND
        if R != S:  # nearest-neighbour upsample keeps index and colours consistent
            m = (np.arange(S) * R) // S
            rgb = rgb[m][:, m]
            index = index[m][:, m]
        out.append({"rgb": np.ascontiguousarray(rgb), "index": np.ascontiguousarray(index, np.int32),
                    "name": name, "pixel_size": float(px * R / S), "forward": f})
    return out


# ------------------------------------------------------------------ merging
def _fit_mask(m: np.ndarray, shape) -> np.ndarray:
    m = np.asarray(m).astype(bool)
    if m.ndim == 3:
        m = m[..., 0]
    if m.shape != tuple(shape):
        r = (np.arange(shape[0]) * m.shape[0]) // shape[0]
        c = (np.arange(shape[1]) * m.shape[1]) // shape[1]
        m = m[r][:, c]
    return m


def view_segments(view: dict, masks, n_points: int, min_mask_points: int = 10) -> np.ndarray:
    """(N,) segment id per point for one view (-1 = not visible or not in a kept mask)."""
    idx = view["index"]
    vis = idx >= 0
    seg = np.full(n_points, -1, np.int32)
    if not vis.any():
        return seg
    n_vis = len(np.unique(idx[vis]))
    kept = []
    for m in masks:
        m = _fit_mask(m, idx.shape)
        area = int(m.sum())
        if area == 0:
            continue
        hit = idx[m]
        hit = hit[hit >= 0]
        if len(hit) < MIN_HIT * area:
            continue                      # mostly background
        k = len(np.unique(hit))
        if k < min_mask_points or k > MAX_FRACTION * n_vis:
            continue                      # speck, or the whole plant
        kept.append((area, m))
    kept.sort(key=lambda t: -t[0])         # paint large first: finest mask wins on overlap
    lab = np.full(idx.shape, -1, np.int32)
    for j, (_, m) in enumerate(kept):
        lab[m] = j
    ok = vis & (lab >= 0)
    seg[idx[ok]] = lab[ok]
    return seg


def merge_segments(S: np.ndarray) -> np.ndarray:
    """Merge per-view segment ids (N, V) into instance ids (N,) by majority co-association
    of atoms (points sharing one id tuple) with average-linkage clustering."""
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform

    n = len(S)
    lab = -np.ones(n, np.int64)
    rows = np.where((S >= 0).any(1))[0]
    if len(rows) == 0:
        return lab
    atoms, inv, cnt = np.unique(S[rows], axis=0, return_inverse=True, return_counts=True)
    inv = np.asarray(inv).ravel()
    keep = np.where(cnt >= ATOM_MIN)[0]
    if len(keep) > MAX_ATOMS:
        keep = keep[np.argsort(-cnt[keep])[:MAX_ATOMS]]
    if len(keep) == 0:
        return lab
    A = atoms[keep]
    if len(A) == 1:
        cl = np.zeros(1, int)
    else:
        together = np.zeros((len(A), len(A)), np.int16)
        apart = np.zeros_like(together)
        for v in range(A.shape[1]):
            a = A[:, v]
            obs = a >= 0
            both = obs[:, None] & obs[None]
            same = a[:, None] == a[None]
            together += both & same
            apart += both & ~same
        tot = together + apart
        D = np.where(tot > 0, apart / np.maximum(tot, 1), UNOBSERVED_DIST)
        np.fill_diagonal(D, 0.0)
        Z = linkage(squareform(D, checks=False), "average")
        cl = fcluster(Z, t=MERGE_DIST, criterion="distance") - 1
    atom_lab = -np.ones(len(atoms), np.int64)
    atom_lab[keep] = cl
    lab[rows] = atom_lab[inv]
    return lab


def fill_unlabelled(points: np.ndarray, labels: np.ndarray, radius: float) -> np.ndarray:
    """Give unlabelled points the label of the nearest labelled point within ``radius``."""
    lab = labels.copy()
    known = lab >= 0
    if radius <= 0 or not known.any() or known.all():
        return lab
    tree = cKDTree(points[known])
    d, j = tree.query(points[~known], k=1, distance_upper_bound=radius)
    hit = np.isfinite(d)
    src = lab[known]
    tgt = np.where(~known)[0]
    lab[tgt[hit]] = src[j[hit]]
    return lab


def segment_leaves(scan: Scan, model: str = "sam2.1_b.pt", n_views: int = 6, image_size: int = 1024,
                   min_points: int = 30, segmenter=None, log=print,
                   fill_radius: float | None = None, min_fraction: float = 0.01) -> np.ndarray:
    """Leaf instance labels (N,) for one plant, -1 = none.

    segmenter : callable rgb (H, W, 3) uint8 -> list of bool masks; None uses the best
                installed SAM backend (``model`` names its weights) or raises RuntimeError
                with the install hint.
    fill_radius : unlabelled points within this distance of a labelled one join it
                (default 3 x the median point spacing; 0 disables).
    min_fraction : instances smaller than this fraction of the segmented points are also
                dropped (e.g. stem slivers that each view cuts in a different place).
    Labels are 0..k-1, compatible with ``traits.component_traits(scan, labels)``."""
    log = log or (lambda *a, **k: None)
    if segmenter is None:
        segmenter = _default_segmenter(model)
    n = len(scan)
    if n < max(min_points, 4):
        return -np.ones(n, np.int64)
    t0 = time.time()
    views = render_views(scan, n_views=n_views, image_size=image_size)
    min_mask = max(5, min_points // 3)
    S = np.full((n, len(views)), -1, np.int32)
    for v, view in enumerate(views):
        masks = list(segmenter(view["rgb"]) or [])
        S[:, v] = view_segments(view, masks, n, min_mask_points=min_mask)
        log(f"leafsam: {view['name']}: {len(masks)} masks, {len(np.unique(S[S[:, v] >= 0, v]))} kept")
    lab = merge_segments(S)
    lab = _drop_small(lab, max(min_points, int(min_fraction * np.sum(lab >= 0))))
    if fill_radius is None:
        fill_radius = 3.0 * median_spacing(scan.points)
    lab = fill_unlabelled(scan.points, lab, fill_radius)
    k = int(lab.max()) + 1 if (lab >= 0).any() else 0
    log(f"leafsam: {k} leaf instance(s), {np.mean(lab >= 0) * 100:.0f}% of points labelled "
        f"({time.time() - t0:.1f} s, {len(views)} views)")
    return lab
