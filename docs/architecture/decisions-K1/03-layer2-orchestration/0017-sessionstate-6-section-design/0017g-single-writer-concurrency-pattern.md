---
adr_number: 0017g
status: ACCEPTED
date_created: '2025-11-03'
date_updated: '2025-11-03'
implementation_date: null
implementation_phase: 'Phase 1 (Foundation)'
implementation_status: PLANNING
authors:
- K1 Architecture Team
title: SessionState Single-Writer Concurrency Pattern
affected_layers:
- layer2_orchestration
- layer3_execution
- layer4_runtime
affected_modules:
- k1.sessionstate.manager
- k1.sessionstate.guard
- k1.concierge
concerns:
- architecture
- concurrency
- performance
- reliability
- security
propagation:
  affected_adrs:
  - ADR-0017
  - ADR-0018
  - ADR-0086
  - ADR-0093
  affected_tests:
  - tests/k1/sessionstate/test_mutation_guard.py
  - tests/k1/sessionstate/test_concurrency.py
  triggers:
  - Writer role changes (Concierge to other agent)
  - MutationGuard policy changes
  - Delta bus protocol changes
  - Sub-agent write access requirements
related_adrs:
- ADR-0017
- ADR-0017c
- ADR-0018
- ADR-0086
- ADR-0093
related_contracts:
- k1/contracts/schemas/module/sessionstate.contract.yaml
- k1/contracts/schemas/events/sessionstate/mutation_requested.v1.json
- k1/contracts/schemas/events/sessionstate/mutation_approved.v1.json
related_diagrams: []
research_citations:
- 'Single-Writer Principle (Martin Thompson, 2011)'
- 'Actor Model Concurrency (Hewitt, 1973)'
- 'Event Sourcing (Martin Fowler, 2005)'
superseded_by: []
supersedes: []
---

# ADR-0017g: SessionState Single-Writer Concurrency Pattern

**Status:** ACCEPTED
**Date:** 2025-11-03
**Authors:** K1 Architecture Team
**Parent ADR:** [ADR-0017 (SessionState 12-Section Design)](0017.md)
**Category:** State Management - Concurrency
**Related ADRs:**
- [ADR-0017c (Control Section)](0017c-control-section-agent-leases-flow.md)
- [ADR-0086 (Dynamic Agent Creation)](../0086-dynamic-agent-creation-subsystem/)
- [ADR-0093 (Concierge Agent Pattern)](../0093-conciergeagent-pattern-(master-coordinator-with-11-meta-intents)/)

---

## Context

### Problem Statement

K1 orchestrates multiple concurrent agents (Concierge, sub-agents, dynamic agents) that all need access to SessionState. Without a formal concurrency model:

1. **Race Conditions:** Multiple agents writing simultaneously corrupt state
2. **Lost Updates:** Agent A reads, Agent B writes, Agent A writes (overwrites B's change)
3. **Inconsistent State:** Half-written mutations visible to readers
4. **Deadlocks:** Agents waiting for each other's locks
5. **Debug Nightmare:** Non-deterministic failures in production

**Observed Failure Modes (Without Single-Writer):**

| Failure Mode | Scenario | Impact |
|--------------|----------|--------|
| **Corrupted beliefs** | Two agents update beliefs_active simultaneously | User facts lost/duplicated |
| **Stale referents** | Scoreboard read during write | Invalid entity references |
| **Turn collision** | Two agents claim turn_lock | Orchestration deadlock |
| **Eviction race** | Eviction runs during active mutation | Data loss |

### Requirements

1. **Consistency:** All readers see consistent state (no partial writes)
2. **Performance:** No lock contention on read path (<100μs read latency)
3. **Simplicity:** Easy to reason about, debug, and test
4. **Flexibility:** Sub-agents can request mutations without direct write access

---

## Decision

We will implement a **Single-Writer Concurrency Pattern** where:

### Core Principle: Concierge is the Sole Writer

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SESSIONSTATE CONCURRENCY MODEL                            │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    CONCIERGE AGENT                                   │    │
│  │                    (SOLE WRITER)                                     │    │
│  │  • Owns SessionState instance                                        │    │
│  │  • All mutations go through Concierge                                │    │
│  │  • MutationGuard validates all writes                                │    │
│  │  • Emits mutation events on Delta Bus                                │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                              │                                               │
│                              │ write                                         │
│                              ▼                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    SESSIONSTATE                                      │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │    │
│  │  │  HOT CORE   │  │  WARM TIER  │  │ LOCAL COLD  │                  │    │
│  │  │   (48KB)    │  │   (48KB)    │  │  (SQLite)   │                  │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                              ▲                                               │
│                              │ read-only                                     │
│                              │                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    SUB-AGENTS (READ-ONLY)                            │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │    │
│  │  │ Research    │  │ Calendar    │  │ Smart Home  │                  │    │
│  │  │ Agent       │  │ Agent       │  │ Agent       │                  │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                  │    │
│  │         │                │                │                          │    │
│  │         └────────────────┴────────────────┘                          │    │
│  │                          │                                           │    │
│  │                          │ mutation requests                         │    │
│  │                          ▼                                           │    │
│  │                    DELTA BUS                                         │    │
│  │              (Write Request Channel)                                 │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                              │                                               │
│                              │ sessionstate.mutation.requested.v1           │
│                              ▼                                               │
│                         CONCIERGE                                            │
│                    (Approves/Rejects)                                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Access Control Matrix

| Agent Type | Read Access | Write Access | Mutation Request | Rationale |
|------------|-------------|--------------|------------------|-----------|
| **Concierge** | ✅ Full | ✅ Full (via MutationGuard) | N/A (is writer) | Master coordinator owns state |
| **Sub-Agent** | ✅ Snapshot | ❌ None | ✅ Via Delta Bus | Isolation prevents corruption |
| **Dynamic Agent** | ✅ Scoped | ❌ None | ✅ Via Delta Bus | Spawned agents are untrusted |
| **Tool** | ❌ None | ❌ None | ❌ None | Tools are stateless |
| **External** | ❌ None | ❌ None | ❌ None | Security boundary |

### MutationGuard Enforcement

All writes MUST pass through MutationGuard:

```python
# k1/sessionstate/guard.py
"""MutationGuard - Enforces single-writer pattern"""

from dataclasses import dataclass
from typing import Optional
from enum import Enum, auto


class RejectionReason(Enum):
    """Reasons a mutation can be rejected"""
    NOT_WRITER = auto()           # Caller is not Concierge
    SECTION_LOCKED = auto()       # Section being evicted/migrated
    SIZE_EXCEEDED = auto()        # Would exceed section/tier/total limit
    NEVER_EVICT_VIOLATION = auto()  # Attempted to evict control section
    INVALID_OPERATION = auto()    # Unknown operation type
    PREFLIGHT_FAILED = auto()     # Preflight check failed


@dataclass
class MutationApproval:
    """Result of mutation preflight check"""
    approved: bool
    reason: Optional[RejectionReason] = None
    available_kb: float = 0.0
    message: str = ""


@dataclass
class MutationRequest:
    """Request to mutate SessionState"""
    requester_id: str            # Agent ID requesting mutation
    section: str                 # Target section (e.g., "beliefs_active")
    operation: str               # Operation type (e.g., "add_fact", "update_referent")
    payload: dict                # Operation-specific data
    estimated_size_bytes: int    # Estimated size change


class MutationGuard:
    """
    Enforces single-writer concurrency pattern.

    Invariants:
    1. Only Concierge can write (verified by writer_id)
    2. All mutations pass preflight checks (size, section locks)
    3. Rejected mutations are logged and returned with reason
    4. NEVER EVICT sections cannot be evicted (control)
    """

    NEVER_EVICT_SECTIONS = {"control"}

    def __init__(
        self,
        writer_id: str,           # Concierge agent ID
        size_tracker: "SizeTracker",
        event_bus: "IEventPort"
    ):
        self._writer_id = writer_id
        self._size_tracker = size_tracker
        self._event_bus = event_bus
        self._locked_sections: set[str] = set()

    def preflight(self, request: MutationRequest) -> MutationApproval:
        """
        Preflight check for mutation request.

        Called BEFORE mutation is applied. Returns approval or rejection.
        """
        # Check 1: Verify caller is writer
        if request.requester_id != self._writer_id:
            return MutationApproval(
                approved=False,
                reason=RejectionReason.NOT_WRITER,
                message=f"Only {self._writer_id} can write. Requester: {request.requester_id}"
            )

        # Check 2: Verify section not locked
        if request.section in self._locked_sections:
            return MutationApproval(
                approved=False,
                reason=RejectionReason.SECTION_LOCKED,
                message=f"Section {request.section} is locked for eviction/migration"
            )

        # Check 3: Verify size limits
        section_available = self._size_tracker.get_section_available(request.section)
        if request.estimated_size_bytes > section_available:
            return MutationApproval(
                approved=False,
                reason=RejectionReason.SIZE_EXCEEDED,
                available_kb=section_available / 1024,
                message=f"Mutation would exceed section limit. Available: {section_available}B"
            )

        # Check 4: Verify NEVER_EVICT not violated
        if request.operation == "evict" and request.section in self.NEVER_EVICT_SECTIONS:
            return MutationApproval(
                approved=False,
                reason=RejectionReason.NEVER_EVICT_VIOLATION,
                message=f"Section {request.section} is marked NEVER_EVICT"
            )

        # All checks passed
        return MutationApproval(
            approved=True,
            available_kb=section_available / 1024,
            message="Mutation approved"
        )

    def lock_section(self, section: str) -> None:
        """Lock section for eviction/migration"""
        self._locked_sections.add(section)

    def unlock_section(self, section: str) -> None:
        """Unlock section after eviction/migration"""
        self._locked_sections.discard(section)

    @property
    def writer_id(self) -> str:
        """Get the authorized writer ID"""
        return self._writer_id
```

### Delta Bus for Sub-Agent Write Requests

Sub-agents cannot write directly. They publish mutation requests to the Delta Bus:

```python
# k1/sessionstate/delta_bus.py
"""Delta Bus - Channel for sub-agent mutation requests"""

from dataclasses import dataclass
from typing import Callable, Awaitable
from datetime import datetime


@dataclass
class MutationRequestEvent:
    """Event emitted by sub-agents requesting state mutation"""
    event_type: str = "sessionstate.mutation.requested.v1"
    request_id: str = ""
    requester_agent_id: str = ""
    target_section: str = ""
    operation: str = ""
    payload: dict = None
    timestamp_ms: int = 0
    priority: int = 0  # 0=normal, 1=high, 2=urgent

    def __post_init__(self):
        if self.payload is None:
            self.payload = {}
        if self.timestamp_ms == 0:
            self.timestamp_ms = int(datetime.utcnow().timestamp() * 1000)


@dataclass
class MutationResponseEvent:
    """Event emitted by Concierge after processing mutation request"""
    event_type: str = ""  # approved.v1 or rejected.v1
    request_id: str = ""
    approved: bool = False
    reason: str = ""
    timestamp_ms: int = 0


class DeltaBus:
    """
    Delta Bus for sub-agent mutation requests.

    Flow:
    1. Sub-agent publishes MutationRequestEvent
    2. Concierge receives request
    3. Concierge validates via MutationGuard
    4. Concierge applies mutation (if approved)
    5. Concierge publishes MutationResponseEvent

    Benefits:
    - Sub-agents never hold write locks
    - All mutations serialized through Concierge
    - Full audit trail of mutation requests
    - Async-friendly (no blocking)
    """

    def __init__(self, event_bus: "IEventPort"):
        self._event_bus = event_bus
        self._handlers: list[Callable[[MutationRequestEvent], Awaitable[None]]] = []

    async def request_mutation(
        self,
        requester_agent_id: str,
        target_section: str,
        operation: str,
        payload: dict,
        priority: int = 0
    ) -> str:
        """
        Request a mutation (called by sub-agents).

        Returns request_id for tracking response.
        """
        import uuid
        request_id = str(uuid.uuid4())

        event = MutationRequestEvent(
            request_id=request_id,
            requester_agent_id=requester_agent_id,
            target_section=target_section,
            operation=operation,
            payload=payload,
            priority=priority
        )

        await self._event_bus.publish(
            topic="sessionstate.mutation.requested",
            event=event
        )

        return request_id

    def register_handler(
        self,
        handler: Callable[[MutationRequestEvent], Awaitable[None]]
    ) -> None:
        """Register handler for mutation requests (called by Concierge)"""
        self._handlers.append(handler)

    async def respond(
        self,
        request_id: str,
        approved: bool,
        reason: str = ""
    ) -> None:
        """Publish mutation response (called by Concierge)"""
        event_type = (
            "sessionstate.mutation.approved.v1" if approved
            else "sessionstate.mutation.rejected.v1"
        )

        event = MutationResponseEvent(
            event_type=event_type,
            request_id=request_id,
            approved=approved,
            reason=reason,
            timestamp_ms=int(datetime.utcnow().timestamp() * 1000)
        )

        await self._event_bus.publish(
            topic=f"sessionstate.mutation.{'approved' if approved else 'rejected'}",
            event=event
        )
```

### Concierge as Sole Writer

```python
# k1/concierge/sessionstate_writer.py
"""Concierge SessionState Writer - Sole authority for state mutations"""

from k1.sessionstate.manager import SessionStateManager
from k1.sessionstate.guard import MutationGuard, MutationRequest
from k1.sessionstate.delta_bus import DeltaBus, MutationRequestEvent


class ConciergeSessionStateWriter:
    """
    Concierge's exclusive writer interface to SessionState.

    Responsibilities:
    1. Process mutation requests from Delta Bus
    2. Validate via MutationGuard
    3. Apply approved mutations
    4. Publish mutation responses
    5. Coordinate eviction/migration when needed
    """

    def __init__(
        self,
        concierge_id: str,
        session_state: SessionStateManager,
        delta_bus: DeltaBus
    ):
        self._concierge_id = concierge_id
        self._session_state = session_state
        self._guard = session_state.mutation_guard
        self._delta_bus = delta_bus

        # Verify this Concierge is the authorized writer
        assert self._guard.writer_id == concierge_id, (
            f"Writer mismatch: guard expects {self._guard.writer_id}, "
            f"got {concierge_id}"
        )

        # Register handler for mutation requests
        self._delta_bus.register_handler(self._handle_mutation_request)

    async def _handle_mutation_request(
        self,
        event: MutationRequestEvent
    ) -> None:
        """Handle mutation request from sub-agent"""
        # Create MutationRequest for preflight
        request = MutationRequest(
            requester_id=self._concierge_id,  # Concierge proxies the request
            section=event.target_section,
            operation=event.operation,
            payload=event.payload,
            estimated_size_bytes=len(str(event.payload).encode())
        )

        # Preflight check
        approval = self._guard.preflight(request)

        if approval.approved:
            # Apply mutation
            try:
                await self._apply_mutation(event)
                await self._delta_bus.respond(
                    request_id=event.request_id,
                    approved=True,
                    reason="Mutation applied successfully"
                )
            except Exception as e:
                await self._delta_bus.respond(
                    request_id=event.request_id,
                    approved=False,
                    reason=f"Mutation failed: {e}"
                )
        else:
            # Reject mutation
            await self._delta_bus.respond(
                request_id=event.request_id,
                approved=False,
                reason=approval.message
            )

    async def _apply_mutation(self, event: MutationRequestEvent) -> None:
        """Apply approved mutation to SessionState"""
        section = self._session_state.get_section(event.target_section)

        # Dispatch to section-specific mutation handler
        handler = getattr(section, f"handle_{event.operation}", None)
        if handler:
            await handler(event.payload)
        else:
            raise ValueError(f"Unknown operation: {event.operation}")
```

---

## Consequences

### Positive

1. **No Race Conditions:** Single writer eliminates concurrent write conflicts
2. **Predictable State:** All readers see consistent snapshots
3. **Simple Mental Model:** Easy to reason about who can modify state
4. **Full Audit Trail:** All mutations flow through Delta Bus with logging
5. **Performance:** Lock-free reads (<100μs), single write queue (no contention)

### Negative

1. **Concierge Bottleneck:** All writes serialized through one component
2. **Latency for Sub-Agents:** Mutation requests are async (not immediate)
3. **Complexity:** Delta Bus adds indirection for sub-agent mutations

### Mitigations

| Concern | Mitigation |
|---------|------------|
| Concierge bottleneck | Batch mutations, async processing, priority queue |
| Sub-agent latency | High-priority mutations processed first |
| Complexity | Well-documented patterns, helper libraries |

---

## Performance Targets

| Operation | Target | Rationale |
|-----------|--------|-----------|
| Read (any section) | <100μs | Lock-free, in-memory |
| Write (direct) | <200μs | MutationGuard preflight + apply |
| Mutation request (sub-agent) | <10ms | Delta Bus round-trip |
| Batch mutation (10 ops) | <1ms | Amortized preflight |

---

## Testing Requirements

1. **Unit Tests:**
   - MutationGuard rejects non-writer requests
   - MutationGuard enforces size limits
   - MutationGuard protects NEVER_EVICT sections
   - Delta Bus delivers requests to Concierge

2. **Integration Tests:**
   - Sub-agent mutation request → Concierge approval → state updated
   - Concurrent reads during write (no blocking)
   - Eviction triggered during mutation (proper sequencing)

3. **Stress Tests:**
   - 100 concurrent readers + 1 writer
   - 1000 mutation requests/second throughput

---

## Final Decision

**Single-Writer Concurrency Pattern** is ACCEPTED for SessionState.

### Key Properties

| Property | Value |
|----------|-------|
| **Writer** | Concierge Agent (sole authority) |
| **Readers** | All agents (read-only snapshots) |
| **Mutation Channel** | Delta Bus (sub-agent → Concierge) |
| **Enforcement** | MutationGuard (preflight + validation) |
| **Lock Model** | Lock-free reads, single write queue |

---

## Related ADRs

- **ADR-0017:** SessionState 12-Section Design (defines sections)
- **ADR-0017c:** Control Section (NEVER_EVICT flag)
- **ADR-0086:** Dynamic Agent Creation (dynamic agents are read-only)
- **ADR-0093:** Concierge Agent Pattern (Concierge as coordinator)
- **ADR-0019e:** SessionState Event Schema (mutation events)

---

## Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| MutationGuard | PLANNING | Preflight validation |
| DeltaBus | PLANNING | Mutation request channel |
| ConciergeSessionStateWriter | PLANNING | Writer integration |
| Tests | PLANNING | Unit + integration |
