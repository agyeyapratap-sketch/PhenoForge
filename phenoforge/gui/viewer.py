"""OpenGL point cloud viewer widget (pyqtgraph), with colour modes and overlays."""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
import pyqtgraph.opengl as gl
from PySide6 import QtCore, QtWidgets

from ..clean import vegetation_indices
from ..scan import Scan

MAX_DISPLAY = 1_500_000


def label_colours(labels: np.ndarray) -> np.ndarray:
    rng = np.random.default_rng(7)
    n = int(labels.max(initial=-1)) + 1
    pal = rng.random((max(n, 1), 3)) * 0.75 + 0.2
    c = np.full((len(labels), 3), 0.55)
    ok = labels >= 0
    c[ok] = pal[labels[ok]]
    return c


def colormap(v: np.ndarray, name: str = "viridis") -> np.ndarray:
    v = np.asarray(v, float)
    lo, hi = np.nanquantile(v, 0.02), np.nanquantile(v, 0.98)
    t = np.clip((v - lo) / (hi - lo + 1e-12), 0, 1)
    cm = pg.colormap.get(name)
    return cm.map(t, mode="float")[:, :3]


class CloudViewer(QtWidgets.QWidget):
    cameraChanged = QtCore.Signal(dict)
    pointPicked = QtCore.Signal(int, object)  # index, xyz (Ctrl + click)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view = gl.GLViewWidget()
        self.view.setBackgroundColor((24, 28, 30))
        self.view.opts["distance"] = 2.0
        self.grid = gl.GLGridItem()
        self.grid.setColor((80, 90, 90, 120))
        self.view.addItem(self.grid)
        self.points_item = None
        self.overlays: list = []
        self.scan: Scan | None = None
        self.mode = "RGB"
        self.point_size = 2.0
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.view)
        self._sync_guard = False
        self.view.installEventFilter(self)

    # camera sync for side-by-side comparison
    def eventFilter(self, obj, ev):
        if obj is self.view and ev.type() in (QtCore.QEvent.MouseMove, QtCore.QEvent.Wheel):
            QtCore.QTimer.singleShot(0, self._emit_camera)
        if (obj is self.view and ev.type() == QtCore.QEvent.MouseButtonPress
                and ev.modifiers() & QtCore.Qt.ControlModifier and self.scan is not None):
            i = self.pick(ev.position().x(), ev.position().y())
            if i is not None:
                self.pointPicked.emit(i, self.scan.points[i].copy())
            return True
        return False

    def pick(self, x: float, y: float, radius_px: float = 8.0):
        """Index of the visible scan point nearest the cursor (front-most within radius)."""
        pts = self.scan.points
        w, h = self.view.width(), self.view.height()
        proj = np.array(self.view.projectionMatrix().data(), float).reshape(4, 4).T
        view = np.array(self.view.viewMatrix().data(), float).reshape(4, 4).T
        P = np.hstack([pts, np.ones((len(pts), 1))]) @ (proj @ view).T
        ok = P[:, 3] > 1e-9
        ndc = P[:, :3] / np.where(ok, P[:, 3], 1)[:, None]
        sx = (ndc[:, 0] + 1) / 2 * w
        sy = (1 - ndc[:, 1]) / 2 * h
        d = np.hypot(sx - x, sy - y)
        cand = np.where(ok & (d <= radius_px))[0]
        if len(cand) == 0:
            return None
        return int(cand[np.argmin(ndc[cand, 2])])

    def _emit_camera(self):
        if not self._sync_guard:
            o = self.view.opts
            self.cameraChanged.emit({"distance": o["distance"], "elevation": o["elevation"],
                                     "azimuth": o["azimuth"], "center": o["center"]})

    def set_camera(self, cam: dict):
        self._sync_guard = True
        self.view.setCameraPosition(pos=cam["center"], distance=cam["distance"],
                                    elevation=cam["elevation"], azimuth=cam["azimuth"])
        self._sync_guard = False

    def set_scan(self, scan: Scan | None, reset_camera: bool = True):
        self.scan = scan
        self.redraw()
        if scan is not None and len(scan) and reset_camera:
            lo, hi = scan.bounds()
            c = (lo + hi) / 2
            ext = float(np.linalg.norm(hi - lo))
            self.view.setCameraPosition(pos=pg.Vector(*c), distance=ext * 1.3, elevation=25, azimuth=-60)
            g = 10 ** np.floor(np.log10(max(ext / 5, 1e-9)))
            self.grid.resetTransform()
            self.grid.setSpacing(g, g, g)
            self.grid.setSize(g * 20, g * 20, 1)
            self.grid.translate(c[0], c[1], scan.ground_z if scan.ground_z is not None else lo[2])

    def colours_for(self, mode: str) -> np.ndarray:
        s = self.scan
        if mode == "RGB" and s.colors is not None:
            return s.colors
        if mode == "Height":
            return colormap(s.points[:, 2], "viridis")
        if mode == "Greenness (ExG)" and s.colors is not None:
            return colormap(vegetation_indices(s.colors)["exg"], "CET-D13")
        if mode == "Plants" and s.labels is not None:
            return label_colours(s.labels)
        if mode == "Leaves" and "leaf_labels" in s.metadata:
            ll = np.asarray(s.metadata["leaf_labels"])
            if len(ll) == len(s):
                return label_colours(ll)
        if mode == "Scalar" and "scalar" in s.metadata:
            return colormap(np.asarray(s.metadata["scalar"]), "plasma")
        return np.full((len(s), 3), 0.75) if s.colors is None else s.colors

    def redraw(self):
        if self.points_item is not None:
            self.view.removeItem(self.points_item)
            self.points_item = None
        if self.scan is None or len(self.scan) == 0:
            return
        pts = self.scan.points
        cols = self.colours_for(self.mode)
        if len(pts) > MAX_DISPLAY:
            idx = np.random.default_rng(0).choice(len(pts), MAX_DISPLAY, replace=False)
            pts, cols = pts[idx], cols[idx]
        rgba = np.hstack([cols, np.ones((len(cols), 1))]).astype(np.float32)
        self.points_item = gl.GLScatterPlotItem(pos=pts.astype(np.float32), color=rgba, size=self.point_size, pxMode=True)
        self.points_item.setGLOptions("opaque")
        self.view.addItem(self.points_item)

    def set_mode(self, mode: str):
        self.mode = mode
        self.redraw()

    def set_point_size(self, s: float):
        self.point_size = s
        if self.points_item is not None:
            self.points_item.setData(size=s)

    def clear_overlays(self):
        for it in self.overlays:
            self.view.removeItem(it)
        self.overlays = []

    def add_hull(self, points: np.ndarray, colour=(1, 0.85, 0.2, 0.9)):
        from scipy.spatial import ConvexHull

        try:
            h = ConvexHull(points)
        except Exception:
            return
        edges = set()
        for simplex in h.simplices:
            for i in range(3):
                a, b = sorted((simplex[i], simplex[(i + 1) % 3]))
                edges.add((a, b))
        seg = np.array([[points[a], points[b]] for a, b in edges]).reshape(-1, 3)
        it = gl.GLLinePlotItem(pos=seg.astype(np.float32), color=colour, width=1.0, mode="lines")
        self.view.addItem(it)
        self.overlays.append(it)

    def add_markers(self, xyz: np.ndarray, colour=(1, 0.2, 0.2, 1), size=10):
        it = gl.GLScatterPlotItem(pos=np.asarray(xyz, np.float32), color=colour, size=size, pxMode=True)
        self.view.addItem(it)
        self.overlays.append(it)

    def snapshot(self, path: str):
        img = self.view.grabFramebuffer()
        img.save(path)
