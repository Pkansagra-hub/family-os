# Memory Layer Gaps Fix Plan

**Document Status**: Planning
**Priority**: High
**Created**: 2026-01-16
**Issue Tracking**: Memory layer columns empty despite infrastructure existing

---

## Executive Summary

After comprehensive code scan of the P03 consolidation pipeline, multiple memory layers have empty columns despite text generators, parsers, and infrastructure being fully implemented. This plan addresses **4 critical gaps** where data is being lost between pipeline phases and database writes.

**Impact:**

- **st_epi**: 451 episodes have NULL summaries (human-readable context lost)
- **st_prospective**: 377 reminders have NULL target dates (unusable for scheduling)
- **st_procedural**: 0 routines detected (habit tracking non-functional)
- Multiple layers missing entity linking data

---

## Quick Reference Table

| GAP ID  | Issue                          | Status           | Priority    | Effort     | Ready to Fix?        |
|---------|--------------------------------|------------------|-------------|------------|----------------------|
| GAP-001 | st_epi columns not inserted    | ✅ Analyzed      | 🔴 Critical | 2.5h       | **YES**              |
| GAP-002 | target_date parsing disabled   | ✅ Analyzed      | 🔴 Critical | 2.5h       | **YES**              |
| GAP-003 | No routine detection           | ✅ Analyzed      | 🟡 High     | 2-3 weeks  | NO (requires design) |
| GAP-004 | Entity aliases missing         | ✅ Analyzed      | 🟡 High     | 2.5-3.5 wk | NO (requires NLP)    |
| GAP-005 | Subtype classification         | ✅ Analyzed      | 🟢 Low      | 1-2 weeks  | NO (enhancement)     |
| GAP-006 | actor_id NULL in st_sem        | ✅ By design     | ℹ️ Info     | 30 min     | N/A (documentation)  |
| GAP-007 | R4 edge sparsity (8 edges!)    | ✅ Analyzed      | 🔴 Critical | 4.5 weeks  | NO (requires design) |

**Total Ready for Implementation**: 2 issues, ~5 hours effort
**Total Design Required**: 4 issues, ~12-14 weeks effort (can be parallelized)

---

## Issue Categorization

### 🔴 Critical (Data Loss Bugs)

- **GAP-001**: st_epi columns not inserted despite being in record_data
- **GAP-002**: target_date parsing disabled with TODO comment

### 🟡 High (Feature Incomplete)

- **GAP-003**: Routine detection never creates st_procedural records
- **GAP-004**: Entity aliases not populated (causes duplicate entities)

### 🟢 Medium (Enhancement)

- **GAP-005**: Fine-grained *_subtype classification not implemented
- **GAP-006**: st_sem.actor_id intentionally NULL (by design)

---

## SKELETON: Issue Breakdown

### GAP-001: st_epi Missing Column Inserts 🔴

**Status**: ✅ Code scanned - CONFIRMED BUG
**Location**: `k0/modules/consolidation/truth_writer/layers/episodic.py:213-239`
**Severity**: Critical (data loss)
**Impact**: 451 episodes have NULL: episode_summary, episode_type, primary_location, participants_json

#### GAP-001.1: Current State - INSERT Statement

**File**: `k0/modules/consolidation/truth_writer/layers/episodic.py#L213-239`

```python
await uow.connection.execute(
    """
    INSERT INTO st_epi (
        episode_id, tenant_id, space_id, cluster_id,
        source_events_json, source_event_count, start_time_utc, end_time_utc,
        confidence_score, observation_count,
        created_at, updated_at, valid_from, version,
        archival_status,
        source_texts_json, embedding_text, embedding_vector, embedding_model
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $11, $11, 1,
              'ACTIVE', $12, $13, $14, $15)
    ON CONFLICT (episode_id) DO NOTHING
    """,
    # ... 15 values passed
)
```

**Missing Columns in INSERT:**

- ❌ `episode_summary` - Human-readable episode description
- ❌ `episode_type` - Activity classification (GENERAL, WORK, SOCIAL, etc.)
- ❌ `primary_location` - Where episode occurred
- ❌ `participants_json` - Who was involved
- ❌ `participant_count` - Number of participants
- ❌ `embedding_id` - UltraBERT embedding reference

#### GAP-001.2: Data DOES Exist in record_data

**File**: `k0/modules/consolidation/staging/truth_write_assembler.py#L320-342`

```python
return {
    "episode_id": cluster.cluster_id,
    "tenant_id": self.tenant_id,
    "space_id": self.space_id,
    "version": 1,
    "episode_summary": cluster.summary or cluster.title or "Untitled episode",  # ✅ EXISTS
    "episode_type": cluster.activity_type or "GENERAL",  # ✅ EXISTS
    "start_time_utc": cluster.temporal_start,
    "end_time_utc": cluster.temporal_end,
    "primary_location": cluster.location_hint,  # ✅ EXISTS
    "participants_json": cluster.participants_json,  # ✅ EXISTS
    "participant_count": len(json.loads(cluster.participants_json or "[]")),  # ✅ EXISTS
    "embedding_id": embedding_id,  # ✅ EXISTS
    # ... more fields
}
```

#### GAP-001.3: Root Cause Analysis

**The Bug:**

1. `TruthWriteAssembler._build_epi_record_data()` creates complete record_data dict
2. Data includes episode_summary, episode_type, primary_location, etc.
3. `EpisodicLayerWriter._insert()` receives this data via `write.record_data`
4. **BUT** the INSERT SQL statement only extracts 15 values
5. The missing columns are **silently ignored** despite being in record_data

**Why This Happened:**

- Likely copy-paste from early prototype with minimal columns
- GAP-001 columns added to schema and record_data builder
- INSERT statement never updated to match
- No validation that record_data keys match INSERT columns

**Evidence from Database:**

```sql
SELECT episode_summary, episode_type, primary_location FROM st_epi LIMIT 1;
-- Result: NULL, NULL, NULL
```

#### GAP-001.4: Fix Strategy

**Step 1**: Add missing columns to INSERT statement
**Step 2**: Add corresponding positional parameters
**Step 3**: Pass values from record_data
**Step 4**: Add integration test to verify all columns populated

**Implementation:**

```python
await uow.connection.execute(
    """
    INSERT INTO st_epi (
        episode_id, tenant_id, space_id, cluster_id,
        source_events_json, source_event_count,
        start_time_utc, end_time_utc,
        confidence_score, observation_count,
        -- ADD THESE COLUMNS:
        episode_summary, episode_type,
        primary_location, location_type,
        participants_json, participant_count,
        embedding_id,
        -- END NEW COLUMNS
        created_at, updated_at, valid_from, version,
        archival_status,
        source_texts_json, embedding_text, embedding_vector, embedding_model
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
        $11, $12, $13, $14, $15, $16, $17,  -- NEW PARAMS
        $18, $18, $18, 1, 'ACTIVE',
        $19, $20, $21, $22
    )
    ON CONFLICT (episode_id) DO NOTHING
    """,
    data["episode_id"],
    data["tenant_id"],
    data["space_id"],
    data.get("cluster_id"),
    source_events_json_str,
    len(source_event_ids),
    data.get("start_time_utc") or data.get("started_at", now),
    data.get("end_time_utc") or data.get("ended_at", now),
    data.get("confidence_score") or data.get("confidence", 1.0),
    data.get("observation_count", 1),
    # NEW VALUES:
    data.get("episode_summary"),
    data.get("episode_type"),
    data.get("primary_location"),
    data.get("location_type"),
    data.get("participants_json", "[]"),
    data.get("participant_count", 0),
    data.get("embedding_id"),
    # END NEW VALUES
    data.get("created_at", now),
    # GAP-001 vectors:
    tv_result.source_texts_json,
    tv_result.embedding_text,
    tv_result.embedding_vector,
    tv_result.embedding_model,
)
```

