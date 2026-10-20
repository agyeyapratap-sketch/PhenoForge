"""Dialogs for the jobs that do not need their own tab: Wi-Fi receive, batch analysis,
frame check, head detector, narrated root video and video scale evidence.

Each dialog runs its work through ``MainWindow.run_bg`` so the window stays responsive and
messages go to the log.
"""

from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets


def _row(*widgets):
    h = QtWidgets.QHBoxLayout()
    for w in widgets:
        h.addWidget(w)
    return h


def _path_field(parent, placeholder="", folder=False, save=False, filt="All files (*)"):
    """Line edit plus a Browse button; returns (layout, line_edit)."""
    e = QtWidgets.QLineEdit()
    e.setPlaceholderText(placeholder)
    b = QtWidgets.QPushButton("Browse…")

    def pick():
        if folder:
            p = QtWidgets.QFileDialog.getExistingDirectory(parent, "Choose a folder", e.text())
        elif save:
            p = QtWidgets.QFileDialog.getSaveFileName(parent, "Save as", e.text(), filt)[0]
        else:
            p = QtWidgets.QFileDialog.getOpenFileName(parent, "Choose a file", e.text(), filt)[0]
        if p:
            e.setText(p)

    b.clicked.connect(pick)
    return _row(e, b), e


def _hint(text):
    l = QtWidgets.QLabel(f"<small style='color:#5b6670'>{text}</small>")
    l.setWordWrap(True)
    return l


# --------------------------------------------------------------------------- Wi-Fi receive
class _Bridge(QtCore.QObject):
    arrived = QtCore.Signal(str)


class ReceiveDialog(QtWidgets.QDialog):
    """Run the LAN upload server and show its QR code; files are handed to the main window."""

    def __init__(self, main):
        super().__init__(main)
        self.main, self.server = main, None
        self.setWindowTitle("Receive scans from a phone over Wi-Fi")
        self.resize(760, 620)
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(QtWidgets.QLabel(
            "<b>1.</b> Connect the phone to the same Wi-Fi network as this PC.<br>"
            "<b>2.</b> Press <b>Start</b>, then point the iPhone camera at the QR code and tap the link.<br>"
            "<b>3.</b> On the web page, tap <b>Choose files</b>, pick the exported .ftscan (or photos, videos, PLY…) and send."))
        f = QtWidgets.QFormLayout()
        inbox = Path(main.workspace.root if main.workspace else Path.home() / "PhenoForge") / "inbox"
        h, self.inbox = _path_field(self, folder=True)
        self.inbox.setText(str(inbox))
        f.addRow("Save files to", h)
        self.port = QtWidgets.QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(int(main.settings.value("handoff_port", 8765)))
        f.addRow("Port", self.port)
        self.to_library = QtWidgets.QCheckBox("Add each scan to the library session selected on the left")
        self.to_library.setChecked(main._selected("session") is not None)
        f.addRow(self.to_library)
        self.auto_open = QtWidgets.QCheckBox("Open each scan as soon as it arrives")
        self.auto_open.setChecked(True)
        f.addRow(self.auto_open)
        lay.addLayout(f)
        self.start_btn = QtWidgets.QPushButton("Start")
        self.start_btn.setStyleSheet("font-weight:bold;padding:6px")
        self.start_btn.clicked.connect(self.toggle)
        lay.addWidget(self.start_btn)
        mid = QtWidgets.QHBoxLayout()
        self.qr = QtWidgets.QLabel("QR code appears here")
        self.qr.setAlignment(QtCore.Qt.AlignCenter)
        self.qr.setMinimumSize(300, 300)
        mid.addWidget(self.qr)
        right = QtWidgets.QVBoxLayout()
        self.url = QtWidgets.QLineEdit(readOnly=True)
        right.addWidget(QtWidgets.QLabel("Or type this address in the phone's browser:"))
        right.addWidget(self.url)
        right.addWidget(QtWidgets.QLabel("Received:"))
        self.received = QtWidgets.QListWidget()
        right.addWidget(self.received, 1)
        mid.addLayout(right, 1)
        lay.addLayout(mid, 1)
        lay.addWidget(_hint("Use this on a trusted lab or home network only. The link contains an access code, but the "
                            "transfer is not encrypted. If the phone cannot open the page, allow Python/PhenoForge through "
                            "the Windows firewall for private networks, or try another port."))
        self.bridge = _Bridge()
        self.bridge.arrived.connect(self._arrived)

    def toggle(self):
        if self.server:
            self.server.stop()
            self.server = None
            self.start_btn.setText("Start")
            self.qr.setText("Stopped")
            self.url.clear()
            return
        from ..handoff import HandoffServer

        try:
            Path(self.inbox.text()).mkdir(parents=True, exist_ok=True)
            self.server = HandoffServer(self.inbox.text(), port=self.port.value(),
                                        on_file=lambda p: self.bridge.arrived.emit(str(p)), log=self.main.log)
            self.server.start()
        except OSError as e:
            self.server = None
            return self.main._error(f"Could not start on port {self.port.value()}: {e}. Try another port.")
        self.main.settings.setValue("handoff_port", self.port.value())
        self.start_btn.setText("Stop")
        self.url.setText(self.server.url)
        rgb = self.server.qr_image(320)
        img = QtGui.QImage(rgb.data, rgb.shape[1], rgb.shape[0], 3 * rgb.shape[1], QtGui.QImage.Format_RGB888).copy()
        self.qr.setPixmap(QtGui.QPixmap.fromImage(img))
        self.main.log(f"Wi-Fi receive started: {self.server.url}")

    def _arrived(self, path):
        self.received.addItem(Path(path).name)
        self.main.log(f"received {path}")
        from ..io import SUPPORTED

        p = Path(path)
        if p.suffix.lower() not in SUPPORTED:
            return
        key = None
        if self.to_library.isChecked() and self.main._selected("session"):
            s = self.main._selected("session")
            rec = self.main.workspace.import_scan(s[1], s[2], p)
            key = ("scan", s[1], s[2], rec["id"])
            p = Path(rec["file"])
            self.main.refresh_tree()
            self.main.log(f"added to the library as {rec['id']}")
        if self.auto_open.isChecked():
            self.main.open_path(str(p), rec=key)

    def closeEvent(self, e):
        if self.server:
            self.server.stop()
            self.server = None
        super().closeEvent(e)


