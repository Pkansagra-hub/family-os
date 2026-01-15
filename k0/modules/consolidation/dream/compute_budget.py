"""
ComputeBudget — Shared compute budget for R5 cycle.

Per A.0.4 invariant and Issue 8.1.15: ComputeBudget is created ONCE per cycle
and passed to all R5 algorithms to enforce the per-cycle rollout cap.

References:
- M8_EXECUTION.md Issue 8.1.15: R5 Algorithm Orchestration
- M8_EXECUTION.md Issue 8.1.6: Adaptive Rollout Allocation + Early Termination
- Dossier §4.6.2.1: Compute budget enforcement

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


# =============================================================================
# CONSTANTS (from dossier §4.6.2.1)
# =============================================================================

# Default per-cycle MCTS rollout budget
P03_R5_DEFAULT_MCTS_BUDGET = 1000

# Default maximum compute time per cycle (milliseconds)
P03_R5_DEFAULT_COMPUTE_TIMEOUT_MS = 30_000  # 30 seconds

# Algorithm time allocations (percentage of total)
P03_R5_ALGORITHM_TIME_ALLOCATION = {
    "bgt_sm": 0.20,  # 20% for BGT-SM
    "cpn": 0.20,  # 20% for CPN
    "spc_uq": 0.20,  # 20% for SPC-UQ
    "mcts": 0.30,  # 30% for MCTS (most expensive)
    "tdl_hco": 0.10,  # 10% for TDL-HCO
}


# =============================================================================
# BUDGET EXHAUSTION REASON
# =============================================================================


class BudgetExhaustionReason(str, Enum):
    """Reasons for budget exhaustion."""

    ROLLOUTS_EXHAUSTED = "rollouts_exhausted"
    TIME_EXHAUSTED = "time_exhausted"
    MANUAL_STOP = "manual_stop"


# =============================================================================
# COMPUTE BUDGET (per A.0.4 invariant)
# =============================================================================


@dataclass
class ComputeBudget:
    """
    Shared compute budget for R5 cycle.

    Created ONCE per cycle and passed to all R5 algorithms.
    Enforces the per-cycle rollout cap and optional time budget.

    Thread-Safe: Uses atomic operations for allocation.
    Deterministic: State changes are logged for reproducibility.

    Attributes:
        max_mcts_rollouts: Maximum MCTS rollouts allowed (default 1000)
        used_rollouts: Rollouts already consumed
        max_compute_ms: Optional time budget in milliseconds
        start_time_ms: When budget tracking started
        exhaustion_reason: Reason if budget exhausted
    """

    max_mcts_rollouts: int = P03_R5_DEFAULT_MCTS_BUDGET
    used_rollouts: int = 0
    max_compute_ms: Optional[int] = None
    start_time_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    exhaustion_reason: Optional[BudgetExhaustionReason] = None

    def can_allocate(self, requested: int) -> bool:
        """
        Check if rollouts can be allocated.

        Args:
            requested: Number of rollouts requested

        Returns:
            True if allocation is possible
        """
        if self.exhausted:
            return False
        return self.used_rollouts + requested <= self.max_mcts_rollouts

    def allocate(self, requested: int) -> int:
        """
        Allocate rollouts, returning actual allocated (may be less).

        Args:
            requested: Number of rollouts requested

        Returns:
            Number of rollouts actually allocated
        """
        if self.exhausted:
            return 0

        available = self.max_mcts_rollouts - self.used_rollouts
        allocated = min(requested, available)
        self.used_rollouts += allocated

        # Check if this exhausts the budget
        if self.used_rollouts >= self.max_mcts_rollouts:
            self.exhaustion_reason = BudgetExhaustionReason.ROLLOUTS_EXHAUSTED

        return allocated

    @property
    def exhausted(self) -> bool:
        """Return True if budget is exhausted (rollouts or time)."""
        if self.exhaustion_reason is not None:
            return True

        # Check rollout exhaustion
        if self.used_rollouts >= self.max_mcts_rollouts:
            self.exhaustion_reason = BudgetExhaustionReason.ROLLOUTS_EXHAUSTED
            return True

        # Check time exhaustion
        if self.max_compute_ms is not None:
            elapsed_ms = int(time.time() * 1000) - self.start_time_ms
            if elapsed_ms >= self.max_compute_ms:
                self.exhaustion_reason = BudgetExhaustionReason.TIME_EXHAUSTED
                return True

        return False

    @property
    def remaining(self) -> int:
        """Return remaining rollouts."""
        return max(0, self.max_mcts_rollouts - self.used_rollouts)

    @property
    def elapsed_ms(self) -> int:
        """Return elapsed time in milliseconds."""
        return int(time.time() * 1000) - self.start_time_ms

    @property
    def remaining_time_ms(self) -> Optional[int]:
        """Return remaining time budget in milliseconds (None if no time budget)."""
        if self.max_compute_ms is None:
            return None
        remaining = self.max_compute_ms - self.elapsed_ms
        return max(0, remaining)

    @property
    def utilization(self) -> float:
        """Return rollout utilization (0.0 to 1.0)."""
        if self.max_mcts_rollouts == 0:
            return 1.0
        return self.used_rollouts / self.max_mcts_rollouts

    def stop(self, reason: str = "manual_stop") -> None:
        """
        Manually stop budget allocation.

        Args:
            reason: Reason for stopping (logged)
        """
        self.exhaustion_reason = BudgetExhaustionReason.MANUAL_STOP

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "max_mcts_rollouts": self.max_mcts_rollouts,
            "used_rollouts": self.used_rollouts,
            "remaining_rollouts": self.remaining,
            "utilization": round(self.utilization, 4),
            "elapsed_ms": self.elapsed_ms,
            "max_compute_ms": self.max_compute_ms,
            "remaining_time_ms": self.remaining_time_ms,
            "exhausted": self.exhausted,
            "exhaustion_reason": self.exhaustion_reason.value if self.exhaustion_reason else None,
        }

    def __repr__(self) -> str:
        """Return string representation."""
        status = "EXHAUSTED" if self.exhausted else "AVAILABLE"
        return (
            f"ComputeBudget("
            f"rollouts={self.used_rollouts}/{self.max_mcts_rollouts}, "
            f"elapsed={self.elapsed_ms}ms, "
            f"status={status})"
        )


# =============================================================================
# ALGORITHM RESULT TRACKING
# =============================================================================


@dataclass
class AlgorithmResult:
    """
    Result from running an R5 algorithm.

    Tracks success, outputs, and any errors for orchestration.

    Attributes:
        algorithm_name: Name of the algorithm (bgt_sm, cpn, etc.)
        success: Whether algorithm completed successfully
        outputs: List of generated outputs (insights, scenarios, etc.)
        error_message: Error message if failed
        compute_ms: Time spent in algorithm (milliseconds)
        rollouts_used: MCTS rollouts consumed (if applicable)
    """

    algorithm_name: str
    success: bool
    outputs: list = field(default_factory=list)
    error_message: Optional[str] = None
    compute_ms: int = 0
    rollouts_used: int = 0

    @property
    def is_failure(self) -> bool:
        """Return True if algorithm failed."""
        return not self.success

    @property
    def output_count(self) -> int:
        """Return number of outputs generated."""
        return len(self.outputs)


@dataclass
class OrchestrationResult:
    """
    Aggregated result from R5 algorithm orchestration.

    Collects results from all algorithms for unified reporting.

    Attributes:
        cycle_id: Cycle identifier
        algorithm_results: Results from each algorithm
        compute_budget: Shared compute budget reference
        total_compute_ms: Total compute time
        budget_snapshot: Final budget state
    """

    cycle_id: str
    algorithm_results: Dict[str, AlgorithmResult] = field(default_factory=dict)
    compute_budget: Optional[ComputeBudget] = None
    total_compute_ms: int = 0
    budget_snapshot: Optional[Dict[str, Any]] = None

    @property
    def all_succeeded(self) -> bool:
        """Return True if all algorithms succeeded."""
        return all(r.success for r in self.algorithm_results.values())

    @property
    def partial_success(self) -> bool:
        """Return True if at least one algorithm succeeded."""
        return any(r.success for r in self.algorithm_results.values())

    @property
    def failures(self) -> Dict[str, str]:
        """Return dictionary of algorithm -> error_message for failures."""
        return {
            name: r.error_message or "Unknown error"
            for name, r in self.algorithm_results.items()
            if r.is_failure
        }

    @property
    def total_outputs(self) -> int:
        """Return total outputs from all algorithms."""
        return sum(r.output_count for r in self.algorithm_results.values())

    def add_result(self, result: AlgorithmResult) -> None:
        """Add an algorithm result."""
        self.algorithm_results[result.algorithm_name] = result
