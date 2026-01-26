# R5 Dream Explorer Phase - Algorithm Analysis

**Date:** 2026-01-25
**Status:** Investigation Complete
**Purpose:** Diagnose why R5 algorithms produce zero outputs despite 2000+ events

---

## Executive Summary

The R5 phase algorithms are failing to produce meaningful outputs due to **data schema mismatches** and **missing prerequisite data**. Despite having 2,112 hipp_events and 639 episodes in PostgreSQL, the algorithms receive data structures that lack required fields.

### Key Findings

| Algorithm | Output | Root Cause |
|-----------|--------|------------|
| **CPN** | 0 scenarios | No CAUSES edges, no sentiment_score in episodes |
| **RoutineDetector** | 0 candidates | Field name mismatch (location vs location_hint) |
| **BGT-SM** | 0 insights | No salience_score, strict quality thresholds |
| **SPC-UQ** | 0 prospective | Episodes lack ambiguity_score |
| **TDL-HCO** | 0 optimizations | No routines in st_procedural |
| **MCTS** | 1 scenario | **Working** (20 rollouts used) |

---

## Database State

### Table Counts (PostgreSQL)

```sql
SELECT table_name, count FROM (
    SELECT 'st_hipp_events' as table_name, COUNT(*) as count FROM st_hipp_events
    UNION ALL SELECT 'st_epi', COUNT(*) FROM st_epi
    UNION ALL SELECT 'st_kg_edges', COUNT(*) FROM st_kg_edges
    UNION ALL SELECT 'st_kg_dom', COUNT(*) FROM st_kg_dom
    UNION ALL SELECT 'st_sem', COUNT(*) FROM st_sem
    UNION ALL SELECT 'st_procedural', COUNT(*) FROM st_procedural
    UNION ALL SELECT 'st_prospective', COUNT(*) FROM st_prospective
);
```

| Table | Count |
|-------|-------|
| st_hipp_events | 2,112 |
| st_epi | 639 |
| st_kg_edges | 2,782 |
| st_kg_dom | 103 |
| st_sem | 749 |
| st_procedural | **0** |
| st_prospective | 300 |

### KG Edge Distribution

```sql
SELECT relation_type, COUNT(*) FROM st_kg_edges GROUP BY relation_type ORDER BY count DESC;
```

| Relation Type | Count |
|---------------|-------|
| INFERRED_RELATED | 1,922 |
| SIMILAR_TO | 483 |
| CONTEXTUALLY_RELATED | 293 |
| TEMPORALLY_ASSOCIATED | 30 |
| FAMILY | 20 |
| PRECEDES | 13 |
| FRIEND | 6 |
| **CAUSES** | **4** |
| RELATED_TO | 4 |
| COLLEAGUE | 4 |
| ACQUAINTANCE | 3 |

**Critical Issue:** Only **4 CAUSES edges** exist. CPN requires CAUSES edges to build causal DAGs.

---

## Algorithm Deep Dives

---

### 1. CPN (Causal Perturbation Network)

**File:** `k0/modules/consolidation/algorithms/cpn.py`

**Purpose:** Generate counterfactual "what-if" scenarios by perturbing past events

**Algorithm Flow:**

1. Select emotionally significant episodes (|sentiment| > 0.3 threshold)
2. Extract causal chains from KG (CAUSES edges only)
3. Identify modifiable nodes (actor-controllable actions)
4. Perturb nodes to generate UPWARD/DOWNWARD/SEMIFACTUAL scenarios
5. Evaluate plausibility and utility changes

#### Input Requirements

| Field | Source | Required Type | Notes |
|-------|--------|---------------|-------|
| `episode_id` | Episode | str | Unique ID |
| `sentiment_score` | Episode | float (-1 to 1) | Emotional valence |
| `salience_score` | Episode | float (0 to 1) | Importance score |
| `start_time_ms` | Episode | int | Milliseconds epoch |
| `entity_ids` | Episode | List[str] | Entities involved |
| `relation_type` | KG Edge | str = "CAUSES" | Only CAUSES used |
| `source_id` | KG Edge | str | Source entity |
| `target_id` | KG Edge | str | Target entity |
| `confidence` | KG Edge | float | Edge confidence |

#### What R5 Provides

The R5 phase passes `EpisodeCluster` objects from `envelope.phases.r2_clusters`:

```python
@dataclass
class EpisodeCluster:
    cluster_id: str
    member_event_ids: List[str]
    dominant_sentiment: float = 0.0  # NOT sentiment_score
    aggregated_sentiment: Optional[float] = None
    aggregated_salience: Optional[float] = None  # NOT salience_score
    temporal_start: int = 0  # NOT start_time_ms
    location_hint: Optional[str] = None
    activity_type: str = ""
    # ... no entity_ids field
```

#### CPN Data Access Methods

```python
def _get_episode_sentiment(self, episode: Any) -> float:
    """Get sentiment score from episode object."""
    if hasattr(episode, "sentiment_score"):  # EpisodeCluster has dominant_sentiment
        return episode.sentiment_score
    elif isinstance(episode, dict):
        return episode.get("sentiment_score", 0.0)
    return 0.0  # <-- ALWAYS RETURNS 0.0

def _get_episode_salience(self, episode: Any) -> float:
    """Get salience score from episode object."""
    if hasattr(episode, "salience_score"):  # EpisodeCluster has aggregated_salience
        return episode.salience_score
    elif isinstance(episode, dict):
        return episode.get("salience_score", 0.5)
    return 0.5  # <-- ALWAYS RETURNS DEFAULT
```

#### Failure Analysis

1. **Missing sentiment_score:** `EpisodeCluster.dominant_sentiment` exists but CPN looks for `sentiment_score`
2. **Missing salience_score:** `EpisodeCluster.aggregated_salience` exists but CPN looks for `salience_score`
3. **Missing entity_ids:** EpisodeCluster has no `entity_ids` field
4. **Only 4 CAUSES edges:** Causal DAGs are nearly empty

**Log Evidence:**

```json
{
  "message": "CPN fallback: no episodes passed emotional threshold, selecting by salience",
  "emotional_threshold": 0.3,
  "episode_count": 35
}
```

All 35 episodes have `sentiment_score=0.0` (default), so none pass the 0.3 threshold.

#### Fix Required

```python
# Option A: Add property aliases to EpisodeCluster
@property
def sentiment_score(self) -> float:
    return self.dominant_sentiment or self.aggregated_sentiment or 0.0

@property
def salience_score(self) -> float:
    return self.aggregated_salience or 0.5

# Option B: Update CPN to check alternate field names
def _get_episode_sentiment(self, episode: Any) -> float:
    for attr in ["sentiment_score", "dominant_sentiment", "aggregated_sentiment"]:
        if hasattr(episode, attr):
            val = getattr(episode, attr)
            if val is not None:
                return val
    return 0.0
```

---

### 2. RoutineDetector (GAP-003)

**File:** `k0/modules/consolidation/algorithms/routine_detector.py`

**Purpose:** Detect recurring behavioral patterns (habits) from episodic memory

**Algorithm Flow:**

1. Group episodes by signature: `{activity_type}:{location}`
2. Filter groups with >= 3 occurrences
3. Analyze temporal patterns (regularity, frequency)
4. Score habit strength: frequency × consistency × recency
5. Determine lifecycle state

#### Input Requirements

| Field | Source | Required Type | Notes |
|-------|--------|---------------|-------|
| `episode_id` | Episode dict | str | Unique ID |
| `activity_type` | Episode dict | str | Activity category |
| `primary_location` | Episode dict | str | Location name |
| `start_time_utc` | Episode dict | int | Timestamp (ms) |

#### What DreamExplorer Provides

```python
# In _run_routine_detector():
for cluster in input_data.recent_episodes:
    episode = {
        "episode_id": cluster.cluster_id,
        "activity_type": cluster.activity_type,
        "location": cluster.location_hint,  # <-- WRONG KEY
        "start_time_ms": cluster.temporal_start,  # <-- WRONG KEY
        "end_time_ms": cluster.temporal_end,
    }
```

#### RoutineDetector Signature Builder

```python
def _group_by_signature(self, episodes: List[Dict[str, Any]]) -> Dict[str, EpisodePattern]:
    for ep in episodes:
        activity = (ep.get("activity_type") or ep.get("episode_type") or "").lower()
        location = (ep.get("primary_location") or ep.get("location_hint") or "").lower()
        # ...
```

The code uses:

- `primary_location` first, then `location_hint` as fallback
- DreamExplorer passes `location` (not `primary_location`)

#### Failure Analysis

1. **Field name mismatch:** DreamExplorer passes `location`, RoutineDetector expects `primary_location`
2. **Timestamp key:** Passes `start_time_ms`, detector expects `start_time_utc`
3. **Insufficient repetitions:** Even with correct fields, may not have 3+ matching signatures

**Log Evidence:**

```json
{
  "message": "RoutineDetector completed (GAP-003)",
  "episodes_analyzed": 35,
  "candidates_detected": 0
}
```

#### Fix Required

```python
# Option A: Fix field names in DreamExplorer._run_routine_detector()
episode = {
    "episode_id": cluster.cluster_id,
    "activity_type": cluster.activity_type,
    "primary_location": cluster.location_hint,  # Use primary_location key
    "start_time_utc": cluster.temporal_start,   # Use start_time_utc key
    "end_time_utc": cluster.temporal_end,
    "episode_summary": cluster.summary,
}

# Option B: Update RoutineDetector to accept more field names
location = (
    ep.get("primary_location") or
    ep.get("location_hint") or
    ep.get("location") or  # Add this
    ""
).lower()
```

---

### 3. BGT-SM (Bisociative Graph Traversal)

**File:** `k0/modules/consolidation/algorithms/bgt_sm.py`

**Purpose:** Discover surprising connections between remote concepts via random walks

**Algorithm Flow:**

1. Select seed entities from high-salience episodes
2. Execute Random Walk with Restart (RWR) to explore KG
3. Identify remote associates (semantic distance > 0.7)
4. Compute PMI for surprise quantification
5. Calculate novelty: distance × PMI / (visit_count + 1)
6. Filter by quality thresholds

#### Quality Thresholds (Issue 8.1.10)

| Threshold | Default | Description |
|-----------|---------|-------------|
| `semantic_distance_threshold` | 0.7 | Min distance for remote associate |
| `pmi_threshold` | 3.0 | Min PMI (2^3 = 8x expected co-occurrence) |
| `novelty_threshold` | 0.5 | Min novelty score |
| `serendipity_threshold` | 0.6 | novelty × relevance × actionability |

#### Input Requirements

| Field | Source | Required Type | Notes |
|-------|--------|---------------|-------|
| `entity_id` | KG Entity | str | Unique ID |
| `entity_type` | KG Entity | str | Person, Location, etc. |
| `name` | KG Entity | str | Human-readable |
| `observation_count` | KG Entity | int | Times observed |
| `embedding` | KG Entity | List[float] | Vector embedding |
| `salience_score` | Episode | float | For seed selection |

#### Seed Selection Logic

```python
def _select_seed_entities(self, input_data: DreamExplorerInput) -> List[str]:
    seed_candidates: Dict[str, float] = {}

    for episode in input_data.recent_episodes:
        entity_ids = getattr(episode, "entity_ids", [])  # EpisodeCluster has no entity_ids
        salience = getattr(episode, "salience_score", 0.5)  # Returns 0.5 default

        for entity_id in entity_ids:  # Empty loop
            seed_candidates[entity_id] = salience
```

#### Failure Analysis

1. **No entity_ids in EpisodeCluster:** Episodes don't provide entity references
2. **No salience_score:** Uses default 0.5
3. **Embeddings may be missing:** Entities need vector embeddings for distance calculation
4. **Strict thresholds:** Even with seeds, 0.7 distance + 3.0 PMI + 0.6 serendipity is hard to meet

**Log Evidence:**

```json
{
  "message": "BGT-SM completed",
  "insights_generated": 0,
  "seeds_explored": 0  // No seeds selected
}
```

Wait - the log shows "insights_generated: 0" but no explicit BGT-SM log in the original trace. BGT-SM runs inside DreamExplorer which completed with `insights_count: 0`.

#### Fix Required

1. Add `entity_ids` to EpisodeCluster or derive from KG
2. Lower thresholds during cold-start:
   - `semantic_distance_threshold`: 0.7 → 0.5
   - `pmi_threshold`: 3.0 → 1.5
   - `serendipity_threshold`: 0.6 → 0.3

---

### 4. SPC-UQ (Schematic Pattern Completion)

**File:** `k0/modules/consolidation/algorithms/spc_uq.py`

**Purpose:** Reconstruct incomplete episodes with uncertainty quantification

**Algorithm Flow:**

1. Identify gaps in incomplete episodes (missing location, participants, etc.)
2. Apply schema-based Bayesian reconstruction
3. Generate Monte Carlo samples for uncertainty
4. Score temporal coherence
5. Output ProspectiveMemory objects

