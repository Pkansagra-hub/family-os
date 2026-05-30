from __future__ import annotations

from k1.concierge.acking.write_elision import WriteElisionGate


def test_neutral_backchannel_elides_optional_sections() -> None:
    decision = WriteElisionGate().evaluate(
        {
            "intent_class": "backchannel",
            "safety_band": "GREEN",
            "prior_safety_band": "GREEN",
            "beliefs": [],
            "affect_label": "neutral",
            "affect_detected": False,
        }
    )

    assert decision.write_safety_band is True
    assert decision.write_temporal is True
    # M5 G3: neutral backchannel must elide every optional section. Safety
    # band and temporal anchor stay unconditional; only `control`,
    # `intents`, `beliefs`, and `affect` get elided.
    assert decision.elided_sections == {"control", "intents", "beliefs", "affect"}
    assert decision.write_control is False
    assert decision.write_intents is False
    assert decision.write_beliefs is False
    assert decision.write_affect is False


def test_task_request_with_beliefs_writes_semantic_sections() -> None:
    decision = WriteElisionGate().evaluate(
        {
            "intent_class": "task_request",
            "intents": [{"name": "book"}],
            "beliefs": [{"fact": "likes quiet restaurants"}],
        }
    )

    assert decision.write_control is True
    assert decision.write_intents is True
    assert decision.write_beliefs is True


def test_affect_only_backchannel_writes_affect() -> None:
    decision = WriteElisionGate().evaluate(
        {
            "intent_class": "backchannel",
            "affect_label": "sad",
            "affect_detected": True,
        }
    )

    assert decision.write_affect is True
    assert "affect" not in decision.elided_sections


def test_safety_escalation_writes_control() -> None:
    decision = WriteElisionGate().evaluate(
        {
            "intent_class": "backchannel",
            "safety_band": "RED",
            "prior_safety_band": "GREEN",
        }
    )

    assert decision.write_safety_band is True
    assert decision.write_control is True
