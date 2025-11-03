---
adr_number: 0003a
title: Protocol Definition Language (PDL) Specification
status: COMPLETED
date_created: '2025-10-12'
date_updated: '2025-10-12'
authors:
- K1 Architecture Team
affected_layers:
- layer2_orchestration
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules:
- k1.l5_infrastructure.pdl_parser
- k1.l5_infrastructure.pdl_compiler
- k1.l4_runtime.protocol_monitor
- k1.l5_infrastructure.fsm_executor
- k1.l5_infrastructure.contracts.protocols
concerns:
- architecture
- modularity
- performance
- scalability
- security
- testing
- interoperability
- developer_experience
supersedes:
- ADR-0002
- ADR-0003
- ADR-0003d
- ADR-0006
- ADR-0010
- ADR-0011
superseded_by: []
related_adrs:
- ADR-0002
- ADR-0003
- ADR-0006
- ADR-0010
- ADR-0011
- ADR-0033
- ADR-0034
- ADR-0035
- ADR-0036
- ADR-0037
implementation_status: COMPLETED
implementation_date: '2025-10-12'
implementation_phase: Phase 2 (Runtime)
related_contracts:
- k0/contracts/api/rest/idempotency/24h_retention.yml
- k0/contracts/asyncapi.events.yaml
- k0/contracts/openapi.k0.yaml
- k1/contracts/flatbuffers/layer3_execution/mcp_message.fbs
- k1/contracts/flatbuffers/layer3_execution/mcp_resource_request.fbs
- k1/contracts/flatbuffers/layer3_execution/mcp_resource_response.fbs
- k1/contracts/flatbuffers/layer3_execution/mcp_tool_discovery.fbs
- k1/contracts/flatbuffers/layer3_execution/model_cache_entry.fbs
- k1/contracts/flatbuffers/layer3_execution/model_request.fbs
- k1/contracts/flatbuffers/layer3_execution/model_response.fbs
- k1/contracts/protocols/definitions/clarification.pdl.yml
related_diagrams:
- architecture_diagrams/k1/k1_protocol_monitor_fsms.mmd
- architecture_diagrams/k1/k1_orchestrator_3phase.mmd
- docs/architecture/diagrams/k1/k1_actor_model_messaging.mmd
research_citations:
- Honda, K., Yoshida, N., Carbone, M. (2008). Multiparty Asynchronous Session Types. Journal of the ACM, Vol. 63, No. 1.
- Yoshida, N., Hu, R., Neykova, R., Ng, N. (2013). The Scribble Protocol Language. TOOLS 2013.
- Smith, R. G. (1980). The Contract Net Protocol: High-Level Communication and Control in a Distributed Problem Solver. IEEE Transactions on Computers, Vol. C-29, No. 12.
propagation:
  triggers:
  - Modifying protocol definitions
  - Changing conversation primitives
  - Updating API contracts or schemas
  - Introducing new agent communication patterns
  - Refactoring state machine semantics
  affected_adrs:
  - ADR-0002
  - ADR-0003
  - ADR-0006
  - ADR-0010
  - ADR-0011
  affected_contracts:
  - k0/contracts/api/rest/idempotency/24h_retention.yml
  - k0/contracts/asyncapi.events.yaml
  - k0/contracts/openapi.k0.yaml
  - k1/contracts/flatbuffers/layer3_execution/mcp_message.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_response.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_tool_discovery.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_cache_entry.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_response.fbs
  affected_tests:
  - tests/k1/l5_infrastructure/test_pdl_parser.py
  - tests/k1/l5_infrastructure/test_pdl_compiler.py
  - tests/k1/l4_runtime/test_protocol_monitor.py
  - tests/k1/l5_infrastructure/test_fsm_executor.py
---

# ADR-0003a: Protocol Definition Language (PDL) Specification

**Status:** ✅ **COMPLETED** (2025-10-12)
**Date:** 2025-10-12
**Last Updated:** 2025-10-12
**Deciders:** K1 Architecture Team
**Technical Story:** Define YAML-based DSL for multi-agent protocol specifications
**Parent ADR:** [ADR-0003: MPST Protocol Validation for Agent Communication](0003-mpst-protocol-validation.md)
**Related ADRs:**
- [ADR-0002: Actor Model for Agent Isolation](0002-actor-model-agent-isolation.md)
- [ADR-0006: 3-Phase Orchestration & Contract Net Protocol](0006-3-phase-orchestration-contract-net.md)
- [ADR-0011: FlatBuffers for All Contracts](0011-flatbuffers-serialization.md)

---

## Executive Summary

K1 Intelligence Module uses a **Protocol Definition Language (PDL)** to declaratively specify multi-agent conversation protocols. PDL is a **YAML-based DSL** designed for readability (not academic Scribble syntax) with conversation-native primitives (clarification, barge-in, grounding).

**Core Features:**
1. **YAML Syntax:** States, transitions, timeouts, guards, violations defined in readable YAML
2. **State Machine Semantics:** Initial/terminal states, message cardinality (0..1, 1, 0..*, 1..*)
3. **Compiler Design:** PDL → FSM compilation, pre-compiled to FlatBuffers for <2ms runtime lookup
4. **Deadlock Detection:** Static analysis of state graph at compile-time
5. **Timeout Policies:** Progress guarantees with fallback transitions
6. **Conversation Primitives:** Native support for clarification loops, barge-in interrupts, grounding commits

**Performance Targets:**
- PDL compilation (startup): <100ms per protocol
- FSM state lookup (runtime): <1ms P95
- Validation latency (runtime): <2ms P95 (after pre-compilation)

**Key Principle:** PDL is designed for **developers, not academics**. Team can write protocols without MPST theory PhD.

---

## Context

### The Problem