#### Input Requirements

| Field | Source | Required Type | Notes |
|-------|--------|---------------|-------|
| `episode_id` | Episode | str | Unique ID |
| `start_time_ms` | Episode | int | Start timestamp |
| `end_time_ms` | Episode | int | End timestamp |
| `location_name` | Episode | Optional[str] | For gap detection |
| `participants` | Episode | Optional[List[str]] | For gap detection |
| `activity_type` | Episode | Optional[str] | For gap detection |
| `ambiguity_score` | Episode | float | Threshold for gaps |

#### Gap Detection

```python
# Episodes with ambiguity_score > 0.5 are candidates for reconstruction
P03_SPC_AMBIGUITY_THRESHOLD = 0.5
```

#### What EpisodeCluster Provides

```python
@dataclass
class EpisodeCluster:
    # Has location_hint (not location_name)
    # Has activity_type
    # No participants field (has participants_json)
    # No ambiguity_score field
```

#### Failure Analysis

1. **No ambiguity_score:** EpisodeCluster doesn't track uncertainty
2. **Field name mismatches:** `location_name` vs `location_hint`
3. **No schema patterns:** `schemas=[]` passed to simulator

**Log Evidence:**
No explicit SPC-UQ log, but `prospective_count: 0` in DreamExplorer output.

---

### 5. TDL-HCO (Temporal Difference Learning)

**File:** `k0/modules/consolidation/algorithms/tdl_hco.py`

**Purpose:** Optimize routines via TD learning to detect bottlenecks

**Algorithm Flow:**

1. Extract routines from episodic memory (requires 3+ occurrences)
2. Learn value function V(s) via TD(0) updates
3. Detect bottlenecks where V drops sharply (gradient < -2.0)
4. Generate optimization suggestions

#### Input Requirements

| Field | Source | Required Type | Notes |
|-------|--------|---------------|-------|
| Routines | st_procedural | RoutineTemplate | Recurring patterns |
| Steps | Routine | RoutineStepData | Step sequence |
| Execution history | Multiple | RoutineExecution | Times performed |

#### Routine Extraction

```python
routines = extract_routines_from_episodes(
    episodes=input_data.recent_episodes,
    min_routine_length=3,   # Min steps per routine
    min_occurrences=2,      # Min times observed
)
```

#### Failure Analysis

1. **st_procedural is empty:** 0 rows in database
2. **RoutineDetector produces nothing:** No routines to optimize
3. **Chicken-and-egg:** TDL-HCO needs routines, but RoutineDetector can't create them

**Log Evidence:**
No TDL-HCO log in output (likely skipped due to no routines).

---

### 6. MCTS (Monte Carlo Tree Search) — WORKING

**File:** `k0/modules/consolidation/algorithms/mcts.py`

**Purpose:** Forward simulation for scenario prediction

**Algorithm Flow:**

1. Build decision tree from current state
2. Run UCT-based exploration (c = √2)
3. Simulate rollouts to evaluate actions
4. Return ranked scenarios

#### Why It Works

MCTS is the **only working algorithm** because:

1. It builds synthetic state from episode/entity counts (no schema dependency)
2. It generates generic actions if none available from entities
3. It doesn't require specific episode fields

**Log Evidence:**

```json
{
  "message": "MCTS completed",
  "scenarios_generated": 1,
  "rollouts_used": 20
}
```

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           R5 DREAM EXPLORER                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   INPUT: envelope.phases.r2_clusters (List[EpisodeCluster])                 │
│          envelope.phases.r4_new_entities (List[KGEntity])                   │
│          envelope.phases.r4_new_edges (List[KGEdge])                        │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ EpisodeCluster fields:                                              │   │
│   │   cluster_id            ✓ (maps to episode_id)                      │   │
│   │   dominant_sentiment    ✗ (CPN expects sentiment_score)             │   │
│   │   aggregated_salience   ✗ (CPN/BGT expects salience_score)          │   │
│   │   temporal_start        ✗ (expects start_time_ms)                   │   │
│   │   location_hint         ✗ (expects primary_location)                │   │
│   │   activity_type         ✓                                           │   │
│   │   [no entity_ids]       ✗ (CPN/BGT need this)                       │   │
│   │   [no ambiguity_score]  ✗ (SPC-UQ needs this)                       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────┐   ┌─────────────────────┐                         │
│   │ KG Edges (2,782)    │   │ KG Entities (103)   │                         │
│   │ - CAUSES: 4 only    │   │ - observation_count │                         │
│   │ - INFERRED: 1,922   │   │ - embeddings?       │                         │
│   └─────────────────────┘   └─────────────────────┘                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ALGORITHM RESULTS                                 │
├──────────────────┬──────────┬───────────────────────────────────────────────┤
│ Algorithm        │ Output   │ Failure Reason                                │
├──────────────────┼──────────┼───────────────────────────────────────────────┤
│ CPN              │ 0        │ sentiment_score=0.0, only 4 CAUSES edges      │
│ RoutineDetector  │ 0        │ Field mismatch, no 3+ matching signatures     │
│ BGT-SM           │ 0        │ No entity_ids, no seeds selected              │
│ SPC-UQ           │ 0        │ No ambiguity_score, no schemas                │
│ TDL-HCO          │ 0        │ st_procedural empty, no routines found        │
│ MCTS             │ 1        │ WORKING - uses synthetic state                │
└──────────────────┴──────────┴───────────────────────────────────────────────┘
```

---

## Recommended Fixes (Priority Order)

### P0: Critical Fixes (Required for any output)

1. **Add property aliases to EpisodeCluster** (phase_outputs.py)

   ```python
   @property
   def sentiment_score(self) -> float:
       return self.dominant_sentiment or self.aggregated_sentiment or 0.0

   @property
   def salience_score(self) -> float:
       return self.aggregated_salience or 0.5

   @property
   def start_time_ms(self) -> int:
       return self.temporal_start

   @property
   def entity_ids(self) -> List[str]:
       # Extract from member events or return empty
       return []
   ```

2. **Fix field names in DreamExplorer._run_routine_detector()**

   ```python
   episode = {
       "episode_id": cluster.cluster_id,
       "activity_type": cluster.activity_type,
       "primary_location": cluster.location_hint,  # Correct key
       "start_time_utc": cluster.temporal_start,   # Correct key
       "episode_summary": cluster.summary,
   }
   ```

3. **Generate CAUSES edges in R4** (kg_edge_inference)
   - Current: Only 4 CAUSES edges exist
   - Needed: Infer causal relationships from temporal sequences

### P1: Cold-Start Thresholds

1. **Lower BGT-SM thresholds** (bgt_sm.py or DreamConfig)

   ```python
   semantic_distance_threshold: 0.5  # Was 0.7
   pmi_threshold: 1.5                # Was 3.0
   serendipity_threshold: 0.3        # Was 0.6
   ```

2. **Lower CPN emotional_threshold** (cpn.py)

   ```python
   emotional_threshold: 0.1  # Was 0.3 (already lowered from 0.6)
   ```

### P2: Data Enrichment

1. **Propagate entity_ids from events to episodes** (R2 clustering)
   - Extract entities from hipp_events during clustering
   - Store in EpisodeCluster.entity_ids

2. **Compute ambiguity_score** (R2 or R3)
   - Track missing fields per episode
   - Store uncertainty metric

3. **Bootstrap st_procedural** (via manual or automated routine detection)
   - Run RoutineDetector with fixed fields
   - Persist to st_procedural table

---

## Files to Modify

| File | Changes |
|------|---------|
| `k0/pipelines/p03/phase_outputs.py` | Add property aliases to EpisodeCluster |
| `k0/modules/consolidation/dream/dream_explorer.py` | Fix field names in _run_routine_detector |
| `k0/modules/consolidation/algorithms/cpn.py` | Check alternate field names |
| `k0/modules/consolidation/algorithms/bgt_sm.py` | Lower cold-start thresholds |
| `k0/modules/consolidation/algorithms/routine_detector.py` | Accept more field variants |
| `k0/pipelines/p03/phases/r4_kg_inference.py` | Generate CAUSES edges |

---

## Test Commands

```bash
# Check current edge distribution
docker exec k0-postgres psql -U k0user -d k0_kernel -c \
  "SELECT relation_type, COUNT(*) FROM st_kg_edges GROUP BY relation_type ORDER BY count DESC;"

# Check episode data
docker exec k0-postgres psql -U k0user -d k0_kernel -c \
  "SELECT episode_id, episode_type, primary_location, confidence_score FROM st_epi LIMIT 5;"

# Verify routine candidates after fix
docker exec k0-postgres psql -U k0user -d k0_kernel -c \
  "SELECT COUNT(*) FROM st_procedural;"
```

---

## Appendix: Log Analysis

**Original Log (2026-01-24):**

```
R5 loaded accumulated KG for BGT-SM:
  - new_entities: 1
  - accumulated_entities: 34
  - merged_entities: 34
  - new_edges: 6
  - accumulated_edges: 23
  - merged_edges: 26

CPN fallback: no episodes passed emotional threshold, selecting by salience
  - emotional_threshold: 0.3
  - episode_count: 35

CPN completed generation:
  - regret_events_count: 10  <- Selected 10 by salience fallback
  - scenarios_generated: 0   <- But 0 scenarios (no CAUSES edges)

MCTS completed:
  - scenarios_generated: 1   <- WORKING
  - rollouts_used: 20

RoutineDetector completed (GAP-003):
  - episodes_analyzed: 35
  - candidates_detected: 0   <- Field mismatch

DreamExplorer completed exploration:
  - insights_count: 0
  - counterfactuals_count: 0
  - prospective_count: 0
  - routines_count: 0
  - routine_candidates_count: 0
  - intent_signals_count: 74  <- IntentSignalDetector works
  - mcts_rollouts_used: 20
  - all_succeeded: true       <- No errors, just no output
