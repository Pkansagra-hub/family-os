---
adr_number: 0017c
affected_layers:
- layer2_orchestration
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules: []
authors:
- K1 Architecture Team
concerns:
- architecture
- cost
- observability
- performance
- privacy
- reliability
- security
- testing
date_created: '2025-11-03'
date_updated: '2025-11-03'
implementation_date: null
implementation_phase: Phase 1 (Foundation)
implementation_status: FROZEN
propagation:
  affected_adrs:
  - ADR-0002
  - ADR-0004
  - ADR-0005
  - ADR-0017
  affected_tests: []
  triggers:
  - Agent lease acquisition/release protocol changes
  - Orchestrator 3-phase flow state modifications
  - Turn lock timeout enforcement adjustments
  - Lease expiration policy updates
  - Concurrency control mechanism changes
related_adrs:
- ADR-0002
- ADR-0004
- ADR-0005
- ADR-0017
- ADR-0019a
related_contracts:
- k1/contracts/flatbuffers/layer2_state/control_section.fbs
- k1/contracts/flatbuffers/layer3_execution/mcp_message.fbs
- k1/contracts/flatbuffers/layer3_execution/mcp_resource_request.fbs
- k1/contracts/flatbuffers/layer3_execution/mcp_resource_response.fbs
- k1/contracts/flatbuffers/layer3_execution/mcp_tool_discovery.fbs
- k1/contracts/flatbuffers/layer3_execution/model_cache_entry.fbs
- k1/contracts/flatbuffers/layer3_execution/model_request.fbs
- k1/contracts/flatbuffers/layer3_execution/model_response.fbs
- k1/contracts/flatbuffers/layer3_execution/model_stream_chunk.fbs
- k1/contracts/flatbuffers/layer3_execution/stream_chunk.fbs
- k1/contracts/flatbuffers/layer3_execution/stream_config.fbs
related_diagrams: []
research_citations:
- Distributed Lease Management (Chubby Lock Service, Google, 2006)
- Orchestration State Machines (Saga Pattern, 1987)
- Actor Model Supervision (Akka Documentation, 2024)
status: FROZEN
superseded_by: []
supersedes: []
title: Control Section - Active Agent Leases & Flow State
---

# ADR-0017c: Control Section - Active Agent Leases & Flow State

**Status:** ⏳ In Progress (0% - Initial Draft)
**Date:** 2025-10-12
**Authors:** K1 Architecture Team
**Parent ADR:** [ADR-0017 (SessionState 6-Section Design)](0017-sessionstate-6-section-design.md)
**Category:** State Management (Layer 2) - Critical Section
**Related ADRs:**
- [ADR-0002 (Actor Model Agent Isolation)](0002-actor-model-agent-isolation.md)
- [ADR-0004 (Orchestrator 3-Phase Coordination)](0004-orchestrator-3-phase-coordination.md)
- [ADR-0005 (Agent Lifecycle FSM)](0005-agent-lifecycle-fsm.md)

---

## Context

### Problem Statement

The **Control Section** tracks active agent leases, execution flow state, and coordination locks for orchestration:

- **Agent Leases:** Currently active agents (intent_classifier, planner, tool_runner) with expiration
- **Flow State:** Current execution phase (negotiation, selection, execution)
- **Turn Lock:** Prevent concurrent turn execution (critical section)
- **Timeout Enforcement:** Lease expiration, turn timeout detection
- **NEVER Evict:** Control section is critical (never evict during turn)

**Key Challenges:**

1. **Lease Management:** Agents acquire leases, must release on completion or timeout
2. **Flow State Tracking:** 3-phase orchestration (negotiation → selection → execution)
3. **Concurrency Control:** Turn lock prevents multiple turns running simultaneously
4. **Timeout Enforcement:** Detect stuck agents (lease timeout), stuck turns (turn timeout)
5. **Size Budget:** 8-12KB (10-20 active agents + flow state)

### Current Landscape

**Industry Orchestration State Patterns:**

1. **Kubernetes Lease (coordination.k8s.io)**:
   - **Pattern:** Leader election lease with TTL (acquire, renew, release)
   - **Advantage:** Battle-tested, distributed lease management
   - **Disadvantage:** Heavyweight (requires etcd), distributed focus

