"""Setting up the cameras from the phone / PC web page (what `python -m dartvision setup` does in a
terminal): find the cameras, show a picture from each, choose which to use and which way up they
are, and save that in config.yaml - so a Pi with no screen needs nothing but the web page.

`play` hands over its cameras while this page is open (a camera can only be opened by one
thing at a time), then opens the new set when you save.
"""
import os
import platform
import time

import cv2

from . import devices
from .cameras import default_backend
from .config import calib_path, load_config, save_config

ROTATIONS = (0, 90, 180, 270)


def candidate_indexes(max_index=10, devs=None):
    """Camera numbers worth trying. On Linux only the USB cameras: a Raspberry Pi 5 has its own
    camera-interface and video-codec devices at /dev/video0-7 and up, which are never ours."""
    devs = devices.list_devices() if devs is None else devs
    if platform.system() == "Linux" and devs:
        usb = sorted(d["index"] for d in devs if d.get("id") and "usb" in d["id"])
        if usb:
            return usb
    return list(range(max_index))


def snapshot(index, frames=12, timeout=4.0):
    """One picture from camera `index`, or None. Reads a few frames so auto exposure settles."""
    cap = cv2.VideoCapture(index, default_backend())
    try:
        if not cap.isOpened():
            return None
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        frame, n, t0 = None, 0, time.time()
        while n < frames and time.time() - t0 < timeout:
            ok, f = cap.read()
            if ok and f is not None:
                frame, n = f, n + 1
            elif frame is None and n == 0 and time.time() - t0 > 1.0:
                break                           # opens but never sends (e.g. a metadata node)
        return frame
    finally:
        cap.release()


class CameraSetup:
    """State of the camera setup page. scan() and apply() are called from the game loop;
    state() and frame_jpeg() may be called from the web server's threads."""

    def __init__(self, config_path="config.yaml", calib_folder="calib", max_index=10,
                 scanner=None, lister=None):
        self.config_path = config_path
        self.calib_folder = calib_folder
        self.max_index = max_index
        self._snap = scanner or snapshot
        self._list = lister or devices.list_devices
        self.found = []          # [{index, id, name, builtin, width, height, use, rotate, cam}]
        self.jpegs = {}          # index -> JPEG bytes (not rotated: the page turns it)
        self.active = False      # play has handed its cameras over to this page
        self.scanning = False
        self.scanned_at = 0.0
        self.message = ""

    # ---- looking for cameras
    def scan(self):
        cfg = load_config(self.config_path)
        current = cfg.get("cameras") or []
        devs = self._list()
        found, jpegs = [], {}
        for idx in candidate_indexes(self.max_index, devs):
            f = self._snap(idx)
            if f is None:
                continue
            d = devices.describe(idx, devs) or {}
            dev_id = d.get("id")
            mine = next((c for c in current if dev_id and c.get("id") == dev_id), None) \
                or next((c for c in current if not c.get("id") and c.get("index") == idx), None)
            builtin = bool(d.get("builtin"))
            found.append({"index": idx, "id": dev_id, "name": d.get("name") or f"camera {idx}",
                          "builtin": builtin, "width": int(f.shape[1]), "height": int(f.shape[0]),
                          "use": mine is not None or not builtin,
                          "rotate": int(mine.get("rotate", 0)) if mine else 0,
                          "cam": mine["name"] if mine else None})
            ok, buf = cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                jpegs[idx] = buf.tobytes()
        self.found, self.jpegs = found, jpegs
        self.scanning, self.scanned_at = False, time.time()
        n = len(found)
        self.message = (f"Found {n} camera{'s' if n != 1 else ''}" if n else
                        "No cameras found - check the USB cables, then tap Look again")
        print("camera setup: " + self.message.lower()
              + "".join(f"\n  index {c['index']}: {c['width']}x{c['height']}  {c['name']}" for c in found))
        return found

    def state(self):
        return {"scanning": self.scanning, "scanned_at": self.scanned_at, "message": self.message,
                "cameras": [{k: v for k, v in c.items()} for c in self.found]}

    def frame_jpeg(self, index):
        try:
            return self.jpegs.get(int(index))
        except (TypeError, ValueError):
            return None

    # ---- saving
    def apply(self, choices):
        """Save the cameras ticked on the page to config.yaml. `choices` is
        [{index, use, rotate}]. A camera keeps its name (and so its calibration) when it's the
        same physical camera as before; if its rotation changes, its old calibration no longer
        fits and is set aside as calib/<name>.json.old. Returns a short message."""
        if not isinstance(choices, list):
            raise ValueError("bad request")
        by_index = {c["index"]: c for c in self.found}
        picked = []
        for ch in choices:
            if not isinstance(ch, dict):
                raise ValueError("bad request")
            try:
                idx, rot = int(ch.get("index")), int(ch.get("rotate", 0))
            except (TypeError, ValueError):
                raise ValueError("bad request")
            if idx not in by_index:
                raise ValueError(f"camera {idx} isn't there any more - tap Look again")
            if rot not in ROTATIONS:
                raise ValueError("rotate must be 0, 90, 180 or 270")
            if ch.get("use"):
                picked.append((by_index[idx], rot))
        if not picked:
            raise ValueError("tick at least one camera")
        cfg = load_config(self.config_path)
        old = {c["name"]: c for c in cfg.get("cameras") or []}
        taken = {f["cam"] for f, _ in picked if f["cam"]}
        n, cams, notes = 1, [], []
        for f, rot in picked:
            name = f["cam"]
            if not name:
                while f"cam{n}" in taken:
                    n += 1
                name = f"cam{n}"
                taken.add(name)
            elif int(old.get(name, {}).get("rotate", 0)) != rot:
                p = calib_path(name, self.calib_folder)
                if os.path.exists(p):
                    os.replace(p, p + ".old")
                    notes.append(f"{name} turned - calibrate it again")
            cam = {"name": name, "index": f["index"], "rotate": rot}
            if f.get("id"):
                cam["id"] = f["id"]
                cam["model"] = f["name"]
            cams.append(cam)
        cfg["cameras"] = cams
        save_config(cfg, self.config_path)
        msg = f"Saved {len(cams)} camera{'s' if len(cams) != 1 else ''}: " + ", ".join(c["name"] for c in cams)
        if notes:
            msg += " (" + "; ".join(notes) + ")"
        print("camera setup: " + msg)
        return msg
