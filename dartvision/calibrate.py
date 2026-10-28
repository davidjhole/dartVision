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
    if existing:
        pts = [tuple(p) for p in existing["image_points"]]
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
               else f"[{cam.name}] fit error {err:.2f}px  - drag points to adjust, S save")
        cv2.rectangle(view, (0, 0), (view.shape[1], 52), (0, 0, 0), -1)
        cv2.putText(view, msg, (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(view, "F freeze  U undo  R reset  S save  N next camera  Q quit",
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
    cv2.destroyWindow(WIN)
    return {"saved": saved, "quit": k in (ord("q"), 27)}
