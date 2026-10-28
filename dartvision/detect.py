"""Throw detection: notice a dart landing, find its tip in each camera,
map the tips onto the board and combine them into one position.

v0.1 is deliberately "classic" computer vision (frame differencing + line
fitting). It is simple to understand and tune; a trained tip detector can
replace `find_dart_tip` later without touching anything else.
"""
import math

import cv2
import numpy as np

from . import board

SMALL_W = 320  # motion is checked on a downscaled copy for speed


def prep(frame):
    """Lightly blurred colour frame (colour helps: a silver barrel on a cream
    segment is nearly invisible in grey but not in colour)."""
    return cv2.GaussianBlur(frame, (5, 5), 0)


def small(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    h, w = g.shape[:2]
    return cv2.resize(g, (SMALL_W, int(h * SMALL_W / w)), interpolation=cv2.INTER_AREA)


def colour_diff(a, b):
    d = cv2.absdiff(a, b)
    return d.max(axis=2) if d.ndim == 3 else d


def change_fraction(a, b, thr):
    return float((cv2.absdiff(a, b) > thr).mean())


def change_mask(before, after, thr, roi=None):
    d = colour_diff(before, after)
    _, m = cv2.threshold(d, thr, 255, cv2.THRESH_BINARY)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    if roi is not None:
        m = cv2.bitwise_and(m, roi)
    return m


def _fit_axis(pts, up):
    vx, vy, x0, y0 = cv2.fitLine(pts, cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
    d = np.array([vx, vy], np.float64)
    if np.dot(d, np.array(up)) > 0:      # make d point towards the board surface
        d = -d
    return d, np.array([x0, y0], np.float64)


def find_dart_tip(before, after, H_inv, board_roi, det, up=(0.0, -1.0)):
    """Find a newly arrived dart in one camera.

    Returns the tip (image + board mm) AND the dart's axis projected onto the
    board as a line. The tip always lies on that line, even when the very point
    of the dart is hard to see, so lines from several cameras can be crossed to
    find it (see fuse_darts).
    before/after: prep()'d frames. H_inv: image->board homography.
    up: image direction pointing away from the board (towards the flights).
    """
    thr = det["diff_threshold"]
    m = change_mask(before, after, thr, board_roi)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    if n <= 1:
        return {"ok": False, "reason": "no change"}
    idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))     # biggest blob = the dart
    area = int(stats[idx, cv2.CC_STAT_AREA])
    if area < det["min_dart_px"]:
        return {"ok": False, "reason": f"blob too small ({area}px)", "area": area}
    if area > det["max_dart_px"]:
        return {"ok": False, "reason": f"blob too big ({area}px)", "area": area}
    ys, xs = np.nonzero(labels == idx)
    pts = np.stack([xs, ys], 1).astype(np.float32)
    d, c = _fit_axis(pts, up)
    proj = (pts - c) @ d
    # refit on the half nearest the board (barrel/shaft) - flights are wide and get clipped
    lower = pts[proj > np.percentile(proj, 40)]
    if len(lower) > 30:
        d, c = _fit_axis(lower, up)
    proj = (pts - c) @ d
    perp = np.abs((pts - c) @ np.array([-d[1], d[0]]))
    near = perp < max(2.5, np.percentile(perp, 50))
    end_pt = c + d * proj[near].max()
    # walk on along the axis with a lower threshold: the last few mm near the
    # board are often low-contrast (silver barrel on a cream segment)
    diff = colour_diff(before, after).astype(np.float32)
    h, w = diff.shape
    low, gap, tip = thr * 0.45, 0, end_pt
    nrm = np.array([-d[1], d[0]])
    for s in range(1, 120):
        q = end_pt + d * s
        vals = [diff[int(round(y)), int(round(x))] for x, y in (q + nrm * o for o in (-2, -1, 0, 1, 2))
                if 0 <= int(round(x)) < w and 0 <= int(round(y)) < h]
        if vals and max(vals) > low:
            tip, gap = q, 0
        else:
            gap += 1
            if gap > 4:
                break
    tip_mm = board.image_to_board([tip], H_inv)[0]
    # dart axis on the board plane: map two points of the image axis through the homography
    a_mm = board.image_to_board([tip, tip - d * 80], H_inv)
    u = a_mm[1] - a_mm[0]
    nu = np.linalg.norm(u)
    line = (tip_mm.tolist(), (u / nu).tolist()) if nu > 1e-6 else None
    length = float(proj.max() - proj.min())
    return {"ok": True, "tip_px": tip.tolist(), "tip_mm": tip_mm.tolist(), "line_mm": line,
            "area": area, "elongation": length / max(1.0, math.sqrt(area)), "axis": d.tolist()}


