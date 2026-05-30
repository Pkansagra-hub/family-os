"""M2.I6 dispatch-critical turn-state overlay helpers."""

from __future__ import annotations

from k1.concierge.section_update.overlay import (
    OVERLAY_TASK_PAYLOAD_KEY,
    attach_overlay_to_task_payload,
    build_dispatch_overlay_from_plan,
    degraded_turn_state_overlay,
    summarize_task_overlay,
)
from k1.concierge.section_update.types import (
    CommitClass,
    SectionMutation,
    SectionUpdatePlan,
)


def _mutation(
    *,
    section: str = "scoreboard",
    operation: str = "add_referent",
    commit_class: CommitClass = CommitClass.DISPATCH_CRITICAL,
) -> SectionMutation:
    return SectionMutation(
        section=section,
        operation=operation,
        data={"text": "it", "entity_id": "hotel-1", "tier": "HIGH"},
        confidence=0.91,
        reason="Reference must be visible before Back starts.",
        commit_class=commit_class,
    )


def _plan(*mutations: SectionMutation) -> SectionUpdatePlan:
    return SectionUpdatePlan(
        plan_id="plan-1",
        turn_id="session-1:4",
        session_id="session-1",
        snapshot_version="snap-1",
        snapshot_source_epoch="11",
        classifier_version="classifier-v1",
        mutations=list(mutations),
    )


def test_dispatch_overlay_contains_only_dispatch_critical_mutations() -> None:
    overlay = build_dispatch_overlay_from_plan(
        _plan(
            _mutation(),
            _mutation(operation="push_topic", commit_class=CommitClass.NEXT_TURN_CONTINUITY),
        ),
        durable=False,
        status="timed_out",
        degraded_reason="writer_timeout",
    )

    assert overlay is not None
    assert overlay["turn_id"] == "session-1:4"
    assert overlay["durable"] is False
    assert overlay["degraded_reason"] == "writer_timeout"
    assert overlay["fields_applied"] == ["scoreboard.add_referent"]
    mutation = overlay["sections"]["scoreboard"]["mutations"][0]
    assert mutation["operation"] == "add_referent"
    assert mutation["data"] == {"text": "it", "entity_id": "hotel-1"}


def test_overlay_rejects_runtime_owned_sections_without_authority_payload() -> None:
    overlay = build_dispatch_overlay_from_plan(
        _plan(_mutation(section="control", operation="set_fsm_overlay")),
        durable=False,
        status="rejected",
    )

    assert overlay is not None
    assert overlay["sections"] == {}
    assert overlay["diagnostics"]["rejected"][0]["section"] == "control"
    assert overlay["diagnostics"]["rejected"][0]["reason"].startswith("forbidden section")


def test_degraded_overlay_makes_missing_critical_context_explicit() -> None:
    overlay = degraded_turn_state_overlay(
        turn_id="session-1:5",
        snapshot_version="snap-2",
        snapshot_source_epoch="22",
        degraded_reason="classifier_timeout",
    )

    task_payload = attach_overlay_to_task_payload({"task_id": "task-1"}, overlay)
    summary = summarize_task_overlay(task_payload)

    assert task_payload[OVERLAY_TASK_PAYLOAD_KEY]["sections"] == {}
    assert summary == {
        "present": True,
        "turn_id": "session-1:5",
        "durable": False,
        "status": "degraded",
        "degraded_reason": "classifier_timeout",
        "section_count": 0,
        "fields_applied": [],
    }
