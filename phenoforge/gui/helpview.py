"""In-app user guide: the Markdown pages in ``phenoforge/guide`` with a topic list and search."""

from __future__ import annotations

import re
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

GUIDE = Path(__file__).resolve().parent.parent / "guide"

# tab title -> guide page opened by F1 on that tab
TAB_TOPICS = {
    "Start": "index.md", "3D analysis": "3d-analysis.md", "Compare": "compare.md", "Images (2D)": "images-2d.md",
    "Roots": "roots-2d.md", "Roots 3D": "roots-3d.md", "Colour": "colour.md", "Validation": "validation.md",
    "3D print": "print.md", "Assistant": "assistant.md", "Tools": "tools.md",
}


def topics() -> list[tuple[str, Path]]:
    """(title, path) for every page, in the order of the guide's index (then alphabetical)."""
    pages = {p.name: p for p in GUIDE.glob("*.md")}
    order = []
    idx = GUIDE / "index.md"
    if idx.exists():
        order = [m for m in re.findall(r"\]\(([\w.-]+\.md)\)", idx.read_text(encoding="utf-8")) if m in pages]
    names = ["index.md"] * ("index.md" in pages) + [n for n in dict.fromkeys(order) if n != "index.md"]
    names += sorted(n for n in pages if n not in names)
    return [(_title(pages[n]), pages[n]) for n in names]


def _title(p: Path) -> str:
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return p.stem.replace("-", " ").capitalize()


class HelpWindow(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PhenoForge user guide")
        self.resize(1100, 800)
        self.setWindowFlag(QtCore.Qt.WindowMaximizeButtonHint)
        sp = QtWidgets.QSplitter()
        left = QtWidgets.QWidget()
        lv = QtWidgets.QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Search the guide…")
        self.search.textChanged.connect(self._filter)
        lv.addWidget(self.search)
        self.list = QtWidgets.QListWidget()
        self.list.currentItemChanged.connect(lambda it, _: it and self.show_page(it.data(QtCore.Qt.UserRole)))
        lv.addWidget(self.list)
        sp.addWidget(left)
        self.browser = QtWidgets.QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setSearchPaths([str(GUIDE)])
        self.browser.anchorClicked.connect(self._link)
        self.browser.setOpenLinks(False)
        self.browser.document().setDefaultStyleSheet("h1{color:#2f6b3a} h2{color:#2f6b3a} code{background:#eef5ec}"
                                                     "table{border-collapse:collapse} td,th{border:1px solid #c9d3c6;padding:3px}")
        sp.addWidget(self.browser)
        sp.setStretchFactor(1, 4)
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(sp)
        self._pages = topics()
        self._filter("")

    def _filter(self, text):
        self.list.blockSignals(True)
        self.list.clear()
        t = text.lower().strip()
        for title, p in self._pages:
            if not t or t in title.lower() or t in p.read_text(encoding="utf-8").lower():
                it = QtWidgets.QListWidgetItem(title)
                it.setData(QtCore.Qt.UserRole, str(p))
                self.list.addItem(it)
        self.list.blockSignals(False)

    def show_page(self, page):
        p = Path(page)
        if not p.is_absolute():
            p = GUIDE / p
        if not p.exists():
            self.browser.setPlainText(f"Guide page not found: {p.name}")
            return
        self.browser.setMarkdown(p.read_text(encoding="utf-8"))
        for i in range(self.list.count()):
            if Path(self.list.item(i).data(QtCore.Qt.UserRole)).name == p.name:
                self.list.blockSignals(True)
                self.list.setCurrentRow(i)
                self.list.blockSignals(False)
        if self.search.text().strip():  # highlight the first hit
            self.browser.find(self.search.text().strip())

    def _link(self, url: QtCore.QUrl):
        target = url.toString()
        if url.scheme() in ("http", "https", "mailto"):
            QtGui.QDesktopServices.openUrl(url)
        elif target.split("#")[0].endswith(".md"):
            self.show_page(target.split("#")[0])
        elif (GUIDE / target).exists() or Path(target).exists():
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(GUIDE / target if (GUIDE / target).exists() else target)))