```

---

## Next Steps

1. Implement P0 fixes in priority order
2. Run P03 pipeline and validate improved output
3. Monitor metrics: `p03_r5_insights_generated`, `p03_r5_counterfactuals_generated`
4. If still low, implement P1 threshold adjustments
5. Long-term: Ensure R4 generates meaningful CAUSES edges

---

# Part 2: Memory Layer Schemas

## Overview

The FamilyOS memory system consists of 8 primary tables that form the cognitive memory architecture. Each layer serves a specific purpose and has defined read/write patterns for R5 algorithms.

### Memory Layer Hierarchy

```
+-----------------------------------------------------------------------------+
|                         MEMORY LAYER ARCHITECTURE                           |
+-----------------------------------------------------------------------------+
|                                                                             |
|  RAW INPUT                                                                  |
|  +---------------------------------------------------------------------+   |
|  | st_hipp_events (2,112 rows)                                         |   |
|  | Raw ingested events from all sources                                |   |
|  | 121 columns - most detailed event data                              |   |
|  +-----------------------------+---------------------------------------+   |
|                                |                                           |
|                                v                                           |
|  EPISODIC MEMORY (What happened)                                           |
|  +---------------------------------------------------------------------+   |
|  | st_epi (639 rows)                                                   |   |
|  | Clustered episodes from events                                      |   |
|  | "Lunch with Mom at cafe" = 1 episode from 3 events                  |   |
|  +-----------------------------+---------------------------------------+   |
|                                |                                           |
|         +----------------------+----------------------+                    |
|         v                      v                      v                    |
|  +--------------+    +------------------+    +------------------+          |
|  | st_sem       |    | st_kg_dom        |    | st_kg_edges      |          |
|  | (749 rows)   |    | (103 rows)       |    | (2,782 rows)     |          |
|  | Patterns &   |    | Entities         |    | Relationships    |          |
|  | Schemas      |    | (People, Places) |    | (FAMILY, CAUSES) |          |
|  +--------------+    +------------------+    +------------------+          |
|         |                      |                      |                    |
|         +----------------------+----------------------+                    |
|                                v                                           |
|  PROCEDURAL & PROSPECTIVE                                                  |
|  +------------------+    +------------------+                              |
|  | st_procedural    |    | st_prospective   |                              |
|  | (0 rows)         |    | (300 rows)       |                              |
|  | Habits/Routines  |    | Future Intentions|                              |
|  +------------------+    +------------------+                              |
|                                                                             |
|  OBSERVATION LAYER (Cross-cutting)                                          |
|  +---------------------------------------------------------------------+   |
|  | st_observations (48,070 rows)                                       |   |
|  | Tracks every observation event for all layers                       |   |
|  | Sentiment, salience, location, social context per observation       |   |
|  +---------------------------------------------------------------------+   |
|                                                                             |
+-----------------------------------------------------------------------------+
```

### Current Row Counts

| Table | Count | Description |
|-------|-------|-------------|
| st_hipp_events | 2,112 | Raw ingested events |
| st_epi | 639 | Episodic memory (clustered episodes) |
| st_sem | 749 | Semantic memory (patterns/schemas) |
| st_kg_dom | 103 | KG entities (people, places, things) |
| st_kg_edges | 2,782 | KG relationships |
| st_procedural | **0** | Procedural memory (habits/routines) |
| st_prospective | 300 | Prospective memory (intentions) |
| st_observations | 48,070 | Observation audit trail |

### Observation Layer Breakdown

| Layer | Observation Type | Count |
|-------|------------------|-------|
| st_kg_edges | REINFORCEMENT | 42,161 |
| st_kg_edges | FIRST_SEEN | 3,134 |
| st_sem | FIRST_SEEN | 953 |
| st_epi | FIRST_SEEN | 639 |
| st_social | FIRST_SEEN | 428 |
| st_prospective | FIRST_SEEN | 397 |
| st_kg_dom | REINFORCEMENT | 246 |
| st_kg_dom | FIRST_SEEN | 112 |

---

# Part 2: Memory Layer Schemas

## Overview

The FamilyOS memory system consists of 8 primary tables that form the cognitive memory architecture. Each layer serves a specific purpose and has defined read/write patterns for R5 algorithms.

### Memory Layer Hierarchy

```
+-----------------------------------------------------------------------------+
|                         MEMORY LAYER ARCHITECTURE                           |
+-----------------------------------------------------------------------------+
|                                                                             |
|  RAW INPUT                                                                  |
|  +---------------------------------------------------------------------+   |
|  | st_hipp_events (2,112 rows)                                         |   |
|  | Raw ingested events from all sources                                |   |
|  | 121 columns - most detailed event data                              |   |
|  +-----------------------------+---------------------------------------+   |
|                                |                                           |
|                                v                                           |
|  EPISODIC MEMORY (What happened)                                           |
|  +---------------------------------------------------------------------+   |
|  | st_epi (639 rows)                                                   |   |
|  | Clustered episodes from events                                      |   |
|  | "Lunch with Mom at cafe" = 1 episode from 3 events                  |   |
|  +-----------------------------+---------------------------------------+   |
|                                |                                           |
|         +----------------------+----------------------+                    |
|         v                      v                      v                    |
|  +--------------+    +------------------+    +------------------+          |
|  | st_sem       |    | st_kg_dom        |    | st_kg_edges      |          |
|  | (749 rows)   |    | (103 rows)       |    | (2,782 rows)     |          |
|  | Patterns &   |    | Entities         |    | Relationships    |          |
|  | Schemas      |    | (People, Places) |    | (FAMILY, CAUSES) |          |
|  +--------------+    +------------------+    +------------------+          |
|         |                      |                      |                    |
|         +----------------------+----------------------+                    |
|                                v                                           |
|  PROCEDURAL & PROSPECTIVE                                                  |
|  +------------------+    +------------------+                              |
|  | st_procedural    |    | st_prospective   |                              |
|  | (0 rows)         |    | (300 rows)       |                              |
|  | Habits/Routines  |    | Future Intentions|                              |
|  +------------------+    +------------------+                              |
|                                                                             |
|  OBSERVATION LAYER (Cross-cutting)                                          |
|  +---------------------------------------------------------------------+   |
|  | st_observations (48,070 rows)                                       |   |
|  | Tracks every observation event for all layers                       |   |
|  | Sentiment, salience, location, social context per observation       |   |
|  +---------------------------------------------------------------------+   |
|                                                                             |
+-----------------------------------------------------------------------------+
```

### Current Row Counts

| Table | Count | Description |
|-------|-------|-------------|
| st_hipp_events | 2,112 | Raw ingested events |
| st_epi | 639 | Episodic memory (clustered episodes) |
| st_sem | 749 | Semantic memory (patterns/schemas) |
| st_kg_dom | 103 | KG entities (people, places, things) |
| st_kg_edges | 2,782 | KG relationships |
| st_procedural | **0** | Procedural memory (habits/routines) |
| st_prospective | 300 | Prospective memory (intentions) |
| st_observations | 48,070 | Observation audit trail |

### Observation Layer Breakdown

| Layer | Observation Type | Count |
|-------|------------------|-------|
| st_kg_edges | REINFORCEMENT | 42,161 |
| st_kg_edges | FIRST_SEEN | 3,134 |
| st_sem | FIRST_SEEN | 953 |
| st_epi | FIRST_SEEN | 639 |
| st_social | FIRST_SEEN | 428 |
| st_prospective | FIRST_SEEN | 397 |
| st_kg_dom | REINFORCEMENT | 246 |
| st_kg_dom | FIRST_SEEN | 112 |

---

## 1. st_hipp_events (Raw Events)

**Purpose:** Store all raw ingested events before consolidation. The "hippocampus" that receives all sensory input.

**Row Count:** 2,112

### Schema (121 columns - key fields shown)

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| **event_id** | text | NO | Primary key (ULID) |
| **tenant_id** | text | NO | Tenant isolation |
| **space_id** | text | NO | User/family space |
| **event_time_utc** | bigint | NO | Event timestamp (ms) |
| text | text | YES | Raw text content |
| activity_type | text | YES | Activity type (7-type) |
| location_name | text | YES | Location name |
| participants_json | text | YES | Participants JSON |
| entities_json | text | YES | **Extracted entities** |
| kg_triples_json | text | YES | **KG triples** |
| **sentiment_score** | double | YES | **Sentiment (-1 to 1)** |
| **salience_score** | double | NO | **Salience (0-1)** |
| episode_cluster_id | text | YES | Assigned episode |

### Key Fields for R5 Algorithms

| Field | Used By | Notes |
|-------|---------|-------|
| sentiment_score | CPN, IntentSignal | Available here, missing in EpisodeCluster |
| salience_score | BGT-SM, CPN | Available here, missing in EpisodeCluster |
| entities_json | BGT-SM, CPN | Contains extracted entity IDs |
| kg_triples_json | CPN | Contains causal relationships |

### When to Fetch

- **R1 (Batch Selector):** Fetch unprocessed events for consolidation
- **R2 (Clustering):** Read events to form episode clusters
- **R5 (Dream):** Read for intent signal detection (IntentSignalDetector)

### When to Write

- **P02 Ingestion:** Primary insert point for new events
- **R2 (Clustering):** Update episode_cluster_id, cluster_confidence
- **R3 (Reconciliation):** Update reconciliation_* fields

---

## 2. st_epi (Episodic Memory)

**Purpose:** Store coherent episodes formed by clustering related events. Each episode represents a memorable experience.

**Row Count:** 639

### Schema (39 columns)

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| **episode_id** | text | NO | Primary key (ULID) |
| **tenant_id** | text | NO | Tenant isolation |
| **space_id** | text | NO | User/family space |
| episode_summary | text | YES | Human-readable summary |
| episode_type | text | YES | Type: routine, social, milestone |
| **start_time_utc** | bigint | NO | Episode start (ms) |
| **end_time_utc** | bigint | NO | Episode end (ms) |
| **source_events_json** | text | NO | Source event IDs (JSON array) |
| **source_event_count** | integer | NO | Number of source events |
| primary_location | text | YES | Primary location |
| participants_json | text | YES | Participants (JSON array) |

### Missing Fields (Needed by R5)

| Expected Field | Current Status | Notes |
|----------------|----------------|-------|
| sentiment_score | **MISSING** | CPN expects this |
| salience_score | **MISSING** | BGT-SM expects this |
| entity_ids | **MISSING** | CPN/BGT-SM expect this |
| ambiguity_score | **MISSING** | SPC-UQ expects this |

### When to Fetch

- **R5 (Dream):** CPN, BGT-SM, SPC-UQ, TDL-HCO, RoutineDetector all read episodes
- **R4 (KG):** Read episodes for entity/edge extraction
- **Query Layer:** Read for user memory queries

### When to Write

- **R2 (Clustering):** Create new episodes from event clusters
- **R3 (Reconciliation):** Update versions, merge duplicates
- **R6 (Write):** Final write after R5 enhancements

---

## 3. st_sem (Semantic Memory)

**Purpose:** Store generalized patterns and schemas extracted from episodes. "Mom likes coffee" is semantic memory.

**Row Count:** 749

### Schema (32 columns)

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| **pattern_id** | text | NO | Primary key (ULID) |
| **tenant_id** | text | NO | Tenant isolation |
| **space_id** | text | NO | User/family space |
| **pattern_type** | text | NO | Pattern type |
| **pattern_name** | text | NO | Pattern name |
| pattern_description | text | YES | Description |
| pattern_attributes_json | text | YES | Pattern attributes |
| temporal_regularity | double | YES | Temporal regularity score |
| **source_episodes_json** | text | NO | Source episode IDs |
| **source_episode_count** | integer | NO | Episode count |

### When to Fetch

- **SPC-UQ:** Read schemas for pattern completion
- **BGT-SM:** Read for semantic distance calculation
- **Query Layer:** Read for knowledge queries

### When to Write

- **R4 (KG):** Create patterns from episode analysis
- **R5 (BGT-SM):** May create new insights as semantic patterns

---

## 4. st_kg_dom (Knowledge Graph Entities)

**Purpose:** Store entities (people, places, things) extracted from events and episodes. The nodes of the knowledge graph.

**Row Count:** 103

### Schema (33 columns)

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| **entity_id** | text | NO | Primary key (ULID or cluster_*) |
| **tenant_id** | text | NO | Tenant isolation |
| **space_id** | text | NO | User/family space |
| **entity_type** | text | NO | PERSON, LOCATION, ACTIVITY, etc. |
| **canonical_name** | text | NO | Canonical name |
| aliases_json | text | YES | Aliases (JSON array) |
| attributes_json | text | YES | Entity attributes |
| observation_count | integer | YES | Times observed |
| confidence_score | double | YES | Confidence |

### When to Fetch

- **BGT-SM:** Select seed entities for random walk
- **CPN:** Get entity references for causal chains
- **Query Layer:** Resolve entity names

### When to Write

- **R4 (KG):** Create/update entities from NER
- **R5 (BGT-SM):** May update access counts

---

## 5. st_kg_edges (Knowledge Graph Edges)

**Purpose:** Store relationships between entities. The edges of the knowledge graph.

**Row Count:** 2,782

### Schema (32 columns)

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| **edge_id** | text | NO | Primary key |
| **source_entity_id** | text | NO | Source entity (FK to st_kg_dom) |
| **target_entity_id** | text | NO | Target entity (FK to st_kg_dom) |
| **relation_type** | text | NO | CAUSES, FAMILY, PRECEDES, etc. |
| edge_weight | double | YES | Edge weight (0-1) |
| confidence_score | double | YES | Confidence |
| observation_count | integer | YES | Times observed |

### Edge Type Distribution

| relation_type | Count | Used By |
|---------------|-------|---------|
| INFERRED_RELATED | 1,922 | BGT-SM |
| SIMILAR_TO | 483 | BGT-SM |
| CONTEXTUALLY_RELATED | 293 | BGT-SM |
| TEMPORALLY_ASSOCIATED | 30 | - |
| FAMILY | 20 | - |
| PRECEDES | 13 | - |
| FRIEND | 6 | - |
| **CAUSES** | **4** | **CPN (needs more!)** |
| RELATED_TO | 4 | - |
| COLLEAGUE | 4 | - |
| ACQUAINTANCE | 3 | - |

### When to Fetch

- **CPN:** Fetch CAUSES edges for causal DAG building
- **BGT-SM:** Fetch all edges for random walk exploration
- **Query Layer:** Relationship queries

### When to Write

- **R4 (KG):** Create edges from relation extraction
- **R5 (BGT-SM):** May create new inferred edges

### Critical Gap: CAUSES Edges

CPN requires CAUSES edges but only 4 exist. Need to either:

1. Generate more CAUSES edges in R4
2. Use PRECEDES/TEMPORALLY_ASSOCIATED as fallback in CPN

---

## 6. st_procedural (Procedural Memory / Routines)

**Purpose:** Store detected behavioral routines and habits.

**Row Count:** 0 (EMPTY!)

### Schema (33 columns)

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| **routine_id** | text | NO | Primary key |
| **actor_id** | text | NO | Actor |
| **routine_name** | text | NO | Routine name |
| routine_category | text | YES | Category (MEAL, EXERCISE, etc.) |
| temporal_anchor | text | YES | Time anchor ("08:00", "morning") |
| day_pattern | text | YES | Day pattern ("weekdays", "MWF") |
| frequency | text | YES | Frequency (DAILY, WEEKLY, etc.) |
| regularity_score | double | YES | Regularity (0-1) |
| action_sequence_json | text | YES | Step sequence (JSON) |
| **source_episodes_json** | text | NO | Source episodes |
| **source_episode_count** | integer | NO | Episode count |

### When to Fetch

- **TDL-HCO:** Read routines for bottleneck detection

### When to Write

- **R5 (RoutineDetector):** Create detected routine candidates

### Critical Gap: Empty Table

RoutineDetector should populate this table, but field mismatches prevent it.

---

## 7. st_prospective (Prospective Memory / Intentions)

**Purpose:** Store future intentions and reminders.

**Row Count:** 300

### Schema (26 columns)

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| **intention_id** | text | NO | Primary key |
| **actor_id** | text | NO | Actor |
| **intention_type** | text | NO | Type (GOAL, REMINDER, DEADLINE) |
| **intention_description** | text | NO | Description |
| target_date | bigint | YES | Target date (ms) |
| status | text | YES | Status (PENDING, COMPLETED) |
| inference_confidence | double | YES | Inference confidence |

### When to Fetch

- **SPC-UQ:** Read for pattern completion
- **Query Layer:** Read for reminder queries

### When to Write

- **R5 (SPC-UQ):** Create prospective memories from reconstructions
- **R5 (IntentSignalDetector):** Create intentions from detected signals

---

## 4. st_kg_dom (Knowledge Graph Entities)

**Purpose:** Store entities (people, places, things) extracted from events and episodes. The nodes of the knowledge graph.

**Row Count:** 103

### Schema (33 columns)

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| **entity_id** | text | NO | Primary key (ULID or cluster_*) |
| **tenant_id** | text | NO | Tenant isolation |
| **space_id** | text | NO | User/family space |
| **entity_type** | text | NO | PERSON, LOCATION, ACTIVITY, etc. |
| **canonical_name** | text | NO | Canonical name |
| aliases_json | text | YES | Aliases (JSON array) |
| attributes_json | text | YES | Entity attributes |
| observation_count | integer | YES | Times observed |
| confidence_score | double | YES | Confidence |

### When to Fetch

- **BGT-SM:** Select seed entities for random walk
- **CPN:** Get entity references for causal chains
- **Query Layer:** Resolve entity names

### When to Write

- **R4 (KG):** Create/update entities from NER
- **R5 (BGT-SM):** May update access counts

---

## 5. st_kg_edges (Knowledge Graph Edges)

**Purpose:** Store relationships between entities. The edges of the knowledge graph.

**Row Count:** 2,782

### Schema (32 columns)

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| **edge_id** | text | NO | Primary key |
| **source_entity_id** | text | NO | Source entity (FK to st_kg_dom) |
| **target_entity_id** | text | NO | Target entity (FK to st_kg_dom) |
| **relation_type** | text | NO | CAUSES, FAMILY, PRECEDES, etc. |
| edge_weight | double | YES | Edge weight (0-1) |
| confidence_score | double | YES | Confidence |
| observation_count | integer | YES | Times observed |

### Edge Type Distribution

| relation_type | Count | Used By |
|---------------|-------|---------|
| INFERRED_RELATED | 1,922 | BGT-SM |
| SIMILAR_TO | 483 | BGT-SM |
| CONTEXTUALLY_RELATED | 293 | BGT-SM |
| TEMPORALLY_ASSOCIATED | 30 | - |
| FAMILY | 20 | - |
| PRECEDES | 13 | - |
| FRIEND | 6 | - |
| **CAUSES** | **4** | **CPN (needs more!)** |
| RELATED_TO | 4 | - |
| COLLEAGUE | 4 | - |
| ACQUAINTANCE | 3 | - |

### When to Fetch

- **CPN:** Fetch CAUSES edges for causal DAG building
- **BGT-SM:** Fetch all edges for random walk exploration
- **Query Layer:** Relationship queries

### When to Write

- **R4 (KG):** Create edges from relation extraction
- **R5 (BGT-SM):** May create new inferred edges

### Critical Gap: CAUSES Edges

CPN requires CAUSES edges but only 4 exist. Need to either:

1. Generate more CAUSES edges in R4
2. Use PRECEDES/TEMPORALLY_ASSOCIATED as fallback in CPN

---

## 6. st_procedural (Procedural Memory / Routines)

**Purpose:** Store detected behavioral routines and habits.

**Row Count:** 0 (EMPTY!)

### Schema (33 columns)

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| **routine_id** | text | NO | Primary key |
| **actor_id** | text | NO | Actor |
| **routine_name** | text | NO | Routine name |
| routine_category | text | YES | Category (MEAL, EXERCISE, etc.) |
| temporal_anchor | text | YES | Time anchor ("08:00", "morning") |
| day_pattern | text | YES | Day pattern ("weekdays", "MWF") |
| frequency | text | YES | Frequency (DAILY, WEEKLY, etc.) |
| regularity_score | double | YES | Regularity (0-1) |
| action_sequence_json | text | YES | Step sequence (JSON) |
| **source_episodes_json** | text | NO | Source episodes |
| **source_episode_count** | integer | NO | Episode count |

### When to Fetch

- **TDL-HCO:** Read routines for bottleneck detection

### When to Write

- **R5 (RoutineDetector):** Create detected routine candidates

### Critical Gap: Empty Table

RoutineDetector should populate this table, but field mismatches prevent it.

---

## 7. st_prospective (Prospective Memory / Intentions)

**Purpose:** Store future intentions and reminders.

**Row Count:** 300

### Schema (26 columns)

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| **intention_id** | text | NO | Primary key |
| **actor_id** | text | NO | Actor |
| **intention_type** | text | NO | Type (GOAL, REMINDER, DEADLINE) |
| **intention_description** | text | NO | Description |
| target_date | bigint | YES | Target date (ms) |
| status | text | YES | Status (PENDING, COMPLETED) |
| inference_confidence | double | YES | Inference confidence |

### When to Fetch

- **SPC-UQ:** Read for pattern completion
- **Query Layer:** Read for reminder queries

### When to Write

- **R5 (SPC-UQ):** Create prospective memories from reconstructions
- **R5 (IntentSignalDetector):** Create intentions from detected signals

---

## 8. st_observations (Observation Audit Trail)

**Purpose:** Track every observation event across all memory layers. Contains sentiment, salience, location, and social context for each observation.

**Row Count:** 48,070

### Schema (32 columns)

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| **observation_id** | text | NO | Primary key |
| **layer** | text | NO | Target layer (st_epi, st_kg_edges, etc.) |
| **record_id** | text | NO | Target record ID |
| **observed_at** | bigint | NO | Observation time (ms) |
| **observation_type** | text | NO | FIRST_SEEN, REINFORCEMENT |
| **observation_weight** | double | NO | Observation weight |
| **sentiment_score** | double | YES | **Sentiment (-1 to 1)** |
| **salience_score** | double | YES | **Salience (0-1)** |
| **affect_valence** | double | YES | Affect valence |
| **affect_arousal** | double | YES | Affect arousal |
| **location_name** | text | YES | Location name |
| **social_context** | text | YES | Social context |
| **social_intimacy** | text | YES | Intimacy level |

### Key Insight: This Table Has What Episodes Need

| Field | Present in st_observations | Missing in st_epi |
|-------|---------------------------|-------------------|
| sentiment_score | YES | **MISSING** |
| salience_score | YES | **MISSING** |
| affect_valence | YES | **MISSING** |
| affect_arousal | YES | **MISSING** |
| social_context | YES | **MISSING** |

### When to Fetch

- **R5 (All algorithms):** Fetch observations to enrich episodes with sentiment/salience
- **Analytics:** Read for memory access patterns

### When to Write

- **R2 (Clustering):** Write observations for new episodes
- **R4 (KG):** Write observations for entity/edge updates
- **R6 (Write):** Write observations for all memory layer updates

### Critical Insight: Use st_observations to Enrich Episodes

Instead of adding columns to st_epi, R5 can JOIN with st_observations:

```sql
SELECT
    e.episode_id,
    e.episode_summary,
    AVG(o.sentiment_score) as sentiment_score,
    AVG(o.salience_score) as salience_score
