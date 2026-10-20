"""Narrated root-growth video from a time series of root images.

Each image (a rhizotron / root box / Petri dish photographed over days, or frames pulled
from a video) is segmented with :mod:`phenoforge.roots`; the overlay is shown with a caption
bar (total and primary length, laterals, tips, change since the previous frame) and the
frames are written to an MP4. One spoken sentence per frame ("Day 3: total root length 412
millimetres, up 18 percent; 14 tips.") is written as SRT subtitles and, when ``pyttsx3``
(offline SAPI5 on Windows, NSSpeech on macOS, eSpeak on Linux) and an ffmpeg binary
(``imageio-ffmpeg`` or ffmpeg on PATH) are available, synthesised and muxed into the video.
Speech synthesis is optional and never fatal: without it the result is a silent video + SRT.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

from . import roots
from .phenotype2d import read_image, write_csv

FPS = 10
MAX_WIDTH = 1280
BAR_H = 96


def _name_of(item, i: int) -> str:
    if isinstance(item, (str, os.PathLike)):
        return Path(item).stem
    return f"frame {i + 1}"


def _spoken_name(name: str) -> str:
    s = re.sub(r"[_\-]+", " ", name).strip()
    s = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", s)  # "day3" -> "day 3"
    return s[:1].upper() + s[1:] if s else s


def _length(tr: dict, key: str) -> tuple[float, str]:
    if f"{key}_mm" in tr:
        return float(tr[f"{key}_mm"]), "mm"
    return float(tr.get(f"{key}_px", 0.0)), "px"


def _sentence(name: str, tr: dict, prev_total: float | None) -> str:
    total, unit = _length(tr, "total_length")
    word = "millimetres" if unit == "mm" else "pixels"
    s = f"{_spoken_name(name)}: total root length {total:.0f} {word}"
    if prev_total is not None and prev_total > 0:
        pct = 100.0 * (total - prev_total) / prev_total
        if abs(pct) < 0.5:
            s += ", unchanged"
        else:
            s += f", {'up' if pct > 0 else 'down'} {abs(pct):.0f} percent"
    n = int(tr.get("n_tips", 0))
    s += f"; {n} tip{'s' if n != 1 else ''}."
    return s


def _fit(img: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Letterbox RGB ``img`` into (w, h) on a dark background."""
    import cv2

    w, h = size
    ih, iw = img.shape[:2]
    s = min(w / iw, h / ih)
    nw, nh = max(1, int(round(iw * s))), max(1, int(round(ih * s)))
    r = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
    out = np.full((h, w, 3), 20, np.uint8)
    y0, x0 = (h - nh) // 2, (w - nw) // 2
    out[y0:y0 + nh, x0:x0 + nw] = r
    return out


def _compose(overlay: np.ndarray, size: tuple[int, int], lines: list[str]) -> np.ndarray:
    """Overlay letterboxed above a caption bar; returns a BGR frame for the VideoWriter."""
    import cv2

    w, h = size
    body = _fit(overlay, (w, h - BAR_H))
    bar = np.full((BAR_H, w, 3), 30, np.uint8)
    scale = max(0.45, min(0.8, w / 1400))
    for k, txt in enumerate(lines[:3]):
        cv2.putText(bar, txt, (12, 28 + k * 30), cv2.FONT_HERSHEY_SIMPLEX, scale,
                    (255, 255, 255) if k == 0 else (200, 230, 255), 1 if k else 2, cv2.LINE_AA)
    return cv2.cvtColor(np.vstack([body, bar]), cv2.COLOR_RGB2BGR)


def _srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _ffmpeg_exe() -> str | None:
    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).exists():
            return exe
    except Exception:
        pass
    return shutil.which("ffmpeg")


_TTS_SCRIPT = r"""
import json, sys
import pyttsx3
jobs = json.loads(open(sys.argv[1], encoding="utf-8").read())
e = pyttsx3.init()
try:
    e.setProperty("rate", 175)
except Exception:
    pass
for text, path in jobs:
    e.save_to_file(text, path)
e.runAndWait()
"""


