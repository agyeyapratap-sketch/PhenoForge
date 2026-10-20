"""Wheat head (spike) and tiller counts.

3D heuristics (no training needed)
  * ``count_heads``   : candidate points by colour (straw / yellow hue window) and / or by
                        shape (upper-canopy points whose neighbourhood is volumetric rather
                        than planar like a leaf or linear like a stem), DBSCAN, then keep
                        clusters shaped like a spike: elongated (length / width 2-10), round
                        in cross-section, plausible size.
  * ``count_tillers`` : thin horizontal slices through a band just above the ground; stem
                        cross-sections are small round blobs in XY, leaves crossing the band
                        are long or flat and rejected; blobs that line up through most slices
                        are counted as tillers.

Both are HEURISTICS tuned on synthetic plants (``synthetic.make_wheat``). They assume a
cleaned, ground-aligned cloud (+Z up, ground at z ~ 0, scan.ground_z if set) of a single
plant. Validate against manual counts on a subset of your own scans before using them as
data; touching / overlapping heads, green heads with leaf-like colour, awns and tillers
bunched inside a common sheath all bias the counts (usually downwards).

2D detector (optional, ``pip install ultralytics``)
  * ``make_dataset_yaml`` / ``train_detector`` / ``detect_heads_images`` train and run a
    YOLO box detector on photos of heads annotated in YOLO format (e.g. with Label Studio,
    CVAT or Roboflow exports). All ultralytics calls go through ``_load_yolo`` /
    ``_boxes_from_result`` so tests can replace them.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from .clean import vegetation_indices
from .scan import Scan, cluster_eps, median_spacing

STRAW_HUE = (35.0, 65.0)   # degrees; ripening / ripe spikes. Green leaves are ~ 80-140.

# metric limits (metres); for non-metric scans they are scaled by plant height / REF_HEIGHT
REF_HEIGHT = 0.6
HEAD_LENGTH = (0.03, 0.15)
HEAD_WIDTH = (0.006, 0.03)
HEAD_ASPECT = (2.0, 10.0)
STEM_DIAMETER = (0.0012, 0.010)


# ------------------------------------------------------------------ helpers
def _ground_and_height(scan: Scan) -> tuple[float, float, np.ndarray]:
    """(ground z, plant height, height above ground per point)."""
    z = scan.points[:, 2]
    gz = float(scan.ground_z) if scan.ground_z is not None else float(np.quantile(z, 0.001))
    h = z - gz
    top = float(h.max()) if len(h) else 0.0
    plant = h > 0.02 * top
    H = float(np.quantile(h[plant], 0.998)) if plant.sum() > 10 else top
    return gz, max(H, 1e-9), h


def _unit(scan: Scan, H: float) -> float:
    """Multiplier for the metric limits: 1 for metric scans, else plant height / REF_HEIGHT."""
    return 1.0 if scan.metric else H / REF_HEIGHT


def _dbscan(points: np.ndarray, eps: float, min_points: int) -> np.ndarray:
    import open3d as o3d

    pc = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(np.asarray(points, float)))
    return np.asarray(pc.cluster_dbscan(eps=float(eps), min_points=int(min_points)), int)


def _eigen_features(points: np.ndarray, radius: float, k: int = 64) -> tuple[np.ndarray, np.ndarray]:
    """Neighbourhood PCA on a voxel subsample (voxel = radius / 4) mapped back to every point.

    Returns (scattering = l3 / l1, planarity = (l2 - l3) / l1) per point. Heads are volumetric
    at a ~1 cm scale (high scattering), leaves planar, stems linear.
    """
    voxel = radius / 4
    key = np.floor(points / voxel).astype(np.int64)
    _, rep, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1)
    sub = points[rep]
    d, idx = cKDTree(sub).query(sub, k=min(k, len(sub)), distance_upper_bound=radius)
    valid = np.isfinite(d)
    idx = np.where(valid, idx, 0)
    w = valid.astype(float)[..., None]
    nb = sub[idx]
    cnt = np.maximum(w.sum(1), 1)
    mu = (nb * w).sum(1) / cnt
    X = (nb - mu[:, None, :]) * w
    cov = np.einsum("nki,nkj->nij", X, X) / cnt[..., None]
    ev = np.linalg.eigvalsh(cov)[:, ::-1]           # l1 >= l2 >= l3
    l1 = np.maximum(ev[:, 0], 1e-18)
    scat = ev[:, 2] / l1
    plan = (ev[:, 1] - ev[:, 2]) / l1
    few = valid.sum(1) < 6
    scat[few] = 0.0
    return scat[inv], plan[inv]


def _shape(P: np.ndarray) -> dict:
    """PCA extents of a cluster: length (axis 1), width (axis 2), thickness (axis 3)."""
    c = P.mean(0)
    _, vec = np.linalg.eigh(np.cov((P - c).T))
    vec = vec[:, ::-1]
    proj = (P - c) @ vec
    ext = np.quantile(proj, 0.99, axis=0) - np.quantile(proj, 0.01, axis=0)
    return {"length": float(ext[0]), "width": float(ext[1]), "thickness": float(ext[2]),
            "axis": vec[:, 0], "centroid": c}


# ------------------------------------------------------------------ heads (3D)
def _head_ok(sh: dict, u: float) -> bool:
    L, W, T = sh["length"], sh["width"], sh["thickness"]
    aspect = L / max(W, 1e-12)
    return bool(HEAD_LENGTH[0] * u <= L <= HEAD_LENGTH[1] * u and HEAD_WIDTH[0] * u <= W <= HEAD_WIDTH[1] * u
                and HEAD_ASPECT[0] <= aspect <= HEAD_ASPECT[1] and T / max(W, 1e-12) > 0.55)


def _drop_debris(found, hs: np.ndarray, H: float, log):
    """Drop clusters whose top is low in the canopy or with < 20 % of the median head's points."""
    if not found:
        return found
    medN = np.median([len(g) for g, _ in found])
    keep = []
    for g, sh in found:
        top = float(np.quantile(hs[g], 0.99))
        if top < 0.6 * H or len(g) < 0.2 * medN:
            log(f"  rejected small / low cluster: n={len(g)} top={top:.4g}")
            continue
        keep.append((g, sh))
    return keep


