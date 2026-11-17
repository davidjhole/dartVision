"""Game modes. Each turn is re-worked out from its darts every time, so any dart of the
current turn can be corrected (not just the last one).

Every mode has the same shape:
    players, cur, player, turn [(label, points)], bust, leg_winner, match_winner, legs
    add_dart(label, pts)  set_dart(i, label, pts)  undo()  next_player()  next_leg()
    card(p) -> (big text, small text)   hint() -> str   table() -> None or rows for a grid
"""
import copy

def parse(label):
    """'T20' -> (20, 3), 'D5' -> (5, 2), 'S1' -> (1, 1), 'SB' -> (25, 1), 'DB' -> (25, 2), MISS -> (0, 0)."""
    if label == "DB":
        return 25, 2
    if label == "SB":
        return 25, 1
    if not label or label == "MISS":
        return 0, 0
    return int(label[1:]), {"S": 1, "D": 2, "T": 3}[label[0]]


class Game:
    name = "game"

    def __init__(self, players, legs_to_win=1):
        self.players = list(players)
        self.legs_to_win = legs_to_win
        self.legs = {p: 0 for p in self.players}
        self.leg_no = 0
        self.leg_starter = 0
        self.match_winner = None
        self.darts_thrown = {p: 0 for p in self.players}     # whole match, for averages
        self.leg_log = []                                    # finished legs (for the results file)
        self._start_leg()

    # ---------------------------------------------------------------- per mode
    def initial(self, p):
        raise NotImplementedError

    def apply(self, st, label, pts, i):
        """Apply one dart to the player's state st (mutate). Return None, 'bust' or 'win'."""
        raise NotImplementedError

    def round_limit(self):
        return None

    def leg_winner_at_limit(self):
        return None

    def card(self, p):
        return "", ""

    def hint(self):
        return ""

    def table(self):
        return None

    # ---------------------------------------------------------------- shared
    @property
    def player(self):
        return self.players[self.cur]

    def _start_leg(self):
        self.state = {p: self.initial(p) for p in self.players}
        self.cur = self.leg_starter
        self.round = 1
        self.turn, self.bust, self.leg_winner = [], False, None
        self.history = []
        self.leg_darts = {p: 0 for p in self.players}
        self._counted = None
        self._ended_on_limit = False
        self._snap = copy.deepcopy(self.state[self.player])

    def _recompute(self):
        st = copy.deepcopy(self._snap)
        self.bust, self.leg_winner = False, None
        for i, (lab, pts) in enumerate(self.turn):
            r = self.apply(st, lab, pts, i)
            if r == "bust":
                st, self.bust = copy.deepcopy(self._snap), True
                break
            if r == "win":
                self.leg_winner = self.player
                break
        self.state[self.player] = st
        self._count_leg()

    def _count_leg(self):
        """Keep the legs tally in step with leg_winner (a correction can take a win back)."""
        if self._counted == self.leg_winner:
            return
        if self._counted:
            self.legs[self._counted] -= 1
        if self.leg_winner:
            self.legs[self.leg_winner] += 1
        self._counted = self.leg_winner
        self.match_winner = next((p for p in self.players if self.legs[p] >= self.legs_to_win), None)

    def add_dart(self, label, pts):
        """Returns 'ok', 'bust', 'win' or 'turn_full'."""
        if self.leg_winner or self.bust or len(self.turn) >= 3:
            return "turn_full"
        self.turn.append((label, pts))
        self._update()
        return "win" if self.leg_winner else "bust" if self.bust else "ok"

    def set_dart(self, i, label, pts):
        if self._ended_on_limit:
            return
        if 0 <= i < len(self.turn):
            self.turn[i] = (label, pts)
        elif i == len(self.turn) and i < 3:
            self.turn.append((label, pts))
        self._update()

    def correct_last(self, label, pts):
        self.set_dart(len(self.turn) - 1 if self.turn else 0, label, pts)

    def undo(self):
        if self.turn and not self._ended_on_limit:
            self.turn.pop()
            self._update()

    def _update(self):
        self._recompute()

    def next_player(self):
        """End the current turn. Returns True if the leg ended on the round limit."""
        if self.leg_winner:
            return False
        p = self.player
        self.history.append((p, list(self.turn), self.bust))
        self.darts_thrown[p] += len(self.turn)
        self.leg_darts[p] += len(self.turn)
        self.turn, self.bust = [], False
        self.cur = (self.cur + 1) % len(self.players)
        if self.cur == self.leg_starter:
            self.round += 1
            lim = self.round_limit()
            if lim and self.round > lim:
                self.leg_winner = self.leg_winner_at_limit()
                self._ended_on_limit = True
                self._count_leg()
                self.cur = (self.cur - 1) % len(self.players)
                return True
        self._snap = copy.deepcopy(self.state[self.player])
        return False

    def next_leg(self):
        """After a leg is won: log it and set up the next one (the next player starts)."""
        w = self.leg_winner
        p = self.player
        if self.turn:
            self.darts_thrown[p] += len(self.turn)
            self.leg_darts[p] += len(self.turn)
            self.history.append((p, list(self.turn), False))
            self.turn = []
        self._archive_leg()
        self.leg_log.append({"leg": len(self.leg_log) + 1, "winner": w,
                             "darts": dict(self.leg_darts), "turns": len(self.history)})
        self.leg_starter = (self.leg_starter + 1) % len(self.players)
        self._start_leg()

    def _archive_leg(self):
        pass

    def summary(self):
        return {"mode": self.name, "players": self.players, "legs_to_win": self.legs_to_win,
                "legs": self.legs, "winner": self.match_winner, "leg_log": self.leg_log}


