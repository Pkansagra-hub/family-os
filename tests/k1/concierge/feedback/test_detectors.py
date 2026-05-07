"""K1 detector unit tests (MS-3e Epic 3e.2).

Real detectors, real regex, real similarity math — no mocks.
Three detectors × accept + reject fixtures.
"""

from __future__ import annotations

import pytest

from k1.concierge.feedback.context import ConversationContext
from k1.concierge.feedback.detectors import (
    CorrectionDetector,
    ReformulationDetector,
    ValidationDetector,
)

# ---------------------------------------------------------------------------
# CorrectionDetector
# ---------------------------------------------------------------------------


@pytest.fixture
def ctx() -> ConversationContext:
    return ConversationContext(
        session_id="sess-test",
        last_bot_response="You had coffee with Rachel on Tuesday.",
        grounded_event_ids=["evt-1"],
        response_id="resp-1",
    )


@pytest.mark.parametrize(
    "utterance",
    [
        "no, I actually had tea, not coffee",
        "actually it was Wednesday not Tuesday",
        "tea, not coffee",
        "that's wrong",
        "you got it wrong",
        "I never said it was Rachel",
    ],
)
def test_correction_detector_accepts_correction_phrasings(
    utterance: str, ctx: ConversationContext
) -> None:
    sig = CorrectionDetector().detect(utterance, context=ctx)
    assert sig is not None, f"expected correction signal for: {utterance!r}"
    assert sig.pipeline_id == "P02"
    assert sig.signal_class == "CORRECTION"
    assert sig.confidence > 0.0
    # Pattern indices walk strongest-first; high-confidence patterns get idx 0
    assert 0 <= sig.matched_pattern_index <= 3


@pytest.mark.parametrize(
    "utterance",
    [
        "what's the weather today",
        "tell me about my recent meetings",
        "thanks!",
        "yes, that's helpful",
        "",
        "   ",
    ],
)
def test_correction_detector_rejects_non_correction(
    utterance: str, ctx: ConversationContext
) -> None:
    assert CorrectionDetector().detect(utterance, context=ctx) is None


def test_correction_detector_attaches_grounded_event_id_as_target() -> None:
    ctx = ConversationContext(
        session_id="s1",
        grounded_event_ids=["evt-42", "evt-43"],
        last_bot_response="prior",
    )
    sig = CorrectionDetector().detect("no, it was tea, not coffee", context=ctx)
    assert sig is not None
    assert sig.target_event_id == "evt-42"
    assert sig.correction_target == "memory"


def test_correction_detector_falls_back_to_response_target_without_grounding() -> None:
    ctx = ConversationContext(session_id="s1", last_bot_response="prior")
    sig = CorrectionDetector().detect("that's wrong", context=ctx)
    assert sig is not None
    assert sig.correction_target == "response"
    assert sig.target_event_id is None


# ---------------------------------------------------------------------------
# ValidationDetector
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "utterance,polarity",
    [
        ("yes, that's right", "positive"),
        ("yep!", "positive"),
        ("thanks", "positive"),
        ("perfect", "positive"),
        ("you got it right", "positive"),
        ("no", "negative"),
        ("nope", "negative"),
        ("that's wrong", "negative"),
        ("you got that wrong", "negative"),
        ("not quite", "negative"),
    ],
)
def test_validation_detector_polarities(utterance: str, polarity: str) -> None:
    ctx = ConversationContext(
        session_id="s",
        response_id="r",
        grounded_event_ids=["evt-1"],
    )
    sig = ValidationDetector().detect(utterance, context=ctx)
    assert sig is not None, f"expected validation for {utterance!r}"
    assert sig.pipeline_id == "P08"
    assert sig.signal_class == "VALIDATION"
    assert sig.polarity == polarity
    assert sig.target_response_id == "r"
    assert sig.target_event_ids == ("evt-1",)


@pytest.mark.parametrize(
    "utterance",
    [
        "what's the weather",
        "tell me more",
        "could you explain",
        "",
        "let's talk about meetings",
    ],
)
def test_validation_detector_rejects_neutral(utterance: str) -> None:
    assert ValidationDetector().detect(utterance) is None


# ---------------------------------------------------------------------------
# ReformulationDetector
# ---------------------------------------------------------------------------


def test_reformulation_detected_when_partial_overlap() -> None:
    ctx = ConversationContext(
        session_id="s",
        last_user_message="show me my meetings with Rachel last Tuesday",
        response_id="r-1",
        grounded_event_ids=["evt-1"],
    )
    sig = ReformulationDetector().detect("tell me about meetings Rachel Tuesday", context=ctx)
    assert sig is not None
    assert sig.pipeline_id == "P03"
    assert sig.signal_class == "IMPLICIT"
    assert 0.30 < sig.similarity < 0.85
    assert 0.0 <= sig.confidence <= 1.0
    assert sig.target_response_id == "r-1"


def test_reformulation_rejected_for_verbatim_repeat() -> None:
    ctx = ConversationContext(
        session_id="s",
        last_user_message="who did I meet on Tuesday afternoon",
    )
    # Identical -> similarity == 1.0 > hi (0.85) -> reject.
    sig = ReformulationDetector().detect("who did I meet on Tuesday afternoon", context=ctx)
    assert sig is None


def test_reformulation_rejected_for_brand_new_topic() -> None:
    ctx = ConversationContext(
        session_id="s",
        last_user_message="who did I meet on Tuesday afternoon",
    )
    # No content overlap (after stopword removal) -> below lo band -> reject.
    sig = ReformulationDetector().detect("recipe for sourdough bread", context=ctx)
    assert sig is None


def test_reformulation_rejected_without_prior_message() -> None:
    ctx = ConversationContext(session_id="s")  # no last_user_message
    sig = ReformulationDetector().detect("who did I meet Tuesday", context=ctx)
    assert sig is None


def test_reformulation_band_validates_constructor() -> None:
    with pytest.raises(ValueError):
        ReformulationDetector(similarity_low=0.9, similarity_high=0.5)
    with pytest.raises(ValueError):
        ReformulationDetector(similarity_low=-0.1, similarity_high=0.5)
