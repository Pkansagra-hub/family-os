"""Section-update lifecycle event payload helpers."""

from __future__ import annotations

from enum import Enum
from typing import Any

from k1.concierge.section_update.idempotency import build_plan_idempotency_key
from k1.concierge.section_update.plan_compiler import CompileResult
from k1.concierge.section_update.types import SectionUpdateInput, SectionUpdatePlan


class SectionUpdateCompletionStatus(str, Enum):
    """Lifecycle completion statuses for section-update diagnostics."""

    REQUESTED = "requested"
    SHADOW_NOOP = "shadow_noop"
    SHADOW_PLAN = "shadow_plan"
    NOOP = "noop"
    REJECTED = "rejected"
    STALE = "stale"
    DUPLICATE = "duplicate"
    APPLIED = "applied"
    PARTIAL = "partial"
    WRITER_REJECTED = "writer_rejected"
    WRITER_FAILED = "writer_failed"
    TIMED_OUT = "timed_out"
    PROVIDER_FAILED = "provider_failed"
    DEGRADED_NOOP = "degraded_noop"


def build_section_update_requested_payload(
    input_data: SectionUpdateInput,
    *,
    mode: str,
    classifier_version: str = "section-update-v0",
) -> dict[str, Any]:
    """Build the public request diagnostic payload without prompt dumps."""

    snapshot_version = _snapshot_value(input_data, "snapshot_version")
    snapshot_source_epoch = _snapshot_value(input_data, "snapshot_source_epoch")
    return {
        "turn_id": input_data.turn_id,
        "session_id": input_data.session_id,
        "cognitive_trace_id": input_data.cognitive_trace_id,
        "mode": str(mode or ""),
        "prompt_mode": input_data.prompt_mode,
        "fsm_state": input_data.fsm_state,
        "bus_topic": input_data.bus_topic,
        "snapshot_version": snapshot_version,
        "snapshot_source_epoch": snapshot_source_epoch,
        "classifier_version": classifier_version,
        "plan_idempotency_key": build_plan_idempotency_key(
            session_id=input_data.session_id,
            turn_id=input_data.turn_id,
            snapshot_version=snapshot_version,
            classifier_version=classifier_version,
        ),
    }


def build_section_update_completed_payload(
    input_data: SectionUpdateInput,
    *,
    status: SectionUpdateCompletionStatus | str,
    mode: str,
    classifier_version: str = "section-update-v0",
    plan: SectionUpdatePlan | None = None,
    compile_result: CompileResult | None = None,
    writer_summary: dict[str, Any] | None = None,
    diagnostics: list[dict[str, Any]] | None = None,
    elapsed_ms: int = 0,
) -> dict[str, Any]:
    """Build the public completion diagnostic payload.

    The payload intentionally carries counts and ids, not raw prompt text,
    SessionState dumps, or mutation payload bodies.
    """

    status_text = status.value if isinstance(status, SectionUpdateCompletionStatus) else str(status)
    snapshot_version = _snapshot_value(input_data, "snapshot_version")
    payload: dict[str, Any] = {
        "turn_id": input_data.turn_id,
        "session_id": input_data.session_id,
        "cognitive_trace_id": input_data.cognitive_trace_id,
        "mode": str(mode or ""),
        "status": status_text,
        "prompt_mode": input_data.prompt_mode,
        "fsm_state": input_data.fsm_state,
        "bus_topic": input_data.bus_topic,
        "snapshot_version": snapshot_version,
        "snapshot_source_epoch": _snapshot_value(input_data, "snapshot_source_epoch"),
        "classifier_version": classifier_version,
        "elapsed_ms": int(elapsed_ms or 0),
        "diagnostics": list(diagnostics or []),
    }
    if plan is not None:
        payload.update(
            {
                "plan_id": plan.plan_id,
                "plan_idempotency_key": plan.plan_idempotency_key,
                "apply_timing": plan.apply_timing.value,
                "mutation_count": len(plan.mutations),
                "rejected_candidate_count": len(plan.rejected_candidates),
                "overlay_present": plan.overlay is not None,
            }
        )
    else:
        payload.update(
            {
                "plan_id": "",
                "plan_idempotency_key": build_plan_idempotency_key(
                    session_id=input_data.session_id,
                    turn_id=input_data.turn_id,
                    snapshot_version=snapshot_version,
                    classifier_version=classifier_version,
                ),
                "mutation_count": 0,
                "rejected_candidate_count": 0,
                "overlay_present": False,
            }
        )
    if compile_result is not None:
        payload["compile"] = compile_result.to_summary()
    if writer_summary is not None:
        payload["writer"] = dict(writer_summary)
    return payload


def _snapshot_value(input_data: SectionUpdateInput, key: str) -> str:
    value = input_data.session_snapshot.get(key, "")
    return str(value or "")


__all__ = [
    "SectionUpdateCompletionStatus",
    "build_section_update_completed_payload",
    "build_section_update_requested_payload",
]