def fuse(points, tol_mm=12.0):
    """Combine per-camera board positions: largest group agreeing within tol_mm,
    median of that group. Returns (x, y, cameras_used) or None."""
    pts = [np.asarray(p, float) for p in points if p is not None]
    if not pts:
        return None
    best = []
    for p in pts:
        grp = [q for q in pts if np.linalg.norm(q - p) <= tol_mm]
        if len(grp) > len(best):
            best = grp
    c = np.median(np.array(best), axis=0)
    return float(c[0]), float(c[1]), len(best)


def _intersect(l1, l2):
    (p1, u1), (p2, u2) = l1, l2
    A = np.array([[u1[0], -u2[0]], [u1[1], -u2[1]]])
    if abs(np.linalg.det(A)) < 0.34:          # lines within ~20 deg of parallel
        return None
    t = np.linalg.solve(A, np.asarray(p2) - np.asarray(p1))
    return np.asarray(p1) + t[0] * np.asarray(u1)


def _ls_point(lines):
    """Point minimising squared distance to all lines."""
    A, b = np.zeros((2, 2)), np.zeros(2)
    for p, u in lines:
        u = np.asarray(u); n = np.array([-u[1], u[0]])
        A += np.outer(n, n); b += np.outer(n, n) @ np.asarray(p)
    if abs(np.linalg.det(A)) < 0.1:
        return None
    return np.linalg.solve(A, b)


def fuse_darts(results, tol_mm=12.0, line_tol_mm=6.0):
    """Combine per-camera results. Prefers crossing the dart-axis lines (robust to
    a hidden or low-contrast tip); falls back to averaging tip points.
    Returns (x, y, cameras_used, method) or None."""
    good = [r for r in results if r.get("ok")]
    tips = [r["tip_mm"] for r in good]
    lines = [tuple(map(np.asarray, r["line_mm"])) for r in good if r.get("line_mm")]
    tip_guess = fuse(tips, tol_mm * 3)
    cands = [x for i in range(len(lines)) for j in range(i + 1, len(lines))
             if (x := _intersect(lines[i], lines[j])) is not None]
    if cands:
        c0 = np.median(np.array(cands), axis=0)
        inl = [l for l in lines if abs(np.dot(c0 - l[0], [-l[1][1], l[1][0]])) < line_tol_mm]
        c = _ls_point(inl) if len(inl) >= 2 else None
        if c is not None and (tip_guess is None or np.hypot(c[0] - tip_guess[0], c[1] - tip_guess[1]) < 60):
            return float(c[0]), float(c[1]), len(inl), "lines"
    if tip_guess:
        return tip_guess[0], tip_guess[1], tip_guess[2], "tips"
    return None


