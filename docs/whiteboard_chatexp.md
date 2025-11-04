# 🧠 Making an LLM Agentic System Feel Like Real Humans

**Date:** November 2, 2025
**Status:** Brainstorming Session
**Context:** K0 (Memory Microkernel) + K1 (Intelligence Microkernel) + 20 Pipelines
**Brainstormers:** [Architecture Team]

---

## 🎯 Core Vision

A conversational AI system that:

- **Learns continuously** about each family member (not just in-session)
- **Forms memories simultaneously** with conversation (parallel dual-pipeline)
- **Grows understanding** across all life domains (health, finance, relationships, activities)
- **Feels like talking to a real person** who remembers, understands context, and adapts
- **Never forgets** important things but gracefully prioritizes what matters

---

## 🏗️ Architecture Foundation: Dual Kernels

### **K0 - Memory Microkernel (Durable, Persistent)**

Handles all persistent memory, durability guarantees, and orchestration:

```
├─ WAL (Write-Ahead Log) → Exactly-once durability, recovery guarantees
├─ 8 Memory Types:
│  ├─ Episodic (moments, conversations, events) — "I had coffee with Mom yesterday"
│  ├─ Semantic (facts, generalizations, knowledge) — "Mom likes coffee meetings"
│  ├─ Procedural (habits, routines, skills) — "Recovery includes 2x weekly PT"
│  ├─ Affect (emotions, significance, salience) — "This memory matters deeply"
│  ├─ Social (relationships, family dynamics) — "Mom-User: caring, daily contact"
│  ├─ Self-Model (personality, values, preferences) — "User: proactive caregiver"
│  ├─ Vector (semantic embeddings for retrieval) — "Recovery ≈ PT ≈ progress"
│  └─ Knowledge Graph (structured relationships, temporal) — "Mom →[sister]→ Alice"
├─ P09 Connectors (8 data sources):
│  ├─ Health (fitness, medical, wellness, PT schedules)
│  ├─ Finance (spending, budgets, pharmacy costs, insurance)
│  ├─ Calendar (events, commitments, scheduling)
│  ├─ Contacts/Social (relationships, interactions, presence)
│  ├─ Work (schedule, projects, priorities)
│  ├─ Activity (steps, sleep, movement)
│  ├─ Weather (location, planning context)
│  └─ Travel (trips, visits, presence)
├─ 20 Pipelines (P01-P20) for specialized processing (see below)
└─ P07 Multi-device Sync (E2EE, CRDT, family coordination)
```

### **K1 - Intelligence Microkernel (Real-time, Responsive)**

Handles real-time reasoning, agent coordination, and user interaction:

```
├─ Agent Fabric (Actor Model lifecycle: PENDING → WARMING → ACTIVE → IDLE → DRAINING → TERMINATED)
├─ Orchestrator Core (3-phase: Negotiation → Selection → Execution)
├─ Planner Agent (4-stage reasoning: Sketch → Expand → Validate → Commit)
├─ SessionState (6-section working memory: beliefs, scoreboard, control, persona, multimodal, meta)
├─ Model Hub (LLM routing, inference, KV cache management, placement optimization)
└─ Tool Runner (safe code/API execution via MCP/WASM sandboxing)
```

---

## 🚀 20 K0 Pipelines: The Memory Processing Backbone

Each pipeline is a **specialized processor** handling different aspects of memory management. They run in parallel, coordinated through the K0 WAL and event bus.

### **Group 1: Memory Formation & Retrieval (P01-P02)**

**P01 Recall/Read** — Query & retrieve existing memories

- Input: User query "What does Mom like?"
- Process: Search across all 8 memory types + KG
- Output: "Mom likes coffee meetings, visits quarterly, concerned about health"
- Used by: K1 for context enrichment, response generation

**P02 Write/Ingest** — Record new memories (hippocampal encoding)

- Input: "I had coffee with Mom, she's recovering well"
- Process: Parse entities, extract facts, store episodic
- Output: Episodic memory + triggering P03/P06/P19
- Used by: Every conversation, continuously adding to memory

---

### **Group 2: Memory Consolidation & Learning (P03, P06)**

**P03 Consolidation/Forgetting** — Sleep-like memory processing

- Trigger: Nightly (2-5AM) or after memory burst (>1000 entries)
- Process:
  1. **Hippocampal Replay** — Strengthen important patterns
  2. **Episodic → Semantic** — "3 coffee visits" → "Mom values connection"
  3. **Knowledge Graph Evolution** — Discover relationships, temporal patterns
  4. **Synaptic Pruning** — Remove noise, archive old details
  5. **Dream-Like Exploration** — Creative insights, counterfactuals
- Output: Enriched semantic knowledge, enhanced KG, proactive suggestions
- Real-world example: "After week's data, system realizes: recovery plateau normal at 6 weeks"

**P06 Learning/Neuromod** — Adaptive feedback & parameter updates

- Input: User feedback ("That suggestion was perfect!")
- Process: Extract learning signal, validate safety, update user model
- Output: Adaptive preferences, behavior refinement
- Guard: "Advisory-only" — K1 suggests, K0 validates, executes
- No drift: Detects when learning is failing and rolls back

---

### **Group 3: Coordination & Synchronization (P05, P07)**

**P05 Prospective/Triggers** — Future-oriented memories & scheduling

- Input: "Mom's PT is Monday 10am, remind me"
- Process: Schedule trigger, create prospective memory, link to goals
- Output: Proactive notifications at right time
- Example: Suggests "Alice visiting tomorrow, prepare house?" Saturday morning

**P07 Sync/CRDT** — Multi-device coordination

- Input: Update on phone "Mom's PT done", sync to laptop/watch
- Process: CRDT merge, conflict resolution, E2EE synchronization
- Output: Consistent family memory across all devices
- Enables: Any device becomes potential update source (health app, calendar)

---

### **Group 4: Semantic Processing (P08)**

**P08 Embedding Lifecycle** — Vector generation & semantic indexing

- Input: Episodic memories → vectorization
- Process: Generate semantic embeddings, maintain similarity index
- Output: Fast semantic search, analogical reasoning
- Example: "Is Mom's recovery like Uncle Bob's?" (semantic comparison)

---

### **Group 5: Data Ingestion (P09)**

**P09 Connector Ingestion** — External app data integration

- Input: Health app: "PT scheduled Monday", Finance: "Pharmacy $47.50"
- Process: Normalize, enrich, link to existing memories
- Output: Unified cross-domain context
- Magic: "Mom recovering + PT scheduled + sister visiting = important moment"
- Sources: Health, Finance, Calendar, Contacts, Work, Activity, Weather, Travel

---

### **Group 6: Privacy & Compliance (P10, P11, P12)**

**P10 PII/Minimization** — Privacy enforcement & redaction

- Input: Storing "Mom's medical record + SSN + address"
- Process: Detect sensitive data, apply privacy band rules
- Output: PII redacted/encrypted, audit trail created
- Enforced: GREEN/AMBER/RED privacy bands apply to storage

**P11 DSAR/GDPR** — Right-to-access, right-to-erasure

- Input: "Export all my data" or "Delete conversations with Alice"
- Process: Locate across all pipelines, export/delete consistently
- Output: Compliance proof, audit trail
- Enforced: 30-day GDPR compliance requirements

**P12 Device/E2EE** — Encryption & key management

- Input: Multi-device sync with encryption
- Process: Manage E2EE keys, encrypt at rest, secure transmission
- Output: Only device owner can read sensitive data
- Enforced: Even K0 can't decrypt RED-band data (user has key)

---

### **Group 7: Data Organization (P13, P14, P15)**

**P13 Index Rebuild** — Search index maintenance

- Input: Periodic rebuild trigger
- Process: Reindex episodic + semantic + KG
- Output: Optimized search performance
- Result: P01 queries remain sub-millisecond

**P14 Near-Duplicate/Canon** — Deduplication & canonicalization

- Input: "Mom" vs "Mother" vs "Mary" in memory
- Process: Identify duplicates, canonicalize references
- Output: Single, consistent entity representation
- Result: "Mom" always refers to same person across 8 memory types

**P15 Rollups/Summaries** — Aggregation & compression

- Input: "Mom's PT: 4 sessions, improved, soreness decreasing"
- Process: Create monthly rollup, compress old details, archive
- Output: Lean summaries, detailed history preserved but compressed
- Result: Memory stays efficient even after years of interaction

---

### **Group 8: Experimentation & Governance (P16, P17, P18)**

**P16 Feature Flags/A-B** — Experimentation framework

- Input: "Test new proactive suggestion algorithm"
- Process: A/B split users, measure outcomes
- Output: Data-driven feature rollout decisions
- Example: "Proactive suggestions +30% satisfaction, roll out"

**P17 QoS/Cost Governance** — Resource management & budgets

- Input: "Mom's health data: high priority, unlimited budget"
- Process: Allocate resources, enforce budgets, prioritize processing
- Output: Fair resource distribution, graceful degradation
- Result: Important data processed first, non-critical data deferred

**P18 Safety/Abuse** — Content moderation & detection

- Input: Potential harmful content or safety violation
- Process: Safety filters, abuse detection, policy enforcement
- Output: Flagged unsafe content, audit trail
- Guard: "System won't suggest unsafe actions"

---

### **Group 9: Personalization & Habits (P19, P20)**

**P19 Personalization/Reco** — User modeling & contextual adaptation

- Input: User behavior, explicit preferences, family dynamics
- Process: Build user model (goals, values, communication style)
- Output: Personalized context for every interaction
- Examples:
  - "User prefers proactive suggestions" → more initiative
  - "User stressed about finances" → cost-aware recommendations
  - "Family values health first" → prioritize health queries

**P20 Procedure/Habits** — Skill storage & habit formation

- Input: "Recovery includes PT 2x/week + rest + check-ins"
- Process: Store procedural memory, reinforce habits
- Output: Automated routines, skill reuse
- Result: "User learns: recovery success = PT consistency"

---

## 🔄 Dual Memory Sources: Conversation + Connectors

### **Memory Source 1: User Conversation Stream**

```
User: "I had coffee with Mom yesterday, she's recovering from surgery"
        ↓
K1 Processing:
  • NLP: Extract entities (Mom, surgery, recovery, coffee)
  • Intent: Memory formation + social context + health tracking
  • Emotion: Caring, concerned
        ↓
K0 Pipeline Cascade (PARALLEL):
  P02 (Write): Stores episodic "2025-11-02: Coffee with Mom (post-surgery)"
  P06 (Learning): Learns "User initiates after health events"
  P19 (Personalization): Updates "Mom is primary concern (salience: ++)"
  P08 (Embedding): Creates vector "coffee ≈ connection ≈ recovery support"
  P07 (Sync): Shares across all family devices if permissioned
        ↓
SessionState Updated (6-section):
  1. beliefs: "Mom recovering, surgery happened"
  2. scoreboard: "Mom is current topic, health focus active"
  3. control: "Agent addressing family health concern"
  4. persona: "User is caring, proactive, health-conscious"
  5. multimodal: [empty]
  6. meta: Timestamps, interaction count
        ↓
Later (P03 Consolidation):
  • Discovers: "3 coffee visits in week → Mom values connection during recovery"
  • Creates semantic: "User-Mom: strong, daily-contact pattern during health crisis"
  • Updates KG: "Mom --[visited_by]--> User (frequency: increased)"
```

### **Memory Source 2: App Connectors (P09)**

```
Health App Event: "2025-11-04 PT Session scheduled: Mom, Mon 10:00-11:00"
        ↓
K0 P09 Connector Ingestion:
  • Creates episodic: "PT Monday 10:00, scheduled for recovery"
  • Updates semantic: "PT is recovery routine (2x weekly expected)"
  • Updates KG: "Mom --[therapy]--> PT (2x weekly, ongoing)"
  • Triggers P05: Schedule reminder "PT tomorrow?"

Finance App Event: "Pharmacy charge: $47.50 (Mom's prescription)"
        ↓
K0 P09 Ingestion:
  • Episodic: "Healthcare expense for recovery"
  • Semantic: "Recovery has ongoing costs"
  • KG link: "Mom", "health", "finances" interconnected
  • P19 (Personalization): "Healthcare spending is significant factor"

Calendar App Event: "Sister Alice visiting Nov 8-10"
        ↓
K0 P09 Ingestion:
  • Episodic: "Alice visit scheduled, 3 days"
  • Social KG: "Alice --[sister]--> User", "Alice --[visiting]--> Mom"
  • P05 (Prospective): "Reminder: Prepare for sister visit + family time"
  • P19 (Personalization): "Family coordination matters to user"

Activity App Event: "Mom: 2000 steps today, trending up from 500 day 1 of recovery"
        ↓
K0 P09 Ingestion:
  • Episodic: "Movement trend positive"
  • Semantic: "Recovery trajectory: strong progress"
  • KG: "Mom --[recovery_progress]--> mobility_improving"
  • P06 (Learning): "Physical progress indicator of recovery success"
```

### **Unified Self-Model (Emerges from Both Sources)**

```
Family Member: "Mom"
├─ Health:
│  ├─ current_status: "recovering from surgery (Oct 15)"
│  ├─ recovery_timeline: "3-6 months, on track for 4-5"
│  ├─ pt_schedule: "2x weekly (Mon 10am, Fri 2pm)"
│  ├─ medication: "Post-operative, $47.50/week pharmacy"
│  ├─ mobility_trend: "2000 steps day 20, improving"
│  └─ pain_status: "Soreness after PT, resolves day 2"
├─ Relationships:
│  ├─ with_user: "close, daily contact, user is primary caregiver"
│  ├─ with_alice: "sister, visiting during recovery"
│  ├─ support_network: "family-coordinated, high involvement"
├─ Communication_Preferences:
│  ├─ preferred_style: "coffee meetings (in-person preferred)"
│  ├─ frequency_baseline: "monthly visits"
│  ├─ frequency_during_crisis: "daily or more"
│  └─ response_style: "grateful, values presence"
├─ Learned_Patterns:
│  ├─ user_initiated_checkins: "after medical events"
│  ├─ peak_concern_times: "post-appointment, post-PT"
│  ├─ preferred_support: "presence + practical help"
│  └─ celebration_importance: "milestones matter psychologically"
└─ Temporal_Context:
   ├─ surgery_date: "2025-10-15"
   ├─ recovery_duration_so_far: "20 days"
   ├─ estimated_completion: "2025-12-20 ± 2 weeks"
   └─ next_key_dates: ["2025-11-04 PT", "2025-11-08 Alice visit"]
```

---

## ⚡ Simultaneous Memory Formation: The Magic

**Key Insight:** Memory formation happens DURING conversation (parallel), not after.

```
Timeline: User Message Arrives

T0: Message received: "I had coffee with Mom yesterday"
    ↓
T0+0ms: K1 Parsing (Async thread)
        • Extract entities, intent, emotion
        • Update SessionState (all 6 sections)
        • Trigger K0 for context
        ↓
T0+1ms: K0 Memory Formation (PARALLEL, P02+P06+P19+P08+P07)
        • P02 Write: Store episodic "coffee with Mom"
        • P06 Learning: Extract learning signal
        • P19 Personalization: Update salience scores
        • P08 Embedding: Generate vector
        • P07 Sync: Queue for device sync
        • All happening in background, non-blocking
        ↓
T0+50ms: K1 Response Generation
         • Query K0 P01 for recovery context
         • LLM reasoning: "Mom is in week 3 recovery"
         • Generate response: "That's wonderful..."
         ↓
T0+100ms: P03 Consolidation Trigger (if needed)
          • Check: Is memory > 1000 entries?
          • If yes: Schedule consolidation run
          • Run during next idle period
          ↓
T0+150ms: Response Streamed to User
          "That's wonderful to hear! How is she feeling physically?
           I know the first few weeks can be tough."
          ↓
T0+200ms: User reading response while...
          ↓
T0+500ms: P06 Learning Updates (Background)
          • Extract learning signal: "User values presence-based support"
          • Update model: "Recovery quality depends on family connection"
          • Persist to K0
          ↓
T0+1000ms: P08 Embedding Index Updated
           • Vector indices refreshed
           • Similarity search now reflects latest conversation
           • Ready for next P01 query
           ↓
T0+5000ms: P07 Sync Completes (if multi-device)
           • Phone → Laptop → Watch synchronized
           • Family can see same memory context
           ↓
T0+10000ms: Evening - P03 Consolidation Runs
            • If >1000 new memories today
            • Or scheduled nightly window
            • Extracts patterns, creates semantic knowledge
            • Tomorrow, responses will be even better informed

Result:
  ✨ User got responsive conversation (T0+150ms)
  ✨ Memory formed in parallel (T0+1-500ms)
  ✨ Learning extracted (T0+500ms)
  ✨ Multi-device sync complete (T0+5000ms)
  ✨ Deep consolidation ready for next session (T0+10000ms)
```

**Why This Feels "Real":**

- System responsive but thoughtful
- Isn't slowed down by memory work
- Context improves over time
- Feels like someone actively listening AND learning

---

## 🧠 Knowledge Graph for Structured Relationships

**Problem with traditional LLMs:**

```
Q: "Who is Mom related to?"
A: Searches text → "Mom...sister Alice...lives with user..."
Result: Fuzzy inference, error-prone, can't handle complex queries
```

**Real Human Understanding via K0::st_kg:**

```
Knowledge Graph (K0 st_kg driver):

Nodes:
  ├─ Person("Mom" / entity_id: p_001)
  │  └─ attributes: {name: "Mary", age: 67, location: "Seattle"}
  ├─ Person("User" / entity_id: p_002)
  │  └─ attributes: {name: "Alice", age: 32, role: "primary_caregiver"}
  ├─ Person("Sister" / entity_id: p_003)
  │  └─ attributes: {name: "Alice", age: 35, location: "Portland"}
  ├─ Place("Seattle" / entity_id: place_001)
  ├─ Event("Surgery" / entity_id: evt_001)
  │  └─ attributes: {date: "2025-10-15", type: "orthopedic", status: "successful"}
  ├─ Activity("PhysicalTherapy" / entity_id: act_001)
  │  └─ attributes: {frequency: "2x weekly", duration: "12 weeks", progress: "positive"}
  └─ Concept("Recovery" / entity_id: concept_001)

Edges (with temporal validity):
  ├─ p_001 --[sister_of]--> p_003
  │  └─ {confidence: 1.0, valid_from: 1980-06-15, valid_to: null}
  ├─ p_002 --[daughter_of]--> p_001
  │  └─ {confidence: 1.0, valid_from: 1990-08-20, valid_to: null}
  ├─ p_001 --[lives_in]--> place_001
  │  └─ {confidence: 0.95, valid_from: 2010-03-01, valid_to: null}
  ├─ p_001 --[undergoing]--> act_001
  │  └─ {valid_from: 2025-10-20, valid_to: estimated_2025-12-20}
  ├─ p_001 --[affected_by]--> evt_001
  │  └─ {date: 2025-10-15, causality: "direct"}
  ├─ p_003 --[visiting]--> p_001
  │  └─ {valid_from: 2025-11-08, valid_to: 2025-11-10, purpose: "recovery_support"}
  ├─ p_002 --[concerned_about]--> concept_001
  │  └─ {valid_from: 2025-10-15, emotion: "high_priority"}
  ├─ concept_001 --[supported_by]--> p_002
  │  └─ {role: "primary_caregiver", actions: ["daily_checkins", "coordinate_pt"]}
  └─ act_001 --[part_of]--> concept_001
     └─ {role: "therapeutic_intervention"}

Temporal Queries (P03 Consolidation discovers these patterns):
  Q: "Who had medical events in Oct 2025?"
  A: [p_001(Mom): evt_001(Surgery, Oct 15)]

  Q: "What family is visiting next week?"
  A: [p_003(Alice): visiting p_001(Mom), Nov 8-10, purpose: recovery support]

  Q: "What activities is Mom doing?"
  A: [act_001(PT): 2x weekly, ongoing, recovery_progress: positive]

  Q: "Recovery timeline?"
  A: [Started: Oct 15 (surgery) → Oct 20 (PT start) → Dec 20 (estimated end)]

  Q: "Who is supporting Mom's recovery?"
  A: [p_002(User/Alice): primary_caregiver
     p_003(Sister/Alice): visiting for support
     Medical team: PT, physician oversight]

  Q: "What if Alice's visit extended 1 week?"
  A: KG enables: "More family presence → predicted recovery improvement"
     (Causal reasoning possible with structured KG)
```

**Why Structured KG Matters:**

- Family relationships are explicit, not inferred
- Temporal reasoning (future events, timelines)
- Cross-domain queries (health + family + finances)
- Causal inference ("If X, then Y likely")
- Relationship complexity ("Transitive: if Alice visits Mom, and User loves Mom, then...")

---

## 🌙 P03 Consolidation: Sleep-Like Memory Processing

**The heart of "real human" feeling:**

```
TRIGGER: Nightly (2-5AM) or after 1000+ new memories

┌──────────────────────────────────────────────────────────┐
│  PHASE 1: HIPPOCAMPAL REPLAY (Pattern Strengthening)     │
└──────────────────────────────────────────────────────────┘

Input (Raw episodic from day):
  "2025-11-02 09:00: Coffee with Mom"
  "2025-11-02 10:30: Mom mentioned PT Monday"
  "2025-11-03 10:15: Mom completed PT"
  "2025-11-03 11:45: Mom mentioned soreness"
  "2025-11-04 12:00: Mom feeling better"

Process: Identify salient patterns
  • Salience analysis: "Mom's recovery" = high (emotional + medical)
  • Replay: Strengthen these traces 5x
  • Create associations: "PT → soreness (temporary) → improvement"
  • Emotion tagging: "Mom's well-being is USER's priority"

Output (After consolidation):
  Strengthened pattern: "Mom recovery trajectory: challenging → improving"
  Association: PT is integral to recovery success
  Emotional grounding: "This matters to user profoundly"


┌──────────────────────────────────────────────────────────┐
│  PHASE 2: EPISODIC → SEMANTIC (Generalization)           │
└──────────────────────────────────────────────────────────┘

Input (Episodic instances):
  • "3 coffee meetings with Mom this week"
  • "Mom initiated calls 5x"
  • "User missed 0 check-ins"
  • "Mom expressed gratitude 4x"

Process: Extract generalizations
  • "Mom values connection" (pattern from 3 meetings)
  • "User is primary support" (from check-in frequency)
  • "Recovery requires emotional + physical support" (inferred)
  • "Family coordination increases recovery success" (learned)

Output (New semantic memories):
  • "Mom prefers frequent, in-person connection during recovery"
  • "User derives satisfaction from caregiving"
  • "Coffee is Mom's preferred communication style"


┌──────────────────────────────────────────────────────────┐
│  PHASE 3: KNOWLEDGE GRAPH EVOLUTION                       │
└──────────────────────────────────────────────────────────┘

Input (Episodic + semantic + connector data):
  User interactions: "Initiates check-ins"
  PT app: "2x weekly, positive progress"
  Finance: "$47.50/week pharmacy cost"
  Social: "Sister visiting during recovery"

Process: Discover relationships & causality
  • Relationship discovery: "User-Mom support intensity = recovery quality"
  • Temporal patterns: "PT schedule blocks other activities"
  • Causality: "Family presence → emotional resilience → recovery success"
  • Risk factors: "Cost awareness might limit rehab if not managed"

Output (Enhanced KG):
  New edges added:
    • p_002 --[emotional_support_for]--> p_001 (weight: high)
    • concept_recovery --[requires]--> emotional_presence
    • pt_schedule --[competes_with]--> family_time (identify conflict)
    • financial_constraints --[may_affect]--> treatment_adherence


┌──────────────────────────────────────────────────────────┐
│  PHASE 4: SYNAPTIC HOMEOSTASIS (Pruning & Compression)    │
└──────────────────────────────────────────────────────────┘

Input: Memory traces marked for evaluation
  "Checked time at 3:42pm" (random detail)
  "PT session lasted 47 minutes" (microdetail)
  "Mom complained about soreness" (repeated theme)
  "User scheduled 5 reminders" (procedural noise)

Process: Prune & compress
  • Remove noise: "Checked time" → not salient, delete
  • Compress temporal: "4 PT sessions" → "PT routine established"
  • Keep pattern: "Soreness → improvement cycle" → retain
  • Archive: Move old episodic to cold storage, keep summary

Output (Lean memory):
  ✅ Keep: "PT increases soreness short-term, improves medium-term"
  ❌ Delete: "Random details (time checks, microdetails)"
  📦 Archive: Old episodic → summary form


┌──────────────────────────────────────────────────────────┐
│  PHASE 5: DREAM-LIKE EXPLORATION (Creative Insight)      │
└──────────────────────────────────────────────────────────┘

Input (KG + consolidated patterns + user model):
  KG paths: "Mom --[sister]--> Alice", "Alice --[visiting]..."
  Pattern: "Mom improves with social connection"
  Learning: "User initiates after medical events"

Process: Generate counterfactuals & insights
  • "What if Alice stayed 2 weeks instead of 3 days?"
    → Predicted: "Emotional support could reduce pain scores"
  • "What if we missed PT for a week?"
    → Predicted: "Recovery setback likely, confidence drop probable"
  • "When should we celebrate completion?"
    → Insight: "Mark milestone when Mom walks without aid (week 10 estimated)"
  • "Could we automate reminder system?"
    → Insight: "Yes, but human connection (calls) more valuable"

Output (Anticipatory insights):
  🎯 Suggestion 1: "Alice's visit perfectly timed for recovery boost"
  🎯 Suggestion 2: "Plan celebration milestone around week 10 PT completion"
  🎯 Suggestion 3: "Risk: watch for motivation dip week 6-7 (common) — proactive support"
  🎯 Suggestion 4: "Opportunity: family could learn PT exercises to help at home"
```

**After Consolidation Completes:**

```
System State:
  ✨ Went from reactive memory to proactive wisdom
  ✨ Discovered patterns human might not notice
  ✨ Temporal reasoning now includes recovery arcs, not just facts
  ✨ Ready to make significantly better suggestions next conversation

Example (Next day):
  User: "How's Mom doing?"
  K1 Response: (informed by P03 consolidation)
    "Mom is in week 3 recovery. Her PT is progressing well — that soreness
     after sessions is normal and trending down. I've noticed her emotional
     resilience really improves after your visits. Alice's visit next week
     could be a nice boost during this recovery plateau we're entering.
     How are YOU holding up? Caregiving is demanding."

  ✨ Feels like doctor who's been watching the case continuously
  ✨ Anticipates next week's emotional needs
  ✨ Recognizes caregiver fatigue
```

---

## 📚 P06 Learning Loop & Drift Detection

System learns from interactions but with safety guardrails:

```
Session: User says "That proactive suggestion was perfect!"
         ↓
K1 Learning Loop (Advisory-Only):
  • Collects signal: Positive feedback on proactive suggestion
  • Analyzes pattern: "User appreciates initiative on family coordination"
  • Recommends: "Increase proactive suggestions on social coordination"
         ↓
K0 P06 Validation & Persistence (Authoritative):
  • Receives advisory from K1: "Increase social suggestions 20%"
  • Validates against policy: "Is this safe? Aligned with user values?"
  • Cross-checks: "Is user actually benefiting or just being polite?"
  • Drift detection: "Not showing signs of suggestion fatigue? ✓"
  • Persists: Updates K0::st_sqlite[learning_traces]
  • Creates receipt: "Learning: social_coordination_preference_+20%"
  • Emits event: learning.feedback.social_coordination (with trace_id)
         ↓
Next Conversation (Week later):
  ✨ System 20% more proactive with family coordination
  ✨ Suggests family meeting timing, sibling coordination, etc.
  ✨ But can rollback immediately if feedback turns negative

Drift Detection Example:
  If system starts suggesting unsolicited social interventions:
  • K1 detects: "User ignoring our family suggestions 70% of time"
  • Advisory to K0: "Rollback social initiative to baseline"
  • K0 P06 executes immediately: "Reset social suggestions to baseline"
  • Adds audit log: "Drift detected, rolled back, user restored to original"
  • Never gets stuck in bad loop
```

---

## 🎭 Dynamic Agent Creation (ADR-0086 + K1 Orchestration)

Smart specialization: System creates specialized agents as needed.

```
User: "I need to coordinate Mom's PT schedule with her medications.
       The timing is tricky because PT makes her tired."
        ↓
K1 Orchestrator evaluates task:
  • Task complexity: High (multiple constraints)
  • Specialized knowledge needed: Yes (healthcare + scheduling)
  • Current agents sufficient: No
  • Action: Dynamically create specialist agent
        ↓
Agent Factory creates:
  Agent("HealthcareCoordinator", session_id="sess_123")
    ├─ agent_id: "agent-sess-123-1729163400000-000001"
    ├─ capabilities: [
    │    "calendar_integration" (read-write Mom's schedule),
    │    "healthcare_knowledge" (PT guidelines, recovery),
    │    "medication_tracking" (drug interactions, timing),
    │    "constraint_solver" (find non-conflicting times)
    │  ]
    ├─ persona: {
    │    domain: "healthcare",
    │    empathy_level: "high",
    │    expertise: "orthopedic recovery",
    │    communication_style: "practical + supportive"
    │  }
    ├─ memory_budget: 64MB (temporary)
    ├─ context: Gets Mom's full recovery state from K0 P01 Query
    │  • Recovery stage: Week 3
    │  • PT schedule: Mon 10am, Fri 2pm
    │  • Medications: Post-op pain meds 3x/day, anti-inflammatory
    │  • Fatigue pattern: Peaks 2 hours post-PT
    │  • User constraint: Wants to attend PT when possible
    │  • Financial: Cost-conscious, wants efficient timing
    └─ duration: Active for this task, auto-terminates after
        ↓
Agent specializes on task:
  • "PT at 10am → Mom fatigued until 12pm"
  • "Pain meds at 8am, noon, 6pm (interference with PT?)"
  • "Option 1: Take meds after PT (less effective during session but tolerates)"
  • "Option 2: Reschedule PT to 2pm (conflicts with Friday PT)"
  • "Option 3: Adjust med timing to 7am, 3pm, 9pm (allows PT pre-medicated)"
  • "Recommendation: Option 3 safest + maintains PT effectiveness"
        ↓
Communicates with user:
  "I've analyzed Mom's PT schedule with medication timing. Here's what I found:

   Current issue: Pain meds peak 2 hours post-administration. PT at 10am
   conflicts with the 8am med dosing window.

   Recommendation: Shift medication timing to 7am, 3pm, 9pm.
   This keeps Mom pre-medicated for PT (pain management) without
   making her drowsy. Post-PT soreness will have medication support.

   PT effectiveness should improve, and fatigue should be lower.
   I've created a new med schedule and updated Mom's calendar.

   Next steps: Show this to Mom's physician for approval before changing."
        ↓
Agent terminates, specialized context released:
  • Memory freed: 64MB returned to pool
  • Knowledge preserved: Result stored in K0 semantic memory
  • Learning recorded: "Healthcare coordination successful" → P06
  • Traces maintained: Audit trail in receipts
        ↓
Result: User got specialized expertise without waiting for human

✨ Next similar task: Faster (learned pattern) but new agent created if needed
✨ If user frequently coordinates healthcare: Could make agent persistent
```

