"""Calibrating from the phone / PC page: python -m pytest tests/test_web_calibrate.py
A fake camera shows a synthetic board; the test taps the 5 points like the page does."""
import json
import os
import sys
import urllib.error
import urllib.request

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from dartvision import board, web  # noqa: E402
from dartvision.calibrate import WebCalibrator  # noqa: E402
from dartvision.config import load_calibration  # noqa: E402
import synth  # noqa: E402


class FakeCam:
    def __init__(self, name, angle):
        self.name = name
        self.img, self.H = synth.render_view(angle)

    @property
    def size(self):
        return (self.img.shape[1], self.img.shape[0])

    def read(self):
        return self.img.copy()

    def true_points(self):
        return board.board_to_image([p for _, p in board.CALIB_POINTS], self.H).tolist()


@pytest.fixture
def cams():
    return [FakeCam("cam1", -90), FakeCam("cam2", 30)]


@pytest.fixture
def base(cams, tmp_path):
    web.take_actions()
    url = web.start(port=0, host="127.0.0.1")
    assert url
    web.set_calibrator(WebCalibrator(cams, folder=str(tmp_path)))
    yield f"http://127.0.0.1:{web.server.server_address[1]}"
    web.set_calibrator(None)
    web.stop()
    web.take_actions()


def get(base, path):
    try:
        with urllib.request.urlopen(base + path, timeout=5) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def post(base, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_lists_cameras_and_targets(base):
    _, _, b = get(base, "/calib/cams")
    d = json.loads(b)
    assert [c["name"] for c in d["cameras"]] == ["cam1", "cam2"]
    assert all(c["saved"] is None and c["size"] == [1280, 720] for c in d["cameras"])
    assert len(d["targets"]) == 5 and d["targets"][0]["mm"] == [0, 0]


def test_frame_is_a_jpeg(base):
    code, h, b = get(base, "/calib/frame?cam=cam1")
    assert code == 200 and h["Content-Type"] == "image/jpeg" and b[:2] == b"\xff\xd8"
    assert get(base, "/calib/frame?cam=nope")[0] == 503


def test_preview_then_save(base, cams, tmp_path):
    pts = cams[0].true_points()
    code, d = post(base, "/calib/preview", {"cam": "cam1", "points": pts})
    assert code == 200 and d["err"] < 0.5 and len(d["lines"]) == 26
    assert load_calibration("cam1", str(tmp_path)) is None          # preview doesn't save
    code, d = post(base, "/calib/save", {"cam": "cam1", "points": pts})
    assert code == 200 and d["ok"]
    cal = load_calibration("cam1", str(tmp_path))
    assert np.allclose(cal["image_points"], pts) and cal["image_size"] == [1280, 720]
    assert np.allclose(cal["H"] / cal["H"][2, 2], cams[0].H / cams[0].H[2, 2], rtol=1e-3, atol=1e-3)
    assert web.take_actions() == [{"type": "calibrated", "cam": "cam1"}]   # the game loop reloads it
    d = json.loads(get(base, "/calib/cams")[2])
    assert d["cameras"][0]["saved"] and d["cameras"][1]["saved"] is None


@pytest.mark.parametrize("body", [
    {"cam": "cam1", "points": [[1, 2]] * 4},
    {"cam": "cam1", "points": "nope"},
    {"cam": "cam1", "points": [[1, "x"]] * 5},
    {"cam": "nope", "points": [[1, 2]] * 5},
    ["not", "a", "dict"],
])
def test_bad_points_are_refused(base, body):
    code, d = post(base, "/calib/save", body)
    assert code == 400 and not d["ok"]
    assert web.take_actions() == []


def test_off_without_a_calibrator():
    url = web.start(port=0, host="127.0.0.1")
    try:
        b = f"http://127.0.0.1:{web.server.server_address[1]}"
        assert get(b, "/calib/cams")[0] == 404
        assert post(b, "/calib/save", {"cam": "cam1", "points": []})[0] == 404
    finally:
        web.stop()


def test_page_has_calibration_screen():
    assert "Calibrate cameras" in web.PAGE and "/calib/save" in web.PAGE
