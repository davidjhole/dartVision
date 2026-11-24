"""dartvision – DIY automatic dart scoring.

    python -m dartvision setup        find cameras, write config.yaml
    python -m dartvision preview      live view of all cameras (+ board overlay)
    python -m dartvision calibrate    click-calibrate each camera (on the phone / PC page if no screen)
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

from . import board, logbuf
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


def _no_screen():
    return sys.platform.startswith("linux") and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def cmd_calibrate(args):
    from .cameras import open_cameras
    from .calibrate import calibrate_camera
    cfg = load_config(args.config)
    cams = open_cameras(cfg, only=args.camera, config_path=args.config)
    if args.web or _no_screen():
        return _calibrate_web(cams, args.port)
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


def _calibrate_web(cams, port):
    """Calibrate from a phone / PC browser: no window needed on this computer (Pi with no screen)."""
    from . import web
    from .calibrate import WebCalibrator
    url = web.start(port)
    if not url:
        return
    web.set_calibrator(WebCalibrator(cams))
    print(f"\nCalibrate from a phone or PC on the same Wi-Fi: open  {url}")
    print("Tap the 5 points on each camera's picture and Save. Ctrl+C here when you're done.\n")
    try:
        while True:
            for a in web.take_actions():
                if a.get("type") == "calibrated":
                    done = [c.name for c in cams if load_calibration(c.name)]
                    left = [c.name for c in cams if c.name not in done]
                    print(f"{a.get('cam')} calibrated" + (f" - still to do: {', '.join(left)}" if left
                                else " - all cameras done. Ctrl+C, then  python -m dartvision play"))
            web.publish({"screen": "calibrate", "log": logbuf.for_web()})
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        for c in cams:
            c.close()


# arrow keys as cv2.waitKeyEx reports them (macOS, Linux, Windows)
_ARROWS = {63232: "up", 63233: "down", 63234: "left", 63235: "right",
           65362: "up", 65364: "down", 65361: "left", 65363: "right",
           2490368: "up", 2621440: "down", 2424832: "left", 2555904: "right",
           0: "up", 1: "down", 2: "left", 3: "right"}


def _key(k):
    """Name of a key from cv2.waitKeyEx: 'up', 'enter', 'esc', 'back', a single character, or None."""
    if k == -1:
        return None
    if k in _ARROWS and k > 3:
        return _ARROWS[k]
    c = k & 0xFF
    if c in (13, 10):
        return "enter"
    if c == 27:
        return "esc"
    if c in (8, 127):
        return "back"
    if c == 9:
        return "tab"
    if k in (0, 1, 2, 3):
        return _ARROWS[k]
    return chr(c) if 32 <= c < 127 else None


def _hit(hits, pos):
    if pos is None:
        return None
    for name, (x0, y0, x1, y1) in hits.items():
        if x0 <= pos[0] <= x1 and y0 <= pos[1] <= y1:
            return name
    return None


def cmd_play(args):
    import json
    from .cameras import open_cameras
    from .detect import ThrowTracker
    from .games import MODES
    from .menu import Menu
    from .recorder import Recorder, set_label, accept_if_unlabelled
    from .board import parse_score
    from . import ui
    from .caller import TurnWatcher, Speaker, phrase
    from .lights import Lights
    cfg = load_config(args.config)
    cams = open_cameras(cfg, config_path=args.config)
    cals = {c.name: load_calibration(c.name) for c in cams}
    missing = [n for n, c in cals.items() if c is None]
    if missing:
        print("Not calibrated yet:", ", ".join(missing), "- calibrate from the phone page (Calibrate cameras"
              " in the menu) or run  python -m dartvision calibrate")
        cals = {n: c for n, c in cals.items() if c}
        if not cals and args.no_web:
            return
    frames = grab(cams)
    tracker = ThrowTracker(cals, cfg["detection"], {n: f.shape for n, f in frames.items()})
    tracker.reset(frames)
    rec = None if args.no_record else Recorder(cfg["record_dir"])
    results_path = os.path.join(cfg["record_dir"], "results.jsonl")

    WIN = "dartvision"
    if _no_screen():
        args.headless = True                  # no screen attached (e.g. a Pi on its own)
    if not args.headless:
        cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WIN, 1600, 900)
    click = {"pos": None}

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            click["pos"] = (x, y)
    if not args.headless:
        cv2.setMouseCallback(WIN, on_mouse)

    # ---- menu state
    screen = "menu"
    menu = Menu(args.players, args.start, MODES)
    players = menu.players          # the same list: the menu changes it in place
    sel_row, typing = 0, ""

    # ---- game state
    game = None
    last, marks, turn_recs = {}, [], []
    status, pending_unknown = "", None
    entry, entry_title, entry_target = None, "", None
    show_cams = False
    show_log = False
    started = ""

    # ---- caller (voice) and 180 flash
    vcfg = cfg["voice"]
    watcher = TurnWatcher()
    speaker = Speaker(vcfg["engine"] if vcfg["enabled"] else "off")
    vout = str(vcfg.get("output", "auto")).lower()
    if vcfg["enabled"] and vout in ("auto", "computer", "both") and not speaker.available:
        print("voice: no speech program found on this computer"
              + (" (install one: sudo apt install espeak-ng)" if sys.platform.startswith("linux") else "")
              + " - the phone / TV page can still speak")
    lights = Lights(cfg["lights"])
    calls, call_n, flash_at = [], 0, 0.0

    def announce(text, flash=False):
        """Say one call (computer and / or phone page) and flash the screen, page and light for a 180."""
        nonlocal call_n, flash_at
        if flash:
            flash_at = time.time()
            lights.flash()
        call_n += 1
        calls.append({"n": call_n, "text": text, "flash": bool(flash)})
        del calls[:-5]
        if text and (vout in ("computer", "both") or (vout == "auto" and not (url and web.voice_listening()))):
            speaker.say(text)

    def run_caller():
        for ev in watcher.observe(game if screen == "play" else None):
            if not vcfg["enabled"] or (ev["kind"] == "require" and not vcfg.get("require", True)):
                text = ""
            else:
                text = phrase(ev)
            announce(text, ev.get("flash"))

    def test_flash():
        """The 'Test 180 flash' button: the whole 180 celebration, without throwing one."""
        if lights.enabled:
            print("testing the 180 flash (light, screen and phone)")
        else:
            print("testing the 180 flash - no light set up (lights: in config.yaml), so screen and phone only")
        announce("One hundred and eighty!" if vcfg["enabled"] else "", True)

    def log_result(kind, extra=None):
        try:
            os.makedirs(cfg["record_dir"], exist_ok=True)
            row = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": kind, "started": started,
                   "mode": getattr(game, "mode_title", game.name), **game.summary(), **(extra or {})}
            with open(results_path, "a") as f:
                f.write(json.dumps(row) + "\n")
        except Exception as e:  # noqa
            print("couldn't save the result:", e)

    def start_game():
        nonlocal game, screen, status, marks, turn_recs, last, started
        game = menu.new_game()
        screen, status, marks, turn_recs, last = "play", f"{game.player} to throw", [], [], {}
        started = time.strftime("%Y-%m-%d %H:%M:%S")
        tracker.reset(grab(cams))
        print(f"Game on: {getattr(game, 'mode_title', game.name)} - {', '.join(players)}"
              + (f"   recording to {rec.dir}" if rec else ""))

    def end_turn():
        nonlocal turn_recs
        for d in turn_recs:
            if d:
                accept_if_unlabelled(d)      # not corrected = it was right
        turn_recs = []

    def finish_leg():
        """Leg won and acknowledged (Enter / darts pulled): next leg, or back to the menu."""
        nonlocal screen, marks, last, status
        end_turn()
        if game.match_winner:
            log_result("match")
            print(f"{game.match_winner} wins the match")
            screen = "menu"
        else:
            w = game.leg_winner
            game.next_leg()
            log_result("leg", {"leg_winner": w})
            status = f"next leg - {game.player} to throw"
        marks, last = [], {}
        tracker.reset(grab(cams))

    def open_entry(i, title):
        nonlocal entry, entry_title, entry_target
        entry, entry_title, entry_target = "", title, i

    def apply_entry(txt):
        set_dart_label(entry_target, txt)

    def set_dart_label(i, txt):
        nonlocal pending_unknown, status
        try:
            lab, pts = parse_score(txt)
        except Exception as e:  # noqa
            status = f"didn't understand '{txt}' ({e})"
            return
        if i != "pending" and pending_unknown and i >= len(game.turn):
            i = "pending"
        if i == "pending" or i >= len(game.turn):       # a dart we couldn't read, or one typed in
            if game.add_dart(lab, pts) == "turn_full":
                status = "this turn already has 3 darts"
                return
            d = pending_unknown if i == "pending" else None
            turn_recs.append(d); marks.append(None)
            if d:
                set_label(d, lab, "entered")
            pending_unknown = None
            status = f"entered {lab}"
        else:
            game.set_dart(i, lab, pts)
            if i < len(turn_recs) and turn_recs[i]:
                set_label(turn_recs[i], lab, "corrected")
            if i < len(marks) and marks[i]:
                marks[i] = (marks[i][0], marks[i][1], lab)
            status = f"dart {i + 1} corrected to {lab}"
        print(f"[{game.player}] {status}")

    def recalibrated(name):
        """A camera was calibrated from the web page: use it straight away."""
        nonlocal tracker, last
        cal = load_calibration(name)
        if cal is None or name not in {c.name for c in cams}:
            return
        cals[name] = cal
        tracker = ThrowTracker(cals, cfg["detection"], {n: f.shape for n, f in grab(cams).items()})
        tracker.reset(grab(cams))
        last = {}
        left = [c.name for c in cams if c.name not in cals]
        print(f"{name} calibrated from the web page" + (f" - still to do: {', '.join(left)}" if left else ""))

    def act(a):
        """One user action, from a key, a click or the web page."""
        nonlocal screen, status, marks, last, show_cams, typing
        t = a.get("type")
        if t == "calibrated":
            recalibrated(str(a.get("cam", "")))
            return
        if t == "test_flash":
            test_flash()
            return
        if screen == "menu":
            if menu.act(a) == "start":
                start_game()
            return
        if t == "set_dart":
            i = int(a.get("i", 0))
            if 0 <= i <= len(game.turn):
                set_dart_label(i, str(a.get("label", "")))
        elif t == "undo":
            if turn_recs:
                d = turn_recs.pop()
                if d:
                    set_label(d, "FALSE", "undone")      # remember it as a false detection
            if marks:
                marks.pop()
            game.undo(); status = "undid last dart"
        elif t == "miss":
            if game.add_dart("MISS", 0) != "turn_full":
                turn_recs.append(None); marks.append(None); status = "miss added"
        elif t in ("darts_out", "next_player"):     # darts are out but it didn't notice: end the turn
            end_turn()
            if game.leg_winner:
                finish_leg()
                return
            if game.turn or game.bust or t == "next_player":
                game.next_player()
            tracker.reset(grab(cams)); marks, last = [], {}
            status = f"{game.player} to throw"
        elif t == "next_leg" and game.leg_winner:
            finish_leg()
        elif t == "menu":
            end_turn()
            if not game.match_winner and any(game.legs.values()):
                log_result("unfinished")
            screen = "menu"
        elif t == "cams":
            show_cams = not show_cams

    def web_state():
        common = {"log": logbuf.for_web(), "calls": calls, "web_voice": bool(vcfg["enabled"]) and vout != "computer",
                  "can_calibrate": True, "uncalibrated": [c.name for c in cams if c.name not in cals]}
        if screen == "menu":
            return {"screen": "menu", "status": status,
                    "menu": menu.web_state(), "note": UPDATE.get("note", ""), **common}
        mk = [{"x": round(m[0], 1), "y": round(m[1], 1), "i": i} for i, m in enumerate(marks) if m]
        return {"screen": "play", "status": status, **common, "game": {
            "title": getattr(game, "mode_title", game.name) +
                     (f"   first to {game.legs_to_win} legs" if game.legs_to_win > 1 else ""),
            "players": [{"name": p, "big": game.card(p)[0], "small": game.card(p)[1], "legs": game.legs[p],
                         "active": i == game.cur} for i, p in enumerate(game.players)],
            "player": game.player, "turn": game.turn, "total": sum(x for _, x in game.turn),
            "hint": game.hint(), "bust": game.bust, "leg_winner": game.leg_winner,
            "match_winner": game.match_winner, "legs_to_win": game.legs_to_win,
            "table": game.table(), "marks": mk}}

    url = None
    if not args.no_web:
        from . import web
        url = web.start(args.port)
        if url:
            from .calibrate import WebCalibrator
            web.set_calibrator(WebCalibrator(cams))
            print(f"\nScoreboard / remote: open  {url}  on a phone, iPad or TV (same Wi-Fi)\n")
    headless = args.headless
    if headless:
        print("Running without a screen - use the web page. Ctrl+C to stop.")

    running = False
    while True:
        if url:
            for a in web.take_actions():
                try:
                    act(a)
                except Exception as e:  # noqa - a bad tap mustn't stop the game
                    logbuf.error(f"phone action {a.get('type')} failed", e)
        frames = grab(cams)
        ev = tracker.update(frames) if cals else None
        if ev and screen == "play":
            saved = rec.save(ev["before_raw"], frames, ev) if rec and ev["type"] in ("DART", "UNKNOWN") else None
            if game.leg_winner and ev["type"] == "TAKEOUT":
                finish_leg()
            elif ev["type"] == "DART" and not game.leg_winner:
                res = game.add_dart(ev["label"], ev["points"])
                if res == "turn_full":
                    status = f"extra dart seen ({ev['label']}) - ignored"
                else:
                    status = f"{ev['label']} ({ev['points']})  from {ev['cams_used']} cam(s)"
                    if res == "bust":
                        status += "  BUST"
                    turn_recs.append(saved)
                    marks.append((ev["pos_mm"][0], ev["pos_mm"][1], ev["label"]))
                last = {n: r for n, r in ev["cams"].items() if r.get("ok")}
                print(f"[{game.player}] {status}")
            elif ev["type"] == "TAKEOUT":
                end_turn()
                if game.turn or game.bust:
                    game.next_player()
                status = f"darts pulled - {game.player} to throw"
                last, marks = {}, []
                print(status)
            elif ev["type"] == "UNKNOWN" and not game.leg_winner:
                pending_unknown = saved
                status = "couldn't read that one - type it in the box"
                print(status, {n: r.get("reason") for n, r in ev.get("cams", {}).items()})
                if entry is None and len(game.turn) < 3:
                    open_entry("pending", "Couldn't read that dart - what was it?")

        run_caller()
        if url:
            web.publish(web_state())
        if not running:
            running = True
            if cfg["update"].get("auto"):
                from . import autoupdate
                autoupdate.started_ok()          # made it into the game loop: keep this version
        if headless:
            time.sleep(0.005)
            continue
        W, H_win = ui.window_size(WIN)
        bar_h = ui.info_bar_height(H_win)
        H = H_win - bar_h
        if screen == "menu":
            out, hits = ui.draw_menu(W, H, MODES, sel_row, menu.mode_i, menu.opts(), players, typing)
        else:
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
            note = f"Update {UPDATE['latest']} available (installs on quit)" if UPDATE.get("latest") else UPDATE.get("note")
            out, hits = ui.draw_play(W, H, game, [frames[c.name] for c in cams], [c.name for c in cams], ovs,
                                     status, [m for m in marks if m], show_cams, note,
                                     entry_target if entry is not None else None)
            if game.leg_winner and entry is None:
                w = game.leg_winner
                if game.match_winner:
                    ui.draw_banner(out, f"{w} wins!", [
                        "  -  ".join(f"{p} {game.legs[p]}" for p in game.players) if game.legs_to_win > 1 else "",
                        "Enter = back to the menu      a dart was wrong? press 1, 2 or 3"])
                else:
                    ui.draw_banner(out, f"{w} wins the leg", [
                        "legs  " + "  -  ".join(f"{p} {game.legs[p]}" for p in game.players),
                        "pull the darts out or press Enter for the next leg"])
            if entry is not None:
                _draw_entry_box(out, entry_title, entry)
        if time.time() - flash_at < 3.0:
            ui.draw_flash(out, time.time() - flash_at)
        if show_log:
            ui.draw_log_panel(out, logbuf.lines())
        out = np.vstack([out, ui.draw_info_bar(W, bar_h, logbuf.last(), show_log)])
        hits["log"] = (0, H, W, H_win)
        cv2.imshow(WIN, out)
        k = _key(cv2.waitKeyEx(1))
        hit = _hit(hits, click["pos"])
        click["pos"] = None
        if cv2.getWindowProperty(WIN, cv2.WND_PROP_VISIBLE) < 1:
            break
        if k == "tab" or hit == "log":
            if k == "tab":
                k = None
            hit = None
            show_log = not show_log

        # ------------------------------------------------ menu
        if screen == "menu":
            n_opts = len(menu.opts())
            add_row = n_opts + 1
            if hit:
                if hit.startswith("mode"):
                    act({"type": "mode", "i": int(hit[4:])}); sel_row = 0
                elif hit.startswith("opt"):
                    sel_row = int(hit[3:]); act({"type": "opt", "row": sel_row, "step": 1})
                elif hit.startswith("del"):
                    act({"type": "remove_player", "i": int(hit[3:])})
                elif hit == "add":
                    sel_row = add_row
                elif hit == "start":
                    act({"type": "start"})
                elif hit == "test_flash":
                    act({"type": "test_flash"})
            if k is None:
                continue
            if k == "esc" or (k == "q" and not typing):
                break
            if k == "up":
                sel_row = max(0, sel_row - 1)
            elif k == "down":
                sel_row = min(add_row, sel_row + 1)
            elif k in ("left", "right"):
                if sel_row <= n_opts:
                    menu.change_opt(sel_row, -1 if k == "left" else 1)
            elif k == "enter":
                if typing.strip():
                    menu.add_player(typing); typing = ""
                elif players:
                    start_game()
            elif k == "back":
                if typing:
                    typing = typing[:-1]
                elif players:
                    players.pop()
            elif len(k) == 1 and (k.isalnum() or k in " -'") and menu.can_add():
                sel_row = add_row
                typing = (typing + k)[:14]
                typing = typing[:1].upper() + typing[1:]
            continue

        # ------------------------------------------------ correction box open
        if entry is not None:
            if k == "enter":
                if entry.strip():
                    apply_entry(entry)
                entry = None
            elif k == "esc":
                entry = None; status = "cancelled"
            elif k == "back":
                entry = entry[:-1]
            elif k and len(k) == 1 and k.isalnum() and len(entry) < 8:
                entry += k.upper()
            continue

        # ------------------------------------------------ playing
        if hit and hit.startswith("dart"):
            j = int(hit[4:])
            if j <= len(game.turn):
                open_entry(j, f"Dart {j + 1} was:")
        if k is None:
            continue
        if k == "q" or k == "esc":
            act({"type": "menu"})
            continue
        if k == "enter" and game.leg_winner:
            act({"type": "next_leg"})
            continue
        if k in ("1", "2", "3"):
            j = int(k) - 1
            if j <= len(game.turn):
                open_entry(j, f"Dart {j + 1} was:")
        if k == "c":
            j = max(0, len(game.turn) - 1) if game.turn else 0
            open_entry(j, "Correct the last dart to:" if game.turn else "Dart 1 was:")
        named = {"v": "cams", "u": "undo", "m": "miss", "r": "darts_out", "n": "next_player"}
        if k in named:
            act({"type": named[k]})
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
    if not sys.stdin or not sys.stdin.isatty():
        print("(no keyboard here - run  python -m dartvision update -y  to install it)")
        return
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
    s.add_argument("--web", action="store_true", help="calibrate from a phone / PC browser instead of a window "
                   "(automatic on a Pi with no screen)")
    s.add_argument("--port", type=int, default=8080, help="web page port (with --web)")
    s = sub.add_parser("play"); s.add_argument("players", nargs="*", default=["Player 1"])
    s.add_argument("--start", type=int, default=501, help="pre-select 301 / 501 / 701 in the menu")
    s.add_argument("--headless", action="store_true", help="no window: play from the web page only (Pi with no screen)")
    s.add_argument("--port", type=int, default=8080, help="web scoreboard port")
    s.add_argument("--no-web", action="store_true", help="don't start the web scoreboard"); s.add_argument("--no-record", action="store_true")
    s = sub.add_parser("label"); s.add_argument("session"); s.add_argument("--all", action="store_true")
    s = sub.add_parser("replay"); s.add_argument("session")
    s = sub.add_parser("update"); s.add_argument("-y", "--yes", action="store_true")
    sub.add_parser("version")
    args = ap.parse_args(argv)
    logbuf.install()
    from . import __version__
    if args.cmd == "version":
        print(f"dartvision v{__version__}"); return
    cfg = load_config(args.config)
    auto = args.cmd == "play" and cfg["update"].get("auto")
    if auto:
        from . import autoupdate
        if os.environ.get(autoupdate.ENV_UPDATED):
            st = autoupdate._load(autoupdate.ROOT)
            if st.get("pending") and st.get("new"):
                UPDATE["note"] = "updated to " + autoupdate._short(autoupdate.ROOT, st["new"])
        print("Checking GitHub for updates ...")
        res, msg = autoupdate.update(branch=cfg["update"].get("branch", "main"))
        print({"updated": "Updated:", "up_to_date": "Up to date:", "offline": "Update check skipped (offline):",
               "skipped": "Not updating:", "rolled_back": "Update not kept:", "error": "Update check failed:"}[res], msg)
        if res == "updated":
            print("Restarting on the new version ...\n")
            autoupdate.restart()
        if res == "rolled_back":
            UPDATE["note"] = "an update failed to start - kept the previous version"
    if args.cmd in ("play", "preview", "calibrate") and cfg["update"]["check_on_start"] and cfg["update"]["repo"]:
        from .update import check_in_background

        def found(info):
            UPDATE.update(info)
            print(f"** Update available: {info['latest']} - run  python -m dartvision update **")
        check_in_background(cfg["update"]["repo"], found)
    run = {"setup": cmd_setup, "preview": cmd_preview, "calibrate": cmd_calibrate, "play": cmd_play,
           "label": cmd_label, "replay": cmd_replay, "update": cmd_update}[args.cmd]
    try:
        run(args)
    except Exception:
        if auto and autoupdate.crashed_after_update():
            import traceback
            traceback.print_exc()
            print("Restarting on the previous version ...\n")
            autoupdate.restart()
        raise


if __name__ == "__main__":
    main()