# --------------------------------------------------------------------------- batch
class BatchDialog(QtWidgets.QDialog):
    """Analyse every scan in a folder with one preset; writes per-scan files and all_scans.csv."""

    def __init__(self, main):
        super().__init__(main)
        from ..pipeline import PRESETS

        self.main = main
        self.setWindowTitle("Analyse a whole folder")
        self.resize(640, 360)
        f = QtWidgets.QFormLayout(self)
        h, self.src = _path_field(self, "folder with scans (.ftscan, .zip, .ply, .obj, .usdz …)", folder=True)
        f.addRow("Scans", h)
        h, self.out = _path_field(self, folder=True)
        self.out.setText(str(Path(main.workspace.root if main.workspace else Path.home() / "PhenoForge") / "batch_results"))
        f.addRow("Results folder", h)
        self.preset = QtWidgets.QComboBox()
        self.preset.addItems(PRESETS)
        self.preset.setCurrentText(main.preset_box.currentText())
        f.addRow("Settings", self.preset)
        self.use_tab = QtWidgets.QCheckBox("Use the current 3D-tab settings instead (scale, plants, leaves…)")
        f.addRow(self.use_tab)
        self.save_cloud = QtWidgets.QCheckBox("Also save each cleaned point cloud (.ply)")
        f.addRow(self.save_cloud)
        f.addRow(_hint("Each scan gets its own JSON and CSV files; <b>all_scans.csv</b> has one row per scan, ready for "
                       "Excel or R. Scans that fail are listed in the log and skipped."))
        go = QtWidgets.QPushButton("Run")
        go.setStyleSheet("font-weight:bold;padding:6px")
        go.clicked.connect(self.run)
        f.addRow(go)

    def run(self):
        from .. import pipeline

        if not self.src.text():
            return self.main._error("Choose a folder of scans")
        try:
            opt = self.main._options() if self.use_tab.isChecked() else pipeline.preset_options(self.preset.currentText())
        except Exception as e:
            return self.main._error(str(e))
        src, out, save_cloud = self.src.text(), self.out.text(), self.save_cloud.isChecked()

        def work(log=print):
            from .. import io
            from ..cli import _inputs
            from ..phenotype2d import write_csv

            files = _inputs([src])
            rows = []
            for i, f in enumerate(files, 1):
                log(f"[{i}/{len(files)}] {f.name}")
                try:
                    s, res = pipeline.run(io.load(f), opt, log=lambda *_: None)
                    pipeline.save_results(res, out, f.stem)
                    if save_cloud:
                        io.save_point_cloud(s, Path(out) / f"{f.stem}_clean.ply")
                    ids = {k: v for k, v in res.get("package", {}).items() if k in ("plant_id", "genotype", "treatment")}
                    rows.append({"scan": f.stem, **ids, **{k: v for k, v in res["plant"].items() if not isinstance(v, list)}})
                except Exception as e:  # keep going; report at the end
                    log(f"  FAILED {f.name}: {e}")
            if rows:
                write_csv(Path(out) / "all_scans.csv", rows)
            return len(rows), len(files)

        self.main.run_bg(work, done=lambda r: self.main.log(f"batch done: {r[0]} of {r[1]} scans; table in {Path(out) / 'all_scans.csv'}"))
        self.accept()


