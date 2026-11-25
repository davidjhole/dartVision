"""Cross-platform USB camera capture (Windows / Linux / macOS / Raspberry Pi)."""
import platform
import threading
import time

import cv2

from . import devices

SYSTEM = platform.system()


def default_backend():
    if SYSTEM == "Windows":
        return cv2.CAP_DSHOW          # opens fast and honours MJPG on Windows
    if SYSTEM == "Darwin":
        return cv2.CAP_AVFOUNDATION
    return cv2.CAP_V4L2               # Linux and Raspberry Pi


def list_cameras(max_index=10, indexes=None):
    """Try indexes 0..max_index (or the given ones) and report which ones deliver frames."""
    found = []
    for i in (range(max_index) if indexes is None else indexes):
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
    """Grabs frames on a background thread so every camera stays current.

    If a camera stops sending pictures (a USB hub that browns out or resets does this without
    any error), read() notices and reopens it, so the picture doesn't freeze for good.
    """
    STALL_S = 3.0          # no new frame for this long -> reopen the camera

    def __init__(self, name, index, width=1280, height=720, fps=30, rotate=0, exposure=None, dev_id=None):
        self.name, self.index, self.rotate, self.dev_id = name, index, rotate, dev_id
        self._settings = (width, height, fps, exposure)
        self.frame, self.stamp, self.count = None, 0.0, 0
        self.reconnects = 0
        self.grabbed = 0            # pictures taken off the camera (decoded or not)
        self.decode_every = 1       # >1: take every picture from the camera but only decode every n-th
        self._lock = threading.Lock()
        self._run = True
        self._gen = 0
        self._next_try = 0.0
        self._dup_warned = self._stall_warned = False
        self.peers = []                         # the other cameras (set by open_cameras)
        self.cap = self._open()
        if self.cap is None:
            raise RuntimeError(f"camera {name} (index {index}) would not open")
        self._start_reader()
        t0 = time.time()
        while self.frame is None and time.time() - t0 < 5:
            time.sleep(0.02)
        if self.frame is None:
            raise RuntimeError(f"camera {name} opened but sent no frames")

    def _open(self):
        width, height, fps, exposure = self._settings
        cap = cv2.VideoCapture(self.index, default_backend())
        if not cap.isOpened():
            cap.release()
            return None
        # MJPG keeps 3-4 cameras within USB 2.0 bandwidth. Set it before the size.
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if exposure is not None:
            # Manual exposure: values differ by OS/driver (Linux V4L2: 1 = manual).
            cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1 if SYSTEM == "Linux" else 0.25)
            cap.set(cv2.CAP_PROP_EXPOSURE, exposure)
        return cap

    def _start_reader(self):
        self._gen += 1
        self._t = threading.Thread(target=self._loop, args=(self._gen, self.cap), daemon=True)
        self._t.start()

    def _loop(self, gen, cap):
        n = 0
        while self._run and gen == self._gen:
            # grab() takes the picture off the camera (cheap); retrieve() decodes the JPEG (the
            # expensive part). Pictures not needed are grabbed and dropped without decoding.
            if not cap.grab():
                time.sleep(0.01)
                continue
            n += 1
            self.grabbed += 1
            every = max(1, int(self.decode_every))
            if every > 1 and n % every and self.frame is not None:
                with self._lock:
                    self.stamp = time.time()        # still alive, just not decoded
                continue
            ok, f = cap.retrieve()
            if not ok or f is None:
                continue
            if gen != self._gen:
                break
            f = _rotate(f, self.rotate)
            with self._lock:
                self.frame, self.stamp = f, time.time()
                self.count += 1

    def service(self):
        """Reopen the camera if it has stopped sending pictures. Runs on the caller's (main)
        thread: macOS crashes if a camera is released or opened from a background thread
        while another thread is still reading from it."""
        now = time.time()
        if now - self.stamp < self.STALL_S or now < self._next_try:
            return
        self._next_try = now + self.STALL_S
        if not self._stall_warned:
            print(f"[{self.name}] no picture for {self.STALL_S:.0f} s - trying to reopen it (every {self.STALL_S:.0f} s)")
            self._stall_warned = True
        self._gen += 1                          # ask the old reader thread to stop
        self._t.join(timeout=1.0)
        if self._t.is_alive():                  # stuck inside the driver: leave it, try again later
            return
        try:
            self.cap.release()
        except Exception:
            pass
        if self.dev_id:                         # find our camera by its port, not its old number
            idx = devices.index_for_id(self.dev_id)
            if idx is None:                     # still switched off / unplugged
                return
            self.index = idx
        cap = self._open()
        if cap is None:                         # unplugged / switched off: keep trying
            return
        if self._is_duplicate(cap):
            # macOS renumbers cameras when one disappears: this index now belongs to another
            # camera that is already open. Don't show it twice; keep trying.
            if not self._dup_warned:
                print(f"[{self.name}] index {self.index} is now another camera (the computer renumbered "
                      "them). Once it's back on, restart dartvision if it doesn't return by itself.")
                self._dup_warned = True
            cap.release()
            return
        self._dup_warned = self._stall_warned = False
        print(f"[{self.name}] picture back")
        self.cap = cap
        self.reconnects += 1
        self.stamp = time.time()
        self._start_reader()

    def _is_duplicate(self, cap):
        """True if the newly opened camera shows the same picture as another open camera."""
        frame = None
        t0 = time.time()
        while frame is None and time.time() - t0 < 1.5:
            ok, f = cap.read()
            if ok and f is not None:
                frame = _rotate(f, self.rotate)
        if frame is None:
            return False
        def small(img):
            return cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (64, 36), interpolation=cv2.INTER_AREA)
        me = small(frame).astype("int16")
        for p in self.peers:
            if p is self or p.frame is None:
                continue
            other = p.frame
            if other.shape != frame.shape:
                continue
            if abs(me - small(other).astype("int16")).mean() < 4:   # same view, just sensor noise
                return True
        return False

    @property
    def stalled(self):
        return time.time() - self.stamp > 1.5

    def read(self):
        self.service()
        with self._lock:
            return None if self.frame is None else self.frame.copy()

    @property
    def size(self):
        f = self.frame
        return (f.shape[1], f.shape[0]) if f is not None else (0, 0)

    def close(self):
        self._run = False
        self._gen += 1
        self._t.join(timeout=1)
        try:
            self.cap.release()
        except Exception:
            pass


