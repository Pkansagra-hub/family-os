# K0 Pipeline Architecture Reference

## Core Memory & Cognitive Pipelines (P01-P20)

This table documents all K0 pipelines with their signal flows, module dependencies, and what capabilities they provide to K1.

### Signal Flow & Integration Table

| ID  | Pipeline Name                     | Primary Modules (by ownership; infra omitted)                                                                      | Key Signals Generated                                                                                                     | Key Signals Consumed                                                                                                  | What K1 Gets                                                                                                              |
| --- | --------------------------------- | ------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| P01 | Recall / Read                     | `api`, `retrieval`, `hippocampus`, `workspace`, `core`, `cortex`, `storage`, `temporal`                           | `workspace.broadcast.v1`, `core.salience.computed.v1`, `workspace.attention.shifted.v1`                                  | `st_hipp_store`, `st_epi`, `st_sem`, `st_fts`, `st_vec`, hippocampus CA3 sequences/clusters, temporal recency/circadian | Query API for recall, workspace broadcasts (live "thinking" state), full salience with query context                     |
| P02 | Write / Ingest                    | `api`, `perception`, `hippocampus`, `core`, `affect`, `space`, `storage`                                          | `p02.hippocampus.pattern_separated.v1`, `core.affect.analyzed.v1`, `space.resolution.complete.v1`, `workspace.wm.updated.v1`, `p02.write.complete.v1`, `core.enrichment.complete.v1` | `cognitive.memory.write.committed.v1`, `st_wal`, `st_idem_ledger`, `st_hipp_store` (24h novelty window)             | Durability receipts (Ed25519-signed), async enrichment events (affect, hippocampus DG, space), simple salience scores    |
| P03 | Consolidation / Forgetting        | `consolidation`, `hippocampus`, `storage`, `learning`, `ml_capsule`                                               | `p03.hippocampus.sequences_detected.v1`, `p03.hippocampus.clusters_updated.v1`, `p03.consolidation.complete.v1`, CA3 updates to `st_hipp_store` | `p02.write.complete.v1`, `st_hipp_store` (batch reads), timer triggers (nightly 2am)                                 | Episodic threads (sequences), recurring themes (clusters), consolidated memories in `st_epi`/`st_sem`                    |
| P04 | Arbitration / Action              | `arbitration`, `action`, `core`, `workspace`, `cortex`, `affect`, `social_cognition`, `imagination`, `prospective` | `arbitration.decision.v1`, `arbitration.action.recommended.v1`, `workspace.broadcast.v1` (proactive)                     | `workspace.broadcast.v1` (from P01), `core.affect.analyzed.v1`, prospective cues, intelligence advisories            | Action recommendations (advisory only, user approval required), decision reasoning traces, proactive attention management |
| P05 | Prospective / Triggers            | `prospective`, `core`, `workspace`, `storage`, `learning`, `cortex`, `temporal`                                   | `prospective.cue.triggered.v1`, `prospective.intention.formed.v1`, `prospective.retrieval.complete.v1`                  | `workspace.broadcast.v1`, temporal time-based cues, event-based cues, hippocampus sequences                          | Proactive reminders ("you planned to water plants now"), cue-triggered intentions, context retrieval                     |
| P06 | Learning / Neuromodulation        | `learning`, `cortex`, `affect`, `social_cognition`, `ml_capsule`, `storage`                                       | `learning.model.updated.v1`, `learning.feedback.processed.v1`, model weights to `st_ml_artifacts`                       | `core.affect.analyzed.v1`, `arbitration.decision.v1`, workspace broadcasts, prospective outcomes                     | Habit patterns, personalized salience weights, adaptive UX (learned preferences), reward prediction                      |
| P07 | Sync / CRDT                       | `sync`, `storage`, `security`, `supervisor`, `services`                                                           | `infra.sync.delta.available.v1`, `infra.sync.conflict.resolved.v1`, `infra.sync.peer.discovered.v1`, `infra.sync.edge.connected.v1` | Local WAL writes, remote device deltas, vector clocks, MLS group keys                                                | Multi-device sync (P2P WiFi, edge relay, BLE mesh), CRDT conflict resolution, space-scoped sync, offline-first guarantees |
| P08 | Embedding Lifecycle               | `ml_capsule`, `retrieval`, `storage`, `consolidation`, `services`                                                 | `p08.embedding.generated.v1`, `p08.embedding.indexed.v1`, writes to `st_vec`, `st_emb`                                  | `p03.consolidation.complete.v1` (reindex trigger), `st_hipp_store`, `st_epi`, `st_sem`                               | Vector embeddings for semantic recall, FAISS indices, model version tracking                                             |
| P09 | Connector Ingestion               | `perception`, `services`, `sync`, `hippocampus`, `core`, `workspace`, `storage`                                   | External events normalized to K0 format, routed to P02                                                                   | External APIs (Google Calendar, email, photos, etc.), connector configs, OAuth tokens                                 | External data ingestion (calendar events, emails, photos), webhook endpoints, token management                            |
| P10 | PII / Minimization                | `security`, `storage`, `consolidation`, `services`, `workflows`                                                   | `policy.pii.redacted.v1`, `policy.band.enforced.v1`, writes to `st_pii_map`, `st_redaction_log`                         | All write events, policy manifests, PII schema registry                                                              | PII redaction logs, policy band enforcement, GDPR compliance tracking, audit trails                                      |
| P11 | DSAR / GDPR / Rights Handling     | `security`, `storage`, `workflows`, `services`, `api`                                                             | `gdpr.deletion.complete.v1`, `gdpr.dsar.complete.v1`, deletion operations across all storage                            | `gdpr.dsar.requested.v1` (from K1 API), space ownership data, visible_to mappings                                    | GDPR deletion confirmations, data export packages (JSON/CSV), right to erasure audit logs                                |
| P12 | Device / E2EE                     | `security`, `sync`, `services`, `storage`                                                                         | Device provisioning events, MLS group key rotations, E2EE session establishment                                          | Device registration requests, MLS group membership, ratchet states                                                    | Device identity management, E2EE session keys, forward secrecy (key rotation), HSM integration                            |
| P13 | Index Rebuild                     | `retrieval`, `storage`, `consolidation`, `services`, `workflows`                                                  | Index rebuild completion events, FTS/vector index refreshes                                                              | `p03.consolidation.complete.v1`, storage schema migrations, index corruption detection                                | Index health monitoring, rebuild progress, search performance metrics                                                     |
| P14 | Near-Duplicate / Canonicalization | `hippocampus`, `consolidation`, `storage`, `ml_capsule`                                                           | Deduplication events, canonical memory IDs, merge operations                                                             | `p02.hippocampus.pattern_separated.v1` (simhash, novelty), near_duplicates field                                     | Deduplicated memory views, canonical event mappings, storage efficiency metrics                                           |
| P15 | Rollups / Summaries               | `consolidation`, `learning`, `retrieval`, `workspace`, `storage`                                                  | Summary generation events, rollup completion, aggregated stats                                                           | Hippocampus sequences/clusters, temporal windows, consolidation triggers                                              | Daily/weekly/monthly summaries ("Emma's soccer season"), highlight reels, trend analysis                                  |
| P16 | Feature Flags / A-B               | `registry`, `cortex`, `services`, `observability` (as first-class here)                                           | Feature flag changes, A/B variant assignments, experiment results                                                        | User profiles, device capabilities, experiment configs                                                                | A/B test participation, feature rollout status, personalized UX variants                                                  |
| P17 | QoS / Cost Governance             | `cortex`, `services`, `observability`, `registry`, `supervisor`                                                   | `system.backpressure.triggered.v1`, `qos.throttle.applied.v1`, rate limit events                                        | All pipeline metrics (latency, throughput), queue depths, resource utilization                                        | Performance budgets, throttling status, admission control decisions, cost projections                                     |
| P18 | Safety / Abuse                    | `security`, `perception`, `cortex`, `arbitration`, `learning`                                                     | `safety.flag.raised.v1`, `safety.content.quarantined.v1`, writes to `st_flagged_content`                                | All intelligence advisories, action recommendations, affect patterns, social signals                                  | Safety alerts, harmful content flags, abuse detection (never auto-blocks, advisory only)                                  |
| P19 | Personalization / Recommendation  | `learning`, `cortex`, `social_cognition`, `retrieval`, `workspace`, `storage`                                     | `profile.updated.v1`, `personalization.weights.adjusted.v1`, learned preferences                                        | Workspace attention patterns, affect baselines, salience factors, action acceptance rates                             | Personalized salience weights (Dad prefers work, Mom prefers family), emotional baselines, learned preferences             |
| P20 | Procedure / Habits                | `learning`, `workflows`, `arbitration`, `prospective`, `workspace`, `storage`                                     | Habit formation/execution events, routine suggestions, skill acquisition progress                                        | Action outcomes, repetition patterns, reward signals, procedural memory                                               | Habit tracking ("Emma's bedtime routine 8pm"), skill progress, routine recommendations                                    |

