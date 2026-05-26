from __future__ import annotations

from types import SimpleNamespace

import pytest

from k1.concierge.section_update.prompt import SECTION_UPDATE_BATCH_TOOL_NAME
from scripts import m3_live_shadow_validation as runner


def _args(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "timeout_ms": 45000,
        "preferred_provider": "vertex",
        "preferred_model": "gemini-2.5-flash-lite",
        "turn_limit": 0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_build_classifier_input_redacts_raw_front_session_ops() -> None:
    observation = {
        "index": 2,
        "web_turn": 2,
        "text": "Actually, Priya is covering soccer pickup today, not Jordan.",
        "response_text": "Got it.",
        "activity": {
            "tool_calls": ["update_beliefs", "update_beliefs"],
            "session_ops": ["SS.beliefs: Jordan.is=not the carpool contact"],
            "latency_ms": 123,
            "fsm_states": ["LISTENING", "DISPATCHING"],
        },
        "session_snapshot_before_turn": {
            "available": True,
            "source": "api/session/state",
            "snapshot_version": "snap-1",
            "snapshot_source_epoch": "epoch-1",
            "section_count": 19,
            "sections": {},
            "cognitive_sections": {},
        },
    }

    input_data = runner.build_classifier_input(observation, {"session_id": "s1"}, _args())

    assistant_turn = input_data["assistant_turn"]
    assert assistant_turn["session_ops"] == []
    assert assistant_turn["raw_front_session_ops_redacted"] is True
    assert assistant_turn["legacy_front_tool_names"] == ["update_beliefs"]
    assert assistant_turn["legacy_front_session_op_count"] == 1
    assert "Jordan.is=not" not in str(input_data)


def test_run_label_placeholders_are_rejected_from_semantic_turn_data() -> None:
    config = {"turns": [{"text": "hello {run_label}"}]}

    with pytest.raises(ValueError, match="run label placeholder"):
        runner.selected_turns(config, _args(), "m3-test")


def test_first_noop_tranche_config_selects_40_noop_golden_cases() -> None:
    config = runner.load_config(runner.DEFAULT_CONFIG)
    turns = runner.selected_turns(config, _args(), "m3-test")
    cases = runner.golden_cases_by_id(config)
    case_ids = [str(turn["golden_case_id"]) for turn in turns]

    assert len(case_ids) == 40
    assert len(set(case_ids)) == 40
    assert all(case_id.startswith("noop_") for case_id in case_ids)

    for turn in turns:
        assert turn["expected_operations"] == []
        assert turn["critical_operations"] == []
        assert turn["dangerous_false_write_if_unexpected"] is True

    for case_id in case_ids:
        expected_plan = cases[case_id]["expected_plan"]
        assert expected_plan["apply_timing"] == "no_op"
        assert expected_plan["mutations"] == []
        assert expected_plan["rejected_candidates"]


def test_plan_from_tool_calls_filters_front_contaminated_correction_candidates() -> None:
    input_data = {
        "turn_id": "web-live-m3-poc:2",
        "session_id": "web-live-m3-poc",
        "cognitive_trace_id": "trace-2",
        "user_turn": {"text": "Actually, Priya is covering soccer pickup today, not Jordan."},
        "session_snapshot": {"snapshot_version": "snap-2"},
    }
    tool_calls = [
        {
            "name": SECTION_UPDATE_BATCH_TOOL_NAME,
            "arguments": {
                "turn_id": input_data["turn_id"],
                "apply_timing": "shadow_only",
                "mutations": [
                    {
                        "section": "beliefs_active",
                        "operation": "add_fact",
                        "data": {
                            "subject": "Emma's soccer pickup",
                            "predicate": "has_carpool_contact",
                            "obj": "Priya",
                        },
                        "confidence": 1.0,
                        "reason": "User corrected the carpool contact for soccer pickup.",
                        "source": "classifier:section_update",
                        "idempotency_key": "pickup-contact-priya",
                        "commit_class": "next_turn_continuity",
                    },
                    {
                        "section": "beliefs_active",
                        "operation": "add_fact",
                        "data": {
                            "subject": "Emma's soccer pickup",
                            "predicate": "has_carpool_contact",
                            "obj": "Priya",
                        },
                        "confidence": 1.0,
                        "reason": "Duplicate restatement of the same correction.",
                        "source": "classifier:section_update",
                        "idempotency_key": "pickup-contact-priya-v2",
                        "commit_class": "next_turn_continuity",
                    },
                    {
                        "section": "beliefs_active",
                        "operation": "add_fact",
                        "data": {
                            "subject": "Jordan",
                            "predicate": "is_carpool_contact_for",
                            "obj": "Emma's soccer pickup today",
                        },
                        "confidence": 1.0,
                        "reason": "Removing Jordan from the pickup contact.",
                        "source": "classifier:section_update",
                        "idempotency_key": "jordan-pickup-removed",
                        "commit_class": "next_turn_continuity",
                    },
                    {
                        "section": "beliefs_active",
                        "operation": "update_confidence",
                        "data": {"id": "fact-jordan", "confidence": 0.1},
                        "confidence": 1.0,
                        "reason": "Lower confidence in the prior Jordan fact.",
                        "source": "classifier:section_update",
                        "idempotency_key": "fact-jordan-confidence",
                        "commit_class": "next_turn_continuity",
                    },
                ],
                "rejected_candidates": [],
            },
        }
    ]

    plan, status, degradation_reason, validation_errors = runner.plan_from_tool_calls(
        input_data=input_data,
        tool_calls=tool_calls,
        required_tool_name=SECTION_UPDATE_BATCH_TOOL_NAME,
        metadata={"provider_id": "vertex", "model_id": "gemini-2.5-flash-lite"},
    )

    assert status == "shadow_plan"
    assert degradation_reason == ""
    assert validation_errors == []
    assert len(plan.mutations) == 1
    accepted = plan.mutations[0]
    assert accepted.operation == "add_fact"
    assert accepted.data == {
        "subject": "Emma's soccer pickup",
        "predicate": "has_carpool_contact",
        "obj": "Priya",
        "confidence": 1.0,
        "source": "classifier:section_update",
    }
    assert len(plan.rejected_candidates) == 3
    assert any("duplicate_semantic_mutation" in item.reason for item in plan.rejected_candidates)
    assert any("ordinary correction" in item.reason for item in plan.rejected_candidates)
    assert any("requires explicit confidence" in item.reason for item in plan.rejected_candidates)


def test_plan_from_tool_calls_rejects_closure_meta_belief_as_noop() -> None:
    input_data = {
        "turn_id": "web-live-m3-poc:4",
        "session_id": "web-live-m3-poc",
        "cognitive_trace_id": "trace-4",
        "user_turn": {"text": "Thanks, that is all for pickup."},
        "assistant_turn": {"final_text": "You got it, Alex! Glad we got that sorted."},
        "session_snapshot": {"snapshot_version": "snap-4"},
    }
    tool_calls = [
        {
            "name": SECTION_UPDATE_BATCH_TOOL_NAME,
            "arguments": {
                "turn_id": input_data["turn_id"],
                "apply_timing": "shadow_only",
                "mutations": [
                    {
                        "section": "beliefs_active",
                        "operation": "add_fact",
                        "data": {
                            "subject": "Alex",
                            "predicate": "is_done_with",
                            "obj": "pickup arrangements",
                        },
                        "confidence": 1.0,
                        "reason": "User is done with the pickup arrangements.",
                        "source": "classifier:section_update",
                        "idempotency_key": "belief:carpool-contact:alex",
                        "commit_class": "next_turn_continuity",
                    }
                ],
                "rejected_candidates": [],
            },
        }
    ]

    plan, status, degradation_reason, validation_errors = runner.plan_from_tool_calls(
        input_data=input_data,
        tool_calls=tool_calls,
        required_tool_name=SECTION_UPDATE_BATCH_TOOL_NAME,
        metadata={"provider_id": "vertex", "model_id": "gemini-2.5-flash-lite"},
    )

    assert status == "shadow_noop"
    assert plan.is_noop is True
    assert degradation_reason == ""
    assert validation_errors == []
    assert plan.mutations == []
    assert len(plan.rejected_candidates) == 1
    assert "conversational closure" in plan.rejected_candidates[0].reason
