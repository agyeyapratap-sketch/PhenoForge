"""OpenGL point cloud viewer widget (pyqtgraph), with colour modes and overlays."""

from __future__ import annotations

import time

import numpy as np
import pyqtgraph as pg
import pyqtgraph.opengl as gl
from OpenGL import GL
from OpenGL.GL import shaders
from PySide6 import QtCore, QtGui, QtWidgets

from ..clean import vegetation_indices
from ..scan import Scan, cluster_eps

MAX_DISPLAY = 1_500_000
MAX_SPLATS = 300_000
SPLAT_FALLBACK = 0.6  # sigma as a fraction of the 6th-neighbour distance when a cloud has no splat radii
SPLAT_SIGMAS = 2.5  # sprite half-width in Gaussian sigmas (beyond this the splat is ~invisible)


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


# fragment shaders: Gaussian falloff exp(-d^2 / 2 sigma^2) instead of hard discs
_FALLOFF = f"exp(-{0.5 * SPLAT_SIGMAS ** 2:.4f} * r2)"
_SPLAT_FRAG = {
    "core": """
        #ifdef GL_ES
        precision mediump float;
        #endif
        in vec4 v_color;
        out vec4 fragColor;
        void main() {
            vec2 xy = (gl_PointCoord - 0.5) * 2.0;
            float r2 = dot(xy, xy);
            if (r2 > 1.0) discard;
            fragColor = vec4(v_color.rgb, v_color.a * FALLOFF);
        }
    """,
    "legacy": """
        #ifdef GL_ES
        precision mediump float;
        #endif
        varying vec4 v_color;
        void main() {
            vec2 xy = (gl_PointCoord - 0.5) * 2.0;
            float r2 = dot(xy, xy);
            if (r2 > 1.0) discard;
            gl_FragColor = vec4(v_color.rgb, v_color.a * FALLOFF);
        }
    """,
}


class SplatItem(gl.GLScatterPlotItem):
    """World-sized point sprites with Gaussian alpha falloff, alpha-blended back to front."""

    _shaderProgram = None

    def __init__(self, pos: np.ndarray, color: np.ndarray, size: np.ndarray):
        super().__init__(pos=pos, color=color, size=size, pxMode=False)
        self._pos, self._col, self._size = pos, color, size
        self._last_eye = None
        # blended and depth-tested but not depth-written, so translucent splats never punch holes
        self.setGLOptions({GL.GL_DEPTH_TEST: True, GL.GL_BLEND: True, GL.GL_CULL_FACE: False,
                           # keep framebuffer alpha opaque (else the widget composites see-through)
                           "glBlendFuncSeparate": (GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA,
                                                   GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA),
                           "glDepthMask": (GL.GL_FALSE,)})

    def set_size(self, size: np.ndarray):
        self._size = size
        self._last_eye = None
        self.update()

    @staticmethod
    def getShaderProgram():
        klass = SplatItem
        if klass._shaderProgram is not None:
            return klass._shaderProgram
        from pyqtgraph.opengl.items import GLScatterPlotItem as base

        ctx = QtGui.QOpenGLContext.currentContext()
        es, ver = ctx.isOpenGLES(), ctx.format().version()
        core = ver >= ((3, 0) if es else (3, 1))
        head = ("#version 300 es\n" if core else "#version 100\n") if es else ("#version 140\n" if core else "#version 120\n")
        vert = (base.SHADER_CORE if core else base.SHADER_LEGACY)[GL.GL_VERTEX_SHADER]
        frag = _SPLAT_FRAG["core" if core else "legacy"].replace("FALLOFF", _FALLOFF)
        program = shaders.compileProgram(shaders.compileShader([head, vert], GL.GL_VERTEX_SHADER),
                                         shaders.compileShader([head, frag], GL.GL_FRAGMENT_SHADER))
        GL.glBindAttribLocation(program, 0, "a_position")
        GL.glBindAttribLocation(program, 1, "a_color")
        GL.glBindAttribLocation(program, 2, "a_size")
        GL.glLinkProgram(program)
        klass._shaderProgram = program
        return program

    def _sort_back_to_front(self):
        v = self.view()
        if v is None:
            return
        cp = v.cameraPosition()
        eye = np.array([cp.x(), cp.y(), cp.z()], np.float32)
        if self._last_eye is not None:
            c = v.opts["center"]
            dist = np.linalg.norm(eye - np.array([c.x(), c.y(), c.z()], np.float32)) + 1e-12
            if np.linalg.norm(eye - self._last_eye) / dist < 0.01:  # < ~0.5 deg moved: keep order
                return
        self._last_eye = eye
        d = self._pos - eye
        order = np.argsort(-np.einsum("ij,ij->i", d, d))
        super().setData(pos=self._pos[order], color=self._col[order], size=self._size[order])

    def paint(self):
        self._sort_back_to_front()
        super().paint()
        GL.glDepthMask(GL.GL_TRUE)  # restore for the items painted after us


