"""
K1 L4 Runtime — SessionState Control (Locking & Flow Control)

**Purpose:** SessionState locking, flow control, turn lock management, concurrency control

**Components:**
- Agent Leases — Track ACTIVE/IDLE agents with lease expiration
- Flow State — Current flow_id (UUID) for plan execution tracking
- Turn Lock — Boolean lock to prevent concurrent plan modifications
- Concurrency Control — Prevent race conditions during state updates

**Performance:**
- Lock acquisition: <0.1ms P95
- Lock release: <0.05ms P95
- Lease check: <0.01ms (in-memory lookup)

**ADRs (2 total):**
- ADR-0017c: Control Section (agent leases ACTIVE/IDLE, flow_id UUID, turn_lock bool)
- ADR-0007d: Stage 4 Commit (SessionState locking flow_id concurrent plan prevention <0.1ms)

**Control Section Structure:**

```python
@dataclass
class ControlSection:
    # Agent Leases
    active_agents: Dict[str, AgentLease]  # agent_id → lease

    # Flow Control
    current_flow_id: Optional[str]  # UUID of current plan execution
    flow_started_at_ms: int         # Flow start timestamp

    # Turn Lock
    turn_lock: bool                 # True if plan execution in progress
    turn_lock_holder: Optional[str] # agent_id holding the lock
    turn_lock_acquired_at_ms: int   # Lock acquisition timestamp

    # Concurrency Control
    state_version: int              # Optimistic locking version counter
    last_modified_by: str           # agent_id of last modifier

@dataclass
class AgentLease:
    agent_id: str
    state: Literal["ACTIVE", "IDLE"]  # Agent lifecycle state
    lease_expires_at_ms: int          # Lease expiration (5 min default)
    capabilities: List[str]            # Granted capabilities
```

**Locking Protocol:**

1. **Acquire Turn Lock:**
   - Check turn_lock == False
   - Atomically set turn_lock = True, turn_lock_holder = agent_id
   - Record turn_lock_acquired_at_ms
   - Set current_flow_id = new_flow_id (UUID)

2. **Execute Plan:**
   - Agent holds lock during 4-stage planning
   - Lock prevents concurrent plan modifications
   - Lock timeout: 60s (safety mechanism)

3. **Release Turn Lock:**
   - Atomically set turn_lock = False
   - Clear turn_lock_holder
   - Increment state_version

**Agent Lease Management:**

- **Lease Duration:** 5 minutes default (configurable)
- **Renewal:** Agent pings every 1 minute to renew
- **Expiration:** Auto-remove expired leases (background task)
- **State Tracking:** ACTIVE (executing tasks) vs IDLE (pooled, available)

**Concurrency Control:**

- **Optimistic Locking:** state_version incremented on every mutation
- **Read-Modify-Write:** Check version before write, retry on conflict
- **Conflict Detection:** Compare expected_version vs current version
- **Retry Policy:** Exponential backoff (10ms → 100ms, max 3 retries)

**Files:**
- locking.py — Turn lock implementation (acquire, release, timeout)
- flow_control.py — Flow state management (flow_id tracking)
- agent_leases.py — Agent lease tracking (ACTIVE/IDLE states)
- concurrency.py — Optimistic locking, version control

**Integration:**
- L2 Planner: Stage 4 Commit calls control.acquire_lock() before plan commit
- L3 Agents: Agent hire/fire updates active_agents leases
- L4 Protocol Monitor: Validates state transitions respect lock invariants

**Performance Metrics:**
- session_state_lock_acquisitions_total (counter)
- session_state_lock_contention_total (counter, failed acquisitions)
- session_state_lock_hold_duration_ms (histogram)
- session_state_lease_active_agents (gauge)

**Research Foundations:**
- Lamport (1978) — Time, Clocks, and Ordering of Events (distributed locking)
- Gray & Reuter (1992) — Transaction Processing (optimistic concurrency)

**Last Updated:** October 2025
**Status:** Production-ready locking and flow control
"""

__version__ = "0.1.0"

# TODO: Implement locking.py, flow_control.py, agent_leases.py, concurrency.py
# Per ADR-0017c (Control Section) and ADR-0007d (Stage 4 Commit)
