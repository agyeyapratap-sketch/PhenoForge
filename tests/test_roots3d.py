"""3D root phenotyping on synthetic crowns and fibrous root systems with known answers."""

import numpy as np

from phenoforge import roots3d, synthetic


def test_root_crown_traits():
    s, tr = synthetic.make_root_crown(seed=1, n_roots=6)
    _, T, ex = roots3d.crown_pipeline(s, axis="z", green_sheet=False, plane=False, stem_cut=tr["stem_length"],
                                      log=lambda *a: None)
    assert T["root_number"] == tr["n_roots"]
    assert abs(T["crown_volume_whole_m3"] / tr["crown_volume_fine_voxel"] - 1) < 0.05
    ang = sorted(r["angle_from_vertical_deg"] for r in ex["roots"])
    tang = sorted(r["angle_from_vertical"] for r in tr["roots"])
    assert np.max(np.abs(np.subtract(ang, tang))) < 8
    ln = sorted(r["length_m"] for r in ex["roots"])
    tln = sorted(r["length"] for r in tr["roots"])
    assert np.max(np.abs(np.subtract(ln, tln)) / tln) < 0.15
    assert 0 < T["compactness_percent"] < 100


def test_crown_orientation_from_side():
    s, tr = synthetic.make_root_crown(seed=0, n_roots=5)
    s.transform(np.array([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float))  # laid on its side
    _, T, _ = roots3d.crown_pipeline(s, axis="-y", green_sheet=False, plane=False, stem_cut=tr["stem_length"],
                                     log=lambda *a: None)
    assert T["root_number"] == 5


def test_fibrous_root_length_and_tips():
    s, tr = synthetic.make_fibrous_roots()
    out, _ = roots3d.fibrous_from_scan(s, log=lambda *a: None)
    assert abs(out["total_length_m"] / tr["total_length"] - 1) < 0.15
    assert abs(out["n_tips"] - tr["n_tips"]) <= 3
