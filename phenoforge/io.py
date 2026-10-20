"""Reading and writing scans.

Supported inputs
----------------
Point clouds : .ply (incl. 3D Gaussian Splatting .ply), .pcd, .xyz/.xyzrgb/.pts/.txt/.csv, .las/.laz (laspy)
Meshes       : .obj, .glb, .gltf, .stl, .off, .ply (faces), .usdz/.usd/.usdc/.usda (usd-core)
Packages     : .zip and other zip-based scan packages: the best geometry inside is loaded,
               images and JSON sidecars are listed in ``scan.metadata``.

Meshes are kept on the scan and also sampled into a coloured point cloud, because every
trait in :mod:`phenoforge.traits` works on points.
"""

from __future__ import annotations

import json
import os
import tempfile
import zipfile
from pathlib import Path

import numpy as np

from .scan import Scan

POINT_EXT = {".ply", ".pcd", ".xyz", ".xyzrgb", ".pts", ".txt", ".csv", ".las", ".laz"}
MESH_EXT = {".obj", ".glb", ".gltf", ".stl", ".off"}
USD_EXT = {".usdz", ".usd", ".usdc", ".usda"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".tif", ".tiff", ".bmp"}
SUPPORTED = POINT_EXT | MESH_EXT | USD_EXT | {".zip", ".ftscan"}

SH_C0 = 0.28209479177387814  # zeroth spherical-harmonic constant used by 3DGS


def load(path: str | os.PathLike, mesh_samples: int = 400_000, splat_min_opacity: float = 0.3) -> Scan:
    """Load any supported file and return a :class:`Scan`."""
    p = Path(path)
    ext = p.suffix.lower()
    if not p.exists():
        raise FileNotFoundError(p)
    if p.is_dir():
        return _load_package_dir(p, mesh_samples)
    if ext in (".zip", ".ftscan") or (ext not in SUPPORTED and zipfile.is_zipfile(p)):
        return _load_zip(p, mesh_samples)
    if ext in USD_EXT:
        scan = _load_usd(p, mesh_samples)
    elif ext == ".ply":
        scan = _load_ply(p, mesh_samples, splat_min_opacity)
    elif ext in MESH_EXT:
        scan = _load_trimesh(p, mesh_samples)
    elif ext == ".pcd":
        scan = _load_o3d_cloud(p)
    elif ext in (".las", ".laz"):
        scan = _load_las(p)
    elif ext in (".xyz", ".xyzrgb", ".pts", ".txt", ".csv"):
        scan = _load_ascii(p)
    else:
        raise ValueError(f"Unsupported file type: {ext}")
    scan.name = p.stem
    scan.source = str(p)
    scan.history.append(f"loaded {p.name} ({len(scan)} points{', mesh' if scan.has_mesh else ''})")
    return scan


# ---------------------------------------------------------------- point clouds
def _load_ply(p: Path, mesh_samples: int, splat_min_opacity: float) -> Scan:
    from plyfile import PlyData

    ply = PlyData.read(str(p))
    names = {e.name for e in ply.elements}
    v = ply["vertex"].data
    props = set(v.dtype.names)
    xyz = np.column_stack([v["x"], v["y"], v["z"]]).astype(np.float64)

    if {"f_dc_0", "f_dc_1", "f_dc_2"} <= props:  # 3D Gaussian Splatting
        rgb = 0.5 + SH_C0 * np.column_stack([v["f_dc_0"], v["f_dc_1"], v["f_dc_2"]])
        keep = np.ones(len(xyz), bool)
        alpha = np.ones(len(xyz))
        if "opacity" in props:
            alpha = 1.0 / (1.0 + np.exp(-np.asarray(v["opacity"], float)))
            keep = alpha >= splat_min_opacity
        s = Scan(points=xyz[keep], colors=np.clip(rgb[keep], 0, 1))
        s.extras["splat_alpha"] = alpha[keep].astype(np.float32)
        if {"scale_0", "scale_1", "scale_2"} <= props:
            # area-equivalent disc radius: sqrt of the two largest axes (splats are often flat)
            ax = np.sort(np.exp(np.column_stack([v["scale_0"], v["scale_1"], v["scale_2"]]).astype(float)), axis=1)
            s.extras["splat_radius"] = np.sqrt(ax[keep, 1] * ax[keep, 2]).astype(np.float32)
        s.metadata["format"] = "gaussian_splat"
        s.metadata["splats_total"] = int(len(xyz))
        return s

    if "face" in names and len(ply["face"].data) > 0:
        return _load_trimesh(p, mesh_samples)

    cols = None
    for trip in (("red", "green", "blue"), ("r", "g", "b"), ("diffuse_red", "diffuse_green", "diffuse_blue")):
        if set(trip) <= props:
            cols = np.column_stack([v[c] for c in trip]).astype(np.float64)
            if cols.max(initial=0) > 1.0:
                cols /= 255.0 if cols.max() <= 255 else 65535.0
            break
    nrm = None
    if {"nx", "ny", "nz"} <= props:
        nrm = np.column_stack([v["nx"], v["ny"], v["nz"]]).astype(np.float64)
    s = Scan(points=xyz, colors=cols, normals=nrm)
    for extra in ("confidence", "intensity", "scalar_Intensity"):
        if extra in props:
            s.metadata[extra] = np.asarray(v[extra])
    return s


