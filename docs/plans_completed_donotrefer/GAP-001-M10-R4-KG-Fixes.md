# GAP-001 Milestone 10: R4 Knowledge Graph Quality Fixes

**Status**: Planning
**Created**: 2026-01-15
**Related**: GAP-001 M9 (R5 Dream Cold Start Fix)

---

## Overview

After GAP-001 M9 enabled observation_count accumulation, we discovered additional issues preventing causal edge generation and degrading KG quality.

---

## Issue Index

| Issue ID | Priority | Title | Status |
|----------|----------|-------|--------|
| M10.1 | 🔴 CRITICAL | Causal inference skips UPDATE_EDGE types | ✅ DONE |
| M10.2 | 🟠 HIGH | Fragmented stopword filtering in entity extraction | ✅ DONE |
| M10.3 | 🟠 HIGH | Edges always use RELATED_TO instead of ULTRABERT types | ✅ DONE |
| M10.4 | 🟡 MEDIUM | min_co_occurrence=1 allows low-quality edges | ✅ DONE |
| M10.5 | 🟡 MEDIUM | No entity confidence threshold | ✅ DONE |
| M10.6 | 🟡 MEDIUM | Entity deduplication incomplete | ✅ DONE |
| M10.7 | 🔵 LOW | No temporal relationship types (FOLLOWS, PRECEDES) | TODO |
| M10.8 | 🔵 LOW | Semantic pattern naming not descriptive | TODO |

---

## Issue M10.1: Causal Inference Skips UPDATE_EDGE Types

**Priority**: 🔴 CRITICAL
**Status**: ✅ DONE

### Problem

`_infer_causal_relationships()` only processes `CREATE_EDGE` types:

```python
# r4_kg_consolidator.py:1499-1501
for edge_update in edge_updates:
    if edge_update.update_type != KGUpdateType.CREATE_EDGE:
        continue  # SKIPS UPDATE_EDGE!
```

With GAP-001 M9, existing edges use `UPDATE_EDGE` to increment `observation_count`. Edges that accumulate 5+ observations are **never analyzed for causality**.

### Impact

- No CAUSES edges generated
- CPN counterfactual generation fails (requires CAUSES edges)
- R5 dream exploration produces 0 counterfactuals

### Files to Modify

- [x] `k0/pipelines/p03/phases/r4_kg_consolidator.py`

### Exploration Findings (2026-01-15)

**Flow Analysis:**

1. `_discover_relationships()` returns `List[KGUpdate]` with either:
   - `CREATE_EDGE` (new edges, observation_count from this batch)
   - `UPDATE_EDGE` (existing edges, observation_count = accumulated total)

2. `_infer_causal_relationships()` receives these updates but filters out `UPDATE_EDGE`

3. The `observation_count` check at line 1521 requires >= 5 observations:

   ```python
   if observations < self.config.granger_min_observations:  # 5
       continue
   ```

4. First batch: Edge created with count=1 → skipped (1 < 5)
5. Subsequent batches: Edge updated with count=6 → skipped (UPDATE_EDGE filtered)

**Key Data Structures:**

```python
@dataclass
class KGUpdate:
    update_type: KGUpdateType  # CREATE_EDGE or UPDATE_EDGE
    edge_id: Optional[str] = None
    source_id: Optional[str] = None
    target_id: Optional[str] = None
    relation_type: Optional[str] = None
    observation_count: int = 0

@dataclass
class CausalEdge:
    source_id: str
    target_id: str
    relation_type: str  # Always 'CAUSES'
    confidence: float
    observation_count: int
    precedence_ratio: float
```

### Solution

**Change**: Modify `_infer_causal_relationships()` to process BOTH `CREATE_EDGE` and `UPDATE_EDGE` types.

```python
# BEFORE (line 1499-1501):
for edge_update in edge_updates:
    if edge_update.update_type != KGUpdateType.CREATE_EDGE:
        continue

# AFTER:
for edge_update in edge_updates:
    # GAP-001 M10.1: Process both CREATE and UPDATE edges
    # UPDATE_EDGE contains accumulated observation_count from M9 fix
    if edge_update.update_type not in (KGUpdateType.CREATE_EDGE, KGUpdateType.UPDATE_EDGE):
        continue
```

**Why this works:**

- `UPDATE_EDGE` now has `observation_count` = previous + new (accumulated across batches)
- When observation_count >= 5, Granger causality check can proceed
- All other logic (cluster lookup, precedence ratio, etc.) works the same

