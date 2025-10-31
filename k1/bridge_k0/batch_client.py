"""
Batch Client - Bounded Batching for SessionState Deltas

Layer: L5 Infrastructure
Component: K0 Bridge → Batching
Priority: P0 (Critical Path)
Status: 🚧 STUB - NEEDS_IMPLEMENTATION

Architecture Decision Records:
    - ADR-0022: Bounded Batching (250ms window, 64KB size, 100 message count)
    - ADR-0022b: HTTP/2 Multiplexing and Connection Management
    - ADR-0001a: K0 Bridge Dual Protocol (JSON PRIMARY + FlatBuffers SECONDARY)
    - ADR-0001f: K0-K1 Pipeline Boundary (K1 NEVER implements pipelines)

Dependencies:
    Internal:
        - k1.bridge_k0.command_client.CommandClient (send batched commands)
        - k1.bridge_k0.protocol.ProtocolNegotiator (format switching)
        - k1.l5_infrastructure.event_bus (EventBus for batch events)
    External:
        - asyncio (async runtime, batch timer)

Connects To:
    Upstream:
        - k1.l4_runtime.session_state (SessionState delta generator)
        - k1.l2_orchestration.orchestrator (agent coordination)
    Downstream:
        - k1.bridge_k0.command_client (send batched MemoryWrite commands)

Performance Budgets:
    - Delta accumulation: <1ms P95
    - Batch flush: <250ms P95 (within batching window)
    - Receipt latency: <100ms P95
    - Memory: <5MB per session (bounded buffer)
    - Throughput: 400 deltas/sec (100 deltas × 4 flushes/sec)

Observability:
    Metrics:
        - k1_k0_bridge_batch_accumulation_size{gauge} (current batch size)
        - k1_k0_bridge_batch_flush_latency_ms{trigger, p50, p95, p99} (histogram)
        - k1_k0_bridge_batch_flushes_total{trigger} (counter: timeout/size/count)
    Traces:
        - Span: k0_bridge.batch_client.flush
        - Attributes: batch_id, delta_count, size_bytes, trigger, cognitive_trace_id
    Logs:
        - INFO: batch flushed (batch_id, msg_count, size_bytes, trigger)
        - WARNING: buffer full (current_size, max_size, dropping_oldest)
        - ERROR: receipt timeout (batch_id, timeout_ms)

References:
    - Diagram: architecture_diagrams/k1/k1_complete_with_flows.mmd
    - Whiteboard: docs/whiteboard.md (Section: K0 Bridge Bounded Batching)
    - Test: tests/k1/bridge_k0/test_batch_client.py
"""

import asyncio
import json
import logging
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

# =============================================================================
# SECTION 1: IMPORTS
# =============================================================================
# Standard library imports

# Third-party imports
# None

# Internal imports
from k1.bridge_k0.command_client import (
    Command,
    CommandClient,
    CommandStatus,
    CommandType,
    Priority,
)
# from k1.bridge_k0.protocol import ProtocolNegotiator, SerializationFormat
# from k1.l5_infrastructure.event_bus import EventBus, Event, EventTopic

try:  # pragma: no cover - observability package may not yet exist
    from k1.l5_infrastructure.observability import (  # type: ignore
        create_span,
        emit_counter,
        emit_gauge,
        emit_histogram,
    )
except (ModuleNotFoundError, ImportError):  # pragma: no cover
    def create_span(name: str, **_attrs: Any):  # type: ignore
        class _NullSpan:
            def __enter__(self) -> "_NullSpan":
                return self

            def __exit__(self, *_exc: Any) -> None:
                return None

            def set_attribute(self, *_args: Any, **_kwargs: Any) -> None:
                return None

        return _NullSpan()

    def emit_counter(_name: str, _value: float = 1.0, _labels: Optional[Dict[str, Any]] = None) -> None:
        return None

    def emit_gauge(_name: str, _value: float, _labels: Optional[Dict[str, Any]] = None) -> None:
        return None

    def emit_histogram(_name: str, _value: float, _labels: Optional[Dict[str, Any]] = None) -> None:
        return None

