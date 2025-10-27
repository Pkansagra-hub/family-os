"""
K1 L4 Runtime — SessionState Memory Manager (3-Tier Eviction)

Implements the 3-tier memory eviction strategy defined in ADR-0018 and the
per-section budgets from ADR-0024c / sessionstate contracts.

Responsibilities:
    * Periodic memory audits (5s cadence) with pressure classification
      (GREEN/YELLOW/RED/CRITICAL) per ADR-0018 thresholds.
    * Tiered eviction pipeline:
        1. Beliefs (oldest user facts first) — Tier 1 soft eviction
        2. Multimodal buffers (audio → vision → text) — Tier 2 hard eviction
        3. Scoreboard history (oldest agent scores) — Tier 3 critical eviction
    * Integration with SessionStateControl so evictions participate in the
      delta batching pipeline and respect performance budgets defined in
      ADR-0024 and ADR-0038b.
    * Prometheus metrics (ADR-0029c): memory_pressure_level gauge,
      memory_evicted_bytes_total counter (per tier),
      memory_audit_latency_ms histogram, plus existing session-state metrics.

Zero-simulation policy: no mock delays, direct interaction with the live
SessionStateControl instance. All actions emit structured logs with
cognitive_trace_id alignment.
"""

from __future__ import annotations

import asyncio
import math
import os
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional, Tuple

import flatbuffers

try:  # ADR-0029 logging guidance
    import structlog  # type: ignore

    logger = structlog.get_logger(__name__)
except ImportError:  # pragma: no cover - fallback for minimal env
    import logging

    class _StdLoggerAdapter:
        def __init__(self, base_logger: logging.Logger) -> None:
            self._base = base_logger

        def info(self, event: str, **context) -> None:
            self._base.info("%s %s", event, context)

        def warning(self, event: str, **context) -> None:
            self._base.warning("%s %s", event, context)

        def debug(self, event: str, **context) -> None:
            self._base.debug("%s %s", event, context)

    logger = _StdLoggerAdapter(logging.getLogger(__name__))

try:  # Optional psutil for accurate RSS inspection per ADR-0018c
    import psutil  # type: ignore
except ImportError:  # pragma: no cover - psutil optional
    psutil = None

from k1.l4_runtime.session_state.control.control import (
    SessionStateControl,
    session_state_delta_merge_ms,
    session_state_lock_acquire_ms,
    session_state_lock_contention_total,
    session_state_write_queue_depth,
)
from k1.l4_runtime.session_state.model.BeliefsSection import BeliefsSectionT
from k1.l4_runtime.session_state.model.MultimodalSection import MultimodalSectionT
from k1.l4_runtime.session_state.model.ScoreboardSection import ScoreboardSectionT
from k1.l4_runtime.session_state.model.SessionState import SessionStateT
from k1.l4_runtime.session_state.model.UserFact import UserFactT
from k1.l4_runtime.session_state.model.wrapper import SectionMask, SessionStateWrapper
from k1.l5_infrastructure.observability.metrics import (
    K1MetricsCollector,
    get_k1_metrics,
)

# ---------------------------------------------------------------------------
# Constants (contracts + ADRs)
# ---------------------------------------------------------------------------

SOFT_LIMIT_BYTES = 64 * 1024  # 64KB — Tier 1 trigger (ADR-0024c)
HARD_LIMIT_BYTES = 128 * 1024  # 128KB — Tier 2 trigger
CRITICAL_LIMIT_BYTES = 256 * 1024  # 256KB — Tier 3 (session kill budget)

TIER1_TRIGGER = 0.70  # >70% of critical limit ⇒ Tier 1
TIER2_TRIGGER = 0.85  # >85% ⇒ Tier 2
TIER3_TRIGGER = 0.95  # >95% ⇒ Tier 3 (critical)

AUDIT_INTERVAL_SECONDS = 5.0  # Acceptance criteria
_MIN_EVICT_FRACTION = 0.25  # Remove at least 25% of candidates per tier

# ---------------------------------------------------------------------------
# Helper datatypes
# ---------------------------------------------------------------------------


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class MemoryAuditResult:
    """Result of an audit pass."""

    pressure: "MemoryPressure"
    usage_pct: float
    usage_bytes: int


class MemoryPressure(IntEnum):
    """Memory pressure levels (IntEnum for gauge compatibility)."""

    GREEN = 0
    YELLOW = 1
    RED = 2
    CRITICAL = 3


# ---------------------------------------------------------------------------
# Memory Manager Implementation
# ---------------------------------------------------------------------------


