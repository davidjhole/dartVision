"""Minimal x01 game (501 / 301, double out) for 1-4 players."""


class X01:
    def __init__(self, players, start=501, double_out=True):
        self.players = list(players)
        self.start, self.double_out = start, double_out
        self.scores = {p: start for p in self.players}
        self.cur = 0
        self.turn = []            # [(label, points)]
        self.turn_start = start
        self.history = []         # completed turns: (player, [darts], bust)
        self.winner = None
        self.bust = False

    @property
    def player(self):
        return self.players[self.cur]

    def _recompute(self):
        left, self.bust, self.winner = self.turn_start, False, None
        for label, pts in self.turn:
            new = left - pts
            finishing = label.startswith("D") or label == "DB" or not self.double_out
            if new == 0 and finishing:
                left, self.winner = 0, self.player
                break
            if new < 0 or new == 0 or (self.double_out and new == 1):
                left, self.bust = self.turn_start, True
                break
            left = new
        self.scores[self.player] = left

    def add_dart(self, label, points):
        """Returns 'ok', 'bust', 'checkout' or 'turn_full'."""
        if self.winner or self.bust or len(self.turn) >= 3:
            return "turn_full"
        self.turn.append((label, points))
        self._recompute()
        return "checkout" if self.winner else "bust" if self.bust else "ok"

    def undo(self):
        if self.turn:
            self.turn.pop()
            self._recompute()

    def correct_last(self, label, points):
        if self.turn:
            self.turn.pop()
        self.turn.append((label, points))
        self._recompute()
        return "checkout" if self.winner else "bust" if self.bust else "ok"

    def next_player(self):
        self.history.append((self.player, list(self.turn), self.bust))
        self.turn, self.bust = [], False
        self.cur = (self.cur + 1) % len(self.players)
        self.turn_start = self.scores[self.player]

    def three_dart_avg(self, player):
        darts = [d for pl, t, _ in self.history if pl == player for d in t]
        scored = self.start - self.scores[player] if not self.winner or self.winner != player else self.start
        n = len(darts) + (len(self.turn) if self.player == player else 0)
        return 3 * scored / n if n else 0.0


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
