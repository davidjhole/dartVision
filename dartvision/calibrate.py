"""Click-to-calibrate: map each camera's image onto the board plane.

For each camera you click 5 points (bull + 4 places where a wire meets the
outer edge of the double ring). From those we compute a homography, i.e. the
mapping between camera pixels and millimetres on the board face, and draw the
whole wire layout back over the live image so you can see it fits.
"""
import cv2
import numpy as np

from . import board
from .config import save_calibration, load_calibration

WIN = "dartvision calibrate"


def compute_homography(image_points, board_points):
    img = np.asarray(image_points, np.float64)
    brd = np.asarray(board_points, np.float64)
    H, _ = cv2.findHomography(brd, img, 0)
    if H is None:
        raise ValueError("points are degenerate (all in a line?)")
    proj = board.board_to_image(brd, H)
    err = float(np.sqrt(((proj - img) ** 2).sum(1)).mean())
    return H, err


def _guide(target_idx, size=220):
    """Small top-down board with the point to click highlighted."""
    img, H = board.render_board(px_per_mm=size / 480)
    for i, (_, p) in enumerate(board.CALIB_POINTS):
        q = board.board_to_image([p], H)[0].astype(int)
        col = (0, 255, 255) if i == target_idx else (120, 120, 120)
        cv2.circle(img, tuple(q), 7 if i == target_idx else 4, col, 2 if i == target_idx else -1, cv2.LINE_AA)
    return img


def _magnifier(frame, x, y, half=30, zoom=5):
    h, w = frame.shape[:2]
    x0, y0 = max(0, x - half), max(0, y - half)
    x1, y1 = min(w, x + half), min(h, y + half)
    crop = frame[y0:y1, x0:x1]
    if crop.size == 0:
        return None
    big = cv2.resize(crop, None, fx=zoom, fy=zoom, interpolation=cv2.INTER_NEAREST)
    cx, cy = (x - x0) * zoom + zoom // 2, (y - y0) * zoom + zoom // 2
    cv2.line(big, (cx - 15, cy), (cx + 15, cy), (0, 255, 255), 1)
    cv2.line(big, (cx, cy - 15), (cx, cy + 15), (0, 255, 255), 1)
    cv2.rectangle(big, (0, 0), (big.shape[1] - 1, big.shape[0] - 1), (0, 255, 255), 1)
    return big


