"""Cross-platform USB camera capture (Windows / Linux / macOS / Raspberry Pi)."""
import platform
import threading
import time

import cv2

SYSTEM = platform.system()


def default_backend():
    if SYSTEM == "Windows":
        return cv2.CAP_DSHOW          # opens fast and honours MJPG on Windows
    if SYSTEM == "Darwin":
        return cv2.CAP_AVFOUNDATION
    return cv2.CAP_V4L2               # Linux and Raspberry Pi


def list_cameras(max_index=10):
    """Try indexes 0..max_index and report which ones deliver frames."""
    found = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i, default_backend())
        if not cap.isOpened():
            cap.release()
            continue
        ok, frame = cap.read()
        if ok and frame is not None:
            found.append({"index": i, "width": frame.shape[1], "height": frame.shape[0]})
        cap.release()
    return found


def _rotate(frame, deg):
    if deg == 90:
        return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    if deg == 180:
        return cv2.rotate(frame, cv2.ROTATE_180)
    if deg == 270:
        return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return frame


class Camera:
    """Grabs frames on a background thread so every camera stays current."""

    def __init__(self, name, index, width=1280, height=720, fps=30, rotate=0, exposure=None):
        self.name, self.index, self.rotate = name, index, rotate
        self.cap = cv2.VideoCapture(index, default_backend())
        if not self.cap.isOpened():
            raise RuntimeError(f"camera {name} (index {index}) would not open")
        # MJPG keeps 3-4 cameras within USB 2.0 bandwidth. Set it before the size.
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, fps)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if exposure is not None:
            # Manual exposure: values differ by OS/driver (Linux V4L2: 1 = manual).
            self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1 if SYSTEM == "Linux" else 0.25)
            self.cap.set(cv2.CAP_PROP_EXPOSURE, exposure)
        self.frame, self.stamp, self.count = None, 0.0, 0
        self._lock = threading.Lock()
        self._run = True
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()
        t0 = time.time()
        while self.frame is None and time.time() - t0 < 5:
            time.sleep(0.02)
        if self.frame is None:
            raise RuntimeError(f"camera {name} opened but sent no frames")

    def _loop(self):
        while self._run:
            ok, f = self.cap.read()
            if not ok:
                time.sleep(0.01)
                continue
            f = _rotate(f, self.rotate)
            with self._lock:
                self.frame, self.stamp = f, time.time()
                self.count += 1

    def read(self):
        with self._lock:
            return None if self.frame is None else self.frame.copy()

    @property
    def size(self):
        f = self.frame
        return (f.shape[1], f.shape[0]) if f is not None else (0, 0)

    def close(self):
        self._run = False
        self._t.join(timeout=1)
        self.cap.release()


def open_cameras(cfg, only=None):
    cams = []
    for c in cfg["cameras"]:
        if only and c["name"] != only:
            continue
        cams.append(Camera(c["name"], c["index"], cfg["width"], cfg["height"], cfg["fps"],
                           c.get("rotate", 0), cfg.get("exposure")))
    if not cams:
        raise SystemExit("No cameras configured. Run:  python -m dartvision setup")
    return cams