def _split_cluster(P_all: np.ndarray, g: np.ndarray, eps: float, k: int, u: float, min_points: int):
    """Try to split touching heads: DBSCAN with a smaller radius, then k-means with k parts.
    Returns a list of (indices, shape) when every big part looks like a head, else []."""
    from scipy.cluster.vq import kmeans2

    P = P_all[g]
    trials = []
    for f in (0.6, 0.4):
        sub = _dbscan(P, eps * f, 8)
        trials.append([np.where(sub == c)[0] for c in np.unique(sub[sub >= 0])])
    for kk in sorted({k, 2}):
        _, lab = kmeans2(P, kk, minit="++", seed=0)
        trials.append([np.where(lab == c)[0] for c in range(kk)])
    for parts in trials:
        parts = [p for p in parts if len(p) >= max(min_points, 0.15 * len(g))]
        if len(parts) < 2:
            continue
        shapes = [_shape(P[p]) for p in parts]
        if all(_head_ok(s, u) for s in shapes):
            return [(g[p], s) for p, s in zip(parts, shapes)]
    return []


def count_heads(scan: Scan, method: str = "auto", hue_range: tuple[float, float] | None = None,
                min_points: int = 40, log=print) -> tuple[np.ndarray, list[dict], dict]:
    """Count wheat heads (spikes) in a single-plant cloud. HEURISTIC - validate on your data.

    method
      "colour" : candidates are upper-canopy points in the hue window (default straw/yellow
                 ``STRAW_HUE``; pass ``hue_range`` for e.g. green heads of a given cultivar).
      "shape"  : candidates are upper-canopy points with a volumetric neighbourhood (PCA
                 scattering), regardless of colour (green heads, no colour).
      "both"   : colour AND shape.
      "auto"   : colour if the scan has colours and that finds heads, else shape.
    Clusters (DBSCAN) are kept when elongated (length / width 2-10), round in cross-section
    (thickness / width > 0.55, rejects flat or curled yellow leaf tips) and of plausible size: length
    3-15 cm, width 0.6-3 cm on metric scans, scaled by plant height / 0.6 m otherwise.

    Returns (labels per point, -1 = not a head; rows per head; summary). Lengths are in scan
    units. Touching heads merge into one wide cluster that is rejected, so dense canopies
    undercount; awns inflate width.
    """
    n = len(scan)
    labels = -np.ones(n, int)
    gz, H, h = _ground_and_height(scan)
    u = _unit(scan, H)
    pts = scan.points
    upper = h > 0.5 * H
    has_col = scan.colors is not None
    if method == "auto":
        if has_col:
            lab, rows, summ = count_heads(scan, "colour", hue_range, min_points, log)
            if summ["head_count"] > 0:
                summ["method"] = "auto:colour"
                return lab, rows, summ
            log("count_heads: no straw-coloured heads found; falling back to shape")
        lab, rows, summ = count_heads(scan, "shape", hue_range, min_points, log)
        summ["method"] = "auto:shape"
        return lab, rows, summ
    if method not in ("colour", "color", "shape", "both"):
        raise ValueError(f"unknown method {method!r}")

    cand = upper.copy()
    if method in ("colour", "color", "both"):
        if not has_col:
            raise ValueError("colour method needs a scan with colours")
        lo, hi = hue_range or STRAW_HUE
        idx = vegetation_indices(scan.colors)
        sat = scan.colors.max(1) - scan.colors.min(1)
        cand &= (idx["hue"] >= lo) & (idx["hue"] <= hi) & (sat > 0.12)
    if method in ("shape", "both"):
        sel = np.where(cand)[0]
        if len(sel) > 10:
            scat, _ = _eigen_features(pts[sel], radius=0.012 * u)
            m = np.zeros(n, bool)
            m[sel] = scat > 0.06
            cand &= m
        else:
            cand[:] = False
    sel = np.where(cand)[0]
    log(f"count_heads[{method}]: {len(sel)} candidate points above {0.5 * H:.4g}")
    rows: list[dict] = []
    found: list[tuple[np.ndarray, dict]] = []   # (indices into sel, shape)
    if len(sel) >= min_points:
        P_all = pts[sel]
        sp = median_spacing(P_all)
        eps = min(max(cluster_eps(P_all, 10), 2.5 * sp), 0.008 * u)
        cl = _dbscan(P_all, eps, 8)
        groups = [np.where(cl == c)[0] for c in np.unique(cl[cl >= 0])]
        rejected = []
        for g in groups:
            if len(g) < min_points:
                continue
            sh = _shape(P_all[g])
            if _head_ok(sh, u):
                found.append((g, sh))
            else:
                rejected.append(g)
                log(f"  rejected cluster: n={len(g)} L={sh['length']:.4g} W={sh['width']:.4g} T={sh['thickness']:.4g}")
        # heads sit in the upper canopy and are point-rich compared with leaf debris
        found = _drop_debris(found, h[sel], H, log)
        # touching heads merge: split clusters much longer / wider and bigger than the typical
        # head, and rejected clusters big enough for two heads
        if found:
            ref = np.median if len(found) >= 3 else np.min
            medL = ref([s["length"] for _, s in found])
            medW = ref([s["width"] for _, s in found])
            medN = ref([len(g) for g, _ in found])
            out = []
            for g, sh in found:
                if (sh["length"] > 1.6 * medL or sh["width"] > 1.6 * medW) and len(g) > 1.5 * medN:
                    parts = _split_cluster(P_all, g, eps, max(2, int(round(len(g) / medN))), u, min_points)
                    if parts:
                        log(f"  split a merged cluster (n={len(g)}) into {len(parts)} heads")
                        out += parts
                        continue
                out.append((g, sh))
            for g in rejected:
                if len(g) >= 1.7 * medN:
                    parts = _split_cluster(P_all, g, eps, max(2, int(round(len(g) / medN))), u, min_points)
                    if parts:
                        log(f"  split a rejected cluster (n={len(g)}) into {len(parts)} heads")
                        out += parts
            found = _drop_debris(out, h[sel], H, log)
    for g, sh in found:
        idx_pts = sel[g]
        L, W, T = sh["length"], sh["width"], sh["thickness"]
        hid = len(rows)
        labels[idx_pts] = hid
        col = scan.colors[idx_pts].mean(0) if has_col else np.full(3, np.nan)
        ax = sh["axis"] * np.sign(sh["axis"][2] or 1)
        rows.append({
            "head_id": hid, "length": L, "width": W, "thickness": T, "aspect": L / max(W, 1e-12),
            "top_height": float(np.quantile(h[idx_pts], 0.99)),
            "centroid_x": float(sh["centroid"][0]), "centroid_y": float(sh["centroid"][1]),
            "centroid_z": float(sh["centroid"][2]),
            "tilt_deg": float(np.degrees(np.arccos(np.clip(ax[2], -1, 1)))),
            "n_points": int(len(idx_pts)),
            "mean_r": float(col[0]), "mean_g": float(col[1]), "mean_b": float(col[2]),
        })
    Ls = np.array([r["length"] for r in rows]) if rows else np.zeros(0)
    Ws = np.array([r["width"] for r in rows]) if rows else np.zeros(0)
    summ = {
        "head_count": len(rows),
        "head_length_mean": float(Ls.mean()) if len(Ls) else float("nan"),
        "head_length_sd": float(Ls.std()) if len(Ls) else float("nan"),
        "head_width_mean": float(Ws.mean()) if len(Ws) else float("nan"),
        "head_top_height_mean": float(np.mean([r["top_height"] for r in rows])) if rows else float("nan"),
        "plant_height": H, "metric": bool(scan.metric), "method": method, "heuristic": True,
    }
    log(f"count_heads[{method}]: {len(rows)} head(s)")
    return labels, rows, summ