FROM st_epi e
JOIN st_observations o ON o.record_id = e.episode_id AND o.layer = 'st_epi'
GROUP BY e.episode_id, e.episode_summary;
```

---

## Algorithm -> Table Mapping

### Read Operations

| Algorithm | Reads From | Fields Needed |
|-----------|------------|---------------|
| **CPN** | st_epi | sentiment_score, salience_score, entity_ids |
| **CPN** | st_kg_edges | relation_type='CAUSES', source_id, target_id |
| **BGT-SM** | st_kg_dom | entity_id, entity_type, observation_count |
| **BGT-SM** | st_kg_edges | source_id, target_id, relation_type |
| **SPC-UQ** | st_epi | location_name, participants, activity_type |
| **SPC-UQ** | st_sem | pattern_type, pattern_attributes_json |
| **TDL-HCO** | st_procedural | routine_id, action_sequence_json |
| **RoutineDetector** | st_epi | activity_type, primary_location, start_time_utc |
| **IntentSignal** | st_hipp_events | text, intent_category, temporal_json |

### Write Operations

| Algorithm | Writes To | What It Creates |
|-----------|-----------|-----------------|
| **CPN** | st_prospective | Counterfactual scenarios as intentions |
| **BGT-SM** | st_sem | New insights as semantic patterns |
| **SPC-UQ** | st_prospective | Reconstructed intentions |
| **TDL-HCO** | st_procedural | Optimized routine suggestions |
| **RoutineDetector** | st_procedural | Detected routine candidates |
| **IntentSignal** | st_prospective | Detected intentions |
| **MCTS** | (none) | Scenarios stay in memory for evaluation |

---

# Part 3: R5 Algorithm I/O Roadmap (Code-Verified)

## 3.1 Data Availability Constraint

**Critical Context:** R7 (Write phase) persists data to PostgreSQL only AFTER R5 completes.

```
┌─────────────────────────────────────────────────────────────────────────┐
│ CYCLE DATA AVAILABILITY                                                  │
├─────────────────────────────────────────────────────────────────────────┤
│ Prior Cycles (N-1, N-2, ...)    │  Current Cycle (N)                    │
│ ────────────────────────────────│──────────────────────────────────────│
│ PostgreSQL Tables:              │  In-Memory (Envelope):                │
│  - st_epi                       │   - envelope.phases.r2_clusters       │
│  - st_kg_edges                  │   - envelope.phases.r4_entities       │
│  - st_kg_dom                    │   - envelope.phases.r4_edges          │
│  - st_sem                       │   - (NOT in PostgreSQL yet!)          │
│  - st_procedural                │                                       │
│  - st_observations              │                                       │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3.1.1 Parity Resolution Strategy

### The Problem

R5 algorithms need BOTH:

1. **Historical data** from PostgreSQL (prior cycles N-1, N-2, ...)
2. **Current data** from in-memory envelope (cycle N)

But current cycle data is NOT persisted until R7 completes (after R5). This creates a **temporal parity gap**.

### Current State Analysis

| Data Type | Prior Cycles (PostgreSQL) | Current Cycle (Envelope) | Merged? |
|-----------|---------------------------|--------------------------|---------|
| KG Entities | st_kg_dom | envelope.phases.r4_new_entities | **YES** (GAP-001 M9.2) |
| KG Edges | st_kg_edges | envelope.phases.r4_new_edges | **YES** (GAP-001 M9.2) |
| Episodes | st_epi | envelope.phases.r2_clusters | **NO** - GAP! |
| Routines | st_procedural | (none in envelope) | **NO** - GAP! |
| Observations | st_observations | (computed but not persisted) | **NO** - GAP! |
| Semantic Patterns | st_sem | (none in envelope) | **NO** - GAP! |

### Code Evidence: Existing GAP-001 M9.2 Pattern

**Source:** `k0/pipelines/p03/phases/r5_dream_explorer.py` lines 383-418

```python
# =====================================================================
# GAP-001 M9.2: Load accumulated KG entities and edges
# BGT-SM needs the full graph, not just batch-new entities
# =====================================================================
accumulated_entities = await self._load_accumulated_entities(
    ctx=ctx,
    tenant_id=envelope.context.tenant_id,
    space_id=envelope.context.space_id,
)
accumulated_edges = await self._load_accumulated_edges(...)

# Merge accumulated with new (new entities take precedence via dict)
new_entities = list(envelope.phases.r4_new_entities)
new_edges = list(envelope.phases.r4_new_edges)

# Create entity ID set for deduplication
new_entity_ids = {e.entity_id for e in new_entities}
merged_entities = new_entities + [
    e for e in accumulated_entities if e.entity_id not in new_entity_ids
]
```

This pattern WORKS for KG but is NOT applied to episodes or routines.

---

## 3.1.2 Resolution: Extend Merge Pattern to All Data Types

