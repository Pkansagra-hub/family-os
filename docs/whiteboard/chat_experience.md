# 💬 Chat Interface ↔ K1 Kernel Connection Architecture

**Question:** How will our chat interface be connected to our K1 kernel agentic system?

---

## 📊 Complete Architecture Flow (Corrected with Writer Agents)

```text
┌─────────────────────────────────────────────────────────────────────┐
│  USER CHAT INTERFACE (Frontend)                                     │
│  • Web app (React/Vue)                                              │
│  • Mobile app (iOS/Android)                                         │
│  • Voice assistant                                                  │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ (WebSocket/REST/SSE)
┌─────────────────────────────────────────────────────────────────────┐
│  API GATEWAY (K1 Layer 5: Infrastructure)                           │
│  • TLS 1.3 encryption                                               │
│  • JWT authentication (1-hour tokens) — RS256 with capability tokens│
│  • Rate limiting (100 req/min per session)                          │
│  • CORS handling                                                    │
│  • Request routing & load balancing                                 │
│  • Privacy band validation (GREEN/AMBER/RED)                        │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│  K1 API ENDPOINTS (Layer 1: Input Processing)                       │
│  • REST API: /api/v1/sessions, /api/v1/turns                        │
│  • WebSocket: wss://k1.example.com/ws (FlatBuffers framing)         │
│  • SSE Stream: /api/v1/stream (recall hints, consolidation events)  │
│                                                                     │
│  Stream Switch (normalizes: text, audio, vision)                    │
│  Intent Router (3-tier: rules → SLM → LLM, <50ms P95)               │
│  SessionState Bootstrap (captures metadata, privacy_band, locale)   │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│  K1 CONCIERGE AGENT (Layer 3: 🤖 AI Agent — Tier 1)                 │
│  • NLU/Intent Classification (50ms budget)                          │
│  • Phi-3-mini on-device LLM                                         │
│  • Meta-intent triage: 11 patterns (ACK, STATUS, SMALL_TALK, etc.)  │
│  • Routes task intents to K1 Orchestrator                           │
│  • Maintains conversation continuity via SessionState               │
│  • Direct resolution for meta-intents (no orchestration)            │
│                                                                     │
│  OUTPUT: task_envelope.fbs with cognitive_trace_id + capabilities   │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ (routes to)
┌─────────────────────────────────────────────────────────────────────┐
┌─────────────────────────────────────────────────────────────────────┐
│  K1 ORCHESTRATOR (Layer 2: Pure Actor — 3-Phase Contract Net)       │
│                                                                     │
│  ▪️ PURE ACTOR (deterministic, NO LLM, NO Model Hub)                │
│  ▪️ Coordinates 58 agents (4 AI + 54 pure actors)                   │
│  ▪️ Latency budget: <80ms P95 orchestration overhead                │
│                                                                     │
│  ═══════════════════════════════════════════════════════════════════ │
│  PHASE 1: NEGOTIATION (<50ms P95) — ADR-0006a                       │
│  ═══════════════════════════════════════════════════════════════════ │
│  Contract Net Protocol (Smith 1980):                                │
│                                                                     │
│  1. Broadcast TaskAnnouncement to all ACTIVE agents:                │
│     • Roster lookup: O(1) agent map                                 │
│     • Non-blocking send: Fire-and-forget to agent mailboxes         │
│     • Message: task_id, deadline_ms=50, required_tools, budget      │
│                                                                     │
│  2. Agents evaluate & bid (parallel, <20ms each):                   │
│     • Capability check: Do I have required tools/models?            │
│     • Estimate latency & cost: Based on tool registry               │
│     • Confidence scoring (4 factors):                               │
│       - Capability match (40%): How well do my tools fit?           │
│       - Success rate (30%): Historical success rate (learning loop) │
│       - Load (20%): Current mailbox depth (lower = higher conf.)    │
│       - Context (10%): Do I have session context available?         │
│     • Decision: Bid if confidence > threshold AND within budget     │
│                                                                     │
│  3. Collect proposals with 50ms deadline:                           │
│     • Non-blocking receives from MPSC queue                         │
│     • Early exit: If all expected agents responded, stop waiting    │
│     • Deadline enforced: Latecomers ignored                         │
│     • Fallback (if no proposals):                                   │
│       - Tier 1: Hire new agent (if capacity)                        │
│       - Tier 2: Simplify task (reduce tool count)                   │
│       - Tier 3: Wait 100ms, retry                                   │
│       - Tier 4: Graceful degradation (return empty)                 │
│                                                                     │
│  ═══════════════════════════════════════════════════════════════════ │
│  PHASE 2: SELECTION (<5ms P95) — ADR-0006b                          │
│  ═══════════════════════════════════════════════════════════════════ │
│  Multi-Criteria Weighted Scoring (MADM):                            │
│                                                                     │
│  1. Normalize factors (all to 0-1 scale):                           │
│     • Confidence: Already 0-1 from agent                            │
│     • Latency: 1.0 if ≤50% budget, else decay to 0.5 at budget     │
│     • Cost: 1.0 if ≤30% budget, else decay to 0.5 at budget        │
│     • Parallelism: 1.0 (yes) or 0.7 (partial) or 0.0 (no)          │
│     • Track record: Agent's success rate (0.0-1.0)                  │
│     • Load penalty: Agent's current load (0.0=idle, 1.0=full)       │
│                                                                     │
│  2. Score all proposals (weighted sum):                             │
│     score = 10.0×conf + 8.0×lat + (-5.0)×cost + 3.0×par +          │
│              2.0×track + (-4.0)×load                                │
│     Typical range: -10 to +25                                       │
│     Example: Expert agent = 20.0, Overloaded agent = 10.0           │
│                                                                     │
│  3. Rank by score (highest = best):                                 │
│     Sort proposals descending by score                              │
│                                                                     │
│  4. Tie-breaking (if multiple max scores):                          │
│     • 60% prefer_resident (agent already in session)                │
│     • 20% prefer_fast (lowest latency)                              │
│     • 10% prefer_cheap (lowest cost)                                │
│     • 10% random (for exploration)                                  │
│     Result: Deterministic winner selection                          │
│                                                                     │
│  5. Send TaskAssignment to winner:                                  │
│     • Message: Full TaskAnnouncement + winning agent_id             │
│     • Routing: Via winner's mailbox (MPSC queue)                    │
│     • Logging: Full score breakdown for explainability              │
│                                                                     │
│  ═══════════════════════════════════════════════════════════════════ │
│  PHASE 3: EXECUTION (50-500ms per task) — ADR-0006c                 │
│  ═══════════════════════════════════════════════════════════════════ │
│  Parallel DAG Execution with MapReduce-style Barriers:              │
│                                                                     │
│  1. Build task dependency graph (DAG):                              │
│     • Parse steps from plan                                         │
│     • Identify dependencies (Step B depends on Step A output)       │
│     • Validate: No cycles allowed                                   │
│                                                                     │
│  2. Compute parallel waves (topological sort):                      │
│     • Wave 1: All independent steps (no dependencies)               │
│     • Barrier: Wait for all Wave 1 tasks to complete                │
│     • Wave 2: Steps that depend on Wave 1 results                   │
│     • Barrier: Wait for all Wave 2 tasks                            │
│     • ... (repeat for all waves)                                    │
│     • Max parallelism: 3 concurrent tasks (semaphore limit)         │
│                                                                     │
│  3. Execute each wave (parallel within wave, sequential across):    │
│     • Per-task: <5ms deterministic logic OR 50-500ms LLM call       │
│     • Task types:                                                   │
│       - Tool: Call API (search, booking, etc)                       │
│       - Model: LLM inference (chat, classification, etc)            │
│       - Ask: Clarification from user                                │
│     • Error handling:                                               │
│       - Critical step fails: Abort, trigger compensation            │
│       - Non-critical fails: Log, continue                           │
│                                                                     │
│  4. Collect results + handle errors (Saga Pattern):                 │
│     • Success: Return task result to user                           │
│     • Critical failure: Compensation (reverse-order undo)           │
│       - Step A: Delete calendar event                               │
│       - Step B: Cancel restaurant booking                           │
│       - Step C: Refund payment                                      │
│     • Non-critical failure: Return partial results                  │
│                                                                     │
│  RESULT: Fastest possible execution (parallelism) + Reliability     │
│  (error recovery) + Observability (full trace via cognitive_trace_id)
│                                                                     │
│  NOTES:                                                             │
│  • ALL coordination is deterministic (no randomness in logic)       │
│  • Proposals flow: Negotiation → Selection → Execution → K0 storage│
│  • Latency split: Negotiate (38ms) + Select (3ms) + Execute (var)  │
│  • Performance validation: PoC achieved 16ms P95 negotiation        │
│    (vs 50ms target), 3-5ms P95 selection (vs 5ms target)           │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ (creates or reuses)
┌─────────────────────────────────────────────────────────────────────┐
│  K1 SPECIALIST AGENTS (Layer 3: On-Demand Dynamic Creation)         │
│  • HealthcareAgent — PT schedules, medications, recovery            │
│  • FinanceAgent — Budgets, costs, insurance                         │
│  • SocialCoordinator — Family events, visits, relationships         │
│  • ResearcherAgent — Knowledge synthesis (semantic search)          │
│  • PlannerAgent — 4-stage task planning (Layer 2: 🤖 AI Agent)      │
│  • RoutineAgent — Habits, reminders                                 │
│  • EmergencyAgent — Crisis detection, escalation                    │
│  • Created on-demand, terminated after task completion              │
│  • Each uses Model Hub for LLM reasoning (4 AI agents total)        │
│                                                                     │
│  OUTPUT: Tool results + SessionState deltas via DeltaBus            │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ (reads/writes)
┌─────────────────────────────────────────────────────────────────────┐
│  K1 SESSION STATE (Layer 4: Runtime Core)                           │
│  • 6-Section Working Memory (In-process, <1ms access):              │
│    1. Beliefs (user beliefs, confidence, temporal decay)            │
│    2. Scoreboard (QUD stack, entity tracking, pronoun resolution)   │
│    3. Control (current_flow, agent_roster, execution_state)         │
│    4. Persona (personality traits, LLM system prompt)               │
│    5. Multimodal (audio waveforms, image embeddings)                │
│    6. Meta (session_id, creation_time, turn count, cognitive_trace) │
│                                                                     │
│  • FlatBuffers serialization: session_state.fbs (11 schemas)        │
│  • Delta computation: field-level diffs only (ADR-0019)             │
│  • Field-level batching: 250ms interval or 100-delta trigger        │
│  • Eviction: Priority-based (beliefs > multimodal > scoreboard)     │
└─────────────────────────────────────────────────────────────────────┘

                              ↓ (deltas flow to)
┌─────────────────────────────────────────────────────────────────────┐
│  TIER 3: WRITER AGENTS (Background, Always-Active, Specialized)     │
│  • MemoryWriterAgent (Active Agent - Knows P02/P05/Semantic tables) │
│    - RECEIVES TASKS from Planner (e.g., "store prospective trigger")│
│    - READS SessionState: beliefs, control, persona, meta            │
│    - READS deltas from DeltaBus (in-process event bus)              │
│    - KNOWS EXACTLY which K0 tables & schemas:                       │
│      * P05 (Prospective): Cron triggers + event-based               │
│      * P02 (Episodic): Memories with embedding vectors              │
│      * Semantic: Concept relationships + KG edges                   │
│    - ENRICHES with: trigger candidates, agent roster, affect        │
│    - FORMATS smartly: Different serialization per target table      │
│    - Outputs: Batched CommandType.MEMORY_WRITE envelopes            │
│                                                                     │
│  • LearningExtractorAgent (Active Agent - Knows P06 schema)         │
│    - RECEIVES TASKS from Planner (e.g., "extract learning signal")  │
│    - READS: SessionState scoreboard, user feedback, agent perf.     │
│    - KNOWS: P06 Learning pipeline requirements + table schema       │
│    - EXTRACTS: learning signals, drift indicators, confidence scores│
│    - WRITES: P06 pipeline with parameter update recommendations     │
│                                                                     │
│  • SemanticEnricherAgent (Active Agent - Knows semantic/KG schema)  │
│    - RECEIVES TASKS from Planner (e.g., "enrich memory with KG")    │
│    - READS: SessionState beliefs, extracted entities                │
│    - KNOWS: Semantic table + KG schema (nodes, edges, temporal)     │
│    - ENRICHES: Concepts, relationships, affect, entity connections  │
│    - WRITES: K0 semantic index + KG updates                         │
│                                                                     │
│  ALWAYS-ACTIVE: All three persist for session lifetime (like Tier 1)│
│  MAILBOX: Receive tasks from Planner (don't just watch DeltaBus)    │
│  ASYNC: Non-blocking to response streaming (concurrent background)  │
│  PERSISTENCE: Each writes via K0 Bridge with Privacy Lane routing   │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ (via batch_client.py & state_delta_emitter.py)
┌─────────────────────────────────────────────────────────────────────┐
│  K0 BRIDGE LAYER (Layer 5: K1 ↔ K0 Communication)                   │
│                                                                     │
│  Batching Pipeline (state_delta_emitter.py):                        │
│    • Batches collected deltas: 250ms flush OR 64KB OR 100 deltas    │
│    • Each batch: field_path + old_value + new_value + origin        │
│    • Privacy lane decision: GREEN fast-lane vs AMBER/RED smart-lane │
│    • Encodes: StateDelta FlatBuffers → CommandType envelope         │
│                                                                     │
│  Command Client (command_client.py):                                │
│    • Dual-protocol: FlatBuffers (primary) / JSON (fallback)         │
│    • Serializes batch → HTTP/2 POST                                 │
│    • Ports: P02 MemoryWrite (:5200) OR P06 Learning (:5206)         │
│    • Latency: <50ms GREEN, <200ms AMBER/RED                         │
│    • Retry: 3 attempts with exponential backoff                     │
│    • Receipt: Awaited before next batch (SLA enforcement)           │
│                                                                     │
│  WAL Writer (wal_writer.py):                                        │
│    • Logs orchestration outcomes + saga compensations               │
│    • Ensures reversible state (ADR-0008)                            │
│    • Feeds: K0 bridge traces for audit                              │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ (communicates with)
┌─────────────────────────────────────────────────────────────────────┐
│  K0 MEMORY KERNEL (Backend Storage & Processing)                    │
│  • 20 Pipelines (P01-P20) for memory processing:                    │
│                                                                     │
│    P01: Recall/Read                                                 │
│      • Input: Query from Concierge or Specialists                   │
│      • Returns: Episodic + Semantic + KG + Procedural               │
│      • Multi-store: FTS5 (BM25) + FAISS (vector) + SQLite KG        │
│                                                                     │
│    P02: Write/Ingest (Receives MemoryWriter batches)                │
│      • Stage 1: Schema validation, deduplication via episodic WAL   │
│      • Stage 2: Persist to K0::st_sqlite[episodic_memories]         │
│      • Stage 3: Materialize semantic projections + vectors          │
│      • Fan-out: Triggers P06, P19, P03 via kernel bus               │
│                                                                     │
│    P03: Consolidation (Sleep-like processing, 5 phases)             │
│      • Hippocampal Replay → Episodic→Semantic → KG Evolution →      │
│      • Synaptic Homeostasis → Dream-like Exploration                │
│                                                                     │
│    P06: Learning/Neuromod (Receives LearningExtractor signals)      │
│      • Adaptive feedback + parameter updates                        │
│      • Drift detection + rollback safety                            │
│                                                                     │
│    P19: Personalization (Receives SemanticEnricher context)         │
│      • User modeling + contextual adaptation                        │
│                                                                     │
│    ... and 15 more pipelines (sync, encryption, compliance, etc.)   │
│                                                                     │
│  • Multi-store architecture:                                        │
│    - K0::st_sqlite[episodic_memories] — Events + raw observations   │
│    - K0::st_sqlite[semantic_memories] — Generalizations + patterns  │
│    - K0::st_sqlite[prospective] — Future reminders & triggers       │
│    - K0::st_vector — FAISS index for semantic search                │
│    - K0::st_kg — Knowledge graph with temporal edges                │
│    - K0::st_episodic_wal — Deduplication index                      │
│                                                                     │
│  • CRITICAL: K0 P05 (Prospective Memory) Background Processing      │
│    - K0 P05 runs CONTINUOUSLY in background (not triggered by K1)   │
│    - Owns all temporal scheduling (time-based, pattern, anomaly)    │
│    - Evaluates triggers every minute (cron scheduler)               │
│    - **SENDS TICKS TO K1 VIA SSE** when trigger time arrives:       │
│      * Time-based: "4 hours, drink water" → SSE tick at 8am/12pm/   │
│      * Pattern-based: "Milk day detected" → SSE tick with confidence│
│      * Escalating: T+48h "rent due soon", T+24h "urgent!", T+0 "NOW"│
│      * Anomaly-based: "Unusual spending detected" → SSE alert       │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ (SSE notifications back to K1)
┌─────────────────────────────────────────────────────────────────────┐
│  K0 SSE PORT (:5202) — Sends Ticks & Events TO K1                   │
│  • **Direction: K0 → K1** (K0 is PROACTIVE, sends ticks)            │
│  • Topics sent:                                                     │
│    - prospective.trigger.fired — Time-based reminders               │
│    - prospective.pattern.detected — Learned routine detections      │
│    - prospective.anomaly.alert — Unusual activity detected          │
│    - memory.write.ack — Persistence confirmations                   │
│    - consolidation.* — Sleep-like processing events                 │
│                                                                     │
│  • K1 ProactiveAgent subscribes & listens:                          │
│    - Receives ticks from K0 P05 (no polling!)                       │
│    - Acts on ticks: notifies user, enriches context                 │
│    - Feeds back to Orchestrator for execution                       │
│                                                                     │
│  • Future turns pre-hydrated: Intent Router caches received ticks   │
│  • Bridge-only persistence: K1 state ephemeral, K0 is durable       │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ (response streamed back via)
┌─────────────────────────────────────────────────────────────────────┐
│  RESPONSE STREAMING (WebSocket + SSE)                               │
│  • K1 generates response using LLM (50-500ms)                       │
│  • Concierge + Specialists synthesize results                       │
│  • SessionState beliefs + persona used for response formatting      │
│  • Streams tokens to user in real-time via WebSocket                │
│                                                                     │
│  CONCURRENT BACKGROUND (Tier 3 Writer Agents):                      │
│    • MemoryWriterAgent — Extract entities, enrich, batch to K0      │
│    • LearningExtractor — Score learning signals, detect drift       │
│    • SemanticEnricher — Tag concepts, analyze affect, score salience│
│    • None block response; all async → K0 bridge                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🔑 Key Distinctions: Writer Agents Pattern

**NOT Direct K1 SessionState → K0:**

K1 SessionState lives **in-process** and is NOT directly persisted. Instead:

1. **SessionState Deltas** flow from working memory to a **DeltaBus** (in-process event bus)
2. **Writer Agents** (specialized background actors) subscribe to **DeltaBus**
3. Each Writer Agent **knows**:
   - Which K0 tables to write to (episodic vs semantic vs KG)
   - How to format data for that specific table
   - Which K0 pipeline (P02, P06, P19, P03) to target
   - Privacy bands and capability routing
4. Writer Agents **batch** deltas and send via **K0 Bridge** (state_delta_emitter + batch_client)
5. K0 Bridge validates, route-decides (Fast vs Smart lane), and dispatches

**Sources:**

- **epic_1_1_ingress_discovery.md** — Steps 8-12: SessionState stewardship + MemoryWriter agents + P02 bridge persistence
- **whiteboard_chatexp.md** — Tier 3 Writer Agents pattern (MemoryWriterAgent, LearningExtractor, SemanticEnricher)
- **K1 README** — Layer 4 (SessionState) + Layer 5 (K0 Bridge)
- **ADR-0019** — Delta serialization (field-level diffs)
- **ADR-0001a** — K0 Bridge communication protocol (dual-format, lane routing)
- **ADR-0017** — SessionState 6-section design
- **ADR-0049** — Fast/Smart lane routing (privacy + obligation scoring)

---

## 🚀 Complete Proactive Flow Example

### Scenario: "Remind me to drink water every 4 hours"

```text
T0: USER SAYS
   "Remind me to drink water every 4 hours"

