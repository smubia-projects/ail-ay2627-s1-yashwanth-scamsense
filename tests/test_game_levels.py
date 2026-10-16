"""Structural checks on the authored game levels (game/levels.js). Needs Node; skipped if it isn't installed."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

GAME = Path(__file__).resolve().parent.parent / "game"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _levels():
    js = (GAME / "levels.js").read_text(encoding="utf-8") + "\nprocess.stdout.write(JSON.stringify({LEVELS, TYPOLOGY_NAMES}));"
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True, encoding="utf-8").stdout
    return json.loads(out)


def test_levels_structurally_sound():
    data = _levels()
    levels, typ = data["LEVELS"], data["TYPOLOGY_NAMES"]
    assert len(levels) >= 6
    from pipeline.retrieve import load_typologies
    kb = set(load_typologies())
    for L in levels:
        ids = [c["id"] for c in L["chats"]]
        assert len(ids) == len(set(ids)), L["name"]
        assert any(c["truth"] == "scam" for c in L["chats"]) and any(c["truth"] == "legit" for c in L["chats"]), L["name"]
        gos, starts = set(), 0
        for c in L["chats"]:
            assert c["truth"] in ("scam", "legit") and c["explain"] and c["typology"] in typ
            if c["typology"] != "legit":
                assert c["typology"] in kb, c["typology"]          # game uses the same typology ids as the KB
            starts += c.get("start") is not None
            for step in c["script"]:
                if isinstance(step, dict) and "go" in step:
                    assert step["go"] in ids, (L["name"], step["go"])
                    gos.add(step["go"])
                if isinstance(step, dict) and "c" in step:
                    assert any(o.get("ok") for o in step["c"]), "every choice needs at least one good option"
                    assert any(not o.get("ok") for o in step["c"]) or c["truth"] == "legit"
                    if step.get("timer"):
                        assert 0 <= step.get("def", 0) < len(step["c"])
        # every chat is reachable: either starts on a timer or is the target of a handoff
        for c in L["chats"]:
            assert c.get("start") is not None or c["id"] in gos, (L["name"], c["id"])
        assert starts >= 1


def test_scam_chats_have_red_flags_and_legit_chats_do_not():
    for L in _levels()["LEVELS"]:
        for c in L["chats"]:
            text = json.dumps([s for s in c["script"] if isinstance(s, str)])
            if c["truth"] == "scam":
                assert "{{" in text, (L["name"], c["id"])
            else:
                assert "{{" not in text, (L["name"], c["id"])