2. **Saga Pattern (Compensating Transactions)**:
   - **Pattern:** Track saga state (steps, compensations, status)
   - **Advantage:** Rollback support, failure handling
   - **Disadvantage:** Complex (compensating actions), heavyweight

3. **Workflow Engine (Temporal, Airflow)**:
   - **Pattern:** DAG execution state (tasks, dependencies, status)
   - **Advantage:** Rich execution model, retry logic
   - **Disadvantage:** Heavyweight (persistent storage), overkill for K1

4. **Actor Mailbox (Akka, Orleans)**:
   - **Pattern:** Actor state (processing, idle, suspended)
   - **Advantage:** Simple, actor-local state
   - **Disadvantage:** No global flow state, no coordination

### K1 Requirements

**Control Section Properties:**

1. **Agent Lease Tracking:** Store active agents with lease_expires_ms (timeout detection)
2. **Flow State:** Track current phase (negotiation, selection, execution)
3. **Turn Lock:** Boolean flag + turn_id (prevent concurrent turns)
4. **Timeout Detection:** Check lease_expires_ms, turn_timeout_ms every tick
5. **NEVER Evict:** Control section is critical (eviction = coordinator crash)

**Performance Targets (P95):**

| Operation | Target | Rationale |
|-----------|--------|-----------|
| `acquire_lease(agent_id)` | <300μs | Fast lease acquisition |
| `release_lease(agent_id)` | <200μs | Fast lease release |
| `check_timeouts()` | <5ms | Periodic timeout check |
| `set_flow_state(phase)` | <100μs | Fast phase transition |

---

## Decision

We will implement **Control Section** as:

1. **Agent Lease Store:** HashMap with agent_id → AgentLease (state, lease_expires_ms)
2. **Flow State:** Single FlowState object (current_phase, turn_id, started_at_ms, timeout_ms)
3. **Turn Lock:** Boolean flag + turn_id (prevents concurrent turns)
4. **Timeout Checker:** Periodic scan (every 1s) to detect expired leases and turn timeout
5. **NEVER Evict:** Control section exempted from eviction policy

**Data Model:**

```
AgentLease:
  - agent_id: string (e.g., "agent_123")
  - agent_type: string (e.g., "intent_classifier", "planner")
  - state: string (e.g., "ACTIVE", "IDLE", "DRAINING")
  - lease_started_ms: long (when lease acquired)
  - lease_expires_ms: long (timeout threshold)
  - capabilities: [string] (what agent can do)

FlowState:
  - current_phase: string ("negotiation", "selection", "execution", "idle")
  - turn_id: string (current turn identifier)
  - started_at_ms: long (when turn started)
  - timeout_ms: long (turn timeout threshold, e.g., 30s)

ControlSection:
  - agent_leases: [AgentLease] (10-20 agents, ~8KB)
  - flow_state: FlowState (~1KB)
  - turn_lock: bool (prevents concurrent turns)
```

---

## Implementation

### FlatBuffers Schema

```flatbuffers
// k1/session_state/schemas/control_section.fbs
namespace K1.SessionState;

/// Agent lease (currently active agent)
table AgentLease {
  /// Agent identifier
  agent_id: string (required);

  /// Agent type ("intent_classifier", "planner", "tool_runner", etc.)
  agent_type: string (required);

  /// Agent state ("PENDING", "WARMING", "ACTIVE", "IDLE", "DRAINING", "TERMINATED")
  state: string (required);

  /// Lease start timestamp (milliseconds)
  lease_started_ms: long (required);

  /// Lease expiration timestamp (milliseconds)
  lease_expires_ms: long (required);

  /// Agent capabilities (e.g., ["INTENT_CLASSIFICATION", "TOOL_CALL"])
  capabilities: [string];
}

/// Flow state (3-phase orchestration)
table FlowState {
  /// Current phase ("negotiation", "selection", "execution", "idle")
  current_phase: string (required);

  /// Current turn identifier
  turn_id: string;

  /// Turn start timestamp (milliseconds)
  started_at_ms: long;

  /// Turn timeout threshold (milliseconds)
  timeout_ms: long;
}

/// Control section (agent leases, flow state, turn lock)
table ControlSection {
  /// Active agent leases (10-20 agents)
  agent_leases: [AgentLease] (required);

  /// Current flow state
  flow_state: FlowState;

  /// Turn lock (prevents concurrent turns)
  turn_lock: bool;

  /// Total size in bytes
  total_size_bytes: int;

  /// Last update timestamp
  last_updated_ms: long;
}

root_type ControlSection;
```

