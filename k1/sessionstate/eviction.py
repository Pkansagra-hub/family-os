"""
EvictionEngine - WARM Tier Eviction to LOCAL COLD
===================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.1 Kernel Services
ISSUE: 2.1.3

ADRs:
- ADR-0018 series: 3-Tier Eviction Strategy

DEPENDENCIES:
- SizeTracker (for capacity checks)
- MutationGuard (for section locking)
- LocalColdArchive (for archiving evicted data)

==============================================================================
SPECIFICATION
==============================================================================

PURPOSE:
    Evict data from WARM tier to LOCAL COLD (K1 SQLite) when capacity
    pressure exceeds thresholds. Ensures we never exceed 96KB total.

EVICTION PRIORITY (from README.md):
    Priority 1: telemetry     - First to evict (aggregate and drop raw)
    Priority 2: beliefs_history - Oldest facts archived
    Priority 3: history_recent  - Oldest compressed/summarized turns
    Priority 4: persona        - Lowest priority (usually static)

NEVER EVICT:
    - control section (HOT) - CRITICAL INVARIANT
    - meta section (HOT) - CRITICAL INVARIANT
    - If control evicted, orchestration crashes

EVICTION TARGETS:
    - WARM tier sections only (HOT demotes to WARM, doesn't evict)
    - Archive to LOCAL COLD (K1 SQLite)
    - K0 sync is optional/async (edge-first design)

==============================================================================
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol

from .config import SessionStateConfig
from .sizetracker import (
    NEVER_EVICT_SECTIONS,
    SECTION_BUDGETS,
    TOTAL_SIZE_LIMIT_BYTES,
    WARM_SECTIONS,
    WARM_SIZE_LIMIT_BYTES,
    PressureLevel,
    SizeTracker,
)

if TYPE_CHECKING:
    from .guard import MutationGuard
    from .local_cold import LocalColdArchive

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS (config-backed: sessionstate.eviction.*)
# =============================================================================

# Target utilization after eviction (give headroom)
TARGET_UTILIZATION_AFTER_EVICTION: float = 0.70  # config: sessionstate.eviction.target_utilization

# Minimum bytes to evict per pass (avoid micro-evictions)
MIN_EVICTION_BYTES: int = 1024  # config: sessionstate.eviction.min_eviction_bytes

# Maximum eviction iterations to prevent infinite loops
MAX_EVICTION_ITERATIONS: int = 10  # config: sessionstate.eviction.max_eviction_iterations


class EvictionPriority(IntEnum):
    """
    Eviction priority (lower = evict first).

    Maps to SECTION_BUDGETS.eviction_priority for WARM sections.
    """

    TELEMETRY = 1  # First to evict (lowest value = highest eviction priority)
    ARTIFACTS_WARM = 2  # Evict after telemetry
    BELIEFS_HISTORY = 3
    HISTORY_RECENT = 4
    PERSONA = 10  # Last to evict (highest value)


# Section to eviction priority mapping (WARM only)
EVICTION_PRIORITIES: Dict[str, EvictionPriority] = {
    "telemetry": EvictionPriority.TELEMETRY,
    "artifacts_warm": EvictionPriority.ARTIFACTS_WARM,
    "beliefs_history": EvictionPriority.BELIEFS_HISTORY,
    "history_recent": EvictionPriority.HISTORY_RECENT,
    "persona": EvictionPriority.PERSONA,
}


class EvictionReason(str):
    """Eviction trigger reasons for diagnostics."""

    PRESSURE_ELEVATED = "pressure_elevated"
    PRESSURE_CRITICAL = "pressure_critical"
    PRESSURE_EMERGENCY = "pressure_emergency"
    MANUAL = "manual"
    PREEMPTIVE = "preemptive"


@dataclass
class EvictionCandidate:
    """
    A section that can be evicted.

    Attributes:
        section: Section name
        priority: Eviction priority (lower = evict first)
        current_bytes: Current size in bytes
        evictable_bytes: How many bytes can be evicted
        budget_bytes: Section budget limit
        utilization_pct: Current utilization percentage
    """

    section: str
    priority: EvictionPriority
    current_bytes: int
    evictable_bytes: int
    budget_bytes: int
    utilization_pct: float

    def __repr__(self) -> str:
        return (
            f"EvictionCandidate(section='{self.section}', priority={self.priority.name}, "
            f"current={self.current_bytes}B, evictable={self.evictable_bytes}B, "
            f"utilization={self.utilization_pct:.1%})"
        )


@dataclass
class EvictedItem:
    """
    Record of a single evicted item.

    Attributes:
        section: Source section
        archive_id: ID in LOCAL COLD (or None if not archived)
        bytes_freed: Bytes removed from WARM
        bytes_archived: Bytes stored in LOCAL COLD
        metadata: Additional eviction metadata
    """

    section: str
    archive_id: Optional[str]
    bytes_freed: int
    bytes_archived: int
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvictionResult:
    """
    Result of an eviction operation.

    Attributes:
        success: Whether eviction achieved target
        sections_evicted: List of sections that had data evicted
        bytes_freed: Total bytes freed from WARM
        bytes_archived: Total bytes archived to LOCAL COLD
        evicted_items: Details of each evicted item
        new_pressure: Pressure level after eviction
        iterations: Number of eviction passes
        duration_ms: Time taken for eviction
        reason: Why eviction was triggered
        error: Error message if failed
    """

    success: bool
    sections_evicted: List[str]
    bytes_freed: int
    bytes_archived: int
    evicted_items: List[EvictedItem]
    new_pressure: PressureLevel
    iterations: int
    duration_ms: float
    reason: str = ""
    error: Optional[str] = None

    def __repr__(self) -> str:
        status = "SUCCESS" if self.success else "FAILED"
        return (
            f"EvictionResult({status}: freed={self.bytes_freed}B, "
            f"archived={self.bytes_archived}B, sections={self.sections_evicted}, "
            f"pressure={self.new_pressure.value}, took={self.duration_ms:.2f}ms)"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "sections_evicted": self.sections_evicted,
            "bytes_freed": self.bytes_freed,
            "bytes_archived": self.bytes_archived,
            "evicted_items": [
                {
                    "section": item.section,
                    "archive_id": item.archive_id,
                    "bytes_freed": item.bytes_freed,
                    "bytes_archived": item.bytes_archived,
                    "metadata": item.metadata,
                }
                for item in self.evicted_items
            ],
            "new_pressure": self.new_pressure.value,
            "iterations": self.iterations,
            "duration_ms": round(self.duration_ms, 3),
            "reason": self.reason,
            "error": self.error,
        }


# =============================================================================
# SECTION DATA PROVIDER PROTOCOL
# =============================================================================


class ISectionDataProvider(Protocol):
    """
    Protocol for accessing section data for eviction.

    The EvictionEngine needs to read section data for archiving.
    This protocol abstracts the section access pattern.
    """

    def get_section_data(self, section: str) -> Optional[bytes]:
        """Get serialized section data for archiving."""
        ...

    def clear_section(self, section: str) -> int:
        """Clear section data, return bytes freed."""
        ...

    def get_evictable_data(self, section: str, target_bytes: int) -> tuple[bytes, int]:
        """
        Get partial data for eviction.

        Args:
            section: Section name
            target_bytes: Target bytes to evict

        Returns:
            Tuple of (data to archive, bytes that will be freed)
        """
        ...

    def remove_evicted_data(self, section: str, bytes_to_remove: int) -> int:
        """Remove data after archiving, return actual bytes freed."""
        ...


# =============================================================================
# EVICTION ENGINE
# =============================================================================


class EvictionEngine:
    """
    Manages eviction from WARM tier to LOCAL COLD.

    Eviction is triggered when WARM tier pressure exceeds thresholds.
    Data is archived to LOCAL COLD (K1 SQLite) before being removed.

    Thread Safety:
        - Uses MutationGuard.lock_section() during eviction
        - Eviction is NOT concurrent (single eviction at a time)
        - Multiple readers can read during eviction

    Performance:
        - get_eviction_candidates(): O(n) where n = WARM sections (4)
        - evict(): O(k * m) where k = sections evicted, m = items per section
        - Typically <10ms for standard eviction

    Invariants:
        - NEVER evict control or meta sections
        - ALWAYS archive before evicting
        - If archive fails, don't evict
        - Section is locked during eviction

    Example:
        engine = EvictionEngine(
            size_tracker=size_tracker,
            local_cold=local_cold,
            mutation_guard=mutation_guard,
        )

        # Check candidates
        candidates = engine.get_eviction_candidates()
        # [EvictionCandidate(section='telemetry', priority=1, ...), ...]

        # Evict to free 10KB
        result = engine.evict(target_bytes=10 * 1024)
        if result.success:
            print(f"Freed {result.bytes_freed} bytes")

    Attributes:
        _size_tracker: SizeTracker for capacity checks
        _local_cold: LocalColdArchive for archiving evicted data
        _mutation_guard: MutationGuard for section locking
        _section_provider: Optional provider for section data access
        _eviction_in_progress: Flag to prevent concurrent evictions
    """

    __slots__ = (
        "_ss_cfg",
        "_size_tracker",
        "_local_cold",
        "_mutation_guard",
        "_section_provider",
        "_eviction_in_progress",
        "_session_id",
    )

    def __init__(
        self,
        size_tracker: SizeTracker,
        local_cold: "LocalColdArchive",
        mutation_guard: Optional["MutationGuard"] = None,
        section_provider: Optional[ISectionDataProvider] = None,
        session_id: str = "",
        config: Optional[SessionStateConfig] = None,
    ) -> None:
        """
        Initialize EvictionEngine.

        Args:
            size_tracker: SizeTracker for capacity checks
            local_cold: LocalColdArchive for archiving evicted data
            mutation_guard: MutationGuard for section locking (optional for testing)
            section_provider: Provider for section data access (optional)
            session_id: Session ID for archive metadata
            config: Optional SessionStateConfig (defaults used if None)
        """
        self._ss_cfg = config or SessionStateConfig()
        self._size_tracker = size_tracker
        self._local_cold = local_cold
        self._mutation_guard = mutation_guard
        self._section_provider = section_provider
        self._eviction_in_progress = False
        self._session_id = session_id or str(uuid.uuid4())

        logger.info(
            "EvictionEngine initialized (session=%s, target_util=%.0f%%)",
            self._session_id[:8],
            self._ss_cfg.eviction.target_utilization * 100,
        )

    # =========================================================================
    # EVICTION CANDIDATES
    # =========================================================================

    def get_eviction_candidates(self) -> List[EvictionCandidate]:
        """
        Get list of sections that can be evicted, sorted by priority.

        Returns:
            List[EvictionCandidate]: Candidates in eviction order
                                     (priority 1 first, priority 4 last)

        Only WARM tier sections are evictable:
        - telemetry (priority 1)
        - beliefs_history (priority 2)
        - history_recent (priority 3)
        - persona (priority 10)
        """
        candidates: List[EvictionCandidate] = []

        for section in WARM_SECTIONS:
            # Skip NEVER_EVICT sections (should not exist in WARM, but safety check)
            if section in NEVER_EVICT_SECTIONS:
                continue

            budget = SECTION_BUDGETS[section]
            current = self._size_tracker.get_section_size(section)

            # Only include sections with data to evict
            if current > 0:
                # Get priority from mapping, or use budget's eviction_priority
                priority_val = budget.eviction_priority or 99
                priority = EVICTION_PRIORITIES.get(section, EvictionPriority(min(priority_val, 10)))

                candidates.append(
                    EvictionCandidate(
                        section=section,
                        priority=priority,
                        current_bytes=current,
                        evictable_bytes=current,  # Can evict all WARM data
                        budget_bytes=budget.max_bytes,
                        utilization_pct=current / budget.max_bytes if budget.max_bytes > 0 else 0,
                    )
                )

        # Sort by priority (lower = evict first)
        candidates.sort(key=lambda c: c.priority)

        return candidates

    # =========================================================================
    # EVICTION CORE
    # =========================================================================

    def evict(
        self,
        target_bytes: int,
        reason: str = EvictionReason.MANUAL,
    ) -> EvictionResult:
        """
        Evict data to free the specified number of bytes.

        EVICTION ALGORITHM:
        1. Check if eviction is already in progress
        2. Get candidates sorted by priority
        3. For each candidate (lowest priority number first):
           a. Lock section via MutationGuard
           b. Calculate how much to evict from this section
           c. Get data from section
           d. Archive to LOCAL COLD
           e. Remove from section
           f. Update SizeTracker
           g. Unlock section
           h. Check if target reached
        4. Return result

        Args:
            target_bytes: How many bytes to free (minimum)
            reason: Why eviction was triggered (for logging/events)

        Returns:
            EvictionResult: Success/failure with details

        Note:
            Caller should emit EvictionTriggeredEvent before calling
            and EvictionCompletedEvent after return.
        """
        start_time = time.perf_counter()

        # Prevent concurrent evictions
        if self._eviction_in_progress:
            logger.warning("Eviction already in progress, skipping")
            return EvictionResult(
                success=False,
                sections_evicted=[],
                bytes_freed=0,
                bytes_archived=0,
                evicted_items=[],
                new_pressure=self._get_current_pressure(),
                iterations=0,
                duration_ms=0,
                reason=reason,
                error="Eviction already in progress",
            )

        try:
            self._eviction_in_progress = True

            logger.info(
                "Starting eviction: target=%dB (%dKB), reason=%s",
                target_bytes,
                target_bytes // 1024,
                reason,
            )

            # Validate target
            if target_bytes <= 0:
                return EvictionResult(
                    success=True,
                    sections_evicted=[],
                    bytes_freed=0,
                    bytes_archived=0,
                    evicted_items=[],
                    new_pressure=self._get_current_pressure(),
                    iterations=0,
                    duration_ms=self._elapsed_ms(start_time),
                    reason=reason,
                )

            # Get candidates
            candidates = self.get_eviction_candidates()
            if not candidates:
                logger.warning("No eviction candidates available")
                return EvictionResult(
                    success=False,
                    sections_evicted=[],
                    bytes_freed=0,
                    bytes_archived=0,
                    evicted_items=[],
                    new_pressure=self._get_current_pressure(),
                    iterations=0,
                    duration_ms=self._elapsed_ms(start_time),
                    reason=reason,
                    error="No eviction candidates available",
                )

            # Evict in priority order
            total_freed = 0
            total_archived = 0
            sections_evicted: List[str] = []
            evicted_items: List[EvictedItem] = []
            iterations = 0
            remaining = target_bytes

            for candidate in candidates:
                if remaining <= 0:
                    break
                if iterations >= self._ss_cfg.eviction.max_eviction_iterations:
                    logger.warning("Max eviction iterations reached")
                    break

                iterations += 1

                # Calculate how much to evict from this section
                to_evict = min(candidate.evictable_bytes, remaining)
                _min_evict = self._ss_cfg.eviction.min_eviction_bytes
                if to_evict < _min_evict and candidate.evictable_bytes >= _min_evict:
                    to_evict = _min_evict

                # Evict from section
                result = self._evict_section(
                    section=candidate.section,
                    target_bytes=to_evict,
                    reason=reason,
                )

                if result:
                    total_freed += result.bytes_freed
                    total_archived += result.bytes_archived
                    remaining -= result.bytes_freed
                    if candidate.section not in sections_evicted:
                        sections_evicted.append(candidate.section)
                    evicted_items.append(result)

            # Check if we achieved target
            success = total_freed >= target_bytes or remaining <= 0

            duration = self._elapsed_ms(start_time)
            new_pressure = self._get_current_pressure()

            result = EvictionResult(
                success=success,
                sections_evicted=sections_evicted,
                bytes_freed=total_freed,
                bytes_archived=total_archived,
                evicted_items=evicted_items,
                new_pressure=new_pressure,
                iterations=iterations,
                duration_ms=duration,
                reason=reason,
                error=None if success else f"Only freed {total_freed}B of {target_bytes}B target",
            )

            logger.info(
                "Eviction complete: %s, freed=%dB, archived=%dB, sections=%s, took=%.2fms",
                "SUCCESS" if success else "PARTIAL",
                total_freed,
                total_archived,
                sections_evicted,
                duration,
            )

            return result

        finally:
            self._eviction_in_progress = False

    def _evict_section(
        self,
        section: str,
        target_bytes: int,
        reason: str,
    ) -> Optional[EvictedItem]:
        """
        Evict data from a single section.

        Args:
            section: Section to evict from
            target_bytes: How many bytes to evict
            reason: Eviction reason for metadata

        Returns:
            EvictedItem if successful, None if failed
        """
        # Lock section if MutationGuard available
        if self._mutation_guard:
            if not self._mutation_guard.lock_section(section):
                logger.warning("Failed to lock section %s for eviction", section)
                return None

        try:
            # Get current size
            current_size = self._size_tracker.get_section_size(section)
            if current_size == 0:
                return None

            # Calculate actual bytes to evict
            bytes_to_evict = min(target_bytes, current_size)

            # Get section data for archiving
            if self._section_provider:
                data, actual_bytes = self._section_provider.get_evictable_data(
                    section, bytes_to_evict
                )
            else:
                # Fallback: simulate full section eviction
                data = self._create_placeholder_data(section, bytes_to_evict)
                actual_bytes = bytes_to_evict

            # Archive to LOCAL COLD
            archive_id = None
            bytes_archived = 0

            if data and len(data) > 0:
                try:
                    archive_result = self._local_cold.archive(
                        section=section,
                        data=data,
                        session_id=self._session_id,
                        metadata={
                            "reason": reason,
                            "bytes_evicted": actual_bytes,
                            "timestamp_ms": int(time.time() * 1000),
                        },
                    )

                    if archive_result.success:
                        archive_id = archive_result.archive_id
                        bytes_archived = archive_result.size_bytes
                    else:
                        logger.error(
                            "Failed to archive %s: %s",
                            section,
                            archive_result.error,
                        )
                        # Don't evict if archive failed
                        return None

                except Exception as e:
                    logger.error("Archive failed for %s: %s", section, e)
                    return None

            # Remove from section
            if self._section_provider:
                bytes_freed = self._section_provider.remove_evicted_data(section, actual_bytes)
            else:
                # Fallback: just update size tracker
                bytes_freed = actual_bytes

            # Update size tracker (negative delta)
            self._size_tracker.update(section, -bytes_freed)

            logger.debug(
                "Evicted from %s: freed=%dB, archived=%dB, archive_id=%s",
                section,
                bytes_freed,
                bytes_archived,
                archive_id,
            )

            return EvictedItem(
                section=section,
                archive_id=archive_id,
                bytes_freed=bytes_freed,
                bytes_archived=bytes_archived,
                metadata={"reason": reason},
            )

        finally:
            # Unlock section
            if self._mutation_guard:
                self._mutation_guard.unlock_section(section)

    def _create_placeholder_data(self, section: str, size: int) -> bytes:
        """
        Create placeholder data for sections without a provider.

        This is used in testing or when section_provider is not available.
        """
        import json

        placeholder = {
            "section": section,
            "evicted_bytes": size,
            "placeholder": True,
            "timestamp_ms": int(time.time() * 1000),
        }
        return json.dumps(placeholder).encode("utf-8")

    # =========================================================================
    # PRESSURE-BASED EVICTION
    # =========================================================================

    def evict_to_normal_pressure(
        self, reason: str = EvictionReason.PRESSURE_ELEVATED
    ) -> EvictionResult:
        """
        Evict enough data to reach NORMAL pressure level.

        This is a convenience method that calculates the target automatically
        based on current utilization.

        Args:
            reason: Eviction reason

        Returns:
            EvictionResult
        """
        needed = self.estimate_eviction_needed()
        if needed <= 0:
            return EvictionResult(
                success=True,
                sections_evicted=[],
                bytes_freed=0,
                bytes_archived=0,
                evicted_items=[],
                new_pressure=self._get_current_pressure(),
                iterations=0,
                duration_ms=0,
                reason=reason,
            )

        return self.evict(target_bytes=needed, reason=reason)

    def estimate_eviction_needed(self) -> int:
        """
        Estimate how many bytes need to be evicted.

        Returns:
            int: Bytes that should be evicted to reach target utilization

        Formula:
            If pressure <= NORMAL: return 0
            Otherwise: return bytes to reach TARGET_UTILIZATION_AFTER_EVICTION
        """
        current_total = self._size_tracker.get_total_size()
        pressure = self._get_current_pressure()

        if pressure == PressureLevel.NORMAL:
            return 0

        # Target: 70% utilization (gives headroom)
        _cfg_evict = self._ss_cfg.eviction
        target_bytes = int(TOTAL_SIZE_LIMIT_BYTES * _cfg_evict.target_utilization)
        needed = current_total - target_bytes

        return max(0, needed)

    def estimate_warm_eviction_needed(self) -> int:
        """
        Estimate bytes to evict from WARM tier specifically.

        Returns:
            int: Bytes that should be evicted from WARM
        """
        warm_total = self._size_tracker.get_tier_size("warm")
        _target_util = self._ss_cfg.eviction.target_utilization
        target = int(WARM_SIZE_LIMIT_BYTES * _target_util)
        return max(0, warm_total - target)

    # =========================================================================
    # CAN EVICT CHECK
    # =========================================================================

    def can_evict(self, section: str) -> bool:
        """
        Check if a section can be evicted.

        Args:
            section: Section name

        Returns:
            bool: True if section is evictable

        Rules:
            - Only WARM sections can be evicted
            - NEVER_EVICT sections return False
            - HOT sections demote to WARM, they don't evict directly
        """
        # Only WARM sections can be evicted
        if section not in WARM_SECTIONS:
            return False

        # Check NEVER_EVICT list
        if section in NEVER_EVICT_SECTIONS:
            return False

        # Check if section has eviction priority defined
        budget = SECTION_BUDGETS.get(section)
        if budget and budget.eviction_priority is None:
            return False

        return True

    def get_evictable_bytes(self) -> int:
        """
        Get total bytes that can be evicted.

        Returns:
            int: Sum of all evictable bytes across WARM sections
        """
        total = 0
        for section in WARM_SECTIONS:
            if self.can_evict(section):
                total += self._size_tracker.get_section_size(section)
        return total

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _get_current_pressure(self) -> PressureLevel:
        """Get current overall pressure level."""
        return self._size_tracker.get_pressure()

    def _elapsed_ms(self, start_time: float) -> float:
        """Calculate elapsed time in milliseconds."""
        return (time.perf_counter() - start_time) * 1000

    # =========================================================================
    # PROPERTIES
    # =========================================================================

    @property
    def size_tracker(self) -> SizeTracker:
        """Get the associated SizeTracker instance."""
        return self._size_tracker

    @property
    def is_eviction_in_progress(self) -> bool:
        """Check if eviction is currently running."""
        return self._eviction_in_progress

    @property
    def session_id(self) -> str:
        """Get session ID."""
        return self._session_id

    def get_status(self) -> Dict[str, Any]:
        """
        Get eviction engine status for diagnostics.

        Returns:
            dict with current state
        """
        candidates = self.get_eviction_candidates()
        return {
            "session_id": self._session_id[:8] + "...",
            "eviction_in_progress": self._eviction_in_progress,
            "current_pressure": self._get_current_pressure().value,
            "eviction_needed_bytes": self.estimate_eviction_needed(),
            "evictable_bytes": self.get_evictable_bytes(),
            "candidate_count": len(candidates),
            "candidates": [
                {
                    "section": c.section,
                    "priority": c.priority.name,
                    "current_bytes": c.current_bytes,
                }
                for c in candidates[:5]  # Top 5 candidates
            ],
        }

    def __repr__(self) -> str:
        pressure = self._get_current_pressure()
        evictable = self.get_evictable_bytes()
        return (
            f"EvictionEngine(session={self._session_id[:8]}..., "
            f"pressure={pressure.value}, evictable={evictable}B, "
            f"in_progress={self._eviction_in_progress})"
        )


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    "EvictionCandidate",
    "EvictionEngine",
    "EvictionPriority",
    "EvictionReason",
    "EvictionResult",
    "EvictedItem",
    "ISectionDataProvider",
    "TARGET_UTILIZATION_AFTER_EVICTION",
    "MIN_EVICTION_BYTES",
    "MAX_EVICTION_ITERATIONS",
]