def _load_o3d_cloud(p: Path) -> Scan:
    import open3d as o3d

    pc = o3d.io.read_point_cloud(str(p))
    return Scan.from_o3d(pc)


def _load_las(p: Path) -> Scan:
    try:
        import laspy
    except ImportError as e:  # pragma: no cover
        raise ImportError("Reading LAS/LAZ needs the 'laspy' package (pip install laspy[lazrs])") from e
    las = laspy.read(str(p))
    xyz = np.column_stack([las.x, las.y, las.z]).astype(np.float64)
    cols = None
    if all(hasattr(las, c) for c in ("red", "green", "blue")):
        cols = np.column_stack([las.red, las.green, las.blue]).astype(np.float64)
        cols /= 65535.0 if cols.max(initial=0) > 255 else 255.0
    s = Scan(points=xyz, colors=cols)
    s.metric = True  # LAS is georeferenced in metres in practice
    return s


def _load_ascii(p: Path) -> Scan:
    delim = "," if p.suffix.lower() == ".csv" else None
    with open(p, "r", errors="ignore") as fh:
        first = fh.readline()
    skip = 0
    try:
        [float(x) for x in first.replace(",", " ").split()[:3]]
    except ValueError:
        skip = 1
    if p.suffix.lower() == ".pts":  # .pts often starts with a point count line
        if len(first.split()) == 1:
            skip = 1
    a = np.loadtxt(p, delimiter=delim, skiprows=skip, ndmin=2)
    xyz = a[:, :3]
    cols = None
    if a.shape[1] >= 6:
        c = a[:, -3:] if a.shape[1] in (7, 10) else a[:, 3:6]
        cols = c / (255.0 if c.max(initial=0) > 1 else 1.0)
    return Scan(points=xyz, colors=cols)


# ---------------------------------------------------------------------- meshes
def _load_trimesh(p: Path, n_samples: int) -> Scan:
    import trimesh

    loaded = trimesh.load(str(p), force="scene", process=False)
    meshes = []
    for node in loaded.graph.nodes_geometry:
        T, gname = loaded.graph[node]
        g = loaded.geometry[gname]
        if isinstance(g, trimesh.Trimesh) and len(g.faces):
            g = g.copy()
            g.apply_transform(T)
            meshes.append(g)
        elif isinstance(g, trimesh.PointCloud):
            pts = trimesh.transform_points(g.vertices, T)
            cols = None if g.colors is None or len(g.colors) == 0 else np.asarray(g.colors)[:, :3] / 255.0
            return Scan(points=pts, colors=cols)
    if not meshes:
        raise ValueError(f"No triangle geometry found in {p.name}")
    return scan_from_trimeshes(meshes, n_samples)


