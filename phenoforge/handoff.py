"""Wi-Fi handoff: receive scans from a phone over the local network.

Scanning apps on the iPhone export packages (.ftscan/.zip), meshes and clouds (.ply/.usdz),
photos and videos. Rather than a custom discovery protocol, the PC runs a tiny upload
server: it shows a URL and a QR code, the phone camera opens the URL in Safari, and the
user picks files from the Files app. Each file is streamed straight to an inbox folder
(as ``name.part``, renamed when complete) and ``on_file(path)`` fires so the GUI or CLI
can import it into the library.

Security: this is meant for a trusted lab LAN. A random token in the URL stops casual
access from other devices on the network, but the transport is plain HTTP (not
encrypted), so do not run it on public or untrusted networks.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import socket
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

MAX_BYTES = 4 * 1024 ** 3                   # refuse single files over 4 GB
CHUNK = 1024 * 1024
DRAIN_BYTES = 16 * 1024 * 1024             # read and discard rejected bodies up to this size
ALLOWED_EXT = {
    ".ftscan", ".zip", ".ply", ".pcd", ".obj", ".glb", ".gltf", ".usdz", ".usd",
    ".las", ".laz", ".xyz", ".jpg", ".jpeg", ".png", ".heic", ".tif", ".tiff", ".dng",
    ".cr2", ".nef", ".arw", ".mov", ".mp4", ".m4v", ".json", ".csv",
}


def lan_ip() -> str:
    """Best-guess LAN IPv4 of this PC (the interface used to reach the internet)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))   # UDP connect sends nothing; just picks a route
        ip = s.getsockname()[0]
        return ip if ip and not ip.startswith("0.") else "127.0.0.1"
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def safe_filename(name: str) -> str:
    """Strip directories and unsafe characters, keeping the extension."""
    name = urllib.parse.unquote(name or "").replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^A-Za-z0-9._ ()+-]+", "_", name).strip(" .")
    stem, ext = os.path.splitext(name)
    return (stem[:120] or "upload") + ext.lower()


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


class _Handler(BaseHTTPRequestHandler):
    server_version = "PhenoForgeHandoff/1.0"
    hub: "HandoffServer"                     # set on the subclass made per server

    # -- helpers ---------------------------------------------------------------------------
    def log_message(self, fmt, *args):       # silence default stderr logging
        pass

    def _send(self, code: int, body: bytes, ctype: str = "text/plain; charset=utf-8",
              close: bool = False) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if close:                            # body may be unread; do not reuse the socket
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj, close: bool = False) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json", close)

    def _reject(self, code: int, msg: str) -> None:
        # Drain a small unread body first: closing a socket with pending data makes Windows
        # send a reset, and the client never sees the error response.
        try:
            left = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            left = 0
        if 0 < left <= DRAIN_BYTES:
            while left > 0:
                chunk = self.rfile.read(min(CHUNK, left))
                if not chunk:
                    break
                left -= len(chunk)
        self._json(code, {"error": msg}, close=True)

    def _query(self) -> tuple[str, dict[str, str]]:
        u = urllib.parse.urlsplit(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        return u.path, q

    def _authorised(self, q: dict[str, str]) -> bool:
        given = q.get("t") or self.headers.get("X-Token") or ""
        return secrets.compare_digest(given, self.hub.token)

    # -- routes ----------------------------------------------------------------------------
    def do_GET(self):
        path, q = self._query()
        if path in ("/", "/index.html"):
            page = _PAGE.replace("%EXT%", json.dumps(sorted(ALLOWED_EXT)))
            self._send(200, page.encode(), "text/html; charset=utf-8")
        elif path == "/list":
            if not self._authorised(q):
                return self._json(403, {"error": "bad token"})
            files = sorted((p for p in self.hub.inbox.iterdir()
                            if p.is_file() and p.suffix != ".part"),
                           key=lambda p: p.stat().st_mtime, reverse=True)
            self._json(200, [{"name": p.name, "size": p.stat().st_size} for p in files[:200]])
        elif path == "/favicon.ico":
            self._send(204, b"")
        else:
            self._send(404, b"not found")

    def do_POST(self):
        path, q = self._query()
        hub = self.hub
        who = self.client_address[0]
        if path != "/upload":
            return self._reject(404, "not found")
        if not self._authorised(q):
            hub.log(f"[handoff] {who} upload refused: bad token")
            return self._reject(403, "bad or missing token")
        name = safe_filename(q.get("name") or self.headers.get("X-Filename") or "")
        ext = os.path.splitext(name)[1]
        if ext not in ALLOWED_EXT:
            hub.log(f"[handoff] {who} upload refused: {name} (type {ext or 'none'} not allowed)")
            return self._reject(415, f"file type {ext or '(none)'} not accepted")
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self._json(411, {"error": "Content-Length required"}, close=True)
        if length < 0 or length > MAX_BYTES:
            hub.log(f"[handoff] {who} upload refused: {name} is {_human(length)} (> 4 GB)")
            return self._reject(413, "file larger than 4 GB")

        part, final = hub._reserve(name)
        got = 0
        try:
            with open(part, "r+b") as f:
                while got < length:
                    chunk = self.rfile.read(min(CHUNK, length - got))
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
            if got != length:
                raise ConnectionResetError(f"connection closed after {got} of {length} bytes")
            final = hub._commit(part, final)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, TimeoutError,
                OSError) as e:
            part.unlink(missing_ok=True)
            hub.log(f"[handoff] {who} upload of {name} failed: {e}")
            self.close_connection = True
            try:
                self._json(400, {"error": "upload incomplete"}, close=True)
            except OSError:
                pass
            return
        hub.log(f"[handoff] {who} received {final.name} ({_human(length)})")
        self._json(200, {"ok": True, "name": final.name, "size": length})
        if hub.on_file is not None:
            try:
                hub.on_file(final)
            except Exception as e:          # never let a callback bug kill the server
                hub.log(f"[handoff] on_file callback failed for {final.name}: {e}")


