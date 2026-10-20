"""iPhonotype .ftscan packages: orientation, scale, metadata and the comparison with the app."""

import json
import zipfile

import numpy as np
import pytest
from plyfile import PlyData, PlyElement

from phenoforge import ftscan, io, pipeline


def _package(root, height=0.30):
    """A minimal .ftscan folder: a Y-up splat 'plant' (a vertical green column on a brown disc)."""
    rng = np.random.default_rng(0)
    n_plant, n_soil = 6000, 4000
    stem = np.column_stack([rng.normal(0, 0.01, n_plant), rng.uniform(0, height, n_plant), rng.normal(0, 0.01, n_plant)])
    r, a = 0.12 * np.sqrt(rng.uniform(0, 1, n_soil)), rng.uniform(0, 2 * np.pi, n_soil)
    soil = np.column_stack([r * np.cos(a), np.zeros(n_soil), r * np.sin(a)])  # ground is the XZ plane: Y-up
    xyz = np.vstack([stem, soil]).astype(np.float32)
    rgb = np.vstack([np.tile([0.2, 0.6, 0.15], (n_plant, 1)), np.tile([0.45, 0.3, 0.15], (n_soil, 1))])
    dc = (rgb - 0.5) / io.SH_C0
    v = np.zeros(len(xyz), dtype=[(k, "f4") for k in ("x", "y", "z", "f_dc_0", "f_dc_1", "f_dc_2", "opacity",
                                                     "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3")])
    for i, k in enumerate("xyz"):
        v[k] = xyz[:, i]
    for i in range(3):
        v[f"f_dc_{i}"] = dc[:, i]
        v[f"scale_{i}"] = np.log(0.002)
    v["opacity"], v["rot_0"] = 4.0, 1.0
    pkg = root / "S1.ftscan"
    (pkg / "splats").mkdir(parents=True)
    (pkg / "3dgs").mkdir()
    (pkg / "analysis").mkdir()
    PlyData([PlyElement.describe(v, "vertex")]).write(str(pkg / "splats" / "iphone_splat_reconstruction.ply"))
    (pkg / "manifest.json").write_text(json.dumps({
        "coordinate_frames": {"source_frame": "ios_native_object_capture_heif_coordinate_system", "units": "m"},
        "session": {"plant_id": "W123", "genotype": "Scepter", "treatment": "drought", "operator_name": "AP",
                    "environment_light_summary": {"estimated_lux_mean": 600.0, "estimated_par_mean_umol_m2s": 11.0}},
        "device": {"app_version": "2.3.1"}, "quality": {"coverage_estimate": 0.8, "warnings": []}}))
    (pkg / "3dgs" / "workflow.json").write_text(json.dumps({
        "on_device_splat_geometry_units": "meters", "metric_scale_verified": True,
        "metric_scale_source": "embedded_heif_camera_baseline_pairs", "metric_scale_confidence": 0.95, "image_count": 120}))
    (pkg / "analysis" / "on_device_aggregate_traits.json").write_text(json.dumps({"heightCm": height * 100, "widthCm": 4.0}))
    return pkg


@pytest.mark.parametrize("zipped", [False, True])
def test_package_loads_upright_metric_with_metadata(tmp_path, zipped):
    pkg = _package(tmp_path)
    if zipped:
        z = tmp_path / "S1.ftscan.zip"
        with zipfile.ZipFile(z, "w") as f:
            for p in pkg.rglob("*"):
                f.write(p, p.relative_to(tmp_path))
        pkg = z
    scan = io.load(pkg)
    assert scan.metric
    ext = np.ptp(scan.points, axis=0)
    assert ext[2] > 0.25 and ext[2] > ext[1]  # the column now stands along +Z
    info = ftscan.package_info(scan)
    assert info["plant_id"] == "W123" and info["genotype"] == "Scepter" and info["operator"] == "AP"
    assert info["light_lux_mean"] == 600.0 and info["photos"] == 120 and info["scale_verified"] is True


def test_pipeline_reports_package_and_app_comparison(tmp_path):
    scan = io.load(_package(tmp_path, height=0.30))
    out, res = pipeline.run(scan, pipeline.preset_options("iPhonotype app (.ftscan)", leaves="none"), log=lambda *a: None)
    assert res["package"]["plant_id"] == "W123"
    h = next(r for r in res["app_comparison"] if r["trait"].startswith("height"))
    assert abs(h["PhenoForge"] - 30.0) < 1.5  # cm, from metres
    files = pipeline.save_results(res, tmp_path / "out", "S1")
    assert {"package_csv", "vs_iphonotype_csv"} <= set(files)
    assert "W123" in (tmp_path / "out" / "S1_plant.csv").read_text()


def test_presets_are_valid_options():
    for name in pipeline.PRESETS:
        opt = pipeline.preset_options(name)
        assert opt.plants in ("single", "watershed", "grid", "dbscan")
    assert pipeline.preset_options("Wheat: heads and tillers").heads


def test_assume_metric_only_without_other_scaling():
    from phenoforge.scan import Scan

    s = Scan(points=np.random.default_rng(1).uniform(0, 0.3, (3000, 3)))
    opt = dict(vegetation="none", leaves="none", align_ground=False)
    assert not pipeline.run(s, pipeline.Options(**opt), log=lambda *a: None)[0].metric
    assert pipeline.run(s, pipeline.Options(assume_metric=True, **opt), log=lambda *a: None)[0].metric
    assert pipeline.preset_options("iPhone LiDAR app (PLY / OBJ / USDZ)").assume_metric
    assert not s.metric  # the input scan is never changed


def test_non_ios_package_is_not_rotated(tmp_path):
    pkg = _package(tmp_path)
    m = json.loads((pkg / "manifest.json").read_text())
    m["coordinate_frames"]["source_frame"] = "other"
    (pkg / "manifest.json").write_text(json.dumps(m))
    scan = io.load(pkg)
    assert np.ptp(scan.points, axis=0)[1] > 0.25  # left as stored (Y is still the long axis)
    assert "package_transform" not in scan.metadata