def scan_from_trimeshes(meshes, n_samples: int) -> Scan:
    """Sample points (with texture or vertex colour) from one or more trimesh meshes."""
    import trimesh

    areas = np.array([m.area for m in meshes], float)
    counts = np.maximum(1, np.round(n_samples * areas / max(areas.sum(), 1e-12))).astype(int)
    pts_all, col_all, V, F, VC = [], [], [], [], []
    off = 0
    for m, n in zip(meshes, counts):
        try:
            pts, fidx, cols = trimesh.sample.sample_surface(m, int(n), sample_color=True, seed=0)
            cols = np.asarray(cols, float)[:, :3] / 255.0
        except Exception:
            pts, fidx = trimesh.sample.sample_surface(m, int(n), seed=0)
            cols = None
        if cols is None:
            fc = _face_colors(m)
            cols = fc[fidx] if fc is not None else np.full((len(pts), 3), 0.6)
        pts_all.append(pts)
        col_all.append(cols)
        vc = _vertex_colors(m)
        V.append(np.asarray(m.vertices, float))
        F.append(np.asarray(m.faces, np.int64) + off)
        VC.append(vc if vc is not None else np.full((len(m.vertices), 3), 0.6))
        off += len(m.vertices)
    return Scan(
        points=np.vstack(pts_all),
        colors=np.vstack(col_all),
        mesh_vertices=np.vstack(V),
        mesh_triangles=np.vstack(F),
        mesh_colors=np.vstack(VC),
    )


def _vertex_colors(m):
    try:
        vis = m.visual
        if vis.kind == "texture":
            vis = vis.to_color()
        vc = np.asarray(vis.vertex_colors, float)[:, :3] / 255.0
        return vc if len(vc) == len(m.vertices) else None
    except Exception:
        return None


def _face_colors(m):
    try:
        vis = m.visual
        if vis.kind == "texture":
            vis = vis.to_color()
        fc = np.asarray(vis.face_colors, float)[:, :3] / 255.0
        return fc if len(fc) == len(m.faces) else None
    except Exception:
        return None