# --------------------------------------------------------------------------- frame check
class FrameCheckDialog(QtWidgets.QDialog):
    """Compare the as-loaded iPhonotype scan with the photos it was made from."""

    def __init__(self, main, scan):
        super().__init__(main)
        self.main, self.scan = main, scan
        self.setWindowTitle(f"Scan vs photos: {scan.name}")
        self.resize(1200, 760)
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(_hint("Each photo is compared with the 3D scan drawn from the same camera position. "
                            "IoU near 1 means the model matches what the camera saw; low values point to missing or "
                            "extra geometry, or a plant that moved during capture."))
        sp = QtWidgets.QSplitter()
        self.table = QtWidgets.QTableWidget()
        self.table.itemSelectionChanged.connect(self._show)
        sp.addWidget(self.table)
        from .app import ImageView

        self.view = ImageView()
        sp.addWidget(self.view)
        sp.setStretchFactor(1, 3)
        lay.addWidget(sp, 1)
        self.summary = QtWidgets.QLabel("Working…")
        lay.addWidget(self.summary)
        self.frames = {}
        self.rows = []
        main.run_bg(self._work, done=self._done)

    def _work(self, log=print):
        from .. import framecheck

        rows, summary = framecheck.compare_package(self.scan, log=log)
        frames = {f["name"]: f for f in framecheck.load_frames(self.scan.metadata["package"])}
        return rows, summary, frames

    def _done(self, out):
        from .app import table_from_rows

        self.rows, summary, self.frames = out
        table_from_rows(self.table, self.rows)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.summary.setText("  ·  ".join(f"{k}: {v:.3g}" if isinstance(v, float) else f"{k}: {v}" for k, v in summary.items()))
        if self.rows:
            self.table.selectRow(0)

    def _show(self):
        from .. import framecheck

        r = self.table.currentRow()
        if 0 <= r < len(self.rows) and self.rows[r].get("name") in self.frames:
            self.view.show_rgb(framecheck.compare_frame(self.scan, self.frames[self.rows[r]["name"]])["overlay"])


