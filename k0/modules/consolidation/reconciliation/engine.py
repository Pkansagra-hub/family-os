"""ReconciliationFramework -- 6-stage decision pipeline (M9.4).

Stateless decision machine. No DB reads. No DB writes.
All state comes from arguments. ``decide()`` is the only decision path.

Stages:
    1. K1 Signal Check (Tier 1) -- correction/contradiction override
    2. Override Check -- duplicate/prune short-circuit
    3. Identity Filter -- filter existing records by identity compatibility
    4. Similarity Rank -- cosine similarity on compatible subset
    5. Threshold Decision -- per-layer thresholds from TruthLayerSpec
    6. Result Assembly -- build ReconciliationResult with hooks + confidence
"""

from __future__ import annotations

import math
import time
from collections.abc import Sequence

import numpy as np

from k0.modules.consolidation.identity import IdentityStrategy
from k0.modules.consolidation.reconciliation.confidence import ConfidenceModel
from k0.modules.consolidation.reconciliation.result import ReconciliationResult
from k0.modules.consolidation.truth_layer_registry import (
    ReconciliationThresholds,
    TruthLayerRegistry,
)
from k0.modules.consolidation.types import ReconciliationCandidate, TruthRecord
from k0.pipelines.p03.event_state import ReconciliationAction

# ---------------------------------------------------------------------------
# Internal helpers (pure functions, no side effects)
# ---------------------------------------------------------------------------


