"""
Tests for SummaryGenerator — Issue 5.1.10

Tests ReconciliationSummary generation from event states.
"""

from k0.modules.consolidation.staging.r6_output import ReconciliationSummary
from k0.modules.consolidation.staging.summary_generator import (
    GeneratorResult,
    SummaryGenerator,
    count_actions,
    generate_summary,
    validate_total,
)
from k0.pipelines.p03.event_state import P03EventState, ReconciliationAction
from k0.pipelines.p03.staged_writes import (
    LAYER_ST_EPI,
    LAYER_ST_KG_DOM,
    LAYER_ST_KG_EDGES,
    LAYER_ST_SEM,
    StagedWrite,
    WriteOperation,
)

# =============================================================================
# FIXTURES
# =============================================================================


def make_event_state(
    event_id: str = "event_001",
    action: ReconciliationAction = ReconciliationAction.CREATE,
    cluster_id: str = "cluster_001",
) -> P03EventState:
    """Create a P03EventState with specified action."""
    state = P03EventState(event_id=event_id)
    state.reconciliation_action = action
    state.cluster_id = cluster_id
    return state


def make_staged_write(
    layer: str = LAYER_ST_EPI,
    record_id: str = "rec_001",
    write_id: str = "write_001",
) -> StagedWrite:
    """Create a StagedWrite with defaults."""
    return StagedWrite(
        write_id=write_id,
        layer=layer,
        operation=WriteOperation.INSERT,
        record_id=record_id,
        record_data={},
        idempotency_key=f"p03:write:cycle:{layer}:{record_id}",
        source_phase="R6",
        expected_version=0,
        source_event_ids=[],
    )


# =============================================================================
# SUMMARY GENERATOR CLASS TESTS
# =============================================================================