# ------------------------------------------------------------------------- x01
class X01(Game):
    def __init__(self, players, start=501, double_out=True, double_in=False, legs_to_win=1):
        self.start, self.double_out, self.double_in = start, double_out, double_in
        self.scored = {p: 0 for p in players}
        super().__init__(players, legs_to_win)
        self.name = f"{start}"

    def initial(self, p):
        return {"left": self.start, "in": not self.double_in}

    def apply(self, st, label, pts, i):
        num, mult = parse(label)
        if not st["in"]:
            if mult == 2:
                st["in"] = True
            else:
                return None
        new = st["left"] - pts
        finishing = mult == 2 or not self.double_out
        if new == 0 and finishing:
            st["left"] = 0
            return "win"
        if new < 0 or new == 0 or (self.double_out and new == 1):
            return "bust"
        st["left"] = new
        return None

    def card(self, p):
        darts = self.darts_thrown[p] + (len(self.turn) if p == self.player else 0)
        done = sum(t for pl, ds, b in self._all_turns() if pl == p and not b for t in [sum(x for _, x in ds)])
        avg = 3 * done / darts if darts else 0.0
        return str(self.state[p]["left"]), f"avg {avg:.1f}"

    def _all_turns(self):
        cur = [(self.player, self.turn, self.bust)]
        return [t for leg in getattr(self, "_old_turns", []) for t in leg] + self.history + cur

    def _archive_leg(self):
        self._old_turns = getattr(self, "_old_turns", []) + [list(self.history)]

    def hint(self):
        if self.bust:
            return ""
        left = self.state[self.player]["left"]
        need = 3 - len(self.turn)
        h = checkout_hint(left)
        return h if h and len(h.split()) <= need else ""

    @property
    def mode_title(self):
        return f"{self.start}  {'double out' if self.double_out else 'straight out'}" + \
            ("  double in" if self.double_in else "")


# ---------------------------------------------------------------------- cricket
CRICKET = [20, 19, 18, 17, 16, 15, 25]


