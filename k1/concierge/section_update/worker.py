"""Background section-update worker for completed Concierge turns."""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Mapping

from k1.bus.envelope import Envelope
from k1.bus.ports.bus import SubscriptionHandle
from k1.concierge.bus.builders import (
    build_section_update_completed,
    build_section_update_requested,
)
from k1.concierge.bus.topics import TOPIC_TURN_COMPLETED
from k1.concierge.section_update.apply import apply_section_update_plan
from k1.concierge.section_update.classifier import ISectionUpdateClassifier
from k1.concierge.section_update.events import (
    SectionUpdateCompletionStatus,
    build_section_update_completed_payload,
    build_section_update_requested_payload,
)
from k1.concierge.section_update.idempotency import SectionUpdateIdempotencyStore
from k1.concierge.section_update.input_builder import build_section_update_input
from k1.concierge.section_update.lifecycle import classify_section_update_blocking
from k1.concierge.section_update.plan_compiler import PlanCompiler
from k1.concierge.section_update.types import SectionUpdateInput, SectionUpdatePlan

logger = logging.getLogger(__name__)

_BACKGROUND_APPLY_MODES = {"background_apply", "apply"}
_SHADOW_MODES = {"shadow", "offline_stub"}
_DISABLED_MODES = {"", "off", "disabled", "none"}
_DEGRADED_MODES = {"degraded_noop"}


@dataclass(frozen=True)
class SectionUpdateWorkerConfig:
    """Runtime knobs for one per-session section-update worker."""

    mode: str = "background_apply"
    timeout_ms: int = 75_000
    queue_max: int = 128
    classifier_version: str = "section-update-v0"
    provider_id: str = ""
    model_id: str = ""


@dataclass
class SectionUpdateWorkerStats:
    """Payload-free worker counters used by health checks and M5 tracking."""

    running: bool = False
    mode: str = "background_apply"
    queue_depth: int = 0
    last_turn_id_seen: str = ""
    last_turn_id_completed: str = ""
    last_status: str = ""
    last_error_code: str = ""
    turn_completed_count: int = 0
    section_update_requested_count: int = 0
    section_update_completed_count: int = 0
    queue_full_count: int = 0
    duplicate_count: int = 0
    applied_count: int = 0
    noop_count: int = 0
    degraded_noop_count: int = 0
    provider_failed_count: int = 0
    timed_out_count: int = 0
    rejected_count: int = 0
    stale_count: int = 0
    writer_rejected_count: int = 0
    writer_failed_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class _QueuedTurn:
    envelope: Envelope


