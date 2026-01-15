"""
MCTS Shadow Validation — Heuristic vs MCTS comparison tracking.

This module implements the shadow validation loop for R5 decisions,
comparing heuristic choices with MCTS choices and tracking outcomes.

Issue Reference: M8_EXECUTION.md Issue 8.1.14
Dossier Reference: P03 Consolidation Dossier Section 4.6.0

Shadow Mode Behavior:
1. Compute heuristic choice (fast, deterministic)
2. Run MCTS (compute-intensive, probabilistic)
3. Apply heuristic choice (MCTS is read-only in shadow mode)
4. Log both to st_mcts_shadow_log for later evaluation

Promotion Logic:
- If agreement rate >95%: Keep disabled (MCTS not worth compute)
- If diff >20% AND MCTS better >55%: Promote to enabled_low

Evaluation Window: 7 days after decision creation

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from logging import getLogger
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from k0.pipelines.p03.context import generate_ulid

logger = getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

# Table name for shadow log
ST_MCTS_SHADOW_LOG_TABLE = "st_mcts_shadow_log"

# Evaluation window in milliseconds (7 days)
EVALUATION_WINDOW_MS = 7 * 24 * 60 * 60 * 1000  # 604800000 ms

# Promotion thresholds (from dossier)
P03_R5_SHADOW_DIFF_THRESHOLD = 0.20  # 20% difference threshold
P03_R5_SHADOW_AGREEMENT_THRESHOLD = 0.95  # 95% agreement = keep disabled
P03_R5_SHADOW_BETTER_THRESHOLD = 0.55  # 55% MCTS better = enable

# Default evaluation window in days
P03_R5_SHADOW_VALIDATION_WINDOW_DAYS = 30  # 30-day rolling window for analysis


# =============================================================================
# ENUMS
# =============================================================================


class ShadowDecisionType(str, Enum):
    """Types of decisions tracked in shadow mode."""

    MERGE = "merge"
    SPLIT = "split"
    CAUSAL = "causal"
    CLUSTER = "cluster"
    REINFORCE = "reinforce"
    DECAY = "decay"
    NOVELTY = "novelty"
    INSIGHT_RANKING = "insight_ranking"


class PromotionRecommendation(str, Enum):
    """Recommendation for R5 mode promotion."""

    KEEP_DISABLED = "keep_disabled"  # High agreement, MCTS not worth cost
    KEEP_SHADOW = "keep_shadow"  # Not enough data or inconclusive
    PROMOTE_ENABLED_LOW = "promote_enabled_low"  # MCTS proves valuable
    PROMOTE_ENABLED = "promote_enabled"  # Strong MCTS benefit


# =============================================================================
# DATA STRUCTURES
# =============================================================================


@dataclass(frozen=True)
class ShadowDecisionRecord:
    """
    Record of a shadow mode decision comparison.

    Immutable record capturing both heuristic and MCTS choices
    for later evaluation.

    Attributes:
        decision_id: ULID unique identifier
        cycle_id: Parent consolidation cycle ULID
        decision_type: Classification of the decision
        heuristic_choice: Action chosen by heuristic
        mcts_choice: Action chosen by MCTS
        choices_differ: Whether heuristic != mcts
        context: Rich context for analysis
        applied_choice: Choice actually applied (always heuristic)
        outcome_heuristic: Observed outcome (filled in after evaluation)
        outcome_mcts: Predicted MCTS outcome (filled in after evaluation)
        mcts_better: Whether MCTS would have been better
        evaluated_at_ms: When evaluation was performed
        created_at_ms: Creation timestamp
    """

    decision_id: str
    cycle_id: str
    decision_type: str
    heuristic_choice: str
    mcts_choice: str
    choices_differ: bool
    context: Dict[str, Any]
    applied_choice: str
    outcome_heuristic: Optional[float] = None
    outcome_mcts: Optional[float] = None
    mcts_better: Optional[bool] = None
    evaluated_at_ms: Optional[int] = None
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    @classmethod
    def create(
        cls,
        cycle_id: str,
        decision_type: ShadowDecisionType,
        heuristic_choice: str,
        mcts_choice: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> "ShadowDecisionRecord":
        """
        Factory method to create a new shadow decision record.

        In shadow mode, heuristic is always applied.

        Args:
            cycle_id: Parent consolidation cycle ULID
            decision_type: Type of decision
            heuristic_choice: Action chosen by heuristic
            mcts_choice: Action chosen by MCTS
            context: Additional context for analysis

        Returns:
            New ShadowDecisionRecord
        """
        return cls(
            decision_id=generate_ulid(),
            cycle_id=cycle_id,
            decision_type=decision_type.value,
            heuristic_choice=heuristic_choice,
            mcts_choice=mcts_choice,
            choices_differ=heuristic_choice != mcts_choice,
            context=context or {},
            applied_choice=heuristic_choice,  # Always heuristic in shadow mode
            created_at_ms=int(time.time() * 1000),
        )

    def to_db_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database insertion."""
        return {
            "decision_id": self.decision_id,
            "cycle_id": self.cycle_id,
            "decision_type": self.decision_type,
            "heuristic_choice": self.heuristic_choice,
            "mcts_choice": self.mcts_choice,
            "choices_differ": self.choices_differ,
            "context_json": json.dumps(self.context),
            "applied_choice": self.applied_choice,
            "outcome_heuristic": self.outcome_heuristic,
            "outcome_mcts": self.outcome_mcts,
            "mcts_better": self.mcts_better,
            "evaluated_at": self.evaluated_at_ms,
            "created_at": self.created_at_ms,
        }

    def with_evaluation(
        self,
        outcome_heuristic: float,
        outcome_mcts: float,
        mcts_better: bool,
    ) -> "ShadowDecisionRecord":
        """
        Create a new record with evaluation results.

        Args:
            outcome_heuristic: Observed heuristic outcome
            outcome_mcts: Predicted MCTS outcome
            mcts_better: Whether MCTS would have been better

        Returns:
            New record with evaluation filled in
        """
        return ShadowDecisionRecord(
            decision_id=self.decision_id,
            cycle_id=self.cycle_id,
            decision_type=self.decision_type,
            heuristic_choice=self.heuristic_choice,
            mcts_choice=self.mcts_choice,
            choices_differ=self.choices_differ,
            context=self.context,
            applied_choice=self.applied_choice,
            outcome_heuristic=outcome_heuristic,
            outcome_mcts=outcome_mcts,
            mcts_better=mcts_better,
            evaluated_at_ms=int(time.time() * 1000),
            created_at_ms=self.created_at_ms,
        )


