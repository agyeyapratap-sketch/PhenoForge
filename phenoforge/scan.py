"""The Scan container: a coloured point cloud, an optional mesh, and metadata."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class Scan:
    """A plant scan in a right-handed frame with +Z up once ``align_ground`` has run.

    points  : (N, 3) float64, model units (metres once scaled)
    colors  : (N, 3) float64 in [0, 1], or None
    normals : (N, 3) float64, or None
    labels  : (N,) int, -1 = unlabelled (plant / leaf ids from segmentation)
    mesh_vertices / mesh_triangles / mesh_colors : optional triangle mesh
    units_per_metre : 1.0 when the scan is metric (LiDAR or scaled), else unknown
    metric : True once the scale is known (LiDAR import, ArUco or two-point scale)
    """

    points: np.ndarray
    colors: np.ndarray | None = None
    normals: np.ndarray | None = None
    labels: np.ndarray | None = None
    mesh_vertices: np.ndarray | None = None
    mesh_triangles: np.ndarray | None = None
    mesh_colors: np.ndarray | None = None
    name: str = "scan"
    source: str = ""
    metric: bool = False
    ground_z: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    history: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.points = np.asarray(self.points, dtype=np.float64).reshape(-1, 3)
        if self.colors is not None:
            c = np.asarray(self.colors, dtype=np.float64).reshape(-1, 3)
            if c.max(initial=0) > 1.0:
                c = c / 255.0
            self.colors = np.clip(c, 0, 1)
        if self.normals is not None:
            self.normals = np.asarray(self.normals, dtype=np.float64).reshape(-1, 3)
        if self.labels is not None:
            self.labels = np.asarray(self.labels, dtype=np.int64).reshape(-1)

    # ------------------------------------------------------------------ basics
    def __len__(self) -> int:
        return len(self.points)

    @property
    def has_mesh(self) -> bool:
        return self.mesh_vertices is not None and self.mesh_triangles is not None and len(self.mesh_triangles) > 0

    def copy(self) -> "Scan":
        return copy.deepcopy(self)

    def subset(self, mask: np.ndarray, note: str | None = None) -> "Scan":
        """Return a new scan holding only the points where ``mask`` is True (mesh dropped
        unless every vertex is kept)."""
        mask = np.asarray(mask)
        s = Scan(
            points=self.points[mask],
            colors=None if self.colors is None else self.colors[mask],
            normals=None if self.normals is None else self.normals[mask],
            labels=None if self.labels is None else self.labels[mask],
            name=self.name,
            source=self.source,
            metric=self.metric,
            ground_z=self.ground_z,
            metadata=dict(self.metadata),
            history=list(self.history),
        )
        if self.has_mesh:
            s.mesh_vertices, s.mesh_triangles, s.mesh_colors = _crop_mesh_to_bounds(self, s.points)
        if note:
            s.history.append(note)
        return s

    def transform(self, T: np.ndarray) -> None:
        """Apply a 4x4 rigid or similarity transform in place."""
        T = np.asarray(T, dtype=np.float64)
        R, t = T[:3, :3], T[:3, 3]
        self.points = self.points @ R.T + t
        if self.normals is not None:
            # remove the uniform scale from R before rotating normals
            s = np.cbrt(abs(np.linalg.det(R))) or 1.0
            self.normals = self.normals @ (R / s).T
        if self.mesh_vertices is not None:
            self.mesh_vertices = self.mesh_vertices @ R.T + t

    def scale(self, factor: float, mark_metric: bool = True, note: str = "") -> None:
        T = np.eye(4)
        T[:3, :3] *= factor
        self.transform(T)
        if self.ground_z is not None:
            self.ground_z *= factor
        if mark_metric:
            self.metric = True
        self.history.append(note or f"scaled x{factor:.6g}")

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        return self.points.min(axis=0), self.points.max(axis=0)

    # --------------------------------------------------------------- open3d
    def to_o3d(self):
        import open3d as o3d

        pc = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(self.points))
        if self.colors is not None:
            pc.colors = o3d.utility.Vector3dVector(self.colors)
        if self.normals is not None:
            pc.normals = o3d.utility.Vector3dVector(self.normals)
        return pc

    def mesh_to_o3d(self):
        import open3d as o3d

        if not self.has_mesh:
            return None
        m = o3d.geometry.TriangleMesh(
            o3d.utility.Vector3dVector(self.mesh_vertices), o3d.utility.Vector3iVector(self.mesh_triangles)
        )
        if self.mesh_colors is not None:
            m.vertex_colors = o3d.utility.Vector3dVector(self.mesh_colors)
        return m

    @classmethod
    def from_o3d(cls, pc, **kw) -> "Scan":
        pts = np.asarray(pc.points)
        cols = np.asarray(pc.colors) if pc.has_colors() else None
        nrm = np.asarray(pc.normals) if pc.has_normals() else None
        return cls(points=pts, colors=cols, normals=nrm, **kw)

    def ensure_normals(self, radius: float | None = None, k: int = 30) -> None:
        if self.normals is not None and len(self.normals) == len(self.points):
            return
        import open3d as o3d

        pc = self.to_o3d()
        if radius is None:
            radius = 3 * median_spacing(self.points)
        pc.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=radius, max_nn=k))
        pc.orient_normals_to_align_with_direction(np.array([0.0, 0.0, 1.0]))
        self.normals = np.asarray(pc.normals)


def median_spacing(points: np.ndarray, sample: int = 5000) -> float:
    """Median nearest-neighbour distance (estimated from a sample)."""
    from scipy.spatial import cKDTree

    pts = np.asarray(points)
    if len(pts) < 2:
        return 1.0
    tree = cKDTree(pts)
    idx = np.random.default_rng(0).choice(len(pts), size=min(sample, len(pts)), replace=False)
    d, _ = tree.query(pts[idx], k=2)
    m = float(np.median(d[:, 1]))
    return m if m > 0 else 1e-6


def cluster_eps(points: np.ndarray, min_points: int = 10, factor: float = 1.5, sample: int = 5000) -> float:
    """DBSCAN radius that keeps a surface connected: ``factor`` x the median distance to the
    ``min_points``-th neighbour (robust for random, non-grid sampling)."""
    from scipy.spatial import cKDTree

    pts = np.asarray(points)
    if len(pts) <= min_points:
        return 1.0
    idx = np.random.default_rng(0).choice(len(pts), size=min(sample, len(pts)), replace=False)
    d, _ = cKDTree(pts).query(pts[idx], k=min_points + 1)
    return float(np.median(d[:, -1]) * factor)


def _crop_mesh_to_bounds(scan: Scan, kept_points: np.ndarray):
    """Keep mesh triangles whose vertices all lie near a kept point."""
    from scipy.spatial import cKDTree

    if len(kept_points) == 0:
        return None, None, None
    tol = 2.5 * median_spacing(scan.points)
    d, _ = cKDTree(kept_points).query(scan.mesh_vertices, k=1, distance_upper_bound=tol)
    vkeep = np.isfinite(d)
    tkeep = vkeep[scan.mesh_triangles].all(axis=1)
    if not tkeep.any():
        return None, None, None
    tris = scan.mesh_triangles[tkeep]
    used = np.unique(tris)
    remap = -np.ones(len(scan.mesh_vertices), dtype=np.int64)
    remap[used] = np.arange(len(used))
    cols = None if scan.mesh_colors is None else scan.mesh_colors[used]
    return scan.mesh_vertices[used], remap[tris], cols
