"""Synchronised-video metric evidence: a per-frame audit of the scale reference in a capture.

Purpose: evidence that the scale reference (ArUco marker(s) of known printed size) was
visible, flat and consistent throughout the capture video, so a measurement taken from the
reconstruction or photos can be traced back to frames where the scale was actually seen.

For every ``every_n``-th frame: timestamp, sharpness (variance of the Laplacian), marker ids
detected, apparent marker side in px, mm/px per marker and the frame median, and the marker
skew (longest/shortest side - 1, %; a flat marker seen square-on is ~0). The summary gives
the fraction of frames with markers, the median mm/px and its coefficient of variation, the
fraction of usable frames and the sharpest marker frames. Writes a CSV, a plot of mm/px and
sharpness against time, and a contact sheet of the six sharpest marker frames.
"""

from __future__ import annotations

import heapq
from pathlib import Path

import numpy as np

from .phenotype2d import write_csv, write_image
from .scale import detect_aruco, marker_side_px

SHEET_N = 6


def _skew_pct(c: np.ndarray) -> float:
    s = [np.linalg.norm(c[i] - c[(i + 1) % 4]) for i in range(4)]
    return float(100.0 * (max(s) / max(min(s), 1e-9) - 1.0))


def _plot(rows: list[dict], med: float | None, path: Path) -> None:
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    fig = Figure(figsize=(9, 5), dpi=110)
    FigureCanvasAgg(fig)
    ax1, ax2 = fig.subplots(2, 1, sharex=True)
    t = [r["time_s"] for r in rows]
    tm = [r["time_s"] for r in rows if r["mm_per_px"] != ""]
    v = [r["mm_per_px"] for r in rows if r["mm_per_px"] != ""]
    ax1.plot(tm, v, "o-", ms=3, lw=1, color="#1f77b4", label="frame median")
    if med:
        ax1.axhline(med, color="#444", ls="--", lw=1, label=f"median {med:.4g}")
        ax1.axhspan(med * 0.98, med * 1.02, color="#2ca02c", alpha=0.12, label="+/-2 %")
    ax1.set_ylabel("mm / px")
    ax1.legend(loc="best", fontsize=8)
    ax1.grid(alpha=0.3)
    ax2.plot(t, [r["sharpness"] for r in rows], "-", lw=1, color="#d62728")
    has = [r["time_s"] for r in rows if r["n_markers"]]
    ax2.plot(has, [r["sharpness"] for r in rows if r["n_markers"]], "o", ms=3, color="#d62728",
             label="marker visible")
    ax2.set_ylabel("sharpness (var. Laplacian)")
    ax2.set_xlabel("time (s)")
    ax2.legend(loc="best", fontsize=8)
    ax2.grid(alpha=0.3)
    fig.suptitle("Scale reference through the capture")
    fig.tight_layout()
    fig.savefig(str(path))


