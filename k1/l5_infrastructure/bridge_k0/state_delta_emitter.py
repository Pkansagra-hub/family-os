"""
State Delta Emitter - SessionState Incremental Updates

Layer: L5 Infrastructure
Component: K0 Bridge → State Delta Emitter
Priority: P1 (Performance Optimization)
Status: 🚧 STUB - NEEDS_IMPLEMENTATION

Architecture Decision Records:
    - ADR-0001a: K0 Bridge Communication Protocol (delta-based updates, field_path)
    - ADR-0022: K0 Bridge Bounded Batching (250ms batching, 64KB size trigger)
    - ADR-0019: FlatBuffers SessionState Serialization (SessionSection enum)

Dependencies:
    Internal:
        - k1.bridge_k0.command_client (CommandClient for K0 writes)
        - k1.bridge_k0.batch_client (BatchClient for batching)
        - k1.l4_runtime.session_state (SessionState, SessionSection)
    External:
        - asyncio (async runtime)
        - time (timestamps)
        - deepdiff (field-level diffing)

Connects To:
    Upstream:
        - k1.l4_runtime.session_state.manager (tracks SessionState changes)
        - k1.l2_orchestration.orchestrator (emits state deltas on decision)
    Downstream:
        - K0 Command Port (P02 MemoryWrite → StateDelta batches)

Performance Budgets:
    - Delta compute: <1ms P95 (field-level diff)
    - Delta emit: <5ms P95 (local buffer, async flush)
    - Batch flush: <100ms P95 (K0 Command Port latency)
    - Network reduction: 90%+ vs full state (128KB → 12KB)

Observability:
    Metrics:
        - k1_state_delta_emitter_deltas_total{counter, labels: section}
        - k1_state_delta_emitter_bytes_saved_total{counter}
        - k1_state_delta_emitter_batch_flush_duration_seconds{histogram}
    Traces:
        - Span: k0_bridge.state_delta_emitter.compute_delta
        - Span: k0_bridge.state_delta_emitter.emit
    Logs:
        - DEBUG: delta_computed (session_id, section, field_path, operation)
        - INFO: delta_batch_flushed (delta_count, bytes_saved, flush_latency_ms)

References:
    - ADR-0001a: K0 Bridge Delta-Based Updates
    - ADR-0022: Bounded Batching (250ms flush, 64KB trigger)
    - Research: Operational Transformation (Ellis & Gibbs 1989) - Collaborative editing
    - Diagram: architecture_diagrams/k1/k1_complete_with_flows.mmd
    - Test: tests/k1/bridge_k0/test_state_delta_emitter.py
"""

import asyncio
import logging
import time
from contextlib import suppress
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, List, Optional

# Third-party imports
try:  # pragma: no cover - optional dependency
    from deepdiff import DeepDiff  # type: ignore
except (ModuleNotFoundError, ImportError):  # pragma: no cover
    DeepDiff = None  # type: ignore

# Internal imports
from k1.bridge_k0.batch_client import (
    BatchClient,
    FlushTrigger,
    SessionStateDelta,
)
from k1.bridge_k0.command_client import CommandClient

