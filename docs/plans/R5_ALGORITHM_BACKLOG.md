# R5 Algorithm Remediation Backlog

**Created:** 2026-01-25
**Source:** R5_PHASE_ALGORITHM_ANALYSIS.md
**Status:** Planning

---

## Overview

This backlog organizes the R5 phase algorithm fixes into Milestones (one per algorithm) with Epics and Issues as actionable work items.

### Summary Matrix

| Milestone | Algorithm | Current Output | Target Output | Status |
|-----------|-----------|----------------|---------------|--------|
| M0 | Cross-Cutting | - | - | In Progress |
| M1 | CPN | 0 scenarios | 10-50 | Blocked |
| M2 | RoutineDetector | 0 candidates | 5-20 | Ready |
| M3 | BGT-SM | 0 insights | 20-50 | Ready |
| M4 | SPC-UQ | 0 reconstructions | 5-15 | Blocked |
| M5 | TDL-HCO | 0 optimizations | 3-10 | Blocked |
| M6 | MCTS | 1 scenario | 1 | Done |
| M7 | IntentSignalDetector | 74 signals | 74 | Done |

---

# Milestone M0: Cross-Cutting Infrastructure

**Goal:** Resolve parity gaps and data flow issues that affect multiple algorithms

---

## Epic M0-E1: Parity Resolution Layer

**Purpose:** R5 algorithms need BOTH historical data (PostgreSQL) AND current-cycle data (envelope). R7 writes to PostgreSQL AFTER R5 completes, creating a temporal parity gap. This epic resolves that gap by loading accumulated data.

---

### Issue M0-E1-I1: Implement episodes_query syscall

- **File:** `k0/kernel/syscalls.py`
- **Lines:** 3626-3768
- **Status:** IMPLEMENTED

#### Problem Statement

R5 algorithms (RoutineDetector, CPN, TDL-HCO, SPC-UQ) need historical episode context to detect patterns. Without historical data, RoutineDetector cannot find 3+ matching signatures, CPN cannot build causal chains, etc.

#### Implementation Evidence

**Location:** `k0/kernel/syscalls.py` lines 3626-3768

```python
async def episodes_query(
    self,
    tenant_id: str,
    space_id: str,
    limit: int = 100,
    order_by: str = "start_time_utc DESC",
) -> dict[str, Any]:
```

**Key Features:**

- Capability: `st_epi.read`
- Query includes observation JOIN for sentiment/salience enrichment:

  ```sql
  LEFT JOIN LATERAL (
      SELECT AVG(obs.sentiment_score) as sentiment_score,
             AVG(obs.salience_score) as salience_score
      FROM st_observations obs
      WHERE obs.record_id = e.episode_id
        AND obs.layer = 'st_epi'
  ) o ON TRUE
  ```

- Filters by `archival_status = 'ACTIVE'`
- Orders by `start_time_utc DESC`

**Return Fields:**

| Field | Type | Source |
|-------|------|--------|
| episode_id | str | st_epi.episode_id |
| episode_summary | str | st_epi.episode_summary |
| episode_type | str | st_epi.episode_type |
| start_time_utc | int | st_epi.start_time_utc |
| end_time_utc | int | st_epi.end_time_utc |
| source_events_json | str | st_epi.source_events_json |
| primary_location | str | st_epi.primary_location |
| sentiment_score | float | st_observations (AVG) |
| salience_score | float | st_observations (AVG) |

#### Acceptance Criteria

- [x] Syscall returns episodes with sentiment_score, salience_score
- [x] Includes observation JOIN for enrichment
- [x] Respects tenant/space isolation
- [x] Performance target: <50ms P95 for 100 episodes

---

### Issue M0-E1-I2: Implement procedural_memory_query syscall

- **File:** `k0/kernel/syscalls.py`
- **Lines:** 3771-3898
- **Status:** IMPLEMENTED

#### Problem Statement

TDL-HCO algorithm needs existing routines to optimize using temporal difference learning. Without historical routines, TDL-HCO immediately skips: "no routines available".

#### Implementation Evidence

**Location:** `k0/kernel/syscalls.py` lines 3771-3898

```python
async def procedural_memory_query(
    self,
    tenant_id: str,
    space_id: str,
    limit: int = 50,
) -> dict[str, Any]:
```

**Key Features:**

- Capability: `st_procedural.read`
- Orders by `regularity_score DESC` (most regular routines first)
- Filters by `archival_status = 'ACTIVE'`

**Return Fields:**

| Field | Type | Source |
|-------|------|--------|
| routine_id | str | st_procedural.routine_id |
| actor_id | str | st_procedural.actor_id |
| routine_name | str | st_procedural.routine_name |
| routine_category | str | st_procedural.routine_category |
| temporal_anchor | str | st_procedural.temporal_anchor |
| day_pattern | str | st_procedural.day_pattern |
| frequency | str | st_procedural.frequency |
| regularity_score | float | st_procedural.regularity_score |
| action_sequence_json | str | st_procedural.action_sequence_json |
| lifecycle_state | str | st_procedural.lifecycle_state |

#### Acceptance Criteria

- [x] Syscall returns routines with action_sequence_json
- [x] Respects tenant/space isolation
- [x] Performance target: <30ms P95 for 50 routines

---

### Issue M0-E1-I3: Add episode merge logic to R5

- **File:** `k0/pipelines/p03/phases/r5_dream_explorer.py`
- **Lines:** 426-447 (call site), 780-853 (method)
- **Status:** IMPLEMENTED

#### Problem Statement

R5 received ONLY current-cycle episodes from `envelope.phases.r2_clusters`. This is insufficient for pattern detection algorithms that need episode history.

#### Implementation Evidence

**Method Location:** `k0/pipelines/p03/phases/r5_dream_explorer.py` lines 780-853

```python
async def _load_accumulated_episodes(
    self,
    ctx: "P03RunnerContext",
    tenant_id: str,
    space_id: str,
) -> List["EpisodeCluster"]:
```

**Key Features:**

- Calls `ctx.syscalls.episodes_query()` with `limit=self.config.accumulated_episode_limit`
- Converts PostgreSQL rows to `EpisodeCluster` objects
- Maps fields: `episode_id` → `cluster_id`, `primary_location` → `location_hint`
- Graceful fallback: returns `[]` on error (logs warning)

**Merge Logic Location:** lines 426-447

```python
accumulated_episodes = await self._load_accumulated_episodes(...)
current_episodes = list(envelope.phases.r2_clusters)
current_episode_ids = {e.cluster_id for e in current_episodes}
merged_episodes = current_episodes + [
    e for e in accumulated_episodes if e.cluster_id not in current_episode_ids
]
```

**Merge Pattern:** GAP-001 M9.2 (current cycle takes precedence via ID set exclusion)

#### Acceptance Criteria

- [x] `_load_accumulated_episodes()` method added
- [x] Episodes merged with deduplication
- [x] Current cycle takes precedence
- [x] Logging shows merge counts

---

### Issue M0-E1-I4: Add routine merge logic to R5

- **File:** `k0/pipelines/p03/phases/r5_dream_explorer.py`
- **Lines:** 855-910 (method)
- **Status:** IMPLEMENTED

#### Problem Statement

TDL-HCO needs existing routines from prior cycles. Without this, it cannot detect bottlenecks in established routines.

#### Implementation Evidence

**Method Location:** `k0/pipelines/p03/phases/r5_dream_explorer.py` lines 855-910

```python
async def _load_accumulated_routines(
    self,
    ctx: "P03RunnerContext",
    tenant_id: str,
    space_id: str,
) -> List[dict]:
```

**Key Features:**

- Calls `ctx.syscalls.procedural_memory_query()` with `limit=self.config.accumulated_routine_limit`
- Returns raw dict format (TDL-HCO works with dicts)
- Graceful fallback: returns `[]` on error

**Note:** Routine merge happens at algorithm level (TDL-HCO), not at input construction level.

#### Acceptance Criteria

- [x] `_load_accumulated_routines()` method added
- [x] Passed to TDL-HCO via algorithm dispatch
- [x] Graceful error handling

---

### Issue M0-E1-I5: Add config limits for accumulated data

- **File:** `k0/pipelines/p03/r5_config.py`
- **Lines:** 141-144
- **Status:** IMPLEMENTED

#### Problem Statement

Need configurable limits to control how much historical data is loaded. Too much = performance impact. Too little = insufficient context for algorithms.

#### Implementation Evidence

**Location:** `k0/pipelines/p03/r5_config.py` lines 141-144

```python
# Accumulated Episode/Routine limits (R5 Parity Resolution)
# Limits for loading accumulated episodes/routines for R5 dream algorithms
accumulated_episode_limit: int = 100  # Max episodes to load for RoutineDetector/CPN
accumulated_routine_limit: int = 50  # Max routines to load for TDL-HCO
```

**Rationale:**

- 100 episodes: Enough for RoutineDetector to find 3+ matching signatures
- 50 routines: Enough for TDL-HCO to detect optimization opportunities
- Both values can be tuned based on performance monitoring

#### Acceptance Criteria

- [x] accumulated_episode_limit = 100
- [x] accumulated_routine_limit = 50
- [x] Documented in config class

---

## Epic M0-E2: EpisodeCluster Compatibility

**Purpose:** R5 algorithms expect specific field names on episodes (EpisodeProtocol in CPN, dict keys in RoutineDetector). EpisodeCluster uses different field names. This epic adds compatibility properties.

---

### Issue M0-E2-I1: Add CPN compatibility properties to EpisodeCluster

- **File:** `k0/pipelines/p03/phase_outputs.py`
- **Lines:** 116-154
- **Status:** IMPLEMENTED

#### Problem Statement

CPN algorithm uses helper methods that look for specific field names:

- `_get_episode_sentiment()` looks for `sentiment_score` (line 868)
- `_get_episode_salience()` looks for `salience_score` (line 876)
- `_get_episode_start_time()` looks for `start_time_ms` (line 884)
- `_get_episode_id()` looks for `episode_id` (line 860)

But EpisodeCluster has:

- `dominant_sentiment` (NOT sentiment_score)
- `aggregated_salience` (NOT salience_score)
- `temporal_start` (NOT start_time_ms)
- `cluster_id` (NOT episode_id)

#### Implementation Evidence

**Location:** `k0/pipelines/p03/phase_outputs.py` lines 116-154

```python
@property
def sentiment_score(self) -> float:
    """Alias for CPN algorithm compatibility."""
    return self.dominant_sentiment

@property
def salience_score(self) -> float:
    """Alias for CPN algorithm compatibility."""
    return self.aggregated_salience if self.aggregated_salience is not None else 0.5

@property
def start_time_ms(self) -> int:
    """Alias for CPN algorithm compatibility."""
    return self.temporal_start

@property
def episode_id(self) -> str:
    """Alias for CPN algorithm compatibility."""
    return self.cluster_id
```

#### Acceptance Criteria

- [x] sentiment_score → dominant_sentiment
- [x] salience_score → aggregated_salience or 0.5 (fallback)
- [x] start_time_ms → temporal_start
- [x] episode_id → cluster_id

---

### Issue M0-E2-I2: Add entity_ids field to EpisodeCluster

- **File:** `k0/pipelines/p03/phase_outputs.py`
- **Lines:** 84 (insert after line 84)
- **Status:** NOT STARTED

#### Problem Statement

CPN algorithm needs entity IDs to build causal chains:

- `_get_episode_entities()` (cpn.py line 895) returns `[]` if no `entity_ids` attribute
- Empty entity_ids → CPN cannot build causal DAG → 0 scenarios generated

**CPN Code Evidence (cpn.py lines 895-900):**

```python
def _get_episode_entities(self, episode: Any) -> List[str]:
    """Get entity IDs from episode object."""
    if hasattr(episode, "entity_ids"):
        return list(episode.entity_ids)
    elif isinstance(episode, dict):
        return episode.get("entity_ids", [])
    return []  # <-- Always returns [] for EpisodeCluster!
```

#### What Needs To Be Done

**Add field to EpisodeCluster dataclass:**

```python
# In phase_outputs.py, EpisodeCluster class (after line 84):
entity_ids: List[str] = field(default_factory=list)  # CPN causal chain entities
```

**Field Purpose:**

- Store entity IDs extracted from NER during R2 clustering
- Used by CPN to build causal chains
- Used by BGT-SM for seed entity selection

#### Acceptance Criteria

- [ ] Field `entity_ids: List[str]` added to EpisodeCluster
- [ ] Default is empty list via `field(default_factory=list)`
- [ ] Docstring mentions CPN/BGT-SM usage

---

### Issue M0-E2-I3: Populate entity_ids during R2 clustering

- **File:** `k0/pipelines/p03/phases/r2_episodic_integrator.py`
- **Lines:** 1060-1210 (`_build_episode_cluster` method)
- **Status:** NOT STARTED

#### Problem Statement

EpisodeCluster.entity_ids field exists (after M0-E2-I2) but is never populated. R2 has access to NER data via `ner_entities_json` field.

