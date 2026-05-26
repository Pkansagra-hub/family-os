"""M2.I3 active section-update apply path through writer_port only."""

from __future__ import annotations

from k1.concierge.section_update.apply import apply_section_update_plan
from k1.concierge.section_update.events import SectionUpdateCompletionStatus
from k1.concierge.section_update.idempotency import SectionUpdateIdempotencyStore
from k1.concierge.section_update.plan_compiler import PlanCompiler
from k1.concierge.section_update.types import SectionMutation, SectionUpdatePlan
from k1.sessionstate.ports.writer import (
    BatchResult,
    MutationResponse,
    RejectionCategory,
)


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


class _Writer:
    def __init__(self, mode: str = "approved") -> None:
        self.mode = mode
        self.calls = []

    def batch_mutations(self, batch):
        self.calls.append(batch)
        if self.mode == "raise":
            raise RuntimeError("writer down")
        responses = []
        for request in batch.requests:
            if self.mode == "rejected":
                responses.append(
                    MutationResponse.rejected(
                        request_id=request.request_id,
                        section=request.section,
                        operation=request.operation,
                        reason="guard rejected",
                        category=RejectionCategory.VALIDATION,
                    )
                )
            else:
                responses.append(
                    MutationResponse.approved(
                        request_id=request.request_id,
                        section=request.section,
                        operation=request.operation,
                        new_size_bytes=128,
                        bytes_delta=32,
                        available_bytes=4096,
                    )
                )
        return BatchResult.from_responses(batch.batch_id, responses)


def test_noop_plan_does_not_call_writer_port() -> None:
    writer = _Writer()

    result = apply_section_update_plan(_plan(), writer_port=writer)

    assert result.status == SectionUpdateCompletionStatus.NOOP
    assert writer.calls == []
    assert result.writer_called is False


def test_invalid_plan_does_not_call_writer_port() -> None:
    writer = _Writer()

    result = apply_section_update_plan(_plan(_mutation("control", "set")), writer_port=writer)

    assert result.status == SectionUpdateCompletionStatus.REJECTED
    assert writer.calls == []
    assert result.diagnostics[0]["code"] == "invalid_target"


def test_stale_plan_does_not_call_writer_port() -> None:
    writer = _Writer()

    result = apply_section_update_plan(
        _plan(_mutation(), snapshot_version="old"),
        writer_port=writer,
        current_snapshot_version="new",
    )

    assert result.status == SectionUpdateCompletionStatus.STALE
    assert writer.calls == []
    assert result.diagnostics[0]["code"] == "stale_snapshot_version"


def test_duplicate_plan_does_not_call_writer_port() -> None:
    writer = _Writer()
    compiler = PlanCompiler(idempotency_store=SectionUpdateIdempotencyStore())
    plan = _plan(_mutation())
    first = apply_section_update_plan(plan, writer_port=writer, compiler=compiler)
    second = apply_section_update_plan(plan, writer_port=writer, compiler=compiler)

    assert first.status == SectionUpdateCompletionStatus.APPLIED
    assert second.status == SectionUpdateCompletionStatus.DUPLICATE
    assert len(writer.calls) == 1


def test_valid_plan_calls_writer_batch_once_with_classifier_metadata() -> None:
    writer = _Writer()

    result = apply_section_update_plan(
        _plan(_mutation()),
        writer_port=writer,
        current_snapshot_version="snap-1",
    )

    assert result.status == SectionUpdateCompletionStatus.APPLIED
    assert len(writer.calls) == 1
    batch = writer.calls[0]
    assert batch.writer_id == "tool:section_update_classifier"
    assert batch.cognitive_trace_id == "trace-1"
    assert batch.requests[0].metadata["section_update_plan_id"] == "plan-1"
    assert batch.requests[0].metadata["commit_class"] == "next_turn_continuity"
    assert result.writer_summary["applied_count"] == 1
    assert result.writer_summary["responses"][0]["section"] == "beliefs_active"


def test_writer_rejection_is_surfaced_as_completion_status() -> None:
    writer = _Writer(mode="rejected")

    result = apply_section_update_plan(_plan(_mutation()), writer_port=writer)

    assert result.status == SectionUpdateCompletionStatus.WRITER_REJECTED
    assert len(writer.calls) == 1
    assert result.writer_summary["rejected_count"] == 1
    assert result.writer_summary["responses"][0]["reason"] == "guard rejected"


def test_writer_exception_degrades_to_writer_failed_without_retry() -> None:
    writer = _Writer(mode="raise")

    result = apply_section_update_plan(_plan(_mutation()), writer_port=writer)

    assert result.status == SectionUpdateCompletionStatus.WRITER_FAILED
    assert len(writer.calls) == 1
    assert result.writer_result is None
    assert result.diagnostics[0]["code"] == "writer_failed"
