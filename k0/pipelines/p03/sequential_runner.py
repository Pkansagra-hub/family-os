"""
P03 Sequential Runner — Issue 1.2.3, 1.2.4

Engine that runs phases strictly in order, applies transitions/skip rules,
records per-phase results, and supports resume from checkpoint.

Issue 1.2.4 adds structured log emission and observability integration.

References:
- Spec: docs/pipelines/P03_consolidation_dossier_v2.md §4.0, Appendix G.3
- Issue: docs/TEMP_EXECUTION_DOCS/M1_EXECUTION.md Issue 1.2.3, 1.2.4
- Runner Contract: k0/pipelines/p03/runner_contract.py (Issue 1.2.1)
- Phase Interface: k0/pipelines/p03/phase_interface.py (Issue 1.2.2)
- Observability: k0/pipelines/p03/observability.py (Issue 1.1.6, 1.2.4)

Key Constraint: Strict R0→R8 sequential execution (NOT parallel DAG).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

from k0.pipelines.p03.observability import PhaseTransitionLogger, PhaseTransitionLoggerProtocol
from k0.pipelines.p03.ops import P03MetricsRegistry
from k0.pipelines.p03.phase_interface import (
    P03CycleResult,
    P03PhaseProtocol,
    P03PhaseResult,
    P03RunnerContext,
)
from k0.pipelines.p03.runner_contract import (
    PHASE_CONTRACTS,
    R6_DLQ_CONFLICT_THRESHOLD,
    R6_RETRY_CONFIGS,
    RESUME_MATRIX,
    SKIP_TRANSITIONS,
    P03ErrorType,
    P03PhaseId,
    P03PhaseStatus,
    classify_r6_error,
    is_valid_transition,
)

if TYPE_CHECKING:
    from k0.pipelines.p03.envelope import P03BatchEnvelope

logger = logging.getLogger(__name__)


# =============================================================================
# RUNNER ERRORS
# =============================================================================


class P03RunnerError(Exception):
    """Base error for P03 runner issues."""

    pass


class InvalidPhaseTransitionError(P03RunnerError):
    """Raised when attempting an illegal phase transition."""

    def __init__(self, from_phase: P03PhaseId, to_phase: P03PhaseId):
        self.from_phase = from_phase
        self.to_phase = to_phase
        super().__init__(f"Invalid transition: {from_phase.value} -> {to_phase.value}")


class PhaseNotRegisteredError(P03RunnerError):
    """Raised when trying to run a phase that has no registered implementation."""

    def __init__(self, phase_id: P03PhaseId):
        self.phase_id = phase_id
        super().__init__(f"No phase implementation registered for {phase_id.value}")


class ResumeNotAllowedError(P03RunnerError):
    """Raised when trying to resume from an invalid phase."""

    def __init__(self, phase_id: P03PhaseId, reason: str):
        self.phase_id = phase_id
        self.reason = reason
        super().__init__(f"Cannot resume from {phase_id.value}: {reason}")


# =============================================================================
# PHASE TIMELINE ENTRY
# =============================================================================


@dataclass
class PhaseTimelineEntry:
    """
    Timeline entry for a single phase execution.

    Used for metrics emission and debugging.
    """

    phase_id: P03PhaseId
    status: P03PhaseStatus
    start_ts: int  # Unix timestamp (ms)
    end_ts: int  # Unix timestamp (ms)
    duration_ms: int
    skip_reason: Optional[str] = None
    error_type: Optional[str] = None
    retry_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        result = {
            "phase_id": self.phase_id.value,
            "status": self.status.value,
            "start_ts": self.start_ts,
            "end_ts": self.end_ts,
            "duration_ms": self.duration_ms,
        }
        if self.skip_reason:
            result["skip_reason"] = self.skip_reason
        if self.error_type:
            result["error_type"] = self.error_type
        if self.retry_count > 0:
            result["retry_count"] = self.retry_count
        return result


# =============================================================================
# SEQUENTIAL RUNNER
# =============================================================================


class P03SequentialRunner:
    """
    Sequential runner for P03 consolidation pipeline.

    Executes phases strictly in order (R0→R8) with:
    - Skip condition evaluation
    - Transition validation
    - Phase result recording
    - Checkpoint creation (via hooks)
    - Resume from checkpoint support

    Usage:
        runner = P03SequentialRunner(
            phases={
                P03PhaseId.R0_INIT: R0InitPhase(),
                P03PhaseId.R1_SCORE: R1ScorePhase(),
                # ...
            }
        )
        result = await runner.run(envelope, ctx)

    Note: Does NOT reuse generic DAG runner - P03 requires strict sequential
    execution with specific skip transitions.
    """

    def __init__(
        self,
        phases: Dict[P03PhaseId, P03PhaseProtocol],
        *,
        on_phase_start: Optional[Callable[..., Any]] = None,
        on_phase_complete: Optional[Callable[..., Any]] = None,
        on_checkpoint: Optional[Callable[..., Any]] = None,
        transition_logger: Optional[PhaseTransitionLoggerProtocol] = None,
    ):
        """
        Initialize the sequential runner.

        Args:
            phases: Mapping of phase ID to phase implementation
            on_phase_start: Optional callback(envelope, phase_id, ctx) before phase
            on_phase_complete: Optional callback(envelope, phase_id, result, ctx) after phase
            on_checkpoint: Optional callback(envelope, phase_id, checkpoint_data) for persistence
            transition_logger: Optional logger for structured phase transition events (Issue 1.2.4)
        """
        self._phases = phases
        self._on_phase_start = on_phase_start
        self._on_phase_complete = on_phase_complete
        self._on_checkpoint = on_checkpoint
        self._transition_logger = transition_logger or PhaseTransitionLogger()
        self._timeline: List[PhaseTimelineEntry] = []

    @property
    def transition_logger(self) -> PhaseTransitionLoggerProtocol:
        """Get the transition logger for external access to events."""
        return self._transition_logger

    @property
    def registered_phases(self) -> List[P03PhaseId]:
        """Return list of registered phase IDs."""
        return list(self._phases.keys())

    def has_phase(self, phase_id: P03PhaseId) -> bool:
        """Check if a phase implementation is registered."""
        return phase_id in self._phases

    def get_timeline(self) -> List[PhaseTimelineEntry]:
        """Return phase execution timeline (for metrics)."""
        return self._timeline.copy()

    def clear_timeline(self) -> None:
        """Clear the phase timeline."""
        self._timeline.clear()

    # =========================================================================
    # MAIN EXECUTION
    # =========================================================================

    async def run(
        self,
        envelope: "P03BatchEnvelope",
        ctx: P03RunnerContext,
    ) -> P03CycleResult:
        """
        Execute full cycle from R0 to R8.

        Args:
            envelope: P03BatchEnvelope to process
            ctx: Runner context with syscalls, logger, config

        Returns:
            P03CycleResult with per-phase results and overall status
        """
        return await self.run_from(envelope, ctx, start_phase=P03PhaseId.R0_INIT)

    async def run_from(
        self,
        envelope: "P03BatchEnvelope",
        ctx: P03RunnerContext,
        start_phase: P03PhaseId,
    ) -> P03CycleResult:
        """
        Execute cycle starting from a specific phase.

        Used for:
        - Normal execution (start_phase=R0)
        - Resume from checkpoint (start_phase=checkpoint phase)

        Args:
            envelope: P03BatchEnvelope to process
            ctx: Runner context
            start_phase: Phase to start execution from

        Returns:
            P03CycleResult with per-phase results

        Raises:
            ResumeNotAllowedError: If start_phase is not resumable
            PhaseNotRegisteredError: If a required phase is not registered
        """
        # Validate resume is allowed from this phase
        self._validate_resume(start_phase, envelope)

        # Clear timeline for fresh run
        self.clear_timeline()

        # Issue 6.1.3: Inject metrics registry into observability context
        if ctx.metrics_registry and envelope.observability:
            envelope.observability.metrics_registry = ctx.metrics_registry
            envelope.observability.tenant_id = envelope.context.tenant_id

        cycle_start_ms = int(time.time() * 1000)
        phase_results: Dict[P03PhaseId, P03PhaseResult] = {}
        final_phase: Optional[P03PhaseId] = None
        dlq_reason: Optional[str] = None

        # Get execution order starting from start_phase
        execution_order = P03PhaseId.execution_order()
        start_index = execution_order.index(start_phase)

        # Use index-based iteration to support skip jumps
        current_index = start_index

        logger.info(
            "P03 Runner: Starting execution loop",
            extra={
                "cycle_id": envelope.context.cycle_id,
                "start_phase": start_phase.value,
                "start_index": start_index,
                "total_phases": len(execution_order),
                "registered_phases": [p.value for p in self._phases.keys()],
            },
        )

        while current_index < len(execution_order):
            phase_id = execution_order[current_index]

            logger.debug(
                f"P03 Runner: Loop iteration - phase {phase_id.value}",
                extra={
                    "cycle_id": envelope.context.cycle_id,
                    "current_index": current_index,
                    "phase_id": phase_id.value,
                },
            )

            # Check deadline before starting phase
            if ctx.is_deadline_exceeded:
                dlq_reason = f"Deadline exceeded before {phase_id.value}"
                break

            # Check if this phase was already skipped (due to skip transition)
            if phase_id in phase_results and phase_results[phase_id].is_skipped:
                current_index += 1
                continue

            # Get phase implementation
            if not self.has_phase(phase_id):
                raise PhaseNotRegisteredError(phase_id)

            phase = self._phases[phase_id]

            # Use R6-specific retry logic for R6_STAGE phase (Issue 5.2.W6)
            if phase_id == P03PhaseId.R6_STAGE:
                result = await self._execute_r6_with_retry(envelope, ctx, phase)
            else:
                result = await self._execute_phase(envelope, ctx, phase, phase_id)

            phase_results[phase_id] = result

            # Log phase result for debugging
            logger.info(
                f"P03 Runner: Phase {phase_id.value} completed with status {result.status.value}",
                extra={
                    "cycle_id": envelope.context.cycle_id,
                    "phase_id": phase_id.value,
                    "status": result.status.value,
                    "is_success": result.is_success,
                    "is_failed": result.is_failed,
                    "is_skipped": result.is_skipped,
                    "duration_ms": result.duration_ms,
                    "error_type": result.error_info.error_type if result.error_info else None,
                },
            )

            # Record timeline entry
            self._record_timeline_entry(phase_id, result)

            if result.is_failed:
                # Phase failed - check if we should DLQ
                final_phase = phase_id
                contract = PHASE_CONTRACTS.get(phase_id)
                if contract and result.retry_count >= contract.max_retries:
                    dlq_reason = f"{phase_id.value} failed after {result.retry_count} retries"
                else:
                    dlq_reason = f"{phase_id.value} failed: {result.error_info.error_type if result.error_info else 'unknown'}"
                logger.warning(
                    f"P03 Runner: Breaking loop due to phase failure - {dlq_reason}",
                    extra={
                        "cycle_id": envelope.context.cycle_id,
                        "failed_phase": phase_id.value,
                        "dlq_reason": dlq_reason,
                    },
                )
                break

            if result.is_skipped:
                # Phase was skipped - determine next phase from skip transitions
                next_phase = self._get_skip_target(phase_id)
                if next_phase:
                    # Skip to target phase (e.g., R2→R6)
                    skip_to_index = execution_order.index(next_phase)
                    # Mark intermediate phases as skipped and emit skip events
                    for i in range(current_index + 1, skip_to_index):
                        skipped_phase = execution_order[i]
                        skip_reason = f"Skipped due to {phase_id.value} skip transition"
                        skip_result = P03PhaseResult.skip(
                            phase_id=skipped_phase,
                            reason=skip_reason,
                            duration_ms=0,
                        )
                        phase_results[skipped_phase] = skip_result
                        envelope.mark_phase_skipped(skipped_phase, skip_reason)
                        self._record_timeline_entry(skipped_phase, skip_result)

                        # Emit skip event for intermediate phase (Issue 1.2.4)
                        self._transition_logger.log_phase_skip(
                            cycle_id=envelope.context.cycle_id,
                            batch_id=envelope.context.batch_id,
                            space_id=envelope.context.space_id,
                            tenant_id=envelope.context.tenant_id,
                            phase_id=skipped_phase.value,
                            skip_reason=skip_reason,
                            duration_ms=0,
                            trace_id=(
                                envelope.observability.trace_id if envelope.observability else None
                            ),
                            span_id=(
                                envelope.observability.current_span_id
                                if envelope.observability
                                else None
                            ),
                        )
                    # Jump to the target phase
                    logger.info(
                        f"P03 Runner: Skip transition {phase_id.value} -> {next_phase.value}",
                        extra={
                            "cycle_id": envelope.context.cycle_id,
                            "from_phase": phase_id.value,
                            "to_phase": next_phase.value,
                            "skip_to_index": skip_to_index,
                        },
                    )
                    current_index = skip_to_index
                    continue

            final_phase = phase_id

            # Checkpoint if enabled
            if ctx.checkpoint_enabled and self._on_checkpoint:
                checkpoint_data = envelope.checkpoints.get(phase_id, {})
                self._on_checkpoint(envelope, phase_id, checkpoint_data)

            current_index += 1
            logger.debug(
                f"P03 Runner: Advancing to next phase index {current_index}",
                extra={
                    "cycle_id": envelope.context.cycle_id,
                    "next_index": current_index,
                    "next_phase": (
                        execution_order[current_index].value
                        if current_index < len(execution_order)
                        else "END"
                    ),
                },
            )

        # Log loop exit
        logger.info(
            "P03 Runner: Execution loop completed",
            extra={
                "cycle_id": envelope.context.cycle_id,
                "final_index": current_index,
                "final_phase": final_phase.value if final_phase else None,
                "dlq_reason": dlq_reason,
                "phases_executed": [p.value for p in phase_results.keys()],
            },
        )

        # Calculate total duration
        total_duration_ms = int(time.time() * 1000) - cycle_start_ms

        # Emit cycle-level metrics (Issue 6.1.2)
        self._emit_cycle_metrics(
            ctx=ctx,
            envelope=envelope,
            total_duration_ms=total_duration_ms,
            phase_results=phase_results,
            success=dlq_reason is None,
        )

        # Determine final status
        if dlq_reason:
            return P03CycleResult.fail(
                cycle_id=envelope.context.cycle_id,
                batch_id=envelope.context.batch_id,
                phase_results=phase_results,
                total_duration_ms=total_duration_ms,
                failed_phase=final_phase or start_phase,
                dlq_reason=dlq_reason,
            )

        return P03CycleResult.success(
            cycle_id=envelope.context.cycle_id,
            batch_id=envelope.context.batch_id,
            phase_results=phase_results,
            total_duration_ms=total_duration_ms,
        )

    # =========================================================================
    # CYCLE METRICS EMISSION (Issue 6.1.2)
    # =========================================================================

    def _emit_cycle_metrics(
        self,
        ctx: P03RunnerContext,
        envelope: "P03BatchEnvelope",
        total_duration_ms: int,
        phase_results: Dict[P03PhaseId, P03PhaseResult],
        success: bool,
    ) -> None:
        """
        Emit cycle-level metrics via P03MetricsRegistry.

        Per Issue 6.1.2, emits:
        - p03_cycle_total: Counter for cycle completions
        - p03_cycle_duration_seconds: Histogram for cycle duration
        - p03_cycle_batch_size: Histogram for batch item count
        - p03_cycle_phase_skip_count: How many phases were skipped

        Args:
            ctx: Runner context with metrics registry
            envelope: Batch envelope with context
            total_duration_ms: Cycle duration in milliseconds
            phase_results: Results from each phase
            success: True if cycle succeeded, False if DLQ'd
        """
        if not ctx.metrics_registry:
            return

        registry: P03MetricsRegistry = ctx.metrics_registry

        # Extract labels
        tenant_id = envelope.context.tenant_id
        space_id = envelope.context.space_id
        qos_band = ctx.qos_band

        # Count skipped phases
        skipped_count = sum(1 for r in phase_results.values() if r.status.value == "SKIPPED")

        # Emit cycle completion counter
        registry.emit_cycle_complete(
            tenant_id=tenant_id,
            space_id=space_id,
            qos_band=qos_band,
            success=success,
        )

        # Emit cycle duration histogram
        registry.emit_cycle_duration(
            duration_ms=total_duration_ms,
            tenant_id=tenant_id,
            space_id=space_id,
            qos_band=qos_band,
        )

        # Emit batch size histogram
        batch_size = envelope.context.item_count
        registry.emit_batch_size(
            batch_size=batch_size,
            tenant_id=tenant_id,
            space_id=space_id,
            qos_band=qos_band,
        )

        # Emit phase skip count
        registry.emit_phase_skip_count(
            skip_count=skipped_count,
            tenant_id=tenant_id,
            space_id=space_id,
        )

    # =========================================================================
    # PHASE EXECUTION
    # =========================================================================

    async def _execute_phase(
        self,
        envelope: "P03BatchEnvelope",
        ctx: P03RunnerContext,
        phase: P03PhaseProtocol,
        phase_id: P03PhaseId,
    ) -> P03PhaseResult:
        """
        Execute a single phase with callbacks and structured logging.

        Emits structured log events per Issue 1.2.4:
        - phase_start: When phase begins execution
        - phase_complete: When phase succeeds
        - phase_skip: When phase is skipped
        - phase_fail: When phase fails

        Args:
            envelope: The batch envelope
            ctx: Runner context
            phase: Phase implementation
            phase_id: Phase identifier

        Returns:
            P03PhaseResult from phase execution
        """
        # Extract identifiers for logging
        cycle_id = envelope.context.cycle_id
        batch_id = envelope.context.batch_id
        space_id = envelope.context.space_id
        tenant_id = envelope.context.tenant_id
        trace_id = envelope.observability.trace_id if envelope.observability else None
        span_id = envelope.observability.current_span_id if envelope.observability else None

        # Emit phase_start event
        self._transition_logger.log_phase_start(
            cycle_id=cycle_id,
            batch_id=batch_id,
            space_id=space_id,
            tenant_id=tenant_id,
            phase_id=phase_id.value,
            trace_id=trace_id,
            span_id=span_id,
        )

        # Call phase start callback
        if self._on_phase_start:
            self._on_phase_start(envelope, phase_id, ctx)

        # Mark phase start on envelope
        envelope.mark_phase_start(phase_id)

        # Execute phase
        result = await phase.run(envelope, ctx)

        # Emit structured log event based on result
        if result.is_success:
            self._transition_logger.log_phase_complete(
                cycle_id=cycle_id,
                batch_id=batch_id,
                space_id=space_id,
                tenant_id=tenant_id,
                phase_id=phase_id.value,
                duration_ms=result.duration_ms,
                trace_id=trace_id,
                span_id=span_id,
            )
            envelope.mark_phase_complete(phase_id)
            # Create checkpoint at phase boundary
            if ctx.checkpoint_enabled:
                envelope.checkpoint(phase_id, result.outputs_summary)
        elif result.is_skipped:
            self._transition_logger.log_phase_skip(
                cycle_id=cycle_id,
                batch_id=batch_id,
                space_id=space_id,
                tenant_id=tenant_id,
                phase_id=phase_id.value,
                skip_reason=result.skip_reason or "unspecified",
                duration_ms=result.duration_ms,
                trace_id=trace_id,
                span_id=span_id,
            )
            envelope.mark_phase_skipped(phase_id, result.skip_reason or "")
        elif result.is_failed and result.error_info:
            self._transition_logger.log_phase_fail(
                cycle_id=cycle_id,
                batch_id=batch_id,
                space_id=space_id,
                tenant_id=tenant_id,
                phase_id=phase_id.value,
                error_type=result.error_info.error_type,
                error_message=result.error_info.error_message,
                duration_ms=result.duration_ms,
                retry_count=result.retry_count,
                trace_id=trace_id,
                span_id=span_id,
            )
            envelope.mark_phase_failed(phase_id, result.error_info)

        # Call phase complete callback
        if self._on_phase_complete:
            self._on_phase_complete(envelope, phase_id, result, ctx)

        return result

    # =========================================================================
    # TRANSITION LOGIC
    # =========================================================================

    def _get_skip_target(self, phase_id: P03PhaseId) -> Optional[P03PhaseId]:
        """
        Get the target phase for a skip transition.

        Args:
            phase_id: Current phase that was skipped

        Returns:
            Target phase to skip to, or None if no skip transition
        """
        skip_info = SKIP_TRANSITIONS.get(phase_id)
        if skip_info:
            return skip_info[0]
        return None

    def _validate_resume(
        self,
        start_phase: P03PhaseId,
        envelope: "P03BatchEnvelope",
    ) -> None:
        """
        Validate that resuming from start_phase is allowed.

        Args:
            start_phase: Phase to resume from
            envelope: The batch envelope

        Raises:
            ResumeNotAllowedError: If resume is not allowed
        """
        resume_policy = RESUME_MATRIX.get(start_phase)
        if not resume_policy:
            raise ResumeNotAllowedError(start_phase, "No resume policy defined")

        if not resume_policy.can_resume:
            raise ResumeNotAllowedError(start_phase, "Phase does not support resume")

        # Check required state exists
        for required_state in resume_policy.requires_state:
            if required_state == "event_ids":
                if not envelope.context.event_ids:
                    raise ResumeNotAllowedError(
                        start_phase, f"Missing required state: {required_state}"
                    )
            elif required_state == "batch_id":
                if not envelope.context.batch_id:
                    raise ResumeNotAllowedError(
                        start_phase, f"Missing required state: {required_state}"
                    )
            # Note: More complex state checks would go here
            # For now, we trust that if checkpoint exists, state is valid

        # If resume_from differs from start_phase, adjust
        # (e.g., R7 failure should resume from R6)
        if resume_policy.resume_from != start_phase:
            # The caller should use resume_policy.resume_from instead
            # This is informational - we don't raise, just log
            pass

    def _record_timeline_entry(
        self,
        phase_id: P03PhaseId,
        result: P03PhaseResult,
    ) -> None:
        """Record a timeline entry for the phase execution."""
        end_ts = int(time.time() * 1000)
        start_ts = end_ts - result.duration_ms

        entry = PhaseTimelineEntry(
            phase_id=phase_id,
            status=result.status,
            start_ts=start_ts,
            end_ts=end_ts,
            duration_ms=result.duration_ms,
            skip_reason=result.skip_reason,
            error_type=result.error_info.error_type if result.error_info else None,
            retry_count=result.retry_count,
        )
        self._timeline.append(entry)

    # =========================================================================
    # R6-SPECIFIC RETRY LOGIC (Issue 5.2.W6)
    # =========================================================================

    async def _execute_r6_with_retry(
        self,
        envelope: "P03BatchEnvelope",
        ctx: P03RunnerContext,
        phase: P03PhaseProtocol,
    ) -> P03PhaseResult:
        """
        Execute R6 with specialized retry logic for VERSION_CONFLICT and UNIQUE_VIOLATION.

        Issue 5.2.W6: Targeted R6 error recovery.

        Retry policies:
        - VERSION_CONFLICT: Max 3 immediate retries with re-read
        - UNIQUE_VIOLATION: Max 1 retry, check existing and skip/merge
        - MANIFEST_INVALID: DLQ immediately (no retry)

        DLQ Threshold: >10% version conflicts in batch triggers DLQ.

        Args:
            envelope: The batch envelope
            ctx: Runner context
            phase: R6 phase implementation

        Returns:
            P03PhaseResult from phase execution
        """
        phase_id = P03PhaseId.R6_STAGE
        total_events = len(envelope.context.event_ids) if envelope.context.event_ids else 1
        version_conflict_count = 0

        # Track retry state per error type
        retry_counts: Dict[P03ErrorType, int] = {
            P03ErrorType.R6_VERSION_CONFLICT: 0,
            P03ErrorType.R6_UNIQUE_VIOLATION: 0,
        }

        while True:
            # Execute phase attempt
            result = await self._execute_phase(envelope, ctx, phase, phase_id)

            if result.is_success or result.is_skipped:
                return result

            if not result.error_info:
                # Unknown error - return as-is
                return result

            # Classify the error
            error_type = classify_r6_error(result.error_info.error_message)

            # Get retry config for this error type
            retry_config = R6_RETRY_CONFIGS.get(error_type)

            if not retry_config or retry_config.max_retries == 0:
                # No retry allowed - DLQ
                return self._create_r6_dlq_result(
                    envelope=envelope,
                    error_type=error_type,
                    error_message=result.error_info.error_message,
                    duration_ms=result.duration_ms,
                    reason=f"{error_type.value}: no retry policy",
                )

            # Track version conflicts for DLQ threshold check
            if error_type == P03ErrorType.R6_VERSION_CONFLICT:
                version_conflict_count += 1
                conflict_rate = version_conflict_count / total_events

                if conflict_rate > R6_DLQ_CONFLICT_THRESHOLD:
                    return self._create_r6_dlq_result(
                        envelope=envelope,
                        error_type=error_type,
                        error_message=result.error_info.error_message,
                        duration_ms=result.duration_ms,
                        reason=f"DLQ threshold exceeded: {conflict_rate:.1%} > {R6_DLQ_CONFLICT_THRESHOLD:.0%}",
                    )

            # Check if we've exceeded max retries for this error type
            if retry_counts[error_type] >= retry_config.max_retries:
                return self._create_r6_dlq_result(
                    envelope=envelope,
                    error_type=error_type,
                    error_message=result.error_info.error_message,
                    duration_ms=result.duration_ms,
                    reason=f"{error_type.value}: max retries ({retry_config.max_retries}) exceeded",
                )

            # Apply retry strategy
            retry_counts[error_type] += 1

            if error_type == P03ErrorType.R6_VERSION_CONFLICT:
                # Re-read event versions before retry
                await self._refresh_event_versions(envelope, ctx)

            elif error_type == P03ErrorType.R6_UNIQUE_VIOLATION:
                # Check existing and skip/merge strategy
                existing_handled = await self._handle_unique_violation(envelope, ctx)
                if existing_handled:
                    # Existing record found and handled - skip this attempt
                    return P03PhaseResult.skip(
                        phase_id=phase_id,
                        reason="Unique violation resolved: existing record merged",
                        duration_ms=result.duration_ms,
                    )

            # Log retry attempt
            self._transition_logger.log_phase_fail(
                cycle_id=envelope.context.cycle_id,
                batch_id=envelope.context.batch_id,
                space_id=envelope.context.space_id,
                tenant_id=envelope.context.tenant_id,
                phase_id=phase_id.value,
                error_type=error_type.value,
                error_message=f"Retry {retry_counts[error_type]}/{retry_config.max_retries}: {result.error_info.error_message}",
                duration_ms=result.duration_ms,
                retry_count=retry_counts[error_type],
                trace_id=envelope.observability.trace_id if envelope.observability else None,
                span_id=envelope.observability.current_span_id if envelope.observability else None,
            )

    def _create_r6_dlq_result(
        self,
        envelope: "P03BatchEnvelope",
        error_type: P03ErrorType,
        error_message: str,
        duration_ms: int,
        reason: str,
    ) -> P03PhaseResult:
        """
        Create a DLQ result for R6 failures.

        Args:
            envelope: The batch envelope
            error_type: Classified error type
            error_message: Original error message
            duration_ms: Phase duration
            reason: DLQ reason

        Returns:
            P03PhaseResult with DLQ status
        """
        from k0.pipelines.p03.observability import P03Error

        return P03PhaseResult.fail(
            phase_id=P03PhaseId.R6_STAGE,
            error=P03Error.create(
                phase="R6_STAGE",
                stage_id="staging",
                error_type=error_type.value,
                error_message=error_message,
                recoverable=False,
                context={"dlq_reason": reason},
            ),
            duration_ms=duration_ms,
            retry_count=0,  # Already exceeded
        )

    async def _refresh_event_versions(
        self,
        envelope: "P03BatchEnvelope",
        ctx: P03RunnerContext,
    ) -> None:
        """
        Re-read event versions from storage before VERSION_CONFLICT retry.

        Issue 5.2.W6: Re-read current versions to resolve optimistic locking conflicts.

        Args:
            envelope: The batch envelope
            ctx: Runner context
        """
        if not envelope.context.event_ids:
            return

        # Use syscall to re-read event versions if available
        if ctx.syscalls and hasattr(ctx.syscalls, "get_event_versions"):
            try:
                event_versions = await ctx.syscalls.get_event_versions(envelope.context.event_ids)
                # Update envelope with fresh versions
                if hasattr(envelope, "update_event_versions"):
                    envelope.update_event_versions(event_versions)
            except Exception:
                # Best effort - continue with retry even if version refresh fails
                pass

    async def _handle_unique_violation(
        self,
        envelope: "P03BatchEnvelope",
        ctx: P03RunnerContext,
    ) -> bool:
        """
        Handle UNIQUE_VIOLATION by checking existing record and merging if applicable.

        Issue 5.2.W6: Check-existing-skip-merge strategy for unique violations.

        Args:
            envelope: The batch envelope
            ctx: Runner context

        Returns:
            True if existing record was found and handled (skip staging)
            False if should retry staging
        """
        # Use syscall to check for existing staged records
        if ctx.syscalls and hasattr(ctx.syscalls, "check_existing_staged"):
            try:
                existing = await ctx.syscalls.check_existing_staged(
                    batch_id=envelope.context.batch_id,
                    event_ids=envelope.context.event_ids,
                )
                if existing:
                    # Record exists - mark as already staged and return True to skip
                    envelope.mark_already_staged(existing)
                    return True
            except Exception:
                # Best effort - continue with retry if check fails
                pass
        return False

    # =========================================================================
    # VALIDATION HELPERS
    # =========================================================================

    def validate_phase_order(
        self,
        phases: List[P03PhaseId],
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate that a sequence of phases follows legal transitions.

        Args:
            phases: List of phase IDs in execution order

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not phases:
            return (True, None)

        for i in range(len(phases) - 1):
            from_phase = phases[i]
            to_phase = phases[i + 1]
            if not is_valid_transition(from_phase, to_phase):
                return (
                    False,
                    f"Invalid transition: {from_phase.value} -> {to_phase.value}",
                )

        return (True, None)

    def get_resume_phase(self, failed_phase: P03PhaseId) -> P03PhaseId:
        """
        Get the correct phase to resume from after a failure.

        Some phases (like R7) require resuming from an earlier phase (R6).

        Args:
            failed_phase: The phase that failed

        Returns:
            The phase to resume from
        """
        resume_policy = RESUME_MATRIX.get(failed_phase)
        if resume_policy:
            return resume_policy.resume_from
        return failed_phase


# =============================================================================
# FACTORY FUNCTION
# =============================================================================


def create_runner(
    phases: Dict[P03PhaseId, P03PhaseProtocol],
    *,
    on_phase_start: Optional[Callable[..., Any]] = None,
    on_phase_complete: Optional[Callable[..., Any]] = None,
    on_checkpoint: Optional[Callable[..., Any]] = None,
    transition_logger: Optional[PhaseTransitionLoggerProtocol] = None,
) -> P03SequentialRunner:
    """
    Factory function to create a P03SequentialRunner.

    Args:
        phases: Mapping of phase ID to phase implementation
        on_phase_start: Optional callback before phase
        on_phase_complete: Optional callback after phase
        on_checkpoint: Optional callback for checkpointing
        transition_logger: Optional structured logger for phase events (Issue 1.2.4)

    Returns:
        Configured P03SequentialRunner
    """
    return P03SequentialRunner(
        phases=phases,
        on_phase_start=on_phase_start,
        on_phase_complete=on_phase_complete,
        on_checkpoint=on_checkpoint,
        transition_logger=transition_logger,
    )
