---
adr_number: 0084
title: K0 Memory Consolidation Pipeline (P03) — Offline Learning & Dream-Like Reflection
status: PROPOSED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer1_input
- layer2_orchestration
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules: []
concerns:
- architecture
- compliance
- cost
- modularity
- observability
- performance
- privacy
- reliability
- scalability
- security
- testing
- ux
supersedes: []
superseded_by: []
related_adrs:
- ADR-0001a
- ADR-0001e
- ADR-0017
- ADR-0032
- ADR-0059
- ADR-0069
- ADR-0084a
- ADR-0084b
- ADR-0084c
- ADR-0084d
implementation_status: COMPLETED
implementation_date: null
implementation_phase: null
related_contracts: []
related_diagrams: []
research_citations: []
propagation:
  triggers:
  - Adding new module to any layer
  - Changing layer dependency rules
  - Modifying system architecture
  - Performance requirement changes
  - Updating API contracts or schemas
  affected_adrs:
  - ADR-0001a
  - ADR-0001e
  - ADR-0017
  - ADR-0032
  - ADR-0059
  - ADR-0069
  - ADR-0084a
  - ADR-0084b
  - ADR-0084c
  - ADR-0084d
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
  affected_tests: []
---


# ADR-0084: K0 Memory Consolidation Pipeline (P03) — Offline Learning & Dream-Like Reflection

**Status:** Proposed 🔄
**Capability:** #26 Dream/Reflection Cycle (Post-MVP v1.1)
**Last Updated:** 2025-01-22

---

## Context & Problem Statement

FamilyOS requires an **intelligent memory consolidation system** that mimics human sleep-cycle memory processing to:

1. **Transform short-term episodic memories into long-term semantic knowledge** (Hippocampus → Cortex pattern)
2. **Optimize memory storage** by identifying frequently accessed memories for prioritization and archiving stale data
3. **Extract insights from daily patterns** to suggest automations and identify user habits
4. **Strengthen emotionally salient memories** while pruning irrelevant details
5. **Enable dream-like exploration** for creative problem-solving and counterfactual thinking
6. **Improve retrieval performance** through offline indexing and schema evolution

**Current State (from Architecture Analysis):**

**K0 Architecture (4-part Mermaid diagrams)** reveals extensive consolidation infrastructure:

- **P03 Consolidation Pipeline (Part 1):** Explicitly listed in 20-pipeline inventory, integrates "P03 WITHIN Consolidation" → MEMORY_SPACES
- **Hippocampus Layer (Part 1/Part 2):**
  - **CA3_CONSOLIDATION** (`ca3/consolidation_coordinator.py`) — Pattern replay & association strengthening
  - **hipp_consolidation** (`hippocampus/consolidation_scheduler.py`) — Consolidation timing & triggers
  - **CA1_BRIDGE** (`ca1/cortical_bridge.py`) — Episodic → Semantic transfer
  - **CA1_THETA** (`ca1/theta_rhythm.py`) — Theta oscillations for encoding/retrieval mode switching
  - **affect_memory_mod** (`affect/memory_modulation.py`) — Emotional memory prioritization
- **Sleep Coordination (Part 4):** SLEEP_SCHEDULER, SLEEP_STATE_MACHINE, SLEEP_TRIGGER with NREM/REM event types
- **5 Consolidation Processes (Part 4):** CONS_HIPPOCAMPAL (replay), CONS_NEOCORTICAL (integration), CONS_SYNAPTIC (pruning), CONS_EPISODIC, CONS_SEMANTIC, CONS_PROCEDURAL, CONS_EMOTIONAL
- **Knowledge Graph Consolidation (Part 4):** KG_TEMPORAL_ENGINE, KG_CAUSAL_GRAPH, KG_CONCEPT_EVOLUTION, KG_RELATION_DISCOVERY
- **Dream-Like Exploration (Part 3):** DREAM_CONSOLIDATION (`k0/p03`), DREAM_EXPLORATION (creative space), DREAM_REHEARSAL (motor skills)
- **Storage:** K0::st_sqlite[episodic, semantic, procedural], K0::st_kg[nodes, edges, temporal], K0::st_vector[embeddings]

**Capability #26 Requirements (from missing_capabilities_for_seamless_ux.md):**

