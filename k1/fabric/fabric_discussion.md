# Capability Fabric -- K1 Kernel Design Document

> **Status**: Design Discussion
> **Date**: 2026-02-06
> **Layer**: L2.5 in K1 Cognitive Architecture Skeleton
> **Location**: `k1/fabric/`
> **Diagram**: `architecture_diagrams/k1/k1_cognitive_architecture_skeleton.mmd` (subgraph `L2_5_FABRIC`)
> **Governing Whiteboard**: `docs/architecture/whiteboard_k1/whiteboard_concierge_orchestrator_planner_fabric.md`
> **Related ADRs**: ADR-K004 (Capability Fabric Adaptation), ADR-0005 (Agent Lifecycle), ADR-0017 (Single Writer), ADR-0028 (Performance Scheduling)

---

## Table of Contents

1. [What is Capability Fabric](#1-what-is-capability-fabric)
2. [Where Fabric Sits in K1](#2-where-fabric-sits-in-k1)
3. [Three Roles of Fabric](#3-three-roles-of-fabric)
4. [Callers: Who Calls Fabric and Why](#4-callers-who-calls-fabric-and-why)
5. [Fabric Invariants (Non-Negotiable)](#5-fabric-invariants-non-negotiable)
6. [Subsystem 1: Capability Contract System](#6-subsystem-1-capability-contract-system)
7. [Subsystem 2: Capability Registry](#7-subsystem-2-capability-registry)
8. [Subsystem 3: Semantic Retrieval Engine](#8-subsystem-3-semantic-retrieval-engine)
9. [Subsystem 4: Provider Resolution Engine](#9-subsystem-4-provider-resolution-engine)
10. [Subsystem 5: Policy Engine](#10-subsystem-5-policy-engine)
11. [Subsystem 6: Execution Runtime (Providers)](#11-subsystem-6-execution-runtime-providers)
12. [Subsystem 7: Context Builder](#12-subsystem-7-context-builder)
13. [Agent Factory (Inside Execution Runtime)](#13-agent-factory-inside-execution-runtime)
14. [Message Envelopes and Schemas](#14-message-envelopes-and-schemas)
15. [Fabric API Surface (All Entrypoints)](#15-fabric-api-surface-all-entrypoints)
16. [Execution Flows Per Tier](#16-execution-flows-per-tier)
17. [Tool Execution Round-Trip (Complete Pipeline)](#17-tool-execution-round-trip-complete-pipeline)
18. [Workflow Integration](#18-workflow-integration)
19. [Error Handling and Circuit Breakers](#19-error-handling-and-circuit-breakers)
20. [Event Bus Integration](#20-event-bus-integration)
21. [Observability and Telemetry](#21-observability-and-telemetry)
22. [Performance Targets](#22-performance-targets)
23. [Security Model](#23-security-model)
24. [Dependency Graph and Build Order](#24-dependency-graph-and-build-order)
25. [Directory Structure (Target)](#25-directory-structure-target)
26. [Open Design Questions](#26-open-design-questions)

---

## 1. What is Capability Fabric

Capability Fabric is K1's central resolution, retrieval, and execution engine. It is the single runtime through which every tool invocation, agent spawn, and workflow execution flows. It has NO LLM. It never writes to SessionState. It is deterministic per-request and stateless per-invocation.

**One-sentence definition**: Fabric resolves a capability name to a concrete provider, builds execution context from SessionState, executes the provider via the appropriate runtime (MCP, WASM, Bridge, Agent), and returns a structured result.

**What Fabric is NOT**:

- It is NOT an orchestrator. The Orchestrator walks the DAG. Fabric executes individual steps.
- It is NOT a planner. The Planner decides what to do. Fabric does what it is told.
- It is NOT an LLM. Fabric is deterministic computation: lookup, filter, rank, route, execute.
- It is NOT a state writer. Fabric NEVER writes to SessionState (ADR-0017).

**Why it exists**: Without Fabric, every component (Concierge, Orchestrator, Planner, Sub-Agents) would need to know how to find tools, select providers, build context, handle MCP protocols, manage WASM sandboxes, route through Bridge, and spawn agents. Fabric centralizes all of that into one subsystem so the rest of K1 can remain clean.

---

## 2. Where Fabric Sits in K1

K1 is a layered cognitive kernel. Fabric is Layer 2.5, positioned between the coordination layer (Orchestrator/Planner at L2/L3) and the execution layer (Sub-Agents at L4).

```
L0  External Interfaces (Web, Mobile, Voice) -- detached, TBD
L1  Concierge (FSM, UltraBERT, Single Writer) -- user-facing intelligence
L2  Orchestrator (Blind DAG Executor, NO LLM)
L2.5  [CAPABILITY FABRIC] -- resolution + retrieval + execution
L3  Planner (LLM-powered, 4-stage pipeline, read-only discovery tools)
L4  Spawned Sub-Agents (created by Fabric, each has own LLM)
L5  SessionState (12-section, Single Writer, Multi-Reader)
L6  Cross-Kernel Bridge (K0 communication gateway)
```

### Position in the Request Flow

```
User input
  -> L1 Concierge (LISTENING -> ACKING -> DISPATCHING)
       |
       |-- LOW tier:  Concierge -> [FABRIC] -> result -> DELIVERING
       |-- MED tier:  Concierge -> Orchestrator -> [FABRIC] -> result -> DELIVERING
       |-- HIGH tier: Concierge -> Orchestrator -> Planner -> [FABRIC retrieval]
                                                    |
                                     CommittedPlan -> Orchestrator -> [FABRIC execution] -> result
                                                                                             -> DELIVERING
```

### Skeleton Diagram Reference

In `k1_cognitive_architecture_skeleton.mmd`, Fabric is the subgraph `L2_5_FABRIC` containing:

| Subgraph | Contents |
|---|---|
| `FABRIC_CORE` | CapabilityFabric, Fabric Mailbox, Registry, Loader, Resolver, Context Builder, Context Budget |
| `FABRIC_RETRIEVAL` | Semantic Search Engine, Top-K Ranker, Hard Filters, Soft Ranker |
| `FABRIC_PROVIDERS` | Agent Providers (58+), Tool Providers (MCP), Workflow Providers, Concierge Providers |
| `FABRIC_CONTRACTS` | Agent Contracts (YAML), Tool Contracts (YAML), Workflow Contracts, Versioning |
| `FABRIC_POLICY` | Affective Routing, Cognitive Load Routing, QoS Integration, Security Context |
| `MODULE_REGISTRY` | Module Loader, Contract Validator, Module Cache |
| `PROVIDER_RESOLUTION` | Provider Matcher, Provider Selector, Provider Factory, Hard Filter, Soft Ranker |
| `CAPABILITY_TYPES` | agent.spawn/execute, tool.execute/read, workflow.run, concierge.state |
| `MODEL_GATEWAY` | Model Router, Model Cache, Model Metrics |
| `PROMPT_MANAGEMENT` | Prompt System, Template Store, Resolver, Variable Injector, Version Controller, Compiler |
| `OUTPUT_VALIDATION` | Schema Hierarchy (FlatBuffers), 3-Tier Validation Pipeline, Hallucination Detector |

---

## 3. Three Roles of Fabric

Fabric serves three distinct, independent roles. A single request uses either Role 1 OR Role 2, never both simultaneously.

### Role 1: Intelligent Retrieval (Serves the Planner)

**When**: HIGH-tier tasks. Planner LLM calls discovery tools during Stages 1-2.

**What Fabric does**:

1. Receives a semantic query (e.g., `discover_capabilities(domain="restaurant", intent="book_reservation")`)
2. Embeds the query using the same embedding model that indexed the registry
3. Hard-filters the registry: eliminates capabilities where safety_band < user's band, availability == OFFLINE, or required_inputs cannot be satisfied from known context
4. Soft-ranks remaining candidates: semantic similarity (weight 0.4) + domain overlap (0.3) + success_rate_30d (0.15) + inverse cost/latency (0.15)
5. Returns Top-K results (default K=10) with full schemas

**Planner discovery tools that invoke Role 1**:

| Tool | Queries | Returns |
|---|---|---|
| `discover_capabilities(domain?, intent?)` | Tool + Agent registries | Top-K capabilities with input/output schemas |
| `find_relevant_prompts(intent?, domain?)` | Prompt Registry | Top-K prompt templates with variable definitions |

Note: `query_planning_context()` and `recall_for_planning()` do NOT go through Fabric -- they read SessionState and K0 Bridge directly.

### Role 2: Resolution and Execution (Serves Orchestrator and Concierge)

**When**: ALL tiers. Every actual tool/agent execution goes through this path.

**What Fabric does**:

1. Receives `CapabilityRequest{name, params, prompt_template?, context}`
2. **Resolve**: Looks up `name` in Capability Registry (exact match, not semantic)
3. **Select Provider**: Policy Engine picks the best provider from the resolved set
4. **Build Context**: Context Builder reads declared `required_context` sections from SessionState, applies 128K token budget (recency + relevance strategy)
5. **Execute**: Routes to the appropriate runtime (MCP Runner, WASM Sandbox, Bridge Client, Agent Spawn)
6. **Return**: `CapabilityResult{success, data, error, duration_ms}`

### Role 3: Agent Factory (Spawns Per-Step Workers)

**When**: Plan steps with `agent.execute.*` or `agent.spawn.*` capability types.

**What Fabric does**:

1. Looks up agent template in Agent Registry (e.g., `invitation_sender.yaml`)
2. Agent Factory instantiates:
   - Fresh MPSC Mailbox (Weighted Fair Queuing priority)
   - LLM access via Model Gateway
   - SessionState multi-reader access (lock-free, read-only)
   - Scoped tools: ONLY the `tools_granted[]` declared in the CommittedPlan step
   - Prompt template from the plan step (resolved + compiled by Prompt System)
   - Parameters from the plan step
3. Agent executes its task with its own LLM
4. Agent emits `CapabilityResult` back to Fabric
5. Agent lifecycle: PENDING -> WARMING -> ACTIVE -> IDLE (pool for reuse) or DRAINING -> TERMINATED

---

## 4. Callers: Who Calls Fabric and Why

Fabric is stateless per-request. It does not care who called it. But callers have different patterns:

### Concierge (LOW Tier -- Direct Fast Path)

```
Concierge LLM calls invoke_capability() action tool
  -> ToolDispatcher routes via IDispatchPort
  -> FabricOrchAdapter sends CapabilityRequest to Fabric
  -> Fabric resolves, builds context, executes
  -> CapabilityResult returns to Concierge
  -> Same LLM call generates response with tool_result
```

**Latency budget**: < 2 seconds total (Fabric portion < 1.5s)
**Concierge also queries**: `discover_capabilities()` via read tool for context, and `spawn_via_fabric()` for dynamic agents.

### Orchestrator (MEDIUM/HIGH Tier -- DAG Execution)

```
Orchestrator receives CommittedPlan (HIGH) or TaskEnvelope (MEDIUM)
  -> Topological walker identifies next steps
  -> For each step: CapabilityRequest{name, params, context} -> Fabric
  -> Fabric resolves, builds context, executes
  -> CapabilityResult returns to Orchestrator
  -> Orchestrator aggregates all step results
  -> Results flow to Concierge COMPANIONING via DeltaBus
```

**Latency budget**: 2-10s (MEDIUM) or 10-60s (HIGH)
**Multiple parallel Fabric calls**: Steps with no dependencies execute concurrently.

### Planner (HIGH Tier -- Discovery Only)

```
Planner LLM calls discover_capabilities(domain="restaurant")
  -> Planner Discovery Tool handler calls Fabric Retrieval API
  -> Fabric performs semantic Top-K search
  -> Returns top-10 relevant capabilities with schemas
  -> Planner LLM uses results to build plan steps
```

**Latency budget**: < 50ms per retrieval call (Planner makes 3-6 calls per plan)
**Read-only**: Planner NEVER triggers execution through Fabric.

### Sub-Agents (Spawned by Fabric, Use invoke_capability)

```
Sub-Agent (e.g., invitation_sender) needs to call a sub-tool
  -> Agent's scoped invoke_capability() tool
  -> Routes to Fabric (same path as any CapabilityRequest)
  -> Fabric resolves, builds context, executes
  -> CapabilityResult returns to Sub-Agent
  -> Sub-Agent continues its task
```

**Constraint**: Sub-Agents can ONLY invoke tools from their `tools_granted[]` list. Fabric enforces this.

---

## 5. Fabric Invariants (Non-Negotiable)

These are hard constraints. Violation of any invariant is a bug.

| ID | Invariant | Enforcement Point |
|---|---|---|
| FAB-01 | Fabric NEVER writes to SessionState | CapabilityFabric.execute() -- no IStatePort dependency |
| FAB-02 | Fabric NEVER calls an LLM | No ILLMPort dependency in Fabric subsystem |
| FAB-03 | Fabric is stateless per-request | No instance state carried between CapabilityRequest calls |
| FAB-04 | Every execution returns CapabilityResult within circuit breaker timeout (30s) | Circuit breaker wrapper on execute() |
| FAB-05 | Hard filters run BEFORE soft ranking (safety first) | Retrieval pipeline ordering |
| FAB-06 | Safety band access is ALWAYS checked before provider execution | Policy Engine first gate |
| FAB-07 | Sub-Agent tool access is scoped to plan-specified `tools_granted[]` only | Agent Factory enforcement |
| FAB-08 | Context Builder respects 128K token budget for agent context | Context Budget Manager ceiling |
| FAB-09 | All Fabric events emitted on K1 Event Bus with cognitive_trace_id | Event emission wrapper |
| FAB-10 | Provider selection is deterministic given same inputs + same registry state | No randomness in ranking |
| FAB-11 | Capability names follow type conventions: `agent.spawn.*`, `agent.execute.*`, `tool.execute.*`, `tool.read.*`, `workflow.run.*`, `concierge.state.*` | Registry validation on register() |
| FAB-12 | All contracts validated against schema before registration | Module Validator on load |

---

## 6. Subsystem 1: Capability Contract System

### Purpose

The contract system defines the standard shape for every tool, agent, prompt, and workflow in the system. Contracts are the single source of truth for what a capability needs, what it produces, and how it behaves. Every other Fabric subsystem reads from contracts.

### Contract Location

```
k1/contracts/
  tools/          -- Tool contracts (YAML)
    restaurant_booking.yaml
    weather_api.yaml
    calendar_tool.yaml
    ...
  agents/         -- Agent contracts (YAML)
    invitation_sender.yaml
    health_agent.yaml
    finance_agent.yaml
    ...
  prompts/        -- Prompt contracts (YAML)
    invitation_drafter_v1.yaml
    restaurant_booking_v2.yaml
    ...
  workflows/      -- Workflow contracts (compiled from WorkflowSpec)
    weekly_health_check.yaml
    ...
  schemas/        -- JSON Schema files for contract validation
    tool_contract.schema.json
    agent_contract.schema.json
    prompt_contract.schema.json
    workflow_contract.schema.json
```

### Tool Contract Schema (Complete)

Every tool in the system -- MCP tools, WASM tools, Bridge operations -- MUST have a contract in this format.

```yaml
# Standard Tool Contract
# Applies to ALL tools in ALL domains (FamilyOS, SchoolOS, BankOS, any domain)
tool_contract:
  # ---- Identity ----
  name: "tool.execute.restaurant_booking"       # Canonical capability name (must match type convention)
  version: "2.1.0"                               # Semver
  domain:                                        # Domain tags (multi-label, used for retrieval ranking)
    - "FOOD"
    - "EVENTS"

  # ---- Description (used for semantic retrieval embedding) ----
  description: "Books a restaurant reservation"  # Human-readable, 1 sentence, max 120 chars
  capabilities:                                  # What this tool CAN do (list of verbs)
    - "reserve_table"
    - "check_availability"
    - "cancel_reservation"
  limitations:                                   # What this tool CANNOT do (explicit boundaries)
    - "does not handle payment"
    - "max 20 guests per reservation"

  # ---- Input Requirements (what it needs to perform) ----
  required_inputs:
    - name: "date"
      type: "DATE"                               # DATE, STRING, NUMBER, BOOLEAN, ARRAY[T], OBJECT
      description: "Reservation date (ISO 8601)"
    - name: "party_size"
      type: "NUMBER"
      description: "Number of guests (1-20)"
    - name: "location"
      type: "STRING"
      description: "City or area for restaurant search"
  optional_inputs:
    - name: "cuisine"
      type: "STRING"
      description: "Preferred cuisine type"
    - name: "budget_range"
      type: "STRING"
      enum: ["$", "$$", "$$$", "$$$$"]
      description: "Price range"

  # ---- Context Requirements (SessionState sections the tool needs) ----
  required_context:
    - "beliefs_active.entities"                  # For name resolution (PERSON entities)
    - "temporal_context"                         # For date resolution (absolute times)
  optional_context:
    - "persona"                                  # For tone matching (if applicable)
    - "affective_now"                            # For emotion-aware responses

  # ---- Output Schema (what it returns) ----
  output:
    type: "object"
    properties:
      venue_name: { type: "string" }
      address: { type: "string" }
      confirmation_id: { type: "string" }
      date: { type: "string", format: "date" }
      party_size: { type: "number" }

  # ---- Provider Metadata ----
  provider_type: "MCP"                           # MCP | WASM | BRIDGE | AGENT
  provider_id: "opentable_mcp"                   # Which MCP server / agent template / WASM module
  provider_endpoint: "mcp://local/opentable"     # Connection string (for MCP: server URI)

  # ---- Policy Metadata ----
  safety_band_min: "GREEN"                       # Minimum safety band required (GREEN < AMBER < RED < CRISIS)
  cost_per_call: 0.001                           # Estimated cost in USD per invocation
  avg_latency_ms: 2000                           # Average execution time in milliseconds
  max_latency_ms: 10000                          # Maximum expected latency (circuit breaker hint)
  availability: "ONLINE"                         # ONLINE | DEGRADED | OFFLINE

  # ---- Audit Fields ----
  registered_at: "2026-01-15T10:00:00Z"
  last_updated: "2026-02-01T14:30:00Z"
  success_rate_30d: 0.97                         # Rolling 30-day success rate
  total_invocations_30d: 1423                    # Rolling 30-day invocation count
```

### Agent Contract Schema (Complete)

Agents are tools that have their own LLM. They are created from YAML templates and spawned on-demand by the Agent Factory.

```yaml
agent_contract:
  # ---- Identity ----
  name: "agent.execute.invitation_sender"
  version: "1.0.0"
  domain:
    - "SOCIAL"
    - "COMMUNICATION"

  # ---- Description ----
  description: "Drafts and sends personalized invitations"
  capabilities:
    - "draft_invitation"
    - "personalize_per_recipient"
    - "send_via_messaging"
  limitations:
    - "text-only invitations (no image generation)"
    - "max 50 recipients per batch"

  # ---- Input Requirements ----
  required_inputs:
    - name: "event_description"
      type: "STRING"
      description: "What the invitation is for"
    - name: "recipients"
      type: "ARRAY[CONTACT]"
      description: "List of people to invite"
  optional_inputs:
    - name: "tone"
      type: "STRING"
      enum: ["formal", "casual", "playful"]

  # ---- Context Requirements ----
  required_context:
    - "beliefs_active.entities"
    - "persona"                                  # For tone matching

  # ---- Agent-Specific Fields ----
  prompt_template: "invitation_drafter_v1"       # Default prompt template from Prompt Registry
  tools_granted:                                 # What tools this agent is allowed to use
    - "tool.execute.send_message"
    - "tool.read.contact_lookup"
  llm_budget_tokens: 2000                        # Max tokens per LLM invocation
  max_tool_calls: 10                             # Max tool calls per agent execution
  max_execution_time_ms: 30000                   # Agent timeout

  # ---- Output Schema ----
  output:
    type: "object"
    properties:
      invitations_sent: { type: "number" }
      failed_recipients: { type: "array", items: { type: "string" } }
      summary: { type: "string" }

  # ---- Provider Metadata ----
  provider_type: "AGENT"
  template_file: "invitation_sender.yaml"        # YAML template in k1/contracts/agents/

  # ---- Policy Metadata ----
  safety_band_min: "GREEN"
  cost_per_call: 0.05                            # Higher cost (uses LLM)
  avg_latency_ms: 5000
  max_latency_ms: 30000
  availability: "ONLINE"

  # ---- Audit Fields ----
  registered_at: "2026-01-20T09:00:00Z"
  last_updated: "2026-02-03T11:00:00Z"
  success_rate_30d: 0.93
  total_invocations_30d: 87
```

### Prompt Contract Schema (Complete)

Prompts are templates used by agents and the Planner. They declare what variables they need, what output they produce, and which agents/tools they are compatible with.

```yaml
prompt_contract:
  # ---- Identity ----
  name: "invitation_drafter_v1"
  version: "1.0.0"
  domain:
    - "SOCIAL"
    - "COMMUNICATION"

  # ---- Description ----
  description: "Drafts personalized event invitations"
  intent_match:                                  # Intents that trigger this prompt (for retrieval)
    - "send_invitation"
    - "invite_people"
    - "party_planning"

  # ---- Template Variables (must be filled before use) ----
  variables:
    - name: "event_type"
      type: "STRING"
      required: true
      description: "Type of event (birthday, wedding, etc.)"
    - name: "guest_name"
      type: "STRING"
      required: true
      description: "Name of the person being invited"
    - name: "event_details"
      type: "STRING"
      required: true
      description: "Date, time, location details"
    - name: "tone"
      type: "STRING"
      required: false
      default: "casual"
      description: "Invitation tone"

  # ---- Template Content ----
  template_file: "k1/prompts/agents/invitation_drafter_v1.txt"
  max_tokens: 500                                # Recommended token budget for this prompt

  # ---- Output Format ----
  output_format: "TEXT"                          # TEXT | JSON | STRUCTURED

  # ---- Compatibility (what can use this prompt) ----
  compatible_agents:
    - "agent.execute.invitation_sender"
  compatible_tools: []

  # ---- Audit Fields ----
  registered_at: "2026-01-20T09:00:00Z"
  last_updated: "2026-02-01T14:30:00Z"
```

### Workflow Contract Schema

Workflows are frozen CommittedPlans saved for repeated execution (cron, event trigger, or manual).

```yaml
workflow_contract:
  # ---- Identity ----
  name: "workflow.run.weekly_health_check"
  version: "1.0.0"
  domain:
    - "HEALTH"

  # ---- Description ----
  description: "Weekly check-in on family health metrics"

  # ---- Source ----
  source_plan_id: "uuid-of-original-committed-plan"

  # ---- Trigger Configuration ----
  trigger:
    type: "cron"                                 # cron | event | manual
    schedule: "0 8 * * MON"                      # Cron expression
    timezone: "America/Los_Angeles"

  # ---- Steps (frozen from CommittedPlan) ----
  steps:
    - id: "s1"
      capability: "tool.read.health_metrics"
      params: { family_member: "Mom", metric_types: ["blood_pressure", "weight"] }
      deps: []
    - id: "s2"
      capability: "agent.execute.health_summarizer"
      prompt_template: "health_summary_v1"
      params: { metrics: "$s1.result", timeframe: "7d" }
      deps: ["s1"]
  dependencies:
    s2: ["s1"]

  # ---- Cross-Workflow ----
  max_depth: 3                                   # Max workflow nesting depth
  allows_sub_workflows: true

  # ---- Policy Metadata ----
  safety_band_min: "GREEN"
  avg_latency_ms: 15000
  active: true

  # ---- Audit Fields ----
  created_at: "2026-02-05T14:30:00Z"
  last_run: "2026-02-03T08:00:00Z"
  run_count: 4
  success_rate: 1.0
```

### Contract Validation Rules

Module Validator enforces these rules on every contract before it enters the registry:

1. `name` MUST follow the type convention pattern (`tool.execute.*`, `agent.execute.*`, etc.)
2. `version` MUST be valid semver
3. `domain[]` MUST contain at least one valid domain tag
4. `description` MUST be non-empty (used for embedding index)
5. `required_inputs[]` MUST each have `name`, `type`, `description`
6. `output` MUST have a valid JSON Schema definition
7. `provider_type` MUST be one of: MCP, WASM, BRIDGE, AGENT
8. `safety_band_min` MUST be one of: GREEN, AMBER, RED, CRISIS
9. `availability` MUST be one of: ONLINE, DEGRADED, OFFLINE
10. For agents: `tools_granted[]` MUST reference only valid `tool.execute.*` or `tool.read.*` names
11. For prompts: `variables[].required == true` MUST all be satisfiable from declared sources
12. No circular dependencies in workflow `dependencies` (validated as acyclic DAG)

---

## 7. Subsystem 2: Capability Registry

### Purpose

The Registry is the in-memory indexed catalog of all loaded contracts. Both retrieval (Role 1) and resolution (Role 2) query the Registry. It is the single source of truth for what capabilities exist, how to invoke them, and their current state.

### Data Structures

```
CapabilityRegistry
  |
  |-- by_name: dict[str, CapabilityContract]        # O(1) lookup by canonical name
  |-- by_domain: dict[str, list[CapabilityContract]] # Inverted index for domain filtering
  |-- by_type: dict[str, list[CapabilityContract]]   # Grouped by capability type prefix
  |-- by_provider: dict[str, list[CapabilityContract]]# Grouped by provider_id
  |-- embedding_index: VectorIndex                   # Pre-computed vectors for semantic search
  |     |-- vectors: ndarray[float32]                # (N, embedding_dim) matrix
  |     |-- texts: list[str]                         # description + capabilities text per contract
  |     |-- contract_ids: list[str]                  # Parallel array of contract names
  |-- metadata_cache: dict[str, ContractMetadata]    # Hot cache of frequently accessed metadata
```

### Core Methods

```python
class CapabilityRegistry:
    def register(self, contract: CapabilityContract) -> None:
        """
        Add a contract to the registry.
        1. Validate contract via ModuleValidator
        2. Compute embedding for (description + capabilities) text
        3. Insert into all indexes (name, domain, type, provider, embedding)
        4. Emit k1.fabric.capability.registered.v1 event
        Raises: ContractValidationError if contract is malformed.
        """

    def unregister(self, name: str) -> None:
        """
        Remove a contract from the registry.
        1. Remove from all indexes
        2. Remove embedding vector
        3. Emit k1.fabric.capability.unregistered.v1 event
        Used for: hot-reload when a YAML file changes, tool goes permanently offline.
        """

    def lookup(self, name: str) -> CapabilityContract | None:
        """
        Exact-match lookup by canonical capability name.
        O(1) via by_name dict.
        Used by: Provider Resolution Engine (Role 2).
        Returns None if not found (caller handles error).
        """

    def search(self, query: SearchQuery) -> list[ScoredCapability]:
        """
        Semantic + filtered search across the registry.
        Used by: Retrieval Engine (Role 1).
        SearchQuery contains: text (str), domain (str?), intent (str?), safety_band (str), top_k (int).
        Returns list of ScoredCapability{contract, score} sorted by descending score.
        See Section 8 for full retrieval pipeline.
        """

    def list_by_domain(self, domain: str) -> list[CapabilityContract]:
        """
        Return all capabilities tagged with the given domain.
        O(1) via by_domain inverted index.
        """

    def list_by_type(self, type_prefix: str) -> list[CapabilityContract]:
        """
        Return all capabilities matching the type prefix.
        e.g., list_by_type("agent.execute") returns all agent execution capabilities.
        """

    def update_availability(self, name: str, availability: str) -> None:
        """
        Update a capability's availability status (ONLINE/DEGRADED/OFFLINE).
        Called when: circuit breaker trips, health check fails, tool comes back online.
        Does NOT re-compute embedding (availability is a policy filter, not a semantic property).
        """

    def update_metrics(self, name: str, success: bool, latency_ms: int) -> None:
        """
        Update rolling 30-day metrics for a capability.
        Called after every CapabilityResult is returned.
        Updates: success_rate_30d, avg_latency_ms, total_invocations_30d.
        """

    def reload(self) -> None:
        """
        Full reload from k1/contracts/ directory.
        1. Scan all YAML files in tools/, agents/, prompts/, workflows/
        2. Validate each contract
        3. Rebuild all indexes (including recomputing embedding vectors)
        Used at: startup, and on explicit reload command.
        """
```

### Hot-Reload Mechanism

The Module Loader watches the `k1/contracts/` directory for changes (file create/modify/delete). On change:

1. Parse the modified YAML file
2. Validate against the appropriate schema
3. If valid: `registry.unregister(old_name)` then `registry.register(new_contract)`
4. If invalid: log error, keep old contract in registry, emit `k1.fabric.contract.validation.failed.v1`
5. No downtime: hot-reload is atomic per-contract

### Embedding Index Details

The embedding index powers Role 1 (Retrieval) semantic search:

- **Model**: Same embedding model used elsewhere in K1 (consistency, no model-mismatch)
- **Text to embed**: `f"{contract.description} | {' '.join(contract.capabilities)}"`
- **Index type**: FAISS flat L2 or IVF for >10K contracts (configurable)
- **Rebuild**: On startup (full), on register/unregister (incremental -- add/remove single vector)
- **Dimensionality**: Matches embedding model output (e.g., 768 for MiniLM, 1024 for larger)

---

## 8. Subsystem 3: Semantic Retrieval Engine

### Purpose

The Retrieval Engine serves Role 1: Intelligent Retrieval for the Planner. When the Planner LLM calls `discover_capabilities()` or `find_relevant_prompts()`, this engine performs semantic Top-K search across the registry and returns the most relevant results.

### Why Semantic Retrieval (Not Dump Everything)

The scale problem: as the system grows to 100K+ tools, 100K+ agents, 10K+ prompts, you cannot pass the entire catalog into a Planner LLM prompt. Token budgets explode. Irrelevant noise drowns relevant capabilities.

Fabric is the ONLY component that sees the full catalog. The Planner sees only a filtered, relevant subset (Top-K).

### Retrieval Pipeline (Step by Step)

```
Input: SearchQuery{text, domain?, intent?, safety_band, top_k=10}
  |
  v
[1] EMBED QUERY
  |  Embed the query text using the same model that indexed the registry.
  |  Result: query_vector (float32 array)
  |
  v
[2] HARD FILTER (Eliminates Non-Candidates)
  |  For each capability in the registry, apply ALL hard rules.
  |  A capability is ELIMINATED if ANY hard rule fails.
  |
  |  Hard Rule 1: Safety Band Access
  |    capability.safety_band_min must be <= user's current safety_band
  |    e.g., if user is GREEN, capabilities requiring AMBER+ are eliminated
  |
  |  Hard Rule 2: Availability
  |    capability.availability must NOT be OFFLINE
  |    DEGRADED capabilities are kept but penalized in soft ranking
  |
  |  Hard Rule 3: Input Satisfiability
  |    All capability.required_inputs must be satisfiable from:
  |    (a) the request params, OR (b) the user's SessionState context, OR (c) the Planner can ask
  |    If a required_input is completely unsatisfiable => eliminated
  |    (Relaxed check: if MOST are satisfiable, keep it -- Planner can formulate clarifications)
  |
  |  Result: filtered_set (subset of registry)
  |
  v
[3] SOFT RANKING (Scores Remaining Candidates)
  |
  |  For each capability in filtered_set, compute composite score:
  |
  |  Score = (0.4 * semantic_similarity)
  |        + (0.3 * domain_match)
  |        + (0.15 * success_rate)
  |        + (0.15 * cost_latency_score)
  |
  |  semantic_similarity:
  |    cosine(query_vector, capability_embedding_vector)
  |    Range: 0.0 to 1.0
  |
  |  domain_match:
  |    |intersection(query.domain_tags, capability.domain)| / |union(...)|
  |    Range: 0.0 to 1.0
  |    If query has no domain filter: 0.5 (neutral)
  |
  |  success_rate:
  |    capability.success_rate_30d
  |    Range: 0.0 to 1.0
  |    If no data (new capability): 0.5 (neutral)
  |
  |  cost_latency_score:
  |    1.0 - normalize(capability.cost_per_call + capability.avg_latency_ms / 10000)
  |    Lower cost + faster = higher score
  |    Range: 0.0 to 1.0
  |
  |  DEGRADED penalty: If availability == DEGRADED, multiply final score by 0.7
  |
  |  Result: scored_set sorted by descending score
  |
  v
[4] TOP-K SELECTION
  |  Return the top K results (default K=10, max K=25)
  |  Each result includes:
  |    - Full contract (name, description, capabilities, limitations)
  |    - Input schema (required_inputs, optional_inputs)
  |    - Output schema
  |    - Score (for debugging/logging, not exposed to Planner LLM)
  |    - Provider type
  |
  v
Output: list[RetrievalResult{contract, score}]
```

### Performance Requirements

| Metric | Target | Rationale |
|---|---|---|
| Retrieval latency (10K capabilities) | < 20ms | Planner calls 3-6 times per plan; total budget 100-300ms |
| Retrieval latency (100K capabilities) | < 50ms | FAISS IVF index for large catalogs |
| Embedding computation per query | < 5ms | Single vector, batch-1 inference |
| Hard filter pass | < 2ms | Simple field comparisons, no I/O |
| Soft ranking | < 10ms | Dot products + field reads on filtered set |

### API for Planner Discovery Tools

```python
class RetrievalEngine:
    def discover_capabilities(
        self,
        domain: str | None,
        intent: str | None,
        safety_band: str,
        session_context: dict,  # For input satisfiability check
        top_k: int = 10
    ) -> list[RetrievalResult]:
        """
        Called by Planner's discover_capabilities() tool.
        Searches Tool + Agent registries.
        Returns top-K with full schemas.
        """

    def find_relevant_prompts(
        self,
        intent: str | None,
        domain: str | None,
        safety_band: str,
        top_k: int = 10
    ) -> list[RetrievalResult]:
        """
        Called by Planner's find_relevant_prompts() tool.
        Searches Prompt Registry.
        Returns top-K prompt templates with variable definitions.
        """
```

---

## 9. Subsystem 4: Provider Resolution Engine

### Purpose

The Provider Resolution Engine maps a `CapabilityRequest.name` to a concrete provider implementation. This is Role 2 (Execution), not Role 1 (Retrieval). It is an exact-match lookup, not a semantic search.

### Resolution Pipeline

```
Input: CapabilityRequest{name: "tool.execute.restaurant_booking", params: {...}, context: {...}}
  |
  v
[1] REGISTRY LOOKUP
  |  contract = registry.lookup(request.name)
  |  If not found: return CapabilityResult{success=false, error="capability_not_found"}
  |
  v
[2] PROVIDER MATCHING
  |  Find all registered providers that can fulfill this contract.
  |  Usually 1 provider per capability (1:1 mapping).
  |  For some capabilities, multiple providers exist:
  |    e.g., restaurant_booking might have "opentable_mcp" and "resy_mcp"
  |  Provider list comes from: contract.provider_id + any aliases in Provider Registry
  |
  v
[3] POLICY EVALUATION (see Section 10)
  |  For each matched provider, Policy Engine computes a policy score.
  |  Policy dimensions: Affective, Cognitive Load, QoS, Security.
  |  Security is a hard gate (fail = reject). Others are soft scores.
  |
  v
[4] PROVIDER SELECTION
  |  Select the highest-scoring provider from policy evaluation.
  |  If all providers fail security check: return CapabilityResult{success=false, error="access_denied"}
  |
  v
[5] PROVIDER INSTANTIATION
  |  Provider Factory creates the provider handler:
  |    - MCPProvider: configured with MCP server URI + protocol version
  |    - WASMProvider: configured with WASM module path + sandbox config
  |    - BridgeProvider: configured with Bridge Client connection
  |    - AgentProvider: triggers Agent Factory (see Section 13)
  |    - WorkflowProvider: configured with WorkflowSpec + run manifest
  |    - ConciergeProvider: configured with FSM state handler reference
  |
  v
Output: ResolvedProvider{provider_instance, contract, policy_context}
```

### Provider Registry (Internal)

```python
class ProviderRegistry:
    """
    Maps provider_id to provider configuration.
    Separate from Capability Registry (which maps capability names to contracts).
    """
    providers: dict[str, ProviderConfig]

    def register_provider(self, provider_id: str, config: ProviderConfig) -> None
    def lookup_provider(self, provider_id: str) -> ProviderConfig | None
    def health_check(self, provider_id: str) -> ProviderHealth
```

### Provider Config Examples

```yaml
# MCP Provider
provider_config:
  provider_id: "opentable_mcp"
  provider_type: "MCP"
  endpoint: "mcp://local/opentable"
  protocol_version: "2025-01-01"
  transport: "stdio"                             # stdio | sse | streamable-http
  max_concurrent: 10
  health_check_interval_s: 60

# WASM Provider
provider_config:
  provider_id: "calc_wasm"
  provider_type: "WASM"
  module_path: "k1/wasm/calc.wasm"
  sandbox_memory_mb: 64
  max_execution_ms: 5000

# Bridge Provider
provider_config:
  provider_id: "k0_memory_bridge"
  provider_type: "BRIDGE"
  bridge_endpoint: "bridge://k0"
  operations:
    - "memory.store"
    - "memory.recall"
    - "memory.delta"
```

---

## 10. Subsystem 5: Policy Engine

### Purpose

The Policy Engine decides WHICH provider to use when multiple options exist, and enforces access control. It evaluates four dimensions for every provider candidate.

### Four Policy Dimensions

#### Dimension 1: Security Context (Hard Gate)

This is the FIRST check. If it fails, the provider is immediately rejected. No scoring.

```
Input:  user's current safety_band (from SessionState control.safety_band)
        capability's safety_band_min (from contract)
Check:  user_band >= capability_band_min
        Band ordering: GREEN < AMBER < RED < CRISIS
Result: PASS or REJECT

Example:
  User safety_band = GREEN
  Capability safety_band_min = AMBER
  Result: REJECT (user does not have AMBER access)
```

Additional security checks:

- Sub-Agent tool scoping: verify requested capability is in `tools_granted[]`
- Rate limiting: per-capability invocation limits (if configured)
- Tenant isolation: capabilities scoped to family_id (multi-tenant future)

#### Dimension 2: Affective Routing (Soft Score)

Reads `affective_now` from SessionState to adjust provider selection based on the user's emotional state.

```
Input:  affective_now.raw (detected emotion), affective_now.intensity
Rules:
  - High sadness/anxiety (intensity > 0.7):
      Prefer agents with gentler tone (check agent contract prompt_template tone hints)
      Prefer simpler tools (fewer steps)
      Score boost: +0.1 for empathetic-tagged providers
  - High joy/excitement:
      Prefer richer responses (more detailed agents)
      Score boost: +0.05 for detail-rich providers
  - Neutral/low intensity:
      No adjustment (score += 0.0)

Output: affective_score (float, range 0.0-0.2) added to provider's composite score
```

#### Dimension 3: Cognitive Load Routing (Soft Score)

Reads the complexity tier and user's cognitive state to prefer providers that match the user's capacity.

```
Input:  complexity_tier (LOW/MEDIUM/HIGH), cognitive_load estimate from Mental Model Management
Rules:
  - High cognitive load (user overwhelmed):
      Prefer faster providers (lower avg_latency_ms)
      Prefer simpler outputs (fewer fields in output schema)
      Score boost: +0.1 for fast, simple providers
  - Low cognitive load (user is fresh):
      No penalty for complex providers
      Score boost: +0.05 for comprehensive providers

Output: cognitive_score (float, range 0.0-0.15) added to composite score
```

#### Dimension 4: QoS Integration (Soft Score)

Budget-aware and latency-aware provider selection.

```
Input:  session_budget remaining, latency_budget remaining, priority from WFQ scheduler
Rules:
  - Tight budget (< 20% remaining):
      Heavily prefer lower cost_per_call providers
      Score: 1.0 - normalize(cost_per_call)  (weight 0.8)
  - Tight latency (< 30% budget remaining):
      Heavily prefer lower avg_latency_ms providers
      Score: 1.0 - normalize(avg_latency_ms / max_latency_ms)  (weight 0.8)
  - Ample budget and latency:
      Still factor cost/latency but with lower weight
      Score: balanced formula (weight 0.3 each)

Output: qos_score (float, range 0.0-0.2) added to composite score
```

### Composite Provider Score

```
final_score = base_relevance_score
            + affective_score
            + cognitive_score
            + qos_score

Where base_relevance_score = 1.0 for single-provider capabilities (most cases)
                           = soft_ranking_score for multi-provider capabilities
```

The provider with the highest `final_score` is selected. Ties broken by: lower avg_latency_ms, then alphabetical name (deterministic, per FAB-10).

---

## 11. Subsystem 6: Execution Runtime (Providers)

### Purpose

The Execution Runtime is where capability invocation actually happens. Each provider type implements a common interface and handles the specifics of its execution environment.

### Common Provider Interface

```python
class CapabilityProvider(Protocol):
    async def execute(
        self,
        request: CapabilityRequest,
        context: ExecutionContext,
        trace_id: str
    ) -> CapabilityResult:
        """
        Execute the capability.
        - request: what to do (name, params)
        - context: assembled SessionState sections + prompt (from Context Builder)
        - trace_id: cognitive_trace_id for observability
        Returns CapabilityResult{success, data, error, duration_ms}
        """

    async def health_check(self) -> ProviderHealth:
        """Check if the provider is healthy and responsive."""

    def capabilities(self) -> list[str]:
        """List of capability names this provider handles."""
```

### Provider Type 1: MCP Provider

Handles tool execution via the Model Context Protocol. Supports local MCP servers (stdio), remote MCP servers (SSE/streamable-http), and K0 Connector Proxy (for device adapters via Bridge/IFL).

```
MCP Provider Execution Flow:
  1. Receive CapabilityRequest
  2. Look up MCP server connection (from ProviderConfig.endpoint)
  3. Build MCP tool_call message:
     {
       "method": "tools/call",
       "params": {
         "name": contract.name,  // or mapped tool name on the MCP server
         "arguments": request.params
       }
     }
  4. Send to MCP server via configured transport (stdio/SSE/HTTP)
  5. Await response (within circuit breaker timeout)
  6. Parse MCP tool_result
  7. Return CapabilityResult{
       success: !result.isError,
       data: result.content,
       error: result.isError ? result.content[0].text : null,
       duration_ms: elapsed
     }
```

**MCP Server Management**:

| Category | Examples | Transport | Location |
|---|---|---|---|
| Local MCP Servers | file_system, calculator, sqlite | stdio | Same machine |
| Remote MCP Servers | weather_api, opentable | SSE / HTTP | Cloud endpoints |
| K0 Connector Proxy | HomeKit, Tesla, Google Home | Bridge/IFL | Via Cross-Kernel Bridge |

### Provider Type 2: WASM Provider

Sandboxed execution for untrusted or computationally isolated tools.

```
WASM Provider Execution Flow:
  1. Receive CapabilityRequest
  2. Load WASM module (from ProviderConfig.module_path, cached after first load)
  3. Create sandbox with configured memory limit
  4. Marshal request.params into WASM-compatible format
  5. Execute WASM function
  6. Unmarshal result
  7. Return CapabilityResult
```

**Sandbox constraints**: memory limit (configurable, default 64MB), execution timeout (configurable, default 5s), no network access (pure computation only).

### Provider Type 3: Bridge Provider

Routes operations to K0 (the memory/storage kernel) through the Cross-Kernel Bridge.

```
Bridge Provider Execution Flow:
  1. Receive CapabilityRequest (e.g., "tool.read.k0_recall")
  2. Map to Bridge operation (e.g., bridge.recall(query))
  3. Send via Bridge Client (respects K0 health, offline fallback)
  4. If K0 is offline: fallback to LOCAL COLD (K1 SQLite)
  5. Return CapabilityResult with K0 response data
```

**Bridge operations**: memory.store, memory.recall, memory.delta, checkpoint, feedback.signal

### Provider Type 4: Agent Provider (Agent Factory)

See Section 13 for full Agent Factory design.

### Provider Type 5: Workflow Provider

Rehydrates a frozen WorkflowSpec and executes it as a DAG.

```
Workflow Provider Execution Flow:
  1. Receive CapabilityRequest (e.g., "workflow.run.weekly_health_check")
  2. Load WorkflowSpec from Workflow Registry
  3. Workflow Compiler rehydrates the plan:
     a. Validate all referenced capabilities still exist
     b. Validate schemas still match (detect drift)
     c. If drift detected: emit gap signal, abort or fallback
  4. Create Run Manifest (pinned version + hash for audit)
  5. Send rehydrated plan to Orchestrator for DAG execution
  6. Orchestrator walks DAG via Fabric (recursive: Fabric -> Orchestrator -> Fabric)
  7. Guard: max workflow depth = 3 (sub-workflow nesting limit)
  8. Return aggregated CapabilityResult
```

### Provider Type 6: Concierge Provider

Handles Concierge internal state operations (`concierge.state.*`). These are capabilities that modify Concierge FSM state.

```
Concierge Provider Execution Flow:
  1. Receive CapabilityRequest (e.g., "concierge.state.interrupt_check")
  2. Route to corresponding FSM state handler
  3. Handler modifies FSM state (via Concierge Single Writer)
  4. Return CapabilityResult
```

---

## 12. Subsystem 7: Context Builder

### Purpose

The Context Builder assembles the execution context for agents and tool calls. Every provider execution needs SessionState context, but within a token budget. The Context Builder reads the declared `required_context` sections from the capability contract, fetches them from SessionState (multi-reader, lock-free), applies the token budget, and packages the result.

### Context Assembly Flow

```
Input: CapabilityContract, CapabilityRequest, SessionState reference
  |
  v
[1] READ CONTRACT REQUIREMENTS
  |  sections_needed = contract.required_context + contract.optional_context
  |  e.g., ["beliefs_active.entities", "temporal_context", "persona"]
  |
  v
[2] FETCH FROM SESSION STATE (Multi-Reader, Lock-Free)
  |  For each section in sections_needed:
  |    data = sessionstate.read(section)
  |    if section is optional and not found: skip (no error)
  |    if section is required and not found: log warning, continue with partial context
  |
  v
[3] INJECT REQUEST PARAMS
  |  context.params = request.params
  |  context.intent = request.intent (if present)
  |
  v
[4] RESOLVE PROMPT TEMPLATE (if applicable)
  |  If contract has prompt_template:
  |    template = prompt_system.resolve(contract.prompt_template)
  |    variables = map contract variables to context data
  |    compiled_prompt = prompt_compiler.compile(template, variables)
  |    context.prompt = compiled_prompt
  |
  v
[5] APPLY TOKEN BUDGET
  |  total_tokens = count_tokens(context)
  |  budget = 128_000 tokens (K1 context window)
  |  If total_tokens > budget * 0.8:
  |    Apply compression strategy:
  |      a. Recency: keep most recent turns/facts, drop older ones
  |      b. Relevance: keep sections most relevant to the capability's domain
  |      c. Summarization: compress verbose sections (same logic as Concierge ContextAssembler)
  |  Final total_tokens MUST be < budget
  |
  v
[6] PACKAGE AND RETURN
  |  ExecutionContext{
  |    session_sections: dict[str, Any],   -- fetched SessionState data
  |    params: dict[str, Any],             -- request parameters
  |    prompt: str | None,                 -- compiled prompt (if applicable)
  |    token_count: int,                   -- actual tokens consumed
  |    trace_id: str                       -- cognitive_trace_id
  |  }
  |
  v
Output: ExecutionContext
```

### Token Budget Strategy

The 128K budget is shared across:

| Component | Budget Share | Notes |
|---|---|---|
| System prompt (agent) | 2K-5K | Fixed per agent type |
| Compiled prompt template | 500-2K | From Prompt Contract max_tokens |
| SessionState sections | 10K-40K | Depends on required_context size |
| Request params | 1K-5K | Capability-specific |
| Tool results (if agent reuses context) | 5K-20K | Accumulated during agent execution |
| Response headroom | 2K-8K | Agent's llm_budget_tokens |

Strategy precedence for compression when over budget:

1. Drop optional_context sections first
2. Truncate history_recent (keep only last 3 turns)
3. Summarize beliefs_active (drop low-confidence facts)
4. If still over: summarize scoreboard (keep only current QUD)
5. Emergency: drop all WARM tier sections, keep only HOT

---

## 13. Agent Factory (Inside Execution Runtime)

### Purpose

The Agent Factory is the sub-component of Agent Provider that instantiates new agents from YAML templates. Agents are per-step workers created on-demand for plan steps requiring `agent.execute.*` or `agent.spawn.*` capabilities.

### Agent Instantiation Flow

```
Input: AgentContract, CapabilityRequest (from CommittedPlan step), ExecutionContext
  |
  v
[1] LOAD TEMPLATE
  |  template = load_yaml(contract.template_file)
  |  Validate template against agent contract schema
  |
  v
[2] CREATE MAILBOX
  |  mailbox = MPSCMailbox(
  |    priority = WFQ_PRIORITY.INTERACTIVE,  -- default for spawned agents
  |    capacity = 100                         -- max pending messages
  |  )
  |
  v
[3] GRANT LLM ACCESS
  |  llm_handle = model_gateway.create_handle(
  |    budget_tokens = contract.llm_budget_tokens,  -- from agent contract
  |    model_preference = template.model_preference, -- if specified
  |    trace_id = context.trace_id
  |  )
  |
  v
[4] GRANT SESSION STATE READ ACCESS
  |  reader = sessionstate.create_reader(
  |    sections = contract.required_context,  -- only declared sections
  |    mode = "lock-free"                     -- multi-reader, no locks
  |  )
  |
  v
[5] SCOPE TOOL ACCESS
  |  Determine which tools the agent can use:
  |  a. Start with contract.tools_granted (from agent contract)
  |  b. Override with plan_step.tools_granted (from CommittedPlan step, if specified)
  |  c. Plan step overrides take precedence (Planner specifies exact tools per step)
  |  d. NEVER grant tools not in the union of (a) and (b)
  |
  |  tool_scope = ToolScope(
  |    allowed_tools = resolved_tools_granted,
  |    invoke_capability = FabricInvoker(fabric_ref, tool_scope)  -- recursive invocation
  |  )
  |
  v
[6] BUILD INITIAL CONTEXT
  |  Use Context Builder (Section 12) to assemble:
  |  - Prompt template (compiled with variables)
  |  - SessionState sections (from required_context)
  |  - Request parameters (from CommittedPlan step.params)
  |  - Token budget applied
  |
  v
[7] INSTANTIATE AGENT
  |  agent = Agent(
  |    id = generate_agent_id(),
  |    contract = contract,
  |    mailbox = mailbox,
  |    llm = llm_handle,
  |    state_reader = reader,
  |    tools = tool_scope,
  |    context = initial_context,
  |    lifecycle_state = PENDING
  |  )
  |
  v
[8] START AGENT LIFECYCLE
  |  agent.lifecycle_state = WARMING (model preloading)
  |  await agent.warm_up()
  |  agent.lifecycle_state = ACTIVE
  |  result = await agent.execute(request.params)
  |  agent.lifecycle_state = IDLE (or DRAINING if one-shot)
  |
  v
Output: CapabilityResult from agent execution
```

### Agent Lifecycle States (ADR-0005)

```
PENDING -----(Supervisor Hire)-----> WARMING
WARMING -----(Model Ready)---------> ACTIVE
ACTIVE ------(60s Idle TTL)--------> IDLE
IDLE --------(New Task)------------> ACTIVE      (fast reactivation from pool)
ACTIVE ------(Supervisor Drain)----> DRAINING
IDLE --------(Supervisor Drain)----> DRAINING
DRAINING ----(Tasks Complete)------> TERMINATED
```

- **IDLE pool**: Agents that finish their task transition to IDLE, not TERMINATED. If a new task of the same type arrives within the idle TTL (60s), the agent is reactivated from the pool instead of a cold start.
- **WARMING**: Model preloading phase. If the agent's preferred model is already loaded in the Model Gateway cache, this phase is near-instant.
- **TERMINATED**: Clean resource disposal -- release mailbox, LLM handle, state reader, tool scope.

### Agent State Writes: Delta Pattern

Agents NEVER write to SessionState directly (FAB-01, ADR-0017). Instead:

```
Agent discovers a fact: "Mom prefers Italian food"
  -> Agent emits delta to Delta Bus:
     {
       type: "k1.agent.{agent_id}.delta.v1",
       payload: {
         delta_type: "fact_discovered",
         section: "beliefs_active",
         data: { fact: "Mom prefers Italian food", confidence: 0.85 }
       }
     }
  -> Delta Bus -> Aggregation Window (500ms batching, LWW merge)
  -> Concierge FSM receives aggregated batch
  -> Concierge (Single Writer) applies to SessionState via MutationGuard
```

---

## 14. Message Envelopes and Schemas

### All Inter-Component Messages That Touch Fabric

These are the message types that flow into, out of, or through Fabric. All are domain-agnostic -- they work for FamilyOS, SchoolOS, BankOS, or any business domain.

### CapabilityRequest (Into Fabric)

```yaml
CapabilityRequest:
  request_id: "uuid"                             # Unique request identifier
  capability_name: "tool.execute.restaurant_booking"  # Canonical name from registry
  params:                                        # Capability-specific parameters
    date: "2026-02-14"
    party_size: 8
    location: "San Jose"
  prompt_template: "restaurant_booking_v2"       # Optional: override default prompt
  context_override:                              # Optional: additional context sections
    beliefs_active.entities: true                 # Request specific sections
  tier: "MEDIUM"                                 # Complexity tier (for routing/logging)
  caller: "orchestrator"                         # Who sent this (concierge | orchestrator | sub-agent)
  caller_id: "orchestrator-actor-001"            # Specific caller instance
  trace_id: "cognitive-trace-uuid"               # Cognitive Trace ID (unifies causality)
  timeout_ms: 10000                              # Caller's timeout expectation
  retry_count: 0                                 # Current retry attempt (0 = first try)
```

### CapabilityResult (Out of Fabric)

```yaml
CapabilityResult:
  request_id: "uuid"                             # Matches CapabilityRequest.request_id
  success: true                                  # Overall success/failure
  data:                                          # Capability-specific result data
    venue_name: "Chez Panisse"
    address: "1517 Shattuck Ave, Berkeley, CA"
    confirmation_id: "CONF-12345"
    date: "2026-02-14"
    party_size: 8
  error: null                                    # Error details if success=false
  # error:
  #   code: "capability_not_found"               # Machine-readable error code
  #   message: "No capability registered for 'tool.execute.xyz'"
  #   retriable: false                           # Can the caller retry?
  duration_ms: 1850                              # Execution time in ms
  provider_id: "opentable_mcp"                   # Which provider executed this
  trace_id: "cognitive-trace-uuid"               # Same trace ID from request
```

### TaskEnvelope (Concierge -> Orchestrator)

Not a Fabric type, but Fabric sees it indirectly through Orchestrator's calls.

```yaml
TaskEnvelope:
  envelope_id: "uuid"
  intent: "plan birthday party for Mom next Saturday"
  context:                                       # Pre-assembled context from Concierge
    intents: { primary: "plan_event", all: ["plan_event", "book_restaurant", "send_invitations"] }
    domains: ["EVENTS", "FOOD", "SOCIAL"]
    entities: [{ type: "PERSON", value: "Mom" }, { type: "DATE", value: "2026-02-14" }]
    safety_band: "GREEN"
    affective_now: { emotion: "excited", intensity: 0.6 }
  capabilities:                                  # For MEDIUM: Concierge pre-identifies capabilities
    - "tool.execute.restaurant_booking"
    - "tool.execute.cake_order"
  tier: "HIGH"                                   # Complexity tier
  trace_id: "cognitive-trace-uuid"
```

### PlanRequest (Orchestrator -> Planner)

```yaml
PlanRequest:
  request_id: "uuid"
  intent: "plan birthday party for Mom next Saturday"
  constraints:
    budget: "unknown"                            # May need clarification
    safety_band: "GREEN"
    time_budget_ms: 45000                        # Planner must finish within this
  context:                                       # Forwarded from TaskEnvelope
    intents: { primary: "plan_event" }
    domains: ["EVENTS", "FOOD", "SOCIAL"]
    entities: [{ type: "PERSON", value: "Mom" }]
  trace_id: "cognitive-trace-uuid"
```

### CommittedPlan (Planner -> Orchestrator)

```yaml
CommittedPlan:
  plan_id: "uuid"
  intent: "plan birthday party for Mom next Saturday"
  created_at: "2026-02-06T14:30:00Z"
  steps:
    - id: "s1"
      capability: "tool.execute.restaurant_booking"
      prompt_template: "restaurant_booking_v2"
      params: { date: "2026-02-14", party_size: 8, cuisine: "vegetarian" }
      tools_granted: []                          # Tool capabilities don't use sub-tools
      deps: []
    - id: "s2"
      capability: "tool.execute.cake_order"
      prompt_template: null                      # Direct tool, no prompt needed
      params: { type: "birthday", flavor: "chocolate", date: "2026-02-14" }
      tools_granted: []
      deps: []
    - id: "s3"
      capability: "tool.read.k0_recall"
      prompt_template: null
      params: { query: "family members contact info" }
      tools_granted: []
      deps: []
    - id: "s4"
      capability: "agent.execute.invitation_sender"
      prompt_template: "invitation_drafter_v1"
      params: { event: "birthday_party", recipients: "$s3.result", venue: "$s1.result.venue" }
      tools_granted:                             # Planner specifies exact tools for this agent
        - "tool.execute.send_message"
        - "tool.read.contact_lookup"
      deps: ["s1", "s3"]                         # Depends on restaurant and contacts
  dependencies:
    s4: ["s1", "s3"]                             # Explicit DAG edges
  wal_sequence: 42                               # K0 WAL sequence for crash recovery
  trace_id: "cognitive-trace-uuid"
```

### RetrievalResult (Fabric -> Planner Discovery Tool)

```yaml
RetrievalResult:
  capabilities:                                  # Top-K results
    - name: "tool.execute.restaurant_booking"
      description: "Books a restaurant reservation"
      capabilities: ["reserve_table", "check_availability", "cancel_reservation"]
      limitations: ["does not handle payment", "max 20 guests"]
      required_inputs:
        - { name: "date", type: "DATE", description: "Reservation date (ISO 8601)" }
        - { name: "party_size", type: "NUMBER", description: "Number of guests (1-20)" }
        - { name: "location", type: "STRING", description: "City or area" }
      optional_inputs:
        - { name: "cuisine", type: "STRING", description: "Preferred cuisine type" }
        - { name: "budget_range", type: "STRING", enum: ["$","$$","$$$","$$$$"] }
      output:
        type: "object"
        properties:
          venue_name: { type: "string" }
          confirmation_id: { type: "string" }
      provider_type: "MCP"
      avg_latency_ms: 2000
    - name: "tool.execute.resy_booking"
      # ... next result ...
  total_matched: 47                              # Total candidates before Top-K
  query_latency_ms: 18                           # How long the retrieval took
```

---

## 15. Fabric API Surface (All Entrypoints)

Fabric exposes a clean API surface. All callers use these methods, NOTHING else.

### Execution API (Role 2)

```python
class CapabilityFabric:
    async def execute(
        self,
        request: CapabilityRequest
    ) -> CapabilityResult:
        """
        Main execution entrypoint. All capability invocations go through here.
        Steps: Resolve -> Policy -> Context Build -> Execute -> Return

        Called by:
          - Concierge (LOW tier, via IDispatchPort -> FabricOrchAdapter)
          - Orchestrator (MEDIUM/HIGH tier, per DAG step)
          - Sub-Agents (via scoped invoke_capability)
          - Workflow Provider (for sub-workflow steps)

        Invariants enforced:
          - FAB-03: Stateless per-request
          - FAB-04: Circuit breaker timeout (30s)
          - FAB-06: Safety band check before execution
          - FAB-09: Event emission on K1 Event Bus
        """

    async def execute_batch(
        self,
        requests: list[CapabilityRequest]
    ) -> list[CapabilityResult]:
        """
        Execute multiple capabilities in parallel.
        Used by: Orchestrator for parallel DAG steps with no dependencies.
        Each request is independent -- partial failures are allowed.
        Returns results in same order as requests.
        """
```

### Retrieval API (Role 1)

```python
class FabricRetrieval:
    async def discover_capabilities(
        self,
        domain: str | None = None,
        intent: str | None = None,
        safety_band: str = "GREEN",
        session_context: dict | None = None,
        top_k: int = 10
    ) -> RetrievalResult:
        """
        Semantic Top-K search across Tool + Agent registries.
        Called by: Planner's discover_capabilities() tool handler.
        """

    async def find_relevant_prompts(
        self,
        intent: str | None = None,
        domain: str | None = None,
        safety_band: str = "GREEN",
        top_k: int = 10
    ) -> RetrievalResult:
        """
        Semantic Top-K search across Prompt Registry.
        Called by: Planner's find_relevant_prompts() tool handler.
        """
```

### Registry Management API

```python
class CapabilityRegistryAPI:
    def register(self, contract: CapabilityContract) -> None
    def unregister(self, name: str) -> None
    def lookup(self, name: str) -> CapabilityContract | None
    def update_availability(self, name: str, status: str) -> None
    def update_metrics(self, name: str, success: bool, latency_ms: int) -> None
    def reload(self) -> None
    def health(self) -> RegistryHealth
```

### Concierge-Facing Ports

Concierge accesses Fabric through two ports defined in the hexagonal architecture:

| Port | Adapter | Routes To |
|---|---|---|
| `IDispatchPort` | `FabricOrchAdapter` (prod) | `CAPABILITY_FABRIC` (LOW), `ORCHESTRATOR_MAILBOX` (MED/HIGH), `CAPABILITY_REGISTRY` (query) |
| `IDispatchPort` | `TestDispatchAdapter` (test) | In-memory mock Fabric |

The `FabricOrchAdapter` is the boundary between Concierge and Fabric. It decides:

- LOW tier: Call `fabric.execute()` directly
- MED/HIGH tier: Send `TaskEnvelope` to Orchestrator Mailbox
- Registry query: Call `fabric.discover_capabilities()` or `fabric.find_relevant_prompts()`

---

## 16. Execution Flows Per Tier

### LOW Tier (< 2 seconds)

```
1. Concierge DISPATCHING: LLM calls invoke_capability("tool.execute.weather_api", params={city: "SF"})
2. ToolDispatcher -> IDispatchPort -> FabricOrchAdapter
3. FabricOrchAdapter detects tier=LOW, calls fabric.execute() directly
4. Fabric pipeline:
   a. Registry lookup: "tool.execute.weather_api" -> WeatherApiContract
   b. Provider Resolution: provider_id="openweather_mcp" -> MCPProvider
   c. Policy Engine: security=PASS, affective=neutral, qos=OK
   d. Context Builder: required_context=[] (no SessionState needed for weather)
   e. Execute: MCP call to openweather_mcp server
   f. Result: CapabilityResult{success=true, data={temp: 65, conditions: "sunny"}, duration_ms=800}
5. Fabric emits k1.capability.completed.v1 on Event Bus
6. CapabilityResult returns to Concierge DISPATCHING (same LLM call)
7. LLM generates response: "It's 65F and sunny in San Francisco!"
8. Concierge DELIVERING -> OUTPUT_CHANNEL
```

**Total time**: 800ms (Fabric) + 500ms (LLM response) = ~1.3s

### MEDIUM Tier (2-10 seconds)

```
1. Concierge DISPATCHING: FSM creates TaskEnvelope{tier=MEDIUM, capabilities=["tool.execute.calendar_create", "tool.execute.send_notification"]}
2. FabricOrchAdapter sends TaskEnvelope to Orchestrator Mailbox
3. Concierge LLM generates preliminary ack: "Setting up that reminder for you..."
4. COMPANIONING: sends ack to user

5. Orchestrator receives TaskEnvelope, tier=MEDIUM:
   a. Step 1: fabric.execute({name: "tool.execute.calendar_create", params: {event: "dentist", date: "2026-02-10 at 3pm"}})
      -> Fabric resolves, executes via Google Calendar MCP
      -> CapabilityResult{success=true, data={event_id: "cal-123"}}
   b. Step 2: fabric.execute({name: "tool.execute.send_notification", params: {message: "Dentist appointment set for Feb 10", target: "family_chat"}})
      -> Fabric resolves, executes via Messaging MCP
      -> CapabilityResult{success=true}
   c. Orchestrator aggregates results, emits to DeltaBus

6. Concierge receives aggregated results via DeltaBus -> Aggregation Window
7. DELIVERING: LLM generates final response with tool_results + cognitive tools
8. OUTPUT_CHANNEL
```

**Total time**: 1.5s (step 1) + 1.0s (step 2) + 1.0s (LLM) = ~3.5s

### HIGH Tier (10-60 seconds)

```
1. Concierge DISPATCHING: FSM creates TaskEnvelope{tier=HIGH, intent="plan birthday party for Mom"}
2. FabricOrchAdapter sends TaskEnvelope to Orchestrator Mailbox
3. Concierge LLM generates preliminary ack + cognitive tools
4. COMPANIONING: ack to user

5. Orchestrator receives TaskEnvelope, tier=HIGH:
   a. Creates PlanRequest, sends to Planner Mailbox

6. Planner Stage 1 (SKETCH):
   a. LLM calls discover_capabilities(domain="restaurant") -> Fabric Retrieval -> Top-10 tools
   b. LLM calls discover_capabilities(domain="cake_delivery") -> Fabric Retrieval -> Top-10 tools
   c. LLM calls discover_capabilities(domain="messaging") -> Fabric Retrieval -> Top-10 tools
   d. LLM calls recall_for_planning("Mom birthday preferences") -> K0 Bridge (NOT Fabric)
   e. LLM calls query_planning_context(sections=["beliefs_active"]) -> SessionState (NOT Fabric)
   f. Produces rough plan sketch

7. Planner Stage 2 (EXPAND):
   a. LLM calls find_relevant_prompts(intent="invitation_drafting") -> Fabric Retrieval -> Top-10 prompts
   b. Maps each step to capability + prompt + params

8. Planner Stage 3 (VALIDATE): LLM verifies DAG, schemas, safety
9. Planner Stage 4 (COMMIT): Persist CommittedPlan to K0 WAL (deterministic, no LLM)

10. CommittedPlan returns to Orchestrator

11. Orchestrator DAG execution via Fabric:
    a. Parallel batch 1 (no deps):
       - fabric.execute(s1: restaurant_booking) -> 2s
       - fabric.execute(s2: cake_order) -> 1.5s
       - fabric.execute(s3: k0_recall contacts) -> 0.5s
    b. Sequential after s1+s3 complete:
       - fabric.execute(s4: invitation_sender agent) -> 5s (agent with own LLM)
    c. Progress deltas to DeltaBus -> Concierge PROGRESSING -> user sees updates

12. Orchestrator aggregates all results -> DeltaBus -> Concierge

13. DELIVERING: LLM generates final response (8K tokens) + cognitive tools
14. OUTPUT_CHANNEL
```

**Total time**: ~2s (ack) + ~3s (planning) + ~7s (DAG execution) + ~2s (final LLM) = ~14s

---

## 17. Tool Execution Round-Trip (Complete Pipeline)

This is the complete data flow for a single tool execution through Fabric, from invocation to result delivery to the user. Corresponds to the skeleton diagram edges in the TOOL EXECUTION & RESULT PIPELINE section.

```
STEP 1: INVOKE
  Caller (Concierge/Orchestrator/Sub-Agent) sends CapabilityRequest to Fabric

STEP 2: RESOLVE
  Fabric Registry lookup -> Contract found
  Provider Resolution -> Provider selected via Policy Engine

STEP 3: BUILD CONTEXT
  Context Builder reads SessionState (required_context sections)
  Token budget applied (128K ceiling)
  Prompt template compiled (if applicable)

STEP 4: ROUTE TO PROVIDER
  Fabric routes to appropriate execution runtime:
  - MCP Provider    -> MCP Server (local stdio or remote SSE/HTTP)
  - WASM Provider   -> WASM Sandbox (isolated computation)
  - Bridge Provider -> K0 via Cross-Kernel Bridge
  - Agent Provider  -> Agent Factory -> new agent with own LLM
  - Workflow Provider -> Orchestrator (recursive DAG execution)

STEP 5: EXECUTE
  Provider runs the tool/agent/workflow
  Waits for response (within circuit breaker timeout)

STEP 6: RESULT
  Provider returns CapabilityResult{success, data, error, duration_ms}
  Fabric updates registry metrics: success_rate, avg_latency, invocation_count

STEP 7: EMIT EVENTS
  Fabric emits on K1 Event Bus:
  - k1.capability.completed.v1 (if success)
  - k1.capability.failed.v1 (if error)
  All events carry cognitive_trace_id

STEP 8: RETURN TO CALLER
  CapabilityResult flows back to caller:
  - LOW path:  Fabric -> Concierge COMPANIONING -> TOOL_RESULT_BUFFER -> DELIVERING
  - MED/HIGH:  Fabric -> Orchestrator -> aggregation -> DeltaBus -> Concierge -> DELIVERING
```

---

## 18. Workflow Integration

### How a Plan Becomes a Workflow

1. A HIGH-tier task runs successfully through the full pipeline
2. User says: "Do this every Monday morning" or "Make this a workflow"
3. Concierge recognizes `save_workflow` intent (UltraBERT classification)
4. The `CommittedPlan` is saved to the **Workflow Registry** as a `WorkflowSpec`
5. A `TriggerSpec` is attached based on user request (cron, event, or manual)

### Workflow Execution (No Re-Planning)

```
Workflow Scheduler (cron fires at scheduled time)
  -> Workflow Compiler rehydrates DAG from WorkflowSpec
  -> Validates all referenced capabilities still exist in registry
  -> If schema drift detected:
       a. Small drift (new optional field): auto-fill with defaults, notify user
       b. Large drift (tool removed): store gap in K0 P06 proactive memory
       c. Next time user is free: Concierge proactively asks with justification
  -> Workflow Run Supervisor creates Run Manifest (pinned version + hash)
  -> Orchestrator executes the DAG via Fabric (same path as HIGH tier)
  -> Results delivered to user (or logged if no active session)
```

### Cross-Workflow Triggers

A workflow step can invoke another workflow:

```yaml
step:
  id: "s3"
  capability: "workflow.run.weekly_grocery_list"
  params:
    trigger_reason: "birthday_party_prep"
    override_params: { extra_items: ["birthday cake ingredients"] }
  deps: ["s1"]
```

Guard rails:

- Max workflow depth: 3 (workflow -> workflow -> workflow, no deeper)
- Cycle detection: validated in Planner Stage 3 VALIDATE (or Workflow Compiler on rehydration)
- Each sub-workflow gets its own Run Manifest for audit trail

---

## 19. Error Handling and Circuit Breakers

### Error Categories

| Error | Source | Handling |
|---|---|---|
| `capability_not_found` | Registry lookup | Return immediately, no retry |
| `access_denied` | Policy Engine security check | Return immediately, no retry |
| `provider_offline` | Provider health check | Return immediately, update availability to OFFLINE |
| `provider_timeout` | Execution exceeds circuit breaker timeout | Circuit breaker trips, fallback |
| `provider_error` | Provider returns error | Retry up to 2 times (configurable) |
| `context_build_failed` | SessionState read failure | Use stale read (circuit breaker fallback) |
| `budget_exceeded` | Token budget overflow | Compress context, retry once |

### Circuit Breaker Configuration

```yaml
circuit_breaker:
  name: "CB: Capability Fabric"
  timeout_ms: 30000                              # 30 seconds per invocation
  failure_threshold: 5                           # 5 failures per minute
  failure_window_ms: 60000                       # 1 minute sliding window
  half_open_after_ms: 30000                      # Try one request after 30s
  fallback: "capability_unavailable"             # Return error to caller
```

Per-provider circuit breakers:

| Provider Type | Timeout | Threshold | Fallback |
|---|---|---|---|
| MCP (local) | 10s | 3/min | tool offline |
| MCP (remote) | 15s | 3/min | tool offline |
| WASM | 5s | 5/min | computation failed |
| Bridge (K0) | 10s | 3/min | LOCAL COLD fallback |
| Agent | 30s | 2/min | agent execution failed |
| Workflow | 60s | 1/min | workflow failed |

### Retry Strategy

```
Attempt 1: Execute normally
  -> Transient failure (network, timeout)
Attempt 2: Same provider, same params (confirm persistent failure)
  -> Same failure
Attempt 3: NOT AUTOMATIC
  -> Return CapabilityResult{success=false, error=..., retriable=false}
  -> Caller decides (Orchestrator: cancel dependent steps, Concierge: inform user)
```

### Error Event Emission

Every error emits `k1.capability.failed.v1` on the Event Bus:

```yaml
k1.capability.failed.v1:
  request_id: "uuid"
  capability_name: "tool.execute.restaurant_booking"
  error_code: "provider_timeout"
  error_message: "MCP server did not respond within 10s"
  provider_id: "opentable_mcp"
  retry_count: 2
  trace_id: "cognitive-trace-uuid"
  timestamp: "2026-02-06T14:30:00Z"
```

---

## 20. Event Bus Integration

### Events Emitted by Fabric

| Event Topic | When | Payload |
|---|---|---|
| `k1.capability.invoked.v1` | Before execution starts | request_id, capability_name, caller, tier, trace_id |
| `k1.capability.completed.v1` | After successful execution | request_id, capability_name, duration_ms, provider_id, trace_id |
| `k1.capability.failed.v1` | After failed execution | request_id, capability_name, error_code, retry_count, trace_id |
| `k1.fabric.capability.registered.v1` | New contract added to registry | capability_name, version, provider_type |
| `k1.fabric.capability.unregistered.v1` | Contract removed from registry | capability_name |
| `k1.fabric.contract.validation.failed.v1` | Contract failed schema validation | file_path, errors[] |
| `k1.fabric.learning.signal.v1` | Learning signal from execution outcome | capability_name, success, latency, user_satisfaction |
| `k1.fabric.provider.health.changed.v1` | Provider availability changed | provider_id, old_status, new_status |

### Events Consumed by Fabric

| Event Topic | From | Action |
|---|---|---|
| `k1.orchestration.step.execute.v1` | Orchestrator | Trigger capability execution |
| `k1.planner.discovery.request.v1` | Planner tool handler | Trigger retrieval search |
| `k1.fabric.provider.health.check.v1` | Health monitor | Run health check on provider |

---

## 21. Observability and Telemetry

### Cognitive Trace ID

Every Fabric operation carries a `cognitive_trace_id` that unifies causality across the entire request chain:

```
User input -> Concierge (trace_id=X) -> Orchestrator (trace_id=X) -> Fabric (trace_id=X) -> Provider (trace_id=X)
```

### Structured Logging

Every Fabric operation logs:

```json
{
  "timestamp": "2026-02-06T14:30:00.123Z",
  "level": "INFO",
  "component": "fabric.execution",
  "trace_id": "cognitive-trace-uuid",
  "request_id": "uuid",
  "capability_name": "tool.execute.restaurant_booking",
  "provider_id": "opentable_mcp",
  "phase": "execute",
  "duration_ms": 1850,
  "success": true
}
```

Phases logged: `resolve`, `policy_check`, `context_build`, `execute`, `result_return`

### Metrics Emitted

| Metric | Type | Labels | Purpose |
|---|---|---|---|
| `fabric.execution.duration_ms` | Histogram | capability_name, provider_type, tier | Execution latency distribution |
| `fabric.execution.success_rate` | Counter | capability_name, success | Success/failure counts |
| `fabric.retrieval.duration_ms` | Histogram | query_type (discover/prompt) | Retrieval latency |
| `fabric.retrieval.result_count` | Histogram | query_type | How many results returned |
| `fabric.registry.size` | Gauge | capability_type | Current registry size |
| `fabric.circuit_breaker.state` | Gauge | provider_id, state | CB state (closed/open/half-open) |
| `fabric.context_build.tokens` | Histogram | capability_name | Tokens consumed per context build |

---

## 22. Performance Targets

| Operation | Target Latency | Max Latency | Notes |
|---|---|---|---|
| Registry lookup (exact name) | < 1ms | 5ms | Hash table O(1) |
| Retrieval search (10K caps) | < 20ms | 50ms | FAISS + filter + rank |
| Retrieval search (100K caps) | < 50ms | 100ms | FAISS IVF index |
| Provider resolution | < 5ms | 10ms | Registry + policy evaluation |
| Context build (small) | < 10ms | 50ms | 2-3 SessionState sections |
| Context build (large) | < 50ms | 200ms | 6+ sections, token compression |
| MCP execution (local) | < 2s | 10s | Depends on tool |
| MCP execution (remote) | < 5s | 15s | Network latency |
| WASM execution | < 1s | 5s | Sandboxed computation |
| Bridge execution (K0) | < 2s | 10s | Cross-kernel communication |
| Agent execution | < 10s | 30s | Agent has own LLM calls |
| Full Fabric overhead | < 100ms | 500ms | Everything except provider execution time |

"Fabric overhead" = resolve + policy + context build + routing + result packaging. The actual provider execution time is external to Fabric.

---

## 23. Security Model

### Principle: Least Privilege

Every entity that touches Fabric gets the minimum access required.

| Entity | Can Execute | Can Read SessionState | Can Write SessionState |
|---|---|---|---|
| Concierge (via IDispatchPort) | Any capability | All sections (Single Writer) | Yes (Single Writer) |
| Orchestrator | Capabilities from TaskEnvelope/CommittedPlan | Multi-reader (lock-free) | Never (DeltaBus only) |
| Planner | Discovery tools only (read-only) | Multi-reader (lock-free) | Never (DeltaBus only) |
| Sub-Agent | Only `tools_granted[]` from plan step | Declared `required_context` sections only | Never (DeltaBus only) |
| Workflow | Capabilities from frozen plan | Same as Orchestrator | Never |

### Safety Band Enforcement

```
Safety bands: GREEN < AMBER < RED < CRISIS

User's current band: from SessionState control.safety_band
Capability's minimum band: from contract.safety_band_min

Rule: user_band >= capability_band_min
  GREEN user  -> can use GREEN-min tools only
  AMBER user  -> can use GREEN and AMBER-min tools
  RED user    -> can use GREEN, AMBER, and RED-min tools
  CRISIS      -> immediate safety protocol, bypasses normal Fabric path
```

### Sub-Agent Tool Scoping

```python
class ToolScope:
    """
    Enforces that a sub-agent can only invoke capabilities
    from its tools_granted list.
    """
    allowed_tools: set[str]  # e.g., {"tool.execute.send_message", "tool.read.contact_lookup"}

    def validate(self, capability_name: str) -> bool:
        if capability_name not in self.allowed_tools:
            raise AccessDeniedError(
                f"Agent not authorized to invoke '{capability_name}'. "
                f"Allowed: {self.allowed_tools}"
            )
        return True
```

---

## 24. Dependency Graph and Build Order

### Internal Subsystem Dependencies

```
[1] Contract System ────────────────────────────────────────────────┐
    (schemas, validation, YAML loading)                             |
         |                                                          |
         v                                                          |
[2] Capability Registry ──────────────────────────────────┐         |
    (indexes, embedding, lookup, search)                  |         |
         |                              |                 |         |
         v                              v                 |         |
[3] Retrieval Engine           [4] Provider Resolution    |         |
    (semantic Top-K)               (name -> provider)     |         |
         |                              |                 |         |
         |                              v                 |         |
         |                    [5] Policy Engine            |         |
         |                       (security, affect, QoS)  |         |
         |                              |                 |         |
         |                              v                 |         |
         |                    [6] Execution Runtime        |         |
         |                       (MCP, WASM, Bridge,      |         |
         |                        Agent, Workflow,         |         |
         |                        Concierge providers)     |         |
         |                              |                 |         |
         |                              v                 v         v
         |                    [7] Context Builder ←──── Registry + Contracts
         |                       (SessionState read,
         |                        token budget,
         |                        prompt compilation)
         |
         v
    Serves Planner                Serves Orchestrator + Concierge
```

### Recommended Build Order

| Phase | What | Why First |
|---|---|---|
| Phase 1 | Contract schemas + validation | Everything reads contracts |
| Phase 2 | Capability Registry (in-memory, no embeddings yet) | Execution and retrieval both need it |
| Phase 3 | Provider Resolution + basic Policy (security only) | Enables execution without retrieval |
| Phase 4 | Execution Runtime (MCP Provider first) | MCP is most common provider type |
| Phase 5 | Context Builder | Agents need context for execution |
| Phase 6 | Embedding Index + Retrieval Engine | Planner needs this, but it's HIGH tier only |
| Phase 7 | Full Policy Engine (affective, cognitive, QoS) | Refinement, not blocking |
| Phase 8 | Agent Factory | Depends on all above subsystems |
| Phase 9 | Workflow Provider | Depends on Agent Factory + Orchestrator integration |

### External Dependencies (Things Fabric Needs From Other K1 Components)

| Dependency | Component | What Fabric Uses |
|---|---|---|
| SessionState | K1 SessionState Store | Multi-reader access for context building |
| K1 Event Bus | K1 Coordination | Event emission + consumption |
| Model Gateway | K1 L2.5 (co-located with Fabric) | Agent Factory grants LLM access to agents |
| Prompt System | K1 L2.5 (co-located with Fabric) | Prompt resolution + compilation for context building |
| Bridge Client | K1 Cross-Kernel Bridge | Bridge Provider needs K0 access |
| Delta Bus | K1 Coordination | Agents emit deltas through this |
| WFQ Scheduler | K1 Coordination | Mailbox priority for agents |

---

## 25. Directory Structure (Target)

```
k1/fabric/
  __init__.py
  fabric.py                          # CapabilityFabric main class (API surface)
  types.py                           # All Fabric types: CapabilityRequest, CapabilityResult, etc.

  core/
    __init__.py
    registry.py                      # CapabilityRegistry (in-memory indexed catalog)
    registry_types.py                # Contract types, ScoredCapability, SearchQuery
    context_builder.py               # Context Builder (SessionState -> ExecutionContext)
    context_budget.py                # Token budget manager (128K ceiling, compression)
    module_loader.py                 # Watches k1/contracts/, hot-reload on change
    module_validator.py              # Schema validation for contracts

  retrieval/
    __init__.py
    retrieval_engine.py              # Semantic Top-K retrieval (Role 1)
    embedding_index.py               # FAISS vector index for semantic search
    hard_filter.py                   # Safety band + availability + satisfiability filter
    soft_ranker.py                   # Weighted composite scoring (0.4/0.3/0.15/0.15)
    top_k_selector.py                # Select top K from scored candidates

  provider_resolution/
    __init__.py
    resolver.py                      # Provider Resolution Engine (name -> provider)
    provider_registry.py             # Provider configurations (MCP endpoints, WASM paths)
    provider_matcher.py              # Capability name -> provider candidates
    provider_selector.py             # Policy-scored provider selection
    provider_factory.py              # Instantiate provider handlers

  policy/
    __init__.py
    policy_engine.py                 # Composite policy evaluation (4 dimensions)
    security_context.py              # Safety band access control (hard gate)
    affective_routing.py             # Emotion-aware provider selection
    cognitive_load_routing.py        # Complexity-aware provider selection
    qos_integration.py               # Budget-aware and latency-aware selection
    tool_scope.py                    # Sub-agent tool access scoping

  providers/
    __init__.py
    base_provider.py                 # CapabilityProvider protocol/interface
    mcp_provider.py                  # MCP tool execution (stdio/SSE/HTTP)
    wasm_provider.py                 # WASM sandboxed execution
    bridge_provider.py               # K0 via Cross-Kernel Bridge
    agent_provider.py                # Agent Factory + agent execution
    workflow_provider.py             # Workflow rehydration + Orchestrator routing
    concierge_provider.py            # Concierge FSM state handlers

  contracts/
    __init__.py
    tool_contract.py                 # ToolContract dataclass + parser
    agent_contract.py                # AgentContract dataclass + parser
    prompt_contract.py               # PromptContract dataclass + parser
    workflow_contract.py             # WorkflowContract dataclass + parser

  capability_types/
    __init__.py
    type_registry.py                 # Capability type conventions (agent.spawn.*, tool.execute.*, etc.)

  module_registry/
    __init__.py
    # (Merged into core/registry.py + core/module_loader.py)
    # This directory exists for K0-pattern compatibility

  events/
    __init__.py
    fabric_events.py                 # All event topic definitions + payloads
    event_emitter.py                 # Event emission wrapper (enforces trace_id)

  circuit_breaker/
    __init__.py
    breaker.py                       # CircuitBreaker implementation
    breaker_config.py                # Per-provider CB configurations

  health/
    __init__.py
    health_checker.py                # Provider health monitoring
    availability_tracker.py          # Track ONLINE/DEGRADED/OFFLINE per provider
```

---

## 26. Open Design Questions

These items from the whiteboard (Section 16) are prerequisites before implementation:

| # | Topic | Status | Blocks |
|---|---|---|---|
| 1 | **Planner Tool Schemas**: Exact JSON input/output schemas for `discover_capabilities()`, `find_relevant_prompts()`, `query_planning_context()`, `recall_for_planning()` | NEEDS DESIGN SESSION | Retrieval Engine API, Planner integration |
| 2 | **Core Envelope Schemas**: Finalize TaskEnvelope, PlanRequest, CommittedPlan, CapabilityRequest, CapabilityResult as domain-agnostic protobuf/FlatBuffer/Pydantic | NEEDS DESIGN SESSION | All inter-component communication |
| 3 | **Fabric Retrieval API**: How Planner tool calls map to Fabric's internal retrieval pipeline. Token budgets per retrieval response. | NEEDS DESIGN SESSION | Planner <-> Fabric integration |
| 4 | **Tool/Agent/Prompt Registry Schema**: Finalize the standard YAML contract format (drafts exist in this document and whiteboard S15) | DRAFT EXISTS | Contract validation, hot-reload |
| 5 | **WorkflowSpec Schema**: Finalize with cross-workflow trigger support + version management | DRAFT EXISTS | Workflow Provider |
| 6 | **Agent Prompt Injection**: Exact Context Builder assembly -- what goes where in the agent's context window, token allocation per section | NEEDS DESIGN SESSION | Agent Factory, Context Builder |
| 7 | **Embedding Model Selection**: Which embedding model for the semantic index? Must match K1 default for consistency. Dimension size affects FAISS index. | NEEDS DECISION | Retrieval Engine |
| 8 | **Multi-Provider Selection**: When multiple providers handle the same capability, how exactly does the soft ranking work? Is it the Retrieval Soft Ranker or a separate Provider Soft Ranker? | NEEDS CLARIFICATION | Provider Resolution, Policy Engine |
| 9 | **Fabric Mailbox**: Does Fabric need its own Mailbox (shown in skeleton as `FABRIC_MAILBOX` with WFQ REALTIME priority), or is it purely synchronous per-request? | NEEDS DECISION | Concurrency model |
| 10 | **ADR-K004 Update**: ADR-K004 references Contract-Net Protocol. It needs updating to reflect Fabric as Resolution + Retrieval + Agent Factory (supersedes Contract-Net). | NEEDS ADR REVISION | Governance compliance |

---

*This document is the single design reference for Capability Fabric within the K1 Cognitive Kernel. All implementation must comply with the invariants, schemas, and flows described here. For the broader K1 architecture context, see `k1_cognitive_architecture_skeleton.mmd` and `whiteboard_concierge_orchestrator_planner_fabric.md`.*
