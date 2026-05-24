"""
HotTier - HOT CORE Tier Manager
================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.4 Implement Tier Managers
ISSUE: 2.4.1 (HotTier)

ADRs:
- ADR-0017 series: SessionState 6-Section Design
- ADR-0018 series: 3-Tier Eviction Strategy

==============================================================================
SPECIFICATION
==============================================================================

PURPOSE:
    Manage HOT CORE sections (always in memory).
    Coordinate 52KB budget across 10 sections.

TOTAL BUDGET: 52KB (53248 bytes)

SECTIONS (with individual budgets):
    - control:          8KB (NEVER demote)
    - beliefs_active:   8KB (demotes to beliefs_history)
    - scoreboard:       6KB
    - history_active:   8KB (demotes to history_recent)
    - clarifications:   4KB
    - affective_now:    4KB
    - narrative_active: 4KB
    - meta:             2KB (NEVER demote)
    - task_state:       4KB (NEVER demote)
    - task_artifacts:   4KB (demotes to artifacts_warm)

DEMOTION PAIRS:
    beliefs_active -> beliefs_history (WARM)
    history_active -> history_recent (WARM)
    task_artifacts -> artifacts_warm (WARM)

PRESSURE LEVELS:
    NORMAL:   < 80% utilization
    ELEVATED: 80-90% utilization
    HIGH:     90-95% utilization
    CRITICAL: > 95% utilization

OPERATIONS:
    - get_section(name): Get section by name
    - get_all_sections(): Get all sections
    - get_total_size(): Get total HOT size
    - get_pressure(): Get pressure level
    - demote_if_needed(): Trigger demotion if over pressure
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterator, List, Optional, Union

from ..config import SessionStateConfig
from ..sections import (
    AffectiveNowSection,
    BeliefsActiveSection,
    ClarificationsSection,
    ControlSection,
    GroundingSection,
    HistoryActiveSection,
    MetaSection,
    NarrativeActiveSection,
    ScoreboardSection,
    SpatialSection,
    TemporalSection,
)
from ..sections.task_artifacts import TaskArtifactsSection
from ..sections.task_state import TaskStateSection

if TYPE_CHECKING:
    from ..migration import MigrationEngine

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS (config-backed: sessionstate.tiers.*)
# =============================================================================

# Budget in bytes
HOT_BUDGET_BYTES: int = 53248  # config: sessionstate.tiers.hot_budget_bytes

# Section budgets (from sizetracker.py)
SECTION_BUDGETS: Dict[str, int] = {
    "control": 8 * 1024,
    "beliefs_active": 8 * 1024,
    "scoreboard": 6 * 1024,
    "history_active": 8 * 1024,
    "clarifications": 4 * 1024,
    "affective_now": 4 * 1024,
    "narrative_active": 4 * 1024,
    "meta": 2 * 1024,
    "temporal": 4 * 1024,
    "spatial": 4 * 1024,
    "grounding": 2 * 1024,
    "task_state": 4 * 1024,
    "task_artifacts": 4 * 1024,
}

# Sections that are ordered for demotion (lower index = demote first)
DEMOTE_ORDER: List[str] = [
    "history_active",  # 1: Oldest turns first
    "beliefs_active",  # 2: Previous turn facts
    "narrative_active",  # 3: Paused threads
    "task_artifacts",  # 4: Presented artifacts -> artifacts_warm
]

# Sections that can never be demoted
NEVER_DEMOTE: frozenset[str] = frozenset(
    ["control", "meta", "temporal", "spatial", "grounding", "task_state"]
)

# Demotion target pairs: HOT section -> WARM section
DEMOTE_TARGETS: Dict[str, str] = {
    "beliefs_active": "beliefs_history",
    "history_active": "history_recent",
    "task_artifacts": "artifacts_warm",
}

# All HOT section names
HOT_SECTION_NAMES: List[str] = [
    "control",
    "beliefs_active",
    "scoreboard",
    "history_active",
    "clarifications",
    "affective_now",
    "narrative_active",
    "meta",
    "temporal",
    "spatial",
    "grounding",
    "task_state",
    "task_artifacts",
]


class HotPressureLevel(str, Enum):
    """HOT tier pressure levels."""

    NORMAL = "normal"  # <80%
    ELEVATED = "elevated"  # 80-90%
    HIGH = "high"  # 90-95%
    CRITICAL = "critical"  # >95%


# Pressure thresholds (config-backed: sessionstate.tiers.*_threshold_pct)
NORMAL_THRESHOLD: float = 0.80
ELEVATED_THRESHOLD: float = 0.90
HIGH_THRESHOLD: float = 0.95


@dataclass
class DemotionCandidate:
    """
    A candidate item for demotion to WARM tier.

    Attributes:
        section: Source section name
        target_section: Target WARM section name
        key: Item identifier (turn_id, fact_id, etc.)
        data: The data to be demoted
        size_bytes: Estimated size in bytes
        priority: Demotion priority (lower = demote first)
        reason: Why this item is a candidate
    """

    section: str
    target_section: str
    key: str
    data: Any
    size_bytes: int
    priority: int
    reason: str = ""

    def __repr__(self) -> str:
        return (
            f"DemotionCandidate(section='{self.section}' -> '{self.target_section}', "
            f"key='{self.key}', size={self.size_bytes}B, priority={self.priority})"
        )


@dataclass
class DemotionResult:
    """
    Result of a demotion operation.

    Attributes:
        success: Whether demotion completed successfully
        items_demoted: Number of items demoted
        bytes_freed: Bytes freed from HOT tier
        new_pressure: Pressure level after demotion
        candidates: Candidates that were demoted
        duration_ms: Time taken in milliseconds
        error: Error message if failed
    """

    success: bool
    items_demoted: int
    bytes_freed: int
    new_pressure: HotPressureLevel
    candidates: List[DemotionCandidate] = field(default_factory=list)
    duration_ms: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "items_demoted": self.items_demoted,
            "bytes_freed": self.bytes_freed,
            "new_pressure": self.new_pressure.value,
            "candidates_count": len(self.candidates),
            "duration_ms": round(self.duration_ms, 3),
            "error": self.error,
        }

    @staticmethod
    def failure(error: str, duration_ms: float = 0.0) -> DemotionResult:
        """Create a failure result."""
        return DemotionResult(
            success=False,
            items_demoted=0,
            bytes_freed=0,
            new_pressure=HotPressureLevel.CRITICAL,
            error=error,
            duration_ms=duration_ms,
        )

    @staticmethod
    def no_candidates() -> DemotionResult:
        """Create result for no demotion candidates."""
        return DemotionResult(
            success=True,
            items_demoted=0,
            bytes_freed=0,
            new_pressure=HotPressureLevel.NORMAL,
        )


@dataclass
class HotSnapshot:
    """
    Snapshot of HotTier state.

    Useful for monitoring and debugging.
    """

    total_size: int
    budget_bytes: int
    utilization_pct: float
    pressure: HotPressureLevel
    section_sizes: Dict[str, int]
    section_counts: Dict[str, int]
    timestamp_ms: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_size": self.total_size,
            "budget_bytes": self.budget_bytes,
            "utilization_pct": round(self.utilization_pct, 4),
            "pressure": self.pressure.value,
            "section_sizes": self.section_sizes.copy(),
            "section_counts": self.section_counts.copy(),
            "timestamp_ms": self.timestamp_ms,
        }


# Type alias for section union
SectionType = Union[
    ControlSection,
    BeliefsActiveSection,
    ScoreboardSection,
    HistoryActiveSection,
    ClarificationsSection,
    AffectiveNowSection,
    NarrativeActiveSection,
    MetaSection,
    TemporalSection,
    SpatialSection,
    GroundingSection,
    TaskStateSection,
    TaskArtifactsSection,
]


class HotTier:
    """
    HOT CORE tier manager.

    Manages 10 HOT sections with a combined 52KB budget.
    Coordinates demotion to WARM tier when under pressure.

    Budget: 52KB (53248 bytes)
    Sections: 10 (control, beliefs_active, scoreboard, history_active,
                  clarifications, affective_now, narrative_active, meta,
                  task_state, task_artifacts)

    Thread Safety:
        - Read operations are safe for concurrent access
        - Write operations (demote_if_needed) should be serialized
          through SessionStateManager

    Example:
        tier = HotTier(session_id="abc-123")

        # Get section
        control = tier.get_section("control")
        control.advance_turn()

        # Check pressure
        if tier.get_pressure() == HotPressureLevel.HIGH:
            tier.demote_if_needed()

        # Get snapshot
        snapshot = tier.get_snapshot()
        print(snapshot.to_dict())
    """

    BUDGET_BYTES: int = HOT_BUDGET_BYTES  # config: sessionstate.tiers.hot_budget_bytes
    TIER_NAME: str = "hot"

    __slots__ = (
        "_ss_cfg",
        "_session_id",
        "_sections",
        "_created_at_ms",
        "_migration_engine",
    )

    def __init__(
        self,
        session_id: str = "",
        migration_engine: Optional[MigrationEngine] = None,
        config: Optional[SessionStateConfig] = None,
    ) -> None:
        """
        Initialize HotTier with all 10 sections.

        Args:
            session_id: Session UUID (for section initialization)
            migration_engine: Optional MigrationEngine for demotion operations
            config: Optional SessionStateConfig (defaults used if None)
        """
        self._ss_cfg = config or SessionStateConfig()
        self._session_id = session_id
        self._migration_engine = migration_engine
        self._created_at_ms = int(time.time() * 1000)

        # Initialize all 10 sections
        self._sections: Dict[str, SectionType] = {
            "control": ControlSection(session_id=session_id),
            "beliefs_active": BeliefsActiveSection(session_id=session_id),
            "scoreboard": ScoreboardSection(),
            "history_active": HistoryActiveSection(),
            "clarifications": ClarificationsSection(),
            "affective_now": AffectiveNowSection(),
            "narrative_active": NarrativeActiveSection(),
            "meta": MetaSection(session_id=session_id),
            "temporal": TemporalSection(session_id=session_id),
            "spatial": SpatialSection(session_id=session_id),
            "grounding": GroundingSection(session_id=session_id),
            "task_state": TaskStateSection(),
            "task_artifacts": TaskArtifactsSection(),
        }

        logger.info(
            "HotTier initialized: %d sections, budget=%dKB (session=%s)",
            len(self._sections),
            self._ss_cfg.tiers.hot_budget_bytes // 1024,
            session_id[:8] if session_id else "none",
        )

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def tier_name(self) -> str:
        """Tier name identifier."""
        return self.TIER_NAME

    @property
    def budget_bytes(self) -> int:
        """Total tier budget in bytes."""
        return self.BUDGET_BYTES

    @property
    def session_id(self) -> str:
        """Session identifier."""
        return self._session_id

    @property
    def section_count(self) -> int:
        """Number of sections in this tier."""
        return len(self._sections)

    # =========================================================================
    # Section Access
    # =========================================================================

    def get_section(self, name: str) -> Optional[SectionType]:
        """
        Get section by name.

        Args:
            name: Section name (e.g., 'control', 'beliefs_active')

        Returns:
            Section instance or None if not found

        Example:
            control = tier.get_section("control")
            if control:
                control.advance_turn()
        """
        return self._sections.get(name)

    def get_section_strict(self, name: str) -> SectionType:
        """
        Get section by name, raising KeyError if not found.

        Args:
            name: Section name

        Returns:
            Section instance

        Raises:
            KeyError: If section name is invalid
        """
        if name not in self._sections:
            raise KeyError(f"Unknown HOT section: {name}")
        return self._sections[name]

    def get_all_sections(self) -> Dict[str, SectionType]:
        """
        Get all sections.

        Returns:
            Dictionary mapping section names to section instances
        """
        return self._sections.copy()

    def get_section_names(self) -> List[str]:
        """
        Get list of section names.

        Returns:
            List of section name strings
        """
        return list(self._sections.keys())

    def __getitem__(self, name: str) -> SectionType:
        """Enable dict-like access: tier['control']."""
        return self.get_section_strict(name)

    def __contains__(self, name: str) -> bool:
        """Enable 'in' operator: 'control' in tier."""
        return name in self._sections

    def __iter__(self) -> Iterator[str]:
        """Enable iteration over section names."""
        return iter(self._sections)

    def __len__(self) -> int:
        """Return number of sections."""
        return len(self._sections)

    # =========================================================================
    # Size Tracking
    # =========================================================================

    def get_total_size(self) -> int:
        """
        Get total size of all sections in bytes.

        Returns:
            Total bytes used across all HOT sections
        """
        total = 0
        for section in self._sections.values():
            total += section.get_size_bytes()
        return total

    def get_section_size(self, name: str) -> int:
        """
        Get size of a specific section.

        Args:
            name: Section name

        Returns:
            Section size in bytes, or 0 if not found
        """
        section = self._sections.get(name)
        if section:
            return section.get_size_bytes()
        return 0

    def get_section_sizes(self) -> Dict[str, int]:
        """
        Get size of each section.

        Returns:
            Dictionary mapping section names to byte counts
        """
        return {name: section.get_size_bytes() for name, section in self._sections.items()}

    def get_available_bytes(self) -> int:
        """
        Get available bytes before budget limit.

        Returns:
            Number of bytes available
        """
        return max(0, self.BUDGET_BYTES - self.get_total_size())

    def get_utilization(self) -> float:
        """
        Get tier utilization as percentage.

        Returns:
            Float 0.0-1.0 representing utilization
        """
        if self.BUDGET_BYTES == 0:
            return 0.0
        return self.get_total_size() / self.BUDGET_BYTES

    # =========================================================================
    # Pressure Assessment
    # =========================================================================

    def get_pressure(self) -> HotPressureLevel:
        """
        Get current pressure level based on utilization.

        Returns:
            HotPressureLevel enum value

        Thresholds:
            NORMAL:   < 80%
            ELEVATED: 80-90%
            HIGH:     90-95%
            CRITICAL: >= 95%
        """
        util = self.get_utilization()
        _cfg_t = self._ss_cfg.tiers
        if util < _cfg_t.normal_threshold_pct:
            return HotPressureLevel.NORMAL
        elif util < _cfg_t.elevated_threshold_pct:
            return HotPressureLevel.ELEVATED
        elif util < _cfg_t.critical_threshold_pct:
            return HotPressureLevel.HIGH
        else:
            return HotPressureLevel.CRITICAL

    def is_under_pressure(self) -> bool:
        """
        Check if tier is under pressure (ELEVATED or higher).

        Returns:
            True if pressure is ELEVATED, HIGH, or CRITICAL
        """
        return self.get_pressure() != HotPressureLevel.NORMAL

    def needs_demotion(self) -> bool:
        """
        Check if demotion is needed (HIGH or CRITICAL pressure).

        Returns:
            True if pressure is HIGH or CRITICAL
        """
        pressure = self.get_pressure()
        return pressure in (HotPressureLevel.HIGH, HotPressureLevel.CRITICAL)

    # =========================================================================
    # Demotion
    # =========================================================================

    def get_demotable_sections(self) -> List[str]:
        """
        Get list of sections that can be demoted, in priority order.

        Returns:
            List of section names that can demote (have WARM targets)
        """
        return [name for name in DEMOTE_ORDER if name in DEMOTE_TARGETS]

    def get_demotion_candidates(self, max_candidates: int = 10) -> List[DemotionCandidate]:
        """
        Get items that can be demoted to WARM tier.

        This method inspects demotable sections (beliefs_active, history_active)
        and returns items that should be demoted.

        Args:
            max_candidates: Maximum number of candidates to return

        Returns:
            List of DemotionCandidate objects, ordered by priority
        """
        candidates: List[DemotionCandidate] = []
        priority = 0

        for section_name in DEMOTE_ORDER:
            if section_name not in DEMOTE_TARGETS:
                continue

            section = self._sections.get(section_name)
            if not section:
                continue

            target_section = DEMOTE_TARGETS[section_name]

            # Check history_active for demotable turns
            if section_name == "history_active":
                history = self._sections.get("history_active")
                if history and hasattr(history, "get_demote_candidates"):
                    # Get oldest turns ready for demotion
                    demote_items = history.get_demote_candidates()  # type: ignore
                    for item in demote_items:
                        priority += 1
                        candidates.append(
                            DemotionCandidate(
                                section=section_name,
                                target_section=target_section,
                                key=item.get("turn_id", str(priority)),
                                data=item,
                                size_bytes=item.get("size_bytes", 500),
                                priority=priority,
                                reason="history_overflow",
                            )
                        )
                        if len(candidates) >= max_candidates:
                            break

            # Check beliefs_active for demotable facts
            elif section_name == "beliefs_active":
                beliefs = self._sections.get("beliefs_active")
                if beliefs and hasattr(beliefs, "get_demote_candidates"):
                    demote_items = beliefs.get_demote_candidates()  # type: ignore
                    for item in demote_items:
                        priority += 1
                        candidates.append(
                            DemotionCandidate(
                                section=section_name,
                                target_section=target_section,
                                key=item.get("fact_id", str(priority)),
                                data=item,
                                size_bytes=item.get("size_bytes", 200),
                                priority=priority,
                                reason="turn_complete",
                            )
                        )
                        if len(candidates) >= max_candidates:
                            break

            if len(candidates) >= max_candidates:
                break

        return candidates

    def demote_if_needed(
        self,
        target_utilization: float = 0.70,
        demote_callback: Optional[Callable[[List[DemotionCandidate]], int]] = None,
    ) -> DemotionResult:
        """
        Trigger demotion if over pressure.

        This method checks current pressure and demotes items to WARM
        until utilization drops below target.

        Args:
            target_utilization: Target utilization after demotion (default 70%)
            demote_callback: Optional callback to execute demotion.
                           Receives candidates, returns bytes freed.
                           If None, uses MigrationEngine if available.

        Returns:
            DemotionResult with details of operation

        Note:
            The actual demotion is handled by either:
            1. The provided demote_callback
            2. The configured MigrationEngine
            3. Returns failure if neither is available
        """
        start_time = time.perf_counter()
        current_pressure = self.get_pressure()

        # Check if demotion needed
        if current_pressure == HotPressureLevel.NORMAL:
            return DemotionResult(
                success=True,
                items_demoted=0,
                bytes_freed=0,
                new_pressure=current_pressure,
                duration_ms=(time.perf_counter() - start_time) * 1000,
            )

        # Get candidates
        candidates = self.get_demotion_candidates()
        if not candidates:
            return DemotionResult.no_candidates()

        # Execute demotion
        bytes_freed = 0
        items_demoted = 0

        if demote_callback:
            # Use provided callback
            bytes_freed = demote_callback(candidates)
            items_demoted = len(candidates) if bytes_freed > 0 else 0
        elif self._migration_engine:
            # Use MigrationEngine
            for candidate in candidates:
                result = self._migration_engine.demote(
                    section=candidate.section,
                    items=[
                        {
                            "key": candidate.key,
                            "data": candidate.data,
                            "size_bytes": candidate.size_bytes,
                        }
                    ],
                    trigger="pressure",
                )
                if result.success:
                    bytes_freed += result.bytes_freed
                    items_demoted += result.items_migrated

                # Check if we've freed enough
                if self.get_utilization() <= target_utilization:
                    break
        else:
            # No demotion mechanism available
            duration_ms = (time.perf_counter() - start_time) * 1000
            return DemotionResult.failure(
                error="No demotion mechanism available (no callback or MigrationEngine)",
                duration_ms=duration_ms,
            )

        duration_ms = (time.perf_counter() - start_time) * 1000
        new_pressure = self.get_pressure()

        logger.info(
            "HotTier demotion: freed %d bytes, demoted %d items, pressure: %s -> %s",
            bytes_freed,
            items_demoted,
            current_pressure.value,
            new_pressure.value,
        )

        return DemotionResult(
            success=True,
            items_demoted=items_demoted,
            bytes_freed=bytes_freed,
            new_pressure=new_pressure,
            candidates=candidates[:items_demoted],
            duration_ms=duration_ms,
        )

    def set_migration_engine(self, engine: MigrationEngine) -> None:
        """
        Set the migration engine for demotion operations.

        Args:
            engine: MigrationEngine instance
        """
        self._migration_engine = engine

    # =========================================================================
    # Serialization
    # =========================================================================

    def serialize_all(self) -> Dict[str, bytes]:
        """
        Serialize all sections to FlatBuffer bytes.

        Returns:
            Dictionary mapping section names to serialized bytes
        """
        result: Dict[str, bytes] = {}
        for name, section in self._sections.items():
            result[name] = section.to_flatbuffer()
        return result

    def deserialize_all(self, data: Dict[str, bytes]) -> int:
        """
        Deserialize all sections from FlatBuffer bytes.

        Args:
            data: Dictionary mapping section names to serialized bytes

        Returns:
            Number of sections deserialized
        """
        count = 0
        for name, section_data in data.items():
            section = self._sections.get(name)
            if section and hasattr(section, "from_flatbuffer"):
                # Note: from_flatbuffer is a classmethod that returns new instance
                # We need to replace the section with the new instance
                new_section = type(section).from_flatbuffer(section_data)
                self._sections[name] = new_section
                count += 1
        return count

    # =========================================================================
    # Lifecycle
    # =========================================================================

    def clear_all(self) -> None:
        """Clear all sections."""
        for section in self._sections.values():
            section.clear()
        logger.debug("HotTier cleared all sections")

    def clear_section(self, name: str) -> bool:
        """
        Clear a specific section.

        Args:
            name: Section name

        Returns:
            True if section was cleared, False if not found
        """
        section = self._sections.get(name)
        if section:
            section.clear()
            return True
        return False

    # =========================================================================
    # Snapshot
    # =========================================================================

    def get_snapshot(self) -> HotSnapshot:
        """
        Get current state snapshot.

        Returns:
            HotSnapshot with current tier state
        """
        section_sizes: Dict[str, int] = {}
        section_counts: Dict[str, int] = {}

        for name, section in self._sections.items():
            section_sizes[name] = section.get_size_bytes()
            # Get item count if available
            if hasattr(section, "__len__"):
                section_counts[name] = len(section)  # type: ignore
            else:
                section_counts[name] = 0

        total_size = sum(section_sizes.values())
        utilization = total_size / self.BUDGET_BYTES if self.BUDGET_BYTES > 0 else 0.0

        return HotSnapshot(
            total_size=total_size,
            budget_bytes=self.BUDGET_BYTES,
            utilization_pct=utilization,
            pressure=self.get_pressure(),
            section_sizes=section_sizes,
            section_counts=section_counts,
            timestamp_ms=int(time.time() * 1000),
        )

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get tier statistics for monitoring.

        Returns:
            Dictionary with tier statistics
        """
        snapshot = self.get_snapshot()
        return {
            "tier": self.TIER_NAME,
            "total_size_bytes": snapshot.total_size,
            "budget_bytes": snapshot.budget_bytes,
            "available_bytes": self.get_available_bytes(),
            "utilization_pct": round(snapshot.utilization_pct * 100, 2),
            "pressure": snapshot.pressure.value,
            "section_count": len(self._sections),
            "sections": snapshot.section_sizes,
            "demotable_sections": self.get_demotable_sections(),
            "demotion_candidates_count": len(self.get_demotion_candidates()),
        }

    # =========================================================================
    # String Representations
    # =========================================================================

    def __repr__(self) -> str:
        """Detailed string representation."""
        return (
            f"HotTier(session='{self._session_id[:8] if self._session_id else 'none'}', "
            f"size={self.get_total_size()}/{self.BUDGET_BYTES}B, "
            f"pressure={self.get_pressure().value}, "
            f"sections={len(self._sections)})"
        )

    def __str__(self) -> str:
        """Human-readable string."""
        util = self.get_utilization() * 100
        return f"HotTier: {util:.1f}% utilized ({self.get_pressure().value})"


# =============================================================================
# Factory Function
# =============================================================================


def create_hot_tier(
    session_id: str = "",
    migration_engine: Optional[MigrationEngine] = None,
) -> HotTier:
    """
    Factory function to create a HotTier instance.

    Args:
        session_id: Session UUID
        migration_engine: Optional MigrationEngine for demotion

    Returns:
        Configured HotTier instance
    """
    return HotTier(session_id=session_id, migration_engine=migration_engine)
    return HotTier(session_id=session_id, migration_engine=migration_engine)