- **Input Signals:** Daily interaction logs, Memory access patterns, Unused/stale data, System idle time, Priority markers
- **Missing Components (per doc):**
  1. Nightly reflection scheduler (detect system idle time 2AM-5AM, trigger consolidation)
  2. Memory access pattern analysis (identify frequently accessed memories for prioritization)
  3. Stale data detection (identify unused memories for archival or deletion)
  4. Episodic-to-semantic conversion (extract patterns from daily interactions, generalize to semantic knowledge)
  5. Priority markers (mark critical memories for preservation)
  6. K1 Learning Loop integration (analyze daily patterns, identify habits, suggest automations)

**Problem:** While extensive infrastructure exists, there is **no comprehensive architectural document** unifying consolidation workflows, sleep-cycle integration, dream-like exploration, and reflection mechanisms. This ADR provides that holistic design.

---

## Decision

Implement **K0 P03 Consolidation Pipeline** as a **sleep-cycle-inspired memory optimization system** with 5 core processes:

### 1. Hippocampal Replay (Pattern Strengthening)
### 2. Neocortical Integration (Episodic → Semantic)
### 3. Synaptic Homeostasis (Forgetting & Pruning)
### 4. Knowledge Graph Consolidation (Entity/Relationship Extraction)
### 5. Dream-Like Exploration (Creative Insight Generation)

---

## Consolidation Architecture

### High-Level Flow

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                          K0 P03 CONSOLIDATION PIPELINE                           │
│                         (Sleep-Cycle Memory Processing)                          │
└──────────────────────────────────────────────────────────────────────────────────┘

TRIGGER SOURCES (Idle Detection):
  ┌─────────────────────────────────────────────────────────────────────┐
  │ SLEEP_SCHEDULER (k0/consolidation/scheduler.py)                     │
  │ • Idle detection: System activity <5% for 15min window              │
  │ • Preferred window: 2AM-5AM (configurable)                          │
  │ • Fallback: Any 3-hour idle period                                  │
  │ • Manual trigger: User-initiated via CLI/API                        │
  │ • Event trigger: After large memory write bursts (>1000 entries)    │
  └─────────────────────────────────────────────────────────────────────┘
            │
            ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │ SLEEP_STATE_MACHINE (k0/consolidation/state_machine.py)             │
  │ • Simulates NREM/REM sleep cycles (90-minute periods)               │
  │ • NREM (Slow-Wave): Episodic → Semantic consolidation               │
  │ • REM (Paradoxical): Creative exploration, insight generation       │
  │ • Theta rhythm coordination via CA1_THETA                           │
  │ • Emit events: infra.consolidation.nrem_start/end                   │
  │                infra.consolidation.rem_start/end                    │
  └─────────────────────────────────────────────────────────────────────┘
            │
            ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │ K0 WAL (evt_wal) → P03 Pipeline Fan-Out                             │
  │ • Batch processing: 1000 events/batch                               │
  │ • Progress tracking: K0 Offsets (evt_offsets)                       │
  │ • Priority: Low (nice +10, pausable, yield to user interactions)    │
  └─────────────────────────────────────────────────────────────────────┘
            │
            ├──────────────┬──────────────┬──────────────┬──────────────┐
            ▼              ▼              ▼              ▼              ▼
┌────────────────┐ ┌────────────────┐ ┌────────────────┐ ┌────────────────┐ ┌────────────────┐
│ HIPPOCAMPAL    │ │ NEOCORTICAL    │ │ SYNAPTIC       │ │ KNOWLEDGE      │ │ DREAM-LIKE     │
│ REPLAY         │ │ INTEGRATION    │ │ HOMEOSTASIS    │ │ GRAPH CONSOL.  │ │ EXPLORATION    │
│ (CA3 Pattern)  │ │ (Epi→Semantic) │ │ (Forgetting)   │ │ (Entity Extr.) │ │ (Insight Gen.) │
└────────────────┘ └────────────────┘ └────────────────┘ └────────────────┘ └────────────────┘
         │                  │                  │                  │                  │
         └──────────────────┴──────────────────┴──────────────────┴──────────────────┘
                                            │
                                            ▼
                              ┌──────────────────────────┐
                              │ CONSOLIDATED STORAGE     │
                              │ • K0::st_sqlite[semantic]│
                              │ • K0::st_kg[nodes,edges] │
                              │ • K0::st_vector[insights]│
                              │ • K0::st_sqlite[skills]  │
                              └──────────────────────────┘