#### GAP-001.5: Files to Modify

1. **PRIMARY**: `k0/modules/consolidation/truth_writer/layers/episodic.py`
   - Function: `_insert()` at line ~213
   - Add 7 columns to INSERT statement
   - Add 7 positional parameters

2. **VALIDATION**: Add integration test
   - File: `tests/k0/modules/consolidation/truth_writer/test_episodic.py`
   - Test: Verify all record_data fields make it to database

#### GAP-001.6: Test Plan

**Unit Test**: Verify INSERT SQL has all columns

```python
def test_insert_includes_all_record_data_columns():
    """Verify INSERT statement includes all fields from record_data."""
    # Mock UnitOfWork
    # Create sample record_data with all fields
    # Call _insert()
    # Verify SQL contains: episode_summary, episode_type, etc.
```

**Integration Test**: End-to-end verification

```python
@pytest.mark.asyncio
async def test_e2e_episode_columns_populated():
    """Verify episode fields propagate to database."""
    # Create EpisodeCluster with summary, location, participants
    # Run through TruthWriteAssembler → EpisodicLayerWriter
    # Query st_epi
    # Assert episode_summary IS NOT NULL
    # Assert episode_type IS NOT NULL
    # Assert primary_location IS NOT NULL
```

**Validation on Production Data**:

```sql
-- Before fix: All NULL
SELECT COUNT(*) FROM st_epi WHERE episode_summary IS NULL;
-- Result: 451

-- After fix + rerun: All populated
SELECT COUNT(*) FROM st_epi WHERE episode_summary IS NOT NULL;
-- Expected: 451
```

#### GAP-001.7: Estimated Effort

- **Coding**: 30 minutes (straightforward SQL update)
- **Testing**: 1 hour (write integration test)
- **Validation**: 1 hour (re-run consolidation on subset)
- **Total**: 2.5 hours

---

### GAP-002: target_date Parsing Disabled 🔴

**Status**: ✅ Code scanned - CONFIRMED DISABLED
**Location**: `k0/modules/consolidation/algorithms/intent_signal_detector.py:408-432`
**Severity**: Critical (feature non-functional)
**Impact**: 377 reminders have NULL target_date (scheduling impossible)

#### GAP-002.1: Current State - Parsing Disabled

**File**: `k0/modules/consolidation/algorithms/intent_signal_detector.py#L408-432`

```python
def _parse_temporal_date(
    self,
    temporal_json: str,
) -> Optional[int]:
    """
    Parse temporal_json to extract target date.

    UltraBERT temporal head produces:
    {"entities": [{"text": "tomorrow at 3pm", "label": "TIME"}]}

    This returns the raw temporal text for now.
    Phase 6 TemporalParser will convert to Unix ms.

    Args:
        temporal_json: JSON string from st_hipp_events.temporal_json

    Returns:
        Unix ms timestamp or None if no parseable date

    Note:
        Full temporal parsing is deferred to Phase 6 TemporalParser.
        This method returns None until that module is implemented.
    """
    if not temporal_json or temporal_json == "[]":
        return None

    try:
        data = json.loads(temporal_json)
    except json.JSONDecodeError:
        return None

    # UltraBERT format: {"entities": [...]} or [...]
    entities = data.get("entities", []) if isinstance(data, dict) else data

    if not entities:
        return None

    # For now, return None - Phase 6 will implement actual parsing
    # We still create the ReminderSignal for routing purposes
    return None  # ❌ ALWAYS RETURNS NONE
```

#### GAP-002.2: TemporalParser EXISTS and is Fully Tested

**File**: `k0/modules/consolidation/algorithms/temporal_parser.py`

```python
class TemporalParser:
    """
    Parses temporal expressions to Unix ms timestamps.

    Supports:
        - Relative dates: tomorrow, next week, next Monday
        - Relative times: in an hour, in 30 minutes
        - Absolute times: 3pm, 15:00, 3:30 PM
        - Combined: tomorrow at 3pm, next Monday at 10am
    """

    def parse_temporal_json(
        self,
        temporal_json: str,
        reference_time: Optional[int] = None,
    ) -> Optional[int]:
        """Parse temporal_json and return target timestamp."""
        # ✅ FULLY IMPLEMENTED
        # ✅ Returns Unix ms timestamp
        # ✅ Handles all UltraBERT temporal formats
```

**Test Coverage**: `tests/k0/modules/consolidation/algorithms/test_temporal_parser.py`

- ✅ 20+ test cases
- ✅ Tests relative dates (tomorrow, next Monday, etc.)
- ✅ Tests relative times (in 2 hours, in 30 minutes)
- ✅ Tests absolute times (3pm, 15:00)
- ✅ Tests combined expressions (tomorrow at 3pm)

#### GAP-002.3: Root Cause Analysis

**The Bug:**

1. TemporalParser was implemented in "Phase 6" (per plan comments)
2. IntentSignalDetector has TODO comment: "Phase 6 TemporalParser will implement"
3. **BUT** Phase 6 is complete - TemporalParser exists and is tested
4. Nobody wired TemporalParser.parse_temporal_json() call
5. Method still returns `None` with original TODO comment

**Evidence from Database:**

```sql
SELECT COUNT(*) FROM st_prospective WHERE target_date IS NOT NULL;
-- Result: 0

SELECT intention_description FROM st_prospective
WHERE intention_type = 'REMINDER' LIMIT 5;
-- Results show temporal expressions like "tomorrow", "next Monday"
-- But target_date is NULL for all
```

**Why This Happened:**

- Work was tracked in separate milestones
- TemporalParser implemented as standalone module
- IntentSignalDetector never updated to use it
- No integration test catching the disconnect

#### GAP-002.4: Fix Strategy

**Step 1**: Import TemporalParser in IntentSignalDetector
**Step 2**: Create TemporalParser instance (or singleton)
**Step 3**: Call parse_temporal_json() instead of returning None
**Step 4**: Pass event timestamp as reference_time

**Implementation:**

```python
# In IntentSignalDetector.__init__():
from k0.modules.consolidation.algorithms.temporal_parser import TemporalParser

class IntentSignalDetector:
    def __init__(self):
        self._temporal_parser = TemporalParser()  # ADD THIS

    def _parse_temporal_date(
        self,
        temporal_json: str,
        reference_time_ms: Optional[int] = None,  # ADD PARAM
    ) -> Optional[int]:
        """Parse temporal_json to extract target date."""
        if not temporal_json or temporal_json == "[]":
            return None

        try:
            # Use TemporalParser instead of returning None
            return self._temporal_parser.parse_temporal_json(
                temporal_json=temporal_json,
                reference_time=reference_time_ms,
            )
        except Exception as e:
            # Log error but don't fail entire signal detection
            logger.warning(f"Temporal parsing failed: {e}")
            return None
```

**Update caller** in `_extract_reminder()`:

```python
def _extract_reminder(self, event: P03EventState) -> ReminderSignal:
    """Extract reminder signal from set_reminder event."""
    # Parse temporal_json for target date
    target_date = self._parse_temporal_date(
        event.temporal_expressions_json,
        reference_time_ms=event.timestamp,  # Pass event time as reference
    )

    # Extract action from text using patterns
    action = self._extract_action_from_text(event.content_text)

    return ReminderSignal(
        signal_type=IntentSignalType.REMINDER,
        event_id=event.event_id,
        confidence=self.DEFAULT_CONFIDENCE,
        source_text=event.content_text,
        action_description=action,
        target_date=target_date,  # Now populated!
    )
```

