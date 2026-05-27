from __future__ import annotations

import os
from collections import Counter
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
        "model_call_spacing_s": 0.0,
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


def test_cumulative_config_selects_full_100_case_corpus_in_ordered_tranches() -> None:
    config = runner.load_config(runner.DEFAULT_CONFIG)
    turns = runner.selected_turns(config, _args(), "m3-test")
    cases = runner.golden_cases_by_id(config)
    case_ids = [str(turn["golden_case_id"]) for turn in turns]
    first_tranche = turns[:40]
    second_tranche = turns[40:75]
    third_tranche = turns[75:100]

    assert len(case_ids) == 100
    assert len(set(case_ids)) == 100
    assert len(first_tranche) == 40
    assert len(second_tranche) == 35
    assert len(third_tranche) == 25
    assert all(str(turn["golden_case_id"]).startswith("noop_") for turn in first_tranche)
    assert [
        sum(1 for turn in second_tranche if str(turn["golden_case_id"]).startswith(prefix))
        for prefix in ("belief_", "definition_", "correction_")
    ] == [12, 12, 11]
    assert [
        sum(1 for turn in third_tranche if str(turn["golden_case_id"]).startswith(prefix))
        for prefix in ("scoreboard_", "clarification_", "narrative_", "affect_")
    ] == [8, 7, 5, 5]

    for turn in first_tranche:
        assert turn["expected_operations"] == []
        assert turn["critical_operations"] == []
        assert turn["dangerous_false_write_if_unexpected"] is True

    for case_id in case_ids[:40]:
        expected_plan = cases[case_id]["expected_plan"]
        assert expected_plan["apply_timing"] == "no_op"
        assert expected_plan["mutations"] == []
        assert expected_plan["rejected_candidates"]

    for turn in second_tranche:
        assert turn["expected_operations"] == ["beliefs_active.add_fact"]
        assert turn["critical_operations"] == ["beliefs_active.add_fact"]
        assert turn["dangerous_false_write_if_unexpected"] is True

    for case_id in case_ids[40:75]:
        expected_plan = cases[case_id]["expected_plan"]
        assert expected_plan["apply_timing"] == "shadow_only"
        assert expected_plan["rejected_candidates"] == []
        assert [
            f"{mutation['section']}.{mutation['operation']}"
            for mutation in expected_plan["mutations"]
        ] == ["beliefs_active.add_fact"]
        mutation = expected_plan["mutations"][0]
        assert mutation["data"]["confidence"] == mutation["confidence"]
        assert mutation["data"]["source"] == "classifier:section_update"
        assert "obj" in mutation["data"]

    third_operations = Counter(
        operation for turn in third_tranche for operation in turn["expected_operations"]
    )
    assert third_operations == Counter(
        {
            "scoreboard.add_referent": 4,
            "scoreboard.push_question": 2,
            "scoreboard.push_topic": 2,
            "clarifications.request": 7,
            "narrative_active.create_thread": 5,
            "affective_now.update": 5,
        }
    )

    for turn in third_tranche:
        assert turn["critical_operations"] == turn["expected_operations"]
        assert turn["dangerous_false_write_if_unexpected"] is True

    for case_id in case_ids[75:100]:
        expected_plan = cases[case_id]["expected_plan"]
        assert expected_plan["apply_timing"] == "shadow_only"
        assert expected_plan["rejected_candidates"] == []
        assert len(expected_plan["mutations"]) == 1
        mutation = expected_plan["mutations"][0]
        operation_name = f"{mutation['section']}.{mutation['operation']}"
        assert operation_name in third_operations
        assert mutation["source"] == "classifier:section_update"
        assert mutation["idempotency_key"]
        required_payload_keys = {
            "scoreboard.add_referent": {"text", "entity_id", "entity_type", "salience"},
            "scoreboard.push_question": {"text", "asked_by", "priority"},
            "scoreboard.push_topic": {"name", "salience", "is_primary"},
            "clarifications.request": {
                "agent_id",
                "question",
                "priority",
                "related_entity",
                "related_intent",
                "timeout_ms",
                "blocking",
            },
            "narrative_active.create_thread": {
                "title",
                "goal",
                "related_entities",
                "related_intents",
                "auto_switch",
            },
            "affective_now.update": {
                "emotion",
                "intensity",
                "valence",
                "arousal",
                "dominance",
                "confidence",
                "source",
            },
        }
        assert required_payload_keys[operation_name].issubset(mutation["data"])


