"""
MCTS Decision Persistence — Storage and retrieval for MCTS decision traces.

This module provides the persistence layer for MCTS decisions made during
R5 dream-like exploration. It writes to st_mcts_decisions and integrates
with K0's TruthWriter infrastructure.

Issue Reference: M8_EXECUTION.md Issue 8.1.7
Dossier Reference: P03 Consolidation Dossier Section 4.6, Appendix D

Key Features:
- Persist MCTS decisions with full context and metrics
- Support early termination tracking
- Integration with compute budget tracking
- Async batch persistence for efficiency

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

# Table name for MCTS decisions
ST_MCTS_DECISIONS_TABLE = "st_mcts_decisions"

# Maximum decisions to batch persist
MAX_BATCH_SIZE = 100


# =============================================================================
# ENUMS
# =============================================================================


class MCTSDecisionType(str, Enum):
    """Types of MCTS decisions."""

    MERGE = "merge"
    CAUSAL = "causal"
    CLUSTER = "cluster"
    INSIGHT_RANKING = "insight_ranking"
    COUNTERFACTUAL = "counterfactual"
    ROUTINE_OPTIMIZATION = "routine_optimization"
    PROSPECTIVE_MEMORY = "prospective_memory"


class TerminationReason(str, Enum):
    """Reasons for MCTS early termination."""

    CLEAR_WINNER = "clear_winner"
    LOW_UNCERTAINTY = "low_uncertainty"
    BUDGET_EXHAUSTED = "budget_exhausted"
    MAX_DEPTH_REACHED = "max_depth_reached"
    CONVERGENCE = "convergence"
    NONE = "none"  # No early termination


# =============================================================================
# DATA STRUCTURES
# =============================================================================


@dataclass(frozen=True)
class MCTSDecisionRecord:
    """
    Record of a single MCTS decision for persistence.

    This is the immutable representation of an MCTS decision
    ready for storage in st_mcts_decisions.

    Attributes:
        decision_id: Unique ULID identifier
        cycle_id: Parent consolidation cycle ULID
        decision_type: Classification of the decision
        context: Rich context for retrospective analysis
        rollouts_allocated: Rollouts allocated based on importance
        rollouts_executed: Actual rollouts performed
        early_termination: Whether terminated early
        termination_reason: Why it terminated (if early)
        chosen_action: The selected action
        value_estimate: Expected value of chosen action
        confidence_interval_width: CI width at termination
        compute_ms: Wall-clock compute time
        created_at_ms: Creation timestamp (epoch ms)
    """

    decision_id: str
    cycle_id: str
    decision_type: str
    context: Dict[str, Any]
    rollouts_allocated: int
    rollouts_executed: int
    early_termination: bool
    termination_reason: str
    chosen_action: Optional[str]
    value_estimate: float
    confidence_interval_width: float
    compute_ms: int
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    @classmethod
    def create(
        cls,
        cycle_id: str,
        decision_type: MCTSDecisionType,
        context: Optional[Dict[str, Any]] = None,
        rollouts_allocated: int = 0,
        rollouts_executed: int = 0,
        early_termination: bool = False,
        termination_reason: TerminationReason = TerminationReason.NONE,
        chosen_action: Optional[str] = None,
        value_estimate: float = 0.0,
        confidence_interval_width: float = 1.0,
        compute_ms: int = 0,
    ) -> "MCTSDecisionRecord":
        """Factory method to create a new decision record with auto-generated ID."""
        return cls(
            decision_id=generate_ulid(),
            cycle_id=cycle_id,
            decision_type=decision_type.value,
            context=context or {},
            rollouts_allocated=rollouts_allocated,
            rollouts_executed=rollouts_executed,
            early_termination=early_termination,
            termination_reason=termination_reason.value,
            chosen_action=chosen_action,
            value_estimate=value_estimate,
            confidence_interval_width=confidence_interval_width,
            compute_ms=compute_ms,
            created_at_ms=int(time.time() * 1000),
        )

    def to_db_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database insertion."""
        return {
            "decision_id": self.decision_id,
            "cycle_id": self.cycle_id,
            "decision_type": self.decision_type,
            "context_json": json.dumps(self.context),
            "rollouts_allocated": self.rollouts_allocated,
            "rollouts_executed": self.rollouts_executed,
            "early_termination": self.early_termination,
            "termination_reason": self.termination_reason if self.early_termination else None,
            "chosen_action": self.chosen_action,
            "value_estimate": self.value_estimate,
            "confidence_interval_width": self.confidence_interval_width,
            "compute_ms": self.compute_ms,
            "created_at": self.created_at_ms,
        }


# =============================================================================
# PROTOCOLS
# =============================================================================


@runtime_checkable
class DatabaseConnection(Protocol):
    """Protocol for database connection (async)."""

    async def execute(self, query: str, params: Dict[str, Any]) -> Any: ...

    async def execute_many(self, query: str, params_list: List[Dict[str, Any]]) -> Any: ...


# =============================================================================
# PERSISTENCE LAYER
# =============================================================================


