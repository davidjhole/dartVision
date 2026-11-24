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
import collections
import time


class Pace:
    def __init__(self):
        self._seen = {}
        self._last = None
        self._loops = collections.deque(maxlen=120)
        self.loop_ms = 0.0          # typical (median) time between passes of the main loop
        self.dart_at = 0.0          # when the last scored dart started moving (for the caller line)
        self._fps = {}              # camera -> (time, frame count, frames per second)

    def loop_start(self):
        now = time.monotonic()
        if self._last is not None:
            self._loops.append((now - self._last) * 1000)
            self.loop_ms = sorted(self._loops)[len(self._loops) // 2]
        self._last = now

    def fresh(self, cams):
        """True once every camera has sent a new picture since the last True (a camera that has
        sent nothing for half a second is not waited for). The cameras aren't in step: counting
        a new picture from any one of them as a "frame" made the settle wait several times too
        short, so a dart could be looked at before every camera had a still picture of it."""
        wall = time.time()
        live = [c for c in cams if wall - getattr(c, "stamp", wall) < 0.5]
        new = bool(cams) and all(c.count != self._seen.get(c.name) for c in live)
        if new:
            self._seen = {c.name: c.count for c in cams}
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
        res = ev.get("cams") or {}

        def cam(n, s):
            why = "" if res.get(n, {}).get("ok", True) else f" {res[n].get('reason', '?')}"
            return f"{n} {s:.2f}{why}"
        per = ", ".join(cam(n, s) for n, s in (t.get("cams") or {}).items())
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
