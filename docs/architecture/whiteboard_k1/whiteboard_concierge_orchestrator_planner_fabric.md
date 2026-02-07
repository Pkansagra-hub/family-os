# Whiteboard: Concierge / Orchestrator / Planner / Fabric

> **Status**: Design Discussion (Whiteboard)
> **Date**: 2026-02-05
> **Scope**: End-to-end flow from user input through Concierge, Orchestrator, Planner, and Capability Fabric
> **Artifacts Updated**: `k1_cognitive_architecture_skeleton.mmd`, `k1/concierge/concierge.mmd`

---

## 1. Component Roles (Locked)

| Component | Role | Has LLM? | Has Tools? | Writes SessionState? |
|---|---|---|---|---|
| **Concierge** | Conversation conductor, complexity router, single writer | Yes | Cognitive + Read + Action | Yes (Single Writer, ADR-0017) |
| **Planner** | Plan architect -- discovers capabilities, builds DAG | Yes | Discovery tools (read-only) | Never (emits deltas to DeltaBus) |
| **Orchestrator** | Blind DAG executor -- LangGraph-style runtime | No | No | Never (emits deltas to DeltaBus) |
| **Fabric** | Capability resolution + agent factory + execution runtime | No | N/A -- it IS the runtime | Never |
| **Spawned Agents** | Per-step workers (created by Fabric on-demand) | Yes (each gets LLM) | Whatever the plan step specifies | Never (emit deltas to DeltaBus) |

**Key analogy**: Orchestrator = LangGraph execution engine. Someone (the Planner) gives it explicit instructions on what to do. It does not think. It follows.

---

## 2. How LLMs Interact with SessionState

### Two-Phase Write Per Turn (Locked)

Every user turn triggers exactly two phases of SessionState writes. Both happen inside the Concierge (Single Writer Pattern).

**Phase 1: UltraBERT (22ms, deterministic, pre-LLM)**

UltraBERT v4 (ModernBERT-base, 149M params, 12 classification heads) runs a single forward pass and the Concierge FSM writes deterministically -- these are NOT tool calls:

| Head | Writes To | Data |
|---|---|---|
| Intent Head (multi-label) | `control.intents` | `{primary, all[], scores{}}` |
| Ingress Head (multi-label) | `control.domains` | `domains[] above threshold` |
| Safety Head (4-band) | `control.safety_band` | GREEN / AMBER / RED / CRISIS |
| Emotions Head (44-class) | `affective_now.raw` | Detected emotion |
| Sentiment Head (5-level) | `affective_now.sentiment` | very_negative to very_positive |
| NER Head (GlobalPointer) | `beliefs_active.entities` | PERSON, ORG, LOC, TIME, DATE |
| Relations Head | `beliefs_active.relations` | spouse_of, parent_of, works_at |
| Temporal Resolution | `temporal_context` | Resolved absolute times |

**Phase 2: LLM Cognitive Tools (semantic understanding, post-UltraBERT)**

The Concierge LLM decides which tools to call based on conversation understanding. Zero tool calls for trivial turns ("ok cool"). Multiple calls for state-changing turns ("Actually it was Thursday not Wednesday").

| Cognitive Tool | What LLM Detects | Writes To |
|---|---|---|
| `update_scoreboard()` | Pronoun resolution, QUD, salience, topic shift | `scoreboard` |
| `update_beliefs()` | Implicit facts, user corrections, invalidations | `beliefs_active`, `beliefs_history` |
| `update_clarifications()` | Semantic gaps only LLM can detect | `clarifications` |
| `update_narrative()` | Thread switches, resumptions, new threads | `narrative_active` |
| `refine_affect()` | Sarcasm, nuance UltraBERT missed | `affective_now` (override) |
| `promote_belief()` | User referencing old context (bring WARM to HOT) | `beliefs_active` (from `beliefs_history`) |

Every cognitive tool call goes through `MutationGuard.preflight(section, op, data) -> Approval`.

### Why Tool Calls Over Structured Output (Locked)

Decision: LLM cognitive tools win over structured output because:

1. **Zero overhead on simple turns**: "ok cool" = 0 tool calls, no empty JSON fields
2. **Independent validation**: Each tool call goes through MutationGuard separately
3. **Native to LLM training**: Function-calling is what models are trained for
4. **Auditable**: Every tool call logged in `history_active` with trace ID
5. **Selective**: LLM only calls what it detects needs updating

### 12-Section Detection Matrix

| Section | Phase 1 (UltraBERT) | Phase 2 (LLM) | System-Only |
|---|---|---|---|
| `control` | intents, domains, safety_band | -- | leases (internal) |
| `beliefs_active` | entities, relations | corrections, implicit facts | -- |
| `scoreboard` | -- | referents, QUD, salience | -- |
| `history_active` | -- | -- | auto-append (every turn) |
| `clarifications` | -- | semantic gaps | -- |
| `affective_now` | raw emotion, sentiment | sarcasm override | -- |
| `narrative_active` | -- | thread state | -- |
| `meta` | -- | -- | auto-update (timestamps) |
| `beliefs_history` (WARM) | -- | invalidations | eviction engine |
| `history_recent` (WARM) | -- | -- | eviction engine |
| `persona` (WARM) | -- | -- | experience layer heuristic |
| `telemetry` (WARM) | -- | -- | metrics aggregator |

---

## 3. Concierge Tool Categories (Locked)

### Cognitive Tools (6) -- LLM detects what to update

Available on ALL tiers (LOW, MEDIUM, HIGH). These run during the LLM call in DISPATCHING (LOW), preliminary ack (MED/HIGH), and DELIVERING (all tiers).