---

## 🎨 Human-Like Interaction Arc: Week-by-Week

### **Week 1: Crisis Event Triggers**

```
Monday:
  User: "Mom's having surgery tomorrow, she's really nervous"

  K1 Response: "That's a lot to manage. Tell me about the surgery?"
  K0 P02: Records episodic "Surgery planned, Mom anxious"
  K0 P19: Updates "Mom: high importance + current crisis"

  K1 SessionState: Creates recovery_support context

Tuesday:
  User: "Surgery went well! She's in recovery room now"

  K0 P02: Episodic "Surgery completed, positive outcome"
  K0 P06: Learns "User celebrates good medical outcomes"
  K0 P19: Updates "Mom: acute recovery phase"

  K1 Response: "I'm so glad it went well. Let's set up tracking
              for her recovery. When does she go home?"
```

### **Week 2: Consolidation Begins**

```
Wednesday (P03 Consolidation runs overnight):

  K0 P03 discoveries:
    • Mom is primary concern (appeared 8x in past 48 hours)
    • Recovery is emotionally significant (tagged high salience)
    • User initiates check-ins after health events (pattern)
    • PT is part of routine (appears in calendar + health app)
    • Family coordination is valued (Alice mentioned, visit being planned)

  Creates semantic memories:
    • "Mom values connection during recovery"
    • "User is proactive caregiver"
    • "Recovery includes PT + rest + family support"

  Updates KG:
    • Mom --[surgery_date]--> 2025-10-15
    • Mom --[recovery_support]--> User + PT + Alice
    • Recovery --[duration]--> 3-6 months (estimated 4-5 weeks PT)
    • Surgery --[outcome]--> positive

  P06 Learning:
    • "User cares deeply about Mom's health outcomes"
    • "Proactive support appreciated"
    • "Family coordination matters"

Friday:
  User: "Mom's doing better, started PT yesterday"

  K0 Response (now informed by consolidation):
    • Knows recovery arc: Normal to have ups/downs
    • Knows PT is critical: "How is she handling PT?"
    • Knows user is primary support: Asks about USER's wellbeing

  K1 Response: "That's wonderful! Week 1 PT is tough. The soreness
               is normal. How's she sleeping? How are you holding up?"

  ✨ Already feels more informed, more human
```

### **Week 3: Contextual Awareness Emerges**

```
Friday (1 week later):
  User: "How's Mom doing?"

  K0 P01 Query returns:
    • Mom: PT 2x weekly, recovering well
    • Recovery trajectory: On track for 4-month timeline
    • Recent activities: Coffee with user 3x this week, Alice visiting next week
    • Costs: $47/week pharmacy (tracked), PT progressing
    • Emotional state: Positive, grateful

  K1 Response (sophisticated, informed):
    "Mom's recovery is progressing really well. Week 3 PT is usually when
     the breakthrough happens — the body starts adapting. I've noticed
     she's been in much better spirits with your coffee visits.

     Alice visiting next week could give everyone a nice morale boost
     during this middle phase. Has she tried the modified exercises yet?"

  ✨ Feels like someone who's been following the case
```

### **Week 4: Proactive Suggestions**

```
Thursday morning:
  User: (no message)

  System (proactive):
    "Just a thought — Alice arrives tomorrow. Mom might appreciate help
     preparing the house. Should we create a checklist? Things like:
     • Clear pathways for walker/crutches
     • Stock bathroom with essentials
     • Arrange pillows/comfort items
     • Meal prep for visiting week

     Would you like me to send Mom a gentle message about this too?"

  ✨ Feels like someone thinking ahead on your behalf
  ✨ Personalized to recovery stage

  User: "Yes! Great idea."

  K0 P05 (Prospective):
    • Creates reminders for each prep item
    • Schedules check-in after Alice arrives (learns what helps)

  K0 P06:
    • "User appreciates proactive family coordination"
    • Increases initiative slightly for future family events
```

### **Week 6: Deep Understanding**

```
Monday:
  User: "PT feels less effective, Mom's frustrated"

  K1 queries K0:
  K0 returns from P03 consolidation:
    • Week 6 recovery: Typical plateau period (neurologically normal)
    • Fatigue signals: Expected at this point
    • Psychological factor: Common frustration at "slow progress"
    • Historical pattern: Uncle Bob had same at week 5-6, recovered

  K1 Response (deeply informed):
    "Recovery plateau at week 6 is completely normal — the body's adapting
     to PT demands. The nervous system is rewiring, not showing obvious gains.
     Frustration is actually a sign she's engaged with recovery!

     This is where mental support matters most. Some ideas:
     • Shift focus to process (she's doing PT) not just outcome (healing speed)
     • Measure different metrics (endurance vs pain)
     • Celebrate small wins (walked longer today)
     • Maybe add family activity to break routine (short outing?)

     The good news: This phase usually resolves week 7-8 with visible breakthroughs."

  ✨ Feels like therapist + doctor + friend combined
  ✨ Anticipates psychological needs + physical

  User: "That helps so much, thank you"

  K0 P06: Learns "User wants informed, recovery-specific guidance"
  K0 P03 (next night): Consolidates "PT plateaus common, reassurance effective"
```

### **Week 10: System Has Genuine Memory**

```
User: "Mom wants to know how much longer until full recovery"

K0 P01 Query returns comprehensive recovery model:
  • Surgery: Oct 15 (8 weeks ago)
  • Expected timeline: 3-6 months, realistic 4-5 months
  • Current state: Week 8, strong progress, minor setbacks resolved
  • PT trend: Week 1-3 painful, Week 4-6 plateau, Week 7-10 breakthrough
  • Mobility: From limping → walking with crutches → walking without aids
  • Pain: From 8/10 → 4/10 → 2/10
  • PT adherence: 100% (missed 0 sessions)
  • Emotional trajectory: Initially scared → plateau frustration → now confident
  • Family support: Consistent, high-quality (user + Alice visits)

K1 Response (deeply informed by 10-week arc):
  "Mom's looking at 4-5 weeks more of gradual improvement, but she's
   essentially 'recovered' now — back to full function by week 12-14.

   Here's where she's been:
   • Weeks 1-2: Acute post-op (toughest, heavy pain)
   • Weeks 3-6: Early PT, challenging improvements, frustration phase
   • Weeks 7-10: Now — steady gains, confidence returning, pain managed
   • Weeks 11-14: Final PT, return to normal activities, celebration time

   The plateau you experienced at week 6? That actually resolved faster than
   many people. That's because of your consistent support and her PT adherence.

   Pain is down to 2/10 now, which is excellent. Mobility is near-normal.
   I'd expect her to feel 'recovered' by end of week 12, though PT continues."

  ✨ Feels like doctor who's been following case for months
  ✨ Can reference specific timelines and compare to patterns
  ✨ Personalizes recovery trajectory based on data
```

### **Week 14: Proactive Celebration**

```
System (unsolicited, observing PT completion timeline):
  "Mom's PT completion is coming up next week. I wanted to bring this up:

   Recovery milestones matter — not just physically but psychologically.
   After weeks of hard work, celebrating matters. Some thoughts:
   • Family dinner (Mom cooked her favorite? Symbolic)
   • Thank you gift for PT team (they'll appreciate recognition)
   • Commemorate the journey (photos, written reflection?)
   • Share story if comfortable (helps others in same situation)

   This transition from 'recovery' to 'recovered' is real and worth marking.
   What feels right for your family?"

  ✨ Feels like someone who genuinely cares
  ✨ Psychologically attuned, not just mechanical
  ✨ Recognizes meaning-making in recovery

  User: "That's beautiful. Family dinner it is."

  K0 P06: "Celebration/recognition + milestone psychology valued"
  K0 P05: Creates reminder for thank-you notes, coordinates family dinner
  K0 P03 (next consolidation): "Recovery milestone celebrated with family
                               → builds family resilience for future challenges"

  ✨ System learns deeper about family values and priorities
```

---

## 🚨 Missing Concepts: What Needs Building

From brainstorm + ADRs, these critical concepts need implementation:

### **1. Dynamic User Modeling Service (PersonaGraph)**

