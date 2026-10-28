"""End-to-end check on synthetic images:  python tests/test_pipeline.py"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from dartvision import board                                # noqa: E402
from dartvision.calibrate import compute_homography         # noqa: E402
from dartvision.config import DEFAULT                       # noqa: E402
from dartvision.detect import ThrowTracker, find_dart_tip, fuse_darts, prep  # noqa: E402
from synth import render_view, clicked_points               # noqa: E402

CAMS = {"cam1": 45, "cam2": 135, "cam3": 225, "cam4": 315}


def test_scoring():
    assert board.score_at(0, 0) == ("DB", 50)
    assert board.score_at(0, 10) == ("SB", 25)
    assert board.score_at(0, 103) == ("T20", 60)
    assert board.score_at(0, -166) == ("D3", 6)
    assert board.score_at(103, 0) == ("T6", 18)
    assert board.score_at(-150, 0) == ("S11", 11)
    assert board.score_at(0, 200) == ("MISS", 0)
    a = math.radians(80.5)  # just clockwise of the 20/1 wire -> 1
    assert board.score_at(140 * math.cos(a), 140 * math.sin(a)) == ("S1", 1)
    assert board.parse_score("t20") == ("T20", 60) and board.parse_score("25") == ("SB", 25)
    print("scoring: ok")


def calibrate_all():
    cals = {}
    for n, a in CAMS.items():
        _, Hc = render_view(a)
        pts = clicked_points(Hc, seed=hash(n) % 100)
        H, err = compute_homography(pts, [p for _, p in board.CALIB_POINTS])
        cals[n] = {"H": H, "H_inv": np.linalg.inv(H), "fit": err}
    return cals


def test_detection(n_darts=150, seed=3):
    rng = np.random.default_rng(seed)
    cals = calibrate_all()
    det = DEFAULT["detection"]
    shapes = {n: (720, 1280, 3) for n in CAMS}
    tr = ThrowTracker(cals, det, shapes)
    errs, right, per_cam_err = [], 0, {n: [] for n in CAMS}
    wrong = []
    for k in range(n_darts):
        r = 170 * math.sqrt(rng.uniform(0, 1))
        a = rng.uniform(0, 2 * math.pi)
        p = (r * math.cos(a), r * math.sin(a))
        pts = []
        for n, ang in CAMS.items():
            b, _ = render_view(ang, [], seed=k)
            af, _ = render_view(ang, [p], seed=k + 1000)
            res = find_dart_tip(prep(b), prep(af), cals[n]["H_inv"], tr.roi[n], det)
            pts.append(res)
            if res["ok"]:
                per_cam_err[n].append(np.hypot(res["tip_mm"][0] - p[0], res["tip_mm"][1] - p[1]))
        f = fuse_darts(pts, det["fuse_tolerance_mm"])
        if f is None:
            wrong.append((p, "none")); continue
        e = math.hypot(f[0] - p[0], f[1] - p[1]); errs.append(e)
        ok = board.score_at(*f[:2])[0] == board.score_at(*p)[0]
        right += ok
        if not ok:
            wrong.append((tuple(round(v, 1) for v in p), board.score_at(*p)[0], board.score_at(*f[:2])[0], round(e, 1)))
    print(f"detection: {right}/{n_darts} scored correctly ({100 * right / n_darts:.1f}%)")
    print(f"  fused position error: median {np.median(errs):.1f} mm, 90% {np.percentile(errs, 90):.1f} mm, max {max(errs):.1f} mm")
    for n, e in per_cam_err.items():
        print(f"  {n}: median {np.median(e):.1f} mm, 90% {np.percentile(e, 90):.1f} mm ({len(e)} found)")
    for w in wrong[:8]:
        print("  miss:", w)
    return right / n_darts


def test_tracker():
    """State machine: dart lands -> DART, second dart -> DART, pull darts -> TAKEOUT."""
    cals = calibrate_all()
    det = DEFAULT["detection"]
    tr = ThrowTracker(cals, det, {n: (720, 1280, 3) for n in CAMS})
    darts = [(0, 103), (20, -60)]

    def frames(ds, hand=False, seed=0):
        out = {}
        for n, a in CAMS.items():
            img, _ = render_view(a, ds, seed=seed)
            if hand:
                img[200:520, 500:800] = (90, 120, 160)   # a "hand" in view
            out[n] = img
        return out

    tr.reset(frames([], seed=1))
    events = []
    seq = ([frames([], seed=s) for s in range(2, 5)] +
           [frames(darts[:1], seed=s) for s in range(5, 15)] +
           [frames(darts[:2], seed=s) for s in range(15, 25)] +
           [frames(darts[:2], hand=True, seed=s) for s in range(25, 28)] +
           [frames([], seed=s) for s in range(28, 40)])
    for fr in seq:
        ev = tr.update(fr)
        if ev:
            events.append((ev["type"], ev.get("label")))
    print("tracker events:", events)
    assert [e[0] for e in events] == ["DART", "DART", "TAKEOUT"], events
    assert events[0][1] == "T20", events
    print("tracker: ok")


if __name__ == "__main__":
    test_scoring()
    test_tracker()
    acc = test_detection(int(os.environ.get("DV_DARTS", 150)))
    floor = float(os.environ.get("DV_MIN_ACCURACY", 0))
    if acc < floor:
        sys.exit(f"accuracy {acc:.1%} below {floor:.0%}")
