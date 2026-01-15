"""
AccessTracker — Track entity access patterns for per-entity decay learning.

Tracks access counts, timestamps, and inter-access intervals to enable
Bayesian λ estimation for per-entity decay rates.

Scientific Basis:
- Maximum Likelihood Estimation for exponential distribution
- λ_MLE = n / Σ(intervals) where n = number of intervals

Spec Reference:
- Dossier §4.4.1: Per-Entity Access Tracking
- M4_EXECUTION.md Issue 4.3.5

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol, runtime_checkable

# =============================================================================
# Constants
# =============================================================================

# Time constants
MS_PER_DAY = 24 * 60 * 60 * 1000  # 86,400,000 ms

# Access tracking defaults (from Dossier §4.4.1)
DEFAULT_MIN_ACCESS_COUNT = 5  # Min accesses before learning λ
DEFAULT_MIN_SPREAD_DAYS = 7  # Min spread between first and last access
DEFAULT_MAX_INTERVALS_STORED = 10  # Max intervals to store per entity

# Lambda bounds (from Dossier §4.4.1)
LAMBDA_MIN = 0.0001  # Minimum λ (very slow decay, ~6931 day half-life)
LAMBDA_MAX = 0.1  # Maximum λ (fast decay, ~7 day half-life)


# =============================================================================
# Access Statistics
# =============================================================================


@dataclass
class AccessStats:
    """
    Access statistics for an entity.

    Attributes:
        entity_id: Unique entity identifier
        entity_table: Source table (st_epi, st_sem, etc.)
        access_count: Total number of accesses
        first_access_at: Timestamp of first access (ms)
        last_access_at: Timestamp of last access (ms)
        access_intervals_ms: List of inter-access intervals (ms)
        spread_days: Days between first and last access
        eligible_for_learning: True if 5+ accesses AND 7+ day spread
    """

    entity_id: str
    entity_table: str = ""
    access_count: int = 0
    first_access_at: int = 0  # ms
    last_access_at: int = 0  # ms
    access_intervals_ms: List[int] = field(default_factory=list)
    spread_days: float = 0.0
    eligible_for_learning: bool = False

    def get_intervals_days(self) -> List[float]:
        """Convert intervals from ms to days."""
        return [interval / MS_PER_DAY for interval in self.access_intervals_ms]


@dataclass
class LambdaEstimate:
    """
    Bayesian λ estimate result.

    Attributes:
        entity_id: Entity identifier
        entity_table: Source table
        lambda_value: Estimated decay rate (per day)
        confidence: Confidence in estimate [0, 1]
        sample_count: Number of intervals used
        half_life_days: Approximate half-life in days
    """

    entity_id: str
    entity_table: str
    lambda_value: float
    confidence: float
    sample_count: int
    half_life_days: float = 0.0

    def __post_init__(self) -> None:
        """Calculate half-life from lambda."""
        if self.lambda_value > 0:
            self.half_life_days = 0.693 / self.lambda_value


# =============================================================================
# Configuration
# =============================================================================


@dataclass(frozen=True)
class AccessTrackerConfig:
    """
    Configuration for access tracking.

    From Dossier §4.4.1 Configuration:
        P03_ACCESS_MIN_COUNT: 5
        P03_ACCESS_MIN_SPREAD_DAYS: 7
        P03_ACCESS_INTERVALS_MAX: 10
    """

    min_access_count: int = DEFAULT_MIN_ACCESS_COUNT
    min_spread_days: float = DEFAULT_MIN_SPREAD_DAYS
    max_intervals_stored: int = DEFAULT_MAX_INTERVALS_STORED
    lambda_min: float = LAMBDA_MIN
    lambda_max: float = LAMBDA_MAX

    def validate(self) -> None:
        """Validate configuration."""
        if self.min_access_count < 2:
            raise ValueError(f"min_access_count must be >= 2, got {self.min_access_count}")
        if self.min_spread_days <= 0:
            raise ValueError(f"min_spread_days must be > 0, got {self.min_spread_days}")
        if self.max_intervals_stored < 1:
            raise ValueError(f"max_intervals_stored must be >= 1, got {self.max_intervals_stored}")
        if self.lambda_min <= 0:
            raise ValueError(f"lambda_min must be > 0, got {self.lambda_min}")
        if self.lambda_max <= self.lambda_min:
            raise ValueError(
                f"lambda_max ({self.lambda_max}) must be > lambda_min ({self.lambda_min})"
            )


# =============================================================================
# Storage Protocol
# =============================================================================


@runtime_checkable
class AccessStoreProtocol(Protocol):
    """
    Protocol for access tracking storage.

    Implementations may use database, in-memory, or mock storage.
    """

    async def get_access_stats(self, entity_id: str, entity_table: str) -> Optional[AccessStats]:
        """Get current access stats for entity."""
        ...

    async def update_access_stats(self, stats: AccessStats) -> None:
        """Update access stats for entity."""
        ...

    async def persist_lambda(
        self,
        entity_id: str,
        space_id: str,
        lambda_value: float,
        confidence: float,
        sample_count: int,
    ) -> None:
        """Persist learned λ to st_learned_weights."""
        ...


# =============================================================================
# In-Memory Store (for testing)
# =============================================================================


class InMemoryAccessStore:
    """
    In-memory implementation of AccessStoreProtocol.

    For testing and development. Production uses database storage.
    """

    def __init__(self) -> None:
        self._stats: Dict[str, AccessStats] = {}
        self._lambdas: Dict[str, LambdaEstimate] = {}

    def _key(self, entity_id: str, entity_table: str) -> str:
        return f"{entity_table}:{entity_id}"

    async def get_access_stats(self, entity_id: str, entity_table: str) -> Optional[AccessStats]:
        """Get current access stats for entity."""
        return self._stats.get(self._key(entity_id, entity_table))

    async def update_access_stats(self, stats: AccessStats) -> None:
        """Update access stats for entity."""
        key = self._key(stats.entity_id, stats.entity_table)
        self._stats[key] = stats

    async def persist_lambda(
        self,
        entity_id: str,
        space_id: str,
        lambda_value: float,
        confidence: float,
        sample_count: int,
    ) -> None:
        """Persist learned λ (in-memory)."""
        key = f"{space_id}:{entity_id}"
        self._lambdas[key] = LambdaEstimate(
            entity_id=entity_id,
            entity_table="",
            lambda_value=lambda_value,
            confidence=confidence,
            sample_count=sample_count,
        )

    def get_lambda(self, entity_id: str, space_id: str) -> Optional[LambdaEstimate]:
        """Get persisted λ (for testing)."""
        key = f"{space_id}:{entity_id}"
        return self._lambdas.get(key)


# =============================================================================
# AccessTracker Class
# =============================================================================


class AccessTracker:
    """
    Track entity access patterns for per-entity decay learning.

    Tracks access counts, timestamps, and inter-access intervals.
    Determines when an entity has sufficient data for Bayesian λ estimation.

    Usage:
        tracker = AccessTracker()

        # Record access (called when P04 retrieves entity)
        stats = await tracker.record_access(
            entity_id='mem_123',
            entity_table='st_epi',
            accessed_at_ms=1700000000000,
            store=my_store,
        )

        # Check if eligible for λ learning
        if stats.eligible_for_learning:
            intervals = stats.get_intervals_days()
            lambda_estimate = tracker.estimate_lambda(intervals)

    Spec: Dossier §4.4.1
    """

    def __init__(
        self,
        config: Optional[AccessTrackerConfig] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize access tracker.

        Args:
            config: Access tracking configuration
            logger: Logger instance
        """
        self.config = config or AccessTrackerConfig()
        self.config.validate()
        self.logger = logger or logging.getLogger(__name__)

    async def record_access(
        self,
        entity_id: str,
        entity_table: str,
        accessed_at_ms: int,
        store: AccessStoreProtocol,
    ) -> AccessStats:
        """
        Record an entity access (triggered by P04 query retrieval).

        Algorithm (from Dossier §4.4.1):
        1. Fetch current access tracking data
        2. Compute inter-access interval if prior access exists
        3. Append to intervals array (keep last N)
        4. Update access_count, first_access_at, last_access_at
        5. Check if entity now qualifies for λ learning

        Args:
            entity_id: Unique entity identifier
            entity_table: Source table (st_epi, st_sem, etc.)
            accessed_at_ms: Access timestamp (ms since epoch)
            store: Storage backend

        Returns:
            Updated AccessStats
        """
        # Get existing stats or create new
        existing = await store.get_access_stats(entity_id, entity_table)

        if existing is None:
            # First access
            stats = AccessStats(
                entity_id=entity_id,
                entity_table=entity_table,
                access_count=1,
                first_access_at=accessed_at_ms,
                last_access_at=accessed_at_ms,
                access_intervals_ms=[],
                spread_days=0.0,
                eligible_for_learning=False,
            )
        else:
            # Subsequent access
            stats = existing

            # Compute interval from last access
            if stats.last_access_at > 0:
                interval_ms = accessed_at_ms - stats.last_access_at
                if interval_ms > 0:
                    # Append interval
                    new_intervals = stats.access_intervals_ms + [interval_ms]
                    # Keep only last N intervals
                    if len(new_intervals) > self.config.max_intervals_stored:
                        new_intervals = new_intervals[-self.config.max_intervals_stored :]
                    stats.access_intervals_ms = new_intervals

            # Update timestamps and count
            stats.access_count += 1
            stats.last_access_at = accessed_at_ms

            # Calculate spread
            stats.spread_days = (stats.last_access_at - stats.first_access_at) / MS_PER_DAY

            # Check eligibility
            stats.eligible_for_learning = self.check_learning_eligibility(stats)

        # Persist updated stats
        await store.update_access_stats(stats)

        self.logger.debug(
            f"Access recorded: entity={entity_id} table={entity_table} "
            f"count={stats.access_count} eligible={stats.eligible_for_learning}"
        )

        return stats

    def check_learning_eligibility(self, stats: AccessStats) -> bool:
        """
        Check if entity has enough data for λ learning.

        From Dossier §4.4.1:
        - Requires min_access_count (default 5) accesses
        - Requires min_spread_days (default 7) between first and last

        Args:
            stats: Current access statistics

        Returns:
            True if eligible for λ learning
        """
        has_enough_accesses = stats.access_count >= self.config.min_access_count
        has_enough_spread = stats.spread_days >= self.config.min_spread_days
        return has_enough_accesses and has_enough_spread

    def get_inter_access_intervals_days(self, stats: AccessStats) -> List[float]:
        """
        Get inter-access intervals in days for Bayesian estimation.

        Args:
            stats: Access statistics with intervals

        Returns:
            List of intervals in days (e.g., [2.3, 5.1, 1.8, 3.4])
        """
        return stats.get_intervals_days()


