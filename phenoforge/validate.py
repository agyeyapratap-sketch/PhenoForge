"""Validation against ground truth: masks and traits.

* ``mask_metrics``    : IoU, Dice, precision, recall, area error for a predicted vs a
                        reference mask (e.g. benchmark masks from a phenotyping facility).
* ``agreement``       : MAE, RMSE, bias, R^2, Pearson r, Lin's CCC, OLS slope/intercept and
                        Bland-Altman limits for predicted vs reference values.
* ``compare_csv``     : join two CSV files on a key column and run ``agreement`` for each
                        matching numeric column. Optional linear correction is returned so
                        a facility calibration can be applied to later scans.
"""

from __future__ import annotations

import csv

import numpy as np


def mask_metrics(pred: np.ndarray, ref: np.ndarray) -> dict:
    p, r = np.asarray(pred, bool), np.asarray(ref, bool)
    tp = np.sum(p & r)
    fp = np.sum(p & ~r)
    fn = np.sum(~p & r)
    return {
        "iou": float(tp / max(tp + fp + fn, 1)),
        "dice": float(2 * tp / max(2 * tp + fp + fn, 1)),
        "precision": float(tp / max(tp + fp, 1)),
        "recall": float(tp / max(tp + fn, 1)),
        "area_pred_px": int(p.sum()), "area_ref_px": int(r.sum()),
        "area_error_percent": float((p.sum() - r.sum()) / max(r.sum(), 1) * 100),
    }


def agreement(pred, ref) -> dict:
    x = np.asarray(ref, float)
    y = np.asarray(pred, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    n = len(x)
    if n < 2:
        return {"n": int(n)}
    d = y - x
    ss_res = np.sum(d ** 2)
    ss_tot = np.sum((x - x.mean()) ** 2)
    slope, intercept = np.polyfit(x, y, 1)
    r = float(np.corrcoef(x, y)[0, 1]) if np.std(x) > 0 and np.std(y) > 0 else float("nan")
    ccc = 2 * np.cov(x, y, bias=True)[0, 1] / (x.var() + y.var() + (x.mean() - y.mean()) ** 2)
    return {
        "n": int(n), "mae": float(np.mean(np.abs(d))), "rmse": float(np.sqrt(np.mean(d ** 2))),
        "bias": float(d.mean()), "mape_percent": float(np.mean(np.abs(d) / np.maximum(np.abs(x), 1e-12)) * 100),
        "r2": float(1 - ss_res / ss_tot) if ss_tot > 0 else float("nan"), "pearson_r": r,
        "ccc": float(ccc), "slope": float(slope), "intercept": float(intercept),
        "loa_low": float(d.mean() - 1.96 * d.std(ddof=1)), "loa_high": float(d.mean() + 1.96 * d.std(ddof=1)),
        # calibration to map predictions onto the reference scale: ref ~ a * pred + b
        "calib_a": float(np.polyfit(y, x, 1)[0]), "calib_b": float(np.polyfit(y, x, 1)[1]),
    }


def read_csv(path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def compare_csv(pred_csv, ref_csv, key: str, columns: list[str] | None = None,
                ref_columns: dict[str, str] | None = None) -> dict:
    """Join on ``key``; ``ref_columns`` maps prediction column -> reference column name."""
    P = {row[key]: row for row in read_csv(pred_csv)}
    R = {row[key]: row for row in read_csv(ref_csv)}
    keys = sorted(set(P) & set(R))
    if columns is None:
        columns = [c for c in next(iter(P.values())).keys() if c != key]
    ref_columns = ref_columns or {}
    out = {"matched": len(keys), "unmatched_pred": sorted(set(P) - set(R)), "unmatched_ref": sorted(set(R) - set(P))}
    for c in columns:
        rc = ref_columns.get(c, c)
        try:
            y = [float(P[k][c]) for k in keys]
            x = [float(R[k][rc]) for k in keys]
        except (KeyError, ValueError):
            continue
        out[c] = agreement(y, x)
    return out


def plot_agreement(pred, ref, path, title: str = "", units: str = "") -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x, y = np.asarray(ref, float), np.asarray(pred, float)
    a = agreement(y, x)
    fig, ax = plt.subplots(1, 2, figsize=(10, 4.5))
    ax[0].scatter(x, y, s=12)
    lo, hi = min(x.min(), y.min()), max(x.max(), y.max())
    ax[0].plot([lo, hi], [lo, hi], "k--", lw=1)
    ax[0].set_xlabel(f"reference {units}")
    ax[0].set_ylabel(f"predicted {units}")
    ax[0].set_title(f"{title}  R²={a['r2']:.3f}  MAE={a['mae']:.3g}")
    m, d = (x + y) / 2, y - x
    ax[1].scatter(m, d, s=12)
    for v in (a["bias"], a["loa_low"], a["loa_high"]):
        ax[1].axhline(v, ls="--", lw=1, c="k")
    ax[1].set_xlabel("mean")
    ax[1].set_ylabel("predicted - reference")
    ax[1].set_title("Bland-Altman")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