### Tests

```python
# Test that UPDATE_EDGE with observation_count >= 5 creates causal edge
@pytest.mark.asyncio
async def test_causal_inference_processes_update_edge():
    """M10.1: UPDATE_EDGE with sufficient observations should create CAUSES edge."""
    # Setup: Create UPDATE_EDGE with observation_count=6 (> granger_min_observations=5)
    # Verify: CausalEdge is created with relation_type="CAUSES"

## Issue M10.2: Fragmented Stopword Filtering in Entity Extraction

**Priority**: 🟠 HIGH
**Status**: ✅ DONE

### Problem (CORRECTED)

Original diagnosis was incorrect. Stopword filtering EXISTS but is **fragmented and not universal**:

1. **`GARBAGE_ENTITY_WORDS`** (70+ words) - Only checked for `VALIDATED_NER_FAMILY` labels
2. **`BERT_NER_PERSON_STOPWORDS`** (30+ words) - Only for `bert_ner` source with PERSON label
3. **`BERT_NER_LOC_STOPWORDS`** - Only for `bert_ner` source with LOC label
4. **`ner_general` head** - Has ZERO stopword filtering
5. **`temporal` head** - Has ZERO stopword filtering

### Root Cause

In `_map_entity()` (lines 896-1012):
- NER_FAMILY filtering: Lines 905-925 (3-tier: TRUSTED/REJECTED/VALIDATED)
- BERT-NER filtering: Lines 957-978 (PERSON and LOC stopwords)
- **MISSING**: Universal garbage word check for ALL heads/labels
- **MISSING**: Stopword check for `ner_general` and `temporal` heads

### Impact

- Garbage entities ("the", "a", "Good", "Need") pass through from `ner_general`/`temporal`
- KG polluted with non-entities
- Edges created between noise and real entities
- Insight quality degraded

### Files

- [x] `k0/modules/consolidation/algorithms/entity_extractor.py` - EXPLORED

### Solution

Add universal stopword filtering at the TOP of `_map_entity()` before any label-specific logic:

```python
def _map_entity(self, raw: dict[str, Any], source_head: str) -> ExtractedEntity | None:
    label = raw.get("label", "")
    text = raw.get("text", "")

    if not label or not text:
        return None

    # === UNIVERSAL STOPWORD FILTERING (ALL HEADS) ===
    normalized_check = self.normalize_name(text)
    if normalized_check.lower() in self.GARBAGE_ENTITY_WORDS:
        logger.debug(f"Filtered garbage entity: '{text}' ({label}) from {source_head}")
        return None

    # Filter short entities (tokenization artifacts)
    if len(normalized_check) <= 1:
        logger.debug(f"Filtered short entity: '{text}' ({label}) from {source_head}")
        return None

    # ... rest of existing label-specific filtering ...
```

### Tests

```python
@pytest.mark.parametrize("garbage_word", ["the", "a", "and", "Good", "Need", "met", "was"])
def test_garbage_words_filtered_all_heads(garbage_word):
    """M10.2: Garbage words should be filtered regardless of NER head."""
    extractor = UltraBERTEntityExtractor()
    for head in ["ner_family", "ner_general", "temporal", "bert_ner"]:
        result = extractor._map_entity({"text": garbage_word, "label": "PERSON"}, head)
        assert result is None, f"'{garbage_word}' from {head} should be filtered"
