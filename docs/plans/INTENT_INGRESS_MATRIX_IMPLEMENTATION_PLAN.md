# Intent & Ingress Matrix Implementation Plan

**Created**: 2026-01-12
**GAP Reference**: [GAP_001_CROSS_LAYER_VECTOR_LINKING.md](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md)
**Related Milestones**: M7 (Intent-Aware Prospective Writer), M8 (Intent-Aware Memory Formation)
**Estimated Effort**: 5-6 days

---

## 1. Executive Summary

This plan implements the **Intent & Ingress Matrix** from GAP-001, enabling P03 consolidation to route events based on UltraBERT intent/ingress classification to appropriate truth layers.

### Current State Analysis

| Component | Status | Notes |
|-----------|--------|-------|
| `st_hipp_events.intent_category` | ✅ Exists (0046) | Values: log_memory, set_reminder, etc. (UltraBERT intent head) |
| `st_hipp_events.ingress_category` | ✅ Exists (0046) | Values: DIARY, TASK, HEALTH, etc. (UltraBERT ingress head) |
| `st_hipp_events.temporal_json` | ✅ Exists (0046) | UltraBERT temporal head output (labeled entities) |
| `P03EventState.intent_label` | ✅ Populated in R0 | Mapped from intent_category |
| `P03EventState.temporal_expressions_json` | ✅ Populated in R0 | Mapped from temporal_json |
| Intent detection in R5 | ❌ Not implemented | Algorithms don't check intent_label |
| Intent routing in R6 | ❌ Not implemented | No `assemble_intent_signal_writes()` |
| st_prospective REMINDER writes | ❌ Not implemented | CHECK constraint extended (0057) |
| st_sem LESSON/EMOTIONAL_TREND | ❌ Not implemented | ✅ CHECK constraint extended (0058) |
| st_kg_dom query_count | ❌ Not implemented | ✅ Column added (0059) |
| st_prospective DECISION | ❌ Not implemented | ✅ CHECK constraint extended (0057) |

---

## 2. Intent → Memory Layer Matrix

| Intent | K0 Action | st_epi | st_sem | st_prospective | st_kg_dom | st_kg_edges |
|--------|-----------|--------|--------|----------------|-----------|-------------|
| `log_memory` | Default storage | ✅ Primary | Pattern detect | — | Entity extract | Edge strengthen |
| `query_memory` | Query tracking | — | — | — | **Query++** | **Query++** |
| `set_reminder` | Create reminder | ✅ Context | — | ✅ **REMINDER** | Entity extract | — |
| `express_feeling` | Emotional trend | ✅ Emotional | **EMOTIONAL_TREND** | — | Entity extract | Sentiment on edge |
| `seek_advice` | Decision pending | ✅ Context | — | ✅ **DECISION** | Entity extract | — |
| `share_news` | Milestone | ✅ Milestone | — | — | **Milestone track** | — |
| `reflect` | Lesson learned | ✅ Introspection | ✅ **LESSON** | — | Entity extract | Insight edges |
| `other` | Default | ✅ Default | — | — | Entity extract | — |

---

## 3. Ingress Category Usage

| Ingress Category | Primary Layer | Special Handling |
|------------------|---------------|------------------|
| `DIARY` | st_epi | Standard episodic |
| `TASK` | st_procedural | Routine detection |
| `HEALTH` | st_epi + st_sem | Health pattern tracking |
| `CELEBRATION` | st_epi | Salience boost, milestone |
| `ROUTINE` | st_procedural | TDL-HCO input |
| `SOCIAL` | st_social | Relationship update |
| `TRAVEL` | st_epi | Location pattern |
| `WORK` | st_epi | Context tagging |
| `FAMILY` | st_social + st_epi | Family relationship boost |
| `MEAL` | st_epi + st_procedural | Routine pattern |
| `EXERCISE` | st_procedural + st_epi | Health + routine |
| `OTHER` | st_epi | Default |

---

## 4. Implementation Phases

### Phase 1: Schema Migrations (0.5 day) ✅ COMPLETE

**Status**: Implemented 2026-01-12

**Files Created**:
- `k0/db/alembic/versions/0057_st_prospective_intent_types.py`
- `k0/db/alembic/versions/0058_st_sem_pattern_types.py`
- `k0/db/alembic/versions/0059_kg_query_tracking.py`
- `tests/k0/db/alembic/test_intent_routing_migrations.py` (17 tests passing)