def calibrate_camera(cam, folder="calib"):
    """Interactive calibration for one camera. Returns {saved, quit}."""
    n_pts = len(board.CALIB_POINTS)
    existing = load_calibration(cam.name, folder)
    pts = [None] * n_pts
    bp = existing.get("board_points_mm") if existing else None
    if bp and len(bp) == n_pts and np.allclose(bp, [p for _, p in board.CALIB_POINTS], atol=0.5):
        pts = [tuple(p) for p in existing["image_points"]]     # (saved from the page with other points: start fresh)
    state = {"mouse": (0, 0), "drag": None, "frozen": None}

    def on_mouse(ev, x, y, flags, _):
        state["mouse"] = (x, y)
        if ev == cv2.EVENT_LBUTTONDOWN:
            # grab a nearby point to drag, otherwise place the next missing one
            near = [i for i, p in enumerate(pts) if p and np.hypot(p[0] - x, p[1] - y) < 12]
            if near:
                state["drag"] = near[0]
            elif None in pts:
                pts[pts.index(None)] = (float(x), float(y))
        elif ev == cv2.EVENT_MOUSEMOVE and state["drag"] is not None:
            pts[state["drag"]] = (float(x), float(y))
        elif ev == cv2.EVENT_LBUTTONUP:
            state["drag"] = None

    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN, *cam.size)
    cv2.setMouseCallback(WIN, on_mouse)
    saved = False
    while True:
        frame = state["frozen"] if state["frozen"] is not None else cam.read()
        if frame is None:
            continue
        view = frame.copy()
        done = None not in pts
        if done:
            H, err = compute_homography(pts, [p for _, p in board.CALIB_POINTS])
            board.draw_board_overlay(view, H, (0, 255, 0), 1)
        for i, p in enumerate(pts):
            if p:
                q = (int(round(p[0])), int(round(p[1])))
                cv2.circle(view, q, 5, (0, 255, 255), 1, cv2.LINE_AA)
                cv2.putText(view, str(i + 1), (q[0] + 7, q[1] - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        nxt = pts.index(None) if not done else None
        msg = (f"[{cam.name}] click {nxt + 1}/{n_pts}: {board.CALIB_POINTS[nxt][0]}" if nxt is not None
               else f"[{cam.name}] fit error {err:.2f}px  - drag points to adjust, S to save + next camera")
        cv2.rectangle(view, (0, 0), (view.shape[1], 52), (0, 0, 0), -1)
        cv2.putText(view, msg, (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(view, "F freeze  U undo  R reset  S save + next  N skip camera  Q quit",
                    (10, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (170, 170, 170), 1, cv2.LINE_AA)
        g = _guide(nxt if nxt is not None else -1)
        view[60:60 + g.shape[0], 10:10 + g.shape[1]] = g
        mag = _magnifier(frame, *state["mouse"])
        if mag is not None:
            h, w = mag.shape[:2]
            view[60:60 + h, view.shape[1] - w - 10:view.shape[1] - 10] = mag
        if state["frozen"] is not None:
            cv2.putText(view, "FROZEN", (view.shape[1] - 120, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.imshow(WIN, view)
        k = cv2.waitKey(15) & 0xFF
        if k in (ord("q"), 27):
            break
        if k == ord("n"):
            if done and not saved and not state.get("skip_warned"):
                print(f"[{cam.name}] not saved - press S to save, or N again to skip this camera")
                state["skip_warned"] = True
                continue
            break
        if k == ord("f"):
            state["frozen"] = None if state["frozen"] is not None else frame.copy()
        if k == ord("r"):
            pts[:] = [None] * n_pts
        if k == ord("u"):
            placed = [i for i, p in enumerate(pts) if p]
            if placed:
                pts[placed[-1]] = None
        if k == ord("s") and done:
            save_calibration(cam.name, pts, [p for _, p in board.CALIB_POINTS], H, cam.size, folder)
            print(f"saved calibration for {cam.name} (fit error {err:.2f}px)")
            saved = True
            break                                   # straight on to the next camera
    cv2.destroyWindow(WIN)
    return {"saved": saved, "quit": k in (ord("q"), 27)}


# ------------------------------------------------------------------ calibrating from the web page
def wire_lines(H):
    """The board's wires as polylines in image pixels, for the web page to draw over the picture."""
    out = []
    for r in (board.R_BULL, board.R_OUTER_BULL, board.R_TRIPLE_IN, board.R_TRIPLE_OUT,
              board.R_DOUBLE_IN, board.R_DOUBLE_OUT):
        out.append(board.board_to_image(board._circle_pts(r, 96), H))
    for i in range(20):
        a = np.radians(90 - 18 * i - 9)
        seg = [(board.R_OUTER_BULL * np.cos(a), board.R_OUTER_BULL * np.sin(a)),
               (board.R_DOUBLE_OUT * np.cos(a), board.R_DOUBLE_OUT * np.sin(a))]
        out.append(board.board_to_image(seg, H))
    return [[[round(float(x), 1), round(float(y), 1)] for x, y in line] for line in out]


def web_targets():
    """Points the page can ask for: the bull, then where each of the 20 sector wires meets the outer
    edge of the double ring (clockwise from the wire between 20 and 1). The page suggests the usual
    four (CALIB_POINTS), but any of them can be used: from a low camera one of the usual four can be
    out of the picture."""
    out = [("bull centre", (0.0, 0.0))]
    for i in range(20):
        left, right = board.SECTORS[i], board.SECTORS[(i + 1) % 20]
        a = np.radians(board.sector_boundary_angle(left, right))
        out.append((f"outer double wire between {left} and {right}",
                    (board.R_DOUBLE_OUT * np.cos(a), board.R_DOUBLE_OUT * np.sin(a))))
    return out


WEB_TARGETS = web_targets()


def _target_index(mm):
    d = [np.hypot(p[0] - mm[0], p[1] - mm[1]) for _, p in WEB_TARGETS]
    i = int(np.argmin(d))
    return i if d[i] < 0.5 else None


DEFAULT_TARGETS = [_target_index(p) for _, p in board.CALIB_POINTS]
MIN_POINTS = 4


class WebCalibrator:
    """Calibration through the phone / PC web page instead of a window on the computer, so a Pi
    with no screen can be calibrated without VNC. The page fetches a still picture from each
    camera, you tap the points on it (at least 4, normally 5) and it sends them back here to check and save.

    Called from the web server's threads; Camera.read() is thread-safe and returns a copy.
    """

    def __init__(self, cams, folder="calib", on_saved=None):
        self.cams = {c.name: c for c in cams}
        self.order = [c.name for c in cams]
        self.folder = folder
        self.on_saved = on_saved

    def cameras(self):
        out = []
        for n in self.order:
            cal = load_calibration(n, self.folder)
            pts = tg = None
            if cal:
                tg = [_target_index(p) for p in cal.get("board_points_mm", [])]
                if None in tg or len(tg) != len(cal["image_points"]):
                    tg = None
                else:
                    pts = cal["image_points"]
            out.append({"name": n, "size": list(self.cams[n].size),
                        "saved": cal["saved"] if cal else None,
                        "image_size": cal.get("image_size") if cal else None,
                        "points": pts, "point_targets": tg})
        return {"cameras": out, "default": DEFAULT_TARGETS, "min": MIN_POINTS,
                "targets": [{"name": t, "mm": [round(float(p[0]), 2), round(float(p[1]), 2)]} for t, p in WEB_TARGETS]}

    def frame_jpeg(self, name, quality=88):
        cam = self.cams.get(name)
        f = cam.read() if cam else None
        if f is None:
            return None
        ok, buf = cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return buf.tobytes() if ok else None

    def _points(self, name, points, targets=None):
        """Check what the page sent. Returns (image points, board points in mm)."""
        if name not in self.cams:
            raise ValueError(f"no camera called {name!r}")
        try:
            pts = [(float(p[0]), float(p[1])) for p in points]
        except (TypeError, ValueError, IndexError, KeyError):
            raise ValueError("points must be [x, y] pairs")
        if targets is None:                       # the original page: the usual 5, in order
            targets = DEFAULT_TARGETS[:len(pts)]
        try:
            targets = [int(t) for t in targets]
        except (TypeError, ValueError):
            raise ValueError("targets must be numbers")
        if len(targets) != len(pts) or any(not 0 <= t < len(WEB_TARGETS) for t in targets):
            raise ValueError("each point needs a target")
        if len(set(targets)) != len(targets):
            raise ValueError("the same point is used twice")
        if len(pts) < MIN_POINTS:
            raise ValueError(f"need at least {MIN_POINTS} points")
        if not np.isfinite(pts).all():
            raise ValueError("points must be numbers")
        return pts, [WEB_TARGETS[t][1] for t in targets]

    def preview(self, name, points, targets=None):
        """Fit the points without saving: fit error + wire overlay to draw."""
        pts, mm = self._points(name, points, targets)
        H, err = compute_homography(pts, mm)
        return {"ok": True, "err": round(err, 2), "lines": wire_lines(H), "checked": len(pts) > MIN_POINTS}

    def save(self, name, points, targets=None):
        pts, mm = self._points(name, points, targets)
        H, err = compute_homography(pts, mm)
        save_calibration(name, pts, mm, H, self.cams[name].size, self.folder)
        print(f"saved calibration for {name} from the web page (fit error {err:.2f}px)")
        if self.on_saved:
            self.on_saved(name)
        return {"ok": True, "err": round(err, 2)}