# ------------------------------------------------------------------------- USD
def _load_usd(p: Path, n_samples: int) -> Scan:
    """Load USD/USDZ meshes via usd-core (pxr). Textures are sampled through trimesh."""
    try:
        from pxr import Usd, UsdGeom, UsdShade
    except ImportError as e:
        raise ImportError("Reading USDZ needs the 'usd-core' package (pip install usd-core)") from e
    import trimesh
    from PIL import Image

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        if p.suffix.lower() == ".usdz":
            with zipfile.ZipFile(p) as z:
                z.extractall(root)
            layers = sorted(root.rglob("*.usd*"), key=lambda q: q.stat().st_size, reverse=True)
            if not layers:
                raise ValueError("USDZ archive contains no USD layer")
            stage_path = layers[0]
        else:
            stage_path = p
        stage = Usd.Stage.Open(str(stage_path))
        up = UsdGeom.GetStageUpAxis(stage)
        mpu = UsdGeom.GetStageMetersPerUnit(stage) or 1.0
        meshes = []
        xcache = UsdGeom.XformCache()
        for prim in stage.Traverse():
            if not prim.IsA(UsdGeom.Mesh):
                continue
            um = UsdGeom.Mesh(prim)
            pts = np.asarray(um.GetPointsAttr().Get() or [], float)
            counts = np.asarray(um.GetFaceVertexCountsAttr().Get() or [], int)
            idx = np.asarray(um.GetFaceVertexIndicesAttr().Get() or [], int)
            if len(pts) == 0 or len(counts) == 0:
                continue
            M = np.asarray(xcache.GetLocalToWorldTransform(prim), float).T  # USD is row-vector
            pts = pts @ M[:3, :3].T + M[:3, 3]
            corner = _triangulate(counts)
            visual = None
            uv_attr = UsdGeom.PrimvarsAPI(prim).GetPrimvar("st")
            tex_img = _usd_texture(prim, UsdShade, root if p.suffix.lower() == ".usdz" else p.parent)
            if uv_attr and uv_attr.HasValue() and tex_img is not None:
                st = np.asarray(uv_attr.ComputeFlattened(), float)
                interp = uv_attr.GetInterpolation()
                if interp == "faceVarying" and len(st) == len(idx):
                    # unweld so every triangle corner has its own uv
                    pts_m = pts[idx[corner.ravel()]]
                    uv_m = st[corner.ravel()]
                    tris = np.arange(len(pts_m)).reshape(-1, 3)
                else:
                    pts_m, uv_m = pts, st if len(st) == len(pts) else None
                    tris = idx[corner]
                if uv_m is not None:
                    visual = trimesh.visual.TextureVisuals(uv=uv_m, image=Image.open(tex_img))
                    meshes.append(trimesh.Trimesh(pts_m, tris, visual=visual, process=False))
                    continue
            mesh = trimesh.Trimesh(pts, idx[corner].reshape(-1, 3), process=False)
            dc = UsdGeom.PrimvarsAPI(prim).GetPrimvar("displayColor")
            if dc and dc.HasValue():
                c = np.asarray(dc.ComputeFlattened(), float)
                if len(c) == len(pts):
                    mesh.visual.vertex_colors = (np.clip(c, 0, 1) * 255).astype(np.uint8)
            meshes.append(mesh)
        if not meshes:
            raise ValueError("No meshes found in USD stage")
        scan = scan_from_trimeshes(meshes, n_samples)
    if up == "Y":  # convert Y-up (Apple default) to Z-up
        R = np.array([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float)
        scan.transform(R)
    if mpu != 1.0:
        scan.scale(mpu, note=f"USD metersPerUnit {mpu}")
    scan.metric = True  # Apple Object Capture / RoomPlan exports are metric
    scan.metadata["format"] = "usd"
    return scan


def _triangulate(counts: np.ndarray) -> np.ndarray:
    """Fan-triangulate polygons; return (T, 3) corner positions into faceVertexIndices."""
    starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
    corner = []
    for s, c in zip(starts, counts):
        for k in range(1, c - 1):
            corner.extend((s, s + k, s + k + 1))
    return np.asarray(corner, int).reshape(-1, 3)


def _usd_texture(prim, UsdShade, base: Path):
    try:
        mat, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
        if not mat:
            return None
        for sh in mat.GetPrim().GetChildren():
            shader = UsdShade.Shader(sh)
            if not shader:
                continue
            f = shader.GetInput("file")
            if f and f.Get() is not None:
                ap = f.Get()
                path = ap.resolvedPath or ap.path
                cand = Path(path)
                if not cand.is_absolute():
                    cand = base / path.lstrip("./")
                if cand.exists():
                    return cand
                hits = list(base.rglob(Path(path).name))
                if hits:
                    return hits[0]
    except Exception:
        return None
    return None


# -------------------------------------------------------------------- packages
GEOM_PRIORITY = [".ply", ".usdz", ".glb", ".gltf", ".obj", ".usdc", ".usd", ".pcd", ".las", ".laz", ".xyz", ".pts", ".stl"]


def _pick_geometry(files: list[Path]) -> Path | None:
    cands = [f for f in files if f.suffix.lower() in GEOM_PRIORITY]
    if not cands:
        return None
    return sorted(cands, key=lambda f: (GEOM_PRIORITY.index(f.suffix.lower()), -f.stat().st_size))[0]


def _load_package_dir(d: Path, mesh_samples: int) -> Scan:
    files = [f for f in d.rglob("*") if f.is_file()]
    geom = _pick_geometry(files)
    if geom is None:
        raise ValueError(f"No supported geometry in package {d.name}")
    scan = load(geom, mesh_samples)
    if geom.suffix.lower() == ".ply" and _ios_frame(files):
        # iOS capture frames (ARKit / Object Capture, e.g. iPhonotype .ftscan) are Y-up; PLY carries no up axis
        R = np.array([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float)
        scan.transform(R)
        scan.metadata["package_transform"] = R  # maps package (capture) coordinates to the loaded scan
        scan.history.append("converted Y-up to Z-up (iOS capture frame in package manifest)")
        wf = next((f for f in files if f.name == "workflow.json"), None)
        try:
            w = json.loads(wf.read_text(errors="ignore")) if wf else {}
        except Exception:
            w = {}
        if (scan.metadata.get("format") == "gaussian_splat" and w.get("on_device_splat_geometry_units") == "meters"
                and w.get("metric_scale_verified")):
            scan.metric = True
            scan.history.append(f"metric from the package ({w.get('metric_scale_source', '?')}, "
                                f"confidence {w.get('metric_scale_confidence', float('nan')):.2f})")
    scan.metadata["package"] = str(d)
    scan.metadata["images"] = [str(f) for f in files if f.suffix.lower() in IMAGE_EXT]
    for j in files:
        if j.suffix.lower() == ".json" and j.stat().st_size < 2_000_000:
            try:
                scan.metadata.setdefault("sidecars", {})[j.name] = json.loads(j.read_text(errors="ignore"))
            except Exception:
                pass
    return scan


def _ios_frame(files: list[Path]) -> bool:
    """True when the package manifest says its coordinates come from an iOS capture session."""
    for f in files:
        if f.name.lower() == "manifest.json" and f.stat().st_size < 2_000_000:
            try:
                frame = json.loads(f.read_text(errors="ignore")).get("coordinate_frames", {}).get("source_frame", "")
            except Exception:
                continue
            if str(frame).lower().startswith(("ios_", "arkit")):
                return True
    return False


PACKAGE_CACHE = Path(tempfile.gettempdir()) / "phenoforge_packages"
CACHE_KEEP = 4  # unpacked packages kept; packages can be ~1 GB each


def _unpack(p: Path) -> Path:
    """Unpack a zip package once into a shared cache; reopening the same file reuses it."""
    import hashlib
    import shutil
    import time

    st = p.stat()
    key = hashlib.sha1(f"{p.resolve()}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:16]
    td = PACKAGE_CACHE / key  # short: Windows paths are limited to 260 characters
    done = td / ".unpacked"
    if done.exists():
        os.utime(done)  # most recently used
        return td
    shutil.rmtree(td, ignore_errors=True)
    td.mkdir(parents=True)
    with zipfile.ZipFile(p) as z:
        for m in z.infolist():
            if m.filename.startswith("__MACOSX/") or "/._" in m.filename:  # macOS metadata, not scan data
                continue
            target = (td / m.filename).resolve()  # guard against path traversal
            if not str(target).startswith(str(td.resolve())):
                continue
            z.extract(m, td)
    done.write_text(str(p))
    # drop the least recently used packages beyond CACHE_KEEP
    old = sorted((d for d in PACKAGE_CACHE.iterdir() if (d / ".unpacked").exists() and d != td),
                 key=lambda d: (d / ".unpacked").stat().st_mtime, reverse=True)
    for d in old[CACHE_KEEP - 1:]:
        shutil.rmtree(d, ignore_errors=True)
    for d in Path(tempfile.gettempdir()).glob("phenoforge_pkg_*"):  # folders left by older versions
        if time.time() - d.stat().st_mtime > 3600:
            shutil.rmtree(d, ignore_errors=True)
    return td


def _load_zip(p: Path, mesh_samples: int) -> Scan:
    td = _unpack(p)
    scan = _load_package_dir(td, mesh_samples)
    scan.name = p.stem
    scan.source = str(p)
    return scan


# --------------------------------------------------------------------- writing
def save_point_cloud(scan: Scan, path: str | os.PathLike) -> None:
    p = Path(path)
    ext = p.suffix.lower()
    if ext in (".ply", ".pcd"):
        import open3d as o3d

        o3d.io.write_point_cloud(str(p), scan.to_o3d())
        if scan.labels is not None and ext == ".ply":
            _write_labelled_ply(scan, p)
    elif ext in (".xyz", ".csv", ".txt"):
        cols = [scan.points]
        header = "x,y,z"
        if scan.colors is not None:
            cols.append(np.round(scan.colors * 255))
            header += ",r,g,b"
        if scan.labels is not None:
            cols.append(scan.labels[:, None])
            header += ",label"
        np.savetxt(p, np.hstack(cols), delimiter="," if ext == ".csv" else " ", fmt="%.6f",
                   header=header if ext == ".csv" else "", comments="")
    else:
        raise ValueError(f"Cannot write point clouds as {ext}")


def _write_labelled_ply(scan: Scan, p: Path) -> None:
    from plyfile import PlyData, PlyElement

    n = len(scan)
    dt = [("x", "f4"), ("y", "f4"), ("z", "f4")]
    if scan.colors is not None:
        dt += [("red", "u1"), ("green", "u1"), ("blue", "u1")]
    dt += [("label", "i4")]
    a = np.empty(n, dtype=dt)
    a["x"], a["y"], a["z"] = scan.points.T
    if scan.colors is not None:
        c = np.round(scan.colors * 255).astype(np.uint8)
        a["red"], a["green"], a["blue"] = c.T
    a["label"] = scan.labels
    PlyData([PlyElement.describe(a, "vertex")], text=False).write(str(p))


def save_mesh(vertices, triangles, colors, path: str | os.PathLike) -> None:
    import trimesh

    m = trimesh.Trimesh(vertices, triangles, process=False)
    if colors is not None:
        m.visual.vertex_colors = (np.clip(colors, 0, 1) * 255).astype(np.uint8)
    m.export(str(path))
