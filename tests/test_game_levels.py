"""Structural checks on the authored game cases (game/levels.js). Needs Node; skipped if it isn't installed."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

GAME = Path(__file__).resolve().parent.parent / "game"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    js = (GAME / "levels.js").read_text(encoding="utf-8") + (
        "\nprocess.stdout.write(JSON.stringify({LEVELS, STYLES, TYPOLOGY_NAMES, INTENT_IDS: Object.keys(INTENTS), ORDER: INTENT_ORDER}));")
    f = tmp_path_factory.mktemp("levels") / "dump.js"
    f.write_text(js, encoding="utf-8")
    out = subprocess.run(["node", str(f)], capture_output=True, text=True, check=True, encoding="utf-8").stdout
    return json.loads(out)


def merged(chat, spec, styles):
    st = styles[chat.get("style", "business")]
    strip = lambda d: {k: v for k, v in (d or {}).items() if v}  # noqa: E731
    return {"vars": {**st.get("vars", {}), **spec.get("vars", {})}, "replies": {**st.get("replies", {}), **spec.get("replies", {})},
            "tells": strip({**st.get("tells", {}), **spec.get("tells", {})}), "clears": strip({**st.get("clears", {}), **spec.get("clears", {})})}


def open_spec(chat):
    specs = [s["open"] for s in chat["script"] if isinstance(s, dict) and "open" in s]
    assert len(specs) == 1, f"{chat['id']} needs exactly one open conversation"
    return specs[0]


def gos(node):
    if isinstance(node, list):
        return {g for x in node for g in gos(x)}
    if isinstance(node, dict):
        return ({node["go"]} if "go" in node else set()) | {g for v in node.values() for g in gos(v)}
    return set()


def test_no_timers_and_no_multiple_choice(data):
    blob = json.dumps(data["LEVELS"])
    assert '"timer"' not in blob and '"timed"' not in blob, "timers were removed on purpose"
    assert '"c":' not in blob, "cases are typed investigation, not multiple choice"


def test_cases_are_organised_and_complete(data):
    from pipeline.retrieve import load_typologies
    kb, ids = set(load_typologies()), set(data["INTENT_IDS"])
    levels = data["LEVELS"]
    assert len(levels) >= 6
    assert [l["diff"] for l in levels][0] == "easy" and levels[-1]["diff"] == "expert"
    for L in levels:
        assert L["briefing"] and L["debrief"] and len(L["life"]) >= 3, L["name"]
        cid = [c["id"] for c in L["chats"]]
        assert len(cid) == len(set(cid))
        scam = [c for c in L["chats"] if c["truth"] == "scam"]
        legit = [c for c in L["chats"] if c["truth"] == "legit"]
        assert len(scam) >= 3 and len(legit) >= 1, f"{L['name']}: one organised ring + at least one genuine contact"
        assert len({c["group"] for c in scam if c["group"] == "ring"}) == 1 and sum(c["group"] == "ring" for c in scam) >= 3, "ring members share a group"
        reachable = gos([c["script"] for c in L["chats"]])
        for c in L["chats"]:
            assert c["explain"] and c["style"] in data["STYLES"]
            assert c["typology"] == "legit" or c["typology"] in kb
            assert c.get("start") is not None or c["id"] in reachable, (L["name"], c["id"], "unreachable")
        for c in scam:  # the ring starts small and is handed along, not 5 random contacts at once
            assert c.get("start") is not None or c["id"] in reachable


def test_open_specs_valid_and_placeholders_resolved(data):
    ids = set(data["INTENT_IDS"])
    for L in data["LEVELS"]:
        for c in L["chats"]:
            spec = open_spec(c)
            m = merged(c, spec, data["STYLES"])
            assert spec["budget"] >= 4
            assert set(m["replies"]) <= ids | {"_all"}, (c["id"], set(m["replies"]) - ids)
            assert set(m["tells"]) <= ids and set(m["clears"]) <= ids
            assert set(spec.get("loss", {})) <= {"comply_pay", "comply_cred", "comply_install"}
            for n in spec.get("events", {}):
                assert 1 <= int(n) <= spec["budget"], (c["id"], n)
            # every {placeholder} in every reply must have a value (else the player would see blanks)
            for intent, replies in m["replies"].items():
                for r in replies:
                    text = r["m"] if isinstance(r, dict) else r
                    for var in re.findall(r"\{(\w+)\}", text):
                        assert var in m["vars"], f"{L['name']}/{c['id']}: reply '{intent}' uses undefined {{{var}}}"
            if c["truth"] == "scam":
                assert len(m["tells"]) >= 2, f"{c['id']}: a scammer must leak at least two tells when questioned"
                if "bot" not in c["style"]:
                    assert spec.get("loss"), f"{c['id']}: falling for it must cost something"
            else:
                assert len(m["clears"]) >= 2, f"{c['id']}: a genuine sender must welcome verification"
                assert "{{" not in json.dumps([s for s in c["script"] if isinstance(s, str)]), "genuine messages carry no red flags"
                assert not spec.get("loss")


def test_scam_pitches_have_red_flags_to_tap(data):
    for L in data["LEVELS"]:
        for c in L["chats"]:
            pitch = json.dumps([s for s in c["script"] if isinstance(s, str)])
            if c["truth"] == "scam" and c["style"] != "friendly":
                assert "{{" in pitch, (L["name"], c["id"])


def test_cross_party_contradictions_exist_in_hard_cases(data):
    """Hard cases plant inconsistencies between ring members (the multi-party insight)."""
    def facts(node):
        out = []
        if isinstance(node, list):
            for x in node:
                out += facts(x)
        elif isinstance(node, dict):
            if "fact" in node:
                out.append(tuple(node["fact"][:2]))
            for v in node.values():
                out += facts(v)
        return out

    with_contradiction = 0
    for L in data["LEVELS"]:
        by_key = {}
        for c in L["chats"]:
            for k, v in facts(c["script"]):
                by_key.setdefault((c["group"], k), set()).add(v)
        if any(len(v) >= 2 for v in by_key.values()):
            with_contradiction += 1
    assert with_contradiction >= 4