class ThrowTracker:
    """Multi-camera state machine.

    IDLE   -> something moves in any camera -> MOVING
    MOVING -> everything quiet for `settle_frames` -> decide:
        no lasting change            -> ignore (dart bounced out / shadow)
        image back to the empty board -> TAKEOUT (darts pulled, turn over)
        small new blob                -> DART (find tips, fuse, score)
        large change                  -> UNKNOWN (re-baseline, ask user)
    """

    def __init__(self, calibs, det, frame_shapes):
        self.det = det
        self.calibs = calibs
        self.roi = {}
        for name, cal in calibs.items():
            shape = frame_shapes[name]
            m = board.board_mask(shape, cal["H"], board.R_DOUBLE_OUT + 10)
            # extend upwards in the image: the dart body sticks out towards the camera
            # grow the region UPWARDS in the image (towards smaller y) by 150 px
            k = np.zeros((301, 1), np.uint8); k[150:] = 1
            self.roi[name] = cv2.dilate(m, k, anchor=(0, 150))
        self.state = "IDLE"
        self.quiet = 0
        self.prev_small = {}
        self.reference = {}   # board as it was after the last settled event
        self.empty = {}       # board with no darts (start of turn)
        self.darts_on_board = 0

    def reset(self, frames):
        g = {n: prep(f) for n, f in frames.items()}
        self.reference = dict(g)
        self.empty = dict(g)
        self.ref_raw = {n: f.copy() for n, f in frames.items()}
        self.prev_small = {n: small(x) for n, x in g.items()}
        self.state, self.quiet, self.darts_on_board = "IDLE", 0, 0

    def update(self, frames):
        """Feed one frame per camera. Returns an event dict or None."""
        g = {n: prep(f) for n, f in frames.items()}
        if not self.reference:
            self.reset(frames)
            return None
        sm = {n: small(x) for n, x in g.items()}
        motion = max(change_fraction(self.prev_small[n], sm[n], self.det["diff_threshold"]) for n in sm)
        self.prev_small = sm
        if self.state == "IDLE":
            if motion > self.det["motion_on"]:
                self.state, self.quiet = "MOVING", 0
            return None
        # MOVING
        self.quiet = self.quiet + 1 if motion < self.det["motion_off"] else 0
        if self.quiet < self.det["settle_frames"]:
            return None
        self.state = "IDLE"
        before_raw = self.ref_raw
        ev = self._decide(g)
        if ev["type"] != "NOTHING":
            self.ref_raw = {n: f.copy() for n, f in frames.items()}
        ev["before_raw"] = before_raw
        return ev

    def _decide(self, g):
        thr = self.det["diff_threshold"]
        vs_ref = {n: (change_mask(self.reference[n], g[n], thr, self.roi.get(n)) > 0).sum() for n in g}
        vs_empty = {n: (change_mask(self.empty[n], g[n], thr, self.roi.get(n)) > 0).sum() for n in g}
        changed = [n for n in g if vs_ref[n] >= self.det["min_dart_px"]]
        if not changed:
            return {"type": "NOTHING"}
        if self.darts_on_board and all(vs_empty[n] < self.det["min_dart_px"] for n in g):
            self.reference = dict(g); self.empty = dict(g); self.darts_on_board = 0
            return {"type": "TAKEOUT"}
        per_cam = {}
        for n in g:
            cal = self.calibs.get(n)
            if cal is None:
                continue
            per_cam[n] = find_dart_tip(self.reference[n], g[n], cal["H_inv"], self.roi[n], self.det)
        self.reference = dict(g)
        good = [r for r in per_cam.values() if r.get("ok")]
        if not good:
            big = any(r.get("reason", "").startswith("blob too big") for r in per_cam.values())
            if big and all(vs_empty[n] < 3 * self.det["min_dart_px"] for n in g):
                self.empty = dict(g); self.darts_on_board = 0
                return {"type": "TAKEOUT", "cams": per_cam}
            return {"type": "UNKNOWN", "cams": per_cam}
        f = fuse_darts(good, self.det["fuse_tolerance_mm"])
        if f is None:
            return {"type": "UNKNOWN", "cams": per_cam}
        label, pts = board.score_at(f[0], f[1])
        self.darts_on_board += 1
        return {"type": "DART", "pos_mm": f[:2], "cams_used": f[2], "method": f[3], "label": label, "points": pts,
                "cams": per_cam}