# ------------------------------------------------------------------ tillers (3D)
def _fit_circle(Q: np.ndarray) -> tuple[np.ndarray, float, float]:
    """Algebraic (Kasa) circle fit; returns (centre, radius, RMS radial residual)."""
    A = np.column_stack([2 * Q, np.ones(len(Q))])
    sol, *_ = np.linalg.lstsq(A, (Q ** 2).sum(1), rcond=None)
    c = sol[:2]
    r = float(np.sqrt(max(sol[2] + c @ c, 1e-18)))
    res = float(np.sqrt(np.mean((np.linalg.norm(Q - c, axis=1) - r) ** 2)))
    return c, r, res


def _slice_stems(pts: np.ndarray, eps: float, dia: tuple[float, float], min_points: int = 8):
    """Stem cross-sections in one thin slice of 3D points: round XY blobs of plausible diameter.

    Each blob is first de-leaned (x and y regressed on z and the trend removed) so a leaning
    stem collapses to a ring, while a steep leaf collapses to a flat line across its width.
    """
    if len(pts) < min_points:
        return np.zeros((0, 2)), []
    P = pts.copy()
    P[:, 2] = 0
    cl = _dbscan(P, eps, 4)
    centres, dias = [], []
    for c in np.unique(cl[cl >= 0]):
        R = pts[cl == c]
        if len(R) < min_points:
            continue
        dz = R[:, 2] - R[:, 2].mean()
        var = float(dz @ dz)
        slope = (dz @ (R[:, :2] - R[:, :2].mean(0))) / var if var > 0 else np.zeros(2)
        Q = R[:, :2] - np.outer(dz, slope)
        ctr = Q.mean(0)
        _, vec = np.linalg.eigh(np.cov((Q - ctr).T))
        proj = (Q - ctr) @ vec[:, ::-1]
        ext = np.quantile(proj, 0.98, axis=0) - np.quantile(proj, 0.02, axis=0)
        major, minor = ext[0], max(ext[1], 1e-12)
        # leaves give long or (after de-leaning) flat traces; stems compact round blobs
        if not (major <= dia[1] and major / minor < 2.0):
            continue
        cc, r, res = _fit_circle(Q)
        if res < 0.3 * r and np.linalg.norm(cc - ctr) < 1.2 * r:   # clean ring / arc: use the fit
            d_est = 2 * r
        else:                                                       # noisy: blob extent minus noise
            cc, d_est = ctr, float(np.sqrt(major * minor)) * 0.85
        if dia[0] <= d_est <= dia[1]:
            centres.append(cc)
            dias.append(d_est)
    return np.array(centres).reshape(-1, 2), dias