```
update_scoreboard()       -- referents, QUD, salience, topic shift
update_beliefs()          -- new facts, corrections, invalidations
update_clarifications()   -- semantic gaps, resolved gaps
update_narrative()        -- thread switch/resume/new/continue
refine_affect()           -- override emotion when sarcasm/nuance detected
promote_belief()          -- WARM to HOT fact promotion
```

### Read Tools (3) -- Context retrieval

```
recall_memory()           -- K0 long-term memory via Bridge
discover_capabilities()   -- Capability Registry query
summarize_context()       -- Token budget compression
```

### Action Tools (3) -- Execution and delegation

```
invoke_capability()       -- Direct Fabric execution (LOW tier fast path)
spawn_via_fabric()        -- Dynamic agent creation
execute_workflow()        -- Pre-compiled workflow invocation
```

---

## 4. Complexity-Based Routing (Locked)

UltraBERT classifies every turn into a complexity tier. The tier determines the execution path.

### Tier Decision Factors

| Factor | Source | Impact |
|---|---|---|
| Intent count | `len(intents.all[])` | Multi-intent = bump |
| Domain count | `len(domains[])` | Cross-domain = bump |
| Intent type | `intents.primary` | set_reminder = LOW, plan_trip = HIGH |
| Safety band | `safety_band` | CRISIS = immediate protocol |
| Emotion intensity | `emotions.intensity` | High emotional = bump |

### Flow Per Tier

**LOW (< 2s) -- Tool first, then LLM response**

```
DISPATCHING --> invoke_capability() --> Fabric executes tool
           --> tool_result to TOOL_RESULT_BUFFER
           --> DELIVERING: LLM call with tool_result (~500 tokens)
           --> response + cognitive tool calls
           --> OUTPUT_CHANNEL
```

Concierge calls Fabric directly via `invoke_capability()`. No Orchestrator. No Planner.

**MEDIUM (2-10s) -- Concierge delegates to Orchestrator, no planning**

MEDIUM tasks need 1-2 specialized agents or tools but no full planning pipeline. Concierge has `invoke_capability()`, `spawn_via_fabric()` action tools. For MEDIUM, Concierge constructs the TaskEnvelope with enough detail (which capabilities, what params) and sends it to Orchestrator. Orchestrator coordinates 1-2 Fabric calls and returns results via DeltaBus.

```
DISPATCHING --> TaskEnvelope{intent, capabilities[], params, context, tier=MEDIUM}
           --> Sends to Orchestrator Mailbox
           --> LLM preliminary ack (~200 tokens) + cognitive tools
           --> COMPANIONING: ack to user
Orchestrator --> direct CapabilityRequest(s) to Fabric (1-2 calls, no planning)
           --> tool_results back to Orchestrator
           --> aggregated results via DeltaBus to Concierge
           --> DELIVERING: LLM final response (2K tokens) + cognitive tools
           --> OUTPUT_CHANNEL
```

Key difference from HIGH: Concierge already knows WHAT to do (it has read tools to discover capabilities). It just needs Orchestrator to coordinate execution because the task has 2+ steps or takes >2s.

**HIGH (10-60s) -- Full planning pipeline**

```
DISPATCHING --> TaskEnvelope to Orchestrator Mailbox
           --> LLM preliminary ack (~200 tokens) + cognitive tools
           --> COMPANIONING: ack to user
Orchestrator --> PlanRequest to Planner
Planner    --> Stage 1-4 (see section 5)
           --> CommittedPlan back to Orchestrator
Orchestrator --> PARALLEL_DAG execution via Fabric
           --> progress deltas to PROGRESSING
           --> DELIVERING: LLM final response (8K tokens) + cognitive tools
           --> OUTPUT_CHANNEL
```

**CRISIS -- Safety protocol**

```
ACKING --> CRISIS detected --> Safety Agent --> immediate response
```

---

## 5. Planner: Agentic Planning with Discovery Tools

### Key Design Decision: Planner LLM Has Tools

**Previous skeleton said**: "Planner uses prompts, NOT function-calling tools"

**New decision**: The Planner LLM is an agentic planner with read-only discovery tools. It reasons about the task, discovers what capabilities and prompts are available, then builds a plan grounded in reality -- not imagination.

**Rationale**:

- Without tools: Entire capability catalog + prompt catalog dumped into prompt context. Wasteful tokens, doesn't scale as capabilities grow.
- With tools: Planner LLM queries only relevant capabilities/prompts. Scales to unlimited capabilities.
- Mirrors Concierge pattern: Concierge has cognitive/read/action tools. Planner has discovery tools.

### Planner Discovery Tools (Read-Only)

| Tool | Queries | Returns | Example |
|---|---|---|---|
| `discover_capabilities(domain?, intent?)` | Capability Registry | Available capabilities with input/output schemas | `discover_capabilities(domain="restaurant")` -> `[{name: "tool.execute.restaurant_booking", params: {date, party_size, location}, provider: "opentable_mcp"}]` |
| `find_relevant_prompts(intent?, domain?)` | Prompt Registry | Matching prompt templates with variables | `find_relevant_prompts(intent="birthday_party")` -> `[{name: "party_planner_v2", vars: [guest_list, venue, date]}]` |
| `query_planning_context(sections?)` | SessionState (multi-reader) | User context relevant for plan construction | `query_planning_context(sections=["beliefs_active", "persona"])` -> `{beliefs: [{fact: "Mom lives in San Jose"}], persona: {style: "warm"}}` |
| `recall_for_planning(query)` | K0 via Bridge | Long-term memory relevant to plan | `recall_for_planning("Mom's food preferences")` -> `{facts: [{fact: "Mom is vegetarian", confidence: 0.95}]}` |