---

### Python Implementation

```python
# k1/session_state/control_manager.py
"""Control Section Manager - Agent Leases & Flow State

Research:
- Lease Management: "The Part-Time Parliament" (Lamport, 1998) - Paxos leases
- Flow State: "Coordination in Distributed Systems" (Andrews, 1991)
- Timeout Detection: "Failure Detectors" (Chandra & Toueg, 1996)
"""

from typing import Dict, Optional, List
from dataclasses import dataclass
import time
import logging

logger = logging.getLogger(__name__)


@dataclass
class AgentLeaseData:
    """In-memory agent lease representation"""
    agent_id: str
    agent_type: str
    state: str
    lease_started_ms: int
    lease_expires_ms: int
    capabilities: List[str]


@dataclass
class FlowStateData:
    """In-memory flow state representation"""
    current_phase: str
    turn_id: Optional[str]
    started_at_ms: int
    timeout_ms: int


class ControlManager:
    """Manage control section (agent leases, flow state, turn lock)

    Responsibilities:
    - Track active agent leases with timeout
    - Manage 3-phase orchestration flow state
    - Enforce turn lock (prevent concurrent turns)
    - Detect expired leases and turn timeouts

    Performance:
    - acquire_lease: O(1) insert, <300μs P95
    - release_lease: O(1) delete, <200μs P95
    - check_timeouts: O(n) scan, <5ms P95 (n = 10-20)
    - set_flow_state: O(1) update, <100μs P95

    CRITICAL: This section is NEVER evicted (coordinator depends on it)
    """

    DEFAULT_LEASE_DURATION_MS = 30_000  # 30s lease timeout
    DEFAULT_TURN_TIMEOUT_MS = 60_000  # 60s turn timeout

    def __init__(self):
        """Initialize control manager"""
        self.agent_leases: Dict[str, AgentLeaseData] = {}
        self.flow_state = FlowStateData(
            current_phase="idle",
            turn_id=None,
            started_at_ms=0,
            timeout_ms=0,
        )
        self.turn_lock = False

    def acquire_lease(
        self,
        agent_id: str,
        agent_type: str,
        state: str = "ACTIVE",
        capabilities: Optional[List[str]] = None,
        lease_duration_ms: Optional[int] = None,
    ) -> bool:
        """Acquire agent lease

        Args:
            agent_id: Agent identifier
            agent_type: Agent type (e.g., "planner")
            state: Agent state (e.g., "ACTIVE")
            capabilities: Agent capabilities
            lease_duration_ms: Lease duration (default: 30s)

        Returns:
            True if lease acquired, False if already exists

        Performance: <300μs P95
        """
        if agent_id in self.agent_leases:
            logger.warning(f"[ControlManager] Lease already exists for {agent_id}")
            return False

        now_ms = self._get_timestamp_ms()
        duration = lease_duration_ms or self.DEFAULT_LEASE_DURATION_MS

        lease = AgentLeaseData(
            agent_id=agent_id,
            agent_type=agent_type,
            state=state,
            lease_started_ms=now_ms,
            lease_expires_ms=now_ms + duration,
            capabilities=capabilities or [],
        )

        self.agent_leases[agent_id] = lease
        logger.info(f"[ControlManager] Acquired lease: {agent_id} ({agent_type})")
        return True

    def release_lease(self, agent_id: str) -> bool:
        """Release agent lease

        Args:
            agent_id: Agent identifier

        Returns:
            True if lease existed and was released, False otherwise

        Performance: <200μs P95
        """
        if agent_id in self.agent_leases:
            del self.agent_leases[agent_id]
            logger.info(f"[ControlManager] Released lease: {agent_id}")
            return True
        return False

    def renew_lease(self, agent_id: str, lease_duration_ms: Optional[int] = None) -> bool:
        """Renew agent lease (extend expiration)

        Args:
            agent_id: Agent identifier
            lease_duration_ms: New lease duration (default: 30s)

        Returns:
            True if lease renewed, False if lease doesn't exist
        """
        if agent_id not in self.agent_leases:
            return False

        now_ms = self._get_timestamp_ms()
        duration = lease_duration_ms or self.DEFAULT_LEASE_DURATION_MS

        lease = self.agent_leases[agent_id]
        lease.lease_expires_ms = now_ms + duration

        logger.info(f"[ControlManager] Renewed lease: {agent_id}")
        return True

    def get_lease(self, agent_id: str) -> Optional[AgentLeaseData]:
        """Get agent lease

        Args:
            agent_id: Agent identifier

        Returns:
            AgentLeaseData if exists, None otherwise
        """
        return self.agent_leases.get(agent_id)

    def get_all_leases(self) -> List[AgentLeaseData]:
        """Get all active agent leases

        Returns:
            List of all leases
        """
        return list(self.agent_leases.values())

    def check_timeouts(self) -> List[str]:
        """Check for expired leases (call periodically, e.g., every 1s)

        Returns:
            List of agent_ids with expired leases

        Performance: <5ms P95 for 10-20 leases
        """
        now_ms = self._get_timestamp_ms()
        expired = []

        for agent_id, lease in list(self.agent_leases.items()):
            if lease.lease_expires_ms < now_ms:
                logger.warning(
                    f"[ControlManager] Lease expired: {agent_id} "
                    f"(expired_at={lease.lease_expires_ms}, now={now_ms})"
                )
                expired.append(agent_id)
                # Auto-release expired lease
                del self.agent_leases[agent_id]

        return expired

    def set_flow_state(
        self,
        phase: str,
        turn_id: Optional[str] = None,
        timeout_ms: Optional[int] = None,
    ):
        """Set flow state (phase transition)

        Args:
            phase: Phase name ("negotiation", "selection", "execution", "idle")
            turn_id: Turn identifier
            timeout_ms: Turn timeout (default: 60s)

        Performance: <100μs P95
        """
        now_ms = self._get_timestamp_ms()
        timeout = timeout_ms or self.DEFAULT_TURN_TIMEOUT_MS

        self.flow_state = FlowStateData(
            current_phase=phase,
            turn_id=turn_id,
            started_at_ms=now_ms,
            timeout_ms=now_ms + timeout,
        )

        logger.info(f"[ControlManager] Flow state: {phase} (turn_id={turn_id})")

    def get_flow_state(self) -> FlowStateData:
        """Get current flow state

        Returns:
            FlowStateData
        """
        return self.flow_state

    def is_turn_timed_out(self) -> bool:
        """Check if current turn has timed out

        Returns:
            True if turn timed out, False otherwise
        """
        if self.flow_state.current_phase == "idle":
            return False

        now_ms = self._get_timestamp_ms()
        return now_ms > self.flow_state.timeout_ms

    def acquire_turn_lock(self, turn_id: str) -> bool:
        """Acquire turn lock (prevents concurrent turns)

        Args:
            turn_id: Turn identifier

        Returns:
            True if lock acquired, False if already locked
        """
        if self.turn_lock:
            logger.warning(f"[ControlManager] Turn lock already held")
            return False

        self.turn_lock = True
        logger.info(f"[ControlManager] Turn lock acquired: {turn_id}")
        return True

    def release_turn_lock(self):
        """Release turn lock"""
        self.turn_lock = False
        logger.info(f"[ControlManager] Turn lock released")

    def is_turn_locked(self) -> bool:
        """Check if turn is locked

        Returns:
            True if locked, False otherwise
        """
        return self.turn_lock

    def get_size_kb(self) -> int:
        """Estimate section size in KB

        Returns:
            Estimated size in KB
        """
        lease_bytes = sum(
            len(lease.agent_id) + len(lease.agent_type) + 64
            for lease in self.agent_leases.values()
        )
        flow_state_bytes = 128  # Fixed size
        total_bytes = lease_bytes + flow_state_bytes
        return total_bytes // 1024

    def _get_timestamp_ms(self) -> int:
        """Get current timestamp in milliseconds

        Returns:
            Milliseconds since epoch
        """
        return int(time.time() * 1000)
```