**NER Data Structure Evidence (r2_episodic_integrator.py lines 1236-1250):**

```python
ner_json = getattr(e.event, "ner_entities_json", "{}") or "{}"
ner_data = json.loads(ner_json) if ner_json else {}
if isinstance(ner_data, dict):
    for source in ["ner_family", "ner_general"]:
        if source in ner_data and isinstance(ner_data[source], dict):
            entities = ner_data[source].get("entities", [])
            for ent in entities:
                if isinstance(ent, dict):
                    label = ent.get("label", "")
                    text = ent.get("text", "").strip()
```

**NER Data Format:**

```json
{
  "ner_family": {
    "entities": [
      {"label": "PERSON", "text": "Mom", "id": "person_mom_123"},
      {"label": "KINSHIP", "text": "sister", "id": "kinship_sister_456"}
    ]
  },
  "ner_general": {
    "entities": [
      {"label": "ORG", "text": "Starbucks", "id": "org_starbucks_789"}
    ]
  }
}
```

#### What Needs To Be Done

**1. Add entity extraction logic in `_build_episode_cluster()` (after line 1155):**

```python
# Extract entity IDs from NER across all member events
entity_ids: set = set()
for e in cluster_events:
    try:
        ner_json = getattr(e.event, "ner_entities_json", "{}") or "{}"
        ner_data = json.loads(ner_json) if ner_json else {}
        if isinstance(ner_data, dict):
            for source in ["ner_family", "ner_general"]:
                if source in ner_data and isinstance(ner_data[source], dict):
                    entities = ner_data[source].get("entities", [])
                    for ent in entities:
                        if isinstance(ent, dict):
                            ent_id = ent.get("id")
                            if ent_id:
                                entity_ids.add(ent_id)
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass
```

**2. Pass to EpisodeCluster constructor (line ~1210):**

```python
return EpisodeCluster(
    cluster_id=cluster_id,
    member_event_ids=list(member_ids),
    entity_ids=list(entity_ids),  # ADD THIS LINE
    # ... rest of fields
)
```

#### Acceptance Criteria

- [ ] Extract entity IDs from `ner_entities_json`
- [ ] Handle both `ner_family` and `ner_general` sources
- [ ] Deduplicate across member events using set
- [ ] Pass to EpisodeCluster constructor
- [ ] Graceful error handling (no crash on malformed JSON)

---

### Issue M0-E2-I4: Add ambiguity_score field to EpisodeCluster

- **File:** `k0/pipelines/p03/phase_outputs.py`
- **Lines:** 84 (insert after entity_ids)
- **Status:** NOT STARTED

#### Problem Statement

SPC-UQ algorithm uses `ambiguity_score` to detect episodes with uncertain content that need reconstruction:

**SPC-UQ Code Evidence (spc_uq.py lines 497-506):**

```python
ambiguity = self._get_attr(episode, "ambiguity_score", 0.0)
if ambiguity > self.config.ambiguity_threshold:  # threshold = 0.5
    gaps.append(
        AttributeGap(
            attribute_name="ambiguous_content",
            gap_type=GapType.CONTENT,
            priority=0.9,
            ambiguity_score=ambiguity,
        )
    )
```

**SPC-UQ EpisodeForSimulation Protocol (spc_uq.py lines 127-133):**

```python
@runtime_checkable
class EpisodeForSimulation(Protocol):
    @property
    def episode_id(self) -> str: ...
    @property
    def start_time_ms(self) -> int: ...
    @property
    def ambiguity_score(self) -> float: ...  # <-- REQUIRED!
```

**Current State:** EpisodeCluster has NO `ambiguity_score` field → always returns 0.0 → SPC-UQ content gaps never detected.

#### What Needs To Be Done

**Add field to EpisodeCluster dataclass:**

```python
# In phase_outputs.py, EpisodeCluster class (after entity_ids):
ambiguity_score: float = 0.0  # SPC-UQ gap detection (0=complete, 1=ambiguous)
```

**Field Purpose:**

- Measures how incomplete/uncertain an episode is
- Computed from ratio of missing fields (location, participants, activity)
- SPC-UQ uses threshold of 0.5 to trigger reconstruction

#### Acceptance Criteria

- [ ] Field `ambiguity_score: float = 0.0` added to EpisodeCluster
- [ ] Docstring mentions SPC-UQ usage

---

### Issue M0-E2-I5: Compute ambiguity_score during R2 clustering

- **File:** `k0/pipelines/p03/phases/r2_episodic_integrator.py`
- **Lines:** 1060-1210 (`_build_episode_cluster` method)
- **Status:** NOT STARTED

#### Problem Statement

EpisodeCluster.ambiguity_score field exists (after M0-E2-I4) but is never populated. R2 has access to all fields needed to compute ambiguity.

**Ambiguity Calculation Logic:**

- Check which critical fields are missing/empty
- Critical fields: location_hint, participants_json, activity_type
- ambiguity_score = (missing_count) / (total_critical_fields)
- Example: if location missing and activity missing but participants present → 2/3 = 0.67

#### What Needs To Be Done

**Add ambiguity computation in `_build_episode_cluster()` (before return):**

```python
# Compute ambiguity score based on missing critical fields
critical_field_checks = [
    location_hint is None or location_hint == "",  # Missing location
    participants_json == "[]" or not all_participants,  # No participants
    activity_type is None or activity_type == "",  # Missing activity
]
missing_count = sum(1 for check in critical_field_checks if check)
ambiguity_score = missing_count / len(critical_field_checks)  # 0.0 to 1.0
```

**Pass to EpisodeCluster constructor:**

```python
return EpisodeCluster(
    # ... existing fields
    ambiguity_score=ambiguity_score,  # ADD THIS LINE
)
```

**Threshold Guidance:**

- 0.0: All fields present (complete episode)
- 0.33: One field missing
- 0.67: Two fields missing (triggers SPC-UQ at 0.5 threshold)
- 1.0: All fields missing (highly ambiguous)

#### Acceptance Criteria

- [ ] Count missing: location_hint, participants, activity_type
- [ ] ambiguity_score = missing_count / total_fields
- [ ] Pass to EpisodeCluster constructor
- [ ] Values range from 0.0 (complete) to 1.0 (fully ambiguous)

---

# Milestone M1: CPN (Causal Perturbation Network)

**Goal:** Generate 10-50 counterfactual "what-if" scenarios per cycle
**Current:** 0 scenarios
**Blockers:** Missing entity_ids, only 4 CAUSES edges

---

## Epic M1-E1: Field Compatibility

**Purpose:** Verify CPN helper methods work with EpisodeCluster after M0 compatibility properties are added.

---

### Issue M1-E1-I1: Verify CPN reads sentiment_score property

- **File:** `k0/modules/consolidation/algorithms/cpn.py`
- **Lines:** 866-872
- **Status:** READY (depends on M0-E2-I1)

#### Problem Statement

CPN selects "regret events" (emotionally significant episodes) by filtering on sentiment. The `_get_episode_sentiment()` helper returns 0.0 for EpisodeCluster because it looks for `sentiment_score` attribute:

**CPN Code (cpn.py lines 866-872):**

```python
def _get_episode_sentiment(self, episode: Any) -> float:
    """Get sentiment score from episode object."""
    if hasattr(episode, "sentiment_score"):
        return episode.sentiment_score  # <-- Will work after M0-E2-I1
    elif isinstance(episode, dict):
        return episode.get("sentiment_score", 0.0)
    return 0.0
```

**Usage in Regret Selection (cpn.py line 470):**

```python
if abs(sentiment) < self.config.emotional_threshold:  # threshold = 0.3
    continue  # Skip if not emotionally significant
```

**After M0-E2-I1:** EpisodeCluster now has `sentiment_score` property → returns `dominant_sentiment`

#### What Needs To Be Done

**Verification Test:**

```python
from k0.pipelines.p03.phase_outputs import EpisodeCluster
from k0.modules.consolidation.algorithms.cpn import CPN

# Create episode with sentiment
episode = EpisodeCluster(
    cluster_id="test_001",
    dominant_sentiment=0.5,  # Above 0.3 threshold
)

cpn = CPN()
sentiment = cpn._get_episode_sentiment(episode)
assert sentiment == 0.5, "CPN should read sentiment_score property"
```

#### Acceptance Criteria

- [ ] CPN._get_episode_sentiment() returns non-zero for EpisodeCluster
- [ ] Episodes with |sentiment| >= 0.3 pass emotional threshold filter
- [ ] Regret event selection produces 1-10 candidates

---

### Issue M1-E1-I2: Verify CPN reads salience_score property

- **File:** `k0/modules/consolidation/algorithms/cpn.py`
- **Lines:** 874-879
- **Status:** READY (depends on M0-E2-I1)

#### Problem Statement

When no episodes pass the emotional threshold, CPN falls back to salience-based selection:

**CPN Fallback Logic (cpn.py lines 484-493):**

```python
if not regret_events:
    # Fallback: select by salience if no emotional events
    logger.info(
        "CPN fallback: no episodes passed emotional threshold, selecting by salience",
        extra={
            "emotional_threshold": self.config.emotional_threshold,
            "episode_count": len(episodes),
        },
    )
    regret_events = self._select_by_salience(episodes)
```

**After M0-E2-I1:** EpisodeCluster now has `salience_score` property → returns `aggregated_salience or 0.5`

#### What Needs To Be Done

**Verification Test:**

```python
episode = EpisodeCluster(
    cluster_id="test_002",
    aggregated_salience=0.8,
)

cpn = CPN()
salience = cpn._get_episode_salience(episode)
assert salience == 0.8, "CPN should read salience_score property"
```

#### Acceptance Criteria

- [ ] CPN._get_episode_salience() returns non-default for EpisodeCluster
- [ ] Fallback selection works when emotional threshold not met
- [ ] Top-k salient episodes selected correctly

---

### Issue M1-E1-I3: Verify CPN reads entity_ids

- **File:** `k0/modules/consolidation/algorithms/cpn.py`
- **Lines:** 895-900
- **Status:** BLOCKED (depends on M0-E2-I2, M0-E2-I3)

#### Problem Statement

CPN needs entity IDs to build causal chains (DAG). Without entity_ids, causal graph is empty:

**CPN Code (cpn.py lines 895-900):**

```python
def _get_episode_entities(self, episode: Any) -> List[str]:
    """Get entity IDs from episode object."""
    if hasattr(episode, "entity_ids"):
        return list(episode.entity_ids)
    elif isinstance(episode, dict):
        return episode.get("entity_ids", [])
    return []  # <-- Always returns [] without M0-E2-I2/I3!
```

**DAG Construction (cpn.py lines 530-565):**

```python
def _extract_causal_chain(self, episode, edge_lookup) -> CausalDAG:
    dag = CausalDAG()
    episode_entities = self._get_episode_entities(episode)

    for entity_id in episode_entities:  # <-- Empty loop if no entity_ids!
        # Build DAG from CAUSES edges
        ...
```

#### What Needs To Be Done

1. Complete M0-E2-I2 (add entity_ids field)
2. Complete M0-E2-I3 (populate entity_ids from NER)
3. Verify CPN reads populated entity_ids

**Verification Test:**

```python
episode = EpisodeCluster(
    cluster_id="test_003",
    entity_ids=["person_mom_123", "org_starbucks_456"],
)

cpn = CPN()
entities = cpn._get_episode_entities(episode)
assert len(entities) == 2, "CPN should read entity_ids"
assert "person_mom_123" in entities
```

#### Acceptance Criteria

- [ ] entity_ids non-empty for episodes with NER data
- [ ] CPN._get_episode_entities() returns populated list
- [ ] Causal DAG builds with entities from episodes

---

## Epic M1-E2: CAUSES Edge Generation

**Purpose:** CPN requires CAUSES edges to build causal DAGs. Currently only 4 CAUSES edges exist (out of 2,782 total edges). Need to generate more CAUSES edges in R4.

---

### Issue M1-E2-I1: Audit R4 causal edge inference

- **File:** `k0/pipelines/p03/phases/r4_kg_consolidator.py`
- **Lines:** 2220-2280
- **Status:** NOT STARTED

#### Problem Statement

Only 4 CAUSES edges exist in st_kg_edges. Understanding why requires auditing the inference logic.

#### Code Evidence

**CAUSES Edge Generation (r4_kg_consolidator.py lines 2235-2242):**

```python
# Determine relation type based on precedence ratio
# CAUSES: strong precedence (ratio >= threshold, typically 0.75)
# FOLLOWS: moderate precedence (0.60 <= ratio < threshold)
# PRECEDES: inverse moderate precedence (ratio <= 0.40)
# No edge: ambiguous range (0.40 < ratio < 0.60)

if precedence_ratio >= threshold:
    relation_type = "CAUSES"
```

**Threshold Configuration (r4_kg_consolidator.py line 151):**

```python
granger_precedence_threshold: float = 0.75  # 4.4.9 (overridden by 4.4.10)
```

**Minimum Observations Requirement:**

```python
if observations < self.config.granger_min_observations:
    continue  # Skip if not enough observations
```