| ID  | Pipeline Name                               | What it actually does for a family (high-level job)                                                                                        | Under the hood (uses which K0/K1 bits)                      |
| --- | ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------- |
| P21 | Family Timeline & Storytelling              | Turn raw events into a **shared family timeline**: “what happened this month?”, highlight reels, anniversaries, photo/story bundles.       | P01/P02/P03/P15 + imagination, workspace, social_cognition  |
| P22 | Household Finance & Bills                   | Track **rent, EMI, credit card, subscriptions, due dates**, and nudge people before they’re stressed. Simple projections (“next 90 days”). | P02/P05/P06/P19 on “money” memories; prospective + learning |
| P23 | Health, Sleep & Energy Rhythms              | Notice **patterns in GERD, sleep, steps, meals, meds**, then make gentle adjustments and reminders (not medical, just pattern coach).      | P02/P03/P05/P06, affect, perception (health APIs), learning |
| P24 | Learning & School Support                   | Build a **learning graph** for each person: exams, skills, weak topics, help sessions; generate study plans and spaced reminders.          | P01/P02/P05/P06/P19, prospective, workflows, retrieval      |
| P25 | Home Ops, Chores & Routines                 | Turn ad-hoc “do dishes / trash / laundry” into **fair, rotating routines** with low-friction nudges and dashboards everyone can see.       | P02/P05/P20, workflows, social_cognition, prospective       |
| P26 | Relationships & Emotional Climate           | Track mood trends, conflicts, appreciations; suggest **repair moments, check-ins, gratitude notes** (no psych claims, just patterns).      | P02/P03/P06/P19, affect, social_cognition, learning         |
| P27 | Parenting & Child Development               | Remember **milestones, school issues, interests**, and propose age-appropriate activities, boundaries, and routines (non-clinical).        | P02/P03/P05/P06, social_cognition, prospective, retrieval   |
| P28 | Career, Workload & Focus Balance            | Balance **work tasks, upskilling, rest** across adults; surface overload and suggest rebalancing or saying “no” earlier.                   | P01/P02/P06/P17/P19, learning, cortex (QoS), workflows      |
| P29 | Home Devices, Environment & Digital Hygiene | Coordinate **Wi-Fi, screens, consoles, phones** with time-of-day rules; encourage healthy usage patterns, quiet hours, sleep mode.         | P04/P05/P07/P12/P18, security, sync, action, safety         |
| P30 | Safety, Emergencies & Resilience            | Prepare and react to **emergencies**: ICE contacts, meds, backup info, checklists; fast recall when something bad happens.                 | P01/P02/P04/P11/P18, security, workflows, prospective       |

