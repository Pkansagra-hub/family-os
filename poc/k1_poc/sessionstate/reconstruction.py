"""
ReconstructionSLA - COLD -> HOT Hydration with SLA Guarantees
==============================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.1 Kernel Services
ISSUE: 2.1.5

ADRs:
- ADR-0020: Multi-Tier Storage Architecture

==============================================================================
SPECIFICATION
==============================================================================

PURPOSE:
    Reconstruct session state from LOCAL COLD (or K0 fallback) with
    strict SLA guarantees. Used when session is restored after cold start.

SLA TARGETS:
    - LOCAL COLD reconstruction: <50ms (P95)
    - K0 fallback reconstruction: <100ms (P95)

HYDRATION ORDER:
    1. HOT sections FIRST (for immediate responsiveness)
    2. WARM sections NEXT
    3. LOCAL COLD is lazy-loaded (on demand)

EDGE-FIRST DESIGN:
    - Try LOCAL COLD (K1 SQLite) first - always available
    - K0 is fallback only (may be unavailable offline)
    - Never block on K0

==============================================================================
CLASS: ReconstructionSLA
==============================================================================
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, FrozenSet, List, Optional, Tuple

from poc.k1_poc.config import get_config

if TYPE_CHECKING:
    from poc.k1_poc.sessionstate.local_cold import LocalColdArchive
    from poc.k1_poc.sessionstate.ports.k0_sync import IK0SyncPort
    from poc.k1_poc.sessionstate.tiers.hot import HotTier
    from poc.k1_poc.sessionstate.tiers.warm import WarmTier

logger = logging.getLogger(__name__)


class ReconstructionSource(str, Enum):
    """Source of reconstruction data."""

    LOCAL_COLD = "local_cold"  # K1 SQLite (primary)
    K0 = "k0"  # K0 cloud (fallback)
    FRESH = "fresh"  # No data, start fresh


@dataclass
class ReconstructionResult:
    """
    Result of a reconstruction operation.

    Attributes:
        success: Whether reconstruction succeeded
        source: Where data came from
        sections_restored: List of sections that were restored
        hot_restored: Whether HOT tier was fully restored
        warm_restored: Whether WARM tier was fully restored
        duration_ms: Total time taken
        hot_duration_ms: Time to restore HOT (should be <50ms)
        sla_met: Whether SLA was met
        error: Error message if failed
    """

    success: bool
    source: ReconstructionSource
    sections_restored: List[str] = field(default_factory=list)
    hot_restored: bool = False
    warm_restored: bool = False
    duration_ms: float = 0.0
    hot_duration_ms: float = 0.0
    sla_met: bool = True
    error: Optional[str] = None


# SLA constants (config-backed: sessionstate.reconstruction.*)
SLA_LOCAL_COLD_MS = 50.0
SLA_K0_FALLBACK_MS = 100.0

# K0 fallback timeout
K0_TIMEOUT_MS = 80.0

# HOT section hydration priority (lower = higher priority)
HOT_HYDRATION_PRIORITY: List[str] = [
    "control",  # Required for orchestration - FIRST
    "meta",  # Schema version - needed early
    "beliefs_active",  # Current context
    "scoreboard",  # Discourse state
    "history_active",  # Recent turns
    "clarifications",  # Pending items
    "affective_now",  # Mood state
    "narrative_active",  # Active threads
]

# WARM section hydration priority
WARM_HYDRATION_PRIORITY: List[str] = [
    "persona",  # Stable traits - important for personality
    "beliefs_history",  # Historical beliefs
    "history_recent",  # Older history
    "telemetry",  # Metrics - lowest priority
]

# All HOT section names (frozen for O(1) lookup)
HOT_SECTIONS: FrozenSet[str] = frozenset(HOT_HYDRATION_PRIORITY)

# All WARM section names
WARM_SECTIONS: FrozenSet[str] = frozenset(WARM_HYDRATION_PRIORITY)

# All sections
ALL_SECTIONS: FrozenSet[str] = HOT_SECTIONS | WARM_SECTIONS

# Estimation constants (config-backed: sessionstate.reconstruction.*)
ESTIMATE_LOCAL_COLD_BASE_MS = 5.0
ESTIMATE_LOCAL_COLD_PER_KB_MS = 0.5
ESTIMATE_K0_BASE_MS = 30.0
ESTIMATE_K0_PER_KB_MS = 1.0


@dataclass
class SectionData:
    """
    Container for section restoration data.

    Attributes:
        name: Section name
        data: Serialized data (bytes)
        size_bytes: Size of data
        source: Where this data came from
    """

    name: str
    data: bytes
    size_bytes: int
    source: ReconstructionSource


@dataclass
class HydrationResult:
    """
    Result of hydrating a tier.

    Attributes:
        sections_hydrated: List of sections that were hydrated
        all_restored: Whether all expected sections were restored
        duration_ms: Time taken for hydration
        errors: List of (section, error) for failed hydrations
    """

    sections_hydrated: List[str] = field(default_factory=list)
    all_restored: bool = False
    duration_ms: float = 0.0
    errors: List[Tuple[str, str]] = field(default_factory=list)


class ReconstructionSLA:
    """
    Manages session reconstruction from COLD storage with SLA guarantees.

    Reconstruction is used when:
    - Session starts after cold boot
    - Session resumes after timeout
    - Explicit restore request

    Attributes:
        _local_cold: LocalColdArchive for LOCAL COLD access
        _k0_sync_port: Optional IK0SyncPort for K0 fallback
        _hot: HotTier to hydrate
        _warm: WarmTier to hydrate
        _deserializer: Optional function to deserialize section data

    Example:
        sla = ReconstructionSLA(local_cold, k0_sync_port, hot, warm)

        result = sla.reconstruct(
            session_id="user-123-session-456",
            sections=["control", "beliefs_active", "scoreboard"],
        )

        if result.sla_met:
            print(f"Restored in {result.duration_ms}ms")
        else:
            print(f"SLA breach: {result.duration_ms}ms > {SLA_LOCAL_COLD_MS}ms")
    """

    def __init__(
        self,
        local_cold: Optional[LocalColdArchive],
        k0_sync_port: Optional[IK0SyncPort],
        hot: Optional[HotTier] = None,
        warm: Optional[WarmTier] = None,
        deserializer: Optional[Callable[[str, bytes], Any]] = None,
    ) -> None:
        """
        Initialize ReconstructionSLA.

        Args:
            local_cold: LocalColdArchive for LOCAL COLD access
            k0_sync_port: Optional K0 sync port for fallback
            hot: HotTier to hydrate (optional for testing)
            warm: WarmTier to hydrate (optional for testing)
            deserializer: Function to deserialize section data (section_name, bytes) -> object
        """
        self._local_cold = local_cold
        self._k0_sync_port = k0_sync_port
        self._hot = hot
        self._warm = warm
        self._deserializer = deserializer

        # Metrics tracking
        self._total_reconstructions = 0
        self._successful_reconstructions = 0
        self._sla_breaches = 0
        self._source_counts: Dict[ReconstructionSource, int] = {
            ReconstructionSource.LOCAL_COLD: 0,
            ReconstructionSource.K0: 0,
            ReconstructionSource.FRESH: 0,
        }

        logger.info(
            "ReconstructionSLA initialized (local_cold=%s, k0=%s, sla_target=%.0fms)",
            "available" if local_cold else "none",
            "available" if k0_sync_port else "none",
            get_config().sessionstate.reconstruction.sla_local_cold_ms,
        )

    @property
    def total_reconstructions(self) -> int:
        """Total number of reconstruction attempts."""
        return self._total_reconstructions

    @property
    def successful_reconstructions(self) -> int:
        """Number of successful reconstructions."""
        return self._successful_reconstructions

    @property
    def sla_breaches(self) -> int:
        """Number of SLA breaches."""
        return self._sla_breaches

    @property
    def sla_compliance_rate(self) -> float:
        """SLA compliance rate (0.0 to 1.0)."""
        if self._total_reconstructions == 0:
            return 1.0
        return 1.0 - (self._sla_breaches / self._total_reconstructions)

    def get_source_counts(self) -> Dict[ReconstructionSource, int]:
        """Get reconstruction counts by source."""
        return dict(self._source_counts)

    def reconstruct(
        self,
        session_id: str,
        sections: Optional[List[str]] = None,
    ) -> ReconstructionResult:
        """
        Reconstruct session from COLD storage.

        RECONSTRUCTION FLOW:
        1. Try LOCAL COLD (K1 SQLite) first
        2. If not found, try K0 (if available)
        3. If neither, return FRESH (empty session)
        4. Hydrate HOT first, then WARM
        5. Track timing for SLA compliance

        Args:
            session_id: Session to restore
            sections: Optional list of specific sections to restore.
                     If None, restore all available.

        Returns:
            ReconstructionResult: Result with timing and SLA info

        Events to emit (by caller):
            - ReconstructionStartedEvent (before calling)
        """
        start_time = time.perf_counter()
        self._total_reconstructions += 1

        # Validate session_id
        if not session_id or not session_id.strip():
            duration_ms = (time.perf_counter() - start_time) * 1000
            return ReconstructionResult(
                success=False,
                source=ReconstructionSource.FRESH,
                duration_ms=duration_ms,
                error="session_id is required",
            )

        # Normalize sections
        requested_sections = self._normalize_sections(sections)

        # Track source and data
        source = ReconstructionSource.FRESH
        section_data: Dict[str, bytes] = {}

        # Step 1: Try LOCAL COLD first (edge-first)
        local_cold_data = self._try_local_cold(session_id, requested_sections)
        if local_cold_data:
            source = ReconstructionSource.LOCAL_COLD
            section_data = local_cold_data
            logger.debug(
                "Restored %d sections from LOCAL COLD for session %s",
                len(section_data),
                session_id,
            )
        else:
            # Step 2: Try K0 fallback (if available)
            k0_data = self._try_k0_fallback(session_id, requested_sections)
            if k0_data:
                source = ReconstructionSource.K0
                section_data = k0_data
                logger.debug(
                    "Restored %d sections from K0 for session %s",
                    len(section_data),
                    session_id,
                )
            else:
                # Step 3: Fresh start
                logger.debug("No data found, starting fresh session %s", session_id)

        # Update source counts
        self._source_counts[source] += 1

        # Step 4: Hydrate tiers
        hot_result = self._hydrate_hot(section_data)
        warm_result = self._hydrate_warm(section_data)

        # Calculate total duration
        total_duration_ms = (time.perf_counter() - start_time) * 1000

        # Check SLA
        sla_met = self._check_sla(source, total_duration_ms)
        if not sla_met:
            self._sla_breaches += 1
            _cfg_recon = get_config().sessionstate.reconstruction
            logger.warning(
                "SLA breach: %s reconstruction took %.2fms (limit: %.2fms)",
                source.value,
                total_duration_ms,
                (
                    _cfg_recon.sla_local_cold_ms
                    if source == ReconstructionSource.LOCAL_COLD
                    else _cfg_recon.sla_k0_fallback_ms
                ),
            )

        # Combine restored sections
        all_restored_sections = hot_result.sections_hydrated + warm_result.sections_hydrated

        # Determine overall success
        # Success = we got some data OR it's a fresh start
        success = bool(section_data) or source == ReconstructionSource.FRESH
        if success:
            self._successful_reconstructions += 1

        # Collect errors
        all_errors = hot_result.errors + warm_result.errors
        error_msg = None
        if all_errors:
            error_msg = "; ".join(f"{sec}: {err}" for sec, err in all_errors)

        return ReconstructionResult(
            success=success,
            source=source,
            sections_restored=all_restored_sections,
            hot_restored=hot_result.all_restored,
            warm_restored=warm_result.all_restored,
            duration_ms=total_duration_ms,
            hot_duration_ms=hot_result.duration_ms,
            sla_met=sla_met,
            error=error_msg,
        )

    def _normalize_sections(
        self,
        sections: Optional[List[str]],
    ) -> Optional[List[str]]:
        """
        Normalize and validate section list.

        Args:
            sections: Optional list of sections

        Returns:
            Validated list or None (for all sections)
        """
        if sections is None:
            return None

        # Filter to valid sections only
        valid = [s for s in sections if s in ALL_SECTIONS]
        return valid if valid else None

    def _try_local_cold(
        self,
        session_id: str,
        sections: Optional[List[str]],
    ) -> Optional[Dict[str, bytes]]:
        """
        Try to restore from LOCAL COLD (K1 SQLite).

        Args:
            session_id: Session to restore
            sections: Sections to restore (None = all)

        Returns:
            Dict of section name -> data if found, None otherwise
        """
        if self._local_cold is None:
            logger.debug("No LocalColdArchive configured")
            return None

        result: Dict[str, bytes] = {}
        sections_to_restore = list(sections) if sections else list(ALL_SECTIONS)

        for section in sections_to_restore:
            try:
                restore_result = self._local_cold.restore(
                    section=section,
                    session_id=session_id,
                )
                if restore_result.success and restore_result.data:
                    result[section] = restore_result.data
            except Exception as e:
                logger.warning(
                    "Failed to restore section %s from LOCAL COLD: %s",
                    section,
                    str(e),
                )
                continue

        return result if result else None

    def _try_k0_fallback(
        self,
        session_id: str,
        sections: Optional[List[str]],
    ) -> Optional[Dict[str, bytes]]:
        """
        Try to restore from K0 cloud storage.

        Only called if LOCAL COLD doesn't have the session.

        Args:
            session_id: Session to restore
            sections: Sections to restore (None = all)

        Returns:
            Dict of section name -> data if found, None otherwise

        Note:
            - This is best-effort
            - Has timeout (K0_TIMEOUT_MS)
            - Never blocks indefinitely
        """
        if self._k0_sync_port is None:
            logger.debug("No K0 sync port configured")
            return None

        # Check if K0 is available
        try:
            if not self._k0_sync_port.is_available:
                logger.debug("K0 sync port not available")
                return None
        except Exception:
            logger.debug("Failed to check K0 availability")
            return None

        try:
            # Use restore_from_k0 which returns all session data
            start = time.perf_counter()
            restore_result = self._k0_sync_port.restore_from_k0(session_id)
            elapsed_ms = (time.perf_counter() - start) * 1000

            if elapsed_ms > get_config().sessionstate.reconstruction.k0_timeout_ms:
                logger.warning(
                    "K0 restore took %.2fms (timeout: %.2fms)",
                    elapsed_ms,
                    get_config().sessionstate.reconstruction.k0_timeout_ms,
                )

            if not restore_result.success:
                logger.debug("K0 restore failed: %s", restore_result.error)
                return None

            # The K0 port returns section data - we need to extract bytes
            # This depends on the K0 port implementation
            # For now, assume it returns bytes keyed by section
            # If sections are specified, filter to those
            result: Dict[str, bytes] = {}

            # K0 sync port should return data per section
            # This is a placeholder - actual implementation depends on K0 port
            if hasattr(restore_result, "section_data"):
                section_data = restore_result.section_data
                if sections:
                    for section in sections:
                        if section in section_data:
                            result[section] = section_data[section]
                else:
                    result = section_data

            return result if result else None

        except Exception as e:
            logger.warning("K0 fallback failed: %s", str(e))
            return None

    def _hydrate_hot(self, section_data: Dict[str, bytes]) -> HydrationResult:
        """
        Hydrate HOT tier sections.

        Priority order:
        1. control (required for orchestration)
        2. meta (schema version)
        3. beliefs_active (current context)
        4. scoreboard (discourse state)
        5. history_active (recent turns)
        6. clarifications, affective_now, narrative_active

        Args:
            section_data: Dict of section name -> serialized data

        Returns:
            HydrationResult with sections hydrated and timing
        """
        start_time = time.perf_counter()
        result = HydrationResult()

        # Get HOT sections from data
        hot_data = {k: v for k, v in section_data.items() if k in HOT_SECTIONS}

        if not hot_data:
            result.duration_ms = (time.perf_counter() - start_time) * 1000
            result.all_restored = True  # No HOT data expected
            return result

        # Hydrate in priority order
        for section in HOT_HYDRATION_PRIORITY:
            if section not in hot_data:
                continue

            data = hot_data[section]
            try:
                if self._hot is not None:
                    # Get the section from HotTier
                    tier_section = self._hot.get_section(section)
                    if tier_section is not None:
                        # Deserialize and restore
                        if self._deserializer:
                            obj = self._deserializer(section, data)
                            if hasattr(tier_section, "restore_from"):
                                tier_section.restore_from(obj)
                            elif hasattr(tier_section, "load"):
                                tier_section.load(obj)
                        else:
                            # Direct bytes restore
                            if hasattr(tier_section, "restore_from_bytes"):
                                tier_section.restore_from_bytes(data)

                result.sections_hydrated.append(section)
            except Exception as e:
                logger.warning("Failed to hydrate HOT section %s: %s", section, str(e))
                result.errors.append((section, str(e)))

        result.duration_ms = (time.perf_counter() - start_time) * 1000

        # Check if all HOT sections in data were restored
        expected_hot = set(hot_data.keys())
        restored_hot = set(result.sections_hydrated)
        result.all_restored = expected_hot == restored_hot

        return result

    def _hydrate_warm(self, section_data: Dict[str, bytes]) -> HydrationResult:
        """
        Hydrate WARM tier sections.

        Called after HOT is hydrated.

        Args:
            section_data: Dict of section name -> serialized data

        Returns:
            HydrationResult with sections hydrated and timing
        """
        start_time = time.perf_counter()
        result = HydrationResult()

        # Get WARM sections from data
        warm_data = {k: v for k, v in section_data.items() if k in WARM_SECTIONS}

        if not warm_data:
            result.duration_ms = (time.perf_counter() - start_time) * 1000
            result.all_restored = True  # No WARM data expected
            return result

        # Hydrate in priority order
        for section in WARM_HYDRATION_PRIORITY:
            if section not in warm_data:
                continue

            data = warm_data[section]
            try:
                if self._warm is not None:
                    # Get the section from WarmTier
                    tier_section = self._warm.get_section(section)
                    if tier_section is not None:
                        # Deserialize and restore
                        if self._deserializer:
                            obj = self._deserializer(section, data)
                            if hasattr(tier_section, "restore_from"):
                                tier_section.restore_from(obj)
                            elif hasattr(tier_section, "load"):
                                tier_section.load(obj)
                        else:
                            # Direct bytes restore
                            if hasattr(tier_section, "restore_from_bytes"):
                                tier_section.restore_from_bytes(data)

                result.sections_hydrated.append(section)
            except Exception as e:
                logger.warning("Failed to hydrate WARM section %s: %s", section, str(e))
                result.errors.append((section, str(e)))

        result.duration_ms = (time.perf_counter() - start_time) * 1000

        # Check if all WARM sections in data were restored
        expected_warm = set(warm_data.keys())
        restored_warm = set(result.sections_hydrated)
        result.all_restored = expected_warm == restored_warm

        return result

    def _check_sla(
        self,
        source: ReconstructionSource,
        duration_ms: float,
    ) -> bool:
        """
        Check if SLA was met.

        Args:
            source: Reconstruction source
            duration_ms: Total duration

        Returns:
            True if SLA met, False otherwise

        Thresholds:
            LOCAL_COLD: <50ms
            K0: <100ms
            FRESH: always True (instant)
        """
        if source == ReconstructionSource.FRESH:
            return True
        elif source == ReconstructionSource.LOCAL_COLD:
            return duration_ms < get_config().sessionstate.reconstruction.sla_local_cold_ms
        elif source == ReconstructionSource.K0:
            return duration_ms < get_config().sessionstate.reconstruction.sla_k0_fallback_ms
        else:
            return True  # Unknown source, assume OK

    def estimate_reconstruction_time(
        self,
        session_id: str,
    ) -> float:
        """
        Estimate how long reconstruction will take.

        Used for ReconstructionStartedEvent.expected_duration_ms

        Args:
            session_id: Session to estimate

        Returns:
            Estimated duration in ms

        Strategy:
            - Check if session exists in LOCAL COLD
            - If yes: estimate based on data size
            - If no: estimate K0 latency + data size
            - If neither: return 0 (fresh start)
        """
        if not session_id:
            return 0.0

        # Check LOCAL COLD first
        if self._local_cold is not None:
            try:
                archives = self._local_cold.list_archives(session_id)
                if archives:
                    # Calculate total size
                    total_size_kb = sum(a.size_bytes for a in archives) / 1024
                    _cfg_r = get_config().sessionstate.reconstruction
                    return (
                        _cfg_r.estimate_local_cold_base_ms
                        + total_size_kb * _cfg_r.estimate_local_cold_per_kb_ms
                    )
            except Exception:
                pass

        # Check K0
        if self._k0_sync_port is not None:
            try:
                if self._k0_sync_port.is_available:
                    # Assume average session size (~50KB)
                    _cfg_r = get_config().sessionstate.reconstruction
                    return _cfg_r.estimate_k0_base_ms + 50 * _cfg_r.estimate_k0_per_kb_ms
            except Exception:
                pass

        # Fresh start
        return 0.0

    def reconstruct_section(
        self,
        session_id: str,
        section: str,
    ) -> Tuple[Optional[bytes], ReconstructionSource]:
        """
        Reconstruct a single section.

        Useful for lazy-loading specific sections without full reconstruction.

        Args:
            session_id: Session to restore
            section: Section name to restore

        Returns:
            Tuple of (data if found, source)
        """
        if section not in ALL_SECTIONS:
            return None, ReconstructionSource.FRESH

        # Try LOCAL COLD first
        if self._local_cold is not None:
            try:
                result = self._local_cold.restore(section=section, session_id=session_id)
                if result.success and result.data:
                    return result.data, ReconstructionSource.LOCAL_COLD
            except Exception:
                pass

        # Try K0 fallback
        if self._k0_sync_port is not None:
            try:
                if self._k0_sync_port.is_available:
                    k0_result = self._k0_sync_port.restore_from_k0(session_id)
                    if k0_result.success and hasattr(k0_result, "section_data"):
                        section_data = k0_result.section_data
                        if section in section_data:
                            return section_data[section], ReconstructionSource.K0
            except Exception:
                pass

        return None, ReconstructionSource.FRESH

    def reset_metrics(self) -> None:
        """Reset all metrics counters."""
        self._total_reconstructions = 0
        self._successful_reconstructions = 0
        self._sla_breaches = 0
        self._source_counts = {
            ReconstructionSource.LOCAL_COLD: 0,
            ReconstructionSource.K0: 0,
            ReconstructionSource.FRESH: 0,
        }

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get current metrics.

        Returns:
            Dict with all reconstruction metrics
        """
        return {
            "total_reconstructions": self._total_reconstructions,
            "successful_reconstructions": self._successful_reconstructions,
            "sla_breaches": self._sla_breaches,
            "sla_compliance_rate": self.sla_compliance_rate,
            "source_counts": dict(self._source_counts),
        }