**All read-only. The Planner never writes, never executes, never spawns.**

### 4-Stage Planning Pipeline (Revised)

**Stage 1: SKETCH (LLM, ~2K tokens)**

Planner LLM receives intent + context from PlanRequest. Uses discovery tools to understand what's available. Produces a rough plan outline.

```
Input:  PlanRequest{intent: "plan birthday party for Mom next Saturday",
                    constraints: {budget: unknown, safety_band: GREEN}}

LLM thinks: "I need to book a venue, order cake, send invitations"
LLM calls:  discover_capabilities(domain="restaurant")
LLM calls:  discover_capabilities(domain="cake_delivery")
LLM calls:  discover_capabilities(domain="messaging")
LLM calls:  query_planning_context(sections=["beliefs_active"])
LLM calls:  recall_for_planning("Mom birthday preferences")

Output: Rough plan sketch with identified capabilities
```

If requirements are unclear, Planner fires HIL: Requirement Clarification -> question goes to user via OUTPUT_CHANNEL -> user answer returns -> back to Stage 1.

**Stage 2: EXPAND (LLM, ~1K tokens)**

Map each plan step to a concrete capability + prompt + parameters. Build the dependency graph.

```
LLM calls:  find_relevant_prompts(intent="restaurant_booking")
LLM calls:  find_relevant_prompts(intent="invitation_drafting")

Output: Expanded plan with steps[], each step has:
  - capability name (from Capability Registry)
  - prompt template (from Prompt Registry)
  - parameters (from context + user input)
  - dependencies (which steps must complete first)
```

**Stage 3: VALIDATE (LLM arbiter, ~500 tokens)**

Validation checks:

- All referenced capabilities exist in registry (real, not hallucinated)
- Dependency graph is acyclic (valid DAG)
- No safety band violations
- No constraint violations (budget, time, permissions)
- Capability schemas match planned parameters

If risky, Planner fires HIL: Plan Approval -> user sees plan -> approves/modifies -> back to Stage 3.

**Stage 4: COMMIT (Deterministic, NO LLM)**

- Persist `CommittedPlan` to K0 WAL (crash recovery)
- Return `CommittedPlan{steps[], dependencies[]}` to Orchestrator

### CommittedPlan Schema

```yaml
CommittedPlan:
  plan_id: uuid
  intent: "plan birthday party for Mom next Saturday"
  created_at: "2026-02-05T14:30:00Z"
  steps:
    - id: s1
      capability: "tool.execute.restaurant_booking"
      prompt_template: "restaurant_booking_v2"
      params: {date: "2026-02-14", party_size: 8, cuisine: "vegetarian"}
      deps: []
    - id: s2
      capability: "tool.execute.cake_order"
      prompt_template: null  # no prompt needed, direct tool
      params: {type: "birthday", flavor: "chocolate", date: "2026-02-14"}
      deps: []
    - id: s3
      capability: "tool.read.k0_recall"
      prompt_template: null
      params: {query: "family members contact info"}
      deps: []
    - id: s4
      capability: "agent.execute.invitation_sender"
      prompt_template: "invitation_drafter_v1"
      params: {event: "birthday_party", recipients: "$s3.result", venue: "$s1.result.venue"}
      deps: [s1, s3]  # needs both venue and contacts
  dependencies:
    s4: [s1, s3]  # explicit DAG edges
```

---

## 6. Orchestrator: Blind DAG Executor

### Core Principle

The Orchestrator is a LangGraph-style execution engine. Someone (the Planner) gives it explicit instructions. It does not think. It follows the plan step by step.

### Orchestrator Has NO LLM, NO Tools

It receives a `CommittedPlan` and mechanically executes it:

```
receive(TaskEnvelope) from Concierge Mailbox
emit(task.accepted) to Concierge FSM

if tier == MEDIUM:
    # No planning needed -- direct execution
    request = CapabilityRequest(envelope.capability, envelope.params, envelope.context)
    result = fabric.invoke(request)
    send(result) to Concierge COMPANIONING

if tier == HIGH:
    # Full planning needed
    plan_request = PlanRequest(envelope.intent, envelope.constraints, envelope.context)
    send(plan_request) to Planner Mailbox
    committed_plan = await(Planner response)

    # DAG Execution
    for step in topological_order(committed_plan.steps, committed_plan.dependencies):
        wait_for(step.deps)
        request = CapabilityRequest(step.capability, step.params, step.prompt, step.context)
        result = fabric.invoke(request)
        step.result = result
        emit_delta(step.id, result)           # progress to DeltaBus
        emit_progress(step.id, result.summary) # to Concierge PROGRESSING

    aggregate(all_results) --> send to Concierge COMPANIONING
```

### DAG Execution: Parallel Where Possible

Given the birthday party example:

```
s1 (restaurant booking) ---+
s2 (cake order)         ---+--- all parallel (no deps) ---> complete
s3 (family contacts)    ---+
                               |
                               v s1 + s3 complete
                          s4 (send invitations) ---> depends on s1 + s3
```

The Orchestrator uses `topological_order()` to determine which steps can run in parallel and which must wait for dependencies. Steps with no dependencies run concurrently via Fabric.

### Message Envelopes

