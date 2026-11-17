"""dartvision – DIY automatic dart scoring.

    python -m dartvision setup        find cameras, write config.yaml
    python -m dartvision preview      live view of all cameras (+ board overlay)
    python -m dartvision calibrate    click-calibrate each camera
    python -m dartvision play         play 501 with auto scoring (records every throw)
    python -m dartvision label DIR    go through a recorded session, type the true score
    python -m dartvision replay DIR   re-run detection on a session, report accuracy
    python -m dartvision update       check GitHub for a new version and install it
"""
import argparse
import math
import os
import sys
import time

import cv2
import numpy as np

from . import board
from .config import load_config, save_config, load_calibration

TILE_W, TILE_H = 640, 360
UPDATE = {}   # filled in by the background update check
GREEN, YELLOW, RED, WHITE, GREY = (0, 220, 0), (0, 255, 255), (0, 0, 255), (255, 255, 255), (150, 150, 150)


# ------------------------------------------------------------------ helpers
def tile(frames, overlays=None, labels=None):
    imgs = []
    for i, f in enumerate(frames):
        t = cv2.resize(f, (TILE_W, TILE_H))
        if overlays and overlays[i] is not None:
            overlays[i](t, TILE_W / f.shape[1], TILE_H / f.shape[0])
        if labels:
            cv2.putText(t, labels[i], (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, YELLOW, 2, cv2.LINE_AA)
        imgs.append(t)
    while len(imgs) % 2:
        imgs.append(np.zeros_like(imgs[0]))
    rows = [np.hstack(imgs[i:i + 2]) for i in range(0, len(imgs), 2)]
    return np.vstack(rows)


def scaled_H(H, sx, sy):
    return np.diag([sx, sy, 1.0]) @ H


def grab(cams):
    return {c.name: c.read() for c in cams}


# ------------------------------------------------------------------ commands
def cmd_setup(args):
    from .cameras import list_cameras
    from . import devices
    print("Looking for cameras ...")
    found = list_cameras(args.max_index)
    if not found:
        print("No cameras found. Check USB connections (and on macOS, camera permission for your terminal).")
        return
    devs = devices.list_devices()
    skip = set(args.skip or [])
    cams = []
    for f in found:
        d = devices.describe(f["index"], devs) or {}
        name = d.get("name") or "?"
        note = ""
        if f["index"] in skip:
            note = "  - skipped (--skip)"
        elif d.get("builtin") and not args.keep_builtin:
            note = "  - skipped: the computer's own camera"
        print(f"  index {f['index']}: {f['width']}x{f['height']}  {name}{note}")
        if note:
            continue
        cam = {"name": f"cam{len(cams) + 1}", "index": f["index"], "rotate": 0}
        if d.get("id"):
            cam["id"] = d["id"]          # stable: tied to the USB port, survives renumbering
            cam["model"] = name
        cams.append(cam)
    if found and not devs:
        print("(camera names and port ids aren't available here - cameras are kept by number only)")
    cfg = load_config(args.config)
    cfg["cameras"] = cams
    save_config(cfg, args.config)
    print(f"\nWrote {args.config} with {len(cams)} camera(s).")
    print("Next: python -m dartvision preview")


def cmd_preview(args):
    from .cameras import open_cameras
    cfg = load_config(args.config)
    cams = open_cameras(cfg, config_path=args.config)
    cals = {c.name: load_calibration(c.name) for c in cams}
    cv2.namedWindow("dartvision preview", cv2.WINDOW_NORMAL)
    show = True
    t0, n = time.time(), 0
    rate = {c.name: (time.time(), c.count, 0.0) for c in cams}   # real frames per second from each camera
    while True:
        frames = grab(cams)
        ovs = []
        for c in cams:
            cal = cals[c.name]
            ovs.append((lambda img, sx, sy, cal=cal: board.draw_board_overlay(img, scaled_H(cal["H"], sx, sy), GREEN, 1, False))
                       if (show and cal) else None)
        n += 1
        now = time.time()
        for c in cams:
            t, k, r = rate[c.name]
            if now - t >= 1.0:
                rate[c.name] = (now, c.count, (c.count - k) / (now - t))
        def label(c):
            s = f"{c.name} (index {c.index})  {c.size[0]}x{c.size[1]}  {rate[c.name][2]:.0f} fps"
            if c.stalled:
                s += "  NO PICTURE - reconnecting"
            elif c.reconnects:
                s += f"  (reconnected {c.reconnects}x)"
            return s
        labels = [label(c) for c in cams]
        view = tile([frames[c.name] for c in cams], ovs, labels)
        cv2.putText(view, "G toggle overlay   Q quit", (8, view.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, WHITE, 1)
        from . import ui
        cv2.imshow("dartvision preview", ui.fit(view, *ui.window_size("dartvision preview", (view.shape[1], view.shape[0]))))
        k = cv2.waitKey(1) & 0xFF
        if k in (ord("q"), 27):
            break
        if k == ord("g"):
            show = not show
    for c in cams:
        c.close()
    cv2.destroyAllWindows()


def cmd_calibrate(args):
    from .cameras import open_cameras
    from .calibrate import calibrate_camera
    cfg = load_config(args.config)
    cams = open_cameras(cfg, only=args.camera, config_path=args.config)
    print("For each camera click: 1) the bull centre, then where the wire meets the OUTER edge of")
    print("the double ring 2) between 20 and 1, 3) between 6 and 10, 4) between 3 and 19, 5) between 11 and 14.")
    print("Use F to freeze the picture, drag points to fine tune, S to save and go to the next camera (N skips one).")
    try:
        for c in cams:
            r = calibrate_camera(c)
            if r["quit"]:
                break
    finally:
        for c in cams:
            c.close()


def _draw_scoreboard(game, last_events, status, w=420, h=720):
    from .game import checkout_hint
    p = np.full((h, w, 3), 25, np.uint8)
    y = 40
    cv2.putText(p, f"{game.start}  double out", (16, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, GREY, 1, cv2.LINE_AA)
    y += 30
    for i, pl in enumerate(game.players):
        active = i == game.cur
        col = YELLOW if active else WHITE
        cv2.putText(p, ("> " if active else "  ") + pl, (16, y + 36), cv2.FONT_HERSHEY_SIMPLEX, 0.9, col, 2, cv2.LINE_AA)
        cv2.putText(p, str(game.scores[pl]), (230, y + 40), cv2.FONT_HERSHEY_SIMPLEX, 1.6, col, 3, cv2.LINE_AA)
        cv2.putText(p, f"avg {game.three_dart_avg(pl):.1f}", (36, y + 62), cv2.FONT_HERSHEY_SIMPLEX, 0.5, GREY, 1)
        y += 80
    y += 10
    cv2.putText(p, "This turn:", (16, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, GREY, 1, cv2.LINE_AA)
    for j in range(3):
        lab = game.turn[j][0] if j < len(game.turn) else "-"
        cv2.putText(p, lab, (16 + j * 130, y + 45), cv2.FONT_HERSHEY_SIMPLEX, 1.2, WHITE, 2, cv2.LINE_AA)
    y += 70
    total = sum(pt for _, pt in game.turn)
    cv2.putText(p, f"= {total}", (16, y), cv2.FONT_HERSHEY_SIMPLEX, 1.0, WHITE, 2, cv2.LINE_AA)
    if game.bust:
        cv2.putText(p, "BUST - pull darts", (130, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, RED, 2, cv2.LINE_AA)
    hint = checkout_hint(game.scores[game.player])
    if hint and not game.bust:
        cv2.putText(p, f"checkout: {hint}", (16, y + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, GREEN, 2, cv2.LINE_AA)
    if game.winner:
        cv2.putText(p, f"{game.winner} WINS!", (16, y + 90), cv2.FONT_HERSHEY_SIMPLEX, 1.4, GREEN, 3, cv2.LINE_AA)
    y = h - 170
    if UPDATE.get("latest"):
        cv2.putText(p, f"Update {UPDATE['latest']} available (installs on quit)", (16, y - 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, GREEN, 1, cv2.LINE_AA)
    cv2.putText(p, status[:40], (16, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, YELLOW, 1, cv2.LINE_AA)
    keys = ["C correct last dart", "U undo last dart   M add miss",
            "N next player   R darts out / reset", "Q quit"]
    for i, t in enumerate(keys):
        cv2.putText(p, t, (16, y + 30 + 24 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.5, GREY, 1, cv2.LINE_AA)
    return p


def cmd_play(args):
    from .cameras import open_cameras
    from .detect import ThrowTracker
    from .game import X01
    from .recorder import Recorder, set_label, accept_if_unlabelled
    from .board import parse_score
    cfg = load_config(args.config)
    cams = open_cameras(cfg, config_path=args.config)
    cals = {c.name: load_calibration(c.name) for c in cams}
    missing = [n for n, c in cals.items() if c is None]
    if missing:
        print("Not calibrated yet:", ", ".join(missing), "- run  python -m dartvision calibrate")
        cals = {n: c for n, c in cals.items() if c}
        if not cals:
            return
    frames = grab(cams)
    tracker = ThrowTracker(cals, cfg["detection"], {n: f.shape for n, f in frames.items()})
    tracker.reset(frames)
    rec = None if args.no_record else Recorder(cfg["record_dir"])
    game = X01(args.players, start=args.start)
    last = {}
    status = "Ready - throw!"
    turn_recs = []          # recording folder for each dart in the current turn (None = typed in)
    pending_unknown = None  # recording of a throw we couldn't read, waiting for C
    entry = None            # text being typed into the on-screen box (None = box closed)
    marks = []              # (x, y, label) of this turn's darts, for the board picture
    from . import ui
    from .game import checkout_hint
    cv2.namedWindow("dartvision", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("dartvision", 1600, 900)
    entry_title = ""

    def apply_entry(txt):
        nonlocal pending_unknown, status
        try:
            lab, pts = parse_score(txt)
        except Exception as e:  # noqa
            status = f"didn't understand '{txt}' ({e})"
            return
        if pending_unknown:                       # a throw we couldn't read
            game.add_dart(lab, pts); turn_recs.append(pending_unknown)
            set_label(pending_unknown, lab, "entered"); pending_unknown = None
        else:
            game.correct_last(lab, pts)
            if turn_recs and turn_recs[-1]:
                set_label(turn_recs[-1], lab, "corrected")
            if marks:
                marks[-1] = (marks[-1][0], marks[-1][1], lab)
        status = f"corrected to {lab}"
        print(f"[{game.player}] {status}")

    def end_turn():
        nonlocal turn_recs
        for d in turn_recs:
            if d:
                accept_if_unlabelled(d)      # not corrected = it was right
        turn_recs = []

    print(f"Game on: {', '.join(args.players)}  ({args.start})" + (f"   recording to {rec.dir}" if rec else ""))
    while True:
        frames = grab(cams)
        ev = tracker.update(frames)
        if ev:
            saved = rec.save(ev["before_raw"], frames, ev) if rec and ev["type"] in ("DART", "UNKNOWN") else None
            if ev["type"] == "DART":
                res = game.add_dart(ev["label"], ev["points"])
                status = f"{ev['label']} ({ev['points']})  from {ev['cams_used']} cam(s)"
                if res == "bust":
                    status += "  BUST"
                if res == "turn_full":
                    status = f"extra dart seen ({ev['label']}) - ignored"
                else:
                    turn_recs.append(saved)
                    marks.append((ev["pos_mm"][0], ev["pos_mm"][1], ev["label"]))
                last = {n: r for n, r in ev["cams"].items() if r.get("ok")}
                print(f"[{game.player}] {status}")
            elif ev["type"] == "TAKEOUT":
                end_turn()
                if game.turn or game.bust:
                    game.next_player()
                status = f"darts pulled - {game.player} to throw"
                last = {}
                marks = []
                print(status)
            elif ev["type"] == "UNKNOWN":
                pending_unknown = saved
                status = "couldn't read that one - type it in the box"
                print(status, {n: r.get("reason") for n, r in ev.get("cams", {}).items()})
                if entry is None:
                    entry, entry_title = "", "Couldn't read that dart - what was it?"
        ovs = []
        for c in cams:
            cal = cals.get(c.name)

            def ov(img, sx, sy, cal=cal, name=c.name):
                if cal is None:
                    return
                board.draw_board_overlay(img, scaled_H(cal["H"], sx, sy), (0, 120, 0), 1, False)
                r = last.get(name)
                if r:
                    x, y = r["tip_px"]
                    cv2.circle(img, (int(x * sx), int(y * sy)), 6, RED, 2, cv2.LINE_AA)
            ovs.append(ov)
        W, H = ui.window_size("dartvision")
        note = f"Update {UPDATE['latest']} available (installs on quit)" if UPDATE.get("latest") else None
        hint = checkout_hint(game.scores[game.player]) if not game.bust else None
        out = ui.draw_play(W, H, game, [frames[c.name] for c in cams], [c.name for c in cams], ovs,
                           status, marks, hint, note)
        if entry is not None:
            _draw_entry_box(out, entry_title, entry)
        cv2.imshow("dartvision", out)
        k = cv2.waitKey(1) & 0xFF
        if entry is not None:                     # typing into the box: keys are text, not commands
            if k in (13, 10):                     # Enter
                if entry.strip():
                    apply_entry(entry)
                entry = None
            elif k == 27:                         # Esc
                entry = None; status = "cancelled"
            elif k in (8, 127):                   # Backspace
                entry = entry[:-1]
            elif k != 255 and chr(k).isalnum() and len(entry) < 8:
                entry += chr(k).upper()
            continue
        if k in (ord("q"), 27):
            end_turn()
            break
        if k == ord("u"):
            if turn_recs:
                d = turn_recs.pop()
                if d:
                    set_label(d, "FALSE", "undone")      # remember it as a false detection
            game.undo(); status = "undid last dart"
            if marks:
                marks.pop()
        if k == ord("m"):
            game.add_dart("MISS", 0); turn_recs.append(None); status = "miss added"
        if k == ord("n"):
            end_turn()
            game.next_player(); tracker.reset(grab(cams)); status = f"{game.player} to throw"
            marks = []
        if k == ord("r"):                         # darts are out but it didn't notice: end the turn
            end_turn()
            if game.turn or game.bust:
                game.next_player()
            tracker.reset(grab(cams)); marks = []; last = {}
            status = f"reset - {game.player} to throw"
        if k == ord("c"):
            entry, entry_title = "", "Correct the last dart to:"
    for c in cams:
        c.close()
    cv2.destroyAllWindows()
    offer_update(cfg)


def _draw_entry_box(img, title, text):
    """On-screen text box for typing a score (no need to switch to the terminal)."""
    h, w = img.shape[:2]
    bw, bh = 560, 190
    x0, y0 = (w - bw) // 2, (h - bh) // 2
    over = img.copy()
    cv2.rectangle(over, (x0, y0), (x0 + bw, y0 + bh), (25, 25, 25), -1)
    cv2.addWeighted(over, 0.9, img, 0.1, 0, img)
    cv2.rectangle(img, (x0, y0), (x0 + bw, y0 + bh), (0, 200, 255), 2)
    cv2.putText(img, title, (x0 + 20, y0 + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.75, WHITE, 2, cv2.LINE_AA)
    cv2.rectangle(img, (x0 + 20, y0 + 62), (x0 + bw - 20, y0 + 122), (60, 60, 60), -1)
    caret = "_" if int(time.time() * 2) % 2 else " "
    cv2.putText(img, text + caret, (x0 + 32, y0 + 108), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 230, 255), 3, cv2.LINE_AA)
    cv2.putText(img, "e.g. T20  D16  5  SB  DB  MISS     Enter = save   Esc = cancel",
                (x0 + 20, y0 + 160), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (190, 190, 190), 1, cv2.LINE_AA)


def offer_update(cfg):
    if not UPDATE.get("latest"):
        return
    from . import update
    print(f"\nA new version is available: {UPDATE['latest']}  ({UPDATE.get('url')})")
    if UPDATE.get("notes"):
        print(UPDATE["notes"][:800])
    if input("Install it now? [y/N] ").strip().lower() == "y":
        update.apply(UPDATE)


def cmd_update(args):
    from . import update, __version__
    cfg = load_config(args.config)
    info = update.check(cfg["update"]["repo"])
    if info.get("error"):
        print("Couldn't check for updates:", info["error"]); return
    print(f"Installed: v{__version__}   Latest: {info['latest']}")
    if not info["newer"]:
        print("You're up to date."); return
    if info.get("notes"):
        print(info["notes"][:1500])
    if args.yes or input("Install now? [y/N] ").strip().lower() == "y":
        update.apply(info)


def cmd_label(args):
    from .recorder import iter_throws, set_label
    from .board import parse_score
    for d, meta, before, after in iter_throws(args.session):
        if "true_label" in meta and not args.all:
            continue
        imgs, labs = [], []
        for name, img in after.items():
            v = img.copy()
            r = meta.get("cams", {}).get(name, {})
            if r.get("ok"):
                cv2.circle(v, tuple(int(a) for a in r["tip_px"]), 10, RED, 2)
            imgs.append(v); labs.append(name)
        cv2.imshow("label", tile(imgs, labels=labs))
        cv2.waitKey(50)
        guess = meta.get("label", "?")
        txt = input(f"{os.path.basename(d)}: detected {guess}. True score (Enter = correct, q = stop): ").strip()
        if txt.lower() == "q":
            break
        lab = guess if txt == "" else parse_score(txt)[0]
        set_label(d, lab, "manual")
    cv2.destroyAllWindows()


def cmd_replay(args):
    from .recorder import iter_throws
    from .detect import find_dart_tip, fuse_darts, prep, ThrowTracker
    cfg = load_config(args.config)
    det = cfg["detection"]
    calib_dir = os.path.join(args.session, "calib")
    n = right = false_pos = 0
    by_src = {}
    for d, meta, before, after in iter_throws(args.session):
        cals = {c: load_calibration(c, calib_dir) for c in after}
        cals = {c: v for c, v in cals.items() if v}
        tr = ThrowTracker(cals, det, {c: f.shape for c, f in after.items()})
        pts = []
        for c in cals:
            pts.append(find_dart_tip(prep(before[c]), prep(after[c]), cals[c]["H_inv"], tr.roi[c], det))
        f = fuse_darts(pts, det["fuse_tolerance_mm"])
        lab = board.score_at(f[0], f[1])[0] if f else "?"
        truth = meta.get("true_label")
        src = meta.get("label_source", "")
        if truth == "FALSE":
            false_pos += 1
            print(f"-- {os.path.basename(d)}: {lab:5s}  (false detection, undone in game)")
            continue
        ok = "" if truth is None else ("OK " if truth == lab else "XX ")
        if truth is not None:
            n += 1; right += truth == lab
            by_src[src] = by_src.get(src, 0) + 1
        print(f"{ok}{os.path.basename(d)}: {lab:5s}" + (f"  (true {truth}, {src})" if truth else ""))
    if n:
        print(f"\nAccuracy on labelled throws: {right}/{n} = {100 * right / n:.1f}%")
        print("labels:", ", ".join(f"{k or 'manual'} {v}" for k, v in by_src.items()),
              f"| false detections: {false_pos}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dartvision", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="config.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup"); s.add_argument("--max-index", type=int, default=8)
    s.add_argument("--skip", type=int, nargs="*", help="camera indexes to leave out (e.g. laptop webcam)")
    s.add_argument("--keep-builtin", action="store_true", help="keep the computer's own camera too")
    sub.add_parser("preview")
    s = sub.add_parser("calibrate"); s.add_argument("--camera", help="only this camera name")
    s = sub.add_parser("play"); s.add_argument("players", nargs="*", default=["Player 1"])
    s.add_argument("--start", type=int, default=501); s.add_argument("--no-record", action="store_true")
    s = sub.add_parser("label"); s.add_argument("session"); s.add_argument("--all", action="store_true")
    s = sub.add_parser("replay"); s.add_argument("session")
    s = sub.add_parser("update"); s.add_argument("-y", "--yes", action="store_true")
    sub.add_parser("version")
    args = ap.parse_args(argv)
    from . import __version__
    if args.cmd == "version":
        print(f"dartvision v{__version__}"); return
    cfg = load_config(args.config)
    if args.cmd in ("play", "preview", "calibrate") and cfg["update"]["check_on_start"] and cfg["update"]["repo"]:
        from .update import check_in_background

        def found(info):
            UPDATE.update(info)
            print(f"** Update available: {info['latest']} - run  python -m dartvision update **")
        check_in_background(cfg["update"]["repo"], found)
    {"setup": cmd_setup, "preview": cmd_preview, "calibrate": cmd_calibrate, "play": cmd_play,
     "label": cmd_label, "replay": cmd_replay, "update": cmd_update}[args.cmd](args)


if __name__ == "__main__":
    main()
