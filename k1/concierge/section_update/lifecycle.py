"""Section-update classifier lifecycle helpers."""

from __future__ import annotations

import asyncio
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Mapping

from k1.bus.envelope import Envelope
from k1.concierge.bus.builders import (
    build_section_update_completed,
    build_section_update_requested,
)
from k1.concierge.section_update.classifier import ISectionUpdateClassifier
from k1.concierge.section_update.events import (
    SectionUpdateCompletionStatus,
    build_section_update_completed_payload,
    build_section_update_requested_payload,
)
from k1.concierge.section_update.types import SectionUpdateInput, SectionUpdatePlan


@dataclass(frozen=True)
class SectionUpdateLifecycleResult:
    """Result returned by a lifecycle helper."""

    status: SectionUpdateCompletionStatus
    mode: str
    input_data: SectionUpdateInput
    plan: SectionUpdatePlan | None
    requested_event: Envelope
    completed_event: Envelope
    elapsed_ms: int


@dataclass(frozen=True)
class SectionUpdateClassificationResult:
    """Synchronous wrapper result for async classifier execution."""

    status: SectionUpdateCompletionStatus
    plan: SectionUpdatePlan | None
    diagnostics: list[dict[str, Any]]
    elapsed_ms: int


async def run_shadow_section_update(
    *,
    input_data: SectionUpdateInput,
    classifier: ISectionUpdateClassifier,
    bus: Any,
    parent_id: int = 0,
    mode: str = "shadow",
    classifier_version: str = "section-update-v0",
) -> SectionUpdateLifecycleResult:
    """Publish request/completion diagnostics for shadow classification.

    Shadow mode never receives a writer port and never mutates SessionState;
    it only observes classifier output and publishes lifecycle diagnostics.
    """

    started = time.perf_counter()
    requested_event = build_section_update_requested(
        build_section_update_requested_payload(
            input_data,
            mode=mode,
            classifier_version=classifier_version,
        ),
        parent_id=parent_id,
    )
    bus.publish(requested_event)

    plan: SectionUpdatePlan | None = None
    diagnostics: list[dict[str, Any]] = []
    try:
        plan = await classifier.classify(input_data)
        status = (
            SectionUpdateCompletionStatus.SHADOW_NOOP
            if plan.is_noop
            else SectionUpdateCompletionStatus.SHADOW_PLAN
        )
        classifier_version = plan.classifier_version
    except Exception as exc:  # noqa: BLE001 - lifecycle boundary degrades to diagnostics.
        status = SectionUpdateCompletionStatus.PROVIDER_FAILED
        diagnostics.append({"code": "provider_failed", "message": str(exc)})

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    completed_event = build_section_update_completed(
        build_section_update_completed_payload(
            input_data,
            status=status,
            mode=mode,
            classifier_version=classifier_version,
            plan=plan,
            diagnostics=diagnostics,
            elapsed_ms=elapsed_ms,
        ),
        parent_id=parent_id,
    )
    bus.publish(completed_event)
    return SectionUpdateLifecycleResult(
        status=status,
        mode=mode,
        input_data=input_data,
        plan=plan,
        requested_event=requested_event,
        completed_event=completed_event,
        elapsed_ms=elapsed_ms,
    )


def classify_section_update_blocking(
    *,
    input_data: SectionUpdateInput,
    classifier: ISectionUpdateClassifier,
    timeout_ms: int,
) -> SectionUpdateClassificationResult:
    """Run the async classifier behind a bounded synchronous FSM gate.

    The classifier runs in a daemon thread with its own event loop so a sync
    bus handler can wait for a bounded result without trying to re-enter the
    current asyncio loop. The worker thread only returns a plan; writer apply
    remains on the caller thread after the timeout gate succeeds.
    """

    started = time.perf_counter()
    result_queue: "queue.Queue[tuple[str, Any]]" = queue.Queue(maxsize=1)

    def _run() -> None:
        try:
            result_queue.put(("ok", asyncio.run(classifier.classify(input_data))))
        except Exception as exc:  # noqa: BLE001 - returned as lifecycle diagnostic.
            result_queue.put(("error", exc))

    thread = threading.Thread(target=_run, name="section-update-classifier", daemon=True)
    thread.start()
    try:
        status, value = result_queue.get(timeout=max(0.001, timeout_ms / 1000.0))
    except queue.Empty:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return SectionUpdateClassificationResult(
            status=SectionUpdateCompletionStatus.TIMED_OUT,
            plan=None,
            diagnostics=[{"code": "classifier_timeout", "message": f"timeout_ms={timeout_ms}"}],
            elapsed_ms=elapsed_ms,
        )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if status == "error":
        return SectionUpdateClassificationResult(
            status=SectionUpdateCompletionStatus.PROVIDER_FAILED,
            plan=None,
            diagnostics=[{"code": "provider_failed", "message": str(value)}],
            elapsed_ms=elapsed_ms,
        )
    if isinstance(value, SectionUpdatePlan):
        plan = value
    elif isinstance(value, Mapping):
        try:
            plan = SectionUpdatePlan.from_dict(value)
        except Exception as exc:  # noqa: BLE001 - malformed model output is diagnostic only.
            return SectionUpdateClassificationResult(
                status=SectionUpdateCompletionStatus.REJECTED,
                plan=None,
                diagnostics=[{"code": "invalid_schema", "message": str(exc)}],
                elapsed_ms=elapsed_ms,
            )
    else:
        return SectionUpdateClassificationResult(
            status=SectionUpdateCompletionStatus.REJECTED,
            plan=None,
            diagnostics=[
                {
                    "code": "invalid_schema",
                    "message": f"classifier returned {type(value).__name__}",
                }
            ],
            elapsed_ms=elapsed_ms,
        )
    return SectionUpdateClassificationResult(
        status=SectionUpdateCompletionStatus.NOOP if plan.is_noop else SectionUpdateCompletionStatus.REQUESTED,
        plan=plan,
        diagnostics=[],
        elapsed_ms=elapsed_ms,
    )


__all__ = [
    "SectionUpdateClassificationResult",
    "SectionUpdateLifecycleResult",
    "classify_section_update_blocking",
    "run_shadow_section_update",
]