**Possible Reasons for Low CAUSES Count:**

1. precedence_ratio rarely reaches 0.75 threshold
2. Not enough co-occurrence observations (min required)
3. Timestamp pairs not being built correctly
4. Adaptive thresholds (4.4.10) may be even stricter

#### What Needs To Be Done

1. Add logging to track:
   - How many entity pairs are analyzed
   - Distribution of precedence_ratio values
   - How many fail threshold vs min_observations
2. Query st_kg_edges for edge type distribution
3. Review adaptive threshold values per category

**SQL Audit Query:**

```sql
SELECT relation_type, COUNT(*)
FROM st_kg_edges
GROUP BY relation_type
ORDER BY COUNT(*) DESC;
```

#### Acceptance Criteria

- [ ] Identify inference logic for CAUSES (documented above)
- [ ] Document confidence thresholds (0.75 default)
- [ ] Log shows why most pairs don't produce CAUSES edges
- [ ] Recommendations for increasing CAUSES edge count

---

### Issue M1-E2-I2: Lower CAUSES edge precedence threshold

- **File:** `k0/pipelines/p03/phases/r4_kg_consolidator.py`
- **Lines:** 151, 2241
- **Status:** NOT STARTED

#### Problem Statement

The default `granger_precedence_threshold` of 0.75 is too strict for cold-start scenarios. Most entity pairs don't have strong enough temporal precedence to meet this threshold.

#### What Needs To Be Done

**Option A: Lower default threshold**

```python
# In R4KGConsolidatorConfig (line 151):
granger_precedence_threshold: float = 0.60  # Lowered from 0.75 for cold-start
```

**Option B: Add cold-start mode**

```python
# In R4KGConsolidatorConfig:
cold_start_precedence_threshold: float = 0.60
is_cold_start: bool = True  # Based on edge count

# In inference logic:
threshold = (
    self.config.cold_start_precedence_threshold
    if self._is_cold_start()
    else self.config.granger_precedence_threshold
)

def _is_cold_start(self) -> bool:
    # Cold start if fewer than 100 CAUSES edges exist
    return self._stats.causal_edges_created < 100
```

**Impact Analysis:**

- Threshold 0.75 → Very few CAUSES edges (currently 4)
- Threshold 0.60 → More CAUSES edges (estimated 20-50)
- Threshold 0.50 → Many CAUSES edges (may include noise)

#### Acceptance Criteria

- [ ] Threshold lowered to 0.60 for cold-start
- [ ] Config-driven (not hardcoded)
- [ ] CAUSES edge count increases to 20-50

---

### Issue M1-E2-I3: Lower minimum observations for CAUSES inference

- **File:** `k0/pipelines/p03/phases/r4_kg_consolidator.py`
- **Status:** NOT STARTED

#### Problem Statement

Granger causality requires minimum observations (co-occurrence pairs) to be statistically meaningful. In cold-start, pairs may not have enough observations.

#### What Needs To Be Done

1. Find `granger_min_observations` config value
2. Lower from default (likely 5) to 3 for cold-start
3. Track observation count distribution in logs

#### Acceptance Criteria

- [ ] granger_min_observations lowered for cold-start
- [ ] More entity pairs qualify for CAUSES inference

---

### Issue M1-E2-I4: Use PRECEDES edges as weak causal candidates in CPN

- **File:** `k0/modules/consolidation/algorithms/cpn.py`
- **Lines:** 518-520
- **Status:** NOT STARTED

#### Problem Statement

CPN only uses CAUSES edges (4 exist) but PRECEDES edges (13 exist) represent inverse temporal precedence. PRECEDES can be treated as "weak causal" - Entity A precedes Entity B temporally, suggesting potential causation.

**Current Edge Type Distribution:**

| relation_type | Count | CPN Compatible? |
|---------------|-------|-----------------|
| CAUSES | 4 | Yes (current) |
| PRECEDES | 13 | Yes (add as weak) |
| TEMPORALLY_ASSOCIATED | 30 | Maybe |
| FOLLOWS | 0 | N/A |

**Current CPN Code (cpn.py lines 518-520):**

```python
if rel_type != "CAUSES":
    continue  # Filters out ALL other edge types!
```

#### What Needs To Be Done

**Option A: Add PRECEDES as weak causal (recommended):**

```python
# In cpn.py _build_edge_lookup():
CAUSAL_EDGE_TYPES = {"CAUSES", "PRECEDES"}

if rel_type not in CAUSAL_EDGE_TYPES:
    continue

# Apply confidence penalty for PRECEDES (weaker than CAUSES)
if rel_type == "PRECEDES":
    confidence = confidence * 0.7  # 30% penalty
```

**Option B: Configurable edge types:**

```python
# In CPNConfig:
causal_edge_types: Tuple[str, ...] = ("CAUSES",)
weak_causal_edge_types: Tuple[str, ...] = ("PRECEDES", "TEMPORALLY_ASSOCIATED")
weak_causal_penalty: float = 0.7

# In _build_edge_lookup():
if rel_type in self.config.causal_edge_types:
    pass  # Use full confidence
elif rel_type in self.config.weak_causal_edge_types:
    confidence = confidence * self.config.weak_causal_penalty
else:
    continue
```

**Semantic Justification:**

- PRECEDES: "Entity A appears before Entity B" (ratio <= 0.40)
- This is the inverse of FOLLOWS (ratio >= 0.60)
- If A precedes B consistently, A may influence B
- Not as strong as CAUSES (ratio >= 0.75) but still useful

**Risk Mitigation:**

- Apply 30% confidence penalty for weak causal edges
- CPN's plausibility calculation will naturally down-weight
- More scenarios generated (better than 0)

#### Acceptance Criteria

- [ ] PRECEDES edges included in CPN edge lookup
- [ ] Confidence penalty applied (0.7x)
- [ ] CPN generates more scenarios with expanded edge set
- [ ] Config-driven for easy tuning

---

### Issue M1-E2-I5: Synthetic CAUSES from high-confidence co-occurrence

- **File:** `k0/pipelines/p03/phases/r4_kg_consolidator.py`
- **Lines:** 2100-2200 (new method)
- **Status:** NOT STARTED

#### Problem Statement

Many edges have high observation_count and confidence but don't meet the 0.75 precedence threshold. These represent strong co-occurrence patterns that could be upgraded to CAUSES.

**Current Edge Types (high count, low CAUSES):**

| relation_type | Count | observation_count (avg) |
|---------------|-------|-------------------------|
| INFERRED_RELATED | 1,922 | 10-50+ |
| SIMILAR_TO | 483 | 5-20 |
| CONTEXTUALLY_RELATED | 293 | 5-15 |

**Opportunity:** Edges with observation_count >= 10 AND confidence >= 0.8 likely have implicit causal relationships even if precedence_ratio is slightly below threshold.

#### What Needs To Be Done

**Add synthetic CAUSES inference in R4:**

```python
def _infer_synthetic_causes(
    self,
    edges: List[KGEdgeUpdate],
) -> List[CausalEdge]:
    """
    Generate synthetic CAUSES edges from high-confidence co-occurrence.

    Criteria:
    - observation_count >= 10
    - confidence >= 0.8
    - Not already CAUSES/FOLLOWS/PRECEDES

    These represent strong co-occurrence that implies causation.
    """
    synthetic_causes = []

    for edge in edges:
        if edge.relation_type in ("CAUSES", "FOLLOWS", "PRECEDES"):
            continue

        if (edge.observation_count or 0) < 10:
            continue

        if (edge.confidence or 0) < 0.8:
            continue

        # High-confidence co-occurrence -> synthetic CAUSES
        synthetic = CausalEdge(
            source_id=edge.source_id,
            target_id=edge.target_id,
            relation_type="CAUSES",
            confidence=edge.confidence * 0.8,  # 20% penalty for synthetic
            observation_count=edge.observation_count,
            precedence_ratio=0.65,  # Assumed weak precedence
            is_synthetic=True,  # Flag for debugging
        )
        synthetic_causes.append(synthetic)

    return synthetic_causes
```

**Configuration:**

```python
# In R4KGConsolidatorConfig:
enable_synthetic_causes: bool = True
synthetic_causes_min_observations: int = 10
synthetic_causes_min_confidence: float = 0.8
synthetic_causes_confidence_penalty: float = 0.8
```

#### Acceptance Criteria

- [ ] Synthetic CAUSES generated from high-confidence edges
- [ ] Minimum thresholds: 10 observations, 0.8 confidence
- [ ] 20% confidence penalty applied
- [ ] is_synthetic flag for debugging/filtering
- [ ] Estimated 50-100 additional CAUSES edges

---

### Issue M1-E2-I6: Upgrade TEMPORALLY_ASSOCIATED to CAUSES

- **File:** `k0/pipelines/p03/phases/r4_kg_consolidator.py`
- **Status:** NOT STARTED

#### Problem Statement

30 edges have relation_type = "TEMPORALLY_ASSOCIATED". These represent entities that consistently appear together in time but weren't classified as CAUSES due to threshold.

**Edge Data:**

```sql
SELECT * FROM st_kg_edges WHERE relation_type = 'TEMPORALLY_ASSOCIATED';
-- 30 edges with temporal co-occurrence
```

**Opportunity:** TEMPORALLY_ASSOCIATED edges have implicit temporal precedence - review and upgrade qualifying edges to CAUSES.

#### What Needs To Be Done

**Option A: Re-evaluate with lower threshold**

In R4 causal inference, add special handling:

```python
# If edge is TEMPORALLY_ASSOCIATED, use relaxed threshold
if existing_edge.relation_type == "TEMPORALLY_ASSOCIATED":
    threshold = min(threshold, 0.55)  # More lenient for temporal edges
```

**Option B: Batch upgrade script**

Create one-time migration to upgrade qualifying edges:

```sql
UPDATE st_kg_edges
SET relation_type = 'CAUSES'
WHERE relation_type = 'TEMPORALLY_ASSOCIATED'
  AND observation_count >= 5
  AND confidence_score >= 0.6;
```

#### Acceptance Criteria

- [ ] Review 30 TEMPORALLY_ASSOCIATED edges
- [ ] Upgrade qualifying edges to CAUSES
- [ ] Expected: 10-20 additional CAUSES edges

---

## Epic M1-E3: Threshold Tuning

**Purpose:** CPN has multiple configurable thresholds that affect output volume. Cold-start scenarios need lower thresholds.

---

### Issue M1-E3-I1: Verify emotional_threshold is configurable

- **File:** `k0/modules/consolidation/algorithms/cpn.py`
- **Lines:** 77-89
- **Status:** ALREADY CONFIGURABLE

#### Code Evidence

**CPNConfig (cpn.py lines 67-77):**

```python
@dataclass(frozen=True)
class CPNConfig:
    """Configuration for Causal Perturbation Network."""
    emotional_threshold: float = 0.3  # GAP-001 M9.3: lowered from 0.6
    top_k_regret_events: int = 10
    causal_chain_depth: int = 5
    perturbation_std: float = 0.1
    min_plausibility: float = 0.3
    min_utility_delta: float = 0.3
    # ...
```

**Note:** Already lowered from 0.6 to 0.3 per GAP-001 M9.3.

#### What Needs To Be Done

No code changes needed. Already configurable via CPNConfig.

For cold-start, can instantiate with lower threshold:

```python
config = CPNConfig(emotional_threshold=0.1)
cpn = CPN(config=config)
```

#### Acceptance Criteria

- [x] emotional_threshold in CPNConfig
- [x] Default 0.3 (already lowered from 0.6)
- [ ] Consider lowering to 0.1 for first 100 cycles

---

## Epic M1-E4: Testing & Validation

**Purpose:** Add integration tests to verify CPN produces scenarios after fixes.

---

### Issue M1-E4-I1: Add CPN integration test

- **File:** `tests/k0/modules/consolidation/algorithms/test_cpn_integration.py`
- **Status:** NOT STARTED

#### What Needs To Be Done

Create integration test that:

1. Creates episodes with sentiment_score, salience_score, entity_ids
2. Creates CAUSES edges between entities
3. Runs CPN.generate()
4. Verifies scenarios_generated > 0

**Test Skeleton:**

```python
import pytest
from k0.pipelines.p03.phase_outputs import EpisodeCluster
from k0.modules.consolidation.algorithms.cpn import CPN, CPNConfig

class TestCPNIntegration:
    def test_cpn_generates_scenarios_with_causes_edges(self):
        # Create episodes with entity_ids
        episodes = [
            EpisodeCluster(
                cluster_id=f"ep_{i}",
                dominant_sentiment=0.5,
                aggregated_salience=0.7,
                entity_ids=["person_a", "org_b"],
            )
            for i in range(10)
        ]

        # Create CAUSES edges
        edges = [
            {"source_id": "person_a", "target_id": "org_b",
             "relation_type": "CAUSES", "confidence": 0.8}
        ]

        # Run CPN
        config = CPNConfig(emotional_threshold=0.1)
        cpn = CPN(config=config)
        scenarios = cpn.generate(
            episodes=episodes,
            kg_edges=edges,
        )

        assert len(scenarios) > 0, "CPN should generate scenarios"
```

