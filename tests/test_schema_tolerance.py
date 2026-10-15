"""Tolerance for realistic model quirks - while the never-safe rule still holds."""
import pytest
from pydantic import ValidationError

from pipeline.schemas import ReasoningResult, Verdict


@pytest.mark.parametrize("raw,expected", [
    ("likely scam", Verdict.LIKELY_SCAM), ("Likely Scam", Verdict.LIKELY_SCAM), ("LIKELY_SCAM", Verdict.LIKELY_SCAM),
    ("suspicious", Verdict.SUSPICIOUS), ("Can’t tell", Verdict.CANT_TELL), ("cant_tell", Verdict.CANT_TELL),
])
def test_verdict_case_and_apostrophe_tolerated(raw, expected):
    assert ReasoningResult.model_validate({"verdict": raw, "confidence": 0.5, "reason": "x"}).verdict is expected


@pytest.mark.parametrize("bad", ["SAFE", "Safe.", "legit", "Not Scam", "likely safe", "Probably legitimate",
                                 "Safe - not a scam", "Legitimate message"])
def test_safe_like_still_rejected_after_normalisation(bad):
    with pytest.raises(ValidationError):
        ReasoningResult.model_validate({"verdict": bad, "confidence": 0.9, "reason": "x"})


def test_malformed_list_items_dropped_not_fatal():
    r = ReasoningResult.model_validate({
        "verdict": "Suspicious", "confidence": "80%", "reason": "x", "typology_id": "none",
        "stages": [{"stage": "Claimed Authority", "present": True, "confidence": "high"}, {"stage": "bogus"}, "junk"],
        "cross_party": [{"kind": "bogus-kind"}, {"kind": "Hand-off", "message_idxs": ["1", 2]}],
        "evidence": [{"message_idx": 0}, {"message_idx": 1, "quote": "hello"}]})
    assert r.confidence == 0.8 and r.typology_id is None
    assert [s.stage.value for s in r.stages] == ["claimed_authority"] and r.stages[0].confidence == 0.85
    assert len(r.cross_party) == 1 and r.cross_party[0].message_idxs == [1, 2]
    assert len(r.evidence) == 1