| Sender | Receiver | Envelope | Content |
|---|---|---|---|
| Concierge DISPATCHING | Orchestrator | `TaskEnvelope` | `{intent, context, tier}` |
| Orchestrator | Planner | `PlanRequest` | `{intent, constraints, context}` |
| Planner | Orchestrator | `CommittedPlan` | `{steps[], dependencies[]}` |
| Orchestrator | Fabric | `CapabilityRequest` | `{capability_name, params, prompt_template, context}` |
| Fabric | Orchestrator | `CapabilityResult` | `{success, data, error, duration}` |
| Orchestrator | Concierge | Aggregated results | All `CapabilityResult[]` |

### 3-Phase Orchestration (ADR-0006) -- SUPERSEDED

**Decision**: The Contract-Net Protocol (Task Announcement -> Proposal Bidding -> Multi-Criteria Scoring) from ADR-0006 is **no longer needed**. Fabric's Provider Resolution Engine handles all provider selection with its Policy Engine (QoS + affective + security + cognitive load routing).

ADR-0006 should be revised to describe the Orchestrator purely as a **blind DAG executor**:

- Receives `CommittedPlan` from Planner (HIGH) or `TaskEnvelope` from Concierge (MEDIUM)
- Walks the DAG in topological order
- Calls Fabric per step (Fabric handles provider selection)
- Aggregates results, emits deltas
- No negotiation, no bidding, no scoring -- Fabric does all of that

**Action**: Create superseding ADR that redefines Orchestrator as DAG executor. Reference this whiteboard.

---

## 7. Capability Fabric: Resolution Engine + Agent Factory

### Fabric: Three Responsibilities

Fabric serves three distinct roles in the system:

**Role 1: Intelligent Registry & Retrieval (Serves Planner)**

Fabric manages the Tool Registry, Agent Registry, and Prompt Registry. When the Planner LLM calls `discover_capabilities(domain="restaurant")`, Fabric does NOT dump 100,000 tools into the response. It performs **semantic retrieval** -- returning the top 10 most relevant tools, top 10 most relevant prompts, and top 10 most relevant agents that fulfill the capability the Planner needs.

This is critical for scale. With unlimited tools, agents, and prompts, the Planner cannot see everything. Fabric is the smart recommendation engine that surfaces what matters.

| Planner Tool Call | Fabric Does | Returns |
|---|---|---|
| `discover_capabilities(domain, intent)` | Semantic search across Tool + Agent registries | Top-K capabilities with schemas, ranked by relevance |
| `find_relevant_prompts(intent, domain)` | Semantic search across Prompt Registry | Top-K prompt templates with variable definitions |

**Role 2: Resolution & Execution (Serves Orchestrator + Concierge)**

When it receives a `CapabilityRequest{name, params, prompt_template, context}`:

1. **Resolve**: Look up `capability_name` in Capability Registry
2. **Select Provider**: Policy Engine picks best provider considering:
   - Affective Routing (emotion-aware selection)
   - Cognitive Load Routing (complexity-aware)
   - QoS Integration (budget-aware)
   - Security Context (safety band access control)
3. **Build Context**: Context Builder reads SessionState sections, applies token budget (128K), injects into provider context
4. **Execute** via the appropriate runtime:
   - **MCP Runner**: For MCP tool calls (local or remote servers)
   - **WASM Sandbox**: For sandboxed execution
   - **Bridge**: For K0 operations
   - **Agent Spawn**: Create a new agent from YAML template
5. **Return**: `CapabilityResult{success, data, error, duration}`

**Role 3: Agent Factory (Spawns Per-Step Workers)**

See Agent Spawning section below.

### Agent Spawning (Unlimited Agents)

When a plan step requires `agent.execute.*`, Fabric:

1. Looks up agent template in Agent Registry (e.g., `invitation_sender.yaml`)
2. Agent Factory instantiates the agent with:
   - Its own Mailbox (MPSC queue)
   - LLM access (via Model Gateway)
   - SessionState read access (multi-reader, lock-free)
   - The tools specified in the plan step
   - The prompt template from the plan step
   - The parameters from the plan step
3. Agent executes its task -- it has its own LLM, reasons independently
4. Agent returns `CapabilityResult` to Fabric
5. Agent transitions: ACTIVE -> IDLE (pool for reuse) or DRAINING -> TERMINATED

### Capability Types

```
agent.spawn.*          -- Create agent from template
agent.execute.*        -- Run agent for a task
tool.execute.*         -- Run MCP/WASM tool directly
tool.read.*            -- Read-only tool (K0 queries, etc.)
workflow.run.*         -- Execute pre-compiled workflow
concierge.state.*      -- Concierge internal state operations
```

### Provider Types

| Provider | LLM? | Examples |
|---|---|---|
| Agent Provider | Yes | health_agent, finance_agent, invitation_sender |
| Tool Provider (MCP) | No | calendar_tool, weather_api, restaurant_booking |
| Tool Provider (WASM) | No | Sandboxed computations |
| Workflow Provider | Mixed | Pre-compiled DAGs (may contain agents) |
| Concierge Provider | Yes | FSM state handlers |

---

## 8. Concierge Uses Fabric Directly (LOW Tier)

For LOW tier, the Concierge bypasses Orchestrator entirely:

```
Concierge LLM calls invoke_capability() tool
  --> Fabric receives CapabilityRequest
  --> Fabric resolves, builds context, executes
  --> CapabilityResult returns to Concierge
  --> Concierge LLM generates response with tool_result
```

This means Fabric handles both:

- **Direct calls** from Concierge (LOW tier, fast path)
- **Orchestrated calls** from Orchestrator's DAG (MEDIUM/HIGH tier)

No conflict -- Fabric is stateless per-request. It doesn't care who called it.

---

## 9. Workflow: Saved Plan as Cron Job

### How a Plan Becomes a Workflow