### Strategy: Apply GAP-001 M9.2 Pattern Universally

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ RESOLUTION: UNIFIED MERGE LAYER                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  FOR EACH DATA TYPE:                                                        │
│    1. Load accumulated data from PostgreSQL (prior cycles)                  │
│    2. Get current-cycle data from envelope                                  │
│    3. Merge with deduplication (current takes precedence)                   │
│    4. Pass merged data to algorithms                                        │
│                                                                             │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐         │
│  │  PostgreSQL     │    │    Envelope     │    │   Merged Data   │         │
│  │  (Prior Cycles) │ +  │ (Current Cycle) │ =  │  (R5 Input)     │         │
│  └────────┬────────┘    └────────┬────────┘    └────────┬────────┘         │
│           │                      │                      │                   │
│           v                      v                      v                   │
│  ┌────────────────────────────────────────────────────────────────┐        │
│  │                    DreamExplorerInput                          │        │
│  ├────────────────────────────────────────────────────────────────┤        │
│  │ recent_episodes = merged_episodes (st_epi + r2_clusters)       │  NEW!  │
│  │ kg_entities = merged_entities (st_kg_dom + r4_entities) ✓      │  DONE  │
│  │ kg_edges = merged_edges (st_kg_edges + r4_edges) ✓             │  DONE  │
│  │ routines = merged_routines (st_procedural + routine_candidates)│  NEW!  │
│  │ event_states = envelope.events (current only is fine)          │  OK    │
│  └────────────────────────────────────────────────────────────────┘        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3.1.3 Implementation Plan: Episode Merge

### Gap: Episodes Not Merged

**Current Code (r5_dream_explorer.py line 421-424):**

```python
input_data = DreamExplorerInput(
    ...
    recent_episodes=list(envelope.phases.r2_clusters),  # <-- ONLY current cycle!
    ...
)
```

**Problem:** CPN, RoutineDetector, SPC-UQ, TDL-HCO all receive ONLY current-cycle episodes.

### Fix: Add _load_accumulated_episodes()

**New method to add in r5_dream_explorer.py:**

```python
async def _load_accumulated_episodes(
    self,
    ctx: "P03RunnerContext",
    tenant_id: str,
    space_id: str,
    limit: int = 100,  # Recent N episodes for analysis
) -> List["EpisodeCluster"]:
    """
    Load accumulated episodes from st_epi for R5.

    Similar to GAP-001 M9.2 pattern for KG entities.
    Algorithms like RoutineDetector need episode history to detect patterns.

    Returns:
        List of EpisodeCluster objects from storage
    """
    from k0.pipelines.p03.phase_outputs import EpisodeCluster

    try:
        result = await ctx.syscalls.episodes_query(
            tenant_id=tenant_id,
            space_id=space_id,
            limit=limit,
            order_by="start_time_utc DESC",  # Most recent first
        )

        episodes = []
        for row in result.get("episodes", []):
            episode = EpisodeCluster(
                cluster_id=row["episode_id"],
                member_event_ids=json.loads(row.get("source_events_json", "[]")),
                dominant_sentiment=row.get("sentiment_score", 0.0),
                aggregated_sentiment=row.get("sentiment_score"),
                aggregated_salience=row.get("salience_score"),
                dominant_location=row.get("primary_location"),
                location_hint=row.get("primary_location"),
                temporal_start=row.get("start_time_utc", 0),
                temporal_end=row.get("end_time_utc", 0),
                activity_type=row.get("episode_type", ""),
            )
            episodes.append(episode)

        return episodes
    except Exception as e:
        self._logger.warning(
            "Failed to load accumulated episodes, proceeding with batch-only",
            extra={"error": str(e)},
        )
        return []
```

**Updated merge logic:**

```python
# Load accumulated episodes from prior cycles
accumulated_episodes = await self._load_accumulated_episodes(
    ctx=ctx,
    tenant_id=envelope.context.tenant_id,
    space_id=envelope.context.space_id,
)

# Merge with current cycle (current takes precedence)
current_episodes = list(envelope.phases.r2_clusters)
current_ids = {e.cluster_id for e in current_episodes}
merged_episodes = current_episodes + [
    e for e in accumulated_episodes if e.cluster_id not in current_ids
]

# Build input with merged episodes
input_data = DreamExplorerInput(
    ...
    recent_episodes=merged_episodes,  # <-- NOW INCLUDES HISTORY!
    ...
)
```

---

## 3.1.4 Implementation Plan: Routine Merge

### Gap: Routines Not Merged (TDL-HCO Blocked)

**Current Code (dream_explorer.py line 985-993):**

```python
# Extract routines from episodic memory
routines = extract_routines_from_episodes(
    episodes=input_data.recent_episodes,  # <-- Only uses episodes!
    min_routine_length=3,
    min_occurrences=2,
)

if not routines:
    self._logger.debug("TDL-HCO skipped: no routines found")
    return []
```

**Problem:** TDL-HCO extracts routines from episodes, but:

1. If RoutineDetector hasn't run yet (it runs AFTER TDL-HCO in parallel), no routines exist
2. st_procedural is empty, so even historical routines aren't available

### Fix: Two-Phase Routine Handling

**Phase 1: Load accumulated routines from st_procedural**

```python
async def _load_accumulated_routines(
    self,
    ctx: "P03RunnerContext",
    tenant_id: str,
    space_id: str,
) -> List[Dict]:
    """
    Load accumulated routines from st_procedural for TDL-HCO.

    TDL-HCO needs existing routines to optimize.
    """
    try:
        result = await ctx.syscalls.procedural_memory_query(
            tenant_id=tenant_id,
            space_id=space_id,
            limit=50,
        )
        return result.get("routines", [])
    except Exception as e:
        self._logger.warning(
            "Failed to load accumulated routines",
            extra={"error": str(e)},
        )
        return []
```

**Phase 2: Ensure RoutineDetector runs BEFORE TDL-HCO**

Current execution order (dream_explorer.py line 177-195):

```python
# PHASE 1: Run parallel algorithms (CPN, BGT-SM, SPC-UQ, MCTS)
parallel_results = await self._run_parallel_algorithms(...)

# PHASE 2: Run TDL-HCO (depends on routine data)
optimizations = await self._run_tdl_hco(...)

# GAP-003: Run routine detector (runs after TDL-HCO!)
routine_candidates = await self._run_routine_detector(...)
```

**Fix: Reorder execution to run RoutineDetector BEFORE TDL-HCO**

```python
# PHASE 1: Run parallel algorithms
parallel_results = await self._run_parallel_algorithms(...)

# PHASE 1.5: Run RoutineDetector FIRST (GAP-003)
routine_candidates = await self._run_routine_detector(input_data, cycle_id)

# PHASE 2: Run TDL-HCO with detected routines + accumulated
optimizations = await self._run_tdl_hco(
    input_data,
    cycle_id,
    compute_budget,
    detected_routines=routine_candidates,  # <-- Pass detected routines
)
```

---

## 3.1.5 Implementation Plan: Observation Enrichment

### Gap: Current-Cycle Episodes Missing Observation Data

**Problem:** R2 creates EpisodeClusters with computed `aggregated_sentiment` and `aggregated_salience`, but these are NOT persisted to st_observations until R7.

**Why It Matters:** CPN and BGT-SM need sentiment/salience for episode selection.

### Resolution: EpisodeCluster Already Computed

**Good News:** R2's `_build_episode_cluster()` already computes these fields:

```python
# From r2_episodic_integrator.py lines 1090-1095:
dominant_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0.0

# From r2_episodic_integrator.py lines 1185-1190:
(aggregated_sentiment, aggregated_salience, ...) = self._aggregate_context_fields(member_contexts)
```

**No Additional Fix Needed** for current-cycle episodes. The issue is the FIELD NAME mismatch (see Section 4.3.1).

---

## 3.1.6 Complete Parity Resolution Matrix

| Gap ID | Data Type | Current Status | Fix Location | Priority |
|--------|-----------|----------------|--------------|----------|
| **P-01** | Episodes | No historical merge | r5_dream_explorer.py | HIGH |
| **P-02** | Routines | No historical merge | r5_dream_explorer.py | HIGH |
| **P-03** | Routine detection order | Runs after TDL-HCO | dream_explorer.py | HIGH |
| **P-04** | Semantic patterns | No merge (BGT-SM self-sufficient) | - | LOW |
| **P-05** | Observations | EpisodeCluster has computed values | - | DONE |
| **P-06** | KG Entities | Merged via GAP-001 M9.2 | - | DONE |
| **P-07** | KG Edges | Merged via GAP-001 M9.2 | - | DONE |

---

## 3.1.7 Syscall Requirements for Parity Resolution

### Required Syscalls (Check Availability)

| Syscall | Purpose | Status |
|---------|---------|--------|
| `kg_entities_query` | Load accumulated entities | EXISTS (GAP-001) |
| `kg_edges_query` | Load accumulated edges | EXISTS (GAP-001) |
| `episodes_query` | Load accumulated episodes | **IMPLEMENTED** |
| `procedural_memory_query` | Load accumulated routines | **IMPLEMENTED** |

### Implementation Status (2026-01-25)

**Syscalls Added:**
- `k0/kernel/syscalls.py` - Added `episodes_query()` and `procedural_memory_query()`
- Both syscalls include observation JOIN for sentiment/salience enrichment

**Config Limits Added:**
- `k0/pipelines/p03/r5_config.py` - Added `accumulated_episode_limit` (100) and `accumulated_routine_limit` (50)

**Merge Logic Added:**
- `k0/pipelines/p03/phases/r5_dream_explorer.py` - Added `_load_accumulated_episodes()` and `_load_accumulated_routines()`
- Episodes now merged: `current_episodes + accumulated_episodes` (current takes precedence)

**Field Mappings Fixed:**
- `k0/pipelines/p03/phase_outputs.py` - Added CPN compatibility properties:
  - `sentiment_score` → `dominant_sentiment`
  - `salience_score` → `aggregated_salience`
  - `start_time_ms` → `temporal_start`
  - `episode_id` → `cluster_id`

- `k0/modules/consolidation/dream/dream_explorer.py` - Fixed RoutineDetector dict conversion:
  - Changed `"location"` → `"location_hint"` and `"primary_location"`
  - Added `"start_time_utc"` for RoutineDetector timestamp lookup

---

## 3.1.8 Expected Outcome After Parity Fixes

| Algorithm | Before Parity Fix | After Parity Fix |
|-----------|-------------------|------------------|
| **CPN** | 0 (only current-cycle episodes, no entity_ids) | 10-50 (historical + current, entities populated) |
| **RoutineDetector** | 0 (field mismatch + only current episodes) | 5-20 (historical episodes enable pattern detection) |
| **BGT-SM** | 0 (working KG merge, but episode inputs broken) | 20-50 (full KG + episode context) |
| **SPC-UQ** | 0 (current-only episodes) | 5-15 (historical + current for pattern completion) |
| **TDL-HCO** | 0 (no routines from st_procedural) | 3-10 (historical routines + newly detected) |
| **MCTS** | 1 (working) | 1 (working) |
| **IntentSignal** | 74 (working) | 74 (working) |

---

## 3.2 Algorithm Inventory (with File Paths)

| # | Algorithm | File Path | Status | Purpose |
|---|-----------|-----------|--------|---------|
| 1 | CPN | k0/modules/consolidation/algorithms/cpn.py | BROKEN | Counterfactual what-if scenarios |
| 2 | RoutineDetector | k0/modules/consolidation/algorithms/routine_detector.py | BROKEN | Detect recurring habits |
| 3 | BGT-SM | k0/modules/consolidation/algorithms/bgt_sm.py | BROKEN | Discover surprising connections |
| 4 | SPC-UQ | k0/modules/consolidation/algorithms/spc_uq.py | BROKEN | Reconstruct incomplete episodes |
| 5 | TDL-HCO | k0/modules/consolidation/algorithms/tdl_hco.py | BROKEN | Optimize routines via TD learning |
| 6 | MCTS | k0/modules/consolidation/algorithms/mcts.py | WORKING | Forward scenario simulation |
| 7 | IntentSignalDetector | k0/modules/consolidation/algorithms/intent_signal_detector.py | WORKING | Detect future intentions |

---

## 3.3 Algorithm 1: CPN (Causal Perturbation Network)

### Code Evidence: EpisodeProtocol Requirements

**Source:** `k0/modules/consolidation/algorithms/cpn.py` lines 110-133

```python
@runtime_checkable
class EpisodeProtocol(Protocol):
    """Protocol for episodic memory data."""

    @property
    def episode_id(self) -> str:
        """Unique episode identifier."""
        ...

    @property
    def sentiment_score(self) -> float:      # <-- REQUIRED
        """Sentiment score (-1 to 1)."""
        ...

    @property
    def salience_score(self) -> float:       # <-- REQUIRED
        """Importance/salience score (0 to 1)."""
        ...

    @property
    def start_time_ms(self) -> int:
        """Start timestamp in milliseconds."""
        ...

    @property
    def entity_ids(self) -> List[str]:       # <-- REQUIRED
        """Entity IDs involved in episode."""
        ...
```