---

## Testing Strategy

### Unit Tests (WARD Framework)

```python
# tests/session_state/test_control_manager.py
from ward import test, fixture
import time
from k1.session_state.control_manager import ControlManager

@fixture
def control():
    """Fixture for ControlManager"""
    return ControlManager()

@test("acquire_lease creates lease with expiration")
def _(control=control):
    success = control.acquire_lease("agent_1", "planner", lease_duration_ms=5000)
    assert success is True

    lease = control.get_lease("agent_1")
    assert lease.agent_id == "agent_1"
    assert lease.agent_type == "planner"
    assert lease.lease_expires_ms > 0

@test("check_timeouts detects expired leases")
def _(control=control):
    # Acquire lease with 100ms timeout
    control.acquire_lease("agent_1", "planner", lease_duration_ms=100)

    # Wait for expiration
    time.sleep(0.15)

    # Check timeouts
    expired = control.check_timeouts()
    assert "agent_1" in expired

@test("set_flow_state transitions phase")
def _(control=control):
    control.set_flow_state("negotiation", turn_id="turn_1")

    flow_state = control.get_flow_state()
    assert flow_state.current_phase == "negotiation"
    assert flow_state.turn_id == "turn_1"

@test("turn_lock prevents concurrent turns")
def _(control=control):
    # Acquire lock
    success1 = control.acquire_turn_lock("turn_1")
    assert success1 is True

    # Try to acquire again (should fail)
    success2 = control.acquire_turn_lock("turn_2")
    assert success2 is False

    # Release lock
    control.release_turn_lock()

    # Try to acquire again (should succeed)
    success3 = control.acquire_turn_lock("turn_3")
    assert success3 is True
```