---

## Multi-Device Sync Architecture (P07 Deep Dive)

### Sync Topology

- **P2P WiFi Mesh**: Direct device-to-device sync on local network (WebRTC/HTTP, <10ms latency)
- **Edge Relay**: Internet sync via untrusted edge server with MLS E2EE (Fly.io/NAS)
- **BLE Mesh**: Bluetooth Low Energy for offline sync (camping trips, no WiFi/cellular)

### Conflict Resolution

- **CRDT (Conflict-free Replicated Data Types)**: Automatic merge without central coordinator
  - `CRDTSet` for tags (add-wins semantics)
  - `CRDTText` for content (OT-like merging)
  - `LWWRegister` for affect (last-write-wins)
  - `Vector Clocks` for causality tracking (per-device wal_pos)
- **Hybrid Logical Clocks (HLC)**: Global event ordering despite clock drift

### Space-Scoped Sync

| Space | Syncs To | Example |
|-------|----------|---------|
| `shared:household` | All family devices | "Emma's soccer game today" |
| `personal:dad` | Only Dad's devices | "Dad's knee surgery notes" |
| `personal:mom` | Only Mom's devices | "Mom's work stress diary" |
| `personal:emma` | Emma's + parent devices | "Emma's homework" (guardian visibility) |

### Encryption

