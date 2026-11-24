"""Where the time goes between a dart landing and its score: one "timing:" line in the log for
each dart (and pull-out), so a slow computer (a Raspberry Pi) shows which part is slow.

    timing: dart T20 - moving 0.35 s, settle 0.20 s, find 0.12 s (cam1 0.03, cam2 0.03, ...),
            save 0.00 s = 0.67 s from landing to score | loop 21 ms, cameras 30/30/29/30 fps, 1280x720

moving  first movement until the last (the dart flying in and wobbling, or a hand)
settle  the quiet wait after it (detection.settle_frames frames)
find    finding the dart in every camera and working out the score (per camera in brackets)
save    storing the throw's pictures (in the background, so this should be ~0)
loop    how long one pass of the main loop takes; much over 1000/fps ms means frames are missed
"""
import time


class Pace:
    def __init__(self):
        self._seen = None
        self._last = None
        self.loop_ms = 0.0          # smoothed time between passes of the main loop
        self.dart_at = 0.0          # when the last scored dart started moving (for the caller line)
        self._fps = {}              # camera -> (time, frame count, frames per second)

    def loop_start(self):
        now = time.monotonic()
        if self._last is not None:
            dt = (now - self._last) * 1000
            self.loop_ms = dt if not self.loop_ms else 0.9 * self.loop_ms + 0.1 * dt
        self._last = now

    def fresh(self, cams):
        """True if any camera has sent a new picture since the last call."""
        seen = tuple((c.name, c.count) for c in cams)
        new = seen != self._seen
        self._seen = seen
        now = time.monotonic()
        for c in cams:
            t, n, fps = self._fps.get(c.name, (now, c.count, 0.0))
            if now - t >= 2.0:
                self._fps[c.name] = (now, c.count, (c.count - n) / (now - t))
            elif c.name not in self._fps:
                self._fps[c.name] = (t, n, fps)
        return new

    def describe(self, ev, cams, save_s=0.0):
        t = ev.get("timing") or {}
        kind = ev["type"].lower()
        what = f"dart {ev['label']}" if ev["type"] == "DART" else kind
        per = ", ".join(f"{n} {s:.2f}" for n, s in (t.get("cams") or {}).items())
        total = t.get("moving", 0) + t.get("settle", 0) + t.get("detect", 0) + save_s
        fps = "/".join(f"{self._fps.get(c.name, (0, 0, 0))[2]:.0f}" for c in cams)
        size = ""
        if cams and getattr(cams[0], "frame", None) is not None:
            h, w = cams[0].frame.shape[:2]
            size = f", {w}x{h}"
        return (f"timing: {what} - moving {t.get('moving', 0):.2f} s, settle {t.get('settle', 0):.2f} s, "
                f"find {t.get('detect', 0):.2f} s" + (f" ({per})" if per else "") +
                f", save {save_s:.2f} s = {total:.2f} s from landing to score"
                f" | loop {self.loop_ms:.0f} ms, cameras {fps} fps{size}")
