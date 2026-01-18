# Milestone 7: Intent-Aware Prospective Writer — set_reminder → st_prospective

> **GAP Reference**: [GAP_001_CROSS_LAYER_VECTOR_LINKING.md](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md) Section 8.3
> **Effort**: 1 day
> **Priority**: P1 (Important)
> **Dependencies**: Milestone 3 (R7 Writer Updates)
> **Status**: ✅ COMPLETE (2026-01-15)

## Completion Summary

**All 5 issues are ALREADY IMPLEMENTED.** This milestone was completed as part of the
Intent Ingress Matrix implementation.

| Issue | Description | Implementation |
|-------|-------------|----------------|
| 7.1 | ReminderIntentDetector | `IntentSignalDetector` in `k0/modules/consolidation/algorithms/intent_signal_detector.py` |
| 7.2 | R5 ForwardSimulator | `DreamExplorer.explore()` Phase 4 calls `IntentSignalDetector.detect_all()` |
| 7.3 | ProspectiveLayerWriter | `k0/modules/consolidation/truth_writer/layers/prospective.py` |
| 7.4 | TruthWriteAssembler | `IntentSignalAssembler._assemble_reminder()` in `k0/modules/consolidation/staging/intent_signal_assembler.py` |
| 7.5 | Integration Tests | `tests/k0/pipelines/p03/integration/test_intent_ingress_matrix_e2e.py` - **30 tests passing** |

### Key Implementation Details

1. **IntentSignalDetector** routes `intent_label="set_reminder"` → `ReminderSignal`
2. **IntentSignalAssembler** routes `ReminderSignal` → `st_prospective` INSERT with `intention_type='REMINDER'`
3. **R6 Coordinator** STEP 2.5 calls `intent_signal_assembler.assemble_all(r5_intent_signals)`

---

---

## Overview

Update P03 consolidation to route events with `intent_category = "set_reminder"` to st_prospective:

1. **R5 ForwardSimulator**: Detect reminder intents in event batch
2. **Parse temporal_json**: Extract target_date from UltraBERT temporal output
3. **R7 ProspectiveLayerWriter**: Create st_prospective record with `intention_type = "REMINDER"`
4. **P05 Integration**: Enable prospective triggers to fire at target_date

---

## Epic: Intent-to-Prospective Routing for Reminders

### Architecture

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    SET_REMINDER → ST_PROSPECTIVE FLOW                            │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   User: "Remind me to call Mom tomorrow at 3pm"                                 │
│                          │                                                       │
│                          ▼                                                       │
│   ┌───────────────────────────────────────────────────────────────────────┐     │
│   │                   P02: Write Event                                     │     │
│   │   UltraBERT output stored in st_hipp_events:                          │     │
│   │   • intent_category = "set_reminder"                                   │     │
│   │   • temporal_json = [{"text": "tomorrow at 3pm", "label": "TIME"}]    │     │
│   │   • text = "Remind me to call Mom tomorrow at 3pm"                    │     │
│   └───────────────────────────────────────────────────────────────────────┘     │
│                          │                                                       │
│                          ▼                                                       │
│   ┌───────────────────────────────────────────────────────────────────────┐     │
│   │                   P03 R0: Batch Selector                               │     │
│   │   Selects events for consolidation (READY status, >24h old)           │     │
│   └───────────────────────────────────────────────────────────────────────┘     │
│                          │                                                       │
│                          ▼                                                       │
│   ┌───────────────────────────────────────────────────────────────────────┐     │
│   │                   P03 R5: Forward Simulator (UPDATED)                  │     │
│   │                                                                        │     │
│   │   NEW: Detect intent_category = "set_reminder"                        │     │
│   │   → Flag batch for prospective extraction                              │     │
│   │   → Parse temporal_json for target_date                                │     │
│   │   → Extract action description from text                               │     │
│   └───────────────────────────────────────────────────────────────────────┘     │
│                          │                                                       │
│                          ▼                                                       │
│   ┌───────────────────────────────────────────────────────────────────────┐     │
│   │                   P03 R7: ProspectiveLayerWriter (UPDATED)             │     │
│   │                                                                        │     │
│   │   CREATE st_prospective record:                                        │     │
│   │   • intention_id = generate_id()                                       │     │
│   │   • intention_type = "REMINDER"                                        │     │
│   │   • intention_description = "Call Mom"                                 │     │
│   │   • target_date = parsed_timestamp                                     │     │
│   │   • target_context = original text                                     │     │
│   │   • source_event_ids = [event_id]                                      │     │
│   │   • source_texts_json = [original text]                                │     │
│   └───────────────────────────────────────────────────────────────────────┘     │
│                          │                                                       │
│                          ▼                                                       │
│   ┌───────────────────────────────────────────────────────────────────────┐     │
│   │                   P05: Prospective Triggers                            │     │
│   │                                                                        │     │
│   │   Periodic job scans st_prospective:                                   │     │
│   │   WHERE target_date <= NOW()                                           │     │
│   │     AND status = 'PENDING'                                             │     │
│   │                                                                        │     │
│   │   → Emit reminder event to K1                                          │     │
│   └───────────────────────────────────────────────────────────────────────┘     │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Issues

