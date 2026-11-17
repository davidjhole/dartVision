"""Start-screen settings: python -m pytest tests/test_menu.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dartvision.games import X01, Cricket  # noqa: E402
from dartvision.menu import Menu  # noqa: E402


def test_defaults():
    m = Menu()
    assert m.players == ["Player 1"] and m.mode_name == "501"
    assert m.opts() == [("Legs", "single leg"), ("Double out", "yes"), ("Double in", "no")]


def test_players_from_the_command_line():
    assert Menu(["Dave", "James"]).players == ["Dave", "James"]
    assert Menu(["Player 1", "Dave"]).players == ["Dave"]
    assert len(Menu([str(i) for i in range(10)]).players) == 6


def test_start_preselects_a_mode():
    assert Menu(start=301).mode_name == "301"
    assert Menu(start="nonsense").mode_name == "501"


def test_first_name_replaces_the_placeholder():
    m = Menu()
    assert m.add_player("  Dave  ")
    assert m.players == ["Dave"]
    assert m.add_player("J")
    assert m.players == ["Dave", "J"]


def test_add_player_limits():
    m = Menu(["A"])
    assert not m.add_player("   ")
    assert m.add_player("x" * 30) and m.players[-1] == "x" * 14
    for n in "BCDE":
        m.add_player(n)
    assert len(m.players) == 6 and not m.can_add()
    assert not m.add_player("G") and len(m.players) == 6


def test_remove_player():
    m = Menu(["A", "B"])
    assert m.remove_player(0) and m.players == ["B"]
    assert not m.remove_player(5) and not m.remove_player(-1)


def test_players_list_is_changed_in_place():
    """The window code holds on to menu.players, so it must stay the same list."""
    m = Menu(["A"])
    ref = m.players
    m.add_player("B")
    m.act({"type": "remove_player", "i": 0})
    assert ref is m.players and ref == ["B"]


def test_options_cycle():
    m = Menu()
    m.change_opt(1, 1)
    assert m.opt["legs"] == 2 and m.opts()[0] == ("Legs", "first to 2")
    m.change_opt(1, -1)
    m.change_opt(1, -1)
    assert m.opt["legs"] == 7
    m.change_opt(2, 1)
    assert m.opt["double_out"] is False
    m.change_opt(3, 1)
    assert m.opt["double_in"] is True
    m.change_opt(0, -1)
    assert m.mode_name == "Count up (8 rounds)"


def test_cricket_has_no_double_options():
    m = Menu(start="Cricket")
    m.set_mode(3)
    assert m.mode_name == "Cricket" and m.opts() == [("Legs", "single leg")]
    m.change_opt(2, 1)                       # not shown, so it doesn't change
    assert m.opt["double_out"] is True


def test_act_from_the_web_page():
    m = Menu(["Dave"])
    m.act({"type": "add_player", "name": "J"})
    m.act({"type": "mode", "i": 1})
    m.act({"type": "opt", "row": 2, "step": 1})
    assert m.players == ["Dave", "J"] and m.mode_name == "301" and m.opt["double_out"] is False
    assert m.act({"type": "start"}) == "start"
    m.act({"type": "mode", "i": "bad"})      # junk from the page is ignored
    m.act({"type": "remove_player"})
    assert m.mode_name == "301" and len(m.players) == 2


def test_start_needs_a_player():
    m = Menu(["A"])
    m.remove_player(0)
    assert m.act({"type": "start"}) is None


def test_new_game_uses_the_settings():
    m = Menu(["A", "B"], start=301)
    m.change_opt(1, 1)
    m.change_opt(2, 1)
    g = m.new_game()
    assert isinstance(g, X01) and g.start == 301 and g.legs_to_win == 2 and not g.double_out
    assert g.players == ["A", "B"] and g.players is not m.players
    m.set_mode(3)
    assert isinstance(m.new_game(), Cricket)


def test_web_state():
    m = Menu(["Dave"])
    s = m.web_state()
    assert s["players"] == ["Dave"] and s["mode"] == 0 and s["modes"][0] == "501"
    assert s["opts"][0] == ["Legs", "single leg"]
    assert s["players"] is not m.players
