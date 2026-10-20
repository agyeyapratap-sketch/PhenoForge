"""Gaussian-splat PLY extras (radius / alpha) and the Splat viewer mode."""

import os

import numpy as np
import pytest

from phenoforge import io, pipeline
from phenoforge.scan import Scan


def _write_splat_ply(path, n: int = 400, seed: int = 0):
    from plyfile import PlyData, PlyElement

    rng = np.random.default_rng(seed)
    names = ["x", "y", "z", "f_dc_0", "f_dc_1", "f_dc_2", "opacity",
             "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3"]
    v = np.zeros(n, dtype=[(k, "f4") for k in names])
    v["x"], v["y"], v["z"] = rng.uniform(-0.05, 0.05, (3, n))
    v["f_dc_1"] = 1.0  # greenish
    v["opacity"] = np.where(np.arange(n) % 4 == 0, -5.0, 3.0)  # every 4th splat ~transparent
    for k in ("scale_0", "scale_1", "scale_2"):
        v[k] = np.log(0.002)
    v["scale_0"][:10] = np.log(0.0005)  # a few flat splats
    v["rot_0"] = 1.0
    PlyData([PlyElement.describe(v, "vertex")]).write(str(path))
    return v


def test_load_splat_extras(tmp_path):
    v = _write_splat_ply(tmp_path / "s.ply")
    s = io.load(tmp_path / "s.ply")
    assert len(s) == 300  # low-opacity quarter dropped
    assert set(s.extras) >= {"splat_radius", "splat_alpha"}
    for a in s.extras.values():
        assert len(a) == len(s)
    assert np.all(s.extras["splat_alpha"] > 0.9)
    assert np.allclose(np.median(s.extras["splat_radius"]), 0.002, rtol=1e-3)
    kept = np.asarray(v["opacity"]) > 0
    assert np.allclose(s.points[:, 0], v["x"][kept], atol=1e-6)


def test_subset_scale_transform_extras():
    s = Scan(points=np.random.default_rng(1).random((50, 3)),
             extras={"splat_radius": np.full(50, 0.01), "splat_alpha": np.linspace(0, 1, 50)})
    m = np.arange(50) % 2 == 0
    sub = s.subset(m)
    assert len(sub.extras["splat_alpha"]) == 25
    assert np.allclose(sub.extras["splat_alpha"], s.extras["splat_alpha"][m])
    s.scale(2.0)
    assert np.allclose(s.extras["splat_radius"], 0.02)
    T = np.eye(4)
    T[:3, :3] = 0.5 * np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]])  # rotate + halve
    s.transform(T)
    assert np.allclose(s.extras["splat_radius"], 0.01)
    assert np.allclose(s.extras["splat_alpha"], np.linspace(0, 1, 50))  # non-length extras untouched
    assert s.copy().extras["splat_radius"] is not s.extras["splat_radius"]


def test_extra_ignores_misaligned():
    s = Scan(points=np.zeros((5, 3)), extras={"splat_radius": np.ones(4)})
    assert s.extra("splat_radius") is None
    assert "splat_radius" not in s.subset(np.ones(5, bool)).extras


def test_pipeline_keeps_extras_aligned(tmp_path):
    from phenoforge.synthetic import make_tray

    s, _ = make_tray()
    s.extras["splat_radius"] = np.full(len(s), 0.001)
    s.extras["splat_alpha"] = np.full(len(s), 0.8)
    out, _ = pipeline.run(s, pipeline.Options(vegetation="none", leaves="none"), log=lambda *a: None)
    assert out.extras
    for a in out.extras.values():
        assert len(a) == len(out)


def test_viewer_splat_mode(tmp_path):
    pytest.importorskip("PySide6")
    pytest.importorskip("pyqtgraph.opengl")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtWidgets

    from phenoforge.gui.viewer import CloudViewer

    _write_splat_ply(tmp_path / "s.ply")
    s = io.load(tmp_path / "s.ply")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    v = CloudViewer()
    v.set_scan(s)
    v.set_mode("Splat")
    pos, rgba, size = v.splat_arrays()
    assert len(pos) == len(s) and rgba.shape == (len(s), 4) and np.all(size > 0)
    v.set_point_size(4.0)
    s.extras.clear()  # fallback: radii from point spacing
    v.set_scan(s)
    assert np.all(v.splat_arrays()[2] > 0)
    v.set_auto_orbit(True, 30)
    assert v._orbit_timer.isActive()
    v.set_auto_orbit(False)
    assert not v._orbit_timer.isActive()
    app.processEvents()
