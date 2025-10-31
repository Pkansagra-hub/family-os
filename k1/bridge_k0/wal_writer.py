"""
WAL Writer - Write-Ahead Logger for Orchestration Decisions

Layer: L5 Infrastructure
Component: K0 Bridge → WAL Writer
Priority: P0 (Critical Path - Reliability)
Status: 🚧 STUB - NEEDS_IMPLEMENTATION

Architecture Decision Records:
    - ADR-0008: Saga Pattern for Error Recovery (WAL for compensation logs)
    - ADR-0008c: Distributed State Management (SAGA_LOG topic, 7-day retention)
    - ADR-0022: K0 Bridge Bounded Batching (receipt persistence)
    - ADR-0001a: K0 Bridge Communication Protocol (Command Port P02)

Dependencies:
    Internal:
        - k1.bridge_k0.command_client (CommandClient for K0 writes)
        - k1.bridge_k0.batch_client (BatchClient for batching)
    External:
        - asyncio (async runtime)
        - time (timestamps)
        - json (log serialization)

Connects To:
    Upstream:
        - k1.l2_orchestration.saga_coordinator (logs saga decisions)
        - k1.l2_orchestration.orchestrator (logs orchestration plans)
    Downstream:
        - K0 Command Port (P02 MemoryWrite → SAGA_LOG topic)

Performance Budgets:
    - Log write: <5ms P95 (local buffer, async flush)
    - Batch flush: <100ms P95 (K0 Command Port latency)
    - Replay latency: <50ms P95 (read from K0 WAL)

Observability:
    Metrics:
        - k1_wal_writer_logs_total{counter, labels: topic}
        - k1_wal_writer_batch_flush_duration_seconds{histogram}
        - k1_wal_writer_replay_duration_seconds{histogram}
    Traces:
        - Span: k0_bridge.wal_writer.log
        - Span: k0_bridge.wal_writer.replay
    Logs:
        - INFO: wal_log_written (topic, log_id, size_bytes)
        - INFO: wal_batch_flushed (topic, batch_count, flush_latency_ms)

References:
    - ADR-0008: Saga Pattern (WAL for crash recovery)
    - ADR-0008c: Distributed State Management (SAGA_LOG topic)
    - Research: Write-Ahead Logging (Gray & Reuter 1993) - Transaction Processing
    - Diagram: architecture_diagrams/k1/k1_complete_with_flows.mmd
    - Test: tests/k1/bridge_k0/test_wal_writer.py
"""

import asyncio
import json
import logging
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from k1.bridge_k0.command_client import Command, CommandClient, CommandReceipt, CommandType

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

    def emit_histogram(_name: str, _value: float, _labels: Optional[Dict[str, Any]] = None) -> None:
        return None

    def emit_gauge(_name: str, _value: float, _labels: Optional[Dict[str, Any]] = None) -> None:
        return None

# Configure module logger
logger = logging.getLogger(__name__)

# =============================================================================
# SECTION 2: CONSTANTS & CONFIGURATION
# =============================================================================

# TODO(@infrastructure-team): Load from k1/config/saga.yml (ADR-0008c)
# Assigned to: Issue #L5-1.4.1
DEFAULT_CONFIG = {
    "wal_topic": "SAGA_LOG",  # K0 topic for saga logs
    "retention_days": 7,  # 7-day retention in K0
    "write_timeout_ms": 5000,  # 5s write timeout
    "batch_flush_interval_ms": 250,  # 250ms batch flush (aligned with ADR-0022)
    "batch_size_max": 100,  # 100 logs per batch (count trigger)
    "batch_size_bytes": 64 * 1024,  # 64KB payload trigger
    "replay_cache_size": 1000,  # 1000 logs in replay cache
    "queue_capacity": 10_000,  # Max buffered WAL entries (ADR-0038b)
    "max_buffer_bytes": 5 * 1024 * 1024,  # 5MB bounded buffer (guidance)
    "pending_receipts_max": 1000,  # Guard pending receipts (ADR-0038b)
}