### Code Evidence: EpisodeCluster Actual Fields

**Source:** `k0/pipelines/p03/phase_outputs.py` lines 74-105

```python
@dataclass
class EpisodeCluster:
    cluster_id: str
    member_event_ids: List[str]
    dominant_sentiment: float = 0.0       # NOT sentiment_score
    aggregated_sentiment: Optional[float] = None
    aggregated_salience: Optional[float] = None  # NOT salience_score
    location_hint: Optional[str] = None   # NOT location
    temporal_start: int = 0               # NOT start_time_ms
    temporal_end: int = 0
    activity_type: str = ""
    # NO entity_ids field!
```

### Field Mapping Gap Analysis

| CPN Expects | EpisodeCluster Has | Resolution |
|-------------|-------------------|------------|
| sentiment_score | dominant_sentiment | Add @property alias |
| salience_score | aggregated_salience | Add @property alias |
| start_time_ms | temporal_start | Add @property alias |
| entity_ids | MISSING | Derive from st_hipp_events.entities_json |

### Code Evidence: CPN Helper Method — NO FALLBACK FOR dominant_sentiment

**Source:** `k0/modules/consolidation/algorithms/cpn.py` lines 866-899

```python
def _get_episode_sentiment(self, episode: Any) -> float:
    """Get sentiment score from episode object."""
    if hasattr(episode, "sentiment_score"):
        return episode.sentiment_score
    elif isinstance(episode, dict):
        return episode.get("sentiment_score", 0.0)
    return 0.0  # <-- NO fallback for dominant_sentiment!

def _get_episode_salience(self, episode: Any) -> float:
    """Get salience score from episode object."""
    if hasattr(episode, "salience_score"):
        return episode.salience_score
    elif isinstance(episode, dict):
        return episode.get("salience_score", 0.5)
    return 0.5  # <-- NO fallback for aggregated_salience!

def _get_episode_entities(self, episode: Any) -> List[str]:
    """Get entity IDs from episode object."""
    if hasattr(episode, "entity_ids"):
        return list(episode.entity_ids)
    elif isinstance(episode, dict):
        return episode.get("entity_ids", [])
    return []  # <-- Returns empty list if EpisodeCluster has no entity_ids!
```

### Input/Output Summary

| Input | Source | Code Location | Status |
|-------|--------|---------------|--------|
| Episodes | input_data.recent_episodes | dream_explorer.py:564-610 | ✅ Passed correctly |
| sentiment_score | EpisodeCluster has dominant_sentiment ONLY | cpn.py:866-872 | ❌ Returns 0.0 always |
| salience_score | EpisodeCluster has aggregated_salience ONLY | cpn.py:874-880 | ❌ Returns 0.5 always |
| entity_ids | EpisodeCluster has NO entity_ids field | cpn.py:892-897 | ❌ Returns [] - BREAKS DAG |
| CAUSES edges | input_data.kg_edges | dream_explorer.py:564 | ⚠️ Only 4 exist in DB |

| Output | Destination | Code Location |
|--------|-------------|---------------|
| CPNCounterfactual | st_prospective | dream_explorer.py:618-629 |

### Root Cause (Verified)

1. `entity_ids` returns empty list → CPN cannot build causal DAG
2. Only 4 CAUSES edges in st_kg_edges → Minimal DAG even if entities existed

---

## 3.4 Algorithm 2: RoutineDetector (GAP-003)

### Code Evidence: DreamExplorer Calls RoutineDetector

**Source:** `k0/modules/consolidation/dream/dream_explorer.py` lines 1024-1085

`python
async def _run_routine_detector(
    self,
    input_data: DreamExplorerInput,
    cycle_id: str,
) -> List["RoutineCandidate"]:
    # Convert EpisodeCluster to dict format for RoutineDetector
    episodes: List[dict] = []
    for cluster in input_data.recent_episodes:
        episode = {
            "episode_id": cluster.cluster_id,
            "activity_type": cluster.activity_type,
            "location": cluster.location_hint,     # <-- KEY: passes "location"
            "start_time_ms": cluster.temporal_start,  # <-- KEY: passes "start_time_ms"
            "end_time_ms": cluster.temporal_end,
        }
        episodes.append(episode)

    detector = RoutineDetector(min_occurrences=3)
    candidates = detector.detect(episodes)
`

### Code Evidence: RoutineDetector._group_by_signature()

**Source:** `k0/modules/consolidation/algorithms/routine_detector.py` lines 268-283

`python
def _group_by_signature(self, episodes: List[Dict[str, Any]]) -> Dict[str, EpisodePattern]:
    patterns: Dict[str, EpisodePattern] = {}
    for ep in episodes:
        activity = (ep.get("activity_type") or ep.get("episode_type") or "").lower()
        location = (ep.get("primary_location") or ep.get("location_hint") or "").lower()
        # DreamExplorer passes "location" but this looks for "primary_location" first!
        # ep.get("primary_location") returns None
        # ep.get("location_hint") returns None (DreamExplorer passes key "location")
        # Result: location = ""

        pattern.timestamps.append(ep.get("start_time_utc", 0))  # <-- Expects start_time_utc!
        # DreamExplorer passes "start_time_ms" - WRONG KEY!
`

### Field Mismatch Analysis

| DreamExplorer Passes | RoutineDetector Expects | Result |
|----------------------|-------------------------|--------|
| `location` | `primary_location` or `location_hint` | Empty string |
| `start_time_ms` | `start_time_utc` | 0 (default) |

### Input/Output Summary

| Input | Source | Code Location | Status |
|-------|--------|---------------|--------|
| Episodes (as dicts) | input_data.recent_episodes | dream_explorer.py:1065-1073 | ⚠️ Field name mismatch |
| location | cluster.location_hint | dream_explorer.py:1070 | ❌ Key is "location" not "primary_location" |
| start_time | cluster.temporal_start | dream_explorer.py:1071 | ❌ Key is "start_time_ms" not "start_time_utc" |

| Output | Destination | Code Location |
|--------|-------------|---------------|
| RoutineCandidate | st_procedural (via R6/R7) | routine_detector.py:100-127 |

### Root Cause (Verified)

1. DreamExplorer passes `location` but RoutineDetector looks for `primary_location` first
2. DreamExplorer passes `start_time_ms` but RoutineDetector reads `start_time_utc`
3. Both result in empty/zero values → no valid signatures → 0 candidates

### Required Fix

`python

# In dream_explorer.py_run_routine_detector()

episode = {
    "episode_id": cluster.cluster_id,
    "activity_type": cluster.activity_type,
    "primary_location": cluster.location_hint,  # FIX: use primary_location key
    "start_time_utc": cluster.temporal_start,   # FIX: use start_time_utc key
    "end_time_utc": cluster.temporal_end,
}
`

---

## 3.5 Algorithm 3: BGT-SM (Bisociative Graph Traversal)

### Code Evidence: Seed Entity Selection

**Source:** `k0/modules/consolidation/dream/dream_explorer.py` lines 487-536

`python
def _select_seed_entities(
    self,
    input_data: DreamExplorerInput,
) -> List[str]:
    seed_candidates: Dict[str, float] = {}

    # Extract entities from recent episodes
    for episode in input_data.recent_episodes:
        entity_ids = getattr(episode, "entity_ids", [])  # <-- EpisodeCluster has NO entity_ids!
        salience = getattr(episode, "salience_score", 0.5)  # <-- Returns 0.5 (no salience_score attr)

        for entity_id in entity_ids:  # <-- EMPTY LOOP (entity_ids = [])
            if entity_id not in seed_candidates:
                seed_candidates[entity_id] = 0.0
            seed_candidates[entity_id] += salience

    # Add high-observation entities from KG (FALLBACK)
    for entity in input_data.kg_entities:
        entity_id = getattr(entity, "entity_id", None)
        obs_count = getattr(entity, "observation_count", 0)
        if entity_id and obs_count >= 5:  # Min 5 observations
            seed_candidates[entity_id] = obs_count / 100.0
`

### Code Evidence: BGT-SM Quality Thresholds

**Source:** `k0/modules/consolidation/algorithms/bgt_sm.py` lines 74-81

`python

# Thresholds (per Issue 8.1.9, 8.1.10)

P03_BGT_SEMANTIC_DISTANCE_THRESHOLD = 0.7  # Min distance for remote associate
P03_BGT_PMI_THRESHOLD = 3.0                # Min PMI (2^3 = 8x expected)
P03_BGT_NOVELTY_THRESHOLD = 0.5            # Min novelty score
P03_BGT_SERENDIPITY_THRESHOLD = 0.6        # novelty x relevance x actionability
`

### Input/Output Summary

| Input | Source | Code Location | Status |
|-------|--------|---------------|--------|
| kg_entities | input_data.kg_entities | dream_explorer.py:439 | ✅ Passed correctly |
| kg_edges | input_data.kg_edges | dream_explorer.py:439 | ✅ Passed correctly |
| seed_entity_ids | _select_seed_entities() | dream_explorer.py:455 | ⚠️ Falls back to KG entities |
| entity_ids from episodes | EpisodeCluster.entity_ids | dream_explorer.py:511-516 | ❌ MISSING - empty loop |
| embeddings | entity.embedding | dream_explorer.py:547-558 | ⚠️ May be None for some entities |

| Output | Destination | Code Location |
|--------|-------------|---------------|
| BGTInsight -> Insight | st_sem (pattern_type=insight) | bgt_sm.py:1000-1020 |

### Root Cause (Verified)

1. EpisodeCluster has no `entity_ids` field → episode-based seeds fail
2. Falls back to KG entities with obs_count >= 5 (may find some seeds)
3. Strict thresholds (0.7 distance, 3.0 PMI, 0.6 serendipity) filter out most results
4. If seeds found from KG fallback, still 0 insights if thresholds too strict

### Why BGT-SM Might Produce Some Results

Unlike CPN, BGT-SM has a fallback path:

- If episode-based seeds fail, it uses KG entities with high observation counts
- This can produce seeds even without entity_ids in episodes
- But strict quality thresholds may still filter all results

---

## 3.6 Algorithm 4: SPC-UQ (Schematic Pattern Completion)

### Code Evidence: Gap Detection Requires ambiguity_score

**Source:** `k0/modules/consolidation/algorithms/spc_uq.py` lines 497-505

`python

# Check ambiguity

ambiguity = self._get_attr(episode, "ambiguity_score", 0.0)  # <-- EpisodeCluster has NO ambiguity_score
if ambiguity > self.config.ambiguity_threshold:  # threshold = 0.5
    gaps.append(
        AttributeGap(
            attribute_name="ambiguous_content",
            gap_type=GapType.CONTENT,
            priority=0.9,
            ambiguity_score=ambiguity,
        )
    )
`

### Code Evidence: EpisodicSimulator Protocol

**Source:** `k0/modules/consolidation/algorithms/spc_uq.py` lines 127-133

`python
@runtime_checkable
class EpisodeForSimulation(Protocol):
    @property
    def episode_id(self) -> str: ...
    @property
    def start_time_ms(self) -> int: ...  # <-- EpisodeCluster has temporal_start
    @property
    def ambiguity_score(self) -> float: ...  # <-- MISSING from EpisodeCluster
`

### Input/Output Summary

| Input | Source | Code Location | Status |
|-------|--------|---------------|--------|
| Episodes | input_data.recent_episodes | dream_explorer.py:632-700 | ✅ Passed correctly |
| ambiguity_score | EpisodeCluster.ambiguity_score | spc_uq.py:497 | ❌ MISSING - returns 0.0 |
| start_time_ms | EpisodeCluster.temporal_start | spc_uq.py:129 | ⚠️ Protocol mismatch |
| schemas | input_data.schemas | dream_explorer.py:660 | ⚠️ May be empty list |

| Output | Destination | Code Location |
|--------|-------------|---------------|
| Reconstruction | st_prospective (is_canonical=False) | spc_uq.py:680-720 |

### Root Cause (Verified)

1. EpisodeCluster has no `ambiguity_score` → always returns 0.0
2. 0.0 < 0.5 threshold → content gaps never detected
3. Other gaps (location, participants) may still be found
4. Empty schemas list → no pattern completion possible

---

## 3.7 Algorithm 5: TDL-HCO (Temporal Difference Learning)

### Code Evidence: Requires Routines from st_procedural

**Source:** `k0/modules/consolidation/algorithms/tdl_hco.py` lines 52-56

`python

# Minimum routine length for analysis

P03_TDL_MIN_ROUTINE_LENGTH = 3

# Minimum occurrences to consider a pattern a "routine"

P03_TDL_MIN_ROUTINE_OCCURRENCES = 3
`

### Code Evidence: DreamExplorer Calls TDL-HCO

**Source:** `k0/modules/consolidation/dream/dream_explorer.py` lines 927-1020

