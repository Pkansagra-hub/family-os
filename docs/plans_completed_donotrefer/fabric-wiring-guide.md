# Fabric End-to-End Wiring Guide for Epic 5.3

**Target Audience**: AI Coders implementing `FabricFactory`, `FabricFacade`, `FabricRetrieval`, and `CapabilityRegistryAPI`
**Source**: Complete analysis of fabric-implementation-plan.md (Milestones 1-5, Epic 5.3)
**Purpose**: Comprehensive wiring documentation showing dependency graph, initialization order, and integration points

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [The Six Port Interfaces (Epic 5.1)](#the-six-port-interfaces-epic-51)
3. [Adapters (Epic 5.2)](#adapters-epic-52)
4. [Complete Component Dependency Graph](#complete-component-dependency-graph)
5. [FabricFactory Construction Order](#fabricfactory-construction-order)
6. [The Three Factory Methods](#the-three-factory-methods)
7. [FabricFacade Execution Pipeline](#fabricfacade-execution-pipeline)
8. [Critical Wiring Constraints (FAB-01 to FAB-13)](#critical-wiring-constraints)
9. [Bidirectional Wiring Examples](#bidirectional-wiring-examples)
10. [Implementation Checklist](#implementation-checklist)

---

## Architecture Overview

The Fabric follows **Hexagonal Architecture (Ports & Adapters)**:

```
┌─────────────────────────────────────────────────────────────────┐
│                        FABRIC CORE                              │
│  ┌────────────┐  ┌──────────┐  ┌─────────────┐  ┌───────────┐ │
│  │  Registry  │  │ Resolver │  │ PolicyEngine│  │ Providers │ │
│  └────────────┘  └──────────┘  └─────────────┘  └───────────┘ │
│                                                                  │
│  ┌────────────────┐  ┌──────────────┐  ┌────────────────────┐ │
│  │ RetrievalEngine│  │ContextBuilder│  │ OutputValidation   │ │
│  └────────────────┘  └──────────────┘  └────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │
                         PORT LAYER (6 Interfaces)
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         ADAPTERS                                │
│  Production: SessionStateReaderAdapter, BridgeConnectionAdapter │
│  Testing: TestStateReader, LocalEvent, TestBridge, etc.        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              EXTERNAL SYSTEMS (K0, SessionState, etc.)          │
└─────────────────────────────────────────────────────────────────┘
```

**Key Principle**: Fabric core NEVER directly imports from external systems. All communication through ports.

---

## The Six Port Interfaces (Epic 5.1)

These 6 ports define ALL external communication:

### 5.1.1 ISessionStateReader

**Location**: `k1/fabric/ports/state_reader.py`
**Purpose**: Read-only SessionState access
**Status**: ✅ IMPLEMENTED

**Interface**:

```python
@runtime_checkable
class ISessionStateReader(Protocol):
    """Read-only access to SessionState sections"""

    async def read_section(self, session_id: str, section: str) -> Dict[str, Any]:
        """Read a specific section. Returns empty dict if missing."""
        ...

    async def read_sections(self, session_id: str, sections: List[str]) -> Dict[str, Dict[str, Any]]:
        """Batch read multiple sections. Lock-free, multi-reader safe."""
        ...

    async def has_section(self, session_id: str, section: str) -> bool:
        """Check if section exists without reading."""
        ...
```

**Consumers**:

- `PolicyEngine` (affective_now, cognitive state)
- `ContextBuilder` (required_context, optional_context)
- `SemanticValidator` (beliefs_active for hallucination detection)
- `AgentFactory` (step 4: grant SessionState read access)

**Critical Rule (FAB-01)**: Agents can ONLY read SessionState, never write. Writes go through `IDeltaBusPort`.

---

### 5.1.2 IEventPort

**Location**: `k1/fabric/ports/event_port.py`
**Purpose**: Event emission and subscription
**Status**: ✅ IMPLEMENTED

**Interface**:

```python
@runtime_checkable
class IEventPort(Protocol):
    """Event bus interface for pub/sub"""

    async def emit(self, event_type: str, payload: Dict[str, Any], trace_id: str) -> None:
        """Emit event with cognitive_trace_id (FAB-09)"""
        ...

    def subscribe(self, event_pattern: str, handler: Callable[[str, Dict], Awaitable[None]]) -> str:
        """Subscribe to events matching pattern. Returns subscription_id."""
        ...

    def unsubscribe(self, subscription_id: str) -> None:
        """Remove subscription"""
        ...
```

**Event Categories**:

```python
# Registry events
k1.fabric.capability.registered.v1
k1.fabric.capability.unregistered.v1
k1.fabric.capability.availability.changed.v1
k1.fabric.capability.metrics.updated.v1
k1.fabric.capability.version.conflict.v1
k1.fabric.registry.reloaded.v1

# Execution events
k1.capability.invoked.v1
k1.capability.completed.v1
k1.capability.failed.v1

# Validation events
k1.fabric.contract.validation.failed.v1
k1.fabric.output.validation.failed.v1

# Learning events
k1.fabric.learning.signal.v1  # → K0 P09 Learning Loop

# Health events
k1.fabric.provider.health.changed.v1

# Backpressure events
k1.fabric.pressure.warning.v1
k1.fabric.pressure.shedding.v1

# Proactive gap detection
k1.fabric.capability.contract_updated.v1

# External subscriptions
k1.mcp.tool.discovered.v1  # FROM Orchestrator → triggers registration
```

**Consumers**:

- `Registry` (emit on register/unregister)
- `ModuleLoader` (emit validation failures)
- `CircuitBreaker` (emit state changes)
- `HealthChecker` (emit health changes)
- `OutputValidationPipeline` (emit validation failures)
- `FabricMailbox` (emit backpressure warnings)
- `EventEmitter` (wraps all event emission with trace_id)

---

### 5.1.3 IBridgePort

**Location**: `k1/fabric/ports/bridge_port.py`
**Purpose**: K0 Cross-Kernel Bridge access
**Status**: ✅ IMPLEMENTED

**Interface**:

```python
@runtime_checkable
class IBridgePort(Protocol):
    """Access K0 via Bridge for memory & IFL-routed tools"""

    async def call(self, operation: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute bridge operation.
        Operations:
        - memory.store, memory.recall, memory.delta (SessionState mutations)
        - tool.execute.home.*, tool.execute.device.* (IFL-routed tools)
        """
        ...

    async def is_available(self) -> bool:
        """Check if Bridge connection is active (LOCAL vs HOT/WARM)"""
        ...
```

**Consumers**:

- `BridgeProvider` ONLY (no other component calls Bridge directly)

**Graceful Fallback**:

- `is_available() == False` → LOCAL COLD mode
- `BridgeProvider` returns capability unavailable errors gracefully

---

### 5.1.4 IModelGatewayPort

**Location**: `k1/fabric/ports/model_gateway.py`
**Purpose**: LLM access for agents
**Status**: ✅ IMPLEMENTED

**Interface**:

```python
@runtime_checkable
class IModelGatewayPort(Protocol):
    """Model access for agent execution"""

    async def create_session(self, agent_id: str, config: ModelConfig) -> ModelSession:
        """Create LLM session for agent (with warm-up)"""
        ...

    async def complete(self, session: ModelSession, messages: List[Message]) -> CompletionResult:
        """Request completion from model"""
        ...

    async def close_session(self, session: ModelSession) -> None:
        """Clean up model session"""
        ...
```

**Consumers**:

- `AgentFactory` (step 3: grant LLM access during agent instantiation)
- `Agent.warm_up()` (preload model during WARMING → ACTIVE transition)
- `Agent.execute()` (call model during request processing)

**Critical Rule (FAB-02)**: NO direct LLM calls except through this port. Enforces deterministic routing.

---

### 5.1.5 IPromptSystemPort

**Location**: `k1/fabric/ports/prompt_system.py`
**Purpose**: Prompt template resolution
**Status**: ✅ IMPLEMENTED

**Interface**:

```python
@runtime_checkable
class IPromptSystemPort(Protocol):
    """Prompt template resolution"""

    async def resolve_template(self, template_id: str, variables: Dict[str, Any]) -> str:
        """Resolve prompt template with variables"""
        ...

    async def get_compiled_prompt(self, capability_name: str, context: ExecutionContext) -> str:
        """Get compiled prompt for capability with context injection"""
        ...
```

**Consumers**:

- `ContextBuilder` (step 4: resolve prompt templates before execution)

**Usage Flow**:

1. Contract defines: `prompt_templates: ["agent.reasoning.v1", "system.safety.v2"]`
2. `ContextBuilder.build()` calls `IPromptSystemPort.get_compiled_prompt()`
3. Templates resolved with variables from `ExecutionContext`
4. Final compiled prompt included in `ExecutionContext` passed to provider

---

### 5.1.6 IDeltaBusPort

**Location**: `k1/fabric/ports/delta_bus.py`
**Purpose**: Agent delta emission for SessionState mutations
**Status**: ✅ IMPLEMENTED

**Interface**:

```python
@runtime_checkable
class IDeltaBusPort(Protocol):
    """Delta emission for SessionState changes"""

    async def emit_delta(self, agent_id: str, deltas: List[Delta]) -> None:
        """
        Emit deltas for processing by Concierge.
        Delta format: {section: str, key: str, value: Any, operation: 'set'|'delete'}
        """
        ...
```

**Delta Flow**:

```
Agent discovers fact during execution
  ↓
Agent.execute() calls DeltaEmitter.emit()
  ↓
DeltaEmitter batches (500ms window, LWW merge on section+key)
  ↓
IDeltaBusPort.emit_delta(agent_id, batched_deltas)
  ↓
Delta Bus routes to Concierge
  ↓
Concierge applies to SessionState via FSM
```

**Consumers**:

- `Agent.execute()` (fact discovery during agent reasoning)
- `DeltaEmitter` (internal to AgentFactory, batches deltas before port call)

**Critical Rule (FAB-01 Enforcement)**: This is the ONLY way agents mutate SessionState.

---

## Adapters (Epic 5.2)

### Production Adapters

#### SessionStateReaderAdapter (5.2.1)

**Location**: `k1/fabric/adapters/sessionstate_reader.py`
**Status**: ✅ IMPLEMENTED
**Wraps**: Real `SessionStateManager` (injected per-session)
**Usage**: Production deployments with live SessionState

#### BridgeConnectionAdapter (5.2.8)

**Location**: `k1/fabric/adapters/bridge_connection.py`
**Status**: ⚠️ PARTIALLY IMPLEMENTED (test version exists)
**Routes**: K0 Bridge when available, graceful fallback when not
**Usage**: Production HOT/WARM mode (LOCAL COLD = unavailable)

---

### Test Adapters

#### TestSessionStateReaderAdapter (5.2.2)

**Location**: `k1/fabric/adapters/test_state_reader.py`
**Status**: ✅ IMPLEMENTED
**Storage**: In-memory `Dict[Tuple[session_id, section], data]`
**Usage**: Standalone mode, unit tests

#### LocalEventAdapter (5.2.3)

**Location**: `k1/fabric/adapters/local_event.py`
**Status**: ✅ IMPLEMENTED
**Features**: Synchronous dispatch, capture_mode for testing
**Usage**: Testing (capture and assert on events)

#### TestBridgeAdapter (5.2.4)

**Location**: `k1/fabric/adapters/test_bridge.py`
**Status**: ✅ IMPLEMENTED
**Responses**: Canned responses for memory/IFL operations
**Usage**: Standalone mode, tests Bridge-dependent capabilities

#### TestModelGatewayAdapter (5.2.5)

**Location**: `k1/fabric/adapters/test_model_gateway.py`
**Status**: ✅ IMPLEMENTED
**Responses**: Canned LLM responses for deterministic tests
**Usage**: Agent provider tests

#### TestPromptSystemAdapter (5.2.6)

**Location**: `k1/fabric/adapters/test_prompt_system.py`
**Status**: ✅ IMPLEMENTED
**Storage**: Static prompt templates from dict
**Usage**: Standalone mode, context builder tests

#### TestDeltaBusAdapter (5.2.7)

**Location**: `k1/fabric/adapters/test_delta_bus.py`
**Status**: ⚠️ NOT FOUND (may be in different location)
**Features**: Capture mode for delta assertions
**Usage**: Agent provider tests

---

## Complete Component Dependency Graph

### Layer 1: Foundation Types (No Dependencies)

**File**: `k1/fabric/types.py`
**Status**: ✅ IMPLEMENTED

**Key Types**:

```python
# Request/Response Envelopes
CapabilityRequest (input envelope: name, params, trace_id, session_id, priority)
CapabilityResult (output envelope: success, data, metadata, error)

# Contracts
CapabilityContract (base)
AgentContract (extends CapabilityContract)
PromptContract (extends CapabilityContract)
WorkflowContract (extends CapabilityContract)

# Retrieval
RetrievalResult (list[ScoredCapability])

# Execution
ExecutionContext (compiled_prompt, state_sections, token_budget, tools_granted)
ProviderConfig (provider_id, type, endpoint, timeout, etc.)

# Enums
ProviderType: MCP | WASM | BRIDGE | AGENT | WORKFLOW | CONCIERGE
SafetyBand: PUBLIC | INTERNAL | PRIVATE
Availability: ONLINE | DEGRADED | OFFLINE
Tier: PROD | BETA | EXPERIMENTAL
AgentLifecycleState: PENDING | WARMING | ACTIVE | IDLE | DRAINING | TERMINATED
Priority: INTERACTIVE | BACKGROUND | BATCH
BatchStrategy: PARALLEL | SEQUENTIAL | DAG

# Versioning
CapabilityVersion (major, minor, patch, semver parsing)
```

---

### Layer 2: Contract System (M2 - Depends on: Types)

#### ContractValidator (2.1.1)

**Location**: `k1/fabric/core/contract_validator.py`
**Status**: ✅ IMPLEMENTED
**Dependencies**: types
**Used By**: Registry.register(), ModuleLoader
**Validates**: All 12 semantic rules (see fabric-implementation-plan.md Epic 2.1)

#### Parsers (2.1.2)

**Location**: `k1/fabric/contracts/*.py`
**Status**: ✅ IMPLEMENTED
**Files**:

- `tool_contract.py` → `CapabilityContract`
- `agent_contract.py` → `AgentContract`
- `prompt_contract.py` → `PromptContract`
- `workflow_contract.py` → `WorkflowContract`
- `__init__.py` → `parse_contract()` facade

#### ModuleLoader (2.3.1)

**Location**: `k1/fabric/core/module_loader.py`
**Status**: ✅ IMPLEMENTED
**Dependencies**: ContractValidator, Registry, IEventPort
**Key Methods**:

- `scan_directory(path)` → loads YAML from disk
- `register_from_dict(dict)` → programmatic registration (for MCP tool discovery)
- `hot_reload_watcher()` → watches for file changes

#### CapabilityRegistry (2.2.1) ⭐ CENTRAL HUB

**Location**: `k1/fabric/core/registry.py`
**Status**: ✅ IMPLEMENTED
**Dependencies**: ContractValidator, IEventPort
**Thread Safety**: RLock guards all mutations

**5 Indexes**:

```python
by_name: Dict[str, CapabilityContract]         # O(1) exact lookup
by_domain: Dict[str, List[str]]                 # inverted index
by_type: Dict[str, List[str]]                   # grouped by type prefix
by_version: Dict[str, Dict[Version, Contract]]  # version-aware lookup
by_provider: Dict[str, List[str]]               # grouped by provider_id
```

**Key Methods**:

```python
register(contract: CapabilityContract) -> None
    ├── Validate via ContractValidator
    ├── Check for duplicates
    ├── Insert into 5 indexes
    └── Emit: k1.fabric.capability.registered.v1

unregister(name: str) -> None
    ├── Remove from 5 indexes
    └── Emit: k1.fabric.capability.unregistered.v1

lookup(name: str, version: Optional[Version] = None) -> CapabilityContract
    └── O(1) exact match from by_name or by_version

list_by_domain(domain: str) -> List[CapabilityContract]
list_by_type(type_prefix: str) -> List[CapabilityContract]

update_availability(name: str, status: Availability) -> None
    └── Emit: k1.fabric.capability.availability.changed.v1

update_metrics(name: str, latency_ms: float, success: bool) -> None
    ├── Running averages: success_rate_30d, avg_latency_ms
    └── Emit: k1.fabric.capability.metrics.updated.v1

reload() -> None
    └── Full reload from disk, emit: k1.fabric.registry.reloaded.v1

health() -> RegistryHealth
    └── Snapshot: total, by_status, by_provider_type
```

---

### Layer 3: Provider Resolution (M3 - Depends on: Registry, Types)

#### ProviderRegistry (3.1.1)

**Location**: `k1/fabric/provider_resolution/provider_registry.py`
**Status**: ✅ IMPLEMENTED
**Purpose**: Maps `provider_id` → `ProviderConfig`
**Methods**: `register_provider()`, `lookup_provider()`, `health_check()`
**Populated By**: FabricFactory at startup

#### ProviderMatcher (3.1.2)

**Location**: `k1/fabric/provider_resolution/provider_matcher.py`
**Status**: ✅ IMPLEMENTED
**Purpose**: Given `CapabilityContract` → find all registered providers
**Usually**: 1:1 (contract.provider_id → provider)
**Returns**: `list[ProviderConfig]`

#### PolicyEngine (3.2.5) ⭐ CRITICAL WIRING

**Location**: `k1/fabric/policy/policy_engine.py`
**Status**: ✅ IMPLEMENTED
**Dependencies**: ISessionStateReader, types

**4 Dimensions** (final_score = base + affective + cognitive + qos):

```python
1. SecurityContext (HARD GATE - runs FIRST)
   ├── Checks: user_band >= capability.safety_band_min
   ├── Enforces: FAB-06 (safety first)
   └── Returns: PASS or REJECT

2. AffectiveRouting (soft score: 0.0-0.2)
   ├── Reads: affective_now from ISessionStateReader
   ├── Rules: high sadness/anxiety → gentler providers (+0.1)
   └── Returns: score (0.0-0.2)

3. CognitiveLoadRouting (soft score: 0.0-0.15)
   ├── Reads: cognitive state from ISessionStateReader
   ├── Rules: high load → faster providers (+0.1)
   └── Returns: score (0.0-0.15)

4. QoSIntegration (soft score: 0.0-0.2)
   ├── Reads: budget/latency from request/context
   ├── Rules: tight budget → cheaper (0.8), ample → balanced (0.3)
   └── Returns: score (0.0-0.2)
```

**ToolScope** (sub-agent tool scoping):

```python
validate_tool_access(capability_name: str, tools_granted: List[str]) -> None
    ├── Validates: capability_name in tools_granted[]
    ├── Enforces: FAB-07 (scoped access)
    └── Raises: AccessDeniedError if not granted
```

**Returns**: `PolicyResult{allowed: bool, score: float, reasons: List[str]}`

#### ProviderSelector (3.1.3)

**Location**: `k1/fabric/provider_resolution/provider_selector.py`
**Status**: ✅ IMPLEMENTED
**Purpose**: Given candidates + policy scores → select best
**Tie-Breaking**: Lower latency, then alphabetical
**Enforces**: FAB-10 (deterministic)
**Returns**: `ResolvedProvider{provider_instance, contract, policy_context}`

#### ProviderFactory (3.1.4)

**Location**: `k1/fabric/provider_resolution/provider_factory.py`
**Status**: ✅ IMPLEMENTED
**Purpose**: Given `ProviderConfig` → instantiate provider

**Provider Types**:

```python
MCPProvider       (3.3.2) - MCP tool execution
WASMProvider      (3.3.3) - WASM sandboxed execution
BridgeProvider    (3.3.4) - K0 Bridge routing
AgentProvider     (3.3.7) - Agent spawning
WorkflowProvider  (3.3.5) - Workflow orchestration
ConciergeProvider (3.3.6) - Concierge FSM routing
```

**Factory Pattern**: Injected dependencies (ports, registry, context builder, etc.)

#### Resolver (3.1.5) ⭐ COMPLETE PIPELINE

**Location**: `k1/fabric/provider_resolution/resolver.py`
**Status**: ✅ IMPLEMENTED
**Dependencies**: CapabilityRegistry, ProviderRegistry, PolicyEngine, ProviderFactory

**5-Step Pipeline**:

```python
resolve(request: CapabilityRequest) -> ResolvedProvider:
    1. Registry.lookup(request.capability_name)
    2. ProviderMatcher → candidates
    3. PolicyEngine.evaluate() → allowed + score
    4. ProviderSelector → best provider
    5. ProviderFactory.instantiate() → provider instance
```

---

### Layer 4: Execution Runtime (M3 - Depends on: Types, Ports, PolicyEngine)

#### CapabilityProvider Protocol

**Location**: `k1/fabric/providers/base_provider.py`
**Status**: ✅ IMPLEMENTED

**Interface**:

```python
@runtime_checkable
class CapabilityProvider(Protocol):
    async def execute(self, request: CapabilityRequest, context: ExecutionContext, trace_id: str) -> CapabilityResult:
        ...

    async def health_check(self) -> ProviderHealth:
        ...

    def capabilities(self) -> List[str]:
        ...
```

#### All Providers (3.3.x)

**Status**: ✅ ALL IMPLEMENTED

| Provider | File | Circuit Breaker Timeout | Key Dependencies |
|----------|------|-------------------------|------------------|
| MCPProvider | `providers/mcp_provider.py` | 10s local / 15s remote | None |
| WASMProvider | `providers/wasm_provider.py` | 5s | None |
| BridgeProvider | `providers/bridge_provider.py` | 10s | IBridgePort |
| WorkflowProvider | `providers/workflow_provider.py` | 60s | Registry (version-aware lookup) |
| ConciergeProvider | `providers/concierge_provider.py` | 30s | None |
| AgentProvider | `providers/agent_provider.py` | 30s | ALL PORTS + ContextBuilder + PolicyEngine |

#### CircuitBreaker (3.4.1) ⭐ FAULT ISOLATION

**Location**: `k1/fabric/circuit_breaker/breaker.py`
**Status**: ✅ IMPLEMENTED
**Dependencies**: IEventPort (state changes)

**States**: CLOSED → OPEN (fail threshold) → HALF_OPEN → CLOSED/OPEN

**Per-Provider Configs** (3.4.2):

```python
MCP local:   timeout=10s, failure_threshold=3/min, retry_max=2
MCP remote:  timeout=15s, failure_threshold=3/min, retry_max=2
WASM:        timeout=5s,  failure_threshold=5/min, retry_max=2
Bridge:      timeout=10s, failure_threshold=3/min, retry_max=2
Agent:       timeout=30s, failure_threshold=2/min, retry_max=2
Workflow:    timeout=60s, failure_threshold=1/min, retry_max=1
Default:     timeout=30s, failure_threshold=5/min, retry_max=2
```

**Bidirectional with HealthChecker**:

- CB OPEN → trigger immediate health check
- Health success → signal CB HALF_OPEN

**Enforces**: FAB-04 (timeout within 30s)

#### OutputValidationPipeline (3.5.1) ⭐ 3-TIER

**Location**: `k1/fabric/output_validation/pipeline.py`
**Status**: ✅ IMPLEMENTED
**Dependencies**: ISessionStateReader, IEventPort
**Wired Into**: FabricFacade.execute() AFTER provider returns

**3 Tiers** (fail fast):

```python
1. StructuralValidator (HARD FAIL)
   ├── Checks: required fields, valid JSON, no truncation, size limits
   └── REJECT malformed → CapabilityResult.failure()

2. SchemaValidator (HARD FAIL, with coercion fallback)
   ├── Validates: result.data against contract.output_schema
   ├── Fallback: attempt coercion, retry validation
   └── REJECT schema violation → CapabilityResult.failure()

3. SemanticValidator (SOFT FAIL, agent/prompt only)
   ├── Reads: SessionState beliefs via ISessionStateReader
   ├── Checks: factual grounding, consistency, confidence
   ├── ANNOTATE with warning, do NOT reject
   └── Optional: skip_semantic=True for tool-only results
```

**Emits**: `k1.fabric.output.validation.failed.v1` on rejection

#### HealthChecker (3.6.1)

**Location**: `k1/fabric/health/health_checker.py`
**Status**: ✅ IMPLEMENTED
**Dependencies**: ProviderRegistry, CircuitBreaker map, IEventPort

**Flow**:

```python
Periodic health checks (default 30s per provider type)
  ↓
Iterate providers → call health_check() → update state
  ↓
State transitions: ONLINE ↔ DEGRADED ↔ OFFLINE (with thresholds)
  ↓
Calls: AvailabilityTracker.update_state()
  ↓
Emits: k1.fabric.provider.health.changed.v1
```

**Bidirectional with CB**:

- Subscribes to CB state changes
- CB OPEN → immediate health check
- Health success → signal CB HALF_OPEN

**Started By**: FabricFactory in setup phase

#### AvailabilityTracker (3.6.2)

**Location**: `k1/fabric/health/availability_tracker.py`
**Status**: ✅ IMPLEMENTED
**Tracks**: ONLINE/DEGRADED/OFFLINE per provider
**Maintains**: Transition history
**Calls**: Registry.update_availability()
**Data Consumed By**: HardFilter (4.1.2)

---

### Layer 5: Retrieval Engine (M4 - Depends on: Registry, Types)

#### EmbeddingIndex (4.1.1)

**Location**: `k1/fabric/retrieval/embedding_index.py`
**Status**: ✅ IMPLEMENTED
**Dependencies**: FAISS library

**Text to Embed**: `f"{contract.description} | {' '.join(contract.capabilities)}"`

**Operations**:

- `add_vector(contract_id, vector)` - incremental updates on register
- `remove_vector(contract_id)` - on unregister
- `search(vector, k)` → `list[(id, score)]`

**Support**: Flat L2 (<10K), IVF (>10K)

#### HardFilter (4.1.2)

**Location**: `k1/fabric/retrieval/hard_filter.py`
**Status**: ✅ IMPLEMENTED
**Dependencies**: ISessionStateReader (implicit for input satisfiability check)

**3 Hard Rules** (ANY fail = ELIMINATED):

```python
1. Safety band: capability.safety_band_min <= user_band
2. Availability: not OFFLINE (DEGRADED kept, penalized)
3. Input satisfiability: required_inputs satisfiable from params + SessionState
```

**Enforces**: FAB-05 (filters before soft ranking)

#### SoftRanker (4.1.3)

**Location**: `k1/fabric/retrieval/soft_ranker.py`
**Status**: ✅ IMPLEMENTED
**Dependencies**: EmbeddingIndex, CapabilityRegistry (metrics)

**Composite Scoring** (weights: 0.4 + 0.3 + 0.15 + 0.15):

```python
semantic_similarity (0.4):     cosine(query_vector, capability_vector)
domain_match (0.3):            Jaccard(query_domains, capability_domains)
success_rate (0.15):           capability.success_rate_30d (default 0.5 if new)
cost_latency_score (0.15):     1.0 - normalize(cost + latency/10000)
DEGRADED penalty:              multiply by 0.7
```

#### TopKSelector (4.1.4)

**Location**: `k1/fabric/retrieval/top_k_selector.py`
**Status**: ✅ IMPLEMENTED
**Selects**: Top K from scored set (default K=10, max K=25)
**Each Result**: contract + schemas + score + provider_type

#### RetrievalEngine (4.1.5) ⭐ ROLE 1

**Location**: `k1/fabric/retrieval/retrieval_engine.py`
**Status**: ✅ IMPLEMENTED
**Dependencies**: CapabilityRegistry, EmbeddingIndex, AvailabilityTracker, ISessionStateReader

**Full Pipeline**: Embed → HardFilter → SoftRank → TopK

**APIs**:

```python
async def discover_capabilities(
    domain: str,
    intent: str,
    safety_band: SafetyBand,
    session_context: Dict[str, Any],
    top_k: int = 10
) -> RetrievalResult
    # Returns list[ScoredCapability]

async def find_relevant_prompts(
    intent: str,
    domain: str,
    safety_band: SafetyBand,
    top_k: int = 10
) -> RetrievalResult
    # Returns list[ScoredPrompt]
```

**Performance Targets**:

- <20ms for 10K contracts
- <50ms for 100K contracts

**Called By**: FabricRetrieval.discover_capabilities() (5.3.3)

---

### Layer 6: Context Builder (M4 - Depends on: Registry, Types, Ports)

#### ContextBuilder (4.2.1) ⭐ CRITICAL WIRING

**Location**: `k1/fabric/core/context_builder.py`
**Status**: ✅ IMPLEMENTED
**Dependencies**: ISessionStateReader, IPromptSystemPort, types

**6-Step Flow**:

```python
async def build(self, request: CapabilityRequest, contract: CapabilityContract) -> ExecutionContext:
    1. Read contract.required_context + optional_context
    2. Fetch from SessionState via ISessionStateReader (multi-reader, lock-free)
    3. Inject request params
    4. Resolve prompt template via IPromptSystemPort
    5. Apply token budget (128K ceiling)
    6. Package ExecutionContext
```

**Handles**:

- Optional sections missing → skip
- Required sections missing → warn + continue

**Enforces**: FAB-08 (128K token ceiling)

**Output**: `ExecutionContext` consumed by ALL providers

#### ContextBudget (4.2.2)

**Location**: `k1/fabric/core/context_budget.py`
**Status**: ✅ IMPLEMENTED
**Internal To**: ContextBuilder

**Budget Allocation**:

```python
system_prompt:      2K-5K
compiled_prompt:    500-2K
SessionState:       10K-40K
request_params:     1K-5K
tool_results:       5K-20K
response_headroom:  2K-8K
CEILING:            128K tokens
```

**Compression Strategies** (5 levels, applied in order):

```python
1. Drop optional_context first
2. Truncate history_recent to last 3 turns
3. Summarize beliefs_active (drop low-confidence)
4. Summarize scoreboard (keep only current QUD)
5. Emergency: drop all WARM, keep HOT only
```

**Token Counting**: tiktoken (if available) or chars/4 heuristic (<1ms)

---

### Layer 7: Agent Factory & Agent Lifecycle (M4 - Depends on: Registry, Types, Ports, ContextBuilder, PolicyEngine)

#### AgentFactory (4.3.1) ⭐ MOST HEAVILY WIRED

**Location**: `k1/fabric/providers/agent_provider.py`
**Status**: ✅ IMPLEMENTED

**Dependencies** (ALL PORTS):

```python
IModelGatewayPort     → grant LLM access
ISessionStateReader   → read declared sections
IDeltaBusPort         → emit deltas
ContextBuilder        → initial context
ToolScope             → enforce tools_granted[]
FabricMailbox         → MPSC communication
CapabilityRegistry    → lookup contracts
```

**8-Step Instantiation**:

```python
async def spawn_and_execute(request: CapabilityRequest, contract: AgentContract) -> CapabilityResult:
    1. Load YAML template (AgentContract from registry)
    2. Create MPSC Mailbox (WFQ INTERACTIVE priority)
    3. Grant LLM access via IModelGatewayPort
    4. Grant SessionState read (declared sections, lock-free)
    5. Scope tool access (tools_granted, strict enforcement)
    6. Build initial context via ContextBuilder
    7. Instantiate Agent object
    8. Start lifecycle: PENDING → WARMING → ACTIVE
```

**Agent Lifecycle**:

```python
PENDING     → just created, not yet initialized
WARMING     → model preloading via IModelGatewayPort
ACTIVE      → executing requests
IDLE        → pooled, 60s TTL
DRAINING    → graceful shutdown
TERMINATED  → removed from pool
```

**Enforces**:

- FAB-01: Never writes SessionState → emit deltas to IDeltaBusPort
- FAB-07: Tool scope → ToolScope validation

#### Agent (4.3.2)

**Location**: `k1/fabric/providers/agent_provider.py`
**Status**: ✅ IMPLEMENTED

**Instance Properties**:

```python
id:                UUID
contract:          AgentContract
mailbox:           MPSC
llm_handle:        from IModelGatewayPort
state_reader:      ISessionStateReader reference
tool_scope:        ToolScope validator
context:           ExecutionContext
lifecycle_state:   AgentLifecycleState
```

**Methods**:

```python
async warm_up() -> None
    # WARMING → ACTIVE

async execute(params: Dict[str, Any]) -> CapabilityResult
    # Main execution loop

async drain() -> None
    # DRAINING

async terminate() -> None
    # TERMINATED
```

**Delta Emission**:

```python
DeltaEmitter (internal)
├── Batched emission (500ms window)
├── LWW merge on (section, key)
├── Thread-safe Lock
└── Emits: k1.agent.{agent_id}.delta.v1 (DELTA_TOPIC_PATTERN)
```

**Tool Invocation**:

```python
async invoke_capability(name: str, params: Dict[str, Any]) -> CapabilityResult
    └── Respects tool scope (FAB-07)
```

#### AgentPool (4.3.3)

**Location**: `k1/fabric/providers/agent_provider.py`
**Status**: ✅ IMPLEMENTED

**Purpose**: IDLE agent reuse by contract name

**Config**:

```python
max_pool_size:  5 (configurable)
idle_ttl:       60s (configurable)
sweep_interval: 15s (configurable)
```

**Thread Safety**: RLock

**Methods**: `put()`, `get()`, `sweep()`, `drain_all()`

**AgentFactory Flow**: Check pool before spawning (hit = reuse without warm_up)

#### FabricMailbox (4.4.1)

**Location**: `k1/fabric/concurrency/dispatcher.py`
**Status**: ✅ IMPLEMENTED
**Dependencies**: IEventPort (backpressure events)

**Bounded Parallelism**: Semaphore(max_concurrent=10)

**BackpressureLevel**: NORMAL / WARNING / SHEDDING / SATURATED

**DispatchResult**: wraps CapabilityResult + wait_ms + backpressure_at_entry

**Flow**:

```python
shutdown check → backpressure reject → semaphore acquire → execute → release
```

**Backpressure Signals**:

```python
WARNING at 80%:     emit k1.fabric.pressure.warning.v1
SHEDDING at 95%:    reject BACKGROUND
SATURATED at 100%:  reject all
```

**Graceful Shutdown**: Drains all permits

**Used By**: FabricFactory production mode only

#### TimeoutGuard (4.4.2)

**Location**: `k1/fabric/concurrency/timeout.py`
**Status**: ✅ IMPLEMENTED

**Deadline Enforcement**:

```python
Priority: request params > default > max cap
```

**Exceptions**: `DeadlineExceededError(agent_id, timeout_ms, retriable=True)`

**Methods**: `resolve_timeout()`, `execute_with_guard()`, `execute_safe()`

**Stats**: total_guarded, total_exceeded, total_succeeded

---

### Layer 8: Event Bus Integration (M5 - Depends on: Types, Ports)

#### EventEmitter (5.4.2)

**Location**: Not yet implemented - **NEEDS CREATION**
**Status**: ❌ TODO (Epic 5.4)
**Dependencies**: IEventPort

**Wraps**: IEventPort
**Enforces**: cognitive_trace_id on every event (FAB-09)

**Methods**:

```python
async emit_invoked(request: CapabilityRequest) -> None
async emit_completed(request: CapabilityRequest, result: CapabilityResult) -> None
async emit_failed(request: CapabilityRequest, error: Exception) -> None
async emit_registered(contract: CapabilityContract) -> None
async emit_unregistered(name: str) -> None
async emit_learning_signal(
    capability_name: str,
    provider_id: str,
    success: bool,
    duration_ms: float,
    error_code: Optional[str],
    context_quality_score: float
) -> None
```

**Singleton**: Per Fabric instance (created by FabricFactory)

---

## FabricFactory Construction Order

**File**: `k1/fabric/factory.py` (Epic 5.3.1)
**Status**: ❌ TODO - **THIS IS WHAT YOU NEED TO IMPLEMENT**

This is the **dependency-safe initialization order** that FabricFactory MUST follow:

```python
class FabricFactory:
    """
    Composition root for Fabric.
    Wires all subsystems in dependency-safe order.
    """

    @staticmethod
    def create_standalone() -> Fabric:
        """All test adapters, no external deps. For development/testing."""
        ...

    @staticmethod
    def create_for_testing(capture_events: bool = True) -> Fabric:
        """Test adapters + event capture mode. For integration tests."""
        ...

    @staticmethod
    def create_with_ports(
        state_reader: ISessionStateReader,
        event_port: IEventPort,
        bridge: IBridgePort,
        model_gateway: IModelGatewayPort,
        prompt_system: IPromptSystemPort,
        delta_bus: IDeltaBusPort,
        production_mode: bool = False
    ) -> Fabric:
        """Custom adapter injection. For production deployment."""
        ...
```

### Construction Order (20 Steps)

```python
def _construct_fabric(
    state_reader: ISessionStateReader,
    event_port: IEventPort,
    bridge: IBridgePort,
    model_gateway: IModelGatewayPort,
    prompt_system: IPromptSystemPort,
    delta_bus: IDeltaBusPort,
    production_mode: bool
) -> Fabric:
    """Internal: Dependency-safe construction order"""

    # ===== STEP 1: Adapters are already provided as parameters =====
    # (or created in create_standalone/create_for_testing)

    # ===== STEP 2: Types & utilities (pure, no dependencies) =====
    validator = ContractValidator()

    # ===== STEP 3: Registry (depends on: validator, event_port) =====
    registry = CapabilityRegistry(
        validator=validator,
        event_port=event_port
    )

    # ===== STEP 4: ModuleLoader (depends on: registry, event_port) =====
    module_loader = ModuleLoader(
        registry=registry,
        event_port=event_port
    )

    # ===== STEP 5: Policy subsystem (depends on: state_reader) =====
    security_context = SecurityContext()
    affective_routing = AffectiveRouting(state_reader=state_reader)
    cognitive_routing = CognitiveLoadRouting(state_reader=state_reader)
    qos_integration = QoSIntegration()
    tool_scope = ToolScope()

    policy_engine = PolicyEngine(
        security_context=security_context,
        affective_routing=affective_routing,
        cognitive_routing=cognitive_routing,
        qos_integration=qos_integration,
        tool_scope=tool_scope
    )

    # ===== STEP 6: Provider infrastructure =====
    provider_registry = ProviderRegistry()

    # ===== STEP 7: Circuit Breakers (depends on: provider_registry) =====
    circuit_breakers: Dict[str, CircuitBreaker] = {}
    # Will be populated as providers are registered

    # ===== STEP 8: ContextBuilder (depends on: state_reader, prompt_system) =====
    context_builder = ContextBuilder(
        state_reader=state_reader,
        prompt_system=prompt_system
    )

    # ===== STEP 9: ProviderFactory (depends on: ALL PORTS + context_builder) =====
    provider_factory = ProviderFactory(
        registry=registry,
        bridge_port=bridge,
        model_gateway=model_gateway,
        state_reader=state_reader,
        delta_bus=delta_bus,
        context_builder=context_builder,
        tool_scope=tool_scope,
        circuit_breakers=circuit_breakers  # shared reference, will be populated
    )

    # ===== STEP 10: Provider Resolution =====
    provider_matcher = ProviderMatcher(registry=registry)
    provider_selector = ProviderSelector()

    resolver = Resolver(
        registry=registry,
        provider_registry=provider_registry,
        provider_matcher=provider_matcher,
        policy_engine=policy_engine,
        provider_selector=provider_selector,
        provider_factory=provider_factory
    )

    # ===== STEP 11: Retrieval subsystem (depends on: registry) =====
    embedding_index = EmbeddingIndex()
    hard_filter = HardFilter(state_reader=state_reader)
    soft_ranker = SoftRanker(
        embedding_index=embedding_index,
        registry=registry
    )
    top_k_selector = TopKSelector()

    retrieval_engine = RetrievalEngine(
        registry=registry,
        embedding_index=embedding_index,
        hard_filter=hard_filter,
        soft_ranker=soft_ranker,
        top_k_selector=top_k_selector,
        state_reader=state_reader
    )

    # ===== STEP 12: OutputValidationPipeline =====
    structural_validator = StructuralValidator()
    schema_validator = SchemaValidator()
    semantic_validator = SemanticValidator(state_reader=state_reader)
    validation_fallback = ValidationFallback()

    validation_pipeline = OutputValidationPipeline(
        structural=structural_validator,
        schema=schema_validator,
        semantic=semantic_validator,
        fallback=validation_fallback,
        event_port=event_port
    )

    # ===== STEP 13: HealthChecker & AvailabilityTracker =====
    availability_tracker = AvailabilityTracker(registry=registry)

    health_checker = HealthChecker(
        provider_registry=provider_registry,
        availability_tracker=availability_tracker,
        circuit_breakers=circuit_breakers,  # bidirectional reference
        event_port=event_port
    )

    # ===== STEP 14: Wire HealthChecker ↔ CircuitBreaker bidirectional callbacks =====
    # (Each CB gets reference to health_checker, health_checker gets CB map)

    # ===== STEP 15: FabricMailbox (OPTIONAL - production mode only) =====
    mailbox = None
    if production_mode:
        timeout_guard = TimeoutGuard()
        mailbox = FabricMailbox(
            max_concurrent=10,
            timeout_guard=timeout_guard,
            event_port=event_port
        )

    # ===== STEP 16: EventEmitter =====
    event_emitter = EventEmitter(event_port=event_port)

    # ===== STEP 17: FabricFacade (MAIN API) =====
    fabric_facade = FabricFacade(
        resolver=resolver,
        context_builder=context_builder,
        validation_pipeline=validation_pipeline,
        event_emitter=event_emitter,
        registry=registry,
        mailbox=mailbox  # None in standalone/testing modes
    )

    # ===== STEP 18: FabricRetrieval (RETRIEVAL API) =====
    fabric_retrieval = FabricRetrieval(
        retrieval_engine=retrieval_engine
    )

    # ===== STEP 19: CapabilityRegistryAPI =====
    registry_api = CapabilityRegistryAPI(registry=registry)

    # ===== STEP 20: Bootstrap registry & start background services =====
    # Scan k1/contracts/ directory
    module_loader.scan_directory("k1/contracts/")

    # Start health checker periodic loop
    health_checker.start_periodic_loop()

    # Wire event subscriptions
    event_port.subscribe("k1.mcp.tool.discovered.v1", module_loader.register_from_dict)
    # ... more subscriptions for proactive gap detection, learning signals, etc.

    # ===== RETURN FABRIC INSTANCE =====
    return Fabric(
        facade=fabric_facade,
        retrieval=fabric_retrieval,
        registry_api=registry_api,
        registry=registry,
        module_loader=module_loader,
        health_checker=health_checker,
        event_port=event_port
    )
```

---

## The Three Factory Methods

### 1. create_standalone()

**Purpose**: Development/testing with NO external dependencies
**Usage**: Unit tests, examples, local development

```python
@staticmethod
def create_standalone() -> Fabric:
    """
    Creates Fabric with all test adapters.
    No external dependencies (SessionState, Bridge, LLM, etc.)
    """
    # Create test adapters
    state_reader = TestSessionStateReaderAdapter()
    event_port = LocalEventAdapter(capture_mode=False)
    bridge = TestBridgeAdapter()
    model_gateway = TestModelGatewayAdapter()
    prompt_system = TestPromptSystemAdapter()
    delta_bus = TestDeltaBusAdapter()

    # NO mailbox (direct execute)
    return _construct_fabric(
        state_reader=state_reader,
        event_port=event_port,
        bridge=bridge,
        model_gateway=model_gateway,
        prompt_system=prompt_system,
        delta_bus=delta_bus,
        production_mode=False
    )
```

---

### 2. create_for_testing()

**Purpose**: Integration tests with event capture
**Usage**: Contract tests, integration tests, test assertions on events

```python
@staticmethod
def create_for_testing(capture_events: bool = True) -> Fabric:
    """
    Creates Fabric with test adapters + event capture mode.
    Suitable for integration tests where you want to assert on events.
    """
    # Create test adapters
    state_reader = TestSessionStateReaderAdapter()
    event_port = LocalEventAdapter(capture_mode=capture_events)  # CAPTURE MODE
    bridge = TestBridgeAdapter()
    model_gateway = TestModelGatewayAdapter()
    prompt_system = TestPromptSystemAdapter()
    delta_bus = TestDeltaBusAdapter()

    # NO mailbox (direct execute)
    return _construct_fabric(
        state_reader=state_reader,
        event_port=event_port,
        bridge=bridge,
        model_gateway=model_gateway,
        prompt_system=prompt_system,
        delta_bus=delta_bus,
        production_mode=False
    )
```

---

### 3. create_with_ports()

**Purpose**: Production deployment with custom adapters
**Usage**: Real deployment with live SessionState, K0 Bridge, LLM access

```python
@staticmethod
def create_with_ports(
    state_reader: ISessionStateReader,
    event_port: IEventPort,
    bridge: IBridgePort,
    model_gateway: IModelGatewayPort,
    prompt_system: IPromptSystemPort,
    delta_bus: IDeltaBusPort,
    production_mode: bool = False
) -> Fabric:
    """
    Creates Fabric with custom adapter injection.
    For production deployment.

    Args:
        production_mode: If True, adds FabricMailbox for bounded parallelism
    """
    return _construct_fabric(
        state_reader=state_reader,
        event_port=event_port,
        bridge=bridge,
        model_gateway=model_gateway,
        prompt_system=prompt_system,
        delta_bus=delta_bus,
        production_mode=production_mode  # Adds mailbox if True
    )
```

---

## FabricFacade Execution Pipeline

**File**: `k1/fabric/fabric.py` (Epic 5.3.2)
**Status**: ❌ TODO - **THIS IS WHAT YOU NEED TO IMPLEMENT**

**Class**: `CapabilityFabric` (main API from fabric_discussion.md Section 15)

```python
class CapabilityFabric:
    """
    Main execution API (Role 2).
    Stateless, deterministic, policy-driven capability execution.
    """

    def __init__(
        self,
        resolver: Resolver,
        context_builder: ContextBuilder,
        validation_pipeline: OutputValidationPipeline,
        event_emitter: EventEmitter,
        registry: CapabilityRegistry,
        mailbox: Optional[FabricMailbox] = None
    ):
        self.resolver = resolver
        self.context_builder = context_builder
        self.validation_pipeline = validation_pipeline
        self.event_emitter = event_emitter
        self.registry = registry
        self.mailbox = mailbox

    async def execute(self, request: CapabilityRequest) -> CapabilityResult:
        """
        Execute a single capability request.

        Pipeline (9 steps):
        1. Emit invoked event
        2. Resolve provider (Registry → Policy → Selector → Factory)
        3. Build context (SessionState + prompts + budget)
        4. Execute via CircuitBreaker
        5. Validate output (3-tier pipeline)
        6. Emit completed/failed event
        7. Update metrics
        8. Emit learning signal
        9. Return result
        """
        ...

    async def execute_batch(
        self,
        requests: List[CapabilityRequest],
        strategy: BatchStrategy = BatchStrategy.PARALLEL
    ) -> List[CapabilityResult]:
        """
        Execute batch of requests with specified strategy.

        BatchStrategy:
        - PARALLEL: All at once (default)
        - SEQUENTIAL: Ordered execution
        - DAG: Dependency-aware (for Orchestrator wave execution)

        Partial failure handling:
        - Each request independent
        - Failed requests return CapabilityResult.failure()
        - Does NOT block other requests

        Ordering guarantee:
        - Results list matches input order (regardless of execution order)

        Backpressure:
        - Batch size capped at max_batch_size (default 50)

        Critical for: Orchestrator DAG wave execution where multiple
        capabilities execute in a single wave.
        """
        ...
```

### Execute Pipeline (IN ORDER)

```python
async def execute(self, request: CapabilityRequest) -> CapabilityResult:
    trace_id = request.trace_id or generate_trace_id()

    try:
        # ===== STEP 1: Emit invoked event =====
        await self.event_emitter.emit_invoked(request)

        # ===== STEP 2: Resolve provider =====
        # 2a. Registry.lookup(name)
        # 2b. ProviderMatcher → candidates
        # 2c. PolicyEngine.evaluate() → allowed + score
        #     - SecurityContext (hard gate - FIRST)
        #     - AffectiveRouting (soft)
        #     - CognitiveLoadRouting (soft)
        #     - QoSIntegration (soft)
        # 2d. ProviderSelector → best provider
        # 2e. ProviderFactory.instantiate() → provider instance
        resolved = await self.resolver.resolve(request)
        provider = resolved.provider_instance
        contract = resolved.contract

        # ===== STEP 3: Build context =====
        # - Read required_context from SessionState
        # - Resolve prompt templates
        # - Apply token budget (128K)
        context = await self.context_builder.build(request, contract)

        # ===== STEP 4: Execute via CircuitBreaker =====
        # CircuitBreaker wraps provider.execute()
        # Handles: timeout, retry, state transitions
        result = await provider.execute(request, context, trace_id)

        # ===== STEP 5: Validate output (3-tier pipeline) =====
        # Tier 1: StructuralValidator (hard fail)
        # Tier 2: SchemaValidator (hard fail, with coercion fallback)
        # Tier 3: SemanticValidator (soft fail, annotation only)
        validated_result = await self.validation_pipeline.validate(
            result, contract, context
        )

        # ===== STEP 6: Emit completed event =====
        await self.event_emitter.emit_completed(request, validated_result)

        # ===== STEP 7: Update metrics =====
        duration_ms = validated_result.metadata.get("duration_ms", 0)
        success = validated_result.success
        self.registry.update_metrics(request.capability_name, duration_ms, success)

        # ===== STEP 8: Emit learning signal (for K0 P09) =====
        await self.event_emitter.emit_learning_signal(
            capability_name=request.capability_name,
            provider_id=resolved.provider_id,
            success=success,
            duration_ms=duration_ms,
            error_code=validated_result.error.code if not success else None,
            context_quality_score=context.quality_score
        )

        # ===== STEP 9: Return result =====
        return validated_result

    except Exception as e:
        # Emit failed event
        await self.event_emitter.emit_failed(request, e)
        return CapabilityResult.failure(
            error=CapabilityError(
                code="EXECUTION_ERROR",
                message=str(e),
                retriable=True
            )
        )
```

### execute_batch() Semantics

```python
async def execute_batch(
    self,
    requests: List[CapabilityRequest],
    strategy: BatchStrategy = BatchStrategy.PARALLEL
) -> List[CapabilityResult]:
    """
    Execute batch of requests with specified strategy.
    """
    # Validate batch size
    if len(requests) > self.max_batch_size:
        raise ValueError(f"Batch size {len(requests)} exceeds max {self.max_batch_size}")

    if strategy == BatchStrategy.PARALLEL:
        # Execute all concurrently
        tasks = [self.execute(req) for req in requests]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    elif strategy == BatchStrategy.SEQUENTIAL:
        # Execute in order
        results = []
        for req in requests:
            result = await self.execute(req)
            results.append(result)

    elif strategy == BatchStrategy.DAG:
        # Dependency-aware execution
        # (Orchestrator provides dependency graph in request metadata)
        dag = self._extract_dag(requests)
        results = await self._execute_dag(dag)

    else:
        raise ValueError(f"Unknown strategy: {strategy}")

    # Ensure results match input order
    return results
```

---

## FabricRetrieval (Epic 5.3.3)

**File**: `k1/fabric/fabric.py`
**Status**: ❌ TODO - **NEEDS IMPLEMENTATION**

```python
class FabricRetrieval:
    """
    Retrieval API (Role 1).
    Separate class for capability discovery.
    """

    def __init__(self, retrieval_engine: RetrievalEngine):
        self.retrieval_engine = retrieval_engine

    async def discover_capabilities(
        self,
        domain: str,
        intent: str,
        safety_band: SafetyBand,
        session_context: Dict[str, Any],
        top_k: int = 10
    ) -> RetrievalResult:
        """
        Discover capabilities matching domain + intent.

        Pipeline:
        1. Embed query (domain + intent)
        2. HardFilter (safety, availability, input satisfiability)
        3. SoftRank (semantic + domain + success + cost/latency)
        4. TopK selection

        Returns: RetrievalResult with list[ScoredCapability]
        """
        return await self.retrieval_engine.discover_capabilities(
            domain=domain,
            intent=intent,
            safety_band=safety_band,
            session_context=session_context,
            top_k=top_k
        )

    async def find_relevant_prompts(
        self,
        intent: str,
        domain: str,
        safety_band: SafetyBand,
        top_k: int = 10
    ) -> RetrievalResult:
        """
        Find relevant prompt templates for intent.

        Same pipeline as discover_capabilities, but filters for
        PromptContract types only.
        """
        return await self.retrieval_engine.find_relevant_prompts(
            intent=intent,
            domain=domain,
            safety_band=safety_band,
            top_k=top_k
        )
```

---

## CapabilityRegistryAPI (Epic 5.3.4)

**File**: `k1/fabric/fabric.py`
**Status**: ❌ TODO - **NEEDS IMPLEMENTATION**

```python
class CapabilityRegistryAPI:
    """
    Registry management API.
    Thin wrapper over core Registry.
    """

    def __init__(self, registry: CapabilityRegistry):
        self.registry = registry

    def register(self, contract: CapabilityContract) -> None:
        """Register capability (validates first)"""
        self.registry.register(contract)

    def unregister(self, name: str) -> None:
        """Unregister capability"""
        self.registry.unregister(name)

    def lookup(self, name: str, version: Optional[Version] = None) -> CapabilityContract:
        """O(1) exact lookup"""
        return self.registry.lookup(name, version)

    def list_by_domain(self, domain: str) -> List[CapabilityContract]:
        """List all capabilities in domain"""
        return self.registry.list_by_domain(domain)

    def list_by_type(self, type_prefix: str) -> List[CapabilityContract]:
        """List by type (e.g., 'agent.', 'tool.')"""
        return self.registry.list_by_type(type_prefix)

    def update_availability(self, name: str, status: Availability) -> None:
        """Update availability status"""
        self.registry.update_availability(name, status)

    def update_metrics(self, name: str, latency_ms: float, success: bool) -> None:
        """Update running metrics"""
        self.registry.update_metrics(name, latency_ms, success)

    def reload(self) -> None:
        """Full reload from disk"""
        self.registry.reload()

    def health(self) -> RegistryHealth:
        """Registry health snapshot"""
        return self.registry.health()
```

---

## Critical Wiring Constraints

These 13 invariants MUST be enforced through wiring:

| Invariant | Enforcement Point | Wiring Detail |
|-----------|-------------------|---------------|
| **FAB-01** (No writes to SessionState) | AgentFactory | ISessionStateReader only (no IStateWritePort). Delta emission via IDeltaBusPort → Delta Bus → Concierge |
| **FAB-02** (No LLM calls) | ProviderFactory | No ILLMPort. Agents access LLM via IModelGatewayPort (5.1.4) only |
| **FAB-03** (Stateless per-request) | FabricFacade | No instance state held between execute() calls |
| **FAB-04** (Timeout 30s) | CircuitBreaker | Per-provider config enforced in 3.4.2. Default 30s. |
| **FAB-05** (Filter before rank) | RetrievalEngine | HardFilter runs before SoftRanker in pipeline |
| **FAB-06** (Safety check) | PolicyEngine | SecurityContext runs FIRST in 4-dimension scoring |
| **FAB-07** (Tool scope) | AgentFactory | ToolScope validation in step 5 of instantiation |
| **FAB-08** (128K budget) | ContextBuilder | ContextBudget enforcement with compression strategies |
| **FAB-09** (Trace IDs) | EventEmitter | cognitive_trace_id added by EventEmitter.emit_*() methods |
| **FAB-10** (Deterministic) | ProviderSelector | Tie-breaking rules: latency, then alphabetical |
| **FAB-11** (Name conventions) | ContractValidator | Rule in validation enforces naming patterns |
| **FAB-12** (Validate before register) | Registry | register() calls ContractValidator (2.1.1) before insert |
| **FAB-13** (Performance SLIs) | Benchmarks | <1ms registry, <50ms retrieval, <100ms overhead (from 1.2.3) |

---

## Bidirectional Wiring Examples

### Example 1: Health Checker ↔ Circuit Breaker Loop

```python
# HealthChecker runs periodic loop (every 30s)
HealthChecker.health_check_loop()
  ↓ (monitoring)
CircuitBreaker state
  ↓ (when CB OPEN)
HealthChecker triggers immediate check
  ↓ (if health success)
HealthChecker signals CB to try HALF_OPEN
  ↓ (CB tries one request)
Provider recovers → CB transitions CLOSED
```

**Wiring in FabricFactory**:

```python
# Step 13: Create HealthChecker with CB reference
health_checker = HealthChecker(
    provider_registry=provider_registry,
    availability_tracker=availability_tracker,
    circuit_breakers=circuit_breakers,  # bidirectional reference
    event_port=event_port
)

# Step 14: Each CB gets reference to health_checker
for provider_id, cb in circuit_breakers.items():
    cb.set_health_checker(health_checker)
```

---

### Example 2: Registry → EmbeddingIndex → RetrievalEngine

```python
ModuleLoader.scan_directory() loads YAML
  ↓
Registry.register(contract) saves to by_name index
  ↓
EmbeddingIndex.add_vector(contract_id, text) indexes for semantic search
  ↓
RetrievalEngine.discover_capabilities() queries EmbeddingIndex + Registry
```

**Wiring in FabricFactory**:

```python
# Step 3: Create Registry
registry = CapabilityRegistry(validator=validator, event_port=event_port)

# Step 11: Create EmbeddingIndex
embedding_index = EmbeddingIndex()

# Wire registry to embedding index (on register/unregister)
registry.on_register(embedding_index.add_vector)
registry.on_unregister(embedding_index.remove_vector)

# Step 11: Create RetrievalEngine with both
retrieval_engine = RetrievalEngine(
    registry=registry,
    embedding_index=embedding_index,
    ...
)
```

---

### Example 3: AgentFactory 8-Step Instantiation

```python
FabricFactory.create_with_ports() injects:
  ├── IModelGatewayPort → AgentFactory step 3
  ├── ISessionStateReader → AgentFactory step 4
  ├── IDeltaBusPort → Agent.execute() delta emission
  ├── IPromptSystemPort → ContextBuilder step 4
  ├── ContextBuilder → AgentFactory step 6
  └── ToolScope → AgentFactory step 5
```

**Wiring in FabricFactory**:

```python
# Step 8: Create ContextBuilder with ports
context_builder = ContextBuilder(
    state_reader=state_reader,
    prompt_system=prompt_system
)

# Step 9: Create ProviderFactory with ALL ports
provider_factory = ProviderFactory(
    registry=registry,
    bridge_port=bridge,
    model_gateway=model_gateway,      # → AgentFactory step 3
    state_reader=state_reader,        # → AgentFactory step 4
    delta_bus=delta_bus,              # → Agent delta emission
    context_builder=context_builder,  # → AgentFactory step 6
    tool_scope=tool_scope,            # → AgentFactory step 5
    circuit_breakers=circuit_breakers
)
```

---

## Component Dependency Matrix

| Component | ISessionStateReader | IEventPort | IBridgePort | IModelGatewayPort | IPromptSystemPort | IDeltaBusPort |
|-----------|---------------------|------------|-------------|-------------------|-------------------|---------------|
| PolicyEngine | ✓ (affective/cog) | ✗ | ✗ | ✗ | ✗ | ✗ |
| ContextBuilder | ✓ (read sections) | ✗ | ✗ | ✗ | ✓ (resolve) | ✗ |
| SemanticValidator | ✓ (beliefs) | ✗ | ✗ | ✗ | ✗ | ✗ |
| AgentFactory | ✓ (step 4) | ✗ | ✗ | ✓ (step 3) | ✓ (via CB) | ✓ (deltas) |
| Agent | ✓ (via SF) | ✗ | ✗ | ✓ (via GW) | ✗ | ✓ (emit) |
| BridgeProvider | ✗ | ✗ | ✓ (route ops) | ✗ | ✗ | ✗ |
| Registry | ✗ | ✓ (events) | ✗ | ✗ | ✗ | ✗ |
| ModuleLoader | ✗ | ✓ (events) | ✗ | ✗ | ✗ | ✗ |
| CircuitBreaker | ✗ | ✓ (state) | ✗ | ✗ | ✗ | ✗ |
| HealthChecker | ✗ | ✓ (health) | ✗ | ✗ | ✗ | ✗ |
| OutputValidation | ✓ (semantic) | ✓ (failed) | ✗ | ✗ | ✗ | ✗ |
| FabricMailbox | ✗ | ✓ (pressure) | ✗ | ✗ | ✗ | ✗ |

---

## Implementation Checklist

### ✅ COMPLETED (Already Implemented)

**Epic 5.1: Ports** (All 6 ports)

- ✅ 5.1.1 ISessionStateReader
- ✅ 5.1.2 IEventPort
- ✅ 5.1.3 IBridgePort
- ✅ 5.1.4 IModelGatewayPort
- ✅ 5.1.5 IPromptSystemPort
- ✅ 5.1.6 IDeltaBusPort

**Epic 5.2: Adapters**

- ✅ 5.2.1 SessionStateReaderAdapter (production)
- ✅ 5.2.2 TestSessionStateReaderAdapter
- ✅ 5.2.3 LocalEventAdapter
- ✅ 5.2.4 TestBridgeAdapter
- ✅ 5.2.5 TestModelGatewayAdapter
- ✅ 5.2.6 TestPromptSystemAdapter
- ⚠️ 5.2.7 TestDeltaBusAdapter (may exist, needs verification)
- ⚠️ 5.2.8 BridgeConnectionAdapter (production - needs verification)

**M2: Contract System**

- ✅ 2.1.1 ContractValidator
- ✅ 2.1.2 Contract Parsers
- ✅ 2.2.1 CapabilityRegistry
- ✅ 2.3.1 ModuleLoader

**M3: Provider Resolution & Execution**

- ✅ 3.1.1 ProviderRegistry
- ✅ 3.1.2 ProviderMatcher
- ✅ 3.1.3 ProviderSelector
- ✅ 3.1.4 ProviderFactory
- ✅ 3.1.5 Resolver
- ✅ 3.2.5 PolicyEngine (with all 4 dimensions + ToolScope)
- ✅ 3.3.2 MCPProvider
- ✅ 3.3.3 WASMProvider
- ✅ 3.3.4 BridgeProvider
- ✅ 3.3.5 WorkflowProvider
- ✅ 3.3.6 ConciergeProvider
- ✅ 3.3.7 AgentProvider
- ✅ 3.4.1 CircuitBreaker
- ✅ 3.5.1 OutputValidationPipeline (3-tier)
- ✅ 3.6.1 HealthChecker
- ✅ 3.6.2 AvailabilityTracker

**M4: Retrieval & Context**

- ✅ 4.1.1 EmbeddingIndex
- ✅ 4.1.2 HardFilter
- ✅ 4.1.3 SoftRanker
- ✅ 4.1.4 TopKSelector
- ✅ 4.1.5 RetrievalEngine
- ✅ 4.2.1 ContextBuilder
- ✅ 4.2.2 ContextBudget
- ✅ 4.3.1 AgentFactory
- ✅ 4.3.2 Agent
- ✅ 4.3.3 AgentPool
- ✅ 4.4.1 FabricMailbox
- ✅ 4.4.2 TimeoutGuard

---

### ❌ TODO (Epic 5.3 - YOUR TASK)

**Epic 5.3.1: FabricFactory** (PRIORITY 1)

- ❌ Create `k1/fabric/factory.py`
- ❌ Implement `create_standalone()`
- ❌ Implement `create_for_testing()`
- ❌ Implement `create_with_ports()`
- ❌ Implement `_construct_fabric()` with 20-step construction order
- ❌ Wire bidirectional HealthChecker ↔ CircuitBreaker callbacks
- ❌ Wire Registry → EmbeddingIndex event subscriptions
- ❌ Wire event subscriptions (k1.mcp.tool.discovered.v1, etc.)
- ❌ Bootstrap registry from k1/contracts/
- ❌ Start HealthChecker periodic loop

**Epic 5.3.2: FabricFacade** (PRIORITY 2)

- ❌ Create `k1/fabric/fabric.py` with `CapabilityFabric` class
- ❌ Implement `execute(request) -> CapabilityResult` (9-step pipeline)
- ❌ Implement `execute_batch(requests, strategy) -> List[CapabilityResult]`
- ❌ Add BatchStrategy enum (PARALLEL, SEQUENTIAL, DAG)
- ❌ Wire OutputValidationPipeline into execution path
- ❌ Implement partial failure handling
- ❌ Implement ordering guarantee (results match input order)
- ❌ Implement backpressure (max_batch_size=50)
- ❌ Enforce FAB-03 (stateless per-request)
- ❌ Enforce FAB-04 (circuit breaker timeout)
- ❌ Enforce FAB-09 (event emission with trace_id)

**Epic 5.3.3: FabricRetrieval** (PRIORITY 3)

- ❌ Add `FabricRetrieval` class to `k1/fabric/fabric.py`
- ❌ Implement `discover_capabilities()` (delegate to RetrievalEngine)
- ❌ Implement `find_relevant_prompts()` (delegate to RetrievalEngine)

**Epic 5.3.4: CapabilityRegistryAPI** (PRIORITY 4)

- ❌ Add `CapabilityRegistryAPI` class to `k1/fabric/fabric.py`
- ❌ Implement thin wrapper methods (register, unregister, lookup, etc.)

**Epic 5.4: Event Emitter** (PRIORITY 5)

- ❌ Create `k1/fabric/events/event_emitter.py`
- ❌ Implement `EventEmitter` class wrapping IEventPort
- ❌ Add methods: emit_invoked, emit_completed, emit_failed, emit_learning_signal
- ❌ Enforce FAB-09 (cognitive_trace_id on every event)

**Epic 5.5: Final Integration** (PRIORITY 6)

- ❌ Create integration tests using `create_for_testing()`
- ❌ Test all 3 factory methods
- ❌ Test execute() pipeline end-to-end
- ❌ Test execute_batch() with all 3 strategies
- ❌ Test partial failure handling
- ❌ Test backpressure scenarios
- ❌ Test bidirectional HealthChecker ↔ CircuitBreaker loop
- ❌ Verify all 13 FAB invariants

---

## Summary

This document provides **complete end-to-end wiring guidance** for implementing Epic 5.3:

1. **Section I-II**: Understand the 6 ports and their adapters
2. **Section III**: Study the full dependency graph (Layers 1-8)
3. **Section IV**: Follow the 20-step FabricFactory construction order
4. **Section V**: Implement the 3 factory methods
5. **Section VI**: Implement FabricFacade.execute() 9-step pipeline
6. **Section VII**: Wire critical constraints (FAB-01 to FAB-13)
7. **Section VIII**: Study bidirectional wiring examples
8. **Section IX**: Use dependency matrix for port injection
9. **Section X**: Follow implementation checklist

**Key Insight**: FabricFactory is the **composition root**. All wiring happens there. Once the factory is implemented, FabricFacade/FabricRetrieval/CapabilityRegistryAPI are thin delegates.

**Critical Success Factor**: Follow the 20-step construction order EXACTLY. Dependency violations will cause runtime errors.

---

**Good luck with the implementation! 🚀**
