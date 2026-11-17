"""The start-screen settings (game, options, players), shared by the window, the keyboard and the
web page so they all change the same thing. Standard library only, so it can be tested on its own.
"""
from .games import MODES

LEGS = [1, 2, 3, 4, 5, 7]
MAX_PLAYERS = 6
NAME_LEN = 14
DEFAULT_PLAYER = "Player 1"


class Menu:
    def __init__(self, players=(), start="501", modes=MODES):
        self.modes = modes
        self.names = [m[0] for m in modes]
        self.players = [p for p in players if p != DEFAULT_PLAYER][:MAX_PLAYERS] or [DEFAULT_PLAYER]
        self.mode_i = self.names.index(str(start)) if str(start) in self.names else 0
        self.opt = {"legs": 1, "double_out": True, "double_in": False}

    @property
    def mode_name(self):
        return self.names[self.mode_i]

    def opts(self):
        """Option rows for the current game: [(label, value text)]. Row numbers start at 1."""
        o = [("Legs", f"first to {self.opt['legs']}" if self.opt["legs"] > 1 else "single leg")]
        if self.mode_name in ("301", "501", "701"):
            o += [("Double out", "yes" if self.opt["double_out"] else "no"),
                  ("Double in", "yes" if self.opt["double_in"] else "no")]
        return o

    def set_mode(self, i):
        self.mode_i = int(i) % len(self.modes)

    def change_opt(self, row, step):
        """Row 0 is the game itself, then the option rows from opts()."""
        if row == 0:
            self.mode_i = (self.mode_i + step) % len(self.modes)
        elif row == 1:
            self.opt["legs"] = LEGS[(LEGS.index(self.opt["legs"]) + step) % len(LEGS)]
        elif row == 2 and len(self.opts()) >= 2:
            self.opt["double_out"] = not self.opt["double_out"]
        elif row == 3 and len(self.opts()) >= 3:
            self.opt["double_in"] = not self.opt["double_in"]

    def can_add(self):
        return len(self.players) < MAX_PLAYERS or self.players == [DEFAULT_PLAYER]

    def add_player(self, name):
        """Add a player (the 'Player 1' placeholder makes way for the first real name). True if added."""
        name = str(name).strip()[:NAME_LEN]
        if not name or not self.can_add():
            return False
        if self.players == [DEFAULT_PLAYER]:
            self.players.clear()
        self.players.append(name)
        return True

    def remove_player(self, i):
        if 0 <= i < len(self.players):
            self.players.pop(i)
            return True
        return False

    def new_game(self):
        return self.modes[self.mode_i][1](list(self.players), dict(self.opt))

    def act(self, a):
        """A menu action from the web page or a click. Returns 'start' when the game should start."""
        t = a.get("type")
        try:
            if t == "mode":
                self.set_mode(int(a.get("i", 0)))
            elif t == "opt":
                self.change_opt(int(a.get("row", 1)), int(a.get("step", 1)))
            elif t == "add_player":
                self.add_player(a.get("name", ""))
            elif t == "remove_player":
                self.remove_player(int(a.get("i", -1)))
            elif t == "start" and self.players:
                return "start"
        except (TypeError, ValueError):
            pass
        return None

    def web_state(self):
        return {"modes": list(self.names), "mode": self.mode_i, "opts": [list(o) for o in self.opts()],
                "players": list(self.players)}