**K1 Agent Landscape:**
- **58 agents:** 4 AI agents (Concierge, Planner, Researcher, Safety Watch) + 54 pure agents (Orchestrator, Supervisor, Router, etc.)
- **6 core protocols:** Agent Hire, Task Execution, Clarification, Barge-In, Tool Call, Saga Rollback
- **Complex conversations:** Multi-step protocols with timeouts, nested protocols, interrupt handling

**Without PDL:**
- ❌ **No formal specification:** Protocols scattered in code, undocumented
- ❌ **No validation:** Invalid message sequences not detected until runtime failures
- ❌ **No deadlock detection:** Circular waits cause agent hangs
- ❌ **No timeout guarantees:** Conversations stuck waiting for messages that never arrive
- ❌ **Hard to reason about:** Cannot prove protocol correctness

**Traditional Approaches:**

1. **Scribble (Academic MPST):**
   - ✅ Formal guarantees (deadlock freedom, progress)
   - ❌ Academic syntax (requires MPST theory background)
   - ❌ Global/local projection complexity (2× code)
   - ❌ No conversation primitives (must encode manually)
   - ❌ Python support weak

2. **State Machine Libraries (Python Transitions):**
   - ✅ Python-native, simple API
   - ❌ No protocol theory (just FSMs, no MPST guarantees)
   - ❌ No deadlock detection
   - ❌ No timeout policies
   - ❌ Code duplication (each protocol = separate class)

3. **No Formal Specification:**
   - ✅ Zero overhead
   - ❌ Production failures inevitable
   - ❌ Debugging nightmare (why did agent hang?)
   - ❌ No guarantees (deadlocks possible)

**Requirements:**

- **Readable:** YAML-based, developers can read/write without MPST PhD
- **Conversation-native:** Clarification, barge-in, grounding as first-class primitives
- **Fast:** Pre-compiled FSMs for <2ms validation
- **Safe:** Deadlock detection at compile-time, timeout policies for progress
- **Actor-centric:** Protocols validate Actor message sequences (not LLM calls)
- **AI-aware:** Distinguish protocol timeouts (500ms) from AI agent LLM timeouts (5000ms)

---

## Decision

We adopt a **custom Protocol Definition Language (PDL)** with YAML syntax, pre-compiled to FlatBuffers FSM tables for <2ms runtime validation.

### **Decision Matrix**

**Four alternatives evaluated for protocol specification:**

| Alternative | Readability | Conversation Primitives | Deadlock Detection | Compile Time | Runtime Cost | Team Fit |
|-------------|-------------|-------------------------|---------------------|--------------|--------------|----------|
| **1. Scribble/MPST** | ❌ Academic | ❌ Manual | ✅ Yes | ⚠️ Complex | ⚠️ 5-10ms | ❌ 4/10 |
| **2. Python Transitions** | ✅ Code | ❌ Manual | ❌ No | ✅ Fast | ✅ <1ms | ⚠️ 6/10 |
| **3. Custom PDL (YAML)** | ✅ Declarative | ✅ Native | ✅ Yes | ✅ <100ms | ✅ <2ms | ✅ **9/10** |
| **4. No Specification** | ✅ Zero | N/A | ❌ No | N/A | ✅ 0ms | ❌ 2/10 |

**Decision: Alternative 3 (Custom PDL) selected.**

**Key Decision Factors:**

