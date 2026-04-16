# ModelHub — Cross-Reference with K1 Actors

> Generated: 2026-04-14 · Scope: How every K1 component connects to ModelHub

---

## 1. Architecture Diagram Context

Source: `architecture_diagrams/k1/k1_cognitive_architecture_skeleton.mmd`

The **LLM Call Matrix** (lines 3–50) lists **18 consumers** with dedicated token budgets. ModelHub is the **single funnel** for ALL LLM calls — no actor calls an LLM API directly.

```text
MODEL_HUB subgraph (lines 706-726):
  RequestRouter + CapabilityRouter
  ResponseCache
  CostTracker + AuditLogger
```

---

## 2. Consumer × ModelHub Integration Map

### 2.1 Concierge (Front + Back Actors)

| Aspect | Detail |
| --- | --- |
| **Interface** | `ILLMPort` → `ModelHubPOCBridge` (wrapping `GeminiConciergeAdapter`) |
| **Capabilities Used** | `CHAT`, `STRUCTURED`, `TOOL_CALL`, `REASON` |
| **Token Budget** | Front: 4K in / 2K out; Back: 8K in / 4K out (architecture diagram) |
| **Call Pattern** | Front: user-facing streaming; Back: intent analysis, plan delegation |
| **Priority** | Front: `INTERACTIVE`; Back: `INTERACTIVE` |
| **Wiring (POC)** | `bootstrap.py` → `ModelHubPOCBridge(GeminiConciergeAdapter)` injected into Concierge |
| **Wiring (Production)** | `BusEnvelopeDeserializer` → `k1.model_hub.execute.v1` → `IModelHubPort.execute()` |
| **Gap** | POC bridge bypasses full ModelHub pipeline (no budget/cache/CB/RL). Production path via bus not yet wired. |

### 2.2 Fabric (Agent Factory + L3 Agents)

| Aspect | Detail |
| --- | --- |
| **Interface** | `model_hub.create_handle()` → per-agent LLM handle |
| **Architecture Diagram** | `fabric.mmd`: "Agent Factory grants LLM access via model_hub.create_handle" |
| **Capabilities Used** | `CHAT`, `TOOL_CALL`, `STRUCTURED`, `REASON`, `VISION` (per agent type) |
| **Token Budget** | Per-agent limits set by Agent Factory (not global budget) |
| **Call Pattern** | Agent executes tool calls via LLM → model hub routes to provider |
| **Priority** | Varies by agent complexity (simple=`INTERACTIVE`, complex=`BACKGROUND`) |
| **Integration Point** | `LLMRequestBusAdapter` → facade delegating to `IModelHubPort` |
| **Wiring** | Agent Factory injects `LLMRequestBusAdapter` into spawned agents |

### 2.3 Planner (4-Stage Pipeline)

| Aspect | Detail |
| --- | --- |
| **Interface** | LLM calls for stages 1–3 of 4-stage pipeline |
| **Architecture Diagram** | Planner calls LLM for: (1) decomposition, (2) dependency analysis, (3) resource estimation |
| **Capabilities Used** | `STRUCTURED` (plan JSON), `REASON` (complex decomposition) |
| **Token Budget** | 8K in / 4K out (architecture diagram) |
| **Priority** | `INTERACTIVE` (synchronous planning path) |
| **Wiring** | Planner receives `ILLMPort` → delegates to ModelHub |

### 2.4 Orchestrator

| Aspect | Detail |
| --- | --- |
| **Interface** | Indirect — delegates LLM calls to Planner/Concierge/Fabric |
| **Architecture Diagram** | Orchestrator is the FSM controller; does NOT call LLM directly |
| **Capabilities Used** | None directly (orchestrates actors that call ModelHub) |
| **Wiring** | No direct ModelHub dependency |

### 2.5 Memory Writer