#### Acceptance Criteria

- [ ] Test with 10+ episodes with entity_ids
- [ ] Test with 20+ CAUSES edges
- [ ] Verify scenarios_generated > 0
- [ ] Test all scenario types: UPWARD, DOWNWARD, SEMIFACTUAL

---

# Milestone M2: RoutineDetector (GAP-003)

**Goal:** Detect 5-20 recurring behavioral patterns per cycle
**Current:** 0 candidates
**Blockers:** Field name mismatch (FIXED), need merged historical episodes

## Epic M2-E1: Field Mapping Fix

**Purpose:** Fix field key mismatches between DreamExplorer episode dict conversion and RoutineDetector expectations.

---

### Issue M2-E1-I1: Fix location field key in DreamExplorer

- **File:** `k0/modules/consolidation/dream/dream_explorer.py`
- **Lines:** 1020-1120 (`_run_routine_detector` method)
- **Status:** IMPLEMENTED

#### Problem Statement

RoutineDetector uses fallback chain for location field lookup, but DreamExplorer was passing dict with wrong key name.

**RoutineDetector Field Lookup (routine_detector.py lines 268-269):**

```python
activity = (ep.get("activity_type") or ep.get("episode_type") or "").lower()
location = (ep.get("primary_location") or ep.get("location_hint") or "").lower()
```

**Expected Keys:**

- `primary_location` (first choice)
- `location_hint` (fallback)

**Original DreamExplorer Code (was wrong):**

```python
"location": getattr(ep, "primary_location", ""),  # Wrong key!
```

#### What Was Done

**Fixed DreamExplorer (lines 1067-1069):**

```python
# FIXED: Use correct keys for RoutineDetector fallback chain
"primary_location": getattr(ep, "primary_location", ""),
"location_hint": getattr(ep, "location_hint", ""),
```

#### Acceptance Criteria

- [x] Key `primary_location` in episode dict
- [x] Key `location_hint` in episode dict for fallback
- [x] RoutineDetector can read location field

---

### Issue M2-E1-I2: Fix timestamp field key in DreamExplorer

- **File:** `k0/modules/consolidation/dream/dream_explorer.py`
- **Lines:** 1020-1120 (`_run_routine_detector` method)
- **Status:** IMPLEMENTED

#### Problem Statement

RoutineDetector uses `start_time_utc` for temporal binning. DreamExplorer was not populating this field.

**RoutineDetector Timestamp Access (routine_detector.py lines 270-271):**

```python
# Temporal binning uses start_time_utc
timestamp_str = ep.get("start_time_utc", "")
```

**Original DreamExplorer Code:**

```python
"start_time_ms": getattr(ep, "start_time_ms", 0),  # Wrong format!
```

#### What Was Done

**Fixed DreamExplorer (lines 1065-1066):**

```python
# FIXED: Add start_time_utc for RoutineDetector temporal binning
"start_time_utc": (
    datetime.fromtimestamp(getattr(ep, "start_time_ms", 0) / 1000, tz=timezone.utc).isoformat()
    if getattr(ep, "start_time_ms", 0) > 0 else ""
),
```

#### Acceptance Criteria

- [x] Key `start_time_utc` in episode dict
- [x] ISO format string for datetime parsing
- [x] Handle zero timestamps gracefully

---

## Epic M2-E2: Merged Episode Data

**Purpose:** Ensure RoutineDetector receives enough episodes (including from prior cycles) to detect 3+ signature matches.

---

### Issue M2-E2-I1: Verify RoutineDetector runs with merged episodes

- **File:** `k0/modules/consolidation/dream/dream_explorer.py`
- **Lines:** 1020-1040 (`_run_routine_detector` method)
- **Status:** READY

#### Problem Statement

RoutineDetector needs 3+ episodes with same signature to detect a routine. With only current-cycle episodes (10-50), patterns may not repeat enough.

**RoutineDetector Min Occurrences (routine_detector.py lines 86-88):**

```python
@dataclass
class RoutineDetectorConfig:
    min_occurrences: int = 3  # Need 3+ matches for routine detection
    min_routine_length: int = 2
```

**Signature Grouping (routine_detector.py lines 257-270):**

```python
def _group_by_signature(self, episodes: List[Dict[str, Any]]) -> Dict[str, List[Dict]]:
    """Group episodes by behavioral signature (activity + location + time_bin)."""
    groups: Dict[str, List[Dict]] = {}
    for ep in episodes:
        activity = (ep.get("activity_type") or ep.get("episode_type") or "").lower()
        location = (ep.get("primary_location") or ep.get("location_hint") or "").lower()
        # Compute time bin from start_time_utc
        time_bin = self._compute_time_bin(ep.get("start_time_utc", ""))
        signature = f"{activity}:{location}:{time_bin}"
        if signature not in groups:
            groups[signature] = []
        groups[signature].append(ep)
    return groups
```

**Parity Resolution (r5_dream_explorer.py lines 775-870):**
Now loads accumulated episodes from st_epi via `episodes_query` syscall and merges with current cycle.

#### What Was Done

Parity resolution in M0-E1 already handles this:

1. `_load_accumulated_episodes()` loads from st_epi
2. Episodes merged with current cycle in DreamExplorerInput.recent_episodes
3. RoutineDetector now receives 500+ episodes instead of 10-50

#### Verification Test

```python
# Run R5 and check log for episode counts
# Expected: "RoutineDetector received 500+ episodes (50 current + 450 accumulated)"
```

#### Acceptance Criteria

- [x] Merged episodes passed to RoutineDetector (via M0-E1)
- [ ] Log shows 100+ episodes received
- [ ] At least 3 signatures have 3+ occurrences

---

### Issue M2-E2-I2: Consider running RoutineDetector before TDL-HCO

- **File:** `k0/modules/consolidation/dream/dream_explorer.py`
- **Lines:** 180-200 (algorithm execution order)
- **Status:** NOT STARTED

#### Problem Statement

TDL-HCO requires routines as input. Currently it calls `extract_routines_from_episodes()` which creates synthetic routines. Instead, TDL-HCO could use RoutineDetector's output.

**Current TDL-HCO Input (dream_explorer.py lines 985-990):**

```python
# Extract routines from episodic memory
routines = extract_routines_from_episodes(
    episodes=input_data.recent_episodes,
    min_routine_length=3,
    min_occurrences=2,  # Lower threshold for testing
)
```

**RoutineDetector Output (routine_detector.py lines 40-50):**

```python
@dataclass
class RoutineCandidate:
    routine_id: str
    signature: str
    occurrences: int
    episodes: List[Dict[str, Any]]  # Episodes matching this routine
    average_duration_minutes: float
    time_bins: List[str]  # Morning, afternoon, evening patterns
```

**Proposed Execution Order:**

```
Current:
  CPN, BGT-SM, SPC-UQ (parallel)
  RoutineDetector, MCTS, IntentSignal (parallel)
  TDL-HCO (sequential, uses extract_routines_from_episodes)

Proposed:
  CPN, BGT-SM, SPC-UQ, RoutineDetector (parallel)
  TDL-HCO (sequential, uses RoutineDetector output)
```

#### What Needs To Be Done

**Option A: Pass RoutineDetector output to TDL-HCO**

```python
# In _run_tdl_hco:
async def _run_tdl_hco(
    self,
    input_data: DreamExplorerInput,
    cycle_id: str,
    detected_routines: List[RoutineCandidate],  # New parameter
) -> List[RoutineOptimization]:
    if detected_routines:
        routines = [self._convert_candidate_to_routine(r) for r in detected_routines]
    else:
        routines = extract_routines_from_episodes(...)
```

**Option B: Keep extraction but include RoutineDetector candidates**

```python
# Merge detected_routines into extracted routines
all_routines = routines + [
    self._convert_candidate_to_routine(r)
    for r in detected_routines
]
```

#### Acceptance Criteria

- [ ] RoutineDetector runs before TDL-HCO
- [ ] TDL-HCO receives detected_routines parameter
- [ ] Optimizations generated from detected patterns

---

## Epic M2-E3: Testing and Validation

**Purpose:** Add integration tests to verify RoutineDetector produces candidates after fixes.

---

### Issue M2-E3-I1: Add RoutineDetector field mapping test

- **File:** `tests/k0/modules/consolidation/algorithms/test_routine_detector.py`
- **Status:** NOT STARTED

#### What Needs To Be Done

Create test that verifies field keys work correctly:

```python
import pytest
from k0.modules.consolidation.algorithms.routine_detector import (
    RoutineDetector, RoutineDetectorConfig
)

class TestRoutineDetectorFieldMapping:
    def test_location_fallback_chain(self):
        """Verify location read from primary_location or location_hint."""
        episodes = [
            # Episode with primary_location
            {"episode_id": "ep_1", "activity_type": "coffee",
             "primary_location": "starbucks", "start_time_utc": "2024-01-15T08:30:00Z"},
            # Episode with location_hint only
            {"episode_id": "ep_2", "activity_type": "coffee",
             "location_hint": "starbucks", "start_time_utc": "2024-01-16T08:30:00Z"},
            # Episode with both
            {"episode_id": "ep_3", "activity_type": "coffee",
             "primary_location": "starbucks", "location_hint": "cafe",
             "start_time_utc": "2024-01-17T08:30:00Z"},
        ]

        detector = RoutineDetector(config=RoutineDetectorConfig(min_occurrences=3))
        candidates = detector.detect(episodes=episodes)

        # Should group all 3 as same routine (coffee:starbucks:morning)
        assert len(candidates) >= 1
        assert candidates[0].occurrences == 3

    def test_timestamp_parsing(self):
        """Verify start_time_utc parsed for time binning."""
        episodes = [
            {"episode_id": f"ep_{i}", "activity_type": "commute",
             "primary_location": "highway", "start_time_utc": f"2024-01-1{i}T07:30:00Z"}
            for i in range(5)  # 5 morning commutes
        ]

        detector = RoutineDetector(config=RoutineDetectorConfig(min_occurrences=3))
        candidates = detector.detect(episodes=episodes)

        # Should detect morning commute routine
        assert len(candidates) >= 1
        assert "morning" in candidates[0].time_bins
```

#### Acceptance Criteria

- [ ] Test with `primary_location` key works
- [ ] Test with `location_hint` fallback works
- [ ] Test with `start_time_utc` parses correctly
- [ ] candidates_detected > 0

---

### Issue M2-E3-I2: Add RoutineDetector integration test with historical data

- **File:** `tests/k0/pipelines/p03/test_r5_routine_detector.py`
- **Status:** NOT STARTED

#### What Needs To Be Done

Create integration test that simulates merged episodes from PostgreSQL:

```python
import pytest
from k0.modules.consolidation.dream.dream_explorer import DreamExplorer, DreamConfig
from k0.modules.consolidation.dream.models import DreamExplorerInput
from k0.pipelines.p03.phase_outputs import EpisodeCluster

class TestRoutineDetectorIntegration:
    @pytest.mark.asyncio
    async def test_routine_detection_with_merged_episodes(self):
        """Verify RoutineDetector finds patterns in merged historical data."""

        # Simulate 100 episodes: 30 current + 70 accumulated
        episodes = []

        # Create repeating pattern: coffee at starbucks at 8am
        for i in range(20):
            episodes.append(EpisodeCluster(
                cluster_id=f"coffee_{i}",
                primary_location="starbucks",
                episode_type="coffee",
                start_time_ms=1705000000000 + (i * 86400000),  # Daily
            ))

        # Create another pattern: gym at 6pm
        for i in range(15):
            episodes.append(EpisodeCluster(
                cluster_id=f"gym_{i}",
                primary_location="fitness_center",
                episode_type="exercise",
                start_time_ms=1705036000000 + (i * 86400000),  # Daily 6pm
            ))

        # Create noise episodes
        for i in range(50):
            episodes.append(EpisodeCluster(
                cluster_id=f"random_{i}",
                primary_location=f"location_{i % 10}",
                episode_type=f"activity_{i % 7}",
                start_time_ms=1705000000000 + (i * 3600000),
            ))

        config = DreamConfig()
        explorer = DreamExplorer(config=config)

        input_data = DreamExplorerInput(
            recent_episodes=episodes,
            kg_entities=[],
            kg_edges=[],
        )

        candidates = await explorer._run_routine_detector(
            input_data=input_data,
            cycle_id="test_cycle",
        )

        # Should detect at least 2 routines (coffee, gym)
        assert len(candidates) >= 2

        # Verify coffee routine detected
        coffee_routine = next((c for c in candidates if "coffee" in c.signature), None)
        assert coffee_routine is not None
        assert coffee_routine.occurrences >= 10

#### Acceptance Criteria

- [ ] Test with 100+ merged episodes
- [ ] At least 2 routines detected
- [ ] Pattern detection works across cycles
- [ ] Correct signature format (activity:location:time_bin)

---

# Milestone M3: BGT-SM (Bisociative Graph Traversal)

**Goal:** Discover 20-50 surprising connections per cycle
**Current:** 0 insights
**Blockers:** Missing entity_ids for seed selection, strict thresholds for cold-start

## Epic M3-E1: Seed Entity Selection

**Purpose:** Ensure BGT-SM receives valid seed entities for random walk exploration.

---

### Issue M3-E1-I1: Verify BGT-SM uses entity_ids from episodes

- **File:** `k0/modules/consolidation/dream/dream_explorer.py`
- **Lines:** 489-540 (`_select_seed_entities` method)
- **Status:** BLOCKED (depends on M0-E2-I2, M0-E2-I3)

#### Problem Statement

BGT-SM requires seed entities to start random walks. Seeds are extracted from episodes via `entity_ids` attribute. Without entity_ids, no episode-based seeds are selected.

**Seed Selection Logic (dream_explorer.py lines 494-510):**

```python
def _select_seed_entities(
    self,
    input_data: DreamExplorerInput,
) -> List[str]:
    """Select seed entities for BGT-SM exploration."""
    seed_candidates: Dict[str, float] = {}  # entity_id -> score

    # Extract entities from recent episodes
    for episode in input_data.recent_episodes:
        entity_ids = getattr(episode, "entity_ids", [])  # <-- Returns [] without M0-E2-I2!
        salience = getattr(episode, "salience_score", 0.5)

        for entity_id in entity_ids:
            if entity_id not in seed_candidates:
                seed_candidates[entity_id] = 0.0
            seed_candidates[entity_id] += salience  # Salience-weighted scoring
