"""M1.I3 whole-plan validation and BatchRequest compiler."""

from __future__ import annotations

from k1.concierge.section_update.plan_compiler import CompileStatus, PlanCompiler
from k1.concierge.section_update.types import SectionMutation, SectionUpdatePlan


def _mutation(section: str = "beliefs_active", operation: str = "add_fact") -> SectionMutation:
    return SectionMutation(
        section=section,
        operation=operation,
        data={"subject": "user", "predicate": "prefers", "obj": "quiet"},
        confidence=0.9,
        reason="User stated a durable preference.",
        commit_class="next_turn_continuity",
    )


def _plan(*mutations: SectionMutation, snapshot_version: str = "snap-1") -> SectionUpdatePlan:
    return SectionUpdatePlan(
        plan_id="plan-1",
        turn_id="turn-1",
        session_id="session-1",
        snapshot_version=snapshot_version,
        classifier_version="classifier-v1",
        mutations=list(mutations),
        cognitive_trace_id="trace-1",
    )


def test_valid_plan_compiles_to_ordered_batch_request() -> None:
    plan = _plan(
        _mutation("beliefs_active", "add_fact"),
        SectionMutation(
            section="scoreboard",
            operation="push_question",
            data={"text": "Where should the user sit?", "asked_by": "front"},
            confidence=0.8,
            reason="Conversation opened a new question.",
            commit_class="next_turn_continuity",
        ),
    )

    result = PlanCompiler().compile(plan, current_snapshot_version="snap-1")

    assert result.status == CompileStatus.COMPILED
    assert result.writer_call_required is True
    assert result.batch_request is not None
    assert result.batch_request.writer_id == "tool:section_update_classifier"
    assert result.batch_request.cognitive_trace_id == "trace-1"
    assert result.batch_request.stop_on_rejection is True
    assert [req.section for req in result.batch_request.requests] == [
        "beliefs_active",
        "scoreboard",
    ]
    assert [req.operation for req in result.batch_request.requests] == [
        "add_fact",
        "push_question",
    ]
    assert all(req.estimated_bytes > 0 for req in result.batch_request.requests)
    assert result.batch_request.requests[0].metadata["section_update_plan_id"] == "plan-1"
    assert result.batch_request.requests[0].metadata["commit_class"] == "next_turn_continuity"


def test_empty_mutations_compile_to_noop_without_batch() -> None:
    plan = _plan()

    result = PlanCompiler().compile(plan)

    assert result.status == CompileStatus.NOOP
    assert result.batch_request is None
    assert result.writer_call_required is False
    assert result.diagnostics[0].code == "noop"


def test_invalid_section_rejected_before_batch() -> None:
    plan = _plan(_mutation("control", "set"))

    result = PlanCompiler().compile(plan)

    assert result.status == CompileStatus.REJECTED
    assert result.batch_request is None
    assert result.diagnostics[0].code == "invalid_target"
    assert result.rejected_candidates[0].section == "control"


def test_guard_apply_mismatch_operation_rejected_before_batch() -> None:
    plan = _plan(_mutation("scoreboard", "answer_question"))

    result = PlanCompiler().compile(plan)
    assert result.status == CompileStatus.REJECTED
    assert result.batch_request is None
    assert "operation not allowed" in result.diagnostics[0].message


def test_stale_snapshot_rejected_before_batch() -> None:
    plan = _plan(_mutation(), snapshot_version="old-snap")

    result = PlanCompiler().compile(plan, current_snapshot_version="new-snap")

    assert result.status == CompileStatus.STALE
    assert result.batch_request is None
    assert result.diagnostics[0].code == "stale_snapshot_version"


def test_compiler_does_not_call_writer_port() -> None:
    plan = _plan(_mutation())
    compiler = PlanCompiler()

    result = compiler.compile(plan)

    assert result.status == CompileStatus.COMPILED
    assert result.batch_request is not None
    assert not hasattr(compiler, "writer_port")
