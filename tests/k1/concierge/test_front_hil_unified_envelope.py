"""Front HIL unified envelope adapter tests (E1.M2.1)."""

from __future__ import annotations

import time
from typing import Any

import pytest

from k1.concierge.actors.front_hil_envelope import (
    build_hil_response_envelope_dict,
    is_new_hil_envelope,
    unwrap_hil_request_payload,
)
from k1.hil.types import (
    CapabilityContractView,
    CapabilityGateRequest,
    HILEnvelope,
    HILKind,
    HILResponseEnvelope,
)


def _env(kind: HILKind, inner: dict[str, Any]) -> dict[str, Any]:
    return HILEnvelope(
        hil_request_id="abc-123",
        kind=kind,
        caller_key=f"{kind.value}:c",
        trace_id="t",
        created_at_ms=int(time.time() * 1000),
        timeout_ms=60_000,
        payload=inner,
    ).to_dict()


# ---------------------------------------------------------------------------
# is_new_hil_envelope
# ---------------------------------------------------------------------------


def test_is_new_envelope_true_on_full_envelope() -> None:
    assert is_new_hil_envelope(_env(HILKind.CLARIFICATION, {"question": "q"}))


def test_is_new_envelope_false_on_legacy_payload() -> None:
    legacy = {"hil_type": "clarification", "question": "q", "options": []}
    assert not is_new_hil_envelope(legacy)


def test_is_new_envelope_false_on_partial() -> None:
    assert not is_new_hil_envelope(
        {"hil_request_id": "x", "kind": "clarification"}
    )  # missing payload


def test_is_new_envelope_false_on_non_dict() -> None:
    assert not is_new_hil_envelope("not a dict")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# unwrap per kind
# ---------------------------------------------------------------------------


def test_unwrap_clarification_envelope() -> None:
    payload = _env(HILKind.CLARIFICATION, {"question": "What time?"})
    flat = unwrap_hil_request_payload(payload)
    assert flat["hil_type"] == "clarification"
    assert flat["question"] == "What time?"
    assert flat["_hil_envelope"]["hil_request_id"] == "abc-123"


def test_unwrap_approval_envelope_renders_summary_and_side_effects() -> None:
    payload = _env(
        HILKind.APPROVAL,
        {
            "summary": "Run plan X",
            "side_effects": ["delete file", "send email"],
            "options": [{"label": "ok"}],
        },
    )
    flat = unwrap_hil_request_payload(payload)
    assert flat["hil_type"] == "approval"
    assert "Run plan X" in flat["question"]
    assert "delete file" in flat["question"]
    assert flat["side_effects"] == ["delete file", "send email"]
    assert flat["options"] == [{"label": "ok"}]


def test_unwrap_needs_human_envelope_preserves_inner_hil_type() -> None:
    payload = _env(
        HILKind.NEEDS_HUMAN,
        {
            "hil_type": "selection",
            "question": "pick one",
            "options": [{"label": "A"}, {"label": "B"}],
            "side_effects": ["x"],
        },
    )
    flat = unwrap_hil_request_payload(payload)
    assert flat["hil_type"] == "selection"
    assert flat["question"] == "pick one"
    assert flat["options"] == [{"label": "A"}, {"label": "B"}]


def test_unwrap_override_envelope_renders_unresolved_and_alts() -> None:
    payload = _env(
        HILKind.OVERRIDE,
        {
            "unresolved_capabilities": ["cap.foo"],
            "proposed_alternatives": [{"description": "use cap.bar"}],
        },
    )
    flat = unwrap_hil_request_payload(payload)
    assert flat["hil_type"] == "override"
    assert "cap.foo" in flat["question"]
    assert "use cap.bar" in flat["question"]


def test_unwrap_capability_gate_envelope_renders_question() -> None:
    req = CapabilityGateRequest(
        caller_key="fabric:cap.x",
        trace_id="t",
        capability_name="unlock_door",
        contract=CapabilityContractView(
            name="cap.x",
            safety_band_min="AMBER",
            requires_human_confirmation=None,
            side_effects=[{"kind": "physical_actuation"}],
        ),
        params={"door": "front"},
        params_summary="front door",
    )
    inner = {
        "capability_name": req.capability_name,
        "contract": {
            "name": req.contract.name,
            "safety_band_min": req.contract.safety_band_min,
            "requires_human_confirmation": req.contract.requires_human_confirmation,
            "side_effects": list(req.contract.side_effects),
            "description": req.contract.description,
        },
        "params": dict(req.params),
        "params_summary": req.params_summary,
    }
    payload = _env(HILKind.CAPABILITY_GATE, inner)
    flat = unwrap_hil_request_payload(payload)
    assert flat["hil_type"] == "capability_gate"
    assert "unlock_door" in flat["question"]
    assert "front door" in flat["question"]
    assert flat["side_effects"] == [{"kind": "physical_actuation"}]


# ---------------------------------------------------------------------------
# legacy fallback
# ---------------------------------------------------------------------------


