"""
ControlSection - System Control Block (HOT CORE)
=================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.2 Implement HOT CORE Sections
ISSUE: 2.2.1 (control_block)

This is the NEVER-EVICT control section containing critical orchestration
state. Uses FlatBuffers for <100us serialization.

FlatBuffer Schema: k1/contracts/flatbuffers/sessionstate/control_section.fbs
Generated Bindings: k1/sessionstate/generated/flatbuffers/K1/SessionState/
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

import flatbuffers

# Generated FlatBuffer types
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState import (
    AgentLeaseAddAgentId,
    AgentLeaseAddAgentType,
    AgentLeaseAddCapabilities,
    AgentLeaseAddLeaseExpiresMs,
    AgentLeaseAddLeaseStartedMs,
    AgentLeaseAddPriority,
    AgentLeaseAddState,
    AgentLeaseEnd,
    AgentLeaseStart,
    AgentLeaseStartCapabilitiesVector,
)
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState import (
    ControlSection as FBControlSection,
)
from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState import (
    ControlSectionAddAgentLeases,
    ControlSectionAddDomains,
    ControlSectionAddFlowState,
    ControlSectionAddHeader,
    ControlSectionAddNeverEvict,
    ControlSectionAddSafety,
    ControlSectionAddTurnLock,
    ControlSectionEnd,
    ControlSectionStart,
    ControlSectionStartAgentLeasesVector,
    DomainContextAddActiveDomains,
    DomainContextAddPrimaryDomain,
    DomainContextEnd,
    DomainContextStart,
    DomainContextStartActiveDomainsVector,
    FlowStateAddCompletedAgents,
    FlowStateAddCurrentPhase,
    FlowStateAddPendingAgents,
    FlowStateAddStartedAtMs,
    FlowStateAddTimeoutMs,
    FlowStateAddTurnId,
    FlowStateEnd,
    FlowStateStart,
    FlowStateStartCompletedAgentsVector,
    FlowStateStartPendingAgentsVector,
    SafetyContextAddBand,
    SafetyContextAddBlockedActions,
    SafetyContextAddEscalatedAtMs,
    SafetyContextAddEscalationReason,
    SafetyContextAddRequiresConfirmation,
    SafetyContextEnd,
    SafetyContextStart,
    SafetyContextStartBlockedActionsVector,
    SectionHeaderAddLastUpdatedMs,
    SectionHeaderAddSectionName,
    SectionHeaderAddSizeBytes,
    SectionHeaderEnd,
    SectionHeaderStart,
    TurnLockAddLocked,
    TurnLockAddLockedAtMs,
    TurnLockAddLockHolder,
    TurnLockAddLockTimeoutMs,
    TurnLockAddTurnId,
    TurnLockEnd,
    TurnLockStart,
)

# =============================================================================
# ISection Protocol - Common interface for all sections
# =============================================================================


@runtime_checkable
class ISection(Protocol):
    """
    Protocol for session state sections.

    All sections must implement this interface to work with
    the SizeTracker, EvictionEngine, and other kernel services.
    """

    @property
    def name(self) -> str:
        """Section identifier name."""
        ...

    @property
    def tier(self) -> str:
        """Section tier (hot, warm, cold)."""
        ...

    @property
    def budget_bytes(self) -> int:
        """Maximum size budget in bytes."""
        ...

    @property
    def can_evict(self) -> bool:
        """Whether section can be evicted under memory pressure."""
        ...

    def get_size_bytes(self) -> int:
        """Get current serialized size in bytes."""
        ...

    def to_flatbuffer(self) -> bytes:
        """Serialize section to FlatBuffer bytes."""
        ...

    def from_flatbuffer(self, data: bytes) -> None:
        """Deserialize section from FlatBuffer bytes."""
        ...

    def clear(self) -> None:
        """Clear all section data."""
        ...

    def get_metadata(self) -> Dict[str, Any]:
        """Get section metadata for telemetry/debugging."""
        ...


# =============================================================================
# Enums matching FlatBuffer schema
# =============================================================================


class AgentState(IntEnum):
    """Agent lifecycle states."""

    PENDING = 0
    WARMING = 1
    ACTIVE = 2
    IDLE = 3
    DRAINING = 4
    TERMINATED = 5


class FlowPhase(IntEnum):
    """Orchestration flow phases."""

    IDLE = 0
    NEGOTIATION = 1
    SELECTION = 2
    EXECUTION = 3


class PrivacyBand(IntEnum):
    """Privacy classification bands."""

    GREEN = 0  # Public, shareable
    AMBER = 1  # Internal, limited sharing
    RED = 2  # Sensitive, strict access
    BLACK = 3  # Top secret, no sharing


# =============================================================================
# Data Classes for Domain Objects
# =============================================================================


@dataclass
class AgentLease:
    """
    Agent lease - grants temporary access to orchestration.

    Default TTL: 30 seconds, renewable.
    """

    agent_id: str
    agent_type: str
    state: AgentState = AgentState.PENDING
    lease_started_ms: int = 0
    lease_expires_ms: int = 0
    capabilities: List[str] = field(default_factory=list)
    priority: int = 0

    def is_expired(self, now_ms: Optional[int] = None) -> bool:
        """Check if lease has expired."""
        now_ms = now_ms or int(time.time() * 1000)
        return now_ms > self.lease_expires_ms

    def remaining_ms(self, now_ms: Optional[int] = None) -> int:
        """Get remaining lease time in milliseconds."""
        now_ms = now_ms or int(time.time() * 1000)
        return max(0, self.lease_expires_ms - now_ms)


@dataclass
class FlowState:
    """Current orchestration phase and turn context."""

    current_phase: FlowPhase = FlowPhase.IDLE
    turn_id: str = ""
    started_at_ms: int = 0
    timeout_ms: int = 60000  # 60 second default timeout
    pending_agents: List[str] = field(default_factory=list)
    completed_agents: List[str] = field(default_factory=list)

    def is_timed_out(self, now_ms: Optional[int] = None) -> bool:
        """Check if flow has timed out."""
        if self.started_at_ms == 0:
            return False
        now_ms = now_ms or int(time.time() * 1000)
        return (now_ms - self.started_at_ms) > self.timeout_ms


@dataclass
class TurnLock:
    """Turn-level lock to prevent concurrent turn processing."""

    locked: bool = False
    lock_holder: str = ""
    locked_at_ms: int = 0
    lock_timeout_ms: int = 30000  # 30 second default
    turn_id: str = ""

    def is_lock_expired(self, now_ms: Optional[int] = None) -> bool:
        """Check if lock has timed out."""
        if not self.locked or self.locked_at_ms == 0:
            return False
        now_ms = now_ms or int(time.time() * 1000)
        return (now_ms - self.locked_at_ms) > self.lock_timeout_ms


@dataclass
class IntentClassification:
    """Classified user intent."""

    primary: str = ""
    all_intents: List[str] = field(default_factory=list)
    scores: List[float] = field(default_factory=list)
    classifier: str = ""


@dataclass
class DomainContext:
    """Active domains for this session."""

    active_domains: List[str] = field(default_factory=list)
    primary_domain: str = ""
    domain_confidence: List[float] = field(default_factory=list)


@dataclass
class SafetyContext:
    """Safety band and context for policy enforcement."""

    band: PrivacyBand = PrivacyBand.GREEN
    escalation_reason: str = ""
    escalated_at_ms: int = 0
    requires_confirmation: bool = False
    blocked_actions: List[str] = field(default_factory=list)

    def is_escalated(self) -> bool:
        """Check if safety has been escalated above GREEN."""
        return self.band != PrivacyBand.GREEN


# =============================================================================
# ControlSection - Production Implementation
# =============================================================================


class ControlSection:
    """
    Control Section - NEVER EVICT orchestration state.

    This section contains critical orchestration state that must always
    be present in memory. It manages:
    - Agent leases (10-20 agents max)
    - Flow state (current phase, pending/completed agents)
    - Turn lock (prevents concurrent processing)
    - Intent classification
    - Domain context
    - Safety context

    Budget: 8KB (8192 bytes)
    Tier: HOT CORE
    Eviction: NEVER - Always protected

    FlatBuffer Schema: control_section.fbs
    Serialization Target: <100 microseconds

    Example:
        section = ControlSection(session_id="sess-123")

        # Register agent
        lease = section.register_agent("agent-1", "planner")

        # Start turn
        turn_id = section.start_turn()

        # Acquire lock
        section.acquire_lock("agent-1", turn_id)

        # Set flow phase
        section.set_flow_phase(FlowPhase.EXECUTION)

        # Serialize for persistence
        data = section.to_flatbuffer()
    """

    BUDGET_BYTES = 8192  # 8KB
    TIER = "hot"
    CAN_EVICT = False
    SECTION_NAME = "control"
    SCHEMA_VERSION = "1.0.0"
    DEFAULT_LEASE_TTL_MS = 30000  # 30 seconds

    def __init__(
        self,
        session_id: str = "",
        schema_version: str = "",
    ) -> None:
        """
        Initialize ControlSection.

        Args:
            session_id: Session UUID (generated if empty)
            schema_version: Schema version (uses default if empty)
        """
        now_ms = int(time.time() * 1000)

        self._session_id = session_id or str(uuid.uuid4())
        self._schema_version = schema_version or self.SCHEMA_VERSION
        self._created_at_ms = now_ms
        self._last_updated_ms = now_ms

        # Core state
        self._agent_leases: Dict[str, AgentLease] = {}
        self._flow_state = FlowState()
        self._turn_lock = TurnLock()
        self._intents = IntentClassification()
        self._domains = DomainContext()
        self._safety = SafetyContext()

        # FSM overlay (M4 E4.1.2) -- mirrors ConciergeControlExtension
        self._fsm_overlay: Dict[str, Any] = {
            "fsm_state": "",
            "active_task_ids": [],
            "complexity_tier": "",
        }

        # Temporal anchor (sub-field per skeleton.mmd NOTE line 834)
        # Computed by temporal resolution engine, written during Phase 1.
        # Port path: moves to Multimodal section (Section 5) during port.
        self._temporal_anchor: Optional[Dict[str, Any]] = None

        # Turn tracking
        self._current_turn_id = str(uuid.uuid4())
        self._turn_count = 0

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
        """Whether section can be evicted. Always False for ControlSection."""
        return self.CAN_EVICT

    def get_size_bytes(self) -> int:
        """
        Get current serialized size in bytes.

        Uses cached value if available, otherwise computes estimate.
        """
        if self._cache_valid and self._cached_bytes:
            return len(self._cached_bytes)

        # Estimate size without full serialization
        size = 0

        # Header overhead (~50 bytes)
        size += 50

        # Agent leases (~100 bytes each average)
        size += len(self._agent_leases) * 100

        # Flow state (~200 bytes)
        size += 200

        # Turn lock (~100 bytes)
        size += 100

        # Intents (~100 bytes)
        size += 100

        # Domains (~100 bytes)
        size += 100

        # Safety (~100 bytes)
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

        # Build nested objects first (FlatBuffers requirement)
        # Strings and vectors must be created before the table they're in

        # 1. Build agent leases
        lease_offsets = []
        for lease in self._agent_leases.values():
            # Build capabilities vector
            cap_offsets = [builder.CreateString(c) for c in lease.capabilities]
            if cap_offsets:
                AgentLeaseStartCapabilitiesVector(builder, len(cap_offsets))
                for co in reversed(cap_offsets):
                    builder.PrependUOffsetTRelative(co)
                caps_vec = builder.EndVector()
            else:
                caps_vec = 0

            agent_id_offset = builder.CreateString(lease.agent_id)
            agent_type_offset = builder.CreateString(lease.agent_type)

            AgentLeaseStart(builder)
            AgentLeaseAddAgentId(builder, agent_id_offset)
            AgentLeaseAddAgentType(builder, agent_type_offset)
            AgentLeaseAddState(builder, int(lease.state))
            AgentLeaseAddLeaseStartedMs(builder, lease.lease_started_ms)
            AgentLeaseAddLeaseExpiresMs(builder, lease.lease_expires_ms)
            if caps_vec:
                AgentLeaseAddCapabilities(builder, caps_vec)
            AgentLeaseAddPriority(builder, lease.priority)
            lease_offsets.append(AgentLeaseEnd(builder))

        # Build leases vector
        if lease_offsets:
            ControlSectionStartAgentLeasesVector(builder, len(lease_offsets))
            for lo in reversed(lease_offsets):
                builder.PrependUOffsetTRelative(lo)
            leases_vec = builder.EndVector()
        else:
            leases_vec = 0

        # 2. Build flow state
        fs = self._flow_state
        turn_id_offset = builder.CreateString(fs.turn_id)

        pending_offsets = [builder.CreateString(a) for a in fs.pending_agents]
        if pending_offsets:
            FlowStateStartPendingAgentsVector(builder, len(pending_offsets))
            for po in reversed(pending_offsets):
                builder.PrependUOffsetTRelative(po)
            pending_vec = builder.EndVector()
        else:
            pending_vec = 0

        completed_offsets = [builder.CreateString(a) for a in fs.completed_agents]
        if completed_offsets:
            FlowStateStartCompletedAgentsVector(builder, len(completed_offsets))
            for co in reversed(completed_offsets):
                builder.PrependUOffsetTRelative(co)
            completed_vec = builder.EndVector()
        else:
            completed_vec = 0

        FlowStateStart(builder)
        FlowStateAddCurrentPhase(builder, int(fs.current_phase))
        FlowStateAddTurnId(builder, turn_id_offset)
        FlowStateAddStartedAtMs(builder, fs.started_at_ms)
        FlowStateAddTimeoutMs(builder, fs.timeout_ms)
        if pending_vec:
            FlowStateAddPendingAgents(builder, pending_vec)
        if completed_vec:
            FlowStateAddCompletedAgents(builder, completed_vec)
        flow_state_offset = FlowStateEnd(builder)

        # 3. Build turn lock
        tl = self._turn_lock
        lock_holder_offset = builder.CreateString(tl.lock_holder)
        lock_turn_id_offset = builder.CreateString(tl.turn_id)

        TurnLockStart(builder)
        TurnLockAddLocked(builder, tl.locked)
        TurnLockAddLockHolder(builder, lock_holder_offset)
        TurnLockAddLockedAtMs(builder, tl.locked_at_ms)
        TurnLockAddLockTimeoutMs(builder, tl.lock_timeout_ms)
        TurnLockAddTurnId(builder, lock_turn_id_offset)
        turn_lock_offset = TurnLockEnd(builder)

        # 4. Build domains
        dc = self._domains
        domain_offsets = [builder.CreateString(d) for d in dc.active_domains]
        if domain_offsets:
            DomainContextStartActiveDomainsVector(builder, len(domain_offsets))
            for do in reversed(domain_offsets):
                builder.PrependUOffsetTRelative(do)
            domains_vec = builder.EndVector()
        else:
            domains_vec = 0

        primary_domain_offset = builder.CreateString(dc.primary_domain)

        DomainContextStart(builder)
        if domains_vec:
            DomainContextAddActiveDomains(builder, domains_vec)
        DomainContextAddPrimaryDomain(builder, primary_domain_offset)
        domains_offset = DomainContextEnd(builder)

        # 5. Build safety context
        sc = self._safety
        esc_reason_offset = builder.CreateString(sc.escalation_reason)

        blocked_offsets = [builder.CreateString(a) for a in sc.blocked_actions]
        if blocked_offsets:
            SafetyContextStartBlockedActionsVector(builder, len(blocked_offsets))
            for bo in reversed(blocked_offsets):
                builder.PrependUOffsetTRelative(bo)
            blocked_vec = builder.EndVector()
        else:
            blocked_vec = 0

        SafetyContextStart(builder)
        SafetyContextAddBand(builder, int(sc.band))
        SafetyContextAddEscalationReason(builder, esc_reason_offset)
        SafetyContextAddEscalatedAtMs(builder, sc.escalated_at_ms)
        SafetyContextAddRequiresConfirmation(builder, sc.requires_confirmation)
        if blocked_vec:
            SafetyContextAddBlockedActions(builder, blocked_vec)
        safety_offset = SafetyContextEnd(builder)

        # 6. Build header
        section_name_offset = builder.CreateString(self.SECTION_NAME)

        SectionHeaderStart(builder)
        SectionHeaderAddSectionName(builder, section_name_offset)
        SectionHeaderAddSizeBytes(builder, self.get_size_bytes())
        SectionHeaderAddLastUpdatedMs(builder, self._last_updated_ms)
        header_offset = SectionHeaderEnd(builder)

        # 7. Build ControlSection root
        ControlSectionStart(builder)
        ControlSectionAddHeader(builder, header_offset)
        if leases_vec:
            ControlSectionAddAgentLeases(builder, leases_vec)
        ControlSectionAddFlowState(builder, flow_state_offset)
        ControlSectionAddTurnLock(builder, turn_lock_offset)
        ControlSectionAddDomains(builder, domains_offset)
        ControlSectionAddSafety(builder, safety_offset)
        ControlSectionAddNeverEvict(builder, True)
        control_section = ControlSectionEnd(builder)

        builder.Finish(control_section)
        self._cached_bytes = bytes(builder.Output())
        self._cache_valid = True

        return self._cached_bytes

    def from_flatbuffer(self, data: bytes) -> None:
        """
        Deserialize section from FlatBuffer bytes.

        Args:
            data: FlatBuffer-encoded data
        """
        fb = FBControlSection.GetRootAsControlSection(data, 0)

        # Clear current state
        self._agent_leases.clear()

        # Load agent leases
        for i in range(fb.AgentLeasesLength()):
            lease_fb = fb.AgentLeases(i)
            if lease_fb:
                caps = [
                    (
                        lease_fb.Capabilities(j).decode("utf-8")
                        if isinstance(lease_fb.Capabilities(j), bytes)
                        else lease_fb.Capabilities(j)
                    )
                    for j in range(lease_fb.CapabilitiesLength())
                ]
                agent_id = (
                    lease_fb.AgentId().decode("utf-8")
                    if isinstance(lease_fb.AgentId(), bytes)
                    else lease_fb.AgentId()
                )
                agent_type = (
                    lease_fb.AgentType().decode("utf-8")
                    if isinstance(lease_fb.AgentType(), bytes)
                    else lease_fb.AgentType()
                )
                lease = AgentLease(
                    agent_id=agent_id or "",
                    agent_type=agent_type or "",
                    state=AgentState(lease_fb.State()),
                    lease_started_ms=lease_fb.LeaseStartedMs(),
                    lease_expires_ms=lease_fb.LeaseExpiresMs(),
                    capabilities=caps,
                    priority=lease_fb.Priority(),
                )
                self._agent_leases[lease.agent_id] = lease

        # Load flow state
        fs_fb = fb.FlowState()
        if fs_fb:
            turn_id = (
                fs_fb.TurnId().decode("utf-8")
                if isinstance(fs_fb.TurnId(), bytes)
                else fs_fb.TurnId()
            )
            pending = [
                (
                    fs_fb.PendingAgents(j).decode("utf-8")
                    if isinstance(fs_fb.PendingAgents(j), bytes)
                    else fs_fb.PendingAgents(j)
                )
                for j in range(fs_fb.PendingAgentsLength())
            ]
            completed = [
                (
                    fs_fb.CompletedAgents(j).decode("utf-8")
                    if isinstance(fs_fb.CompletedAgents(j), bytes)
                    else fs_fb.CompletedAgents(j)
                )
                for j in range(fs_fb.CompletedAgentsLength())
            ]
            self._flow_state = FlowState(
                current_phase=FlowPhase(fs_fb.CurrentPhase()),
                turn_id=turn_id or "",
                started_at_ms=fs_fb.StartedAtMs(),
                timeout_ms=fs_fb.TimeoutMs(),
                pending_agents=pending,
                completed_agents=completed,
            )

        # Load turn lock
        tl_fb = fb.TurnLock()
        if tl_fb:
            lock_holder = (
                tl_fb.LockHolder().decode("utf-8")
                if isinstance(tl_fb.LockHolder(), bytes)
                else tl_fb.LockHolder()
            )
            turn_id = (
                tl_fb.TurnId().decode("utf-8")
                if isinstance(tl_fb.TurnId(), bytes)
                else tl_fb.TurnId()
            )
            self._turn_lock = TurnLock(
                locked=tl_fb.Locked(),
                lock_holder=lock_holder or "",
                locked_at_ms=tl_fb.LockedAtMs(),
                lock_timeout_ms=tl_fb.LockTimeoutMs(),
                turn_id=turn_id or "",
            )

        # Load domains
        dc_fb = fb.Domains()
        if dc_fb:
            domains = [
                (
                    dc_fb.ActiveDomains(j).decode("utf-8")
                    if isinstance(dc_fb.ActiveDomains(j), bytes)
                    else dc_fb.ActiveDomains(j)
                )
                for j in range(dc_fb.ActiveDomainsLength())
            ]
            primary = (
                dc_fb.PrimaryDomain().decode("utf-8")
                if isinstance(dc_fb.PrimaryDomain(), bytes)
                else dc_fb.PrimaryDomain()
            )
            self._domains = DomainContext(
                active_domains=domains,
                primary_domain=primary or "",
            )

        # Load safety
        sc_fb = fb.Safety()
        if sc_fb:
            esc_reason = (
                sc_fb.EscalationReason().decode("utf-8")
                if isinstance(sc_fb.EscalationReason(), bytes)
                else sc_fb.EscalationReason()
            )
            blocked = [
                (
                    sc_fb.BlockedActions(j).decode("utf-8")
                    if isinstance(sc_fb.BlockedActions(j), bytes)
                    else sc_fb.BlockedActions(j)
                )
                for j in range(sc_fb.BlockedActionsLength())
            ]
            self._safety = SafetyContext(
                band=PrivacyBand(sc_fb.Band()),
                escalation_reason=esc_reason or "",
                escalated_at_ms=sc_fb.EscalatedAtMs(),
                requires_confirmation=sc_fb.RequiresConfirmation(),
                blocked_actions=blocked,
            )

        # Update timestamp
        header = fb.Header()
        if header:
            self._last_updated_ms = header.LastUpdatedMs()

        self._invalidate_cache()

    def clear(self) -> None:
        """Clear all section data to initial state."""
        now_ms = int(time.time() * 1000)

        self._agent_leases.clear()
        self._flow_state = FlowState()
        self._turn_lock = TurnLock()
        self._intents = IntentClassification()
        self._domains = DomainContext()
        self._safety = SafetyContext()
        self._fsm_overlay = {
            "fsm_state": "",
            "active_task_ids": [],
            "complexity_tier": "",
        }
        self._current_turn_id = str(uuid.uuid4())
        self._turn_count = 0
        self._last_updated_ms = now_ms

        self._invalidate_cache()

    def get_metadata(self) -> Dict[str, Any]:
        """Get section metadata for telemetry/debugging."""
        meta: Dict[str, Any] = {
            "name": self.name,
            "tier": self.tier,
            "budget_bytes": self.budget_bytes,
            "current_size_bytes": self.get_size_bytes(),
            "utilization_pct": (self.get_size_bytes() / self.budget_bytes) * 100,
            "can_evict": self.can_evict,
            "session_id": self._session_id,
            "schema_version": self._schema_version,
            "turn_count": self._turn_count,
            "current_turn_id": self._current_turn_id,
            "agent_count": len(self._agent_leases),
            "flow_phase": self._flow_state.current_phase.name,
            "is_locked": self._turn_lock.locked,
            "safety_band": self._safety.band.name,
            "last_updated_ms": self._last_updated_ms,
        }
        # M4 E4.1.2: include FSM overlay when populated
        if self._fsm_overlay.get("fsm_state"):
            meta["fsm_state"] = self._fsm_overlay["fsm_state"]
            meta["active_task_ids"] = list(self._fsm_overlay["active_task_ids"])
            meta["complexity_tier"] = self._fsm_overlay["complexity_tier"]
        # Temporal anchor (sub-field per skeleton.mmd NOTE)
        if self._temporal_anchor is not None:
            meta["temporal_anchor"] = self._temporal_anchor
        return meta

    def set_temporal_anchor(self, anchor_dict: Dict[str, Any]) -> None:
        """Set temporal anchor computed by Temporal Resolution Engine.

        Architecture ref: skeleton.mmd -> ACKING_CORE -> TIME_RESOLUTION
        Port path: Multimodal section sub-field (Section 5).

        Args:
            anchor_dict: TemporalAnchor.to_dict() output with keys:
                local_time_iso, day_of_week, time_of_day, is_weekend,
                timezone, hour_24
        """
        self._temporal_anchor = anchor_dict
        self._last_updated_ms = int(time.time() * 1000)
        self._invalidate_cache()

    def get_temporal_anchor(self) -> Optional[Dict[str, Any]]:
        """Get current temporal anchor, or None if not yet computed."""
        return self._temporal_anchor

    def set_fsm_overlay(
        self,
        fsm_state: str,
        active_task_ids: List[str],
        complexity_tier: str = "",
    ) -> None:
        """Set FSM overlay fields mirrored from ConciergeControlExtension.

        Called by the control extension after every FSM state mutation
        so that actors reading ControlSection from SessionState see
        the current FSM state and active task list.

        M4 E4.1.2 -- avoids FlatBuffer schema churn by storing in a
        metadata sub-dict rather than adding schema-level fields.

        P3.1 -- ``complexity_tier`` is retained for backward-compat with
        existing dispatch_task AUTO callers (P3.3 deletes the AUTO path).
        Phase 1 no longer produces it; new callers should omit it.

        Args:
            fsm_state:       Current ConciergeState name.
            active_task_ids: Currently active task ID list.
            complexity_tier: Legacy tier (kept for AUTO dispatch fallback).
        """
        self._fsm_overlay = {
            "fsm_state": fsm_state,
            "active_task_ids": list(active_task_ids),
            "complexity_tier": complexity_tier,
        }
        self._touch()

    @property
    def fsm_overlay(self) -> Dict[str, Any]:
        """Read-only access to the FSM overlay dict."""
        return dict(self._fsm_overlay)

    # =========================================================================
    # Agent Lease Management
    # =========================================================================

    def register_agent(
        self,
        agent_id: str,
        agent_type: str,
        capabilities: Optional[List[str]] = None,
        priority: int = 0,
        ttl_ms: Optional[int] = None,
    ) -> AgentLease:
        """
        Register a new agent with a lease.

        Args:
            agent_id: Unique agent identifier
            agent_type: Agent type (planner, executor, etc.)
            capabilities: List of agent capabilities
            priority: Agent priority (0-255)
            ttl_ms: Lease duration in milliseconds

        Returns:
            AgentLease: Created lease

        Raises:
            ValueError: If agent already registered
        """
        if agent_id in self._agent_leases:
            raise ValueError(f"Agent {agent_id} already registered")

        now_ms = int(time.time() * 1000)
        ttl = ttl_ms or self.DEFAULT_LEASE_TTL_MS

        lease = AgentLease(
            agent_id=agent_id,
            agent_type=agent_type,
            state=AgentState.PENDING,
            lease_started_ms=now_ms,
            lease_expires_ms=now_ms + ttl,
            capabilities=capabilities or [],
            priority=priority,
        )

        self._agent_leases[agent_id] = lease
        self._touch()
        return lease

    def renew_lease(
        self,
        agent_id: str,
        ttl_ms: Optional[int] = None,
    ) -> bool:
        """
        Renew an agent's lease.

        Args:
            agent_id: Agent identifier
            ttl_ms: New TTL in milliseconds

        Returns:
            bool: True if renewed, False if not found
        """
        if agent_id not in self._agent_leases:
            return False

        now_ms = int(time.time() * 1000)
        ttl = ttl_ms or self.DEFAULT_LEASE_TTL_MS

        lease = self._agent_leases[agent_id]
        lease.lease_expires_ms = now_ms + ttl
        lease.lease_started_ms = now_ms

        self._touch()
        return True

    def set_agent_state(
        self,
        agent_id: str,
        state: AgentState,
    ) -> bool:
        """
        Update agent state.

        Args:
            agent_id: Agent identifier
            state: New state

        Returns:
            bool: True if updated, False if not found
        """
        if agent_id not in self._agent_leases:
            return False

        self._agent_leases[agent_id].state = state
        self._touch()
        return True

    def unregister_agent(self, agent_id: str) -> bool:
        """
        Unregister an agent.

        Args:
            agent_id: Agent identifier

        Returns:
            bool: True if removed, False if not found
        """
        if agent_id not in self._agent_leases:
            return False

        del self._agent_leases[agent_id]
        self._touch()
        return True

    def get_agent(self, agent_id: str) -> Optional[AgentLease]:
        """Get agent lease by ID."""
        return self._agent_leases.get(agent_id)

    def list_agents(self, state: Optional[AgentState] = None) -> List[AgentLease]:
        """List agents, optionally filtered by state."""
        if state is None:
            return list(self._agent_leases.values())
        return [l for l in self._agent_leases.values() if l.state == state]

    def expire_stale_leases(self, now_ms: Optional[int] = None) -> List[str]:
        """
        Expire stale leases and return list of expired agent IDs.

        Args:
            now_ms: Current time (uses system time if not provided)

        Returns:
            List of expired agent IDs
        """
        now_ms = now_ms or int(time.time() * 1000)
        expired = [aid for aid, lease in self._agent_leases.items() if lease.is_expired(now_ms)]

        for aid in expired:
            del self._agent_leases[aid]

        if expired:
            self._touch()

        return expired

    # =========================================================================
    # Flow State Management
    # =========================================================================

    def get_flow_state(self) -> FlowState:
        """Get current flow state."""
        return self._flow_state

    def set_flow_phase(self, phase: FlowPhase) -> None:
        """Set current flow phase."""
        self._flow_state.current_phase = phase
        self._touch()

    def start_turn(self, timeout_ms: int = 60000) -> str:
        """
        Start a new turn.

        Args:
            timeout_ms: Turn timeout in milliseconds

        Returns:
            str: New turn ID
        """
        now_ms = int(time.time() * 1000)
        self._turn_count += 1
        self._current_turn_id = str(uuid.uuid4())

        self._flow_state = FlowState(
            current_phase=FlowPhase.IDLE,
            turn_id=self._current_turn_id,
            started_at_ms=now_ms,
            timeout_ms=timeout_ms,
            pending_agents=[],
            completed_agents=[],
        )

        self._touch()
        return self._current_turn_id

    def add_pending_agent(self, agent_id: str) -> None:
        """Add agent to pending list."""
        if agent_id not in self._flow_state.pending_agents:
            self._flow_state.pending_agents.append(agent_id)
            self._touch()

    def mark_agent_completed(self, agent_id: str) -> None:
        """Mark agent as completed for this turn."""
        if agent_id in self._flow_state.pending_agents:
            self._flow_state.pending_agents.remove(agent_id)
        if agent_id not in self._flow_state.completed_agents:
            self._flow_state.completed_agents.append(agent_id)
        self._touch()

    # =========================================================================
    # Turn Lock Management
    # =========================================================================

    def get_turn_lock(self) -> TurnLock:
        """Get current turn lock state."""
        return self._turn_lock

    def acquire_lock(
        self,
        holder: str,
        turn_id: str,
        timeout_ms: int = 30000,
    ) -> bool:
        """
        Acquire turn lock.

        Args:
            holder: Lock holder identifier
            turn_id: Turn to lock
            timeout_ms: Lock timeout

        Returns:
            bool: True if acquired, False if already locked
        """
        # Check if current lock is expired
        if self._turn_lock.locked:
            if not self._turn_lock.is_lock_expired():
                return False  # Still locked
            # Lock expired, can acquire

        now_ms = int(time.time() * 1000)
        self._turn_lock = TurnLock(
            locked=True,
            lock_holder=holder,
            locked_at_ms=now_ms,
            lock_timeout_ms=timeout_ms,
            turn_id=turn_id,
        )

        self._touch()
        return True

    def release_lock(self, holder: str) -> bool:
        """
        Release turn lock.

        Args:
            holder: Must match current lock holder

        Returns:
            bool: True if released, False if not holder
        """
        if not self._turn_lock.locked:
            return True  # Already unlocked

        if self._turn_lock.lock_holder != holder:
            return False  # Not the holder

        self._turn_lock = TurnLock()
        self._touch()
        return True

    def force_release_lock(self) -> None:
        """Force release lock (admin operation)."""
        self._turn_lock = TurnLock()
        self._touch()

    # =========================================================================
    # Domain Management
    # =========================================================================

    def get_domains(self) -> DomainContext:
        """Get current domain context."""
        return self._domains

    def set_primary_domain(self, domain: str) -> None:
        """Set primary domain."""
        self._domains.primary_domain = domain
        if domain and domain not in self._domains.active_domains:
            self._domains.active_domains.append(domain)
        self._touch()

    def add_domain(self, domain: str) -> None:
        """Add active domain."""
        if domain not in self._domains.active_domains:
            self._domains.active_domains.append(domain)
            self._touch()

    def remove_domain(self, domain: str) -> None:
        """Remove active domain."""
        if domain in self._domains.active_domains:
            self._domains.active_domains.remove(domain)
            if self._domains.primary_domain == domain:
                self._domains.primary_domain = (
                    self._domains.active_domains[0] if self._domains.active_domains else ""
                )
            self._touch()

    # =========================================================================
    # Safety Management
    # =========================================================================

    def get_safety(self) -> SafetyContext:
        """Get current safety context."""
        return self._safety

    def escalate_safety(
        self,
        band: PrivacyBand,
        reason: str,
        require_confirmation: bool = False,
    ) -> None:
        """
        Escalate safety band.

        Args:
            band: New privacy band
            reason: Escalation reason
            require_confirmation: Whether user confirmation required
        """
        now_ms = int(time.time() * 1000)
        self._safety.band = band
        self._safety.escalation_reason = reason
        self._safety.escalated_at_ms = now_ms
        self._safety.requires_confirmation = require_confirmation
        self._touch()

    def block_action(self, action: str) -> None:
        """Block an action."""
        if action not in self._safety.blocked_actions:
            self._safety.blocked_actions.append(action)
            self._touch()

    def unblock_action(self, action: str) -> None:
        """Unblock an action."""
        if action in self._safety.blocked_actions:
            self._safety.blocked_actions.remove(action)
            self._touch()

    def reset_safety(self) -> None:
        """Reset safety to GREEN."""
        self._safety = SafetyContext()
        self._touch()

    # =========================================================================
    # Intent Management (M10 E10.2.1)
    # =========================================================================

    def set_intent(self, intent: IntentClassification) -> None:
        """Set classified intent from Phase 1.

        Args:
            intent: IntentClassification with primary, all_intents, scores, classifier.
        """
        self._intents = intent
        self._touch()

    def get_intents(self) -> IntentClassification:
        """Get current intent classification."""
        return self._intents

    # =========================================================================
    # Complexity Tier (M10 E10.2.1)
    # =========================================================================

    def set_complexity_tier(self, tier: str) -> None:
        """Set complexity tier in FSM overlay.

        Args:
            tier: "LOW", "MEDIUM", or "HIGH".
        """
        self._fsm_overlay["complexity_tier"] = tier
        self._touch()

    def get_complexity_tier(self) -> str:
        """Get complexity tier from FSM overlay."""
        return self._fsm_overlay.get("complexity_tier", "")

    # =========================================================================
    # Session Properties
    # =========================================================================

    @property
    def session_id(self) -> str:
        """Session identifier."""
        return self._session_id

    @property
    def schema_version(self) -> str:
        """Schema version."""
        return self._schema_version

    @property
    def turn_count(self) -> int:
        """Total turn count."""
        return self._turn_count

    @property
    def current_turn_id(self) -> str:
        """Current turn identifier."""
        return self._current_turn_id

    @property
    def last_updated_ms(self) -> int:
        """Last update timestamp."""
        return self._last_updated_ms

    # =========================================================================
    # Legacy API (for backward compatibility with skeleton)
    # =========================================================================

    def get(self) -> Dict[str, Any]:
        """Get control data as dictionary (legacy API)."""
        return {
            "session_id": self._session_id,
            "schema_version": self._schema_version,
            "turn_count": self._turn_count,
            "current_turn_id": self._current_turn_id,
            "flow_phase": self._flow_state.current_phase.name,
            "is_locked": self._turn_lock.locked,
            "lock_holder": self._turn_lock.lock_holder,
            "safety_band": self._safety.band.name,
            "agent_count": len(self._agent_leases),
            "last_updated_ms": self._last_updated_ms,
        }

    def set_mode(self, mode: str) -> None:
        """Set flow phase by mode name (legacy API)."""
        mode_map = {
            "idle": FlowPhase.IDLE,
            "negotiation": FlowPhase.NEGOTIATION,
            "selection": FlowPhase.SELECTION,
            "execution": FlowPhase.EXECUTION,
        }
        phase = mode_map.get(mode.lower(), FlowPhase.IDLE)
        self.set_flow_phase(phase)

    def advance_turn(self) -> str:
        """Advance to next turn (legacy API)."""
        return self.start_turn()

    def set_focus(self, task_id: str, goal: str = "") -> None:
        """Set focus (legacy API - maps to domain)."""
        self.set_primary_domain(task_id)

    def clear_focus(self) -> None:
        """Clear focus (legacy API)."""
        self._domains.primary_domain = ""
        self._touch()

    def touch(self) -> None:
        """Update last_activity_ms to now."""
        self._last_updated_ms = int(time.time() * 1000)
        self._invalidate_cache()

    def serialize(self) -> bytes:
        """Serialize to FlatBuffer bytes (legacy API)."""
        return self.to_flatbuffer()

    def deserialize(self, data: bytes) -> None:
        """Deserialize from FlatBuffer bytes (legacy API)."""
        self.from_flatbuffer(data)

    def apply(self, operation: str, data: Dict[str, Any]) -> Any:
        """Apply mutation operation (legacy API)."""
        if operation == "set_mode":
            self.set_mode(data["mode"])
        elif operation == "advance_turn":
            return self.advance_turn()
        elif operation == "set_focus":
            self.set_focus(data["task_id"], data.get("goal", ""))
        elif operation == "clear_focus":
            self.clear_focus()
        elif operation == "register_agent":
            return self.register_agent(
                data["agent_id"],
                data["agent_type"],
                data.get("capabilities"),
                data.get("priority", 0),
            )
        elif operation == "unregister_agent":
            return self.unregister_agent(data["agent_id"])
        elif operation == "acquire_lock":
            return self.acquire_lock(
                data["holder"],
                data["turn_id"],
                data.get("timeout_ms", 30000),
            )
        elif operation == "release_lock":
            return self.release_lock(data["holder"])
        elif operation == "set_fsm_overlay":
            return self.set_fsm_overlay(
                data["fsm_state"],
                data["active_task_ids"],
                data.get("complexity_tier", ""),
            )
        else:
            raise ValueError(f"Unknown operation: {operation}")

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    def _touch(self) -> None:
        """Update timestamp and invalidate cache."""
        self._last_updated_ms = int(time.time() * 1000)
        self._invalidate_cache()

    def _invalidate_cache(self) -> None:
        """Invalidate serialization cache."""
        self._cache_valid = False
        self._cached_bytes = None


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    "ControlSection",
    "ISection",
    "AgentLease",
    "FlowState",
    "TurnLock",
    "IntentClassification",
    "DomainContext",
    "SafetyContext",
    "AgentState",
    "FlowPhase",
    "PrivacyBand",
]
