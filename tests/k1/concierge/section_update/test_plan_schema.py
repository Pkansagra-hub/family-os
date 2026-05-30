"""M1.I1 SectionUpdate runtime-free contract types."""

from __future__ import annotations

import pytest

from k1.concierge.section_update.types import (
    ApplyTiming,
    CommitClass,
    RejectedCandidate,
    SectionMutation,
    SectionUpdateContractError,
    SectionUpdateInput,
    SectionUpdatePlan,
    SectionUpdateValidation,
    TurnStateOverlay,
)


def _mutation() -> SectionMutation:
    return SectionMutation(
        section="beliefs_active",
        operation="add_fact",
        data={"subject": "user", "predicate": "prefers", "obj": "quiet"},
        confidence=0.91,
        reason="User stated a durable preference.",
        commit_class=CommitClass.NEXT_TURN_CONTINUITY,
    )


def test_section_update_input_round_trips() -> None:
    original = SectionUpdateInput(
        turn_id="turn-1",
        session_id="session-1",
        cognitive_trace_id="trace-1",
        prompt_mode="STANDARD",
        fsm_state="COMPANIONING",
        bus_topic="k1.response.final.v1",
        user_turn={"text": "I prefer quiet rooms"},
        assistant_turn={"final_text": "Got it."},
        session_snapshot={"snapshot_version": "snap-1"},
        constraints={"classifier_mode": "offline_stub"},
    )

    restored = SectionUpdateInput.from_dict(original.to_dict())

    assert restored.to_dict() == original.to_dict()


def test_section_update_plan_round_trips_with_nested_types() -> None:
    original = SectionUpdatePlan(
        plan_id="plan-1",
        turn_id="turn-1",
        session_id="session-1",
        snapshot_version="snap-1",
        classifier_version="classifier-v1",
        apply_timing=ApplyTiming.ASYNC_AFTER_RESPONSE,
        mutations=[_mutation()],
        overlay=TurnStateOverlay(turn_id="turn-1", sections={"scoreboard": {"topic": "x"}}),
        rejected_candidates=[RejectedCandidate(section="all", reason="nothing else needed")],
        validation=SectionUpdateValidation(schema_valid=True),
    )

    restored = SectionUpdatePlan.from_dict(original.to_dict())

    assert restored.to_dict() == original.to_dict()
    assert restored.plan_idempotency_key == "session-1:turn-1:snap-1:classifier-v1"


def test_noop_plan_is_empty_mutations_only() -> None:
    plan = SectionUpdatePlan.noop(
        plan_id="noop-1",
        turn_id="turn-1",
        session_id="session-1",
        reason="low-signal greeting",
    )

    assert plan.is_noop is True
    assert plan.apply_timing == ApplyTiming.NO_OP
    assert plan.mutations == []
    assert plan.rejected_candidates[0].reason == "low-signal greeting"


def test_noop_timing_cannot_mix_with_mutations() -> None:
    with pytest.raises(SectionUpdateContractError, match="no_op"):
        SectionUpdatePlan(
            plan_id="bad-noop",
            turn_id="turn-1",
            session_id="session-1",
            apply_timing=ApplyTiming.NO_OP,
            mutations=[_mutation()],
        )


def test_mutation_rejects_missing_section() -> None:
    with pytest.raises(SectionUpdateContractError, match="section"):
        SectionMutation.from_dict(
            {
                "operation": "add_fact",
                "data": {},
                "confidence": 0.8,
                "reason": "missing section",
                "commit_class": "next_turn_continuity",
            }
        )


def test_mutation_rejects_bad_confidence() -> None:
    with pytest.raises(SectionUpdateContractError, match="confidence"):
        SectionMutation(
            section="beliefs_active",
            operation="add_fact",
            data={},
            confidence=1.5,
            reason="bad confidence",
            commit_class="next_turn_continuity",
        )


def test_plan_rejects_invalid_apply_timing() -> None:
    with pytest.raises(SectionUpdateContractError, match="apply_timing"):
        SectionUpdatePlan(
            plan_id="plan-1",
            turn_id="turn-1",
            session_id="session-1",
            apply_timing="eventually",
            mutations=[],
        )