1. A HIGH-tier task runs successfully: Planner builds plan -> Orchestrator executes DAG -> results delivered to user
2. User says: "Do this every Monday morning" or "Make this a workflow"
3. Concierge recognizes the intent (UltraBERT classifies `save_workflow`)
4. The `CommittedPlan` is saved to the **Workflow Registry** as a `WorkflowSpec`
5. A `TriggerSpec` is attached based on user request

### WorkflowSpec Schema

```yaml
WorkflowSpec:
  workflow_id: uuid
  name: "Mom's Weekly Health Check"
  source_plan_id: <reference to original CommittedPlan>
  version: 1
  trigger:
    type: "cron"              # cron | event | manual
    schedule: "0 8 * * MON"   # every Monday at 8am
    timezone: "America/Los_Angeles"
  steps: <same as CommittedPlan.steps[]>
  dependencies: <same as CommittedPlan.dependencies>
  created_at: "2026-02-05T14:30:00Z"
  last_run: null
  active: true
```

### Workflow Execution (No Re-Planning)

```
Workflow Scheduler (cron fires)
  --> Workflow Compiler rehydrates DAG from WorkflowSpec
  --> Workflow Run Supervisor creates Run Manifest (pinned version + hash)
  --> Orchestrator executes the DAG via Fabric (same as HIGH tier execution)
  --> Results delivered to user (or logged if no active session)
```

No Planner involved. The plan is frozen. Orchestrator just runs it.

### Workflow Invalidation (Capability Changes) -- Proactive Gap Detection

If a capability referenced in the workflow disappears or its schema changes:

1. **Detection**: Workflow Compiler detects schema mismatch during rehydration (or proactively when tool registry updates)
2. **Gap Analysis**: Identify what new information is needed for the updated tool schema
3. **Proactive Memory**: Store the gap in proactive gap detection memory (K0 P06 pattern)
4. **User Engagement**: When user is free (not mid-conversation, not busy), Concierge proactively asks:
   - "Hey, the restaurant booking tool updated and now requires a preferred cuisine. For your weekly Mom brunch workflow -- what cuisine should I use?"
   - Always with **justification**: explain WHY we're asking, WHAT changed
5. **Re-plan if needed**: If the gap is too large (tool removed entirely), trigger re-planning with original intent

This follows the same proactive gap detection pattern as K0 P06 curiosity flow -- gaps are stored, questions are formulated when the user is available, and justification is always provided.

---

## 10. Delta Bus: How Non-Writers Report State Changes

Since only Concierge writes to SessionState, all other components emit deltas:

```
Sub-agent completes work --> emits state delta to DeltaBus
Planner makes progress   --> emits planning delta to DeltaBus
Orchestrator aggregates  --> emits orchestration delta to DeltaBus

DeltaBus --> Aggregation Window (500ms batching, LWW merge)
         --> Concierge FSM receives aggregated batch
         --> Concierge (Single Writer) applies to SessionState via MutationGuard
```

### Delta Types

| Source | Delta Type | Example |
|---|---|---|
| Spawned Agent | `k1.agent.{id}.delta.v1` | `{type: "fact_discovered", data: {fact: "Mom prefers Italian"}}` |
| Planner | `k1.planner.delta.v1` | `{type: "plan_stage_complete", stage: 2}` |
| Orchestrator | `k1.orchestration.delta.v1` | `{type: "step_complete", step_id: "s1", result_summary: "..."}` |
| Curiosity Agent | `k1.curiosity.delta.v1` | `{type: "gap_question_formulated", question: "..."}` |

---

## 11. Circuit Breaker Protection

Each component boundary is protected by circuit breakers:

| Circuit Breaker | Timeout | Threshold | Fallback |
|---|---|---|---|
| Model Gateway | 30s | 3/min | Cached/template response |
| Orchestrator | 60s | 2/min | Degrade to LOW tier |
| Planner | 45s | 2/min | Skip planning, direct execution |
| Capability Fabric | 30s | 5/min | Capability unavailable |
| MCP Connector | 10s | 3/min | Tool offline |
| SessionState | 100ms | 10/min | Stale read |
| SSE Connection | 5s reconnect | 3/min | Polling mode |

---

## 12. Summary: End-to-End Flow (HIGH Tier Example)