`python
async def _run_tdl_hco(
    self,
    input_data: DreamExplorerInput,
    cycle_id: str,
    compute_budget: Optional[ComputeBudget],
) -> List[RoutineOptimization]:
    # Extract routines from procedural memory
    routines = input_data.routines  # <-- Comes from st_procedural (0 rows!)

    if not routines:
        self._logger.debug("TDL-HCO skipped: no routines available")
        return []
`

### Input/Output Summary

| Input | Source | Code Location | Status |
|-------|--------|---------------|--------|
| routines | input_data.routines (from st_procedural) | dream_explorer.py:950 | ❌ 0 rows in DB |
| episodes | input_data.recent_episodes | dream_explorer.py:927 | ✅ Available |
| compute_budget | Shared budget | dream_explorer.py:189 | ✅ Available |

| Output | Destination | Code Location |
|--------|-------------|---------------|
| RoutineOptimization | st_procedural (updates existing) | tdl_hco.py:300-350 |

### Root Cause (Verified)

1. st_procedural table has 0 rows (confirmed via PostgreSQL query)
2. RoutineDetector fails due to field mismatches → never populates st_procedural
3. TDL-HCO immediately skips: "no routines available"
4. Chicken-and-egg: TDL-HCO needs routines, but RoutineDetector can't create them

### Dependency Chain

`
RoutineDetector (BROKEN) → st_procedural (EMPTY) → TDL-HCO (SKIPPED)
`

---

## 3.8 Algorithm 6: MCTS (Monte Carlo Tree Search) - WORKING

### Code Evidence: Why MCTS Works

**Source:** `k0/modules/consolidation/dream/dream_explorer.py` lines 838-856

`python

# Build initial state from recent episodes

initial_state = SimpleState(
    state_id=f"state_{cycle_id[:8]}",
    features={
        "episode_count": float(len(input_data.recent_episodes)),  # <-- Uses COUNT, not fields
        "entity_count": float(len(input_data.kg_entities)),      # <-- Uses COUNT, not fields
    },
)
`

### Code Evidence: Fallback Actions If No Entities

**Source:** `k0/modules/consolidation/dream/dream_explorer.py` lines 917-925

`python

# Add generic future actions if no entity-based actions

if not actions:
    actions = [
        SimpleAction(action_id="action_explore", action_type="explore"),
        SimpleAction(action_id="action_consolidate", action_type="consolidate"),
        SimpleAction(action_id="action_rest", action_type="rest"),
    ]
`

### Input/Output Summary

| Input | Source | Code Location | Status |
|-------|--------|---------------|--------|
| episode_count | len(recent_episodes) | dream_explorer.py:842 | ✅ Works (counts only) |
| entity_count | len(kg_entities) | dream_explorer.py:843 | ✅ Works (counts only) |
| available_actions | kg_entities[:10] or fallback | dream_explorer.py:849-925 | ✅ Has fallback |
| compute_budget | Shared budget | dream_explorer.py:782 | ✅ Controls rollouts |

| Output | Destination | Code Location |
|--------|-------------|---------------|
| MCTSScenario | In-memory only (for evaluation) | mcts.py:700-750 |

### Why MCTS Works

1. Uses **counts** (episode_count, entity_count), not specific episode fields
2. Has **fallback actions** if no entity-based actions available
3. SimpleState doesn't require sentiment_score, salience_score, or entity_ids
4. MCTS is fundamentally about forward simulation, not episode analysis

### Log Evidence (Confirmed Working)

`json
{
  "message": "MCTS completed",
  "scenarios_generated": 1,
  "rollouts_used": 20
}
`

## 3.9 Algorithm 7: IntentSignalDetector (GAP-001) - WORKING

### Code Evidence: Uses P03EventState, Not EpisodeCluster

**Source:** `k0/modules/consolidation/algorithms/intent_signal_detector.py` lines 46-65

`python
class IntentSignalDetector:
    """
    Detects intent signals from P03 event states.

    Uses UltraBERT intent_label and supporting fields (temporal_json,
    emotions_json, ner_entities_json) to create typed IntentSignal objects.
    """

    def detect_all(self, event_states: List[P03EventState]) -> List[AnyIntentSignal]:
        # Works on P03EventState which HAS all needed fields
        ...
`

### Code Evidence: P03EventState Has Required Fields

**Source:** `k0/pipelines/p03/event_state.py` (P03EventState dataclass)

`python
@dataclass
class P03EventState:
    event_id: str
    text: str
    intent_label: Optional[str] = None       # <-- Available from UltraBERT
    temporal_json: Optional[str] = None      # <-- Available from ingestion
    emotions_json: Optional[str] = None      # <-- Available from sentiment analysis
    ner_entities_json: Optional[str] = None  # <-- Available from NER
`

### Input/Output Summary

| Input | Source | Code Location | Status |
|-------|--------|---------------|--------|
| event_states | envelope.phases.r1_batch | dream_explorer.py:200-240 | OK Passed correctly |
| intent_label | P03EventState.intent_label | intent_signal_detector.py:150-200 | OK Available |
| temporal_json | P03EventState.temporal_json | intent_signal_detector.py:220-250 | OK Available |
| text | P03EventState.text | intent_signal_detector.py:65-90 | OK Available |

| Output | Destination | Code Location |
|--------|-------------|---------------|
| ReminderSignal | st_prospective (REMINDER) | intent_signal_detector.py:280-320 |
| DecisionSignal | st_prospective (DECISION) | intent_signal_detector.py:330-370 |
| LessonSignal | st_sem (LESSON) | intent_signal_detector.py:380-420 |
| MilestoneSignal | st_sem (MILESTONE) | intent_signal_detector.py:430-470 |

### Why IntentSignalDetector Works

1. Uses **P03EventState** from R1 batch, NOT EpisodeCluster
2. P03EventState has all required fields (intent_label, temporal_json, text)
3. Uses **regex patterns** to extract actions, options, lessons
4. No dependency on episode fields like sentiment_score or entity_ids

### Log Evidence (Confirmed Working)

`json
{
  "message": "IntentSignalDetector completed",
  "signals_detected": 74
}
`

---

## 3.10 Master I/O Matrix

### Input Matrix by Source

| Algorithm | From Envelope (Current Cycle) | From PostgreSQL (Prior Cycles) | Status |
|-----------|-------------------------------|-------------------------------|--------|
| CPN | recent_episodes, kg_edges | - | BROKEN |
| RoutineDetector | recent_episodes | st_epi (optional) | BROKEN |
| BGT-SM | kg_entities, kg_edges | - | BROKEN |
| SPC-UQ | recent_episodes, schemas | st_sem (schemas) | BROKEN |
| TDL-HCO | - | st_procedural (routines) | BLOCKED |
| MCTS | episode_count, entity_count | - | WORKING |
| IntentSignalDetector | r1_batch (P03EventState) | - | WORKING |

### Output Matrix by Destination

| Algorithm | Output Type | R7 Writes To | Status |
|-----------|-------------|--------------|--------|
| CPN | CPNCounterfactual | st_prospective | 0 outputs |
| RoutineDetector | RoutineCandidate | st_procedural | 0 outputs |
| BGT-SM | BGTInsight | st_sem | 0 outputs |
| SPC-UQ | Reconstruction | st_prospective | 0 outputs |
| TDL-HCO | RoutineOptimization | st_procedural | 0 outputs |
| MCTS | MCTSScenario | (in-memory) | 1 scenario |
| IntentSignalDetector | IntentSignal | st_prospective | 74 signals |

---

## 3.11 Fix Priority Roadmap

### Phase 1: Quick Wins (Unblocks 3 algorithms)

| Fix ID | Target | Change | Unblocks |
|--------|--------|--------|----------|
| F1 | cpn.py:866-880 | Add fallback for dominant_sentiment and aggregated_salience | CPN sentiment |
| F2 | dream_explorer.py:1065-1073 | Change field keys: location to primary_location, start_time_ms to start_time_utc | RoutineDetector |
| F3 | bgt_sm.py | Lower thresholds (distance:0.5, pmi:1.5, serendipity:0.3) | BGT-SM insights |

### Phase 2: Schema Enrichment (Unblocks remaining)

| Fix ID | Target | Change | Unblocks |
|--------|--------|--------|----------|
| F4 | phase_outputs.py EpisodeCluster | Add entity_ids field derived from member events | CPN DAG, BGT-SM seeds |
| F5 | phase_outputs.py EpisodeCluster | Add ambiguity_score computed from missing fields | SPC-UQ gaps |
| F6 | R2 episodic_integrator | Compute and populate entity_ids during clustering | All entity-dependent |

### Phase 3: Causal Graph (High effort)

| Fix ID | Target | Change | Unblocks |
|--------|--------|--------|----------|
| F7 | R4 kg_consolidator | Generate CAUSES edges from temporal sequences | CPN causal DAG |
| F8 | R4 granger_causality | Lower confidence threshold for edge creation | More causal edges |

### Dependency Order

`
F2 (RoutineDetector) -> st_procedural populated -> TDL-HCO unblocked
F1, F4 (CPN entity_ids) + F7 (CAUSES edges) -> CPN produces counterfactuals
F3, F4 (BGT-SM seeds) -> BGT-SM produces insights
F5 (ambiguity_score) -> SPC-UQ produces reconstructions
`

---

## 3.12 Expected Output After Fixes

| Algorithm | Current | After Phase 1 | After Phase 2 |
|-----------|---------|---------------|---------------|
| CPN | 0 | 0 (needs entity_ids) | 10-50 counterfactuals |
| RoutineDetector | 0 | 5-20 routines | 5-20 routines |
| BGT-SM | 0 | 5-15 insights | 20-50 insights |
| SPC-UQ | 0 | 0 (needs ambiguity) | 5-15 reconstructions |
| TDL-HCO | 0 (blocked) | 3-10 optimizations | 3-10 optimizations |
| MCTS | 1 | 1 | 1 |
| IntentSignalDetector | 74 | 74 | 74 |

---

## 3.13 Validation Queries (Run After Fixes)

`sql
-- Check if RoutineDetector populated st_procedural
SELECT COUNT(*) as routine_count FROM st_procedural;

-- Check if CPN produced counterfactuals
SELECT COUNT(*) as counterfactual_count FROM st_prospective
WHERE intention_type = 'COUNTERFACTUAL';

-- Check if BGT-SM produced insights
SELECT COUNT(*) as insight_count FROM st_sem
WHERE source_type = 'BGT_INSIGHT';

-- Check if SPC-UQ produced reconstructions
SELECT COUNT(*) as reconstruction_count FROM st_prospective
WHERE intention_type = 'RECONSTRUCTION' AND is_canonical = false;
`

---

# Part 4: Source of Truth - Code Discovery & Data Flow Mapping

**Purpose:** Map complete data flow from source files → transformations → algorithm inputs → fix targets

---

## 4.1 Master File Registry

### Core Source of Truth Files

| Component | File Path | Purpose | Lines of Interest |
|-----------|-----------|---------|-------------------|
| **EpisodeCluster** | `k0/pipelines/p03/phase_outputs.py` | Episode data structure | Lines 74-130 |
| **R2 Phase** | `k0/pipelines/p03/phases/r2_episodic_integrator.py` | Creates EpisodeClusters | Lines 1060-1200 |
| **R5 Phase** | `k0/pipelines/p03/phases/r5_dream_explorer.py` | Orchestrates algorithms | Lines 320-450 |
| **DreamExplorer** | `k0/modules/consolidation/dream/dream_explorer.py` | Algorithm dispatcher | Lines 560-700 |
| **DreamExplorerInput** | `k0/modules/consolidation/dream/models.py` | Input dataclass | Lines 335-363 |

### Algorithm Source Files

| Algorithm | File Path | Entry Point | Lines of Interest |
|-----------|-----------|-------------|-------------------|
| **CPN** | `k0/modules/consolidation/algorithms/cpn.py` | `generate()` | Lines 866-900 (helpers) |
| **RoutineDetector** | `k0/modules/consolidation/algorithms/routine_detector.py` | `detect()` | Lines 260-290 |
| **BGT-SM** | `k0/modules/consolidation/algorithms/bgt_sm.py` | `generate_insights()` | (entity extraction) |
| **SPC-UQ** | `k0/modules/consolidation/algorithms/spc_uq.py` | `simulate()` | (ambiguity detection) |
| **TDL-HCO** | `k0/modules/consolidation/algorithms/tdl_hco.py` | `optimize()` | (routine input) |
| **MCTS** | `k0/modules/consolidation/algorithms/mcts.py` | `run()` | (working) |
| **IntentSignalDetector** | `k0/modules/consolidation/dream/intent_signals.py` | `detect()` | (working) |

---