class Cricket(Game):
    name = "cricket"
    mode_title = "Cricket"

    def initial(self, p):
        return {"marks": {n: 0 for n in CRICKET}, "points": 0}

    def apply(self, st, label, pts, i):
        num, mult = parse(label)
        if num in CRICKET:
            for _ in range(mult):
                if st["marks"][num] < 3:
                    st["marks"][num] += 1
                elif any(self.state[o]["marks"][num] < 3 for o in self.players if o != self.player):
                    st["points"] += num
        others_pts = [self.state[o]["points"] for o in self.players if o != self.player]
        if all(v == 3 for v in st["marks"].values()) and all(st["points"] >= x for x in others_pts):
            return "win"
        return None

    def card(self, p):
        closed = sum(1 for v in self.state[p]["marks"].values() if v == 3)
        return str(self.state[p]["points"]), f"{closed}/7 closed"

    def table(self):
        rows = []
        for n in CRICKET:
            rows.append(("B" if n == 25 else str(n), [self.state[p]["marks"][n] for p in self.players],
                         all(self.state[p]["marks"][n] == 3 for p in self.players)))
        return rows


# --------------------------------------------------------------- around the clock
class AroundTheClock(Game):
    name = "around the clock"
    mode_title = "Around the clock"
    ORDER = list(range(1, 21)) + [25]

    def initial(self, p):
        return {"next": 0}

    def apply(self, st, label, pts, i):
        num, mult = parse(label)
        if st["next"] < len(self.ORDER) and num == self.ORDER[st["next"]]:
            st["next"] += 1
            if st["next"] == len(self.ORDER):
                return "win"
        return None

    def _target(self, p):
        n = self.state[p]["next"]
        return "done" if n >= len(self.ORDER) else ("Bull" if self.ORDER[n] == 25 else str(self.ORDER[n]))

    def card(self, p):
        return self._target(p), f"{self.state[p]['next']}/21 hit"

    def hint(self):
        return f"aim for {self._target(self.player)}"


# ------------------------------------------------------------------- count up
class CountUp(Game):
    name = "count up"
    ROUNDS = 8

    @property
    def mode_title(self):
        return f"Count up - round {min(self.round, self.ROUNDS)} of {self.ROUNDS}"

    def initial(self, p):
        return {"score": 0}

    def apply(self, st, label, pts, i):
        st["score"] += pts
        return None

    def round_limit(self):
        return self.ROUNDS

    def leg_winner_at_limit(self):
        return max(self.players, key=lambda p: self.state[p]["score"])

    def card(self, p):
        darts = self.leg_darts[p] + (len(self.turn) if p == self.player else 0)
        avg = 3 * self.state[p]["score"] / darts if darts else 0.0
        return str(self.state[p]["score"]), f"avg {avg:.1f}"


MODES = [
    ("501", lambda pl, o: X01(pl, 501, o["double_out"], o["double_in"], o["legs"])),
    ("301", lambda pl, o: X01(pl, 301, o["double_out"], o["double_in"], o["legs"])),
    ("701", lambda pl, o: X01(pl, 701, o["double_out"], o["double_in"], o["legs"])),
    ("Cricket", lambda pl, o: Cricket(pl, o["legs"])),
    ("Around the clock", lambda pl, o: AroundTheClock(pl, o["legs"])),
    ("Count up (8 rounds)", lambda pl, o: CountUp(pl, o["legs"])),
]


# simple checkout table for the common finishes (<= 170)
def checkout_hint(left):
    if left > 170 or left in (169, 168, 166, 165, 163, 162, 159) or left < 2:
        return ""
    singles = [(f"S{n}", n) for n in range(1, 21)] + [("SB", 25)]
    trebles = [(f"T{n}", 3 * n) for n in range(20, 0, -1)]
    doubles = [(f"D{n}", 2 * n) for n in range(20, 0, -1)] + [("DB", 50)]
    for d in doubles:
        if d[1] == left:
            return d[0]
    for a in trebles + singles:
        for d in doubles:
            if a[1] + d[1] == left:
                return f"{a[0]} {d[0]}"
    for a in trebles:
        for b in trebles + singles:
            for d in doubles:
                if a[1] + b[1] + d[1] == left:
                    return f"{a[0]} {b[0]} {d[0]}"
    return ""

