"""iPhonotype ``.ftscan`` packages: session metadata, light, scale provenance and app traits.

An ``.ftscan`` is a zip (or folder) exported by the iPhonotype iPhone app. :func:`io.load`
already loads its geometry (the Gaussian-splat PLY) and unpacks it into
``scan.metadata["package"]``. This module reads the JSON sidecars around it:

* ``manifest.json``                      plant ID, genotype, treatment, operator, notes, device,
                                         capture times, coverage, light/PAR proxy summary
* ``3dgs/workflow.json``                 scale source and confidence of the splat cloud
* ``logs/native_object_capture.json``    number of photos taken and recommended
* ``analysis/on_device_aggregate_traits.json``  the app's preliminary traits (cm)
* ``logs/imprint_tray_metadata.json``    text the app read in view (label OCR)

Everything is optional: missing files or fields are skipped, so older or newer app
versions still load. Field names are as found in app version 2.3.1.
"""

from __future__ import annotations

import json
from pathlib import Path

# library metadata field -> manifest session field
SESSION_FIELDS = {"plant_id": "plant_id", "genotype": "genotype", "treatment": "treatment",
                  "operator": "operator_name", "notes": "notes"}


def package_dir(scan_or_path) -> Path | None:
    """The unpacked package folder of a loaded scan, or the given folder/zip path itself."""
    p = scan_or_path.metadata.get("package") if hasattr(scan_or_path, "metadata") else scan_or_path
    if not p:
        return None
    p = Path(p)
    if p.is_file():  # a zip: unpack it once through io
        from .io import load

        return package_dir(load(p))
    hits = list(p.rglob("manifest.json"))
    return hits[0].parent if hits else None


def is_ftscan(scan_or_path) -> bool:
    d = package_dir(scan_or_path)
    if d is None:
        return False
    m = _json(d / "manifest.json")
    return "ios" in str(m.get("coordinate_frames", {}).get("source_frame", "")).lower() or "session" in m


def package_info(scan_or_path) -> dict:
    """Flat dict of everything useful in the package (empty if it is not an iPhonotype package)."""
    d = package_dir(scan_or_path)
    if d is None:
        return {}
    m = _json(d / "manifest.json")
    if not m:
        return {}
    sess, dev, qual = m.get("session", {}), m.get("device", {}), m.get("quality", {})
    light = sess.get("environment_light_summary", {})
    wf = _json(d / "3dgs" / "workflow.json")
    cap = _json(d / "logs" / "native_object_capture.json")
    ocr = _json(d / "logs" / "imprint_tray_metadata.json") or m.get("imprint_tray_metadata_info", {})
    info = {
        "source": "iPhonotype",
        **{k: sess.get(v, "") for k, v in SESSION_FIELDS.items()},
        "session_id": sess.get("session_id", ""),
        "started_utc": sess.get("started_at_utc", ""),
        "ended_utc": sess.get("ended_at_utc", ""),
        "capture_seconds": sess.get("duration_seconds"),
        "scan_mode": sess.get("scan_mode", ""),
        "scan_workflow": sess.get("scan_workflow", ""),
        "scan_target": sess.get("scan_target", ""),
        "app_version": dev.get("app_version", ""),
        "device": dev.get("model", ""),
        "ios_version": dev.get("os_version", ""),
        "photos": cap.get("image_count", wf.get("image_count")),
        "photos_recommended": cap.get("recommended_image_count_ideal"),
        "photos_minimum": cap.get("recommended_image_count_min"),
        "coverage_estimate": qual.get("coverage_estimate"),
        "light_lux_mean": light.get("estimated_lux_mean"),
        "light_lux_min": light.get("estimated_lux_min"),
        "light_lux_max": light.get("estimated_lux_max"),
        "par_mean_umol_m2_s": light.get("estimated_par_mean_umol_m2s"),
        "leaf_reflectance_mean_percent": light.get("estimated_leaf_reflectance_mean_percent"),
        "splat_units": wf.get("on_device_splat_geometry_units", ""),
        "scale_source": wf.get("metric_scale_source", ""),
        "scale_confidence": wf.get("metric_scale_confidence"),
        "scale_verified": wf.get("metric_scale_verified"),
        "used_lidar": "lidar" in " ".join(m.get("sensor_provenance", {}).get("primary_sensors", [])).lower(),
        "label_text": " | ".join(o.get("text", "") for o in ocr.get("observations", []) if o.get("confidence", 0) >= 0.5),
        "warnings": "; ".join(qual.get("warnings", [])),
    }
    return {k: v for k, v in info.items() if v not in (None, "")}


def app_traits(scan_or_path) -> dict:
    """The app's on-device traits (aggregate), as reported (cm, cm2, cm3)."""
    d = package_dir(scan_or_path)
    if d is None:
        return {}
    t = _json(d / "analysis" / "on_device_aggregate_traits.json")
    return {k: v for k, v in t.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}


def compare_with_app(plant: dict, app: dict, metric: bool) -> list[dict]:
    """Side-by-side rows of PhenoForge plant traits and the app's traits, in cm units.

    Only comparable pairs are listed. ``plant`` is ``results["plant"]`` from the pipeline.
    """
    if not app:
        return []
    f = 100.0 if metric else float("nan")  # m -> cm only when the scan is metric
    pairs = [  # (label, PhenoForge key, power of the unit, app key)
        ("height (cm)", "height_max", 1, "heightCm"),
        ("width (cm)", "spread_x", 1, "widthCm"),
        ("depth (cm)", "spread_y", 1, "depthCm"),
        ("convex hull volume (cm3)", "hull_volume_m3", 3, "hullVolumeCm3"),
        ("convex hull surface (cm2)", "hull_surface_m2", 2, "hullSurfaceCm2"),
        ("footprint (cm2)", "footprint_hull_m2", 2, "footprintCm2"),
        ("projected / canopy area (cm2)", "projected_area_m2", 2, "canopyCoverCm2"),
        ("greenness ExG", "exg_mean", 0, "plantGreennessExG"),
    ]
    rows = []
    for label, pk, power, ak in pairs:
        if pk not in plant or ak not in app:
            continue
        pf = plant[pk] * (f ** power if power else 1.0)
        rows.append({"trait": label, "PhenoForge": pf, "iPhonotype app": app[ak],
                     "difference_percent": 100 * (pf - app[ak]) / app[ak] if app[ak] else float("nan")})
    return rows


def _json(p: Path) -> dict:
    try:
        return json.loads(Path(p).read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {}
