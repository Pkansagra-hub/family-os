"""
R6Staging Phase Tests — Issues 5.1.14 & 5.1.15

Tests for R6 input extraction and output population:
- R6Inputs dataclass validation
- _extract_inputs() correctly gathers R1-R4 outputs
- _populate_envelope() routes writes correctly
- _event_update_to_staged_write() conversion
"""

from dataclasses import dataclass, field
from typing import List
from unittest.mock import MagicMock

import pytest

from k0.modules.consolidation.staging.r6_coordinator import R6CoordinatorConfig
from k0.modules.consolidation.staging.r6_output import (
    R6Output,
    ReconciliationSummary,
    StagedEventUpdate,
)
from k0.pipelines.p03.event_state import P03EventState, ReconciliationAction
from k0.pipelines.p03.phase_outputs import EpisodeCluster, GapCandidate, P03PhaseOutputs
from k0.pipelines.p03.phases.r6_staging import R6Inputs, R6Staging, create_r6_phase
from k0.pipelines.p03.staged_writes import (
    LAYER_ST_HIPP_EVENTS,
    P03StagedWrites,
    StagedWrite,
    WriteOperation,
)

# =============================================================================
# CONSTANTS
# =============================================================================

TEST_ULID = "01HXYZ123456789ABCDEFGHJKM"
TEST_TENANT = "tenant_001"
TEST_SPACE = "space_001"


# =============================================================================
# MOCK ENVELOPE
# =============================================================================


@dataclass
class MockCycleContext:
    """Mock P03CycleContext for testing."""

    cycle_id: str = TEST_ULID
    tenant_id: str = TEST_TENANT
    space_id: str = TEST_SPACE
    cycle_start_ts: int = 1704067200000


@dataclass
class MockBatchEnvelope:
    """Mock P03BatchEnvelope for testing."""

    context: MockCycleContext = field(default_factory=MockCycleContext)
    events: List[P03EventState] = field(default_factory=list)
    phases: P03PhaseOutputs = field(default_factory=P03PhaseOutputs)
    staged: P03StagedWrites = field(default_factory=P03StagedWrites)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def sample_event_states() -> List[P03EventState]:
    """Create sample event states for testing."""
    states = []
    for i in range(3):
        state = P03EventState(event_id=f"event_{i:03d}")
        state.importance_score = 0.5 + (i * 0.1)
        state.reconciliation_action = ReconciliationAction.CREATE
        states.append(state)
    return states


@pytest.fixture
def sample_clusters() -> List[EpisodeCluster]:
    """Create sample episode clusters."""
    return [
        EpisodeCluster(
            cluster_id="cluster_001",
            member_event_ids=["event_000", "event_001"],
            title="Test Cluster",
        ),
    ]


@pytest.fixture
def sample_gap_candidates() -> List[GapCandidate]:
    """Create sample gap candidates."""
    return [
        GapCandidate(
            gap_id="gap_001",
            gap_type="AMBIGUITY",
            related_entity_id="entity_001",
            entropy_score=0.7,
            priority="MEDIUM",
        ),
    ]


@pytest.fixture
def sample_envelope(sample_event_states, sample_clusters, sample_gap_candidates):
    """Create a sample envelope with R1-R4 outputs."""
    envelope = MockBatchEnvelope()
    envelope.events = sample_event_states
    envelope.phases.r2_clusters = sample_clusters
    envelope.phases.r4_gap_candidates = sample_gap_candidates
    return envelope


@pytest.fixture
def r6_staging() -> R6Staging:
    """Create R6Staging instance."""
    return R6Staging()


# =============================================================================
# R6INPUTS DATACLASS TESTS — Issue 5.1.14
# =============================================================================