# Configure module logger
logger = logging.getLogger(__name__)

# =============================================================================
# SECTION 2: CONSTANTS & CONFIGURATION
# =============================================================================

# TODO(@infrastructure-team): Load from k1/config/k0_bridge.yml (ADR-0022)
# Assigned to: Issue #L5-1.3.1
DEFAULT_CONFIG = {
    "batch_window_ms": 250,  # 250ms batching window (ADR-0022)
    "batch_size_bytes": 65536,  # 64KB batch size limit
    "batch_count_max": 100,  # 100 messages max per batch
    "pending_receipts_max": 1000,  # Max pending receipts (bounds memory)
    "max_buffer_bytes": 5242880,  # 5MB max buffer (1000 * 5KB avg)
    "enable_batching": True,  # Enable bounded batching
}

# =============================================================================
# SECTION 3: TYPE DEFINITIONS & ENUMS
# =============================================================================


class FlushTrigger(Enum):
    """Batch flush trigger reasons"""

    TIME = "TIME"  # 250ms window elapsed
    SIZE = "SIZE"  # 64KB size reached
    COUNT = "COUNT"  # 100 messages reached
    MANUAL = "MANUAL"  # Explicit flush() call


@dataclass
class SessionStateDelta:
    """
    SessionState delta for batching.

    Fields:
        session_id: Session ID (e.g., "sess_abc123")
        field_path: JSON path to field (e.g., "turn[0].assistant_response.text")
        value: New value (Any type, JSON-serializable)
        timestamp: Unix timestamp (milliseconds)
        privacy_band: Privacy classification (GREEN | AMBER | RED | BLACK)
        size_bytes: Estimated size in bytes (for batch size calculation)
        priority: Command priority (maps to CommandClient priorities)
    """

    session_id: str
    field_path: str
    value: Any
    timestamp: float
    privacy_band: str = "GREEN"
    size_bytes: int = 0
    priority: int = Priority.REALTIME.value

    def __post_init__(self) -> None:
        if self.size_bytes <= 0:
            self.size_bytes = len(self.field_path) + len(json.dumps(self.value))
        if self.priority not in {p.value for p in Priority}:
            raise ValueError(f"Invalid priority value: {self.priority}")


@dataclass
class Batch:
    """
    Batch of SessionState deltas.

    Fields:
        batch_id: Unique batch ID (e.g., "batch_123")
        deltas: List of SessionState deltas
        created_at: Batch creation timestamp
        size_bytes: Total batch size in bytes
        cognitive_trace_id: Trace ID for observability
    """

    batch_id: str
    deltas: List[SessionStateDelta]
    created_at: float
    size_bytes: int
    cognitive_trace_id: Optional[str] = None


@dataclass
class BatchReceipt:
    """
    Receipt for batched command.

    Fields:
        batch_id: Batch ID
        receipt_id: K0 receipt ID (e.g., "rcpt_456")
        status: Receipt status (PENDING | COMMITTED | FAILED)
        timestamp: Receipt timestamp
    """

    batch_id: str
    receipt_id: str
    status: str
    timestamp: float


# =============================================================================
# SECTION 4: CORE CLASSES
# =============================================================================


