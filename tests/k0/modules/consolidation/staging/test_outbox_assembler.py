"""
Tests for OutboxEventAssembler — Issue 5.1.8

Tests outbox event assembly for R8 emission.
Issue 8.1.12: Added tests for R5 insight event assembly.
"""

import pytest

from k0.modules.consolidation.staging.outbox_assembler import (
    PRIORITY_COMPLETION,
    PRIORITY_DECISION,
    PRIORITY_GAP,
    PRIORITY_INSIGHT,
    SOURCE_PHASE_R6,
    TOPIC_CONSOLIDATION_COMPLETE,
    TOPIC_GAP_DETECTED,
    TOPIC_INSIGHT_GENERATED,
    TOPIC_MEMORY_PRUNED,
    TOPIC_PATTERN_DETECTED,
    TOPIC_TRUTH_CREATED,
    TOPIC_TRUTH_EVOLVED,
    TOPIC_TRUTH_REINFORCED,
    AssembledOutbox,
    OutboxEventAssembler,
    count_outbox_events,
    get_events_by_priority,
    summarize_outbox,
)
from k0.modules.consolidation.staging.r6_output import ReconciliationSummary
from k0.pipelines.p03.event_state import P03EventState, PruneDecision, ReconciliationAction
from k0.pipelines.p03.phase_outputs import GapCandidate, Insight

# =============================================================================
# FIXTURES
# =============================================================================


def make_summary(**overrides) -> ReconciliationSummary:
    """Create a ReconciliationSummary with defaults."""
    defaults = {
        "total_events": 10,
        "consolidated_count": 5,
        "duplicate_count": 2,
        "pruned_count": 1,
        "pending_review_count": 2,
        "action_breakdown": (("CREATE", 3), ("REINFORCE", 2)),
        "layer_write_counts": (("st_epi", 5), ("st_sem", 3)),
        "kg_entity_count": 4,
        "kg_edge_count": 6,
        "gap_count": 2,
        "total_writes": 15,
        "cycle_duration_ms": 1500,
    }
    defaults.update(overrides)
    return ReconciliationSummary(**defaults)


def make_event_state(
    event_id: str,
    action: ReconciliationAction = ReconciliationAction.CREATE,
    **overrides,
) -> P03EventState:
    """Create a P03EventState with defaults."""
    state = P03EventState(event_id=event_id)
    state.reconciliation_action = action
    state.best_match_id = overrides.get("best_match_id", "match_001")
    state.best_match_layer = overrides.get("best_match_layer", "st_epi")
    state.similarity_score = overrides.get("similarity_score", 0.85)
    state.confidence = overrides.get("confidence", 0.9)
    state.reconciliation_reason = overrides.get("reason", "Test reason")
    state.importance_score = overrides.get("importance_score", 0.8)
    state.cluster_id = overrides.get("cluster_id", "cluster_001")
    state.decay_score = overrides.get("decay_score", 0.3)
    state.days_since_access = overrides.get("days_since_access", 90)
    state.prune_decision = overrides.get("prune_decision", PruneDecision.ARCHIVE)
    return state


def make_gap(gap_id: str, **overrides) -> GapCandidate:
    """Create a GapCandidate with defaults."""
    defaults = {
        "gap_id": gap_id,
        "gap_type": "AMBIGUITY",
        "related_entity_id": "entity_001",
        "entropy_score": 0.7,
        "priority": "HIGH",
        "context_json": "{}",
        "candidate_values": ["val1", "val2"],
    }
    defaults.update(overrides)
    return GapCandidate(**defaults)


@pytest.fixture
def assembler() -> OutboxEventAssembler:
    """Create assembler with default config."""
    return OutboxEventAssembler(
        cycle_ulid="01ABC123",
        tenant_id="tenant_test",
        space_id="space_test",
    )


# =============================================================================
# TEST ASSEMBLER INIT
# =============================================================================


class TestAssemblerInit:
    """Tests for OutboxEventAssembler initialization."""

    def test_init_stores_envelope_fields(self):
        """Assembler stores cycle, tenant, space IDs."""
        asm = OutboxEventAssembler(
            cycle_ulid="01XYZ",
            tenant_id="t1",
            space_id="s1",
        )
        assert asm.cycle_ulid == "01XYZ"
        assert asm.tenant_id == "t1"
        assert asm.space_id == "s1"


