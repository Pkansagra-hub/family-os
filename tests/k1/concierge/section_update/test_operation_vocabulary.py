"""M1.I2 classifier operation vocabulary."""

from __future__ import annotations

from k1.concierge.section_update.vocabulary import (
    CLASSIFIER_OPERATION_REGISTRY,
    FORBIDDEN_SECTIONS,
    GUARD_APPLY_MISMATCHES,
    LLM_WRITABLE_SECTIONS,
    SECTION_APPLY_OPERATIONS,
    allowed_operation_pairs,
    allowed_operations,
    validate_target,
)
from k1.sessionstate.guard import VALID_OPERATIONS
from k1.sessionstate.sizetracker import ALL_SECTIONS


def test_registry_has_only_six_cognitive_sections() -> None:
    assert tuple(CLASSIFIER_OPERATION_REGISTRY) == LLM_WRITABLE_SECTIONS
    assert set(CLASSIFIER_OPERATION_REGISTRY) == {
        "beliefs_active",
        "scoreboard",
        "clarifications",
        "narrative_active",
        "affective_now",
        "trust_level",
    }


def test_registry_matches_safe_v0_operations() -> None:
    assert allowed_operations("beliefs_active") == ("add_fact", "update_confidence")
    assert allowed_operations("scoreboard") == (
        "add_commitment",
        "add_referent",
        "cancel_commitment",
        "fulfill_commitment",
        "pop_question",
        "push_question",
        "push_topic",
    )
    assert allowed_operations("clarifications") == ("answer", "request")
    assert allowed_operations("narrative_active") == (
        "archive_thread",
        "create_thread",
        "pause_thread",
        "resolve_thread",
        "switch_to",
        "update_thread",
    )
    assert allowed_operations("affective_now") == ("update",)
    assert allowed_operations("trust_level") == ("update",)


def test_every_allowed_operation_is_guard_and_apply_compatible() -> None:
    for section, operation in allowed_operation_pairs():
        assert operation in VALID_OPERATIONS
        assert operation in SECTION_APPLY_OPERATIONS[section]


def test_guard_apply_mismatches_are_not_classifier_visible() -> None:
    assert "answer_question" in GUARD_APPLY_MISMATCHES["scoreboard"]
    assert "set_salience" in GUARD_APPLY_MISMATCHES["scoreboard"]
    assert "update_priority" in GUARD_APPLY_MISMATCHES["clarifications"]
    assert "update_dimensions" in GUARD_APPLY_MISMATCHES["affective_now"]

    for section, mismatched_ops in GUARD_APPLY_MISMATCHES.items():
        for operation in mismatched_ops:
            assert operation not in allowed_operations(section)


def test_forbidden_runtime_sections_rejected() -> None:
    assert "control" in FORBIDDEN_SECTIONS
    assert "task_state" in FORBIDDEN_SECTIONS
    assert "history_active" in FORBIDDEN_SECTIONS

    result = validate_target("control", "set")

    assert result.ok is False
    assert "forbidden" in result.reason


def test_all_non_writable_sessionstate_sections_are_forbidden() -> None:
    assert ALL_SECTIONS.difference(LLM_WRITABLE_SECTIONS).issubset(FORBIDDEN_SECTIONS)


def test_invalid_operation_rejected_with_reason() -> None:
    result = validate_target("scoreboard", "answer_question")

    assert result.ok is False
    assert "operation not allowed" in result.reason


def test_narrative_shorthand_rejected() -> None:
    result = validate_target("narrative_active", "resume")

    assert result.ok is False
    assert "shorthand" in result.reason


def test_runtime_owned_record_turn_is_not_model_visible() -> None:
    assert "record_turn" in VALID_OPERATIONS
    assert "record_turn" in SECTION_APPLY_OPERATIONS["narrative_active"]
    assert "record_turn" not in allowed_operations("narrative_active")