```

---

## Issue M10.3: Edges Always Use RELATED_TO Instead of ULTRABERT Types

**Priority**: 🟠 HIGH
**Status**: ✅ DONE

### Problem

`ULTRABERT_TO_TYPE` mapping exists with rich relationship types:

```python
ULTRABERT_TO_TYPE = {
    "parent_of": "FAMILY",
    "spouse_of": "FAMILY",
    "friend_of": "FRIEND",
    ...
}
```

But `_discover_relationships()` always creates edges with `relation_type="RELATED_TO"`.

### Root Cause Analysis (2026-01-15)

**Dual Flow Architecture:**

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     R4 Phase Data Flow                                   │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  envelope.events                                                         │
│       │                                                                  │
│       ├──► _extract_entities() ──► entities_json ──► ExtractedEntity    │
│       │        │                                                         │
│       │        └─ event_entity_map: Dict[event_id, List[ExtractedEntity]]│
│       │                     │                                            │
│       │                     ▼                                            │
│       │    _discover_relationships() ──► KGUpdate(relation_type="RELATED_TO")
│       │                                    ❌ NO ACCESS TO RELATIONS     │
│       │                                                                  │
│       └──► _extract_social_relationships() ──► extracted_relations_json │
│                     │                                                    │
│                     └─► ["parent_of", "spouse_of"] ──► ULTRABERT_TO_TYPE │
│                               │                                          │
│                               ▼                                          │
│                     SocialRelationship(relationship_type="FAMILY")       │
│                               ✅ USES ULTRABERT TYPES                    │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

**The Gap:**

- `extracted_relations_json` contains `["parent_of", "spouse_of", ...]`
- This is ONLY used in `_extract_social_relationships()` for st_social
- `_discover_relationships()` has NO access to these relations
- Result: All KG edges are generic `RELATED_TO`

### Current Code (Lines 1448-1465)

```python
# GAP-001 M9: Check if edge already exists
if pair_key in existing_edges:
    updates.append(
        KGUpdate(
            update_type=KGUpdateType.UPDATE_EDGE,
            relation_type=existing.get("relation_type", "RELATED_TO"),  # ← preserves old type
            ...
        )
    )
else:
    # CREATE new edge
    updates.append(
        KGUpdate(
            update_type=KGUpdateType.CREATE_EDGE,
            relation_type="RELATED_TO",  # ← HARDCODED!
            ...
        )
    )
```

### Impact

- All KG edges are generic RELATED_TO (except CAUSES from Granger)
- Relationship semantics lost (FAMILY, FRIEND, COLLEAGUE not preserved)
- Graph traversal can't filter by relationship type
- P01 Recall can't prioritize family vs acquaintance relationships

### Files

- [x] `k0/pipelines/p03/phases/r4_kg_consolidator.py` - EXPLORED

### Solution

**Approach: Build event→relations map and pass to `_discover_relationships()`**

1. During `_extract_entities()`, also parse `extracted_relations_json`
2. Build `event_relations_map: Dict[str, List[str]]` (event_id → relation types)
3. In `_discover_relationships()`:
   - For each co-occurring entity pair in an event
   - Look up the event's relation types
   - Use `ULTRABERT_TO_TYPE` to map to FAMILY/FRIEND/COLLEAGUE
   - If multiple events have different types, use priority (FAMILY > FRIEND > COLLEAGUE > ACQUAINTANCE)

```python
# In _extract_entities() - add relation extraction:
event_relations_map: Dict[str, List[str]] = {}

for event in events:
    # ... existing entity extraction ...

    # Extract UltraBERT relations for edge type inference
    extracted_relations_json = getattr(event, "extracted_relations_json", None)
    try:
        relations = json.loads(extracted_relations_json) if extracted_relations_json else []
        event_relations_map[event.event_id] = relations
    except (json.JSONDecodeError, TypeError):
        event_relations_map[event.event_id] = []

return all_entities, event_entity_map, event_relations_map


# In _discover_relationships() - use relations for edge type:
def _infer_edge_type_from_relations(
    self,
    event_ids: List[str],
    event_relations_map: Dict[str, List[str]],
) -> str:
    """Infer edge type from UltraBERT relations across events."""
    # Priority: FAMILY > FRIEND > COLLEAGUE > ACQUAINTANCE > RELATED_TO
    TYPE_PRIORITY = {"FAMILY": 4, "FRIEND": 3, "COLLEAGUE": 2, "ACQUAINTANCE": 1}

    best_type = "RELATED_TO"
    best_priority = 0

    for event_id in event_ids:
        for rel in event_relations_map.get(event_id, []):
            mapped_type = self.ULTRABERT_TO_TYPE.get(rel)
            if mapped_type and TYPE_PRIORITY.get(mapped_type, 0) > best_priority:
                best_type = mapped_type
                best_priority = TYPE_PRIORITY[mapped_type]

    return best_type