def _track(C: np.ndarray, S: np.ndarray, link: float, max_gap: int = 2) -> list[list[int]]:
    """Link per-slice centres into vertical tracks: greedy nearest matching between a slice
    and the tracks seen in the previous ``max_gap`` slices, one centre per track per slice."""
    tracks: list[list[int]] = []
    for i in np.unique(S):
        idx = np.where(S == i)[0]
        live = [t for t in tracks if i - S[t[-1]] <= max_gap]
        pairs = sorted((float(np.linalg.norm(C[j] - C[t[-1]])), k, j)
                       for k, t in enumerate(live) for j in idx)
        used_t, used_c = set(), set()
        for d, k, j in pairs:
            if d > link * (i - S[live[k][-1]]) or k in used_t or j in used_c:
                continue
            live[k].append(int(j))
            used_t.add(k)
            used_c.add(j)
        tracks += [[int(j)] for j in idx if j not in used_c]
    return tracks


def count_tillers(scan: Scan, band: tuple[float, float] | None = None, log=print) -> tuple[dict, np.ndarray]:
    """Count tillers (stems) crossing a horizontal band above the ground. HEURISTIC.

    ``band`` = (z_low, z_high) height above ground in scan units (metres if metric). Default:
    two bands, 5-15 % and 15-25 % of plant height; a given band is paired with the band of the
    same width just above it. Each band is cut into ~1 cm slices; in each slice the XY points
    are clustered (DBSCAN), each blob is de-leaned, and compact round blobs of stem diameter
    (1.2-10 mm metric) are kept - leaves crossing the slice give long or flat traces. Blobs are
    then linked slice to slice into vertical tracks; a tiller is a track present in at least
    half of the slices (leaf crossings last one or two slices). The larger band count is
    reported, since leaves and sheaths hide stems more often than they fake one.

    Limits: needs stems resolved in the cloud (noise well below the stem radius, ~1 mm points);
    tillers still bunched in a common sheath at band height count as one; stems hidden on
    one side by occlusion give arcs (handled) but fully unseen stems are missed.

    Returns (summary, stem centres XY (mean over the band) of the counted tillers).
    """
    gz, H, h = _ground_and_height(scan)
    u = _unit(scan, H)
    pts = scan.points
    above = h > 0.01 * H
    sp = median_spacing(pts[above]) if above.sum() > 10 else median_spacing(pts)
    eps = max(2.5 * sp, 0.0012 * u)
    dia = (STEM_DIAMETER[0] * u, STEM_DIAMETER[1] * u)
    if band is None:
        bands = [(0.05 * H, 0.15 * H), (0.15 * H, 0.25 * H)]
    else:
        lo, hi = float(band[0]), float(band[1])
        bands = [(lo, hi), (hi, hi + (hi - lo))]
    link = 0.004 * u   # stems drift ~2 mm per 1 cm slice; neighbouring tillers are further apart
    results = []
    for lo, hi in bands:
        nsl = max(2, int(round((hi - lo) / (0.01 * u))))
        edges = np.linspace(lo, hi, nsl + 1)
        C, D, S = [], [], []
        for i, (a, b) in enumerate(zip(edges[:-1], edges[1:])):
            m = (h >= a) & (h < b)
            c, d = _slice_stems(pts[m], eps, dia)
            C.append(c)
            D += d
            S += [i] * len(c)
        C = np.vstack(C) if C else np.zeros((0, 2))
        D, S = np.asarray(D, float), np.asarray(S, int)
        chains = []
        for tr in _track(C, S, link):
            cover = len(tr) / nsl
            if cover >= 0.5:   # leaf crossings show up in a few slices only
                chains.append((C[tr].mean(0), float(np.median(D[tr])), cover))
        results.append({"band": (lo, hi), "count": len(chains), "chains": chains,
                        "slice_counts": np.bincount(S, minlength=nsl).tolist()})
        log(f"count_tillers: band {lo:.4g}-{hi:.4g}: per-slice stems {results[-1]['slice_counts']} -> "
            f"{len(chains)} continuous stem(s)")
    # leaves and sheaths hide stems in some bands, but rarely fake a continuous stem: take the max
    pick = max(results, key=lambda r: (r["count"], np.mean([c[2] for c in r["chains"]]) if r["chains"] else 0))
    ch = pick["chains"]
    summary = {
        "tiller_count": int(pick["count"]),
        "band_low": float(pick["band"][0]), "band_high": float(pick["band"][1]),
        "band_counts": [r["count"] for r in results],
        "band_coverage": float(np.mean([c[2] for c in ch])) if ch else 0.0,
        "stem_diameter_mean": float(np.mean([c[1] for c in ch])) if ch else float("nan"),
        "plant_height": H, "metric": bool(scan.metric), "heuristic": True,
    }
    centres = np.array([c[0] for c in ch], float).reshape(-1, 2)
    return summary, centres