#### GAP-002.5: Files to Modify

1. **PRIMARY**: `k0/modules/consolidation/algorithms/intent_signal_detector.py`
   - Add TemporalParser import
   - Initialize `_temporal_parser` in `__init__`
   - Replace `return None` with `_temporal_parser.parse_temporal_json()` call
   - Pass reference_time_ms parameter

2. **TESTS**: `tests/k0/modules/consolidation/algorithms/test_intent_signal_detector.py`
   - Add test: `test_reminder_with_temporal_expression()`
   - Verify target_date is populated
   - Mock or use real temporal_json fixtures

#### GAP-002.6: Test Plan

**Unit Test**: Verify temporal parsing wired

```python
def test_reminder_signal_extracts_target_date():
    """Verify ReminderSignal.target_date is populated from temporal_json."""
    detector = IntentSignalDetector()

    event = P03EventState(
        event_id="evt_001",
        intent_label="set_reminder",
        content_text="Remind me to call Mom tomorrow at 3pm",
        temporal_expressions_json='{"entities": [{"text": "tomorrow at 3pm", "label": "TIME"}]}',
        timestamp=1736726400000,  # 2026-01-13 00:00:00
    )

    signal = detector._extract_reminder(event)

    assert isinstance(signal, ReminderSignal)
    assert signal.target_date is not None
    # tomorrow at 3pm from 2026-01-13 00:00 = 2026-01-14 15:00
    expected_ms = 1736870400000
    assert abs(signal.target_date - expected_ms) < 1000 * 60  # Within 1 minute
```

**Integration Test**: E2E reminder flow

```python
@pytest.mark.asyncio
async def test_e2e_reminder_target_date_in_database():
    """Verify target_date makes it to st_prospective."""
    # Create event with temporal expression
    # Run through P03 pipeline
    # Query st_prospective
    # Assert target_date IS NOT NULL
    # Assert target_date matches expected timestamp
```

**Validation on Production Data**:

```sql
-- After fix + rerun
SELECT intention_description,
       target_date,
       TO_TIMESTAMP(target_date/1000) as target_datetime
FROM st_prospective
WHERE intention_type = 'REMINDER' AND target_date IS NOT NULL
LIMIT 10;

-- Should see parsed timestamps for all temporal expressions
```

#### GAP-002.7: Estimated Effort

- **Coding**: 1 hour (wire TemporalParser + handle edge cases)
- **Testing**: 1 hour (unit + integration tests)
- **Validation**: 30 minutes (verify on test data)
- **Total**: 2.5 hours

---

### GAP-003: st_procedural Routine Detection Missing 🟡

**Status**: ✅ Analysis COMPLETE - Requires Design Phase
**Location**: No RoutineDetector module exists
**Severity**: High (feature missing - habit tracking non-functional)
**Neurological Basis**: Basal Ganglia → Procedural Memory / Habit Formation

#### GAP-003.1: Neurological Foundation

**Brain Region**: **Basal Ganglia** (Striatum, Putamen, Caudate Nucleus)

**Function in Humans**:

- **Habit Formation**: Dorsal striatum encodes repeated action sequences through reward-based learning
- **Motor Programs**: Converts conscious actions into automatic routines (e.g., driving, typing)
- **Temporal Prediction**: Basal ganglia learns temporal statistics of recurring behaviors
- **Context-Action Binding**: Putamen links environmental cues to habitual responses

**Key Neuroscience**:

- **Habit Loop**: Cue → Routine → Reward (Graybiel & Grafton, 2015)
- **Chunking**: Brain compresses repeated sequences into single units for efficiency
- **TD Learning**: Basal ganglia uses temporal difference learning for habit strength
- **Procedural vs Declarative**: Habits stored separately from explicit memory (can't verbalize)

**Why This Matters**:
The st_procedural layer models the basal ganglia's role in detecting and optimizing repeated behavioral patterns. Without routine detection, the system loses:

- Ability to predict future behaviors from past patterns
- Optimization opportunities ("You usually take this route")
- Habit-breaking interventions (detecting maladaptive routines)
- Energy-efficient pattern reuse

#### GAP-003.2: Current State

**Database Evidence**:

```sql
SELECT COUNT(*) FROM st_procedural;
-- Result: 0 rows (completely empty)
```

**Code Reality**:

- ❌ No `RoutineDetector` module exists in codebase
- ❌ No temporal pattern detection algorithm
- ❌ No habit formation scoring
- ✅ Schema EXISTS in database with all columns
- ✅ R7 Truth Writer has ProceduralLayerWriter stub
- ✅ R5 DreamExplorer outputs RoutineOptimization objects (TDL-HCO algorithm)

**What's Missing**:

1. **Temporal Pattern Miner**: Detect recurring time-based sequences
2. **Routine Classifier**: Distinguish habits from one-time actions
3. **Habit Strength Scorer**: Frequency × consistency × recency
4. **Context Extractor**: Identify triggering cues (location, time, preceding events)

#### GAP-003.3: Root Cause Analysis

**Why Empty**:

- Procedural memory detection is **NOT IMPLEMENTED** in any phase
- R2 Episodic Clustering focuses on single events, not sequences
- R5 TDL-HCO generates *prospective* routine optimizations (forward-looking)
- No *retrospective* routine extraction from historical episodes
- Design requires multi-episode temporal analysis (cross-episode pattern mining)

**Neurological Parallel**:
In the brain, habit formation requires:

1. **Repetition**: Multiple exposures to same context-action pair
2. **Reinforcement**: Dopamine signals strengthen successful routines
3. **Consolidation**: Sleep-dependent transfer from hippocampus to striatum

Our system has:

- ✅ Repetition data (episodic memory)
- ❌ No cross-episode pattern detector
- ❌ No habit strength scoring
- ❌ No consolidation from episodes → procedures

#### GAP-003.4: Architectural Requirements

**Algorithm Design Needed**:

1. **Routine Candidate Detection** (Temporal Pattern Mining):

   ```
   Input: st_epi (451 episodes with timestamps, locations, activity_type)
   Output: Routine candidates with:
     - Pattern signature ("Coffee at Starbucks")
     - Temporal regularity ("Every weekday at 8am ± 30min")
     - Occurrence count (15 times in 30 days)
   ```

2. **Habit Strength Scoring** (Basal Ganglia Model):

   ```
   Strength = (Frequency × Consistency × Recency) / TimeWindow

   Frequency: How many times pattern occurred
   Consistency: Temporal variance (low = strong habit)
   Recency: Exponential decay (recent = still active)
   ```

3. **Context-Action Binding** (Cue Detection):

   ```
   Cue Types:
     - Temporal: "Every Monday at 9am"
     - Spatial: "When at gym"
     - Sequential: "After coffee, check email"
     - Social: "When with Bob"
   ```

4. **Routine Lifecycle**:

   ```
   States: FORMING → ESTABLISHED → MAINTAINED → DECAYING → EXTINCT
   Transitions based on:
     - Forming: 3-7 repetitions in 21 days
     - Established: Consistency > 0.8, count > 10
     - Decaying: No occurrence in expected window
   ```

#### GAP-003.5: Implementation Strategy

**Phase 1: Design (3-5 days)**

- [ ] Create ADR for routine detection architecture
- [ ] Design RoutineDetector module specification
- [ ] Define routine_candidate, routine_pattern schemas
- [ ] Design temporal pattern mining algorithm (sliding window? sequence mining?)
- [ ] Define habit strength formula with neurological grounding

**Phase 2: Core Implementation (5-7 days)**

- [ ] Create `k0/modules/consolidation/algorithms/routine_detector.py`
- [ ] Implement TemporalPatternMiner (detect recurring sequences)
- [ ] Implement HabitStrengthScorer (frequency × consistency × recency)
- [ ] Implement ContextExtractor (identify triggering cues)
- [ ] Wire to R2 or new R2.5 phase (after episodic clustering)

**Phase 3: Integration (2-3 days)**

- [ ] Update ProceduralLayerWriter to accept RoutineCandidate objects
- [ ] Add routine_id generation (ULID)
- [ ] Write integration tests (episode sequences → routines)
- [ ] Validate on real data (should detect coffee routine, gym pattern, etc.)

**Phase 4: R5 Integration (2 days)**

- [ ] Wire TDL-HCO outputs to st_procedural (optimization_suggestion field)
- [ ] Create bidirectional link: retrospective routines ↔ prospective optimizations
- [ ] Enable "habit breaking" insights from R5

#### GAP-003.6: Neurological Validation Criteria

**How to Know It's Working**:

1. **Habit Detection**: System identifies patterns humans recognize as routines
   - "Coffee at 8am every weekday" (temporal)
   - "Gym on Monday/Wednesday/Friday" (weekly pattern)
   - "Check email after breakfast" (sequential)

2. **Habit Strength**: Scores correlate with subjective strength
   - Strong habits: high frequency, low variance, recent
   - Weak habits: sporadic, high variance, or decaying

3. **Cue Sensitivity**: Detects context-dependent triggers
   - "Only at home office" (spatial cue)
   - "When stressed" (emotional cue - from sentiment)
   - "After specific person visits" (social cue)

4. **Lifecycle Transitions**: Tracks habit formation/extinction
   - New routine: FORMING → ESTABLISHED over 2-4 weeks
   - Broken habit: MAINTAINED → DECAYING → EXTINCT when stopped

#### GAP-003.7: Example Output Schema

```python
RoutineRecord(
    routine_id="01JFXYZ...",
    routine_name="Morning Coffee Routine",
    activity_type="FOOD_DRINK",
    pattern_signature={
        "action": "get_coffee",
        "location": "Starbucks on Main St",
        "time_window": "07:30-08:30",
        "frequency": "weekdays"
    },
    habit_strength=0.87,  # High strength
    occurrence_count=23,
    first_occurrence_ms=1705996800000,
    last_occurrence_ms=1736726400000,
    temporal_regularity=0.92,  # Low variance
    triggering_cues=["weekday_morning", "commute_route"],
    lifecycle_state="ESTABLISHED",
    optimization_suggestion="Try earlier time to avoid lines"
)
```

#### GAP-003.8: Estimated Effort

- **Design Phase**: 3-5 days (ADR, algorithm design, schema)
- **Implementation**: 5-7 days (RoutineDetector module + tests)
- **Integration**: 2-3 days (wire to pipeline, validate)
- **R5 Integration**: 2 days (TDL-HCO linkage)
- **Total**: 12-17 days (~2.5-3.5 weeks)

**Dependencies**:

- Requires GAP-001 fix (episode_summary for pattern description)
- Benefits from GAP-002 fix (temporal patterns)
- Complements R5 TDL-HCO (retrospective + prospective routines)

---

### GAP-004: Entity Alias Merging Missing 🟡

**Status**: ✅ Analysis COMPLETE - Requires NLP Design
**Location**: `k0/pipelines/p03/phases/r4_kg_consolidator.py` + R4 entity extraction
**Severity**: High (duplicate entities fragment knowledge graph)
**Neurological Basis**: Semantic Networks → Coreference Resolution

#### GAP-004.1: Neurological Foundation

**Brain Region**: **Temporal Lobe** (Semantic Memory Networks)

**Function in Humans**:

- **Entity Recognition**: Brain maintains single representation for each real-world entity
- **Coreference Resolution**: Automatically links "Mom", "Mother", "Mama" to same person
- **Semantic Binding**: Different labels activate same underlying concept node
- **Contextual Disambiguation**: Uses context to resolve ambiguous references ("Jordan" = person vs country)

**Key Neuroscience**:

- **Hub-and-Spoke Model**: Anterior temporal lobe acts as semantic hub linking multiple labels
- **Neural Reuse**: Same neurons activate for synonymous terms (fMRI studies)
- **Lexical-Semantic Interface**: Brain stores multiple lexical forms pointing to single concept
- **Entity Consolidation**: Sleep-dependent merging of coreferent memories

**Why This Matters**:
The st_kg_dom layer models semantic entity representations. Without alias merging:

- **Knowledge Fragmentation**: "Mom" and "Mother" treated as separate people
- **Graph Sparsity**: Relationships split across duplicate nodes (weak PMI scores)
- **Insight Degradation**: BGT-SM can't discover connections between "Mom" and related concepts
- **Memory Inefficiency**: Redundant storage and processing

#### GAP-004.2: Current State

**Database Evidence**:

```sql
-- Check for potential duplicates
SELECT canonical_name, entity_type, COUNT(*) as count
FROM st_kg_dom
GROUP BY canonical_name, entity_type
HAVING COUNT(*) > 1;
-- Result: 0 (no exact duplicates detected by simple grouping)

-- But semantic duplicates exist:
SELECT entity_id, canonical_name, entity_type
FROM st_kg_dom
WHERE entity_type = 'PERSON'
ORDER BY canonical_name;
-- Result shows: "Mom", "Mother", "Mama" as separate entities
```

**Schema Check**:

```sql
SELECT aliases_json FROM st_kg_dom WHERE aliases_json IS NOT NULL;
-- Result: 0 rows (aliases_json is NULL for all 147 entities)
```

**Code Reality**:

- ✅ Schema has `aliases_json` column
- ❌ Column is NEVER populated (always NULL)
- ❌ No coreference resolution in R4 KG Consolidator
- ❌ No entity deduplication logic
- ❌ No fuzzy matching or semantic similarity for entity merging

#### GAP-004.3: Root Cause Analysis

**Why Aliases Empty**:

1. **UltraBERT NER**: Extracts entities from raw text
   - "Call Mom" → entity: "Mom" (PERSON)
   - "Mother's birthday" → entity: "Mother" (PERSON)
   - Each creates separate entity_id

2. **R4 KG Consolidator**: Groups entities by exact canonical_name match only
   - No fuzzy matching
   - No semantic similarity
   - No pronoun resolution ("she", "her" → person name)
   - No nickname detection ("Bob" = "Robert")

3. **No Alias Detection Module**: Missing component to:
   - Detect potential aliases
   - Score alias confidence
   - Merge coreferent entities
   - Update aliases_json field

**Neurological Parallel**:
Humans resolve coreference through:

- **Phonological Similarity**: "Mom" ≈ "Mama" (sound-based)
- **Semantic Context**: "She" in "Call Mom. She said yes" resolves to Mom
- **World Knowledge**: "Bob" and "Robert" are common nickname pairs
- **Frequency Co-occurrence**: Entities in similar contexts likely same

Our system lacks ALL of these mechanisms.

#### GAP-004.4: Architectural Requirements

**Algorithm Design Needed**:

1. **Alias Candidate Detection**:

   ```
   Strategies:
     a) String Similarity: Levenshtein distance < threshold ("Mom" ↔ "Mama")
     b) Embedding Similarity: Cosine distance < 0.1 (semantic equivalence)
     c) Nickname Database: "Bob" ↔ "Robert" (English name pairs)
     d) Pronoun Resolution: "he", "she", "they" → antecedent
     e) Co-occurrence: Entities never appearing together (mutual exclusion)
   ```

2. **Coreference Scoring**:

   ```
   Score = weighted_sum([
       string_similarity_score * 0.2,
       embedding_similarity_score * 0.3,
       context_overlap_score * 0.3,
       exclusion_score * 0.2  # Never co-occur = likely same
   ])

   Threshold: 0.7 → merge entities
   ```

3. **Entity Merging Strategy**:

   ```
   When merging entity_A → entity_B:
     1. Keep entity_B as canonical (higher observation_count)
     2. Add entity_A.canonical_name to entity_B.aliases_json
     3. Rewrite all edges: source_id/target_id = entity_A → entity_B
     4. Merge attributes_json (union of properties)
     5. Sum observation_counts
     6. Delete entity_A or mark as MERGED → entity_B
   ```

4. **Pronoun Resolution** (Advanced):

   ```
   Text: "Call Mom. She said yes."

   Step 1: Detect pronoun "She"
   Step 2: Find antecedent candidates (PERSON entities in prior sentences)
   Step 3: Score by recency + gender match + context
   Step 4: Link "She" → "Mom"
   ```

#### GAP-004.5: Implementation Strategy

**Phase 1: Design (2-3 days)**

- [ ] Create ADR for entity alias detection architecture
- [ ] Research coreference resolution approaches (spaCy? neuralcoref? custom?)
- [ ] Define alias_candidate, merge_proposal schemas
- [ ] Design scoring formula with weights
- [ ] Define merge transaction flow (database updates)

**Phase 2: Core Implementation (5-7 days)**

- [ ] Create `k0/modules/consolidation/algorithms/alias_detector.py`
- [ ] Implement StringSimilarityMatcher (Levenshtein + phonetic)
- [ ] Implement EmbeddingSimilarityMatcher (cosine distance)
- [ ] Implement NicknameDatabaseMatcher (common name pairs)
- [ ] Implement CoreferenceScorer (weighted combination)
- [ ] Implement EntityMerger (database transaction logic)

**Phase 3: Integration (3-4 days)**

- [ ] Wire AliasDetector to R4 KG Consolidator (after initial entity extraction)
- [ ] Add merge proposals to R6 staging (for review/rollback)
- [ ] Update KGEntityWriter to populate aliases_json
- [ ] Write integration tests ("Mom" + "Mother" → merged entity)

**Phase 4: Validation (2-3 days)**

- [ ] Run on historical data (detect merges)
- [ ] Manual review of top 20 merge proposals (precision check)
- [ ] Validate graph connectivity improves (edge count per entity)
- [ ] Check BGT-SM generates better insights (higher PMI scores)

#### GAP-004.6: Example Scenarios

**Scenario 1: Family Members**

```
Before:
  - Entity: "Mom" (ID: e001, obs_count: 45)
  - Entity: "Mother" (ID: e002, obs_count: 12)
  - Entity: "Mama" (ID: e003, obs_count: 8)
  - Total: 3 entities, 65 observations

After Merge:
  - Entity: "Mom" (ID: e001, obs_count: 65)
    aliases_json: ["Mother", "Mama"]
  - Result: 1 entity, consolidated knowledge
```

**Scenario 2: Nicknames**

```
Before:
  - Entity: "Bob" (ID: e010, obs_count: 20)
  - Entity: "Robert" (ID: e011, obs_count: 5)

After Merge:
  - Entity: "Bob" (ID: e010, obs_count: 25)
    aliases_json: ["Robert"]
```

**Scenario 3: Pronouns** (Advanced)

```
Text: "Called Bob. He agreed to meet tomorrow."

Before:
  - Entity: "Bob" (PERSON)
  - Entity: "He" (PERSON) ← WRONG

After Coreference:
  - Entity: "Bob" (PERSON)
  - "He" → resolves to "Bob" (no separate entity)
```

#### GAP-004.7: Neurological Validation Criteria

**How to Know It's Working**:

1. **Merge Accuracy**: Humans agree with 90%+ of merges
   - "Mom" + "Mother" = YES (obvious)
   - "Alex" + "Alexandra" = MAYBE (need context)
   - "Jordan" (person) + "Jordan" (country) = NO (disambiguation)

2. **Graph Consolidation**:

   ```sql
   -- Before: 147 entities, avg 0.05 edges per entity
   -- After: 120 entities, avg 0.08 edges per entity
   -- Improvement: Denser graph, stronger connections
   ```

3. **BGT-SM Impact**: Insights reference consolidated entities
   - Before: "Insight connects Bob to Coffee"
   - After: "Insight connects Bob (aka Robert) to Coffee"
   - Higher PMI scores due to combined observation counts

4. **Zero False Positives**: No obviously incorrect merges
   - Don't merge "Apple" (company) + "Apple" (fruit)
   - Require context/type match for ambiguous names

#### GAP-004.8: Estimated Effort

- **Design Phase**: 2-3 days (ADR, coreference research, scoring design)
- **Implementation**: 5-7 days (AliasDetector module + NLP integration)
- **Integration**: 3-4 days (R4 wiring, database updates)
- **Validation**: 2-3 days (manual review, graph metrics)
- **Total**: 12-17 days (~2.5-3.5 weeks)

**Dependencies**:

- Uses entity embeddings (already exist)
- Benefits from GAP-001 (episode context for coreference)
- Critical for R5 BGT-SM effectiveness (denser graph = better insights)

**NLP Libraries to Consider**:

- **spaCy**: Built-in coreference resolution (neuralcoref extension)
- **AllenNLP**: State-of-art coreference models
- **Fuzzywuzzy**: String similarity scoring
- **Custom**: Lightweight embedding-based approach

---

### GAP-005: Fine-Grained Subtype Classification Missing 🟢

**Status**: Enhancement (Low Priority)
**Location**: Multiple layers (st_sem.pattern_subtype, st_social.relationship_subtype, st_kg_dom.entity_subtype)
**Severity**: Low (functional without, but limits granularity)
**Neurological Basis**: Hierarchical Cortical Processing → Category Refinement

#### GAP-005.1: Neurological Foundation

**Brain Region**: **Prefrontal Cortex** (Category Hierarchies) + **Temporal Lobe** (Semantic Taxonomy)

**Function in Humans**:

- **Hierarchical Categorization**: Brain organizes concepts in multi-level taxonomies
  - Superordinate: "Relationship"
  - Basic: "Friend"
  - Subordinate: "Close Friend", "Work Friend", "Childhood Friend"
- **Categorical Perception**: Refined categories enable finer-grained predictions
- **Contextual Differentiation**: Subtypes capture nuanced distinctions

**Key Neuroscience**:

- **Prototype Theory**: Brain stores prototypical examples of subcategories
- **Graded Membership**: Entities can be "more" or "less" typical of subtype
- **Feature-Based Classification**: Subtypes defined by distinctive feature bundles
- **Anterior Temporal Lobe**: Stores fine-grained semantic distinctions

**Why This Matters**:
Subtype classification enables:

- **Precise Retrieval**: "Find close friends" vs "Find all friends"
- **Nuanced Insights**: "Your work friendships lack depth" vs "You have many friendships"
- **Better Predictions**: "Close friends usually call back within 1 hour"
- **Richer Context**: "Childhood friends share history, work friends share goals"

#### GAP-005.2: Current State - What's Missing

**1. st_sem.pattern_subtype** (0 / 2817 populated):

```sql
SELECT pattern_type, COUNT(*) FROM st_sem GROUP BY pattern_type;
-- Results: THEME, LESSON, EMOTIONAL_TREND (coarse types only)

-- Missing subtypes:
-- THEME → HEALTH_THEME, WORK_THEME, RELATIONSHIP_THEME
-- LESSON → CAUTIONARY_TALE, BEST_PRACTICE, INSIGHT
-- EMOTIONAL_TREND → INCREASING_STRESS, SUSTAINED_JOY, BURNOUT_PATTERN
```

**2. st_social.relationship_subtype** (2 / 24 populated):

```sql
SELECT relationship_type, relationship_subtype FROM st_social;
-- Results:
--   FRIEND → NULL (should be: CLOSE_FRIEND, CASUAL_ACQUAINTANCE, WORK_FRIEND)
--   FAMILY → NULL (should be: PARENT, SIBLING, EXTENDED_FAMILY)
--   COLLEAGUE → NULL (should be: MANAGER, PEER, DIRECT_REPORT)
```

**3. st_kg_dom.entity_subtype** (0 / 147 populated):

```sql
SELECT entity_type, COUNT(*) FROM st_kg_dom GROUP BY entity_type;
-- Results: PERSON, LOCATION, ORGANIZATION (basic types only)

-- Missing subtypes:
-- PERSON → FAMILY_MEMBER, FRIEND, PROFESSIONAL, CELEBRITY
-- LOCATION → HOME, WORKPLACE, RECREATIONAL, TRANSIT
-- ORGANIZATION → EMPLOYER, SCHOOL, BUSINESS, GOVERNMENT
```

#### GAP-005.3: Root Cause Analysis

**Why Subtypes Empty**:

1. **Feature Extraction Needed**: Subtypes require analyzing entity/relationship features
   - Intimacy level, interaction frequency, context patterns
2. **Classification Rules**: No decision trees or models to assign subtypes
3. **Training Data**: Subtypes require labeled examples or rule-based heuristics
4. **Design Trade-off**: MVP focused on coarse types for faster deployment

**Neurological Parallel**:
The brain refines categories through:

- **Experience**: Repeated exposures reveal fine-grained distinctions
- **Social Learning**: Culture teaches subcategory boundaries ("What is a 'close' friend?")
- **Contextual Tuning**: Prefrontal cortex adjusts category boundaries based on goals

Our system has coarse types but no refinement mechanism.

#### GAP-005.4: Implementation Strategy (When Prioritized)

**Phase 1: Semantic Pattern Subtypes**

```python
def classify_pattern_subtype(pattern: SemanticPattern) -> str:
    """
    Classify semantic pattern subtype based on features.

    THEME subtypes:
      - Health theme: mentions body, exercise, food, sleep
      - Work theme: mentions career, projects, deadlines
      - Relationship theme: mentions people, emotions, social events

    LESSON subtypes:
      - Cautionary tale: negative outcome, regret, warning
      - Best practice: positive outcome, success, recommendation
      - Insight: neutral analysis, connection, realization
    """
    if pattern.pattern_type == "THEME":
        if any(kw in pattern.pattern_name.lower() for kw in ["health", "exercise", "sleep"]):
            return "HEALTH_THEME"
        elif any(kw in pattern.pattern_name.lower() for kw in ["work", "project", "career"]):
            return "WORK_THEME"
        elif any(kw in pattern.pattern_name.lower() for kw in ["friend", "family", "relationship"]):
            return "RELATIONSHIP_THEME"
    # ... more rules
    return None
```

**Phase 2: Relationship Subtypes**

```python
def classify_relationship_subtype(rel: SocialRelationship) -> str:
    """
    Classify relationship subtype based on intimacy + context.

    FRIEND subtypes:
      - Close friend: intimacy > 0.7, frequent contact, personal topics
      - Work friend: shared workplace, professional context
      - Casual acquaintance: low frequency, shallow topics

    FAMILY subtypes:
      - Parent: biological/adoptive parent role
      - Sibling: brother/sister
      - Extended family: aunts, uncles, cousins, grandparents
    """
    if rel.relationship_type == "FRIEND":
        if rel.intimacy_level > 0.7 and rel.interaction_frequency == "DAILY":
            return "CLOSE_FRIEND"
        elif "work" in rel.typical_activities_json:
            return "WORK_FRIEND"
        else:
            return "CASUAL_ACQUAINTANCE"
    # ... more rules
    return None
```

**Phase 3: Entity Subtypes**

```python
def classify_entity_subtype(entity: KGEntity) -> str:
    """
    Classify entity subtype based on attributes + relationships.

    PERSON subtypes:
      - Family member: has FAMILY relationship
      - Friend: has FRIEND relationship
      - Professional: appears in work contexts

    LOCATION subtypes:
      - Home: frequent presence, sleeping, relaxing activities
      - Workplace: work activities, colleagues present
      - Recreational: leisure activities, weekends
    """
    if entity.entity_type == "PERSON":
        # Check relationship graph
        if entity.has_relationship_type("FAMILY"):
            return "FAMILY_MEMBER"
        elif entity.has_relationship_type("FRIEND"):
            return "FRIEND"
        elif entity.appears_in_context("work"):
            return "PROFESSIONAL"
    # ... more rules
    return None
```

#### GAP-005.5: Estimated Effort

- **Design**: 1-2 days (define subtype taxonomies for each layer)
- **Implementation**: 3-5 days (classifier logic + feature extraction)
- **Validation**: 1-2 days (manual review of classifications)
- **Total**: 5-9 days (~1-2 weeks)

**Priority**: LOW - System functional without subtypes, but improves query precision

---

### GAP-006: st_sem.actor_id NULL (By Design) ℹ️

**Status**: Not a Bug - Documentation Issue
**Location**: `st_sem.actor_id` column
**Severity**: N/A (intentional design)
**Neurological Basis**: Global vs Local Memory Systems

#### GAP-006.1: Neurological Foundation

**Brain Region**: **Semantic Memory** (Temporal Lobe) vs **Episodic Memory** (Hippocampus)

**Function in Humans**:

- **Episodic Memory**: Personal, contextualized, actor-specific
  - "I had coffee at Starbucks yesterday" (who: me, when: yesterday, where: Starbucks)
- **Semantic Memory**: Generalized, decontextualized, actor-independent
  - "Coffee contains caffeine" (universal knowledge, not tied to any person)
  - "Starbucks opens at 6am" (general fact, applies to everyone)

**Key Neuroscience**:

- **Consolidation**: Episodic memories → abstracted into semantic facts (loses personal context)
- **Generalization**: Repeated personal experiences become universal patterns
- **Shared Knowledge**: Semantic memory is implicitly shareable across actors
- **Atemporal**: Semantic facts exist outside specific timepoints

**Why actor_id is NULL in st_sem**:
Semantic patterns represent **generalized knowledge** extracted from episodes:

- **Pattern**: "Morning routines improve productivity"
  - Source: 50 episodes from 3 different actors
  - Generalized: No single actor "owns" this pattern
  - Storage: st_sem with actor_id = NULL (applies to all)

- **Pattern**: "Stress increases before deadlines"
  - Source: 30 episodes from multiple actors
  - Generalized: Universal work pattern
  - Storage: st_sem with actor_id = NULL

#### GAP-006.2: Current Behavior (Correct)

```sql
SELECT pattern_name, actor_id FROM st_sem LIMIT 5;
-- Result: All actor_id = NULL
-- This is CORRECT behavior for semantic memory
```

**Why This is Intentional**:

1. Semantic patterns are **cross-actor abstractions**
2. Multiple actors can discover same pattern independently
3. Pattern generality makes it reusable across actors in multi-tenant scenarios
4. Actor-specific patterns should be in st_epi (episodic) or st_procedural (habits)

#### GAP-006.3: When actor_id SHOULD Be Populated

**Actor-Specific Patterns** (Future Enhancement):
If system detects **idiosyncratic patterns** unique to one actor:

- "Bob always misspells 'receive'"
- "Alice prefers tea, never coffee"
- "Jordan avoids phone calls on weekends"

These should have actor_id populated (currently not implemented).

**Implementation** (if needed):

```python
def extract_semantic_pattern(episodes: List[Episode]) -> SemanticPattern:
    # Check if pattern is actor-specific
    unique_actors = {ep.actor_id for ep in episodes}

    if len(unique_actors) == 1 and pattern_is_idiosyncratic(episodes):
        # Actor-specific pattern
        return SemanticPattern(
            pattern_name="Bob's coffee preference",
            actor_id=episodes[0].actor_id,  # Populate actor_id
        )
    else:
        # Generalized pattern
        return SemanticPattern(
            pattern_name="Morning beverage preferences",
            actor_id=None,  # NULL = applies to all
        )
```

#### GAP-006.4: Resolution

**Action**: Update documentation to clarify design choice

- **File**: `k0/modules/consolidation/staging/truth_write_assembler.py`
- **Add Comment**:

  ```python
  # actor_id is intentionally NULL for semantic patterns
  # Semantic memory represents generalized, actor-independent knowledge
  # Actor-specific patterns should use st_epi or st_procedural
  ```

**Effort**: 30 minutes (documentation update)

**Priority**: INFO - No code change needed

---

## 🧠 R5 Dream Algorithm Analysis: Why Insights Not Generating

**Status**: ✅ Root Cause Identified
**Issue**: 0 insights generated despite R5_MODE = ENABLED and 147 entities in KG
**Neurological Basis**: REM Sleep Consolidation → Insight Generation

### R5.1: Neurological Foundation (REM Sleep & Creativity)

**Brain Process**: **REM Sleep** → Creative Insight Generation

**Function in Humans**:

- **Memory Replay**: Hippocampus replays recent experiences during REM
- **Remote Associates**: PFC explores distant semantic connections
- **Pattern Integration**: Integrates new memories with existing knowledge structures
- **Creativity Boost**: REM sleep enhances associative thinking (Walker, 2017)
- **Offline Consolidation**: Weakens unimportant connections, strengthens meaningful ones

**Key Neuroscience**:

- **DMN Activation**: Default Mode Network active during REM (mind-wandering)
- **Acetylcholine Suppression**: Reduced feedback inhibition enables novel connections
- **Theta Oscillations**: Hippocampal theta facilitates memory-knowledge integration
- **Bisociative Thinking**: Connecting concepts from separate associative contexts (Koestler, 1964)

**System Equivalent**:

- **R5 Dream Explorer**: Models REM-like exploration of knowledge graph
- **BGT-SM Algorithm**: Bisociative Graph Traversal discovering remote associates
- **PMI Scoring**: Quantifies "surprise" of novel connections
- **Cold Start Protection**: Skips REM when insufficient knowledge (like newborns)

### R5.2: Current State - Why 0 Insights

**Configuration Check**:

```python
# k0/pipelines/p03/r5_config.py:230
P03_FF_R5_MODE: R5Mode = R5Mode.ENABLED  # ✅ R5 is ENABLED

# k0/pipelines/p03/r5_config.py:90
P03_BGT_COLD_START_THRESHOLD = 100  # Min corpus for BGT-SM
```

**Knowledge Graph State**:

```sql
-- Database reality:
SELECT COUNT(*) FROM st_kg_dom;    -- 147 entities ✅ Above threshold
SELECT COUNT(*) FROM st_kg_edges;  --   8 edges   ❌ CRITICALLY SPARSE

-- Insight generation:
SELECT COUNT(*) FROM st_sem WHERE pattern_type = 'INSIGHT';
-- Result: 0 (no insights generated)
```

**Root Cause**: **SPARSE GRAPH - NOT COLD START**

Despite having 147 entities (above 100 threshold), the knowledge graph is **critically sparse**:

- **8 edges / 147 entities** = 0.054 edges per entity
- **Expected**: 10-20 edges per entity for meaningful traversal
- **Problem**: BGT-SM random walks hit dead ends (no paths to explore)

### R5.3: BGT-SM Algorithm Execution Flow

**Step 1: Seed Selection** ✅ (Likely Working)

```python
# k0/modules/consolidation/dream/dream_explorer.py:482-530
seed_entity_ids = self._select_seed_entities(input_data)
# Selects high-salience entities from recent episodes
```

**Step 2: Random Walk with Restart** ❌ (Failing Here)

```python
# k0/modules/consolidation/algorithms/bgt_sm.py:1036-1050
visits = walk_engine.aggregate_walks(
    seed_entity_id,
    max_walks_per_seed=3,  # 3 walks per seed
)
# Problem: With only 0.054 edges/entity, walks immediately terminate
# Most entities are ISOLATED NODES with 0 outgoing edges
```

**Step 3: Find Remote Associates** ❌ (No Candidates)

```python
# k0/modules/consolidation/algorithms/bgt_sm.py:1052-1078
associates = self._find_remote_associates(...)
# Requires:
#   1. Semantic distance > 0.7 (remote)
#   2. PMI > 3.0 (surprising connection)
#
# Problem: With sparse graph, no remote nodes are reachable
# walks only visit 1-2 neighbors before dead end
```

**Step 4: Generate Insights** ❌ (Empty Input)

```python
# If no associates found, no insights generated
insights = []  # Empty list
return insights  # 0 insights
```

### R5.4: Why Graph is So Sparse

**R4 KG Consolidator** generates edges from:

1. **Co-occurrence**: Entities mentioned together in same event
2. **Explicit Relations**: "Bob called Alice" → edge(Bob, Alice, "CALLED")
3. **Temporal Proximity**: Events close in time → potential causal edge

**Problem Sources**:

**1. Single-Actor Dataset**: Most events involve only 1-2 entities

```sql
-- Check entity co-occurrence in episodes
SELECT participant_count, COUNT(*)
FROM st_epi
GROUP BY participant_count;
-- Expected result: Most episodes have 1-2 participants
-- Few edges created from sparse interactions
```

**2. Limited Social Interactions**: Family member events are personal, not social

```sql
SELECT relationship_type, COUNT(*) FROM st_social;
-- Result: 24 relationships (small social graph)
-- If data is mostly solo activities, few social edges
```

**3. Edge Creation Threshold**: R4 may require multiple co-occurrences before creating edge

```python
# Hypothesis: R4 creates edge only if co-occur count > threshold
# Single mentions don't create edges → sparse graph
```

### R5.5: Verification Steps

**1. Check actual edge count per entity**:

```sql
-- Outgoing edges per entity
SELECT source_id, COUNT(*) as out_degree
FROM st_kg_edges
GROUP BY source_id
ORDER BY out_degree DESC;

-- Incoming edges per entity
SELECT target_id, COUNT(*) as in_degree
FROM st_kg_edges
GROUP BY target_id
ORDER BY in_degree DESC;

-- Isolated nodes (0 edges)
SELECT COUNT(*)
FROM st_kg_dom e
WHERE NOT EXISTS (
    SELECT 1 FROM st_kg_edges
    WHERE source_id = e.entity_id OR target_id = e.entity_id
);
-- Expected: HIGH count of isolated nodes
```

**2. Check BGT-SM execution logs**:

```bash
# Look for BGT-SM skip messages in logs
docker logs k0-kernel --tail 500 | grep -i "bgt-sm\|cold.start\|insight"

# Expected output:
# "BGT-SM skipped: no seed entities available" OR
# "BGT-SM discovery complete: insights_generated=0"
```

**3. Check R5 phase execution**:

```sql
-- If we had st_cycles table:
-- SELECT r5_skipped, r5_skip_reason FROM st_cycles ORDER BY created_at DESC LIMIT 5;

-- Alternative: Check if R5 outputs exist
SELECT COUNT(*) FROM st_sem WHERE pattern_type = 'INSIGHT';
-- Result: 0 (confirms no insights generated)
```

### R5.6: Solution Paths

**Option 1: Lower BGT-SM Requirements** (Quick Fix)

```python
# k0/modules/consolidation/algorithms/bgt_sm.py:76-78
P03_BGT_SEMANTIC_DISTANCE_THRESHOLD = 0.7  # Lower to 0.4 (more permissive)
P03_BGT_PMI_THRESHOLD = 3.0  # Lower to 1.5 (less surprising required)
P03_BGT_COLD_START_THRESHOLD = 100  # Already lowered from 10,000

# Effect: Generate insights from weaker connections
# Risk: Lower quality insights (less "surprising")
```

**Option 2: Enrich Knowledge Graph** (Proper Fix)

```python
# Enhance R4 KG Consolidator to create more edges:

1. **Implicit Relations**: Infer edges from context
   - "Bob's office" → edge(Bob, office, "WORKS_AT")
   - "Mom's birthday" → edge(User, Mom, "FAMILY_OF")

2. **Transitive Closure**: Create implied edges
   - If A→B and B→C, create A→C edge (path compression)
   - Increases reachability for random walks

3. **Semantic Similarity Edges**: Connect similar entities
   - If embedding_similarity(A, B) > 0.8, create edge(A, B, "SIMILAR_TO")
   - Enables walks between conceptually related nodes

4. **Temporal Edges**: Connect time-adjacent entities
   - Entities in consecutive events → edge(A, B, "PRECEDES")
   - Enables discovery of sequential patterns
```

**Option 3: Hybrid Approach** (Recommended)

```python
1. **Short-term**: Lower BGT-SM thresholds to generate SOME insights
   - Demonstrates R5 functionality
   - Provides user value immediately
   - Sets: distance_threshold=0.4, pmi_threshold=1.5

2. **Medium-term**: Implement GAP-004 (Entity Alias Merging)
   - Consolidates duplicate entities → denser graph
   - "Mom" + "Mother" + "Mama" → 1 entity with 3x connections

3. **Long-term**: Enhance R4 with implicit relation extraction
   - Increases edge count from ~8 to ~50-100
   - Enables meaningful graph traversal
   - Unlocks full BGT-SM potential
```

### R5.7: Neurological Validation

**Healthy REM Sleep** requires:

- **Rich Memory Content**: Sufficient experiences to integrate
- **Associative Network**: Connected memories enabling traversal
- **Temporal Stability**: Consistent sleep patterns for consolidation

**Healthy R5 Execution** requires:

- **Rich Knowledge Graph**: 100+ entities ✅ (Have: 147)
- **Dense Connectivity**: 10-20 edges/entity ❌ (Have: 0.054)
- **Semantic Diversity**: Varied entity types ✅ (Have: PERSON, LOCATION, ORG)

**Current Status**: **R5 is "trying to dream" but the knowledge graph is too sparse to generate meaningful insights** — like trying to have creative REM sleep with only 1 day of memories.

### R5.8: Immediate Action Items

**Priority 1: Verify Hypothesis**

```sql
-- Run this query to confirm isolated nodes:
SELECT
  (SELECT COUNT(*) FROM st_kg_dom) as total_entities,
  (SELECT COUNT(*) FROM st_kg_edges) as total_edges,
  (SELECT COUNT(*) FROM st_kg_dom e
   WHERE NOT EXISTS (
     SELECT 1 FROM st_kg_edges
     WHERE source_id = e.entity_id OR target_id = e.entity_id
   )) as isolated_entities,
  ROUND((SELECT COUNT(*)::float FROM st_kg_edges) /
        (SELECT COUNT(*)::float FROM st_kg_dom), 3) as edges_per_entity;
```

**Priority 2: Quick Win - Lower Thresholds**

```python
# File: k0/modules/consolidation/algorithms/bgt_sm.py
# Change lines 76-78:
P03_BGT_SEMANTIC_DISTANCE_THRESHOLD = 0.4  # Was 0.7
P03_BGT_PMI_THRESHOLD = 1.5  # Was 3.0
P03_BGT_COLD_START_THRESHOLD = 50  # Was 100

# Re-run consolidation and check insights
```

**Priority 3: Implement GAP-004** (Entity Merging)

- Consolidates graph → increases density
- See GAP-004 section for full plan

**Priority 4: Enhance R4 Edge Creation** (Design Phase)

- Add implicit relation extraction
- Add semantic similarity edges
- Add transitive closure

### R5.9: Success Metrics

**After fixes, expect**:

```sql
-- Insights generated
SELECT COUNT(*) FROM st_sem WHERE pattern_type = 'INSIGHT';
-- Target: 5-20 insights per consolidation cycle

-- Edge density improved
SELECT COUNT(*)::float / (SELECT COUNT(*) FROM st_kg_dom) as edges_per_entity
FROM st_kg_edges;
-- Target: 0.5-1.0 edges/entity (10x improvement)

-- Isolated nodes reduced
SELECT COUNT(*) FROM st_kg_dom e
WHERE NOT EXISTS (SELECT 1 FROM st_kg_edges WHERE source_id = e.entity_id OR target_id = e.entity_id);
-- Target: < 20% of entities isolated
```

---

## Implementation Phases

### Phase 1: Critical Data Loss Fixes (1-2 days)

- [ ] GAP-001: Fix st_epi INSERT statement
- [ ] GAP-002: Wire TemporalParser to IntentSignalDetector
- [ ] Validation: Re-run consolidation and verify columns populated

### Phase 2: Feature Completion (3-5 days)

- [ ] GAP-003: Design and implement RoutineDetector
- [ ] GAP-004: Implement entity alias detection
- [ ] Validation: Run on historical data and verify results

### Phase 3: Enhancement (Optional)

- [ ] GAP-005: Fine-grained subtype classification
- [ ] GAP-006: Documentation update (actor_id by design)

---

## Next Steps

1. **Code Discovery**: Deep scan each GAP location
2. **Fill Skeleton**: Add detailed analysis to each section
3. **Create Fix Branch**: `fix/memory-layer-gaps`
4. **Implement Fixes**: Sequential PRs for each GAP
5. **Validate**: Test on production data snapshot

---

## Code Discovery Progress

- [x] Initial pipeline scan complete
- [x] Skeleton created
- [x] **GAP-001 detailed analysis COMPLETE** ✅
  - Root cause identified: INSERT SQL missing 6 columns
  - Fix documented with code examples
  - Test plan defined
- [x] **GAP-002 detailed analysis COMPLETE** ✅
  - Root cause identified: TemporalParser not wired despite existing
  - Fix documented with integration steps
  - Test plan defined
- [ ] GAP-003 architecture design (routine detection - requires design phase)
- [ ] GAP-004 coreference strategy (entity aliases - requires NLP design)

---

## 🚀 Ready for Implementation

**GAP-001 and GAP-002 are fully analyzed and ready to implement.**

Both fixes are straightforward code changes with clear test plans. Estimated combined effort: **5 hours** (coding + testing).

---

*GAP-003 and GAP-004 require architectural design before implementation (see separate sections below).*

---

Add a “Part J: Wiring checklist per algorithm” section (still skeleton) that lists each algorithm (semantic similarity, temporal proximity, contextual, transitive closure, Bayesian causal, weight normalization) with:

inputs it needs
syscalls it calls
envelope fields it emits
what must be persisted in st_kg_edges
