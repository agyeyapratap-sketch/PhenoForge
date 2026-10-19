"""Local workspace: projects -> sessions -> scans, stored as plain folders and JSON.

Layout::

    <workspace>/
        workspace.json                  list of projects
        <project>/project.json          metadata, sessions
        <project>/<session>/<scan_id>/  the imported file(s), scan.json, results/

Nothing leaves the computer. Metadata fields are free-form; the GUI fills species,
genotype, treatment, plant/pot/tray id, QR text, GPS, date and notes.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import uuid
from pathlib import Path


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", s.strip())[:60] or "untitled"


class Workspace:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.index = self.root / "workspace.json"
        if not self.index.exists():
            self._write(self.index, {"projects": [], "created": _now()})

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _read(p: Path) -> dict:
        return json.loads(p.read_text(encoding="utf-8"))

    @staticmethod
    def _write(p: Path, d: dict) -> None:
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=2, default=str), encoding="utf-8")
        tmp.replace(p)

    # ------------------------------------------------------------ projects
    def projects(self) -> list[dict]:
        out = []
        for name in self._read(self.index)["projects"]:
            pj = self.root / name / "project.json"
            if pj.exists():
                out.append(self._read(pj))
        return out

    def create_project(self, name: str, **meta) -> dict:
        slug = _slug(name)
        d = self.root / slug
        d.mkdir(exist_ok=True)
        pj = d / "project.json"
        if pj.exists():
            return self._read(pj)
        proj = {"name": name, "slug": slug, "created": _now(), "sessions": [], **meta}
        self._write(pj, proj)
        idx = self._read(self.index)
        if slug not in idx["projects"]:
            idx["projects"].append(slug)
            self._write(self.index, idx)
        return proj

    def create_session(self, project: str, name: str | None = None, **meta) -> dict:
        pj = self.root / _slug(project) / "project.json"
        proj = self._read(pj)
        name = name or dt.date.today().isoformat()
        slug = _slug(name)
        (pj.parent / slug).mkdir(exist_ok=True)
        if not any(s["slug"] == slug for s in proj["sessions"]):
            proj["sessions"].append({"name": name, "slug": slug, "created": _now(), "scans": [], **meta})
            self._write(pj, proj)
        return next(s for s in proj["sessions"] if s["slug"] == slug)

    def import_scan(self, project: str, session: str, path, copy: bool = True, **meta) -> dict:
        src = Path(path)
        pj = self.root / _slug(project) / "project.json"
        proj = self._read(pj)
        sess = next(s for s in proj["sessions"] if s["slug"] == _slug(session))
        sid = f"{_slug(src.stem)}_{uuid.uuid4().hex[:6]}"
        d = pj.parent / sess["slug"] / sid
        (d / "results").mkdir(parents=True)
        if copy:
            if src.is_dir():
                shutil.copytree(src, d / src.name)
            else:
                shutil.copy2(src, d / src.name)
            stored = d / src.name
        else:
            stored = src
        rec = {"id": sid, "file": str(stored), "original": str(src), "imported": _now(), **meta}
        self._write(d / "scan.json", rec)
        sess["scans"].append(sid)
        self._write(pj, proj)
        return rec

    def scan_dir(self, project: str, session: str, scan_id: str) -> Path:
        return self.root / _slug(project) / _slug(session) / scan_id

    def scan_record(self, project: str, session: str, scan_id: str) -> dict:
        return self._read(self.scan_dir(project, session, scan_id) / "scan.json")

    def update_scan(self, project: str, session: str, scan_id: str, **fields) -> dict:
        p = self.scan_dir(project, session, scan_id) / "scan.json"
        rec = self._read(p)
        rec.update(fields)
        self._write(p, rec)
        return rec

    def save_results(self, project: str, session: str, scan_id: str, name: str, data: dict) -> Path:
        p = self.scan_dir(project, session, scan_id) / "results" / f"{_slug(name)}.json"
        self._write(p, {"saved": _now(), **data})
        return p

    def all_scans(self):
        """Yield (project, session, record) for every scan."""
        for proj in self.projects():
            for s in proj["sessions"]:
                for sid in s["scans"]:
                    try:
                        yield proj, s, self.scan_record(proj["slug"], s["slug"], sid)
                    except FileNotFoundError:
                        continue

    def export_table(self, path) -> str:
        """One CSV row per scan with metadata and the latest 'traits' result."""
        from .phenotype2d import write_csv

        rows = []
        for proj, sess, rec in self.all_scans():
            row = {"project": proj["name"], "session": sess["name"], **{k: v for k, v in rec.items() if not isinstance(v, (dict, list))}}
            tr = self.scan_dir(proj["slug"], sess["slug"], rec["id"]) / "results" / "traits.json"
            if tr.exists():
                t = self._read(tr)
                row.update({k: v for k, v in t.get("plant", t).items() if not isinstance(v, (dict, list))})
            rows.append(row)
        write_csv(path, rows)
        return str(path)


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")
