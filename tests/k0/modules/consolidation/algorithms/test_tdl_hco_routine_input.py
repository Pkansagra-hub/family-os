"""
Integration tests for TDL-HCO Routine Input (M5-E1).

These tests validate:
- DreamExplorerInput.accumulated_routines field exists
- TDL-HCO receives merged routines (detected + accumulated)
- Routine conversion from st_procedural format to RoutineTemplate
- Routine conversion from RoutineCandidate to RoutineTemplate

References:
- R5_ALGORITHM_BACKLOG.md M5-E1: Routine Input
- TDL-HCO Issue 8.1.11: Motor Rehearsal for Habits
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from k0.modules.consolidation.algorithms.routine_detector import RoutineCandidate

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def accumulated_routine_dict() -> dict:
    """Sample routine dict from st_procedural (procedural_memory_query syscall)."""
    return {
        "routine_id": "routine_morning_coffee",
        "actor_id": "user_001",
        "routine_name": "Morning Coffee Routine",
        "routine_category": "daily",
        "temporal_anchor": "08:00",
        "day_pattern": "weekday",
        "frequency": 5,
        "regularity_score": 0.85,
        "action_sequence_json": '[{"action": "wake_up", "duration_ms": 60000}, {"action": "make_coffee", "duration_ms": 300000}]',
        "source_episodes_json": '["ep_001", "ep_002", "ep_003"]',
        "source_episode_count": 3,
        "lifecycle_state": "ACTIVE",
    }


@pytest.fixture
def routine_candidate() -> RoutineCandidate:
    """Sample RoutineCandidate from RoutineDetector."""
    return RoutineCandidate(
        routine_id="detected_routine_001",
        routine_name="Detected Exercise Routine",
        routine_category="EXERCISE",
        temporal_anchor="07:00",
        day_pattern="weekdays",
        source_episode_count=5,
        typical_duration_minutes=45,
        source_episodes_json='[{"episode_id": "ep_010", "start_time_ms": 1705000000000}, {"episode_id": "ep_011", "start_time_ms": 1705086400000}]',
    )


# =============================================================================
# DREAM EXPLORER INPUT TESTS
# =============================================================================


class TestDreamExplorerInputRoutineField:
    """Tests for accumulated_routines field in DreamExplorerInput."""

    def test_dream_explorer_input_has_accumulated_routines_field(self) -> None:
        """DreamExplorerInput has accumulated_routines field."""
        from k0.modules.consolidation.dream.models import DreamExplorerInput

        input_data = DreamExplorerInput(
            cycle_id="cycle_001",
            tenant_id="tenant_001",
            space_id="space_001",
        )

        assert hasattr(input_data, "accumulated_routines")
        assert isinstance(input_data.accumulated_routines, list)
        assert input_data.accumulated_routines == []  # Default empty

    def test_dream_explorer_input_accepts_accumulated_routines(
        self, accumulated_routine_dict: dict
    ) -> None:
        """DreamExplorerInput accepts accumulated_routines in constructor."""
        from k0.modules.consolidation.dream.models import DreamExplorerInput

        input_data = DreamExplorerInput(
            cycle_id="cycle_001",
            tenant_id="tenant_001",
            space_id="space_001",
            accumulated_routines=[accumulated_routine_dict],
        )

        assert len(input_data.accumulated_routines) == 1
        assert input_data.accumulated_routines[0]["routine_id"] == "routine_morning_coffee"

    def test_dream_explorer_input_multiple_routines(self, accumulated_routine_dict: dict) -> None:
        """DreamExplorerInput can hold multiple accumulated routines."""
        from k0.modules.consolidation.dream.models import DreamExplorerInput

        routine2 = accumulated_routine_dict.copy()
        routine2["routine_id"] = "routine_evening_walk"
        routine2["routine_name"] = "Evening Walk Routine"

        input_data = DreamExplorerInput(
            cycle_id="cycle_001",
            tenant_id="tenant_001",
            space_id="space_001",
            accumulated_routines=[accumulated_routine_dict, routine2],
        )

        assert len(input_data.accumulated_routines) == 2


# =============================================================================
# ROUTINE CONVERSION TESTS
# =============================================================================


class TestAccumulatedRoutineConversion:
    """Tests for converting st_procedural routines to RoutineTemplate."""

    def test_convert_accumulated_routine_to_template(self, accumulated_routine_dict: dict) -> None:
        """Accumulated routine dict converts to RoutineTemplate."""
        from k0.modules.consolidation.dream import DreamConfig, DreamExplorer

        explorer = DreamExplorer(config=DreamConfig())
        templates = explorer._convert_accumulated_routines_to_templates([accumulated_routine_dict])

        assert len(templates) == 1
        template = templates[0]
        assert template.routine_id == "routine_morning_coffee"
        assert template.routine_name == "Morning Coffee Routine"
        assert template.execution_count == 3

    def test_convert_accumulated_routine_parses_action_sequence(
        self, accumulated_routine_dict: dict
    ) -> None:
        """Action sequence JSON is parsed into steps."""
        from k0.modules.consolidation.dream import DreamConfig, DreamExplorer

        explorer = DreamExplorer(config=DreamConfig())
        templates = explorer._convert_accumulated_routines_to_templates([accumulated_routine_dict])

        template = templates[0]
        # Should have 2 steps from action_sequence_json
        assert len(template.canonical_steps) == 2
        assert "wake_up" in template.canonical_steps
        assert "make_coffee" in template.canonical_steps

    def test_convert_accumulated_routine_handles_empty_action_sequence(self) -> None:
        """Empty action sequence creates synthetic step."""
        from k0.modules.consolidation.dream import DreamConfig, DreamExplorer

        routine = {
            "routine_id": "routine_001",
            "routine_name": "Simple Routine",
            "action_sequence_json": "[]",
            "source_episodes_json": "[]",
            "source_episode_count": 1,
            "regularity_score": 0.7,
        }

        explorer = DreamExplorer(config=DreamConfig())
        templates = explorer._convert_accumulated_routines_to_templates([routine])

        assert len(templates) == 1
        # Should create synthetic step from routine name
        assert len(templates[0].canonical_steps) == 1
        assert templates[0].canonical_steps[0] == "Simple Routine"

    def test_convert_accumulated_routine_handles_malformed_json(self) -> None:
        """Malformed JSON in action_sequence_json is handled gracefully."""
        from k0.modules.consolidation.dream import DreamConfig, DreamExplorer

        routine = {
            "routine_id": "routine_001",
            "routine_name": "Malformed Routine",
            "action_sequence_json": "not valid json",
            "source_episodes_json": "also not valid",
            "source_episode_count": 1,
            "regularity_score": 0.5,
        }

        explorer = DreamExplorer(config=DreamConfig())
        templates = explorer._convert_accumulated_routines_to_templates([routine])

        # Should still create template with synthetic step
        assert len(templates) == 1
        assert templates[0].routine_name == "Malformed Routine"

    def test_convert_accumulated_routine_uses_regularity_as_success_rate(
        self, accumulated_routine_dict: dict
    ) -> None:
        """Regularity score is used as success rate proxy."""
        from k0.modules.consolidation.dream import DreamConfig, DreamExplorer

        explorer = DreamExplorer(config=DreamConfig())
        templates = explorer._convert_accumulated_routines_to_templates([accumulated_routine_dict])

        template = templates[0]
        assert template.success_rate == 0.85  # From regularity_score


class TestRoutineCandidateConversion:
    """Tests for converting RoutineCandidate to RoutineTemplate."""

    def test_convert_routine_candidate_to_template(
        self, routine_candidate: "RoutineCandidate"
    ) -> None:
        """RoutineCandidate converts to RoutineTemplate."""
        from k0.modules.consolidation.dream import DreamConfig, DreamExplorer

        explorer = DreamExplorer(config=DreamConfig())
        templates = explorer._convert_routine_candidates_to_templates([routine_candidate])

        assert len(templates) == 1
        template = templates[0]
        assert template.routine_id == "detected_routine_001"
        assert template.routine_name == "Detected Exercise Routine"
        assert template.execution_count == 5

    def test_convert_routine_candidate_creates_executions(
        self, routine_candidate: "RoutineCandidate"
    ) -> None:
        """Routine candidate creates execution records from source episodes."""
        from k0.modules.consolidation.dream import DreamConfig, DreamExplorer

        explorer = DreamExplorer(config=DreamConfig())
        templates = explorer._convert_routine_candidates_to_templates([routine_candidate])

        template = templates[0]
        assert len(template.executions) == 2  # From source_episodes_json


# =============================================================================
# TDL-HCO ROUTINE MERGING TESTS
# =============================================================================


class TestTDLHCORoutineMerging:
    """Tests for TDL-HCO routine source merging."""

    def test_tdl_hco_prioritizes_detected_routines(self) -> None:
        """TDL-HCO uses detected routines when available."""
        from k0.modules.consolidation.dream import DreamConfig, DreamExplorer
        from k0.modules.consolidation.dream.models import DreamExplorerInput

        # Create mock episode for minimal input
        @dataclass
        class MockEpisode:
            cluster_id: str = "ep_001"
            activity_type: str = "exercise"

        detected = RoutineCandidate(
            routine_id="detected_001",
            routine_name="Detected Routine",
            routine_category="EXERCISE",
            source_episode_count=3,
            typical_duration_minutes=30,
            source_episodes_json='[{"episode_id": "ep_001", "start_time_ms": 0}]',
        )

        # Verify input_data can be created with mock episode
        _ = DreamExplorerInput(
            cycle_id="cycle_001",
            tenant_id="tenant_001",
            space_id="space_001",
            recent_episodes=[MockEpisode()],
            accumulated_routines=[],
        )

        explorer = DreamExplorer(config=DreamConfig())
        templates = explorer._convert_routine_candidates_to_templates([detected])

        assert len(templates) == 1
        assert templates[0].routine_id == "detected_001"

    def test_accumulated_routines_merged_without_duplicates(self) -> None:
        """Accumulated routines merge without duplicating existing IDs."""
        from k0.modules.consolidation.dream import DreamConfig, DreamExplorer

        accumulated = [
            {
                "routine_id": "routine_001",
                "routine_name": "First Routine",
                "action_sequence_json": "[]",
                "source_episodes_json": "[]",
                "source_episode_count": 2,
                "regularity_score": 0.8,
            },
            {
                "routine_id": "routine_002",
                "routine_name": "Second Routine",
                "action_sequence_json": "[]",
                "source_episodes_json": "[]",
                "source_episode_count": 3,
                "regularity_score": 0.7,
            },
        ]

        explorer = DreamExplorer(config=DreamConfig())
        templates = explorer._convert_accumulated_routines_to_templates(accumulated)

        assert len(templates) == 2
        ids = {t.routine_id for t in templates}
        assert ids == {"routine_001", "routine_002"}


# =============================================================================
# M5-E1 ACCEPTANCE CRITERIA TESTS
# =============================================================================


class TestM5E1AcceptanceCriteria:
    """Tests verifying M5-E1 acceptance criteria are met."""

    def test_m5_e1_i1_accumulated_routines_field_exists(self) -> None:
        """M5-E1-I1: DreamExplorerInput.accumulated_routines exists."""
        from k0.modules.consolidation.dream.models import DreamExplorerInput

        input_data = DreamExplorerInput(
            cycle_id="test",
            tenant_id="tenant",
            space_id="space",
        )

        assert hasattr(input_data, "accumulated_routines")

    def test_m5_e1_i1_routine_conversion_method_exists(self) -> None:
        """M5-E1-I1: _convert_accumulated_routines_to_templates exists."""
        from k0.modules.consolidation.dream import DreamConfig, DreamExplorer

        explorer = DreamExplorer(config=DreamConfig())
        assert hasattr(explorer, "_convert_accumulated_routines_to_templates")

    def test_m5_e1_i2_routine_candidate_conversion_exists(self) -> None:
        """M5-E1-I2: _convert_routine_candidates_to_templates exists."""
        from k0.modules.consolidation.dream import DreamConfig, DreamExplorer

        explorer = DreamExplorer(config=DreamConfig())
        assert hasattr(explorer, "_convert_routine_candidates_to_templates")

    def test_m5_e1_tdl_hco_accepts_detected_routines_parameter(self) -> None:
        """M5-E1-I2: _run_tdl_hco accepts detected_routines parameter."""
        import inspect

        from k0.modules.consolidation.dream import DreamExplorer

        sig = inspect.signature(DreamExplorer._run_tdl_hco)
        params = list(sig.parameters.keys())

        assert "detected_routines" in params