class TestR6InputsDataclass:
    """Tests for R6Inputs dataclass."""

    def test_default_values(self):
        """Test R6Inputs has sensible defaults."""
        inputs = R6Inputs()

        assert inputs.event_states == {}
        assert inputs.r2_clusters == []
        assert inputs.r3_dedup_merges == []
        assert inputs.r4_new_entities == []
        assert inputs.r4_gap_candidates == []
        assert inputs.cycle_id == ""
        assert inputs.tenant_id == ""
        assert inputs.space_id == ""

    def test_event_count_property(self):
        """Test event_count returns correct count."""
        inputs = R6Inputs(
            event_states={
                "e1": MagicMock(),
                "e2": MagicMock(),
                "e3": MagicMock(),
            }
        )

        assert inputs.event_count == 3

    def test_batch_event_ids_property(self):
        """Test batch_event_ids returns set of event IDs."""
        inputs = R6Inputs(
            event_states={
                "e1": MagicMock(),
                "e2": MagicMock(),
            }
        )

        assert inputs.batch_event_ids == {"e1", "e2"}

    def test_full_construction(self, sample_clusters, sample_gap_candidates):
        """Test R6Inputs with all fields populated."""
        event_states = {"e1": P03EventState(event_id="e1")}

        inputs = R6Inputs(
            event_states=event_states,
            r2_clusters=sample_clusters,
            r4_gap_candidates=sample_gap_candidates,
            cycle_id=TEST_ULID,
            tenant_id=TEST_TENANT,
            space_id=TEST_SPACE,
            cycle_start_ms=1704067200000,
        )

        assert inputs.event_count == 1
        assert len(inputs.r2_clusters) == 1
        assert len(inputs.r4_gap_candidates) == 1
        assert inputs.cycle_id == TEST_ULID


# =============================================================================
# _EXTRACT_INPUTS TESTS — Issue 5.1.14
# =============================================================================


class TestExtractInputs:
    """Tests for R6Staging._extract_inputs()."""

    def test_extracts_event_states(self, r6_staging, sample_envelope):
        """Test event states extracted and keyed by ID."""
        inputs = r6_staging._extract_inputs(sample_envelope)

        assert len(inputs.event_states) == 3
        assert "event_000" in inputs.event_states
        assert "event_001" in inputs.event_states
        assert "event_002" in inputs.event_states

    def test_extracts_r2_clusters(self, r6_staging, sample_envelope):
        """Test R2 clusters extracted."""
        inputs = r6_staging._extract_inputs(sample_envelope)

        assert len(inputs.r2_clusters) == 1
        assert inputs.r2_clusters[0].cluster_id == "cluster_001"

    def test_extracts_r4_gap_candidates(self, r6_staging, sample_envelope):
        """Test R4 gap candidates extracted."""
        inputs = r6_staging._extract_inputs(sample_envelope)

        assert len(inputs.r4_gap_candidates) == 1
        assert inputs.r4_gap_candidates[0].gap_id == "gap_001"

    def test_extracts_cycle_context(self, r6_staging, sample_envelope):
        """Test cycle context fields extracted."""
        inputs = r6_staging._extract_inputs(sample_envelope)

        assert inputs.cycle_id == TEST_ULID
        assert inputs.tenant_id == TEST_TENANT
        assert inputs.space_id == TEST_SPACE
        assert inputs.cycle_start_ms == 1704067200000

    def test_handles_empty_outputs(self, r6_staging):
        """Test handles envelope with no phase outputs."""
        envelope = MockBatchEnvelope()

        inputs = r6_staging._extract_inputs(envelope)

        assert inputs.event_count == 0
        assert inputs.r2_clusters == []
        assert inputs.r4_gap_candidates == []

    def test_handles_none_outputs(self, r6_staging):
        """Test handles None phase output fields gracefully."""
        envelope = MockBatchEnvelope()
        envelope.phases.r2_clusters = None
        envelope.phases.r4_gap_candidates = None

        inputs = r6_staging._extract_inputs(envelope)

        assert inputs.r2_clusters == []
        assert inputs.r4_gap_candidates == []


# =============================================================================
# _POPULATE_ENVELOPE TESTS — Issue 5.1.15
# =============================================================================