```

**Log When No Seeds (dream_explorer.py lines 457-460):**

```python
if not seed_entity_ids:
    self._logger.debug("BGT-SM skipped: no seed entities available")
    return []  # <-- Currently always hits this branch!
```

#### What Needs To Be Done

After M0-E2-I2 and M0-E2-I3 are complete:

1. EpisodeCluster will have `entity_ids: List[str]` field
2. R2 will populate `entity_ids` from NER extraction
3. `_select_seed_entities()` will return 1-5 seed entities

**Verification:**

```python
# After entity_ids populated:
episode = EpisodeCluster(
    cluster_id="ep_1",
    entity_ids=["person_mom", "org_starbucks", "activity_coffee"],
    aggregated_salience=0.8,
)

seeds = explorer._select_seed_entities(
    DreamExplorerInput(recent_episodes=[episode], kg_entities=[], kg_edges=[])
)
assert len(seeds) >= 1
assert "person_mom" in seeds or "org_starbucks" in seeds
```

#### Acceptance Criteria

- [ ] `entity_ids` attribute accessible on EpisodeCluster
- [ ] Salience-weighted selection produces 1-5 seeds
- [ ] Seeds exist in KG (verified by `graph.has_entity()`)

---

### Issue M3-E1-I2: Verify BGT-SM KG fallback works

- **File:** `k0/modules/consolidation/dream/dream_explorer.py`
- **Lines:** 515-530 (`_select_seed_entities` fallback section)
- **Status:** READY

#### Problem Statement

When no episodes have `entity_ids`, BGT-SM should fall back to high-observation entities from KG.

**KG Fallback Logic (dream_explorer.py lines 515-525):**

```python
# Add high-observation entities from KG
for entity in input_data.kg_entities:
    entity_id = getattr(entity, "entity_id", None)
    obs_count = getattr(entity, "observation_count", 0)

    if entity_id and obs_count >= 5:  # Min 5 observations
        if entity_id not in seed_candidates:
            seed_candidates[entity_id] = 0.0
        seed_candidates[entity_id] += obs_count / 100.0  # Normalize
```

**KG Entity Protocol (bgt_sm.py lines 135-145):**

```python
@runtime_checkable
class EntityProtocol(Protocol):
    """Protocol for knowledge graph entities."""
    entity_id: str
    entity_type: str
    observation_count: int  # Used for fallback selection
```

#### What Needs To Be Done

Verify KG entities are passed correctly to dream_explorer:

1. `input_data.kg_entities` contains entities from R4
2. Entities have `observation_count` >= 5
3. Fallback selection picks top 5 by observation count

**Verification Test:**

```python
# Create KG entities with observation counts
entities = [
    KGEntity(entity_id=f"ent_{i}", entity_type="PERSON", observation_count=i*5)
    for i in range(1, 20)
]

seeds = explorer._select_seed_entities(
    DreamExplorerInput(
        recent_episodes=[],  # No episodes
        kg_entities=entities,
        kg_edges=[],
    )
)

# Should select top 5 by observation_count
assert len(seeds) == 5
assert "ent_19" in seeds  # Highest obs_count = 95
```

#### Acceptance Criteria

- [x] KG fallback code exists (verified above)
- [ ] Test with empty episodes, non-empty KG entities
- [ ] 5 seeds selected from high-observation entities
- [ ] Seeds work for random walk

---

## Epic M3-E2: Threshold Tuning

**Purpose:** Lower BGT-SM thresholds for cold-start scenarios where data is sparse.

---

### Issue M3-E2-I1: Lower semantic_distance_threshold for cold-start

- **File:** `k0/modules/consolidation/algorithms/bgt_sm.py`
- **Lines:** 79, 213 (constant and config)
- **Status:** NOT STARTED

#### Problem Statement

The default `semantic_distance_threshold` of 0.7 is too strict. Remote associates must have embedding distance >= 0.7 to be considered "surprising". In cold-start, embeddings may cluster tightly.

**Current Threshold (bgt_sm.py lines 79, 213):**

```python
P03_BGT_SEMANTIC_DISTANCE_THRESHOLD = 0.7  # Line 79

@dataclass(frozen=True)
class BGTConfig:
    semantic_distance_threshold: float = P03_BGT_SEMANTIC_DISTANCE_THRESHOLD  # Line 213
```

**Threshold Check (bgt_sm.py lines 655-660):**

```python
# Check semantic distance (must be "remote")
distance = self._compute_embedding_distance(seed_embedding, target_embedding)
if distance < self.config.semantic_distance_threshold:
    continue  # Not remote enough - skip!
```

**Embedding Distance Calculation (bgt_sm.py lines 760-775):**

```python
def _compute_embedding_distance(
    self,
    emb1: List[float],
    emb2: List[float],
) -> float:
    """Compute cosine distance (1 - similarity)."""
    dot = sum(a * b for a, b in zip(emb1, emb2))
    norm1 = math.sqrt(sum(a * a for a in emb1))
    norm2 = math.sqrt(sum(b * b for b in emb2))
    similarity = dot / (norm1 * norm2 + 1e-9)
    return 1.0 - similarity  # Distance = 1 - cosine_similarity
```

#### What Needs To Be Done

Lower threshold for cold-start:

```python
# Option A: Lower default
P03_BGT_SEMANTIC_DISTANCE_THRESHOLD = 0.5  # From 0.7

# Option B: Add cold-start profile
P03_BGT_COLD_START_SEMANTIC_THRESHOLD = 0.5
P03_BGT_PRODUCTION_SEMANTIC_THRESHOLD = 0.7
```

#### Acceptance Criteria

- [ ] Threshold lowered to 0.5 for cold-start
- [ ] Config-driven (not hardcoded in algorithm)
- [ ] More remote associates pass threshold

---

### Issue M3-E2-I2: Lower pmi_threshold for cold-start

- **File:** `k0/modules/consolidation/algorithms/bgt_sm.py`
- **Lines:** 80, 214 (constant and config)
- **Status:** NOT STARTED

#### Problem Statement

The default `pmi_threshold` of 3.0 is too strict. PMI (Pointwise Mutual Information) measures how much more likely two entities co-occur than expected by chance.

**PMI Formula:**

```
PMI(x, y) = log2( P(x,y) / (P(x) * P(y)) )
```

A PMI of 3.0 means entities co-occur 8x more often than expected (2^3 = 8). This is very high for cold-start.

**Current Threshold (bgt_sm.py lines 80, 214):**

```python
P03_BGT_PMI_THRESHOLD = 3.0  # Line 80

@dataclass(frozen=True)
class BGTConfig:
    pmi_threshold: float = P03_BGT_PMI_THRESHOLD  # Line 214
```

**PMI Calculation (bgt_sm.py lines 700-725):**

```python
def calculate_pmi(
    self,
    entity_a: str,
    entity_b: str,
) -> float:
    """Calculate PMI for entity pair."""
    # P(a) = occurrences_a / corpus_size
    # P(b) = occurrences_b / corpus_size
    # P(a,b) = co_occurrences / corpus_size
    # PMI = log2(P(a,b) / (P(a) * P(b)))

    co_occ = self._get_co_occurrence_count(entity_a, entity_b)
    if co_occ == 0:
        return 0.0

    p_a = self._get_occurrence_count(entity_a) / self.corpus_size_n
    p_b = self._get_occurrence_count(entity_b) / self.corpus_size_n
    p_ab = co_occ / self.corpus_size_n

    return math.log2(p_ab / (p_a * p_b + 1e-9))
```

#### What Needs To Be Done

Lower threshold for cold-start:

```python
# Lower from 3.0 to 1.5 (entities co-occur ~3x more than expected)
P03_BGT_PMI_THRESHOLD = 1.5
```

#### Acceptance Criteria

- [ ] Threshold lowered to 1.5 for cold-start
- [ ] Config-driven
- [ ] More surprising associations pass

---

### Issue M3-E2-I3: Lower serendipity_threshold for cold-start

- **File:** `k0/modules/consolidation/algorithms/bgt_sm.py`
- **Lines:** 83, 218 (constant and config)
- **Status:** NOT STARTED

#### Problem Statement

The default `serendipity_threshold` (actually `novelty_threshold`) of 0.5 filters out insights with low novelty scores.

**Novelty Score Calculation (bgt_sm.py lines 750-758):**

```python
def _calculate_novelty(
    self,
    associate: RemoteAssociate,
) -> float:
    """Calculate novelty score for remote associate."""
    # Novelty = semantic_distance * pmi / (visit_count + 1)
    # Higher distance, higher PMI, lower visit count = more novel
    return (
        associate.semantic_distance
        * associate.pmi
        / (associate.visit_count + 1)
    )
```

**Current Threshold (bgt_sm.py lines 81-82):**

```python
P03_BGT_NOVELTY_THRESHOLD = 0.5  # Min novelty score for insights
P03_BGT_SERENDIPITY_THRESHOLD = 0.6  # Alternative name, same concept
```

#### What Needs To Be Done

Lower novelty threshold for cold-start:

```python
P03_BGT_NOVELTY_THRESHOLD = 0.3  # From 0.5
```

#### Acceptance Criteria

- [ ] Threshold lowered to 0.3 for cold-start
- [ ] Config-driven
- [ ] More insights generated

---

### Issue M3-E2-I4: Make BGT-SM thresholds configurable via DreamConfig

- **File:** `k0/modules/consolidation/dream/dream_explorer.py`
- **Lines:** 447-455 (BGTConfig creation)
- **Status:** NOT STARTED

#### Problem Statement

Currently BGT thresholds are passed from DreamConfig but not all are exposed.

**Current Config Mapping (dream_explorer.py lines 447-455):**

```python
# Create BGT config from DreamConfig
bgt_config = BGTConfig(
    semantic_distance_threshold=self.config.semantic_distance_threshold,
    pmi_threshold=self.config.pmi_threshold,
    novelty_threshold=self.config.min_novelty_score,
    corpus_size_n=self.config.corpus_size_n,
    max_total_insights=self.config.max_insights,
    seed=seed,
)
```

**DreamConfig (r5_config.py lines 50-100):**

Need to verify all thresholds are in DreamConfig.

#### What Needs To Be Done

1. Ensure DreamConfig has all BGT thresholds
2. Add cold-start profiles (production vs cold-start)
3. Document threshold meanings

**Proposed DreamConfig Update:**

```python
@dataclass
class DreamConfig:
    # ... existing ...

    # BGT-SM thresholds
    semantic_distance_threshold: float = 0.5  # Cold-start: 0.5, production: 0.7
    pmi_threshold: float = 1.5  # Cold-start: 1.5, production: 3.0
    min_novelty_score: float = 0.3  # Cold-start: 0.3, production: 0.5

    # Cold-start detection
    bgt_cold_start_threshold: int = 100  # If corpus < 100, use cold-start thresholds
```

#### Acceptance Criteria

- [ ] All 4 thresholds in DreamConfig
- [ ] Cold-start vs production profiles
- [ ] Documentation of threshold meanings

---

## Epic M3-E3: Testing and Validation

**Purpose:** Add integration tests to verify BGT-SM produces insights after fixes.

---

### Issue M3-E3-I1: Add BGT-SM integration test

- **File:** `tests/k0/modules/consolidation/algorithms/test_bgt_sm_integration.py`
- **Status:** NOT STARTED

#### What Needs To Be Done

Create integration test with KG entities, edges, and embeddings:

```python
import pytest
import random
from k0.modules.consolidation.algorithms.bgt_sm import (
    BisociativeGraphTraversal, BGTConfig
)

