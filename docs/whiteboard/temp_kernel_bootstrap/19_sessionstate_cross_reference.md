# SessionState ↔ Orchestrator ↔ Planner ↔ Fabric — Cross-Reference & Gap Analysis

> Generated: 2026-04-12 · Companion docs: `18_sessionstate_api_mapping.md`, `15_orchestrator_api_mapping.md`, `15_planner_api_mapping.md`, `16_fabric_api_mapping.md`, `17_fabric_orchestrator_planner_cross_reference.md`

---

## 1. SessionState Consumer Topology

SessionState is the **shared cognitive context** for the K1 kernel. Every major component reads from it; only Concierge (via DirectWriterAdapter) writes to it.

```text
                                ┌────────────────────────┐
                     writes     │  SessionStateManager    │
              ┌────────────────►│  (15 sections, 3 tiers) │
              │                 │  HOT 52KB │ WARM 52KB   │
              │                 │  LOCAL COLD (SQLite)     │
              │                 └──┬──┬──┬──┬──┬──┬───────┘
              │                    │  │  │  │  │  │
              │         reads      │  │  │  │  │  │  reads
              │       ┌────────────┘  │  │  │  │  └──────────────┐
              │       │    ┌──────────┘  │  │  └────────┐        │
              │       │    │    ┌────────┘  └────┐      │        │
              │       ▼    ▼    ▼               ▼      ▼        ▼
           Concierge  Fabric  Planner     Orchestrator  MemWriter  ModelHub
           (SSMState  (SSRead  (Planner   (MockState    (Session   (MHState
            Adapter)   Adapter) Adapter)   Adapter ⚠)   ReadAdapt)  ReadAdapt)
```

### 1.1 Wiring Summary (from kernel/service.py)

| Consumer | Wired At | Adapter Class | SSM Reference | Status |
| --- | --- | --- | --- | --- |
| Fabric | P3 | `SessionStateReaderAdapter(ssm, session_id)` | Direct SSM | **LIVE** |
| Concierge | P4 | `SSMStateAdapter(ssm)` | Direct SSM | **LIVE** |
| MemoryWriter | P5 | `SessionReadAdapter(manager=ssm)` | Direct SSM | **LIVE** |
| Planner | P6 | `PlannerStateAdapter(reader=...)` | ⚠ `reader=None` placeholder in some paths | **PARTIAL** |
| Orchestrator | P1 | `MockStateReadAdapter()` | ❌ No SSM reference | **STUB** |
| ModelHub | P3 | `MHStateReadAdapter(...)` | Direct SSM | **LIVE** |

---

## 2. Interface Contracts: How Each Component Accesses SessionState

### 2.1 Concierge → SessionState (SSMStateAdapter — PRIMARY WRITER)

Concierge is the **sole writer** to SessionState. Every user turn, the Turn Engine mutates multiple sections.

| Operation | Section(s) | Data Flow | Frequency |
| --- | --- | --- | --- |
| `mutate("control", "set", {...})` | `control` | Set intent, domain, safety_band, flow_state, agent_leases | Every turn |
| `mutate("history_active", "add_turn", turn)` | `history_active` | Append user + assistant turn (max 10) | Every turn |
| `mutate("beliefs_active", "add_fact", fact)` | `beliefs_active` | Append SVO fact from NLU extraction | Per extracted fact |
| `mutate("scoreboard", "push_question", q)` | `scoreboard` | Push QUD, update salience, manage topics | Per discourse update |
| `mutate("affective_now", "set", emotion)` | `affective_now` | Russell circumplex (valence, arousal) + trajectory | Every turn |
| `mutate("narrative_active", "create_thread", t)` | `narrative_active` | Thread FSM (ACTIVE/PAUSED/RESOLVED) | On topic shift |
| `mutate("task_state", "set", task)` | `task_state` | Active tasks, HIL recovery, progress | On task creation |
| `mutate("task_artifacts", "append", artifact)` | `task_artifacts` | Task outputs, presented-at tracking | On task completion |
| `mutate("clarifications", "push_question", q)` | `clarifications` | Pending clarification requests | On ambiguity |
| `mutate("meta", "update", {...})` | `meta` | Session identity, lifecycle transitions | Session events |
| `mutate("persona", "set", profile)` | `persona` | Personality, prosody, vocabulary | Session start / rare |
| `mutate("telemetry", "record_turn", metrics)` | `telemetry` | Token/cost/latency per turn | Every turn |

