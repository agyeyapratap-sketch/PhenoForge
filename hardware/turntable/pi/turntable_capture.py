#!/usr/bin/env python3
"""PhenoForge turntable: step the platter and take a photo at every stop (Raspberry Pi 5).

Wiring (BCM numbers, TMC2209 or A4988/DRV8825 step-stick):
    GPIO18 -> STEP     GPIO23 -> DIR     GPIO24 -> EN (low = enabled)
    GPIO25 <- hall sensor OUT (optional home switch, active low, 3.3 V supply)
    Driver VM 12-24 V with a 100 uF capacitor, driver GND to Pi GND. MS1/MS2 set 1/16 microsteps.

Cameras:
    gphoto2   a DSLR / mirrorless camera on USB (sudo apt install gphoto2)
    opencv    one or more USB cameras, e.g. the two Arducam 16 MP (--cam 0 2)
    none      the table only stops and waits (--settle seconds): use a phone on an interval
              timer or a Bluetooth shutter, then copy the photos into the session folder

Examples:
    python3 turntable_capture.py --jog 90                       # test the drive
    python3 turntable_capture.py --out ~/scans/W123 --camera gphoto2 --shots 36 --rings low mid top
    python3 turntable_capture.py --out ~/scans/C07 --camera opencv --cam 0 2 --shots 24
    python3 turntable_capture.py --dry-run --camera none --shots 4   # no GPIO, no camera

Output: <out>/<ring>_<index>_<angle>.jpg (+ _camN for several cameras) and <out>/turntable.json,
which PhenoForge reads (Tools > Import from a capture device > Turntable rig).
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


class Stepper:
    """Trapezoidal-speed stepping on a step/dir driver through lgpio (works on the Pi 5)."""

    def __init__(self, step=18, dir=23, en=24, home=None, steps_per_rev=200, microsteps=16, ratio=6.0,
                 dry_run=False):
        self.pins = dict(step=step, dir=dir, en=en)
        self.home_pin = home
        self.usteps_per_deg = steps_per_rev * microsteps * ratio / 360.0
        self.dry = dry_run
        self.pos = 0  # microsteps from home / start
        if dry_run:
            return
        import lgpio

        self.lg = lgpio
        self.h = None
        for chip in (0, 4):  # Pi 5: gpiochip0 on new kernels, gpiochip4 on early ones
            try:
                h = lgpio.gpiochip_open(chip)
                lgpio.gpio_claim_output(h, step, 0)
                self.h = h
                break
            except Exception:
                continue
        if self.h is None:
            raise RuntimeError("cannot open the GPIO chip (is this a Raspberry Pi with lgpio installed?)")
        lgpio.gpio_claim_output(self.h, dir, 0)
        lgpio.gpio_claim_output(self.h, en, 1)
        if home is not None:
            lgpio.gpio_claim_input(self.h, home, lgpio.SET_PULL_UP)

    def enable(self, on=True):
        if not self.dry:
            self.lg.gpio_write(self.h, self.pins["en"], 0 if on else 1)

    def at_home(self) -> bool:
        return (not self.dry) and self.home_pin is not None and self.lg.gpio_read(self.h, self.home_pin) == 0

    def move_deg(self, deg, speed=30.0, accel=60.0, stop_at_home=False):
        """Rotate by ``deg`` (sign = direction) with speed in deg/s and acceleration in deg/s^2."""
        n = int(round(abs(deg) * self.usteps_per_deg))
        if n == 0:
            return 0
        if self.dry:
            time.sleep(min(abs(deg) / speed, 0.05))
            self.pos += n if deg > 0 else -n
            return n
        self.lg.gpio_write(self.h, self.pins["dir"], 1 if deg > 0 else 0)
        time.sleep(0.001)
        vmax = speed * self.usteps_per_deg  # usteps/s
        a = accel * self.usteps_per_deg
        v0 = min(vmax, 200.0)
        ramp = int(min(n // 2, (vmax ** 2 - v0 ** 2) / (2 * a))) if vmax > v0 else 0
        t = time.perf_counter()
        step = self.pins["step"]
        done = 0
        for i in range(n):
            k = min(i, n - 1 - i)
            v = math.sqrt(v0 ** 2 + 2 * a * k) if k < ramp else vmax
            dt = 1.0 / v
            self.lg.gpio_write(self.h, step, 1)
            t += dt / 2
            while time.perf_counter() < t:
                pass
            self.lg.gpio_write(self.h, step, 0)
            t += dt / 2
            while time.perf_counter() < t:
                pass
            done += 1
            if stop_at_home and self.at_home():
                break
        self.pos += done if deg > 0 else -done
        return done

    def home(self, speed=15.0):
        """Turn until the magnet passes the hall sensor (at most 1.1 turns)."""
        if self.dry or self.home_pin is None:
            self.pos = 0
            return False
        if self.at_home():
            self.move_deg(20, speed)
        self.move_deg(396, speed, stop_at_home=True)
        ok = self.at_home()
        self.pos = 0
        return ok

    @property
    def angle(self) -> float:
        return (self.pos / self.usteps_per_deg) % 360.0

    def close(self):
        if not self.dry:
            self.enable(False)
            self.lg.gpiochip_close(self.h)


class Cameras:
    def __init__(self, kind, cams=(0,), width=0, height=0, warmup=5):
        self.kind = kind
        self.caps = []
        self.warmup = warmup
        if kind == "gphoto2":
            if not shutil.which("gphoto2"):
                raise RuntimeError("gphoto2 not found: sudo apt install gphoto2")
            subprocess.run(["gphoto2", "--auto-detect"], check=True)
        elif kind == "opencv":
            import cv2

            for c in cams:
                cap = cv2.VideoCapture(int(c), cv2.CAP_V4L2)
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
                if width and height:
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                if not cap.isOpened():
                    raise RuntimeError(f"cannot open camera {c}")
                self.caps.append((c, cap))

    def shoot(self, stem: Path) -> list[str]:
        """Take one photo per camera, return the file names written."""
        if self.kind == "none":
            return []
        if self.kind == "gphoto2":
            p = stem.with_suffix(".%C")
            subprocess.run(["gphoto2", "--capture-image-and-download", "--force-overwrite", "--filename", str(p)],
                           check=True, stdout=subprocess.DEVNULL)
            return sorted(f.name for f in stem.parent.glob(stem.name + ".*"))
        import cv2

        out = []
        for c, cap in self.caps:
            for _ in range(self.warmup):  # drop buffered frames taken while the table moved
                cap.grab()
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError(f"camera {c} returned no frame")
            name = f"{stem.name}_cam{c}.jpg" if len(self.caps) > 1 else f"{stem.name}.jpg"
            cv2.imwrite(str(stem.parent / name), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            out.append(name)
        return out

    def close(self):
        for _, cap in self.caps:
            cap.release()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="turntable_session")
    ap.add_argument("--shots", type=int, default=36, help="stops per revolution (36 = every 10 degrees)")
    ap.add_argument("--rings", nargs="+", default=["ring1"], help="camera heights, one revolution each, e.g. low mid top")
    ap.add_argument("--camera", choices=["gphoto2", "opencv", "none"], default="gphoto2")
    ap.add_argument("--cam", nargs="+", default=["0"], help="OpenCV camera indices")
    ap.add_argument("--size", nargs=2, type=int, default=[0, 0], metavar=("W", "H"), help="OpenCV capture size")
    ap.add_argument("--settle", type=float, default=1.5, help="seconds to wait after each move (plant stops swinging)")
    ap.add_argument("--speed", type=float, default=20.0, help="deg/s; lower for tall or heavy samples")
    ap.add_argument("--accel", type=float, default=20.0, help="deg/s^2; lower if leaves or roots swing")
    ap.add_argument("--ratio", type=float, default=6.0, help="belt reduction (120T / 20T = 6)")
    ap.add_argument("--microsteps", type=int, default=16)
    ap.add_argument("--pins", nargs=3, type=int, default=[18, 23, 24], metavar=("STEP", "DIR", "EN"))
    ap.add_argument("--home-pin", type=int, default=None, help="hall sensor GPIO (e.g. 25) to start each ring at 0 deg")
    ap.add_argument("--reverse", action="store_true", help="turn the other way")
    ap.add_argument("--jog", type=float, default=None, help="only rotate by this many degrees and exit")
    ap.add_argument("--dry-run", action="store_true", help="no GPIO (test on any computer)")
    ap.add_argument("--yes", action="store_true", help="do not wait for Enter between rings")
    a = ap.parse_args(argv)

    st = Stepper(*a.pins, home=a.home_pin, microsteps=a.microsteps, ratio=a.ratio, dry_run=a.dry_run)
    sign = -1 if a.reverse else 1
    st.enable(True)
    try:
        if a.jog is not None:
            st.move_deg(sign * a.jog, a.speed, a.accel)
            print(f"moved {a.jog} deg")
            return 0
        out = Path(a.out).expanduser()
        out.mkdir(parents=True, exist_ok=True)
        cams = Cameras(a.camera, a.cam, *a.size)
        step_deg = 360.0 / a.shots
        meta = {"rig": "phenoforge-turntable", "version": 1, "created": datetime.now().isoformat(timespec="seconds"),
                "shots_per_ring": a.shots, "step_deg": step_deg, "direction": "cw" if a.reverse else "ccw",
                "camera": a.camera, "cameras": a.cam if a.camera == "opencv" else [a.camera],
                "ratio": a.ratio, "microsteps": a.microsteps, "settle_s": a.settle, "rings": []}
        for r, ring in enumerate(a.rings):
            if r > 0 and not a.yes:
                input(f"Move the camera to ring '{ring}' and press Enter... ")
            homed = st.home() if a.home_pin is not None else False
            start = st.pos
            shots = []
            for i in range(a.shots):
                time.sleep(a.settle)
                angle = ((st.pos - start) / st.usteps_per_deg) % 360.0
                stem = out / f"{ring}_{i:03d}_{angle:05.1f}"
                files = cams.shoot(stem)
                shots.append({"index": i, "angle_deg": round(angle, 3), "files": files,
                              "time": datetime.now().isoformat(timespec="milliseconds")})
                print(f"{ring} {i + 1}/{a.shots}  {angle:6.1f} deg  {' '.join(files) or '(external camera)'}", flush=True)
                # step to the next stop; the target is computed from the start so errors do not add up
                target = start + round((i + 1) * step_deg * st.usteps_per_deg) * sign
                st.move_deg((target - st.pos) / st.usteps_per_deg, a.speed, a.accel)
            meta["rings"].append({"name": ring, "homed": homed, "shots": shots})
            (out / "turntable.json").write_text(json.dumps(meta, indent=1))
        cams.close()
        print(f"done: {sum(len(r['shots']) for r in meta['rings'])} stops in {out}")
    finally:
        st.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
