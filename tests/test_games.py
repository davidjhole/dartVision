"""Game rules: python -m pytest tests/test_games.py"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dartvision.games import (MODES, AroundTheClock, CountUp, Cricket, X01,  # noqa: E402
                              checkout_hint, parse)


def throw(g, *labels):
    """Throw darts for the current player; returns the last add_dart result."""
    from dartvision.board import parse_score
    r = None
    for lab in labels:
        r = g.add_dart(*parse_score(lab))
    return r


def turn(g, *labels):
    r = throw(g, *labels)
    g.next_player()
    return r


# ------------------------------------------------------------------ helpers
@pytest.mark.parametrize("label,expected", [
    ("T20", (20, 3)), ("D5", (5, 2)), ("S1", (1, 1)), ("SB", (25, 1)), ("DB", (25, 2)),
    ("MISS", (0, 0)), ("", (0, 0))])
def test_parse(label, expected):
    assert parse(label) == expected


@pytest.mark.parametrize("left,hint", [
    (40, "D20"), (50, "DB"), (170, "T20 T20 DB"), (100, "T20 D20"), (2, "D1"),
    (169, ""), (171, ""), (1, ""), (159, "")])
def test_checkout_hint(left, hint):
    assert checkout_hint(left) == hint


@pytest.mark.parametrize("left", range(2, 171))
def test_checkout_hint_adds_up_and_ends_on_a_double(left):
    h = checkout_hint(left)
    if not h:
        return
    darts = h.split()
    assert len(darts) <= 3
    assert darts[-1].startswith("D") or darts[-1] == "DB"
    assert sum(25 * parse(d)[1] if d in ("SB", "DB") else parse(d)[0] * parse(d)[1] for d in darts) == left


# ---------------------------------------------------------------------- x01
def test_x01_scores_and_alternates_players():
    g = X01(["A", "B"], 501)
    assert g.player == "A"
    turn(g, "T20", "T20", "T20")
    assert g.state["A"]["left"] == 321 and g.player == "B"
    turn(g, "S1", "S5", "MISS")
    assert g.state["B"]["left"] == 495 and g.player == "A"
    assert g.card("A") == ("321", "avg 180.0")


def test_x01_bust_resets_the_turn():
    g = X01(["A"], 301)
    g.state["A"]["left"] = 40
    g._snap = dict(g.state["A"])
    assert throw(g, "T20") == "bust"
    assert g.bust and g.state["A"]["left"] == 40
    assert throw(g, "S1") == "turn_full"        # no more darts after a bust


@pytest.mark.parametrize("left,dart", [(1, "S1"), (2, "S1"), (16, "S16"), (20, "T20")])
def test_x01_double_out_busts(left, dart):
    g = X01(["A"], 501, double_out=True)
    g.state["A"]["left"] = left
    g._snap = dict(g.state["A"])
    assert throw(g, dart) == "bust"


def test_x01_double_out_win():
    g = X01(["A", "B"], 501)
    g.state["A"]["left"] = 40
    g._snap = dict(g.state["A"])
    assert throw(g, "D20") == "win"
    assert g.leg_winner == "A" and g.match_winner == "A" and g.legs["A"] == 1
    assert throw(g, "S1") == "turn_full"


def test_x01_straight_out():
    g = X01(["A"], 301, double_out=False)
    g.state["A"]["left"] = 20
    g._snap = dict(g.state["A"])
    assert throw(g, "S20") == "win"


def test_x01_double_in():
    g = X01(["A"], 501, double_in=True)
    throw(g, "T20", "D10", "S5")
    assert g.state["A"]["left"] == 501 - 20 - 5    # T20 doesn't count until a double


def test_correcting_a_dart_takes_back_a_win():
    g = X01(["A", "B"], 501)
    g.state["A"]["left"] = 40
    g._snap = dict(g.state["A"])
    throw(g, "D20")
    assert g.legs["A"] == 1
    g.set_dart(0, "S20", 20)
    assert g.leg_winner is None and g.legs["A"] == 0 and g.match_winner is None
    assert g.state["A"]["left"] == 20


def test_correcting_any_dart_of_the_turn():
    g = X01(["A"], 501)
    throw(g, "T20", "T20", "T20")
    g.set_dart(0, "S20", 20)
    assert g.state["A"]["left"] == 501 - 140
    g.undo()
    assert g.turn == [("S20", 20), ("T20", 60)] and g.state["A"]["left"] == 501 - 80


def test_set_dart_can_fill_the_next_empty_dart():
    g = X01(["A"], 501)
    g.set_dart(0, "T20", 60)
    assert g.turn == [("T20", 60)]
    g.set_dart(5, "T20", 60)                     # out of range: ignored
    assert len(g.turn) == 1


def test_fourth_dart_is_refused():
    g = X01(["A"], 501)
    throw(g, "S1", "S1", "S1")
    assert throw(g, "S1") == "turn_full" and len(g.turn) == 3


def test_x01_hint_only_when_reachable_with_darts_left():
    g = X01(["A"], 501)
    g.state["A"]["left"] = 100
    g._snap = dict(g.state["A"])
    assert g.hint() == "T20 D20"
    throw(g, "MISS", "MISS")
    assert g.hint() == ""                        # needs two darts, one left


def test_legs_and_match():
    g = X01(["A", "B"], 301, legs_to_win=2)
    g.state["A"]["left"] = 40
    g._snap = dict(g.state["A"])
    throw(g, "D20")
    assert g.leg_winner == "A" and g.match_winner is None
    g.next_leg()
    assert g.player == "B"                        # the other player starts the next leg
    assert g.state["A"]["left"] == 301 and g.leg_log[0]["winner"] == "A"
    g.state["B"]["left"] = 2
    g._snap = dict(g.state["B"])
    throw(g, "D1")
    assert g.legs == {"A": 1, "B": 1} and g.match_winner is None
    g.next_leg()
    assert g.player == "A"
    g.state["A"]["left"] = 50
    g._snap = dict(g.state["A"])
    throw(g, "DB")
    assert g.match_winner == "A"
    s = g.summary()
    assert s["winner"] == "A" and s["legs"] == {"A": 2, "B": 1} and len(s["leg_log"]) == 2


def test_x01_mode_title():
    assert X01(["A"], 501).mode_title == "501  double out"
    assert X01(["A"], 301, double_out=False, double_in=True).mode_title == "301  straight out  double in"


# ------------------------------------------------------------------- cricket
def test_cricket_marks_and_points():
    g = Cricket(["A", "B"])
    turn(g, "T20", "S20", "S19")
    assert g.state["A"]["marks"][20] == 3 and g.state["A"]["points"] == 20   # 4th mark scores
    assert g.state["A"]["marks"][19] == 1
    turn(g, "T20")                                 # B closes 20
    assert g.state["B"]["points"] == 0
    turn(g, "T20")                                 # closed for everyone: no points
    assert g.state["A"]["points"] == 20
    assert g.card("A") == ("20", "1/7 closed")


def test_cricket_ignores_numbers_outside_15_to_20_and_bull():
    g = Cricket(["A", "B"])
    turn(g, "T14", "D1", "S7")
    assert all(v == 0 for v in g.state["A"]["marks"].values())


def test_cricket_win_needs_all_closed_and_not_behind():
    g = Cricket(["A", "B"])
    for n in (20, 19, 18, 17, 16, 15):
        g.state["A"]["marks"][n] = 3
    g.state["A"]["marks"][25] = 2
    g.state["B"]["points"] = 10
    g._snap = {"marks": dict(g.state["A"]["marks"]), "points": 0}
    assert throw(g, "SB") is not None and g.leg_winner is None   # closed but behind
    g.undo()
    g.state["B"]["points"] = 0
    assert throw(g, "SB") == "win"


def test_cricket_table():
    g = Cricket(["A", "B"])
    throw(g, "T20")
    rows = g.table()
    assert rows[0] == ("20", [3, 0], False) and rows[-1][0] == "B" and len(rows) == 7


# ----------------------------------------------------------- around the clock
def test_around_the_clock():
    g = AroundTheClock(["A"])
    throw(g, "S1", "T2", "S5")
    assert g.state["A"]["next"] == 2 and g.hint() == "aim for 3"
    g.state["A"]["next"] = 20
    g._snap = dict(g.state["A"])
    g.turn = []
    assert g.hint() == "aim for Bull"
    assert throw(g, "DB") == "win"
    assert g.card("A") == ("done", "21/21 hit")


# ------------------------------------------------------------------- count up
def test_count_up_ends_after_8_rounds():
    g = CountUp(["A", "B"])
    for _ in range(7):
        assert not turn(g, "T20") == "win"
        turn(g, "S1")
    throw(g, "T20")
    assert g.next_player() is False
    throw(g, "S1")
    assert g.next_player() is True
    assert g.leg_winner == "A" and g.match_winner == "A"
    assert g.state["A"]["score"] == 480 and g.state["B"]["score"] == 8
    g.undo()                                        # finished: nothing changes any more
    assert g.state["A"]["score"] == 480


# ---------------------------------------------------------------------- modes
@pytest.mark.parametrize("name,make", MODES)
def test_every_mode_starts_and_plays_a_turn(name, make):
    g = make(["A", "B"], {"legs": 1, "double_out": True, "double_in": False})
    throw(g, "S20", "MISS", "T19")
    assert len(g.turn) == 3
    g.next_player()
    assert g.player == "B" and g.turn == []
    for p in g.players:
        big, small = g.card(p)
        assert isinstance(big, str) and isinstance(small, str)
    assert isinstance(g.hint(), str)
