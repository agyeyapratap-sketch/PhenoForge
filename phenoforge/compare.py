"""Comparing scans: two time points of one plant, or treatment vs control.

``compare_traits`` gives absolute and percent change per trait; ``register`` aligns two scans
(coarse FPFH + RANSAC, refined with ICP) so they can be shown in a synchronised viewer or
differenced point by point (``cloud_distance``).
"""

from __future__ import annotations

import numpy as np

from .scan import Scan, median_spacing


def compare_traits(a: dict, b: dict) -> list[dict]:
    rows = []
    for k, va in a.items():
        vb = b.get(k)
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)) and not isinstance(va, bool):
            d = vb - va
            rows.append({"trait": k, "a": va, "b": vb, "change": d,
                         "change_percent": (d / va * 100) if va else float("nan")})
    return rows


def register(source: Scan, target: Scan, voxel: float | None = None, refine_icp: bool = True):
    """Return the 4x4 transform aligning ``source`` onto ``target`` and the ICP fitness."""
    import open3d as o3d

    if voxel is None:
        voxel = 3 * max(median_spacing(source.points), median_spacing(target.points))
    reg = o3d.pipelines.registration

    def prep(s):
        pc = s.to_o3d().voxel_down_sample(voxel)
        pc.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=2 * voxel, max_nn=30))
        f = reg.compute_fpfh_feature(pc, o3d.geometry.KDTreeSearchParamHybrid(radius=5 * voxel, max_nn=100))
        return pc, f

    ps, fs = prep(source)
    pt, ft = prep(target)
    res = reg.registration_ransac_based_on_feature_matching(
        ps, pt, fs, ft, True, 1.5 * voxel, reg.TransformationEstimationPointToPoint(False), 3,
        [reg.CorrespondenceCheckerBasedOnEdgeLength(0.9), reg.CorrespondenceCheckerBasedOnDistance(1.5 * voxel)],
        reg.RANSACConvergenceCriteria(100000, 0.999))
    T = res.transformation
    fit = res.fitness
    if refine_icp:
        icp = reg.registration_icp(ps, pt, voxel, T, reg.TransformationEstimationPointToPlane())
        T, fit = icp.transformation, icp.fitness
    return np.asarray(T), float(fit)


def cloud_distance(a: Scan, b: Scan) -> np.ndarray:
    """Per-point distance from a to the nearest point of b (growth / loss maps)."""
    from scipy.spatial import cKDTree

    d, _ = cKDTree(b.points).query(a.points)
    return d