**Reads:** Concierge reads ALL sections (HOT + WARM) for FSM decisions and LLM prompt assembly.

### 2.2 Fabric → SessionState (SessionStateReaderAdapter — READ ONLY)

| Fabric Component | Sections Read | Method | Purpose |
| --- | --- | --- | --- |
| `ContextBuilder` | `beliefs_active`, `history_active`, `task_state` | `read_section(session_id, section)` | Inject cognitive context into ExecutionContext for capability execution |
| `ContextBuilder.get_snapshot()` | ALL HOT+WARM | `get_snapshot()` | Full session context for agent prompt assembly |
| `PolicyEngine` (SecurityContext) | `control` | `read_section(session_id, "control")` | Safety band check — block capability if safety_band=RED |
| `PolicyEngine` (AffectiveRouting) | `affective_now` | `read_section(session_id, "affective_now")` | Emotion-aware provider scoring (+0.0–0.2 weight adjustment) |
| `PolicyEngine` (CognitiveLoadRouting) | `meta` | `read_section(session_id, "meta")` | Cognitive load scoring for model selection (+0.0–0.15) |

**Adapter translation:**
```
Fabric calls:    reader.read_section(session_id, "control")
Adapter does:    ssm.get_section("control")  → returns Section object
                 section.to_dict()            → returns Dict[str, Any]
Returns:         Dict[str, Any] to Fabric
```

**Cross-reference with Fabric API (16_fabric_api_mapping.md):**
- Fabric's `ISessionStateReader` port declares: `read_section(session_id, section_name) → Dict[str, Any]`
- SessionStateReaderAdapter implements this by calling `ssm.get_section(name).to_dict()`
- **ALIGNED**: Section names match, types match.

### 2.3 Planner → SessionState (PlannerStateAdapter — PARTIAL)

| Planner Component | Sections Read | Method | Purpose |
| --- | --- | --- | --- |
| `ToolCallRouter` (state_read tool) | `control` | `read_sections(["control"], trace_id)` | Safety band, active domains for planning constraints |
| `ToolCallRouter` (state_read tool) | `beliefs_active` | `read_sections(["beliefs_active"], trace_id)` | Known facts for constraint derivation |
| `ToolCallRouter` (state_read tool) | `history_active` | `read_sections(["history_active"], trace_id)` | Recent turns for intent understanding |
| `ToolCallRouter` (state_read tool) | `task_state` | `read_sections(["task_state"], trace_id)` | Active tasks for dependency planning |
| `ToolCallRouter` (state_read tool) | `scoreboard` | `read_sections(["scoreboard"], trace_id)` | Open questions, commitments for plan goals |

**Adapter translation:**
```
Planner calls:   state_adapter.read_sections(["control", "beliefs_active"], trace_id)
Adapter does:    for section in sections:
                     reader.read_section(session_id, section)  → Dict
Returns:         Dict[str, Dict[str, Any]]  (section_name → data)
```