def _synthesise(sentences: list[str], work: Path, log=print) -> list[Path]:
    """Speak each sentence to a WAV with pyttsx3 in a child process (keeps COM/SAPI and its
    event loop away from the GUI thread, and a hung TTS engine can be killed by timeout)."""
    import json
    import importlib.util

    if importlib.util.find_spec("pyttsx3") is None:
        raise RuntimeError("pyttsx3 not installed (pip install pyttsx3)")
    wavs = [work / f"say_{i:04d}.wav" for i in range(len(sentences))]
    jobs = work / "tts_jobs.json"
    jobs.write_text(json.dumps([[s, str(p)] for s, p in zip(sentences, wavs)]), encoding="utf-8")
    script = work / "tts.py"
    script.write_text(_TTS_SCRIPT, encoding="utf-8")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    r = subprocess.run([sys.executable, str(script), str(jobs)], capture_output=True, text=True,
                       timeout=30 + 10 * len(sentences), creationflags=flags)
    if r.returncode != 0:
        raise RuntimeError(f"speech synthesis failed: {(r.stderr or r.stdout).strip()[-300:]}")
    missing = [p.name for p in wavs if not p.exists() or p.stat().st_size < 100]
    if missing:
        raise RuntimeError(f"speech engine produced no audio for {len(missing)} sentence(s)")
    return wavs


def _wav_seconds(p: Path) -> float:
    with wave.open(str(p), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def _concat_wavs(wavs: list[Path], durations: list[float], out: Path) -> None:
    """Join the per-sentence WAVs, each padded with silence to its frame's duration."""
    params = None
    chunks = []
    for p, d in zip(wavs, durations):
        with wave.open(str(p), "rb") as w:
            if params is None:
                params = w.getparams()
            elif (w.getnchannels(), w.getsampwidth(), w.getframerate()) != \
                    (params.nchannels, params.sampwidth, params.framerate):
                raise RuntimeError("speech clips have differing audio formats")
            data = w.readframes(w.getnframes())
        frame_bytes = params.nchannels * params.sampwidth
        want = int(round(d * params.framerate)) * frame_bytes
        chunks.append(data[:want] + b"\x00" * max(0, want - len(data)))
    with wave.open(str(out), "wb") as w:
        w.setnchannels(params.nchannels)
        w.setsampwidth(params.sampwidth)
        w.setframerate(params.framerate)
        w.writeframes(b"".join(chunks))


def _open_writer(path: Path, size: tuple[int, int], codecs=("avc1", "mp4v")):
    import cv2

    for cc in codecs:
        vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*cc), FPS, size)
        if vw.isOpened():
            return vw, cc
        vw.release()
    raise RuntimeError(f"OpenCV cannot write MP4 to {path}")


