"""
SessionState Event Payload Dataclasses
=======================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 3.2 Define Event Port
ISSUE: 3.2.2

CONTRACTS:
- Event schema contract: k1/contracts/schemas/events/sessionstate.events.yaml
- JSON Schema validation: k1/contracts/jsonschema/sessionstate/events.schema.json

ADRs:
- ADR-0017 series: SessionState 6-Section Design
- ADR-NEW: Event Schema Definition (to be created)

==============================================================================
SPECIFICATION
==============================================================================

PURPOSE:
    Define all event payload dataclasses for SessionState events.
    These payloads are emitted via IEventPort and must match JSON Schema.

EVENTS (8 total):
    1. MutationRequestedEvent - Before preflight check
    2. MutationApprovedEvent - After successful mutation
    3. MutationRejectedEvent - When preflight rejects mutation
    4. EvictionTriggeredEvent - When eviction starts
    5. EvictionCompletedEvent - After eviction completes
    6. EmergencyActivatedEvent - When capacity >95%
    7. EmergencyResolvedEvent - When capacity drops below threshold
    8. ReconstructionStartedEvent - When restoring from COLD

EVENT TOPIC FORMAT:
    sessionstate.{event_type}
    Example: sessionstate.mutation.approved

==============================================================================
DATACLASSES
==============================================================================
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List


class EventType(str, Enum):
    """All SessionState event types."""

    MUTATION_REQUESTED = "sessionstate.mutation.requested"
    MUTATION_APPROVED = "sessionstate.mutation.approved"
    MUTATION_REJECTED = "sessionstate.mutation.rejected"
    EVICTION_TRIGGERED = "sessionstate.eviction.triggered"
    EVICTION_COMPLETED = "sessionstate.eviction.completed"
    EMERGENCY_ACTIVATED = "sessionstate.emergency.activated"
    EMERGENCY_RESOLVED = "sessionstate.emergency.resolved"
    RECONSTRUCTION_STARTED = "sessionstate.reconstruction.started"


class PressureLevel(str, Enum):
    """Memory pressure levels."""

    NORMAL = "normal"  # <90% utilization
    ELEVATED = "elevated"  # 90-95% utilization
    CRITICAL = "critical"  # >95% utilization


class EmergencyLevel(str, Enum):
    """Emergency mode levels."""

    WARNING = "warning"  # 90% threshold
    CRITICAL = "critical"  # 95% threshold


@dataclass
class BaseEvent:
    """
    Base class for all SessionState events.

    Attributes:
        event_id: Unique event identifier (UUID)
        event_type: Event type from EventType enum
        session_id: Session that generated the event
        cognitive_trace_id: Trace ID for distributed tracing
        timestamp_ms: Event timestamp in milliseconds since epoch
    """

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = ""
    session_id: str = ""
    cognitive_trace_id: str = ""
    timestamp_ms: int = field(
        default_factory=lambda: int(datetime.now(timezone.utc).timestamp() * 1000)
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "session_id": self.session_id,
            "cognitive_trace_id": self.cognitive_trace_id,
            "timestamp_ms": self.timestamp_ms,
        }
        # Add subclass-specific fields
        for key, value in self.__dict__.items():
            if key not in result:
                # Handle enums
                if isinstance(value, Enum):
                    result[key] = value.value
                else:
                    result[key] = value
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BaseEvent":
        """Create event from dictionary."""
        return cls(**data)


@dataclass
class MutationRequestedEvent(BaseEvent):
    """
    Emitted when a mutation is requested, before preflight check.

    SPEC:
    - Emitted: Before MutationGuard.preflight()
    - Purpose: Audit trail, metrics collection

    Attributes:
        section: Target section name
        operation: Operation type (set, append, update, clear)
        estimated_bytes: Estimated size of mutation
        writer_id: ID of the writer requesting mutation (should be Concierge)
    """

    event_type: str = field(default=EventType.MUTATION_REQUESTED.value)
    section: str = ""
    operation: str = ""
    estimated_bytes: int = 0
    writer_id: str = ""


@dataclass
class MutationApprovedEvent(BaseEvent):
    """
    Emitted when a mutation is approved and applied.

    SPEC:
    - Emitted: After successful mutation
    - Contains: New sizes, capacity remaining

    Attributes:
        section: Mutated section name
        operation: Operation type
        previous_size_bytes: Section size before mutation
        new_size_bytes: Section size after mutation
        tier_utilization_pct: Tier utilization percentage after mutation
        total_utilization_pct: Total utilization percentage after mutation
    """

    event_type: str = field(default=EventType.MUTATION_APPROVED.value)
    section: str = ""
    operation: str = ""
    previous_size_bytes: int = 0
    new_size_bytes: int = 0
    tier_utilization_pct: float = 0.0
    total_utilization_pct: float = 0.0


@dataclass
class MutationRejectedEvent(BaseEvent):
    """
    Emitted when preflight rejects a mutation.

    SPEC:
    - Emitted: When MutationGuard.preflight() returns rejected
    - Purpose: Alerting, debugging capacity issues

    Attributes:
        section: Target section name
        operation: Requested operation
        reason: Rejection reason
        section_available_bytes: Remaining capacity in section
        tier_available_bytes: Remaining capacity in tier
        total_available_bytes: Remaining capacity overall
    """

    event_type: str = field(default=EventType.MUTATION_REJECTED.value)
    section: str = ""
    operation: str = ""
    reason: str = ""
    section_available_bytes: int = 0
    tier_available_bytes: int = 0
    total_available_bytes: int = 0


@dataclass
class EvictionTriggeredEvent(BaseEvent):
    """
    Emitted when eviction starts.

    SPEC:
    - Emitted: When EvictionEngine.evict() is called
    - Contains: Target reduction, candidates

    Attributes:
        tier: Tier being evicted (always "warm")
        target_reduction_bytes: How many bytes to free
        pressure_level: Current pressure level
        candidates: List of sections eligible for eviction (in priority order)
    """

    event_type: str = field(default=EventType.EVICTION_TRIGGERED.value)
    tier: str = "warm"
    target_reduction_bytes: int = 0
    pressure_level: str = PressureLevel.CRITICAL.value
    candidates: List[str] = field(default_factory=list)


@dataclass
class EvictionCompletedEvent(BaseEvent):
    """
    Emitted after eviction completes.

    SPEC:
    - Emitted: After EvictionEngine.evict() completes
    - Contains: What was evicted, new pressure

    Attributes:
        tier: Tier that was evicted
        sections_evicted: Sections that had data evicted
        bytes_freed: Total bytes freed
        bytes_archived: Total bytes archived to LOCAL COLD
        new_pressure_level: Pressure level after eviction
        duration_ms: Time taken for eviction
    """

    event_type: str = field(default=EventType.EVICTION_COMPLETED.value)
    tier: str = "warm"
    sections_evicted: List[str] = field(default_factory=list)
    bytes_freed: int = 0
    bytes_archived: int = 0
    new_pressure_level: str = PressureLevel.NORMAL.value
    duration_ms: float = 0.0


@dataclass
class EmergencyActivatedEvent(BaseEvent):
    """
    Emitted when capacity exceeds emergency threshold.

    SPEC:
    - Emitted: When total utilization >90% (WARNING) or >95% (CRITICAL)
    - Purpose: Alerting, automatic eviction trigger

    Thresholds:
    - WARNING: 90% (87KB of 96KB)
    - CRITICAL: 95% (91KB of 96KB) - writes may be rejected

    Attributes:
        level: Emergency level (warning or critical)
        total_size_bytes: Current total size
        hot_size_bytes: HOT tier size
        warm_size_bytes: WARM tier size
        utilization_pct: Overall utilization percentage
        writes_blocked: Whether writes are being blocked
    """

    event_type: str = field(default=EventType.EMERGENCY_ACTIVATED.value)
    level: str = EmergencyLevel.WARNING.value
    total_size_bytes: int = 0
    hot_size_bytes: int = 0
    warm_size_bytes: int = 0
    utilization_pct: float = 0.0
    writes_blocked: bool = False


@dataclass
class EmergencyResolvedEvent(BaseEvent):
    """
    Emitted when emergency condition is resolved.

    SPEC:
    - Emitted: When utilization drops below emergency threshold
    - Contains: How it was resolved, new state

    Attributes:
        previous_level: Emergency level that was resolved
        resolution_method: How resolved (eviction, manual_clear, etc.)
        new_utilization_pct: Utilization after resolution
        duration_ms: How long emergency lasted
    """

    event_type: str = field(default=EventType.EMERGENCY_RESOLVED.value)
    previous_level: str = EmergencyLevel.WARNING.value
    resolution_method: str = ""
    new_utilization_pct: float = 0.0
    duration_ms: float = 0.0


@dataclass
class ReconstructionStartedEvent(BaseEvent):
    """
    Emitted when session reconstruction from COLD begins.

    SPEC:
    - Emitted: When restore() is called
    - Contains: Source, sections being restored

    Attributes:
        source: Reconstruction source (local_cold, k0, fresh)
        sections_requested: Sections requested for restoration
        expected_duration_ms: Expected duration based on data size
    """

    event_type: str = field(default=EventType.RECONSTRUCTION_STARTED.value)
    source: str = "local_cold"  # local_cold, k0, fresh
    sections_requested: List[str] = field(default_factory=list)
    expected_duration_ms: float = 0.0


# =============================================================================
# EVENT FACTORY
# =============================================================================


class SessionStateEvents:
    """
    Factory for creating SessionState events with proper defaults.

    Usage:
        event = SessionStateEvents.mutation_approved(
            session_id="session-123",
            cognitive_trace_id="trace-456",
            section="beliefs_active",
            operation="append",
            previous_size_bytes=1024,
            new_size_bytes=2048,
        )

        event_port.emit(event.event_type, event)
    """

    @staticmethod
    def mutation_requested(
        session_id: str,
        cognitive_trace_id: str,
        section: str,
        operation: str,
        estimated_bytes: int,
        writer_id: str = "concierge",
    ) -> MutationRequestedEvent:
        """Create a MutationRequestedEvent."""
        return MutationRequestedEvent(
            session_id=session_id,
            cognitive_trace_id=cognitive_trace_id,
            section=section,
            operation=operation,
            estimated_bytes=estimated_bytes,
            writer_id=writer_id,
        )

    @staticmethod
    def mutation_approved(
        session_id: str,
        cognitive_trace_id: str,
        section: str,
        operation: str,
        previous_size_bytes: int,
        new_size_bytes: int,
        tier_utilization_pct: float,
        total_utilization_pct: float,
    ) -> MutationApprovedEvent:
        """Create a MutationApprovedEvent."""
        return MutationApprovedEvent(
            session_id=session_id,
            cognitive_trace_id=cognitive_trace_id,
            section=section,
            operation=operation,
            previous_size_bytes=previous_size_bytes,
            new_size_bytes=new_size_bytes,
            tier_utilization_pct=tier_utilization_pct,
            total_utilization_pct=total_utilization_pct,
        )

    @staticmethod
    def mutation_rejected(
        session_id: str,
        cognitive_trace_id: str,
        section: str,
        operation: str,
        reason: str,
        section_available_bytes: int,
        tier_available_bytes: int,
        total_available_bytes: int,
    ) -> MutationRejectedEvent:
        """Create a MutationRejectedEvent."""
        return MutationRejectedEvent(
            session_id=session_id,
            cognitive_trace_id=cognitive_trace_id,
            section=section,
            operation=operation,
            reason=reason,
            section_available_bytes=section_available_bytes,
            tier_available_bytes=tier_available_bytes,
            total_available_bytes=total_available_bytes,
        )

    @staticmethod
    def eviction_triggered(
        session_id: str,
        cognitive_trace_id: str,
        target_reduction_bytes: int,
        pressure_level: PressureLevel,
        candidates: List[str],
    ) -> EvictionTriggeredEvent:
        """Create an EvictionTriggeredEvent."""
        return EvictionTriggeredEvent(
            session_id=session_id,
            cognitive_trace_id=cognitive_trace_id,
            target_reduction_bytes=target_reduction_bytes,
            pressure_level=(
                pressure_level.value
                if isinstance(pressure_level, PressureLevel)
                else pressure_level
            ),
            candidates=candidates,
        )

    @staticmethod
    def eviction_completed(
        session_id: str,
        cognitive_trace_id: str,
        sections_evicted: List[str],
        bytes_freed: int,
        bytes_archived: int,
        new_pressure_level: PressureLevel,
        duration_ms: float,
    ) -> EvictionCompletedEvent:
        """Create an EvictionCompletedEvent."""
        return EvictionCompletedEvent(
            session_id=session_id,
            cognitive_trace_id=cognitive_trace_id,
            sections_evicted=sections_evicted,
            bytes_freed=bytes_freed,
            bytes_archived=bytes_archived,
            new_pressure_level=(
                new_pressure_level.value
                if isinstance(new_pressure_level, PressureLevel)
                else new_pressure_level
            ),
            duration_ms=duration_ms,
        )

    @staticmethod
    def emergency_activated(
        session_id: str,
        cognitive_trace_id: str,
        level: EmergencyLevel,
        total_size_bytes: int,
        hot_size_bytes: int,
        warm_size_bytes: int,
        writes_blocked: bool = False,
    ) -> EmergencyActivatedEvent:
        """Create an EmergencyActivatedEvent."""
        total_budget = 96 * 1024  # 96KB
        utilization_pct = (total_size_bytes / total_budget) * 100 if total_budget > 0 else 0.0
        return EmergencyActivatedEvent(
            session_id=session_id,
            cognitive_trace_id=cognitive_trace_id,
            level=level.value if isinstance(level, EmergencyLevel) else level,
            total_size_bytes=total_size_bytes,
            hot_size_bytes=hot_size_bytes,
            warm_size_bytes=warm_size_bytes,
            utilization_pct=utilization_pct,
            writes_blocked=writes_blocked,
        )

    @staticmethod
    def emergency_resolved(
        session_id: str,
        cognitive_trace_id: str,
        previous_level: EmergencyLevel,
        resolution_method: str,
        new_utilization_pct: float,
        duration_ms: float,
    ) -> EmergencyResolvedEvent:
        """Create an EmergencyResolvedEvent."""
        return EmergencyResolvedEvent(
            session_id=session_id,
            cognitive_trace_id=cognitive_trace_id,
            previous_level=(
                previous_level.value
                if isinstance(previous_level, EmergencyLevel)
                else previous_level
            ),
            resolution_method=resolution_method,
            new_utilization_pct=new_utilization_pct,
            duration_ms=duration_ms,
        )

    @staticmethod
    def reconstruction_started(
        session_id: str,
        cognitive_trace_id: str,
        source: str,
        sections_requested: List[str],
        expected_duration_ms: float = 0.0,
    ) -> ReconstructionStartedEvent:
        """Create a ReconstructionStartedEvent."""
        return ReconstructionStartedEvent(
            session_id=session_id,
            cognitive_trace_id=cognitive_trace_id,
            source=source,
            sections_requested=sections_requested,
            expected_duration_ms=expected_duration_ms,
        )


# =============================================================================
# IMPLEMENTATION NOTES
# =============================================================================
"""
1. JSON SCHEMA VALIDATION:
   - All events must validate against k1/contracts/jsonschema/sessionstate/events.schema.json
   - Use to_dict() method for serialization
   - Add from_dict() class method for deserialization

2. DISTRIBUTED TRACING:
   - cognitive_trace_id MUST be propagated from Concierge request
   - Used for correlating SessionState events with orchestration flow

3. TIMESTAMP FORMAT:
   - Use milliseconds since epoch (int)
   - UTC timezone always

4. EVENT EMISSION ORDER:
   Mutation flow:
   1. MutationRequestedEvent
   2. MutationApprovedEvent OR MutationRejectedEvent
   3. (optional) EvictionTriggeredEvent
   4. (optional) EvictionCompletedEvent
   5. (optional) EmergencyActivatedEvent

5. TESTING:
   - Use LocalEventAdapter with capture mode
   - Assert events emitted with correct payloads
   - Verify JSON Schema compliance
"""
