"""
MutationGuard - Preflight Validation for All Mutations
=======================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.1 Kernel Services
ISSUE: 2.1.2

ADRs:
- ADR-0017 series: SessionState 6-Section Design
- ADR-0017g: Single-Writer Concurrency Pattern
- ADR-0018 series: 3-Tier Eviction Strategy

DEPENDENCIES:
- SizeTracker (Issue 2.1.1 - IMPLEMENTED)

==============================================================================
SPECIFICATION
==============================================================================

PURPOSE:
    Preflight validation for all mutations before they are applied.
    Checks capacity at 3 levels: section, tier, and total.
    Returns approval/rejection with detailed reason.

VALIDATION FLOW (3-tier check):
    1. Section capacity: Does this mutation fit in section budget?
    2. Tier capacity: Does this mutation fit in tier budget (HOT/WARM)?
    3. Total capacity: Does this mutation fit in total budget (96KB)?

REJECTION REASONS:
    - "Section capacity exceeded: {section} has {available}KB available"
    - "Tier capacity exceeded: {tier} has {available}KB available"
    - "Total capacity exceeded: {available}KB available"
    - "Emergency mode active: writes blocked"

VALID OPERATIONS:
    - "set": Replace section data
    - "append": Add to section (e.g., add fact, add turn)
    - "update": Modify existing data
    - "clear": Remove data (negative delta)
    - "delete": Remove specific item

EMERGENCY MODE:
    - Activated when pressure > 95% (EMERGENCY level)
    - ALL writes are rejected until pressure drops
    - Cleared after successful eviction

==============================================================================
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional, Set

from .sizetracker import (
    ALL_SECTIONS,
    HOT_SECTIONS,
    HOT_SIZE_LIMIT_BYTES,
    SECTION_BUDGETS,
    TOTAL_SIZE_LIMIT_BYTES,
    WARM_SIZE_LIMIT_BYTES,
    SizeTracker,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

# Valid mutation operations
VALID_OPERATIONS: frozenset[str] = frozenset(
    {
        "set",  # Replace section data
        "append",  # Add to section (list append, dict merge)
        "add_turn",  # Add turn to history section (alias for append)
        "add_fact",  # Add belief fact to beliefs_active
        "create_thread",  # Narrative thread creation
        "switch_to",  # Narrative thread switch
        "pause_thread",  # Narrative thread pause
        "resolve_thread",  # Narrative thread resolve
        "archive_thread",  # Narrative thread archive
        "update_thread",  # Narrative thread update
        "update",  # Modify existing entry
        "register_agent",  # Control section agent registration
        "add_referent",  # Scoreboard referent creation
        "request",  # Clarifications request
        "add_compressed",  # History recent compressed turn
        "add_summarized",  # History recent summarized turn
        "set_session_summary",  # History recent session summary update
        "add_vocabulary",  # Persona vocabulary entry
        "clear",  # Clear section/subsection (negative delta expected)
        "delete",  # Delete specific item (negative delta expected)
        "record_turn",  # Record turn timing in telemetry
        "record_error",  # Record error in telemetry
        "accept_demoted",  # Accept demoted data in WARM sections
    }
)

# FlatBuffer metadata overhead estimate (10% safety margin)
FLATBUFFER_OVERHEAD_FACTOR: float = 1.10


class RejectionReason(str, Enum):
    """
    Standard rejection reasons.

    These codes enable programmatic handling of rejections.
    Use .value for logging/serialization.
    """

    SECTION_CAPACITY = "section_capacity_exceeded"
    TIER_CAPACITY = "tier_capacity_exceeded"
    TOTAL_CAPACITY = "total_capacity_exceeded"
    EMERGENCY_MODE = "emergency_mode_active"
    INVALID_SECTION = "invalid_section"
    INVALID_OPERATION = "invalid_operation"
    SECTION_LOCKED = "section_locked"
    NEGATIVE_ESTIMATE = "negative_estimate_invalid"


@dataclass(frozen=False)
class Approval:
    """
    Result of preflight validation.

    Immutable result object returned by MutationGuard.preflight().

    Attributes:
        approved: Whether mutation is approved
        reason: Human-readable rejection reason (empty if approved)
        reason_code: Structured reason code for programmatic handling
        available_kb: Available capacity in KB (for error messages)
        section_available_bytes: Remaining bytes in target section
        tier_available_bytes: Remaining bytes in tier
        total_available_bytes: Remaining bytes overall
        tier: Which tier the section belongs to ('hot' or 'warm')
    """

    approved: bool
    reason: str = ""
    reason_code: Optional[RejectionReason] = None
    available_kb: float = 0.0
    section_available_bytes: int = 0
    tier_available_bytes: int = 0
    total_available_bytes: int = 0
    tier: str = ""

    def __repr__(self) -> str:
        if self.approved:
            return (
                f"Approval(approved=True, available_kb={self.available_kb:.2f}, "
                f"tier='{self.tier}')"
            )
        return (
            f"Approval(approved=False, reason='{self.reason}', "
            f"reason_code={self.reason_code}, available_kb={self.available_kb:.2f})"
        )

    @staticmethod
    def approve(
        section_available_bytes: int,
        tier_available_bytes: int,
        total_available_bytes: int,
        tier: str = "",
    ) -> Approval:
        """
        Create an approval result.

        Args:
            section_available_bytes: Bytes remaining in section after mutation
            tier_available_bytes: Bytes remaining in tier after mutation
            total_available_bytes: Bytes remaining total after mutation
            tier: Tier name ('hot' or 'warm')

        Returns:
            Approval with approved=True and capacity info
        """
        return Approval(
            approved=True,
            section_available_bytes=section_available_bytes,
            tier_available_bytes=tier_available_bytes,
            total_available_bytes=total_available_bytes,
            available_kb=total_available_bytes / 1024,
            tier=tier,
        )

    @staticmethod
    def reject(
        reason: str,
        reason_code: RejectionReason,
        available_bytes: int,
        section_available_bytes: int = 0,
        tier_available_bytes: int = 0,
        total_available_bytes: int = 0,
        tier: str = "",
    ) -> Approval:
        """
        Create a rejection result.

        Args:
            reason: Human-readable rejection message
            reason_code: Structured rejection code
            available_bytes: Bytes available at point of rejection
            section_available_bytes: Remaining in section
            tier_available_bytes: Remaining in tier
            total_available_bytes: Remaining overall
            tier: Tier name

        Returns:
            Approval with approved=False and reason info
        """
        return Approval(
            approved=False,
            reason=reason,
            reason_code=reason_code,
            available_kb=available_bytes / 1024,
            section_available_bytes=section_available_bytes,
            tier_available_bytes=tier_available_bytes,
            total_available_bytes=total_available_bytes,
            tier=tier,
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "approved": self.approved,
            "reason": self.reason,
            "reason_code": self.reason_code.value if self.reason_code else None,
            "available_kb": round(self.available_kb, 3),
            "section_available_bytes": self.section_available_bytes,
            "tier_available_bytes": self.tier_available_bytes,
            "total_available_bytes": self.total_available_bytes,
            "tier": self.tier,
        }


class MutationGuard:
    """
    Preflight validation for all SessionState mutations.

    All mutations MUST pass through preflight() before being applied.
    This ensures we never exceed capacity limits and enforces the
    single-writer pattern defined in ADR-0017g.

    Thread Safety:
        - preflight() is safe for concurrent calls (reads from SizeTracker)
        - emergency_mode uses threading.Lock for atomic updates
        - lock_section/unlock_section use threading.Lock

    Performance:
        - preflight(): O(1) - constant time checks
        - All capacity reads are from SizeTracker (lock-free)

    Invariants:
        - Mutations are never applied if preflight() returns approved=False
        - Emergency mode blocks ALL writes regardless of capacity
        - control and meta sections cannot be evicted (enforced separately)

    Example:
        guard = MutationGuard(size_tracker)

        # Check if mutation is allowed
        approval = guard.preflight(
            section="beliefs_active",
            operation="append",
            estimated_bytes=1024,
        )

        if approval.approved:
            # Apply mutation
            section.append(data)
            size_tracker.update("beliefs_active", 1024)
        else:
            # Reject mutation - use approval.reason for error message
            raise MutationRejectedError(approval.reason)

    Attributes:
        _size_tracker: SizeTracker instance for capacity checks
        _emergency_mode: Whether emergency mode is active (>95% capacity)
        _locked_sections: Set of sections currently locked for eviction/migration
        _lock: Lock for emergency_mode and locked_sections updates
    """

    __slots__ = (
        "_size_tracker",
        "_emergency_mode",
        "_locked_sections",
        "_lock",
    )

    def __init__(self, size_tracker: SizeTracker) -> None:
        """
        Initialize MutationGuard.

        Args:
            size_tracker: SizeTracker instance for capacity checks.
                         Must be the same instance used by SessionStateManager.
        """
        self._size_tracker = size_tracker
        self._emergency_mode: bool = False
        self._locked_sections: Set[str] = set()
        self._lock = threading.Lock()

        logger.debug("MutationGuard initialized with SizeTracker")

    # =========================================================================
    # PREFLIGHT VALIDATION
    # =========================================================================

    def preflight(
        self,
        section: str,
        operation: str,
        estimated_bytes: int,
    ) -> Approval:
        """
        Validate a mutation before applying it.

        This is the primary entry point for mutation validation. All mutations
        MUST call preflight() and check approval.approved before proceeding.

        PREFLIGHT CHECKS (in order):
            1. Validate section name exists
            2. Validate operation type
            3. Check if section is locked (eviction/migration in progress)
            4. Check emergency mode (if active, reject all writes)
            5. For positive deltas only:
               a. Check section capacity
               b. Check tier capacity
               c. Check total capacity

        Args:
            section: Target section name (e.g., 'beliefs_active', 'control')
            operation: Operation type ('set', 'append', 'update', 'clear', 'delete')
            estimated_bytes: Estimated size change in bytes.
                            Positive = growth, Negative = shrink.
                            For 'clear'/'delete', should be negative or 0.

        Returns:
            Approval: Result with approved/rejected status and detailed reason.
                     If approved, includes available capacity information.
                     If rejected, includes reason and available_kb for error message.

        Note:
            - Shrinking operations (negative delta) are always allowed unless
              emergency mode is active or section is locked.
            - The actual mutation is the caller's responsibility.
            - After mutation, caller must call size_tracker.update().

        Performance: O(1) - all checks are constant time
        """
        # ---------------------------------------------------------------------
        # CHECK 1: Validate section name
        # ---------------------------------------------------------------------
        if section not in ALL_SECTIONS:
            logger.warning("Preflight rejected: invalid section '%s'", section)
            return Approval.reject(
                reason=f"Invalid section: '{section}'. Valid sections: {', '.join(sorted(ALL_SECTIONS))}",
                reason_code=RejectionReason.INVALID_SECTION,
                available_bytes=0,
            )

        # Determine tier for this section
        tier = "hot" if section in HOT_SECTIONS else "warm"
        budget = SECTION_BUDGETS[section]

        # ---------------------------------------------------------------------
        # CHECK 2: Validate operation type
        # ---------------------------------------------------------------------
        if operation not in VALID_OPERATIONS:
            logger.warning("Preflight rejected: invalid operation '%s'", operation)
            return Approval.reject(
                reason=f"Invalid operation: '{operation}'. Valid operations: {', '.join(sorted(VALID_OPERATIONS))}",
                reason_code=RejectionReason.INVALID_OPERATION,
                available_bytes=0,
                tier=tier,
            )

        # ---------------------------------------------------------------------
        # CHECK 3: Check section lock
        # ---------------------------------------------------------------------
        with self._lock:
            if section in self._locked_sections:
                logger.info("Preflight rejected: section '%s' is locked", section)
                return Approval.reject(
                    reason=f"Section '{section}' is locked for eviction or migration",
                    reason_code=RejectionReason.SECTION_LOCKED,
                    available_bytes=self._size_tracker.get_available_bytes(section),
                    section_available_bytes=self._size_tracker.get_available_bytes(section),
                    tier_available_bytes=self._size_tracker.get_tier_available_bytes(tier),
                    total_available_bytes=self._size_tracker.get_total_available_bytes(),
                    tier=tier,
                )

            # -----------------------------------------------------------------
            # CHECK 4: Check emergency mode
            # -----------------------------------------------------------------
            if self._emergency_mode:
                logger.info("Preflight rejected: emergency mode active")
                return Approval.reject(
                    reason="Emergency mode active: all writes blocked until eviction completes",
                    reason_code=RejectionReason.EMERGENCY_MODE,
                    available_bytes=self._size_tracker.get_total_available_bytes(),
                    section_available_bytes=self._size_tracker.get_available_bytes(section),
                    tier_available_bytes=self._size_tracker.get_tier_available_bytes(tier),
                    total_available_bytes=self._size_tracker.get_total_available_bytes(),
                    tier=tier,
                )

        # ---------------------------------------------------------------------
        # CHECK 5: Capacity checks (only for positive deltas)
        # ---------------------------------------------------------------------
        # Shrinking operations (clear, delete with negative delta) bypass capacity checks
        if estimated_bytes <= 0:
            # Shrinking - always allowed (helps reduce pressure)
            return Approval.approve(
                section_available_bytes=self._size_tracker.get_available_bytes(section)
                - estimated_bytes,
                tier_available_bytes=self._size_tracker.get_tier_available_bytes(tier)
                - estimated_bytes,
                total_available_bytes=self._size_tracker.get_total_available_bytes()
                - estimated_bytes,
                tier=tier,
            )

        # Growing operation - check capacities in order
        # Get current availability
        section_available = self._size_tracker.get_available_bytes(section)
        tier_available = self._size_tracker.get_tier_available_bytes(tier)
        total_available = self._size_tracker.get_total_available_bytes()

        # -----------------------------------------------------------------
        # CHECK 5a: Section capacity
        # -----------------------------------------------------------------
        if estimated_bytes > section_available:
            current = self._size_tracker.get_section_size(section)
            logger.info(
                "Preflight rejected: section '%s' capacity exceeded "
                "(current=%d, delta=%d, budget=%d, available=%d)",
                section,
                current,
                estimated_bytes,
                budget.max_bytes,
                section_available,
            )
            return Approval.reject(
                reason=(
                    f"Section capacity exceeded: '{section}' has {section_available / 1024:.2f}KB "
                    f"available, mutation needs {estimated_bytes / 1024:.2f}KB"
                ),
                reason_code=RejectionReason.SECTION_CAPACITY,
                available_bytes=section_available,
                section_available_bytes=section_available,
                tier_available_bytes=tier_available,
                total_available_bytes=total_available,
                tier=tier,
            )

        # -----------------------------------------------------------------
        # CHECK 5b: Tier capacity
        # -----------------------------------------------------------------
        if estimated_bytes > tier_available:
            tier_limit = HOT_SIZE_LIMIT_BYTES if tier == "hot" else WARM_SIZE_LIMIT_BYTES
            tier_current = self._size_tracker.get_tier_size(tier)
            logger.info(
                "Preflight rejected: %s tier capacity exceeded "
                "(current=%d, delta=%d, limit=%d, available=%d)",
                tier.upper(),
                tier_current,
                estimated_bytes,
                tier_limit,
                tier_available,
            )
            return Approval.reject(
                reason=(
                    f"Tier capacity exceeded: {tier.upper()} tier has {tier_available / 1024:.2f}KB "
                    f"available, mutation needs {estimated_bytes / 1024:.2f}KB"
                ),
                reason_code=RejectionReason.TIER_CAPACITY,
                available_bytes=tier_available,
                section_available_bytes=section_available,
                tier_available_bytes=tier_available,
                total_available_bytes=total_available,
                tier=tier,
            )

        # -----------------------------------------------------------------
        # CHECK 5c: Total capacity
        # -----------------------------------------------------------------
        if estimated_bytes > total_available:
            total_current = self._size_tracker.get_total_size()
            logger.info(
                "Preflight rejected: total capacity exceeded "
                "(current=%d, delta=%d, limit=%d, available=%d)",
                total_current,
                estimated_bytes,
                TOTAL_SIZE_LIMIT_BYTES,
                total_available,
            )
            return Approval.reject(
                reason=(
                    f"Total capacity exceeded: session has {total_available / 1024:.2f}KB "
                    f"available, mutation needs {estimated_bytes / 1024:.2f}KB"
                ),
                reason_code=RejectionReason.TOTAL_CAPACITY,
                available_bytes=total_available,
                section_available_bytes=section_available,
                tier_available_bytes=tier_available,
                total_available_bytes=total_available,
                tier=tier,
            )

        # -----------------------------------------------------------------
        # ALL CHECKS PASSED - APPROVED
        # -----------------------------------------------------------------
        logger.debug(
            "Preflight approved: section='%s', operation='%s', bytes=%d",
            section,
            operation,
            estimated_bytes,
        )
        return Approval.approve(
            section_available_bytes=section_available - estimated_bytes,
            tier_available_bytes=tier_available - estimated_bytes,
            total_available_bytes=total_available - estimated_bytes,
            tier=tier,
        )

    # =========================================================================
    # SECTION LOCKING (for eviction/migration)
    # =========================================================================

    def lock_section(self, section: str) -> bool:
        """
        Lock a section for eviction or migration.

        While locked, preflight() will reject mutations to this section.
        Used by EvictionEngine and MigrationEngine to prevent concurrent
        modifications during data movement.

        Args:
            section: Section to lock

        Returns:
            bool: True if locked, False if section name is invalid

        Thread Safety: Uses lock for atomic update
        """
        if section not in ALL_SECTIONS:
            logger.warning("Cannot lock invalid section: '%s'", section)
            return False

        with self._lock:
            self._locked_sections.add(section)
            logger.info("Section '%s' locked for eviction/migration", section)
        return True

    def unlock_section(self, section: str) -> bool:
        """
        Unlock a section after eviction or migration completes.

        Args:
            section: Section to unlock

        Returns:
            bool: True if unlocked, False if section wasn't locked

        Thread Safety: Uses lock for atomic update
        """
        with self._lock:
            if section in self._locked_sections:
                self._locked_sections.discard(section)
                logger.info("Section '%s' unlocked", section)
                return True
        return False

    def is_section_locked(self, section: str) -> bool:
        """Check if a section is currently locked."""
        with self._lock:
            return section in self._locked_sections

    def get_locked_sections(self) -> frozenset[str]:
        """Get set of currently locked sections."""
        with self._lock:
            return frozenset(self._locked_sections)

    # =========================================================================
    # EMERGENCY MODE
    # =========================================================================

    def activate_emergency_mode(self) -> None:
        """
        Activate emergency mode (block all writes).

        Called when capacity exceeds CRITICAL threshold (95%).
        All preflight() calls will return rejection until deactivated.

        Side effects:
            - All writes blocked until deactivated
            - EmergencyActivatedEvent should be emitted by caller

        Thread Safety: Uses lock for atomic update
        """
        with self._lock:
            if not self._emergency_mode:
                self._emergency_mode = True
                logger.warning(
                    "EMERGENCY MODE ACTIVATED: All writes blocked. " "Current pressure: %.1f%%",
                    (self._size_tracker.get_total_size() / TOTAL_SIZE_LIMIT_BYTES) * 100,
                )

    def deactivate_emergency_mode(self) -> None:
        """
        Deactivate emergency mode (allow writes).

        Called when capacity drops below threshold after eviction.
        preflight() will resume normal capacity checks.

        Side effects:
            - Writes resume normal validation
            - EmergencyResolvedEvent should be emitted by caller

        Thread Safety: Uses lock for atomic update
        """
        with self._lock:
            if self._emergency_mode:
                self._emergency_mode = False
                logger.info(
                    "Emergency mode deactivated. Current pressure: %.1f%%",
                    (self._size_tracker.get_total_size() / TOTAL_SIZE_LIMIT_BYTES) * 100,
                )

    def is_emergency_mode(self) -> bool:
        """
        Check if emergency mode is active.

        Returns:
            bool: True if emergency mode is active

        Thread Safety: Atomic read
        """
        with self._lock:
            return self._emergency_mode

    # =========================================================================
    # SIZE ESTIMATION HELPERS
    # =========================================================================

    def estimate_mutation_size(
        self,
        section: str,
        operation: str,
        data: Any,
    ) -> int:
        """
        Estimate size of a mutation before serialization.

        This is a BEST EFFORT estimate used for preflight. Actual size may
        differ after FlatBuffer serialization. Includes 10% overhead margin.

        Args:
            section: Target section (for type hints)
            operation: Operation type
            data: Data to be stored

        Returns:
            int: Estimated size in bytes (with 10% safety margin)

        Estimation Strategy:
            - For None: 0 bytes
            - For strings: UTF-8 encoded length
            - For bytes: Length of bytes
            - For numbers: 8 bytes (int/float)
            - For bools: 1 byte
            - For dicts/lists: JSON serialization as approximation
            - Add 10% overhead for FlatBuffer metadata

        Note:
            For accurate estimates, caller should use FlatBuffer.pack()
            and measure actual serialized size when possible.
        """
        if data is None:
            return 0

        base_size = self._estimate_data_size(data)
        return int(base_size * FLATBUFFER_OVERHEAD_FACTOR)

    def _estimate_data_size(self, data: Any) -> int:
        """
        Estimate raw data size without overhead.

        Internal helper for estimate_mutation_size.
        """
        if data is None:
            return 0

        if isinstance(data, str):
            return len(data.encode("utf-8"))

        if isinstance(data, bytes):
            return len(data)

        if isinstance(data, bool):
            return 1

        if isinstance(data, (int, float)):
            return 8

        if isinstance(data, (list, tuple)):
            return sum(self._estimate_data_size(item) for item in data)

        if isinstance(data, dict):
            # Use JSON as approximation for complex structures
            try:
                return len(json.dumps(data).encode("utf-8"))
            except (TypeError, ValueError):
                # Fallback for non-serializable data
                return sum(
                    self._estimate_data_size(k) + self._estimate_data_size(v)
                    for k, v in data.items()
                )

        # Default fallback for unknown types
        return 64

    # =========================================================================
    # PROPERTIES
    # =========================================================================

    @property
    def size_tracker(self) -> SizeTracker:
        """Get the associated SizeTracker instance."""
        return self._size_tracker

    def get_capacity_summary(self) -> dict:
        """
        Get current capacity summary for diagnostics.

        Returns:
            dict with current sizes, available space, and pressure levels
        """
        snapshot = self._size_tracker.get_snapshot()
        return {
            "total_size_bytes": snapshot.total,
            "total_available_bytes": TOTAL_SIZE_LIMIT_BYTES - snapshot.total,
            "total_utilization_pct": round(snapshot.total_utilization_pct * 100, 1),
            "hot_size_bytes": snapshot.hot_total,
            "hot_available_bytes": HOT_SIZE_LIMIT_BYTES - snapshot.hot_total,
            "hot_utilization_pct": round(snapshot.hot_utilization_pct * 100, 1),
            "warm_size_bytes": snapshot.warm_total,
            "warm_available_bytes": WARM_SIZE_LIMIT_BYTES - snapshot.warm_total,
            "warm_utilization_pct": round(snapshot.warm_utilization_pct * 100, 1),
            "overall_pressure": snapshot.overall_pressure.value,
            "hot_pressure": snapshot.hot_pressure.value,
            "warm_pressure": snapshot.warm_pressure.value,
            "emergency_mode": self.is_emergency_mode(),
            "locked_sections": list(self.get_locked_sections()),
        }

    def __repr__(self) -> str:
        snapshot = self._size_tracker.get_snapshot()
        return (
            f"MutationGuard(total={snapshot.total}/{TOTAL_SIZE_LIMIT_BYTES}, "
            f"pressure={snapshot.overall_pressure.value}, "
            f"emergency={self.is_emergency_mode()})"
        )


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    "Approval",
    "MutationGuard",
    "RejectionReason",
    "VALID_OPERATIONS",
]
