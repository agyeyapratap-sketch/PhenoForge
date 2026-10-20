"""Command line: ``phenoforge <command> ...`` (run ``phenoforge -h`` for the list).

With no command the desktop app starts.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np


def _opts_from_args(a) -> "pipeline.Options":
    from . import pipeline

    opt = pipeline.Options(
        voxel=a.voxel, outliers=not a.no_outliers, align_ground=not a.no_ground, remove_ground=not a.keep_ground,
        y_up=a.y_up, vegetation=a.vegetation, vegetation_threshold=a.veg_threshold,
        aruco_size_m=a.aruco_mm / 1000.0 if a.aruco_mm else 0.0, aruco_dict=a.aruco_dict,
        aruco_ids=[int(x) for x in a.aruco_ids.split(",")] if a.aruco_ids else None,
        manual_scale=a.scale, plants=a.plants, expected_plants=a.expected,
        grid_rows=a.grid[0] if a.grid else 0, grid_cols=a.grid[1] if a.grid else 0,
        grid_pitch_m=a.pitch_mm / 1000.0 if a.pitch_mm else 0.0, leaves=a.leaves,
        largest_cluster=a.largest_cluster, heads=a.heads, tillers=a.tillers, objects=a.objects, assume_metric=a.metric)
    if a.preset:
        # the preset fills in every option left at its default
        base = pipeline.Options()
        for k, v in pipeline.PRESETS[_preset_name(a.preset)][1].items():
            if getattr(opt, k) == getattr(base, k):
                setattr(opt, k, v)
    return opt


def _preset_name(text: str) -> str:
    from .pipeline import PRESETS

    hits = [n for n in PRESETS if text.lower() in n.lower()]
    if len(hits) != 1:
        sys.exit(f"--preset '{text}' matches {len(hits)} presets; choose one of:\n  " + "\n  ".join(PRESETS))
    return hits[0]


def _inputs(paths) -> list[Path]:
    """Expand folders into the scans inside them; an .ftscan or package folder is one scan."""
    from . import io

    files = []
    for f in paths:
        p = Path(f)
        if p.is_dir() and p.suffix.lower() != ".ftscan" and not (p / "manifest.json").exists():
            files += sorted(x for x in p.iterdir() if x.suffix.lower() in io.SUPPORTED)
        else:
            files.append(p)
    return files


def _add_analysis_args(p):
    p.add_argument("--preset", default="", help="ready-made settings, e.g. 'iphonotype', 'wheat', 'tray', 'fruit' "
                                                 "(see 'phenoforge presets'); explicit flags still win")
    p.add_argument("--out", default="phenoforge_results")
    p.add_argument("--voxel", type=float, default=0.0, help="downsample voxel (scan units), 0 = off")
    p.add_argument("--no-outliers", action="store_true")
    p.add_argument("--no-ground", action="store_true", help="do not fit/align the ground plane")
    p.add_argument("--keep-ground", action="store_true", help="align but keep ground points")
    p.add_argument("--y-up", action="store_true", help="input is Y-up (glTF/USDZ from phone apps)")
    p.add_argument("--vegetation", default="exg", choices=["exg", "gli", "vari", "hue", "none"])
    p.add_argument("--veg-threshold", type=float, default=None)
    p.add_argument("--aruco-mm", type=float, default=0.0, help="printed ArUco marker side in mm (enables scaling)")
    p.add_argument("--aruco-dict", default="DICT_4X4_50")
    p.add_argument("--aruco-ids", default="", help="comma-separated IDs to accept, e.g. 0,1,2,3")
    p.add_argument("--scale", type=float, default=0.0, help="manual scale factor")
    p.add_argument("--metric", action="store_true", help="the file is already in metres (LiDAR app export)")
    p.add_argument("--plants", default="single", choices=["single", "watershed", "grid", "dbscan"])
    p.add_argument("--expected", type=int, default=None, help="expected number of plants")
    p.add_argument("--grid", type=int, nargs=2, metavar=("ROWS", "COLS"))
    p.add_argument("--pitch-mm", type=float, default=0.0)
    p.add_argument("--leaves", default="components", choices=["none", "components", "region", "sam"],
                   help="leaf candidates; 'sam' uses the optional AI model (pip install ultralytics)")
    p.add_argument("--heads", action="store_true", help="count wheat heads (spikes), heuristic")
    p.add_argument("--tillers", action="store_true", help="count tillers from stem cross-sections")
    p.add_argument("--objects", action="store_true", help="dimensions of each separate object (fruit, tubers)")
    p.add_argument("--largest-cluster", action="store_true")
    p.add_argument("--save-cloud", action="store_true", help="also write the cleaned, labelled cloud (.ply)")


def cmd_analyse(a):
    from . import io, pipeline

    files = _inputs(a.inputs)
    rows = []
    for f in files:
        print(f"== {f}")
        scan = io.load(f)
        out, res = pipeline.run(scan, _opts_from_args(a))
        files_out = pipeline.save_results(res, a.out, f.stem)
        if a.save_cloud:
            io.save_point_cloud(out, Path(a.out) / f"{f.stem}_clean.ply")
        ids = {k: v for k, v in res.get("package", {}).items() if k in ("plant_id", "genotype", "treatment")}
        rows.append({"scan": f.stem, **ids, **{k: v for k, v in res["plant"].items() if not isinstance(v, list)}})
        print(json.dumps({k: res["plant"][k] for k in ("height_max", "projected_area_m2", "surface_area_m2",
                                                       "hull_volume_m3", "voxel_volume_m3", "head_count", "tiller_count")
                          if k in res["plant"]}, indent=1))
        print("written:", ", ".join(files_out.values()))
    if len(rows) > 1:
        from .phenotype2d import write_csv

        write_csv(Path(a.out) / "all_scans.csv", rows)


def cmd_images(a):
    from . import phenotype2d

    s, b = phenotype2d.batch(a.inputs, a.out, marker_size_mm=a.aruco_mm or None, dictionary=a.aruco_dict,
                             method=a.method, min_blob_px=a.min_blob)
    print("written:", s, b)


def cmd_roots(a):
    from . import phenotype2d, roots

    rows = []
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    inputs = []
    for f in a.inputs:
        p = Path(f)
        if p.suffix.lower() in (".mp4", ".mov", ".avi", ".mkv"):
            frames = roots.extract_frames(p, out / f"{p.stem}_frames", every_n=a.every)
            if a.stitch:
                pano = roots.stitch([phenotype2d.read_image(x) for x in frames])
                pp = out / f"{p.stem}_panorama.png"
                phenotype2d.write_image(pp, pano)
                inputs.append(pp)
            else:
                inputs += [Path(x) for x in frames]
        elif p.is_dir():
            inputs += sorted(x for x in p.iterdir() if x.suffix.lower() in phenotype2d.IMG_EXT)
        else:
            inputs.append(p)
    from .scale import image_mm_per_px

    for f in inputs:
        rgb = phenotype2d.read_image(f)
        mmpp = a.mm_per_px or (image_mm_per_px(rgb, a.aruco_mm)[0] if a.aruco_mm else None)
        m = roots.root_mask(rgb, roots_dark={"auto": None, "dark": True, "light": False}[a.roots])
        t, draw = roots.root_traits(m, mm_per_px=mmpp)
        phenotype2d.write_image(out / f"{f.stem}_roots.png", roots.draw_overlay(rgb, m, draw))
        rows.append({"image": f.name, **t})
        print(f.name, {k: round(v, 2) if isinstance(v, float) else v for k, v in t.items()})
    phenotype2d.write_csv(out / "roots.csv", rows)


def cmd_roots3d(a):
    from . import io, roots3d
    from .phenotype2d import write_csv

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows, root_rows = [], []
    for f in a.inputs:
        f = Path(f)
        print(f"== {f}")
        if a.mode == "ct":
            sol = roots3d.load_volume_stack(f, a.ct_voxel_mm / 1000, invert=a.ct_invert)
            t, _ = roots3d.fibrous_traits(sol)
        else:
            scan = io.load(f)
            if a.aruco_mm or a.scale:
                from . import clean, scale

                if a.aruco_mm:
                    scan, ms = scale.apply_aruco_scale(clean.align_to_ground(scan, remove=False), a.aruco_mm / 1000,
                                                       dictionary=a.aruco_dict)
                    print("ArUco:", ms.summary())
                else:
                    scan = scale.apply_factor(scan, a.scale, "manual")
            if a.mode == "crown":
                opt = roots3d.CrownOptions(voxel=a.voxel_mm / 1000 if a.voxel_mm else 0.0, depth=a.depth,
                                           sectors=a.sectors, core_radius=a.core_mm / 1000 if a.core_mm else 0.0,
                                           weight_kg=a.weight_kg)
                s2, t, ex = roots3d.crown_pipeline(scan, axis=a.axis, green_sheet=not a.no_green, plane=not a.no_plane,
                                                   stem_cut=a.stem_mm / 1000, opt=opt)
                root_rows += [{"scan": f.stem, **r} for r in ex["roots"]]
                if a.save_cloud:
                    io.save_point_cloud(s2, out / f"{f.stem}_crown_labelled.ply")
                    V, F = ex["mesh"]
                    io.save_mesh(V, F, None, out / f"{f.stem}_crown_remesh.ply")
            else:
                s2 = roots3d.orient(scan, a.axis)
                t, _ = roots3d.fibrous_from_scan(s2, voxel=a.voxel_mm / 1000 if a.voxel_mm else 0.0)
        flat = {k: v for k, v in t.items() if not isinstance(v, (list, dict))}
        rows.append({"scan": f.stem, **flat})
        print(json.dumps({k: round(v, 4) if isinstance(v, float) else v for k, v in flat.items() if k.endswith(("cm", "cm2", "cm3", "deg", "percent", "number", "tips"))}, indent=1))
    write_csv(out / "roots3d.csv", rows)
    if root_rows:
        write_csv(out / "roots3d_individual_roots.csv", root_rows)
    print("written:", out / "roots3d.csv")


def cmd_colorcal(a):
    from . import colorcal, phenotype2d

    rgb = phenotype2d.read_image(a.chart)
    meas = colorcal.detect_patches_mcc(rgb)
    if meas is None:
        if not a.corners:
            sys.exit("Chart not detected automatically; pass --corners x1 y1 x2 y2 x3 y3 x4 y4 (TL TR BR BL)")
        meas = colorcal.sample_patches_from_corners(rgb, np.array(a.corners, float).reshape(4, 2))
    ref = colorcal.load_reference(a.reference) if a.reference else colorcal.REFERENCE_SRGB
    corr = colorcal.fit_correction(meas, ref)
    colorcal.save_correction(a.out, corr)
    print(f"RMSE before {corr['rmse_before']:.1f}, after {corr['rmse_after']:.1f} (8-bit); saved {a.out}")
    for img in a.apply or []:
        o = Path(img)
        phenotype2d.write_image(o.with_name(o.stem + "_cc.png"), colorcal.correct_image(phenotype2d.read_image(o), corr["M"]))


def cmd_validate(a):
    from . import validate

    res = validate.compare_csv(a.pred, a.ref, a.key, a.columns.split(",") if a.columns else None)
    print(json.dumps(res, indent=1))
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=2))


def cmd_compare(a):
    from . import compare, io, pipeline, traits

    sa, sb = io.load(a.a), io.load(a.b)
    opt = _opts_from_args(a)
    ca, ra = pipeline.run(sa, opt)
    cb, rb = pipeline.run(sb, opt)
    rows = compare.compare_traits(ra["plant"], rb["plant"])
    for r in rows:
        print(f"{r['trait']:24s} {r['a']:12.5g} -> {r['b']:12.5g}  ({r['change_percent']:+.1f} %)")
    from .phenotype2d import write_csv

    Path(a.out).mkdir(parents=True, exist_ok=True)
    write_csv(Path(a.out) / "comparison.csv", rows)


def cmd_print(a):
    from . import io, pipeline, printexport

    scan = io.load(a.input)
    if not a.raw:
        scan, _ = pipeline.run(scan, _opts_from_args(a))
    info = printexport.export_print_bundle(scan, a.out, name=Path(a.input).stem, n_colours=a.colours,
                                           target_height_mm=a.height_mm or None, method=a.mesh,
                                           depth=a.depth, base_mm=a.base_mm)
    print(json.dumps(info, indent=1))


def cmd_markers(a):
    from .scale import make_marker_sheet

    make_marker_sheet(a.out, a.aruco_dict, range(a.first, a.first + a.count), a.mm, a.dpi)
    print("written:", a.out)


def cmd_reconstruct(a):
    from .reconstruct import run_colmap

    p = run_colmap(a.images, a.out, a.colmap, a.quality)
    print("model:", p)


def cmd_capture(a):
    from . import capture, io

    if a.prepare_only:
        src = Path(a.inputs[0])
        if src.suffix.lower() in capture.VIDEO_EXT:
            rep = capture.video_to_frames(src, a.out, target_frames=a.frames)
        elif a.device == "turntable" or capture.detect_device([src]) == "turntable":
            rep, masks = capture.prepare_turntable(src, a.out)
            print("masks:", masks)
        else:
            rep = capture.prepare_photos(src, a.out, None if a.device == "auto" else a.device)
        print(rep.summary())
        return
    scan, info = capture.import_capture(a.inputs, a.out, None if a.device == "auto" else a.device, a.colmap, a.quality)
    p = Path(a.out) / f"{scan.name}_scan.ply"
    io.save_point_cloud(scan, p)
    print(json.dumps({k: v for k, v in info.items() if k != "rejected"}, indent=1))
    print("scan:", p, "(not metric: scale it with --aruco-mm when analysing)" if not scan.metric else "")


def cmd_presets(a):
    from .pipeline import PRESETS

    for name, (desc, fields) in PRESETS.items():
        print(f"{name}\n    {desc}\n    {fields or '(defaults)'}")


def cmd_info(a):
    from . import ftscan, io

    for f in _inputs(a.inputs):
        scan = io.load(f)
        print(f"== {f}\n{len(scan):,} points{' + mesh' if scan.has_mesh else ''}, "
              f"{'metric' if scan.metric else 'not metric'}, format {scan.metadata.get('format', '?')}")
        info = ftscan.package_info(scan)
        for k, v in {**info, **{f"app_{k}": v for k, v in ftscan.app_traits(scan).items()}}.items():
            print(f"  {k:32s} {v}")


def cmd_receive(a):
    from .handoff import serve_forever

    serve_forever(a.inbox, port=a.port, token=a.token or None)


def cmd_heads_train(a):
    from . import heads

    yaml = Path(a.data)
    if yaml.is_dir():
        yaml = heads.make_dataset_yaml(yaml / "images", yaml / "labels", yaml / "dataset.yaml")
    print("model:", heads.train_detector(yaml, a.out, epochs=a.epochs, model=a.model, imgsz=a.imgsz))


def cmd_heads_detect(a):
    from . import heads

    rows = heads.detect_heads_images(a.inputs, a.weights, a.out, conf=a.conf)
    print(f"{len(rows)} image(s), {sum(r['head_count'] for r in rows)} heads; written to {a.out}")


def cmd_rootvideo(a):
    from . import narrate, phenotype2d

    imgs = []
    for f in a.inputs:
        p = Path(f)
        imgs += sorted(x for x in p.iterdir() if x.suffix.lower() in phenotype2d.IMG_EXT) if p.is_dir() else [p]
    info = narrate.make_root_video(imgs, a.out, mm_per_px=a.mm_per_px, aruco_mm=a.aruco_mm,
                                   roots_dark={"auto": None, "dark": True, "light": False}[a.roots],
                                   seconds_per_image=a.seconds, narrate=not a.silent, title=a.title)
    print(json.dumps(info, indent=1, default=str))


def cmd_scale_evidence(a):
    from .videoevidence import video_scale_evidence

    _, summary = video_scale_evidence(a.video, a.mm, dictionary=a.aruco_dict, every_n=a.every, out_dir=a.out)
    print(json.dumps(summary, indent=1, default=str))


def cmd_framecheck(a):
    from . import framecheck, io
    from .phenotype2d import write_csv, write_image

    scan = io.load(a.package)
    rows, summary = framecheck.compare_package(scan, max_frames=a.frames)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "frame_check.csv", rows)
    frames = framecheck.load_frames(scan.metadata.get("package", a.package))
    for r in sorted(rows, key=lambda r: r.get("iou", 0))[:3]:  # overlays of the worst frames
        fr = next((f for f in frames if f["name"] == r["name"]), None)
        if fr is not None:
            write_image(out / f"overlay_{Path(fr['name']).stem}.png", framecheck.compare_frame(scan, fr)["overlay"])
    print(json.dumps(summary, indent=1, default=str))


def cmd_demo(a):
    from . import io, synthetic

    s, truth = synthetic.make_tray(head=True)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    io.save_point_cloud(s, a.out)
    print(f"wrote {a.out}; ArUco DICT_4X4_50 markers of 50 mm; true scale factor {truth['unknown_scale']}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="phenoforge", description="Open-source 3D plant phenotyping")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("analyse", help="3D traits for scans (files or folders)")
    p.add_argument("inputs", nargs="+")
    _add_analysis_args(p)
    p.set_defaults(fn=cmd_analyse)

    p = sub.add_parser("images", help="2D canopy phenotyping of photos")
    p.add_argument("inputs", nargs="+")
    p.add_argument("--out", default="phenoforge_images")
    p.add_argument("--aruco-mm", type=float, default=0.0)
    p.add_argument("--aruco-dict", default="DICT_4X4_50")
    p.add_argument("--method", default="exg", choices=["exg", "hsv"])
    p.add_argument("--min-blob", type=int, default=200)
    p.set_defaults(fn=cmd_images)

    p = sub.add_parser("roots", help="root traits from images or videos")
    p.add_argument("inputs", nargs="+")
    p.add_argument("--out", default="phenoforge_roots")
    p.add_argument("--mm-per-px", type=float, default=None)
    p.add_argument("--aruco-mm", type=float, default=0.0)
    p.add_argument("--roots", default="auto", choices=["auto", "dark", "light"])
    p.add_argument("--every", type=int, default=10, help="keep every Nth video frame")
    p.add_argument("--stitch", action="store_true", help="stitch video frames into one panorama")
    p.set_defaults(fn=cmd_roots)

    p = sub.add_parser("roots3d", help="3D root traits: root crowns (cassava-style), fibrous systems, CT stacks")
    p.add_argument("inputs", nargs="+")
    p.add_argument("--mode", default="crown", choices=["crown", "fibrous", "ct"])
    p.add_argument("--out", default="phenoforge_roots3d")
    p.add_argument("--axis", default="z", help="direction from roots to stem: z,-z,x,-x,y,-y or pca")
    p.add_argument("--stem-mm", type=float, default=0.0, help="length of stem stub to cut off the top")
    p.add_argument("--no-green", action="store_true", help="do not remove a green background sheet")
    p.add_argument("--no-plane", action="store_true", help="do not remove a flat background plane")
    p.add_argument("--aruco-mm", type=float, default=0.0)
    p.add_argument("--aruco-dict", default="DICT_4X4_50")
    p.add_argument("--scale", type=float, default=0.0)
    p.add_argument("--voxel-mm", type=float, default=0.0, help="0 = auto")
    p.add_argument("--depth", type=int, default=8, help="remesh octree depth for the auto voxel")
    p.add_argument("--sectors", type=int, default=1, help="1 = whole crown, 2 = split in half as in the paper")
    p.add_argument("--core-mm", type=float, default=0.0, help="crown core radius, 0 = auto")
    p.add_argument("--weight-kg", type=float, default=0.0, help="fresh root weight for root density")
    p.add_argument("--ct-voxel-mm", type=float, default=0.1)
    p.add_argument("--ct-invert", action="store_true", help="roots are darker than the background")
    p.add_argument("--save-cloud", action="store_true")
    p.set_defaults(fn=cmd_roots3d)

    p = sub.add_parser("colorcal", help="fit a colour correction from a colour-checker photo")
    p.add_argument("chart")
    p.add_argument("--out", default="colour_correction.json")
    p.add_argument("--corners", type=float, nargs=8)
    p.add_argument("--reference", help="JSON with 24 sRGB patch values for your chart")
    p.add_argument("--apply", nargs="*", help="images to correct")
    p.set_defaults(fn=cmd_colorcal)

    p = sub.add_parser("validate", help="agreement between predicted and reference CSVs")
    p.add_argument("pred")
    p.add_argument("ref")
    p.add_argument("--key", default="scan")
    p.add_argument("--columns", default="")
    p.add_argument("--out", default="")
    p.set_defaults(fn=cmd_validate)

    p = sub.add_parser("compare", help="trait change between two scans")
    p.add_argument("a")
    p.add_argument("b")
    _add_analysis_args(p)
    p.set_defaults(fn=cmd_compare)

    p = sub.add_parser("print", help="multi-colour 3D print bundle (3MF, STL per colour, OBJ)")
    p.add_argument("input")
    _add_analysis_args(p)
    p.add_argument("--raw", action="store_true", help="skip cleaning, print the scan as is")
    p.add_argument("--colours", type=int, default=4)
    p.add_argument("--height-mm", type=float, default=120.0, help="0 = true size")
    p.add_argument("--mesh", default="poisson", choices=["poisson", "alpha", "ball", "existing"])
    p.add_argument("--depth", type=int, default=9)
    p.add_argument("--base-mm", type=float, default=2.0)
    p.set_defaults(fn=cmd_print)

    p = sub.add_parser("markers", help="printable ArUco marker sheet")
    p.add_argument("--out", default="aruco_sheet.png")
    p.add_argument("--aruco-dict", default="DICT_4X4_50")
    p.add_argument("--first", type=int, default=0)
    p.add_argument("--count", type=int, default=9)
    p.add_argument("--mm", type=float, default=50.0)
    p.add_argument("--dpi", type=int, default=300)
    p.set_defaults(fn=cmd_markers)

    p = sub.add_parser("reconstruct", help="photogrammetry with COLMAP (if installed)")
    p.add_argument("images")
    p.add_argument("--out", default="colmap_work")
    p.add_argument("--colmap", default=None)
    p.add_argument("--quality", default="medium", choices=["low", "medium", "high", "extreme"])
    p.set_defaults(fn=cmd_reconstruct)

    p = sub.add_parser("capture", help="import from iPhone LiDAR, Android, DSLR or the turntable rig (photos, video, RAW, app exports)")
    p.add_argument("inputs", nargs="+", help="scan file, video, photo folder or photo files")
    p.add_argument("--device", default="auto", choices=["auto", "iphone_lidar", "android", "dslr", "turntable"])
    p.add_argument("--out", default="phenoforge_capture")
    p.add_argument("--prepare-only", action="store_true", help="only make the clean photo/frame folder")
    p.add_argument("--frames", type=int, default=120, help="frames to keep from a video")
    p.add_argument("--colmap", default=None)
    p.add_argument("--quality", default="medium", choices=["low", "medium", "high", "extreme"])
    p.set_defaults(fn=cmd_capture)

    p = sub.add_parser("presets", help="list the ready-made analysis settings")
    p.set_defaults(fn=cmd_presets)

    p = sub.add_parser("info", help="what is in a scan or iPhonotype package (plant ID, light, scale, app traits)")
    p.add_argument("inputs", nargs="+")
    p.set_defaults(fn=cmd_info)

    p = sub.add_parser("receive", help="receive scans from a phone over Wi-Fi (open the printed link or QR on the phone)")
    p.add_argument("--inbox", default="phenoforge_inbox")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--token", default="", help="access code in the link (random if empty)")
    p.set_defaults(fn=cmd_receive)

    p = sub.add_parser("heads-train", help="train a wheat-head detector on your labelled photos (needs: pip install ultralytics)")
    p.add_argument("data", help="dataset.yaml, or a folder with images/ and labels/ in YOLO format")
    p.add_argument("--out", default="head_detector")
    p.add_argument("--epochs", type=int, default=100)
    p.add_argument("--model", default="yolov8n.pt")
    p.add_argument("--imgsz", type=int, default=1024)
    p.set_defaults(fn=cmd_heads_train)

    p = sub.add_parser("heads-detect", help="count wheat heads in photos with a trained detector")
    p.add_argument("inputs", nargs="+")
    p.add_argument("--weights", required=True, help="best.pt from heads-train")
    p.add_argument("--out", default="heads_detected")
    p.add_argument("--conf", type=float, default=0.25)
    p.set_defaults(fn=cmd_heads_detect)

    p = sub.add_parser("rootvideo", help="narrated video of a root image time series, with traits per frame")
    p.add_argument("inputs", nargs="+", help="images or a folder, in time order")
    p.add_argument("--out", default="roots_video.mp4")
    p.add_argument("--mm-per-px", type=float, default=None)
    p.add_argument("--aruco-mm", type=float, default=0.0)
    p.add_argument("--roots", default="auto", choices=["auto", "dark", "light"])
    p.add_argument("--seconds", type=float, default=3.0, help="seconds per image")
    p.add_argument("--title", default="")
    p.add_argument("--silent", action="store_true", help="no spoken narration (subtitles only)")
    p.set_defaults(fn=cmd_rootvideo)

    p = sub.add_parser("scale-evidence", help="check that the ArUco scale stayed visible and consistent through a capture video")
    p.add_argument("video")
    p.add_argument("--mm", type=float, required=True, help="printed marker side in mm")
    p.add_argument("--aruco-dict", default="DICT_4X4_50")
    p.add_argument("--every", type=int, default=5)
    p.add_argument("--out", default="scale_evidence")
    p.set_defaults(fn=cmd_scale_evidence)

    p = sub.add_parser("framecheck", help="compare an iPhonotype scan with its own photos (IoU per frame)")
    p.add_argument("package")
    p.add_argument("--frames", type=int, default=12)
    p.add_argument("--out", default="frame_check")
    p.set_defaults(fn=cmd_framecheck)

    p = sub.add_parser("demo", help="write a synthetic tray scan with ArUco markers")
    p.add_argument("--out", default="demo_tray.ply")
    p.set_defaults(fn=cmd_demo)

    sub.add_parser("gui", help="start the desktop app")

    a = ap.parse_args(argv)
    if a.cmd in (None, "gui"):
        from .gui.app import run

        return run()
    a.fn(a)


if __name__ == "__main__":
    main()