def test_simulated_kernel_observations_use_sessionstate_snapshots_and_oracle_apply() -> None:
    config = runner.load_config(runner.DEFAULT_CONFIG)
    turns = runner.selected_turns(config, _args(turn_limit=42), "m3-test")

    observations, summary = runner.collect_simulated_kernel_turns(turns, config)

    assert len(observations) == 42
    assert summary["kernel"] == "bypassed"
    assert summary["session_state"] == "SessionStateFactory.create_for_testing"
    assert summary["oracle_mutation_count"] == 2
    assert summary["oracle_failed_mutation_count"] == 0
    assert observations[0]["prompt_mode"] == "simulated_kernel"
    assert observations[0]["session_snapshot_before_turn"]["source"] == (
        "simulated/sessionstate/pre_turn"
    )
    first_belief_snapshot = observations[40]["session_snapshot_before_turn"]
    second_belief_snapshot = observations[41]["session_snapshot_before_turn"]
    assert first_belief_snapshot["cognitive_sections"]["beliefs_active"]["fact_count"] == 0
    assert second_belief_snapshot["cognitive_sections"]["beliefs_active"]["fact_count"] == 1


def test_normalize_provider_env_prefers_config_over_ambient_google(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "google")
    monkeypatch.setenv("GOOGLE_API_KEY", "placeholder-not-used")
    monkeypatch.delenv("VERTEX_MODEL", raising=False)
    config = {
        "preferred_provider": "vertex",
        "preferred_model": "gemini-2.5-flash-lite",
    }

    runner.normalize_provider_env(config, _args(preferred_provider="", preferred_model=""))

    assert os.environ["LLM_PROVIDER"] == "vertex"
    assert os.environ["GOOGLE_GENAI_USE_VERTEXAI"] == "True"
    assert os.environ["K1_SECTION_UPDATE_MODEL"] == "gemini-2.5-flash-lite"
    assert os.environ["VERTEX_MODEL"] == "gemini-2.5-flash-lite"
    assert "GOOGLE_API_KEY" not in os.environ


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