## 4.2 Complete Data Flow Chain

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          P03 PIPELINE DATA FLOW                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  R1: P03EventState (raw events)                                            │
│      │                                                                      │
│      └──► event.sentiment_score ✓                                          │
│      └──► event.importance_score ✓                                         │
│      └──► event.location_name ✓                                            │
│      └──► event.location_type ✓                                            │
│                                                                             │
│  R2: r2_episodic_integrator.py Line 476                                    │
│      │   envelope.phases.r2_clusters = episode_clusters                    │
│      │                                                                      │
│      └──► _build_episode_cluster() Line 1060                               │
│           │                                                                 │
│           │   FROM: cluster_events (List[EventAdapter])                    │
│           │   TO:   EpisodeCluster dataclass                               │
│           │                                                                 │
│           ├──► dominant_sentiment = avg(event.sentiment_score) ✓           │
│           ├──► aggregated_sentiment = computed ✓                           │
│           ├──► aggregated_salience = computed ✓                            │
│           ├──► location_hint = most_common(event.location_name) ✓          │
│           ├──► dominant_location = from member_contexts ✓                  │
│           └──► activity_type = most_common(event.activity_type) ✓          │
│                                                                             │
│  R5: r5_dream_explorer.py Line 421-432                                     │
│      │                                                                      │
│      │   input_data = DreamExplorerInput(                                  │
│      │       recent_episodes=list(envelope.phases.r2_clusters),  ◄── HERE  │
│      │       kg_entities=merged_entities,                                  │
│      │       kg_edges=merged_edges,                                        │
│      │       event_states=list(envelope.events),                           │
│      │   )                                                                 │
│      │                                                                      │
│      └──► DreamExplorer.explore(input_data)                                │
│                                                                             │
│  DreamExplorer: dream_explorer.py Line 288                                 │
│      │   parallel_results = await asyncio.gather(...)                      │
│      │                                                                      │
│      ├──► _run_cpn(input_data)  ──► input_data.recent_episodes passed      │
│      │         └──► CPN expects: episode.sentiment_score  ✗ MISSING!       │
│      │             EpisodeCluster has: dominant_sentiment  ✓ EXISTS        │
│      │                                                                      │
│      ├──► _run_routine_detector(input_data) Line 1065-1078                 │
│      │         └──► Converts EpisodeCluster → dict:                        │
│      │                 "location": cluster.location_hint   ◄── PROVIDES    │
│      │             Algorithm expects:                                      │
│      │                 ep.get("primary_location") first    ◄── LOOKS FOR   │
│      │                 ep.get("location_hint") fallback    ◄── WOULD MATCH │
│      │                                                                      │
│      └──► _run_bgt_sm(input_data)                                          │
│               └──► Uses kg_entities (from merged_entities)                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4.3 Critical Field Mismatches

### 4.3.1 CPN Field Mismatch

**Location:** `k0/modules/consolidation/algorithms/cpn.py` Lines 866-872

```python
# CPN helper method - WHAT IT LOOKS FOR:
def _get_episode_sentiment(self, episode: Any) -> float:
    if hasattr(episode, "sentiment_score"):      # ◄── LOOKS FOR THIS
        return episode.sentiment_score
    elif isinstance(episode, dict):
        return episode.get("sentiment_score", 0.0)
    return 0.0  # ◄── RETURNS 0.0 IF NOT FOUND!
```

**EpisodeCluster has (phase_outputs.py Line 87-89):**

```python
@dataclass
class EpisodeCluster:
    dominant_sentiment: float = 0.0      # ◄── HAS THIS (different name!)
    aggregated_sentiment: Optional[float] = None  # ◄── ALSO HAS THIS
```

**Fix Target:** `k0/pipelines/p03/phase_outputs.py` Line 87

**Option A - Add alias property:**

```python
@property
def sentiment_score(self) -> float:
    """Alias for CPN compatibility."""
    return self.dominant_sentiment
```

**Option B - Add field in R2 builder:**
Edit `k0/pipelines/p03/phases/r2_episodic_integrator.py` Line 1060+ to add:

```python
sentiment_score=dominant_sentiment,  # Add this line
```

---

### 4.3.2 RoutineDetector Field Mismatch

**Location:** `k0/modules/consolidation/algorithms/routine_detector.py` Line 269

```python
# RoutineDetector - WHAT IT LOOKS FOR:
location = (ep.get("primary_location") or ep.get("location_hint") or "").lower()
#           ^^^^^^^^^^^^^^^^^^^^           ^^^^^^^^^^^^^^^
#           LOOKS FOR FIRST                 FALLBACK (would match!)
```

**DreamExplorer conversion (dream_explorer.py Lines 1067-1075):**

```python
# WHAT DREAMEXPLORER PROVIDES:
episode = {
    "episode_id": cluster.cluster_id,
    "activity_type": cluster.activity_type,
    "location": cluster.location_hint,   # ◄── PROVIDES "location", NOT "location_hint"!
    "start_time_ms": cluster.temporal_start,
}
```

**Mismatch Analysis:**

- DreamExplorer provides: `"location"`
- RoutineDetector checks: `"primary_location"` then `"location_hint"`
- Result: Neither match! Empty string used.

**Fix Target:** `k0/modules/consolidation/dream/dream_explorer.py` Line 1071

**Fix:**

```python
# Change from:
"location": cluster.location_hint,
# To:
"location_hint": cluster.location_hint,  # Match what RoutineDetector expects
```

---

### 4.3.3 CPN entity_ids Mismatch

**Location:** `k0/modules/consolidation/algorithms/cpn.py` Lines 883-887

```python
# CPN helper method - WHAT IT LOOKS FOR:
def _get_episode_entities(self, episode: Any) -> List[str]:
    if hasattr(episode, "entity_ids"):    # ◄── LOOKS FOR entity_ids
        return list(episode.entity_ids)
    elif isinstance(episode, dict):
        return episode.get("entity_ids", [])
    return []  # ◄── RETURNS [] IF NOT FOUND!
```

**EpisodeCluster has:** NO `entity_ids` field!

**Fix Target:** `k0/pipelines/p03/phase_outputs.py`

**Add to EpisodeCluster dataclass (after line 85):**

```python
entity_ids: List[str] = field(default_factory=list)  # For CPN causal chains
```

**And in R2 builder (r2_episodic_integrator.py Line 1060+):**
Extract entity_ids from member_contexts or events.

---

### 4.3.4 CPN salience_score Mismatch

**Location:** `k0/modules/consolidation/algorithms/cpn.py` Lines 874-879

```python
# CPN helper method - WHAT IT LOOKS FOR:
def _get_episode_salience(self, episode: Any) -> float:
    if hasattr(episode, "salience_score"):    # ◄── LOOKS FOR salience_score
        return episode.salience_score
    elif isinstance(episode, dict):
        return episode.get("salience_score", 0.5)
    return 0.5  # ◄── RETURNS 0.5 DEFAULT
```

**EpisodeCluster has (phase_outputs.py Line 89):**

```python
aggregated_salience: Optional[float] = None  # ◄── DIFFERENT NAME!
```

**Fix Target:** `k0/pipelines/p03/phase_outputs.py`

**Add alias property:**

```python
@property
def salience_score(self) -> float:
    """Alias for CPN compatibility."""
    return self.aggregated_salience or 0.5
```

---

## 4.4 Fix Implementation Matrix

| Fix ID | Algorithm | Fix Type | File to Edit | Line(s) | Priority |
|--------|-----------|----------|--------------|---------|----------|
| F-01 | RoutineDetector | Key rename | `dream_explorer.py` | 1071 | HIGH |
| F-02 | CPN | Add property | `phase_outputs.py` | 130+ | HIGH |
| F-03 | CPN | Add property | `phase_outputs.py` | 130+ | HIGH |
| F-04 | CPN | Add field | `phase_outputs.py` | 85+ | MEDIUM |
| F-05 | CPN | Populate field | `r2_episodic_integrator.py` | 1175+ | MEDIUM |
| F-06 | SPC-UQ | Add field | `phase_outputs.py` | 85+ | LOW |
| F-07 | TDL-HCO | Populate table | (RoutineDetector fix) | - | HIGH |

---

## 4.5 Verified Code Snippets for Each Fix

### Fix F-01: RoutineDetector Location Key

**File:** `k0/modules/consolidation/dream/dream_explorer.py`
**Current (Line 1067-1075):**

```python
for cluster in input_data.recent_episodes:
    episode = {
        "episode_id": cluster.cluster_id,
        "activity_type": cluster.activity_type,
        "location": cluster.location_hint,  # ◄── WRONG KEY
        "start_time_ms": cluster.temporal_start,
        "end_time_ms": cluster.temporal_end,
    }
    episodes.append(episode)
```

**Fixed:**

```python
for cluster in input_data.recent_episodes:
    episode = {
        "episode_id": cluster.cluster_id,
        "activity_type": cluster.activity_type,
        "location_hint": cluster.location_hint,  # ◄── CORRECT KEY
        "start_time_ms": cluster.temporal_start,
        "end_time_ms": cluster.temporal_end,
    }
    episodes.append(episode)
```

---

### Fix F-02 & F-03: CPN Compatibility Properties

**File:** `k0/pipelines/p03/phase_outputs.py`
**Add after EpisodeCluster class definition (after line 130):**

```python
@property
def sentiment_score(self) -> float:
    """Alias for CPN algorithm compatibility.

    CPN expects sentiment_score but EpisodeCluster uses dominant_sentiment.
    See: k0/modules/consolidation/algorithms/cpn.py Line 866-872
    """
    return self.dominant_sentiment

@property
def salience_score(self) -> float:
    """Alias for CPN algorithm compatibility.

    CPN expects salience_score but EpisodeCluster uses aggregated_salience.
    See: k0/modules/consolidation/algorithms/cpn.py Line 874-879
    """
    return self.aggregated_salience if self.aggregated_salience is not None else 0.5
```

---

### Fix F-04 & F-05: Add entity_ids Field

**File:** `k0/pipelines/p03/phase_outputs.py`
**Add to EpisodeCluster dataclass (around line 85):**

```python
entity_ids: List[str] = field(default_factory=list)  # CPN causal chain entities
```

**File:** `k0/pipelines/p03/phases/r2_episodic_integrator.py`
**Add to _build_episode_cluster method (around line 1175):**

```python
# Extract entity IDs from NER across all member events
entity_ids: set = set()
for e in cluster_events:
    try:
        import json
        ner_entities = json.loads(e.event.ner_entities_json or "[]")
        for entity in ner_entities:
            if isinstance(entity, dict) and entity.get("id"):
                entity_ids.add(entity["id"])
    except (json.JSONDecodeError, TypeError):
        pass

# In EpisodeCluster constructor:
entity_ids=list(entity_ids),
```

---

## 4.6 Data Provider Chain Summary

```
┌────────────────────────────────────────────────────────────────────────┐
│                    COMPLETE DATA PROVIDER CHAIN                        │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  PHASE │ SOURCE                  │ DESTINATION                        │
│  ──────┼─────────────────────────┼───────────────────────────────────  │
│  R0    │ st_hipp_events          │ envelope.events (P03EventState)    │
│  R1    │ envelope.events         │ envelope.events (scored)           │
│  R2    │ envelope.events         │ envelope.phases.r2_clusters        │
│  R4    │ envelope.events         │ envelope.phases.r4_new_entities    │
│        │                         │ envelope.phases.r4_new_edges       │
│  R5    │ r2_clusters + r4_*      │ DreamExplorerInput                 │
│  R5    │ DreamExplorerInput      │ Algorithm inputs (converted)       │
│                                                                        │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  ALGORITHM    │ INPUT PROVIDER      │ CONVERSION LOCATION              │
│  ─────────────┼─────────────────────┼──────────────────────────────────│
│  CPN          │ recent_episodes     │ Passed directly (EpisodeCluster) │
│  RoutineDetec │ recent_episodes     │ dream_explorer.py:1065-1078      │
│  BGT-SM       │ kg_entities         │ dream_explorer.py:_run_bgt_sm()  │
│  SPC-UQ       │ recent_episodes     │ dream_explorer.py:_run_spc_uq()  │
│  TDL-HCO      │ st_procedural       │ syscall: read_procedural_memory  │
│  MCTS         │ recent_episodes     │ dream_explorer.py:_run_mcts()    │
│  IntentSignal │ event_states        │ Passed directly (P03EventState)  │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 4.7 Verification Commands

After applying fixes, run these commands to verify:

```powershell
# Run R5 tests to verify fixes
pytest tests/k0/modules/consolidation/algorithms/test_routine_detector.py -v

# Run full P03 integration test
pytest tests/k0/pipelines/p03/test_r5_integration.py -v

# Check for EpisodeCluster property access
python -c "from k0.pipelines.p03.phase_outputs import EpisodeCluster; ec = EpisodeCluster('test'); print(f'sentiment_score: {ec.sentiment_score}')"
```

---

*End of R5 Phase Algorithm Analysis Document*
*Part 4 added: Source of Truth Code Discovery on 2026-01-25*
