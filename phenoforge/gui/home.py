"""Start page: one button per job, so new users never have to find the right tab first."""

from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtWidgets

# (task key, title, one-line description); the main window decides what each key does
TASKS = [
    ("Scans from a phone or 3D scanner", [
        ("ftscan", "Analyse an iPhonotype scan", "Open a .ftscan package. Plant ID, scale and the app's traits are read for you."),
        ("lidar", "Analyse a 3D scan", "PLY, OBJ, GLB, USDZ, LAS or PCD from a LiDAR or scanning app."),
        ("receive", "Receive from my phone (Wi-Fi)", "Show a QR code; send scans from the phone without cables."),
        ("photos", "Make 3D from photos or video", "Android, DSLR or turntable photos, reconstructed with COLMAP."),
        ("batch", "Analyse a whole folder", "Same settings for every scan; one CSV table at the end."),
    ]),
    ("What are you measuring?", [
        ("tray", "A tray or bench of plants", "Separate touching plants or pots, with traits per plant."),
        ("wheat", "Wheat: heads and tillers", "Count heads (spikes) and tillers; train a head detector on photos."),
        ("objects", "Fruit, tubers or seeds", "Length, width, thickness, volume and colour of each object."),
        ("roots3d", "Roots in 3D", "Root crowns, fibrous root systems and CT stacks."),
        ("images", "Photos from above (2D)", "Canopy cover and area for a folder of photos with an ArUco card."),
        ("roots2d", "Root photos or video (2D)", "Root length, tips and a narrated time-lapse video."),
    ]),
    ("Check and compare", [
        ("compare", "Compare two scans over time", "Analyse both with the same settings and see how each trait changed."),
        ("validate", "Check against hand measurements", "R², RMSE and agreement plots against your own data."),
        ("framecheck", "Check a scan against its photos", "Does the 3D model match what the camera saw? (iPhonotype)"),
    ]),
    ("Learn", [
        ("demo", "Try the demo", "A synthetic tray with known answers: press Run analysis."),
        ("guide", "Read the user guide", "Step-by-step help for every part of PhenoForge (F1 at any time)."),
    ]),
]


class HomePage(QtWidgets.QScrollArea):
    task = QtCore.Signal(str)
    openRecent = QtCore.Signal(str)

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        body = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(body)
        v.setContentsMargins(28, 20, 28, 20)
        title = QtWidgets.QLabel("<h1 style='margin:0'>What would you like to do?</h1>"
                                 "<p style='color:#5b6670'>Pick a job. PhenoForge chooses sensible settings, which you can "
                                 "still change in each tab. Press <b>F1</b> anywhere for help on that screen.</p>")
        title.setWordWrap(True)
        v.addWidget(title)
        for group, items in TASKS:
            v.addWidget(QtWidgets.QLabel(f"<h3 style='margin-bottom:2px'>{group}</h3>"))
            grid = QtWidgets.QGridLayout()
            grid.setSpacing(10)
            for i, (key, name, desc) in enumerate(items):
                grid.addWidget(self._card(key, name, desc), i // 3, i % 3)
            for c in range(3):
                grid.setColumnStretch(c, 1)
            v.addLayout(grid)
        v.addWidget(QtWidgets.QLabel("<h3 style='margin-bottom:2px'>Recent scans</h3>"))
        self.recent = QtWidgets.QListWidget()
        self.recent.setMaximumHeight(140)
        self.recent.itemDoubleClicked.connect(lambda it: self.openRecent.emit(it.data(QtCore.Qt.UserRole)))
        v.addWidget(self.recent)
        v.addStretch()
        self.setWidget(body)

    def _card(self, key, name, desc):
        b = QtWidgets.QPushButton()
        b.setCursor(QtCore.Qt.PointingHandCursor)
        b.setMinimumHeight(74)
        b.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        b.setStyleSheet("QPushButton{text-align:left;padding:10px 14px;border:1px solid #c9d3c6;border-radius:8px;background:#f6faf5}"
                        "QPushButton:hover{background:#e6f1e3;border-color:#2f6b3a}")
        lay = QtWidgets.QVBoxLayout(b)
        lay.setContentsMargins(12, 8, 12, 8)
        t = QtWidgets.QLabel(f"<b style='color:#2f6b3a;font-size:11pt'>{name}</b><br><span style='color:#33424a'>{desc}</span>")
        t.setWordWrap(True)
        t.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        lay.addWidget(t)
        b.setToolTip(desc)
        b.clicked.connect(lambda: self.task.emit(key))
        return b

    def set_recent(self, paths):
        self.recent.clear()
        for p in paths:
            it = QtWidgets.QListWidgetItem(f"{Path(p).name}    —    {Path(p).parent}")
            it.setData(QtCore.Qt.UserRole, p)
            it.setToolTip(p)
            self.recent.addItem(it)
        if not paths:
            self.recent.addItem("Scans you open appear here; double-click to open again.")