#### Issue 1.1: Extend st_prospective intention_type CHECK

**File**: `k0/db/alembic/versions/0060_st_prospective_intent_types.py` (NEW)

```sql
-- Extend intention_type CHECK to include DECISION
ALTER TABLE st_prospective DROP CONSTRAINT ck_prosp_intention_type;
ALTER TABLE st_prospective ADD CONSTRAINT ck_prosp_intention_type
  CHECK (intention_type IN ('GOAL', 'PLAN', 'REMINDER', 'COMMITMENT', 'WISH', 'DECISION', 'COUNTERFACTUAL'));
```

#### Issue 1.2: Extend st_sem pattern_type CHECK

**File**: `k0/db/alembic/versions/0061_st_sem_pattern_types.py` (NEW)

```sql
-- Add LESSON, EMOTIONAL_TREND, INSIGHT to pattern types
ALTER TABLE st_sem DROP CONSTRAINT ck_sem_pattern_type;
ALTER TABLE st_sem ADD CONSTRAINT ck_sem_pattern_type
  CHECK (pattern_type IN ('ROUTINE', 'PREFERENCE', 'THEME', 'RELATIONSHIP', 'GOAL', 'VALUE',
                          'LESSON', 'EMOTIONAL_TREND', 'INSIGHT'));
```

#### Issue 1.3: Add query_count to st_kg_dom and st_kg_edges

**File**: `k0/db/alembic/versions/0062_kg_query_tracking.py` (NEW)

```sql
ALTER TABLE st_kg_dom ADD COLUMN query_count INTEGER DEFAULT 0;
ALTER TABLE st_kg_dom ADD COLUMN last_queried_at BIGINT;
ALTER TABLE st_kg_dom ADD COLUMN milestones_json TEXT;

ALTER TABLE st_kg_edges ADD COLUMN query_count INTEGER DEFAULT 0;
ALTER TABLE st_kg_edges ADD COLUMN last_queried_at BIGINT;
ALTER TABLE st_kg_edges ADD COLUMN sentiment_avg FLOAT;
```

---

### Phase 2: Intent Signal Detection (1 day) ✅ COMPLETE

**Status**: Implemented 2026-01-12

**Files Created**:
- `k0/modules/consolidation/dream/intent_signals.py` - IntentSignal models (6 signal types)
- `k0/modules/consolidation/algorithms/intent_signal_detector.py` - IntentSignalDetector class
- `tests/k0/modules/consolidation/dream/test_intent_signals.py` - Model tests (27 tests)
- `tests/k0/modules/consolidation/algorithms/test_intent_signal_detector.py` - Detector tests (19 tests)

**Total Phase 2 Tests**: 46 tests passing

#### Issue 2.1: Create IntentSignal Models

**File**: `k0/modules/consolidation/dream/intent_signals.py` (NEW)

```python
"""
Intent Signal Models — GAP-001 Implementation

Intent signals detected from P03EventState that route to specific layers.
"""
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class IntentSignalType(str, Enum):
    """Types of intent signals."""
    REMINDER = "reminder"          # set_reminder → st_prospective
    DECISION = "decision"          # seek_advice → st_prospective
    LESSON = "lesson"              # reflect → st_sem
    EMOTIONAL_TREND = "emotional"  # express_feeling → st_sem
    MILESTONE = "milestone"        # share_news → st_kg_dom
    QUERY_BOOST = "query_boost"    # query_memory → st_kg_dom/edges


@dataclass
class IntentSignal:
    """Base intent signal detected from event."""
    signal_type: IntentSignalType
    event_id: str
    confidence: float
    source_text: str


@dataclass
class ReminderSignal(IntentSignal):
    """set_reminder intent → st_prospective REMINDER."""
    action_description: str
    target_date: Optional[int]  # Unix ms


@dataclass
class DecisionSignal(IntentSignal):
    """seek_advice intent → st_prospective DECISION."""
    decision_context: str
    options_mentioned: List[str]


@dataclass
class LessonSignal(IntentSignal):
    """reflect intent → st_sem LESSON."""
    lesson_description: str
    topic_entities: List[str]


@dataclass
class EmotionalSignal(IntentSignal):
    """express_feeling intent → st_sem EMOTIONAL_TREND."""
    emotion_label: str
    intensity: float
    target_entities: List[str]  # Who the feeling is about


@dataclass
class MilestoneSignal(IntentSignal):
    """share_news intent → st_kg_dom milestone."""
    milestone_type: str  # ACHIEVEMENT, ANNOUNCEMENT, TRANSITION
    entity_id: str


@dataclass
class QueryBoostSignal(IntentSignal):
    """query_memory intent → increment query_count."""
    entity_ids: List[str]
    edge_ids: List[str]
```