- **MLS (Messaging Layer Security)** group encryption for E2EE sync
- Edge relay is **zero-knowledge** (sees timestamps, not content)
- Forward secrecy with 24-hour key rotation

### Offline-First Guarantees

Every device has **full K0 kernel** (SQLite, WAL, pipelines). Sync opportunistically when connected.

- ✅ **Write memories offline** → Sync later via delta protocol
- ✅ **Query locally** → No network needed for recall
- ✅ **Enrich locally** → Hippocampus DG, affect, space resolution work offline


---

## Key Architecture Principles

### 1. K0 = Brain, K1 = Body

- **K0 (Memory/Cognitive Kernel)**: Thinks, remembers, learns, feels → **never acts autonomously**
- **K1 (Orchestration Layer)**: Presents, executes, coordinates → **never decides autonomously**
- **Safety boundary**: K0 emits `arbitration.action.recommended.v1` → K1 shows to user → user approves → K1 executes

### 2. Offline-First, Privacy-First

- Every device has **full K0 kernel** (no cloud dependency)
- Sync is **opportunistic** (P2P WiFi, edge relay, BLE mesh)
- **Space-scoped visibility** enforced at storage + sync layers
- **MLS E2EE** for all remote sync (zero-knowledge relay)

### 3. Signal-Driven Architecture

- Pipelines communicate via **event bus** (loose coupling)
- Every signal has `trace_id` (observability, debugging)
- **At-least-once delivery** (WAL + transactional outbox + DLQ)
- **CRDT conflict resolution** (eventual consistency without coordinator)

### 4. Memory Backbone as Foundation

- **Hippocampus** (P02 DG + P03 CA3) provides novelty, sequences, clusters
- **Affect** provides emotional context (valence, arousal, bands)
- **Space** provides privacy boundaries (ownership, visibility)
- **Temporal** provides time-aware features (recency, circadian, relative phrases)
- All higher pipelines (P04-P30) **build on** this backbone

---

## What K1 Can Build with This

### 1. Conversational AI Assistant

Uses: P01 (recall with sequences/clusters/affect), P04 (workspace context), P07 (ToM/social insights)

Example: "What did Emma do last week?" → Rich answer with episodic threads, emotional context, family dynamics

### 2. Smart Home Dashboard

Uses: P04 (real-time workspace broadcast), P05 (prospective cues), Affect (mood badges), P07 sync

Example: Today panel shows current focus + affect + upcoming intentions, synced across all devices

### 3. Family Calendar with Context

Uses: P01 (recall), P03 (sequences), P04 (recommendations), Affect, Temporal

Example: Saturday event shows sequence context ("game 12 of 16"), constraints ("Dad's knee"), affect ("Emma excited")

### 4. Proactive Wellness Monitoring

Uses: Affect patterns, P03 clusters, P06 learning, P07 ToM/metacognition

Example: Detects 5 days of Emma stress → suggests teacher catch-up, relaxing weekend, check-in

### 5. Privacy-Aware Multi-User Views

Uses: Space module, P10 policy, band enforcement

Example: Emma sees family activities + her memories, but not Dad's medical records (band=RED)

### 6. Explainable AI

Uses: P04 traces, P07 intelligence, observability events

Example: "Why suggest dentist?" → Shows reasoning chain (6 months since last, pattern detected, aligns with health goals)


---

## References

- **Whiteboard**: `k0/pipelines/whiteboard.md` (Section 3: Event Bus Topic Namespace)
- **Architecture Diagrams**: `architecture_diagrams/k0/*.mmd` (Mermaid flow diagrams)
- **Core/Workspace README**: (Cognitive architecture, salience, working memory, global workspace)
- **Hippocampus Module**: `k0/modules/hippocampus/README.md` (DG/CA3/CA1 architecture)
- **Design Workflow**: `.github/instructions/design-workflow.instructions.md` (5-step module design)
- **Sync Implementation**: `k0/sync/` (CRDT, P2P, edge relay, MLS encryption)
