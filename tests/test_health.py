"""Computer health in the log and the shareable report:  python -m pytest tests/test_health.py"""
import json
import os
import sys
import urllib.request

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dartvision import health, logbuf, web  # noqa: E402


@pytest.fixture(autouse=True)
def fresh():
    logbuf.clear()
    yield
    logbuf.clear()


def test_decode_throttled():
    assert health.decode_throttled(0) == ([], [])
    assert health.decode_throttled(0x80000) == ([], ["hit the soft temperature limit"])
    now, since = health.decode_throttled(0x50005)
    assert now == ["under-voltage (power supply too weak)", "throttled (CPU slowed down)"]
    assert since == ["under-voltage", "throttled"]
    assert health.decode_throttled(None) == ([], [])


def test_describe_throttled():
    assert health.describe_throttled(0x80000) == "Pi: OK now; since boot: hit the soft temperature limit (0x80000)"
    assert health.describe_throttled(0x1).startswith("Pi: NOW under-voltage")
    assert health.describe_throttled(None) == ""


def test_temp_bands_have_some_slack():
    assert health.temp_band(45) == "cool"
    assert health.temp_band(78.5) == "hot"
    assert health.temp_band(80.2) == "very hot"
    assert health.temp_band(80.5, "hot") == "hot"          # just over the edge: no change yet
    assert health.temp_band(82.5, "hot") == "very hot"
    assert health.temp_band(79, "very hot") == "very hot"  # just under: stays until 2 °C below
    assert health.temp_band(77.5, "very hot") == "hot"


class FakeMonitor(health.Monitor):
    def __init__(self, samples):
        self.out = []
        super().__init__(emit=lambda text, level: self.out.append((level, text)))
        self.samples = list(samples)

    def sample(self):
        base = {"t": 0.0, "temp": 50.0, "throttled": 0, "fan": None, "freq": 1.5, "freq_max": 2.4, "load": 0.5,
                "cores": 4, "cpu": 20, "own_cpu": 15, "mem_used": 400.0, "mem_total": 3800.0, "own_mem": 120.0,
                "disk_free": 20.0}
        base.update(self.samples.pop(0))
        return base


def test_logs_at_start_on_changes_and_every_few_minutes():
    m = FakeMonitor([{"t": 1000}, {"t": 1005}, {"t": 1010, "temp": 75},
                     {"t": 1015, "temp": 75, "throttled": 0x80008},
                     {"t": 1020, "temp": 75, "throttled": 0x80000}, {"t": 1025, "temp": 75, "throttled": 0x80000},
                     {"t": 1700, "temp": 75, "throttled": 0x80000}])
    for _ in range(7):
        m.tick()
    texts = [t for _, t in m.out]
    assert len(texts) == 5
    assert "[started]" in texts[0] and texts[0].startswith("health: 50.0°C cool")
    assert "temperature now hot" in texts[1]
    assert "new: soft temperature limit" in texts[2] and "since boot: hit the soft temperature limit" in texts[2]
    assert m.out[2][0] == "warn"                       # slowed down right now
    assert "stopped: soft temperature limit" in texts[3]
    assert texts[4].endswith("(0x80000)")              # the every-10-minutes line, no reason
    assert m.temp_max == 75


def test_low_disk_and_memory():
    m = FakeMonitor([{"t": 1}, {"t": 2, "disk_free": 0.5, "mem_used": 3600.0}])
    m.tick()
    m.tick()
    assert "memory nearly full" in m.out[-1][1] and "disk nearly full" in m.out[-1][1]
    assert m.out[-1][0] == "warn"


def test_web_summary():
    m = FakeMonitor([{"t": 1, "temp": 78.6, "throttled": 0x80000}])
    m.tick()
    w = m.for_web()
    assert w["temp"] == 78.6 and w["band"] == "hot" and w["throttled"] == "0x80000"
    assert w["now"] == [] and w["since"] == ["hit the soft temperature limit"]
    json.dumps(w)


def test_real_sample_doesnt_crash():
    m = health.Monitor()
    s = m.sample()
    assert "temp" in s and m.line(s).startswith("health:")


def test_report_has_everything():
    logbuf.add("timing: dart T20 - moving 0.30 s, settle 0.20 s, find 0.10 s, save 0.00 s = 0.60 s from landing to score")
    logbuf.add("timing: dart S5 - moving 0.30 s, settle 0.20 s, find 0.50 s, save 0.00 s = 1.00 s from landing to score")
    logbuf.add("couldn't read that one")
    m = FakeMonitor([{"t": 1, "temp": 78.6, "throttled": 0x80000}])
    m.tick()
    cfg = {"cameras": [{"name": "cam1", "index": 0}, {"name": "cam2", "index": 2, "rotate": 180}],
           "width": 1280, "height": 720, "fps": 30, "detection": {"settle_frames": 6},
           "voice": {"enabled": True}, "lights": {"type": "http", "on_url": "http://secret"}}
    r = health.report("v0.1.1 (abc1234)", cfg, calibrated=["cam1"], monitor=m, extra={"speed now": "x"})
    assert "version: v0.1.1 (abc1234)" in r
    assert "throttled=0x80000" in r and "hit the soft temperature limit" in r
    assert "2 darts: landing to score median 1.00 s, fastest 0.60 s, slowest 1.00 s" in r
    assert "cam1 (index 0, rotate 0, calibrated)" in r and "cam2 (index 2, rotate 180, NOT calibrated)" in r
    assert "secret" not in r                            # no light URLs
    assert "E couldn't read that one" in r
    short = health.report(max_lines=1)
    assert "== Log (1 lines" in short


@pytest.fixture
def base():
    url = web.start(port=0, host="127.0.0.1")
    assert url
    yield f"http://127.0.0.1:{web.server.server_address[1]}"
    web.stop()
    web.set_report(None)


def test_log_and_report_from_the_page(base):
    for i in range(5):
        logbuf.add(f"line {i}")
    with urllib.request.urlopen(base + "/log.json?n=3") as r:
        rows = json.loads(r.read())
    assert [x[2] for x in rows] == ["line 2", "line 3", "line 4"]
    web.set_report(lambda n: f"report with {n} lines")
    with urllib.request.urlopen(base + "/report.txt?lines=400") as r:
        assert r.read() == b"report with 400 lines"
    with urllib.request.urlopen(base + "/report.txt?download=1") as r:
        assert "attachment" in r.headers["Content-Disposition"] and r.read() == b"report with None lines"
