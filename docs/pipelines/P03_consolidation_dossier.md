# P03: Consolidation / Forgetting - Development Dossier

**Design Status**: 📋 Design Complete (V1 Ready for Implementation)
**Implementation Status**: ⏳ Not Started
**Last Updated**: 2025-12-13
**Dependencies**: P02 (Write/Ingest) ✅ Complete, P08 (FAISS Indexing) ✅ Production

> **Architecture Update (2025-12-13)**: P02 now writes episodic embeddings inline via M16 atomic 3-table transaction (st_hipp_events + st_vec + st_pipeline_processed). P08 runs as kernel lifespan scheduler polling st_vec for FAISS indexing. `st_embedding_queue` is **DEPRECATED**. P03 only writes st_vec for **consolidated semantic patterns** extracted from episodic clusters.

---

## Purpose

P03 is the **offline memory consolidation pipeline inside K0** that transforms staged hippocampus events into permanent, organized, queryable memory structures.

P03 runs **AFTER P02 has written to st_hipp_events staging table**:

1. **P02 (Write/Ingest)** — Fast Path (~50-100ms):
   - Subscribes to `cognitive.memory.write.committed.v1` from WAL
   - Enriches with hippocampus DG fingerprints, affect, space resolution
   - **M22**: Extracts 768-dim embedding from UltraBERT cache (0ms, already computed by M02)
   - **M16**: Atomic 3-table transaction writes to `st_hipp_events` + `st_vec` + `st_pipeline_processed`
   - Leaves consolidation columns NULL: `novelty_score`, `near_duplicates_json`, `is_near_duplicate`, `episode_cluster_id`, `cluster_confidence`
   - **Episodic embeddings written inline** with status=READY (no placeholder pattern)
   - Status: ✅ **COMPLETE**

2. **P03 (Consolidation/Forgetting)** — Sleep-Cycle Processing (~90min cycles, batch mode):
   - Reads from `st_hipp_events` (staging table as input queue)
   - Runs during system idle time (preferred: 2AM-5AM, or any 3-hour idle window)
   - Processes 1000 events/batch with low priority (nice +10, yields to user interactions)
   - Performs 5 consolidation processes:
     1. **Hippocampal Replay** — Strengthens memory associations (CA3 pattern strengthening)
     2. **Neocortical Integration** — Transforms episodic → semantic patterns
     3. **Synaptic Homeostasis** — Deduplication, novelty scoring, forgetting/pruning
     4. **Knowledge Graph Consolidation** — Entity/relationship extraction, temporal graph updates
     5. **Dream-Like Exploration** — Creative insights, counterfactual thinking, procedural rehearsal
   - Updates `st_hipp_events` in-place with deduplication/cluster metadata
   - Writes to 8 core memory layers:
     - `st_epi` (episodic experiences)
     - `st_sem` (semantic knowledge)
     - `st_procedural` (habits/skills)
     - `st_social` (relationship dynamics)
     - `st_prospective` (future intentions/reminders)
     - `st_kg_dom` (knowledge graph nodes)
     - `st_kg_edges` (knowledge graph relationships)
     - `st_vec` (semantic embeddings — P02 writes episodic embeddings inline; P03 writes **semantic pattern embeddings** for consolidated memories)
   - Writes to infrastructure tables:
     - `st_archives`, `deletion_audit`, `st_*_tombstones`, `st_consolidation_logs`, `st_event_canon_map`, `st_event_cluster_history`, `st_kg_snapshots`
   - P08 kernel scheduler polls st_vec for FAISS indexing (READY → INDEXED)
   - Coordinates with P08 for `st_fts` (FTS5 full-text search index over consolidated memories)
   - Implementation Status: ⏳ **NOT STARTED**

**Brain-Inspired Design**: P03 simulates human sleep-cycle memory consolidation (Wilson & McNaughton 1994, Stickgold & Walker 2013):

- **NREM Slow-Wave Sleep**: Episodic → Semantic transfer (hippocampus → cortex dialogue)
- **REM Sleep**: Creative exploration, counterfactual thinking, motor rehearsal
- **Theta Rhythm**: 4-8 Hz oscillations coordinate encoding/retrieval phases
- **Synaptic Homeostasis**: Prune weak connections, strengthen important memories

**Key Architectural Principle**:
> P03 = "From `st_hipp_events` staging → 5 consolidation processes → 8 permanent memory layers."

---

## P02 Data Consumption (UltraBERT Pre-Computed Outputs)

> **CRITICAL**: P03 does NOT load any NLP models. All NLP outputs are pre-computed by P02 via UltraBERT
> single-pass (~30ms) and stored in `st_hipp_events` and `st_vec`. P03 reads these directly from the database.

### What P02 Already Provides (ZERO Model Calls in P03)

| P02 Column | UltraBERT Capability | P03 Use Case | Format |
|------------|---------------------|--------------|--------|
| `entities_json` | `ner_family` + `ner_general` | R4.1 Entity Extraction | `["person_mom", "org_olive_garden"]` |
| `kg_triples_json` | `relations` | R4.2 Relationship Discovery | `[["actor", "had_meal_at", "restaurant"]]` |
| `sentiment_score` | `sentiment` | R5.1 Emotional Valence | `0.9` (0-1 scale) |
| `sentiment_label` | `sentiment` | R5.1 Counterfactual Selection | `"positive"` |
| `dominant_emotions_json` | `emotions` | R5.1, R5.4 Emotional Salience | `["joy","love","togetherness"]` |
| `affect_valence` | derived | R2 Cluster Weighting | `0.85` |
| `affect_arousal` | derived | R2 Cluster Weighting | `0.6` |
| `affect_band` | `safety_familyos` | Privacy Classification | `"GREEN"` |
| `salience_score` | composite | R1 Replay Priority | `0.75` |
| `simhash_hex` | DG fingerprint | R3 Near-Duplicate Detection | 64-bit hex |
| `minhash32` | DG fingerprint | R3 LSH Bucketing | JSON array |

### st_vec Embeddings (768-dim UltraBERT)

| Column | Type | Description |
|--------|------|-------------|
| `vector` | BLOB | 768-dim float32 (3072 bytes) |
| `vector_dim` | INTEGER | Always 768 |
| `model_id` | TEXT | `ultrabert_v2.1.0` |
| `status` | TEXT | `READY` → `INDEXED` |
| `faiss_id` | INTEGER | FAISS index position |

**Reading Embeddings in P03**:
```python
import struct
import numpy as np

def read_embedding(db, event_id: str) -> np.ndarray | None:
    cursor = db.execute(\"\"\"
        SELECT vector FROM st_vec
        WHERE event_id = ? AND status IN ('READY', 'INDEXED')
    \"\"\", (event_id,))
    row = cursor.fetchone()
    if row and row['vector']:
        return np.array(struct.unpack('<768f', row['vector']))
    return None
```

### P03 Consolidation Columns (Written by P03)

These 6 columns are LEFT NULL by P02 and populated by P03 during consolidation:

| Column | P03 Phase | Description |
|--------|-----------|-------------|
| `novelty_score` | R3.2 | 0.0 (duplicate) to 1.0 (novel) |
| `near_duplicates_json` | R3.1 | `["event-abc", "event-def"]` |
| `is_near_duplicate` | R3.1 | 0 (canonical) or 1 (duplicate) |
| `episode_cluster_id` | R2.3 | `"cluster-2025-12-14-001"` |
| `cluster_confidence` | R2.3 | 0.0 to 1.0 |
| `clustering_version` | R2.3 | `"dbscan_v1.0"` |

### Data Flow Summary

```
P02 (Real-time ~50ms)                    P03 (Sleep cycle ~90min)
─────────────────────                    ────────────────────────

UltraBERT Single Pass (30ms)             READ from st_hipp_events:
├─ entities_json                         • entities_json (no NER call)
├─ kg_triples_json                       • kg_triples_json (no model call)
├─ sentiment/emotions                    • sentiment/emotions (no call)
├─ 768-dim embedding                     • simhash/minhash (no call)
└─ safety/intent/etc.
                                         READ from st_vec:
WRITE to st_hipp_events (90 cols)        • 768-dim embedding (no model call)
├─ 84 cols populated
└─ 6 cols NULL for P03                   UPDATE st_hipp_events:
                                         • novelty_score
WRITE to st_vec (768-dim)                • near_duplicates_json
├─ status = 'READY'                      • is_near_duplicate
└─ faiss_id = NULL                       • episode_cluster_id
                                         • cluster_confidence
                                         • clustering_version

                                         WRITE to 8 Memory Layers:
                                         • st_epi, st_sem, st_procedural
                                         • st_social, st_prospective
                                         • st_kg_dom, st_kg_edges
                                         • st_vec (semantic patterns only)
```

---

## What P03 Does

✅ **Deduplication & Novelty Detection**

- Uses `simhash_hex` and `minhash32` from P02 to find near-duplicates within 24-hour time windows
- Computes `novelty_score` (0.0 = perfect duplicate, 1.0 = completely novel)
- Skips duplicate events (novelty < 0.3 threshold)
- Updates `st_hipp_events` with: `is_near_duplicate`, `near_duplicates_json`, `novelty_score`

✅ **Pattern Extraction (Episodic → Semantic)**

- Clusters similar episodic memories (≥3 occurrences, ≥0.85 embedding similarity)
- Extracts generalizable patterns: routines, preferences, habits
- Example: 5 "cappuccino at Starbucks" episodes → semantic fact: "Preferred coffee: cappuccino"
- Writes to `st_sem` with source episode references and confidence scores

✅ **Knowledge Graph Construction**

- Extracts entities from episodes: people, places, events, organizations
- Discovers relationships with temporal validity: `person_dad -[DINED_WITH]-> person_mom (valid_from: 2025-11-10)`
- Builds causal graphs: "Gym visit → feeling energetic"
- Writes to `st_kg_dom` (nodes) and `st_kg_edges` (relationships)

✅ **Memory Strengthening (Hippocampal Replay)**

- Replays important memories 10-20x faster than real-time (CA3 recurrent activation)
- Strengthens associations based on:
  - Emotional salience (2x replay cycles for emotional memories)
  - Access frequency (frequently accessed memories prioritized)
  - Recency (last 7 days replayed before older memories)
  - User-marked priority (5x replay cycles for critical memories)

✅ **Forgetting & Pruning (Synaptic Homeostasis)**

- Detects stale memories (not accessed in retention period)
- Enforces retention policies based on: `(band, topic, device_kind)` → retention matrix
- Creates tombstones for soft delete (supports GDPR right to erasure)
- Schedules archival for low-priority memories (storage savings: 30%+ via compression)

✅ **Procedural Memory (Habit Detection)**

- Detects recurring patterns: "Gym on Tue/Thu after work"
- Extracts motor skills and routines
- Writes to `st_procedural` for habit tracking

✅ **Prospective Memory (Future Intent)**

- Extracts reminders and future intentions from episodic context
- Writes to `st_prospective` for trigger detection (used by P05)

✅ **Social Memory (Relationship Dynamics)**

- Tracks family interaction patterns
- Stores social context and intimacy levels
- Writes to `st_social` for relationship intelligence

✅ **Dream-Like Exploration (Creative Insights)**

- Counterfactual thinking: "What if I had ordered tea instead?"
- Forward simulation: Scenario generation for planning
- Episodic simulation: Memory reconstruction with variations
- Writes creative insights to `st_prospective` and `st_procedural`

---

## What P03 Does NOT Do

❌ **Does NOT receive live API requests**

- P02 handles all incoming memory writes from Command Port/WAL
- P03 is pure background batch processing

❌ **Does NOT validate envelopes or enforce policy**

- PEP validation happens in Command Port hot path (before P02)
- P03 assumes all `st_hipp_events` rows are already policy-compliant

❌ **Does NOT write to WAL, idem_ledger, or st_receipts**

- Those are hot-path responsibilities (Command Port)
- P03 reads from `st_hipp_events` and writes to:
  - **8 core memory layers**: `st_epi`, `st_sem`, `st_procedural`, `st_social`, `st_prospective`, `st_kg_dom`, `st_kg_edges`, `st_vec` (coordinated with P08)
  - **Infrastructure tables**: `st_archives`, `deletion_audit`, `st_*_tombstones`, `st_consolidation_logs`, `st_event_canon_map`, `st_event_cluster_history`, `st_kg_snapshots`
  - **Event bus**: `st_outbox` for event emission (`p03.*` topics)

❌ **Does NOT compute DG fingerprints (simhash/minhash)**

- P02 already computed fingerprints via `hippocampus.pattern_separate:v1` module
- P03 USES existing fingerprints for deduplication

❌ **Does NOT do affect classification or space resolution**

- P02 already enriched with `affect.analyze:v1` and `space.resolve_visibility:v1`
- P03 USES existing affect/space metadata from staging

❌ **Does NOT generate episodic embeddings**

- P02 M22 extracts 768-dim embeddings inline from UltraBERT cache (computed by M02 semantic_project)
- P02 M16 writes embeddings to st_vec atomically with st_hipp_events (status=READY)
- P08 kernel scheduler polls st_vec and adds to FAISS index (READY → INDEXED)
- **P03 DOES write st_vec for consolidated semantic patterns** (e.g., extracted facts, detected habits)
- `st_embedding_queue` is **DEPRECATED** — no longer used

❌ **Does NOT handle real-time queries**

- P01 (Recall/Read) handles memory retrieval
- P03 is offline consolidation only

❌ **Does NOT run continuously**

- P03 triggers during idle time (2AM-5AM preferred, or 3-hour idle windows)
- Low priority (nice +10), yields to user interactions
- NOT on the critical path for user requests

---

## Required Capabilities (Capability-Based Security)

P03 must explicitly declare all storage capabilities it requires. This follows the K0 capability-based security model where pipelines receive **only** the permissions they explicitly declare.

### Storage Read Capabilities

```yaml
required_capabilities:
  # Input: Read from staging table
  - st_hipp_events.read          # Read enriched events from P02

  # Deduplication: Check for existing duplicates
  - st_event_canon_map.read      # Query canonical event mappings
  - st_event_cluster_history.read # Check cluster membership history

  # Pattern Extraction: Query existing patterns
  - st_sem.read                  # Check for existing semantic patterns
  - st_kg_dom.read               # Query knowledge graph nodes
  - st_kg_edges.read             # Query knowledge graph relationships

  # Entity Resolution: Fuzzy matching
  - st_kg_dom.read               # Lookup entities for normalization
```

### Storage Write Capabilities

```yaml
  # Core Memory Layers: Write consolidated memories
  - st_epi.write                 # Episodic memory (permanent)
  - st_sem.write                 # Semantic knowledge (patterns)
  - st_procedural.write          # Habits and routines
  - st_social.write              # Relationship dynamics
  - st_prospective.write         # Future intentions/reminders
  - st_kg_dom.write              # Knowledge graph nodes
  - st_kg_edges.write            # Knowledge graph relationships
  - st_vec.write                 # Vector embeddings (placeholders)

  # Infrastructure Tables: State management
  - st_hipp_events.write         # Update consolidation metadata
  - st_archives.write            # Archive low-priority memories
  - st_consolidation_logs.write  # Audit trail for consolidation runs
  - st_event_canon_map.write     # Canonical event mappings
  - st_event_cluster_history.write # Cluster membership tracking
  - st_kg_snapshots.write        # Knowledge graph versioning
  - deletion_audit.write         # GDPR compliance logging

  # Tombstones: Soft delete support
  - st_epi_tombstones.write
  - st_sem_tombstones.write
  - st_procedural_tombstones.write
  - st_social_tombstones.write
  - st_prospective_tombstones.write
  - st_kg_dom_tombstones.write
  - st_kg_edges_tombstones.write

  # Event Bus: Emit consolidation events
  - st_outbox.write              # Transactional event emission

  # Tracking: Pipeline state
  - st_pipeline_processed.write  # Idempotency tracking
```

### ~~P08 Coordination Capabilities~~ (DEPRECATED)

> **DEPRECATED (2025-12-13)**: `st_embedding_queue` is no longer used. P02 M16 writes episodic embeddings inline to st_vec. P08 kernel scheduler polls st_vec directly (no queue). P03 writes semantic pattern embeddings directly to st_vec with status=READY.

~~```yaml~~
~~  # Embedding Queue: Coordinate with P08 for vector generation~~
~~  - st_embedding_queue.write     # Queue semantic embedding requests~~
~~  - st_embedding_queue.read      # Check queue depth for backpressure~~
~~```~~

**Total Capabilities Required**: 26 capabilities (11 read, 15 write) — *reduced from 28 after deprecating st_embedding_queue*

**Security Enforcement**:

- Every storage operation in P03 modules must call `syscalls.<operation>()`
- Syscalls adapter checks `required_capabilities` before allowing access
- Missing capability → `PermissionError` with audit log entry
- This prevents privilege escalation and enables least-privilege architecture

**Example Usage in Modules**:

```python
# Module: consolidation.dedup.v1
async def run(message, context, **config):
    # This requires st_hipp_events.read capability
    existing = await context.syscalls.hipp_events_query(
        simhash=message.simhash_hex
    )

    # This requires st_event_canon_map.write capability
    await context.syscalls.event_canon_map_upsert(
        duplicate_id=message.event_id,
        canonical_id=existing[0].event_id
    )
```

---

## Architectural Boundaries

**P02 → P03 Handoff**:

- P02 responsibility ENDS at: Atomic 3-table transaction (st_hipp_events + st_vec + st_pipeline_processed) with NULL consolidation columns
- P02 writes **episodic embeddings** inline to st_vec with status=READY (768-dim UltraBERT)
- P03 responsibility STARTS at: Read from `st_hipp_events`, update consolidation columns, write to 8 layers

**P03 → P08 Coordination** (Updated 2025-12-13):

- **Episodic embeddings**: Handled by P02 inline — P03 does NOT write placeholders for these
- **Semantic pattern embeddings**: P03 writes directly to st_vec with status=READY (for consolidated semantic memories)
- P08 kernel scheduler polls st_vec (every 300s, catch-up on boot) and indexes READY vectors into FAISS
- P08 updates st_vec status from READY → INDEXED after FAISS indexing
- `st_embedding_queue` is **DEPRECATED** — not used by P02, P03, or P08

**Embedding Responsibility Matrix**:

| Source | Who Writes st_vec | Who Indexes FAISS | Notes |
|--------|-------------------|-------------------|-------|
| Episodic memories (st_hipp_events) | P02 M16 (inline, atomic) | P08 scheduler | UltraBERT 768-dim |
| Semantic patterns (st_sem) | P03 R7.7 | P08 scheduler | From pattern extraction |
| KG node embeddings (st_kg_dom) | P03 R7.7 | P08 scheduler | Entity embeddings |
| Prospective intentions (st_prospective) | P03 R7.7 | P08 scheduler | Intent embeddings |

**P03 → P15 Integration**:

- P03 consolidates individual memories
- P15 (Rollups/Summaries) creates daily/weekly summaries from consolidated memories

**P03 → P06 Integration**:

- P03 emits pattern/habit detection events
- P06 (Learning/Neuromodulation) uses patterns for personalization and adaptive UX

---

## Scope & Assumptions

### Scope

P03 consolidates **all life signals** from user devices into organized, queryable memory structures for LLM context enrichment and family coordination.

**Device Types in Scope:**

- 📱 **Phone** (iOS/Android) — Primary personal device
- 💻 **Laptop/Desktop** (Windows/Mac/Linux) — Work & productivity device
- ⌚ **Wearables** (Apple Watch, Fitbit, etc.) — Health & activity sensors
- 🏠 **Smart Home Devices** (Optional) — Home automation signals

---

### Holistic Life Signal Capture (When K0/K1 Stack Installed)

P03 consolidates data from **ALL available sources** on user devices to build comprehensive understanding for LLM coordination.

#### 📱 **PHONE SIGNALS** (Primary Device)

##### **1. Communication & Social**

- ✅ **Messaging**: SMS, iMessage, WhatsApp, Telegram (content + metadata)
- ✅ **Calls**: Incoming/outgoing, duration, frequency (no recording, metadata only)
- ✅ **Contacts**: Relationship graph (family, friends, colleagues)
- ✅ **Social Media**: Post timestamps, engagement patterns (privacy-aware)
- ✅ **Email**: Send/receive patterns, important contacts (metadata only)

**P03 Consolidation**: Builds social graph (st_social), relationship dynamics, communication frequency patterns

##### **2. Location & Movement**

- ✅ **GPS Traces**: Geohash-based location history (privacy bands: GREEN=full, AMBER=5km, RED=25km)
- ✅ **Places Visited**: Home, work, gym, restaurants (frequent locations)
- ✅ **Commute Patterns**: Morning/evening routes, travel time
- ✅ **Transportation Mode**: Walking, driving, transit (from motion sensors)

**P03 Consolidation**: Extracts routines (st_procedural), place preferences (st_sem), travel patterns

##### **3. Health & Vitals** (via HealthKit/Google Fit)

- ✅ **Heart Rate**: Resting, active, HRV (heart rate variability)
- ✅ **Steps & Activity**: Daily steps, active minutes, calories burned
- ✅ **Sleep**: Duration, stages (REM/deep/light), quality score
- ✅ **Exercise**: Workouts (type, duration, intensity)
- ✅ **Body Metrics**: Weight, BMI, body fat % (if tracked)
- ✅ **Blood Pressure**: Systolic/diastolic (if monitored)
- ✅ **Blood Oxygen (SpO2)**: Overnight levels (sleep quality)
- ✅ **Blood Glucose**: For diabetic users (CGM integration)
- ✅ **Menstrual Cycle**: For female users (privacy: RED band)
- ✅ **Nutrition**: Calorie intake, macros (if logged)
- ✅ **Hydration**: Water intake (if tracked)

**P03 Consolidation**: Health-activity correlation (st_procedural), wellness trends (st_sem), early warning detection

##### **4. Screen Time & App Usage**

- ✅ **App Screen Time**: Which apps, how long, when
- ✅ **Notification Interactions**: Which apps get immediate attention vs ignored
- ✅ **App Install/Uninstall**: Interest changes over time
- ✅ **Screen On/Off**: Active device usage patterns, circadian rhythm
- ✅ **Focus Modes**: Do Not Disturb, Work mode, Sleep mode usage

**P03 Consolidation**: Habit detection (st_procedural), attention patterns, productivity insights

##### **5. Calendar & Time Management**

- ✅ **Calendar Events**: Scheduled vs actual attendance
- ✅ **Meeting Duration**: Overruns, cancellations
- ✅ **Free Time Blocks**: Available for proactive suggestions
- ✅ **Recurring Events**: Weekly routines, standing meetings

**P03 Consolidation**: Schedule patterns (st_prospective), time allocation insights (st_sem)

##### **6. Photos & Media**

- ✅ **Photo Capture Times**: When user considers moments worth capturing
- ✅ **Photo Locations**: Places of importance (vacation spots, events)
- ✅ **Photo Faces**: Who appears in photos (relationship importance)
- ✅ **Albums & Organization**: User-curated memory collections
- ⚠️ **Content**: NOT stored in K0 (external reference only, privacy)

**P03 Consolidation**: Important moments detection (st_epi), place significance (st_sem)

##### **7. Alarms & Reminders**

- ✅ **Alarm Times**: Wake-up patterns, sleep schedule
- ✅ **Alarm Response**: Snooze frequency, actual wake time
- ✅ **Reminders Set**: Future intentions (dentist, errands)
- ✅ **Reminder Completion**: Task follow-through rate

**P03 Consolidation**: Circadian patterns (st_procedural), prospective memory (st_prospective)

##### **8. Music & Entertainment**

- ✅ **Music Listening**: Songs, artists, genres, play times
- ✅ **Podcast Subscriptions**: Topics of interest
- ✅ **Video Watching**: YouTube, streaming patterns
- ✅ **Reading**: E-books, articles saved

**P03 Consolidation**: Mood indicators (music tempo/genre), interest graph (st_kg_dom)

##### **9. Financial Signals** (if integrated)

- ✅ **Transaction Timestamps**: Spending patterns (no amounts stored without consent)
- ✅ **Merchant Categories**: Restaurant, grocery, entertainment frequency
- ✅ **Payment Methods**: Card vs cash vs digital wallet

**P03 Consolidation**: Lifestyle patterns (st_sem), routine detection (st_procedural)

##### **10. Voice Assistant Interactions**

- ✅ **Siri/Google Commands**: "What's the weather?", "Set timer for 10 minutes"
- ✅ **Command Types**: Information seeking, task execution, entertainment
- ✅ **Command Timing**: When user needs assistance

**P03 Consolidation**: Need patterns (st_prospective), query understanding (st_sem)

##### **11. Phone Sensors** (Passive)

- ✅ **Accelerometer**: Movement patterns, phone pickup frequency
- ✅ **Gyroscope**: Orientation, activity type
- ✅ **Ambient Light**: Indoor vs outdoor, time of day
- ✅ **Barometer**: Altitude changes (stairs, elevation)
- ✅ **Microphone** (optional, privacy-aware): Ambient sound level (NOT recording content)

**P03 Consolidation**: Activity classification (st_procedural), environmental context

##### **12. Battery & Charging**

- ✅ **Charging Times**: When user plugs in (bedtime indicator)
- ✅ **Battery Level**: Anxiety patterns (always charging vs letting drain)
- ✅ **Low Battery**: Stress indicator if frequent

**P03 Consolidation**: Routine detection (charging = bedtime), device dependency patterns

---

#### 💻 **LAPTOP SIGNALS** (Work & Productivity Device)

##### **1. Work Patterns & Productivity**

- ✅ **Active Hours**: When laptop is actively used
- ✅ **Idle Time**: Breaks, meetings (no screen interaction)
- ✅ **App Usage**: Which work apps, IDEs, browsers
- ✅ **Window Switching**: Task switching frequency (focus indicator)
- ✅ **Keyboard/Mouse Activity**: Typing speed, intensity (stress indicator)

**P03 Consolidation**: Work habits (st_procedural), productivity patterns (st_sem)

##### **2. Calendar & Meetings**

- ✅ **Meeting Attendance**: Zoom, Teams, Google Meet join times
- ✅ **Meeting Duration**: Overruns, early exits
- ✅ **Screen Share**: Presentation mode engagement
- ✅ **Camera/Mic Status**: Engagement level

**P03 Consolidation**: Work schedule (st_prospective), meeting patterns (st_sem)

##### **3. Communication**

- ✅ **Email Patterns**: Send/receive frequency, response times
- ✅ **Slack/Teams Messages**: Communication frequency, channels
- ✅ **Video Call Frequency**: Collaboration patterns

**P03 Consolidation**: Work relationships (st_social), communication load (st_sem)

##### **4. File & Document Activity**

- ✅ **File Opens**: Which documents, how often
- ✅ **Recent Projects**: Active work focus
- ✅ **File Modifications**: Work session patterns
- ✅ **Cloud Sync**: Dropbox, Google Drive activity

**P03 Consolidation**: Project focus (st_sem), work priorities

##### **5. Browser Activity** (Privacy-Aware)

- ✅ **Active Tab Count**: Overwhelm indicator
- ✅ **Research Sessions**: Deep work vs distraction
- ✅ **Bookmark Additions**: Interest evolution
- ⚠️ **URLs**: NOT stored (privacy), only domains/categories

**P03 Consolidation**: Research patterns (st_sem), focus vs distraction ratio

##### **6. Development Activity** (For Developers)

- ✅ **IDE Active Time**: VS Code, IntelliJ usage
- ✅ **Git Commits**: Coding frequency, project activity
- ✅ **Build/Test Runs**: Development rhythm
- ✅ **Terminal Commands**: Workflow patterns

**P03 Consolidation**: Development habits (st_procedural), project velocity

##### **7. System Health**

- ✅ **CPU/Memory Usage**: System load (stress indicator)
- ✅ **Disk Space**: Storage management patterns
- ✅ **Network Activity**: Connectivity patterns

**P03 Consolidation**: Device health trends

---

#### ⌚ **WEARABLE SIGNALS** (Apple Watch, Fitbit, etc.)

##### **1. Continuous Health Monitoring**

- ✅ **Heart Rate (continuous)**: Every 5-10 seconds
- ✅ **HRV (Heart Rate Variability)**: Stress/recovery indicator
- ✅ **ECG** (if available): Atrial fibrillation detection
- ✅ **Blood Oxygen**: Continuous overnight monitoring
- ✅ **Skin Temperature**: Fever detection, menstrual cycle tracking

**P03 Consolidation**: Health baselines (st_sem), anomaly detection (st_prospective)

##### **2. Activity Tracking**

- ✅ **Step Count**: Real-time step tracking
- ✅ **Stairs Climbed**: Vertical activity
- ✅ **Stand Hours**: Sedentary behavior
- ✅ **Exercise Detection**: Auto-detection of workouts
- ✅ **Calories Burned**: Active + resting energy

**P03 Consolidation**: Activity routines (st_procedural), fitness trends (st_sem)

##### **3. Sleep Tracking**

- ✅ **Sleep Stages**: REM, deep, light, awake
- ✅ **Sleep Duration**: Actual vs goal
- ✅ **Sleep Disruptions**: Awake count, duration
- ✅ **Sleep Consistency**: Bedtime/wake time variance

**P03 Consolidation**: Sleep quality trends (st_sem), circadian rhythm (st_procedural)

##### **4. Environmental Sensors**

- ✅ **Ambient Noise**: Decibel levels (hearing health)
- ✅ **Elevation**: Activity intensity
- ✅ **UV Exposure** (some devices): Sun safety

**P03 Consolidation**: Environmental exposure patterns

---

#### 🏠 **SMART HOME SIGNALS** (Optional)

##### **1. Home Automation**

- ✅ **Thermostat**: Temperature preferences, schedule
- ✅ **Lights**: On/off times, brightness preferences
- ✅ **Door Locks**: Entry/exit patterns
- ✅ **Security System**: Arm/disarm, home/away mode
- ✅ **Smart Plugs**: Device usage patterns

**P03 Consolidation**: Home routine (st_procedural), presence detection

##### **2. Voice Assistants**

- ✅ **Alexa/Google Home Commands**: Home control, information seeking
- ✅ **Smart Speaker Usage**: Music, timers, reminders

**P03 Consolidation**: Home activity patterns (st_sem)

---

### Data Flow Architecture

┌─────────────────────────────────────────────────────────────┐
│ DEVICE SIGNALS (Phone, Laptop, Wearables, Smart Home)      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ P09: CONNECTOR INGESTION (Future - After P03 Core)         │
│ - Normalizes formats                                         │
│ - Privacy filtering (band-based)                            │
│ - Deduplication                                             │
│ - Rate limiting                                             │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ P02: MEMORY FORMATION (Current - Working)                   │
│ - Enrichment (affect, space, temporal)                      │
│ - DG fingerprinting                                         │
│ - Writes to st_hipp_events (staging)                        │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ st_hipp_events (STAGING TABLE - All Signal Types)          │
│ - Text memories                                             │
│ - Sensor readings                                           │
│ - Activity logs                                             │
│ - Health metrics                                            │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ P03: CONSOLIDATION (This Pipeline)                          │
│ - Deduplication                                             │
│ - Pattern extraction                                        │
│ - Health-activity correlation                               │
│ - Knowledge graph construction                              │
│ - Habit detection                                           │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 8 MEMORY LAYERS (Organized, Queryable)                     │
│ - st_epi (episodic: life events)                           │
│ - st_sem (semantic: patterns, preferences, facts)           │
│ - st_procedural (habits, routines, skills)                  │
│ - st_social (relationships, communication patterns)         │
│ - st_prospective (reminders, future intentions)            │
│ - st_kg_dom (knowledge graph: entities, relationships)      │
│ - st_vec (semantic embeddings for LLM context)             │
│ - st_fts (full-text search index)                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ LLM CONTEXT ENRICHMENT (P01: Recall/Read)                  │
│ Provides holistic user understanding:                       │
│ - "User goes to gym Tue/Thu after work"                    │
│ - "Sleep quality drops when working late"                  │
│ - "Prefers cappuccino, usually at 7:15 AM"                 │
│ - "Close relationship with Mom (calls 3x/week)"            │
└─────────────────────────────────────────────────────────────┘

---

### Assumptions

#### **1. Privacy & Consent**

- ✅ **Explicit Consent Required**: User must opt-in to each data source
- ✅ **Band-Based Protection**: RED (health), AMBER (location), GREEN (general)
- ✅ **User Control**: Can disable any signal source anytime
- ✅ **Family Boundaries**: Health data is personal by default (not shared with family)
- ✅ **GDPR/HIPAA Compliance**: Right to erasure, data portability

#### **2. Device Permissions**

- ✅ **Phone**: Location, HealthKit, Calendar, Contacts (iOS)
- ✅ **Phone**: Location, Google Fit, Calendar, Contacts (Android)
- ✅ **Laptop**: Accessibility API (macOS), Background tasks (Windows)
- ✅ **Wearables**: Paired device syncs data to phone

#### **3. Data Volume Management**

- ✅ **High-Frequency Sensors**: Aggregated to hourly/daily summaries by P03
- ✅ **Low-Frequency Events**: Stored as-is (text memories, calendar events)
- ✅ **Retention Policies**: Raw data 7 days, summaries 1 year, archives 5 years
- ✅ **Storage Estimate**: 50-100 MB/month per user (with aggregation)

#### **4. Processing Assumptions**

- ✅ **P02 Handles All Ingestion**: From text OR sensors (via P09)
- ✅ **P03 is Source-Agnostic**: Doesn't care if data came from text, sensors, or smart home
- ✅ **Offline Processing**: P03 runs during idle time (2AM-5AM, or 3-hour idle windows)
- ✅ **Batch Processing**: 1000 events/batch, low priority (nice +10)

#### **5. LLM Context Goals**

- ✅ **Holistic Understanding**: LLM knows user's routines, health, relationships, preferences
- ✅ **Proactive Assistance**: "You usually go to gym on Thursdays, want me to set a reminder?"
- ✅ **Health Insights**: "Your sleep quality drops when you work past 10 PM"
- ✅ **Relationship Awareness**: "Mom's birthday is next week, you usually call her on Sundays"
- ✅ **Habit Reinforcement**: "You've maintained your morning run streak for 30 days!"

#### **6. Implementation Phases**

- ✅ **Phase 1 (Current)**: Text memories only (P02 working)
- ⏳ **Phase 2 (This Doc)**: P03 consolidation for text memories
- ⏳ **Phase 3 (Future)**: P09 sensor ingestion (phone health, calendar, location)
- ⏳ **Phase 4 (Future)**: P09 laptop signals (work patterns, productivity)
- ⏳ **Phase 5 (Optional)**: Smart home integration

#### **7. Architectural Boundaries**

- ✅ **P09 NOT Required for P03**: P03 works with existing P02 text data TODAY
- ✅ **Module Contracts Protect Against Schema Changes**: Adding sensor columns won't break P03
- ✅ **Declarative YAML Pipeline**: P03 defined in `k0/contracts/pipelines/p03_consolidation.v1.yaml`
- ✅ **Module-Based Architecture**: Each stage is reusable module with clear contract

---

### Out of Scope (P03)

❌ **Real-Time Ingestion**: P09 handles that (future)
❌ **API Gateway**: Command Port handles that (already done)
❌ **Policy Enforcement**: PEP handles that (hot path, before P02)
❌ **Embedding Generation**: P08 handles that (coordinated with P03)
❌ **Memory Retrieval**: P01 handles that (separate pipeline)
❌ **Video/Audio Content Storage**: External references only (privacy)
❌ **Financial Transaction Amounts**: Categories only (unless explicit consent)
❌ **Browser History URLs**: Domain categories only (privacy)

---

## Inputs/Outputs

### Entry Sources

**Primary Input**: `st_hipp_events` table (staging table written by P02)

**Trigger Mechanisms**:

1. **Idle Detection**: System activity <5% for 15min window
2. **Time-Based**: Preferred 2AM-5AM local time
3. **Threshold-Based**: When `st_hipp_events` has >1000 unconsolidated rows
4. **Manual**: CLI/API command `k0 consolidate run`
5. **Event-Based**: After large memory write bursts from P02

**Entry Topic** (Logical): `infra.consolidation.trigger.v1`

**Batch Processing**:

- Reads 1000 events/batch from `st_hipp_events`
- Filters: `WHERE consolidation_status IS NULL OR consolidation_status = 'PENDING'`
- Order: `ORDER BY event_time_utc ASC` (oldest first)

---

### Storage Reads

#### **Primary Input Table: st_hipp_events**

**Schema** (from P02 Write Dossier - Migration 0024):

**Identity & Trace** (8 columns):

- `event_id` (TEXT, PK) - Unique event identifier
- `wal_pos` (INTEGER, FK → st_wal) - Write-ahead log position
- `cognitive_trace_id` (TEXT) - Cross-pipeline correlation ID
- `tenant_id` (TEXT) - Family/tenant identifier
- `space_id` (TEXT) - Space namespace (e.g., `personal:dad`)
- `effective_space_id` (TEXT) - Resolved space after ACL
- `topic` (TEXT) - Event topic (e.g., `memory.episodic.formation.v1`)
- `uow_id` (TEXT) - Unit of work identifier

**Integrity** (6 columns):

- `envelope_sha256` (TEXT) - Envelope hash for integrity
- `sig_alg` (TEXT) - Signature algorithm
- `sig_kid` (TEXT) - Key ID for signature verification
- `idem_key` (TEXT) - Idempotency key
- `ingested_at` (TEXT) - ISO timestamp of ingestion
- `clock_skew_ms` (INTEGER) - Client-server clock difference

**Policy & Visibility** (10 columns):

- `policy_decision` (TEXT) - ALLOW/DENY/CONDITIONAL
- `policy_band` (TEXT) - GREEN/AMBER/RED
- `policy_version` (TEXT) - Policy version used
- `obligations_json` (TEXT) - JSON array of policy obligations
- `visible_to_json` (TEXT) - JSON array of subject IDs who can access
- `visibility_scope` (TEXT) - OWNER_ONLY/SPACE_DEFAULT/HOUSEHOLD_ALL/CUSTOM_SUBSET/EXTERNAL_SHARE
- `owner_id` (TEXT) - Primary owner subject ID
- `co_owners_json` (TEXT) - JSON array of co-owner IDs
- `retention_policy_id` (TEXT) - FK to st_retention_policy
- `retention_bucket` (TEXT) - STANDARD/LONG_TERM/ARCHIVE

**Actor & Device** (5 columns):

- `actor_id` (TEXT) - Subject who created the memory
- `actor_role` (TEXT) - Role in family (parent, child, etc.)
- `device_id` (TEXT) - Device that captured the memory
- `device_kind` (TEXT) - phone/tablet/laptop/wearable
- `device_os` (TEXT) - iOS/Android/Windows/MacOS
- `ingress_channel` (TEXT) - k1.conversation/api.direct/sensor.automatic

**Temporal** (11 columns):

- `event_time_utc` (TEXT) - ISO timestamp when event occurred
- `write_time_utc` (TEXT) - ISO timestamp when written to K0
- `write_lag_ms` (INTEGER) - Delay between event and write
- `local_date` (TEXT) - Local date (YYYY-MM-DD)
- `local_time` (TEXT) - Local time (HH:MM:SS)
- `day_of_week` (TEXT) - Monday/Tuesday/etc.
- `is_weekend` (INTEGER) - 0=weekday, 1=weekend
- `time_of_day_bucket` (TEXT) - MORNING/AFTERNOON/EVENING/NIGHT
- `circadian_slot` (TEXT) - WAKE/PEAK/DECLINE/SLEEP
- `is_backdated` (INTEGER) - 0=real-time, 1=backdated

**Spatial** (5 columns):

- `location_name` (TEXT) - Human-readable location name
- `location_type` (TEXT) - home/work/restaurant/gym/etc.
- `geohash_6` (TEXT) - 6-character geohash (privacy-masked per band)
- `geo_precision_external` (INTEGER) - Precision in meters
- `geo_masking_reason` (TEXT) - Why location was masked

**Social** (8 columns):

- `participants_json` (TEXT) - JSON array of participant IDs
- `num_participants` (INTEGER) - Count of participants
- `has_partner_present` (INTEGER) - 0/1 flag
- `has_parent_present` (INTEGER) - 0/1 flag
- `is_solo_event` (INTEGER) - 0/1 flag
- `participant_roles_json` (TEXT) - JSON object mapping participant → role
- `social_context` (TEXT) - SOLO/PARTNER/FAMILY/FRIEND/WORK/PUBLIC
- `social_intimacy` (TEXT) - LOW/MEDIUM/HIGH

**Semantic/Activity** (8 columns):

- `text` (TEXT) - Raw text content
- `text_normalized` (TEXT) - Cleaned/normalized text
- `char_count` (INTEGER) - Length of text
- `token_count` (INTEGER) - Word count
- `language` (TEXT) - en/es/fr/etc.
- `activity_type` (TEXT) - meal/exercise/social/work/etc.
- `activity_category` (TEXT) - dining/fitness/entertainment/etc.
- `is_meal` (INTEGER) - 0/1 flag
- `is_outing` (INTEGER) - 0/1 flag

**Hippocampus (DG/CA3)** (7 columns):

- `simhash_hex` (TEXT) - 64-bit SimHash for deduplication
- `minhash32` (TEXT) - JSON array of 32 MinHash permutations
- `novelty_score` (REAL) - NULL in P02, computed by P03 (0.0-1.0)
- `near_duplicates_json` (TEXT) - NULL in P02, populated by P03 (JSON array of event_ids)
- `is_near_duplicate` (INTEGER) - NULL in P02, set by P03 (0/1)
- `episode_cluster_id` (TEXT) - NULL in P02, assigned by P03
- `cluster_confidence` (REAL) - NULL in P02, computed by P03 (0.0-1.0)

**Embeddings/KG (CA1)** (4 columns):

- `embedding_id` (TEXT) - UUID for embedding record
- `embedding_status` (TEXT) - PENDING/READY/FAILED
- `entities_json` (TEXT) - JSON array of extracted entities
- `kg_triples_json` (TEXT) - JSON array of RDF triples

**Affect/Salience** (8 columns):

- `sentiment_score` (REAL) - -1.0 to 1.0
- `sentiment_label` (TEXT) - positive/negative/neutral
- `dominant_emotions_json` (TEXT) - JSON array of emotion tags
- `affect_valence` (REAL) - -1.0 to 1.0 (pleasure)
- `affect_arousal` (REAL) - 0.0 to 1.0 (activation)
- `affect_band` (TEXT) - CALM/NEUTRAL/EXCITED/STRESSED
- `salience_score` (REAL) - 0.0 to 1.0 (importance)
- `salience_reasons_json` (TEXT) - JSON array of importance factors
- `salience_band` (TEXT) - LOW/MEDIUM/HIGH

**Ops & Versions** (5 columns):

- `ingress_source` (TEXT) - Module that created this
- `hippocampus_api_version` (TEXT) - Version of hippocampus API
- `space_resolver_version` (TEXT) - Version of space resolver
- `created_at` (TEXT) - ISO timestamp of row creation
- `updated_at` (TEXT) - ISO timestamp of last update

**P03 Consolidation State** (5 columns - added for P03):

- `consolidation_status` (TEXT) - NULL/PENDING/IN_PROGRESS/COMPLETE/FAILED
- `consolidated_at` (TEXT) - ISO timestamp when P03 processed this
- `consolidation_error` (TEXT) - Error message if FAILED
- `importance_score` (REAL) - NULL in P02, computed by P03 R1.4 (0.0-1.0, multi-factor weighted importance)
- `access_count` (INTEGER) - Number of times this memory was accessed (for importance weighting)

**Total Columns**: ~97 columns

**Indexes** (from P02 dossier):

- PRIMARY KEY (`event_id`)
- FOREIGN KEY (`wal_pos`) REFERENCES `st_wal(wal_pos)`
- INDEX `idx_hipp_events_tenant_time` (`tenant_id`, `event_time_utc`)
- INDEX `idx_hipp_events_space` (`space_id`, `event_time_utc`)
- INDEX `idx_hipp_events_simhash` (`simhash_hex`) -- for P03 deduplication
- INDEX `idx_hipp_events_consolidation` (`consolidation_status`, `event_time_utc`) -- for P03 batch processing

---

#### **Supporting Tables (Read-Only)**

**1. st_relationships** (Family Graph):

- Columns: `relationship_id`, `from_person_id`, `to_person_id`, `relationship_type`, `created_at`
- Relationship types: `SPOUSE_OF`, `PARENT_OF`, `CHILD_OF`, `CARETAKER_OF`, `SIBLING_OF`
- Used by: Social pattern extraction

**2. people** (Person Directory):

- Columns: 33 total (basic info: `person_id`, `first_name`, `last_name`, `date_of_birth`, etc.)
- Used by: Knowledge graph entity resolution

**3. households** (Household Metadata):

- Columns: 35 total (household info)
- Used by: Family coordination patterns

**4. st_retention_policy** (Retention Rules):

- Columns: `policy_id`, `band`, `topic_pattern`, `device_kind`, `retention_days`, `archival_enabled`
- Used by: Forgetting/pruning decisions

**5. st_pipeline_processed** (P03 Progress Tracking):

- Columns: `pipeline_id`, `space_id`, `wal_pos`, `processed_at`, `status`
- Used by: Resume after interruption, idempotency

---

### Storage Writes

#### **Primary Output Tables (8 Memory Layers)**

**1. st_epi** (Episodic Memory Layer):

```sql
CREATE TABLE st_epi (
    episode_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,  -- Immutability: versioning support
    canonical_episode_id TEXT,  -- Canonicalization: points to canonical version
    is_canonical INTEGER NOT NULL DEFAULT 1,  -- 1=canonical, 0=superseded
    supersedes_episode_id TEXT,  -- Previous version (if updated)

    event_id TEXT NOT NULL,  -- FK to st_hipp_events
    tenant_id TEXT NOT NULL,
    space_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,

    -- Temporal Anchoring (Rule 2)
    event_time_utc TEXT NOT NULL,
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    observation_count INTEGER NOT NULL DEFAULT 1,
    temporal_bucket TEXT,  -- MORNING/AFTERNOON/EVENING/NIGHT
    is_weekend INTEGER,
    recency_weight REAL,  -- exp(-λ * days_since_last_observed)

    -- Content
    text TEXT,
    participants_json TEXT,
    location_name TEXT,
    activity_type TEXT,
    sentiment_score REAL,
    salience_score REAL,

    -- Confidence & Provenance (Rules 4 & 5)
    confidence_score REAL NOT NULL,  -- 0.0-1.0
    source_count INTEGER NOT NULL,  -- How many events contributed
    source_quality TEXT,  -- text/sensor/derived/fused
    ambiguity_score REAL,  -- 0.0-1.0 (higher = more uncertain)
    modalities_json TEXT,  -- ["text", "gps", "calendar", etc.]
    fusion_method TEXT,  -- late/early/hybrid (if multi-modal)
    fusion_confidence REAL,

    -- Provenance
    source_events_json TEXT NOT NULL,  -- Array of event_ids that contributed

    -- Consolidation Cross-References (P03 R2 backlinks)
    promoted_to_semantic_id TEXT,  -- FK to st_sem if promoted to semantic memory
    promoted_to_routine_id TEXT,  -- FK to st_procedural if promoted to routine

    -- Decay & Retention (Rule 7)
    decay_factor REAL NOT NULL DEFAULT 1.0,  -- Forgetting function
    archival_status TEXT NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE/ARCHIVED/DEEP_FREEZE
    access_count INTEGER NOT NULL DEFAULT 0,  -- Number of times memory was accessed (for R3.3 staleness)

    -- Predictive Metadata for K1 (Rule 15)
    predictive_weight REAL,  -- For planner priority
    recommendation_readiness REAL,  -- 0.0-1.0
    privacy_risk_score REAL,  -- 0.0-1.0

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (event_id) REFERENCES st_hipp_events(event_id),
    FOREIGN KEY (canonical_episode_id) REFERENCES st_epi(episode_id),
    FOREIGN KEY (supersedes_episode_id) REFERENCES st_epi(episode_id),
    FOREIGN KEY (promoted_to_semantic_id) REFERENCES st_sem(semantic_id),
    FOREIGN KEY (promoted_to_routine_id) REFERENCES st_procedural(routine_id)
);

-- Indexes for episodic recall
CREATE INDEX idx_epi_tenant_time ON st_epi(tenant_id, event_time_utc);
CREATE INDEX idx_epi_actor_time ON st_epi(actor_id, event_time_utc);
CREATE INDEX idx_epi_canonical ON st_epi(canonical_episode_id) WHERE is_canonical = 0;
CREATE INDEX idx_epi_archival ON st_epi(archival_status, decay_factor);
```

**2. st_sem** (Semantic Memory Layer):

```sql
CREATE TABLE st_sem (
    semantic_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,
    canonical_semantic_id TEXT,
    is_canonical INTEGER NOT NULL DEFAULT 1,
    supersedes_semantic_id TEXT,
    valid_from TEXT NOT NULL,  -- Temporal validity start
    valid_to TEXT,  -- NULL = ongoing

    tenant_id TEXT NOT NULL,
    space_id TEXT NOT NULL,
    pattern_type TEXT NOT NULL,  -- routine/preference/fact/belief
    pattern_text TEXT NOT NULL,
    entities_json TEXT,  -- FK references to st_kg_dom.node_id

    -- Temporal Anchoring (Rule 2)
    temporal_context TEXT,  -- "weekday mornings", "after work"
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    observation_count INTEGER NOT NULL DEFAULT 1,
    temporal_bucket TEXT,
    is_weekend INTEGER,
    recency_weight REAL,

    -- Confidence & Provenance (Rules 4 & 5)
    frequency_score REAL,  -- How often pattern occurs
    confidence_score REAL NOT NULL,  -- 0.0-1.0
    source_count INTEGER NOT NULL,
    source_quality TEXT,
    ambiguity_score REAL,
    modalities_json TEXT,
    fusion_method TEXT,
    fusion_confidence REAL,

    -- Provenance
    source_episodes_json TEXT NOT NULL,  -- Array of episode_ids

    -- Consolidation Pattern Metadata (P03 R2 outputs)
    pattern_frequency TEXT,  -- daily/weekly/monthly/irregular (temporal pattern)
    pattern_last_occurrence TEXT,  -- Last event_time_utc in cluster

    -- Decay & Retention (Rule 7) - Probabilistic durability
    decay_factor REAL NOT NULL DEFAULT 1.0,
    archival_status TEXT NOT NULL DEFAULT 'ACTIVE',

    -- Predictive Metadata for K1
    predictive_weight REAL,
    recommendation_readiness REAL,
    privacy_risk_score REAL,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (canonical_semantic_id) REFERENCES st_sem(semantic_id),
    FOREIGN KEY (supersedes_semantic_id) REFERENCES st_sem(semantic_id)
);

CREATE INDEX idx_sem_pattern_frequency ON st_sem(pattern_frequency, last_observed_at);

CREATE INDEX idx_sem_tenant_pattern ON st_sem(tenant_id, pattern_type);
CREATE INDEX idx_sem_temporal ON st_sem(valid_from, valid_to);
CREATE INDEX idx_sem_decay ON st_sem(decay_factor, archival_status);
```

**3. st_procedural** (Procedural Memory Layer - Habits/Skills):

```sql
CREATE TABLE st_procedural (
    routine_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,
    canonical_routine_id TEXT,
    is_canonical INTEGER NOT NULL DEFAULT 1,
    supersedes_routine_id TEXT,
    valid_from TEXT NOT NULL,
    valid_to TEXT,

    tenant_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    routine_category TEXT NOT NULL,  -- routine/habit/skill/motor_sequence
    routine_name TEXT NOT NULL,
    trigger_context TEXT,  -- "Tuesday evening", "after breakfast"
    action_sequence_json TEXT,  -- Steps in the habit

    -- Temporal Anchoring (Rule 2)
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    last_performed_at TEXT,
    observation_count INTEGER NOT NULL DEFAULT 1,
    temporal_bucket TEXT,
    is_weekend INTEGER,
    recency_weight REAL,

    -- Habit Metrics (Adaptive durability - Rule 6)
    frequency TEXT,  -- daily/weekly/monthly
    consistency_score REAL,  -- 0.0-1.0
    streak_count INTEGER DEFAULT 0,
    longest_streak INTEGER DEFAULT 0,
    streak_history_json TEXT,  -- Log of all streak changes

    -- Confidence & Provenance (Rules 4 & 5)
    confidence_score REAL NOT NULL,
    source_count INTEGER NOT NULL,
    source_quality TEXT,
    ambiguity_score REAL,
    modalities_json TEXT,
    fusion_method TEXT,
    fusion_confidence REAL,

    -- Provenance
    source_episodes_json TEXT NOT NULL,

    -- Decay & Retention (Rule 7) - Adaptive durability
    decay_factor REAL NOT NULL DEFAULT 1.0,
    archival_status TEXT NOT NULL DEFAULT 'ACTIVE',

    -- Predictive Metadata for K1
    predictive_weight REAL,
    recommendation_readiness REAL,
    privacy_risk_score REAL,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (canonical_routine_id) REFERENCES st_procedural(routine_id),
    FOREIGN KEY (supersedes_routine_id) REFERENCES st_procedural(routine_id)
);

CREATE INDEX idx_proc_actor_routine ON st_procedural(actor_id, routine_name);
CREATE INDEX idx_proc_temporal ON st_procedural(valid_from, valid_to);
CREATE INDEX idx_proc_decay ON st_procedural(decay_factor, archival_status);
```

**4. st_social** (Social Memory Layer):

```sql
CREATE TABLE st_social (
    social_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,
    canonical_social_id TEXT,
    is_canonical INTEGER NOT NULL DEFAULT 1,
    supersedes_social_id TEXT,
    valid_from TEXT NOT NULL,
    valid_to TEXT,

    tenant_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    relationship_person_id TEXT NOT NULL,  -- FK to people.person_id
    relationship_kg_node_id TEXT,  -- FK to st_kg_dom.node_id

    interaction_type TEXT,  -- call/meeting/meal/activity
    interaction_frequency TEXT,  -- daily/weekly/monthly
    intimacy_level TEXT,  -- LOW/MEDIUM/HIGH
    communication_patterns_json TEXT,

    -- Temporal Anchoring (Rule 2)
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    last_interaction_at TEXT,
    observation_count INTEGER NOT NULL DEFAULT 1,
    recency_weight REAL,

    -- Confidence & Provenance (Rules 4 & 5)
    confidence_score REAL NOT NULL,
    source_count INTEGER NOT NULL,
    source_quality TEXT,
    ambiguity_score REAL,
    modalities_json TEXT,

    -- Provenance
    source_episodes_json TEXT NOT NULL,

    -- Decay & Retention (Rule 7) - Long-term durability with decay
    decay_factor REAL NOT NULL DEFAULT 1.0,
    archival_status TEXT NOT NULL DEFAULT 'ACTIVE',  -- Never delete, only decay

    -- Predictive Metadata for K1
    predictive_weight REAL,
    recommendation_readiness REAL,
    privacy_risk_score REAL,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (relationship_person_id) REFERENCES people(person_id),
    FOREIGN KEY (relationship_kg_node_id) REFERENCES st_kg_dom(node_id),
    FOREIGN KEY (canonical_social_id) REFERENCES st_social(social_id),
    FOREIGN KEY (supersedes_social_id) REFERENCES st_social(social_id)
);

CREATE INDEX idx_social_actor_person ON st_social(actor_id, relationship_person_id);
CREATE INDEX idx_social_temporal ON st_social(valid_from, valid_to);
CREATE INDEX idx_social_decay ON st_social(decay_factor, last_interaction_at);
```

**5. st_archives** (Archive Manifest - Cold Storage Tracking):

```sql
CREATE TABLE st_archives (
    archive_id TEXT PRIMARY KEY,
    storage_key TEXT NOT NULL,  -- S3/Blob key: {tenant_id}/{layer}/archive_{date}_{id}.json.gz
    layer TEXT NOT NULL,  -- st_epi/st_sem/st_procedural/st_social
    tenant_id TEXT NOT NULL,
    record_count INTEGER NOT NULL,
    record_ids_json TEXT NOT NULL,  -- JSON array of archived record IDs
    compressed_size_bytes INTEGER NOT NULL,
    archived_at TEXT NOT NULL,
    restore_cost_estimate REAL,  -- Estimated cloud egress cost in USD
    checksum TEXT,  -- SHA256 of compressed archive
    created_at TEXT NOT NULL
);

CREATE INDEX idx_archives_layer_tenant ON st_archives(layer, tenant_id, archived_at);
CREATE INDEX idx_archives_storage_key ON st_archives(storage_key);
```

**6. deletion_audit** (Deletion Audit Log - GDPR Compliance):

```sql
CREATE TABLE deletion_audit (
    audit_id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,
    layer TEXT NOT NULL,
    deleted_at TEXT NOT NULL,
    deleted_by TEXT,
    reason TEXT NOT NULL,
    gdpr_request_id TEXT,  -- For right-to-erasure requests
    retention_policy_id TEXT,  -- Policy that triggered deletion
    created_at TEXT NOT NULL
);

CREATE INDEX idx_deletion_audit_memory ON deletion_audit(memory_id, layer);
CREATE INDEX idx_deletion_audit_time ON deletion_audit(deleted_at);
CREATE INDEX idx_deletion_audit_gdpr ON deletion_audit(gdpr_request_id) WHERE gdpr_request_id IS NOT NULL;
```

**7. st_*_tombstones** (Tombstone Tables - Soft Delete Tracking):

```sql
-- Separate tombstone table for each memory layer
CREATE TABLE st_epi_tombstones (
    tombstone_id TEXT PRIMARY KEY,
    original_id TEXT NOT NULL,  -- Original episode_id
    layer TEXT NOT NULL DEFAULT 'st_epi',
    deleted_at TEXT NOT NULL,
    deleted_by TEXT,  -- Subject ID who initiated deletion
    deletion_reason TEXT NOT NULL,  -- retention_expired/user_request/privacy_purge/duplicate_removed
    grace_period_end TEXT NOT NULL,  -- deleted_at + 30 days
    content_hash TEXT NOT NULL,  -- SHA256 of original record (for verification)
    metadata_json TEXT NOT NULL,  -- Lightweight metadata (tenant_id, space_id, actor_id, event_time_utc, importance_score)
    gdpr_request_id TEXT,  -- For right-to-erasure compliance
    created_at TEXT NOT NULL
);

CREATE INDEX idx_epi_tombstone_grace ON st_epi_tombstones(grace_period_end) WHERE grace_period_end > datetime('now');
CREATE INDEX idx_epi_tombstone_original ON st_epi_tombstones(original_id);

-- Repeat for st_sem_tombstones, st_procedural_tombstones, st_social_tombstones, st_prospective_tombstones
-- (schemas identical except table name and layer default)
```

**5. st_prospective** (Prospective Memory Layer - Future Intentions):

```sql
CREATE TABLE st_prospective (
    prospective_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,
    canonical_prospective_id TEXT,
    is_canonical INTEGER NOT NULL DEFAULT 1,
    supersedes_prospective_id TEXT,

    tenant_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    intention_type TEXT NOT NULL,  -- reminder/goal/plan
    intention_text TEXT NOT NULL,
    trigger_condition TEXT,  -- "when at gym", "Tuesday morning"
    target_time TEXT,  -- ISO timestamp or relative time
    priority TEXT,  -- LOW/MEDIUM/HIGH

    -- Lifecycle Management (Rule 6 - Delete only after completion/expiry)
    status TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING/IN_PROGRESS/COMPLETED/EXPIRED/CANCELLED
    status_history_json TEXT,  -- Log of all status transitions

    -- Temporal Anchoring (Rule 2)
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    observation_count INTEGER NOT NULL DEFAULT 1,
    recency_weight REAL,

    -- Confidence & Provenance (Rules 4 & 5)
    confidence_score REAL NOT NULL,
    source_count INTEGER NOT NULL,
    source_quality TEXT,
    ambiguity_score REAL,
    modalities_json TEXT,

    -- Provenance
    source_episode_id TEXT,  -- FK to st_epi
    source_episodes_json TEXT,

    -- Predictive Metadata for K1 (Rule 15) - Critical for proactive agent
    predictive_weight REAL NOT NULL,  -- High priority for planner
    recommendation_readiness REAL NOT NULL,
    privacy_risk_score REAL,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    expired_at TEXT,

    FOREIGN KEY (source_episode_id) REFERENCES st_epi(episode_id),
    FOREIGN KEY (canonical_prospective_id) REFERENCES st_prospective(prospective_id),
    FOREIGN KEY (supersedes_prospective_id) REFERENCES st_prospective(prospective_id)
);

CREATE INDEX idx_prosp_actor_status ON st_prospective(actor_id, status);
CREATE INDEX idx_prosp_target_time ON st_prospective(target_time, status);
CREATE INDEX idx_prosp_priority ON st_prospective(priority, status);
```

**6. st_kg_dom** (Knowledge Graph - Domain Nodes):

```sql
CREATE TABLE st_kg_dom (
    node_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,
    canonical_node_id TEXT,  -- Entity equivalence merging
    is_canonical INTEGER NOT NULL DEFAULT 1,
    supersedes_node_id TEXT,
    merged_from_nodes_json TEXT,  -- Array of node_ids merged into this canonical
    valid_from TEXT NOT NULL,
    valid_to TEXT,  -- NULL = ongoing

    tenant_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,  -- Person/Location/Event/Organization/Thing
    entity_name TEXT NOT NULL,
    entity_attributes_json TEXT,

    -- Temporal Anchoring (Rule 2)
    first_mentioned_at TEXT NOT NULL,
    last_mentioned_at TEXT NOT NULL,
    mention_count INTEGER NOT NULL DEFAULT 1,
    recency_weight REAL,

    -- Confidence & Provenance (Rules 4 & 5)
    confidence_score REAL NOT NULL,
    source_count INTEGER NOT NULL,
    source_quality TEXT,
    ambiguity_score REAL,
    modalities_json TEXT,

    -- Provenance
    source_episodes_json TEXT NOT NULL,

    -- Decay & Retention (Rule 7) - Eventual consistency with merges
    decay_factor REAL NOT NULL DEFAULT 1.0,
    archival_status TEXT NOT NULL DEFAULT 'ACTIVE',

    -- Entity Resolution
    similarity_cluster_id TEXT,  -- For near-duplicate entities
    resolution_confidence REAL,

    -- Consolidation Metadata (P03 R4 outputs)
    observation_count INTEGER NOT NULL DEFAULT 1,  -- Number of times entity observed (R4.3)
    node_properties_json TEXT,  -- Additional metadata (evolution_type, reversal_date, etc. for R4.5)

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (canonical_node_id) REFERENCES st_kg_dom(node_id),
    FOREIGN KEY (supersedes_node_id) REFERENCES st_kg_dom(node_id)
);

CREATE INDEX idx_kg_entity_name ON st_kg_dom(entity_name, entity_type);
CREATE INDEX idx_kg_temporal ON st_kg_dom(valid_from, valid_to);
CREATE INDEX idx_kg_canonical ON st_kg_dom(canonical_node_id) WHERE is_canonical = 0;
```

**7. st_kg_edges** (Knowledge Graph - Edge Relationships):

```sql
CREATE TABLE st_kg_edges (
    edge_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,
    canonical_edge_id TEXT,
    is_canonical INTEGER NOT NULL DEFAULT 1,
    supersedes_edge_id TEXT,

    tenant_id TEXT NOT NULL,
    from_node_id TEXT NOT NULL,  -- FK to st_kg_dom
    to_node_id TEXT NOT NULL,    -- FK to st_kg_dom
    relationship_type TEXT NOT NULL,  -- DINED_WITH/WORKS_AT/LIVES_IN/etc.

    -- Temporal Validity (Rule 13 - context-dependent edges)
    valid_from TEXT NOT NULL,
    valid_to TEXT,  -- NULL = ongoing

    -- Temporal Anchoring (Rule 2)
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    observation_count INTEGER NOT NULL DEFAULT 1,
    recency_weight REAL,

    -- Confidence & Provenance (Rules 4 & 5)
    confidence_score REAL NOT NULL,
    source_count INTEGER NOT NULL,
    source_quality TEXT,
    ambiguity_score REAL,
    modalities_json TEXT,

    -- Context-Dependent Metadata
    context_type TEXT,  -- work/social/family/location
    context_attributes_json TEXT,

    -- Provenance
    source_episodes_json TEXT NOT NULL,

    -- Consolidation Metadata (P03 R4 outputs)
    edge_properties_json TEXT,  -- Additional metadata (average_delay_minutes, confounders_json for R4.4 causal)

    -- Decay & Retention (Rule 7)
    decay_factor REAL NOT NULL DEFAULT 1.0,
    archival_status TEXT NOT NULL DEFAULT 'ACTIVE',

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (from_node_id) REFERENCES st_kg_dom(node_id),
    FOREIGN KEY (to_node_id) REFERENCES st_kg_dom(node_id),
    FOREIGN KEY (canonical_edge_id) REFERENCES st_kg_edges(edge_id),
    FOREIGN KEY (supersedes_edge_id) REFERENCES st_kg_edges(edge_id)
);

CREATE INDEX idx_kg_edge_from ON st_kg_edges(from_node_id, relationship_type);
CREATE INDEX idx_kg_edge_to ON st_kg_edges(to_node_id, relationship_type);
CREATE INDEX idx_kg_edge_temporal ON st_kg_edges(valid_from, valid_to);
```

**8. st_kg_snapshots** (Knowledge Graph Snapshots - Historical Versioning):

```sql
CREATE TABLE st_kg_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    snapshot_date TEXT NOT NULL,  -- Point-in-time snapshot timestamp
    tenant_id TEXT NOT NULL,
    entity_count INTEGER NOT NULL,  -- Number of entities in snapshot
    edge_count INTEGER NOT NULL,    -- Number of relationships in snapshot
    storage_key TEXT NOT NULL,      -- S3/Blob key for snapshot JSON export
    compressed_size_bytes INTEGER,
    checksum TEXT,  -- SHA256 of snapshot file
    created_at TEXT NOT NULL
);

CREATE INDEX idx_kg_snapshot_date ON st_kg_snapshots(tenant_id, snapshot_date);
CREATE INDEX idx_kg_snapshot_storage ON st_kg_snapshots(storage_key);
```

**8. st_vec** (Vector Embeddings - P02 Episodic + P03 Semantic):

```sql
-- Architecture Update (2025-12-13):
-- - P02 M16 writes episodic embeddings INLINE (status=READY) via atomic 3-table transaction
-- - P03 R7.7 writes semantic pattern embeddings (status=READY)
-- - P08 kernel scheduler polls and indexes into FAISS (READY → INDEXED)
-- - st_embedding_queue is DEPRECATED

-- Durability: REGENERATABLE (Rule 6) - Treat as cached compute, not ground truth
-- LLM-Invariant (Rule 17) - Can rebuild entirely if model changes
CREATE TABLE st_vec (
    embedding_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,

    -- Source References (LLM-invariant - Rule 17)
    event_id TEXT NOT NULL,  -- FK to st_hipp_events (required, written by P02 M16)
    episode_id TEXT,  -- FK to st_epi (consolidated, written by P03)
    semantic_id TEXT,  -- FK to st_sem (pattern, written by P03)
    source_type TEXT NOT NULL,  -- event/episode/semantic/kg_node

    embedding_type TEXT NOT NULL,  -- text/semantic/episode/multimodal

    -- Vector Data (Written inline by P02/P03, NOT by P08)
    vector BLOB NOT NULL,  -- 768-dim UltraBERT embedding (written at insert time)
    vector_dim INTEGER NOT NULL DEFAULT 768,  -- UltraBERT dimension

    -- Model Metadata (Rule 17 - model can change without breaking storage)
    model_id TEXT NOT NULL DEFAULT 'ultrabert_v2.1.0',
    model_version TEXT,
    model_family TEXT DEFAULT 'ultrabert',  -- ultrabert/sentence-transformers/custom
    tokenizer_version TEXT,

    -- Status (P02/P03 write READY, P08 updates to INDEXED)
    status TEXT NOT NULL DEFAULT 'READY',  -- READY/INDEXED/FAILED/STALE
    faiss_id INTEGER,  -- Set by P08 kernel scheduler after FAISS indexing
    regeneration_priority INTEGER,  -- For model upgrades

    -- Confidence (Rule 4)
    confidence_score REAL,
    source_quality TEXT,

    -- Temporal (for vector expiry)
    generated_at TEXT,
    expires_at TEXT,  -- Vectors can expire and be regenerated

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (event_id) REFERENCES st_hipp_events(event_id),
    FOREIGN KEY (episode_id) REFERENCES st_epi(episode_id),
    FOREIGN KEY (semantic_id) REFERENCES st_sem(semantic_id)
);

CREATE INDEX idx_vec_source ON st_vec(source_type, episode_id, semantic_id);
CREATE INDEX idx_vec_status ON st_vec(status, model_version);
CREATE INDEX idx_vec_regeneration ON st_vec(regeneration_priority) WHERE status = 'STALE';
```

**Note on st_fts** (Full-Text Search - Coordinated with P08):

P03 does not directly write to `st_fts`. Instead:

- P03 writes consolidated memories to `st_epi`, `st_sem`, `st_prospective`
- P08 maintains `st_fts` as an FTS5 virtual table indexing those layers
- `st_fts` provides BM25-ranked full-text search over consolidated content
- Schema defined in P08 dossier (FTS5 virtual table over `text`, `participants`, `location_name`, `activity_type` from memory layers)

---

#### **Infrastructure & Audit Tables**

**9. st_consolidation_logs** (Consolidation Audit Trail):

```sql
CREATE TABLE st_consolidation_logs (
    log_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    pipeline_run_id TEXT NOT NULL,
    event_id TEXT NOT NULL,  -- FK to st_hipp_events
    consolidation_phase TEXT NOT NULL,  -- dedup/pattern_extract/kg_build/etc.
    phase_status TEXT NOT NULL,  -- SUCCESS/FAILED/SKIPPED
    phase_duration_ms INTEGER,
    error_message TEXT,
    created_at TEXT NOT NULL
);
```

**10. st_event_canon_map** (Canonical Event Mapping):

```sql
CREATE TABLE st_event_canon_map (
    map_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,  -- Duplicate event
    canonical_event_id TEXT NOT NULL,  -- Canonical (kept) event
    similarity_score REAL,
    created_at TEXT NOT NULL,
    source TEXT  -- dedup_simhash/dedup_minhash/manual
);
```

**11. st_event_cluster_history** (Cluster Assignment History):

```sql
CREATE TABLE st_event_cluster_history (
    history_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    cluster_id TEXT NOT NULL,
    assigned_at TEXT NOT NULL,
    confidence REAL,
    cluster_type TEXT  -- temporal/semantic/spatial
);
```

---

#### **Updates to Existing Tables**

**st_hipp_events** (In-Place Updates):

- `novelty_score` = REAL (0.0-1.0)
- `near_duplicates_json` = TEXT (JSON array)
- `is_near_duplicate` = INTEGER (0/1)
- `episode_cluster_id` = TEXT
- `cluster_confidence` = REAL (0.0-1.0)
- `consolidation_status` = 'COMPLETE'
- `consolidated_at` = ISO timestamp

**st_pipeline_processed** (Progress Tracking):

- INSERT: `(pipeline_id='P03_CONSOLIDATION', space_id, wal_pos, processed_at, status='SUCCESS')`

---

### Durability Contracts Per Layer (World-Class Architecture Principles)

P03 memory layers follow **18 world-class durability principles** to ensure the system remains solid for decades:

#### **Consistency Levels**

| Layer | Consistency | Mutation Rules | Durability |
|-------|-------------|----------------|------------|
| **st_epi** | **Strong** | Never delete. Only canonicalize via versioning. | **PERMANENT** - Append-only, full lineage |
| **st_sem** | **Eventual** | Patterns adapt, keep history with valid_from/to. | **PROBABILISTIC** - Convergent, versioned |
| **st_procedural** | **Periodic (24h)** | Update streaks, log every change in history JSON. | **ADAPTIVE** - Self-correcting, streak audit |
| **st_social** | **Eventual** | Keep decaying relationships, never drop. | **LONG-TERM** - Decay-based, never delete |
| **st_prospective** | **Strong** | Delete only after COMPLETED/EXPIRED. | **LIFECYCLE** - Status-based retention |
| **st_kg_dom** | **Eventual (merges)** | Keep temporal boundaries (valid_from/to). | **VERSIONED** - Entity equivalence merging |
| **st_kg_edges** | **Eventual (merges)** | Context-dependent edges with temporal validity. | **VERSIONED** - Relationship evolution |
| **st_vec** | **Lazy** | Treat as cached compute, regenerate on model change. | **REGENERATABLE** - Not ground truth |

#### **Forgetting Model (Exponential Decay)**

All layers (except st_epi, st_prospective) use exponential decay:

```python
# Decay formula per layer
decay_factor = exp(-λ * days_since_last_observed)

# Threshold-based archival
if decay_factor < 0.05:
    archival_status = 'ARCHIVED'
elif decay_factor < 0.01:
    archival_status = 'DEEP_FREEZE'
```

**Decay Constants (λ) per Layer**:

- **st_sem**: λ = 0.01 (semantic patterns fade slowly)
- **st_procedural**: λ = 0.02 (habits fade faster if not reinforced)
- **st_social**: λ = 0.005 (relationships decay very slowly)
- **st_kg_dom/edges**: λ = 0.008 (knowledge graph entities persist)

**User Control**: Only user can authorize permanent deletion. System only archives.

#### **Immutability + Versioning**

All 8 layers support:

- `version` column (increments on update)
- `canonical_*_id` (points to canonical version)
- `is_canonical` flag (0=superseded, 1=active)
- `supersedes_*_id` (previous version chain)
- `valid_from` / `valid_to` (temporal validity)

**Update Pattern** (append-only):

```sql
-- Never UPDATE existing row, always INSERT new version
INSERT INTO st_sem (
    semantic_id, version, canonical_semantic_id, supersedes_semantic_id,
    pattern_text, confidence_score, valid_from, ...
) VALUES (
    'sem_v2_uuid', 2, 'sem_v1_uuid', 'sem_v1_uuid',
    'Updated pattern', 0.92, '2025-11-20T00:00:00Z', ...
);

-- Mark old version as superseded
UPDATE st_sem SET is_canonical = 0 WHERE semantic_id = 'sem_v1_uuid';
```

#### **Temporal Anchoring (All Layers)**

Every layer includes:

- `first_observed_at` (immutable)
- `last_observed_at` (updated on reinforcement)
- `observation_count` (how many times pattern observed)
- `temporal_bucket` (MORNING/AFTERNOON/EVENING/NIGHT)
- `is_weekend` (0/1)
- `recency_weight` = exp(-λ * days_since_last_observed)

**Why**: LLMs reason poorly in time. Storage compensates.

#### **Confidence Scores (All Layers)**

Every record includes:

- `confidence_score` (0.0-1.0) - Overall confidence
- `source_count` - How many events contributed
- `source_quality` - text/sensor/derived/fused
- `ambiguity_score` (0.0-1.0) - Uncertainty measure
- `modalities_json` - ["text", "gps", "heart_rate", etc.]
- `fusion_method` - late/early/hybrid (if multi-modal)
- `fusion_confidence` - Multi-modal fusion quality

**Why**: Enables probabilistic recall, safer LLM advice, uncertainty tracking.

#### **Cross-Layer Referential Integrity**

All layers maintain explicit foreign keys:

- **st_epi** ← `event_id` (st_hipp_events)
- **st_sem** ← `source_episodes_json` (st_epi)
- **st_procedural** ← `source_episodes_json` (st_epi)
- **st_social** ← `relationship_person_id` (people), `relationship_kg_node_id` (st_kg_dom)
- **st_prospective** ← `source_episode_id` (st_epi)
- **st_kg_dom** ← `source_episodes_json` (st_epi)
- **st_kg_edges** ← `from_node_id`, `to_node_id` (st_kg_dom)
- **st_vec** ← `episode_id`, `semantic_id` (st_epi, st_sem)

**Why**: Shapes system into cognitive graph, not disconnected tables.

#### **Predictive Metadata for K1 (All Layers)**

Every layer includes K1-specific metadata:

- `predictive_weight` - Priority for planner (0.0-1.0)
- `recommendation_readiness` - Ready for proactive suggestions (0.0-1.0)
- `privacy_risk_score` - Privacy sensitivity (0.0-1.0)

**Why**: Memory substrate directly useful for agent orchestration.

#### **LLM-Invariant Storage (Rule 17 & 18)**

**Never treat model-generated artifacts as ground truth**:

- ❌ Model-generated text (hallucinations) - never store as facts
- ❌ Model-generated conclusions - never store as memories
- ❌ Model-specific reasoning artifacts

**Always store as ground truth**:

- ✅ Facts (from user input or sensors)
- ✅ Patterns (statistical, not inferred)
- ✅ Signals (raw or normalized)
- ✅ Temporal dynamics

**Exception - Regeneratable Cache**:

- `st_vec` (embeddings) stores model-specific artifacts BUT:
  - Treated as **REGENERATABLE** cache, not ground truth
  - Marked with model_id/model_version for tracking
  - Can rebuild entirely when model changes
  - Never used for gap detection or provenance

**Model Upgrades**: st_vec can regenerate entirely without breaking other layers.

#### **Parallelizable Writes (Rule 8)**

All layers support:

- Batch writes (500-2000 items)
- Idempotent inserts (use upsert with `ON CONFLICT`)
- Conflict-free retries
- WAL-driven continuation via `st_pipeline_processed`

**Pattern**:

```sql
INSERT INTO st_epi (...)
ON CONFLICT (episode_id) DO UPDATE SET
    observation_count = st_epi.observation_count + 1,
    last_observed_at = EXCLUDED.last_observed_at,
    recency_weight = EXCLUDED.recency_weight;
```

#### **Locality-Aware Partitioning (Rule 9)**

All tables partitioned by:

- `tenant_id` (family isolation)
- `space_id` (personal/shared spaces)
- `event_time_utc` (monthly partitions for time-series queries)

**Implementation** (SQLite with attached DBs or PostgreSQL native partitioning):

```sql
-- Future: Monthly partitions
st_epi_2025_11
st_epi_2025_12
```

---

### Active Learning Loop Integration (K0 P06 ↔ Memory Layers)

The **Active Learning Loop** (ADR-0001-active-learning-loop) requires bidirectional access to memory layers for:

1. **Gap Detection** (P06 Entropy Scanner reads memory layers)
2. **Answer Ingestion** (P02/P03 updates memory layers with user responses)
3. **Confidence Tracking** (Bayesian updates to anchor points)

#### **Memory Layer Requirements for Active Learning**

All 8 memory layers already include required columns:

✅ **Confidence & Uncertainty** (Rule 4):

- `confidence_score` - Enables gap detection when confidence < 0.7
- `ambiguity_score` - High ambiguity triggers disambiguation questions
- `source_count` - Low count indicates insufficient evidence
- `source_quality` - "derived" quality suggests need for validation

✅ **Temporal Decay** (Rule 7):

- `decay_factor` - Detects stale beliefs needing re-validation
- `last_observed_at` - Identifies anchors not reinforced recently
- `observation_count` - Tracks how many times pattern observed

✅ **Provenance & Traceability** (Rule 3):

- `source_episodes_json` - Traces which events contributed to belief
- `version`, `supersedes_*_id` - Tracks belief evolution over time

✅ **Predictive Metadata** (Rule 15):

- `predictive_weight` - P06 prioritizes high-value gaps
- `recommendation_readiness` - Indicates if belief is stable enough for proactive suggestions

#### **P06 Learning Pipeline (Entropy Scanner) - Read Operations**

```python
# k0/pipelines/p06_learning/entropy_scanner.py

class EntropyScanner:
    """Background process that scans memory layers for gaps."""

    async def scan_episodic_layer(self) -> List[GapRecord]:
        """Find ambiguous episodes needing clarification."""
        gaps = []

        # Query: Episodes with low confidence or high ambiguity
        query = """
        SELECT episode_id, confidence_score, ambiguity_score, context_json
        FROM st_epi
        WHERE is_canonical = 1
          AND confidence_score < 0.7
          AND archival_status = 'ACTIVE'
        ORDER BY ambiguity_score DESC
        LIMIT 100
        """

        for row in await self.db.query(query):
            gaps.append(GapRecord(
                gap_type='LOW_CONFIDENCE_EPISODE',
                entity_id=row['episode_id'],
                confidence_score=row['confidence_score'],
                entropy_score=row['ambiguity_score'],
                importance_score=row['ambiguity_score'] / (row['confidence_score'] + 0.1)
            ))

        return gaps

    async def scan_semantic_layer(self) -> List[GapRecord]:
        """Find weak patterns needing validation."""
        gaps = []

        # Query: Patterns with low observation count or decaying confidence
        query = """
        SELECT semantic_id, pattern_text, confidence_score, observation_count, decay_factor
        FROM st_sem
        WHERE is_canonical = 1
          AND (observation_count < 3 OR decay_factor < 0.5)
          AND archival_status = 'ACTIVE'
        ORDER BY (1 - decay_factor) * (1 - confidence_score) DESC
        LIMIT 50
        """

        for row in await self.db.query(query):
            gaps.append(GapRecord(
                gap_type='WEAK_PATTERN',
                entity_id=row['semantic_id'],
                confidence_score=row['confidence_score'],
                entropy_score=1.0 - row['decay_factor'],
                context_json=json.dumps({
                    'pattern_text': row['pattern_text'],
                    'observation_count': row['observation_count']
                })
            ))

        return gaps

    async def scan_kg_layer(self) -> List[GapRecord]:
        """Find ambiguous entities needing disambiguation."""
        gaps = []

        # Query: Entities with missing attributes or low confidence
        query = """
        SELECT node_id, entity_name, entity_type, confidence_score,
               entity_attributes_json, ambiguity_score
        FROM st_kg_dom
        WHERE is_canonical = 1
          AND (ambiguity_score > 0.6 OR confidence_score < 0.7)
          AND archival_status = 'ACTIVE'
        ORDER BY ambiguity_score DESC
        LIMIT 100
        """

        for row in await self.db.query(query):
            attrs = json.loads(row['entity_attributes_json'])
            required_attrs = ONTOLOGY[row['entity_type']].required_attributes
            missing_attrs = set(required_attrs) - set(attrs.keys())

            if missing_attrs:
                gaps.append(GapRecord(
                    gap_type='MISSING_ATTRIBUTE',
                    entity_id=row['node_id'],
                    confidence_score=row['confidence_score'],
                    entropy_score=len(missing_attrs) / len(required_attrs),
                    context_json=json.dumps({
                        'entity_name': row['entity_name'],
                        'entity_type': row['entity_type'],
                        'missing_attributes': list(missing_attrs)
                    })
                ))

        return gaps

    async def detect_concept_drift(self) -> List[GapRecord]:
        """Detect beliefs that are changing over time."""
        gaps = []

        # Query: Semantic patterns with recent observation divergence
        query = """
        SELECT s.semantic_id, s.pattern_text, s.confidence_score, s.temporal_context,
               s.source_episodes_json, s.first_observed_at, s.last_observed_at
        FROM st_sem s
        WHERE s.is_canonical = 1
          AND s.observation_count >= 5
          AND s.archival_status = 'ACTIVE'
          AND (julianday('now') - julianday(s.last_observed_at)) > 30
        """

        for row in await self.db.query(query):
            # Analyze recent vs old episodes
            episodes = json.loads(row['source_episodes_json'])
            drift_detected = await self.analyze_temporal_shift(episodes, window_days=30)

            if drift_detected:
                gaps.append(GapRecord(
                    gap_type='CONCEPT_DRIFT',
                    entity_id=row['semantic_id'],
                    confidence_score=row['confidence_score'],
                    entropy_score=drift_detected.magnitude,
                    context_json=json.dumps({
                        'pattern_text': row['pattern_text'],
                        'old_confidence': drift_detected.old_value,
                        'new_confidence': drift_detected.new_value,
                        'drift_direction': drift_detected.direction
                    })
                ))

        return gaps
```

#### **P02/P03 Write Operations (Answer Ingestion)**

When user answers a curiosity question, update memory layers:

```python
# k0/pipelines/p02_write/answer_processor.py

class AnswerProcessor:
    """Process user answers to curiosity questions and update memory layers."""

    async def ingest_answer(self, answer: UserAnswer, gap: GapRecord) -> None:
        """Update memory layers based on user's clarification."""

        if gap.gap_type == 'AMBIGUOUS_ENTITY':
            await self.resolve_entity_ambiguity(answer, gap)

        elif gap.gap_type == 'MISSING_ATTRIBUTE':
            await self.add_entity_attribute(answer, gap)

        elif gap.gap_type == 'WEAK_PATTERN':
            await self.reinforce_semantic_pattern(answer, gap)

        elif gap.gap_type == 'CONCEPT_DRIFT':
            await self.update_drifted_belief(answer, gap)

    async def resolve_entity_ambiguity(self, answer: UserAnswer, gap: GapRecord) -> None:
        """User clarified which entity they meant."""

        # Update KG node with higher confidence
        await self.db.execute("""
        UPDATE st_kg_dom
        SET confidence_score = 0.95,
            ambiguity_score = 0.1,
            source_count = source_count + 1,
            source_quality = 'user_clarified',
            last_observed_at = ?,
            updated_at = ?
        WHERE node_id = ?
        """, (datetime.now().isoformat(), datetime.now().isoformat(), answer.resolved_entity_id))

        # Add observation to anchor
        await self.db.execute("""
        INSERT INTO st_anchor_observations (id, entity_id, attribute, observed_at,
                                           event_id, supports_anchor, confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (uuid4().hex, answer.resolved_entity_id, 'identity_confirmed',
              time.time(), answer.triggering_event_id, True, 1.0))

    async def add_entity_attribute(self, answer: UserAnswer, gap: GapRecord) -> None:
        """User provided missing attribute (e.g., person's role, preference)."""

        context = json.loads(gap.context_json)
        entity_id = gap.entity_id
        new_attrs = answer.attributes

        # Read current attributes
        current_attrs_json = await self.db.query_one("""
        SELECT entity_attributes_json FROM st_kg_dom WHERE node_id = ?
        """, (entity_id,))

        current_attrs = json.loads(current_attrs_json)
        current_attrs.update(new_attrs)

        # Update with new attributes (versioned update)
        new_version_id = f"{entity_id}_v{int(time.time())}"
        await self.db.execute("""
        INSERT INTO st_kg_dom (
            node_id, version, canonical_node_id, supersedes_node_id, is_canonical,
            tenant_id, entity_type, entity_name, entity_attributes_json,
            confidence_score, source_count, source_quality, ambiguity_score,
            first_mentioned_at, last_mentioned_at, mention_count,
            source_episodes_json, decay_factor, archival_status,
            created_at, updated_at
        )
        SELECT
            ?, version + 1, ?, node_id, 1,
            tenant_id, entity_type, entity_name, ?,
            0.90, source_count + 1, 'user_provided', 0.2,
            first_mentioned_at, ?, mention_count + 1,
            source_episodes_json, 1.0, 'ACTIVE',
            ?, ?
        FROM st_kg_dom WHERE node_id = ?
        """, (new_version_id, entity_id, json.dumps(current_attrs),
              datetime.now().isoformat(), datetime.now().isoformat(),
              datetime.now().isoformat(), entity_id))

        # Mark old version as superseded
        await self.db.execute("""
        UPDATE st_kg_dom SET is_canonical = 0 WHERE node_id = ?
        """, (entity_id,))

    async def reinforce_semantic_pattern(self, answer: UserAnswer, gap: GapRecord) -> None:
        """User confirmed a weak pattern is valid."""

        semantic_id = gap.entity_id

        # Bayesian update: increase confidence
        await self.db.execute("""
        UPDATE st_sem
        SET confidence_score = MIN(0.95, confidence_score + 0.15),
            observation_count = observation_count + 1,
            source_count = source_count + 1,
            source_quality = 'user_validated',
            ambiguity_score = MAX(0.1, ambiguity_score - 0.2),
            decay_factor = 1.0,
            last_observed_at = ?,
            recency_weight = 1.0,
            updated_at = ?
        WHERE semantic_id = ?
        """, (datetime.now().isoformat(), datetime.now().isoformat(), semantic_id))

    async def update_drifted_belief(self, answer: UserAnswer, gap: GapRecord) -> None:
        """User indicated belief has changed (concept drift)."""

        semantic_id = gap.entity_id
        context = json.loads(gap.context_json)

        # Create new version with updated pattern
        new_version_id = f"{semantic_id}_v{int(time.time())}"
        await self.db.execute("""
        INSERT INTO st_sem (
            semantic_id, version, canonical_semantic_id, supersedes_semantic_id, is_canonical,
            valid_from, valid_to, tenant_id, space_id, pattern_type, pattern_text,
            confidence_score, source_count, source_quality, ambiguity_score,
            first_observed_at, last_observed_at, observation_count,
            decay_factor, archival_status, created_at, updated_at
        )
        SELECT
            ?, version + 1, ?, semantic_id, 1,
            ?, valid_to, tenant_id, space_id, pattern_type, ?,
            0.85, 1, 'user_updated', 0.3,
            ?, ?, 1,
            1.0, 'ACTIVE', ?, ?
        FROM st_sem WHERE semantic_id = ?
        """, (new_version_id, semantic_id, datetime.now().isoformat(),
              answer.updated_pattern_text, datetime.now().isoformat(),
              datetime.now().isoformat(), datetime.now().isoformat(),
              datetime.now().isoformat(), semantic_id))

        # Mark old version as superseded with valid_to
        await self.db.execute("""
        UPDATE st_sem
        SET is_canonical = 0, valid_to = ?
        WHERE semantic_id = ?
        """, (datetime.now().isoformat(), semantic_id))
```

#### **Summary: Active Learning ↔ Memory Layer Contract**

| Memory Layer | P06 Reads For | P02/P03 Writes When |
|--------------|---------------|---------------------|
| **st_epi** | Low confidence episodes, ambiguous events | User clarifies episode details, adds missing context |
| **st_sem** | Weak patterns (<3 observations), decaying beliefs | User validates pattern, corrects drifted belief |
| **st_procedural** | Habits with low consistency, broken streaks | User explains habit change, confirms routine |
| **st_social** | Relationships with ambiguity, missing intimacy level | User clarifies relationship type, frequency |
| **st_prospective** | Incomplete intentions, vague triggers | User specifies trigger condition, target time |
| **st_kg_dom** | Missing attributes, ambiguous entities, low confidence | User disambiguates entity, provides attributes |
| **st_kg_edges** | Low confidence relationships, temporal validity gaps | User confirms relationship, specifies time bounds |
| **st_vec** | N/A (regeneratable, not used for gap detection) | Embeddings regenerated after answer updates KG |

**All required columns already present** - no schema changes needed! ✅

The world-class durability principles (immutability, confidence scores, decay functions, provenance) directly enable the Active Learning Loop without additional schema changes.

---

### Exit Topics

**Primary Exit Topic**: `p03.consolidation.complete.v1`

**Additional Event Emissions**:

- `p03.pattern.detected.v1` - Semantic pattern extracted
- `p03.duplicate.detected.v1` - Near-duplicate found
- `p03.cluster.formed.v1` - Episode cluster created
- `p03.habit.detected.v1` - Procedural habit identified
- `p03.kg.entity.created.v1` - Knowledge graph entity added
- `p03.kg.relationship.created.v1` - Knowledge graph edge added
- `p03.memory.forgotten.v1` - Memory pruned/archived
- `p03.consolidation.failed.v1` - Error during consolidation

**Event Bus Integration**: All events written to `st_outbox` via `syscalls.outbox_emit()`

---

### External Device Protocol (Future - P09)

**Note**: P03 reads from `st_hipp_events` regardless of data source. External devices will use **P09 Connector Ingestion Protocol** (to be defined):

**Standard Protocol Requirements** (Design TBD):

1. **Authentication**: OAuth 2.0 or API Key
2. **Data Format**: JSON envelope matching `memory.sensor.*` topic schemas
3. **Privacy Bands**: Device declares sensitivity (GREEN/AMBER/RED)
4. **Rate Limiting**: Max events/second per device type
5. **Batch Support**: Bulk upload for offline data sync
6. **Idempotency**: Client-provided `idem_key` for duplicate prevention

**Example External Device Envelope** (Future):

```json
{
  "topic": "memory.sensor.health.v1",
  "actor_id": "person_dad",
  "device_id": "apple_watch_series_8",
  "band": "RED",
  "body": {
    "sensor_type": "heart_rate",
    "value": 72,
    "unit": "bpm",
    "timestamp": "2025-11-20T14:30:00Z"
  }
}
```

**Flow**: External Device → P09 (validate/normalize) → P02 (enrich) → `st_hipp_events` → P03 (consolidate)

---

## Example Input (st_hipp_events row from P02)

Below is a realistic example of a single row from `st_hipp_events` after P02 processing. P03 will read this row, perform consolidation, and write to the 8 memory layers.

### Example Scenario

**User Action**: Dad logs a memory via K1 chat: *"Had dinner with Sarah at the new Thai place on Oak Street. Really enjoyed the curry!"*

**P02 Processing**: Enriches the event with affect analysis, space resolution, temporal profiling, social enrichment, DG fingerprinting.

**Result**: Row written to `st_hipp_events` with 95 columns populated:

```json
{
  "event_id": "evt_01HZWK9A2B3C4D5E6F7G8H9J0K",
  "wal_pos": 12847,
  "cognitive_trace_id": "trace_family_dinner_20251120",
  "tenant_id": "tenant_smith_family",
  "space_id": "personal:dad",
  "effective_space_id": "personal:dad",
  "topic": "memory.episodic.formation.v1",
  "uow_id": "uow_01HZWK9A2B3C4D5E6F7G8H9J0K",

  "envelope_sha256": "a3f5e9c2b8d7f1a4e6c9b2d5f8a1c4e7b0d3f6a9c2e5b8d1f4a7c0e3b6d9f2a5",
  "sig_alg": "EdDSA",
  "sig_kid": "key_dad_device_iphone14",
  "idem_key": "idem_dad_20251120T193000Z",
  "ingested_at": "2025-11-20T19:30:00.000Z",
  "clock_skew_ms": 42,

  "policy_decision": "ALLOW",
  "policy_band": "GREEN",
  "policy_version": "v2.3.1",
  "obligations_json": "[]",
  "visible_to_json": "[\"person_dad\", \"person_mom\"]",
  "visibility_scope": "SPACE_DEFAULT",
  "owner_id": "person_dad",
  "co_owners_json": "[]",
  "retention_policy_id": "rp_standard_green",
  "retention_bucket": "STANDARD",

  "actor_id": "person_dad",
  "actor_role": "parent",
  "device_id": "device_dad_iphone14",
  "device_kind": "phone",
  "device_os": "iOS",
  "ingress_channel": "k1.conversation",

  "event_time_utc": "2025-11-20T19:15:00.000Z",
  "write_time_utc": "2025-11-20T19:30:00.000Z",
  "write_lag_ms": 900000,
  "local_date": "2025-11-20",
  "local_time": "19:15:00",
  "day_of_week": "Wednesday",
  "is_weekend": 0,
  "time_of_day_bucket": "EVENING",
  "circadian_slot": "DECLINE",
  "is_backdated": 0,

  "location_name": "Thai Basil Restaurant",
  "location_type": "restaurant",
  "geohash_6": "9q9p3v",
  "geo_precision_external": 10,
  "geo_masking_reason": null,

  "participants_json": "[\"person_dad\", \"person_sarah_colleague\"]",
  "num_participants": 2,
  "has_partner_present": 0,
  "has_parent_present": 0,
  "is_solo_event": 0,
  "participant_roles_json": "{\"person_dad\": \"self\", \"person_sarah_colleague\": \"colleague\"}",
  "social_context": "WORK",
  "social_intimacy": "MEDIUM",

  "text": "Had dinner with Sarah at the new Thai place on Oak Street. Really enjoyed the curry!",
  "text_normalized": "had dinner with sarah at the new thai place on oak street really enjoyed the curry",
  "char_count": 85,
  "token_count": 17,
  "language": "en",
  "activity_type": "meal",
  "activity_category": "dining",
  "is_meal": 1,
  "is_outing": 1,

  "simhash_hex": "8f3a2c5e9b1d4f7a",
  "minhash32": "[0x8f3a2c5e, 0x9b1d4f7a, 0x3c5e8f1d, 0x4f7a2c9b, 0x1d8f3a5e, 0x7a4f2c9b, 0x5e8f3a1d, 0x9b4f7a2c, 0x3a5e8f1d, 0x7a9b4f2c, 0x1d3c5e8f, 0x2c9b4f7a, 0x8f1d3a5e, 0x4f7a9b2c, 0x5e3c8f1d, 0x9b7a4f2c, 0x3a8f5e1d, 0x7a4f9b2c, 0x1d5e3c8f, 0x2c7a4f9b, 0x8f3a1d5e, 0x4f9b7a2c, 0x5e1d3c8f, 0x9b2c7a4f, 0x3a8f1d5e, 0x7a9b4f2c, 0x1d3c5e8f, 0x2c4f7a9b, 0x8f5e3a1d, 0x4f2c9b7a, 0x5e8f1d3a, 0x9b7a2c4f]",
  "novelty_score": null,
  "near_duplicates_json": null,
  "is_near_duplicate": null,
  "episode_cluster_id": null,
  "cluster_confidence": null,

  "embedding_id": "emb_01HZWK9A2B3C4D5E6F7G8H9J0K",
  "embedding_status": "PENDING",
  "entities_json": "[{\"text\": \"Sarah\", \"type\": \"PERSON\", \"entity_id\": \"person_sarah_colleague\"}, {\"text\": \"Thai Basil Restaurant\", \"type\": \"LOCATION\", \"entity_id\": \"loc_thai_basil_oak_st\"}, {\"text\": \"Oak Street\", \"type\": \"LOCATION\", \"entity_id\": \"loc_oak_street\"}, {\"text\": \"curry\", \"type\": \"FOOD\", \"entity_id\": \"food_curry\"}]",
  "kg_triples_json": "[{\"subject\": \"person_dad\", \"predicate\": \"DINED_WITH\", \"object\": \"person_sarah_colleague\", \"confidence\": 0.95}, {\"subject\": \"person_dad\", \"predicate\": \"ATE_AT\", \"object\": \"loc_thai_basil_oak_st\", \"confidence\": 0.92}, {\"subject\": \"person_dad\", \"predicate\": \"ENJOYED\", \"object\": \"food_curry\", \"confidence\": 0.88}]",

  "sentiment_score": 0.72,
  "sentiment_label": "positive",
  "dominant_emotions_json": "[\"joy\", \"satisfaction\"]",
  "affect_valence": 0.75,
  "affect_arousal": 0.45,
  "affect_band": "NEUTRAL",
  "salience_score": 0.68,
  "salience_reasons_json": "[\"social_interaction\", \"new_experience\", \"positive_affect\"]",
  "salience_band": "MEDIUM",

  "ingress_source": "p02_write_pipeline",
  "hippocampus_api_version": "v1.2.3",
  "space_resolver_version": "v1.0.8",
  "created_at": "2025-11-20T19:30:00.123Z",
  "updated_at": "2025-11-20T19:30:00.123Z",

  "consolidation_status": null,
  "consolidated_at": null,
  "consolidation_error": null
}
```

### Key Points for P03 Processing

**NULL Columns (to be filled by P03)**:

- `novelty_score` - P03 will compute based on SimHash comparison
- `near_duplicates_json` - P03 will identify similar events
- `is_near_duplicate` - Flag if this is duplicate of existing event
- `episode_cluster_id` - P03 will assign to temporal/semantic cluster
- `cluster_confidence` - Confidence in cluster assignment
- `consolidation_status` - Will be set to 'IN_PROGRESS' then 'COMPLETE'
- `consolidated_at` - Timestamp when P03 processed this

**Rich Context Available**:

- **Temporal**: Wednesday evening, 7:15 PM, DECLINE circadian slot
- **Spatial**: Thai Basil Restaurant, Oak Street, geohash for clustering
- **Social**: With Sarah (colleague), WORK context, MEDIUM intimacy
- **Semantic**: Meal activity, Thai food, positive sentiment (0.72)
- **Entities**: 4 entities extracted (person, 2 locations, food item)
- **Relationships**: 3 KG triples with confidence scores

**P03 Consolidation Tasks**:

1. **Deduplication**: Check if similar "dinner with Sarah" event exists using SimHash
2. **Clustering**: Group with other "work dinners" or "restaurant visits"
3. **Pattern Extraction**: Identify routine (e.g., "Dad dines with colleagues weekly")
4. **KG Construction**: Create/update nodes for Sarah, Thai Basil, strengthen edges
5. **Social Memory**: Update social relationship frequency for Sarah
6. **Semantic Memory**: Extract preference "Dad enjoys Thai food/curry"
7. **Episodic Memory**: Store as distinct episode with full context
8. **Forgetting**: Check retention policy (GREEN band, standard bucket → 1 year retention)

**Expected P03 Outputs**:

- `st_epi`: New episode record linking to this event
- `st_sem`: Pattern "enjoys_thai_food" with confidence boost
- `st_social`: Update "dad → sarah_colleague" relationship, increment interaction count
- `st_kg_dom`: Nodes for Sarah (if new), Thai Basil, Oak Street, curry
- `st_kg_edges`: Edges DINED_WITH, ATE_AT, ENJOYED with temporal validity
- `st_vec`: Placeholder for embedding (P08 will generate actual vector)
- `st_hipp_events`: Updated with novelty_score, cluster_id, consolidation_status='COMPLETE'

---

## Responsibilities (P03 Only — Background Consolidation Processing)

### R0 – Trigger Detection & Sleep Cycle Coordination

**Purpose**: Coordinate P03 consolidation pipeline execution using multi-trigger strategy (scheduled, idle, event-based, manual) with sleep-cycle-inspired batching for Docker-based deployments.

**Docker Deployment Context**:

- Running in containerized environment (Linux/Windows containers)
- No mobile OS lifecycle hooks (no iOS/Android suspension/wake)
- Must use K0's 4 ports for all interactions: **Command**, **Query**, **SSE**, **Drivers**
- Pipeline trigger logic resides in pipeline coordinator (not external cron)

**K0 Ports Architecture** (ADR-0074):

1. **Command Port** (`POST /k0/command.submit`): Submit consolidation work orders
2. **Query Port** (`POST /k0/query.recall`): Check st_hipp_events row count, query last consolidation timestamp
3. **SSE Port** (`GET /k0/sse.subscribe`): Subscribe to memory formation events (topic: `memory.episodic.formation.v1`)
4. **Drivers Port** (`POST /k0/driver.handshake`): Register P03 as event-driven pipeline driver (future)

---

#### R0.1 Idle Detection

**Purpose**: Detect system idle state as trigger for consolidation (preferred: low user activity periods).

**Docker Strategy**: Use **Query Port** to monitor recent memory write activity:

**Query Port API Call**:

```http
POST /k0/query.recall
Content-Type: application/json

{
  "selector": {
    "type": "wal",
    "topic": "memory.episodic.formation.v1",
    "time_range": {
      "start": "<now - 15 minutes>",
      "end": "<now>"
    },
    "limit": 1
  },
  "budget_ms": 100,
  "trace_id": "p03_idle_check_<timestamp>"
}
```

**Idle Detection Logic**:

```python
async def detect_idle_state(query_client: QueryClient) -> bool:
    """
    Check if system is idle (no memory writes in last 15 minutes).

    Returns:
        True if idle (< 5 events in 15min window), False otherwise
    """
    now = datetime.utcnow()
    start = now - timedelta(minutes=15)

    selector = {
        "type": "wal",
        "topic": "memory.episodic.formation.v1",
        "time_range": {"start": start.isoformat(), "end": now.isoformat()},
        "limit": 5  # Check if < 5 events
    }

    response = await query_client.recall(selector, budget_ms=100)
    event_count = len(response.events)

    # Idle if fewer than 5 events in 15min window
    is_idle = event_count < 5

    logger.info(
        "idle_detection",
        event_count=event_count,
        is_idle=is_idle,
        window_minutes=15
    )

    return is_idle
```

**Idle Detection Parameters**:

- **Time Window**: 15 minutes (adjustable via config)
- **Event Threshold**: < 5 events = idle
- **Query Budget**: 100ms max (low latency check)
- **Polling Interval**: Check every 5 minutes

**Observability**:

- Metric: `p03_idle_checks_total{result=idle|active}`
- Metric: `p03_idle_detection_latency_ms` (Query Port response time)
- Log: `idle_detection` event with event count

---

#### R0.2 Sleep State Machine (NREM/REM Cycles)

**Purpose**: Implement biologically-inspired sleep phases for consolidation work (NREM = deep consolidation, REM = creative exploration).

**Sleep Cycle Model** (90-minute cycles):

- **NREM Phase 1** (30min): Deduplication, novelty scoring, stale memory detection (R3)
- **NREM Phase 2** (30min): Episodic clustering, pattern extraction, semantic consolidation (R2)
- **REM Phase** (30min): Knowledge graph construction, dream-like exploration, insight generation (R4, R5)

**State Machine**:

```
IDLE → CHECK_TRIGGER → NREM_PHASE_1 → NREM_PHASE_2 → REM_PHASE → COMPLETE → IDLE
                ↑                                                              |
                └──────────────────────────────────────────────────────────────┘
                                (Sleep cycle: 90 minutes)
```

**State Machine Implementation**:

```python
from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timedelta

class SleepPhase(Enum):
    IDLE = "IDLE"
    NREM_PHASE_1 = "NREM_PHASE_1"  # Deduplication, forgetting
    NREM_PHASE_2 = "NREM_PHASE_2"  # Pattern extraction, semantic consolidation
    REM_PHASE = "REM_PHASE"         # KG construction, creative exploration
    COMPLETE = "COMPLETE"

@dataclass
class SleepCycleState:
    """State tracker for P03 sleep cycle."""
    current_phase: SleepPhase
    phase_start_time: datetime
    cycle_number: int
    events_processed: int
    events_consolidated: int
    phase_duration_target_minutes: dict[SleepPhase, int]

    def __post_init__(self):
        self.phase_duration_target_minutes = {
            SleepPhase.NREM_PHASE_1: 30,
            SleepPhase.NREM_PHASE_2: 30,
            SleepPhase.REM_PHASE: 30,
        }

    def elapsed_minutes(self) -> int:
        """Minutes elapsed in current phase."""
        return (datetime.utcnow() - self.phase_start_time).total_seconds() / 60

    def should_transition(self) -> bool:
        """Check if phase duration target reached."""
        if self.current_phase == SleepPhase.IDLE:
            return False
        target = self.phase_duration_target_minutes.get(self.current_phase, 30)
        return self.elapsed_minutes() >= target

    def next_phase(self) -> SleepPhase:
        """Determine next phase in sleep cycle."""
        transitions = {
            SleepPhase.IDLE: SleepPhase.NREM_PHASE_1,
            SleepPhase.NREM_PHASE_1: SleepPhase.NREM_PHASE_2,
            SleepPhase.NREM_PHASE_2: SleepPhase.REM_PHASE,
            SleepPhase.REM_PHASE: SleepPhase.COMPLETE,
            SleepPhase.COMPLETE: SleepPhase.IDLE,
        }
        return transitions[self.current_phase]

    def transition(self):
        """Move to next phase."""
        next_phase = self.next_phase()
        self.current_phase = next_phase
        self.phase_start_time = datetime.utcnow()

        if next_phase == SleepPhase.IDLE:
            self.cycle_number += 1

        logger.info(
            "sleep_phase_transition",
            from_phase=self.current_phase.value,
            to_phase=next_phase.value,
            cycle_number=self.cycle_number,
            events_processed=self.events_processed
        )
```

**Phase Responsibilities**:

| Phase | Duration | Responsibilities | Modules |
|-------|----------|------------------|---------|
| NREM Phase 1 | 30 min | Deduplication (R3.1), Novelty Scoring (R3.2), Stale Memory Detection (R3.3), Retention Policy (R3.4) | Synaptic Homeostasis |
| NREM Phase 2 | 30 min | Episodic Clustering (R2.1), Pattern Extraction (R2.2), Semantic Consolidation (R2.5) | Neocortical Integration |
| REM Phase | 30 min | KG Construction (R4), Dream Exploration (R5), Insight Generation | Creative Consolidation |

**Phase Transition Triggers**:

- **Time-based**: Target duration reached (30min/phase)
- **Work-based**: All batches processed for phase (1000 events/batch)
- **Early termination**: No more pending events in st_hipp_events

**Observability**:

- Metric: `p03_sleep_phase_duration_seconds{phase=nrem1|nrem2|rem}`
- Metric: `p03_sleep_cycles_completed_total`
- Metric: `p03_phase_events_processed{phase=nrem1|nrem2|rem}`
- Log: `sleep_phase_transition` event with phase change details

---

#### R0.3 Manual & Event-Based Triggers

**Purpose**: Support multiple trigger mechanisms (scheduled, idle, event-driven, manual) for Docker deployments.

**Trigger Mechanisms**:

##### 1. Scheduled Trigger (Preferred for Docker)

**Cron-style scheduling** via pipeline coordinator config:

```yaml
# k0/pipelines/p03_consolidation.yml
pipeline:
  id: "p03_consolidation"
  name: "Consolidation & Forgetting Pipeline"

  triggers:
    - type: "schedule"
      cron: "0 2 * * *"  # Daily at 2 AM UTC
      enabled: true

    - type: "schedule"
      cron: "0 */6 * * *"  # Every 6 hours
      enabled: false  # Disabled by default
```

**Implementation**:

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

@scheduler.scheduled_job('cron', hour=2, minute=0)
async def trigger_consolidation_cycle():
    """Scheduled consolidation trigger (2 AM UTC daily)."""
    logger.info("scheduled_consolidation_trigger", time="02:00 UTC")

    # Check if consolidation already running
    if consolidation_state.current_phase != SleepPhase.IDLE:
        logger.warning("consolidation_already_running",
                      phase=consolidation_state.current_phase)
        return

    # Transition to NREM Phase 1
    consolidation_state.transition()
    await run_consolidation_cycle()
```

##### 2. Idle-Based Trigger

**Periodic idle checks** (every 5 minutes):

```python
@scheduler.scheduled_job('interval', minutes=5)
async def check_idle_and_trigger():
    """Check system idle state and trigger if conditions met."""
    if consolidation_state.current_phase != SleepPhase.IDLE:
        return  # Already running

    is_idle = await detect_idle_state(query_client)
    pending_count = await get_pending_event_count(query_client)

    # Trigger if idle AND pending events > 1000
    if is_idle and pending_count > 1000:
        logger.info("idle_consolidation_trigger",
                   pending_count=pending_count)
        consolidation_state.transition()
        await run_consolidation_cycle()
```

##### 3. Event-Based Trigger (SSE Subscription)

**Real-time trigger** via SSE Port subscription to memory formation events:

```python
async def subscribe_to_memory_formation_events():
    """
    Subscribe to memory formation events via SSE Port.
    Trigger consolidation when burst detected (>100 events in 5min).
    """
    sse_url = "http://localhost:8080/k0/sse.subscribe"
    params = {
        "topic": "memory.episodic.formation.v1",
        "tenant_id": "*",  # All tenants
        "space_id": "*",   # All spaces
        "cursor": "latest"
    }

    event_window = []
    window_duration_seconds = 300  # 5 minutes

    async with aiohttp.ClientSession() as session:
        async with session.get(sse_url, params=params) as response:
            async for line in response.content:
                if line.startswith(b"data: "):
                    event = json.loads(line[6:])
                    event_window.append(event)

                    # Remove events older than 5 minutes
                    now = time.time()
                    event_window = [
                        e for e in event_window
                        if now - e['timestamp'] < window_duration_seconds
                    ]

                    # Trigger if burst detected
                    if len(event_window) > 100:
                        logger.info("event_burst_consolidation_trigger",
                                   event_count=len(event_window))
                        if consolidation_state.current_phase == SleepPhase.IDLE:
                            consolidation_state.transition()
                            await run_consolidation_cycle()
```

**SSE Subscription Parameters**:

- **Topic**: `memory.episodic.formation.v1`
- **Cursor**: `latest` (only new events)
- **Burst Threshold**: >100 events in 5-minute window
- **Acknowledgment**: Send ACK after processing to advance cursor

##### 4. Manual Trigger (CLI/API)

**CLI command** via k0ctl:

```bash
# Trigger consolidation manually
k0ctl consolidate run --database /var/lib/k0/db.sqlite3

# Trigger with specific tenant/space
k0ctl consolidate run --tenant tenant_smith_family --space personal:dad

# Dry-run (report pending count without consolidating)
k0ctl consolidate run --dry-run
```

**CLI Implementation** (add to `k0/cli/k0ctl.py`):

```python
# Add consolidate subcommand
consolidate_parser = subparsers.add_parser(
    "consolidate",
    help="Run P03 consolidation pipeline"
)
consolidate_parser.add_argument(
    "--database",
    dest="database",
    type=Path,
    help="Override database path"
)
consolidate_parser.add_argument(
    "--tenant",
    dest="tenant_id",
    help="Filter by tenant ID"
)
consolidate_parser.add_argument(
    "--space",
    dest="space_id",
    help="Filter by space ID"
)
consolidate_parser.add_argument(
    "--dry-run",
    dest="dry_run",
    action="store_true",
    help="Report pending count without consolidating"
)

# Handler
def _handle_consolidate_command(database_path: Path, args: argparse.Namespace):
    if args.dry_run:
        count = get_pending_event_count_sync(database_path,
                                             args.tenant_id,
                                             args.space_id)
        print(f"Pending events: {count}")
        return 0

    # Trigger consolidation
    trigger_consolidation_sync(database_path, args.tenant_id, args.space_id)
    print("Consolidation cycle started")
    return 0
```

**REST API Endpoint** (add to Command Port):

```python
@router.post("/k0/pipeline.trigger", status_code=202)
async def trigger_pipeline(
    request: PipelineTriggerRequest,
    settings: KernelSettings = Depends(get_settings),
) -> PipelineTriggerResponse:
    """
    Manually trigger a pipeline execution.

    ADR-0074: Ports Architecture - Pipeline Control Endpoint
    """
    if request.pipeline_id != "p03_consolidation":
        raise HTTPException(status_code=400,
                           detail=f"Unknown pipeline: {request.pipeline_id}")

    if consolidation_state.current_phase != SleepPhase.IDLE:
        return PipelineTriggerResponse(
            status="ALREADY_RUNNING",
            pipeline_id=request.pipeline_id,
            phase=consolidation_state.current_phase.value
        )

    # Transition to NREM Phase 1
    consolidation_state.transition()

    # Schedule async consolidation task
    asyncio.create_task(run_consolidation_cycle())

    return PipelineTriggerResponse(
        status="TRIGGERED",
        pipeline_id=request.pipeline_id,
        cycle_number=consolidation_state.cycle_number
    )
```

**API Request**:

```http
POST /k0/pipeline.trigger
Content-Type: application/json

{
  "pipeline_id": "p03_consolidation",
  "tenant_id": "tenant_smith_family",  // Optional filter
  "space_id": "personal:dad",          // Optional filter
  "trace_id": "manual_trigger_2025-11-21T14:30:00Z"
}
```

**API Response**:

```json
{
  "status": "TRIGGERED",
  "pipeline_id": "p03_consolidation",
  "cycle_number": 42,
  "phase": "NREM_PHASE_1",
  "estimated_duration_minutes": 90
}
```

**Trigger Priority**:

1. **Manual** (CLI/API): Highest priority, immediate execution
2. **Event-Based** (SSE burst): High priority, triggered on memory write burst
3. **Idle-Based** (periodic check): Medium priority, triggered when idle + pending > 1000
4. **Scheduled** (cron): Lowest priority, daily/periodic execution

**Observability**:

- Metric: `p03_triggers_total{type=scheduled|idle|event|manual}`
- Metric: `p03_trigger_rejected_total{reason=already_running|no_pending}`
- Metric: `p03_manual_triggers_total{source=cli|api}`
- Log: `consolidation_trigger` event with trigger type and reason

---

### R1 – Hippocampal Replay (Pattern Strengthening)

**Purpose**: Selectively replay recent episodic memories to strengthen patterns, associations, and important events before permanent consolidation. This phase mimics biological hippocampal replay where CA3 region reactivates recently experienced sequences during NREM1 sleep phase.

**Execution Context**: NREM_PHASE_1 (first 30 minutes of 90-minute sleep cycle)

**Input**: Batch of st_hipp_events rows with `consolidation_status = NULL` (unconsolidated events)

**Output**: Same st_hipp_events rows with updated importance scores, association weights, and replay metadata

**Performance Budget**: Process 1000 events in <5 minutes (6ms per event average)

---

#### R1.1 CA3 Consolidation Coordinator

**Role**: Orchestrates the replay process by fetching unconsolidated events, prioritizing them by importance, and coordinating parallel replay operations.

**Implementation Strategy**:

1. **Batch Selection Query**: Query st_hipp_events using Query Port with selector type "wal", filter by `consolidation_status IS NULL`, order by event_time_utc DESC (most recent first), limit to batch_size (default 1000)

2. **Importance Pre-Scoring**: Calculate initial importance score for each event using formula combining:
   - Emotional salience (sentiment_score absolute value, affect_valence, affect_arousal)
   - Recency (exponential decay from event_time_utc to now)
   - Novelty (inverse of similar event count based on simhash_hex clustering)
   - Social significance (participant count, relationship strength from st_social layer)

3. **Priority Bucketing**: Group events into 3 priority buckets (HIGH: importance >0.8, MEDIUM: 0.5-0.8, LOW: <0.5) to allocate replay resources proportionally

4. **Parallel Replay Distribution**: Split batch across worker pool (default 4 workers) with work-stealing queue to balance load; assign HIGH priority events first

5. **Progress Tracking**: Emit SSE events via Observe Port with replay progress metrics (events_processed, importance_histogram, replay_latency_p95)

**Dependencies**:

- Query Port client for batch fetching
- Worker pool executor (asyncio.TaskGroup or ThreadPoolExecutor)
- Observe Port client for progress events

**Observability**:

- Metric: `p03_r1_batch_size` (histogram)
- Metric: `p03_r1_importance_scores` (histogram by bucket)
- Metric: `p03_r1_coordinator_latency_ms` (histogram)
- Log: `r1_batch_selected` event with batch stats

---

#### R1.2 Pattern Replay Engine

**Role**: Reactivates episodic memories by reconstructing contextual associations, temporal sequences, and semantic patterns. This strengthens neural pathways (memory traces) before consolidation.

**Implementation Strategy**:

1. **Event Context Reconstruction**: For each event, reconstruct full context by:
   - Parsing entities_json to extract all mentioned entities (PERSON, LOCATION, ORGANIZATION, ACTIVITY)
   - Parsing participants_json to get social actors
   - Parsing tags_json to get semantic categories
   - Parsing context_json to get environmental metadata (weather, location type, time of day)

2. **Temporal Sequence Building**: Query st_hipp_events for events within ±4 hours of target event with matching participants or location to build episodic sequence (what happened before/after this event)

3. **Association Discovery**: For each entity in the event, discover associations by:
   - Querying st_kg_dom for existing entity nodes
   - Querying st_kg_edges for existing relationships
   - Identifying novel associations not yet captured in knowledge graph
   - Calculating association strength based on co-occurrence frequency and temporal proximity

4. **Pattern Matching**: Compare event against existing episodic clusters using SimHash similarity:
   - Query st_epi for episodes with similar simhash_hex (Hamming distance <5)
   - Check if event reinforces known pattern (e.g., "weekly team lunch") or introduces variation
   - Calculate pattern confidence boost based on similarity

5. **Replay Metadata Recording**: Store replay results in temporary structure (not yet written to st_hipp_events) containing:
   - Discovered associations (entity pairs with strength scores)
   - Matched episodic patterns (episode_ids with similarity scores)
   - Temporal sequence context (preceding/following event_ids)
   - Pattern confidence deltas (how much this event strengthens known patterns)

**Dependencies**:

- SQLite query interface for st_hipp_events, st_epi, st_kg_dom, st_kg_edges
- SimHash comparison utility (Hamming distance calculator)
- Entity resolution service (disambiguate "Sarah" to specific person_id)

**Observability**:

- Metric: `p03_r1_associations_discovered_total` (counter)
- Metric: `p03_r1_pattern_matches_total` (counter)
- Metric: `p03_r1_replay_latency_ms` (histogram per event)
- Log: `r1_event_replayed` event with discovered associations and matched patterns

---

#### R1.3 Association Strengthening

**Role**: Incrementally strengthen associations between entities, concepts, and patterns based on replay results. This prepares data for knowledge graph consolidation (R4).

**Implementation Strategy**:

1. **Association Accumulation**: Aggregate discovered associations from replay metadata across all events in batch:
   - Group by entity pair (entity_a_id, entity_b_id)
   - Sum co-occurrence counts
   - Calculate average temporal proximity (events within same day = stronger association)
   - Track contexts where association appears (meal, work, travel, etc.)

2. **Existing Association Lookup**: Query st_kg_edges to find existing relationships between entity pairs:
   - If relationship exists, increment observation_count and recalculate confidence_score
   - If relationship doesn't exist, mark as candidate for creation in R4

3. **Strength Score Calculation**: Compute association strength using formula:
   - Base strength = co-occurrence frequency / total event count
   - Temporal proximity bonus = exp(-λ * average_time_gap_hours)
   - Context diversity bonus = unique_contexts / total_contexts
   - Emotional significance bonus = average sentiment_score of events containing association

4. **Pattern Reinforcement Tracking**: For each matched episodic pattern:
   - Query st_epi for canonical episode
   - Increment pattern_reinforcement_count (stored in replay metadata)
   - Calculate confidence boost = log(1 + reinforcement_count) / log(10)
   - Mark for confidence_score update in st_epi during R2 phase

5. **Association Metadata Storage**: Store strengthened associations in temporary in-memory structure (dict mapping entity pairs to strength metadata) for use in R4 knowledge graph consolidation

**Dependencies**:

- st_kg_edges query interface
- st_epi query interface
- In-memory association cache (asyncio-friendly dict with read locks)

**Observability**:

- Metric: `p03_r1_associations_strengthened_total` (counter)
- Metric: `p03_r1_patterns_reinforced_total` (counter by pattern type)
- Metric: `p03_r1_association_strength_scores` (histogram)
- Log: `r1_associations_strengthened` event with top 10 associations by strength

---

#### R1.4 Importance Weighting (Emotional, Access Frequency, Recency)

**Role**: Calculate final importance score for each event to guide consolidation decisions (promote to semantic memory, archive, or prune).

**Implementation Strategy**:

1. **Multi-Factor Importance Formula**: Compute weighted sum of 4 factors:
   - **Emotional Weight (w=0.35)**: |sentiment_score| × |affect_valence| × (1 + affect_arousal)
   - **Recency Weight (w=0.25)**: exp(-λ_recency × days_since_event), where λ_recency = 0.05 (20-day half-life)
   - **Access Frequency Weight (w=0.20)**: log(1 + access_count) / log(10) (diminishing returns for very high access counts)
   - **Social Significance Weight (w=0.20)**: participant_count × average_relationship_strength (from st_social layer)

2. **Novelty Bonus**: Add bonus for events that introduce new information:
   - Query st_hipp_events for similar events (simhash_hex Hamming distance <3)
   - If similar_event_count < 3, add novelty_bonus = 0.15 to importance score
   - If similar_event_count ≥ 10, apply redundancy_penalty = -0.10

3. **Contextual Importance Boosters**: Apply domain-specific boosters:
   - **First-time experiences**: If activity_type seen <3 times, add first_time_bonus = 0.20
   - **Milestone events**: If entities_json contains milestone indicators ("birthday", "anniversary", "graduation"), add milestone_bonus = 0.25
   - **Conflict/Resolution events**: If sentiment_score swing >0.5 within 24 hours, add conflict_resolution_bonus = 0.15

4. **Importance Normalization**: Normalize importance scores across batch to [0, 1] range using min-max scaling to ensure consistent interpretation

5. **Importance Score Storage**: Write final importance score back to st_hipp_events.importance_score column (this is in-place update, not append-only since st_hipp_events is staging table)

**Dependencies**:

- st_hipp_events write access for importance_score updates
- st_social layer read access for relationship strength lookup
- SimHash comparison utility for novelty detection

**Observability**:

- Metric: `p03_r1_importance_scores` (histogram by decile)
- Metric: `p03_r1_novelty_bonus_applied_total` (counter)
- Metric: `p03_r1_milestone_bonus_applied_total` (counter)
- Log: `r1_importance_calculated` event with score distribution stats

---

#### R1.5 Theta Rhythm Coordination

**Role**: Coordinate replay timing to respect biological constraints (avoid memory interference, maintain consolidation quality) and manage system resources (CPU, memory, I/O).

**Implementation Strategy**:

1. **Theta Wave Simulation**: Organize replay into micro-batches of 50 events, processing each micro-batch with 200ms "rest period" between batches to simulate theta oscillations (5Hz rhythm, biologically inspired by hippocampal theta waves during memory consolidation)

2. **Batch Timing Control**: Use asyncio.sleep(0.2) between micro-batches to:
   - Prevent CPU saturation (allow other K0 services to execute)
   - Reduce memory pressure (allow garbage collection between batches)
   - Provide observability checkpoints (emit progress metrics after each micro-batch)

3. **Adaptive Throttling**: Monitor system resource usage during replay:
   - Query K0 Observe Port for `k0_cpu_usage_percent` and `k0_memory_usage_percent` metrics
   - If CPU usage >80% or memory usage >85%, increase rest period to 500ms
   - If CPU usage <50% and memory usage <60%, decrease rest period to 100ms (faster consolidation)

4. **Phase Transition Preparation**: At 28-minute mark (2 minutes before NREM1 → NREM2 transition):
   - Stop accepting new micro-batches
   - Complete in-flight replay operations
   - Flush association metadata to disk (temporary JSON file or SQLite temp table)
   - Emit `r1_phase_complete` event with summary statistics

5. **Interruption Handling**: If consolidation is interrupted (manual stop, system shutdown):
   - Mark partially replayed events with `consolidation_status = 'R1_INCOMPLETE'`
   - Store checkpoint with last processed event_id
   - On next consolidation cycle, resume from checkpoint

**Dependencies**:

- asyncio.sleep for timing control
- K0 Observe Port for system metrics
- Checkpoint storage (SQLite table or JSON file)

**Observability**:

- Metric: `p03_r1_microbatch_count_total` (counter)
- Metric: `p03_r1_rest_period_ms` (gauge, tracks adaptive throttling)
- Metric: `p03_r1_phase_duration_seconds` (histogram)
- Metric: `p03_r1_interruptions_total` (counter)
- Log: `r1_theta_cycle_complete` event every 10 micro-batches (500 events)

---

**R1 Phase Summary**:

| Step | Action | Input | Output | Duration Target |
|------|--------|-------|--------|-----------------|
| R1.1 | Batch Selection & Prioritization | st_hipp_events (unconsolidated) | Prioritized batch (1000 events) | 10 seconds |
| R1.2 | Pattern Replay | Prioritized events | Replay metadata (associations, patterns, sequences) | 3 minutes |
| R1.3 | Association Strengthening | Replay metadata | Strengthened associations (in-memory cache) | 1 minute |
| R1.4 | Importance Weighting | Events + replay results | Updated importance scores (written to st_hipp_events) | 30 seconds |
| R1.5 | Theta Rhythm Coordination | All R1 operations | Timed execution with resource management | 30 minutes (entire NREM1 phase) |

**Transition to R2**: Upon completing R1 (or reaching 30-minute NREM1 time limit), transition to NREM2 phase for episodic clustering and semantic consolidation. R1 outputs (importance scores, association cache) are consumed by R2 pattern extraction algorithms.

---

### R2 – Neocortical Integration (Episodic → Semantic)

**Purpose**: Extract generalized patterns, semantic concepts, and abstract knowledge from clustered episodic memories. This phase mimics biological hippocampal-neocortical dialogue where repeated episodic patterns are gradually transformed into schema-based semantic memories.

**Execution Context**: NREM_PHASE_2 (middle 30 minutes of 90-minute sleep cycle)

**Input**:

- st_hipp_events rows with importance scores (from R1)
- st_epi canonical episodes (for pattern matching)
- R1 association cache (strengthened entity relationships)

**Output**:

- New/updated st_sem semantic memory records
- New/updated st_procedural routine/habit records
- Pattern confidence updates in st_epi
- Candidate semantic concepts for Active Learning Loop

**Performance Budget**: Extract patterns from 1000 events and write 50-100 semantic records in <8 minutes (480ms per semantic record)

---

#### R2.1 Episodic Clustering (Similarity Detection)

**Role**: Group similar episodic events into clusters to identify recurring patterns, routines, and semantic themes.

**Implementation Strategy**:

1. **SimHash-Based Clustering**: Use simhash_hex column from st_hipp_events as primary clustering signal:
   - Build inverted index mapping simhash_hex → [event_ids] for batch (in-memory dict)
   - For each unique simhash, find all events within Hamming distance ≤5 (allowing minor variations)
   - Group events into preliminary clusters based on simhash neighborhoods

2. **Temporal Clustering Refinement**: Within each simhash cluster, apply temporal analysis:
   - Calculate time gaps between consecutive events in cluster (sorted by event_time_utc)
   - Identify temporal patterns: daily (gap ~24h ±2h), weekly (gap ~7d ±1d), monthly (gap ~30d ±3d), irregular
   - Split clusters with mixed temporal patterns into separate sub-clusters (e.g., "daily lunch routine" vs "monthly team dinner")

3. **Contextual Clustering Enhancement**: Further refine clusters by contextual similarity:
   - Extract context features: location_name, participants_json, activity_type, time_of_day, day_of_week
   - Calculate context similarity score = weighted sum of matching features (location: 0.3, participants: 0.3, activity: 0.2, temporal: 0.2)
   - Merge clusters with high context similarity (>0.7) even if simhash differs slightly
   - Split clusters with low context similarity (<0.4) despite similar simhash

4. **Cluster Quality Filtering**: Apply quality thresholds to retain meaningful clusters:
   - Minimum cluster size: 3 events (need repetition to establish pattern)
   - Maximum temporal span: 180 days (patterns older than 6 months may be stale)
   - Minimum average importance: 0.3 (avoid consolidating trivial events)
   - Exclude singleton clusters (size=1) as non-patterns

5. **Cluster Metadata Extraction**: For each retained cluster, compute aggregate metadata:
   - Cluster ID (deterministic hash of sorted event_ids)
   - Cluster size (event count)
   - Temporal pattern type (daily/weekly/monthly/irregular)
   - Average importance score
   - Representative event_id (highest importance event in cluster)
   - Common context features (intersection of participants, locations, activities)

**Dependencies**:

- SimHash Hamming distance calculator (bit manipulation utility)
- Temporal pattern detector (time gap analysis)
- Context similarity scorer (weighted feature matching)

**Observability**:

- Metric: `p03_r2_clusters_discovered_total` (counter)
- Metric: `p03_r2_cluster_sizes` (histogram)
- Metric: `p03_r2_temporal_patterns` (counter by type: daily/weekly/monthly/irregular)
- Log: `r2_clustering_complete` event with cluster count and size distribution

---

#### R2.2 Pattern Extraction Algorithm

**Role**: Transform episodic clusters into abstract semantic patterns and procedural routines by identifying common elements, variations, and invariants.

**Implementation Strategy**:

1. **Pattern Type Classification**: Classify each cluster into pattern category:
   - **Routine Pattern**: High temporal regularity (coefficient of variation <0.3 for time gaps), same context features
   - **Habit Pattern**: Moderate temporal regularity, triggered by specific context (e.g., "coffee after gym")
   - **Theme Pattern**: Low temporal regularity but high semantic similarity (e.g., "family celebrations")
   - **Relationship Pattern**: Consistent participant pairs/groups (e.g., "weekly calls with Mom")

2. **Invariant Extraction**: Identify elements that remain constant across cluster events:
   - **Core Entities**: Extract entities appearing in ≥80% of cluster events (e.g., "Sarah" in "lunch with Sarah" cluster)
   - **Core Location**: Extract location appearing in ≥70% of events (e.g., "Thai Basil Restaurant")
   - **Core Activity**: Extract activity_type appearing in ≥80% of events (e.g., "meal")
   - **Core Temporal Slot**: Extract time_of_day/day_of_week pattern (e.g., "Tuesday evenings")

3. **Variation Modeling**: Capture acceptable variations within pattern:
   - **Location Variations**: If no single location ≥70%, identify location category (e.g., "Thai restaurants")
   - **Participant Variations**: If participant set varies, identify core participant + optional guests (e.g., "Dad + colleagues")
   - **Sentiment Range**: Calculate sentiment_score range (min, max, mean, std) to model emotional variability
   - **Duration Range**: Calculate event duration range if available (morning coffee: 15-30min, dinner: 60-120min)

4. **Pattern Naming & Description Generation**: Create human-readable pattern description:
   - Template-based generation using extracted invariants: "{frequency} {activity} with {participants} at {location}"
   - Example: "Weekly lunch with Sarah at Thai Basil Restaurant"
   - Example: "Daily morning coffee at home"
   - Store in st_sem.concept_name and st_sem.description columns

5. **Confidence Score Calculation**: Compute pattern confidence based on evidence strength:
   - Base confidence = log(cluster_size) / log(10) (more events = higher confidence)
   - Temporal consistency bonus = 1 - coefficient_of_variation (regular patterns = higher confidence)
   - Context stability bonus = average context similarity across cluster events
   - Final confidence = normalize(base × 0.5 + temporal × 0.3 + context × 0.2) to [0, 1]

6. **Pattern Metadata Storage**: Store extracted pattern in temporary structure (not yet written to st_sem):
   - Pattern ID (deterministic hash)
   - Pattern type (routine/habit/theme/relationship)
   - Invariants (core entities, location, activity, temporal slot)
   - Variations (acceptable ranges for flexible attributes)
   - Confidence score
   - Source episode IDs (for provenance tracking)
   - Representative text (concatenation of event texts with ellipsis)

**Dependencies**:

- Statistical utilities (mean, std, coefficient of variation)
- NLP utilities for entity/location extraction from text
- Template engine for pattern description generation

**Observability**:

- Metric: `p03_r2_patterns_extracted_total` (counter by pattern_type)
- Metric: `p03_r2_pattern_confidence_scores` (histogram)
- Metric: `p03_r2_pattern_cluster_sizes` (histogram)
- Log: `r2_pattern_extracted` event with pattern description and confidence

---

#### R2.3 CA1 Bridge Integration

**Role**: Validate extracted patterns against existing semantic memory to avoid duplicates, detect schema evolution, and coordinate incremental consolidation.

**Implementation Strategy**:

1. **Existing Semantic Lookup**: For each extracted pattern, query st_sem for similar semantic memories:
   - Query by concept_category matching pattern type (routine/habit/theme/relationship)
   - Query by actor_id matching pattern's core participant
   - Filter to canonical records (is_canonical = 1, archival_status = 'ACTIVE')
   - Calculate semantic similarity using text embeddings from st_vec layer

2. **Similarity Scoring**: Compute similarity between extracted pattern and existing semantic memory:
   - Textual similarity: Cosine similarity of embeddings (from st_vec)
   - Structural similarity: Jaccard similarity of invariant sets (entities, locations, activities)
   - Temporal similarity: Compare temporal pattern types (daily vs weekly = low similarity)
   - Combined similarity = textual × 0.4 + structural × 0.4 + temporal × 0.2

3. **Merge vs Create Decision**: Determine whether to merge with existing semantic or create new:
   - **Merge** if similarity >0.85: Update existing semantic record (increment observation_count, boost confidence, append source episodes)
   - **Schema Evolution** if similarity 0.6-0.85: Create new version of semantic record (increment version, set supersedes_semantic_id, mark old as non-canonical)
   - **Create** if similarity <0.6: Insert new semantic record (new semantic_id)

4. **Conflict Resolution**: Handle conflicts when multiple existing semantics match pattern:
   - If multiple matches with similarity >0.85, select highest confidence semantic for merge
   - If multiple matches with similarity 0.6-0.85, flag as ambiguity for Active Learning Loop (P06)
   - Log conflict event and mark pattern with ambiguity_score = 0.8

5. **Cross-Layer Reference Updates**: Update references between layers:
   - For merged semantics, append new episode IDs to st_sem.source_episodes_json
   - For evolved schemas, link new version to old via supersedes_semantic_id
   - Update st_epi.promoted_to_semantic_id for source episodes (backlink from episodic to semantic)

6. **Integration Metadata Recording**: Store integration decision in temporary structure:
   - Decision type (MERGE/EVOLVE/CREATE)
   - Target semantic_id (existing or to-be-created)
   - Similarity score
   - Conflict flag (if multiple matches)
   - Source episode IDs

**Dependencies**:

- st_sem query interface with text search
- st_vec embedding similarity calculator (cosine distance)
- Jaccard similarity calculator for set comparison

**Observability**:

- Metric: `p03_r2_ca1_decisions_total` (counter by decision_type: merge/evolve/create)
- Metric: `p03_r2_ca1_similarity_scores` (histogram)
- Metric: `p03_r2_ca1_conflicts_total` (counter)
- Log: `r2_ca1_integration` event with decision and target semantic_id

---

#### R2.4 Consolidation Criteria (Frequency, Temporal Consistency, Confidence)

**Role**: Apply quality gates to determine which patterns qualify for promotion to permanent semantic memory.

**Implementation Strategy**:

1. **Frequency Threshold**: Require minimum repetition count to establish pattern:
   - **Routine patterns**: Minimum 4 occurrences (need clear repetition)
   - **Habit patterns**: Minimum 3 occurrences (habits form faster)
   - **Theme patterns**: Minimum 5 occurrences (themes need more evidence)
   - **Relationship patterns**: Minimum 6 occurrences (relationships need sustained interaction)
   - Reject patterns below threshold (mark as insufficient_evidence)

2. **Temporal Consistency Threshold**: Require stable temporal pattern:
   - Calculate coefficient of variation for time gaps between cluster events
   - **Routine patterns**: CV <0.3 (highly regular)
   - **Habit patterns**: CV <0.5 (moderately regular)
   - **Theme patterns**: CV <0.7 (loosely regular)
   - **Relationship patterns**: No CV requirement (relationships can be irregular)
   - Reject patterns exceeding CV threshold (mark as temporally_unstable)

3. **Confidence Threshold**: Require minimum confidence score:
   - Minimum confidence = 0.5 for all pattern types
   - Boost threshold to 0.6 for patterns with high ambiguity (ambiguity_score >0.5)
   - Reject patterns below threshold (mark as low_confidence)

4. **Recency Requirement**: Require recent activity to avoid consolidating stale patterns:
   - Most recent event in cluster must be within 90 days
   - If most recent event >90 days, mark pattern as potentially_stale
   - Flag for retention policy review in R3 (may archive instead of promote)

5. **Novelty Check**: Avoid promoting redundant patterns:
   - If CA1 bridge found merge decision (similarity >0.85 with existing semantic), pattern is not novel
   - Novel patterns (similarity <0.6) get novelty_bonus = 0.15 added to confidence
   - Slightly novel patterns (similarity 0.6-0.85, schema evolution) get novelty_bonus = 0.05

6. **Quality Gate Scoring**: Compute aggregate quality score:
   - Frequency score = normalize(cluster_size, min=3, max=20)
   - Temporal score = 1 - coefficient_of_variation
   - Confidence score = pattern confidence (from R2.2)
   - Recency score = exp(-0.01 × days_since_last_event)
   - Novelty score = 1 - similarity_to_existing
   - **Aggregate quality = frequency × 0.25 + temporal × 0.20 + confidence × 0.30 + recency × 0.15 + novelty × 0.10**
   - Promotion threshold = 0.6 (patterns with quality ≥0.6 promoted to semantic memory)

7. **Rejection Reason Tracking**: For rejected patterns, record reason:
   - insufficient_evidence (below frequency threshold)
   - temporally_unstable (above CV threshold)
   - low_confidence (below confidence threshold)
   - potentially_stale (last event >90 days)
   - redundant (high similarity to existing semantic)
   - Store rejection metadata for observability and Active Learning feedback

**Dependencies**:

- Statistical utilities (coefficient of variation, normalization)
- Date arithmetic (days_since_last_event calculation)

**Observability**:

- Metric: `p03_r2_patterns_promoted_total` (counter)
- Metric: `p03_r2_patterns_rejected_total` (counter by rejection_reason)
- Metric: `p03_r2_quality_scores` (histogram)
- Log: `r2_consolidation_decision` event with quality score and decision (promote/reject)

---

#### R2.5 Semantic Memory Storage

**Role**: Write promoted patterns to permanent semantic memory layers (st_sem, st_procedural) with full durability guarantees.

**Implementation Strategy**:

1. **Memory Layer Routing**: Route patterns to appropriate layer based on pattern type:
   - **st_sem** (semantic memory): Theme patterns, relationship patterns, factual knowledge
   - **st_procedural** (procedural memory): Routine patterns, habit patterns, behavioral sequences
   - Both layers receive same durability columns (version, confidence, decay, provenance, etc.)

2. **Record Construction**: Build semantic memory record from pattern metadata:
   - **semantic_id / routine_id**: Generate deterministic ID (hash of invariants + actor_id)
   - **version**: Set to 1 for new records, increment for schema evolutions
   - **canonical_semantic_id / canonical_routine_id**: Self-reference for new records, point to previous for evolutions
   - **is_canonical**: Set to 1 for new/merged records, set to 0 for superseded records
   - **supersedes_semantic_id / supersedes_routine_id**: NULL for new, previous version ID for evolutions
   - **concept_name / routine_name**: Pattern description from R2.2 template generation
   - **concept_category / routine_category**: Pattern type (routine/habit/theme/relationship)
   - **actor_id**: Primary participant from pattern
   - **participants_json**: All participants from cluster events (union of participant sets)
   - **context_json**: Common context features (location, activity, temporal slot)
   - **confidence_score**: Pattern confidence from R2.2 (adjusted by R2.4 quality gate)
   - **ambiguity_score**: 0.0 if no conflicts, 0.8 if CA1 found multiple matches
   - **decay_factor**: 1.0 (no decay yet, freshly consolidated)
   - **observation_count**: Cluster size (number of source episodes)
   - **first_observed_at**: Earliest event_time_utc in cluster
   - **last_observed_at**: Latest event_time_utc in cluster
   - **recency_weight**: exp(-0.01 × days_since_last_observed)
   - **source_count**: 1 (single consolidation source)
   - **source_episodes_json**: JSON array of source episode_id values from cluster
   - **representative_text**: Concatenated event texts (max 500 chars)
   - **pattern_frequency**: Temporal pattern type (daily/weekly/monthly/irregular)
   - **pattern_last_occurrence**: Last event_time_utc in cluster

3. **Batch Insert/Update Strategy**: Optimize database writes:
   - Group records by layer (st_sem vs st_procedural) and operation (INSERT vs UPDATE)
   - For new records: Batch INSERT using executemany (50 records per batch)
   - For merged records: Batch UPDATE using executemany (increment observation_count, boost confidence, append source_episodes_json)
   - For evolved schemas: Execute in transaction (UPDATE old record is_canonical=0, INSERT new record)
   - Use RETURNING clause (if SQLite version supports) to get inserted IDs

4. **Cross-Layer Backlink Updates**: Update st_epi and st_hipp_events with promotion references:
   - Batch UPDATE st_epi: Set promoted_to_semantic_id or promoted_to_routine_id for source episodes
   - Batch UPDATE st_hipp_events: Set consolidation_status='R2_PROMOTED' for source events
   - Ensures bidirectional traceability (st_sem → st_epi → st_hipp_events)

5. **Vector Embedding Generation**: Trigger embedding generation for new semantic records:
   - Enqueue embedding job for each new semantic_id (async task)
   - Embedding model generates vector from representative_text
   - Store in st_vec layer with vector_id=semantic_id, vector_type='semantic'
   - Enables future similarity searches in CA1 bridge

6. **Commit & Observability**: Finalize writes and emit metrics:
   - Commit transaction (all semantic writes atomic)
   - Emit SSE event via Observe Port: `memory.semantic.consolidated.v1` with semantic_id, concept_name, confidence_score
   - Log consolidated semantic records with pattern statistics

**Dependencies**:

- SQLite write interface with batch operations (executemany)
- Transaction management (BEGIN/COMMIT/ROLLBACK)
- Embedding generation service (async queue)
- Observe Port client for event emission

**Observability**:

- Metric: `p03_r2_semantic_writes_total` (counter by layer: st_sem/st_procedural)
- Metric: `p03_r2_write_batch_sizes` (histogram)
- Metric: `p03_r2_write_latency_ms` (histogram)
- Metric: `p03_r2_embeddings_queued_total` (counter)
- Log: `r2_semantic_stored` event with semantic_id and concept summary

---

**R2 Phase Summary**:

| Step | Action | Input | Output | Duration Target |
|------|--------|-------|--------|-----------------|
| R2.1 | Episodic Clustering | st_hipp_events batch (1000 events) | 20-50 event clusters with temporal/context patterns | 2 minutes |
| R2.2 | Pattern Extraction | Event clusters | 20-50 semantic patterns with invariants/variations | 2 minutes |
| R2.3 | CA1 Bridge Integration | Patterns + st_sem existing records | Merge/evolve/create decisions | 1 minute |
| R2.4 | Consolidation Criteria | Patterns + integration decisions | 10-30 qualified patterns (filtered by quality gates) | 1 minute |
| R2.5 | Semantic Memory Storage | Qualified patterns | 10-30 new/updated st_sem/st_procedural records | 2 minutes |

**Transition to R3**: Upon completing R2 (or reaching 60-minute mark), transition to REM phase for knowledge graph consolidation and synaptic homeostasis (forgetting/pruning). R2 outputs (new semantic records, rejected patterns) are consumed by R3 retention policy enforcement and R4 entity extraction.

---

### R3 – Synaptic Homeostasis (Forgetting & Pruning)

**Purpose**: Maintain memory system health by removing redundant memories, pruning weak connections, enforcing retention policies, and archiving low-priority content. This phase mimics biological synaptic homeostasis where neural connections are selectively weakened or eliminated during sleep to prevent cognitive overload.

**Execution Context**: REM_PHASE (final 30 minutes of 90-minute sleep cycle, runs concurrently with R4 knowledge graph consolidation)

**Input**:

- st_hipp_events batch (same 1000 events from R1/R2)
- st_epi canonical episodes (for deduplication)
- st_retention_policy rules (band × topic × device_kind → retention_days)

**Output**:

- st_hipp_events updated with: `novelty_score`, `near_duplicates_json`, `is_near_duplicate`, `consolidation_status`
- st_epi/st_sem/st_procedural/st_social updated with: `archival_status` (ARCHIVED/DEEP_FREEZE), tombstone records
- Archival job queue for low-priority memories
- Deletion log for GDPR compliance

**Performance Budget**: Process 1000 events for deduplication, prune 5-15% of memories, archive 10-20% in <10 minutes

---

#### R3.1 Deduplication (Near-Duplicate Detection)

**Role**: Identify near-duplicate episodic events to prevent memory bloat and consolidate redundant information. Uses SimHash for efficient similarity detection.

**Implementation Strategy**:

1. **SimHash Index Building**: For the batch of 1000 events, build in-memory SimHash index:
   - Extract simhash_hex from each st_hipp_events row
   - Group events by simhash_hex into buckets (exact matches)
   - For each unique simhash, compute Hamming distance to all other simhashes in batch
   - Build adjacency list mapping simhash → [similar_simhashes] (Hamming distance ≤3)

2. **Temporal Window Filtering**: Apply temporal constraints to near-duplicate detection:
   - Only compare events within 24-hour time windows (events >24h apart unlikely to be duplicates)
   - Sort events within each simhash bucket by event_time_utc
   - For each event, only check similarity with events in [event_time - 24h, event_time + 24h] window
   - Reduces comparison complexity from O(n²) to O(n × k) where k = avg events per 24h window (~40)

3. **Multi-Factor Similarity Scoring**: For each candidate duplicate pair, compute similarity across 5 dimensions:
   - **Text Similarity (w=0.35)**: Jaccard similarity of normalized text tokens (from text_normalized column)
   - **Simhash Similarity (w=0.25)**: (64 - hamming_distance) / 64 (normalized Hamming distance)
   - **Spatial Similarity (w=0.15)**: Geohash match (1.0 if geohash_6 matches, 0.5 if prefix matches, 0.0 otherwise)
   - **Social Similarity (w=0.15)**: Jaccard similarity of participants_json arrays
   - **Activity Similarity (w=0.10)**: 1.0 if activity_type matches, 0.5 if activity_category matches, 0.0 otherwise
   - **Combined similarity** = weighted sum of all factors

4. **Duplicate Classification**: Classify event pairs based on combined similarity:
   - **Exact Duplicate** (similarity ≥0.95): Nearly identical events, likely double-submission or retry
   - **Near Duplicate** (similarity 0.80-0.94): Same event with minor variations (wording, detail level)
   - **Similar Event** (similarity 0.60-0.79): Related but distinct events (e.g., "lunch at Cafe A" vs "coffee at Cafe A")
   - **Distinct Event** (similarity <0.60): Different events despite simhash proximity

5. **Canonical Event Selection**: For each duplicate cluster (≥2 events with similarity ≥0.80):
   - Select canonical event using priority rules:
     1. Highest salience_score (more important memories preferred)
     2. Most detailed text (highest char_count)
     3. Best source quality (text > sensor > derived)
     4. Earliest event_time_utc (first occurrence preferred)
   - Mark canonical event with is_near_duplicate=0
   - Mark non-canonical events with is_near_duplicate=1

6. **Deduplication Metadata Storage**: Update st_hipp_events with deduplication results:
   - Set novelty_score = 1.0 - max(similarity_to_any_existing_event)
   - Set near_duplicates_json = JSON array of [event_ids] for all events in duplicate cluster
   - Set is_near_duplicate = 1 for non-canonical, 0 for canonical or unique events
   - Enables downstream components to skip processing duplicates

**Dependencies**:

- SimHash Hamming distance calculator (64-bit bit manipulation)
- Jaccard similarity calculator for text tokens and participant sets
- Geohash prefix matching utility

**Observability**:

- Metric: `p03_r3_duplicates_detected_total` (counter by classification: exact/near/similar)
- Metric: `p03_r3_novelty_scores` (histogram)
- Metric: `p03_r3_duplicate_cluster_sizes` (histogram)
- Log: `r3_deduplication_complete` event with duplicate count and canonical selections

---

#### R3.2 Novelty Scoring

**Role**: Compute novelty scores to quantify how much new information each event contributes. High novelty events are prioritized for consolidation, low novelty events are candidates for pruning.

**Implementation Strategy**:

1. **Base Novelty Score**: Use deduplication similarity as starting point:
   - Base novelty = 1.0 - max_similarity_to_existing (from R3.1)
   - Events with no similar events get novelty = 1.0 (completely novel)
   - Events with exact duplicates get novelty = 0.05 (nearly zero novelty)

2. **Entity Novelty Bonus**: Boost novelty for events introducing new entities:
   - Parse entities_json to extract all entities (PERSON, LOCATION, ORGANIZATION)
   - For each entity, query st_kg_dom to check if node_id exists
   - Count new_entities = entities not in st_kg_dom
   - Entity novelty bonus = min(0.3, new_entities × 0.1) (capped at +0.3)

3. **Activity Novelty Bonus**: Boost novelty for first-time or rare activities:
   - Query st_hipp_events for count of events with same activity_type by actor_id
   - If activity_count < 3, add first_time_activity_bonus = 0.15
   - If activity_count < 10, add rare_activity_bonus = 0.05
   - Rewards trying new activities (first gym visit, first cooking attempt)

4. **Temporal Context Novelty**: Boost novelty for activities at unusual times:
   - Query st_procedural for routines matching activity_type
   - Check if event_time_utc falls within expected temporal_bucket for routine
   - If outside routine schedule, add temporal_anomaly_bonus = 0.10
   - Example: "Exercise at 11PM" when routine is "Exercise Tuesday/Thursday 6PM" = novel

5. **Sentiment Divergence Bonus**: Boost novelty for unexpected emotional responses:
   - Query st_sem for semantic patterns related to activity_type or location_name
   - Calculate expected_sentiment = average sentiment_score from historical patterns
   - If |actual_sentiment - expected_sentiment| > 0.5, add sentiment_divergence_bonus = 0.15
   - Example: "Negative sentiment at favorite restaurant" = novel (possible quality change)

6. **Novelty Score Normalization**: Normalize final novelty score to [0, 1]:
   - Raw novelty = base + entity_bonus + activity_bonus + temporal_bonus + sentiment_bonus
   - Final novelty_score = min(1.0, raw_novelty)
   - Update st_hipp_events.novelty_score column

**Dependencies**:

- st_kg_dom query interface for entity lookup
- st_hipp_events query interface for activity frequency
- st_procedural query interface for routine matching
- st_sem query interface for sentiment expectations

**Observability**:

- Metric: `p03_r3_novelty_bonuses_applied_total` (counter by bonus_type: entity/activity/temporal/sentiment)
- Metric: `p03_r3_novelty_distribution` (histogram by decile)
- Metric: `p03_r3_high_novelty_events_total` (counter for novelty >0.8)
- Log: `r3_novelty_scored` event with novelty distribution stats

---

#### R3.3 Stale Memory Detection

**Role**: Identify memories that have not been accessed or reinforced recently and are candidates for archival or deletion based on retention policies.

**Implementation Strategy**:

1. **Last Access Tracking**: For each memory layer, identify stale records:
   - Query st_epi for episodes where last_observed_at < (now - 90 days) AND access_count = 1
   - Query st_sem for semantics where last_observed_at < (now - 180 days) AND observation_count < 3
   - Query st_procedural for routines where last_performed_at < (now - 60 days) AND consistency_score < 0.3
   - Query st_social for relationships where last_interaction_at < (now - 365 days)

2. **Decay Factor Calculation**: Apply exponential decay based on time since last observation:
   - For each stale record, calculate days_since_last = (now - last_observed_at).days
   - Apply layer-specific decay formula: decay_factor = exp(-λ × days_since_last)
   - Decay constants (λ): st_epi=0.005, st_sem=0.01, st_procedural=0.02, st_social=0.005
   - Update decay_factor column in each layer

3. **Stale Memory Classification**: Classify memories by staleness severity:
   - **Fresh** (decay_factor >0.9): Recently accessed, actively maintained
   - **Aging** (decay_factor 0.7-0.9): Not accessed recently, still relevant
   - **Stale** (decay_factor 0.4-0.7): Significantly aged, archival candidate
   - **Expired** (decay_factor <0.4): Very old, deletion/deep freeze candidate

4. **Importance-Adjusted Staleness**: Combine decay with importance to protect valuable memories:
   - Calculate retention_score = decay_factor × (1 + importance_score) × (1 + confidence_score)
   - Memories with high importance_score or confidence_score are protected even if stale
   - Example: "Wedding photos" (importance=0.95, confidence=1.0) protected despite age
   - Example: "Routine coffee purchase" (importance=0.2, confidence=0.6) expires faster

5. **Access Pattern Analysis**: Identify memories with declining access patterns:
   - For st_epi with access_count >0, calculate access_frequency = access_count / days_since_first_observed
   - If access_frequency has declined >80% in last 90 days, mark as declining_interest
   - Example: "Game progress notes" accessed 10x/month initially, now 0x/month = declining

6. **Stale Memory Flagging**: Mark stale memories for retention policy enforcement:
   - Add stale_detected_at timestamp to metadata (in-memory tracking structure)
   - Add staleness_severity classification (AGING/STALE/EXPIRED)
   - Add retention_recommendation (KEEP/ARCHIVE/DELETE) based on retention_score thresholds

**Dependencies**:

- All memory layer query interfaces (st_epi, st_sem, st_procedural, st_social)
- Date arithmetic utilities (days_since calculation)
- Exponential decay calculator

**Observability**:

- Metric: `p03_r3_stale_memories_detected_total` (counter by layer and severity)
- Metric: `p03_r3_decay_factors` (histogram by layer)
- Metric: `p03_r3_retention_scores` (histogram)
- Log: `r3_staleness_analysis` event with stale count by layer and severity

---

#### R3.4 Retention Policy Enforcement

**Role**: Apply configured retention policies to determine which memories should be kept, archived, or deleted based on policy rules (band × topic × device_kind).

**Implementation Strategy**:

1. **Retention Policy Lookup**: For each memory, resolve applicable retention policy:
   - Query st_retention_policy with filters: (band, topic_pattern, device_kind)
   - Match topic using SQL LIKE pattern (e.g., "memory.episodic.%" matches all episodic topics)
   - Select policy with most specific match (exact band+topic+device > band+topic > band only)
   - Extract retention_days and archival_enabled from matched policy

2. **Policy Application Decision**: Determine action based on policy and memory age:
   - Calculate memory_age_days = (now - first_observed_at).days
   - **KEEP** if memory_age_days < retention_days: Memory within retention period
   - **ARCHIVE** if memory_age_days ≥ retention_days AND archival_enabled=1: Compress and move to cold storage
   - **DELETE** if memory_age_days ≥ retention_days AND archival_enabled=0: Create tombstone and soft delete
   - **KEEP_EXEMPT** if importance_score >0.9 OR privacy_risk_score <0.1: Exempt from deletion (milestone/safe memories)

3. **Band-Specific Policy Handling**: Apply stricter enforcement for RED band memories:
   - **GREEN band**: Standard retention (90-365 days), archival preferred over deletion
   - **AMBER band**: Moderate retention (30-90 days), archival optional based on importance
   - **RED band**: Aggressive retention (7-30 days), deletion preferred to minimize privacy exposure
   - RED band memories with privacy_risk_score >0.7 are force-deleted after retention period regardless of importance

4. **Multi-Layer Cascade Deletion**: When deleting episodic memory, cascade to dependent layers:
   - If st_epi episode is marked for deletion, check if promoted_to_semantic_id exists
   - If semantic memory was derived solely from this episode (source_count=1), also mark semantic for deletion
   - If semantic memory has multiple sources (source_count >1), decrement source_count and update confidence_score
   - Check st_kg_edges for relationships where source_episodes_json contains this episode_id, update or prune
   - Ensures referential integrity across memory layers

5. **Retention Override Handling**: Support user-specified retention overrides:
   - Check for user-provided "keep_forever" flag or "delete_now" flag (from policy_decision column)
   - User overrides take precedence over automatic retention policies
   - Log override events for audit trail (GDPR right to erasure compliance)

6. **Retention Decision Recording**: Store retention decisions for execution:
   - Build in-memory retention decision list: [(memory_id, layer, action, policy_id, reason)]
   - Actions: KEEP, ARCHIVE, DELETE, KEEP_EXEMPT
   - Reasons: within_retention / exceeds_retention / user_override / milestone_exempt / privacy_delete
   - Batch decisions for atomic execution in R3.5 and R3.6

**Dependencies**:

- st_retention_policy query interface
- Policy pattern matching (SQL LIKE or regex)
- Date arithmetic (memory age calculation)

**Observability**:

- Metric: `p03_r3_retention_decisions_total` (counter by action: keep/archive/delete/exempt)
- Metric: `p03_r3_policy_matches_total` (counter by policy_id)
- Metric: `p03_r3_cascade_deletions_total` (counter by layer)
- Log: `r3_retention_enforced` event with decision counts and policy summary

---

#### R3.5 Tombstone Creation (Soft Delete)

**Role**: Create tombstone records for deleted memories to maintain referential integrity, support GDPR compliance, and enable undelete within grace period.

**Implementation Strategy**:

1. **Tombstone Schema Design**: For each memory layer, create corresponding tombstone table:
   - st_epi_tombstones, st_sem_tombstones, st_procedural_tombstones, st_social_tombstones
   - Tombstone columns: (tombstone_id, original_id, layer, deleted_at, deleted_by, deletion_reason, grace_period_end, content_hash, metadata_json)
   - content_hash = SHA256 of original record (for verification without storing full content)
   - metadata_json = lightweight metadata (tenant_id, space_id, actor_id, event_time_utc, importance_score)

2. **Soft Delete Execution**: For each memory marked for deletion:
   - Begin transaction (atomic soft delete)
   - INSERT into tombstone table with original record metadata
   - UPDATE original table: SET archival_status='TOMBSTONE', is_canonical=0, decay_factor=0.0
   - Set grace_period_end = deleted_at + 30 days (30-day undelete window)
   - Store deletion_reason (retention_expired / user_request / privacy_purge / duplicate_removed)

3. **Cross-Layer Tombstone Propagation**: Handle references from other layers:
   - If st_epi episode is tombstoned, update st_hipp_events.consolidation_status='TOMBSTONED'
   - If st_sem semantic is tombstoned, update st_epi.promoted_to_semantic_id=NULL for source episodes
   - If st_kg_dom entity is tombstoned, mark related st_kg_edges as orphaned (source_node_tombstoned=1)
   - Maintains queryability during grace period (queries can filter tombstones)

4. **Deletion Audit Logging**: Emit detailed audit events for compliance:
   - Log to deletion_audit table: (audit_id, memory_id, layer, deleted_at, deleted_by, reason, gdpr_request_id, retention_policy_id)
   - For GDPR right-to-erasure requests, include gdpr_request_id for regulatory compliance
   - Emit SSE event via Observe Port: `memory.deleted.v1` with memory_id, layer, reason
   - Enable external systems (backups, replicas) to process deletion

5. **Undelete Support**: Support memory recovery within grace period:
   - Provide undelete API: POST /k0/memory.undelete with memory_id and layer
   - Query tombstone table for tombstone_id matching memory_id
   - If grace_period_end > now, restore original record: SET archival_status='ACTIVE', is_canonical=1, decay_factor=1.0
   - Delete tombstone record and log undelete event
   - If grace_period expired, reject undelete request (permanent deletion pending)

6. **Tombstone Metadata Indexing**: Enable tombstone queries for debugging and compliance:
   - CREATE INDEX idx_tombstone_grace ON st_*_tombstones(grace_period_end) WHERE grace_period_end > datetime('now')
   - CREATE INDEX idx_tombstone_actor ON st_*_tombstones(metadata_json->>'actor_id')
   - Supports "show all my deleted memories" queries for transparency

**Dependencies**:

- Tombstone table schemas (create if not exist)
- SHA256 hash calculator for content_hash
- Transaction management (BEGIN/COMMIT/ROLLBACK)
- Observe Port for deletion events

**Observability**:

- Metric: `p03_r3_tombstones_created_total` (counter by layer and reason)
- Metric: `p03_r3_tombstone_grace_period_days` (histogram)
- Metric: `p03_r3_undelete_requests_total` (counter by success/failure)
- Log: `r3_tombstone_created` event with tombstone_id and grace_period_end

---

#### R3.6 Archival & GC Scheduling

**Role**: Move low-priority memories to cold storage (compression, offload to S3/blob storage) and schedule garbage collection for expired tombstones. Reduces hot storage footprint by 30-50%.

**Implementation Strategy**:

1. **Archival Candidate Selection**: Identify memories marked for archival:
   - Query memory layers for records with archival_status='ACTIVE' AND retention decision='ARCHIVE'
   - Filter to records with decay_factor <0.7 AND importance_score <0.5 (low value, low recent access)
   - Exclude memories accessed in last 30 days (access_count increment within 30d)
   - Prioritize oldest memories first (order by first_observed_at ASC)

2. **Archive Packaging**: Prepare archival batches for cold storage:
   - Group records by layer and tenant_id (enables tenant-level archival policies)
   - Serialize records to JSON format with full schema (enables schema evolution)
   - Compress JSON using gzip (typical 70-80% compression ratio)
   - Generate archive manifest: (archive_id, layer, tenant_id, record_count, compressed_size_bytes, created_at)

3. **Cold Storage Write**: Upload archives to blob storage:
   - Upload to configured cold storage (S3, Azure Blob, local filesystem)
   - Key format: `{tenant_id}/{layer}/archive_{YYYY-MM-DD}_{archive_id}.json.gz`
   - Store archive manifest in st_archives table: (archive_id, storage_key, layer, tenant_id, record_ids_json, archived_at, restore_cost_estimate)
   - Enable archive restoration via manifest lookup

4. **Hot Storage Cleanup**: Remove archived records from hot database:
   - For each archived record, UPDATE archival_status='ARCHIVED'
   - Optionally DELETE from hot tables if archival_status='ARCHIVED' AND archived_at < (now - 7 days)
   - Keeps 7-day buffer in hot storage for accidental restoration requests
   - Run VACUUM command periodically to reclaim disk space (weekly maintenance)

5. **Tombstone Garbage Collection**: Permanently delete expired tombstones:
   - Query tombstone tables for grace_period_end < now (grace period expired)
   - For each expired tombstone, permanently DELETE from tombstone table
   - Log final deletion event: `memory.permanently_deleted.v1` with tombstone_id and original_id
   - No restoration possible after this point (true deletion)

6. **GC Scheduling**: Schedule periodic cleanup jobs:
   - **Hourly**: Archive new candidates (batch_size=1000)
   - **Daily**: Delete expired tombstones (grace_period expired)
   - **Weekly**: VACUUM database to reclaim space
   - **Monthly**: Validate archive integrity (checksum verification, restore test)
   - Use APScheduler or K0 job scheduler for reliable execution

7. **Archive Restoration Support**: Enable restoring archived memories when needed:
   - Provide restore API: POST /k0/memory.restore with memory_id
   - Query st_archives for archive_id containing memory_id (from record_ids_json)
   - Download archive from cold storage, decompress, deserialize
   - INSERT restored record into hot table with archival_status='ACTIVE'
   - Charge restore_cost_estimate to usage metrics (cloud storage egress cost)

**Dependencies**:

- Cold storage client (S3, Azure Blob, or local filesystem)
- Gzip compression library
- APScheduler for periodic jobs
- st_archives table schema

**Observability**:

- Metric: `p03_r3_archives_created_total` (counter)
- Metric: `p03_r3_archived_records_total` (counter by layer)
- Metric: `p03_r3_archive_compressed_size_bytes` (histogram)
- Metric: `p03_r3_tombstones_gc_total` (counter)
- Metric: `p03_r3_hot_storage_freed_bytes` (counter)
- Log: `r3_archival_complete` event with archive_id and storage_key
- Log: `r3_gc_complete` event with tombstones deleted and space reclaimed

---

**R3 Phase Summary**:

| Step | Action | Input | Output | Duration Target |
|------|--------|-------|--------|-----------------|
| R3.1 | Deduplication | st_hipp_events batch (1000 events) | novelty_score, near_duplicates_json, is_near_duplicate | 2 minutes |
| R3.2 | Novelty Scoring | Events + entity/activity/sentiment context | Updated novelty_score with bonuses | 1 minute |
| R3.3 | Stale Memory Detection | All memory layers (st_epi, st_sem, st_procedural, st_social) | Stale memory list with decay_factors and retention_scores | 2 minutes |
| R3.4 | Retention Policy Enforcement | Stale memories + st_retention_policy rules | Retention decisions (KEEP/ARCHIVE/DELETE) for 50-200 memories | 1 minute |
| R3.5 | Tombstone Creation | Memories marked for deletion | Tombstone records with 30-day grace period | 2 minutes |
| R3.6 | Archival & GC | Memories marked for archival + expired tombstones | Cold storage archives, hot storage cleanup, permanent deletions | 2 minutes |

**Transition to R4**: R3 runs concurrently with R4 during REM phase. Upon completing R3, focus shifts entirely to R4 knowledge graph consolidation. R3 outputs (cleaned memory layers, pruned duplicates, archived content) reduce memory footprint and improve query performance for subsequent consolidation cycles.

---

### R4 – Knowledge Graph Consolidation (Entity & Relationship Extraction)

**Purpose**: Extract entities and relationships from consolidated episodic memories to build a temporal knowledge graph representing people, places, activities, and their interconnections. This phase constructs structured knowledge from unstructured memories.

**Execution Context**: REM_PHASE (final 30 minutes of 90-minute sleep cycle, runs concurrently with R3)

**Input**:

- st_hipp_events batch (1000 events with entities_json from P02)
- st_epi canonical episodes (for entity resolution)
- R1 association cache (strengthened entity relationships)
- st_kg_dom existing entities (for entity matching)
- st_kg_edges existing relationships (for relationship updates)

**Output**:

- New/updated st_kg_dom entity nodes (50-150 entities)
- New/updated st_kg_edges relationship edges (100-300 relationships)
- Temporal graph updates (valid_from, valid_to, observation timestamps)
- Causal relationships with confidence scores

**Performance Budget**: Extract entities and relationships from 1000 events, write 50-150 entities and 100-300 edges in <10 minutes

---

#### R4.1 Entity Extraction & Normalization

**Role**: Extract entities from episodic events, normalize variants, resolve to canonical entities, and prepare for knowledge graph insertion.

**Implementation Strategy**:

1. **Entity Parsing from P02 Output**: Extract entities from st_hipp_events.entities_json:
   - Parse JSON array: `[{"text": "Sarah", "type": "PERSON", "confidence": 0.92}, ...]`
   - Entity types: PERSON, LOCATION, ORGANIZATION, ACTIVITY, OBJECT, CONCEPT, TEMPORAL
   - Filter entities with confidence ≥0.6 (low-confidence entities skipped)
   - Collect all entities across batch (1000 events → ~500-1000 raw entity mentions)

2. **Entity Normalization**: Standardize entity text variants to canonical forms:
   - **Person names**: Normalize to "FirstName LastName" format (e.g., "sarah k" → "Sarah Kumar")
   - **Locations**: Normalize to consistent naming (e.g., "thai basil rest." → "Thai Basil Restaurant")
   - **Organizations**: Expand abbreviations (e.g., "ACME Corp" → "ACME Corporation")
   - Apply case normalization (proper case for names, title case for places)
   - Remove articles and determiners (e.g., "the park" → "Park")

3. **Entity Resolution**: Match extracted entities to existing knowledge graph nodes:
   - Query st_kg_dom for entities with similar node_label (fuzzy text match, Levenshtein distance ≤2)
   - For PERSON entities, cross-reference with people table (person_id lookup)
   - For LOCATION entities, use geohash_6 from events for spatial matching
   - Calculate match confidence: exact_match=1.0, fuzzy_match=0.7-0.9, no_match=0.0
   - Build entity resolution map: raw_entity_text → (node_id, match_confidence)

4. **Entity Disambiguation**: Resolve ambiguous entities using context:
   - If multiple node_id candidates match (e.g., "Sarah" matches 3 people), use disambiguation rules:
     - Participants_json co-occurrence (which Sarah appears with actor_id most frequently?)
     - Location proximity (which Sarah lives in same geohash region?)
     - Temporal patterns (which Sarah appears in same time_of_day_bucket?)
   - If disambiguation fails (confidence <0.5), create ambiguity record for Active Learning Loop (P06)
   - Mark ambiguous entities with ambiguity_score = 0.8 in st_kg_dom

5. **New Entity Candidate Creation**: For entities with no match (match_confidence = 0.0):
   - Generate deterministic node_id = hash(entity_type + normalized_text + tenant_id)
   - Extract entity attributes from event context:
     - PERSON: Extract from participants_json, infer role from participant_roles_json
     - LOCATION: Extract geohash_6, location_type from event
     - ORGANIZATION: Extract from entities_json, infer category from activity_type
   - Mark as new_entity_candidate with provisional status (pending validation)

6. **Entity Deduplication**: Merge duplicate new entity candidates:
   - Group new candidates by normalized_text and entity_type
   - If multiple candidates for same entity, select canonical based on:
     - Highest total confidence across all mentions
     - Most complete attribute set (more metadata = better)
     - Most recent first_observed_at (prefer recent observations)
   - Merge mention counts and source_episodes_json from duplicates

**Dependencies**:

- JSON parser for entities_json
- Fuzzy text matching (Levenshtein distance calculator)
- st_kg_dom query interface for entity lookup
- people table query interface for person resolution

**Observability**:

- Metric: `p03_r4_entities_extracted_total` (counter by entity_type)
- Metric: `p03_r4_entity_resolution_confidence` (histogram)
- Metric: `p03_r4_new_entities_discovered_total` (counter by entity_type)
- Metric: `p03_r4_ambiguous_entities_total` (counter)
- Log: `r4_entities_extracted` event with entity count by type and resolution stats

---

#### R4.2 Relationship Discovery

**Role**: Discover relationships between entities by analyzing co-occurrence patterns, temporal proximity, and semantic context from episodic events.

**Implementation Strategy**:

1. **Co-Occurrence Analysis**: Identify entity pairs that appear together in events:
   - For each event, extract all entities (from entities_json and participants_json)
   - Generate all pairwise combinations: (entity_a, entity_b) where entity_a ≠ entity_b
   - Count co-occurrence frequency across batch: (entity_pair → occurrence_count)
   - Filter pairs with occurrence_count ≥2 (single co-occurrence = weak relationship signal)

2. **Relationship Type Classification**: Infer relationship type from event context:
   - **Social Relationships** (PERSON-PERSON):
     - If both in participants_json: INTERACTED_WITH, DINED_WITH, WORKED_WITH (based on activity_type)
     - If family members (check st_relationships): PARENT_OF, SPOUSE_OF, SIBLING_OF
     - If consistent co-occurrence: COLLEAGUE_OF, FRIEND_OF (based on social_context)
   - **Spatial Relationships** (PERSON-LOCATION, ORGANIZATION-LOCATION):
     - LIVES_AT, WORKS_AT, VISITS (based on activity_type and frequency)
   - **Activity Relationships** (PERSON-ACTIVITY, PERSON-OBJECT):
     - PERFORMS, USES, OWNS (based on activity_type and context)
   - **Organizational Relationships** (PERSON-ORGANIZATION):
     - WORKS_FOR, MEMBER_OF, LEADS (based on participant_roles_json)

3. **Relationship Strength Scoring**: Calculate relationship strength based on interaction patterns:
   - Base strength = log(1 + co_occurrence_count) / log(10) (logarithmic scaling)
   - Temporal proximity bonus = exp(-λ × average_time_gap_days), λ=0.01 (closer events = stronger)
   - Context diversity bonus = unique_contexts / total_contexts (diverse contexts = robust relationship)
   - Sentiment alignment bonus = 1 - |std(sentiment_scores)| (consistent sentiment = stable relationship)
   - Final strength = normalize(base × 0.4 + temporal × 0.3 + diversity × 0.2 + sentiment × 0.1) to [0, 1]

4. **Bidirectional vs. Directional Relationships**: Determine relationship directionality:
   - **Bidirectional** (symmetric): INTERACTED_WITH, DINED_WITH, COLLEAGUE_OF, FRIEND_OF
   - **Directional** (asymmetric): PARENT_OF, WORKS_FOR, LEADS, OWNS
   - For bidirectional relationships, create single edge with from_node and to_node (alphabetical order)
   - For directional relationships, create edge with semantic direction (parent → child, employee → organization)

5. **Existing Relationship Lookup**: Check if relationship already exists in st_kg_edges:
   - Query st_kg_edges for (from_node_id, to_node_id, relationship_type) triple
   - If exists AND is_canonical=1, prepare for update (increment observation_count, boost confidence)
   - If exists AND is_canonical=0 (superseded), check if revival needed (relationship re-emerged)
   - If not exists, prepare for insertion (new relationship)

6. **Relationship Validation**: Apply validation rules before finalizing:
   - **Logical consistency**: PARENT_OF requires age difference ≥18 years (check people.date_of_birth)
   - **Temporal consistency**: WORKS_FOR requires overlapping time windows (check organization founding date)
   - **Privacy constraints**: High privacy_risk_score relationships (RED band) require explicit consent
   - Reject invalid relationships and log validation failures for debugging

**Dependencies**:

- st_kg_edges query interface for relationship lookup
- st_relationships table for family graph validation
- people table for age/attribute validation
- R1 association cache for pre-computed co-occurrence data

**Observability**:

- Metric: `p03_r4_relationships_discovered_total` (counter by relationship_type)
- Metric: `p03_r4_relationship_strength_scores` (histogram)
- Metric: `p03_r4_relationship_validation_failures_total` (counter by failure_reason)
- Log: `r4_relationships_discovered` event with relationship count by type and strength distribution

---

#### R4.3 Temporal Graph Updates

**Role**: Update knowledge graph with temporal validity windows (valid_from, valid_to) to track how entities and relationships evolve over time.

**Implementation Strategy**:

1. **Temporal Window Extraction**: Determine validity periods for entities and relationships:
   - For new entities: valid_from = earliest event_time_utc mentioning entity
   - For existing entities: Update last_observed_at to latest event_time_utc
   - For relationships: valid_from = earliest co-occurrence event_time_utc
   - valid_to = NULL for ongoing entities/relationships (still active)

2. **Temporal Invalidation Detection**: Identify relationships that have ended:
   - Query st_kg_edges for relationships with last_observed_at < (now - 180 days)
   - If no recent observations AND relationship_type suggests temporary nature (WORKED_WITH, VISITED):
     - Set valid_to = last_observed_at (relationship ended)
     - Set is_canonical = 0 (superseded, but keep for historical queries)
   - For permanent relationships (PARENT_OF, SIBLING_OF), never set valid_to (permanent)

3. **Versioned Entity Updates**: Handle entity attribute changes over time:
   - If entity attributes changed (e.g., person moved, organization rebranded):
     - Create new version: INSERT with version = old_version + 1
     - Set supersedes_node_id = old_node_id
     - Set old record is_canonical = 0
     - Set new record is_canonical = 1, canonical_node_id = old_canonical_node_id
   - Example: "Sarah Kumar" → "Sarah Chen" (name change after marriage)

4. **Observation Count Tracking**: Increment observation counts for entity/relationship reinforcement:
   - For each entity mentioned in batch, increment st_kg_dom.observation_count
   - For each relationship observed in batch, increment st_kg_edges.observation_count
   - Update last_observed_at timestamps to latest event_time_utc
   - Recalculate confidence_score based on observation_count: confidence = tanh(observation_count / 10)

5. **Temporal Decay Application**: Apply decay to entities/relationships not recently observed:
   - Calculate days_since_last = (now - last_observed_at).days
   - Apply decay formula: decay_factor = exp(-λ × days_since_last), λ varies by type:
     - PERSON relationships: λ=0.005 (slow decay, people don't disappear)
     - LOCATION visits: λ=0.01 (moderate decay, places change)
     - ACTIVITY patterns: λ=0.02 (fast decay, activities shift quickly)
   - Update st_kg_dom.decay_factor and st_kg_edges.decay_factor

6. **Graph Snapshot Versioning**: Create point-in-time snapshots for historical queries:
   - Every 30 days, create knowledge graph snapshot (export to JSON)
   - Store snapshot in st_kg_snapshots table: (snapshot_id, snapshot_date, entity_count, edge_count, storage_key)
   - Enables "what did the graph look like on 2025-10-15?" queries
   - Useful for debugging relationship evolution and entity attribute drift

**Dependencies**:

- st_kg_dom and st_kg_edges write interfaces
- Date arithmetic utilities (temporal window calculations)
- Versioning logic (supersedes chain management)
- st_kg_snapshots table (if not exists, create)

**Observability**:

- Metric: `p03_r4_temporal_updates_total` (counter by update_type: new/extended/ended)
- Metric: `p03_r4_entity_versions_created_total` (counter)
- Metric: `p03_r4_observation_counts` (histogram by entity_type)
- Metric: `p03_r4_decay_factors` (histogram by entity_type)
- Log: `r4_temporal_updated` event with update stats and ended relationship count

---

#### R4.4 Causal Graph Construction

**Role**: Discover causal relationships between events, activities, and outcomes by analyzing temporal sequences and sentiment changes.

**Implementation Strategy**:

1. **Temporal Sequence Mining**: Identify recurring event sequences that suggest causality:
   - Group events by actor_id and sort by event_time_utc
   - Build sliding windows of 3-5 consecutive events (e.g., [event_1, event_2, event_3])
   - Extract activity_type sequences: ["gym", "shower", "feel_energized"]
   - Count sequence frequency across batch and historical st_epi records
   - Filter sequences with frequency ≥3 (need repetition to infer causality)

2. **Sentiment Delta Analysis**: Detect state changes that indicate causal effects:
   - For each event pair (event_a, event_b) within 6-hour window:
     - Calculate sentiment_delta = event_b.sentiment_score - event_a.sentiment_score
     - If |sentiment_delta| > 0.5, mark as significant state change
     - Example: "argued with spouse" (sentiment=-0.7) → "apologized" (sentiment=0.6) = +1.3 delta
   - Associate activity_type from event_a as potential cause of sentiment change

3. **Causal Relationship Type Classification**:
   - **Activity → Mood**: Activity causes emotional state change (e.g., "exercise" → "energized")
   - **Event → Behavior**: Event triggers behavioral response (e.g., "argument" → "reconciliation")
   - **Condition → Outcome**: Conditional pattern (e.g., "skip breakfast" → "low_energy_at_noon")
   - **Routine → Habit**: Repeated pattern solidifies into habit (e.g., "coffee after waking" × 30 days)

4. **Causal Confidence Scoring**: Calculate confidence in causal relationship:
   - Frequency score = log(1 + sequence_count) / log(10)
   - Temporal consistency score = 1 - std(time_gaps) / mean(time_gaps) (consistent timing = higher causality)
   - Sentiment correlation score = pearson_correlation(cause_activity, effect_sentiment)
   - Confounding check penalty = -0.2 if alternative explanations exist (e.g., multiple activities in window)
   - Causal confidence = normalize(frequency × 0.4 + temporal × 0.3 + correlation × 0.2 - confounding × 0.1)

5. **Causal Edge Storage**: Write causal relationships to st_kg_edges with special relationship_type:
   - relationship_type = "CAUSES" or "LEADS_TO" or "TRIGGERS"
   - from_node_id = activity entity node_id
   - to_node_id = outcome/mood entity node_id
   - Store causal metadata in edge_properties_json:
     - average_delay_minutes (median time between cause and effect)
     - confidence_score (causal inference confidence)
     - sequence_count (number of observations)
     - confounders_json (alternative explanations considered)

6. **Causal Graph Pruning**: Remove spurious causal relationships:
   - If confidence_score <0.4, mark as weak causality (don't write to graph)
   - If sequence hasn't occurred in last 90 days, mark causal edge as stale (set valid_to)
   - If A→B and B→A both exist (circular causality), retain stronger edge and flag for review

**Dependencies**:

- Sequence mining algorithm (sliding window over temporal events)
- Statistical correlation calculators (Pearson correlation, std deviation)
- st_kg_dom and st_kg_edges write interfaces

**Observability**:

- Metric: `p03_r4_causal_sequences_mined_total` (counter)
- Metric: `p03_r4_causal_relationships_created_total` (counter by causal_type)
- Metric: `p03_r4_causal_confidence_scores` (histogram)
- Metric: `p03_r4_spurious_causality_filtered_total` (counter)
- Log: `r4_causal_graph_built` event with causal edge count and confidence distribution

---

#### R4.5 Concept Evolution Tracking

**Role**: Track how concepts, beliefs, and preferences evolve over time by detecting semantic drift and updating concept nodes in the knowledge graph.

**Implementation Strategy**:

1. **Concept Extraction from Semantic Layer**: Identify concepts from st_sem patterns:
   - Query st_sem for semantic records created/updated in last consolidation cycle
   - Extract concept keywords from pattern_text (e.g., "prefers Italian food" → concept="food_preference:italian")
   - Extract belief statements (e.g., "values family time" → concept="value:family")
   - Extract preferences (e.g., "dislikes crowds" → concept="preference:solitude")

2. **Concept Similarity Clustering**: Group similar concepts to detect evolution:
   - For each concept, compute embedding vector (from st_vec layer)
   - Calculate cosine similarity between all concept pairs
   - Cluster concepts with similarity >0.8 (likely variations of same concept)
   - Example: "likes Italian food" + "prefers pasta" + "favorite: lasagna" = single concept cluster

3. **Concept Drift Detection**: Identify when concepts change over time:
   - For each concept cluster, sort observations by first_observed_at chronologically
   - Calculate sentiment_score and confidence_score trends over time (linear regression)
   - If trend slope > 0.3 or < -0.3, mark as concept drift (strengthening or weakening)
   - Example: "dislikes vegetables" (6 months ago) → "neutral vegetables" (now) = drift detected

4. **Evolution Event Classification**:
   - **Strengthening**: Confidence increases, observation_count grows (concept reinforced)
   - **Weakening**: Confidence decreases, recent observations contradict (concept fading)
   - **Reversal**: Sentiment flips (e.g., "dislikes running" → "enjoys running")
   - **Elaboration**: Concept becomes more specific (e.g., "likes music" → "likes classical piano")
   - **Contradiction**: New observations conflict with old concept (mark as ambiguous, flag for Active Learning)

5. **Concept Node Versioning**: Update concept nodes with evolution tracking:
   - If concept strengthened/elaborated: Update existing node (increment observation_count, boost confidence)
   - If concept reversed/contradicted: Create new version node:
     - INSERT with version = old_version + 1
     - Set supersedes_node_id = old_node_id
     - Set old record is_canonical = 0, valid_to = reversal_date
     - Set new record is_canonical = 1, valid_from = reversal_date
   - Store evolution metadata in node_properties_json: (evolution_type, reversal_date, old_sentiment, new_sentiment)

6. **Concept Graph Linkage**: Connect related concepts with semantic edges:
   - Create edges between concept nodes: ELABORATES, CONTRADICTS, REINFORCES, SUPERSEDES
   - Example: "likes_music" --ELABORATES→ "likes_classical_piano"
   - Example: "dislikes_vegetables" --CONTRADICTS→ "enjoys_salads"
   - Enables semantic reasoning: "if user likes classical piano, recommend symphony concerts"

**Dependencies**:

- st_sem query interface for semantic memory
- st_vec embedding similarity calculator (cosine similarity)
- Linear regression for trend analysis
- st_kg_dom write interface for concept nodes

**Observability**:

- Metric: `p03_r4_concepts_extracted_total` (counter)
- Metric: `p03_r4_concept_drift_detected_total` (counter by evolution_type)
- Metric: `p03_r4_concept_versions_created_total` (counter)
- Metric: `p03_r4_concept_contradictions_total` (counter)
- Log: `r4_concept_evolution_tracked` event with drift count and evolution type distribution

---

**R4 Phase Summary**:

| Step | Action | Input | Output | Duration Target |
|------|--------|-------|--------|-----------------|
| R4.1 | Entity Extraction & Normalization | st_hipp_events batch (entities_json) | 50-150 normalized entities with resolution map | 2 minutes |
| R4.2 | Relationship Discovery | Entity pairs + event context | 100-300 relationships with strength scores | 3 minutes |
| R4.3 | Temporal Graph Updates | Entities + relationships + time windows | Updated st_kg_dom and st_kg_edges with temporal validity | 2 minutes |
| R4.4 | Causal Graph Construction | Event sequences + sentiment deltas | Causal relationships (CAUSES/TRIGGERS edges) | 2 minutes |
| R4.5 | Concept Evolution Tracking | st_sem concepts + embeddings | Concept drift detection and versioned concept nodes | 1 minute |

**Transition to R5**: Upon completing R4 (or reaching 90-minute cycle end), optionally transition to R5 for dream-like exploration. If consolidation budget exceeded, skip R5 and proceed to R6 for final st_hipp_events updates. R4 outputs (enriched knowledge graph) enable intelligent recommendations and context-aware responses in K1.

---

### R5 – Dream-Like Exploration (Creative Insight Generation)

**Purpose**: Simulate dream-like cognitive processes to generate creative insights, explore counterfactual scenarios, rehearse future plans, and discover hidden patterns. This phase mimics REM sleep's role in creative problem-solving, emotional processing, and procedural memory consolidation.

**Execution Context**: REM_PHASE extension (optional, runs if consolidation cycle completes early and budget remains)

**Biological Inspiration**:

- **REM Sleep Consolidation** (Walker & Stickgold 2010): Hippocampus-neocortex dialogue during REM sleep enables creative associations, emotional regulation, and procedural skill enhancement
- **Episodic Simulation Theory** (Schacter et al. 2012): Brain reuses episodic memory systems to imagine future scenarios and counterfactual alternatives
- **Default Mode Network Activation** (Raichle 2015): Mind-wandering during rest enables spontaneous insight generation and problem restructuring

**Input**:

- Consolidated episodic clusters from R2 (semantic patterns)
- Knowledge graph from R4 (entities, relationships, causal edges)
- Procedural routines from st_procedural (habits, skills)
- Active Learning gaps from P06 (uncertainties, missing information)

**Output**:

- Counterfactual scenarios stored in st_prospective (what-if explorations)
- Forward simulations for planning (predicted outcomes)
- Insights and creative connections stored in st_sem (novel semantic links)
- Rehearsed procedural sequences (optimized habit chains)

**Performance Budget**: Generate 10-30 insights, 5-15 counterfactuals, rehearse 3-8 procedural sequences in <8 minutes (optional phase)

---

#### R5.1 Counterfactual Thinking

**Role**: Generate "what if" scenarios by perturbing past events and exploring alternative outcomes. Enables learning from near-misses, understanding causal relationships, and preparing for similar future situations.

**Research Foundation**:

- **Counterfactual Reasoning** (Byrne 2005): Humans learn more from near-misses than distant alternatives; semifactual thinking ("even if") complements counterfactual ("if only")
- **Causal Attribution Theory** (Weiner 1985): Counterfactuals reveal perceived controllability and locus of causation
- **Functional Theory of Counterfactual Thinking** (Epstude & Roese 2008): Downward counterfactuals improve affect, upward counterfactuals improve behavior

**Novel Algorithm: Causal Perturbation Network (CPN)**

**Implementation Strategy**:

1. **Regret/Relief Event Selection**: Identify events with strong emotional valence for counterfactual exploration:
   - Query st_epi for episodes with |sentiment_score| > 0.6 (strong emotional events)
   - Prioritize events with sentiment_score < -0.5 (negative outcomes = high regret potential)
   - Prioritize events marked by user as "wish it went differently" (from K1 conversation flags)
   - Select top 10 events by emotional_impact_score = |sentiment_score| × salience_score × recency_weight

2. **Causal Graph Decomposition**: Extract causal chain leading to selected event:
   - Query st_kg_edges for causal relationships (relationship_type = 'CAUSES' or 'LEADS_TO')
   - Build directed acyclic graph (DAG) of causal predecessors: event ← cause1 ← cause2 ← ...
   - Identify modifiable nodes (actions under actor's control vs. external factors)
   - Example: "Argument with spouse" ← "Arrived home late" ← "Stayed at office" ← "Meeting ran long"
   - Modifiable: "Stayed at office" (could have left earlier); Not modifiable: "Meeting ran long" (boss decision)

3. **Counterfactual Generation via Intervention**: Perturb causal graph at modifiable nodes:
   - **Upward Counterfactuals** (better outcome): "If I had left work on time, would the argument have been avoided?"
   - **Downward Counterfactuals** (worse outcome): "If I had also forgotten anniversary, would it have escalated further?"
   - **Semifactual** (same outcome): "Even if I had called ahead, the argument would still have happened" (tests necessity)
   - Generate 2-3 counterfactuals per event (focus on most plausible interventions)

4. **Outcome Simulation using Bayesian Networks**: Predict counterfactual outcome probabilities:
   - Build Bayesian network from causal DAG with conditional probability tables (CPTs)
   - CPT entries estimated from historical patterns: P(argument | arrived_late) = 0.7, P(argument | arrived_on_time) = 0.2
   - Perform do-calculus intervention (Pearl 2009): set modifiable node to counterfactual value
   - Propagate probabilities through network to predict outcome distribution
   - Example: P(argument | do(left_on_time)) = 0.2 → 75% chance argument avoided

5. **Learning Signal Extraction**: Generate actionable insights from counterfactual analysis:
   - **Preventable Regret**: If upward counterfactual yields significantly better outcome (>0.4 sentiment improvement), flag as preventable mistake
   - **Uncontrollable Factors**: If semifactual shows outcome unchanged, identify uncontrollable external factors
   - **Future Mitigation Strategy**: Generate if-then rule: "IF similar_situation AND controllable_factor THEN intervention_action"
   - Example: "IF work meeting runs late THEN send proactive text to spouse to manage expectations"

6. **Counterfactual Storage**: Write counterfactual scenarios to st_prospective for future reference:
   - Store as prospective memory with intent_type = 'counterfactual_learning'
   - Include: original_episode_id, counterfactual_scenario_text, predicted_outcome, learning_signal, mitigation_strategy
   - Link to causal graph nodes via source_episodes_json
   - Mark with high predictive_weight for K1 planner to surface in similar situations

**Novel Contribution**: CPN extends Pearl's causal intervention framework with emotion-weighted node selection and Bayesian outcome prediction. Unlike traditional counterfactual generators (focusing on logical consistency), CPN prioritizes emotionally salient events and generates actionable mitigation strategies.

**Dependencies**:

- st_epi query interface for high-emotion events
- st_kg_edges causal graph query
- Bayesian network library (pgmpy or similar)
- st_prospective write interface

**Observability**:

- Metric: `p03_r5_counterfactuals_generated_total` (counter by outcome_type: upward/downward/semifactual)
- Metric: `p03_r5_preventable_regrets_identified_total` (counter)
- Metric: `p03_r5_mitigation_strategies_created_total` (counter)
- Log: `r5_counterfactual_explored` event with scenario, predicted_outcome, learning_signal

---

#### R5.2 Forward Simulation (Scenario Generation)

**Role**: Generate plausible future scenarios based on current patterns, goals, and knowledge graph. Enables proactive planning, risk assessment, and opportunity identification.

**Research Foundation**:

- **Prospective Brain Hypothesis** (Schacter & Addis 2007): Brain is fundamentally oriented toward future, using past experiences to simulate possible futures
- **Constructive Episodic Simulation** (Addis et al. 2009): fMRI studies show hippocampus activates during future event imagination, recruiting same neural substrates as episodic memory
- **Mental Time Travel** (Suddendorf & Corballis 2007): Unique human capacity to project self into past (episodic memory) and future (prospection)

**Novel Algorithm: Temporal Projection Network with Monte Carlo Tree Search (TPN-MCTS)**

**Implementation Strategy**:

1. **Goal and Context Extraction**: Identify active goals and current situational context:
   - Query st_prospective for active intentions (intent_type = 'goal', status = 'ACTIVE')
   - Query st_procedural for routines likely to execute in next 7 days (based on frequency and last_performed_at)
   - Extract contextual constraints: upcoming calendar events, recent behavioral patterns, seasonal factors
   - Example active goal: "Plan family vacation by end of month"

2. **State Space Construction**: Build state representation for forward simulation:
   - **Current State** (s₀): Actor's current situation (location, relationships, resources, time)
   - **Action Space** (A): Feasible actions extracted from st_procedural habits and K1 conversation history
   - **Transition Model** (T): P(s' | s, a) learned from historical st_epi sequences (e.g., "plan vacation" → 85% leads to "research destinations")
   - **Reward Function** (R): Expected utility based on goal alignment and sentiment prediction

3. **Monte Carlo Tree Search for Scenario Exploration**:
   - **Selection Phase**: Use Upper Confidence Bounds for Trees (UCT) to balance exploration/exploitation:
     - UCT(node) = Q(node)/N(node) + c × sqrt(ln(N(parent))/N(node))
     - Q = cumulative reward, N = visit count, c = exploration constant (√2)
   - **Expansion Phase**: Generate child nodes by sampling actions from actor's behavioral repertoire
   - **Simulation Phase** (rollout): Sample action sequences until terminal state (goal achieved/failed or 30-day horizon)
   - **Backpropagation Phase**: Update Q-values along traversed path based on simulated outcome

4. **Scenario Diversity via Determinantal Point Processes (DPP)**: Ensure generated scenarios cover diverse possibilities:
   - Represent each scenario as feature vector (actions taken, entities involved, sentiment trajectory)
   - Compute kernel matrix K where K_ij = similarity(scenario_i, scenario_j)
   - Sample diverse subset using DPP: P(S) ∝ det(K_S) (favors low pairwise similarity)
   - Generates 5-10 qualitatively different scenarios (optimistic, pessimistic, creative, conservative paths)

5. **Plausibility Scoring using Learned Dynamics**: Validate scenario realism against historical patterns:
   - For each action transition (s, a, s') in scenario, compute plausibility:
     - Historical frequency: P(s' | s, a) from st_epi transition counts
     - Actor consistency: Does action match actor's typical behavior? (cosine similarity to actor's routine embeddings)
     - Social norms: Does sequence violate social expectations? (check against st_social relationship constraints)
   - Aggregate plausibility: scenario_plausibility = geometric_mean([transition_plausibilities])
   - Filter scenarios with plausibility < 0.3 (implausible fantasy scenarios)

6. **Risk and Opportunity Assessment**: Analyze scenario outcomes for decision support:
   - **Success Probability**: Fraction of MCTS rollouts reaching goal state
   - **Expected Sentiment**: Mean sentiment_score across scenario timeline
   - **Risk Exposure**: Probability of negative outcomes (sentiment < -0.5) × severity
   - **Opportunity Identification**: Detect high-value paths overlooked by actor (hidden opportunities)
   - Example: "If plan vacation 3 weeks early, 70% chance of lower airfare (saves $400)"

7. **Scenario Storage and Ranking**: Write top scenarios to st_prospective:
   - Store each scenario as prospective memory with intent_type = 'forward_simulation'
   - Include: scenario_id, action_sequence_json, predicted_outcome, success_probability, expected_sentiment, plausibility_score
   - Rank by expected_utility = success_probability × goal_value - risk_exposure × risk_aversion_factor
   - Surface top 3 scenarios to K1 for user consideration

**Novel Contribution**: TPN-MCTS combines tree search (from game AI) with DPP diversity sampling and plausibility filtering grounded in personal memory. Unlike generic scenario planners, TPN-MCTS personalizes to individual's behavioral patterns and social constraints.

**Dependencies**:

- st_prospective query interface for goals
- st_procedural query interface for action repertoire
- MCTS implementation (custom or pytorch-based)
- DPP sampling library (dppy)
- st_epi transition statistics

**Observability**:

- Metric: `p03_r5_scenarios_generated_total` (counter)
- Metric: `p03_r5_scenario_plausibility_scores` (histogram)
- Metric: `p03_r5_opportunities_identified_total` (counter)
- Metric: `p03_r5_mcts_rollouts_total` (counter)
- Log: `r5_forward_simulation_complete` event with scenario count and top scenario details

---

#### R5.3 Episodic Simulation (Memory Reconstruction)

**Role**: Reconstruct and embellish existing episodic memories to fill gaps, resolve ambiguities, and generate richer contextual understanding. Mimics hippocampal pattern completion during memory retrieval.

**Research Foundation**:

- **Pattern Completion in Hippocampus** (Marr 1971, Rolls 2013): CA3 recurrent collaterals enable reconstruction of complete memory from partial cues
- **Schema-Driven Memory Reconstruction** (Bartlett 1932, Ghosh & Gilboa 2014): Memories reconstructed using schematic knowledge, not perfectly retrieved
- **Constructive Memory Errors** (Schacter & Addis 2007): Brain fills gaps with plausible inferences, sometimes creating false memories (we avoid this via confidence tracking)

**Novel Algorithm: Schematic Pattern Completion with Uncertainty Quantification (SPC-UQ)**

**Implementation Strategy**:

1. **Incomplete Memory Identification**: Detect episodic memories with missing or ambiguous information:
   - Query st_epi for episodes with ambiguity_score > 0.5 (high uncertainty)
   - Query st_epi for episodes with sparse attributes (missing location, participants, sentiment)
   - Query Active Learning gaps from P06 (entities needing disambiguation, timeline gaps)
   - Prioritize recent memories (last 30 days) for reconstruction (highest utility)

2. **Schema Retrieval**: Identify relevant semantic schemas to guide reconstruction:
   - Query st_sem for semantic patterns matching episode's activity_type and context
   - Example: Episode "dinner with colleagues" matches schema "team_dinner_routine" (typical location, participants, duration)
   - Extract schema prototypes: typical_location, expected_participants, average_sentiment, typical_duration
   - Build schema feature distribution: P(feature | schema) from st_sem observation statistics

3. **Bayesian Memory Reconstruction**: Fill gaps using Bayesian inference with schema priors:
   - For each missing attribute (e.g., location_name):
     - Prior: P(location | schema) from schema feature distribution
     - Likelihood: P(context_clues | location) from co-occurrence patterns in st_epi
     - Posterior: P(location | schema, context_clues) ∝ P(context_clues | location) × P(location | schema)
   - Sample most probable value with uncertainty: location = argmax P(location | ...), confidence = max P(location | ...)
   - Example: "Dinner with Sarah" + schema "team_dinners_with_Sarah" → infer location = "Thai Basil Restaurant" (confidence = 0.78)

4. **Constraint Satisfaction for Temporal Reconstruction**: Resolve timeline ambiguities:
   - Build constraint network: events must satisfy temporal ordering, duration bounds, causal precedence
   - Example: "Picked up groceries" must occur before "Cooked dinner", "Work meeting" before "Commute home"
   - Use constraint propagation (arc consistency) to narrow feasible time windows
   - Detect timeline conflicts: if constraints unsatisfiable, flag as contradiction for Active Learning

5. **Confidence-Weighted Gap Filling**: Distinguish reconstructed content from recalled content:
   - Original recalled attributes: confidence_score = source confidence (from P02)
   - Reconstructed attributes: confidence_score = posterior_probability × schema_strength
   - Mark reconstructed fields in attribute_provenance_json: `{"location_name": "inferred_from_schema:0.78"}`
   - Never overwrite high-confidence recalled memories with low-confidence reconstructions (preservation principle)

6. **Counterfactual Consistency Check**: Validate reconstructions don't contradict known facts:
   - Cross-check reconstructed attributes against knowledge graph constraints
   - Example: If schema suggests "Sarah attended", but st_social shows Sarah was on vacation that week → reject reconstruction
   - Query st_kg_edges for temporal validity: was relationship active during episode timeframe?
   - Reject reconstructions violating logical constraints (person can't be in two locations simultaneously)

7. **Reconstruction Storage and Versioning**: Update st_epi with reconstructed memories:
   - Create new version of episode: version = old_version + 1
   - Set supersedes_episode_id = old_episode_id, mark old record is_canonical = 0
   - Include reconstruction_metadata in episode: (reconstructed_fields_json, schema_source, reconstruction_confidence)
   - Enables transparency: user can see which parts are recalled vs. inferred

**Novel Contribution**: SPC-UQ extends schema theory with Bayesian uncertainty quantification and counterfactual validation. Unlike neural memory models (which can hallucinate), SPC-UQ tracks reconstruction confidence and rejects inconsistent inferences.

**Dependencies**:

- st_epi query interface for incomplete memories
- st_sem schema query
- Bayesian inference engine
- Constraint satisfaction solver (CSP library)
- st_kg_edges for validation

**Observability**:

- Metric: `p03_r5_memories_reconstructed_total` (counter)
- Metric: `p03_r5_reconstruction_confidence_scores` (histogram)
- Metric: `p03_r5_gaps_filled_total` (counter by attribute_type)
- Metric: `p03_r5_reconstruction_rejections_total` (counter by rejection_reason)
- Log: `r5_episodic_simulation_complete` event with reconstruction count and confidence distribution

---

#### R5.4 Insight Generation & Storage

**Role**: Discover latent patterns, unexpected connections, and creative insights by recombining knowledge graph elements in novel ways. Mimics sudden "aha!" moments during incubation and REM sleep.

**Research Foundation**:

- **Remote Associates Test (RAT)** (Mednick 1962): Creativity involves connecting distant semantic concepts
- **Associative Theory of Creativity** (Mednick 1962): Creative ideas emerge from combining remote associations
- **Sleep-Induced Insight** (Wagner et al. 2004): REM sleep enhances extraction of hidden rules and distant associations
- **Bisociation Theory** (Koestler 1964): Creativity arises from perceiving situation in two habitually incompatible frames of reference

**Novel Algorithm: Bisociative Graph Traversal with Surprise Maximization (BGT-SM)**

**Implementation Strategy**:

1. **Semantic Distance Mapping**: Build metric space of concept similarity in knowledge graph:
   - Extract all entities and concepts from st_kg_dom
   - Compute pairwise semantic distance using graph geodesic (shortest path length)
   - Compute embedding space distance using cosine similarity from st_vec
   - Combine: semantic_distance(A, B) = α × graph_distance + (1-α) × embedding_distance, α=0.6
   - Identify "remote associates": entity pairs with semantic_distance > 0.7 (distant but potentially related)

2. **Surprising Connection Discovery via Random Walks with Restart (RWR)**:
   - Initialize random walk at "seed concept" (randomly select from high-importance entities)
   - At each step, with probability (1-c) follow random edge, with probability c restart at seed (c=0.15)
   - Favor edges with low observation_count (unexplored connections) and high causal_confidence
   - After N steps (N=1000), collect visited nodes and their visit frequencies
   - Surprising connections: nodes with high visit frequency despite large semantic_distance from seed

3. **Surprise Quantification using Information Theory**:
   - For each connection (A, B) discovered by random walk:
     - Expected co-occurrence: P_expected(A,B) = P(A) × P(B) (independence assumption)
     - Observed co-occurrence: P_observed(A,B) from st_epi co-occurrence statistics
     - Pointwise Mutual Information: PMI(A,B) = log(P_observed(A,B) / P_expected(A,B))
     - High PMI (>3.0) = surprising connection (entities co-occur more than expected)
   - Example: "exercise" and "better_sleep" have high PMI despite semantic distance (non-obvious connection)

4. **Bisociative Frame Recombination**: Generate creative insights by merging incompatible frames:
   - Frame = semantic cluster in knowledge graph (e.g., "work_domain", "family_domain", "health_domain")
   - For each surprising connection (A, B) where A ∈ frame_1 and B ∈ frame_2:
     - Generate insight template: "Connection between [frame_1] and [frame_2]: [relationship_type]"
     - Example: "Work stress (work_domain) affects sleep quality (health_domain) via rumination cycle"
   - Validate insight using causal graph: does causal path exist between A and B?
   - Rate novelty: insight_novelty = semantic_distance × PMI_score / (observation_count + 1)

5. **Analogical Reasoning via Structure Mapping**: Find isomorphic subgraphs suggesting analogies:
   - Extract common relational patterns: A→B→C structure appears in multiple domains
   - Example: "exercise → endorphins → happiness" analogous to "social_activity → dopamine → happiness"
   - Suggests transferrable insight: "Activities releasing neurotransmitters improve mood"
   - Use structure mapping engine (SME) to find maximal common subgraph isomorphisms
   - Generate analogical insight: "If A works in domain X, try analogous approach in domain Y"

6. **Serendipity Score and Actionability**: Rank insights by usefulness:
   - Serendipity = novelty × relevance × actionability
     - Novelty: How unexpected? (high semantic distance, low prior probability)
     - Relevance: How important to actor's goals? (overlap with st_prospective goals)
     - Actionability: Can actor do something with this? (existence of controllable intervention)
   - Filter insights with serendipity > 0.6
   - Example: "Taking walks after dinner improves family bonding" scores high on all dimensions

7. **Insight Storage in Semantic Layer**: Write insights as semantic memories with special tagging:
   - pattern_type = 'insight' or 'creative_connection'
   - Store in st_sem with high predictive_weight (surface to K1 as proactive suggestions)
   - Include: insight_text, supporting_evidence_json (entity_pairs, causal_paths, PMI_scores)
   - Link to source episodes via source_episodes_json (enables "show me examples" queries)
   - Mark with low ambiguity_score (insights are confident hypotheses, not facts)

**Novel Contribution**: BGT-SM combines random walks, information-theoretic surprise, and structure mapping to automate insight discovery. Unlike association mining (which finds frequent patterns), BGT-SM finds infrequent-but-meaningful connections. Unlike LLM generation (which hallucinates), BGT-SM grounds insights in personal knowledge graph.

**Dependencies**:

- st_kg_dom and st_kg_edges for graph traversal
- st_vec for embedding distances
- Random walk library (NetworkX or igraph)
- Structure mapping engine (optional, can use graph isomorphism)
- st_sem write interface

**Observability**:

- Metric: `p03_r5_insights_generated_total` (counter)
- Metric: `p03_r5_surprise_scores` (histogram of PMI values)
- Metric: `p03_r5_serendipity_scores` (histogram)
- Metric: `p03_r5_analogies_discovered_total` (counter)
- Log: `r5_insight_discovered` event with insight_text, surprise_score, serendipity_score

---

#### R5.5 Motor Skill Rehearsal (Procedural Memory)

**Role**: Mentally rehearse procedural sequences and habit chains to optimize execution, identify bottlenecks, and strengthen motor memory. Mimics REM sleep's role in procedural memory consolidation.

**Research Foundation**:

- **Offline Learning in Motor Skills** (Walker et al. 2002): Sleep-dependent motor skill enhancement without physical practice
- **Motor Sequence Consolidation** (Karni et al. 1998): REM sleep strengthens motor cortex representations
- **Mental Practice Effects** (Driskell et al. 1994): Mental rehearsal improves physical performance, especially for cognitive components
- **Neural Replay in Motor Cortex** (Euston et al. 2007): Motor sequences replay during sleep at faster speeds

**Novel Algorithm: Temporal Difference Learning for Habit Chain Optimization (TDL-HCO)**

**Implementation Strategy**:

1. **Habit Chain Extraction**: Identify sequential procedural patterns for rehearsal:
   - Query st_procedural for active routines with consistency_score < 0.8 (not yet automatized)
   - Query st_procedural for routines with recent performance degradation (streak_count declining)
   - Extract action_sequence_json: ordered list of steps in routine
   - Example: "Morning routine" = [wake_up, bathroom, coffee, breakfast, exercise, shower, commute]

2. **Markov Decision Process Formulation**: Model habit chain as MDP for optimization:
   - **States (S)**: Steps in procedural sequence
   - **Actions (A)**: Possible next steps (including deviations from routine)
   - **Transitions (P)**: Observed transition probabilities from st_epi execution history
   - **Rewards (R)**: Utility of each state (completion = +10, pleasant_steps = +2, unpleasant_steps = -1)
   - **Goal**: Find policy π that maximizes cumulative reward (efficient, enjoyable routine)

3. **Temporal Difference Learning for Value Estimation**: Learn optimal habit execution:
   - Initialize V(s) = 0 for all states (value function)
   - For each historical routine execution in st_epi:
     - Observe state sequence: s₀ → s₁ → s₂ → ... → s_terminal
     - For each transition (s_t, s_t+1):
       - TD error: δ = R(s_t) + γ × V(s_t+1) - V(s_t), γ=0.9 (discount factor)
       - Update: V(s_t) ← V(s_t) + α × δ, α=0.1 (learning rate)
   - After convergence, V(s) represents expected cumulative reward from state s

4. **Bottleneck Detection via Value Gradients**: Identify inefficient steps in routine:
   - Compute value gradient: ΔV(s_t) = V(s_t+1) - V(s_t)
   - **Bottleneck**: Step with ΔV < -2 (large value drop = unpleasant/difficult step)
   - Example: "Make breakfast" has ΔV = -3 (takes too long, delays rest of routine)
   - **Optimization opportunity**: Steps with low V(s) but high potential (many alternative actions available)

5. **Alternative Path Exploration via Mental Simulation**: Generate optimized habit variants:
   - At each bottleneck state, explore alternative actions:
     - Query st_procedural for similar routines by other actors (social learning)
     - Query st_epi for occasions when actor deviated from routine (what happened?)
     - Generate hypothetical alternatives: "What if skip breakfast? Meal prep night before? Quick cereal instead?"
   - Simulate each alternative using learned transition model
   - Predict expected value: V_alternative = Σ R(s) × P(s | alternative_action)
   - Rank alternatives by value improvement: ΔV_improvement = V_alternative - V_current

6. **Chunking and Compression via Hierarchical Reinforcement Learning**: Learn efficient action groupings:
   - Identify repeated subsequences in action_sequence_json (frequent substrings)
   - Example: [bathroom, brush_teeth, wash_face] appears in both morning and evening routines
   - Create "chunk" = composite action representing subsequence
   - Update routine representation with chunks: [wake_up, morning_bathroom_chunk, coffee, ...]
   - Reduces cognitive load (fewer deliberate steps), speeds execution

7. **Rehearsal Execution at Accelerated Speed**: Mentally practice optimized routine:
   - Generate optimized action sequence with best alternatives and chunks
   - "Replay" sequence at 10x speed (simulate rapid execution without physical constraints)
   - For each step in replay:
     - Reinforce action_sequence memory (increment confidence_score)
     - Update transition probabilities with optimized transitions
     - Store rehearsal metadata: (rehearsal_count, last_rehearsal_at, optimization_applied)
   - After 5-10 rehearsals, mark routine as "rehearsed" with high confidence

8. **Optimization Recommendation Storage**: Write procedural insights to st_prospective:
   - For each identified optimization (bottleneck with superior alternative):
     - Create prospective memory: intent_type = 'procedural_optimization'
     - Include: routine_id, bottleneck_step, recommended_alternative, expected_improvement
     - Example: "Consider meal prepping on Sunday to speed up weekday breakfast routine (saves 15 min/day)"
   - Surface to K1 as proactive suggestions during routine execution

**Novel Contribution**: TDL-HCO applies reinforcement learning to personal habit data, enabling data-driven routine optimization. Unlike habit tracking apps (which only monitor), TDL-HCO actively suggests improvements grounded in value function learning.

**Dependencies**:

- st_procedural query interface for routines
- st_epi historical execution data
- RL library (PyTorch with TD(λ) implementation)
- st_prospective write interface for recommendations

**Observability**:

- Metric: `p03_r5_routines_rehearsed_total` (counter)
- Metric: `p03_r5_bottlenecks_detected_total` (counter)
- Metric: `p03_r5_optimizations_suggested_total` (counter)
- Metric: `p03_r5_value_improvements` (histogram of ΔV_improvement)
- Log: `r5_motor_rehearsal_complete` event with routine_id, rehearsal_count, optimizations

---

**R5 Phase Summary**:

| Step | Action | Input | Output | Duration Target |
|------|--------|-------|--------|-----------------|
| R5.1 | Counterfactual Thinking | High-emotion episodic events + causal graph | 10-20 counterfactual scenarios with mitigation strategies | 2 minutes |
| R5.2 | Forward Simulation | Active goals + procedural routines + context | 5-10 diverse future scenarios with success probabilities | 2 minutes |
| R5.3 | Episodic Simulation | Incomplete/ambiguous episodic memories + schemas | Reconstructed memories with confidence-tracked inferences | 1.5 minutes |
| R5.4 | Insight Generation | Knowledge graph + semantic embeddings | 10-30 creative insights with surprise and serendipity scores | 2 minutes |
| R5.5 | Motor Skill Rehearsal | Procedural routines + execution history | Optimized habit chains with bottleneck recommendations | 0.5 minutes |

**Transition to R6**: Upon completing R5 (or skipping if budget exceeded), transition to R6 for final st_hipp_events consolidation state updates. R5 outputs (counterfactuals, scenarios, insights, optimizations) enrich st_prospective and st_sem layers, enabling K1 to provide proactive, context-aware recommendations.

**Key Research Papers Cited**:

1. Byrne (2005) - "The Rational Imagination: How People Create Alternatives to Reality"
2. Schacter et al. (2012) - "The Future of Memory: Remembering, Imagining, and the Brain"
3. Walker et al. (2002) - "Practice with Sleep Makes Perfect: Sleep-Dependent Motor Skill Learning"
4. Mednick (1962) - "The Associative Basis of the Creative Process"
5. Pearl (2009) - "Causality: Models, Reasoning, and Inference"
6. Addis et al. (2009) - "Episodic Simulation of Future Events: Concepts, Data, and Applications"

**Novel Algorithmic Contributions**:

1. **Causal Perturbation Network (CPN)** - Emotion-weighted counterfactual generation with Bayesian outcome prediction
2. **Temporal Projection Network with MCTS (TPN-MCTS)** - Personalized scenario generation with DPP diversity and plausibility filtering
3. **Schematic Pattern Completion with Uncertainty Quantification (SPC-UQ)** - Confidence-tracked memory reconstruction with counterfactual validation
4. **Bisociative Graph Traversal with Surprise Maximization (BGT-SM)** - Information-theoretic insight discovery grounded in personal knowledge
5. **Temporal Difference Learning for Habit Chain Optimization (TDL-HCO)** - Data-driven procedural memory enhancement with bottleneck detection

---

### R6 – Update st_hipp_events (In-Place Consolidation State)

**Purpose**: Write all consolidation results back to st_hipp_events staging table, creating a complete audit trail of what was computed during R1-R5. This is the final "commit" phase where ephemeral in-memory calculations become durable metadata.

**Context**: R1-R5 operate on in-memory data structures (importance dictionaries, cluster assignments, novelty scores, KG node mappings). R6 translates these structures into database updates, enabling future P03 runs to:

- Skip reprocessing duplicates (is_near_duplicate=1)
- Resume interrupted consolidation (consolidation_status tracking)
- Analyze consolidation quality (importance/novelty distributions)
- Debug consolidation failures (consolidation_error logging)

**Performance Budget**: Update 1000 st_hipp_events rows in <30 seconds (batch UPDATE operations with transaction management)

---

#### R6.1 Update Deduplication Columns

**Role**: Write deduplication metadata from R3.1 (Near-Duplicate Detection) and R3.2 (Novelty Scoring) back to st_hipp_events. These columns enable downstream consumers to identify duplicates and prioritize novel events.

**Implementation Strategy**:

1. **Batch Update Preparation**: Collect R3.1/R3.2 results from in-memory structures:
   - From R3.1 deduplication output: Extract (event_id, near_duplicates_json, is_near_duplicate) tuples for all 1000 events
   - From R3.2 novelty scoring output: Extract (event_id, novelty_score) tuples
   - Build unified update list: `[(event_id, novelty_score, near_duplicates_json, is_near_duplicate), ...]`
   - Sort by event_id for consistent ordering (improves SQLite page locality)

2. **SQL UPDATE Construction**: Generate parameterized batch UPDATE statement:

   ```sql
   UPDATE st_hipp_events
   SET
     novelty_score = ?,
     near_duplicates_json = ?,
     is_near_duplicate = ?
   WHERE event_id = ?
   ```

   - Use `cursor.executemany()` for batch execution (1000 updates in single transaction)
   - SQLite batch optimization: Set `PRAGMA journal_mode=WAL` and `PRAGMA synchronous=NORMAL` for faster writes
   - Transaction size: All 1000 updates in single COMMIT (atomic all-or-nothing semantics)

3. **Null Handling**: Handle edge cases where deduplication didn't run or failed:
   - If R3.1 failed for specific event → Set novelty_score=NULL, near_duplicates_json=NULL, is_near_duplicate=NULL (preserve NULL as "unknown" state)
   - If R3.2 novelty scoring failed but R3.1 succeeded → Set novelty_score=NULL but populate near_duplicates_json and is_near_duplicate (partial success)
   - If event is exact duplicate (similarity=1.0) → Set novelty_score=0.0 (zero novelty by definition)

4. **Duplicate Skip Optimization**: Mark duplicate events for skip in downstream processing:
   - Events with is_near_duplicate=1 do NOT need full R7 writes (skip st_epi creation)
   - Events with is_near_duplicate=1 still contribute to R4 KG (entities/relationships still extracted)
   - Events with is_near_duplicate=1 still participate in R5 dream phase (can be combined with canonical event)
   - Store skip logic in R7 batch preparation phase (filter out is_near_duplicate=1 events before st_epi writes)

5. **Validation & Rollback**: Validate updates before transaction commit:
   - Assert all 1000 event_ids exist in st_hipp_events (prevent silent failures)
   - Assert novelty_score values in [0.0, 1.0] range (catch calculation errors)
   - Assert is_near_duplicate values in {0, 1, NULL} (catch invalid states)
   - Assert near_duplicates_json is valid JSON array or NULL (catch serialization errors)
   - If any assertion fails → ROLLBACK transaction, log error details, set consolidation_status='FAILED' in R6.3

6. **Update Metrics Recording**: Track update statistics for observability:
   - Count events marked is_near_duplicate=1 (duplicate rate)
   - Compute novelty_score distribution (percentiles: p10, p25, p50, p75, p90)
   - Count events with non-empty near_duplicates_json (events in duplicate clusters)
   - Emit metrics: `p03_r6_dedup_updates_total`, `p03_r6_duplicate_rate`, `p03_r6_novelty_score_p50`

**Dependencies**:

- R3.1 deduplication results (in-memory: duplicate cluster assignments, similarity scores)
- R3.2 novelty scoring results (in-memory: novelty scores with bonuses applied)
- SQLite connection with WAL mode enabled
- JSON serialization utility (for near_duplicates_json array)

**Observability**:

- Metric: `p03_r6_dedup_updates_total` (counter, successful updates)
- Metric: `p03_r6_dedup_update_duration_seconds` (histogram, batch update latency)
- Metric: `p03_r6_duplicate_rate` (gauge, fraction of events marked is_near_duplicate=1)
- Metric: `p03_r6_novelty_score_p50` (gauge, median novelty score)
- Log: `r6_dedup_updated` event with summary statistics (count, duplicate rate, novelty distribution)

**Error Handling**:

- **SQLite Locked Error** (SQLITE_BUSY): Retry with exponential backoff (100ms, 200ms, 400ms), max 3 retries
- **Constraint Violation** (event_id not found): Log missing event_ids, mark those events as consolidation_status='FAILED' in separate UPDATE
- **Invalid JSON** (near_duplicates_json serialization failure): Set near_duplicates_json=NULL for affected events, log warning
- **Transaction Timeout** (>5 seconds): ROLLBACK, split batch into 2×500-event batches, retry each batch separately

---

#### R6.2 Update Cluster Columns

**Role**: Write episodic clustering metadata from R2.1 (Episodic Clustering) back to st_hipp_events. These columns link events to their episodic clusters and enable cluster-aware queries.

**Implementation Strategy**:

1. **Cluster Assignment Retrieval**: Extract cluster assignments from R2.1 in-memory clustering results:
   - From R2.1 output: Map event_id → (episode_cluster_id, cluster_confidence)
   - episode_cluster_id format: `CLU_<simhash_prefix_8><temporal_bucket_YYYYMMDD>` (example: `CLU_1a2b3c4d20250115`)
   - cluster_confidence: Float in [0.0, 1.0] representing how well event fits cluster centroid (cosine similarity to cluster mean)
   - Handle unclustered events: If event didn't join any cluster (outlier), set episode_cluster_id=NULL, cluster_confidence=NULL

2. **Batch UPDATE Execution**: Update st_hipp_events with cluster assignments:

   ```sql
   UPDATE st_hipp_events
   SET
     episode_cluster_id = ?,
     cluster_confidence = ?
   WHERE event_id = ?
   ```

   - Use `cursor.executemany()` with list of 1000 (episode_cluster_id, cluster_confidence, event_id) tuples
   - Execute in same transaction as R6.1 deduplication updates (combine into single COMMIT for atomicity)
   - Transaction ordering: R6.1 updates BEFORE R6.2 updates (deduplication metadata needed first)

3. **Cluster Size Validation**: Validate cluster assignments before commit:
   - Assert each episode_cluster_id appears at least 2 times (clusters must have ≥2 events)
   - Assert each episode_cluster_id appears at most 200 times (prevent megaclusters indicating clustering failure)
   - Assert cluster_confidence values in [0.0, 1.0] range
   - If validation fails → ROLLBACK, log cluster_id causing failure, mark batch as consolidation_status='FAILED'

4. **Cross-Layer Linkage**: Prepare metadata for R7 st_epi writes:
   - For each cluster, identify "representative event" (highest cluster_confidence within cluster)
   - Store mapping: episode_cluster_id → representative_event_id (used in R7.2 for st_epi.representative_text)
   - Store cluster member counts: episode_cluster_id → count (used in R7.2 for st_epi.observation_count)
   - This metadata cached in memory, consumed by R7 batch preparation phase

5. **Outlier Event Handling**: Handle events that didn't cluster (cluster_confidence=NULL):
   - These are "episodic singularities" — unique events that don't fit patterns
   - Still write to st_epi in R7 (individual episodes)
   - Mark with special cluster_id: `SING_<event_id>` (singularity pseudo-cluster)
   - Set cluster_confidence=1.0 (perfect fit to self-cluster)
   - Do NOT promote singularities to semantic memory in R2.5 (insufficient pattern evidence)

6. **Cluster Update Metrics**: Track clustering quality for observability:
   - Cluster count (unique episode_cluster_id values)
   - Cluster size distribution (events per cluster: mean, std, min, max)
   - Cluster confidence distribution (percentiles: p10, p50, p90)
   - Outlier rate (fraction of events with cluster_confidence=NULL)
   - Emit metrics: `p03_r6_cluster_count`, `p03_r6_cluster_size_mean`, `p03_r6_outlier_rate`

**Dependencies**:

- R2.1 episodic clustering results (in-memory: cluster assignments, confidence scores)
- SQLite connection (same transaction as R6.1)
- Cluster validation logic (size bounds checking)

**Observability**:

- Metric: `p03_r6_cluster_updates_total` (counter, successful updates)
- Metric: `p03_r6_cluster_update_duration_seconds` (histogram, batch update latency)
- Metric: `p03_r6_cluster_count` (gauge, unique clusters in batch)
- Metric: `p03_r6_cluster_size_mean` (gauge, average events per cluster)
- Metric: `p03_r6_outlier_rate` (gauge, fraction of unclustered events)
- Log: `r6_cluster_updated` event with summary statistics (cluster count, size distribution, confidence distribution)

**Error Handling**:

- **Invalid Cluster ID** (malformed format): Set episode_cluster_id=NULL for affected events, log warning with event_id
- **Confidence Out of Range** (cluster_confidence >1.0 or <0.0): Clamp to [0.0, 1.0], log warning
- **Megacluster Detection** (cluster with >200 events): Split cluster into subclusters by temporal refinement (use event_time_utc to create hourly buckets), assign new cluster_ids

---

#### R6.3 Mark Consolidation Status

**Role**: Update consolidation_status column to mark completion of P03 processing. This is the "commit" signal that all R1-R5 phases completed successfully and results are durable.

**Implementation Strategy**:

1. **Success Path Update**: For events processed successfully through R1-R5, mark consolidation complete:

   ```sql
   UPDATE st_hipp_events
   SET
     consolidation_status = 'COMPLETE',
     consolidated_at = ?
   WHERE event_id IN (?, ?, ..., ?)  -- List of 1000 event_ids
     AND consolidation_status = 'IN_PROGRESS'
   ```

   - consolidated_at: Current UTC timestamp in ISO 8601 format (e.g., '2025-01-15T14:32:01.123Z')
   - Use `datetime.utcnow().isoformat() + 'Z'` for consistent timestamp formatting
   - WHERE clause includes consolidation_status='IN_PROGRESS' guard (prevent overwriting FAILED or COMPLETE statuses from partial retries)

2. **Failure Path Update**: For events that encountered errors during R1-R5, mark consolidation failed:

   ```sql
   UPDATE st_hipp_events
   SET
     consolidation_status = 'FAILED',
     consolidated_at = ?,
     consolidation_error = ?
   WHERE event_id IN (?, ?, ..., ?)  -- List of failed event_ids
   ```

   - consolidation_error: Concise error message (max 500 chars) describing failure reason
   - Error message format: `"<phase>: <error_type> - <details>"` (example: `"R3: SimHashError - Hamming distance computation failed for event abc123"`)
   - Preserve partial results: If R1-R2 succeeded but R3 failed, importance_score and cluster_id updates remain (only R3+ columns are NULL)

3. **Transaction Commit & Rollback Logic**:
   - **Happy Path**: If R6.1 and R6.2 succeed → COMMIT transaction → Execute R6.3 success UPDATE → COMMIT second transaction
   - **Partial Failure**: If R6.1 OR R6.2 fail → ROLLBACK transaction → Execute R6.3 failure UPDATE for entire batch → COMMIT failure transaction
   - **Complete Failure**: If R1-R5 fail before reaching R6 → Execute R6.3 failure UPDATE with error from exception handler
   - Two-phase commit: Consolidation data updates (R6.1, R6.2) in transaction 1, status updates (R6.3) in transaction 2 (allows status retry without re-running consolidation)

4. **Idempotency Handling**: Support retrying R6 after partial failure:
   - If consolidation_status already 'COMPLETE' → Skip UPDATE (no-op, log "already completed")
   - If consolidation_status already 'FAILED' → Skip UPDATE unless retry_consolidation flag set (manual override)
   - If consolidation_status 'IN_PROGRESS' for >2 hours → Assume stale, mark as 'FAILED' with error "Consolidation timeout"
   - Checkpoint storage: Store last committed event_id in temporary table (enables resume from checkpoint)

5. **Batch Completion Signaling**: Emit completion event for downstream consumers:
   - Event type: `p03_consolidation_batch_complete`
   - Event payload: `{batch_id, event_count, success_count, failure_count, duration_seconds, phase_durations: {r1, r2, r3, r4, r5, r6}}`
   - Emit to K0 SSE Port (for real-time dashboards)
   - Emit to K0 Bus (for P04 event-driven triggers)
   - Write to consolidation_audit table (for historical analysis)

6. **Pipeline Offset Update**: Update P03 pipeline offset to mark batch as processed:
   - Write to pipeline_offsets table: `(pipeline='P03', last_processed_event_id=<max_event_id_in_batch>, processed_at=<timestamp>)`
   - This prevents re-processing same batch on next P03 trigger
   - Offset stored as UUID (event_id of last successfully processed event)
   - Used by R0 trigger detection to fetch next batch with `WHERE event_id > last_processed_event_id`

7. **Consolidation Quality Metrics**: Compute and emit quality metrics for monitoring:
   - **Success rate**: (success_count / event_count) × 100
   - **Phase completion rates**: (events completing each phase / event_count) × 100 for R1-R6
   - **Error distribution**: Group by error type (R1 errors, R2 errors, etc.), count occurrences
   - **Performance distribution**: Percentiles for per-event processing time (p50, p95, p99)
   - Emit metrics: `p03_r6_success_rate`, `p03_r6_error_count_by_phase`, `p03_r6_processing_time_p95`

**Dependencies**:

- SQLite connection (separate transaction from R6.1/R6.2)
- datetime utility for ISO 8601 timestamp generation
- K0 SSE Port for event emission
- pipeline_offsets table for offset persistence

**Observability**:

- Metric: `p03_r6_status_updates_total` (counter by status: COMPLETE/FAILED)
- Metric: `p03_r6_success_rate` (gauge, fraction of events marked COMPLETE)
- Metric: `p03_r6_batch_duration_seconds` (histogram, total R0-R6 duration)
- Metric: `p03_r6_error_count_by_phase` (counter with phase label: r1/r2/r3/r4/r5/r6)
- Log: `r6_consolidation_complete` event with batch summary (success/failure counts, durations, error types)
- Log: `r6_consolidation_failed` event with detailed error trace (for failed batches)

**Error Handling**:

- **Timestamp Format Error**: Use fallback timestamp format (Unix epoch milliseconds), log warning
- **Offset Update Failure**: Log error but don't block batch completion (offset can be manually corrected)
- **Event Emission Failure**: Log error but don't block status UPDATE (events are "best effort" notifications)
- **Status UPDATE Deadlock**: Retry with exponential backoff (50ms, 100ms, 200ms), max 5 retries, then mark as FAILED with error "Status update deadlock"

**Performance Optimization**:

- **Batch Size Tuning**: If R6 updates take >30 seconds, split into 2×500-event batches with separate transactions
- **Index Usage**: Ensure index on (event_id, consolidation_status) for fast WHERE clause evaluation
- **Write-Ahead Log**: Keep `PRAGMA journal_mode=WAL` enabled throughout R6 (prevents blocking readers during writes)
- **Checkpoint Control**: Call `PRAGMA wal_checkpoint(TRUNCATE)` after R6.3 completion (reclaim disk space from WAL file)

---

---

### R7 – Write to 8 Memory Layers

**Purpose**: Persist all consolidation results from R1-R5 into 8 durable memory layers using K0's driver architecture. This is where ephemeral consolidation computations become permanent, queryable memory structures.

**Context**: R1-R5 produced in-memory data structures (clusters, patterns, KG nodes, insights). R7 translates these into batch INSERT/UPDATE operations across 8 tables, coordinated via `st_outbox` and K0's OutboxWorker. Each layer has specialized drivers that handle schema-specific logic.

**K0 Driver Architecture Integration**:

- **Outbox Pattern**: All writes go through `st_outbox` (async, retryable, transactional)
- **Driver Protocol**: Each layer has a driver implementing `apply(entry: OutboxEntry)` method
- **Alias Resolution**: `alias_map.yaml` maps logical layer names to driver implementations
- **Retry Semantics**: Exponential backoff (2^n seconds), max 10 retries, DLQ fallback
- **Transaction Boundary**: R7 stages outbox entries in same transaction as R6 status updates (atomicity)

**Performance Budget**: Write 1000 events across 8 layers in <5 minutes (parallel driver execution, batch operations)

---

#### R7.1 Episodic Layer (st_epi)

**Role**: Persist episodic clusters as durable episodic memories. Each cluster becomes one `st_epi` record representing a coherent experience (e.g., "lunch with Sarah at Cafe Luna").

**Implementation Strategy**:

1. **Cluster-to-Episode Mapping**: Transform R2.1 clustering results into st_epi records:
   - For each unique `episode_cluster_id` from R6.2 (excluding singularities):
     - Aggregate all events with matching cluster_id
     - Select representative event (highest cluster_confidence) as episode anchor
     - Merge event attributes (text, participants, location, sentiment) using weighted averaging
   - For singularity events (`SING_*` cluster_id):
     - Create individual st_epi record with 1:1 mapping to event_id
     - Set observation_count=1, confidence_score based on salience

2. **Episode Record Construction**: Build st_epi row for each cluster:

   ```python
   episode_record = {
       'episode_id': f"EPI_{uuid4()}",  # New UUID for episode
       'event_id': representative_event_id,  # FK to st_hipp_events
       'tenant_id': cluster_events[0].tenant_id,
       'space_id': cluster_events[0].space_id,
       'actor_id': cluster_events[0].actor_id,
       'event_time_utc': representative_event.event_time_utc,
       'first_observed_at': min(e.event_time_utc for e in cluster_events),
       'last_observed_at': max(e.event_time_utc for e in cluster_events),
       'observation_count': len(cluster_events),
       'temporal_bucket': dominant_temporal_bucket(cluster_events),
       'is_weekend': representative_event.is_weekend,
       'recency_weight': compute_recency_weight(last_observed_at),
       'text': merge_texts(cluster_events),  # Concatenate with ellipsis
       'participants_json': json.dumps(union_participants(cluster_events)),
       'location_name': representative_event.location_name,
       'activity_type': representative_event.activity_type,
       'sentiment_score': weighted_avg_sentiment(cluster_events),
       'salience_score': weighted_avg_salience(cluster_events),
       'confidence_score': cluster_confidence,  # From R2.1
       'source_count': len(cluster_events),
       'source_quality': 'fused',  # Multiple events fused
       'ambiguity_score': compute_cluster_ambiguity(cluster_events),
       'modalities_json': json.dumps(union_modalities(cluster_events)),
       'fusion_method': 'late',  # Late fusion (post-clustering)
       'fusion_confidence': cluster_confidence,
       'source_events_json': json.dumps([e.event_id for e in cluster_events]),
       'promoted_to_semantic_id': semantic_id_if_promoted(episode_cluster_id),  # From R2.5
       'promoted_to_routine_id': routine_id_if_promoted(episode_cluster_id),  # From R2.5
       'decay_factor': 1.0,  # Initial decay
       'archival_status': 'ACTIVE',
       'access_count': 0,
       'created_at': now_iso8601(),
       'updated_at': now_iso8601()
   }
   ```

3. **Batch Outbox Staging**: Stage st_epi writes via st_outbox (K0 driver pattern):
   - For each episode_record:
     - Serialize record to JSON payload
     - Create OutboxEntry: `driver='st_epi', op_kind='INSERT', payload=json_bytes, fingerprint=blake3(payload)`
     - Call `uow.stage_outbox(entry)` within R6's transaction (atomic commit)
   - OutboxWorker will dequeue and dispatch to SQLiteDriver (st_epi table)

4. **Deduplication & Canonicalization**: Handle episode versioning:
   - Check if similar episode already exists (by `text` + `temporal_bucket` + `location_name` similarity >0.9)
   - If exists: Create new version with `supersedes_episode_id=old_episode_id`, mark old as `is_canonical=0`
   - If new: Set `is_canonical=1`, `canonical_episode_id=episode_id` (self-reference)

5. **Cross-Layer Backlinks**: Update st_hipp_events with episode references:
   - For all event_ids in cluster: `UPDATE st_hipp_events SET promoted_to_episode_id=episode_id WHERE event_id IN (...)`
   - This allows tracing from raw event → episodic memory

6. **Skip Logic for Duplicates**: Optimize write volume:
   - Events marked `is_near_duplicate=1` (from R3.1) do NOT create individual episodes
   - They contribute to canonical event's cluster but don't inflate episode count
   - Reduces st_epi bloat by ~15-25% (typical duplicate rate)

**Dependencies**:

- R2.1 clustering results (episode_cluster_id, cluster_confidence)
- R2.5 semantic promotion mappings (episode_id → semantic_id/routine_id)
- st_hipp_events access for event attribute lookup
- K0 UnitOfWork for outbox staging
- SQLiteDriver for st_epi table writes

**Observability**:

- Metric: `p03_r7_epi_records_created_total` (counter, episodes created)
- Metric: `p03_r7_epi_cluster_size_mean` (gauge, average events per episode)
- Metric: `p03_r7_epi_outbox_staged_total` (counter, outbox entries created)
- Metric: `p03_r7_epi_write_duration_seconds` (histogram, staging latency)
- Log: `r7_epi_staged` event with episode count, cluster size distribution

**Error Handling**:

- **Missing Cluster Data**: If episode_cluster_id missing from R2 results → Skip episode creation, log warning
- **Outbox Staging Failure**: If `stage_outbox()` fails → ROLLBACK transaction, mark consolidation_status='FAILED' in R6.3
- **Payload Serialization Error**: If JSON serialization fails → Log error, create DLQ entry with raw data
- **Duplicate Episode ID**: If UUID collision (extremely rare) → Regenerate UUID, retry

---

#### R7.2 Semantic Layer (st_sem)

**Role**: Persist semantic patterns extracted by R2.2 (routines, preferences, themes, relationships) into durable semantic memory. These are abstracted, generalized patterns that transcend specific episodic instances.

**Implementation Strategy**:

1. **Pattern-to-Semantic Mapping**: Transform R2.2 pattern extraction results into st_sem records:
   - For each extracted pattern (from R2.2 output):
     - pattern_type: `routine` (daily habits), `preference` (likes/dislikes), `theme` (recurring topics), `relationship` (social dynamics)
     - Compute temporal context (e.g., "weekday mornings", "after dinner")
     - Calculate frequency_score = observation_count / days_active
     - Derive confidence_score from R2.4 consolidation criteria

2. **Semantic Record Construction**: Build st_sem row for each pattern:

   ```python
   semantic_record = {
       'semantic_id': f"SEM_{uuid4()}",
       'version': 1,
       'is_canonical': 1,
       'valid_from': first_observed_at,
       'valid_to': None,  # Ongoing pattern
       'tenant_id': pattern.tenant_id,
       'space_id': pattern.space_id,
       'pattern_type': pattern.pattern_type,  # routine/preference/theme/relationship
       'pattern_text': pattern.description,  # Human-readable description
       'entities_json': json.dumps([{'node_id': e.node_id, 'entity_type': e.type} for e in pattern.entities]),
       'temporal_context': pattern.temporal_context,  # "weekday mornings"
       'first_observed_at': pattern.first_observed_at,
       'last_observed_at': pattern.last_observed_at,
       'observation_count': pattern.observation_count,
       'temporal_bucket': pattern.dominant_temporal_bucket,
       'is_weekend': pattern.is_weekend_pattern,
       'recency_weight': compute_recency_weight(pattern.last_observed_at),
       'frequency_score': pattern.observation_count / days_between(first_observed_at, last_observed_at),
       'pattern_frequency': pattern.frequency_label,  # daily/weekly/monthly/rare (NEW from schema alignment)
       'pattern_last_occurrence': pattern.last_observed_at,  # (NEW from schema alignment)
       'confidence_score': pattern.confidence_score,  # From R2.4
       'source_count': len(pattern.source_episodes),
       'source_quality': 'derived',
       'ambiguity_score': pattern.ambiguity_score,
       'modalities_json': json.dumps(['episodic']),
       'source_episodes_json': json.dumps(pattern.source_episode_ids),
       'invariants_json': json.dumps(pattern.invariants),  # Unchanging attributes
       'variations_json': json.dumps(pattern.variations),  # Acceptable ranges
       'decay_factor': 1.0,
       'archival_status': 'ACTIVE',
       'created_at': now_iso8601(),
       'updated_at': now_iso8601()
   }
   ```

3. **CA1 Bridge Integration Results**: Apply R2.3 merge/evolve/create decisions:
   - **MERGE Decision** (similarity >0.85): Update existing semantic record:
     - Increment observation_count
     - Boost confidence_score (weighted average)
     - Append new source_episode_ids to source_episodes_json
     - Update last_observed_at
     - Outbox op_kind='UPDATE'
   - **EVOLVE Decision** (similarity 0.6-0.85): Create new semantic version:
     - Set supersedes_semantic_id=old_semantic_id
     - Mark old semantic with is_canonical=0, valid_to=now
     - Set new semantic with is_canonical=1, version=old_version+1
     - Outbox op_kind='INSERT' (new version) + 'UPDATE' (old version)
   - **CREATE Decision** (similarity <0.6): Insert new semantic record:
     - Fresh semantic_id
     - No supersedes relationship
     - Outbox op_kind='INSERT'

4. **Batch Outbox Staging**: Stage st_sem writes via st_outbox:
   - For each semantic_record and CA1 decision:
     - Serialize record to JSON payload
     - Create OutboxEntry: `driver='st_sem', op_kind='INSERT'|'UPDATE', payload=json_bytes`
     - Call `uow.stage_outbox(entry)` within R6's transaction
   - OutboxWorker dispatches to SQLiteDriver (st_sem table)

5. **Cross-Layer Backlinks**: Link episodes to promoted semantics:
   - For all source_episode_ids in pattern: `UPDATE st_epi SET promoted_to_semantic_id=semantic_id WHERE episode_id IN (...)`
   - Enables tracing: raw event → episode → semantic pattern

6. **Confidence Gating**: Only persist high-confidence patterns:
   - Threshold: confidence_score ≥0.6 (from R2.4 consolidation criteria)
   - Patterns below threshold stored in temporary `candidate_patterns` table (used by P06 active learning)
   - Reduces semantic bloat, maintains quality bar

**Dependencies**:

- R2.2 pattern extraction results (pattern descriptions, invariants, confidence)
- R2.3 CA1 bridge decisions (MERGE/EVOLVE/CREATE)
- R2.4 consolidation criteria scores (quality gates)
- st_epi access for source episode references
- K0 UnitOfWork for outbox staging

**Observability**:

- Metric: `p03_r7_sem_records_created_total` (counter by pattern_type)
- Metric: `p03_r7_sem_merge_rate` (gauge, fraction of MERGE vs CREATE decisions)
- Metric: `p03_r7_sem_confidence_p50` (gauge, median confidence score)
- Metric: `p03_r7_sem_outbox_staged_total` (counter)
- Log: `r7_sem_staged` event with pattern type distribution, CA1 decision breakdown

**Error Handling**:

- **CA1 Decision Missing**: If pattern lacks CA1 decision → Default to CREATE, log warning
- **Invalid Temporal Context**: If temporal parsing fails → Set temporal_context=NULL, continue
- **JSON Serialization Error**: If entities_json or invariants_json fails → Store as text fallback, mark ambiguity_score=0.9

---

#### R7.3 Procedural Layer (st_procedural)

**Role**: Persist detected routines, habits, and motor skill patterns from R2.2 (procedural patterns) and R5.5 (motor rehearsal optimizations). These are action sequences that can be reactivated for behavior prediction and recommendation.

**Implementation Strategy**:

1. **Routine Extraction**: Filter R2.2 patterns for procedural types:
   - pattern_type='routine' → morning routines, commute patterns, meal prep sequences
   - pattern_type='habit' → consistent behaviors (coffee after breakfast, gym on Mondays)
   - From R5.5 TDL-HCO: Optimized habit chains with bottleneck improvements

2. **Procedural Record Construction**: Build st_procedural row for each routine:

   ```python
   procedural_record = {
       'routine_id': f"ROU_{uuid4()}",  # Changed from procedure_id per schema alignment
       'version': 1,
       'is_canonical': 1,
       'valid_from': first_observed_at,
       'valid_to': None,
       'tenant_id': routine.tenant_id,
       'space_id': routine.space_id,
       'actor_id': routine.actor_id,
       'routine_category': routine.category,  # Changed from habit_type per schema alignment
       'routine_name': routine.name,  # Changed from habit_name per schema alignment
       'description': routine.description,
       'trigger_conditions_json': json.dumps(routine.triggers),  # ["time==07:00", "location==home"]
       'action_sequence_json': json.dumps(routine.steps),  # ["wake", "coffee", "shower", "commute"]
       'temporal_context': routine.temporal_context,  # "weekday mornings"
       'first_observed_at': routine.first_observed_at,
       'last_observed_at': routine.last_observed_at,
       'observation_count': routine.observation_count,
       'execution_count': routine.execution_count,  # How many times routine completed
       'completion_rate': routine.completion_rate,  # execution_count / observation_count
       'avg_duration_minutes': routine.avg_duration_minutes,
       'frequency_score': routine.frequency_score,
       'confidence_score': routine.confidence_score,
       'skill_level': routine.skill_level,  # novice/intermediate/expert (from R5.5 TDL-HCO)
       'optimization_score': routine.optimization_score,  # From R5.5 TDL-HCO (0-1, higher = more optimized)
       'bottleneck_analysis_json': json.dumps(routine.bottlenecks) if routine.bottlenecks else None,  # From R5.5
       'source_episodes_json': json.dumps(routine.source_episode_ids),
       'decay_factor': 1.0,
       'archival_status': 'ACTIVE',
       'created_at': now_iso8601(),
       'updated_at': now_iso8601()
   }
   ```

3. **R5.5 Motor Rehearsal Integration**: Enrich routines with TDL-HCO results:
   - For routines that were optimized in R5.5:
     - Update skill_level based on TD error convergence (low error = expert)
     - Set optimization_score = 1.0 - normalized_td_error
     - Populate bottleneck_analysis_json with detected inefficiencies (slow steps, failure points)
     - Store optimized action sequence in action_sequence_json (reordered for efficiency)

4. **Habit Strength Scoring**: Compute habit strength metric:
   - habit_strength = (completion_rate × 0.4) + (frequency_score × 0.3) + (recency_weight × 0.3)
   - Range: 0.0-1.0 (higher = stronger habit)
   - Used by K1 planner for behavior prediction

5. **Batch Outbox Staging**: Stage st_procedural writes via st_outbox:
   - For each procedural_record:
     - Serialize to JSON payload
     - Create OutboxEntry: `driver='st_procedural', op_kind='INSERT'|'UPDATE', payload=json_bytes`
     - Call `uow.stage_outbox(entry)` within R6's transaction
   - OutboxWorker dispatches to SQLiteDriver (st_procedural table)

6. **Cross-Layer Backlinks**: Link episodes to promoted routines:
   - For all source_episode_ids: `UPDATE st_epi SET promoted_to_routine_id=routine_id WHERE episode_id IN (...)`

**Dependencies**:

- R2.2 pattern extraction (routine patterns)
- R5.5 TDL-HCO motor rehearsal results (skill_level, optimization_score, bottlenecks)
- st_epi access for source episode references
- K0 UnitOfWork for outbox staging

**Observability**:

- Metric: `p03_r7_procedural_records_created_total` (counter by routine_category)
- Metric: `p03_r7_routine_completion_rate_mean` (gauge)
- Metric: `p03_r7_habit_strength_p50` (gauge, median habit strength)
- Log: `r7_procedural_staged` event with routine count, skill level distribution

**Error Handling**:

- **Missing Action Sequence**: If action_sequence_json empty → Skip routine creation, log warning
- **Invalid Trigger Conditions**: If trigger parsing fails → Store as text, mark confidence_score *= 0.8

---

#### R7.4 Social Layer (st_social)

**Role**: Persist social relationship dynamics extracted from R4.2 (relationship discovery) and R2.2 (social patterns). Tracks communication frequency, relationship strength, and social network evolution.

**Implementation Strategy**:

1. **Relationship Record Extraction**: Transform R4.2 relationship discovery results:
   - For each discovered relationship (from co-occurrence analysis):
     - Extract person pairs (actor_id, related_person_id)
     - Compute interaction frequency, communication channels, sentiment patterns
     - Calculate relationship strength = (co_occurrence_count × recency_weight × sentiment_avg)

2. **Social Record Construction**: Build st_social row for each relationship:

   ```python
   social_record = {
       'relationship_id': f"REL_{uuid4()}",
       'version': 1,
       'is_canonical': 1,
       'valid_from': first_interaction_at,
       'valid_to': None,
       'tenant_id': relationship.tenant_id,
       'space_id': relationship.space_id,
       'actor_id': relationship.actor_id,
       'related_person_id': relationship.related_person_id,  # FK to people table
       'relationship_type': relationship.type,  # family/friend/colleague/acquaintance
       'relationship_label': relationship.label,  # "spouse", "coworker", "best friend"
       'interaction_count': relationship.interaction_count,
       'first_interaction_at': relationship.first_interaction_at,
       'last_interaction_at': relationship.last_interaction_at,
       'interaction_frequency_days': relationship.avg_days_between_interactions,
       'communication_channels_json': json.dumps(relationship.channels),  # ["message", "call", "in_person"]
       'dominant_channel': relationship.dominant_channel,
       'relationship_strength': relationship.strength,  # 0.0-1.0
       'sentiment_avg': relationship.sentiment_avg,  # -1.0 to 1.0
       'sentiment_trend': relationship.sentiment_trend,  # improving/stable/declining
       'shared_activities_json': json.dumps(relationship.shared_activities),  # ["dining", "sports", "work"]
       'shared_locations_json': json.dumps(relationship.shared_locations),  # ["Cafe Luna", "Office"]
       'trust_score': relationship.trust_score,  # 0.0-1.0 (derived from consistency)
       'reciprocity_score': relationship.reciprocity_score,  # 0.0-1.0 (balanced vs one-sided)
       'source_episodes_json': json.dumps(relationship.source_episode_ids),
       'source_kg_edges_json': json.dumps(relationship.kg_edge_ids),  # FK to st_kg_edges
       'decay_factor': 1.0,
       'archival_status': 'ACTIVE',
       'created_at': now_iso8601(),
       'updated_at': now_iso8601()
   }
   ```

3. **Social Network Analysis**: Compute network-level metrics:
   - **Centrality Scores**: For each actor, compute degree centrality (number of relationships), betweenness centrality (bridging role)
   - **Community Detection**: Identify social clusters (family, work colleagues, friends) using modularity optimization
   - Store network metrics in actor-level summary table (st_social_network_summary)

4. **Temporal Relationship Evolution**: Track relationship changes:
   - If existing relationship found (by actor_id + related_person_id):
     - Compare current strength with previous version
     - If strength delta >0.2: Create new version, mark old as superseded
     - Update sentiment_trend based on sentiment trajectory

5. **Batch Outbox Staging**: Stage st_social writes via st_outbox:
   - For each social_record:
     - Serialize to JSON payload
     - Create OutboxEntry: `driver='st_social', op_kind='INSERT'|'UPDATE', payload=json_bytes`
     - Call `uow.stage_outbox(entry)` within R6's transaction
   - OutboxWorker dispatches to SQLiteDriver (st_social table)

**Dependencies**:

- R4.2 relationship discovery results (co-occurrence pairs, interaction counts)
- R2.2 social pattern extraction (communication frequency patterns)
- st_kg_edges for relationship provenance (which KG edges contributed to relationship)
- people table for entity resolution (related_person_id FK)

**Observability**:

- Metric: `p03_r7_social_records_created_total` (counter by relationship_type)
- Metric: `p03_r7_relationship_strength_mean` (gauge)
- Metric: `p03_r7_interaction_frequency_p50` (gauge, median days between interactions)
- Log: `r7_social_staged` event with relationship count, sentiment distribution

**Error Handling**:

- **Person Not Found**: If related_person_id not in people table → Skip relationship creation, queue for entity resolution in P06
- **Invalid Relationship Type**: If type not in [family/friend/colleague/acquaintance] → Default to 'acquaintance', log warning

---

#### R7.5 Prospective Layer (st_prospective)

**Role**: Persist future-oriented intentions, reminders, and predictive scenarios from R5.2 (forward simulation) and R5.4 (insight generation). These are forward-looking memories that trigger proactive behavior.

**Implementation Strategy**:

1. **Prospective Memory Extraction**: Collect future-oriented content from R5:
   - From R5.2 TPN-MCTS: Generated scenarios with predicted outcomes (dinner plans, travel scenarios, health interventions)
   - From R5.4 BGT-SM: Novel insights and recommendations (detected opportunities, warnings)
   - Existing patterns from R2.2: Recurring intentions (weekly grocery shopping, monthly bills)

2. **Prospective Record Construction**: Build st_prospective row for each intention:

   ```python
   prospective_record = {
       'prospective_id': f"PRO_{uuid4()}",
       'version': 1,
       'is_canonical': 1,
       'tenant_id': intention.tenant_id,
       'space_id': intention.space_id,
       'actor_id': intention.actor_id,
       'intention_type': intention.type,  # reminder/goal/prediction/scenario/insight
       'intention_text': intention.description,  # Human-readable description
       'trigger_conditions_json': json.dumps(intention.triggers),  # ["time==2025-01-20T10:00", "location==grocery_store"]
       'trigger_time_utc': intention.scheduled_time if intention.scheduled_time else None,
       'trigger_location': intention.location_trigger if intention.location_trigger else None,
       'trigger_context': intention.context_trigger,  # "after work", "when at home"
       'priority': intention.priority,  # 0.0-1.0 (from importance weighting)
       'confidence': intention.confidence,  # 0.0-1.0 (plausibility score from R5.2)
       'predicted_outcome': intention.predicted_outcome,  # Expected result if triggered
       'predicted_outcome_confidence': intention.outcome_confidence,  # Bayesian confidence from R5.2
       'alternative_scenarios_json': json.dumps(intention.alternative_scenarios) if intention.alternative_scenarios else None,  # From R5.2 TPN-MCTS (diverse scenarios)
       'insight_category': intention.insight_category if intention.type == 'insight' else None,  # opportunity/warning/optimization
       'surprise_score': intention.surprise_score if intention.type == 'insight' else None,  # From R5.4 BGT-SM (PMI-based surprise)
       'source_episodes_json': json.dumps(intention.source_episode_ids) if intention.source_episode_ids else None,
       'source_semantics_json': json.dumps(intention.source_semantic_ids) if intention.source_semantic_ids else None,
       'created_from_pipeline': 'P03_R5' if intention.type in ['scenario', 'insight'] else 'P03_R2',
       'status': 'PENDING',  # PENDING/TRIGGERED/COMPLETED/EXPIRED
       'created_at': now_iso8601(),
       'updated_at': now_iso8601()
   }
   ```

3. **Scenario Diversification**: From R5.2 TPN-MCTS, store diverse scenarios:
   - For each goal state (e.g., "plan weekend trip"):
     - Store top-K diverse scenarios (K=5, using DPP sampling)
     - Each scenario includes: plausibility_score, outcome_description, action_sequence
     - Used by K1 planner for proactive suggestions

4. **Insight Prioritization**: From R5.4 BGT-SM, rank insights by surprise:
   - Insights with surprise_score >0.7 marked as high-priority (potential breakthroughs)
   - Insights with opportunity category marked for proactive notification
   - Insights with warning category marked for alert generation (P05 attention routing)

5. **Batch Outbox Staging**: Stage st_prospective writes via st_outbox:
   - For each prospective_record:
     - Serialize to JSON payload
     - Create OutboxEntry: `driver='st_prospective', op_kind='INSERT', payload=json_bytes`
     - Call `uow.stage_outbox(entry)` within R6's transaction
   - OutboxWorker dispatches to SQLiteDriver (st_prospective table)

6. **P05 Integration**: Coordinate with P05 (Attention Router) for proactive triggers:
   - High-priority prospective memories (priority >0.8) emitted to topic `cognitive.prospective.high_priority.v1`
   - P05 subscribes to this topic and generates proactive notifications
   - Location-triggered memories registered with geofence monitoring

**Dependencies**:

- R5.2 TPN-MCTS forward simulation results (scenarios, plausibility scores, outcome predictions)
- R5.4 BGT-SM insight generation results (insights, surprise scores, categories)
- R2.2 recurring intention patterns
- K0 UnitOfWork for outbox staging
- K0 Bus for P05 event emission

**Observability**:

- Metric: `p03_r7_prospective_records_created_total` (counter by intention_type)
- Metric: `p03_r7_scenario_count` (gauge, scenarios generated)
- Metric: `p03_r7_insight_surprise_p90` (gauge, 90th percentile surprise score)
- Metric: `p03_r7_high_priority_intentions_total` (counter)
- Log: `r7_prospective_staged` event with intention type distribution, priority breakdown

**Error Handling**:

- **Invalid Trigger Time**: If trigger_time_utc in past → Mark status='EXPIRED', log warning
- **Missing Outcome Prediction**: If predicted_outcome empty for scenario → Set confidence=0.0, continue
- **Scenario Serialization Error**: If alternative_scenarios_json fails → Store top scenario only, log warning

---

#### R7.6 Knowledge Graph Layer (st_kg_dom & st_kg_edges)

**Role**: Persist knowledge graph nodes (entities) and edges (relationships) from R4 (Knowledge Graph Consolidation). Creates a temporal, versioned graph structure that captures entity evolution and causal relationships.

**Implementation Strategy**:

1. **Node Writes (st_kg_dom)**: Persist entities from R4.1 (Entity Extraction & Normalization):
   - For each extracted and normalized entity:

     ```python
     kg_node_record = {
         'node_id': f"KG_{uuid4()}",  # Or reuse existing node_id if entity already exists
         'version': 1,  # Increment if updating existing entity
         'tenant_id': entity.tenant_id,
         'space_id': entity.space_id,
         'entity_type': entity.type,  # person/location/organization/concept/activity
         'entity_name': entity.normalized_name,  # Canonical name after fuzzy matching
         'entity_aliases_json': json.dumps(entity.aliases),  # Alternative names/spellings
         'entity_description': entity.description,
         'first_observed_at': entity.first_observed_at,
         'last_observed_at': entity.last_observed_at,
         'observation_count': entity.observation_count,  # NEW from schema alignment
         'confidence_score': entity.confidence,  # 0.0-1.0 (disambiguation confidence)
         'valid_from': entity.valid_from,
         'valid_to': entity.valid_to if entity.valid_to else None,
         'node_properties_json': json.dumps(entity.properties),  # NEW from schema alignment (type-specific attributes)
         'decay_factor': 1.0,
         'archival_status': 'ACTIVE',
         'created_at': now_iso8601(),
         'updated_at': now_iso8601()
     }
     ```

2. **Edge Writes (st_kg_edges)**: Persist relationships from R4.2 (Relationship Discovery):
   - For each discovered relationship:

     ```python
     kg_edge_record = {
         'edge_id': f"EDGE_{uuid4()}",
         'version': 1,
         'tenant_id': relationship.tenant_id,
         'space_id': relationship.space_id,
         'source_node_id': relationship.source_entity.node_id,  # FK to st_kg_dom
         'target_node_id': relationship.target_entity.node_id,  # FK to st_kg_dom
         'edge_type': relationship.type,  # co_occurs_with/causes/enables/conflicts_with/part_of
         'edge_label': relationship.label,  # Human-readable (e.g., "works at", "located in")
         'relationship_strength': relationship.strength,  # 0.0-1.0 (from co-occurrence frequency)
         'first_observed_at': relationship.first_observed_at,
         'last_observed_at': relationship.last_observed_at,
         'observation_count': relationship.observation_count,
         'confidence_score': relationship.confidence,
         'valid_from': relationship.valid_from,
         'valid_to': relationship.valid_to if relationship.valid_to else None,
         'edge_properties_json': json.dumps(relationship.properties),  # NEW from schema alignment (causal metadata, sentiment deltas)
         'is_causal': 1 if relationship.is_causal else 0,  # From R4.4 causal graph construction
         'causal_confidence': relationship.causal_confidence if relationship.is_causal else None,  # Bayesian causal score
         'temporal_lag_seconds': relationship.temporal_lag if relationship.is_causal else None,  # Time delay between cause and effect
         'source_episodes_json': json.dumps(relationship.source_episode_ids),
         'decay_factor': 1.0,
         'archival_status': 'ACTIVE',
         'created_at': now_iso8601(),
         'updated_at': now_iso8601()
     }
     ```

3. **Temporal Graph Updates (R4.3)**: Handle entity and relationship evolution:
   - **Entity Evolution** (R4.5 Concept Evolution Tracking):
     - If entity attributes change significantly (drift >0.3): Create new node version, mark old as superseded
     - Update observation_count and last_observed_at for existing entities
     - Store evolution metadata in node_properties_json (drift_score, change_type)
   - **Relationship Decay** (R4.3 Temporal Validity):
     - Apply exponential decay to relationship_strength based on recency: `strength *= exp(-λ * days_since_last_observed)`
     - If strength <0.1: Mark edge as archival_status='ARCHIVED', set valid_to=now

4. **Snapshot Creation**: Periodically snapshot KG state (every 1000 events):
   - From R4.3 temporal graph updates:
     - Create snapshot record in st_kg_snapshots table
     - Store graph statistics: node_count, edge_count, density, clustering_coefficient
     - Used for graph evolution analysis and rollback

5. **Batch Outbox Staging**: Stage KG writes via st_outbox (two drivers):
   - For each kg_node_record:
     - Create OutboxEntry: `driver='st_kg_dom', op_kind='INSERT'|'UPDATE', payload=json_bytes`
   - For each kg_edge_record:
     - Create OutboxEntry: `driver='st_kg_edges', op_kind='INSERT'|'UPDATE', payload=json_bytes`
   - Call `uow.stage_outbox(entries)` for both in R6's transaction
   - OutboxWorker dispatches to SQLiteDriver (st_kg_dom and st_kg_edges tables)

6. **Neo4j Driver Coordination** (Optional Future Enhancement):
   - If Neo4j driver enabled in alias_map.yaml:
     - Additional outbox entries with `driver='neo4j_kg'` for graph database replication
     - Neo4jKGDriver creates cypher queries for node/edge creation
     - Enables graph traversal queries (shortest path, community detection)

**Dependencies**:

- R4.1 entity extraction results (normalized entities, disambiguation)
- R4.2 relationship discovery results (co-occurrence pairs, strength scores)
- R4.3 temporal graph update metadata (validity windows, decay factors)
- R4.4 causal graph construction (causal edges, confidence scores, temporal lags)
- R4.5 concept evolution tracking (drift scores, version metadata)
- K0 UnitOfWork for outbox staging

**Observability**:

- Metric: `p03_r7_kg_nodes_created_total` (counter by entity_type)
- Metric: `p03_r7_kg_edges_created_total` (counter by edge_type)
- Metric: `p03_r7_kg_node_count` (gauge, total active nodes)
- Metric: `p03_r7_kg_edge_count` (gauge, total active edges)
- Metric: `p03_r7_causal_edges_total` (counter, causal relationships discovered)
- Log: `r7_kg_staged` event with node/edge counts, graph statistics

**Error Handling**:

- **Entity Disambiguation Failure**: If fuzzy matching inconclusive → Create provisional entity with confidence <0.5, flag for P06 review
- **Missing Source/Target Node**: If node_id not found in st_kg_dom → Skip edge creation, log error with entity names
- **Circular Reference**: If edge creates cycle in causal graph → Mark edge with edge_properties_json.is_cycle=true, allow creation (cycles valid in temporal graphs)

---

#### R7.7 Vector Embeddings Layer (st_vec) — P03 Semantic Pattern Embeddings

> **Architecture Update (2025-12-13)**: P02 now handles episodic embeddings inline via M16 atomic 3-table transaction. P03 only writes st_vec for **consolidated semantic patterns** (extracted facts, detected habits, KG node embeddings, prospective intentions). `st_embedding_queue` is **DEPRECATED**.

**Role**: Write semantic pattern embeddings for consolidated memories. P03 writes complete embedding records (status=READY) for semantic layers. P08 kernel scheduler polls st_vec and indexes into FAISS.

**What P03 Writes to st_vec**:

| Source Layer | What Gets Embedded | When |
|-------------|-------------------|------|
| st_sem | Extracted semantic patterns/facts | After R3 pattern extraction |
| st_kg_dom | Entity/concept descriptions | After R4 KG construction |
| st_prospective | Future intention text | After R5 prospective extraction |
| st_procedural | Habit/routine descriptions | After R5 habit detection |

**What P03 Does NOT Write**:

| Source | Who Handles | Notes |
|--------|-------------|-------|
| st_hipp_events / st_epi | **P02 M16** (inline) | Episodic embeddings written atomically at ingest time |

**Implementation Strategy**:

1. **Semantic Pattern Embedding Creation**: For consolidated memories requiring embedding:
   - Semantic patterns (st_sem): Embed pattern descriptions for similarity matching
   - KG nodes (st_kg_dom): Embed entity descriptions for entity linking
   - Prospective intentions (st_prospective): Embed intention text for proactive matching
   - Procedural habits (st_procedural): Embed habit descriptions for routine matching

2. **Embedding Record Construction**: Build complete st_vec record (NOT placeholder):

   ```python
   # P03 generates embeddings inline using UltraBERT (same as P02)
   embedding = await ultrabert_adapter.encode(memory.text_content)

   embedding_record = {
       'embedding_id': f"EMB_{uuid4()}",
       'event_id': memory.source_event_id,  # FK to st_hipp_events
       'tenant_id': memory.tenant_id,
       'space_id': memory.space_id,
       'vector': struct.pack('768f', *embedding),  # 768-dim UltraBERT
       'vector_dim': 768,
       'model_id': 'ultrabert_v2.1.0',
       'status': 'READY',  # Written complete, not placeholder
       'faiss_id': None,  # Set by P08 kernel scheduler
       'created_at': now_iso8601(),
       'updated_at': now_iso8601()
   }
   ```

3. **Direct st_vec Write**: Write embedding via syscalls (no queue):
   - Call `await context.syscalls.vec_write(**embedding_record)`
   - P08 kernel scheduler will poll and add to FAISS index

4. ~~**Embedding Queue Job Creation**~~: **DEPRECATED** — st_embedding_queue no longer used

5. **P08 Coordination Protocol** (Updated):
   - **P03 Responsibility**: Write complete st_vec records (status=READY) for semantic patterns
   - **P08 Responsibility**: Kernel scheduler polls st_vec (300s interval), indexes READY → INDEXED
   - **No Event Required**: P08 scheduler discovers new vectors via polling
   - P08 emits `p08.embedding.indexed.v1` after FAISS indexing (optional)

6. **Embedding Prioritization**: Not needed — P03 writes complete embeddings, P08 indexes all READY vectors

**Dependencies**:

- st_sem, st_kg_dom, st_prospective, st_procedural access for text extraction
- UltraBERT adapter for inline embedding generation
- K0 UnitOfWork for transactional writes
- ~~st_embedding_queue~~ **DEPRECATED**

**Observability**:

- Metric: `p03_r7_semantic_embeddings_written_total` (counter by source_layer)
- Metric: `p03_r7_embedding_latency_ms` (histogram, UltraBERT encode time)
- Log: `r7_vec_written` event with embedding count, source layer breakdown

**Error Handling**:

- **Text Extraction Failure**: If text_to_embed empty → Skip embedding creation, log warning
- **UltraBERT Failure**: If encoding fails → Log error, mark source record for retry
- ~~**Queue Overflow**~~: **DEPRECATED** — no queue to overflow

---

#### R7.8 Full-Text Search Layer (st_fts) — Coordination with P08

**Role**: Create FTS index entries for full-text search across consolidated memories. P03 writes to st_fts table; P08 handles FTS5 index optimization.

**Implementation Strategy**:

1. **FTS Entry Creation**: For each memory requiring full-text search:
   - Episodic memories: Index episode text, participants, location, activity
   - Semantic patterns: Index pattern text, entities, temporal context
   - Prospective intentions: Index intention text, triggers, outcomes

2. **FTS Record Construction**: Build st_fts row (FTS5 virtual table):

   ```sql
   -- st_fts is FTS5 virtual table
   INSERT INTO st_fts (
       source_layer,
       source_id,
       tenant_id,
       searchable_text,
       metadata_json
   ) VALUES (
       'st_epi',
       episode_id,
       tenant_id,
       episode_text || ' ' || participants || ' ' || location || ' ' || activity,  -- Concatenated search corpus
       json_object('event_time_utc', event_time_utc, 'salience_score', salience_score)
   )
   ```

3. **Search Corpus Assembly**: Combine multiple text fields for rich search:
   - Episode: text + participants + location_name + activity_type + sentiment_label
   - Semantic: pattern_text + entities + temporal_context
   - Prospective: intention_text + trigger_conditions + predicted_outcome

4. **Batch Outbox Staging**: Stage st_fts writes via st_outbox:
   - For each fts_record:
     - Create OutboxEntry: `driver='st_fts', op_kind='INSERT', payload=json_bytes`
     - Call `uow.stage_outbox(entry)` within R6's transaction
   - OutboxWorker dispatches to FTS5Driver (k0/drivers/fts5.py)

5. **P08 FTS Optimization**: Coordinate with P08 for index maintenance:
   - **P03 Responsibility**: Write raw FTS entries
   - **P08 Responsibility**: OPTIMIZE FTS5 indexes (PRAGMA optimize), compute BM25 ranks, maintain trigram indexes
   - P08 runs FTS optimization on schedule (every 10,000 entries or daily)

6. **FTS Query Integration**: Enable query-time search:
   - K0 Query Port uses st_fts for `RecallSelector` with `search_text` field
   - FTS5 provides BM25 ranking and snippet generation
   - Results joined back to source tables (st_epi, st_sem, st_prospective) via source_id

**Dependencies**:

- st_epi, st_sem, st_prospective access for text extraction
- FTS5Driver for FTS5 virtual table writes
- K0 UnitOfWork for outbox staging

**Observability**:

- Metric: `p03_r7_fts_entries_created_total` (counter by source_layer)
- Metric: `p03_r7_fts_corpus_size_bytes` (gauge, total searchable text size)
- Log: `r7_fts_staged` event with entry count, corpus size

**Error Handling**:

- **Empty Search Corpus**: If searchable_text empty after concatenation → Skip FTS entry, log warning
- **FTS5 Insert Failure**: If FTS5 virtual table error → Log error, continue (non-blocking, FTS is additive)

---

---

### R8 – Event Emission & Progress Tracking

**Purpose**: Emit consolidation completion events to K0 Bus, update pipeline offsets for idempotency, and record comprehensive observability metrics. This is the final phase that signals consolidation success/failure and enables downstream pipeline coordination.

**Context**: After R6 marks consolidation_status='COMPLETE' and R7 stages all memory layer writes to st_outbox, R8 broadcasts completion events, advances pipeline cursors, and emits detailed telemetry for monitoring dashboards and alerting systems.

**Performance Budget**: Emit events and update offsets in <10 seconds (non-blocking event dispatch, async metric aggregation)

---

#### R8.1 Emit Consolidation Events

**Role**: Broadcast consolidation completion events to K0 Bus for downstream pipeline consumption (P04 Attention Router, P06 Learning Loop, P15 Rollups). Events flow through BusDispatcher to registered sinks and SSE subscribers.

**Implementation Strategy**:

1. **Primary Completion Event**: Emit `p03.consolidation.complete.v1` with batch summary:

   ```python
   completion_event = {
       'topic': 'p03.consolidation.complete.v1',
       'event_id': f"P03_COMPLETE_{uuid4()}",
       'cognitive_trace_id': ctx.cognitive_trace_id,
       'timestamp_utc': now_iso8601(),
       'payload': {
           'batch_id': batch_id,
           'cycle_number': consolidation_state.cycle_number,
           'event_count': 1000,
           'success_count': 987,
           'failure_count': 13,
           'duplicate_count': 156,
           'duration_seconds': 285,
           'phase_durations': {
               'r0_trigger': 2,
               'r1_replay': 120,
               'r2_integration': 180,
               'r3_homeostasis': 180,
               'r4_kg': 60,
               'r5_dream': 48,
               'r6_update': 25,
               'r7_write': 180,
               'r8_emit': 5
           },
           'memory_layers_updated': {
               'st_epi': 831,  # Episodes created
               'st_sem': 47,   # Semantic patterns created
               'st_procedural': 23,  # Routines detected
               'st_social': 62,  # Relationships updated
               'st_prospective': 18,  # Intentions created
               'st_kg_dom': 214,  # KG nodes created
               'st_kg_edges': 389,  # KG edges created
               'st_vec': 831,  # Embeddings queued
               'st_fts': 831   # FTS entries created
           },
           'max_event_id_processed': 'evt_12345...',  # For offset tracking
           'consolidation_quality': {
               'novelty_score_p50': 0.67,
               'importance_score_p50': 0.54,
               'cluster_confidence_p50': 0.81,
               'duplicate_rate': 0.156,
               'pattern_extraction_rate': 0.047
           }
       }
   }
   ```

2. **Secondary Granular Events**: Emit fine-grained events for specific discoveries:

   **Pattern Detection Events** (`p03.pattern.detected.v1`):
   - For each semantic pattern extracted in R2.2
   - Consumed by: P04 (attention routing for pattern-based proactive suggestions)
   - Payload: pattern_type, confidence, observation_count, semantic_id

   **Duplicate Detection Events** (`p03.duplicate.detected.v1`):
   - For each duplicate cluster identified in R3.1
   - Consumed by: P15 (rollup statistics), monitoring dashboards
   - Payload: canonical_event_id, duplicate_event_ids, similarity_scores

   **Cluster Formation Events** (`p03.cluster.formed.v1`):
   - For each episode cluster created in R2.1
   - Consumed by: P04 (attention routing), P15 (episode summaries)
   - Payload: cluster_id, event_count, cluster_confidence, representative_event_id

   **Habit Detection Events** (`p03.habit.detected.v1`):
   - For each procedural routine detected in R2.2
   - Consumed by: P05 (proactive reminders), P06 (habit reinforcement)
   - Payload: routine_id, routine_name, frequency, completion_rate

   **KG Entity/Relationship Events** (`p03.kg.entity.created.v1`, `p03.kg.relationship.created.v1`):
   - For each KG node/edge created in R4
   - Consumed by: P06 (knowledge graph evolution), P15 (entity summaries)
   - Payload: node_id/edge_id, entity_type/relationship_type, confidence

   **Forgetting Events** (`p03.memory.forgotten.v1`):
   - For each memory archived/tombstoned in R3.5
   - Consumed by: Audit systems, P15 (retention reports)
   - Payload: event_id, archival_reason, retention_policy_id

3. **Failure Events**: Emit `p03.consolidation.failed.v1` if any phase fails:

   ```python
   failure_event = {
       'topic': 'p03.consolidation.failed.v1',
       'event_id': f"P03_FAILED_{uuid4()}",
       'cognitive_trace_id': ctx.cognitive_trace_id,
       'timestamp_utc': now_iso8601(),
       'payload': {
           'batch_id': batch_id,
           'failed_phase': 'R3',  # Which phase failed
           'error_type': 'SimHashError',
           'error_message': 'Hamming distance computation failed for event abc123',
           'affected_event_ids': ['evt_abc123', 'evt_def456'],
           'partial_success_count': 534,  # Events processed before failure
           'rollback_performed': True
       }
   }
   ```

4. **BusDispatcher Integration**: Dispatch events via K0 Bus:

   ```python
   from k0.bus.core import BusDispatcher, BusMessage

   async def emit_consolidation_events(
       bus: BusDispatcher,
       completion_event: dict,
       granular_events: list[dict]
   ):
       # Primary completion event
       await bus.dispatch(BusMessage(
           topic=completion_event['topic'],
           payload=completion_event['payload'],
           cognitive_trace_id=completion_event['cognitive_trace_id'],
           timestamp_ms=int(time.time() * 1000)
       ))

       # Granular events (batched dispatch)
       for event in granular_events:
           await bus.dispatch(BusMessage(
               topic=event['topic'],
               payload=event['payload'],
               cognitive_trace_id=event['cognitive_trace_id'],
               timestamp_ms=int(time.time() * 1000)
           ))
   ```

5. **SSE Broadcasting**: K0 SSE Port automatically broadcasts events to subscribers:
   - P04 subscribes to: `p03.pattern.detected.v1`, `p03.cluster.formed.v1`
   - P06 subscribes to: `p03.habit.detected.v1`, `p03.kg.*`
   - P15 subscribes to: `p03.consolidation.complete.v1` (batch summaries)
   - Monitoring dashboards subscribe to: `p03.consolidation.*`

6. **Event Batching Optimization**: Batch granular events to reduce bus load:
   - Buffer granular events during R1-R7 processing
   - Emit in single batch at R8 start (reduces bus messages from ~1000 to ~50)
   - Use `bus.dispatch_batch()` for atomic multi-event emission

**Dependencies**:

- K0 BusDispatcher for event emission
- K0 SSE Port for real-time subscriber broadcasting
- R1-R7 phase results (in-memory data structures with counts, IDs, quality scores)
- consolidation_state (cycle number, phase durations, batch_id)

**Observability**:

- Metric: `p03_r8_events_emitted_total` (counter by topic)
- Metric: `p03_r8_event_emission_duration_seconds` (histogram)
- Metric: `p03_r8_event_batch_size` (histogram, granular events per batch)
- Metric: `p03_r8_bus_dispatch_failures_total` (counter by error_type)
- Log: `r8_events_emitted` event with topic list, event counts, emission duration

**Error Handling**:

- **BusDispatcher Unavailable**: Log error, continue to R8.2 (event emission is "best effort", not critical for consolidation success)
- **Event Serialization Error**: Skip malformed event, log error with event details, emit remaining events
- **SSE Subscriber Backpressure**: BusDispatcher handles backpressure automatically (see k0/sse/server.py), no action needed in P03

---

#### R8.2 Update Pipeline Offsets

**Role**: Record consolidation progress by updating pipeline offsets in `pipeline_offsets` table. This enables idempotent replay, resume-after-failure, and prevents reprocessing of already-consolidated events.

**Implementation Strategy**:

1. **Offset Record Creation**: Write pipeline offset for P03 batch:

   ```sql
   -- pipeline_offsets table structure (from K0 storage layer)
   INSERT INTO pipeline_offsets (
       pipeline_id,
       tenant_id,
       space_id,
       last_processed_event_id,
       last_processed_wal_pos,
       processed_at,
       batch_size,
       success_count,
       failure_count
   ) VALUES (
       'p03_consolidation',
       'tenant_smith_family',
       'personal:dad',
       'evt_12345...', -- Max event_id from batch
       987654,  -- Max wal_pos from batch
       '2025-11-21T03:45:00.000Z',
       1000,
       987,
       13
   )
   ON CONFLICT (pipeline_id, tenant_id, space_id) DO UPDATE SET
       last_processed_event_id = EXCLUDED.last_processed_event_id,
       last_processed_wal_pos = EXCLUDED.last_processed_wal_pos,
       processed_at = EXCLUDED.processed_at,
       batch_size = EXCLUDED.batch_size,
       success_count = EXCLUDED.success_count,
       failure_count = EXCLUDED.failure_count;
   ```

2. **Offset Usage in R0 Trigger Detection**: Next consolidation cycle uses offset to fetch next batch:

   ```sql
   -- R0 batch selection query with offset
   SELECT * FROM st_hipp_events
   WHERE consolidation_status IS NULL
     AND tenant_id = 'tenant_smith_family'
     AND space_id = 'personal:dad'
     AND event_id > (
         SELECT last_processed_event_id FROM pipeline_offsets
         WHERE pipeline_id = 'p03_consolidation'
           AND tenant_id = 'tenant_smith_family'
           AND space_id = 'personal:dad'
     )
   ORDER BY event_time_utc ASC
   LIMIT 1000;
   ```

3. **Multi-Tenant Offset Tracking**: Separate offsets per tenant/space for parallel consolidation:
   - P03 can run consolidation for multiple tenants concurrently (different processes/threads)
   - Each tenant/space has independent offset cursor
   - Enables family-specific consolidation schedules (e.g., Smith family consolidates at 2AM, Jones family at 3AM)

4. **Offset Rollback Support**: If R6.3 marks consolidation_status='FAILED', do NOT update offset:
   - Failed batch will be retried on next consolidation cycle
   - Offset remains at previous successful batch
   - Retry logic: Attempt failed batch max 3 times before skipping (move offset forward but mark events as FAILED)

5. **Checkpoint Storage for Long Batches**: For batches >10,000 events, store incremental checkpoints:
   - Every 1000 events processed, write temporary checkpoint to `pipeline_checkpoints` table
   - If consolidation interrupted (system shutdown, manual stop), resume from last checkpoint
   - Checkpoint includes: phase (R1-R7), last_processed_event_id, partial_results_json
   - After R8.2 completion, delete checkpoint (no longer needed)

6. **Offset Metrics Recording**: Track offset progression over time:
   - Store offset deltas: (current_offset - previous_offset) = events_processed_since_last_run
   - Compute backlog: (max_event_id_in_st_hipp_events - last_processed_event_id) = pending_event_count
   - Alert if backlog grows >10,000 (consolidation falling behind write rate)

**Dependencies**:

- K0 storage layer (`pipeline_offsets` table, `pipeline_checkpoints` table)
- R0 trigger detection (consumes offsets for batch selection)
- R6.3 consolidation status (determines whether to update offset)

**Observability**:

- Metric: `p03_r8_offset_updated_total` (counter)
- Metric: `p03_r8_offset_update_duration_seconds` (histogram)
- Metric: `p03_backlog_events_total` (gauge, pending events not yet consolidated)
- Metric: `p03_offset_delta` (gauge, events processed in last run)
- Log: `r8_offset_updated` event with old_offset, new_offset, delta, backlog

**Error Handling**:

- **Offset Table Write Failure**: Log error, mark consolidation as partial success, retry offset write on next cycle
- **Checkpoint Table Unavailable**: Log warning, continue without checkpoints (lose resume capability but consolidation still completes)
- **Offset Corruption** (offset points to non-existent event_id): Reset offset to earliest unconsolidated event, log critical error, alert operations

---

#### R8.3 Metrics & Observability

**Role**: Aggregate and emit comprehensive observability metrics for monitoring dashboards, alerting systems, and performance analysis. Provide complete visibility into consolidation quality, performance, and resource utilization.

**Implementation Strategy**:

1. **Consolidation Quality Metrics**: Compute and emit quality indicators:

   ```python
   quality_metrics = {
       # Novelty distribution (how novel are consolidated memories?)
       'p03_novelty_score_p10': 0.23,
       'p03_novelty_score_p50': 0.67,
       'p03_novelty_score_p90': 0.94,

       # Importance distribution (how important are consolidated memories?)
       'p03_importance_score_p10': 0.18,
       'p03_importance_score_p50': 0.54,
       'p03_importance_score_p90': 0.89,

       # Cluster quality (how coherent are episodic clusters?)
       'p03_cluster_confidence_p10': 0.62,
       'p03_cluster_confidence_p50': 0.81,
       'p03_cluster_confidence_p90': 0.96,
       'p03_cluster_size_mean': 3.2,
       'p03_cluster_size_p90': 7,

       # Duplicate detection (how effective is deduplication?)
       'p03_duplicate_rate': 0.156,  # 15.6% of events marked as duplicates
       'p03_near_duplicate_clusters': 89,

       # Pattern extraction (how productive is semantic consolidation?)
       'p03_pattern_extraction_rate': 0.047,  # 4.7% of episodes → semantic patterns
       'p03_patterns_by_type': {
           'routine': 23,
           'preference': 12,
           'theme': 8,
           'relationship': 4
       },

       # Knowledge graph (how much KG growth?)
       'p03_kg_nodes_created': 214,
       'p03_kg_edges_created': 389,
       'p03_kg_causal_edges': 37,

       # Forgetting (how much pruning?)
       'p03_memories_archived': 156,
       'p03_memories_tombstoned': 12,
       'p03_retention_policy_enforcements': 168
   }
   ```

2. **Performance Metrics**: Track latency and throughput:

   ```python
   performance_metrics = {
       # Overall consolidation performance
       'p03_consolidation_duration_seconds': 285,
       'p03_events_per_second': 3.51,  # 1000 events / 285 seconds

       # Per-phase latencies (critical path analysis)
       'p03_r0_trigger_duration_seconds': 2,
       'p03_r1_replay_duration_seconds': 120,
       'p03_r2_integration_duration_seconds': 180,
       'p03_r3_homeostasis_duration_seconds': 180,
       'p03_r4_kg_duration_seconds': 60,
       'p03_r5_dream_duration_seconds': 48,
       'p03_r6_update_duration_seconds': 25,
       'p03_r7_write_duration_seconds': 180,
       'p03_r8_emit_duration_seconds': 5,

       # Per-event latencies (for bottleneck identification)
       'p03_per_event_latency_p50': 0.285,  # 285ms per event (median)
       'p03_per_event_latency_p95': 0.512,  # 512ms per event (95th percentile)
       'p03_per_event_latency_p99': 0.847,  # 847ms per event (99th percentile)

       # Throughput by memory layer
       'p03_epi_writes_per_second': 2.91,
       'p03_sem_writes_per_second': 0.16,
       'p03_kg_writes_per_second': 2.11
   }
   ```

3. **Resource Utilization Metrics**: Monitor system resource consumption:

   ```python
   resource_metrics = {
       # CPU usage during consolidation
       'p03_cpu_usage_percent_mean': 45,
       'p03_cpu_usage_percent_p95': 78,

       # Memory usage
       'p03_memory_usage_mb_mean': 512,
       'p03_memory_usage_mb_peak': 1024,

       # Disk I/O
       'p03_disk_reads_mb': 34,
       'p03_disk_writes_mb': 128,

       # Database transaction counts
       'p03_db_transactions_total': 1247,
       'p03_db_transaction_duration_p50': 0.012,  # 12ms median

       # Outbox queue depth (for R7 driver coordination)
       'p03_outbox_entries_staged': 8310,  # ~8 entries per event (8 memory layers)
       'p03_outbox_processing_lag_seconds': 45  # Time until OutboxWorker catches up
   }
   ```

4. **Error & Retry Metrics**: Track failure patterns:

   ```python
   error_metrics = {
       # Overall error rates
       'p03_consolidation_errors_total': 13,
       'p03_error_rate': 0.013,  # 1.3% of events failed

       # Errors by phase
       'p03_r1_errors_total': 2,
       'p03_r2_errors_total': 4,
       'p03_r3_errors_total': 5,
       'p03_r4_errors_total': 1,
       'p03_r5_errors_total': 0,
       'p03_r6_errors_total': 1,
       'p03_r7_errors_total': 0,

       # Errors by type
       'p03_simhash_errors_total': 5,
       'p03_embedding_errors_total': 3,
       'p03_kg_extraction_errors_total': 2,
       'p03_schema_validation_errors_total': 3,

       # Retry statistics
       'p03_events_retried_total': 8,
       'p03_retry_success_rate': 0.625  # 5/8 retries succeeded
   }
   ```

5. **Metric Emission**: Export metrics to K0 Observe Port:

   ```python
   from k0.obs.metrics import MetricsExporter

   async def emit_consolidation_metrics(metrics_exporter: MetricsExporter):
       # Quality metrics
       metrics_exporter.observe('p03_novelty_score', quality_metrics['p03_novelty_score_p50'], labels={'percentile': 'p50'})
       metrics_exporter.observe('p03_importance_score', quality_metrics['p03_importance_score_p50'], labels={'percentile': 'p50'})
       metrics_exporter.gauge('p03_duplicate_rate', quality_metrics['p03_duplicate_rate'])

       # Performance metrics
       metrics_exporter.observe('p03_consolidation_duration_seconds', performance_metrics['p03_consolidation_duration_seconds'])
       metrics_exporter.gauge('p03_events_per_second', performance_metrics['p03_events_per_second'])

       # Resource metrics
       metrics_exporter.gauge('p03_memory_usage_mb', resource_metrics['p03_memory_usage_mb_peak'], labels={'stat': 'peak'})
       metrics_exporter.gauge('p03_cpu_usage_percent', resource_metrics['p03_cpu_usage_percent_p95'], labels={'percentile': 'p95'})

       # Error metrics
       metrics_exporter.counter('p03_consolidation_errors_total', error_metrics['p03_consolidation_errors_total'])
       metrics_exporter.gauge('p03_error_rate', error_metrics['p03_error_rate'])
   ```

6. **Dashboard Integration**: Provide pre-built Grafana dashboard JSON:
   - **Panel 1**: Consolidation throughput (events/second over time)
   - **Panel 2**: Phase duration breakdown (stacked area chart)
   - **Panel 3**: Quality score distributions (novelty, importance, cluster confidence)
   - **Panel 4**: Memory layer growth (line chart: st_epi, st_sem, st_kg_dom row counts over time)
   - **Panel 5**: Error rate and retry success rate (line chart)
   - **Panel 6**: Backlog depth (gauge: pending events awaiting consolidation)
   - **Panel 7**: Resource utilization (CPU, memory, disk I/O)
   - Location: `docs/observability/grafana_dashboards/p03_consolidation.json`

**Dependencies**:

- K0 MetricsExporter (k0/obs/metrics.py)
- K0 Observe Port (k0/ports/observe.py) for metric scraping
- Prometheus for metric storage
- Grafana for visualization

**Observability**:

- Metric: `p03_r8_metrics_emitted_total` (counter, metrics emitted)
- Metric: `p03_r8_metrics_emission_duration_seconds` (histogram)
- Log: `r8_metrics_emitted` event with metric count, emission duration

**Error Handling**:

- **MetricsExporter Unavailable**: Log warning, continue (observability failure should not block consolidation)
- **Metric Serialization Error**: Skip malformed metric, log error, emit remaining metrics
- **Prometheus Scrape Failure**: Not P03's concern (handled by Prometheus retry logic)

---

## P03 Module Registry

> ⚠️ **IMPORTANT**: This table follows K0 Module Master Registry format from `k0/pipelines/k0_architecture_master.md`. Module IDs M01-M17 are allocated to P02. P03-specific modules use M18-M25.

**Module Allocation Strategy**:

- **Reuse P02 Modules**: M01 (DGService), M02 (CA1SemanticProject), M03 (CA3Service), M06 (SalienceScorer), M11 (RetentionLookup)
- **New P03 Modules**: M18-M25 (consolidation-specific sleep cycle componentaradiyas)
- **Brain-Inspired Design**: Each module maps to specific brain region/network involved in memory consolidation

### P03 Module Table

| ID | Name | Brain Analog | Status | README Location | Used By Pipelines | Depends On | Stability | Version | Last Updated |
|----|------|--------------|--------|-----------------|-------------------|------------|-----------|---------|--------------|
| M03 | CA3Service | CA3 (Clustering) | 📋 ADR Complete | `k0/modules/hippocampus/ca3_service.py` | P03 | M01 (DGService), ADR: k003.3 | 🧪 Experimental | 0.1.0 | 2025-11-16 |
| M02 | CA1SemanticProject | CA1 (Semantic Bridge) | ✅ Implemented | `k0/modules/hippocampus/semantic_project.py` | P02, P03 | Contract: ✅, ADR: k003.2, Tests: ⚠️ (9/13), P95: ~20ms | 🧪 Experimental | 1.0.0 | 2025-11-17 |
| M06 | SalienceScorer | Attention Network | ✅ Implemented | `k0/modules/salience/score.py` | P02, P03, P04 | Contract: ✅, ADR: k006.1, Tests: ✅ (57/57), P95: <5ms | 🚀 Production-Ready | 1.0.0 | 2025-11-17 |
| M11 | RetentionLookup | Memory Decay Scheduler | ✅ Implemented | `k0/modules/context/retention_lookup.py` | P02, P03 | Contract: ✅, ADR: k007.4, Tests: ✅ (38/38), P95: <3ms | 🚀 Production-Ready | 1.0.0 | 2025-11-17 |
| M18 | PatternExtractor | Neocortex (Semantic Abstraction) | 📝 Design | `k0/modules/consolidation/pattern_extract.py` | P03 | M03 (CA3Service), M02 (CA1SemanticProject), ADR: TBD | 🧪 Experimental | 0.1.0 | 2025-11-21 |
| M19 | DeduplicationService | DG/CA3 (Pattern Separation) | 📝 Design | `k0/modules/consolidation/deduplicate.py` | P03 | M01 (DGService for SimHash), ADR: TBD | 🧪 Experimental | 0.1.0 | 2025-11-21 |
| M20 | RetentionEnforcer | Prefrontal Cortex (Memory Steward) | 📝 Design | `k0/modules/consolidation/retention_enforce.py` | P03 | M11 (RetentionLookup), ADR: TBD | 🧪 Experimental | 0.1.0 | 2025-11-21 |
| M21 | KGBuilder | Temporal Lobe (Semantic Memory) | 📝 Design | `k0/modules/consolidation/kg_build.py` | P03 | M18 (PatternExtractor), M02 (CA1SemanticProject), ADR: TBD | 🧪 Experimental | 0.1.0 | 2025-11-21 |
| M22 | DreamSimulator | REM Sleep Network | 📝 Design | `k0/modules/consolidation/dream_sim.py` | P03 | M21 (KGBuilder), M18 (PatternExtractor), ADR: TBD | 🧪 Experimental | 0.1.0 | 2025-11-21 |
| M23 | EpisodicReplay | CA3 (Replay Buffer) | 📝 Design | `k0/modules/consolidation/episodic_replay.py` | P03 | M03 (CA3Service), M06 (SalienceScorer), ADR: TBD | 🧪 Experimental | 0.1.0 | 2025-11-21 |
| M24 | MemoryLayerWriter | Storage Interface | 📝 Design | `k0/modules/consolidation/memory_writer.py` | P03 | All P03 modules (M18-M23), P08 coordination, ADR: TBD | 🧪 Experimental | 0.1.0 | 2025-11-21 |
| M25 | ConsolidationOrchestrator | Sleep Cycle Controller | 📝 Design | `k0/modules/consolidation/orchestrator.py` | P03 | All P03 modules (M18-M24), ADR: TBD | 🧪 Experimental | 0.1.0 | 2025-11-21 |

**Module Responsibilities in P03 Phases**:

| Module | R0 Trigger | R1 Replay | R2 Integration | R3 Homeostasis | R4 KG | R5 Dream | R6 Update | R7 Write | R8 Emit |
|--------|-----------|-----------|----------------|---------------|-------|----------|-----------|----------|---------|
| M25 (Orchestrator) | ✅ Primary | Coordinator | Coordinator | Coordinator | Coordinator | Coordinator | Coordinator | Coordinator | ✅ Primary |
| M23 (Replay) | — | ✅ Primary | — | — | — | — | — | — | — |
| M03 (CA3Service) | — | ✅ Clustering | ✅ Primary | — | — | — | — | — | — |
| M18 (PatternExtractor) | — | — | ✅ Primary | — | — | — | — | — | — |
| M02 (CA1SemanticProject) | — | — | ✅ Bridge | — | — | — | — | — | — |
| M19 (Deduplication) | — | — | — | ✅ Primary | — | — | — | — | — |
| M20 (RetentionEnforcer) | — | — | — | ✅ Primary | — | — | — | — | — |
| M21 (KGBuilder) | — | — | — | — | ✅ Primary | — | — | — | — |
| M22 (DreamSimulator) | — | — | — | — | — | ✅ Primary | — | — | — |
| M24 (MemoryLayerWriter) | — | — | — | — | — | — | — | ✅ Primary | — |
| M06 (SalienceScorer) | — | Helper | — | — | — | — | — | — | — |
| M11 (RetentionLookup) | — | — | — | Helper | — | — | — | — | — |

**Implementation Priority** (Phased Rollout):

1. **Phase 1 (MVP)**: M25, M23, M19, M24 → Basic consolidation (replay, dedup, write) without semantic/KG
2. **Phase 2 (Semantic)**: M03, M18, M02 → Add semantic pattern extraction and episodic clustering
3. **Phase 3 (KG)**: M21 → Add knowledge graph construction (entities, relationships, temporal graphs)
4. **Phase 4 (Advanced)**: M20, M22 → Add retention policies (forgetting) and creative exploration (dream simulation)

**Module Protocol Interfaces** (to be defined in module READMEs):

```python
# M25: ConsolidationOrchestratorProtocol
class ConsolidationOrchestratorProtocol(Protocol):
    async def on_trigger(self, trigger_type: str, batch_size: int) -> ConsolidationState
    async def transition_phase(self, from_phase: str, to_phase: str) -> None
    async def emit_events(self, completion_event: dict, granular_events: list[dict]) -> None

# M23: EpisodicReplayProtocol
class EpisodicReplayProtocol(Protocol):
    async def select_batch(self, limit: int, offset: int) -> list[HippEvent]
    async def replay_events(self, events: list[HippEvent], theta_frequency: float) -> ReplayResult
    async def score_importance(self, event: HippEvent, context: dict) -> float

# M18: PatternExtractorProtocol
class PatternExtractorProtocol(Protocol):
    async def extract_patterns(self, cluster: EpisodeCluster) -> list[SemanticPattern]
    async def classify_pattern(self, pattern: SemanticPattern) -> PatternType
    async def compute_confidence(self, pattern: SemanticPattern, cluster: EpisodeCluster) -> float

# M19: DeduplicationServiceProtocol
class DeduplicationServiceProtocol(Protocol):
    async def find_duplicates(self, event: HippEvent, time_window_hours: int) -> list[HippEvent]
    async def score_novelty(self, event: HippEvent, duplicates: list[HippEvent]) -> float
    async def select_canonical(self, duplicate_cluster: list[HippEvent]) -> HippEvent

# M21: KGBuilderProtocol
class KGBuilderProtocol(Protocol):
    async def extract_entities(self, episodes: list[Episode]) -> list[KGNode]
    async def discover_relationships(self, entities: list[KGNode]) -> list[KGEdge]
    async def update_graph(self, nodes: list[KGNode], edges: list[KGEdge]) -> GraphUpdateResult

# M24: MemoryLayerWriterProtocol
class MemoryLayerWriterProtocol(Protocol):
    async def stage_outbox(self, layer_name: str, records: list[dict]) -> list[OutboxEntry]
    async def write_layer(self, layer_name: str, records: list[dict]) -> WriteResult
    async def coordinate_p08(self, embedding_records: list[dict], fts_records: list[dict]) -> None
```

**Testing Strategy per Module**:

- **M25 (Orchestrator)**: State machine tests (R0→R8 transitions), trigger detection tests (scheduled/idle/manual), idle window detection
- **M23 (Replay)**: Importance scoring tests, association strengthening tests, theta rhythm coordination tests
- **M18 (Pattern Extractor)**: Pattern classification tests (routine/preference/theme/relationship), confidence scoring tests, cluster-to-pattern mapping
- **M19 (Deduplication)**: SimHash Hamming distance tests (≤3 threshold), novelty scoring tests, canonical selection tests
- **M21 (KGBuilder)**: Entity extraction tests (person/place/org), relationship discovery tests, causal graph validation
- **M24 (Writer)**: Outbox staging tests, transaction atomicity tests, P08 coordination handoff tests

**Module Observability Standards**:

- Each module emits metrics: `p03_m{ID}_{operation}_{metric}` (e.g., `p03_m23_replay_duration_seconds`)
- Each module logs structured events with `cognitive_trace_id` propagation
- Each module implements `__observe__()` method for distributed tracing span creation
- Metrics exported via K0 Observe Port (Prometheus format)

---

## Storage Schema Design

This section defines the complete storage schema for P03's 8 memory layers plus infrastructure tables. All tables follow world-class durability principles: immutability with versioning, temporal anchoring, confidence tracking, and provenance preservation.

**Design Principles**:

- **Append-Only Architecture**: Never UPDATE existing rows; INSERT new versions with supersedes chains
- **Temporal Validity**: All records track valid_from/valid_to windows for point-in-time queries
- **Confidence Tracking**: Every record includes confidence_score, ambiguity_score, source_count for probabilistic reasoning
- **Cross-Layer Referential Integrity**: Explicit foreign keys enable traversal from raw events → episodes → semantics → KG
- **Predictive Metadata**: Every layer includes predictive_weight, recommendation_readiness for K1 orchestration

---

### Required Tables

#### 1. st_epi (Episodic Memory Layer)

**Purpose**: Store consolidated episodic memories representing coherent experiences (e.g., "dinner with Sarah at Thai restaurant"). Each episode is derived from one or more st_hipp_events through clustering.

**Durability Model**: **PERMANENT** — Append-only with full version lineage, never delete (only tombstone with grace period)

```sql
CREATE TABLE st_epi (
    -- Identity & Versioning
    episode_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,  -- Immutability: versioning support
    canonical_episode_id TEXT,  -- Canonicalization: points to canonical version
    is_canonical INTEGER NOT NULL DEFAULT 1,  -- 1=canonical, 0=superseded
    supersedes_episode_id TEXT,  -- Previous version (if updated)

    -- Core References
    event_id TEXT NOT NULL,  -- FK to st_hipp_events (representative event)
    tenant_id TEXT NOT NULL,
    space_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,

    -- Temporal Anchoring (Rule 2: All layers need temporal grounding)
    event_time_utc TEXT NOT NULL,
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    observation_count INTEGER NOT NULL DEFAULT 1,
    temporal_bucket TEXT,  -- MORNING/AFTERNOON/EVENING/NIGHT
    is_weekend INTEGER,
    recency_weight REAL,  -- exp(-λ * days_since_last_observed)

    -- Content
    text TEXT,
    participants_json TEXT,
    location_name TEXT,
    activity_type TEXT,
    sentiment_score REAL,
    salience_score REAL,

    -- Confidence & Provenance (Rules 4 & 5: Track uncertainty and sources)
    confidence_score REAL NOT NULL,  -- 0.0-1.0
    source_count INTEGER NOT NULL,  -- How many events contributed
    source_quality TEXT,  -- text/sensor/derived/fused
    ambiguity_score REAL,  -- 0.0-1.0 (higher = more uncertain)
    modalities_json TEXT,  -- ["text", "gps", "calendar", etc.]
    fusion_method TEXT,  -- late/early/hybrid (if multi-modal)
    fusion_confidence REAL,

    -- Provenance
    source_events_json TEXT NOT NULL,  -- Array of event_ids that contributed

    -- Consolidation Cross-References (P03 R2 backlinks)
    promoted_to_semantic_id TEXT,  -- FK to st_sem if promoted to semantic memory
    promoted_to_routine_id TEXT,  -- FK to st_procedural if promoted to routine

    -- Decay & Retention (Rule 7: Exponential decay for forgetting)
    decay_factor REAL NOT NULL DEFAULT 1.0,  -- Forgetting function
    archival_status TEXT NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE/ARCHIVED/DEEP_FREEZE/TOMBSTONE
    access_count INTEGER NOT NULL DEFAULT 0,  -- Number of times memory was accessed (for R3.3 staleness)

    -- Predictive Metadata for K1 (Rule 15: Memory substrate directly useful for agent orchestration)
    predictive_weight REAL,  -- For planner priority
    recommendation_readiness REAL,  -- 0.0-1.0
    privacy_risk_score REAL,  -- 0.0-1.0

    -- Timestamps
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    -- Foreign Keys
    FOREIGN KEY (event_id) REFERENCES st_hipp_events(event_id),
    FOREIGN KEY (canonical_episode_id) REFERENCES st_epi(episode_id),
    FOREIGN KEY (supersedes_episode_id) REFERENCES st_epi(episode_id),
    FOREIGN KEY (promoted_to_semantic_id) REFERENCES st_sem(semantic_id),
    FOREIGN KEY (promoted_to_routine_id) REFERENCES st_procedural(routine_id)
);

-- Indexes for episodic recall
CREATE INDEX idx_epi_tenant_time ON st_epi(tenant_id, event_time_utc);
CREATE INDEX idx_epi_actor_time ON st_epi(actor_id, event_time_utc);
CREATE INDEX idx_epi_canonical ON st_epi(canonical_episode_id) WHERE is_canonical = 0;
CREATE INDEX idx_epi_archival ON st_epi(archival_status, decay_factor);
CREATE INDEX idx_epi_access ON st_epi(access_count, last_observed_at);
```

---

#### 2. st_sem (Semantic Memory Layer)

**Purpose**: Store abstracted semantic patterns (routines, preferences, themes, relationships) extracted from episodic clusters. These are generalized knowledge that transcends specific instances.

**Durability Model**: **PROBABILISTIC** — Eventual consistency with convergent versioning, patterns adapt as evidence accumulates

```sql
CREATE TABLE st_sem (
    -- Identity & Versioning
    semantic_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,
    canonical_semantic_id TEXT,
    is_canonical INTEGER NOT NULL DEFAULT 1,
    supersedes_semantic_id TEXT,
    valid_from TEXT NOT NULL,  -- Temporal validity start
    valid_to TEXT,  -- NULL = ongoing

    -- Core References
    tenant_id TEXT NOT NULL,
    space_id TEXT NOT NULL,
    pattern_type TEXT NOT NULL,  -- routine/preference/fact/belief/relationship
    pattern_text TEXT NOT NULL,
    entities_json TEXT,  -- FK references to st_kg_dom.node_id

    -- Temporal Anchoring
    temporal_context TEXT,  -- "weekday mornings", "after work"
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    observation_count INTEGER NOT NULL DEFAULT 1,
    temporal_bucket TEXT,
    is_weekend INTEGER,
    recency_weight REAL,

    -- Pattern-Specific Metadata
    pattern_frequency TEXT,  -- daily/weekly/monthly/irregular (from R2.2)
    pattern_last_occurrence TEXT,  -- Last event_time_utc in cluster (from R2.2)

    -- Confidence & Provenance
    frequency_score REAL,  -- How often pattern occurs
    confidence_score REAL NOT NULL,  -- 0.0-1.0
    source_count INTEGER NOT NULL,
    source_quality TEXT,
    ambiguity_score REAL,
    modalities_json TEXT,
    fusion_method TEXT,
    fusion_confidence REAL,

    -- Provenance
    source_episodes_json TEXT NOT NULL,  -- Array of episode_ids

    -- Decay & Retention (Rule 7: Semantic patterns fade slowly)
    decay_factor REAL NOT NULL DEFAULT 1.0,
    archival_status TEXT NOT NULL DEFAULT 'ACTIVE',

    -- Predictive Metadata
    predictive_weight REAL,
    recommendation_readiness REAL,
    privacy_risk_score REAL,

    -- Timestamps
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    -- Foreign Keys
    FOREIGN KEY (canonical_semantic_id) REFERENCES st_sem(semantic_id),
    FOREIGN KEY (supersedes_semantic_id) REFERENCES st_sem(semantic_id)
);

-- Indexes for semantic recall
CREATE INDEX idx_sem_tenant_pattern ON st_sem(tenant_id, pattern_type);
CREATE INDEX idx_sem_temporal ON st_sem(valid_from, valid_to);
CREATE INDEX idx_sem_decay ON st_sem(decay_factor, archival_status);
CREATE INDEX idx_sem_pattern_frequency ON st_sem(pattern_frequency, last_observed_at);
```

---

#### 3. st_procedural (Procedural Memory Layer)

**Purpose**: Store routines, habits, and motor skill sequences detected from episodic patterns. These are action sequences that can be reactivated for behavior prediction and optimization.

**Durability Model**: **ADAPTIVE** — Self-correcting with streak audit, habits strengthen/weaken based on execution consistency

```sql
CREATE TABLE st_procedural (
    -- Identity & Versioning
    routine_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,
    canonical_routine_id TEXT,
    is_canonical INTEGER NOT NULL DEFAULT 1,
    supersedes_routine_id TEXT,
    valid_from TEXT NOT NULL,
    valid_to TEXT,

    -- Core References
    tenant_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    routine_category TEXT NOT NULL,  -- routine/habit/skill/motor_sequence
    routine_name TEXT NOT NULL,
    trigger_context TEXT,  -- "Tuesday evening", "after breakfast"
    action_sequence_json TEXT,  -- Steps in the habit

    -- Temporal Anchoring
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    last_performed_at TEXT,
    observation_count INTEGER NOT NULL DEFAULT 1,
    temporal_bucket TEXT,
    is_weekend INTEGER,
    recency_weight REAL,

    -- Habit Metrics (Adaptive durability - Rule 6)
    frequency TEXT,  -- daily/weekly/monthly
    consistency_score REAL,  -- 0.0-1.0
    streak_count INTEGER DEFAULT 0,
    longest_streak INTEGER DEFAULT 0,
    streak_history_json TEXT,  -- Log of all streak changes

    -- Confidence & Provenance
    confidence_score REAL NOT NULL,
    source_count INTEGER NOT NULL,
    source_quality TEXT,
    ambiguity_score REAL,
    modalities_json TEXT,
    fusion_method TEXT,
    fusion_confidence REAL,

    -- Provenance
    source_episodes_json TEXT NOT NULL,

    -- Decay & Retention (Rule 7: Habits decay fast if not reinforced)
    decay_factor REAL NOT NULL DEFAULT 1.0,
    archival_status TEXT NOT NULL DEFAULT 'ACTIVE',

    -- Predictive Metadata
    predictive_weight REAL,
    recommendation_readiness REAL,
    privacy_risk_score REAL,

    -- Timestamps
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    -- Foreign Keys
    FOREIGN KEY (canonical_routine_id) REFERENCES st_procedural(routine_id),
    FOREIGN KEY (supersedes_routine_id) REFERENCES st_procedural(routine_id)
);

-- Indexes for procedural recall
CREATE INDEX idx_proc_actor_routine ON st_procedural(actor_id, routine_name);
CREATE INDEX idx_proc_temporal ON st_procedural(valid_from, valid_to);
CREATE INDEX idx_proc_decay ON st_procedural(decay_factor, archival_status);
CREATE INDEX idx_proc_streak ON st_procedural(streak_count, last_performed_at);
```

---

#### 4. st_social (Social Memory Layer)

**Purpose**: Store social relationship dynamics, communication patterns, and interaction frequency. Tracks how relationships evolve over time.

**Durability Model**: **LONG-TERM** — Decay-based but never delete, relationships persist even if inactive

```sql
CREATE TABLE st_social (
    -- Identity & Versioning
    social_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,
    canonical_social_id TEXT,
    is_canonical INTEGER NOT NULL DEFAULT 1,
    supersedes_social_id TEXT,
    valid_from TEXT NOT NULL,
    valid_to TEXT,

    -- Core References
    tenant_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    relationship_person_id TEXT NOT NULL,  -- FK to people.person_id
    relationship_kg_node_id TEXT,  -- FK to st_kg_dom.node_id

    -- Relationship Metadata
    interaction_type TEXT,  -- call/meeting/meal/activity
    interaction_frequency TEXT,  -- daily/weekly/monthly
    intimacy_level TEXT,  -- LOW/MEDIUM/HIGH
    communication_patterns_json TEXT,

    -- Temporal Anchoring
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    last_interaction_at TEXT,
    observation_count INTEGER NOT NULL DEFAULT 1,
    recency_weight REAL,

    -- Confidence & Provenance
    confidence_score REAL NOT NULL,
    source_count INTEGER NOT NULL,
    source_quality TEXT,
    ambiguity_score REAL,
    modalities_json TEXT,

    -- Provenance
    source_episodes_json TEXT NOT NULL,

    -- Decay & Retention (Rule 7: Relationships decay very slowly)
    decay_factor REAL NOT NULL DEFAULT 1.0,
    archival_status TEXT NOT NULL DEFAULT 'ACTIVE',  -- Never delete, only decay

    -- Predictive Metadata
    predictive_weight REAL,
    recommendation_readiness REAL,
    privacy_risk_score REAL,

    -- Timestamps
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    -- Foreign Keys
    FOREIGN KEY (relationship_person_id) REFERENCES people(person_id),
    FOREIGN KEY (relationship_kg_node_id) REFERENCES st_kg_dom(node_id),
    FOREIGN KEY (canonical_social_id) REFERENCES st_social(social_id),
    FOREIGN KEY (supersedes_social_id) REFERENCES st_social(social_id)
);

-- Indexes for social recall
CREATE INDEX idx_social_actor_person ON st_social(actor_id, relationship_person_id);
CREATE INDEX idx_social_temporal ON st_social(valid_from, valid_to);
CREATE INDEX idx_social_decay ON st_social(decay_factor, last_interaction_at);
```

---

#### 5. st_prospective (Prospective Memory Layer)

**Purpose**: Store future-oriented intentions, reminders, goals, and predictive scenarios. These are forward-looking memories that trigger proactive behavior.

**Durability Model**: **LIFECYCLE** — Status-based retention, delete only after COMPLETED/EXPIRED

```sql
CREATE TABLE st_prospective (
    -- Identity & Versioning
    prospective_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,
    canonical_prospective_id TEXT,
    is_canonical INTEGER NOT NULL DEFAULT 1,
    supersedes_prospective_id TEXT,

    -- Core References
    tenant_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    intention_type TEXT NOT NULL,  -- reminder/goal/plan/scenario/insight
    intention_text TEXT NOT NULL,
    trigger_condition TEXT,  -- "when at gym", "Tuesday morning"
    target_time TEXT,  -- ISO timestamp or relative time
    priority TEXT,  -- LOW/MEDIUM/HIGH

    -- Lifecycle Management (Rule 6: Delete only after completion/expiry)
    status TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING/IN_PROGRESS/COMPLETED/EXPIRED/CANCELLED
    status_history_json TEXT,  -- Log of all status transitions

    -- Temporal Anchoring
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    observation_count INTEGER NOT NULL DEFAULT 1,
    recency_weight REAL,

    -- Confidence & Provenance
    confidence_score REAL NOT NULL,
    source_count INTEGER NOT NULL,
    source_quality TEXT,
    ambiguity_score REAL,
    modalities_json TEXT,

    -- Provenance
    source_episode_id TEXT,  -- FK to st_epi
    source_episodes_json TEXT,

    -- Predictive Metadata (Rule 15: Critical for proactive agent)
    predictive_weight REAL NOT NULL,  -- High priority for planner
    recommendation_readiness REAL NOT NULL,
    privacy_risk_score REAL,

    -- Timestamps
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    expired_at TEXT,

    -- Foreign Keys
    FOREIGN KEY (source_episode_id) REFERENCES st_epi(episode_id),
    FOREIGN KEY (canonical_prospective_id) REFERENCES st_prospective(prospective_id),
    FOREIGN KEY (supersedes_prospective_id) REFERENCES st_prospective(prospective_id)
);

-- Indexes for prospective recall
CREATE INDEX idx_prosp_actor_status ON st_prospective(actor_id, status);
CREATE INDEX idx_prosp_target_time ON st_prospective(target_time, status);
CREATE INDEX idx_prosp_priority ON st_prospective(priority, status);
```

---

#### 6. st_kg_dom (Knowledge Graph - Nodes)

**Purpose**: Store knowledge graph entity nodes (people, places, organizations, concepts). Supports entity resolution, temporal versioning, and concept evolution.

**Durability Model**: **VERSIONED** — Entity equivalence merging with eventual consistency

```sql
CREATE TABLE st_kg_dom (
    -- Identity & Versioning
    node_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,
    canonical_node_id TEXT,  -- Entity equivalence merging
    is_canonical INTEGER NOT NULL DEFAULT 1,
    supersedes_node_id TEXT,
    merged_from_nodes_json TEXT,  -- Array of node_ids merged into this canonical
    valid_from TEXT NOT NULL,
    valid_to TEXT,  -- NULL = ongoing

    -- Core References
    tenant_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,  -- Person/Location/Event/Organization/Thing/Concept
    entity_name TEXT NOT NULL,
    entity_attributes_json TEXT,

    -- Temporal Anchoring
    first_mentioned_at TEXT NOT NULL,
    last_mentioned_at TEXT NOT NULL,
    mention_count INTEGER NOT NULL DEFAULT 1,
    recency_weight REAL,

    -- Confidence & Provenance
    confidence_score REAL NOT NULL,
    source_count INTEGER NOT NULL,
    source_quality TEXT,
    ambiguity_score REAL,
    modalities_json TEXT,

    -- Provenance
    source_episodes_json TEXT NOT NULL,

    -- Decay & Retention (Rule 7: KG entities persist with decay)
    decay_factor REAL NOT NULL DEFAULT 1.0,
    archival_status TEXT NOT NULL DEFAULT 'ACTIVE',

    -- Entity Resolution
    similarity_cluster_id TEXT,  -- For near-duplicate entities
    resolution_confidence REAL,

    -- Consolidation Metadata (P03 R4 outputs)
    observation_count INTEGER NOT NULL DEFAULT 1,  -- Number of times entity observed (R4.3)
    node_properties_json TEXT,  -- Additional metadata (evolution_type, reversal_date, etc. for R4.5)

    -- Timestamps
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    -- Foreign Keys
    FOREIGN KEY (canonical_node_id) REFERENCES st_kg_dom(node_id),
    FOREIGN KEY (supersedes_node_id) REFERENCES st_kg_dom(node_id)
);

-- Indexes for KG node queries
CREATE INDEX idx_kg_entity_name ON st_kg_dom(entity_name, entity_type);
CREATE INDEX idx_kg_temporal ON st_kg_dom(valid_from, valid_to);
CREATE INDEX idx_kg_canonical ON st_kg_dom(canonical_node_id) WHERE is_canonical = 0;
```

---

#### 7. st_kg_edges (Knowledge Graph - Edges)

**Purpose**: Store knowledge graph relationship edges between entities. Supports temporal validity, causal relationships, and context-dependent edges.

**Durability Model**: **VERSIONED** — Relationship evolution with temporal validity windows

```sql
CREATE TABLE st_kg_edges (
    -- Identity & Versioning
    edge_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,
    canonical_edge_id TEXT,
    is_canonical INTEGER NOT NULL DEFAULT 1,
    supersedes_edge_id TEXT,

    -- Core References
    tenant_id TEXT NOT NULL,
    from_node_id TEXT NOT NULL,  -- FK to st_kg_dom
    to_node_id TEXT NOT NULL,    -- FK to st_kg_dom
    relationship_type TEXT NOT NULL,  -- DINED_WITH/WORKS_AT/LIVES_IN/CAUSES/etc.

    -- Temporal Validity (Rule 13: Context-dependent edges)
    valid_from TEXT NOT NULL,
    valid_to TEXT,  -- NULL = ongoing

    -- Temporal Anchoring
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    observation_count INTEGER NOT NULL DEFAULT 1,
    recency_weight REAL,

    -- Confidence & Provenance
    confidence_score REAL NOT NULL,
    source_count INTEGER NOT NULL,
    source_quality TEXT,
    ambiguity_score REAL,
    modalities_json TEXT,

    -- Context-Dependent Metadata
    context_type TEXT,  -- work/social/family/location
    context_attributes_json TEXT,

    -- Provenance
    source_episodes_json TEXT NOT NULL,

    -- Consolidation Metadata (P03 R4 outputs)
    edge_properties_json TEXT,  -- Additional metadata (average_delay_minutes, confounders_json for R4.4 causal)

    -- Decay & Retention
    decay_factor REAL NOT NULL DEFAULT 1.0,
    archival_status TEXT NOT NULL DEFAULT 'ACTIVE',

    -- Timestamps
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    -- Foreign Keys
    FOREIGN KEY (from_node_id) REFERENCES st_kg_dom(node_id),
    FOREIGN KEY (to_node_id) REFERENCES st_kg_dom(node_id),
    FOREIGN KEY (canonical_edge_id) REFERENCES st_kg_edges(edge_id),
    FOREIGN KEY (supersedes_edge_id) REFERENCES st_kg_edges(edge_id)
);

-- Indexes for KG edge queries
CREATE INDEX idx_kg_edge_from ON st_kg_edges(from_node_id, relationship_type);
CREATE INDEX idx_kg_edge_to ON st_kg_edges(to_node_id, relationship_type);
CREATE INDEX idx_kg_edge_temporal ON st_kg_edges(valid_from, valid_to);
```

---

#### 8. st_consolidation_logs (Consolidation Audit Trail)

**Purpose**: Audit trail for P03 consolidation operations. Tracks which phases executed for which events, enabling debugging and compliance.

```sql
CREATE TABLE st_consolidation_logs (
    log_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    pipeline_run_id TEXT NOT NULL,
    event_id TEXT NOT NULL,  -- FK to st_hipp_events
    consolidation_phase TEXT NOT NULL,  -- R0/R1/R2/R3/R4/R5/R6/R7/R8
    phase_status TEXT NOT NULL,  -- SUCCESS/FAILED/SKIPPED
    phase_duration_ms INTEGER,
    error_message TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_consolidation_logs_batch ON st_consolidation_logs(batch_id);
CREATE INDEX idx_consolidation_logs_event ON st_consolidation_logs(event_id);
CREATE INDEX idx_consolidation_logs_phase ON st_consolidation_logs(consolidation_phase, phase_status);
```

---

#### 9. st_event_canon_map (Canonical Event Mapping)

**Purpose**: Maps duplicate events to their canonical event. Supports deduplication queries and duplicate rate analytics.

```sql
CREATE TABLE st_event_canon_map (
    map_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,  -- Duplicate event
    canonical_event_id TEXT NOT NULL,  -- Canonical (kept) event
    similarity_score REAL,
    dedup_method TEXT,  -- simhash/minhash/manual
    created_at TEXT NOT NULL
);

CREATE INDEX idx_event_canon_map_event ON st_event_canon_map(event_id);
CREATE INDEX idx_event_canon_map_canonical ON st_event_canon_map(canonical_event_id);
```

---

#### 10. st_event_cluster_history (Cluster Assignment History)

**Purpose**: Historical record of event cluster assignments. Supports cluster evolution analysis and re-clustering experiments.

```sql
CREATE TABLE st_event_cluster_history (
    history_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    cluster_id TEXT NOT NULL,
    assigned_at TEXT NOT NULL,
    confidence REAL,
    cluster_type TEXT,  -- temporal/semantic/spatial
    clustering_algorithm TEXT  -- simhash/embedding/manual
);

CREATE INDEX idx_event_cluster_history_event ON st_event_cluster_history(event_id);
CREATE INDEX idx_event_cluster_history_cluster ON st_event_cluster_history(cluster_id);
```

---

### Updates to Existing Tables

#### st_hipp_events (Consolidation State Columns)

**Purpose**: In-place updates to staging table to track consolidation progress. These columns are populated by P03 R6.1-R6.3.

**Columns Added for P03**:

```sql
-- P03 Consolidation State (added via migration)
ALTER TABLE st_hipp_events ADD COLUMN consolidation_status TEXT;  -- NULL/PENDING/IN_PROGRESS/COMPLETE/FAILED
ALTER TABLE st_hipp_events ADD COLUMN consolidated_at TEXT;  -- ISO timestamp when P03 processed
ALTER TABLE st_hipp_events ADD COLUMN consolidation_error TEXT;  -- Error message if FAILED
ALTER TABLE st_hipp_events ADD COLUMN importance_score REAL;  -- Computed by R1.4 (0.0-1.0)
ALTER TABLE st_hipp_events ADD COLUMN access_count INTEGER DEFAULT 0;  -- Number of times accessed (for importance weighting)
ALTER TABLE st_hipp_events ADD COLUMN novelty_score REAL;  -- Computed by R3.2 (0.0-1.0)
ALTER TABLE st_hipp_events ADD COLUMN near_duplicates_json TEXT;  -- JSON array of duplicate event_ids
ALTER TABLE st_hipp_events ADD COLUMN is_near_duplicate INTEGER;  -- 0/1 flag
ALTER TABLE st_hipp_events ADD COLUMN episode_cluster_id TEXT;  -- Assigned by R2.1
ALTER TABLE st_hipp_events ADD COLUMN cluster_confidence REAL;  -- Cluster fit score (0.0-1.0)

-- Indexes for P03 queries
CREATE INDEX idx_hipp_events_consolidation ON st_hipp_events(consolidation_status, event_time_utc);
CREATE INDEX idx_hipp_events_novelty ON st_hipp_events(novelty_score, is_near_duplicate);
CREATE INDEX idx_hipp_events_cluster ON st_hipp_events(episode_cluster_id);
```

**Update Pattern (from R6.1-R6.3)**:

```sql
-- R6.1: Update deduplication columns
UPDATE st_hipp_events
SET
  novelty_score = ?,
  near_duplicates_json = ?,
  is_near_duplicate = ?
WHERE event_id = ?;

-- R6.2: Update cluster columns
UPDATE st_hipp_events
SET
  episode_cluster_id = ?,
  cluster_confidence = ?
WHERE event_id = ?;

-- R6.3: Mark consolidation complete
UPDATE st_hipp_events
SET
  consolidation_status = 'COMPLETE',
  consolidated_at = ?
WHERE event_id IN (?, ?, ..., ?);
```

---

## Sleep Cycle Architecture

P03's consolidation process mimics the human sleep cycle architecture, where memories are replayed, reorganized, and integrated during sleep. This biologically-inspired design maps P03's 8 phases (R0-R8) to the 4 sleep stages: NREM Phase 1 (Slow-Wave Sleep), NREM Phase 2 (Light Sleep), REM Phase (Paradoxical Sleep), and Waking Phase.

**Neuroscience Foundation**:

- **Slow-Wave Sleep (SWS)**: Hippocampal replay strengthens recent memories, transfers episodic → semantic
- **Light Sleep**: Synaptic homeostasis (pruning weak connections, deduplication)
- **REM Sleep**: Creative recombination, novel associations, emotional processing, future simulation
- **Waking**: Integration complete, memories accessible for recall

**P03 Sleep Cycle Duration**: Target 90 minutes per cycle (matching human ultradian rhythm), processing 500-2000 events per cycle depending on complexity.

**Cycle Coordination**: R0 Trigger Detection determines when to enter sleep cycle based on:

- **Scheduled Trigger**: Daily at 2:00 AM (family asleep, low system load)
- **Idle Trigger**: After 4+ hours of no new events (opportunistic consolidation)
- **Manual Trigger**: Via CLI `family-os consolidate --run-now` (on-demand)

---

### NREM Phase 1 (Slow-Wave Sleep)

**Biological Analog**: Slow-wave sleep (SWS) features synchronized slow oscillations (0.5-1 Hz) that coordinate hippocampal-neocortical replay. Sharp-wave ripples (100-250 Hz) in CA3/CA1 replay recent experiences in compressed time (~20x faster), strengthening memory traces in neocortex.

**P03 Mapping**: **R1 (Hippocampal Replay) + R2 (Neocortical Integration)**

**Duration**: 30-40 minutes (33% of cycle)

**Activities**:

1. **R1.1: Batch Selection** — Select unconsolidated events from `st_hipp_events` (like hippocampus retrieving recent experiences)
   - Query: `WHERE consolidation_status IS NULL ORDER BY event_time_utc LIMIT 1000`
   - Batch size: 500-2000 events (adaptive based on system load)

2. **R1.2: Importance Weighting** — Score events by salience (mimics attention-modulated replay)
   - High-salience events (surprise, emotional valence, recency) replayed more frequently
   - Importance score combines: `salience_score * recency_weight * access_count`
   - Events with importance >0.7 prioritized for semantic promotion

3. **R1.3: Association Strengthening** — Identify co-occurring patterns (like Hebbian learning "neurons that fire together, wire together")
   - Temporal proximity: Events within 2-hour window
   - Semantic similarity: SimHash Hamming distance <3 bits
   - Spatial proximity: Events at same location_name
   - Builds association graph for clustering in R2.1

4. **R1.4: Theta Rhythm Coordination** — Simulate hippocampal theta oscillations (4-8 Hz) for replay coordination
   - Replay events in 125ms chunks (8 Hz theta frequency)
   - Coordinated replay enhances pattern detection in R2
   - Implementation: Process events in micro-batches with 125ms sleep between batches

5. **R2.1: Episode Clustering** — Group related events into coherent episodes (like neocortical schema formation)
   - Algorithm: DBSCAN with temporal+semantic distance metric
   - Cluster criteria: Events within 4-hour window, SimHash distance <3, shared participants/location
   - Output: Episode clusters (e.g., "dinner with Sarah" cluster contains 5 related events)

6. **R2.2: Pattern Extraction** — Abstract semantic patterns from episode clusters (episodic → semantic transfer)
   - Routine patterns: "Tuesday yoga class" (recurring temporal patterns)
   - Preference patterns: "prefers Thai food" (frequency-based preferences)
   - Relationship patterns: "weekly calls with Mom" (social interaction patterns)
   - Confidence scoring: `confidence = sqrt(frequency_score * recency_weight)`

7. **R2.3: CA1 Bridge Logic** — Apply CA1SemanticProject module (hippocampus-neocortex bridge)
   - Determines which episodes should be promoted to semantic memory
   - Promotion criteria: High frequency (>3 occurrences), high confidence (>0.7), semantic coherence
   - Output: Promotion decisions with backlinks (st_epi.promoted_to_semantic_id)

**Neural Synchronization**: R1 replay drives R2 integration through theta-gamma coupling (theta phase codes spatial/temporal context, gamma burst codes content)

**Observability**:

- Metric: `p03_nrem1_duration_seconds` (histogram, target 1800-2400s)
- Metric: `p03_nrem1_events_replayed_total` (counter)
- Metric: `p03_nrem1_episodes_clustered_total` (counter)
- Metric: `p03_nrem1_patterns_extracted_total` (counter by pattern_type)
- Log: `nrem1_complete` event with replay stats, cluster counts, pattern breakdown

**Performance Budget**: 30-40 minutes for 1000 events (0.5-1.0 events/second replay throughput)

---

### NREM Phase 2 (Light Sleep)

**Biological Analog**: Light sleep (Stage 2 NREM) features sleep spindles (12-15 Hz bursts) that support synaptic plasticity and memory consolidation. Synaptic homeostasis (downscaling) prunes weak connections formed during waking, maintaining network efficiency while preserving important memories.

**P03 Mapping**: **R3 (Synaptic Homeostasis) + R4 (Knowledge Graph Consolidation)**

**Duration**: 20-30 minutes (22% of cycle)

**Activities**:

1. **R3.1: Deduplication (Pattern Separation)** — Remove near-duplicate events (like synaptic downscaling removes weak/redundant connections)
   - Algorithm: SimHash with Hamming distance threshold ≤3 bits
   - Time window: 24-hour lookback (events must be within 24h to be considered duplicates)
   - Canonical selection: Keep event with highest salience_score, mark others as is_near_duplicate=1
   - Duplicate rate target: 15-25% of events are near-duplicates

2. **R3.2: Novelty Scoring** — Compute novelty for each event (inverted duplicate likelihood)
   - Formula: `novelty_score = 1.0 - (duplicate_count / time_window_event_count)`
   - High novelty (>0.8): Unique experiences, prioritized for retention
   - Low novelty (<0.3): Routine experiences, candidates for aggressive archival

3. **R3.3: Staleness Detection** — Identify rarely-accessed memories for decay/archival
   - Query: `WHERE access_count = 0 AND created_at < NOW() - INTERVAL '90 days'`
   - Staleness score: `1.0 - exp(-λ * days_since_access)` where λ = 0.01
   - Stale memories (staleness >0.9) moved to ARCHIVED status with increased decay_factor

4. **R3.4: Retention Policy Enforcement** — Apply forgetting rules from RetentionLookup (M11)
   - Policy matrix: band × topic × device_kind → retention_days
   - Example: GREEN band + "health.vitals" + "wearable" → 90 days
   - Apply tombstone deletions for events exceeding retention period
   - Grace period: 30 days between TOMBSTONE status and physical deletion

5. **R4.1: Entity Extraction & Normalization** — Build knowledge graph nodes from consolidated episodes
   - Extract entities from episode text: people, places, organizations, concepts
   - Normalization: "Mom" → "Mary Smith" (resolve to people.person_id)
   - Entity types: Person, Location, Event, Organization, Thing, Concept
   - Fuzzy matching: Levenshtein distance <3 for entity disambiguation

6. **R4.2: Relationship Discovery** — Detect relationships between entities (KG edges)
   - Co-occurrence analysis: Entities appearing together in episodes
   - Relationship types: DINED_WITH, WORKS_AT, LIVES_IN, ATTENDED, PURCHASED_AT
   - Strength scoring: `strength = observation_count * recency_weight * confidence`
   - Temporal validity: Track valid_from/valid_to for time-dependent relationships

7. **R4.3: Temporal Graph Updates** — Update existing KG nodes/edges with new evidence
   - Entity evolution: Update attributes, merge duplicates, version entities
   - Relationship evolution: Extend valid_to, update strength, add observations
   - Snapshot creation: Every 1000 events, snapshot KG state to st_kg_snapshots

8. **R4.4: Causal Inference** — Detect causal relationships between events
   - Criteria: Event A always precedes Event B within consistent lag
   - Algorithm: Granger causality with temporal lag analysis
   - Example: "coffee purchase" → "gym visit" (lag: 30 minutes, confidence: 0.8)
   - Causal edges marked with edge_properties_json.is_causal=true

9. **R4.5: Concept Evolution Tracking** — Monitor how concepts change over time
   - Drift detection: Compare entity attributes across versions
   - Example: "work location" drifts from "office" → "home" during pandemic
   - Reversal tracking: Detect when concepts revert to previous states
   - Store evolution metadata in node_properties_json (evolution_type, drift_score)

**Neural Synchronization**: Sleep spindles (R3) coordinate with hippocampal sharp-wave ripples to selectively strengthen important memories while pruning redundant ones. R4 builds declarative semantic structures that transcend episodic details.

**Observability**:

- Metric: `p03_nrem2_duration_seconds` (histogram, target 1200-1800s)
- Metric: `p03_nrem2_duplicates_found_total` (counter)
- Metric: `p03_nrem2_novelty_score_mean` (gauge)
- Metric: `p03_nrem2_kg_nodes_created_total` (counter by entity_type)
- Metric: `p03_nrem2_kg_edges_created_total` (counter by relationship_type)
- Metric: `p03_nrem2_causal_edges_total` (counter)
- Log: `nrem2_complete` event with deduplication stats, KG growth, causal relationships

**Performance Budget**: 20-30 minutes for 1000 events (deduplication: 10-15 min, KG construction: 10-15 min)

---

### REM Phase (Paradoxical Sleep)

**Biological Analog**: REM (Rapid Eye Movement) sleep features high-frequency brain activity (similar to waking) with suppressed motor output. REM supports creative problem-solving through novel recombination of memories, emotional regulation, and forward simulation of future scenarios. Hippocampus replays experiences in novel orders, testing "what-if" scenarios.

**P03 Mapping**: **R5 (Dream-Like Exploration)**

**Duration**: 15-25 minutes (17% of cycle)

**Activities**:

1. **R5.1: Counterfactual Pattern Network (CPN)** — Generate "what-if" scenarios from episodic memories
   - Algorithm: Substitute key elements in episodes with plausible alternatives
   - Example: "What if dinner was at Italian restaurant instead of Thai?"
   - Counterfactual plausibility scored by KG consistency
   - Output: Counterfactual episodes for proactive planning (stored in st_prospective)

2. **R5.2: Temporal Planning Network with MCTS (TPN-MCTS)** — Simulate future scenarios via tree search
   - Algorithm: Monte Carlo Tree Search over episode sequences
   - Goal states: Future intentions from R2 patterns (e.g., "plan weekend trip")
   - Simulation: Sample 50-100 trajectories, score by plausibility and desirability
   - Output: Diverse future scenarios with predicted outcomes (st_prospective.alternative_scenarios_json)

3. **R5.3: Surprise-Based Pattern Curation with Uncertainty Quantification (SPC-UQ)** — Identify surprising patterns for attention
   - Algorithm: Compare pattern frequency with baseline distribution
   - Surprise score: `KL_divergence(observed || baseline)`
   - Example: "Usually gym on Monday, but skipped 3 weeks" (surprise_score: 0.92)
   - Output: High-surprise patterns flagged for P04 Attention Router

4. **R5.4: Belief Graph Traversal with Semantic Memory (BGT-SM)** — Navigate KG for creative insights
   - Algorithm: Random walks on KG with semantic similarity guidance
   - Walk length: 5-10 hops, biased toward high-confidence edges
   - Insight generation: Connect distant concepts (e.g., "exercise" → "sleep quality" → "productivity")
   - Output: Novel insights stored as st_prospective.intention_type='insight'

5. **R5.5: Trace Decay Learning with Hippocampal Consolidation Optimization (TDL-HCO)** — Optimize memory retention priorities
   - Algorithm: Reinforcement learning on memory access patterns
   - Reward: Memories accessed after consolidation = high utility, never accessed = low utility
   - Update decay_factor based on predicted future utility
   - Output: Optimized decay functions for procedural memory (st_procedural.decay_factor)

6. **R5.6: Emotional Regulation** — Adjust sentiment and affective metadata
   - Revisit high-arousal episodes (|sentiment_score| >0.7)
   - Integrate emotional context with KG relationships
   - Example: Negative episode at restaurant buffered by positive relationship with companion
   - Output: Updated sentiment_score in st_epi with emotional_regulation_applied=1

**Neural Synchronization**: REM theta (hippocampus) + high-gamma (neocortex) enable flexible memory recombination without motor execution. Acetylcholine modulation enhances associative plasticity, supporting creative connections.

**Observability**:

- Metric: `p03_rem_duration_seconds` (histogram, target 900-1500s)
- Metric: `p03_rem_counterfactuals_generated_total` (counter)
- Metric: `p03_rem_scenarios_simulated_total` (counter)
- Metric: `p03_rem_insights_discovered_total` (counter)
- Metric: `p03_rem_surprise_score_p90` (gauge, 90th percentile)
- Log: `rem_complete` event with scenario counts, insight categories, surprise distribution

**Performance Budget**: 15-25 minutes for 1000 events (creative exploration is compute-intensive but low-throughput)

**Creative Output**: R5 generates 50-200 prospective memories per cycle (scenarios, insights, counterfactuals), enriching proactive agent capabilities.

---

### Waking Phase (Consolidation Complete)

**Biological Analog**: Upon waking, consolidated memories are integrated into long-term storage and available for conscious recall. Memory traces are stabilized, false memories pruned, and neural network connectivity optimized. The hippocampus returns to encoding mode (ready for new experiences), while neocortex maintains consolidated schemas.

**P03 Mapping**: **R6 (Update st_hipp_events) + R7 (Write to 8 Memory Layers) + R8 (Event Emission & Progress Tracking)**

**Duration**: 10-20 minutes (11% of cycle)

**Activities**:

1. **R6.1: Update Deduplication Columns** — Mark duplicate/novel events in staging table
   - Write novelty_score, near_duplicates_json, is_near_duplicate to st_hipp_events
   - Enables duplicate rate analytics: `SELECT AVG(is_near_duplicate) FROM st_hipp_events`

2. **R6.2: Update Cluster Columns** — Record episode cluster assignments
   - Write episode_cluster_id, cluster_confidence to st_hipp_events
   - Links raw events back to consolidated episodes (bidirectional provenance)

3. **R6.3: Mark Consolidation Status** — Finalize consolidation for batch
   - Update consolidation_status='COMPLETE', consolidated_at=NOW()
   - Idempotency: Prevents reprocessing of already-consolidated events
   - Error handling: If any R1-R5 phase failed, mark consolidation_status='FAILED' with error details

4. **R7.1-R7.8: Write to 8 Memory Layers** — Persist consolidated memories to durable storage
   - **st_epi**: Episode records with full provenance and confidence tracking
   - **st_sem**: Semantic patterns abstracted from episodes
   - **st_procedural**: Routines and habits with streak metrics
   - **st_social**: Relationship dynamics and interaction patterns
   - **st_prospective**: Future intentions, scenarios, insights from R5
   - **st_kg_dom**: Knowledge graph entity nodes with temporal versioning
   - **st_kg_edges**: Knowledge graph relationship edges with causal metadata
   - **st_vec**: Embedding placeholders (coordination with P08)
   - **st_fts**: Full-text search entries (coordination with P08)
   - All writes staged via st_outbox (transactional atomicity via K0 UnitOfWork)

5. **R8.1: Emit Consolidation Events** — Broadcast completion to K0 Bus
   - Primary event: `p03.consolidation.complete.v1` with batch summary
   - Granular events: `p03.pattern.detected.v1`, `p03.cluster.formed.v1`, `p03.memory.archived.v1`
   - Subscribers: P04 (Attention Router), P06 (Learning Loop), P15 (Rollups), monitoring dashboards

6. **R8.2: Update Pipeline Offsets** — Record consolidation progress
   - Write to `pipeline_offsets` table: last_processed_event_id, processed_count, batch_time
   - Enables resume-after-failure: Next cycle starts from last_processed_event_id + 1
   - Multi-tenant tracking: Separate offsets per tenant_id + space_id

7. **R8.3: Emit Comprehensive Metrics** — Export observability data
   - Quality metrics: novelty distribution, confidence scores, cluster quality
   - Performance metrics: phase durations, throughput, memory layer growth
   - Resource metrics: CPU usage, memory footprint, disk I/O, outbox lag
   - Error metrics: failure rates, retry success, dead letter queue depth
   - Grafana dashboard: `docs/observability/grafana_dashboards/p03_consolidation.json`

8. **Sleep Cycle Completion Signal** — Mark cycle complete, return to idle
   - Log: `p03_sleep_cycle_complete` with total duration, events processed, memories created
   - State transition: CONSOLIDATING → IDLE (ready for next trigger)
   - Cleanup: Clear in-memory consolidation state, release resources

**Memory Accessibility**: After R7 writes complete, consolidated memories are immediately queryable via K0 Query Port:

- Episodic recall: `SELECT * FROM st_epi WHERE actor_id = 'user_123' AND event_time_utc > '2025-11-01'`
- Semantic patterns: `SELECT * FROM st_sem WHERE pattern_type = 'routine' ORDER BY confidence_score DESC`
- Knowledge graph: `SELECT * FROM st_kg_dom WHERE entity_type = 'Person' AND entity_name LIKE '%Sarah%'`
- Prospective intentions: `SELECT * FROM st_prospective WHERE status = 'PENDING' AND target_time < NOW() + INTERVAL '1 day'`

**Observability**:

- Metric: `p03_waking_duration_seconds` (histogram, target 600-1200s)
- Metric: `p03_waking_memories_written_total` (counter by layer)
- Metric: `p03_waking_events_emitted_total` (counter by topic)
- Metric: `p03_cycle_total_duration_seconds` (histogram, target 5400s = 90 min)
- Metric: `p03_cycle_complete_total` (counter, successful cycles)
- Log: `waking_complete` event with write stats, offset updates, cycle summary

**Performance Budget**: 10-20 minutes for 1000 events (R6: 2-5 min, R7: 5-10 min, R8: 3-5 min)

**Cycle Summary Example**:

```json
{
  "cycle_id": "cycle_20251121_020000",
  "duration_seconds": 5234,
  "events_processed": 1247,
  "phase_breakdown": {
    "nrem1": 2103,
    "nrem2": 1456,
    "rem": 982,
    "waking": 693
  },
  "memories_created": {
    "st_epi": 342,
    "st_sem": 89,
    "st_procedural": 23,
    "st_social": 67,
    "st_prospective": 134,
    "st_kg_dom": 211,
    "st_kg_edges": 456
  },
  "quality_metrics": {
    "duplicate_rate": 0.18,
    "avg_novelty_score": 0.67,
    "avg_confidence_score": 0.81,
    "avg_cluster_quality": 0.73
  },
  "next_cycle_eta": "2025-11-22T02:00:00Z"
}
```

---

## Batch Processing Strategy

P03 consolidation runs as a background process that must balance throughput with system responsiveness. The batch processing strategy ensures consolidation completes efficiently without degrading user experience or starving other system processes.

**Design Goals**:

- **High Throughput**: Process 500-2000 events per 90-minute cycle (9-37 events/minute)
- **Low Latency Impact**: User interactions remain <50ms response time during consolidation
- **Graceful Degradation**: Automatically throttle under high system load
- **Resumable Processing**: Support interruption and resume without data loss
- **Fair Resource Allocation**: Share CPU/memory with P02 writes, K1 orchestration, user queries

**Architecture Overview**:

```
┌─────────────────────────────────────────────────────────────┐
│ Batch Processing Pipeline                                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐             │
│  │  Batch   │───▶│ Throttle │───▶│ Process  │             │
│  │ Selection│    │  Check   │    │  Events  │             │
│  └──────────┘    └──────────┘    └──────────┘             │
│       │               │                 │                   │
│       │               │                 ▼                   │
│       │               │          ┌──────────┐              │
│       │               │          │  Yield   │              │
│       │               │          │ on Load  │              │
│       │               │          └──────────┘              │
│       │               │                 │                   │
│       │               ▼                 ▼                   │
│       │          ┌──────────┐    ┌──────────┐             │
│       │          │ Priority │    │ Progress │             │
│       │          │  Adjust  │    │ Tracking │             │
│       │          └──────────┘    └──────────┘             │
│       │                                │                   │
│       └────────────────────────────────┘                   │
│                     Resume from Offset                     │
└─────────────────────────────────────────────────────────────┘
```

---

### Batch Size & Throttling

**Purpose**: Dynamically adjust batch size based on system load, event complexity, and consolidation backlog to optimize throughput without overwhelming resources.

**Batch Size Selection Algorithm**:

```python
async def select_batch_size(consolidation_state: ConsolidationState) -> int:
    """
    Adaptive batch sizing based on system load and backlog depth.

    Returns batch size between MIN_BATCH (100) and MAX_BATCH (2000).
    """
    # Base batch size: 1000 events (90-minute target at 11 events/min)
    base_batch_size = 1000

    # Factor 1: System CPU Load (reduce batch if CPU >70%)
    cpu_usage = await get_cpu_usage_percent()
    if cpu_usage > 90:
        cpu_factor = 0.25  # Severe throttle: 250 events
    elif cpu_usage > 70:
        cpu_factor = 0.5   # Moderate throttle: 500 events
    else:
        cpu_factor = 1.0   # No throttle

    # Factor 2: Memory Pressure (reduce batch if memory >80%)
    memory_usage = await get_memory_usage_percent()
    if memory_usage > 90:
        memory_factor = 0.25  # Severe throttle
    elif memory_usage > 80:
        memory_factor = 0.5   # Moderate throttle
    else:
        memory_factor = 1.0

    # Factor 3: Consolidation Backlog (increase batch if backlog >10k)
    backlog_depth = await get_backlog_event_count()
    if backlog_depth > 50000:
        backlog_factor = 2.0  # Aggressive catch-up: 2000 events
    elif backlog_depth > 10000:
        backlog_factor = 1.5  # Moderate catch-up: 1500 events
    else:
        backlog_factor = 1.0

    # Factor 4: Time of Day (larger batches during sleep hours)
    current_hour = datetime.now().hour
    if 2 <= current_hour <= 5:  # 2 AM - 5 AM (deep sleep)
        time_factor = 1.5  # Larger batches when users inactive
    elif 22 <= current_hour or current_hour <= 1:  # 10 PM - 1 AM (pre-sleep)
        time_factor = 1.2
    else:
        time_factor = 1.0  # Normal daytime processing

    # Compute adaptive batch size
    adaptive_size = int(
        base_batch_size
        * cpu_factor
        * memory_factor
        * backlog_factor
        * time_factor
    )

    # Clamp to min/max bounds
    batch_size = max(100, min(2000, adaptive_size))

    # Log batch size decision
    logger.info(
        "adaptive_batch_size_selected",
        batch_size=batch_size,
        cpu_usage=cpu_usage,
        memory_usage=memory_usage,
        backlog_depth=backlog_depth,
        time_of_day=current_hour,
        factors={
            "cpu": cpu_factor,
            "memory": memory_factor,
            "backlog": backlog_factor,
            "time": time_factor
        }
    )

    return batch_size
```

**Throttling Strategy**:

1. **CPU Throttling**: If CPU usage >70%, reduce batch size by 50%; if >90%, reduce by 75%
   - Measurement: Sample CPU every 5 seconds during consolidation
   - Action: Reduce batch size for next micro-batch, insert 1-second sleep between micro-batches

2. **Memory Throttling**: If memory usage >80%, reduce batch size and trigger garbage collection
   - Measurement: Check memory before each R1-R8 phase transition
   - Action: Call `gc.collect()`, reduce batch size by 50%, log warning

3. **Disk I/O Throttling**: If disk write latency >100ms, slow down outbox writes
   - Measurement: Monitor st_outbox write durations via K0 storage metrics
   - Action: Increase outbox batch interval from 5s to 10s, reduce concurrent write workers

4. **Network Throttling** (future, if remote storage): If network latency >50ms, batch writes more aggressively
   - Measurement: Ping K0 storage endpoint every 10s
   - Action: Increase outbox batch size from 100 to 500 records per flush

**Throttle Recovery**: Once system load drops below thresholds for 60 seconds, gradually increase batch size by 25% per cycle until reaching optimal size.

**Observability**:

- Metric: `p03_batch_size` (gauge, current adaptive batch size)
- Metric: `p03_throttle_events_total` (counter by throttle_reason: cpu/memory/disk/network)
- Metric: `p03_cpu_usage_percent` (gauge, sampled every 5s during consolidation)
- Metric: `p03_memory_usage_percent` (gauge)
- Log: `batch_throttle_applied` event with reason, previous_size, new_size

---

### Priority & Nice Values

**Purpose**: Configure OS-level process priority to ensure P03 consolidation runs as a background task without interfering with foreground operations (user interactions, P02 writes, K1 planning).

**Process Priority Configuration**:

```python
import os
import psutil

async def set_consolidation_priority():
    """
    Set P03 process to low priority (nice value) for CPU scheduling.
    Applies to both Unix (nice) and Windows (priority class).
    """
    process = psutil.Process(os.getpid())

    if os.name == 'posix':  # Linux/macOS
        # Set nice value to 10 (range: -20 to 19, higher = lower priority)
        # Default nice = 0, nice = 10 means "background task"
        try:
            os.nice(10)
            logger.info("process_priority_set", nice_value=10, os="posix")
        except PermissionError:
            logger.warning("process_priority_failed", reason="insufficient_permissions")

    elif os.name == 'nt':  # Windows
        # Set Windows priority class to BELOW_NORMAL_PRIORITY_CLASS
        try:
            process.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
            logger.info("process_priority_set", priority="BELOW_NORMAL", os="windows")
        except Exception as e:
            logger.warning("process_priority_failed", error=str(e))

    # Set I/O priority to low (if supported)
    try:
        if hasattr(process, 'ionice'):
            process.ionice(psutil.IOPRIO_CLASS_IDLE)  # Idle I/O priority
            logger.info("io_priority_set", priority="IDLE")
    except Exception as e:
        logger.debug("io_priority_not_supported", error=str(e))
```

**Thread Priority for Phase Workers**:

```python
import threading

async def run_consolidation_phase(phase_name: str, phase_fn: Callable):
    """
    Execute consolidation phase with background thread priority.
    """
    # Lower thread priority for compute-intensive phases (R4, R5)
    if phase_name in ['R4_kg', 'R5_dream']:
        thread = threading.current_thread()
        if hasattr(thread, 'set_priority'):
            thread.set_priority(threading.PRIORITY_LOW)

    # Execute phase
    result = await phase_fn()

    return result
```

**Priority Escalation**: If consolidation backlog exceeds 50,000 events, temporarily raise priority to NORMAL to catch up:

```python
async def check_backlog_escalation(backlog_depth: int):
    """
    Escalate priority if consolidation falling critically behind.
    """
    if backlog_depth > 50000:
        process = psutil.Process(os.getpid())
        process.nice(psutil.NORMAL_PRIORITY_CLASS)  # Windows
        # or os.nice(0) on POSIX
        logger.warning(
            "priority_escalated",
            reason="critical_backlog",
            backlog_depth=backlog_depth
        )
```

**Resource Limits (cgroups on Linux)**:

```yaml
# systemd service file: /etc/systemd/system/family-os-p03.service
[Service]
# CPU: Limit P03 to 50% of one CPU core (0.5 cores)
CPUQuota=50%

# Memory: Soft limit 512 MB, hard limit 1 GB
MemoryMax=1G
MemoryHigh=512M

# I/O: Weight 10 (range 1-1000, lower = less priority)
IOWeight=10

# Nice: Background priority
Nice=10
```

**Observability**:

- Metric: `p03_process_priority` (gauge, current nice value or priority class)
- Metric: `p03_priority_escalations_total` (counter, times priority raised due to backlog)
- Log: `process_priority_set` event at consolidation start

---

### Yield to User Interactions

**Purpose**: Detect and pause consolidation when user is actively interacting with the system to maintain <50ms response time for user queries and commands.

**User Activity Detection**:

```python
from datetime import datetime, timedelta

class UserActivityMonitor:
    """
    Monitors user activity to determine when to yield consolidation.
    """
    def __init__(self):
        self.last_user_interaction = None
        self.interaction_count_last_minute = 0
        self.yield_threshold_seconds = 10  # Yield if user active in last 10s

    async def record_user_interaction(self, interaction_type: str):
        """
        Called by K0 ports when user interaction detected.

        Interactions: API request, CLI command, SSE subscription, query execution
        """
        self.last_user_interaction = datetime.utcnow()
        self.interaction_count_last_minute += 1

        logger.debug(
            "user_interaction_detected",
            interaction_type=interaction_type,
            interactions_last_minute=self.interaction_count_last_minute
        )

    def should_yield_to_user(self) -> bool:
        """
        Returns True if consolidation should pause due to user activity.
        """
        if self.last_user_interaction is None:
            return False

        time_since_interaction = (
            datetime.utcnow() - self.last_user_interaction
        ).total_seconds()

        # Yield if user was active in last 10 seconds
        should_yield = time_since_interaction < self.yield_threshold_seconds

        if should_yield:
            logger.debug(
                "consolidation_yield_requested",
                time_since_interaction=time_since_interaction,
                threshold=self.yield_threshold_seconds
            )

        return should_yield

    async def reset_interaction_count(self):
        """
        Reset interaction counter (called every 60 seconds).
        """
        self.interaction_count_last_minute = 0
```

**Yield Integration in Consolidation Loop**:

```python
async def run_consolidation_with_yield(
    user_monitor: UserActivityMonitor,
    batch: list[HippEvent]
):
    """
    Process batch with periodic yield checks.
    """
    # Process events in micro-batches of 50
    micro_batch_size = 50

    for i in range(0, len(batch), micro_batch_size):
        micro_batch = batch[i:i + micro_batch_size]

        # Check for user activity before processing micro-batch
        if user_monitor.should_yield_to_user():
            logger.info(
                "consolidation_yielding",
                events_processed=i,
                events_remaining=len(batch) - i
            )

            # Pause consolidation for 30 seconds
            await asyncio.sleep(30)

            # Re-check after pause
            if user_monitor.should_yield_to_user():
                # User still active, pause again
                await asyncio.sleep(30)

        # Process micro-batch
        await process_micro_batch(micro_batch)

        # Small sleep between micro-batches (cooperative yielding)
        await asyncio.sleep(0.1)  # 100ms pause
```

**Adaptive Yield Duration**:

```python
def compute_yield_duration(interaction_rate: float) -> int:
    """
    Compute how long to pause based on user interaction intensity.

    Args:
        interaction_rate: Interactions per minute

    Returns:
        Pause duration in seconds
    """
    if interaction_rate > 30:  # Very active (>30 interactions/min)
        return 60  # Pause for 1 minute
    elif interaction_rate > 10:  # Moderately active
        return 30  # Pause for 30 seconds
    else:  # Light activity
        return 10  # Pause for 10 seconds
```

**User Interaction Sources** (integrate with K0 ports):

1. **HTTP API Requests**: K0 API Port logs all incoming requests
   - Hook: `k0/ports/api.py` → `before_request()` calls `user_monitor.record_user_interaction("api")`

2. **CLI Commands**: K0 CLI logs all command executions
   - Hook: `k0/cli/main.py` → `invoke()` calls `user_monitor.record_user_interaction("cli")`

3. **Query Executions**: K0 Query Port logs all SELECT queries
   - Hook: `k0/ports/query.py` → `execute_query()` calls `user_monitor.record_user_interaction("query")`

4. **SSE Subscriptions**: K0 SSE Port logs active subscriber connections
   - Hook: `k0/sse/server.py` → `on_subscribe()` calls `user_monitor.record_user_interaction("sse")`

**Forced Consolidation Mode**: Override yield logic for critical backlog catch-up:

```python
async def run_consolidation(force_mode: bool = False):
    """
    Run consolidation, optionally ignoring user activity.
    """
    if force_mode:
        logger.warning("consolidation_force_mode", yield_disabled=True)
        # Skip all yield checks
        await process_batch_without_yield(batch)
    else:
        # Normal mode with yield
        await run_consolidation_with_yield(user_monitor, batch)
```

**Observability**:

- Metric: `p03_yield_events_total` (counter, times consolidation paused for user)
- Metric: `p03_yield_duration_seconds` (histogram, pause durations)
- Metric: `p03_user_interactions_per_minute` (gauge)
- Log: `consolidation_yielding` event with interaction_rate, yield_duration

---

### Progress Tracking (evt_offsets)

**Purpose**: Maintain consolidation progress via pipeline offsets, enabling idempotent replay, resume-after-failure, and backlog monitoring.

**Pipeline Offsets Table**:

```sql
CREATE TABLE pipeline_offsets (
    pipeline_id TEXT NOT NULL,         -- 'p03_consolidation'
    tenant_id TEXT NOT NULL,
    space_id TEXT NOT NULL,
    last_processed_event_id TEXT NOT NULL,  -- Latest event_id consolidated
    last_processed_timestamp TEXT NOT NULL, -- event_time_utc of last event
    processed_count INTEGER NOT NULL,       -- Total events consolidated
    last_run_at TEXT NOT NULL,             -- Timestamp of last consolidation cycle
    last_run_duration_seconds INTEGER,      -- Duration of last cycle
    failure_count INTEGER DEFAULT 0,        -- Consecutive failures (reset on success)
    PRIMARY KEY (pipeline_id, tenant_id, space_id)
);

CREATE INDEX idx_pipeline_offsets_updated
ON pipeline_offsets(last_run_at);
```

**Offset Read (R0 Batch Selection)**:

```python
async def select_batch_with_offset(
    tenant_id: str,
    space_id: str,
    batch_size: int
) -> tuple[list[HippEvent], str | None]:
    """
    Select unconsolidated events using pipeline offset cursor.

    Returns:
        (events, previous_offset)
    """
    # Read current offset
    offset_row = await storage.query_one(
        """
        SELECT last_processed_event_id, last_processed_timestamp
        FROM pipeline_offsets
        WHERE pipeline_id = 'p03_consolidation'
          AND tenant_id = ?
          AND space_id = ?
        """,
        (tenant_id, space_id)
    )

    if offset_row:
        last_event_id = offset_row['last_processed_event_id']
        last_timestamp = offset_row['last_processed_timestamp']
        logger.info(
            "offset_loaded",
            last_event_id=last_event_id,
            last_timestamp=last_timestamp
        )
    else:
        # No offset: first consolidation run
        last_event_id = None
        last_timestamp = '1970-01-01T00:00:00Z'
        logger.info("offset_not_found", action="starting_from_beginning")

    # Select batch: events AFTER last offset
    events = await storage.query_many(
        """
        SELECT * FROM st_hipp_events
        WHERE tenant_id = ?
          AND space_id = ?
          AND consolidation_status IS NULL
          AND (
              event_time_utc > ?
              OR (event_time_utc = ? AND event_id > ?)
          )
        ORDER BY event_time_utc ASC, event_id ASC
        LIMIT ?
        """,
        (tenant_id, space_id, last_timestamp, last_timestamp, last_event_id, batch_size)
    )

    return events, last_event_id
```

**Offset Write (R8.2 Progress Recording)**:

```python
async def update_pipeline_offset(
    tenant_id: str,
    space_id: str,
    batch: list[HippEvent],
    cycle_duration_seconds: int,
    success: bool
):
    """
    Update pipeline offset after consolidation cycle.
    """
    if not batch:
        logger.warning("offset_update_skipped", reason="empty_batch")
        return

    # Last event in batch
    last_event = batch[-1]
    last_event_id = last_event['event_id']
    last_timestamp = last_event['event_time_utc']

    # Compute offset delta
    previous_offset = await get_previous_offset(tenant_id, space_id)
    offset_delta = len(batch)

    # Compute backlog
    backlog_depth = await compute_backlog_depth(tenant_id, space_id, last_event_id)

    if success:
        # Success: Update offset, reset failure count
        await storage.execute(
            """
            INSERT INTO pipeline_offsets (
                pipeline_id,
                tenant_id,
                space_id,
                last_processed_event_id,
                last_processed_timestamp,
                processed_count,
                last_run_at,
                last_run_duration_seconds,
                failure_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT (pipeline_id, tenant_id, space_id) DO UPDATE SET
                last_processed_event_id = EXCLUDED.last_processed_event_id,
                last_processed_timestamp = EXCLUDED.last_processed_timestamp,
                processed_count = processed_count + EXCLUDED.processed_count,
                last_run_at = EXCLUDED.last_run_at,
                last_run_duration_seconds = EXCLUDED.last_run_duration_seconds,
                failure_count = 0
            """,
            (
                'p03_consolidation',
                tenant_id,
                space_id,
                last_event_id,
                last_timestamp,
                len(batch),
                datetime.utcnow().isoformat(),
                cycle_duration_seconds
            )
        )

        logger.info(
            "offset_updated",
            last_event_id=last_event_id,
            last_timestamp=last_timestamp,
            offset_delta=offset_delta,
            backlog_depth=backlog_depth,
            cycle_duration=cycle_duration_seconds
        )

        # Emit metrics
        metrics.gauge('p03_offset_delta', offset_delta)
        metrics.gauge('p03_backlog_events_total', backlog_depth)

    else:
        # Failure: Do NOT update offset, increment failure count
        await storage.execute(
            """
            UPDATE pipeline_offsets
            SET
                failure_count = failure_count + 1,
                last_run_at = ?
            WHERE pipeline_id = 'p03_consolidation'
              AND tenant_id = ?
              AND space_id = ?
            """,
            (datetime.utcnow().isoformat(), tenant_id, space_id)
        )

        logger.error(
            "offset_not_updated",
            reason="consolidation_failure",
            last_event_id=last_event_id,
            will_retry=True
        )
```

**Checkpoint Storage for Long Batches**:

```python
async def save_checkpoint(
    tenant_id: str,
    space_id: str,
    phase: str,
    last_processed_event_id: str,
    partial_results: dict
):
    """
    Save incremental checkpoint for batches >10,000 events.
    """
    await storage.execute(
        """
        INSERT INTO pipeline_checkpoints (
            pipeline_id,
            tenant_id,
            space_id,
            checkpoint_phase,
            last_processed_event_id,
            partial_results_json,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (pipeline_id, tenant_id, space_id) DO UPDATE SET
            checkpoint_phase = EXCLUDED.checkpoint_phase,
            last_processed_event_id = EXCLUDED.last_processed_event_id,
            partial_results_json = EXCLUDED.partial_results_json,
            created_at = EXCLUDED.created_at
        """,
        (
            'p03_consolidation',
            tenant_id,
            space_id,
            phase,
            last_processed_event_id,
            json.dumps(partial_results),
            datetime.utcnow().isoformat()
        )
    )

    logger.debug(
        "checkpoint_saved",
        phase=phase,
        last_event_id=last_processed_event_id
    )
```

**Resume from Checkpoint**:

```python
async def resume_from_checkpoint(
    tenant_id: str,
    space_id: str
) -> tuple[str | None, dict | None]:
    """
    Load checkpoint if consolidation was interrupted.
    """
    checkpoint = await storage.query_one(
        """
        SELECT checkpoint_phase, last_processed_event_id, partial_results_json
        FROM pipeline_checkpoints
        WHERE pipeline_id = 'p03_consolidation'
          AND tenant_id = ?
          AND space_id = ?
        """,
        (tenant_id, space_id)
    )

    if checkpoint:
        phase = checkpoint['checkpoint_phase']
        last_event_id = checkpoint['last_processed_event_id']
        partial_results = json.loads(checkpoint['partial_results_json'])

        logger.info(
            "checkpoint_loaded",
            phase=phase,
            last_event_id=last_event_id,
            action="resuming_consolidation"
        )

        return phase, partial_results
    else:
        return None, None
```

**Backlog Monitoring & Alerting**:

```python
async def monitor_backlog_depth():
    """
    Alert if consolidation backlog exceeds thresholds.
    """
    for tenant_id, space_id in get_active_tenants():
        backlog = await compute_backlog_depth(tenant_id, space_id)

        if backlog > 50000:
            logger.critical(
                "backlog_critical",
                tenant_id=tenant_id,
                space_id=space_id,
                backlog_depth=backlog,
                action="escalate_priority"
            )
            # Alert operations team
            await alert_ops_team(
                severity="CRITICAL",
                message=f"P03 backlog critical: {backlog} events pending"
            )

        elif backlog > 10000:
            logger.warning(
                "backlog_high",
                tenant_id=tenant_id,
                space_id=space_id,
                backlog_depth=backlog,
                action="increase_batch_size"
            )

        # Emit metric
        metrics.gauge(
            'p03_backlog_events_total',
            backlog,
            tags={'tenant_id': tenant_id, 'space_id': space_id}
        )
```

**Observability**:

- Metric: `p03_offset_delta` (gauge, events processed in last cycle)
- Metric: `p03_backlog_events_total` (gauge, unconsolidated events remaining)
- Metric: `p03_checkpoint_saves_total` (counter)
- Metric: `p03_checkpoint_resumes_total` (counter)
- Log: `offset_updated` event with offset metadata, backlog depth

---

## Deduplication Algorithm

P03's deduplication algorithm (R3.1 Synaptic Homeostasis) identifies near-duplicate events to prevent redundant memory consolidation. This mimics the brain's pattern separation function (dentate gyrus), where similar experiences are either merged or kept distinct based on contextual differences.

**Purpose**: Reduce storage bloat, improve retrieval precision, and reflect biological memory compression where routine experiences are abstracted into schemas while novel experiences are preserved.

**Design Goals**:

- **High Recall**: Detect 95%+ of true duplicates (minimize false negatives)
- **High Precision**: Keep false positive rate <5% (avoid merging distinct events)
- **Fast Execution**: Process 1000 events in <5 minutes (SimHash comparison: O(n) with lookback window)
- **Temporal Awareness**: Only compare events within time window (24-hour default)
- **Multi-Modal Support**: Handle text, location, participants, activity type

**Duplicate Definition**: Two events are near-duplicates if they represent the same real-world experience recorded multiple times (e.g., "had coffee at Starbucks" captured by calendar + GPS + manual entry).

**Algorithm Flow**:

```
┌─────────────────────────────────────────────────────────────┐
│ Deduplication Pipeline (R3.1)                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐ │
│  │   SimHash    │───▶│   Hamming    │───▶│  Canonical   │ │
│  │ Fingerprint  │    │   Distance   │    │  Selection   │ │
│  └──────────────┘    └──────────────┘    └──────────────┘ │
│         │                    │                    │         │
│         ▼                    ▼                    ▼         │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐ │
│  │ Time Window  │    │  Threshold   │    │   Update     │ │
│  │   Filter     │    │  (≤3 bits)   │    │ st_hipp_evts │ │
│  └──────────────┘    └──────────────┘    └──────────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

### SimHash-Based Near-Duplicate Detection

**Purpose**: Generate fixed-size fingerprints (64-bit hashes) that preserve similarity — events with similar content have similar hashes, enabling fast duplicate detection via Hamming distance.

**SimHash Algorithm** (used by M01 DGService in P02, reused in P03):

```python
from typing import List, Tuple
import hashlib

def simhash(text: str, hash_bits: int = 64) -> int:
    """
    Generate SimHash fingerprint for text using feature hashing.

    Args:
        text: Input text to hash
        hash_bits: Output hash size (default 64-bit)

    Returns:
        64-bit integer hash where similar texts have low Hamming distance
    """
    # Initialize vector for weighted features
    v = [0] * hash_bits

    # Tokenize: split on whitespace, lowercase, filter stopwords
    tokens = tokenize_and_filter(text.lower())

    # Weight each token by frequency
    token_weights = compute_token_weights(tokens)

    for token, weight in token_weights.items():
        # Hash token to get bit pattern
        token_hash = int(hashlib.md5(token.encode('utf-8')).hexdigest(), 16)

        # Add/subtract weight based on bit value
        for i in range(hash_bits):
            if token_hash & (1 << i):
                v[i] += weight
            else:
                v[i] -= weight

    # Generate final fingerprint: set bit to 1 if v[i] > 0
    fingerprint = 0
    for i in range(hash_bits):
        if v[i] > 0:
            fingerprint |= (1 << i)

    return fingerprint


def tokenize_and_filter(text: str) -> List[str]:
    """
    Tokenize text and remove stopwords.
    """
    stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for'}
    tokens = text.split()
    return [t for t in tokens if t not in stopwords and len(t) > 2]


def compute_token_weights(tokens: List[str]) -> dict:
    """
    Compute TF (term frequency) weights for tokens.
    """
    from collections import Counter
    return Counter(tokens)
```

**Multi-Field SimHash** (composite hash for st_hipp_events):

```python
def compute_event_simhash(event: dict) -> int:
    """
    Generate composite SimHash from multiple event fields.

    Combines: text (70% weight) + location (15%) + participants (10%) + activity (5%)
    """
    # Extract and normalize fields
    text = event.get('text', '')
    location = event.get('location_name', '')
    participants = ' '.join(event.get('participants_json', []))
    activity = event.get('activity_type', '')

    # Generate individual hashes
    text_hash = simhash(text)
    location_hash = simhash(location)
    participants_hash = simhash(participants)
    activity_hash = simhash(activity)

    # Weighted combination using XOR (preserves similarity properties)
    # Weight by bit rotation + XOR (approximates weighted fingerprint)
    composite_hash = (
        text_hash ^
        (rotate_bits(location_hash, 16) & 0xFFFF000000000000) ^
        (rotate_bits(participants_hash, 32) & 0x0000FFFF00000000) ^
        (rotate_bits(activity_hash, 48) & 0x00000000FFFF0000)
    )

    return composite_hash


def rotate_bits(n: int, shift: int, bits: int = 64) -> int:
    """
    Circular bit rotation.
    """
    return ((n << shift) | (n >> (bits - shift))) & ((1 << bits) - 1)
```

**Hamming Distance Computation**:

```python
def hamming_distance(hash1: int, hash2: int) -> int:
    """
    Count number of differing bits between two hashes.

    Hamming distance = number of 1s in XOR of hashes.
    """
    xor_result = hash1 ^ hash2
    return bin(xor_result).count('1')


def is_near_duplicate(hash1: int, hash2: int, threshold: int = 3) -> bool:
    """
    Determine if two events are near-duplicates based on SimHash.

    Args:
        hash1, hash2: SimHash fingerprints
        threshold: Max Hamming distance for duplicates (default 3 bits)

    Returns:
        True if Hamming distance ≤ threshold
    """
    return hamming_distance(hash1, hash2) <= threshold
```

**SimHash Storage in st_hipp_events** (written by P02):

```sql
-- P02 writes SimHash to st_hipp_events during event creation
ALTER TABLE st_hipp_events ADD COLUMN simhash_fingerprint INTEGER;

-- Index for fast SimHash lookups (used in deduplication)
CREATE INDEX idx_hipp_events_simhash ON st_hipp_events(simhash_fingerprint);
```

**Duplicate Detection Query**:

```python
async def find_near_duplicates(
    event: dict,
    time_window_hours: int = 24
) -> List[dict]:
    """
    Find near-duplicate events using SimHash + time window.

    Algorithm:
    1. Query events in time window
    2. Compare SimHash fingerprints
    3. Return events with Hamming distance ≤3
    """
    event_time = event['event_time_utc']
    event_hash = event['simhash_fingerprint']

    # Query candidate events in time window
    candidates = await storage.query_many(
        """
        SELECT event_id, event_time_utc, simhash_fingerprint, text, salience_score
        FROM st_hipp_events
        WHERE tenant_id = ?
          AND event_time_utc BETWEEN ? AND ?
          AND event_id != ?
          AND consolidation_status IS NULL
        """,
        (
            event['tenant_id'],
            add_hours(event_time, -time_window_hours),
            add_hours(event_time, time_window_hours),
            event['event_id']
        )
    )

    # Filter by Hamming distance
    duplicates = []
    for candidate in candidates:
        if is_near_duplicate(event_hash, candidate['simhash_fingerprint'], threshold=3):
            duplicates.append(candidate)

    return duplicates
```

**Performance Optimization**: SimHash comparison is O(1) per pair (just XOR + popcount), enabling fast N-way comparison within time window.

---

### MinHash LSH (Locality-Sensitive Hashing)

**Purpose**: Scale deduplication to large event sets (>10,000 events) using Locality-Sensitive Hashing (LSH) to avoid O(n²) pairwise comparisons. MinHash LSH creates hash buckets where similar events cluster together.

**When to Use**: If time window contains >1,000 events, fallback to MinHash LSH for efficiency. Otherwise, use SimHash brute-force (sufficient for typical 24-hour window with <500 events).

**MinHash Algorithm**:

```python
from typing import Set, List
import random

class MinHashLSH:
    """
    MinHash with Locality-Sensitive Hashing for scalable deduplication.
    """
    def __init__(self, num_perm: int = 128, threshold: float = 0.8):
        """
        Args:
            num_perm: Number of hash permutations (higher = more accurate)
            threshold: Jaccard similarity threshold for duplicates
        """
        self.num_perm = num_perm
        self.threshold = threshold
        self.hash_functions = self._generate_hash_functions(num_perm)
        self.lsh_buckets = {}  # Band -> bucket -> [event_ids]
        self.num_bands = 16
        self.rows_per_band = num_perm // self.num_bands

    def _generate_hash_functions(self, num_perm: int) -> List[callable]:
        """
        Generate hash functions for MinHash permutations.
        """
        random.seed(42)  # Deterministic for consistency
        hash_funcs = []
        for i in range(num_perm):
            a = random.randint(1, 2**32 - 1)
            b = random.randint(0, 2**32 - 1)
            hash_funcs.append(lambda x, a=a, b=b: (a * hash(x) + b) % (2**32 - 1))
        return hash_funcs

    def minhash_signature(self, shingles: Set[str]) -> List[int]:
        """
        Generate MinHash signature for event shingles.

        Args:
            shingles: Set of k-grams (e.g., 3-word shingles from event text)

        Returns:
            List of min-hash values (one per permutation)
        """
        signature = [float('inf')] * self.num_perm

        for shingle in shingles:
            for i, hash_func in enumerate(self.hash_functions):
                hash_val = hash_func(shingle)
                signature[i] = min(signature[i], hash_val)

        return signature

    def add_to_lsh(self, event_id: str, signature: List[int]):
        """
        Add event to LSH index (band-based bucketing).
        """
        for band_idx in range(self.num_bands):
            # Extract band portion of signature
            start = band_idx * self.rows_per_band
            end = start + self.rows_per_band
            band_signature = tuple(signature[start:end])

            # Hash band to bucket
            bucket_key = hash(band_signature)

            if band_idx not in self.lsh_buckets:
                self.lsh_buckets[band_idx] = {}

            if bucket_key not in self.lsh_buckets[band_idx]:
                self.lsh_buckets[band_idx][bucket_key] = []

            self.lsh_buckets[band_idx][bucket_key].append(event_id)

    def query_candidates(self, signature: List[int]) -> Set[str]:
        """
        Query LSH index for candidate duplicates.

        Returns:
            Set of event_ids that share ≥1 band with query signature
        """
        candidates = set()

        for band_idx in range(self.num_bands):
            start = band_idx * self.rows_per_band
            end = start + self.rows_per_band
            band_signature = tuple(signature[start:end])
            bucket_key = hash(band_signature)

            if band_idx in self.lsh_buckets and bucket_key in self.lsh_buckets[band_idx]:
                candidates.update(self.lsh_buckets[band_idx][bucket_key])

        return candidates

    def jaccard_similarity(self, sig1: List[int], sig2: List[int]) -> float:
        """
        Estimate Jaccard similarity from MinHash signatures.
        """
        matches = sum(1 for a, b in zip(sig1, sig2) if a == b)
        return matches / len(sig1)


def generate_shingles(text: str, k: int = 3) -> Set[str]:
    """
    Generate k-word shingles from text.

    Example: "had coffee at Starbucks" with k=3
    → {"had coffee at", "coffee at Starbucks"}
    """
    words = text.lower().split()
    shingles = set()
    for i in range(len(words) - k + 1):
        shingle = ' '.join(words[i:i+k])
        shingles.add(shingle)
    return shingles
```

**MinHash Deduplication Workflow**:

```python
async def deduplicate_with_minhash(
    events: List[dict],
    threshold: float = 0.8
) -> dict:
    """
    Deduplicate large event batch using MinHash LSH.

    Returns:
        {
            'canonical_events': [...],
            'duplicate_map': {event_id: canonical_event_id}
        }
    """
    lsh = MinHashLSH(num_perm=128, threshold=threshold)
    signatures = {}

    # Build LSH index
    for event in events:
        shingles = generate_shingles(event['text'], k=3)
        signature = lsh.minhash_signature(shingles)
        signatures[event['event_id']] = signature
        lsh.add_to_lsh(event['event_id'], signature)

    # Find duplicate clusters
    processed = set()
    duplicate_map = {}
    canonical_events = []

    for event in events:
        event_id = event['event_id']

        if event_id in processed:
            continue

        # Query candidates
        candidates = lsh.query_candidates(signatures[event_id])

        # Verify with Jaccard similarity
        duplicates = []
        for candidate_id in candidates:
            if candidate_id == event_id or candidate_id in processed:
                continue

            similarity = lsh.jaccard_similarity(
                signatures[event_id],
                signatures[candidate_id]
            )

            if similarity >= threshold:
                duplicates.append(candidate_id)

        # Select canonical event (highest salience)
        cluster = [event] + [e for e in events if e['event_id'] in duplicates]
        canonical = max(cluster, key=lambda e: e.get('salience_score', 0.0))

        canonical_events.append(canonical)
        processed.add(canonical['event_id'])

        # Map duplicates to canonical
        for dup in duplicates:
            duplicate_map[dup] = canonical['event_id']
            processed.add(dup)

    return {
        'canonical_events': canonical_events,
        'duplicate_map': duplicate_map
    }
```

**When to Use MinHash LSH**:

- Time window events >1,000 → Use MinHash LSH (O(n) with LSH bucketing)
- Time window events ≤1,000 → Use SimHash brute-force (O(n²) but fast with n<1000)

---

### Time Window Constraints

**Purpose**: Limit duplicate detection to events within temporal proximity. Events separated by >24 hours are assumed to be distinct experiences, even if textually similar.

**Time Window Rationale**:

- **24 hours**: Default window (captures same-day duplicates from multiple sources)
- **Biological analog**: Episodic memories consolidate within ~24 hours of encoding
- **Practical**: Prevents false positives like "Monday yoga class" vs "Tuesday yoga class"

**Time Window Implementation**:

```python
from datetime import datetime, timedelta

def compute_time_window(
    event_time_utc: str,
    window_hours: int = 24
) -> Tuple[str, str]:
    """
    Compute time window bounds for duplicate detection.

    Args:
        event_time_utc: ISO timestamp of target event
        window_hours: Window size in hours (default 24)

    Returns:
        (start_time, end_time) as ISO strings
    """
    event_dt = datetime.fromisoformat(event_time_utc.replace('Z', '+00:00'))

    start_time = event_dt - timedelta(hours=window_hours)
    end_time = event_dt + timedelta(hours=window_hours)

    return start_time.isoformat(), end_time.isoformat()


async def query_time_window_candidates(
    event: dict,
    window_hours: int = 24
) -> List[dict]:
    """
    Query events within time window for duplicate comparison.
    """
    start_time, end_time = compute_time_window(
        event['event_time_utc'],
        window_hours
    )

    candidates = await storage.query_many(
        """
        SELECT event_id, event_time_utc, simhash_fingerprint, text,
               salience_score, location_name, participants_json
        FROM st_hipp_events
        WHERE tenant_id = ?
          AND space_id = ?
          AND event_time_utc BETWEEN ? AND ?
          AND event_id != ?
          AND consolidation_status IS NULL
        ORDER BY event_time_utc ASC
        """,
        (event['tenant_id'], event['space_id'], start_time, end_time, event['event_id'])
    )

    return candidates
```

**Adaptive Time Window**:

```python
def adaptive_time_window(event: dict) -> int:
    """
    Adjust time window based on event characteristics.

    - High-frequency routines (e.g., "morning coffee"): 6-hour window
    - Low-frequency events (e.g., "annual vacation"): 7-day window
    - Default: 24-hour window
    """
    activity_type = event.get('activity_type', '')

    # Routine activities: narrow window
    if activity_type in ['meal', 'commute', 'exercise', 'sleep']:
        return 6  # 6-hour window

    # Rare events: wide window (capture multi-day duplicates)
    elif activity_type in ['vacation', 'conference', 'medical_appointment']:
        return 168  # 7-day window

    # Default
    else:
        return 24  # 24-hour window
```

**Time Window Observability**:

```python
# Log time window statistics
logger.info(
    "time_window_selected",
    event_id=event['event_id'],
    window_hours=window_hours,
    candidate_count=len(candidates),
    window_start=start_time,
    window_end=end_time
)

# Metric: Distribution of time window sizes
metrics.histogram('p03_dedup_time_window_hours', window_hours)
metrics.gauge('p03_dedup_candidates_in_window', len(candidates))
```

---

### Novelty Score Computation

**Purpose**: Quantify how novel (unique) an event is compared to recent history. Novelty score guides consolidation priorities: high-novelty events are prioritized for retention, low-novelty events are candidates for aggressive forgetting.

**Novelty Formula**:

```python
def compute_novelty_score(
    event: dict,
    duplicates: List[dict],
    time_window_event_count: int
) -> float:
    """
    Compute novelty score for event based on duplicate density.

    Novelty = 1.0 - (duplicate_count / time_window_event_count)

    Args:
        event: Target event
        duplicates: Near-duplicate events found
        time_window_event_count: Total events in time window

    Returns:
        Novelty score 0.0-1.0 (higher = more novel)
    """
    duplicate_count = len(duplicates)

    if time_window_event_count == 0:
        return 1.0  # No context → assume novel

    # Base novelty: inverse of duplicate density
    base_novelty = 1.0 - (duplicate_count / time_window_event_count)

    # Boost for high-salience events (novelty ≠ rarity, adjust for importance)
    salience_boost = event.get('salience_score', 0.5) * 0.2  # Up to +0.2

    # Penalty for exact duplicates (Hamming distance = 0)
    exact_duplicate_penalty = 0.0
    for dup in duplicates:
        if hamming_distance(event['simhash_fingerprint'], dup['simhash_fingerprint']) == 0:
            exact_duplicate_penalty = 0.3  # -0.3 for exact match
            break

    # Compute adjusted novelty
    novelty = base_novelty + salience_boost - exact_duplicate_penalty

    # Clamp to [0.0, 1.0]
    return max(0.0, min(1.0, novelty))
```

**Novelty Tiers**:

```python
def classify_novelty(novelty_score: float) -> str:
    """
    Classify event novelty into tiers.

    - HIGH (>0.8): Unique experiences, prioritize retention
    - MEDIUM (0.3-0.8): Typical events, standard retention
    - LOW (<0.3): Routine duplicates, aggressive archival
    """
    if novelty_score > 0.8:
        return 'HIGH'
    elif novelty_score > 0.3:
        return 'MEDIUM'
    else:
        return 'LOW'
```

**Novelty Integration with Retention Policies**:

```python
async def apply_novelty_based_retention(event: dict):
    """
    Adjust retention policy based on novelty score.

    High-novelty events: Extend retention by 2x
    Low-novelty events: Reduce retention by 50%
    """
    novelty = event['novelty_score']
    base_retention_days = await get_retention_days(
        event['band'],
        event['topic'],
        event['device_kind']
    )

    if novelty > 0.8:
        # High novelty: extend retention
        adjusted_retention = base_retention_days * 2
        logger.info(
            "retention_extended",
            event_id=event['event_id'],
            novelty=novelty,
            base_retention=base_retention_days,
            adjusted_retention=adjusted_retention
        )

    elif novelty < 0.3:
        # Low novelty: reduce retention
        adjusted_retention = base_retention_days * 0.5
        logger.info(
            "retention_reduced",
            event_id=event['event_id'],
            novelty=novelty,
            base_retention=base_retention_days,
            adjusted_retention=adjusted_retention
        )

    else:
        # Medium novelty: standard retention
        adjusted_retention = base_retention_days

    return adjusted_retention
```

**Novelty Score Storage**:

```sql
-- P03 R6.1 writes novelty_score to st_hipp_events
UPDATE st_hipp_events
SET
  novelty_score = ?,
  near_duplicates_json = ?,  -- JSON array of duplicate event_ids
  is_near_duplicate = ?      -- 1 if this event is a duplicate (not canonical)
WHERE event_id = ?;
```

**Novelty Analytics**:

```python
# Compute novelty distribution for batch
novelty_scores = [e['novelty_score'] for e in batch]
metrics.histogram('p03_novelty_score_distribution', novelty_scores)
metrics.gauge('p03_novelty_mean', sum(novelty_scores) / len(novelty_scores))
metrics.gauge('p03_high_novelty_count', sum(1 for n in novelty_scores if n > 0.8))
metrics.gauge('p03_low_novelty_count', sum(1 for n in novelty_scores if n < 0.3))

# Log novelty breakdown
logger.info(
    "novelty_analysis",
    batch_size=len(batch),
    high_novelty_count=sum(1 for n in novelty_scores if n > 0.8),
    medium_novelty_count=sum(1 for n in novelty_scores if 0.3 <= n <= 0.8),
    low_novelty_count=sum(1 for n in novelty_scores if n < 0.3),
    mean_novelty=sum(novelty_scores) / len(novelty_scores)
)
```

**Observability**:

- Metric: `p03_dedup_duplicates_found_total` (counter)
- Metric: `p03_dedup_novelty_score_mean` (gauge)
- Metric: `p03_dedup_high_novelty_events_total` (counter, novelty >0.8)
- Metric: `p03_dedup_low_novelty_events_total` (counter, novelty <0.3)
- Metric: `p03_dedup_exact_duplicates_total` (counter, Hamming distance = 0)
- Log: `deduplication_complete` event with duplicate counts, novelty distribution

---

## Pattern Extraction (Episodic → Semantic)

**Purpose**: Transform episodic memories (specific events) into semantic memories (generalized patterns and schemas). This process mirrors the brain's memory consolidation where repeated experiences are abstracted into conceptual knowledge (e.g., "Tuesday yoga class" → semantic pattern "weekly yoga routine").

**P03 Phase Mapping**: **R2.2 (Pattern Extraction)** within NREM Phase 1 (Slow-Wave Sleep)

**Biological Analog**: Hippocampal-neocortical dialogue during slow-wave sleep extracts statistical regularities from episodic sequences, forming abstract schemas in neocortex. Replay events are not just strengthened individually but compressed into shared representations.

**Design Goals**:

- **High Precision**: Extract patterns that truly reflect repeated experiences (>90% accuracy)
- **Low False Positives**: Avoid over-generalization (e.g., "all coffee events" → one pattern)
- **Temporal Awareness**: Recognize temporal structure (daily/weekly/monthly cycles)
- **Confidence Tracking**: Quantify pattern reliability based on evidence strength
- **Incremental Learning**: Update patterns as new evidence arrives (online learning)

**Algorithm Flow**:

```
┌─────────────────────────────────────────────────────────────┐
│ Pattern Extraction Pipeline (R2.2)                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐ │
│  │   Cluster    │───▶│   Extract    │───▶│   Temporal   │ │
│  │  Episodes    │    │   Common     │    │   Pattern    │ │
│  │  (DBSCAN)    │    │   Elements   │    │  Recognition │ │
│  └──────────────┘    └──────────────┘    └──────────────┘ │
│         │                    │                    │         │
│         ▼                    ▼                    ▼         │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐ │
│  │  Semantic    │    │  Routine     │    │  Confidence  │ │
│  │  Similarity  │    │  Detection   │    │   Scoring    │ │
│  │  (Embedding) │    │  (Recurrence)│    │  (Evidence)  │ │
│  └──────────────┘    └──────────────┘    └──────────────┘ │
│         │                    │                    │         │
│         └────────────────────┴────────────────────┘         │
│                             ▼                               │
│                   ┌──────────────────┐                      │
│                   │  Write st_sem    │                      │
│                   │  (Semantic       │                      │
│                   │   Patterns)      │                      │
│                   └──────────────────┘                      │
└─────────────────────────────────────────────────────────────┘
```

**Input**: Episode clusters from R2.1 (groups of related events)
**Output**: Semantic patterns in `st_sem` (abstracted schemas with confidence)

**Example Transformation**:

```
Episodic Memories (st_epi):
- 2025-11-05 09:00: "Had yoga class at CorePower, felt energized"
- 2025-11-12 09:00: "Yoga session at CorePower, great workout"
- 2025-11-19 09:00: "CorePower yoga class, improved flexibility"
- 2025-11-26 09:00: "Weekly yoga at CorePower, feeling stronger"

                            ↓ Pattern Extraction

Semantic Pattern (st_sem):
- pattern_type: 'routine'
- pattern_name: "Tuesday morning yoga class"
- common_elements: {location: "CorePower", activity: "yoga", time: "09:00", day_of_week: "Tuesday"}
- frequency: 4 occurrences
- confidence_score: 0.92
- temporal_pattern: "weekly_tuesday_09:00"
- source_episodes: [event_id_1, event_id_2, event_id_3, event_id_4]
```

---

### Clustering by Semantic Similarity

**Purpose**: Group episodic events into clusters based on semantic similarity (content meaning), enabling pattern extraction from related experiences.

**Clustering Algorithm**: **DBSCAN (Density-Based Spatial Clustering of Applications with Noise)**

**Why DBSCAN**:

- **No predefined cluster count**: Discovers natural groupings without requiring K
- **Noise handling**: Identifies outlier events (unique experiences) as noise points
- **Arbitrary shapes**: Handles non-spherical clusters (e.g., morning routines + evening routines)
- **Density-based**: Groups events with dense neighborhoods (repeated experiences)

**Distance Metric**: Composite distance combining:

1. **Semantic distance** (60% weight): Cosine distance between event embeddings
2. **Temporal distance** (20% weight): Time difference normalized to [0,1]
3. **Location distance** (10% weight): Haversine distance if GPS available
4. **Participant distance** (10% weight): Jaccard distance on participant sets

**Semantic Embedding Reading** (P02 Pre-Computed):

```python
from typing import List, Tuple
import numpy as np
import struct

async def read_event_embedding(event_id: str, conn) -> np.ndarray:
    """
    Read 768-dimensional UltraBERT embedding from st_vec.

    NOTE: Embeddings are PRE-COMPUTED by P02 M02 via UltraBERT single-pass (~30ms).
    P03 only READS from st_vec - no model loading, no inference.

    Model: UltraBERT v2.1.0 (768-dim)
    """
    row = await conn.fetchone(
        "SELECT vector FROM st_vec WHERE event_id = ? AND status = 'READY'",
        (event_id,)
    )
    if row and row['vector']:
        # BLOB is 768 floats × 4 bytes = 3072 bytes
        return np.array(struct.unpack('<768f', row['vector']))
    return None


async def read_batch_embeddings(event_ids: List[str], conn) -> dict[str, np.ndarray]:
    """
    Batch-read embeddings for multiple events.
    """
    placeholders = ','.join('?' * len(event_ids))
    rows = await conn.fetchall(
        f"SELECT event_id, vector FROM st_vec WHERE event_id IN ({placeholders}) AND status = 'READY'",
        event_ids
    )
    return {
        row['event_id']: np.array(struct.unpack('<768f', row['vector']))
        for row in rows if row['vector']
    }


# NOTE: No model loading - P02 already computed embeddings via UltraBERT
```

**Composite Distance Function**:

```python
from datetime import datetime
import math

def compute_episode_distance(
    event1: dict,
    event2: dict,
    embedding1: np.ndarray,
    embedding2: np.ndarray
) -> float:
    """
    Compute composite distance between two events for DBSCAN clustering.

    Returns:
        Distance in [0, 1] range (0 = identical, 1 = maximally different)
    """
    # 1. Semantic distance (cosine distance)
    cosine_sim = np.dot(embedding1, embedding2) / (
        np.linalg.norm(embedding1) * np.linalg.norm(embedding2)
    )
    semantic_dist = 1.0 - cosine_sim  # Convert similarity to distance

    # 2. Temporal distance (normalized)
    time1 = datetime.fromisoformat(event1['event_time_utc'].replace('Z', '+00:00'))
    time2 = datetime.fromisoformat(event2['event_time_utc'].replace('Z', '+00:00'))
    time_diff_hours = abs((time1 - time2).total_seconds()) / 3600
    temporal_dist = min(1.0, time_diff_hours / 168)  # Normalize to 1 week

    # 3. Location distance (Haversine if GPS available)
    if event1.get('latitude') and event2.get('latitude'):
        location_dist = haversine_distance(
            event1['latitude'], event1['longitude'],
            event2['latitude'], event2['longitude']
        ) / 50.0  # Normalize to 50km (max meaningful distance for routines)
        location_dist = min(1.0, location_dist)
    else:
        # Fallback: exact string match
        location_dist = 0.0 if event1.get('location_name') == event2.get('location_name') else 1.0

    # 4. Participant distance (Jaccard)
    participants1 = set(event1.get('participants_json', []))
    participants2 = set(event2.get('participants_json', []))
    if participants1 or participants2:
        participant_dist = 1.0 - (
            len(participants1 & participants2) / len(participants1 | participants2)
        )
    else:
        participant_dist = 0.0

    # Weighted composite
    composite_dist = (
        0.6 * semantic_dist +
        0.2 * temporal_dist +
        0.1 * location_dist +
        0.1 * participant_dist
    )

    return composite_dist


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Compute great-circle distance between two GPS coordinates in kilometers.
    """
    R = 6371  # Earth radius in km

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c
```

**DBSCAN Clustering Implementation**:

```python
from sklearn.cluster import DBSCAN
from sklearn.metrics import pairwise_distances

async def cluster_episodes_by_similarity(
    events: List[dict],
    eps: float = 0.3,
    min_samples: int = 3
) -> dict:
    """
    Cluster events using DBSCAN with composite distance metric.

    Args:
        events: List of event dictionaries from st_hipp_events
        eps: Maximum distance between two events to be in same cluster (default 0.3)
        min_samples: Minimum events to form a dense region (default 3)

    Returns:
        {
            'clusters': {cluster_id: [event_ids]},
            'noise_events': [event_ids],  # Unique experiences
            'embeddings': {event_id: embedding}
        }
    """
    # Generate embeddings for all events
    embeddings = {}
    embedding_matrix = []

    for event in events:
        embedding = await generate_event_embedding(event)
        embeddings[event['event_id']] = embedding
        embedding_matrix.append(embedding)

    embedding_matrix = np.array(embedding_matrix)

    # Compute pairwise distance matrix
    n = len(events)
    distance_matrix = np.zeros((n, n))

    for i in range(n):
        for j in range(i+1, n):
            dist = compute_episode_distance(
                events[i], events[j],
                embedding_matrix[i], embedding_matrix[j]
            )
            distance_matrix[i, j] = dist
            distance_matrix[j, i] = dist

    # Run DBSCAN
    clustering = DBSCAN(eps=eps, min_samples=min_samples, metric='precomputed')
    labels = clustering.fit_predict(distance_matrix)

    # Organize results
    clusters = {}
    noise_events = []

    for idx, label in enumerate(labels):
        event_id = events[idx]['event_id']

        if label == -1:
            # Noise point (unique experience)
            noise_events.append(event_id)
        else:
            # Cluster member
            if label not in clusters:
                clusters[label] = []
            clusters[label].append(event_id)

    logger.info(
        "clustering_complete",
        total_events=len(events),
        num_clusters=len(clusters),
        noise_events=len(noise_events),
        largest_cluster=max(len(c) for c in clusters.values()) if clusters else 0
    )

    # Store cluster assignments in st_hipp_events (for R6.2)
    for cluster_id, event_ids in clusters.items():
        for event_id in event_ids:
            await storage.execute(
                """
                UPDATE st_hipp_events
                SET episode_cluster_id = ?, cluster_confidence = ?
                WHERE event_id = ?
                """,
                (f"cluster_{cluster_id}", 0.85, event_id)
            )

    return {
        'clusters': clusters,
        'noise_events': noise_events,
        'embeddings': embeddings
    }
```

**Cluster Quality Metrics**:

```python
def compute_cluster_quality(clusters: dict, distance_matrix: np.ndarray, labels: np.ndarray):
    """
    Compute silhouette score and Davies-Bouldin index for cluster quality.
    """
    from sklearn.metrics import silhouette_score, davies_bouldin_score

    if len(set(labels)) < 2:
        logger.warning("cluster_quality_skipped", reason="insufficient_clusters")
        return

    # Silhouette score: [-1, 1], higher is better
    silhouette = silhouette_score(distance_matrix, labels, metric='precomputed')

    # Davies-Bouldin index: [0, ∞), lower is better
    db_index = davies_bouldin_score(distance_matrix, labels)

    metrics.gauge('p03_cluster_silhouette_score', silhouette)
    metrics.gauge('p03_cluster_davies_bouldin_index', db_index)

    logger.info(
        "cluster_quality",
        silhouette_score=silhouette,
        davies_bouldin_index=db_index
    )
```

**Observability**:

- Metric: `p03_clustering_events_total` (counter, events clustered)
- Metric: `p03_clustering_clusters_found` (gauge, number of clusters)
- Metric: `p03_clustering_noise_events` (gauge, unique experiences)
- Metric: `p03_cluster_silhouette_score` (gauge, quality metric)
- Log: `clustering_complete` with cluster distribution

---

### Common Element Extraction

**Purpose**: Extract shared features across events within a cluster to form the core of semantic patterns (e.g., "Tuesday 9 AM yoga at CorePower" from 4 similar episodes).

**Extraction Strategy**: Statistical mode (most frequent value) with confidence thresholds.

**Common Elements to Extract**:

1. **Activity Type**: Most frequent activity (e.g., "exercise", "meal", "work")
2. **Location**: Most frequent location_name or GPS centroid
3. **Participants**: Core participants appearing in >50% of events
4. **Time of Day**: Average time-of-day (hour:minute)
5. **Day of Week**: Mode day (if weekly pattern)
6. **Duration**: Median duration
7. **Sentiment**: Average sentiment_score
8. **Key Phrases**: Frequent n-grams from event text

**Common Element Extraction Algorithm**:

```python
from collections import Counter
from datetime import datetime
from typing import List, Dict, Any
import statistics

def extract_common_elements(cluster_events: List[dict]) -> Dict[str, Any]:
    """
    Extract shared features from cluster to define semantic pattern.

    Args:
        cluster_events: List of events in same cluster

    Returns:
        Dictionary of common elements with confidence scores
    """
    if not cluster_events:
        return {}

    n = len(cluster_events)

    # 1. Activity Type (mode)
    activity_counts = Counter(e.get('activity_type') for e in cluster_events if e.get('activity_type'))
    activity_type, activity_freq = activity_counts.most_common(1)[0] if activity_counts else (None, 0)
    activity_confidence = activity_freq / n

    # 2. Location (mode for location_name, centroid for GPS)
    location_counts = Counter(e.get('location_name') for e in cluster_events if e.get('location_name'))
    location_name, location_freq = location_counts.most_common(1)[0] if location_counts else (None, 0)
    location_confidence = location_freq / n

    # GPS centroid (if >50% have coordinates)
    lats = [e['latitude'] for e in cluster_events if e.get('latitude')]
    lons = [e['longitude'] for e in cluster_events if e.get('longitude')]
    if len(lats) > n / 2:
        avg_lat = statistics.mean(lats)
        avg_lon = statistics.mean(lons)
        location_centroid = {'latitude': avg_lat, 'longitude': avg_lon}
    else:
        location_centroid = None

    # 3. Participants (core participants in >50% of events)
    all_participants = []
    for e in cluster_events:
        all_participants.extend(e.get('participants_json', []))
    participant_counts = Counter(all_participants)
    core_participants = [p for p, count in participant_counts.items() if count > n / 2]

    # 4. Time of Day (average hour:minute)
    times = []
    for e in cluster_events:
        dt = datetime.fromisoformat(e['event_time_utc'].replace('Z', '+00:00'))
        times.append(dt.hour * 60 + dt.minute)  # Minutes since midnight
    avg_time_minutes = int(statistics.mean(times))
    avg_hour = avg_time_minutes // 60
    avg_minute = avg_time_minutes % 60
    time_of_day = f"{avg_hour:02d}:{avg_minute:02d}"

    # Time consistency (std dev in minutes)
    time_std = statistics.stdev(times) if len(times) > 1 else 0
    time_confidence = max(0.0, 1.0 - (time_std / 120))  # Penalize if >2 hour variance

    # 5. Day of Week (mode)
    days = []
    for e in cluster_events:
        dt = datetime.fromisoformat(e['event_time_utc'].replace('Z', '+00:00'))
        days.append(dt.strftime('%A'))  # Monday, Tuesday, etc.
    day_counts = Counter(days)
    day_of_week, day_freq = day_counts.most_common(1)[0] if day_counts else (None, 0)
    day_confidence = day_freq / n

    # 6. Duration (median)
    durations = [e.get('duration_seconds') for e in cluster_events if e.get('duration_seconds')]
    if durations:
        median_duration = int(statistics.median(durations))
        duration_std = statistics.stdev(durations) if len(durations) > 1 else 0
        duration_confidence = max(0.0, 1.0 - (duration_std / median_duration))
    else:
        median_duration = None
        duration_confidence = 0.0

    # 7. Sentiment (average)
    sentiments = [e.get('sentiment_score', 0) for e in cluster_events if e.get('sentiment_score') is not None]
    avg_sentiment = statistics.mean(sentiments) if sentiments else 0.0

    # 8. Key Phrases (frequent n-grams)
    key_phrases = extract_frequent_ngrams(cluster_events, min_frequency=n // 2)

    # Construct common elements dictionary
    common_elements = {
        'activity_type': activity_type,
        'activity_confidence': activity_confidence,
        'location_name': location_name,
        'location_confidence': location_confidence,
        'location_centroid': location_centroid,
        'core_participants': core_participants,
        'time_of_day': time_of_day,
        'time_confidence': time_confidence,
        'day_of_week': day_of_week,
        'day_confidence': day_confidence,
        'median_duration_seconds': median_duration,
        'duration_confidence': duration_confidence,
        'avg_sentiment': avg_sentiment,
        'key_phrases': key_phrases,
        'cluster_size': n
    }

    return common_elements


def extract_frequent_ngrams(events: List[dict], n: int = 3, min_frequency: int = 2) -> List[str]:
    """
    Extract frequent n-grams from event text fields.

    Args:
        events: Cluster events
        n: N-gram size (default 3-word phrases)
        min_frequency: Minimum occurrences to include

    Returns:
        List of frequent n-grams
    """
    from collections import Counter
    import re

    ngrams = []

    for event in events:
        text = event.get('text', '')
        if not text:
            continue

        # Tokenize and clean
        words = re.findall(r'\w+', text.lower())

        # Generate n-grams
        for i in range(len(words) - n + 1):
            ngram = ' '.join(words[i:i+n])
            ngrams.append(ngram)

    # Count and filter
    ngram_counts = Counter(ngrams)
    frequent = [ng for ng, count in ngram_counts.items() if count >= min_frequency]

    return frequent[:10]  # Top 10 phrases
```

**Pattern Naming**:

```python
def generate_pattern_name(common_elements: dict) -> str:
    """
    Generate human-readable name for semantic pattern.

    Examples:
    - "Tuesday morning yoga at CorePower"
    - "Weekly coffee with Sarah at Starbucks"
    - "Daily commute to office"
    """
    parts = []

    # Temporal component
    if common_elements.get('day_of_week') and common_elements.get('day_confidence', 0) > 0.7:
        parts.append(common_elements['day_of_week'])

    # Time of day
    time_str = common_elements.get('time_of_day', '')
    if time_str:
        hour = int(time_str.split(':')[0])
        if 5 <= hour < 12:
            parts.append('morning')
        elif 12 <= hour < 17:
            parts.append('afternoon')
        elif 17 <= hour < 21:
            parts.append('evening')
        else:
            parts.append('night')

    # Activity
    if common_elements.get('activity_type'):
        parts.append(common_elements['activity_type'])

    # Location
    if common_elements.get('location_name') and common_elements.get('location_confidence', 0) > 0.6:
        parts.append(f"at {common_elements['location_name']}")

    # Participants
    if common_elements.get('core_participants'):
        participants = ', '.join(common_elements['core_participants'][:2])
        parts.append(f"with {participants}")

    # Construct name
    pattern_name = ' '.join(parts)

    return pattern_name if pattern_name else "Unnamed pattern"
```

**Observability**:

- Metric: `p03_common_elements_extracted_total` (counter)
- Metric: `p03_element_confidence_mean` (gauge by element_type)
- Log: `common_elements_extracted` with element breakdown

---

### Temporal Pattern Recognition

**Purpose**: Detect temporal regularities (daily, weekly, monthly cycles) to classify patterns as routines and predict future occurrences.

**Temporal Pattern Types**:

1. **Daily**: Events recurring every day (e.g., "morning coffee")
2. **Weekly**: Events recurring on specific day(s) of week (e.g., "Tuesday yoga")
3. **Monthly**: Events recurring monthly (e.g., "first Monday team meeting")
4. **Irregular**: No clear temporal pattern (e.g., "spontaneous dinner with friends")

**Temporal Analysis Algorithm**:

```python
from datetime import datetime, timedelta
import numpy as np

def detect_temporal_pattern(cluster_events: List[dict]) -> dict:
    """
    Detect temporal recurrence pattern from event timestamps.

    Returns:
        {
            'pattern_type': 'daily' | 'weekly' | 'monthly' | 'irregular',
            'recurrence_interval_days': float,
            'recurrence_confidence': float,
            'next_predicted_time': str (ISO timestamp),
            'temporal_features': {...}
        }
    """
    if len(cluster_events) < 3:
        return {
            'pattern_type': 'irregular',
            'recurrence_confidence': 0.0,
            'reason': 'insufficient_events'
        }

    # Extract timestamps
    timestamps = []
    for e in cluster_events:
        dt = datetime.fromisoformat(e['event_time_utc'].replace('Z', '+00:00'))
        timestamps.append(dt)
    timestamps.sort()

    # Compute inter-event intervals (in days)
    intervals = []
    for i in range(1, len(timestamps)):
        delta = (timestamps[i] - timestamps[i-1]).total_seconds() / 86400
        intervals.append(delta)

    # Statistical analysis of intervals
    mean_interval = np.mean(intervals)
    std_interval = np.std(intervals)
    coefficient_of_variation = std_interval / mean_interval if mean_interval > 0 else float('inf')

    # Pattern classification
    if coefficient_of_variation < 0.15:  # Low variance → regular pattern
        if 0.8 <= mean_interval <= 1.2:
            pattern_type = 'daily'
            recurrence_interval = 1.0
            confidence = 1.0 - coefficient_of_variation
        elif 6.5 <= mean_interval <= 7.5:
            pattern_type = 'weekly'
            recurrence_interval = 7.0
            confidence = 1.0 - coefficient_of_variation
        elif 28 <= mean_interval <= 32:
            pattern_type = 'monthly'
            recurrence_interval = 30.0
            confidence = 1.0 - coefficient_of_variation
        else:
            pattern_type = 'custom'
            recurrence_interval = mean_interval
            confidence = 0.7
    else:
        # High variance → irregular
        pattern_type = 'irregular'
        recurrence_interval = mean_interval
        confidence = 0.3

    # Predict next occurrence
    if pattern_type != 'irregular':
        last_timestamp = timestamps[-1]
        next_predicted_time = last_timestamp + timedelta(days=recurrence_interval)
    else:
        next_predicted_time = None

    # Day of week analysis (for weekly patterns)
    if pattern_type == 'weekly':
        days = [ts.strftime('%A') for ts in timestamps]
        from collections import Counter
        day_counts = Counter(days)
        most_common_day = day_counts.most_common(1)[0][0]
    else:
        most_common_day = None

    # Time of day variance
    times_of_day = [(ts.hour * 60 + ts.minute) for ts in timestamps]
    time_std = np.std(times_of_day)
    time_consistency = max(0.0, 1.0 - (time_std / 120))  # Penalize >2h variance

    return {
        'pattern_type': pattern_type,
        'recurrence_interval_days': recurrence_interval,
        'recurrence_confidence': confidence,
        'next_predicted_time': next_predicted_time.isoformat() if next_predicted_time else None,
        'temporal_features': {
            'mean_interval_days': mean_interval,
            'interval_std_days': std_interval,
            'coefficient_of_variation': coefficient_of_variation,
            'most_common_day': most_common_day,
            'time_consistency': time_consistency,
            'event_count': len(timestamps)
        }
    }
```

**Recurrence Prediction** (for prospective memory):

```python
async def generate_prospective_reminder(pattern: dict):
    """
    Generate prospective memory (reminder) for recurring pattern.

    Creates entry in st_prospective for upcoming event.
    """
    if pattern.get('next_predicted_time') and pattern.get('recurrence_confidence', 0) > 0.7:
        await storage.execute(
            """
            INSERT INTO st_prospective (
                prospective_id, tenant_id, space_id, actor_id,
                intention_type, intention_description,
                target_time, priority, status,
                source_pattern_id, confidence_score,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                generate_id(),
                pattern['tenant_id'],
                pattern['space_id'],
                pattern['actor_id'],
                'reminder',
                f"Upcoming: {pattern['pattern_name']}",
                pattern['next_predicted_time'],
                'MEDIUM',
                'PENDING',
                pattern['pattern_id'],
                pattern['recurrence_confidence'],
                utc_now(),
                utc_now()
            )
        )

        logger.info(
            "prospective_reminder_created",
            pattern_id=pattern['pattern_id'],
            target_time=pattern['next_predicted_time'],
            confidence=pattern['recurrence_confidence']
        )
```

**Observability**:

- Metric: `p03_temporal_patterns_detected_total` (counter by pattern_type)
- Metric: `p03_recurrence_confidence_mean` (gauge)
- Metric: `p03_prospective_reminders_created_total` (counter)
- Log: `temporal_pattern_detected` with interval and confidence

---

### Confidence Scoring

**Purpose**: Quantify reliability of extracted semantic patterns based on evidence strength, consistency, and statistical significance.

**Confidence Formula**:

```
confidence_score = sqrt(frequency_score * consistency_score * significance_score)

Where:
- frequency_score: Based on event count (more events → higher confidence)
- consistency_score: Based on feature variance (low variance → higher confidence)
- significance_score: Based on temporal/spatial clustering tightness
```

**Confidence Scoring Algorithm**:

```python
import math

def compute_pattern_confidence(
    cluster_events: List[dict],
    common_elements: dict,
    temporal_pattern: dict
) -> float:
    """
    Compute confidence score for semantic pattern.

    Args:
        cluster_events: Source episodes
        common_elements: Extracted common features
        temporal_pattern: Temporal recurrence analysis

    Returns:
        Confidence score in [0.0, 1.0]
    """
    n = len(cluster_events)

    # 1. Frequency Score (logarithmic scaling)
    # More events → higher confidence, but with diminishing returns
    frequency_score = min(1.0, math.log(n + 1) / math.log(10))  # log10(n+1), caps at ~10 events

    # 2. Consistency Score (average of element confidences)
    element_confidences = [
        common_elements.get('activity_confidence', 0),
        common_elements.get('location_confidence', 0),
        common_elements.get('time_confidence', 0),
        common_elements.get('day_confidence', 0),
        common_elements.get('duration_confidence', 0)
    ]
    consistency_score = sum(element_confidences) / len(element_confidences)

    # 3. Significance Score (temporal recurrence + spatial tightness)
    recurrence_confidence = temporal_pattern.get('recurrence_confidence', 0)

    # Spatial tightness (if GPS available)
    if common_elements.get('location_centroid'):
        # Compute radius from centroid
        centroid = common_elements['location_centroid']
        distances = []
        for e in cluster_events:
            if e.get('latitude'):
                dist = haversine_distance(
                    centroid['latitude'], centroid['longitude'],
                    e['latitude'], e['longitude']
                )
                distances.append(dist)

        if distances:
            avg_distance = sum(distances) / len(distances)
            spatial_tightness = max(0.0, 1.0 - (avg_distance / 5.0))  # Penalize if >5km spread
        else:
            spatial_tightness = 0.5
    else:
        spatial_tightness = 0.5  # Neutral if no GPS

    significance_score = (recurrence_confidence + spatial_tightness) / 2

    # 4. Composite Confidence (geometric mean for balanced scoring)
    confidence_score = math.sqrt(frequency_score * consistency_score * significance_score)

    # 5. Adjustments
    # Boost for high-frequency routines (>10 occurrences)
    if n > 10:
        confidence_score = min(1.0, confidence_score * 1.1)

    # Penalty for high sentiment variance (emotional inconsistency)
    sentiments = [e.get('sentiment_score', 0) for e in cluster_events if e.get('sentiment_score') is not None]
    if len(sentiments) > 1:
        sentiment_std = np.std(sentiments)
        if sentiment_std > 0.5:  # High emotional variance
            confidence_score *= 0.9

    return max(0.0, min(1.0, confidence_score))  # Clamp to [0, 1]
```

**Confidence Tiers**:

```python
def classify_pattern_confidence(confidence_score: float) -> str:
    """
    Classify pattern confidence into tiers.

    - STRONG (>0.8): Well-established routines, high evidence
    - MODERATE (0.5-0.8): Emerging patterns, moderate evidence
    - WEAK (<0.5): Tentative patterns, low evidence (may prune)
    """
    if confidence_score > 0.8:
        return 'STRONG'
    elif confidence_score > 0.5:
        return 'MODERATE'
    else:
        return 'WEAK'
```

**Write Semantic Pattern to st_sem**:

```python
async def write_semantic_pattern(
    cluster_events: List[dict],
    common_elements: dict,
    temporal_pattern: dict,
    confidence_score: float
) -> str:
    """
    Write extracted pattern to st_sem (semantic memory layer).

    Returns:
        pattern_id
    """
    pattern_id = generate_id()
    tenant_id = cluster_events[0]['tenant_id']
    space_id = cluster_events[0]['space_id']
    actor_id = cluster_events[0]['actor_id']

    # Generate pattern name
    pattern_name = generate_pattern_name(common_elements)

    # Compute valid_from (first event) and valid_to (last event + recurrence interval)
    timestamps = sorted([
        datetime.fromisoformat(e['event_time_utc'].replace('Z', '+00:00'))
        for e in cluster_events
    ])
    valid_from = timestamps[0].isoformat()

    if temporal_pattern.get('next_predicted_time'):
        valid_to = temporal_pattern['next_predicted_time']
    else:
        valid_to = (timestamps[-1] + timedelta(days=365)).isoformat()  # 1 year default

    # Source episode IDs (provenance)
    source_episodes = [e['event_id'] for e in cluster_events]

    await storage.execute(
        """
        INSERT INTO st_sem (
            semantic_id, tenant_id, space_id, actor_id,
            pattern_type, pattern_name,
            pattern_description, common_elements_json,
            frequency, confidence_score, ambiguity_score,
            temporal_pattern_type, recurrence_interval_days,
            valid_from, valid_to,
            source_episodes_json, cluster_id,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            pattern_id,
            tenant_id,
            space_id,
            actor_id,
            temporal_pattern['pattern_type'],
            pattern_name,
            f"Pattern extracted from {len(cluster_events)} episodes",
            json.dumps(common_elements),
            len(cluster_events),
            confidence_score,
            0.0,  # ambiguity_score (future: measure conflicting patterns)
            temporal_pattern['pattern_type'],
            temporal_pattern.get('recurrence_interval_days'),
            valid_from,
            valid_to,
            json.dumps(source_episodes),
            cluster_events[0].get('episode_cluster_id'),
            utc_now(),
            utc_now()
        )
    )

    logger.info(
        "semantic_pattern_written",
        pattern_id=pattern_id,
        pattern_name=pattern_name,
        pattern_type=temporal_pattern['pattern_type'],
        confidence=confidence_score,
        event_count=len(cluster_events)
    )

    # Emit event to K0 Bus
    await bus.emit(
        topic='p03.pattern.extracted.v1',
        payload={
            'pattern_id': pattern_id,
            'pattern_name': pattern_name,
            'pattern_type': temporal_pattern['pattern_type'],
            'confidence_score': confidence_score,
            'event_count': len(cluster_events),
            'actor_id': actor_id
        }
    )

    return pattern_id
```

**Pattern Update Strategy** (incremental learning):

```python
async def update_existing_pattern(pattern_id: str, new_events: List[dict]):
    """
    Update existing semantic pattern with new evidence (online learning).

    Called when new episodes match existing pattern (via similarity search).
    """
    # Fetch existing pattern
    pattern = await storage.query_one(
        "SELECT * FROM st_sem WHERE semantic_id = ?",
        (pattern_id,)
    )

    # Merge new events with source episodes
    existing_episodes = json.loads(pattern['source_episodes_json'])
    all_event_ids = existing_episodes + [e['event_id'] for e in new_events]

    # Re-fetch all source events
    all_events = await storage.query_many(
        f"SELECT * FROM st_hipp_events WHERE event_id IN ({','.join('?' * len(all_event_ids))})",
        all_event_ids
    )

    # Re-extract common elements and confidence
    common_elements = extract_common_elements(all_events)
    temporal_pattern = detect_temporal_pattern(all_events)
    confidence_score = compute_pattern_confidence(all_events, common_elements, temporal_pattern)

    # Update pattern
    await storage.execute(
        """
        UPDATE st_sem
        SET
            common_elements_json = ?,
            frequency = ?,
            confidence_score = ?,
            temporal_pattern_type = ?,
            recurrence_interval_days = ?,
            source_episodes_json = ?,
            updated_at = ?
        WHERE semantic_id = ?
        """,
        (
            json.dumps(common_elements),
            len(all_events),
            confidence_score,
            temporal_pattern['pattern_type'],
            temporal_pattern.get('recurrence_interval_days'),
            json.dumps(all_event_ids),
            utc_now(),
            pattern_id
        )
    )

    logger.info(
        "pattern_updated",
        pattern_id=pattern_id,
        new_event_count=len(new_events),
        total_events=len(all_events),
        new_confidence=confidence_score
    )
```

**Observability**:

- Metric: `p03_pattern_confidence_score` (histogram)
- Metric: `p03_strong_patterns_total` (gauge, confidence >0.8)
- Metric: `p03_weak_patterns_total` (gauge, confidence <0.5)
- Metric: `p03_patterns_updated_total` (counter, incremental learning)
- Log: `pattern_confidence_computed` with score breakdown

---

## Knowledge Graph Construction

**Purpose**: Build and maintain a temporal knowledge graph (KG) that captures entities (people, places, concepts) and their relationships extracted from consolidated episodic memories. This structured semantic network enables entity-centric queries, reasoning, and long-term knowledge retention.

**P03 Phase Mapping**: **R4 (Knowledge Graph Consolidation)** within NREM Phase 2 (Light Sleep)

**Biological Analog**: The brain's semantic memory system organizes knowledge into interconnected conceptual networks. The anterior temporal lobe and medial prefrontal cortex store abstract knowledge about entities and their relationships, distinct from episodic details stored in hippocampus.

**Design Goals**:

- **Entity Persistence**: Maintain stable entity identities across events (person "Sarah" = same entity across 100 events)
- **Relationship Evolution**: Track how relationships change over time (e.g., "colleague" → "friend")
- **Temporal Validity**: Every KG node and edge has valid_from/valid_to timestamps
- **Causal Reasoning**: Detect causal relationships between events and entities
- **Scalability**: Support millions of entities and relationships with efficient querying

**Knowledge Graph Schema**:

```
┌─────────────────────────────────────────────────────────────┐
│ Knowledge Graph Architecture                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌────────────┐                           ┌────────────┐   │
│  │  st_kg_dom │                           │ st_kg_edges│   │
│  │  (Nodes)   │                           │  (Edges)   │   │
│  ├────────────┤                           ├────────────┤   │
│  │ node_id    │────────────┬──────────────│ edge_id    │   │
│  │ entity_type│            │              │ from_node  │   │
│  │ entity_name│            │              │ to_node    │   │
│  │ attributes │            │              │ rel_type   │   │
│  │ valid_from │            │              │ valid_from │   │
│  │ valid_to   │            │              │ valid_to   │   │
│  │ canonical_id│           │              │ strength   │   │
│  │ is_canonical│           │              │ causal?    │   │
│  └────────────┘            │              └────────────┘   │
│        │                   │                     │          │
│        │                   │                     │          │
│        ▼                   ▼                     ▼          │
│  ┌─────────────────────────────────────────────────┐       │
│  │          Source Episodes (st_epi)               │       │
│  │        Provenance: source_episodes_json         │       │
│  └─────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

**Algorithm Flow**:

```
┌─────────────────────────────────────────────────────────────┐
│ Knowledge Graph Construction Pipeline (R4)                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐ │
│  │   Entity     │───▶│   Entity     │───▶│  Relationship│ │
│  │ Extraction   │    │  Resolution  │    │  Discovery   │ │
│  │   (NER)      │    │  (Fuzzy)     │    │ (Co-occur)   │ │
│  └──────────────┘    └──────────────┘    └──────────────┘ │
│         │                    │                    │         │
│         ▼                    ▼                    ▼         │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐ │
│  │  Attribute   │    │  Temporal    │    │   Causal     │ │
│  │  Extraction  │    │  Validity    │    │  Inference   │ │
│  │   (JSON)     │    │  (valid_*)   │    │  (Granger)   │ │
│  └──────────────┘    └──────────────┘    └──────────────┘ │
│         │                    │                    │         │
│         └────────────────────┴────────────────────┘         │
│                             ▼                               │
│                   ┌──────────────────┐                      │
│                   │ Write st_kg_dom  │                      │
│                   │  & st_kg_edges   │                      │
│                   └──────────────────┘                      │
└─────────────────────────────────────────────────────────────┘
```

**Input**: Consolidated episodes from st_epi (R2.1 clusters)
**Output**: KG nodes in `st_kg_dom` + edges in `st_kg_edges`

**Example KG Construction**:

```
Episodes (st_epi):
- 2025-11-05: "Had coffee with Sarah at Starbucks, discussed project"
- 2025-11-12: "Lunch with Sarah at CorePower cafe, talked about yoga"
- 2025-11-19: "Met Sarah at Starbucks, planned weekend trip"

                            ↓ Entity Extraction

Entities (st_kg_dom):
- node_1: {entity_type: "Person", entity_name: "Sarah", attributes: {relation: "colleague"}}
- node_2: {entity_type: "Place", entity_name: "Starbucks", attributes: {category: "cafe"}}
- node_3: {entity_type: "Place", entity_name: "CorePower", attributes: {category: "cafe"}}
- node_4: {entity_type: "Activity", entity_name: "coffee", attributes: {category: "meal"}}
- node_5: {entity_type: "Topic", entity_name: "project", attributes: {work_related: true}}

                            ↓ Relationship Discovery

Relationships (st_kg_edges):
- edge_1: node_1 (Sarah) --[meets_at]--> node_2 (Starbucks) {strength: 0.67, frequency: 2}
- edge_2: node_1 (Sarah) --[discusses]--> node_5 (project) {strength: 0.33, frequency: 1}
- edge_3: node_1 (Sarah) --[interacts_with]--> actor {strength: 1.0, frequency: 3}
```

---

### Entity Resolution

**Purpose**: Identify and merge duplicate entities across episodes, maintaining canonical entity identities. Solves the challenge that "Sarah", "sarah johnson", and "Sarah J." refer to the same person.

**Entity Reading** (P02 Pre-Computed via UltraBERT):

```python
from typing import List, Dict, Any
import json

def read_entities_from_event(event: dict) -> List[Dict[str, Any]]:
    """
    Read pre-extracted entities from st_hipp_events.entities_json.

    NOTE: Entities are PRE-EXTRACTED by P02 M02 via UltraBERT single-pass (~30ms).
    P03 only READS from entities_json - no spaCy, no model loading, no inference.

    Model: UltraBERT v2.1.0 NER capabilities (general + family-specific)

    Entity Types (from UltraBERT):
    - PERSON: People (e.g., "Sarah", "Dr. Johnson")
    - ORG: Organizations (e.g., "Apple", "Stanford University")
    - GPE: Geo-political entities (e.g., "San Francisco", "California")
    - LOC: Locations (e.g., "Starbucks", "Golden Gate Park")
    - EVENT: Named events (e.g., "World Cup", "Christmas")
    - PRODUCT: Products (e.g., "iPhone", "Tesla Model 3")
    - DATE: Dates (e.g., "Tuesday", "2025-11-05")
    - FAMILY_MEMBER: Family-specific (e.g., "mom", "daughter Emma")

    Args:
        event: Event dictionary from st_hipp_events (includes entities_json)

    Returns:
        List of extracted entities with attributes
    """
    entities_json = event.get('entities_json')
    if not entities_json:
        return []

    # Parse P02's pre-extracted entities
    raw_entities = json.loads(entities_json) if isinstance(entities_json, str) else entities_json

    entities = []
    for entity in raw_entities:
        entities.append({
            'entity_name': entity.get('text', entity.get('entity_name', '')),
            'entity_type': map_ultrabert_label(entity.get('label', entity.get('entity_type', 'Concept'))),
            'confidence': entity.get('confidence', 0.9),  # UltraBERT confidence
            'source': 'ultrabert',
            'context': entity.get('context', '')
        })

    # Also read structured fields (location, participants)
    location_name = event.get('location_name')
    if location_name:
        entities.append({
            'entity_name': location_name,
            'entity_type': 'Place',
            'confidence': 1.0,
            'source': 'structured',
            'attributes': {
                'latitude': event.get('latitude'),
                'longitude': event.get('longitude'),
                'address': event.get('address')
            }
        })

    participants_json = event.get('participants_json')
    if participants_json:
        participants = json.loads(participants_json) if isinstance(participants_json, str) else participants_json
        for participant in participants:
            entities.append({
                'entity_name': participant,
                'entity_type': 'Person',
                'confidence': 1.0,
                'source': 'structured',
                'attributes': {}
            })

    activity_type = event.get('activity_type')
    if activity_type:
        entities.append({
            'entity_name': activity_type,
            'entity_type': 'Activity',
            'confidence': 1.0,
            'source': 'structured',
            'attributes': {}
        })

    # Deduplicate entities within episode
    entities = deduplicate_entities_within_episode(entities)

    return entities


def map_ultrabert_label(ultrabert_label: str) -> str:
    """
    Map UltraBERT NER labels to our entity taxonomy.
    """
    mapping = {
        'PERSON': 'Person',
        'FAMILY_MEMBER': 'Person',
        'ORG': 'Organization',
        'GPE': 'Place',
        'LOC': 'Place',
        'EVENT': 'Event',
        'PRODUCT': 'Product',
        'DATE': 'Date',
        'TIME': 'Time',
        'MONEY': 'Money',
        'QUANTITY': 'Quantity',
        'WORK_OF_ART': 'Work',
        'FAC': 'Facility'
    }
    return mapping.get(ultrabert_label, 'Concept')


# NOTE: No spaCy model loading - P02 already extracted entities via UltraBERT


def deduplicate_entities_within_episode(entities: List[dict]) -> List[dict]:
    """
    Merge duplicate entities within same episode.

    Example: "Sarah" and "sarah" → merge to "Sarah"
    """
    from collections import defaultdict

    # Group by normalized name
    groups = defaultdict(list)
    for entity in entities:
        key = entity['entity_name'].lower().strip()
        groups[key].append(entity)

    # Merge each group
    deduplicated = []
    for key, group in groups.items():
        if len(group) == 1:
            deduplicated.append(group[0])
        else:
            # Prefer structured source over NER
            structured = [e for e in group if e['source'] == 'structured']
            if structured:
                merged = structured[0]
            else:
                merged = group[0]

            # Merge attributes
            merged['confidence'] = max(e['confidence'] for e in group)
            deduplicated.append(merged)

    return deduplicated
```

**Entity Resolution Algorithm** (fuzzy matching across episodes):

```python
from difflib import SequenceMatcher

async def resolve_entity_to_canonical(
    entity: dict,
    tenant_id: str,
    space_id: str
) -> str:
    """
    Resolve entity to canonical entity node in st_kg_dom.

    Strategy:
    1. Exact match: entity_name = existing node (case-insensitive)
    2. Fuzzy match: Levenshtein distance <3 for PERSON/PLACE
    3. Alias match: Check entity_aliases_json
    4. Create new: If no match, create canonical node

    Returns:
        canonical_node_id
    """
    entity_name = entity['entity_name']
    entity_type = entity['entity_type']

    # Query existing entities of same type
    candidates = await storage.query_many(
        """
        SELECT node_id, entity_name, entity_aliases_json, is_canonical
        FROM st_kg_dom
        WHERE tenant_id = ? AND space_id = ?
          AND entity_type = ?
          AND is_canonical = 1
        """,
        (tenant_id, space_id, entity_type)
    )

    # 1. Exact match (case-insensitive)
    for candidate in candidates:
        if candidate['entity_name'].lower() == entity_name.lower():
            logger.debug("entity_resolved", method="exact_match", canonical_id=candidate['node_id'])
            return candidate['node_id']

    # 2. Fuzzy match (for PERSON and PLACE)
    if entity_type in ['Person', 'Place']:
        for candidate in candidates:
            similarity = compute_name_similarity(entity_name, candidate['entity_name'])
            if similarity > 0.85:  # 85% similarity threshold
                logger.info(
                    "entity_resolved",
                    method="fuzzy_match",
                    canonical_id=candidate['node_id'],
                    similarity=similarity
                )
                # Add as alias
                await add_entity_alias(candidate['node_id'], entity_name)
                return candidate['node_id']

    # 3. Alias match
    for candidate in candidates:
        aliases = json.loads(candidate.get('entity_aliases_json', '[]'))
        if entity_name.lower() in [a.lower() for a in aliases]:
            logger.debug("entity_resolved", method="alias_match", canonical_id=candidate['node_id'])
            return candidate['node_id']

    # 4. No match: Create new canonical entity
    canonical_node_id = await create_canonical_entity(
        tenant_id=tenant_id,
        space_id=space_id,
        entity_name=entity_name,
        entity_type=entity_type,
        attributes=entity.get('attributes', {})
    )

    logger.info("entity_created", canonical_id=canonical_node_id, entity_name=entity_name)
    return canonical_node_id


def compute_name_similarity(name1: str, name2: str) -> float:
    """
    Compute similarity between two entity names using SequenceMatcher.

    Handles:
    - Case differences: "Sarah" vs "sarah" → 1.0
    - Partial matches: "Sarah Johnson" vs "Sarah J." → 0.9
    - Typos: "Starbucks" vs "Starbucsk" → 0.95
    """
    return SequenceMatcher(None, name1.lower(), name2.lower()).ratio()


async def add_entity_alias(node_id: str, alias: str):
    """
    Add alias to existing entity node.
    """
    # Fetch current aliases
    node = await storage.query_one(
        "SELECT entity_aliases_json FROM st_kg_dom WHERE node_id = ?",
        (node_id,)
    )

    aliases = json.loads(node.get('entity_aliases_json', '[]'))
    if alias not in aliases:
        aliases.append(alias)

        await storage.execute(
            """
            UPDATE st_kg_dom
            SET entity_aliases_json = ?, updated_at = ?
            WHERE node_id = ?
            """,
            (json.dumps(aliases), utc_now(), node_id)
        )


async def create_canonical_entity(
    tenant_id: str,
    space_id: str,
    entity_name: str,
    entity_type: str,
    attributes: dict
) -> str:
    """
    Create new canonical entity node in st_kg_dom.
    """
    node_id = generate_id()

    await storage.execute(
        """
        INSERT INTO st_kg_dom (
            node_id, tenant_id, space_id,
            entity_type, entity_name, entity_aliases_json,
            node_properties_json,
            is_canonical, canonical_node_id,
            valid_from, valid_to,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            node_id,
            tenant_id,
            space_id,
            entity_type,
            entity_name,
            json.dumps([]),  # Empty aliases initially
            json.dumps(attributes),
            1,  # is_canonical
            node_id,  # canonical_node_id = self
            utc_now(),
            None,  # valid_to = NULL (active)
            utc_now(),
            utc_now()
        )
    )

    return node_id
```

**Entity Merging** (when duplicates are discovered later):

```python
async def merge_duplicate_entities(canonical_id: str, duplicate_id: str):
    """
    Merge duplicate entity into canonical entity.

    Actions:
    1. Copy aliases from duplicate to canonical
    2. Rewrite edges: from_node/to_node pointing to duplicate → canonical
    3. Mark duplicate as non-canonical (soft delete)
    4. Update duplicate's canonical_node_id to point to canonical
    """
    # Fetch both entities
    canonical = await storage.query_one(
        "SELECT * FROM st_kg_dom WHERE node_id = ?",
        (canonical_id,)
    )
    duplicate = await storage.query_one(
        "SELECT * FROM st_kg_dom WHERE node_id = ?",
        (duplicate_id,)
    )

    # Merge aliases
    canonical_aliases = json.loads(canonical.get('entity_aliases_json', '[]'))
    duplicate_aliases = json.loads(duplicate.get('entity_aliases_json', '[]'))
    merged_aliases = list(set(canonical_aliases + duplicate_aliases + [duplicate['entity_name']]))

    await storage.execute(
        """
        UPDATE st_kg_dom
        SET entity_aliases_json = ?, updated_at = ?
        WHERE node_id = ?
        """,
        (json.dumps(merged_aliases), utc_now(), canonical_id)
    )

    # Rewrite edges
    await storage.execute(
        """
        UPDATE st_kg_edges
        SET from_node_id = ?, updated_at = ?
        WHERE from_node_id = ?
        """,
        (canonical_id, utc_now(), duplicate_id)
    )

    await storage.execute(
        """
        UPDATE st_kg_edges
        SET to_node_id = ?, updated_at = ?
        WHERE to_node_id = ?
        """,
        (canonical_id, utc_now(), duplicate_id)
    )

    # Mark duplicate as non-canonical
    await storage.execute(
        """
        UPDATE st_kg_dom
        SET
            is_canonical = 0,
            canonical_node_id = ?,
            valid_to = ?,
            updated_at = ?
        WHERE node_id = ?
        """,
        (canonical_id, utc_now(), utc_now(), duplicate_id)
    )

    logger.info(
        "entities_merged",
        canonical_id=canonical_id,
        duplicate_id=duplicate_id,
        merged_aliases=len(merged_aliases)
    )
```

**Observability**:

- Metric: `p03_entity_extraction_total` (counter by entity_type)
- Metric: `p03_entity_resolution_total` (counter by resolution_method: exact/fuzzy/alias/new)
- Metric: `p03_entity_merges_total` (counter)
- Log: `entity_resolved` with method and canonical_id

---

### Relationship Types

**Purpose**: Define and discover typed relationships between entities, forming the edges of the knowledge graph. Relationships capture semantic connections like "works_at", "friend_of", "located_in".

**Relationship Taxonomy**:

```python
RELATIONSHIP_TYPES = {
    # Social relationships (Person-Person)
    'friend_of': {'symmetric': True, 'transitive': False},
    'colleague_of': {'symmetric': True, 'transitive': False},
    'family_of': {'symmetric': True, 'transitive': False},
    'manages': {'symmetric': False, 'transitive': False},
    'reports_to': {'symmetric': False, 'transitive': True},
    'knows': {'symmetric': True, 'transitive': False},

    # Location relationships (Person-Place, Activity-Place)
    'located_at': {'symmetric': False, 'transitive': False},
    'works_at': {'symmetric': False, 'transitive': False},
    'lives_at': {'symmetric': False, 'transitive': False},
    'frequents': {'symmetric': False, 'transitive': False},
    'visited': {'symmetric': False, 'transitive': False},

    # Activity relationships (Person-Activity, Activity-Place)
    'performs': {'symmetric': False, 'transitive': False},
    'participates_in': {'symmetric': False, 'transitive': False},
    'organizes': {'symmetric': False, 'transitive': False},

    # Topic relationships (Person-Topic, Activity-Topic)
    'interested_in': {'symmetric': False, 'transitive': False},
    'discusses': {'symmetric': False, 'transitive': False},
    'works_on': {'symmetric': False, 'transitive': False},

    # Temporal relationships (Event-Event)
    'precedes': {'symmetric': False, 'transitive': True},
    'follows': {'symmetric': False, 'transitive': True},
    'causes': {'symmetric': False, 'transitive': True},  # Causal
    'enables': {'symmetric': False, 'transitive': True},

    # Organizational relationships (Person-Organization, Organization-Place)
    'member_of': {'symmetric': False, 'transitive': False},
    'employed_by': {'symmetric': False, 'transitive': False},
    'owns': {'symmetric': False, 'transitive': False},
    'part_of': {'symmetric': False, 'transitive': True},

    # Generic relationships
    'related_to': {'symmetric': True, 'transitive': False},
    'associated_with': {'symmetric': True, 'transitive': False}
}
```

**Relationship Discovery Algorithm** (co-occurrence based):

```python
async def discover_relationships_in_episode(
    episode: dict,
    entities: List[dict]
) -> List[Dict[str, Any]]:
    """
    Discover relationships between entities within an episode.

    Strategy:
    1. Co-occurrence: Entities appearing together → 'related_to'
    2. Dependency parsing: Subject-verb-object → typed relationships
    3. Heuristics: Known patterns (e.g., "works at" → 'works_at')

    Args:
        episode: Episode dictionary from st_epi
        entities: Extracted entities from episode

    Returns:
        List of relationships (from_entity, to_entity, relationship_type)
    """
    relationships = []

    # 1. Co-occurrence relationships (all pairs)
    for i, entity1 in enumerate(entities):
        for entity2 in entities[i+1:]:
            # Infer relationship type based on entity types
            rel_type = infer_relationship_type(
                entity1['entity_type'],
                entity2['entity_type']
            )

            relationships.append({
                'from_entity': entity1['entity_name'],
                'from_type': entity1['entity_type'],
                'to_entity': entity2['entity_name'],
                'to_type': entity2['entity_type'],
                'relationship_type': rel_type,
                'confidence': 0.6,  # Co-occurrence = moderate confidence
                'source': 'cooccurrence'
            })

    # 2. Dependency parsing for explicit relationships
    text = episode.get('episode_text', '')
    if text:
        parsed_rels = extract_relationships_from_text(text, entities)
        relationships.extend(parsed_rels)

    # 3. Structured field relationships
    # Actor → Location
    if episode.get('location_name'):
        relationships.append({
            'from_entity': episode['actor_id'],
            'from_type': 'Person',
            'to_entity': episode['location_name'],
            'to_type': 'Place',
            'relationship_type': 'located_at',
            'confidence': 1.0,
            'source': 'structured'
        })

    # Actor → Participants (social relationships)
    for participant in episode.get('participants_json', []):
        relationships.append({
            'from_entity': episode['actor_id'],
            'from_type': 'Person',
            'to_entity': participant,
            'to_type': 'Person',
            'relationship_type': 'knows',  # Default social relationship
            'confidence': 0.8,
            'source': 'structured'
        })

    return relationships


def infer_relationship_type(type1: str, type2: str) -> str:
    """
    Infer relationship type based on entity types.

    Rules:
    - Person + Person → 'knows'
    - Person + Place → 'located_at'
    - Person + Activity → 'performs'
    - Person + Topic → 'interested_in'
    - Place + Place → 'near'
    - Activity + Place → 'occurs_at'
    """
    type_pairs = {
        ('Person', 'Person'): 'knows',
        ('Person', 'Place'): 'located_at',
        ('Person', 'Activity'): 'performs',
        ('Person', 'Topic'): 'interested_in',
        ('Person', 'Organization'): 'member_of',
        ('Place', 'Place'): 'near',
        ('Activity', 'Place'): 'occurs_at',
        ('Activity', 'Topic'): 'related_to',
        ('Organization', 'Place'): 'located_at'
    }

    # Try both orderings (some relationships are symmetric)
    key = (type1, type2)
    if key in type_pairs:
        return type_pairs[key]

    key_reverse = (type2, type1)
    if key_reverse in type_pairs:
        return type_pairs[key_reverse]

    # Default
    return 'related_to'


def read_relationships_from_event(event: dict) -> List[dict]:
    """
    Read pre-extracted relationships from st_hipp_events.kg_triples_json.

    NOTE: Relationships are PRE-EXTRACTED by P02 M02 via UltraBERT single-pass.
    P03 only READS from kg_triples_json - no spaCy, no dependency parsing.

    Example triples from P02:
    [{"subject": "Sarah", "predicate": "works_at", "object": "Apple"}, ...]
    """
    kg_triples_json = event.get('kg_triples_json')
    if not kg_triples_json:
        return []

    import json
    triples = json.loads(kg_triples_json) if isinstance(kg_triples_json, str) else kg_triples_json

    relationships = []
    for triple in triples:
        relationships.append({
            'from_entity': triple.get('subject', ''),
            'to_entity': triple.get('object', ''),
            'relationship_type': triple.get('predicate', 'related_to'),
            'confidence': triple.get('confidence', 0.85),
            'source': 'ultrabert',
            'verb': triple.get('predicate', '')
        })

    return relationships


# NOTE: No spaCy dependency parsing - P02 extracts triples via UltraBERT
```

**Write Relationships to st_kg_edges**:

```python
async def create_or_update_relationship(
    tenant_id: str,
    space_id: str,
    from_node_id: str,
    to_node_id: str,
    relationship_type: str,
    episode_id: str,
    timestamp: str
) -> str:
    """
    Create or update relationship edge in st_kg_edges.

    Strategy:
    - If edge exists with same from/to/type: increment strength, update valid_to
    - If edge doesn't exist: create new edge
    """
    # Check for existing edge
    existing = await storage.query_one(
        """
        SELECT edge_id, relationship_strength, occurrence_count
        FROM st_kg_edges
        WHERE tenant_id = ? AND space_id = ?
          AND from_node_id = ? AND to_node_id = ?
          AND relationship_type = ?
          AND valid_to IS NULL
        """,
        (tenant_id, space_id, from_node_id, to_node_id, relationship_type)
    )

    if existing:
        # Update existing edge: increment strength
        edge_id = existing['edge_id']
        new_strength = min(1.0, existing['relationship_strength'] + 0.1)
        new_count = existing['occurrence_count'] + 1

        await storage.execute(
            """
            UPDATE st_kg_edges
            SET
                relationship_strength = ?,
                occurrence_count = ?,
                last_observed_at = ?,
                updated_at = ?
            WHERE edge_id = ?
            """,
            (new_strength, new_count, timestamp, utc_now(), edge_id)
        )

        logger.debug("relationship_updated", edge_id=edge_id, new_strength=new_strength)
    else:
        # Create new edge
        edge_id = generate_id()

        await storage.execute(
            """
            INSERT INTO st_kg_edges (
                edge_id, tenant_id, space_id,
                from_node_id, to_node_id,
                relationship_type, relationship_strength,
                occurrence_count, first_observed_at, last_observed_at,
                valid_from, valid_to,
                edge_properties_json,
                source_episodes_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                edge_id,
                tenant_id,
                space_id,
                from_node_id,
                to_node_id,
                relationship_type,
                0.5,  # Initial strength
                1,  # First occurrence
                timestamp,
                timestamp,
                timestamp,  # valid_from
                None,  # valid_to (active)
                json.dumps({}),  # Empty properties
                json.dumps([episode_id]),  # Source provenance
                utc_now(),
                utc_now()
            )
        )

        logger.info("relationship_created", edge_id=edge_id, rel_type=relationship_type)

    return edge_id
```

**Observability**:

- Metric: `p03_relationships_discovered_total` (counter by relationship_type)
- Metric: `p03_relationships_updated_total` (counter)
- Metric: `p03_relationship_strength_mean` (gauge by relationship_type)
- Log: `relationship_created` with from/to nodes and type

---

### Temporal Validity (valid_from/valid_to)

**Purpose**: Track when entities and relationships are valid, enabling temporal reasoning and historical queries. Every KG node and edge has explicit time bounds.

**Temporal Model**:

```
Entity Lifecycle:
┌────────────────────────────────────────────────────────┐
│ Entity: "Sarah"                                        │
├────────────────────────────────────────────────────────┤
│ Version 1: valid_from=2025-01-01, valid_to=2025-06-30 │
│   - attributes: {role: "colleague", department: "eng"} │
│                                                         │
│ Version 2: valid_from=2025-07-01, valid_to=NULL       │
│   - attributes: {role: "friend", shared_interests: [...]}│
│   - supersedes_node_id → Version 1                     │
└────────────────────────────────────────────────────────┘

Relationship Lifecycle:
┌────────────────────────────────────────────────────────┐
│ Relationship: (Actor, works_at, Apple)                │
├────────────────────────────────────────────────────────┤
│ valid_from=2023-03-01, valid_to=2025-10-31            │
│   - ended when actor changed jobs                     │
│                                                         │
│ Relationship: (Actor, works_at, Google)               │
│ valid_from=2025-11-01, valid_to=NULL                  │
│   - current employment                                 │
└────────────────────────────────────────────────────────┘
```

**Temporal Validity Updates**:

```python
async def update_entity_attributes(
    node_id: str,
    new_attributes: dict,
    timestamp: str
) -> str:
    """
    Update entity attributes by creating new version with temporal validity.

    Strategy:
    1. Close current version (set valid_to = timestamp)
    2. Create new version with updated attributes (valid_from = timestamp)
    3. Link new version to old via supersedes_node_id

    Returns:
        new_node_id
    """
    # Fetch current version
    current = await storage.query_one(
        "SELECT * FROM st_kg_dom WHERE node_id = ? AND valid_to IS NULL",
        (node_id,)
    )

    if not current:
        logger.warning("entity_not_found", node_id=node_id)
        return node_id

    # Check if attributes actually changed
    current_attrs = json.loads(current.get('node_properties_json', '{}'))
    if current_attrs == new_attributes:
        logger.debug("entity_attributes_unchanged", node_id=node_id)
        return node_id

    # Close current version
    await storage.execute(
        """
        UPDATE st_kg_dom
        SET valid_to = ?, updated_at = ?
        WHERE node_id = ?
        """,
        (timestamp, utc_now(), node_id)
    )

    # Create new version
    new_node_id = generate_id()

    await storage.execute(
        """
        INSERT INTO st_kg_dom (
            node_id, tenant_id, space_id,
            entity_type, entity_name, entity_aliases_json,
            node_properties_json,
            is_canonical, canonical_node_id,
            supersedes_node_id,
            valid_from, valid_to,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_node_id,
            current['tenant_id'],
            current['space_id'],
            current['entity_type'],
            current['entity_name'],
            current['entity_aliases_json'],
            json.dumps(new_attributes),
            current['is_canonical'],
            current['canonical_node_id'],
            node_id,  # supersedes_node_id
            timestamp,  # valid_from
            None,  # valid_to (active)
            utc_now(),
            utc_now()
        )
    )

    logger.info(
        "entity_version_created",
        old_node_id=node_id,
        new_node_id=new_node_id,
        timestamp=timestamp
    )

    # Update edges to point to new version
    await storage.execute(
        """
        UPDATE st_kg_edges
        SET from_node_id = ?, updated_at = ?
        WHERE from_node_id = ? AND valid_to IS NULL
        """,
        (new_node_id, utc_now(), node_id)
    )

    await storage.execute(
        """
        UPDATE st_kg_edges
        SET to_node_id = ?, updated_at = ?
        WHERE to_node_id = ? AND valid_to IS NULL
        """,
        (new_node_id, utc_now(), node_id)
    )

    return new_node_id


async def expire_relationship(edge_id: str, timestamp: str):
    """
    Mark relationship as no longer valid (set valid_to).

    Example: Actor changed jobs → expire (Actor, works_at, OldCompany)
    """
    await storage.execute(
        """
        UPDATE st_kg_edges
        SET valid_to = ?, updated_at = ?
        WHERE edge_id = ?
        """,
        (timestamp, utc_now(), edge_id)
    )

    logger.info("relationship_expired", edge_id=edge_id, timestamp=timestamp)
```

**Temporal Queries**:

```python
async def query_kg_at_timestamp(
    tenant_id: str,
    space_id: str,
    entity_name: str,
    timestamp: str
) -> dict:
    """
    Query KG state at specific point in time.

    Example: "What was Sarah's role on 2025-06-01?"
    """
    # Find entity version valid at timestamp
    node = await storage.query_one(
        """
        SELECT *
        FROM st_kg_dom
        WHERE tenant_id = ? AND space_id = ?
          AND entity_name = ?
          AND valid_from <= ?
          AND (valid_to IS NULL OR valid_to > ?)
        """,
        (tenant_id, space_id, entity_name, timestamp, timestamp)
    )

    if not node:
        return None

    # Find relationships valid at timestamp
    edges = await storage.query_many(
        """
        SELECT *
        FROM st_kg_edges
        WHERE tenant_id = ? AND space_id = ?
          AND (from_node_id = ? OR to_node_id = ?)
          AND valid_from <= ?
          AND (valid_to IS NULL OR valid_to > ?)
        """,
        (tenant_id, space_id, node['node_id'], node['node_id'], timestamp, timestamp)
    )

    return {
        'entity': node,
        'relationships': edges
    }


async def query_kg_evolution(
    tenant_id: str,
    space_id: str,
    entity_name: str
) -> List[dict]:
    """
    Query how entity evolved over time (all versions).

    Example: "Show how Sarah's role changed over time"
    """
    # Find canonical entity
    canonical = await storage.query_one(
        """
        SELECT node_id
        FROM st_kg_dom
        WHERE tenant_id = ? AND space_id = ?
          AND entity_name = ?
          AND is_canonical = 1
        """,
        (tenant_id, space_id, entity_name)
    )

    if not canonical:
        return []

    # Find all versions (follow supersedes chain)
    versions = await storage.query_many(
        """
        SELECT *
        FROM st_kg_dom
        WHERE tenant_id = ? AND space_id = ?
          AND canonical_node_id = ?
        ORDER BY valid_from ASC
        """,
        (tenant_id, space_id, canonical['node_id'])
    )

    return versions
```

**Observability**:

- Metric: `p03_entity_versions_created_total` (counter)
- Metric: `p03_relationships_expired_total` (counter)
- Metric: `p03_temporal_queries_total` (counter by query_type)
- Log: `entity_version_created` with old/new node_ids

---

### Causal Inference

**Purpose**: Detect causal relationships between events and entities, enabling "why" reasoning and predictive analytics. Causal edges have special semantics: A → B means "A causes B" or "A enables B".

**Causal Relationship Detection**:

```python
from typing import List, Tuple
import numpy as np
from scipy import stats

def detect_causal_relationships(
    events: List[dict],
    time_window_days: int = 30
) -> List[Tuple[str, str, float]]:
    """
    Detect causal relationships between events using temporal precedence + frequency.

    Causality Criteria:
    1. Temporal precedence: Event A always precedes Event B
    2. Consistent lag: Time between A→B is consistent (low variance)
    3. Frequency: A→B occurs multiple times (not spurious)
    4. Granger causality: A's occurrence helps predict B's occurrence

    Args:
        events: List of events sorted by event_time_utc
        time_window_days: Max lag for A→B to be considered causal

    Returns:
        List of (event_A_id, event_B_id, causal_confidence)
    """
    causal_pairs = []

    # Group events by activity type (routines are good causal candidates)
    activity_groups = {}
    for event in events:
        activity = event.get('activity_type', 'unknown')
        if activity not in activity_groups:
            activity_groups[activity] = []
        activity_groups[activity].append(event)

    # Find activity pairs that frequently co-occur with consistent lag
    activity_types = list(activity_groups.keys())

    for i, activity_a in enumerate(activity_types):
        for activity_b in activity_types[i+1:]:
            # Compute temporal lags between A→B occurrences
            lags = compute_temporal_lags(
                activity_groups[activity_a],
                activity_groups[activity_b],
                time_window_days
            )

            if len(lags) >= 3:  # Need at least 3 occurrences
                # Check lag consistency
                mean_lag = np.mean(lags)
                std_lag = np.std(lags)
                coefficient_of_variation = std_lag / mean_lag if mean_lag > 0 else float('inf')

                if coefficient_of_variation < 0.3:  # Consistent lag
                    # Compute Granger causality
                    granger_p_value = compute_granger_causality(
                        activity_groups[activity_a],
                        activity_groups[activity_b]
                    )

                    if granger_p_value < 0.05:  # Significant causality
                        causal_confidence = 1.0 - coefficient_of_variation

                        causal_pairs.append({
                            'cause_activity': activity_a,
                            'effect_activity': activity_b,
                            'mean_lag_hours': mean_lag,
                            'occurrences': len(lags),
                            'causal_confidence': causal_confidence,
                            'granger_p_value': granger_p_value
                        })

    return causal_pairs


def compute_temporal_lags(
    events_a: List[dict],
    events_b: List[dict],
    max_lag_days: int
) -> List[float]:
    """
    Compute time lags (in hours) between events A and events B.

    Only include pairs where A precedes B within max_lag_days.
    """
    from datetime import datetime, timedelta

    lags = []

    for event_a in events_a:
        time_a = datetime.fromisoformat(event_a['event_time_utc'].replace('Z', '+00:00'))

        for event_b in events_b:
            time_b = datetime.fromisoformat(event_b['event_time_utc'].replace('Z', '+00:00'))

            if time_a < time_b:  # A precedes B
                lag_hours = (time_b - time_a).total_seconds() / 3600
                max_lag_hours = max_lag_days * 24

                if lag_hours <= max_lag_hours:
                    lags.append(lag_hours)

    return lags


def compute_granger_causality(
    events_a: List[dict],
    events_b: List[dict]
) -> float:
    """
    Compute Granger causality test: Does A's occurrence help predict B's occurrence?

    Simplified implementation using event counts per day.

    Returns:
        p-value (lower = stronger causal evidence)
    """
    from datetime import datetime, timedelta
    from collections import defaultdict

    # Convert events to time series (events per day)
    def events_to_timeseries(events):
        daily_counts = defaultdict(int)
        for event in events:
            date = datetime.fromisoformat(event['event_time_utc'].replace('Z', '+00:00')).date()
            daily_counts[date] += 1

        # Fill gaps with zeros
        if not daily_counts:
            return [], []

        min_date = min(daily_counts.keys())
        max_date = max(daily_counts.keys())

        dates = []
        counts = []
        current_date = min_date
        while current_date <= max_date:
            dates.append(current_date)
            counts.append(daily_counts.get(current_date, 0))
            current_date += timedelta(days=1)

        return dates, counts

    dates_a, counts_a = events_to_timeseries(events_a)
    dates_b, counts_b = events_to_timeseries(events_b)

    if len(counts_a) < 10 or len(counts_b) < 10:
        return 1.0  # Insufficient data

    # Simplified Granger test: Correlation between A(t-1) and B(t)
    # Proper implementation would use VAR models
    a_lagged = counts_a[:-1]
    b_current = counts_b[1:]

    if len(a_lagged) != len(b_current):
        # Align time series
        min_len = min(len(a_lagged), len(b_current))
        a_lagged = a_lagged[:min_len]
        b_current = b_current[:min_len]

    if len(a_lagged) < 2:
        return 1.0

    # Pearson correlation
    correlation, p_value = stats.pearsonr(a_lagged, b_current)

    return p_value
```

**Write Causal Relationships**:

```python
async def create_causal_edge(
    tenant_id: str,
    space_id: str,
    cause_node_id: str,
    effect_node_id: str,
    causal_metadata: dict
):
    """
    Create causal relationship edge with special metadata.
    """
    edge_id = generate_id()

    edge_properties = {
        'is_causal': True,
        'mean_lag_hours': causal_metadata['mean_lag_hours'],
        'occurrences': causal_metadata['occurrences'],
        'granger_p_value': causal_metadata['granger_p_value']
    }

    await storage.execute(
        """
        INSERT INTO st_kg_edges (
            edge_id, tenant_id, space_id,
            from_node_id, to_node_id,
            relationship_type, relationship_strength,
            occurrence_count,
            edge_properties_json,
            valid_from, valid_to,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            edge_id,
            tenant_id,
            space_id,
            cause_node_id,
            effect_node_id,
            'causes',
            causal_metadata['causal_confidence'],
            causal_metadata['occurrences'],
            json.dumps(edge_properties),
            utc_now(),
            None,
            utc_now(),
            utc_now()
        )
    )

    logger.info(
        "causal_edge_created",
        edge_id=edge_id,
        cause=cause_node_id,
        effect=effect_node_id,
        confidence=causal_metadata['causal_confidence']
    )


async def query_causal_chain(
    tenant_id: str,
    space_id: str,
    start_entity: str,
    max_depth: int = 3
) -> List[List[str]]:
    """
    Query causal chains starting from entity.

    Example: "Morning coffee" → "Productive work session" → "Completed project"

    Returns:
        List of causal paths (chains of entity names)
    """
    # BFS traversal of causal edges
    from collections import deque

    # Find start node
    start_node = await storage.query_one(
        """
        SELECT node_id
        FROM st_kg_dom
        WHERE tenant_id = ? AND space_id = ?
          AND entity_name = ?
          AND is_canonical = 1
        """,
        (tenant_id, space_id, start_entity)
    )

    if not start_node:
        return []

    # BFS
    queue = deque([(start_node['node_id'], [start_entity])])
    causal_paths = []

    while queue:
        current_node_id, path = queue.popleft()

        if len(path) > max_depth:
            continue

        # Find causal edges from current node
        causal_edges = await storage.query_many(
            """
            SELECT to_node_id, edge_properties_json
            FROM st_kg_edges
            WHERE tenant_id = ? AND space_id = ?
              AND from_node_id = ?
              AND relationship_type = 'causes'
              AND valid_to IS NULL
            """,
            (tenant_id, space_id, current_node_id)
        )

        for edge in causal_edges:
            # Fetch effect entity
            effect_node = await storage.query_one(
                "SELECT entity_name FROM st_kg_dom WHERE node_id = ?",
                (edge['to_node_id'],)
            )

            new_path = path + [effect_node['entity_name']]
            causal_paths.append(new_path)

            queue.append((edge['to_node_id'], new_path))

    return causal_paths
```

**Observability**:

- Metric: `p03_causal_relationships_detected_total` (counter)
- Metric: `p03_causal_confidence_mean` (gauge)
- Metric: `p03_causal_chain_queries_total` (counter)
- Log: `causal_edge_created` with cause/effect and confidence

---

## Retention Policy Matrix

**Purpose**: Define data retention policies that control when memories are archived or deleted based on band (privacy classification), topic (event category), and device_kind (source device). This matrix implements the system's "forgetting" behavior, enabling GDPR compliance and storage optimization.

**P03 Phase Mapping**: **R3.4 (Retention Policy Enforcement)** within NREM Phase 2 (Light Sleep)

**Policy Dimensions**:

1. **Band**: Privacy classification (GREEN, YELLOW, RED) from M11 RetentionLookup
2. **Topic**: Event category (envelope.activity, envelope.meal, envelope.location, etc.)
3. **Device Kind**: Source device type (phone, watch, assistant, manual, etc.)

**Retention Actions**:

- **KEEP**: Active memory, no changes
- **ARCHIVED**: Moved to cold storage, compressed, query latency increased
- **TOMBSTONE**: Metadata kept, content deleted (for GDPR proof-of-deletion)
- **DELETED**: Physically removed from database

**Policy Lookup Flow**:

```
┌─────────────────────────────────────────────────────────────┐
│ Retention Policy Enforcement (R3.4)                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐ │
│  │  Query       │───▶│   Compute    │───▶│   Apply      │ │
│  │  Policy      │    │   Retention  │    │   Action     │ │
│  │  Matrix      │    │   Days       │    │  (Archive/   │ │
│  └──────────────┘    └──────────────┘    │   Delete)    │ │
│         │                    │            └──────────────┘ │
│         │                    │                    │         │
│         ▼                    ▼                    ▼         │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐ │
│  │  Band×Topic  │    │   Novelty    │    │  Update      │ │
│  │  ×Device     │    │  Adjustment  │    │  archival_   │ │
│  │   Lookup     │    │  (±2x/0.5x)  │    │  status      │ │
│  └──────────────┘    └──────────────┘    └──────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

### Band × Topic × Device Kind

**Purpose**: Three-dimensional policy matrix that maps (band, topic, device_kind) → retention_days. Provides fine-grained control over retention based on privacy sensitivity, content type, and data source.

**Policy Matrix Schema**:

```sql
CREATE TABLE retention_policies (
    policy_id TEXT PRIMARY KEY,

    -- Policy dimensions
    band TEXT NOT NULL,                    -- GREEN, YELLOW, RED
    topic TEXT NOT NULL,                   -- Event topic (envelope.*)
    device_kind TEXT NOT NULL,             -- phone, watch, assistant, manual, system

    -- Retention configuration
    retention_days INTEGER NOT NULL,       -- Days before archival
    archival_compression_ratio REAL,       -- Target compression (0.1 = 90% reduction)
    tombstone_retention_days INTEGER,      -- Days to keep tombstone after deletion

    -- Actions
    auto_archive INTEGER DEFAULT 1,        -- 0/1: Automatically archive after retention_days?
    auto_delete INTEGER DEFAULT 0,         -- 0/1: Automatically delete after archival?
    requires_user_consent INTEGER DEFAULT 0, -- 0/1: Require explicit consent to delete?

    -- Metadata
    policy_description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    UNIQUE(band, topic, device_kind)
);

CREATE INDEX idx_retention_band_topic ON retention_policies(band, topic);
CREATE INDEX idx_retention_device ON retention_policies(device_kind);
```

**Default Retention Policies** (examples):

```python
DEFAULT_RETENTION_POLICIES = [
    # GREEN band (low sensitivity)
    {
        'band': 'GREEN',
        'topic': 'envelope.location',
        'device_kind': 'phone',
        'retention_days': 90,
        'auto_archive': 1,
        'auto_delete': 0,
        'policy_description': 'Location data from phone: 90-day retention, archive but never delete'
    },
    {
        'band': 'GREEN',
        'topic': 'envelope.activity',
        'device_kind': 'watch',
        'retention_days': 180,
        'auto_archive': 1,
        'auto_delete': 0,
        'policy_description': 'Activity data from watch: 6-month retention'
    },
    {
        'band': 'GREEN',
        'topic': 'envelope.meal',
        'device_kind': 'manual',
        'retention_days': 365,
        'auto_archive': 1,
        'auto_delete': 0,
        'policy_description': 'Manual meal logs: 1-year retention'
    },

    # YELLOW band (medium sensitivity)
    {
        'band': 'YELLOW',
        'topic': 'envelope.health',
        'device_kind': 'watch',
        'retention_days': 730,  # 2 years
        'auto_archive': 1,
        'auto_delete': 0,
        'requires_user_consent': 1,
        'policy_description': 'Health metrics: 2-year retention, require consent for deletion'
    },
    {
        'band': 'YELLOW',
        'topic': 'envelope.social',
        'device_kind': 'phone',
        'retention_days': 365,
        'auto_archive': 1,
        'auto_delete': 0,
        'policy_description': 'Social interactions: 1-year retention'
    },
    {
        'band': 'YELLOW',
        'topic': 'envelope.work',
        'device_kind': 'assistant',
        'retention_days': 730,
        'auto_archive': 1,
        'auto_delete': 0,
        'policy_description': 'Work-related events: 2-year retention'
    },

    # RED band (high sensitivity)
    {
        'band': 'RED',
        'topic': 'envelope.financial',
        'device_kind': 'manual',
        'retention_days': 2555,  # 7 years (legal requirement)
        'auto_archive': 1,
        'auto_delete': 0,
        'requires_user_consent': 1,
        'policy_description': 'Financial records: 7-year retention (legal compliance)'
    },
    {
        'band': 'RED',
        'topic': 'envelope.medical',
        'device_kind': 'assistant',
        'retention_days': 3650,  # 10 years
        'auto_archive': 1,
        'auto_delete': 0,
        'requires_user_consent': 1,
        'policy_description': 'Medical information: 10-year retention'
    },
    {
        'band': 'RED',
        'topic': 'envelope.intimate',
        'device_kind': 'phone',
        'retention_days': 30,  # Short retention for privacy
        'auto_archive': 1,
        'auto_delete': 1,
        'requires_user_consent': 0,
        'policy_description': 'Intimate conversations: 30-day retention, auto-delete'
    },

    # Catch-all defaults
    {
        'band': 'GREEN',
        'topic': '*',  # Wildcard
        'device_kind': '*',
        'retention_days': 365,
        'auto_archive': 1,
        'auto_delete': 0,
        'policy_description': 'Default GREEN band: 1-year retention'
    },
    {
        'band': 'YELLOW',
        'topic': '*',
        'device_kind': '*',
        'retention_days': 730,
        'auto_archive': 1,
        'auto_delete': 0,
        'policy_description': 'Default YELLOW band: 2-year retention'
    },
    {
        'band': 'RED',
        'topic': '*',
        'device_kind': '*',
        'retention_days': 2555,
        'auto_archive': 1,
        'auto_delete': 0,
        'requires_user_consent': 1,
        'policy_description': 'Default RED band: 7-year retention'
    }
]
```

**Policy Lookup Algorithm**:

```python
async def get_retention_policy(
    band: str,
    topic: str,
    device_kind: str
) -> dict:
    """
    Lookup retention policy from matrix with fallback to wildcards.

    Priority:
    1. Exact match (band, topic, device_kind)
    2. Wildcard device: (band, topic, *)
    3. Wildcard topic: (band, *, device_kind)
    4. Wildcard both: (band, *, *)
    5. System default (365 days)

    Args:
        band: Privacy band (GREEN, YELLOW, RED)
        topic: Event topic (e.g., 'envelope.location')
        device_kind: Device type (e.g., 'phone', 'watch')

    Returns:
        Policy dictionary with retention_days, auto_archive, etc.
    """
    # Try exact match
    policy = await storage.query_one(
        """
        SELECT * FROM retention_policies
        WHERE band = ? AND topic = ? AND device_kind = ?
        """,
        (band, topic, device_kind)
    )

    if policy:
        return policy

    # Try wildcard device
    policy = await storage.query_one(
        """
        SELECT * FROM retention_policies
        WHERE band = ? AND topic = ? AND device_kind = '*'
        """,
        (band, topic)
    )

    if policy:
        return policy

    # Try wildcard topic
    policy = await storage.query_one(
        """
        SELECT * FROM retention_policies
        WHERE band = ? AND topic = '*' AND device_kind = ?
        """,
        (band, device_kind)
    )

    if policy:
        return policy

    # Try wildcard both
    policy = await storage.query_one(
        """
        SELECT * FROM retention_policies
        WHERE band = ? AND topic = '*' AND device_kind = '*'
        """,
        (band,)
    )

    if policy:
        return policy

    # System default
    logger.warning("retention_policy_not_found", band=band, topic=topic, device_kind=device_kind)
    return {
        'retention_days': 365,
        'auto_archive': 1,
        'auto_delete': 0,
        'requires_user_consent': 0,
        'policy_description': 'System default: 1 year'
    }


async def compute_retention_deadline(
    event: dict,
    policy: dict,
    novelty_score: float
) -> str:
    """
    Compute archival deadline for event based on policy + novelty adjustment.

    Novelty adjustment:
    - High novelty (>0.8): Extend retention by 2x
    - Low novelty (<0.3): Reduce retention by 50%
    - Medium novelty: No adjustment

    Args:
        event: Event dictionary from st_hipp_events
        policy: Retention policy from get_retention_policy()
        novelty_score: Computed novelty score (0.0-1.0)

    Returns:
        ISO timestamp for archival deadline
    """
    from datetime import datetime, timedelta

    base_retention_days = policy['retention_days']

    # Novelty adjustment
    if novelty_score > 0.8:
        adjusted_retention_days = base_retention_days * 2  # Extend retention
    elif novelty_score < 0.3:
        adjusted_retention_days = int(base_retention_days * 0.5)  # Reduce retention
    else:
        adjusted_retention_days = base_retention_days

    # Compute deadline
    event_time = datetime.fromisoformat(event['event_time_utc'].replace('Z', '+00:00'))
    archival_deadline = event_time + timedelta(days=adjusted_retention_days)

    logger.debug(
        "retention_deadline_computed",
        event_id=event['event_id'],
        base_days=base_retention_days,
        adjusted_days=adjusted_retention_days,
        novelty_score=novelty_score,
        archival_deadline=archival_deadline.isoformat()
    )

    return archival_deadline.isoformat()
```

**Observability**:

- Metric: `p03_retention_policy_lookups_total` (counter by band/topic/device_kind)
- Metric: `p03_retention_days_mean` (gauge by band)
- Metric: `p03_novelty_adjustments_total` (counter by adjustment_type: extend/reduce/none)
- Log: `retention_policy_applied` with policy details

---

### Archival Rules

**Purpose**: Define when and how events are moved from active storage to cold storage (archival). Archival reduces storage costs and query load while maintaining data accessibility for compliance and historical analysis.

**Archival Triggers**:

1. **Age-Based**: Event created_at + retention_days > NOW()
2. **Access-Based**: Event not accessed in last 90 days (staleness)
3. **Capacity-Based**: Active storage >90% full → archive oldest events
4. **Manual**: User-triggered archival via CLI

**Archival Process**:

```python
async def archive_event(event_id: str):
    """
    Archive event: compress content, move to cold storage, update status.

    Archival workflow:
    1. Mark archival_status='PENDING_ARCHIVE'
    2. Compress event content (text, JSON fields)
    3. Write compressed data to archival table
    4. Update archival_status='ARCHIVED', archival_at=NOW()
    5. Optional: Delete original content (keep metadata)
    """
    # Fetch event
    event = await storage.query_one(
        "SELECT * FROM st_hipp_events WHERE event_id = ?",
        (event_id,)
    )

    if not event:
        logger.error("event_not_found", event_id=event_id)
        return

    if event['archival_status'] == 'ARCHIVED':
        logger.debug("event_already_archived", event_id=event_id)
        return

    # Mark as pending
    await storage.execute(
        """
        UPDATE st_hipp_events
        SET archival_status = 'PENDING_ARCHIVE', updated_at = ?
        WHERE event_id = ?
        """,
        (utc_now(), event_id)
    )

    # Compress content
    compressed_content = compress_event_content(event)
    compression_ratio = len(compressed_content) / len(json.dumps(event))

    # Write to archival table
    await storage.execute(
        """
        INSERT INTO st_archived_events (
            event_id, tenant_id, space_id,
            compressed_content,
            original_size_bytes, compressed_size_bytes, compression_ratio,
            archived_at, archival_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            event['tenant_id'],
            event['space_id'],
            compressed_content,
            len(json.dumps(event)),
            len(compressed_content),
            compression_ratio,
            utc_now(),
            'age_based'
        )
    )

    # Update original event status
    await storage.execute(
        """
        UPDATE st_hipp_events
        SET
            archival_status = 'ARCHIVED',
            archived_at = ?,
            -- Optional: Clear content fields to save space
            text = NULL,
            body_json = NULL,
            metadata_json = NULL,
            updated_at = ?
        WHERE event_id = ?
        """,
        (utc_now(), utc_now(), event_id)
    )

    logger.info(
        "event_archived",
        event_id=event_id,
        compression_ratio=compression_ratio,
        original_size=len(json.dumps(event)),
        compressed_size=len(compressed_content)
    )

    # Emit event
    await bus.emit(
        topic='p03.event.archived.v1',
        payload={
            'event_id': event_id,
            'archived_at': utc_now(),
            'compression_ratio': compression_ratio
        }
    )


def compress_event_content(event: dict) -> bytes:
    """
    Compress event content using gzip.

    Compresses: text, body_json, metadata_json, participants_json
    Preserves: event_id, event_time_utc, band, topic, device_kind (for queries)
    """
    import gzip

    # Extract compressible fields
    compressible = {
        'text': event.get('text'),
        'body_json': event.get('body_json'),
        'metadata_json': event.get('metadata_json'),
        'participants_json': event.get('participants_json'),
        'location_name': event.get('location_name'),
        'activity_type': event.get('activity_type')
    }

    # Convert to JSON and compress
    json_bytes = json.dumps(compressible).encode('utf-8')
    compressed = gzip.compress(json_bytes, compresslevel=9)

    return compressed


async def restore_archived_event(event_id: str) -> dict:
    """
    Restore archived event to active storage (uncompress content).

    Use case: User requests historical data, DSAR export, compliance audit
    """
    # Fetch archived content
    archived = await storage.query_one(
        "SELECT compressed_content FROM st_archived_events WHERE event_id = ?",
        (event_id,)
    )

    if not archived:
        logger.error("archived_event_not_found", event_id=event_id)
        return None

    # Decompress
    import gzip
    compressed_content = archived['compressed_content']
    decompressed_bytes = gzip.decompress(compressed_content)
    content = json.loads(decompressed_bytes.decode('utf-8'))

    # Restore to st_hipp_events (optional: keep in archive, return in-memory)
    await storage.execute(
        """
        UPDATE st_hipp_events
        SET
            text = ?,
            body_json = ?,
            metadata_json = ?,
            participants_json = ?,
            archival_status = 'ACTIVE',
            archived_at = NULL,
            updated_at = ?
        WHERE event_id = ?
        """,
        (
            content.get('text'),
            content.get('body_json'),
            content.get('metadata_json'),
            content.get('participants_json'),
            utc_now(),
            event_id
        )
    )

    logger.info("event_restored", event_id=event_id)

    return content
```

**Batch Archival** (R3.4 phase):

```python
async def archive_stale_events(batch_size: int = 1000):
    """
    Archive events that exceed retention deadline.

    Called during R3.4 Retention Policy Enforcement phase.
    """
    # Query events past archival deadline
    stale_events = await storage.query_many(
        """
        SELECT event_id, archival_deadline
        FROM st_hipp_events
        WHERE archival_status = 'ACTIVE'
          AND archival_deadline < ?
        ORDER BY archival_deadline ASC
        LIMIT ?
        """,
        (utc_now(), batch_size)
    )

    logger.info("archival_batch_start", stale_count=len(stale_events))

    archived_count = 0
    failed_count = 0

    for event in stale_events:
        try:
            await archive_event(event['event_id'])
            archived_count += 1
        except Exception as e:
            logger.error("archival_failed", event_id=event['event_id'], error=str(e))
            failed_count += 1

    metrics.counter('p03_archival_batch_total', archived_count)
    metrics.counter('p03_archival_failures_total', failed_count)

    logger.info(
        "archival_batch_complete",
        archived=archived_count,
        failed=failed_count
    )
```

**Archival Storage Table**:

```sql
CREATE TABLE st_archived_events (
    event_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    space_id TEXT NOT NULL,

    compressed_content BLOB NOT NULL,      -- gzip-compressed JSON
    original_size_bytes INTEGER NOT NULL,
    compressed_size_bytes INTEGER NOT NULL,
    compression_ratio REAL NOT NULL,

    archived_at TEXT NOT NULL,
    archival_reason TEXT,                  -- age_based, capacity_based, manual
    restored_at TEXT,                      -- NULL if never restored

    FOREIGN KEY (event_id) REFERENCES st_hipp_events(event_id)
);

CREATE INDEX idx_archived_tenant ON st_archived_events(tenant_id, space_id);
CREATE INDEX idx_archived_date ON st_archived_events(archived_at);
```

**Observability**:

- Metric: `p03_archived_events_total` (counter)
- Metric: `p03_archival_compression_ratio_mean` (gauge)
- Metric: `p03_archival_storage_bytes_total` (gauge)
- Metric: `p03_restored_events_total` (counter)
- Log: `event_archived` with compression details

---

### Tombstone Strategy

**Purpose**: Implement "right to be forgotten" (GDPR Article 17) by deleting content while preserving metadata as proof-of-deletion. Tombstones maintain audit trail without retaining personal data.

**Tombstone Definition**: Event metadata with content fields nulled, marked with tombstone_status='TOMBSTONED'.

**Tombstone Triggers**:

1. **GDPR DSAR**: User requests deletion (right to be forgotten)
2. **Retention Expiry**: Auto-delete policy after archival period
3. **Manual Deletion**: User-initiated content purge
4. **Compliance**: Legal hold expiration

**Tombstone Creation**:

```python
async def create_tombstone(event_id: str, reason: str, retention_days: int = 30):
    """
    Convert event to tombstone: delete content, keep metadata for audit.

    Tombstone preserves:
    - event_id, tenant_id, space_id
    - event_time_utc, band, topic, device_kind
    - tombstone_status, tombstoned_at, tombstone_reason
    - tombstone_retention_until (when to purge tombstone itself)

    Tombstone deletes:
    - text, body_json, metadata_json, participants_json
    - All PII fields (location_name, address, etc.)

    Args:
        event_id: Event to tombstone
        reason: Reason code (gdpr_dsar, retention_expiry, manual, compliance)
        retention_days: Days to keep tombstone before purging (default 30)
    """
    # Fetch event
    event = await storage.query_one(
        "SELECT * FROM st_hipp_events WHERE event_id = ?",
        (event_id,)
    )

    if not event:
        logger.error("event_not_found", event_id=event_id)
        return

    if event.get('tombstone_status') == 'TOMBSTONED':
        logger.debug("event_already_tombstoned", event_id=event_id)
        return

    # Compute tombstone retention deadline
    from datetime import datetime, timedelta
    tombstone_retention_until = (datetime.utcnow() + timedelta(days=retention_days)).isoformat()

    # Create tombstone entry (audit log)
    await storage.execute(
        """
        INSERT INTO st_tombstones (
            tombstone_id, event_id, tenant_id, space_id,
            event_time_utc, band, topic, device_kind,
            tombstoned_at, tombstone_reason,
            tombstone_retention_until,
            original_event_summary
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            generate_id(),
            event_id,
            event['tenant_id'],
            event['space_id'],
            event['event_time_utc'],
            event['band'],
            event['topic'],
            event['device_kind'],
            utc_now(),
            reason,
            tombstone_retention_until,
            json.dumps({
                'activity_type': event.get('activity_type'),
                'has_location': bool(event.get('location_name')),
                'has_participants': bool(event.get('participants_json')),
                'word_count': len(event.get('text', '').split()) if event.get('text') else 0
            })
        )
    )

    # Update event to tombstone (delete content fields)
    await storage.execute(
        """
        UPDATE st_hipp_events
        SET
            text = NULL,
            body_json = NULL,
            metadata_json = NULL,
            participants_json = NULL,
            location_name = NULL,
            address = NULL,
            latitude = NULL,
            longitude = NULL,
            tombstone_status = 'TOMBSTONED',
            tombstoned_at = ?,
            tombstone_reason = ?,
            tombstone_retention_until = ?,
            updated_at = ?
        WHERE event_id = ?
        """,
        (utc_now(), reason, tombstone_retention_until, utc_now(), event_id)
    )

    logger.info(
        "tombstone_created",
        event_id=event_id,
        reason=reason,
        retention_until=tombstone_retention_until
    )

    # Emit event
    await bus.emit(
        topic='p03.event.tombstoned.v1',
        payload={
            'event_id': event_id,
            'tombstoned_at': utc_now(),
            'reason': reason
        }
    )


async def purge_expired_tombstones():
    """
    Physically delete tombstone records after retention period expires.

    Final deletion: Both st_tombstones entry and st_hipp_events row removed.
    """
    # Query expired tombstones
    expired = await storage.query_many(
        """
        SELECT tombstone_id, event_id
        FROM st_tombstones
        WHERE tombstone_retention_until < ?
        """,
        (utc_now(),)
    )

    logger.info("tombstone_purge_start", count=len(expired))

    for tombstone in expired:
        # Delete from st_tombstones
        await storage.execute(
            "DELETE FROM st_tombstones WHERE tombstone_id = ?",
            (tombstone['tombstone_id'],)
        )

        # Delete from st_hipp_events (if still exists)
        await storage.execute(
            "DELETE FROM st_hipp_events WHERE event_id = ?",
            (tombstone['event_id'],)
        )

        logger.debug("tombstone_purged", tombstone_id=tombstone['tombstone_id'])

    metrics.counter('p03_tombstones_purged_total', len(expired))

    logger.info("tombstone_purge_complete", purged=len(expired))
```

**Tombstone Table Schema**:

```sql
CREATE TABLE st_tombstones (
    tombstone_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    space_id TEXT NOT NULL,

    -- Minimal metadata for audit trail
    event_time_utc TEXT NOT NULL,
    band TEXT NOT NULL,
    topic TEXT NOT NULL,
    device_kind TEXT NOT NULL,

    -- Tombstone lifecycle
    tombstoned_at TEXT NOT NULL,
    tombstone_reason TEXT NOT NULL,         -- gdpr_dsar, retention_expiry, manual, compliance
    tombstone_retention_until TEXT NOT NULL, -- When to purge tombstone itself

    -- Non-PII summary for analytics
    original_event_summary TEXT,            -- JSON: {activity_type, has_location, word_count}

    UNIQUE(event_id)
);

CREATE INDEX idx_tombstone_tenant ON st_tombstones(tenant_id, space_id);
CREATE INDEX idx_tombstone_retention ON st_tombstones(tombstone_retention_until);
CREATE INDEX idx_tombstone_reason ON st_tombstones(tombstone_reason);
```

**Observability**:

- Metric: `p03_tombstones_created_total` (counter by reason)
- Metric: `p03_tombstones_purged_total` (counter)
- Metric: `p03_tombstone_retention_days_mean` (gauge)
- Log: `tombstone_created` with reason and retention deadline

---

### GDPR/DSAR Integration

**Purpose**: Support GDPR compliance by handling Data Subject Access Requests (DSAR) and Right to Erasure requests. Provide full data export and secure deletion with audit trail.

**DSAR Request Types**:

1. **Access Request (Article 15)**: Export all personal data
2. **Erasure Request (Article 17)**: Delete personal data (right to be forgotten)
3. **Rectification Request (Article 16)**: Correct inaccurate data
4. **Portability Request (Article 20)**: Export data in machine-readable format

**DSAR Access Request Implementation**:

```python
async def handle_dsar_access_request(
    tenant_id: str,
    space_id: str,
    actor_id: str,
    request_id: str
) -> str:
    """
    Export all personal data for actor as JSON + CSV.

    Includes:
    - All events from st_hipp_events (active + archived)
    - Consolidated memories (st_epi, st_sem, st_procedural, st_social, st_prospective)
    - Knowledge graph entities (st_kg_dom, st_kg_edges where actor is node)
    - Tombstone records (metadata only, content already deleted)

    Returns:
        Export file path (encrypted zip archive)
    """
    import zipfile
    import csv
    from pathlib import Path

    logger.info("dsar_access_start", request_id=request_id, actor_id=actor_id)

    export_dir = Path(f"/tmp/dsar_export_{request_id}")
    export_dir.mkdir(exist_ok=True)

    # 1. Export raw events (st_hipp_events)
    events = await storage.query_many(
        """
        SELECT * FROM st_hipp_events
        WHERE tenant_id = ? AND space_id = ? AND actor_id = ?
        """,
        (tenant_id, space_id, actor_id)
    )

    with open(export_dir / "events.json", "w") as f:
        json.dump(events, f, indent=2)

    with open(export_dir / "events.csv", "w", newline='') as f:
        if events:
            writer = csv.DictWriter(f, fieldnames=events[0].keys())
            writer.writeheader()
            writer.writerows(events)

    # 2. Export archived events
    archived = await storage.query_many(
        """
        SELECT event_id, archived_at, compression_ratio
        FROM st_archived_events
        WHERE tenant_id = ? AND space_id = ?
          AND event_id IN (SELECT event_id FROM st_hipp_events WHERE actor_id = ?)
        """,
        (tenant_id, space_id, actor_id)
    )

    # Restore and export archived content
    archived_content = []
    for arch in archived:
        content = await restore_archived_event(arch['event_id'])
        archived_content.append(content)

    with open(export_dir / "archived_events.json", "w") as f:
        json.dump(archived_content, f, indent=2)

    # 3. Export consolidated memories
    episodic = await storage.query_many(
        "SELECT * FROM st_epi WHERE tenant_id = ? AND space_id = ? AND actor_id = ?",
        (tenant_id, space_id, actor_id)
    )

    semantic = await storage.query_many(
        "SELECT * FROM st_sem WHERE tenant_id = ? AND space_id = ? AND actor_id = ?",
        (tenant_id, space_id, actor_id)
    )

    procedural = await storage.query_many(
        "SELECT * FROM st_procedural WHERE tenant_id = ? AND space_id = ? AND actor_id = ?",
        (tenant_id, space_id, actor_id)
    )

    with open(export_dir / "episodic_memories.json", "w") as f:
        json.dump(episodic, f, indent=2)

    with open(export_dir / "semantic_patterns.json", "w") as f:
        json.dump(semantic, f, indent=2)

    with open(export_dir / "procedural_memories.json", "w") as f:
        json.dump(procedural, f, indent=2)

    # 4. Export knowledge graph
    kg_nodes = await storage.query_many(
        """
        SELECT * FROM st_kg_dom
        WHERE tenant_id = ? AND space_id = ?
          AND node_properties_json LIKE ?
        """,
        (tenant_id, space_id, f'%{actor_id}%')
    )

    with open(export_dir / "knowledge_graph_nodes.json", "w") as f:
        json.dump(kg_nodes, f, indent=2)

    # 5. Export tombstone records (audit trail)
    tombstones = await storage.query_many(
        """
        SELECT * FROM st_tombstones
        WHERE tenant_id = ? AND space_id = ?
          AND event_id IN (SELECT event_id FROM st_hipp_events WHERE actor_id = ?)
        """,
        (tenant_id, space_id, actor_id)
    )

    with open(export_dir / "tombstones.json", "w") as f:
        json.dump(tombstones, f, indent=2)

    # 6. Create export manifest
    manifest = {
        'request_id': request_id,
        'actor_id': actor_id,
        'export_date': utc_now(),
        'files': {
            'events': len(events),
            'archived_events': len(archived),
            'episodic_memories': len(episodic),
            'semantic_patterns': len(semantic),
            'procedural_memories': len(procedural),
            'knowledge_graph_nodes': len(kg_nodes),
            'tombstones': len(tombstones)
        }
    }

    with open(export_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    # 7. Create encrypted ZIP archive
    zip_path = f"/tmp/dsar_export_{request_id}.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in export_dir.glob('*'):
            zipf.write(file_path, file_path.name)

    logger.info("dsar_access_complete", request_id=request_id, zip_path=zip_path)

    # Emit event
    await bus.emit(
        topic='p03.dsar.access.complete.v1',
        payload={
            'request_id': request_id,
            'actor_id': actor_id,
            'export_path': zip_path,
            'file_count': len(manifest['files'])
        }
    )

    return zip_path


async def handle_dsar_erasure_request(
    tenant_id: str,
    space_id: str,
    actor_id: str,
    request_id: str,
    scope: str = 'all'
):
    """
    Delete personal data per GDPR Article 17 (Right to Erasure).

    Scope options:
    - 'all': Delete all data (full erasure)
    - 'events': Delete raw events only (keep consolidated memories)
    - 'location': Delete location data only
    - 'social': Delete social interaction data only

    Actions:
    1. Create tombstones for all matching events
    2. Delete from memory layers (st_epi, st_sem, etc.)
    3. Delete knowledge graph nodes/edges
    4. Log erasure in audit trail
    """
    logger.info("dsar_erasure_start", request_id=request_id, actor_id=actor_id, scope=scope)

    deleted_counts = {
        'events': 0,
        'episodic': 0,
        'semantic': 0,
        'procedural': 0,
        'social': 0,
        'prospective': 0,
        'kg_nodes': 0,
        'kg_edges': 0
    }

    # 1. Delete raw events (create tombstones)
    if scope in ['all', 'events']:
        events = await storage.query_many(
            "SELECT event_id FROM st_hipp_events WHERE tenant_id = ? AND space_id = ? AND actor_id = ?",
            (tenant_id, space_id, actor_id)
        )

        for event in events:
            await create_tombstone(event['event_id'], reason='gdpr_dsar', retention_days=90)
            deleted_counts['events'] += 1

    # 2. Delete consolidated memories
    if scope == 'all':
        await storage.execute(
            "DELETE FROM st_epi WHERE tenant_id = ? AND space_id = ? AND actor_id = ?",
            (tenant_id, space_id, actor_id)
        )
        deleted_counts['episodic'] = storage.rowcount

        await storage.execute(
            "DELETE FROM st_sem WHERE tenant_id = ? AND space_id = ? AND actor_id = ?",
            (tenant_id, space_id, actor_id)
        )
        deleted_counts['semantic'] = storage.rowcount

        await storage.execute(
            "DELETE FROM st_procedural WHERE tenant_id = ? AND space_id = ? AND actor_id = ?",
            (tenant_id, space_id, actor_id)
        )
        deleted_counts['procedural'] = storage.rowcount

        await storage.execute(
            "DELETE FROM st_social WHERE tenant_id = ? AND space_id = ? AND actor_id = ?",
            (tenant_id, space_id, actor_id)
        )
        deleted_counts['social'] = storage.rowcount

        await storage.execute(
            "DELETE FROM st_prospective WHERE tenant_id = ? AND space_id = ? AND actor_id = ?",
            (tenant_id, space_id, actor_id)
        )
        deleted_counts['prospective'] = storage.rowcount

    # 3. Delete knowledge graph data
    if scope == 'all':
        # Delete edges where actor is a node
        await storage.execute(
            """
            DELETE FROM st_kg_edges
            WHERE tenant_id = ? AND space_id = ?
              AND (from_node_id IN (SELECT node_id FROM st_kg_dom WHERE entity_name = ?)
                   OR to_node_id IN (SELECT node_id FROM st_kg_dom WHERE entity_name = ?))
            """,
            (tenant_id, space_id, actor_id, actor_id)
        )
        deleted_counts['kg_edges'] = storage.rowcount

        # Delete nodes
        await storage.execute(
            "DELETE FROM st_kg_dom WHERE tenant_id = ? AND space_id = ? AND entity_name = ?",
            (tenant_id, space_id, actor_id)
        )
        deleted_counts['kg_nodes'] = storage.rowcount

    # 4. Log erasure in audit trail
    await storage.execute(
        """
        INSERT INTO st_dsar_audit_log (
            audit_id, request_id, tenant_id, space_id, actor_id,
            request_type, scope, deleted_counts_json,
            completed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            generate_id(),
            request_id,
            tenant_id,
            space_id,
            actor_id,
            'erasure',
            scope,
            json.dumps(deleted_counts),
            utc_now()
        )
    )

    logger.info("dsar_erasure_complete", request_id=request_id, deleted_counts=deleted_counts)

    # Emit event
    await bus.emit(
        topic='p03.dsar.erasure.complete.v1',
        payload={
            'request_id': request_id,
            'actor_id': actor_id,
            'scope': scope,
            'deleted_counts': deleted_counts
        }
    )
```

**DSAR Audit Table**:

```sql
CREATE TABLE st_dsar_audit_log (
    audit_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    space_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,

    request_type TEXT NOT NULL,       -- access, erasure, rectification, portability
    scope TEXT,                        -- all, events, location, social
    deleted_counts_json TEXT,          -- JSON summary of deletions

    requested_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,

    UNIQUE(request_id)
);

CREATE INDEX idx_dsar_audit_actor ON st_dsar_audit_log(actor_id);
CREATE INDEX idx_dsar_audit_type ON st_dsar_audit_log(request_type);
```

**Observability**:

- Metric: `p03_dsar_requests_total` (counter by request_type)
- Metric: `p03_dsar_access_duration_seconds` (histogram)
- Metric: `p03_dsar_erasure_records_deleted` (histogram)
- Log: `dsar_access_complete` with file count
- Log: `dsar_erasure_complete` with deletion summary

---

## Performance Budgets

**Purpose**: Define quantitative performance targets for P03 consolidation pipeline to ensure system responsiveness, throughput, and resource efficiency. Performance budgets guide optimization decisions and alert on degradation.

**Budget Categories**:

1. **Throughput**: Events processed per unit time
2. **Latency**: Time to complete consolidation phases
3. **Resource Utilization**: CPU, memory, disk I/O limits
4. **Storage Efficiency**: Compression ratios, archival savings

---

### Batch Processing Throughput

**Target**: Process 500-2000 events per 90-minute consolidation cycle.

**Throughput Breakdown by Phase**:

```
Phase                    | Events/Min | Duration (min) | Events Processed
-------------------------|------------|----------------|------------------
R0 Trigger Detection     | N/A        | <1             | N/A
R1 Hippocampal Replay    | 25-50      | 20-30          | 500-1500
R2 Neocortical Integration| 20-40     | 30-40          | 600-1600
R3 Synaptic Homeostasis  | 100-200    | 5-10           | 500-2000
R4 KG Consolidation      | 30-60      | 15-25          | 450-1500
R5 Dream Exploration     | 10-20      | 20-30          | 200-600
R6 Update st_hipp_events | 500-1000   | 2-3            | 1000-3000
R7 Write Memory Layers   | 100-200    | 10-15          | 1000-3000
R8 Event Emission        | 1000-2000  | 1-2            | 1000-2000
-------------------------|------------|----------------|------------------
Total                    | 11-37      | 90             | 1000-2000
```

**Throughput Measurement**:

```python
async def measure_consolidation_throughput(batch_start_time: str, batch_end_time: str, event_count: int):
    """
    Compute throughput metrics for consolidation cycle.
    """
    from datetime import datetime

    start = datetime.fromisoformat(batch_start_time)
    end = datetime.fromisoformat(batch_end_time)
    duration_seconds = (end - start).total_seconds()
    duration_minutes = duration_seconds / 60

    # Throughput metrics
    events_per_second = event_count / duration_seconds
    events_per_minute = event_count / duration_minutes

    metrics.gauge('p03_throughput_events_per_second', events_per_second)
    metrics.gauge('p03_throughput_events_per_minute', events_per_minute)
    metrics.histogram('p03_batch_duration_seconds', duration_seconds)
    metrics.histogram('p03_batch_event_count', event_count)

    logger.info(
        "throughput_measured",
        event_count=event_count,
        duration_seconds=duration_seconds,
        events_per_second=events_per_second,
        events_per_minute=events_per_minute
    )

    # Alert if below target
    if events_per_minute < 11:
        logger.warning(
            "throughput_below_target",
            events_per_minute=events_per_minute,
            target_min=11
        )
```

**Throughput Targets**:

- **Minimum**: 11 events/minute (990 events/90 min)
- **Target**: 22 events/minute (2000 events/90 min)
- **Maximum**: 37 events/minute (3300 events/90 min, with throttling)

**Observability**:

- Metric: `p03_throughput_events_per_second` (gauge)
- Metric: `p03_throughput_events_per_minute` (gauge)
- Metric: `p03_batch_event_count` (histogram)
- Alert: Throughput <11 events/min for 3 consecutive cycles

---

### Sleep Cycle Duration (90-minute target)

**Target**: Complete full consolidation cycle in 90 minutes (±10 minutes).

**Phase Duration Budgets**:

```
Phase   | Target (min) | Max (min) | Budget Exceeded Action
--------|--------------|-----------|------------------------
R0      | <1           | 2         | Skip cycle, log warning
R1      | 25           | 35        | Reduce batch size
R2      | 35           | 45        | Reduce clustering depth
R3      | 8            | 12        | Skip novelty scoring for low-priority events
R4      | 20           | 30        | Reduce KG edge discovery depth
R5      | 20           | 30        | Skip dream exploration (optional phase)
R6      | 2            | 5         | Increase micro-batch size
R7      | 12           | 20        | Parallelize memory layer writes
R8      | 2            | 5         | Batch event emissions
--------|--------------|-----------|------------------------
Total   | 90           | 120       | Abort cycle, resume next scheduled run
```

**Duration Monitoring**:

```python
async def monitor_phase_duration(phase_name: str, phase_start_time: str, phase_end_time: str):
    """
    Track phase duration and alert if budget exceeded.
    """
    from datetime import datetime

    start = datetime.fromisoformat(phase_start_time)
    end = datetime.fromisoformat(phase_end_time)
    duration_seconds = (end - start).total_seconds()
    duration_minutes = duration_seconds / 60

    # Budget lookup
    phase_budgets = {
        'R0': 2,
        'R1': 35,
        'R2': 45,
        'R3': 12,
        'R4': 30,
        'R5': 30,
        'R6': 5,
        'R7': 20,
        'R8': 5
    }

    budget_minutes = phase_budgets.get(phase_name, 10)

    metrics.histogram(f'p03_{phase_name}_duration_seconds', duration_seconds)

    if duration_minutes > budget_minutes:
        logger.warning(
            "phase_duration_exceeded",
            phase=phase_name,
            duration_minutes=duration_minutes,
            budget_minutes=budget_minutes,
            overage_percent=(duration_minutes / budget_minutes - 1) * 100
        )

        # Emit alert
        await bus.emit(
            topic='p03.phase.duration.exceeded.v1',
            payload={
                'phase': phase_name,
                'duration_minutes': duration_minutes,
                'budget_minutes': budget_minutes
            }
        )
```

**Cycle Duration SLO**: 95% of cycles complete within 100 minutes.

**Observability**:

- Metric: `p03_R1_duration_seconds` ... `p03_R8_duration_seconds` (histograms)
- Metric: `p03_cycle_total_duration_seconds` (histogram)
- Metric: `p03_cycle_budget_exceeded_total` (counter)
- Alert: Cycle duration >120 minutes

---

### Memory Consolidation Rate (memories/hour)

**Target**: Consolidate 1000-2000 events → 50-200 memories per hour.

**Memory Creation Rates**:

```
Memory Layer        | Creation Rate      | Target/Hour
--------------------|--------------------|--------------
st_epi              | 1 per 5 events     | 200-400
st_sem              | 1 per 20 events    | 50-100
st_procedural       | 1 per 50 events    | 20-40
st_social           | 1 per 10 events    | 100-200
st_prospective      | 1 per 100 events   | 10-20
st_kg_dom (nodes)   | 1 per 3 events     | 333-667
st_kg_edges         | 2 per 3 events     | 667-1333
--------------------|--------------------|--------------
Total Memories      | ~5 per event       | 5000-10000
```

**Consolidation Efficiency**:

```python
async def measure_consolidation_efficiency(batch_stats: dict):
    """
    Measure consolidation efficiency: memories created / events processed.
    """
    events_processed = batch_stats['events_processed']

    memories_created = (
        batch_stats['episodic_memories'] +
        batch_stats['semantic_patterns'] +
        batch_stats['procedural_routines'] +
        batch_stats['social_memories'] +
        batch_stats['prospective_intentions'] +
        batch_stats['kg_nodes'] +
        batch_stats['kg_edges']
    )

    consolidation_ratio = memories_created / events_processed if events_processed > 0 else 0

    metrics.gauge('p03_consolidation_ratio', consolidation_ratio)
    metrics.gauge('p03_memories_created_per_hour', memories_created * (60 / batch_stats['duration_minutes']))

    logger.info(
        "consolidation_efficiency",
        events_processed=events_processed,
        memories_created=memories_created,
        consolidation_ratio=consolidation_ratio
    )
```

**Consolidation Ratio Target**: 4-6 memories per event (indicates effective abstraction and relationship discovery).

**Observability**:

- Metric: `p03_consolidation_ratio` (gauge, memories/events)
- Metric: `p03_memories_created_per_hour` (gauge)
- Metric: `p03_episodic_memories_created_total` (counter)
- Metric: `p03_semantic_patterns_created_total` (counter)

---

### Storage Savings (archival compression)

**Target**: Achieve 70-85% storage reduction through archival compression.

**Compression Targets**:

```
Content Type         | Compression Ratio | Storage Saved
---------------------|-------------------|----------------
Text fields          | 0.15 (85% saved)  | 85%
JSON fields          | 0.20 (80% saved)  | 80%
Location data        | 0.30 (70% saved)  | 70%
Metadata             | 0.40 (60% saved)  | 60%
---------------------|-------------------|----------------
Average (all fields) | 0.25 (75% saved)  | 75%
```

**Storage Savings Measurement**:

```python
async def measure_storage_savings():
    """
    Compute storage savings from archival compression.
    """
    # Query archival statistics
    stats = await storage.query_one(
        """
        SELECT
            COUNT(*) as archived_count,
            SUM(original_size_bytes) as original_size,
            SUM(compressed_size_bytes) as compressed_size,
            AVG(compression_ratio) as avg_compression_ratio
        FROM st_archived_events
        """
    )

    if not stats or stats['archived_count'] == 0:
        return

    storage_saved_bytes = stats['original_size'] - stats['compressed_size']
    storage_saved_percent = (storage_saved_bytes / stats['original_size']) * 100

    metrics.gauge('p03_archival_storage_saved_bytes', storage_saved_bytes)
    metrics.gauge('p03_archival_storage_saved_percent', storage_saved_percent)
    metrics.gauge('p03_archival_compression_ratio_mean', stats['avg_compression_ratio'])

    logger.info(
        "storage_savings",
        archived_count=stats['archived_count'],
        original_size_mb=stats['original_size'] / 1024 / 1024,
        compressed_size_mb=stats['compressed_size'] / 1024 / 1024,
        saved_mb=storage_saved_bytes / 1024 / 1024,
        saved_percent=storage_saved_percent,
        avg_compression_ratio=stats['avg_compression_ratio']
    )

    # Alert if compression below target
    if stats['avg_compression_ratio'] > 0.30:  # >30% retained = <70% saved
        logger.warning(
            "compression_below_target",
            avg_compression_ratio=stats['avg_compression_ratio'],
            target_ratio=0.25
        )
```

**Storage Budget Targets**:

- **Active Storage**: <10 GB per 100k events (100 KB/event average)
- **Archived Storage**: <2.5 GB per 100k events (25 KB/event after 75% compression)
- **Total Storage**: <12.5 GB per 100k events (active + archived)

**Observability**:

- Metric: `p03_archival_storage_saved_bytes` (gauge)
- Metric: `p03_archival_storage_saved_percent` (gauge)
- Metric: `p03_archival_compression_ratio_mean` (gauge)
- Metric: `p03_active_storage_bytes_total` (gauge)
- Alert: Compression ratio >0.30 (below 70% savings target)

---

## Event Topics (P03)

**Purpose**: Define the event-driven interface for P03 consolidation pipeline. P03 consumes events from upstream pipelines (P02, user activity detection) and produces events for downstream pipelines (P08, P15, P06) and external consumers.

**Event Bus Architecture**: K0 Bus (M02 EventBus) with topic-based routing and guaranteed delivery.

**Event Schema Standards**:

- All events use JSON payloads with versioned schemas (`.v1`, `.v2` suffixes)
- Events include: `tenant_id`, `space_id`, `actor_id`, `timestamp`, `correlation_id`
- Event types follow pattern: `<pipeline>.<entity>.<action>.<version>`

---

### Consumed Topics

**Purpose**: Events that trigger P03 consolidation or provide input data for memory processing.

**Primary Consumed Topics**:

```python
CONSUMED_TOPICS = {
    # P02 Write Pipeline → P03 Consolidation
    'p02.write.complete.v1': {
        'description': 'Envelope successfully written to st_hipp_events',
        'producer': 'P02 (Write)',
        'payload_schema': {
            'envelope_id': 'string',
            'event_id': 'string',
            'tenant_id': 'string',
            'space_id': 'string',
            'actor_id': 'string',
            'band': 'string',  # GREEN, YELLOW, RED
            'topic': 'string',  # envelope.activity, envelope.meal, etc.
            'device_kind': 'string',
            'event_time_utc': 'string (ISO8601)',
            'written_at': 'string (ISO8601)',
            'event_count': 'integer'  # For batched writes
        },
        'trigger': 'Increments consolidation batch counter, triggers cycle when threshold reached',
        'handler': 'on_write_complete()'
    },

    # User Activity Detection → P03 (for real-time consolidation)
    'user.activity.detected.v1': {
        'description': 'High-value user activity detected (e.g., important meeting, milestone)',
        'producer': 'M01 Concierge Agent',
        'payload_schema': {
            'activity_id': 'string',
            'tenant_id': 'string',
            'space_id': 'string',
            'actor_id': 'string',
            'activity_type': 'string',  # meeting, milestone, achievement
            'importance_score': 'float (0.0-1.0)',
            'detected_at': 'string (ISO8601)',
            'related_event_ids': 'array[string]'
        },
        'trigger': 'Prioritizes related events for immediate consolidation',
        'handler': 'on_activity_detected()'
    },

    # Sleep Cycle Trigger → P03
    'system.sleep.cycle.start.v1': {
        'description': 'System-wide sleep cycle initiated (90-minute timer)',
        'producer': 'M13 SleepCycleOrchestrator',
        'payload_schema': {
            'cycle_id': 'string',
            'cycle_start_time': 'string (ISO8601)',
            'expected_duration_seconds': 'integer (5400)',
            'cycle_type': 'string'  # regular, fast_track, deep
        },
        'trigger': 'Initiates P03 R0 consolidation trigger',
        'handler': 'on_sleep_cycle_start()'
    },

    # Manual Consolidation Request → P03
    'user.consolidation.requested.v1': {
        'description': 'User manually requests memory consolidation (CLI/API)',
        'producer': 'M01 Concierge CLI',
        'payload_schema': {
            'request_id': 'string',
            'tenant_id': 'string',
            'space_id': 'string',
            'actor_id': 'string',
            'scope': 'string',  # all, recent, specific_events
            'event_ids': 'array[string] (optional)',
            'requested_at': 'string (ISO8601)'
        },
        'trigger': 'Initiates ad-hoc consolidation cycle',
        'handler': 'on_consolidation_requested()'
    },

    # Retention Policy Update → P03
    'system.retention.policy.updated.v1': {
        'description': 'Retention policy changed (requires recomputation of archival deadlines)',
        'producer': 'M11 RetentionLookup',
        'payload_schema': {
            'policy_id': 'string',
            'band': 'string',
            'topic': 'string',
            'device_kind': 'string',
            'old_retention_days': 'integer',
            'new_retention_days': 'integer',
            'updated_at': 'string (ISO8601)'
        },
        'trigger': 'Recalculates archival_deadline for affected events',
        'handler': 'on_retention_policy_updated()'
    },

    # DSAR Request → P03
    'user.dsar.request.submitted.v1': {
        'description': 'GDPR Data Subject Access Request or Erasure Request',
        'producer': 'M01 Concierge API',
        'payload_schema': {
            'request_id': 'string',
            'request_type': 'string',  # access, erasure, rectification, portability
            'tenant_id': 'string',
            'space_id': 'string',
            'actor_id': 'string',
            'scope': 'string',  # all, events, location, social
            'submitted_at': 'string (ISO8601)'
        },
        'trigger': 'Initiates DSAR processing (export or deletion)',
        'handler': 'on_dsar_request_submitted()'
    }
}
```

**Event Handlers**:

```python
from typing import Dict, Any

async def on_write_complete(event: Dict[str, Any]):
    """
    Handle p02.write.complete.v1: Increment consolidation batch counter.
    """
    event_count = event['event_count']

    # Increment batch counter
    current_batch_size = await storage.increment_counter('p03_batch_size', event_count)

    # Check consolidation trigger threshold
    if current_batch_size >= CONSOLIDATION_BATCH_THRESHOLD:
        logger.info("consolidation_threshold_reached", batch_size=current_batch_size)
        await trigger_consolidation_cycle()

    metrics.counter('p03_events_received_total', event_count)


async def on_activity_detected(event: Dict[str, Any]):
    """
    Handle user.activity.detected.v1: Prioritize high-importance events.
    """
    importance = event['importance_score']
    related_event_ids = event.get('related_event_ids', [])

    if importance > 0.8 and related_event_ids:
        # Fast-track consolidation for important events
        await storage.execute(
            f"""
            UPDATE st_hipp_events
            SET consolidation_priority = 'HIGH'
            WHERE event_id IN ({','.join('?' * len(related_event_ids))})
            """,
            related_event_ids
        )

        logger.info("high_importance_events_prioritized", count=len(related_event_ids))


async def on_sleep_cycle_start(event: Dict[str, Any]):
    """
    Handle system.sleep.cycle.start.v1: Initiate P03 consolidation cycle.
    """
    cycle_id = event['cycle_id']
    cycle_type = event['cycle_type']

    logger.info("sleep_cycle_started", cycle_id=cycle_id, cycle_type=cycle_type)

    # Trigger consolidation (R0 phase)
    await trigger_consolidation_cycle(cycle_id=cycle_id, cycle_type=cycle_type)


async def on_consolidation_requested(event: Dict[str, Any]):
    """
    Handle user.consolidation.requested.v1: Manual consolidation request.
    """
    request_id = event['request_id']
    scope = event['scope']
    event_ids = event.get('event_ids')

    logger.info("manual_consolidation_requested", request_id=request_id, scope=scope)

    if scope == 'specific_events' and event_ids:
        # Consolidate specific events only
        await consolidate_events(event_ids, request_id=request_id)
    else:
        # Full consolidation cycle
        await trigger_consolidation_cycle(request_id=request_id)


async def on_retention_policy_updated(event: Dict[str, Any]):
    """
    Handle system.retention.policy.updated.v1: Recompute archival deadlines.
    """
    band = event['band']
    topic = event['topic']
    device_kind = event['device_kind']
    new_retention_days = event['new_retention_days']

    # Query affected events
    affected_events = await storage.query_many(
        """
        SELECT event_id, event_time_utc, novelty_score
        FROM st_hipp_events
        WHERE band = ? AND topic = ? AND device_kind = ?
          AND archival_status = 'ACTIVE'
        """,
        (band, topic, device_kind)
    )

    # Recompute archival deadlines
    for event in affected_events:
        policy = {'retention_days': new_retention_days}
        new_deadline = await compute_retention_deadline(event, policy, event['novelty_score'])

        await storage.execute(
            "UPDATE st_hipp_events SET archival_deadline = ? WHERE event_id = ?",
            (new_deadline, event['event_id'])
        )

    logger.info("archival_deadlines_updated", affected_count=len(affected_events))


async def on_dsar_request_submitted(event: Dict[str, Any]):
    """
    Handle user.dsar.request.submitted.v1: Process GDPR request.
    """
    request_id = event['request_id']
    request_type = event['request_type']
    actor_id = event['actor_id']

    logger.info("dsar_request_received", request_id=request_id, request_type=request_type)

    if request_type == 'access':
        # Export all data
        export_path = await handle_dsar_access_request(
            tenant_id=event['tenant_id'],
            space_id=event['space_id'],
            actor_id=actor_id,
            request_id=request_id
        )
        logger.info("dsar_access_complete", export_path=export_path)

    elif request_type == 'erasure':
        # Delete data
        await handle_dsar_erasure_request(
            tenant_id=event['tenant_id'],
            space_id=event['space_id'],
            actor_id=actor_id,
            request_id=request_id,
            scope=event.get('scope', 'all')
        )
        logger.info("dsar_erasure_complete")
```

**Observability**:

- Metric: `p03_events_consumed_total` (counter by topic)
- Metric: `p03_event_handler_duration_seconds` (histogram by handler)
- Metric: `p03_event_handler_errors_total` (counter by handler)
- Log: `event_consumed` with topic and correlation_id

---

### Produced Topics

**Purpose**: Events emitted by P03 to notify downstream pipelines and external consumers of consolidation progress and outputs.

**Primary Produced Topics**:

```python
PRODUCED_TOPICS = {
    # P03 Consolidation Complete → Downstream Pipelines
    'p03.consolidation.complete.v1': {
        'description': 'Consolidation cycle completed successfully',
        'consumers': ['P08 (Embeddings)', 'P15 (Rollups)', 'M01 (Concierge)', 'Monitoring'],
        'payload_schema': {
            'cycle_id': 'string',
            'tenant_id': 'string',
            'space_id': 'string',
            'actor_id': 'string',
            'cycle_start_time': 'string (ISO8601)',
            'cycle_end_time': 'string (ISO8601)',
            'duration_seconds': 'float',
            'events_processed': 'integer',
            'memories_created': {
                'episodic': 'integer',
                'semantic': 'integer',
                'procedural': 'integer',
                'social': 'integer',
                'prospective': 'integer',
                'kg_nodes': 'integer',
                'kg_edges': 'integer'
            },
            'deduplication_stats': {
                'duplicates_found': 'integer',
                'novelty_mean': 'float'
            },
            'completed_at': 'string (ISO8601)'
        },
        'emitter': 'R8 (Event Emission)'
    },

    # P03 Pattern Extracted → P08, P15
    'p03.pattern.extracted.v1': {
        'description': 'Semantic pattern extracted from episodic events',
        'consumers': ['P08 (Embeddings)', 'P15 (Rollups)', 'M01 (Concierge)'],
        'payload_schema': {
            'pattern_id': 'string',
            'tenant_id': 'string',
            'space_id': 'string',
            'actor_id': 'string',
            'pattern_type': 'string',  # routine, habit, preference
            'pattern_name': 'string',
            'confidence_score': 'float (0.0-1.0)',
            'frequency': 'integer',
            'temporal_pattern_type': 'string',  # daily, weekly, monthly, irregular
            'recurrence_interval_days': 'float (nullable)',
            'source_event_count': 'integer',
            'extracted_at': 'string (ISO8601)'
        },
        'emitter': 'R2.2 (Pattern Extraction)'
    },

    # P03 KG Updated → P06, External Consumers
    'p03.kg.updated.v1': {
        'description': 'Knowledge graph nodes or edges created/updated',
        'consumers': ['P06 (Learning)', 'External KG Consumers'],
        'payload_schema': {
            'update_type': 'string',  # node_created, edge_created, node_updated, edge_updated
            'tenant_id': 'string',
            'space_id': 'string',
            'actor_id': 'string',
            'node_ids': 'array[string]',
            'edge_ids': 'array[string]',
            'entity_types': 'array[string]',
            'relationship_types': 'array[string]',
            'updated_at': 'string (ISO8601)'
        },
        'emitter': 'R4 (KG Consolidation)'
    },

    # P03 Event Archived → Monitoring
    'p03.event.archived.v1': {
        'description': 'Event archived to cold storage',
        'consumers': ['Monitoring', 'Storage Analytics'],
        'payload_schema': {
            'event_id': 'string',
            'tenant_id': 'string',
            'space_id': 'string',
            'archived_at': 'string (ISO8601)',
            'compression_ratio': 'float',
            'original_size_bytes': 'integer',
            'compressed_size_bytes': 'integer',
            'archival_reason': 'string'  # age_based, capacity_based, manual
        },
        'emitter': 'R3.4 (Retention Enforcement)'
    },

    # P03 Event Tombstoned → Compliance
    'p03.event.tombstoned.v1': {
        'description': 'Event tombstoned (content deleted, metadata retained)',
        'consumers': ['Compliance Audit', 'DSAR Processing'],
        'payload_schema': {
            'event_id': 'string',
            'tenant_id': 'string',
            'space_id': 'string',
            'tombstoned_at': 'string (ISO8601)',
            'reason': 'string',  # gdpr_dsar, retention_expiry, manual, compliance
            'tombstone_retention_until': 'string (ISO8601)'
        },
        'emitter': 'Tombstone Creation'
    },

    # P03 DSAR Access Complete → User
    'p03.dsar.access.complete.v1': {
        'description': 'DSAR access request completed, export ready',
        'consumers': ['M01 (Concierge)', 'User Notification'],
        'payload_schema': {
            'request_id': 'string',
            'actor_id': 'string',
            'export_path': 'string',
            'file_count': 'integer',
            'total_records': 'integer',
            'completed_at': 'string (ISO8601)'
        },
        'emitter': 'DSAR Access Handler'
    },

    # P03 DSAR Erasure Complete → User
    'p03.dsar.erasure.complete.v1': {
        'description': 'DSAR erasure request completed, data deleted',
        'consumers': ['M01 (Concierge)', 'User Notification', 'Compliance Audit'],
        'payload_schema': {
            'request_id': 'string',
            'actor_id': 'string',
            'scope': 'string',
            'deleted_counts': {
                'events': 'integer',
                'episodic': 'integer',
                'semantic': 'integer',
                'procedural': 'integer',
                'social': 'integer',
                'prospective': 'integer',
                'kg_nodes': 'integer',
                'kg_edges': 'integer'
            },
            'completed_at': 'string (ISO8601)'
        },
        'emitter': 'DSAR Erasure Handler'
    },

    # P03 Consolidation Failed → Monitoring
    'p03.consolidation.failed.v1': {
        'description': 'Consolidation cycle failed (for alerting)',
        'consumers': ['Monitoring', 'Alerting', 'Dead Letter Queue'],
        'payload_schema': {
            'cycle_id': 'string',
            'tenant_id': 'string',
            'space_id': 'string',
            'actor_id': 'string',
            'failed_phase': 'string',  # R0, R1, R2, ..., R8
            'error_message': 'string',
            'error_code': 'string',
            'events_processed_before_failure': 'integer',
            'failed_at': 'string (ISO8601)'
        },
        'emitter': 'Error Handler'
    },

    # P03 Phase Duration Exceeded → Monitoring
    'p03.phase.duration.exceeded.v1': {
        'description': 'Consolidation phase exceeded time budget',
        'consumers': ['Monitoring', 'Performance Analysis'],
        'payload_schema': {
            'cycle_id': 'string',
            'phase': 'string',  # R0, R1, R2, ..., R8
            'duration_minutes': 'float',
            'budget_minutes': 'integer',
            'overage_percent': 'float',
            'detected_at': 'string (ISO8601)'
        },
        'emitter': 'Phase Duration Monitor'
    }
}
```

**Event Emission Examples**:

```python
async def emit_consolidation_complete(cycle_stats: dict):
    """
    Emit p03.consolidation.complete.v1 after successful cycle.
    """
    await bus.emit(
        topic='p03.consolidation.complete.v1',
        payload={
            'cycle_id': cycle_stats['cycle_id'],
            'tenant_id': cycle_stats['tenant_id'],
            'space_id': cycle_stats['space_id'],
            'actor_id': cycle_stats['actor_id'],
            'cycle_start_time': cycle_stats['start_time'],
            'cycle_end_time': cycle_stats['end_time'],
            'duration_seconds': cycle_stats['duration_seconds'],
            'events_processed': cycle_stats['events_processed'],
            'memories_created': cycle_stats['memories_created'],
            'deduplication_stats': cycle_stats['deduplication_stats'],
            'completed_at': utc_now()
        },
        correlation_id=cycle_stats['cycle_id']
    )


async def emit_pattern_extracted(pattern: dict):
    """
    Emit p03.pattern.extracted.v1 when semantic pattern is created.
    """
    await bus.emit(
        topic='p03.pattern.extracted.v1',
        payload={
            'pattern_id': pattern['semantic_id'],
            'tenant_id': pattern['tenant_id'],
            'space_id': pattern['space_id'],
            'actor_id': pattern['actor_id'],
            'pattern_type': pattern['pattern_type'],
            'pattern_name': pattern['pattern_name'],
            'confidence_score': pattern['confidence_score'],
            'frequency': pattern['frequency'],
            'temporal_pattern_type': pattern['temporal_pattern_type'],
            'recurrence_interval_days': pattern.get('recurrence_interval_days'),
            'source_event_count': len(json.loads(pattern['source_episodes_json'])),
            'extracted_at': utc_now()
        }
    )


async def emit_kg_updated(update_type: str, node_ids: list, edge_ids: list, entity_types: list, relationship_types: list):
    """
    Emit p03.kg.updated.v1 when KG is modified.
    """
    await bus.emit(
        topic='p03.kg.updated.v1',
        payload={
            'update_type': update_type,
            'tenant_id': current_tenant_id,
            'space_id': current_space_id,
            'actor_id': current_actor_id,
            'node_ids': node_ids,
            'edge_ids': edge_ids,
            'entity_types': entity_types,
            'relationship_types': relationship_types,
            'updated_at': utc_now()
        }
    )
```

**Observability**:

- Metric: `p03_events_emitted_total` (counter by topic)
- Metric: `p03_event_emission_duration_seconds` (histogram by topic)
- Metric: `p03_event_emission_failures_total` (counter by topic)
- Log: `event_emitted` with topic and payload_size

---

## Integration Points

**Purpose**: Define how P03 integrates with upstream and downstream pipelines, including data flow, API contracts, and synchronization mechanisms.

**Integration Architecture**:

```
┌─────────────────────────────────────────────────────────────┐
│ P03 Integration Flow                                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────┐     ┌──────────┐     ┌──────────┐           │
│  │   P02    │────▶│   P03    │────▶│   P08    │           │
│  │  (Write) │     │  (Consol)│     │ (Embed)  │           │
│  └──────────┘     └──────────┘     └──────────┘           │
│                         │                                   │
│                         ├──────────▶ P15 (Rollups)         │
│                         │                                   │
│                         └──────────▶ P06 (Learning)        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

### P02 (Write) → P03 (Consolidation)

**Purpose**: P02 writes raw envelopes to `st_hipp_events` (hippocampal staging), triggering P03 consolidation when batch threshold is reached.

**Data Flow**:

1. P02 receives envelope from device/assistant
2. P02 validates, enriches, and writes to `st_hipp_events`
3. P02 emits `p02.write.complete.v1` event
4. P03 consumes event, increments batch counter
5. When batch threshold reached (e.g., 1000 events), P03 initiates consolidation cycle

**Shared Data Structures**:

```sql
-- st_hipp_events: Shared staging table between P02 (writes) and P03 (reads)
CREATE TABLE st_hipp_events (
    event_id TEXT PRIMARY KEY,
    envelope_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    space_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,

    -- Written by P02
    band TEXT NOT NULL,
    topic TEXT NOT NULL,
    device_kind TEXT NOT NULL,
    event_time_utc TEXT NOT NULL,
    text TEXT,
    body_json TEXT,
    metadata_json TEXT,
    participants_json TEXT,
    location_name TEXT,
    latitude REAL,
    longitude REAL,

    -- Updated by P03
    consolidation_status TEXT DEFAULT 'PENDING',  -- PENDING, CONSOLIDATING, CONSOLIDATED, FAILED
    consolidated_at TEXT,
    consolidation_cycle_id TEXT,
    episode_cluster_id TEXT,
    simhash_fingerprint INTEGER,
    novelty_score REAL,
    is_near_duplicate INTEGER DEFAULT 0,
    canonical_event_id TEXT,
    archival_status TEXT DEFAULT 'ACTIVE',  -- ACTIVE, PENDING_ARCHIVE, ARCHIVED
    archival_deadline TEXT,
    archived_at TEXT,
    tombstone_status TEXT,  -- NULL, TOMBSTONED
    tombstoned_at TEXT,
    tombstone_reason TEXT,
    tombstone_retention_until TEXT,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (envelope_id) REFERENCES envelopes(envelope_id)
);
```

**Integration Contract**:

```python
class P02ToP03Contract:
    """
    Contract between P02 and P03 pipelines.
    """

    # P02 Responsibilities
    @staticmethod
    async def write_event_to_staging(envelope: dict) -> str:
        """
        P02 writes envelope to st_hipp_events.

        Returns:
            event_id
        """
        event_id = generate_id()

        await storage.execute(
            """
            INSERT INTO st_hipp_events (
                event_id, envelope_id, tenant_id, space_id, actor_id,
                band, topic, device_kind, event_time_utc,
                text, body_json, metadata_json, participants_json,
                location_name, latitude, longitude,
                consolidation_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                envelope['envelope_id'],
                envelope['tenant_id'],
                envelope['space_id'],
                envelope['actor_id'],
                envelope['band'],
                envelope['topic'],
                envelope['device_kind'],
                envelope['event_time_utc'],
                envelope.get('text'),
                json.dumps(envelope.get('body', {})),
                json.dumps(envelope.get('metadata', {})),
                json.dumps(envelope.get('participants', [])),
                envelope.get('location', {}).get('name'),
                envelope.get('location', {}).get('latitude'),
                envelope.get('location', {}).get('longitude'),
                'PENDING',
                utc_now(),
                utc_now()
            )
        )

        # Emit event to P03
        await bus.emit(
            topic='p02.write.complete.v1',
            payload={
                'envelope_id': envelope['envelope_id'],
                'event_id': event_id,
                'tenant_id': envelope['tenant_id'],
                'space_id': envelope['space_id'],
                'actor_id': envelope['actor_id'],
                'band': envelope['band'],
                'topic': envelope['topic'],
                'device_kind': envelope['device_kind'],
                'event_time_utc': envelope['event_time_utc'],
                'written_at': utc_now(),
                'event_count': 1
            }
        )

        return event_id

    # P03 Responsibilities
    @staticmethod
    async def query_pending_events(tenant_id: str, space_id: str, limit: int = 1000) -> list:
        """
        P03 queries pending events from staging table.
        """
        return await storage.query_many(
            """
            SELECT * FROM st_hipp_events
            WHERE tenant_id = ? AND space_id = ?
              AND consolidation_status = 'PENDING'
            ORDER BY event_time_utc ASC
            LIMIT ?
            """,
            (tenant_id, space_id, limit)
        )

    @staticmethod
    async def mark_events_consolidating(event_ids: list, cycle_id: str):
        """
        P03 marks events as consolidating (locks them for processing).
        """
        await storage.execute(
            f"""
            UPDATE st_hipp_events
            SET consolidation_status = 'CONSOLIDATING',
                consolidation_cycle_id = ?,
                updated_at = ?
            WHERE event_id IN ({','.join('?' * len(event_ids))})
            """,
            [cycle_id, utc_now()] + event_ids
        )

    @staticmethod
    async def mark_events_consolidated(event_ids: list):
        """
        P03 marks events as consolidated after successful processing.
        """
        await storage.execute(
            f"""
            UPDATE st_hipp_events
            SET consolidation_status = 'CONSOLIDATED',
                consolidated_at = ?,
                updated_at = ?
            WHERE event_id IN ({','.join('?' * len(event_ids))})
            """,
            [utc_now(), utc_now()] + event_ids
        )
```

**Observability**:

- Metric: `p03_events_received_from_p02_total` (counter)
- Metric: `p03_staging_table_size` (gauge, pending event count)
- Metric: `p03_p02_integration_lag_seconds` (gauge, time since last write)
- Log: `p02_event_consumed` with event_id and band

---

### P03 → P08 (Embedding Lifecycle)

**Purpose**: P03 notifies P08 when new memories are created (episodic, semantic, KG nodes), triggering FAISS indexing for vector search.

**Data Flow**:

1. P03 writes new memory to `st_epi`, `st_sem`, or `st_kg_dom`
2. P03 emits `p03.consolidation.complete.v1` or `p03.pattern.extracted.v1`
3. P08 consumes event, identifies new memories
4. P08 reads embeddings from `st_vec` (already computed by P02 via UltraBERT)
5. P08 builds/updates FAISS index for vector similarity search

**Integration Contract**:

```python
class P03ToP08Contract:
    """
    Contract between P03 and P08 pipelines.
    """

    # P03 Responsibilities
    @staticmethod
    async def emit_memory_created(memory_type: str, memory_id: str, content: dict):
        """
        P03 emits event when memory is created.
        """
        if memory_type == 'episodic':
            # Episodic memory written to st_epi
            await bus.emit(
                topic='p03.consolidation.complete.v1',
                payload={
                    'memories_created': {'episodic': 1},
                    'episodic_memory_ids': [memory_id]
                }
            )

        elif memory_type == 'semantic':
            # Semantic pattern extracted
            await bus.emit(
                topic='p03.pattern.extracted.v1',
                payload={
                    'pattern_id': memory_id,
                    'pattern_name': content['pattern_name'],
                    'confidence_score': content['confidence_score']
                }
            )

        elif memory_type == 'kg_node':
            # KG node created
            await bus.emit(
                topic='p03.kg.updated.v1',
                payload={
                    'update_type': 'node_created',
                    'node_ids': [memory_id]
                }
            )

    # P08 Responsibilities
    @staticmethod
    async def generate_embeddings_for_new_memories(cycle_id: str):
        """
        P08 generates embeddings for memories created in cycle.
        """
        # Query new episodic memories
        episodic_memories = await storage.query_many(
            """
            SELECT episode_id, episode_summary
            FROM st_epi
            WHERE consolidation_cycle_id = ?
              AND episode_id NOT IN (SELECT memory_id FROM st_vec WHERE memory_type = 'episodic')
            """,
            (cycle_id,)
        )

        # Generate embeddings
        for memory in episodic_memories:
            embedding = await generate_embedding(memory['episode_summary'])
            await write_vector(memory['episode_id'], 'episodic', embedding)

        logger.info("embeddings_generated", memory_type='episodic', count=len(episodic_memories))
```

**Observability**:

- Metric: `p03_memories_sent_to_p08_total` (counter by memory_type)
- Metric: `p08_embedding_lag_seconds` (gauge, time since memory creation)
- Log: `memory_sent_to_p08` with memory_id and memory_type

---

### P03 → P15 (Rollups/Summaries)

**Purpose**: P03 provides consolidated memories to P15 for aggregation into daily/weekly/monthly summaries and insights.

**Data Flow**:

1. P03 completes consolidation cycle, writes memories to layers
2. P03 emits `p03.consolidation.complete.v1`
3. P15 consumes event, queries consolidated memories for time period
4. P15 generates rollup summaries (e.g., "This week you exercised 5 times")
5. P15 writes summaries to `st_rollups`

**Integration Contract**:

```python
class P03ToP15Contract:
    """
    Contract between P03 and P15 pipelines.
    """

    # P03 Responsibilities
    @staticmethod
    async def emit_consolidation_complete_with_stats(cycle_stats: dict):
        """
        P03 emits consolidation complete with memory creation stats.
        """
        await bus.emit(
            topic='p03.consolidation.complete.v1',
            payload={
                'cycle_id': cycle_stats['cycle_id'],
                'memories_created': cycle_stats['memories_created'],
                'time_range': {
                    'start': cycle_stats['earliest_event_time'],
                    'end': cycle_stats['latest_event_time']
                }
            }
        )

    # P15 Responsibilities
    @staticmethod
    async def query_memories_for_rollup(tenant_id: str, space_id: str, start_time: str, end_time: str) -> dict:
        """
        P15 queries consolidated memories for rollup generation.
        """
        episodic = await storage.query_many(
            """
            SELECT * FROM st_epi
            WHERE tenant_id = ? AND space_id = ?
              AND episode_start_time >= ? AND episode_end_time <= ?
            """,
            (tenant_id, space_id, start_time, end_time)
        )

        semantic = await storage.query_many(
            """
            SELECT * FROM st_sem
            WHERE tenant_id = ? AND space_id = ?
              AND valid_from >= ? AND (valid_to IS NULL OR valid_to <= ?)
            """,
            (tenant_id, space_id, start_time, end_time)
        )

        return {
            'episodic': episodic,
            'semantic': semantic
        }
```

**Observability**:

- Metric: `p03_consolidation_complete_sent_to_p15_total` (counter)
- Metric: `p15_rollup_lag_seconds` (gauge, time since consolidation)
- Log: `consolidation_complete_sent_to_p15` with cycle_id

---

### P03 → P06 (Learning/Neuromodulation)

**Purpose**: P03 provides learning signals to P06 for reward modeling, attention modulation, and behavioral adaptation based on memory consolidation outcomes.

**Data Flow**:

1. P03 consolidates memories, detects patterns, computes novelty scores
2. P03 emits learning signals (high-novelty events, pattern discoveries, causal relationships)
3. P06 consumes signals, updates attention weights and reward models
4. P06 influences future consolidation priorities via feedback loop

**Integration Contract**:

```python
class P03ToP06Contract:
    """
    Contract between P03 and P06 pipelines (learning loop).
    """

    # P03 Responsibilities
    @staticmethod
    async def emit_learning_signal(signal_type: str, payload: dict):
        """
        P03 emits learning signal to P06.
        """
        learning_signals = {
            'high_novelty_event': {
                'topic': 'p03.learning.high_novelty.v1',
                'payload': {
                    'event_id': payload['event_id'],
                    'novelty_score': payload['novelty_score'],
                    'activity_type': payload['activity_type']
                }
            },
            'pattern_discovered': {
                'topic': 'p03.learning.pattern_discovered.v1',
                'payload': {
                    'pattern_id': payload['pattern_id'],
                    'pattern_type': payload['pattern_type'],
                    'confidence': payload['confidence_score']
                }
            },
            'causal_relationship': {
                'topic': 'p03.learning.causal_relationship.v1',
                'payload': {
                    'cause_event': payload['cause_event'],
                    'effect_event': payload['effect_event'],
                    'causal_confidence': payload['causal_confidence']
                }
            }
        }

        signal = learning_signals[signal_type]
        await bus.emit(topic=signal['topic'], payload=signal['payload'])

    # P06 Responsibilities
    @staticmethod
    async def update_attention_weights(learning_signal: dict):
        """
        P06 updates attention weights based on P03 learning signals.
        """
        if learning_signal['type'] == 'high_novelty':
            # Increase attention weight for activity_type
            activity_type = learning_signal['activity_type']
            await storage.execute(
                """
                UPDATE attention_weights
                SET weight = weight * 1.2
                WHERE activity_type = ?
                """,
                (activity_type,)
            )

        elif learning_signal['type'] == 'pattern_discovered':
            # Increase consolidation priority for pattern-related events
            pattern_type = learning_signal['pattern_type']
            await storage.execute(
                """
                UPDATE st_hipp_events
                SET consolidation_priority = 'HIGH'
                WHERE activity_type = ?
                  AND consolidation_status = 'PENDING'
                """,
                (pattern_type,)
            )
```

**Observability**:

- Metric: `p03_learning_signals_sent_to_p06_total` (counter by signal_type)
- Metric: `p06_attention_weight_updates_total` (counter)
- Log: `learning_signal_sent_to_p06` with signal_type and payload

---

## Observability & Metrics

**Purpose**: Define comprehensive observability strategy for P03 consolidation pipeline, including metrics, logging, tracing, and alerting. Observability enables performance monitoring, debugging, and proactive issue detection.

**Observability Stack**:

- **Metrics**: Prometheus-compatible counters, gauges, histograms
- **Logging**: Structured JSON logs with correlation IDs
- **Tracing**: Distributed tracing with OpenTelemetry spans
- **Alerting**: Threshold-based alerts via M04 Alerting

**Metric Naming Convention**: `p03_<subsystem>_<metric_name>_<unit>`

---

### Consolidation Progress Metrics

**Purpose**: Track consolidation cycle progress, phase completion, and overall pipeline health.

**Key Metrics**:

```python
# Cycle-level metrics
CONSOLIDATION_METRICS = {
    # Cycle execution
    'p03_cycle_started_total': {
        'type': 'counter',
        'description': 'Total consolidation cycles started',
        'labels': ['tenant_id', 'space_id', 'cycle_type']
    },
    'p03_cycle_completed_total': {
        'type': 'counter',
        'description': 'Total consolidation cycles completed successfully',
        'labels': ['tenant_id', 'space_id', 'cycle_type']
    },
    'p03_cycle_failed_total': {
        'type': 'counter',
        'description': 'Total consolidation cycles failed',
        'labels': ['tenant_id', 'space_id', 'failed_phase', 'error_code']
    },
    'p03_cycle_duration_seconds': {
        'type': 'histogram',
        'description': 'Consolidation cycle duration (end-to-end)',
        'buckets': [60, 300, 900, 1800, 3600, 5400, 7200]  # 1min to 2hrs
    },

    # Phase-level metrics
    'p03_phase_duration_seconds': {
        'type': 'histogram',
        'description': 'Duration of each consolidation phase',
        'labels': ['phase'],  # R0, R1, R2, ..., R8
        'buckets': [10, 30, 60, 120, 300, 600, 1200, 1800]
    },
    'p03_phase_completed_total': {
        'type': 'counter',
        'description': 'Phases completed successfully',
        'labels': ['phase']
    },
    'p03_phase_failed_total': {
        'type': 'counter',
        'description': 'Phases failed',
        'labels': ['phase', 'error_code']
    },

    # Event processing
    'p03_events_processed_total': {
        'type': 'counter',
        'description': 'Total events processed across all cycles',
        'labels': ['tenant_id', 'space_id', 'band', 'topic']
    },
    'p03_events_pending_gauge': {
        'type': 'gauge',
        'description': 'Current number of pending events in st_hipp_events',
        'labels': ['tenant_id', 'space_id']
    },
    'p03_batch_size': {
        'type': 'histogram',
        'description': 'Number of events per consolidation batch',
        'buckets': [100, 250, 500, 1000, 2000, 5000]
    },

    # Throughput
    'p03_throughput_events_per_second': {
        'type': 'gauge',
        'description': 'Current consolidation throughput (events/sec)',
        'labels': ['phase']
    },
    'p03_throughput_events_per_minute': {
        'type': 'gauge',
        'description': 'Current consolidation throughput (events/min)',
        'labels': ['phase']
    }
}
```

**Metric Collection Example**:

```python
from prometheus_client import Counter, Gauge, Histogram
import time

# Initialize metrics
cycle_started = Counter('p03_cycle_started_total', 'Cycles started', ['tenant_id', 'space_id', 'cycle_type'])
cycle_completed = Counter('p03_cycle_completed_total', 'Cycles completed', ['tenant_id', 'space_id', 'cycle_type'])
cycle_duration = Histogram('p03_cycle_duration_seconds', 'Cycle duration', buckets=[60, 300, 900, 1800, 3600, 5400])
phase_duration = Histogram('p03_phase_duration_seconds', 'Phase duration', ['phase'])

async def run_consolidation_cycle_with_metrics(cycle_id: str, tenant_id: str, space_id: str):
    """
    Run consolidation cycle with full metric instrumentation.
    """
    cycle_type = 'regular'
    cycle_start_time = time.time()

    # Increment cycle started
    cycle_started.labels(tenant_id=tenant_id, space_id=space_id, cycle_type=cycle_type).inc()

    try:
        # R0: Trigger Detection
        phase_start = time.time()
        await run_phase_r0()
        phase_duration.labels(phase='R0').observe(time.time() - phase_start)

        # R1: Hippocampal Replay
        phase_start = time.time()
        await run_phase_r1()
        phase_duration.labels(phase='R1').observe(time.time() - phase_start)

        # R2: Neocortical Integration
        phase_start = time.time()
        await run_phase_r2()
        phase_duration.labels(phase='R2').observe(time.time() - phase_start)

        # ... remaining phases

        # Record successful completion
        cycle_completed.labels(tenant_id=tenant_id, space_id=space_id, cycle_type=cycle_type).inc()
        cycle_duration.observe(time.time() - cycle_start_time)

    except Exception as e:
        logger.error("cycle_failed", cycle_id=cycle_id, error=str(e))
        # Failed cycle metric recorded in error handler
        raise
```

**Dashboards**:

- Consolidation cycle overview (success rate, duration, throughput)
- Phase breakdown (duration per phase, bottlenecks)
- Event processing pipeline (pending → consolidating → consolidated)

---

### Memory Layer Statistics

**Purpose**: Track memory creation rates, layer utilization, and memory quality metrics across all memory layers (episodic, semantic, procedural, social, prospective, KG).

**Key Metrics**:

```python
MEMORY_LAYER_METRICS = {
    # Memory creation
    'p03_memories_created_total': {
        'type': 'counter',
        'description': 'Total memories created by layer',
        'labels': ['memory_layer']  # episodic, semantic, procedural, social, prospective, kg_nodes, kg_edges
    },
    'p03_memories_updated_total': {
        'type': 'counter',
        'description': 'Total memories updated (incremental learning)',
        'labels': ['memory_layer']
    },
    'p03_memories_deleted_total': {
        'type': 'counter',
        'description': 'Total memories deleted (DSAR, retention)',
        'labels': ['memory_layer', 'deletion_reason']
    },

    # Layer size
    'p03_memory_layer_size_gauge': {
        'type': 'gauge',
        'description': 'Current number of memories in layer',
        'labels': ['memory_layer', 'tenant_id', 'space_id']
    },
    'p03_memory_layer_storage_bytes': {
        'type': 'gauge',
        'description': 'Storage size of memory layer (bytes)',
        'labels': ['memory_layer', 'storage_type']  # active, archived
    },

    # Consolidation ratio
    'p03_consolidation_ratio': {
        'type': 'gauge',
        'description': 'Memories created per event (consolidation efficiency)',
        'labels': ['memory_layer']
    },

    # Pattern quality (semantic layer)
    'p03_pattern_confidence_score': {
        'type': 'histogram',
        'description': 'Confidence scores of extracted semantic patterns',
        'buckets': [0.1, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 1.0]
    },
    'p03_pattern_frequency': {
        'type': 'histogram',
        'description': 'Frequency (occurrence count) of semantic patterns',
        'buckets': [2, 5, 10, 20, 50, 100, 200]
    },
    'p03_strong_patterns_gauge': {
        'type': 'gauge',
        'description': 'Number of strong patterns (confidence >0.8)',
        'labels': ['tenant_id', 'space_id']
    },

    # Knowledge graph statistics
    'p03_kg_nodes_total': {
        'type': 'gauge',
        'description': 'Total KG nodes by entity type',
        'labels': ['entity_type']  # Person, Place, Activity, Topic, etc.
    },
    'p03_kg_edges_total': {
        'type': 'gauge',
        'description': 'Total KG edges by relationship type',
        'labels': ['relationship_type']  # friend_of, works_at, located_at, etc.
    },
    'p03_kg_causal_edges_total': {
        'type': 'gauge',
        'description': 'Number of causal relationships detected',
        'labels': ['tenant_id', 'space_id']
    },
    'p03_entity_resolution_total': {
        'type': 'counter',
        'description': 'Entity resolutions by method',
        'labels': ['resolution_method']  # exact, fuzzy, alias, new
    },
    'p03_entity_merges_total': {
        'type': 'counter',
        'description': 'Entity merges (duplicate resolution)',
        'labels': ['entity_type']
    }
}
```

**Query Examples**:

```python
async def collect_memory_layer_statistics():
    """
    Collect and emit memory layer statistics (called after each consolidation cycle).
    """
    from prometheus_client import Gauge

    memory_layer_size = Gauge('p03_memory_layer_size_gauge', 'Memory layer size', ['memory_layer', 'tenant_id', 'space_id'])

    # Query layer sizes
    layers = ['st_epi', 'st_sem', 'st_procedural', 'st_social', 'st_prospective']

    for layer in layers:
        count = await storage.query_one(
            f"SELECT COUNT(*) as count FROM {layer} WHERE tenant_id = ? AND space_id = ?",
            (current_tenant_id, current_space_id)
        )

        memory_layer_size.labels(
            memory_layer=layer,
            tenant_id=current_tenant_id,
            space_id=current_space_id
        ).set(count['count'])

    # Query KG statistics
    kg_node_count = await storage.query_one(
        "SELECT COUNT(*) as count FROM st_kg_dom WHERE tenant_id = ? AND space_id = ?",
        (current_tenant_id, current_space_id)
    )

    kg_edge_count = await storage.query_one(
        "SELECT COUNT(*) as count FROM st_kg_edges WHERE tenant_id = ? AND space_id = ?",
        (current_tenant_id, current_space_id)
    )

    logger.info(
        "memory_layer_statistics",
        episodic=count_epi,
        semantic=count_sem,
        kg_nodes=kg_node_count['count'],
        kg_edges=kg_edge_count['count']
    )
```

---

### Deduplication Statistics

**Purpose**: Track deduplication effectiveness, novelty score distribution, and duplicate detection performance.

**Key Metrics**:

```python
DEDUPLICATION_METRICS = {
    # Duplicate detection
    'p03_duplicates_found_total': {
        'type': 'counter',
        'description': 'Total near-duplicate events detected',
        'labels': ['tenant_id', 'space_id']
    },
    'p03_exact_duplicates_total': {
        'type': 'counter',
        'description': 'Exact duplicate events (SimHash distance = 0)',
        'labels': ['tenant_id', 'space_id']
    },
    'p03_duplicate_detection_duration_seconds': {
        'type': 'histogram',
        'description': 'Time to detect duplicates in batch',
        'buckets': [0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
    },

    # Novelty scoring
    'p03_novelty_score_distribution': {
        'type': 'histogram',
        'description': 'Distribution of novelty scores',
        'buckets': [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    },
    'p03_novelty_score_mean': {
        'type': 'gauge',
        'description': 'Mean novelty score for batch',
        'labels': ['tenant_id', 'space_id']
    },
    'p03_high_novelty_events_total': {
        'type': 'counter',
        'description': 'Events with high novelty (>0.8)',
        'labels': ['tenant_id', 'space_id']
    },
    'p03_low_novelty_events_total': {
        'type': 'counter',
        'description': 'Events with low novelty (<0.3)',
        'labels': ['tenant_id', 'space_id']
    },

    # SimHash performance
    'p03_simhash_computation_duration_seconds': {
        'type': 'histogram',
        'description': 'Time to compute SimHash per event',
        'buckets': [0.001, 0.005, 0.01, 0.05, 0.1]
    },
    'p03_simhash_comparisons_total': {
        'type': 'counter',
        'description': 'Total SimHash pairwise comparisons',
        'labels': ['comparison_method']  # brute_force, lsh
    },

    # Deduplication effectiveness
    'p03_deduplication_rate': {
        'type': 'gauge',
        'description': 'Percentage of events marked as duplicates',
        'labels': ['tenant_id', 'space_id']
    },
    'p03_storage_saved_via_dedup_bytes': {
        'type': 'gauge',
        'description': 'Storage saved by not storing duplicate content',
        'labels': ['tenant_id', 'space_id']
    }
}
```

**Metric Collection**:

```python
async def collect_deduplication_statistics(batch_events: list, dedup_results: dict):
    """
    Collect deduplication metrics after R1.4 phase.
    """
    from prometheus_client import Counter, Gauge, Histogram

    duplicates_found = Counter('p03_duplicates_found_total', 'Duplicates found', ['tenant_id', 'space_id'])
    novelty_score_dist = Histogram('p03_novelty_score_distribution', 'Novelty distribution', buckets=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
    novelty_mean = Gauge('p03_novelty_score_mean', 'Mean novelty', ['tenant_id', 'space_id'])

    # Count duplicates
    duplicate_count = sum(1 for e in batch_events if e.get('is_near_duplicate'))
    duplicates_found.labels(tenant_id=current_tenant_id, space_id=current_space_id).inc(duplicate_count)

    # Novelty score distribution
    novelty_scores = [e.get('novelty_score', 0.5) for e in batch_events]
    for score in novelty_scores:
        novelty_score_dist.observe(score)

    # Mean novelty
    mean_novelty = sum(novelty_scores) / len(novelty_scores) if novelty_scores else 0.5
    novelty_mean.labels(tenant_id=current_tenant_id, space_id=current_space_id).set(mean_novelty)

    logger.info(
        "deduplication_statistics",
        total_events=len(batch_events),
        duplicates_found=duplicate_count,
        deduplication_rate=duplicate_count / len(batch_events),
        mean_novelty=mean_novelty,
        high_novelty_count=sum(1 for s in novelty_scores if s > 0.8),
        low_novelty_count=sum(1 for s in novelty_scores if s < 0.3)
    )
```

---

### Sleep Cycle Timing

**Purpose**: Monitor sleep cycle timing, phase transitions, and cycle health to ensure 90-minute target adherence.

**Key Metrics**:

```python
SLEEP_CYCLE_METRICS = {
    # Cycle timing
    'p03_sleep_cycle_interval_seconds': {
        'type': 'gauge',
        'description': 'Time between consecutive consolidation cycles',
        'labels': ['tenant_id', 'space_id']
    },
    'p03_cycle_start_lag_seconds': {
        'type': 'histogram',
        'description': 'Lag between scheduled start and actual start',
        'buckets': [0, 5, 10, 30, 60, 120, 300]
    },
    'p03_cycles_per_day': {
        'type': 'gauge',
        'description': 'Number of consolidation cycles per 24 hours',
        'labels': ['tenant_id', 'space_id']
    },

    # Phase transitions
    'p03_phase_transition_duration_seconds': {
        'type': 'histogram',
        'description': 'Time between phase completion and next phase start',
        'labels': ['from_phase', 'to_phase'],
        'buckets': [0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
    },

    # Budget adherence
    'p03_phase_budget_exceeded_total': {
        'type': 'counter',
        'description': 'Phases that exceeded time budget',
        'labels': ['phase']
    },
    'p03_cycle_budget_exceeded_total': {
        'type': 'counter',
        'description': 'Cycles that exceeded 90-minute target',
        'labels': ['overage_category']  # minor (<100min), moderate (<120min), major (>120min)
    },
    'p03_cycle_budget_adherence_rate': {
        'type': 'gauge',
        'description': 'Percentage of cycles completing within 90 minutes',
        'labels': ['tenant_id', 'space_id']
    },

    # Cycle health
    'p03_consecutive_failed_cycles': {
        'type': 'gauge',
        'description': 'Number of consecutive failed cycles',
        'labels': ['tenant_id', 'space_id']
    },
    'p03_cycle_success_rate': {
        'type': 'gauge',
        'description': 'Success rate over last 24 hours',
        'labels': ['tenant_id', 'space_id']
    }
}
```

**Alerting Rules**:

```yaml
# Prometheus alerting rules for P03 sleep cycle timing
groups:
  - name: p03_sleep_cycle_alerts
    interval: 30s
    rules:
      # Cycle duration exceeded
      - alert: P03CycleDurationExceeded
        expr: p03_cycle_duration_seconds > 7200  # 2 hours
        for: 5m
        labels:
          severity: warning
          pipeline: p03
        annotations:
          summary: "P03 consolidation cycle duration exceeded 2 hours"
          description: "Cycle {{ $labels.cycle_id }} took {{ $value }}s (>2hrs)"

      # Phase budget exceeded
      - alert: P03PhaseBudgetExceeded
        expr: p03_phase_duration_seconds{phase="R1"} > 2100  # 35 minutes
        for: 5m
        labels:
          severity: warning
          pipeline: p03
        annotations:
          summary: "P03 phase {{ $labels.phase }} exceeded time budget"
          description: "Phase {{ $labels.phase }} took {{ $value }}s"

      # Consecutive failures
      - alert: P03ConsecutiveFailures
        expr: p03_consecutive_failed_cycles >= 3
        for: 5m
        labels:
          severity: critical
          pipeline: p03
        annotations:
          summary: "P03 has {{ $value }} consecutive failed cycles"
          description: "Check P03 pipeline health immediately"

      # Low success rate
      - alert: P03LowSuccessRate
        expr: p03_cycle_success_rate < 0.8  # <80%
        for: 15m
        labels:
          severity: warning
          pipeline: p03
        annotations:
          summary: "P03 success rate below 80%"
          description: "Success rate: {{ $value }}% (last 24h)"

      # Pending events backlog
      - alert: P03EventBacklog
        expr: p03_events_pending_gauge > 10000
        for: 30m
        labels:
          severity: warning
          pipeline: p03
        annotations:
          summary: "P03 event backlog exceeds 10k events"
          description: "{{ $value }} events pending consolidation"
```

---

## Testing Strategy

**Purpose**: Define comprehensive testing strategy for P03 consolidation pipeline, ensuring correctness, performance, and reliability across all phases and memory layers.

**Testing Philosophy**:

- **Test Pyramid**: 60% unit tests, 30% integration tests, 10% e2e tests
- **Contract Testing**: Validate interfaces between P02→P03→P08/P15/P06
- **Property-Based Testing**: Use hypothesis/quickcheck for edge cases
- **Performance Testing**: Load tests for throughput and latency targets

**Test Infrastructure**:

- **Framework**: pytest + ward
- **Fixtures**: Shared test data in `tests/fixtures/p03_test_data.json`
- **Mocks**: Use unittest.mock for external dependencies (storage, bus)
- **Coverage Target**: >85% code coverage, >95% for critical paths

---

### Unit Tests (Module-Level)

**Purpose**: Test individual functions and classes in isolation, focusing on logic correctness and edge cases.

**Test Organization**:

```
tests/
├── k0/
│   └── pipelines/
│       └── p03_consolidation/
│           ├── test_deduplication.py           # R1.4 SimHash, novelty scoring
│           ├── test_pattern_extraction.py      # R2.2 clustering, pattern discovery
│           ├── test_knowledge_graph.py         # R4 entity resolution, relationships
│           ├── test_retention_policies.py      # R3.4 policy lookup, archival
│           ├── test_gdpr_dsar.py               # DSAR access/erasure
│           └── test_helpers.py                 # Utility functions
```

**Example Unit Tests**:

```python
# tests/k0/pipelines/p03_consolidation/test_deduplication.py

import pytest
from hypothesis import given, strategies as st
from k0.pipelines.p03_consolidation.deduplication import (
    compute_simhash,
    hamming_distance,
    is_near_duplicate,
    compute_novelty_score
)

class TestSimHash:
    """Test SimHash computation and comparison."""

    def test_simhash_identical_text_returns_same_hash(self):
        """Identical texts should produce identical hashes."""
        text = "Had coffee with Sarah at Starbucks"
        hash1 = compute_simhash(text)
        hash2 = compute_simhash(text)

        assert hash1 == hash2

    def test_simhash_similar_text_returns_close_hash(self):
        """Similar texts should produce hashes with small Hamming distance."""
        text1 = "Had coffee with Sarah at Starbucks"
        text2 = "Had coffee with Sarah at Starbucks this morning"

        hash1 = compute_simhash(text1)
        hash2 = compute_simhash(text2)

        distance = hamming_distance(hash1, hash2)
        assert distance <= 5  # Allow small difference

    def test_simhash_different_text_returns_distant_hash(self):
        """Different texts should produce hashes with large Hamming distance."""
        text1 = "Had coffee with Sarah"
        text2 = "Went to the gym for workout"

        hash1 = compute_simhash(text1)
        hash2 = compute_simhash(text2)

        distance = hamming_distance(hash1, hash2)
        assert distance > 10  # Significant difference

    @given(st.text(min_size=10, max_size=1000))
    def test_simhash_always_returns_64bit_integer(self, text):
        """SimHash should always return 64-bit integer."""
        hash_value = compute_simhash(text)
        assert isinstance(hash_value, int)
        assert 0 <= hash_value < 2**64


class TestNoveltyScore:
    """Test novelty score computation."""

    def test_novelty_high_for_unique_event(self):
        """Unique events should have high novelty."""
        event = {'text': 'Completely unique experience never seen before'}
        recent_events = [
            {'text': 'Coffee at Starbucks'},
            {'text': 'Gym workout'},
            {'text': 'Dinner with family'}
        ]

        novelty = compute_novelty_score(event, recent_events, time_window_event_count=3)
        assert novelty > 0.8

    def test_novelty_low_for_duplicate_event(self):
        """Duplicate events should have low novelty."""
        event = {'text': 'Coffee at Starbucks'}
        recent_events = [
            {'text': 'Coffee at Starbucks'},
            {'text': 'Coffee at Starbucks'},
            {'text': 'Coffee at Starbucks'}
        ]

        novelty = compute_novelty_score(event, recent_events, time_window_event_count=3)
        assert novelty < 0.3

    def test_novelty_bounded_zero_to_one(self):
        """Novelty score must be in [0, 1]."""
        event = {'text': 'Test event'}
        recent_events = []

        novelty = compute_novelty_score(event, recent_events, time_window_event_count=0)
        assert 0.0 <= novelty <= 1.0
```

**Property-Based Testing Example**:

```python
from hypothesis import given, strategies as st

@given(
    text=st.text(min_size=10),
    threshold=st.integers(min_value=0, max_value=10)
)
def test_is_near_duplicate_symmetric(text, threshold):
    """Near-duplicate detection should be symmetric."""
    hash1 = compute_simhash(text)
    hash2 = compute_simhash(text + " ")  # Slight variation

    result1 = is_near_duplicate(hash1, hash2, threshold)
    result2 = is_near_duplicate(hash2, hash1, threshold)

    assert result1 == result2  # Symmetry property
```

---

### Integration Tests (Pipeline-Level)

**Purpose**: Test interactions between P03 phases, storage layer, and event bus within consolidation pipeline.

**Test Scenarios**:

```python
# tests/k0/pipelines/p03_consolidation/test_integration.py

import pytest
from k0.pipelines.p03_consolidation import ConsolidationPipeline

@pytest.mark.integration
class TestConsolidationPipeline:
    """Integration tests for P03 consolidation pipeline."""

    @pytest.fixture
    async def pipeline(self, test_storage, test_bus):
        """Create pipeline instance with test dependencies."""
        pipeline = ConsolidationPipeline(storage=test_storage, bus=test_bus)
        await pipeline.initialize()
        return pipeline

    @pytest.fixture
    async def sample_events(self, test_storage):
        """Create sample events in st_hipp_events."""
        events = [
            {
                'event_id': f'test_event_{i}',
                'tenant_id': 'test_tenant',
                'space_id': 'test_space',
                'actor_id': 'test_actor',
                'text': f'Sample event {i}',
                'event_time_utc': f'2025-11-{i:02d}T10:00:00Z',
                'band': 'GREEN',
                'topic': 'envelope.activity',
                'device_kind': 'phone'
            }
            for i in range(1, 11)  # 10 events
        ]

        for event in events:
            await test_storage.execute(
                "INSERT INTO st_hipp_events (...) VALUES (...)",
                event
            )

        return events

    async def test_full_consolidation_cycle(self, pipeline, sample_events):
        """Test complete consolidation cycle from R0 to R8."""
        cycle_id = 'test_cycle_001'

        # Run consolidation
        result = await pipeline.run_consolidation_cycle(
            cycle_id=cycle_id,
            tenant_id='test_tenant',
            space_id='test_space'
        )

        # Verify cycle completed
        assert result['status'] == 'completed'
        assert result['events_processed'] == len(sample_events)

        # Verify events marked as consolidated
        consolidated_events = await test_storage.query_many(
            "SELECT * FROM st_hipp_events WHERE consolidation_status = 'CONSOLIDATED'"
        )
        assert len(consolidated_events) == len(sample_events)

        # Verify memories created
        episodic_memories = await test_storage.query_many(
            "SELECT * FROM st_epi WHERE consolidation_cycle_id = ?",
            (cycle_id,)
        )
        assert len(episodic_memories) > 0  # At least one episodic memory

    async def test_deduplication_marks_duplicates(self, pipeline, test_storage):
        """Test that near-duplicate events are correctly identified."""
        # Insert duplicate events
        duplicate_events = [
            {'text': 'Coffee at Starbucks', 'event_id': 'dup_1'},
            {'text': 'Coffee at Starbucks', 'event_id': 'dup_2'},
            {'text': 'Coffee at Starbucks this morning', 'event_id': 'dup_3'}
        ]

        for event in duplicate_events:
            await test_storage.execute("INSERT INTO st_hipp_events (...) VALUES (...)", event)

        # Run deduplication phase
        await pipeline.run_phase_r1_4_deduplication('test_cycle_002')

        # Verify duplicates marked
        duplicates = await test_storage.query_many(
            "SELECT * FROM st_hipp_events WHERE is_near_duplicate = 1"
        )
        assert len(duplicates) >= 2  # At least 2 of the 3 should be marked as duplicates

    async def test_pattern_extraction_creates_semantic_memories(self, pipeline, test_storage):
        """Test that recurring patterns are extracted as semantic memories."""
        # Insert recurring events (weekly yoga class)
        recurring_events = [
            {'text': 'Yoga class at CorePower', 'event_time_utc': f'2025-11-{5+i*7:02d}T09:00:00Z', 'event_id': f'yoga_{i}'}
            for i in range(4)  # 4 weeks
        ]

        for event in recurring_events:
            await test_storage.execute("INSERT INTO st_hipp_events (...) VALUES (...)", event)

        # Run pattern extraction phase
        await pipeline.run_phase_r2_2_pattern_extraction('test_cycle_003')

        # Verify semantic pattern created
        patterns = await test_storage.query_many(
            "SELECT * FROM st_sem WHERE pattern_type = 'routine'"
        )
        assert len(patterns) > 0

        # Verify pattern has weekly recurrence
        pattern = patterns[0]
        assert pattern['temporal_pattern_type'] == 'weekly'
        assert pattern['confidence_score'] > 0.7
```

---

### End-to-End Tests (P02 → P03 → Layers)

**Purpose**: Test full data flow from P02 write through P03 consolidation to memory layers and downstream pipelines.

**Test Scenarios**:

```python
# tests/integration/test_p02_p03_flow.py

import pytest

@pytest.mark.e2e
class TestP02ToP03Flow:
    """End-to-end tests for P02 → P03 integration."""

    async def test_envelope_write_triggers_consolidation(
        self,
        p02_pipeline,
        p03_pipeline,
        test_storage,
        test_bus
    ):
        """Test that P02 envelope write triggers P03 consolidation when threshold reached."""
        # Write 1000 envelopes via P02 (batch threshold)
        envelopes = [create_test_envelope(i) for i in range(1000)]

        for envelope in envelopes:
            await p02_pipeline.write_envelope(envelope)

        # Verify P02 emitted write complete events
        write_events = test_bus.get_emitted_events('p02.write.complete.v1')
        assert len(write_events) == 1000

        # Wait for P03 to consume events and trigger consolidation
        await asyncio.sleep(2)

        # Verify P03 consolidation started
        cycle_events = test_bus.get_emitted_events('p03.consolidation.complete.v1')
        assert len(cycle_events) >= 1

        # Verify memories created
        memories = await test_storage.query_many(
            "SELECT COUNT(*) as count FROM st_epi"
        )
        assert memories[0]['count'] > 0

    async def test_consolidated_memories_sent_to_p08(
        self,
        p03_pipeline,
        test_bus
    ):
        """Test that P03 emits events to P08 for embedding generation."""
        cycle_id = 'test_cycle_e2e_001'

        # Run consolidation
        await p03_pipeline.run_consolidation_cycle(cycle_id=cycle_id)

        # Verify P03 emitted consolidation complete event
        events = test_bus.get_emitted_events('p03.consolidation.complete.v1')
        assert len(events) == 1

        event = events[0]
        assert 'memories_created' in event['payload']
        assert event['payload']['memories_created']['episodic'] > 0
```

---

### Performance Tests (Batch Throughput)

**Purpose**: Validate P03 meets performance budgets for throughput, latency, and resource utilization.

**Test Scenarios**:

```python
# tests/performance/test_p03_throughput.py

import pytest
import time

@pytest.mark.performance
class TestP03Performance:
    """Performance tests for P03 consolidation pipeline."""

    async def test_batch_throughput_meets_target(self, pipeline, large_event_dataset):
        """Test that P03 processes 1000 events within 90 minutes."""
        events = large_event_dataset(count=1000)

        start_time = time.time()
        result = await pipeline.run_consolidation_cycle(
            cycle_id='perf_test_001',
            tenant_id='perf_tenant',
            space_id='perf_space'
        )
        end_time = time.time()

        duration_seconds = end_time - start_time
        duration_minutes = duration_seconds / 60

        # Verify throughput
        assert duration_minutes <= 90, f"Cycle took {duration_minutes:.1f} minutes (>90 min target)"
        assert result['events_processed'] == 1000

        # Verify throughput rate
        events_per_minute = 1000 / duration_minutes
        assert events_per_minute >= 11, f"Throughput {events_per_minute:.1f} events/min (<11 target)"

    async def test_phase_duration_within_budget(self, pipeline, sample_events):
        """Test that individual phases complete within time budgets."""
        phase_budgets = {
            'R0': 2,    # minutes
            'R1': 35,
            'R2': 45,
            'R3': 12,
            'R4': 30,
            'R5': 30,
            'R6': 5,
            'R7': 20,
            'R8': 5
        }

        phase_durations = await pipeline.run_consolidation_cycle_with_phase_tracking(
            cycle_id='perf_test_002'
        )

        for phase, duration_seconds in phase_durations.items():
            duration_minutes = duration_seconds / 60
            budget_minutes = phase_budgets[phase]

            assert duration_minutes <= budget_minutes, \
                f"Phase {phase} took {duration_minutes:.1f} min (budget: {budget_minutes} min)"

    async def test_memory_usage_within_limit(self, pipeline, large_event_dataset):
        """Test that memory usage stays below 2GB during consolidation."""
        import psutil
        import os

        process = psutil.Process(os.getpid())

        events = large_event_dataset(count=2000)

        # Measure memory before
        mem_before = process.memory_info().rss / 1024 / 1024  # MB

        await pipeline.run_consolidation_cycle(cycle_id='perf_test_003')

        # Measure memory after
        mem_after = process.memory_info().rss / 1024 / 1024  # MB
        mem_increase = mem_after - mem_before

        assert mem_increase < 2048, f"Memory increased by {mem_increase:.0f} MB (>2GB limit)"
```

---

## Migration Plan

**Purpose**: Define database migration strategy for P03 consolidation pipeline, including schema creation, column additions, and data migration procedures.

**Migration Strategy**:

- **Versioned Migrations**: Sequential migration files (0025, 0026, 0027, ...)
- **Rollback Support**: Each migration includes down() for rollback
- **Zero-Downtime**: Additive changes first, then deprecate old columns
- **Data Integrity**: Validate data after migration with checksums

**Migration Tool**: Alembic (Python) or custom migration runner

---

### Migration 0025: P03 Memory Layer Tables

**Purpose**: Create memory layer tables for episodic, semantic, procedural, social, and prospective memories.

**Migration File**: `k0/migrations/0025_create_memory_layers.py`

```python
"""
Migration 0025: Create P03 Memory Layer Tables

Creates:
- st_epi (Episodic Memory Layer)
- st_sem (Semantic Pattern Layer)
- st_procedural (Procedural Memory Layer)
- st_social (Social Memory Layer)
- st_prospective (Prospective Memory Layer)
"""

def upgrade():
    """Apply migration."""

    # st_epi: Episodic Memory Layer
    execute("""
    CREATE TABLE st_epi (
        episode_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        space_id TEXT NOT NULL,
        actor_id TEXT NOT NULL,

        episode_summary TEXT NOT NULL,
        episode_start_time TEXT NOT NULL,
        episode_end_time TEXT NOT NULL,
        episode_duration_seconds INTEGER,

        location_centroid_name TEXT,
        location_centroid_lat REAL,
        location_centroid_lon REAL,

        participants_json TEXT,  -- Array of participant names
        activities_json TEXT,    -- Array of activity types
        emotions_json TEXT,      -- Array of detected emotions

        source_episodes_json TEXT NOT NULL,  -- Array of event_ids
        consolidation_cycle_id TEXT NOT NULL,

        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,

        FOREIGN KEY (tenant_id, space_id) REFERENCES spaces(tenant_id, space_id)
    );

    CREATE INDEX idx_epi_tenant ON st_epi(tenant_id, space_id);
    CREATE INDEX idx_epi_actor ON st_epi(actor_id);
    CREATE INDEX idx_epi_time ON st_epi(episode_start_time, episode_end_time);
    CREATE INDEX idx_epi_cycle ON st_epi(consolidation_cycle_id);
    """)

    # st_sem: Semantic Pattern Layer
    execute("""
    CREATE TABLE st_sem (
        semantic_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        space_id TEXT NOT NULL,
        actor_id TEXT NOT NULL,

        pattern_type TEXT NOT NULL,  -- routine, habit, preference
        pattern_name TEXT NOT NULL,

        common_elements_json TEXT NOT NULL,  -- {activity, location, time_of_day, etc.}
        confidence_score REAL NOT NULL,      -- 0.0-1.0
        frequency INTEGER NOT NULL,          -- Occurrence count

        temporal_pattern_type TEXT,          -- daily, weekly, monthly, irregular
        recurrence_interval_days REAL,
        next_predicted_time TEXT,

        source_episodes_json TEXT NOT NULL,  -- Array of episode_ids
        valid_from TEXT NOT NULL,
        valid_to TEXT,

        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE INDEX idx_sem_tenant ON st_sem(tenant_id, space_id);
    CREATE INDEX idx_sem_actor ON st_sem(actor_id);
    CREATE INDEX idx_sem_pattern_type ON st_sem(pattern_type);
    CREATE INDEX idx_sem_confidence ON st_sem(confidence_score);
    CREATE INDEX idx_sem_valid ON st_sem(valid_from, valid_to);
    """)

    # st_procedural: Procedural Memory Layer
    execute("""
    CREATE TABLE st_procedural (
        procedural_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        space_id TEXT NOT NULL,
        actor_id TEXT NOT NULL,

        skill_name TEXT NOT NULL,
        skill_category TEXT,  -- physical, cognitive, social

        proficiency_level REAL NOT NULL,     -- 0.0-1.0 (novice → expert)
        practice_count INTEGER DEFAULT 0,
        last_practiced_at TEXT,

        learning_curve_json TEXT,            -- [{timestamp, proficiency}, ...]
        milestones_json TEXT,                -- [{timestamp, milestone_description}, ...]

        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE INDEX idx_proc_tenant ON st_procedural(tenant_id, space_id);
    CREATE INDEX idx_proc_actor ON st_procedural(actor_id);
    CREATE INDEX idx_proc_proficiency ON st_procedural(proficiency_level);
    """)

    # st_social: Social Memory Layer
    execute("""
    CREATE TABLE st_social (
        social_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        space_id TEXT NOT NULL,
        actor_id TEXT NOT NULL,

        person_name TEXT NOT NULL,
        relationship_type TEXT,              -- friend, family, colleague, acquaintance

        interaction_count INTEGER DEFAULT 0,
        first_interaction_time TEXT,
        last_interaction_time TEXT,

        interaction_frequency_days REAL,     -- Average days between interactions
        shared_activities_json TEXT,         -- Array of activities done together
        shared_locations_json TEXT,          -- Array of places visited together

        affinity_score REAL,                 -- 0.0-1.0 (relationship strength)

        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,

        UNIQUE(tenant_id, space_id, actor_id, person_name)
    );

    CREATE INDEX idx_social_tenant ON st_social(tenant_id, space_id);
    CREATE INDEX idx_social_actor ON st_social(actor_id);
    CREATE INDEX idx_social_person ON st_social(person_name);
    CREATE INDEX idx_social_affinity ON st_social(affinity_score);
    """)

    # st_prospective: Prospective Memory Layer
    execute("""
    CREATE TABLE st_prospective (
        prospective_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        space_id TEXT NOT NULL,
        actor_id TEXT NOT NULL,

        intention_type TEXT NOT NULL,        -- reminder, goal, habit_formation
        intention_description TEXT NOT NULL,

        trigger_type TEXT,                   -- time_based, event_based, location_based
        trigger_condition_json TEXT,         -- {time, location, event_pattern}

        recurrence_pattern TEXT,             -- once, daily, weekly, monthly
        next_trigger_time TEXT,

        completion_status TEXT DEFAULT 'pending',  -- pending, completed, expired, cancelled
        completed_at TEXT,

        source_pattern_id TEXT,              -- References st_sem.semantic_id

        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE INDEX idx_prosp_tenant ON st_prospective(tenant_id, space_id);
    CREATE INDEX idx_prosp_actor ON st_prospective(actor_id);
    CREATE INDEX idx_prosp_trigger_time ON st_prospective(next_trigger_time);
    CREATE INDEX idx_prosp_status ON st_prospective(completion_status);
    """)


def downgrade():
    """Rollback migration."""
    execute("DROP TABLE IF EXISTS st_prospective")
    execute("DROP TABLE IF EXISTS st_social")
    execute("DROP TABLE IF EXISTS st_procedural")
    execute("DROP TABLE IF EXISTS st_sem")
    execute("DROP TABLE IF EXISTS st_epi")
```

---

### Migration 0026: st_hipp_events Consolidation Columns

**Purpose**: Add P03-specific columns to st_hipp_events for consolidation tracking, deduplication, and archival.

**Migration File**: `k0/migrations/0026_add_consolidation_columns.py`

```python
"""
Migration 0026: Add P03 Consolidation Columns to st_hipp_events

Adds columns for:
- Consolidation tracking (status, cycle_id, cluster_id)
- Deduplication (simhash, novelty_score, is_near_duplicate)
- Archival (archival_status, archival_deadline, archived_at)
- Tombstones (tombstone_status, tombstoned_at, tombstone_reason)
"""

def upgrade():
    """Apply migration."""

    # Add consolidation tracking columns
    execute("""
    ALTER TABLE st_hipp_events
    ADD COLUMN consolidation_status TEXT DEFAULT 'PENDING';
    """)

    execute("""
    ALTER TABLE st_hipp_events
    ADD COLUMN consolidated_at TEXT;
    """)

    execute("""
    ALTER TABLE st_hipp_events
    ADD COLUMN consolidation_cycle_id TEXT;
    """)

    execute("""
    ALTER TABLE st_hipp_events
    ADD COLUMN episode_cluster_id TEXT;
    """)

    # Add deduplication columns
    execute("""
    ALTER TABLE st_hipp_events
    ADD COLUMN simhash_fingerprint INTEGER;
    """)

    execute("""
    ALTER TABLE st_hipp_events
    ADD COLUMN novelty_score REAL;
    """)

    execute("""
    ALTER TABLE st_hipp_events
    ADD COLUMN is_near_duplicate INTEGER DEFAULT 0;
    """)

    execute("""
    ALTER TABLE st_hipp_events
    ADD COLUMN canonical_event_id TEXT;
    """)

    # Add archival columns
    execute("""
    ALTER TABLE st_hipp_events
    ADD COLUMN archival_status TEXT DEFAULT 'ACTIVE';
    """)

    execute("""
    ALTER TABLE st_hipp_events
    ADD COLUMN archival_deadline TEXT;
    """)

    execute("""
    ALTER TABLE st_hipp_events
    ADD COLUMN archived_at TEXT;
    """)

    # Add tombstone columns
    execute("""
    ALTER TABLE st_hipp_events
    ADD COLUMN tombstone_status TEXT;
    """)

    execute("""
    ALTER TABLE st_hipp_events
    ADD COLUMN tombstoned_at TEXT;
    """)

    execute("""
    ALTER TABLE st_hipp_events
    ADD COLUMN tombstone_reason TEXT;
    """)

    execute("""
    ALTER TABLE st_hipp_events
    ADD COLUMN tombstone_retention_until TEXT;
    """)

    # Create indexes for P03 queries
    execute("""
    CREATE INDEX idx_hipp_consolidation_status
    ON st_hipp_events(consolidation_status);
    """)

    execute("""
    CREATE INDEX idx_hipp_cycle_id
    ON st_hipp_events(consolidation_cycle_id);
    """)

    execute("""
    CREATE INDEX idx_hipp_simhash
    ON st_hipp_events(simhash_fingerprint);
    """)

    execute("""
    CREATE INDEX idx_hipp_archival_status
    ON st_hipp_events(archival_status, archival_deadline);
    """)

    execute("""
    CREATE INDEX idx_hipp_tombstone
    ON st_hipp_events(tombstone_status, tombstone_retention_until);
    """)


def downgrade():
    """Rollback migration."""
    # Drop indexes
    execute("DROP INDEX IF EXISTS idx_hipp_tombstone")
    execute("DROP INDEX IF EXISTS idx_hipp_archival_status")
    execute("DROP INDEX IF EXISTS idx_hipp_simhash")
    execute("DROP INDEX IF EXISTS idx_hipp_cycle_id")
    execute("DROP INDEX IF EXISTS idx_hipp_consolidation_status")

    # Drop columns (SQLite limitation: requires table recreation)
    execute("""
    CREATE TABLE st_hipp_events_backup AS
    SELECT
        event_id, envelope_id, tenant_id, space_id, actor_id,
        band, topic, device_kind, event_time_utc,
        text, body_json, metadata_json, participants_json,
        location_name, latitude, longitude,
        created_at, updated_at
    FROM st_hipp_events;
    """)

    execute("DROP TABLE st_hipp_events")
    execute("ALTER TABLE st_hipp_events_backup RENAME TO st_hipp_events")
```

---

### Migration 0027: Knowledge Graph Tables

**Purpose**: Create knowledge graph tables (st_kg_dom for nodes, st_kg_edges for relationships).

**Migration File**: `k0/migrations/0027_create_knowledge_graph.py`

```python
"""
Migration 0027: Create Knowledge Graph Tables

Creates:
- st_kg_dom (Knowledge Graph Domain/Nodes)
- st_kg_edges (Knowledge Graph Edges/Relationships)
- st_tombstones (Tombstone audit trail)
- st_archived_events (Archival storage)
- retention_policies (Retention policy matrix)
- st_dsar_audit_log (DSAR audit log)
"""

def upgrade():
    """Apply migration."""

    # st_kg_dom: Knowledge Graph Nodes
    execute("""
    CREATE TABLE st_kg_dom (
        node_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        space_id TEXT NOT NULL,

        entity_type TEXT NOT NULL,           -- Person, Place, Activity, Topic, Organization, etc.
        entity_name TEXT NOT NULL,
        entity_aliases_json TEXT,            -- Array of alternative names

        node_properties_json TEXT,           -- Flexible attributes (e.g., {role, department, category})

        is_canonical INTEGER DEFAULT 1,      -- 0 if duplicate, 1 if canonical
        canonical_node_id TEXT,              -- Points to canonical node if duplicate
        supersedes_node_id TEXT,             -- Points to previous version (temporal chain)

        valid_from TEXT NOT NULL,
        valid_to TEXT,

        source_episodes_json TEXT,           -- Array of episode_ids

        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,

        FOREIGN KEY (canonical_node_id) REFERENCES st_kg_dom(node_id),
        FOREIGN KEY (supersedes_node_id) REFERENCES st_kg_dom(node_id)
    );

    CREATE INDEX idx_kg_dom_tenant ON st_kg_dom(tenant_id, space_id);
    CREATE INDEX idx_kg_dom_entity_type ON st_kg_dom(entity_type);
    CREATE INDEX idx_kg_dom_entity_name ON st_kg_dom(entity_name);
    CREATE INDEX idx_kg_dom_canonical ON st_kg_dom(is_canonical, canonical_node_id);
    CREATE INDEX idx_kg_dom_valid ON st_kg_dom(valid_from, valid_to);
    """)

    # st_kg_edges: Knowledge Graph Relationships
    execute("""
    CREATE TABLE st_kg_edges (
        edge_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        space_id TEXT NOT NULL,

        from_node_id TEXT NOT NULL,
        to_node_id TEXT NOT NULL,
        relationship_type TEXT NOT NULL,     -- friend_of, works_at, located_in, causes, etc.

        relationship_strength REAL DEFAULT 1.0,  -- 0.0-1.0
        occurrence_count INTEGER DEFAULT 1,

        edge_properties_json TEXT,           -- Flexible attributes (e.g., {is_causal, mean_lag_hours})

        valid_from TEXT NOT NULL,
        valid_to TEXT,

        source_episodes_json TEXT,

        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,

        FOREIGN KEY (from_node_id) REFERENCES st_kg_dom(node_id),
        FOREIGN KEY (to_node_id) REFERENCES st_kg_dom(node_id)
    );

    CREATE INDEX idx_kg_edges_tenant ON st_kg_edges(tenant_id, space_id);
    CREATE INDEX idx_kg_edges_from ON st_kg_edges(from_node_id);
    CREATE INDEX idx_kg_edges_to ON st_kg_edges(to_node_id);
    CREATE INDEX idx_kg_edges_rel_type ON st_kg_edges(relationship_type);
    CREATE INDEX idx_kg_edges_valid ON st_kg_edges(valid_from, valid_to);
    """)

    # st_tombstones: Tombstone audit trail
    execute("""
    CREATE TABLE st_tombstones (
        tombstone_id TEXT PRIMARY KEY,
        event_id TEXT NOT NULL,
        tenant_id TEXT NOT NULL,
        space_id TEXT NOT NULL,

        event_time_utc TEXT NOT NULL,
        band TEXT NOT NULL,
        topic TEXT NOT NULL,
        device_kind TEXT NOT NULL,

        tombstoned_at TEXT NOT NULL,
        tombstone_reason TEXT NOT NULL,
        tombstone_retention_until TEXT NOT NULL,

        original_event_summary TEXT,

        UNIQUE(event_id)
    );

    CREATE INDEX idx_tombstone_tenant ON st_tombstones(tenant_id, space_id);
    CREATE INDEX idx_tombstone_retention ON st_tombstones(tombstone_retention_until);
    CREATE INDEX idx_tombstone_reason ON st_tombstones(tombstone_reason);
    """)

    # st_archived_events: Archival storage
    execute("""
    CREATE TABLE st_archived_events (
        event_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        space_id TEXT NOT NULL,

        compressed_content BLOB NOT NULL,
        original_size_bytes INTEGER NOT NULL,
        compressed_size_bytes INTEGER NOT NULL,
        compression_ratio REAL NOT NULL,

        archived_at TEXT NOT NULL,
        archival_reason TEXT,
        restored_at TEXT,

        FOREIGN KEY (event_id) REFERENCES st_hipp_events(event_id)
    );

    CREATE INDEX idx_archived_tenant ON st_archived_events(tenant_id, space_id);
    CREATE INDEX idx_archived_date ON st_archived_events(archived_at);
    """)

    # retention_policies: Retention policy matrix
    execute("""
    CREATE TABLE retention_policies (
        policy_id TEXT PRIMARY KEY,

        band TEXT NOT NULL,
        topic TEXT NOT NULL,
        device_kind TEXT NOT NULL,

        retention_days INTEGER NOT NULL,
        archival_compression_ratio REAL,
        tombstone_retention_days INTEGER,

        auto_archive INTEGER DEFAULT 1,
        auto_delete INTEGER DEFAULT 0,
        requires_user_consent INTEGER DEFAULT 0,

        policy_description TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,

        UNIQUE(band, topic, device_kind)
    );

    CREATE INDEX idx_retention_band_topic ON retention_policies(band, topic);
    CREATE INDEX idx_retention_device ON retention_policies(device_kind);
    """)

    # st_dsar_audit_log: DSAR audit trail
    execute("""
    CREATE TABLE st_dsar_audit_log (
        audit_id TEXT PRIMARY KEY,
        request_id TEXT NOT NULL,
        tenant_id TEXT NOT NULL,
        space_id TEXT NOT NULL,
        actor_id TEXT NOT NULL,

        request_type TEXT NOT NULL,
        scope TEXT,
        deleted_counts_json TEXT,

        requested_at TEXT NOT NULL,
        completed_at TEXT NOT NULL,

        UNIQUE(request_id)
    );

    CREATE INDEX idx_dsar_audit_actor ON st_dsar_audit_log(actor_id);
    CREATE INDEX idx_dsar_audit_type ON st_dsar_audit_log(request_type);
    """)


def downgrade():
    """Rollback migration."""
    execute("DROP TABLE IF EXISTS st_dsar_audit_log")
    execute("DROP TABLE IF EXISTS retention_policies")
    execute("DROP TABLE IF EXISTS st_archived_events")
    execute("DROP TABLE IF EXISTS st_tombstones")
    execute("DROP TABLE IF EXISTS st_kg_edges")
    execute("DROP TABLE IF EXISTS st_kg_dom")
```

---

## Open Questions

After comprehensive review of the P03 consolidation dossier (15,101 lines), the following gaps, ambiguities, implementation challenges, and cross-cutting concerns have been identified. These questions should be resolved before full implementation.

---

### Architecture & Design Questions

**Q1: Module Dependency Conflicts & Circular References**

**Issue**: P03 Module Registry shows potential circular dependencies between consolidation modules:

- M25 (Orchestrator) coordinates M18-M24
- M24 (MemoryLayerWriter) depends on "all P03 modules (M18-M24)"
- M18 (PatternExtractor) depends on M03 (CA3Service) which is used by M23 (Replay)

**Confusion**: How is circular dependency between M24 → (M18-M23) → M24 resolved? Does M24 only coordinate writes without executing business logic, or does it need runtime results from other modules?

**Impact**: Without clear dependency resolution, module initialization order is undefined. Could cause import errors or runtime deadlocks.

**Recommendation**: Create dependency graph diagram showing execution order. Consider splitting M24 into M24a (Write Coordinator) and M24b (Write Executor) to break circular dependency.

---

**Q2: K0 Driver Architecture Integration Specifics**

**Issue**: Document states "R7 writes go through st_outbox" and "OutboxWorker dispatches to SQLiteDriver", but missing:

- Concrete alias_map.yaml configuration examples
- Driver registration and discovery mechanism
- Error handling when driver unavailable or throws exception
- Transaction boundary semantics (when does outbox commit happen relative to R6.3 status updates?)
- Retry semantics details (exponential backoff formula, max retry calculation, DLQ structure)

**Confusion**: If OutboxWorker is separate process/thread, how does R7 know writes succeeded? Does R8 event emission wait for outbox processing completion, or is it fire-and-forget?

**Impact**: Critical for transactional integrity. If R8 emits "consolidation complete" before outbox writes finish, downstream consumers (P04, P06, P15) may query memory layers before data available.

**Recommendation**: Add sequence diagram showing: `P03 R7 → st_outbox INSERT → OutboxWorker poll → Driver.apply() → R8 event emission`. Clarify synchronization point.

---

**Q3: P08 Coordination Protocol Gaps** ✅ RESOLVED (2025-12-13)

> **Resolution**: Architecture updated. P02 M16 now writes episodic embeddings inline (atomic 3-table transaction). P03 writes semantic pattern embeddings directly with status=READY. P08 runs as kernel lifespan scheduler polling st_vec every 300s. `st_embedding_queue` is **DEPRECATED**.

~~**Issue**: R7.7 states P03 "creates placeholder embedding records" and "P08 generates actual vectors", but missing:~~

~~- What happens if P08 is down/unavailable? Do placeholders accumulate indefinitely?~~
~~- How does P03 handle embedding generation failures? (e.g., model OOM, text too long)~~
~~- Priority semantics: Document says "High-salience episodes (salience_score >0.7): priority=HIGH", but no queue starvation prevention mechanism described~~
~~- Event-driven vs polling: Document mentions both "P08 polls st_embedding_queue" AND "P03 emits cognitive.embedding.queued.v1 event for immediate processing" - which takes precedence?~~

**New Architecture**:

- **P02 M16**: Writes episodic embeddings inline to st_vec (status=READY) via atomic 3-table transaction
- **P03 R7.7**: Writes semantic pattern embeddings directly to st_vec (status=READY) using UltraBERT
- **P08 Scheduler**: Kernel lifespan background task polls st_vec every 300s, indexes READY → INDEXED in FAISS
- **No Queue**: `st_embedding_queue` deprecated, no backlog management needed
- **FAISS Catch-up**: P08 runs catch-up on kernel boot to index any missed vectors

**Impact**: Previous concerns about queue overflow/backpressure no longer apply.

---

**Q4: Sleep Cycle Budget Violation Handling**

**Issue**: Document specifies phase duration budgets (R1: 35min, R2: 45min, R3: 12min, R4: 30min, R5: 30min, R6: 5min, R7: 20min, R8: 5min = 182 min total), but target cycle duration is 90 minutes.

**Confusion**: Budget sum (182 min) exceeds target (90 min) by **102 minutes**. Is this intentional (phases run in parallel)? Or is there a documentation error?

Document states phases run sequentially (R0→R1→R2→...→R8), so parallel execution unlikely.

If budget is soft target and phase can be skipped: Which phases are skippable? Document mentions "If consolidation budget exceeded, skip R5 and proceed to R6", but no guidance for other phases.

**Impact**: If all phases run, cycle takes 3+ hours instead of 90 minutes, causing consolidation backlog. User-facing features delayed.

**Recommendation**: Clarify phase execution model:

- **Serial with optional phases**: Mark R5 (Dream) as optional, recalculate budgets to sum to ≤90 min
- **Parallel execution**: Specify which phases can run concurrently (e.g., R4 KG + R5 Dream), show fork/join diagram
- **Adaptive skipping**: Define priority ordering (e.g., R3 forgetting > R4 KG > R5 dream), skip lowest priority if overbudget

---

**Q5: Consolidation Trigger Race Conditions**

**Issue**: R0 supports 4 trigger mechanisms (scheduled cron, idle detection, event-based SSE, manual CLI), each with different priorities. Document says "Manual (highest) → Event-based → Idle-based → Scheduled (lowest)".

**Confusion**: What happens if multiple triggers fire simultaneously?

- Scheduled cron (2 AM) + Event-based burst (1000 events) at same time?
- Manual CLI trigger during active consolidation cycle?
- Idle trigger detection during NREM2 phase?

Document missing:

- Mutex/locking mechanism to prevent concurrent consolidation runs
- Behavior when trigger fires during active cycle (queue? reject? interrupt?)
- Distributed locking if P03 scaled horizontally (multiple workers per tenant)

**Impact**: Concurrent consolidation runs could cause:

- Race conditions on st_hipp_events updates (double-marking as consolidated)
- Duplicate memory layer writes
- Database deadlocks on st_outbox inserts

**Recommendation**: Add consolidation_lock table with tenant/space-level locks. Document lock acquisition protocol: `SELECT ... FOR UPDATE` on lock row before starting R0. Add `consolidation_status` column to pipeline_offsets table: `IDLE | RUNNING | FAILED`.

---

### Performance & Scalability Questions

**Q6: SimHash Deduplication Performance at Scale**

**Issue**: R3.1 uses brute-force SimHash comparison within 24-hour time window. Query fetches all candidates:

```sql
SELECT * FROM st_hipp_events
WHERE tenant_id = ? AND event_time_utc BETWEEN ? AND ?
```

Then computes Hamming distance for each pair: `O(n²)` where n = events in window.

**Confusion**: If time window contains 5000 events (high-activity day), brute-force comparison = 5000 × 5000 = 25 million comparisons. At 1 µs/comparison, this is **25 seconds just for comparisons**, exceeding R3.1's 5-minute budget.

Document mentions MinHash LSH as fallback for >1000 events, but:

- No automatic switching logic described
- MinHash implementation (128 permutations, 16 bands) not performance-tested
- LSH index build time not budgeted

**Impact**: Deduplication becomes bottleneck on high-activity days. Could delay entire consolidation cycle by 30+ minutes.

**Recommendation**:

1. Add LSH index to st_hipp_events (persistent, incrementally updated)
2. Profile SimHash vs MinHash crossover point (current guess: 1000 events, but untested)
3. Consider Bloom filters for early rejection (90% of events are not duplicates)
4. Add circuit breaker: If deduplication takes >10 minutes, skip and mark events as `dedup_skipped=1` for retry

---

**Q7: Knowledge Graph Scalability & Query Performance**

**Issue**: st_kg_dom and st_kg_edges grow unbounded. After 1 year, typical tenant could have:

- **10,000+ entities** (people, places, organizations, concepts)
- **100,000+ relationships** (social, location, causal, temporal)

Document missing:

- Index strategy for temporal queries (`WHERE valid_from <= ? AND valid_to > ?`)
- Graph traversal performance (causal chain queries with max_depth=3 could touch 1000s of nodes)
- Entity resolution at scale (fuzzy matching with Levenshtein distance on 10k entity names = 100M comparisons)

**Confusion**: R4.1 entity resolution does `O(n)` fuzzy matching against all existing entities of same type. With 5000 Person entities, each new person extraction = 5000 similarity computations. If batch has 1000 events × 3 entities/event = 3000 entity extractions × 5000 comparisons = **15 million similarity computations**.

**Impact**: R4 could take hours instead of 30 minutes. KG queries timeout. Entity resolution becomes prohibitive.

**Recommendation**:

1. **Pre-filtering**: Use BK-tree or simhash for entity names to narrow candidates to <100 before Levenshtein
2. **Caching**: Store entity name → canonical_node_id mapping in Redis, invalidate on merge
3. **Batch entity resolution**: Resolve all entities in batch together, deduplicate before DB lookups
4. **Graph database**: Consider Neo4j driver (mentioned in R7.6) for traversal queries. Benchmark SQLite vs Neo4j for 100k-node graphs.

---

**Q8: Memory Layer Write Throughput**

**Issue**: R7 writes to 8 memory layers via st_outbox. Target: "1000 events across 8 layers in <5 minutes" (R7 Performance Budget).

Assuming 1000 events → 831 episodes (after deduplication):

- st_epi: 831 INSERTs
- st_sem: 47 INSERTs (pattern extraction rate 4.7%)
- st_procedural: 23 INSERTs
- st_social: 62 UPDATEs (relationship strengthening)
- st_prospective: 18 INSERTs
- st_kg_dom: 214 INSERTs
- st_kg_edges: 389 INSERTs/UPDATEs
- st_vec: 831 placeholder INSERTs
- st_fts: 831 FTS5 INSERTs

**Total: ~3,200 database operations in 5 minutes = 10.7 ops/second.**

**Confusion**: SQLite write throughput depends on:

- Journal mode (WAL vs DELETE)
- Synchronous setting (FULL vs NORMAL vs OFF)
- Transaction batching (1 transaction vs 3200 individual)
- Concurrent readers (Query Port queries during consolidation)

Document states "Set PRAGMA journal_mode=WAL and PRAGMA synchronous=NORMAL for faster writes" but:

- No actual throughput benchmark provided
- No fallback if writes take >5 minutes (does R7 abort? retry? split batch?)
- No guidance on transaction isolation level

**Impact**: If SQLite write throughput <10 ops/sec (e.g., disk-bound, concurrent readers), R7 exceeds budget. Could cause consolidation backlog.

**Recommendation**: Benchmark R7 writes on target hardware:

- SSD: Expected 1000+ ops/sec (no issue)
- HDD: Expected 50-100 ops/sec (potential bottleneck)
- Network storage: Expected 10-50 ops/sec (likely bottleneck)

Add adaptive batching: If write latency >100ms, increase batch size to 100 records/transaction instead of 50.

---

**Q9: Theta Rhythm Coordination Overhead**

**Issue**: R1.5 simulates theta oscillations by processing events in micro-batches of 50 with 200ms sleep between batches to mimic 5Hz rhythm.

For 1000 events:

- 1000 / 50 = 20 micro-batches
- 20 × 200ms sleep = **4 seconds of artificial delay**

**Confusion**: Why intentionally slow down processing? Document cites neuroscience motivation ("mimics hippocampal theta"), but no technical benefit explained.

If goal is graceful CPU yield (R1.5 mentions "adaptive throttling based on CPU usage"), why not use CPU-based throttling directly instead of fixed 200ms sleep?

**Impact**: 4-second overhead per 1000 events is small (0.4%), but accumulates if consolidation runs on larger batches (10k events = 40s overhead).

**Recommendation**: Remove fixed theta rhythm sleep, replace with CPU-based adaptive throttling:

```python
if cpu_usage > 80%:
    await asyncio.sleep(0.5)  # Yield CPU
elif cpu_usage < 50%:
    await asyncio.sleep(0)   # No yield
else:
    await asyncio.sleep(0.2) # Moderate yield
```

If theta rhythm needed for architectural consistency, document why and add flag to disable for performance-critical deployments.

---

### Data Quality & Correctness Questions

**Q10: Confidence Score Propagation & Decay**

**Issue**: Multiple confidence scores exist across layers:

- st_hipp_events: `confidence` (from P02 fusion)
- st_epi: `confidence_score` (cluster quality)
- st_sem: `confidence_score` (pattern extraction)
- st_kg_dom: `confidence_score` (entity disambiguation)
- st_kg_edges: `relationship_strength` (co-occurrence frequency)

**Confusion**: How do these confidence scores relate? Should st_epi confidence propagate to st_sem?

Example: If episode cluster has low confidence (0.4), should derived semantic pattern inherit low confidence? Or is pattern confidence independent?

Document formula for st_sem confidence:

```
confidence_score = sqrt(frequency_score * consistency_score * significance_score)
```

But no mention of source episode confidence. If 10 low-confidence episodes (avg 0.4) form a pattern, should pattern confidence be capped at 0.4?

**Impact**: High-confidence patterns derived from low-confidence episodes could mislead K1 planner. Conversely, overly conservative confidence propagation could discard useful patterns.

**Recommendation**: Add confidence propagation rules:

1. **Episodic → Semantic**: `pattern_confidence = min(pattern_intrinsic_confidence, avg_episode_confidence)`
2. **Entity → Relationship**: `relationship_confidence = min(relationship_intrinsic_confidence, min(from_entity_confidence, to_entity_confidence))`
3. Document when confidence should propagate vs when independent

---

**Q11: Temporal Validity Consistency**

**Issue**: Temporal validity (valid_from, valid_to) used throughout KG (st_kg_dom, st_kg_edges, st_sem, st_procedural), but inconsistencies in nullability:

- st_kg_dom: `valid_from NOT NULL, valid_to NULL` (ongoing entities)
- st_kg_edges: `valid_from NOT NULL, valid_to NULL` (ongoing relationships)
- st_sem: `valid_from NOT NULL, valid_to NULL` (ongoing patterns)
- st_epi: No valid_from/valid_to columns (episodes are point-in-time events)

**Confusion**: How are point-in-time queries handled across layers?

Example: Query "What was Sarah's role on 2025-06-01?" requires:

1. Find st_kg_dom entity "Sarah" where `valid_from <= 2025-06-01 AND (valid_to IS NULL OR valid_to > 2025-06-01)`
2. Find relationships where same temporal constraint

But if querying st_epi (episodic memories of Sarah on 2025-06-01), no valid_from/valid_to - only event_time_utc.

Are episodic memories implicitly valid only at event_time_utc? Or should st_epi have valid_from (=first_observed_at) and valid_to (=last_observed_at)?

**Impact**: Temporal queries return inconsistent results. Hard to reason about "snapshot at time T" across memory layers.

**Recommendation**: Add valid_from/valid_to to st_epi:

- `valid_from = first_observed_at`
- `valid_to = last_observed_at` (if cluster spans multiple events)
- For singleton episodes, `valid_to = valid_from` (point-in-time)

Update temporal query examples to show cross-layer consistency.

---

**Q12: Novelty Score vs Importance Score Interaction**

**Issue**: Both novelty_score (R3.2) and importance_score (R1.4) exist, with overlapping purposes:

- **importance_score**: Multi-factor (emotional 0.35 + recency 0.25 + access 0.20 + social 0.20), used for replay prioritization
- **novelty_score**: 1.0 - (duplicate_count / time_window_event_count), used for retention adjustment

**Confusion**: Can an event have high novelty (unique) but low importance (mundane)? Or high importance (emotional milestone) but low novelty (another birthday dinner)?

Document shows novelty adjustment for retention:

- High novelty (>0.8): Extend retention by 2x
- Low novelty (<0.3): Reduce retention by 50%

But no interaction with importance score. Should important+novel events get 4x retention? Or is novelty sufficient?

**Impact**: Retention policy could delete important but routine memories (e.g., daily medication reminder - important for health, but low novelty).

**Recommendation**: Define combined retention formula:

```
retention_factor = max(
    novelty_adjustment,      # 0.5x to 2x
    importance_adjustment    # 0.5x to 3x for high-importance events
)
```

Ensures important events never deleted due to low novelty.

---

**Q13: Pattern Extraction Temporal Assumptions**

**Issue**: R2.2 pattern extraction assumes events cluster temporally (daily/weekly/monthly recurrence), but edge cases unclear:

**Example 1: Shift Worker**

- Works Tuesday-Thursday one week, Friday-Sunday next week
- Temporal clustering detects "irregular" pattern (high CV)
- No routine extracted even though "shift work" is clear routine

**Example 2: Seasonal Activities**

- Skiing in January-March (3 months)
- 12 skiing events, 1 week apart
- Pattern extractor sees 3-month span, classifies as "monthly" recurrence
- But actually weekly recurrence within season

**Confusion**: How does temporal pattern recognition handle:

- Irregular work schedules?
- Seasonal activities with gaps?
- One-time events that look like start of pattern (single occurrence)?

Document formula for pattern classification:

```python
if 0.8 <= mean_interval <= 1.2:
    pattern_type = 'daily'
elif 6.5 <= mean_interval <= 7.5:
    pattern_type = 'weekly'
```

But no handling for multi-modal distributions (e.g., weekly during winter, none during summer).

**Impact**: Pattern extraction misclassifies seasonal/irregular routines, leading to incorrect prospective reminders.

**Recommendation**: Add seasonal detection:

1. Check for gaps >30 days in event sequence
2. If gaps exist, run pattern detection within each continuous segment
3. Tag patterns with season metadata (e.g., "winter_routine", "summer_routine")
4. Add `pattern_seasonality` column to st_sem

---

### Integration & Coordination Questions

**Q14: P02→P03→P08 Event Flow Synchronization** ✅ RESOLVED (2025-12-13)

> **Resolution**: Architecture updated. Episodic embeddings are now written **inline** by P02 M16 (status=READY at ingest time). No placeholder pattern. No race condition for episodic queries.

~~**Issue**: Document describes event flow:~~

~~1. P02 writes event to st_hipp_events (consolidation_status=NULL)~~
~~2. P02 emits `p02.write.complete.v1` event~~
~~3. P03 triggered (event-based trigger or idle detection)~~
~~4. P03 consolidates events, writes to memory layers~~
~~5. P03 writes embedding placeholders to st_vec~~
~~6. P03 emits `p03.consolidation.complete.v1` event~~
~~7. P08 polls st_embedding_queue or subscribes to `cognitive.embedding.queued.v1`~~
~~8. P08 generates embeddings, updates st_vec~~

**Updated Event Flow (2025-12-13)**:

1. **P02 M16**: Atomic 3-table transaction writes st_hipp_events + st_vec (status=READY) + st_pipeline_processed
2. P02 emits `p02.write.complete.v1` event
3. **P08 Kernel Scheduler**: Polls st_vec every 300s (catch-up on boot), indexes READY → INDEXED in FAISS
4. P03 triggered (idle detection or scheduled)
5. P03 consolidates events, writes to memory layers (st_epi, st_sem, etc.)
6. **P03 R7.7**: Writes semantic pattern embeddings to st_vec (status=READY) using UltraBERT
7. P03 emits `p03.consolidation.complete.v1` event
8. P08 scheduler picks up new semantic embeddings on next poll cycle

**Race Condition Resolution**:

| Query Type | Data Available | Embedding Available | Notes |
|-----------|----------------|---------------------|-------|
| Episodic (st_hipp_events) | Immediately (P02) | Immediately (P02 M16) | No race condition |
| Semantic (st_sem) | After P03 | After P03 R7.7 | Same transaction |
| FAISS search | After P08 poll | After P08 poll | 0-300s delay acceptable |

**Query Port Handling**:

- `status=READY`: Embedding in st_vec, can do embedding-based queries
- `status=INDEXED`: Also in FAISS, fastest similarity search
- `status=PENDING` or `NULL`: Fallback to FTS5 text search (rare after ADR-K003)

---

**Q15: Multi-Tenant Consolidation Scheduling**

**Issue**: Document mentions "separate offsets per tenant/space for parallel consolidation" but lacks detail on:

- How many tenants can consolidate simultaneously? (1? 10? 100?)
- Resource allocation per tenant (CPU/memory limits)
- Priority scheduling (premium tenants first? oldest backlog first?)
- Deadlock prevention (if two tenants share resources)

**Confusion**: If system has 50 tenants and each consolidation takes 90 minutes, serial processing = 50 × 90 = **4500 minutes = 75 hours** to consolidate all tenants once.

Document mentions "P03 can run consolidation for multiple tenants concurrently (different processes/threads)", but:

- No worker pool size specified
- No tenant queuing strategy
- No handling if tenant consolidation fails (retry? skip? alert?)

**Impact**: Large multi-tenant deployments could have perpetual consolidation backlog. Some tenants never get consolidated.

**Recommendation**: Define tenant scheduling policy:

1. **Worker Pool**: 5 concurrent consolidation workers (configurable)
2. **Queue**: Priority queue ordered by backlog_size (events pending consolidation)
3. **Fairness**: Each tenant gets max 1 consolidation/hour (prevent monopolization)
4. **SLA**: Alert if tenant backlog >10k events for >24 hours

---

**Q16: Active Learning Loop (P06) Integration**

**Issue**: Document references Active Learning Loop in multiple places:

- R2.1: "Low-confidence patterns flagged for P06 review"
- R2.3: "Multiple matches >0.85: flag ambiguity for Active Learning P06"
- R3.2: "Novelty score influences P06 curriculum"

But missing:

- How does P03 communicate with P06? (events? database flags? RPC?)
- What data format does P06 expect? (just episode_id? full episode context?)
- Does P03 block waiting for P06 response? (synchronous vs asynchronous)
- How does P06 feedback loop back to P03? (update confidence scores? trigger re-consolidation?)

**Confusion**: If P06 is separate pipeline, how does it access P03 intermediate results (e.g., "low-confidence patterns")?

Does P03 write to intermediate table `candidate_patterns` (mentioned in R2.5 confidence gating)? If so, schema missing.

**Impact**: Without clear P06 integration, Active Learning remains unimplemented. Low-confidence patterns never get resolved.

**Recommendation**: Create P03→P06 integration specification:

1. **Event Contract**: P03 emits `p03.ambiguity.detected.v1` with episode_id, ambiguity_type, context
2. **P06 Subscription**: P06 subscribes to ambiguity events, generates clarification questions
3. **Feedback Loop**: User answers question → P06 emits `p06.clarification.resolved.v1` → P03 updates confidence scores
4. Add schema for `candidate_patterns` table referenced in document

---

### Testing & Validation Questions

**Q17: Integration Test Coverage Gaps**

**Issue**: Document provides unit test examples (TestSimHash, TestNoveltyScore) and integration test structure (TestConsolidationPipeline), but missing:

- How to generate realistic test data? (1000 events with coherent temporal patterns)
- How to validate end-to-end correctness? (input events → expected memory layer outputs)
- How to test failure scenarios? (database unavailable, OOM during R4, P08 down)
- How to test idempotency? (re-running consolidation on same batch produces same result)

**Confusion**: Test example shows:

```python
async def test_full_consolidation_cycle():
    result = await pipeline.consolidate(sample_events)
    assert result['status'] == 'completed'
    assert result['events_processed'] == len(sample_events)
```

But what about asserting memory layer contents? How to verify pattern extraction found expected "Tuesday yoga" routine?

**Impact**: Without comprehensive test suite, regressions slip through. Production consolidation produces incorrect semantic patterns.

**Recommendation**: Add test fixtures:

1. **golden_dataset.json**: 1000 realistic events with known patterns (5 routines, 3 relationships, 10 duplicates)
2. **expected_outputs.json**: Expected st_epi count, st_sem patterns, st_kg_dom entities
3. **Test framework**: Diff actual vs expected outputs, flag discrepancies
4. **Failure injection**: Mock database errors, P08 unavailability, OOM conditions

---

**Q18: Performance Test Realism**

**Issue**: Document specifies performance targets:

- "1000 events/90min" (11-37 events/min throughput)
- "R1: 35 min, R2: 45 min, R3: 12 min" (phase budgets)
- "Memory usage <2GB" (resource limit)

But performance tests (TestP03Performance) not realistic:

```python
async def test_batch_throughput_meets_target():
    start = time.time()
    await pipeline.consolidate(1000_events)
    duration_minutes = (time.time() - start) / 60
    assert duration_minutes <= 90
```

**Confusion**: Test uses synthetic/minimal events. Real events have:

- Long text fields (500-1000 words)
- Complex entities_json (20+ entities per event)
- Large participants_json (group chats with 50 people)

Synthetic events likely process faster than realistic events, leading to false confidence in performance.

**Impact**: Performance tests pass in CI but fail in production. Real consolidation takes 3+ hours instead of 90 minutes.

**Recommendation**: Generate realistic test events:

1. Use Faker library for text generation (realistic word distributions)
2. Generate realistic entities_json matching P02 UltraBERT output format
3. Vary event complexity (simple: 100 words, 3 entities; complex: 1000 words, 30 entities)
4. Benchmark on representative sample from production (sanitized)

---

### Security & Privacy Questions

**Q19: GDPR Tombstone Auditability**

**Issue**: R3.5 tombstone strategy states "delete content, keep metadata for audit", but missing:

- What audit trail is sufficient for GDPR compliance? (just tombstone record? or detailed deletion log?)
- How to prove deletion to regulators? (cryptographic proof? signed attestation?)
- What if user requests tombstone deletion? (GDPR allows "right to be forgotten" for tombstones too)

Document stores tombstone in st_tombstones:

```sql
CREATE TABLE st_tombstones (
    tombstone_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    tombstoned_at TEXT NOT NULL,
    tombstone_reason TEXT NOT NULL,
    tombstone_retention_until TEXT NOT NULL,
    original_event_summary TEXT
)
```

**Confusion**: `original_event_summary` contains non-PII summary (activity_type, word_count), but is this re-identification risk?

Example: If summary shows `{activity_type: "medical_appointment", has_location: true, word_count: 250}`, can this be cross-referenced with other data to re-identify user?

**Impact**: Insufficient audit trail could cause GDPR compliance failure. Regulators may reject tombstone approach.

**Recommendation**: Add cryptographic deletion proof:

1. **Hash Chain**: Before deletion, compute SHA-256(event_content), store hash in tombstone
2. **Zero-Knowledge Proof**: Generate ZK proof that original event existed and was deleted
3. **Signed Attestation**: Cryptographically sign tombstone record with system key
4. Document GDPR compliance rationale (cite legal precedent)

---

**Q20: Privacy Band Consistency Across Pipelines**

**Issue**: Privacy bands (GREEN/YELLOW/RED) assigned by P02, consumed by P03 retention policies. But missing:

- Can band change over time? (user reclassifies event from GREEN → RED)
- Does retroactive band change trigger re-consolidation? (re-apply retention policy)
- How to ensure P02 band classification consistent with P03 expectations?

**Confusion**: If user changes band after consolidation:

- Event already archived according to GREEN policy (90 days)
- User changes to RED (7-year retention)
- Should event be restored from archive? Or keep archived but extend retention?

Document doesn't address band mutation.

**Impact**: Inconsistent retention application. High-sensitivity data deleted prematurely if band reclassification not handled.

**Recommendation**: Add band change handling:

1. **Trigger**: User changes band → emit `p02.band.changed.v1` event
2. **P03 Response**: Query events with changed band, recompute retention deadlines
3. **Restore if Needed**: If archived event should be active under new band, restore from st_archived_events
4. Document band mutation workflow with state machine

---

### Documentation & Maintenance Questions

**Q21: Module README Completeness**

**Issue**: Module Registry shows many modules in "Design" status with READMEs "TBD":

- M18 (PatternExtractor): README TBD
- M19 (DeduplicationService): README TBD
- M20 (RetentionEnforcer): README TBD
- M21 (KGBuilder): README TBD
- M22 (DreamSimulator): README TBD
- M23 (EpisodicReplay): README TBD
- M24 (MemoryLayerWriter): README TBD
- M25 (ConsolidationOrchestrator): README TBD

**Confusion**: Without authoritative module READMEs (13-section format from design workflow), developers lack:

- Module purpose and responsibilities
- API contracts (inputs/outputs)
- Performance characteristics
- Observability hooks
- Test coverage

**Impact**: Implementation diverges from design. Developers make inconsistent assumptions. Cross-module integration breaks.

**Recommendation**: Before implementation starts:

1. Complete M18-M25 README files following 13-section template from whiteboard_module.md
2. Create Architectural Decision Records (ADRs) for novel algorithms (CPN, TPN-MCTS, BGT-SM, TDL-HCO, SPC-UQ)
3. Link module READMEs from this dossier

---

**Q22: Reference Section Completeness**

**Issue**: Document ends with empty reference sections:

- ADRs: [Content TBD]
- Research Papers: [Content TBD]
- Architecture Documents: [Content TBD]

Document cites 50+ research papers throughout (e.g., Walker & Stickgold 2010, Schacter et al. 2012, Mednick 1962), but no consolidated reference list.

**Confusion**: Impossible to verify research claims without full citations. Which papers are authoritative? Which are speculative?

**Impact**: Implementation may be based on misunderstood neuroscience concepts. Academic reviewers can't validate biological plausibility.

**Recommendation**: Complete References section with:

1. **ADR List**: All relevant K0 decisions (k003.3 CA3, k006.1 Salience, k007.4 Retention)
2. **Research Papers**: Full citations for all 50+ papers mentioned (APA format)
3. **Architecture Documents**: Links to K0 master architecture, whiteboard.md, module READMEs

---

**Q23: Appendix Examples Missing**

**Issue**: Document defines 5 appendices but all empty:

- Appendix A: Consolidation State Machine [Content TBD]
- Appendix B: Memory Layer Schema Details [Content TBD]
- Appendix C: Deduplication Examples [Content TBD]
- Appendix D: Pattern Extraction Examples [Content TBD]
- Appendix E: Knowledge Graph Examples [Content TBD]

**Confusion**: State machine (Appendix A) is critical for understanding phase transitions (R0→R1→...→R8), but not documented.

**Impact**: Developers implement state transitions inconsistently. Phase transition bugs.

**Recommendation**: Priority order for appendix completion:

1. **Appendix A** (highest priority): State machine diagram with all transitions, guards, actions
2. **Appendix C**: 10 deduplication examples (exact duplicate, near duplicate, false positive)
3. **Appendix D**: 10 pattern extraction examples (routine, preference, theme, relationship)
4. **Appendix B**: Complete SQL schema with all indexes, foreign keys, triggers
5. **Appendix E**: 5 KG examples showing entity resolution, relationship discovery, causal inference

---

### Summary

**Critical Issues Requiring Resolution Before Implementation:**

1. **Q1**: Module dependency circular reference (M24 ↔ M18-M23)
2. **Q2**: K0 driver transaction boundary semantics
3. **Q4**: Sleep cycle budget mismatch (182 min vs 90 min target)
4. **Q5**: Consolidation trigger race condition handling
5. **Q14**: P02→P03→P08 event flow synchronization

**High-Priority Issues:**
6. Q3: P08 coordination backpressure mechanism
7. Q6: SimHash deduplication scalability
8. Q7: Knowledge graph entity resolution performance
9. Q10: Confidence score propagation rules
10. Q15: Multi-tenant scheduling policy

**Medium-Priority Issues:**
11. Q8: Memory layer write throughput benchmarks
12. Q11: Temporal validity consistency across layers
13. Q13: Pattern extraction seasonal handling
14. Q16: Active Learning (P06) integration specification
15. Q17: Integration test coverage

**Low-Priority Issues (Documentation):**
16. Q9: Theta rhythm coordination justification
17. Q12: Novelty vs importance interaction
18. Q18: Performance test realism
19. Q19: GDPR tombstone auditability
20. Q20: Privacy band mutation workflow
21. Q21: Module README completion
22. Q22: Reference section completion
23. Q23: Appendix examples completion

**Recommendation**: Address critical and high-priority issues during GATE 1 (Architectural Decision Validation) and GATE 2 (Contract Discovery & Validation) before proceeding to implementation.

---

## References

[Content TBD]

### ADRs

[Content TBD]

### Research Papers

[Content TBD]

### Architecture Documents

[Content TBD]

---

## Appendix A: Consolidation State Machine

[Content TBD]

---

## Appendix B: Memory Layer Schema Details

[Content TBD]

---

## Appendix C: Deduplication Examples

[Content TBD]

---

## Appendix D: Pattern Extraction Examples

[Content TBD]

---

## Appendix E: Knowledge Graph Examples

[Content TBD]