T0+35ms: K1 CONCIERGE DETECTS
   ├─ Meta-intent: PROSPECTIVE_MEMORY (temporal request)
   └─ Creates: task_envelope ("Store 4-hour water reminder")

T0+55ms: K1 PLANNER (Layer 2 AI Agent)
   ├─ Stage 1 (Sketch): LLM generates plan
   ├─ Stage 2 (Expand): Deterministic tool lookup
   ├─ Stage 3 (Validate): Rules + Safety Watch checks
   └─ Stage 4 (Commit): Sends task to MemoryWriterAgent
       "Task: Store prospective trigger
        - Type: time_based
        - Frequency: every 4 hours (cron: 0 8,12,16,20)
        - Action: notification"

T0+100ms: MEMORYWRITER AGENT (Tier 3, Active, Always-Listening)
   ├─ RECEIVES task from Planner mailbox
   ├─ READS SessionState:
   │  ├─ beliefs: user's typical schedule (work 9-5)
   │  ├─ control: current privacy_band (GREEN)
   │  └─ persona: preference level (casual reminders OK)
   │
   ├─ KNOWS: P05 Prospective table schema
   ├─ FORMATS: Structured trigger object
   └─ SENDS to K0 via Bridge:
       StateDelta {
         trigger_id: "trigger_123",
         type: "time",
         schedule: "0 8,12,16,20 * * *",
         action: "drink_water",
         priority: 5,
         privacy_band: "GREEN"
       }

T0+250ms: K0 BRIDGE (state_delta_emitter → batch_client → command_client)
   ├─ Batches delta with others
   ├─ Lane router decides: GREEN band → Fast lane
   └─ Sends HTTP/2 POST to K0 P02 (MemoryWrite port)

T0+300ms: K0 STORES
   ├─ K0::st_sqlite[prospective] ← prospective trigger stored
   └─ K0 P05 Scheduler adds to queue

═══════════════════════════════════════════════════════════════

MEANWHILE, K0 P05 BACKGROUND LOOP (Runs every minute, always):

8:00am (TOMORROW):
   K0 P05 checks: "Any triggers due NOW?"
   ├─ Finds: trigger_123 (drink water)
   ├─ Evaluates: Time match + context
   └─ EMITS SSE TICK: prospective.trigger.fired
       {event: "drink_water", time: "8:00am", confidence: 0.98}

   ↓
   K0 SSE Port → K1 ProactiveAgent (listening)

K1 PROACTIVE AGENT (Tier 3, Always-Listening via SSE):
   ├─ RECEIVES tick from K0: "Drink water now!"
   ├─ QUERIES K1: Any active task? (check SessionState control)
   └─ IF user available (not in meeting):
       Sends notification: 💧 "Time to drink water! (4/8 daily goal)"

USER SEES:
   💧 "Time to drink water! (4/8 daily goal)"
   [✓ Done] [Later]

═══════════════════════════════════════════════════════════════

12:00pm (SAME DAY):
   K0 P05 fires again → SSE tick → K1 ProactiveAgent
   → Notification: 💧 "Midday water break! (5/8 goal)"

4:00pm:
   K0 P05 fires again → Notification: 💧 (6/8)

8:00pm:
   K0 P05 fires again → Notification: 💧 (7/8)
```

### Key Insight: System is PROACTIVE, not Reactive

```text
REACTIVE (OLD WAY):
User asks → K1 processes → Done
(K0 waits for user to ask again)

PROACTIVE (NEW WAY):
User sets trigger → K0 stores + runs background loop
→ At trigger time, K0 SENDS tick to K1
→ K1 acts before user asks
→ System feels "alive" and anticipatory ✨
```

---

## 🎯 Writer Agents: The Intelligence Layer

**Each Writer knows specialized things:**

| Writer | Reads From | Knows | Writes To |
|--------|------------|-------|-----------|
| **MemoryWriterAgent** | SessionState + task | P05/P02 schemas, episodic vs semantic | K0::st_sqlite[prospective, episodic, semantic] |
| **LearningExtractorAgent** | SessionState + feedback | P06 schema, drift signals | K0 P06 pipeline (learning updates) |
| **SemanticEnricherAgent** | SessionState beliefs | KG schema, entity relationships | K0::st_kg, K0::st_sqlite[semantic] |

**Each receives TASKS from Planner:**

- "Store this prospective trigger"
- "Extract learning from this turn"
- "Enrich this memory with semantics"

**Each knows EXACTLY which K0 table and schema** to use for their domain.

This is the **bridge between intelligent decision-making (K1) and durable knowledge storage (K0)**.

---

## 🧠 **Complete System Integration: 7-Component Architecture**

All components work together as a coordinated cognitive system. Here's how each component fits:

### **1. 📬 MAILBOX = Nervous System (Message Passing)**

**Role:** Foundation for all inter-agent communication

**What it does:**

- Every agent has a **mailbox** (async message queue)
- 4 priority levels: URGENT (0) → REALTIME (1) → INTERACTIVE (2) → BACKGROUND (3)
- Weighted Fair Queueing: URGENT messages processed 4x more often than BACKGROUND
- Backpressure protection: High watermark (50 msgs) → Low watermark (25 msgs)

**Performance:** <0.5ms P95 enqueue/dequeue latency

**Example:**

```python
# Concierge sends task to Planner
concierge.send_message(
  receiver="planner",
  priority=2,  # INTERACTIVE (agent coordination)
  payload={"task": "Book dinner", "trace_id": "trace_xyz"}
)

# Planner receives on mailbox, processes
task = planner.mailbox.receive()  # Blocks until msg available
```

---

### **2. 🤖 CONCIERGE = Decision Maker (Route or Handle?)**

**Role:** Master coordinator at K1 entrance (Tier 1 AI Agent)

**What it does:**

1. **Receives** user input from chat interface
2. **Classifies intent:** Is this a meta-intent or task-intent?
   - Meta-intent: "ok thanks", "what time is it?", "remind me later" → **Handle directly** (no orchestration)
   - Task-intent: "book dinner", "remind me to drink water", "schedule meeting" → **Route to Planner**
3. **Routes** task-intents to Planner via mailbox (Priority 2: INTERACTIVE)
4. **Maintains** conversation context via SessionState

**Decision Logic (LLM-based):**

```python
class ConciergeAgent:
  def process_user_input(self, user_message: str):
    intent = self.llm_classify(user_message)  # Meta vs Task

    if intent.type == "META_INTENT":
      response = self.handle_directly(intent)  # Use LLM for conversational response
      return response_to_user(response)
    else:  # TASK_INTENT
      task_envelope = self.create_task(intent)
      planner_mailbox.send(
        Message(priority=2, task=task_envelope, trace_id=generate_trace_id())
      )
      # Return to user: "I'll handle that..."
      return "Processing your request..."
