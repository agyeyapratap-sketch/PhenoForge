import json

import numpy as np
from PIL import Image, ImageDraw

from phenoforge.framecheck import compare_frame, compare_package, load_frames
from phenoforge.objects import object_dimensions
from phenoforge.scan import Scan


def _ellipsoid(n, axes, centre, rng, rot=None):
    d = rng.normal(size=(n, 3))
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    p = d * np.asarray(axes)
    if rot is not None:
        p = p @ rot.T
    return p + centre


def _rot(rng):
    q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
    return q * np.sign(np.linalg.det(q))


def test_object_dimensions_ellipsoids():
    rng = np.random.default_rng(1)
    specs = [((0.05, 0.03, 0.02), (0.0, 0.0, 0.05)),
             ((0.04, 0.04, 0.04), (0.25, 0.0, 0.05)),
             ((0.06, 0.025, 0.015), (0.5, 0.1, 0.05))]
    pts = np.vstack([_ellipsoid(6000, a, c, rng, _rot(rng)) for a, c in specs])
    cols = np.tile([0.8, 0.3, 0.1], (len(pts), 1))
    scan = Scan(points=pts, colors=cols, metric=True, ground_z=0.0)
    labels, rows = object_dimensions(scan, log=lambda *a: None)
    assert len(rows) == 3
    for axes, centre in specs:
        row = min(rows, key=lambda r: np.hypot(r["centroid_x"] - centre[0], r["centroid_y"] - centre[1]))
        got = np.array([row["length"], row["width"], row["thickness"]])
        want = 2 * np.array(axes)
        assert np.all(np.abs(got - want) / want < 0.05), (got, want)
        assert row["hue_deg"] < 30
    sphere = min(rows, key=lambda r: abs(r["centroid_x"] - 0.25))
    assert abs(sphere["sphericity"] - 1) < 0.03
    assert abs(sphere["equiv_diameter"] - 0.08) / 0.08 < 0.05
    flat = min(rows, key=lambda r: abs(r["centroid_x"] - 0.5))
    assert flat["elongation"] > 2 and flat["sphericity"] < sphere["sphericity"]
    assert labels.shape == (len(pts),)


# ----------------------------------------------------------------- framecheck
F, W, H = 500.0, 400, 400
CENTRE, RADIUS = np.array([0.3, 0.2, 0.0]), 0.3  # capture frame (Y-up, as in the package)


def _package(tmp_path, c2w_gl):
    (tmp_path / "images").mkdir()
    img = Image.new("RGB", (W, H), (128, 128, 128))
    # GL camera at z=2 looking down -Z: +X right, +Y up in the image -> v decreases with y
    u = W / 2 + F * CENTRE[0] / 2.0
    v = H / 2 - F * CENTRE[1] / 2.0
    r = F * RADIUS / np.sqrt(4.0 - RADIUS ** 2)
    ImageDraw.Draw(img).ellipse([u - r, v - r, u + r, v + r], fill=(40, 170, 50))
    img.save(tmp_path / "images" / "f0.png")
    meta = {"fl_x": F, "fl_y": F, "cx": W / 2, "cy": H / 2, "w": W, "h": H,
            "frames": [{"file_path": "images/f0.png", "transform_matrix": np.asarray(c2w_gl).tolist()}]}
    (tmp_path / "transforms.json").write_text(json.dumps(meta))
    return tmp_path


def _blob_scan(pkg):
    rng = np.random.default_rng(0)
    pts = _ellipsoid(40000, (RADIUS,) * 3, CENTRE, rng)
    scan = Scan(points=pts, colors=np.tile([0.15, 0.65, 0.2], (len(pts), 1)))
    # mimic io._load_package_dir: Y-up capture frame converted to Z-up on load
    R = np.array([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float)
    scan.transform(R)
    scan.metadata["package_transform"] = R
    scan.metadata["package"] = str(pkg)
    return scan


def test_framecheck_aligned_and_wrong_pose(tmp_path):
    c2w = np.eye(4)
    c2w[2, 3] = 2.0
    pkg = _package(tmp_path, c2w)
    frames = load_frames(pkg)
    assert len(frames) == 1 and frames[0]["w"] == W
    assert np.allclose(frames[0]["c2w"][:3, 2], [0, 0, -1])  # OpenCV +Z forward = GL -Z
    scan = _blob_scan(pkg)
    r = compare_frame(scan, frames[0])
    assert r["iou"] > 0.8, r["iou"]
    assert r["overlay"].dtype == np.uint8 and r["overlay"].shape[0] == H

    bad = dict(frames[0])
    a = np.radians(12)
    Ry = np.array([[np.cos(a), 0, np.sin(a), 0], [0, 1, 0, 0], [-np.sin(a), 0, np.cos(a), 0], [0, 0, 0, 1]])
    bad["c2w"] = frames[0]["c2w"] @ Ry  # camera panned 12 deg about its own centre
    assert compare_frame(scan, bad)["iou"] < 0.3

    rows, summary = compare_package(scan, log=lambda *a: None)
    assert summary["frames_compared"] == 1 and summary["mean_iou"] > 0.8 and "warning" not in summary

    moved = scan.copy()
    T = np.eye(4)
    T[:3, 3] = [5.0, 0.0, -1.0]  # e.g. re-centred / ground-aligned after loading
    moved.transform(T)
    _, s2 = compare_package(moved, log=lambda *a: None)
    assert s2["mean_iou"] < 0.05 and "warning" in s2


def test_framecheck_missing_image(tmp_path):
    c2w = np.eye(4)
    c2w[2, 3] = 2.0
    pkg = _package(tmp_path, c2w)
    (pkg / "images" / "f0.png").unlink()
    scan = _blob_scan(pkg)
    rows, summary = compare_package(scan, log=lambda *a: None)
    assert rows[0]["error"] and summary["frames_compared"] == 0 and "warning" in summary
