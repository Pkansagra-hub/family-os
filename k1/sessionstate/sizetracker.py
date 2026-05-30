"""
SizeTracker - Per-Section Byte Accounting
==========================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.1 Kernel Services
ISSUE: 2.1.1

ADRs:
- ADR-0017 series: SessionState 6-Section Design
- ADR-0018 series: 3-Tier Eviction Strategy (pressure thresholds)

==============================================================================
SPECIFICATION
==============================================================================

PURPOSE:
    Track byte usage per section, per tier, and total.
    Provide pressure level assessment for eviction decisions.

IMPLEMENTATION ORDER:
    SizeTracker is FOUNDATIONAL - no dependencies.
    Must be implemented first before MutationGuard, EvictionEngine.

SIZE BUDGETS (from README.md):
    TOTAL: 96KB (98,304 bytes)

    HOT CORE (48KB):
        - control:          8KB (8,192 bytes)  - NEVER EVICT
        - beliefs_active:   8KB
        - scoreboard:       6KB (6,144 bytes)
        - history_active:   8KB
        - clarifications:   4KB (4,096 bytes)
        - affective_now:    4KB
        - narrative_active: 4KB
        - meta:             2KB (2,048 bytes)

    WARM TIER (48KB):
        - beliefs_history:  12KB (12,288 bytes)
        - history_recent:   20KB (20,480 bytes)
        - persona:          8KB
        - telemetry:        8KB

PRESSURE LEVELS:
    NORMAL:    < 80% utilization
    ELEVATED:  80-90% utilization (trigger migration)
    CRITICAL:  90-95% utilization (trigger eviction)
    EMERGENCY: > 95% utilization (emergency mode, may reject writes)

==============================================================================
CLASS: SizeTracker
==============================================================================
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, FrozenSet, List, Optional, Tuple

from .config import TiersConfig

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class PressureLevel(str, Enum):
    """
    Memory pressure levels.

    Thresholds (from common.fbs and README Section 8.1):
        NORMAL:    < 80% utilization
        ELEVATED:  80-90% utilization (trigger migration)
        CRITICAL:  90-95% utilization (trigger eviction)
        EMERGENCY: > 95% utilization (emergency mode, may reject writes)
    """

    NORMAL = "normal"
    ELEVATED = "elevated"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class Tier(str, Enum):
    """Memory tiers."""

    HOT = "hot"
    WARM = "warm"


@dataclass(frozen=True)
class SectionBudget:
    """
    Immutable size budget specification for a section.

    Attributes:
        name: Section identifier (e.g., 'control', 'beliefs_active')
        tier: Which tier this section belongs to (HOT or WARM)
        max_bytes: Maximum allowed size in bytes
        eviction_priority: Priority for eviction (lower = evicted first).
                          None means NEVER EVICT.
        can_migrate: Whether section can migrate between tiers.
    """

    name: str
    tier: Tier
    max_bytes: int
    eviction_priority: Optional[int] = None  # None = NEVER EVICT
    can_migrate: bool = True


# =============================================================================
# SECTION BUDGET DEFINITIONS
# =============================================================================
# Source: k1/sessionstate/README.md Sections 5-6

SECTION_BUDGETS: Dict[str, SectionBudget] = {
    # HOT CORE sections (52KB total, matches config hot_budget_bytes)
    "control": SectionBudget(
        name="control",
        tier=Tier.HOT,
        max_bytes=8 * 1024,
        eviction_priority=None,  # NEVER EVICT
        can_migrate=False,
    ),
    "beliefs_active": SectionBudget(
        name="beliefs_active",
        tier=Tier.HOT,
        max_bytes=8 * 1024,
        eviction_priority=5,  # Demotes to beliefs_history
        can_migrate=True,
    ),
    "scoreboard": SectionBudget(
        name="scoreboard",
        tier=Tier.HOT,
        max_bytes=6 * 1024,
        eviction_priority=6,
        can_migrate=True,
    ),
    "history_active": SectionBudget(
        name="history_active",
        tier=Tier.HOT,
        max_bytes=8 * 1024,
        eviction_priority=4,  # Demotes to history_recent
        can_migrate=True,
    ),
    "clarifications": SectionBudget(
        name="clarifications",
        tier=Tier.HOT,
        max_bytes=4 * 1024,
        eviction_priority=7,
        can_migrate=True,
    ),
    "affective_now": SectionBudget(
        name="affective_now",
        tier=Tier.HOT,
        max_bytes=4 * 1024,
        eviction_priority=8,
        can_migrate=True,
    ),
    "narrative_active": SectionBudget(
        name="narrative_active",
        tier=Tier.HOT,
        max_bytes=4 * 1024,  # 4KB (config: narrative_active)
        eviction_priority=9,
        can_migrate=True,
    ),
    "meta": SectionBudget(
        name="meta",
        tier=Tier.HOT,
        max_bytes=2 * 1024,
        eviction_priority=None,  # NEVER EVICT
        can_migrate=False,
    ),
    "temporal": SectionBudget(
        name="temporal",
        tier=Tier.HOT,
        max_bytes=4 * 1024,
        eviction_priority=None,  # NEVER EVICT
        can_migrate=False,
    ),
    "grounding": SectionBudget(
        name="grounding",
        tier=Tier.HOT,
        max_bytes=2 * 1024,
        eviction_priority=None,  # NEVER EVICT
        can_migrate=False,
    ),
    "trust_level": SectionBudget(
        name="trust_level",
        tier=Tier.HOT,
        max_bytes=2 * 1024,
        eviction_priority=None,  # NEVER EVICT
        can_migrate=False,
    ),
    "spatial": SectionBudget(
        name="spatial",
        tier=Tier.HOT,
        max_bytes=4 * 1024,
        eviction_priority=None,  # NEVER EVICT
        can_migrate=False,
    ),
    "task_state": SectionBudget(
        name="task_state",
        tier=Tier.HOT,
        max_bytes=4 * 1024,
        eviction_priority=None,  # NEVER EVICT (critical for HITL recovery)
        can_migrate=False,
    ),
    "task_artifacts": SectionBudget(
        name="task_artifacts",
        tier=Tier.HOT,
        max_bytes=4 * 1024,
        eviction_priority=3,  # Demotes to artifacts_warm
        can_migrate=True,
    ),
    # WARM TIER sections (48KB total)
    "beliefs_history": SectionBudget(
        name="beliefs_history",
        tier=Tier.WARM,
        max_bytes=12 * 1024,
        eviction_priority=2,  # Archive oldest to COLD
        can_migrate=True,
    ),
    "history_recent": SectionBudget(
        name="history_recent",
        tier=Tier.WARM,
        max_bytes=20 * 1024,  # 20KB (config: history_recent)
        eviction_priority=3,  # Summarize oldest, archive
        can_migrate=True,
    ),
    "persona": SectionBudget(
        name="persona",
        tier=Tier.WARM,
        max_bytes=8 * 1024,
        eviction_priority=10,  # Never evict unless EMERGENCY (highest)
        can_migrate=True,
    ),
    "telemetry": SectionBudget(
        name="telemetry",
        tier=Tier.WARM,
        max_bytes=8 * 1024,  # 8KB (config: telemetry)
        eviction_priority=1,  # FIRST to evict (lowest priority)
        can_migrate=True,
    ),
    "artifacts_warm": SectionBudget(
        name="artifacts_warm",
        tier=Tier.WARM,
        max_bytes=8 * 1024,
        eviction_priority=2,  # Evict after telemetry
        can_migrate=True,
    ),
    "place_registry": SectionBudget(
        name="place_registry",
        tier=Tier.WARM,
        max_bytes=8 * 1024,
        eviction_priority=4,
        can_migrate=True,
    ),
}

# Frozen sets for tier membership (O(1) lookup)
HOT_SECTIONS: FrozenSet[str] = frozenset(
    name for name, budget in SECTION_BUDGETS.items() if budget.tier == Tier.HOT
)
WARM_SECTIONS: FrozenSet[str] = frozenset(
    name for name, budget in SECTION_BUDGETS.items() if budget.tier == Tier.WARM
)
NEVER_EVICT_SECTIONS: FrozenSet[str] = frozenset(
    name for name, budget in SECTION_BUDGETS.items() if budget.eviction_priority is None
)
ALL_SECTIONS: FrozenSet[str] = frozenset(SECTION_BUDGETS.keys())

# =============================================================================
# SIZE CONSTANTS (from TiersConfig defaults)
# =============================================================================

_ss_tiers = TiersConfig()
TOTAL_SIZE_LIMIT_BYTES: int = _ss_tiers.total_size_limit_bytes
HOT_SIZE_LIMIT_BYTES: int = _ss_tiers.hot_budget_bytes
WARM_SIZE_LIMIT_BYTES: int = _ss_tiers.warm_budget_bytes

# Pressure thresholds (from TiersConfig defaults)
NORMAL_THRESHOLD_PCT: float = _ss_tiers.normal_threshold_pct
ELEVATED_THRESHOLD_PCT: float = _ss_tiers.elevated_threshold_pct
CRITICAL_THRESHOLD_PCT: float = _ss_tiers.critical_threshold_pct
# >95% = EMERGENCY


@dataclass
class SizeSnapshot:
    """
    Immutable snapshot of size tracker state.

    Useful for observability, debugging, and metrics emission.
    """

    sections: Dict[str, int]
    hot_total: int
    warm_total: int
    total: int
    hot_pressure: PressureLevel
    warm_pressure: PressureLevel
    overall_pressure: PressureLevel
    hot_utilization_pct: float
    warm_utilization_pct: float
    total_utilization_pct: float
    timestamp_ns: int = field(default_factory=lambda: 0)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "sections": self.sections.copy(),
            "hot_total": self.hot_total,
            "warm_total": self.warm_total,
            "total": self.total,
            "hot_pressure": self.hot_pressure.value,
            "warm_pressure": self.warm_pressure.value,
            "overall_pressure": self.overall_pressure.value,
            "hot_utilization_pct": round(self.hot_utilization_pct, 4),
            "warm_utilization_pct": round(self.warm_utilization_pct, 4),
            "total_utilization_pct": round(self.total_utilization_pct, 4),
            "timestamp_ns": self.timestamp_ns,
        }


class SizeTracker:
    """
    Per-section byte accounting for SessionState.

    Tracks byte usage per section, per tier, and total. Provides pressure
    level assessment for MutationGuard and EvictionEngine decisions.

    Thread Safety:
        - Read operations are lock-free (snapshot-based reads)
        - Write operations use a lock to ensure atomic updates
        - Single-writer pattern is assumed (only SessionStateManager.mutate calls update)

    Performance:
        - get_section_size: O(1)
        - get_tier_size: O(n) where n = sections in tier (8 for HOT, 4 for WARM)
        - get_total_size: O(1) with caching
        - get_pressure: O(1) with caching
        - update: O(1)

    Invariants:
        - Section sizes are always >= 0
        - Total never exceeds 96KB in normal operation (enforcement is MutationGuard's job)
        - control and meta sections have eviction_priority = None (NEVER EVICT)

    Example:
        tracker = SizeTracker()

        # Update after mutation
        tracker.update("beliefs_active", delta_bytes=1024)

        # Check sizes
        print(tracker.get_section_size("beliefs_active"))  # 1024
        print(tracker.get_tier_size("hot"))  # 1024
        print(tracker.get_total_size())  # 1024
        print(tracker.get_pressure())  # PressureLevel.NORMAL

        # Get full snapshot
        snapshot = tracker.get_snapshot()
        print(snapshot.to_dict())

    Attributes:
        _section_sizes: Dict mapping section name to current byte count
        _lock: Threading lock for write operations
        _hot_total_cached: Cached HOT tier total
        _warm_total_cached: Cached WARM tier total
        _cache_valid: Whether cached totals are valid
    """

    __slots__ = (
        "_section_sizes",
        "_lock",
        "_hot_total_cached",
        "_warm_total_cached",
        "_cache_valid",
    )

    def __init__(self) -> None:
        """
        Initialize SizeTracker with all sections at 0 bytes.

        Creates internal tracking dictionary and lock.
        """
        self._section_sizes: Dict[str, int] = {name: 0 for name in ALL_SECTIONS}
        self._lock = threading.Lock()
        self._hot_total_cached: int = 0
        self._warm_total_cached: int = 0
        self._cache_valid: bool = True

        logger.info("SizeTracker initialized: %d sections tracked", len(self._section_sizes))

    def _validate_section(self, section: str) -> None:
        """
        Validate section name exists.

        Args:
            section: Section name to validate

        Raises:
            KeyError: If section name is invalid
        """
        if section not in ALL_SECTIONS:
            valid_sections = ", ".join(sorted(ALL_SECTIONS))
            raise KeyError(f"Invalid section '{section}'. Valid sections: {valid_sections}")

    def _invalidate_cache(self) -> None:
        """Invalidate cached tier totals."""
        self._cache_valid = False

    def _update_cache(self) -> None:
        """Update cached tier totals if invalidated."""
        if self._cache_valid:
            return

        self._hot_total_cached = sum(self._section_sizes[name] for name in HOT_SECTIONS)
        self._warm_total_cached = sum(self._section_sizes[name] for name in WARM_SECTIONS)
        self._cache_valid = True

    @staticmethod
    def _calculate_pressure(current: int, limit: int) -> PressureLevel:
        """
        Calculate pressure level from utilization.

        Args:
            current: Current size in bytes
            limit: Maximum limit in bytes

        Returns:
            PressureLevel based on utilization percentage
        """
        if limit <= 0:
            return PressureLevel.EMERGENCY

        utilization = current / limit

        if utilization >= CRITICAL_THRESHOLD_PCT:
            return PressureLevel.EMERGENCY
        elif utilization >= ELEVATED_THRESHOLD_PCT:
            return PressureLevel.CRITICAL
        elif utilization >= NORMAL_THRESHOLD_PCT:
            return PressureLevel.ELEVATED
        else:
            return PressureLevel.NORMAL

    # =========================================================================
    # READ OPERATIONS (Lock-Free)
    # =========================================================================

    def get_section_size(self, section: str) -> int:
        """
        Get current size of a section in bytes.

        Args:
            section: Section name (e.g., 'beliefs_active')

        Returns:
            int: Current size in bytes

        Raises:
            KeyError: If section name is invalid

        Performance: O(1), lock-free
        """
        self._validate_section(section)
        return self._section_sizes[section]

    def get_tier_size(self, tier: str) -> int:
        """
        Get total size of a tier in bytes.

        Args:
            tier: Tier name ('hot' or 'warm')

        Returns:
            int: Total size of all sections in tier

        Raises:
            ValueError: If tier name is invalid

        Performance: O(1) with caching, O(n) on cache miss
        """
        tier_lower = tier.lower()

        if tier_lower not in ("hot", "warm"):
            raise ValueError(f"Invalid tier '{tier}'. Must be 'hot' or 'warm'.")

        self._update_cache()

        if tier_lower == "hot":
            return self._hot_total_cached
        else:
            return self._warm_total_cached

    def get_total_size(self) -> int:
        """
        Get total size across all sections.

        Returns:
            int: Total size in bytes (should never exceed 96KB in normal operation)

        Performance: O(1) with caching
        """
        self._update_cache()
        return self._hot_total_cached + self._warm_total_cached

    def get_pressure(self, tier: Optional[str] = None) -> PressureLevel:
        """
        Get current pressure level.

        Args:
            tier: Optional tier to check ('hot', 'warm', or None for overall)

        Returns:
            PressureLevel: NORMAL, ELEVATED, CRITICAL, or EMERGENCY

        Thresholds:
            NORMAL:    < 80% of limit
            ELEVATED:  80-90% of limit
            CRITICAL:  90-95% of limit
            EMERGENCY: > 95% of limit

        Example:
            # Check overall pressure
            pressure = tracker.get_pressure()

            # Check HOT tier pressure
            hot_pressure = tracker.get_pressure('hot')
        """
        if tier is None:
            # Overall pressure
            return self._calculate_pressure(self.get_total_size(), TOTAL_SIZE_LIMIT_BYTES)

        tier_lower = tier.lower()

        if tier_lower == "hot":
            return self._calculate_pressure(self.get_tier_size("hot"), HOT_SIZE_LIMIT_BYTES)
        elif tier_lower == "warm":
            return self._calculate_pressure(self.get_tier_size("warm"), WARM_SIZE_LIMIT_BYTES)
        else:
            raise ValueError(f"Invalid tier '{tier}'. Must be 'hot', 'warm', or None.")

    def get_section_pressure(self, section: str) -> PressureLevel:
        """
        Get pressure level for a specific section.

        Args:
            section: Section name

        Returns:
            PressureLevel: Based on section's individual budget

        Raises:
            KeyError: If section name is invalid
        """
        self._validate_section(section)
        budget = SECTION_BUDGETS[section]
        current = self._section_sizes[section]
        return self._calculate_pressure(current, budget.max_bytes)

    def get_available_bytes(self, section: str) -> int:
        """
        Get remaining bytes available in a section.

        Args:
            section: Section name

        Returns:
            int: Bytes remaining before section budget exceeded.
                 May be negative if over budget.

        Raises:
            KeyError: If section name is invalid
        """
        self._validate_section(section)
        budget = SECTION_BUDGETS[section]
        return budget.max_bytes - self._section_sizes[section]

    def get_tier_available_bytes(self, tier: str) -> int:
        """
        Get remaining bytes available in a tier.

        Args:
            tier: Tier name ('hot' or 'warm')

        Returns:
            int: Bytes remaining before tier limit exceeded.
                 May be negative if over budget.

        Raises:
            ValueError: If tier name is invalid
        """
        tier_lower = tier.lower()

        if tier_lower == "hot":
            return HOT_SIZE_LIMIT_BYTES - self.get_tier_size("hot")
        elif tier_lower == "warm":
            return WARM_SIZE_LIMIT_BYTES - self.get_tier_size("warm")
        else:
            raise ValueError(f"Invalid tier '{tier}'. Must be 'hot' or 'warm'.")

    def get_total_available_bytes(self) -> int:
        """
        Get remaining bytes available overall.

        Returns:
            int: Bytes remaining before 96KB limit.
                 May be negative if over budget.
        """
        return TOTAL_SIZE_LIMIT_BYTES - self.get_total_size()

    def get_budget(self, section: str) -> SectionBudget:
        """
        Get the budget specification for a section.

        Args:
            section: Section name

        Returns:
            SectionBudget: Budget specification for the section

        Raises:
            KeyError: If section name is invalid
        """
        self._validate_section(section)
        return SECTION_BUDGETS[section]

    def get_eviction_candidates(self, tier: str) -> List[Tuple[str, int, int]]:
        """
        Get sections eligible for eviction, sorted by priority.

        Args:
            tier: Tier name ('hot' or 'warm')

        Returns:
            List of (section_name, current_size, eviction_priority) tuples,
            sorted by eviction_priority (lowest first = evict first).
            Excludes NEVER EVICT sections.

        Raises:
            ValueError: If tier name is invalid
        """
        tier_lower = tier.lower()

        if tier_lower == "hot":
            sections = HOT_SECTIONS
        elif tier_lower == "warm":
            sections = WARM_SECTIONS
        else:
            raise ValueError(f"Invalid tier '{tier}'. Must be 'hot' or 'warm'.")

        candidates = []
        for name in sections:
            budget = SECTION_BUDGETS[name]
            if budget.eviction_priority is not None:
                candidates.append((name, self._section_sizes[name], budget.eviction_priority))

        # Sort by eviction_priority (lowest first = evict first)
        candidates.sort(key=lambda x: x[2])
        return candidates

    def get_snapshot(self) -> SizeSnapshot:
        """
        Get complete snapshot of all sizes.

        Returns:
            SizeSnapshot with all metrics and pressure levels.

        Thread Safety: Creates consistent snapshot of current state.
        """
        import time

        self._update_cache()

        hot_total = self._hot_total_cached
        warm_total = self._warm_total_cached
        total = hot_total + warm_total

        # Calculate utilizations
        hot_util = hot_total / HOT_SIZE_LIMIT_BYTES if HOT_SIZE_LIMIT_BYTES > 0 else 0
        warm_util = warm_total / WARM_SIZE_LIMIT_BYTES if WARM_SIZE_LIMIT_BYTES > 0 else 0
        total_util = total / TOTAL_SIZE_LIMIT_BYTES if TOTAL_SIZE_LIMIT_BYTES > 0 else 0

        return SizeSnapshot(
            sections=self._section_sizes.copy(),
            hot_total=hot_total,
            warm_total=warm_total,
            total=total,
            hot_pressure=self._calculate_pressure(hot_total, HOT_SIZE_LIMIT_BYTES),
            warm_pressure=self._calculate_pressure(warm_total, WARM_SIZE_LIMIT_BYTES),
            overall_pressure=self._calculate_pressure(total, TOTAL_SIZE_LIMIT_BYTES),
            hot_utilization_pct=hot_util,
            warm_utilization_pct=warm_util,
            total_utilization_pct=total_util,
            timestamp_ns=time.time_ns(),
        )

    # =========================================================================
    # WRITE OPERATIONS (Thread-Safe with Lock)
    # =========================================================================

    def update(self, section: str, delta_bytes: int) -> int:
        """
        Update section size after mutation.

        Args:
            section: Section name
            delta_bytes: Change in bytes (positive = growth, negative = shrink)

        Returns:
            int: New section size after update

        Raises:
            KeyError: If section name is invalid

        Thread Safety:
            Uses lock for atomic update. Should only be called by single writer
            (after MutationGuard approval).
        """
        self._validate_section(section)

        with self._lock:
            old_size = self._section_sizes[section]
            new_size = old_size + delta_bytes

            # Ensure non-negative (clamp to 0)
            if new_size < 0:
                logger.warning(
                    "Section '%s' size would go negative (%d + %d = %d), clamping to 0",
                    section,
                    old_size,
                    delta_bytes,
                    new_size,
                )
                new_size = 0

            self._section_sizes[section] = new_size
            self._invalidate_cache()

            # Check for pressure transitions (detailed debugging)
            budget = SECTION_BUDGETS[section]
            old_pressure = self._calculate_pressure(old_size, budget.max_bytes)
            new_pressure = self._calculate_pressure(new_size, budget.max_bytes)
            if old_pressure != new_pressure:
                logger.info(
                    "Pressure transition: section='%s' %s -> %s (size=%dB/%dB)",
                    section,
                    old_pressure.value,
                    new_pressure.value,
                    new_size,
                    budget.max_bytes,
                )

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "Updated section '%s': %d -> %d (delta=%+d)",
                    section,
                    old_size,
                    new_size,
                    delta_bytes,
                )

            return new_size

    def set_section_size(self, section: str, size_bytes: int) -> None:
        """
        Set absolute size for a section (used during reconstruction).

        Args:
            section: Section name
            size_bytes: Absolute size in bytes

        Raises:
            KeyError: If section name is invalid
            ValueError: If size_bytes is negative

        Thread Safety: Uses lock for atomic update.
        """
        self._validate_section(section)

        if size_bytes < 0:
            raise ValueError(f"size_bytes must be >= 0, got {size_bytes}")

        with self._lock:
            old_size = self._section_sizes[section]
            self._section_sizes[section] = size_bytes
            self._invalidate_cache()

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "Set section '%s': %d -> %d",
                    section,
                    old_size,
                    size_bytes,
                )

    def reset(self) -> None:
        """
        Reset all section sizes to 0.

        Use case: Starting fresh session or after full eviction.

        Thread Safety: Uses lock for atomic reset.
        """
        with self._lock:
            for name in self._section_sizes:
                self._section_sizes[name] = 0
            self._hot_total_cached = 0
            self._warm_total_cached = 0
            self._cache_valid = True

            logger.info("SizeTracker reset: all sections set to 0 bytes")

    def bulk_update(self, updates: Dict[str, int]) -> None:
        """
        Apply multiple size updates atomically.

        Args:
            updates: Dict of section name to delta_bytes

        Raises:
            KeyError: If any section name is invalid

        Thread Safety: Uses lock for atomic batch update.

        Example:
            tracker.bulk_update({
                "beliefs_active": 1024,
                "scoreboard": -512,
            })
        """
        # Validate all sections first
        for section in updates:
            self._validate_section(section)

        with self._lock:
            for section, delta in updates.items():
                old_size = self._section_sizes[section]
                new_size = max(0, old_size + delta)
                self._section_sizes[section] = new_size

            self._invalidate_cache()

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Bulk update applied: %s", updates)

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def is_over_budget(self, section: Optional[str] = None) -> bool:
        """
        Check if section, tier, or total is over budget.

        Args:
            section: Optional section name. If None, checks total.

        Returns:
            True if over budget, False otherwise.
        """
        if section is not None:
            self._validate_section(section)
            budget = SECTION_BUDGETS[section]
            return self._section_sizes[section] > budget.max_bytes

        return self.get_total_size() > TOTAL_SIZE_LIMIT_BYTES

    def can_evict(self, section: str) -> bool:
        """
        Check if a section can be evicted.

        Args:
            section: Section name

        Returns:
            True if section can be evicted (has eviction_priority),
            False if NEVER EVICT.

        Raises:
            KeyError: If section name is invalid
        """
        self._validate_section(section)
        return section not in NEVER_EVICT_SECTIONS

    def __repr__(self) -> str:
        """Return string representation."""
        snapshot = self.get_snapshot()
        return (
            f"SizeTracker("
            f"total={snapshot.total}/{TOTAL_SIZE_LIMIT_BYTES}, "
            f"hot={snapshot.hot_total}/{HOT_SIZE_LIMIT_BYTES}, "
            f"warm={snapshot.warm_total}/{WARM_SIZE_LIMIT_BYTES}, "
            f"pressure={snapshot.overall_pressure.value})"
        )


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    "PressureLevel",
    "Tier",
    "SectionBudget",
    "SizeSnapshot",
    "SizeTracker",
    "SECTION_BUDGETS",
    "HOT_SECTIONS",
    "WARM_SECTIONS",
    "NEVER_EVICT_SECTIONS",
    "ALL_SECTIONS",
    "TOTAL_SIZE_LIMIT_BYTES",
    "HOT_SIZE_LIMIT_BYTES",
    "WARM_SIZE_LIMIT_BYTES",
    "NORMAL_THRESHOLD_PCT",
    "ELEVATED_THRESHOLD_PCT",
    "CRITICAL_THRESHOLD_PCT",
]
