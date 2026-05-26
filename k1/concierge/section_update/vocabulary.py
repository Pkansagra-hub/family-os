"""Classifier-visible SessionState section/operation vocabulary.

This registry is intentionally narrower than section ``apply`` support. It is
the V0 intersection of cognitive sections, guard-safe operations, and policy
choices suitable for a post-turn classifier.
"""

from __future__ import annotations

from dataclasses import dataclass

LLM_WRITABLE_SECTIONS: tuple[str, ...] = (
    "beliefs_active",
    "scoreboard",
    "clarifications",
    "narrative_active",
    "affective_now",
)

FORBIDDEN_SECTIONS: frozenset[str] = frozenset(
    {
        "control",
        "temporal",
        "spatial",
        "grounding",
        "history_active",
        "history_recent",
        "task_state",
        "task_artifacts",
        "meta",
        "telemetry",
        "persona",
        "place_registry",
        "artifacts_warm",
        "beliefs_history",
        "beliefs_warm",
        "narrative_archive",
    }
)

SECTION_APPLY_OPERATIONS: dict[str, frozenset[str]] = {
    "beliefs_active": frozenset(
        {"add_fact", "update", "update_confidence", "pin_fact", "unpin_fact", "clear"}
    ),
    "scoreboard": frozenset(
        {
            "push_question",
            "pop_question",
            "answer_question",
            "add_referent",
            "set_salience",
            "push_topic",
            "set_user_intent",
            "add_commitment",
            "fulfill_commitment",
            "cancel_commitment",
        }
    ),
    "clarifications": frozenset(
        {
            "request",
            "answer",
            "cancel",
            "expire",
            "expire_old",
            "set_blocking",
            "clear_blocking",
            "update_priority",
            "clear",
        }
    ),
    "narrative_active": frozenset(
        {
            "create_thread",
            "switch_to",
            "pause_thread",
            "resolve_thread",
            "archive_thread",
            "update_thread",
            "record_turn",
            "clear",
        }
    ),
    "affective_now": frozenset(
        {
            "update",
            "update_emotion",
            "update_dimensions",
            "set_empathy_needed",
            "set_celebration_appropriate",
            "clear",
        }
    ),
}

# Snapshot of MutationGuard.VALID_OPERATIONS relevant to M1. Tests assert the
# classifier registry stays within the live guard set without forcing this
# production module to import deep SessionState internals.
GUARD_VALID_OPERATIONS_SNAPSHOT: frozenset[str] = frozenset(
    {
        "add_fact",
        "create_thread",
        "switch_to",
        "pause_thread",
        "resolve_thread",
        "archive_thread",
        "update_thread",
        "update",
        "update_confidence",
        "add_referent",
        "push_question",
        "pop_question",
        "push_topic",
        "add_commitment",
        "fulfill_commitment",
        "cancel_commitment",
        "answer",
        "request",
        "clear",
        "record_turn",
    }
)

# Guard-safe but intentionally not model-visible in V0.
POLICY_EXCLUDED_OPERATIONS: dict[str, frozenset[str]] = {
    "beliefs_active": frozenset({"update", "clear"}),
    "clarifications": frozenset({"clear"}),
    "narrative_active": frozenset({"record_turn", "clear"}),
    "affective_now": frozenset({"clear"}),
}

GUARD_APPLY_MISMATCHES: dict[str, frozenset[str]] = {
    section: frozenset(ops.difference(GUARD_VALID_OPERATIONS_SNAPSHOT))
    for section, ops in SECTION_APPLY_OPERATIONS.items()
}

CLASSIFIER_OPERATION_REGISTRY: dict[str, tuple[str, ...]] = {
    section: tuple(
        sorted(
            SECTION_APPLY_OPERATIONS[section]
            .intersection(GUARD_VALID_OPERATIONS_SNAPSHOT)
            .difference(POLICY_EXCLUDED_OPERATIONS.get(section, frozenset()))
        )
    )
    for section in LLM_WRITABLE_SECTIONS
}

SHORTHAND_OPERATION_REJECTIONS: frozenset[str] = frozenset({"switch", "resume", "close"})


@dataclass(frozen=True)
class TargetValidation:
    """Result of validating a mutation section/operation target."""

    ok: bool
    reason: str = ""


def allowed_operations(section: str) -> tuple[str, ...]:
    """Return classifier-visible operations for one section."""

    return CLASSIFIER_OPERATION_REGISTRY.get(str(section), ())


def allowed_operation_pairs() -> set[tuple[str, str]]:
    """Return all classifier-visible section/operation pairs."""

    return {
        (section, operation)
        for section, operations in CLASSIFIER_OPERATION_REGISTRY.items()
        for operation in operations
    }


def validate_target(section: str, operation: str) -> TargetValidation:
    """Validate a model-proposed section/operation target."""

    section = str(section or "")
    operation = str(operation or "")
    if section in FORBIDDEN_SECTIONS:
        return TargetValidation(False, f"forbidden section: {section}")
    if section not in LLM_WRITABLE_SECTIONS:
        return TargetValidation(False, f"unknown or non-writable section: {section}")
    if operation in SHORTHAND_OPERATION_REJECTIONS:
        return TargetValidation(False, f"shorthand operation is not allowed: {operation}")
    if operation not in CLASSIFIER_OPERATION_REGISTRY[section]:
        return TargetValidation(False, f"operation not allowed for {section}: {operation}")
    return TargetValidation(True)