class TestPopulateEnvelope:
    """Tests for R6Staging._populate_envelope()."""

    def test_populates_truth_writes(self, r6_staging):
        """Test truth writes added to envelope.staged."""
        envelope = MockBatchEnvelope()

        # Create mock R6 result
        truth_write = StagedWrite(
            write_id="write_001",
            layer="st_epi",
            operation=WriteOperation.INSERT,
            record_id="record_001",
            record_data={"test": "data"},
            idempotency_key="test-key",
            source_phase="R6",
        )

        r6_output = MagicMock(spec=R6Output)
        r6_output.staged_truth_writes = (truth_write,)
        r6_output.staged_kg_writes = ()
        r6_output.staged_outbox_events = ()
        r6_output.staged_event_updates = ()
        r6_output.reconciliation_summary = ReconciliationSummary()

        result = MagicMock()
        result.r6_output = r6_output

        r6_staging._populate_envelope(envelope, result)

        assert envelope.staged.total_writes() >= 1

    def test_populates_kg_writes(self, r6_staging):
        """Test KG writes added to envelope.staged."""
        envelope = MockBatchEnvelope()

        kg_write = StagedWrite(
            write_id="write_002",
            layer="st_kg_dom",
            operation=WriteOperation.INSERT,
            record_id="entity_001",
            record_data={"entity_name": "Test"},
            idempotency_key="kg-key",
            source_phase="R6",
        )

        r6_output = MagicMock(spec=R6Output)
        r6_output.staged_truth_writes = ()
        r6_output.staged_kg_writes = (kg_write,)
        r6_output.staged_outbox_events = ()
        r6_output.staged_event_updates = ()
        r6_output.reconciliation_summary = ReconciliationSummary()

        result = MagicMock()
        result.r6_output = r6_output

        r6_staging._populate_envelope(envelope, result)

        # KG writes should be routed to st_kg_dom_writes
        assert len(envelope.staged.st_kg_dom_writes) == 1

    def test_populates_outbox_events(self, r6_staging):
        """Test outbox events appended to envelope.staged."""
        from k0.pipelines.p03.staged_writes import StagedOutboxEvent

        envelope = MockBatchEnvelope()

        outbox_event = StagedOutboxEvent.create(
            topic="p03.consolidation.completed",
            payload={"cycle_id": TEST_ULID},
            phase="R6",
        )

        r6_output = MagicMock(spec=R6Output)
        r6_output.staged_truth_writes = ()
        r6_output.staged_kg_writes = ()
        r6_output.staged_outbox_events = (outbox_event,)
        r6_output.staged_event_updates = ()
        r6_output.reconciliation_summary = ReconciliationSummary()

        result = MagicMock()
        result.r6_output = r6_output

        r6_staging._populate_envelope(envelope, result)

        assert len(envelope.staged.outbox_events) == 1
        assert envelope.staged.outbox_events[0].topic == "p03.consolidation.completed"

    def test_populates_event_updates(self, r6_staging):
        """Test event updates converted to StagedWrite and added."""
        envelope = MockBatchEnvelope()

        event_update = StagedEventUpdate(
            event_id="event_001",
            consolidation_status="CONSOLIDATED",
            reconciliation_action="CREATE",
            idempotency_key="r6:event_001",
        )

        r6_output = MagicMock(spec=R6Output)
        r6_output.staged_truth_writes = ()
        r6_output.staged_kg_writes = ()
        r6_output.staged_outbox_events = ()
        r6_output.staged_event_updates = (event_update,)
        r6_output.reconciliation_summary = ReconciliationSummary()

        result = MagicMock()
        result.r6_output = r6_output

        r6_staging._populate_envelope(envelope, result)

        # Event updates go to st_hipp_events_updates
        assert len(envelope.staged.st_hipp_events_updates) == 1
        write = envelope.staged.st_hipp_events_updates[0]
        assert write.layer == LAYER_ST_HIPP_EVENTS
        assert write.record_id == "event_001"
        assert write.operation == WriteOperation.UPDATE

    def test_populates_r6_summary(self, r6_staging):
        """Test r6_summary set on envelope.phases."""
        envelope = MockBatchEnvelope()

        summary = ReconciliationSummary(
            total_events=5,
            consolidated_count=3,
            duplicate_count=1,
            pruned_count=1,
        )

        r6_output = MagicMock(spec=R6Output)
        r6_output.staged_truth_writes = ()
        r6_output.staged_kg_writes = ()
        r6_output.staged_outbox_events = ()
        r6_output.staged_event_updates = ()
        r6_output.reconciliation_summary = summary

        result = MagicMock()
        result.r6_output = r6_output

        r6_staging._populate_envelope(envelope, result)

        assert envelope.phases.r6_summary.total_events == 5
        assert envelope.phases.r6_summary.consolidated_count == 3

    def test_handles_none_r6_output(self, r6_staging):
        """Test handles None r6_output gracefully."""
        envelope = MockBatchEnvelope()

        result = MagicMock()
        result.r6_output = None

        # Should not raise
        r6_staging._populate_envelope(envelope, result)

        assert envelope.staged.total_writes() == 0


