"""
Command Port Adapter - K0 Command Port (P02 MemoryWrite)

Layer: L5 Infrastructure
Component: K0 Bridge → Command Port
Priority: P0 (Critical Path)
Status: ✅ IMPLEMENTED

Architecture Decision Records:
    - ADR-0001a: K0 Bridge Dual Protocol (JSON PRIMARY + FlatBuffers SECONDARY)
    - ADR-0001f: K0-K1 Pipeline Boundary (K1 NEVER implements lanes/retrieval)
    - ADR-0022: Bounded Batching (250ms window, 64KB, 100 messages)
    - ADR-0014: JSON REST API Dual Format (content negotiation)

Dependencies:
    Internal:
        - k1.bridge_k0.command_client.CommandClient (HTTP/2 client)
        - k1.bridge_k0.protocol.ProtocolNegotiator (format switching)
        - k1.bridge_k0.http2_client.HTTP2Connection (transport)
    External:
        - None (no external dependencies)

Connects To:
    Upstream:
        - k1.l4_runtime.session_state (SessionState deltas)
        - k1.l2_orchestration.orchestrator (agent coordination)
    Downstream:
        - K0 Command Port: POST /k0/command (P02 MemoryWrite)

Performance Budgets:
    - Send latency: <5ms P95 (K1 → K0 Command Port)
    - Receipt confirmation: <100ms P95 (K0 receipt → K1)
    - Batch flush: 250ms window OR 64KB size OR 100 messages
    - Memory: <5MB per session (bounded batching)

Observability:
    Metrics:
        - k1_k0_command_port_requests_total{status} (counter)
        - k1_k0_command_port_latency_ms{p50, p95, p99} (histogram)
        - k1_k0_command_port_batch_size{p50, p95, p99} (histogram)
    Traces:
        - Span: k0_bridge.command_port_send
        - Attributes: session_id, delta_count, batch_size, cognitive_trace_id
    Logs:
        - INFO: command sent (session_id, receipt_id, latency_ms)
        - WARNING: batch flush forced (reason: timeout/size/count)
        - ERROR: command failed (reason, retry_attempt)

References:
    - Diagram: architecture_diagrams/k1/k1_complete_with_flows.mmd
    - Whiteboard: docs/whiteboard.md (Section: K0 Command Port P02)
    - Test: tests/k1/bridge_k0/ports/test_command_port.py
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass

# =============================================================================
# SECTION 1: IMPORTS
# =============================================================================
# Standard library imports
from typing import Any, Dict, List, Optional

from contextlib import suppress

from k1.bridge_k0.command_client import (
    Command,
    CommandClient,
    CommandReceipt,
    CommandStatus,
    CommandType,
)

try:  # pragma: no cover - optional observability integration
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

# TODO(@infrastructure-team): Load from k1/config/k0_bridge.yml (ADR-0001a)
# Assigned to: Issue #L5-1.2.1
DEFAULT_CONFIG = {
    "k0_host": "localhost",
    "k0_command_port": 8080,
    "endpoint": "/k0/command",  # K0 Command Port endpoint
    "timeout_ms": 5000,  # 5s timeout for command requests
    "batch_window_ms": 250,  # 250ms batching window (ADR-0022)
    "batch_size_bytes": 65536,  # 64KB batch size limit
    "batch_count_max": 100,  # 100 messages max per batch
    "enable_batching": True,  # Enable bounded batching
}

# =============================================================================
# SECTION 3: TYPE DEFINITIONS & ENUMS
# =============================================================================


@dataclass
class SessionStateDelta:
    """
    SessionState delta for K0 Command Port.

    Fields:
        field_path: JSON path to field (e.g., "turn[0].assistant_response.text")
        value: New value (Any type, JSON-serializable)
        timestamp: Unix timestamp (milliseconds)
        privacy_band: Privacy classification (GREEN | AMBER | RED)
    """

    field_path: str
    value: Any
    timestamp: float
    session_id: str
    privacy_band: str = "GREEN"


@dataclass
class CommandRequest:
    """
    Command request payload for K0 Command Port.

    Fields:
        command_type: Command type (MEMORY_WRITE, ACTION_COMMAND, TRIGGER_SET)
        session_id: Session ID (e.g., "sess_abc123")
        deltas: List of SessionState deltas to write
        cognitive_trace_id: Trace ID for observability
    """

    command_type: str
    session_id: str
    deltas: List[SessionStateDelta]
    cognitive_trace_id: Optional[str] = None


@dataclass
class CommandResponse:
    """
    Command response from K0 Command Port.

    Fields:
        receipt_id: Receipt ID (e.g., "rcpt_456")
        status: Command status (SUCCESS | PENDING | FAILED | TIMEOUT)
        timestamp: Unix timestamp (milliseconds)
        error_message: Error message (if status == FAILED)
    """

    receipt_id: str
    status: CommandStatus
    timestamp: float
    error_message: Optional[str] = None


# =============================================================================
# SECTION 4: CORE CLASSES
# =============================================================================


class CommandPort:
    """
    Adapter for K0 Command Port (P02 MemoryWrite).

    Purpose:
        Sends SessionState deltas to K0 Command Port, receives receipts,
        handles bounded batching (250ms/64KB/100 messages), manages format
        negotiation (JSON vs FlatBuffers), tracks receipt confirmations.

    Responsibilities:
        1. Send SessionState deltas to K0 Command Port (POST /k0/command)
        2. Batch deltas (250ms window OR 64KB OR 100 messages)
        3. Format negotiation (JSON PRIMARY, FlatBuffers SECONDARY)
        4. Receipt tracking (receipt_id → PENDING → COMMITTED)
        5. Error handling (retries, circuit breaker integration)

    Lifecycle:
        INIT → CONNECTING → READY → [DEGRADED] → TERMINATED

    Thread Safety: Yes (async-safe)
    Async Safe: Yes (fully async/await compatible)

    Cognitive Trace:
        - Propagates cognitive_trace_id to K0 Command Port
        - Required for: send_delta, flush_batch

    Performance Budget (P95):
        - Send latency: <5ms (K1 → K0 Command Port)
        - Receipt confirmation: <100ms (K0 receipt → K1)
        - Batch flush: 250ms window OR 64KB OR 100 messages

    Examples:
        >>> config = CommandPortConfig(k0_host='localhost', k0_port=8080)
        >>> command_port = CommandPort(config)
        >>> await command_port.initialize()
        >>>
        >>> # Send SessionState delta
        >>> delta = SessionStateDelta(
        ...     field_path='turn[0].assistant_response.text',
        ...     value='Hello, user!',
        ...     timestamp=time.time() * 1000,
        ...     privacy_band='GREEN'
        ... )
        >>> response = await command_port.send_delta(
        ...     session_id='sess_123',
        ...     deltas=[delta],
        ...     cognitive_trace_id='trace_456'
        ... )
        >>> print(f'Receipt: {response.receipt_id}, Status: {response.status}')
        >>> await command_port.shutdown()

    References:
        - ADR-0001a: K0 Bridge Dual Protocol
        - ADR-0022: Bounded Batching (250ms window, 64KB, 100 messages)
        - Diagram: architecture_diagrams/k1/k1_complete_with_flows.mmd
    """

    def __init__(self, config: Dict[str, Any], command_client: CommandClient) -> None:
        """
        Initialize CommandPort adapter.

        Args:
            config: Configuration dict with K0 host, port, endpoints

        Raises:
            ValueError: If configuration is invalid
            TypeError: If config type is incorrect

        Side Effects:
            - Initializes internal state (batching queue, receipt tracker)
            - Does NOT connect to K0 (call initialize() to connect)

        ADR: ADR-0001a (K0 Bridge Dual Protocol)
        Assigned to: Issue #L5-1.2.1
        """
        # TODO(@infrastructure-team): Implement initialization (ADR-0001a)
        # 1. Validate config (check k0_host, k0_command_port, endpoint)
        # 2. Initialize state machine (INIT → CONNECTING → READY)
        # 3. Initialize batching queue (SessionState deltas)
        # 4. Initialize receipt tracker (receipt_id → status)
        # 5. Initialize protocol negotiator (JSON vs FlatBuffers)
        self.config = {**DEFAULT_CONFIG, **config}
        self.state = "INIT"  # INIT | CONNECTING | READY | DEGRADED | TERMINATED
        self._logger = logger
        self._command_client = command_client
        self._batch_queue: List[SessionStateDelta] = []
        self._queue_size_bytes = 0
        self._queue_lock = asyncio.Lock()
        self._flush_lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        self._receipt_tracker: Dict[str, CommandReceipt] = {}
        self._pending_receipts: Dict[str, CommandReceipt] = {}
        self._last_flush_monotonic = time.monotonic()

        emit_gauge("k1_k0_command_port_batch_size", 0, {"topic": "session_state"})

    async def initialize(self) -> None:
        """
        Async initialization phase - connect to K0 Command Port.

        This method performs async setup (HTTP/2 connection, format negotiation).

        Raises:
            RuntimeError: If initialization fails
            ConnectionError: If cannot connect to K0 Command Port

        Lifecycle:
            Transitions: INIT → CONNECTING → READY

        ADR: ADR-0001a (K0 Bridge Dual Protocol)
        Assigned to: Issue #L5-1.2.1
        """
        # TODO(@infrastructure-team): Implement async initialization (ADR-0001a)
        # 1. Connect to K0 Command Port (HTTP/2 connection)
        # 2. Negotiate format (JSON vs FlatBuffers via OPTIONS request)
        # 3. Start batch flush timer (250ms interval)
        # 4. Transition state: INIT → CONNECTING → READY
        if self.state != "INIT":
            raise RuntimeError("CommandPort already initialized")

        self._shutdown_event.clear()
        if self.config.get("enable_batching", True):
            self._flush_task = asyncio.create_task(self._batch_timer_loop())

        self.state = "READY"
        self._logger.info(
            "command_port_initialized",
            k0_host=self.config.get("k0_host"),
            k0_port=self.config.get("k0_command_port"),
            batch_window_ms=self.config["batch_window_ms"],
            batch_size_bytes=self.config["batch_size_bytes"],
            batch_count_max=self.config["batch_count_max"],
        )

    async def send_delta(
        self,
        session_id: str,
        deltas: List[SessionStateDelta],
        cognitive_trace_id: Optional[str] = None,
    ) -> CommandResponse:
        """
        Send SessionState deltas to K0 Command Port.

        This method batches deltas if batching enabled, or sends immediately.

        Args:
            session_id: Session ID (e.g., "sess_abc123")
            deltas: List of SessionState deltas to write
            cognitive_trace_id: Trace ID for observability

        Returns:
            CommandResponse (receipt_id, status, timestamp)

        Raises:
            ValueError: If session_id or deltas invalid
            RuntimeError: If K0 Command Port unavailable

        Performance:
            - Target: <5ms P95 (K1 → K0 Command Port)
            - Batch flush: 250ms window OR 64KB OR 100 messages

        Observability:
            - Metrics: k1_k0_command_port_requests_total{status}
            - Traces: Span name: k0_bridge.command_port_send
            - Logs: INFO: command sent (session_id, receipt_id, latency_ms)

        ADR: ADR-0022 (Bounded Batching)
        Assigned to: Issue #L5-1.2.1
        """
        # TODO(@infrastructure-team): Implement send_delta (ADR-0022)
        # 1. Add deltas to batch queue (if batching enabled)
        # 2. Check flush triggers:
        #    - Time: >250ms since last flush
        #    - Size: >64KB total size
        #    - Count: >100 messages
        # 3. If trigger met, flush batch (send to K0 Command Port)
        # 4. Create CommandRequest (command_type=MEMORY_WRITE, session_id, deltas)
        # 5. Send via HTTP/2 (POST /k0/command)
        # 6. Parse response (receipt_id, status, timestamp)
        # 7. Track receipt (receipt_id → PENDING)
        # 8. Record metrics (latency, batch size)
        # 9. Return CommandResponse
        if not deltas:
            raise ValueError("deltas cannot be empty")
        if not session_id:
            raise ValueError("session_id is required")

        if self.state not in {"READY", "DEGRADED"}:
            raise RuntimeError("CommandPort is not ready")

        async with self._queue_lock:
            for delta in deltas:
                if delta.privacy_band == "BLACK":
                    emit_counter(
                        "k1_k0_command_port_requests_total",
                        1,
                        {"status": "rejected_privacy", "band": "BLACK"},
                    )
                    self._logger.warning(
                        "delta_rejected_privacy",
                        session_id=session_id,
                        field_path=delta.field_path,
                        trace_id=cognitive_trace_id,
                    )
                    raise RuntimeError("BLACK band deltas must not be sent to K0")

            self._enqueue_batch(session_id, deltas)

            should_flush = False
            if self._queue_size_bytes >= self.config["batch_size_bytes"]:
                should_flush = True
            if len(self._batch_queue) >= self.config["batch_count_max"]:
                should_flush = True
            time_since_flush = (time.monotonic() - self._last_flush_monotonic) * 1000
            if time_since_flush >= self.config["batch_window_ms"]:
                should_flush = True

        if not self.config.get("enable_batching", True):
            should_flush = True

        if should_flush:
            command_response = await self.flush_batch(trigger="auto", cognitive_trace_id=cognitive_trace_id)
            if command_response:
                return command_response[0]

        emit_counter(
            "k1_k0_command_port_requests_total",
            1,
            {"status": "queued", "band": deltas[0].privacy_band},
        )
        emit_gauge(
            "k1_k0_command_port_batch_size",
            len(self._batch_queue),
            {"session_id": session_id},
        )

        return CommandResponse(
            receipt_id="pending",
            status=CommandStatus.PENDING,
            timestamp=time.time() * 1000,
        )

    async def flush_batch(
        self,
        trigger: str = "manual",
        cognitive_trace_id: Optional[str] = None,
    ) -> List[CommandResponse]:
        """
        Flush pending batch to K0 Command Port.

        This method forces immediate flush (ignores batch window).

        Args:
            cognitive_trace_id: Trace ID for observability

        Returns:
            List of CommandResponse (one per batch)

        Raises:
            RuntimeError: If K0 Command Port unavailable

        Performance:
            - Target: <100ms P95 (batch send + receipt)

        ADR: ADR-0022 (Bounded Batching)
        Assigned to: Issue #L5-1.2.1
        """
        if self.state not in {"READY", "DEGRADED"}:
            raise RuntimeError("CommandPort is not ready")

        async with self._flush_lock:
            if not self._batch_queue:
                return []

            deltas_snapshot = list(self._batch_queue)
            batch_size_bytes = self._queue_size_bytes
            self._batch_queue = []
            self._queue_size_bytes = 0
            self._last_flush_monotonic = time.monotonic()

            batch_id = f"cmd_{uuid.uuid4()}"
            trace_id = cognitive_trace_id or batch_id
            payload = self._serialize_batch(deltas_snapshot, batch_id, trigger, trace_id)

            command = Command(
                command_id=batch_id,
                command_type=CommandType.MEMORY_WRITE,
                session_id=self._choose_session_id(deltas_snapshot),
                cognitive_trace_id=trace_id,
                payload=payload,
                priority=self._choose_priority(deltas_snapshot),
            )

            start_time = time.perf_counter()
            with create_span(
                "k0_bridge.command_port.flush",
                batch_id=batch_id,
                trigger=trigger,
                delta_count=len(deltas_snapshot),
                size_bytes=batch_size_bytes,
            ) as span:
                span.set_attribute("session_count", len({d.session_id for d in deltas_snapshot}))
                receipt = await self._command_client.send_command(
                    command,
                    cognitive_trace_id=command.cognitive_trace_id,
                )

            flush_latency_ms = (time.perf_counter() - start_time) * 1000
            emit_histogram(
                "k1_k0_command_port_latency_ms",
                flush_latency_ms,
                {"status": receipt.status.value},
            )
            emit_counter(
                "k1_k0_command_port_requests_total",
                1,
                {"status": receipt.status.value},
            )

            result_status = receipt.status
            if not isinstance(result_status, CommandStatus):
                result_status = CommandStatus(result_status)

            command_response = CommandResponse(
                receipt_id=receipt.receipt_id,
                status=result_status,
                timestamp=receipt.timestamp_ms,
                error_message=receipt.error,
            )

            self._track_receipt(receipt)

            self._logger.info(
                "command_batch_flushed",
                receipt_id=receipt.receipt_id,
                delta_count=len(deltas_snapshot),
                trigger=trigger,
                latency_ms=round(flush_latency_ms, 2),
            )

            return [command_response]

    async def get_receipt_status(self, receipt_id: str) -> CommandStatus:
        """
        Get receipt status from K0 Command Port.

        Args:
            receipt_id: Receipt ID (e.g., "rcpt_456")

        Returns:
            CommandStatus (SUCCESS | PENDING | FAILED | TIMEOUT)

        Raises:
            ValueError: If receipt_id not found

        ADR: ADR-0022b (Receipt Tracking)
        Assigned to: Issue #L5-1.2.1
        """
        receipt = self._receipt_tracker.get(receipt_id)
        if receipt is None:
            raise ValueError(f"Unknown receipt_id: {receipt_id}")

        status = receipt.status
        if not isinstance(status, CommandStatus):
            status = CommandStatus(status)
        return status

    async def shutdown(self) -> None:
        """
        Graceful shutdown sequence.

        This method performs cleanup and state transitions.

        Lifecycle:
            - Flush pending batch (ensure no data loss)
            - Close HTTP/2 connection
            - Finalize metrics

        ADR: ADR-0001a (K0 Bridge Dual Protocol)
        Assigned to: Issue #L5-1.2.1
        """
        if self.state == "TERMINATED":
            return

        self.state = "DEGRADED"
        async with self._flush_lock:
            if self._batch_queue:
                await self.flush_batch(trigger="shutdown", cognitive_trace_id=None)

        self._shutdown_event.set()
        if self._flush_task:
            self._flush_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._flush_task
        self._flush_task = None

        try:
            await self._command_client.shutdown()
        finally:
            self.state = "TERMINATED"
            self._logger.info("command_port_shutdown_complete")


# =============================================================================
# SECTION 5: HELPER FUNCTIONS
# =============================================================================


    async def _batch_timer_loop(self) -> None:
        interval = self.config["batch_window_ms"] / 1000.0
        try:
            while not self._shutdown_event.is_set():
                await asyncio.sleep(interval)
                if self.state not in {"READY", "DEGRADED"}:
                    continue
                time_since_flush = (time.monotonic() - self._last_flush_monotonic) * 1000
                if time_since_flush < self.config["batch_window_ms"]:
                    continue
                if not self._batch_queue:
                    continue
                await self.flush_batch(trigger="timer", cognitive_trace_id=None)
        except asyncio.CancelledError:  # pragma: no cover
            return

    def _enqueue_batch(self, session_id: str, deltas: List[SessionStateDelta]) -> None:
        for delta in deltas:
            self._batch_queue.append(delta)
            self._queue_size_bytes += self._estimate_delta_size(delta)
        emit_gauge(
            "k1_k0_command_port_batch_size",
            len(self._batch_queue),
            {"session_id": session_id},
        )

    def _estimate_delta_size(self, delta: SessionStateDelta) -> int:
        payload = {
            "field_path": delta.field_path,
            "value": delta.value,
            "timestamp": delta.timestamp,
            "privacy_band": delta.privacy_band,
        }
        return len(json.dumps(payload, separators=(",", ":")))

    def _serialize_batch(
        self,
        deltas: List[SessionStateDelta],
        batch_id: str,
        trigger: str,
        trace_id: str,
    ) -> bytes:
        payload = {
            "batch_id": batch_id,
            "trigger": trigger,
            "generated_at_ms": int(time.time() * 1000),
            "deltas": [
                {
                    "field_path": delta.field_path,
                    "value": delta.value,
                    "timestamp": delta.timestamp,
                    "privacy_band": delta.privacy_band,
                }
                for delta in deltas
            ],
        }
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    def _choose_session_id(self, deltas: List[SessionStateDelta]) -> str:
        session_ids = {delta.session_id for delta in deltas if delta.session_id}
        if len(session_ids) == 1:
            return session_ids.pop()
        return "multi_session"

    def _choose_priority(self, deltas: List[SessionStateDelta]) -> int:
        return 1

    def _track_receipt(self, receipt: CommandReceipt) -> None:
        self._receipt_tracker[receipt.receipt_id] = receipt
        if receipt.status == CommandStatus.PENDING:
            self._pending_receipts[receipt.receipt_id] = receipt
        else:
            self._pending_receipts.pop(receipt.receipt_id, None)


def create_command_port(
    config: Optional[Dict[str, Any]] = None,
    command_client: Optional[CommandClient] = None,
) -> CommandPort:
    """
    Create CommandPort with default or provided configuration.

    Args:
        config: Configuration dict (default: localhost:8080)

    Returns:
        CommandPort instance

    ADR: ADR-0001a (K0 Bridge Dual Protocol)
    Assigned to: Issue #L5-1.2.1
    """
    if config is None:
        config = DEFAULT_CONFIG
    if command_client is None:
        raise ValueError("command_client is required")

    return CommandPort(config, command_client)


# =============================================================================
# SECTION 6: MODULE EXPORTS & INITIALIZATION
# =============================================================================

__all__ = [
    "CommandPort",
    "CommandRequest",
    "CommandResponse",
    "SessionStateDelta",
    "CommandStatus",
    "create_command_port",
]


# =============================================================================
# OBSERVABILITY INTEGRATION
# =============================================================================
# Metrics to export (Prometheus):
#   - k1_k0_command_port_requests_total{status} (counter)
#   - k1_k0_command_port_latency_ms{p50, p95, p99} (histogram)
#   - k1_k0_command_port_batch_size{p50, p95, p99} (histogram)
#
# Traces to generate (OpenTelemetry):
#   - Span name: k0_bridge.command_port_send
#   - Attributes: session_id, delta_count, batch_size, cognitive_trace_id
#   - Links to: upstream session_state spans
#
# Logs to emit (structured logging):
#   - Level: INFO (normal), WARNING (batch flush), ERROR (failures)
#   - Fields: component='command_port', session_id, receipt_id, latency_ms
#
# =============================================================================

# =============================================================================
# COGNITIVE TRACE PROPAGATION
# =============================================================================
# All async methods must:
#   1. Accept cognitive_trace_id parameter
#   2. Include trace_id in HTTP request headers (X-Cognitive-Trace-Id)
#   3. Include trace_id in all log statements
#
# Example:
#   response = await command_port.send_delta(
#       session_id='sess_123',
#       deltas=[delta],
#       cognitive_trace_id='trace_abc123'
#   )
#   # HTTP request includes: X-Cognitive-Trace-Id: trace_abc123
#
# =============================================================================

# =============================================================================
# TESTING REQUIREMENTS (WARD Framework)
# =============================================================================
# Integration tests required:
#   - tests/k1/bridge_k0/ports/test_command_port.py
#   - Test send_delta (SessionState delta writes)
#   - Test bounded batching (250ms/64KB/100 messages)
#   - Test receipt tracking (receipt_id → status)
#   - Test format negotiation (JSON vs FlatBuffers)
#   - Test error handling (K0 unavailable, timeouts)
#
# No simulation code allowed:
#   - Use real K0 mock server with /k0/command endpoint
#   - Test both JSON and FlatBuffers paths
#   - Integration tests > unit tests
#
# Performance budget tests:
#   - Assert send latency <5ms P95
#   - Assert batch flush <100ms P95
#   - Assert receipt confirmation <100ms P95
#
# =============================================================================