1. **YAML Readability:** Team can read/write protocols without MPST theory (vs Scribble's academic syntax)
2. **Conversation Primitives:** Native `clarification`, `barge_in`, `grounding` primitives (vs manual encoding)
3. **Pre-compiled FSMs:** Compile PDL → FlatBuffers at startup for <2ms runtime validation (vs 5-10ms Scribble interpretation)
4. **Deadlock Detection:** Static analysis of state graph (vs Python Transitions no detection)
5. **AI Agent Integration:** Distinguish protocol timeout (500ms) from AI agent LLM timeout (5000ms) in YAML

**Rejection Rationale:**

- **Alternative 1 (Scribble):** Too academic, global/local projection overhead, weak Python support
- **Alternative 2 (Python Transitions):** No protocol theory, no deadlock detection, code duplication
- **Alternative 4 (No Specification):** Unacceptable - 58 agents require formal protocol guarantees

---

## PDL Language Specification

### 1. **YAML Schema Overview**

**Top-Level Structure:**

```yaml
protocol:
  name: "agent_hire"                  # Protocol identifier (snake_case)
  version: "1.0"                      # Semantic versioning
  description: "Agent hiring protocol with negotiation"

  initial_state: "start"              # Entry point (REQUIRED)
  terminal_states: ["hired", "rejected", "timeout"]  # Exit states (REQUIRED)

  states: [...]                       # FSM states (REQUIRED)
  transitions: [...]                  # FSM transitions (REQUIRED)
  timeouts: [...]                     # Timeout policies (OPTIONAL)
  violations: [...]                   # Violation handling (OPTIONAL)
  roles: [...]                        # Role definitions (OPTIONAL, see ADR-0003d)
  messages: [...]                     # Message schemas (OPTIONAL, see ADR-0003d)
```

---

### 2. **State Definitions**

**State Schema:**

```yaml
states:
  - name: "start"                     # State ID (snake_case)
    type: "entry"                     # entry | interaction | decision | exit
    description: "Protocol entry point"  # Human-readable description
    timeout_ms: null                  # Timeout in milliseconds (null = no timeout)
    llm_aware: false                  # true = allows AI agent LLM calls in this state

  - name: "negotiation"
    type: "interaction"               # Multi-agent interaction
    description: "Collect proposals from agents"
    timeout_ms: 500                   # 500ms to collect all proposals
    llm_aware: true                   # AI agents may call LLMs during this state

  - name: "selection"
    type: "decision"                  # Orchestrator decision point
    description: "Score proposals, select winner"
    timeout_ms: 100                   # 100ms for deterministic selection
    llm_aware: false                  # Pure actor logic, no LLM

  - name: "hired"
    type: "exit"                      # Terminal state (success)
    description: "Agent successfully hired"
    timeout_ms: null

  - name: "timeout"
    type: "exit"                      # Terminal state (timeout)
    description: "Negotiation timed out"
    timeout_ms: null
```

**State Types:**

| Type          | Purpose                          | Timeout Required? | Example            |
|---------------|----------------------------------|-------------------|--------------------|
| `entry`       | Protocol start state             | No                | `start`            |
| `interaction` | Multi-agent message exchange     | Yes (recommended) | `negotiation`      |
| `decision`    | Orchestrator decision point      | Yes (recommended) | `selection`        |
| `exit`        | Terminal state (success/failure) | No                | `hired`, `timeout` |

**llm_aware Flag:**

- `llm_aware: true` — State allows AI agents to call Model Hub internally (LLM reasoning)
  - Example: Planner generates plan in `planning` state (5000ms timeout)
  - Protocol timeout = max time to **receive next message** (not LLM call duration)
- `llm_aware: false` — State expects only pure actor logic (deterministic, <100ms)
  - Example: Orchestrator scores proposals in `selection` state (no LLM)

**CRITICAL:** `llm_aware` does NOT mean protocol validates LLM calls. It's documentation for timeout tuning (LLM-aware states need longer timeouts).

---

### 3. **Transition Definitions**

**Transition Schema:**

```yaml
transitions:
  - from: "start"                     # Source state (REQUIRED)
    to: "negotiation"                 # Destination state (REQUIRED)
    message: "HireRequest"            # Message type that triggers transition (REQUIRED)
    sender: "orchestrator"            # Sender agent ID or role (REQUIRED)
    receivers: ["*"]                  # Receiver agent IDs or ["*"] for broadcast (REQUIRED)
    cardinality: "1"                  # Message cardinality (OPTIONAL, default: "1")
    condition: null                   # Guard condition (OPTIONAL)
    trigger: null                     # Auto-trigger type (OPTIONAL: timeout | system)

  - from: "negotiation"
    to: "negotiation"                 # Self-loop (multiple proposals)
    message: "Proposal"
    sender: "agent"                   # Any agent (role-based)
    receivers: ["orchestrator"]
    cardinality: "0..*"               # Zero or more proposals
    condition: null
    trigger: null

  - from: "negotiation"
    to: "selection"
    message: "ProposalsClosed"
    sender: "orchestrator"
    receivers: []                     # Internal transition (no recipients)
    cardinality: "1"
    condition: null
    trigger: "timeout"                # Auto-triggered after 500ms timeout

  - from: "selection"
    to: "hired"
    message: "HireApproval"
    sender: "orchestrator"
    receivers: ["agent"]
    cardinality: "1"
    condition: "score > threshold"    # Guard: only if proposal score high enough
    trigger: null
```

**Message Cardinality:**

| Cardinality | Meaning                     | Example                          |
|-------------|----------------------------|----------------------------------|
| `0..1`      | Zero or one message        | Optional clarification request   |
| `1`         | Exactly one message        | Hire approval (default)          |
| `0..*`      | Zero or more messages      | Multiple agent proposals         |
| `1..*`      | One or more messages       | At least one proposal required   |

**Senders & Receivers:**

- **Sender:**
  - Agent ID: `"orchestrator"`, `"planner_agent"` (specific agent)
  - Role: `"agent"` (any agent with this role)
  - System: `"system"` (system-triggered, e.g., timeout)

- **Receivers:**
  - Agent ID list: `["orchestrator"]`, `["planner_agent", "researcher_agent"]`
  - Broadcast: `["*"]` (all agents receive)
  - Empty: `[]` (internal transition, no message sent)

**Guard Conditions:**

- Optional boolean expressions evaluated at runtime
- Syntax: Simple comparison operators (`>`, `<`, `==`, `!=`, `>=`, `<=`)
- Variables: Protocol-scoped (e.g., `score`, `confidence`, `retry_count`)
- Example: `"score > threshold"`, `"retry_count < 3"`, `"confidence >= 0.8"`

**Triggers:**

- `null` — Normal message-triggered transition (default)
- `"timeout"` — Auto-triggered when state timeout expires
- `"system"` — System-triggered (e.g., supervisor crash detection)

---

### 4. **Timeout Policies**

**Timeout Schema:**

```yaml
timeouts:
  - state: "negotiation"              # State name (REQUIRED)
    action: "ProposalsClosed"         # Message to auto-send on timeout (REQUIRED)
    fallback_state: "selection"       # Alternative: direct state transition
    log: true                         # Log timeout event (default: true)

  - state: "selection"
    action: "HireRejection"           # Reject if selection takes >100ms
    fallback_state: "rejected"
    log: true
```

**Timeout Semantics:**

1. **State Timeout:** Defined in `states[].timeout_ms` (e.g., 500ms for `negotiation`)
2. **Timeout Action:** Defined in `timeouts[].action` (message to auto-send)
3. **Fallback State:** Optional direct state transition without message

**Example: Negotiation Timeout Flow**

```
1. Enter "negotiation" state at T=0
2. Wait for "Proposal" messages
3. If T=500ms and no ProposalsClosed received:
   → Protocol Monitor auto-sends ProposalsClosed (system message)
   → Transition to "selection" state
```

**Progress Guarantee:** Every non-terminal state **MUST** have a timeout policy. This ensures protocols always reach terminal states (no infinite waits).

---

### 5. **Violation Handling**

**Violation Schema:**

```yaml
violations:
  - type: "unexpected_message"        # Violation type (REQUIRED)
    action: "block"                   # block | warn | dlq | repair (REQUIRED)
    log: true                         # Log violation (default: true)
    metrics: true                     # Emit metrics (default: true)

  - type: "timeout"
    action: "fallback"                # Trigger timeout transition
    log: true
    metrics: true

  - type: "deadlock"
    action: "abort"                   # Abort protocol, cleanup FSM
    log: true
    metrics: true

  - type: "role_mismatch"             # Sender role doesn't match expected (see ADR-0003d)
    action: "block"
    log: true
    metrics: true
```

**Violation Types:**

| Type                  | Cause                                      | Example                                      |
|-----------------------|--------------------------------------------|----------------------------------------------|
| `unexpected_message`  | Message received in wrong state            | `Proposal` sent after `selection` state      |
| `invalid_sender`      | Sender not allowed to send this message    | Agent sends `HireApproval` (only orchestrator) |
| `invalid_cardinality` | Wrong number of messages                   | Two `HireApproval` messages (cardinality: 1) |
| `timeout`             | State timeout expired                      | No `Proposal` received within 500ms          |
| `deadlock`            | Circular wait detected                     | A waits for B, B waits for A                 |
| `role_mismatch`       | Sender role doesn't match expected role    | Agent with role "agent" sends as "orchestrator" |
| `schema_invalid`      | Message schema validation failed           | FlatBuffers schema mismatch                  |

**Violation Actions:**

| Action     | Behavior                                                  | Use Case                          |
|------------|-----------------------------------------------------------|-----------------------------------|
| `block`    | Drop message, log to DLQ, do NOT transition               | Invalid messages (default)        |
| `warn`     | Log violation, deliver message anyway (degraded mode)     | Development/debugging             |
| `dlq`      | Log to Protocol DLQ for manual review                     | Audit trail, forensics            |
| `repair`   | Auto-inject timeout transition or orchestrator callback   | Graceful degradation              |
| `fallback` | Trigger timeout fallback transition                       | Timeout handling                  |
| `abort`    | Abort protocol, cleanup FSM, log error                    | Unrecoverable errors (deadlock)   |

---

### 6. **Role Definitions (Optional)**

**Role Schema** (see ADR-0003d for full details):

```yaml
roles:
  - name: "orchestrator"              # Role name (REQUIRED)
    capabilities: ["hire", "fire", "score"]  # Allowed operations (OPTIONAL)

  - name: "agent"
    capabilities: ["propose", "accept", "reject"]

  - name: "system"
    capabilities: ["timeout", "monitor", "abort"]
```

**Purpose:** Define roles for role-based access control (RBAC). Agents have signed capability leases with roles. Protocol Monitor verifies `sender_role` matches expected role for message type.

**Cross-Reference:** ADR-0003d (Role Attestation & Capability Verification), ADR-0010 (Capability-Based Security)

---

### 7. **Message Definitions (Optional)**

**Message Schema** (see ADR-0003d for full details):

```yaml
messages:
  HireRequest:
    sender_role: "orchestrator"       # Only orchestrator can send
    receivers: ["*"]                  # Broadcast to all agents
    schema: "HireRequest.fbs"         # FlatBuffers schema file
    priority: 2                       # Priority (0=background, 3=urgent)

  Proposal:
    sender_role: "agent"              # Only agents can send
    receivers: ["orchestrator"]
    schema: "Proposal.fbs"
    priority: 2
```

**Purpose:** Bind message types to FlatBuffers schemas and role restrictions. Enables schema validation + role-based security.

**Cross-Reference:** ADR-0011 (FlatBuffers Serialization), ADR-0003d (Role Attestation)

---

## Compiler Design

### **Compilation Pipeline**

```
┌────────────────────────────────────────────────────────────────┐
│                   PDL Compilation Pipeline                     │
│                                                                │
│  1. YAML Parse                                                 │
│      ↓                                                         │
│  2. Syntax Validation (states, transitions, timeouts)          │
│      ↓                                                         │
│  3. Semantic Validation (initial state exists, terminal reachable) │
│      ↓                                                         │
│  4. Deadlock Detection (state graph analysis, circular waits)  │
│      ↓                                                         │
│  5. FSM Code Generation (transition table, timeout policies)   │
│      ↓                                                         │
│  6. FlatBuffers Serialization (pre-compiled FSM → .fbs binary) │
│      ↓                                                         │
│  7. Runtime Load (FSM.fbs → in-memory lookup table)            │
└────────────────────────────────────────────────────────────────┘
```

### **1. YAML Parse**

**Tool:** PyYAML (Python standard library)

```python
import yaml

def parse_pdl(file_path: str) -> dict:
    """Parse PDL YAML file"""
    with open(file_path, 'r') as f:
        pdl = yaml.safe_load(f)
    return pdl
```

**Output:** Python dictionary with protocol definition

---

### **2. Syntax Validation**

**Checks:**
- `protocol.name` exists (string, snake_case)
- `protocol.version` exists (semantic version: "1.0", "1.1.2")
- `protocol.initial_state` exists and references valid state
- `protocol.terminal_states` exists (list of state names)
- All `states` have: `name`, `type`, `description`
- All `transitions` have: `from`, `to`, `message`, `sender`, `receivers`

**Example Validator:**

```python
def validate_syntax(pdl: dict) -> List[str]:
    """Validate PDL syntax, return list of errors"""
    errors = []

    # Check required fields
    if 'name' not in pdl['protocol']:
        errors.append("Missing protocol.name")

    if 'initial_state' not in pdl['protocol']:
        errors.append("Missing protocol.initial_state")

    # Check states
    state_names = {s['name'] for s in pdl['protocol']['states']}
    if pdl['protocol']['initial_state'] not in state_names:
        errors.append(f"initial_state '{pdl['protocol']['initial_state']}' not in states")

    # Check transitions reference valid states
    for t in pdl['protocol']['transitions']:
        if t['from'] not in state_names:
            errors.append(f"Transition 'from' state '{t['from']}' not in states")
        if t['to'] not in state_names:
            errors.append(f"Transition 'to' state '{t['to']}' not in states")

    return errors
```

---

### **3. Semantic Validation**

**Checks:**
- All terminal states are reachable from initial state (BFS/DFS)
- No orphaned states (unreachable from initial state)
- Every non-terminal state has outgoing transitions
- Cardinality constraints are valid (0..1, 1, 0..*, 1..*)
- Guard conditions use valid variables
- Timeout actions reference valid messages or states

**Example: Reachability Check**

```python
def check_reachability(pdl: dict) -> List[str]:
    """Check all terminal states reachable from initial state"""
    errors = []

    # Build adjacency list
    graph = defaultdict(list)
    for t in pdl['protocol']['transitions']:
        graph[t['from']].append(t['to'])

    # BFS from initial state
    initial = pdl['protocol']['initial_state']
    visited = set()
    queue = [initial]

    while queue:
        state = queue.pop(0)
        if state in visited:
            continue
        visited.add(state)
        queue.extend(graph[state])

    # Check all terminal states reachable
    for terminal in pdl['protocol']['terminal_states']:
        if terminal not in visited:
            errors.append(f"Terminal state '{terminal}' not reachable from initial state")

    return errors
```

---

### **4. Deadlock Detection**

**Algorithm:** Detect circular waits in state graph

**Definition:** Deadlock occurs when:
- State A waits for message M1 from agent B
- State B waits for message M2 from agent A
- No timeout policies to break cycle

**Detection Strategy:**

1. **Build dependency graph:** State → {expected messages from agents}
2. **Detect cycles:** Use Tarjan's strongly connected components algorithm
3. **Check timeout escape:** For each cycle, verify timeout policy exists

**Example:**

```python
def detect_deadlock(pdl: dict) -> List[str]:
    """Detect circular waits (deadlocks) in protocol"""
    errors = []

    # Build dependency graph: state → {expected senders}
    dependencies = defaultdict(set)
    for t in pdl['protocol']['transitions']:
        if t['trigger'] is None:  # Only message-triggered transitions
            dependencies[t['from']].add(t['sender'])

    # Detect cycles using DFS
    visited = set()
    rec_stack = set()

    def dfs(state, path):
        visited.add(state)
        rec_stack.add(state)

        for next_state in get_next_states(state):
            if next_state not in visited:
                if dfs(next_state, path + [next_state]):
                    return True
            elif next_state in rec_stack:
                # Cycle detected
                cycle = path[path.index(next_state):] + [next_state]
                if not has_timeout_escape(cycle):
                    errors.append(f"Deadlock detected: {' → '.join(cycle)}")
                return True

        rec_stack.remove(state)
        return False

    dfs(pdl['protocol']['initial_state'], [])
    return errors
```

**Timeout Escape:** Protocol has timeout policy for at least one state in cycle (breaks deadlock).

---

### **5. FSM Code Generation**

**Output:** Transition table for O(1) runtime lookups

**FSM Representation:**

```python
@dataclass
class FSM:
    """Compiled protocol FSM"""
    protocol_name: str
    version: str
    initial_state: str
    terminal_states: Set[str]

    # Transition table: (state, message) → transition
    transitions: Dict[Tuple[str, str], Transition]

    # State metadata: state → state_info
    states: Dict[str, StateInfo]

    # Timeout policies: state → timeout_action
    timeouts: Dict[str, TimeoutPolicy]

@dataclass
class Transition:
    from_state: str
    to_state: str
    message: str
    sender: str
    receivers: List[str]
    cardinality: str
    condition: Optional[str]
    trigger: Optional[str]

@dataclass
class StateInfo:
    name: str
    type: str
    description: str
    timeout_ms: Optional[int]
    llm_aware: bool

@dataclass
class TimeoutPolicy:
    state: str
    action: str
    fallback_state: Optional[str]
```

**Compilation Function:**

```python
def compile_pdl_to_fsm(pdl: dict) -> FSM:
    """Compile PDL to FSM data structure"""

    # Build transition table
    transitions = {}
    for t in pdl['protocol']['transitions']:
        key = (t['from'], t['message'])
        transitions[key] = Transition(
            from_state=t['from'],
            to_state=t['to'],
            message=t['message'],
            sender=t['sender'],
            receivers=t['receivers'],
            cardinality=t.get('cardinality', '1'),
            condition=t.get('condition'),
            trigger=t.get('trigger')
        )

    # Build state metadata
    states = {}
    for s in pdl['protocol']['states']:
        states[s['name']] = StateInfo(
            name=s['name'],
            type=s['type'],
            description=s['description'],
            timeout_ms=s.get('timeout_ms'),
            llm_aware=s.get('llm_aware', False)
        )

    # Build timeout policies
    timeouts = {}
    for tp in pdl['protocol'].get('timeouts', []):
        timeouts[tp['state']] = TimeoutPolicy(
            state=tp['state'],
            action=tp['action'],
            fallback_state=tp.get('fallback_state')
        )

    return FSM(
        protocol_name=pdl['protocol']['name'],
        version=pdl['protocol']['version'],
        initial_state=pdl['protocol']['initial_state'],
        terminal_states=set(pdl['protocol']['terminal_states']),
        transitions=transitions,
        states=states,
        timeouts=timeouts
    )
```

---

### **6. FlatBuffers Serialization**

**Purpose:** Pre-compile FSM to binary format for fast runtime loading (<100ms startup, <1ms lookup)

**FlatBuffers Schema:**

```fbs
// k1/runtime/protocol_monitor/schemas/fsm.fbs

namespace K1.ProtocolMonitor;

table FSM {
  protocol_name: string;
  version: string;
  initial_state: string;
  terminal_states: [string];
  states: [StateInfo];
  transitions: [Transition];
  timeouts: [TimeoutPolicy];
}

table StateInfo {
  name: string;
  type: string;  // entry | interaction | decision | exit
  description: string;
  timeout_ms: int = null;
  llm_aware: bool = false;
}

table Transition {
  from_state: string;
  to_state: string;
  message: string;
  sender: string;
  receivers: [string];
  cardinality: string = "1";
  condition: string = null;
  trigger: string = null;  // timeout | system | null
}

table TimeoutPolicy {
  state: string;
  action: string;
  fallback_state: string = null;
}
```

**Serialization:**

```python
import flatbuffers
from k1.runtime.protocol_monitor.schemas import FSM as FSMSchema

def serialize_fsm(fsm: FSM) -> bytes:
    """Serialize FSM to FlatBuffers binary"""
    builder = flatbuffers.Builder(1024)

    # Serialize states
    state_offsets = []
    for s in fsm.states.values():
        name_offset = builder.CreateString(s.name)
        type_offset = builder.CreateString(s.type)
        desc_offset = builder.CreateString(s.description)

        FSMSchema.StateInfoStart(builder)
        FSMSchema.StateInfoAddName(builder, name_offset)
        FSMSchema.StateInfoAddType(builder, type_offset)
        FSMSchema.StateInfoAddDescription(builder, desc_offset)
        FSMSchema.StateInfoAddTimeoutMs(builder, s.timeout_ms or 0)
        FSMSchema.StateInfoAddLlmAware(builder, s.llm_aware)
        state_offsets.append(FSMSchema.StateInfoEnd(builder))

    # ... serialize transitions, timeouts similarly ...

    # Build FSM
    protocol_name_offset = builder.CreateString(fsm.protocol_name)
    version_offset = builder.CreateString(fsm.version)

    FSMSchema.FSMStart(builder)
    FSMSchema.FSMAddProtocolName(builder, protocol_name_offset)
    FSMSchema.FSMAddVersion(builder, version_offset)
    # ... add states, transitions, timeouts ...
    fsm_offset = FSMSchema.FSMEnd(builder)

    builder.Finish(fsm_offset)
    return bytes(builder.Output())
```

**Output:** Binary file `agent_hire.fsm.fbs` (~2-5 KB per protocol)

---

### **7. Runtime Load**

**Purpose:** Load pre-compiled FSM binary at startup, build in-memory lookup tables

```python
class ProtocolMonitor:
    """Runtime FSM executor"""

    def __init__(self):
        self.protocols: Dict[str, FSM] = {}  # protocol_name → FSM

    def load_protocol(self, fsm_binary: bytes):
        """Load pre-compiled FSM from FlatBuffers binary"""
        fsm_schema = FSMSchema.FSM.GetRootAsFSM(fsm_binary, 0)

        # Build transition lookup table: O(1) access
        transitions = {}
        for i in range(fsm_schema.TransitionsLength()):
            t = fsm_schema.Transitions(i)
            key = (t.FromState().decode(), t.Message().decode())
            transitions[key] = Transition(
                from_state=t.FromState().decode(),
                to_state=t.ToState().decode(),
                message=t.Message().decode(),
                sender=t.Sender().decode(),
                receivers=[t.Receivers(j).decode() for j in range(t.ReceiversLength())],
                cardinality=t.Cardinality().decode(),
                condition=t.Condition().decode() if t.Condition() else None,
                trigger=t.Trigger().decode() if t.Trigger() else None
            )
            transitions[key] = t

        # Store FSM
        fsm = FSM(
            protocol_name=fsm_schema.ProtocolName().decode(),
            version=fsm_schema.Version().decode(),
            initial_state=fsm_schema.InitialState().decode(),
            terminal_states={fsm_schema.TerminalStates(i).decode()
                           for i in range(fsm_schema.TerminalStatesLength())},
            transitions=transitions,
            states={...},  # Build from fsm_schema.States()
            timeouts={...}  # Build from fsm_schema.Timeouts()
        )

        self.protocols[fsm.protocol_name] = fsm
```

**Performance:**
- Load time: <100ms per protocol (5-6 protocols = 500ms startup overhead)
- Lookup time: <1ms P95 (hash table O(1) access)
- Memory: ~5-10 KB per protocol (58 agents × 5 protocols = 300 KB total)

---

## Example: Agent Hire Protocol (Complete PDL)

**File:** `k1/protocols/hire.pdl.yml`

```yaml
# Agent Hire Protocol
# Purpose: Hire agent with negotiation and selection
# States: 6 (start, negotiation, selection, hired, rejected, timeout)
# Transitions: 8
# Research: Contract Net Protocol (Smith 1980), MPST (Honda 2008)

protocol:
  name: "agent_hire"
  version: "1.0"
  description: "Hire agent with negotiation, scoring, and selection"

  initial_state: "start"
  terminal_states: ["hired", "rejected", "timeout"]

  # ===== FSM States =====
  states:
    - name: "start"
      type: "entry"
      description: "Protocol entry point"
      timeout_ms: null
      llm_aware: false

    - name: "negotiation"
      type: "interaction"
      description: "Collect proposals from agents (broadcast HireRequest)"
      timeout_ms: 500         # 500ms to collect all proposals
      llm_aware: true         # AI agents may call LLMs to generate proposals

    - name: "selection"
      type: "decision"
      description: "Score proposals, select winner (deterministic)"
      timeout_ms: 100         # 100ms for scoring logic
      llm_aware: false        # Pure actor logic, no LLM

    - name: "hired"
      type: "exit"
      description: "Agent successfully hired"
      timeout_ms: null

    - name: "rejected"
      type: "exit"
      description: "No suitable agent found"
      timeout_ms: null

    - name: "timeout"
      type: "exit"
      description: "Negotiation timed out (no proposals received)"
      timeout_ms: null

  # ===== FSM Transitions =====
  transitions:
    # Transition 1: Start → Negotiation
    - from: "start"
      to: "negotiation"
      message: "HireRequest"
      sender: "orchestrator"
      receivers: ["*"]        # Broadcast to all agents
      cardinality: "1"
      condition: null
      trigger: null

    # Transition 2: Negotiation → Negotiation (self-loop for multiple proposals)
    - from: "negotiation"
      to: "negotiation"
      message: "Proposal"
      sender: "agent"         # Any agent can send proposal
      receivers: ["orchestrator"]
      cardinality: "0..*"     # Zero or more proposals
      condition: null
      trigger: null

    # Transition 3: Negotiation → Selection (timeout auto-close)
    - from: "negotiation"
      to: "selection"
      message: "ProposalsClosed"
      sender: "system"        # System-triggered on timeout
      receivers: []
      cardinality: "1"
      condition: null
      trigger: "timeout"      # Auto-triggered after 500ms

    # Transition 4: Selection → Hired (high score)
    - from: "selection"
      to: "hired"
      message: "HireApproval"
      sender: "orchestrator"
      receivers: ["agent"]    # Winning agent
      cardinality: "1"
      condition: "score > threshold"  # Guard: only if score high enough
      trigger: null

    # Transition 5: Selection → Rejected (low score)
    - from: "selection"
      to: "rejected"
      message: "HireRejection"
      sender: "orchestrator"
      receivers: ["agent"]    # Rejected agent(s)
      cardinality: "1"
      condition: "score <= threshold"
      trigger: null

    # Transition 6: Negotiation → Timeout (no proposals)
    - from: "negotiation"
      to: "timeout"
      message: "Timeout"
      sender: "system"
      receivers: []
      cardinality: "1"
      condition: "proposal_count == 0"  # Guard: no proposals received
      trigger: "timeout"

    # Transition 7: Selection → Rejected (selection timeout)
    - from: "selection"
      to: "rejected"
      message: "SelectionTimeout"
      sender: "system"
      receivers: []
      cardinality: "1"
      condition: null
      trigger: "timeout"      # Auto-reject if selection takes >100ms

    # Transition 8: Selection → Timeout (no valid proposals)
    - from: "selection"
      to: "timeout"
      message: "NoValidProposals"
      sender: "orchestrator"
      receivers: []
      cardinality: "1"
      condition: "all_scores <= threshold"
      trigger: null

  # ===== Timeout Policies =====
  timeouts:
    - state: "negotiation"
      action: "ProposalsClosed"  # Auto-close after 500ms
      fallback_state: "selection"
      log: true

    - state: "selection"
      action: "SelectionTimeout"  # Auto-reject if selection takes >100ms
      fallback_state: "rejected"
      log: true

  # ===== Violation Handling =====
  violations:
    - type: "unexpected_message"
      action: "block"         # Drop invalid messages
      log: true
      metrics: true

    - type: "timeout"
      action: "fallback"      # Trigger timeout transition
      log: true
      metrics: true

    - type: "deadlock"
      action: "abort"         # Abort protocol, cleanup FSM
      log: true
      metrics: true

    - type: "role_mismatch"   # Sender role doesn't match expected
      action: "block"
      log: true
      metrics: true

  # ===== Roles (see ADR-0003d) =====
  roles:
    - name: "orchestrator"
      capabilities: ["hire", "fire", "score"]

    - name: "agent"
      capabilities: ["propose", "accept", "reject"]

    - name: "system"
      capabilities: ["timeout", "monitor", "abort"]

  # ===== Messages (see ADR-0003d) =====
  messages:
    HireRequest:
      sender_role: "orchestrator"
      receivers: ["*"]
      schema: "HireRequest.fbs"
      priority: 2           # Normal priority

    Proposal:
      sender_role: "agent"
      receivers: ["orchestrator"]
      schema: "Proposal.fbs"
      priority: 2

    HireApproval:
      sender_role: "orchestrator"
      receivers: ["agent"]
      schema: "HireApproval.fbs"
      priority: 3           # Urgent (agent waiting)

    HireRejection:
      sender_role: "orchestrator"
      receivers: ["agent"]
      schema: "HireRejection.fbs"
      priority: 2

    ProposalsClosed:
      sender_role: "system"
      receivers: []
      schema: "ProposalsClosed.fbs"
      priority: 1           # Internal system message

    Timeout:
      sender_role: "system"
      receivers: []
      schema: "Timeout.fbs"
      priority: 1
```

---

## Consequences

### Positive ✅

**✅ Developer-Friendly Syntax:**
- YAML readable without MPST theory PhD
- **Result:** Team can write/modify protocols without formal methods training

**✅ Conversation-Native Primitives:**
- Clarification, barge-in, grounding as first-class state types
- **Result:** Protocols match user mental model of conversations

**✅ Fast Runtime Validation:**
- Pre-compiled FSMs for <2ms validation (vs 5-10ms Scribble interpretation)
- **Result:** Meets <5ms P95 validation budget

**✅ Deadlock Detection:**
- Static analysis at compile-time (detect circular waits before deployment)
- **Result:** Zero deadlocks in production

**✅ Progress Guarantees:**
- Timeout policies for all non-terminal states
- **Result:** Protocols always complete or timeout gracefully

**✅ Separation of Concerns:**
- Protocol validation (Actor messages) separate from AI agent internal logic (LLM calls)
- **Result:** Protocol Monitor stays simple, deterministic, <5ms

---

### Negative ⚠️

**⚠️ Custom Language Maintenance:**
- Must maintain PDL parser, compiler, validator
- **Mitigation:** Well-documented spec, comprehensive tests
- **Risk Level:** LOW (YAML syntax stable, compiler code small)

**⚠️ No Formal Proofs:**
- Cannot auto-prove deadlock freedom (like Scribble's theory)
- **Mitigation:** Compile-time deadlock detection, extensive testing
- **Risk Level:** LOW (heuristic deadlock detection catches most cases)

**⚠️ Learning Curve:**
- Team must learn PDL syntax (YAML + FSM concepts)
- **Mitigation:** Examples provided, YAML is familiar format
- **Risk Level:** LOW (2-3 days to learn, simpler than Scribble)

**⚠️ Compiler Bugs:**
- Bugs in PDL compiler could cause protocol validation failures
- **Mitigation:** Extensive compiler test suite, golden test protocols
- **Risk Level:** MEDIUM (critical path, requires rigorous testing)

---

## Implementation Notes

### **Implementation Timeline**

**Phase 1 (Week 1): PDL Parser & Validator**
- Implement YAML parser (PyYAML)
- Implement syntax validator (required fields, type checks)
- Implement semantic validator (reachability, orphaned states)
- Unit tests for all validators

**Phase 2 (Week 1-2): Deadlock Detection**
- Implement state graph builder
- Implement cycle detection (Tarjan's algorithm)
- Implement timeout escape check
- Test with known deadlock examples

**Phase 3 (Week 2): FSM Code Generation**
- Implement PDL → FSM compiler
- Implement FlatBuffers schema for FSM
- Implement serialization/deserialization
- Golden test: compile hire.pdl.yml → hire.fsm.fbs

**Phase 4 (Week 2): Runtime Integration**
- Implement FSM loader in Protocol Monitor
- Implement transition lookup (<1ms P95)
- Integration test with mailbox hooks
- Performance test: validate 10,000 messages, measure P95 latency

---

### **Dependencies**

**Before Starting:**
- ✅ PyYAML library (Python standard library)
- ✅ FlatBuffers compiler (`flatc`) installed
- ✅ ADR-0011 (FlatBuffers Serialization) - Schema patterns

**Blocking:**
- 0003b (6 Core Protocol Implementations) - Requires PDL spec
- 0003c (Protocol Monitor Runtime) - Requires compiled FSMs

---

### **Success Metrics**

**Correctness:**
- ✅ All syntax errors caught at compile-time
- ✅ Deadlock detection catches circular waits in test protocols
- ✅ Compiled FSMs match hand-coded FSMs (golden tests)

**Performance:**
- ✅ PDL compilation: <100ms per protocol
- ✅ FSM state lookup: <1ms P95
- ✅ Validation latency: <2ms P95 (after pre-compilation)

**Quality:**
- ✅ 95%+ test coverage (parser, validator, compiler)
- ✅ All 6 core protocols compile without errors
- ✅ Documentation complete (examples, tutorials)

---

### **Testing Strategy**

**Unit Tests:**
- PDL parser (valid YAML, invalid YAML, missing fields)
- Syntax validator (state types, transition schemas)
- Semantic validator (reachability, cardinality)
- Deadlock detector (known deadlock patterns)
- FSM compiler (PDL → FSM correctness)

**Integration Tests:**
- Compile all 6 core protocols (hire, task, clarification, barge-in, tool, saga)
- Load compiled FSMs in Protocol Monitor
- Validate sample messages against FSMs
- Performance test: 10,000 validations, measure P95

**Golden Tests:**
- Compare compiled FSM with expected FSM (byte-for-byte)
- Test protocol files: `hire.pdl.yml`, `task.pdl.yml`, `clarification.pdl.yml`

---

## References

### **Research Papers**

1. **Honda, K., Yoshida, N., Carbone, M. (2008)**
   "Multiparty Asynchronous Session Types"
   *Journal of the ACM, Vol. 63, No. 1*
   **Relevance**: MPST theory foundation, deadlock freedom proofs

2. **Yoshida, N., Hu, R., Neykova, R., Ng, N. (2013)**
   "The Scribble Protocol Language"
   *TOOLS 2013*
   **Relevance**: Academic MPST language (comparison, rejection rationale)

3. **Smith, R. G. (1980)**
   "The Contract Net Protocol: High-Level Communication and Control in a Distributed Problem Solver"
   *IEEE Transactions on Computers, Vol. C-29, No. 12*
   **Relevance**: Contract Net Protocol (Agent Hire protocol basis)

### **Related ADRs**

- [ADR-0003: MPST Protocol Validation](0003-mpst-protocol-validation.md) — Parent ADR
- [ADR-0002: Actor Model for Agent Isolation](0002-actor-model-agent-isolation.md) — Message passing foundation
- [ADR-0006: 3-Phase Orchestration](0006-3-phase-orchestration-contract-net.md) — Hire protocol usage
- [ADR-0011: FlatBuffers Serialization](0011-flatbuffers-serialization.md) — FSM serialization format

### **Architecture Diagrams**

- `architecture_diagrams/k1_protocol_monitor_fsms.mmd` — 6 protocol FSMs visualized
- `architecture_diagrams/k1_orchestrator_3phase.mmd` — Orchestration protocol flow

### **Whiteboard References**

- `docs/whiteboard.md` (lines 1401-1500) — MPST overview, protocol validation
- `docs/whiteboard.md` (lines 3650-3800) — Protocol examples, milestone planning

---

**Document Status:** ✅ **COMPLETE** - Comprehensive PDL specification with YAML syntax, compiler design, example protocols, and implementation guidance.

**Cross-References:**
- ADR-0003 (Parent): MPST Protocol Validation
- ADR-0002: Actor Model (message passing validation)
- ADR-0011: FlatBuffers (FSM serialization)
- Whiteboard: lines 1401-1500 (MPST), 3650-3800 (protocols)

**Canonical Values:**
- **58 agents:** 4 AI agents + 54 pure agents
- **Protocol timeout:** 500ms (Actor message receipt)
- **LLM timeout:** 5000ms (AI agent internal, separate concept)
- **Validation budget:** <5ms P95 (receive-side), <2ms FSM lookup
- **Compilation budget:** <100ms per protocol (startup only)

**Document End**