- Not static preferences → dynamic model of evolving user values
- Extract: goals (Mom's recovery), fears (setback), values (family first), learning style
- Update: after each interaction, learns your changing priorities
- **Impact:** "You care about Mom's health — let me help [X]. Last week you cared about [Y]"

### **2. Cross-Domain Context Fusion**

- Health + Finance + Relationships + Calendar + Work → unified context
- "Mom recovering + PT expensive + sister visiting = important family moment"
- Not siloed, but semantically integrated through KG
- **Impact:** Holistic family understanding, not fragmented views

### **3. Affective Memory (Emotional Grounding)**

- P03 should extract: "This memory matters because... [emotional reason]"
- Emotional salience drives what gets consolidated vs forgotten vs archived
- "Mom's recovery is emotionally charged → preserve details + context"
- **Impact:** System understands what really matters, not just what's frequent

### **4. Proactive Anticipation System**

- Not just responsive: "What's Mom's PT schedule?"
- But proactive: "Mom's PT is today, good time to check in? She'll need encouragement"
- Based on learned patterns + P03 consolidation insights + KG causal analysis
- **Impact:** Feels like thoughtful friend thinking ahead, not reactive assistant

### **5. Multi-Person Memory Model**

- Each family member has own model (Alice, Mom, User, Dad, etc.)
- Shared family memory (relationships, events everyone knows, family values)
- Private memory (person-specific health, preferences, secrets)
- Coordination rules: Updates affecting multiple people (Alice visiting Mom)
- **Impact:** Family-aware system, not just user-centric, manages complex dynamics

### **6. Causality Graph** (separate from KG)

- "Mom's recovery affects when she can visit Dad"
- "Finance constraints affect healthcare choices"
- "Family stress affects recovery speed"
- Causal reasoning: "If X happens, Y will likely follow because Z"
- **Impact:** Better predictions, proactive planning, scenario analysis

### **7. Counterfactual Reasoning in Dreams (P03 Phase 5)**

- "What if Mom recovered faster? How would we celebrate?"
- "What if Alice couldn't visit? How would we support Mom emotionally?"
- "What if we missed PT for a week? Recovery impact?"
- **Impact:** Creative problem-solving, scenario planning, risk awareness

### **8. Device/Context Embodiment (ADR-0085)**

- System aware of which device user is on
- Phone: Short, quick suggestions, voice-friendly
- Laptop: Longer-form planning, written content
- Watch: Micro-interactions, time-critical alerts
- Car: Voice-only, safe driving (no complex text)
- **Impact:** Tailored interaction style, context-appropriate, safer

### **9. Emotional Regulation Coordination**

- System aware of user's current emotional state
- During stress: Simplify suggestions, be calming, offer support
- During celebration: Match energy, be enthusiastic, amplify joy
- During overwhelm: Proactively manage load, suggest break
- **Impact:** Feels emotionally attuned, not robotic, supportive

### **10. Habit Formation & Habit Breaking Support (P20)**

- P20 Procedural memory: "Recovery includes PT routine"
- Help form: "PT is Monday 10am + meds after = automated"
- Break: "Old pattern: check-ins only when crisis. New: regular connection"
- Track: Habit strength, consistency, relapse risk
- **Impact:** Practical life improvement, behavior change support, automation

---

## 🏆 Success Metrics: How Do We Know It Feels "Real"?

These metrics show when the system achieves "real human" feel:

- **Memory Accuracy** — System recalls specific details after weeks/months
- **Contextual Relevance** — Suggestions feel appropriately timed, not random
- **Emotional Resonance** — User feels understood, not processed
- **Anticipation Quality** — System thinks ahead in ways user genuinely appreciates
- **Learning Velocity** — Noticeably improves week-to-week
- **No Drift** — Never gets stuck in bad patterns, detects and corrects
- **Cross-Domain Coherence** — Understands how health affects mood affects priorities
- **Multi-Person Awareness** — Tracks Mom, Alice, User as distinct agents with needs
- **Temporal Reasoning** — Understands recovery arcs, not just snapshots
- **Privacy Instinct** — Protects sensitive info naturally (feels considerate)
- **Family Coordination** — Proactively manages complex family dynamics
- **Psychological Insight** — Recognizes emotional needs (plateau frustration, celebration)

---

## 🔗 Integration: How 20 Pipelines Work Together

Every user message triggers a coordinated pipeline dance:

```
User: "Mom's doing better, started PT today"
        ↓
┌─────────────────────────────────────────────────┐
│  K0 Pipeline Orchestration (20 pipelines)       │
└─────────────────────────────────────────────────┘

P02 (Write/Ingest) ▶ Record episodic: "PT started, positive"
P06 (Learning) ▶ Extract: "PT success correlates with user support"
P19 (Personalization) ▶ Update: "PT is family priority"
P08 (Embedding) ▶ Create vector: "PT ≈ recovery progress"
P07 (Sync) ▶ Share recovery milestone to family devices
P01 (Recall) ▶ Get recovery context for response
P10 (PII) ▶ Ensure health data properly protected
P17 (QoS) ▶ Prioritize Mom's health data (high importance)
P03 (Consolidation) ▶ Schedule: Extract "PT pain-improvement cycle"
P05 (Prospective) ▶ Schedule: "PT reminder for next session"
P16 (Experiment) ▶ Track: Does proactive PT support improve adherence?
P18 (Safety) ▶ Check: All suggestions medically sound
P14 (Dedup) ▶ Ensure: "PT" = "Physical Therapy" consistently
        ↓
Result: K1 Response
  "That's wonderful! Week 1 PT is tough but important. The soreness is
   normal. How's her energy? And how are YOU doing managing her care?"
        ↓
Later (P03 runs nightly):
  Consolidates week's PT + recovery data
  Discovers patterns: Pain cycles, improvement trajectories
  Creates semantic memory: "PT effectiveness depends on consistency"
  Updates KG: Mom's recovery arc now includes PT milestones
  Generates insights: "Week 6 plateau likely, have support plan ready"
        ↓
Next week:
  All subsequent responses benefit from consolidation
  System is smarter, more contextual, more human-like
```

---

## 💡 Why This Architecture Feels "Real"

1. **Parallel Memory Formation** — Thinks WHILE talking, not after (human-like responsiveness)
2. **Consolidated Wisdom** — Regular "sleep" creates deeper understanding (like humans)
3. **Structured Knowledge** — KG enables correct family reasoning (not fuzzy inference)
4. **Learning Without Drift** — Adaptive but with safety (learns good, prevents bad)
5. **Proactive Anticipation** — Thinks ahead based on patterns (feels like good friend)
6. **Cross-Domain Fusion** — Understands interconnected life (health affects mood)
7. **Emotional Grounding** — Recognizes what matters most (feels attuned)
8. **Temporal Awareness** — Understands arcs and trajectories (not just snapshots)
9. **Continuous Growth** — Gets smarter week-to-week (feels like relationship deepening)
10. **Graceful Prioritization** — Never tries to remember everything equally (feels intelligent)

---

## 🚀 Next Steps: Implementation Roadmap

### Phase 1: Foundation (Weeks 1-4)

- [ ] Finalize all 20 pipeline ADRs
- [ ] Implement P02 (Write) + P01 (Recall)
- [ ] Implement P03 (Consolidation) all 5 phases
- [ ] Implement P09 (Connector Ingestion) for health + calendar

### Phase 2: Intelligence (Weeks 5-8)

- [ ] Implement P06 (Learning Loop) with drift detection
- [ ] Implement P19 (Personalization) for user modeling
- [ ] Dynamic agent creation (ADR-0086)
- [ ] K1 ↔ K0 bridge (P04, P06 signals)

### Phase 3: Knowledge Graph (Weeks 9-12)

- [ ] Implement K0::st_kg driver (temporal graph)
- [ ] Temporal reasoning engine (P03 extracts KG)
- [ ] Family relationship queries
- [ ] Causality reasoning

### Phase 4: Multi-Device (Weeks 13-16)

- [ ] Implement P07 (Sync/CRDT)
- [ ] Multi-device context sharing
- [ ] Cross-family coordination

### Phase 5: Advanced Features (Weeks 17+)

- [ ] Counterfactual reasoning in P03
- [ ] Emotional grounding (Affect memory)
- [ ] Embodied awareness (ADR-0085)
- [ ] Habit formation support (P20)

---

## 🧭 Vision Statement

**A conversational AI that remembers you. Not your preferences in a database, but actually remembers your family, your concerns, your victories. That thinks while you talk. That consolidates while you sleep. That gets smarter every week. That feels like talking to someone who actually cares.**

---

## 📚 Reference ADRs

- ADR-0001: K0/K1 Kernel Split (dual microkernel architecture)
- ADR-0017: SessionState 6-Section Design (K1 working memory)
- ADR-0081: Knowledge Graph Architecture (structured relationships)
- ADR-0084: Memory Consolidation Pipeline (P03 detailed)
- ADR-0085: Embodied Awareness (device context)
- ADR-0086: Dynamic Agent Creation
- ADR-0059: Learning Loop (P06 feedback integration)

---

## 🎭 K1 Agent Architecture: Complete Flow (Concierge + Specialists + Writers + Orchestrator)

### Three-Tier Agent Hierarchy with K1 Orchestration

Based on existing ADRs (ADR-0006f, ADR-0007, ADR-0086):

```
┌─────────────────────────────────────────────────────────────────────┐
│  TIER 1: CONCIERGE AGENT (Always Active, Single-Domain Router)      │
│  Role: Master Coordinator + Intent Classification                    │
└─────────────────────────────────────────────────────────────────────┘
         │
         ├─ Listens to ALL user messages
         ├─ Classifies intent & domain (health, finance, social, planning)
         ├─ Routes to appropriate specialist(s)
         ├─ Coordinates multi-domain queries via K1 Orchestrator
         └─ Maintains conversation continuity

                    ↓ Routes to ↓

┌─────────────────────────────────────────────────────────────────────┐
│  TIER 2: SPECIALIST AGENTS (Domain-Specific, On-Demand)             │
│  Created by: AgentFactory (ADR-0086) using dynamic agent creation   │
└─────────────────────────────────────────────────────────────────────┘

┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
│ HealthcareAgent      │  │ FinanceAgent         │  │ SocialCoordinator    │
│ • PT schedules       │  │ • Budget tracking    │  │ • Family events      │
│ • Medication timing  │  │ • Pharmacy costs     │  │ • Visit planning     │
│ • Recovery guidance  │  │ • Insurance claims   │  │ • Relationship mgmt  │
│                      │  │                      │  │                      │
│ Tools:               │  │ Tools:               │  │ Tools:               │
│ • Calendar (health)  │  │ • Plaid API          │  │ • Calendar (social)  │
│ • MCP health APIs    │  │ • Spreadsheet calc   │  │ • Contact directory  │
│ • Med database       │  │ • Receipt OCR        │  │ • Messaging APIs     │
│                      │  │                      │  │                      │
│ Lifecycle: Dynamic   │  │ Lifecycle: Dynamic   │  │ Lifecycle: Dynamic   │
│ Creation: On-demand  │  │ Creation: On-demand  │  │ Creation: On-demand  │
│ Termination: After   │  │ Termination: After   │  │ Termination: After   │
│ task completion      │  │ task completion      │  │ task completion      │
└──────────────────────┘  └──────────────────────┘  └──────────────────────┘

┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
│ PlannerAgent         │  │ RoutineAgent         │  │ EmergencyAgent       │
│ (ADR-0007)           │  │                      │  │                      │
│ • 4-stage pipeline   │  │ • Habit tracking     │  │ • Crisis detection   │
│ • Task breakdown     │  │ • Routine building   │  │ • Urgent escalation  │
│ • Goal setting       │  │ • Reminders          │  │ • Safety protocols   │
│ • DAG generation     │  │                      │  │                      │
└──────────────────────┘  └──────────────────────┘  └──────────────────────┘

                    ↓ All observed by ↓

┌─────────────────────────────────────────────────────────────────────┐
│  TIER 3: WRITER AGENTS (Background, Always Active)                  │
│  Pattern: Silent Observers + Bookkeepers                            │
└─────────────────────────────────────────────────────────────────────┘

┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
│ MemoryWriterAgent    │  │ LearningExtractor    │  │ SemanticEnricher     │
│ • Extract entities   │  │ • P06 signals        │  │ • Tag concepts       │
│ • P02 raw write      │  │ • Drift detection    │  │ • Affect analysis    │
│ • P02 enrichment     │  │ • Pattern learning   │  │ • Salience scoring   │
└──────────────────────┘  └──────────────────────┘  └──────────────────────┘

                    ↓ Coordinated by ↓

┌─────────────────────────────────────────────────────────────────────┐
│  K1 ORCHESTRATOR (ADR-0006f: 3-Phase Contract Net Protocol)         │
│  Pure Actor (NOT AI agent) - Deterministic coordination             │
└─────────────────────────────────────────────────────────────────────┘

Phase 1: NEGOTIATION (~20-50ms)
  • Broadcast task announcement to all eligible agents
  • Agents bid with confidence scores + constraints
  • Collect proposals with 50ms deadline

Phase 2: SELECTION (<5ms)
  • Evaluate proposals with weighted scoring
  • Select best agent(s) for task (single or parallel)
  • Award task to winner(s)

Phase 3: EXECUTION (Variable, task-dependent)
  • ADR-0006c: Parallel DAG execution engine
  • Build DAG from plan (nodes = steps, edges = dependencies)
  • Compute waves via topological sort (Kahn's algorithm)
  • Execute waves in parallel (asyncio.gather, max 3 concurrent)
  • Handle stragglers and errors
```

---

## 🔄 Complete User Request Flow: Architecture Integration

### Example: Cross-Domain Query with K1 Orchestration

**User Request:** "Can we afford to extend Mom's PT another month?"

```
┌──────────────────────────────────────────────────────────────────────────┐
│ T0: User message arrives                                                  │
└──────────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────────┐
│ T0+1ms: ConciergeAgent (Always Active)                                   │
│  • Fast intent classification (<10ms)                                     │
│  • Detects: DECISION_SUPPORT, domains=[health, finance]                  │
│  • Strategy: Multi-agent collaboration (complex cross-domain)            │
└──────────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────────┐
│ T0+10ms: ConciergeAgent creates TASK for K1 Orchestrator                 │
│  Task: {                                                                  │
│    intent: "evaluate_pt_extension",                                       │
│    domains: ["health", "finance"],                                        │
│    requirements: {                                                        │
│      health_analysis: "PT effectiveness, remaining sessions",            │
│      finance_analysis: "Budget constraints, cost projection"             │
│    }                                                                      │
│  }                                                                        │
└──────────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────────┐
│ T0+15ms: PHASE 1 - NEGOTIATION (K1 Orchestrator)                         │
│  ADR-0006f Contract Net Protocol                                          │
└──────────────────────────────────────────────────────────────────────────┘
                              ↓
         ┌────────────────────┴────────────────────┐
         │                                         │
┌────────▼───────────┐                 ┌──────────▼──────────┐
│ HealthcareAgent    │                 │ FinanceAgent        │
│ (Check if exists)  │                 │ (Check if exists)   │
└────────┬───────────┘                 └──────────┬──────────┘
         │                                         │
         ├─ NOT FOUND → AgentFactory.create()    ├─ NOT FOUND → AgentFactory.create()
         │   (ADR-0086)                           │   (ADR-0086)
         │                                         │
         ↓                                         ↓
┌────────────────────────────────────────┐ ┌──────────────────────────────────┐
│ AgentFactory:                          │ │ AgentFactory:                    │
│ 1. Load template: health_specialist.yml│ │ 1. Load template: finance.yml    │
│ 2. Reserve resources: 256MB, GPU       │ │ 2. Reserve resources: 128MB, CPU │
│ 3. Generate ID: agent-sess-123-...-001 │ │ 3. Generate ID: agent-sess-123-002│
│ 4. Bind capabilities: [TOOL_CALL,     │ │ 4. Bind capabilities: [TOOL_CALL, │
│    MEMORY_READ, MODEL_CALL]            │ │    MEMORY_READ, MODEL_CALL]      │
│ 5. Compose: health_prompt + tools     │ │ 5. Compose: finance_prompt + tools│
│ 6. State: PENDING → WARMING → ACTIVE  │ │ 6. State: PENDING → WARMING → ACTIVE│
│ Duration: ~50-100ms                    │ │ Duration: ~50-100ms              │
└────────┬───────────────────────────────┘ └──────────┬───────────────────────┘
         │                                             │
         └─────────────────┬───────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────────────────┐
│ Both agents BID on task:                                                  │
│                                                                            │
│ HealthcareAgent Proposal:                                                 │
│  • Confidence: 0.9 (high - has PT data access)                           │
│  • Estimated latency: 150ms (K0 P01 query + analysis)                    │
│  • Estimated cost: $0.0001 (lightweight query)                           │
│  • Capabilities: ✅ Can access PT records, analyze effectiveness          │
│  • Constraints: Requires K0 health domain access                          │
│                                                                            │
│ FinanceAgent Proposal:                                                    │
│  • Confidence: 0.95 (high - has budget tracking)                         │
│  • Estimated latency: 100ms (K0 P01 query + calculation)                 │
│  • Estimated cost: $0.00005 (simple calculation)                         │
│  • Capabilities: ✅ Can access budget, calculate costs                    │
│  • Constraints: Requires K0 finance domain access                         │
└──────────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────────┐
│ T0+60ms: PHASE 2 - SELECTION (K1 Orchestrator)                           │
│  ADR-0006f: Weighted Scoring Function                                    │
│                                                                            │
│  Score = (confidence × 0.4) + (latency_score × 0.3) +                    │
│          (cost_score × 0.2) + (capability_match × 0.1)                   │
│                                                                            │
│  HealthcareAgent: 0.87 (SELECTED)                                        │
│  FinanceAgent: 0.91 (SELECTED)                                           │
│                                                                            │
│  Decision: BOTH agents selected for parallel execution                    │
└──────────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────────┐
│ T0+65ms: PlannerAgent creates TASK PLAN (ADR-0007)                       │
│  4-Stage Planning Pipeline:                                               │
│                                                                            │
│  STAGE 1: SKETCH (LLM-based, 150-500ms)                                  │
│    Generate high-level plan:                                              │
│    Step 1: Query PT effectiveness (HealthcareAgent)                      │
│    Step 2: Query budget status (FinanceAgent)                            │
│    Step 3: Synthesize recommendation (ConciergeAgent)                    │
│                                                                            │
│  STAGE 2: EXPAND (Deterministic, <1ms)                                   │
│    Fill tool schemas from registry:                                       │
│    Step 1: {tool: "k0_p01_query", domain: "health", ...}                │
│    Step 2: {tool: "k0_p01_query", domain: "finance", ...}               │
│                                                                            │
│  STAGE 3: VALIDATE (Two-Tier, <1ms or 50-100ms)                         │
│    Tier 1 (Rules): ✅ Structure valid, no circular deps, budget OK       │
│    Tier 2 (Arbiter): ⏭️ SKIPPED (GREEN band, no safety concerns)        │
│                                                                            │
│  STAGE 4: COMMIT (<10ms)                                                  │
│    Serialize to FlowDef (FlatBuffers), write to K0 WAL                   │
│                                                                            │
│  Plan DAG:                                                                │
│    Step 1 (HealthcareAgent) ──┐                                          │
│    Step 2 (FinanceAgent) ──────┼─→ Step 3 (ConciergeAgent synthesis)    │
│                                                                            │
│  Duration: ~200-600ms                                                     │
└──────────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────────┐
│ T0+700ms: PHASE 3 - EXECUTION (K1 Orchestrator)                          │
│  ADR-0006c: Parallel DAG Execution Engine                                 │
└──────────────────────────────────────────────────────────────────────────┘
                              ↓
         ┌────────────────────┴────────────────────┐
         │ Wave 1: Parallel execution (no deps)    │
         └─────────────────────────────────────────┘
                              ↓
┌────────────────────────────┐        ┌─────────────────────────────────┐
│ Step 1: HealthcareAgent    │        │ Step 2: FinanceAgent            │
│ (Parallel with Step 2)     │        │ (Parallel with Step 1)          │
└────────┬───────────────────┘        └──────────┬──────────────────────┘
         │                                        │
         │ Query K0 P01:                         │ Query K0 P01:
         │ • PT sessions: 8 of 12                │ • Pharmacy: $47/week
         │ • Progress: strong                    │ • PT copay: $25/session
         │ • Mobility: improving                 │ • Insurance: 80% covered
         │ • Pain: decreased                     │ • Budget: $500/mo healthcare
         │                                        │
         │ Analysis:                              │ Analysis:
         │ "PT is effective,                     │ "Current spending: $250/mo
         │  extension recommended"               │  Additional month: +$200
         │                                        │  Total: $450 (under budget)"
         │                                        │
         │ Duration: ~150ms                      │ Duration: ~100ms
         └────────┬───────────────────────────────┴─────────┘
                  │
         ┌────────▼────────┐
         │ Barrier: Wait   │
         │ for Wave 1      │
         └────────┬────────┘
                  ↓
         ┌────────────────────────────────────────┐
         │ Wave 2: Step 3 (depends on Wave 1)     │
         └─────────────────────────────────────────┘
                  ↓
┌──────────────────────────────────────────────────────────────────────────┐
│ Step 3: ConciergeAgent (Synthesis)                                       │
│                                                                            │
│  Input Context:                                                            │
│  • Health result: PT effective, extension recommended                     │
│  • Finance result: $200 more, within budget ($450 < $500)                │
│                                                                            │
│  LLM Synthesis Prompt:                                                    │
│  "User asked about extending PT. Integrate health and finance analysis   │
│   to provide coherent recommendation."                                    │
│                                                                            │
│  Generated Response:                                                       │
│  "Yes, extending Mom's PT another month makes sense both medically       │
│   and financially. Her progress has been strong — mobility improving,    │
│   pain decreasing. The cost would be about $200 more (4 sessions × $50), │
│   bringing your total healthcare spending to $450/month, still under     │
│   your $500 budget. I'd recommend talking to her PT about specific       │
│   goals for the extension."                                               │
│                                                                            │
│  Duration: ~150ms (LLM inference)                                         │
└──────────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────────┐
│ T0+1000ms: Response streaming to user                                    │
│  (User sees tokens immediately)                                           │
└──────────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────────┐
│ T0+1001ms: MemoryWriterAgent (Background, Parallel)                      │
│  TIER 3: Background Bookkeeping                                           │
│                                                                            │
│  Phase 1: Immediate raw capture (T0+10ms, already happened)              │
│    k0.p02_write_raw(                                                      │
│      text="Can we afford to extend Mom's PT?",                           │
│      entities=["Mom", "PT", "afford", "extend"],                         │
│      intent="cross_domain_decision",                                      │
│      partial=True                                                         │
│    )                                                                      │
│                                                                            │
│  Phase 2: Enrichment (after synthesis completes)                         │
│    k0.p02_enrich(                                                         │
│      session_id="sess_123",                                              │
│      entities=["Mom", "PT", "budget", "extension"],                      │
│      semantic_tags=["health", "finance", "decision_support"],            │
│      affect={"salience": 0.9, "emotion": "concerned_planning"},          │
│      triggers=["P03", "P06", "P19"],                                     │
│      agents_involved=["ConciergeAgent", "HealthcareAgent",               │
│                      "FinanceAgent", "PlannerAgent"],                    │
│      orchestration_metadata={                                             │
│        "negotiation_time_ms": 50,                                         │
│        "selection_time_ms": 5,                                            │
│        "execution_time_ms": 300,                                          │
│        "total_orchestration_ms": 355,                                     │
│        "agents_created_dynamic": 2,  # Healthcare + Finance              │
│        "dag_waves": 2,                                                    │
│        "parallel_execution": True                                         │
│      }                                                                    │
│    )                                                                      │
│                                                                            │
│  Phase 3: Trigger downstream pipelines                                    │
│    • P06 (Learning): "User makes data-driven health decisions"           │
│    • P19 (Personalization): "Health+finance both matter, cross-domain"   │
│    • P03 (Consolidation): Schedule if >1000 memories                     │
│                                                                            │
│  Duration: ~50-200ms (background, non-blocking)                          │
└──────────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────────┐
│ T0+2000ms: Agent Cleanup (ADR-0005: Agent Lifecycle FSM)                 │
│                                                                            │
│  HealthcareAgent: ACTIVE → IDLE (task complete)                          │
│  • Idle pool: Wait 5 minutes for reuse                                   │
│  • If not reused: IDLE → DRAINING → TERMINATED                           │
│                                                                            │
│  FinanceAgent: ACTIVE → IDLE (task complete)                             │
│  • Idle pool: Wait 5 minutes for reuse                                   │
│  • If not reused: IDLE → DRAINING → TERMINATED                           │
│                                                                            │
│  ConciergeAgent: Remains ACTIVE (always active)                          │
│  MemoryWriterAgent: Remains ACTIVE (always active)                       │
└──────────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────────┐
│ RESULT: User got comprehensive cross-domain recommendation               │
│  • Total latency: ~1000ms (within 2000ms P95 budget)                     │
│  • Memory formed: Episodic + enriched                                     │
│  • Learning extracted: Cross-domain decision patterns                     │
│  • Agents efficiently managed: Created dynamically, cleaned up after use │
│  • K1 orchestration overhead: ~355ms (negotiate + select + execute)     │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 🔑 Key Architecture Patterns Integrated

### 1. **Three-Tier Agent Hierarchy**

- **Tier 1 (Concierge):** Always active, routes and coordinates
- **Tier 2 (Specialists):** Domain-specific, dynamically created on-demand (ADR-0086)
- **Tier 3 (Writers):** Background bookkeepers, always active

### 2. **K1 Orchestrator (ADR-0006f): 3-Phase Contract Net Protocol**

- **Phase 1 (Negotiation):** Broadcast + bidding (~20-50ms)
- **Phase 2 (Selection):** Weighted scoring (<5ms)
- **Phase 3 (Execution):** Parallel DAG execution (ADR-0006c)

### 3. **Dynamic Agent Creation (ADR-0086)**

- **AgentFactory:** Singleton pattern for runtime agent creation
- **Templates:** YAML-based agent specifications (capabilities, resources, prompts)
- **Resource Reservation:** Pre-allocate memory/compute before agent creation
- **Lifecycle Integration:** PENDING → WARMING → ACTIVE → IDLE → DRAINING → TERMINATED

### 4. **Planner Agent (ADR-0007): 4-Stage Planning Pipeline**

- **Stage 1 (Sketch):** LLM generates high-level plan (150-500ms)
- **Stage 2 (Expand):** Deterministic tool schema lookup (<1ms)
- **Stage 3 (Validate):** Two-tier validation (rules + LLM arbiter if risky)
- **Stage 4 (Commit):** Serialize to FlatBuffers, persist to K0 WAL (<10ms)

### 5. **Parallel DAG Execution (ADR-0006c)**

- **Topological Sort:** Kahn's algorithm for wave computation
- **Wave-Based Execution:** Independent steps run in parallel (asyncio.gather)
- **Barrier Synchronization:** Wait for wave completion before next wave
- **Straggler Handling:** Detect slow tasks, log warnings

### 6. **SessionState (ADR-0017): 6-Section Working Memory**

- **beliefs:** User facts, preferences (10-20KB)
- **scoreboard:** Common ground, referents (4-8KB)
- **control:** Active agent leases, flow state (8-12KB)
- **persona:** Personality model, tone (2-4KB)
- **multimodal:** Audio/vision state (4-8KB)
- **meta:** Telemetry, timestamps (2-4KB)

### 7. **Writer Agents: Two-Phase Memory Formation**

- **Phase 1:** Immediate raw capture (T0+1ms, non-blocking)
- **Phase 2:** Post-response enrichment (T0+500ms, after LLM completes)
- **User Experience:** Appears simultaneous (raw write before response streams)

---

# 🎬 Real-World Chat Scenarios: Comprehensive List

### Category 1: User Corrections & Rapid Input

#### Scenario 1.1: **Typo Correction (Immediate)**

```
User (T0):      "Book dinner at Italin restaurant"
User (T0+0.5s): "Italian* restaurant"

Problem:
  • ConciergeAgent already started processing first message
  • HealthcareAgent might be bidding (wrong domain!)
  • First message should be CANCELLED

Solution:
  ✅ Message Queue with cancellation tokens
  ✅ Concierge detects rapid correction (< 2s, similar text)
  ✅ Cancel first orchestration, merge into second
  ✅ SessionState: Mark msg_1 as "superseded_by: msg_2"
```

#### Scenario 1.2: **Rapid-Fire Messages (No Response Yet)**

```
User (T0):      "What's Mom's PT schedule?"
User (T0+0.3s): "Also check her medications"
User (T0+0.5s): "And when is Alice visiting?"

Problem:
  • Orchestrator started 3 separate tasks
  • 3 HealthcareAgents might be created unnecessarily
  • Should be treated as ONE multi-part query

Solution:
  ✅ Message batching window (500ms buffer)
  ✅ Concierge detects rapid sequence, waits for pause
  ✅ Merge into single multi-domain query
  ✅ SessionState: Group messages under single turn_id
```

#### Scenario 1.3: **Correction After Partial Processing**

```
User (T0):      "Book dinner at 7pm"
System (T0+200ms): "Finding restaurants for 7pm..."
User (T0+300ms): "Actually make it 8pm"

Problem:
  • RestaurantAgent already querying for 7pm slots
  • Partial work wasted
  • Need to UPDATE ongoing task, not cancel

Solution:
  ✅ Task amendment protocol
  ✅ Orchestrator supports UPDATE_TASK message
  ✅ Agent checks for amendments mid-execution
  ✅ SessionState: Update control.active_tasks with amendment
```

---

### Category 2: Mid-Response Interruptions

#### Scenario 2.1: **User Interrupts Streaming Response**

```
System (T0):    "Mom's PT schedule is..."
User (T0+500ms): "Stop, I need to ask something else"

Problem:
  • DialogueAgent still streaming tokens
  • MemoryWriterAgent hasn't finished enrichment
  • Partial response should be saved but marked incomplete

Solution:
  ✅ ConciergeAgent: Detect interruption (new message while system_state="streaming")
  ✅ Send INTERRUPT_STREAM command to DialogueAgent
  ✅ DialogueAgent implements graceful interruption protocol:

class DialogueAgent:
    async def handle_interruption(self):
        """Graceful streaming interruption protocol."""
        # 1. STOP token generation immediately
        self.streaming = False
        self.stop_event.set()  # Signal LLM to stop generating

        # 2. SAVE partial response with metadata
        partial_response = self.buffer.get_accumulated_text()
        await self.save_partial_response(
            content=partial_response,
            status="interrupted",
            tokens_generated=self.token_count,
            interrupted_at=time.now()
        )

        # 3. UPDATE SessionState
        self.session_state.scoreboard.last_response_status = "interrupted"
        self.session_state.scoreboard.partial_responses.append({
            "content": partial_response,
            "interrupted_at": time.now(),
            "reason": "user_interruption"
        })

        # 4. NOTIFY MemoryWriterAgent (abort enrichment)
        await self.message_bus.send(
            agent_id="memory_writer",
            message=AbortEnrichment(response_id=self.current_response_id)
        )

        # 5. YIELD control back to ConciergeAgent
        self.state = AgentState.INTERRUPTED
        return InterruptionAck(partial_saved=True)

  ✅ MemoryWriterAgent: Check for abort signal before enrichment
  ✅ SessionState: Track partial_responses for potential resume
  ✅ User sees: Streaming stops immediately, new query processed
```

#### Scenario 2.2: **User Changes Topic Mid-Response**

```
System (T0):    "Mom's recovery is progressing well. Her PT sessions..."
User (T0+800ms): "What's the weather tomorrow?"

Problem:
  • HealthcareAgent mid-response about PT
  • User expects immediate topic switch
  • Old response no longer relevant

Solution:
  ✅ Context switch protocol
  ✅ Concierge: Detect topic change (scoreboard.qud shift)
  ✅ Cancel old task, start new task
  ✅ SessionState: Push old QUD to history, set new QUD
```

#### Scenario 2.3: **User Interrupts with Clarification**

```
System (T0):    "I found 5 restaurants available at 7pm..."
User (T0+600ms): "Only Italian restaurants"

Problem:
  • RestaurantAgent listing all cuisines
  • User wants to REFINE ongoing query, not start new one
  • Should filter results, not restart search

Solution:
  ✅ Query refinement protocol
  ✅ Concierge: Detect refinement (similar domain, adds constraint)
  ✅ Orchestrator: REFINE_TASK (add filter, don't restart)
  ✅ SessionState: Append constraint to control.active_tasks
```

---

### Category 3: System Delays & User Impatience

#### Scenario 3.1: **System Taking Too Long (User Checks Status)**

```
User (T0):      "Find cheapest flight to Seattle"
System (T0+5s): [Still processing, external API slow]
User (T0+6s):   "Are you there?"

Problem:
  • User thinks system crashed
  • Second message should NOT cancel first task
  • User wants status update, not new task

Solution:
  ✅ Status query detection
  ✅ Concierge: Recognize meta-queries ("are you there?", "hello?")
  ✅ Return: "Still searching flights, found 12 so far..."
  ✅ Don't interrupt ongoing task
```

#### Scenario 3.2: **User Gets Impatient and Cancels**

```
User (T0):      "Compare all insurance plans"
System (T0+3s): [Long-running comparison task]
User (T0+4s):   "Never mind, too slow"

Problem:
  • FinanceAgent mid-execution, APIs already called
  • Partial work done, might have results
  • Should save progress and gracefully terminate

Solution:
  ✅ Explicit cancellation detection
  ✅ Concierge: Detect cancel phrases ("never mind", "stop", "forget it")
  ✅ Orchestrator: CANCEL_TASK with SAVE_PARTIAL flag
  ✅ MemoryWriterAgent: Save "task_cancelled" event
  ✅ SessionState: Mark control.active_tasks as "cancelled"
```

#### Scenario 3.3: **System Error, User Retries**

```
System (T0):    "Error: Unable to book reservation (API timeout)"
User (T0+2s):   "Try again"

Problem:
  • User expects RETRY of last task, not new task
  • Should use same parameters, different strategy
  • Orchestrator should try backup agent or fallback API

Solution:
  ✅ Retry detection ("try again", "retry", "one more time")
  ✅ SessionState: Store last_failed_task
  ✅ Orchestrator: RETRY_TASK with FALLBACK strategy
  ✅ Use different agent or API (if available)
```

---

### Category 4: Multi-Turn Dependencies

#### Scenario 4.1: **Amendment to Previous Request**

```
User (T0):      "Book dinner for 2 at 7pm"
System (T0+1s): "Booked table at Ristorante X"
User (T0+3s):   "Actually make it for 4 people"

Problem:
  • Booking already completed (external API called)
  • Need to MODIFY existing booking, not create new one
  • Compensation needed (cancel old, rebook new)

Solution:
  ✅ Amendment detection (recent action + modification)
  ✅ SessionState: Store last_action_id in control section
  ✅ Orchestrator: COMPENSATE_AND_AMEND (Saga pattern)
  ✅ RestaurantAgent: Cancel old booking, create new one
```

#### Scenario 4.2: **Follow-Up Question (Context Dependency)**

```
User (T0):      "What restaurants are near Mom's house?"
System (T0+1s): "Found 5 restaurants within 2 miles"
User (T0+3s):   "Which one is cheapest?"

Problem:
  • User expects system to remember "5 restaurants"
  • Second query depends on first query results
  • Need to carry forward context

Solution:
  ✅ SessionState.scoreboard: Store referents
  ✅ Concierge: Resolve "which one" → previous result set
  ✅ Query rewrite: "Which restaurant from [prev_results] is cheapest?"
  ✅ No new search needed, filter existing results
```

#### Scenario 4.3: **Chain of Dependent Actions**

```
User (T0):      "Find restaurants, book one, add to calendar"
System (T0+1s): "Found 10 restaurants"
User (T0+2s):   "Book the Italian one at 7pm"
[System books]
User (T0+5s):   "Send me the calendar invite"

Problem:
  • 3-step workflow with dependencies
  • Each step depends on previous step result
  • User expects seamless flow without repeating context

Solution:
  ✅ ConciergeAgent: Detect multi-step workflow from initial query
  ✅ SessionState.control: Add workflow state machine

@dataclass
class WorkflowState:
    """Track multi-step workflow progress in SessionState.control."""
    workflow_id: str
    steps: List[WorkflowStep]  # [find, book, calendar]
    current_step_index: int
    step_results: Dict[str, Any]  # Pass results between steps
    status: str  # "in_progress", "awaiting_user_input", "completed"

class WorkflowStep:
    step_name: str  # "find_restaurants", "book_restaurant", "add_to_calendar"
    depends_on: Optional[str]  # Previous step name
    result: Optional[Any]  # Step output
    status: str  # "pending", "in_progress", "completed"

  ✅ ConciergeAgent creates workflow:

async def process_multi_step_query(self, query: str):
    # Initial query: "Find restaurants, book one, add to calendar"
    workflow = WorkflowState(
        workflow_id=generate_id(),
        steps=[
            WorkflowStep("find_restaurants", depends_on=None),
            WorkflowStep("book_restaurant", depends_on="find_restaurants"),
            WorkflowStep("add_to_calendar", depends_on="book_restaurant")
        ],
        current_step_index=0,
        step_results={},
        status="in_progress"
    )
    self.session_state.control.workflow_state = workflow

    # Start first step
    await self.orchestrator.coordinate_task(
        TaskEnvelope(intent="find_restaurants", workflow_id=workflow.workflow_id)
    )

  ✅ After each step completes, ConciergeAgent advances workflow:

async def advance_workflow(self, step_result: Any):
    workflow = self.session_state.control.workflow_state

    # Save current step result
    current_step = workflow.steps[workflow.current_step_index]
    current_step.result = step_result
    current_step.status = "completed"
    workflow.step_results[current_step.step_name] = step_result

    # Check if waiting for user input
    if workflow.current_step_index == 0:  # After find_restaurants
        workflow.status = "awaiting_user_input"
        # User says: "Book the Italian one at 7pm"
        # ConciergeAgent resolves "the Italian one" using step_results
        return

    # Move to next step if auto-proceed
    workflow.current_step_index += 1
    if workflow.current_step_index < len(workflow.steps):
        next_step = workflow.steps[workflow.current_step_index]
        # Pass previous results as context
        await self.orchestrator.coordinate_task(
            TaskEnvelope(
                intent=next_step.step_name,
                workflow_id=workflow.workflow_id,
                context=workflow.step_results  # Previous results available
            )
        )
    else:
        workflow.status = "completed"

  ✅ SessionState.scoreboard.referents tracks results:
    - "the Italian one" → step_results["find_restaurants"][2] (Italian restaurant)
    - "the calendar invite" → step_results["add_to_calendar"].event_id

  ✅ Orchestrator aware of workflow context, passes to agents
  ✅ User experience: Seamless multi-turn flow without repeating context
```

---

### Category 5: Conversational Noise

#### Scenario 5.1: **Acknowledgments (No Real Intent)**

```
System (T0):    "Mom's PT is scheduled for Monday 10am"
User (T0+1s):   "ok"

Problem:
  • "ok" has no intent, just acknowledgment
  • Should NOT trigger orchestration
  • But should be captured in memory (user acknowledged)

Solution:
  ✅ Intent classification: "acknowledgment" (no action needed)
  ✅ Concierge: Don't route to orchestrator
  ✅ Update SessionState.meta: user_acknowledged = True
  ✅ MemoryWriterAgent: Record acknowledgment (affects learning)
```

#### Scenario 5.2: **Small Talk (Social Lubrication)**

```
User (T0):      "How are you?"
OR
User (T0):      "Thanks for helping"

Problem:
  • Social courtesy, not task-oriented
  • Should respond naturally but not trigger specialists
  • Maintains relationship, not transactional

Solution:
  ✅ Intent: "social_interaction"
  ✅ Concierge handles directly (no orchestration)
  ✅ Quick response: "I'm here to help! What can I do for you?"
  ✅ SessionState: Update persona.rapport_score += 0.1
```

#### Scenario 5.3: **Ambiguous/Vague Query**

```
User (T0):      "What about Mom?"

Problem:
  • Underspecified query (what ABOUT Mom?)
  • Could be health, schedule, mood, location, etc.
  • System should ask clarifying question, not guess

Solution:
  ✅ Concierge: Detect ambiguity (low intent confidence < 0.6)
  ✅ Don't route to orchestrator yet
  ✅ Ask clarification: "What would you like to know about Mom? Her PT schedule, recovery progress, or something else?"
  ✅ SessionState.scoreboard: qud = "clarifying_intent"
```

---

### Category 6: Error Recovery & Edge Cases

#### Scenario 6.1: **External API Failure Mid-Execution**

```
System (T0):    "Booking restaurant..."
System (T0+2s): "Error: Restaurant booking API unavailable"
User (T0+3s):   "Can you try a different restaurant?"

Problem:
  • Partial failure (API down, not user error)
  • User expects fallback option
  • System should suggest alternatives, not just fail

Solution:
  ✅ Orchestrator: Implement automatic API fallback strategy

class K1Orchestrator:
    async def execute_with_fallback(self, task: TaskEnvelope, agent: Agent):
        """Execute task with automatic API fallback on failure."""
        try:
            result = await agent.execute(task)
            return result

        except APIUnavailableError as e:
            # 1. LOG failure for telemetry
            self.session_state.control.last_failed_task = {
                "task_id": task.id,
                "agent_id": agent.id,
                "failure_reason": "api_unavailable",
                "failed_api": e.api_name,
                "timestamp": time.now()
            }

            # 2. CHECK for backup APIs
            backup_apis = self.config.get_backup_apis(e.api_name)
            if backup_apis:
                for backup_api in backup_apis:
                    try:
                        result = await agent.execute_with_api(task, backup_api)
                        # Success with backup!
                        return result
                    except Exception:
                        continue  # Try next backup

            # 3. TRY alternative approach (different agent)
            alternative_agents = await self._find_alternative_agents(task.intent)
            for alt_agent in alternative_agents:
                if alt_agent.id != agent.id:  # Don't retry same agent
                    try:
                        result = await alt_agent.execute(task)
                        return result
                    except Exception:
                        continue

            # 4. ALL fallbacks failed - return partial result with alternatives
            raise TaskPartialFailure(
                message="Primary API unavailable",
                partial_results=agent.get_partial_results(),
                suggested_alternatives=[
                    "Try a different restaurant",
                    "Try again in a few minutes",
                    "I can search for similar options"
                ]
            )

  ✅ ConciergeAgent: Present failure gracefully with options

async def handle_api_failure(self, failure: TaskPartialFailure):
    # Don't expose technical error to user
    response = f"The booking service is temporarily unavailable. "

    if failure.partial_results:
        response += f"I found these alternatives: {failure.partial_results}. "

    response += "Would you like me to try a different restaurant?"

    return response

  ✅ SessionState: Track API health for circuit breaker

@dataclass
class ControlSection:
    api_health: Dict[str, APIHealthStatus]  # Track failure rates

class APIHealthStatus:
    api_name: str
    consecutive_failures: int
    last_failure_time: float
    circuit_open: bool  # Stop trying if too many failures

  ✅ User experience: Transparent retry with alternatives, no technical errors exposed
```

#### Scenario 6.2: **Agent Crash Mid-Execution**

```
System (T0):    "Analyzing health data..."
System (T0+2s): [HealthcareAgent crashes - OOM]
User (T0+3s):   [Waiting for response]

Problem:
  • Agent crashed, user unaware
  • Orchestrator should detect failure and recover
  • User should not see error, system should retry

Solution:
  ✅ Implement Actor Model supervision (ADR-0002)

class AgentSupervisor:
    """
    Supervisor actor that monitors agent health and restarts on crash.
    Based on Erlang/OTP supervision trees.
    """

    def __init__(self, orchestrator: K1Orchestrator):
        self.orchestrator = orchestrator
        self.supervised_agents: Dict[str, SupervisedAgent] = {}
        self.restart_strategies = {
            "one_for_one": self._restart_one,  # Restart only crashed agent
            "one_for_all": self._restart_all,  # Restart all agents in group
        }

    async def supervise_agent(self, agent: Agent, strategy: str = "one_for_one"):
        """Register agent for supervision."""
        self.supervised_agents[agent.id] = SupervisedAgent(
            agent=agent,
            restart_strategy=strategy,
            max_restarts=3,
            restart_window=60.0,  # Max 3 restarts per 60s
            restart_count=0,
            last_restart_time=None
        )

        # Monitor agent health via heartbeat
        asyncio.create_task(self._monitor_agent_health(agent))

    async def _monitor_agent_health(self, agent: Agent):
        """Monitor agent via heartbeat, detect crashes."""
        while True:
            try:
                await asyncio.sleep(5.0)  # Check every 5 seconds

                # Send heartbeat ping
                response = await asyncio.wait_for(
                    agent.ping(),
                    timeout=2.0
                )

                if not response:
                    # Agent not responding - likely crashed
                    await self._handle_agent_crash(agent.id, "heartbeat_timeout")

            except asyncio.TimeoutError:
                await self._handle_agent_crash(agent.id, "heartbeat_timeout")

            except Exception as e:
                await self._handle_agent_crash(agent.id, str(e))

    async def _handle_agent_crash(self, agent_id: str, reason: str):
        """Handle agent crash with automatic restart."""
        supervised = self.supervised_agents.get(agent_id)
        if not supervised:
            return

        # 1. LOG crash for telemetry (don't expose to user)
        await self._log_crash(agent_id, reason)

        # 2. CHECK restart limits (prevent restart loops)
        if not self._can_restart(supervised):
            # Too many restarts - blacklist agent permanently
            await self.orchestrator.blacklist_agent(agent_id, reason="crash_loop")
            await self.orchestrator.find_backup_agent(supervised.agent.capabilities)
            return

        # 3. RESTART agent with clean state
        try:
            new_agent = await self._restart_agent(supervised)
            supervised.restart_count += 1
            supervised.last_restart_time = time.now()

            # 4. NOTIFY orchestrator of agent replacement
            await self.orchestrator.replace_agent(agent_id, new_agent.id)

            # 5. RESUME task transparently (user doesn't notice)
            active_task = self.orchestrator.get_agent_active_task(agent_id)
            if active_task:
                await new_agent.resume_task(active_task)

        except Exception as e:
            # Restart failed - use backup agent
            await self.orchestrator.blacklist_agent(agent_id, reason="restart_failed")
            await self.orchestrator.find_backup_agent(supervised.agent.capabilities)

    def _can_restart(self, supervised: SupervisedAgent) -> bool:
        """Check if agent can be restarted (rate limiting)."""
        if supervised.restart_count >= supervised.max_restarts:
            # Check if restart window expired
            if supervised.last_restart_time:
                time_since_restart = time.now() - supervised.last_restart_time
                if time_since_restart < supervised.restart_window:
                    return False  # Too many restarts too quickly
                else:
                    # Window expired, reset counter
                    supervised.restart_count = 0
        return True

  ✅ Orchestrator: Blacklist crashed agents, select backups

async def blacklist_agent(self, agent_id: str, reason: str):
    """Blacklist crashed agent, prevent future selection."""
    self.blacklisted_agents[agent_id] = {
        "reason": reason,
        "blacklisted_at": time.now(),
        "expires_at": time.now() + 300  # Blacklist for 5 minutes
    }

async def find_backup_agent(self, capabilities: List[str]):
    """Find backup agent with same capabilities."""
    for agent in self.available_agents:
        if (agent.id not in self.blacklisted_agents and
            agent.has_capabilities(capabilities)):
            return agent

    # No backup - create new agent dynamically (ADR-0086)
    return await self.agent_factory.create_agent(capabilities)

  ✅ User experience: "Still analyzing, one moment..." (transparent retry)
  ✅ No technical errors exposed, seamless recovery
```

#### Scenario 6.3: **Conflicting Requests (Simultaneous Multi-Device)**

```
Device 1 (T0):      "Book dinner at 7pm"
Device 2 (T0+0.5s): "Book dinner at 8pm"

Problem:
  • Same user, 2 devices, conflicting requests
  • Which one wins? Last-write-wins? Ask user?
  • Need conflict resolution strategy

Solution:
  ✅ SessionState: Add multi-device conflict detection

@dataclass
class ControlSection:
    """Extended SessionState.control for multi-device conflicts."""
    conflict_log: List[ConflictingRequest]
    conflict_resolution_strategy: str = "ask_user"  # "ask_user", "last_write_wins", "merge"

class ConflictingRequest:
    request_1: UserMessage
    request_2: UserMessage
    device_1: str  # "phone", "laptop", "tablet"
    device_2: str
    conflict_type: str  # "parameter_mismatch", "contradictory_intent"
    resolution: Optional[str] = None  # Which one won
    resolved_at: Optional[float] = None

  ✅ ConciergeAgent: Detect conflicts from multiple devices

async def detect_multi_device_conflict(self, new_msg: UserMessage) -> Optional[Conflict]:
    """Detect if new message conflicts with recent message from different device."""

    # Check recent messages (last 5 seconds) from different devices
    recent_msgs = [
        msg for msg in self.session_state.scoreboard.recent_turns
        if (time.now() - msg.timestamp < 5.0 and
            msg.device_id != new_msg.device_id)
    ]

    for prev_msg in recent_msgs:
        # Use LLM to detect conflicts
        conflict_check = await self.model_hub.complete(
            agent_id="concierge",
            system_prompt="""
Detect if two messages from different devices are conflicting.

CONFLICTING examples:
- "Book dinner at 7pm" vs "Book dinner at 8pm" (same intent, different time)
- "Cancel my appointment" vs "Confirm my appointment" (opposite actions)

NOT CONFLICTING:
- "What's the weather?" vs "Book dinner" (different intents)
- "Book dinner at 7pm" vs "Also invite Mom" (complementary)

Return JSON: {"is_conflict": true|false, "conflict_type": "...", "reasoning": "..."}
""",
            user_prompt=f"""
Message 1 ({prev_msg.device_id}): "{prev_msg.text}"
Message 2 ({new_msg.device_id}): "{new_msg.text}"

Are these conflicting?
""",
            temperature=0.1,
            response_format="json"
        )

        result = json.loads(conflict_check)
        if result["is_conflict"]:
            return Conflict(
                msg_1=prev_msg,
                msg_2=new_msg,
                conflict_type=result["conflict_type"],
                reasoning=result["reasoning"]
            )

    return None

  ✅ ConciergeAgent: Resolve conflicts based on strategy

async def resolve_conflict(self, conflict: Conflict):
    """Resolve multi-device conflict based on strategy."""

    strategy = self.session_state.control.conflict_resolution_strategy

    if strategy == "ask_user":
        # ASK user which device's request to honor
        clarification = f"""
You requested "{conflict.msg_1.text}" on {conflict.msg_1.device_id},
but then "{conflict.msg_2.text}" on {conflict.msg_2.device_id}.

Which would you like me to do?
1. {conflict.msg_1.text} ({conflict.msg_1.device_id})
2. {conflict.msg_2.text} ({conflict.msg_2.device_id})
"""

        # Send clarification to both devices
        await self.broadcast_to_devices(clarification,
            [conflict.msg_1.device_id, conflict.msg_2.device_id])

        # Wait for user response
        self.session_state.control.pending_conflict_resolution = conflict
        return

    elif strategy == "last_write_wins":
        # CANCEL first request, honor second
        await self.orchestrator.cancel_task(conflict.msg_1.task_id)
        await self.process_message(conflict.msg_2.text)

        # Notify first device
        await self.send_to_device(
            f"Cancelled '{conflict.msg_1.text}' - you requested '{conflict.msg_2.text}' on {conflict.msg_2.device_id}",
            conflict.msg_1.device_id
        )

    elif strategy == "merge":
        # TRY to merge if complementary (e.g., "Book dinner" + "Invite Mom")
        # Not applicable for true conflicts, fall back to ask_user
        pass

    # Log resolution
    self.session_state.control.conflict_log.append(ConflictingRequest(
        request_1=conflict.msg_1,
        request_2=conflict.msg_2,
        device_1=conflict.msg_1.device_id,
        device_2=conflict.msg_2.device_id,
        conflict_type=conflict.conflict_type,
        resolution=strategy,
        resolved_at=time.now()
    ))

  ✅ Multi-device sync (ADR P07): Propagate resolution to all devices
  ✅ User chooses which request wins, other cancelled gracefully
```

---

### Category 7: Privacy & Safety Interruptions

#### Scenario 7.1: **User Realizes Sensitive Data Shared**

```
User (T0):      "Book appointment with Dr. Smith for my depression treatment"
User (T0+1s):   "Wait, delete that, don't save it"

Problem:
  • Sensitive data (RED band) already captured
  • User wants IMMEDIATE deletion (GDPR right)
  • MemoryWriterAgent may have already written to K0

Solution:
  ✅ ConciergeAgent: Detect URGENT deletion intent with highest priority

async def detect_deletion_intent(self, msg: str) -> DeletionIntent:
    """Detect if user wants to delete/redact previous message."""
    deletion_phrases = ["delete", "don't save", "remove that", "forget that", "erase"]

    if any(phrase in msg.lower() for phrase in deletion_phrases):
        return DeletionIntent(
            is_deletion=True,
            urgency="URGENT",  # Highest priority - GDPR right
            scope="previous_message",
            reason="user_requested"
        )
    return None

  ✅ Emergency deletion protocol with 3-tier cascade:

async def execute_emergency_deletion(self, deletion: DeletionIntent):
    """
    TIER 1: Abort in-flight writes (< 1 second)
    TIER 2: Delete from SessionState (immediate)
    TIER 3: Trigger K0 P11 GDPR erasure (if already persisted)
    """

    # TIER 1: Abort MemoryWriterAgent if still writing
    prev_msg = self.session_state.scoreboard.recent_turns[-2]  # Message before "delete"

    abort_result = await self.message_bus.send(
        agent_id="memory_writer",
        message=AbortWrite(
            message_id=prev_msg.id,
            priority="URGENT",
            reason="user_deletion_request"
        ),
        timeout=0.5  # Very short timeout
    )

    if abort_result.status == "aborted":
        # SUCCESS: Write never happened
        self.session_state.scoreboard.recent_turns.remove(prev_msg)
        return {"status": "deleted", "tier": "in_flight_abort"}

    # TIER 2: Scrub from SessionState immediately
    self.session_state.scoreboard.recent_turns.remove(prev_msg)

    # Remove from beliefs if extracted
    sensitive_beliefs = [
        b for b in self.session_state.beliefs
        if prev_msg.text in b.source_text
    ]
    for belief in sensitive_beliefs:
        self.session_state.beliefs.remove(belief)

    # TIER 3: Check if already written to K0
    if abort_result.status == "already_written":
        # Trigger K0 P11 (GDPR erasure pipeline)
        await self.trigger_k0_gdpr_erasure(
            memory_id=abort_result.memory_id,
            reason="user_deletion_request",
            privacy_band="RED"  # Sensitive data
        )

        return {"status": "deleted", "tier": "k0_erasure_triggered"}

    return {"status": "deleted", "tier": "session_state_only"}

  ✅ MemoryWriterAgent: Check for abort signals before write

class MemoryWriterAgent:
    async def write_memory(self, content: str, metadata: Dict):
        """Write with abort check."""

        # CHECK for abort signal BEFORE writing
        if await self.check_abort_signal(metadata["message_id"]):
            return WriteResult(status="aborted", memory_id=None)

        # Write to K0
        memory_id = await self.k0_client.write_memory(content, metadata)

        # CHECK for abort signal AFTER writing (race condition)
        if await self.check_abort_signal(metadata["message_id"]):
            # Too late - already written, return memory_id for K0 erasure
            return WriteResult(status="already_written", memory_id=memory_id)

        return WriteResult(status="success", memory_id=memory_id)

  ✅ K0 P11 GDPR Erasure Pipeline (existing K0 capability)

async def trigger_k0_gdpr_erasure(self, memory_id: str, reason: str, privacy_band: str):
    """Trigger K0's GDPR erasure pipeline."""
    await self.k0_client.execute_pipeline(
        pipeline="P11_GDPR_ERASURE",
        params={
            "memory_id": memory_id,
            "reason": reason,
            "privacy_band": privacy_band,
            "cascade_delete": True,  # Delete all derived memories
            "audit_log": True  # Log deletion for compliance
        }
    )

  ✅ User confirmation: "Deleted. That information was not saved."
  ✅ Audit trail: Log deletion request (NOT the content itself)
```

#### Scenario 7.2: **User Realizes Request Violates Safety**

```
User (T0):      "Find ways to hide money from IRS"
System (T0+1s): [Safety Watch agent flags as risky]
System (T0+2s): "I can't help with tax evasion..."
User (T0+3s):   "Sorry, I meant legal tax optimization strategies"

Problem:
  • Initial query flagged as unsafe
  • User clarifies intent was legitimate
  • System should allow rephrased query

Solution:
  ✅ Safety Arbiter: Implement re-evaluation protocol (ADR-0007 Tier 2)

class SafetyArbiter:
    """
    Tier 2 validation in PlannerAgent (ADR-0007).
    Handles safety re-evaluation when user clarifies intent.
    """

    async def evaluate_safety(self, query: str, context: SessionState) -> SafetyResult:
        """Evaluate query safety with context awareness."""

        # CHECK if this is a rephrasing after safety block
        recent_safety_block = self._check_recent_safety_block(context)

        if recent_safety_block:
            # User is rephrasing - evaluate with benefit of doubt
            return await self._evaluate_rephrased_query(
                original_query=recent_safety_block.query,
                rephrased_query=query,
                context=context
            )

        # Normal safety evaluation
        return await self._evaluate_query_safety(query, context)

    async def _evaluate_rephrased_query(
        self,
        original_query: str,
        rephrased_query: str,
        context: SessionState
    ) -> SafetyResult:
        """Evaluate rephrased query with clarification context."""

        safety_check = await self.model_hub.complete(
            agent_id="safety_arbiter",
            system_prompt="""
You are a safety arbiter evaluating rephrased queries.

CONTEXT: User's original query was blocked for safety. They are now clarifying intent.

EVALUATION:
- If rephrased query clarifies LEGITIMATE intent → ALLOW
- If rephrased query still violates safety → BLOCK
- Give benefit of doubt to clarifications

UNSAFE patterns:
- Tax evasion, fraud, illegal activities
- Harm to self or others
- Privacy violations

SAFE clarifications:
- "Legal tax optimization" (clarifies from "hide money from IRS")
- "Research violent crime statistics" (clarifies from "how to hurt someone")

Return JSON: {
  "is_safe": true|false,
  "confidence": 0.0-1.0,
  "reasoning": "...",
  "is_legitimate_clarification": true|false
}
""",
            user_prompt=f"""
Original query (BLOCKED): "{original_query}"
Rephrased query: "{rephrased_query}"

User clarification phrases: {context.scoreboard.recent_turns[-1].text}
  (e.g., "I meant", "sorry", "let me clarify")

Is the rephrased query safe and legitimate?
""",
            temperature=0.1,
            response_format="json"
        )

        result = json.loads(safety_check)

        if result["is_safe"] and result["is_legitimate_clarification"]:
            # ALLOW with clean slate
            context.meta.safety_flag_resolved = True
            context.meta.last_safety_block = None

            return SafetyResult(
                is_safe=True,
                confidence=result["confidence"],
                reasoning="Legitimate clarification after safety block",
                allow_execution=True
            )
        else:
            # STILL unsafe - block again
            return SafetyResult(
                is_safe=False,
                confidence=result["confidence"],
                reasoning=result["reasoning"],
                allow_execution=False
            )

    def _check_recent_safety_block(self, context: SessionState) -> Optional[SafetyBlock]:
        """Check if user was recently blocked for safety."""

        # Look for safety blocks in last 10 seconds
        if context.meta.last_safety_block:
            time_since_block = time.now() - context.meta.last_safety_block.timestamp
            if time_since_block < 10.0:
                return context.meta.last_safety_block

        return None

  ✅ SessionState: Track safety events for re-evaluation

@dataclass
class MetaSection:
    """SessionState.meta - Metadata and safety tracking."""
    last_safety_block: Optional[SafetyBlock] = None
    safety_flag_resolved: bool = False
    safety_violations: List[SafetyViolation] = field(default_factory=list)

class SafetyBlock:
    query: str
    reason: str
    timestamp: float
    user_acknowledged: bool = False  # User said "sorry", "I meant"

  ✅ ConciergeAgent: Detect clarification intent

async def detect_clarification_after_safety_block(self, msg: str) -> bool:
    """Detect if user is clarifying after safety block."""

    clarification_phrases = [
        "i meant", "sorry", "let me clarify", "what i meant was",
        "no i mean", "actually i mean", "i'm asking about"
    ]

    if any(phrase in msg.lower() for phrase in clarification_phrases):
        if self.session_state.meta.last_safety_block:
            self.session_state.meta.last_safety_block.user_acknowledged = True
            return True

    return False

  ✅ User experience:
    1. Original query blocked: "I can't help with tax evasion..."
    2. User clarifies: "Sorry, I meant legal tax optimization"
    3. System re-evaluates with benefit of doubt
    4. If legitimate → Process query with clean slate
    5. If still unsafe → Block with clear explanation

  ✅ Audit logging: Track safety_flag_resolved events (not penalize user)
```

---

## ✅ Final Scenario Resolution Status: 23/23 COMPLETE (100%)

### Summary: All Real-World Chat Scenarios Resolved

| Category | Scenarios | Status | Implementation |
|----------|-----------|--------|----------------|
| **User Corrections & Rapid Input** | 3/3 | ✅ Complete | ConciergeAgent meta-intents: CORRECTION, RAPID_BATCH, REFINEMENT |
| **Mid-Response Interruptions** | 3/3 | ✅ Complete | DialogueAgent.handle_interruption(), TOPIC_CHANGE, REFINEMENT |
| **System Delays & User Impatience** | 3/3 | ✅ Complete | STATUS_CHECK, CANCELLATION, RETRY meta-intents |
| **Multi-Turn Dependencies** | 3/3 | ✅ Complete | SessionState.control.workflow_state, AMENDMENT, referents |
| **Conversational Noise** | 3/3 | ✅ Complete | ACKNOWLEDGMENT, SMALL_TALK, AMBIGUOUS_QUERY meta-intents |
| **Error Recovery & Edge Cases** | 3/3 | ✅ Complete | Orchestrator fallback, AgentSupervisor, multi-device conflicts |
| **Privacy & Safety** | 2/2 | ✅ Complete | Emergency deletion protocol, SafetyArbiter re-evaluation |
| **TOTAL** | **23/23** | **✅ 100%** | **All scenarios resolved by existing architecture extensions** |

### Key Implementations Added

**1. DialogueAgent Streaming Interruption (Scenario 2.1)**

- `DialogueAgent.handle_interruption()` - Stop streaming, save partial, yield control
- `SessionState.scoreboard.partial_responses` - Track interrupted responses
- MemoryWriterAgent abort mechanism

**2. Workflow State Machine (Scenario 4.3)**

- `SessionState.control.workflow_state` - Multi-step workflow tracking
- `WorkflowStep` with dependencies and results
- ConciergeAgent workflow advancement logic

**3. Orchestrator API Fallback (Scenario 6.1)**

- `K1Orchestrator.execute_with_fallback()` - Automatic backup API retry
- `SessionState.control.api_health` - Circuit breaker tracking
- Graceful failure with alternatives

**4. Agent Supervision & Crash Recovery (Scenario 6.2)**

- `AgentSupervisor` class - Actor Model supervision (ADR-0002)
- Heartbeat monitoring, automatic restart with rate limiting
- Blacklist crashed agents, select backups transparently

**5. Multi-Device Conflict Resolution (Scenario 6.3)**

- `SessionState.control.conflict_log` - Track conflicting requests
- `ConciergeAgent.detect_multi_device_conflict()` - LLM-based conflict detection
- User confirmation protocol ("Which time: 7pm on phone or 8pm on laptop?")

**6. Emergency Deletion Protocol (Scenario 7.1)**

- 3-tier cascade: Abort in-flight → Scrub SessionState → Trigger K0 P11
- MemoryWriterAgent abort signal checking
- GDPR compliance with audit trail

**7. Safety Re-Evaluation (Scenario 7.2)**

- `SafetyArbiter.evaluate_rephrased_query()` - Clarification-aware safety check
- `SessionState.meta.last_safety_block` - Track safety events
- Benefit of doubt for legitimate clarifications

### Architecture Insight

**All 23 scenarios resolved by EXTENDING existing components, not creating new parallel systems:**

- **ConciergeAgent**: Handles 11 meta-intents + workflow detection
- **SessionState**: Extended with workflow_state, conflict_log, api_health, partial_responses
- **K1 Orchestrator**: Added fallback strategy, blacklist management
- **New Components**: AgentSupervisor (ADR-0002), SafetyArbiter (ADR-0007)
- **MemoryWriterAgent**: Added abort checking
- **DialogueAgent**: Added interruption protocol

**No separate classifier classes needed** - ConciergeAgent's comprehensive LLM system prompt handles everything! 🎯

---

## 🏗️ How Our Architecture Handles Real-World Chat Scenarios

**Key Insight:** All these scenarios are handled by **ConciergeAgent's LLM system prompt**, not separate systems. ConciergeAgent is the single entry point that routes appropriately.

### Architecture Components (Already Established)

```
USER MESSAGE
    ↓
ConciergeAgent (Tier 1, Always Active)
    ├─ Classifies meta-intent (LLM-powered)
    ├─ Updates SessionState (6 sections)
    ├─ Routes to Orchestrator OR handles directly
    ↓
K1 Orchestrator (if routed)
    ├─ 3-Phase Coordination (ADR-0006f)
    ├─ Dynamic Agent Creation (ADR-0086)
    ├─ Parallel DAG Execution (ADR-0006c)
    ↓
Specialist Agents (Tier 2, Dynamic)
    ├─ Receive rich AgentContext (affect, self-model, conversation)
    ├─ LLM-powered with context in system prompt
    ↓
MemoryWriterAgent (Tier 3, Always Active)
    ├─ Background bookkeeping (P02)
    ├─ Enrichment after response
```

### ConciergeAgent: Comprehensive LLM System Prompt

**ConciergeAgent handles ALL scenarios through ONE LLM system prompt:**

```python
class ConciergeAgent:
    """
    Tier 1: Master coordinator, always active.
    Single entry point for all user messages.
    Handles meta-intent classification and routing decisions.
    """

    def __init__(self, model_hub: ModelHub, session_state: SessionState):
        self.model_hub = model_hub
        self.session_state = session_state
        self.system_prompt = self._build_comprehensive_system_prompt()

    def _build_comprehensive_system_prompt(self) -> str:
        """
        ConciergeAgent's comprehensive LLM system prompt.
        Handles ALL real-world chat scenarios in ONE prompt.
        """
        return """
You are ConciergeAgent, the master coordinator for a family AI assistant.

Your responsibilities:
1. Classify user intent and meta-intent
2. Update SessionState conversation tracking
3. Route to K1 Orchestrator OR handle directly
4. Manage multi-turn workflows
5. Handle corrections, amendments, interruptions gracefully

---

META-INTENT CLASSIFICATION (Handle These First):

1. **ACKNOWLEDGMENT** (no orchestration needed)
   - User: "ok", "thanks", "got it", "sounds good"
   - Context: Short message after system response
   - Action: Update SessionState.meta.user_acknowledged = True
   - Response: Brief acknowledgment ("You're welcome!"), don't trigger orchestration

2. **STATUS_CHECK** (system delayed, user checking in)
   - User: "are you there?", "hello?", "still working?", "what's taking so long?"
   - Context: Active task running > 10 seconds
   - Action: Return progress update from SessionState.control.active_tasks
   - Response: "Still searching flights, found 12 so far..." (specific progress)
   - Don't cancel ongoing task

3. **CANCELLATION** (user wants to stop)
   - User: "never mind", "stop", "forget it", "cancel that", "don't worry about it"
   - Context: Active task or recent request
   - Action: Send CANCEL_TASK to Orchestrator with save_partial=True
   - Update: SessionState.control.active_tasks[task_id].status = "cancelled"
   - Response: "Cancelled. I saved what I found so far."

4. **RETRY** (after failure)
   - User: "try again", "retry", "one more time", "can you try that again?"
   - Context: Recent failed task (SessionState.control.last_failed_task)
   - Action: Send RETRY_TASK to Orchestrator with fallback_strategy=True
   - Response: "Retrying with a different approach..."

5. **CORRECTION** (typo fix, rapid follow-up < 2s)
   - User (T0): "Book dinner at Italin restaurant"
   - User (T0+0.5s): "Italian* restaurant"
   - Detection criteria:
     • Rapid follow-up (<2s since last message)
     • High text similarity (>80%, one word different)
     • Correction markers ("*", "I meant", "sorry, typo")
   - Action: Cancel first message (supersede), merge correction into new intent
   - Update: SessionState.scoreboard.recent_turns[-1].superseded_by = msg_2
   - Route corrected query to Orchestrator

6. **RAPID_BATCH** (multiple messages in quick succession < 500ms)
   - User (T0): "What's Mom's PT schedule?"
   - User (T0+0.3s): "Also check her medications"
   - User (T0+0.5s): "And when is Alice visiting?"
   - Detection: Multiple messages < 500ms apart, same/related domain
   - Action: Wait for pause (500ms buffer), merge into single multi-part query
   - Update: SessionState.scoreboard.turn_id (group under single turn)
   - Route merged query to Orchestrator as multi-domain task

7. **AMENDMENT** (modifying previous completed action)
   - User (T0): "Book dinner for 2 at 7pm"
   - System: [Booking confirmed at 7pm for 2 people]
   - User (T0+3s): "Actually make it for 4 people"
   - Detection criteria:
     • Recent action (<30s, SessionState.control.last_action_id exists)
     • Modification intent ("actually", "change to", "make it")
     • Same domain as previous action
   - Action: Send COMPENSATE_AND_AMEND to Orchestrator (Saga pattern)
   - Use: SessionState.control.last_action_id for compensation
   - Response: "Updating reservation from 2 to 4 people..."

8. **REFINEMENT** (adding constraint to ongoing query)
   - System: "I found 5 restaurants available at 7pm..."
   - User: "Only Italian restaurants"
   - Detection: Similar domain, adds constraint, system mid-response or just completed
   - Action: Send REFINE_TASK to Orchestrator (filter current results, don't restart)
   - Update: SessionState.control.active_tasks[task_id].refinements.append(...)
   - Response: "Filtering to Italian restaurants only..."

9. **TOPIC_CHANGE** (switching domains mid-conversation)
   - System: "Mom's recovery is progressing well with PT..."
   - User: "What's the weather tomorrow?"
   - Detection criteria:
     • Completely different domain (health → weather)
     • No connection to current QUD (Questions Under Discussion)
     • Sudden shift in topic
   - Action:
     • Push old QUD to history
     • Cancel old task if streaming
     • Set new QUD
   - Update: SessionState.scoreboard.qud_history.append(old_qud)
   - Route new query to Orchestrator

10. **AMBIGUOUS_QUERY** (underspecified, needs clarification)
    - User: "What about Mom?"
    - Detection: Low confidence (<0.6), missing key details, vague pronoun usage
    - Action: Don't route to orchestrator yet, ask clarification question
    - Generate clarification: "What would you like to know about Mom? Her PT schedule, recovery progress, medications, or something else?"
    - Update: SessionState.scoreboard.qud = "clarifying_intent"
    - Wait for clarifying response before routing

11. **SMALL_TALK** (social interaction, no task)
    - User: "How are you?", "What's up?", "Good morning"
    - Detection: Social greeting, no task intent
    - Action: Handle directly, don't route to orchestrator
    - Response: Brief, friendly response ("I'm doing well! How can I help you today?")
    - Update: SessionState.scoreboard (log turn, maintain conversation flow)

---

TASK-ORIENTED CLASSIFICATION (Route to Orchestrator):

If none of the above meta-intents match, classify as task intent:
- Extract: intent, domains, required slots, entities
- Check: SessionState.beliefs for context pre-fill (recent names, locations, preferences)
- Check: SessionState.scoreboard.referents for pronoun resolution ("it", "that", "which one")
- Build: Task envelope with full context
- Route: to K1 Orchestrator for 3-phase coordination

---

SESSIONSTATE UPDATES (Your Responsibility Every Message):

For every message, update:
1. **SessionState.scoreboard.recent_turns** - Append turn with affect detection
2. **SessionState.scoreboard.topics_discussed** - Track domain shifts
3. **SessionState.scoreboard.qud** - Update Questions Under Discussion
4. **SessionState.scoreboard.referents** - Track "it", "that", "which one" (what they refer to)
5. **SessionState.control.active_tasks** - Track ongoing orchestrations
6. **SessionState.affect** - Detect emotional state via LLM emotion analysis
7. **SessionState.self_model** - Extract self-perception beliefs from user message
8. **SessionState.control.last_query** - Save query for amendment detection
9. **SessionState.control.last_query_time** - Timestamp for correction detection

---

ROUTING DECISIONS:

- **Meta-intents (1-11 above)**: Handle directly, don't route to orchestrator
  - ACKNOWLEDGMENT, SMALL_TALK → respond directly
  - STATUS_CHECK → return progress from active_tasks
  - CANCELLATION, RETRY, AMENDMENT, REFINEMENT → send task command to orchestrator
  - TOPIC_CHANGE → cancel old task, route new query
  - AMBIGUOUS → ask clarification first, route after clarified

- **Task-intents**: Build task envelope, route to K1 Orchestrator
  - Include: intent, domains, slots, required agents, parallel execution flag
  - Include: rich context from SessionState (beliefs, affect, conversation history)

---

CONVERSATION CONTEXT (Always Consider):

Input from SessionState:
- recent_turns (last 10 turns with affect tags, timestamps)
- topics_discussed (conversation history: ["health", "finance", "social"])
- active_tasks (what's currently running, progress %)
- last_action_id (for amendments/rollbacks)
- last_failed_task (for retries with context)
- last_query + last_query_time (for correction detection)
- user_affect (current emotional state: {"emotion": "anxious", "intensity": 0.7})
- user_self_perception (beliefs about self: ["worried about costs", "wants best for Mom"])
- current_qud (current question under discussion)
- referents (what "it", "that", "which one" refer to)

---

OUTPUT FORMAT:

Return JSON:
{
  "classification": "ACKNOWLEDGMENT|TASK_INTENT|CANCELLATION|CORRECTION|AMENDMENT|REFINEMENT|TOPIC_CHANGE|AMBIGUOUS|STATUS_CHECK|RETRY|SMALL_TALK|RAPID_BATCH",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation of why this classification",
  "action": "handle_directly|route_to_orchestrator|ask_clarification|cancel_task|retry_task|amend_task|refine_task|merge_messages",

  "sessionstate_updates": {
    "affect": {"emotion": "anxious|neutral|happy|frustrated", "intensity": 0.0-1.0},
    "self_model_beliefs": ["belief extracted from message"],
    "qud": "current question under discussion",
    "topics": ["domain1", "domain2"],
    "referents": {"it": "Mom's PT schedule", "that": "the reservation"}
  },

  "orchestrator_task": {  // Only if action = route_to_orchestrator
    "intent": "evaluate_pt_extension",
    "domains": ["health", "finance"],
    "slots": {"patient": "Mom", "timeframe": "next month"},
    "requires_parallel": true,
    "agent_context": {  // Rich context for specialist agents
      "affect": {...},
      "self_model": {...},
      "conversation_summary": "User is concerned about costs...",
      "recent_turns": [...]
    }
  },

  "task_command": {  // Only if action = cancel_task|retry_task|amend_task|refine_task
    "type": "CANCEL|RETRY|COMPENSATE_AND_AMEND|REFINE",
    "task_id": "task_123",
    "save_partial": true,
    "amendments": {...},  // For AMEND
    "refinements": {"filter": "Italian only"},  // For REFINE
    "fallback_strategy": true  // For RETRY
  },

  "direct_response": "..."  // Only if action = handle_directly|ask_clarification
}
"""

    async def process_message(self, user_msg: str) -> ConciergeDecision:
        """
        Single entry point for all user messages.
        ConciergeAgent's LLM classifies intent and determines routing.
        """

        # BUILD USER PROMPT with full conversation context
        time_since_last = self._time_since_last_message()

        user_prompt = f"""
Current message: "{user_msg}"

CONTEXT:
- Previous message: "{self.session_state.scoreboard.recent_turns[-1].text if self.session_state.scoreboard.recent_turns else 'None'}"
- Time since last message: {time_since_last}ms
- System state: {self._get_system_state()}  # idle, processing, streaming
- Active tasks: {self._get_active_tasks_summary()}  # e.g., "searching_flights: 65% complete"
- Last action: {self.session_state.control.last_action_id} at {self.session_state.control.last_action_time}
- Current QUD: "{self.session_state.scoreboard.qud}"
- Topics discussed: {self.session_state.scoreboard.topics_discussed}
- User affect: {self.session_state.affect.current_emotion} (intensity: {self.session_state.affect.intensity})
- Referents: {self.session_state.scoreboard.referents}  # "it" → "Mom's PT schedule"

Classify intent and determine action.
"""

        # LLM PROCESSES message with comprehensive system prompt
        response = await self.model_hub.complete(
            agent_id="concierge",
            system_prompt=self.system_prompt,
            user_prompt=user_prompt,
            temperature=0.1,  # Low temp for consistent classification
            response_format="json"
        )

        decision = json.loads(response)

        # UPDATE SESSIONSTATE based on LLM's analysis
        await self._update_session_state(user_msg, decision["sessionstate_updates"])

        # ROUTE based on action
        if decision["action"] == "route_to_orchestrator":
            # Route to K1 Orchestrator with task envelope
            return await self._route_to_orchestrator(decision["orchestrator_task"])

        elif decision["action"] in ["cancel_task", "retry_task", "amend_task", "refine_task"]:
            # Send task management command to Orchestrator
            return await self._send_task_command(decision["task_command"])

        elif decision["action"] == "handle_directly":
            # Handle directly (acknowledgment, status check, small talk)
            return ConciergeDecision(
                response=decision["direct_response"],
                route_to_orchestrator=False
            )

        elif decision["action"] == "ask_clarification":
            # Ask clarification, don't route yet
            return ConciergeDecision(
                response=decision["direct_response"],
                awaiting_clarification=True
            )

        elif decision["action"] == "merge_messages":
            # Wait for more rapid messages (500ms buffer)
            await asyncio.sleep(0.5)
            # Check if more messages arrived, merge them
            merged_msgs = await self._collect_rapid_messages()
            # Re-process merged message
            return await self.process_message(merged_msgs)

    async def _update_session_state(self, user_msg: str, updates: Dict):
        """
        Update SessionState based on ConciergeAgent's LLM analysis.
        """

        # 1. UPDATE AFFECT (emotional state)
        if "affect" in updates:
            self.session_state.affect.current_emotion = updates["affect"]["emotion"]
            self.session_state.affect.intensity = updates["affect"]["intensity"]
            self.session_state.affect.history.append({
                "emotion": updates["affect"]["emotion"],
                "intensity": updates["affect"]["intensity"],
                "timestamp": time.now()
            })

        # 2. UPDATE SELF-MODEL (beliefs about self)
        if "self_model_beliefs" in updates:
            for belief in updates["self_model_beliefs"]:
                if belief not in self.session_state.self_model.current_beliefs:
                    self.session_state.self_model.current_beliefs.append(belief)

        # 3. UPDATE SCOREBOARD (conversation tracking)
        if "qud" in updates:
            # Push old QUD to history if changing topics
            if self.session_state.scoreboard.qud != updates["qud"]:
                self.session_state.scoreboard.qud_history.append(
                    self.session_state.scoreboard.qud
                )
            self.session_state.scoreboard.qud = updates["qud"]

        if "topics" in updates:
            for topic in updates["topics"]:
                if topic not in self.session_state.scoreboard.topics_discussed:
                    self.session_state.scoreboard.topics_discussed.append(topic)

        if "referents" in updates:
            # Track what "it", "that", "which one" refer to
            self.session_state.scoreboard.referents.update(updates["referents"])

        # 4. UPDATE CONTROL (last query tracking for amendments/corrections)
        self.session_state.control.last_query = user_msg
        self.session_state.control.last_query_time = time.now()

        # 5. APPEND TO RECENT TURNS
        self.session_state.scoreboard.recent_turns.append({
            "role": "user",
            "text": user_msg,
            "affect": updates.get("affect", {}),
            "timestamp": time.now()
        })

    async def _route_to_orchestrator(self, task: Dict) -> ConciergeDecision:
        """
        Route task to K1 Orchestrator with rich context.
        """
        task_envelope = TaskEnvelope(
            intent=task["intent"],
            domains=task["domains"],
            slots=task["slots"],
            requires_parallel=task["requires_parallel"],
            agent_context=AgentContext(
                affect=task["agent_context"]["affect"],
                self_model=task["agent_context"]["self_model"],
                conversation_summary=task["agent_context"]["conversation_summary"],
                conversation_history=task["agent_context"]["recent_turns"]
            ),
            cognitive_trace_id=self.session_state.cognitive_trace_id
        )

        # Send to K1 Orchestrator
        task_id = await self.orchestrator.coordinate_task(task_envelope)

        # Track in SessionState
        self.session_state.control.active_tasks[task_id] = {
            "status": "negotiating",
            "started_at": time.now(),
            "task": task_envelope
        }

        return ConciergeDecision(
            task_id=task_id,
            route_to_orchestrator=True
        )

    async def _send_task_command(self, command: Dict) -> ConciergeDecision:
        """
        Send task management command to Orchestrator.
        """
        if command["type"] == "CANCEL":
            await self.orchestrator.cancel_task(
                task_id=command["task_id"],
                save_partial=command["save_partial"]
            )
            self.session_state.control.active_tasks[command["task_id"]]["status"] = "cancelled"
            return ConciergeDecision(response="Task cancelled.")

        elif command["type"] == "RETRY":
            task_id = await self.orchestrator.retry_task(
                task_id=self.session_state.control.last_failed_task["task_id"],
                fallback_strategy=command["fallback_strategy"]
            )
            return ConciergeDecision(response="Retrying with a different approach...")

        elif command["type"] == "COMPENSATE_AND_AMEND":
            # Saga pattern: compensate previous action + execute new
            task_id = await self.orchestrator.compensate_and_amend(
                original_task_id=self.session_state.control.last_action_id,
                amendments=command["amendments"]
            )
            return ConciergeDecision(response="Updating your request...")

        elif command["type"] == "REFINE":
            # Add constraints to ongoing task without restart
            await self.orchestrator.refine_task(
                task_id=command["task_id"],
                refinements=command["refinements"]
            )
            return ConciergeDecision(response="Refining results...")
```

### K1 Orchestrator Integration (ADR-0006f: 3-Phase Coordination)

**Orchestrator receives task commands from ConciergeAgent:**

```python
class K1Orchestrator:
    """
    Pure actor (no LLM), coordinates specialist agents.
    Receives tasks and commands from ConciergeAgent.
    """

    async def cancel_task(self, task_id: str, save_partial: bool = True):
        """
        Cancel ongoing task, optionally save partial results.
        """
        task = self.active_tasks[task_id]

        # Broadcast CANCEL to all agents working on this task
        for agent_id in task.assigned_agents:
            await self.message_bus.send(
                agent_id=agent_id,
                message=CancelTask(task_id=task_id, save_partial=save_partial)
            )

        # Save partial results if requested
        if save_partial and task.partial_results:
            await self.save_partial_results(task_id, task.partial_results)

        # Update task status
        task.status = TaskStatus.CANCELLED

    async def retry_task(self, task_id: str, fallback_strategy: bool = True):
        """
        Retry failed task with fallback strategy.
        """
        original_task = self.failed_tasks[task_id]

        # Use fallback strategy: different agents, reduced scope
        if fallback_strategy:
            original_task.fallback = True
            original_task.priority = TaskPriority.HIGH

        # Re-run 3-phase coordination
        new_task_id = await self.coordinate_task(original_task)
        return new_task_id

    async def compensate_and_amend(self, original_task_id: str, amendments: Dict):
        """
        Saga pattern: compensate previous action, then execute amended task.
        """
        original_task = self.completed_tasks[original_task_id]

        # STEP 1: COMPENSATE (rollback previous action)
        compensation_actions = self._generate_compensation_actions(original_task)
        for action in compensation_actions:
            await self._execute_compensation(action)

        # STEP 2: AMEND (execute new task with updated parameters)
        amended_task = original_task.copy()
        amended_task.slots.update(amendments)
        amended_task.is_amendment = True
        amended_task.original_task_id = original_task_id

        new_task_id = await self.coordinate_task(amended_task)
        return new_task_id

    async def refine_task(self, task_id: str, refinements: Dict):
        """
        Add constraints to ongoing task without restart (filter results).
        """
        task = self.active_tasks[task_id]

        # Broadcast REFINE to agents (they filter current results)
        for agent_id in task.assigned_agents:
            await self.message_bus.send(
                agent_id=agent_id,
                message=RefineTask(task_id=task_id, refinements=refinements)
            )

        # Update task refinements
        task.refinements.append(refinements)
```

### SessionState Integration (ADR-0017: 6-Section Design)

**SessionState tracks all conversation state for ConciergeAgent's decisions:**

```python
@dataclass
class ControlSection:
    """SessionState.control - Task management and workflow tracking."""
    active_tasks: Dict[str, TaskState]  # Currently running tasks
    last_action_id: Optional[str]  # For amendments (Saga compensation)
    last_action_time: float  # For amendment detection (<30s window)
    last_failed_task: Optional[FailedTask]  # For retry with context
    last_query: str  # For correction/amendment detection
    last_query_time: float  # For correction detection (<2s window)
    workflow_state: Optional[WorkflowState]  # Multi-turn workflow tracking
    pending_clarification: Optional[str]  # Waiting for user clarification

@dataclass
class ScoreboardSection:
    """SessionState.scoreboard - Conversation tracking."""
    recent_turns: List[Turn]  # Last 10 turns with affect, timestamps
    topics_discussed: List[str]  # ["health", "finance", "social"]
    qud: str  # Current Question Under Discussion
    qud_history: List[str]  # Previous QUDs (for topic change detection)
    referents: Dict[str, str]  # {"it": "Mom's PT schedule", "that": "the reservation"}
    turn_id: int  # For grouping rapid messages under single turn
```

### Summary: Aligned with Established Architecture

**Real-world scenarios are handled by existing components:**

1. **ConciergeAgent** (Tier 1, Always Active)
   - Single entry point for ALL user messages
   - Comprehensive LLM system prompt handles ALL meta-intent classification
   - Updates SessionState every message
   - Routes to Orchestrator OR handles directly
   - No separate classifier classes needed

2. **SessionState** (ADR-0017: 6-Section Design)
   - Tracks conversation state for all scenarios
   - control section: task management, last query tracking, workflow state
   - scoreboard section: conversation tracking, topics, referents, QUD
   - affect section: emotional state tracking
   - self_model section: user beliefs tracking

3. **K1 Orchestrator** (ADR-0006f: 3-Phase Coordination)
   - Receives task commands from ConciergeAgent (CANCEL, RETRY, AMEND, REFINE)
   - Implements Saga pattern for compensations
   - Manages agent lifecycle and parallel execution
   - Pure actor (no LLM), coordinates specialist agents

4. **Specialist Agents** (Tier 2, Dynamic via ADR-0086)
   - Receive rich AgentContext from ConciergeAgent (affect, self-model, conversation history)
   - LLM-powered with context in system prompts
   - Generate naturally empathetic responses based on context

5. **MemoryWriterAgent** (Tier 3, Always Active)
   - Background bookkeeping (P02 memory formation)
   - Enrichment after specialist agent responses
   - Non-blocking, async

**Key Architectural Insight:**
No new systems or parallel classifiers needed. Our existing three-tier architecture handles all 20+ real-world chat scenarios through ConciergeAgent's comprehensive LLM system prompt and proper SessionState tracking.

---

## 📋 Summary: Critical Real-World Scenarios

| Category | Scenarios | Architecture Needs |
|----------|-----------|-------------------|
| **User Corrections** | Typo fix, rapid-fire, amendments | Message batching, cancellation tokens, amendment protocol |
| **Interruptions** | Mid-response stop, topic switch, refinement | Interruption detection, context switching, task refinement |
| **Delays** | Status checks, impatience, errors | Status queries, cancellation, retry with fallback |
| **Multi-Turn** | Amendments, follow-ups, chains | Workflow state, referent tracking, compensation (Saga) |
| **Conversational Noise** | Acknowledgments, small talk, vague queries | Meta-intent classification, clarification prompts |
| **Error Recovery** | API failures, agent crashes, conflicts | Supervisor recovery, conflict resolution, transparent retry |
| **Privacy/Safety** | Deletion requests, safety violations | Urgent deletion, safety re-evaluation, GDPR compliance |

Summarized conversation historyI'll analyze all the real-world chat scenarios and identify the systems/components needed to handle them comprehensively.

Thinking

Based on analyzing all 7 categories of real-world chat scenarios, here are the **systems/components needed** to handle them comprehensively:

## Core Infrastructure (8 Systems)

1. **CancellationToken System** - Token-based task cancellation with propagation
2. **Message Queue with Batching Window** - 500ms buffer for rapid-fire messages
3. **Task Amendment Protocol** - UPDATE_TASK, CANCEL_TASK, RETRY_TASK operations
4. **Workflow State Machine** - Multi-turn conversation state tracking
5. **Streaming Interruption Protocol** - Graceful stop for DialogueAgent mid-response
6. **Progress Heartbeat System** - Keep user informed during long operations
7. **Timeout Manager** - Per-operation timeouts with fallback responses
8. **Context Switch Manager** - Save/restore state when topic changes abruptly

## Intelligence Layer (6 Systems)

9. **Meta-Intent Classifier** - Detect acknowledgments, status checks, cancellations
10. **Ambiguity Resolver** - Handle vague queries ("What about Mom?")
11. **Referent Tracker** - Track "it", "that", "which one" across turns
12. **Dependency Graph Builder** - Link multi-turn actions (find → book → send)
13. **Small Talk Handler** - Respond to "How are you?", "Thanks" without orchestrator
14. **Conflict Resolver** - Handle same-user multi-device conflicts

## Resilience Layer (5 Systems)

15. **Saga Compensation Engine** - Rollback/compensate for amended tasks
16. **Agent Crash Recovery** - Detect and restart failed agents
17. **External API Retry Logic** - Exponential backoff, circuit breaker
18. **Partial Response Preservation** - Save incomplete work before interruption
19. **Fallback Response Generator** - "I'm working on it" when stuck

## Safety & Privacy Layer (4 Systems)

20. **Emergency Stop Protocol** - Immediate halt on "delete that"
21. **Memory Redaction Engine** - Remove specific memories on user request
22. **Safety Guardrails** - Pre-execution risk assessment
23. **Audit Trail Logger** - Track what was deleted/cancelled and why

## SessionState Extensions (3 New Sections)

24. **SessionState.workflow** - Active tasks, last action ID, amendment history
25. **SessionState.interruption_state** - Saved context for resumed tasks
26. **SessionState.conflict_log** - Multi-device request tracking

## Observability & Debugging (3 Systems)

27. **Task Timeline Recorder** - Full timeline of corrections/amendments
28. **User Intent History** - Track intent evolution across rapid messages
29. **Failure Analysis Logger** - Why tasks failed, what was retried

---

**Total: 29 distinct systems/components needed**

**Critical Dependencies:**

- Systems 1-8 (Core) must exist first - foundation for everything else
- Systems 9-14 (Intelligence) depend on Core being stable
- Systems 15-19 (Resilience) integrate with Core cancellation/amendment
- Systems 20-23 (Safety) override all other systems (highest priority)

---

## 🧩 Conversational Intelligence: Slot-Based Dialogue Management

**Problem:** User provides incomplete information requiring back-and-forth clarification.

**Example:**

```
User: "I want to plan a trip to California"
Missing: When? From where? How many people? Budget? Transport? Activities?
```

### Core Concept: Slot Filling State Machine

**Intent Structure:**

```python
intent = {
    "type": "plan_trip",
    "required_slots": {
        "destination": "California",  # ✅ Filled
        "dates": None,                # ❌ Missing
        "origin": None,               # ❌ Missing
        "travelers": None             # ❌ Missing
    },
    "optional_slots": {
        "budget": None,
        "transport_mode": None,
        "interests": []
    },
    "completion": 0.25  # 1/4 required slots (need 75% to proceed)
}
```

### Intelligent Clarification Flow

**T0: Initial Request (Incomplete)**

```
User → "I want to plan a trip to California"
ConciergeAgent extracts:
  - Intent: "plan_trip"
  - Slots filled: {destination: "California"}
  - Completion: 25% (1/4 required)
  - Decision: ROUTE_TO_CLARIFICATION (insufficient)
```

**T0+100ms: Slot Pre-Fill from Context**

```python
# Context-Aware Pre-Fill Engine checks SessionState.beliefs:
pre_fill = {
    "origin": "Phoenix",              # From user profile (home city)
    "travelers": 4,                   # From family profile
    "budget": "$3000-$5000",          # From past trip spending
    "transport_mode": "fly"           # From past preferences
}
# Completion jumps to 100% without asking!
```

**T0+150ms: DialogueAgent Confirms High-Confidence Pre-Fills**

```
DialogueAgent → User:
"I can help plan your California trip! Based on your family, I'm thinking:
- Flying from Phoenix for 4 people
- Budget around $4000
- Dates in the next 2-3 months
Does that sound right, or would you like to adjust anything?"
```

**T1: User Refines**

```
User → "Actually just me and my wife, and we'll drive"
DialogueAgent updates:
  - travelers: 2 (overwrite)
  - transport_mode: "driving" (overwrite)
  - trip_type: "couples" (implicit extraction)
  - Completion: 100% (all required slots confirmed)
```

**T1+100ms: Handoff to PlannerAgent**

```
DialogueAgent → PlannerAgent:
"Complete slot data ready, generate road trip plan for 2 from Phoenix to California"
```

### 6 Key Systems for Conversational Intelligence

**30. Slot Filling State Machine**

- Track required vs optional slots per intent type
- Calculate completion percentage
- Determine when to ask vs when to proceed

**31. Context-Aware Pre-Fill Engine**

- Query `SessionState.beliefs` for user profile data
- Query `SessionState.scoreboard` for recent context
- Check user's calendar for date availability
- Analyze past behavior for preference patterns

**32. Progressive Disclosure Question Generator**

- Priority tiers: Critical → Conditional → Optional
- Ask one question at a time (natural conversation)
- Skip questions with high-confidence pre-fills
- Use implicit extraction to reduce question count

**33. Slot Validation & Refinement**

- Handle vague inputs: "next month" → query calendar → specific dates
- Handle relative references: "the usual budget" → past trip average
- Confirm high-risk slots before execution

**34. Multi-Turn Clarification Protocol**

```python
DialogueAgent modes:
  - STREAMING_RESPONSE: Normal conversational mode
  - SLOT_FILLING: Clarification question mode
  - SLOT_CONFIRMATION: Verify before execution
  - HANDOFF: Complete → route to PlannerAgent
```

**35. Conversational Memory (Slot Tracking in SessionState)**

```python
SessionState.workflow.active_slot_filling = {
    "intent_id": "intent-12345",
    "intent_type": "plan_trip",
    "slots_filled": {
        "destination": {"value": "California", "confidence": 0.95, "turn": 1},
        "dates": {"value": "2025-03-15 to 03-22", "confidence": 0.80, "turn": 3},
        "travelers": {"value": 2, "confidence": 0.90, "turn": 2},
        "origin": {"value": "Phoenix", "confidence": 1.0, "source": "pre-filled"}
    },
    "clarification_history": [
        {"turn": 1, "asked": "When?", "answered": "Next month"},
        {"turn": 2, "asked": "How many?", "answered": "Just me and my wife"}
    ]
}
```

### Revised Architecture Flow

**Before (Naive):**

```
User → ConciergeAgent → [Route to Specialist] → Execute
```

**After (Intelligent):**

```
User → ConciergeAgent (Intent + Slot Extraction)
  ↓
  [Sufficient slots? Check completion %]
  ├─ YES (≥75%) → Route to PlannerAgent → Execute
  └─ NO (<75%)  → DialogueAgent Slot Filling Mode
                    ↓
                  [Pre-fill from context]
                    ↓
                  [Ask clarification questions]
                    ↓
                  [User provides answers]
                    ↓
                  [Update slots, check completion]
                    ↓
                  [Complete?]
                  └─ YES → Handoff to PlannerAgent → Execute
```

### Key Insight: Implicit Information Extraction

**Natural Language → Structured Slots:**

```
"We'll drive from Phoenix"
  → origin: "Phoenix"
  → transport_mode: "driving"

"Just me and my wife"
  → travelers: 2
  → trip_type: "couples"

"Next month"
  → Query calendar
  → dates: "2025-12-01 to 2025-12-08" (first available week)
```

**Total Systems: 35 (29 real-world scenarios + 6 conversational intelligence)**

---

## 🧠 Emotional Intelligence: LLM-Powered Context-Aware Agents

**Problem:** Specialist agents receiving only task queries (no emotional context, conversation history, or user self-perception) create **socially blind agents** that can cause harm even when factually correct.

**Solution:** LLM-powered emotional intelligence through rich system prompts and context-aware inference.

### The Critical Gap: Empathy & Situational Awareness

**❌ Bad Scenario (Blind Agent - No Context):**

```
User (tensed, self-critical): "I've been terrible with money lately..."
User: "Can we afford to extend Mom's PT another month?"

FinanceAgent (blind, no context):
  System Prompt: "You are FinanceAgent. Analyze financial queries accurately."
  User Prompt: "Can we afford PT extension?"

Response: "Your spending is 25% over budget. Healthcare category overspent by $800."

Result: BRUTAL. Confirms user's worst fears. Factually correct but emotionally damaging.
```

**✅ Good Scenario (LLM Context-Aware Agent):**

```
User (tensed, self-critical): "I've been terrible with money lately..."
User: "Can we afford to extend Mom's PT another month?"

FinanceAgent (LLM-powered with rich context):
  System Prompt: """
  You are FinanceAgent. The user is currently ANXIOUS (intensity: 0.7, negative valence).

  USER SELF-PERCEPTION: User believes "I'm bad with money" (self-critical, low confidence).

  CONVERSATION CONTEXT: User has been discussing financial stress and caregiving burden.
  Tone: SUPPORTIVE. Sensitivity: HIGH.

  USER VALUES: Family-first, responsibility, transparency.
  USER IDENTITY: Primary caregiver for recovering mother.

  RECENT CONVERSATION:
  - Turn 1 (User): "I've been terrible with money lately" [anxious]
  - Turn 2 (Agent): "What's making you feel that way?" [probe]
  - Turn 3 (User): "Mom's medical bills keep coming" [overwhelmed]

  INSTRUCTIONS:
  1. Challenge negative self-beliefs supportively (user is NOT "bad with money")
  2. Reframe data with empathy and context
  3. Acknowledge caregiving effort
  4. Provide actionable solutions, not just problems
  5. Maintain factual accuracy while being emotionally intelligent
  """

  User Prompt: "Can we afford to extend Mom's PT another month? Financial data: {data}"

LLM Response: "I understand your concern about finances. Let me show you what's
  actually happening:

  ✅ POSITIVE: You're managing essentials well—groceries and utilities on track
  ⚠️  CONTEXT: Healthcare spending is up $800, but that's temporary due to Mom's PT,
     which is important and valuable care
  💡 SOLUTION: If we shift $300 from dining out next month, extending PT is very doable

  You're not 'bad with money'—you're prioritizing what matters (family) and making
  temporary adjustments. That's actually smart financial caregiving."

Result: Same data, empathetic framing. User feels supported, not judged.
```

### System 36: AgentContext (Rich Context Envelope for LLM System Prompts)

**AgentContext is NOT hardcoded logic—it's structured data that gets formatted into LLM system prompts.**

```python
@dataclass
class AgentContext:
    """
    Rich context extracted from SessionState.
    Formatted into LLM system prompts for context-aware inference.
    """

    # 1. EMOTIONAL STATE (extracted by LLM, stored in SessionState.affect)
    user_affect: AffectState = {
        "current_emotion": "anxious",      # LLM-detected emotion
        "intensity": 0.7,                   # 0.0-1.0
        "valence": -0.5,                    # -1.0 (negative) to +1.0 (positive)
        "arousal": 0.6,                     # 0.0 (calm) to 1.0 (agitated)
    }

    # 2. SELF-MODEL (LLM-extracted beliefs, stored in SessionState.self_model)
    user_self_perception: SelfModel = {
        "current_beliefs": [
            "I'm bad with money",           # LLM extracted from "terrible with money"
            "I'm a caring son",
            "I'm overwhelmed"
        ],
        "confidence": 0.4,                  # Low self-confidence
        "identity_salience": ["caregiver", "financially_struggling"]
    }

    # 3. CONVERSATION CONTEXT (maintained in SessionState.scoreboard)
    conversation_context: ConversationState = {
        "tone": "supportive",               # Required tone
        "sensitivity_level": "high",        # How careful to be
        "topics_discussed": ["mom_health", "finances", "stress"],
        "user_concerns": ["money_guilt", "caregiving_burden"]
    }

    # 4. TEMPORAL CONTEXT (last 5-10 turns from SessionState.scoreboard)
    recent_history: List[Turn] = [
        {"role": "user", "text": "I've been terrible with money", "affect": "anxious"},
        {"role": "assistant", "text": "What's making you feel that way?"},
        {"role": "user", "text": "Mom's medical bills keep coming", "affect": "overwhelmed"}
    ]

    # 5. USER BELIEFS (from SessionState.beliefs)
    user_beliefs: Beliefs = {
        "values": ["family_first", "responsibility", "transparency"],
        "constraints": ["tight_budget", "limited_time"],
        "facts": ["mom_recovering", "PT_twice_weekly", "user_primary_caregiver"]
    }

    def to_system_prompt(self) -> str:
        """
        Format AgentContext into LLM system prompt.
        This is where context becomes actionable for the LLM.
        """
        return f"""
USER EMOTIONAL STATE: {self.user_affect.current_emotion.upper()}
  (intensity: {self.user_affect.intensity}, valence: {self.user_affect.valence})

USER SELF-PERCEPTION:
  Beliefs: {', '.join(self.user_self_perception.current_beliefs)}
  Confidence: {self.user_self_perception.confidence}
  Identity: {', '.join(self.user_self_perception.identity_salience)}

CONVERSATION CONTEXT:
  Tone Required: {self.conversation_context.tone.upper()}
  Sensitivity Level: {self.conversation_context.sensitivity_level.upper()}
  Topics Discussed: {', '.join(self.conversation_context.topics_discussed)}
  User Concerns: {', '.join(self.conversation_context.user_concerns)}

RECENT CONVERSATION:
{self._format_recent_history()}

USER VALUES & BELIEFS:
  Values: {', '.join(self.user_beliefs.values)}
  Constraints: {', '.join(self.user_beliefs.constraints)}
  Key Facts: {', '.join(self.user_beliefs.facts)}

INSTRUCTIONS:
1. Respond with empathy and situational awareness
2. Challenge negative self-beliefs supportively (if present)
3. Acknowledge user's efforts and values
4. Provide actionable solutions, not just analysis
5. Maintain factual accuracy while being emotionally intelligent
6. Use appropriate tone based on emotional state
"""
```

### System 37: LLM-Based Emotional Intelligence (No Hardcoded Rules)

**OLD APPROACH (Rule-Based Chatbot - WRONG):**

```python
class EmotionalIntelligenceLayer:
    def adjust_response(self, raw_response: str, context: AgentContext) -> str:
        # ❌ Hardcoded if/else logic (fragile, limited)
        if "bad with money" in context.user_self_perception.current_beliefs:
            raw_response = "You're not bad with money. " + raw_response

        if context.user_affect.current_emotion == "anxious":
            raw_response = self.soften_tone(raw_response)

        return raw_response
```

**NEW APPROACH (LLM-Powered - CORRECT):**

```python
class LLMEmotionalIntelligence:
    """
    LLM-based emotional intelligence through rich system prompts.
    No hardcoded rules - LLM naturally incorporates context.
    """

    async def generate_empathetic_response(
        self,
        task: Task,
        data: Dict,
        context: AgentContext
    ) -> str:
        """
        Generate emotionally intelligent response using LLM with rich context.
        """

        # BUILD SYSTEM PROMPT with full context
        system_prompt = f"""
You are FinanceAgent, a compassionate financial advisor for family caregivers.

{context.to_system_prompt()}

Your response should:
- Be factually accurate (use provided data)
- Address user's emotional state appropriately
- Challenge negative self-beliefs if present
- Provide hope and actionable next steps
- Acknowledge caregiving effort and family values
"""

        # BUILD USER PROMPT with task and data
        user_prompt = f"""
Task: {task.query}

Financial Data:
- Monthly budget: ${data['budget']}
- Current spending: ${data['spending']} ({data['percent_over']}% over budget)
- Healthcare spending: ${data['healthcare_total']} (${data['healthcare_over']} over typical)
- Available flexibility: ${data['flexible_spending']} in discretionary categories

Analyze and respond with empathy and practical guidance.
"""

        # LLM GENERATES context-aware response naturally
        response = await self.model_hub.complete(
            agent_id="finance_agent",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.7,  # Slightly creative for empathetic phrasing
            max_tokens=500
        )

        return response
```

**Key Insight: LLM does the emotional intelligence work, not hardcoded if/else.**

### System 38: Context Propagation (Orchestrator → LLM System Prompts)

**K1 Orchestrator builds AgentContext and passes to specialist agents:**

```python
class K1Orchestrator:
    async def execute_phase3_with_llm_context(
        self,
        selected_agents: List[Agent],
        task: Task
    ) -> List[Result]:
        """
        Phase 3: Execution with LLM-powered emotional intelligence.
        """

        # BUILD AGENTCONTEXT from SessionState
        context = self._build_agent_context()

        # EXECUTE agents with context (formatted as system prompts internally)
        results = await asyncio.gather(*[
            agent.execute_with_llm_context(task, context)
            for agent in selected_agents
        ])

        return results

    def _build_agent_context(self) -> AgentContext:
        """
        Extract rich context from SessionState.
        This data will be formatted into LLM system prompts.
        """
        return AgentContext(
            user_affect=self.session_state.affect.current_state,
            user_self_perception=self.session_state.self_model,
            conversation_context=self.session_state.scoreboard.conversation,
            recent_history=self.session_state.scoreboard.recent_turns[-10:],
            user_beliefs=self.session_state.beliefs
        )
```

**Specialist Agent Implementation:**

```python
class FinanceAgent:
    def __init__(self, model_hub: ModelHub):
        self.model_hub = model_hub
        self.llm_ei = LLMEmotionalIntelligence(model_hub)

    async def execute_with_llm_context(
        self,
        task: Task,
        context: AgentContext
    ) -> Result:
        """
        Execute financial analysis with LLM-powered emotional intelligence.
        """

        # 1. FETCH DATA (standard K0 query)
        financial_data = await self.k0.query_finances(task.user_id)

        # 2. LLM GENERATES emotionally intelligent response
        #    System prompt includes full AgentContext
        #    LLM naturally incorporates empathy, no rules needed
        response = await self.llm_ei.generate_empathetic_response(
            task=task,
            data=financial_data,
            context=context  # ← Rich context becomes system prompt
        )

        return Result(content=response, agent="finance_agent")
```

### System 39: LLM-Based Affect Tracking (Not Keyword Matching)

**OLD APPROACH (Keyword Matching - WRONG):**

```python
# ❌ Brittle, misses nuance
if "terrible" in message or "bad" in message:
    emotion = "anxious"
```

**NEW APPROACH (LLM Emotion Classification - CORRECT):**

```python
class LLMAffectTracker:
    """
    LLM-based emotion detection with nuanced understanding.
    Integrates with P04 (Affective Tagging) pipeline.
    """

    async def analyze_message(self, user_message: str) -> AffectState:
        """
        Use LLM to detect emotional state from user message.
        """

        # LLM PROMPT for emotion classification
        system_prompt = """
You are an emotion detection specialist. Analyze the emotional state from user messages.

Return a JSON object with:
{
  "emotion": "anxious|worried|stressed|proud|confident|sad|frustrated|neutral|...",
  "intensity": 0.0-1.0 (how strong the emotion is),
  "valence": -1.0 to +1.0 (negative to positive),
  "arousal": 0.0-1.0 (calm to agitated),
  "confidence": 0.0-1.0 (detection confidence),
  "reasoning": "brief explanation"
}

Consider:
- Explicit emotion words ("terrible", "worried", "great")
- Self-critical language ("I'm bad at", "I'm failing")
- Context and phrasing (nuanced detection)
- Intensity markers ("very", "extremely", "a bit")
"""

        user_prompt = f'Analyze emotional state: "{user_message}"'

        # LLM DETECTS emotion with nuance
        response = await self.model_hub.complete(
            agent_id="affect_tracker",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.1,  # Low temp for consistent classification
            response_format="json"
        )

        affect_data = json.loads(response)

        # BUILD AffectState
        affect_state = AffectState(
            current_emotion=affect_data["emotion"],
            intensity=affect_data["intensity"],
            valence=affect_data["valence"],
            arousal=affect_data["arousal"],
            confidence=affect_data["confidence"]
        )

        # UPDATE SessionState.affect
        self.session_state.affect.current_state = affect_state

        # TRIGGER P04 pipeline for memory tagging
        await self.k0_bus.publish("affect.detected", affect_data)

        return affect_state
```

**LLM-Based Self-Model Extraction:**

```python
class LLMSelfModelTracker:
    """
    Extract user's self-perception beliefs using LLM.
    Updates SessionState.self_model.
    """

    async def extract_self_beliefs(self, user_message: str) -> List[str]:
        """
        Use LLM to detect what user message reveals about self-perception.
        """

        system_prompt = """
Analyze what this message reveals about the user's self-perception and beliefs about themselves.

Extract beliefs like:
- "I'm bad with money" (self-critical about finances)
- "I'm a caring son" (positive identity as caregiver)
- "I'm overwhelmed" (feeling of being unable to cope)
- "I'm not good enough" (low self-worth)

Return JSON array of extracted beliefs with confidence scores:
[
  {"belief": "I'm bad with money", "confidence": 0.9},
  {"belief": "I'm overwhelmed", "confidence": 0.7}
]
"""

        user_prompt = f'Extract self-perception beliefs: "{user_message}"'

        response = await self.model_hub.complete(
            agent_id="self_model_tracker",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.1,
            response_format="json"
        )

        beliefs = json.loads(response)

        # UPDATE SessionState.self_model
        for belief_data in beliefs:
            if belief_data["confidence"] > 0.6:
                self.session_state.self_model.current_beliefs.append(
                    belief_data["belief"]
                )

        return beliefs
```

### Complete LLM-Powered Flow (Real Architecture)

```
T-300ms: User → "I've been terrible with money lately..."

  → LLMAffectTracker.analyze_message()
     LLM Prompt: "Detect emotion from: 'I've been terrible with money lately'"
     LLM Response: {"emotion": "anxious", "intensity": 0.6, "valence": -0.5, ...}
     → Update SessionState.affect

  → LLMSelfModelTracker.extract_self_beliefs()
     LLM Prompt: "Extract self-perception from: 'terrible with money lately'"
     LLM Response: [{"belief": "I'm bad with money", "confidence": 0.9}]
     → Update SessionState.self_model

T0: User → "Can we afford to extend Mom's PT another month?"

  → LLMAffectTracker.analyze_message()
     LLM detects: anxious (0.7 intensity, increased from 0.6)

  → ConciergeAgent:
     - Extract intent: "finance_query" (LLM-based intent classification)
     - Check SessionState: affect=anxious, self_model="bad with money"
     - Set conversation_tone: "supportive", sensitivity: "high"

T0+50ms: K1 Orchestrator Phase 1 (Negotiation)
  → Build AgentContext from SessionState
  → Broadcast to agents

T0+100ms: FinanceAgent receives bid request
  → Bids with confidence=0.9

T0+150ms: K1 Orchestrator Phase 3 (Execution)
  → FinanceAgent.execute_with_llm_context(task, context)

T0+200ms: FinanceAgent execution:
  1. Query K0 for financial data
  2. Build LLM system prompt with AgentContext.to_system_prompt()
     System Prompt includes:
     - "User is ANXIOUS (intensity: 0.7, valence: -0.5)"
     - "User believes: I'm bad with money"
     - "Tone: SUPPORTIVE, Sensitivity: HIGH"
     - "Recent conversation: [3 turns with affect tags]"
     - "Instructions: Challenge negative beliefs, provide hope + solutions"

  3. LLM generates response (temperature=0.7)
     Input: System prompt + financial data
     Output: Empathetic, context-aware response

T0+800ms: LLM Response (emotionally intelligent, naturally):
  "I understand your concern about finances. Let me show you what's actually happening:

  ✅ POSITIVE: You're managing essentials well—groceries and utilities on track
  ⚠️  CONTEXT: Healthcare spending is up $800, but that's temporary due to Mom's PT
  💡 SOLUTION: If we shift $300 from dining out, extending PT is very doable

  You're not 'bad with money'—you're prioritizing family. That's smart caregiving."

T0+850ms: MemoryWriterAgent (background):
  → Write episodic memory with P04 affect tagging:
     - user_anxious_about_finances
     - challenged_negative_belief_successfully
     - user_reassured_with_actionable_solution
```

### Key Architecture Principles: LLM-Powered Emotional Intelligence

**1. NO Hardcoded Rules**

- ❌ `if affect == "anxious": soften_tone()`
- ✅ LLM system prompt: "User is anxious, respond with empathy"

**2. LLM for Detection**

- ❌ Keyword matching: `"terrible" → anxious`
- ✅ LLM classification: Nuanced emotion detection with confidence scores

**3. LLM for Response Generation**

- ❌ Template responses with string replacement
- ✅ LLM generates naturally empathetic responses from rich context

**4. Context as System Prompts**

- AgentContext formatted into structured system prompts
- LLM naturally incorporates context into reasoning
- No separate "emotional intelligence layer" - it's built into inference

**5. Integration with K0 Pipelines**

- LLM-detected affect → P04 (Affective Tagging) for memory
- LLM-extracted beliefs → SessionState.self_model
- All context flows through SessionState (ADR-0017)

### System Summary: LLM-Powered Emotional Intelligence

**36. AgentContext (Rich Context → LLM System Prompts)**

- Data structure for user affect, self-model, conversation context, history, beliefs
- `to_system_prompt()` formats context for LLM inference
- No hardcoded logic, just structured context

**37. LLM-Based Emotional Intelligence**

- LLM generates empathetic responses from rich system prompts
- No if/else rules for tone adjustment
- Natural language understanding of emotional nuance

**38. Context Propagation (Orchestrator → Agents)**

- K1 Orchestrator builds AgentContext from SessionState
- Passes to specialist agents during Phase 3
- Agents format context as system prompts for LLM

**39. LLM-Based Affect & Self-Model Tracking**

- LLM detects emotions (not keyword matching)
- LLM extracts self-perception beliefs
- Updates SessionState continuously
- Integrates with P04 (Affective Tagging) pipeline

**Total Systems: 39 (LLM-powered, not rule-based chatbots)**

---

## 📊 Complete System Count

**Core Infrastructure:** 8 systems (cancellation, queuing, timeouts, etc.)
**Intelligence Layer:** 6 systems (meta-intent, ambiguity, referents, etc.)
**Resilience Layer:** 5 systems (saga, crash recovery, API retry, etc.)
**Safety & Privacy:** 4 systems (emergency stop, redaction, guardrails, etc.)
**SessionState Extensions:** 3 systems (workflow, interruption, conflict tracking)
**Observability:** 3 systems (timeline, intent history, failure analysis)
**Conversational Intelligence:** 6 systems (slot filling, pre-fill, validation, etc.)
**Emotional Intelligence:** 4 systems (AgentContext, EI Layer, context propagation, affect tracking)

**Total: 39 Systems for Production-Ready Human-Like AI**

---

## 🧠 System 40: Tiered Chat History Management (Token Cost Optimization)

### The Core Problem

**Challenge:** Full chat history grows unbounded and becomes expensive/slow to pass to every LLM call.

**Example Scenario:**

- 50-turn conversation = ~10,000 tokens of raw history
- Passing to every LLM call = massive token waste (10K × number of agents × turns)
- But agents need context for empathy, continuity, and referent resolution
- **Cost explosion:** At $0.01 per 1K tokens, 100 turns with 5 agents = $50+ per conversation!

**Current Problem in SessionState (ADR-0017):**

```python
@dataclass
class Beliefs:
    recent_turns: Deque[TurnSummary] = field(default_factory=lambda: deque(maxlen=5))
    # Only 5 turns - too limiting for complex conversations
```

**Whiteboard AgentContext (naive approach):**

```python
recent_history: List[Turn]  # 5-10 turns passed to every agent
# Problem: What about longer conversations? How to compress?
```

### Solution: 3-Tier History Architecture

**Design Principle:** Different context granularities for different needs, automatic compression.

```python
@dataclass
class Scoreboard:
    """
    Extended SessionState.scoreboard for tiered history management.
    Supports unlimited conversation length with bounded token cost.
    """

    # ========================================
    # TIER 1: RECENT TURNS (Working Memory)
    # ========================================
    # Last 10 turns, always passed to LLM system prompts
    # Cost: ~1000 tokens per LLM call
    # Use case: Immediate context, referent resolution ("it", "that", "which one")

    recent_turns: Deque[Turn] = field(default_factory=lambda: deque(maxlen=10))

    @dataclass
    class Turn:
        turn_id: int
        role: str  # "user" | "assistant"
        text: str  # Full utterance
        intent: Optional[str]  # Classified intent
        affect: Optional[str]  # "anxious", "happy", "neutral"
        timestamp: datetime
        superseded_by: Optional[int] = None  # For typo corrections

    # ========================================
    # TIER 2: SESSION SUMMARY (Compressed Memory)
    # ========================================
    # LLM-generated rolling summary of conversation
    # Updated every 10 turns by background SessionSummarizer
    # Cost: ~500 tokens per LLM call
    # Use case: Broader context, topic tracking, emotional arc, key decisions

    session_summary: str = ""  # Max 500 tokens
    last_summary_turn: int = 0  # Track when last summarized

    # Example summary:
    # "User expressed anxiety about Mom's PT costs (turns 1-5), asked about
    #  budget flexibility. After reviewing finances (turns 6-8), user felt
    #  reassured that extending PT is feasible. Conversation shifted to
    #  planning family dinner (turns 9-10), user relaxed and happy. Key
    #  decision: Extend PT another month, shift $300 from dining budget."

    # ========================================
    # TIER 3: DEEP CONTEXT (On-Demand K0 Retrieval)
    # ========================================
    # Historical memories from K0 (episodic, not stored in SessionState)
    # Retrieved via K0 P01 (Recall) only when needed
    # Cost: 0 tokens by default, ~500 tokens when retrieved
    # Use case: Historical patterns, past decisions, long-term tracking

    # Not stored in SessionState - queried from K0 as needed:
    # - "3 weeks ago user mentioned budget concerns"
    # - "User always prefers Italian restaurants"
    # - "Last vacation planning took 2 weeks of back-and-forth"

    # ========================================
    # METADATA for Smart Context Selection
    # ========================================

    topics_discussed: List[str] = field(default_factory=list)
    # Example: ["mom_health", "finances", "vacation_planning", "dinner_recipes"]

    emotional_arc: List[EmotionalState] = field(default_factory=list)
    # Track mood evolution over session

    @dataclass
    class EmotionalState:
        turn_id: int
        emotion: str
        intensity: float  # 0.0-1.0
        valence: float    # -1.0 (negative) to +1.0 (positive)
```

### Token Budget Analysis

**Per-LLM-Call Cost:**

| Tier | Content | Tokens | Always Passed? | Use Case |
|------|---------|--------|----------------|----------|
| **Tier 1: Recent** | Last 10 turns | ~1000 | ✅ Yes | Immediate context, referents |
| **Tier 2: Summary** | Compressed session | ~500 | ✅ Yes | Broader context, emotional arc |
| **Tier 3: Deep** | K0 retrieval | ~500 | ❌ Conditional | Historical patterns |
| **Total (typical)** | Recent + Summary | **~1500** | - | **95% of calls** |
| **Total (complex)** | All 3 tiers | **~2000** | - | **5% of calls (when needed)** |

**Comparison:**

- **Naive approach (full history):** 10,000+ tokens per call
- **Tiered approach:** 1,500-2,000 tokens per call
- **Savings:** 80-85% token reduction!

### Progressive Summarization Pipeline

**Background agent automatically compresses history:**

```python
class SessionSummarizer:
    """
    Background agent that progressively summarizes conversation.
    Triggered every 10 turns, non-blocking.
    """

    async def summarize_session(self, session_state: SessionState):
        """
        LLM-based summarization of last 10 turns.
        Appends to existing session_summary with compression.
        """

        # Check if 10 turns elapsed since last summary
        turns_since_summary = (
            session_state.scoreboard.turn_count -
            session_state.scoreboard.last_summary_turn
        )

        if turns_since_summary < 10:
            return  # Not time yet

        # Get last 10 turns (before they're evicted from deque)
        turns_to_summarize = list(session_state.scoreboard.recent_turns)

        # LLM generates summary
        new_summary = await self.model_hub.complete(
            agent_id="session_summarizer",
            system_prompt="""
You are a conversation summarizer for a family AI assistant.

Summarize the last 10 turns into a concise narrative.

FOCUS ON:
1. Topics discussed (with emotional context)
2. Key decisions made or actions taken
3. User concerns/questions raised
4. Tasks completed or pending
5. Emotional arc (how user's mood evolved)
6. Important entities mentioned (people, places, dates)

FORMAT:
- 2-4 sentences, max 150 words
- Narrative style, chronological
- Include turn ranges for reference (e.g., "turns 11-20")

EXAMPLE OUTPUT:
"Turns 11-20: User expressed frustration about work deadlines (anxious,
intensity 0.7), asked for help prioritizing tasks. After reviewing calendar,
user felt more organized and requested dinner recipe suggestions. Mood
shifted to relaxed (neutral, intensity 0.3). Key decision: Focus on Project
X this week, defer Project Y. User interested in Italian cuisine."
""",
            user_prompt=f"""
Previous summary (turns 1-{session_state.scoreboard.last_summary_turn}):
{session_state.scoreboard.session_summary}

New turns to summarize (turns {session_state.scoreboard.last_summary_turn + 1}-{session_state.scoreboard.turn_count}):
{self._format_turns(turns_to_summarize)}

Generate updated summary. Append to previous summary.
""",
            max_tokens=200,
            temperature=0.3  # Low temp for consistent summarization
        )

        # Compress if combined summary exceeds 500 tokens
        session_state.scoreboard.session_summary = self._compress_and_append(
            old_summary=session_state.scoreboard.session_summary,
            new_summary=new_summary,
            max_tokens=500
        )

        # Update last summary turn
        session_state.scoreboard.last_summary_turn = session_state.scoreboard.turn_count

    def _compress_and_append(
        self,
        old_summary: str,
        new_summary: str,
        max_tokens: int
    ) -> str:
        """
        Append new summary to old, compress old if exceeds max_tokens.
        """
        combined = f"{old_summary}\n\n{new_summary}"

        if self._estimate_tokens(combined) > max_tokens:
            # Compress old summary to half length
            compressed_old = await self.model_hub.complete(
                agent_id="session_summarizer",
                system_prompt="""
Compress this conversation summary to half its length while keeping:
1. All key decisions and actions
2. Major topic shifts
3. Emotional turning points
4. Important entity mentions

Remove: Minor details, redundant information, verbose phrasing.
""",
                user_prompt=old_summary,
                max_tokens=max_tokens // 2
            )

            return f"{compressed_old}\n\n{new_summary}"

        return combined

    def _format_turns(self, turns: List[Turn]) -> str:
        """Format turns for LLM consumption."""
        formatted = []
        for turn in turns:
            affect_str = f" [{turn.affect}]" if turn.affect else ""
            formatted.append(
                f"Turn {turn.turn_id} ({turn.role}){affect_str}: {turn.text}"
            )
        return "\n".join(formatted)
```

**Scheduling:** Runs in background (Tier 3 Writer Agent), triggered every 10 turns, non-blocking.

### Smart Context Selection (Per-Agent)

**Different agents need different history:**

```python
class ContextSelector:
    """
    Intelligent context selection based on agent type and task.
    Minimizes token cost while maintaining quality.
    """

    def build_agent_context(
        self,
        agent: Agent,
        task: Task,
        session_state: SessionState
    ) -> AgentContext:
        """
        Build context tailored to agent's needs.
        """

        if agent.type == "ConciergeAgent":
            # ALWAYS needs recent turns for meta-intent classification
            return AgentContext(
                recent_history=list(session_state.scoreboard.recent_turns),  # All 10
                session_summary=session_state.scoreboard.session_summary,
                deep_context=None,  # ConciergeAgent doesn't need K0 retrieval
                history_tier_used="recent+summary",
                estimated_tokens=1500
            )

        elif agent.type == "FinanceAgent":
            # Needs recent turns + finance-related context
            finance_turns = self._filter_turns_by_topic(
                session_state.scoreboard.recent_turns,
                topics=["finance", "budget", "spending", "money"]
            )

            return AgentContext(
                recent_history=finance_turns[-5:],  # Only finance-relevant turns
                session_summary=self._extract_finance_summary(
                    session_state.scoreboard.session_summary
                ),
                deep_context=None,  # Usually not needed
                history_tier_used="recent+summary(filtered)",
                estimated_tokens=1000
            )

        elif agent.type == "MemoryWriterAgent":
            # FULL CONTEXT needed for quality enrichment
            return AgentContext(
                recent_history=list(session_state.scoreboard.recent_turns),  # All 10
                session_summary=session_state.scoreboard.session_summary,
                deep_context=None,  # Has direct K0 access if needed

                # Additional context for enrichment
                user_affect_history=session_state.affect.history[-10:],
                user_beliefs=session_state.beliefs,
                conversation_topics=session_state.scoreboard.topics_discussed,

                history_tier_used="recent+summary+affect",
                estimated_tokens=2500  # Can afford more (background, non-blocking)
            )

        elif agent.type == "SafetyArbiter":
            # Recent 3 turns + safety-specific context
            return AgentContext(
                recent_history=list(session_state.scoreboard.recent_turns[-3:]),
                session_summary=None,  # Safety doesn't need full summary
                deep_context=None,

                # Safety-specific context
                safety_context=session_state.meta.last_safety_block,

                history_tier_used="recent(minimal)+safety",
                estimated_tokens=500
            )

        elif self._needs_deep_context(task, agent):
            # Conditionally retrieve from K0 for complex queries
            deep_context = await self._retrieve_deep_context(task, session_state)

            return AgentContext(
                recent_history=list(session_state.scoreboard.recent_turns[-5:]),
                session_summary=session_state.scoreboard.session_summary,
                deep_context=deep_context,  # K0 retrieval
                history_tier_used="recent+summary+deep",
                estimated_tokens=2000
            )

        else:
            # Default: Recent + Summary (most common case)
            return AgentContext(
                recent_history=list(session_state.scoreboard.recent_turns),
                session_summary=session_state.scoreboard.session_summary,
                deep_context=None,
                history_tier_used="recent+summary",
                estimated_tokens=1500
            )

    def _needs_deep_context(self, task: Task, agent: Agent) -> bool:
        """
        Decide if K0 retrieval is needed (Tier 3).
        """
        # Deep context triggers:
        # 1. User explicitly references past ("like last time", "before")
        # 2. Complex pattern analysis ("What pattern do you see in my spending?")
        # 3. Contradiction resolution ("Didn't you say X before?")
        # 4. Long-term tracking queries ("How has Mom's recovery progressed?")

        past_reference_phrases = [
            "last time", "before", "previously", "earlier", "history",
            "pattern", "trend", "always", "usually", "didn't you say"
        ]

        if any(phrase in task.query.lower() for phrase in past_reference_phrases):
            return True

        # MemoryWriterAgent always has K0 access (but doesn't need pre-retrieval)
        if agent.type == "MemoryWriterAgent":
            return False  # Has direct K0 access

        # Complex analytical queries
        if any(word in task.query.lower() for word in
               ["analyze", "pattern", "trend", "compare", "track"]):
            return True

        return False

    async def _retrieve_deep_context(
        self,
        task: Task,
        session_state: SessionState
    ) -> str:
        """
        Retrieve relevant historical context from K0.
        """
        # Query K0 P01 (Recall) for relevant memories
        memories = await self.k0_client.query_memories(
            query=task.query,
            user_id=session_state.user_id,
            limit=3,  # Top 3 relevant memories
            max_tokens=500,  # Bounded retrieval
            privacy_band="GREEN"  # Only non-sensitive memories
        )

        # Format for LLM consumption
        if memories:
            formatted = "HISTORICAL CONTEXT (from past conversations):\n"
            for mem in memories:
                formatted += f"- {mem.timestamp.strftime('%Y-%m-%d')}: {mem.summary}\n"
            return formatted

        return None
```

### AgentContext with Tiered History

**Updated data structure:**

```python
@dataclass
class AgentContext:
    """
    Rich context envelope with tiered history management.
    Passed to specialist agents, formatted as LLM system prompts.
    """

    # ========================================
    # TIER 1: Recent History (Always Included)
    # ========================================
    recent_history: List[Turn]
    # Last 5-10 turns, tailored per agent
    # Cost: ~500-1000 tokens

    # ========================================
    # TIER 2: Session Summary (Always Included)
    # ========================================
    session_summary: Optional[str]
    # Compressed conversation context
    # Cost: ~500 tokens

    # ========================================
    # TIER 3: Deep Context (Conditionally Included)
    # ========================================
    deep_context: Optional[str] = None
    # K0 retrieval for complex queries
    # Cost: ~500 tokens (when needed)

    # ========================================
    # Emotional & Belief Context
    # ========================================
    user_affect: AffectState
    user_self_perception: SelfModel
    conversation_context: ConversationState
    user_beliefs: Beliefs

    # ========================================
    # Metadata (for observability)
    # ========================================
    history_tier_used: str  # "recent" | "recent+summary" | "recent+summary+deep"
    estimated_tokens: int   # Token cost tracking

    def to_system_prompt(self) -> str:
        """
        Format AgentContext into LLM system prompt.
        Includes appropriate history tier.
        """
        prompt = f"""
USER EMOTIONAL STATE: {self.user_affect.current_emotion.upper()}
  (intensity: {self.user_affect.intensity}, valence: {self.user_affect.valence})

USER SELF-PERCEPTION:
  Beliefs: {', '.join(self.user_self_perception.current_beliefs)}
  Confidence: {self.user_self_perception.confidence}

CONVERSATION CONTEXT:
  Tone Required: {self.conversation_context.tone.upper()}
  Sensitivity Level: {self.conversation_context.sensitivity_level.upper()}
"""

        # TIER 1: Recent History (always included)
        if self.recent_history:
            prompt += "\nRECENT CONVERSATION:\n"
            for turn in self.recent_history:
                affect_str = f" [{turn.affect}]" if turn.affect else ""
                prompt += f"- Turn {turn.turn_id} ({turn.role}){affect_str}: {turn.text}\n"

        # TIER 2: Session Summary (if available)
        if self.session_summary:
            prompt += f"\nSESSION SUMMARY:\n{self.session_summary}\n"

        # TIER 3: Deep Context (if retrieved)
        if self.deep_context:
            prompt += f"\n{self.deep_context}\n"

        prompt += """
USER VALUES & BELIEFS:
  Values: {', '.join(self.user_beliefs.values)}
  Constraints: {', '.join(self.user_beliefs.constraints)}

INSTRUCTIONS:
1. Respond with empathy and situational awareness
2. Challenge negative self-beliefs supportively (if present)
3. Reference past context when relevant
4. Provide actionable solutions
5. Maintain factual accuracy while being emotionally intelligent
"""
        return prompt
```

### Integration with K1 Orchestrator

**Orchestrator builds tiered context:**

```python
class K1Orchestrator:
    def __init__(self):
        self.context_selector = ContextSelector()

    async def execute_phase3_with_context(
        self,
        selected_agents: List[Agent],
        task: Task,
        session_state: SessionState
    ) -> List[Result]:
        """
        Phase 3: Execution with smart context selection.
        """

        # Build tailored context for each agent
        results = []
        for agent in selected_agents:
            # Smart context selection (different per agent)
            context = self.context_selector.build_agent_context(
                agent=agent,
                task=task,
                session_state=session_state
            )

            # Execute with context
            result = await agent.execute_with_context(task, context)

            # Track token usage (observability)
            self._log_token_usage(agent.id, context.estimated_tokens)

            results.append(result)

        return results
```

### Cost-Benefit Analysis

**50-Turn Conversation Example:**

| Approach | Tokens/Call | Calls | Total Tokens | Cost @ $0.01/1K |
|----------|-------------|-------|--------------|-----------------|
| **Naive (full history)** | 10,000 | 50 | 500,000 | **$5.00** |
| **Recent only (10 turns)** | 1,000 | 50 | 50,000 | $0.50 |
| **Tiered (recent + summary)** | 1,500 | 47 | 70,500 | **$0.71** |
| **Tiered with deep (5% of calls)** | 2,000 | 3 | 6,000 | $0.06 |
| **Total (Tiered)** | - | 50 | **76,500** | **$0.77** |

**Savings:** 85% cost reduction ($5.00 → $0.77)

### Performance Budget

**Per-Agent Token Budgets:**

| Agent Type | Tier Used | Token Budget | Justification |
|------------|-----------|--------------|---------------|
| **ConciergeAgent** | Recent + Summary | 1,500 | Needs full context for meta-intent classification |
| **Specialist Agents** | Recent (filtered) + Summary | 1,000-1,500 | Topic-filtered, efficient |
| **MemoryWriterAgent** | Recent + Summary + Affect | 2,500 | Background, can afford more for quality |
| **SafetyArbiter** | Recent (minimal) | 500 | Only needs recent turns for safety check |
| **PlannerAgent** | Recent + Summary | 1,500 | Needs context for plan validation |
| **Deep queries (5%)** | All 3 tiers | 2,000 | Complex queries need historical context |

**Average per call:** ~1,500 tokens (manageable!)

### System Summary

**System 40: Tiered Chat History Management**

**Components:**

- 3-Tier history architecture (Recent, Summary, Deep)
- Progressive summarization pipeline (SessionSummarizer)
- Smart context selection (ContextSelector)
- Per-agent tuning
- K0 on-demand retrieval

**Benefits:**

- 80-85% token cost reduction
- Bounded token cost (1,500-2,000 vs 10,000+)
- Maintains context quality
- Automatic compression
- Scales to unlimited conversation length

**Integration:**

- SessionState.scoreboard extensions (ADR-0017)
- AgentContext updates
- K1 Orchestrator Phase 3
- Background Writer Agent (SessionSummarizer)
- K0 P01 (Recall) integration

---

## 🔧 System 41: Tool & API Integration Gap Analysis (MCP/WASM/Orchestration)

**Status:** 📊 Gap Analysis Complete (2025-11-03)
**Coverage:** 45% (5/11 major concerns addressed)
**Source:** Tool/API Integration Inventory (ADR-0001e, ADR-0033b, ADR-0052)

### Executive Summary

K1's tool execution foundation is **solid** (sandbox architecture, registry, protocol, user confirmation) but **orchestration layer needs work** (automatic chaining, validation, discovery).

**Key Finding:** ADR-0052 provides comprehensive USER-DRIVEN orchestration (step-by-step approval), but TOOL-DRIVEN orchestration (automatic chaining) is still needed.

### Well-Covered Areas (5/11 = 45%)

**✅ Sandbox Architecture (EXCELLENT)**
- **ADR-0001e:** P21+ Integration Pipeline Layer
  - 3 sandbox types: MCP (MEDIUM isolation, JSON-RPC 2.0), WASM (HIGH isolation, zero syscalls), Process (HIGH isolation, cgroups)
  - Security: PEP enforcement, egress proxy, secrets manager
  - Lifecycle: Circuit breaker (CLOSED→OPEN→HALF-OPEN), DLQ (exponential backoff), quarantine (>10 failures/min)
  - Examples: P21-P30 (Philips Hue, Bank of America, Google Calendar, Weather, Maps, IoT, Email, Voice, Health, Custom)

**✅ Tool Registry (GOOD)**
- **ADR-0004, ADR-0007:** 56-Module Architecture + Planning Pipeline
  - `tools/registry/*.json` - Tool catalog with metadata (side_effects, latency_hint, cost_hint, capabilities, band_requirements)
  - Pure actor module (deterministic, no LLM calls)
  - Tool hallucination detection (validates LLM plans against registry, 5% rate → target <1%)

**✅ Tool Call Protocol (GOOD)**
- **ADR-0001e, ADR-0003:** JSON-RPC 2.0 for MCP, WASM exports, MPST validation
  - tool.pdl.yml: 4 states, 7 transitions (agent → validate → execute → return)

**✅ User Confirmation Protocol (EXCELLENT)**
- **ADR-0052:** Enhanced HITL Protocols (4 extensions, 1052 lines, ACCEPTED 2025-10-14)
  - **Extension 0052a:** Step-by-Step Approval (multi-step workflows, per-step approval, rollback via Saga Pattern, progress tracking)
  - **Extension 0052b:** RED Band Approval (explicit confirmation phrases, 4 levels: LOW/MEDIUM/HIGH/CRITICAL, two-person rule, 7-year audit trail)
  - **Extension 0052c:** Nested Clarifications (clarification chains, history tracking, "go back", MAX_DEPTH=3)
  - **Extension 0052d:** Proactive Risk Confirmation (anomaly detection, agent-initiated safety checks)
  - **Approval Levels:**
    - LOW: Single "Yes" button (auto-execute safe operations)
    - MEDIUM: Type "CONFIRM"
    - HIGH: Type exact phrase (e.g., "CONFIRM DELETE 1.2M RECORDS")
    - CRITICAL: Two-person approval (second approver, out-of-band notification, 5min timeout)

**✅ Lifecycle Management (GOOD)**
- **ADR-0001e:** Circuit breaker, DLQ, quarantine mechanisms

### Critical Gaps (2 Remaining)

**❌ 1. Tool Chaining & Orchestration (Automatic, Tool-Centric)**

**Current State:** ADR-0052a provides USER-DRIVEN orchestration (step-by-step approval)

**Missing:** TOOL-DRIVEN orchestration (automatic chaining for low-risk queries)

**Two Types of Orchestration:**

| Type | Who Controls | Best For | Example | ADR Coverage |
|------|--------------|----------|---------|--------------|
| **User-Centric** | User approves each step | High-risk ops, production changes, compliance | "Deploy v2.1.3" → User confirms: tests → backup → deploy → verify | ✅ ADR-0052a |
| **Tool-Centric** | System chains automatically | Low-risk queries, automated workflows, API calls | "Find Mexican restaurant nearby and book" → Auto: location → search → filter → book | ❌ MISSING |

**What's Needed:**
- Tool dependency graphs (tool A output → tool B input)
- Sequential vs parallel execution strategies
- Tool result passing between steps (data flow)
- Automatic failure handling (retry, fallback, partial success)
- Rollback semantics (if C fails, undo A and B?)

**Impact:** Complex tasks broken, poor UX for simple multi-step queries

**Examples:**
```
User: "Find best Mexican restaurants nearby, filter by rating >4.5, book table for 2 at 7pm"

Current (Manual): User must trigger each step separately
Needed (Automatic): System chains:
  1. location_service.getCurrentLocation()
  2. yelp_api.searchRestaurants(cuisine="Mexican", location=result1, rating>4.5)
  3. filter_service.filterByRating(results=result2, min_rating=4.5)
  4. opentable_api.bookReservation(restaurant=result3[0], time="7pm", party_size=2)
Agent: "✅ Booked table at Casa Bonita for 7pm tonight (4.7★)"
```

**Priority:** 🔴 **CRITICAL** (breaks user experience for common queries)

---

**❌ 2. Tool Result Parsing & Validation**

**Current State:** Tools return results via JSON-RPC 2.0 or WASM exports, no validation

**Missing:**
- Schema validation for tool results (did tool return expected format?)
- Error handling strategies (retry, fallback, escalate to user)
- Partial success handling (tool returned 5/10 results, is that acceptable?)
- Type coercion rules (tool returned string "123", plan expects int 123)

**Impact:** Brittle execution, cascading failures, poor error messages to users

**Examples:**
```python
# Current: No validation
result = tool_runner.execute("weather_api", {"location": "New York"})
temp = result["temperature"]  # KeyError if tool returns different schema!

# Needed: Schema validation
result_schema = {
    "temperature": int,
    "humidity": int,
    "conditions": str
}
validated_result = validate_tool_result(result, result_schema, retry_on_error=True)
temp = validated_result.temperature  # Type-safe access
```

**What's Needed:**
- Tool result schema definitions (JSON Schema or FlatBuffers)
- Validation engine (check results against schema)
- Error recovery strategies:
  - **Retry:** Tool returned malformed JSON → Retry with exponential backoff
  - **Fallback:** Primary tool failed → Try backup tool
  - **Partial success:** Got 5/10 results → Ask user: "Found 5 results, good enough?"
  - **Type coercion:** String "123" → int 123 (safe conversions)
  - **Escalate:** Critical field missing → Ask user for clarification

**Priority:** 🔴 **CRITICAL** (production reliability blocker)

---

### High Priority Gaps (3)

**❌ 3. Agent-Tool Integration Patterns**

**Current State:** Tool runner module exists (`tools/runner`, `tools/sandbox`, `tools/registry`)

**Missing:**
- How do agents discover which tools to use? (Registry lookup? LLM decides? Both?)
- Agent capability → tool requirement mapping (if agent has `smart_home.control`, can use `philips_hue` tool)
- Tool access control per agent (ConciergeAgent can use all tools, CalendarAgent only calendar-related tools)
- Agent-specific tool prompt templates (how agent presents tool calls to LLM)

**Impact:** Agent design unclear, security boundaries undefined, capability model incomplete

**Examples:**
```python
# Current: Unclear how agents discover tools
class FinanceAgent:
    def handle_task(self, task):
        # How does agent know about bank_api, payment_api, investment_api?
        pass

# Needed: Explicit agent-tool integration
class FinanceAgent:
    def __init__(self, tool_registry):
        # Agent declares capabilities
        self.capabilities = ["finance.banking", "finance.payments"]

        # Discover tools matching capabilities
        self.available_tools = tool_registry.get_tools_by_capability(self.capabilities)
        # → [bank_api, payment_api, investment_api, budget_tracker]

        # LLM system prompt includes tool descriptions
        self.tool_descriptions = [tool.to_llm_description() for tool in self.available_tools]
```

**Priority:** 🟠 **HIGH** (agent design blocker)

---

**❌ 4. Dynamic Tool Discovery**

**Current State:** Static tool registry (`tools/registry/*.json` files loaded at startup)

**Missing:**
- Runtime tool discovery (new MCP server comes online → K1 learns about it without restart)
- Hot-reload of tool schemas (tool updated → reload schema without K1 restart)
- Tool versioning (multiple versions of same tool, e.g., `calendar_api_v1`, `calendar_api_v2`)
- Tool deprecation warnings (old tools marked deprecated, suggest alternatives)

**Impact:** Requires K1 restart for new tools, can't deploy tools independently, zero-downtime updates blocked

**Examples:**
```yaml
# Current: Static registry (restart required)
tools/registry/calendar.json  # Loaded at startup, can't change

# Needed: Dynamic discovery
# MCP server starts at runtime
mcp_server --name calendar_v2 --port 8002

# K1 discovers automatically (no restart)
K1: "Detected new MCP server: calendar_v2"
K1: "Loading tool schemas from http://localhost:8002"
K1: "Registered 5 new tools: create_event_v2, update_event_v2, ..."

# Tool versioning
tools:
  - name: create_event
    version: 1.0.0
    deprecated: true
    replacement: create_event_v2
  - name: create_event_v2
    version: 2.0.0
    status: active
```

**Priority:** 🟠 **HIGH** (deployment flexibility blocker)

---

**❌ 5. Tool Performance Budgets & SLO Enforcement**

**Current State:** Tool registry has `latency_hint` and `cost_hint` metadata (not enforced)

**Missing:**
- SLO enforcement (if tool exceeds `latency_hint`, trip circuit breaker?)
- Performance monitoring per tool (which tools are slow? Which fail often?)
- Cost tracking (which tools consume most API credits? Budget alerts?)
- Adaptive timeout adjustment (if tool usually takes 2s, increase timeout)

**Impact:** No observability, cost overruns, slow tools degrade UX, no SLO accountability

**Examples:**
```yaml
# Current: Hints only (not enforced)
calendar_api:
  latency_hint: 500ms  # Not enforced!
  cost_hint: $0.001    # Not tracked!

# Needed: SLO enforcement
calendar_api:
  slo:
    p50_latency_ms: 300  # Median
    p95_latency_ms: 500  # 95th percentile
    p99_latency_ms: 1000 # 99th percentile
    error_rate_max: 0.01 # 1% max error rate
    cost_per_call_usd: 0.001
    cost_budget_daily_usd: 10.00  # Alert if exceeded

  enforcement:
    circuit_breaker:
      failure_threshold: 3      # Trip after 3 failures
      timeout_threshold_ms: 1500 # Trip if >1.5× p99 latency
    alerts:
      - type: slack
        condition: error_rate > 0.05
      - type: email
        condition: daily_cost > $10

# Monitoring dashboard
Tool Performance (Last 24h):
  calendar_api: P50=280ms P95=450ms P99=900ms ✅ (within SLO)
  weather_api:  P50=150ms P95=2500ms P99=4000ms ❌ (exceeds SLO)
  bank_api:     Cost=$12.50 ⚠️ (over budget)
```

**Priority:** 🟠 **HIGH** (production observability blocker)

---

### Medium Priority Gaps (1)

**❌ 6. Tool Context Injection**

**Current State:** Tools execute in sandboxes with capabilities, but no user context

**Missing:**
- How does tool get user context? (`user_id`, `session_id`, `cognitive_trace_id`)
- How does tool get SessionState? (current location, calendar events, family members)
- Privacy boundaries: Should tool see full SessionState or filtered view?

**Impact:** Tool personalization limited, context-aware tools can't work, privacy risks

**Examples:**
```python
# Current: No context
result = tool_runner.execute("weather_api", {"location": "New York"})

# Needed: Context injection
context = {
    "user_id": "user_123",
    "session_id": "session_456",
    "cognitive_trace_id": "trace_789",
    "session_state": {
        "current_location": {"lat": 40.7128, "lon": -74.0060},
        "calendar_next_event": "Team meeting at 2pm",
        "privacy_band": "GREEN"  # Tool can access GREEN band data only
    }
}
result = tool_runner.execute("weather_api", {"location": "current"}, context=context)
# Tool resolves "current" → uses context.session_state.current_location
```

**Priority:** 🟡 **MEDIUM** (enhancement, not blocker)

---

### Summary Statistics

**Covered:** 5/11 major concerns (45%)
- ✅ Sandbox architecture (MCP/WASM/Process)
- ✅ Tool registry (JSON specs with metadata)
- ✅ Tool call protocol (JSON-RPC 2.0, MPST validation)
- ✅ User confirmation protocol (ADR-0052, 4 extensions)
- ✅ Lifecycle management (circuit breaker, DLQ, quarantine)

**Critical Gaps:** 2 (production blockers)
1. Tool Chaining & Orchestration (automatic, tool-centric)
2. Tool Result Parsing & Validation

**High Priority Gaps:** 3 (essential features)
3. Agent-Tool Integration Patterns
4. Dynamic Tool Discovery
5. Tool Performance Budgets & SLOs

**Medium Priority Gaps:** 1 (enhancements)
6. Tool Context Injection

**New ADRs Required:** 6 (2 CRITICAL, 3 HIGH, 1 MEDIUM)

### Integration Points

**System 41 integrates with:**
- **ADR-0001e:** P21+ Integration Pipeline (sandbox foundation)
- **ADR-0033b:** WASM Sandbox Implementation (HIGH isolation)
- **ADR-0052:** Enhanced HITL Protocols (user-driven orchestration)
- **ADR-0004:** 56-Module Architecture (tool registry module)
- **ADR-0007:** 4-Stage Planning Pipeline (tool schema lookup)
- **ADR-0003:** MPST Protocol Validation (tool call protocol)
- **System 40:** Tiered Chat History (context for tool personalization)
- **Three-Tier Hierarchy:** ConciergeAgent/Specialists invoke tools

### Next Steps

1. **Document critical gaps** (2 new ADRs):
   - ADR-TBD: Tool Chaining & Orchestration Protocol (automatic, dependency graphs, parallel execution)
   - ADR-TBD: Tool Result Schema Validation & Error Recovery

2. **Document high priority gaps** (3 new ADRs):
   - ADR-TBD: Agent-Tool Integration Patterns (discovery, capability mapping, access control)
   - ADR-TBD: Dynamic Tool Discovery & Hot-Reload (runtime discovery, versioning, deprecation)
   - ADR-TBD: Tool Performance Budgets & SLO Enforcement (monitoring, circuit breaker, cost tracking)

3. **Defer medium priority gap** (1 ADR, can be part of proactive behavior design):
   - ADR-TBD: Tool Context Injection Protocol (privacy-aware context passing)

4. **Proceed to proactive behavior design** with full context on tool capabilities and gaps

**Performance:**

- Session summarization: <2s (background, every 10 turns)
- Context selection: <10ms (in-memory)
- K0 deep retrieval: ~100-200ms (when needed)
- Net impact: Minimal latency, massive cost savings

---

## 🔮 System 42: Proactive Behavior & Anticipatory Actions

**Status:** 📐 Design Complete (2025-11-03)
**Type:** Core Intelligence - Proactive Computing
**Complexity:** MAJOR (comparable to Three-Tier Hierarchy, Tiered Chat History)
**Research:** Tennenhouse 2000 (Proactive Computing), Horvitz 2003 (Attention-Sensitive Alerting), Ryan & Deci 2000 (Self-Determination Theory), Lee & See 2004 (Trust Calibration)

### Executive Summary

**System-initiated actions and suggestions based on learned patterns, context, and user goals WITHOUT explicit user request.**

**Key Transformation:**
- **Reactive:** User asks "Remind me to take medication" → System responds
- **Proactive:** System notices user usually takes medication at 9am, missed today → System initiates reminder

**Core Innovation:** Event-driven trigger architecture with confidence-based thresholds, user control, and adaptive learning from feedback.

**Coverage:** 45% tool integration foundation (ADR-0001e sandboxes, ADR-0052 confirmation) enables proactive tool usage.

---

### Research Foundation

**1. Proactive Computing (Tennenhouse 2000)**
- Anticipate user needs before explicit request
- Context-aware triggering
- Balance helpfulness vs intrusiveness

**2. Interruption Research (Horvitz et al. 1999, 2003)**
- Cost-benefit analysis of interruptions
- Attention-sensitive alerting
- User interruptibility models (busy/available/deep work)

**3. Anticipatory UX (Apple Proactive Assistant, Google Now)**
- Time-based triggers (morning routine, commute)
- Location-based triggers (arrive home → suggest tasks)
- Pattern-based triggers (usually order coffee at 10am)

**4. Human Autonomy (Self-Determination Theory, Ryan & Deci 2000)**
- **Support vs control:** Proactive SUPPORT (suggestions) good, CONTROL (forced actions) bad
- **User agency:** Always allow dismissal, "don't suggest this again"
- **Adaptive:** Learn from user acceptance/rejection

**5. Trust Calibration (Lee & See 2004)**
- **Over-trust:** User relies too much, system makes mistake → Harm
- **Under-trust:** User ignores helpful suggestions → Wasted opportunity
- **Right-calibration:** User accepts ~70% of suggestions (sweet spot)

---

### Core Design Principles

**1. Trigger-Based Architecture (Not Polling)**
- Event-driven triggers (time, location, pattern, anomaly)
- Efficient: Don't check constantly, respond to signals
- Observable: Clear why system triggered

**2. Confidence Thresholds (Risk-Aware)**
- **HIGH (>0.9):** Auto-execute safe actions (turn on lights when home)
- **MEDIUM (0.7-0.9):** Suggest with one-tap approval (medication reminder)
- **LOW (<0.7):** Don't interrupt, log for learning only

**3. User Control & Transparency**
- Always explain WHY triggered ("You usually take medication at 9am")
- Always allow dismissal ("Not now", "Don't remind me about this")
- Learn from feedback (user dismisses 3× → stop suggesting)

**4. Graceful Degradation**
- Start conservative (few suggestions, high confidence only)
- Gradually increase as user accepts suggestions (build trust)
- Back off if user rejects frequently (recalibrate)

**5. Integration with K0 Kernel (Event-Driven Architecture)**

**CRITICAL: K0 ↔ K1 Boundary**
- **K0 owns:** Trigger storage, evaluation, scheduling, event generation (via P05 pipeline)
- **K1 owns:** Event subscription (SSE), confidence scoring, suggestion delivery, feedback processing
- **Interface:** K0 SSE Port (publish) → K1 ProactiveAgent (subscribe)

**Integration Points:**
- **K0 P05 (Prospective/Triggers):** Stores triggers, evaluates schedules, emits `prospective.*` events
- **K0 SSE Port:** Real-time event delivery via Server-Sent Events
- **K0 P01 (Recall):** Historical pattern detection for trigger creation
- **K0 Command Port:** K1 → K0 trigger registration/updates
- **K1 Tool Execution (P21-P30):** Execute proactive actions
- **ADR-0052:** Confirmation protocols for risky proactive actions

---

### Key Architectural Components

#### 1. ProactiveAgent (New Tier 2 Specialist)

**Role:** Subscribe to K0 prospective events, generate suggestions, process feedback

**Capabilities:**
- `confidence_scoring` - Score suggestion reliability (0.0-1.0) based on K0 event
- `suggestion_generation` - Generate action-oriented suggestions from trigger events
- `feedback_processing` - Learn from user acceptance/rejection, update K0 triggers
- `sse_subscription` - Subscribe to `prospective.*` topic via K0 SSE Port

**Integration:**
- Works alongside existing Tier 2 specialists (HealthcareAgent, FinanceAgent, PlannerAgent)
- Doesn't replace specialists, augments with proactive monitoring
- Invokes specialists for proactive actions (e.g., HealthcareAgent for medication)

**Lifecycle:**
- **Always Active:** Tier 2 specialist in ACTIVE state (not on-demand)
- **SSE subscription:** Maintains persistent SSE connection to K0 (`prospective.*` topic)
- **Fast wakeup:** Generates suggestion within 100ms of K0 event

**Event Processing:**
```python
class ProactiveAgent:
    async def subscribe_to_k0_events(self):
        """Maintain SSE subscription to K0 prospective.* events"""
        async with sse_client.subscribe(
            topics=["prospective.trigger.fired", "prospective.reminder.due"],
            subscriber_id=self.agent_id
        ) as stream:
            async for event in stream:
                await self.handle_trigger_event(event)

    async def handle_trigger_event(self, event):
        """Process K0 trigger event → confidence scoring → suggestion"""
        trigger_data = event.payload  # From K0 P05
        confidence = self.score_confidence(trigger_data)

        if confidence >= 0.7:
            suggestion = self.generate_suggestion(trigger_data, confidence)
            await self.send_to_concierge(suggestion)
        else:
            # Learn only, don't interrupt
            self.log_pattern(trigger_data, confidence)
```

---

#### 2. K0 P05 Trigger System (Kernel-Owned)

**Architecture:** K0 P05 pipeline owns ALL trigger logic (storage, evaluation, event emission)

**4 Trigger Types in K0:**

**A. TimeBasedTrigger (K0 Cron/Scheduler)**
```sql
-- K0 trigger table (SQLite)
CREATE TABLE prospective_triggers (
  trigger_id TEXT PRIMARY KEY,
  type TEXT NOT NULL,  -- 'time' | 'location' | 'pattern' | 'anomaly'
  schedule TEXT,       -- Cron expression: "0 9 * * *" (9am daily)
  tolerance_sec INTEGER, -- ±300 sec (5min window)
  action TEXT NOT NULL,  -- 'medication_reminder'
  pattern_strength REAL, -- 0.95 (95% success rate)
  user_id TEXT,
  space_id TEXT,
  enabled INTEGER DEFAULT 1,
  created_at TEXT,
  updated_at TEXT
);
```

**K0 P05 Evaluation:**
```python
# k0/pipelines/p05.py (simplified)
class ProspectivePipeline:
    async def evaluate_triggers(self):
        """K0 scheduler checks trigger table every minute"""
        now = datetime.now(tz=timezone.utc)

        for trigger in self.fetch_due_triggers(now):
            # Emit event to K0 Bus → SSE Port
            event = {
                "topic": "prospective.trigger.fired",
                "trigger_id": trigger.trigger_id,
                "action": trigger.action,
                "pattern_strength": trigger.pattern_strength,
                "timestamp": now.isoformat()
            }
            await self.k0_bus.publish(event)

            # Update trigger last_fired_at
            self.update_trigger(trigger.trigger_id, last_fired_at=now)
```

**B. LocationBasedTrigger (K0 Geofence)**
```sql
-- K0 location trigger
INSERT INTO prospective_triggers VALUES (
  'arrive_home',
  'location',
  NULL,  -- No cron schedule
  300,   -- 5min tolerance
  'turn_on_lights',
  0.92,  -- Pattern strength
  'user_123',
  'space_456',
  1,     -- Enabled
  '2025-11-03T12:00:00Z',
  '2025-11-03T12:00:00Z'
);

-- Triggered by K0 event: "location.geofence.entered"
-- K0 P05 listens to location.* events, checks trigger table
```

**C. PatternBasedTrigger (K0 Pattern Detector)**
```sql
-- K0 pattern trigger (grocery restocking)
INSERT INTO prospective_triggers VALUES (
  'grocery_restock_milk',
  'pattern',
  NULL,  -- No fixed schedule
  86400, -- ±1 day tolerance
  'suggest_milk_order',
  0.88,  -- 15/17 occurrences
  'user_123',
  'space_456',
  1,
  '2025-11-03T12:00:00Z',
  '2025-11-03T12:00:00Z'
);

-- K0 P01 (Recall) detects pattern: "milk order every 7 days"
-- K0 P05 checks: last_milk_order > 6 days → Emit event
```

**D. AnomalyBasedTrigger (K0 Anomaly Detector)**
```sql
-- K0 anomaly trigger (unusual transaction)
INSERT INTO prospective_triggers VALUES (
  'unusual_transaction',
  'anomaly',
  NULL,  -- No schedule
  0,     -- No tolerance
  'confirm_unusual_transaction',
  0.85,  -- High confidence in anomaly detection
  'user_123',
  'space_456',
  1,
  '2025-11-03T12:00:00Z',
  '2025-11-03T12:00:00Z'
);

-- K0 P01 (Recall) calculates baseline: avg=$250, stddev=$50
-- K0 P05 checks: transaction > $400 (3× stddev) → Emit event
```

**K0 P05 → SSE Flow:**
```
K0 Scheduler (cron/minute) → P05 evaluate_triggers()
  → Fetch due triggers from SQLite
  → Emit event {topic: "prospective.trigger.fired", ...}
  → K0 Bus (in-kernel)
  → SSE Port (fan-out to subscribed K1 agents)
  → K1 ProactiveAgent receives SSE event
```

**Trigger Registration (K1 → K0):**
```python
# k1/l2_orchestration/proactive_agent.py
class ProactiveAgent:
    async def register_trigger(self, trigger_spec):
        """Register trigger via K0 Command Port"""
        response = await self.k0_command_port.submit({
            "operation": "prospective.register_trigger",
            "trigger": {
                "type": "time",
                "schedule": "0 9 * * *",  # 9am daily
                "tolerance_sec": 300,     # ±5min
                "action": "medication_reminder",
                "pattern_strength": 0.95
            }
        })
        return response.trigger_id
```

---

#### 3. Confidence Scoring Engine

**Inputs:**
1. **Pattern strength** (0.0-1.0) - How consistent is the pattern?
   - `pattern_strength = successful_occurrences / total_opportunities`
   - Example: Medication 30/32 times = 0.94

2. **Historical success rate** (0.0-1.0) - How often does user accept THIS suggestion?
   - `success_rate = accepted / (accepted + dismissed)`
   - Example: User accepted medication reminder 28/30 times = 0.93

3. **Context alignment** (0.0-1.0) - Does current context match pattern context?
   - Time match: Within schedule ± tolerance? (+0.1)
   - Location match: At expected location? (+0.1)
   - Calendar match: No conflicts? (+0.05)

4. **User receptivity** (0.0-1.0) - Is user available/interruptible?
   - Deep work mode: -0.2 (user in focused session)
   - Available: +0.0 (default)
   - Recently dismissed: -0.3 (user dismissed similar suggestion <10min ago)

**Scoring Formula (Rule-Based):**
```python
confidence = (
    pattern_strength × 0.4 +
    success_rate × 0.3 +
    context_alignment × 0.2 +
    user_receptivity × 0.1
)
# Capped at 0.0-1.0
```

**Output:**
- Confidence score (0.0-1.0)
- Explanation string ("You usually take medication at 9am ± 5min, success rate 93%")
- Decision: AUTO_EXECUTE | SUGGEST | LEARN_ONLY

**Thresholds:**
- **AUTO_EXECUTE:** confidence > 0.9 AND action_risk = LOW (safe actions only)
- **SUGGEST:** 0.7 ≤ confidence ≤ 0.9 (one-tap approval)
- **LEARN_ONLY:** confidence < 0.7 (don't interrupt, log pattern)

---

#### 4. Suggestion Delivery System

**Delivery Channels:**

**A. In-Context (During Chat)**
```
User: [chatting with ConciergeAgent]
ConciergeAgent: "By the way, it's 9:05am - time for your blood pressure medication?"
  [Accept] [Not now] [Don't remind me]
```

**B. Push Notification (Background)**
```
📱 Notification:
"Time for blood pressure medication (9:05am)"
[Take now] [Dismiss] [Remind in 10min]
```

**C. Ambient Display (Smart Home)**
```
🪟 Smart Mirror (bathroom):
"Good morning! Medication reminder: 9:05am"
[Voice: "OK, taken"] [Dismiss]
```

**Timing (Attention-Sensitive):**
- **Immediate:** HIGH confidence (>0.9), time-critical (medication window)
- **Next interaction:** MEDIUM confidence (0.7-0.9), not urgent (grocery suggestion)
- **Defer:** User in deep work mode (don't interrupt)
- **Never:** LOW confidence (<0.7), learn only

**Format (Action-Oriented):**
- ✅ **Good:** "Take medication now?" (action verb, question)
- ❌ **Bad:** "It's time for medication" (informational, passive)

---

#### 5. Feedback Loop & Learning

**Explicit Feedback:**
```yaml
user_responses:
  - accept: confidence += 0.05, success_count++
  - dismiss: confidence -= 0.03, dismiss_count++
  - not_now: confidence -= 0.01, defer_count++
  - never_again: confidence = 0.0, disable_trigger for category
```

**Implicit Feedback:**
```python
# Missed opportunity detection
if user_manually_does_action_after_dismissing_suggestion:
    confidence += 0.02  # User wanted it, just bad timing
    suggest_earlier_next_time = True

# False positive detection
if user_dismisses_immediately_3_times_in_row:
    confidence -= 0.15  # Clearly not wanted
    back_off_for_7_days = True
```

**Adaptation Strategies:**

**1. Confidence Threshold Adjustment**
```python
if success_rate > 0.85:  # User loves this suggestion
    confidence_threshold_suggest = 0.65  # Lower threshold, suggest more
elif success_rate < 0.60:  # User rejects often
    confidence_threshold_suggest = 0.80  # Raise threshold, suggest less
```

**2. Temporal Adjustment**
```python
if user_accepts_but_10min_later:
    suggested_time += timedelta(minutes=10)  # Shift suggestion time
```

**3. Category Disablement**
```python
if dismiss_count_for_category > 10 AND success_rate < 0.3:
    disable_category(category)  # Stop all suggestions in category
    notify_user("Disabled proactive suggestions for {category}")
```

---

#### 6. Proactivity Settings (User Preferences)

**Global Levels:**
```yaml
proactivity_level:
  OFF: 0 suggestions (disable all triggers)
  LOW: Only CRITICAL suggestions (medication, safety, conflicts)
  MEDIUM: CRITICAL + helpful suggestions (default)
  HIGH: Aggressive suggestions (predict many needs)
```

**Per-Category Settings:**
```yaml
user_preferences:
  medication: HIGH      # Always remind (health critical)
  grocery: MEDIUM       # Suggest when pattern strong
  social: LOW           # Don't push social suggestions
  financial: HIGH       # Always confirm unusual transactions
  smart_home: HIGH      # Auto-execute safe actions (lights, thermostat)
  calendar: MEDIUM      # Suggest conflict resolution
```

**Temporal Settings:**
```yaml
time_preferences:
  weekday_morning: HIGH    # More proactive (morning routine)
  weekday_evening: MEDIUM  # Moderate (winding down)
  weekend: LOW             # Less proactive (user wants freedom)
  night: OFF               # Never interrupt sleep
```

**Notification Limits (Fatigue Prevention):**
```yaml
rate_limits:
  max_per_hour: 3      # Max 3 suggestions/hour
  max_per_day: 15      # Max 15 suggestions/day
  min_gap_seconds: 600 # Min 10min between suggestions
```

---

### Example Proactive Scenarios

#### Scenario 1: Medication Reminder (Time + Pattern)

**Trigger:**
```yaml
trigger: TimeBasedTrigger("medication_09am")
time: 09:05 (5min late)
pattern: user_takes_med at 09:00 ± 5min on 95% of days
```

**Confidence Scoring:**
```python
pattern_strength = 0.95  # 30/32 days
success_rate = 0.93      # User accepted 28/30 reminders
context_alignment = 0.95 # Within 5min window
user_receptivity = 1.0   # Available (not in deep work)

confidence = 0.95×0.4 + 0.93×0.3 + 0.95×0.2 + 1.0×0.1
           = 0.38 + 0.279 + 0.19 + 0.1
           = 0.949 → 0.95
```

**Decision:** confidence = 0.95 > 0.9 AND action_risk = LOW → **SUGGEST** (one-tap)

**Delivery:**
```
[In-context if user chatting, push notification otherwise]

"Time for your blood pressure medication? (9:05am)"
[Accept] [Not now] [Don't remind me]

Explanation: "You usually take medication at 9am ± 5min (95% of days)"
```

**Feedback:**
- User accepts → `success_count++`, confidence stays high
- User dismisses → `confidence -= 0.03`, next reminder at 9:07am (shift +2min)

---

#### Scenario 2: Grocery Restocking (Pattern + Anomaly)

**Trigger:**
```yaml
trigger: PatternBasedTrigger("milk_restock")
pattern: milk_order every 7 days ± 1 day
evidence: 15 occurrences
condition: milk_last_ordered = 6 days ago AND no_pending_order
```

**Confidence Scoring:**
```python
pattern_strength = 0.88  # 15/17 times (2 missed)
success_rate = 0.75      # User accepted 15/20 grocery suggestions
context_alignment = 0.9  # Within 7±1 day window (day 6)
user_receptivity = 1.0   # Available

confidence = 0.88×0.4 + 0.75×0.3 + 0.9×0.2 + 1.0×0.1
           = 0.352 + 0.225 + 0.18 + 0.1
           = 0.857 → 0.86
```

**Decision:** 0.7 ≤ confidence = 0.86 < 0.9 → **SUGGEST** (one-tap)

**Delivery:**
```
[In-context during chat, low priority]

"Add milk to grocery list? (Usually restock Sundays, last order 6 days ago)"
[Add to list] [Not yet] [Don't suggest]
```

**Feedback:**
- User dismisses → `confidence -= 0.03`, wait 2 more days (re-trigger at day 8)
- User manually orders milk 1 day later → `confidence += 0.02` (missed opportunity, suggest earlier next time)

---

#### Scenario 3: Calendar Conflict Prevention (Event + Context)

**Trigger:**
```yaml
trigger: AnomalyBasedTrigger("calendar_conflict")
event: user_accepted_meeting_invite
conflict: overlaps with "Emma's soccer practice" (4pm recurring event)
```

**Confidence Scoring:**
```python
pattern_strength = 1.0   # Calendar data certain (no ambiguity)
success_rate = 0.92      # User accepted 23/25 conflict warnings
context_alignment = 1.0  # Conflict is certain, family priority clear
user_receptivity = 1.0   # Available

confidence = 1.0×0.4 + 0.92×0.3 + 1.0×0.2 + 1.0×0.1
           = 0.4 + 0.276 + 0.2 + 0.1
           = 0.976 → 0.98
```

**Decision:** confidence = 0.98 > 0.9 AND action_risk = LOW → **SUGGEST** (immediate)

**Delivery:**
```
[Immediate, in-context]

"⚠️ This meeting conflicts with Emma's soccer practice (4pm).
Suggest alternate time to organizer?"
[Yes, suggest alternate] [I'll handle it] [Keep conflict]

Explanation: "Family priority (soccer practice) marked as recurring high-priority event"
```

**Feedback:**
- User accepts → System drafts email: "I have a conflict at 4pm. Can we do 2pm or 5pm instead?"
- User selects "I'll handle it" → `confidence -= 0.0` (user handled, not rejection)

---

#### Scenario 4: Commute Preparation (Time + Location + Weather)

**Trigger:**
```yaml
trigger: TimeBasedTrigger("commute_prep")
time: 07:45 (user leaves at 08:00, 15min before)
location: home
weather: heavy_rain detected (API call)
```

**Confidence Scoring:**
```python
# Action 1: Turn on garage heater (safe, auto-execute)
pattern_strength = 0.92  # User leaves at 8am 92% of weekdays
action_risk = LOW        # Safe smart home action
confidence_action1 = 0.92 > 0.9 → AUTO_EXECUTE

# Action 2: Suggest leave early (requires user decision)
pattern_strength = 0.88  # Traffic delay pattern on rainy days
success_rate = 0.70      # User accepted "leave early" 14/20 times
context_alignment = 0.95 # Heavy rain confirmed, weekday commute
user_receptivity = 1.0   # Available

confidence_action2 = 0.88×0.4 + 0.70×0.3 + 0.95×0.2 + 1.0×0.1
                   = 0.352 + 0.21 + 0.19 + 0.1
                   = 0.852 → 0.85
```

**Decision:**
- Action 1 (garage heater): confidence = 0.92 > 0.9 AND action_risk = LOW → **AUTO_EXECUTE**
- Action 2 (leave early): 0.7 ≤ confidence = 0.85 < 0.9 → **SUGGEST**

**Delivery:**
```
[Push notification at 7:45am]

"✅ Turned on garage heater (cold morning)

⚠️ Heavy rain detected. Suggest leaving 10min early? (8am commute)"
[Leave at 7:50] [Leave at 8:00] [Dismiss]

Explanation: "Traffic delay pattern on rainy days (70% acceptance rate)"
```

**Feedback:**
- User dismisses 2× in a row → `confidence -= 0.06`, threshold → 0.88 (less aggressive with traffic suggestions)

---

#### Scenario 5: Social Coordination (Pattern + Belief) - LOW Confidence

**Trigger:**
```yaml
trigger: PatternBasedTrigger("weekend_planning")
time: Friday 18:00
pattern: "user plans weekend activities on Friday evening"
evidence: 3 occurrences (weak pattern)
```

**Confidence Scoring:**
```python
pattern_strength = 0.50  # Only 3/6 Fridays (weak evidence)
success_rate = 0.00      # Never suggested before (no history)
context_alignment = 0.9  # Friday 6pm matches pattern
user_receptivity = 1.0   # Available

confidence = 0.50×0.4 + 0.00×0.3 + 0.9×0.2 + 1.0×0.1
           = 0.2 + 0.0 + 0.18 + 0.1
           = 0.48 → 0.48
```

**Decision:** confidence = 0.48 < 0.7 → **LEARN_ONLY** (don't interrupt yet)

**Delivery:**
```
[No suggestion to user]

Internal logging:
  event: "weekend_planning_pattern_detected"
  confidence: 0.48
  action: "LEARN_ONLY (confidence too low)"
  next_steps: "Increment pattern count if user manually asks 'what should we do this weekend?'"
```

**Feedback:**
- If user manually asks "What should we do this weekend?" later → `pattern_count++`, confidence → 0.55
- After 3 more confirming occurrences → confidence > 0.7 → **START SUGGESTING**

---

### SessionState Integration

**New Section: `proactive`**

```python
@dataclass
class ProactiveSuggestion:
    suggestion_id: str          # Unique ID (e.g., "med_reminder_20251103_0905")
    type: str                   # "medication_reminder" | "grocery_restock" | etc.
    trigger_id: str             # Which trigger fired (e.g., "medication_09am")
    confidence: float           # 0.0-1.0
    action: str                 # "suggest_medication" | "turn_on_lights" | etc.
    explanation: str            # Why triggered
    status: str                 # "pending" | "accepted" | "dismissed" | "expired"
    created_at: datetime
    expires_at: datetime        # Auto-expire after N minutes
    delivery_channel: str       # "in_context" | "push" | "ambient"

@dataclass
class FeedbackHistory:
    accepted: int = 0
    dismissed: int = 0
    not_now: int = 0
    never_again: int = 0
    success_rate: float = 0.0   # accepted / (accepted + dismissed)

@dataclass
class ProactiveState:
    enabled: bool = True
    level: str = "MEDIUM"       # OFF | LOW | MEDIUM | HIGH
    active_suggestions: List[ProactiveSuggestion] = field(default_factory=list)
    feedback_history: Dict[str, FeedbackHistory] = field(default_factory=dict)
    user_preferences: Dict[str, str] = field(default_factory=dict)
    disabled_triggers: List[str] = field(default_factory=list)
    last_suggestion_time: Optional[datetime] = None
    suggestions_today: int = 0

# Add to SessionState
class SessionState:
    ...
    proactive: ProactiveState = field(default_factory=ProactiveState)
```

**Example SessionState.proactive:**
```yaml
proactive:
  enabled: true
  level: "MEDIUM"
  active_suggestions:
    - suggestion_id: "med_reminder_20251103_0905"
      type: "medication_reminder"
      trigger_id: "medication_09am"
      confidence: 0.95
      action: "suggest_medication"
      explanation: "You usually take medication at 9am ± 5min (95% of days)"
      status: "pending"
      created_at: "2025-11-03T09:05:00Z"
      expires_at: "2025-11-03T09:30:00Z"
      delivery_channel: "push"

  feedback_history:
    medication_reminders:
      accepted: 30
      dismissed: 2
      not_now: 0
      never_again: 0
      success_rate: 0.94
    grocery_restock:
      accepted: 15
      dismissed: 5
      not_now: 3
      never_again: 0
      success_rate: 0.75

  user_preferences:
    medication: "HIGH"
    grocery: "MEDIUM"
    social: "LOW"
    financial: "HIGH"
    smart_home: "HIGH"
    calendar: "MEDIUM"

  disabled_triggers: []
  last_suggestion_time: "2025-11-03T09:05:00Z"
  suggestions_today: 8
```

---

### K0 Integration (Pattern Detection)

**P01 (Recall) Query for Pattern Detection:**

```python
# Query: "Detect medication timing pattern"
recall_query = {
    "query_type": "temporal_pattern",
    "entity": "medication",
    "window": "last_30_days",
    "filters": {
        "action": "take_medication",
        "medication_name": "blood_pressure"
    }
}

# K0 returns:
pattern = {
    "pattern_type": "daily_temporal",
    "schedule": "09:00 ± 5min",
    "frequency": 30/32,  # 30 out of 32 days
    "confidence": 0.95,
    "outliers": [
        {"date": "2025-10-20", "time": "14:00", "reason": "doctor_appointment"},
        {"date": "2025-10-27", "time": "missed", "reason": "unknown"}
    ],
    "recommendation": "suggest_at_09:00_with_5min_tolerance"
}
```

**P01 Query for Anomaly Detection:**

```python
# Query: "Detect unusual financial transaction"
recall_query = {
    "query_type": "anomaly_detection",
    "entity": "financial_transfer",
    "window": "last_90_days",
    "current_value": 500.00
}

# K0 returns:
anomaly = {
    "baseline": {
        "mean": 250.00,
        "stddev": 50.00,
        "p95": 350.00
    },
    "current_value": 500.00,
    "z_score": 5.0,  # (500 - 250) / 50 = 5
    "is_anomaly": true,
    "confidence": 0.99,
    "explanation": "Transfer amount $500 is 5× standard deviations above mean ($250 ± $50)"
}
```

---

### Tool Execution Integration (P21-P30)

**Proactive Tool Usage:**

```python
# Example: Proactive smart home action
if confidence > 0.9 and action_risk == LOW:
    # AUTO_EXECUTE via tool integration
    result = tool_runner.execute(
        tool="philips_hue",
        action="turn_on",
        params={"room": "living_room", "brightness": 75},
        context={
            "proactive": true,
            "trigger_id": "arrive_home",
            "confidence": 0.92
        }
    )

    # Notify user of auto-executed action
    notification = f"✅ Turned on living room lights (you arrived home)"
```

**Confirmation Protocol Integration (ADR-0052):**

```python
# Map confidence to approval level
def get_approval_level(confidence: float, action_risk: str) -> str:
    if confidence > 0.9 and action_risk == "LOW":
        return "LOW"  # Auto-execute or one-button confirm
    elif 0.7 <= confidence <= 0.9:
        return "MEDIUM"  # Type "CONFIRM"
    elif confidence > 0.7 and action_risk == "HIGH":
        return "HIGH"  # Type exact phrase
    elif action_risk == "CRITICAL":
        return "CRITICAL"  # Two-person approval (RED band)
    else:
        return None  # Don't suggest (confidence too low)

# Use ADR-0052 confirmation protocol
approval_level = get_approval_level(confidence=0.85, action_risk="MEDIUM")
if approval_level:
    confirmation_request = {
        "clarification_type": "RED_BAND_APPROVAL" if approval_level == "CRITICAL" else "APPROVAL",
        "approval_level": approval_level,
        "operation": action,
        "explanation": explanation,
        "required_phrase": "CONFIRM" if approval_level == "MEDIUM" else None
    }
```

---

### Three-Tier Agent Hierarchy Integration

**ConciergeAgent (Tier 1) - Routes Proactive Suggestions:**
```python
class ConciergeAgent:
    def handle_proactive_suggestion(self, suggestion: ProactiveSuggestion):
        """
        Route proactive suggestion to user, handle meta-intents.
        """
        # Meta-intent detection
        if user_input == "not now":
            self.defer_suggestion(suggestion, minutes=10)
        elif user_input == "don't remind me about this":
            self.disable_trigger(suggestion.trigger_id)
        elif user_input == "accept" or user_input == "yes":
            self.execute_proactive_action(suggestion)
        else:
            # Unknown response, clarify
            self.ask_clarification("Accept, dismiss, or defer?")
```

**ProactiveAgent (Tier 2) - NEW Specialist:**
```python
class ProactiveAgent:
    """
    Tier 2 specialist for proactive behavior monitoring and suggestions.

    Lifecycle: Always ACTIVE (background monitoring)
    """

    def __init__(self):
        self.trigger_system = TriggerSystem()
        self.confidence_scorer = ConfidenceScorer()
        self.feedback_processor = FeedbackProcessor()

    async def monitor_triggers(self):
        """Background loop: Check triggers on events"""
        while self.active:
            event = await self.event_bus.wait_for_event()
            triggered = self.trigger_system.evaluate(event)

            if triggered:
                confidence = self.confidence_scorer.score(triggered)

                if confidence >= 0.7:
                    suggestion = self.generate_suggestion(triggered, confidence)
                    await self.send_to_concierge(suggestion)
                else:
                    # Learn only, don't suggest
                    self.log_pattern(triggered, confidence)

    def generate_suggestion(self, trigger, confidence):
        """Generate action-oriented suggestion with explanation"""
        pass

    def process_feedback(self, suggestion_id, feedback_type):
        """Learn from user acceptance/rejection"""
        pass
```

**Specialist Agents (Tier 2) - Execute Proactive Actions:**
```python
# Example: HealthcareAgent executes medication reminder
class HealthcareAgent:
    async def execute_proactive_action(self, action: str, params: dict):
        if action == "suggest_medication":
            # Check medication schedule from beliefs
            med_schedule = self.session_state.beliefs.get("medication_schedule")

            # Generate suggestion
            suggestion = {
                "message": f"Time for your {params['medication_name']}?",
                "actions": ["Take now", "Remind in 10min", "Dismiss"]
            }

            return suggestion
```

---

### Performance Budgets

**Latency Targets (P95) - K0 ↔ K1 Event-Driven:**

**K0 Side (Kernel):**
- K0 P05 trigger evaluation: <50ms per trigger check (cron scheduler)
- K0 P01 pattern detection: <100ms (historical query for pattern strength)
- K0 Bus publish: <5ms (in-kernel fan-out)
- SSE Port delivery: <10ms (push to K1 subscribers)
- **K0 Total (trigger → SSE):** <165ms P95

**K1 Side (User-Space):**
- SSE event receipt: <5ms (network + deserialization)
- Confidence scoring: <50ms (rule-based algorithm)
- LLM suggestion generation: <200ms (lightweight prompt)
- Send to ConciergeAgent: <10ms (internal K1 routing)
- **K1 Total (SSE → suggestion):** <265ms P95

**End-to-End (K0 trigger → user sees suggestion):**
- **Total latency:** <430ms P95 (was 500ms before K0 optimization)
- **Background monitoring:** 0% CPU (K0 P05 cron-based, not polling)

**Throughput:**
- K0 P05 trigger checks: 1000+ triggers/minute (parallel SQLite queries)
- SSE events per second: 1000+ (K0 Bus capacity)
- K1 suggestions per day: 10-20 per user (rate limited in K1)
- K1 suggestions per hour: Max 3 (fatigue prevention in K1)

**Memory:**
- K0 trigger storage: <10KB per trigger × 100 triggers = <1MB per user
- K1 active suggestions: <5KB per suggestion × 10 active = <50KB per user
- K1 feedback history: <100KB (all categories)
- **Total:** <1.2MB per user session

---

### Observability & Metrics

**K0 Metrics (Prometheus):**
```python
# K0 P05 trigger evaluation
k0_p05_trigger_checks_total(trigger_type, result)  # result: fired | skipped | error
k0_p05_trigger_evaluation_duration_seconds(trigger_type)  # Histogram
k0_p05_events_emitted_total(topic)  # prospective.trigger.fired, prospective.reminder.due

# K0 SSE delivery
k0_sse_events_published_total(topic)
k0_sse_subscribers_gauge(topic)  # Active K1 subscribers
```

**K1 Metrics (Prometheus):**
```python
# K1 ProactiveAgent processing
k1_proactive_events_received_total(trigger_type)
k1_proactive_suggestions_generated_total(type, confidence_level)  # high | medium | low
k1_proactive_suggestions_accepted_total(type)
k1_proactive_suggestions_dismissed_total(type)
k1_proactive_suggestions_never_again_total(type)

# User satisfaction
k1_proactive_success_rate_gauge(type)  # accepted / (accepted + dismissed)
k1_proactive_missed_opportunities_total(type)  # User did manually after dismissing

# Performance
k1_proactive_confidence_scoring_duration_seconds()
k1_proactive_suggestion_generation_duration_seconds()
k1_proactive_sse_event_latency_seconds()  # Time from K0 event to K1 receipt

# Fatigue metrics
k1_proactive_suggestions_per_hour_gauge()
k1_proactive_suggestions_per_day_gauge()
k1_proactive_rate_limited_total()  # Suggestions suppressed due to rate limit
```

**Distributed Tracing (OpenTelemetry):**
```python
# Span chain: K0 → SSE → K1
span_k0_p05_evaluate = tracer.start_span("k0.p05.evaluate_trigger")
span_k0_sse_publish = tracer.start_span("k0.sse.publish", parent=span_k0_p05)
span_k1_sse_receive = tracer.start_span("k1.proactive.sse_receive", parent=span_k0_sse)
span_k1_confidence = tracer.start_span("k1.proactive.confidence_score", parent=span_k1_sse)
span_k1_suggest = tracer.start_span("k1.proactive.generate_suggestion", parent=span_k1_confidence)

# cognitive_trace_id flows: K0 event → K1 suggestion → user response
```

**Logging (Structured):**
```python
# K0 P05 logging
logger.info(
    "k0.p05.trigger_fired",
    trigger_id="med_reminder_001",
    trigger_type="time",
    user_id="user_123",
    scheduled_time="09:00:00",
    actual_time="09:05:12",
    pattern_strength=0.95
)

# K1 ProactiveAgent logging
logger.info(
    "k1.proactive.suggestion_generated",
    suggestion_id="med_reminder_20251103_0905",
    trigger_id="med_reminder_001",
    type="medication_reminder",
    confidence=0.95,
    decision="SUGGEST",
    explanation="User takes med at 9am ± 5min (95% of days)"
)

logger.info(
    "k1.proactive.feedback_received",
    suggestion_id="med_reminder_20251103_0905",
    feedback="accepted",
    previous_success_rate=0.93,
    new_success_rate=0.94
)
```

---

### Privacy & Safety

**1. Pattern Detection (GREEN Band Only by Default):**
- Only use GREEN band data for pattern detection (no sensitive RED data)
- Explicit user consent required for RED band pattern learning
- Example: Financial patterns use aggregated amounts, not transaction details

**2. Proactive Actions Respect Privacy Bands:**
- GREEN band: Auto-execute safe actions (lights, thermostat)
- AMBER band: Suggest with confirmation (calendar changes, messages)
- RED band: Always require explicit confirmation (financial, health data access)
- BLACK band: Never proactive (absolutely forbidden)

**3. Audit Trail:**
- Log all proactive suggestions + user responses
- Retention: 90 days (rolling window)
- Compliance: GDPR right to deletion (user can delete all proactive history)

**4. User Control:**
- **Global disable:** "Turn off proactive behavior" → All triggers disabled
- **Category disable:** "Don't suggest grocery items" → Category-specific disable
- **Trigger disable:** "Never remind me about this" → Single trigger disabled

**5. Safety Thresholds:**
- No auto-execute for risky actions (financial transfers, data deletion, external communications)
- RED band operations always require ADR-0052 CRITICAL approval (two-person rule)
- Anomaly detection thresholds conservative (3× stddev = 99.7% confidence)

---

### Open Questions & Future Work

**Resolved in Design:**
1. ✅ **Trigger Registration:** Declarative YAML (static), hot-reload on file change
2. ✅ **Confidence Scoring:** Rule-based (Phase 1), ML-based (Phase 3 future)
3. ✅ **Notification Fatigue:** Max 3/hour, 15/day, min 10min gap
4. ✅ **Cross-Agent Coordination:** ProactiveAgent orchestrates, specialists execute

**Open for Future Phases:**
5. ❓ **Cold Start:** How to bootstrap patterns for new users?
   - Option A: Generic templates (most users take medication at 9am)
   - Option B: Explicit user onboarding (ask "when do you take medication?")
   - Option C: Learn passively (wait 30 days before suggesting)

6. ❓ **Multi-User (Family Context):** Who gets proactive suggestions?
   - Option A: Per-user suggestions (Dad gets medication, Mom gets calendar)
   - Option B: Shared suggestions (family grocery restocking)
   - Option C: Hybrid (per-user + shared categories)

7. ❓ **Temporal Reasoning:** How to handle "remind me in 30 minutes"?
   - Integration with PlannerAgent (create deferred task)
   - Trigger system enhancement (one-time scheduled triggers)

8. ❓ **ML Model for Confidence:** Replace rule-based scoring?
   - Train on user feedback history (supervised learning)
   - Features: pattern strength, success rate, context, time of day, user state
   - Target: confidence score (0.0-1.0)

---

### Implementation Phases

**Phase 1: Core Architecture (6-8 weeks) - CRITICAL**
- **K0 P05 Extensions:** Trigger storage schema (SQLite), cron scheduler, event emission
- **K1 ProactiveAgent:** SSE subscription, confidence scoring, suggestion generation
- **K0 ↔ K1 Integration:** Command Port trigger registration, SSE event flow
- SessionState.proactive extensions (active_suggestions, feedback_history only - triggers in K0)
- Basic suggestion delivery (in-context only via ConciergeAgent)

**Phase 2: Feedback Loop & Learning (4-6 weeks) - HIGH**
- Explicit feedback handling (accept/dismiss/never-again)
- Implicit feedback detection (manual action = missed opportunity)
- K0 P05 trigger updates (confidence threshold adaptation via Command Port)
- Success rate tracking per category
- Graceful degradation (back off if rejected)

**Phase 3: Advanced Features (8-10 weeks) - MEDIUM**
- Push notifications (beyond in-context)
- Ambient display integration (smart home)
- ML-based confidence scoring (replace rule-based in K1)
- K0 P01 pattern detection enhancements (location, anomaly)
- Multi-modal suggestions (voice, visual, haptic)

**Phase 4: Observability & Tuning (4-6 weeks) - LOW**
- Monitoring dashboard (K0 + K1 metrics combined)
- A/B testing framework (test suggestion phrasing)
- User analytics (which triggers most valuable?)
- Performance optimization (reduce K0 P05 latency, K1 processing)

**Total Estimated Effort:** 22-30 weeks (5-7 months)

---

### Architecture Flow Diagram (K0 ↔ K1 Boundary)

```
┌─────────────────────────────────────────────────────────────────┐
│ K0 KERNEL (Privileged Space)                                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ P05 Prospective/Triggers Pipeline                        │   │
│  │                                                           │   │
│  │  ┌──────────────────────────────────────────┐          │   │
│  │  │ Trigger Storage (SQLite)                 │          │   │
│  │  │  - trigger_id, type, schedule            │          │   │
│  │  │  - pattern_strength, user_id, enabled    │          │   │
│  │  └──────────────────────────────────────────┘          │   │
│  │         │                                                │   │
│  │         ▼                                                │   │
│  │  ┌──────────────────────────────────────────┐          │   │
│  │  │ Cron Scheduler (every minute)            │          │   │
│  │  │  - Fetch due triggers from SQLite        │          │   │
│  │  │  - Evaluate time/pattern/location/anomaly│          │   │
│  │  │  - <50ms P95 per trigger                 │          │   │
│  │  └──────────────────────────────────────────┘          │   │
│  │         │                                                │   │
│  │         ▼                                                │   │
│  │  ┌──────────────────────────────────────────┐          │   │
│  │  │ Event Emitter                             │          │   │
│  │  │  topic: "prospective.trigger.fired"       │          │   │
│  │  │  payload: {trigger_id, action, pattern}   │          │   │
│  │  └──────────────────────────────────────────┘          │   │
│  └──────────────┬────────────────────────────────────────┘   │
│                 │                                              │
│                 ▼                                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ K0 Bus (In-Kernel Fan-Out) <5ms                         │ │
│  └──────────────┬──────────────────────────────────────────┘ │
│                 │                                              │
│                 ▼                                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ SSE Port (Server-Sent Events) <10ms                      │ │
│  │  - Publishes to subscribed K1 agents                     │ │
│  │  - Topic filter: prospective.*                           │ │
│  └──────────────┬──────────────────────────────────────────┘ │
└─────────────────┼───────────────────────────────────────────┘
                  │ SSE Stream (Real-Time)
                  │ Event: {topic, trigger_id, ...}
                  │
┌─────────────────▼───────────────────────────────────────────┐
│ K1 USER-SPACE (Intelligence Layer)                           │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ ProactiveAgent (Tier 2 Specialist) - ALWAYS ACTIVE      ││
│  │                                                           ││
│  │  ┌──────────────────────────────────────────┐          ││
│  │  │ SSE Subscription                          │          ││
│  │  │  - subscribe("prospective.*")             │          ││
│  │  │  - Receive events <5ms                    │          ││
│  │  └──────────────┬───────────────────────────┘          ││
│  │                 │                                        ││
│  │                 ▼                                        ││
│  │  ┌──────────────────────────────────────────┐          ││
│  │  │ Confidence Scoring Engine <50ms           │          ││
│  │  │  - Pattern strength (from K0 event)       │          ││
│  │  │  - Historical success rate (SessionState) │          ││
│  │  │  - Context alignment (SessionState)       │          ││
│  │  │  - Output: confidence (0.0-1.0) + decision│          ││
│  │  └──────────────┬───────────────────────────┘          ││
│  │                 │                                        ││
│  │                 ▼ (if confidence >= 0.7)                ││
│  │  ┌──────────────────────────────────────────┐          ││
│  │  │ Suggestion Generator <200ms (LLM)         │          ││
│  │  │  - Action-oriented message                │          ││
│  │  │  - Explanation + confidence               │          ││
│  │  │  - Delivery channel (in-context/push)     │          ││
│  │  └──────────────┬───────────────────────────┘          ││
│  └─────────────────┼──────────────────────────────────────┘│
│                    │                                         │
│                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ ConciergeAgent (Tier 1) - Route to User <10ms           ││
│  │  - Accept → Execute action via tool (P21-P30)           ││
│  │  - Dismiss → Send feedback to K0 P05                    ││
│  │  - Not now → Defer (re-trigger in 10min)                ││
│  └─────────────────────────────────────────────────────────┘│
│                    │                                         │
└────────────────────┼─────────────────────────────────────────┘
                     │
                     ▼
             ┌───────────────┐
             │ USER DEVICE   │
             │ (UI/Push/SSE) │
             └───────────────┘

LATENCY BREAKDOWN (P95):
- K0 P05 evaluation: 50ms
- K0 Bus publish: 5ms
- SSE delivery: 10ms
- K1 SSE receive: 5ms
- K1 confidence: 50ms
- K1 LLM generation: 200ms
- K1 route to user: 10ms
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total: 330ms P95 ✅ (Target: <500ms)
```

---

### Integration Summary

**System 42 integrates with:**

**K0 Kernel:**
- **K0 P05 (Prospective/Triggers):** Owns trigger storage, evaluation, scheduling, event emission
- **K0 SSE Port:** Real-time event delivery to K1 subscribers
- **K0 Command Port:** K1 → K0 trigger registration/updates
- **K0 P01 (Recall):** Historical pattern detection for trigger creation (pattern strength calculation)
- **K0 Bus:** In-kernel event fan-out to SSE Port

**K1 Intelligence:**
- **SessionState (ADR-0017):** New `proactive` section for active_suggestions, feedback_history, user_preferences
  - ⚠️ **Triggers NOT in SessionState** - stored in K0 P05 SQLite (kernel owns scheduling)
- **Tool Execution (ADR-0001e):** Proactive tool usage via MCP/WASM/Process sandboxes (P21-P30)
- **Confirmation Protocol (ADR-0052):** Map confidence to approval levels (LOW/MEDIUM/HIGH/CRITICAL)
- **Three-Tier Hierarchy:** ConciergeAgent routes suggestions, ProactiveAgent subscribes to K0, Specialists execute actions
- **Tiered Chat History (System 40):** Context for pattern understanding
- **Emotional Intelligence (System 37-39):** User receptivity, attention-sensitive alerting

**New ADRs Required:** 2 CRITICAL
- ADR-XXXX: Proactive Behavior Core Architecture (K0 P05 extensions, K1 ProactiveAgent, SSE subscription, confidence scoring)
- ADR-XXXX: Proactive Feedback Loop & Learning (K0 ↔ K1 feedback flow, trigger updates via Command Port, adaptive thresholds)

**⚠️ CRITICAL ARCHITECTURAL CONSTRAINT:**
- **K0 owns scheduling, triggers, events** - K1 CANNOT independently generate ticks or schedule actions
- **SSE Port is the ONLY interface** for K0 → K1 real-time events
- **Command Port is the ONLY interface** for K1 → K0 writes (trigger registration/updates)
- **No drift from K0 architecture** - All proactive timing must flow through K0 P05 pipeline

---

## 📊 Complete System Count (Updated)

**Core Infrastructure:** 8 systems (cancellation, queuing, timeouts, etc.)
**Intelligence Layer:** 6 systems (meta-intent, ambiguity, referents, etc.)
**Resilience Layer:** 5 systems (saga, crash recovery, API retry, etc.)
**Safety & Privacy:** 4 systems (emergency stop, redaction, guardrails, etc.)
**SessionState Extensions:** 3 systems (workflow, interruption, conflict tracking)
**Observability:** 3 systems (timeline, intent history, failure analysis)
**Conversational Intelligence:** 6 systems (slot filling, pre-fill, validation, etc.)
**Emotional Intelligence:** 4 systems (AgentContext, EI Layer, context propagation, affect tracking)
**History Management:** 1 system (tiered history with progressive summarization)
**Tool Integration:** 1 system (gaps analysis, 45% coverage)
**Proactive Behavior:** 1 system (K0 P05 triggers + K1 ProactiveAgent, SSE-driven)

**Total: 42 Systems for Production-Ready Human-Like AI**

---
