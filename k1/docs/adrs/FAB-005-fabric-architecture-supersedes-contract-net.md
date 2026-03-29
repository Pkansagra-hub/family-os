---
adr_id: FAB-005
title: "Capability Fabric Architecture (Supersedes Contract-Net)"
status: Accepted
date: 2026-02-06
module: fabric
layer: "L2"
authors: []
related_adrs:
  - "FAB-001"
  - "FAB-002"
  - "FAB-003"
  - "FAB-004"
  - "FAB-006"
  - "FAB-007"
  - "FAB-008"
  - "FAB-009"
related_events:
  - "k1.fabric.capability.requested.v1"
  - "k1.fabric.capability.resolved.v1"
  - "k1.fabric.capability.executed.v1"
  - "k1.fabric.capability.registered.v1"
  - "k1.fabric.retrieval.query.v1"
related_contracts:
  - "k1/contracts/schemas/modules/fabric/module.contract.yaml"
related_ports:
  - "ISessionStateReader"
  - "IEventPort"
  - "IBridgePort"
  - "IModelGatewayPort"
  - "IPromptSystemPort"
implements_issue: "1.1.1, 1.1.2"
superseded_by: ""
tags:
  - architecture
  - fabric
  - resolution
  - retrieval
  - agent-factory
  - foundation
---

# FAB-005: Capability Fabric Architecture (Supersedes Contract-Net)

## Context

### Problem Statement

The original K1 architecture (ADR-0006, ADR-K004) used the Contract-Net Protocol for capability negotiation: Orchestrator announces tasks, agents bid, best bid wins. This was designed when K1 had 58 statically-defined agents. The Capability Fabric replaces this with a more scalable pattern: centralized registry + semantic retrieval + deterministic resolution + dynamic agent factory.

ADR-K004 (referenced in governance but no file found) needs to be formally superseded.

### What Changed Since ADR-0006/K004

| Aspect | Old (Contract-Net) | New (Capability Fabric) |
|--------|-------------------|------------------------|
| Discovery | Broadcast task announcement, agents bid | Semantic retrieval (FAISS + UltraBERT 768d) + exact name lookup |
| Selection | Hiring Agent scores bids via LLM | Deterministic soft ranking (0.4 semantic + 0.3 domain + 0.15 success + 0.15 cost) |
| Agent Creation | Static 58-agent pool | Dynamic Agent Factory spawns from YAML templates |
| Provider Types | Only actors | 6 types: MCP, WASM, Bridge, Agent, Workflow, Concierge |
| LLM Usage | Hiring Agent uses LLM to score bids | Fabric has NO LLM (FAB-02 invariant). Fully deterministic. |
| Statefulness | Agents maintain state | Fabric is stateless per-request (FAB-03 invariant) |
| Execution | Agent executes autonomously | Fabric routes to provider runtime, returns CapabilityResult |

### Legacy ADR-0006 (3-Phase Orchestration) Content

ADR-0006 defines 3-phase orchestration: (1) Task Announcement, (2) Agent Bidding, (3) Winner Selection. This pattern is still valid for the Orchestrator's DAG walking, but Capability Fabric replaces the "how to find and invoke a capability" part. The Orchestrator now calls `Fabric.execute(CapabilityRequest)` instead of broadcasting to agents.

### Constraints

- Must be backward-compatible with existing Orchestrator DAG walking pattern
- Must preserve all 13 Fabric invariants (FAB-01 through FAB-13)
- Must support hexagonal architecture (5 port interfaces)
- Must be independently testable without other K1 modules

---

## Decision

### Chosen Approach

Capability Fabric replaces Contract-Net Protocol for all capability resolution, retrieval, and execution. The architecture has three roles and seven subsystems.

### Three Roles

| Role | Serves | Pattern | Latency Budget |
|------|--------|---------|----------------|
| Role 1: Intelligent Retrieval | Planner (HIGH tier) | Semantic Top-K via FAISS + UltraBERT | <50ms per query |
| Role 2: Resolution + Execution | Orchestrator + Concierge (ALL tiers) | Exact name lookup -> policy check -> provider dispatch | <100ms overhead |
| Role 3: Agent Factory | Plan steps with agent.* types | YAML template -> spawn -> scoped tools -> execute | <250ms cold start |

### Seven Subsystems

| # | Subsystem | Directory | Key Classes |
|---|-----------|-----------|-------------|
| 1 | Contract System | `contracts/` | ContractValidator, ToolContractParser, AgentContractParser, PromptContractParser, WorkflowContractParser |
| 2 | Capability Registry | `core/` | CapabilityRegistry (by_name, by_domain, by_type, by_provider indexes) |
| 3 | Semantic Retrieval Engine | `retrieval/` | EmbeddingIndex (FAISS), HardFilter, SoftRanker |
| 4 | Provider Resolution Engine | `provider_resolution/` | ProviderResolver, ProviderSelector, ProviderFactory |
| 5 | Policy Engine | `policy/` | SecurityContext, AffectiveRouting, CognitiveLoadRouting, QoSIntegration |
| 6 | Execution Runtime | `providers/` | MCPProvider, WASMProvider, BridgeProvider, AgentProvider, WorkflowProvider, ConciergeProvider |
| 7 | Context Builder | `core/` | ContextBuilder (reads SessionState, 128K token budget) |

### 13 Hard Invariants