# =============================================================================
# _EVENT_UPDATE_TO_STAGED_WRITE TESTS — Issue 5.1.15
# =============================================================================


class TestEventUpdateToStagedWrite:
    """Tests for R6Staging._event_update_to_staged_write()."""

    def test_converts_to_staged_write(self, r6_staging):
        """Test conversion produces valid StagedWrite."""
        update = StagedEventUpdate(
            event_id="event_001",
            consolidation_status="CONSOLIDATED",
            reconciliation_action="CREATE",
            novelty_score=0.85,
            confidence=0.9,
            idempotency_key="r6:staging:event_001",
        )

        write = r6_staging._event_update_to_staged_write(update)

        assert isinstance(write, StagedWrite)
        assert write.layer == LAYER_ST_HIPP_EVENTS
        assert write.operation == WriteOperation.UPDATE
        assert write.record_id == "event_001"
        assert write.source_phase == "R6"

    def test_conversion_preserves_data(self, r6_staging):
        """Test conversion preserves all update data."""
        update = StagedEventUpdate(
            event_id="event_002",
            consolidation_status="DUPLICATE",
            novelty_score=0.1,
            near_duplicates_json='["event_001"]',
            reconciliation_action="SKIP",
            best_match_id="event_001",
            best_match_layer="st_epi",
            similarity_score=0.95,
            confidence=0.99,
            reconciliation_reason="Exact duplicate",
            idempotency_key="r6:staging:event_002",
        )

        write = r6_staging._event_update_to_staged_write(update)

        assert write.record_data["consolidation_status"] == "DUPLICATE"
        assert write.record_data["novelty_score"] == 0.1
        assert write.record_data["near_duplicates_json"] == '["event_001"]'
        assert write.record_data["best_match_id"] == "event_001"

    def test_idempotency_key_preserved(self, r6_staging):
        """Test idempotency key is preserved in conversion."""
        update = StagedEventUpdate(
            event_id="event_003",
            consolidation_status="CONSOLIDATED",
            idempotency_key="custom-idem-key",
        )

        write = r6_staging._event_update_to_staged_write(update)

        assert write.idempotency_key == "custom-idem-key"


# =============================================================================
# FACTORY FUNCTION TESTS
# =============================================================================


class TestCreateR6Phase:
    """Tests for create_r6_phase factory function."""

    def test_creates_r6_staging(self):
        """Test factory creates R6Staging instance."""
        phase = create_r6_phase()

        assert isinstance(phase, R6Staging)

    def test_accepts_config(self):
        """Test factory accepts configuration."""
        config = R6CoordinatorConfig(dry_run=True, validate_manifest=False)

        phase = create_r6_phase(config=config)

        assert phase._config.dry_run is True
        assert phase._config.validate_manifest is False

    def test_default_config(self):
        """Test factory uses default config when not provided."""
        phase = create_r6_phase()

        assert phase._config.dry_run is False
        assert phase._config.validate_manifest is True