try:  # pragma: no cover - observability package may not yet exist
    from k1.l5_infrastructure.observability import (  # type: ignore
        create_span,
        emit_counter,
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

    def emit_counter(_name: str, _value: float = 1.0, _labels: Optional[dict] = None) -> None:
        return None

    def emit_histogram(_name: str, _value: float, _labels: Optional[dict] = None) -> None:
        return None


# Configure module logger
logger = logging.getLogger(__name__)

# =============================================================================
# SECTION 2: CONSTANTS & CONFIGURATION
# =============================================================================

# TODO(@infrastructure-team): Load from k1/config/k0_bridge.yml (ADR-0001a)
# Assigned to: Issue #L5-1.4.2
DEFAULT_CONFIG = {
    "batch_flush_interval_ms": 250,  # 250ms batch flush (aligned with ADR-0022)
    "batch_size_max_bytes": 65536,  # 64KB batch size trigger
    "batch_count_max": 100,  # 100 deltas per batch
    "diff_max_depth": 10,  # Max diff depth (prevent infinite recursion)
    "compression_threshold_bytes": 4096,  # 4KB compression threshold
}

# =============================================================================
# SECTION 3: TYPE DEFINITIONS & ENUMS
# =============================================================================


class DeltaOperation(Enum):
    """Delta operation types (ADR-0001a)"""

    SET = "SET"  # Set field value
    DELETE = "DELETE"  # Delete field
    APPEND = "APPEND"  # Append to array


class SessionSection(Enum):
    """SessionState section types (ADR-0019)"""

    BELIEFS = "BELIEFS"  # User facts, preferences
    SCOREBOARD = "SCOREBOARD"  # Capability scores
    CONTROL = "CONTROL"  # Conversation state
    PERSONA = "PERSONA"  # Agent persona
    MULTIMODAL = "MULTIMODAL"  # Images, audio
    META = "META"  # Metadata


@dataclass
class StateDelta:
    """
    SessionState field-level delta.

    Fields:
        session_id: Session identifier
        section: SessionState section (BELIEFS, SCOREBOARD, etc.)
        field_path: JSONPath-style field path (e.g., "beliefs.user_facts[2].value")
        operation: Delta operation (SET, DELETE, APPEND)
        value: New value (for SET/APPEND) or None (for DELETE)
        old_value: Previous value (optional, for debugging)
        timestamp: Unix timestamp (milliseconds)
        cognitive_trace_id: Trace ID for observability
    """

    session_id: str
    section: SessionSection
    field_path: str
    operation: DeltaOperation
    value: Any
    old_value: Optional[Any] = None
    timestamp: Optional[int] = None
    cognitive_trace_id: Optional[str] = None
    privacy_band: str = "GREEN"


@dataclass
class DeltaEmitResult:
    """
    Delta emit operation result.

    Fields:
        deltas_emitted: Number of deltas emitted
        bytes_saved: Bytes saved vs full state transmission
        emit_latency_ms: Emit operation latency (ms)
        batched: Whether deltas were batched (True) or flushed immediately (False)
    """

    deltas_emitted: int
    bytes_saved: int
    emit_latency_ms: float
    batched: bool


# =============================================================================
# SECTION 4: CORE CLASSES
# =============================================================================


class StateDeltaEmitter:
    """
    SessionState incremental update emitter.

    Purpose:
        Tracks field-level changes in SessionState, emits deltas (not full state)
        to K0 Command Port (P02) for incremental updates. Uses field_path notation
        (JSONPath-style) for precise change tracking, batches deltas every 250ms or
        64KB (aligned with ADR-0022), reduces network traffic 90%+ vs full state
        transmission (128KB → 12KB typical).

    Delta-Based Updates (ADR-0001a):
        - Track field-level changes: beliefs.user_facts[2].value = "Emma likes soccer"
        - Emit only changed fields: {"field_path": "beliefs.user_facts[2].value", "operation": "SET", "value": {...}}
        - Reduce network traffic: 128KB full state → 12KB delta (90% reduction)
        - K0 applies deltas: Incremental SessionState updates in CACHE tier

    Field Path Notation (JSONPath-style):
        - Top-level field: "beliefs"
        - Nested object: "beliefs.user_facts"
        - Array element: "beliefs.user_facts[2]"
        - Nested array: "beliefs.user_facts[2].value"

    Responsibilities:
        1. Track SessionState changes (field-level diff)
        2. Emit deltas (not full state) to K0
        3. Batch deltas for efficiency (250ms or 64KB)
        4. Reduce network traffic 90%+ vs full state

    Lifecycle:
        INIT → READY → [track_changes/emit_delta] → SHUTDOWN

    Thread Safety: Yes (async-safe with lock)
    Async Safe: Yes (fully async/await compatible)

    Performance Budget (P95):
        - Delta compute: <1ms (field-level diff)
        - Delta emit: <5ms (local buffer, async flush)
        - Batch flush: <100ms (K0 Command Port latency)
        - Network reduction: 90%+ (128KB → 12KB)

    Examples:
        >>> config = StateDeltaEmitterConfig(batch_flush_interval_ms=250)
        >>> emitter = StateDeltaEmitter(config, command_client=k0_command_client)
        >>>
        >>> # Track SessionState changes
        >>> old_state = SessionState(session_id='sess_456', beliefs={'user_facts': []})
        >>> new_state = SessionState(session_id='sess_456', beliefs={'user_facts': [{'fact': 'Emma likes soccer'}]})
        >>>
        >>> # Compute deltas
        >>> deltas = await emitter.compute_deltas(old_state, new_state)
        >>> # [StateDelta(field_path='beliefs.user_facts[0]', operation='APPEND', value={...})]
        >>>
        >>> # Emit deltas to K0
        >>> result = await emitter.emit_deltas(deltas)
        >>> print(result.bytes_saved)  # 116KB saved (128KB → 12KB)

    References:
        - ADR-0001a: K0 Bridge Delta-Based Updates
        - ADR-0022: Bounded Batching (250ms flush, 64KB trigger)
        - Research: Operational Transformation (Ellis & Gibbs 1989) - Collaborative editing
    """

    def __init__(
        self,
        config: "StateDeltaEmitterConfig",
        batch_client: BatchClient,
        command_client: Optional[CommandClient] = None,
    ) -> None:
        """
        Initialize StateDeltaEmitter.

        Args:
            config: StateDeltaEmitterConfig with batching, diff settings
            command_client: CommandClient for K0 writes (None = create default)

        Raises:
            ValueError: If configuration is invalid

        Side Effects:
            - Initializes batch buffer (empty)
            - Starts batch flush timer (250ms interval)
            - Does NOT connect to K0 (call initialize())

        ADR: ADR-0001a (State Delta Emitter initialization)
        Assigned to: Issue #L5-1.4.2
        """
        self._validate_config(config)
        if batch_client is None:
            raise ValueError("batch_client is required for StateDeltaEmitter")

        self.config = config
        self._command_client = command_client
        self._batch_client = batch_client
        self._logger = logger
        self._batch_buffer: List[StateDelta] = []
        self._batch_lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()

    async def initialize(self) -> None:
        """
        Initialize delta emitter (start batch flush timer).

        This method starts the background batch flush timer (250ms interval).

        Side Effects:
            - Starts batch flush timer task
            - Logs initialization

        ADR: ADR-0001a (Delta Emitter initialization)
        Assigned to: Issue #L5-1.4.2
        """
        # TODO(@infrastructure-team): Implement initialization (ADR-0001a)
        # 1. Verify command_client initialized
        # 2. Start batch flush timer (250ms interval)
        # 3. Log initialization event
        if self._flush_task is not None:
            raise RuntimeError("StateDeltaEmitter already initialized")

        self._shutdown_event.clear()
        self._flush_task = asyncio.create_task(self._batch_flush_loop())
        self._logger.info(
            "state_delta_emitter_initialized batch_flush_interval_ms=%d batch_size_max_bytes=%d batch_count_max=%d",
            self.config.batch_flush_interval_ms,
            self.config.batch_size_max_bytes,
            self.config.batch_count_max,
        )

    async def compute_deltas(
        self, old_state: Any, new_state: Any  # SessionState  # SessionState
    ) -> List[StateDelta]:
        """
        Compute field-level deltas between old and new SessionState.

        This method performs field-level diff using DeepDiff library, generates
        StateDelta objects for each changed field with field_path notation.

        Args:
            old_state: Previous SessionState
            new_state: New SessionState

        Returns:
            List of StateDelta objects (one per changed field)

        Performance:
            - Target: <1ms P95 (field-level diff)

        ADR: ADR-0001a (State delta computation)
        Assigned to: Issue #L5-1.4.2
        """
        if DeepDiff is None:
            raise DeltaComputeError("DeepDiff dependency missing for delta computation")

        start = time.perf_counter()
        with create_span("k0_bridge.state_delta_emitter.compute_delta") as span:
            diff = DeepDiff(  # type: ignore[operator]
                getattr(old_state, "to_dict", lambda: old_state)(),
                getattr(new_state, "to_dict", lambda: new_state)(),
                max_level=self.config.diff_max_depth,
                verbose_level=2,
            )

            deltas = list(self._deepdiff_to_deltas(diff, new_state))
            span.set_attribute("delta_count", len(deltas))

        latency_ms = (time.perf_counter() - start) * 1000
        emit_histogram(
            "k1_state_delta_emitter_diff_latency_ms",
            latency_ms,
            None,
        )
        emit_counter(
            "k1_state_delta_emitter_deltas_total",
            len(deltas),
            None,
        )
        self._logger.debug(
            "deltas_computed delta_count=%d latency_ms=%.2f",
            len(deltas),
            latency_ms,
        )

        return deltas

    async def emit_deltas(self, deltas: List[StateDelta]) -> DeltaEmitResult:
        """
        Emit state deltas to K0 Command Port.

        This method buffers deltas locally, flushes batch if size/count limit reached,
        otherwise waits for 250ms timer to flush batch to K0.

        Args:
            deltas: List of StateDelta objects to emit

        Returns:
            DeltaEmitResult with deltas_emitted, bytes_saved, batched flag

        Raises:
            TimeoutError: If emit timeout exceeded (5s)

        Performance:
            - Target: <5ms P95 (local buffer, async flush)

        ADR: ADR-0001a (State delta emit)
        Assigned to: Issue #L5-1.4.2
        """
        start = time.perf_counter()
        accepted: List[StateDelta] = []
        for delta in deltas:
            if delta.privacy_band == "BLACK":
                self._logger.warning(
                    "delta_rejected_privacy session_id=%s field_path=%s",
                    delta.session_id,
                    delta.field_path,
                )
                emit_counter(
                    "k1_state_delta_emitter_deltas_rejected_total",
                    1,
                    {"reason": "privacy_band_black"},
                )
                continue
            accepted.append(delta)

        if not accepted:
            emit_histogram(
                "k1_state_delta_emitter_emit_latency_ms",
                (time.perf_counter() - start) * 1000,
                None,
            )
            return DeltaEmitResult(
                deltas_emitted=0,
                bytes_saved=0,
                emit_latency_ms=0.0,
                batched=True,
            )

        async with self._batch_lock:
            self._batch_buffer.extend(accepted)
            batch_size_bytes = self._calculate_batch_size()

            should_flush = (
                batch_size_bytes >= self.config.batch_size_max_bytes
                or len(self._batch_buffer) >= self.config.batch_count_max
            )

            if should_flush:
                result = await self._flush_batch(trigger=FlushTrigger.SIZE)
            else:
                result = DeltaEmitResult(
                    deltas_emitted=len(accepted),
                    bytes_saved=0,
                    emit_latency_ms=0.0,
                    batched=True,
                )

        emit_histogram(
            "k1_state_delta_emitter_emit_latency_ms",
            (time.perf_counter() - start) * 1000,
            None,
        )
        return result

    async def shutdown(self) -> None:
        """
        Graceful shutdown sequence.

        This method flushes pending deltas, cancels batch flush timer, closes K0 connection.

        Lifecycle:
            - Flush pending batch
            - Cancel batch flush timer
            - Close command_client connection

        ADR: ADR-0001a (Delta Emitter shutdown)
        Assigned to: Issue #L5-1.4.2
        """
        # TODO(@infrastructure-team): Implement shutdown (ADR-0001a)
        # 1. Set shutdown event
        # 2. Flush pending batch
        # 3. Cancel batch flush timer
        # 4. Close command_client connection
        # 5. Log shutdown event
        if self._flush_task is None:
            return

        self._shutdown_event.set()

        async with self._batch_lock:
            if self._batch_buffer:
                await self._flush_batch(trigger=FlushTrigger.MANUAL)

        self._flush_task.cancel()
        with suppress(asyncio.CancelledError):
            await self._flush_task

        self._flush_task = None
        self._logger.info("state_delta_emitter_shutdown_complete")

    # =========================================================================
    # PRIVATE METHODS (Implementation Details)
    # =========================================================================

    async def _batch_flush_loop(self) -> None:
        """
        Background batch flush timer (250ms interval).

        This method runs in background, flushes batch every 250ms if non-empty.

        ADR: ADR-0022 (Bounded Batching - 250ms flush interval)
        Assigned to: Issue #L5-1.4.2
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
                await asyncio.sleep(interval)
                async with self._batch_lock:
                    if self._batch_buffer:
                        await self._flush_batch(trigger=FlushTrigger.TIME)
        except asyncio.CancelledError:  # pragma: no cover
            raise

    async def _flush_batch(self, trigger: FlushTrigger) -> DeltaEmitResult:
        """
        Flush batch buffer to K0 Command Port.

        Side Effects:
            - Sends batch to K0 Command Port (P02)
            - Clears batch buffer
            - Emits metrics

        Returns:
            DeltaEmitResult with deltas_emitted, bytes_saved

        ADR: ADR-0001a (Delta batch flush)
        Assigned to: Issue #L5-1.4.2
        """
        start_time = time.perf_counter()
        deltas = list(self._batch_buffer)
        self._batch_buffer.clear()
        batch_size_bytes = self._calculate_batch_size_from_deltas(deltas)

        full_state_size_estimate = 128 * 1024  # 128KB baseline
        bytes_saved = max(full_state_size_estimate - batch_size_bytes, 0)

        receipt = await self._emit_to_batch_client(deltas, trigger)

        latency_ms = (time.perf_counter() - start_time) * 1000
        emit_histogram(
            "k1_state_delta_emitter_batch_flush_duration_seconds",
            latency_ms / 1000.0,
            {"trigger": trigger.value},
        )
        emit_counter(
            "k1_state_delta_emitter_bytes_saved_total",
            bytes_saved,
            None,
        )
        self._logger.info(
            "delta_batch_flushed delta_count=%d bytes_saved=%d trigger=%s receipt_status=%s",
            len(deltas),
            bytes_saved,
            trigger.value,
            receipt.status if receipt else "pending",
        )

        return DeltaEmitResult(
            deltas_emitted=len(deltas),
            bytes_saved=bytes_saved,
            emit_latency_ms=latency_ms,
            batched=False,
        )

    def _calculate_batch_size(self) -> int:
        return self._calculate_batch_size_from_deltas(self._batch_buffer)

    def _calculate_batch_size_from_deltas(self, deltas: Iterable[StateDelta]) -> int:
        return sum(len(delta.field_path) + len(str(delta.value)) for delta in deltas)

    async def _emit_to_batch_client(
        self,
        deltas: List[StateDelta],
        trigger: FlushTrigger,
    ) -> Optional[Any]:
        receipts = []
        for delta in deltas:
            if delta.privacy_band == "BLACK":
                self._logger.warning(
                    "delta_rejected_privacy session_id=%s field_path=%s",
                    delta.session_id,
                    delta.field_path,
                )
                emit_counter(
                    "k1_state_delta_emitter_deltas_rejected_total",
                    1,
                    {"reason": "privacy_band_black"},
                )
                continue

            session_delta = SessionStateDelta(
                session_id=delta.session_id,
                field_path=delta.field_path,
                value=delta.value,
                timestamp=delta.timestamp or time.time() * 1000,
                privacy_band=delta.privacy_band,
            )
            receipt = await self._batch_client.add_delta(
                session_delta,
                cognitive_trace_id=delta.cognitive_trace_id,
            )
            if receipt:
                receipts.append(receipt)

        if receipts:
            return receipts[-1]

        if trigger != FlushTrigger.MANUAL:
            return None

        return await self._batch_client.flush(trigger=trigger)

    def _deepdiff_to_deltas(self, diff: Any, new_state: Any) -> Iterable[StateDelta]:
        # Placeholder conversion: only handle values_changed entries
        if not diff:
            return []

        deltas: List[StateDelta] = []
        values_changed = diff.get("values_changed", {})
        for path, change in values_changed.items():
            session_id = getattr(new_state, "session_id", "unknown_session")
            field_path = path.replace("root", "", 1).strip(".")
            deltas.append(
                StateDelta(
                    session_id=session_id,
                    section=SessionSection.META,
                    field_path=field_path,
                    operation=DeltaOperation.SET,
                    value=change.get("new_value"),
                    old_value=change.get("old_value"),
                    timestamp=int(time.time() * 1000),
                    cognitive_trace_id=getattr(new_state, "cognitive_trace_id", None),
                    privacy_band=getattr(new_state, "privacy_band", "GREEN"),
                )
            )

        return deltas

    def _validate_config(self, config: "StateDeltaEmitterConfig") -> None:
        if config.batch_flush_interval_ms <= 0:
            raise ValueError("batch_flush_interval_ms must be positive")
        if config.batch_size_max_bytes <= 0:
            raise ValueError("batch_size_max_bytes must be positive")
        if config.batch_count_max <= 0:
            raise ValueError("batch_count_max must be positive")


@dataclass
class StateDeltaEmitterConfig:
    """
    State Delta Emitter configuration.

    Fields:
        batch_flush_interval_ms: Batch flush interval (default: 250ms, aligned with ADR-0022)
        batch_size_max_bytes: Max batch size for flush trigger (default: 64KB)
        batch_count_max: Max deltas per batch (default: 100)
        diff_max_depth: Max diff depth for nested objects (default: 10)
        compression_threshold_bytes: Compression threshold (default: 4KB)
    """

    batch_flush_interval_ms: int = DEFAULT_CONFIG["batch_flush_interval_ms"]
    batch_size_max_bytes: int = DEFAULT_CONFIG["batch_size_max_bytes"]
    batch_count_max: int = DEFAULT_CONFIG["batch_count_max"]
    diff_max_depth: int = DEFAULT_CONFIG["diff_max_depth"]
    compression_threshold_bytes: int = DEFAULT_CONFIG["compression_threshold_bytes"]


# =============================================================================
# SECTION 5: HELPER FUNCTIONS & EXCEPTIONS
# =============================================================================


class DeltaComputeError(Exception):
    """Raised when delta computation fails"""

    pass


class DeltaEmitError(Exception):
    """Raised when delta emit fails"""

    pass


def create_state_delta_emitter(
    config: Optional[StateDeltaEmitterConfig] = None,
    batch_client: Optional[BatchClient] = None,
    command_client: Optional[CommandClient] = None,
) -> StateDeltaEmitter:
    """
    Create StateDeltaEmitter with default or provided configuration.

    Args:
        config: StateDeltaEmitterConfig (default: 250ms batching, 64KB trigger)
        command_client: CommandClient for K0 writes

    Returns:
        StateDeltaEmitter instance

    ADR: ADR-0001a (State Delta Emitter factory)
    Assigned to: Issue #L5-1.4.2
    """
    if config is None:
        config = StateDeltaEmitterConfig()

    if batch_client is None:
        raise ValueError("batch_client is required")

    return StateDeltaEmitter(config, batch_client=batch_client, command_client=command_client)


# =============================================================================
# SECTION 6: MODULE EXPORTS & INITIALIZATION
# =============================================================================

__all__ = [
    "StateDeltaEmitter",
    "StateDeltaEmitterConfig",
    "StateDelta",
    "DeltaEmitResult",
    "DeltaOperation",
    "SessionSection",
    "DeltaComputeError",
    "DeltaEmitError",
    "create_state_delta_emitter",
]


# =============================================================================
# OBSERVABILITY INTEGRATION
# =============================================================================
# Metrics to export (Prometheus):
#   - k1_state_delta_emitter_deltas_total{counter, labels: section}
#   - k1_state_delta_emitter_bytes_saved_total{counter}
#   - k1_state_delta_emitter_batch_flush_duration_seconds{histogram}
#
# Traces to generate (OpenTelemetry):
#   - Span name: k0_bridge.state_delta_emitter.compute_delta
#   - Span name: k0_bridge.state_delta_emitter.emit
#   - Attributes: session_id, section, delta_count, bytes_saved
#
# Logs to emit (structured logging):
#   - Level: DEBUG (delta_computed, delta_emitted)
#   - Level: INFO (delta_batch_flushed)
#   - Fields: component='state_delta_emitter', session_id, section, delta_count, bytes_saved
#
# =============================================================================

# =============================================================================
# TESTING REQUIREMENTS (WARD Framework)
# =============================================================================
# Integration tests required:
#   - tests/k1/bridge_k0/test_state_delta_emitter.py
#   - Test delta computation (field-level diff, field_path generation)
#   - Test delta emit (buffer → batch → flush → K0 receipt)
#   - Test batch flush (250ms timer, 64KB size trigger, 100 count trigger)
#   - Test network savings (128KB full state → 12KB delta batch = 90% reduction)
#
# No simulation code allowed:
#   - Use real SessionState objects with real field changes
#   - Use real K0 Command Port mock
#   - Test with real batching (250ms timer, 64KB/100 delta limits)
#   - Integration tests > unit tests
#
# Performance budget tests:
#   - Assert delta compute <1ms P95 (field-level diff)
#   - Assert delta emit <5ms P95 (local buffer)
#   - Assert batch flush <100ms P95 (K0 Command Port)
#   - Assert network reduction ≥90% (128KB → ≤12KB)
#
# =============================================================================
