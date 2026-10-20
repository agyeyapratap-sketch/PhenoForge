"""One-call analysis used by the GUI 'Run all' button, the CLI and batch processing."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from . import clean, scale, segment, traits
from .scan import Scan


@dataclass
class Options:
    voxel: float = 0.0                 # 0 = no downsampling (model units, before scaling)
    outliers: bool = True
    align_ground: bool = True
    remove_ground: bool = True
    y_up: bool = False                 # convert Y-up input (glTF/USDZ from phone apps)
    vegetation: str = "exg"            # exg | gli | hue | none
    vegetation_threshold: float | None = None
    aruco_size_m: float = 0.0          # >0 enables ArUco scaling
    aruco_dict: str = "DICT_4X4_50"
    aruco_ids: list[int] | None = None
    manual_scale: float = 0.0          # >0 multiplies coordinates
    assume_metric: bool = False        # the file is already in metres (LiDAR app exports), so report metric units
    plants: str = "single"             # single | watershed | grid | dbscan
    expected_plants: int | None = None
    grid_rows: int = 0
    grid_cols: int = 0
    grid_pitch_m: float = 0.0
    leaves: str = "components"         # none | components | region | sam (AI, optional install)
    leaf_min_points: int = 30
    largest_cluster: bool = False
    heads: bool = False                # wheat head (spike) count, heuristic
    tillers: bool = False              # tiller count from stem cross-sections
    objects: bool = False              # per-object dimensions (fruit, tubers, seeds on a bench)
    extra: dict = field(default_factory=dict)


# Ready-made settings for common jobs: name -> (description, Options fields)
PRESETS: dict[str, tuple[str, dict]] = {
    "Single plant (general)": ("One plant, any scan. Set the scale yourself.", {}),
    "iPhonotype app (.ftscan)": ("Open the .ftscan package. The splat is in metres from the app; check with ArUco if a card is in view.",
                                 {"y_up": False, "plants": "single", "leaves": "components"}),
    "iPhone LiDAR app (PLY / OBJ / USDZ)": ("LiDAR export in metres. Tick Y-up only if the plant lies on its side.",
                                            {"plants": "single", "leaves": "components", "assume_metric": True}),
    "Photos or video with ArUco (Android, DSLR, turntable)": ("Photogrammetry is not metric: scale from 50 mm ArUco markers.",
                                                              {"aruco_size_m": 0.05, "plants": "single"}),
    "Tray of touching plants": ("Separates plants by watershed; enter the number of plants.",
                                {"plants": "watershed", "leaves": "none"}),
    "Bench of pots in a grid": ("Assigns plants to pots; enter rows, columns and pot pitch.", {"plants": "grid", "leaves": "none"}),
    "Wheat: heads and tillers": ("Counts heads (spikes) and tillers. Heuristic: validate against hand counts.",
                                 {"plants": "single", "leaves": "components", "heads": True, "tillers": True, "vegetation": "none"}),
    "Fruit / objects on a bench": ("Dimensions of each separate object; keeps all colours.",
                                   {"plants": "single", "leaves": "none", "vegetation": "none", "objects": True}),
}


def preset_options(name: str, **overrides) -> "Options":
    """Options for a named preset, with any fields overridden."""
    return Options(**{**PRESETS[name][1], **overrides})


def run(scan: Scan, opt: Options, log=print) -> tuple[Scan, dict]:
    s = scan
    res: dict = {"options": asdict(opt)}
    app = {}
    if scan.metadata.get("package"):
        from . import ftscan

        res["package"] = ftscan.package_info(scan)
        app = ftscan.app_traits(scan)
        if res["package"]:
            log(f"iPhonotype package: plant {res['package'].get('plant_id') or '(no ID)'}, "
                f"{res['package'].get('photos', '?')} photos, scale {res['package'].get('scale_source', 'unknown')}")
    if opt.assume_metric and not s.metric and opt.aruco_size_m <= 0 and opt.manual_scale <= 0:
        s = s.copy()
        s.metric = True
        s.history.append("treated as metres (file from a LiDAR app)")
    if opt.y_up:
        s = clean.convert_y_up(s)
    if opt.voxel > 0:
        s = clean.voxel_downsample(s, opt.voxel)
        log(f"downsampled to {len(s)} points")
    if opt.outliers:
        s = clean.remove_statistical_outliers(s)
        log(f"outlier removal -> {len(s)} points")
    if opt.align_ground:
        # keep the ground until after the markers have been measured
        s = clean.align_to_ground(s, remove=False)
        log("ground plane aligned to z = 0")
    if opt.aruco_size_m > 0:
        s, ms = scale.apply_aruco_scale(s, opt.aruco_size_m, dictionary=opt.aruco_dict, allowed_ids=opt.aruco_ids)
        res["scale"] = {"method": "aruco", "factor": ms.factor, "markers": ms.marker_sizes_units,
                        "cv_percent": ms.cv_percent, "rejected": ms.rejected}
        log(f"ArUco: {ms.summary()}")
    elif opt.manual_scale > 0:
        s = scale.apply_factor(s, opt.manual_scale, "manual")
        res["scale"] = {"method": "manual", "factor": opt.manual_scale}
    if opt.align_ground and opt.remove_ground:
        m = s.points[:, 2] > 2.0 * _spacing(s)
        s = s.subset(m, f"removed ground ({np.sum(~m)} points)")
    if opt.vegetation != "none" and s.colors is not None:
        s = clean.keep_vegetation(s, opt.vegetation, opt.vegetation_threshold)
        log(f"vegetation filter -> {len(s)} points")
    if opt.largest_cluster:
        s = clean.largest_clusters(s, keep=max(1, opt.expected_plants or 1))

    res["plant"] = traits.compute_traits(s)
    labels = None
    if opt.plants == "watershed":
        labels = segment.plants_watershed(s, expected=opt.expected_plants)
    elif opt.plants == "dbscan":
        labels = segment.plants_dbscan(s)
    elif opt.plants == "grid" and opt.grid_rows and opt.grid_cols and opt.grid_pitch_m:
        origin = segment.auto_grid_origin(s, opt.grid_rows, opt.grid_cols, opt.grid_pitch_m)
        cen = segment.pot_grid_centres(opt.grid_rows, opt.grid_cols, opt.grid_pitch_m, origin=origin)
        labels = segment.plants_pot_grid(s, cen, max_radius=opt.grid_pitch_m * 0.75)
        res["pot_centres"] = cen.tolist()
    elif opt.plants == "grid":
        log("Pot grid skipped: enter rows, columns and pot pitch")
    if labels is not None:
        labels = segment.order_labels_reading(s, labels)
        s.labels = labels
        rows = []
        for k in np.unique(labels[labels >= 0]):
            t = traits.compute_traits(s.subset(labels == k), ground_z=s.ground_z)
            rows.append({"plant": int(k), **{a: b for a, b in t.items() if not isinstance(b, list)}})
        res["plants"] = rows
        log(f"{len(rows)} plant instance(s)")
    if opt.leaves != "none":
        groups = [np.ones(len(s), bool)] if labels is None else [labels == k for k in np.unique(labels[labels >= 0])]
        leaf_rows = []
        leaf_lab = -np.ones(len(s), int)
        nxt = 0
        for gi, g in enumerate(groups):
            sub = s.subset(g)
            if len(sub) < opt.leaf_min_points:
                continue
            if opt.leaves == "sam":
                from . import leafsam

                ll = leafsam.segment_leaves(sub, min_points=opt.leaf_min_points, log=log)
            elif opt.leaves == "region":
                if len(sub) > 60000:
                    sub = clean.voxel_downsample(sub, _spacing(sub) * 2)
                    g = None
                ll = segment.leaf_candidates_region_growing(sub, min_points=opt.leaf_min_points)
            else:
                ll = segment.leaf_candidates_components(sub, min_points=opt.leaf_min_points)
            for r in traits.component_traits(sub, ll, min_points=opt.leaf_min_points):
                r["plant"] = gi if labels is not None else 0
                r["leaf"] = r.pop("label")
                leaf_rows.append(r)
            if g is not None:
                l2 = np.where(ll >= 0, ll + nxt, -1)
                leaf_lab[np.where(g)[0]] = l2
                nxt = max(nxt, l2.max(initial=-1) + 1)
        res["leaf_candidates"] = leaf_rows
        res["leaf_labels_note"] = ("AI (SAM) leaf instances from rendered views; check them visually" if opt.leaves == "sam"
                                   else "visible leaf candidates; touching leaves may merge")
        if labels is None:
            s.labels = leaf_lab
        s.metadata["leaf_labels"] = leaf_lab
    if opt.heads:
        from . import heads

        head_lab, res["heads"], summary = heads.count_heads(s, log=log)
        s.metadata["head_labels"] = head_lab
        res["plant"].update(summary)
        log(f"heads: {summary.get('head_count', 0)}")
    if opt.tillers:
        from . import heads

        summary, _ = heads.count_tillers(s, log=log)
        res["plant"].update(summary)
        log(f"tillers: {summary.get('tiller_count', '?')}")
    if opt.objects:
        from . import objects

        obj_lab, res["objects"] = objects.object_dimensions(s, log=log)
        s.metadata["object_labels"] = obj_lab
        log(f"{len(res['objects'])} object(s) measured")
    if app:
        from . import ftscan

        res["app_comparison"] = ftscan.compare_with_app(res["plant"], app, s.metric)
    res["history"] = s.history
    res["metric"] = s.metric
    res["units"] = "m, m2, m3" if s.metric else "scan units (not scaled)"
    return s, res


def _spacing(s: Scan) -> float:
    from .scan import median_spacing

    return median_spacing(s.points)


def save_results(res: dict, out_dir, name: str) -> dict:
    from .phenotype2d import write_csv

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files = {}
    p = out / f"{name}_traits.json"
    p.write_text(json.dumps(res, indent=2, default=_jsonable), encoding="utf-8")
    files["json"] = str(p)
    ids = {k: v for k, v in res.get("package", {}).items() if k in ("plant_id", "genotype", "treatment", "operator", "started_utc")}
    write_csv(out / f"{name}_plant.csv", [{"scan": name, **ids, **{k: v for k, v in res["plant"].items() if not isinstance(v, list)}}])
    files["plant_csv"] = str(out / f"{name}_plant.csv")
    for key, suffix in (("plants", "plants"), ("leaf_candidates", "leaves"), ("heads", "heads"), ("objects", "objects"),
                        ("app_comparison", "vs_iphonotype")):
        if res.get(key):
            write_csv(out / f"{name}_{suffix}.csv", [{"scan": name, **{k: v for k, v in r.items() if not isinstance(v, list)}}
                                                     for r in res[key]])
            files[f"{suffix}_csv"] = str(out / f"{name}_{suffix}.csv")
    if res.get("package"):
        write_csv(out / f"{name}_package.csv", [{"scan": name, **res["package"]}])
        files["package_csv"] = str(out / f"{name}_package.csv")
    return files


def _jsonable(o):
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    return str(o)
