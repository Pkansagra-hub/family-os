"""
SessionStateManager - Central Facade for All SessionState Operations
=====================================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.5 SessionStateManager
ISSUES: 2.5.1, 2.5.2, 2.5.3, 2.5.4

ARCHITECTURE DIAGRAMS:
- k1/sessionstate/sessionstate.mmd (external view)
- k1/sessionstate/sessionstate_internal.mmd (internal structure)
- architecture_diagrams/k1/k1_cognitive_architecture_skeleton.mmd

ADRs:
- ADR-0017 series: SessionState 6-Section Design
- ADR-0018 series: 3-Tier Eviction Strategy
- ADR-0020: Multi-Tier Storage Architecture
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .adapters.section_data_adapter import SectionDataAdapter
from .events import EmergencyLevel, EventType, SessionStateEvents
from .eviction import EvictionEngine
from .guard import MutationGuard
from .local_cold import LocalColdArchive
from .migration import MigrationEngine
from .sizetracker import (
    ALL_SECTIONS,
    HOT_SECTIONS,
    SECTION_BUDGETS,
    WARM_SECTIONS,
    WARM_SIZE_LIMIT_BYTES,
    PressureLevel,
    SizeTracker,
)
from .tiers.hot import HotTier
from .tiers.local_cold import LocalColdTier
from .tiers.warm import WarmTier

if TYPE_CHECKING:
    from .ports.events import IEventPort
    from .ports.k0_sync import IK0SyncPort
    from .ports.lifecycle import ILifecyclePort
    from .ports.storage import IStoragePort
    from .ports.writer import IWriterPort

logger = logging.getLogger(__name__)


# =============================================================================
# EXCEPTIONS
# =============================================================================


class SectionNotFoundError(KeyError):
    """Raised when a section name is invalid."""

    def __init__(self, section: str):
        self.section = section
        super().__init__(f"Section '{section}' not found. Valid: {', '.join(sorted(ALL_SECTIONS))}")


class MutationRejectedError(Exception):
    """Raised when a mutation is rejected by MutationGuard."""

    def __init__(self, reason: str, available_kb: float = 0.0):
        self.reason = reason
        self.available_kb = available_kb
        super().__init__(reason)


class LifecycleError(Exception):
    """Raised when lifecycle operation fails."""

    pass


# =============================================================================
# DATACLASSES
# =============================================================================


@dataclass
class MutationResult:
    """
    Result of a mutation operation.

    Attributes:
        success: Whether mutation was applied
        section: Target section name
        operation: Operation performed
        bytes_delta: Change in bytes (positive = growth, negative = shrink)
        new_size_bytes: New section size after mutation
        available_bytes: Remaining capacity after mutation
        pressure: Current pressure level after mutation
        error: Error message if failed
        reason: Rejection reason if rejected
        cognitive_trace_id: Trace ID for distributed tracing correlation
    """

    success: bool
    section: str
    operation: str
    bytes_delta: int = 0
    new_size_bytes: int = 0
    available_bytes: int = 0
    pressure: PressureLevel = PressureLevel.NORMAL
    error: Optional[str] = None
    reason: str = ""
    cognitive_trace_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "section": self.section,
            "operation": self.operation,
            "bytes_delta": self.bytes_delta,
            "new_size_bytes": self.new_size_bytes,
            "available_bytes": self.available_bytes,
            "pressure": self.pressure.value,
            "error": self.error,
            "reason": self.reason,
            "cognitive_trace_id": self.cognitive_trace_id,
        }

    @classmethod
    def rejected(
        cls,
        section: str,
        operation: str,
        reason: str,
        available_bytes: int = 0,
        cognitive_trace_id: str = "",
    ) -> MutationResult:
        """Create a rejection result."""
        return cls(
            success=False,
            section=section,
            operation=operation,
            reason=reason,
            available_bytes=available_bytes,
            error=reason,
            cognitive_trace_id=cognitive_trace_id,
        )

    @classmethod
    def failure(
        cls,
        section: str,
        operation: str,
        error: str,
        cognitive_trace_id: str = "",
    ) -> MutationResult:
        """Create a failure result."""
        return cls(
            success=False,
            section=section,
            operation=operation,
            error=error,
            cognitive_trace_id=cognitive_trace_id,
        )


@dataclass
class SectionInfo:
    """
    Information about a single section.

    Attributes:
        name: Section name
        tier: Tier name ('hot' or 'warm')
        size_bytes: Current size in bytes
        budget_bytes: Maximum allowed size
        utilization_pct: Current utilization percentage
        pressure: Section-specific pressure level
    """

    name: str
    tier: str
    size_bytes: int
    budget_bytes: int
    utilization_pct: float
    pressure: PressureLevel

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "tier": self.tier,
            "size_bytes": self.size_bytes,
            "budget_bytes": self.budget_bytes,
            "utilization_pct": round(self.utilization_pct, 4),
            "pressure": self.pressure.value,
        }


@dataclass
class SessionSnapshot:
    """
    Complete session state snapshot for diagnostics.

    Attributes:
        session_id: Session identifier
        total_size_bytes: Total bytes used across all tiers
        hot_size_bytes: Bytes used in HOT tier
        warm_size_bytes: Bytes used in WARM tier
        hot_utilization_pct: HOT tier utilization percentage
        warm_utilization_pct: WARM tier utilization percentage
        total_utilization_pct: Total utilization percentage
        pressure: Current overall pressure level
        sections: Per-section information
        last_mutation_ms: Timestamp of last mutation
        is_running: Whether manager is in RUNNING state
        timestamp_ms: Snapshot timestamp
    """

    session_id: str
    total_size_bytes: int
    hot_size_bytes: int
    warm_size_bytes: int
    hot_utilization_pct: float
    warm_utilization_pct: float
    total_utilization_pct: float
    pressure: PressureLevel
    sections: Dict[str, SectionInfo]
    last_mutation_ms: int
    is_running: bool
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "total_size_bytes": self.total_size_bytes,
            "hot_size_bytes": self.hot_size_bytes,
            "warm_size_bytes": self.warm_size_bytes,
            "hot_utilization_pct": round(self.hot_utilization_pct, 4),
            "warm_utilization_pct": round(self.warm_utilization_pct, 4),
            "total_utilization_pct": round(self.total_utilization_pct, 4),
            "pressure": self.pressure.value,
            "sections": {name: info.to_dict() for name, info in self.sections.items()},
            "last_mutation_ms": self.last_mutation_ms,
            "is_running": self.is_running,
            "timestamp_ms": self.timestamp_ms,
        }


@dataclass
class StartResult:
    """
    Result of start operation.

    Attributes:
        success: Whether start succeeded
        session_id: Session that was started
        duration_ms: Time taken to start
        restored: Whether session was restored from checkpoint
        restore_source: Source of restoration ('local_cold', 'k0', 'fresh')
        error: Error message if failed
        cognitive_trace_id: Trace ID for distributed tracing correlation
    """

    success: bool
    session_id: str = ""
    duration_ms: float = 0.0
    restored: bool = False
    restore_source: str = "fresh"
    error: Optional[str] = None
    cognitive_trace_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "session_id": self.session_id,
            "duration_ms": round(self.duration_ms, 3),
            "restored": self.restored,
            "restore_source": self.restore_source,
            "error": self.error,
            "cognitive_trace_id": self.cognitive_trace_id,
        }


@dataclass
class StopResult:
    """
    Result of stop operation.

    Attributes:
        success: Whether stop succeeded
        checkpoint_id: ID of final checkpoint (if any)
        duration_ms: Time taken to stop
        error: Error message if failed
        cognitive_trace_id: Trace ID for distributed tracing correlation
    """

    success: bool
    checkpoint_id: Optional[str] = None
    duration_ms: float = 0.0
    error: Optional[str] = None
    cognitive_trace_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "checkpoint_id": self.checkpoint_id,
            "duration_ms": round(self.duration_ms, 3),
            "error": self.error,
            "cognitive_trace_id": self.cognitive_trace_id,
        }


@dataclass
class CheckpointResult:
    """
    Result of checkpoint operation.

    Attributes:
        success: Whether checkpoint succeeded
        checkpoint_id: Unique checkpoint identifier
        size_bytes: Total bytes checkpointed
        duration_ms: Time taken
        sla_met: Whether <50ms SLA was met
        error: Error message if failed
        cognitive_trace_id: Trace ID for distributed tracing correlation
    """

    success: bool
    checkpoint_id: str = ""
    size_bytes: int = 0
    duration_ms: float = 0.0
    sla_met: bool = True
    error: Optional[str] = None
    cognitive_trace_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "checkpoint_id": self.checkpoint_id,
            "size_bytes": self.size_bytes,
            "duration_ms": round(self.duration_ms, 3),
            "sla_met": self.sla_met,
            "error": self.error,
            "cognitive_trace_id": self.cognitive_trace_id,
        }


@dataclass
class RestoreResult:
    """
    Result of restore operation.

    Attributes:
        success: Whether restore succeeded
        source: Where data came from ('local_cold', 'k0', 'fresh')
        sections_restored: List of sections that were restored
        hot_restored: Whether HOT tier was fully restored
        warm_restored: Whether WARM tier was fully restored
        duration_ms: Time taken
        sla_met: Whether SLA was met
        error: Error message if failed
        cognitive_trace_id: Trace ID for distributed tracing correlation
    """

    success: bool
    source: str = "fresh"
    sections_restored: List[str] = field(default_factory=list)
    hot_restored: bool = False
    warm_restored: bool = False
    duration_ms: float = 0.0
    sla_met: bool = True
    error: Optional[str] = None
    cognitive_trace_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "source": self.source,
            "sections_restored": self.sections_restored,
            "hot_restored": self.hot_restored,
            "warm_restored": self.warm_restored,
            "duration_ms": round(self.duration_ms, 3),
            "sla_met": self.sla_met,
            "error": self.error,
            "cognitive_trace_id": self.cognitive_trace_id,
        }


class ManagerState(str, Enum):
    """SessionStateManager lifecycle states."""

    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


# =============================================================================
# SESSIONSTATEMANAGER CLASS
# =============================================================================


class SessionStateManager:
    """
    Central facade for all SessionState operations.

    Orchestrates HotTier, WarmTier, LocalColdTier, and kernel services
    (SizeTracker, MutationGuard, EvictionEngine, MigrationEngine).

    Pattern:
        - Single instance per session
        - Single-writer (only Concierge writes via IWriterPort)
        - Multi-reader (lock-free reads, <1ms latency)

    Thread Safety:
        - Write operations use RLock for serialization
        - Read operations are lock-free (snapshot-based)
        - Internal state changes are atomic

    Attributes:
        session_id: Unique session identifier
        hot: HotTier manager (8 sections, 48KB)
        warm: WarmTier manager (4 sections, 48KB)
        local_cold: LocalColdTier (K1 SQLite archive)
        size_tracker: Per-section byte accounting
        mutation_guard: Preflight validation
        eviction_engine: WARM -> LOCAL COLD eviction
        migration_engine: HOT <-> WARM migration

    Example:
        manager = SessionStateManager(
            session_id="abc-123",
            storage_port=sqlite_adapter,
            event_port=local_event_adapter,
            writer_port=direct_writer,
            lifecycle_port=standalone_lifecycle,
        )

        result = manager.start()
        assert result.success

        control = manager.get_section("control")
        control.advance_turn()

        result = manager.mutate("beliefs_active", "append", {...})
        if result.success:
            print(f"Added {result.bytes_delta} bytes")

        manager.stop()
    """

    __slots__ = (
        "_session_id",
        "_storage_port",
        "_event_port",
        "_writer_port",
        "_lifecycle_port",
        "_k0_sync_port",
        "_hot",
        "_warm",
        "_local_cold",
        "_local_cold_archive",
        "_size_tracker",
        "_mutation_guard",
        "_eviction_engine",
        "_migration_engine",
        "_section_provider",
        "_emergency_active",
        "_state",
        "_write_lock",
        "_last_mutation_ms",
        "_started_at_ms",
        "_mutation_count",
    )

    def __init__(
        self,
        session_id: str,
        storage_port: IStoragePort,
        event_port: IEventPort,
        writer_port: IWriterPort,
        lifecycle_port: ILifecyclePort,
        local_cold_archive: Optional[LocalColdArchive] = None,
        k0_sync_port: Optional[IK0SyncPort] = None,
    ) -> None:
        """
        Initialize SessionStateManager with injected ports.

        Args:
            session_id: Unique session identifier
            storage_port: Persistence adapter (SQLiteStorageAdapter for LOCAL COLD)
            event_port: Event bus adapter (LocalEventAdapter for standalone)
            writer_port: Writer adapter (DirectWriterAdapter for standalone)
            lifecycle_port: Lifecycle adapter (StandaloneLifecycle for standalone)
            local_cold_archive: Optional LocalColdArchive instance (for testing)
            k0_sync_port: Optional K0 sync port for cross-device sync

        Note:
            Does NOT start lifecycle here. Call start() explicitly after construction.
        """
        self._session_id = session_id
        self._storage_port = storage_port
        self._event_port = event_port
        self._writer_port = writer_port
        self._lifecycle_port = lifecycle_port
        self._k0_sync_port = k0_sync_port

        # State
        self._state = ManagerState.CREATED
        self._write_lock = threading.RLock()
        self._last_mutation_ms = 0
        self._started_at_ms = 0
        self._mutation_count = 0

        # Initialize kernel services first
        self._size_tracker = SizeTracker()
        self._mutation_guard = MutationGuard(self._size_tracker)

        # Initialize LOCAL COLD archive
        self._local_cold_archive = local_cold_archive or LocalColdArchive()

        # Initialize tier managers
        self._hot = HotTier(session_id=session_id)
        self._warm = WarmTier(
            session_id=session_id,
            local_cold=self._local_cold_archive,
        )
        self._local_cold = LocalColdTier(
            storage=self._local_cold_archive,
            session_id=session_id,
        )

        # Initialize engines with dependencies
        # W5 (audit Fix J): SectionDataAdapter wires the live HOT + WARM tier
        # objects into both engines so eviction can serialize+clear real
        # section bytes and migration can move payloads between tiers.
        self._section_provider = SectionDataAdapter(self._hot, self._warm)
        self._eviction_engine = EvictionEngine(
            size_tracker=self._size_tracker,
            local_cold=self._local_cold_archive,
            mutation_guard=self._mutation_guard,
            session_id=session_id,
            section_provider=self._section_provider,
        )

        self._migration_engine = MigrationEngine(
            size_tracker=self._size_tracker,
            mutation_guard=self._mutation_guard,
            session_id=session_id,
            section_provider=self._section_provider,
        )

        # W7: emergency activation tracking — only emit on rising edge.
        self._emergency_active: bool = False

        logger.info(
            "SessionStateManager initialized (session=%s, state=%s, sections=hot:%d+warm)",
            session_id[:8] if session_id else "none",
            self._state.value,
            len(HOT_SECTIONS),
        )

    # =========================================================================
    # PROPERTIES
    # =========================================================================

    @property
    def session_id(self) -> str:
        """Session identifier."""
        return self._session_id

    @property
    def state(self) -> ManagerState:
        """Current lifecycle state."""
        return self._state

    @property
    def is_running(self) -> bool:
        """Whether manager is in RUNNING state."""
        return self._state == ManagerState.RUNNING

    @property
    def hot(self) -> HotTier:
        """HOT tier manager."""
        return self._hot

    @property
    def warm(self) -> WarmTier:
        """WARM tier manager."""
        return self._warm

    @property
    def local_cold(self) -> LocalColdTier:
        """LOCAL COLD tier manager."""
        return self._local_cold

    @property
    def size_tracker(self) -> SizeTracker:
        """Size tracking service."""
        return self._size_tracker

    @property
    def mutation_guard(self) -> MutationGuard:
        """Mutation validation service."""
        return self._mutation_guard

    @property
    def eviction_engine(self) -> EvictionEngine:
        """Eviction engine."""
        return self._eviction_engine

    @property
    def migration_engine(self) -> MigrationEngine:
        """Migration engine."""
        return self._migration_engine

    # =========================================================================
    # READ API (Issue 2.5.2)
    # =========================================================================
    # Guarantee: Lock-free reads, <1ms latency
    # Thread-safety: Multi-reader safe

    def get_section(self, name: str) -> Any:
        """
        Get a section by name.

        Args:
            name: Section name (e.g., 'control', 'beliefs_active', 'scoreboard')

        Returns:
            Section instance (type depends on section)

        Raises:
            SectionNotFoundError: If section name is invalid

        Performance:
            - <1ms latency guaranteed
            - Lock-free read
        """
        if name not in ALL_SECTIONS:
            raise SectionNotFoundError(name)

        # Check HOT tier first
        if name in HOT_SECTIONS:
            section = self._hot.get_section(name)
            if section is not None:
                return section

        # Check WARM tier
        if name in WARM_SECTIONS:
            section = self._warm.get_section(name)
            if section is not None:
                return section

        raise SectionNotFoundError(name)

    def get_hot(self) -> HotTier:
        """
        Get the HOT tier (8 sections, 52KB max).

        Returns:
            HotTier: HOT tier manager with all 8 sections

        Sections:
            - control (8KB, NEVER EVICT)
            - beliefs_active (8KB)
            - scoreboard (6KB)
            - history_active (8KB)
            - clarifications (4KB)
            - affective_now (4KB)
            - narrative_active (4KB)
            - meta (2KB)
        """
        return self._hot

    def get_warm(self) -> WarmTier:
        """
        Get the WARM tier (4 sections, 48KB max).

        Returns:
            WarmTier: WARM tier manager with all 4 sections

        Sections:
            - beliefs_history (12KB, eviction priority 2)
            - history_recent (20KB, eviction priority 3)
            - persona (8KB, eviction priority 4)
            - telemetry (8KB, eviction priority 1 - first to evict)
        """
        return self._warm

    def get_all_section_sizes(self) -> Dict[str, int]:
        """
        Get current size in bytes for all sections.

        Returns:
            Dict mapping section name to current byte count.

        Performance:
            - <1ms latency (uses SizeTracker snapshot)
        """
        snapshot = self._size_tracker.get_snapshot()
        return snapshot.sections.copy()

    def get_local_cold(self) -> LocalColdTier:
        """
        Get the LOCAL COLD tier (K1 SQLite archive).

        Returns:
            LocalColdTier: LOCAL COLD tier manager
        """
        return self._local_cold

    def get_local_cold_archive(self) -> LocalColdArchive:
        """Return the underlying LocalColdArchive (raw storage layer).

        Used by Memory Writer's enriched read path to fetch archived
        ``history_active`` blobs across an arbitrary session_id without
        needing the per-session ``LocalColdTier`` wrapper.
        """
        return self._local_cold_archive

    def get_snapshot(self) -> SessionSnapshot:
        """
        Get current session snapshot for diagnostics.

        Returns:
            SessionSnapshot: Complete state snapshot including:
                - Size breakdown per section
                - Tier utilization (HOT %, WARM %)
                - Current pressure level (NORMAL/ELEVATED/CRITICAL)
                - Last mutation timestamp

        Performance:
            - <1ms latency guaranteed
            - Lock-free read (uses SizeTracker snapshot)
        """
        size_snapshot = self._size_tracker.get_snapshot()

        sections: Dict[str, SectionInfo] = {}

        for section_name in ALL_SECTIONS:
            budget = SECTION_BUDGETS[section_name]
            size_bytes = size_snapshot.sections.get(section_name, 0)
            budget_bytes = budget.max_bytes

            utilization = size_bytes / budget_bytes if budget_bytes > 0 else 0.0

            # Calculate section pressure
            if utilization >= 0.95:
                pressure = PressureLevel.EMERGENCY
            elif utilization >= 0.90:
                pressure = PressureLevel.CRITICAL
            elif utilization >= 0.80:
                pressure = PressureLevel.ELEVATED
            else:
                pressure = PressureLevel.NORMAL

            tier = "hot" if section_name in HOT_SECTIONS else "warm"

            sections[section_name] = SectionInfo(
                name=section_name,
                tier=tier,
                size_bytes=size_bytes,
                budget_bytes=budget_bytes,
                utilization_pct=utilization * 100,
                pressure=pressure,
            )

        return SessionSnapshot(
            session_id=self._session_id,
            total_size_bytes=size_snapshot.total,
            hot_size_bytes=size_snapshot.hot_total,
            warm_size_bytes=size_snapshot.warm_total,
            hot_utilization_pct=size_snapshot.hot_utilization_pct * 100,
            warm_utilization_pct=size_snapshot.warm_utilization_pct * 100,
            total_utilization_pct=size_snapshot.total_utilization_pct * 100,
            pressure=size_snapshot.overall_pressure,
            sections=sections,
            last_mutation_ms=self._last_mutation_ms,
            is_running=self.is_running,
        )

    # =========================================================================
    # WRITE API - SINGLE WRITER ONLY (Issue 2.5.3)
    # =========================================================================
    # Pattern: Only Concierge calls this via IWriterPort
    # Enforcement: MutationGuard preflight
    # Rejection: Returns reason and available capacity

    def mutate(
        self,
        section: str,
        operation: str,
        data: Any,
        estimated_bytes: Optional[int] = None,
        cognitive_trace_id: Optional[str] = None,
    ) -> MutationResult:
        """
        Apply a mutation to a section.

        SINGLE WRITER PATTERN:
            Only Concierge should call this method. Sub-agents propose
            deltas to Concierge, who applies them via this API.

        Args:
            section: Target section name
            operation: Operation type ('set', 'append', 'update', 'clear', 'delete')
            data: Operation-specific data payload
            estimated_bytes: Optional size estimate (auto-calculated if None)
            cognitive_trace_id: Trace ID for distributed tracing correlation

        Returns:
            MutationResult with success/failure and detailed info

        Flow:
            1. MutationGuard.preflight() - Check capacity
            2. If rejected: emit MutationRejectedEvent, return rejection
            3. If approved: apply mutation
            4. SizeTracker.update() - Update byte counts
            5. Check pressure levels
            6. If ELEVATED: trigger MigrationEngine
            7. If CRITICAL: trigger EvictionEngine
            8. Emit MutationApprovedEvent
        """
        trace_id = cognitive_trace_id or ""
        with self._write_lock:
            # Estimate bytes if not provided
            if estimated_bytes is None:
                estimated_bytes = self._estimate_bytes(data)

            # Step 1: Preflight validation
            approval = self._mutation_guard.preflight(
                section=section,
                operation=operation,
                estimated_bytes=estimated_bytes,
            )

            if not approval.approved:
                logger.info(
                    "Mutation rejected: section=%s, op=%s, reason=%s, trace_id=%s",
                    section,
                    operation,
                    approval.reason,
                    trace_id,
                )
                return MutationResult.rejected(
                    section=section,
                    operation=operation,
                    reason=approval.reason,
                    available_bytes=approval.total_available_bytes,
                    cognitive_trace_id=trace_id,
                )

            # Step 2: Apply mutation
            try:
                actual_bytes = self._apply_mutation(section, operation, data)
            except Exception as e:
                logger.error(
                    "Mutation failed: section=%s, op=%s, error=%s, trace_id=%s",
                    section,
                    operation,
                    str(e),
                    trace_id,
                )
                return MutationResult.failure(
                    section=section,
                    operation=operation,
                    error=str(e),
                    cognitive_trace_id=trace_id,
                )

            # Step 3: Update size tracking
            self._size_tracker.update(section, actual_bytes)
            self._last_mutation_ms = int(time.time() * 1000)
            self._mutation_count += 1

            # Step 4: Check pressure and trigger engines if needed
            pressure = self._size_tracker.get_pressure()

            if pressure in (PressureLevel.CRITICAL, PressureLevel.EMERGENCY):
                # W7: emit EmergencyActivated on rising edge.
                if not self._emergency_active:
                    self._emergency_active = True
                    self._emit_emergency_activated(pressure, trace_id)
                # Trigger eviction for WARM sections
                if section in WARM_SECTIONS:
                    self._trigger_eviction_if_needed(trace_id=trace_id)
                # Trigger migration for HOT sections
                elif section in HOT_SECTIONS:
                    self._trigger_migration_if_needed()
            elif self._emergency_active and pressure == PressureLevel.NORMAL:
                # Pressure cleared; allow re-arming the emergency edge.
                self._emergency_active = False

            # Get new size
            new_size = self._size_tracker.get_section_size(section)
            available = self._size_tracker.get_total_available_bytes()

            logger.info(
                "Mutation applied: section=%s, op=%s, delta=%dB, new_size=%dB, pressure=%s, trace_id=%s",
                section,
                operation,
                actual_bytes,
                new_size,
                pressure.value,
                trace_id,
            )

            return MutationResult(
                success=True,
                section=section,
                operation=operation,
                bytes_delta=actual_bytes,
                new_size_bytes=new_size,
                available_bytes=available,
                pressure=pressure,
                cognitive_trace_id=trace_id,
            )

    def _estimate_bytes(self, data: Any) -> int:
        """Estimate size of data in bytes."""
        if data is None:
            return 0
        if isinstance(data, bytes):
            return len(data)
        if isinstance(data, str):
            return len(data.encode("utf-8"))
        try:
            return len(json.dumps(data).encode("utf-8"))
        except (TypeError, ValueError):
            return 1024  # Default estimate

    def _apply_mutation(self, section: str, operation: str, data: Any) -> int:
        """
        Apply mutation to the appropriate section.

        Returns the actual bytes changed.
        """
        # Get the section
        sec = self.get_section(section)

        # Apply based on operation type
        if hasattr(sec, "get_size_bytes"):
            old_size = sec.get_size_bytes()
        elif hasattr(sec, "size_bytes"):
            old_size = sec.size_bytes
        else:
            old_size = 0

        if operation == "set":
            if hasattr(sec, "set_data"):
                sec.set_data(data)
            elif hasattr(sec, "set"):
                sec.set(data)
            else:
                # Fallback: direct attribute set
                sec._data = data
        elif operation == "append" or operation == "add_turn":
            # Handle dict data by unpacking as kwargs for methods expecting
            # positional/keyword arguments (e.g., history_active.append())
            if hasattr(sec, "append"):
                if isinstance(data, dict):
                    sec.append(**data)
                else:
                    sec.append(data)
            elif hasattr(sec, "add"):
                if isinstance(data, dict):
                    sec.add(**data)
                else:
                    sec.add(data)
            else:
                raise ValueError(f"Section {section} does not support append")
        elif operation == "add_fact":
            if hasattr(sec, "add_fact"):
                if isinstance(data, dict):
                    sec.add_fact(**data)
                else:
                    raise ValueError("add_fact expects dict data")
            else:
                raise ValueError(f"Section {section} does not support add_fact")
        elif operation == "update":
            if hasattr(sec, "update"):
                if isinstance(data, dict):
                    sec.update(**data)
                else:
                    sec.update(data)
            elif hasattr(sec, "merge"):
                sec.merge(data)
            else:
                raise ValueError(f"Section {section} does not support update")
        elif operation == "record_turn":
            # Special operation for telemetry section
            if hasattr(sec, "record_turn"):
                if isinstance(data, dict):
                    sec.record_turn(**data)
                else:
                    sec.record_turn(data)
            else:
                raise ValueError(f"Section {section} does not support record_turn")
        elif operation == "record_error":
            # Special operation for telemetry section
            if hasattr(sec, "record_error"):
                if isinstance(data, dict):
                    sec.record_error(**data)
                else:
                    sec.record_error(data)
            else:
                raise ValueError(f"Section {section} does not support record_error")
        elif operation == "accept_demoted":
            # Special operation for WARM sections accepting demoted data
            if hasattr(sec, "accept_demoted"):
                if isinstance(data, dict):
                    sec.accept_demoted(**data)
                else:
                    sec.accept_demoted(data)
            else:
                raise ValueError(f"Section {section} does not support accept_demoted")
        elif operation == "clear":
            if hasattr(sec, "clear"):
                sec.clear()
            else:
                raise ValueError(f"Section {section} does not support clear")
        elif operation == "delete":
            if hasattr(sec, "delete"):
                sec.delete(data)
            elif hasattr(sec, "remove"):
                sec.remove(data)
            else:
                raise ValueError(f"Section {section} does not support delete")
        else:
            if hasattr(sec, "apply"):
                if isinstance(data, dict):
                    sec.apply(operation, data)
                else:
                    sec.apply(operation, {"value": data})
            else:
                raise ValueError(f"Unknown operation: {operation}")

        if hasattr(sec, "get_size_bytes"):
            new_size = sec.get_size_bytes()
        elif hasattr(sec, "size_bytes"):
            new_size = sec.size_bytes
        else:
            new_size = 0
        return new_size - old_size

    def _trigger_eviction_if_needed(self, trace_id: str = "") -> None:
        """Trigger eviction if WARM tier is under pressure."""
        warm_pressure = self._size_tracker.get_pressure("warm")
        if warm_pressure in (PressureLevel.CRITICAL, PressureLevel.EMERGENCY):
            logger.info("Triggering eviction due to WARM pressure: %s", warm_pressure.value)
            # Target 70% utilization
            target_bytes = int(WARM_SIZE_LIMIT_BYTES * 0.70)
            current = self._size_tracker.get_tier_size("warm")
            bytes_to_free = current - target_bytes
            if bytes_to_free > 0:
                # W7: emit EvictionTriggered before doing the work.
                candidates = sorted(WARM_SECTIONS)
                self._safe_emit(
                    EventType.EVICTION_TRIGGERED.value,
                    SessionStateEvents.eviction_triggered(
                        session_id=self._session_id,
                        cognitive_trace_id=trace_id,
                        target_reduction_bytes=bytes_to_free,
                        pressure_level=warm_pressure,
                        candidates=candidates,
                    ),
                )
                start_ms = time.perf_counter() * 1000.0
                result = self._eviction_engine.evict(target_bytes=bytes_to_free)
                duration_ms = (time.perf_counter() * 1000.0) - start_ms
                # W7: emit EvictionCompleted with whatever the engine reports.
                bytes_freed = getattr(result, "bytes_freed", 0) or 0
                bytes_archived = getattr(result, "bytes_archived", 0) or 0
                sections_evicted = getattr(result, "sections_evicted", []) or []
                self._safe_emit(
                    EventType.EVICTION_COMPLETED.value,
                    SessionStateEvents.eviction_completed(
                        session_id=self._session_id,
                        cognitive_trace_id=trace_id,
                        sections_evicted=list(sections_evicted),
                        bytes_freed=int(bytes_freed),
                        bytes_archived=int(bytes_archived),
                        new_pressure_level=self._size_tracker.get_pressure("warm"),
                        duration_ms=duration_ms,
                    ),
                )

    def _emit_emergency_activated(self, pressure: PressureLevel, trace_id: str) -> None:
        """W7: publish EmergencyActivatedEvent on rising-edge pressure."""
        try:
            level = (
                EmergencyLevel.CRITICAL
                if pressure == PressureLevel.EMERGENCY
                else EmergencyLevel.WARNING
            )
            hot_size = self._size_tracker.get_tier_size("hot")
            warm_size = self._size_tracker.get_tier_size("warm")
            self._safe_emit(
                EventType.EMERGENCY_ACTIVATED.value,
                SessionStateEvents.emergency_activated(
                    session_id=self._session_id,
                    cognitive_trace_id=trace_id,
                    level=level,
                    total_size_bytes=hot_size + warm_size,
                    hot_size_bytes=hot_size,
                    warm_size_bytes=warm_size,
                    writes_blocked=False,
                ),
            )
        except Exception:  # pragma: no cover - never let observability break mutate()
            logger.debug("EmergencyActivated emit failed", exc_info=True)

    def _safe_emit(self, event_type: str, payload: Any) -> None:
        """Fire-and-forget event emission; swallows errors."""
        port = self._event_port
        if port is None:
            return
        try:
            port.emit(event_type, payload)
        except Exception:  # pragma: no cover - emit must never raise upward
            logger.debug("Event emit failed for %s", event_type, exc_info=True)

    def _trigger_migration_if_needed(self) -> None:
        """Trigger migration if HOT tier is under pressure."""
        hot_pressure = self._size_tracker.get_pressure("hot")
        if hot_pressure in (PressureLevel.CRITICAL, PressureLevel.EMERGENCY):
            logger.info("Triggering migration due to HOT pressure: %s", hot_pressure.value)
            self._migration_engine.demote_on_pressure()

    def _sync_size_tracker(self) -> None:
        """
        Synchronize size tracker with actual section sizes.

        Called after start() or restore() to ensure SizeTracker reflects
        the real memory footprint of all sections. This fixes the issue
        where SizeTracker shows 0 bytes because it was never initialized
        with actual section sizes.
        """
        total_synced = 0
        for section_name in ALL_SECTIONS:
            try:
                section = self.get_section(section_name)
                if hasattr(section, "get_size_bytes"):
                    size = section.get_size_bytes()
                    self._size_tracker.set_section_size(section_name, size)
                    total_synced += size
            except SectionNotFoundError:
                # Section not available yet, skip
                pass

        logger.debug(
            "Size tracker synced with actual section sizes (total=%d bytes)",
            total_synced,
        )

    # =========================================================================
    # LIFECYCLE API (Issue 2.5.4)
    # =========================================================================
    # Checkpoint: Periodic snapshot to LOCAL COLD
    # Restore: Hydrate from LOCAL COLD (or K0 fallback)

    def start(
        self,
        restore_if_exists: bool = True,
        cognitive_trace_id: Optional[str] = None,
    ) -> StartResult:
        """
        Start the SessionState lifecycle.

        Actions:
            1. Transition state to STARTING
            2. Try to restore from checkpoint if restore_if_exists=True
            3. Initialize all sections to empty state if no checkpoint
            4. Transition state to RUNNING

        Args:
            restore_if_exists: Whether to try restoring from checkpoint
            cognitive_trace_id: Trace ID for distributed tracing correlation

        Returns:
            StartResult: Success/failure with timing info
        """
        trace_id = cognitive_trace_id or ""
        start_time = time.time()

        if self._state not in (ManagerState.CREATED, ManagerState.STOPPED):
            return StartResult(
                success=False,
                session_id=self._session_id,
                error=f"Cannot start from state: {self._state.value}",
                cognitive_trace_id=trace_id,
            )

        self._state = ManagerState.STARTING
        logger.info(
            "SessionState state transition: CREATED -> STARTING (session=%s)",
            self._session_id[:8] if self._session_id else "none",
        )

        try:
            restore_source = "fresh"
            restored = False

            # Try to restore if requested
            if restore_if_exists:
                restore_result = self.restore(
                    self._session_id,
                    cognitive_trace_id=trace_id,
                )
                if restore_result.success and restore_result.source != "fresh":
                    restore_source = restore_result.source
                    restored = True

            # Transition to RUNNING
            self._state = ManagerState.RUNNING
            self._started_at_ms = int(time.time() * 1000)

            # Sync size tracker with actual section sizes
            self._sync_size_tracker()

            duration_ms = (time.time() - start_time) * 1000

            logger.info(
                "SessionStateManager started (session=%s, restored=%s, source=%s, took=%.2fms, trace_id=%s)",
                self._session_id[:8] if self._session_id else "none",
                restored,
                restore_source,
                duration_ms,
                trace_id,
            )

            return StartResult(
                success=True,
                session_id=self._session_id,
                duration_ms=duration_ms,
                restored=restored,
                restore_source=restore_source,
                cognitive_trace_id=trace_id,
            )

        except Exception as e:
            self._state = ManagerState.ERROR
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "Failed to start SessionStateManager: %s, trace_id=%s",
                str(e),
                trace_id,
            )
            return StartResult(
                success=False,
                session_id=self._session_id,
                duration_ms=duration_ms,
                error=str(e),
                cognitive_trace_id=trace_id,
            )

    def stop(
        self,
        checkpoint_before_stop: bool = True,
        cognitive_trace_id: Optional[str] = None,
    ) -> StopResult:
        """
        Stop the SessionState lifecycle gracefully.

        Actions:
            1. Transition state to STOPPING
            2. Final checkpoint to LOCAL COLD (if checkpoint_before_stop=True)
            3. Transition state to STOPPED

        Args:
            checkpoint_before_stop: Whether to checkpoint before stopping
            cognitive_trace_id: Trace ID for distributed tracing correlation

        Returns:
            StopResult: Success/failure with timing info
        """
        trace_id = cognitive_trace_id or ""
        start_time = time.time()

        if self._state not in (ManagerState.RUNNING, ManagerState.STARTING):
            return StopResult(
                success=False,
                error=f"Cannot stop from state: {self._state.value}",
                cognitive_trace_id=trace_id,
            )

        self._state = ManagerState.STOPPING
        logger.info(
            "SessionState state transition: RUNNING -> STOPPING (session=%s, mutations=%d)",
            self._session_id[:8] if self._session_id else "none",
            self._mutation_count,
        )

        checkpoint_id: Optional[str] = None

        try:
            # Final checkpoint
            if checkpoint_before_stop:
                checkpoint_result = self.checkpoint(cognitive_trace_id=trace_id)
                if checkpoint_result.success:
                    checkpoint_id = checkpoint_result.checkpoint_id

            # Transition to STOPPED
            self._state = ManagerState.STOPPED

            duration_ms = (time.time() - start_time) * 1000

            logger.info(
                "SessionStateManager stopped (session=%s, checkpoint=%s, took=%.2fms, trace_id=%s)",
                self._session_id[:8] if self._session_id else "none",
                checkpoint_id or "none",
                duration_ms,
                trace_id,
            )

            return StopResult(
                success=True,
                checkpoint_id=checkpoint_id,
                duration_ms=duration_ms,
                cognitive_trace_id=trace_id,
            )

        except Exception as e:
            self._state = ManagerState.ERROR
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "Failed to stop SessionStateManager: %s, trace_id=%s",
                str(e),
                trace_id,
            )
            return StopResult(
                success=False,
                duration_ms=duration_ms,
                error=str(e),
                cognitive_trace_id=trace_id,
            )

    def checkpoint(self, cognitive_trace_id: Optional[str] = None) -> CheckpointResult:
        """
        Checkpoint current state to LOCAL COLD (K1 SQLite).

        Purpose:
            Periodic durability snapshot for offline recovery.

        Actions:
            1. Serialize all sections (FlatBuffer data + metadata)
            2. Write to K1 SQLite via LocalColdTier
            3. Optional: Queue sync to K0 via IK0SyncPort (non-blocking)

        Args:
            cognitive_trace_id: Trace ID for distributed tracing correlation

        Returns:
            CheckpointResult with success/failure and timing info

        SLA:
            - <50ms for LOCAL COLD write
        """
        trace_id = cognitive_trace_id or ""
        start_time = time.time()
        checkpoint_id = str(uuid.uuid4())

        try:
            # Collect snapshot metadata
            snapshot = self.get_snapshot()

            # Serialize ACTUAL section data (FlatBuffers), not just metadata
            section_data: Dict[str, str] = {}
            import base64

            # Serialize HOT sections
            for section_name in HOT_SECTIONS:
                try:
                    section = self._hot.get_section(section_name)
                    if section:
                        fb_bytes = section.to_flatbuffer()
                        section_data[section_name] = base64.b64encode(fb_bytes).decode("ascii")
                except Exception as e:
                    logger.warning("Failed to serialize HOT section %s: %s", section_name, e)

            # Serialize WARM sections
            for section_name in WARM_SECTIONS:
                try:
                    section = self._warm.get_section(section_name)
                    if section:
                        fb_bytes = section.to_flatbuffer()
                        section_data[section_name] = base64.b64encode(fb_bytes).decode("ascii")
                except Exception as e:
                    logger.warning("Failed to serialize WARM section %s: %s", section_name, e)

            # Build checkpoint with both metadata and section data
            checkpoint_dict = {
                "metadata": snapshot.to_dict(),
                "section_data": section_data,
                "version": 2,  # Version 2 includes section data
            }

            # Serialize checkpoint
            checkpoint_data = json.dumps(checkpoint_dict).encode("utf-8")
            size_bytes = len(checkpoint_data)

            # Write to LOCAL COLD
            archive_result = self._local_cold.archive(
                section="checkpoint",
                data=checkpoint_data,
                metadata={
                    "checkpoint_id": checkpoint_id,
                    "session_id": self._session_id,
                    "timestamp_ms": snapshot.timestamp_ms,
                },
            )

            duration_ms = (time.time() - start_time) * 1000
            sla_met = duration_ms < 50.0

            if archive_result.success:
                logger.info(
                    "Checkpoint created: id=%s, size=%dB, took=%.2fms, sla_met=%s, trace_id=%s",
                    checkpoint_id[:8],
                    size_bytes,
                    duration_ms,
                    sla_met,
                    trace_id,
                )
                return CheckpointResult(
                    success=True,
                    checkpoint_id=checkpoint_id,
                    size_bytes=size_bytes,
                    duration_ms=duration_ms,
                    sla_met=sla_met,
                    cognitive_trace_id=trace_id,
                )
            else:
                return CheckpointResult(
                    success=False,
                    checkpoint_id=checkpoint_id,
                    duration_ms=duration_ms,
                    error=archive_result.error,
                    cognitive_trace_id=trace_id,
                )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error("Checkpoint failed: %s, trace_id=%s", str(e), trace_id)
            return CheckpointResult(
                success=False,
                checkpoint_id=checkpoint_id,
                duration_ms=duration_ms,
                error=str(e),
                cognitive_trace_id=trace_id,
            )

    def restore(
        self,
        session_id: str,
        cognitive_trace_id: Optional[str] = None,
    ) -> RestoreResult:
        """
        Restore session from LOCAL COLD (or K0 fallback).

        Edge-First Strategy:
            1. Try LOCAL COLD (K1 SQLite) first - always available
            2. If not found: start fresh session

        Hydration Order:
            1. HOT sections first (for immediate responsiveness)
            2. WARM sections next
            3. Do NOT load full COLD - lazy load on demand

        Args:
            session_id: Session to restore
            cognitive_trace_id: Trace ID for distributed tracing correlation

        Returns:
            RestoreResult with success/failure and timing info

        SLA:
            - <50ms from LOCAL COLD
        """
        trace_id = cognitive_trace_id or ""
        start_time = time.time()

        try:
            # Try LOCAL COLD first
            restore_result = self._local_cold.restore(section="checkpoint")

            if restore_result.success and restore_result.data:
                # Parse checkpoint data
                checkpoint_data = json.loads(restore_result.data.decode("utf-8"))

                # Hydrate sections from checkpoint
                sections_restored = self._hydrate_from_checkpoint(checkpoint_data)

                duration_ms = (time.time() - start_time) * 1000
                sla_met = duration_ms < 50.0

                logger.info(
                    "Session restored from local_cold: session=%s, sections=%d, took=%.2fms, trace_id=%s",
                    session_id[:8] if session_id else "none",
                    len(sections_restored),
                    duration_ms,
                    trace_id,
                )

                return RestoreResult(
                    success=True,
                    source="local_cold",
                    sections_restored=sections_restored,
                    hot_restored=any(s in HOT_SECTIONS for s in sections_restored),
                    warm_restored=any(s in WARM_SECTIONS for s in sections_restored),
                    duration_ms=duration_ms,
                    sla_met=sla_met,
                    cognitive_trace_id=trace_id,
                )

            # No checkpoint found - start fresh
            duration_ms = (time.time() - start_time) * 1000

            logger.debug(
                "No checkpoint found, starting fresh: session=%s, trace_id=%s",
                session_id[:8] if session_id else "none",
                trace_id,
            )

            return RestoreResult(
                success=True,
                source="fresh",
                sections_restored=[],
                duration_ms=duration_ms,
                cognitive_trace_id=trace_id,
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error("Restore failed: %s, trace_id=%s", str(e), trace_id)
            return RestoreResult(
                success=False,
                source="fresh",
                duration_ms=duration_ms,
                error=str(e),
                cognitive_trace_id=trace_id,
            )

    def _hydrate_from_checkpoint(self, checkpoint_data: Dict[str, Any]) -> List[str]:
        """
        Hydrate sections from checkpoint data.

        Supports two checkpoint versions:
            - Version 1 (legacy): Only size metadata, no section data
            - Version 2: Full section data (FlatBuffer encoded, base64 wrapped)

        Returns list of sections that were restored.
        """
        sections_restored: List[str] = []
        import base64

        # Check checkpoint version
        version = checkpoint_data.get("version", 1)

        if version >= 2:
            # Version 2: Full section data restoration
            section_data = checkpoint_data.get("section_data", {})
            metadata = checkpoint_data.get("metadata", {})
            sections_metadata = metadata.get("sections", {})

            # Hydrate HOT sections first
            for section_name in HOT_SECTIONS:
                if section_name in section_data:
                    try:
                        # Decode FlatBuffer data
                        fb_bytes = base64.b64decode(section_data[section_name])

                        # Get section and restore data
                        section = self._hot.get_section(section_name)
                        if section:
                            section.from_flatbuffer(fb_bytes)

                            # Update size tracker with actual size
                            actual_size = section.get_size_bytes()
                            self._size_tracker.set_section_size(section_name, actual_size)
                            sections_restored.append(section_name)

                            logger.debug(
                                "Restored HOT section %s: %d bytes",
                                section_name,
                                actual_size,
                            )
                    except Exception as e:
                        logger.warning("Failed to restore HOT section %s: %s", section_name, e)

            # Then WARM sections
            for section_name in WARM_SECTIONS:
                if section_name in section_data:
                    try:
                        # Decode FlatBuffer data
                        fb_bytes = base64.b64decode(section_data[section_name])

                        # Get section and restore data
                        section = self._warm.get_section(section_name)
                        if section:
                            section.from_flatbuffer(fb_bytes)

                            # Update size tracker with actual size
                            actual_size = section.get_size_bytes()
                            self._size_tracker.set_section_size(section_name, actual_size)
                            sections_restored.append(section_name)

                            logger.debug(
                                "Restored WARM section %s: %d bytes",
                                section_name,
                                actual_size,
                            )
                    except Exception as e:
                        logger.warning("Failed to restore WARM section %s: %s", section_name, e)

        else:
            # Version 1 (legacy): Only update size tracker from metadata
            sections_data = checkpoint_data.get("sections", {})

            for section_name in HOT_SECTIONS:
                if section_name in sections_data:
                    section_info = sections_data[section_name]
                    if section_info.get("size_bytes", 0) > 0:
                        self._size_tracker.set_section_size(
                            section_name, section_info.get("size_bytes", 0)
                        )
                        sections_restored.append(section_name)

            for section_name in WARM_SECTIONS:
                if section_name in sections_data:
                    section_info = sections_data[section_name]
                    if section_info.get("size_bytes", 0) > 0:
                        self._size_tracker.set_section_size(
                            section_name, section_info.get("size_bytes", 0)
                        )
                        sections_restored.append(section_name)

        return sections_restored
