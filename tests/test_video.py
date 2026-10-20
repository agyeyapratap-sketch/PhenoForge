import csv
import importlib.util
import re

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from phenoforge.narrate import _ffmpeg_exe, make_root_video
from phenoforge.phenotype2d import write_image
from phenoforge.videoevidence import video_scale_evidence


def _root_image(day: int, size=(360, 300)) -> np.ndarray:
    """Dark branching 'root' on light paper; primary and laterals grow with ``day``."""
    h, w = size
    img = np.full((h, w, 3), 225, np.uint8)
    rng = np.random.default_rng(0)
    img = np.clip(img.astype(int) + rng.integers(-6, 7, img.shape), 0, 255).astype(np.uint8)
    x0, y0 = w // 2, 15
    depth = 60 + 70 * day
    cv2.line(img, (x0, y0), (x0, min(y0 + depth, h - 10)), (40, 30, 20), 3)
    for k in range(day):
        y = y0 + 40 + 45 * k
        if y > h - 20:
            break
        L = 25 + 15 * (day - k)
        side = 1 if k % 2 else -1
        cv2.line(img, (x0, y), (x0 + side * L, y + L // 2), (40, 30, 20), 2)
    return img


def _make_images(tmp_path, n=3):
    paths = []
    for d in range(1, n + 1):
        p = tmp_path / f"day_{d}.png"
        write_image(p, _root_image(d))
        paths.append(str(p))
    return paths


def _count_frames(path) -> int:
    cap = cv2.VideoCapture(str(path))
    n = 0
    while cap.read()[0]:
        n += 1
    cap.release()
    return n


def _check_outputs(res, n):
    assert _count_frames(res["video"]) >= n
    srt = open(res["srt"], encoding="utf-8").read()
    assert len(re.findall(r"^\d+\n\d\d:\d\d:\d\d,\d{3} --> ", srt, re.M)) == n
    with open(res["csv"], encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == n
    return rows


def test_root_video_silent(tmp_path):
    paths = _make_images(tmp_path, 3)
    res = make_root_video(paths, tmp_path / "out" / "roots.mp4", mm_per_px=0.1, roots_dark=True, narrate=False,
                          seconds_per_image=0.5, title="Test box", log=lambda *a: None)
    assert res["narrated"] is False
    rows = _check_outputs(res, 3)
    tot = [float(r["total_length_mm"]) for r in rows]
    assert tot[0] < tot[1] < tot[2]
    assert rows[1]["sentence"].startswith("Day 2: total root length") and "up" in rows[1]["sentence"]


@pytest.mark.skipif(importlib.util.find_spec("pyttsx3") is None or _ffmpeg_exe() is None,
                    reason="pyttsx3 or ffmpeg not available")
def test_root_video_narrated(tmp_path):
    paths = _make_images(tmp_path, 2)
    res = make_root_video(paths, tmp_path / "narr.mp4", mm_per_px=0.1, roots_dark=True, narrate=True,
                          seconds_per_image=0.5, log=lambda *a: None)
    # must never raise; on a headless machine without a voice it falls back to silent
    _check_outputs(res, 2)
    if not res["narrated"]:
        pytest.skip(f"no speech on this machine: {res['note']}")
    assert res["duration_s"] >= 1.0


def test_video_scale_evidence(tmp_path):
    d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    marker_mm, base = 30.0, 120
    path = tmp_path / "capture.mp4"
    W, H, n = 480, 360, 40
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 20, (W, H))
    assert vw.isOpened()
    truth = []
    for i in range(n):
        side = base + (i % 3)  # slight scale change
        truth.append(marker_mm / side)
        frame = np.full((H, W, 3), 255, np.uint8)
        m = cv2.aruco.generateImageMarker(d, 7, side)
        x, y = 60 + 4 * i, 80 + 2 * (i % 10)
        frame[y:y + side, x:x + side] = m[..., None]
        if i >= 30:  # marker leaves the view near the end
            frame[:] = 255
        vw.write(frame)
    vw.release()
    rows, summ = video_scale_evidence(path, marker_mm, every_n=2, out_dir=tmp_path / "ev", log=lambda *a: None)
    assert summ["frames_sampled"] == 20
    assert summ["frames_with_markers"] == 15
    assert summ["marker_ids"] == [7]
    expected = float(np.median(truth[:30]))
    assert abs(summ["median_mm_per_px"] - expected) / expected < 0.02
    assert summ["cv_percent"] < 3
    assert 0.6 < summ["fraction_usable"] <= 0.75
    assert len(summ["sharpest_frames"]) == 6
    from pathlib import Path

    for k in ("csv", "plot", "contact_sheet"):
        assert summ[k] and Path(summ[k]).exists()