```

### Implementation (2026-01-15)

**Changes Made:**

1. **Updated `_extract_entities()` signature** (lines 722-751):
   - Returns 3-tuple: `(all_entities, event_entity_map, event_relations_map)`
   - Added extraction of `extracted_relations_json` per event
   - Filters out "no_relation" type

2. **Updated caller in `run()`** (lines 582-606):
   - Captures `event_relations_map` third return value
   - Passes to `_discover_relationships()`

3. **Updated `_discover_relationships()` signature** (lines 1308-1340):
   - Added `event_relations_map: Dict[str, List[str]]` parameter
   - Tracks `event_ids` per co-occurrence pair

4. **Added `_infer_edge_type_from_relations()` helper** (lines 1705-1757):
   - TYPE_PRIORITY: FAMILY(4) > FRIEND(3) > COLLEAGUE(2) > ACQUAINTANCE(1)
   - Returns highest priority type from contributing events

5. **Updated edge creation** (lines 1489-1503):
   - New edges use `inferred_type` instead of hardcoded "RELATED_TO"
   - Existing edges preserve their relation_type

### Tests (12 tests, all passing)

```
TestEdgeTypeInference::test_infer_family_type_from_parent_of ✓
TestEdgeTypeInference::test_infer_family_type_from_spouse_of ✓
TestEdgeTypeInference::test_infer_friend_type ✓
TestEdgeTypeInference::test_infer_colleague_type ✓
TestEdgeTypeInference::test_priority_family_over_friend ✓
TestEdgeTypeInference::test_priority_friend_over_colleague ✓
TestEdgeTypeInference::test_multiple_relations_in_single_event ✓
TestEdgeTypeInference::test_empty_event_relations_returns_related_to ✓
TestEdgeTypeInference::test_empty_event_ids_returns_related_to ✓
TestEdgeTypeInference::test_unknown_relation_type_ignored ✓
TestEdgeTypeInference::test_mixed_known_unknown_relations ✓
TestEdgeTypeInference::test_all_family_relations_map_correctly ✓
```

---

## Issue M10.4: min_co_occurrence=1 Allows Low-Quality Edges

**Priority**: 🟡 MEDIUM
**Status**: ✅ DONE

### Problem

Config default is `min_co_occurrence=1`, allowing single-occurrence edges.

Test expects `min_co_occurrence=2`:

```python
# test_r4_kg_consolidator.py:104
assert config.min_co_occurrence == 2  # FAILS - actual is 1
```

### Impact

- Noise edges from single co-occurrences
- Lower graph quality
- More edges to process, slower performance

### Files to Explore

- [ ] `k0/pipelines/p03/phases/r4_kg_consolidator.py` - R4Config

### Solution

Changed `min_co_occurrence` default from 1 to 2 in R4Config:

```python
# BEFORE:
min_co_occurrence: int = 1  # Lower threshold for initial relationship discovery

# AFTER:
min_co_occurrence: int = 2  # M10.4: Require 2+ co-occurrences for quality edges
```

**Rationale:**

- Single co-occurrences can be noise (two entities appearing together once by chance)
- Two or more co-occurrences provide stronger signal for meaningful relationships
- Reduces edge noise and improves graph quality

### Implementation (2026-01-15)

**File Changed:** `k0/pipelines/p03/phases/r4_kg_consolidator.py` line 113

### Tests

Existing test now passes:

```
TestR4Config::test_default_config_values ✓
```

---

## Issue M10.5: No Entity Confidence Threshold

**Priority**: 🟡 MEDIUM
**Status**: ✅ DONE

### Problem

Low-confidence entities are not filtered during extraction. The current flow:

1. UltraBERT NER produces entities with labels
2. `LABEL_MAPPING` assigns priority scores (0.60-0.95) based on label type
3. ALL entities pass through to clustering regardless of priority
4. Only at clustering stage does confidence band routing occur

**Current Threshold Behavior:**

```python
# confidence_router.py:52-53
P03_CONFIDENCE_THRESHOLD_AUTO: float = 0.85  # High: auto-accept
P03_CONFIDENCE_THRESHOLD_FLAG: float = 0.60  # Medium: accept but flag