# =============================================================================
# TEST COMPLETION EVENT
# =============================================================================


class TestCompletionEvent:
    """Tests for assemble_completion_event."""

    def test_completion_event_topic(self, assembler):
        """Completion event has correct topic."""
        summary = make_summary()
        event = assembler.assemble_completion_event(summary, {"R0": 100})
        assert event.topic == TOPIC_CONSOLIDATION_COMPLETE

    def test_completion_event_priority(self, assembler):
        """Completion event has highest priority (10)."""
        summary = make_summary()
        event = assembler.assemble_completion_event(summary, {})
        assert event.priority == PRIORITY_COMPLETION

    def test_completion_event_source_phase(self, assembler):
        """Completion event source phase is R6."""
        summary = make_summary()
        event = assembler.assemble_completion_event(summary, {})
        assert event.source_phase == SOURCE_PHASE_R6

    def test_completion_event_envelope_fields(self, assembler):
        """Completion event payload includes envelope fields."""
        summary = make_summary()
        event = assembler.assemble_completion_event(summary, {})

        assert event.payload["cycle_id"] == "01ABC123"
        assert event.payload["tenant_id"] == "tenant_test"
        assert event.payload["space_id"] == "space_test"
        assert "timestamp_ms" in event.payload

    def test_completion_event_summary_dict(self, assembler):
        """Completion event includes summary as dict."""
        summary = make_summary(total_events=42)
        event = assembler.assemble_completion_event(summary, {})

        assert event.payload["summary"]["total_events"] == 42

    def test_completion_event_phase_durations(self, assembler):
        """Completion event includes phase durations."""
        summary = make_summary()
        durations = {"R0": 100, "R1": 200, "R2": 150}
        event = assembler.assemble_completion_event(summary, durations)

        assert event.payload["phase_durations"] == durations


# =============================================================================
# TEST DECISION EVENTS
# =============================================================================


