"""
P03 Batch Envelope — Top-Level Container

This module defines the P03BatchEnvelope, the root container that flows
through all R0-R8 phases of the consolidation pipeline.

References:
- Discovery: docs/pipelines/P03_envelope_fields_discovery.md §15.1
- Issue: docs/TEMP_EXECUTION_DOCS/M1_EXECUTION.md Issue 1.1.1
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from k0.pipelines.p03.context import P03CycleContext
from k0.pipelines.p03.event_state import P03EventState
from k0.pipelines.p03.observability import P03Error, P03ObservabilityContext
from k0.pipelines.p03.phase_outputs import P03PhaseOutputs
from k0.pipelines.p03.runner_contract import P03PhaseId, P03PhaseStatus
from k0.pipelines.p03.staged_writes import P03StagedWrites


@dataclass
class P03BatchEnvelope:
    """
    Top-level envelope for P03 consolidation pipeline.

    This is the root container that flows through all R0-R8 phases.
    Unlike P02's shallow merge, P03 uses nested enrichment:
    - context: Immutable batch metadata (set in R0)
    - events: Mutable per-event state (enriched R1-R6)
    - phases: Aggregated outputs (populated per phase)
    - staged: Deferred writes (accumulated R1-R6, committed R7)
    - observability: Tracing, timing, metrics, errors

    Attributes:
        context: Immutable cycle context (set in R0, never changes)
        events: List of per-event states (enriched through phases)
        phases: Phase outputs container (populated incrementally)
        staged: Staged writes container (accumulated, committed in R7)
        observability: Observability context (tracing, timing, errors)
        current_phase: Current phase in execution
        phase_statuses: Status of each phase
        checkpoints: Phase checkpoint snapshots
    """

    # === IMMUTABLE CONTEXT (set in R0) ===
    context: P03CycleContext

    # === MUTABLE PER-EVENT STATE ===
    events: List[P03EventState] = field(default_factory=list)

    # === PHASE OUTPUTS (populated incrementally) ===
    phases: P03PhaseOutputs = field(default_factory=P03PhaseOutputs)

    # === STAGED WRITES (accumulated, committed in R7) ===
    staged: P03StagedWrites = field(default_factory=P03StagedWrites)

    # === OBSERVABILITY ===
    observability: P03ObservabilityContext = field(default_factory=P03ObservabilityContext)

    # === STATE TRACKING ===
    current_phase: P03PhaseId = P03PhaseId.R0_INIT
    phase_statuses: Dict[P03PhaseId, P03PhaseStatus] = field(default_factory=dict)

    # === CHECKPOINTS ===
    checkpoints: Dict[P03PhaseId, Dict] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        context: P03CycleContext,
        events: Optional[List[P03EventState]] = None,
    ) -> "P03BatchEnvelope":
        """
        Factory method for creating a new envelope.

        Args:
            context: Immutable cycle context (from R0)
            events: Initial list of event states (from R0)

        Returns:
            New P03BatchEnvelope instance
        """
        envelope = cls(
            context=context,
            events=events or [],
        )
        # Initialize all phase statuses to INIT
        for phase in P03PhaseId.execution_order():
            envelope.phase_statuses[phase] = P03PhaseStatus.INIT
        return envelope

    # =========================================================================
    # PHASE TRACKING
    # =========================================================================

    def mark_phase_start(self, phase: P03PhaseId) -> None:
        """
        Record phase transition to PROC status.

        Args:
            phase: Phase being started
        """
        self.current_phase = phase
        self.phase_statuses[phase] = P03PhaseStatus.PROC
        self.observability.start_phase(phase.value)

    def mark_phase_complete(self, phase: P03PhaseId) -> None:
        """
        Record phase completion with DONE status.

        Args:
            phase: Phase that completed
        """
        self.phase_statuses[phase] = P03PhaseStatus.DONE
        self.observability.end_phase(phase.value)

    def mark_phase_skipped(self, phase: P03PhaseId, reason: str) -> None:
        """
        Record phase skip with SKIP status.

        Args:
            phase: Phase that was skipped
            reason: Why it was skipped
        """
        self.phase_statuses[phase] = P03PhaseStatus.SKIP
        # Record skip in observability and emit metrics (Issue 6.1.3)
        self.observability.increment(f"phase.{phase.value}.skipped")
        self.observability.end_phase(phase.value, status="skipped")

    def mark_phase_failed(self, phase: P03PhaseId, error: P03Error) -> None:
        """
        Record phase failure with FAIL status.

        Args:
            phase: Phase that failed
            error: Error details
        """
        self.phase_statuses[phase] = P03PhaseStatus.FAIL
        self.observability.add_error(error)
        # Emit phase failure metrics (Issue 6.1.3)
        self.observability.end_phase(phase.value, status="failed")

    def get_phase_status(self, phase: P03PhaseId) -> P03PhaseStatus:
        """Get status of a specific phase."""
        return self.phase_statuses.get(phase, P03PhaseStatus.INIT)

    def get_phase_duration_ms(self, phase: P03PhaseId) -> Optional[int]:
        """Get duration of a completed phase in milliseconds."""
        return self.observability.get_phase_duration_ms(phase.value)

    # =========================================================================
    # EVENT ACCESS
    # =========================================================================

    def get_event(self, event_id: str) -> Optional[P03EventState]:
        """
        Lookup event by ID.

        Args:
            event_id: Event ID to find

        Returns:
            P03EventState if found, None otherwise
        """
        for event in self.events:
            if event.event_id == event_id:
                return event
        return None

    def get_events_by_cluster(self, cluster_id: str) -> List[P03EventState]:
        """
        Get all events in a specific cluster.

        Args:
            cluster_id: Cluster ID to filter by

        Returns:
            List of events in the cluster
        """
        return [e for e in self.events if e.cluster_id == cluster_id]

    def get_actionable_events(self) -> List[P03EventState]:
        """Get events that need truth writes (not SKIP/PRUNE)."""
        return [e for e in self.events if e.is_actionable()]

    @property
    def event_count(self) -> int:
        """Number of events in the batch."""
        return len(self.events)

    # =========================================================================
    # CHECKPOINTING
    # =========================================================================

    def checkpoint(self, phase: P03PhaseId, summary: Optional[Dict] = None) -> None:
        """
        Create checkpoint at current phase.

        Args:
            phase: Phase to checkpoint
            summary: Optional phase-specific summary
        """
        self.checkpoints[phase] = {
            "phase": phase.value,
            "timestamp": int(time.time() * 1000),
            "events_count": len(self.events),
            "staged_writes_count": self.staged.total_writes(),
            "errors_count": len(self.observability.errors),
            "phase_timings": dict(self.observability.get_all_phase_durations()),
            "summary": summary or {},
        }

    def get_checkpoint(self, phase: P03PhaseId) -> Optional[Dict]:
        """Get checkpoint for a specific phase."""
        return self.checkpoints.get(phase)

    def has_checkpoint(self, phase: P03PhaseId) -> bool:
        """Check if checkpoint exists for phase."""
        return phase in self.checkpoints

    # =========================================================================
    # SUMMARY
    # =========================================================================

    def to_summary_dict(self) -> Dict:
        """
        Convert to compact summary for logging.

        Returns:
            Dictionary with key envelope metrics
        """
        return {
            "cycle_id": self.context.cycle_id,
            "batch_id": self.context.batch_id,
            "tenant_id": self.context.tenant_id,
            "space_id": self.context.space_id,
            "current_phase": self.current_phase.value,
            "events_count": len(self.events),
            "staged_writes_count": self.staged.total_writes(),
            "errors_count": len(self.observability.errors),
            "phase_statuses": {p.value: s.value for p, s in self.phase_statuses.items()},
        }

    def __repr__(self) -> str:
        return (
            f"P03BatchEnvelope(cycle_id={self.context.cycle_id!r}, "
            f"events={len(self.events)}, phase={self.current_phase.value})"
        )