def _contact_sheet(tiles: list[tuple], path: Path, tile_w: int = 400) -> None:
    import cv2

    ims = []
    for sharp, idx, t, rgb in tiles:
        h, w = rgb.shape[:2]
        im = cv2.resize(rgb, (tile_w, max(1, int(round(h * tile_w / w)))), interpolation=cv2.INTER_AREA)
        cv2.rectangle(im, (0, 0), (tile_w, 24), (0, 0, 0), -1)
        cv2.putText(im, f"frame {idx}  t={t:.2f}s  sharp={sharp:.0f}", (6, 17),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        ims.append(im)
    th = max(i.shape[0] for i in ims)
    ims = [np.vstack([i, np.full((th - i.shape[0], tile_w, 3), 255, np.uint8)]) for i in ims]
    while len(ims) % 3:
        ims.append(np.full((th, tile_w, 3), 255, np.uint8))
    rows = [np.hstack(ims[k:k + 3]) for k in range(0, len(ims), 3)]
    write_image(path, np.vstack(rows))


def video_scale_evidence(video, marker_mm: float, dictionary: str = "DICT_4X4_50", every_n: int = 5,
                         out_dir=None, log=print) -> tuple[list[dict], dict]:
    """Audit the ArUco scale reference frame by frame through a capture video.

    Evidence that the scale reference was visible, flat and consistent throughout the
    capture: per sampled frame, the timestamp, sharpness, markers seen, apparent marker size,
    skew and mm/px. A frame is *usable* when a marker is detected, sharpness is at least 30 %
    of the median marker-frame sharpness, skew is under 10 % and its mm/px lies within 5 % of
    the capture median. Writes ``<stem>_scale_evidence.csv``, ``..._plot.png`` and
    ``..._sharpest.png`` into ``out_dir`` (default: ``<video stem>_scale_evidence`` beside it).
    Returns (rows, summary).
    """
    import cv2

    video = Path(video)
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    if not np.isfinite(fps) or fps <= 0:
        fps = 30.0
    out = Path(out_dir) if out_dir else video.with_name(video.stem + "_scale_evidence")
    out.mkdir(parents=True, exist_ok=True)
    every_n = max(1, int(every_n))

    rows: list[dict] = []
    best: list[tuple] = []  # min-heap of (sharpness, idx, time, annotated RGB) for the contact sheet
    i = 0
    while True:
        if i % every_n:
            if not cap.grab():
                break
            i += 1
            continue
        ok, frame = cap.read()
        if not ok:
            break
        t = i / fps
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        corners, ids = detect_aruco(gray, dictionary)
        sides = [marker_side_px(c) for c in corners]
        mmpx = [marker_mm / s for s in sides if s > 0]
        skews = [_skew_pct(c) for c in corners]
        row = {"frame": i, "time_s": round(t, 4), "sharpness": round(sharp, 2), "n_markers": len(ids),
               "marker_ids": [int(k) for k in ids],
               "marker_side_px": round(float(np.median(sides)), 3) if sides else "",
               "mm_per_px": float(np.median(mmpx)) if mmpx else "",
               "mm_per_px_each": [f"{int(k)}:{v:.6g}" for k, v in zip(ids, mmpx)],
               "skew_pct": round(float(np.max(skews)), 2) if skews else ""}
        rows.append(row)
        if len(ids):
            key = (sharp, i)
            if len(best) < SHEET_N or key > best[0][:2]:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                cv2.aruco.drawDetectedMarkers(rgb, [c.reshape(1, 4, 2).astype(np.float32) for c in corners],
                                              np.asarray(ids, np.int32).reshape(-1, 1))
                item = (sharp, i, t, rgb)
                if len(best) < SHEET_N:
                    heapq.heappush(best, item)
                else:
                    heapq.heapreplace(best, item)
        i += 1
    cap.release()
    if not rows:
        raise ValueError(f"No frames could be read from {video}")

    marked = [r for r in rows if r["n_markers"]]
    vals = np.array([r["mm_per_px"] for r in marked], float)
    med = float(np.median(vals)) if len(vals) else None
    cv = float(100 * vals.std() / vals.mean()) if len(vals) > 1 else 0.0
    sh_med = float(np.median([r["sharpness"] for r in marked])) if marked else 0.0
    for r in rows:
        r["usable"] = bool(r["n_markers"] and r["sharpness"] >= 0.3 * sh_med and r["skew_pct"] < 10
                           and abs(r["mm_per_px"] - med) <= 0.05 * med)
    best = sorted(best, key=lambda b: -b[0])
    stem = video.stem
    csv_p, plot_p, sheet_p = (out / f"{stem}_scale_evidence.csv", out / f"{stem}_scale_evidence_plot.png",
                              out / f"{stem}_scale_evidence_sharpest.png")
    write_csv(csv_p, rows)
    try:
        _plot(rows, med, plot_p)
    except Exception as e:
        log(f"Plot skipped: {e}")
        plot_p = None
    if best:
        _contact_sheet(best, sheet_p)
    else:
        sheet_p = None
    all_ids = sorted({k for r in marked for k in r["marker_ids"]})
    summary = {
        "video": str(video), "fps": fps, "frames_sampled": len(rows), "every_n": every_n,
        "duration_s": rows[-1]["time_s"], "frames_with_markers": len(marked),
        "fraction_with_markers": len(marked) / len(rows), "marker_ids": all_ids, "marker_mm": marker_mm,
        "median_mm_per_px": med, "cv_percent": cv,
        "median_marker_side_px": float(np.median([r["marker_side_px"] for r in marked])) if marked else None,
        "max_skew_pct": float(max(r["skew_pct"] for r in marked)) if marked else None,
        "usable_frames": sum(r["usable"] for r in rows),
        "fraction_usable": sum(r["usable"] for r in rows) / len(rows),
        "sharpest_frames": [{"frame": b[1], "time_s": round(b[2], 3), "sharpness": round(b[0], 1)} for b in best],
        "csv": str(csv_p), "plot": str(plot_p) if plot_p else None, "contact_sheet": str(sheet_p) if sheet_p else None,
    }
    if med:
        log(f"Scale evidence: markers in {len(marked)}/{len(rows)} sampled frames, "
            f"median {med:.5g} mm/px, CV {cv:.2f}%, usable {100 * summary['fraction_usable']:.0f}%")
    else:
        log(f"Scale evidence: no {dictionary} markers found in {len(rows)} sampled frames")
    return rows, summary
