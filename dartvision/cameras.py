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
    """Grabs frames on a background thread so every camera stays current.

    If a camera stops sending pictures (a USB hub that browns out or resets does this without
    any error), read() notices and reopens it, so the picture doesn't freeze for good.
    """
    STALL_S = 3.0          # no new frame for this long -> reopen the camera

    def __init__(self, name, index, width=1280, height=720, fps=30, rotate=0, exposure=None):
        self.name, self.index, self.rotate = name, index, rotate
        self._settings = (width, height, fps, exposure)
        self.frame, self.stamp, self.count = None, 0.0, 0
        self.reconnects = 0
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
        while self._run and gen == self._gen:
            ok, f = cap.read()
            if not ok:
                time.sleep(0.01)
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


def open_cameras(cfg, only=None):
    cams = []
    for c in cfg["cameras"]:
        if only and c["name"] != only:
            continue
        cams.append(Camera(c["name"], c["index"], cfg["width"], cfg["height"], cfg["fps"],
                           c.get("rotate", 0), cfg.get("exposure")))
    if not cams:
        raise SystemExit("No cameras configured. Run:  python -m dartvision setup")
    for c in cams:
        c.peers = cams
    return cams
