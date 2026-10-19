"""Mesh reconstruction and multi-colour 3D print export.

``reconstruct_mesh`` builds a watertight-ish surface from the cloud (Poisson, trimmed by
sample density) or uses the scan's own mesh. ``quantize_colours`` reduces vertex colours to
N filament colours (k-means in Lab, or a fixed palette), ``split_by_colour`` makes one
part per colour, and ``export_print_bundle`` writes:

  * <name>.3mf             one object per colour with a colour material each, which
                           PrusaSlicer / OrcaSlicer / Bambu Studio load as a multi-part
                           object so each part can be given its own filament/extruder
  * <name>_<colour>.stl    one STL per colour (for Snapmaker Luban, Cura, etc.)
  * <name>.obj + .mtl      coloured OBJ for viewers
  * <name>_palette.json    palette and per-colour triangle counts
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np

from .scan import Scan, median_spacing


def reconstruct_mesh(scan: Scan, method: str = "poisson", depth: int = 9, density_trim: float = 0.05,
                     alpha: float | None = None):
    """Return (vertices, triangles, vertex_colours)."""
    import open3d as o3d

    if method == "existing":
        if not scan.has_mesh:
            raise ValueError("Scan has no mesh; use 'poisson', 'alpha' or 'ball'")
        return scan.mesh_vertices, scan.mesh_triangles, scan.mesh_colors
    s = scan.copy()
    s.ensure_normals()
    pc = s.to_o3d()
    if method == "poisson":
        mesh, dens = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(pc, depth=depth)
        dens = np.asarray(dens)
        mesh.remove_vertices_by_mask(dens < np.quantile(dens, density_trim))
    elif method == "alpha":
        a = alpha or 3 * median_spacing(scan.points)
        mesh = o3d.geometry.TriangleMesh.create_from_point_cloud_alpha_shape(pc, a)
    elif method == "ball":
        r = median_spacing(scan.points)
        mesh = o3d.geometry.TriangleMesh.create_from_point_cloud_ball_pivoting(
            pc, o3d.utility.DoubleVector([1.5 * r, 3 * r, 6 * r]))
    else:
        raise ValueError(method)
    mesh.remove_degenerate_triangles()
    mesh.remove_unreferenced_vertices()
    V = np.asarray(mesh.vertices)
    F = np.asarray(mesh.triangles)
    # colour vertices from the nearest scan points
    if scan.colors is not None:
        from scipy.spatial import cKDTree

        _, nn = cKDTree(scan.points).query(V, k=4)
        C = scan.colors[nn].mean(1)
    else:
        C = np.full((len(V), 3), 0.5)
    return V, F, C


def _rgb_to_lab(c):
    import cv2

    return cv2.cvtColor((np.clip(c, 0, 1).reshape(-1, 1, 3) * 255).astype(np.uint8), cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(float)


def quantize_colours(vertex_colours: np.ndarray, n: int = 4, palette: np.ndarray | None = None, seed: int = 0):
    """Return (labels per vertex, palette (n, 3) in [0, 1])."""
    import cv2

    lab = _rgb_to_lab(vertex_colours).astype(np.float32)
    if palette is not None:
        pal = np.asarray(palette, float)
        if pal.max() > 1:
            pal = pal / 255.0
        d = ((lab[:, None, :] - _rgb_to_lab(pal)[None]) ** 2).sum(-1)
        return d.argmin(1), pal
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.5)
    cv2.setRNGSeed(seed)
    _, labels, centres = cv2.kmeans(lab, n, None, crit, 5, cv2.KMEANS_PP_CENTERS)
    labels = labels.ravel()
    pal = np.array([vertex_colours[labels == k].mean(0) if np.any(labels == k) else [0.5] * 3 for k in range(n)])
    # order palette dark -> light, so colour 0 is a stable choice for the base
    order = np.argsort(_rgb_to_lab(pal)[:, 0])
    remap = np.empty(n, int)
    remap[order] = np.arange(n)
    return remap[labels], pal[order]


def split_by_colour(V, F, vertex_labels, n):
    """Assign each triangle to the majority label of its vertices; return list of (V, F) per colour."""
    tl = vertex_labels[F]
    face_lab = np.array([np.bincount(t, minlength=n).argmax() for t in tl])
    parts = []
    for k in range(n):
        f = F[face_lab == k]
        if len(f) == 0:
            parts.append((np.zeros((0, 3)), np.zeros((0, 3), int)))
            continue
        used = np.unique(f)
        remap = -np.ones(len(V), int)
        remap[used] = np.arange(len(used))
        parts.append((V[used], remap[f]))
    return parts, face_lab


def add_base(V, F, C, thickness: float, margin: float = 0.0, colour=(0.35, 0.25, 0.15)):
    """Add a rectangular plinth under the model (helps thin plants print)."""
    lo, hi = V.min(0), V.max(0)
    x0, y0 = lo[:2] - margin
    x1, y1 = hi[:2] + margin
    z1 = lo[2]
    z0 = z1 - thickness
    bv = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
                   [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], float)
    bf = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
                   [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]], int) + len(V)
    return np.vstack([V, bv]), np.vstack([F, bf]), np.vstack([C, np.tile(colour, (8, 1))])


def write_3mf(path, parts, palette, names=None, unit: str = "millimeter") -> None:
    """Minimal 3MF core writer: one object per part with a base material per colour, all
    grouped in one build item via a components object."""
    names = names or [f"colour_{k}" for k in range(len(parts))]
    hexcol = ["#%02X%02X%02XFF" % tuple(int(round(v * 255)) for v in c) for c in palette]
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           f'<model unit="{unit}" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">',
           '<metadata name="Application">PhenoForge</metadata>', "<resources>",
           '<basematerials id="1">']
    for nm, h in zip(names, hexcol):
        out.append(f'<base name="{nm}" displaycolor="{h}"/>')
    out.append("</basematerials>")
    oid = 2
    ids = []
    for k, (V, F) in enumerate(parts):
        if len(F) == 0:
            continue
        out.append(f'<object id="{oid}" name="{names[k]}" type="model" pid="1" pindex="{k}"><mesh><vertices>')
        out.extend(f'<vertex x="{x:.4f}" y="{y:.4f}" z="{z:.4f}"/>' for x, y, z in V)
        out.append("</vertices><triangles>")
        out.extend(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in F)
        out.append("</triangles></mesh></object>")
        ids.append(oid)
        oid += 1
    out.append(f'<object id="{oid}" name="plant" type="model"><components>')
    out.extend(f'<component objectid="{i}"/>' for i in ids)
    out.append("</components></object></resources>")
    out.append(f'<build><item objectid="{oid}"/></build></model>')
    ct = ('<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
            '</Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", "\n".join(out))


def write_stl(path, V, F) -> None:
    import trimesh

    trimesh.Trimesh(V, F, process=False).export(str(path))


def write_obj(path, parts, palette, names) -> None:
    p = Path(path)
    mtl = p.with_suffix(".mtl")
    with open(mtl, "w") as fh:
        for nm, c in zip(names, palette):
            fh.write(f"newmtl {nm}\nKd {c[0]:.4f} {c[1]:.4f} {c[2]:.4f}\n\n")
    with open(p, "w") as fh:
        fh.write(f"mtllib {mtl.name}\n")
        off = 1
        for (V, F), nm in zip(parts, names):
            if len(F) == 0:
                continue
            fh.write(f"o {nm}\nusemtl {nm}\n")
            for v in V:
                fh.write(f"v {v[0]:.5f} {v[1]:.5f} {v[2]:.5f}\n")
            for f in F + off:
                fh.write(f"f {f[0]} {f[1]} {f[2]}\n")
            off += len(V)


def export_print_bundle(scan: Scan, out_dir, name: str = "plant", n_colours: int = 4, palette=None,
                        target_height_mm: float | None = 120.0, method: str = "poisson", depth: int = 9,
                        base_mm: float = 2.0) -> dict:
    """Make a printable multi-colour bundle. Model units are converted to mm: if the scan is
    metric it is printed at true size unless ``target_height_mm`` rescales it."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    V, F, C = reconstruct_mesh(scan, method=method, depth=depth)
    V = V.copy()
    V -= V.min(0)
    V *= 1000.0 if scan.metric else 1.0
    if target_height_mm:
        V *= target_height_mm / max(V[:, 2].max(), 1e-9)
    labels, pal = quantize_colours(C, n_colours, palette)
    if base_mm:
        nV = len(V)
        V, F, C = add_base(V, F, C, base_mm)
        labels = np.concatenate([labels, np.zeros(len(V) - nV, int)])  # base takes colour 0 (darkest)
    parts, _ = split_by_colour(V, F, labels, len(pal))
    names = [f"c{k}_{'%02x%02x%02x' % tuple(int(v * 255) for v in pal[k])}" for k in range(len(pal))]
    write_3mf(out / f"{name}.3mf", parts, pal, names)
    stls = []
    for (pv, pf), nm in zip(parts, names):
        if len(pf):
            fp = out / f"{name}_{nm}.stl"
            write_stl(fp, pv, pf)
            stls.append(str(fp))
    write_obj(out / f"{name}.obj", parts, pal, names)
    info = {"palette_rgb": (pal * 255).round().astype(int).tolist(), "names": names,
            "triangles_per_colour": [int(len(pf)) for _, pf in parts], "size_mm": np.ptp(V, axis=0).round(2).tolist(),
            "files": {"3mf": str(out / f"{name}.3mf"), "obj": str(out / f"{name}.obj"), "stl": stls}}
    with open(out / f"{name}_palette.json", "w") as fh:
        json.dump(info, fh, indent=2)
    return info
