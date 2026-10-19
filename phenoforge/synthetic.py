"""Synthetic scans with known answers, for tests and the 'demo scan' button.

``make_tray`` builds a soil plane with ArUco markers printed on it and a grid of simple
plants (stem + strap leaves, optional wheat-like head), then applies an unknown scale and a
tilt so the full pipeline (ground alignment, ArUco scale, segmentation, traits) is exercised.
"""

from __future__ import annotations

import numpy as np

from .scan import Scan


def _leaf(rng, base, azimuth, length, width, rise, droop, density):
    """Strap leaf as a curved ribbon; returns points (n, 3) and its true one-sided area."""
    nu = max(10, int(length * density))
    nv = max(3, int(width * density))
    u = rng.random(nu * nv)
    v = rng.random(nu * nv) - 0.5
    w = width * (1 - u ** 2) * 0.9 + width * 0.1  # tapering
    s = u * length
    d = np.array([np.cos(azimuth), np.sin(azimuth), 0.0])
    side = np.array([-np.sin(azimuth), np.cos(azimuth), 0.0])
    x = base[0] + d[0] * s * 0.9 + side[0] * v * w
    y = base[1] + d[1] * s * 0.9 + side[1] * v * w
    z = base[2] + rise * s - droop * s ** 2 / length
    pts = np.column_stack([x, y, z])
    # true one-sided area: triangulate the same parametric surface finely
    U, Vv = np.meshgrid(np.linspace(0, 1, 200), np.linspace(-0.5, 0.5, 21), indexing="ij")
    Wd = width * (1 - U ** 2) * 0.9 + width * 0.1
    S = U * length
    X = d[0] * S * 0.9 + side[0] * Vv * Wd
    Y = d[1] * S * 0.9 + side[1] * Vv * Wd
    Z = rise * S - droop * S ** 2 / length
    G = np.stack([X, Y, Z], -1)
    a = np.cross(G[1:, :-1] - G[:-1, :-1], G[:-1, 1:] - G[:-1, :-1])
    b = np.cross(G[1:, 1:] - G[1:, :-1], G[:-1, 1:] - G[1:, :-1])
    area = 0.5 * (np.linalg.norm(a, axis=-1).sum() + np.linalg.norm(b, axis=-1).sum())
    return pts, float(area)


def make_plant(rng, centre, height=0.3, n_leaves=5, leaf_len=0.15, leaf_w=0.015, head=False, density=2500):
    pts, cols, areas = [], [], 0.0
    r = 0.003
    nz = int(2 * np.pi * r * height * density ** 2)  # same sampling density as the leaves
    t = rng.random(nz) * 2 * np.pi
    zz = rng.random(nz) * height
    pts.append(np.column_stack([centre[0] + r * np.cos(t), centre[1] + r * np.sin(t), zz]))
    cols.append(np.tile([0.30, 0.55, 0.20], (nz, 1)))
    for k in range(n_leaves):
        z0 = height * (0.15 + 0.6 * k / max(n_leaves - 1, 1))
        az = rng.random() * 2 * np.pi
        p, a = _leaf(rng, (centre[0], centre[1], z0), az, leaf_len, leaf_w, 0.8, 0.9, density)
        pts.append(p)
        cols.append(np.tile([0.20, 0.60, 0.15], (len(p), 1)) + rng.normal(0, 0.03, (len(p), 3)))
        areas += a
    if head:
        nh = int(0.08 * density * 4)
        hz = height + rng.random(nh) * 0.08
        ht = rng.random(nh) * 2 * np.pi
        pts.append(np.column_stack([centre[0] + 0.006 * np.cos(ht), centre[1] + 0.006 * np.sin(ht), hz]))
        cols.append(np.tile([0.80, 0.72, 0.40], (nh, 1)))
    P = np.vstack(pts)
    stem_area = 2 * np.pi * r * height
    return P, np.clip(np.vstack(cols), 0, 1), areas, P[:, 2].max(), stem_area


