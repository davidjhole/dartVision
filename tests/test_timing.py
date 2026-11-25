"""Timing log line and background picture saving:  python -m pytest tests/test_timing.py"""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dartvision.recorder import Recorder, set_label  # noqa: E402
from dartvision.timing import Pace  # noqa: E402


class FakeCam:
    def __init__(self, name):
        self.name, self.count, self.frame = name, 0, np.zeros((720, 1280, 3), np.uint8)
        self.stamp = time.time()


def test_timing_line():
    p = Pace()
    cams = [FakeCam("cam1"), FakeCam("cam2")]
    assert p.fresh(cams)
    assert not p.fresh(cams)                  # nothing new: the tracker isn't fed a repeat
    cams[1].count += 1
    assert not p.fresh(cams)                  # only one camera has a new picture: wait for both
    cams[0].count += 1
    assert p.fresh(cams)
    cams[0].count += 1
    cams[1].stamp -= 2                         # cam2 stopped sending: don't wait for it
    assert p.fresh(cams)
    unk = {"type": "UNKNOWN", "cams": {"cam1": {"ok": False, "reason": "blob too small (80px)"}, "cam2": {"ok": True}},
           "timing": {"moving": 0, "settle": 0.4, "detect": 0.1, "cams": {"cam1": 0.04, "cam2": 0.05}}}
    assert "(cam1 0.04 blob too small (80px), cam2 0.05)" in p.describe(unk, cams)
    ev = {"type": "DART", "label": "T20",
          "timing": {"moving": 0.3, "settle": 0.2, "detect": 0.1, "cams": {"cam1": 0.04, "cam2": 0.05}}}
    line = p.describe(ev, cams, 0.0)
    assert line.startswith("timing: dart T20 - moving 0.30 s, settle 0.20 s, find 0.10 s (cam1 0.04, cam2 0.05)")
    assert "= 0.60 s from landing to score" in line and "1280x720" in line


def test_recorder_writes_pictures_in_background(tmp_path):
    rec = Recorder(str(tmp_path), calib_folder=str(tmp_path / "nope"))
    img = np.full((72, 128, 3), 100, np.uint8)
    d = rec.save({"cam1": img}, {"cam1": img}, {"type": "DART", "label": "T20", "before_raw": {}})
    set_label(d, "T19", "corrected")          # meta is there straight away
    rec.flush()
    assert sorted(os.listdir(d)) == ["cam1_after.jpg", "cam1_before.jpg", "meta.json"]
    with open(os.path.join(d, "meta.json")) as f:
        assert json.load(f)["true_label"] == "T19"


def test_camera_skips_decoding_unneeded_pictures():
    """Waiting for a dart, only every n-th picture is decoded (the expensive part on a Pi)."""
    import threading
    from dartvision.cameras import Camera

    class FakeCap:
        def __init__(self):
            self.grabs = self.decodes = 0

        def grab(self):
            self.grabs += 1
            time.sleep(0.001)
            return True

        def retrieve(self):
            self.decodes += 1
            return True, np.zeros((4, 4, 3), np.uint8)

    cam = Camera.__new__(Camera)
    cam.name, cam.rotate, cam.frame, cam.stamp, cam.count, cam.grabbed = "cam1", 0, None, 0.0, 0, 0
    cam.decode_every, cam._lock, cam._run, cam._gen = 3, threading.Lock(), True, 1
    cap = FakeCap()
    t = threading.Thread(target=cam._loop, args=(1, cap), daemon=True)
    t.start()
    time.sleep(0.3)
    cam._run = False
    t.join(1)
    assert cap.grabs > 30 and cam.grabbed == cap.grabs
    assert cap.decodes == cam.count and abs(cap.decodes - cap.grabs / 3) <= 2


def test_recordings_stay_under_the_size_limit(tmp_path):
    from dartvision.recorder import iter_throws
    root = tmp_path / "rec"
    for i in range(3):                           # three old sessions, 1 MB each
        d = root / f"session_2026010{i}_120000" / "throw_0000"
        d.mkdir(parents=True)
        (d / "cam1_after.jpg").write_bytes(b"x" * 1_000_000)
    rec = Recorder(str(root), calib_folder=str(tmp_path / "nope"), max_mb=2.5, background=False)
    assert not (root / "session_20260100_120000" / "throw_0000").exists()     # oldest went
    assert (root / "session_20260102_120000" / "throw_0000").exists()
    assert os.path.isdir(rec.dir)
    img = np.random.default_rng(0).integers(0, 255, (72, 128, 3), np.uint8)
    d = rec.save({"cam1": img}, {"cam1": img}, {"type": "DART", "label": "T20"})
    rec.flush()
    (_, meta, before, after), = [t for t in iter_throws(rec.dir)]
    assert meta["label"] == "T20" and after["cam1"].shape == img.shape
    set_label(str(tmp_path / "gone" / "throw_0001"), "T19")     # tidied away: no error


def test_recorder_png_still_works(tmp_path):
    rec = Recorder(str(tmp_path), calib_folder=str(tmp_path / "nope"), fmt="png", background=False)
    img = np.full((8, 8, 3), 50, np.uint8)
    d = rec.save({"cam1": img}, {"cam1": img}, {"type": "DART"})
    assert "cam1_after.png" in os.listdir(d)


def test_corrected_darts_are_kept_longest(tmp_path):
    root = tmp_path / "rec"
    for i in range(3):
        d = root / f"session_2026010{i}_120000" / "throw_0000"
        d.mkdir(parents=True)
        (d / "cam1_after.jpg").write_bytes(b"x" * 1_000_000)
        src = "corrected" if i == 0 else "accepted"
        (d / "meta.json").write_text(json.dumps({"type": "DART", "label_source": src}))
    Recorder(str(root), calib_folder=str(tmp_path / "nope"), max_mb=1.5, background=False)
    assert (root / "session_20260100_120000" / "throw_0000").exists()       # the corrected one stays
    assert not (root / "session_20260101_120000" / "throw_0000").exists()
    assert not (root / "session_20260102_120000" / "throw_0000").exists()