# --------------------------------------------------------------------------- head detector
class HeadDetectorDialog(QtWidgets.QDialog):
    """Train a wheat-head detector on labelled photos, or count heads in new photos."""

    def __init__(self, main):
        super().__init__(main)
        from ..heads import detector_available

        self.main = main
        self.setWindowTitle("Wheat-head detector (photos)")
        self.resize(680, 420)
        lay = QtWidgets.QVBoxLayout(self)
        ok, msg = detector_available()
        lay.addWidget(_hint(("Ready: " + msg) if ok else
                            f"<b>Optional add-on not installed.</b> {msg}. Training works best with an NVIDIA GPU."))
        tabs = QtWidgets.QTabWidget()
        w = QtWidgets.QWidget()
        f = QtWidgets.QFormLayout(w)
        h, self.data = _path_field(self, "folder with images/ and labels/ (YOLO format), or dataset.yaml", folder=True)
        f.addRow("Labelled photos", h)
        h, self.tout = _path_field(self, folder=True)
        self.tout.setText(str(Path.home() / "PhenoForge" / "head_detector"))
        f.addRow("Save model to", h)
        self.epochs = QtWidgets.QSpinBox()
        self.epochs.setRange(1, 2000)
        self.epochs.setValue(100)
        f.addRow("Epochs", self.epochs)
        f.addRow(_hint("Label 50–200 photos with a free tool such as Label Studio or CVAT (export: YOLO). One box per head."))
        b = QtWidgets.QPushButton("Train")
        b.clicked.connect(self.train)
        f.addRow(b)
        tabs.addTab(w, "1  Train")
        w = QtWidgets.QWidget()
        f = QtWidgets.QFormLayout(w)
        h, self.imgs = _path_field(self, "folder of photos", folder=True)
        f.addRow("Photos", h)
        h, self.weights = _path_field(self, "best.pt from training", filt="Model (*.pt)")
        self.weights.setText(main.settings.value("head_weights", ""))
        f.addRow("Model", h)
        h, self.dout = _path_field(self, folder=True)
        self.dout.setText(str(Path.home() / "PhenoForge" / "heads_detected"))
        f.addRow("Results folder", h)
        self.conf = QtWidgets.QDoubleSpinBox()
        self.conf.setRange(0.01, 0.99)
        self.conf.setValue(0.25)
        f.addRow("Confidence", self.conf)
        b = QtWidgets.QPushButton("Count heads")
        b.clicked.connect(self.detect)
        f.addRow(b)
        tabs.addTab(w, "2  Count heads")
        lay.addWidget(tabs)
        btn = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        btn.rejected.connect(self.reject)
        lay.addWidget(btn)
        if not ok:
            tabs.setEnabled(False)

    def train(self):
        from .. import heads

        d = Path(self.data.text())
        if not self.data.text():
            return self.main._error("Choose the labelled photos")

        def work(log=print):
            yaml = d if d.suffix == ".yaml" else heads.make_dataset_yaml(d / "images", d / "labels", d / "dataset.yaml")
            return heads.train_detector(yaml, self.tout.text(), epochs=self.epochs.value(), log=log)

        def done(p):
            self.weights.setText(str(p))
            self.main.settings.setValue("head_weights", str(p))
            self.main.log(f"head detector saved: {p}")

        self.main.run_bg(work, done=done)

    def detect(self):
        from .. import heads, phenotype2d

        if not (self.imgs.text() and self.weights.text()):
            return self.main._error("Choose photos and a trained model")
        imgs = sorted(p for p in Path(self.imgs.text()).iterdir() if p.suffix.lower() in phenotype2d.IMG_EXT)
        self.main.settings.setValue("head_weights", self.weights.text())
        self.main.run_bg(heads.detect_heads_images, imgs, self.weights.text(), self.dout.text(), conf=self.conf.value(),
                         done=lambda rows: self.main.log(f"{sum(r['head_count'] for r in rows)} heads in {len(rows)} photos; "
                                                         f"see {self.dout.text()}"))


