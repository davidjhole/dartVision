"""Synthetic camera views of the board, rendered from the real camera positions
on the halo, with fake darts. Used to test calibration maths, detection and
scoring without hardware."""
import math

import cv2
import numpy as np

from dartvision import board

W, H_IMG = 1280, 720
HFOV = 92.0                       # 100 deg diagonal lens on a 16:9 sensor
CAM_R, CAM_Z = 271.7, 48.5        # lens radius from bull / height above board face (halo v3)


def camera_matrices(angle_deg, r=CAM_R, z=CAM_Z):
    f = (W / 2) / math.tan(math.radians(HFOV / 2))
    K = np.array([[f, 0, W / 2], [0, f, H_IMG / 2], [0, 0, 1]])
    a = math.radians(angle_deg)
    C = np.array([r * math.cos(a), r * math.sin(a), z])
    fwd = -C / np.linalg.norm(C)                 # aim at the bull
    up = np.array([0, 0, 1.0])                   # away from the board = image up
    right = np.cross(fwd, up); right /= np.linalg.norm(right)
    down = np.cross(fwd, right)
    R = np.stack([right, down, fwd])
    t = -R @ C
    return K, R, t


def project(K, R, t, P):
    P = np.atleast_2d(P).astype(float)
    c = (R @ P.T).T + t
    uv = (K @ c.T).T
    return uv[:, :2] / uv[:, 2:3], c[:, 2]


def plane_H(K, R, t):
    """board plane (z=0, mm) -> image homography"""
    return K @ np.stack([R[:, 0], R[:, 1], t], 1)


_TOP = None


def render_view(angle_deg, darts=(), noise=2.0, seed=0):
    """Render one camera's view with darts at board positions [(x, y), ...] (mm)."""
    global _TOP
    if _TOP is None:
        _TOP = board.render_board(px_per_mm=2.0, margin=240)
    top, H_b2top = _TOP
    K, R, t = camera_matrices(angle_deg)
    Hc = plane_H(K, R, t)
    img = cv2.warpPerspective(top, Hc @ np.linalg.inv(H_b2top), (W, H_IMG), borderValue=(70, 75, 80))
    rng = np.random.default_rng(seed)
    for k, (x, y) in enumerate(darts):
        # dart: 120 mm long, tilted slightly upward like a real dart
        d = np.array([0.15 * math.cos(k), 0.25, 1.0]); d /= np.linalg.norm(d)
        pts3 = [np.array([x, y, 0.0]) + d * s for s in np.linspace(0, 120, 25)]
        uv, depth = project(K, R, t, np.array(pts3))
        for i in range(len(uv) - 1):
            if depth[i] <= 0 or depth[i + 1] <= 0:
                continue
            s = i / len(uv)
            width_mm = 2.2 if s < 0.05 else 7 if s < 0.4 else 5 if s < 0.75 else 30
            px = max(2, int(K[0, 0] * width_mm / depth[i]))
            col = (200, 200, 205) if s < 0.75 else (30, 30, 200)
            cv2.line(img, tuple(np.int32(uv[i])), tuple(np.int32(uv[i + 1])), col, px, cv2.LINE_AA)
    if noise:
        img = np.clip(img.astype(np.int16) + rng.normal(0, noise, img.shape), 0, 255).astype(np.uint8)
    return img, Hc


def clicked_points(Hc, jitter_px=0.7, seed=1):
    rng = np.random.default_rng(seed)
    pts = board.board_to_image([p for _, p in board.CALIB_POINTS], Hc)
    return pts + rng.normal(0, jitter_px, pts.shape)