class TestSummaryGeneratorCompute:
    """Tests for SummaryGenerator.compute()."""

    def test_empty_event_states(self):
        """Test with no events."""
        generator = SummaryGenerator()
        result = generator.compute({})

        assert isinstance(result, GeneratorResult)
        assert result.summary.total_events == 0
        assert result.summary.consolidated_count == 0
        assert result.warnings == []

    def test_single_create_event(self):
        """Test single CREATE event maps to CONSOLIDATED."""
        generator = SummaryGenerator()
        states = {
            "e1": make_event_state("e1", ReconciliationAction.CREATE),
        }

        result = generator.compute(states)

        assert result.summary.total_events == 1
        assert result.summary.consolidated_count == 1
        assert result.summary.duplicate_count == 0
        assert result.summary.pruned_count == 0

    def test_all_consolidated_actions(self):
        """Test all actions that map to CONSOLIDATED."""
        generator = SummaryGenerator()
        states = {
            "e1": make_event_state("e1", ReconciliationAction.CREATE),
            "e2": make_event_state("e2", ReconciliationAction.REINFORCE),
            "e3": make_event_state("e3", ReconciliationAction.EXTEND),
            "e4": make_event_state("e4", ReconciliationAction.EVOLVE),
        }

        result = generator.compute(states)

        assert result.summary.total_events == 4
        assert result.summary.consolidated_count == 4
        assert result.warnings == []

    def test_skip_maps_to_duplicate(self):
        """Test SKIP action maps to DUPLICATE status."""
        generator = SummaryGenerator()
        states = {
            "e1": make_event_state("e1", ReconciliationAction.SKIP),
            "e2": make_event_state("e2", ReconciliationAction.SKIP),
        }

        result = generator.compute(states)

        assert result.summary.total_events == 2
        assert result.summary.duplicate_count == 2
        assert result.summary.consolidated_count == 0

    def test_prune_maps_to_pruned(self):
        """Test PRUNE action maps to PRUNED status."""
        generator = SummaryGenerator()
        states = {
            "e1": make_event_state("e1", ReconciliationAction.PRUNE),
        }

        result = generator.compute(states)

        assert result.summary.total_events == 1
        assert result.summary.pruned_count == 1

    def test_contradict_and_pending_map_to_pending_review(self):
        """Test CONTRADICT and PENDING map to PENDING_REVIEW."""
        generator = SummaryGenerator()
        states = {
            "e1": make_event_state("e1", ReconciliationAction.CONTRADICT),
            "e2": make_event_state("e2", ReconciliationAction.PENDING),
        }

        result = generator.compute(states)

        assert result.summary.total_events == 2
        assert result.summary.pending_review_count == 2

    def test_pending_events_generate_warning(self):
        """Test PENDING events generate warnings."""
        generator = SummaryGenerator()
        states = {
            "e1": make_event_state("e1", ReconciliationAction.PENDING),
            "e2": make_event_state("e2", ReconciliationAction.PENDING),
        }

        result = generator.compute(states)

        assert result.pending_count == 2
        assert len(result.warnings) == 1
        assert "2 events still have PENDING" in result.warnings[0]

    def test_mixed_actions(self):
        """Test mixed action types are counted correctly."""
        generator = SummaryGenerator()
        states = {
            "e1": make_event_state("e1", ReconciliationAction.CREATE),
            "e2": make_event_state("e2", ReconciliationAction.REINFORCE),
            "e3": make_event_state("e3", ReconciliationAction.SKIP),
            "e4": make_event_state("e4", ReconciliationAction.PRUNE),
            "e5": make_event_state("e5", ReconciliationAction.CONTRADICT),
        }

        result = generator.compute(states)

        assert result.summary.total_events == 5
        assert result.summary.consolidated_count == 2  # CREATE, REINFORCE
        assert result.summary.duplicate_count == 1  # SKIP
        assert result.summary.pruned_count == 1  # PRUNE
        assert result.summary.pending_review_count == 1  # CONTRADICT

    def test_action_breakdown_is_sorted(self):
        """Test action breakdown is sorted tuple of tuples."""
        generator = SummaryGenerator()
        states = {
            "e1": make_event_state("e1", ReconciliationAction.CREATE),
            "e2": make_event_state("e2", ReconciliationAction.SKIP),
        }

        result = generator.compute(states)

        assert isinstance(result.summary.action_breakdown, tuple)
        # Actions should be sorted alphabetically
        actions = [a[0] for a in result.summary.action_breakdown]
        assert actions == sorted(actions)

    def test_with_layer_write_counts(self):
        """Test layer write counts are stored as tuple."""
        generator = SummaryGenerator()
        states = {"e1": make_event_state("e1")}
        layer_counts = {"st_epi": 5, "st_sem": 3}

        result = generator.compute(states, layer_write_counts=layer_counts)

        assert isinstance(result.summary.layer_write_counts, tuple)
        layer_dict = dict(result.summary.layer_write_counts)
        assert layer_dict["st_epi"] == 5
        assert layer_dict["st_sem"] == 3

    def test_with_kg_and_gap_counts(self):
        """Test KG entity/edge and gap counts."""
        generator = SummaryGenerator()
        states = {"e1": make_event_state("e1")}

        result = generator.compute(
            states,
            kg_entity_count=10,
            kg_edge_count=25,
            gap_count=3,
        )

        assert result.summary.kg_entity_count == 10
        assert result.summary.kg_edge_count == 25
        assert result.summary.gap_count == 3

    def test_total_writes_and_duration(self):
        """Test total writes and cycle duration."""
        generator = SummaryGenerator()
        states = {"e1": make_event_state("e1")}

        result = generator.compute(
            states,
            total_writes=100,
            cycle_duration_ms=5000,
        )

        assert result.summary.total_writes == 100
        assert result.summary.cycle_duration_ms == 5000


class TestSummaryGeneratorComputeFromActions:
    """Tests for SummaryGenerator.compute_from_actions()."""

    def test_list_of_actions(self):
        """Test compute from list of actions."""
        generator = SummaryGenerator()
        actions = [
            ReconciliationAction.CREATE,
            ReconciliationAction.CREATE,
            ReconciliationAction.SKIP,
        ]

        summary = generator.compute_from_actions(actions)

        assert summary.total_events == 3
        assert summary.consolidated_count == 2
        assert summary.duplicate_count == 1

    def test_empty_actions_list(self):
        """Test with empty actions list."""
        generator = SummaryGenerator()
        summary = generator.compute_from_actions([])

        assert summary.total_events == 0

    def test_all_same_action(self):
        """Test all same action type."""
        generator = SummaryGenerator()
        actions = [ReconciliationAction.REINFORCE] * 5

        summary = generator.compute_from_actions(actions)

        assert summary.total_events == 5
        assert summary.consolidated_count == 5