#### Issue 2.2: Create IntentSignalDetector

**File**: `k0/modules/consolidation/algorithms/intent_signal_detector.py` (NEW)

Responsibilities:

- Scan P03EventState list for intent-bearing events
- Parse temporal_json for REMINDER target dates
- Extract action descriptions from text
- Return list of IntentSignal objects

```python
"""
IntentSignalDetector — GAP-001 Implementation

Detects intent signals from P03EventState list.
Called by R5 DreamExplorer or directly by R6 TruthWriteAssembler.
"""
import json
import re
from typing import List

from k0.pipelines.p03.event_state import P03EventState
from k0.modules.consolidation.dream.intent_signals import (
    IntentSignal,
    IntentSignalType,
    ReminderSignal,
    DecisionSignal,
    LessonSignal,
    EmotionalSignal,
    MilestoneSignal,
    QueryBoostSignal,
)


class IntentSignalDetector:
    """Detects intent signals from event states."""

    # Regex patterns for action extraction
    REMINDER_PATTERNS = [
        r"remind me to (.+?)(?:\s+(?:at|on|in|by|tomorrow|next)|$)",
        r"don't forget to (.+?)(?:\s+(?:at|on|in|by)|$)",
        r"reminder[:\s]+(.+?)(?:\s+(?:at|on|in|by)|$)",
    ]

    def detect_all(
        self,
        event_states: List[P03EventState],
    ) -> List[IntentSignal]:
        """
        Detect all intent signals from event states.

        Routes based on intent_label:
        - set_reminder → ReminderSignal
        - seek_advice → DecisionSignal
        - reflect → LessonSignal
        - express_feeling → EmotionalSignal
        - share_news → MilestoneSignal
        - query_memory → QueryBoostSignal
        """
        signals: List[IntentSignal] = []

        for event in event_states:
            if not event.intent_label:
                continue

            signal = self._detect_for_event(event)
            if signal:
                signals.append(signal)

        return signals

    def _detect_for_event(self, event: P03EventState) -> Optional[IntentSignal]:
        """Detect signal for single event based on intent_label."""
        intent = event.intent_label.lower()

        if intent == "set_reminder":
            return self._extract_reminder(event)
        elif intent == "seek_advice":
            return self._extract_decision(event)
        elif intent == "reflect":
            return self._extract_lesson(event)
        elif intent == "express_feeling":
            return self._extract_emotional(event)
        elif intent == "share_news":
            return self._extract_milestone(event)
        elif intent == "query_memory":
            return self._extract_query_boost(event)

        return None

    def _extract_reminder(self, event: P03EventState) -> ReminderSignal:
        """Extract reminder signal from set_reminder event."""
        # Parse temporal_json for target date
        target_date = self._parse_temporal_date(event.temporal_expressions_json)

        # Extract action from text
        action = self._extract_action_from_text(event.content_text)

        return ReminderSignal(
            signal_type=IntentSignalType.REMINDER,
            event_id=event.event_id,
            confidence=0.8,  # TODO: Use intent confidence from UltraBERT
            source_text=event.content_text,
            action_description=action,
            target_date=target_date,
        )

    # ... other extraction methods
```

---

### Phase 3: R5 Integration (0.5 day) ✅ COMPLETE

**Status**: Implemented 2026-01-12

**Files Modified**:
- `k0/modules/consolidation/dream/models.py` - Added `intent_signals` field to `DreamExplorerOutput`
- `k0/modules/consolidation/dream/dream_explorer.py` - Added IntentSignalDetector call in `explore()`
- `k0/modules/consolidation/dream/__init__.py` - Exported IntentSignal types
- `k0/pipelines/p03/phase_outputs.py` - Added `r5_intent_signals` field to `P03PhaseOutputs`
- `k0/pipelines/p03/phases/r5_dream_explorer.py` - Added `intent_signals` to `R5PhaseOutputs`, updated `_stage_outputs()`

**Tests Created**:
- `tests/k0/modules/consolidation/dream/test_intent_signal_integration.py` (12 tests)

