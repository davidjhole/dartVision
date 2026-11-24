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
    assert sorted(os.listdir(d)) == ["cam1_after.png", "cam1_before.png", "meta.json"]
    with open(os.path.join(d, "meta.json")) as f:
        assert json.load(f)["true_label"] == "T19"
