"""Web scoreboard / remote: python -m pytest tests/test_web.py
Runs the real HTTP server on a free local port and talks to it like the phone page does.
"""
import json
import os
import sys
import urllib.error
import urllib.request

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dartvision import web  # noqa: E402
from dartvision.menu import Menu  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_state():
    with web._lock:
        web._state.update(v=0, data={})
    web.take_actions()
    yield
    web.take_actions()


@pytest.fixture
def base():
    url = web.start(port=0, host="127.0.0.1")
    assert url
    yield f"http://127.0.0.1:{web.server.server_address[1]}"
    web.stop()


def get(base, path):
    with urllib.request.urlopen(base + path, timeout=5) as r:
        return r.status, r.headers, r.read()


def post(base, path, body):
    req = urllib.request.Request(base + path, data=body if isinstance(body, bytes) else json.dumps(body).encode(),
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def state(base):
    return json.loads(get(base, "/state")[2])


# ------------------------------------------------------------ publish / versions
def test_version_goes_up_only_on_change():
    web.publish({"a": 1})
    assert web.snapshot()["v"] == 1
    web.publish({"a": 1})
    assert web.snapshot()["v"] == 1
    web.publish({"a": 2})
    assert web.snapshot() == {"v": 2, "boot": web.BOOT, "a": 2}


def test_list_changed_in_place_still_bumps_the_version():
    """The bug: the phone's setup screen didn't show a player added on the computer.

    The game loop publishes a dict holding its own players list and then appends to that same
    list. publish() used to keep the reference, so the 'old' state changed too, compared equal,
    and the version (which the phone watches) never went up.
    """
    players = ["Dave"]
    web.publish({"screen": "menu", "menu": {"players": players}})
    v = web.snapshot()["v"]
    players.append("J")
    web.publish({"screen": "menu", "menu": {"players": players}})
    s = web.snapshot()
    assert s["v"] == v + 1
    assert s["menu"]["players"] == ["Dave", "J"]


def test_published_state_is_a_copy():
    turn = [("T20", 60)]
    web.publish({"turn": turn})
    turn.append(("S1", 1))
    assert web.snapshot()["turn"] == [["T20", 60]]


def test_dart_corrected_in_place_bumps_the_version():
    """Same trap during a game: game.turn is changed in place when a dart is corrected."""
    turn = [("T20", 60)]
    web.publish({"screen": "play", "game": {"turn": turn}})
    v = web.snapshot()["v"]
    turn[0] = ("S20", 20)
    web.publish({"screen": "play", "game": {"turn": turn}})
    assert web.snapshot()["v"] == v + 1


# ----------------------------------------------------------------- HTTP server
def test_page_is_served(base):
    code, headers, body = get(base, "/")
    assert code == 200 and headers["Content-Type"].startswith("text/html")
    assert b"<title>dartvision</title>" in body
    assert headers["Cache-Control"] == "no-store"


def test_state_endpoint(base):
    web.publish({"screen": "menu", "status": "hi"})
    s = state(base)
    assert s["screen"] == "menu" and s["status"] == "hi" and s["v"] == 1


def test_unknown_paths(base):
    with pytest.raises(urllib.error.HTTPError) as e:
        get(base, "/nope")
    assert e.value.code == 404
    assert post(base, "/nope", {"type": "x"})[0] == 404


def test_actions_are_queued(base):
    assert post(base, "/action", {"type": "add_player", "name": "J"}) == (200, {"ok": True})
    assert post(base, "/action", {"type": "start"})[0] == 200
    assert web.take_actions() == [{"type": "add_player", "name": "J"}, {"type": "start"}]
    assert web.take_actions() == []


@pytest.mark.parametrize("body", [b"not json", b"[1, 2]", b'{"name": "no type"}', b'{"type": 5}'])
def test_bad_actions_are_refused(base, body):
    assert post(base, "/action", body)[0] == 400
    assert web.take_actions() == []


# --------------------------------------------- the computer and the phone in step
class Loop:
    """The bits of the game loop that matter here: apply web actions, then publish."""

    def __init__(self, players):
        self.menu = Menu(players)
        self.players = self.menu.players          # the window code keeps this same list

    def tick(self):
        for a in web.take_actions():
            self.menu.act(a)
        web.publish({"screen": "menu", "status": "", "menu": self.menu.web_state()})


def test_player_added_on_the_computer_shows_on_the_phone(base):
    loop = Loop(["Dave"])
    loop.tick()
    seen = state(base)
    assert seen["menu"]["players"] == ["Dave"]

    loop.menu.add_player("J")                     # typed on the computer + Enter
    loop.tick()
    now = state(base)
    assert now["v"] > seen["v"], "the phone only redraws when the version changes"
    assert now["menu"]["players"] == ["Dave", "J"]


def test_player_removed_on_the_computer_shows_on_the_phone(base):
    loop = Loop(["Dave", "J"])
    loop.tick()
    v = state(base)["v"]
    loop.players.pop()                            # Backspace on the computer
    loop.tick()
    now = state(base)
    assert now["v"] > v and now["menu"]["players"] == ["Dave"]


def test_options_changed_on_the_computer_show_on_the_phone(base):
    loop = Loop(["Dave"])
    loop.tick()
    v = state(base)["v"]
    loop.menu.change_opt(1, 1)
    loop.menu.change_opt(0, 1)
    loop.tick()
    now = state(base)
    assert now["v"] > v and now["menu"]["mode"] == 1
    assert now["menu"]["opts"][0] == ["Legs", "first to 2"]


def test_player_added_on_the_phone_shows_everywhere(base):
    loop = Loop(["Dave"])
    loop.tick()
    post(base, "/action", {"type": "add_player", "name": "J"})
    loop.tick()
    assert loop.players == ["Dave", "J"]
    assert state(base)["menu"]["players"] == ["Dave", "J"]


def test_two_phones_see_the_same_thing(base):
    loop = Loop(["Dave"])
    loop.tick()
    post(base, "/action", {"type": "add_player", "name": "J"})
    loop.tick()
    assert state(base) == state(base)


# ------------------------------------------------------------ caller voice on the page
def test_page_with_voice_on_takes_over_the_talking(base):
    web._voice_seen["t"] = 0.0
    web.publish({"screen": "menu", "calls": [{"n": 1, "text": "Bust", "flash": False}], "web_voice": True})
    assert not web.voice_listening()
    s = state(base)
    assert s["calls"][0]["text"] == "Bust"
    assert not web.voice_listening()               # a page with its voice off doesn't count
    get(base, "/state?voice=1")
    assert web.voice_listening()


def test_page_has_voice_button_and_flash():
    assert 'class="vbtn"' in web.PAGE and 'id="flash"' in web.PAGE and "speechSynthesis" in web.PAGE


def test_page_has_the_info_bar_and_log(base):
    body = get(base, "/")[2]
    assert b'id="infot"' in body and b'id="logl"' in body and b"renderLog" in body


def test_log_lines_reach_the_phone(base):
    web.publish({"screen": "menu", "log": [[1, "info", "Game on"], [2, "error", "couldn't read that one"]]})
    assert state(base)["log"][-1] == [2, "error", "couldn't read that one"]


# -------------------------------------------------------- the computer goes away
def test_state_carries_a_boot_id(base):
    s = state(base)
    assert s["boot"] == web.BOOT and len(web.BOOT) == 8


def test_clean_quit_tells_the_phone(base):
    import time
    web.publish({"screen": "menu"})
    state(base)                                   # a phone is polling
    t = time.monotonic()
    web.announce_stop(wait=0.3)
    assert time.monotonic() - t >= 0.3            # waited so the phone hears it
    assert state(base)["screen"] == "stopped"


def test_quit_isnt_held_up_with_no_phone_open():
    import time
    web._last_poll["t"] = 0
    t = time.monotonic()
    web.announce_stop(wait=5)
    assert time.monotonic() - t < 1 and web.snapshot()["screen"] == "stopped"


def test_page_handles_lost_connection(base):
    body = get(base, "/")[2]
    assert b'id="lost"' in body and b"Lost connection" in body and b"location.reload" in body