**Total Phase 3 Tests**: 12 tests passing

**R0 Integration Check**: ✅ Already implemented
- R0 already maps `intent_category → intent_label` in `_row_to_event_state()` (line 632)
- R0 already maps `temporal_json → temporal_expressions_json` in `_row_to_event_state()` (line 635)
- No changes needed to R0

#### Issue 3.1: Add Intent Detection to DreamExplorer

**File**: `k0/modules/consolidation/dream/dream_explorer.py` (MODIFY)

Add to `DreamExplorerOutput`:

```python
@dataclass
class DreamExplorerOutput:
    # ... existing fields
    intent_signals: List[IntentSignal] = field(default_factory=list)
```

Add intent detection to `explore()`:

```python
async def explore(self, input_data: DreamExplorerInput) -> DreamExplorerOutput:
    # ... existing algorithm calls

    # NEW: Detect intent signals
    intent_detector = IntentSignalDetector()
    intent_signals = intent_detector.detect_all(input_data.event_states)

    return DreamExplorerOutput(
        # ... existing outputs
        intent_signals=intent_signals,
    )
```

#### Issue 3.2: Update R5 Phase to Pass Intent Signals

**File**: `k0/pipelines/p03/phases/r5_dream_explorer.py` (MODIFY)

Update `R5PhaseOutputs`:

```python
@dataclass
class R5PhaseOutputs:
    # ... existing fields
    intent_signals: List[IntentSignal] = field(default_factory=list)
```

---

### Phase 4: R6 Intent Routing (1 day)

#### Issue 4.1: Create Intent Signal Assembler

**File**: `k0/modules/consolidation/staging/intent_signal_assembler.py` (NEW)

```python
"""
IntentSignalAssembler — Routes intent signals to appropriate layer writes.

Called by R6Coordinator to convert IntentSignals into StagedWrites.
"""
from typing import Dict, List

from k0.modules.consolidation.dream.intent_signals import (
    IntentSignal,
    IntentSignalType,
    ReminderSignal,
    DecisionSignal,
    LessonSignal,
    EmotionalSignal,
    MilestoneSignal,
    QueryBoostSignal,
)
from k0.pipelines.p03.staged_writes import (
    LAYER_ST_PROSPECTIVE,
    LAYER_ST_SEM,
    LAYER_ST_KG_DOM,
    LAYER_ST_KG_EDGES,
    StagedWrite,
    WriteOperation,
)


class IntentSignalAssembler:
    """Assembles StagedWrites from IntentSignals."""

    def __init__(self, tenant_id: str, space_id: str, actor_id: str):
        self.tenant_id = tenant_id
        self.space_id = space_id
        self.actor_id = actor_id

    def assemble_all(
        self,
        signals: List[IntentSignal],
    ) -> Dict[str, List[StagedWrite]]:
        """
        Convert all intent signals to staged writes.

        Returns dict mapping layer → writes for that layer.
        """
        result: Dict[str, List[StagedWrite]] = {}

        for signal in signals:
            writes = self._assemble_signal(signal)
            for layer, write in writes:
                if layer not in result:
                    result[layer] = []
                result[layer].append(write)

        return result

    def _assemble_signal(self, signal: IntentSignal) -> List[tuple]:
        """Route single signal to appropriate writes."""
        if signal.signal_type == IntentSignalType.REMINDER:
            return self._assemble_reminder(signal)
        elif signal.signal_type == IntentSignalType.DECISION:
            return self._assemble_decision(signal)
        elif signal.signal_type == IntentSignalType.LESSON:
            return self._assemble_lesson(signal)
        elif signal.signal_type == IntentSignalType.EMOTIONAL_TREND:
            return self._assemble_emotional(signal)
        elif signal.signal_type == IntentSignalType.MILESTONE:
            return self._assemble_milestone(signal)
        elif signal.signal_type == IntentSignalType.QUERY_BOOST:
            return self._assemble_query_boost(signal)
        return []

    def _assemble_reminder(self, signal: ReminderSignal) -> List[tuple]:
        """Create st_prospective INSERT for REMINDER."""
        record_data = {
            "intention_id": f"reminder_{signal.event_id}",
            "tenant_id": self.tenant_id,
            "space_id": self.space_id,
            "actor_id": self.actor_id,
            "intention_type": "REMINDER",
            "intention_description": signal.action_description,
            "target_date": signal.target_date,
            "target_context": signal.source_text,
            "status": "ACTIVE",
            "confidence_score": signal.confidence,
            # ... other fields
        }

        write = StagedWrite.insert(
            layer=LAYER_ST_PROSPECTIVE,
            record_id=record_data["intention_id"],
            data=record_data,
            phase="R6_INTENT",
            event_ids=[signal.event_id],
        )

        return [(LAYER_ST_PROSPECTIVE, write)]

    # ... other assembly methods for DECISION, LESSON, EMOTIONAL, etc.
```