| Aspect | Detail |
| --- | --- |
| **Interface** | `LLMGatewayAdapter` for Model Hub route |
| **Architecture Diagram** | `memory_writer.mmd`: "LLMGatewayAdapter for Model Hub route" |
| **Capabilities Used** | `CHAT` (summarization), `EMBED` (vector embeddings) |
| **Token Budget** | Background summarization: 4K in / 1K out |
| **Priority** | `BACKGROUND` (non-blocking, async) |
| **Call Pattern** | Batch summarization of episodic memory → semantic memory |
| **Wiring** | `LLMGatewayAdapter` wraps `IModelHubPort` |

### 2.6 Supervision / Arbiter

| Aspect | Detail |
| --- | --- |
| **Architecture Diagram** | Arbiter uses LLM for safety/policy evaluation |
| **Capabilities Used** | `MODERATE`, `STRUCTURED` (safety verdicts) |
| **Priority** | `REALTIME` (blocks pipeline) |
| **Token Budget** | 2K in / 1K out (architecture diagram) |

### 2.7 Learning / Experience Layer

| Aspect | Detail |
| --- | --- |
| **Architecture Diagram** | Experience layer extracts lessons from interactions |
| **Capabilities Used** | `CHAT` (reflection), `EMBED` (lesson vectors) |
| **Priority** | `BACKGROUND` |

---

## 3. Adapter Integration Matrix

How ModelHub adapters connect to external K1 systems:

| Adapter | External System | Direction | Contract |
| --- | --- | --- | --- |
| `BusEnvelopeDeserializer` | **K1 Event Bus** | IN (subscribe) + OUT (publish) | `k1.model_hub.execute.v1` → `k1.model_hub.execute.response.v1` |
| `SessionStateProdAdapter` | **SessionState** | IN (read) | `IStateReadPort.read(sections)` → `StateSnapshot` |
| `SessionStateReadAdapter` | *(test stub)* | IN (read) | Same interface, in-memory dict |
| `EventBusAdapter` | **Internal events** | OUT | 11 topics (§2.2 of doc 22) |
| `LLMRequestBusAdapter` | **Fabric agents** | IN (facade) | Facade delegating to `IModelHubPort.execute()` |
| `ConfigAdapter` | **Config system** | IN (read) | `IConfigPort.get(key)` + `watch()` |
| `CredentialStoreAdapter` | **Env vars / Vault** | IN (read) | `MH_KEY_<PROVIDER_ID>` env lookup |
| `PrometheusAdapter` | **Metrics system** | OUT | 12 named metrics |
| `HealthReportAdapter` | **Health system** | OUT | Worst-of aggregation |

---

## 4. Data Flow Diagrams

### 4.1 Concierge → ModelHub (POC Path)

```text
User Input
  → ConciergeActor.front_actor()
    → ILLMPort.generate()
      → ModelHubPOCBridge.generate()
        → GeminiConciergeAdapter.generate()
          → Google Gemini API (direct, bypasses ModelHub pipeline)
```

### 4.2 Concierge → ModelHub (Production Path — NOT YET WIRED)

```text
User Input
  → ConciergeActor.front_actor()
    → ILLMPort.generate()
      → Bus publish k1.model_hub.execute.v1
        → BusEnvelopeDeserializer._on_message()
          → IModelHubPort.execute(HubRequest)
            → 9-step pipeline (budget → capability → model → cache → dispatch)
              → Plugin.execute() → LLM API
          → Bus publish k1.model_hub.execute.response.v1
```

### 4.3 Fabric Agent → ModelHub

```text
Agent Factory spawns agent
  → Injects LLMRequestBusAdapter as ILLMPort
    → Agent calls tool via LLM
      → LLMRequestBusAdapter.execute()
        → IModelHubPort.execute(HubRequest)
          → 9-step pipeline → Plugin → LLM API
```

### 4.4 Memory Writer → ModelHub

```text
Episodic buffer trigger
  → MemoryWriter.summarize()
    → LLMGatewayAdapter.generate()
      → IModelHubPort.execute(HubRequest{capability=CHAT, priority=BACKGROUND})
        → 9-step pipeline → Plugin → LLM API
```

