"""
MetaSection - Session Metadata (HOT CORE)
==========================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.2 Implement HOT CORE Sections
ISSUE: 2.2.8 (meta)

This section contains session identifiers, lifecycle tracking, and memory
usage information. It is NEVER EVICTED as it contains the session identity.

FlatBuffer Schema: k1/contracts/flatbuffers/sessionstate/meta_section.fbs
Generated Bindings: k1/sessionstate/generated/flatbuffers/K1/SessionState/

Schema Contents:
- header: SectionHeader
- identity: SessionIdentity (session_id, user_id, device_id, privacy_band)
- lifecycle: SessionLifecycle (created_at, last_activity, turn_count, etc.)
- memory: MemoryUsage (per-section sizes, budget enforcement)
- version: VersionInfo (schema versioning for migrations)
- Quick access fields: session_id, user_id, privacy_band, turn_count, is_active
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Dict, Optional

import flatbuffers

# Generated FlatBuffer types
from k1.sessionstate.generated.flatbuffers.K1.SessionState import MetaSection as FBMetaSection
from k1.sessionstate.generated.flatbuffers.K1.SessionState.MemoryUsage import (
    MemoryUsageAddColdReferences,
    MemoryUsageAddEvictionCount,
    MemoryUsageAddHotAffectiveNow,
    MemoryUsageAddHotBeliefsActive,
    MemoryUsageAddHotBudget,
    MemoryUsageAddHotClarifications,
    MemoryUsageAddHotControl,
    MemoryUsageAddHotHistoryActive,
    MemoryUsageAddHotMeta,
    MemoryUsageAddHotNarrativeActive,
    MemoryUsageAddHotScoreboard,
    MemoryUsageAddHotTotal,
    MemoryUsageAddIsOverBudget,
    MemoryUsageAddPressureLevel,
    MemoryUsageAddRemoteReferences,
    MemoryUsageAddSessionTotal,
    MemoryUsageAddTotalBudget,
    MemoryUsageAddWarmBeliefsHistory,
    MemoryUsageAddWarmBudget,
    MemoryUsageAddWarmHistoryRecent,
    MemoryUsageAddWarmPersona,
    MemoryUsageAddWarmTelemetry,
    MemoryUsageAddWarmTotal,
    MemoryUsageEnd,
    MemoryUsageStart,
)
from k1.sessionstate.generated.flatbuffers.K1.SessionState.MetaSection import (
    MetaSectionAddHeader,
    MetaSectionAddIdentity,
    MetaSectionAddIsActive,
    MetaSectionAddLifecycle,
    MetaSectionAddMemory,
    MetaSectionAddPrivacyBand,
    MetaSectionAddSessionId,
    MetaSectionAddTurnCount,
    MetaSectionAddUserId,
    MetaSectionAddVersion,
    MetaSectionEnd,
    MetaSectionStart,
)
from k1.sessionstate.generated.flatbuffers.K1.SessionState.SectionHeader import (
    SectionHeaderAddLastUpdatedMs,
    SectionHeaderAddSectionName,
    SectionHeaderAddSizeBytes,
    SectionHeaderEnd,
    SectionHeaderStart,
)
from k1.sessionstate.generated.flatbuffers.K1.SessionState.SessionIdentity import (
    SessionIdentityAddDeviceId,
    SessionIdentityAddIsAnonymous,
    SessionIdentityAddIsDemoMode,
    SessionIdentityAddPrivacyBand,
    SessionIdentityAddSessionId,
    SessionIdentityAddUserId,
    SessionIdentityEnd,
    SessionIdentityStart,
)
from k1.sessionstate.generated.flatbuffers.K1.SessionState.SessionLifecycle import (
    SessionLifecycleAddIdleTimeoutMs,
    SessionLifecycleAddIsActive,
    SessionLifecycleAddIsExpired,
    SessionLifecycleAddLastTurnId,
    SessionLifecycleAddMaxLifetimeMs,
    SessionLifecycleAddTurnCount,
    SessionLifecycleEnd,
    SessionLifecycleStart,
)
from k1.sessionstate.generated.flatbuffers.K1.SessionState.VersionInfo import (
    VersionInfoAddFeatures,
    VersionInfoAddFormat,
    VersionInfoAddMinCompatibleVersion,
    VersionInfoAddStateVersion,
    VersionInfoEnd,
    VersionInfoStart,
)

# =============================================================================
# Enums (matching FlatBuffer schema)
# =============================================================================


class PrivacyBand(IntEnum):
    """Privacy classification bands (matches common.fbs)."""

    GREEN = 0  # Public, shareable
    AMBER = 1  # Internal, limited sharing (default)
    RED = 2  # Sensitive, strict access
    BLACK = 3  # Top secret, no sharing


class PressureLevel(IntEnum):
    """Memory pressure levels (matches common.fbs)."""

    NORMAL = 0  # <60% utilization
    ELEVATED = 1  # 60-80% utilization
    HIGH = 2  # 80-90% utilization
    CRITICAL = 3  # >90% utilization


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class SessionIdentity:
    """
    Session identification and ownership.

    Contains the core identifiers for a session that establish
    ownership, origin, and privacy classification.
    """

    session_id: str = ""
    user_id: str = ""
    device_id: str = ""
    privacy_band: PrivacyBand = PrivacyBand.AMBER
    is_anonymous: bool = False
    is_demo_mode: bool = False

    def __post_init__(self) -> None:
        """Generate session_id if not provided."""
        if not self.session_id:
            self.session_id = str(uuid.uuid4())

    def is_elevated_privacy(self) -> bool:
        """Check if privacy is above AMBER (RED or BLACK)."""
        return self.privacy_band >= PrivacyBand.RED

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "device_id": self.device_id,
            "privacy_band": self.privacy_band.name,
            "is_anonymous": self.is_anonymous,
            "is_demo_mode": self.is_demo_mode,
        }


@dataclass
class SessionLifecycle:
    """
    Session lifecycle tracking.

    Tracks session creation, activity, expiration, and turn counting.
    """

    created_at_ms: int = 0
    last_activity_ms: int = 0
    expires_at_ms: int = 0
    turn_count: int = 0
    last_turn_id: str = ""
    is_active: bool = True
    is_expired: bool = False
    idle_timeout_ms: int = 3600000  # 1 hour default
    max_lifetime_ms: int = 86400000  # 24 hours default

    def __post_init__(self) -> None:
        """Initialize timestamps if not provided."""
        now_ms = int(time.time() * 1000)
        if self.created_at_ms == 0:
            self.created_at_ms = now_ms
        if self.last_activity_ms == 0:
            self.last_activity_ms = now_ms
        if self.expires_at_ms == 0:
            self.expires_at_ms = now_ms + self.max_lifetime_ms

    def record_activity(self, turn_id: str = "") -> None:
        """Record activity, updating timestamps."""
        now_ms = int(time.time() * 1000)
        self.last_activity_ms = now_ms
        self.turn_count += 1
        if turn_id:
            self.last_turn_id = turn_id

    def check_expiration(self) -> bool:
        """
        Check if session has expired.

        Returns:
            bool: True if expired (updates is_expired flag)
        """
        now_ms = int(time.time() * 1000)

        # Check idle timeout
        idle_expired = (now_ms - self.last_activity_ms) > self.idle_timeout_ms

        # Check max lifetime
        lifetime_expired = now_ms > self.expires_at_ms

        # Check absolute expiration
        absolute_expired = (now_ms - self.created_at_ms) > self.max_lifetime_ms

        if idle_expired or lifetime_expired or absolute_expired:
            self.is_expired = True
            self.is_active = False

        return self.is_expired

    def get_age_ms(self) -> int:
        """Get session age in milliseconds."""
        now_ms = int(time.time() * 1000)
        return now_ms - self.created_at_ms

    def get_idle_ms(self) -> int:
        """Get idle time in milliseconds since last activity."""
        now_ms = int(time.time() * 1000)
        return now_ms - self.last_activity_ms

    def get_remaining_lifetime_ms(self) -> int:
        """Get remaining lifetime before max expiration."""
        now_ms = int(time.time() * 1000)
        return max(0, self.expires_at_ms - now_ms)

    def deactivate(self) -> None:
        """Deactivate the session."""
        self.is_active = False

    def reactivate(self) -> None:
        """Reactivate the session if not expired."""
        if not self.is_expired:
            self.is_active = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "created_at_ms": self.created_at_ms,
            "last_activity_ms": self.last_activity_ms,
            "expires_at_ms": self.expires_at_ms,
            "turn_count": self.turn_count,
            "last_turn_id": self.last_turn_id,
            "is_active": self.is_active,
            "is_expired": self.is_expired,
            "idle_timeout_ms": self.idle_timeout_ms,
            "max_lifetime_ms": self.max_lifetime_ms,
            "age_ms": self.get_age_ms(),
            "idle_ms": self.get_idle_ms(),
        }


@dataclass
class MemoryUsage:
    """
    Memory usage tracking for budget enforcement.

    Tracks per-section sizes in both HOT and WARM tiers,
    plus budget enforcement fields.
    """

    # HOT core sizes (bytes)
    hot_control: int = 0
    hot_beliefs_active: int = 0
    hot_scoreboard: int = 0
    hot_history_active: int = 0
    hot_clarifications: int = 0
    hot_affective_now: int = 0
    hot_narrative_active: int = 0
    hot_meta: int = 0

    # WARM tier sizes (bytes)
    warm_beliefs_history: int = 0
    warm_history_recent: int = 0
    warm_persona: int = 0
    warm_telemetry: int = 0

    # Reference counts
    cold_references: int = 0
    remote_references: int = 0

    # Budget configuration
    hot_budget: int = 49152  # 48KB
    warm_budget: int = 49152  # 48KB
    total_budget: int = 98304  # 96KB

    # Eviction tracking
    last_eviction_ms: int = 0
    eviction_count: int = 0

    @property
    def hot_total(self) -> int:
        """Calculate total HOT tier size."""
        return (
            self.hot_control
            + self.hot_beliefs_active
            + self.hot_scoreboard
            + self.hot_history_active
            + self.hot_clarifications
            + self.hot_affective_now
            + self.hot_narrative_active
            + self.hot_meta
        )

    @property
    def warm_total(self) -> int:
        """Calculate total WARM tier size."""
        return (
            self.warm_beliefs_history
            + self.warm_history_recent
            + self.warm_persona
            + self.warm_telemetry
        )

    @property
    def session_total(self) -> int:
        """Calculate total session size (HOT + WARM)."""
        return self.hot_total + self.warm_total

    @property
    def is_over_budget(self) -> bool:
        """Check if any tier is over budget."""
        return self.hot_total > self.hot_budget or self.warm_total > self.warm_budget

    @property
    def pressure_level(self) -> PressureLevel:
        """Calculate memory pressure level based on utilization."""
        hot_util = self.hot_total / self.hot_budget if self.hot_budget > 0 else 0
        warm_util = self.warm_total / self.warm_budget if self.warm_budget > 0 else 0
        max_util = max(hot_util, warm_util)

        if max_util >= 0.9:
            return PressureLevel.CRITICAL
        elif max_util >= 0.8:
            return PressureLevel.HIGH
        elif max_util >= 0.6:
            return PressureLevel.ELEVATED
        return PressureLevel.NORMAL

    def get_hot_utilization(self) -> float:
        """Get HOT tier utilization (0.0 to 1.0+)."""
        return self.hot_total / self.hot_budget if self.hot_budget > 0 else 0

    def get_warm_utilization(self) -> float:
        """Get WARM tier utilization (0.0 to 1.0+)."""
        return self.warm_total / self.warm_budget if self.warm_budget > 0 else 0

    def get_total_utilization(self) -> float:
        """Get total session utilization (0.0 to 1.0+)."""
        return self.session_total / self.total_budget if self.total_budget > 0 else 0

    def update_hot_section(self, section: str, size_bytes: int) -> None:
        """Update a HOT section's size."""
        attr_name = f"hot_{section}"
        if hasattr(self, attr_name):
            setattr(self, attr_name, size_bytes)

    def update_warm_section(self, section: str, size_bytes: int) -> None:
        """Update a WARM section's size."""
        attr_name = f"warm_{section}"
        if hasattr(self, attr_name):
            setattr(self, attr_name, size_bytes)

    def record_eviction(self) -> None:
        """Record an eviction event."""
        self.last_eviction_ms = int(time.time() * 1000)
        self.eviction_count += 1

    def get_section_sizes(self) -> Dict[str, int]:
        """Get all section sizes as a dictionary."""
        return {
            "hot_control": self.hot_control,
            "hot_beliefs_active": self.hot_beliefs_active,
            "hot_scoreboard": self.hot_scoreboard,
            "hot_history_active": self.hot_history_active,
            "hot_clarifications": self.hot_clarifications,
            "hot_affective_now": self.hot_affective_now,
            "hot_narrative_active": self.hot_narrative_active,
            "hot_meta": self.hot_meta,
            "warm_beliefs_history": self.warm_beliefs_history,
            "warm_history_recent": self.warm_history_recent,
            "warm_persona": self.warm_persona,
            "warm_telemetry": self.warm_telemetry,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            **self.get_section_sizes(),
            "hot_total": self.hot_total,
            "warm_total": self.warm_total,
            "session_total": self.session_total,
            "cold_references": self.cold_references,
            "remote_references": self.remote_references,
            "hot_budget": self.hot_budget,
            "warm_budget": self.warm_budget,
            "total_budget": self.total_budget,
            "is_over_budget": self.is_over_budget,
            "pressure_level": self.pressure_level.name,
            "hot_utilization": self.get_hot_utilization(),
            "warm_utilization": self.get_warm_utilization(),
            "last_eviction_ms": self.last_eviction_ms,
            "eviction_count": self.eviction_count,
        }