```

---

## 1. Hippocampal Replay (Pattern Strengthening)

**Purpose:** Strengthen memory traces through offline pattern replay (CA3 recurrent network activation).

**Neuroscience Basis:** During slow-wave sleep, hippocampus replays experiences 10-20x faster than real-time (Wilson & McNaughton 1994, Buzsáki 2015). Replayed sequences strengthen synaptic connections.

### Implementation

**Module:** `k0/consolidation/hippocampal_replay.py`

**Components:**

1. **CA3_CONSOLIDATION Coordinator** (`ca3/consolidation_coordinator.py`)
   - Trigger: NREM phase start event
   - Retrieves recent episodic memories (last 24 hours, access_count > 0)
   - Initiates pattern replay sequences
   - Coordinates with CA3_RECURRENT for association strengthening

2. **Pattern Replay Engine**
   ```python
   def replay_pattern(episode: EpisodicMemory, replay_speed: float = 10.0):
       """
       Replay episodic memory sequence at accelerated speed.

       Args:
           episode: Memory to replay (from K0::st_sqlite[episodic_memories])
           replay_speed: Speedup factor (default 10x real-time)

       Process:
       1. Load episode sequence from storage
       2. Activate CA3 recurrent associations (retrieve related memories)
       3. Strengthen connections (increment association weights)
       4. Emit replay events for observability
       """
       # Pseudocode
       sequence = load_episode_sequence(episode.id)
       associations = ca3_completer.retrieve_associations(sequence)

       for memory_node in sequence:
           # Strengthen synaptic weights (Hebbian learning)
           for associated_node in associations[memory_node]:
               increment_association_weight(memory_node, associated_node)

           # Emit replay event
           emit_event(
               topic="infra.consolidation.replay",
               data={"episode_id": episode.id, "node": memory_node, "speed": replay_speed}
           )
   ```

3. **Importance Weighting**
   - **Emotional salience** (via `affect_memory_mod`): Emotional memories receive 2x replay cycles
   - **Access frequency** (via `access_count`): Frequently accessed memories receive priority
   - **Recency** (via `last_accessed_ts`): Recent memories (last 7 days) replayed before older ones
   - **User-marked priority** (via `priority_marker`): Critical flag → 5x replay cycles

4. **Theta Rhythm Coordination**
   - `CA1_THETA` (`ca1/theta_rhythm.py`) modulates replay timing
   - Theta oscillations (4-8 Hz) synchronize encoding/retrieval phases
   - NREM theta: Slower (4-6 Hz) for consolidation
   - REM theta: Faster (6-8 Hz) for creative exploration

**Output:**
- Strengthened association weights in CA3_RECURRENT
- Replay logs in K0::st_sqlite[consolidation_logs]
- Metrics: `consolidation_replay_count`, `consolidation_replay_duration_ms`

---

## 2. Neocortical Integration (Episodic → Semantic)

**Purpose:** Extract generalizable patterns from episodic memories and integrate into semantic knowledge base.

**Neuroscience Basis:** Hippocampal-neocortical dialogue during sleep transfers episodic details to cortical semantic representations (Squire & Alvarez 1995, Stickgold & Walker 2013).

### Implementation

**Module:** `k0/consolidation/neocortical_integration.py`

**Components:**

1. **Episodic → Semantic Transformer**
   - **Input:** Episodic memories from K0::st_sqlite[episodic_memories]
   - **Pattern Extraction:**
     - **Temporal patterns:** "User asks about weather every morning at 7AM" → Semantic fact: "Morning weather check routine"
     - **Location sequences:** "User visits gym after work on Tuesdays/Thursdays" → Semantic: "Gym routine (Tue/Thu post-work)"
     - **Entity generalizations:** "User orders cappuccino at Starbucks 5 times" → Semantic: "Preferred coffee: cappuccino"
   - **Output:** Semantic memory entries in K0::st_sqlite[semantic_memories]

2. **CA1_BRIDGE Integration** (`ca1/cortical_bridge.py`)
   - CA1 acts as bridge between hippocampus (episodic) and cortex (semantic)
   - Formats consolidated memories for semantic storage
   - Ensures context preservation during transfer
   - Coordinates with K0 P02 (Write/Ingest) for semantic writes

3. **Pattern Extraction Algorithm**
   ```python
   def extract_semantic_pattern(episodes: List[EpisodicMemory]) -> SemanticMemory:
       """
       Extract generalizable pattern from clustered episodic memories.

       Args:
           episodes: Cluster of similar episodic memories (grouped by embeddings)

       Returns:
           Generalized semantic memory entry
       """
       # Cluster by semantic similarity (K0::st_vector)
       clusters = cluster_by_embedding_similarity(episodes, threshold=0.85)

       for cluster in clusters:
           # Identify common elements
           common_entities = extract_common_entities(cluster)  # e.g., "Starbucks"
           common_actions = extract_common_actions(cluster)    # e.g., "order coffee"
           temporal_pattern = extract_temporal_pattern(cluster) # e.g., "morning, weekday"

           # Generate semantic abstraction
           semantic_memory = SemanticMemory(
               pattern_type="routine",
               entities=common_entities,
               actions=common_actions,
               temporal_context=temporal_pattern,
               confidence=len(cluster) / total_episodes,  # Frequency-based confidence
               source_episodes=[ep.id for ep in cluster]
           )

           # Store in K0::st_sqlite[semantic_memories]
           store_semantic_memory(semantic_memory)
   ```

4. **Consolidation Criteria**
   - **Frequency threshold:** Pattern must appear ≥3 times in episodic data
   - **Temporal consistency:** Pattern must occur within predictable time windows
   - **Confidence score:** ≥0.70 to qualify for semantic storage
   - **User feedback:** Explicit confirmations increase confidence to 1.0

**Output:**
- Semantic memories in K0::st_sqlite[semantic_memories]
- Consolidated pattern entries with source episode references
- Metrics: `consolidation_episodic_to_semantic_count`, `consolidation_pattern_confidence_avg`

---

## 3. Synaptic Homeostasis (Forgetting & Pruning)

**Purpose:** Optimize memory storage by pruning weak connections and archiving unused data (synaptic downscaling during sleep, Tononi & Cirelli 2014).

**Neuroscience Basis:** Sleep maintains synaptic homeostasis by downscaling weak synapses, preserving storage capacity and preventing interference.

### Implementation

**Module:** `k0/consolidation/synaptic_homeostasis.py`

**Components:**

1. **Stale Data Detector**
   - **Criteria for archival:**
     - `last_accessed_ts` > 90 days (configurable)
     - `access_count` = 0 (never accessed)
     - `priority_marker` = false
     - `emotional_salience` < 0.30 (low emotional weight)
   - **Actions:**
     - Move to archive table: K0::st_sqlite[archived_memories]
     - Update FTS5 index to exclude archived memories
     - Prune vector embeddings for archived entries

2. **Connection Pruning Algorithm**
   ```python
   def prune_weak_associations(threshold_weight: float = 0.10):
       """
       Prune weak associations in CA3_RECURRENT network.

       Args:
           threshold_weight: Associations below this weight are pruned
       """
       # Query all associations from CA3_RECURRENT
       associations = query_ca3_associations()

       for assoc in associations:
           if assoc.weight < threshold_weight:
               # Prune weak connection
               delete_association(assoc.src_id, assoc.dst_id)

               # Log pruning event
               emit_event(
                   topic="infra.consolidation.prune",
                   data={"src": assoc.src_id, "dst": assoc.dst_id, "weight": assoc.weight}
               )
   ```

3. **Forgetting Policy**
   - **Curve:** Ebbinghaus exponential decay
     - `retention_probability = base^(-time_days / half_life)`
     - `base = 0.5`, `half_life = 30 days` (configurable)
   - **Exceptions (never forget):**
     - `priority_marker = true`
     - `emotional_salience >= 0.80`
     - Referenced by semantic memories (via `source_episodes`)
     - Accessed within last 7 days

4. **Storage Optimization**
   - **Compaction:** Merge similar episodic memories (deduplication)
   - **Rollups:** Aggregate daily logs into weekly summaries (via P15 Rollups/Summaries)
   - **Compression:** Apply LZ4 compression to archived memories
   - **Vacuum:** SQLite VACUUM every 30 days to reclaim disk space

**Output:**
- Archived memories in K0::st_sqlite[archived_memories]
- Pruned associations in CA3_RECURRENT
- Metrics: `consolidation_archived_count`, `consolidation_pruned_connections`, `consolidation_storage_freed_mb`

---

## 4. Knowledge Graph Consolidation (Entity/Relationship Extraction)

**Purpose:** Extract entities, relationships, and causal structures from consolidated memories and integrate into K0::st_kg.

### Implementation

**Module:** `k0/consolidation/kg_consolidation.py`

**Components:**

1. **Entity Extraction**
   - **Input:** Consolidated semantic memories
   - **Extraction:**
     - Named entities: People ("Mom", "Sarah"), Places ("Starbucks", "Office"), Organizations ("Amazon")
     - Concepts: "morning routine", "exercise habit", "coffee preference"
     - Temporal markers: "weekday mornings", "Tuesday evenings"
   - **Storage:** K0::st_kg[nodes] with entity types

2. **Relationship Inference**
   - **Causal relationships:** "User orders coffee → Increased productivity" (via KG_CAUSAL_GRAPH)
   - **Temporal relationships:** "Morning shower → Morning coffee → Commute" (sequences)
   - **Associative relationships:** "Starbucks" ↔ "Cappuccino" (co-occurrence)
   - **Storage:** K0::st_kg[edges] with relationship types

3. **Schema Evolution** (via `KG_CONCEPT_EVOLUTION`)
   - **Concept updates:** If new pattern emerges ("User now prefers oat milk"), update concept node
   - **Version control:** K0::st_kg versioning tracks schema changes
   - **Inconsistency resolution:** If conflicting patterns detected, use recency + confidence to resolve

4. **Temporal Reasoning** (via `KG_TEMPORAL_ENGINE`)
   - **Time-aware queries:** "What did user do last Tuesday morning?"
   - **Historical analysis:** Track concept evolution over time
   - **Retention:** Temporal edges persist for 365 days (archival after 1 year)

**Output:**
- Entity nodes in K0::st_kg[nodes]
- Relationship edges in K0::st_kg[edges]
- Temporal snapshots in K0::st_kg[temporal]
- Metrics: `consolidation_kg_entities_extracted`, `consolidation_kg_relationships_inferred`

---

## 5. Dream-Like Exploration (Creative Insight Generation)

**Purpose:** Enable creative problem-solving through REM-like exploration of semantic space and counterfactual thinking.

**Neuroscience Basis:** REM sleep facilitates creative insight through novel associations and memory recombination (Walker & Stickgold 2010, Cai et al. 2009).

### Implementation

**Module:** `k0/consolidation/dream_exploration.py`

**Components:**

1. **Explorative Dreaming** (via `DREAM_EXPLORATION`)
   - **Trigger:** REM phase start event
   - **Process:**
     - Sample random walk through K0::st_vector (semantic embedding space)
     - Generate novel associations by linking distant concepts
     - Identify insight candidates (high novelty + moderate plausibility)
   - **Example:** Connect "morning routine" + "exercise habit" → Insight: "Morning exercise could replace coffee for energy"

2. **Counterfactual Thinking** (via `SIM_COUNTERFACTUAL`)
   - **Generate "what-if" scenarios:** "What if user left for work 15 minutes earlier?"
   - **Replay alternative sequences:** Modify episodic memory timeline
   - **Evaluate outcomes:** Use K0::st_kg causal relationships to predict consequences

3. **Mental Rehearsal** (via `DREAM_REHEARSAL`)
   - **Skill practice:** Replay motor programs from K0::st_sqlite[motor_programs]
   - **Offline learning:** Strengthen procedural memories without physical execution
   - **Integration:** Consolidate practiced skills into K0 P20 (Procedures/Habits)

4. **Reflection Prompt Generation**
   - **Memory gap analysis:** "User mentioned Seattle trip 3 times but no itinerary → Prompt: 'Would you like to plan your Seattle trip?'"
   - **Unresolved threads:** "User asked about restaurant reservation but never booked → Follow up"
   - **Goal progress:** "User set exercise goal 2 weeks ago → Check: 'How's your exercise goal going?'"

**Output:**
- Insight entries in K0::st_vector[insights]
- Reflection prompts in K0::st_sqlite[reflection_prompts]
- Metrics: `consolidation_insights_generated`, `consolidation_reflection_prompts`

---

## Sleep Coordination & State Machine

### Sleep Scheduler (`SLEEP_SCHEDULER`)

**Module:** `k0/consolidation/scheduler.py`

**Idle Detection:**
- **Criteria:**
  - System CPU usage <5% for 15-minute window
  - No active user interactions (keyboard, mouse, touchscreen)
  - No pending K0 Command Port writes (queue size <10)
  - Battery level >30% (avoid draining during low battery)
- **Preferred window:** 2AM-5AM local time
- **Fallback:** Any 3-hour idle period
- **Manual trigger:** CLI command `k0ctl consolidate --force`
- **Event trigger:** After large memory write bursts (>1000 entries in 1 hour)

**Coordination:**
- Emit `infra.consolidation.trigger` event to SLEEP_STATE_MACHINE
- Monitor K0 Offsets (evt_offsets) for progress tracking
- Pause consolidation if user activity detected (resume on next idle window)

### Sleep State Machine (`SLEEP_STATE_MACHINE`)

**Module:** `k0/consolidation/state_machine.py`

**States:**
1. **IDLE:** Awaiting consolidation trigger
2. **NREM_PHASE_1:** Slow-wave sleep (Episodic → Semantic consolidation)
3. **NREM_PHASE_2:** Deep sleep (Synaptic pruning, forgetting)
4. **REM_PHASE:** Paradoxical sleep (Creative exploration, insight generation)
5. **WAKING:** Consolidation complete, return to idle

**State Transitions:**
```
IDLE --(trigger)--> NREM_PHASE_1 --(45 min)--> NREM_PHASE_2 --(30 min)--> REM_PHASE --(15 min)--> WAKING --(complete)--> IDLE
  ^                                                                                                                        |
  └────────────────────────────────────── (user interruption) ────────────────────────────────────────────────────────────┘
