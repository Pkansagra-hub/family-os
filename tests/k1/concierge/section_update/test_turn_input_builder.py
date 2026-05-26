"""M2.I1 SectionUpdateInput construction from completed Front turns."""

from __future__ import annotations

import json
from dataclasses import dataclass

from k1.bus.envelope import Envelope, PayloadFormat, Priority
from k1.concierge.react.loop import ReactResult
from k1.concierge.section_update.input_builder import build_section_update_input


def _envelope(
    *,
    topic: str = "k1.response.final.v1",
    payload: dict | None = None,
) -> Envelope:
    return Envelope(
        topic=topic,
        priority=Priority.INTERACTIVE,
        envelope_id=42,
        sequence=7,
        cognitive_trace_id="trace-1",
        session_id="session-1",
        request_id="request-1",
        parent_id=41,
        created_ns=1_700_000_000_123_000_000,
        payload=json.dumps(payload or {"text": "I prefer quiet rooms"}).encode("utf-8"),
        payload_format=PayloadFormat.JSON,
    )


class _Snapshot:
    def to_dict(self) -> dict:
        return {
            "session_id": "session-1",
            "total_size_bytes": 1200,
            "hot_size_bytes": 800,
            "warm_size_bytes": 400,
            "pressure": "normal",
            "last_mutation_ms": 12345,
            "is_running": True,
            "timestamp_ms": 999999,
            "sections": {
                "beliefs_active": {
                    "name": "beliefs_active",
                    "tier": "hot",
                    "size_bytes": 120,
                    "budget_bytes": 4096,
                    "utilization_pct": 2.93,
                    "pressure": "normal",
                }
            },
        }


@dataclass
class _Referent:
    id: str
    text: str
    entity_id: str


@dataclass
class _Commitment:
    id: str
    description: str
    trigger_condition: str


class _Scoreboard:
    def list_referents(self) -> list[_Referent]:
        return [_Referent(id="r1", text="quiet rooms", entity_id="pref:quiet")]

    def list_open_questions(self) -> list[dict]:
        return [{"id": "q1", "text": "Which hotel?"}]

    def get_open_commitments(self) -> list[_Commitment]:
        return [
            _Commitment(
                id="c1",
                description="Find quiet hotels",
                trigger_condition="when travel dates are known",
            )
        ]

    def add_referent(self, *_args, **_kwargs) -> None:
        raise AssertionError("input builder must not mutate scoreboard")


class _History:
    def get_typed_entries(self) -> list[dict]:
        return [
            {"role": "user", "text": "Book a room"},
            {"role": "assistant", "text": "Sure."},
        ]


class _SessionState:
    def __init__(self) -> None:
        self.reads: list[str] = []
        self.sections = {
            "scoreboard": _Scoreboard(),
            "history_active": _History(),
        }

    def get_snapshot(self) -> _Snapshot:
        return _Snapshot()

    def get_section(self, name: str):
        self.reads.append(name)
        return self.sections.get(name)


def test_identical_turn_data_produces_identical_input() -> None:
    ss = _SessionState()
    env = _envelope(
        payload={
            "text": "I prefer quiet rooms",
            "device_id": "device-1",
            "arbiter_decision": "new_task",
            "safety_band": "GREEN",
            "routing_metadata": {"intent": "travel"},
        }
    )
    result = ReactResult(status="complete", text="Got it.")

    first = build_section_update_input(
        envelope=env,
        ss=ss,
        turn_number=3,
        user_text="I prefer quiet rooms",
        assistant_text="Got it.",
        prompt_mode="STANDARD",
        fsm_state="LISTENING",
        react_result=result,
        prompt_context={"system_prompt": "do not leak this", "tool_names": ["recall_memory"]},
    )
    second = build_section_update_input(
        envelope=env,
        ss=ss,
        turn_number=3,
        user_text="I prefer quiet rooms",
        assistant_text="Got it.",
        prompt_mode="STANDARD",
        fsm_state="LISTENING",
        react_result=result,
        prompt_context={"system_prompt": "do not leak this", "tool_names": ["recall_memory"]},
    )

    assert first.to_dict() == second.to_dict()
    assert first.turn_id == "session-1:3"
    assert first.prompt_context["system_prompt_summary"]["sha256"]
    assert "do not leak this" not in json.dumps(first.prompt_context)


def test_final_response_turn_captures_user_assistant_and_read_only_context() -> None:
    ss = _SessionState()
    env = _envelope(payload={"text": "I prefer quiet rooms", "device_id": "device-1"})

    section_input = build_section_update_input(
        envelope=env,
        ss=ss,
        turn_number=9,
        user_text="I prefer quiet rooms",
        assistant_text="Got it.",
        prompt_mode="STANDARD",
        fsm_state="LISTENING",
        react_result=ReactResult(status="complete", text="fallback should not win"),
        scenario_data={"active_member": "Riley"},
    )

    assert section_input.user_turn["text"] == "I prefer quiet rooms"
    assert section_input.user_turn["device_id"] == "device-1"
    assert section_input.assistant_turn["final_text"] == "Got it."
    assert section_input.session_snapshot["snapshot_version"]
    assert section_input.session_snapshot["snapshot_source_epoch"] == "12345"
    assert (
        section_input.session_snapshot["scoreboard_context"]["open_commitments"][0]["description"]
        == "Find quiet hotels"
    )
    assert section_input.history_context["entry_count"] == 2
    assert ss.reads == ["scoreboard", "history_active"]


def test_dispatch_turn_carries_dispatch_specs_without_requiring_final_text() -> None:
    env = _envelope(
        topic="k1.orchestration.task.dispatch.v1",
        payload={"text": "Find a hotel", "trace_id": "trace-from-payload"},
    )
    result = ReactResult(
        status="complete",
        text="",
        dispatched_tasks=[
            {
                "task_id": "task-1",
                "tier": "LOW",
                "intents": [{"action": "find_hotel"}],
            }
        ],
        parallel_tool_calls=1,
        sequential_tool_calls=2,
    )

    section_input = build_section_update_input(
        envelope=env,
        turn_number=4,
        session_id="session-1",
        user_text="Find a hotel",
        prompt_mode="STANDARD",
        fsm_state="COMPANIONING",
        react_result=result,
    )

    assert section_input.bus_topic == "k1.orchestration.task.dispatch.v1"
    assert section_input.assistant_turn["final_text"] == ""
    assert section_input.assistant_turn["dispatch_count"] == 1
    assert section_input.assistant_turn["dispatch_specs"][0]["task_id"] == "task-1"
    assert section_input.assistant_turn["parallel_tool_calls"] == 1
    assert section_input.assistant_turn["sequential_tool_calls"] == 2


def test_missing_optional_context_degrades_to_empty_fields() -> None:
    section_input = build_section_update_input(
        envelope=_envelope(payload={"text": "hello"}),
        session_id="session-1",
        user_text="hello",
        assistant_text="hi",
    )

    assert section_input.scenario_context == {}
    assert section_input.history_context == {"entries": [], "entry_count": 0, "window": 8}
    assert section_input.session_snapshot == {
        "source": "none",
        "snapshot_version": "",
        "snapshot_source_epoch": "",
    }
