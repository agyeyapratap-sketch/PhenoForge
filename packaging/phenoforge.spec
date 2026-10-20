# PyInstaller spec for PhenoForge. Build from the repository root:
#   pyinstaller packaging/phenoforge.spec --noconfirm
# Produces dist/PhenoForge/PhenoForge.exe (GUI) and dist/PhenoForge/phenoforge-cli.exe (console).
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
datas, binaries, hidden = [], [], []
def _skip(name):
    return not any(part in name for part in (".examples", ".tests", ".test", "._tests"))


for pkg in ("open3d", "pyqtgraph", "skimage", "trimesh", "plyfile", "tifffile"):
    d, b, h = collect_all(pkg, filter_submodules=_skip)
    datas += d
    binaries += b
    hidden += h
for opt in ("pxr", "laspy", "lazrs", "rawpy"):
    try:
        d, b, h = collect_all(opt, filter_submodules=_skip)
        datas += d
        binaries += b
        hidden += h
    except Exception:
        pass
hidden += collect_submodules("phenoforge") + ["OpenGL.platform.win32", "OpenGL.arrays.numpymodule"]
datas += [(os.path.join(ROOT, "phenoforge", "gui", "icon.png"), "phenoforge/gui"),
          (os.path.join(ROOT, "phenoforge", "guide"), "phenoforge/guide")]  # in-app user guide
EXCLUDES = ["tkinter", "IPython", "jupyter", "notebook", "torch", "tensorflow"]

a = Analysis([os.path.join(SPECPATH, "launcher.py")], pathex=[ROOT], binaries=binaries, datas=datas,
             hiddenimports=hidden, excludes=EXCLUDES, noarchive=False)
pyz = PYZ(a.pure)
icon = os.path.join(SPECPATH, "phenoforge.ico")
gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name="PhenoForge", console=False, icon=icon)
cli = EXE(pyz, a.scripts, [], exclude_binaries=True, name="phenoforge-cli", console=True, icon=icon)
coll = COLLECT(gui, cli, a.binaries, a.datas, strip=False, upx=False, name="PhenoForge")