# ConfidenceBand routing in _resolve_entities():
# - AUTO (≥0.85): Accepted, no review
# - FLAG (0.60-0.85): Accepted but flagged
# - GAP (<0.60): Emitted to P06, not added to KG
```

**But the problem is:**

The `priority` from `LABEL_MAPPING` is NOT true entity confidence:

- KINSHIP always gets 0.95 regardless of context
- PERSON always gets 0.85 regardless of context
- MISC always gets 0.60 regardless of context

This means a garbage MISC entity like "the" gets 0.60 and enters FLAG band.

### Current Priority Scores (from LABEL_MAPPING)

| Label | KGEntityType | Priority |
|-------|--------------|----------|
| KINSHIP | FAMILY_MEMBER | 0.95 |
| FAMILY_EVENT | EVENT | 0.90 |
| HOME_LOC | LOCATION | 0.90 |
| DATE_REL | TEMPORAL | 0.90 |
| PERSON/PER | PERSON | 0.85 |
| ORG | ORGANIZATION | 0.80 |
| LOC/GPE | LOCATION | 0.80 |
| EVENT | EVENT | 0.75 |
| FAC | LOCATION | 0.75 |
| PRODUCT | OBJECT | 0.70 |
| WORK_OF_ART | CONCEPT | 0.65 |
| NORP | CONCEPT | 0.65 |
| MISC | CONCEPT | 0.60 |

### Impact

- MISC entities (priority 0.60) enter FLAG band, not GAP band
- Garbage entities like "the", "our", "met" can have 0.60+ priority
- Even TRUSTED labels can have bad entities (NER model mistakes)
- Universal stopword filter (M10.2) helps but doesn't catch all garbage

### Files to Explore

- [x] `k0/modules/consolidation/algorithms/entity_extractor.py` - LABEL_MAPPING
- [x] `k0/modules/consolidation/algorithms/confidence_router.py` - thresholds
- [x] `k0/pipelines/p03/phases/r4_kg_consolidator.py` - _resolve_entities()

### Analysis: Should We Add Entity-Level Confidence Threshold?

**Option A: Pre-Clustering Entity Filter**
Add `min_entity_priority` config to filter entities before clustering:

```python
# In _extract_entities():
if entity.priority < self.config.min_entity_priority:
    continue  # Skip low-priority entities
```

**Option B: Adjust Priority Thresholds**
Raise MISC/NORP/WORK_OF_ART priorities to 0.70+ so they hit FLAG band correctly.

**Option C: Use NER Confidence Scores**
If UltraBERT provides per-entity confidence scores (not just label), use those.

**Recommendation**: Option A is cleanest. Add `min_entity_priority: float = 0.65` to R4Config.

### Solution

Implemented Option A - added `min_entity_priority` config to filter low-priority entities:

```python
# R4Config (line 128):
min_entity_priority: float = 0.65  # M10.5: Filter low-priority entities (MISC=0.60)

# In _extract_entities() after entity creation:
if priority < self.config.min_entity_priority:
    logger.debug(
        f"R4: Skipping low-priority entity: {text!r} "
        f"({label}, priority={priority:.2f} < {self.config.min_entity_priority})"
    )
    continue
```

**Effect**: MISC entities (0.60) are now filtered out. NORP/WORK_OF_ART (0.65) pass through.

### Implementation (2026-01-15)

**File Changed:** `k0/pipelines/p03/phases/r4_kg_consolidator.py`

- Added `min_entity_priority` to R4Config docstring and fields
- Added priority check in `_extract_entities()` after entity creation

### Tests (2 tests, all passing)

```
TestEntityPriorityThreshold::test_min_entity_priority_default_value ✓
TestEntityPriorityThreshold::test_min_entity_priority_custom_value ✓
```

---

## Issue M10.6: Entity Deduplication Incomplete

**Priority**: 🟡 MEDIUM
**Status**: ✅ DONE

### Problem

Entity deduplication happens at TWO levels with different strategies:

**Level 1: Entity Extractor (`_deduplicate_entities`)**

- Key: `normalized_text` only (case-sensitive!)
- Same text → keep highest priority
- Different cases NOT deduplicated: "Mom" vs "mom" → 2 entities

**Level 2: R4 Clustering (`_build_entity_clusters`)**

- Key: `{kg_type}:{normalized_text.lower()}`
- Groups by type + lowercase name
- Creates single cluster for "Mom" and "mom"

**The Gap:**
While Level 2 handles case normalization, there are issues:

1. **Cluster ID includes raw text**: `cluster_PERSON_panda` vs `cluster_PERSON_Panda`
   - Actually NO - cluster_id is built from key which uses `.lower()`

2. **First entity wins for canonical_name**:

   ```python
   first_entity = entity_events[0][0]
   canonical_name = first_entity.normalized_text  # Whatever came first
   ```

   - If "panda" event processed before "Panda" event, canonical = "panda"
   - If "Panda" event processed first, canonical = "Panda"
   - Non-deterministic canonical names

3. **No preference for proper case**:
   - "John" should beat "john" as canonical name
   - Currently first-in wins, not proper-case wins

### Current Deduplication Code

```python
# entity_extractor.py:1099-1111
def _deduplicate_entities(self, entities):
    seen: dict[str, ExtractedEntity] = {}
    for entity in entities:
        key = entity.normalized_text  # NOT lowercased!
        if key not in seen:
            seen[key] = entity
        elif entity.priority > seen[key].priority:
            seen[key] = entity
    return list(seen.values())