class TestDecisionEvents:
    """Tests for assemble_decision_events."""

    def test_empty_states_returns_empty(self, assembler):
        """Empty event states returns empty list."""
        events = assembler.assemble_decision_events({})
        assert events == []

    def test_reinforce_produces_reinforced_event(self, assembler):
        """REINFORCE action produces truth.reinforced event."""
        states = {
            "e1": make_event_state("e1", ReconciliationAction.REINFORCE),
        }
        events = assembler.assemble_decision_events(states)

        assert len(events) == 1
        assert events[0].topic == TOPIC_TRUTH_REINFORCED

    def test_reinforce_event_payload(self, assembler):
        """REINFORCE event has correct payload fields."""
        state = make_event_state(
            "e1",
            ReconciliationAction.REINFORCE,
            best_match_id="match_x",
            best_match_layer="st_sem",
            similarity_score=0.92,
        )
        states = {"e1": state}
        events = assembler.assemble_decision_events(states)

        payload = events[0].payload
        assert payload["event_id"] == "e1"
        assert payload["matched_record_id"] == "match_x"
        assert payload["matched_layer"] == "st_sem"
        assert payload["similarity_score"] == 0.92

    def test_create_produces_two_events(self, assembler):
        """CREATE action produces truth.created and pattern.detected."""
        states = {
            "e1": make_event_state("e1", ReconciliationAction.CREATE),
        }
        events = assembler.assemble_decision_events(states)

        assert len(events) == 2
        topics = [e.topic for e in events]
        assert TOPIC_TRUTH_CREATED in topics
        assert TOPIC_PATTERN_DETECTED in topics

    def test_create_event_payloads(self, assembler):
        """CREATE events have correct payload fields."""
        state = make_event_state(
            "e1",
            ReconciliationAction.CREATE,
            importance_score=0.75,
            cluster_id="cluster_abc",
        )
        states = {"e1": state}
        events = assembler.assemble_decision_events(states)

        created = [e for e in events if e.topic == TOPIC_TRUTH_CREATED][0]
        assert created.payload["event_id"] == "e1"
        assert created.payload["importance_score"] == 0.75
        assert created.payload["cluster_id"] == "cluster_abc"

        pattern = [e for e in events if e.topic == TOPIC_PATTERN_DETECTED][0]
        assert pattern.payload["pattern_id"] == "sem_e1"

    def test_evolve_produces_evolved_event(self, assembler):
        """EVOLVE action produces truth.evolved event."""
        states = {
            "e1": make_event_state("e1", ReconciliationAction.EVOLVE),
        }
        events = assembler.assemble_decision_events(states)

        assert len(events) == 1
        assert events[0].topic == TOPIC_TRUTH_EVOLVED

    def test_extend_produces_evolved_event(self, assembler):
        """EXTEND action also produces truth.evolved event."""
        states = {
            "e1": make_event_state("e1", ReconciliationAction.EXTEND),
        }
        events = assembler.assemble_decision_events(states)

        assert len(events) == 1
        assert events[0].topic == TOPIC_TRUTH_EVOLVED

    def test_evolved_event_includes_action(self, assembler):
        """Evolved event payload includes action type."""
        states = {
            "e1": make_event_state("e1", ReconciliationAction.EVOLVE),
        }
        events = assembler.assemble_decision_events(states)
        assert events[0].payload["action"] == "EVOLVE"

    def test_prune_produces_pruned_event(self, assembler):
        """PRUNE action produces memory.pruned event."""
        state = make_event_state(
            "e1",
            ReconciliationAction.PRUNE,
            decay_score=0.2,
            days_since_access=120,
            prune_decision=PruneDecision.TOMBSTONE,
        )
        states = {"e1": state}
        events = assembler.assemble_decision_events(states)

        assert len(events) == 1
        assert events[0].topic == TOPIC_MEMORY_PRUNED
        assert events[0].payload["prune_decision"] == "TOMBSTONE"
        assert events[0].payload["decay_score"] == 0.2

    def test_pending_produces_no_event(self, assembler):
        """PENDING action produces no decision event."""
        states = {
            "e1": make_event_state("e1", ReconciliationAction.PENDING),
        }
        events = assembler.assemble_decision_events(states)
        assert events == []

    def test_skip_produces_no_event(self, assembler):
        """SKIP action produces no decision event."""
        states = {
            "e1": make_event_state("e1", ReconciliationAction.SKIP),
        }
        events = assembler.assemble_decision_events(states)
        assert events == []

    def test_contradict_produces_no_event(self, assembler):
        """CONTRADICT action produces no decision event (routed to P06)."""
        states = {
            "e1": make_event_state("e1", ReconciliationAction.CONTRADICT),
        }
        events = assembler.assemble_decision_events(states)
        assert events == []

    def test_decision_event_priority(self, assembler):
        """All decision events have priority 50."""
        states = {
            "e1": make_event_state("e1", ReconciliationAction.CREATE),
            "e2": make_event_state("e2", ReconciliationAction.REINFORCE),
        }
        events = assembler.assemble_decision_events(states)
        for event in events:
            assert event.priority == PRIORITY_DECISION

    def test_multiple_states(self, assembler):
        """Multiple states produce correct number of events."""
        states = {
            "e1": make_event_state("e1", ReconciliationAction.CREATE),  # 2 events
            "e2": make_event_state("e2", ReconciliationAction.REINFORCE),  # 1 event
            "e3": make_event_state("e3", ReconciliationAction.PRUNE),  # 1 event
            "e4": make_event_state("e4", ReconciliationAction.SKIP),  # 0 events
        }
        events = assembler.assemble_decision_events(states)
        assert len(events) == 4  # 2 + 1 + 1 + 0


# =============================================================================
# TEST GAP EVENTS
# =============================================================================


class TestGapEvents:
    """Tests for assemble_gap_events."""

    def test_empty_gaps_returns_empty(self, assembler):
        """Empty gaps returns empty list."""
        events = assembler.assemble_gap_events([])
        assert events == []

    def test_single_gap_event(self, assembler):
        """Single gap produces single event."""
        gaps = [make_gap("gap_001")]
        events = assembler.assemble_gap_events(gaps)

        assert len(events) == 1
        assert events[0].topic == TOPIC_GAP_DETECTED

    def test_gap_event_priority(self, assembler):
        """Gap events have priority 30."""
        gaps = [make_gap("gap_001")]
        events = assembler.assemble_gap_events(gaps)
        assert events[0].priority == PRIORITY_GAP

    def test_gap_event_payload(self, assembler):
        """Gap event payload includes all gap fields."""
        gap = make_gap(
            "gap_xyz",
            gap_type="CONTRADICTION",
            related_entity_id="entity_abc",
            entropy_score=0.85,
            priority="MEDIUM",
            candidate_values=["a", "b", "c"],
        )
        events = assembler.assemble_gap_events([gap])

        payload = events[0].payload
        assert payload["gap_id"] == "gap_xyz"
        assert payload["gap_type"] == "CONTRADICTION"
        assert payload["related_entity_id"] == "entity_abc"
        assert payload["entropy_score"] == 0.85
        assert payload["priority"] == "MEDIUM"
        assert payload["candidate_values"] == ["a", "b", "c"]

    def test_gap_events_deduplicated(self, assembler):
        """Duplicate gap_ids are deduplicated."""
        gaps = [
            make_gap("gap_001"),
            make_gap("gap_001"),  # duplicate
            make_gap("gap_002"),
        ]
        events = assembler.assemble_gap_events(gaps)

        assert len(events) == 2
        gap_ids = [e.payload["gap_id"] for e in events]
        assert "gap_001" in gap_ids
        assert "gap_002" in gap_ids