class TestBGTSMIntegration:
    def test_bgt_generates_insights_with_kg_data(self):
        """Verify BGT-SM generates insights from KG."""

        # Create entities with embeddings
        entities = []
        embeddings = {}
        for i in range(100):
            entity_id = f"entity_{i}"
            entities.append(MockEntity(
                entity_id=entity_id,
                entity_type="CONCEPT" if i % 3 == 0 else "PERSON",
                observation_count=random.randint(5, 50),
            ))
            # Random embedding (normally distributed)
            embeddings[entity_id] = [random.gauss(0, 1) for _ in range(128)]

        # Create edges (random connections)
        edges = []
        for i in range(500):
            src = f"entity_{random.randint(0, 99)}"
            tgt = f"entity_{random.randint(0, 99)}"
            if src != tgt:
                edges.append(MockEdge(
                    source_id=src,
                    target_id=tgt,
                    relation_type="RELATES_TO",
                    confidence=random.uniform(0.5, 1.0),
                ))

        # Configure with cold-start thresholds
        config = BGTConfig(
            semantic_distance_threshold=0.5,  # Lower for cold-start
            pmi_threshold=1.5,
            novelty_threshold=0.3,
            corpus_size_n=100,
            cold_start_threshold=50,  # Ensure not in cold-start mode
            seed=42,
        )

        bgt = BisociativeGraphTraversal(config=config)

        # Select seed entities
        seed_entities = [f"entity_{i}" for i in range(5)]

        insights = bgt.discover(
            entities=entities,
            edges=edges,
            seed_entity_ids=seed_entities,
            embeddings=embeddings,
            rng_seed=42,
        )

        # Should generate at least some insights
        assert len(insights) >= 1

        # Verify insight structure
        for insight in insights:
            assert insight.seed_entity_id in seed_entities
            assert insight.target_entity_id.startswith("entity_")
            assert insight.novelty_score > 0
            assert insight.pmi > 0
            assert len(insight.insight_text) > 0

@dataclass
class MockEntity:
    entity_id: str
    entity_type: str
    observation_count: int

@dataclass
class MockEdge:
    source_id: str
    target_id: str
    relation_type: str
    confidence: float
```

#### Acceptance Criteria

- [ ] Test with 100+ entities
- [ ] Test with 500+ edges
- [ ] Test with embeddings for semantic distance
- [ ] Verify insights_generated > 0
- [ ] Test cold-start threshold behavior

---

# Milestone M4: SPC-UQ (Schematic Pattern Completion)

**Goal:** Reconstruct 5-15 incomplete episodes per cycle
**Current:** 0 reconstructions
**Blockers:** Missing ambiguity_score field, empty schemas array

## Epic M4-E1: Ambiguity Score Field

**Purpose:** Add `ambiguity_score` field to EpisodeCluster so SPC-UQ can detect gaps.

---

### Issue M4-E1-I1: Add ambiguity_score to EpisodeCluster

- **File:** `k0/pipelines/p03/phase_outputs.py`
- **Lines:** ~84 (EpisodeCluster class)
- **Status:** NOT STARTED (same as M0-E2-I4)

#### Problem Statement

SPC-UQ uses `ambiguity_score` to identify episodes with high uncertainty that need reconstruction:

**Gap Detection Logic (spc_uq.py lines 495-505):**

```python
# Check ambiguity
ambiguity = self._get_attr(episode, "ambiguity_score", 0.0)
if ambiguity > self.config.ambiguity_threshold:  # threshold = 0.5
    gaps.append(
        AttributeGap(
            attribute_name="ambiguous_content",
            gap_type=GapType.CONTENT,
            priority=0.9,  # High priority for ambiguous episodes
            ambiguity_score=ambiguity,
        )
    )
```

**Ambiguity Threshold (spc_uq.py lines 54-55):**

```python
# Ambiguity score threshold for gap detection
P03_SPC_AMBIGUITY_THRESHOLD = 0.5
```

**EpisodeProtocol (spc_uq.py lines 128-132):**

```python
@runtime_checkable
class EpisodeProtocol(Protocol):
    @property
    def ambiguity_score(self) -> float: ...  # Required by SPC-UQ!
```

#### What Needs To Be Done

Same as M0-E2-I4. Add field to EpisodeCluster:

```python
# In phase_outputs.py, EpisodeCluster class:
ambiguity_score: float = 0.0  # SPC-UQ gap detection field
```

#### Acceptance Criteria

- [ ] Field `ambiguity_score: float` added to EpisodeCluster
- [ ] Default is 0.0 (no ambiguity)
- [ ] Docstring mentions SPC-UQ usage

---

### Issue M4-E1-I2: Compute ambiguity_score in R2

- **File:** `k0/pipelines/p03/phases/r2_episodic_integrator.py`
- **Lines:** 1060-1210 (`_build_episode_cluster` method)
- **Status:** NOT STARTED (same as M0-E2-I5)

#### Problem Statement

Need to compute `ambiguity_score` from missing field ratio during R2 clustering.

**Proposed Calculation:**

```python
# Count missing fields
required_fields = [
    "primary_location",
    "episode_type",
    "participants",
    "summary",
]

missing_count = sum(
    1 for f in required_fields
    if not getattr(cluster_data, f, None)
)

# Ambiguity = ratio of missing fields
ambiguity_score = missing_count / len(required_fields)  # 0.0 to 1.0
```

**Gap Detection (spc_uq.py lines 446-510):**

```python
def identify_gaps(self, episode: Any) -> List[AttributeGap]:
    """Find missing or uncertain attributes in an episode."""
    gaps: List[AttributeGap] = []

    # Check location
    location = self._get_attr(episode, "location_name")
    if not location:
        gaps.append(AttributeGap(
            attribute_name="location_name",
            gap_type=GapType.LOCATION,
            priority=0.8,
        ))

    # Check participants
    participants = self._get_attr(episode, "participants")
    if not participants:
        gaps.append(AttributeGap(
            attribute_name="participants",
            gap_type=GapType.PARTICIPANTS,
            priority=0.7,
        ))

    # Check activity type
    activity = self._get_attr(episode, "activity_type")
    if not activity:
        gaps.append(AttributeGap(
            attribute_name="activity_type",
            gap_type=GapType.ACTIVITY,
            priority=0.6,
        ))
```

#### What Needs To Be Done

Add computation in `_build_episode_cluster()`:

```python
# In r2_episodic_integrator.py _build_episode_cluster():

# Compute ambiguity score from missing fields
required_fields = [
    ("primary_location", cluster_data.get("primary_location")),
    ("episode_type", cluster_data.get("episode_type")),
    ("summary", cluster_data.get("summary")),
]
missing = sum(1 for _, v in required_fields if not v)
ambiguity_score = missing / len(required_fields)

# Create cluster with ambiguity score
return EpisodeCluster(
    # ... existing fields ...
    ambiguity_score=ambiguity_score,
)
```

#### Acceptance Criteria

- [ ] ambiguity_score computed from missing field ratio
- [ ] Value range 0.0 to 1.0
- [ ] Episodes with missing fields have score > 0.5
- [ ] SPC-UQ can detect ambiguous episodes

---

## Epic M4-E2: Schema Population

**Purpose:** Load schemas from st_sem for SPC-UQ reconstruction guidance.

---

### Issue M4-E2-I1: Audit st_sem for available schemas

- **Status:** NOT STARTED

#### Problem Statement

SPC-UQ receives `schemas=[]` (empty list), so no schema-guided reconstruction can occur:

**DreamExplorer Schema Passing (dream_explorer.py lines 688-691):**

```python
reconstructions = simulator.simulate(
    episodes=input_data.recent_episodes,
    fragments=fragments,
    schemas=[],  # Issue 8.1.9 will provide schemas from semantic memory
    context=context,
    rng_seed=seed,
)
```

**st_sem Table Contents (from R5_PHASE_ALGORITHM_ANALYSIS.md):**

| Table | Count | Purpose |
|-------|-------|---------|
| st_sem | 749 | Semantic memory (patterns/schemas) |

**st_sem Pattern Types:**

Need to query to discover schema types:

```sql
SELECT pattern_type, COUNT(*)
FROM st_sem
GROUP BY pattern_type
ORDER BY COUNT(*) DESC;
```

#### What Needs To Be Done

1. Run audit query to see what pattern types exist in st_sem
2. Identify which can be used as schemas for SPC-UQ
3. Document schema format expected by SPC-UQ

**SemanticPattern Protocol (spc_uq.py lines 138-147):**

```python
@runtime_checkable
class SemanticPattern(Protocol):
    """Protocol for semantic patterns/schemas."""

    pattern_id: str
    activity_type: str
    confidence: float

    def get_attribute_distribution(
        self,
        attribute_name: str,
    ) -> Dict[str, float]: ...