class MCTSDecisionPersistence:
    """
    Persistence layer for MCTS decisions.

    Handles writing MCTS decision records to st_mcts_decisions table.
    Supports both single and batch inserts for efficiency.

    Usage:
        persistence = MCTSDecisionPersistence(db_connection)

        # Single insert
        await persistence.persist_decision(decision_record)

        # Batch insert
        await persistence.persist_decisions_batch(decision_records)

        # Get cycle stats
        stats = await persistence.get_cycle_stats(cycle_id)
    """

    def __init__(self, db: Optional[DatabaseConnection] = None):
        """
        Initialize persistence layer.

        Args:
            db: Database connection (optional, can be set later)
        """
        self._db = db
        self._logger = getLogger(f"{__name__}.{self.__class__.__name__}")
        self._pending_decisions: List[MCTSDecisionRecord] = []

    def set_connection(self, db: DatabaseConnection) -> None:
        """Set database connection."""
        self._db = db

    async def persist_decision(self, decision: MCTSDecisionRecord) -> str:
        """
        Persist a single MCTS decision.

        Args:
            decision: Decision record to persist

        Returns:
            decision_id of persisted record
        """
        if self._db is None:
            self._logger.warning("No database connection, buffering decision")
            self._pending_decisions.append(decision)
            return decision.decision_id

        query = self._build_insert_query()
        params = decision.to_db_dict()

        try:
            await self._db.execute(query, params)
            self._logger.debug(
                "Persisted MCTS decision",
                extra={
                    "decision_id": decision.decision_id,
                    "decision_type": decision.decision_type,
                    "rollouts": decision.rollouts_executed,
                },
            )
            return decision.decision_id
        except Exception as e:
            self._logger.error(
                f"Failed to persist MCTS decision: {e}",
                extra={"decision_id": decision.decision_id},
            )
            raise

    async def persist_decisions_batch(
        self,
        decisions: List[MCTSDecisionRecord],
    ) -> int:
        """
        Persist multiple MCTS decisions in batch.

        Args:
            decisions: List of decision records

        Returns:
            Number of decisions persisted
        """
        if not decisions:
            return 0

        if self._db is None:
            self._logger.warning("No database connection, buffering decisions")
            self._pending_decisions.extend(decisions)
            return 0

        query = self._build_insert_query()
        params_list = [d.to_db_dict() for d in decisions]

        try:
            await self._db.execute_many(query, params_list)
            self._logger.debug(
                f"Persisted {len(decisions)} MCTS decisions in batch",
            )
            return len(decisions)
        except Exception as e:
            self._logger.error(f"Failed to persist MCTS decisions batch: {e}")
            raise

    async def flush_pending(self) -> int:
        """
        Flush pending decisions to database.

        Returns:
            Number of decisions flushed
        """
        if not self._pending_decisions:
            return 0

        if self._db is None:
            self._logger.warning("Cannot flush: no database connection")
            return 0

        count = await self.persist_decisions_batch(self._pending_decisions)
        self._pending_decisions.clear()
        return count

    def _build_insert_query(self) -> str:
        """Build INSERT query for st_mcts_decisions."""
        return f"""
            INSERT INTO {ST_MCTS_DECISIONS_TABLE} (
                decision_id,
                cycle_id,
                decision_type,
                context_json,
                rollouts_allocated,
                rollouts_executed,
                early_termination,
                termination_reason,
                chosen_action,
                value_estimate,
                confidence_interval_width,
                compute_ms,
                created_at
            ) VALUES (
                :decision_id,
                :cycle_id,
                :decision_type,
                :context_json,
                :rollouts_allocated,
                :rollouts_executed,
                :early_termination,
                :termination_reason,
                :chosen_action,
                :value_estimate,
                :confidence_interval_width,
                :compute_ms,
                :created_at
            )
        """


# =============================================================================
# CYCLE TRACKER
# =============================================================================


@dataclass
class CycleDecisionTracker:
    """
    Tracks MCTS decisions within a single consolidation cycle.

    Collects decisions during a cycle and provides batch persistence
    at cycle end. Also tracks compute budget usage.

    Usage:
        tracker = CycleDecisionTracker(cycle_id="01JFXYZ...")

        # Record decisions during cycle
        tracker.record_decision(decision)

        # At cycle end
        stats = tracker.get_stats()
        await tracker.persist_all(persistence)
    """

    cycle_id: str
    max_rollouts: int = 1000
    _decisions: List[MCTSDecisionRecord] = field(default_factory=list)
    _total_rollouts: int = 0
    _early_terminations: int = 0

    def record_decision(self, decision: MCTSDecisionRecord) -> None:
        """
        Record a decision made during this cycle.

        Args:
            decision: MCTS decision record
        """
        self._decisions.append(decision)
        self._total_rollouts += decision.rollouts_executed

        if decision.early_termination:
            self._early_terminations += 1

    @property
    def total_rollouts(self) -> int:
        """Total rollouts used in this cycle."""
        return self._total_rollouts

    @property
    def remaining_budget(self) -> int:
        """Remaining rollout budget."""
        return max(0, self.max_rollouts - self._total_rollouts)

    @property
    def budget_exhausted(self) -> bool:
        """Whether budget is exhausted."""
        return self._total_rollouts >= self.max_rollouts

    @property
    def early_termination_rate(self) -> float:
        """Percentage of decisions that terminated early."""
        if not self._decisions:
            return 0.0
        return self._early_terminations / len(self._decisions)

    @property
    def decision_count(self) -> int:
        """Number of decisions recorded."""
        return len(self._decisions)

    def get_stats(self) -> Dict[str, Any]:
        """Get cycle statistics."""
        return {
            "cycle_id": self.cycle_id,
            "decision_count": self.decision_count,
            "total_rollouts": self._total_rollouts,
            "max_rollouts": self.max_rollouts,
            "remaining_budget": self.remaining_budget,
            "budget_exhausted": self.budget_exhausted,
            "early_termination_count": self._early_terminations,
            "early_termination_rate": self.early_termination_rate,
        }

    async def persist_all(
        self,
        persistence: MCTSDecisionPersistence,
    ) -> int:
        """
        Persist all decisions to database.

        Args:
            persistence: Persistence layer

        Returns:
            Number of decisions persisted
        """
        return await persistence.persist_decisions_batch(self._decisions)

    def clear(self) -> None:
        """Clear recorded decisions (after persistence)."""
        self._decisions.clear()
        self._total_rollouts = 0
        self._early_terminations = 0