def make_root_video(images, out_mp4, mm_per_px: float | None = None, aruco_mm: float = 0.0,
                    roots_dark: bool | None = None, seconds_per_image: float = 3.0, narrate: bool = True,
                    title: str = "", log=print) -> dict:
    """Root-growth video with caption bar, SRT subtitles, traits CSV and optional speech.

    ``images``: paths or RGB arrays in time order. Scale: ``mm_per_px`` if given, else ArUco
    markers of side ``aruco_mm`` found in each image, else lengths stay in pixels.
    Writes ``out_mp4``, ``<out>.srt`` and ``<out>_traits.csv``. Returns
    ``{"video", "srt", "csv", "narrated", "note", "rows"}``.
    """
    import cv2

    images = list(images)
    if not images:
        raise ValueError("No images given")
    out = Path(out_mp4)
    if out.suffix.lower() != ".mp4":
        out = out.with_suffix(".mp4")
    out.parent.mkdir(parents=True, exist_ok=True)
    srt_path = out.with_suffix(".srt")
    csv_path = out.with_name(out.stem + "_traits.csv")

    # 1. analyse every image
    rows, overlays, sentences, captions = [], [], [], []
    prev = None
    for i, item in enumerate(images):
        name = _name_of(item, i)
        rgb = read_image(item) if isinstance(item, (str, os.PathLike)) else np.asarray(item)
        if rgb.ndim == 2:
            rgb = np.repeat(rgb[..., None], 3, 2)
        rgb = rgb[..., :3].astype(np.uint8)
        scale = mm_per_px
        if not scale and aruco_mm > 0:
            from .scale import image_mm_per_px

            scale, _ = image_mm_per_px(rgb, aruco_mm)
        mask = roots.root_mask(rgb, roots_dark=roots_dark)
        tr, draw = roots.root_traits(mask, mm_per_px=scale)
        overlays.append(roots.draw_overlay(rgb, mask, draw))
        total, unit = _length(tr, "total_length")
        primary, _ = _length(tr, "primary_length")
        prev_total = _length(prev, "total_length")[0] if prev is not None else None
        sentence = _sentence(name, tr, prev_total)
        if prev_total:
            change = f"{total - prev_total:+.1f} {unit} ({100 * (total - prev_total) / prev_total:+.0f}%) vs previous"
        else:
            change = "first frame" if prev is None else "no roots in previous frame"
        captions.append([f"{title + '  |  ' if title else ''}{name}  ({i + 1}/{len(images)})",
                         f"Total {total:.1f} {unit}   Primary {primary:.1f} {unit}   "
                         f"Laterals {tr['n_laterals']}   Tips {tr['n_tips']}",
                         change])
        sentences.append(sentence)
        row = {"frame": i + 1, "image": str(item) if isinstance(item, (str, os.PathLike)) else name,
               "name": name}
        row.update({k: v for k, v in tr.items()})
        row["change_total_pct"] = (100 * (total - prev_total) / prev_total) if prev_total else ""
        row["sentence"] = sentence
        rows.append(row)
        prev = tr
        log(f"[{i + 1}/{len(images)}] {sentence}")

    # 2. speech (optional, never fatal)
    narrated, note = False, ""
    durations = [float(seconds_per_image)] * len(images)
    work = Path(tempfile.mkdtemp(prefix="pf_narrate_"))
    audio = None
    ffmpeg = _ffmpeg_exe()
    try:
        if narrate:
            if ffmpeg is None:
                raise RuntimeError("no ffmpeg binary (pip install imageio-ffmpeg)")
            wavs = _synthesise(sentences, work, log)
            durations = [max(seconds_per_image, _wav_seconds(p) + 0.4) for p in wavs]
            audio = work / "narration.wav"
            _concat_wavs(wavs, durations, audio)
        else:
            note = "narration off"
    except Exception as e:  # speech must never stop the video
        audio = None
        durations = [float(seconds_per_image)] * len(images)
        note = f"silent video: {e}"
        log(f"Narration unavailable ({e}); writing a silent video with subtitles")

    # 3. video frames
    h0, w0 = overlays[0].shape[:2]
    s = min(1.0, MAX_WIDTH / w0)
    W = int(round(w0 * s)) // 2 * 2
    H = (int(round(h0 * s)) + BAR_H) // 2 * 2
    # with ffmpeg at hand, OpenCV writes an intermediate MPEG-4 file and ffmpeg makes the H.264
    # (+ narration) MP4; without it, OpenCV writes the final file (H.264 if its build can)
    silent = work / "silent.mp4" if ffmpeg else out
    vw, codec = _open_writer(silent, (W, H), ("mp4v",) if ffmpeg else ("avc1", "mp4v"))
    try:
        for ov, cap, d in zip(overlays, captions, durations):
            frame = _compose(ov, (W, H), cap)
            for _ in range(max(1, int(round(d * FPS)))):
                vw.write(frame)
    finally:
        vw.release()

    # 4. H.264 encode and mux narration
    if ffmpeg:
        base = [ffmpeg, "-y", "-loglevel", "error", "-i", str(silent)]
        base += ["-i", str(audio)] if audio is not None else []
        tail = (["-c:a", "aac", "-b:a", "128k", "-shortest"] if audio is not None else ["-an"])
        tail += ["-movflags", "+faststart", str(out)]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            r = subprocess.run(base + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast"] + tail,
                               capture_output=True, text=True, timeout=600, creationflags=flags)
            if r.returncode != 0:  # no libx264 in this ffmpeg build: keep OpenCV's stream
                r = subprocess.run(base + ["-c:v", "copy"] + tail, capture_output=True, text=True,
                                   timeout=600, creationflags=flags)
            if r.returncode != 0:
                raise RuntimeError(r.stderr.strip()[-300:])
            codec = "h264" if "libx264" in r.args else codec
            if audio is not None:
                narrated, note = True, "narrated (pyttsx3 + ffmpeg)"
        except Exception as e:
            shutil.copyfile(silent, out)
            if audio is not None:
                note = f"silent video: muxing audio failed ({e})"
            log(f"ffmpeg step failed ({e}); kept OpenCV's {codec} video")

    # 5. subtitles + CSV
    t = 0.0
    with open(srt_path, "w", encoding="utf-8") as fh:
        for k, (sent, d) in enumerate(zip(sentences, durations), 1):
            n = max(1, int(round(d * FPS)))
            fh.write(f"{k}\n{_srt_time(t)} --> {_srt_time(t + n / FPS)}\n{sent}\n\n")
            rows[k - 1]["start_s"] = round(t, 3)
            rows[k - 1]["duration_s"] = round(n / FPS, 3)
            t += n / FPS
    write_csv(csv_path, rows)
    shutil.rmtree(work, ignore_errors=True)
    log(f"Video: {out} ({codec}, {t:.1f} s, {'narrated' if narrated else 'silent'})")
    return {"video": str(out), "srt": str(srt_path), "csv": str(csv_path), "narrated": narrated,
            "note": note, "codec": codec, "duration_s": t, "rows": rows}
