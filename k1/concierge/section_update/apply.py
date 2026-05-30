"""Apply compiled section-update plans through the SessionState writer port."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from k1.concierge.section_update.events import SectionUpdateCompletionStatus
from k1.concierge.section_update.plan_compiler import (
    CompileResult,
    CompileStatus,
    PlanCompiler,
)
from k1.concierge.section_update.types import SectionUpdatePlan


@dataclass
class SectionUpdateApplyResult:
    """Normalized result of compiling and optionally applying a plan."""

    status: SectionUpdateCompletionStatus
    compile_result: CompileResult
    writer_result: Any | None = None
    writer_summary: dict[str, Any] = field(default_factory=dict)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)

    @property
    def writer_called(self) -> bool:
        return self.writer_result is not None

    @property
    def ok(self) -> bool:
        return self.status in {
            SectionUpdateCompletionStatus.APPLIED,
            SectionUpdateCompletionStatus.NOOP,
        }


def apply_section_update_plan(
    plan: SectionUpdatePlan | Mapping[str, Any],
    *,
    writer_port: Any,
    compiler: PlanCompiler | None = None,
    current_snapshot_version: str | None = None,
    current_snapshot_epoch: str | None = None,
) -> SectionUpdateApplyResult:
    """Compile and apply a section-update plan through ``writer_port``.

    Invalid, stale, duplicate, and no-op plans return without calling the
    writer. Valid compiled plans call ``writer_port.batch_mutations`` once.
    """

    compiler = compiler or PlanCompiler()
    compile_result = compiler.compile(
        plan,
        current_snapshot_version=current_snapshot_version,
        current_snapshot_epoch=current_snapshot_epoch,
    )
    if not compile_result.writer_call_required:
        return SectionUpdateApplyResult(
            status=_status_from_compile(compile_result.status),
            compile_result=compile_result,
            diagnostics=[item.to_dict() for item in compile_result.diagnostics],
        )

    assert compile_result.batch_request is not None
    try:
        writer_result = writer_port.batch_mutations(compile_result.batch_request)
    except Exception as exc:  # noqa: BLE001 - active lifecycle degrades to diagnostic status.
        return SectionUpdateApplyResult(
            status=SectionUpdateCompletionStatus.WRITER_FAILED,
            compile_result=compile_result,
            writer_result=None,
            diagnostics=[{"code": "writer_failed", "message": str(exc)}],
        )

    summary = summarize_writer_result(writer_result)
    return SectionUpdateApplyResult(
        status=_status_from_writer_summary(summary),
        compile_result=compile_result,
        writer_result=writer_result,
        writer_summary=summary,
    )


def summarize_writer_result(writer_result: Any) -> dict[str, Any]:
    """Return a mutation-summary-compatible, payload-free writer summary."""

    responses = list(getattr(writer_result, "responses", []) or [])
    return {
        "batch_id": str(getattr(writer_result, "batch_id", "") or ""),
        "total_requests": int(getattr(writer_result, "total_requests", len(responses)) or 0),
        "applied_count": int(getattr(writer_result, "applied_count", 0) or 0),
        "rejected_count": int(getattr(writer_result, "rejected_count", 0) or 0),
        "failed_count": int(getattr(writer_result, "failed_count", 0) or 0),
        "cancelled_count": int(getattr(writer_result, "cancelled_count", 0) or 0),
        "total_bytes_delta": int(getattr(writer_result, "total_bytes_delta", 0) or 0),
        "stopped_early": bool(getattr(writer_result, "stopped_early", False)),
        "responses": [_summarize_response(item) for item in responses],
    }


def _summarize_response(response: Any) -> dict[str, Any]:
    status = getattr(response, "status", "")
    if hasattr(status, "value"):
        status = status.value
    return {
        "section": str(getattr(response, "section", "") or ""),
        "operation": str(getattr(response, "operation", "") or ""),
        "status": str(status or ""),
        "approved": bool(getattr(response, "approved", False)),
        "reason": str(getattr(response, "reason", "") or getattr(response, "error", "") or ""),
    }


def _status_from_compile(status: CompileStatus) -> SectionUpdateCompletionStatus:
    return {
        CompileStatus.NOOP: SectionUpdateCompletionStatus.NOOP,
        CompileStatus.REJECTED: SectionUpdateCompletionStatus.REJECTED,
        CompileStatus.STALE: SectionUpdateCompletionStatus.STALE,
        CompileStatus.DUPLICATE: SectionUpdateCompletionStatus.DUPLICATE,
    }.get(status, SectionUpdateCompletionStatus.REJECTED)


def _status_from_writer_summary(summary: Mapping[str, Any]) -> SectionUpdateCompletionStatus:
    total = int(summary.get("total_requests", 0) or 0)
    applied = int(summary.get("applied_count", 0) or 0)
    rejected = int(summary.get("rejected_count", 0) or 0)
    failed = int(summary.get("failed_count", 0) or 0)
    cancelled = int(summary.get("cancelled_count", 0) or 0)
    if total > 0 and applied == total and not rejected and not failed and not cancelled:
        return SectionUpdateCompletionStatus.APPLIED
    if applied > 0:
        return SectionUpdateCompletionStatus.PARTIAL
    if failed > 0:
        return SectionUpdateCompletionStatus.WRITER_FAILED
    return SectionUpdateCompletionStatus.WRITER_REJECTED


__all__ = [
    "SectionUpdateApplyResult",
    "apply_section_update_plan",
    "summarize_writer_result",
]
