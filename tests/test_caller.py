"""Caller (voice) and 180 flash: python -m pytest tests/test_caller.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dartvision.caller import TurnWatcher, Speaker, number_words, phrase, find_engine  # noqa: E402
from dartvision.games import X01, Cricket, CountUp  # noqa: E402
from dartvision.lights import Lights  # noqa: E402

T20, S20, D20, S1 = ("T20", 60), ("S20", 20), ("D20", 40), ("S1", 1)


def said(w, g):
    return [phrase(e) for e in w.observe(g)]


def throw(g, *darts):
    for d in darts:
        g.add_dart(*d)


def test_number_words():
    assert number_words(180) == "one hundred and eighty"
    assert number_words(100) == "one hundred"
    assert number_words(26) == "twenty six"
    assert number_words(40) == "forty"
    assert number_words(105) == "one hundred and five"
    assert number_words(13) == "thirteen"


def test_game_on_then_score_after_third_dart():
    g, w = X01(["Dave", "Sam"]), TurnWatcher()
    assert said(w, g) == ["Dave to throw first. Game on!"]
    throw(g, T20, T20)
    assert said(w, g) == []                        # nothing until the turn is done
    throw(g, T20)
    evs = w.observe(g)
    assert [phrase(e) for e in evs] == ["One hundred and eighty!"]
    assert evs[0]["flash"]
    assert said(w, g) == []                        # said once
    g.next_player()
    assert said(w, g) == []                        # darts pulled: already called


def test_low_scores_no_score_and_no_flash():
    g, w = X01(["Dave"]), TurnWatcher()
    w.observe(g)
    throw(g, ("MISS", 0), ("MISS", 0), ("MISS", 0))
    evs = w.observe(g)
    assert [phrase(e) for e in evs] == ["No score"] and not evs[0]["flash"]
    g.next_player()
    throw(g, T20, S20, ("S5", 5))
    assert said(w, g) == ["Eighty five"]


def test_darts_pulled_early_still_called():
    g, w = X01(["Dave", "Sam"]), TurnWatcher()
    w.observe(g)
    throw(g, T20, T20)
    g.next_player()                                # only two darts thrown
    assert said(w, g) == ["One hundred and twenty"]


def test_corrected_third_dart_is_called_again():
    g, w = X01(["Dave"]), TurnWatcher()
    w.observe(g)
    throw(g, T20, T20, S20)
    assert said(w, g) == ["One hundred and forty"]
    g.set_dart(2, *T20)
    evs = w.observe(g)
    assert [phrase(e) for e in evs] == ["One hundred and eighty!"] and evs[0]["flash"]


def test_require_bust_and_game_shot():
    g, w = X01(["Dave", "Sam"], start=101), TurnWatcher()
    w.observe(g)
    throw(g, T20, S1)                              # 40 left
    g.next_player()
    assert said(w, g) == ["Sixty one", "Sam, you require one hundred and one"]
    throw(g, T20, T20)                             # Sam busts
    assert said(w, g) == ["Bust"]
    g.next_player()
    assert said(w, g) == ["Dave, you require forty"]
    throw(g, D20)
    assert said(w, g) == ["Game shot, and the match!"]


def test_game_shot_for_the_leg_then_next_leg():
    g, w = X01(["Dave", "Sam"], start=40, legs_to_win=2), TurnWatcher()
    assert said(w, g) == ["Dave to throw first. Game on!", "Dave, you require forty"]
    throw(g, D20)
    assert said(w, g) == ["Game shot, and the leg!"]
    g.next_leg()
    assert said(w, g) == ["Sam to throw first. Game on!", "Sam, you require forty"]


def test_cricket_calls_only_the_win():
    g, w = Cricket(["Dave", "Sam"]), TurnWatcher()
    w.observe(g)
    throw(g, T20, T20, T20)
    assert said(w, g) == []


def test_count_up_last_round_called_then_winner():
    g, w = CountUp(["Dave"]), TurnWatcher()
    w.observe(g)
    for r in range(CountUp.ROUNDS):
        throw(g, T20, T20, T20)
        assert said(w, g) == ["One hundred and eighty!"]
        g.next_player()
    assert said(w, g) == ["Dave wins the match!"]


def test_new_game_starts_fresh():
    w = TurnWatcher()
    g = X01(["Dave"])
    w.observe(g)
    assert w.observe(None) == []
    assert said(w, X01(["Sam"])) == ["Sam to throw first. Game on!"]


# ------------------------------------------------------------------- speaking
def test_speaker_runs_the_engine_in_the_background():
    import threading
    done, got = threading.Event(), []
    sp = Speaker("auto", runner=lambda argv: (got.append(argv), done.set()))
    if not sp.available:                           # no speech program on this machine
        sp.cmd = lambda t: ["fake-say", t]
        import threading as th
        th.Thread(target=sp._run, daemon=True).start()
    sp.say("Bust")
    assert done.wait(5)
    assert got[0][-1].endswith("Bust") or "Bust" in got[0][-1]


def test_engine_off():
    assert find_engine("off") is None
    assert not Speaker("off").available


# -------------------------------------------------------------------- lights
def test_lights_flash_and_end_on():
    seen = []
    li = Lights({"flashes": 3, "interval": 0}, switch=seen.append, sleep=lambda s: None)
    assert li.flash_now()
    assert seen == [0.0, 1.0] * 3 + [1.0]


def test_lights_go_back_to_dimmed_level():
    seen = []
    li = Lights({"flashes": 1, "interval": 0, "brightness": 0.4}, switch=seen.append, sleep=lambda s: None)
    li.flash_now()
    assert seen == [0.0, 1.0, 0.4]
    li.set_level(2)                                # clamped
    assert seen[-1] == 1.0


def test_lights_survive_a_broken_switch():
    def bad(on):
        raise OSError("plug not answering")
    assert Lights({"flashes": 2, "interval": 0}, switch=bad, sleep=lambda s: None).flash_now()


def test_no_lights_configured():
    li = Lights({"type": "none"})
    assert not li.enabled and not li.flash_now()


def test_http_lights_need_both_urls():
    assert not Lights({"type": "http", "on_url": "http://x/on"}).enabled
    assert Lights({"type": "http", "on_url": "http://x/on", "off_url": "http://x/off"}).enabled
