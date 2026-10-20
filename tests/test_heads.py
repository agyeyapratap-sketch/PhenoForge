"""Wheat head / tiller counts on synthetic plants, and the optional YOLO detector with a fake model."""

import time
from pathlib import Path

import numpy as np
import pytest

from phenoforge import heads, synthetic

quiet = lambda *a, **k: None  # noqa: E731


@pytest.mark.parametrize("n_tillers,n_heads,seed,metric", [(5, 4, 0, True), (8, 6, 1, True), (3, 3, 2, False),
                                                           (10, 7, 6, True), (6, 2, 3, False)])
def test_heads_and_tillers_on_synthetic_wheat(n_tillers, n_heads, seed, metric):
    t0 = time.time()
    s, tr = synthetic.make_wheat(n_tillers, n_heads, metric=metric, seed=seed)
    assert tr["n_tillers"] == n_tillers and tr["n_heads"] == n_heads
    lab, rows, summ = heads.count_heads(s, log=quiet)
    assert len(lab) == len(s)
    assert abs(summ["head_count"] - n_heads) <= 1
    assert summ["head_count"] == len(rows) == lab.max() + 1
    for r in rows:
        assert {"head_id", "length", "width", "top_height", "centroid_x", "n_points", "mean_r"} <= set(r)
    # head length in metres within 15 %
    L = summ["head_length_mean"] * tr["unknown_scale"]
    assert abs(L / np.mean(tr["head_lengths"]) - 1) < 0.15
    ts, centres = heads.count_tillers(s, log=quiet)
    assert abs(ts["tiller_count"] - n_tillers) <= 1
    assert centres.shape == (ts["tiller_count"], 2)
    if metric:
        assert 0.002 < ts["stem_diameter_mean"] < 0.006
    assert time.time() - t0 < 30


def test_shape_method_without_colour():
    s, tr = synthetic.make_wheat(6, 4, seed=4)
    s.colors = None
    lab, rows, summ = heads.count_heads(s, log=quiet)
    assert summ["method"] == "auto:shape"
    assert abs(summ["head_count"] - 4) <= 1


def test_tiller_band_override():
    s, tr = synthetic.make_wheat(5, 3, seed=7)
    ts, _ = heads.count_tillers(s, band=(0.04, 0.10), log=quiet)
    assert abs(ts["tiller_count"] - 5) <= 1
    assert ts["band_low"] in (0.04, 0.10)


def test_no_heads_on_green_plant():
    s, _ = synthetic.make_wheat(4, 0, seed=3, yellow_leaf_tips=0.5)
    _, rows, summ = heads.count_heads(s, method="colour", log=quiet)
    assert summ["head_count"] == 0 and rows == []


# ------------------------------------------------------------- 2D detector (mocked)
def _make_images(d: Path, n=5):
    from phenoforge.phenotype2d import write_image

    img_dir, lab_dir = d / "photos", d / "annotations"
    img_dir.mkdir()
    lab_dir.mkdir()
    for i in range(n):
        write_image(img_dir / f"p{i}.png", np.full((64, 96, 3), 120, np.uint8))
        if i < n - 1:  # last one is a background image
            (lab_dir / f"p{i}.txt").write_text("0 0.5 0.5 0.2 0.3\n")
    return img_dir, lab_dir


def test_make_dataset_yaml(tmp_path):
    img_dir, lab_dir = _make_images(tmp_path)
    y = heads.make_dataset_yaml(img_dir, lab_dir, tmp_path / "out" / "heads.yaml", val_fraction=0.2)
    text = y.read_text()
    assert "names:" in text and "0: 'head'" in text
    train = (tmp_path / "out" / "heads_train.txt").read_text().split()
    val = (tmp_path / "out" / "heads_val.txt").read_text().split()
    assert len(train) == 4 and len(val) == 1 and not set(train) & set(val)
    # labels were not the ultralytics 'images' -> 'labels' sibling, so a copy was laid out
    root = tmp_path / "out" / "dataset"
    assert len(list((root / "images").glob("*.png"))) == 5
    assert len(list((root / "labels").glob("*.txt"))) == 4
    for p in train + val:
        assert Path(p).exists() and "/dataset/images/" in p