# --------------------------------------------------------------------------- videos
class RootVideoDialog(QtWidgets.QDialog):
    """Narrated time-lapse of root images with traits per frame."""

    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.setWindowTitle("Narrated root video")
        self.resize(620, 330)
        f = QtWidgets.QFormLayout(self)
        h, self.src = _path_field(self, "folder of root photos, named in time order", folder=True)
        f.addRow("Photos", h)
        h, self.out = _path_field(self, save=True, filt="MP4 video (*.mp4)")
        self.out.setText(str(Path.home() / "PhenoForge" / "roots_video.mp4"))
        f.addRow("Save video as", h)
        self.title = QtWidgets.QLineEdit()
        self.title.setPlaceholderText("e.g. Rhizotron 3, genotype W123")
        f.addRow("Title", self.title)
        self.mmpp = QtWidgets.QDoubleSpinBox()
        self.mmpp.setRange(0, 100)
        self.mmpp.setDecimals(4)
        self.mmpp.setSuffix(" mm/px")
        f.addRow("Scale (0 = ArUco or pixels)", self.mmpp)
        self.aruco = QtWidgets.QDoubleSpinBox()
        self.aruco.setRange(0, 1000)
        self.aruco.setSuffix(" mm")
        f.addRow("ArUco marker side", self.aruco)
        self.seconds = QtWidgets.QDoubleSpinBox()
        self.seconds.setRange(0.5, 60)
        self.seconds.setValue(3)
        self.seconds.setSuffix(" s")
        f.addRow("Time per photo", self.seconds)
        self.voice = QtWidgets.QCheckBox("Spoken narration (Windows voice; subtitles are always written)")
        self.voice.setChecked(True)
        f.addRow(self.voice)
        b = QtWidgets.QPushButton("Make video")
        b.setStyleSheet("font-weight:bold;padding:6px")
        b.clicked.connect(self.run)
        f.addRow(b)

    def run(self):
        from .. import narrate, phenotype2d

        if not self.src.text():
            return self.main._error("Choose a folder of root photos")
        imgs = sorted(p for p in Path(self.src.text()).iterdir() if p.suffix.lower() in phenotype2d.IMG_EXT)
        self.main.run_bg(narrate.make_root_video, imgs, self.out.text(), mm_per_px=self.mmpp.value() or None,
                         aruco_mm=self.aruco.value(), seconds_per_image=self.seconds.value(), narrate=self.voice.isChecked(),
                         title=self.title.text(), done=self._done)
        self.accept()

    def _done(self, info):
        self.main.log(f"video: {info.get('video')}" + ("" if info.get("narrated") else f" (no voice: {info.get('note', '')})"))
        if info.get("video"):
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(info["video"])))


class ScaleEvidenceDialog(QtWidgets.QDialog):
    """Per-frame ArUco scale audit of a capture video."""

    def __init__(self, main):
        super().__init__(main)
        from ..scale import ARUCO_DICTS

        self.main = main
        self.setWindowTitle("Scale evidence from a capture video")
        self.resize(620, 280)
        f = QtWidgets.QFormLayout(self)
        f.addRow(_hint("Checks that the ArUco card stayed visible, sharp and the same size throughout the video: "
                       "a record you can keep with the data to show the scale was sound."))
        h, self.video = _path_field(self, filt="Videos (*.mp4 *.mov *.avi *.mkv *.m4v)")
        f.addRow("Video", h)
        self.mm = QtWidgets.QDoubleSpinBox()
        self.mm.setRange(1, 1000)
        self.mm.setValue(50)
        self.mm.setSuffix(" mm")
        f.addRow("Marker side", self.mm)
        self.dict = QtWidgets.QComboBox()
        self.dict.addItems(ARUCO_DICTS)
        self.dict.setCurrentText("DICT_4X4_50")
        f.addRow("Dictionary", self.dict)
        h, self.out = _path_field(self, folder=True)
        self.out.setText(str(Path.home() / "PhenoForge" / "scale_evidence"))
        f.addRow("Results folder", h)
        b = QtWidgets.QPushButton("Check video")
        b.clicked.connect(self.run)
        f.addRow(b)

    def run(self):
        from ..videoevidence import video_scale_evidence

        if not self.video.text():
            return self.main._error("Choose a video")
        out = self.out.text()
        self.main.run_bg(video_scale_evidence, self.video.text(), self.mm.value(), dictionary=self.dict.currentText(),
                         out_dir=out, done=lambda r: (self.main.log(f"scale evidence: {r[1]}"),
                                                      QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(out))))
        self.accept()
