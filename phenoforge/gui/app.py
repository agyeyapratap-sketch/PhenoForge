"""PhenoForge desktop app (PySide6)."""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from .. import __version__
from ..scan import Scan
from .viewer import CloudViewer

APP = "PhenoForge"
SCAN_FILTER = ("Scans (*.ply *.pcd *.xyz *.xyzrgb *.pts *.txt *.csv *.las *.laz *.obj *.glb *.gltf *.stl *.off "
               "*.usdz *.usd *.usdc *.usda *.zip *.ftscan);;All files (*)")
IMG_FILTER = "Images (*.jpg *.jpeg *.png *.tif *.tiff *.bmp);;All files (*)"


# --------------------------------------------------------------------------- workers
class Worker(QtCore.QObject):
    finished = QtCore.Signal(object)
    failed = QtCore.Signal(str)
    log = QtCore.Signal(str)

    def __init__(self, fn, *args, **kw):
        super().__init__()
        self.fn, self.args, self.kw = fn, args, kw

    @QtCore.Slot()
    def run(self):
        try:
            res = self.fn(*self.args, log=self.log.emit, **self.kw) if self._wants_log() else self.fn(*self.args, **self.kw)
            self.finished.emit(res)
        except Exception as e:  # noqa: BLE001 - shown to the user
            self.failed.emit(f"{e}\n\n{traceback.format_exc()}")

    def _wants_log(self):
        import inspect

        try:
            return "log" in inspect.signature(self.fn).parameters
        except (TypeError, ValueError):
            return False


def table_from_rows(table: QtWidgets.QTableWidget, rows: list[dict]):
    table.clear()
    keys: list[str] = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    table.setColumnCount(len(keys))
    table.setRowCount(len(rows))
    table.setHorizontalHeaderLabels(keys)
    for i, r in enumerate(rows):
        for j, k in enumerate(keys):
            v = r.get(k, "")
            if isinstance(v, float):
                v = f"{v:.6g}"
            table.setItem(i, j, QtWidgets.QTableWidgetItem(str(v)))
    hh = table.horizontalHeader()
    hh.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
    hh.setStretchLastSection(len(keys) <= 3)


def kv_rows(d: dict) -> list[dict]:
    return [{"trait": k, "value": v} for k, v in d.items() if not isinstance(v, (list, dict, np.ndarray))]


def image_label(rgb: np.ndarray, max_side: int = 900) -> QtGui.QPixmap:
    rgb = np.ascontiguousarray(rgb)
    h, w = rgb.shape[:2]
    if rgb.ndim == 2:
        q = QtGui.QImage(rgb.data, w, h, w, QtGui.QImage.Format_Grayscale8)
    else:
        q = QtGui.QImage(rgb.data, w, h, 3 * w, QtGui.QImage.Format_RGB888)
    pm = QtGui.QPixmap.fromImage(q.copy())
    return pm.scaled(max_side, max_side, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)


class ImageView(QtWidgets.QScrollArea):
    def __init__(self):
        super().__init__()
        self.lbl = QtWidgets.QLabel("No image")
        self.lbl.setAlignment(QtCore.Qt.AlignCenter)
        self.setWidget(self.lbl)
        self.setWidgetResizable(True)

    def show_rgb(self, rgb):
        self.lbl.setPixmap(image_label(rgb, max(self.width(), self.height(), 600)))


def dspin(val, lo, hi, step=0.1, dec=3, suffix=""):
    w = QtWidgets.QDoubleSpinBox()
    w.setRange(lo, hi)
    w.setDecimals(dec)
    w.setSingleStep(step)
    w.setValue(val)
    if suffix:
        w.setSuffix(suffix)
    return w


def ispin(val, lo, hi):
    w = QtWidgets.QSpinBox()
    w.setRange(lo, hi)
    w.setValue(val)
    return w


def combo(items, current=None):
    w = QtWidgets.QComboBox()
    w.addItems(items)
    if current:
        w.setCurrentText(current)
    return w