def open_cameras(cfg, only=None, config_path=None, allow_none=False):
    """Open the configured cameras. Cameras saved with a port id (setup on macOS / Linux) are
    found by that id, so it doesn't matter if the computer has renumbered them. A camera that
    won't open is skipped; with none at all it stops, unless allow_none (then it returns [])."""
    devs = devices.list_devices()
    cams, moved = [], False
    for c in cfg["cameras"]:
        if only and c["name"] != only:
            continue
        index = c["index"]
        if c.get("id"):
            now = devices.index_for_id(c["id"], devs)
            if now is None:
                print(f"[{c['name']}] not found - is it plugged in and switched on? Skipping it.")
                continue
            if now != index:
                print(f"[{c['name']}] is index {now} now (was {index}) - the computer renumbered the cameras.")
                c["index"] = index = now
                moved = True
        else:
            d = devices.describe(index, devs)
            if d and d["builtin"]:
                print(f"[{c['name']}] index {index} is '{d['name']}', the computer's own camera. "
                      "Run  python -m dartvision setup  again.")
        try:
            cams.append(Camera(c["name"], index, cfg["width"], cfg["height"], cfg["fps"],
                               c.get("rotate", 0), cfg.get("exposure"), c.get("id")))
        except RuntimeError as e:
            print(f"[{c['name']}] {e} - skipping it.")
    if not cams:
        if allow_none:       # play with the web page: cameras can be set up from there
            print("No cameras opened - set them up from the phone page (Set up cameras), "
                  "or run  python -m dartvision setup")
            return []
        raise SystemExit("No cameras opened. Run:  python -m dartvision setup")
    if moved and config_path:
        from .config import save_config
        save_config(cfg, config_path)
    now = time.time()
    for c in cams:
        c.peers = cams
        # opening the others can pause a camera for a few seconds (macOS): start the stall clock now
        c.stamp = max(c.stamp, now)
    return cams