def test_make_dataset_yaml_uses_standard_layout_in_place(tmp_path):
    from phenoforge.phenotype2d import write_image

    (tmp_path / "images").mkdir()
    (tmp_path / "labels").mkdir()
    for i in range(3):
        write_image(tmp_path / "images" / f"a{i}.jpg", np.zeros((8, 8, 3), np.uint8))
        (tmp_path / "labels" / f"a{i}.txt").write_text("0 0.5 0.5 0.1 0.1\n")
    heads.make_dataset_yaml(tmp_path / "images", tmp_path / "labels", tmp_path / "d.yaml")
    assert not (tmp_path / "dataset").exists()
    listed = (tmp_path / "d_train.txt").read_text().split() + (tmp_path / "d_val.txt").read_text().split()
    assert len(listed) == 3 and all("/images/" in p for p in listed)


class _FakeBoxes:
    def __init__(self, xyxy, conf):
        self.xyxy, self.conf = np.asarray(xyxy, float), np.asarray(conf, float)

    def __len__(self):
        return len(self.conf)


class _FakeResult:
    def __init__(self, n):
        self.boxes = _FakeBoxes([[5 + 10 * i, 5, 12 + 10 * i, 30] for i in range(n)], [0.9 - 0.3 * i for i in range(n)])


class FakeYOLO:
    calls: list = []

    def __init__(self, model):
        self.model = str(model)
        FakeYOLO.calls.append(("init", self.model))

    def train(self, **kw):
        FakeYOLO.calls.append(("train", kw))
        w = Path(kw["project"]) / kw["name"] / "weights"
        w.mkdir(parents=True, exist_ok=True)
        (w / "best.pt").write_bytes(b"fake")
        self.trainer = type("T", (), {"best": w / "best.pt"})()

    def predict(self, source, conf, verbose=False):
        FakeYOLO.calls.append(("predict", conf))
        return [_FakeResult(3)]


@pytest.fixture
def fake_yolo(monkeypatch):
    FakeYOLO.calls = []
    monkeypatch.setattr(heads, "detector_available", lambda: (True, "fake"))
    monkeypatch.setattr(heads, "_load_yolo", FakeYOLO)
    return FakeYOLO


def test_train_detector_with_fake_yolo(tmp_path, fake_yolo):
    img_dir, lab_dir = _make_images(tmp_path)
    y = heads.make_dataset_yaml(img_dir, lab_dir, tmp_path / "heads.yaml")
    best = heads.train_detector(y, tmp_path / "runs", epochs=3, model="yolov8s.pt", imgsz=640, log=quiet)
    assert best.exists() and best.name == "best.pt"
    assert fake_yolo.calls[0] == ("init", "yolov8s.pt")
    kw = fake_yolo.calls[1][1]
    assert kw["data"] == str(y) and kw["epochs"] == 3 and kw["imgsz"] == 640


def test_detect_heads_images_with_fake_yolo(tmp_path, fake_yolo):
    img_dir, _ = _make_images(tmp_path, n=2)
    res = heads.detect_heads_images(img_dir, tmp_path / "best.pt", tmp_path / "det", conf=0.5, log=quiet)
    assert len(res) == 2
    # boxes with conf 0.9, 0.6 kept; 0.3 dropped
    assert all(r["head_count"] == 2 and len(r["boxes"][0]) == 5 for r in res)
    assert ("predict", 0.5) in fake_yolo.calls
    out = tmp_path / "det"
    assert (out / "heads.csv").exists() and (out / "head_boxes.csv").exists()
    assert len(list(out.glob("*_heads.png"))) == 2
    assert "head_count" in (out / "heads.csv").read_text()


def test_detector_missing_gives_install_hint(monkeypatch):
    import builtins

    real = builtins.__import__

    def no_ultra(name, *a, **k):
        if name.startswith("ultralytics"):
            raise ImportError(name)
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_ultra)
    ok, msg = heads.detector_available()
    assert not ok and "pip install ultralytics" in msg
    with pytest.raises(RuntimeError, match="ultralytics"):
        heads.train_detector("x.yaml", "out", log=quiet)