```

**Examples:**

```text
User: "what time is it?" → Concierge handles directly (meta-intent)
User: "book an italian restaurant" → Routes to Planner (task-intent)
User: "remind me to drink water in 4 hours" → Routes to Planner (task-intent)
```

---

### **3. 📋 PLANNER = Task Generator (4-Stage Pipeline — ADR-0007)**

**Role:** AI-driven task planning and validation (Tier 2 AI Agent, Layer 2: Orchestration)

**Integration Point:** Receives `task_envelope.fbs` from Orchestrator (after agent selection) at **T0+140ms**

**Architecture Overview:**

```text
┌─────────────────────────────────────────────────────────────┐
│  PLANNER AGENT (Tier 2 AI Agent — ADR-0007)                │
│                                                             │
│  Role: Decompose tasks into executable steps                │
│  Input: task_envelope.fbs (from Orchestrator Phase 2)       │
│  Output: committed_plan.fbs (serialized DAG or step list)   │
│                                                             │
│  PURE LLM REASONING: Generates high-level plans             │
│  DETERMINISTIC EXPANSION: Tool schema lookups               │
│  SAFETY VALIDATION: Privacy + capability checks             │
│  PERSISTENCE: Serialize to K0 WAL contracts                 │
│                                                             │
│  Budget: ~80ms P95 (sketch 50ms + expand 1ms + validate 10ms)
└─────────────────────────────────────────────────────────────┘
```

**What it Does:**

The Planner breaks down complex user intents into executable sub-tasks:

- "Remind me to drink water in 4 hours" → [Create prospective memory trigger + Store in K0 P05]
- "Book Italian restaurant for 4 at 7pm" → [Search restaurants API + Filter results + Present options]
- "What's Mom's PT schedule?" → [Query K0 P03 episodic memory + Filter by PT + Format response]

---

## **4-Stage Planning Pipeline (Sketch → Expand → Validate → Commit)**

### **Stage 1️⃣: SKETCH (~50ms) — High-Level Plan Generation**

**What happens:**

- LLM (Phi-3-medium) receives `task_envelope.fbs` with:
  - User intent (natural language)
  - SessionState context (beliefs, preferences, privacy band)
  - Domain constraints (available tools, capabilities)

- LLM generates **high-level sketch plan**:
  - Structured as: `[step_1, step_2, step_3, ...]`
  - Each step: Natural language + estimated inputs/outputs
  - Includes parallelism hints (can steps run in parallel?)
  - Respects privacy band constraints

**Example outputs:**

```text
Input: "Book Italian restaurant for 4 at 7pm"

Sketch Output:
  [
    Step 1: "Search for Italian restaurants near [user_location]"
    Step 2: "Filter by availability at 7pm for 4 people"
    Step 3: "Sort by rating and price"
    Step 4: "Present top 3 options to user"
    Parallelism: Steps 1-3 can run in parallel, Step 4 after
  ]

Input: "Remind me to drink water in 4 hours"

Sketch Output:
  [
    Step 1: "Create temporal trigger with delay=4h"
    Step 2: "Store in K0 P05 (prospective memory)"
    Step 3: "Return confirmation to user"
    Parallelism: Steps 1-2 can run in parallel
  ]
```

**Capabilities:**

- ✅ Reasoning about multi-step workflows
- ✅ Understanding user intent semantics
- ✅ Estimating parallelism opportunities
- ✅ Respecting privacy band context
- ✅ Handling ambiguity (asks clarification questions)

**Latency:** 50ms (LLM token generation time)

---

### **Stage 2️⃣: EXPAND (~1ms) — Deterministic Tool Resolution**

**What happens:**

- For each step in the sketch, **lookup which agent/tool can execute it**
- Deterministic lookup (no LLM): Uses tool registry + agent capabilities
- Generates: `expanded_plan.fbs` with concrete executors

**Tool Resolution Strategy:**

```text
Sketch Step: "Search for Italian restaurants near [user_location]"
                    ↓
          Look up agent capabilities:
                    ↓
  ┌─ researcher_agent: {tools: [google_places_api, yelp_api], domain: restaurants}
  ├─ tool_runner_1: {tools: [generic_http_client, json_parser]}
  ├─ tool_runner_2: {tools: [generic_http_client, json_parser]}
  └─ healthcare_agent: {tools: [medical_api]} ← NOT a match
                    ↓
         Select best-fit agent (researcher_agent)
                    ↓
      Expanded Step: {
        agent_type: "researcher_agent",
        tool: "google_places_api",
        params: {query: "italian restaurants", location: "[user_location]"},
        expected_output: "list_of_restaurants"
      }
```

**Tool Registry Lookup:**

```python
# Deterministic mapping: Sketch intent → Agent + Tools
TOOL_REGISTRY = {
  "search_restaurants": {
    "preferred_agent": "researcher_agent",
    "tools": ["google_places_api", "yelp_api"],
    "budget_ms": 500,
  },
  "store_memory": {
    "preferred_agent": "memory_writer_agent",
    "tools": ["k0_p02_writer", "k0_p05_writer"],
    "budget_ms": 50,
  },
  "query_episodic": {
    "preferred_agent": "memory_query_agent",
    "tools": ["k0_p02_reader", "k0_p03_reader"],
    "budget_ms": 100,
  },
  ...
}
```

**Output: expanded_plan.fbs**

```json
{
  "steps": [
    {
      "step_id": "step_1",
      "agent": "researcher_agent",
      "tool": "google_places_api",
      "inputs": {"query": "italian", "location": "[user_location]", "party_size": 4},
      "outputs": {"type": "list", "schema": "restaurant_listing"},
      "budget_ms": 500
    },
    {
      "step_id": "step_2",
      "agent": "researcher_agent",
      "tool": "filter_availability",
      "inputs": {"restaurants": "step_1.output", "time": "19:00", "party_size": 4},
      "outputs": {"type": "list", "schema": "restaurant_listing"},
      "budget_ms": 50
    },
    ...
  ],
  "parallelism_groups": [
    ["step_1", "step_2"],  // Can run in parallel
    ["step_3"],             // Depends on step_1/step_2
  ]
}
```

**Capabilities:**

- ✅ Deterministic agent selection (no LLM calls)
- ✅ Schema validation (output matches expected type)
- ✅ Budget forecasting (time + resource estimates)
- ✅ Parallelism analysis (topological sort)

**Latency:** <1ms (O(1) lookup + O(steps) iteration)

---

### **Stage 3️⃣: VALIDATE (~10ms) — Safety & Capability Checks**

**What happens:**

- **Two-tier validation:** Rules engine + LLM arbiter for risky cases
- Ensures: Privacy, permissions, resource availability, safety constraints

**Validation Checks:**

```python
class PlanValidator:
  def validate_plan(self, expanded_plan, task_envelope):

    # 1️⃣ PRIVACY BAND CHECK
    for step in expanded_plan.steps:
      storage_location = step.get_output_storage()
      user_band = task_envelope.privacy_band  # GREEN/AMBER/RED

      if storage_location == "K0_EPISODIC" and user_band == "RED":
        # ❌ FAILED: Can't store RED-band data in persistent episodic memory
        raise PrivacyViolation(
          f"Step {step.id}: RED-band data cannot be stored in P02 episodic"
        )

    # 2️⃣ CAPABILITY CHECK
    for step in expanded_plan.steps:
      required_tools = step.get_required_tools()
      agent = self.get_agent(step.agent)

      if not agent.has_capabilities(required_tools):
        # ❌ FAILED: Agent doesn't have required tools
        raise CapabilityMissing(
          f"Agent {agent.name} missing tools: {required_tools}"
        )

    # 3️⃣ RESOURCE AVAILABILITY
    total_budget_ms = sum(step.budget_ms for step in expanded_plan.steps)
    if total_budget_ms > task_envelope.deadline_ms:
      # ⚠️ WARNING: Plan exceeds deadline (may escalate to LLM arbiter)
      return self.escalate_to_llm_arbiter(expanded_plan, task_envelope)

    # 4️⃣ PERMISSION CHECK
    for step in expanded_plan.steps:
      required_permissions = step.get_required_permissions()
      user_permissions = task_envelope.get_user_permissions()

      if not user_permissions.has_all(required_permissions):
        # ❌ FAILED: User lacks required permissions
        raise PermissionDenied(
          f"User missing permissions: {required_permissions}"
        )

    # 5️⃣ EXTERNAL API AVAILABILITY
    for step in expanded_plan.steps:
      if step.tool_type == "external_api":
        is_available = self.check_api_circuit_breaker(step.tool)
        if not is_available:
          # ⚠️ WARNING: API currently down (escalate to LLM arbiter)
          return self.escalate_to_llm_arbiter(expanded_plan, task_envelope)

    return ✅ VALIDATED
```

**LLM Arbiter (for edge cases):**

When validation encounters risky/ambiguous cases:

```python
def escalate_to_llm_arbiter(self, expanded_plan, context):
  """
  LLM makes judgment call on edge cases:
  - Budget exceeded but plan is feasible if steps are optimized
  - API temporarily unavailable but fallback exists
  - Permissions missing but alternative approach available
  """
  arbiter_prompt = f"""
  Plan exceeds latency budget ({total_time}ms > {deadline}ms).
  Can you suggest optimizations?
  - Parallel more steps?
  - Drop low-priority steps?
  - Cache intermediate results?
  """

  optimized_plan = self.llm_suggest_optimization(arbiter_prompt)
  return ✅ VALIDATED_WITH_OPTIMIZATIONS
```

**Output: validated_plan.fbs**

- Same as `expanded_plan.fbs` but with validation status
- Includes risk warnings (if any)
- Budget forecasts confirmed

**Capabilities:**

- ✅ Privacy band enforcement (GREEN/AMBER/RED)
- ✅ Permission validation (user capabilities)
- ✅ Resource budget forecasting
- ✅ API health checks (circuit breakers)
- ✅ Risk escalation to LLM arbiter

**Latency:** ~10ms (parallel rule engine checks + optional LLM escalation)

---

### **Stage 4️⃣: COMMIT (~5ms) — Serialize & Persist**

**What happens:**

- **Serialize** the validated plan to `committed_plan.fbs` (FlatBuffers)
- **Persist** to K0 WAL (write-ahead log) for recovery
- **Return** to Orchestrator for execution

**Serialization (FlatBuffers):**

```python
# Python FlatBuffers schema (defined in k1/contracts/flatbuffers/)
class CommittedPlan:
  plan_id: str           # Unique trace_id reference
  steps: List[PlanStep]  # Array of executable steps
  parallelism_groups: List[List[str]]  # Which steps can run in parallel
  metadata: {
    created_at: timestamp,
    created_by: "planner_agent",
    ttl_ms: 30000,  # Plan valid for 30 seconds
    cognitive_trace_id: "[parent trace]"
  }

class PlanStep:
  step_id: str
  agent_type: str           # researcher, memory_writer, etc.
  tool: str                 # google_places_api, k0_p02_writer, etc.
  input_schema: dict        # FlatBuffers schema for inputs
  output_schema: dict       # FlatBuffers schema for outputs
  estimated_latency_ms: int
  priority: int             # 1=critical, 2=interactive, 3=background
  fallback: Optional[PlanStep]  # Fallback if this step fails
```

**Persistence to K0 WAL:**

```python
def commit_plan(self, validated_plan, task_envelope):
  # Serialize to FlatBuffers binary
  committed_plan_binary = FlatBufferEncoder.encode(validated_plan)

  # Persist to K0 WAL (write-ahead log)
  # This enables recovery if K1 crashes mid-execution
  wal_client.write(
    envelope_type="planning_pipeline.fbs",
    payload=committed_plan_binary,
    cognitive_trace_id=task_envelope.trace_id,
    priority=2  # INTERACTIVE priority
  )

  # Return to Orchestrator for DAG execution
  return committed_plan_binary
```

**Output: committed_plan.fbs**

- Ready for Orchestrator DAG execution
- Stored durably in K0 WAL
- Timeline continues to **T0+220ms (Wave Launch)**

**Capabilities:**

- ✅ FlatBuffers serialization (efficient binary format)
- ✅ K0 WAL persistence (crash recovery)
- ✅ Trace propagation (cognitive_trace_id maintained)
- ✅ Ready for parallel DAG execution

**Latency:** ~5ms (serialization + WAL write)

---

## **Complete 4-Stage Timeline & Integration**

```text
Timeline (milliseconds from user message):

T0+0ms    ────────────► User enters message
T0+15ms   ────────────► Intent Router → API GATEWAY → Layer 1
T0+35ms   ────────────► CONCIERGE evaluates meta-intent
T0+55ms   ────────────► ORCHESTRATOR Phase 1: Negotiation
T0+90ms   ────────────► ORCHESTRATOR Phase 2: Selection & Staffing
              ↓
T0+140ms  ════════════► PLANNER ENTERS (Agent selected for planning)
          ║
          ║ Stage 1 (Sketch ~50ms)
          ║   LLM generates high-level plan
          ║   ├─ Analyze user intent
          ║   ├─ Identify required steps
          ║   └─ Plan parallelism
          ║
T0+190ms  ║ Stage 2 (Expand ~1ms)
          ║   Deterministic tool lookup
          ║   ├─ Which agent handles each step?
          ║   ├─ Validate tool availability
          ║   └─ Build expanded_plan.fbs
          ║
T0+210ms  ║ Stage 3 (Validate ~10ms)
          ║   Safety & capability checks
          ║   ├─ Privacy band enforcement
          ║   ├─ Permission validation
          ║   ├─ Resource budget check
          ║   └─ LLM arbiter (if risky)
          ║
T0+220ms  ║ Stage 4 (Commit ~5ms)
          ║   Serialize & persist
          ║   ├─ FlatBuffers encoding
          ║   ├─ K0 WAL persistence
          ║   └─ Return to Orchestrator
          ║
T0+225ms  ════════════► ORCHESTRATOR Phase 3: Execution Begins
              ↓
          DAG wave 1 execution starts...
```

---

## **Integration with K1 System Components**

### **How Planner Integrates:**

```text
          ┌─────────────┐
          │ CONCIERGE   │
          └──────┬──────┘
                 │ routes task_intent
                 ↓
          ┌─────────────┐
          │ORCHESTRATOR │ (Phase 1-2: Negotiate & Select)
          └──────┬──────┘
                 │ selected_agent = planner_agent
                 ↓
         ┌────────────────┐
         │    PLANNER     │ ◄─── YOU ARE HERE
         │  (4-Stages)    │
         └──────┬─────────┘
                │ returns committed_plan.fbs
                ↓
          ┌─────────────┐
          │ORCHESTRATOR │ (Phase 3: Execution)
          │ (DAG Runner)│
          └──────┬──────┘
                 │ launches parallel waves
                 ↓
         ┌────────────────┐
         │ SPECIALISTS    │ (researcher, tool_runner, etc.)
         │  (Execute)     │
         └────────────────┘
