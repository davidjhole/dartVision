"""Setting up the cameras from the phone / PC page: python -m pytest tests/test_camsetup.py"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

import numpy as np
import pytest
import yaml

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
from dartvision import camsetup, web  # noqa: E402
from dartvision.camsetup import CameraSetup, candidate_indexes  # noqa: E402

USB = "/dev/v4l/by-path/platform-xhci-hcd.0-usb-0:1.{}:1.0-video-index0"
DEVS = [{"index": 0, "id": USB.format(1), "name": "USB Camera A", "builtin": False},
        {"index": 2, "id": USB.format(2), "name": "USB Camera B", "builtin": False},
        {"index": 4, "id": "/dev/v4l/by-path/pci-0000:00:14.0-usb-0:5:1.0-video-index0", "name": "Integrated Camera",
         "builtin": True}]


def frame(v):
    return np.full((720, 1280, 3), v, np.uint8)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(camsetup.platform, "system", lambda: "Linux")
    pics = {0: frame(10), 2: frame(20), 4: frame(30)}
    s = CameraSetup(str(tmp_path / "config.yaml"), str(tmp_path / "calib"),
                    scanner=lambda i: pics.get(i), lister=lambda: DEVS)
    return s


def cams_in(path):
    with open(path) as f:
        return yaml.safe_load(f)["cameras"]


def test_only_usb_cameras_are_tried_on_linux(monkeypatch):
    monkeypatch.setattr(camsetup.platform, "system", lambda: "Linux")
    pi5 = [{"index": i, "id": f"/dev/v4l/by-path/platform-1f00128000.csi-video-index{i}", "name": "rp1-cfe",
            "builtin": False} for i in range(8)] + \
          [{"index": 8, "id": USB.format(1), "name": "USB Camera", "builtin": False}]
    assert candidate_indexes(10, pi5) == [8]
    assert candidate_indexes(4, []) == [0, 1, 2, 3]          # nothing known: try the numbers


def test_scan_finds_cameras_and_skips_the_builtin_one(setup):
    found = setup.scan()
    assert [c["index"] for c in found] == [0, 2, 4]
    assert [c["use"] for c in found] == [True, True, False]
    assert all(c["cam"] is None for c in found)
    assert setup.frame_jpeg(2)[:2] == b"\xff\xd8"
    assert setup.frame_jpeg("nope") is None
    assert "Found 3 cameras" in setup.state()["message"]


def test_save_names_the_cameras_and_keeps_names_after_a_rescan(setup):
    setup.scan()
    msg = setup.apply([{"index": 0, "use": True, "rotate": 0}, {"index": 2, "use": True, "rotate": 180},
                       {"index": 4, "use": False, "rotate": 0}])
    assert "cam1, cam2" in msg
    cams = cams_in(setup.config_path)
    assert [(c["name"], c["index"], c["rotate"], c["id"]) for c in cams] == \
        [("cam1", 0, 0, USB.format(1)), ("cam2", 2, 180, USB.format(2))]
    # the computer renumbers them: each camera is still recognised by its USB port
    DEVS2 = [dict(DEVS[1], index=0), dict(DEVS[0], index=2)]
    setup._list = lambda: DEVS2
    found = setup.scan()
    assert {c["index"]: (c["cam"], c["rotate"], c["use"]) for c in found} == \
        {0: ("cam2", 180, True), 2: ("cam1", 0, True)}
    setup.apply([{"index": c["index"], "use": True, "rotate": c["rotate"]} for c in found])
    assert {c["name"]: c["index"] for c in cams_in(setup.config_path)} == {"cam1": 2, "cam2": 0}


def test_new_camera_gets_a_free_name(setup):
    setup.scan()
    setup.apply([{"index": 2, "use": True, "rotate": 0}])
    setup.scan()
    setup.apply([{"index": 0, "use": True, "rotate": 0}, {"index": 2, "use": True, "rotate": 0}])
    assert {c["index"]: c["name"] for c in cams_in(setup.config_path)} == {0: "cam2", 2: "cam1"}


def test_turning_a_camera_sets_its_old_calibration_aside(setup):
    setup.scan()
    setup.apply([{"index": 0, "use": True, "rotate": 0}])
    os.makedirs(setup.calib_folder)
    p = os.path.join(setup.calib_folder, "cam1.json")
    open(p, "w").write("{}")
    setup.scan()
    msg = setup.apply([{"index": 0, "use": True, "rotate": 180}])
    assert "cam1 turned" in msg
    assert not os.path.exists(p) and os.path.exists(p + ".old")


def test_other_settings_are_kept(setup):
    with open(setup.config_path, "w") as f:
        yaml.safe_dump({"lights": {"type": "gpio", "pin": 18}}, f)
    setup.scan()
    setup.apply([{"index": 0, "use": True, "rotate": 0}])
    with open(setup.config_path) as f:
        assert yaml.safe_load(f)["lights"] == {"type": "gpio", "pin": 18}


@pytest.mark.parametrize("choices, why", [
    ([], "at least one"),
    ([{"index": 0, "use": False, "rotate": 0}], "at least one"),
    ([{"index": 9, "use": True, "rotate": 0}], "isn't there"),
    ([{"index": 0, "use": True, "rotate": 45}], "rotate"),
    ("nope", "bad request"),
    ([{"index": "x", "use": True}], "bad request"),
])
def test_bad_choices_are_refused(setup, choices, why):
    setup.scan()
    with pytest.raises(ValueError, match=why):
        setup.apply(choices)
    assert not os.path.exists(setup.config_path)


def test_page_has_camera_setup_screen():
    for bit in ('id="setup"', "setup_open", "setup_save", "setup_cancel", "setup_scan", "/setup/frame",
                "Set up cameras"):
        assert bit in web.PAGE


# ---------------------------------------------------------------- the real program, no cameras at all
def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def test_play_starts_with_no_cameras_and_opens_camera_setup(tmp_path):
    """A fresh Pi: no config.yaml cameras, nothing plugged in. play must still start and serve the
    page, and the setup screen must open, look for cameras and close again."""
    (tmp_path / "config.yaml").write_text("update: {check_on_start: false, auto: false}\nvoice: {enabled: false}\n"
                                          "cameras: []\n")
    port = _free_port()
    env = dict(os.environ, PYTHONPATH=os.path.abspath(ROOT), DISPLAY="", WAYLAND_DISPLAY="")
    p = subprocess.Popen([sys.executable, "-m", "dartvision", "play", "--headless", "--port", str(port), "--no-record"],
                         cwd=tmp_path, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    base = f"http://127.0.0.1:{port}"

    def state():
        with urllib.request.urlopen(base + "/state", timeout=3) as r:
            return json.load(r)

    def act(a):
        req = urllib.request.Request(base + "/action", data=json.dumps(a).encode(), method="POST")
        urllib.request.urlopen(req, timeout=3).read()

    def wait(cond, t=20):
        t0 = time.time()
        while time.time() - t0 < t:
            try:
                s = state()
                if cond(s):
                    return s
            except OSError:
                pass
            time.sleep(0.2)
        raise AssertionError(f"timed out; last state {s if 's' in dir() else None}")

    try:
        s = wait(lambda s: s.get("screen") == "menu")
        assert s["no_cameras"] and s["can_setup"] and not s["can_calibrate"]
        act({"type": "setup_open"})
        s = wait(lambda s: s.get("screen") == "setup" and not s["setup"]["scanning"])
        assert s["setup"]["cameras"] == [] or all("index" in c for c in s["setup"]["cameras"])
        act({"type": "setup_save", "cams": []})
        s = wait(lambda s: s["setup"]["message"].startswith("Not saved"))
        assert s["screen"] == "setup"
        act({"type": "setup_cancel"})
        s = wait(lambda s: s.get("screen") == "menu")
        assert s["setup_note"] == "Nothing changed"
        act({"type": "start"})                     # a game can still be played, scored by hand
        wait(lambda s: s.get("screen") == "play")
        assert p.poll() is None
    finally:
        p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