def test_plan_from_tool_calls_rejects_runtime_capability_state_question() -> None:
    input_data = {
        "turn_id": "web-live-m3-poc:capability-state",
        "session_id": "web-live-m3-poc",
        "cognitive_trace_id": "trace-capability-state",
        "user_turn": {"text": "Can you check whether the family calendar has anything tomorrow?"},
        "assistant_turn": {"final_text": "Acknowledged for section-update validation."},
        "session_snapshot": {"snapshot_version": "snap-capability-state"},
    }
    tool_calls = [
        {
            "name": SECTION_UPDATE_BATCH_TOOL_NAME,
            "arguments": {
                "turn_id": input_data["turn_id"],
                "apply_timing": "shadow_only",
                "mutations": [
                    {
                        "section": "clarifications",
                        "operation": "request",
                        "data": {
                            "agent_id": "section_update_classifier",
                            "question": "Which calendar should I check?",
                            "priority": 2,
                            "related_entity": "family calendar",
                            "related_intent": "calendar_check",
                            "timeout_ms": 0,
                            "blocking": True,
                        },
                        "confidence": 1.0,
                        "reason": "Incorrectly treated a capability read as a clarification.",
                        "source": "classifier:section_update",
                        "idempotency_key": "clarification:calendar-check",
                        "commit_class": "prompt_critical",
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
    assert degradation_reason == ""
    assert validation_errors == []
    assert plan.mutations == []
    assert "runtime/capability live-state question" in plan.rejected_candidates[0].reason


def test_plan_from_tool_calls_rejects_reminder_status_question_as_qud() -> None:
    input_data = {
        "turn_id": "web-live-m3-poc:reminder-status",
        "session_id": "web-live-m3-poc",
        "cognitive_trace_id": "trace-reminder-status",
        "user_turn": {"text": "Do we already have a reminder for trash night?"},
        "assistant_turn": {"final_text": "Acknowledged for section-update validation."},
        "session_snapshot": {"snapshot_version": "snap-reminder-status"},
    }
    tool_calls = [
        {
            "name": SECTION_UPDATE_BATCH_TOOL_NAME,
            "arguments": {
                "turn_id": input_data["turn_id"],
                "apply_timing": "shadow_only",
                "mutations": [
                    {
                        "section": "scoreboard",
                        "operation": "push_question",
                        "data": {
                            "text": "Do we already have a reminder for trash night?",
                            "asked_by": "user",
                            "priority": 2,
                        },
                        "confidence": 1.0,
                        "reason": "Incorrectly tracked a capability-state read as QUD.",
                        "source": "classifier:section_update",
                        "idempotency_key": "qud:trash-night-reminder",
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
    assert degradation_reason == ""
    assert validation_errors == []
    assert plan.mutations == []
    assert "runtime/capability live-state question" in plan.rejected_candidates[0].reason


def test_plan_from_tool_calls_rejects_history_and_artifact_reads_as_clarifications() -> None:
    for text in (
        "Can you show the exact transcript line I just sent?",
        "What artifact did the last task produce?",
    ):
        input_data = {
            "turn_id": f"web-live-m3-poc:runtime-read:{hash(text)}",
            "session_id": "web-live-m3-poc",
            "cognitive_trace_id": "trace-runtime-read",
            "user_turn": {"text": text},
            "assistant_turn": {"final_text": "Acknowledged for section-update validation."},
            "session_snapshot": {"snapshot_version": "snap-runtime-read"},
        }
        tool_calls = [
            {
                "name": SECTION_UPDATE_BATCH_TOOL_NAME,
                "arguments": {
                    "turn_id": input_data["turn_id"],
                    "apply_timing": "shadow_only",
                    "mutations": [
                        {
                            "section": "clarifications",
                            "operation": "request",
                            "data": {
                                "agent_id": "section_update_classifier",
                                "question": text,
                                "priority": 2,
                                "related_entity": "runtime read",
                                "related_intent": "runtime_read",
                                "timeout_ms": 0,
                                "blocking": True,
                            },
                            "confidence": 1.0,
                            "reason": "Incorrectly treated a runtime-owned read as clarification.",
                            "source": "classifier:section_update",
                            "idempotency_key": "clarification:runtime-read",
                            "commit_class": "prompt_critical",
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
        assert degradation_reason == ""
        assert validation_errors == []
        assert plan.mutations == []
        assert "runtime/capability live-state question" in plan.rejected_candidates[0].reason


def test_plan_from_tool_calls_rejects_meta_and_archive_reads_as_clarifications() -> None:
    for text in (
        "Which internal policy says what you are allowed to write?",
        "What is in the warm beliefs archive?",
    ):
        input_data = {
            "turn_id": f"web-live-m3-poc:meta-read:{hash(text)}",
            "session_id": "web-live-m3-poc",
            "cognitive_trace_id": "trace-meta-read",
            "user_turn": {"text": text},
            "assistant_turn": {"final_text": "Acknowledged for section-update validation."},
            "session_snapshot": {"snapshot_version": "snap-meta-read"},
        }
        tool_calls = [
            {
                "name": SECTION_UPDATE_BATCH_TOOL_NAME,
                "arguments": {
                    "turn_id": input_data["turn_id"],
                    "apply_timing": "shadow_only",
                    "mutations": [
                        {
                            "section": "clarifications",
                            "operation": "request",
                            "data": {
                                "agent_id": "section_update_classifier",
                                "question": text,
                                "priority": 2,
                                "related_entity": "runtime metadata",
                                "related_intent": "runtime_read",
                                "timeout_ms": 0,
                                "blocking": True,
                            },
                            "confidence": 1.0,
                            "reason": "Incorrectly treated a runtime-owned read as clarification.",
                            "source": "classifier:section_update",
                            "idempotency_key": "clarification:meta-read",
                            "commit_class": "prompt_critical",
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
        assert degradation_reason == ""
        assert validation_errors == []
        assert plan.mutations == []
        assert "runtime/capability live-state question" in plan.rejected_candidates[0].reason


def test_plan_from_tool_calls_rejects_durable_correction_as_referent() -> None:
    input_data = {
        "turn_id": "web-live-m3-poc:lunchbox-correction-referent",
        "session_id": "web-live-m3-poc",
        "cognitive_trace_id": "trace-lunchbox-correction",
        "user_turn": {"text": "Pack the red lunchbox for Mira, not the yellow one."},
        "assistant_turn": {"final_text": "Acknowledged for section-update validation."},
        "session_snapshot": {"snapshot_version": "snap-lunchbox-correction"},
    }
    tool_calls = [
        {
            "name": SECTION_UPDATE_BATCH_TOOL_NAME,
            "arguments": {
                "turn_id": input_data["turn_id"],
                "apply_timing": "shadow_only",
                "mutations": [
                    {
                        "section": "scoreboard",
                        "operation": "add_referent",
                        "data": {
                            "text": "the red lunchbox",
                            "entity_id": "red-lunchbox",
                            "entity_type": "object",
                            "salience": 0.9,
                        },
                        "confidence": 1.0,
                        "reason": "Incorrectly treated a durable correction as a referent.",
                        "source": "classifier:section_update",
                        "idempotency_key": "referent:red-lunchbox",
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
    assert degradation_reason == ""
    assert validation_errors == []
    assert plan.mutations == []
    assert "durable correction choice" in plan.rejected_candidates[0].reason


def test_plan_from_tool_calls_accepts_durable_correction_as_belief() -> None:
    input_data = {
        "turn_id": "web-live-m3-poc:lunchbox-correction-belief",
        "session_id": "web-live-m3-poc",
        "cognitive_trace_id": "trace-lunchbox-correction-belief",
        "user_turn": {"text": "Pack the red lunchbox for Mira, not the yellow one."},
        "assistant_turn": {"final_text": "Acknowledged for section-update validation."},
        "session_snapshot": {"snapshot_version": "snap-lunchbox-correction-belief"},
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
                            "subject": "Mira's lunchbox",
                            "predicate": "should_be",
                            "obj": "red lunchbox",
                            "confidence": 1.0,
                            "source": "classifier:section_update",
                        },
                        "confidence": 1.0,
                        "reason": "User corrected the lunchbox choice.",
                        "source": "classifier:section_update",
                        "idempotency_key": "belief:mira-lunchbox:red",
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

    assert status == "shadow_plan"
    assert degradation_reason == ""
    assert validation_errors == []
    assert len(plan.mutations) == 1
    assert plan.mutations[0].section == "beliefs_active"
    assert plan.mutations[0].operation == "add_fact"
    assert plan.mutations[0].data["obj"] == "red lunchbox"


def test_plan_from_tool_calls_rejects_unresolved_placeholder_referent_write() -> None:
    input_data = {
        "turn_id": "web-live-m3-poc:placeholder",
        "session_id": "web-live-m3-poc",
        "cognitive_trace_id": "trace-placeholder",
        "user_turn": {"text": "Use the other one for pickup."},
        "assistant_turn": {"final_text": "Acknowledged for section-update validation."},
        "session_snapshot": {"snapshot_version": "snap-placeholder"},
    }
    tool_calls = [
        {
            "name": SECTION_UPDATE_BATCH_TOOL_NAME,
            "arguments": {
                "turn_id": input_data["turn_id"],
                "apply_timing": "shadow_only",
                "mutations": [
                    {
                        "section": "scoreboard",
                        "operation": "add_referent",
                        "data": {
                            "text": "the other one",
                            "entity_id": "other_pickup_option",
                            "entity_type": "option",
                            "salience": 0.8,
                        },
                        "confidence": 1.0,
                        "reason": "Incorrectly invented a referent for an unresolved placeholder.",
                        "source": "classifier:section_update",
                        "idempotency_key": "scoreboard:other-one",
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
    assert degradation_reason == ""
    assert validation_errors == []
    assert plan.mutations == []
    assert "unresolved placeholder-only turn" in plan.rejected_candidates[0].reason


def test_plan_from_tool_calls_rejects_normal_option_placeholder_with_apostrophe() -> None:
    input_data = {
        "turn_id": "web-live-m3-poc:normal-option",
        "session_id": "web-live-m3-poc",
        "cognitive_trace_id": "trace-normal-option",
        "user_turn": {"text": "Let's use the normal option for that."},
        "assistant_turn": {"final_text": "Acknowledged for section-update validation."},
        "session_snapshot": {"snapshot_version": "snap-normal-option"},
    }
    tool_calls = [
        {
            "name": SECTION_UPDATE_BATCH_TOOL_NAME,
            "arguments": {
                "turn_id": input_data["turn_id"],
                "apply_timing": "shadow_only",
                "mutations": [
                    {
                        "section": "scoreboard",
                        "operation": "add_referent",
                        "data": {
                            "text": "normal option",
                            "entity_id": "normal_option",
                            "entity_type": "option",
                            "salience": 0.8,
                        },
                        "confidence": 1.0,
                        "reason": "Incorrectly invented a referent for normal option.",
                        "source": "classifier:section_update",
                        "idempotency_key": "scoreboard:normal-option",
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
    assert degradation_reason == ""
    assert validation_errors == []
    assert plan.mutations == []
    assert "unresolved placeholder-only turn" in plan.rejected_candidates[0].reason


def test_plan_from_tool_calls_rejects_duplicate_scoreboard_referents() -> None:
    input_data = {
        "turn_id": "web-live-m3-poc:duplicate-referent",
        "session_id": "web-live-m3-poc",
        "cognitive_trace_id": "trace-duplicate-referent",
        "user_turn": {
            "text": "When I say that bottle in this thread, I mean the blue water bottle on the counter."
        },
        "assistant_turn": {"final_text": "Acknowledged for section-update validation."},
        "session_snapshot": {"snapshot_version": "snap-duplicate-referent"},
    }
    referent = {
        "section": "scoreboard",
        "operation": "add_referent",
        "data": {
            "text": "that bottle",
            "entity_id": "blue_water_bottle_on_counter",
            "entity_type": "item",
            "salience": 0.9,
        },
        "confidence": 1.0,
        "reason": "User defined that bottle for this thread.",
        "source": "classifier:section_update",
        "idempotency_key": "scoreboard:that-bottle",
        "commit_class": "next_turn_continuity",
    }
    tool_calls = [
        {
            "name": SECTION_UPDATE_BATCH_TOOL_NAME,
            "arguments": {
                "turn_id": input_data["turn_id"],
                "apply_timing": "shadow_only",
                "mutations": [
                    referent,
                    {**referent, "idempotency_key": "scoreboard:that-bottle-2"},
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
    assert "duplicate_singleton_operation" in plan.rejected_candidates[0].reason


def test_plan_from_tool_calls_rejects_tracking_question_as_clarification() -> None:
    input_data = {
        "turn_id": "web-live-m3-poc:tracking-qud",
        "session_id": "web-live-m3-poc",
        "cognitive_trace_id": "trace-tracking-qud",
        "user_turn": {"text": "Can you help me track which school forms are still due?"},
        "assistant_turn": {"final_text": "Acknowledged for section-update validation."},
        "session_snapshot": {"snapshot_version": "snap-tracking-qud"},
    }
    tool_calls = [
        {
            "name": SECTION_UPDATE_BATCH_TOOL_NAME,
            "arguments": {
                "turn_id": input_data["turn_id"],
                "apply_timing": "shadow_only",
                "mutations": [
                    {
                        "section": "clarifications",
                        "operation": "request",
                        "data": {
                            "agent_id": "section_update_classifier",
                            "question": "Which school forms are still due?",
                            "priority": 2,
                            "related_entity": "school forms",
                            "related_intent": "track_forms",
                            "timeout_ms": 0,
                            "blocking": True,
                        },
                        "confidence": 1.0,
                        "reason": "Incorrectly treated a non-blocking tracking question as clarification.",
                        "source": "classifier:section_update",
                        "idempotency_key": "clarification:school-forms-due",
                        "commit_class": "prompt_critical",
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
    assert degradation_reason == ""
    assert validation_errors == []
    assert plan.mutations == []
    assert "non-blocking tracking question" in plan.rejected_candidates[0].reason


def test_plan_from_tool_calls_rejects_durable_definition_as_scoreboard_referent() -> None:
    input_data = {
        "turn_id": "web-live-m3-poc:durable-definition",
        "session_id": "web-live-m3-poc",
        "cognitive_trace_id": "trace-durable-definition",
        "user_turn": {"text": "When I say blue bag, I mean the diaper bag by the garage door."},
        "assistant_turn": {"final_text": "Acknowledged for section-update validation."},
        "session_snapshot": {"snapshot_version": "snap-durable-definition"},
    }
    tool_calls = [
        {
            "name": SECTION_UPDATE_BATCH_TOOL_NAME,
            "arguments": {
                "turn_id": input_data["turn_id"],
                "apply_timing": "shadow_only",
                "mutations": [
                    {
                        "section": "scoreboard",
                        "operation": "add_referent",
                        "data": {
                            "text": "blue bag",
                            "entity_id": "diaper_bag_by_garage_door",
                            "entity_type": "item",
                            "salience": 0.9,
                        },
                        "confidence": 1.0,
                        "reason": "Incorrectly treated durable shorthand as local discourse.",
                        "source": "classifier:section_update",
                        "idempotency_key": "scoreboard:blue-bag",
                        "commit_class": "next_turn_continuity",
                    },
                    {
                        "section": "beliefs_active",
                        "operation": "add_fact",
                        "data": {
                            "subject": "blue bag",
                            "predicate": "means",
                            "obj": "diaper bag by the garage door",
                            "confidence": 1.0,
                            "source": "classifier:section_update",
                        },
                        "confidence": 1.0,
                        "reason": "User defined a durable shorthand.",
                        "source": "classifier:section_update",
                        "idempotency_key": "belief:blue-bag",
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
    assert plan.mutations[0].section == "beliefs_active"
    assert plan.mutations[0].operation == "add_fact"
    assert "durable shorthand definition" in plan.rejected_candidates[0].reason


def test_plan_from_tool_calls_rejects_extra_correction_add_fact() -> None:
    input_data = {
        "turn_id": "web-live-m3-poc:correction-extra",
        "session_id": "web-live-m3-poc",
        "cognitive_trace_id": "trace-correction-extra",
        "user_turn": {"text": "Use the blue folder for the consent form, not the green one."},
        "assistant_turn": {"final_text": "Acknowledged for section-update validation."},
        "session_snapshot": {"snapshot_version": "snap-correction-extra"},
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
                            "subject": "consent form",
                            "predicate": "is_in_folder",
                            "obj": "blue folder",
                            "confidence": 1.0,
                            "source": "classifier:section_update",
                        },
                        "confidence": 1.0,
                        "reason": "User corrected the consent form folder.",
                        "source": "classifier:section_update",
                        "idempotency_key": "belief:consent-form-blue-folder",
                        "commit_class": "next_turn_continuity",
                    },
                    {
                        "section": "beliefs_active",
                        "operation": "add_fact",
                        "data": {
                            "subject": "green folder",
                            "predicate": "means",
                            "obj": "field trip forms",
                            "confidence": 1.0,
                            "source": "classifier:section_update",
                        },
                        "confidence": 1.0,
                        "reason": "User corrected the meaning of the green folder.",
                        "source": "classifier:section_update",
                        "idempotency_key": "belief:green-folder-forms",
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
    assert plan.mutations[0].data["subject"] == "consent form"
    assert "duplicate_correction_add_fact" in plan.rejected_candidates[0].reason


def test_plan_from_tool_calls_rejects_duplicate_belief_paraphrase() -> None:
    input_data = {
        "turn_id": "web-live-m3-poc:belief-duplicate-paraphrase",
        "session_id": "web-live-m3-poc",
        "cognitive_trace_id": "trace-belief-duplicate-paraphrase",
        "user_turn": {"text": "Sam uses the blue folder for homework papers."},
        "assistant_turn": {"final_text": "Acknowledged for section-update validation."},
        "session_snapshot": {"snapshot_version": "snap-belief-duplicate-paraphrase"},
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
                            "subject": "blue folder",
                            "predicate": "is_used_for",
                            "obj": "homework papers",
                            "confidence": 1.0,
                            "source": "classifier:section_update",
                        },
                        "confidence": 1.0,
                        "reason": "User stated a durable fact about the blue folder.",
                        "source": "classifier:section_update",
                        "idempotency_key": "belief:blue-folder-homework",
                        "commit_class": "next_turn_continuity",
                    },
                    {
                        "section": "beliefs_active",
                        "operation": "add_fact",
                        "data": {
                            "subject": "Sam",
                            "predicate": "uses",
                            "obj": "blue folder for homework papers",
                            "confidence": 1.0,
                            "source": "classifier:section_update",
                        },
                        "confidence": 1.0,
                        "reason": "Duplicate paraphrase of the same sentence.",
                        "source": "classifier:section_update",
                        "idempotency_key": "belief:sam-blue-folder",
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
    assert plan.mutations[0].data["subject"] == "blue folder"
    assert "duplicate_belief_add_fact" in plan.rejected_candidates[0].reason


def test_plan_from_tool_calls_accepts_classifier_owned_clarification_request() -> None:
    input_data = {
        "turn_id": "web-live-m3-poc:clarification",
        "session_id": "web-live-m3-poc",
        "cognitive_trace_id": "trace-clarification",
        "user_turn": {"text": "Schedule the doctor appointment after school."},
        "assistant_turn": {"final_text": "Acknowledged for section-update validation."},
        "session_snapshot": {
            "snapshot_version": "snap-clarification",
            "cognitive_sections": {"clarifications": {"pending": {}, "pending_count": 0}},
        },
    }
    tool_calls = [
        {
            "name": SECTION_UPDATE_BATCH_TOOL_NAME,
            "arguments": {
                "turn_id": input_data["turn_id"],
                "apply_timing": "shadow_only",
                "mutations": [
                    {
                        "section": "clarifications",
                        "operation": "request",
                        "data": {
                            "agent_id": "section_update_classifier",
                            "question": "Which doctor appointment should be scheduled after school?",
                            "priority": 2,
                            "related_entity": "doctor appointment",
                            "related_intent": "schedule_appointment",
                            "timeout_ms": 0,
                            "blocking": True,
                        },
                        "confidence": 1.0,
                        "reason": "The actionable command is missing the appointment identity.",
                        "source": "classifier:section_update",
                        "idempotency_key": "clarification:doctor-appointment-after-school",
                        "commit_class": "prompt_critical",
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

    assert status == "shadow_plan"
    assert degradation_reason == ""
    assert validation_errors == []
    assert len(plan.mutations) == 1
    assert plan.mutations[0].section == "clarifications"
    assert plan.mutations[0].operation == "request"


def test_plan_from_tool_calls_rejects_clarification_answer_without_exact_pending_id() -> None:
    input_data = {
        "turn_id": "web-live-m3-poc:clarification-answer",
        "session_id": "web-live-m3-poc",
        "cognitive_trace_id": "trace-clarification-answer",
        "user_turn": {"text": "Pack the uniform for tomorrow."},
        "assistant_turn": {"final_text": "Acknowledged for section-update validation."},
        "session_snapshot": {
            "snapshot_version": "snap-clarification-answer",
            "cognitive_sections": {
                "clarifications": {
                    "pending_count": 1,
                    "blocking_clarification_id": "clar-existing",
                    "pending": {
                        "clar-existing": {
                            "id": "clar-existing",
                            "question": "Who is included in everyone for dinner tonight?",
                        }
                    },
                }
            },
        },
    }
    tool_calls = [
        {
            "name": SECTION_UPDATE_BATCH_TOOL_NAME,
            "arguments": {
                "turn_id": input_data["turn_id"],
                "apply_timing": "shadow_only",
                "mutations": [
                    {
                        "section": "clarifications",
                        "operation": "answer",
                        "data": {
                            "clarification_id": "clar-invented",
                            "answer": "Pack the uniform for tomorrow.",
                        },
                        "confidence": 1.0,
                        "reason": "Incorrectly treated a new command as an answer.",
                        "source": "classifier:section_update",
                        "idempotency_key": "clarification-answer:uniform",
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
    assert degradation_reason == ""
    assert validation_errors == []
    assert plan.mutations == []
    assert len(plan.rejected_candidates) == 1
    assert "exact pending snapshot clarification_id" in plan.rejected_candidates[0].reason


def test_plan_from_tool_calls_rejects_local_referent_belief() -> None:
    input_data = {
        "turn_id": "web-live-m3-poc:referent",
        "session_id": "web-live-m3-poc",
        "cognitive_trace_id": "trace-referent",
        "user_turn": {
            "text": "For the next question, this form means the field trip permission slip."
        },
        "assistant_turn": {"final_text": "Acknowledged for section-update validation."},
        "session_snapshot": {"snapshot_version": "snap-referent"},
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
                            "subject": "this form",
                            "predicate": "means",
                            "obj": "field trip permission slip",
                            "confidence": 1.0,
                            "source": "classifier:section_update",
                        },
                        "confidence": 1.0,
                        "reason": "User defined this form for the next question.",
                        "source": "classifier:section_update",
                        "idempotency_key": "belief:this-form",
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
    assert degradation_reason == ""
    assert validation_errors == []
    assert plan.mutations == []
    assert "conversation-local referent" in plan.rejected_candidates[0].reason


def test_plan_from_tool_calls_rejects_topic_only_narrative_thread() -> None:
    input_data = {
        "turn_id": "web-live-m3-poc:topic",
        "session_id": "web-live-m3-poc",
        "cognitive_trace_id": "trace-topic",
        "user_turn": {"text": "Let's focus on weekend packing for a minute."},
        "assistant_turn": {"final_text": "Acknowledged for section-update validation."},
        "session_snapshot": {"snapshot_version": "snap-topic"},
    }
    tool_calls = [
        {
            "name": SECTION_UPDATE_BATCH_TOOL_NAME,
            "arguments": {
                "turn_id": input_data["turn_id"],
                "apply_timing": "shadow_only",
                "mutations": [
                    {
                        "section": "narrative_active",
                        "operation": "create_thread",
                        "data": {
                            "title": "Weekend packing",
                            "goal": "Focus on weekend packing",
                            "related_entities": ["weekend packing"],
                            "related_intents": ["topic_focus"],
                            "auto_switch": True,
                        },
                        "confidence": 1.0,
                        "reason": "User asked to focus on weekend packing.",
                        "source": "classifier:section_update",
                        "idempotency_key": "thread:weekend-packing",
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
    assert degradation_reason == ""
    assert validation_errors == []
    assert plan.mutations == []
    assert "topic-only focus/switch" in plan.rejected_candidates[0].reason


def test_plan_from_tool_calls_rejects_affective_belief_but_keeps_affect_update() -> None:
    input_data = {
        "turn_id": "web-live-m3-poc:affect",
        "session_id": "web-live-m3-poc",
        "cognitive_trace_id": "trace-affect",
        "user_turn": {"text": "I am anxious about the schedule conflict tomorrow."},
        "assistant_turn": {"final_text": "Acknowledged for section-update validation."},
        "session_snapshot": {"snapshot_version": "snap-affect"},
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
                            "predicate": "is_anxious_about",
                            "obj": "schedule conflict tomorrow",
                            "confidence": 1.0,
                            "source": "classifier:section_update",
                        },
                        "confidence": 1.0,
                        "reason": "User explicitly stated they are anxious.",
                        "source": "classifier:section_update",
                        "idempotency_key": "belief:anxious-schedule-conflict",
                        "commit_class": "next_turn_continuity",
                    },
                    {
                        "section": "affective_now",
                        "operation": "update",
                        "data": {
                            "emotion": "anxious",
                            "intensity": 0.8,
                            "valence": -0.55,
                            "arousal": 0.75,
                            "dominance": 0.25,
                            "confidence": 0.9,
                            "source": "classifier:section_update",
                        },
                        "confidence": 0.9,
                        "reason": "User explicitly expressed anxiety.",
                        "source": "classifier:section_update",
                        "idempotency_key": "affect:anxious-schedule-conflict",
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
    assert plan.mutations[0].section == "affective_now"
    assert len(plan.rejected_candidates) == 1
    assert "first-person affect" in plan.rejected_candidates[0].reason