def marker_points(marker_id, centre, size, dictionary="DICT_4X4_50", px=1.0e-3, quiet=0.25):
    """Dense coloured points for a printed marker (with a white quiet zone) lying flat at z=0."""
    import cv2

    d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dictionary))
    img = cv2.aruco.generateImageMarker(d, int(marker_id), 120)
    full = size * (1 + 2 * quiet)
    n = int(full / px)
    g = (np.arange(n) + 0.5) * px - full / 2
    X, Y = np.meshgrid(g, g)
    # marker image coordinates: row 0 is +y (top)
    u = (X + size / 2) / size
    v = (size / 2 - Y) / size
    inside = (u >= 0) & (u < 1) & (v >= 0) & (v < 1)
    val = np.ones_like(X)
    iu = np.clip((u * 120).astype(int), 0, 119)
    iv = np.clip((v * 120).astype(int), 0, 119)
    val[inside] = img[iv[inside], iu[inside]] / 255.0
    P = np.column_stack([X.ravel() + centre[0], Y.ravel() + centre[1], np.zeros(X.size)])
    C = np.repeat(val.ravel()[:, None], 3, 1) * 0.9 + 0.05
    return P, C


def make_tray(rows=2, cols=3, pitch=0.25, marker_size=0.05, unknown_scale=3.7, tilt_deg=12.0,
              seed=0, head=False, noise=0.0005, soil_density=1.0e-3):
    """Returns (scan, truth dict). Truth is in metres in the un-scaled, un-tilted frame."""
    rng = np.random.default_rng(seed)
    W = cols * pitch + 0.2
    H = rows * pitch + 0.25
    n_soil = int(W * H / soil_density ** 2 * 0.6)
    soil = np.column_stack([(rng.random(n_soil) - 0.5) * W, (rng.random(n_soil) - 0.5) * H,
                            rng.normal(0, noise, n_soil)])
    soil_c = np.tile([0.36, 0.27, 0.20], (n_soil, 1)) + rng.normal(0, 0.03, (n_soil, 3))
    P, C = [soil], [soil_c]
    truth = {"plants": [], "marker_size": marker_size, "unknown_scale": unknown_scale}
    # markers along the front edge, away from the plants
    for k, mx in enumerate(np.linspace(-W / 2 + 0.07, W / 2 - 0.07, 3)):
        my = -H / 2 + 0.06
        mp, mc = marker_points(k, (mx, my), marker_size)
        # the printed sheet covers the soil beneath it
        half = marker_size * 1.5 / 2
        under = (np.abs(P[0][:, 0] - mx) < half) & (np.abs(P[0][:, 1] - my) < half)
        P[0], C[0] = P[0][~under], C[0][~under]
        P.append(mp + [0, 0, 0.0005])
        C.append(mc)
    for r in range(rows):
        for c in range(cols):
            cx = (c - (cols - 1) / 2) * pitch
            cy = (r - (rows - 1) / 2) * pitch + 0.03
            h = 0.22 + 0.1 * rng.random()
            pp, pc, area, top, stem = make_plant(rng, (cx, cy), height=h, head=head)
            P.append(pp)
            C.append(pc)
            truth["plants"].append({"centre": (cx, cy), "height": float(top), "leaf_area": float(area),
                                    "surface_area": float(area + stem)})
    P = np.vstack(P) + rng.normal(0, noise, (sum(len(p) for p in P), 3))
    C = np.clip(np.vstack(C), 0, 1)
    # unknown scale + tilt + offset, as from an unscaled photogrammetry reconstruction
    a = np.radians(tilt_deg)
    R = np.array([[1, 0, 0], [0, np.cos(a), -np.sin(a)], [0, np.sin(a), np.cos(a)]])
    P = (P @ R.T) / unknown_scale + np.array([0.3, -0.1, 1.2])
    s = Scan(points=P, colors=C, name="synthetic_tray")
    s.history.append("synthetic tray")
    return s, truth


def _tapered_tube(p0, p1, r0, r1, density, rng):
    """Surface points of a tapered tube (closed with end caps)."""
    d = np.asarray(p1, float) - np.asarray(p0, float)
    L = np.linalg.norm(d)
    u = d / L
    a = np.cross(u, [0, 0, 1.0]) if abs(u[2]) < 0.9 else np.cross(u, [1.0, 0, 0])
    a /= np.linalg.norm(a)
    b = np.cross(u, a)
    area = np.pi * (r0 + r1) * L
    n = max(50, int(area * density))
    t = rng.random(n)
    th = rng.random(n) * 2 * np.pi
    r = r0 + (r1 - r0) * t
    P = p0 + np.outer(t * L, u) + (r * np.cos(th))[:, None] * a + (r * np.sin(th))[:, None] * b
    caps = []
    for c, rr in ((p0, r0), (p1, r1)):
        m = max(10, int(np.pi * rr ** 2 * density))
        rad = rr * np.sqrt(rng.random(m))
        ph = rng.random(m) * 2 * np.pi
        caps.append(c + (rad * np.cos(ph))[:, None] * a + (rad * np.sin(ph))[:, None] * b)
    vol = np.pi * L / 3 * (r0 ** 2 + r0 * r1 + r1 ** 2)
    return np.vstack([P] + caps), vol, L


