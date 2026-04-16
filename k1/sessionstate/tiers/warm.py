"""
WarmTier - WARM Tier Manager
=============================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.4 Implement Tier Managers
ISSUE: 2.4.2 (WarmTier)

ADRs:
- ADR-0017 series: SessionState 6-Section Design
- ADR-0018 series: 3-Tier Eviction Strategy

==============================================================================
SPECIFICATION
==============================================================================

PURPOSE:
    Manage WARM tier sections (evictable to LOCAL COLD).
    Coordinate 48KB budget across 4 sections.

TOTAL BUDGET: 48KB (49152 bytes)

SECTIONS (with eviction priority):
    - telemetry:       8KB  (priority 1 - FIRST to evict)
    - beliefs_history: 12KB (priority 2)
    - history_recent:  20KB (priority 3)
    - persona:         8KB  (priority 4 - LAST to evict)

EVICTION:
    When over budget, evict by priority order.
    Evicted data goes to LOCAL COLD.

PROMOTION:
    Some items can promote back to HOT:
    - beliefs_history -> beliefs_active (if frequently accessed)

OPERATIONS:
    - get_section(name): Get section by name
    - accept_demoted(from_section, items): Accept demoted items
    - get_eviction_candidates(): Get items to evict
    - evict(target_bytes): Evict items from section
    - get_pressure(): Get pressure level
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterator, List, Optional, Union

from ..config import SessionStateConfig
from ..sections import (
    ArtifactsWarmSection,
    BeliefsHistorySection,
    HistoryRecentSection,
    PersonaSection,
    TelemetrySection,
)

if TYPE_CHECKING:
    from ..local_cold import LocalColdArchive

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS (config-backed: sessionstate.tiers.*)
# =============================================================================

# Budget in bytes
WARM_BUDGET_BYTES: int = 49152  # config: sessionstate.tiers.warm_budget_bytes

# Section budgets
SECTION_BUDGETS: Dict[str, int] = {
    "telemetry": 8 * 1024,  # 8KB
    "beliefs_history": 12 * 1024,  # 12KB
    "history_recent": 20 * 1024,  # 20KB
    "persona": 8 * 1024,  # 8KB
    "artifacts_warm": 8 * 1024,  # 8KB (config: artifacts_warm)
}

# Eviction order (first to evict first, by priority number)
# Lower priority number = evict first
EVICTION_ORDER: List[str] = [
    "telemetry",  # Priority 1 - first to evict
    "artifacts_warm",  # Priority 2 - evict after telemetry
    "beliefs_history",  # Priority 3
    "history_recent",  # Priority 4
    "persona",  # Priority 5 - last to evict
]

# Eviction priorities (lower = evict first)
EVICTION_PRIORITIES: Dict[str, int] = {
    "telemetry": 1,
    "artifacts_warm": 2,
    "beliefs_history": 3,
    "history_recent": 4,
    "persona": 5,
}

# Demotion acceptance mapping: HOT section -> WARM section
DEMOTION_TARGETS: Dict[str, str] = {
    "beliefs_active": "beliefs_history",
    "history_active": "history_recent",
    "task_artifacts": "artifacts_warm",
}

# All WARM section names
WARM_SECTION_NAMES: List[str] = [
    "telemetry",
    "beliefs_history",
    "history_recent",
    "persona",
    "artifacts_warm",
]


class WarmPressureLevel(str, Enum):
    """WARM tier pressure levels."""

    NORMAL = "normal"  # <80%
    ELEVATED = "elevated"  # 80-90%
    HIGH = "high"  # 90-95%
    CRITICAL = "critical"  # >95%


# Pressure thresholds (config-backed: sessionstate.tiers.*_threshold_pct)
NORMAL_THRESHOLD: float = 0.80
ELEVATED_THRESHOLD: float = 0.90
HIGH_THRESHOLD: float = 0.95


@dataclass
class EvictionCandidate:
    """
    A candidate item for eviction to LOCAL COLD.

    Attributes:
        section: Source section name
        key: Item identifier
        data: The data to be evicted
        size_bytes: Estimated size in bytes
        priority: Eviction priority (lower = evict first)
        reason: Why this item is a candidate
    """

    section: str
    key: str
    data: Any
    size_bytes: int
    priority: int
    reason: str = ""

    def __repr__(self) -> str:
        return (
            f"EvictionCandidate(section='{self.section}', "
            f"key='{self.key}', size={self.size_bytes}B, priority={self.priority})"
        )


@dataclass
class EvictionResult:
    """
    Result of an eviction operation.

    Attributes:
        success: Whether eviction completed successfully
        items_evicted: Number of items evicted
        bytes_freed: Bytes freed from WARM tier
        new_pressure: Pressure level after eviction
        candidates: Candidates that were evicted
        duration_ms: Time taken in milliseconds
        error: Error message if failed
    """

    success: bool
    items_evicted: int
    bytes_freed: int
    new_pressure: WarmPressureLevel
    candidates: List[EvictionCandidate] = field(default_factory=list)
    duration_ms: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "items_evicted": self.items_evicted,
            "bytes_freed": self.bytes_freed,
            "new_pressure": self.new_pressure.value,
            "candidates_count": len(self.candidates),
            "duration_ms": round(self.duration_ms, 3),
            "error": self.error,
        }

    @staticmethod
    def failure(error: str, duration_ms: float = 0.0) -> EvictionResult:
        """Create a failure result."""
        return EvictionResult(
            success=False,
            items_evicted=0,
            bytes_freed=0,
            new_pressure=WarmPressureLevel.CRITICAL,
            error=error,
            duration_ms=duration_ms,
        )

    @staticmethod
    def no_candidates() -> EvictionResult:
        """Create result for no eviction candidates."""
        return EvictionResult(
            success=True,
            items_evicted=0,
            bytes_freed=0,
            new_pressure=WarmPressureLevel.NORMAL,
        )


@dataclass
class DemotedItem:
    """
    An item demoted from HOT tier to WARM tier.

    Attributes:
        source_section: Source HOT section name
        target_section: Target WARM section name
        key: Item identifier
        data: The demoted data
        size_bytes: Size in bytes
    """

    source_section: str
    target_section: str
    key: str
    data: Any
    size_bytes: int = 0


@dataclass
class PromotionCandidate:
    """
    A candidate item for promotion back to HOT tier.

    Attributes:
        section: Source WARM section name
        target_section: Target HOT section name
        key: Item identifier
        data: The data to promote
        access_count: Number of times accessed
        reason: Why this item should be promoted
    """

    section: str
    target_section: str
    key: str
    data: Any
    access_count: int = 0
    reason: str = ""


@dataclass
class WarmSnapshot:
    """
    Snapshot of WarmTier state.

    Useful for monitoring and debugging.
    """

    total_size: int
    budget_bytes: int
    utilization_pct: float
    pressure: WarmPressureLevel
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
    TelemetrySection,
    BeliefsHistorySection,
    HistoryRecentSection,
    PersonaSection,
]


class WarmTier:
    """
    WARM tier manager.

    Manages 4 WARM sections with a combined 48KB budget.
    Coordinates eviction to LOCAL COLD when under pressure.
    Accepts demoted items from HOT tier.

    Budget: 48KB (49152 bytes)
    Sections: 4 (telemetry, beliefs_history, history_recent, persona)

    Eviction Priority (lower = evict first):
        1. telemetry (most expendable)
        2. beliefs_history
        3. history_recent
        4. persona (least expendable)

    Thread Safety:
        - Read operations are safe for concurrent access
        - Write operations (evict_if_needed) should be serialized
          through SessionStateManager

    Example:
        tier = WarmTier(session_id="abc-123")

        # Accept demoted beliefs from HOT
        tier.accept_demoted("beliefs_active", items)

        # Check pressure
        if tier.get_pressure() == WarmPressureLevel.HIGH:
            tier.evict_if_needed()

        # Get snapshot
        snapshot = tier.get_snapshot()
        print(snapshot.to_dict())
    """

    BUDGET_BYTES: int = WARM_BUDGET_BYTES  # config: sessionstate.tiers.warm_budget_bytes
    TIER_NAME: str = "warm"

    __slots__ = (
        "_ss_cfg",
        "_session_id",
        "_sections",
        "_created_at_ms",
        "_local_cold",
        "_eviction_callback",
    )

    def __init__(
        self,
        session_id: str = "",
        local_cold: Optional[LocalColdArchive] = None,
        eviction_callback: Optional[Callable[[str, bytes], bool]] = None,
        config: Optional[SessionStateConfig] = None,
    ) -> None:
        """
        Initialize WarmTier with all 4 sections.

        Args:
            session_id: Session UUID (for section initialization)
            local_cold: Optional LocalColdArchive for eviction
            eviction_callback: Optional callback for eviction (section, data) -> success
            config: Optional SessionStateConfig (defaults used if None)
        """
        self._ss_cfg = config or SessionStateConfig()
        self._session_id = session_id
        self._local_cold = local_cold
        self._eviction_callback = eviction_callback
        self._created_at_ms = int(time.time() * 1000)

        # Initialize all 5 sections
        self._sections: Dict[str, SectionType] = {
            "telemetry": TelemetrySection(),
            "beliefs_history": BeliefsHistorySection(),
            "history_recent": HistoryRecentSection(),
            "persona": PersonaSection(),
            "artifacts_warm": ArtifactsWarmSection(),
        }

        logger.info(
            "WarmTier initialized: %d sections, budget=%dKB (session=%s)",
            len(self._sections),
            self._ss_cfg.tiers.warm_budget_bytes // 1024,
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
            name: Section name (e.g., 'telemetry', 'beliefs_history')

        Returns:
            Section instance or None if not found

        Example:
            telemetry = tier.get_section("telemetry")
            if telemetry:
                telemetry.record_turn(turn_data)
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
            raise KeyError(f"Unknown WARM section: {name}")
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
        """Enable dict-like access: tier['telemetry']."""
        return self.get_section_strict(name)

    def __contains__(self, name: str) -> bool:
        """Enable 'in' operator: 'telemetry' in tier."""
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
            Total bytes used across all WARM sections
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
        if section is not None:
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

    def get_pressure(self) -> WarmPressureLevel:
        """
        Get current pressure level based on utilization.

        Returns:
            WarmPressureLevel enum value

        Thresholds:
            NORMAL:   < 80%
            ELEVATED: 80-90%
            HIGH:     90-95%
            CRITICAL: >= 95%
        """
        util = self.get_utilization()
        _cfg_t = self._ss_cfg.tiers
        if util < _cfg_t.normal_threshold_pct:
            return WarmPressureLevel.NORMAL
        elif util < _cfg_t.elevated_threshold_pct:
            return WarmPressureLevel.ELEVATED
        elif util < _cfg_t.critical_threshold_pct:
            return WarmPressureLevel.HIGH
        else:
            return WarmPressureLevel.CRITICAL

    def is_under_pressure(self) -> bool:
        """
        Check if tier is under pressure (ELEVATED or higher).

        Returns:
            True if pressure is ELEVATED, HIGH, or CRITICAL
        """
        return self.get_pressure() != WarmPressureLevel.NORMAL

    def needs_eviction(self) -> bool:
        """
        Check if eviction is needed (HIGH or CRITICAL pressure).

        Returns:
            True if pressure is HIGH or CRITICAL
        """
        pressure = self.get_pressure()
        return pressure in (WarmPressureLevel.HIGH, WarmPressureLevel.CRITICAL)

    # =========================================================================
    # Demotion Acceptance (from HOT tier)
    # =========================================================================

    def get_demotion_target(self, hot_section: str) -> Optional[str]:
        """
        Get the WARM section that accepts demotions from a HOT section.

        Args:
            hot_section: HOT section name

        Returns:
            WARM section name or None if no mapping exists
        """
        return DEMOTION_TARGETS.get(hot_section)

    def can_accept_demoted(self, hot_section: str, size_bytes: int = 0) -> bool:
        """
        Check if tier can accept demoted items from HOT.

        Args:
            hot_section: Source HOT section name
            size_bytes: Size of data to demote (optional)

        Returns:
            True if demotion can be accepted
        """
        target = self.get_demotion_target(hot_section)
        if not target:
            return False

        # Check if we have capacity
        if size_bytes > 0:
            available = self.get_available_bytes()
            return available >= size_bytes

        return True

    def accept_demoted(
        self,
        from_section: str,
        items: List[Dict[str, Any]],
    ) -> int:
        """
        Accept demoted items from HOT tier.

        Args:
            from_section: Source HOT section name
            items: List of demoted item dictionaries

        Returns:
            Number of items accepted

        Mapping:
            beliefs_active -> beliefs_history
            history_active -> history_recent

        Example:
            # Demote old beliefs from HOT to WARM
            demoted_beliefs = hot.get_demotion_candidates()
            count = warm.accept_demoted("beliefs_active", demoted_beliefs)
        """
        if not items:
            return 0

        target_section = DEMOTION_TARGETS.get(from_section)
        if not target_section:
            logger.warning(
                "No demotion target for section '%s'",
                from_section,
            )
            return 0

        section = self._sections.get(target_section)
        if not section:
            logger.error(
                "Target section '%s' not found",
                target_section,
            )
            return 0

        accepted = 0

        if target_section == "beliefs_history":
            # Accept demoted beliefs
            beliefs_section = self._sections.get("beliefs_history")
            if beliefs_section and hasattr(beliefs_section, "accept_demoted"):
                for item in items:
                    try:
                        beliefs_section.accept_demoted([item])  # type: ignore
                        accepted += 1
                    except Exception as e:
                        logger.warning("Failed to accept belief: %s", e)
            else:
                logger.warning("beliefs_history section missing accept_demoted method")

        elif target_section == "history_recent":
            # Accept demoted history (compressed turns)
            history_section = self._sections.get("history_recent")
            if history_section and hasattr(history_section, "add_compressed_turn"):
                for item in items:
                    try:
                        # Convert to CompressedTurn if needed
                        from ..sections.history_recent import CompressedTurn

                        if isinstance(item, CompressedTurn):
                            history_section.add_compressed_turn(item)  # type: ignore
                        elif isinstance(item, dict):
                            turn = CompressedTurn(
                                turn_id=item.get("turn_id", ""),
                                turn_number=item.get("turn_number", 0),
                                entities=item.get("entities", []),
                                intents=item.get("intents", []),
                                key_phrases=item.get("key_phrases", []),
                                timestamp_ms=item.get("timestamp_ms", 0),
                            )
                            history_section.add_compressed_turn(turn)  # type: ignore
                        accepted += 1
                    except Exception as e:
                        logger.warning("Failed to accept turn: %s", e)
            else:
                logger.warning("history_recent section missing add_compressed_turn method")

        logger.debug(
            "Accepted %d/%d demoted items from '%s' to '%s'",
            accepted,
            len(items),
            from_section,
            target_section,
        )
        return accepted

    # =========================================================================
    # Eviction
    # =========================================================================

    def get_evictable_sections(self) -> List[str]:
        """
        Get list of sections that can be evicted, in priority order.

        Returns:
            List of section names in eviction priority order
        """
        return EVICTION_ORDER.copy()

    def get_eviction_candidates(
        self,
        target_bytes: int = 0,
        max_candidates: int = 50,
    ) -> List[EvictionCandidate]:
        """
        Get items that can be evicted to LOCAL COLD.

        This method inspects sections in eviction priority order and
        returns items that should be evicted.

        Args:
            target_bytes: Bytes to free (0 = use pressure-based calculation)
            max_candidates: Maximum candidates to return

        Returns:
            List of EvictionCandidate objects, ordered by priority
        """
        if target_bytes == 0:
            # Calculate based on pressure
            util = self.get_utilization()
            if util <= self._ss_cfg.tiers.normal_threshold_pct:
                return []  # No eviction needed
            # Target getting back to 70% utilization
            current_size = self.get_total_size()
            target_size = int(self.BUDGET_BYTES * 0.70)
            target_bytes = current_size - target_size

        if target_bytes <= 0:
            return []

        candidates: List[EvictionCandidate] = []
        bytes_collected = 0

        for section_name in EVICTION_ORDER:
            if bytes_collected >= target_bytes:
                break

            if len(candidates) >= max_candidates:
                break

            section = self._sections.get(section_name)
            if not section:
                continue

            priority = EVICTION_PRIORITIES.get(section_name, 99)

            # Check if section has eviction candidates
            if hasattr(section, "get_eviction_candidates"):
                try:
                    section_candidates = section.get_eviction_candidates()  # type: ignore
                    for item in section_candidates:
                        if bytes_collected >= target_bytes:
                            break
                        if len(candidates) >= max_candidates:
                            break

                        item_bytes = item.get("size_bytes", 100)
                        candidates.append(
                            EvictionCandidate(
                                section=section_name,
                                key=item.get("id", item.get("key", str(len(candidates)))),
                                data=item,
                                size_bytes=item_bytes,
                                priority=priority,
                                reason="pressure",
                            )
                        )
                        bytes_collected += item_bytes
                except Exception as e:
                    logger.warning(
                        "Failed to get eviction candidates from %s: %s",
                        section_name,
                        e,
                    )

            # Fallback: use evict_partial if available
            elif hasattr(section, "can_evict") and section.can_evict():  # type: ignore
                # Estimate how much we can get from this section
                section_size = section.get_size_bytes()
                needed = min(target_bytes - bytes_collected, section_size // 2)
                if needed > 0:
                    candidates.append(
                        EvictionCandidate(
                            section=section_name,
                            key=f"{section_name}_partial",
                            data={"target_bytes": needed},
                            size_bytes=needed,
                            priority=priority,
                            reason="pressure_partial",
                        )
                    )
                    bytes_collected += needed

        return candidates

    def evict(
        self,
        target_bytes: int,
        reason: str = "pressure",
    ) -> EvictionResult:
        """
        Evict items from WARM tier to LOCAL COLD.

        Args:
            target_bytes: Bytes to free
            reason: Reason for eviction

        Returns:
            EvictionResult with details

        Note:
            This method archives data to LOCAL COLD before removing from memory.
            If local_cold is not set, data is discarded with a warning.
        """
        start_time = time.time()

        if target_bytes <= 0:
            return EvictionResult(
                success=True,
                items_evicted=0,
                bytes_freed=0,
                new_pressure=self.get_pressure(),
            )

        bytes_freed = 0
        items_evicted = 0
        evicted_candidates: List[EvictionCandidate] = []

        for section_name in EVICTION_ORDER:
            if bytes_freed >= target_bytes:
                break

            section = self._sections.get(section_name)
            if not section:
                continue

            # Check if section supports eviction
            if not hasattr(section, "can_evict") or not section.can_evict():  # type: ignore
                continue

            if not hasattr(section, "evict_partial"):
                continue

            # Calculate how much to evict from this section
            needed = target_bytes - bytes_freed
            section_size = section.get_size_bytes()
            to_evict = min(needed, section_size)

            if to_evict <= 0:
                continue

            try:
                # Evict from section
                evicted_data = section.evict_partial(to_evict)  # type: ignore

                if evicted_data and hasattr(evicted_data, "bytes_freed"):
                    freed = evicted_data.bytes_freed
                    bytes_freed += freed

                    # Archive to LOCAL COLD if available
                    if self._local_cold and freed > 0:
                        try:
                            serialized = section.to_flatbuffer()
                            self._local_cold.archive(
                                section=section_name,
                                data=serialized,
                                session_id=self._session_id,
                            )
                        except Exception as e:
                            logger.warning(
                                "Failed to archive evicted data to LOCAL COLD: %s",
                                e,
                            )
                    elif self._eviction_callback and freed > 0:
                        try:
                            serialized = section.to_flatbuffer()
                            self._eviction_callback(section_name, serialized)
                        except Exception as e:
                            logger.warning("Eviction callback failed: %s", e)

                    items_evicted += 1
                    evicted_candidates.append(
                        EvictionCandidate(
                            section=section_name,
                            key=f"{section_name}_eviction",
                            data={"evicted": True},
                            size_bytes=freed,
                            priority=EVICTION_PRIORITIES.get(section_name, 99),
                            reason=reason,
                        )
                    )

                    logger.debug(
                        "Evicted %d bytes from %s (target: %d)",
                        freed,
                        section_name,
                        target_bytes,
                    )

            except Exception as e:
                logger.error(
                    "Failed to evict from %s: %s",
                    section_name,
                    e,
                )

        duration_ms = (time.time() - start_time) * 1000

        return EvictionResult(
            success=True,
            items_evicted=items_evicted,
            bytes_freed=bytes_freed,
            new_pressure=self.get_pressure(),
            candidates=evicted_candidates,
            duration_ms=duration_ms,
        )

    def evict_if_needed(
        self,
        target_utilization: float = 0.70,
    ) -> EvictionResult:
        """
        Evict items if pressure is HIGH or CRITICAL.

        Args:
            target_utilization: Target utilization after eviction (default 70%)

        Returns:
            EvictionResult with details
        """
        if not self.needs_eviction():
            return EvictionResult.no_candidates()

        current_size = self.get_total_size()
        target_size = int(self.BUDGET_BYTES * target_utilization)
        target_bytes = current_size - target_size

        if target_bytes <= 0:
            return EvictionResult.no_candidates()

        return self.evict(target_bytes, reason="pressure")

    def set_local_cold(self, local_cold: LocalColdArchive) -> None:
        """
        Set the LOCAL COLD archive for eviction.

        Args:
            local_cold: LocalColdArchive instance
        """
        self._local_cold = local_cold

    def set_eviction_callback(
        self,
        callback: Callable[[str, bytes], bool],
    ) -> None:
        """
        Set a callback for eviction (alternative to LOCAL COLD).

        Args:
            callback: Function(section_name, data) -> success
        """
        self._eviction_callback = callback

    # =========================================================================
    # Promotion (to HOT tier)
    # =========================================================================

    def get_promotion_candidates(
        self,
        max_candidates: int = 5,
    ) -> List[PromotionCandidate]:
        """
        Get items that should be promoted back to HOT tier.

        Currently only beliefs_history supports promotion based on access count.

        Args:
            max_candidates: Maximum candidates to return

        Returns:
            List of PromotionCandidate objects
        """
        candidates: List[PromotionCandidate] = []

        # Check beliefs_history for frequently accessed items
        beliefs = self._sections.get("beliefs_history")
        if beliefs and hasattr(beliefs, "get_promotion_candidates"):
            try:
                section_candidates = beliefs.get_promotion_candidates(count=max_candidates)  # type: ignore
                for item in section_candidates:
                    candidates.append(
                        PromotionCandidate(
                            section="beliefs_history",
                            target_section="beliefs_active",
                            key=item.get("id", item.get("fact_id", "")),
                            data=item,
                            access_count=item.get("access_count", 0),
                            reason="frequently_accessed",
                        )
                    )
            except Exception as e:
                logger.warning("Failed to get promotion candidates: %s", e)

        return candidates[:max_candidates]

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
            try:
                result[name] = section.to_flatbuffer()
            except Exception as e:
                logger.error("Failed to serialize section '%s': %s", name, e)
                result[name] = b""
        return result

    def deserialize_all(self, data: Dict[str, bytes]) -> int:
        """
        Deserialize sections from FlatBuffer bytes.

        Args:
            data: Dictionary mapping section names to serialized bytes

        Returns:
            Number of sections successfully deserialized
        """
        count = 0
        for name, section_data in data.items():
            if name not in self._sections:
                logger.warning("Unknown section name during deserialize: %s", name)
                continue

            section = self._sections[name]
            if not section_data:
                continue

            try:
                if hasattr(section, "from_flatbuffer"):
                    section.from_flatbuffer(section_data)  # type: ignore
                    count += 1
            except Exception as e:
                logger.error(
                    "Failed to deserialize section '%s': %s",
                    name,
                    e,
                )
        return count

    # =========================================================================
    # Lifecycle
    # =========================================================================

    def clear_all(self) -> None:
        """Clear all sections."""
        for section in self._sections.values():
            section.clear()
        logger.debug("Cleared all WARM sections")

    def clear_section(self, name: str) -> bool:
        """
        Clear a specific section.

        Args:
            name: Section name

        Returns:
            True if section was cleared, False if not found
        """
        section = self._sections.get(name)
        if section is not None:
            section.clear()
            logger.debug("Cleared WARM section '%s'", name)
            return True
        return False

    # =========================================================================
    # Snapshot / Statistics
    # =========================================================================

    def get_snapshot(self) -> WarmSnapshot:
        """
        Get a snapshot of current tier state.

        Returns:
            WarmSnapshot with size, pressure, and section details
        """
        section_sizes = self.get_section_sizes()
        section_counts: Dict[str, int] = {}

        for name, section in self._sections.items():
            if hasattr(section, "__len__"):
                section_counts[name] = len(section)  # type: ignore
            elif hasattr(section, "count"):
                section_counts[name] = section.count  # type: ignore
            else:
                section_counts[name] = 0

        return WarmSnapshot(
            total_size=self.get_total_size(),
            budget_bytes=self.BUDGET_BYTES,
            utilization_pct=self.get_utilization(),
            pressure=self.get_pressure(),
            section_sizes=section_sizes,
            section_counts=section_counts,
            timestamp_ms=int(time.time() * 1000),
        )

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get detailed statistics.

        Returns:
            Dictionary with comprehensive tier statistics
        """
        snapshot = self.get_snapshot()
        return {
            "tier": self.TIER_NAME,
            "session_id": self._session_id,
            "total_size": snapshot.total_size,
            "budget_bytes": snapshot.budget_bytes,
            "available_bytes": self.get_available_bytes(),
            "utilization_pct": round(snapshot.utilization_pct * 100, 2),
            "pressure": snapshot.pressure.value,
            "section_count": len(self._sections),
            "sections": {
                name: {
                    "size_bytes": snapshot.section_sizes.get(name, 0),
                    "count": snapshot.section_counts.get(name, 0),
                    "eviction_priority": EVICTION_PRIORITIES.get(name, 99),
                }
                for name in self._sections
            },
            "eviction_order": EVICTION_ORDER,
            "created_at_ms": self._created_at_ms,
            "timestamp_ms": snapshot.timestamp_ms,
        }

    # =========================================================================
    # String Representation
    # =========================================================================

    def __repr__(self) -> str:
        return (
            f"WarmTier(session_id='{self._session_id[:8] if self._session_id else ''}...', "
            f"sections={len(self._sections)}, "
            f"size={self.get_total_size()}/{self.BUDGET_BYTES}B, "
            f"pressure={self.get_pressure().value})"
        )

    def __str__(self) -> str:
        util = self.get_utilization()
        return f"WarmTier: {util:.1%} utilized ({self.get_total_size()}/{self.BUDGET_BYTES} bytes)"


# =============================================================================
# Factory Function
# =============================================================================


def create_warm_tier(
    session_id: str = "",
    local_cold: Optional[LocalColdArchive] = None,
) -> WarmTier:
    """
    Factory function to create a WarmTier.

    Args:
        session_id: Session UUID
        local_cold: Optional LocalColdArchive for eviction

    Returns:
        Configured WarmTier instance
    """
    return WarmTier(
        session_id=session_id,
        local_cold=local_cold,
    )