# ----------------------------------------------------------------------------- main
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP} {__version__}  ·  open-source 3D plant phenotyping")
        self.resize(1500, 950)
        self.settings = QtCore.QSettings(APP, APP)
        self.raw_scan: Scan | None = None
        self.scan: Scan | None = None
        self.results: dict | None = None
        self.picks: list[np.ndarray] = []
        self.threads: list[QtCore.QThread] = []
        self.workspace = None

        self.tabs = QtWidgets.QTabWidget()
        self.setCentralWidget(self.tabs)
        self._build_log()
        self._build_library()
        self._build_3d_tab()
        self._build_compare_tab()
        self._build_images_tab()
        self._build_roots_tab()
        self._build_roots3d_tab()
        self._build_colour_tab()
        self._build_validation_tab()
        self._build_print_tab()
        self._build_assistant_tab()
        self._build_tools_tab()
        self._build_menu()
        ws = self.settings.value("workspace", str(Path.home() / "PhenoForge"))
        self.open_workspace(ws)
        self.statusBar().showMessage("Open a scan (File > Open) or try Help > Load demo scan")

    # ----------------------------------------------------------------- infrastructure
    def _build_log(self):
        self.log_box = QtWidgets.QPlainTextEdit(readOnly=True)
        self.log_box.setMaximumBlockCount(5000)
        d = QtWidgets.QDockWidget("Log", self)
        d.setWidget(self.log_box)
        d.setObjectName("log")
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, d)

    def log(self, msg: str):
        self.log_box.appendPlainText(str(msg))
        self.statusBar().showMessage(str(msg).splitlines()[0][:200], 8000)

    def run_bg(self, fn, *args, done=None, **kw):
        th = QtCore.QThread(self)
        w = Worker(fn, *args, **kw)
        w.moveToThread(th)
        th.started.connect(w.run)
        w.log.connect(self.log)
        if done:
            w.finished.connect(done)
        w.failed.connect(self._error)
        w.finished.connect(th.quit)
        w.failed.connect(th.quit)
        th.finished.connect(lambda: self.threads.remove(th) if th in self.threads else None)
        th._worker = w  # keep alive
        self.threads.append(th)
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.BusyCursor)
        th.finished.connect(QtWidgets.QApplication.restoreOverrideCursor)
        th.start()

    def _error(self, msg):
        self.log("ERROR: " + msg)
        QtWidgets.QMessageBox.warning(self, APP, msg.split("\n\n")[0])

    def _build_menu(self):
        m = self.menuBar().addMenu("&File")
        m.addAction("&Open scan...", self.open_scan_dialog, QtGui.QKeySequence.Open)
        m.addAction("Open &workspace folder...", self.choose_workspace)
        m.addAction("&Import scan into library...", self.import_into_library)
        m.addSeparator()
        m.addAction("Export cleaned cloud...", self.export_cloud)
        m.addAction("Export results...", self.save_results)
        m.addAction("Export library table (CSV)...", self.export_library_table)
        m.addAction("Save view snapshot...", self.snapshot)
        m.addSeparator()
        m.addAction("&Quit", self.close, QtGui.QKeySequence.Quit)
        h = self.menuBar().addMenu("&Help")
        h.addAction("Load demo scan", self.load_demo)
        h.addAction("Load demo root crown", self.load_demo_crown)
        h.addAction("About", lambda: QtWidgets.QMessageBox.about(
            self, APP, f"<b>{APP} {__version__}</b><br>Open-source 3D plant phenotyping.<br>MIT licence.<br><br>"
                       "Processing: Open3D, OpenCV, NumPy, SciPy, scikit-image, trimesh.<br>GUI: Qt (PySide6), pyqtgraph."))

    # ----------------------------------------------------------------- library
    def _build_library(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        self.ws_label = QtWidgets.QLabel()
        self.ws_label.setWordWrap(True)
        lay.addWidget(self.ws_label)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["Library", "Info"])
        self.tree.itemDoubleClicked.connect(self._tree_open)
        lay.addWidget(self.tree)
        row = QtWidgets.QHBoxLayout()
        for txt, fn in (("Project +", self.new_project), ("Session +", self.new_session), ("Import", self.import_into_library)):
            b = QtWidgets.QPushButton(txt)
            b.clicked.connect(fn)
            row.addWidget(b)
        lay.addLayout(row)
        meta = QtWidgets.QGroupBox("Scan metadata")
        f = QtWidgets.QFormLayout(meta)
        self.meta_fields = {}
        for k in ("species", "genotype", "treatment", "plant_id", "tray", "qr", "gps", "notes"):
            self.meta_fields[k] = QtWidgets.QLineEdit()
            f.addRow(k.replace("_", " "), self.meta_fields[k])
        b = QtWidgets.QPushButton("Save metadata")
        b.clicked.connect(self.save_metadata)
        f.addRow(b)
        lay.addWidget(meta)
        d = QtWidgets.QDockWidget("Workspace", self)
        d.setObjectName("library")
        d.setWidget(w)
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, d)
        self.current_rec = None

    def open_workspace(self, path):
        from ..library import Workspace

        try:
            self.workspace = Workspace(path)
        except Exception as e:
            self.log(f"workspace error: {e}")
            return
        self.settings.setValue("workspace", str(path))
        self.ws_label.setText(f"<small>{path}</small>")
        self.refresh_tree()

    def choose_workspace(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Workspace folder", str(self.workspace.root if self.workspace else Path.home()))
        if d:
            self.open_workspace(d)

    def refresh_tree(self):
        self.tree.clear()
        if not self.workspace:
            return
        for proj in self.workspace.projects():
            pi = QtWidgets.QTreeWidgetItem([proj["name"], ""])
            pi.setData(0, QtCore.Qt.UserRole, ("project", proj["slug"]))
            for s in proj["sessions"]:
                si = QtWidgets.QTreeWidgetItem([s["name"], f"{len(s['scans'])} scans"])
                si.setData(0, QtCore.Qt.UserRole, ("session", proj["slug"], s["slug"]))
                for sid in s["scans"]:
                    try:
                        rec = self.workspace.scan_record(proj["slug"], s["slug"], sid)
                    except FileNotFoundError:
                        continue
                    info = ", ".join(str(rec[k]) for k in ("plant_id", "treatment") if rec.get(k))
                    ci = QtWidgets.QTreeWidgetItem([Path(rec["file"]).name, info])
                    ci.setData(0, QtCore.Qt.UserRole, ("scan", proj["slug"], s["slug"], sid))
                    si.addChild(ci)
                pi.addChild(si)
            self.tree.addTopLevelItem(pi)
            pi.setExpanded(True)
        self.tree.resizeColumnToContents(0)

    def _selected(self, kind):
        it = self.tree.currentItem()
        while it is not None:
            d = it.data(0, QtCore.Qt.UserRole)
            if d and d[0] == kind:
                return d
            it = it.parent()
        return None

    def new_project(self):
        name, ok = QtWidgets.QInputDialog.getText(self, "New project", "Project name:")
        if ok and name:
            self.workspace.create_project(name)
            self.refresh_tree()

    def new_session(self):
        p = self._selected("project")
        if not p:
            return self._error("Select a project first")
        name, ok = QtWidgets.QInputDialog.getText(self, "New session", "Session name:", text=QtCore.QDate.currentDate().toString("yyyy-MM-dd"))
        if ok and name:
            self.workspace.create_session(p[1], name)
            self.refresh_tree()

    def import_into_library(self):
        s = self._selected("session")
        if not s:
            return self._error("Select a session (create a project and session first)")
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Import scans", "", SCAN_FILTER)
        for f in files:
            rec = self.workspace.import_scan(s[1], s[2], f)
            self.log(f"imported {f} as {rec['id']}")
        self.refresh_tree()

    def _tree_open(self, item, _col):
        d = item.data(0, QtCore.Qt.UserRole)
        if d and d[0] == "scan":
            rec = self.workspace.scan_record(*d[1:])
            self.current_rec = d
            for k, w in self.meta_fields.items():
                w.setText(str(rec.get(k, "")))
            self.load_scan(rec["file"])

    def save_metadata(self):
        if not self.current_rec:
            return self._error("Open a scan from the library first")
        self.workspace.update_scan(*self.current_rec[1:], **{k: w.text() for k, w in self.meta_fields.items()})
        self.refresh_tree()

    def export_library_table(self):
        p, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Library table", "library.csv", "CSV (*.csv)")
        if p:
            self.workspace.export_table(p)
            self.log(f"wrote {p}")

    # ----------------------------------------------------------------- 3D tab
    def _build_3d_tab(self):
        page = QtWidgets.QSplitter()
        self.viewer = CloudViewer()
        self.viewer.pointPicked.connect(self._picked)
        left = QtWidgets.QWidget()
        lv = QtWidgets.QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        bar = QtWidgets.QHBoxLayout()
        self.mode_box = combo(["RGB", "Height", "Greenness (ExG)", "Plants", "Leaves"])
        self.mode_box.currentTextChanged.connect(self.viewer.set_mode)
        bar.addWidget(QtWidgets.QLabel("Colour"))
        bar.addWidget(self.mode_box)
        self.size_box = dspin(2.0, 0.5, 12, 0.5, 1)
        self.size_box.valueChanged.connect(self.viewer.set_point_size)
        bar.addWidget(QtWidgets.QLabel("Point size"))
        bar.addWidget(self.size_box)
        self.hull_cb = QtWidgets.QCheckBox("Convex hull")
        self.hull_cb.toggled.connect(self.update_overlays)
        bar.addWidget(self.hull_cb)
        self.raw_cb = QtWidgets.QCheckBox("Show original")
        self.raw_cb.toggled.connect(self._toggle_raw)
        bar.addWidget(self.raw_cb)
        bar.addStretch()
        bar.addWidget(QtWidgets.QLabel("<small>Drag: orbit · wheel: zoom · Ctrl+click: pick point</small>"))
        lv.addLayout(bar)
        lv.addWidget(self.viewer, 1)
        page.addWidget(left)

        right = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(right)
        b = QtWidgets.QPushButton("Open scan...")
        b.clicked.connect(self.open_scan_dialog)
        rv.addWidget(b)
        tb = QtWidgets.QToolBox()
        # cleaning
        g = QtWidgets.QWidget()
        f = QtWidgets.QFormLayout(g)
        self.o_yup = QtWidgets.QCheckBox("Input is Y-up (glTF / phone app export)")
        self.o_voxel = dspin(0.0, 0, 10, 0.001, 4)
        self.o_outliers = QtWidgets.QCheckBox("Remove outliers")
        self.o_outliers.setChecked(True)
        self.o_ground = QtWidgets.QCheckBox("Fit ground plane, set z = 0")
        self.o_ground.setChecked(True)
        self.o_remove_ground = QtWidgets.QCheckBox("Remove ground points")
        self.o_remove_ground.setChecked(True)
        self.o_veg = combo(["exg", "gli", "vari", "hue", "none"])
        self.o_vegthr = QtWidgets.QLineEdit()
        self.o_vegthr.setPlaceholderText("auto (Otsu)")
        self.o_largest = QtWidgets.QCheckBox("Keep largest cluster(s) only")
        for lbl, w in (("", self.o_yup), ("Voxel downsample (0 = off)", self.o_voxel), ("", self.o_outliers),
                       ("", self.o_ground), ("", self.o_remove_ground), ("Vegetation index", self.o_veg),
                       ("Index threshold", self.o_vegthr), ("", self.o_largest)):
            f.addRow(lbl, w)
        tb.addItem(g, "1  Clean and frame")
        # scale
        g = QtWidgets.QWidget()
        f = QtWidgets.QFormLayout(g)
        self.o_scale_mode = combo(["Already metric (LiDAR)", "ArUco markers", "Two picked points", "Manual factor"])
        self.o_aruco_mm = dspin(50.0, 1, 1000, 1, 2, " mm")
        from ..scale import ARUCO_DICTS

        self.o_aruco_dict = combo(ARUCO_DICTS, "DICT_4X4_50")
        self.o_aruco_ids = QtWidgets.QLineEdit()
        self.o_aruco_ids.setPlaceholderText("all IDs (or e.g. 0-8)")
        self.o_two_mm = dspin(100.0, 0.01, 100000, 1, 2, " mm")
        self.o_factor = dspin(1.0, 1e-6, 1e6, 0.01, 6)
        self.pick_label = QtWidgets.QLabel("Picked: none (Ctrl+click two points)")
        for lbl, w in (("Scale source", self.o_scale_mode), ("Marker side", self.o_aruco_mm), ("Dictionary", self.o_aruco_dict),
                       ("Marker IDs", self.o_aruco_ids), ("Distance between picks", self.o_two_mm), ("", self.pick_label),
                       ("Manual factor", self.o_factor)):
            f.addRow(lbl, w)
        tb.addItem(g, "2  Metric scale")
        # segmentation
        g = QtWidgets.QWidget()
        f = QtWidgets.QFormLayout(g)
        self.o_plants = combo(["single", "watershed", "grid", "dbscan"])
        self.o_expected = ispin(0, 0, 10000)
        self.o_rows = ispin(0, 0, 500)
        self.o_cols = ispin(0, 0, 500)
        self.o_pitch = dspin(0.0, 0, 5000, 1, 1, " mm")
        self.o_leaves = combo(["components", "region", "none"])
        for lbl, w in (("Plants", self.o_plants), ("Expected plants (0 = auto)", self.o_expected),
                       ("Pot grid rows", self.o_rows), ("Pot grid columns", self.o_cols), ("Pot pitch", self.o_pitch),
                       ("Leaf candidates", self.o_leaves)):
            f.addRow(lbl, w)
        tb.addItem(g, "3  Plants and leaves")
        rv.addWidget(tb)
        run = QtWidgets.QPushButton("Run analysis")
        run.setStyleSheet("font-weight: bold; padding: 6px")
        run.clicked.connect(self.run_analysis)
        rv.addWidget(run)
        self.res_tabs = QtWidgets.QTabWidget()
        self.t_plant = QtWidgets.QTableWidget()
        self.t_plants = QtWidgets.QTableWidget()
        self.t_leaves = QtWidgets.QTableWidget()
        self.res_tabs.addTab(self.t_plant, "Scan")
        self.res_tabs.addTab(self.t_plants, "Per plant")
        self.res_tabs.addTab(self.t_leaves, "Leaves")
        rv.addWidget(self.res_tabs, 1)
        row = QtWidgets.QHBoxLayout()
        for txt, fn in (("Save results", self.save_results), ("Export cloud", self.export_cloud), ("Markers image", self.show_marker_image)):
            b = QtWidgets.QPushButton(txt)
            b.clicked.connect(fn)
            row.addWidget(b)
        rv.addLayout(row)
        right.setMinimumWidth(380)
        page.addWidget(right)
        page.setStretchFactor(0, 3)
        self.tabs.addTab(page, "3D analysis")

    def open_scan_dialog(self):
        p, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open scan", self.settings.value("last_dir", ""), SCAN_FILTER)
        if p:
            self.settings.setValue("last_dir", str(Path(p).parent))
            self.current_rec = None
            self.load_scan(p)

    def load_scan(self, path):
        from .. import io

        self.log(f"loading {path}")

        def done(scan):
            self.raw_scan = scan
            self.scan = scan
            self.results = None
            self.picks = []
            if scan.metric:
                self.o_scale_mode.setCurrentIndex(0)
            self.viewer.set_scan(scan)
            self.update_overlays()
            self.log(f"{scan.name}: {len(scan):,} points{' + mesh' if scan.has_mesh else ''}, "
                     f"{'metric' if scan.metric else 'unscaled'}; {scan.metadata.get('format', '')}")

        self.run_bg(io.load, path, done=done)

    def load_demo(self):
        from ..synthetic import make_tray

        s, truth = make_tray(head=True)
        self.raw_scan = self.scan = s
        self.viewer.set_scan(s)
        self.o_scale_mode.setCurrentText("ArUco markers")
        self.o_aruco_mm.setValue(50)
        self.o_plants.setCurrentText("watershed")
        self.o_expected.setValue(6)
        self.log("Demo: synthetic 2x3 tray, unscaled and tilted, with three 50 mm DICT_4X4_50 markers. "
                 f"True scale factor {truth['unknown_scale']}. Press Run analysis.")

    def load_demo_crown(self):
        from ..synthetic import make_root_crown

        s, truth = make_root_crown()
        s.metric = True
        self.raw_scan = self.scan = s
        self.viewer.set_scan(s)
        self.o_scale_mode.setCurrentIndex(0)
        self.r3_view.set_scan(s)
        self.r3_kind.setCurrentIndex(0)
        self.r3_axis.setCurrentText("z")
        self.r3_stem.setValue(60)
        self.tabs.setCurrentIndex([self.tabs.tabText(i) for i in range(self.tabs.count())].index("Roots 3D"))
        self.log(f"Demo crown: {truth['n_roots']} storage roots, metric, stem 60 mm. Press Measure roots.")

    def _toggle_raw(self, on):
        self.viewer.set_scan(self.raw_scan if on else self.scan, reset_camera=False)

    def _picked(self, idx, xyz):
        self.picks = (self.picks + [xyz])[-2:]
        txt = "; ".join(np.round(p, 4).astype(str).tolist().__str__() for p in self.picks)
        if len(self.picks) == 2:
            d = float(np.linalg.norm(self.picks[0] - self.picks[1]))
            unit = "m" if (self.viewer.scan and self.viewer.scan.metric) else "units"
            txt = f"distance {d:.5g} {unit}"
            self.log(f"picked distance {d:.6g} {unit}")
        self.pick_label.setText(f"Picked: {txt}")
        self.viewer.clear_overlays()
        self.viewer.add_markers(np.array(self.picks))
        self.update_overlays(clear=False)

    def _options(self):
        from ..pipeline import Options

        mode = self.o_scale_mode.currentIndex()
        ids = None
        t = self.o_aruco_ids.text().strip()
        if t:
            ids = []
            for part in t.split(","):
                if "-" in part:
                    a, b = part.split("-")
                    ids += list(range(int(a), int(b) + 1))
                elif part.strip():
                    ids.append(int(part))
        manual = 0.0
        if mode == 2:
            if len(self.picks) != 2:
                raise ValueError("Ctrl+click two points of known distance first (on the original scan)")
            from ..scale import scale_from_two_points

            manual = scale_from_two_points(self.picks[0], self.picks[1], self.o_two_mm.value() / 1000)
        elif mode == 3:
            manual = self.o_factor.value()
        thr = self.o_vegthr.text().strip()
        return Options(
            voxel=self.o_voxel.value(), outliers=self.o_outliers.isChecked(), align_ground=self.o_ground.isChecked(),
            remove_ground=self.o_remove_ground.isChecked(), y_up=self.o_yup.isChecked(), vegetation=self.o_veg.currentText(),
            vegetation_threshold=float(thr) if thr else None,
            aruco_size_m=self.o_aruco_mm.value() / 1000 if mode == 1 else 0.0, aruco_dict=self.o_aruco_dict.currentText(),
            aruco_ids=ids, manual_scale=manual, plants=self.o_plants.currentText(),
            expected_plants=self.o_expected.value() or None, grid_rows=self.o_rows.value(), grid_cols=self.o_cols.value(),
            grid_pitch_m=self.o_pitch.value() / 1000, leaves=self.o_leaves.currentText(),
            largest_cluster=self.o_largest.isChecked())

    def run_analysis(self):
        if self.raw_scan is None:
            return self._error("Open a scan first")
        try:
            opt = self._options()
        except Exception as e:
            return self._error(str(e))
        from .. import pipeline

        def done(out):
            scan, res = out
            self.scan, self.results = scan, res
            self.raw_cb.setChecked(False)
            self.viewer.set_scan(scan)
            if res.get("plants"):
                self.mode_box.setCurrentText("Plants")
            self.update_overlays()
            table_from_rows(self.t_plant, kv_rows(res["plant"]))
            table_from_rows(self.t_plants, res.get("plants", []))
            table_from_rows(self.t_leaves, res.get("leaf_candidates", []))
            if not scan.metric:
                self.log("Note: the scan is not metric, so values are in scan units. Use ArUco or two-point scaling.")
            if self.current_rec and self.workspace:
                self.workspace.save_results(*self.current_rec[1:], "traits", json.loads(json.dumps(res, default=_js)))
                self.log("results saved to the library")

        self.run_bg(pipeline.run, self.raw_scan, opt, done=done)

    def update_overlays(self, clear=True):
        if clear:
            self.viewer.clear_overlays()
        s = self.viewer.scan
        if s is None or not self.hull_cb.isChecked() or len(s) < 4:
            return
        if s.labels is not None and (s.labels >= 0).any() and self.mode_box.currentText() == "Plants":
            for k in np.unique(s.labels[s.labels >= 0]):
                p = s.points[s.labels == k]
                if len(p) > 10:
                    self.viewer.add_hull(p[:: max(1, len(p) // 20000)])
        else:
            self.viewer.add_hull(s.points[:: max(1, len(s) // 50000)])

    def save_results(self):
        if not self.results:
            return self._error("Run an analysis first")
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Folder for results")
        if d:
            from ..pipeline import save_results

            files = save_results(self.results, d, self.scan.name)
            self.log("wrote " + ", ".join(files.values()))

    def export_cloud(self):
        if self.scan is None:
            return
        p, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export cloud", f"{self.scan.name}_clean.ply", "PLY (*.ply);;PCD (*.pcd);;CSV (*.csv)")
        if p:
            from ..io import save_point_cloud

            save_point_cloud(self.scan, p)
            self.log(f"wrote {p}")

    def show_marker_image(self):
        if self.raw_scan is None:
            return
        from ..clean import align_to_ground
        from ..scale import scale_from_aruco

        try:
            s = align_to_ground(self.raw_scan, remove=False)
            r = scale_from_aruco(s, self.o_aruco_mm.value() / 1000, dictionary=self.o_aruco_dict.currentText())
        except Exception as e:
            return self._error(str(e))
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(f"ArUco detection: {r.summary()}")
        lay = QtWidgets.QVBoxLayout(dlg)
        iv = ImageView()
        lay.addWidget(iv)
        dlg.resize(1000, 800)
        iv.show_rgb(r.image)
        sizes = ", ".join(f"id {i}: {v * r.factor * 1000:.2f} mm" for i, v in r.marker_sizes_units.items())
        lay.addWidget(QtWidgets.QLabel(f"Marker sides after scaling: {sizes}"))
        dlg.exec()

    def snapshot(self):
        p, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Snapshot", "view.png", "PNG (*.png)")
        if p:
            self.viewer.snapshot(p)

    # ----------------------------------------------------------------- compare tab
    def _build_compare_tab(self):
        page = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(page)
        row = QtWidgets.QHBoxLayout()
        self.cmp_files = [QtWidgets.QLineEdit(), QtWidgets.QLineEdit()]
        for i, e in enumerate(self.cmp_files):
            b = QtWidgets.QPushButton(f"Scan {'AB'[i]}...")
            b.clicked.connect(lambda _=False, e=e: e.setText(QtWidgets.QFileDialog.getOpenFileName(self, "Scan", "", SCAN_FILTER)[0]))
            row.addWidget(b)
            row.addWidget(e)
        go = QtWidgets.QPushButton("Analyse both (uses 3D settings)")
        go.clicked.connect(self.run_compare)
        row.addWidget(go)
        v.addLayout(row)
        sp = QtWidgets.QSplitter()
        self.cmp_view = [CloudViewer(), CloudViewer()]
        for cv in self.cmp_view:
            sp.addWidget(cv)
        self.cmp_view[0].cameraChanged.connect(self.cmp_view[1].set_camera)
        self.cmp_view[1].cameraChanged.connect(self.cmp_view[0].set_camera)
        v.addWidget(sp, 3)
        self.cmp_table = QtWidgets.QTableWidget()
        v.addWidget(self.cmp_table, 2)
        self.tabs.addTab(page, "Compare")

    def run_compare(self):
        from .. import compare, io, pipeline

        paths = [e.text() for e in self.cmp_files]
        if not all(paths):
            return self._error("Choose two scans")
        try:
            opt = self._options()
        except Exception as e:
            return self._error(str(e))

        def work(log=print):
            out = []
            for p in paths:
                log(f"analysing {p}")
                out.append(pipeline.run(io.load(p), opt, log=log))
            return out

        def done(out):
            (sa, ra), (sb, rb) = out
            self.cmp_view[0].set_scan(sa)
            self.cmp_view[1].set_scan(sb)
            self.cmp_view[1].set_camera({k: self.cmp_view[0].view.opts[k] for k in ("distance", "elevation", "azimuth", "center")})
            table_from_rows(self.cmp_table, compare.compare_traits(ra["plant"], rb["plant"]))

        self.run_bg(work, done=done)

    # ----------------------------------------------------------------- 2D images tab
    def _build_images_tab(self):
        page = QtWidgets.QSplitter()
        left = QtWidgets.QWidget()
        f = QtWidgets.QFormLayout(left)
        self.im_in = QtWidgets.QLineEdit()
        b = QtWidgets.QPushButton("Folder...")
        b.clicked.connect(lambda: self.im_in.setText(QtWidgets.QFileDialog.getExistingDirectory(self, "Image folder")))
        hb = QtWidgets.QHBoxLayout()
        hb.addWidget(self.im_in)
        hb.addWidget(b)
        f.addRow("Images", hb)
        self.im_out = QtWidgets.QLineEdit(str(Path.home() / "PhenoForge" / "images_out"))
        f.addRow("Output folder", self.im_out)
        self.im_method = combo(["exg", "hsv"])
        f.addRow("Plant mask", self.im_method)
        self.im_aruco = dspin(0.0, 0, 1000, 1, 2, " mm")
        f.addRow("ArUco marker side (0 = none)", self.im_aruco)
        self.im_minblob = ispin(200, 1, 10_000_000)
        f.addRow("Min plant size (px)", self.im_minblob)
        go = QtWidgets.QPushButton("Run batch")
        go.clicked.connect(self.run_images)
        f.addRow(go)
        self.im_list = QtWidgets.QListWidget()
        self.im_list.currentTextChanged.connect(self._show_overlay)
        f.addRow(self.im_list)
        self.im_qr = QtWidgets.QLabel()
        f.addRow("QR / GPS", self.im_qr)
        page.addWidget(left)
        right = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.im_view = ImageView()
        right.addWidget(self.im_view)
        self.im_table = QtWidgets.QTableWidget()
        right.addWidget(self.im_table)
        page.addWidget(right)
        page.setStretchFactor(1, 3)
        self.tabs.addTab(page, "Images (2D)")

    def run_images(self):
        from .. import phenotype2d

        src, out = self.im_in.text(), self.im_out.text()
        if not src:
            return self._error("Choose an image folder")

        def done(paths):
            import csv

            rows = list(csv.DictReader(open(paths[0], encoding="utf-8")))
            table_from_rows(self.im_table, rows)
            self.im_list.clear()
            self.im_list.addItems([r["image"] for r in rows])
            self.log(f"wrote {paths[0]} and {paths[1]}")

        self.run_bg(phenotype2d.batch, [src], out, done=done, marker_size_mm=self.im_aruco.value() or None,
                    method=self.im_method.currentText(), min_blob_px=self.im_minblob.value())

    def _show_overlay(self, name):
        if not name:
            return
        from .. import phenotype2d

        ov = Path(self.im_out.text()) / f"{Path(name).stem}_overlay.png"
        if ov.exists():
            self.im_view.show_rgb(phenotype2d.read_image(ov))
        src = Path(self.im_in.text()) / name
        if src.exists():
            rgb = phenotype2d.read_image(src)
            self.im_qr.setText(f"QR: {', '.join(phenotype2d.read_qr(rgb)) or '-'} · GPS: {phenotype2d.exif_gps(src) or '-'}")

    # ----------------------------------------------------------------- roots tab
    def _build_roots_tab(self):
        page = QtWidgets.QSplitter()
        left = QtWidgets.QWidget()
        f = QtWidgets.QFormLayout(left)
        self.rt_in = QtWidgets.QLineEdit()
        b = QtWidgets.QPushButton("Image or video...")
        b.clicked.connect(lambda: self.rt_in.setText(QtWidgets.QFileDialog.getOpenFileName(
            self, "Root image or video", "", "Images/videos (*.jpg *.jpeg *.png *.tif *.tiff *.mp4 *.mov *.avi)")[0]))
        hb = QtWidgets.QHBoxLayout()
        hb.addWidget(self.rt_in)
        hb.addWidget(b)
        f.addRow("Input", hb)
        self.rt_roots = combo(["auto", "dark", "light"])
        f.addRow("Roots are", self.rt_roots)
        self.rt_mmpp = dspin(0.0, 0, 100, 0.001, 4, " mm/px")
        f.addRow("Scale (0 = px / ArUco)", self.rt_mmpp)
        self.rt_aruco = dspin(0.0, 0, 1000, 1, 2, " mm")
        f.addRow("ArUco marker side", self.rt_aruco)
        self.rt_every = ispin(10, 1, 1000)
        f.addRow("Video: every Nth frame", self.rt_every)
        self.rt_stitch = QtWidgets.QCheckBox("Video: stitch frames into a panorama")
        f.addRow(self.rt_stitch)
        self.rt_dish = QtWidgets.QCheckBox("Ignore outside a centred circular dish")
        f.addRow(self.rt_dish)
        go = QtWidgets.QPushButton("Analyse roots")
        go.clicked.connect(self.run_roots)
        f.addRow(go)
        self.rt_table = QtWidgets.QTableWidget()
        f.addRow(self.rt_table)
        page.addWidget(left)
        self.rt_view = ImageView()
        page.addWidget(self.rt_view)
        page.setStretchFactor(1, 3)
        self.tabs.addTab(page, "Roots")

    def run_roots(self):
        from .. import phenotype2d, roots
        from ..scale import image_mm_per_px

        src = self.rt_in.text()
        if not src:
            return self._error("Choose an image or video")
        dark = {"auto": None, "dark": True, "light": False}[self.rt_roots.currentText()]

        def work(log=print):
            p = Path(src)
            if p.suffix.lower() in (".mp4", ".mov", ".avi", ".mkv"):
                tmp = Path.home() / "PhenoForge" / "root_frames" / p.stem
                frames = roots.extract_frames(p, tmp, every_n=self.rt_every.value())
                log(f"{len(frames)} frames extracted to {tmp}")
                imgs = [phenotype2d.read_image(x) for x in frames]
                rgb = roots.stitch(imgs) if self.rt_stitch.isChecked() and len(imgs) > 1 else imgs[len(imgs) // 2]
            else:
                rgb = phenotype2d.read_image(p)
            mmpp = self.rt_mmpp.value() or None
            if not mmpp and self.rt_aruco.value():
                mmpp, n = image_mm_per_px(rgb, self.rt_aruco.value())
                log(f"ArUco: {n} marker(s), {mmpp} mm/px")
            m = roots.root_mask(rgb, roots_dark=dark, roi_circle=self.rt_dish.isChecked())
            t, draw = roots.root_traits(m, mm_per_px=mmpp)
            return t, roots.draw_overlay(rgb, m, draw)

        def done(out):
            t, ov = out
            table_from_rows(self.rt_table, kv_rows(t))
            self.rt_view.show_rgb(ov)

        self.run_bg(work, done=done)

    # ----------------------------------------------------------------- roots 3D tab
    def _build_roots3d_tab(self):
        page = QtWidgets.QSplitter()
        self.r3_view = CloudViewer()
        self.r3_view.pointPicked.connect(self._r3_picked)
        left = QtWidgets.QWidget()
        lv = QtWidgets.QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        bar = QtWidgets.QHBoxLayout()
        self.r3_mode_box = combo(["RGB", "Plants", "Height"])
        self.r3_mode_box.setItemText(1, "Roots")
        self.r3_mode_box.currentTextChanged.connect(lambda t: self.r3_view.set_mode("Plants" if t == "Roots" else t))
        bar.addWidget(QtWidgets.QLabel("Colour"))
        bar.addWidget(self.r3_mode_box)
        bar.addStretch()
        bar.addWidget(QtWidgets.QLabel("<small>Ctrl+click: stem top, then crown bottom</small>"))
        lv.addLayout(bar)
        lv.addWidget(self.r3_view, 1)
        page.addWidget(left)
        right = QtWidgets.QWidget()
        f = QtWidgets.QFormLayout(right)
        row = QtWidgets.QHBoxLayout()
        b = QtWidgets.QPushButton("Use scan from 3D tab")
        b.clicked.connect(lambda: self.raw_scan is not None and self.r3_view.set_scan(self.raw_scan))
        row.addWidget(b)
        b = QtWidgets.QPushButton("Open CT stack...")
        b.clicked.connect(self._r3_open_ct)
        row.addWidget(b)
        f.addRow(row)
        self.r3_kind = combo(["Root crown (storage roots)", "Fibrous root system"])
        f.addRow("Root type", self.r3_kind)
        self.r3_axis = combo(["z", "-z", "x", "-x", "y", "-y", "pca", "two picked points"])
        f.addRow("Stem direction", self.r3_axis)
        self.r3_green = QtWidgets.QCheckBox("Remove green background sheet")
        self.r3_green.setChecked(True)
        f.addRow(self.r3_green)
        self.r3_plane = QtWidgets.QCheckBox("Remove flat background plane")
        self.r3_plane.setChecked(True)
        f.addRow(self.r3_plane)
        self.r3_stem = dspin(0.0, 0, 2000, 5, 1, " mm")
        f.addRow("Cut stem stub (top)", self.r3_stem)
        self.r3_voxel = dspin(0.0, 0, 100, 0.5, 2, " mm")
        f.addRow("Voxel (0 = auto)", self.r3_voxel)
        self.r3_depth = ispin(8, 5, 11)
        f.addRow("Remesh depth (auto voxel)", self.r3_depth)
        self.r3_sectors = ispin(1, 1, 8)
        f.addRow("Split crown into sectors (paper: 2)", self.r3_sectors)
        self.r3_core = dspin(0.0, 0, 1000, 1, 1, " mm")
        f.addRow("Crown core radius (0 = auto)", self.r3_core)
        self.r3_weight = dspin(0.0, 0, 1000, 0.01, 3, " kg")
        f.addRow("Root fresh weight", self.r3_weight)
        f.addRow(QtWidgets.QLabel("<small>Scale comes from the 3D tab settings (ArUco, picks or factor). "
                                  "LiDAR scans are already metric.</small>"))
        go = QtWidgets.QPushButton("Measure roots")
        go.setStyleSheet("font-weight: bold; padding: 6px")
        go.clicked.connect(self.run_roots3d)
        f.addRow(go)
        self.r3_tabs = QtWidgets.QTabWidget()
        self.r3_table = QtWidgets.QTableWidget()
        self.r3_roots = QtWidgets.QTableWidget()
        self.r3_tabs.addTab(self.r3_table, "Crown / system")
        self.r3_tabs.addTab(self.r3_roots, "Individual roots")
        f.addRow(self.r3_tabs)
        b = QtWidgets.QPushButton("Save CSV...")
        b.clicked.connect(self._r3_save)
        f.addRow(b)
        right.setMinimumWidth(380)
        page.addWidget(right)
        page.setStretchFactor(0, 3)
        self.tabs.addTab(page, "Roots 3D")
        self.r3_picks, self.r3_result, self.r3_solid = [], None, None

    def _r3_picked(self, idx, xyz):
        self.r3_picks = (self.r3_picks + [xyz])[-2:]
        self.r3_view.clear_overlays()
        self.r3_view.add_markers(np.array(self.r3_picks))
        self.log(f"root axis pick {len(self.r3_picks)}: {np.round(xyz, 4).tolist()}")

    def _r3_open_ct(self):
        from .. import roots3d

        p, _ = QtWidgets.QFileDialog.getOpenFileName(self, "CT / MRI TIFF stack", "", "TIFF (*.tif *.tiff)")
        if not p:
            return
        v, ok = QtWidgets.QInputDialog.getDouble(self, "Voxel size", "Voxel size (mm):", 0.1, 0.001, 100, 4)
        if not ok:
            return

        def done(sol):
            self.r3_solid = sol
            self.r3_kind.setCurrentIndex(1)
            self.r3_view.set_scan(roots3d.solid_to_scan(sol))
            self.log(f"CT stack loaded: {sol.occ.shape} voxels, root volume {sol.volume * 1e6:.2f} cm3")

        self.run_bg(roots3d.load_volume_stack, p, v / 1000, done=done)

    def run_roots3d(self):
        from .. import roots3d, scale

        base = self.r3_view.scan
        if base is None and self.r3_solid is None:
            return self._error("Load a scan in the 3D tab (or a CT stack) first")
        try:
            mode = self.o_scale_mode.currentIndex()
            if base is not None and mode in (1, 2, 3):
                o = self._options()
                factor = o.manual_scale
                if mode == 1:
                    from ..clean import align_to_ground

                    base, ms = scale.apply_aruco_scale(align_to_ground(base, remove=False), o.aruco_size_m,
                                                       dictionary=o.aruco_dict, allowed_ids=o.aruco_ids)
                    self.log("ArUco: " + ms.summary())
                elif factor:
                    base = scale.apply_factor(base, factor, "manual")
        except Exception as e:
            return self._error(str(e))
        axis = self.r3_axis.currentText()
        sp = bp = None
        if axis == "two picked points":
            if len(self.r3_picks) != 2:
                return self._error("Ctrl+click the stem top and then the crown bottom")
            sp, bp = self.r3_picks
            axis = "z"
        crown = self.r3_kind.currentIndex() == 0
        opt = roots3d.CrownOptions(voxel=self.r3_voxel.value() / 1000, depth=self.r3_depth.value(),
                                   sectors=self.r3_sectors.value(), core_radius=self.r3_core.value() / 1000,
                                   weight_kg=self.r3_weight.value())
        ct = self.r3_solid if (self.r3_solid is not None and base is not None and base.name == "roots") else None

        def work(log=print):
            if ct is not None:
                t, _ = roots3d.fibrous_traits(ct, log=log)
                return None, t, {"roots": []}
            if crown:
                return roots3d.crown_pipeline(base, axis, sp, bp, self.r3_green.isChecked(), self.r3_plane.isChecked(),
                                              self.r3_stem.value() / 1000, opt, log=log)
            s2 = roots3d.orient(base, axis, sp, bp)
            t, ex = roots3d.fibrous_from_scan(s2, voxel=self.r3_voxel.value() / 1000, log=log)
            return s2, t, {"roots": []}

        def done(res):
            s2, t, ex = res
            self.r3_result = (t, ex.get("roots", []))
            if s2 is not None:
                self.r3_view.set_scan(s2)
                if crown:
                    self.r3_mode_box.setCurrentText("Roots")
            table_from_rows(self.r3_table, kv_rows(t))
            table_from_rows(self.r3_roots, ex.get("roots", []))
            if s2 is not None and not s2.metric:
                self.log("Note: scan is not metric; set a scale in the 3D tab (ArUco, two points or factor).")

        self.run_bg(work, done=done)

    def _r3_save(self):
        if not self.r3_result:
            return self._error("Measure roots first")
        from ..phenotype2d import write_csv

        p, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Root traits", "roots3d.csv", "CSV (*.csv)")
        if p:
            t, roots = self.r3_result
            write_csv(p, [{k: v for k, v in t.items() if not isinstance(v, (list, dict))}])
            if roots:
                write_csv(Path(p).with_name(Path(p).stem + "_individual_roots.csv"), roots)
            self.log(f"wrote {p}")

    # ----------------------------------------------------------------- colour tab
    def _build_colour_tab(self):
        page = QtWidgets.QSplitter()
        left = QtWidgets.QWidget()
        f = QtWidgets.QFormLayout(left)
        self.cc_img = QtWidgets.QLineEdit()
        b = QtWidgets.QPushButton("Chart photo...")
        b.clicked.connect(lambda: self.cc_img.setText(QtWidgets.QFileDialog.getOpenFileName(self, "Colour chart photo", "", IMG_FILTER)[0]))
        hb = QtWidgets.QHBoxLayout()
        hb.addWidget(self.cc_img)
        hb.addWidget(b)
        f.addRow("Chart", hb)
        self.cc_corners = QtWidgets.QLineEdit()
        self.cc_corners.setPlaceholderText("auto, or x1 y1 x2 y2 x3 y3 x4 y4 (TL TR BR BL)")
        f.addRow("Chart corners", self.cc_corners)
        self.cc_ref = QtWidgets.QLineEdit()
        self.cc_ref.setPlaceholderText("standard 24-patch values, or a JSON file for your chart")
        f.addRow("Reference values", self.cc_ref)
        go = QtWidgets.QPushButton("Fit correction")
        go.clicked.connect(self.fit_colour)
        f.addRow(go)
        self.cc_info = QtWidgets.QLabel("No correction loaded")
        self.cc_info.setWordWrap(True)
        f.addRow(self.cc_info)
        b1 = QtWidgets.QPushButton("Apply to current scan colours")
        b1.clicked.connect(self.apply_colour_scan)
        f.addRow(b1)
        b2 = QtWidgets.QPushButton("Apply to an image folder...")
        b2.clicked.connect(self.apply_colour_folder)
        f.addRow(b2)
        b3 = QtWidgets.QPushButton("Save / load correction...")
        b3.clicked.connect(self.save_load_colour)
        f.addRow(b3)
        page.addWidget(left)
        self.cc_view = ImageView()
        page.addWidget(self.cc_view)
        page.setStretchFactor(1, 3)
        self.tabs.addTab(page, "Colour")
        self.colour_corr = None

    def fit_colour(self):
        from .. import colorcal, phenotype2d

        try:
            rgb = phenotype2d.read_image(self.cc_img.text())
            meas = None
            if self.cc_corners.text().strip():
                c = np.array([float(x) for x in self.cc_corners.text().replace(",", " ").split()]).reshape(4, 2)
                meas = colorcal.sample_patches_from_corners(rgb, c)
            else:
                meas = colorcal.detect_patches_mcc(rgb)
            if meas is None:
                return self._error("Chart not found automatically. Enter its four corners (pixel coordinates).")
            ref = colorcal.load_reference(self.cc_ref.text()) if self.cc_ref.text().strip() else colorcal.REFERENCE_SRGB
            self.colour_corr = colorcal.fit_correction(meas, ref)
            self.cc_info.setText(f"RMSE {self.colour_corr['rmse_before']:.1f} -> {self.colour_corr['rmse_after']:.1f} "
                                 f"(8-bit, {self.colour_corr['used']} patches)")
            self.cc_view.show_rgb(colorcal.correct_image(rgb, self.colour_corr["M"]))
        except Exception as e:
            self._error(str(e))

    def apply_colour_scan(self):
        from .. import colorcal

        if not self.colour_corr or self.raw_scan is None or self.raw_scan.colors is None:
            return self._error("Fit a correction and open a coloured scan first")
        s = self.raw_scan.copy()
        s.colors = colorcal.correct_colors(s.colors, self.colour_corr["M"])
        s.history.append("colour corrected")
        self.raw_scan = self.scan = s
        self.viewer.set_scan(s, reset_camera=False)
        self.log("scan colours corrected; re-run the analysis to update greenness")

    def apply_colour_folder(self):
        from .. import colorcal, phenotype2d

        if not self.colour_corr:
            return self._error("Fit a correction first")
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Image folder")
        if not d:
            return
        out = Path(d) / "colour_corrected"
        out.mkdir(exist_ok=True)
        n = 0
        for p in Path(d).iterdir():
            if p.suffix.lower() in phenotype2d.IMG_EXT:
                phenotype2d.write_image(out / (p.stem + ".png"), colorcal.correct_image(phenotype2d.read_image(p), self.colour_corr["M"]))
                n += 1
        self.log(f"corrected {n} images into {out}")

    def save_load_colour(self):
        from .. import colorcal

        if self.colour_corr:
            p, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save correction", "colour_correction.json", "JSON (*.json)")
            if p:
                colorcal.save_correction(p, self.colour_corr)
        else:
            p, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Load correction", "", "JSON (*.json)")
            if p:
                self.colour_corr = colorcal.load_correction(p)
                self.cc_info.setText(f"Loaded {p}")

    # ----------------------------------------------------------------- validation tab
    def _build_validation_tab(self):
        page = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(page)
        f = QtWidgets.QFormLayout()
        self.va_pred, self.va_ref = QtWidgets.QLineEdit(), QtWidgets.QLineEdit()
        for lbl, e in (("Predicted CSV", self.va_pred), ("Reference CSV (manual / facility)", self.va_ref)):
            hb = QtWidgets.QHBoxLayout()
            hb.addWidget(e)
            b = QtWidgets.QPushButton("...")
            b.clicked.connect(lambda _=False, e=e: e.setText(QtWidgets.QFileDialog.getOpenFileName(self, "CSV", "", "CSV (*.csv)")[0]))
            hb.addWidget(b)
            f.addRow(lbl, hb)
        self.va_key = QtWidgets.QLineEdit("scan")
        f.addRow("Join column", self.va_key)
        self.va_cols = QtWidgets.QLineEdit()
        self.va_cols.setPlaceholderText("all shared numeric columns")
        f.addRow("Columns", self.va_cols)
        self.va_mask = [QtWidgets.QLineEdit(), QtWidgets.QLineEdit()]
        hb = QtWidgets.QHBoxLayout()
        for e, t in zip(self.va_mask, ("predicted mask", "reference mask")):
            e.setPlaceholderText(t)
            hb.addWidget(e)
        f.addRow("Mask pair (PNG)", hb)
        v.addLayout(f)
        row = QtWidgets.QHBoxLayout()
        b = QtWidgets.QPushButton("Compare traits")
        b.clicked.connect(self.run_validation)
        row.addWidget(b)
        b = QtWidgets.QPushButton("Compare masks")
        b.clicked.connect(self.run_mask_validation)
        row.addWidget(b)
        v.addLayout(row)
        sp = QtWidgets.QSplitter()
        self.va_table = QtWidgets.QTableWidget()
        sp.addWidget(self.va_table)
        self.va_plot = ImageView()
        sp.addWidget(self.va_plot)
        v.addWidget(sp, 1)
        self.tabs.addTab(page, "Validation")

    def run_validation(self):
        from .. import validate

        try:
            cols = [c.strip() for c in self.va_cols.text().split(",") if c.strip()] or None
            res = validate.compare_csv(self.va_pred.text(), self.va_ref.text(), self.va_key.text(), cols)
            rows = [{"trait": k, **v} for k, v in res.items() if isinstance(v, dict)]
            table_from_rows(self.va_table, rows)
            self.log(f"matched {res['matched']} rows; unmatched predicted {len(res['unmatched_pred'])}, reference {len(res['unmatched_ref'])}")
            if rows:
                c = rows[0]["trait"]
                P = {r[self.va_key.text()]: r for r in validate.read_csv(self.va_pred.text())}
                R = {r[self.va_key.text()]: r for r in validate.read_csv(self.va_ref.text())}
                keys = sorted(set(P) & set(R))
                out = Path.home() / "PhenoForge" / "validation.png"
                out.parent.mkdir(parents=True, exist_ok=True)
                validate.plot_agreement([float(P[k][c]) for k in keys], [float(R[k][c]) for k in keys], str(out), c)
                from ..phenotype2d import read_image

                self.va_plot.show_rgb(read_image(out))
        except Exception as e:
            self._error(str(e))

    def run_mask_validation(self):
        from .. import phenotype2d, validate

        try:
            a, b = (phenotype2d.read_image(e.text()).mean(2) > 127 for e in self.va_mask)
            table_from_rows(self.va_table, kv_rows(validate.mask_metrics(a, b)))
        except Exception as e:
            self._error(str(e))

    # ----------------------------------------------------------------- print tab
    def _build_print_tab(self):
        page = QtWidgets.QWidget()
        f = QtWidgets.QFormLayout(page)
        f.addRow(QtWidgets.QLabel("Uses the analysed (cleaned) scan from the 3D tab, or the original if not analysed."))
        self.pr_colours = ispin(4, 1, 16)
        f.addRow("Filament colours", self.pr_colours)
        self.pr_palette = QtWidgets.QLineEdit()
        self.pr_palette.setPlaceholderText("auto (k-means), or hex list e.g. 2d5a1e,7fb341,c9b26b,5b3a1e")
        f.addRow("Fixed palette", self.pr_palette)
        self.pr_height = dspin(120, 0, 2000, 5, 1, " mm")
        f.addRow("Print height (0 = true size)", self.pr_height)
        self.pr_mesh = combo(["poisson", "alpha", "ball", "existing"])
        f.addRow("Surface", self.pr_mesh)
        self.pr_depth = ispin(9, 5, 12)
        f.addRow("Poisson depth", self.pr_depth)
        self.pr_base = dspin(2.0, 0, 50, 0.5, 1, " mm")
        f.addRow("Base plate", self.pr_base)
        self.pr_use_raw = QtWidgets.QCheckBox("Use the original scan (keep soil and pot)")
        f.addRow(self.pr_use_raw)
        go = QtWidgets.QPushButton("Export 3MF + STL + OBJ bundle...")
        go.clicked.connect(self.run_print)
        f.addRow(go)
        self.pr_info = QtWidgets.QPlainTextEdit(readOnly=True)
        f.addRow(self.pr_info)
        self.tabs.addTab(page, "3D print")

    def run_print(self):
        from .. import printexport

        s = self.raw_scan if (self.pr_use_raw.isChecked() or self.scan is None) else self.scan
        if s is None:
            return self._error("Open a scan first")
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Output folder")
        if not d:
            return
        pal = None
        if self.pr_palette.text().strip():
            pal = np.array([[int(h[i:i + 2], 16) for i in (0, 2, 4)] for h in self.pr_palette.text().replace("#", "").split(",")])
        self.run_bg(printexport.export_print_bundle, s, d, name=s.name, n_colours=len(pal) if pal is not None else self.pr_colours.value(),
                    palette=pal, target_height_mm=self.pr_height.value() or None, method=self.pr_mesh.currentText(),
                    depth=self.pr_depth.value(), base_mm=self.pr_base.value(),
                    done=lambda info: self.pr_info.setPlainText(json.dumps(info, indent=1)))

    # ----------------------------------------------------------------- assistant tab
    def _build_assistant_tab(self):
        page = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(page)
        v.addWidget(QtWidgets.QLabel("Ask questions about the current scan using a local model in "
                                     "<a href='https://ollama.com'>Ollama</a>. Nothing leaves this computer."))
        row = QtWidgets.QHBoxLayout()
        self.ai_url = QtWidgets.QLineEdit("http://localhost:11434")
        self.ai_model = QtWidgets.QComboBox()
        self.ai_model.setEditable(True)
        self.ai_model.setCurrentText("gemma3:4b")
        b = QtWidgets.QPushButton("List models")
        b.clicked.connect(self.ai_list)
        for w in (QtWidgets.QLabel("Server"), self.ai_url, QtWidgets.QLabel("Model"), self.ai_model, b):
            row.addWidget(w)
        v.addLayout(row)
        self.ai_chat = QtWidgets.QTextBrowser()
        v.addWidget(self.ai_chat, 1)
        row = QtWidgets.QHBoxLayout()
        self.ai_q = QtWidgets.QLineEdit()
        self.ai_q.setPlaceholderText("e.g. Which plant is tallest, and is the leaf area reliable?")
        self.ai_q.returnPressed.connect(self.ai_ask)
        b = QtWidgets.QPushButton("Ask")
        b.clicked.connect(self.ai_ask)
        row.addWidget(self.ai_q)
        row.addWidget(b)
        v.addLayout(row)
        self.tabs.addTab(page, "Assistant")

    def ai_list(self):
        from .. import assistant

        try:
            self.ai_model.clear()
            self.ai_model.addItems(assistant.list_models(self.ai_url.text()))
        except Exception as e:
            self._error(f"Ollama not reachable at {self.ai_url.text()}: {e}")

    def ai_ask(self):
        from .. import assistant

        q = self.ai_q.text().strip()
        if not q:
            return
        ctx = {"scan": self.scan.name if self.scan else None, "metric": bool(self.scan and self.scan.metric),
               "results": self.results or {}, "history": self.scan.history if self.scan else []}
        if self.current_rec and self.workspace:
            ctx["metadata"] = self.workspace.scan_record(*self.current_rec[1:])
        self.ai_chat.append(f"<b>You:</b> {q}")
        self.ai_q.clear()
        self.run_bg(assistant.ask, q, json.loads(json.dumps(ctx, default=_js)), model=self.ai_model.currentText(),
                    url=self.ai_url.text(), done=lambda a: self.ai_chat.append(f"<b>Assistant:</b> {a}<br>"))

    # ----------------------------------------------------------------- tools tab
    def _build_tools_tab(self):
        page = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(page)
        g = QtWidgets.QGroupBox("Import from a capture device (iPhone LiDAR, Android, DSLR)")
        f = QtWidgets.QFormLayout(g)
        self.dev_kind = combo(["Auto-detect", "iPhone / iPad with LiDAR", "Android phone", "DSLR / mirrorless camera"])
        self.dev_kind.currentIndexChanged.connect(self._dev_tips)
        f.addRow("Device", self.dev_kind)
        self.dev_src = QtWidgets.QLineEdit()
        self.dev_src.setPlaceholderText("a scan file, a video, or a folder of photos (JPEG or RAW)")
        hb = QtWidgets.QHBoxLayout()
        hb.addWidget(self.dev_src)
        for txt, fn in (("File/video...", lambda: self.dev_src.setText(QtWidgets.QFileDialog.getOpenFileName(
                self, "Scan file or video", "", "Scans and videos (*.ply *.obj *.glb *.gltf *.usdz *.zip *.las *.mp4 *.mov *.avi *.mkv);;All files (*)")[0])),
                        ("Photo folder...", lambda: self.dev_src.setText(QtWidgets.QFileDialog.getExistingDirectory(self, "Photo folder")))):
            b = QtWidgets.QPushButton(txt)
            b.clicked.connect(fn)
            hb.addWidget(b)
        f.addRow("Input", hb)
        self.dev_tip = QtWidgets.QLabel()
        self.dev_tip.setWordWrap(True)
        f.addRow(self.dev_tip)
        b = QtWidgets.QPushButton("Import (reconstructs photos/video with COLMAP when needed)")
        b.clicked.connect(self.run_device_import)
        f.addRow(b)
        v.addWidget(g)
        self._dev_tips()
        g = QtWidgets.QGroupBox("Printable ArUco marker sheet")
        f = QtWidgets.QFormLayout(g)
        from ..scale import ARUCO_DICTS

        self.mk_dict = combo(ARUCO_DICTS, "DICT_4X4_50")
        self.mk_first = ispin(0, 0, 999)
        self.mk_count = ispin(9, 1, 100)
        self.mk_mm = dspin(50, 5, 500, 1, 1, " mm")
        for lbl, w in (("Dictionary", self.mk_dict), ("First ID", self.mk_first), ("Count", self.mk_count), ("Side", self.mk_mm)):
            f.addRow(lbl, w)
        b = QtWidgets.QPushButton("Save sheet (PNG, 300 dpi)...")
        b.clicked.connect(self.make_markers)
        f.addRow(b)
        v.addWidget(g)
        g = QtWidgets.QGroupBox("Photogrammetry from photos / video frames (COLMAP)")
        f = QtWidgets.QFormLayout(g)
        self.cm_path = QtWidgets.QLineEdit(self.settings.value("colmap", ""))
        self.cm_path.setPlaceholderText("path to COLMAP.bat / colmap.exe (or on PATH)")
        f.addRow("COLMAP", self.cm_path)
        self.cm_imgs = QtWidgets.QLineEdit()
        b = QtWidgets.QPushButton("Image folder...")
        b.clicked.connect(lambda: self.cm_imgs.setText(QtWidgets.QFileDialog.getExistingDirectory(self, "Images")))
        hb = QtWidgets.QHBoxLayout()
        hb.addWidget(self.cm_imgs)
        hb.addWidget(b)
        f.addRow("Images", hb)
        self.cm_quality = combo(["low", "medium", "high", "extreme"], "medium")
        f.addRow("Quality", self.cm_quality)
        b = QtWidgets.QPushButton("Reconstruct and open")
        b.clicked.connect(self.run_colmap)
        f.addRow(b)
        v.addWidget(g)
        v.addStretch()
        self.tabs.addTab(page, "Tools")

    _DEV_KEYS = [None, "iphone_lidar", "android", "dslr"]

    def _dev_tips(self):
        from ..capture import PROFILES

        k = self._DEV_KEYS[self.dev_kind.currentIndex()]
        if k is None:
            self.dev_tip.setText("<small>The device is guessed from file types and photo EXIF. See the SOP PDFs in docs/sop.</small>")
            return
        p = PROFILES[k]
        self.dev_tip.setText(f"<small><b>{p.name}</b>: {p.route}<br>" + "<br>".join("• " + t for t in p.tips) + "</small>")

    def run_device_import(self):
        from ..capture import import_capture

        src = self.dev_src.text().strip()
        if not src:
            return self._error("Choose a scan file, video or photo folder")
        self.settings.setValue("colmap", self.cm_path.text())
        work = Path(src).parent / (Path(src).stem + "_phenoforge")

        def done(out):
            scan, info = out
            self.raw_scan = self.scan = scan
            self.results = None
            self.tabs.setCurrentIndex(0)
            self.viewer.set_scan(scan)
            self.o_scale_mode.setCurrentIndex(0 if info.get("metric") else 1)
            self.log(f"imported from {info['device']} via {info['route']}: {len(scan):,} points"
                     + ("" if info.get("metric") else " (not metric: set the ArUco marker size, then Run analysis)"))
            for r in info.get("rejected", []):
                self.log(f"  rejected {r['file']}: {r['reason']}")

        self.run_bg(import_capture, src, work, self._DEV_KEYS[self.dev_kind.currentIndex()], self.cm_path.text() or None,
                    self.cm_quality.currentText(), done=done)

    def make_markers(self):
        from ..scale import make_marker_sheet

        p, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Marker sheet", "aruco_sheet.png", "PNG (*.png)")
        if p:
            make_marker_sheet(p, self.mk_dict.currentText(), range(self.mk_first.value(), self.mk_first.value() + self.mk_count.value()),
                              self.mk_mm.value())
            self.log(f"wrote {p}; print at 100 % and check one marker with a ruler")

    def run_colmap(self):
        from ..reconstruct import run_colmap

        self.settings.setValue("colmap", self.cm_path.text())
        imgs = self.cm_imgs.text()
        if not imgs:
            return self._error("Choose an image folder")
        work = Path(imgs).parent / (Path(imgs).name + "_colmap")
        self.run_bg(run_colmap, imgs, work, self.cm_path.text() or None, self.cm_quality.currentText(),
                    done=lambda p: (self.tabs.setCurrentIndex(0), self.load_scan(str(p))))


def _js(o):
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, np.generic):
        return o.item()
    return str(o)


def run(argv=None):
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(argv or sys.argv)
    app.setApplicationName(APP)
    app.setStyle("Fusion")
    icon_path = Path(__file__).with_name("icon.png")
    if icon_path.exists():
        app.setWindowIcon(QtGui.QIcon(str(icon_path)))
    w = MainWindow()
    w.show()
    args = [a for a in (argv or sys.argv)[1:] if not a.startswith("-") and a != "gui"]
    if args and Path(args[0]).exists():
        w.load_scan(args[0])
    return app.exec()


if __name__ == "__main__":
    sys.exit(run())
