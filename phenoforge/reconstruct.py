"""Photogrammetry from photos or video frames using COLMAP, if it is installed.

COLMAP (BSD licence, https://colmap.github.io) ships Windows binaries with CUDA. Point
PhenoForge at ``COLMAP.bat`` / ``colmap.exe`` (or put it on PATH) and this module runs
the automatic reconstructor and returns the fused dense cloud. Without CUDA, COLMAP can
still produce a sparse cloud, which is loaded instead.
Photogrammetry results are not metric: apply ArUco scaling afterwards.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def find_colmap(hint: str | None = None) -> str | None:
    for c in filter(None, [hint, os.environ.get("COLMAP_PATH"), "colmap", "COLMAP.bat", "colmap.exe"]):
        p = shutil.which(c) or (c if Path(c).exists() else None)
        if p:
            return p
    return None


def run_colmap(image_dir, work_dir, colmap: str | None = None, quality: str = "medium",
               dense: bool = True, log=print) -> Path:
    exe = find_colmap(colmap)
    if exe is None:
        raise FileNotFoundError("COLMAP not found. Install it from https://colmap.github.io and set its path in Settings.")
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    cmd = [exe, "automatic_reconstructor", "--workspace_path", str(work), "--image_path", str(image_dir),
           "--quality", quality, "--dense", "1" if dense else "0"]
    log(" ".join(cmd))
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout:
        log(line.rstrip())
    if proc.wait() != 0:
        raise RuntimeError(f"COLMAP exited with code {proc.returncode}")
    fused = sorted(work.glob("dense/*/fused.ply"))
    if fused:
        return fused[0]
    sparse = sorted(work.glob("sparse/*"))
    if sparse:
        out = work / "sparse.ply"
        subprocess.run([exe, "model_converter", "--input_path", str(sparse[0]), "--output_path", str(out),
                        "--output_type", "PLY"], check=True)
        return out
    raise RuntimeError("COLMAP finished but produced no model")