class HandoffServer:
    """LAN upload server; see the module docstring. ``on_file`` runs on a server thread."""

    def __init__(self, inbox, port: int = 8765, token: str | None = None, on_file=None,
                 log=print):
        self.inbox = Path(inbox)
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.port = port
        self.token = token or secrets.token_urlsafe(6)
        self.on_file = on_file
        self.log = log
        self._lock = threading.Lock()
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # file naming: pick a unique name and create its .part under a lock
    def _taken(self, p: Path) -> bool:
        return p.exists() or p.with_name(p.name + ".part").exists()

    def _unique(self, name: str) -> Path:
        stem, ext = os.path.splitext(name)
        p, i = self.inbox / name, 1
        while self._taken(p):
            p, i = self.inbox / f"{stem}_{i}{ext}", i + 1
        return p

    def _reserve(self, name: str) -> tuple[Path, Path]:
        with self._lock:
            final = self._unique(name)
            part = final.with_name(final.name + ".part")
            part.touch(exist_ok=False)
        return part, final

    def _commit(self, part: Path, final: Path) -> Path:
        with self._lock:
            if final.exists():               # something else claimed it meanwhile
                stem, ext = os.path.splitext(final.name)
                i = 1
                while (self.inbox / f"{stem}_{i}{ext}").exists():
                    i += 1
                final = self.inbox / f"{stem}_{i}{ext}"
            part.rename(final)
        return final

    # -- lifecycle -------------------------------------------------------------------------
    def start(self) -> None:
        if self._httpd is not None:
            return
        handler = type("Handler", (_Handler,), {"hub": self})
        self._httpd = ThreadingHTTPServer(("0.0.0.0", self.port), handler)
        self._httpd.daemon_threads = True
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                        name="phenoforge-handoff", daemon=True)
        self._thread.start()
        self.log(f"[handoff] serving {self.url}  ->  {self.inbox}")

    def stop(self) -> None:
        if self._httpd is None:
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._httpd = self._thread = None
        self.log("[handoff] stopped")

    @property
    def running(self) -> bool:
        return self._httpd is not None

    @property
    def url(self) -> str:
        return f"http://{lan_ip()}:{self.port}/?t={self.token}"

    def qr_image(self, size: int = 360) -> np.ndarray:
        """RGB uint8 QR code of ``url`` with a white quiet zone, about ``size`` px square."""
        import cv2
        qr = cv2.QRCodeEncoder.create().encode(self.url)        # 255 white / 0 black
        if qr.ndim == 3:
            qr = cv2.cvtColor(qr, cv2.COLOR_BGR2GRAY)
        qr = cv2.copyMakeBorder(qr, 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=255)
        scale = max(1, size // qr.shape[0])
        qr = cv2.resize(qr, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
        pad = max(0, size - qr.shape[0])
        qr = cv2.copyMakeBorder(qr, pad // 2, pad - pad // 2, pad // 2, pad - pad // 2,
                                cv2.BORDER_CONSTANT, value=255)
        return np.ascontiguousarray(np.repeat(qr[:, :, None], 3, axis=2), dtype=np.uint8)

    def qr_ascii(self) -> str:
        """The QR code as text (two characters per module) for a terminal."""
        import cv2
        qr = cv2.QRCodeEncoder.create().encode(self.url)
        if qr.ndim == 3:
            qr = cv2.cvtColor(qr, cv2.COLOR_BGR2GRAY)
        return "\n".join("".join("##" if v < 128 else "  " for v in row) for row in qr)


def serve_forever(inbox, port: int = 8765, token: str | None = None, log=print) -> None:
    """Run the handoff server in the foreground until Ctrl+C (for the CLI)."""
    srv = HandoffServer(inbox, port=port, token=token, log=log)
    srv.start()
    try:
        log(srv.qr_ascii())
    except Exception:
        pass
    log(f"\nOn the iPhone (same Wi-Fi): scan the QR code with the Camera, or open\n"
        f"    {srv.url}\n"
        f"in Safari, tap 'Choose files', pick the exported scans from Files and tap Upload.\n"
        f"Files are saved to {Path(inbox).resolve()}.  Press Ctrl+C to stop.")
    stop = threading.Event()
    try:
        while not stop.wait(0.5):            # short waits keep Ctrl+C responsive on Windows
            pass
    except KeyboardInterrupt:
        pass
    finally:
        srv.stop()


_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PhenoForge upload</title>
<style>
:root{color-scheme:light dark;--bg:#f6f7f4;--fg:#1d2420;--card:#fff;--line:#d9ddd6;--acc:#2f7d4f;--bad:#b3261e}
@media (prefers-color-scheme:dark){:root{--bg:#141815;--fg:#e8ece8;--card:#1f2521;--line:#333b35;--acc:#5cbf83;--bad:#ff8a80}}
*{box-sizing:border-box}body{margin:0;padding:16px;font:17px/1.4 -apple-system,system-ui,sans-serif;background:var(--bg);color:var(--fg)}
h1{font-size:22px;margin:4px 0 4px}p{margin:4px 0 14px;opacity:.8}
.btn{display:block;width:100%;padding:18px;margin:10px 0;border:0;border-radius:14px;font-size:19px;font-weight:600;text-align:center;cursor:pointer}
.pick{background:var(--card);color:var(--fg);border:2px dashed var(--line)}
.go{background:var(--acc);color:#fff}.go:disabled{opacity:.4}
input[type=file]{display:none}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 12px;margin:8px 0}
.row{display:flex;justify-content:space-between;gap:8px;font-size:15px;word-break:break-all}
progress{width:100%;height:10px;margin-top:6px}.ok{color:var(--acc)}.err{color:var(--bad)}
h2{font-size:17px;margin:20px 0 6px}
</style></head><body>
<h1>Send scans to PhenoForge</h1>
<p>Pick exported scans, meshes, photos or videos from Files, then tap Upload. Keep this page open until every file shows Done.</p>
<form id="f" onsubmit="return false">
<label class="btn pick" for="files">Choose files</label>
<input id="files" name="files" type="file" multiple>
<button class="btn go" id="go" disabled>Upload</button>
</form>
<div id="queue"></div>
<h2>Received on the PC</h2><div id="got"><p>Nothing yet.</p></div>
<script>
const T=new URLSearchParams(location.search).get('t')||'';
const $=id=>document.getElementById(id);let picked=[];
function human(n){const u=['B','KB','MB','GB'];let i=0;while(n>=1024&&i<3){n/=1024;i++}return (i?n.toFixed(1):n)+' '+u[i]}
function esc(s){return s.replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
$('files').onchange=e=>{picked=[...e.target.files];$('queue').innerHTML='';
 picked.forEach((f,i)=>{$('queue').insertAdjacentHTML('beforeend',`<div class="card"><div class="row"><span>${esc(f.name)}</span><span id="s${i}">${human(f.size)}</span></div><progress id="p${i}" max="1" value="0"></progress></div>`)});
 $('go').disabled=!picked.length};
const EXT=new Set(%EXT%);
function send(f,i){const e=(f.name.match(/\.[^.]+$/)||[''])[0].toLowerCase();
 if(!EXT.has(e)){$('s'+i).innerHTML='<b class="err">Type '+esc(e||'(none)')+' not accepted</b>';return Promise.resolve()}
 if(f.size>4*1024**3){$('s'+i).innerHTML='<b class="err">Larger than 4 GB</b>';return Promise.resolve()}
 return new Promise(res=>{const x=new XMLHttpRequest();
 x.open('POST','/upload?t='+encodeURIComponent(T)+'&name='+encodeURIComponent(f.name));
 x.setRequestHeader('Content-Type','application/octet-stream');
 x.upload.onprogress=e=>{if(e.lengthComputable){$('p'+i).value=e.loaded/e.total;$('s'+i).textContent=Math.round(100*e.loaded/e.total)+'%'}};
 x.onload=()=>{let m='';try{m=JSON.parse(x.responseText).error||''}catch(_){}
  if(x.status==200){$('p'+i).value=1;$('s'+i).innerHTML='<b class="ok">Done</b>'}else{$('s'+i).innerHTML='<b class="err">'+esc(m||('Error '+x.status))+'</b>'}res()};
 x.onerror=()=>{$('s'+i).innerHTML='<b class="err">Network error</b>';res()};x.send(f)})}
$('go').onclick=async()=>{$('go').disabled=true;for(let i=0;i<picked.length;i++){await send(picked[i],i);refresh()}$('go').disabled=false};
async function refresh(){try{const r=await fetch('/list?t='+encodeURIComponent(T));
 if(r.status==403){$('got').innerHTML='<p class="err">This link is missing its access code. Scan the QR code on the PC again.</p>';return}
 const l=await r.json();$('got').innerHTML=l.length?l.map(f=>`<div class="card row"><span>${esc(f.name)}</span><span>${human(f.size)}</span></div>`).join(''):'<p>Nothing yet.</p>'}catch(_){}}
refresh();setInterval(refresh,5000);
</script></body></html>
"""