```

### **Data Flow (FlatBuffers Contracts):**

```
Input Pipeline:
  task_envelope.fbs
    ↓ (from Concierge + Orchestrator selection)
    ↓
  PLANNER processing:
    ├─ Stage 1: sketch_plan.fbs (internal LLM output)
    ├─ Stage 2: expanded_plan.fbs (tool resolution)
    ├─ Stage 3: validated_plan.fbs (safety checks)
    └─ Stage 4: committed_plan.fbs (ready to execute)
    ↓
  Output Pipeline:
    committed_plan.fbs
      ├─ Serialized to FlatBuffers binary
      ├─ Persisted to K0 WAL
      └─ Returned to Orchestrator for DAG execution
```

---

## **Planner Capabilities & Constraints**

| Capability | Details |
|------------|---------|
| **LLM Reasoning** | Phi-3-medium on-device; reasoning about complex workflows |
| **Tool Schema Knowledge** | Knows all ~150 tool schemas from registry |
| **Privacy Awareness** | Respects GREEN/AMBER/RED privacy bands |
| **Parallelism Detection** | Identifies independent steps for concurrent execution |
| **Budget Awareness** | Plans within latency/resource budgets |
| **Fallback Planning** | Generates alternate plans if primary fails |
| **Plan Persistence** | Stores plans in K0 WAL for crash recovery |
| **Trace Propagation** | Maintains cognitive_trace_id through all stages |

| Constraint | Details |
|-----------|---------|
| **Max Plan Size** | ~500 steps (for reasonable DAG complexity) |
| **Max Depth** | ~20 waves (serial dependency depth) |
| **Budget** | ~80ms P95 for all 4 stages |
| **Tool Registry** | Limited to registered tools (can't invoke arbitrary APIs) |
| **Permissions** | Respects user capability tokens (ADR-0037) |
| **Determinism** | Stages 2-4 are deterministic (only Stage 1 uses LLM) |

---

## **Real-World Example: Restaurant Booking**

```
User Input: "Book Italian restaurant for 4 at 7pm tomorrow in downtown"

T0+140ms: PLANNER ACTIVATED
├─ Stage 1 (Sketch):
│  └─ LLM generates: ["search restaurants", "filter availability", "book table", "send confirmation"]
│
├─ Stage 2 (Expand):
│  ├─ "search restaurants" → researcher_agent + google_places_api
│  ├─ "filter availability" → researcher_agent + filter_tool
│  ├─ "book table" → tool_runner_1 + restaurant_booking_api
│  └─ "send confirmation" → concierge_agent + template_formatter
│
├─ Stage 3 (Validate):
│  ├─ ✅ Privacy band: GREEN (no sensitive data stored)
│  ├─ ✅ Permissions: User has restaurant access
│  ├─ ✅ Budget: 500ms total < 5s deadline
│  └─ ✅ APIs: All available
│
└─ Stage 4 (Commit):
   └─ Serialize committed_plan.fbs → persist to K0 WAL

T0+220ms: ORCHESTRATOR Phase 3 Begins
├─ Wave 1 (Parallel): researcher searches + filter availability
├─ Wave 2 (Dependent): tool_runner books table (waits for Wave 1 results)
└─ Wave 3 (Dependent): concierge formats confirmation

T0+600ms: Results returned to user with booking confirmation
```

**Implementation:**

```python
class PlannerAgent:
  def plan_task(self, task_envelope):
    # Stage 1: Sketch
    sketch = self.llm_generate_sketch(task_envelope)
    # Result: ["search_restaurants", "filter_availability", "book_table", "send_confirmation"]

    # Stage 2: Expand
    expanded = self.expand_sketch(sketch)
    # Result: expanded_plan.fbs with agent assignments, tools, schemas

    # Stage 3: Validate
    validated = self.validate_plan(expanded, task_envelope)
    # Result: validated_plan.fbs with safety checks passed

    # Stage 4: Commit
    committed = self.commit_plan(validated)
    # Result: committed_plan.fbs serialized + persisted to K0 WAL

    return committed
```

---

### **4. 🎯 ORCHESTRATOR = Deterministic Coordinator (3-Phase Contract Net)**

**Role:** Agent selection and task coordination (Tier 2 Pure Actor, NO LLM)

**What it does:**

- **Phase 1 (Negotiation ~50ms):** Broadcast task, collect bids from capable agents
- **Phase 2 (Selection ~5ms):** Score bids, select best agent(s)
- **Phase 3 (Execution 50-500ms):** Coordinate task execution, handle failures

**Why it's PURE (not AI):**

- Uses deterministic weighted scoring formula (not LLM)
- Speed: Deterministic <5ms vs LLM <100ms
- Predictability: No hallucinations in agent selection

**Implementation:**

```python
class OrchestratorActor:  # Pure actor, no LLM
  def execute_task(self, task):
    # Phase 1: Negotiate
    bidders = self.capability_directory.find_agents(task.capability)
    bids = self.broadcast_and_collect(task, bidders)  # Max 50ms wait

    # Phase 2: Select (deterministic scoring)
    winner = self.score_and_select(bids)
    # score = (confidence × 0.5) + (cost_efficiency × 0.3) + (availability × 0.2)

    # Phase 3: Execute
    winner_mailbox.send(Message(type="AWARD", task=task))
    result = winner_mailbox.receive_result()

    if result.status == "SUCCESS":
      return result
    else:  # FAILED
      # Saga compensation: roll back side effects
      self.execute_compensation_recipe(task, result)
```

**Example - Book Dinner:**

```text
Task: "Book Italian restaurant for 4 at 7pm"
       ↓
Broadcast to: [tool_runner_1, tool_runner_2, researcher]  (NOT all 58)
       ↓
Bids received:
  - tool_runner_1: {confidence: 0.95, cost: 1.0 credit, availability: high}
  - researcher: {confidence: 0.85, cost: 0.5 credit, availability: medium}
       ↓
Orchestrator scores & awards to tool_runner_1 (highest score)
       ↓
tool_runner_1 executes: calls restaurant API, books table
       ↓
Returns result to Orchestrator, which returns to Concierge
```

---

### **4b. 🔄 AGENT LIFECYCLE FSM = Agent State Management (ADR-0005 + ADR-0073 Enhancements)**

**Role:** Defines the state transitions for all agents (Tier 1-3 Pure Actors) with comprehensive implementation details

**Foundation:** ADR-0005 (6-state FSM) + ADR-0073 (WARMING/IDLE/DRAINING enhancements)

**Why FSM matters:**

- **Predictability:** Each state has defined entry/exit behaviors with error handling
- **Resource Management:** Clean startup/shutdown with validation, pooling, and cleanup
- **Observability:** Clear trace of agent lifecycle with health checks at each state
- **Fault Recovery:** Explicit compensation paths for failures (rollback, timeout enforcement, task tracking)

**Agent Lifecycle States:**

```text
┌──────────────────────────────────────────────────────────────┐
│  AGENT LIFECYCLE FSM (5-State Machine)                       │
└──────────────────────────────────────────────────────────────┘

    ┌─────────────┐
    │  PENDING    │  (Agent registered, not yet warming up)
    │             │  • Entry: Agent.__init__ complete
    │             │  • Action: None (idle state)
    │             │  • Exit to WARMING: on_activate() called
    │             │  • Exit to TERMINATED: on_shutdown() called
    └─────────────┘
            │
            ↓ (on_activate() called by OrchestratorActor)
    ┌─────────────┐
    │  WARMING    │  (Agent initializing resources - 4-Check Validation)
    │             │  • Entry: PENDING → WARMING via on_activate()
    │             │  • Check 1: Resource availability (CPU, memory, disk)
    │             │  • Check 2: Model loading (language, vision, embeddings)
    │             │  • Check 3: Capability binding (assign capabilities from spec)
    │             │  • Check 4: Supervisor health signal confirmation
    │             │  • Exit to ACTIVE: All 4 checks PASS (ready for orchestrator)
    │             │  • Exit to TERMINATED: Any check FAIL (rollback + cleanup)
    │             │  • Budget: <35s P95 (model loading dominates ~20-30s)
    └─────────────┘
            │
            ↓ (Ready signal received from supervisor)
    ┌─────────────┐
    │   ACTIVE    │  (Agent processing tasks)
    │             │  • Entry: Register in capability directory
    │             │  • Action: Bidding on tasks, executing work
    │             │  • Exit to IDLE: No tasks for 30 sec
    │             │  • Exit to DRAINING: on_drain() signal received
    └─────────────┘
            │
            ├─→ ┌─────────────────────────────┐
            │   │   IDLE                      │  (Agent pooling & TTL management)
            │   │                             │  • Entry: ACTIVE → IDLE (no tasks for 30s)
            │   │                             │  • Action: Add to session pool for reuse
            │   │                             │  • Pool Management: LRU eviction (max 3 agents/session)
            │   │                             │  • Health Checks: Every 30s while idle (<2s each)
            │   │                             │  • TTL Expiration: 10 min default per agent
            │   │                             │  • Exit to ACTIVE: New task bid request
            │   │                             │  • Exit to TERMINATED: TTL expired or health check fail
            │   │                             │  • Budget: <1ms pool lookup + <2s health check
            │   └─────────────────────────────┘
            │           ↓
            └───────────┘

            ↓ (on_drain() called during shutdown)
    ┌──────────────────────────────────┐
    │  DRAINING                        │  (Graceful shutdown with task tracking)
    │                                  │  • Entry: ACTIVE/IDLE → DRAINING via shutdown
    │                                  │  • Stop accepting new tasks immediately
    │                                  │  • Track all in-flight tasks (TaskTracker per task)
    │                                  │  • Request graceful completion for each task
    │                                  │  • Wait for completion: <30s timeout
    │                                  │  • Dependency cleanup: Resources, capabilities, models
    │                                  │  • Exit to TERMINATED: All tasks complete or timeout
    │                                  │  • Budget: <30.5s P95 (task completion dominates)
    │                                  │  • Forced termination if timeout exceeded
    └──────────────────────────────────┘
            │
            ↓ (All dependencies released)
    ┌─────────────┐
    │ TERMINATED  │  (Agent offline, resources freed)
    │             │  • Entry: Close all connections
    │             │  • Action: Deregister from capability directory
    │             │  • No exit: Final state
    └─────────────┘
```

**Implementation Details (ADR-0073 Enhancements):**

#### **Enhancement 1: WARMING State - 4-Check Resource Validation**

```python
class WarmingState:
    """WARMING state with 4-part resource validation before ACTIVE transition"""

    async def enter(self) -> None:
        """PENDING → WARMING transition"""
        try:
            # Check 1: Resource Availability (CPU, Memory, Disk)
            await self._check_resource_availability()
            # Check 2: Model Loading (language model, vision model, embeddings)
            await self._check_model_loading()
            # Check 3: Capability Binding (assign capabilities from spec)
            await self._check_capability_binding()
            # Check 4: Supervisor Health Signal (supervisor confirms monitoring ready)
            await self._check_supervisor_health()
            # All checks passed
            self.state = "ACTIVE"
            self.orchestrator.register_agent(self, self.capabilities)
        except WarmingCheckFailed as e:
            logger.error(f"agent_warming_failed: {e}")
            self.state = "TERMINATED"
            await self.supervisor.handle_warming_failure(self.agent_id, error=e)

    async def _check_resource_availability(self) -> None:
        """Check 1: Validate CPU, memory, disk per agent spec"""
        required_mem_mb = self.agent_spec.memory_budget_mb
        available_mem_mb = self.supervisor.get_available_memory_mb()

        if available_mem_mb < required_mem_mb:
            raise WarmingCheckFailed(
                f"Insufficient memory: need {required_mem_mb}MB, have {available_mem_mb}MB"
            )
        # Reserve resources
        self.supervisor.reserve_resources(
            agent_id=self.agent_id, memory_mb=required_mem_mb
        )

    async def _check_model_loading(self) -> None:
        """Check 2: Preload language model, vision model, embeddings (timeout: 30s)"""
        model_hub = self.supervisor.model_hub
        if self.agent_spec.language_model:
            await model_hub.preload_model(
                model_id=self.agent_spec.language_model,
                agent_id=self.agent_id,
                timeout_sec=30
            )
        # Similar for vision_model, embedding_model

    async def _check_capability_binding(self) -> None:
        """Check 3: Bind capabilities from spec, issue HMAC-signed capability tokens"""
        capability_manager = self.supervisor.capability_manager
        for capability_name in self.agent_spec.capabilities:
            cap_token = await capability_manager.issue_capability(
                subject=f"agent:{self.agent_id}",
                resource=capability_name,
                rights=["execute"],
                ttl_seconds=3600,
                constraints={"agent_id": self.agent_id, "session_id": self.supervisor.session_id}
            )
            await self.supervisor.store_capability(
                agent_id=self.agent_id,
                capability_name=capability_name,
                capability_token=cap_token
            )

    async def _check_supervisor_health(self) -> None:
        """Check 4: Supervisor confirms readiness (timeout: 5s)"""
        supervisor_ready = await self.supervisor.health_check(
            agent_id=self.agent_id, timeout_sec=5
        )
        if not supervisor_ready:
            raise WarmingCheckFailed("Supervisor health check failed")