| ID | Invariant |
|----|-----------|
| FAB-01 | Fabric NEVER writes to SessionState |
| FAB-02 | Fabric NEVER calls an LLM |
| FAB-03 | Fabric is stateless per-request |
| FAB-04 | Every execution returns CapabilityResult within circuit breaker timeout (30s) |
| FAB-05 | Hard filters run BEFORE soft ranking (safety first) |
| FAB-06 | Safety band access is ALWAYS checked before provider execution |
| FAB-07 | Sub-Agent tool access is scoped to plan-specified tools_granted[] only |
| FAB-08 | Context Builder respects 128K token budget for agent context |
| FAB-09 | All Fabric events emitted on K1 Event Bus with cognitive_trace_id |
| FAB-10 | Provider selection is deterministic given same inputs + same registry state |
| FAB-11 | Capability names follow type conventions |
| FAB-12 | All contracts validated against schema before registration |
| FAB-13 | Registry lookup <1ms, Retrieval <50ms, Full overhead <100ms P95 |

### Rationale

Contract-Net worked for the original 58-agent static pool but does not scale to:

- Dynamic agent creation from templates
- 6 provider types (not just actors)
- Semantic discovery across 100K+ capabilities
- Deterministic resolution without LLM
- Sub-50ms retrieval latency requirements

Fabric centralizes all resolution/execution logic so Concierge, Orchestrator, and Planner remain clean.

---

## Alternatives Considered

### Alternative 1: Keep Contract-Net Protocol (Status Quo)

**Rejected because:**

- Requires Hiring Agent LLM call for every capability selection (violates FAB-02)
- O(N) broadcast to all agents for discovery (vs O(1) registry lookup)
- Cannot support MCP/WASM/Bridge providers (only actor-based agents)
- No semantic search (keyword match only)

### Alternative 2: Service Mesh (Istio/Envoy-style)

**Rejected because:**

- K1 is single-process, not microservices
- Adds network overhead for in-memory calls
- Overkill for on-device kernel

### Alternative 3: Plugin Registry (VS Code Extension-style)

**Rejected because:**

- Good for static plugins, not dynamic agent spawning
- No semantic retrieval
- No policy engine integration

---

## Consequences

### Positive

- Single entry point for all capability operations (execute, discover, register)
- Deterministic and auditable (no LLM in resolution path)
- Supports 6 provider types vs only actors
- Semantic retrieval enables 100K+ capability scale
- Hexagonal ports enable independent development and testing

### Negative

- More complex than Contract-Net for simple cases
- Registry must be kept in sync with provider availability
- Centralized point of failure (mitigated by circuit breakers)

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Registry becomes bottleneck | Low | High | Thread-safe RLock, O(1) lookups, no blocking I/O |
| Stale availability data | Medium | Medium | Health checker polls providers, circuit breaker updates availability |
| FAISS index corruption | Low | High | Rebuild from registry on startup; incremental add only |

---

## Implementation

### Affected Code Paths

| Component | File | Change Type |
|-----------|------|-------------|
| CapabilityFabric (facade) | `k1/fabric/core/fabric.py` | New |
| CapabilityRegistry | `k1/fabric/core/registry.py` | New |
| ContractValidator | `k1/fabric/core/module_validator.py` | New |
| ProviderResolver | `k1/fabric/provider_resolution/resolver.py` | New |
| EmbeddingIndex | `k1/fabric/retrieval/embedding_index.py` | New |
| PolicyEngine | `k1/fabric/policy/engine.py` | New |
| AgentProvider | `k1/fabric/providers/agent_provider.py` | New |
| MCPProvider | `k1/fabric/providers/mcp_provider.py` | New |

### Events Emitted/Consumed

| Event Topic | Direction | Description |
|-------------|-----------|-------------|
| `k1.fabric.capability.requested.v1` | Emitted | Every execute() call |
| `k1.fabric.capability.resolved.v1` | Emitted | Provider selected |
| `k1.fabric.capability.executed.v1` | Emitted | Result returned |
| `k1.fabric.capability.registered.v1` | Emitted | New contract registered |
| `k1.fabric.capability.unregistered.v1` | Emitted | Contract removed |
| `k1.fabric.retrieval.query.v1` | Emitted | Semantic search executed |
| `k1.fabric.provider.health.changed.v1` | Emitted | Provider went DEGRADED/OFFLINE |

### Port/Adapter Impact

| Port | Purpose | Production Adapter | Test Adapter |
|------|---------|-------------------|--------------|
| `ISessionStateReader` | Read-only context for Context Builder | `SessionStateReadAdapter` | `TestSessionStateAdapter` |
| `IEventPort` | Emit Fabric events | `K1EventBusAdapter` | `LocalEventAdapter` (capture) |
| `IBridgePort` | Bridge provider + K0 communication | `BridgeConnectionAdapter` | `TestBridgeAdapter` |
| `IModelGatewayPort` | LLM access for spawned agents | `ModelGatewayAdapter` | `TestModelGatewayAdapter` |
| `IPromptSystemPort` | Prompt resolution + compilation | `PromptSystemAdapter` | `TestPromptAdapter` |

### Testing Strategy

- [ ] Architecture compliance tests (13 invariants)
- [ ] Contract-Net migration tests (verify old patterns work through Fabric)
- [ ] Port isolation tests (each port independently testable)
- [ ] Subsystem integration tests (registry + retrieval + resolution)

---

## Amendment History

| Date | Author | Change |
|------|--------|--------|
| 2026-02-06 | - | Accepted: Establishes Fabric as replacement for Contract-Net. |
