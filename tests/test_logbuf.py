"""Log shown on screen / phone:  python -m pytest tests/test_logbuf.py"""
import io
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dartvision import logbuf  # noqa: E402


@pytest.fixture(autouse=True)
def fresh():
    logbuf.clear()
    yield
    logbuf.clear()


@pytest.mark.parametrize("line,level", [
    ("Game on: 501 - Dave, J", "info"),
    ("[cam1] picture back", "info"),
    ("[cam1] no picture for 3 s - trying to reopen it", "warn"),
    ("Not updating: there are local code changes", "warn"),
    ("couldn't save the result: disk full", "error"),
    ("Traceback (most recent call last):", "error"),
    ("Update check failed: timeout", "error")])
def test_levels(line, level):
    assert logbuf.level_of(line) == level


def test_stderr_is_at_least_a_warning():
    assert logbuf.level_of("some library warning", "err") == "warn"
    assert logbuf.level_of("RuntimeError: boom", "err") == "error"


def test_tee_passes_through_and_records_whole_lines():
    real = io.StringIO()
    t = logbuf._Tee(real, "out")
    t.write("hello ")
    assert logbuf.lines() == []                       # not a whole line yet
    t.write("world\nsecond line\nthird")
    assert real.getvalue() == "hello world\nsecond line\nthird"
    assert [s for _, _, s in logbuf.lines()] == ["hello world", "second line"]
    t.write("\n")
    assert logbuf.lines()[-1][2] == "third"


def test_tee_survives_a_closed_terminal():
    real = io.StringIO()
    real.close()
    t = logbuf._Tee(real, "out")
    t.write("still recorded\n")
    t.flush()
    assert logbuf.lines()[-1][2] == "still recorded"


def test_keeps_only_the_last_lines():
    for i in range(logbuf.MAX + 50):
        logbuf.add(f"line {i}")
    ln = logbuf.lines()
    assert len(ln) == logbuf.MAX and ln[-1][2] == f"line {logbuf.MAX + 49}"
    assert len(logbuf.lines(10)) == 10


def test_blank_lines_are_ignored():
    logbuf.add("\n   \n")
    assert logbuf.lines() == []


def test_last_by_level():
    logbuf.add("couldn't do it")
    logbuf.add("all fine")
    assert logbuf.last()[2] == "all fine"
    assert logbuf.last("error")[2] == "couldn't do it"
    assert logbuf.last("warn")[2] == "couldn't do it"


def test_error_records_the_exception(capsys):
    try:
        raise ValueError("bad tap")
    except ValueError as e:
        logbuf.error("phone action set_dart failed", e)
    lv, s = logbuf.lines()[-1][1:]
    assert lv == "error" and "ValueError: bad tap" in s and "set_dart" in s


def test_errors_in_background_threads_are_recorded(monkeypatch):
    monkeypatch.setattr(sys, "stdout", sys.stdout)       # install() swaps these; undo afterwards
    monkeypatch.setattr(sys, "stderr", sys.stderr)
    monkeypatch.setattr(threading, "excepthook", lambda args: None)
    monkeypatch.setattr(logbuf, "_installed", False)
    logbuf.install()

    def boom():
        raise RuntimeError("camera thread died")
    th = threading.Thread(target=boom, name="watchdog")
    th.start()
    th.join()
    assert any("camera thread died" in s and lv == "error" for _, lv, s in logbuf.lines())


def test_for_web():
    logbuf.add("hello")
    (row,) = logbuf.for_web()
    assert isinstance(row[0], int) and row[1:] == ["info", "hello"]


# ------------------------------------------------------------------ drawing
cv2 = pytest.importorskip("cv2")


def test_info_bar_and_panel_draw():
    import numpy as np
    from dartvision import ui
    logbuf.add("couldn't read that one")
    bar = ui.draw_info_bar(1600, ui.info_bar_height(900), logbuf.last())
    assert bar.shape == (ui.info_bar_height(900), 1600, 3)
    assert bar.reshape(-1, 3).max(axis=0)[2] > 150                  # red text for an error
    assert ui.draw_info_bar(400, 22, None).shape == (22, 400, 3)    # nothing logged yet
    img = np.zeros((900, 1600, 3), np.uint8)
    for i in range(100):
        logbuf.add("x" * 300 + str(i))                              # long lines are cut, not crashing
    ui.draw_log_panel(img, logbuf.lines())
    assert img.any()