# r4_kg_consolidator.py:1119-1123
for entity in entities:
    key = f"{entity.kg_type.value}:{entity.normalized_text.lower()}"  # LOWERCASED
    if key not in entity_groups:
        entity_groups[key] = []
    entity_groups[key].append((entity, event.event_id))
```

### Impact

- Non-deterministic canonical names (depends on event processing order)
- "mom" might be canonical when "Mom" is more proper
- Minor issue since `.lower()` handles matching

### Files

- [x] `k0/modules/consolidation/algorithms/entity_extractor.py` - _deduplicate_entities
- [x] `k0/pipelines/p03/phases/r4_kg_consolidator.py` - _build_entity_clusters

### Analysis: Is This Actually a Problem?

**Actually, this is MOSTLY working correctly:**

- Clustering uses `.lower()` so "Mom" and "mom" are in same cluster
- Cluster ID is deterministic: `cluster_FAMILY_MEMBER_mom`
- Issue is only canonical_name can be inconsistent

**Severity: LOW**

- Edge creation uses cluster_id (deterministic)
- KG entity lookup uses cluster_id (deterministic)
- Only display name (canonical_name) might vary

### Solution

Added `_select_canonical_name()` helper method preferring:

1. Most common variant (frequency)
2. Proper case (first letter uppercase)
3. Longest variant (for abbreviations)

```python
def _select_canonical_name(self, mentions: List[str]) -> str:
    """Select best canonical name from entity mentions."""
    if not mentions:
        return ""
    if len(mentions) == 1:
        return mentions[0]

    from collections import Counter
    variant_counts = Counter(mentions)

    def score(name: str) -> tuple:
        count = variant_counts.get(name, 0)
        is_proper = name[0].isupper() if name else False
        length = len(name)
        return (count, is_proper, length)

    return max(mentions, key=score)
```

### Implementation (2026-01-15)

**File Changed:** `k0/pipelines/p03/phases/r4_kg_consolidator.py`

- Added `_select_canonical_name()` helper method
- Updated `_build_entity_clusters()` to use the new method

### Tests (7 tests, all passing)

```
TestCanonicalNameSelection::test_select_single_mention ✓
TestCanonicalNameSelection::test_select_empty_mentions ✓
TestCanonicalNameSelection::test_select_most_common_variant ✓
TestCanonicalNameSelection::test_select_proper_case_over_lowercase ✓
TestCanonicalNameSelection::test_select_longer_variant ✓
TestCanonicalNameSelection::test_frequency_beats_case ✓
TestCanonicalNameSelection::test_real_world_scenario ✓
```

---

## Issue M10.7: No Temporal Relationship Types

**Priority**: 🔵 LOW
**Status**: ✅ DONE

### Problem

No temporal relationship types like:

- `FOLLOWS` - "honeymoon" FOLLOWS "wedding"
- `PRECEDES` - "engagement" PRECEDES "wedding"

Only `CAUSES` is created via Granger causality.

### Current Architecture

**Granger Causality Flow:**

```
_infer_causal_relationships()
    │
    ├─► observations >= granger_min_observations (5)
    │
    ├─► compute_temporal_precedence()
    │       ├─► a_before_b: count of A→B occurrences
    │       ├─► b_before_a: count of B→A occurrences
    │       └─► precedence_ratio = a_before_b / total
    │
    └─► if precedence_ratio >= threshold (0.75)
            └─► CausalEdge(relation_type="CAUSES")  ← ONLY CAUSES