#### Issue 4.2: Update R6 Coordinator

**File**: `k0/modules/consolidation/staging/r6_coordinator.py` (MODIFY)

Add intent signal routing:

```python
# In coordinate() method, after truth_assembly:

# === STEP 2.5: Assemble intent signal writes ===
step_start = _now_ms()
r5_intent_signals = getattr(phase_outputs, "r5_intent_signals", None) or []
intent_signal_writes = self.intent_assembler.assemble_all(r5_intent_signals)
# Merge into truth_assembly
for layer, writes in intent_signal_writes.items():
    if layer in truth_assembly:
        truth_assembly[layer].extend(writes)
    else:
        truth_assembly[layer] = writes
step_durations["assemble_intent_signals"] = _now_ms() - step_start
```

#### Issue 4.3: Update TruthWriteAssembler.assemble_all()

**File**: `k0/modules/consolidation/staging/truth_write_assembler.py` (MODIFY)

Add intent_signals parameter:

```python
def assemble_all(
    self,
    # ... existing params
    intent_signals: Optional[List[IntentSignal]] = None,
) -> Dict[str, List[StagedWrite]]:
    # ... existing assembly

    # Intent signal writes (if R5 provided signals)
    if intent_signals:
        signal_assembler = IntentSignalAssembler(
            self.tenant_id, self.space_id, self.actor_id
        )
        signal_writes = signal_assembler.assemble_all(intent_signals)
        for layer, writes in signal_writes.items():
            if layer in result:
                result[layer].extend(writes)
            else:
                result[layer] = writes
```

---

### Phase 5: R7 Layer Writer Updates (1 day)

#### Issue 5.1: Update ProspectiveLayerWriter for REMINDER/DECISION

**File**: `k0/modules/consolidation/truth_writer/layers/prospective.py` (MODIFY)

- Handle `intention_type = "REMINDER"` writes with target_date
- Handle `intention_type = "DECISION"` writes with decision_context
- Validate intention_type against extended CHECK constraint

#### Issue 5.2: Update SemanticLayerWriter for LESSON/EMOTIONAL_TREND

**File**: `k0/modules/consolidation/truth_writer/layers/semantic.py` (MODIFY)

- Handle `pattern_type = "LESSON"` writes
- Handle `pattern_type = "EMOTIONAL_TREND"` writes
- Include source intent in pattern_attributes_json

#### Issue 5.3: Update KGLayerWriter for Query Tracking

**File**: `k0/modules/consolidation/truth_writer/layers/kg.py` (MODIFY)

- Handle INCREMENT operations for query_count
- Handle milestone_json updates for share_news
- Handle sentiment_avg updates on edges for express_feeling

---

### Phase 6: Temporal Parser (0.5 day)

#### Issue 6.1: Create TemporalParser Module

**File**: `k0/modules/consolidation/algorithms/temporal_parser.py` (NEW)

**Purpose**: Convert UltraBERT temporal head output to Unix timestamps.

**Important**: This does NOT re-extract temporal expressions. UltraBERT already extracted them in P02 and stored them in `st_hipp_events.temporal_json`. This parser CONVERTS those labeled entities to actual Unix ms timestamps for `st_prospective.target_date`.

