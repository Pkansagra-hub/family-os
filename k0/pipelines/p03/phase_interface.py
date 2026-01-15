"""
P03 Phase Interface — Issue 1.2.2

Defines the uniform interface for all R0-R8 phases:
- P03PhaseResult: Outcome of phase execution
- P03Phase: Protocol/ABC for phase implementations
- P03RunnerContext: Context passed to phases during execution

References:
- Spec: docs/pipelines/P03_consolidation_dossier_v2.md Appendix G.2
- Issue: docs/TEMP_EXECUTION_DOCS/M1_EXECUTION.md Issue 1.2.2
- Runner Contract: k0/pipelines/p03/runner_contract.py (Issue 1.2.1)
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional, Protocol, Tuple, runtime_checkable

from k0.pipelines.p03.observability import P03Error
from k0.pipelines.p03.runner_contract import P03PhaseId, P03PhaseStatus

if TYPE_CHECKING:
    from k0.pipelines.p03.envelope import P03BatchEnvelope


# =============================================================================
# PHASE RESULT (Output of phase execution)
# =============================================================================


@dataclass
class P03PhaseResult:
    """
    Result of executing a single phase.

    Captures the outcome (status), timing, outputs summary, and error details.
    This is returned by P03Phase.run() and consumed by the sequential runner.

    Attributes:
        phase_id: Which phase was executed
        status: Outcome status (DONE, SKIP, FAIL)
        duration_ms: Execution time in milliseconds
        outputs_summary: Phase-specific output summary for logging/metrics
        error_info: Error details if status is FAIL
        skip_reason: Explanation if status is SKIP
        retry_count: Number of retries attempted (0 = first attempt)
        idempotency_key: Key used for exactly-once semantics
    """

    phase_id: P03PhaseId
    status: P03PhaseStatus
    duration_ms: int = 0
    outputs_summary: Dict[str, Any] = field(default_factory=dict)
    error_info: Optional[P03Error] = None
    skip_reason: Optional[str] = None
    retry_count: int = 0
    idempotency_key: Optional[str] = None

    @classmethod
    def done(
        cls,
        phase_id: P03PhaseId,
        duration_ms: int,
        outputs_summary: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> "P03PhaseResult":
        """Factory for successful phase completion."""
        return cls(
            phase_id=phase_id,
            status=P03PhaseStatus.DONE,
            duration_ms=duration_ms,
            outputs_summary=outputs_summary or {},
            idempotency_key=idempotency_key,
        )

    @classmethod
    def skip(
        cls,
        phase_id: P03PhaseId,
        reason: str,
        duration_ms: int = 0,
        idempotency_key: Optional[str] = None,
    ) -> "P03PhaseResult":
        """Factory for skipped phase."""
        return cls(
            phase_id=phase_id,
            status=P03PhaseStatus.SKIP,
            duration_ms=duration_ms,
            skip_reason=reason,
            idempotency_key=idempotency_key,
        )

    @classmethod
    def fail(
        cls,
        phase_id: P03PhaseId,
        error: P03Error,
        duration_ms: int = 0,
        retry_count: int = 0,
        idempotency_key: Optional[str] = None,
    ) -> "P03PhaseResult":
        """Factory for failed phase."""
        return cls(
            phase_id=phase_id,
            status=P03PhaseStatus.FAIL,
            duration_ms=duration_ms,
            error_info=error,
            retry_count=retry_count,
            idempotency_key=idempotency_key,
        )

    @property
    def is_success(self) -> bool:
        """True if phase completed successfully."""
        return self.status == P03PhaseStatus.DONE

    @property
    def is_skipped(self) -> bool:
        """True if phase was skipped."""
        return self.status == P03PhaseStatus.SKIP

    @property
    def is_failed(self) -> bool:
        """True if phase failed."""
        return self.status == P03PhaseStatus.FAIL

    @property
    def is_terminal(self) -> bool:
        """True if phase completed or was skipped (can proceed to next)."""
        return self.status in (P03PhaseStatus.DONE, P03PhaseStatus.SKIP)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/metrics."""
        result = {
            "phase_id": self.phase_id.value,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
        }
        if self.outputs_summary:
            result["outputs_summary"] = self.outputs_summary
        if self.error_info:
            result["error"] = {
                "error_type": self.error_info.error_type,
                "message": self.error_info.error_message,
                "recoverable": self.error_info.recoverable,
            }
        if self.skip_reason:
            result["skip_reason"] = self.skip_reason
        if self.retry_count > 0:
            result["retry_count"] = self.retry_count
        if self.idempotency_key:
            result["idempotency_key"] = self.idempotency_key
        return result


# =============================================================================
# RUNNER CONTEXT (Dependencies passed to phases)
# =============================================================================


