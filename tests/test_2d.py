"""2D phenotyping, roots, colour correction, validation and the workspace library."""

import numpy as np

from phenoforge import colorcal, library, phenotype2d, roots, validate


def _marker_image(mm_per_px=0.5, marker_mm=40.0):
    import cv2

    img = np.full((800, 1000, 3), (90, 70, 50), np.uint8)  # soil
    side = int(round(marker_mm / mm_per_px))
    d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    m = cv2.aruco.generateImageMarker(d, 2, side)
    img[40:60 + side + 20, 40:60 + side + 20] = 255
    img[60:60 + side, 60:60 + side] = m[..., None]
    # two green 'plants': discs of radius 60 and 40 px
    cv2.circle(img, (500, 400), 60, (40, 160, 40), -1)
    cv2.circle(img, (800, 400), 40, (40, 160, 40), -1)
    return img


def test_image_analysis_with_aruco_scale():
    img = _marker_image()
    summ, blobs, mask, ov = phenotype2d.analyse_image(img, marker_size_mm=40.0)
    assert summ["n_blobs"] == 2
    assert abs(summ["mm_per_px"] - 0.5) < 0.01
    big = max(b["area_mm2"] for b in blobs)
    assert abs(big - np.pi * 30 ** 2) / (np.pi * 30 ** 2) < 0.05


def test_root_traits_on_drawn_root():
    import cv2

    img = np.full((600, 400, 3), 230, np.uint8)
    cv2.line(img, (200, 50), (200, 550), (40, 40, 40), 3)      # primary, 500 px
    cv2.line(img, (200, 200), (300, 260), (40, 40, 40), 2)     # lateral
    cv2.line(img, (200, 350), (110, 400), (40, 40, 40), 2)     # lateral
    m = roots.root_mask(img)
    t, draw = roots.root_traits(m, mm_per_px=0.1)
    assert abs(t["primary_length_px"] - 500) < 25
    assert t["n_laterals"] == 2
    assert abs(t["primary_length_mm"] - 50) < 2.5


def test_colour_correction_recovers_reference():
    ref = colorcal.REFERENCE_SRGB
    lin = colorcal.srgb_to_linear(ref)
    M_true = np.array([[0.8, 0.1, 0.0, 0.02], [0.05, 0.9, 0.05, 0.0], [0.0, 0.1, 0.7, 0.01]])
    measured = colorcal.linear_to_srgb(colorcal.apply_linear(lin, M_true)) * 255
    corr = colorcal.fit_correction(measured)
    assert corr["rmse_after"] < 1.5 < corr["rmse_before"]


def test_agreement_metrics():
    x = np.arange(20, dtype=float)
    a = validate.agreement(x * 1.1 + 1, x)
    assert abs(a["slope"] - 1.1) < 1e-9 and abs(a["calib_a"] - 1 / 1.1) < 1e-9
    mm = validate.mask_metrics(np.eye(4, dtype=bool), np.eye(4, dtype=bool))
    assert mm["iou"] == 1.0


def test_workspace(tmp_path):
    f = tmp_path / "a.ply"
    f.write_text("ply\n")
    ws = library.Workspace(tmp_path / "ws")
    ws.create_project("Wheat 2026")
    ws.create_session("Wheat 2026", "2026-10-19")
    rec = ws.import_scan("Wheat 2026", "2026-10-19", f, plant_id="P1")
    assert rec["plant_id"] == "P1"
    ws.save_results("Wheat 2026", "2026-10-19", rec["id"], "traits", {"plant": {"height_max": 0.5}})
    out = ws.export_table(tmp_path / "all.csv")
    assert "height_max" in open(out).read()


def test_capture_prepare_and_video(tmp_path):
    import cv2

    from phenoforge import capture

    rng = np.random.default_rng(0)
    src = tmp_path / "photos"
    src.mkdir()
    base = (rng.random((480, 640, 3)) * 255).astype(np.uint8)
    base = cv2.GaussianBlur(base, (0, 0), 1.0)
    for i in range(8):
        img = np.roll(base, i * 5, axis=1)
        if i == 3:
            img = cv2.GaussianBlur(img, (0, 0), 6)  # one blurred photo
        cv2.imwrite(str(src / f"IMG_{i:03d}.jpg"), img)
    rep = capture.prepare_photos(src, tmp_path / "out", device="android", log=lambda *a: None)
    assert len(rep.kept) == 7 and rep.rejected[0]["file"] == "IMG_003.jpg"
    vid = tmp_path / "walk.avi"
    vw = cv2.VideoWriter(str(vid), cv2.VideoWriter_fourcc(*"MJPG"), 10, (640, 480))
    for i in range(60):
        vw.write(np.roll(base, i * 3, axis=1))
    vw.release()
    rep = capture.video_to_frames(vid, tmp_path / "frames", target_frames=12, log=lambda *a: None)
    assert 10 <= len(rep.kept) <= 13
    assert capture.detect_device([tmp_path / "x.NEF"]) == "dslr"


def test_turntable_masks_hide_static_room(tmp_path):
    import cv2

    from phenoforge import capture

    rng = np.random.default_rng(1)
    room = (rng.random((480, 640, 3)) * 255).astype(np.uint8)
    room = cv2.GaussianBlur(room, (0, 0), 2)
    src = tmp_path / "session"
    src.mkdir()
    for i in range(12):
        img = room.copy()
        a = np.radians(i * 30)
        # the sample: a bar that turns with the table, plus a blob on the platter
        p1 = (int(320 + 120 * np.cos(a)), int(240 + 40 * np.sin(a)))
        p2 = (int(320 - 120 * np.cos(a)), int(240 - 40 * np.sin(a)))
        cv2.line(img, p1, p2, (30, 160, 40), 18)
        cv2.circle(img, (320, 240), 30, (40, 140, 60), -1)
        cv2.imwrite(str(src / f"low_{i:03d}_{i * 30:05.1f}.jpg"), img)
    (src / "turntable.json").write_text("{}")
    assert capture.detect_device([src]) == "turntable"
    rep, masks = capture.prepare_turntable(src, tmp_path / "out", log=lambda *a: None)
    assert len(rep.kept) == 12
    m = cv2.imread(str(masks / "low_000_000.0.jpg.png"), cv2.IMREAD_GRAYSCALE)
    assert m.shape == (480, 640)
    assert m[240, 320] == 255 and m[240, 420] == 255      # sample kept
    assert m[40, 40] == 0 and m[440, 600] == 0            # room ignored
    assert 0.05 < (m > 0).mean() < 0.5