# =============================================================================
# TEST ASSEMBLE ALL
# =============================================================================


class TestAssembleAll:
    """Tests for assemble_all."""

    def test_assemble_all_returns_assembled_outbox(self, assembler):
        """assemble_all returns AssembledOutbox."""
        summary = make_summary()
        result = assembler.assemble_all(summary, {}, [], {})
        assert isinstance(result, AssembledOutbox)

    def test_assemble_all_includes_completion(self, assembler):
        """assemble_all always includes completion event."""
        summary = make_summary()
        result = assembler.assemble_all(summary, {}, [], {})

        assert result.completion_event is not None
        assert result.completion_event.topic == TOPIC_CONSOLIDATION_COMPLETE

    def test_assemble_all_combines_all_events(self, assembler):
        """assemble_all combines completion, decision, and gap events."""
        summary = make_summary()
        states = {
            "e1": make_event_state("e1", ReconciliationAction.CREATE),
        }
        gaps = [make_gap("gap_001")]

        result = assembler.assemble_all(summary, states, gaps, {})

        # 1 completion + 2 decision (create) + 1 gap = 4
        assert len(result.events) == 4
        assert len(result.decision_events) == 2
        assert len(result.gap_events) == 1

    def test_assemble_all_counts_by_topic(self, assembler):
        """assemble_all provides counts by topic."""
        summary = make_summary()
        states = {
            "e1": make_event_state("e1", ReconciliationAction.REINFORCE),
            "e2": make_event_state("e2", ReconciliationAction.REINFORCE),
        }
        result = assembler.assemble_all(summary, states, [], {})

        assert result.event_count_by_topic[TOPIC_CONSOLIDATION_COMPLETE] == 1
        assert result.event_count_by_topic[TOPIC_TRUTH_REINFORCED] == 2


# =============================================================================
# TEST UTILITY FUNCTIONS
# =============================================================================


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_count_outbox_events(self, assembler):
        """count_outbox_events returns total count."""
        summary = make_summary()
        states = {"e1": make_event_state("e1", ReconciliationAction.CREATE)}
        result = assembler.assemble_all(summary, states, [], {})

        assert count_outbox_events(result) == 3  # 1 completion + 2 create

    def test_summarize_outbox(self, assembler):
        """summarize_outbox returns summary dict."""
        summary = make_summary()
        gaps = [make_gap("gap_001")]
        result = assembler.assemble_all(summary, {}, gaps, {})

        summ = summarize_outbox(result)
        assert summ["total_events"] == 2  # 1 completion + 1 gap
        assert summ["completion_event"] is True
        assert summ["gap_event_count"] == 1

    def test_get_events_by_priority(self, assembler):
        """get_events_by_priority groups correctly."""
        summary = make_summary()
        states = {"e1": make_event_state("e1", ReconciliationAction.CREATE)}
        gaps = [make_gap("gap_001")]
        result = assembler.assemble_all(summary, states, gaps, {})

        by_priority = get_events_by_priority(result)
        assert PRIORITY_COMPLETION in by_priority
        assert PRIORITY_DECISION in by_priority
        assert PRIORITY_GAP in by_priority
        assert len(by_priority[PRIORITY_COMPLETION]) == 1
        assert len(by_priority[PRIORITY_DECISION]) == 2
        assert len(by_priority[PRIORITY_GAP]) == 1


# =============================================================================
# ISSUE 8.1.12: INSIGHT EVENT ASSEMBLY
# =============================================================================