class SectionUpdateBackgroundWorker:
    """Consume completed turns and maintain cognitive SessionState in the background."""

    def __init__(
        self,
        *,
        session_id: str,
        bus: Any,
        state_manager: Any,
        writer_port: Any | None,
        classifier: ISectionUpdateClassifier | None,
        config: SectionUpdateWorkerConfig | None = None,
        idempotency_store: SectionUpdateIdempotencyStore | None = None,
    ) -> None:
        self.session_id = str(session_id or "")
        self._bus = bus
        self._state_manager = state_manager
        self._writer_port = writer_port
        self._classifier = classifier
        self._config = config or SectionUpdateWorkerConfig()
        self._mode = _normalize_mode(self._config.mode)
        self._idempotency = idempotency_store or SectionUpdateIdempotencyStore()
        self._queue: "queue.Queue[_QueuedTurn | None]" = queue.Queue(
            maxsize=max(1, int(self._config.queue_max or 1))
        )
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._subscription: SubscriptionHandle | None = None
        self._processed_turn_ids: set[str] = set()
        self._lock = threading.RLock()
        self._stats = SectionUpdateWorkerStats(mode=self._mode)

    @property
    def is_running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive() and not self._stop.is_set()

    @property
    def mode(self) -> str:
        return self._mode

    def start(self) -> None:
        """Subscribe to completed turns and start the background queue worker."""

        if self._mode in _DISABLED_MODES:
            return
        if self.is_running:
            return
        self._stop.clear()
        self._subscription = self._bus.subscribe(TOPIC_TURN_COMPLETED, self._on_turn_completed)
        self._thread = threading.Thread(
            target=self._run,
            name=f"section-update-worker:{self.session_id}",
            daemon=True,
        )
        self._thread.start()
        with self._lock:
            self._stats.running = True
            self._stats.mode = self._mode

    def stop(self, *, timeout_s: float = 5.0) -> None:
        """Stop accepting turns, unsubscribe, and join the worker thread."""

        self._stop.set()
        subscription = self._subscription
        self._subscription = None
        if subscription is not None:
            try:
                self._bus.unsubscribe(subscription)
            except Exception:
                logger.debug("section_update worker unsubscribe failed", exc_info=True)
        thread = self._thread
        if thread is not None and thread.is_alive():
            try:
                self._queue.put_nowait(None)
            except queue.Full:
                pass
        if thread is not None:
            thread.join(timeout=max(0.0, float(timeout_s)))
        with self._lock:
            self._stats.running = False
            self._stats.queue_depth = self._queue.qsize()

    def stats_snapshot(self) -> dict[str, Any]:
        with self._lock:
            snapshot = self._stats.to_dict()
        snapshot["running"] = self.is_running
        snapshot["queue_depth"] = self._queue.qsize()
        return snapshot

    def drain(self, *, timeout_s: float = 5.0) -> bool:
        """Wait until currently queued turns have been processed."""

        deadline = time.monotonic() + max(0.0, float(timeout_s))
        while time.monotonic() <= deadline:
            if self._queue.unfinished_tasks == 0:
                return True
            time.sleep(0.01)
        return self._queue.unfinished_tasks == 0

    def _on_turn_completed(self, envelope: Envelope) -> None:
        if self._stop.is_set() or self._mode in _DISABLED_MODES:
            return
        started = time.perf_counter()
        with self._lock:
            self._stats.turn_completed_count += 1
            self._stats.queue_depth = self._queue.qsize()
        try:
            self._queue.put_nowait(_QueuedTurn(envelope=envelope))
        except queue.Full:
            with self._lock:
                self._stats.queue_full_count += 1
                self._stats.last_error_code = "queue_full"
            logger.warning(
                "section_update worker queue full session=%s mode=%s",
                self.session_id,
                self._mode,
            )
            self._publish_queue_full(envelope, elapsed_ms=_elapsed_ms(started))

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                item = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                if item is None:
                    return
                self._process(item.envelope)
            finally:
                self._queue.task_done()

    def _process(self, envelope: Envelope) -> None:
        started = time.perf_counter()
        try:
            input_data = self._build_input(envelope)
        except Exception:  # noqa: BLE001 - background worker must fail closed.
            logger.warning("section_update worker failed to build input", exc_info=True)
            self._record_status(SectionUpdateCompletionStatus.DEGRADED_NOOP, "input_build_failed")
            return

        with self._lock:
            self._stats.last_turn_id_seen = input_data.turn_id
        if input_data.turn_id in self._processed_turn_ids:
            self._publish_requested(input_data, envelope)
            self._publish_completed(
                input_data,
                envelope,
                status=SectionUpdateCompletionStatus.DUPLICATE,
                diagnostics=[{"code": "duplicate_turn", "message": "turn already processed"}],
                elapsed_ms=_elapsed_ms(started),
            )
            return
        self._processed_turn_ids.add(input_data.turn_id)

        self._publish_requested(input_data, envelope)

        # Production path — no shadow / degraded toggles. The worker is
        # constructed by the kernel with an auto-instantiated classifier and a
        # bound writer_port; the only legitimate skip is a structural failure
        # (missing classifier or writer), which is logged loudly so operators
        # see the misconfiguration instead of silent no-ops.
        if self._classifier is None or self._writer_port is None:
            logger.error(
                "section_update worker misconfigured session=%s classifier=%s writer=%s — "
                "skipping turn; kernel must wire both ports.",
                self.session_id,
                type(self._classifier).__name__ if self._classifier else "None",
                type(self._writer_port).__name__ if self._writer_port else "None",
            )
            self._publish_completed(
                input_data,
                envelope,
                status=SectionUpdateCompletionStatus.DEGRADED_NOOP,
                diagnostics=[
                    {
                        "code": "worker_misconfigured",
                        "message": "classifier or writer_port missing",
                    }
                ],
                elapsed_ms=_elapsed_ms(started),
            )
            return

        classification = classify_section_update_blocking(
            input_data=input_data,
            classifier=self._classifier,
            timeout_ms=max(1, int(self._config.timeout_ms or 1)),
        )
        plan = classification.plan
        classifier_version = (
            plan.classifier_version if plan is not None else self._config.classifier_version
        )
        if plan is None:
            self._publish_completed(
                input_data,
                envelope,
                status=classification.status,
                diagnostics=classification.diagnostics,
                elapsed_ms=classification.elapsed_ms,
                classifier_version=classifier_version,
            )
            return

        apply_result = apply_section_update_plan(
            plan,
            writer_port=self._writer_port,
            compiler=PlanCompiler(idempotency_store=self._idempotency),
            current_snapshot_version=str(
                input_data.session_snapshot.get("snapshot_version", "") or ""
            ),
            current_snapshot_epoch=str(
                input_data.session_snapshot.get("snapshot_source_epoch", "") or ""
            ),
        )
        self._publish_completed(
            input_data,
            envelope,
            status=apply_result.status,
            plan=plan,
            compile_result=apply_result.compile_result,
            writer_summary=apply_result.writer_summary,
            diagnostics=apply_result.diagnostics,
            elapsed_ms=classification.elapsed_ms,
            classifier_version=classifier_version,
        )

    def _publish_queue_full(self, envelope: Envelope, *, elapsed_ms: int) -> None:
        try:
            input_data = self._build_input(envelope)
        except Exception:
            logger.debug("section_update worker queue_full input build failed", exc_info=True)
            self._record_status(SectionUpdateCompletionStatus.DEGRADED_NOOP, "queue_full")
            return
        self._publish_requested(input_data, envelope)
        self._publish_completed(
            input_data,
            envelope,
            status=SectionUpdateCompletionStatus.DEGRADED_NOOP,
            diagnostics=[{"code": "queue_full", "message": "section-update worker queue full"}],
            elapsed_ms=elapsed_ms,
        )

    def _build_input(self, envelope: Envelope) -> SectionUpdateInput:
        payload = _payload_dict(envelope)
        turn_number = _optional_int(payload.get("turn_number"))
        return build_section_update_input(
            envelope=envelope,
            ss=self._state_manager,
            turn_id=str(payload.get("turn_id", "") or ""),
            turn_number=turn_number,
            session_id=str(payload.get("session_id", "") or self.session_id),
            cognitive_trace_id=str(payload.get("cognitive_trace_id", "") or ""),
            user_text=str(payload.get("user_message", "") or payload.get("user_msg", "") or ""),
            assistant_text=str(
                payload.get("assistant_response", "") or payload.get("assistant_msg", "") or ""
            ),
            prompt_mode=str(payload.get("prompt_mode", "front_react") or "front_react"),
            fsm_state=str(payload.get("fsm_state", "") or ""),
            constraints={
                "mode": self._mode,
                "classifier_mode": self._mode,
                "timeout_ms": int(self._config.timeout_ms or 0),
                "classifier_version": self._config.classifier_version,
            },
        )

    def _publish_requested(self, input_data: SectionUpdateInput, envelope: Envelope) -> None:
        self._bus.publish(
            build_section_update_requested(
                build_section_update_requested_payload(
                    input_data,
                    mode=self._mode,
                    classifier_version=self._config.classifier_version,
                    provider_id=self._config.provider_id,
                    model_id=self._config.model_id,
                ),
                parent_id=envelope.envelope_id,
            )
        )
        with self._lock:
            self._stats.section_update_requested_count += 1

    def _publish_completed(
        self,
        input_data: SectionUpdateInput,
        envelope: Envelope,
        *,
        status: SectionUpdateCompletionStatus,
        plan: SectionUpdatePlan | None = None,
        compile_result: Any | None = None,
        writer_summary: dict[str, Any] | None = None,
        diagnostics: list[dict[str, Any]] | None = None,
        elapsed_ms: int = 0,
        classifier_version: str | None = None,
    ) -> None:
        payload = build_section_update_completed_payload(
            input_data,
            status=status,
            mode=self._mode,
            classifier_version=classifier_version or self._config.classifier_version,
            provider_id=self._config.provider_id,
            model_id=self._config.model_id,
            plan=plan,
            compile_result=compile_result,
            writer_summary=writer_summary,
            diagnostics=diagnostics,
            elapsed_ms=elapsed_ms,
        )
        self._bus.publish(build_section_update_completed(payload, parent_id=envelope.envelope_id))
        status_text = (
            status.value if isinstance(status, SectionUpdateCompletionStatus) else str(status)
        )
        logger.info(
            "section_update completed session=%s turn=%s mode=%s status=%s plan_ops=%s elapsed_ms=%d",
            self.session_id,
            input_data.turn_id,
            self._mode,
            status_text,
            (len(plan.mutations) if plan is not None else 0),
            int(elapsed_ms or 0),
        )
        self._record_status(status, _diagnostic_code(diagnostics), turn_id=input_data.turn_id)

    def _record_status(
        self,
        status: SectionUpdateCompletionStatus,
        error_code: str = "",
        *,
        turn_id: str = "",
    ) -> None:
        status_text = (
            status.value if isinstance(status, SectionUpdateCompletionStatus) else str(status)
        )
        with self._lock:
            self._stats.section_update_completed_count += 1
            self._stats.last_turn_id_completed = turn_id or self._stats.last_turn_id_completed
            self._stats.last_status = status_text
            self._stats.last_error_code = error_code
            self._stats.queue_depth = self._queue.qsize()
            if status == SectionUpdateCompletionStatus.APPLIED:
                self._stats.applied_count += 1
            elif status in {
                SectionUpdateCompletionStatus.NOOP,
                SectionUpdateCompletionStatus.SHADOW_NOOP,
            }:
                self._stats.noop_count += 1
            elif status == SectionUpdateCompletionStatus.DEGRADED_NOOP:
                self._stats.degraded_noop_count += 1
            elif status == SectionUpdateCompletionStatus.PROVIDER_FAILED:
                self._stats.provider_failed_count += 1
            elif status == SectionUpdateCompletionStatus.TIMED_OUT:
                self._stats.timed_out_count += 1
            elif status == SectionUpdateCompletionStatus.REJECTED:
                self._stats.rejected_count += 1
            elif status == SectionUpdateCompletionStatus.STALE:
                self._stats.stale_count += 1
            elif status == SectionUpdateCompletionStatus.DUPLICATE:
                self._stats.duplicate_count += 1
            elif status == SectionUpdateCompletionStatus.WRITER_REJECTED:
                self._stats.writer_rejected_count += 1
            elif status == SectionUpdateCompletionStatus.WRITER_FAILED:
                self._stats.writer_failed_count += 1


def _normalize_mode(mode: str) -> str:
    """Collapse legacy mode strings down to the two real states.

    Production has exactly two outcomes: the worker is OFF (disabled, no
    subscription, no processing) or it is ON and applies plans against
    SessionState via the bound writer port. Legacy ``shadow`` /
    ``offline_stub`` / ``degraded_noop`` values are intentionally remapped
    to ``background_apply`` — there is no observe-only mode any more.
    """

    normalized = str(mode or "").strip().lower()
    if normalized in _DISABLED_MODES:
        return "off"
    return "background_apply"


def _payload_dict(envelope: Envelope) -> dict[str, Any]:
    payload = envelope.payload
    if isinstance(payload, (bytes, bytearray)):
        if not payload:
            return {}
        try:
            data = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}
    if isinstance(payload, Mapping):
        return dict(payload)
    return {}


def _optional_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _diagnostic_code(diagnostics: list[dict[str, Any]] | None) -> str:
    if not diagnostics:
        return ""
    first = diagnostics[0]
    return str(first.get("code", "") or "") if isinstance(first, dict) else ""


__all__ = [
    "SectionUpdateBackgroundWorker",
    "SectionUpdateWorkerConfig",
    "SectionUpdateWorkerStats",
]
