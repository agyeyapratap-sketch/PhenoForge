"""End-to-end checks against synthetic scans with known answers."""

import json
import zipfile

import numpy as np
import pytest

from phenoforge import clean, io, pipeline, printexport, scale, segment, synthetic, traits
from phenoforge.scan import Scan


@pytest.fixture(scope="module")
def tray():
    return synthetic.make_tray(seed=0, unknown_scale=3.7, tilt_deg=12)


def test_aruco_scale_within_half_percent(tray):
    s, truth = tray
    a = clean.align_to_ground(s, remove=False)
    r = scale.scale_from_aruco(a, truth["marker_size"])
    assert r.n_markers == 3
    assert abs(r.factor / truth["unknown_scale"] - 1) < 0.005


def test_full_pipeline_heights_and_instances(tray):
    s, truth = tray
    opt = pipeline.Options(aruco_size_m=0.05, plants="watershed", expected_plants=6, leaves="components")
    out, res = pipeline.run(s, opt, log=lambda *a: None)
    assert out.metric
    assert len(res["plants"]) == 6
    meas = sorted(p["height_max"] for p in res["plants"])
    true = sorted(p["height"] for p in truth["plants"])
    for m, t in zip(meas, true):
        assert abs(m - t) / t < 0.03  # within 3 %
    areas = sorted(p["surface_area_m2"] for p in res["plants"])
    tareas = sorted(p["surface_area"] for p in truth["plants"])
    for m, t in zip(areas, tareas):
        assert abs(m - t) / t < 0.25
    assert len(res["leaf_candidates"]) >= 6


def test_pot_grid_assigns_all_plants(tray):
    s, truth = tray
    opt = pipeline.Options(aruco_size_m=0.05, plants="grid", grid_rows=2, grid_cols=3, grid_pitch_m=0.25, leaves="none")
    out, res = pipeline.run(s, opt, log=lambda *a: None)
    assert len(res["plants"]) == 6
    sizes = [p["n_points"] for p in res["plants"]]
    assert min(sizes) > 0.7 * max(sizes)


def test_ply_roundtrip_and_zip_package(tmp_path, tray):
    s, _ = tray
    small = s.subset(np.arange(len(s)) % 50 == 0)
    small.labels = np.arange(len(small)) % 3
    p = tmp_path / "scan.ply"
    io.save_point_cloud(small, p)
    back = io.load(p)
    assert len(back) == len(small)
    assert back.colors is not None
    z = tmp_path / "pkg.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.write(p, "data/scan.ply")
        zf.writestr("meta.json", json.dumps({"plant": "A1"}))
    pk = io.load(z)
    assert len(pk) == len(small)
    assert pk.metadata["sidecars"]["meta.json"]["plant"] == "A1"


def test_gaussian_splat_ply(tmp_path):
    from plyfile import PlyData, PlyElement

    n = 1000
    a = np.zeros(n, dtype=[("x", "f4"), ("y", "f4"), ("z", "f4"), ("f_dc_0", "f4"), ("f_dc_1", "f4"),
                           ("f_dc_2", "f4"), ("opacity", "f4")])
    a["x"] = np.random.rand(n)
    a["f_dc_1"] = 1.0
    a["opacity"] = np.where(np.arange(n) < 800, 5.0, -5.0)
    p = tmp_path / "splat.ply"
    PlyData([PlyElement.describe(a, "vertex")]).write(str(p))
    s = io.load(p)
    assert len(s) == 800
    assert s.colors[:, 1].mean() > s.colors[:, 0].mean()


def test_mesh_import_and_mesh_area(tmp_path):
    import trimesh

    box = trimesh.creation.box(extents=(0.1, 0.2, 0.3))
    p = tmp_path / "box.obj"
    box.export(p)
    s = io.load(p, mesh_samples=20000)
    assert s.has_mesh
    assert abs(traits.surface_area(s) - box.area) < 1e-6
    assert abs(traits.compute_traits(s)["hull_volume_m3"] - box.volume) / box.volume < 0.02


def test_point_density_area_flat_square():
    rng = np.random.default_rng(1)
    P = np.column_stack([rng.random(40000) * 0.2, rng.random(40000) * 0.1, rng.normal(0, 0.0002, 40000)])
    a = traits.point_density_area(P)
    assert abs(a - 0.02) / 0.02 < 0.08


def test_print_bundle(tmp_path, tray):
    s, _ = tray
    a = clean.align_to_ground(s, remove=True)
    plant = clean.keep_vegetation(a)
    plant = plant.subset(np.arange(len(plant)) % 5 == 0)
    info = printexport.export_print_bundle(plant, tmp_path, n_colours=3, depth=7)
    with zipfile.ZipFile(info["files"]["3mf"]) as z:
        assert "3D/3dmodel.model" in z.namelist()
    assert len(info["files"]["stl"]) >= 1


def test_watershed_touching_rosettes():
    rng = np.random.default_rng(0)
    pts = []
    for cx in (0.0, 0.09):  # two rosettes whose leaves overlap
        r = np.sqrt(rng.random(30000)) * 0.055
        t = rng.random(30000) * 2 * np.pi
        z = 0.03 * (1 - r / 0.055) + 0.002
        pts.append(np.column_stack([cx + r * np.cos(t), r * np.sin(t), z]))
    s = Scan(points=np.vstack(pts), metric=True, ground_z=0.0)
    lab = segment.plants_watershed(s, expected=2)
    assert len(np.unique(lab[lab >= 0])) == 2
