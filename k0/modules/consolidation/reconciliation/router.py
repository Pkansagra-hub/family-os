"""WriteDecisionRouter -- action-to-StagedWrite mapping (M9.5).

Data-driven mapping layer that converts a ``ReconciliationResult``
(from M9.4) into one or more ``StagedWrite`` objects ready for R7.
Reads merge rules from ``TruthLayerSpec`` (M9.1).  Zero knowledge
of column semantics -- all behaviour is driven by the YAML contracts.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from k0.modules.consolidation.reconciliation.contradict_handler import ContradictHandler
from k0.modules.consolidation.reconciliation.evolve_handler import EvolveHandler
from k0.modules.consolidation.reconciliation.idem import RouterIdempotencyKey
from k0.modules.consolidation.reconciliation.merge_engine import MergeEngine
from k0.modules.consolidation.reconciliation.result import ReconciliationResult
from k0.modules.consolidation.truth_layer_registry import TruthLayerSpec
from k0.modules.consolidation.types import ReconciliationCandidate
from k0.pipelines.p03.context import generate_ulid
from k0.pipelines.p03.event_state import ReconciliationAction
from k0.pipelines.p03.staged_writes import StagedWrite, WriteOperation

log = logging.getLogger(__name__)


def _now_ms() -> int:
    return int(time.time() * 1000)


class WriteDecisionRouter:
    """Data-driven mapping: ReconciliationResult -> StagedWrite(s).

    Reads merge rules from ``TruthLayerSpec``.  Zero knowledge of
    column semantics.
    """

    @staticmethod
    def build(
        result: ReconciliationResult,
        candidate: ReconciliationCandidate,
        spec: TruthLayerSpec,
        cycle_id: str,
    ) -> list[StagedWrite]:
        """Convert a reconciliation decision into write operations.

        Returns:
            List of StagedWrite objects (0 for SKIP, 1 for most, 2 for EVOLVE).
        """
        action = result.action

        if action == ReconciliationAction.SKIP:
            return []

        if action == ReconciliationAction.CREATE:
            return [_build_create(result, candidate, spec, cycle_id)]

        if action == ReconciliationAction.REINFORCE:
            return [_build_reinforce(result, candidate, spec, cycle_id)]

        if action == ReconciliationAction.EXTEND:
            return [_build_extend(result, candidate, spec, cycle_id)]

        if action == ReconciliationAction.EVOLVE:
            return EvolveHandler.build_evolve_pair(result, candidate, spec, cycle_id)

        if action == ReconciliationAction.CONTRADICT:
            return [
                ContradictHandler.build_learning_queue_entry(
                    result,
                    candidate,
                    cycle_id,
                )
            ]

        if action == ReconciliationAction.PRUNE:
            return [_build_prune(result, candidate, spec, cycle_id)]

        return []


# -----------------------------------------------------------------------
# Private builders
# -----------------------------------------------------------------------


def _build_create(
    result: ReconciliationResult,
    candidate: ReconciliationCandidate,
    spec: TruthLayerSpec,
    cycle_id: str,
) -> StagedWrite:
    record_data: dict[str, Any] = dict(candidate.metadata)
    record_id = record_data.get(spec.pk_column) or generate_ulid()
    record_data.setdefault(spec.pk_column, record_id)
    record_data.setdefault(spec.version_column, 1)
    record_data.setdefault(spec.observation_count_column, 1)
    record_data.setdefault(spec.archival_status_column, spec.active_status_value)
    record_data.setdefault(spec.canonical_column, True)

    return StagedWrite(
        write_id=generate_ulid(),
        layer=spec.layer_name,
        operation=WriteOperation.INSERT,
        record_id=record_id,
        record_data=record_data,
        idempotency_key=RouterIdempotencyKey.for_write(
            cycle_id,
            spec.layer_name,
            record_id,
            "create",
        ),
        source_phase=candidate.source_phase,
        source_event_ids=list(candidate.source_event_ids),
        expected_version=None,
    )


def _build_reinforce(
    result: ReconciliationResult,
    candidate: ReconciliationCandidate,
    spec: TruthLayerSpec,
    cycle_id: str,
) -> StagedWrite:
    match_id: str = result.match_id or ""
    record_data: dict[str, Any] = {
        spec.observation_count_column: 1,
    }
    if spec.temporal.last_observed:
        record_data[spec.temporal.last_observed] = _now_ms()

    strategy = spec.confidence_boost_strategy
    if strategy == "additive_0.05":
        record_data["_confidence_boost"] = 0.05
    elif strategy == "multiplicative_1.1":
        record_data["_confidence_boost_factor"] = 1.1

    return StagedWrite(
        write_id=generate_ulid(),
        layer=spec.layer_name,
        operation=WriteOperation.UPDATE,
        record_id=match_id,
        record_data=record_data,
        idempotency_key=RouterIdempotencyKey.for_write(
            cycle_id,
            spec.layer_name,
            match_id,
            "reinforce",
        ),
        source_phase=candidate.source_phase,
        source_event_ids=list(candidate.source_event_ids),
        expected_version=None,
    )


def _build_extend(
    result: ReconciliationResult,
    candidate: ReconciliationCandidate,
    spec: TruthLayerSpec,
    cycle_id: str,
) -> StagedWrite:
    match_id: str = result.match_id or ""
    record_data = MergeEngine.build_extend_data(
        spec=spec,
        candidate_data=candidate.metadata,
        existing_record_id=match_id,
    )

    return StagedWrite(
        write_id=generate_ulid(),
        layer=spec.layer_name,
        operation=WriteOperation.UPDATE,
        record_id=match_id,
        record_data=record_data,
        idempotency_key=RouterIdempotencyKey.for_write(
            cycle_id,
            spec.layer_name,
            match_id,
            "extend",
        ),
        source_phase=candidate.source_phase,
        source_event_ids=list(candidate.source_event_ids),
        expected_version=None,
    )


def _build_prune(
    result: ReconciliationResult,
    candidate: ReconciliationCandidate,
    spec: TruthLayerSpec,
    cycle_id: str,
) -> StagedWrite:
    is_tombstone = candidate.metadata.get("prune_decision") == "TOMBSTONE"
    operation = WriteOperation.TOMBSTONE if is_tombstone else WriteOperation.ARCHIVE

    record_data: dict[str, Any] = {
        spec.archival_status_column: "TOMBSTONE" if is_tombstone else "ARCHIVED",
    }
    if not is_tombstone:
        record_data["archived_reason"] = candidate.metadata.get(
            "prune_reason",
            "decay",
        )

    target_id = result.match_id or candidate.metadata.get(spec.pk_column, "")

    return StagedWrite(
        write_id=generate_ulid(),
        layer=spec.layer_name,
        operation=operation,
        record_id=target_id,
        record_data=record_data,
        idempotency_key=RouterIdempotencyKey.for_write(
            cycle_id,
            spec.layer_name,
            target_id,
            "prune",
        ),
        source_phase=candidate.source_phase,
        source_event_ids=list(candidate.source_event_ids),
        expected_version=None,
    )
