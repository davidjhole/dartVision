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


def _sightline(tip, H_inv, step=30.0):
    """The camera's line of sight through the tip, drawn on the board plane.

    The cameras look across the board at a very low angle, so a tip's height in the
    picture says little about how far away it is (1 px can be 10+ mm), but its left-right
    position is very precise. The image column below the tip is the board surface between
    the tip and the camera, so mapping it gives the line the dart must lie on. Lines from
    two or more cameras cross at the dart."""
    a = board.image_to_board([tip, (tip[0], tip[1] + step)], H_inv)
    u = a[1] - a[0]
    nu = float(np.linalg.norm(u))
    if not np.all(np.isfinite(a)) or nu < 1e-6:
        return None
    return a[0].tolist(), (u / nu).tolist()


def find_dart_tip(before, after, H_inv, board_roi, det, up=(0.0, -1.0)):
    """Find a newly arrived dart in one camera.

    Returns the tip (image + board mm) and the camera's sight line through it on the
    board plane (see _sightline). before/after: prep()'d frames. H_inv: image->board
    homography. up: image direction pointing away from the board (towards the flights).
    """
    thr = det["diff_threshold"]
    m = change_mask(before, after, thr, board_roi)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    if n <= 1:
        return {"ok": False, "reason": "no change"}
    idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))     # biggest blob = (part of) the dart
    area = int(stats[idx, cv2.CC_STAT_AREA])
    if area < det["min_dart_px"]:
        return {"ok": False, "reason": f"blob too small ({area}px)", "area": area}
    if area > det["max_dart_px"]:
        return {"ok": False, "reason": f"blob too big ({area}px)", "area": area}
    ys, xs = np.nonzero(labels == idx)
    pts = np.stack([xs, ys], 1).astype(np.float32)
    d, c = _fit_axis(pts, up)
    # a dart often shows as several pieces (dark flight, bright barrel, a gap where the
    # barrel matches the board behind it): add the pieces that line up with it, refit, repeat
    keep = {idx}
    for _ in range(3):
        nrm = np.array([-d[1], d[0]])
        for j in range(1, n):
            if j in keep or stats[j, cv2.CC_STAT_AREA] < 15:
                continue
            yj, xj = np.nonzero(labels == j)
            pj = np.stack([xj, yj], 1).astype(np.float32)
            if np.median(np.abs((pj - c) @ nrm)) < 12:
                keep.add(j)
        ys, xs = np.nonzero(np.isin(labels, list(keep)))
        pts = np.stack([xs, ys], 1).astype(np.float32)
        d, c = _fit_axis(pts, up)
    area = len(pts)
    nrm = np.array([-d[1], d[0]])
    proj = (pts - c) @ d
    lower = pts[proj > np.percentile(proj, 40)]               # barrel half: flights are wide
    if len(lower) > 30:
        d, c = _fit_axis(lower, up)
        nrm = np.array([-d[1], d[0]])
    proj = (pts - c) @ d
    perp = np.abs((pts - c) @ nrm)
    near = perp < max(2.5, np.percentile(perp, 50))
    end_pt = c + d * proj[near].max()
    # walk on along the axis with a lower threshold: the last few mm near the
    # board are often low-contrast (silver barrel on a cream segment)
    diff = colour_diff(before, after).astype(np.float32)
    h, w = diff.shape
    low, gap, tip = thr * 0.45, 0, end_pt
    for s in range(1, 120):
        q = end_pt + d * s
        vals = [diff[int(round(y)), int(round(x))] for x, y in (q + nrm * o for o in (-2, -1, 0, 1, 2))
                if 0 <= int(round(x)) < w and 0 <= int(round(y)) < h]
        if vals and max(vals) > low:
            tip, gap = q, 0
        else:
            gap += 1
            if gap > 10:                   # bridge short low-contrast stretches (barrel on cream)
                break
    length = float(proj.max() - proj.min())
    elong = length / max(1.0, math.sqrt(area))
    # a dart is long and thin and its tip is on the board, not up in the room behind it
    H = np.linalg.inv(H_inv)
    on_board = board.board_mask(diff.shape, H, board.R_DOUBLE_OUT + 25)
    on_board = cv2.dilate(on_board, np.ones((31, 3), np.uint8))   # tip a few px above the far edge is fine
    ti = (int(round(tip[1])), int(round(tip[0])))
    if not (0 <= ti[0] < h and 0 <= ti[1] < w) or not on_board[ti]:
        return {"ok": False, "reason": "tip not on the board", "tip_px": tip.tolist(), "area": area}
    if length < 40 or elong < 2.0:
        return {"ok": False, "reason": f"not dart-shaped (len {length:.0f}px)", "tip_px": tip.tolist(), "area": area}
    tip_mm = board.image_to_board([tip], H_inv)[0]
    return {"ok": True, "tip_px": tip.tolist(), "tip_mm": tip_mm.tolist(), "line_mm": _sightline(tip, H_inv),
            "area": area, "elongation": elong, "axis": d.tolist()}


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
    """Combine per-camera results by crossing their sight lines.

    Every pair of cameras whose lines cross at a decent angle gives a candidate; the one
    that the most cameras agree with (within line_tol_mm) wins and is refined with all of
    them. With only one usable camera the tip position is used (much less accurate).
    Returns (x, y, cameras_used, method) or None."""
    good = [r for r in results if r.get("ok")]
    lines = [tuple(map(np.asarray, r["line_mm"])) for r in good if r.get("line_mm")]
    best = None
    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            x = _intersect(lines[i], lines[j])
            if x is None or np.hypot(*x) > board.R_BOARD + 40:
                continue
            inl = [l for l in lines if abs(np.dot(x - l[0], [-l[1][1], l[1][0]])) < line_tol_mm]
            score = (len(inl), -sum(abs(np.dot(x - l[0], [-l[1][1], l[1][0]])) for l in inl))
            if best is None or score > best[0]:
                best = (score, x, inl)
    if best is not None:
        _, x, inl = best
        c = _ls_point(inl) if len(inl) >= 2 else None
        if c is None:
            c = x
        return float(c[0]), float(c[1]), len(inl), "lines"
    tips = [r["tip_mm"] for r in good]
    t = fuse(tips, tol_mm * 3)
    if t:
        return t[0], t[1], t[2], "tips"
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
        # a dart being pulled out also leaves a dart-shaped change - but there the picture goes
        # back to how the empty board looked. A new dart differs from the empty board too.
        if self.darts_on_board:
            ratios = []
            for n in changed:
                m_ref = change_mask(self.reference[n], g[n], thr, self.roi.get(n)) > 0
                m_emp = change_mask(self.empty[n], g[n], thr, self.roi.get(n)) > 0
                ratios.append((m_ref & m_emp).sum() / max(1, m_ref.sum()))
            if ratios and float(np.median(ratios)) < 0.35:
                self.reference = dict(g)
                self.darts_on_board = max(0, self.darts_on_board - 1)
                return {"type": "REMOVED"}
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
            if big and self.darts_on_board:
                return {"type": "NOTHING", "cams": per_cam}     # a hand pulling darts out
            if not big:
                # something moved (someone walking past, a hand near the board) but nothing
                # dart-shaped arrived on the board: ignore it
                return {"type": "NOTHING", "cams": per_cam}
            return {"type": "UNKNOWN", "cams": per_cam}
        f = fuse_darts(good, self.det["fuse_tolerance_mm"])
        if f is None or f[2] < 2:
            # one camera alone can't place a dart reliably (it only knows the direction)
            return {"type": "UNKNOWN", "cams": per_cam}
        label, pts = board.score_at(f[0], f[1])
        self.darts_on_board += 1
        return {"type": "DART", "pos_mm": f[:2], "cams_used": f[2], "method": f[3], "label": label, "points": pts,
                "cams": per_cam}
