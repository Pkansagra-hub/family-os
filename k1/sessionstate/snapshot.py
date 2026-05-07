"""
SnapshotAPI - Health Monitoring and Diagnostics
=================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.1 Kernel Services
ISSUE: 2.1.6

==============================================================================
SPECIFICATION
==============================================================================

PURPOSE:
    Provide health monitoring and diagnostics for SessionState.
    Used by CLI, observability, and debugging tools.

SNAPSHOT CONTENTS:
    - Size breakdown per section
    - Tier utilization (HOT %, WARM %)
    - Current pressure level
    - Thrash detection metrics
    - Last mutation timestamp

==============================================================================
CLASS: SnapshotAPI
==============================================================================
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Deque, Dict, List, Optional

if TYPE_CHECKING:
    from poc.k1_poc.sessionstate.tiers.hot import HotTier
    from poc.k1_poc.sessionstate.tiers.warm import WarmTier

from .config import SessionStateConfig
from .sizetracker import (
    HOT_SECTIONS,
    HOT_SIZE_LIMIT_BYTES,
    SECTION_BUDGETS,
    TOTAL_SIZE_LIMIT_BYTES,
    WARM_SECTIONS,
    WARM_SIZE_LIMIT_BYTES,
    PressureLevel,
    SizeTracker,
)

logger = logging.getLogger(__name__)


@dataclass
class SectionSnapshot:
    """
    Snapshot of a single section's state.

    Attributes:
        name: Section name
        tier: Tier name ('hot' or 'warm')
        size_bytes: Current size in bytes
        budget_bytes: Maximum allowed size
        utilization_pct: Current utilization percentage
        pressure: Section-specific pressure level
        last_mutation_ms: Timestamp of last mutation
        eviction_priority: Eviction priority (None for HOT/NEVER_EVICT)
    """

    name: str
    tier: str
    size_bytes: int
    budget_bytes: int
    utilization_pct: float
    pressure: PressureLevel
    last_mutation_ms: int
    eviction_priority: Optional[int] = None


@dataclass
class TierSnapshot:
    """
    Snapshot of a tier's state.

    Attributes:
        name: Tier name ('hot' or 'warm')
        sections: List of section names in this tier
        size_bytes: Current total size
        limit_bytes: Maximum allowed size
        utilization_pct: Current utilization percentage
        pressure: Tier pressure level
    """

    name: str
    sections: List[str]
    size_bytes: int
    limit_bytes: int
    utilization_pct: float
    pressure: PressureLevel


@dataclass
class ThrashMetrics:
    """
    Metrics for detecting thrashing (excessive migration/eviction).

    Attributes:
        migrations_last_minute: Number of migrations in last 60s
        evictions_last_minute: Number of evictions in last 60s
        thrash_detected: Whether thrashing is occurring
        thrash_severity: 0=none, 1=mild, 2=moderate, 3=severe
    """

    migrations_last_minute: int
    evictions_last_minute: int
    thrash_detected: bool
    thrash_severity: int


@dataclass
class PressureReport:
    """
    Detailed pressure report for diagnostics.

    Attributes:
        overall: Overall pressure level
        hot: HOT tier pressure
        warm: WARM tier pressure
        sections_at_limit: Sections at or near capacity
        eviction_candidates: Sections eligible for eviction
        estimated_eviction_bytes: Bytes needed to reach NORMAL
    """

    overall: PressureLevel
    hot: PressureLevel
    warm: PressureLevel
    sections_at_limit: List[str]
    eviction_candidates: List[str]
    estimated_eviction_bytes: int


@dataclass
class SessionSnapshot:
    """
    Complete snapshot of SessionState.

    Attributes:
        session_id: Session identifier
        total_size_bytes: Total size across all sections
        hot_size_bytes: HOT tier size
        warm_size_bytes: WARM tier size
        utilization_pct: Overall utilization percentage
        pressure: Current pressure level
        sections: Dict of section snapshots
        tiers: Dict of tier snapshots
        thrash_metrics: Thrashing detection metrics
        last_mutation_ms: Timestamp of last mutation
        last_checkpoint_ms: Timestamp of last checkpoint
        created_at_ms: Session creation timestamp
    """

    session_id: str
    total_size_bytes: int
    hot_size_bytes: int
    warm_size_bytes: int
    utilization_pct: float
    pressure: PressureLevel
    sections: Dict[str, SectionSnapshot]
    tiers: Dict[str, TierSnapshot]
    thrash_metrics: ThrashMetrics
    last_mutation_ms: int
    last_checkpoint_ms: int
    created_at_ms: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert snapshot to dictionary for JSON serialization."""
        return {
            "session_id": self.session_id,
            "total_size_bytes": self.total_size_bytes,
            "hot_size_bytes": self.hot_size_bytes,
            "warm_size_bytes": self.warm_size_bytes,
            "utilization_pct": round(self.utilization_pct, 4),
            "pressure": self.pressure.value,
            "sections": {
                name: {
                    "name": sec.name,
                    "tier": sec.tier,
                    "size_bytes": sec.size_bytes,
                    "budget_bytes": sec.budget_bytes,
                    "utilization_pct": round(sec.utilization_pct, 4),
                    "pressure": sec.pressure.value,
                    "last_mutation_ms": sec.last_mutation_ms,
                    "eviction_priority": sec.eviction_priority,
                }
                for name, sec in self.sections.items()
            },
            "tiers": {
                name: {
                    "name": tier.name,
                    "sections": tier.sections,
                    "size_bytes": tier.size_bytes,
                    "limit_bytes": tier.limit_bytes,
                    "utilization_pct": round(tier.utilization_pct, 4),
                    "pressure": tier.pressure.value,
                }
                for name, tier in self.tiers.items()
            },
            "thrash_metrics": {
                "migrations_last_minute": self.thrash_metrics.migrations_last_minute,
                "evictions_last_minute": self.thrash_metrics.evictions_last_minute,
                "thrash_detected": self.thrash_metrics.thrash_detected,
                "thrash_severity": self.thrash_metrics.thrash_severity,
            },
            "last_mutation_ms": self.last_mutation_ms,
            "last_checkpoint_ms": self.last_checkpoint_ms,
            "created_at_ms": self.created_at_ms,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionSnapshot":
        """Reconstruct ``SessionSnapshot`` from its ``to_dict`` form.

        Used by ``PlanRequest.from_dict`` so that a plan-request envelope
        round-trips through the bus serializer without data loss.
        """
        sections: Dict[str, SectionSnapshot] = {}
        for name, sec in (data.get("sections") or {}).items():
            sections[name] = SectionSnapshot(
                name=sec.get("name", name),
                tier=sec.get("tier", ""),
                size_bytes=int(sec.get("size_bytes", 0)),
                budget_bytes=int(sec.get("budget_bytes", 0)),
                utilization_pct=float(sec.get("utilization_pct", 0.0)),
                pressure=PressureLevel(sec.get("pressure", PressureLevel.NORMAL.value)),
                last_mutation_ms=int(sec.get("last_mutation_ms", 0)),
                eviction_priority=sec.get("eviction_priority"),
            )

        tiers: Dict[str, TierSnapshot] = {}
        for name, tier in (data.get("tiers") or {}).items():
            tiers[name] = TierSnapshot(
                name=tier.get("name", name),
                sections=list(tier.get("sections", [])),
                size_bytes=int(tier.get("size_bytes", 0)),
                limit_bytes=int(tier.get("limit_bytes", 0)),
                utilization_pct=float(tier.get("utilization_pct", 0.0)),
                pressure=PressureLevel(tier.get("pressure", PressureLevel.NORMAL.value)),
            )

        thrash_raw = data.get("thrash_metrics") or {}
        thrash = ThrashMetrics(
            migrations_last_minute=int(thrash_raw.get("migrations_last_minute", 0)),
            evictions_last_minute=int(thrash_raw.get("evictions_last_minute", 0)),
            thrash_detected=bool(thrash_raw.get("thrash_detected", False)),
            thrash_severity=int(thrash_raw.get("thrash_severity", 0)),
        )

        return cls(
            session_id=data.get("session_id", ""),
            total_size_bytes=int(data.get("total_size_bytes", 0)),
            hot_size_bytes=int(data.get("hot_size_bytes", 0)),
            warm_size_bytes=int(data.get("warm_size_bytes", 0)),
            utilization_pct=float(data.get("utilization_pct", 0.0)),
            pressure=PressureLevel(data.get("pressure", PressureLevel.NORMAL.value)),
            sections=sections,
            tiers=tiers,
            thrash_metrics=thrash,
            last_mutation_ms=int(data.get("last_mutation_ms", 0)),
            last_checkpoint_ms=int(data.get("last_checkpoint_ms", 0)),
            created_at_ms=int(data.get("created_at_ms", 0)),
        )


# Thrash detection thresholds (config-backed: sessionstate.thrash.*)
THRASH_MILD_MIGRATIONS = 5
THRASH_MILD_EVICTIONS = 2
THRASH_MODERATE_MIGRATIONS = 10
THRASH_MODERATE_EVICTIONS = 5
THRASH_SEVERE_MIGRATIONS = 20
THRASH_SEVERE_EVICTIONS = 10

# Rolling window for thrash detection (config: sessionstate.thrash.window_ms)
THRASH_WINDOW_MS = 60_000


class SnapshotAPI:
    """
    Provides health monitoring and diagnostics for SessionState.

    Attributes:
        _size_tracker: SizeTracker for capacity data
        _hot: HotTier (optional)
        _warm: WarmTier (optional)
        _session_id: Session identifier
        _migration_timestamps: Deque of recent migration timestamps (ms)
        _eviction_timestamps: Deque of recent eviction timestamps (ms)
        _last_mutation_ms: Timestamp of last mutation
        _last_checkpoint_ms: Timestamp of last checkpoint
        _created_at_ms: Session creation timestamp

    Example:
        api = SnapshotAPI(size_tracker, hot, warm, session_id)

        # Get complete snapshot
        snapshot = api.get_snapshot()
        print(f"Total: {snapshot.total_size_bytes} bytes")
        print(f"Pressure: {snapshot.pressure}")

        # Get pressure report
        report = api.get_pressure_report()
        if report.eviction_candidates:
            print(f"Eviction candidates: {report.eviction_candidates}")
    """

    def __init__(
        self,
        size_tracker: SizeTracker,
        hot: Optional[HotTier] = None,
        warm: Optional[WarmTier] = None,
        session_id: str = "",
        created_at_ms: Optional[int] = None,
        config: Optional[SessionStateConfig] = None,
    ) -> None:
        """
        Initialize SnapshotAPI.

        Args:
            size_tracker: SizeTracker for capacity data
            hot: HotTier (optional for testing)
            warm: WarmTier (optional for testing)
            session_id: Session identifier
            created_at_ms: Session creation timestamp (default: now)
            config: Optional SessionStateConfig (defaults used if None)
        """
        self._ss_cfg = config or SessionStateConfig()
        self._size_tracker = size_tracker
        self._hot = hot
        self._warm = warm
        self._session_id = session_id

        # Timestamps (ms)
        now_ms = int(time.time() * 1000)
        self._created_at_ms = created_at_ms if created_at_ms is not None else now_ms
        self._last_mutation_ms = 0
        self._last_checkpoint_ms = 0

        # Thrash detection - rolling window of timestamps
        self._migration_timestamps: Deque[int] = deque()
        self._eviction_timestamps: Deque[int] = deque()

        # Section mutation timestamps (optional, for detailed tracking)
        self._section_mutation_ms: Dict[str, int] = {
            name: 0 for name in list(HOT_SECTIONS) + list(WARM_SECTIONS)
        }

    @property
    def session_id(self) -> str:
        """Session identifier."""
        return self._session_id

    @property
    def created_at_ms(self) -> int:
        """Session creation timestamp."""
        return self._created_at_ms

    @property
    def last_mutation_ms(self) -> int:
        """Timestamp of last mutation."""
        return self._last_mutation_ms

    @property
    def last_checkpoint_ms(self) -> int:
        """Timestamp of last checkpoint."""
        return self._last_checkpoint_ms

    def record_mutation(self, section: Optional[str] = None) -> None:
        """
        Record a mutation event.

        Args:
            section: Optional section that was mutated
        """
        now_ms = int(time.time() * 1000)
        self._last_mutation_ms = now_ms
        if section and section in self._section_mutation_ms:
            self._section_mutation_ms[section] = now_ms

    def record_checkpoint(self) -> None:
        """Record a checkpoint event."""
        self._last_checkpoint_ms = int(time.time() * 1000)

    def get_snapshot(self) -> SessionSnapshot:
        """
        Get complete session snapshot.

        Returns:
            SessionSnapshot: Complete state snapshot

        Performance:
            Should be <1ms (read-only, no locks)
        """
        # Get size snapshot from tracker
        size_snap = self._size_tracker.get_snapshot()

        # Build section snapshots
        sections: Dict[str, SectionSnapshot] = {}
        for name in list(HOT_SECTIONS) + list(WARM_SECTIONS):
            sections[name] = self.get_section_snapshot(name)

        # Build tier snapshots
        tiers: Dict[str, TierSnapshot] = {
            "hot": self.get_tier_snapshot("hot"),
            "warm": self.get_tier_snapshot("warm"),
        }

        # Get thrash metrics
        thrash = self.get_thrash_metrics()

        # Calculate overall utilization
        utilization = (
            size_snap.total / TOTAL_SIZE_LIMIT_BYTES if TOTAL_SIZE_LIMIT_BYTES > 0 else 0.0
        )

        return SessionSnapshot(
            session_id=self._session_id,
            total_size_bytes=size_snap.total,
            hot_size_bytes=size_snap.hot_total,
            warm_size_bytes=size_snap.warm_total,
            utilization_pct=utilization * 100,
            pressure=size_snap.overall_pressure,
            sections=sections,
            tiers=tiers,
            thrash_metrics=thrash,
            last_mutation_ms=self._last_mutation_ms,
            last_checkpoint_ms=self._last_checkpoint_ms,
            created_at_ms=self._created_at_ms,
        )

    def get_pressure_report(self) -> PressureReport:
        """
        Get detailed pressure report.

        Returns:
            PressureReport: Pressure analysis with recommendations
        """
        hot_pressure = self._size_tracker.get_pressure("hot")
        warm_pressure = self._size_tracker.get_pressure("warm")
        overall_pressure = self._size_tracker.get_pressure()

        # Find sections at limit (>90% utilization)
        sections_at_limit: List[str] = []
        for name in list(HOT_SECTIONS) + list(WARM_SECTIONS):
            section_pressure = self._size_tracker.get_section_pressure(name)
            if section_pressure in (PressureLevel.CRITICAL, PressureLevel.EMERGENCY):
                sections_at_limit.append(name)

        # Get eviction candidates from WARM tier
        eviction_candidates: List[str] = []
        warm_candidates = self._size_tracker.get_eviction_candidates("warm")
        eviction_candidates = [name for name, _, _ in warm_candidates]

        # Estimate bytes needed to reach NORMAL (<80%)
        warm_size = self._size_tracker.get_tier_size("warm")
        normal_threshold = int(WARM_SIZE_LIMIT_BYTES * 0.8)
        estimated_eviction = max(0, warm_size - normal_threshold)

        return PressureReport(
            overall=overall_pressure,
            hot=hot_pressure,
            warm=warm_pressure,
            sections_at_limit=sections_at_limit,
            eviction_candidates=eviction_candidates,
            estimated_eviction_bytes=estimated_eviction,
        )

    def get_section_snapshot(self, section: str) -> SectionSnapshot:
        """
        Get snapshot of a specific section.

        Args:
            section: Section name

        Returns:
            SectionSnapshot: Section state

        Raises:
            KeyError: If section not found
        """
        # Get budget info
        budget = SECTION_BUDGETS.get(section)
        if budget is None:
            raise KeyError(f"Unknown section: {section}")

        # Get current size
        size_bytes = self._size_tracker.get_section_size(section)

        # Calculate utilization
        utilization = size_bytes / budget.max_bytes if budget.max_bytes > 0 else 0.0

        # Get section pressure
        pressure = self._size_tracker.get_section_pressure(section)

        # Get last mutation time
        last_mutation = self._section_mutation_ms.get(section, 0)

        return SectionSnapshot(
            name=section,
            tier=budget.tier.value,
            size_bytes=size_bytes,
            budget_bytes=budget.max_bytes,
            utilization_pct=utilization * 100,
            pressure=pressure,
            last_mutation_ms=last_mutation,
            eviction_priority=budget.eviction_priority,
        )

    def get_tier_snapshot(self, tier: str) -> TierSnapshot:
        """
        Get snapshot of a specific tier.

        Args:
            tier: Tier name ('hot' or 'warm')

        Returns:
            TierSnapshot: Tier state

        Raises:
            ValueError: If tier name is invalid
        """
        tier_lower = tier.lower()

        if tier_lower == "hot":
            sections = list(HOT_SECTIONS)
            limit_bytes = HOT_SIZE_LIMIT_BYTES
        elif tier_lower == "warm":
            sections = list(WARM_SECTIONS)
            limit_bytes = WARM_SIZE_LIMIT_BYTES
        else:
            raise ValueError(f"Invalid tier: {tier}. Must be 'hot' or 'warm'.")

        size_bytes = self._size_tracker.get_tier_size(tier_lower)
        utilization = size_bytes / limit_bytes if limit_bytes > 0 else 0.0
        pressure = self._size_tracker.get_pressure(tier_lower)

        return TierSnapshot(
            name=tier_lower,
            sections=sections,
            size_bytes=size_bytes,
            limit_bytes=limit_bytes,
            utilization_pct=utilization * 100,
            pressure=pressure,
        )

    def get_thrash_metrics(self) -> ThrashMetrics:
        """
        Get thrashing detection metrics.

        Returns:
            ThrashMetrics: Recent migration/eviction activity

        Thrash detection:
        - Mild: >5 migrations OR >2 evictions per minute
        - Moderate: >10 migrations OR >5 evictions per minute
        - Severe: >20 migrations OR >10 evictions per minute
        """
        self._prune_old_timestamps()

        migrations = len(self._migration_timestamps)
        evictions = len(self._eviction_timestamps)

        # Determine severity
        severity = 0
        thrash_detected = False
        _cfg_thrash = self._ss_cfg.thrash

        if migrations >= _cfg_thrash.severe_migrations or evictions >= _cfg_thrash.severe_evictions:
            severity = 3
            thrash_detected = True
        elif (
            migrations >= _cfg_thrash.moderate_migrations
            or evictions >= _cfg_thrash.moderate_evictions
        ):
            severity = 2
            thrash_detected = True
        elif migrations >= _cfg_thrash.mild_migrations or evictions >= _cfg_thrash.mild_evictions:
            severity = 1
            thrash_detected = True

        return ThrashMetrics(
            migrations_last_minute=migrations,
            evictions_last_minute=evictions,
            thrash_detected=thrash_detected,
            thrash_severity=severity,
        )

    def record_migration(self) -> None:
        """
        Record a migration event for thrash detection.

        Called by MigrationEngine after each migration.
        """
        now_ms = int(time.time() * 1000)
        self._migration_timestamps.append(now_ms)
        self._prune_old_timestamps()

    def record_eviction(self) -> None:
        """
        Record an eviction event for thrash detection.

        Called by EvictionEngine after each eviction.
        """
        now_ms = int(time.time() * 1000)
        self._eviction_timestamps.append(now_ms)
        self._prune_old_timestamps()

    def _prune_old_timestamps(self) -> None:
        """Remove timestamps older than thrash window."""
        now_ms = int(time.time() * 1000)
        cutoff = now_ms - self._ss_cfg.thrash.window_ms

        # Prune migration timestamps
        while self._migration_timestamps and self._migration_timestamps[0] < cutoff:
            self._migration_timestamps.popleft()

        # Prune eviction timestamps
        while self._eviction_timestamps and self._eviction_timestamps[0] < cutoff:
            self._eviction_timestamps.popleft()

    def to_dict(self) -> Dict[str, Any]:
        """
        Export snapshot as dictionary for JSON serialization.

        Returns:
            Dict: Snapshot data suitable for JSON output
        """
        return self.get_snapshot().to_dict()

    def format_table(self) -> str:
        """
        Format snapshot as ASCII table for CLI output.

        Returns:
            str: Formatted table string

        Example output:
            SECTION              TIER   SIZE    BUDGET   USAGE   PRESSURE
            control              HOT    2.1KB   8KB      26%     NORMAL
            beliefs_active       HOT    1.5KB   8KB      19%     NORMAL
            ...
        """
        snapshot = self.get_snapshot()

        lines = []

        # Header
        lines.append(
            f"{'SECTION':<20} {'TIER':<6} {'SIZE':>8} {'BUDGET':>8} {'USAGE':>7} {'PRESSURE':<10}"
        )
        lines.append("-" * 65)

        # Sort sections: HOT first, then WARM
        hot_sections = sorted(
            [s for s in snapshot.sections.values() if s.tier == "hot"],
            key=lambda x: x.name,
        )
        warm_sections = sorted(
            [s for s in snapshot.sections.values() if s.tier == "warm"],
            key=lambda x: x.name,
        )

        for section in hot_sections + warm_sections:
            size_str = self._format_bytes(section.size_bytes)
            budget_str = self._format_bytes(section.budget_bytes)
            usage_str = f"{section.utilization_pct:.0f}%"
            lines.append(
                f"{section.name:<20} {section.tier.upper():<6} {size_str:>8} "
                f"{budget_str:>8} {usage_str:>7} {section.pressure.value:<10}"
            )

        # Totals
        lines.append("-" * 65)
        lines.append(
            f"{'HOT TOTAL':<20} {'HOT':<6} "
            f"{self._format_bytes(snapshot.hot_size_bytes):>8} "
            f"{self._format_bytes(HOT_SIZE_LIMIT_BYTES):>8} "
            f"{(snapshot.hot_size_bytes / HOT_SIZE_LIMIT_BYTES * 100):.0f}%".rjust(7)
            + f" {snapshot.tiers['hot'].pressure.value:<10}"
        )
        lines.append(
            f"{'WARM TOTAL':<20} {'WARM':<6} "
            f"{self._format_bytes(snapshot.warm_size_bytes):>8} "
            f"{self._format_bytes(WARM_SIZE_LIMIT_BYTES):>8} "
            f"{(snapshot.warm_size_bytes / WARM_SIZE_LIMIT_BYTES * 100):.0f}%".rjust(7)
            + f" {snapshot.tiers['warm'].pressure.value:<10}"
        )
        lines.append("-" * 65)
        lines.append(
            f"{'TOTAL':<20} {'':<6} "
            f"{self._format_bytes(snapshot.total_size_bytes):>8} "
            f"{self._format_bytes(TOTAL_SIZE_LIMIT_BYTES):>8} "
            f"{snapshot.utilization_pct:.0f}%".rjust(7) + f" {snapshot.pressure.value:<10}"
        )

        # Thrash info
        if snapshot.thrash_metrics.thrash_detected:
            lines.append("")
            severity_names = ["", "MILD", "MODERATE", "SEVERE"]
            severity_name = severity_names[snapshot.thrash_metrics.thrash_severity]
            lines.append(
                f"WARNING: {severity_name} thrashing detected! "
                f"Migrations: {snapshot.thrash_metrics.migrations_last_minute}/min, "
                f"Evictions: {snapshot.thrash_metrics.evictions_last_minute}/min"
            )

        return "\n".join(lines)

    @staticmethod
    def _format_bytes(size_bytes: int) -> str:
        """Format bytes as human-readable string."""
        if size_bytes < 1024:
            return f"{size_bytes}B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f}KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f}MB"

    def reset_thrash_metrics(self) -> None:
        """Reset thrash detection counters."""
        self._migration_timestamps.clear()
        self._eviction_timestamps.clear()

    def get_section_names(self) -> List[str]:
        """Get all section names."""
        return list(HOT_SECTIONS) + list(WARM_SECTIONS)

    def get_hot_section_names(self) -> List[str]:
        """Get HOT section names."""
        return list(HOT_SECTIONS)

    def get_warm_section_names(self) -> List[str]:
        """Get WARM section names."""
        return list(WARM_SECTIONS)


# =============================================================================
# IMPLEMENTATION NOTES
# =============================================================================
"""
1. READ-ONLY:
   All methods are read-only.
   No side effects except recording migration/eviction timestamps.

2. PERFORMANCE:
   Snapshot should be <1ms to generate.
   Don't iterate over data, just use SizeTracker counts.

3. THRASH DETECTION:
   Keep rolling window of timestamps (last 60 seconds).
   Prune old timestamps on each query.

4. TIMESTAMP TRACKING:
   - last_mutation_ms: Updated by SessionStateManager
   - last_checkpoint_ms: Updated by checkpoint()
   - created_at_ms: Set on session start

5. OUTPUT FORMATS:
   - to_dict(): For JSON/API responses
   - format_table(): For CLI output

6. TESTING (tests/k1/sessionstate/test_snapshot.py):
   - Test empty session snapshot
   - Test snapshot with data
   - Test pressure report
   - Test thrash detection
   - Test format_table output
"""
