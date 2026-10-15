"""Pydantic schemas for every structured boundary in the pipeline.

The verdict enum deliberately has no "safe"/"legitimate" member: the never-safe rule is
enforced by the type system and re-checked on the way out (see verdict.py).
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Verdict(str, Enum):
    LIKELY_SCAM = "Likely scam"
    SUSPICIOUS = "Suspicious"
    CANT_TELL = "Can't tell"

    @property
    def rank(self) -> int:
        return {"Likely scam": 2, "Suspicious": 1, "Can't tell": 0}[self.value]


class Tactic(str, Enum):
    URGENCY = "urgency"
    AUTHORITY = "authority"
    FEAR = "fear"
    REWARD = "reward"
    ISOLATION = "isolation"
    CHANNEL_SWITCH = "channel_switch"
    PAYMENT_REQUEST = "payment_request"
    APP_INSTALL = "app_install"
    CREDENTIAL_REQUEST = "credential_request"


class PaymentMethod(str, Enum):
    NONE = "none"
    BANK_TRANSFER = "bank_transfer"
    PAYNOW = "paynow"
    GIFT_CARD = "gift_card"
    CRYPTO = "crypto"
    CASH_HANDOVER = "cash_handover"
    CARD_DETAILS = "card_details"
    OTHER = "other"


class Stage(str, Enum):
    FIRST_CONTACT = "first_contact"
    CLAIMED_AUTHORITY = "claimed_authority"
    URGENCY = "urgency"
    ISOLATION = "isolation"
    CHANNEL_SWITCH = "channel_switch"
    REQUEST = "request"  # payment / credential / app-install request


STAGE_ORDER = list(Stage)


class CrossPartyKind(str, Enum):
    VOUCHING = "vouching"            # one sender vouches for / corroborates another
    HANDOFF = "handoff"              # victim passed to a "higher authority"
    REPEATED_TACTIC = "repeated_tactic"  # same tactic pushed by different senders
    COORDINATED_PRESSURE = "coordinated_pressure"


class InputKind(str, Enum):
    CONVERSATION = "conversation"
    GENERATE_SCAM_REQUEST = "generate_scam_request"  # user asks the bot to write/improve/translate a scam


# ---------------------------------------------------------------- parsing

class Message(BaseModel):
    idx: int
    sender: str
    text: str
    inferred_sender: bool = False


# ---------------------------------------------------------------- extraction (LLM #1)

class MessageAnnotation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    idx: int
    sender: str | None = None            # only used when the LLM had to segment unlabeled text
    text: str | None = None              # only used when the LLM had to segment unlabeled text
    claimed_identity: str | None = None
    tactics: list[Tactic] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    payment_method: PaymentMethod = PaymentMethod.NONE
    quote: str | None = None             # short verbatim evidence from the message

    @field_validator("tactics", mode="before")
    @classmethod
    def _drop_unknown_tactics(cls, v):
        if not isinstance(v, list):
            return []
        valid = {t.value for t in Tactic}
        return [t for t in v if isinstance(t, str) and t in valid]

    @field_validator("payment_method", mode="before")
    @classmethod
    def _coerce_payment(cls, v):
        valid = {p.value for p in PaymentMethod}
        if v is None:
            return "none"
        return v if v in valid else "other"


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    input_kind: InputKind = InputKind.CONVERSATION
    speakers_inferred: bool = False
    messages: list[MessageAnnotation] = Field(default_factory=list)

    @field_validator("input_kind", mode="before")
    @classmethod
    def _coerce_kind(cls, v):
        return v if v in {k.value for k in InputKind} else "conversation"


# ---------------------------------------------------------------- deterministic rules

class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RuleHit(BaseModel):
    rule_id: str
    message_idx: int | None = None
    severity: Severity
    description: str
    evidence: str = ""


# ---------------------------------------------------------------- stage reasoning (LLM #2)

class StageDetection(BaseModel):
    model_config = ConfigDict(extra="ignore")
    stage: Stage
    present: bool
    message_idxs: list[int] = Field(default_factory=list)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    note: str = ""

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp(cls, v):
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.0


class CrossPartySignal(BaseModel):
    model_config = ConfigDict(extra="ignore")
    kind: CrossPartyKind
    message_idxs: list[int] = Field(default_factory=list)
    description: str = ""


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    message_idx: int
    quote: str
    why: str = ""


class ReasoningResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    verdict: Verdict
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    stages: list[StageDetection] = Field(default_factory=list)
    cross_party: list[CrossPartySignal] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    typology_id: str | None = None

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp(cls, v):
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.0

    @field_validator("verdict", mode="before")
    @classmethod
    def _verdict_must_be_allowed(cls, v):
        # Anything outside the 3-value enum (e.g. "Safe", "Legitimate") is rejected by pydantic
        # -> counts as invalid JSON -> retry -> "Can't tell". This is the never-safe rule.
        return v


# ---------------------------------------------------------------- final report

class Typology(BaseModel):
    id: str
    name: str
    summary: str
    typical_flow: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    what_to_do: list[str] = Field(default_factory=list)
    verified: bool = False


class Report(BaseModel):
    verdict: Verdict
    confidence: float
    reason: str
    messages: list[Message] = Field(default_factory=list)
    annotations: list[MessageAnnotation] = Field(default_factory=list)
    rule_hits: list[RuleHit] = Field(default_factory=list)
    stages: list[StageDetection] = Field(default_factory=list)
    cross_party: list[CrossPartySignal] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    typology: Typology | None = None
    notes: list[str] = Field(default_factory=list)       # honest caveats: degraded mode, inferred speakers...
    speakers_inferred: bool = False
    degraded: bool = False                               # LLM failed -> fallback
    refused: bool = False                                # abuse refusal
    injection_detected: bool = False
    redaction_counts: dict[str, int] = Field(default_factory=dict)
    latency_s: float = 0.0
    calibration: list[str] = Field(default_factory=list)  # human-readable log of verdict adjustments

    @field_validator("verdict")
    @classmethod
    def _never_safe(cls, v):
        if v not in set(Verdict):
            raise ValueError("verdict outside allowed enum")
        return v