```

**Performance:** Resource check <5ms | Model loading <30s | Capability binding <100ms | Supervisor check <5s → **Total <35s P95**

---

#### **Enhancement 2: IDLE State - Agent Pooling & TTL Management**

```python
class IdleState:
    """IDLE state with pooling, TTL expiration, and health checks"""

    async def enter(self) -> None:
        """ACTIVE → IDLE transition (no active tasks for 30s)"""
        # Add to agent pool for reuse (same type agent can be re-assigned task)
        await self.supervisor.pool_manager.add_to_pool(
            agent_id=self.agent_id,
            agent=self.supervisor.get_agent(self.agent_id),
            ttl_seconds=600  # 10-minute default TTL
        )

    async def periodic_health_check(self) -> bool:
        """Called every 30s while in IDLE state - return False if health fails"""
        try:
            # Minimal health check: agent process still running, memory still allocated
            health_status = await self.supervisor.quick_health_check(
                self.agent_id, timeout_sec=2
            )
            return health_status  # False triggers IDLE → TERMINATED
        except asyncio.TimeoutError:
            logger.error(f"idle_health_check_timeout: {self.agent_id}")
            return False

    async def check_ttl_expired(self) -> bool:
        """Check if TTL (10 min default) has elapsed - return True if expired"""
        elapsed_sec = (time.time() - self.idle_start_ts)
        return elapsed_sec > self.ttl_seconds

class AgentPoolManager:
    """Manages agent pooling to maximize reuse while respecting memory budgets"""

    async def add_to_pool(self, agent_id: str, agent: Agent, ttl_seconds: int = 600) -> None:
        """Add idle agent to pool (max 3 agents per session by default)"""
        session_id = agent.session_id
        if len(self.idle_pools.get(session_id, {})) >= self.max_agents_per_session:
            # Evict LRU (least recently used) agent
            lru_agent_id = self._find_lru_agent(session_id)
            await self.remove_from_pool(lru_agent_id)

        self.idle_pools[session_id][agent_id] = {
            'agent': agent,
            'added_ts': time.time(),
            'ttl_seconds': ttl_seconds,
            'access_count': 0
        }

    async def get_from_pool(self, session_id: str, agent_type: str) -> Optional[Agent]:
        """Get first available idle agent from pool for reuse"""
        pool = self.idle_pools.get(session_id, {})
        for agent_id, agent_entry in list(pool.items()):
            # Check TTL
            if time.time() - agent_entry['added_ts'] > agent_entry['ttl_seconds']:
                pool.pop(agent_id)
                continue
            # Check type match and reuse
            if agent_entry['agent'].agent_type == agent_type:
                pool.pop(agent_id)
                return agent_entry['agent']
        return None
```

**Memory Conservation:** Bounded pooling (≤3 agents/session) prevents unbounded memory growth. Models stay loaded in VRAM for <1ms reuse latency.

**Performance:** Pool lookup <1ms | Health check <2s (30s interval) | TTL check <1ms → **Negligible overhead**

---

#### **Enhancement 3: DRAINING State - Task Completion Tracking**

```python
class DrainingState:
    """DRAINING state with task tracking and graceful shutdown"""

    async def enter(self) -> None:
        """ACTIVE/IDLE → DRAINING transition (shutdown requested)"""
        # Get list of active tasks for this agent
        self.active_tasks = await self.supervisor.get_active_tasks(self.agent_id)
        logger.info(f"agent_draining_start: {len(self.active_tasks)} tasks")

        # Signal all tasks to complete gracefully
        for task_id, task in self.active_tasks.items():
            await task.request_completion()

    async def wait_for_completion(self) -> bool:
        """Wait for all tasks to complete or timeout (30s) - return True if all completed"""
        start_time = time.time()

        while True:
            elapsed_sec = time.time() - start_time

            # Check timeout
            if elapsed_sec > 30:  # 30s draining timeout
                logger.warn(f"draining_timeout: {len(self.active_tasks)} tasks incomplete")
                return False

            # Check if all tasks completed
            remaining_tasks = [tid for tid, task in self.active_tasks.items()
                             if not task.is_completed()]

            if not remaining_tasks:
                logger.info(f"draining_all_tasks_completed: elapsed_sec={int(elapsed_sec)}")
                return True

            await asyncio.sleep(0.25)

    async def cleanup_dependencies(self) -> None:
        """Clean up agent dependencies before termination"""
        # Release resources from supervisor
        await self.supervisor.release_resources(self.agent_id)
        # Remove from pool if present
        try:
            await self.supervisor.pool_manager.remove_from_pool(self.agent_id)
        except KeyError:
            pass
        # Revoke all capabilities
        await self.supervisor.capability_manager.revoke_agent_capabilities(self.agent_id)
        # Unload models from model hub
        await self.supervisor.model_hub.unload_agent_models(self.agent_id)

    async def exit(self) -> None:
        """DRAINING → TERMINATED transition"""
        all_completed = await self.wait_for_completion()

        if not all_completed:
            # Force-terminate remaining tasks
            for task_id, task in self.active_tasks.items():
                await task.force_terminate()

        await self.cleanup_dependencies()
        self.state = "TERMINATED"

class TaskTracker:
    """Tracks task completion during draining"""

    async def request_completion(self) -> None:
        """Request task to complete gracefully"""
        self.completion_requested = True

    async def mark_completed(self) -> None:
        """Mark task as completed"""
        self.completed = True

    async def force_terminate(self) -> None:
        """Force-terminate task if timeout exceeded"""
        logger.warn(f"task_force_terminated: {self.task_id}")
        self.completed = True
```

**Performance:** Draining start <10ms | Task wait <30s max | Cleanup <500ms → **Total <30.5s P95**

---

#### **Complete FSM Implementation Pattern:**

```python
class AgentBase:
  def __init__(self):
    self.state = "PENDING"
    self.mailbox = Mailbox()
    self.capabilities = set()
    self.in_flight_tasks = set()

  async def activate(self):
    """Entry to WARMING state (triggers 4 checks)"""
    self.state = "WARMING"
    warming_state = WarmingState(self.agent_id, self.agent_spec, self.supervisor)
    await warming_state.enter()
    self.state = warming_state.state  # ACTIVE or TERMINATED

  async def become_idle(self):
    """Entry to IDLE state (after 30s no tasks)"""
    if self.state == "ACTIVE":
      self.state = "IDLE"
      idle_state = IdleState(self.agent_id, self.supervisor)
      await idle_state.enter()

  async def drain(self):
    """Entry to DRAINING state (shutdown signal)"""
    if self.state in ["ACTIVE", "IDLE"]:
      self.state = "DRAINING"
      draining_state = DrainingState(self.agent_id, self.supervisor)
      await draining_state.enter()
      await draining_state.exit()  # Waits for task completion + cleanup
      self.state = "TERMINATED"
```

**Lifecycle Diagram (Concierge Agent Example - ADR-0073):**

```text
Concierge Agent Lifecycle During Chat Session:

┌─ Session Start
│
├─ PENDING (0ms)
│  └─ Concierge.__init__() complete, waiting for orchestrator
│
├─ WARMING (0-30000ms - 4 checks: resource, model, capability, supervisor)
│  ├─ Check 1: Resource availability <5ms
│  ├─ Check 2: Model loading (~20s for Phi-3-mini on GPU)
│  ├─ Check 3: Capability binding <100ms
│  └─ Check 4: Supervisor health <5s
│
├─ ACTIVE (30s - N sec - Processing tasks)
│  ├─ Chat Turn 1: Bid & execute meta-intent triage
│  ├─ Chat Turn 2: Bid & execute
│  └─ ... (remains ACTIVE, listening for new bids)
│
├─ IDLE (if 30+ sec of silence)
│  ├─ Added to pool (reuse optimization)
│  ├─ Periodic health checks every 30s (<2s each)
│  ├─ TTL default: 10 minutes
│  └─ Model stays resident in VRAM (rapid reactivation)
│
├─ DRAINING (on_drain signal received at shutdown)
│  ├─ Stop accepting new task bids
│  ├─ Track all in-flight tasks (TaskTracker)
│  ├─ Wait for completion (max 30s timeout)
│  ├─ Force-terminate if timeout exceeded
│  └─ Release resources, revoke capabilities, unload models
│
└─ TERMINATED
   └─ Agent offline, resources freed, removed from orchestrator
```

**Performance Budget (P95) - ADR-0073 Targets:**

| State | Duration P95 | CPU | Memory | Details |
|-------|-------------|-----|--------|---------|
| PENDING | N/A | 0% | 50MB | Lightweight, awaiting activation |
| WARMING | <35s | 30-50% | 2.5GB + models | Resource check (5ms) + model load (20-30s) + capabilities (100ms) + supervisor health (5s) |
| ACTIVE | Variable | 5-20% | 2.5GB | Processing tasks, bidding on work |
| IDLE | Continuous | 0% | 2.5GB | Periodic health checks every 30s (<2s each); models stay loaded for quick reuse |
| DRAINING | <30.5s | 10% | 2.5GB | Task tracking & wait (30s max) + cleanup (500ms) |
| TERMINATED | Immediate | 0% | 0% | Resources freed, models unloaded |

**Key Optimizations:**

- ✅ **Model Preloading in WARMING:** One-time cost amortized over many tasks
- ✅ **Agent Pooling in IDLE:** Rapid reuse (<1ms lookup) for same-type agents
- ✅ **Task Tracking in DRAINING:** Graceful completion with 30s hard timeout
- ✅ **Memory Bounding:** Max 3 agents per session prevents runaway allocation

---

### **4c. 🔀 SAGA PATTERN = Distributed Error Recovery with Compensating Transactions (ADR-0008 + Sub-ADRs 0008a-d)**

**Foundation:** ADR-0008 (Saga Pattern Error Recovery) + ADR-0008a (Compensating Transaction Design) + ADR-0008b (Forward Recovery vs Backward Recovery) + ADR-0008c (Distributed State Management) + ADR-0008d (Timeout & Deadlock Handling)

**Role:** Handles failures in multi-step workflows by executing compensating transactions in reverse order to undo side effects and maintain consistency.

**Why Saga Pattern?**

In K1 orchestration (Phase 3), workflows can span multiple external services (booking APIs, calendar APIs, payment processors). Traditional ACID transactions (2PC/3PC) don't work because:

- External APIs don't support 2PC protocol
- Workflows take seconds to minutes (not milliseconds)
- No global transaction coordinator exists
- **Partial failures leave inconsistent state** (booking confirmed but payment failed)

The Saga pattern solves this by systematically undoing completed steps when a later step fails.

---

#### **What is Saga Pattern?**

**Definition (Garcia-Molina & Salem, 1987):**
A saga is a **long-running transaction implemented as a sequence of local transactions**, where each step has a **corresponding compensating transaction** that undoes its side effects.

**Key Principles:**

1. **Sequence:** Steps execute in order (Step 1 → Step 2 → Step 3)
2. **Compensation:** Every step with side effects defines how to undo it
3. **Best-Effort Rollback:** If Step N fails, execute compensations for N-1, N-2, ..., 1 (reverse order)
4. **Eventual Consistency:** All steps eventually complete (successfully or compensated)
5. **Audit Trail:** All executions logged to K0 WAL for debugging

---

#### **Real-World Failure Example: Restaurant Booking**

```text
User Request: "Book dinner at Italian restaurant for 4 at 7pm tomorrow + add to calendar"

WITHOUT Saga Pattern (Current Behavior):
┌──────────────────────────────────────────┐
│ Step 1: Search restaurants                │
│ ✅ SUCCESS (found 5 restaurants)          │
└──────────────────────────────────────────┘
                  ↓