```

**Current Relation Types:**

| Source | Relation Types |
|--------|----------------|
| Co-occurrence (Hebbian) | FAMILY, FRIEND, COLLEAGUE, ACQUAINTANCE, RELATED_TO |
| Causal inference (Granger) | CAUSES |
| Missing | FOLLOWS, PRECEDES |

### The Gap

The Granger causality logic has 3 outcomes:

1. `precedence_ratio >= 0.75` → A CAUSES B
2. `precedence_ratio <= 0.25` → B CAUSES A
3. `0.25 < ratio < 0.75` → No edge created ← **THIS IS THE GAP**

The middle zone (significant precedence but not causal) should create FOLLOWS/PRECEDES edges.

### Impact

- Cannot represent temporal sequences
- Pattern detection limited
- Prospective memory weaker
- "wedding" → "honeymoon" sequence lost if not strongly causal

### Files

- [x] `k0/pipelines/p03/phases/r4_kg_consolidator.py` - _infer_causal_relationships
- [x] `k0/modules/consolidation/algorithms/granger_causality.py` - CausalEdge, thresholds

### Analysis: Solution Options

**Option A: Add FOLLOWS/PRECEDES in R4 (Recommended)**
Modify `_infer_causal_relationships()` to create temporal edges for medium precedence:

```python
# Current thresholds:
# CAUSES: ratio >= 0.75 (strong causality)

# Proposed new thresholds:
# CAUSES:   ratio >= 0.75 (strong causality)
# FOLLOWS:  0.60 <= ratio < 0.75 (moderate precedence)
# PRECEDES: 0.25 < ratio <= 0.40 (reverse moderate precedence)
# NOTHING:  0.40 < ratio < 0.60 (no clear pattern)
```

**Option B: Add in Granger Module**
Extend `CausalEdge` to support FOLLOWS/PRECEDES relation_type.

**Option C: Separate Edge Type**
Create `TemporalEdge` dataclass distinct from `CausalEdge`.

**Recommendation:** Option A - Extend existing `_infer_causal_relationships()` with new thresholds. Use same `CausalEdge` dataclass with different `relation_type`.

### Solution Design

Add config parameters and extend causal inference:

```python
# R4Config additions:
temporal_follows_threshold: float = 0.60  # M10.7: FOLLOWS if ratio >= 0.60
temporal_enable_follows_edges: bool = True  # M10.7: Enable FOLLOWS/PRECEDES

# In _infer_causal_relationships():
if simulated_ratio >= threshold:
    # Strong causality
    relation_type = "CAUSES"
elif self.config.temporal_enable_follows_edges:
    if simulated_ratio >= self.config.temporal_follows_threshold:
        # Moderate precedence (A usually before B)
        relation_type = "FOLLOWS"
    elif simulated_ratio <= (1 - self.config.temporal_follows_threshold):
        # Reverse moderate precedence (B usually before A)
        relation_type = "PRECEDES"
    else:
        relation_type = None  # No clear pattern

if relation_type:
    causal_edge = CausalEdge(
        source_id=source_id,
        target_id=target_id,
        relation_type=relation_type,
        ...
    )
```

### Tests

```
TestTemporalEdgeTypes::test_config_default_enable_temporal_edges ✓
TestTemporalEdgeTypes::test_config_default_temporal_follows_threshold ✓
TestTemporalEdgeTypes::test_config_custom_temporal_settings ✓
TestTemporalEdgeTypes::test_temporal_precedes_threshold_symmetric ✓
TestTemporalEdgeTypes::test_temporal_threshold_bounds_valid ✓
TestTemporalEdgeTypes::test_temporal_threshold_custom_follows ✓
```

### Implementation (2026-01-15)

**File Changed:** `k0/pipelines/p03/phases/r4_kg_consolidator.py`

1. Added config parameters to R4Config:
   - `enable_temporal_edges: bool = True`
   - `temporal_follows_threshold: float = 0.60`

2. Modified `_infer_causal_relationships()` to create FOLLOWS/PRECEDES edges:

```python
# Determine relation type based on precedence ratio
relation_type: str | None = None

if simulated_ratio >= threshold:
    relation_type = "CAUSES"
elif self.config.enable_temporal_edges:
    follows_thresh = self.config.temporal_follows_threshold
    precedes_thresh = 1.0 - follows_thresh  # Symmetric: 0.40 if follows=0.60

    if simulated_ratio >= follows_thresh:
        relation_type = "FOLLOWS"
    elif simulated_ratio <= precedes_thresh:
        relation_type = "PRECEDES"

if relation_type is not None:
    causal_edge = CausalEdge(relation_type=relation_type, ...)
