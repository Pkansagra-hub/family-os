"""Structured decision log -- one JSON line per reconciliation (M9.4).

Uses stdlib ``logging`` (the codebase standard) with structured fields
that align with ``PhaseTransitionEvent`` for cross-phase correlation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from k0.modules.consolidation.reconciliation.result import ReconciliationResult

logger = logging.getLogger("k0.reconciliation")


def log_decision(result: ReconciliationResult) -> None:
    """Emit one structured log line per decision."""
    logger.info(
        "reconciliation_decision",
        extra={
            "cycle_id": result.cycle_id,
            "candidate_id": result.candidate_id,
            "layer": result.layer,
            "action": result.action.value,
            "tier": result.tier,
            "similarity": round(result.similarity, 4),
            "confidence": round(result.confidence, 4),
            "match_id": result.match_id,
            "identity_match": result.identity_match,
            "hooks": result.hooks_required,
            "reason": result.reason,
            "decision_time_ms": round(result.decision_time_ms, 2),
        },
    )