# =============================================================================
# BayesianLambdaEstimator Class
# =============================================================================


class BayesianLambdaEstimator:
    """
    Estimate per-entity decay rate λ using Bayesian inference.

    Scientific Basis:
    - Maximum Likelihood Estimation for exponential distribution
    - λ_MLE = n / Σ(intervals) where n = number of intervals

    For exponential inter-arrival times, MLE gives the rate parameter.
    More frequent accesses → smaller intervals → higher λ (faster expected decay).

    Usage:
        estimator = BayesianLambdaEstimator()

        # Estimate λ from access intervals
        estimate = estimator.estimate_lambda(
            entity_id='mem_123',
            entity_table='st_epi',
            intervals_days=[2.3, 5.1, 1.8, 3.4, 4.2],
        )
        # → LambdaEstimate(lambda_value=0.27, confidence=0.75, ...)

    Spec: Dossier §4.4.1
    """

    def __init__(
        self,
        config: Optional[AccessTrackerConfig] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize lambda estimator.

        Args:
            config: Configuration with lambda bounds
            logger: Logger instance
        """
        self.config = config or AccessTrackerConfig()
        self.logger = logger or logging.getLogger(__name__)

    def estimate_lambda(
        self,
        entity_id: str,
        entity_table: str,
        intervals_days: List[float],
    ) -> Optional[LambdaEstimate]:
        """
        Estimate λ from inter-access intervals.

        Formula (MLE for exponential distribution):
            λ_MLE = n / Σ(intervals)

        Where n = number of intervals.

        Args:
            entity_id: Entity identifier
            entity_table: Source table
            intervals_days: List of inter-access intervals in days

        Returns:
            LambdaEstimate or None if insufficient data

        Note:
            Requires at least 4 intervals (from 5+ accesses).
            Result is clamped to [0.0001, 0.1] range.
        """
        # Need at least 4 intervals (from 5 accesses)
        min_intervals = self.config.min_access_count - 1
        if len(intervals_days) < min_intervals:
            return None

        # Filter out zero or negative intervals
        valid_intervals = [i for i in intervals_days if i > 0]
        if len(valid_intervals) < min_intervals:
            return None

        # MLE for exponential distribution: λ = n / Σ(intervals)
        total_time = sum(valid_intervals)
        if total_time <= 0:
            return None

        lambda_mle = len(valid_intervals) / total_time

        # Clamp to reasonable bounds
        lambda_clamped = max(
            self.config.lambda_min,
            min(self.config.lambda_max, lambda_mle),
        )

        # Calculate confidence based on sample size
        # More samples = higher confidence
        confidence = self._compute_confidence(len(valid_intervals))

        estimate = LambdaEstimate(
            entity_id=entity_id,
            entity_table=entity_table,
            lambda_value=lambda_clamped,
            confidence=confidence,
            sample_count=len(valid_intervals),
        )

        self.logger.info(
            f"Lambda estimated: entity={entity_id} table={entity_table} "
            f"λ={lambda_clamped:.6f} confidence={confidence:.2f} "
            f"samples={len(valid_intervals)} half_life={estimate.half_life_days:.1f}d"
        )

        return estimate

    def _compute_confidence(self, sample_count: int) -> float:
        """
        Compute confidence score based on sample count.

        Confidence curve:
        - 4 samples: 0.50
        - 6 samples: 0.65
        - 8 samples: 0.75
        - 10 samples: 0.85
        - 15+ samples: 0.95

        Args:
            sample_count: Number of intervals

        Returns:
            Confidence score [0.5, 0.95]
        """
        if sample_count <= 4:
            return 0.50
        elif sample_count <= 6:
            return 0.50 + (sample_count - 4) * 0.075  # 0.50 → 0.65
        elif sample_count <= 8:
            return 0.65 + (sample_count - 6) * 0.05  # 0.65 → 0.75
        elif sample_count <= 10:
            return 0.75 + (sample_count - 8) * 0.05  # 0.75 → 0.85
        elif sample_count <= 15:
            return 0.85 + (sample_count - 10) * 0.02  # 0.85 → 0.95
        else:
            return 0.95

    async def persist_lambda(
        self,
        estimate: LambdaEstimate,
        space_id: str,
        store: AccessStoreProtocol,
    ) -> None:
        """
        Store learned λ in st_learned_weights.

        Uses param_key = f'decay_lambda_{entity_id}'

        Args:
            estimate: Lambda estimate to persist
            space_id: Space ID for isolation
            store: Storage backend
        """
        await store.persist_lambda(
            entity_id=estimate.entity_id,
            space_id=space_id,
            lambda_value=estimate.lambda_value,
            confidence=estimate.confidence,
            sample_count=estimate.sample_count,
        )

        self.logger.info(
            f"Lambda persisted: entity={estimate.entity_id} space={space_id} "
            f"λ={estimate.lambda_value:.6f}"
        )


# =============================================================================
# Utility Functions
# =============================================================================


def compute_lambda_mle(intervals_days: List[float]) -> Optional[float]:
    """
    Compute Maximum Likelihood Estimate of λ from intervals.

    Formula: λ_MLE = n / Σ(intervals)

    Args:
        intervals_days: List of inter-access intervals in days

    Returns:
        λ estimate or None if insufficient data
    """
    valid = [i for i in intervals_days if i > 0]
    if len(valid) < 4:
        return None

    total = sum(valid)
    if total <= 0:
        return None

    return len(valid) / total


def clamp_lambda(value: float, min_val: float = LAMBDA_MIN, max_val: float = LAMBDA_MAX) -> float:
    """
    Clamp λ to valid range.

    Args:
        value: Raw λ value
        min_val: Minimum allowed (default 0.0001)
        max_val: Maximum allowed (default 0.1)

    Returns:
        Clamped λ value
    """
    return max(min_val, min(max_val, value))
