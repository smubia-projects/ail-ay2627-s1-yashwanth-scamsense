from collections import Counter

from bot import practice
from pipeline.retrieve import load_typologies


def test_scenarios_well_formed():
    sc = practice.load_scenarios()
    assert 10 <= len(sc) <= 15
    assert sum(1 for s in sc if s.get("multiparty")) >= 3
    assert len({s["id"] for s in sc}) == len(sc)
    typs = load_typologies()
    for s in sc:
        assert s["typology_id"] in typs, s["id"]
        assert s["messages"] and s["explanation"]
        ids = [o["id"] for o in s["options"]]
        assert len(ids) == len(set(ids))
        correct = [o for o in s["options"] if o["correct"]]
        if s.get("genuine"):
            assert not correct
        else:
            assert len(correct) >= 3 and len(correct) < len(s["options"])


def test_scenarios_cover_all_typologies():
    covered = {s["typology_id"] for s in practice.load_scenarios()}
    assert covered >= set(load_typologies())


def test_scoring():
    s = {"options": [{"id": "a", "label": "A", "correct": True}, {"id": "b", "label": "B", "correct": True},
                     {"id": "c", "label": "C", "correct": False}]}
    assert practice.score(s, {"a", "b"})[:2] == (2, 2)
    pts, mx, missed, wrong = practice.score(s, {"a", "c"})
    assert (pts, mx, missed, wrong) == (0, 2, ["B"], ["C"])
    assert practice.score(s, set())[0] == 0           # floored, never negative
    assert practice.score(s, {"c"})[0] == 0


def test_genuine_scenario_scoring():
    g = next(s for s in practice.load_scenarios() if s.get("genuine"))
    assert practice.score(g, set())[0] == 0 and practice.score(g, set())[2] == []
    assert practice.score(g, {g["options"][0]["id"]})[3]  # tapping a non-flag is reported as wrong


def test_render_scenario_has_all_options():
    scen = practice.load_scenarios()[0]
    st = {"opts": list(range(len(scen["options"]))), "sel": {0}, "pts": 0, "max": 0, "done": 0}
    text, kb = practice.render_scenario(scen, st)
    assert "red flag" in text
    assert len(kb.inline_keyboard) == len(scen["options"]) + 1