---

## Research Citations

1. **Lamport, L. (1998).** *"The Part-Time Parliament."* ACM TOCS. — Paxos algorithm, lease-based coordination.

2. **Andrews, G. R. (1991).** *"Concurrent Programming: Principles and Practice."* Benjamin/Cummings. — Coordination primitives, locks, semaphores.

3. **Chandra, T. D., & Toueg, S. (1996).** *"Unreliable Failure Detectors for Reliable Distributed Systems."* JACM. — Timeout-based failure detection.

---

## Signatures

**Sub-ADR Owner:** K1 Architecture Team
**Status:** 🔒 **FROZEN**
**Created Date:** 2025-10-12
**Frozen Date:** 2026-02-02

---

## Final Decision (2026-02-02)

**STATUS: FROZEN** - This ADR represents the final architectural decision.

### Control Section - NEVER EVICT Confirmed

| Aspect | Original Design | Final Design | Change |
|--------|----------------|--------------|--------|
| Tier | N/A | HOT CORE | Placed in HOT |
| Budget | 8-12KB | 8KB | Refined |
| Eviction | Critical (never during turn) | **NEVER EVICT** | Elevated to absolute |

### Final Implementation

**control (HOT CORE - 8KB - NEVER EVICT)**:
- Agent leases with expiration tracking
- Flow state (negotiation → selection → execution)
- Turn lock (single-turn concurrency)
- Intent classification results
- Domain and safety band tracking
- Location: `k1/sessionstate/sections/control.py`

### Critical Invariant: NEVER EVICT

The control section has a **NEVER EVICT** flag because:
1. Evicting control during turn = orchestration crash
2. Agent leases must persist for coordination
3. Turn lock prevents race conditions
4. Flow state is required for phase transitions

### Key Design Decisions Confirmed

1. **Agent Lease Tracking**: HashMap with expiration (original design confirmed)
2. **Flow State FSM**: 3-phase coordination (original design confirmed)
3. **Turn Lock**: Boolean + turn_id (original design confirmed)
4. **Timeout Detection**: Periodic check (original design confirmed)

### Performance Targets (Confirmed)

| Operation | Target | Status |
|-----------|--------|--------|
| `acquire_lease(agent_id)` | <300μs | Confirmed |
| `release_lease(agent_id)` | <200μs | Confirmed |
| `check_timeouts()` | <5ms | Confirmed |
| `set_flow_state(phase)` | <100μs | Confirmed |

---

**END OF ADR-0017c**
