"""3D root phenotyping.

Two modes share one voxel pipeline (scan -> solid voxel model -> traits):

Root crown mode (storage / tuberous roots, after Sunvittayakul et al. 2022, Sci Rep 12:10030,
"Cassava root crown phenotyping using three-dimension (3D) multi-view stereo reconstruction")
  The paper photographs an excavated crown (~25-40 photos on a green sheet with a reference
  box), reconstructs it in Agisoft, then in Blender closes holes with a voxel remesh (octree
  depth 8), rescales from the reference object, removes the stem, splits the crown in half to
  reduce volume bias, and measures crown volume, crown surface, root number, root angle, crown
  diameter, root length, cylinder soil volume and compactness. Root density and the
  surface-to-volume ratio are derived from the weight.
  Here the same steps are automatic and open: COLMAP or any phone scanner for reconstruction,
  ArUco or two-point scaling (or a reference box of known size), green-sheet removal, a
  stem cut, a voxel remesh (closing + hole filling + marching cubes) optionally per sector
  (the "split in half"), and individual roots from 3D connected components after removing the
  crown core.

Fibrous root system mode (cereal roots, washed root systems, X-ray CT / MRI volumes)
  The solid is skeletonised in 3D: total root length, number of tips and branch points,
  maximum depth and width, convex hull volume, root length per depth layer, and the
  primary (longest) path. CT volumes load from TIFF stacks.

Everything is in metres once the scan is metric (cm and cm^3 columns are added for reports).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy import ndimage as ndi

from .scan import Scan, median_spacing


# --------------------------------------------------------------------- orientation
def orient(scan: Scan, axis="z", stem_point=None, base_point=None) -> Scan:
    """Return a copy with the crown/root axis along +Z (stem at the top, roots going down) and
    the stem point at the origin. ``axis`` may be 'z', '-z', 'x', '-x', 'y', '-y', 'pca'
    (longest principal axis) or a 3-vector pointing from the roots towards the stem. Two picked
    points (stem top, crown bottom) override it."""
    from .clean import _rotation_from_to

    s = scan.copy()
    P = s.points
    if stem_point is not None and base_point is not None:
        up = np.asarray(stem_point, float) - np.asarray(base_point, float)
    elif isinstance(axis, str):
        if axis == "pca":
            c = P - P.mean(0)
            _, vecs = np.linalg.eigh(np.cov(c[:: max(1, len(c) // 50000)].T))
            up = vecs[:, -1]
        else:
            sign = -1.0 if axis.startswith("-") else 1.0
            up = sign * np.eye(3)["xyz".index(axis[-1])]
    else:
        up = np.asarray(axis, float)
    R = _rotation_from_to(up / np.linalg.norm(up), np.array([0.0, 0, 1]))
    T = np.eye(4)
    T[:3, :3] = R
    s.transform(T)
    # origin: on the axis through the stem (or the top-centre of the object)
    if stem_point is not None:
        top = R @ np.asarray(stem_point, float)
    else:
        z = s.points[:, 2]
        top_pts = s.points[z >= np.quantile(z, 0.98)]
        top = np.array([*top_pts[:, :2].mean(0), z.max()])
    s.points = s.points - top
    if s.mesh_vertices is not None:
        s.mesh_vertices = s.mesh_vertices - top
    s.ground_z = None
    s.history.append(f"oriented root axis to +Z (up = {np.round(up / np.linalg.norm(up), 3).tolist()})")
    return s


def remove_background(scan: Scan, green_sheet: bool = True, plane: bool = True) -> Scan:
    """Drop the photo background: a green sheet (high ExG) and/or the dominant plane."""
    from .clean import fit_ground_plane, vegetation_indices

    s = scan
    if green_sheet and s.colors is not None:
        exg = vegetation_indices(s.colors)["exg"]
        s = s.subset(exg < 0.12, "removed green background")
    if plane and len(s) > 1000:
        pl, inl = fit_ground_plane(s, prefer_low=False)
        if inl.mean() > 0.15:  # only if a large flat background really exists
            s = s.subset(~inl, f"removed background plane ({inl.sum()} points)")
    return s


def cut_stem(scan: Scan, length: float) -> Scan:
    """Remove the top ``length`` (scan units) along +Z, i.e. the stem stub above the crown."""
    return scan.subset(scan.points[:, 2] <= -length, f"removed stem: top {length:g}")


# ---------------------------------------------------------------------- voxel model
@dataclass
class Solid:
    occ: np.ndarray        # bool (nx, ny, nz)
    origin: np.ndarray     # world coordinate of voxel (0, 0, 0) centre
    voxel: float

    def centres(self, mask=None) -> np.ndarray:
        idx = np.argwhere(self.occ if mask is None else mask)
        return self.origin + idx * self.voxel

    @property
    def volume(self) -> float:
        return float(self.occ.sum() * self.voxel ** 3)


def voxelize(points: np.ndarray, voxel: float, pad: int = 3) -> Solid:
    lo = points.min(0) - pad * voxel
    idx = np.floor((points - lo) / voxel).astype(int)
    shape = idx.max(0) + pad + 1
    occ = np.zeros(shape, bool)
    occ[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    return Solid(occ, lo + voxel / 2, voxel)


def solidify(solid: Solid, close_iter: int = 2, fill: bool = True) -> Solid:
    """Close small gaps in the scanned surface and fill the interior: a voxel 'remesh'.
    Surfaces from photogrammetry and LiDAR are shells, so the inside has to be filled before
    a volume means anything."""
    st = ndi.generate_binary_structure(3, 1)
    occ = ndi.binary_closing(solid.occ, st, iterations=close_iter) | solid.occ if close_iter else solid.occ.copy()
    if fill:
        occ = ndi.binary_fill_holes(occ)
        # also fill cavities that open to one side by filling slice-wise along each axis
        for ax in range(3):
            occ |= _fill_slices(occ, ax)
    return Solid(occ, solid.origin, solid.voxel)


def _fill_slices(occ, ax):
    out = np.zeros_like(occ)
    for i in range(occ.shape[ax]):
        sl = [slice(None)] * 3
        sl[ax] = i
        out[tuple(sl)] = ndi.binary_fill_holes(occ[tuple(sl)])
    return out


def marching_cubes_area(solid: Solid) -> tuple[float, np.ndarray, np.ndarray]:
    from skimage.measure import marching_cubes, mesh_surface_area

    vol = np.pad(solid.occ.astype(np.float32), 1)
    vol = ndi.gaussian_filter(vol, 0.7)  # smooth the staircase so the area is not inflated
    V, F, _, _ = marching_cubes(vol, 0.5, spacing=(solid.voxel,) * 3)
    V = V + solid.origin - solid.voxel
    return float(mesh_surface_area(V, F)), V, F


def auto_voxel(points: np.ndarray, depth: int = 8) -> float:
    """Voxel size like Blender's remesh octree depth: extent / 2^depth, not finer than the
    point spacing allows."""
    ext = float(np.ptp(points, axis=0).max())
    return max(ext / 2 ** depth, 1.5 * median_spacing(points))


# ---------------------------------------------------------------- crown traits
@dataclass
class CrownOptions:
    voxel: float = 0.0           # 0 = auto from depth
    depth: int = 8               # octree-depth equivalent for the auto voxel
    close_iter: int = 2
    sectors: int = 1             # 1 = whole crown; 2 = split in half (as in the paper; see README)
    core_radius: float = 0.0     # 0 = auto (crown core = central cylinder)
    min_root_fraction: float = 0.01  # roots smaller than this share of crown volume are ignored
    weight_kg: float = 0.0       # fresh root weight, for root density


def crown_traits(scan: Scan, opt: CrownOptions | None = None, log=print) -> tuple[dict, dict]:
    """Traits of an oriented (stem at origin, roots below, +Z up) and stem-cut root crown.
    Returns (traits, extra) where extra holds the voxel solid, root labels and mesh."""
    opt = opt or CrownOptions()
    P = scan.points
    v = opt.voxel or auto_voxel(P, opt.depth)
    out: dict = {"voxel_size": v, "n_points": len(P)}

    # volume: optionally per sector around the axis, each closed and filled on its own
    ang = np.arctan2(P[:, 1], P[:, 0])
    vols, solids = [], []
    for k in range(max(1, opt.sectors)):
        if opt.sectors > 1:
            a0 = -np.pi + 2 * np.pi * k / opt.sectors
            m = (ang >= a0) & (ang < a0 + 2 * np.pi / opt.sectors)
        else:
            m = np.ones(len(P), bool)
        if m.sum() < 10:
            continue
        sol = solidify(voxelize(P[m], v), opt.close_iter)
        vols.append(sol.volume)
        solids.append(sol)
    out["crown_volume_m3"] = float(sum(vols))
    whole = solidify(voxelize(P, v), opt.close_iter)
    out["crown_volume_whole_m3"] = whole.volume
    area, MV, MF = marching_cubes_area(whole)
    out["crown_surface_m2"] = area
    out["surface_to_volume_per_m"] = area / out["crown_volume_m3"] if out["crown_volume_m3"] else 0.0

    # crown diameter (max width across the axis) and depth along the axis
    xy = P[:, :2]
    out["crown_diameter_m"] = float(_max_diameter(xy))
    out["crown_depth_m"] = float(-P[:, 2].min()) if P[:, 2].min() < 0 else float(np.ptp(P[:, 2]))
    r_cyl = out["crown_diameter_m"] / 2
    out["cylinder_soil_volume_m3"] = float(np.pi * r_cyl ** 2 * out["crown_depth_m"])
    out["compactness_percent"] = 100 * out["crown_volume_m3"] / out["cylinder_soil_volume_m3"] if out["cylinder_soil_volume_m3"] else 0.0
    try:
        from scipy.spatial import ConvexHull

        out["convex_hull_volume_m3"] = float(ConvexHull(P[:: max(1, len(P) // 200000)]).volume)
    except Exception:
        out["convex_hull_volume_m3"] = 0.0
    if opt.weight_kg:
        out["root_density_kg_m3"] = opt.weight_kg / out["crown_volume_m3"] if out["crown_volume_m3"] else 0.0
        out["root_density_g_cm3"] = out["root_density_kg_m3"] / 1000

    # individual roots: remove the crown core (a central cylinder) and label 3D components.
    # Roots touch near the crown, so the core radius is searched for the value that separates
    # the most roots, then the labels grow back into the core region so each root's length is
    # measured from where it leaves a thin inner core.
    D = out["crown_diameter_m"]
    C = whole.centres()
    rad = np.linalg.norm(C[:, :2], axis=1)
    idx = np.argwhere(whole.occ)
    st26 = ndi.generate_binary_structure(3, 3)
    min_vol = opt.min_root_fraction * out["crown_volume_whole_m3"]
    radii = [opt.core_radius] if opt.core_radius else [f * D for f in (0.08, 0.11, 0.14, 0.17, 0.2, 0.24, 0.28)]
    best = None
    for r in radii:
        occ_r = whole.occ.copy()
        occ_r[tuple(idx[rad <= max(r, 3 * v)].T)] = False
        lab, n = ndi.label(occ_r, st26)
        sizes = ndi.sum(occ_r, lab, range(1, n + 1)) * v ** 3
        keep = [i + 1 for i, s_ in enumerate(sizes) if s_ >= min_vol]
        if best is None or len(keep) > len(best[2]):
            best = (r, lab, keep)
    core_r, lab, keep = best
    rl = -np.ones(whole.occ.shape, int)
    for j, li in enumerate(keep):
        rl[lab == li] = j
    if opt.core_radius:
        inner = opt.core_radius * 0.5
    else:
        # the crown core: radius of the solid just below the stem cut, before roots spread out
        ztop = C[:, 2].max()
        top_slab = C[:, 2] >= ztop - 0.1 * out["crown_depth_m"]
        inner = float(np.quantile(rad[top_slab], 0.9)) if top_slab.any() else 0.06 * D
        inner = min(inner, core_r)
    if core_r > inner:
        from skimage.segmentation import expand_labels

        grow = expand_labels(rl + 1, distance=int(np.ceil((core_r - inner) / v)) + 1) - 1
        region = np.zeros_like(whole.occ)
        region[tuple(idx[rad > inner].T)] = True
        rl = np.where(region & (rl < 0), grow, rl)
    roots = []
    for j in range(len(keep)):
        comp = rl == j
        if comp.sum() >= 3:
            roots.append({"root": j, **_root_metrics(whole, comp, inner)})
    out["root_number"] = len(roots)
    if roots:
        out["root_length_mean_m"] = float(np.mean([r["length_m"] for r in roots]))
        out["root_length_max_m"] = float(np.max([r["length_m"] for r in roots]))
        out["root_angle_mean_deg"] = float(np.mean([r["angle_from_vertical_deg"] for r in roots]))
        out["root_volume_sum_m3"] = float(np.sum([r["volume_m3"] for r in roots]))
    out.update(_cm_units(out))
    for r in roots:
        r.update(_cm_units(r))
    log(f"crown: volume {out['crown_volume_m3'] * 1e6:.1f} cm3, {len(roots)} roots, diameter {out['crown_diameter_m'] * 100:.1f} cm")
    return out, {"solid": whole, "root_labels": rl, "roots": roots, "mesh": (MV, MF), "core_radius": core_r}


def _max_diameter(xy: np.ndarray) -> float:
    from scipy.spatial import ConvexHull
    from scipy.spatial.distance import pdist

    try:
        h = xy[ConvexHull(xy).vertices]
    except Exception:
        h = xy
    return float(pdist(h).max()) if len(h) > 1 else 0.0


def _root_metrics(solid: Solid, comp: np.ndarray, core_r: float) -> dict:
    """Length (geodesic from the end nearest the crown axis), angle, volume, mean diameter."""
    from scipy.sparse.csgraph import dijkstra

    pts = solid.origin + np.argwhere(comp) * solid.voxel
    G, coords = _voxel_graph(comp, solid.voxel)
    rad = np.linalg.norm(pts[:, :2], axis=1)
    start = int(np.argmin(rad + 0.25 * np.abs(pts[:, 2])))  # attachment: nearest the axis, near the top
    d = dijkstra(G, directed=False, indices=start)
    d[~np.isfinite(d)] = -1
    tip = int(np.argmax(d))
    vol = float(comp.sum() * solid.voxel ** 3)
    length = float(d[tip]) + solid.voxel
    vec = pts[tip] - pts[start]
    ang = float(np.degrees(np.arccos(abs(vec[2]) / (np.linalg.norm(vec) + 1e-12))))
    return {"volume_m3": vol, "length_m": length, "straight_length_m": float(np.linalg.norm(vec)),
            "angle_from_vertical_deg": ang, "angle_from_horizontal_deg": 90 - ang,
            "mean_diameter_m": float(2 * np.sqrt(vol / (np.pi * length))) if length > 0 else 0.0,
            "tip_depth_m": float(-pts[tip, 2]), "attach_x": float(pts[start, 0]), "attach_y": float(pts[start, 1]),
            "tip_x": float(pts[tip, 0]), "tip_y": float(pts[tip, 1]), "tip_z": float(pts[tip, 2])}


def _voxel_graph(mask: np.ndarray, voxel: float):
    """26-connected graph over the True voxels of ``mask``."""
    from scipy.sparse import coo_matrix

    coords = np.argwhere(mask)
    index = -np.ones(mask.shape, np.int64)
    index[tuple(coords.T)] = np.arange(len(coords))
    rows, cols, w = [], [], []
    offs = [(a, b, c) for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1) if (a, b, c) > (0, 0, 0)]
    for o in offs:
        q = coords + o
        ok = np.all((q >= 0) & (q < mask.shape), axis=1)
        j = np.full(len(coords), -1)
        j[ok] = index[tuple(q[ok].T)]
        ok &= j >= 0
        rows.append(np.where(ok)[0])
        cols.append(j[ok])
        w.append(np.full(ok.sum(), voxel * np.sqrt(sum(abs(x) for x in o))))
    n = len(coords)
    G = coo_matrix((np.concatenate(w), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n)).tocsr()
    return G.maximum(G.T), coords


def _cm_units(d: dict) -> dict:
    extra = {}
    for k, v in d.items():
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            continue
        if k.endswith("_m3"):
            extra[k[:-3] + "_cm3"] = v * 1e6
        elif k.endswith("_m2"):
            extra[k[:-3] + "_cm2"] = v * 1e4
        elif k.endswith("_m") and not k.endswith("_per_m"):
            extra[k[:-2] + "_cm"] = v * 100
    return extra


# ----------------------------------------------------------------- fibrous systems
def prune_spurs(sk: np.ndarray, voxel: float, spur_len: float) -> np.ndarray:
    """Remove short terminal branches (skeleton noise from bumpy surfaces)."""
    sk = sk.copy()
    G, coords = _voxel_graph(sk, voxel)
    deg = np.diff(G.indptr)
    G = G.tocsr()
    for tip in np.where(deg == 1)[0]:
        path, prev, cur, length = [tip], -1, tip, 0.0
        while True:
            nb = G.indices[G.indptr[cur]:G.indptr[cur + 1]]
            w = G.data[G.indptr[cur]:G.indptr[cur + 1]]
            nxt = [(n, ww) for n, ww in zip(nb, w) if n != prev]
            if len(nxt) != 1:
                break
            n, ww = nxt[0]
            length += ww
            if deg[n] >= 3:  # reached a junction: a spur if short
                if length < spur_len:
                    sk[tuple(coords[path].T)] = False
                break
            if length >= spur_len:
                break
            prev, cur = cur, n
            path.append(cur)
    return sk


def fibrous_traits(solid: Solid, depth_bins: int = 10, spur_voxels: float = 4.0, log=print) -> tuple[dict, dict]:
    """Skeleton traits of a whole root system in a solid voxel model (+Z up, top at z = 0)."""
    from scipy.sparse.csgraph import dijkstra
    from skimage.morphology import skeletonize

    sk = skeletonize(solid.occ)
    if sk.dtype != bool:
        sk = sk > 0
    if spur_voxels:
        sk = prune_spurs(sk, solid.voxel, spur_voxels * solid.voxel)
    G, coords = _voxel_graph(sk, solid.voxel)
    deg = np.diff(G.indptr)
    pts = solid.origin + coords * solid.voxel
    out = {"voxel_size": solid.voxel, "root_volume_m3": solid.volume,
           "total_length_m": float(G.sum() / 2), "n_tips": int(np.sum(deg == 1)),
           "n_branch_points": int(_count_clusters(coords[deg >= 3]))}
    if len(pts):
        z = pts[:, 2]
        out["max_depth_m"] = float(z.max() - z.min())
        out["max_width_m"] = float(_max_diameter(pts[:, :2]))
        try:
            from scipy.spatial import ConvexHull

            out["convex_hull_volume_m3"] = float(ConvexHull(pts[:: max(1, len(pts) // 100000)]).volume)
            out["solidity"] = solid.volume / out["convex_hull_volume_m3"]
        except Exception:
            pass
        top = int(np.argmax(z))
        d = dijkstra(G, directed=False, indices=top)
        d[~np.isfinite(d)] = -1
        out["primary_length_m"] = float(d.max())
        out["length_width_ratio"] = out["max_depth_m"] / out["max_width_m"] if out["max_width_m"] else 0.0
        # root length per depth layer: each skeleton edge's length split by its mid-depth
        coo = G.tocoo()
        mid = (z[coo.row] + z[coo.col]) / 2
        edges = np.linspace(z.max(), z.min(), depth_bins + 1)
        prof = np.histogram(mid, bins=edges[::-1], weights=coo.data / 2)[0][::-1]
        out["length_by_depth_m"] = prof.tolist()
        out["depth_bin_edges_m"] = (z.max() - edges).tolist()
        out["d50_depth_m"] = float(np.interp(0.5, np.cumsum(prof) / max(prof.sum(), 1e-12), (z.max() - edges)[1:]))
        out["mean_diameter_m"] = float(2 * np.sqrt(solid.volume / (np.pi * out["total_length_m"]))) if out["total_length_m"] else 0.0
    out.update(_cm_units({k: v for k, v in out.items() if not isinstance(v, list)}))
    log(f"fibrous roots: total length {out['total_length_m']:.3f} m, {out['n_tips']} tips")
    return out, {"skeleton": pts}


def _count_clusters(coords: np.ndarray) -> int:
    if len(coords) == 0:
        return 0
    m = np.zeros(coords.max(0) + 2, bool)
    m[tuple(coords.T)] = True
    return int(ndi.label(m, ndi.generate_binary_structure(3, 3))[1])


def fibrous_from_scan(scan: Scan, voxel: float = 0.0, close_iter: int = 1, fill: bool = True, log=print):
    # thin roots are scanned as hollow tubes: the voxel must be coarse enough to close them
    v = voxel or max(auto_voxel(scan.points, 9), 4 * median_spacing(scan.points))
    sol = solidify(voxelize(scan.points, v), close_iter, fill=fill)
    return fibrous_traits(sol, log=log)


def load_volume_stack(path, voxel_m: float, threshold: float | None = None, invert: bool = False) -> Solid:
    """Load a CT / MRI TIFF stack (multi-page TIFF or a folder of slices, slice 0 = top) and
    threshold it (Otsu if not given). Returns a +Z-up solid with the top at z = 0."""
    from pathlib import Path

    import tifffile

    from .clean import otsu_threshold

    p = Path(path)
    if p.is_dir():
        files = sorted(f for f in p.iterdir() if f.suffix.lower() in (".tif", ".tiff", ".png"))
        if files[0].suffix.lower() == ".png":
            from .phenotype2d import read_image

            vol = np.stack([read_image(f).mean(2) for f in files])
        else:
            vol = np.stack([tifffile.imread(f) for f in files])
    else:
        vol = tifffile.imread(p)
    vol = vol.astype(np.float32)
    thr = otsu_threshold(vol[::2, ::4, ::4].ravel()) if threshold is None else threshold
    occ = (vol < thr) if invert else (vol > thr)
    occ = np.transpose(occ, (2, 1, 0))[:, :, ::-1]  # (z, y, x) slices -> (x, y, z) with z up
    lab, n = ndi.label(occ)
    if n > 1:  # keep the root system (largest component)
        sizes = ndi.sum(occ, lab, range(1, n + 1))
        occ = lab == (np.argmax(sizes) + 1)
    origin = np.array([0.0, 0.0, -occ.shape[2] * voxel_m])
    return Solid(occ, origin, voxel_m)


def solid_to_scan(solid: Solid, labels: np.ndarray | None = None, name: str = "roots") -> Scan:
    """Surface voxels as a coloured point cloud, for the viewer."""
    er = ndi.binary_erosion(solid.occ)
    shell = solid.occ & ~er
    pts = solid.centres(shell)
    s = Scan(points=pts, name=name, metric=True)
    if labels is not None:
        s.labels = labels[shell]
    s.colors = np.tile([0.85, 0.75, 0.55], (len(pts), 1))
    return s


def crown_pipeline(scan: Scan, axis="z", stem_point=None, base_point=None, green_sheet=True, plane=True,
                   stem_cut: float = 0.0, opt: CrownOptions | None = None, log=print):
    """Background removal -> orientation -> stem cut -> crown traits. Returns (scan, traits, extra)."""
    s = remove_background(scan, green_sheet, plane) if (green_sheet or plane) else scan
    s = orient(s, axis, stem_point, base_point)
    from .clean import largest_clusters, remove_statistical_outliers

    s = remove_statistical_outliers(s)
    s = largest_clusters(s, keep=1)
    s = orient(s, "z")  # re-centre on the cleaned object
    if stem_cut > 0:
        s = cut_stem(s, stem_cut)
    t, extra = crown_traits(s, opt, log=log)
    t["options"] = asdict(opt or CrownOptions())
    # per-point root labels for display
    sol = extra["solid"]
    idx = np.clip(np.round((s.points - sol.origin) / sol.voxel).astype(int), 0, np.array(sol.occ.shape) - 1)
    s.labels = extra["root_labels"][tuple(idx.T)]
    return s, t, extra
