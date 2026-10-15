import pytest
from pydantic import ValidationError

from pipeline.schemas import ReasoningResult, Verdict, Report, ExtractionResult


def test_verdict_enum_has_no_safe():
    values = {v.value for v in Verdict}
    assert values == {"Likely scam", "Suspicious", "Can't tell"}
    assert not any("safe" in v.lower() or "legit" in v.lower() for v in values)


@pytest.mark.parametrize("bad", ["Safe", "safe", "Legitimate", "Not a scam", "Looks fine", "", None])
def test_reasoning_rejects_safe_like_verdicts(bad):
    with pytest.raises(ValidationError):
        ReasoningResult.model_validate({"verdict": bad, "confidence": 0.9, "reason": "x"})


def test_reasoning_accepts_valid():
    r = ReasoningResult.model_validate({"verdict": "Likely scam", "confidence": "0.8", "reason": "x"})
    assert r.verdict is Verdict.LIKELY_SCAM and r.confidence == 0.8


def test_report_rejects_bad_verdict():
    with pytest.raises(ValidationError):
        Report.model_validate({"verdict": "Safe", "confidence": 1, "reason": "x"})


def test_extraction_tolerates_unknown_tactics():
    e = ExtractionResult.model_validate({"messages": [{"idx": 0, "tactics": ["urgency", "made_up"], "payment_method": "bitcoin?"}]})
    assert [t.value for t in e.messages[0].tactics] == ["urgency"]
    assert e.messages[0].payment_method.value == "other"