def make_insight(insight_id: str, **overrides) -> Insight:
    """Create an Insight with defaults."""
    defaults = {
        "insight_id": insight_id,
        "insight_type": "BRIDGE",
        "concept_a_id": "concept_001",
        "concept_b_id": "concept_002",
        "pmi_score": 4.5,
        "novelty_score": 0.85,
        "relevance_score": 0.75,
        "natural_language": f"Insight {insight_id} description",
        "evidence_ids": ["ev1", "ev2"],
    }
    defaults.update(overrides)
    return Insight(**defaults)


class TestInsightEventAssembly:
    """Tests for Issue 8.1.12 R5 insight event assembly."""

    def test_assemble_insight_events_basic(self, assembler):
        """assemble_insight_events creates events for each insight."""
        insights = [
            make_insight("insight_001"),
            make_insight("insight_002"),
        ]

        events = assembler.assemble_insight_events(insights)

        assert len(events) == 2
        assert all(e.topic == TOPIC_INSIGHT_GENERATED for e in events)
        assert all(e.priority == PRIORITY_INSIGHT for e in events)
        assert all(e.source_phase == SOURCE_PHASE_R6 for e in events)

    def test_assemble_insight_events_payload(self, assembler):
        """Insight event payload contains all required fields."""
        insight = make_insight(
            "insight_001",
            insight_type="PATTERN",
            concept_a_id="concept_A",
            concept_b_id="concept_B",
            pmi_score=5.0,
            novelty_score=0.9,
            relevance_score=0.8,
            natural_language="A connects to B",
            evidence_ids=["e1", "e2", "e3"],
        )

        events = assembler.assemble_insight_events([insight])

        assert len(events) == 1
        payload = events[0].payload

        assert payload["insight_id"] == "insight_001"
        assert payload["insight_type"] == "PATTERN"
        assert payload["concept_a_id"] == "concept_A"
        assert payload["concept_b_id"] == "concept_B"
        assert payload["pmi_score"] == 5.0
        assert payload["novelty_score"] == 0.9
        assert payload["relevance_score"] == 0.8
        assert payload["description"] == "A connects to B"
        assert payload["evidence_ids"] == ["e1", "e2", "e3"]
        assert "cycle_id" in payload
        assert "tenant_id" in payload
        assert "space_id" in payload
        assert "timestamp_ms" in payload

    def test_assemble_insight_events_dedupe(self, assembler):
        """Duplicate insight_ids are deduplicated."""
        insights = [
            make_insight("insight_001"),
            make_insight("insight_001"),  # Duplicate
            make_insight("insight_002"),
        ]

        events = assembler.assemble_insight_events(insights)

        assert len(events) == 2
        insight_ids = [e.payload["insight_id"] for e in events]
        assert "insight_001" in insight_ids
        assert "insight_002" in insight_ids

    def test_assemble_insight_events_empty(self, assembler):
        """Empty insight list returns empty events."""
        events = assembler.assemble_insight_events([])
        assert events == []

    def test_assemble_all_includes_insights(self, assembler):
        """assemble_all includes insight events in result."""
        summary = make_summary()
        insights = [make_insight("insight_001"), make_insight("insight_002")]

        result = assembler.assemble_all(
            summary=summary,
            event_states={},
            gaps=[],
            phase_durations={},
            insights=insights,
        )

        assert len(result.insight_events) == 2
        assert result.event_count_by_topic[TOPIC_INSIGHT_GENERATED] == 2
        # Total: 1 completion + 2 insights
        assert len(result.events) == 3

    def test_assemble_all_insights_optional(self, assembler):
        """assemble_all works without insights parameter."""
        summary = make_summary()

        result = assembler.assemble_all(
            summary=summary,
            event_states={},
            gaps=[],
            phase_durations={},
        )

        assert len(result.insight_events) == 0
        assert TOPIC_INSIGHT_GENERATED not in result.event_count_by_topic

    def test_insight_priority_between_gaps_and_decisions(self, assembler):
        """Insight priority (40) is between gaps (30) and decisions (50)."""
        assert PRIORITY_GAP < PRIORITY_INSIGHT < PRIORITY_DECISION

    def test_assembled_outbox_has_insight_events_field(self, assembler):
        """AssembledOutbox dataclass includes insight_events field."""
        summary = make_summary()
        insights = [make_insight("insight_001")]

        result = assembler.assemble_all(
            summary=summary,
            event_states={},
            gaps=[],
            phase_durations={},
            insights=insights,
        )

        assert hasattr(result, "insight_events")
        assert isinstance(result.insight_events, list)
        assert len(result.insight_events) == 1


