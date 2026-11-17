"""Game screen: drawn to whatever size the window is (works resized and full screen)."""
import cv2
import numpy as np

from . import board

BG, PANEL, CARD, ACTIVE = (24, 22, 20), (34, 31, 29), (48, 44, 41), (40, 110, 230)
WHITE, GREY, DIM = (245, 245, 245), (160, 160, 160), (95, 95, 95)
ACCENT, GOOD, BAD = (0, 200, 255), (90, 210, 90), (60, 60, 230)
FONT, BOLD = cv2.FONT_HERSHEY_SIMPLEX, cv2.FONT_HERSHEY_DUPLEX
MARK_COLS = [(0, 200, 255), (255, 160, 60), (200, 90, 255)]


def window_size(name, default=(1600, 900)):
    """Current drawable size of an OpenCV window (falls back to default)."""
    try:
        _, _, w, h = cv2.getWindowImageRect(name)
        if w >= 320 and h >= 240:
            return int(w), int(h)
    except cv2.error:
        pass
    return default


def fit(img, w, h, bg=BG):
    """Scale img to fit w x h without stretching, centred on a plain background."""
    s = min(w / img.shape[1], h / img.shape[0])
    nw, nh = max(1, int(img.shape[1] * s)), max(1, int(img.shape[0] * s))
    out = np.full((h, w, 3), bg, np.uint8)
    x, y = (w - nw) // 2, (h - nh) // 2
    out[y:y + nh, x:x + nw] = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
    return out


def text(img, s, org, size, col=WHITE, thick=1, font=FONT, anchor="l"):
    """Text at org (x = left / centre / right per anchor, y = baseline)."""
    (tw, _), _ = cv2.getTextSize(s, font, size, thick)
    x, y = org
    if anchor == "c":
        x -= tw // 2
    elif anchor == "r":
        x -= tw
    cv2.putText(img, s, (int(x), int(y)), font, size, col, thick, cv2.LINE_AA)
    return tw


def fit_size(s, font, thick, max_w, max_size):
    """Largest text size <= max_size that fits max_w."""
    size = max_size
    while size > 0.3:
        (tw, _), _ = cv2.getTextSize(s, font, size, thick)
        if tw <= max_w:
            break
        size *= 0.92
    return size