def _to_array(embedding: list[float] | None) -> np.ndarray | None:
    """Convert list[float] to L2-normalized ndarray, or return None."""
    if embedding is None or len(embedding) == 0:
        return None
    arr = np.asarray(embedding, dtype=np.float64)
    norm = np.linalg.norm(arr)
    if norm == 0.0:
        return arr
    return arr / norm


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two L2-normalized vectors."""
    val = float(np.dot(a, b))
    if math.isnan(val):
        return 0.0
    return max(0.0, min(1.0, val))


# ---------------------------------------------------------------------------
# Stage 1: K1 Signal Check
# ---------------------------------------------------------------------------


def _check_k1_signals(
    candidate: ReconciliationCandidate,
    layer: str,
) -> ReconciliationResult | None:
    """Tier 1 override for correction/contradiction signals."""
    signals = candidate.k1_signals
    if signals is None:
        return None

    if signals.correction_signal:
        return ReconciliationResult(
            action=ReconciliationAction.EVOLVE,
            tier=1,
            match_id=None,
            match_layer=layer,
            similarity=0.0,
            identity_match=False,
            confidence=0.95,
            reason=(
                f"K1_CORRECTION: correction_source={signals.correction_source}, "
                f"session={signals.session_context_id}"
            ),
            candidate_id=candidate.candidate_id,
            layer=layer,
            cycle_id=candidate.cycle_id,
            hooks_required=["archive_superseded"],
        )

    if signals.contradiction_signal:
        return ReconciliationResult(
            action=ReconciliationAction.CONTRADICT,
            tier=1,
            match_id=None,
            match_layer=layer,
            similarity=0.0,
            identity_match=False,
            confidence=0.90,
            reason=(
                f"K1_CONTRADICTION: supersedes_concept={signals.supersedes_concept}, "
                f"correction_source={signals.correction_source}"
            ),
            candidate_id=candidate.candidate_id,
            layer=layer,
            cycle_id=candidate.cycle_id,
            hooks_required=[],
            contradiction_details={
                "correction_source": signals.correction_source,
                "supersedes_concept": signals.supersedes_concept,
                "session_context_id": signals.session_context_id,
            },
        )

    return None


# ---------------------------------------------------------------------------
# Stage 2: Override Check
# ---------------------------------------------------------------------------


def _check_overrides(
    candidate: ReconciliationCandidate,
    layer: str,
) -> ReconciliationResult | None:
    """Tier 2 override for duplicates and prune/tombstone."""
    meta = candidate.metadata

    if meta.get("is_duplicate") is True:
        duplicate_of = meta.get("duplicate_of_id", "unknown")
        return ReconciliationResult(
            action=ReconciliationAction.SKIP,
            tier=2,
            match_id=None,
            match_layer=layer,
            similarity=0.0,
            identity_match=False,
            confidence=1.0,
            reason=f"OVERRIDE_SKIP: duplicate_of={duplicate_of}",
            candidate_id=candidate.candidate_id,
            layer=layer,
            cycle_id=candidate.cycle_id,
            hooks_required=[],
        )

    if meta.get("prune_decision") == "TOMBSTONE":
        return ReconciliationResult(
            action=ReconciliationAction.PRUNE,
            tier=2,
            match_id=None,
            match_layer=layer,
            similarity=0.0,
            identity_match=False,
            confidence=1.0,
            reason="OVERRIDE_PRUNE: prune_decision=TOMBSTONE",
            candidate_id=candidate.candidate_id,
            layer=layer,
            cycle_id=candidate.cycle_id,
            hooks_required=[],
        )

    return None


# ---------------------------------------------------------------------------
# Stage 3: Identity Filter
# ---------------------------------------------------------------------------


def _filter_by_identity(
    candidate: ReconciliationCandidate,
    records: list[TruthRecord],
    identity: IdentityStrategy | None,
) -> list[TruthRecord]:
    """Return records that are identity-compatible with the candidate.

    If no identity strategy is provided, all records pass.
    Uses ``match_key()`` for key-based layers and ``score_identity()``
    for embedding-based layers.
    """
    if identity is None or not records:
        return list(records)

    compatible: list[TruthRecord] = []
    for record in records:
        key_result = identity.match_key(candidate, record)
        if key_result is True:
            compatible.append(record)
        elif key_result is False:
            continue
        else:
            # None = inconclusive, use score_identity heuristic
            # For embedding-based layers, accept records where the model
            # does not strongly recommend CREATE
            result = identity.score_identity(candidate, record, 0.0)
            if result.recommended_action != "CREATE":
                compatible.append(record)

    return compatible


# ---------------------------------------------------------------------------
# Stage 4: Similarity Rank
# ---------------------------------------------------------------------------


def _rank_by_similarity(
    candidate_embedding: list[float] | None,
    compatible: list[TruthRecord],
) -> tuple[TruthRecord, float]:
    """Find the best-matching record by cosine similarity.

    Returns the best-match record and its similarity score.
    If candidate has no embedding, returns the first record with sim=0.0.
    """
    cand_arr = _to_array(candidate_embedding)
    if cand_arr is None:
        return compatible[0], 0.0

    best_record = compatible[0]
    best_sim = 0.0

    for record in compatible:
        rec_arr = _to_array(record.embedding)
        if rec_arr is None:
            continue
        sim = _cosine_similarity(cand_arr, rec_arr)
        if sim > best_sim:
            best_sim = sim
            best_record = record

    return best_record, best_sim


# ---------------------------------------------------------------------------
# Stage 5: Threshold Decision
# ---------------------------------------------------------------------------


def _apply_thresholds(
    similarity: float,
    thresholds: ReconciliationThresholds,
) -> ReconciliationAction:
    """Map similarity score to action using per-layer thresholds."""
    if similarity >= thresholds.reinforce:
        return ReconciliationAction.REINFORCE
    if similarity >= thresholds.extend:
        return ReconciliationAction.EXTEND
    if similarity >= thresholds.evolve:
        return ReconciliationAction.EVOLVE
    return ReconciliationAction.CREATE


# ---------------------------------------------------------------------------
# Stage 6: Result Assembly
# ---------------------------------------------------------------------------


def _compute_hooks(action: ReconciliationAction) -> list[str]:
    """Determine post-decision hooks based on action."""
    if action == ReconciliationAction.REINFORCE:
        return ["recompute_centroid"]
    if action == ReconciliationAction.EXTEND:
        return ["recompute_centroid", "regenerate_summary"]
    if action == ReconciliationAction.EVOLVE:
        return ["archive_superseded", "recompute_centroid", "regenerate_summary"]
    if action == ReconciliationAction.CREATE:
        return ["recompute_centroid", "regenerate_summary"]
    return []


def _build_reason(
    action: ReconciliationAction,
    similarity: float,
    best_match: TruthRecord | None,
    layer: str,
    thresholds: ReconciliationThresholds,
    compatible_count: int,
    total_count: int,
) -> str:
    """Build structured reason string for the decision."""
    match_id = best_match.record_id if best_match else "None"

    if action == ReconciliationAction.REINFORCE:
        return (
            f"REINFORCE: sim={similarity:.4f} >= threshold={thresholds.reinforce:.2f}, "
            f"match={match_id}, layer={layer}, compatible={compatible_count}/{total_count}"
        )
    if action == ReconciliationAction.EXTEND:
        return (
            f"EXTEND: sim={similarity:.4f} >= threshold={thresholds.extend:.2f}, "
            f"match={match_id}, layer={layer}, compatible={compatible_count}/{total_count}"
        )
    if action == ReconciliationAction.EVOLVE:
        return (
            f"EVOLVE: sim={similarity:.4f} >= threshold={thresholds.evolve:.2f}, "
            f"match={match_id}, layer={layer}, compatible={compatible_count}/{total_count}"
        )
    # CREATE: below evolve threshold or no compatible records
    return (
        f"CREATE: sim={similarity:.4f} < evolve_threshold={thresholds.evolve:.2f}, "
        f"best_match={match_id}, layer={layer}, compatible={compatible_count}/{total_count}"
    )


def _finalize(
    result: ReconciliationResult,
    t0: float,
) -> ReconciliationResult:
    """Set decision_time_ms on a pre-built result."""
    elapsed = (time.perf_counter() - t0) * 1000.0
    object.__setattr__(result, "decision_time_ms", elapsed)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class ReconciliationFramework:
    """Stateless decision machine. No DB reads. No DB writes.

    All state comes from arguments. ``decide()`` is the only decision path.
    """

    @staticmethod
    def decide(
        candidate: ReconciliationCandidate,
        layer: str,
        registry: TruthLayerRegistry,
        existing_records: list[TruthRecord],
        identity_strategy: IdentityStrategy | None = None,
    ) -> ReconciliationResult:
        """6-stage decision pipeline. Pure function.

        Args:
            candidate: The item to reconcile (from R2/R3/R4).
            layer: Target truth layer ("st_epi", "st_sem", etc.).
            registry: M9.1 TruthLayerRegistry (provides thresholds).
            existing_records: Pre-fetched truth records from M9.3.
            identity_strategy: Optional M9.2 IdentityStrategy for the
                target layer. When ``None``, identity filtering is skipped
                (all records are considered compatible).

        Returns:
            ReconciliationResult with action, match, confidence, hooks.
        """
        t0 = time.perf_counter()
        spec = registry.get(layer)

        # Stage 1: K1 Signal Check (Tier 1)
        result = _check_k1_signals(candidate, layer)
        if result is not None:
            return _finalize(result, t0)

        # Stage 2: Override Check
        result = _check_overrides(candidate, layer)
        if result is not None:
            return _finalize(result, t0)

        # Stage 3: Identity Filter
        compatible = _filter_by_identity(candidate, existing_records, identity_strategy)

        if not compatible:
            conf = ConfidenceModel.compute(
                action=ReconciliationAction.CREATE,
                similarity=0.0,
                compatible_count=0,
                total_candidates=len(existing_records),
                identity_match=False,
            )
            return _finalize(
                ReconciliationResult(
                    action=ReconciliationAction.CREATE,
                    tier=2,
                    match_id=None,
                    match_layer=layer,
                    similarity=0.0,
                    identity_match=False,
                    confidence=conf,
                    reason=(
                        f"IDENTITY_FILTER: 0/{len(existing_records)} candidates "
                        f"identity-compatible -> CREATE"
                    ),
                    candidate_id=candidate.candidate_id,
                    layer=layer,
                    cycle_id=candidate.cycle_id,
                    hooks_required=["recompute_centroid", "regenerate_summary"],
                ),
                t0,
            )

        # Stage 4: Similarity Rank
        best_match, best_sim = _rank_by_similarity(candidate.embedding, compatible)

        # Stage 5: Threshold Decision
        action = _apply_thresholds(best_sim, spec.thresholds)

        # Stage 6: Result Assembly
        hooks = _compute_hooks(action)
        conf = ConfidenceModel.compute(
            action=action,
            similarity=best_sim,
            compatible_count=len(compatible),
            total_candidates=len(existing_records),
            identity_match=True,
        )
        reason = _build_reason(
            action,
            best_sim,
            best_match,
            layer,
            spec.thresholds,
            len(compatible),
            len(existing_records),
        )

        return _finalize(
            ReconciliationResult(
                action=action,
                tier=2,
                match_id=best_match.record_id if action != ReconciliationAction.CREATE else None,
                match_layer=layer,
                similarity=best_sim,
                identity_match=True,
                confidence=conf,
                reason=reason,
                candidate_id=candidate.candidate_id,
                layer=layer,
                cycle_id=candidate.cycle_id,
                hooks_required=hooks,
            ),
            t0,
        )

    @staticmethod
    def decide_batch(
        candidates: Sequence[ReconciliationCandidate],
        layer: str,
        registry: TruthLayerRegistry,
        existing_records: list[TruthRecord],
        identity_strategy: IdentityStrategy | None = None,
    ) -> dict[str, ReconciliationResult]:
        """Batch decision: same pre-fetched records, N candidates.

        The caller is responsible for calling truth_candidates_query (M9.3)
        ONCE for (layer, space_id, tenant_id) and passing the result here.

        Args:
            candidates: Batch of items to reconcile.
            layer: Target truth layer.
            registry: M9.1 registry.
            existing_records: Pre-fetched records (shared across candidates).
            identity_strategy: Optional M9.2 IdentityStrategy.

        Returns:
            Dict[candidate_id -> ReconciliationResult].
        """
        results: dict[str, ReconciliationResult] = {}
        for candidate in candidates:
            result = ReconciliationFramework.decide(
                candidate=candidate,
                layer=layer,
                registry=registry,
                existing_records=existing_records,
                identity_strategy=identity_strategy,
            )
            results[candidate.candidate_id] = result
        return results
