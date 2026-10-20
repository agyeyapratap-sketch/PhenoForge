"""Multi-view SAM leaf instances, tested with a fake segmenter (no torch needed)."""

import numpy as np
import pytest

from phenoforge import leafsam, traits
from phenoforge.scan import Scan

N_LEAVES = 5


def make_plant(seed=0, per_leaf=3000):
    """Five elliptical, tilted leaves radiating from a stem at different heights."""
    rng = np.random.default_rng(seed)
    pts, cols, truth = [], [], []
    for k in range(N_LEAVES):
        az = 2 * np.pi * k / N_LEAVES
        # uniform samples in an ellipse (half-length 0.07, half-width 0.03)
        r = np.sqrt(rng.random(per_leaf))
        t = 2 * np.pi * rng.random(per_leaf)
        u, w = 0.07 * r * np.cos(t), 0.03 * r * np.sin(t)
        tilt = np.radians(15 + 5 * k)
        radial = 0.14 + u * np.cos(tilt)
        z = 0.10 + 0.05 * k + u * np.sin(tilt)
        x = radial * np.cos(az) - w * np.sin(az)
        y = radial * np.sin(az) + w * np.cos(az)
        pts.append(np.c_[x, y, z])
        g = 0.45 + 0.08 * k
        cols.append(np.clip(np.c_[np.full(per_leaf, 0.15), np.full(per_leaf, g), np.full(per_leaf, 0.12)]
                            + rng.normal(0, 0.02, (per_leaf, 3)), 0, 1))
        truth.append(np.full(per_leaf, k))
    ns = 800
    zs = rng.random(ns) * 0.32
    ts = 2 * np.pi * rng.random(ns)
    pts.append(np.c_[0.005 * np.cos(ts), 0.005 * np.sin(ts), zs])
    cols.append(np.tile([0.35, 0.45, 0.2], (ns, 1)))
    truth.append(np.full(ns, -1))
    return Scan(points=np.vstack(pts), colors=np.vstack(cols), metric=True), np.concatenate(truth)


def fake_segmenter(rgb):
    """Connected components of non-background pixels, plus a whole-image mask that must be
    discarded as background-sized."""
    from skimage.measure import label

    fg = np.any(rgb != np.array(leafsam.BACKGROUND, np.uint8), axis=-1)
    lab = label(fg, connectivity=1)
    masks = [lab == i for i in range(1, lab.max() + 1) if (lab == i).sum() > 20]
    return masks + [np.ones(fg.shape, bool)]


@pytest.fixture(scope="module")
def plant():
    return make_plant()


def test_render_views_shapes(plant):
    scan, _ = plant
    views = leafsam.render_views(scan, n_views=4, image_size=256)
    assert len(views) == 4 and views[0]["name"] == "top"
    for v in views:
        assert v["rgb"].shape == (256, 256, 3) and v["rgb"].dtype == np.uint8
        assert v["index"].shape == (256, 256) and v["index"].dtype == np.int32
        idx = v["index"]
        assert idx.max() < len(scan) and (idx >= 0).mean() > 0.05
        # background pixels and only those carry the background colour
        bg = np.all(v["rgb"] == leafsam.BACKGROUND, axis=-1)
        assert np.array_equal(bg, idx < 0)


def test_segment_leaves_recovers_leaves(plant):
    scan, truth = plant
    lab = leafsam.segment_leaves(scan, n_views=6, image_size=512, segmenter=fake_segmenter, log=lambda *a: None)
    assert lab.shape == (len(scan),)
    n_inst = len(np.unique(lab[lab >= 0]))
    assert abs(n_inst - N_LEAVES) <= 1
    used = set()
    for k in range(N_LEAVES):
        m = truth == k
        vals, cnt = np.unique(lab[m], return_counts=True)
        best = vals[np.argmax(cnt)]
        assert best >= 0 and cnt.max() / m.sum() > 0.8
        assert best not in used
        used.add(best)
    rows = traits.component_traits(scan, lab, min_points=30, geodesic=False)
    assert len(rows) == n_inst


def test_whole_plant_mask_is_discarded(plant):
    scan, _ = plant
    lab = leafsam.segment_leaves(scan, n_views=3, image_size=256,
                                 segmenter=lambda rgb: [np.ones(rgb.shape[:2], bool)], log=None)
    assert (lab < 0).all()


def test_available_and_missing_backend(plant, monkeypatch):
    ok, msg = leafsam.available()
    assert isinstance(ok, bool) and isinstance(msg, str)
    monkeypatch.setattr(leafsam, "available", lambda: (False, leafsam.INSTALL_HINT))
    with pytest.raises(RuntimeError, match="pip install ultralytics"):
        leafsam.segment_leaves(plant[0], segmenter=None)
