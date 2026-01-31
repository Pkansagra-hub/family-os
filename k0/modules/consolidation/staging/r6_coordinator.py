"""
R6Coordinator — Issue 5.1.11

Orchestrates all R6 sub-components into a coherent staging phase.

Spec Reference:
    - Dossier §4.7 (R6 — Staging Table Updates)
    - Dossier Appendix G R6 (R6 phase contract)
    - M5_EXECUTION.md Issue 5.1.11

Execution Flow:
    1. Mark consolidation status for all events
    2. Populate dedup metadata
    3. Record reconciliation decisions
    4. Assemble truth layer writes
    5. Assemble KG writes
    6. Assemble outbox events
    7. Generate reconciliation summary
    8. Validate manifest
    9. Return R6Output (or raise on validation failure)

Sub-Components:
    - ConsolidationStatusMarker (5.1.2)
    - DedupMetadataPopulator (5.1.3)
    - ReconciliationRecorder (5.1.4)
    - IdempotencyKeyGenerator (5.1.5)
    - TruthWriteAssembler (5.1.6)
    - KGWriteAssembler (5.1.7)
    - OutboxEventAssembler (5.1.8)
    - ManifestValidator (5.1.9)
    - SummaryGenerator (5.1.10)

TIMESTAMP CONVENTION: All *_ms fields use MILLISECONDS since epoch.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from k0.modules.consolidation.staging.dedup_metadata import (
    DedupMetadataPopulator,
    DuplicationResult,
)
from k0.modules.consolidation.staging.idempotency import IdempotencyKeyGenerator
from k0.modules.consolidation.staging.intent_signal_assembler import (
    IntentSignalAssembler,
)
from k0.modules.consolidation.staging.kg_write_assembler import KGWriteAssembler
from k0.modules.consolidation.staging.manifest_validator import (
    ManifestValidationResult,
    ManifestValidator,
)
from k0.modules.consolidation.staging.outbox_assembler import OutboxEventAssembler
from k0.modules.consolidation.staging.r6_output import R6Output, StagedEventUpdate
from k0.modules.consolidation.staging.reconciliation_recorder import (
    ReconciliationRecorder,
)
from k0.modules.consolidation.staging.status_marker import ConsolidationStatusMarker
from k0.modules.consolidation.staging.summary_generator import SummaryGenerator
from k0.modules.consolidation.staging.truth_write_assembler import TruthWriteAssembler
from k0.pipelines.p03.event_state import P03EventState
from k0.pipelines.p03.phase_outputs import GapCandidate
from k0.pipelines.p03.staged_writes import StagedWrite

# =============================================================================
# HELPER
# =============================================================================


def _now_ms() -> int:
    """Return current time in milliseconds since epoch."""
    return int(time.time() * 1000)


# =============================================================================
# COORDINATOR CONFIG
# =============================================================================


@dataclass
class R6CoordinatorConfig:
    """
    Configuration for R6Coordinator.

    Attributes:
        dry_run: If True, skip actual database writes
        validate_manifest: If True, run manifest validation
        emit_metrics: If True, emit metrics during execution
    """

    dry_run: bool = False
    validate_manifest: bool = True
    emit_metrics: bool = True


# =============================================================================
# COORDINATOR RESULT
# =============================================================================


@dataclass
class R6CoordinatorResult:
    """
    Result from R6Coordinator.execute().

    Attributes:
        success: Whether R6 completed successfully
        r6_output: The R6Output if successful
        validation_result: Manifest validation result
        error: Error message if failed
        phase_duration_ms: Time taken for R6 phase
        step_durations_ms: Duration per sub-step
    """

    success: bool = True
    r6_output: Optional[R6Output] = None
    validation_result: Optional[ManifestValidationResult] = None
    error: Optional[str] = None
    phase_duration_ms: int = 0
    step_durations_ms: Dict[str, int] = field(default_factory=dict)


# =============================================================================
# R6 COORDINATOR
# =============================================================================


class R6Coordinator:
    """
    Orchestrates all R6 sub-components into staging phase.

    Coordinates status marking, dedup metadata, reconciliation recording,
    write assembly, outbox assembly, summary generation, and validation.

    Example:
        >>> coordinator = R6Coordinator.create(cycle_ulid, tenant_id, space_id)
        >>> result = coordinator.execute(
        ...     event_states=states,
        ...     phase_outputs=outputs,
        ...     gaps=gaps,
        ...     batch_event_ids=batch_ids,
        ... )
    """

    def __init__(
        self,
        status_marker: ConsolidationStatusMarker,
        dedup_populator: DedupMetadataPopulator,
        recon_recorder: ReconciliationRecorder,
        idempotency_gen: IdempotencyKeyGenerator,
        truth_assembler: TruthWriteAssembler,
        kg_assembler: KGWriteAssembler,
        outbox_assembler: OutboxEventAssembler,
        validator: ManifestValidator,
        summary_gen: SummaryGenerator,
        intent_signal_assembler: Optional[IntentSignalAssembler] = None,
        config: Optional[R6CoordinatorConfig] = None,
    ) -> None:
        """
        Initialize R6Coordinator with all sub-components.

        Args:
            status_marker: Marks consolidation status
            dedup_populator: Populates dedup metadata
            recon_recorder: Records reconciliation decisions
            idempotency_gen: Generates idempotency keys
            truth_assembler: Assembles truth layer writes
            kg_assembler: Assembles KG writes
            outbox_assembler: Assembles outbox events
            validator: Validates manifest before commit
            summary_gen: Generates reconciliation summary
            intent_signal_assembler: Optional assembler for intent signals (GAP-001)
            config: Optional coordinator configuration
        """
        self.status_marker = status_marker
        self.dedup_populator = dedup_populator
        self.recon_recorder = recon_recorder
        self.idempotency_gen = idempotency_gen
        self.truth_assembler = truth_assembler
        self.kg_assembler = kg_assembler
        self.outbox_assembler = outbox_assembler
        self.validator = validator
        self.summary_gen = summary_gen
        self.intent_signal_assembler = intent_signal_assembler
        self.config = config or R6CoordinatorConfig()

    @classmethod
    def create(
        cls,
        cycle_ulid: str,
        tenant_id: str = "",
        space_id: str = "",
        actor_id: str = "",
        existing_entity_ids: Optional[Set[str]] = None,
        config: Optional[R6CoordinatorConfig] = None,
    ) -> "R6Coordinator":
        """
        Factory method to create R6Coordinator with default components.

        Args:
            cycle_ulid: Cycle identifier
            tenant_id: Tenant identifier for outbox envelope
            space_id: Space identifier for outbox envelope
            actor_id: Actor identifier for provenance
            existing_entity_ids: Known entity IDs for FK validation
            config: Optional configuration

        Returns:
            Configured R6Coordinator instance
        """
        idempotency_gen = IdempotencyKeyGenerator(cycle_ulid)

        return cls(
            status_marker=ConsolidationStatusMarker(),
            dedup_populator=DedupMetadataPopulator(),
            recon_recorder=ReconciliationRecorder(),
            idempotency_gen=idempotency_gen,
            truth_assembler=TruthWriteAssembler(
                idempotency_gen,
                tenant_id=tenant_id,
                space_id=space_id,
                consolidation_cycle_id=cycle_ulid,
            ),
            kg_assembler=KGWriteAssembler(
                idempotency_gen,
                tenant_id=tenant_id,
                space_id=space_id,
            ),
            outbox_assembler=OutboxEventAssembler(cycle_ulid, tenant_id, space_id),
            validator=ManifestValidator(existing_entity_ids),
            summary_gen=SummaryGenerator(),
            intent_signal_assembler=IntentSignalAssembler(
                tenant_id=tenant_id,
                space_id=space_id,
                actor_id=actor_id,
            ),
            config=config,
        )

    def execute(
        self,
        event_states: Dict[str, P03EventState],
        phase_outputs: Any,  # P03PhaseOutputs or similar
        gaps: List[GapCandidate],
        batch_event_ids: Set[str],
        dedup_results: Optional[Dict[str, DuplicationResult]] = None,
        phase_durations: Optional[Dict[str, int]] = None,
        cycle_start_ms: int = 0,
    ) -> R6CoordinatorResult:
        """
        Execute full R6 staging workflow.

        Steps:
            1. Mark consolidation status for all events
            2. Populate dedup metadata
            3. Record reconciliation decisions
            4. Assemble truth layer writes
            5. Assemble KG writes
            6. Assemble outbox events
            7. Generate reconciliation summary
            8. Validate manifest
            9. Build and return R6Output

        Args:
            event_states: Map of event_id → P03EventState
            phase_outputs: Phase outputs from R1-R5
            gaps: Gap candidates from R5
            batch_event_ids: Set of all event IDs in batch
            dedup_results: Optional dedup results for metadata
            phase_durations: Duration per phase (for completion event)
            cycle_start_ms: Cycle start time for duration calculation

        Returns:
            R6CoordinatorResult with R6Output or error
        """
        start_ms = _now_ms()
        step_durations: Dict[str, int] = {}

        try:
            # === STEP 1: Build event updates ===
            step_start = _now_ms()
            event_updates = self._build_event_updates(
                event_states,
                dedup_results or {},
            )
            step_durations["build_event_updates"] = _now_ms() - step_start

            # === STEP 2: Assemble truth writes ===
            step_start = _now_ms()
            # Issue 8.1.17: Include R5 outputs in truth write assembly
            r5_insights = getattr(phase_outputs, "r5_insights", None) or []
            r5_counterfactuals = getattr(phase_outputs, "r5_counterfactuals", None) or []
            r5_routine_optimizations = (
                getattr(phase_outputs, "r5_routine_optimizations", None) or []
            )
            # GAP-003: Include routine candidates from RoutineDetector
            r5_routine_candidates = getattr(phase_outputs, "r5_routine_candidates", None) or []
            # MCTS scenarios from R5 DreamExplorer
            r5_mcts_scenarios = getattr(phase_outputs, "r5_mcts_scenarios", None) or []
            truth_assembly = self.truth_assembler.assemble_all(
                clusters=getattr(phase_outputs, "r2_clusters", None),
                event_states=event_states,
                routines=getattr(phase_outputs, "r5_routines", None),
                social_relationships=getattr(phase_outputs, "r4_social_entities", None),
                intentions=getattr(phase_outputs, "r5_intentions", None),
                gaps=gaps,
                # Issue 8.1.17: R5 outputs
                insights=r5_insights,
                counterfactuals=r5_counterfactuals,
                routine_optimizations=r5_routine_optimizations,
                # GAP-003: Routine candidates from RoutineDetector
                routine_candidates=r5_routine_candidates,
                # MCTS scenarios for st_mcts_decisions
                mcts_scenarios=r5_mcts_scenarios,
            )
            truth_writes = self._flatten_truth_writes(truth_assembly)
            step_durations["assemble_truth_writes"] = _now_ms() - step_start

            # === STEP 2.5: Assemble intent signal writes (GAP-001) ===
            step_start = _now_ms()
            r5_intent_signals = getattr(phase_outputs, "r5_intent_signals", None) or []
            intent_truth_writes: List[StagedWrite] = []
            intent_kg_writes: List[StagedWrite] = []
            if r5_intent_signals and self.intent_signal_assembler:
                intent_assembly = self.intent_signal_assembler.assemble_all(r5_intent_signals)
                # Route intent writes by layer: KG layers go to kg_writes, others to truth_writes
                from k0.pipelines.p03.staged_writes import (
                    LAYER_ST_KG_DOM,
                    LAYER_ST_KG_EDGES,
                )

                for layer, writes in intent_assembly.items():
                    if layer in (LAYER_ST_KG_DOM, LAYER_ST_KG_EDGES):
                        intent_kg_writes.extend(writes)
                    else:
                        intent_truth_writes.extend(writes)
                truth_writes = truth_writes + intent_truth_writes
            step_durations["assemble_intent_signals"] = _now_ms() - step_start

            # === STEP 3: Assemble KG writes ===
            step_start = _now_ms()
            entity_writes, edge_writes = self.kg_assembler.assemble_all(
                entities=getattr(phase_outputs, "r4_new_entities", None),
                entity_updates=getattr(phase_outputs, "r4_updated_entities", None),
                edges=getattr(phase_outputs, "r4_new_edges", None),
                edge_updates=getattr(phase_outputs, "r4_updated_edges", None),
                causal_edges=getattr(phase_outputs, "r4_causal_edges", None),
            )
            kg_writes = entity_writes + edge_writes + intent_kg_writes
            step_durations["assemble_kg_writes"] = _now_ms() - step_start

            # === STEP 4: Generate summary ===
            # Issue 8.1.12 / 8.1.17: Include R5 counts in summary
            step_start = _now_ms()
            cycle_duration = _now_ms() - cycle_start_ms if cycle_start_ms else 0
            summary_result = self.summary_gen.compute_with_writes(
                event_states=event_states,
                truth_writes=truth_writes,
                kg_writes=kg_writes,
                gap_count=len(gaps),
                insight_count=len(r5_insights),
                counterfactual_count=len(r5_counterfactuals),
                routine_optimization_count=len(r5_routine_optimizations)
                + len(r5_routine_candidates),
                cycle_duration_ms=cycle_duration,
            )
            step_durations["generate_summary"] = _now_ms() - step_start

            # === STEP 5: Assemble outbox events ===
            # Issue 8.1.12: Include R5 insights in outbox assembly
            step_start = _now_ms()
            outbox_assembly = self.outbox_assembler.assemble_all(
                summary=summary_result.summary,
                event_states=event_states,
                gaps=gaps,
                phase_durations=phase_durations or {},
                insights=r5_insights,
            )
            step_durations["assemble_outbox"] = _now_ms() - step_start

            # === STEP 6: Build R6Output ===
            step_start = _now_ms()
            # For empty batches, use cycle_ulid as fallback for idempotency key
            if batch_event_ids:
                r6_idem_key = self.idempotency_gen.for_batch_phase("R6", list(batch_event_ids))
            else:
                r6_idem_key = f"p03:R6:{self.idempotency_gen.cycle_ulid}:empty"
            r6_output = R6Output(
                cycle_ulid=self.idempotency_gen.cycle_ulid,
                batch_id=self._compute_batch_id(batch_event_ids),
                staged_event_updates=tuple(event_updates),
                staged_truth_writes=tuple(truth_writes),
                staged_kg_writes=tuple(kg_writes),
                staged_outbox_events=tuple(outbox_assembly.events),
                reconciliation_summary=summary_result.summary,
                created_at_ms=_now_ms(),
                r6_idempotency_key=r6_idem_key,
            )
            step_durations["build_r6_output"] = _now_ms() - step_start

            # === STEP 7: Validate manifest ===
            validation_result: Optional[ManifestValidationResult] = None
            if self.config.validate_manifest:
                step_start = _now_ms()
                validation_result = self.validator.validate(r6_output, batch_event_ids)
                step_durations["validate_manifest"] = _now_ms() - step_start

                if not validation_result.is_valid:
                    import logging

                    logger = logging.getLogger(__name__)
                    logger.error(
                        "R6 manifest validation failed",
                        extra={
                            "dlq_reason": validation_result.dlq_reason,
                            "errors": validation_result.errors,
                            "warnings": validation_result.warnings,
                            "stats": validation_result.stats,
                        },
                    )
                    return R6CoordinatorResult(
                        success=False,
                        r6_output=r6_output,
                        validation_result=validation_result,
                        error=f"Manifest validation failed: {validation_result.dlq_reason}",
                        phase_duration_ms=_now_ms() - start_ms,
                        step_durations_ms=step_durations,
                    )

            return R6CoordinatorResult(
                success=True,
                r6_output=r6_output,
                validation_result=validation_result,
                phase_duration_ms=_now_ms() - start_ms,
                step_durations_ms=step_durations,
            )

        except Exception as e:
            import logging
            import traceback

            logger = logging.getLogger(__name__)
            logger.exception(
                "R6Coordinator.execute() failed",
                extra={
                    "error": str(e),
                    "step_durations": step_durations,
                    "traceback": traceback.format_exc(),
                },
            )
            return R6CoordinatorResult(
                success=False,
                error=f"R6 execution failed: {str(e)}",
                phase_duration_ms=_now_ms() - start_ms,
                step_durations_ms=step_durations,
            )

    def _build_event_updates(
        self,
        event_states: Dict[str, P03EventState],
        dedup_results: Dict[str, DuplicationResult],
    ) -> List[StagedEventUpdate]:
        """
        Build all event updates for st_hipp_events.

        Combines status marking, dedup metadata, and reconciliation info.

        Args:
            event_states: Map of event_id → P03EventState
            dedup_results: Map of event_id → DuplicationResult

        Returns:
            List of StagedEventUpdate
        """
        updates: List[StagedEventUpdate] = []

        for event_id, state in event_states.items():
            # Get consolidation status
            status_result = self.status_marker.mark_status(state)

            # Get dedup metadata if available
            dedup_result = dedup_results.get(event_id)
            if dedup_result:
                dedup_meta = self.dedup_populator.from_duplication_result(state, dedup_result)
                near_duplicates_json = dedup_meta.near_duplicates_json
                novelty_score = dedup_meta.novelty_score
            else:
                near_duplicates_json = "[]"
                novelty_score = 1.0

            # Build update
            update = StagedEventUpdate(
                event_id=event_id,
                consolidation_status=status_result.status,
                near_duplicates_json=near_duplicates_json,
                novelty_score=novelty_score,
                episode_cluster_id=state.cluster_id,
                reconciliation_action=state.reconciliation_action.value,
                best_match_id=state.best_match_id,
                best_match_layer=state.best_match_layer,
                similarity_score=state.similarity_score,
                confidence=state.confidence,
                reconciliation_reason=state.reconciliation_reason,
                idempotency_key=self.idempotency_gen.for_event_update(event_id),
                version_conflict=state.version_conflict,
            )
            updates.append(update)

        return updates

    def _flatten_truth_writes(
        self,
        assembly: Dict[str, List[StagedWrite]],
    ) -> List[StagedWrite]:
        """
        Flatten dict of writes into flat list of StagedWrite.

        Deduplicates by (layer, record_id) to prevent manifest validation
        failures. When multiple writes target the same record, the last
        write wins (for UPDATEs, this aggregates the observation count).
        """
        writes: List[StagedWrite] = []
        seen: Dict[tuple, int] = {}  # (layer, record_id) -> index in writes

        for layer_writes in assembly.values():
            for write in layer_writes:
                key = (write.layer, write.record_id)
                if key in seen:
                    # Replace previous write (last-write-wins for updates)
                    writes[seen[key]] = write
                else:
                    seen[key] = len(writes)
                    writes.append(write)

        return writes

    def _compute_batch_id(self, event_ids: Set[str]) -> str:
        """
        Compute deterministic batch ID from event IDs.

        Args:
            event_ids: Set of event IDs

        Returns:
            Batch ID (hash of sorted event IDs)
        """
        import hashlib

        sorted_ids = sorted(event_ids)
        content = ":".join(sorted_ids)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def create_r6_coordinator(
    cycle_ulid: str,
    tenant_id: str = "",
    space_id: str = "",
    actor_id: str = "",
    existing_entity_ids: Optional[Set[str]] = None,
    dry_run: bool = False,
) -> R6Coordinator:
    """
    Convenience function to create R6Coordinator.

    Args:
        cycle_ulid: Cycle identifier
        tenant_id: Tenant identifier
        space_id: Space identifier
        actor_id: Actor identifier for provenance
        existing_entity_ids: Known entity IDs
        dry_run: Whether to run in dry-run mode

    Returns:
        Configured R6Coordinator
    """
    config = R6CoordinatorConfig(dry_run=dry_run)
    return R6Coordinator.create(
        cycle_ulid=cycle_ulid,
        tenant_id=tenant_id,
        space_id=space_id,
        actor_id=actor_id,
        existing_entity_ids=existing_entity_ids,
        config=config,
    )
