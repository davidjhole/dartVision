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


def draw_play(W, H, game, frames, names, overlays, status, marks, show_cams=False, note=None, edit=None):
    """The whole game screen. Returns (image, clickable areas {name: (x0, y0, x1, y1)}).
    Left: scores + this turn. Right: board with this turn's darts (+ cameras if show_cams)."""
    out = np.full((H, W, 3), BG, np.uint8)
    hits = {}
    u = H / 900.0                                   # scale everything with the window height
    pad = int(24 * u)
    left_w = int(W * (0.46 if show_cams else 0.52))
    right_x = left_w + pad

    # ---- header
    title = getattr(game, "mode_title", game.name)
    if game.legs_to_win > 1:
        title += f"   first to {game.legs_to_win} legs"
    text(out, title, (pad, int(48 * u)), fit_size(title, FONT, 1, left_w - 2 * pad, 0.8 * u), GREY, 1)

    # ---- players
    y = int(72 * u)
    n = len(game.players)
    card_h = int(min(170, 520 / max(1, n)) * u)
    for i, pl in enumerate(game.players):
        active = i == game.cur
        inner_h = card_h - int(10 * u)
        box(out, (pad, y), (left_w - pad, y + inner_h), CARD if active else PANEL, int(14 * u))
        if active:
            box(out, (pad, y), (pad + int(10 * u), y + inner_h), ACTIVE, int(4 * u))
        big, small_txt = game.card(pl)
        name_sz = fit_size(pl, BOLD, 2, int((left_w - 2 * pad) * 0.42), min(1.3 * u, inner_h / 70))
        text(out, pl, (pad + int(30 * u), y + int(inner_h * 0.45)), name_sz, WHITE if active else GREY, 2, BOLD)
        text(out, small_txt, (pad + int(30 * u), y + int(inner_h * 0.78)), min(0.65 * u, inner_h / 120), GREY, 1)
        ssz = fit_size(big, BOLD, 4, int((left_w - 2 * pad) * 0.5), inner_h / 46.0)
        text(out, big, (left_w - pad - int(24 * u), y + int(inner_h * 0.5 + 18 * ssz)),
             ssz, (ACCENT if active else WHITE), max(2, int(4 * u)), BOLD, "r")
        if game.legs_to_win > 1:
            for k in range(game.legs_to_win):           # leg dots
                cx = pad + int(30 * u) + k * int(18 * u)
                cv2.circle(out, (cx, y + int(inner_h * 0.9)), int(5 * u), GOOD if k < game.legs[pl] else DIM, -1,
                           cv2.LINE_AA)
        y += card_h

    # ---- this turn: three dart boxes (click one to correct it)
    y += int(6 * u)
    text(out, f"{game.player} - this turn", (pad, y + int(22 * u)), 0.7 * u, GREY, 1)
    text(out, "click a dart or press 1 2 3 to correct it", (left_w - pad, y + int(22 * u)), 0.5 * u, DIM, 1,
         FONT, "r")
    y += int(36 * u)
    bw = (left_w - 2 * pad - 2 * int(14 * u)) // 3
    bh = int(110 * u)
    for j in range(3):
        x0 = pad + j * (bw + int(14 * u))
        has = j < len(game.turn)
        box(out, (x0, y), (x0 + bw, y + bh), CARD if has else PANEL, int(12 * u))
        if edit == j:
            cv2.rectangle(out, (x0, y), (x0 + bw, y + bh), ACCENT, max(1, int(3 * u)))
        if has:
            lab, pts = game.turn[j]
            box(out, (x0, y), (x0 + bw, y + int(6 * u)), MARK_COLS[j], int(3 * u))
            lsz = fit_size(lab, BOLD, 2, bw - int(20 * u), 1.5 * u)
            text(out, lab, (x0 + bw // 2, y + int(bh * 0.55)), lsz, WHITE, 2, BOLD, "c")
            text(out, str(pts), (x0 + bw // 2, y + int(bh * 0.85)), 0.7 * u, GREY, 1, FONT, "c")
        else:
            text(out, "-", (x0 + bw // 2, y + int(bh * 0.6)), 1.2 * u, DIM, 2, BOLD, "c")
        hits[f"dart{j}"] = (x0, y, x0 + bw, y + bh)
    y += bh + int(44 * u)
    total = sum(p for _, p in game.turn)
    tw = text(out, "turn ", (pad, y), 0.8 * u, GREY, 1)
    text(out, f"{total}", (pad + tw, y), 1.5 * u, WHITE, 2, BOLD)
    hint = game.hint()
    if game.bust:
        text(out, "BUST - pull the darts", (left_w - pad, y), 0.9 * u, BAD, 2, BOLD, "r")
    elif hint:
        text(out, hint, (left_w - pad, y), fit_size(hint, BOLD, 2, left_w // 2, 0.8 * u), GOOD, 2, BOLD, "r")

    # ---- status + keys at the bottom left
    yb = H - pad
    keys = "C correct   U undo   M miss   R darts out   V cameras   Q quit"
    text(out, keys, (pad, yb), fit_size(keys, FONT, 1, left_w - 2 * pad, 0.55 * u), DIM, 1)
    text(out, status[:60], (pad, yb - int(34 * u)), fit_size(status[:60], FONT, 1, left_w - 2 * pad, 0.75 * u),
         ACCENT, 1)
    if note:
        text(out, note, (pad, yb - int(66 * u)), 0.55 * u, GOOD, 1)

    # ---- right side
    rw = W - right_x - pad
    top, bottom = pad, H - pad
    if show_cams and frames:
        cam_h = min(int(rw * 9 / 16), (H - 2 * pad) // 2)
        cw = int(cam_h * 16 / 9)
        grid = camera_grid(frames, names, overlays, cw, cam_h)
        out[bottom - cam_h:bottom, right_x + (rw - cw) // 2:right_x + (rw - cw) // 2 + cw] = grid
        bottom -= cam_h + pad
    rows = game.table()
    if rows:
        th = min(bottom - top, int((bottom - top) * 0.55))
        _draw_table(out, rows, game, right_x, top, rw, th, u)
        top += th + pad
    bsize = max(120, min(rw, bottom - top))
    out[top:top + bsize, right_x + (rw - bsize) // 2:right_x + (rw - bsize) // 2 + bsize] = board_view(bsize, marks)
    return out, hits


def _draw_table(out, rows, game, x, y, w, h, u):
    """Cricket-style grid: number in the middle column, each player's marks either side."""
    n = len(game.players)
    rh = h // (len(rows) + 1)
    colw = w // (n + 1)
    for i, pl in enumerate(game.players):
        cx = x + colw * (i + (1 if i >= (n + 1) // 2 else 0)) + colw // 2
        text(out, pl[:8], (cx, y + int(rh * 0.7)), fit_size(pl[:8], BOLD, 1, colw - 8, 0.7 * u),
             ACCENT if i == game.cur else GREY, 1, BOLD, "c")
    mid = x + colw * ((n + 1) // 2) + colw // 2
    for r, (lab, marks, closed) in enumerate(rows):
        yy = y + rh * (r + 1)
        box(out, (x, yy + 2), (x + w, yy + rh - 2), PANEL, int(6 * u))
        text(out, lab, (mid, yy + int(rh * 0.72)), min(1.0 * u, rh / 40), DIM if closed else WHITE, 2, BOLD, "c")
        for i, m in enumerate(marks):
            cx = x + colw * (i + (1 if i >= (n + 1) // 2 else 0)) + colw // 2
            cy = yy + rh // 2
            r0 = max(4, int(rh * 0.3))
            col = GOOD if m >= 3 else WHITE
            if m >= 1:
                cv2.line(out, (cx - r0, cy + r0), (cx + r0, cy - r0), col, max(1, int(3 * u)), cv2.LINE_AA)
            if m >= 2:
                cv2.line(out, (cx - r0, cy - r0), (cx + r0, cy + r0), col, max(1, int(3 * u)), cv2.LINE_AA)
            if m >= 3:
                cv2.circle(out, (cx, cy), r0 + int(4 * u), col, max(1, int(3 * u)), cv2.LINE_AA)


def draw_banner(out, title, lines):
    """Big centred message (leg / match won)."""
    H, W = out.shape[:2]
    u = H / 900.0
    bw, bh = int(W * 0.6), int((120 + 44 * len(lines)) * u)
    x0, y0 = (W - bw) // 2, (H - bh) // 2
    over = out.copy()
    cv2.rectangle(over, (0, 0), (W, H), (0, 0, 0), -1)
    cv2.addWeighted(over, 0.45, out, 0.55, 0, out)
    box(out, (x0, y0), (x0 + bw, y0 + bh), CARD, int(18 * u))
    box(out, (x0, y0), (x0 + bw, y0 + int(8 * u)), GOOD, int(4 * u))
    text(out, title, (W // 2, y0 + int(80 * u)), fit_size(title, BOLD, 3, bw - 40, 1.8 * u), WHITE, 3, BOLD, "c")
    for i, l in enumerate(lines):
        text(out, l, (W // 2, y0 + int((130 + 44 * i) * u)), fit_size(l, FONT, 1, bw - 40, 0.8 * u), GREY, 1,
             FONT, "c")


def draw_flash(out, t, title="180"):
    """Flashing celebration over the game screen (a 180). t = seconds since it started."""
    H, W = out.shape[:2]
    u = H / 900.0
    on = int(t / 0.2) % 2 == 0
    col = ACCENT if on else BAD
    if on:
        over = out.copy()
        cv2.rectangle(over, (0, 0), (W, H), col, -1)
        cv2.addWeighted(over, 0.25, out, 0.75, 0, out)
    th = max(8, int(28 * u))
    cv2.rectangle(out, (th // 2, th // 2), (W - th // 2, H - th // 2), col, th)
    text(out, title, (W // 2, H // 2 + int(90 * u)), fit_size(title, BOLD, 12, W * 0.6, 9 * u), col,
         max(6, int(14 * u)), BOLD, "c")


def draw_menu(W, H, modes, sel_row, mode_i, opts, players, typing):
    """Start screen: pick a game, options and players with the keyboard."""
    out = np.full((H, W, 3), BG, np.uint8)
    hits = {}
    u = H / 900.0
    pad = int(40 * u)
    text(out, "dartvision", (pad, int(80 * u)), 1.6 * u, WHITE, 3, BOLD)
    help_ = ("Up/Down choose   Left/Right change   type a name + Enter to add a player   "
             "Backspace remove   Enter start   Esc quit   (or click)")
    text(out, help_, (pad, H - pad), fit_size(help_, FONT, 1, W - 2 * pad, 0.55 * u), DIM, 1)
    x_mid = W // 2
    # left: game list
    y = int(140 * u)
    text(out, "Game", (pad, y), 0.8 * u, GREY, 1)
    y += int(20 * u)
    rh = int(64 * u)
    for i, (name, _) in enumerate(modes):
        on = i == mode_i
        box(out, (pad, y), (x_mid - pad, y + rh - int(10 * u)), CARD if on else PANEL, int(12 * u))
        if on:
            box(out, (pad, y), (pad + int(8 * u), y + rh - int(10 * u)), ACTIVE if sel_row == 0 else GREY, int(4 * u))
        text(out, name, (pad + int(28 * u), y + int(rh * 0.55)), 0.9 * u, WHITE if on else GREY, 2, BOLD)
        hits[f"mode{i}"] = (pad, y, x_mid - pad, y + rh - int(10 * u))
        y += rh
    # left, under the games: try the 180 celebration (light, screen, phone, voice)
    y += int(30 * u)
    text(out, "Light", (pad, y), 0.8 * u, GREY, 1)
    y += int(20 * u)
    box(out, (pad, y), (x_mid - pad, y + rh - int(10 * u)), PANEL, int(12 * u))
    text(out, "Test 180 flash", (pad + int(28 * u), y + int(rh * 0.55)), 0.9 * u, ACCENT, 2, BOLD)
    hits["test_flash"] = (pad, y, x_mid - pad, y + rh - int(10 * u))
    # right: options + players
    x = x_mid + pad
    y = int(140 * u)
    text(out, "Options", (x, y), 0.8 * u, GREY, 1)
    y += int(20 * u)
    for r, (label, value) in enumerate(opts, start=1):
        on = sel_row == r
        box(out, (x, y), (W - pad, y + rh - int(10 * u)), CARD if on else PANEL, int(12 * u))
        text(out, label, (x + int(24 * u), y + int(rh * 0.55)), 0.75 * u, WHITE if on else GREY, 1)
        text(out, f"<  {value}  >" if on else value, (W - pad - int(24 * u), y + int(rh * 0.55)), 0.85 * u,
             ACCENT if on else WHITE, 2, BOLD, "r")
        hits[f"opt{r}"] = (x, y, W - pad, y + rh - int(10 * u))
        y += rh
    y += int(30 * u)
    text(out, "Players", (x, y), 0.8 * u, GREY, 1)
    y += int(20 * u)
    for i, p in enumerate(players):
        box(out, (x, y), (W - pad, y + rh - int(10 * u)), PANEL, int(12 * u))
        text(out, p, (x + int(24 * u), y + int(rh * 0.55)), 0.9 * u, WHITE, 2, BOLD)
        text(out, "x", (W - pad - int(24 * u), y + int(rh * 0.55)), 0.8 * u, DIM, 2, BOLD, "r")
        hits[f"del{i}"] = (W - pad - int(60 * u), y, W - pad, y + rh - int(10 * u))
        y += rh
    if len(players) < 6:
        on = sel_row == len(opts) + 1
        box(out, (x, y), (W - pad, y + rh - int(10 * u)), CARD if on else PANEL, int(12 * u))
        caret = "_" if on and int(cv2.getTickCount() / cv2.getTickFrequency() * 2) % 2 else ""
        t = typing + caret if (typing or on) else "+ add player"
        text(out, t, (x + int(24 * u), y + int(rh * 0.55)), 0.9 * u, ACCENT if on else DIM, 2, BOLD)
        hits["add"] = (x, y, W - pad, y + rh - int(10 * u))
        y += rh
    # start button
    y = max(y + int(20 * u), H - pad - int(110 * u))
    ok = bool(players)
    box(out, (x, y), (W - pad, y + int(70 * u)), GOOD if ok else PANEL, int(14 * u))
    text(out, "Start  (Enter)" if ok else "add a player to start", ((x + W - pad) // 2, y + int(47 * u)),
         1.0 * u, (20, 20, 20) if ok else DIM, 2, BOLD, "c")
    hits["start"] = (x, y, W - pad, y + int(70 * u))
    return out, hits


# ---------------------------------------------------------------- log
LEVEL_COLS = {"info": GREY, "warn": ACCENT, "error": BAD}


def info_bar_height(H):
    return max(22, int(34 * H / 900.0))


def draw_info_bar(W, h, entry, panel_open=False, now=None):
    """Strip for the bottom of the window: the newest log line (errors stay red for a minute).
    Click it or press Tab for the full log."""
    import time as _t
    out = np.full((h, W, 3), (16, 15, 14), np.uint8)
    cv2.line(out, (0, 0), (W, 0), (60, 56, 52), 1)
    u = h / 34.0
    hint = "Tab: hide log" if panel_open else "Tab / click: log"
    hw = text(out, hint, (W - int(12 * u), int(h * 0.68)), 0.45 * u, DIM, 1, FONT, "r")
    if entry:
        t, lv, s = entry
        age = (now or _t.time()) - t
        col = LEVEL_COLS[lv] if (lv == "info" or age < 60) else DIM
        line = _t.strftime("%H:%M:%S ", _t.localtime(t)) + s
        max_w = W - hw - int(36 * u)
        size = 0.5 * u
        while len(line) > 4 and cv2.getTextSize(line, FONT, size, 1)[0][0] > max_w:
            line = line[:-2]
        text(out, line, (int(12 * u), int(h * 0.68)), size, col, 1)
    return out


def draw_log_panel(out, entries, bottom=None):
    """The last lines of the log over the lower part of the screen (newest at the bottom)."""
    import time as _t
    H, W = out.shape[:2]
    bottom = bottom or H
    u = H / 900.0
    lh = max(14, int(24 * u))
    ph = min(bottom - int(60 * u), int(H * 0.55))
    y0 = bottom - ph
    over = out.copy()
    cv2.rectangle(over, (0, y0), (W, bottom), (12, 11, 10), -1)
    cv2.addWeighted(over, 0.92, out, 0.08, 0, out)
    cv2.line(out, (0, y0), (W, y0), ACCENT, max(1, int(2 * u)))
    text(out, "Log  (also in the terminal)", (int(16 * u), y0 + int(26 * u)), 0.55 * u, GREY, 1)
    n = max(1, (ph - int(44 * u)) // lh)
    y = y0 + int(44 * u) + lh
    for t, lv, s in entries[-n:]:
        line = _t.strftime("%H:%M:%S  ", _t.localtime(t)) + s
        text(out, line[:180], (int(16 * u), y), 0.48 * u, WHITE if lv == "info" else LEVEL_COLS[lv], 1)
        y += lh
    return out