---

## 5. Bus Topic Dependencies

### 5.1 Topics ModelHub PRODUCES (11)

| Topic | Consumer(s) |
| --- | --- |
| `k1.model_hub.request.received.v1` | Telemetry, Supervision |
| `k1.model_hub.request.routed.v1` | Telemetry |
| `k1.model_hub.response.complete.v1` | Telemetry, Cost dashboards |
| `k1.model_hub.cache.hit.v1` | Telemetry |
| `k1.model_hub.provider.failure.v1` | Supervision, Alerts |
| `k1.model_hub.fallback.triggered.v1` | Supervision, Alerts |
| `k1.model_hub.circuit.state.v1` | Supervision, Health dashboard |
| `k1.model_hub.budget.alert.v1` | Supervision, Alerts |
| `k1.model_hub.provider.health.v1` | Health dashboard |
| `k1.model_hub.provider.registered.v1` | Capability discovery |
| `k1.model_hub.capability.available.v1` | Capability discovery |

### 5.2 Topics ModelHub CONSUMES (1)

| Topic | Publisher(s) | Effect |
| --- | --- | --- |
| `k1.model_hub.execute.v1` | Any actor via bus | `BusEnvelopeDeserializer` → `IModelHubPort.execute()` |

---

## 6. SessionState Read Dependency

ModelHub reads (but NEVER writes) SessionState via `IStateReadPort`:

| Section Read | Used By | Purpose |
| --- | --- | --- |
| `affective_state` | `ModelSelector` | Emotion-aware model selection (calmer → cheaper model) |
| `cognitive_load` | `ModelSelector` | Load-aware routing (high load → faster model) |
| `user_preferences` | `ModelSelector` | Preferred provider/model matching |
| `conversation_context` | `NormalizationLayer` | Context injection for system prompts |

**Invariant MH-01**: `IStateReadPort` has NO write methods. This is a hard architectural boundary.

---

## 7. Cross-Reference with Prior Doc Series

| Doc | Component | Relationship to ModelHub |
| --- | --- | --- |
| 14–15 | **Orchestrator** | No direct dependency — orchestrates actors that call ModelHub |
| 15_planner | **Planner** | Calls ModelHub for stages 1–3 of 4-stage planning pipeline |
| 16–17 | **Fabric** | Agent Factory injects `LLMRequestBusAdapter`; Fabric subgraph references MODEL_HUB |
| 18–19 | **SessionState** | ModelHub reads via `IStateReadPort` (MH-01 read-only) |
| 20–21 | **Concierge** | Front/Back actors call via `ILLMPort` → `ModelHubPOCBridge` (POC) |

---

## 8. Kernel Bootstrap Wiring

### 8.1 Current Wiring (POC — `k1/kernel/bootstrap.py`)

```python
# Test mode
model_hub = TestModelHubBridge()

# Production mode
model_hub = ModelHubPOCBridge(GeminiConciergeAdapter())
```

Both inject into Concierge as `ILLMPort`. The full `ModelHubFactory` pipeline is NOT used in kernel bootstrap.

### 8.2 REPL Wiring (`k1/kernel/chat_repl.py`)

```python
# --model-hub flag activates full pipeline
hub = ModelHubFactory.create_standalone(plugins=[GooglePlugin])
```

This is the ONLY path that uses the full 9-step pipeline. Available as a developer flag.

### 8.3 Production Target Wiring (NOT YET IMPLEMENTED)

```python
# Target state
hub = ModelHubFactory.create_standalone(
    config=ModelHubConfig(...),
    plugins=[GooglePlugin, AnthropicPlugin, OpenAIPlugin]
)
# Wire BusEnvelopeDeserializer to k1.bus
# All actors call via bus topic, not direct injection
```

---

## 9. Dual-Path Gap Analysis