```

**Events Emitted:**
- `infra.consolidation.nrem_start` / `infra.consolidation.nrem_end`
- `infra.consolidation.rem_start` / `infra.consolidation.rem_end`
- `infra.consolidation.complete` (includes stats: memories_consolidated, insights_generated, storage_freed_mb)

**Theta Rhythm Coordination:**
- NREM Phase: CA1_THETA 4-6 Hz (slow theta for consolidation)
- REM Phase: CA1_THETA 6-8 Hz (fast theta for exploration)

---

## Job Coordination & Priority

### Consolidation Job Queue

**Module:** `k0/consolidation/job_coordinator.py`

**Priority Levels:**
1. **Critical (P0):** User-marked priority memories (execute immediately)
2. **High (P1):** Emotional memories (emotional_salience ≥ 0.70)
3. **Normal (P2):** Frequently accessed memories (access_count ≥ 5)
4. **Low (P3):** Standard consolidation (all others)
5. **Background (P4):** Archival and pruning

**Job Types:**
- **Replay Jobs:** Hippocampal pattern replay (10-20 sec per job)
- **Transform Jobs:** Episodic → Semantic (30-60 sec per job)
- **Prune Jobs:** Synaptic homeostasis (5-10 sec per job)
- **KG Jobs:** Knowledge graph extraction (15-30 sec per job)
- **Dream Jobs:** Creative exploration (20-40 sec per job)

**Progress Tracking:**
- K0 Offsets (evt_offsets) tracks per-job completion
- Resumable: Interrupted jobs restart from last offset
- Metrics: `consolidation_jobs_completed`, `consolidation_jobs_pending`, `consolidation_avg_job_duration_ms`

### Resource Limits

**CPU:**
- Nice priority: +10 (low priority, yield to user processes)
- CPU affinity: Bind to last 2 cores (avoid interfering with main workload)

**Memory:**
- Max heap: 256 MB
- Batch size: 1000 events per batch (prevents memory spikes)

**Disk I/O:**
- Ionice: Idle class (only write when disk idle)
- Sync strategy: Async writes, fsync every 5 minutes

**Power:**
- Pause if battery <30%
- Reduce frequency if temperature >75°C

---

## Integration with Existing Components

### Hippocampus Integration

**CA3_CONSOLIDATION** (`ca3/consolidation_coordinator.py`):
- **Trigger:** NREM phase start event
- **Coordination:** Orchestrates CA3_RECURRENT for pattern replay
- **Output:** Strengthened associations → CA3_RECURRENT network

**hipp_consolidation** (`hippocampus/consolidation_scheduler.py`):
- **Scheduling:** Coordinates with SLEEP_SCHEDULER
- **Orchestration:** Manages hippocampal consolidation workflow
- **Integration:** D2 Cognitive Core coordination via K0 P03

**CA1_BRIDGE** (`ca1/cortical_bridge.py`):
- **Episodic → Semantic transfer:** Formats memories for semantic storage
- **Context preservation:** Maintains provenance during consolidation
- **Output:** Writes to K0::st_sqlite[semantic_memories] via K0 P02

**CA1_THETA** (`ca1/theta_rhythm.py`):
- **Theta oscillations:** Modulates consolidation timing
- **Encoding/Retrieval modes:** Switches based on NREM/REM phase

**affect_memory_mod** (`affect/memory_modulation.py`):
- **Emotional prioritization:** Emotional memories receive 2x replay cycles
- **Salience weighting:** Affect state influences consolidation priority

### P03 Pipeline Integration

**Event Source:** K0 WAL (evt_wal) → P03 fan-out → Consolidation handlers

**Progress Tracking:** K0 Offsets (evt_offsets) for resumable operations

**Storage:**
- K0::st_sqlite[episodic_memories] → Read source
- K0::st_sqlite[semantic_memories] → Write target
- K0::st_kg[nodes, edges] → Knowledge graph
- K0::st_vector[insights] → Creative insights
- K0::st_sqlite[consolidation_logs] → Audit trails

**Coordination with other pipelines:**
- **P02 (Write/Ingest):** Semantic memory writes via CA1_BRIDGE
- **P08 (Embedding Lifecycle):** Update vector embeddings post-consolidation
- **P13 (Index Rebuild):** Rebuild FTS5 index after archival
- **P15 (Rollups/Summaries):** Aggregate logs into summaries
- **P20 (Procedures/Habits):** Consolidate procedural skills

---

## Performance Budgets

**Consolidation Latency (P95):**
- **Per-job:** <60 seconds
- **Full cycle (NREM + REM):** <90 minutes
- **Replay operation:** <20 seconds
- **Transform operation:** <60 seconds
- **Prune operation:** <10 seconds
- **KG extraction:** <30 seconds
- **Dream exploration:** <40 seconds

**Throughput:**
- **Memories consolidated:** ≥500 memories/hour
- **Patterns extracted:** ≥20 patterns/hour
- **Insights generated:** ≥5 insights/cycle

**Storage Impact:**
- **Archival savings:** ≥30% reduction in active memory footprint
- **Compression ratio:** ≥2:1 for archived memories

**Resource Usage:**
- **CPU:** <10% average (nice +10)
- **Memory:** <256 MB
- **Disk I/O:** <5 MB/s write (ionice idle)

---

## Privacy & Security

**Privacy Bands:**
- **Consolidation respects privacy bands:** RED memories never leave device during consolidation
- **Archive encryption:** Archived memories encrypted at rest (K0 crypto_mls)
- **Audit trails:** All consolidation operations logged in K0::st_sqlite[consolidation_logs]

**User Controls:**
- **Opt-out:** User can disable consolidation via settings
- **Manual trigger:** User can force consolidation via CLI
- **Priority markers:** User can mark critical memories to prevent archival
- **Reflection frequency:** User preference for reflection prompts (off, low, medium, high)

---

## Observability

**Metrics (Prometheus):**
- `consolidation_cycle_duration_seconds` (histogram)
- `consolidation_memories_consolidated_total` (counter)
- `consolidation_patterns_extracted_total` (counter)
- `consolidation_insights_generated_total` (counter)
- `consolidation_storage_freed_bytes` (gauge)
- `consolidation_job_queue_size` (gauge)
- `consolidation_job_duration_seconds` (histogram by job_type)

**Events (K0 SSE Port):**
- `infra.consolidation.trigger` — Consolidation started
- `infra.consolidation.nrem_start` / `infra.consolidation.nrem_end`
- `infra.consolidation.rem_start` / `infra.consolidation.rem_end`
- `infra.consolidation.replay` — Pattern replay event
- `infra.consolidation.transform` — Episodic → Semantic transformation
- `infra.consolidation.prune` — Synaptic pruning event
- `infra.consolidation.insight` — Creative insight generated
- `infra.consolidation.complete` — Consolidation cycle finished

**Traces (OpenTelemetry):**
- `cognitive_trace_id` propagation through all consolidation operations
- Span: `consolidation.cycle` (parent span for full cycle)
  - Child spans: `consolidation.replay`, `consolidation.transform`, `consolidation.prune`, `consolidation.kg_extract`, `consolidation.dream`

---

## Implementation Plan (4-5 weeks)

### Phase 1: Sleep Coordination (Week 1)
- [ ] Implement SLEEP_SCHEDULER idle detection
- [ ] Implement SLEEP_STATE_MACHINE with NREM/REM cycles
- [ ] Integrate with CA1_THETA for theta rhythm coordination
- [ ] Add K0 Offsets progress tracking

### Phase 2: Core Consolidation Processes (Week 2-3)
- [ ] Implement Hippocampal Replay (CA3_CONSOLIDATION integration)
- [ ] Implement Neocortical Integration (Episodic → Semantic transformation)
- [ ] Implement Synaptic Homeostasis (forgetting policy + archival)
- [ ] Integrate with CA1_BRIDGE for semantic writes

### Phase 3: Knowledge Graph & Dream Exploration (Week 3-4)
- [ ] Implement KG Consolidation (entity extraction, relationship inference)
- [ ] Implement Dream Exploration (creative insights, counterfactual thinking)
- [ ] Implement Reflection Prompt Generation

### Phase 4: Integration & Testing (Week 4-5)
- [ ] Integrate all components with P03 pipeline
- [ ] Add resource limits (CPU, memory, disk I/O)
- [ ] Implement observability (metrics, events, traces)
- [ ] Performance testing (consolidation latency, throughput)
- [ ] Privacy/security validation

---

## Consequences

### Positive

✅ **Intelligent memory optimization:** Reduces storage footprint by 30%+ through archival and pruning
✅ **Improved retrieval performance:** Semantic knowledge retrieval faster than episodic search
✅ **Creative insights:** Dream-like exploration generates novel associations and problem-solving suggestions
✅ **User habit detection:** Pattern extraction identifies routines for proactive automation
✅ **Knowledge graph enrichment:** Entity/relationship extraction enhances semantic understanding
✅ **Sleep-cycle realism:** Mimics human memory consolidation for naturalistic intelligence
✅ **Offline learning:** Continues improving without user interaction
✅ **Reflection prompts:** Mindful engagement through memory gap analysis and unresolved thread tracking

### Negative

⚠️ **Complexity:** 5 consolidation processes + sleep state machine adds significant system complexity
⚠️ **Resource consumption:** 90-minute consolidation cycles consume background compute/power
⚠️ **Latency:** Overnight consolidation means user may not see insights until next day
⚠️ **False positives:** Pattern extraction may generate spurious routines (e.g., one-time events misidentified as habits)
⚠️ **Privacy concerns:** Consolidation aggregates data (mitigated by privacy bands + encryption)
⚠️ **Implementation time:** 4-5 weeks full-time development effort

### Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Consolidation deletes critical memories | **High** | Priority markers prevent deletion, user opt-out, audit trails |
| Resource consumption drains battery | **Medium** | Pause if battery <30%, CPU nice +10, ionice idle |
| Pattern extraction generates wrong habits | **Medium** | Confidence thresholds (≥0.70), user feedback integration |
| Consolidation interrupts user workflow | **Low** | Idle detection, pausable operations, low priority |
| Privacy leak via reflection prompts | **Low** | Privacy band enforcement, user control over prompt frequency |

---

## Related ADRs

- **ADR-0001a:** K0 Memory Pipeline (P03 Consolidation trigger mentioned)
- **ADR-0001e:** K0 P15 ConsolidationScheduler (mentioned in capability #26)
- **ADR-0017:** SessionState 6-Section Design (potential consolidation state tracking)
- **ADR-0032:** Privacy Bands (GREEN/AMBER/RED enforcement)
- **ADR-0059:** K1 Learning Loop (pattern recognition for routine automation)
- **ADR-0069:** K0 P08 Affect Modulation (emotional memory prioritization)

**Sub-ADRs (to be created):**
- **ADR-0084a:** Sleep-Cycle Memory Replay Algorithms (Hippocampal replay details)
- **ADR-0084b:** Offline Consolidation Scheduler (Sleep state machine, idle detection)
- **ADR-0084c:** Knowledge Graph Consolidation (Entity extraction, relationship inference)
- **ADR-0084d:** Dream-Like Exploration & Reflection (Creative insights, counterfactual thinking)

---

## References

**Neuroscience:**
- Buzsáki, G. (2015). *Hippocampus*. Annual Review of Neuroscience.
- Wilson, M. A., & McNaughton, B. L. (1994). *Reactivation of hippocampal ensemble memories during sleep*. Science, 265(5172), 676-679.
- Squire, L. R., & Alvarez, P. (1995). *Retrograde amnesia and memory consolidation*. Current Opinion in Neurobiology, 5(2), 169-177.
- Stickgold, R., & Walker, M. P. (2013). *Sleep-dependent memory triage*. Nature Neuroscience, 16(2), 139-145.
- Tononi, G., & Cirelli, C. (2014). *Sleep and the price of plasticity*. Neuron, 81(1), 12-34.
- Walker, M. P., & Stickgold, R. (2010). *Overnight alchemy: Sleep-dependent memory evolution*. Nature Reviews Neuroscience, 11(3), 218-218.
- Cai, D. J., Mednick, S. A., Harrison, E. M., Kanady, J. C., & Mednick, S. C. (2009). *REM, not incubation, improves creativity by priming associative networks*. PNAS, 106(25), 10130-10134.

**Architecture:**
- K0 Architecture Diagrams (Part 1-4): `architecture_diagrams/k0/project_architecture_part*.mmd`
- Capability #26 Requirements: `docs/missing_capabilities_for_seamless_ux.md`

---

**End of ADR-0084**