@dataclass
class ShadowValidationStats:
    """
    Statistics from shadow validation analysis.

    Used for promotion decision logic.

    Attributes:
        total_decisions: Total decisions in evaluation window
        agreements: Decisions where heuristic == mcts
        disagreements: Decisions where heuristic != mcts
        mcts_better_count: Disagreements where MCTS was better
        heuristic_better_count: Disagreements where heuristic was better
        equal_count: Disagreements with equal outcomes
        unevaluated_count: Decisions pending evaluation
        window_days: Evaluation window in days
    """

    total_decisions: int = 0
    agreements: int = 0
    disagreements: int = 0
    mcts_better_count: int = 0
    heuristic_better_count: int = 0
    equal_count: int = 0
    unevaluated_count: int = 0
    window_days: int = P03_R5_SHADOW_VALIDATION_WINDOW_DAYS

    @property
    def agreement_rate(self) -> float:
        """Rate of agreement between heuristic and MCTS."""
        if self.total_decisions == 0:
            return 0.0
        return self.agreements / self.total_decisions

    @property
    def disagreement_rate(self) -> float:
        """Rate of disagreement between heuristic and MCTS."""
        if self.total_decisions == 0:
            return 0.0
        return self.disagreements / self.total_decisions

    @property
    def mcts_better_rate(self) -> float:
        """Rate at which MCTS is better when they disagree."""
        if self.disagreements == 0:
            return 0.0
        evaluated_disagreements = (
            self.mcts_better_count + self.heuristic_better_count + self.equal_count
        )
        if evaluated_disagreements == 0:
            return 0.0
        return self.mcts_better_count / evaluated_disagreements

    @property
    def has_sufficient_data(self) -> bool:
        """Check if we have enough data for promotion decision."""
        # Need at least 100 decisions and 10 evaluated disagreements
        min_decisions = 100
        min_disagreements = 10
        evaluated_disagreements = (
            self.mcts_better_count + self.heuristic_better_count + self.equal_count
        )
        return self.total_decisions >= min_decisions and evaluated_disagreements >= min_disagreements

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/metrics."""
        return {
            "total_decisions": self.total_decisions,
            "agreements": self.agreements,
            "disagreements": self.disagreements,
            "mcts_better_count": self.mcts_better_count,
            "heuristic_better_count": self.heuristic_better_count,
            "equal_count": self.equal_count,
            "unevaluated_count": self.unevaluated_count,
            "agreement_rate": self.agreement_rate,
            "disagreement_rate": self.disagreement_rate,
            "mcts_better_rate": self.mcts_better_rate,
            "has_sufficient_data": self.has_sufficient_data,
            "window_days": self.window_days,
        }


@dataclass
class PromotionAnalysis:
    """
    Analysis result with promotion recommendation.

    Attributes:
        recommendation: Promotion recommendation enum
        stats: Shadow validation statistics
        reasoning: Human-readable explanation
        thresholds_met: Which thresholds were met/not met
    """

    recommendation: PromotionRecommendation
    stats: ShadowValidationStats
    reasoning: str
    thresholds_met: Dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "recommendation": self.recommendation.value,
            "stats": self.stats.to_dict(),
            "reasoning": self.reasoning,
            "thresholds_met": self.thresholds_met,
        }


# =============================================================================
# PROTOCOLS
# =============================================================================


@runtime_checkable
class DatabaseConnection(Protocol):
    """Protocol for database connection (async)."""

    async def execute(self, query: str, params: Dict[str, Any]) -> Any: ...

    async def execute_many(self, query: str, params_list: List[Dict[str, Any]]) -> Any: ...

    async def fetch_one(self, query: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]: ...

    async def fetch_all(self, query: str, params: Dict[str, Any]) -> List[Dict[str, Any]]: ...


# =============================================================================
# SHADOW OUTCOME TRACKER
# =============================================================================


class ShadowOutcomeTracker:
    """
    Tracks and persists shadow mode decision comparisons.

    Main interface for Issue 8.1.14 shadow validation.

    Usage:
        tracker = ShadowOutcomeTracker(db_connection)

        # Record shadow decision
        record = ShadowDecisionRecord.create(
            cycle_id=cycle_id,
            decision_type=ShadowDecisionType.MERGE,
            heuristic_choice="merge_accept",
            mcts_choice="merge_reject",
            context={"entity_id": "ent_001"},
        )
        await tracker.record_decision(record)

        # Later: evaluate pending decisions
        await tracker.evaluate_pending_decisions(outcome_fn)

        # Get promotion recommendation
        analysis = await tracker.analyze_for_promotion()
        print(analysis.recommendation)
    """

    def __init__(self, db: Optional[DatabaseConnection] = None):
        """
        Initialize shadow outcome tracker.

        Args:
            db: Database connection (optional, can be set later)
        """
        self._db = db
        self._logger = getLogger(f"{__name__}.{self.__class__.__name__}")
        self._pending_records: List[ShadowDecisionRecord] = []

    def set_connection(self, db: DatabaseConnection) -> None:
        """Set database connection."""
        self._db = db

    async def record_decision(self, decision: ShadowDecisionRecord) -> str:
        """
        Record a shadow decision to the database.

        Args:
            decision: Shadow decision record

        Returns:
            decision_id of recorded decision
        """
        if self._db is None:
            self._logger.warning("No database connection, buffering decision")
            self._pending_records.append(decision)
            return decision.decision_id

        query = self._build_insert_query()
        params = decision.to_db_dict()

        try:
            await self._db.execute(query, params)
            self._logger.debug(
                "Recorded shadow decision",
                extra={
                    "decision_id": decision.decision_id,
                    "decision_type": decision.decision_type,
                    "choices_differ": decision.choices_differ,
                },
            )
            return decision.decision_id
        except Exception as e:
            self._logger.error(
                f"Failed to record shadow decision: {e}",
                extra={"decision_id": decision.decision_id},
            )
            raise

    async def record_decisions_batch(
        self,
        decisions: List[ShadowDecisionRecord],
    ) -> int:
        """
        Record multiple shadow decisions in batch.

        Args:
            decisions: List of shadow decision records

        Returns:
            Number of decisions recorded
        """
        if not decisions:
            return 0

        if self._db is None:
            self._logger.warning("No database connection, buffering decisions")
            self._pending_records.extend(decisions)
            return 0

        query = self._build_insert_query()
        params_list = [d.to_db_dict() for d in decisions]

        try:
            await self._db.execute_many(query, params_list)
            self._logger.debug(f"Recorded {len(decisions)} shadow decisions in batch")
            return len(decisions)
        except Exception as e:
            self._logger.error(f"Failed to record shadow decisions batch: {e}")
            raise

    async def flush_pending(self) -> int:
        """
        Flush pending decisions to database.

        Returns:
            Number of decisions flushed
        """
        if not self._pending_records:
            return 0

        if self._db is None:
            self._logger.warning("Cannot flush: no database connection")
            return 0

        count = await self.record_decisions_batch(self._pending_records)
        self._pending_records.clear()
        return count

    async def get_pending_evaluation_decisions(
        self,
        limit: int = 100,
    ) -> List[ShadowDecisionRecord]:
        """
        Get decisions pending evaluation (>7 days old, not yet evaluated).

        Args:
            limit: Maximum number of decisions to return

        Returns:
            List of decisions pending evaluation
        """
        if self._db is None:
            self._logger.warning("No database connection")
            return []

        # Calculate cutoff: 7 days ago
        cutoff_ms = int(time.time() * 1000) - EVALUATION_WINDOW_MS

        query = f"""
            SELECT *
            FROM {ST_MCTS_SHADOW_LOG_TABLE}
            WHERE evaluated_at IS NULL
              AND created_at <= :cutoff_ms
            ORDER BY created_at ASC
            LIMIT :limit
        """

        try:
            rows = await self._db.fetch_all(query, {"cutoff_ms": cutoff_ms, "limit": limit})
            return [self._row_to_record(row) for row in rows]
        except Exception as e:
            self._logger.error(f"Failed to fetch pending evaluations: {e}")
            return []

    async def update_evaluation(
        self,
        decision_id: str,
        outcome_heuristic: float,
        outcome_mcts: float,
        mcts_better: bool,
    ) -> bool:
        """
        Update a decision with evaluation results.

        Args:
            decision_id: Decision to update
            outcome_heuristic: Observed heuristic outcome
            outcome_mcts: Predicted MCTS outcome
            mcts_better: Whether MCTS would have been better

        Returns:
            True if update succeeded
        """
        if self._db is None:
            self._logger.warning("No database connection")
            return False

        query = f"""
            UPDATE {ST_MCTS_SHADOW_LOG_TABLE}
            SET outcome_heuristic = :outcome_heuristic,
                outcome_mcts = :outcome_mcts,
                mcts_better = :mcts_better,
                evaluated_at = :evaluated_at
            WHERE decision_id = :decision_id
        """

        params = {
            "decision_id": decision_id,
            "outcome_heuristic": outcome_heuristic,
            "outcome_mcts": outcome_mcts,
            "mcts_better": mcts_better,
            "evaluated_at": int(time.time() * 1000),
        }

        try:
            await self._db.execute(query, params)
            self._logger.debug(
                "Updated shadow decision evaluation",
                extra={
                    "decision_id": decision_id,
                    "mcts_better": mcts_better,
                },
            )
            return True
        except Exception as e:
            self._logger.error(f"Failed to update evaluation: {e}")
            return False

    async def get_stats_for_window(
        self,
        window_days: int = P03_R5_SHADOW_VALIDATION_WINDOW_DAYS,
        decision_type: Optional[str] = None,
    ) -> ShadowValidationStats:
        """
        Get shadow validation statistics for a time window.

        Args:
            window_days: Number of days to look back
            decision_type: Optional filter by decision type

        Returns:
            ShadowValidationStats with aggregated statistics
        """
        if self._db is None:
            self._logger.warning("No database connection")
            return ShadowValidationStats(window_days=window_days)

        # Calculate cutoff timestamp
        cutoff_ms = int(time.time() * 1000) - (window_days * 24 * 60 * 60 * 1000)

        # Build query with optional type filter
        type_filter = ""
        params: Dict[str, Any] = {"cutoff_ms": cutoff_ms}
        if decision_type:
            type_filter = "AND decision_type = :decision_type"
            params["decision_type"] = decision_type

        query = f"""
            SELECT
                COUNT(*) as total_decisions,
                SUM(CASE WHEN NOT choices_differ THEN 1 ELSE 0 END) as agreements,
                SUM(CASE WHEN choices_differ THEN 1 ELSE 0 END) as disagreements,
                SUM(CASE WHEN choices_differ AND mcts_better = true THEN 1 ELSE 0 END) as mcts_better_count,
                SUM(CASE WHEN choices_differ AND mcts_better = false THEN 1 ELSE 0 END) as heuristic_better_count,
                SUM(CASE WHEN choices_differ AND mcts_better IS NULL AND evaluated_at IS NOT NULL THEN 1 ELSE 0 END) as equal_count,
                SUM(CASE WHEN evaluated_at IS NULL THEN 1 ELSE 0 END) as unevaluated_count
            FROM {ST_MCTS_SHADOW_LOG_TABLE}
            WHERE created_at >= :cutoff_ms
              {type_filter}
        """

        try:
            row = await self._db.fetch_one(query, params)
            if row is None:
                return ShadowValidationStats(window_days=window_days)

            return ShadowValidationStats(
                total_decisions=row.get("total_decisions", 0) or 0,
                agreements=row.get("agreements", 0) or 0,
                disagreements=row.get("disagreements", 0) or 0,
                mcts_better_count=row.get("mcts_better_count", 0) or 0,
                heuristic_better_count=row.get("heuristic_better_count", 0) or 0,
                equal_count=row.get("equal_count", 0) or 0,
                unevaluated_count=row.get("unevaluated_count", 0) or 0,
                window_days=window_days,
            )
        except Exception as e:
            self._logger.error(f"Failed to get shadow stats: {e}")
            return ShadowValidationStats(window_days=window_days)

    async def get_stats_by_decision_type(
        self,
        window_days: int = P03_R5_SHADOW_VALIDATION_WINDOW_DAYS,
    ) -> Dict[str, ShadowValidationStats]:
        """
        Get shadow validation statistics grouped by decision type.

        Args:
            window_days: Number of days to look back

        Returns:
            Dictionary of decision_type -> ShadowValidationStats
        """
        if self._db is None:
            self._logger.warning("No database connection")
            return {}

        cutoff_ms = int(time.time() * 1000) - (window_days * 24 * 60 * 60 * 1000)

        query = f"""
            SELECT
                decision_type,
                COUNT(*) as total_decisions,
                SUM(CASE WHEN NOT choices_differ THEN 1 ELSE 0 END) as agreements,
                SUM(CASE WHEN choices_differ THEN 1 ELSE 0 END) as disagreements,
                SUM(CASE WHEN choices_differ AND mcts_better = true THEN 1 ELSE 0 END) as mcts_better_count,
                SUM(CASE WHEN choices_differ AND mcts_better = false THEN 1 ELSE 0 END) as heuristic_better_count,
                SUM(CASE WHEN choices_differ AND mcts_better IS NULL AND evaluated_at IS NOT NULL THEN 1 ELSE 0 END) as equal_count,
                SUM(CASE WHEN evaluated_at IS NULL THEN 1 ELSE 0 END) as unevaluated_count
            FROM {ST_MCTS_SHADOW_LOG_TABLE}
            WHERE created_at >= :cutoff_ms
            GROUP BY decision_type
        """

        try:
            rows = await self._db.fetch_all(query, {"cutoff_ms": cutoff_ms})
            result = {}
            for row in rows:
                dt = row.get("decision_type", "unknown")
                result[dt] = ShadowValidationStats(
                    total_decisions=row.get("total_decisions", 0) or 0,
                    agreements=row.get("agreements", 0) or 0,
                    disagreements=row.get("disagreements", 0) or 0,
                    mcts_better_count=row.get("mcts_better_count", 0) or 0,
                    heuristic_better_count=row.get("heuristic_better_count", 0) or 0,
                    equal_count=row.get("equal_count", 0) or 0,
                    unevaluated_count=row.get("unevaluated_count", 0) or 0,
                    window_days=window_days,
                )
            return result
        except Exception as e:
            self._logger.error(f"Failed to get stats by type: {e}")
            return {}

    async def analyze_for_promotion(
        self,
        window_days: int = P03_R5_SHADOW_VALIDATION_WINDOW_DAYS,
    ) -> PromotionAnalysis:
        """
        Analyze shadow validation results and recommend promotion.

        Implements the promotion logic from dossier:
        - If agreement >95%: Keep disabled (MCTS not worth cost)
        - If diff >20% AND MCTS better >55%: Promote to enabled_low

        Args:
            window_days: Number of days to look back

        Returns:
            PromotionAnalysis with recommendation
        """
        stats = await self.get_stats_for_window(window_days=window_days)

        thresholds_met = {
            "sufficient_data": stats.has_sufficient_data,
            "high_agreement": stats.agreement_rate > P03_R5_SHADOW_AGREEMENT_THRESHOLD,
            "significant_diff": stats.disagreement_rate > P03_R5_SHADOW_DIFF_THRESHOLD,
            "mcts_better": stats.mcts_better_rate > P03_R5_SHADOW_BETTER_THRESHOLD,
        }

        # Decision logic
        if not stats.has_sufficient_data:
            return PromotionAnalysis(
                recommendation=PromotionRecommendation.KEEP_SHADOW,
                stats=stats,
                reasoning=(
                    f"Insufficient data: {stats.total_decisions} decisions "
                    f"(need 100+) and {stats.mcts_better_count + stats.heuristic_better_count + stats.equal_count} "
                    f"evaluated disagreements (need 10+)"
                ),
                thresholds_met=thresholds_met,
            )

        # High agreement = MCTS not worth cost
        if thresholds_met["high_agreement"]:
            return PromotionAnalysis(
                recommendation=PromotionRecommendation.KEEP_DISABLED,
                stats=stats,
                reasoning=(
                    f"High agreement rate ({stats.agreement_rate:.1%}) exceeds "
                    f"threshold ({P03_R5_SHADOW_AGREEMENT_THRESHOLD:.0%}). "
                    f"MCTS adds compute cost without benefit."
                ),
                thresholds_met=thresholds_met,
            )

        # Significant diff AND MCTS better = promote
        if thresholds_met["significant_diff"] and thresholds_met["mcts_better"]:
            return PromotionAnalysis(
                recommendation=PromotionRecommendation.PROMOTE_ENABLED_LOW,
                stats=stats,
                reasoning=(
                    f"Disagreement rate ({stats.disagreement_rate:.1%}) exceeds "
                    f"threshold ({P03_R5_SHADOW_DIFF_THRESHOLD:.0%}) AND "
                    f"MCTS better rate ({stats.mcts_better_rate:.1%}) exceeds "
                    f"threshold ({P03_R5_SHADOW_BETTER_THRESHOLD:.0%}). "
                    f"Recommend enabling MCTS with reduced rollouts."
                ),
                thresholds_met=thresholds_met,
            )

        # Inconclusive
        return PromotionAnalysis(
            recommendation=PromotionRecommendation.KEEP_SHADOW,
            stats=stats,
            reasoning=(
                f"Results inconclusive. Disagreement: {stats.disagreement_rate:.1%}, "
                f"MCTS better: {stats.mcts_better_rate:.1%}. "
                f"Continue shadow mode for more data."
            ),
            thresholds_met=thresholds_met,
        )

    def _build_insert_query(self) -> str:
        """Build INSERT query for st_mcts_shadow_log."""
        return f"""
            INSERT INTO {ST_MCTS_SHADOW_LOG_TABLE} (
                decision_id,
                cycle_id,
                decision_type,
                heuristic_choice,
                mcts_choice,
                choices_differ,
                context_json,
                applied_choice,
                outcome_heuristic,
                outcome_mcts,
                mcts_better,
                evaluated_at,
                created_at
            ) VALUES (
                :decision_id,
                :cycle_id,
                :decision_type,
                :heuristic_choice,
                :mcts_choice,
                :choices_differ,
                :context_json,
                :applied_choice,
                :outcome_heuristic,
                :outcome_mcts,
                :mcts_better,
                :evaluated_at,
                :created_at
            )
        """

    def _row_to_record(self, row: Dict[str, Any]) -> ShadowDecisionRecord:
        """Convert database row to ShadowDecisionRecord."""
        context = row.get("context_json", "{}")
        if isinstance(context, str):
            context = json.loads(context)

        return ShadowDecisionRecord(
            decision_id=row["decision_id"],
            cycle_id=row["cycle_id"],
            decision_type=row["decision_type"],
            heuristic_choice=row["heuristic_choice"],
            mcts_choice=row["mcts_choice"],
            choices_differ=row["choices_differ"],
            context=context,
            applied_choice=row["applied_choice"],
            outcome_heuristic=row.get("outcome_heuristic"),
            outcome_mcts=row.get("outcome_mcts"),
            mcts_better=row.get("mcts_better"),
            evaluated_at_ms=row.get("evaluated_at"),
            created_at_ms=row["created_at"],
        )


# =============================================================================
# CYCLE SHADOW TRACKER
# =============================================================================


@dataclass
class CycleShadowTracker:
    """
    Tracks shadow decisions within a single consolidation cycle.

    Collects decisions during a cycle and provides batch persistence
    at cycle end.

    Usage:
        tracker = CycleShadowTracker(cycle_id="01JFXYZ...")

        # Record decisions during cycle
        tracker.record(heuristic="merge", mcts="no_merge", type=MERGE, context={})

        # At cycle end
        await tracker.persist_all(shadow_tracker)
    """

    cycle_id: str
    _decisions: List[ShadowDecisionRecord] = field(default_factory=list)

    def record(
        self,
        decision_type: ShadowDecisionType,
        heuristic_choice: str,
        mcts_choice: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ShadowDecisionRecord:
        """
        Record a shadow decision made during this cycle.

        Args:
            decision_type: Type of decision
            heuristic_choice: Action chosen by heuristic
            mcts_choice: Action chosen by MCTS
            context: Additional context

        Returns:
            Created ShadowDecisionRecord
        """
        record = ShadowDecisionRecord.create(
            cycle_id=self.cycle_id,
            decision_type=decision_type,
            heuristic_choice=heuristic_choice,
            mcts_choice=mcts_choice,
            context=context,
        )
        self._decisions.append(record)
        return record

    @property
    def decision_count(self) -> int:
        """Number of decisions recorded."""
        return len(self._decisions)

    @property
    def disagreement_count(self) -> int:
        """Number of decisions where heuristic != mcts."""
        return sum(1 for d in self._decisions if d.choices_differ)

    @property
    def agreement_count(self) -> int:
        """Number of decisions where heuristic == mcts."""
        return sum(1 for d in self._decisions if not d.choices_differ)

    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics for this cycle."""
        return {
            "cycle_id": self.cycle_id,
            "decision_count": self.decision_count,
            "agreement_count": self.agreement_count,
            "disagreement_count": self.disagreement_count,
            "agreement_rate": (
                self.agreement_count / self.decision_count if self.decision_count > 0 else 0.0
            ),
        }

    async def persist_all(
        self,
        tracker: ShadowOutcomeTracker,
    ) -> int:
        """
        Persist all decisions to database.

        Args:
            tracker: ShadowOutcomeTracker for persistence

        Returns:
            Number of decisions persisted
        """
        return await tracker.record_decisions_batch(self._decisions)

    def clear(self) -> None:
        """Clear recorded decisions (after persistence)."""
        self._decisions.clear()