```

#### Acceptance Criteria

- [ ] Audit query run on st_sem
- [ ] Pattern types documented
- [ ] Schema format requirements identified
- [ ] Conversion approach planned

---

### Issue M4-E2-I2: Create schema_query syscall

- **File:** `k0/kernel/syscalls.py`
- **Status:** NOT STARTED

#### Problem Statement

Need syscall to load schemas from st_sem for SPC-UQ.

**Proposed Syscall Signature:**

```python
@as_syscall(name="semantic_schema_query", capability="st_sem.read")
async def semantic_schema_query(
    self,
    *,
    pattern_types: Optional[List[str]] = None,
    min_confidence: float = 0.5,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """
    Query semantic schemas for pattern completion.

    Args:
        pattern_types: Filter by pattern type (e.g., ["ACTIVITY", "LOCATION"])
        min_confidence: Minimum confidence threshold
        limit: Maximum schemas to return

    Returns:
        List of schema dicts with pattern_id, activity_type,
        confidence, attribute_distributions
    """
```

**SQL:**

```sql
SELECT
    sem_id as pattern_id,
    pattern_type as activity_type,
    confidence_score as confidence,
    pattern_attributes_json
FROM st_sem
WHERE confidence_score >= :min_confidence
  AND (:pattern_types IS NULL OR pattern_type = ANY(:pattern_types))
ORDER BY confidence_score DESC
LIMIT :limit
```

#### Acceptance Criteria

- [ ] Syscall `semantic_schema_query` implemented
- [ ] Capability `st_sem.read` required
- [ ] Returns schemas in SemanticPattern-compatible format
- [ ] Filter by pattern_type works

---

### Issue M4-E2-I3: Pass schemas to SPC-UQ from syscall

- **File:** `k0/pipelines/p03/phases/r5_dream_explorer.py`
- **Lines:** ~300-350 (input preparation)
- **Status:** NOT STARTED

#### Problem Statement

After M4-E2-I2, need to call syscall and pass results to DreamExplorer.

**R5DreamExplorer Input Building (r5_dream_explorer.py):**

```python
# In _build_dream_input():
# TODO: Load schemas from st_sem via semantic_schema_query

# Current:
input_data = DreamExplorerInput(
    recent_episodes=merged_episodes,
    kg_entities=kg_entities,
    kg_edges=kg_edges,
    # schemas not passed!
)
```

**DreamExplorerInput (dream/models.py):**

```python
@dataclass
class DreamExplorerInput:
    recent_episodes: List[Any]
    kg_entities: List[Any]
    kg_edges: List[Any]
    schemas: List[Any] = field(default_factory=list)  # Add if missing!
```

#### What Needs To Be Done

1. Add `schemas` field to DreamExplorerInput if missing
2. Call `semantic_schema_query` syscall in R5
3. Convert syscall results to SemanticPattern objects
4. Pass to DreamExplorerInput

**Proposed Code:**

```python
# In r5_dream_explorer.py:

# Load schemas from st_sem
schema_results = await self._request_context.syscall(
    "semantic_schema_query",
    pattern_types=["ACTIVITY", "LOCATION", "ROUTINE"],
    min_confidence=0.5,
    limit=50,
)

# Convert to SemanticPattern objects
schemas = [
    SemanticPatternData(
        pattern_id=s["pattern_id"],
        activity_type=s["activity_type"],
        confidence=s["confidence"],
        attributes=json.loads(s.get("pattern_attributes_json", "{}")),
    )
    for s in schema_results
]

# Build input with schemas
input_data = DreamExplorerInput(
    recent_episodes=merged_episodes,
    kg_entities=kg_entities,
    kg_edges=kg_edges,
    schemas=schemas,
)
```

#### Acceptance Criteria

- [ ] Schemas loaded via syscall in R5
- [ ] Converted to SemanticPattern format
- [ ] Passed to DreamExplorerInput.schemas
- [ ] SPC-UQ receives non-empty schemas list

---

## Epic M4-E3: Testing and Validation

**Purpose:** Add integration tests to verify SPC-UQ produces reconstructions.

---

### Issue M4-E3-I1: Add SPC-UQ integration test

- **File:** `tests/k0/modules/consolidation/algorithms/test_spc_uq_integration.py`
- **Status:** NOT STARTED

#### What Needs To Be Done

Create integration test with ambiguous episodes and schemas:

```python
import pytest
from k0.modules.consolidation.algorithms.spc_uq import (
    EpisodicSimulator, SPCConfig, SimpleEpisode
)

class TestSPCUQIntegration:
    def test_spc_generates_reconstructions_with_gaps(self):
        """Verify SPC-UQ reconstructs episodes with gaps."""

        # Create episodes with missing fields (high ambiguity)
        episodes = [
            SimpleEpisode(
                episode_id="ep_1",
                start_time_ms=1705000000000,
                _location_name=None,  # Missing!
                _activity_type="coffee",
                _participants=None,  # Missing!
                _ambiguity_score=0.6,  # Above 0.5 threshold
            ),
            SimpleEpisode(
                episode_id="ep_2",
                start_time_ms=1705003600000,
                _location_name="starbucks",
                _activity_type=None,  # Missing!
                _ambiguity_score=0.4,
            ),
        ]

        # Create schemas for reconstruction guidance
        schemas = [
            MockSchema(
                pattern_id="schema_coffee",
                activity_type="coffee",
                confidence=0.9,
                attribute_distributions={
                    "location_name": {"starbucks": 0.5, "peets": 0.3, "local_cafe": 0.2},
                    "participants": {"alone": 0.6, "friend": 0.3, "coworker": 0.1},
                },
            ),
        ]

        config = SPCConfig(
            simulation_count=50,
            min_confidence=0.3,
            ambiguity_threshold=0.5,
        )

        simulator = EpisodicSimulator(config=config)
        reconstructions = simulator.simulate(
            episodes=episodes,
            fragments=[],
            schemas=schemas,
            rng_seed=42,
        )

        # Should reconstruct ambiguous episodes
        assert len(reconstructions) >= 1

        # Verify reconstruction has filled gaps
        for recon in reconstructions:
            assert recon.confidence_score > 0.3
            assert recon.temporal_coherence_score > 0

@dataclass
class MockSchema:
    pattern_id: str
    activity_type: str
    confidence: float
    attribute_distributions: Dict[str, Dict[str, float]]

    def get_attribute_distribution(self, attr: str) -> Dict[str, float]:
        return self.attribute_distributions.get(attr, {})
```

#### Acceptance Criteria

- [ ] Test with episodes having ambiguity_score > 0.5
- [ ] Test with non-empty schemas
- [ ] Verify reconstructions_generated > 0
- [ ] Reconstructions have filled gaps

---

# Milestone M5: TDL-HCO (Temporal Difference Learning)

**Goal:** Generate 3-10 routine optimizations per cycle
**Current:** 0 optimizations
**Blockers:** st_procedural empty (no routines from prior cycles), depends on M2

## Epic M5-E1: Routine Input

**Purpose:** Ensure TDL-HCO receives routines from st_procedural (accumulated) and RoutineDetector (current cycle).

---

### Issue M5-E1-I1: Verify TDL-HCO receives merged routines

- **File:** `k0/modules/consolidation/dream/dream_explorer.py`
- **Lines:** 927-1015 (`_run_tdl_hco` method)
- **Status:** READY (depends on M0-E1-I4)

#### Problem Statement

TDL-HCO currently extracts routines from episodes using `extract_routines_from_episodes()`. This works for current-cycle data but misses accumulated routines from st_procedural.

**Current TDL-HCO Logic (dream_explorer.py lines 985-995):**

```python
# Extract routines from episodic memory
routines = extract_routines_from_episodes(
    episodes=input_data.recent_episodes,
    min_routine_length=3,
    min_occurrences=2,  # Lower threshold for testing
)

if not routines:
    self._logger.debug("TDL-HCO skipped: no routines found")
    return []
```

**What extract_routines_from_episodes Does (tdl_hco.py lines 85-130):**

```python
def extract_routines_from_episodes(
    episodes: List[Any],
    min_routine_length: int = 3,
    min_occurrences: int = 3,
) -> List[RoutineData]:
    """
    Extract behavioral routines from episodes.

    Groups episodes by activity_type + time_of_day pattern.
    Returns routines that occur min_occurrences times.
    """
    # Group by (activity_type, hour_bin)
    patterns: Dict[str, List] = {}
    for ep in episodes:
        activity = getattr(ep, "activity_type", getattr(ep, "episode_type", None))
        # ... pattern extraction logic ...
```

**R5 Routine Loading (r5_dream_explorer.py lines 820-870):**

Parity resolution now loads accumulated routines via `procedural_memory_query` syscall.

#### What Needs To Be Done

Verify that accumulated routines are merged into `input_data.recent_episodes` so `extract_routines_from_episodes` can find patterns:

1. Check `_load_accumulated_routines()` is called
2. Check routines merged correctly in DreamExplorerInput
3. Optionally: Pass routines directly instead of re-extracting

**Verification Test:**

```python
# After parity resolution:
# - input_data.recent_episodes should contain 100+ episodes
# - extract_routines_from_episodes should find 3+ patterns
```

#### Acceptance Criteria

- [x] `_load_accumulated_routines()` implemented (M0-E1-I4)
- [ ] Routines from st_procedural included in extraction
- [ ] TDL-HCO finds 3+ routines for optimization

---

### Issue M5-E1-I2: Pass RoutineDetector candidates to TDL-HCO

- **File:** `k0/modules/consolidation/dream/dream_explorer.py`
- **Lines:** 180-200 (algorithm execution flow)
- **Status:** NOT STARTED

#### Problem Statement

RoutineDetector produces `RoutineCandidate` objects. TDL-HCO expects `Routine` objects. These should be connected.

**RoutineDetector Output (routine_detector.py lines 40-55):**

```python
@dataclass
class RoutineCandidate:
    routine_id: str
    signature: str  # "activity:location:time_bin"
    occurrences: int
    episodes: List[Dict[str, Any]]
    average_duration_minutes: float
    time_bins: List[str]
    confidence: float
```

**TDL-HCO Input (tdl_hco.py lines 77-90):**

```python
class Routine(Protocol):
    """Protocol for a behavioral routine."""
    routine_id: str
    routine_name: str
    steps: List[RoutineStep]
    occurrence_count: int

class RoutineStep(Protocol):
    step_id: str
    step_name: str
    avg_duration_seconds: float
    reward_signal: float
```

**Current Execution Flow (dream_explorer.py lines 180-195):**

```python
# Independent algorithms
parallel_results = await self._run_parallel_algorithms(input_data, cycle_id)

# RoutineDetector runs here
routine_result = await self._run_with_timeout(
    algorithm_name="routine_detector",
    coro=self._run_routine_detector(input_data, cycle_id),
    timeout_seconds=self.config.routine_detector_timeout,
)

# TDL-HCO runs separately, doesn't receive routine_result
routine_optimizations = await self._run_with_timeout(
    algorithm_name="tdl_hco",
    coro=self._run_tdl_hco(input_data, cycle_id, compute_budget),
    timeout_seconds=self.config.tdl_timeout,
)
```

#### What Needs To Be Done

Option A: Convert RoutineCandidate to Routine and pass to TDL-HCO:

```python
# After RoutineDetector completes:
detected_routines = routine_result if routine_result else []

# Convert to TDL-HCO format
tdl_routines = [
    self._convert_candidate_to_routine(r)
    for r in detected_routines
]

# Pass to TDL-HCO
routine_optimizations = await self._run_tdl_hco(
    input_data=input_data,
    cycle_id=cycle_id,
    detected_routines=tdl_routines,  # New parameter
)
```

Option B: Run RoutineDetector first, add results to input_data:

```python
# Run RoutineDetector before TDL-HCO
detected_routines = await self._run_routine_detector(input_data, cycle_id)

# Add to input_data for TDL-HCO
input_data_with_routines = DreamExplorerInput(
    recent_episodes=input_data.recent_episodes,
    detected_routines=detected_routines,
    # ... other fields ...
)
```

#### Acceptance Criteria

- [ ] RoutineDetector output passed to TDL-HCO
- [ ] Conversion from RoutineCandidate to Routine
- [ ] TDL-HCO receives detected_routines parameter

---

## Epic M5-E2: Execution Order

**Purpose:** Ensure RoutineDetector populates st_procedural so TDL-HCO has data in subsequent cycles.

---

### Issue M5-E2-I1: Ensure RoutineDetector populates st_procedural first

- **File:** `k0/pipelines/p03/phases/r7_layer_writer.py`
- **Status:** BLOCKED (depends on M2 - RoutineDetector must produce output first)

#### Problem Statement

TDL-HCO needs routines from prior cycles, but st_procedural is empty because:

1. RoutineDetector produces 0 candidates (field mismatch - now fixed)
2. R7 doesn't write RoutineCandidate to st_procedural
3. Next cycle, TDL-HCO has no accumulated routines

**R7 Layer Writing (r7_layer_writer.py lines 200-300):**

```python
# R7 writes phase outputs to truth layers:
# - st_epi: Episodes
# - st_sem: Semantic patterns (insights, lessons)
# - st_prospective: Prospective memories
# - st_procedural: Routines (from RoutineDetector)
```

**Dependency Chain:**

```
Cycle N:
  R2 → R4 → R5 (RoutineDetector produces candidates)
  R7 writes candidates to st_procedural

Cycle N+1:
  R5 loads from st_procedural via procedural_memory_query
  TDL-HCO receives accumulated routines
```

#### What Needs To Be Done

1. Fix RoutineDetector field mapping (M2-E1) - DONE
2. Verify R7 writes RoutineCandidate to st_procedural
3. Verify procedural_memory_query returns routines
4. Run multiple cycles to populate st_procedural

**Verification:**

```sql
-- After cycle N with RoutineDetector fix:
SELECT COUNT(*) FROM st_procedural;
-- Expected: > 0 routines

-- Check routine structure:
SELECT routine_id, routine_signature, occurrence_count
FROM st_procedural
LIMIT 10;
```

#### Acceptance Criteria

- [ ] RoutineDetector produces candidates (M2)
- [ ] R7 writes to st_procedural correctly
- [ ] procedural_memory_query returns accumulated routines
- [ ] TDL-HCO receives 3+ routines in cycle N+1

---

## Epic M5-E3: Testing and Validation

**Purpose:** Add integration tests to verify TDL-HCO produces optimizations.

---

### Issue M5-E3-I1: Add TDL-HCO integration test

- **File:** `tests/k0/modules/consolidation/algorithms/test_tdl_hco_integration.py`
- **Status:** NOT STARTED

#### What Needs To Be Done

Create integration test with routines that have bottlenecks:

```python
import pytest
from k0.modules.consolidation.algorithms.tdl_hco import (
    TemporalDifferenceLearning, TDLConfig, RoutineData, RoutineStepData
)

class TestTDLHCOIntegration:
    def test_tdl_generates_optimizations_with_bottlenecks(self):
        """Verify TDL-HCO detects bottlenecks and generates optimizations."""

        # Create routine with bottleneck
        # Morning routine: wake -> shower -> BOTTLENECK(find_keys) -> commute
        routine = RoutineData(
            routine_id="morning_routine",
            routine_name="Morning Routine",
            steps=[
                RoutineStepData(
                    step_id="step_1",
                    step_name="wake_up",
                    step_index=0,
                    avg_duration_seconds=60,
                    reward_signal=0.5,  # Neutral
                ),
                RoutineStepData(
                    step_id="step_2",
                    step_name="shower",
                    step_index=1,
                    avg_duration_seconds=600,  # 10 min
                    reward_signal=0.7,  # Positive
                ),
                RoutineStepData(
                    step_id="step_3",
                    step_name="find_keys",  # BOTTLENECK
                    step_index=2,
                    avg_duration_seconds=300,  # 5 min wasted
                    reward_signal=-0.5,  # Negative! V(s) drops sharply
                ),
                RoutineStepData(
                    step_id="step_4",
                    step_name="commute",
                    step_index=3,
                    avg_duration_seconds=1800,  # 30 min
                    reward_signal=0.3,
                ),
            ],
            occurrence_count=10,
        )

        config = TDLConfig(
            learning_rate=0.1,
            discount_factor=0.9,
            bottleneck_threshold=-2.0,  # V drop > 2.0 = bottleneck
            max_optimizations=5,
            seed=42,
        )

        tdl = TemporalDifferenceLearning(config=config)
        optimizations = tdl.optimize(
            routines=[routine],
            rng_seed=42,
        )

        # Should detect find_keys as bottleneck
        assert len(optimizations) >= 1

        # Verify bottleneck identification
        opt = optimizations[0]
        assert "find_keys" in opt.bottleneck_step or "step_3" in opt.bottleneck_step
        assert opt.expected_improvement > 0
        assert len(opt.suggestion) > 0

#### Acceptance Criteria

- [ ] Test with routine having negative reward steps
- [ ] Bottleneck detection works (V drop > 2.0)
- [ ] Optimization suggestions generated
- [ ] expected_improvement calculated

---

# Milestone M6: MCTS (Monte Carlo Tree Search)

**Goal:** Maintain 1+ scenario per cycle
**Current:** 1 scenario (WORKING)
**Status:** WORKING - No immediate action needed

## Epic M6-E1: Monitoring

**Purpose:** Add observability metrics for MCTS performance tracking.

---

### Issue M6-E1-I1: Add MCTS metrics

- **Status:** NOT STARTED (low priority - algorithm working)

#### Problem Statement

MCTS is producing output (1 scenario), but we lack visibility into:

- How many rollouts were performed
- Simulation depth achieved
- Average reward per rollout
- Time spent in exploration vs exploitation

**MCTS Implementation (mcts.py expected location):**

```python
# Metrics to track:
- scenarios_generated: Counter
- rollouts_per_scenario: Histogram
- simulation_depth: Histogram
- exploration_ratio: Gauge (UCB exploration vs best action)
```

#### What Needs To Be Done

Add Prometheus metrics for monitoring:

```python
from prometheus_client import Counter, Histogram, Gauge

MCTS_SCENARIOS = Counter(
    "r5_mcts_scenarios_total",
    "Total scenarios generated by MCTS"
)

MCTS_ROLLOUTS = Histogram(
    "r5_mcts_rollouts_per_scenario",
    "Rollouts used per scenario",
    buckets=[10, 50, 100, 200, 500, 1000]
)

MCTS_DEPTH = Histogram(
    "r5_mcts_simulation_depth",
    "Maximum depth reached per simulation",
    buckets=[1, 2, 3, 5, 10, 20]
)
```

#### Acceptance Criteria

- [ ] Prometheus metrics exposed
- [ ] Grafana dashboard panel for MCTS
- [ ] Alert on scenarios < 1 per cycle

---

# Milestone M7: IntentSignalDetector

**Goal:** Maintain 50+ signals per cycle
**Current:** 74 signals (WORKING)
**Status:** WORKING - No immediate action needed

## Epic M7-E1: Monitoring

**Purpose:** Add observability for intent signal quality and distribution.

---

### Issue M7-E1-I1: Add IntentSignalDetector metrics

- **Status:** NOT STARTED (low priority - algorithm working)

#### Problem Statement

IntentSignalDetector produces 74 signals, but we lack breakdown by type:

**Signal Types (intent_signal_detector.py):**

```python
class IntentSignalType(str, Enum):
    REMINDER = "reminder"      # Future action reminders
    DECISION = "decision"      # Decision points detected
    LESSON = "lesson"          # Lessons learned
    MILESTONE = "milestone"    # Achievement markers
    FOLLOW_UP = "follow_up"    # Items needing follow-up
```

#### What Needs To Be Done

Add per-type metrics:

```python
from prometheus_client import Counter, Gauge

INTENT_SIGNALS = Counter(
    "r5_intent_signals_total",
    "Total intent signals detected",
    ["signal_type"]  # Label by type
)

# Usage:
INTENT_SIGNALS.labels(signal_type="reminder").inc()
INTENT_SIGNALS.labels(signal_type="lesson").inc()
```

**Dashboard Query:**

```promql
sum by (signal_type) (r5_intent_signals_total)
```

#### Acceptance Criteria

- [ ] Per-type breakdown metrics
- [ ] Prometheus metrics exposed
- [ ] Grafana panel showing distribution
- [ ] Alert on signals < 50 per cycle

## Epic M7-E1: Monitoring

### Issue M7-E1-I1: Add IntentSignalDetector metrics

- **Description:** Track signals by type (REMINDER, DECISION, LESSON)
- **Status:** NOT STARTED
- **Acceptance:**
  - [ ] Per-type breakdown
  - [ ] Prometheus metrics

---

# Dependency Graph

```
M0-E1 (Parity Resolution Layer)
  ├── M0-E1-I1 episodes_query syscall ✓ IMPLEMENTED
  ├── M0-E1-I2 procedural_memory_query syscall ✓ IMPLEMENTED
  ├── M0-E1-I3 episode merge logic ✓ IMPLEMENTED
  ├── M0-E1-I4 routine merge logic ✓ IMPLEMENTED
  └── M0-E1-I5 config limits (accumulated_episode_limit) ✓ IMPLEMENTED

M0-E2 (EpisodeCluster Compatibility)
  ├── M0-E2-I1 CPN properties (sentiment_score, salience_score) ✓ IMPLEMENTED
  ├── M0-E2-I2 entity_ids field → TODO
  ├── M0-E2-I3 populate entity_ids in R2 → TODO (depends on I2)
  ├── M0-E2-I4 ambiguity_score field → TODO
  └── M0-E2-I5 compute ambiguity_score in R2 → TODO (depends on I4)

M1 (CPN - Causal Perturbation Network)
  ├── M1-E1: Episode Input
  │   ├── I1 sentiment_score property ✓ (via M0-E2-I1)
  │   ├── I2 salience_score property ✓ (via M0-E2-I1)
  │   └── I3 entity_ids access → BLOCKED (needs M0-E2-I2, M0-E2-I3)
  ├── M1-E2: CAUSES Edge Generation
  │   ├── I1 audit CAUSES inference logic ✓ DOCUMENTED
  │   ├── I2 lower precedence threshold → TODO
  │   ├── I3 lower min_observations → TODO
  │   ├── I4 use PRECEDES as weak causal → TODO (NEW)
  │   ├── I5 synthetic CAUSES from co-occurrence → TODO (NEW)
  │   └── I6 upgrade TEMPORALLY_ASSOCIATED → TODO (NEW)
  ├── M1-E3: Threshold Configuration
  │   └── I1 emotional_threshold ✓ (already 0.3)
  └── M1-E4: Testing → TODO

M2 (RoutineDetector - GAP-003)
  ├── M2-E1: Field Mapping Fix
  │   ├── I1 location field keys ✓ IMPLEMENTED
  │   └── I2 timestamp field key ✓ IMPLEMENTED
  ├── M2-E2: Merged Episode Data
  │   ├── I1 verify merged episodes → READY
  │   └── I2 execution order optimization → TODO
  └── M2-E3: Testing → TODO

M3 (BGT-SM - Bisociative Graph Traversal)
  ├── M3-E1: Seed Entity Selection
  │   ├── I1 entity_ids from episodes → BLOCKED (needs M0-E2-I2, M0-E2-I3)
  │   └── I2 KG fallback selection → READY
  ├── M3-E2: Threshold Tuning
  │   ├── I1 semantic_distance_threshold 0.7→0.5 → TODO
  │   ├── I2 pmi_threshold 3.0→1.5 → TODO
  │   ├── I3 novelty_threshold 0.5→0.3 → TODO
  │   └── I4 DreamConfig exposure → TODO
  └── M3-E3: Testing → TODO

M4 (SPC-UQ - Schematic Pattern Completion)
  ├── M4-E1: Ambiguity Score
  │   ├── I1 field addition → TODO (same as M0-E2-I4)
  │   └── I2 R2 computation → TODO (same as M0-E2-I5)
  ├── M4-E2: Schema Population
  │   ├── I1 audit st_sem → TODO
  │   ├── I2 schema_query syscall → TODO
  │   └── I3 pass schemas to SPC-UQ → TODO
  └── M4-E3: Testing → TODO

M5 (TDL-HCO - Temporal Difference Learning)
  ├── M5-E1: Routine Input
  │   ├── I1 verify merged routines → READY (via M0-E1-I4)
  │   └── I2 RoutineDetector → TDL-HCO → TODO
  ├── M5-E2: Execution Order
  │   └── I1 st_procedural population → BLOCKED (needs M2 working)
  └── M5-E3: Testing → TODO

M6 (MCTS - Monte Carlo Tree Search)
  └── M6-E1: Monitoring
      └── I1 Prometheus metrics → TODO (low priority, working)

M7 (IntentSignalDetector)
  └── M7-E1: Monitoring
      └── I1 per-type metrics → TODO (low priority, working)
```

---

# Issue Summary

| Milestone | Epic | Issues | Done | In Progress | Blocked | TODO |
|-----------|------|--------|------|-------------|---------|------|
| M0 | E1 (Parity) | 5 | 5 | 0 | 0 | 0 |
| M0 | E2 (EpisodeCluster) | 5 | 1 | 0 | 0 | 4 |
| M1 | E1-E4 (CPN) | 10 | 3 | 0 | 1 | 6 |
| M2 | E1-E3 (RoutineDetector) | 6 | 2 | 0 | 0 | 4 |
| M3 | E1-E3 (BGT-SM) | 7 | 0 | 0 | 1 | 6 |
| M4 | E1-E3 (SPC-UQ) | 6 | 0 | 0 | 0 | 6 |
| M5 | E1-E3 (TDL-HCO) | 4 | 0 | 0 | 1 | 3 |
| M6 | E1 (MCTS) | 1 | 0 | 0 | 0 | 1 |
| M7 | E1 (IntentSignal) | 1 | 0 | 0 | 0 | 1 |
| **TOTAL** | | **45** | **11** | **0** | **3** | **31** |

**Progress: 24% Complete (11/45 issues)**

---

# Priority Execution Order

## Phase 1: Quick Wins (COMPLETED)

1. [x] M0-E1: Parity resolution syscalls and merge (5 issues)
2. [x] M0-E2-I1: CPN compatibility properties
3. [x] M2-E1: RoutineDetector field fix (2 issues)

**Result:** 8 issues completed, parity gap resolved, field mismatches fixed.

## Phase 2: Entity Enrichment (2-3 days)

**Critical Path:** CPN and BGT-SM both need entity_ids

1. [ ] M0-E2-I2: Add entity_ids field
2. [ ] M0-E2-I3: Populate entity_ids in R2
3. [ ] M3-E2: BGT-SM threshold tuning

**Unblocks:** M1-E1-I3 (CPN entity access), M3-E1-I1 (BGT-SM seed selection)

## Phase 3: CAUSES Edge Generation (2-3 days)

**Goal:** Increase CAUSES edges from 4 to 50-100+

1. [ ] M1-E2-I2: Lower CAUSES precedence threshold (0.75 → 0.60)
2. [ ] M1-E2-I3: Lower min_observations (5 → 3)
3. [ ] M1-E2-I4: Add PRECEDES as weak causal in CPN (+13 edges)
4. [ ] M1-E2-I5: Synthetic CAUSES from high-confidence co-occurrence (+50-100 edges)
5. [ ] M1-E2-I6: Upgrade TEMPORALLY_ASSOCIATED to CAUSES (+10-20 edges)

**Expected Results:**

| Strategy | Edges Added | Risk Level |
|----------|-------------|------------|
| Lower threshold | +20-30 | Low |
| Lower min_observations | +10-15 | Low |
| PRECEDES as weak causal | +13 | Medium |
| Synthetic from co-occurrence | +50-100 | Medium |
| Upgrade TEMPORALLY_ASSOCIATED | +10-20 | Low |
| **TOTAL** | **+100-180** | - |

**Unblocks:** CPN counterfactual generation

## Phase 4: Remaining Data Gaps (2-3 days)

1. [ ] M0-E2-I4: Add `ambiguity_score: float` field to EpisodeCluster
2. [ ] M0-E2-I5: Compute ambiguity_score in R2
3. [ ] M4-E2-I1: Audit st_sem for available schemas
4. [ ] M4-E2-I2: Create `semantic_schema_query` syscall
5. [ ] M4-E2-I3: Pass schemas to SPC-UQ

**Unblocks:** M4-E1 (SPC-UQ gap detection)

## Phase 5: Execution Flow Optimization (1-2 days)

1. [ ] M5-E1-I2: Pass RoutineDetector candidates to TDL-HCO
2. [ ] M2-E2-I2: Run RoutineDetector before TDL-HCO

**Unblocks:** M5 (TDL-HCO receives detected routines)

## Phase 6: Integration Testing (2 days)

1. [ ] M1-E4-I1: CPN integration test
2. [ ] M2-E3-I1, I2: RoutineDetector tests
3. [ ] M3-E3-I1: BGT-SM integration test
4. [ ] M4-E3-I1: SPC-UQ integration test
5. [ ] M5-E3-I1: TDL-HCO integration test

## Phase 7: Monitoring (Low Priority)

1. [ ] M6-E1-I1: MCTS Prometheus metrics
2. [ ] M7-E1-I1: IntentSignalDetector per-type metrics

---

# Expected Outcomes After Full Remediation

| Algorithm | Current | Expected | Delta |
|-----------|---------|----------|-------|
| CPN | 0 scenarios | 5-20 | +5-20 |
| RoutineDetector | 0 candidates | 5-20 | +5-20 |
| BGT-SM | 0 insights | 20-50 | +20-50 |
| SPC-UQ | 0 reconstructions | 5-15 | +5-15 |
| TDL-HCO | 0 optimizations | 3-10 | +3-10 |
| MCTS | 1 scenario | 1+ | Maintained |
| IntentSignalDetector | 74 signals | 50+ | Maintained |

**Total Expected Improvement:** From 75 to 110-180 outputs per cycle.

---

*End of R5 Algorithm Remediation Backlog*
*Last Updated: M0-M7 Code Discovery Session*
