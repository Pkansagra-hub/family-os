"""EvolveHandler -- version chain for EVOLVE action (M9.5).

EVOLVE always produces exactly 2 StagedWrites:
  1. UPDATE old record -> SUPERSEDED (non-canonical)
  2. INSERT new canonical record with supersedes link
"""

from __future__ import annotations

import time
from typing import Any

from k0.modules.consolidation.reconciliation.idem import RouterIdempotencyKey
from k0.modules.consolidation.reconciliation.result import ReconciliationResult
from k0.modules.consolidation.truth_layer_registry import TruthLayerSpec
from k0.modules.consolidation.types import ReconciliationCandidate
from k0.pipelines.p03.context import generate_ulid
from k0.pipelines.p03.staged_writes import StagedWrite, WriteOperation


def _now_ms() -> int:
    return int(time.time() * 1000)


class EvolveHandler:
    """Handles EVOLVE: UPDATE old to SUPERSEDED + INSERT new canonical."""

    @staticmethod
    def build_evolve_pair(
        result: ReconciliationResult,
        candidate: ReconciliationCandidate,
        spec: TruthLayerSpec,
        cycle_id: str,
    ) -> list[StagedWrite]:
        """Always returns exactly ``[archive_old, insert_new]``."""
        old_record_id = result.match_id
        new_record_id = candidate.metadata.get(spec.pk_column) or generate_ulid()

        # Write 1: UPDATE old record -> SUPERSEDED
        archive_old = StagedWrite(
            write_id=generate_ulid(),
            layer=spec.layer_name,
            operation=WriteOperation.UPDATE,
            record_id=old_record_id,
            record_data={
                spec.canonical_column: False,
                spec.archival_status_column: "SUPERSEDED",
                "valid_to": _now_ms(),
                spec.version_column: 1,  # COUNTER: version++
            },
            idempotency_key=RouterIdempotencyKey.for_write(
                cycle_id,
                spec.layer_name,
                old_record_id,
                "evolve_archive",
            ),
            source_phase=candidate.source_phase,
            source_event_ids=list(candidate.source_event_ids),
            expected_version=None,
        )

        # Write 2: INSERT new canonical record
        new_data: dict[str, Any] = dict(candidate.metadata)
        new_data[spec.pk_column] = new_record_id
        new_data[spec.supersedes_column] = old_record_id
        new_data[spec.canonical_column] = True
        new_data[spec.version_column] = 1
        new_data[spec.observation_count_column] = 1
        new_data[spec.archival_status_column] = spec.active_status_value

        insert_new = StagedWrite(
            write_id=generate_ulid(),
            layer=spec.layer_name,
            operation=WriteOperation.INSERT,
            record_id=new_record_id,
            record_data=new_data,
            idempotency_key=RouterIdempotencyKey.for_write(
                cycle_id,
                spec.layer_name,
                new_record_id,
                "evolve_create",
            ),
            source_phase=candidate.source_phase,
            source_event_ids=list(candidate.source_event_ids),
            expected_version=None,
        )

        return [archive_old, insert_new]
