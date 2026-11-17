"""The darts caller: says the scores out loud, and flashes for a 180.

TurnWatcher looks at the game after every change, from whatever caused it (a camera, a key, the
phone), and returns what a caller would say: each finished turn's score ("One hundred and
eighty!"), "Bust", "Game shot", and "Dave, you require 40" at the start of a turn on a finish.

Speaker says it out loud on this computer (macOS `say`, Linux / Pi `espeak-ng` or `espeak`,
Windows' built-in voice), one phrase at a time in the background. Through the Pi's HDMI the
sound comes out of the TV. The web page can also speak (phone / iPad / TV browser).
"""
import queue
import shutil
import subprocess
import sys
import threading

from .games import X01, CountUp, checkout_hint

_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
         "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
         "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def number_words(n):
    """British style: 140 -> 'one hundred and forty', 26 -> 'twenty six'."""
    n = int(n)
    if n < 0:
        return "minus " + number_words(-n)
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + ("" if n % 10 == 0 else " " + _ONES[n % 10])
    if n < 1000:
        rest = n % 100
        return _ONES[n // 100] + " hundred" + ("" if rest == 0 else " and " + number_words(rest))
    return str(n)


def phrase(ev):
    """The words for one caller event."""
    k = ev["kind"]
    if k == "game_on":
        return f"{ev['player']} to throw first. Game on!"
    if k == "score":
        t = ev["total"]
        if t == 180:
            return "One hundred and eighty!"
        if t == 0:
            return "No score"
        w = number_words(t)
        return w[0].upper() + w[1:]
    if k == "bust":
        return "Bust"
    if k == "require":
        return f"{ev['player']}, you require {number_words(ev['left'])}"
    if k == "win":
        if ev.get("x01"):
            return "Game shot, and the match!" if ev["match"] else "Game shot, and the leg!"
        return f"{ev['player']} wins the match!" if ev["match"] else f"{ev['player']} wins the leg"
    return ""


class TurnWatcher:
    """Turns game changes into caller events. Call observe(game) whenever something may have
    changed (cheap: once per frame is fine). Each thing is said once; a dart corrected after
    the call gets the new score called."""

    def __init__(self):
        self.game = None

    def _reset(self, game):
        self.game = game
        self.called = {}         # turn key -> what was called for it
        self.said = set()        # one-off keys: game on, require, win
        self.seen_hist = 0
        self.leg = -1

    def _turn_event(self, game, player, darts, bust, won):
        total = sum(p for _, p in darts)
        if won:
            return None          # the win call covers it
        if bust:
            return {"kind": "bust", "player": player, "total": total}
        if isinstance(game, (X01, CountUp)):
            return {"kind": "score", "player": player, "total": total, "darts": len(darts),
                    "flash": total == 180 and len(darts) == 3}
        return None              # cricket / around the clock: no score call

    def _call(self, out, key, ev):
        sig = None if ev is None else (ev["kind"], ev.get("total"))
        if key in self.called and self.called[key] == sig:
            return
        self.called[key] = sig
        if ev is not None:
            out.append(ev)

    def observe(self, game):
        out = []
        if game is None:
            self.game = None
            return out
        if game is not self.game:
            self._reset(game)
        leg = len(game.leg_log)
        if leg != self.leg:      # a new leg: history starts again
            self.leg, self.seen_hist = leg, 0
            if not game.history and not game.turn:
                self._once(out, ("game_on", leg), {"kind": "game_on", "player": game.player})

        # turns that ended since last time (darts pulled before all three were thrown)
        while self.seen_hist < len(game.history):
            i = self.seen_hist
            p, darts, bust = game.history[i]
            key = (leg, i)
            if key not in self.called and darts:
                self._call(out, key, self._turn_event(game, p, darts, bust, False))
            self.seen_hist += 1

        key = (leg, len(game.history))
        done = len(game.turn) == 3 or game.bust or game.leg_winner
        if done and not getattr(game, "_ended_on_limit", False):
            self._call(out, key, self._turn_event(game, game.player, game.turn, game.bust,
                                                  bool(game.leg_winner)))
        if game.leg_winner:
            self._once(out, ("win", leg), {"kind": "win", "player": game.leg_winner,
                                           "match": bool(game.match_winner),
                                           "x01": isinstance(game, X01)})
        elif not game.turn and isinstance(game, X01):
            st = game.state[game.player]
            if st["in"] and st["left"] <= 170 and checkout_hint(st["left"]):
                self._once(out, ("require", key), {"kind": "require", "player": game.player,
                                                   "left": st["left"]})
        return out

    def _once(self, out, key, ev):
        if key not in self.said:
            self.said.add(key)
            out.append(ev)


# ------------------------------------------------------------------ speaking on this computer
def find_engine(name="auto"):
    """The command that speaks on this computer, as a function text -> argv list, or None."""
    def say(t):
        return ["say", t]

    def espeak(binary):
        return lambda t: [binary, "-v", "en-gb", "-s", "150", t]

    def sapi(t):
        t = t.replace("'", "''")
        return ["powershell", "-NoProfile", "-Command",
                "Add-Type -AssemblyName System.Speech; "
                f"(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{t}')"]

    if name in ("off", "none", None, False):
        return None
    if name in ("say",) or (name == "auto" and sys.platform == "darwin" and shutil.which("say")):
        return say
    if name in ("sapi", "windows") or (name == "auto" and sys.platform.startswith("win")):
        return sapi
    if name in ("espeak", "espeak-ng", "auto"):
        for b in ("espeak-ng", "espeak"):
            if shutil.which(b):
                return espeak(b)
    return None


class Speaker:
    """Says phrases one at a time in a background thread, so the game never waits for it."""

    def __init__(self, engine="auto", runner=None):
        self.cmd = find_engine(engine)
        self.runner = runner or (lambda argv: subprocess.run(argv, stdout=subprocess.DEVNULL,
                                                             stderr=subprocess.DEVNULL, timeout=20))
        self.q = queue.Queue()
        if self.cmd:
            threading.Thread(target=self._run, daemon=True).start()

    @property
    def available(self):
        return self.cmd is not None

    def say(self, text):
        if self.cmd and text:
            # a long queue means it's fallen behind: skip the stale calls
            while self.q.qsize() > 2:
                try:
                    self.q.get_nowait()
                except queue.Empty:
                    break
            self.q.put(text)

    def _run(self):
        while True:
            t = self.q.get()
            try:
                self.runner(self.cmd(t))
            except Exception:  # noqa - a missing or broken voice must never stop the game
                pass