@dataclass
class VersionInfo:
    """
    Version tracking for forward/backward compatibility.

    Used for schema migrations and compatibility checking.
    """

    state_version: int = 1  # Session state format version
    min_compatible_version: int = 1  # Minimum compatible version
    format: str = "flatbuffers"  # Serialization format
    features: int = 0  # Feature flags bitmask
    schema_major: int = 1
    schema_minor: int = 0
    schema_patch: int = 0

    def is_compatible(self, other_version: int) -> bool:
        """Check if compatible with another version."""
        return other_version >= self.min_compatible_version

    def get_schema_string(self) -> str:
        """Get schema version as string (e.g., '1.0.0')."""
        return f"{self.schema_major}.{self.schema_minor}.{self.schema_patch}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "state_version": self.state_version,
            "min_compatible_version": self.min_compatible_version,
            "format": self.format,
            "features": self.features,
            "schema": self.get_schema_string(),
        }


# =============================================================================
# MetaSection Implementation
# =============================================================================


class MetaSection:
    """
    Meta Section - Session Metadata (NEVER EVICT).

    Contains session identifiers, lifecycle tracking, and memory usage.
    This section is NEVER evicted because it contains the session identity.

    Budget: 2KB (2048 bytes)
    Tier: HOT CORE
    Eviction: NEVER

    Components:
        - identity: SessionIdentity (session_id, user_id, device_id, privacy_band)
        - lifecycle: SessionLifecycle (created_at, activity, turns, expiration)
        - memory: MemoryUsage (per-section sizes, budget tracking)
        - version: VersionInfo (schema versioning)

    Example:
        section = MetaSection(
            session_id="sess-123",
            user_id="user-456",
        )

        # Record turn activity
        section.record_turn("turn-789")

        # Update memory sizes
        section.update_section_size("control", 1024)

        # Check session health
        if section.is_expired():
            handle_expired_session()

        # Serialize for persistence
        data = section.to_flatbuffer()
    """

    BUDGET_BYTES = 2048  # 2KB
    TIER = "hot"
    CAN_EVICT = False
    SECTION_NAME = "meta"
    SCHEMA_VERSION = "1.0.0"

    def __init__(
        self,
        session_id: str = "",
        user_id: str = "",
        device_id: str = "",
        privacy_band: PrivacyBand = PrivacyBand.AMBER,
        is_anonymous: bool = False,
        is_demo_mode: bool = False,
    ) -> None:
        """
        Initialize MetaSection.

        Args:
            session_id: Session UUID (generated if empty)
            user_id: User identifier
            device_id: Device identifier
            privacy_band: Privacy classification
            is_anonymous: Whether session is anonymous
            is_demo_mode: Whether session is in demo mode
        """
        now_ms = int(time.time() * 1000)

        # Identity
        self._identity = SessionIdentity(
            session_id=session_id or str(uuid.uuid4()),
            user_id=user_id,
            device_id=device_id,
            privacy_band=privacy_band,
            is_anonymous=is_anonymous,
            is_demo_mode=is_demo_mode,
        )

        # Lifecycle
        self._lifecycle = SessionLifecycle(
            created_at_ms=now_ms,
            last_activity_ms=now_ms,
        )

        # Memory tracking
        self._memory = MemoryUsage()

        # Version info
        self._version = VersionInfo()

        # Internal tracking
        self._created_at_ms = now_ms
        self._last_updated_ms = now_ms

        # Integrity hash
        self._integrity_hash = ""

        # Cached serialization
        self._cached_bytes: Optional[bytes] = None
        self._cache_valid = False

    # =========================================================================
    # ISection Protocol Implementation
    # =========================================================================

    @property
    def name(self) -> str:
        """Section identifier name."""
        return self.SECTION_NAME

    @property
    def tier(self) -> str:
        """Section tier (hot, warm, cold)."""
        return self.TIER

    @property
    def budget_bytes(self) -> int:
        """Maximum size budget in bytes."""
        return self.BUDGET_BYTES

    @property
    def can_evict(self) -> bool:
        """Whether section can be evicted. Always False for MetaSection."""
        return self.CAN_EVICT

    def get_size_bytes(self) -> int:
        """
        Get current serialized size in bytes.

        Uses cached value if available.
        """
        if self._cache_valid and self._cached_bytes:
            return len(self._cached_bytes)

        # Estimate size without full serialization
        size = 0

        # Header overhead (~50 bytes)
        size += 50

        # Identity (~150 bytes)
        size += 150

        # Lifecycle (~80 bytes)
        size += 80

        # Memory usage (~200 bytes)
        size += 200

        # Version info (~30 bytes)
        size += 30

        # Quick access fields (~100 bytes)
        size += 100

        return size

    def to_flatbuffer(self) -> bytes:
        """
        Serialize section to FlatBuffer bytes.

        Returns:
            bytes: FlatBuffer-encoded data

        Performance Target: <100 microseconds
        """
        if self._cache_valid and self._cached_bytes:
            return self._cached_bytes

        builder = flatbuffers.Builder(self.BUDGET_BYTES)

        # 1. Build SessionIdentity
        session_id_offset = builder.CreateString(self._identity.session_id)
        user_id_offset = builder.CreateString(self._identity.user_id)
        device_id_offset = builder.CreateString(self._identity.device_id)

        SessionIdentityStart(builder)
        SessionIdentityAddSessionId(builder, session_id_offset)
        SessionIdentityAddUserId(builder, user_id_offset)
        SessionIdentityAddDeviceId(builder, device_id_offset)
        SessionIdentityAddPrivacyBand(builder, int(self._identity.privacy_band))
        SessionIdentityAddIsAnonymous(builder, self._identity.is_anonymous)
        SessionIdentityAddIsDemoMode(builder, self._identity.is_demo_mode)
        identity_offset = SessionIdentityEnd(builder)

        # 2. Build SessionLifecycle
        last_turn_id_offset = builder.CreateString(self._lifecycle.last_turn_id)

        SessionLifecycleStart(builder)
        # Note: Timestamp structs need special handling - skip for now, use scalar fields
        SessionLifecycleAddTurnCount(builder, self._lifecycle.turn_count)
        SessionLifecycleAddLastTurnId(builder, last_turn_id_offset)
        SessionLifecycleAddIsActive(builder, self._lifecycle.is_active)
        SessionLifecycleAddIsExpired(builder, self._lifecycle.is_expired)
        SessionLifecycleAddIdleTimeoutMs(builder, self._lifecycle.idle_timeout_ms)
        SessionLifecycleAddMaxLifetimeMs(builder, self._lifecycle.max_lifetime_ms)
        lifecycle_offset = SessionLifecycleEnd(builder)

        # 3. Build MemoryUsage
        MemoryUsageStart(builder)
        MemoryUsageAddHotControl(builder, self._memory.hot_control)
        MemoryUsageAddHotBeliefsActive(builder, self._memory.hot_beliefs_active)
        MemoryUsageAddHotScoreboard(builder, self._memory.hot_scoreboard)
        MemoryUsageAddHotHistoryActive(builder, self._memory.hot_history_active)
        MemoryUsageAddHotClarifications(builder, self._memory.hot_clarifications)
        MemoryUsageAddHotAffectiveNow(builder, self._memory.hot_affective_now)
        MemoryUsageAddHotNarrativeActive(builder, self._memory.hot_narrative_active)
        MemoryUsageAddHotMeta(builder, self._memory.hot_meta)
        MemoryUsageAddHotTotal(builder, self._memory.hot_total)
        MemoryUsageAddWarmBeliefsHistory(builder, self._memory.warm_beliefs_history)
        MemoryUsageAddWarmHistoryRecent(builder, self._memory.warm_history_recent)
        MemoryUsageAddWarmPersona(builder, self._memory.warm_persona)
        MemoryUsageAddWarmTelemetry(builder, self._memory.warm_telemetry)
        MemoryUsageAddWarmTotal(builder, self._memory.warm_total)
        MemoryUsageAddSessionTotal(builder, self._memory.session_total)
        MemoryUsageAddColdReferences(builder, self._memory.cold_references)
        MemoryUsageAddRemoteReferences(builder, self._memory.remote_references)
        MemoryUsageAddHotBudget(builder, self._memory.hot_budget)
        MemoryUsageAddWarmBudget(builder, self._memory.warm_budget)
        MemoryUsageAddTotalBudget(builder, self._memory.total_budget)
        MemoryUsageAddIsOverBudget(builder, self._memory.is_over_budget)
        MemoryUsageAddPressureLevel(builder, int(self._memory.pressure_level))
        MemoryUsageAddEvictionCount(builder, self._memory.eviction_count)
        memory_offset = MemoryUsageEnd(builder)

        # 4. Build VersionInfo
        format_offset = builder.CreateString(self._version.format)

        VersionInfoStart(builder)
        VersionInfoAddStateVersion(builder, self._version.state_version)
        VersionInfoAddMinCompatibleVersion(builder, self._version.min_compatible_version)
        VersionInfoAddFormat(builder, format_offset)
        VersionInfoAddFeatures(builder, self._version.features)
        version_offset = VersionInfoEnd(builder)

        # 5. Build Header
        section_name_offset = builder.CreateString(self.SECTION_NAME)

        SectionHeaderStart(builder)
        SectionHeaderAddSectionName(builder, section_name_offset)
        SectionHeaderAddSizeBytes(builder, self.get_size_bytes())
        SectionHeaderAddLastUpdatedMs(builder, self._last_updated_ms)
        header_offset = SectionHeaderEnd(builder)

        # 6. Build quick access strings
        quick_session_id = builder.CreateString(self._identity.session_id)
        quick_user_id = builder.CreateString(self._identity.user_id)

        # 7. Build MetaSection root
        MetaSectionStart(builder)
        MetaSectionAddHeader(builder, header_offset)
        MetaSectionAddIdentity(builder, identity_offset)
        MetaSectionAddLifecycle(builder, lifecycle_offset)
        MetaSectionAddMemory(builder, memory_offset)
        MetaSectionAddVersion(builder, version_offset)
        MetaSectionAddSessionId(builder, quick_session_id)
        MetaSectionAddUserId(builder, quick_user_id)
        MetaSectionAddPrivacyBand(builder, int(self._identity.privacy_band))
        MetaSectionAddTurnCount(builder, self._lifecycle.turn_count)
        MetaSectionAddIsActive(builder, self._lifecycle.is_active)
        meta_section = MetaSectionEnd(builder)

        builder.Finish(meta_section)
        self._cached_bytes = bytes(builder.Output())
        self._cache_valid = True

        return self._cached_bytes

    def from_flatbuffer(self, data: bytes) -> None:
        """
        Deserialize section from FlatBuffer bytes.

        Args:
            data: FlatBuffer-encoded data
        """
        fb = FBMetaSection.GetRootAsMetaSection(data, 0)

        # Restore identity
        identity = fb.Identity()
        if identity:
            self._identity.session_id = (
                identity.SessionId().decode("utf-8") if identity.SessionId() else ""
            )
            self._identity.user_id = identity.UserId().decode("utf-8") if identity.UserId() else ""
            self._identity.device_id = (
                identity.DeviceId().decode("utf-8") if identity.DeviceId() else ""
            )
            self._identity.privacy_band = PrivacyBand(identity.PrivacyBand())
            self._identity.is_anonymous = identity.IsAnonymous()
            self._identity.is_demo_mode = identity.IsDemoMode()

        # Restore lifecycle
        lifecycle = fb.Lifecycle()
        if lifecycle:
            self._lifecycle.turn_count = lifecycle.TurnCount()
            self._lifecycle.last_turn_id = (
                lifecycle.LastTurnId().decode("utf-8") if lifecycle.LastTurnId() else ""
            )
            self._lifecycle.is_active = lifecycle.IsActive()
            self._lifecycle.is_expired = lifecycle.IsExpired()
            self._lifecycle.idle_timeout_ms = lifecycle.IdleTimeoutMs()
            self._lifecycle.max_lifetime_ms = lifecycle.MaxLifetimeMs()

        # Restore memory
        memory = fb.Memory()
        if memory:
            self._memory.hot_control = memory.HotControl()
            self._memory.hot_beliefs_active = memory.HotBeliefsActive()
            self._memory.hot_scoreboard = memory.HotScoreboard()
            self._memory.hot_history_active = memory.HotHistoryActive()
            self._memory.hot_clarifications = memory.HotClarifications()
            self._memory.hot_affective_now = memory.HotAffectiveNow()
            self._memory.hot_narrative_active = memory.HotNarrativeActive()
            self._memory.hot_meta = memory.HotMeta()
            self._memory.warm_beliefs_history = memory.WarmBeliefsHistory()
            self._memory.warm_history_recent = memory.WarmHistoryRecent()
            self._memory.warm_persona = memory.WarmPersona()
            self._memory.warm_telemetry = memory.WarmTelemetry()
            self._memory.cold_references = memory.ColdReferences()
            self._memory.remote_references = memory.RemoteReferences()
            self._memory.hot_budget = memory.HotBudget()
            self._memory.warm_budget = memory.WarmBudget()
            self._memory.total_budget = memory.TotalBudget()
            self._memory.eviction_count = memory.EvictionCount()

        # Restore version
        version = fb.Version()
        if version:
            self._version.state_version = version.StateVersion()
            self._version.min_compatible_version = version.MinCompatibleVersion()
            self._version.format = (
                version.Format().decode("utf-8") if version.Format() else "flatbuffers"
            )
            self._version.features = version.Features()

        # Update header info
        header = fb.Header()
        if header:
            self._last_updated_ms = header.LastUpdatedMs()

        self._invalidate_cache()

    def clear(self) -> None:
        """Clear all section data, keeping only identity."""
        session_id = self._identity.session_id
        user_id = self._identity.user_id

        now_ms = int(time.time() * 1000)

        self._identity = SessionIdentity(session_id=session_id, user_id=user_id)
        self._lifecycle = SessionLifecycle(created_at_ms=now_ms)
        self._memory = MemoryUsage()
        self._version = VersionInfo()
        self._last_updated_ms = now_ms
        self._integrity_hash = ""
        self._invalidate_cache()

    def get_metadata(self) -> Dict[str, Any]:
        """Get section metadata for telemetry/debugging."""
        return {
            "name": self.SECTION_NAME,
            "tier": self.TIER,
            "budget_bytes": self.BUDGET_BYTES,
            "current_size_bytes": self.get_size_bytes(),
            "can_evict": self.CAN_EVICT,
            "session_id": self._identity.session_id,
            "user_id": self._identity.user_id,
            "turn_count": self._lifecycle.turn_count,
            "is_active": self._lifecycle.is_active,
            "pressure_level": self._memory.pressure_level.name,
            "last_updated_ms": self._last_updated_ms,
        }

    # =========================================================================
    # Identity API
    # =========================================================================

    @property
    def session_id(self) -> str:
        """Get session ID."""
        return self._identity.session_id

    @property
    def user_id(self) -> str:
        """Get user ID."""
        return self._identity.user_id

    @property
    def device_id(self) -> str:
        """Get device ID."""
        return self._identity.device_id

    @property
    def privacy_band(self) -> PrivacyBand:
        """Get privacy band."""
        return self._identity.privacy_band

    @property
    def is_anonymous(self) -> bool:
        """Check if anonymous session."""
        return self._identity.is_anonymous

    @property
    def is_demo_mode(self) -> bool:
        """Check if demo mode."""
        return self._identity.is_demo_mode

    def get_identity(self) -> SessionIdentity:
        """Get session identity."""
        return self._identity

    def set_user_id(self, user_id: str) -> None:
        """Set user ID (for anonymous -> authenticated conversion)."""
        self._identity.user_id = user_id
        self._touch()

    def set_device_id(self, device_id: str) -> None:
        """Set device ID."""
        self._identity.device_id = device_id
        self._touch()

    def set_privacy_band(self, band: PrivacyBand) -> None:
        """Set privacy band."""
        self._identity.privacy_band = band
        self._touch()

    def upgrade_from_anonymous(self, user_id: str) -> None:
        """Upgrade anonymous session to authenticated."""
        if self._identity.is_anonymous:
            self._identity.user_id = user_id
            self._identity.is_anonymous = False
            self._touch()

    # =========================================================================
    # Lifecycle API
    # =========================================================================

    @property
    def turn_count(self) -> int:
        """Get turn count."""
        return self._lifecycle.turn_count

    @property
    def is_active(self) -> bool:
        """Check if session is active."""
        return self._lifecycle.is_active

    @property
    def is_expired(self) -> bool:
        """Check if session has expired."""
        return self._lifecycle.is_expired

    @property
    def created_at_ms(self) -> int:
        """Get creation timestamp."""
        return self._lifecycle.created_at_ms

    @property
    def last_activity_ms(self) -> int:
        """Get last activity timestamp."""
        return self._lifecycle.last_activity_ms

    def get_lifecycle(self) -> SessionLifecycle:
        """Get session lifecycle."""
        return self._lifecycle

    def record_turn(self, turn_id: str = "") -> int:
        """
        Record a turn, updating activity timestamps.

        Args:
            turn_id: Turn identifier

        Returns:
            int: New turn count
        """
        turn_id = turn_id or str(uuid.uuid4())
        self._lifecycle.record_activity(turn_id)
        self._touch()
        return self._lifecycle.turn_count

    def check_expiration(self) -> bool:
        """
        Check if session has expired.

        Returns:
            bool: True if expired
        """
        expired = self._lifecycle.check_expiration()
        if expired:
            self._touch()
        return expired

    def deactivate(self) -> None:
        """Deactivate the session."""
        self._lifecycle.deactivate()
        self._touch()

    def reactivate(self) -> None:
        """Reactivate the session."""
        self._lifecycle.reactivate()
        self._touch()

    def set_idle_timeout(self, timeout_ms: int) -> None:
        """Set idle timeout in milliseconds."""
        self._lifecycle.idle_timeout_ms = timeout_ms
        self._touch()

    def set_max_lifetime(self, lifetime_ms: int) -> None:
        """Set max lifetime in milliseconds."""
        self._lifecycle.max_lifetime_ms = lifetime_ms
        self._lifecycle.expires_at_ms = self._lifecycle.created_at_ms + lifetime_ms
        self._touch()

    def get_age_ms(self) -> int:
        """Get session age in milliseconds."""
        return self._lifecycle.get_age_ms()

    def get_idle_ms(self) -> int:
        """Get idle time in milliseconds."""
        return self._lifecycle.get_idle_ms()

    # =========================================================================
    # Memory API
    # =========================================================================

    def get_memory(self) -> MemoryUsage:
        """Get memory usage."""
        return self._memory

    @property
    def pressure_level(self) -> PressureLevel:
        """Get current pressure level."""
        return self._memory.pressure_level

    @property
    def hot_utilization(self) -> float:
        """Get HOT tier utilization (0.0 to 1.0+)."""
        return self._memory.get_hot_utilization()

    @property
    def warm_utilization(self) -> float:
        """Get WARM tier utilization (0.0 to 1.0+)."""
        return self._memory.get_warm_utilization()

    def update_section_size(self, section: str, size_bytes: int) -> None:
        """
        Update a section's size.

        Args:
            section: Section name (e.g., 'control', 'beliefs_active')
            size_bytes: New size in bytes
        """
        # Determine tier from section name
        hot_sections = [
            "control",
            "beliefs_active",
            "scoreboard",
            "history_active",
            "clarifications",
            "affective_now",
            "narrative_active",
            "meta",
        ]
        warm_sections = ["beliefs_history", "history_recent", "persona", "telemetry"]

        if section in hot_sections:
            self._memory.update_hot_section(section, size_bytes)
        elif section in warm_sections:
            self._memory.update_warm_section(section, size_bytes)

        # Update meta section's own size
        if section == "meta":
            self._memory.hot_meta = size_bytes

        self._touch()

    def update_all_sizes(self, sizes: Dict[str, int]) -> None:
        """
        Update all section sizes at once.

        Args:
            sizes: Dictionary of section name -> size in bytes
        """
        for section, size in sizes.items():
            self.update_section_size(section, size)
        self._touch()

    def record_eviction(self) -> None:
        """Record an eviction event."""
        self._memory.record_eviction()
        self._touch()

    def set_cold_references(self, count: int) -> None:
        """Set LOCAL COLD reference count."""
        self._memory.cold_references = count
        self._touch()

    def set_remote_references(self, count: int) -> None:
        """Set REMOTE COLD reference count."""
        self._memory.remote_references = count
        self._touch()

    # =========================================================================
    # Version API
    # =========================================================================

    def get_version(self) -> VersionInfo:
        """Get version info."""
        return self._version

    def get_schema_version(self) -> str:
        """Get schema version string."""
        return self._version.get_schema_string()

    def is_compatible_version(self, version: int) -> bool:
        """Check if compatible with a given version."""
        return self._version.is_compatible(version)

    def set_features(self, features: int) -> None:
        """Set feature flags."""
        self._version.features = features
        self._touch()

    # =========================================================================
    # Integrity API
    # =========================================================================

    def compute_integrity(self, data: bytes) -> str:
        """
        Compute integrity hash for given data.

        Args:
            data: Data to hash

        Returns:
            str: SHA256 hex digest
        """
        return hashlib.sha256(data).hexdigest()

    def set_integrity(self, hash_value: str) -> None:
        """Set integrity hash."""
        self._integrity_hash = hash_value

    def get_integrity(self) -> str:
        """Get integrity hash."""
        return self._integrity_hash

    def verify_integrity(self, data: bytes) -> bool:
        """
        Verify data integrity.

        Args:
            data: Data to verify

        Returns:
            bool: True if hash matches
        """
        if not self._integrity_hash:
            return True  # No hash set, assume valid
        return self.compute_integrity(data) == self._integrity_hash

    def update_integrity_from_serialized(self) -> str:
        """
        Update integrity hash from current serialized state.

        Returns:
            str: New integrity hash
        """
        data = self.to_flatbuffer()
        self._integrity_hash = self.compute_integrity(data)
        return self._integrity_hash

    # =========================================================================
    # Apply Operations (MutationGuard Pattern)
    # =========================================================================

    def apply(self, operation: str, data: Dict[str, Any]) -> None:
        """
        Apply a mutation operation.

        Args:
            operation: Operation name
            data: Operation data

        Supported operations:
            - set_user_id: {user_id: str}
            - set_device_id: {device_id: str}
            - set_privacy_band: {band: int or str}
            - record_turn: {turn_id: str}
            - update_section_size: {section: str, size_bytes: int}
            - update_all_sizes: {sizes: Dict[str, int]}
            - record_eviction: {}
            - deactivate: {}
            - reactivate: {}
            - upgrade_from_anonymous: {user_id: str}
        """
        if operation == "set_user_id":
            self.set_user_id(data.get("user_id", ""))
        elif operation == "set_device_id":
            self.set_device_id(data.get("device_id", ""))
        elif operation == "set_privacy_band":
            band = data.get("band", PrivacyBand.AMBER)
            if isinstance(band, int):
                band = PrivacyBand(band)
            elif isinstance(band, str):
                band = PrivacyBand[band.upper()]
            self.set_privacy_band(band)
        elif operation == "record_turn":
            self.record_turn(data.get("turn_id", ""))
        elif operation == "update_section_size":
            self.update_section_size(
                data.get("section", ""),
                data.get("size_bytes", 0),
            )
        elif operation == "update_all_sizes":
            self.update_all_sizes(data.get("sizes", {}))
        elif operation == "record_eviction":
            self.record_eviction()
        elif operation == "deactivate":
            self.deactivate()
        elif operation == "reactivate":
            self.reactivate()
        elif operation == "upgrade_from_anonymous":
            self.upgrade_from_anonymous(data.get("user_id", ""))
        elif operation == "set_idle_timeout":
            self.set_idle_timeout(data.get("timeout_ms", 3600000))
        elif operation == "set_max_lifetime":
            self.set_max_lifetime(data.get("lifetime_ms", 86400000))
        elif operation == "set_cold_references":
            self.set_cold_references(data.get("count", 0))
        elif operation == "set_remote_references":
            self.set_remote_references(data.get("count", 0))
        elif operation == "set_features":
            self.set_features(data.get("features", 0))
        elif operation == "clear":
            self.clear()
        else:
            raise ValueError(f"Unknown operation: {operation}")

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def to_dict(self) -> Dict[str, Any]:
        """Convert section to dictionary."""
        return {
            "identity": self._identity.to_dict(),
            "lifecycle": self._lifecycle.to_dict(),
            "memory": self._memory.to_dict(),
            "version": self._version.to_dict(),
            "integrity_hash": self._integrity_hash,
            "last_updated_ms": self._last_updated_ms,
        }

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"MetaSection(session_id={self._identity.session_id!r}, "
            f"user_id={self._identity.user_id!r}, "
            f"turn_count={self._lifecycle.turn_count}, "
            f"is_active={self._lifecycle.is_active})"
        )

    # =========================================================================
    # Internal Methods
    # =========================================================================

    def _touch(self) -> None:
        """Update last modified timestamp and invalidate cache."""
        self._last_updated_ms = int(time.time() * 1000)
        self._invalidate_cache()

    def _invalidate_cache(self) -> None:
        """Invalidate cached serialization."""
        self._cached_bytes = None
        self._cache_valid = False


# =============================================================================
# Factory Function
# =============================================================================


def create_meta_section(
    session_id: str = "",
    user_id: str = "",
    device_id: str = "",
    privacy_band: PrivacyBand = PrivacyBand.AMBER,
    is_anonymous: bool = False,
    is_demo_mode: bool = False,
) -> MetaSection:
    """
    Factory function to create a MetaSection.

    Args:
        session_id: Session UUID (generated if empty)
        user_id: User identifier
        device_id: Device identifier
        privacy_band: Privacy classification
        is_anonymous: Whether session is anonymous
        is_demo_mode: Whether session is in demo mode

    Returns:
        MetaSection: Initialized section
    """
    return MetaSection(
        session_id=session_id,
        user_id=user_id,
        device_id=device_id,
        privacy_band=privacy_band,
        is_anonymous=is_anonymous,
        is_demo_mode=is_demo_mode,
    )