@dataclass
class P03RunnerContext:
    """
    Context passed to phases during execution.

    Contains all dependencies needed for phase execution:
    - syscalls: K0 syscall interface for storage, events, etc.
    - fabric: Agent fabric reference for async coordination
    - logger: Structured logger for observability
    - qos_context: QoS band, priority, deadline information
    - config: Pipeline configuration

    The context is created by P03SequentialRunner and passed to each phase.
    It remains constant across all phases in a single cycle execution.

    Attributes:
        syscalls: K0 syscall interface (storage, events, embeddings)
        fabric: Agent fabric reference (optional, for async coordination)
        logger: Structured logger with pre-bound context
        qos_band: QoS band ("GREEN", "AMBER", "RED")
        priority: Batch priority (0-100)
        deadline_ms: Hard deadline for cycle completion (unix ms)
        config: Pipeline configuration dictionary
        dry_run: If True, skip actual writes (for testing)
        checkpoint_enabled: If True, persist checkpoints at phase boundaries
        metrics_registry: P03MetricsRegistry for observability (Issue 6.1.1)
    """

    syscalls: Any  # K0 syscall interface (typed as Any to avoid circular imports)
    logger: Any  # Structured logger
    qos_band: str = "GREEN"
    priority: int = 50
    deadline_ms: Optional[int] = None
    config: Dict[str, Any] = field(default_factory=dict)
    fabric: Optional[Any] = None
    dry_run: bool = False
    checkpoint_enabled: bool = True
    metrics_registry: Optional[Any] = None  # P03MetricsRegistry (Issue 6.1.1)

    @classmethod
    def create(
        cls,
        syscalls: Any,
        logger: Any,
        *,
        qos_band: str = "GREEN",
        priority: int = 50,
        deadline_ms: Optional[int] = None,
        config: Optional[Dict[str, Any]] = None,
        fabric: Optional[Any] = None,
        dry_run: bool = False,
        checkpoint_enabled: bool = True,
    ) -> "P03RunnerContext":
        """Factory method for creating runner context."""
        return cls(
            syscalls=syscalls,
            logger=logger,
            qos_band=qos_band,
            priority=priority,
            deadline_ms=deadline_ms,
            config=config or {},
            fabric=fabric,
            dry_run=dry_run,
            checkpoint_enabled=checkpoint_enabled,
        )

    @property
    def is_deadline_exceeded(self) -> bool:
        """Check if the deadline has passed."""
        if self.deadline_ms is None:
            return False
        return int(time.time() * 1000) > self.deadline_ms

    @property
    def remaining_deadline_ms(self) -> Optional[int]:
        """Get remaining time until deadline in milliseconds."""
        if self.deadline_ms is None:
            return None
        remaining = self.deadline_ms - int(time.time() * 1000)
        return max(0, remaining)

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value with default."""
        return self.config.get(key, default)

    def is_backlogged(self, pending_count: int) -> bool:
        """
        Check if system is backlogged based on pending count.

        Used by R5 skip logic: skip_on_backlog AND pending > backlog_threshold

        Args:
            pending_count: Number of pending events in queue

        Returns:
            True if pending exceeds backlog threshold
        """
        threshold = self.get_config("backlog_threshold", 1000)
        skip_on_backlog = self.get_config("r5_skip_on_backlog", True)
        return skip_on_backlog and pending_count > threshold


# =============================================================================
# PHASE PROTOCOL (Interface for phase implementations)
# =============================================================================


@runtime_checkable
class P03PhaseProtocol(Protocol):
    """
    Protocol defining the interface for P03 phase implementations.

    All phases must implement:
    - phase_id: Property returning which phase this is
    - run: Async method executing the phase logic
    - should_skip: Method checking if phase should be skipped
    - idempotency_key: Method computing deterministic retry key

    Example implementation:

        class R1ScorePhase:
            @property
            def phase_id(self) -> P03PhaseId:
                return P03PhaseId.R1_SCORE

            async def run(
                self,
                envelope: P03BatchEnvelope,
                ctx: P03RunnerContext,
            ) -> P03PhaseResult:
                # Phase logic here
                return P03PhaseResult.done(self.phase_id, duration_ms=42)

            def should_skip(
                self,
                envelope: P03BatchEnvelope,
                ctx: P03RunnerContext,
            ) -> Tuple[bool, str]:
                return (False, "")

            def idempotency_key(self, envelope: P03BatchEnvelope) -> str:
                return f"p03:r1:{envelope.context.cycle_id}:{envelope.context.batch_id}"
    """

    @property
    def phase_id(self) -> P03PhaseId:
        """Return the phase identifier."""
        ...

    async def run(
        self,
        envelope: "P03BatchEnvelope",
        ctx: P03RunnerContext,
    ) -> P03PhaseResult:
        """
        Execute the phase logic.

        Args:
            envelope: The batch envelope with context, events, and phase outputs
            ctx: Runner context with syscalls, logger, config

        Returns:
            P03PhaseResult indicating success, skip, or failure
        """
        ...

    def should_skip(
        self,
        envelope: "P03BatchEnvelope",
        ctx: P03RunnerContext,
    ) -> Tuple[bool, str]:
        """
        Check if this phase should be skipped.

        Called by runner BEFORE run(). If returns (True, reason),
        the phase is skipped and runner proceeds to skip target.

        Args:
            envelope: The batch envelope
            ctx: Runner context

        Returns:
            Tuple of (should_skip, reason). If should_skip is True,
            reason must be non-empty.
        """
        ...

    def idempotency_key(self, envelope: "P03BatchEnvelope") -> str:
        """
        Compute deterministic idempotency key for this phase.

        Used for exactly-once semantics. Same envelope should always
        produce the same key. Format varies by phase:

        - R0: p03:cycle:{cycle_id}
        - R1-R5: p03:{phase}:{cycle_id}:{batch_hash}
        - R6: p03:r6:{cycle_id}:{event_id}
        - R7: p03:r7:{cycle_id}:{table}:{record_id}
        - R8: p03:r8:{cycle_id}:{topic}:{offset}

        Args:
            envelope: The batch envelope

        Returns:
            Deterministic string key
        """
        ...


# =============================================================================
# PHASE BASE CLASS (Abstract implementation)
# =============================================================================


class P03PhaseBase(ABC):
    """
    Abstract base class for P03 phase implementations.

    Provides common functionality and enforces the P03Phase interface.
    Phases can extend this class for convenience.

    Usage:
        class R1ScorePhase(P03PhaseBase):
            @property
            def phase_id(self) -> P03PhaseId:
                return P03PhaseId.R1_SCORE

            async def _execute(
                self,
                envelope: P03BatchEnvelope,
                ctx: P03RunnerContext,
            ) -> Dict[str, Any]:
                # Phase logic here
                return {"scored_events": 5, "total_importance": 4.2}
    """

    @property
    @abstractmethod
    def phase_id(self) -> P03PhaseId:
        """Return the phase identifier."""
        raise NotImplementedError

    @abstractmethod
    async def _execute(
        self,
        envelope: "P03BatchEnvelope",
        ctx: P03RunnerContext,
    ) -> Dict[str, Any]:
        """
        Internal phase execution logic.

        Override this method to implement phase-specific logic.
        Returns outputs_summary dict for the result.

        Args:
            envelope: The batch envelope
            ctx: Runner context

        Returns:
            Dict with phase-specific output summary

        Raises:
            Exception: On phase failure (will be caught and wrapped)
        """
        raise NotImplementedError

    async def run(
        self,
        envelope: "P03BatchEnvelope",
        ctx: P03RunnerContext,
    ) -> P03PhaseResult:
        """
        Execute the phase with timing and error handling.

        Wraps _execute() with:
        - Skip check
        - Timing measurement
        - Error handling and wrapping

        Args:
            envelope: The batch envelope
            ctx: Runner context

        Returns:
            P03PhaseResult with status, duration, outputs
        """
        start_ms = int(time.time() * 1000)
        idem_key = self.idempotency_key(envelope)

        # Check skip condition first
        should_skip, skip_reason = self.should_skip(envelope, ctx)
        if should_skip:
            duration_ms = int(time.time() * 1000) - start_ms
            return P03PhaseResult.skip(
                phase_id=self.phase_id,
                reason=skip_reason,
                duration_ms=duration_ms,
                idempotency_key=idem_key,
            )

        try:
            outputs_summary = await self._execute(envelope, ctx)
            duration_ms = int(time.time() * 1000) - start_ms
            return P03PhaseResult.done(
                phase_id=self.phase_id,
                duration_ms=duration_ms,
                outputs_summary=outputs_summary,
                idempotency_key=idem_key,
            )
        except Exception as e:
            duration_ms = int(time.time() * 1000) - start_ms
            error = P03Error.from_exception(
                phase=self.phase_id.value,
                stage_id=self.__class__.__name__,
                exc=e,
                recoverable=self._is_recoverable_error(e),
            )
            return P03PhaseResult.fail(
                phase_id=self.phase_id,
                error=error,
                duration_ms=duration_ms,
                idempotency_key=idem_key,
            )

    def should_skip(
        self,
        envelope: "P03BatchEnvelope",
        ctx: P03RunnerContext,
    ) -> Tuple[bool, str]:
        """
        Default skip check - never skip.

        Override in phases that support skipping (R2, R5).

        Args:
            envelope: The batch envelope
            ctx: Runner context

        Returns:
            (False, "") by default
        """
        return (False, "")

    def idempotency_key(self, envelope: "P03BatchEnvelope") -> str:
        """
        Default idempotency key format.

        Format: p03:{phase}:{cycle_id}:{batch_id}

        Override for phases with different key formats (R6, R7, R8).

        Args:
            envelope: The batch envelope

        Returns:
            Deterministic string key
        """
        return (
            f"p03:{self.phase_id.value.lower()}:"
            f"{envelope.context.cycle_id}:{envelope.context.batch_id}"
        )

    def _is_recoverable_error(self, error: Exception) -> bool:
        """
        Determine if an error is recoverable (can retry).

        Override to customize error classification.

        Args:
            error: The exception that occurred

        Returns:
            True if error is recoverable via retry
        """
        # By default, timeout and connection errors are recoverable
        error_type = type(error).__name__
        recoverable_types = {
            "TimeoutError",
            "ConnectionError",
            "ConnectionRefusedError",
            "ConnectionResetError",
            "OperationalError",  # DB connection issues
        }
        return error_type in recoverable_types


# =============================================================================
# CYCLE RESULT (Output of full cycle execution)
# =============================================================================


@dataclass
class P03CycleResult:
    """
    Result of executing a full P03 consolidation cycle.

    Captures the overall outcome and per-phase results.

    Attributes:
        cycle_id: ULID of the cycle
        batch_id: Batch identifier
        status: Final cycle status (DONE, FAIL)
        phase_results: Results for each executed phase
        total_duration_ms: Total execution time
        final_phase: Last phase that completed or failed
        dlq_reason: If cycle sent to DLQ, the reason
    """

    cycle_id: str
    batch_id: str
    status: P03PhaseStatus
    phase_results: Dict[P03PhaseId, P03PhaseResult] = field(default_factory=dict)
    total_duration_ms: int = 0
    final_phase: Optional[P03PhaseId] = None
    dlq_reason: Optional[str] = None

    @classmethod
    def success(
        cls,
        cycle_id: str,
        batch_id: str,
        phase_results: Dict[P03PhaseId, P03PhaseResult],
        total_duration_ms: int,
    ) -> "P03CycleResult":
        """Factory for successful cycle completion."""
        return cls(
            cycle_id=cycle_id,
            batch_id=batch_id,
            status=P03PhaseStatus.DONE,
            phase_results=phase_results,
            total_duration_ms=total_duration_ms,
            final_phase=P03PhaseId.R8_EMIT,
        )

    @classmethod
    def fail(
        cls,
        cycle_id: str,
        batch_id: str,
        phase_results: Dict[P03PhaseId, P03PhaseResult],
        total_duration_ms: int,
        failed_phase: P03PhaseId,
        dlq_reason: Optional[str] = None,
    ) -> "P03CycleResult":
        """Factory for failed cycle."""
        return cls(
            cycle_id=cycle_id,
            batch_id=batch_id,
            status=P03PhaseStatus.FAIL,
            phase_results=phase_results,
            total_duration_ms=total_duration_ms,
            final_phase=failed_phase,
            dlq_reason=dlq_reason,
        )

    @property
    def is_success(self) -> bool:
        """True if cycle completed successfully."""
        return self.status == P03PhaseStatus.DONE

    @property
    def is_failed(self) -> bool:
        """True if cycle failed."""
        return self.status == P03PhaseStatus.FAIL

    @property
    def phases_executed(self) -> int:
        """Number of phases that were executed (not skipped)."""
        return sum(1 for r in self.phase_results.values() if r.status != P03PhaseStatus.SKIP)

    @property
    def phases_skipped(self) -> int:
        """Number of phases that were skipped."""
        return sum(1 for r in self.phase_results.values() if r.status == P03PhaseStatus.SKIP)

    def get_phase_result(self, phase_id: P03PhaseId) -> Optional[P03PhaseResult]:
        """Get result for a specific phase."""
        return self.phase_results.get(phase_id)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/metrics."""
        return {
            "cycle_id": self.cycle_id,
            "batch_id": self.batch_id,
            "status": self.status.value,
            "total_duration_ms": self.total_duration_ms,
            "final_phase": self.final_phase.value if self.final_phase else None,
            "phases_executed": self.phases_executed,
            "phases_skipped": self.phases_skipped,
            "dlq_reason": self.dlq_reason,
            "phase_results": {p.value: r.to_dict() for p, r in self.phase_results.items()},
        }

    def to_summary_dict(self) -> Dict[str, Any]:
        """Convert to compact summary for logging."""
        return {
            "cycle_id": self.cycle_id,
            "status": self.status.value,
            "total_duration_ms": self.total_duration_ms,
            "phases_executed": self.phases_executed,
            "phases_skipped": self.phases_skipped,
            "dlq_reason": self.dlq_reason,
        }
