"""ContradictHandler -- learning queue entry for CONTRADICT action (M9.5).

CONTRADICT does NOT modify truth tables.  It inserts a gap record into
``st_learning_queue`` for P06 active learning resolution.
"""

from __future__ import annotations

import json
import time
from typing import Any

from k0.modules.consolidation.reconciliation.idem import RouterIdempotencyKey
from k0.modules.consolidation.reconciliation.result import ReconciliationResult
from k0.modules.consolidation.types import ReconciliationCandidate
from k0.pipelines.p03.context import generate_ulid
from k0.pipelines.p03.staged_writes import StagedWrite, WriteOperation


def _now_ms() -> int:
    return int(time.time() * 1000)


class ContradictHandler:
    """Handles CONTRADICT: INSERT gap into st_learning_queue."""

    @staticmethod
    def build_learning_queue_entry(
        result: ReconciliationResult,
        candidate: ReconciliationCandidate,
        cycle_id: str,
    ) -> StagedWrite:
        queue_id = generate_ulid()

        record_data: dict[str, Any] = {
            "queue_id": queue_id,
            "gap_type": "CONTRADICTION",
            "target_layer": result.match_layer,
            "target_id": result.match_id,
            "contradicting_event_ids": list(candidate.source_event_ids),
            "similarity": result.similarity,
            "confidence": result.confidence,
            "context_json": _build_contradiction_context(result, candidate),
            "status": "PENDING",
            "priority": 80,
            "created_at_ms": _now_ms(),
            "tenant_id": candidate.tenant_id,
            "space_id": candidate.space_id,
        }

        return StagedWrite(
            write_id=generate_ulid(),
            layer="st_learning_queue",
            operation=WriteOperation.INSERT,
            record_id=queue_id,
            record_data=record_data,
            idempotency_key=RouterIdempotencyKey.for_write(
                cycle_id,
                "st_learning_queue",
                queue_id,
                "contradict",
            ),
            source_phase=candidate.source_phase,
            source_event_ids=list(candidate.source_event_ids),
            expected_version=None,
        )


def _build_contradiction_context(
    result: ReconciliationResult,
    candidate: ReconciliationCandidate,
) -> str:
    """Build context JSON for P06 review."""
    ctx: dict[str, Any] = {
        "contradiction_reason": result.reason,
        "tier": result.tier,
    }
    if result.contradiction_details:
        ctx["correction_source"] = result.contradiction_details.get("correction_source")
        ctx["supersedes_concept"] = result.contradiction_details.get("supersedes_concept")
        ctx["session_context_id"] = result.contradiction_details.get("session_context_id")
    return json.dumps(ctx)