# ------------------------------------------------------------------ 2D detector (optional)
def detector_available() -> tuple[bool, str]:
    try:
        import ultralytics  # noqa: F401
    except Exception:
        return False, "Head detector needs ultralytics: pip install ultralytics"
    return True, f"ultralytics {getattr(ultralytics, '__version__', '?')}"


def _load_yolo(model):
    """The only place ultralytics is imported for models (monkeypatched in tests)."""
    from ultralytics import YOLO

    return YOLO(str(model))


def _boxes_from_result(res) -> tuple[np.ndarray, np.ndarray]:
    """(xyxy boxes (n, 4), confidences (n,)) from one ultralytics result."""
    b = res.boxes

    def arr(x):
        x = x.cpu() if hasattr(x, "cpu") else x
        x = x.numpy() if hasattr(x, "numpy") else x
        return np.asarray(x, float)

    if b is None or len(b) == 0:
        return np.zeros((0, 4)), np.zeros(0)
    return arr(b.xyxy).reshape(-1, 4), arr(b.conf).reshape(-1)


def _require_detector():
    ok, msg = detector_available()
    if not ok:
        raise RuntimeError(msg)


def make_dataset_yaml(images_dir, labels_dir, out_yaml, names=("head",), val_fraction: float = 0.2,
                      seed: int = 0) -> Path:
    """Write a YOLO dataset yaml with a random train / val split of the images.

    Labels are YOLO txt files (``class cx cy w h`` normalised) named like the images. When
    ``labels_dir`` is not the ``labels`` sibling ultralytics expects (``.../images`` ->
    ``.../labels``), images and labels are copied into ``<yaml dir>/dataset/{images,labels}``.
    Images without a label file are kept as background (no heads) examples.
    """
    from .phenotype2d import IMG_EXT

    images_dir, labels_dir, out_yaml = Path(images_dir), Path(labels_dir), Path(out_yaml)
    imgs = sorted(p for p in images_dir.iterdir() if p.suffix.lower() in IMG_EXT)
    if not imgs:
        raise ValueError(f"no images in {images_dir}")
    out_yaml.parent.mkdir(parents=True, exist_ok=True)

    def expected_label(p: Path) -> Path:
        s = p.resolve().as_posix()
        i = s.rfind("/images/")
        return Path(s[:i] + "/labels/" + s[i + 8:]).with_suffix(".txt") if i >= 0 else Path("")

    if any(expected_label(p) != (labels_dir / (p.stem + ".txt")).resolve() for p in imgs):
        root = out_yaml.parent / "dataset"
        (root / "images").mkdir(parents=True, exist_ok=True)
        (root / "labels").mkdir(parents=True, exist_ok=True)
        new = []
        for p in imgs:
            q = root / "images" / p.name
            if not q.exists() or q.stat().st_size != p.stat().st_size:
                shutil.copy2(p, q)
            lab = labels_dir / (p.stem + ".txt")
            if lab.exists():
                shutil.copy2(lab, root / "labels" / lab.name)
            new.append(q)
        imgs = new
    n_lab = sum((labels_dir / (p.stem + ".txt")).exists() for p in imgs)
    order = np.random.default_rng(seed).permutation(len(imgs))
    n_val = int(round(val_fraction * len(imgs)))
    if len(imgs) >= 2:
        n_val = min(max(n_val, 1), len(imgs) - 1)
    val = [imgs[i] for i in order[:n_val]]
    train = [imgs[i] for i in order[n_val:]] or val
    base = out_yaml.with_suffix("")
    tr_txt, va_txt = Path(str(base) + "_train.txt"), Path(str(base) + "_val.txt")
    tr_txt.write_text("\n".join(p.resolve().as_posix() for p in train) + "\n", encoding="utf-8")
    va_txt.write_text("\n".join(p.resolve().as_posix() for p in (val or train)) + "\n", encoding="utf-8")

    def q(s: str) -> str:
        return "'" + s.replace("'", "''") + "'"

    lines = [f"path: {q(out_yaml.parent.resolve().as_posix())}", f"train: {q(tr_txt.resolve().as_posix())}",
             f"val: {q(va_txt.resolve().as_posix())}", "names:"]
    lines += [f"  {i}: {q(str(nm))}" for i, nm in enumerate(names)]
    out_yaml.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if n_lab < len(imgs):
        print(f"make_dataset_yaml: {len(imgs) - n_lab} image(s) have no label file (used as background)")
    return out_yaml