```
User: "Plan a birthday party for Mom next Saturday -- book a restaurant,
       order a cake, and send invitations to family"

1. LISTENING -> user_input -> ACKING
2. UltraBERT (22ms):
   - Intent: plan_event (HIGH complexity)
   - Domains: [EVENTS, FOOD, SOCIAL]
   - Entities: Mom (PERSON), next Saturday (DATE)
   - Safety: GREEN
   Phase 1 writes: control.intents, control.domains, beliefs_active.entities, temporal_context

3. Complexity Classifier: HIGH (multi-domain + multi-step)
4. DISPATCHING:
   - Creates TaskEnvelope{intent, context, tier=HIGH}
   - Sends to Orchestrator Mailbox
   - LLM preliminary ack (~200 tokens): "I'll plan that birthday party! Let me work on it..."
   - LLM also calls cognitive tools: update_scoreboard(QUD="birthday party planning")
   Phase 2 writes: scoreboard

5. COMPANIONING: Sends ack to user via OUTPUT_CHANNEL

6. Orchestrator receives TaskEnvelope, tier=HIGH:
   - Creates PlanRequest{intent, constraints, context}
   - Sends to Planner Mailbox

7. Planner Stage 1 (SKETCH):
   - LLM calls discover_capabilities(domain="restaurant")
   - LLM calls discover_capabilities(domain="cake_delivery")
   - LLM calls discover_capabilities(domain="messaging")
   - LLM calls recall_for_planning("Mom birthday preferences food")
   - Produces rough plan

8. Planner Stage 2 (EXPAND):
   - LLM calls find_relevant_prompts(intent="restaurant_booking")
   - Maps each step to capability + prompt + params
   - Builds dependency graph: s4 depends on [s1, s3]

9. Planner Stage 3 (VALIDATE):
   - Confirms all capabilities exist
   - DAG is acyclic
   - No safety violations

10. Planner Stage 4 (COMMIT):
    - Persists CommittedPlan to K0 WAL
    - Returns CommittedPlan to Orchestrator

11. Orchestrator executes DAG:
    - Parallel: s1 (restaurant), s2 (cake), s3 (contacts) --> all to Fabric
    - Fabric spawns agents/tools for each
    - Progress deltas to DeltaBus -> Concierge PROGRESSING -> OUTPUT_CHANNEL
    - s1 + s3 complete -> s4 (invitations) starts
    - All steps complete -> aggregate results

12. Results to Concierge COMPANIONING -> TOOL_RESULT_BUFFER

13. DELIVERING:
    - LLM call with all tool_results (~8K tokens)
    - Generates final response with details
    - Calls cognitive tools: update_beliefs(party booked), update_narrative(birthday_party thread)
    - Response to OUTPUT_CHANNEL
    Phase 2 writes: beliefs_active, narrative_active

14. User: "Actually, do this check-in every week"
    - LISTENING -> ACKING -> classify as save_workflow
    - CommittedPlan saved to Workflow Registry
    - TriggerSpec: cron "0 8 * * SAT"
    - Future runs: Scheduler -> Compiler -> Orchestrator -> Fabric (no Planner)
```

---

## 13. Resolved Decisions (From Open Questions)

### Q1: MEDIUM Tier Planning -- RESOLVED: No Planning Needed

MEDIUM tasks require 1-2 specialized agents/tools, not a full plan. Concierge already has `invoke_capability()`, `spawn_via_fabric()`, and `discover_capabilities()` tools. For MEDIUM, Concierge figures out WHAT to do (it has read tools) and sends a detailed TaskEnvelope to Orchestrator. Orchestrator coordinates 1-2 Fabric calls, returns results via DeltaBus. No Planner involvement.

### Q2: Agent Context Injection -- RESOLVED: Tool/Prompt Definitions Declare Requirements

Every tool and prompt definition in the registry explicitly declares what inputs it requires:

```yaml
# Example: restaurant_booking tool definition
tool:
  name: tool.execute.restaurant_booking
  required_inputs:
    - date: "DATE -- when to book"
    - party_size: "NUMBER -- how many guests"
    - cuisine: "STRING -- preferred cuisine type"
    - location: "STRING -- city or area"
  optional_inputs:
    - budget_range: "STRING -- price range"
  required_context:
    - beliefs_active.entities  # for names, relationships
    - temporal_context          # for resolved dates
```

The Planner reads SessionState via `query_planning_context()` and matches context to tool requirements. If required context is missing (e.g., party_size unknown), this is a **gap**. Gaps flow back through the existing gap detection design:

- Planner fires HIL: Requirement Clarification
- Question routes to user via OUTPUT_CHANNEL
- User answer returns to Planner Stage 1
- Planner retries with complete context

Fabric's Context Builder also reads SessionState when spawning agents -- it injects the sections declared in the tool/prompt `required_context` field, not everything.

### Q3: Plan Step Failure -- RESOLVED: 2 Retries Then Graceful Failure

When a plan step fails:

1. **Retry 1**: Same capability, same params (transient failure)
2. **Retry 2**: Same capability, same params (confirm persistent)
3. **Graceful failure**:
   - Mark step as FAILED
   - All dependent steps are CANCELLED (s4 cancelled if s1 failed)
   - Independent steps continue (s2, s3 continue even if s1 failed)
   - Orchestrator aggregates partial results + failure info
   - Concierge DELIVERING: LLM generates polite update to user
     - "I was able to order the cake and get the family contacts, but the restaurant booking didn't go through. Would you like me to try a different restaurant service, or would you prefer to book manually?"
   - No automatic re-planning. User decides next action.

### Q4: Workflow Versioning -- RESOLVED: Proactive Gap Detection

When a tool schema changes:

- Gap stored in proactive gap detection memory (K0 P06 pattern)
- Concierge asks user when free, with justification for why we're asking
- If gap is small (new optional field): auto-fill with defaults, notify user
- If gap is large (tool removed): trigger re-planning with original intent

See Section 9 (Workflow Invalidation) for full flow.

### Q5: Planner Tool Schemas -- DEFERRED

Exact input/output schemas for `discover_capabilities()`, `find_relevant_prompts()`, `query_planning_context()`, `recall_for_planning()` to be designed during implementation phase (GATE 2: Contract Discovery).

### Q6: Contract-Net Protocol -- RESOLVED: Superseded by Fabric

ADR-0006's Contract-Net Protocol (Task Announcement -> Proposal Bidding -> Multi-Criteria Scoring) is **no longer needed**. Fabric's Provider Resolution Engine handles all provider selection. ADR-0006 should be revised to describe Orchestrator purely as a blind DAG executor.

See Section 6 (3-Phase Orchestration -- SUPERSEDED) for details.

---

## 14. Fabric as Intelligent Retrieval Layer (New Decision)

This is a critical architectural insight: Fabric is NOT a dumb registry lookup. It's an **intelligent retrieval layer** that serves the Planner.

### The Scale Problem

As the system grows:

- 100,000+ tools (MCP servers, WASM tools, Bridge operations)
- 100,000+ agents (YAML templates, dynamic patterns)
- 10,000+ prompts (per-domain, per-intent, versioned)

You cannot pass all of this into a Planner LLM prompt. Token budgets explode. Irrelevant noise drowns relevant capabilities.

### The Solution: Semantic Top-K Retrieval

When Planner calls `discover_capabilities(domain="restaurant", intent="book_reservation")`:

1. Fabric receives the query
2. Fabric searches Tool Registry + Agent Registry using **semantic similarity** (embeddings)
3. Filters by: domain match, safety band access, user permissions, current availability
4. Ranks by: relevance score, QoS rating, historical success rate, cost
5. Returns **top 10** most relevant capabilities with their schemas

Same for `find_relevant_prompts()` -- semantic search across Prompt Registry, return top-K.

### What This Means for Each Component

| Component | Sees | How |
|---|---|---|
| Planner | Top-K relevant capabilities + prompts | Via Fabric retrieval tools |
| Orchestrator | Exact capability names from CommittedPlan | From Planner's plan |
| Fabric (execution) | Exact capability name to invoke | From CapabilityRequest |
| Fabric (retrieval) | Full registry (100K+ items) | Semantic search engine |

Fabric is the ONLY component that sees the full catalog. Everyone else sees filtered, relevant subsets.

---

## 15. Resolved Questions (Round 2)

### Q1: Fabric Retrieval Ranking -- RESOLVED: Hard Rules First, Semantic Ranking Second

Semantic Top-K retrieval only works if the underlying catalog is well-structured. Before any ranking algorithm, every tool, agent, and prompt MUST have a **standard contract** defining:

**Tool Contract (Required Fields)**:

```yaml
# Standard Tool Contract -- applies to ALL tools in ALL domains
# (FamilyOS, SchoolOS, BankOS, any business domain)
tool_contract:
  # Identity
  name: "tool.execute.restaurant_booking"        # canonical capability name
  version: "2.1.0"                                # semver
  domain: ["FOOD", "EVENTS"]                      # domain tags (multi-label)

  # Description (used for semantic search)
  description: "Books a restaurant reservation"    # human-readable, 1 sentence
  capabilities:                                    # what this tool CAN do
    - "reserve_table"
    - "check_availability"
    - "cancel_reservation"
  limitations:                                     # what this tool CANNOT do
    - "does not handle payment"
    - "max 20 guests per reservation"

  # Requirements (what it needs to perform)
  required_inputs:
    - name: "date"
      type: "DATE"
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

  # Context requirements (SessionState sections needed)
  required_context:
    - "beliefs_active.entities"     # for name resolution
    - "temporal_context"            # for date resolution

  # Output schema
  output:
    type: "object"
    properties:
      venue_name: { type: "string" }
      address: { type: "string" }
      confirmation_id: { type: "string" }
      date: { type: "string", format: "date" }
      party_size: { type: "number" }

  # Provider metadata
  provider_type: "MCP"               # MCP | WASM | BRIDGE | AGENT
  provider_id: "opentable_mcp"       # which MCP server / agent template

  # Policy metadata
  safety_band_min: "GREEN"           # minimum safety band required
  cost_per_call: 0.001               # estimated cost in USD
  avg_latency_ms: 2000               # average execution time
  availability: "ONLINE"             # ONLINE | DEGRADED | OFFLINE

  # Audit
  registered_at: "2026-01-15T10:00:00Z"
  last_updated: "2026-02-01T14:30:00Z"
  success_rate_30d: 0.97             # rolling 30-day success rate
```

**Agent Contract (Required Fields)**:

```yaml
agent_contract:
  name: "agent.execute.invitation_sender"
  version: "1.0.0"
  domain: ["SOCIAL", "COMMUNICATION"]

  description: "Drafts and sends personalized invitations"
  capabilities:
    - "draft_invitation"
    - "personalize_per_recipient"
    - "send_via_messaging"
  limitations:
    - "text-only invitations (no image generation)"
    - "max 50 recipients per batch"

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

  required_context:
    - "beliefs_active.entities"
    - "persona"                     # for tone matching

  # Agent-specific
  prompt_template: "invitation_drafter_v1"     # default prompt
  tools_granted:                                # what tools this agent can use
    - "tool.execute.send_message"
    - "tool.read.contact_lookup"
  llm_budget_tokens: 2000                       # max tokens per invocation

  provider_type: "AGENT"
  template_file: "invitation_sender.yaml"
  safety_band_min: "GREEN"
  avg_latency_ms: 5000
```

**Prompt Contract (Required Fields)**:

```yaml
prompt_contract:
  name: "invitation_drafter_v1"
  version: "1.0.0"
  domain: ["SOCIAL", "COMMUNICATION"]

  description: "Drafts personalized event invitations"
  intent_match: ["send_invitation", "invite_people", "party_planning"]

  # Template variables (must be filled before use)
  variables:
    - name: "event_type"
      type: "STRING"
      required: true
    - name: "guest_name"
      type: "STRING"
      required: true
    - name: "event_details"
      type: "STRING"
      required: true
    - name: "tone"
      type: "STRING"
      required: false
      default: "casual"

  # What this prompt produces
  output_format: "TEXT"              # TEXT | JSON | STRUCTURED
  max_tokens: 500                    # recommended token budget

  # Compatibility
  compatible_agents: ["agent.execute.invitation_sender"]
  compatible_tools: []               # if prompt is used directly with a tool
```

**Ranking Algorithm (Built on Contracts)**:

Once contracts are solid, retrieval ranking uses:

1. **Hard filters** (eliminate non-candidates):
   - Safety band access (user must have required band)
   - Availability != OFFLINE
   - Required inputs satisfiable (do we have the data?)

2. **Soft ranking** (score remaining candidates):
   - Semantic similarity: embedding cosine between query and `description + capabilities` (weight: 0.4)
   - Domain match: overlap between query domain and tool `domain[]` tags (weight: 0.3)
   - Historical success: `success_rate_30d` (weight: 0.15)
   - Cost/latency: lower cost + faster = higher rank (weight: 0.15)

3. **Return Top-K** (K=10 default, configurable per query)

### Q2: Planner Tool Schemas -- NEEDS DESIGN SESSION

Not deferred anymore. We need to design exact schemas for all 4 Planner discovery tools. This should be a dedicated discussion covering:

- Input/output JSON schemas for `discover_capabilities()`, `find_relevant_prompts()`, `query_planning_context()`, `recall_for_planning()`
- How Planner calls map to Fabric's retrieval API
- Token budgets per tool response

### Q3: TaskEnvelope & All Schemas -- NEEDS DESIGN: Domain-Agnostic

All schemas (TaskEnvelope, PlanRequest, CommittedPlan, CapabilityRequest, CapabilityResult, WorkflowSpec, Tool/Agent/Prompt Contracts) must be **domain-agnostic**. They must work for:

- FamilyOS (families, personal tasks, home automation)
- SchoolOS (education, assignments, grades, schedules)
- BankOS (finance, transactions, compliance, audit)
- HealthOS (medical records, appointments, prescriptions)
- Any future business domain

**Design principle**: Schemas define STRUCTURE, not domain content. Domain specifics live in:

- Tool contracts (per-domain tool definitions)
- Prompt templates (per-domain prompts)
- Agent templates (per-domain agent YAML)
- Capability Registry entries (per-domain capabilities)

The core pipeline (Concierge -> Orchestrator -> Planner -> Fabric) is domain-blind. It works the same whether booking a restaurant or approving a bank loan.

### Q4: Spawned Agent Tool Access -- RESOLVED: Planner-Specified + SessionState Read

When Fabric spawns an agent for a plan step, the agent gets:

1. **Only the tools specified by Planner** in the `CommittedPlan` step (least-privilege):

   ```yaml
   step:
     id: s4
     capability: "agent.execute.invitation_sender"
     tools_granted:                    # Planner specifies exactly which tools
       - "tool.execute.send_message"
       - "tool.read.contact_lookup"
   ```

2. **SessionState read tools** (always granted -- agents need context):
   - `read_session_state(sections[])` -- read specific SessionState sections
   - Which sections? Declared in the agent's `required_context` field from its contract

3. **Prompt injection**: The agent's context window includes:
   - Its prompt template (from `prompt_template` field)
   - Relevant SessionState sections (from `required_context`)
   - Step parameters (from `params`)
   - The Fabric Context Builder assembles this, applies token budget, injects into the agent's first LLM call

**No access to**: cognitive tools (those are Concierge-only), other agent's tools, tools not in `tools_granted`.

### Q5: Workflow Edit UX -- RESOLVED: Replan Only (V1)

**V1**: Users can only re-plan from scratch. If a workflow needs modification:

- User says "change the brunch workflow to use a different restaurant"
- Concierge sends original intent + modification to Planner
- Planner creates new CommittedPlan
- New WorkflowSpec replaces old one (version bump)

**V2** (future): Individual step editing, drag-and-drop workflow builder, visual DAG editor.

### Q6: Cross-Workflow Triggers -- RESOLVED: Yes, Design With It In Mind

Workflows CAN trigger other workflows. Design the system with this capability from V1:

```yaml
# A step in a workflow can invoke another workflow
step:
  id: s3
  capability: "workflow.run.weekly_grocery_list"    # triggers another workflow
  params:
    trigger_reason: "birthday_party_prep"
    override_params:
      extra_items: ["birthday cake ingredients"]
  deps: [s1]
```

**V1 implementation**:

- Simple: A workflow step with `capability: "workflow.run.*"` triggers the referenced workflow via Fabric
- Fabric resolves `workflow.run.weekly_grocery_list` -> WorkflowProvider -> rehydrate + execute
- Results flow back to the parent DAG step like any other CapabilityResult
- No circular triggers allowed (validated in Planner Stage 3)

**Guard rails**:

- Max workflow depth: 3 (workflow -> workflow -> workflow, no deeper)
- Cycle detection in Planner Stage 3 VALIDATE
- Each sub-workflow gets its own Run Manifest for audit trail

---

## 16. Design Sessions Needed (Next Steps)

The following items need dedicated design discussions:

| # | Topic | What to Design | Priority |
| --- | --- | --- | --- |
| 1 | **Planner Tool Schemas** | Exact JSON schemas for all 4 discovery tools | HIGH -- blocks implementation |
| 2 | **Core Envelope Schemas** | TaskEnvelope, PlanRequest, CommittedPlan, CapabilityRequest, CapabilityResult (domain-agnostic) | HIGH -- blocks implementation |
| 3 | **Fabric Retrieval API** | How Planner tool calls map to Fabric internals. Exact Top-K API. | HIGH -- coupled with #1 |
| 4 | **Tool/Agent/Prompt Registry Schema** | Finalize the standard contract format from Q1 above | MEDIUM -- draft exists above |
| 5 | **WorkflowSpec Schema** | Finalize with cross-workflow trigger support + version management | MEDIUM |
| 6 | **Agent Prompt Injection** | Exact Context Builder assembly: what goes where in the agent's prompt window | MEDIUM |
