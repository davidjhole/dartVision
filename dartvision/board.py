"""Standard steel-tip dartboard geometry, scoring and drawing helpers.

Board coordinates are millimetres with the bull at (0, 0), x to the right
and y UP (towards the 20).
"""
import math

import cv2
import numpy as np

# Sector numbers clockwise starting from the top.
SECTORS = [20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5]

# Radii in mm (WDF / PDC regulation board, measured to the wire centres).
R_BULL = 6.35          # inner bull (50)
R_OUTER_BULL = 15.9    # outer bull (25)
R_TRIPLE_IN = 99.0
R_TRIPLE_OUT = 107.0
R_DOUBLE_IN = 162.0
R_DOUBLE_OUT = 170.0
R_BOARD = 225.5        # edge of a 451 mm board


def sector_boundary_angle(left, right):
    """Angle (deg, maths convention: 0 = 3 o'clock, CCW +) of the wire between
    two neighbouring sectors, where `right` is clockwise of `left`."""
    i = SECTORS.index(left)
    assert SECTORS[(i + 1) % 20] == right, f"{left} and {right} are not neighbours"
    centre = 90 - 18 * i
    return centre - 9


# Calibration targets: the bull plus four points where a sector wire meets the
# OUTER edge of the double ring. These are easy to see from any camera angle.
CALIB_POINTS = [("bull centre", (0.0, 0.0))]
for left, right in ((20, 1), (6, 10), (3, 19), (11, 14)):
    a = math.radians(sector_boundary_angle(left, right))
    CALIB_POINTS.append((f"outer double wire between {left} and {right}",
                         (R_DOUBLE_OUT * math.cos(a), R_DOUBLE_OUT * math.sin(a))))


def score_at(x, y):
    """Return (label, points) for a hit at board position (x, y) in mm."""
    r = math.hypot(x, y)
    if r <= R_BULL:
        return "DB", 50
    if r <= R_OUTER_BULL:
        return "SB", 25
    if r > R_DOUBLE_OUT:
        return "MISS", 0
    ang = math.degrees(math.atan2(y, x))
    clockwise_from_top = (90 - ang) % 360
    n = SECTORS[int(((clockwise_from_top + 9) % 360) // 18)]
    if R_TRIPLE_IN < r <= R_TRIPLE_OUT:
        return f"T{n}", 3 * n
    if R_DOUBLE_IN < r <= R_DOUBLE_OUT:
        return f"D{n}", 2 * n
    return f"S{n}", n


def parse_score(text):
    """'T20' -> 60, 'D16' -> 32, 'S5'/'5' -> 5, 'SB'/'25' -> 25, 'DB'/'50'/'BULL' -> 50, 'MISS'/'0' -> 0."""
    t = text.strip().upper()
    if t in ("DB", "BULL", "50", "D25"):
        return "DB", 50
    if t in ("SB", "25", "OB"):
        return "SB", 25
    if t in ("MISS", "M", "0", ""):
        return "MISS", 0
    mult = {"T": 3, "D": 2, "S": 1}.get(t[0], None)
    num = t[1:] if mult else t
    mult = mult or 1
    n = int(num)
    if not 1 <= n <= 20:
        raise ValueError(f"bad score: {text}")
    return f"{'SDT'[mult - 1]}{n}", mult * n


# ---------------------------------------------------------------- drawing
def _circle_pts(r, n=180):
    t = np.linspace(0, 2 * np.pi, n, endpoint=True)
    return np.stack([r * np.cos(t), r * np.sin(t)], axis=1)


def board_to_image(pts_mm, H):
    """Map Nx2 board points (mm) into the image with homography H (board->image)."""
    pts = np.asarray(pts_mm, dtype=np.float64).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(pts, H).reshape(-1, 2)


def image_to_board(pts_px, H_inv):
    pts = np.asarray(pts_px, dtype=np.float64).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(pts, H_inv).reshape(-1, 2)


def draw_board_overlay(img, H, color=(0, 255, 0), thickness=1, numbers=True):
    """Draw the wire layout of a regulation board onto a camera image."""
    for r in (R_BULL, R_OUTER_BULL, R_TRIPLE_IN, R_TRIPLE_OUT, R_DOUBLE_IN, R_DOUBLE_OUT):
        p = board_to_image(_circle_pts(r), H).astype(np.int32)
        cv2.polylines(img, [p], True, color, thickness, cv2.LINE_AA)
    for i in range(20):
        a = math.radians(90 - 18 * i - 9)
        seg = [(R_OUTER_BULL * math.cos(a), R_OUTER_BULL * math.sin(a)),
               (R_DOUBLE_OUT * math.cos(a), R_DOUBLE_OUT * math.sin(a))]
        p = board_to_image(seg, H).astype(np.int32)
        cv2.line(img, tuple(p[0]), tuple(p[1]), color, thickness, cv2.LINE_AA)
    if numbers:
        for i, n in enumerate(SECTORS):
            a = math.radians(90 - 18 * i)
            p = board_to_image([(190 * math.cos(a), 190 * math.sin(a))], H)[0]
            cv2.putText(img, str(n), (int(p[0]) - 8, int(p[1]) + 6), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, color, 1, cv2.LINE_AA)
    return img


def board_mask(shape, H, radius=R_DOUBLE_OUT + 8):
    """Binary mask of the scoring area as seen by a camera."""
    m = np.zeros(shape[:2], np.uint8)
    p = board_to_image(_circle_pts(radius), H).astype(np.int32)
    cv2.fillPoly(m, [p], 255)
    return m


def render_board(px_per_mm=2.0, margin=240):
    """Top-down picture of a board (for tests and the scoreboard). Returns (img, H_board_to_img)."""
    size = int(2 * margin * px_per_mm)
    img = np.full((size, size, 3), 30, np.uint8)
    c = size / 2
    H = np.array([[px_per_mm, 0, c], [0, -px_per_mm, c], [0, 0, 1]], dtype=np.float64)
    cv2.circle(img, (int(c), int(c)), int(R_BOARD * px_per_mm), (25, 25, 25), -1)
    dark, light = (20, 20, 20), (190, 220, 235)
    red, green = (40, 40, 200), (60, 140, 40)
    for i in range(20):
        a0 = 90 - 18 * i - 9
        even = i % 2 == 0
        for r_out, col in ((R_DOUBLE_OUT, red if even else green), (R_DOUBLE_IN, dark if even else light),
                           (R_TRIPLE_OUT, red if even else green), (R_TRIPLE_IN, dark if even else light)):
            t = np.radians(np.linspace(a0, a0 + 18, 12))
            outer = np.stack([r_out * np.cos(t), r_out * np.sin(t)], 1)
            poly = np.vstack([[[0, 0]], outer])
            cv2.fillPoly(img, [board_to_image(poly, H).astype(np.int32)], col, cv2.LINE_AA)
    cv2.circle(img, (int(c), int(c)), int(R_OUTER_BULL * px_per_mm), green, -1, cv2.LINE_AA)
    cv2.circle(img, (int(c), int(c)), int(R_BULL * px_per_mm), red, -1, cv2.LINE_AA)
    draw_board_overlay(img, H, (180, 180, 180), 1, numbers=True)
    return img, H