class BatchClient:
    """
    Batch client for bounded batching of SessionState deltas.

    Purpose:
        Accumulates SessionState deltas from K1 components, flushes batches
        when triggers met (250ms/64KB/100 messages), sends to K0 Command Port,
        tracks receipts, handles bounded buffer (5MB max, 1000 pending receipts).

    Responsibilities:
        1. Accumulate SessionState deltas in batch buffer
        2. Monitor flush triggers (250ms window OR 64KB size OR 100 count)
        3. Flush batch to K0 Command Port (via CommandClient)
        4. Track receipts (receipt_id → PENDING → COMMITTED)
        5. Handle bounded buffer (drop oldest if >5MB or >1000 receipts)

    Batching Strategy (ADR-0022):
        - Time trigger: 250ms since last flush (P1 latency SLA)
        - Size trigger: Batch reaches 64KB (P2 memory bound)
        - Count trigger: 100 deltas accumulated (P2 throughput)
        - Manual trigger: Explicit flush() call (testing, shutdown)

    Lifecycle:
        INIT → READY → [DRAINING] → TERMINATED

    Thread Safety: Yes (async-safe with lock)
    Async Safe: Yes (fully async/await compatible)

    Cognitive Trace:
        - Propagates cognitive_trace_id to batched commands
        - Required for: add_delta, flush

    Performance Budget (P95):
        - Delta accumulation: <1ms
        - Batch flush: <250ms (within window)
        - Receipt confirmation: <100ms

    Examples:
        >>> config = {'batch_window_ms': 250, 'batch_size_bytes': 65536}
        >>> batch_client = BatchClient(config)
        >>> await batch_client.initialize()
        >>>
        >>> # Add SessionState delta
        >>> delta = SessionStateDelta(
        ...     session_id='sess_123',
        ...     field_path='turn[0].assistant_response.text',
        ...     value='Hello, user!',
        ...     timestamp=time.time() * 1000
        ... )
        >>> await batch_client.add_delta(delta, cognitive_trace_id='trace_456')
        >>>
        >>> # Batch auto-flushes when trigger met (250ms/64KB/100 messages)
        >>> await batch_client.shutdown()  # Flush remaining deltas

    References:
        - ADR-0022: Bounded Batching (250ms window, 64KB, 100 messages)
        - Diagram: architecture_diagrams/k1/k1_complete_with_flows.mmd
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        command_client: Optional[CommandClient] = None,
    ) -> None:
        """
        Initialize BatchClient.

        Args:
            config: Configuration dict with batching parameters

        Raises:
            ValueError: If configuration is invalid
            TypeError: If config type is incorrect

        Side Effects:
            - Initializes internal state (batch buffer, receipt tracker)
            - Does NOT start batch timer (call initialize() to start)

        ADR: ADR-0022 (Bounded Batching)
        Assigned to: Issue #L5-1.3.1
        """
        merged_config = {**DEFAULT_CONFIG, **(config or {})}
        self._validate_config(merged_config)

        if command_client is None:
            raise ValueError("command_client is required for BatchClient")

        self.config = merged_config
        self._command_client = command_client
        self.state = "INIT"  # INIT | READY | DRAINING | TERMINATED
        self._logger = logger
        self._batch_buffer: List[Tuple[SessionStateDelta, Optional[str]]] = []
        self._buffer_size_bytes: int = 0
        self._receipt_tracker: Dict[str, BatchReceipt] = {}
        self._pending_receipts: Dict[str, BatchReceipt] = {}
        self._batch_timer_task: Optional[asyncio.Task] = None
        self._flush_lock = asyncio.Lock()
        self._shutdown_event = asyncio.Event()
        self._last_flush_monotonic = time.monotonic()
        self._dlq: List[Dict[str, Any]] = []

    async def initialize(self) -> None:
        """
        Async initialization phase - start batch timer.

        This method performs async setup (start 250ms batch timer).

        Raises:
            RuntimeError: If initialization fails

        Lifecycle:
            Transitions: INIT → READY

        ADR: ADR-0022 (Bounded Batching)
        Assigned to: Issue #L5-1.3.1
        """
        # TODO(@infrastructure-team): Implement async initialization (ADR-0022)
        # 1. Start batch timer task (250ms interval)
        # 2. Initialize current batch (empty)
        # 3. Transition state: INIT → READY
        if self.state != "INIT":
            raise RuntimeError("BatchClient already initialized")

        self._shutdown_event.clear()
        self._last_flush_monotonic = time.monotonic()
        if self.config.get("enable_batching", True):
            self._batch_timer_task = asyncio.create_task(self._batch_timer_loop())

        self.state = "READY"
        self._logger.info(
            "batch_client_initialized batch_window_ms=%d batch_size_bytes=%d batch_count_max=%d",
            self.config["batch_window_ms"],
            self.config["batch_size_bytes"],
            self.config["batch_count_max"],
        )

    async def add_delta(
        self,
        delta: SessionStateDelta,
        cognitive_trace_id: Optional[str] = None,
    ) -> Optional[BatchReceipt]:
        """
        Add SessionState delta to batch buffer.

        This method accumulates deltas and checks flush triggers.

        Args:
            delta: SessionState delta to add
            cognitive_trace_id: Trace ID for observability

        Raises:
            ValueError: If delta is invalid
            RuntimeError: If buffer full (>5MB or >1000 receipts)

        Performance:
            - Target: <1ms P95 (delta accumulation)

        Flush Triggers (checked after add):
            - Time: 250ms since last flush → flush
            - Size: Batch size ≥64KB → flush
            - Count: Batch count ≥100 → flush

        ADR: ADR-0022 (Bounded Batching)
        Assigned to: Issue #L5-1.3.1
        """
        if self.state not in {"READY", "DRAINING"}:
            raise RuntimeError("BatchClient is not ready")

        if delta.privacy_band == "BLACK":
            self._logger.warning(
                "delta_rejected_privacy session_id=%s field_path=%s trace_id=%s",
                delta.session_id,
                delta.field_path,
                cognitive_trace_id,
            )
            emit_counter(
                "k1_k0_bridge_batch_deltas_rejected_total",
                1,
                {"reason": "privacy_band_black"},
            )
            return None

        async with self._flush_lock:
            self._enforce_bounds(delta)

            self._batch_buffer.append((delta, cognitive_trace_id))
            self._buffer_size_bytes += delta.size_bytes

            emit_gauge(
                "k1_k0_bridge_batch_accumulation_size",
                self._buffer_size_bytes,
                None,
            )

            trigger: Optional[FlushTrigger] = None
            if self._buffer_size_bytes >= self.config["batch_size_bytes"]:
                trigger = FlushTrigger.SIZE
            elif len(self._batch_buffer) >= self.config["batch_count_max"]:
                trigger = FlushTrigger.COUNT

            if trigger is not None or not self.config.get("enable_batching", True):
                return await self._flush_locked(
                    trigger or FlushTrigger.MANUAL,
                    cognitive_trace_id=cognitive_trace_id,
                )

        return None

    async def flush(
        self,
        trigger: FlushTrigger = FlushTrigger.MANUAL,
        cognitive_trace_id: Optional[str] = None,
    ) -> Optional[BatchReceipt]:
        """
        Flush pending batch to K0 Command Port.

        This method sends accumulated deltas as batched MemoryWrite command.

        Args:
            trigger: Flush trigger reason (TIME | SIZE | COUNT | MANUAL)
            cognitive_trace_id: Trace ID for observability

        Returns:
            BatchReceipt if batch sent, None if buffer empty

        Raises:
            RuntimeError: If K0 Command Port unavailable

        Performance:
            - Target: <250ms P95 (batch flush + receipt)

        Observability:
            - Metrics: k1_k0_bridge_batch_flushes_total{trigger}
            - Traces: Span name: k0_bridge.batch_client.flush
            - Logs: INFO: batch flushed (batch_id, msg_count, size_bytes, trigger)

        ADR: ADR-0022 (Bounded Batching)
        Assigned to: Issue #L5-1.3.1
        """
        # TODO(@infrastructure-team): Implement flush (ADR-0022)
        # 1. Acquire flush lock (prevent concurrent flushes)
        # 2. Check if buffer empty (if empty, return None)
        # 3. Create Batch object (batch_id, deltas, created_at, size_bytes)
        # 4. Send batch to K0 Command Port (via CommandClient)
        # 5. Parse receipt (receipt_id, status, timestamp)
        # 6. Track receipt (batch_id → BatchReceipt)
        # 7. Clear batch buffer
        # 8. Record metrics (flush latency, batch size, trigger)
        # 9. Return BatchReceipt
        async with self._flush_lock:
            return await self._flush_locked(trigger, cognitive_trace_id)

    async def get_receipt(self, batch_id: str) -> Optional[BatchReceipt]:
        """
        Get receipt status for batch.

        Args:
            batch_id: Batch ID (e.g., "batch_123")

        Returns:
            BatchReceipt if found, None otherwise

        ADR: ADR-0022b (Receipt Tracking)
        Assigned to: Issue #L5-1.3.1
        """
        # TODO(@infrastructure-team): Implement get_receipt (ADR-0022b)
        # 1. Query receipt tracker (batch_id → BatchReceipt)
        # 2. If not found, query K0 (GET /k0/receipts/{batch_id})
        # 3. Update receipt tracker cache
        # 4. Return BatchReceipt
        return self._receipt_tracker.get(batch_id)

    async def shutdown(self) -> None:
        """
        Graceful shutdown sequence.

        This method performs cleanup and state transitions.

        Lifecycle:
            - Flush remaining deltas (ensure no data loss)
            - Stop batch timer
            - Finalize metrics

        ADR: ADR-0022 (Bounded Batching)
        Assigned to: Issue #L5-1.3.1
        """
        # TODO(@infrastructure-team): Implement shutdown (ADR-0022)
        # 1. Set state to DRAINING
        # 2. Flush remaining batch (flush(FlushTrigger.MANUAL))
        # 3. Cancel batch timer task
        # 4. Set state to TERMINATED
        # 5. Clear batch buffer and receipt tracker
        # 6. Flush metrics (Prometheus)
        if self.state == "TERMINATED":
            return

        self.state = "DRAINING"
        async with self._flush_lock:
            await self._flush_locked(FlushTrigger.MANUAL, cognitive_trace_id=None)

        self._shutdown_event.set()

        if self._batch_timer_task:
            self._batch_timer_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._batch_timer_task

        self.state = "TERMINATED"
        self._logger.info("batch_client_shutdown_complete")

    # =========================================================================
    # PRIVATE METHODS (Implementation Details)
    # =========================================================================

    async def _batch_timer_loop(self) -> None:
        interval = self.config["batch_window_ms"] / 1000.0
        try:
            while not self._shutdown_event.is_set():
                await asyncio.sleep(interval)
                if self.state not in {"READY", "DRAINING"}:
                    continue

                time_since_flush = time.monotonic() - self._last_flush_monotonic
                if time_since_flush * 1000 < self.config["batch_window_ms"]:
                    continue

                if not self._batch_buffer:
                    continue

                await self.flush(FlushTrigger.TIME)
        except asyncio.CancelledError:  # pragma: no cover - expected on shutdown
            raise

    async def _flush_locked(
        self,
        trigger: FlushTrigger,
        cognitive_trace_id: Optional[str],
    ) -> Optional[BatchReceipt]:
        if not self._batch_buffer:
            return None

        deltas_snapshot = list(self._batch_buffer)
        buffer_size_snapshot = self._buffer_size_bytes
        self._batch_buffer.clear()
        self._buffer_size_bytes = 0

        batch_id = self._generate_batch_id()
        trace_id = cognitive_trace_id or deltas_snapshot[0][1] or deltas_snapshot[0][0].session_id
        priority = min(delta.priority for delta, _ in deltas_snapshot)
        session_ids = {delta.session_id for delta, _ in deltas_snapshot}
        session_id = session_ids.pop() if len(session_ids) == 1 else "batch"

        payload = self._serialize_batch(batch_id, deltas_snapshot, trigger, buffer_size_snapshot, trace_id)
        command = Command(
            command_id=str(uuid.uuid4()),
            command_type=CommandType.MEMORY_WRITE,
            session_id=session_id,
            cognitive_trace_id=trace_id or batch_id,
            payload=payload,
            priority=priority,
        )

        start_time = time.perf_counter()
        try:
            with create_span(
                "k0_bridge.batch_client.flush",
                batch_id=batch_id,
                trigger=trigger.value,
                delta_count=len(deltas_snapshot),
            ) as span:
                span.set_attribute("size_bytes", buffer_size_snapshot)
                receipt = await self._command_client.send_command(
                    command,
                    cognitive_trace_id=command.cognitive_trace_id,
                )

            latency_ms = (time.perf_counter() - start_time) * 1000
            emit_histogram(
                "k1_k0_bridge_batch_flush_latency_ms",
                latency_ms,
                {"trigger": trigger.value},
            )
            emit_counter(
                "k1_k0_bridge_batch_flushes_total",
                1,
                {"trigger": trigger.value},
            )

            status = receipt.status.value if isinstance(receipt.status, CommandStatus) else str(receipt.status)
            batch_receipt = BatchReceipt(
                batch_id=batch_id,
                receipt_id=receipt.receipt_id,
                status=status,
                timestamp=receipt.timestamp_ms,
            )
            self._receipt_tracker[batch_id] = batch_receipt
            if receipt.status == CommandStatus.PENDING:
                self._pending_receipts[batch_id] = batch_receipt
            else:
                self._pending_receipts.pop(batch_id, None)

            self._logger.info(
                "batch_flushed batch_id=%s trigger=%s delta_count=%d size_bytes=%d latency_ms=%.2f status=%s trace_id=%s",
                batch_id,
                trigger.value,
                len(deltas_snapshot),
                buffer_size_snapshot,
                latency_ms,
                status,
                trace_id,
            )

            self._last_flush_monotonic = time.monotonic()
            return batch_receipt
        except Exception as exc:
            # Restore buffer on failure
            self._batch_buffer[:0] = deltas_snapshot
            self._buffer_size_bytes += buffer_size_snapshot
            emit_counter(
                "k1_k0_bridge_batch_flush_failures_total",
                1,
                {"trigger": trigger.value, "error": exc.__class__.__name__},
            )
            await self._send_to_dlq(batch_id, deltas_snapshot, str(exc), trace_id)
            self._logger.error(
                "batch_flush_failed batch_id=%s error=%s trace_id=%s",
                batch_id,
                str(exc),
                trace_id,
            )
            raise

    def _serialize_batch(
        self,
        batch_id: str,
        deltas_snapshot: List[Tuple[SessionStateDelta, Optional[str]]],
        trigger: FlushTrigger,
        size_bytes: int,
        trace_id: Optional[str],
    ) -> bytes:
        payload = {
            "batch_id": batch_id,
            "trigger": trigger.value,
            "size_bytes": size_bytes,
            "deltas": [
                {
                    "session_id": delta.session_id,
                    "field_path": delta.field_path,
                    "value": delta.value,
                    "timestamp": delta.timestamp,
                    "privacy_band": delta.privacy_band,
                    "priority": delta.priority,
                    "trace_id": trace,
                }
                for delta, trace in deltas_snapshot
            ],
            "trace_id": trace_id,
        }
        return json.dumps(payload, separators=(",", ":")).encode("utf-8")

    def _enforce_bounds(self, delta: SessionStateDelta) -> None:
        pending_limit = self.config["pending_receipts_max"]
        if len(self._pending_receipts) >= pending_limit:
            raise RuntimeError("Pending receipt limit exceeded; apply backpressure upstream")

        max_buffer_bytes = self.config["max_buffer_bytes"]
        while self._buffer_size_bytes + delta.size_bytes > max_buffer_bytes:
            dropped = self._drop_oldest_with_priority(Priority.BACKGROUND.value)
            if not dropped:
                raise RuntimeError("Batch buffer exceeded max capacity and no background items to drop")

    def _drop_oldest_with_priority(self, priority: int) -> bool:
        for idx, (existing_delta, _) in enumerate(self._batch_buffer):
            if existing_delta.priority == priority:
                self._buffer_size_bytes -= existing_delta.size_bytes
                dropped = self._batch_buffer.pop(idx)
                self._logger.warning(
                    "batch_delta_dropped priority=%d session_id=%s field_path=%s",
                    priority,
                    dropped[0].session_id,
                    dropped[0].field_path,
                )
                emit_counter(
                    "k1_k0_bridge_batch_deltas_dropped_total",
                    1,
                    {"priority": priority},
                )
                return True

        return False

    def _validate_config(self, config: Dict[str, Any]) -> None:
        required_positive = [
            "batch_window_ms",
            "batch_size_bytes",
            "batch_count_max",
            "pending_receipts_max",
            "max_buffer_bytes",
        ]
        for key in required_positive:
            if config[key] <= 0:
                raise ValueError(f"BatchClient config value for {key} must be positive")

    def _generate_batch_id(self) -> str:
        return f"batch_{uuid.uuid4()}"

    async def _send_to_dlq(
        self,
        batch_id: str,
        deltas_snapshot: List[Tuple[SessionStateDelta, Optional[str]]],
        error: str,
        trace_id: Optional[str],
    ) -> None:
        dlq_entry = {
            "batch_id": batch_id,
            "error": error,
            "trace_id": trace_id,
            "deltas": [delta.field_path for delta, _ in deltas_snapshot],
            "timestamp": int(time.time() * 1000),
        }
        self._dlq.append(dlq_entry)
        emit_counter(
            "k1_k0_bridge_batch_dlq_total",
            1,
            None,
        )
        if len(self._dlq) > 10000:
            self._dlq.pop(0)

    @property
    def dlq(self) -> List[Dict[str, Any]]:
        return list(self._dlq)


# =============================================================================
# SECTION 5: HELPER FUNCTIONS
# =============================================================================


def create_batch_client(config: Optional[Dict[str, Any]] = None) -> BatchClient:
    """
    Create BatchClient with default or provided configuration.

    Args:
        config: Configuration dict (default: 250ms/64KB/100 messages)

    Returns:
        BatchClient instance

    ADR: ADR-0022 (Bounded Batching)
    Assigned to: Issue #L5-1.3.1
    """
    if config is None:
        config = DEFAULT_CONFIG

    return BatchClient(config)


# =============================================================================
# SECTION 6: MODULE EXPORTS & INITIALIZATION
# =============================================================================

__all__ = [
    "BatchClient",
    "SessionStateDelta",
    "Batch",
    "BatchReceipt",
    "FlushTrigger",
    "create_batch_client",
]


# =============================================================================
# OBSERVABILITY INTEGRATION
# =============================================================================
# Metrics to export (Prometheus):
#   - k1_k0_bridge_batch_accumulation_size{gauge} (current batch size)
#   - k1_k0_bridge_batch_flush_latency_ms{trigger, p50, p95, p99} (histogram)
#   - k1_k0_bridge_batch_flushes_total{trigger} (counter: timeout/size/count)
#
# Traces to generate (OpenTelemetry):
#   - Span name: k0_bridge.batch_client.flush
#   - Attributes: batch_id, delta_count, size_bytes, trigger, cognitive_trace_id
#   - Links to: upstream session_state spans, downstream command_client spans
#
# Logs to emit (structured logging):
#   - Level: INFO (batch flushed), WARNING (buffer full), ERROR (receipt timeout)
#   - Fields: component='batch_client', batch_id, msg_count, size_bytes, trigger
#
# =============================================================================

# =============================================================================
# COGNITIVE TRACE PROPAGATION
# =============================================================================
# All async methods must:
#   1. Accept cognitive_trace_id parameter
#   2. Propagate trace_id to CommandClient (in batch command)
#   3. Include trace_id in all log statements
#
# Example:
#   await batch_client.add_delta(delta, cognitive_trace_id='trace_abc123')
#   # Batch command includes: X-Cognitive-Trace-Id: trace_abc123
#
# =============================================================================

# =============================================================================
# TESTING REQUIREMENTS (WARD Framework)
# =============================================================================
# Integration tests required:
#   - tests/k1/bridge_k0/test_batch_client.py
#   - Test delta accumulation (add_delta)
#   - Test flush triggers (250ms/64KB/100 messages)
#   - Test bounded buffer (5MB max, 1000 receipts)
#   - Test receipt tracking (batch_id → status)
#   - Test graceful shutdown (flush remaining deltas)
#
# No simulation code allowed:
#   - Use real CommandClient with K0 mock server
#   - Test all 3 flush triggers independently
#   - Integration tests > unit tests
#
# Performance budget tests:
#   - Assert delta accumulation <1ms P95
#   - Assert batch flush <250ms P95
#   - Assert receipt confirmation <100ms P95
#
# =============================================================================