```

**Effect:**

- CAUSES: ratio >= 0.75 (strong causality)
- FOLLOWS: 0.60 <= ratio < 0.75 (moderate A→B precedence)
- PRECEDES: ratio <= 0.40 (moderate B→A precedence)
- No edge: 0.40 < ratio < 0.60 (ambiguous)

---

## Issue M10.8: Semantic Pattern Naming Not Descriptive

**Priority**: 🔵 LOW
**Status**: ✅ DONE

### Problem

Pattern names are generic IDs, not descriptive names generated from clustered event content.

### Impact

- Patterns not human-readable
- Debugging harder
- User-facing insights less meaningful

### Files Explored

- [x] `k0/modules/consolidation/staging/truth_write_assembler.py` - R4/R5 pattern assembly
- [x] `k0/modules/consolidation/staging/intent_signal_assembler.py` - Intent signal patterns
- [x] `k0/modules/consolidation/algorithms/bgt_sm.py` - InsightTextGenerator

### Analysis

**Current Pattern Naming by Source:**

| Pattern Source | Pattern Type | Current Naming | Quality |
|----------------|--------------|----------------|---------|
| R5 BGT-SM Insights | INSIGHT | `InsightTextGenerator` templates | ✅ Good |
| R5 Lessons | LESSON | `lesson_description` text | ✅ Good |
| R5 Emotional | EMOTIONAL_TREND | `{emotion_label} emotional pattern` | ✅ Good |
| R4 Entity Promotion | THEME/ROUTINE | Truncated event text (200 chars) | ⚠️ Fixed |

**The Problem:**

`truth_write_assembler.py:_create_sem_insert()` used raw event text:

```python
# Before M10.8:
pattern_name = getattr(state, "text", None) or f"Pattern from {event_id}"
```

This produced names like "Had Thai dinner with Mom at Thai Palace tonight it was really good..." - long rambling text instead of semantic descriptions.

### Solution (2026-01-15)

Added `_generate_pattern_name()` helper that builds descriptive names from event metadata:

**File Changed:** `k0/modules/consolidation/staging/truth_write_assembler.py`

```python
def _generate_pattern_name(state: P03EventState, max_length: int = 200) -> str:
    """
    Generate a descriptive pattern name from event state.

    Priority order:
    1. Activity type + key entities (e.g., "Meal with Mom, Thai Palace at Downtown")
    2. Activity type + location (e.g., "Work at Office")
    3. Activity type + first sentence
    4. Just entities ("Memory about Grandma, beach")
    5. Fallback to truncated text
    """
```

**Updated `_create_sem_insert()`:**

```python
# M10.8: Generate descriptive pattern name from NER entities and activity type
pattern_name = _generate_pattern_name(state, max_length=200)
```

**Example Transformations:**

| Before (raw text) | After (semantic name) |
|-------------------|----------------------|
| "Had Thai dinner with Mom..." | "Meal with Mom, Thai Palace at Downtown" |
| "Great meeting at work today" | "Work at Office" |
| "Saw Grandma at the beach" | "Memory about Grandma, beach" |

### Tests (8 tests, all passing)

```
TestPatternNameGeneration::test_pattern_name_from_activity_and_entities ✓
TestPatternNameGeneration::test_pattern_name_from_activity_and_location ✓
TestPatternNameGeneration::test_pattern_name_from_entities_only ✓
TestPatternNameGeneration::test_pattern_name_fallback_to_text ✓
TestPatternNameGeneration::test_pattern_name_fallback_to_event_id ✓
TestPatternNameGeneration::test_pattern_name_max_length ✓
TestPatternNameGeneration::test_pattern_name_handles_invalid_json ✓
TestPatternNameGeneration::test_pattern_name_limits_entities ✓
```

---

## Exploration Log

### 2026-01-15 - Initial Analysis

**Findings from codebase exploration:**

1. `_infer_causal_relationships()` at line 1500 skips all UPDATE_EDGE types
2. ULTRABERT_TO_TYPE mapping exists but not used in `_discover_relationships()`
3. Entity extraction has no stopword filter visible
4. Test failure confirms min_co_occurrence mismatch (1 vs expected 2)

**Next Steps:**

- Explore each file in detail before implementing fixes
- Start with M10.1 (critical bug blocking causal edge generation)

---

## Implementation Order

1. **M10.1** - Critical: Unblocks all causal edge generation ✅
2. **M10.2** - High: Filter noise entities ✅
3. **M10.3** - High: Uses existing ULTRABERT types ✅
4. **M10.4** - Medium: Raise threshold ✅
5. **M10.5** - Medium: Confidence filter ✅
6. **M10.6** - Medium: Better dedup ✅
7. **M10.7** - Low: Temporal types ✅
8. **M10.8** - Low: Pattern naming ✅
