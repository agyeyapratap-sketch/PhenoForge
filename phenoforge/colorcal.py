"""Colour normalisation with a 24-patch colour checker.

Detection uses OpenCV's mcc module (opencv-contrib) when available; otherwise give the four
outer corners of the chart (top-left, top-right, bottom-right, bottom-left, patch 1 = dark
skin at top-left in the standard landscape orientation) and patches are sampled on a 6x4 grid.

The correction is an affine 3x4 matrix fitted by least squares in linear RGB, from the
measured patch means to the reference values. The same matrix can be applied to photos and
to scan colours, so greenness indices stay comparable across sessions and lighting.
"""

from __future__ import annotations

import json

import numpy as np

# Published sRGB (D65) values of the 24 patches of the classic colour-checker layout,
# row by row from dark skin to black (BabelColor averages, rounded).
REFERENCE_SRGB = np.array([
    [115, 82, 68], [194, 150, 130], [98, 122, 157], [87, 108, 67], [133, 128, 177], [103, 189, 170],
    [214, 126, 44], [80, 91, 166], [193, 90, 99], [94, 60, 108], [157, 188, 64], [224, 163, 46],
    [56, 61, 150], [70, 148, 73], [175, 54, 60], [231, 199, 31], [187, 86, 149], [8, 133, 161],
    [243, 243, 242], [200, 200, 200], [160, 160, 160], [122, 122, 121], [85, 85, 85], [52, 52, 52],
], float)


def srgb_to_linear(c):
    c = np.asarray(c, float) / 255.0 if np.max(c) > 1.0 else np.asarray(c, float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def detect_patches_mcc(rgb: np.ndarray) -> np.ndarray | None:
    """Return (24, 3) measured sRGB patch means (0-255) or None."""
    import cv2

    if not hasattr(cv2, "mcc"):
        return None
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    det = cv2.mcc.CCheckerDetector_create()
    if not det.process(bgr, cv2.mcc.MCC24, 1):
        return None
    checkers = det.getListColorChecker()
    if not checkers:
        return None
    charts = checkers[0].getChartsRGB()
    # charts rows: per patch per channel (p*3 + ch), column 1 = mean
    vals = np.asarray(charts)[:, 1].reshape(-1, 3)
    return vals[:24]  # already RGB order


def sample_patches_from_corners(rgb: np.ndarray, corners, rows: int = 4, cols: int = 6, inset: float = 0.3) -> np.ndarray:
    """Sample patch means given the chart's 4 outer corners (x, y) in TL, TR, BR, BL order."""
    import cv2

    src = np.asarray(corners, np.float32)
    W, H = cols * 100, rows * 100
    dst = np.array([[0, 0], [W, 0], [W, H], [0, H]], np.float32)
    M = cv2.getPerspectiveTransform(src, dst)
    warp = cv2.warpPerspective(rgb, M, (W, H))
    out = []
    for r in range(rows):
        for c in range(cols):
            y0, y1 = int((r + inset / 2) * 100 + inset * 25), int((r + 1 - inset / 2) * 100 - inset * 25)
            x0, x1 = int((c + inset / 2) * 100 + inset * 25), int((c + 1 - inset / 2) * 100 - inset * 25)
            out.append(warp[y0:y1, x0:x1].reshape(-1, 3).mean(0))
    return np.array(out)


def fit_correction(measured_srgb: np.ndarray, reference_srgb: np.ndarray = REFERENCE_SRGB,
                   exclude_clipped: bool = True) -> dict:
    """Least-squares affine map in linear RGB. Returns {'M': 3x4, 'rmse_before', 'rmse_after', 'used'}."""
    m = srgb_to_linear(measured_srgb)
    r = srgb_to_linear(reference_srgb)
    use = np.ones(len(m), bool)
    if exclude_clipped:
        use &= (np.asarray(measured_srgb).max(1) < 250) & (np.asarray(measured_srgb).min(1) > 3)
    if use.sum() < 6:
        use[:] = True
    A = np.hstack([m[use], np.ones((use.sum(), 1))])
    X, *_ = np.linalg.lstsq(A, r[use], rcond=None)
    M = X.T  # 3x4
    pred = apply_linear(m, M)
    to8 = lambda x: linear_to_srgb(x) * 255
    rb = float(np.sqrt(np.mean((np.asarray(measured_srgb, float) - reference_srgb) ** 2)))
    ra = float(np.sqrt(np.mean((to8(pred) - reference_srgb) ** 2)))
    return {"M": M.tolist(), "rmse_before": rb, "rmse_after": ra, "used": int(use.sum())}


def apply_linear(lin: np.ndarray, M) -> np.ndarray:
    M = np.asarray(M, float)
    return lin @ M[:, :3].T + M[:, 3]


def correct_colors(colors01: np.ndarray, M) -> np.ndarray:
    """Apply to scan colours in [0, 1] (sRGB encoded)."""
    return linear_to_srgb(apply_linear(srgb_to_linear(colors01), M))


def correct_image(rgb: np.ndarray, M) -> np.ndarray:
    f = rgb.reshape(-1, 3).astype(np.float32) / 255.0
    out = correct_colors(f, M)
    return (out.reshape(rgb.shape) * 255 + 0.5).astype(np.uint8)


def save_correction(path, corr: dict) -> None:
    with open(path, "w") as fh:
        json.dump(corr, fh, indent=2)


def load_correction(path) -> dict:
    with open(path) as fh:
        return json.load(fh)


def load_reference(path) -> np.ndarray:
    """A custom chart: JSON list of 24 [r, g, b] (0-255) in the same patch order."""
    with open(path) as fh:
        d = json.load(fh)
    if isinstance(d, dict):
        d = d.get("patches_srgb") or d.get("srgb") or list(d.values())[0]
    return np.asarray(d, float)