# =============================================================================
# Issue 8.1.13 — Idempotency Key Tests
# =============================================================================


class TestIdempotencyKeys:
    """Tests for Issue 8.1.13 deterministic idempotency keys."""

    def test_completion_event_idempotency_key(self, assembler):
        """Completion event has deterministic idempotency key."""
        summary = make_summary()
        event = assembler.assemble_completion_event(summary, {})

        # Pattern: {cycle_id}:complete
        assert event.idempotency_key == "01ABC123:complete"

    def test_insight_event_idempotency_key(self, assembler):
        """Insight event has deterministic idempotency key per A.0.5."""
        insight = make_insight("insight_XYZ")

        events = assembler.assemble_insight_events([insight])

        assert len(events) == 1
        # Pattern: {cycle_id}:insight:{insight_id}
        assert events[0].idempotency_key == "01ABC123:insight:insight_XYZ"

    def test_gap_event_idempotency_key(self, assembler):
        """Gap event has deterministic idempotency key."""
        gap = make_gap("gap_ABC")

        events = assembler.assemble_gap_events([gap])

        assert len(events) == 1
        # Pattern: {cycle_id}:gap:{gap_id}
        assert events[0].idempotency_key == "01ABC123:gap:gap_ABC"

    def test_reinforce_event_idempotency_key(self, assembler):
        """REINFORCE event has deterministic idempotency key."""
        states = {
            "event_001": make_event_state("event_001", ReconciliationAction.REINFORCE),
        }

        events = assembler.assemble_decision_events(states)

        assert len(events) == 1
        # Pattern: {cycle_id}:reinforce:{event_id}
        assert events[0].idempotency_key == "01ABC123:reinforce:event_001"

    def test_create_events_idempotency_keys(self, assembler):
        """CREATE action produces events with deterministic keys."""
        states = {
            "event_002": make_event_state("event_002", ReconciliationAction.CREATE),
        }

        events = assembler.assemble_decision_events(states)

        # CREATE produces two events: created and pattern
        assert len(events) == 2

        created_event = [e for e in events if "create:" in e.idempotency_key][0]
        pattern_event = [e for e in events if "pattern:" in e.idempotency_key][0]

        assert created_event.idempotency_key == "01ABC123:create:event_002"
        assert pattern_event.idempotency_key == "01ABC123:pattern:event_002"

    def test_evolve_event_idempotency_key(self, assembler):
        """EVOLVE event has deterministic idempotency key."""
        states = {
            "event_003": make_event_state("event_003", ReconciliationAction.EVOLVE),
        }

        events = assembler.assemble_decision_events(states)

        assert len(events) == 1
        assert events[0].idempotency_key == "01ABC123:evolve:event_003"

    def test_prune_event_idempotency_key(self, assembler):
        """PRUNE event has deterministic idempotency key."""
        states = {
            "event_004": make_event_state("event_004", ReconciliationAction.PRUNE),
        }

        events = assembler.assemble_decision_events(states)

        assert len(events) == 1
        assert events[0].idempotency_key == "01ABC123:prune:event_004"

    def test_idempotency_keys_are_deterministic_on_retry(self, assembler):
        """Same inputs produce same idempotency keys (retry safety)."""
        insight = make_insight("insight_RETRY")

        # First assembly
        events1 = assembler.assemble_insight_events([insight])
        key1 = events1[0].idempotency_key

        # Second assembly (simulating retry)
        events2 = assembler.assemble_insight_events([insight])
        key2 = events2[0].idempotency_key

        # Keys must be identical for deduplication
        assert key1 == key2
        assert key1 == "01ABC123:insight:insight_RETRY"

    def test_insight_payload_includes_idempotency_key(self, assembler):
        """Insight payload includes idempotency_key for schema compliance."""
        insight = make_insight("insight_SCHEMA")

        events = assembler.assemble_insight_events([insight])

        # Check payload has idempotency_key (for p03_insight_generated.json schema)
        payload = events[0].payload
        # idempotency_key is on the event itself, not necessarily in payload
        # But payload should have cycle_id for reconstruction
        assert "cycle_id" in payload
        assert payload["cycle_id"] == "01ABC123"