class TestSummaryGeneratorMerge:
    """Tests for SummaryGenerator.merge()."""

    def test_merge_empty_list(self):
        """Test merging empty list returns empty summary."""
        generator = SummaryGenerator()
        result = generator.merge([])

        assert result.total_events == 0

    def test_merge_single_summary(self):
        """Test merging single summary returns it unchanged."""
        generator = SummaryGenerator()
        summary = ReconciliationSummary(
            total_events=10,
            consolidated_count=8,
            duplicate_count=2,
        )

        result = generator.merge([summary])

        assert result.total_events == 10
        assert result.consolidated_count == 8

    def test_merge_two_summaries(self):
        """Test merging two summaries."""
        generator = SummaryGenerator()
        s1 = ReconciliationSummary(
            total_events=10,
            consolidated_count=8,
            duplicate_count=2,
            kg_entity_count=5,
            kg_edge_count=10,
            total_writes=20,
            cycle_duration_ms=100,
        )
        s2 = ReconciliationSummary(
            total_events=5,
            consolidated_count=3,
            duplicate_count=1,
            pruned_count=1,
            kg_entity_count=3,
            kg_edge_count=5,
            total_writes=10,
            cycle_duration_ms=200,
        )

        result = generator.merge([s1, s2])

        assert result.total_events == 15
        assert result.consolidated_count == 11
        assert result.duplicate_count == 3
        assert result.pruned_count == 1
        assert result.kg_entity_count == 8
        assert result.kg_edge_count == 15
        assert result.total_writes == 30
        # Duration takes max (parallel execution)
        assert result.cycle_duration_ms == 200

    def test_merge_action_breakdowns(self):
        """Test action breakdowns are merged correctly."""
        generator = SummaryGenerator()
        s1 = ReconciliationSummary(
            total_events=5,
            action_breakdown=(("CREATE", 3), ("SKIP", 2)),
        )
        s2 = ReconciliationSummary(
            total_events=3,
            action_breakdown=(("CREATE", 1), ("PRUNE", 2)),
        )

        result = generator.merge([s1, s2])

        breakdown_dict = dict(result.action_breakdown)
        assert breakdown_dict["CREATE"] == 4
        assert breakdown_dict["SKIP"] == 2
        assert breakdown_dict["PRUNE"] == 2

    def test_merge_layer_write_counts(self):
        """Test layer write counts are merged correctly."""
        generator = SummaryGenerator()
        s1 = ReconciliationSummary(
            total_events=5,
            layer_write_counts=(("st_epi", 10), ("st_sem", 5)),
        )
        s2 = ReconciliationSummary(
            total_events=3,
            layer_write_counts=(("st_epi", 5), ("st_kg_dom", 3)),
        )

        result = generator.merge([s1, s2])

        layer_dict = dict(result.layer_write_counts)
        assert layer_dict["st_epi"] == 15
        assert layer_dict["st_sem"] == 5
        assert layer_dict["st_kg_dom"] == 3


class TestSummaryGeneratorComputeWithWrites:
    """Tests for SummaryGenerator.compute_with_writes()."""

    def test_compute_with_truth_writes(self):
        """Test computing summary with truth writes."""
        generator = SummaryGenerator()
        states = {"e1": make_event_state("e1")}
        truth_writes = [
            make_staged_write(LAYER_ST_EPI, "rec_1", "w1"),
            make_staged_write(LAYER_ST_EPI, "rec_2", "w2"),
            make_staged_write(LAYER_ST_SEM, "rec_3", "w3"),
        ]

        result = generator.compute_with_writes(
            event_states=states,
            truth_writes=truth_writes,
            kg_writes=[],
        )

        assert result.summary.total_writes == 3
        layer_dict = dict(result.summary.layer_write_counts)
        assert layer_dict[LAYER_ST_EPI] == 2
        assert layer_dict[LAYER_ST_SEM] == 1

    def test_compute_with_kg_writes(self):
        """Test KG entity and edge counting."""
        generator = SummaryGenerator()
        states = {"e1": make_event_state("e1")}
        kg_writes = [
            make_staged_write(LAYER_ST_KG_DOM, "entity_1", "w1"),
            make_staged_write(LAYER_ST_KG_DOM, "entity_2", "w2"),
            make_staged_write(LAYER_ST_KG_EDGES, "edge_1", "w3"),
        ]

        result = generator.compute_with_writes(
            event_states=states,
            truth_writes=[],
            kg_writes=kg_writes,
        )

        assert result.summary.kg_entity_count == 2
        assert result.summary.kg_edge_count == 1

    def test_compute_with_gap_and_duration(self):
        """Test gap count and duration are passed through."""
        generator = SummaryGenerator()
        states = {"e1": make_event_state("e1")}

        result = generator.compute_with_writes(
            event_states=states,
            truth_writes=[],
            kg_writes=[],
            gap_count=5,
            cycle_duration_ms=1000,
        )

        assert result.summary.gap_count == 5
        assert result.summary.cycle_duration_ms == 1000


