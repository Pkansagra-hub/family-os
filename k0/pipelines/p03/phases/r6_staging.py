"""
R6 Phase — Staging Table Updates.

M5 Issue 5.1.13: R6Staging phase file
M5 Issue 5.1.14: R6 accepts R1-R4 outputs
M5 Issue 5.1.15: R6 outputs to P03StagedWrites

This phase stages all consolidation outputs for atomic commit:
1. Extract R1-R5 outputs from envelope
2. Create and configure R6Coordinator
3. Execute R6 staging workflow
4. Populate envelope.staged with R6Output

References:
    - Dossier §4.7 (R6 — Staging Table Updates)
    - Dossier Appendix G R6 (R6 phase contract)
    - M5_EXECUTION.md Issue 5.1.13-5.1.15
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from k0.modules.consolidation.staging.dedup_metadata import DuplicationResult
from k0.modules.consolidation.staging.r6_coordinator import (
    R6Coordinator,
    R6CoordinatorConfig,
    R6CoordinatorResult,
)
from k0.modules.consolidation.staging.r6_output import StagedEventUpdate
from k0.pipelines.p03.event_state import P03EventState
from k0.pipelines.p03.observability import P03Error
from k0.pipelines.p03.phase_interface import P03PhaseResult
from k0.pipelines.p03.phase_outputs import (
    CausalEdge,
    DecayUpdate,
    DedupMerge,
    EpisodeCluster,
    GapCandidate,
    KGEdge,
    KGEdgeUpdate,
    KGEntity,
    KGEntityUpdate,
)
from k0.pipelines.p03.runner_contract import P03PhaseId

if TYPE_CHECKING:
    from k0.pipelines.p03.envelope import P03BatchEnvelope
    from k0.pipelines.p03.phase_interface import P03RunnerContext

logger = logging.getLogger(__name__)


# =============================================================================
# R6 INPUTS DATACLASS — Issue 5.1.14
# =============================================================================


@dataclass
class R6Inputs:
    """
    Container for all R1-R5 inputs required by R6.

    Extracts all relevant data from the P03BatchEnvelope that R6
    needs to perform staging: event states, clusters, dedup results,
    KG entities/edges, gaps, and cycle context.

    Attributes:
        event_states: Map of event_id → P03EventState
        r2_clusters: Episode clusters from R2
        r3_dedup_merges: Dedup merge operations from R3
        r3_decay_updates: Decay updates from R3
        r4_new_entities: New KG entities from R4
        r4_updated_entities: Updated KG entities from R4
        r4_new_edges: New KG edges from R4
        r4_updated_edges: Updated KG edges from R4
        r4_causal_edges: Causal edges from R4
        r4_gap_candidates: Gap candidates from R4
        cycle_id: Cycle identifier
        tenant_id: Tenant identifier
        space_id: Space identifier
        cycle_start_ms: Cycle start timestamp in milliseconds
    """

    # Per-event state from R0-R4 enrichment
    event_states: Dict[str, P03EventState] = field(default_factory=dict)

    # R2 outputs
    r2_clusters: List[EpisodeCluster] = field(default_factory=list)

    # R3 outputs
    r3_dedup_merges: List[DedupMerge] = field(default_factory=list)
    r3_decay_updates: List[DecayUpdate] = field(default_factory=list)

    # R4 outputs
    r4_new_entities: List[KGEntity] = field(default_factory=list)
    r4_updated_entities: List[KGEntityUpdate] = field(default_factory=list)
    r4_new_edges: List[KGEdge] = field(default_factory=list)
    r4_updated_edges: List[KGEdgeUpdate] = field(default_factory=list)
    r4_causal_edges: List[CausalEdge] = field(default_factory=list)
    r4_gap_candidates: List[GapCandidate] = field(default_factory=list)

    # Cycle context
    cycle_id: str = ""
    tenant_id: str = ""
    space_id: str = ""
    cycle_start_ms: int = 0

    @property
    def event_count(self) -> int:
        """Total number of events in batch."""
        return len(self.event_states)

    @property
    def batch_event_ids(self) -> Set[str]:
        """Set of all event IDs in batch."""
        return set(self.event_states.keys())


# =============================================================================
# R6 STAGING PHASE
# =============================================================================


class R6Staging:
    """
    R6 Phase: Stage all consolidation outputs for atomic commit.

    Responsibilities:
        1. Extract R1-R5 outputs from envelope
        2. Create R6Coordinator with all sub-components
        3. Execute staging workflow (status marking, write assembly, etc.)
        4. Populate envelope.staged with R6Output
        5. Return P03PhaseResult

    The R6 phase does NOT write to the database — it stages writes
    for R7 to execute atomically.

    Sub-Components (via R6Coordinator):
        - ConsolidationStatusMarker (5.1.2)
        - DedupMetadataPopulator (5.1.3)
        - ReconciliationRecorder (5.1.4)
        - IdempotencyKeyGenerator (5.1.5)
        - TruthWriteAssembler (5.1.6)
        - KGWriteAssembler (5.1.7)
        - OutboxEventAssembler (5.1.8)
        - ManifestValidator (5.1.9)
        - SummaryGenerator (5.1.10)
    """

    PHASE_ID = P03PhaseId.R6_STAGE

    def __init__(
        self,
        config: Optional[R6CoordinatorConfig] = None,
    ) -> None:
        """
        Initialize R6Staging phase.

        Args:
            config: Optional R6CoordinatorConfig for the coordinator
        """
        self._config = config or R6CoordinatorConfig()

    async def run(
        self,
        envelope: P03BatchEnvelope,
        ctx: P03RunnerContext,
    ) -> P03PhaseResult:
        """
        Execute R6 staging phase.

        Args:
            envelope: P03BatchEnvelope with R1-R5 outputs
            ctx: Runner context with syscalls, logger, config

        Returns:
            P03PhaseResult indicating success/failure
        """
        start_ms = int(time.time() * 1000)
        cycle_id = envelope.context.cycle_id

        logger.info(
            "R6: Starting staging phase",
            extra={
                "cycle_id": cycle_id,
                "event_count": len(envelope.events),
            },
        )

        try:
            # === STEP 1: Create coordinator ===
            coordinator = self._create_coordinator(envelope, ctx)

            # === STEP 2: Extract inputs from envelope ===
            event_states = self._extract_event_states(envelope)
            phase_outputs = self._extract_phase_outputs(envelope)
            gaps = self._extract_gaps(envelope)
            batch_event_ids = self._extract_batch_event_ids(envelope)
            dedup_results = self._extract_dedup_results(envelope)
            phase_durations = self._extract_phase_durations(envelope)
            cycle_start_ms = envelope.context.triggered_at

            # === STEP 3: Execute R6 coordinator ===
            result = coordinator.execute(
                event_states=event_states,
                phase_outputs=phase_outputs,
                gaps=gaps,
                batch_event_ids=batch_event_ids,
                dedup_results=dedup_results,
                phase_durations=phase_durations,
                cycle_start_ms=cycle_start_ms,
            )

            # === STEP 4: Handle result ===
            if not result.success:
                return self._handle_failure(result, cycle_id, start_ms)

            # === STEP 5: Populate envelope with R6Output ===
            self._populate_envelope(envelope, result)

            duration_ms = int(time.time() * 1000) - start_ms

            logger.info(
                "R6: Staging phase completed",
                extra={
                    "cycle_id": cycle_id,
                    "duration_ms": duration_ms,
                    "event_updates": (
                        len(result.r6_output.staged_event_updates) if result.r6_output else 0
                    ),
                    "truth_writes": (
                        len(result.r6_output.staged_truth_writes) if result.r6_output else 0
                    ),
                    "kg_writes": len(result.r6_output.staged_kg_writes) if result.r6_output else 0,
                    "outbox_events": (
                        len(result.r6_output.staged_outbox_events) if result.r6_output else 0
                    ),
                },
            )

            return P03PhaseResult.done(
                phase_id=self.PHASE_ID,
                duration_ms=duration_ms,
                outputs_summary=self._build_outputs_summary(result),
                idempotency_key=(
                    result.r6_output.r6_idempotency_key
                    if result.r6_output
                    else f"p03:r6:{cycle_id}"
                ),
            )

        except Exception as e:
            duration_ms = int(time.time() * 1000) - start_ms

            logger.exception(
                "R6: Staging phase failed",
                extra={
                    "cycle_id": cycle_id,
                    "duration_ms": duration_ms,
                    "error": str(e),
                },
            )

            return P03PhaseResult.fail(
                phase_id=self.PHASE_ID,
                error=P03Error(
                    error_id=f"r6-{cycle_id}",
                    phase="R6",
                    stage_id="staging",
                    error_type="R6_STAGING_ERROR",
                    error_message=str(e),
                    recoverable=True,  # R6 can be retried
                ),
                duration_ms=duration_ms,
                idempotency_key=f"p03:r6:{cycle_id}",
            )

    # =========================================================================
    # COORDINATOR CREATION
    # =========================================================================

    def _create_coordinator(
        self,
        envelope: P03BatchEnvelope,
        ctx: P03RunnerContext,
    ) -> R6Coordinator:
        """
        Create R6Coordinator with all sub-components.

        Args:
            envelope: Batch envelope for context
            ctx: Runner context

        Returns:
            Configured R6Coordinator
        """
        cycle_ulid = envelope.context.cycle_id
        tenant_id = envelope.context.tenant_id
        space_id = envelope.context.space_id

        # Extract existing entity IDs for FK validation
        existing_entity_ids = self._get_existing_entity_ids(envelope)

        # Extract actor_id from batch events (should be same for all events in batch)
        actor_id = self._extract_batch_actor_id(envelope)

        return R6Coordinator.create(
            cycle_ulid=cycle_ulid,
            tenant_id=tenant_id,
            space_id=space_id,
            actor_id=actor_id,
            existing_entity_ids=existing_entity_ids,
            config=self._config,
        )

    def _extract_batch_actor_id(self, envelope: P03BatchEnvelope) -> str:
        """
        Extract actor_id from batch events.

        In single-user mode, all events in a batch should have the same actor_id.
        Returns the first non-empty actor_id found, or empty string if none.

        Args:
            envelope: Batch envelope with events

        Returns:
            Actor ID string (e.g., "Prince") or empty string
        """
        for event in envelope.events:
            if event.actor_id:
                return event.actor_id
        return ""

    def _get_existing_entity_ids(self, envelope: P03BatchEnvelope) -> Set[str]:
        """
        Extract known entity IDs from envelope for FK validation.

        Args:
            envelope: Batch envelope

        Returns:
            Set of existing entity IDs
        """
        entity_ids: Set[str] = set()

        # Add entity IDs from R4 outputs if available
        r4_outputs = getattr(envelope.phases, "r4", None)
        if r4_outputs:
            entities = getattr(r4_outputs, "entities", None)
            if entities:
                for entity in entities:
                    if hasattr(entity, "entity_id"):
                        entity_ids.add(entity.entity_id)

        return entity_ids

    # =========================================================================
    # INPUT EXTRACTION — Issue 5.1.14
    # =========================================================================

    def _extract_inputs(self, envelope: P03BatchEnvelope) -> R6Inputs:
        """
        Extract all R1-R5 inputs from envelope.

        Consolidates event states and all phase outputs into a single
        R6Inputs container for coordinator consumption.

        Args:
            envelope: P03BatchEnvelope with R1-R5 outputs

        Returns:
            R6Inputs with all required data
        """
        phases = envelope.phases

        return R6Inputs(
            # Per-event state from R0-R4 enrichment
            event_states={e.event_id: e for e in envelope.events},
            # R2 outputs
            r2_clusters=list(phases.r2_clusters) if phases.r2_clusters else [],
            # R3 outputs
            r3_dedup_merges=list(phases.r3_dedup_merges) if phases.r3_dedup_merges else [],
            r3_decay_updates=list(phases.r3_decay_updates) if phases.r3_decay_updates else [],
            # R4 outputs
            r4_new_entities=list(phases.r4_new_entities) if phases.r4_new_entities else [],
            r4_updated_entities=(
                list(phases.r4_updated_entities) if phases.r4_updated_entities else []
            ),
            r4_new_edges=list(phases.r4_new_edges) if phases.r4_new_edges else [],
            r4_updated_edges=list(phases.r4_updated_edges) if phases.r4_updated_edges else [],
            r4_causal_edges=list(phases.r4_causal_edges) if phases.r4_causal_edges else [],
            r4_gap_candidates=list(phases.r4_gap_candidates) if phases.r4_gap_candidates else [],
            # Cycle context
            cycle_id=envelope.context.cycle_id,
            tenant_id=envelope.context.tenant_id,
            space_id=envelope.context.space_id,
            cycle_start_ms=envelope.context.triggered_at,
        )

    def _extract_event_states(
        self,
        envelope: P03BatchEnvelope,
    ) -> Dict[str, P03EventState]:
        """Extract event states from envelope."""
        return {e.event_id: e for e in envelope.events}

    def _extract_phase_outputs(self, envelope: P03BatchEnvelope) -> Any:
        """Extract phase outputs from envelope."""
        return envelope.phases

    def _extract_gaps(self, envelope: P03BatchEnvelope) -> list:
        """Extract gap candidates from envelope."""
        # Gaps come from R5 if present
        r5_outputs = getattr(envelope.phases, "r5", None)
        if r5_outputs:
            gaps = getattr(r5_outputs, "gaps", None)
            if gaps:
                return list(gaps)
        return []

    def _extract_batch_event_ids(self, envelope: P03BatchEnvelope) -> Set[str]:
        """Extract batch event IDs from envelope."""
        return {e.event_id for e in envelope.events}

    def _extract_dedup_results(
        self,
        envelope: P03BatchEnvelope,
    ) -> Optional[Dict[str, DuplicationResult]]:
        """Extract dedup results from R3 outputs."""
        # Primary location: r3_dedup_results (new canonical location)
        if envelope.phases.r3_dedup_results:
            return dict(envelope.phases.r3_dedup_results)

        # Legacy fallback: r3.dedup_results (for backwards compatibility)
        r3_outputs = getattr(envelope.phases, "r3", None)
        if r3_outputs:
            dedup_results = getattr(r3_outputs, "dedup_results", None)
            if dedup_results:
                return dict(dedup_results)
        return None

    def _extract_phase_durations(
        self,
        envelope: P03BatchEnvelope,
    ) -> Optional[Dict[str, int]]:
        """Extract phase durations from envelope for completion event."""
        durations: Dict[str, int] = {}

        for phase_id in P03PhaseId:
            result = getattr(envelope.phases, phase_id.value.lower(), None)
            if result and hasattr(result, "duration_ms"):
                durations[phase_id.value] = result.duration_ms

        return durations if durations else None

    # =========================================================================
    # RESULT HANDLING
    # =========================================================================

    def _handle_failure(
        self,
        result: R6CoordinatorResult,
        cycle_id: str,
        start_ms: int,
    ) -> P03PhaseResult:
        """
        Handle R6 coordinator failure.

        Args:
            result: Failed coordinator result
            cycle_id: Cycle identifier
            start_ms: Phase start time

        Returns:
            P03PhaseResult.fail
        """
        duration_ms = int(time.time() * 1000) - start_ms

        return P03PhaseResult.fail(
            phase_id=self.PHASE_ID,
            error=P03Error(
                error_id=f"r6-{cycle_id}",
                phase="R6",
                stage_id="staging",
                error_type="R6_COORDINATOR_ERROR",
                error_message=result.error or "R6 coordinator failed",
                recoverable=True,
            ),
            duration_ms=duration_ms,
            idempotency_key=f"p03:r6:{cycle_id}",
        )

    def _populate_envelope(
        self,
        envelope: P03BatchEnvelope,
        result: R6CoordinatorResult,
    ) -> None:
        """
        Populate envelope.staged with R6Output — Issue 5.1.15.

        Routes all R6 outputs to the appropriate containers:
        - Truth writes → envelope.staged (by layer)
        - KG writes → envelope.staged (by layer)
        - Outbox events → envelope.staged.outbox_events
        - Event updates → envelope.staged.st_hipp_events_updates
        - Summary → envelope.phases.r6_summary

        Args:
            envelope: Batch envelope to populate
            result: Successful coordinator result
        """
        if not result.r6_output:
            return

        r6_output = result.r6_output

        # Add staged writes to envelope (routed by layer)
        for write in r6_output.staged_truth_writes:
            envelope.staged.add_write(write)

        for write in r6_output.staged_kg_writes:
            envelope.staged.add_write(write)

        # Add outbox events to envelope (directly append to the list)
        for event in r6_output.staged_outbox_events:
            envelope.staged.outbox_events.append(event)

        # Convert event updates to StagedWrite and add to st_hipp_events_updates
        for update in r6_output.staged_event_updates:
            write = self._event_update_to_staged_write(update)
            envelope.staged.st_hipp_events_updates.append(write)

        # Store R6 summary in phase_outputs
        envelope.phases.r6_summary = r6_output.reconciliation_summary

    def _event_update_to_staged_write(
        self,
        update: StagedEventUpdate,
    ) -> Any:
        """
        Convert StagedEventUpdate to StagedWrite for st_hipp_events — Issue 5.1.15.

        Uses the to_staged_write() method on StagedEventUpdate which
        creates an UPDATE operation for st_hipp_events.

        Args:
            update: StagedEventUpdate from R6Coordinator

        Returns:
            StagedWrite configured for UPDATE on st_hipp_events
        """
        return update.to_staged_write(phase="R6")

    def _build_outputs_summary(
        self,
        result: R6CoordinatorResult,
    ) -> Dict[str, Any]:
        """
        Build outputs summary for P03PhaseResult.

        Args:
            result: Successful coordinator result

        Returns:
            Dict with summary metrics
        """
        if not result.r6_output:
            return {"status": "empty"}

        r6_output = result.r6_output
        summary = r6_output.reconciliation_summary

        return {
            "total_events": summary.total_events,
            "consolidated_count": summary.consolidated_count,
            "duplicate_count": summary.duplicate_count,
            "pruned_count": summary.pruned_count,
            "gap_count": summary.gap_count,
            "event_updates": len(r6_output.staged_event_updates),
            "truth_writes": len(r6_output.staged_truth_writes),
            "kg_writes": len(r6_output.staged_kg_writes),
            "outbox_events": len(r6_output.staged_outbox_events),
            "validation_passed": (
                result.validation_result.is_valid if result.validation_result else None
            ),
            "step_durations_ms": result.step_durations_ms,
        }


# =============================================================================
# FACTORY FUNCTION
# =============================================================================


def create_r6_phase(
    config: Optional[R6CoordinatorConfig] = None,
) -> R6Staging:
    """
    Factory function to create R6Staging phase.

    Args:
        config: Optional configuration for coordinator

    Returns:
        Configured R6Staging instance
    """
    return R6Staging(config=config)
