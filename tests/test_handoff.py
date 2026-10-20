from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

import cv2
import numpy as np
import pytest

from phenoforge.handoff import HandoffServer, lan_ip, safe_filename


@pytest.fixture
def server(tmp_path):
    got = []
    srv = HandoffServer(tmp_path / "inbox", port=0, token="tok123", on_file=got.append,
                        log=lambda *a: None)
    srv.start()
    srv.received = got
    yield srv
    srv.stop()


def _upload(srv, name, data: bytes, token="tok123"):
    q = {"name": name}
    if token is not None:
        q["t"] = token
    url = f"http://127.0.0.1:{srv.port}/upload?" + urllib.parse.urlencode(q)
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/octet-stream"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None


def test_upload_ok(server):
    payload = bytes(range(256)) * 5000          # > one chunk
    code, body = _upload(server, "plant 01.ply", payload)
    assert code == 200 and body["name"] == "plant 01.ply"
    out = server.inbox / "plant 01.ply"
    assert out.read_bytes() == payload
    assert server.received == [out]
    assert not list(server.inbox.glob("*.part"))


def test_token_required(server):
    assert _upload(server, "a.ply", b"x", token=None)[0] == 403
    assert _upload(server, "a.ply", b"x", token="wrong")[0] == 403
    assert not any(server.inbox.iterdir()) and server.received == []


def test_bad_extension(server):
    assert _upload(server, "evil.exe", b"MZ")[0] == 415
    assert _upload(server, "noext", b"x")[0] == 415
    assert not any(server.inbox.iterdir())


def test_traversal_and_duplicates(server):
    assert _upload(server, "../../x.ply", b"1")[0] == 200
    assert _upload(server, "..\\..\\x.ply", b"2")[0] == 200
    assert _upload(server, "x.ply", b"3")[0] == 200
    names = sorted(p.name for p in server.inbox.iterdir())
    assert names == ["x.ply", "x_1.ply", "x_2.ply"]
    assert all(p.resolve().parent == server.inbox.resolve() for p in server.received)
    assert not (server.inbox.parent / "x.ply").exists()


def test_safe_filename():
    assert safe_filename("../../a/b/c.FTSCAN") == "c.ftscan"
    assert safe_filename("") == "upload"
    assert safe_filename("..") == "upload"


def test_qr_roundtrip(server):
    img = server.qr_image(360)
    assert img.dtype == np.uint8 and img.ndim == 3 and img.shape[2] == 3
    assert img.shape[0] == img.shape[1] == 360
    assert (img[0] == 255).all()                # white quiet zone
    text, _, _ = cv2.QRCodeDetector().detectAndDecode(img)
    assert text == server.url
    assert server.url.endswith(f":{server.port}/?t=tok123")


def test_index_page(server):
    with urllib.request.urlopen(f"http://127.0.0.1:{server.port}/", timeout=10) as r:
        html = r.read().decode()
    assert r.status == 200 and "<form" in html and 'type="file" multiple' in html
    assert "/upload" in html


def test_list_and_random_token(tmp_path):
    srv = HandoffServer(tmp_path, port=0, log=lambda *a: None)
    assert len(srv.token) >= 6
    assert lan_ip().count(".") == 3
    srv.start()
    try:
        url = f"http://127.0.0.1:{srv.port}/list?t={srv.token}"
        with urllib.request.urlopen(url, timeout=10) as r:
            assert json.loads(r.read()) == []
    finally:
        srv.stop()