**Cross-reference with Planner API (15_planner_api_mapping.md):**
- Planner's `IStateReadPort` declares: `read_sections(sections: List[str], trace_id) → Dict[str, Dict]`
- PlannerStateAdapter wraps an `ISessionStateReader` (same interface as Fabric's reader)
- **⚠ PARTIAL**: Adapter code exists but in some kernel wiring paths, `reader=None` is passed as placeholder (PLN-GAP-01 from planner mapping).

### 2.4 Orchestrator → SessionState (MockStateReadAdapter — STUB ❌)

| Orchestrator Component | Sections Read | Method | Purpose |
| --- | --- | --- | --- |
| `_check_safety_band()` | `control` | `read_section("control")` → `safety_band` | Pre-execution safety gate |
| `_build_plan_request()` | ALL | `get_snapshot()` → full SessionSnapshot | PlanRequest.context for Planner |

**Adapter translation:**
```
Orch calls:    state_adapter.read_section("control")
Mock returns:  {}  (empty dict — always)

Orch calls:    state_adapter.get_snapshot()
Mock returns:  SessionSnapshot(empty)  (always empty)
```

**Cross-reference with Orchestrator API (15_orchestrator_api_mapping.md):**
- Orchestrator's `IStateReadPort` declares: `read_section(section) → Dict`, `get_snapshot() → SessionSnapshot`
- MockStateReadAdapter implements both methods but returns empty data
- **❌ NOT WIRED**: Orchestrator never receives real session state. `_check_safety_band()` always sees `safety_band=None` → defaults to GREEN → **safety gate is bypassed**.
- **❌ Planner context**: PlanRequest.context receives empty SessionSnapshot → Planner plans without cognitive context

### 2.5 MemoryWriter → SessionState (SessionReadAdapter — READ ONLY)

| Component | Sections Read | Method | Purpose |
| --- | --- | --- | --- |
| End-of-turn processor | `beliefs_active` | `read_section("beliefs_active")` | Extract facts to persist to K0 long-term memory |
| End-of-turn processor | `history_active` | `read_section("history_active")` | Extract turns to compress and archive to K0 |

**Cross-reference:** MemoryWriter reads are downstream of Concierge writes. After Concierge mutates `beliefs_active` and `history_active` on each turn, MemoryWriter reads those same sections to decide what to persist.

### 2.6 ModelHub → SessionState (MHStateReadAdapter — READ ONLY)

| Component | Sections Read | Method | Purpose |
| --- | --- | --- | --- |
| Token budget | `meta` | `read_section("meta")` | Session metadata for model selection |
| Cost tracking | `telemetry` | `read_section("telemetry")` | Token usage for budget management |

---

## 3. Data Flow Chains — End-to-End Session Context

### 3.1 User Turn → SessionState → Planner → Fabric

```text
User message arrives at Concierge
  │
  ▼
Concierge Turn Engine:
  mutate("control", "set", {intent, domain, safety_band})
  mutate("history_active", "add_turn", user_turn)
  mutate("beliefs_active", "add_fact", extracted_facts)
  mutate("affective_now", "set", emotion_state)
  mutate("scoreboard", "push_question", qud)
  │
  ▼                              reads
Orchestrator ─────────────────► SessionState ["control"] ──► safety_band check
  │                              (⚠ Mock returns {} → always GREEN)
  │
  ▼ build PlanRequest
Orchestrator ─────────────────► SessionState [get_snapshot()] ──► PlanRequest.context
  │                              (⚠ Mock returns empty → Planner has no context)
  │
  ▼ delegate to Planner
Planner ──────────────────────► SessionState ["control", "beliefs_active",
  │                              "history_active", "task_state", "scoreboard"]
  │                              (⚠ reader=None in some paths → no reads)
  │
  ▼ plan compiled → steps → Orchestrator → Fabric
Fabric ───────────────────────► SessionState ["control"] ──► safety_band for PolicyEngine
  │                              (✅ LIVE — reads real safety_band)
  ▼
Fabric ───────────────────────► SessionState ["beliefs_active", "history_active",
                                 "task_state"] ──► ContextBuilder for capability prompts
                                 (✅ LIVE — reads real cognitive context)
```

**Critical observation:** Fabric reads REAL session state, but the data it reads was written by Concierge. Orchestrator and Planner — the components that decide WHAT to execute — operate on empty/partial session state. This creates an asymmetry where execution (Fabric) is context-aware but planning (Orch+Planner) is context-blind.

### 3.2 Agent Spawn via Fabric — SessionState Role

When Fabric spawns a new agent (via ContextBuilder + PromptSystem):

```text
Fabric.CapabilityFabric.execute(CapabilityRequest)
  │
  ▼
Resolver → select provider (Agent, LLM, Tool, Retrieval)
  │
  ▼ (if Agent provider)
ContextBuilder.build_context(request, provider, session_id):
  │
  ├─ reader.read_section(session_id, "beliefs_active")
  │    → inject known facts into agent prompt
  ├─ reader.read_section(session_id, "history_active")
  │    → inject conversation history for continuity
  ├─ reader.read_section(session_id, "task_state")
  │    → inject active tasks for agent awareness
  ├─ reader.read_section(session_id, "control")
  │    → safety_band for capability boundary enforcement
  ├─ reader.read_section(session_id, "affective_now")
  │    → emotion state for affect-aware responses
  │
  ▼
PromptSystem.resolve(template, context)
  → assembled prompt with full session context
  │
  ▼
Agent executes with session-aware prompt
```

This is the **primary purpose** the user noted: "fabric when any new agent is spawned via prompt and it needs to understand session and also recall memories from k0."

**K0 memory recall path (FUTURE):**
```text
Session restore / cold start:
  ReconstructionSLA.reconstruct()
    ├─ LOCAL COLD (SQLite) → restore section data
    ├─ K0 fallback (IK0SyncPort) → ⚠ NullSyncPort (always fails)
    └─ FRESH start (empty sections)
```

K0 recall is **not yet wired**. The `IK0SyncPort` is `NullSyncPort` (always offline). When wired, Fabric-spawned agents will be able to recover from K0 long-term memory on cold starts.

---

## 4. Type Compatibility Matrix

### 4.1 Section Data Format Across Consumers

| Section | SSM Internal Type | Fabric Receives | Planner Receives | Orch Receives |
| --- | --- | --- | --- | --- |
| `control` | `ControlSection` | `Dict[str, Any]` (via `.to_dict()`) | `Dict[str, Any]` (via reader) | `{}` (mock) |
| `beliefs_active` | `BeliefsActiveSection` | `Dict[str, Any]` | `Dict[str, Any]` | `{}` (mock) |
| `history_active` | `HistoryActiveSection` | `Dict[str, Any]` | `Dict[str, Any]` | `{}` (mock) |
| `affective_now` | `AffectiveNowSection` | `Dict[str, Any]` | Not read | `{}` (mock) |
| `scoreboard` | `ScoreboardSection` | Not directly | `Dict[str, Any]` | `{}` (mock) |
| `task_state` | `TaskStateSection` | `Dict[str, Any]` | `Dict[str, Any]` | `{}` (mock) |
| `meta` | `MetaSection` | `Dict[str, Any]` | Not read | `{}` (mock) |
| `persona` | `PersonaSection` | Not directly | Not read | `{}` (mock) |
| `telemetry` | `TelemetrySection` | Not directly | Not read | `{}` (mock) |

**Key:** All live adapters call `section.to_dict()` which returns a flat `Dict[str, Any]`. Consumers do `data.get("field_name")` to extract values. No schema validation at the boundary — consumers trust the dict shape.

### 4.2 SessionSnapshot Usage

| Consumer | How It Gets Snapshot | What It Uses |
| --- | --- | --- |
| Orchestrator | `state_adapter.get_snapshot()` | Forwarded as `PlanRequest.context` to Planner (⚠ empty from mock) |
| Planner | Receives via `PlanRequest.context` | Session-level context for plan reasoning (⚠ empty) |
| Fabric | Does not use snapshot directly | Reads individual sections via ContextBuilder |
| Diagnostics/CLI | `ssm.get_snapshot()` | Full health/pressure report |

---

## 5. Compound Gap Analysis — "Systemic Session-State Blindness"

### 5.1 The Core Problem

Three components have degraded or absent SessionState access:

| Component | Adapter | Real Data? | Impact |
| --- | --- | --- | --- |
| Orchestrator | `MockStateReadAdapter` | ❌ No | Safety gate bypassed, Planner gets empty context |
| Planner | `PlannerStateAdapter(reader=None)` | ⚠ Partial | ToolCallRouter state_read fails silently |
| Fabric (shared mode) | `NullSessionStateReaderAdapter` | ❌ No | Shared Fabric instances lack session context |

### 5.2 Gap Cross-Reference Table

| Gap ID | Source Doc | Component | Description | Severity |
| --- | --- | --- | --- | --- |
| **XREF-SS-01** | 15_orch | Orchestrator | MockStateReadAdapter never replaced with real SSM adapter | **HIGH** |
| **XREF-SS-02** | 15_planner | Planner | PlannerStateAdapter reader=None placeholder in some wiring paths | **HIGH** |
| **XREF-SS-03** | 17_fabric | Fabric | NullSessionStateReaderAdapter in shared Fabric mode | **MEDIUM** |
| **SS-GAP-01** | 18_ss | SessionState | WARM budget discrepancy (sections sum 52KB, tier limit 48KB) | LOW |
| **SS-GAP-02** | 18_ss | SessionState | narrative_active in demotion list but no WARM target | LOW |
| **SS-GAP-03** | 18_ss | SessionState | 5 production stub adapters blocking full wiring | MEDIUM |
| **SS-GAP-06** | 18_ss | SessionState | K0SyncPort not wired (NullSyncPort) | MEDIUM |

### 5.3 Impact Chain

```text
XREF-SS-01: MockStateReadAdapter (Orchestrator)
  └─► _check_safety_band() sees safety_band=None → defaults GREEN
       └─► Safety gate ALWAYS PASSES regardless of actual session risk
  └─► get_snapshot() returns empty
       └─► PlanRequest.context is empty
            └─► Planner receives no session context in initial request
                 └─► XREF-SS-02: Even if Planner tried state_read tool,
                      reader=None means it fails too
                      └─► Plan is generated WITHOUT:
                           • Knowledge of current safety band
                           • User's active beliefs/facts
                           • Conversation history
                           • Active tasks/dependencies
                           • Discourse state (QUD, commitments)

XREF-SS-03: NullSessionStateReaderAdapter (Fabric shared mode)
  └─► ContextBuilder gets empty sections
       └─► Agent prompts lack session context
            └─► Agent operates in isolation, no continuity
```

### 5.4 Fix Priority & Approach

| Priority | Gap | Fix | Complexity |
| --- | --- | --- | --- |
| **P0** | XREF-SS-01 | Replace MockStateReadAdapter with `SessionStateReaderAdapter(ssm, session_id)` at kernel P1 (Orch wiring) | LOW — adapter exists, just need to wire |
| **P0** | XREF-SS-02 | Wire PlannerStateAdapter with real `SessionStateReaderAdapter` at kernel P6 | LOW — adapter exists, just need to pass non-None reader |
| **P1** | XREF-SS-03 | Create shared-mode reader that takes `session_id` as parameter per call, or require per-session Fabric instances | MEDIUM — design decision needed |
| **P2** | SS-GAP-03 | Implement 5 stub adapters (BridgeStorage, BridgeSync, ConciergeWriter, DeltaBus, FabricLifecycle) | MEDIUM — each requires integration target |
| **P2** | SS-GAP-06 | Wire K0SyncPort for cloud backup/restore | MEDIUM — requires Bridge integration |
| **P3** | SS-GAP-01 | Align WARM section budgets with tier limit (reduce sections by 4KB or raise tier to 52KB) | LOW — config change |

### 5.5 Recommended Fix for P0 Gaps (Orchestrator + Planner)

**Kernel service.py change** (conceptual):

```python
# P2: SessionState creation (already exists)
ssm = SessionStateFactory.create_with_ports(...)
async_ssm = AsyncSSMBridge(ssm)

# P1: Orchestrator — REPLACE Mock with real reader
from k1.fabric.adapters import SessionStateReaderAdapter
orch_state_reader = SessionStateReaderAdapter(ssm, session_id)
orchestrator = OrchestratorFactory.create(
    state_adapter=orch_state_reader,  # was: MockStateReadAdapter()
    ...
)

# P6: Planner — PASS real reader
from k1.fabric.adapters import SessionStateReaderAdapter
planner_ss_reader = SessionStateReaderAdapter(ssm, session_id)
planner_state_adapter = PlannerStateAdapter(reader=planner_ss_reader)  # was: reader=None
planner = PlannerFactory.create(
    state_adapter=planner_state_adapter,
    ...
)
```

This gives both Orchestrator and Planner live session state, fixing the "context-blind planning" problem identified in section 3.1.

---

## 6. Event Correlation — SessionState Events × Consumers

### 6.1 Who Should Listen to SessionState Events

| Event | Likely Consumer | Current Subscriber | Gap? |
| --- | --- | --- | --- |
| `mutation.approved` | Telemetry, MemoryWriter | None (LocalEventAdapter, no subscribers) | YES — no component subscribes |
| `mutation.rejected` | Telemetry, Concierge (retry logic) | None | YES |
| `eviction.triggered` | Telemetry, Orchestrator (plan replay?) | None | YES |
| `eviction.completed` | Telemetry | None | YES |
| `emergency.activated` | Orchestrator (pause planning), Concierge (throttle writes) | None | YES — **critical for backpressure** |
| `emergency.resolved` | Orchestrator, Concierge | None | YES |
| `reconstruction.started` | Telemetry | None | LOW priority |

**Note:** Events are emitted via `LocalEventAdapter` (in-process) but no consumer component subscribes. The event infrastructure exists but is unused. This is acceptable for V1 (edge-first, single-process) but becomes important when DeltaBusAdapter is wired for multi-process.

---

## 7. Session Lifecycle × Component Awareness

### 7.1 Session Creation Flow

```text
User connects → Concierge creates session
  │
  ▼
Kernel.create_session(session_id):
  P2: SSM = SessionStateFactory.create_with_ports(session_id, ...)
      SSM.start(restore_if_exists=True)
        → ReconstructionSLA: try LOCAL COLD → K0 → FRESH
  P3: Fabric.bind_session(SessionStateReaderAdapter(ssm, session_id))
  P4: Concierge.bind_session(SSMStateAdapter(ssm))
  P5: MemoryWriter.bind_session(SessionReadAdapter(ssm))
  P6: Planner.bind_session(PlannerStateAdapter(reader=...))
  │
  ▼
All components have session-specific SSM references
(except Orchestrator → Mock, per XREF-SS-01)
```

### 7.2 Session Destruction Flow

```text
User disconnects → Concierge signals session end
  │
  ▼
Kernel.destroy_session(session_id):
  MemoryWriter: flush pending writes to K0
  SSM.stop(checkpoint_before_stop=True)
    → Final checkpoint to LOCAL COLD
    → Cancel periodic timer
    → Transition RUNNING → STOPPED
  Unbind all component adapters
```

### 7.3 Component Awareness of Session Lifecycle

| Component | Knows Session State? | Handles Session Stop? |
| --- | --- | --- |
| Concierge | YES (via SSMStateAdapter) | YES — triggers session end |
| Fabric | YES (via reader) | Partial — stops reading |
| Planner | Partial (⚠ reader may be None) | No explicit handler |
| Orchestrator | NO (mock) | No explicit handler |
| MemoryWriter | YES (via reader) | YES — flushes K0 writes |
| ModelHub | YES (via reader) | No explicit handler |

---

## 8. Summary Matrix — SessionState Integration Health

| Integration | Wired? | Data Flows? | Correct? | Test Coverage |
| --- | --- | --- | --- | --- |
| Concierge → SSM (writes) | ✅ | ✅ | ✅ | Unit + integration |
| Concierge → SSM (reads) | ✅ | ✅ | ✅ | Unit + integration |
| Fabric → SSM (reads) | ✅ | ✅ | ✅ | Unit (via mock reader) |
| Planner → SSM (reads) | ⚠ | ⚠ reader=None some paths | ❌ partial | Unit (mock only) |
| Orchestrator → SSM (reads) | ❌ | ❌ Mock returns {} | ❌ | None (mock always passes) |
| MemoryWriter → SSM (reads) | ✅ | ✅ | ✅ | Unit |
| ModelHub → SSM (reads) | ✅ | ✅ | ✅ | Unit |
| SSM → LOCAL COLD (archive) | ✅ | ✅ | ✅ | Unit + integration |
| SSM → K0 (sync) | ❌ | ❌ NullSyncPort | N/A | N/A (future) |
| SSM events → consumers | ❌ | ❌ No subscribers | N/A | N/A (future) |

**Bottom line:** 6/10 integrations are **LIVE and correct**. The 2 **P0 gaps** (Orchestrator mock, Planner reader=None) create systemic context blindness in the planning pipeline. Fixing them requires wiring changes only — no new adapter code needed.