class MemoryManager:
    """Three-tier SessionState eviction orchestrator.

    Args:
        control: SessionStateControl managing the target session.
        audit_interval: Interval (seconds) between audit passes.
        metrics: Optional injected metrics collector (defaults to singleton).
        cognitive_trace_id: Trace identifier for structured logs.

    The monitor loop is started explicitly via :meth:`start` and can be
    stopped with :meth:`stop`. Eviction methods are public for explicit tests.
    """

    def __init__(
        self,
        control: SessionStateControl,
        *,
        audit_interval: float = AUDIT_INTERVAL_SECONDS,
        metrics: Optional[K1MetricsCollector] = None,
        cognitive_trace_id: Optional[str] = None,
    ) -> None:
        self._control = control
        self._audit_interval = audit_interval
        self._metrics = metrics or get_k1_metrics()
        self._trace_id = cognitive_trace_id or getattr(
            control, "cognitive_trace_id", control.session_id
        )

        self._pressure_level = MemoryPressure.GREEN
        self._monitor_task: Optional[asyncio.Task] = None
        self._stopped = asyncio.Event()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the background monitor loop."""

        if self._monitor_task and not self._monitor_task.done():
            return

        self._stopped.clear()
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info(
            "memory_manager_started",
            session_id=self._control.session_id,
            cognitive_trace_id=self._trace_id,
            audit_interval_s=self._audit_interval,
        )

    async def stop(self) -> None:
        """Stop the monitor loop."""

        self._stopped.set()
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:  # pragma: no cover - expected path
                pass
            self._monitor_task = None
        logger.info(
            "memory_manager_stopped",
            session_id=self._control.session_id,
            cognitive_trace_id=self._trace_id,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def audit_memory(self) -> MemoryAuditResult:
        """Audit SessionState size and classify pressure.

        Returns:
            MemoryAuditResult containing pressure level and raw usage stats.
        """

        start = time.perf_counter()
        state = await self._control.read_state()
        size_bytes = self._calculate_state_size(state)
        usage_pct = min(size_bytes / CRITICAL_LIMIT_BYTES, 1.0)

        if usage_pct >= TIER3_TRIGGER:
            pressure = MemoryPressure.CRITICAL
        elif usage_pct >= TIER2_TRIGGER:
            pressure = MemoryPressure.RED
        elif usage_pct >= TIER1_TRIGGER:
            pressure = MemoryPressure.YELLOW
        else:
            pressure = MemoryPressure.GREEN

        latency_ms = (time.perf_counter() - start) * 1000
        session_id = self._control.session_id

        self._metrics.session_state.memory_pressure_level.set(int(pressure))
        self._metrics.session_state.session_state_size_bytes.labels(
            section="total"
        ).observe(size_bytes)
        self._metrics.session_state.memory_audit_latency_ms.observe(latency_ms)

        logger.debug(
            "memory_audit_complete",
            session_id=session_id,
            cognitive_trace_id=self._trace_id,
            pressure=str(pressure.name),
            usage_pct=round(usage_pct * 100, 2),
            size_bytes=size_bytes,
            latency_ms=round(latency_ms, 3),
        )

        return MemoryAuditResult(
            pressure=pressure, usage_pct=usage_pct, usage_bytes=size_bytes
        )

    async def evict_tier1(self) -> int:
        """Tier 1 eviction — beliefs LRU pruning."""

        def mutate(state_t: SessionStateT) -> Tuple[bool, int]:
            beliefs = state_t.beliefs or BeliefsSectionT()
            facts = list(beliefs.userFacts or [])
            if len(facts) <= 1:
                return False, 0

            # Sort by last accessed (oldest first)
            sorted_facts = sorted(
                facts,
                key=lambda fact: (fact.lastAccessedMs or 0),
            )
            removal_count = max(1, math.floor(len(sorted_facts) * _MIN_EVICT_FRACTION))
            to_remove = {id(fact) for fact in sorted_facts[:removal_count]}
            remaining = [fact for fact in facts if id(fact) not in to_remove]

            if len(remaining) == len(facts):
                return False, 0

            freed_bytes = sum(
                _estimate_user_fact_bytes(fact) for fact in sorted_facts[:removal_count]
            )

            beliefs.userFacts = remaining
            beliefs.updatedAtMs = _now_ms()
            beliefs.sectionSizeBytes = max(0, beliefs.sectionSizeBytes - freed_bytes)
            state_t.beliefs = beliefs
            state_t.changeMask |= SectionMask.BELIEFS
            return True, freed_bytes

        return await self._apply_mutation("tier1", mutate)

    async def evict_tier2(self) -> int:
        """Tier 2 eviction — multimodal buffers (audio → vision → text)."""

        def mutate(state_t: SessionStateT) -> Tuple[bool, int]:
            multimodal = state_t.multimodal or MultimodalSectionT()
            freed_bytes = 0
            changed = False
            now = _now_ms()

            if multimodal.audio is not None:
                freed_bytes += multimodal.audio.sizeBytes or 0
                multimodal.audio = None
                changed = True

            elif multimodal.vision is not None:
                freed_bytes += multimodal.vision.sizeBytes or 0
                multimodal.vision = None
                changed = True

            elif multimodal.textHistory:
                removal_count = max(
                    1, math.floor(len(multimodal.textHistory) * _MIN_EVICT_FRACTION)
                )
                removed = multimodal.textHistory[:removal_count]
                freed_bytes += sum(len(item or "") for item in removed)
                multimodal.textHistory = multimodal.textHistory[removal_count:]
                changed = True

            if not changed:
                return False, 0

            multimodal.updatedAtMs = now
            multimodal.sectionSizeBytes = max(
                0, multimodal.sectionSizeBytes - freed_bytes
            )
            state_t.multimodal = multimodal
            state_t.changeMask |= SectionMask.MULTIMODAL
            return True, freed_bytes

        return await self._apply_mutation("tier2", mutate)

    async def evict_tier3(self) -> int:
        """Tier 3 eviction — scoreboard pruning (oldest agent scores)."""

        def mutate(state_t: SessionStateT) -> Tuple[bool, int]:
            scoreboard = state_t.scoreboard or ScoreboardSectionT()
            scores = list(scoreboard.agentScores or [])
            if len(scores) <= 1:
                return False, 0

            sorted_scores = sorted(scores, key=lambda score: score.lastUsedMs or 0)
            removal_count = max(1, math.floor(len(sorted_scores) * _MIN_EVICT_FRACTION))
            to_remove = {id(score) for score in sorted_scores[:removal_count]}
            remaining = [score for score in scores if id(score) not in to_remove]

            if len(remaining) == len(scores):
                return False, 0

            freed_bytes = removal_count * 32  # AgentScore struct size (32 bytes)

            scoreboard.agentScores = remaining
            scoreboard.updatedAtMs = _now_ms()
            scoreboard.sectionSizeBytes = max(
                0, scoreboard.sectionSizeBytes - freed_bytes
            )
            state_t.scoreboard = scoreboard
            state_t.changeMask |= SectionMask.SCOREBOARD
            return True, freed_bytes

        return await self._apply_mutation("tier3", mutate)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _monitor_loop(self) -> None:
        try:
            while not self._stopped.is_set():
                await asyncio.sleep(self._audit_interval)
                audit = await self.audit_memory()
                await self._handle_pressure(audit)
        except asyncio.CancelledError:  # pragma: no cover - expected path
            pass

    async def _handle_pressure(self, audit: MemoryAuditResult) -> None:
        if audit.pressure <= self._pressure_level:
            self._pressure_level = audit.pressure
            return

        logger.warning(
            "memory_pressure_escalated",
            session_id=self._control.session_id,
            cognitive_trace_id=self._trace_id,
            previous=str(self._pressure_level.name),
            current=str(audit.pressure.name),
            usage_pct=round(audit.usage_pct * 100, 2),
        )

        bytes_evicted = 0
        if audit.usage_pct >= TIER1_TRIGGER:
            bytes_evicted += await self.evict_tier1()
        if audit.usage_pct >= TIER2_TRIGGER:
            bytes_evicted += await self.evict_tier2()
        if audit.usage_pct >= TIER3_TRIGGER:
            bytes_evicted += await self.evict_tier3()

        self._pressure_level = audit.pressure

        logger.info(
            "memory_eviction_completed",
            session_id=self._control.session_id,
            cognitive_trace_id=self._trace_id,
            pressure=str(audit.pressure.name),
            bytes_evicted=bytes_evicted,
        )

    async def _apply_mutation(
        self,
        tier_label: str,
        mutator,
    ) -> int:
        """Apply a mutation function to the SessionState with delta handling."""

        lock_start = time.perf_counter()
        async with self._control._write_lock:  # pylint: disable=protected-access
            lock_latency_ms = (time.perf_counter() - lock_start) * 1000
            session_state_lock_acquire_ms.labels(lock_type="write").observe(
                lock_latency_ms
            )
            if lock_latency_ms > 1.0:
                session_state_lock_contention_total.labels(lock_type="write").inc()

            current_state = self._control._state  # pylint: disable=protected-access
            original_size = len(
                current_state._buffer
            )  # pylint: disable=protected-access

            state_t = SessionStateT.InitFromObj(
                current_state._state
            )  # pylint: disable=protected-access
            state_t.changeMask = 0

            changed, freed_bytes = mutator(state_t)
            if not changed or freed_bytes <= 0:
                return 0

            state_t.seqNo = (
                current_state._seq_no + 1
            )  # pylint: disable=protected-access

            new_wrapper = self._build_wrapper(state_t)

            delta_start = time.perf_counter()
            delta = new_wrapper.compute_delta(
                self._control._current_state_snapshot
            )  # pylint: disable=protected-access
            delta_latency_ms = (time.perf_counter() - delta_start) * 1000
            session_state_delta_merge_ms.labels(
                session_id=self._control.session_id
            ).observe(delta_latency_ms)

            self._control._state = new_wrapper  # pylint: disable=protected-access
            self._control._pending_deltas.append(
                delta
            )  # pylint: disable=protected-access
            session_state_write_queue_depth.labels(
                session_id=self._control.session_id
            ).set(
                len(self._control._pending_deltas)  # pylint: disable=protected-access
            )

            # Flush triggers (reuse control logic)
            if (
                len(self._control._pending_deltas) >= self._control.max_pending_deltas
            ):  # pylint: disable=protected-access
                await self._control.flush_to_k0()
            elif self._control.enable_auto_flush:  # pylint: disable=protected-access
                elapsed_ms = (
                    time.time() * 1000
                ) - self._control._last_flush_ms  # pylint: disable=protected-access
                if elapsed_ms >= self._control.flush_interval_ms:
                    await self._control.flush_to_k0()

        bytes_now = self._calculate_state_size(new_wrapper)
        actual_freed = max(0, original_size - bytes_now)
        self._record_eviction_metrics(tier_label, max(actual_freed, freed_bytes))
        return max(actual_freed, freed_bytes)

    def _build_wrapper(self, state_t: SessionStateT) -> SessionStateWrapper:
        builder = flatbuffers.Builder(max(1024, state_t.totalSizeBytes or 0))
        offset = state_t.Pack(builder)
        builder.Finish(offset)
        buffer = bytes(builder.Output())
        # Align stored size with actual bytes
        actual_size = len(buffer)
        if state_t.totalSizeBytes != actual_size:
            state_t.totalSizeBytes = actual_size
            builder = flatbuffers.Builder(actual_size + 128)
            offset = state_t.Pack(builder)
            builder.Finish(offset)
            buffer = bytes(builder.Output())
        wrapper = SessionStateWrapper.from_bytes(buffer)
        wrapper._seq_no = state_t.seqNo  # pylint: disable=protected-access
        wrapper._change_mask = state_t.changeMask  # pylint: disable=protected-access
        return wrapper

    def _calculate_state_size(self, state: SessionStateWrapper) -> int:
        total = state.get_total_size_bytes()
        if total:
            return total
        return len(state._buffer)  # pylint: disable=protected-access

    def _record_eviction_metrics(self, tier_label: str, bytes_evicted: int) -> None:
        session_id = self._control.session_id
        self._metrics.session_state.session_state_evictions_total.labels(
            tier=f"{tier_label}_pressure",
            reason="memory_pressure",
        ).inc()
        self._metrics.session_state.memory_evicted_bytes_total.labels(
            tier=tier_label,
        ).inc(bytes_evicted)
        logger.info(
            "memory_eviction_tier",
            session_id=session_id,
            cognitive_trace_id=self._trace_id,
            tier=tier_label,
            bytes_evicted=bytes_evicted,
        )


# ---------------------------------------------------------------------------
# Heuristics for size estimation (contracts reference approximate sizing)
# ---------------------------------------------------------------------------


def _estimate_user_fact_bytes(fact: UserFactT) -> int:
    key_len = len(fact.key or "")
    value_len = len(fact.value or "")
    source_len = len(fact.source or "")
    return key_len + value_len + source_len + 64  # overhead estimate


def _process_rss_bytes() -> int:
    if psutil is not None:  # pragma: no branch - runtime branch
        try:
            return psutil.Process(os.getpid()).memory_info().rss
        except Exception:  # pragma: no cover - defensive
            return 0
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        if hasattr(usage, "ru_maxrss"):
            return usage.ru_maxrss * 1024
    except Exception:  # pragma: no cover - defensive
        pass
    return 0


__all__ = [
    "MemoryManager",
    "MemoryPressure",
    "MemoryAuditResult",
    "_process_rss_bytes",
]