# =============================================================================
# UTILITY FUNCTION TESTS
# =============================================================================


class TestGenerateSummary:
    """Tests for generate_summary utility function."""

    def test_generate_summary_basic(self):
        """Test basic summary generation."""
        states = {
            "e1": make_event_state("e1", ReconciliationAction.CREATE),
            "e2": make_event_state("e2", ReconciliationAction.SKIP),
        }

        summary = generate_summary(states)

        assert isinstance(summary, ReconciliationSummary)
        assert summary.total_events == 2

    def test_generate_summary_with_kwargs(self):
        """Test summary generation with additional arguments."""
        states = {"e1": make_event_state("e1")}

        summary = generate_summary(
            states,
            kg_entity_count=5,
            cycle_duration_ms=100,
        )

        assert summary.kg_entity_count == 5
        assert summary.cycle_duration_ms == 100


class TestCountActions:
    """Tests for count_actions utility function."""

    def test_count_actions_basic(self):
        """Test basic action counting."""
        states = {
            "e1": make_event_state("e1", ReconciliationAction.CREATE),
            "e2": make_event_state("e2", ReconciliationAction.CREATE),
            "e3": make_event_state("e3", ReconciliationAction.SKIP),
        }

        counts = count_actions(states)

        assert counts["CREATE"] == 2
        assert counts["SKIP"] == 1

    def test_count_actions_empty(self):
        """Test counting with empty states."""
        counts = count_actions({})
        assert counts == {}


class TestValidateTotal:
    """Tests for validate_total utility function."""

    def test_validate_total_consistent(self):
        """Test validation passes when totals are consistent."""
        summary = ReconciliationSummary(
            total_events=10,
            consolidated_count=5,
            duplicate_count=2,
            pruned_count=2,
            pending_review_count=1,
        )

        assert validate_total(summary) is True

    def test_validate_total_inconsistent(self):
        """Test validation fails when totals are inconsistent."""
        summary = ReconciliationSummary(
            total_events=10,
            consolidated_count=5,
            duplicate_count=2,
            pruned_count=1,  # Missing 2
            pending_review_count=0,
        )

        assert validate_total(summary) is False

    def test_validate_total_empty_summary(self):
        """Test empty summary validates correctly."""
        summary = ReconciliationSummary()
        assert validate_total(summary) is True


# =============================================================================
# GENERATOR RESULT DATACLASS TESTS
# =============================================================================


class TestGeneratorResult:
    """Tests for GeneratorResult dataclass."""

    def test_default_values(self):
        """Test default values for GeneratorResult."""
        result = GeneratorResult(summary=ReconciliationSummary())

        assert result.warnings == []
        assert result.pending_count == 0

    def test_with_warnings(self):
        """Test GeneratorResult with warnings."""
        result = GeneratorResult(
            summary=ReconciliationSummary(),
            warnings=["warning1", "warning2"],
            pending_count=5,
        )

        assert len(result.warnings) == 2
        assert result.pending_count == 5


# =============================================================================
# ACTION TO STATUS MAPPING TESTS
# =============================================================================


class TestActionToStatusMapping:
    """Tests for ACTION_TO_STATUS mapping completeness."""

    def test_all_actions_have_mapping(self):
        """Test all ReconciliationAction values have a mapping."""
        generator = SummaryGenerator()

        for action in ReconciliationAction:
            assert action in generator.ACTION_TO_STATUS, f"Missing mapping for {action}"

    def test_valid_status_values(self):
        """Test all mapped statuses are valid."""
        generator = SummaryGenerator()
        valid_statuses = {"CONSOLIDATED", "DUPLICATE", "PRUNED", "PENDING_REVIEW"}

        for action, status in generator.ACTION_TO_STATUS.items():
            assert status in valid_statuses, f"Invalid status {status} for {action}"