┌──────────────────────────────────────────┐
│ Step 2: Book reservation                 │
│ ✅ SUCCESS (booking #12345 confirmed)    │
│ SIDE EFFECT: Restaurant booking created  │
└──────────────────────────────────────────┘
                  ↓
┌──────────────────────────────────────────┐
│ Step 3: Add calendar event               │
│ ❌ FAILURE (calendar service timeout)    │
│ PROBLEM: No recovery, booking never added to calendar
│ USER SEES: "Something went wrong"        │
│ USER CONFUSION: Was I booked or not?     │
└──────────────────────────────────────────┘

RESULT: Inconsistent state (restaurant confirmed, calendar empty)
COST: User charges, no-show, cancellation fee, poor UX


WITH Saga Pattern (Desired Behavior):
┌──────────────────────────────────────────┐
│ Step 1: Search restaurants                │
│ ✅ SUCCESS (found 5)                      │
│ NO COMPENSATION: Read-only operation      │
└──────────────────────────────────────────┘
                  ↓
┌──────────────────────────────────────────┐
│ Step 2: Book reservation                 │
│ ✅ SUCCESS (booking #12345)               │
│ SIDE EFFECT: Restaurant booking created  │
│ COMPENSATION: Cancel booking #12345      │
└──────────────────────────────────────────┘
                  ↓
┌──────────────────────────────────────────┐
│ Step 3: Add calendar event               │
│ ❌ FAILURE (timeout)                      │
└──────────────────────────────────────────┘
                  ↓
        SAGA TRIGGERS ROLLBACK
                  ↓
┌──────────────────────────────────────────┐
│ COMPENSATION 2 (Reverse Order):          │
│ Cancel reservation (booking #12345)      │
│ ✅ SUCCESS (booking cancelled)           │
│ API CALL: DELETE /bookings/12345         │
└──────────────────────────────────────────┘
                  ↓
        NO MORE COMPENSATIONS
                  ↓
RESULT: Clean state (no booking, no calendar entry)
USER MESSAGE: "I couldn't add this to your calendar because the calendar service is down.
              The restaurant booking was cancelled to avoid a charge. Try again when the
              calendar service is back."
USER KNOWS: What happened, what was undone, can retry
```

---

#### **How Saga Pattern Works (Orchestrator-Driven)**

**Four Components:**

1. **Saga Coordinator (Pure Actor):** Orchestrates step execution and compensation
2. **Compensation Registry:** Maps tools to their undo actions (50+ compensations)
3. **Failure Classifier:** Decides retry forward vs rollback backward
4. **Distributed State:** K0 WAL persistence for crash recovery

**Saga Execution Flow:**

```python
class SagaCoordinator:
    """Orchestrate multi-step workflows with automatic compensation on failure"""

    async def execute_saga(self, plan: ValidatedPlan, session: SessionState):
        """
        Execute saga with automatic compensation on failure.

        Returns: SagaResult(success=True|False, completed_steps, compensations_run)
        """
        completed_steps = []  # Stack of completed steps (for LIFO compensation)

        try:
            # Execute each step in sequence
            for step_idx, step in enumerate(plan.steps):

                # Try forward recovery first (retry with exponential backoff)
                result = await self.execute_with_retry(
                    step=step,
                    max_retries=5,
                    base_delay_ms=100,
                    max_delay_ms=1600,
                    timeout_ms=30000  # 30s per step
                )

                if result.status == StepStatus.SUCCESS:
                    # Record completed step (for potential compensation)
                    completed_steps.append({
                        "step": step,
                        "result": result
                    })

                    # Log to K0 WAL
                    await self.k0_bridge.write_receipt(
                        topic="SAGA_STEP_SUCCESS",
                        payload={"step_id": step.id, "result": result}
                    )

                elif result.status == StepStatus.FAILURE:
                    # Forward recovery exhausted, trigger backward recovery
                    logger.error(
                        "saga_step_failed",
                        step_id=step.id,
                        error=result.error
                    )

                    # Run compensations in reverse order (LIFO)
                    compensation_results = await self.run_compensations(
                        completed_steps=completed_steps,
                        failed_step=step,
                        session=session
                    )

                    # Return aborted result with compensation summary
                    return SagaResult(
                        success=False,
                        completed_steps=len(completed_steps),
                        failed_step_idx=step_idx,
                        compensations_run=len(compensation_results),
                        user_message=self.generate_user_message(step, result.error)
                    )

            # All steps succeeded
            return SagaResult(
                success=True,
                completed_steps=len(completed_steps)
            )

        except asyncio.TimeoutError:
            # Saga timeout (120s total) → Trigger compensation
            logger.error("saga_timeout")
            await self.run_compensations(completed_steps, None, session)
            return SagaResult(success=False, reason="timeout")

    async def run_compensations(
        self,
        completed_steps: List[Dict],
        failed_step: Optional[PlanStep],
        session: SessionState
    ) -> List[CompensationResult]:
        """
        Run compensating transactions in reverse order (LIFO).

        Best-effort: Continue even if compensation fails.
        """
        compensation_results = []

        # Reverse order (last completed → first completed)
        for step_record in reversed(completed_steps):
            step = step_record["step"]

            # Skip read-only steps (no compensation needed)
            if not step.has_compensation():
                logger.info(f"step_no_compensation: {step.id} (read-only)")
                continue

            # Get compensation action
            compensation = step.get_compensation()

            logger.info(
                "saga_running_compensation",
                step_id=step.id,
                action=compensation.action
            )

            try:
                # Execute compensation with timeout (3s)
                comp_result = await asyncio.wait_for(
                    self.execute_compensation_action(compensation, step_record),
                    timeout=3.0
                )

                compensation_results.append(CompensationResult(
                    step_id=step.id,
                    success=True,
                    latency_ms=comp_result.latency_ms
                ))

                # Log to K0 WAL
                await self.k0_bridge.write_receipt(
                    topic="SAGA_COMPENSATION_SUCCESS",
                    payload={"step_id": step.id, "action": compensation.action}
                )

            except asyncio.TimeoutError:
                # Compensation timeout (3s exceeded)
                logger.error(f"compensation_timeout: {step.id}")
                compensation_results.append(CompensationResult(
                    step_id=step.id,
                    success=False,
                    error="Compensation timeout (3s)"
                ))

            except Exception as e:
                # Compensation failed (best-effort: continue)
                logger.error(f"compensation_failed: {step.id}: {e}")
                compensation_results.append(CompensationResult(
                    step_id=step.id,
                    success=False,
                    error=str(e)
                ))
                # Continue with next compensation (best-effort)

        return compensation_results
```

**Execution Latency Budget:**

- Forward recovery (retry): ~3s (5 retries × ~600ms avg)
- Backward recovery (compensation): ~15s (5 steps × 3s per compensation)
- Saga total timeout: 120s (covers all scenarios)

---

#### **Compensating Transaction Design (ADR-0008a)**

**Three Handler Types:**

##### **Type 1: Tool-Based Compensation**

```python
# Original step
StepDef(
    id="book_restaurant",
    tool="booking_api",
    compensation=ToolCompensation(
        tool_id="cancel_booking",
        params_mapping={
            "booking_id": "result.booking_id"  # Extract from step result
        },
        timeout_ms=3000
    )
)

# Execution: Saga coordinator calls cancel_booking tool with extracted params
```

##### **Type 2: API-Based Compensation**

```python
# Original step
StepDef(
    id="charge_payment",
    tool="payment_api",
    compensation=APICompensation(
        endpoint="https://payment-api.com/v1/refund",
        method="POST",
        payload_mapping={
            "transaction_id": "result.transaction_id",
            "amount": "result.amount"
        },
        timeout_ms=5000  # Payment refund needs more time
    )
)

# Execution: Direct HTTP POST to refund endpoint with mapped parameters
```

##### **Type 3: Custom Compensation**

```python
# Original step
StepDef(
    id="database_write",
    tool="database",
    compensation=CustomCompensation(
        handler_function="k1.compensation.handlers.rollback_database_write",
        params_mapping={
            "table": "step.parameters.table",
            "record_id": "step.parameters.record_id",
            "old_value": "result.old_value"
        }
    )
)

# Execution: Call custom handler with mapped parameters
```

**Compensation Registry (50+ Tools):**

| Tool | Compensation Action | Type |
|------|---------------------|------|
| book_hotel | cancel_booking | Tool |
| reserve_flight | cancel_flight | Tool |
| charge_payment | refund_payment | API |
| create_calendar_event | delete_calendar_event | Tool |
| write_file | delete_file | Tool |
| send_email | recall_email (best-effort) | API |
| database_write | rollback_write | Custom |

---

#### **Recovery Strategies (ADR-0008b: Forward vs Backward Recovery)**

**Strategy Selection Logic:**

```python
class RecoveryStrategySelector:
    """Classify errors and select optimal recovery strategy"""

    def select_strategy(self, error: StepError, step: PlanStep) -> RecoveryStrategy:
        """
        Select recovery strategy based on error type.

        Returns: RETRY_FORWARD, ROLLBACK_BACKWARD, or HYBRID
        """

        # Step 1: Classify error
        error_type = self.classify_error(error)

        # Step 2: Apply decision logic
        if error_type == ErrorType.TRANSIENT:
            # Transient (network timeout, rate limit)
            return RecoveryStrategy.RETRY_FORWARD  # Try again

        elif error_type == ErrorType.PERMANENT:
            # Permanent (invalid input, permission denied)
            return RecoveryStrategy.ROLLBACK_BACKWARD  # Give up + compensate

        elif error_type == ErrorType.AMBIGUOUS:
            # Unknown (timeout after send, 500 error)
            if step.is_idempotent():
                return RecoveryStrategy.RETRY_FORWARD  # Safe to retry
            else:
                return RecoveryStrategy.ROLLBACK_BACKWARD  # Avoid duplicate

# Error classification
TRANSIENT_ERRORS = [
    asyncio.TimeoutError,           # Network timeout
    HTTPException(429),              # Rate limit
    HTTPException(503)               # Service unavailable
]

PERMANENT_ERRORS = [
    ValueError,                       # Invalid input
    PermissionError,                  # Forbidden
    HTTPException(400),               # Bad request
    HTTPException(404)                # Not found
]

AMBIGUOUS_ERRORS = [
    HTTPException(500),               # Internal server error
    HTTPException(502),               # Bad gateway
    ConnectionError                   # Network partition
]
```

**Hybrid Recovery Flow:**

1. **Step fails** → Classify error
2. **If transient** → Retry (up to 5 times with exponential backoff)
3. **If all retries exhausted** → Trigger backward recovery (compensation)
4. **If permanent** → Skip retries, trigger backward recovery immediately

---

#### **Distributed State Management (ADR-0008c)**

**Why Persistence?**

Without persistence, saga state is lost if K1 crashes mid-execution:

```text
Scenario: K1 CRASHES mid-compensation
  Step 1: ✅ Book hotel
  Step 2: ✅ Reserve flight
  Step 3: ❌ Payment fails
  Step 4: 🔄 Start compensation (cancel flight)
  Step 5: 💥 K1 CRASHES

Without WAL: Flight booking never cancelled (orphaned)
With WAL: Recovery coordinator detects crash, resumes compensation
```

**Saga Log Structure:**

```python
SagaLog = {
    "saga_id": "saga_001",
    "state": "COMPENSATING",  # EXECUTING, COMPENSATING, COMPLETED, ABORTED, CRASHED
    "steps_completed": [
        {"step_id": 0, "tool_id": "search", "status": "SUCCESS"},
        {"step_id": 1, "tool_id": "book_hotel", "status": "SUCCESS"}
    ],
    "compensation_stack": [  # LIFO stack for reverse-order execution
        {"step_id": 1, "action": "cancel_booking", "params": {"booking_id": "12345"}},
        # Will execute in reverse order
    ],
    "created_at": 1698000000,
    "last_heartbeat_at": 1698000030,  # Updated every 10s
}

# Written to K0 WAL topic: SAGA_LOG (7-day retention)
```

**Crash Recovery:**

```python
class SagaRecoveryCoordinator:
    """Detect and recover crashed sagas"""

    async def detect_crashed_sagas(self):
        """Scan K0 WAL for sagas with no heartbeat for 60s"""
        crashed = await k0_client.query(
            topic="SAGA_LOG",
            filter={
                "state": ["EXECUTING", "COMPENSATING"],
                "last_heartbeat_at": {"$lt": now_ms - 60000}  # 60s timeout
            }
        )
        return crashed

    async def recover_saga(self, saga_log: SagaLog):
        """Resume compensation from crashed saga"""
        # Execute compensation stack in reverse order (LIFO)
        for compensation in reversed(saga_log.compensation_stack):
            await execute_compensation(compensation)

        # Mark saga as ABORTED
        saga_log.state = "ABORTED"
        await k0_client.update(topic="SAGA_LOG", payload=saga_log)
```

**Heartbeat Mechanism:**

- Saga coordinator sends heartbeat every 10s
- K0 marks saga as CRASHED if no heartbeat for 60s
- Recovery coordinator scans for crashed sagas every 30s
- At-least-once delivery: Compensations may run 1-3 times (idempotency ensures correctness)

---

#### **Timeout & Deadlock Handling (ADR-0008d)**

**4-Level Timeout Hierarchy:**

| Level | Timeout | Purpose |
|-------|---------|---------|
| **Step** | 30s | Prevent individual tool calls from hanging |
| **Compensation** | 3s | Fail-fast on compensation (don't wait long) |
| **Saga** | 120s | Prevent sagas from running forever |
| **Session** | 600s | Prevent sessions from living forever |

**Timeout Enforcement:**

```python
# Step timeout
result = await asyncio.wait_for(
    tool_runner.run_tool(step),
    timeout=30  # 30 seconds
)

# Compensation timeout (shorter, fail-fast)
comp_result = await asyncio.wait_for(
    execute_compensation(compensation),
    timeout=3  # 3 seconds
)

# Saga total timeout (covers all steps + compensations)
saga_result = await asyncio.wait_for(
    execute_saga(plan),
    timeout=120  # 120 seconds
)
```

**Deadlock Prevention:**

- Resource ordering: Acquire locks in deterministic order (sorted by ID)
- Timeout-based resolution: If can't acquire lock within 5s, abort and trigger compensation
- DAG validation: Prevent circular step dependencies (validated in Planner stage 3)

---

#### **Saga Pattern Integration into Phase 3 Execution**

```text
ORCHESTRATOR PHASE 3 EXECUTION (with Saga Pattern):

┌─────────────────────────────────────────┐
│ Orchestrator receives validated plan    │
│ from Planner                            │
└─────────────────────────────────────────┘
            ↓
┌─────────────────────────────────────────┐
│ SagaCoordinator instantiated            │
│ with plan steps + compensation defs     │
└─────────────────────────────────────────┘
            ↓
    ┌───────────────────────────────────┐
    │ EXECUTE EACH STEP (Sequence)      │
    ├───────────────────────────────────┤
    │ For Step 1 to N:                  │
    │   1. Try forward recovery (retry) │
    │   2. If success → record + log    │
    │   3. If fail → break loop         │
    │   4. Trigger backward recovery    │
    └───────────────────────────────────┘
            ↓
┌─────────────────────────────────────────┐
│ If any step FAILS:                      │
│ RUN COMPENSATIONS (Reverse Order)       │
│ - Step N compensation                   │
│ - Step N-1 compensation                 │
│ - ...                                   │
│ - Step 1 compensation                   │
│ (LIFO stack execution)                  │
└─────────────────────────────────────────┘
            ↓
┌─────────────────────────────────────────┐
│ Return SagaResult to Concierge          │
│ - success: True/False                   │
│ - completed_steps: N                    │
│ - compensations_run: M                  │
│ - user_message: Friendly error (if fail)│
└─────────────────────────────────────────┘
```

**Performance:**

- Successful saga (all steps): ~50-500ms (Phase 3 as designed)
- Failed saga with retry: ~3s (5 retries) + compensation time
- Failed saga with immediate compensation: ~15s (5 steps × 3s)
- **Saga total timeout: 120s** (covers all scenarios)

---

#### **Where Saga Connects in K1 System**

```text
CONCIERGE (Decision Maker)
    ↓ creates task envelope

PLANNER (4-Stage Pipeline)
    ├─ Stage 1-2: Generate plan with steps + compensations
    ├─ Stage 3: Validate (include saga feasibility check)
    └─ Stage 4: Commit → Send to Orchestrator

ORCHESTRATOR (Phase 3)
    ├─ Phase 1-2: Negotiate & select agent
    └─ Phase 3: EXECUTE with SAGA PATTERN
        ├─ SagaCoordinator orchestrates steps
        ├─ Forward recovery: Retry logic (exponential backoff)
        ├─ Backward recovery: Compensation (LIFO stack)
        └─ Timeout enforcement: 4-level hierarchy

K0 BRIDGE (Audit Trail)
    ├─ Receives saga execution logs
    ├─ Persists to SAGA_LOG topic (7-day retention)
    └─ Recovery coordinator detects crashes + resumes

WRITERS (Data Formatters)
    └─ Log saga execution results to memory
```

**Key Integration Points:**

1. **Planner → Orchestrator:** Plan includes step definitions + compensation metadata
2. **Orchestrator → SagaCoordinator:** Passes plan steps to saga for execution
3. **SagaCoordinator → Tool Runner:** Executes tools and captures results
4. **SagaCoordinator → K0 Bridge:** Writes saga logs for persistence + crash recovery
5. **Recovery Coordinator → K0 Bridge:** Scans for crashed sagas, resumes compensation

---

#### **Real-World Example: Book Dinner Workflow**

```python
# Plan (from Planner stage 4)
plan = ValidatedPlan(
    id="plan_001",
    steps=[
        StepDef(
            id="search_restaurants",
            action="search_restaurants",
            tool="search_web",
            params={"cuisine": "italian", "location": "downtown"},
            compensation=None  # Read-only, no compensation
        ),
        StepDef(
            id="book_restaurant",
            action="book_table",
            tool="booking_api",
            params={"restaurant": "Bella Italia", "time": "7pm", "party": 4},
            compensation=ToolCompensation(
                tool_id="cancel_booking",
                params_mapping={"booking_id": "result.booking_id"}
            )
        ),
        StepDef(
            id="add_calendar",
            action="create_event",
            tool="calendar_api",
            params={"title": "Dinner", "time": "7pm"},
            compensation=ToolCompensation(
                tool_id="delete_event",
                params_mapping={"event_id": "result.event_id"}
            )
        ),
        StepDef(
            id="send_notification",
            action="send_notification",
            tool="notification_service",
            params={"type": "booking_confirmed"},
            compensation=None  # Can't unsend, but last step so acceptable
        )
    ]
)

# Execution (Orchestrator Phase 3)
saga_coordinator = SagaCoordinator(k0_bridge)
result = await saga_coordinator.execute_saga(plan, session)

if result.success:
    print("✅ All 4 steps completed successfully")
    # User sees: "Your reservation at Bella Italia is confirmed for 7pm!"

else:
    print(f"❌ Workflow failed at step {result.failed_step_idx}")
    print(f"✅ Ran {result.compensations_run} compensations to clean up")
    print(f"💬 User message: {result.user_message}")
    # Example: "I found Bella Italia (7pm for 4), but couldn't add it to your calendar
    #          because the calendar service was down. The restaurant booking was cancelled
    #          to avoid charges. Try again when the calendar is back."
```

**Performance Metrics:**

- Successful execution: ~600ms (search 50ms + book 300ms + calendar 150ms + notify 100ms)
- Failed at calendar: ~15s (forward recovery 3s + compensations: cancel_booking 3s)
- User informed: Clear error message with booking ID and next steps

---

### **5. ✍️ WRITERS = Data Formatters (Know K0 Schemas)**

**Role:** Convert K1 decisions into K0-compatible formats (Tier 3 Pure Actors)

**What they do:**

- **RECEIVE TASKS** from Planner mailbox (Priority 2: INTERACTIVE)
- **READ SessionState** for context (beliefs, preferences, privacy band)
- **FORMAT DATA** according to K0 table schemas
- **SEND to K0 Bridge** via state_delta_emitter (batched)
- **Never block** response streaming (fully async)

**Three Specialized Writers:**

| Writer | Knows | Example Task |
|--------|-------|--------------|
| **MemoryWriter** | P02, P05, P06 episodic/semantic schemas | "Store episodic memory: 'booked restaurant last night'" |
| **LearningExtractor** | P06 schema, drift signals, learning patterns | "Extract: user preferences improving (EWMA trend)" |
| **SemanticEnricher** | KG schema, entity relationships, concepts | "Link: restaurant → cuisine:italian → location:downtown" |

**Implementation:**

```python
class MemoryWriterAgent(PureActor):
  def handle_task_message(self, message):
    task = message.payload  # e.g., {"type": "store_prospective", ...}

    # Step 1: READ from SessionState
    privacy_band = self.session_state.control.privacy_band
    user_prefs = self.session_state.beliefs.preferences

    # Step 2: KNOW K0 schemas
    if task.type == "store_prospective":
      schema = self.k0_schemas["P05_prospective"]  # Knows exactly what P05 expects
      formatted_data = {
        "trigger_id": task.trigger_id,
        "type": "time",
        "schedule": task.schedule,
        "action": task.action,
        "privacy_band": privacy_band,
        "priority": 5
      }

    # Step 3: BATCH & SEND via K0 Bridge
    self.state_delta_emitter.add_delta(formatted_data)
    # Emitter batches: triggers on 250ms elapsed OR 64KB OR 100 deltas

    # If conditions met:
    batch = self.state_delta_emitter.flush()
    self.k0_bridge.send_command(
      port="P05",
      operation="write",
      deltas=batch,
      lane="fast",  # GREEN band → fast lane <50ms
      idempotency_key="sess_001_plan_abc_step_003",  # Exactly-once
      cognitive_trace_id=message.trace_id
    )
```

---

### **6. 💾 SESSIONSTATE = Shared Working Memory**

**Role:** Ephemeral working memory (in-process, not persisted to K0)

**What it contains:**

```python
session_state = {
  "beliefs": {           # What we know about user
    "preferences": {"cuisine": "italian", "budget": "$50-100"},
    "schedule": {"work_hours": "9-5", "timezone": "PST"},
    "health": {"diet_restrictions": ["vegetarian"], "allergies": []},
    "mood": "happy"
  },

  "control": {          # Current session state
    "privacy_band": "GREEN",  # User data sensitivity level
    "cognitive_trace_id": "trace_xyz",
    "turn_number": 42,
    "conversation_context": [...]
  },

  "persona": {          # How to interact with user
    "formality": "casual",
    "verbosity": "concise",
    "emoji_preference": "moderate"
  },

  "working_goal": {     # Current task in progress
    "goal_id": "goal_001",
    "status": "in_progress",
    "subtasks": [...]
  },

  "recall_hints": {     # Cached K0 lookups
    "recent_restaurants": [...],
    "user_preferences": {...}
  },

  "metadata": {         # Session info
    "session_id": "sess_001",
    "user_id": "user_123",
    "device": "mobile",
    "locale": "en-US"
  }
}
```

**Who reads it:**

- Concierge: Reads beliefs, persona to compose responses
- Planner: Reads control (privacy_band) for validation
- Writers: Read beliefs, control for context-aware formatting
- Orchestrator: Reads working_goal to coordinate execution

**Who writes it:**

- SessionState bootstrap (from API Gateway)
- Turn processor (updates turn_number, working_goal)
- Writers populate recall_hints (cached K0 results)

**Key property:** **NOT persisted to K0.** It's ephemeral working memory. Persistence happens through Writers → K0 Bridge → K0.

---

### **7. 🌉 K0 BRIDGE = Kernel Boundary (Writers → K0)**

**Role:** Serialize and send K1 data to K0 (kernel crossing)

**Direction:** **K1 → K0 (push)** and **K0 → K1 (pull via SSE)**

**How Writers use it:**

```python
# Writer batches deltas from SessionState
state_delta_emitter.add_delta({
  "table": "episodic",
  "operation": "insert",
  "data": {...}
})

# After batching trigger (250ms elapsed, 64KB, or 100 deltas):
batch = state_delta_emitter.flush()

# Send via K0 Bridge
k0_bridge.send_command(
  port="P02",  # MemoryWrite port
  operation="write",
  deltas=batch,
  lane="fast",  # GREEN band → <50ms
  idempotency_key="sess_001_plan_abc_step_003",  # Exactly-once
  cognitive_trace_id=trace_id  # End-to-end tracing
)
```

**Return path (K0 → K1):**

```python
# K0 P05 runs background loop every minute
# When trigger fires (e.g., drink water at 8:00am):
k0_p05.emit_sse_tick({
  "event": "prospective.trigger.fired",
  "trigger_id": "trigger_123",
  "action": "drink_water",
  "confidence": 0.98,
  "cognitive_trace_id": trace_id,
  "sequence_offset": 50  # For replay safety
})

# K1 ProactiveAgent listening on SSE:
event = sse_subscriber.receive()
proactive_agent.handle_tick(event)  # Send notification
sse_subscriber.ack(sequence_offset=50)  # Mark as processed
```

---

## Integration Example: Complete User Story

### Scenario: Remind me to drink water every 4 hours, but not during meetings

```text
T0: USER INPUT
   └─ Chat interface → API Gateway

T0+10ms: CONCIERGE (Tier 1)
   ├─ Receives message
   ├─ LLM classifies: "PROSPECTIVE_MEMORY (task-intent)"
   ├─ Routes to Planner
   └─ Sends task envelope via MAILBOX (Priority 2: INTERACTIVE)

T0+35ms: PLANNER (Tier 2)
   ├─ Stage 1: "Store temporal trigger with meeting context"
   ├─ Stage 2: "MemoryWriterAgent knows P05 + P02"
   ├─ Stage 3: "Check privacy (GREEN ✓), permissions ✓"
   ├─ Stage 4: Send task to MemoryWriterAgent
   └─ Sends task via MAILBOX (Priority 2: INTERACTIVE)

T0+100ms: MEMORYWRITER (Tier 3)
   ├─ RECEIVES task from Planner mailbox
   ├─ READS SessionState:
   │  ├─ beliefs: {"schedule": {...}, "preferences": {...}}
   │  ├─ control: {"privacy_band": "GREEN"}
   │  └─ working_goal: {"goal_id": "goal_001"}
   ├─ KNOWS P05 schema:
   │  ├─ trigger fields: type, schedule, action, context
   │  └─ Must include: privacy_band, priority, idempotency_key
   ├─ FORMATS:
   │  {
   │    "trigger_id": "trigger_456",
   │    "type": "time_with_context",
   │    "schedule": "0 8,12,16,20 * * *",
   │    "action": "drink_water",
   │    "context_filter": "NOT in_meeting",
   │    "privacy_band": "GREEN",
   │    "priority": 5,
   │    "idempotency_key": "sess_001_plan_456_step_003",
   │    "cognitive_trace_id": "trace_xyz"
   │  }
   ├─ Batches via state_delta_emitter
   └─ SENDS to K0 Bridge

T0+250ms: K0 BRIDGE
   └─ Sends HTTP/2 POST to K0 P02 (MemoryWrite port)
       Lane: FAST (<50ms for GREEN band)

T0+300ms: K0 RECEIVES
   └─ Stores in K0::st_sqlite[prospective]

TOMORROW 8:00am: K0 P05 BACKGROUND
   ├─ Checks: Any triggers due now?
   ├─ Finds: trigger_456 (time match ✓)
   ├─ Evaluates context: "Is user in meeting?"
   │  └─ Queries K0::st_sqlite[activity] → "No, user free"
   ├─ EMITS SSE TICK
   └─ K1 SSE stream: {"event": "prospective.trigger.fired", ...}

T+8:00am+20ms: K1 PROACTIVEAGENT (Tier 3)
   ├─ Receives tick on SSE
   ├─ Checks SessionState: User available? (not in focus mode)
   ├─ Sends notification: "💧 Time to drink water! (1/4 goal)"
   └─ Acknowledges: sse_subscriber.ack(offset=50)

USER SEES: 💧 Notification at 8am, 12pm, 4pm, 8pm
   (BUT NOT during meetings, because context_filter said so!)
```

---

## How They All Work Together

```text
1. USER CHAT INTERFACE
   ↓ (user input)

2. CONCIERGE (Decision Maker)
   - Classify: Meta or Task?
   - If task → create envelope
   - Send via MAILBOX (Priority 2)
   ↓

3. PLANNER (Task Generator)
   - 4-stage pipeline: sketch → expand → validate → commit
   - Decide: Route to Orchestrator OR Writer?
   - Send via MAILBOX (Priority 2)
   ↓ (splits into two paths)

   PATH A: Task → ORCHESTRATOR (for complex coordination)
   ├─ Phase 1: Broadcast to capable agents (via CapabilityDirectory)
   ├─ Phase 2: Score bids deterministically
   ├─ Phase 3: Execute with winner
   └─ Result back to Concierge

   PATH B: Write Task → WRITERS (for persistence)
   ├─ MemoryWriter, LearningExtractor, SemanticEnricher
   ├─ READS SessionState for context
   ├─ FORMATS according to K0 schemas
   ├─ Batches via state_delta_emitter
   └─ SENDS via K0 Bridge

4. SESSIONSTATE (Shared Working Memory)
   - Updated by: Turn processor, Writers (recall hints)
   - Read by: Concierge, Planner, Writers, Orchestrator
   - Property: Ephemeral (not persisted)

5. K0 BRIDGE (Kernel Boundary)
   - Writers send: Formatted deltas with idempotency_key
   - K0 returns: Receipt confirmation
   - K0 pushes: SSE ticks when triggers fire
   - K1 ProactiveAgent: Listens and acts

6. K0 (Durable Storage)
   - Stores all deltas in tables (P02, P05, P06, etc.)
   - Runs background loops (P05 checks triggers)
   - Sends proactive ticks via SSE
```

All coordinated by **MAILBOX** (nervous system) with **cognitive_trace_id** (causality) and **idempotency keys** (reliability).

---

## Section 6: SessionState — 6-Section Shared Memory

**Reference ADRs:** [ADR-0017](../architecture/decisions/03-layer2-orchestration/0017-sessionstate-6-section-design/0017.md) (parent), [ADR-0017a-f](../architecture/decisions/03-layer2-orchestration/0017-sessionstate-6-section-design/) (sections), [ADR-0018](../architecture/decisions/03-layer2-orchestration/0018-sessionstate-eviction-strategy.md) (eviction), [ADR-0019](../architecture/decisions/03-layer2-orchestration/0019-sessionstate-serialization.md) (FlatBuffers)

### What It Is

**SessionState** is K1's in-memory working state—pure actor state management for orchestrator coordination (NOT AI-specific). Selected **6-Section Structured Design (9/10)** over 4 alternatives after evaluating session state patterns.

**Why 6 Sections Beat Alternatives:**

- **vs Flat Dictionary (5/10):** Prevents 100+ key sprawl, explicit eviction strategy per section
- **vs Hierarchical Namespace (6/10):** No tree overhead for single-session state
- **vs Object-Oriented (7/10):** 4x faster serialization (FlatBuffers <1ms vs pickle 5-10ms)
- **vs ECS Entity-Component (4/10):** Right-sized for conversation (not 10K+ game entities)

**Design Principles:**

- **Clear boundaries:** 6 sections prevent state sprawl (beliefs, scoreboard, control, persona, multimodal, meta)
- **Eviction-friendly:** Independent LRU per section with priority levels (control=critical, meta=low)
- **Fast serialization:** FlatBuffers schemas enable <1ms delta serialization (ADR-0019)
- **Research-grounded:** Working Memory (Baddeley 1974), Common Ground (Clark 1991), Actor Model

**Location:** K1 Kernel Layer 1 - SessionState Manager (`k1/l4_runtime/session_state/`)

---

### How It Works

**Size Budget: 30-56KB typical, 64KB soft limit** (ADR-0018 3-Tier Eviction)

| Section | Size | Purpose | Eviction | K0 Persist |
|---------|------|---------|----------|------------|
| **1. Beliefs** | 10-20KB | User facts, preferences, context | Medium (LRU) | Yes |
| **2. Scoreboard** | 4-8KB | Common ground, QUD stack, referents | High (LRU) | Yes |
| **3. Control** | 8-12KB | Agent leases, flow state | **NEVER** | No |
| **4. Persona** | 2-4KB | Personality (Big Five), tone, style | Low | Yes |
| **5. Multimodal** | 4-8KB | Audio/vision pointers (NOT raw data) | Medium (FIFO) | Partial |
| **6. Meta** | 2-4KB | Telemetry, metrics, timestamps | **EVICT FIRST** | No |

**Section 1: Beliefs** — User facts (300-600 facts × ~50 bytes), preferences, recent turns (last 5 compressed), active entities, constraints. LRU eviction by `last_used`, never evict user-stated facts (confidence=1.0).

**Section 2: Scoreboard** — Common ground tracker (Clark & Brennan 1991). QUD stack (Roberts 1996), referents for pronoun resolution (Centering Theory), grounding acts (20 max), ambiguities. Salience decay 10%/turn (0.9×), threshold 0.01 for removal.

**Section 3: Control** — Agent leases with timeout (Chubby Lock Service patterns), flow state (3-phase orchestration), flow history (last 5), budget tracker, turn lock. **NEVER EVICTED** (coordinator depends on this). Timeout hierarchy: Lease 30s, Step 30s, Turn 60s, Session 600s (ADR-0008d).

**Section 4: Persona** — Big Five personality (OCEAN), tone (friendly/professional/casual/formal), verbosity (0.0-1.0), humor level, language/locale, custom instructions. LLM prompt injection: formats traits into system prompt.

**Section 5: Multimodal** — Audio buffers (pointers to K0 blob storage), vision embeddings (CLIP 512D), streaming state, voice activity detection, ASR buffer. **Stores pointers only** (raw audio/video in K0 blobs). FIFO eviction: keep last 10 audio chunks, last 5 vision embeddings.

**Section 6: Meta** — Session ID/user ID/device ID, timestamps (created/last_activity/expires), performance counters (turns, tokens, tool calls, cost), averages (TTFT, E2E latency), telemetry (last 10 receipt IDs, trace IDs), privacy band (GREEN/AMBER/RED/BLACK), session tags. **Evict FIRST** under pressure (observability only).

**Performance (P95):**

- Section access: <1ms (0.4ms measured)
- Section update: <1ms (0.6ms measured)
- Delta serialization: <1ms (0.8ms measured)
- Full serialization: <10ms (8.2ms measured)
- Eviction check: <5ms (3.2ms measured)

**Amendment #1 (2025-10-22):** 39 UX Capabilities added 15 fields (+11KB). Section 4 (Persona): 2-4KB → 5-7KB (+3KB for voice continuity, self-reference). Section 5 (Multimodal): 4-8KB → 12-16KB (+8KB for ambient context, multi-party). **New median 72KB** (exceeds 64KB soft limit but within 128KB hard limit, triggers LRU eviction gracefully).

---

### Where It Connects

**Component Integration (Read/Write Patterns):**

| Component | Reads | Writes |
|-----------|-------|--------|
| **Mailbox** | control (turn_lock, agent_leases) | - |
| **Concierge** | beliefs (user_facts), persona (tone) | - |
| **Planner (4-Stage)** | beliefs (entities, context), scoreboard (QUD), persona | beliefs (recent_turns), scoreboard (common_ground) |
| **Orchestrator (3-Phase)** | control (leases, flow), beliefs (constraints) | control (leases, flow), scoreboard |
| **Agent Lifecycle FSM** | control (agent_leases state) | control (state transitions) |
| **Saga Pattern** | control (current_flow phase) | control (compensation steps) |
| **Writers** | beliefs, scoreboard, persona, meta (all sections) | beliefs, meta |
| **K0 Bridge** | ALL sections (serialization) | - |

**Data Flow Example (User: "What's the weather?"):**

1. Mailbox: Receive → no SessionState changes
2. Concierge: Classify intent=weather → Read `beliefs.user_facts["location"]`
3. Planner (Sketch): Generate plan → Write `beliefs.active_entities["weather_query"]`
4. Planner (Expand): Enrich → Write `scoreboard.qud_stack.push("What's weather?")`
5. Orchestrator (Negotiation): Acquire lease → Write `control.agent_leases["weather_agent"]`
6. Orchestrator (Selection): Select tool → Read `beliefs.constraints`
7. Orchestrator (Execution): Call API → no SessionState changes
8. Writers (MemoryWriter): Persist → Read beliefs, scoreboard → Write K0 P02/P05
9. K0 Bridge: Serialize → Read ALL 6 sections → Write K0 WAL

---

### How It's Part of System

**Role in K1 Architecture:**

- **In-Memory Fast Path:** <1ms access (vs K0 5-20ms HTTP/2 roundtrip)
- **Shared State:** All K1 components access SessionState (Mailbox → Concierge → Planner → Orchestrator → Writers)
- **Persistence:** Serializes to K0 WAL via K0 Bridge at checkpoints (turn completion, 60s interval, manual)
- **NOT Direct K0:** SessionState lives in-process K1 (volatile), deltas flow to K0 via Writers

**SessionState vs K0 Storage:**

| Aspect | SessionState (K1) | K0 Storage |
|--------|-------------------|------------|
| **Purpose** | In-memory working state | Long-term persistence |
| **Speed** | <1ms (in-process) | 5-20ms (HTTP/2) |
| **Size** | 64KB soft limit | Unlimited (SQLite WAL) |
| **Durability** | Volatile (lost on crash) | Durable (survive restart) |
| **Eviction** | LRU under pressure | Never evicted |
| **Update** | Frequent (per operation) | Batched (60s, turn completion) |
| **Read** | Random access O(1) | Sequential scans (queries) |

**Serialization to K0 (ADR-0019):**

1. **Trigger:** Turn completion OR 60s interval OR manual checkpoint
2. **Delta Computation:** Field-level diffs only (changed fields, not full sections)
3. **FlatBuffers:** 6 schemas (one per section), <1ms serialization each
4. **K0 Bridge:** HTTP/2 POST to K0 WAL (Port P02: session state snapshots)
5. **Receipt:** K0 returns receipt_id, stored in `meta.k0_receipts` (idempotency)

**Privacy Band Enforcement (ADR-00XX):**

- **GREEN:** Full telemetry, K0 persistence allowed
- **AMBER:** Limited telemetry, encrypted K0 persistence
- **RED:** No telemetry, E2EE K0 persistence, no network egress from beliefs/scoreboard
- **BLACK:** E2EE, air-gapped, no persistence

**Monitoring (Prometheus Metrics):**

- `session_state_size_bytes{section}` — Histogram (buckets: 5K, 10K, 20K, 40K, 64K, 80K)
- `session_state_memory_pressure{session_id}` — Gauge (0=HEALTHY, 1=WARNING, 2=EVICT, 3=CRITICAL)
- `session_state_serialization_duration_ms{operation}` — Histogram (serialize, deserialize)
- `session_state_sections_total{section, operation}` — Counter (create, update, delete)

**Memory Pressure Distribution (1000 concurrent sessions):**

- HEALTHY (<56KB): 920 sessions (92%)
- WARNING (56-64KB): 70 sessions (7%)
- EVICT (64-80KB): 9 sessions (0.9%)
- CRITICAL (>80KB): 1 session (0.1%)

**Conclusion:** SessionState provides fast, structured, eviction-friendly in-memory state for K1 orchestrator with FlatBuffers serialization, privacy band enforcement, and graceful LRU eviction. 99% of sessions stay under 64KB soft limit.

---

## Section 7: Event Bus  K1 Pub/Sub Coordination

### What It Is: K1 Internal Event Bus

**K1 Internal Event Bus provides ephemeral runtime coordination via in-memory pub/sub + Actor Model mailboxes, achieving <2ms latency (vs 40ms K0 SSE), 1000s events/sec throughput, with backpressure management and 100% K1-internal operation (no K0 boundary crossing per ADR-0001).**

**K1 vs K0 Events:**

- **K1 Event Bus:** Ephemeral coordination (task announcements, FSM transitions), <2ms in-memory pub/sub, NO persistence
- **K0 SSE:** Durable events (config, receipts, learning, CRDT, audit), ~10ms HTTP/SSE, persisted to K0 WAL

**Components (ADR-0045a/b/c/d):**

- **Topic Registry:** Hierarchical k1.* namespace (orchestration, planning, agent, tool, barge_in, memory)
- **Topic Routing:** Trie-based O(log n) lookup (<100μs), wildcard subscriptions, capability filtering, >95% cache hit rate
- **Delivery Guarantees:** At-most-once (notifications) vs at-least-once (critical events, retry with exponential backoff 100ms  300ms  900ms)
- **Backpressure:** Watermark monitoring (50% yellow, 80% red), drop-oldest or block-with-timeout (500ms), priority-based dropping, <5% drop rate

### How It Works: 6 Event Topics + 2 Patterns

**6 Core Event Topics:**

1. k1.orchestration.*  Task announcements, agent proposals, selection, execution status (100s events/sec)
2. k1.planning.*  Planning phase transitions (sketch  expand  validate  commit, 10s events/sec)
3. k1.agent.*  Lifecycle FSM transitions (PENDING  WARMING  ACTIVE  IDLE  DRAINING  TERMINATED, 10s events/sec)
4. k1.tool.*  Tool execution status (started, completed, failed, 100s events/sec)
5. k1.barge_in.*  Voice interrupts (detected, handled, 1s events/sec)
6. k1.memory.*  Memory cache operations (eviction, warming, 10s events/sec)

**Communication Patterns:**

- **Broadcast Pub/Sub (1-to-N):** Orchestrator publishes k1.orchestration.task.announced  Event bus fans out to 10-20 agent mailboxes (<2ms)
- **Direct Mailbox (1-to-1):** Agent sends proposal  Orchestrator's proposal queue (MPSC, <1ms)

### Where It Connects: Integration Points

**Integration with K1 Components:**

- **Orchestrator  Agents:** Broadcast task announcements, collect proposals, notify winner (Contract Net Protocol)
- **Planner  Orchestrator:** Publish planning phase transitions, monitor progress asynchronously
- **Agent Supervisor  Agents:** Subscribe to lifecycle events, restart failed agents (supervision tree)
- **Tool Runner  Orchestrator:** Publish tool execution status, track progress asynchronously
- **Barge-In  Agents:** Broadcast voice interrupts, cancel current work (<50ms)
- **SessionState  Writers:** Publish memory eviction events, trigger async persistence to K0

**NOT in K1 Event Bus (Use K0 SSE per ADR-0042/0043):**

Config (k0.config.*), Receipts (k0.receipt.*), Learning (k0.learning.*), CRDT (k0.crdt.*), Audit (k0.audit.*)

### How It's Part of System: Performance + Architecture

**Performance (vs K0 SSE):**

- Pub/Sub: <2ms (vs 40ms K0 SSE) = **20 faster**
- Mailbox: <1ms (vs 40ms K0 SSE) = **40 faster**
- Total Coordination: <10ms (vs 90ms K0 SSE) = **9 faster**
- Throughput: 10,000+ events/sec (vs 100 events/sec K0 SSE) = **100 higher**

**Architecture Correctness (ADR-0001):**

- **K0 (Storage):** Durable events (config, receipts, learning, CRDT, audit), persisted to SQLite WAL
- **K1 (Runtime):** Ephemeral events (orchestration, planning, FSM transitions), NO persistence
- **Result:** Correct K0/K1 separation, no architectural drift, 9 faster coordination

**Actor Model Integration (ADR-0002):**

- Mailbox-only communication (no shared state), MPSC queues (bounded 50 items/agent)
- Backpressure management (block sender if full), supervision tree (restart failed agents)

**Production Metrics (P95):**

- Pub/Sub Latency: 1.8ms (10-20 agents), Mailbox Send: 0.7ms, Routing: 85μs
- Throughput: 1,200 events/sec (typical), 10,000+ events/sec (burst)
- Delivery Success: 99.94% (at-least-once), Drop Rate: 4.6% (with backpressure vs 30% without)

**Conclusion:** K1 Event Bus provides 20 faster coordination through in-memory pub/sub, respects ADR-0001 K0/K1 separation (K0=durable, K1=ephemeral), achieves 1000s events/sec throughput with <2ms latency, implements Actor Model isolation with backpressure management, and supports 6 topic categories for K1 runtime coordination (orchestration, planning, agent, tool, barge_in, memory).