```python
"""
TemporalParser — Convert UltraBERT temporal_json to Unix timestamps.

UltraBERT Temporal Head (P02) provides labeled entities like:
    {"entities": [{"text": "tomorrow at 3pm", "label": "TIME"}]}

This parser converts those text labels into Unix millisecond timestamps
for storage in st_prospective.target_date.

Handles relative dates (tomorrow, next week) and absolute dates.
Does NOT re-run NER - uses existing UltraBERT output from st_hipp_events.
"""
import json
from datetime import datetime, timedelta
from typing import Optional


class TemporalParser:
    """Parses temporal expressions to Unix ms timestamps."""

    def parse_temporal_json(
        self,
        temporal_json: str,
        reference_time: Optional[int] = None,
    ) -> Optional[int]:
        """
        Parse temporal_json and return target timestamp.

        Args:
            temporal_json: JSON string from st_hipp_events.temporal_json
            reference_time: Reference time in ms (default: now)

        Returns:
            Unix ms timestamp or None if no parseable date
        """
        if not temporal_json:
            return None

        try:
            data = json.loads(temporal_json)
        except json.JSONDecodeError:
            return None

        # UltraBERT temporal format: {"entities": [{"text": "tomorrow", "label": "DATE_REL"}]}
        entities = data.get("entities", [])
        if not entities:
            return None

        # Find first temporal entity
        for entity in entities:
            label = entity.get("label", "")
            text = entity.get("text", "")

            if label in ("DATE_REL", "TIME_REL", "DATE_ABS", "TIME_ABS"):
                return self._parse_temporal_text(text, reference_time)

        return None

    def _parse_temporal_text(self, text: str, ref_time: Optional[int]) -> Optional[int]:
        """Parse natural language temporal expression."""
        ref = datetime.fromtimestamp((ref_time or int(datetime.now().timestamp() * 1000)) / 1000)
        text_lower = text.lower().strip()

        # Relative date patterns
        if "tomorrow" in text_lower:
            target = ref + timedelta(days=1)
            return self._apply_time(target, text_lower)
        elif "next week" in text_lower:
            target = ref + timedelta(weeks=1)
            return int(target.timestamp() * 1000)
        elif "in an hour" in text_lower:
            target = ref + timedelta(hours=1)
            return int(target.timestamp() * 1000)
        # ... more patterns

        return None

    def _apply_time(self, date: datetime, text: str) -> int:
        """Apply time component if specified."""
        import re
        # Extract time like "3pm", "15:00"
        time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', text, re.I)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2) or 0)
            meridiem = time_match.group(3)

            if meridiem and meridiem.lower() == 'pm' and hour < 12:
                hour += 12
            elif meridiem and meridiem.lower() == 'am' and hour == 12:
                hour = 0

            date = date.replace(hour=hour, minute=minute, second=0)

        return int(date.timestamp() * 1000)
```

---

### Phase 7: Integration Tests (1 day)

#### Issue 7.1: E2E Test: set_reminder → st_prospective REMINDER

```python
def test_set_reminder_creates_prospective_reminder():
    """set_reminder intent creates st_prospective REMINDER record."""
    # Setup event with intent_category = "set_reminder"
    event = create_event(
        text="Remind me to call Mom tomorrow at 3pm",
        intent_category="set_reminder",
        temporal_json='{"entities": [{"text": "tomorrow at 3pm", "label": "TIME"}]}',
    )

    # Run P03 consolidation
    result = await run_p03_cycle([event])

    # Verify st_prospective record created
    prosp = await db.fetch_one(
        "SELECT * FROM st_prospective WHERE intention_type = 'REMINDER'"
    )
    assert prosp is not None
    assert "call Mom" in prosp["intention_description"].lower()
    assert prosp["target_date"] is not None
    assert prosp["status"] == "ACTIVE"
```

#### Issue 7.2: E2E Test: seek_advice → st_prospective DECISION

#### Issue 7.3: E2E Test: reflect → st_sem LESSON

#### Issue 7.4: E2E Test: express_feeling → st_sem EMOTIONAL_TREND

#### Issue 7.5: E2E Test: share_news → st_kg_dom milestone

#### Issue 7.6: E2E Test: query_memory → query_count increment

---

## 5. File Summary

### New Files (8)

| File | Purpose |
|------|---------|
| `k0/db/alembic/versions/0060_st_prospective_intent_types.py` | Extend intention_type CHECK |
| `k0/db/alembic/versions/0061_st_sem_pattern_types.py` | Add LESSON, EMOTIONAL_TREND, INSIGHT |
| `k0/db/alembic/versions/0062_kg_query_tracking.py` | Add query_count, milestones_json |
| `k0/modules/consolidation/dream/intent_signals.py` | IntentSignal dataclasses |
| `k0/modules/consolidation/algorithms/intent_signal_detector.py` | Detect signals from events |
| `k0/modules/consolidation/algorithms/temporal_parser.py` | Parse temporal_json to timestamps |
| `k0/modules/consolidation/staging/intent_signal_assembler.py` | Route signals to writes |
| `contracts/policy/intent_routing.yaml` | Configurable routing rules |

