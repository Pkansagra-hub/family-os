"""Front HIL unified envelope adapter tests (E1.M2.1)."""

from __future__ import annotations

import time
from typing import Any

import pytest

from k1.concierge.actors.front_hil_envelope import (
    build_hil_response_envelope_dict,
    is_legacy_bridge_envelope,
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


def test_legacy_bridge_envelope_marker_is_detected() -> None:
    payload = _env(HILKind.NEEDS_HUMAN, {"question": "q", "legacy_bridge": True})
    assert is_legacy_bridge_envelope(payload)


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


def test_build_response_envelope_preserves_legacy_bridge_marker() -> None:
    incoming = _env(HILKind.NEEDS_HUMAN, {"question": "q", "legacy_bridge": True})
    incoming["legacy_bridge"] = True
    out = build_hil_response_envelope_dict(
        incoming,
        {"selected_option": "answered", "additional_info": "Paris"},
        raw_user_text="Paris",
    )
    assert out["payload"]["legacy_bridge"] is True


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


def test_extract_scenario_data_hitl_resolve_returns_hil_metadata() -> None:
    import json as _json

    from k1.bus.envelope.envelope import Envelope
    from k1.concierge.actors.front import PromptMode, _extract_scenario_data

    payload = _env(
        HILKind.APPROVAL,
        {"summary": "Approve plan", "side_effects": ["send email"], "options": []},
    )
    task_state = type(
        "TaskState",
        (),
        {
            "get_all": lambda self: [
                {
                    "task_id": "task-1",
                    "status": "SUSPENDED",
                    "action": "approve something",
                    "pending_hil_data": {"envelope": payload, "hil_request_id": "abc-123"},
                }
            ]
        },
    )()
    ss = type(
        "SS", (), {"get_section": lambda self, name: task_state if name == "task_state" else None}
    )()
    env = Envelope(topic="k1.user.input.v1", payload=_json.dumps({"text": "yes"}).encode())

    out = _extract_scenario_data(PromptMode.HITL_RESOLVE, env, ss=ss)

    assert out["task_id"] == "task-1"
    assert out["pending_hil_id"] == "abc-123"
    assert out["hil_type"] == "approval"
    assert out["hil_side_effects"] == ["send email"]
    assert out["_hil_envelope"]["hil_request_id"] == "abc-123"
    assert out["legacy_bridge"] is False
    assert out["user_answer"] == "yes"


def test_build_resolution_is_kind_aware_for_approval_and_capability_gate() -> None:
    from k1.concierge.actors.front import _build_resolution

    yes = _build_resolution({"hil_type": "approval", "user_answer": "yes please"})
    no = _build_resolution({"hil_type": "approval", "user_answer": "no"})
    gate = _build_resolution({"hil_type": "capability_gate", "user_answer": "allow it"})

    assert yes["approval"] is True
    assert yes["selected_option"] == "approve"
    assert no["approval"] is False
    assert no["selected_option"] == "reject"
    assert gate["approval"] is True


def test_build_resolution_matches_needs_human_option() -> None:
    from k1.concierge.actors.front import _build_resolution

    out = _build_resolution(
        {
            "hil_type": "needs_human",
            "user_answer": "Use Paris",
            "hil_options": [{"id": "city-paris", "label": "Paris"}],
        }
    )

    assert out["selected_option"] == "city-paris"
    assert out["target"] == {"id": "city-paris", "label": "Paris"}


class _RecordingBus:
    def __init__(self) -> None:
        self.published: list[Any] = []

    def publish(self, envelope: Any) -> None:
        self.published.append(envelope)


def _mock_front_config() -> Any:
    cfg = type("Cfg", (), {})()
    actors = type("Actors", (), {})()
    front = type("Front", (), {})()
    front.default_affect_confidence = 0.5
    front.default_tier = "LOW"
    front.history_window_fallback = 10
    actors.front = front
    cfg.actors = actors
    return cfg


@pytest.mark.asyncio
async def test_front_handler_unified_hitl_response_does_not_emit_task_resume() -> None:
    import json as _json
    from unittest.mock import AsyncMock, MagicMock, patch

    from k1.bus.envelope.envelope import Envelope
    from k1.concierge.actors.front import front_handler
    from k1.concierge.bus.topics import TOPIC_HIL_RESPONSE, TOPIC_TASK_RESUME
    from k1.concierge.prompt.mode import PromptMode
    from k1.concierge.react.loop import ReactResult

    incoming = _env(HILKind.CLARIFICATION, {"question": "Which city?"})
    task_state = type(
        "TaskState",
        (),
        {
            "get_all": lambda self: [
                {
                    "task_id": "task-unified",
                    "status": "SUSPENDED",
                    "pending_hil_data": {"envelope": incoming, "hil_request_id": "abc-123"},
                }
            ]
        },
    )()
    ss = type(
        "SS", (), {"get_section": lambda self, name: task_state if name == "task_state" else None}
    )()
    bus = _RecordingBus()
    env = Envelope(topic="k1.user.input.v1", payload=_json.dumps({"text": "Paris"}).encode())
    result = ReactResult(status="complete", text="Got it.", dispatched_tasks=[])

    with (
        patch("k1.concierge.actors.front.react_loop", return_value=result),
        patch("k1.concierge.actors.front.determine_mode", return_value=PromptMode.HITL_RESOLVE),
        patch("k1.concierge.actors.front.DynamicPromptBuilder") as mock_builder,
        patch("k1.concierge.react.history.build_chat_history", return_value=[]),
        patch("k1.concierge.actors.front.compute_affect_band", return_value="calm"),
        patch("k1.concierge.actors.front.LLMOutputValidator", return_value=None),
        patch("k1.concierge.actors.front.get_config", return_value=_mock_front_config()),
    ):
        mock_ctx = MagicMock()
        mock_ctx.system_prompt = "test"
        mock_ctx.messages = []
        mock_ctx.tools = []
        mock_ctx.max_iterations = 3
        mock_ctx.affect_band = "calm"
        mock_builder.return_value.build.return_value = mock_ctx

        await front_handler(
            envelope=env,
            model=AsyncMock(),
            ss=ss,
            bus=bus,  # type: ignore[arg-type]
            tool_dispatcher=MagicMock(),
            all_tool_schemas=[],
            fsm_state="CLARIFYING_WORKER",
        )

    topics = [event.topic for event in bus.published]
    assert TOPIC_HIL_RESPONSE in topics
    assert TOPIC_TASK_RESUME not in topics


@pytest.mark.asyncio
async def test_front_handler_legacy_bridge_emits_hil_response_before_resume() -> None:
    import json as _json
    from unittest.mock import AsyncMock, MagicMock, patch

    from k1.bus.envelope.envelope import Envelope
    from k1.concierge.actors.front import front_handler
    from k1.concierge.bus.topics import TOPIC_HIL_RESPONSE, TOPIC_TASK_RESUME
    from k1.concierge.prompt.mode import PromptMode
    from k1.concierge.react.loop import ReactResult

    incoming = _env(HILKind.NEEDS_HUMAN, {"question": "Which city?", "legacy_bridge": True})
    incoming["legacy_bridge"] = True
    task_state = type(
        "TaskState",
        (),
        {
            "get_all": lambda self: [
                {
                    "task_id": "task-legacy",
                    "status": "SUSPENDED",
                    "pending_hil_data": {
                        "envelope": incoming,
                        "hil_request_id": "abc-123",
                        "legacy_bridge": True,
                    },
                }
            ]
        },
    )()
    ss = type(
        "SS", (), {"get_section": lambda self, name: task_state if name == "task_state" else None}
    )()
    bus = _RecordingBus()
    env = Envelope(topic="k1.user.input.v1", payload=_json.dumps({"text": "Paris"}).encode())
    result = ReactResult(status="complete", text="Got it.", dispatched_tasks=[])

    with (
        patch("k1.concierge.actors.front.react_loop", return_value=result),
        patch("k1.concierge.actors.front.determine_mode", return_value=PromptMode.HITL_RESOLVE),
        patch("k1.concierge.actors.front.DynamicPromptBuilder") as mock_builder,
        patch("k1.concierge.react.history.build_chat_history", return_value=[]),
        patch("k1.concierge.actors.front.compute_affect_band", return_value="calm"),
        patch("k1.concierge.actors.front.LLMOutputValidator", return_value=None),
        patch("k1.concierge.actors.front.get_config", return_value=_mock_front_config()),
    ):
        mock_ctx = MagicMock()
        mock_ctx.system_prompt = "test"
        mock_ctx.messages = []
        mock_ctx.tools = []
        mock_ctx.max_iterations = 3
        mock_ctx.affect_band = "calm"
        mock_builder.return_value.build.return_value = mock_ctx

        await front_handler(
            envelope=env,
            model=AsyncMock(),
            ss=ss,
            bus=bus,  # type: ignore[arg-type]
            tool_dispatcher=MagicMock(),
            all_tool_schemas=[],
            fsm_state="CLARIFYING_WORKER",
        )

    topics = [event.topic for event in bus.published]
    assert topics.index(TOPIC_HIL_RESPONSE) < topics.index(TOPIC_TASK_RESUME)
