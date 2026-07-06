"""Section-update classifier lifecycle helpers."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
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

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Main-loop reference (set once from the event-loop thread during boot).
# ---------------------------------------------------------------------------
_main_loop: asyncio.AbstractEventLoop | None = None
_main_loop_lock = threading.Lock()


def set_section_update_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Cache the main event loop so worker daemon threads can schedule
    classifier coroutines on it via ``run_coroutine_threadsafe``."""
    global _main_loop
    with _main_loop_lock:
        _main_loop = loop


def _resolve_main_loop() -> asyncio.AbstractEventLoop:
    """Return the cached main loop, falling back to a new loop."""
    global _main_loop
    with _main_loop_lock:
        if _main_loop is not None and not _main_loop.is_closed():
            return _main_loop
    loop = asyncio.new_event_loop()
    with _main_loop_lock:
        if _main_loop is None:
            _main_loop = loop
    return loop


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
    """Run the async classifier behind a bounded synchronous gate.

    Two paths:
      - **Worker daemon thread**: schedules the coroutine on the main
        event loop via ``asyncio.run_coroutine_threadsafe`` and blocks
        on ``future.result(timeout)``.  Main-loop aiohttp sessions are
        safe because the coroutine runs on the main loop.
      - **Main event-loop thread** (FSM controller path): cannot block
        the loop, so spawns a short-lived daemon thread with a fresh
        event loop (``new_event_loop()`` + ``run_until_complete``).
    """

    started = time.perf_counter()
    loop = _resolve_main_loop()

    # Are we on the main event loop's thread?  And is that loop actually
    # running so we can schedule work onto it?
    try:
        running = asyncio.get_running_loop()
        on_main_thread = running is loop
    except RuntimeError:
        on_main_thread = False

    loop_usable = loop is not None and loop.is_running()

    if on_main_thread or not loop_usable:
        # Either we are on the main loop (can't block) or the cached loop is
        # not running (tests / non-asyncio boot).  Spawn a daemon thread.
        return _classify_in_daemon_thread(input_data, classifier, timeout_ms, started)
    else:
        # Worker daemon thread — schedule onto the main loop.
        return _classify_on_main_loop(loop, input_data, classifier, timeout_ms, started)


def _classify_on_main_loop(
    loop: asyncio.AbstractEventLoop,
    input_data: SectionUpdateInput,
    classifier: ISectionUpdateClassifier,
    timeout_ms: int,
    started: float,
) -> SectionUpdateClassificationResult:
    """Schedule classifier on the main loop, blocking with a timeout."""
    future = asyncio.run_coroutine_threadsafe(classifier.classify(input_data), loop)
    try:
        value = future.result(timeout=max(0.001, timeout_ms / 1000.0))
    except concurrent.futures.TimeoutError:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return SectionUpdateClassificationResult(
            status=SectionUpdateCompletionStatus.TIMED_OUT,
            plan=None,
            diagnostics=[{"code": "classifier_timeout", "message": f"timeout_ms={timeout_ms}"}],
            elapsed_ms=elapsed_ms,
        )
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return SectionUpdateClassificationResult(
            status=SectionUpdateCompletionStatus.PROVIDER_FAILED,
            plan=None,
            diagnostics=[{"code": "provider_failed", "message": str(exc)}],
            elapsed_ms=elapsed_ms,
        )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return _build_classification_result(value, elapsed_ms)


def _classify_in_daemon_thread(
    input_data: SectionUpdateInput,
    classifier: ISectionUpdateClassifier,
    timeout_ms: int,
    started: float,
) -> SectionUpdateClassificationResult:
    """Run classifier in a daemon thread with a fresh event loop.

    Used only when the caller is on the main event-loop thread (FSM
    controller) and cannot block the loop.  Uses explicit
    ``new_event_loop()`` + ``run_until_complete`` instead of
    ``asyncio.run()`` to avoid Python 3.13 daemon-thread issues.
    """

    result_queue: "queue.Queue[tuple[str, Any]]" = queue.Queue(maxsize=1)

    def _run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(classifier.classify(input_data))
            result_queue.put(("ok", result))
        except Exception as exc:
            result_queue.put(("error", exc))
        finally:
            loop.close()

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
    return _build_classification_result(value, elapsed_ms)


def _build_classification_result(
    value: Any,
    elapsed_ms: int,
) -> SectionUpdateClassificationResult:
    """Convert a raw classifier return value into a result struct."""
    if isinstance(value, SectionUpdatePlan):
        plan = value
    elif isinstance(value, Mapping):
        try:
            plan = SectionUpdatePlan.from_dict(value)
        except Exception as exc:
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
        status=(
            SectionUpdateCompletionStatus.NOOP
            if plan.is_noop
            else SectionUpdateCompletionStatus.REQUESTED
        ),
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
