"""Accuracy read-out in Settings (from the saved throws' labels):  python -m pytest tests/test_accuracy.py"""
import json
import os
import sys
import urllib.error
import urllib.request

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dartvision import web  # noqa: E402
from dartvision.recorder import Recorder, accuracy, picture, set_label, accept_if_unlabelled  # noqa: E402


def _session(tmp_path):
    rec = Recorder(str(tmp_path / "rec"), calib_folder=str(tmp_path / "nope"), background=False)
    img = np.full((72, 128, 3), 90, np.uint8)
    cams = {"cam1": {"ok": True, "tip_px": [40.0, 30.0]}, "cam2": {"ok": False, "reason": "no change"}}

    def throw(label, kind="DART"):
        return rec.save({"cam1": img, "cam2": img}, {"cam1": img, "cam2": img},
                        {"type": kind, "label": label, "cams": cams})
    a, b, c, d, e = throw("T20"), throw("S1"), throw("D5"), None, throw(None, "UNKNOWN")
    accept_if_unlabelled(a)                    # right
    set_label(b, "S20", "corrected")           # wrong
    set_label(c, "FALSE", "undone")            # false detection
    d = throw("T19"); set_label(d, "T19", "corrected")   # "corrected" to the same: it was right
    return rec, (a, b, c, d, e)


def test_counts_and_wrong_list(tmp_path):
    rec, (a, b, c, d, e) = _session(tmp_path)
    r = accuracy(str(tmp_path / "rec"), rec.dir)
    t = r["this"]
    assert (t["saved"], t["right"], t["corrected"], t["false"], t["unread"]) == (5, 2, 1, 1, 1)
    assert t["judged"] == 4 and t["pct"] == 50.0 and r["all"]["saved"] == 5
    kinds = [(w["source"], w["read"], w["true"]) for w in r["wrong"]]
    assert kinds == [("unread", "?", None), ("undone", "D5", "FALSE"), ("corrected", "S1", "S20")]
    assert r["wrong"][2]["cams"] == ["cam1", "cam2"] and r["wrong"][2]["tips"] == {"cam1": [40.0, 30.0]}


def test_picture_names_are_checked(tmp_path):
    rec, (a, b, *_) = _session(tmp_path)
    root = str(tmp_path / "rec")
    tid = f"{os.path.basename(rec.dir)}/{os.path.basename(b)}"
    data, ctype = picture(root, tid, "cam1", "before")
    assert ctype == "image/jpeg" and data[:2] == b"\xff\xd8"
    for bad in [("../x/throw_0001", "cam1"), (tid, "../../etc"), (tid + "/..", "cam1"), ("session_x/throw_0001", "cam1")]:
        assert picture(root, *bad) is None
    assert picture(root, tid, "cam1", "secret") is None


def test_web_routes(tmp_path):
    rec, (a, b, *_) = _session(tmp_path)
    web.set_recordings(str(tmp_path / "rec"), rec.dir, "all")
    assert web.start(port=0, host="127.0.0.1")
    base = f"http://127.0.0.1:{web.server.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/rec/accuracy", timeout=5) as r:
            j = json.loads(r.read())
        assert j["save"] == "all" and j["this"]["pct"] == 50.0
        tid = j["wrong"][-1]["id"]
        with urllib.request.urlopen(f"{base}/rec/pic?id={tid}&cam=cam1&which=after", timeout=5) as r:
            assert r.headers["Content-Type"] == "image/jpeg"
        try:
            urllib.request.urlopen(f"{base}/rec/pic?id=..%2F..&cam=cam1", timeout=5)
            assert False
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        web.stop()
        web.set_recordings(None)