### Modified Files (8)

| File | Changes |
|------|---------|
| `k0/modules/consolidation/dream/models.py` | Add intent_signals to DreamExplorerOutput |
| `k0/modules/consolidation/dream/dream_explorer.py` | Call IntentSignalDetector |
| `k0/pipelines/p03/phases/r5_dream_explorer.py` | Pass intent_signals to R6 |
| `k0/modules/consolidation/staging/r6_coordinator.py` | Route intent signals to writes |
| `k0/modules/consolidation/staging/truth_write_assembler.py` | Add intent_signals parameter |
| `k0/modules/consolidation/truth_writer/layers/prospective.py` | Handle REMINDER, DECISION |
| `k0/modules/consolidation/truth_writer/layers/semantic.py` | Handle LESSON, EMOTIONAL_TREND |
| `k0/modules/consolidation/truth_writer/layers/kg.py` | Handle query_count, milestones |

### Test Files (6)

| File | Coverage |
|------|----------|
| `tests/k0/modules/consolidation/algorithms/test_intent_signal_detector.py` | Unit tests |
| `tests/k0/modules/consolidation/algorithms/test_temporal_parser.py` | Unit tests |
| `tests/k0/modules/consolidation/staging/test_intent_signal_assembler.py` | Unit tests |
| `tests/k0/pipelines/p03/integration/test_intent_routing_e2e.py` | E2E tests |
| `tests/k0/modules/consolidation/truth_writer/test_prospective_intent.py` | Layer tests |
| `tests/k0/modules/consolidation/truth_writer/test_semantic_intent.py` | Layer tests |

---

## 6. Implementation Order

```
Phase 1: Schema Migrations (0.5 day)
    └── Must be first - other phases depend on new columns

Phase 2: Intent Signal Detection (1 day)
    └── Core logic, no dependencies except models

Phase 6: Temporal Parser (0.5 day)
    └── Used by Phase 2, can run in parallel

Phase 3: R5 Integration (0.5 day)
    └── Depends on Phase 2

Phase 4: R6 Intent Routing (1 day)
    └── Depends on Phase 2, 3

Phase 5: R7 Layer Writer Updates (1 day)
    └── Depends on Phase 1, 4

Phase 7: Integration Tests (1 day)
    └── Depends on all previous phases
```

---

## 7. ADR Requirements

Before implementation, these ADRs should be created:

1. **ADR-K0XX: Intent Signal Detection in P03**
   - Where to detect: R5 ForwardSimulator vs R6 inline
   - Decision: R5 preferred, R6 fallback if R5 blocked

2. **ADR-K0XX: Intent Routing Policy Configuration**
   - Hardcoded vs YAML-driven routing
   - Decision: YAML-driven for flexibility

3. **ADR-K0XX: Temporal Parsing Strategy**
   - Use dateparser library vs custom parsing
   - Decision: Custom for control, add dateparser later

---

## 8. Rollout Strategy

1. **Feature flag**: `P03_INTENT_ROUTING_ENABLED` (default: false)
2. **Gradual rollout**:
   - Week 1: Enable for `set_reminder` only
   - Week 2: Enable for `seek_advice`, `reflect`
   - Week 3: Enable remaining intents
3. **Metrics to monitor**:
   - `p03_intent_signals_detected` counter by signal_type
   - `p03_intent_writes_created` counter by layer
   - `p03_temporal_parse_success_rate` gauge
   - `st_prospective_reminder_count` gauge

---

## 9. Success Criteria

- [ ] Events with `intent_category="set_reminder"` create st_prospective REMINDER records
- [ ] Temporal expressions parsed to target_date with >80% accuracy
- [ ] Events with `intent_category="reflect"` create st_sem LESSON patterns
- [ ] Events with `intent_category="express_feeling"` create st_sem EMOTIONAL_TREND
- [ ] Events with `intent_category="seek_advice"` create st_prospective DECISION
- [ ] Events with `intent_category="share_news"` update st_kg_dom milestones_json
- [ ] Events with `intent_category="query_memory"` increment query_count on matched entities
- [ ] All intent routing is configurable via policy YAML
- [ ] Integration tests pass for all 8 intent types
- [ ] P05 can trigger reminders at target_date
