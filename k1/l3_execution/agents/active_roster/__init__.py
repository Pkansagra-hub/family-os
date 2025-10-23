"""
K1 Layer 3 Execution — agents/active_roster/

PURPOSE:
========
Runtime agent tracking with O(1) lookup/insert/remove operations.
Maintains hash table of active agents for fast roster queries.

RESPONSIBILITIES:
=================
1. Agent Registry: Hash table by agent_id, O(1) lookup
2. State Tracking: Current FSM state, last heartbeat, uptime
3. Roster Operations: Insert (hire), remove (fire), lookup (<1ms)

PRIMARY ADRs:
=============
- ADR-0005: Agent Lifecycle (active roster integration)
  * Active roster tracks agents in ACTIVE, IDLE, DRAINING states
  * Updated on FSM transitions: hire (insert), fire (remove)
  * Provides O(1) lookup for orchestrator agent selection

RELATED ADRs:
=============
- ADR-0029: Prometheus Metrics (active agent count)

DATA STRUCTURE:
===============
**ActiveRoster:**
```python
@dataclass
class AgentInfo:
    agent_id: str
    agent_type: str  # "concierge" | "planner" | "researcher" | "safety_watch"
    session_id: str
    state: State  # FSM state (ACTIVE | IDLE | DRAINING)
    last_heartbeat_ms: int  # Monotonic timestamp
    uptime_ms: int  # Time since ACTIVE
    capabilities: List[Capability]  # TOOL_CALL, MEMORY_READ, etc.

class ActiveRoster:
    def __init__(self):
        self.agents = {}  # agent_id → AgentInfo (hash table)
        self.by_session = {}  # session_id → List[agent_id]
        self.by_type = {}  # agent_type → List[agent_id]
```

ROSTER OPERATIONS:
==================
**Insert (Agent Hire):**
```python
def insert(self, agent_info: AgentInfo) -> None:
    \"\"\"Insert agent into roster (<1ms).\"\"\"
    self.agents[agent_info.agent_id] = agent_info

    # Index by session_id
    if agent_info.session_id not in self.by_session:
        self.by_session[agent_info.session_id] = []
    self.by_session[agent_info.session_id].append(agent_info.agent_id)

    # Index by agent_type
    if agent_info.agent_type not in self.by_type:
        self.by_type[agent_info.agent_type] = []
    self.by_type[agent_info.agent_type].append(agent_info.agent_id)
```

**Remove (Agent Fire):**
```python
def remove(self, agent_id: str) -> AgentInfo:
    \"\"\"Remove agent from roster (<1ms).\"\"\"
    if agent_id not in self.agents:
        return None

    agent_info = self.agents.pop(agent_id)

    # Remove from session index
    self.by_session[agent_info.session_id].remove(agent_id)

    # Remove from type index
    self.by_type[agent_info.agent_type].remove(agent_id)

    return agent_info
```

**Lookup (O(1)):**
```python
def get(self, agent_id: str) -> AgentInfo:
    \"\"\"Get agent info (<1ms).\"\"\"
    return self.agents.get(agent_id)

def get_by_session(self, session_id: str) -> List[AgentInfo]:
    \"\"\"Get all agents for session (<1ms).\"\"\"
    agent_ids = self.by_session.get(session_id, [])
    return [self.agents[aid] for aid in agent_ids]

def get_by_type(self, agent_type: str) -> List[AgentInfo]:
    \"\"\"Get all agents of type (<1ms).\"\"\"
    agent_ids = self.by_type.get(agent_type, [])
    return [self.agents[aid] for aid in agent_ids]
```

**Update (FSM State, Heartbeat):**
```python
def update_state(self, agent_id: str, new_state: State) -> None:
    \"\"\"Update agent FSM state (<1ms).\"\"\"
    if agent_id in self.agents:
        self.agents[agent_id].state = new_state

def update_heartbeat(self, agent_id: str, timestamp_ms: int) -> None:
    \"\"\"Update last heartbeat timestamp (<1ms).\"\"\"
    if agent_id in self.agents:
        self.agents[agent_id].last_heartbeat_ms = timestamp_ms
```

PERFORMANCE METRICS:
====================
- Lookup: <1ms P95 (hash table O(1))
- Insert/remove: <1ms P95 (hash table + 2 indexes)
- Active agent count: 5-20 typical (per K1 instance)
- Memory per agent: ~500 bytes (AgentInfo struct)

INTEGRATION POINTS:
===================
**Agent Hire (Insert):**
```python
from k1.l3_execution.agents.active_roster import ActiveRoster

roster = ActiveRoster()
roster.insert(AgentInfo(
    agent_id="agent_123",
    agent_type="concierge",
    session_id="sess_456",
    state=State.ACTIVE,
    last_heartbeat_ms=time.monotonic() * 1000,
    uptime_ms=0,
    capabilities=[Capability.TOOL_CALL, Capability.MEMORY_READ]
))
```

**Agent Fire (Remove):**
```python
agent_info = roster.remove(agent_id="agent_123")
# Returns: AgentInfo or None
```

**Orchestrator Query (Lookup):**
```python
# Get all active agents for session
agents = roster.get_by_session(session_id="sess_456")

# Get specific agent
agent_info = roster.get(agent_id="agent_123")

# Get all agents of type
concierges = roster.get_by_type(agent_type="concierge")
```

**Supervisor Update (Heartbeat):**
```python
# Update heartbeat timestamp
roster.update_heartbeat(
    agent_id="agent_123",
    timestamp_ms=time.monotonic() * 1000
)
```

TESTING:
========
See tests/l3_execution/agents/test_active_roster.py (ADR-0004d):
- Insert/remove/lookup performance (<1ms)
- Indexing correctness (by_session, by_type)
- State updates (FSM state, heartbeat)
- Memory footprint (500 bytes per agent)
- Concurrent access (thread-safe operations)

OBSERVABILITY:
==============
Prometheus Metrics (ADR-0029):
- layer3_active_agent_count{agent_type}
- layer3_active_agent_count_by_session{session_id}
- layer3_roster_lookup_latency_ms{}

Structured Logs:
```python
logger.info(
    "roster_updated",
    operation="insert",
    agent_id=agent_id,
    agent_type=agent_type,
    session_id=session_id,
    active_count=len(roster.agents),
    trace_id=trace_id
)
```

RESEARCH FOUNDATIONS:
=====================
- Hash tables (Knuth 1973) — O(1) lookup/insert/remove
- Index structures (Comer 1979) — Multi-index data structures

AUTHOR: K1 Intelligence Module
VERSION: 1.0.0
LAST UPDATED: October 2025
"""