| Aspect | POC Path | Production Path |
| --- | --- | --- |
| **Entry** | Direct `ILLMPort` injection | Bus topic `k1.model_hub.execute.v1` |
| **Budget enforcement** | ❌ Bypassed | ✅ Step 2 |
| **Caching** | ❌ Bypassed | ✅ Step 6 (5min TTL) |
| **Circuit breakers** | ❌ Bypassed | ✅ Step 8 |
| **Rate limiting** | ❌ Bypassed | ✅ Step 8 |
| **Fallback chain** | ❌ Single provider | ✅ Top 3 providers |
| **Audit logging** | ❌ Bypassed | ✅ Step 9 |
| **Multi-provider** | ❌ Gemini only | ✅ 5 providers |
| **Metrics** | ❌ None | ✅ 12 metrics |
| **Cost tracking** | ❌ None | ✅ Per-request |

**Recommendation**: Migrate kernel bootstrap to `ModelHubFactory.create_standalone()` to gain all 9-step pipeline protections.

---

## 10. Architecture Diagram LLM Call Matrix (18 Consumers)

From `k1_cognitive_architecture_skeleton.mmd` (lines 3–50):

| # | Consumer | Token Budget (in/out) | Capability | Priority |
| --- | --- | --- | --- | --- |
| 1 | Concierge Front | 4K / 2K | CHAT, STRUCTURED | INTERACTIVE |
| 2 | Concierge Back | 8K / 4K | CHAT, TOOL_CALL, REASON | INTERACTIVE |
| 3 | Planner Stage 1 | 8K / 4K | STRUCTURED | INTERACTIVE |
| 4 | Planner Stage 2 | 4K / 2K | STRUCTURED | INTERACTIVE |
| 5 | Planner Stage 3 | 4K / 2K | STRUCTURED | INTERACTIVE |
| 6 | Fabric Agent (simple) | 2K / 1K | CHAT, TOOL_CALL | INTERACTIVE |
| 7 | Fabric Agent (complex) | 8K / 4K | CHAT, TOOL_CALL, REASON | BACKGROUND |
| 8 | Arbiter (safety) | 2K / 1K | MODERATE, STRUCTURED | REALTIME |
| 9 | Memory Writer (summarize) | 4K / 1K | CHAT | BACKGROUND |
| 10 | Memory Writer (embed) | 2K / — | EMBED | BACKGROUND |
| 11 | Experience Layer | 4K / 2K | CHAT, EMBED | BACKGROUND |
| 12 | HITL Formatter | 2K / 1K | CHAT | INTERACTIVE |
| 13 | Weave (output) | 4K / 2K | CHAT, STRUCTURED | INTERACTIVE |
| 14 | IFL Analyzer | 4K / 2K | STRUCTURED | BACKGROUND |
| 15 | Complexity Router | 2K / 1K | STRUCTURED | REALTIME |
| 16 | Phase1 Classifier | 1K / 0.5K | STRUCTURED | REALTIME |
| 17 | Prompt Optimizer | 4K / 2K | CHAT | BACKGROUND |
| 18 | Feedback Loop | 2K / 1K | STRUCTURED | BACKGROUND |

> Note: Budget values are approximate from architecture diagram annotations. Actual enforcement is via `BudgetEnforcer` ($5/day global) + per-request `RequestConstraints.cost_limit`.

---

## 11. Summary

ModelHub is the **central LLM gateway** for the entire K1 cognitive architecture. It funnels all 18 consumers through a single 9-step pipeline with budget enforcement, capability routing, model selection, caching, circuit breakers, rate limiting, fallback chains, and audit logging.

**Current state**: POC bridge bypasses the full pipeline. Only `chat_repl.py --model-hub` exercises the production path.

**Migration priority**: Wire `ModelHubFactory.create_standalone()` into `k1.kernel.bootstrap` to replace `ModelHubPOCBridge`. This single change activates all 18 invariants for all actors.