def box(img, p0, p1, col, r=10):
    x0, y0 = p0
    x1, y1 = p1
    r = int(max(0, min(r, (x1 - x0) // 2, (y1 - y0) // 2)))
    cv2.rectangle(img, (x0 + r, y0), (x1 - r, y1), col, -1)
    cv2.rectangle(img, (x0, y0 + r), (x1, y1 - r), col, -1)
    for cx, cy in ((x0 + r, y0 + r), (x1 - r, y0 + r), (x0 + r, y1 - r), (x1 - r, y1 - r)):
        cv2.circle(img, (cx, cy), r, col, -1, cv2.LINE_AA)


def camera_grid(frames, names, overlays, w, h):
    """2 x 2 (or 1 x n) camera tiles filling w x h."""
    n = len(frames)
    cols = 2 if n > 1 else 1
    rows = (n + cols - 1) // cols
    tw, th = w // cols, h // rows
    out = np.full((h, w, 3), BG, np.uint8)
    for i, (f, name) in enumerate(zip(frames, names)):
        r, c = divmod(i, cols)
        t = fit(f, tw - 4, th - 4)
        s = min((tw - 4) / f.shape[1], (th - 4) / f.shape[0])
        ox, oy = ((tw - 4) - int(f.shape[1] * s)) // 2, ((th - 4) - int(f.shape[0] * s)) // 2
        if overlays and overlays[i] is not None:
            sub = np.ascontiguousarray(t[oy:oy + int(f.shape[0] * s), ox:ox + int(f.shape[1] * s)])
            overlays[i](sub, s, s)
            t[oy:oy + sub.shape[0], ox:ox + sub.shape[1]] = sub
        text(t, name, (ox + 8, oy + 20), 0.5, WHITE, 1)
        out[r * th + 2:r * th + th - 2, c * tw + 2:c * tw + tw - 2] = t
    return out


_BOARD_CACHE = {}


def board_view(size, marks):
    """Top-down board with this turn's darts marked."""
    if size not in _BOARD_CACHE:
        img, H = board.render_board(px_per_mm=size / 470.0, margin=235)
        img = cv2.resize(img, (size, size))
        img[(img == 30).all(axis=2)] = BG          # blend the square background into the screen
        _BOARD_CACHE[size] = (img, H, size / img.shape[0])
    img, H, k = _BOARD_CACHE[size]
    img = img.copy()
    for i, (x, y, lab) in enumerate(marks):
        p = board.board_to_image([(x, y)], H)[0] * k
        col = MARK_COLS[i % 3]
        cv2.circle(img, (int(p[0]), int(p[1])), max(5, size // 45), col, -1, cv2.LINE_AA)
        cv2.circle(img, (int(p[0]), int(p[1])), max(5, size // 45), (20, 20, 20), 1, cv2.LINE_AA)
    return img


def draw_play(W, H, game, frames, names, overlays, status, marks, hint=None, note=None):
    """The whole game screen. Left: scores + this turn. Right: board + cameras."""
    out = np.full((H, W, 3), BG, np.uint8)
    u = H / 900.0                                   # scale everything with the window height
    pad = int(24 * u)
    left_w = int(W * 0.46)
    right_x = left_w + pad

    # ---- header
    text(out, f"{game.start}  double out", (pad, int(48 * u)), 0.8 * u, GREY, 1)
    if game.winner:
        text(out, f"{game.winner} WINS!", (left_w - pad, int(50 * u)), 1.2 * u, GOOD, 2, BOLD, "r")

    # ---- players
    y = int(80 * u)
    n = len(game.players)
    card_h = int(min(190, 560 / max(1, n)) * u)
    for i, pl in enumerate(game.players):
        active = i == game.cur
        box(out, (pad, y), (left_w - pad, y + card_h - int(10 * u)), CARD if active else PANEL, int(14 * u))
        if active:
            box(out, (pad, y), (pad + int(10 * u), y + card_h - int(10 * u)), ACTIVE, int(4 * u))
        inner_h = card_h - int(10 * u)
        name_sz = fit_size(pl, BOLD, 2, int((left_w - 2 * pad) * 0.42), 1.3 * u)
        text(out, pl, (pad + int(30 * u), y + int(inner_h * 0.42)), name_sz, WHITE if active else GREY, 2, BOLD)
        text(out, f"avg {game.three_dart_avg(pl):.1f}", (pad + int(30 * u), y + int(inner_h * 0.75)),
             0.65 * u, GREY, 1)
        score = str(game.scores[pl])
        ssz = fit_size(score, BOLD, 4, int((left_w - 2 * pad) * 0.5), inner_h / 46.0)
        text(out, score, (left_w - pad - int(24 * u), y + int(inner_h * 0.5 + 18 * ssz)),
             ssz, (ACCENT if active else WHITE), max(2, int(4 * u)), BOLD, "r")
        y += card_h

    # ---- this turn: three dart boxes and the total
    y += int(10 * u)
    text(out, f"{game.player} - this turn", (pad, y + int(22 * u)), 0.7 * u, GREY, 1)
    y += int(36 * u)
    bw = (left_w - 2 * pad - 2 * int(14 * u)) // 3
    bh = int(110 * u)
    for j in range(3):
        x0 = pad + j * (bw + int(14 * u))
        has = j < len(game.turn)
        box(out, (x0, y), (x0 + bw, y + bh), CARD if has else PANEL, int(12 * u))
        if has:
            lab, pts = game.turn[j]
            box(out, (x0, y), (x0 + bw, y + int(6 * u)), MARK_COLS[j], int(3 * u))
            lsz = fit_size(lab, BOLD, 2, bw - int(20 * u), 1.5 * u)
            text(out, lab, (x0 + bw // 2, y + int(bh * 0.55)), lsz, WHITE, 2, BOLD, "c")
            text(out, str(pts), (x0 + bw // 2, y + int(bh * 0.85)), 0.7 * u, GREY, 1, FONT, "c")
        else:
            text(out, "-", (x0 + bw // 2, y + int(bh * 0.6)), 1.2 * u, DIM, 2, BOLD, "c")
    y += bh + int(44 * u)
    total = sum(p for _, p in game.turn)
    tw = text(out, "turn ", (pad, y), 0.8 * u, GREY, 1)
    text(out, f"{total}", (pad + tw, y), 1.5 * u, WHITE, 2, BOLD)
    if game.bust:
        text(out, "BUST - pull the darts", (left_w - pad, y), 0.9 * u, BAD, 2, BOLD, "r")
    elif hint:
        text(out, f"checkout  {hint}", (left_w - pad, y), 0.8 * u, GOOD, 2, BOLD, "r")

    # ---- status + keys at the bottom left
    yb = H - pad
    keys = "C correct    U undo    M miss    N next player    R darts out    Q quit"
    text(out, keys, (pad, yb), fit_size(keys, FONT, 1, left_w - 2 * pad, 0.55 * u), DIM, 1)
    text(out, status[:60], (pad, yb - int(34 * u)), fit_size(status[:60], FONT, 1, left_w - 2 * pad, 0.75 * u),
         ACCENT, 1)
    if note:
        text(out, note, (pad, yb - int(66 * u)), 0.55 * u, GOOD, 1)

    # ---- right: board on top, cameras below
    rw = W - right_x - pad
    cam_h = int(rw * 9 / 16)                      # 2 x 2 grid of 16:9 tiles at this width
    bsize = max(120, min(rw, H - cam_h - 3 * pad))
    bimg = board_view(bsize, marks)
    bx = right_x + (rw - bsize) // 2
    out[pad:pad + bsize, bx:bx + bsize] = bimg
    cy = pad + bsize + pad
    ch = H - cy - pad
    if ch > 60 and frames:
        cw = min(rw, int(ch * 16 / 9))
        grid = camera_grid(frames, names, overlays, cw, ch)
        out[cy:cy + ch, right_x + (rw - cw) // 2:right_x + (rw - cw) // 2 + cw] = grid
    return out