class CloudViewer(QtWidgets.QWidget):
    cameraChanged = QtCore.Signal(dict)
    pointPicked = QtCore.Signal(int, object)  # index, xyz (Ctrl + click)
    autoOrbitChanged = QtCore.Signal(bool)

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
        self._splat_base: np.ndarray | None = None  # world-unit sprite sizes at point size 2
        self._orbit_timer = QtCore.QTimer(self)
        self._orbit_timer.setInterval(30)
        self._orbit_timer.timeout.connect(self._orbit_step)
        self._orbit_speed = 20.0
        self._orbit_t = 0.0

    # camera sync for side-by-side comparison
    def eventFilter(self, obj, ev):
        if obj is self.view and ev.type() == QtCore.QEvent.MouseButtonPress and self._orbit_timer.isActive():
            self.set_auto_orbit(False)  # user takes over the camera
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

    # auto orbit (turntable)
    def set_auto_orbit(self, on: bool, deg_per_sec: float = 20.0):
        self._orbit_speed = float(deg_per_sec)
        if on == self._orbit_timer.isActive():
            return
        if on:
            self._orbit_t = time.perf_counter()
            self._orbit_timer.start()
        else:
            self._orbit_timer.stop()
        self.autoOrbitChanged.emit(on)

    def _orbit_step(self):
        now = time.perf_counter()
        dt, self._orbit_t = min(now - self._orbit_t, 0.2), now
        self.view.orbit(self._orbit_speed * dt, 0)
        self._emit_camera()

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
        self._splat_base = None
        if self.scan is None or len(self.scan) == 0:
            return
        if self.mode == "Splat":
            self._draw_splats()
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

    def splat_arrays(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(positions, RGBA, world-unit sprite diameters) for Splat mode, subsampled to MAX_SPLATS.

        Uses the 3DGS ``splat_radius`` / ``splat_alpha`` extras when present, otherwise a
        radius from the median point spacing so any cloud renders as a filled surface."""
        s = self.scan
        idx = np.arange(len(s))
        if len(s) > MAX_SPLATS:
            idx = np.sort(np.random.default_rng(0).choice(len(s), MAX_SPLATS, replace=False))
        cols = (np.full((len(s), 3), 0.75) if s.colors is None else s.colors)[idx]
        r, a = s.extra("splat_radius"), s.extra("splat_alpha")
        if r is not None:
            r = np.asarray(r, float)[idx]
            lo, hi = np.quantile(r, [0.01, 0.99])
            r = np.clip(r, lo, min(hi, 4 * np.median(r)))  # tame big blurry floaters
        else:
            # subsampling widens the gaps, so grow the radius to match
            r = np.full(len(idx), SPLAT_FALLBACK * cluster_eps(s.points, 6, 1.0) * np.sqrt(len(s) / len(idx)))
        a = np.full(len(idx), 0.9) if a is None else np.asarray(a, float)[idx]
        rgba = np.column_stack([cols, a]).astype(np.float32)
        return s.points[idx].astype(np.float32), rgba, (2 * SPLAT_SIGMAS * r).astype(np.float32)

    def _draw_splats(self):
        pos, rgba, size = self.splat_arrays()
        self._splat_base = size
        self.points_item = SplatItem(pos, rgba, size * (self.point_size / 2.0))
        self.view.addItem(self.points_item)

    def set_mode(self, mode: str):
        self.mode = mode
        self.redraw()

    def set_point_size(self, s: float):
        self.point_size = s
        if isinstance(self.points_item, SplatItem) and self._splat_base is not None:
            self.points_item.set_size(self._splat_base * (s / 2.0))  # point size 2 = native splat size
        elif self.points_item is not None:
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
