"""DualPathRunner -- feature-flagged migration harness (M9.8).

Runs both legacy (bespoke) and engine reconciliation paths in parallel
when ``dual_path_enabled=True``, logging divergences for validation.
When dual-path is off, runs whichever path the config flag selects.

Thread-safe, stateless, synchronous. No DB access.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from k0.modules.consolidation.reconciliation.result import ReconciliationResult
from k0.pipelines.p03.event_state import ReconciliationAction

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Divergence record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Divergence:
    """Single divergence between legacy and engine decisions."""

    candidate_id: str
    legacy_action: ReconciliationAction
    engine_action: ReconciliationAction
    legacy_match_id: str | None
    engine_match_id: str | None
    legacy_similarity: float
    engine_similarity: float
    reason: str


# ---------------------------------------------------------------------------
# DualPathResult
# ---------------------------------------------------------------------------


@dataclass
class DualPathResult:
    """Outcome of a dual-path run (or single-path if dual is off)."""

    # The authoritative result used downstream
    action: ReconciliationAction
    match_id: str | None = None
    match_similarity: float = 0.0
    match_version: int = 0
    confidence: float = 0.0
    reason: str = ""
    hooks_required: list[str] = field(default_factory=list)

    # Engine result (only populated when engine path ran)
    engine_result: ReconciliationResult | None = None

    # Divergence (only populated when dual-path ran and paths disagreed)
    divergence: Divergence | None = None

    @property
    def used_engine(self) -> bool:
        return self.engine_result is not None and self.divergence is None


# ---------------------------------------------------------------------------
# DualPathRunner
# ---------------------------------------------------------------------------


class DualPathRunner:
    """Run legacy and/or engine reconciliation and compare.

    Usage::

        runner = DualPathRunner(
            use_engine=config.enable_engine_reinforce,
            dual_path=config.engine_dual_path_enabled,
            log_divergences=config.engine_dual_path_log_divergences,
        )

        result = runner.run(
            candidate_id="evt_abc",
            legacy_fn=lambda: (action, match_id, sim, version, reason),
            engine_fn=lambda: engine_result,
        )
    """

    def __init__(
        self,
        *,
        use_engine: bool = False,
        dual_path: bool = False,
        log_divergences: bool = True,
    ) -> None:
        self._use_engine = use_engine
        self._dual_path = dual_path
        self._log_divergences = log_divergences

    def run(
        self,
        candidate_id: str,
        legacy_fn: Any,
        engine_fn: Any,
    ) -> DualPathResult:
        """Execute one or both paths and return the authoritative result.

        Args:
            candidate_id: Identifier for logging.
            legacy_fn: Callable returning
                ``(action, match_id, similarity, version, reason)``
                tuple from the bespoke path. Only called when needed.
            engine_fn: Callable returning ``ReconciliationResult``
                from the engine path. Only called when needed.

        Returns:
            DualPathResult with the authoritative decision.
        """
        if not self._use_engine and not self._dual_path:
            # Legacy-only
            action, match_id, sim, version, reason = legacy_fn()
            return DualPathResult(
                action=action,
                match_id=match_id,
                match_similarity=sim,
                match_version=version,
                reason=reason,
            )

        # Engine path (always runs when use_engine or dual_path)
        engine_result: ReconciliationResult = engine_fn()

        if not self._dual_path:
            # Engine-only
            return DualPathResult(
                action=engine_result.action,
                match_id=engine_result.match_id,
                match_similarity=engine_result.similarity,
                match_version=0,  # engine doesn't track version; caller resolves
                confidence=engine_result.confidence,
                reason=engine_result.reason,
                hooks_required=list(engine_result.hooks_required),
                engine_result=engine_result,
            )

        # Dual-path: run legacy too, compare
        action_l, match_l, sim_l, version_l, reason_l = legacy_fn()

        divergence: Divergence | None = None
        if action_l != engine_result.action or match_l != engine_result.match_id:
            divergence = Divergence(
                candidate_id=candidate_id,
                legacy_action=action_l,
                engine_action=engine_result.action,
                legacy_match_id=match_l,
                engine_match_id=engine_result.match_id,
                legacy_similarity=sim_l,
                engine_similarity=engine_result.similarity,
                reason=(
                    f"action: {action_l.value}!={engine_result.action.value}"
                    if action_l != engine_result.action
                    else f"match: {match_l}!={engine_result.match_id}"
                ),
            )
            if self._log_divergences:
                logger.warning(
                    "R2 engine divergence",
                    extra={
                        "candidate_id": candidate_id,
                        "legacy_action": action_l.value,
                        "engine_action": engine_result.action.value,
                        "legacy_match": match_l,
                        "engine_match": engine_result.match_id,
                        "legacy_sim": round(sim_l, 4),
                        "engine_sim": round(engine_result.similarity, 4),
                    },
                )

        # In dual-path mode, legacy is authoritative (safe rollout)
        return DualPathResult(
            action=action_l,
            match_id=match_l,
            match_similarity=sim_l,
            match_version=version_l,
            reason=reason_l,
            engine_result=engine_result,
            divergence=divergence,
        )