def train_detector(data_yaml, out_dir, epochs: int = 100, model: str = "yolov8n.pt", imgsz: int = 1024,
                   log=print) -> Path:
    """Fine-tune a YOLO detector on a YOLO dataset yaml; returns the path of best.pt."""
    _require_detector()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log(f"training {model} on {data_yaml} for {epochs} epochs (imgsz {imgsz}) -> {out_dir}")
    yolo = _load_yolo(model)
    yolo.train(data=str(data_yaml), epochs=int(epochs), imgsz=int(imgsz), project=str(out_dir),
               name="heads", exist_ok=True)
    trainer = getattr(yolo, "trainer", None)
    best = Path(getattr(trainer, "best", "") or out_dir / "heads" / "weights" / "best.pt")
    if not best.exists():
        raise FileNotFoundError(f"training finished but {best} was not written")
    log(f"best weights: {best}")
    return best


def detect_heads_images(images, weights, out_dir, conf: float = 0.25, log=print) -> list[dict]:
    """Run a trained head detector on photos (list of paths or a folder).

    Writes ``<stem>_heads.png`` (boxes drawn), ``heads.csv`` (one row per image) and
    ``head_boxes.csv`` (one row per box, pixels) to ``out_dir``. Returns per image
    {"image", "head_count", "boxes": [[x1, y1, x2, y2, conf], ...]}.
    """
    import cv2

    from .phenotype2d import IMG_EXT, read_image, write_csv, write_image

    _require_detector()
    if isinstance(images, (str, Path)) and Path(images).is_dir():
        images = sorted(p for p in Path(images).iterdir() if p.suffix.lower() in IMG_EXT)
    elif isinstance(images, (str, Path)):
        images = [images]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    yolo = _load_yolo(weights)
    results, rows, brows = [], [], []
    for f in map(Path, images):
        rgb = read_image(f)
        res = yolo.predict(source=rgb[:, :, ::-1].copy(), conf=float(conf), verbose=False)
        xyxy, cf = _boxes_from_result(res[0]) if len(res) else (np.zeros((0, 4)), np.zeros(0))
        keep = cf >= conf
        xyxy, cf = xyxy[keep], cf[keep]
        ann = np.ascontiguousarray(rgb.copy())
        t = max(2, int(round(max(rgb.shape[:2]) / 400)))
        for (x1, y1, x2, y2), c in zip(xyxy, cf):
            cv2.rectangle(ann, (int(x1), int(y1)), (int(x2), int(y2)), (255, 40, 40), t)
            cv2.putText(ann, f"{c:.2f}", (int(x1), max(int(y1) - 4, 10)), cv2.FONT_HERSHEY_SIMPLEX,
                        0.4 * t, (255, 40, 40), max(1, t // 2))
        cv2.putText(ann, f"heads: {len(cf)}", (10, 30 * t), cv2.FONT_HERSHEY_SIMPLEX, 0.6 * t, (255, 255, 0), t)
        write_image(out / f"{f.stem}_heads.png", ann)
        boxes = [[float(a), float(b), float(c), float(d), float(e)] for (a, b, c, d), e in zip(xyxy, cf)]
        results.append({"image": str(f), "head_count": len(boxes), "boxes": boxes})
        rows.append({"image": f.name, "head_count": len(boxes),
                     "mean_conf": float(cf.mean()) if len(cf) else float("nan")})
        for i, bx in enumerate(boxes):
            brows.append({"image": f.name, "box": i, "x1": bx[0], "y1": bx[1], "x2": bx[2], "y2": bx[3],
                          "conf": bx[4]})
        log(f"{f.name}: {len(boxes)} head(s)")
    write_csv(out / "heads.csv", rows)
    write_csv(out / "head_boxes.csv", brows)
    return results