### Issue 7.1: Create ReminderIntentDetector Service

**Priority**: P0
**Effort**: 2 hours

**Description**:
Create a service that detects reminder intents in event batches and extracts action + target_date.

**Files to Create**:

- `k0/modules/consolidation/algorithms/reminder_intent_detector.py` (NEW)

**Code Structure**:

```python
"""
ReminderIntentDetector — GAP-001 Implementation

Detects set_reminder intents in event batches and extracts:
- Action description (what to remind about)
- Target date/time (when to remind)

GAP Reference: GAP_001 Section 8.3 (set_reminder Gap)
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional


@dataclass
class ReminderExtraction:
    """Extracted reminder information from an event."""
    event_id: str
    action_description: str      # "Call Mom"
    target_date: Optional[int]   # Unix timestamp (ms)
    target_context: str          # Original text
    confidence: float            # Extraction confidence
    temporal_source: str         # "temporal_json" or "inferred"


class ReminderIntentDetector:
    """Detects and extracts reminder intents from events."""

    # Patterns to extract action from text
    ACTION_PATTERNS = [
        r"remind me to (.+?)(?:\s+(?:at|on|in|by|tomorrow|next)\s+|$)",
        r"reminder[:\s]+(.+?)(?:\s+(?:at|on|in|by)\s+|$)",
        r"don't forget to (.+?)(?:\s+(?:at|on|in|by)\s+|$)",
    ]

    def detect_reminders(
        self,
        events: List[Dict[str, Any]],
    ) -> List[ReminderExtraction]:
        """
        Scan event batch for reminder intents.

        Args:
            events: List of event dicts with intent_category, temporal_json, text

        Returns:
            List of ReminderExtraction for events with set_reminder intent
        """
        reminders = []
        for event in events:
            if event.get("intent_category") == "set_reminder":
                extraction = self._extract_reminder(event)
                if extraction:
                    reminders.append(extraction)
        return reminders

    def _extract_reminder(self, event: Dict[str, Any]) -> Optional[ReminderExtraction]:
        """Extract reminder details from a single event."""
        event_id = event.get("event_id", "")
        text = event.get("text", "")
        temporal_json = event.get("temporal_json", "[]")

        # Extract action description
        action = self._extract_action(text)
        if not action:
            action = text  # Fallback to full text

        # Parse target date from temporal_json
        target_date, temporal_source = self._parse_target_date(temporal_json)

        return ReminderExtraction(
            event_id=event_id,
            action_description=action,
            target_date=target_date,
            target_context=text,
            confidence=0.85 if target_date else 0.60,
            temporal_source=temporal_source,
        )

    def _extract_action(self, text: str) -> Optional[str]:
        """Extract the action to remind about."""
        text_lower = text.lower()
        for pattern in self.ACTION_PATTERNS:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _parse_target_date(
        self,
        temporal_json: str,
    ) -> tuple[Optional[int], str]:
        """
        Parse target date from UltraBERT temporal_json.

        Returns:
            (target_timestamp_ms, source) or (None, "none")
        """
        try:
            temporals = json.loads(temporal_json) if temporal_json else []
        except json.JSONDecodeError:
            return None, "none"

        for temp in temporals:
            label = temp.get("label", "")
            text = temp.get("text", "")

            # Look for TIME or DATE_REL expressions
            if label in ("TIME", "DATE_REL", "DATE_ABS"):
                parsed = self._parse_temporal_text(text)
                if parsed:
                    return parsed, "temporal_json"

        return None, "none"

    def _parse_temporal_text(self, text: str) -> Optional[int]:
        """Parse temporal text like 'tomorrow at 3pm' to timestamp."""
        # Simplified parsing - production would use dateparser
        now = datetime.utcnow()
        text_lower = text.lower()

        if "tomorrow" in text_lower:
            base = now + timedelta(days=1)
        elif "next week" in text_lower:
            base = now + timedelta(weeks=1)
        else:
            base = now + timedelta(hours=1)  # Default: 1 hour from now

        # Extract time if present (e.g., "3pm", "15:00")
        time_match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text_lower)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2) or 0)
            meridiem = time_match.group(3)

            if meridiem == "pm" and hour < 12:
                hour += 12
            elif meridiem == "am" and hour == 12:
                hour = 0

            base = base.replace(hour=hour, minute=minute, second=0, microsecond=0)

        return int(base.timestamp() * 1000)  # Return ms timestamp
```