def make_root_crown(n_roots=6, seed=0, density=4.0e6, unknown_scale=1.0):
    """Cassava-like crown: a central core with tapered storage roots. Surface points only, as a
    scanner sees them, with the stem pointing +Z. Returns (scan, truth)."""
    rng = np.random.default_rng(seed)
    pts, truth_roots = [], []
    core, cvol, _ = _tapered_tube((0, 0, -0.08), (0, 0, 0.0), 0.035, 0.03, density, rng)
    stem, _, _ = _tapered_tube((0, 0, 0.0), (0, 0, 0.06), 0.012, 0.012, density, rng)
    pts += [core, stem]
    for k in range(n_roots):
        az = 2 * np.pi * k / n_roots + rng.normal(0, 0.1)
        ang = np.radians(35 + 30 * rng.random())          # from vertical
        L = 0.18 + 0.15 * rng.random()
        r0 = 0.022 + 0.01 * rng.random()
        start = np.array([0.03 * np.cos(az), 0.03 * np.sin(az), -0.04])
        d = np.array([np.sin(ang) * np.cos(az), np.sin(ang) * np.sin(az), -np.cos(ang)])
        P, vol, _ = _tapered_tube(start, start + L * d, r0, 0.004, density, rng)
        pts.append(P)
        truth_roots.append({"length": L, "angle_from_vertical": float(np.degrees(ang)), "volume": vol})
    P = np.vstack(pts)
    # truth crown volume by fine voxelisation of the union of the solids (below the stem)
    from scipy import ndimage as ndi

    v = 0.002
    lo = P.min(0) - v
    idx = np.floor((P - lo) / v).astype(int)
    occ = np.zeros(idx.max(0) + 3, bool)
    occ[tuple(idx.T)] = True
    occ = ndi.binary_fill_holes(ndi.binary_closing(occ, iterations=1))
    zc = lo[2] + (np.arange(occ.shape[2]) + 0.5) * v
    occ[:, :, zc > 0] = False
    C = np.clip(np.tile([0.55, 0.42, 0.30], (len(P), 1)) + rng.normal(0, 0.04, (len(P), 3)), 0, 1)
    s = Scan(points=P / unknown_scale, colors=C, name="synthetic_root_crown")
    truth = {"roots": truth_roots, "crown_volume_fine_voxel": float(occ.sum() * v ** 3), "n_roots": n_roots,
             "stem_length": 0.06}
    return s, truth


def make_fibrous_roots(seed=0, density=6.0e6):
    """Branched thin roots (primary + laterals), top at z = 0. Returns (scan, truth length)."""
    rng = np.random.default_rng(seed)
    pts, total = [], 0.0
    for k in range(4):  # 4 seminal roots
        az = 2 * np.pi * k / 4
        top = np.array([0.0, 0, 0])
        d = np.array([0.35 * np.cos(az), 0.35 * np.sin(az), -1.0])
        d /= np.linalg.norm(d)
        L = 0.30
        P, _, _ = _tapered_tube(top, top + L * d, 0.0012, 0.0008, density, rng)
        pts.append(P)
        total += L
        for j in range(4):  # laterals
            s0 = top + (0.05 + 0.06 * j) * d
            ld = np.cross(d, [0, 0, 1.0]) * (1 if j % 2 else -1)
            ld = ld / np.linalg.norm(ld) * 0.8 + np.array([0, 0, -0.6])
            ld /= np.linalg.norm(ld)
            ll = 0.05 + 0.04 * rng.random()
            P, _, _ = _tapered_tube(s0, s0 + ll * ld, 0.0007, 0.0005, density, rng)
            pts.append(P)
            total += ll
    s = Scan(points=np.vstack(pts), name="synthetic_fibrous_roots", metric=True)
    return s, {"total_length": total, "n_tips": 4 + 16}