# =============================================================================
# SECTION 3: TYPE DEFINITIONS & ENUMS
# =============================================================================


class WALTopic(Enum):
    """WAL topic classifications"""

    SAGA_LOG = "SAGA_LOG"  # Saga execution logs (ADR-0008c)
    COMPENSATION_LOG = "COMPENSATION_LOG"  # Compensation action logs (ADR-0008a)
    ORCHESTRATION_LOG = "ORCHESTRATION_LOG"  # Orchestration decisions
    PLAN_COMMITTED = "PLAN_COMMITTED"  # Committed plans


class WALLogType(Enum):
    """WAL log entry types"""

    SAGA_START = "SAGA_START"  # Saga initiated
    STEP_COMPLETE = "STEP_COMPLETE"  # Step completed successfully
    STEP_FAILED = "STEP_FAILED"  # Step failed
    COMPENSATION_START = "COMPENSATION_START"  # Compensation initiated
    COMPENSATION_COMPLETE = "COMPENSATION_COMPLETE"  # Compensation completed
    SAGA_COMPLETE = "SAGA_COMPLETE"  # Saga completed (all steps)
    SAGA_ABORTED = "SAGA_ABORTED"  # Saga aborted (after compensation)


@dataclass
class WALLogEntry:
    """
    Write-Ahead Log entry for orchestration decisions.

    Fields:
        log_id: Unique log identifier (UUID)
        topic: WAL topic (SAGA_LOG, COMPENSATION_LOG, etc.)
        log_type: Log entry type (SAGA_START, STEP_COMPLETE, etc.)
        saga_id: Saga identifier (groups related logs)
        timestamp: Unix timestamp (milliseconds)
        payload: Log-specific payload (serialized to JSON)
        cognitive_trace_id: Trace ID for observability
    """

    log_id: str
    topic: WALTopic
    log_type: WALLogType
    saga_id: str
    timestamp: int
    payload: Dict[str, Any]
    cognitive_trace_id: Optional[str] = None


@dataclass
class WALWriteResult:
    """
    WAL write operation result.

    Fields:
        log_id: Log identifier
        receipt_id: K0 receipt identifier (persistence proof)
        write_latency_ms: Write operation latency (ms)
        batched: Whether log was batched (True) or flushed immediately (False)
    """

    log_id: str
    receipt_id: str
    write_latency_ms: float
    batched: bool


@dataclass
class WALReplayResult:
    """
    WAL replay operation result.

    Fields:
        logs_replayed: Number of logs replayed
        replay_latency_ms: Replay operation latency (ms)
        oldest_log_timestamp: Oldest log timestamp in replay
        newest_log_timestamp: Newest log timestamp in replay
    """

    logs_replayed: int
    replay_latency_ms: float
    oldest_log_timestamp: Optional[int] = None
    newest_log_timestamp: Optional[int] = None


# =============================================================================
# SECTION 4: CORE CLASSES
# =============================================================================