def test_unwrap_legacy_payload_returns_unchanged() -> None:
    legacy = {
        "hil_type": "clarification",
        "question": "?",
        "options": [{"label": "A"}],
        "side_effects": [],
    }
    flat = unwrap_hil_request_payload(legacy)
    assert flat == legacy
    assert "_hil_envelope" not in flat


# ---------------------------------------------------------------------------
# build_hil_response_envelope_dict
# ---------------------------------------------------------------------------


def test_build_response_envelope_clarification() -> None:
    incoming = _env(HILKind.CLARIFICATION, {"question": "q"})
    resolution = {"additional_info": "tomorrow"}
    out = build_hil_response_envelope_dict(incoming, resolution)
    assert out["hil_request_id"] == "abc-123"
    assert out["kind"] == "clarification"
    assert out["payload"]["answer"] == "tomorrow"
    assert out["timed_out"] is False


def test_build_response_envelope_approval_decision_from_approval_flag() -> None:
    incoming = _env(HILKind.APPROVAL, {"summary": "s"})
    out = build_hil_response_envelope_dict(incoming, {"approval": True})
    assert out["payload"]["decision"] == "approve"
    out2 = build_hil_response_envelope_dict(incoming, {"approval": False})
    assert out2["payload"]["decision"] == "reject"


def test_build_response_envelope_needs_human_carries_resolution() -> None:
    incoming = _env(HILKind.NEEDS_HUMAN, {"question": "q"})
    out = build_hil_response_envelope_dict(
        incoming,
        {"selected_option": "ok", "additional_info": "yep"},
        raw_user_text="raw",
    )
    assert out["payload"]["decision"] == "ok"
    assert out["payload"]["resolution"]["additional_info"] == "yep"
    assert out["payload"]["raw_user_text"] == "raw"


def test_build_response_envelope_override_choice() -> None:
    incoming = _env(HILKind.OVERRIDE, {})
    out = build_hil_response_envelope_dict(
        incoming, {"selected_option": "fallback", "target": {"name": "alt"}}
    )
    assert out["payload"]["choice"] == "fallback"
    assert out["payload"]["selected_alternative"] == {"name": "alt"}


def test_build_response_envelope_capability_gate_approved() -> None:
    incoming = _env(HILKind.CAPABILITY_GATE, {"capability_name": "x"})
    out = build_hil_response_envelope_dict(incoming, {"approval": True})
    assert out["payload"]["approved"] is True
    out2 = build_hil_response_envelope_dict(incoming, {"selected_option": "approve"})
    assert out2["payload"]["approved"] is True
    out3 = build_hil_response_envelope_dict(incoming, {"selected_option": "reject"})
    assert out3["payload"]["approved"] is False


def test_build_response_envelope_round_trip_via_dataclass() -> None:
    incoming = _env(HILKind.CLARIFICATION, {"question": "q"})
    out = build_hil_response_envelope_dict(incoming, {"additional_info": "x"})
    parsed = HILResponseEnvelope.from_dict(out)
    assert parsed.hil_request_id == "abc-123"
    assert parsed.kind is HILKind.CLARIFICATION


def test_build_response_envelope_invalid_envelope_raises() -> None:
    with pytest.raises(ValueError):
        build_hil_response_envelope_dict({"hil_request_id": "x"}, {})


# ---------------------------------------------------------------------------
# Front _extract_scenario_data integration (HITL_RELAY)
# ---------------------------------------------------------------------------


def test_extract_scenario_data_hitl_relay_unwraps_new_envelope() -> None:
    import json as _json

    from k1.bus.envelope.envelope import Envelope
    from k1.concierge.actors.front import PromptMode, _extract_scenario_data

    payload = _env(
        HILKind.APPROVAL,
        {"summary": "Run plan", "side_effects": ["e1"], "options": [{"label": "ok"}]},
    )
    env = Envelope(topic="k1.hil.request.v1", payload=_json.dumps(payload).encode())
    out = _extract_scenario_data(PromptMode.HITL_RELAY, env, ss=None)
    assert out["hil_type"] == "approval"
    assert "Run plan" in out["hil_question"]
    assert out["hil_options"] == [{"label": "ok"}]
    assert out["hil_side_effects"] == ["e1"]
    assert out["_hil_envelope"]["hil_request_id"] == "abc-123"


def test_extract_scenario_data_hitl_relay_legacy_payload_still_works() -> None:
    import json as _json

    from k1.bus.envelope.envelope import Envelope
    from k1.concierge.actors.front import PromptMode, _extract_scenario_data

    legacy = {
        "hil_type": "clarification",
        "question": "?",
        "options": [],
        "side_effects": [],
    }
    env = Envelope(topic="k1.hil.request.v1", payload=_json.dumps(legacy).encode())
    out = _extract_scenario_data(PromptMode.HITL_RELAY, env, ss=None)
    assert out["hil_type"] == "clarification"
    assert out["hil_question"] == "?"
    assert out["_hil_envelope"] is None