**References**:

- GAP Section 8.3: [set_reminder Gap](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#83-gap-set_reminder-intent-not-creating-st_prospective-records)
- UltraBERT temporal output: [temporal_json schema](../../k0/db/alembic/versions/0046_st_hipp_events_p02_ner_columns.py)
- st_prospective schema: [0031_st_prospective.py](../../k0/db/alembic/versions/0031_st_prospective.py)

**Acceptance Criteria**:

- [ ] Detects events with intent_category = "set_reminder"
- [ ] Extracts action description from text
- [ ] Parses target_date from temporal_json
- [ ] Handles missing/malformed temporal data gracefully
- [ ] Unit tests for all extraction patterns

---

### Issue 7.2: Update R5 ForwardSimulator for Reminder Detection

**Priority**: P0
**Effort**: 2 hours

**Description**:
Update R5 ForwardSimulator to detect reminder intents and flag batches for prospective extraction.

**Files to Modify**:

- `k0/modules/consolidation/algorithms/forward_simulator.py` (MODIFY)

**Changes Required**:

```python
# Add to ForwardSimulator class

from k0.modules.consolidation.algorithms.reminder_intent_detector import (
    ReminderIntentDetector,
    ReminderExtraction,
)


class ForwardSimulator:
    def __init__(self):
        # ... existing init ...
        self.reminder_detector = ReminderIntentDetector()

    def simulate(self, event_batch: List[Dict]) -> SimulationResult:
        """
        Run forward simulation on event batch.

        UPDATED: Now includes reminder intent detection.
        """
        # ... existing simulation logic ...

        # NEW: Detect reminder intents
        reminders = self.reminder_detector.detect_reminders(event_batch)

        return SimulationResult(
            # ... existing fields ...
            reminder_extractions=reminders,  # NEW
        )
```

**References**:

- R5 Deep Dive: [Forward Simulation](../pipelines/R5_FORWARD_SIMULATOR_DEEP_DIVE.md)
- GAP Section 8.4: [Intent-Aware R5/R7 Processing](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#84-solution-intent-aware-r5r7-processing)

**Acceptance Criteria**:

- [ ] ForwardSimulator detects set_reminder intents
- [ ] Returns ReminderExtraction list in result
- [ ] Does not break existing simulation logic
- [ ] Integration test with reminder events

---

### Issue 7.3: Update R7 ProspectiveLayerWriter for Reminder Creation

**Priority**: P0
**Effort**: 3 hours

**Description**:
Update ProspectiveLayerWriter to create st_prospective records from reminder extractions.

**Files to Modify**:

- `k0/modules/consolidation/truth_writer/layers/prospective.py` (MODIFY)

**Changes Required**:

```python
# Add to ProspectiveLayerWriter class

async def write_reminder(
    self,
    extraction: ReminderExtraction,
    source_texts: List[str],
    conn,
) -> str:
    """
    Create st_prospective record from reminder extraction.

    Args:
        extraction: ReminderExtraction from R5
        source_texts: Original event texts (for source_texts_json)
        conn: Database connection

    Returns:
        intention_id of created record
    """
    intention_id = generate_intention_id()

    await conn.execute(
        """
        INSERT INTO st_prospective (
            intention_id,
            tenant_id,
            space_id,
            actor_id,
            intention_type,
            intention_description,
            target_date,
            target_context,
            source_events_json,
            source_texts_json,
            status,
            priority,
            confidence_score,
            created_at,
            updated_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15
        )
        """,
        intention_id,
        self.tenant_id,
        self.space_id,
        self.actor_id,
        "REMINDER",  # intention_type
        extraction.action_description,
        extraction.target_date,
        extraction.target_context,
        json.dumps([extraction.event_id]),
        json.dumps(source_texts),
        "PENDING",  # status
        5,  # priority (default medium)
        extraction.confidence,
        now_ms(),
        now_ms(),
    )

    return intention_id
```

**References**:

- ProspectiveLayerWriter: [prospective.py](../../k0/modules/consolidation/truth_writer/layers/prospective.py)
- st_prospective schema: [0031_st_prospective.py](../../k0/db/alembic/versions/0031_st_prospective.py)
- P03 Dossier Section 6.7: [st_prospective Schema](../pipelines/P03_consolidation_dossier_v2.md#67-st_prospective-intentions--goals)

**Acceptance Criteria**:

- [ ] Creates st_prospective record with intention_type = "REMINDER"
- [ ] Stores action_description, target_date, target_context
- [ ] Preserves source_texts_json for text preservation
- [ ] Sets status = "PENDING" for P05 consumption
- [ ] Integration test verifying record creation

---

### Issue 7.4: Update TruthWriteAssembler for Reminder Flow

**Priority**: P0
**Effort**: 2 hours

**Description**:
Update TruthWriteAssembler to call ProspectiveLayerWriter for reminder extractions from R5.

**Files to Modify**:

- `k0/modules/consolidation/staging/truth_write_assembler.py` (MODIFY)

**Changes Required**:

```python
# Add to TruthWriteAssembler.assemble() method

async def assemble(self, batch: ConsolidationBatch, conn) -> AssemblyResult:
    """
    Assemble and write truth layer records.

    UPDATED: Now includes reminder → st_prospective routing.
    """
    # ... existing assembly logic ...

    # NEW: Handle reminder extractions from R5
    if batch.simulation_result.reminder_extractions:
        for extraction in batch.simulation_result.reminder_extractions:
            # Fetch source texts before decay
            source_texts = await self.source_text_fetcher.fetch_for_events(
                [extraction.event_id], conn
            )

            # Create st_prospective record
            intention_id = await self.prospective_writer.write_reminder(
                extraction=extraction,
                source_texts=source_texts.texts,
                conn=conn,
            )

            result.prospective_ids.append(intention_id)

    return result
```

**References**:

- TruthWriteAssembler: [truth_write_assembler.py](../../k0/modules/consolidation/staging/truth_write_assembler.py)
- Milestone 3 Issue 3.1: [SourceTextFetcher](../plans_completed_donotrefer/GAP_001_MILESTONE_3_R7_WRITER_UPDATES.md#issue-31-create-sourcetextfetcher-service)

**Acceptance Criteria**:

- [ ] Detects reminder_extractions in R5 result
- [ ] Fetches source texts using SourceTextFetcher
- [ ] Calls ProspectiveLayerWriter.write_reminder()
- [ ] Returns intention_ids in AssemblyResult
- [ ] End-to-end test: event → st_prospective

---

### Issue 7.5: Create Integration Test for Reminder Flow

**Priority**: P0
**Effort**: 2 hours

**Description**:
Create end-to-end integration test verifying reminder events flow through to st_prospective.

**Files to Create**:

- `tests/k0/pipelines/p03/integration/test_reminder_to_prospective.py` (NEW)

**Test Cases**:

```python
"""
Integration tests for set_reminder → st_prospective flow.

GAP Reference: GAP_001 Section 8.3
"""

import pytest
from datetime import datetime, timedelta


class TestReminderToProspective:
    """Test complete reminder flow: P02 event → P03 → st_prospective."""

    @pytest.mark.asyncio
    async def test_simple_reminder_creates_prospective(self, p03_test_env):
        """Basic reminder with explicit time creates st_prospective record."""
        # Arrange: Create event with set_reminder intent
        event = create_test_event(
            text="Remind me to call Mom tomorrow at 3pm",
            intent_category="set_reminder",
            temporal_json='[{"text": "tomorrow at 3pm", "label": "TIME"}]',
        )

        # Act: Run P03 consolidation
        await p03_test_env.run_consolidation([event])

        # Assert: st_prospective record created
        intention = await p03_test_env.fetch_prospective(event.event_id)
        assert intention is not None
        assert intention["intention_type"] == "REMINDER"
        assert intention["intention_description"] == "call Mom"
        assert intention["target_date"] is not None
        assert intention["status"] == "PENDING"

    @pytest.mark.asyncio
    async def test_reminder_without_time_uses_default(self, p03_test_env):
        """Reminder without explicit time uses default (1 hour)."""
        event = create_test_event(
            text="Remind me to buy groceries",
            intent_category="set_reminder",
            temporal_json="[]",  # No temporal data
        )

        await p03_test_env.run_consolidation([event])

        intention = await p03_test_env.fetch_prospective(event.event_id)
        assert intention is not None
        # Should have target_date ~1 hour from now
        assert intention["target_date"] is not None

    @pytest.mark.asyncio
    async def test_non_reminder_intent_no_prospective(self, p03_test_env):
        """Non-reminder intents should not create st_prospective."""
        event = create_test_event(
            text="I had dinner with Mom yesterday",
            intent_category="log_memory",  # Not set_reminder
        )

        await p03_test_env.run_consolidation([event])

        intention = await p03_test_env.fetch_prospective(event.event_id)
        assert intention is None  # No prospective record

    @pytest.mark.asyncio
    async def test_reminder_preserves_source_texts(self, p03_test_env):
        """Reminder record includes source_texts_json."""
        event = create_test_event(
            text="Remind me to call Mom tomorrow at 3pm",
            intent_category="set_reminder",
        )

        await p03_test_env.run_consolidation([event])

        intention = await p03_test_env.fetch_prospective(event.event_id)
        source_texts = json.loads(intention["source_texts_json"])
        assert len(source_texts) == 1
        assert "call Mom" in source_texts[0]
```

**Acceptance Criteria**:

- [ ] Tests pass with real P03 pipeline execution
- [ ] Covers: with time, without time, non-reminder intent
- [ ] Verifies source_texts_json preservation
- [ ] Verifies intention_type = "REMINDER"

---

## Summary

| Issue | Description | Effort |
| ----- | ----------- | ------ |
| 7.1 | ReminderIntentDetector service | 2 hours |
| 7.2 | R5 ForwardSimulator update | 2 hours |
| 7.3 | R7 ProspectiveLayerWriter update | 3 hours |
| 7.4 | TruthWriteAssembler update | 2 hours |
| 7.5 | Integration tests | 2 hours |
| **Total** | | **11 hours (~1.5 days)** |

---

## Dependencies

- **Milestone 3**: SourceTextFetcher for fetching source texts
- **st_prospective schema**: Already exists (migration 0031)
- **UltraBERT intent/temporal**: Already stored in st_hipp_events (migrations 0046, 0053)

---

## References

- [GAP_001 Section 8](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#8-ultrabert-capability-utilization-analysis)
- [P03 Dossier Section 6.7](../pipelines/P03_consolidation_dossier_v2.md#67-st_prospective-intentions--goals)
- [0031_st_prospective.py](../../k0/db/alembic/versions/0031_st_prospective.py)
- [0046_st_hipp_events_p02_ner_columns.py](../../k0/db/alembic/versions/0046_st_hipp_events_p02_ner_columns.py)