class WALWriter:
    """
    Write-Ahead Logger for K1 orchestration decisions.

    Purpose:
        Logs orchestration decisions (saga steps, compensations, plans) to K0
        before execution for crash recovery via replay. Uses K0 Command Port (P02)
        with SAGA_LOG topic, batches logs every 250ms or 100 logs (aligned with
        ADR-0022 bounded batching), supports replay from K0 WAL for state restoration.

    Orchestration Decision Logging (ADR-0008):
        - SAGA_START: Log saga initiation before first step
        - STEP_COMPLETE: Log step completion with result
        - STEP_FAILED: Log step failure with error
        - COMPENSATION_START: Log compensation initiation
        - COMPENSATION_COMPLETE: Log compensation result
        - SAGA_COMPLETE: Log saga completion (all steps)
        - SAGA_ABORTED: Log saga abort (after compensation)

    Crash Recovery Flow:
        1. K1 crashes during saga execution
        2. K1 restarts → reads SAGA_LOG from K0
        3. Identifies incomplete sagas (SAGA_START but no SAGA_COMPLETE/SAGA_ABORTED)
        4. Resumes compensation from last completed step
        5. Logs recovery actions to SAGA_LOG

    Responsibilities:
        1. Log orchestration decisions to K0 before execution
        2. Batch logs for efficiency (250ms or 100 logs)
        3. Support replay from K0 WAL for crash recovery
        4. Maintain cognitive_trace_id for observability
        5. Integrate with K0 Command Port (P02)

    Lifecycle:
        INIT → READY → [log/replay] → SHUTDOWN

    Thread Safety: Yes (async-safe with lock)
    Async Safe: Yes (fully async/await compatible)

    Performance Budget (P95):
        - Log write: <5ms (local buffer, async flush)
        - Batch flush: <100ms (K0 Command Port latency)
        - Replay: <50ms (read from K0 WAL)

    Examples:
        >>> config = WALWriterConfig(wal_topic='SAGA_LOG', batch_flush_interval_ms=250)
        >>> wal = WALWriter(config, command_client=k0_command_client)
        >>>
        >>> # Log saga start
        >>> log_entry = WALLogEntry(
        ...     log_id='log_123',
        ...     topic=WALTopic.SAGA_LOG,
        ...     log_type=WALLogType.SAGA_START,
        ...     saga_id='saga_456',
        ...     timestamp=int(time.time() * 1000),
        ...     payload={'workflow_id': 'wf_789', 'steps': 5},
        ...     cognitive_trace_id='trace_abc'
        ... )
        >>> result = await wal.log(log_entry)
        >>> print(result.receipt_id)  # K0 receipt for persistence proof
        >>>
        >>> # Replay logs for crash recovery
        >>> replay_result = await wal.replay(saga_id='saga_456')
        >>> print(replay_result.logs_replayed)  # Number of logs replayed

    References:
        - ADR-0008: Saga Pattern (WAL for crash recovery)
        - ADR-0008c: Distributed State Management (SAGA_LOG topic, 7-day retention)
        - Research: Write-Ahead Logging (Gray & Reuter 1993) - Transaction Processing
    """

    def __init__(
        self,
        config: "WALWriterConfig",
        command_client: Optional[CommandClient] = None,
    ) -> None:
        """
        Initialize WALWriter.

        Args:
            config: WALWriterConfig with topic, batching, retention settings
            command_client: CommandClient for K0 writes (None = create default)

        Raises:
            ValueError: If configuration is invalid

        Side Effects:
            - Initializes batch buffer (empty)
            - Starts batch flush timer (250ms interval)
            - Does NOT connect to K0 (call initialize())

        ADR: ADR-0008c (WAL Writer with SAGA_LOG topic)
        Assigned to: Issue #L5-1.4.1
        """
        self._validate_config(config)

        if command_client is None:
            raise ValueError("command_client is required for WALWriter")

        self.config = config
        self.command_client = command_client
        self._logger = logger
        self._batch_buffer: List[WALLogEntry] = []
        self._batch_buffer_bytes: int = 0
        self._batch_lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        self._pending_receipts: Dict[str, CommandReceipt] = {}
        self._last_flush_monotonic = time.monotonic()

        emit_gauge("k1_wal_writer_queue_depth", 0, {"topic": self.config.wal_topic})

    async def initialize(self) -> None:
        """
        Initialize WAL writer (start batch flush timer).

        This method starts the background batch flush timer (250ms interval).

        Side Effects:
            - Starts batch flush timer task
            - Logs initialization

        ADR: ADR-0008c (WAL Writer initialization)
        Assigned to: Issue #L5-1.4.1
        """
        if self._flush_task is not None:
            raise RuntimeError("WALWriter already initialized")

        self._shutdown_event.clear()
        self._flush_task = asyncio.create_task(self._batch_flush_loop())
        self._last_flush_monotonic = time.monotonic()
        self._logger.info(
            "wal_writer_initialized",
            topic=self.config.wal_topic,
            batch_flush_interval_ms=self.config.batch_flush_interval_ms,
            batch_size_max=self.config.batch_size_max,
            batch_size_bytes=self.config.batch_size_bytes,
        )

    async def log(self, entry: WALLogEntry) -> WALWriteResult:
        """
        Log orchestration decision to K0 WAL.

        This method buffers the log entry locally, flushes batch if size limit reached,
        otherwise waits for 250ms timer to flush batch to K0 Command Port.

        Args:
            entry: WALLogEntry to log

        Returns:
            WALWriteResult with receipt_id, write_latency_ms, batched flag

        Raises:
            TimeoutError: If write timeout exceeded (5s)

        Performance:
            - Target: <5ms P95 (local buffer, async flush)

        ADR: ADR-0008c (WAL log write)
        Assigned to: Issue #L5-1.4.1
        """
        # TODO(@infrastructure-team): Implement log write (ADR-0008c)
        # 1. Acquire batch lock
        # 2. Add entry to batch buffer
        # 3. If batch size >= 100:
        #    - Flush batch immediately
        #    - Return WALWriteResult(batched=False)
        # 4. Otherwise:
        #    - Return WALWriteResult(batched=True)
        #    - Batch will flush on 250ms timer
        # 5. Emit metrics (k1_wal_writer_logs_total)
        async with self._batch_lock:
            entry_size = self._estimate_entry_size(entry)

            if len(self._batch_buffer) >= self.config.queue_capacity:
                emit_counter(
                    "k1_wal_writer_logs_rejected_total",
                    1,
                    {"reason": "queue_capacity", "topic": entry.topic.value},
                )
                raise RuntimeError("WALWriter queue capacity exceeded")

            if self._batch_buffer_bytes + entry_size > self.config.max_buffer_bytes:
                emit_counter(
                    "k1_wal_writer_logs_rejected_total",
                    1,
                    {"reason": "buffer_bytes", "topic": entry.topic.value},
                )
                raise RuntimeError("WALWriter buffer byte limit exceeded")

            self._batch_buffer.append(entry)
            self._batch_buffer_bytes += entry_size

            emit_gauge(
                "k1_wal_writer_queue_depth",
                len(self._batch_buffer),
                {"topic": self.config.wal_topic},
            )

            should_flush = False
            if len(self._batch_buffer) >= self.config.batch_size_max:
                should_flush = True
            elif self._batch_buffer_bytes >= self.config.batch_size_bytes:
                should_flush = True

            if should_flush:
                result = await self._flush_batch(trigger="count")
                return result

            return WALWriteResult(
                log_id=entry.log_id,
                receipt_id="pending",
                write_latency_ms=0.0,
                batched=True,
            )

    async def replay(
        self, saga_id: str, from_timestamp: Optional[int] = None
    ) -> WALReplayResult:
        """
        Replay WAL logs for crash recovery.

        This method reads SAGA_LOG entries from K0 for the specified saga_id,
        returns all log entries ordered by timestamp for state reconstruction.

        Args:
            saga_id: Saga identifier to replay
            from_timestamp: Optional start timestamp (replay logs >= timestamp)

        Returns:
            WALReplayResult with logs_replayed, replay_latency_ms

        Raises:
            TimeoutError: If replay timeout exceeded (5s)

        Performance:
            - Target: <50ms P95 (read from K0 WAL)

        ADR: ADR-0008c (WAL replay for crash recovery)
        Assigned to: Issue #L5-1.4.1
        """
        # TODO(@infrastructure-team): Implement replay (ADR-0008c)
        # 1. Query K0 Command Port for SAGA_LOG entries
        # 2. Filter by saga_id
        # 3. Filter by from_timestamp (if provided)
        # 4. Sort by timestamp ascending
        # 5. Return WALReplayResult with logs, latency
        # 6. Emit metrics (k1_wal_writer_replay_duration_seconds)
        start_time = time.perf_counter()

        # Replay logic here (query K0)
        logs_replayed = 0

        replay_latency_ms = (time.perf_counter() - start_time) * 1000

        self._logger.info(
            "wal_replay_complete",
            saga_id=saga_id,
            logs_replayed=logs_replayed,
            replay_latency_ms=replay_latency_ms,
        )

        return WALReplayResult(
            logs_replayed=logs_replayed, replay_latency_ms=replay_latency_ms
        )

    async def shutdown(self) -> None:
        """
        Graceful shutdown sequence.

        This method flushes pending logs, cancels batch flush timer, closes K0 connection.

        Lifecycle:
            - Flush pending batch
            - Cancel batch flush timer
            - Close command_client connection

        ADR: ADR-0008c (WAL Writer shutdown)
        Assigned to: Issue #L5-1.4.1
        """
        # TODO(@infrastructure-team): Implement shutdown (ADR-0008c)
        # 1. Set shutdown event
        # 2. Flush pending batch
        # 3. Cancel batch flush timer
        # 4. Close command_client connection
        # 5. Log shutdown event
        self._shutdown_event.set()

        async with self._batch_lock:
            if self._batch_buffer:
                await self._flush_batch(trigger="shutdown")

        if self._flush_task:
            self._flush_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._flush_task

        self._flush_task = None
        self._logger.info("wal_writer_shutdown_complete")

    # =========================================================================
    # PRIVATE METHODS (Implementation Details)
    # =========================================================================

    async def _batch_flush_loop(self) -> None:
        """
        Background batch flush timer (250ms interval).

        This method runs in background, flushes batch every 250ms if non-empty.

        ADR: ADR-0022 (Bounded Batching - 250ms flush interval)
        Assigned to: Issue #L5-1.4.1
        """
        # TODO(@infrastructure-team): Implement batch flush loop (ADR-0022)
        # 1. Loop until shutdown event
        # 2. Sleep 250ms
        # 3. Acquire batch lock
        # 4. If batch non-empty: flush batch
        # 5. Release batch lock
        interval = self.config.batch_flush_interval_ms / 1000
        try:
            while not self._shutdown_event.is_set():
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            while not self._shutdown_event.is_set():
                async with self._batch_lock:
                    if self._batch_buffer:
                        await self._flush_batch(trigger="timer")
                        self._last_flush_monotonic = time.monotonic()
                try:
                    await asyncio.wait_for(self._shutdown_event.wait(), timeout=interval)
                except asyncio.TimeoutError:
                    continue

    async def _flush_batch(self, trigger: str) -> WALWriteResult:
        """
        Flush batch buffer to K0 Command Port.

        Side Effects:
            - Sends batch to K0 Command Port (P02)
            - Clears batch buffer
            - Emits metrics

        Returns:
            WALWriteResult for last log in batch

        ADR: ADR-0008c (WAL batch flush)
        Assigned to: Issue #L5-1.4.1
        """
        if not self._batch_buffer:
            return WALWriteResult(
                log_id="batch_none",
                receipt_id="noop",
                write_latency_ms=0.0,
                batched=False,
            )

        start_time = time.perf_counter()
        entries = list(self._batch_buffer)
        batch_bytes = self._batch_buffer_bytes
        self._batch_buffer = []
        self._batch_buffer_bytes = 0
        emit_gauge("k1_wal_writer_queue_depth", 0, {"topic": self.config.wal_topic})

        batch_id = f"wal_{uuid.uuid4()}"
        payload_dict = {
            "batch_id": batch_id,
            "topic": self.config.wal_topic,
            "count": len(entries),
            "trigger": trigger,
            "generated_at_ms": int(time.time() * 1000),
            "entries": [
                {
                    "log_id": entry.log_id,
                    "topic": entry.topic.value,
                    "log_type": entry.log_type.value,
                    "saga_id": entry.saga_id,
                    "timestamp": entry.timestamp,
                    "payload": entry.payload,
                    "cognitive_trace_id": entry.cognitive_trace_id,
                }
                for entry in entries
            ],
        }

        serialized = json.dumps(payload_dict, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

        saga_ids = {entry.saga_id for entry in entries}
        session_id = saga_ids.pop() if len(saga_ids) == 1 else "wal_batch"
        trace_id = next((entry.cognitive_trace_id for entry in entries if entry.cognitive_trace_id), batch_id)

        command = Command(
            command_id=str(uuid.uuid4()),
            command_type=CommandType.MEMORY_WRITE,
            session_id=session_id,
            cognitive_trace_id=trace_id,
            payload=serialized,
            priority=CommandType.MEMORY_WRITE.value == "MEMORY_WRITE",
        )

        # Command.priority expects int; ensure proper value
        command.priority = 1

        with create_span(
            "k0_bridge.wal_writer.flush",
            batch_id=batch_id,
            topic=self.config.wal_topic,
            trigger=trigger,
            entry_count=len(entries),
            size_bytes=len(serialized),
        ) as span:
            span.set_attribute("queue_bytes", batch_bytes)
            receipt = await self.command_client.send_command(command, cognitive_trace_id=trace_id)

        flush_latency_ms = (time.perf_counter() - start_time) * 1000
        emit_histogram(
            "k1_wal_writer_batch_flush_duration_seconds",
            flush_latency_ms / 1000.0,
            {"topic": self.config.wal_topic, "trigger": trigger},
        )
        emit_counter(
            "k1_wal_writer_logs_total",
            len(entries),
            {"topic": self.config.wal_topic},
        )

        self._pending_receipts[receipt.receipt_id] = receipt
        if len(self._pending_receipts) > self.config.pending_receipts_max:
            self._logger.warning(
                "wal_writer_pending_receipts_high",
                pending=len(self._pending_receipts),
                max_allowed=self.config.pending_receipts_max,
            )

        self._logger.info(
            "wal_batch_flushed",
            topic=self.config.wal_topic,
            batch_count=len(entries),
            flush_latency_ms=round(flush_latency_ms, 2),
            receipt_id=receipt.receipt_id,
        )

        return WALWriteResult(
            log_id=batch_id,
            receipt_id=receipt.receipt_id,
            write_latency_ms=flush_latency_ms,
            batched=False,
        )

    def _estimate_entry_size(self, entry: WALLogEntry) -> int:
        entry_dict = {
            "log_id": entry.log_id,
            "topic": entry.topic.value,
            "log_type": entry.log_type.value,
            "saga_id": entry.saga_id,
            "timestamp": entry.timestamp,
            "payload": entry.payload,
        }
        if entry.cognitive_trace_id:
            entry_dict["cognitive_trace_id"] = entry.cognitive_trace_id
        return len(json.dumps(entry_dict, ensure_ascii=False).encode("utf-8"))

    def _validate_config(self, config: "WALWriterConfig") -> None:
        if not config.wal_topic:
            raise ValueError("wal_topic must be provided")
        if config.batch_flush_interval_ms <= 0:
            raise ValueError("batch_flush_interval_ms must be positive")
        if config.batch_size_max <= 0:
            raise ValueError("batch_size_max must be positive")
        if config.batch_size_bytes <= 0:
            raise ValueError("batch_size_bytes must be positive")
        if config.queue_capacity <= 0:
            raise ValueError("queue_capacity must be positive")
        if config.max_buffer_bytes <= 0:
            raise ValueError("max_buffer_bytes must be positive")
        if config.pending_receipts_max <= 0:
            raise ValueError("pending_receipts_max must be positive")


@dataclass
class WALWriterConfig:
    """
    WAL Writer configuration.

    Fields:
        wal_topic: K0 topic for logs (default: SAGA_LOG)
        retention_days: Log retention in K0 (default: 7 days)
        write_timeout_ms: Write timeout (default: 5s)
        batch_flush_interval_ms: Batch flush interval (default: 250ms, aligned with ADR-0022)
        batch_size_max: Max logs per batch (default: 100)
        replay_cache_size: Replay cache size (default: 1000 logs)
    """

    wal_topic: str = DEFAULT_CONFIG["wal_topic"]
    retention_days: int = DEFAULT_CONFIG["retention_days"]
    write_timeout_ms: int = DEFAULT_CONFIG["write_timeout_ms"]
    batch_flush_interval_ms: int = DEFAULT_CONFIG["batch_flush_interval_ms"]
    batch_size_max: int = DEFAULT_CONFIG["batch_size_max"]
    batch_size_bytes: int = DEFAULT_CONFIG["batch_size_bytes"]
    replay_cache_size: int = DEFAULT_CONFIG["replay_cache_size"]
    queue_capacity: int = DEFAULT_CONFIG["queue_capacity"]
    max_buffer_bytes: int = DEFAULT_CONFIG["max_buffer_bytes"]
    pending_receipts_max: int = DEFAULT_CONFIG["pending_receipts_max"]


# =============================================================================
# SECTION 5: HELPER FUNCTIONS & EXCEPTIONS
# =============================================================================


class WALWriteError(Exception):
    """Raised when WAL write fails"""

    pass


class WALReplayError(Exception):
    """Raised when WAL replay fails"""

    pass


def create_wal_writer(
    config: Optional[WALWriterConfig] = None, command_client: Optional[Any] = None
) -> WALWriter:
    """
    Create WALWriter with default or provided configuration.

    Args:
        config: WALWriterConfig (default: SAGA_LOG topic, 250ms batching)
        command_client: CommandClient for K0 writes

    Returns:
        WALWriter instance

    ADR: ADR-0008c (WAL Writer factory)
    Assigned to: Issue #L5-1.4.1
    """
    if config is None:
        config = WALWriterConfig()

    return WALWriter(config, command_client)


# =============================================================================
# SECTION 6: MODULE EXPORTS & INITIALIZATION
# =============================================================================

__all__ = [
    "WALWriter",
    "WALWriterConfig",
    "WALLogEntry",
    "WALWriteResult",
    "WALReplayResult",
    "WALTopic",
    "WALLogType",
    "WALWriteError",
    "WALReplayError",
    "create_wal_writer",
]


# =============================================================================
# OBSERVABILITY INTEGRATION
# =============================================================================
# Metrics to export (Prometheus):
#   - k1_wal_writer_logs_total{counter, labels: topic}
#   - k1_wal_writer_batch_flush_duration_seconds{histogram}
#   - k1_wal_writer_replay_duration_seconds{histogram}
#
# Traces to generate (OpenTelemetry):
#   - Span name: k0_bridge.wal_writer.log
#   - Span name: k0_bridge.wal_writer.replay
#   - Attributes: topic, saga_id, log_count, latency_ms
#
# Logs to emit (structured logging):
#   - Level: INFO (wal_log_written, wal_batch_flushed, wal_replay_complete)
#   - Fields: component='wal_writer', topic, saga_id, log_id, batch_count, latency_ms
#
# =============================================================================

# =============================================================================
# TESTING REQUIREMENTS (WARD Framework)
# =============================================================================
# Integration tests required:
#   - tests/k1/bridge_k0/test_wal_writer.py
#   - Test log write (SAGA_START → buffer → batch flush → K0 receipt)
#   - Test batch flush (250ms timer, 100 log count trigger)
#   - Test replay (read SAGA_LOG from K0, reconstruct saga state)
#   - Test crash recovery (incomplete saga → replay → resume compensation)
#
# No simulation code allowed:
#   - Use real K0 Command Port mock with SAGA_LOG topic
#   - Test with real batching (250ms timer, 100 log limit)
#   - Integration tests > unit tests
#
# Performance budget tests:
#   - Assert log write <5ms P95 (local buffer)
#   - Assert batch flush <100ms P95 (K0 Command Port)
#   - Assert replay <50ms P95 (K0 WAL read)
#
# =============================================================================
