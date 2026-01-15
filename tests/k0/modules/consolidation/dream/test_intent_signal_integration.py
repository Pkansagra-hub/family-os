"""
Test suite for Phase 3: R5 DreamExplorer Intent Signal Integration (GAP-001).

Validates:
1. IntentSignalDetector integration in DreamExplorer.explore()
2. intent_signals field in DreamExplorerOutput
3. R5PhaseOutputs.intent_signals field
4. Staging of intent_signals in P03PhaseOutputs

Plan Reference: docs/plans/INTENT_INGRESS_MATRIX_IMPLEMENTATION_PLAN.md Phase 3
"""

from __future__ import annotations

import pytest

from k0.modules.consolidation.dream.config import DreamConfig
from k0.modules.consolidation.dream.dream_explorer import DreamExplorer
from k0.modules.consolidation.dream.intent_signals import (
    DecisionSignal,
    EmotionalSignal,
    IntentSignalType,
    LessonSignal,
    MilestoneSignal,
    QueryBoostSignal,
    ReminderSignal,
)
from k0.modules.consolidation.dream.models import DreamExplorerInput, DreamExplorerOutput
from k0.pipelines.p03.event_state import P03EventState
from k0.pipelines.p03.phase_outputs import P03PhaseOutputs
from k0.pipelines.p03.phases.r5_dream_explorer import R5PhaseOutputs

# =============================================================================
# Fixtures
# =============================================================================


def make_event(
    event_id: str,
    intent_label: str,
    content_text: str,
    temporal_json: str = "[]",
    emotions_json: str = "[]",
    ner_entities_json: str = "[]",
) -> P03EventState:
    """Create a P03EventState with specified fields for testing."""
    return P03EventState(
        event_id=event_id,
        intent_label=intent_label,
        content_text=content_text,
        temporal_expressions_json=temporal_json,
        emotions_json=emotions_json,
        ner_entities_json=ner_entities_json,
    )


@pytest.fixture
def explorer() -> DreamExplorer:
    """Create DreamExplorer with default config."""
    return DreamExplorer(config=DreamConfig())


@pytest.fixture
def sample_input_with_intents() -> DreamExplorerInput:
    """Create sample input with intent-bearing events."""
    events = [
        make_event("evt_1", "set_reminder", "Remind me to call Mom tomorrow"),
        make_event("evt_2", "seek_advice", "Should I accept the job offer or stay?"),
        make_event("evt_3", "reflect", "I learned that patience is important"),
        make_event("evt_4", "express_feeling", "I feel so happy today!"),
        make_event("evt_5", "share_news", "Good news - I got promoted!"),
        make_event("evt_6", "query_memory", "When did we last visit Grandma?"),
        make_event("evt_7", "log_memory", "Just logging something"),  # No signal
    ]
    return DreamExplorerInput(
        cycle_id="01JTEST123456789ABCDEFGH",
        tenant_id="tenant-test",
        space_id="space-test",
        recent_episodes=[],
        kg_entities=[],
        kg_edges=[],
        event_states=events,
    )


@pytest.fixture
def sample_input_no_intents() -> DreamExplorerInput:
    """Create sample input without intent-bearing events."""
    events = [
        make_event("evt_1", "log_memory", "Just logging this"),
        make_event("evt_2", "", "No intent label"),
        make_event("evt_3", "other", "Something else"),
    ]
    return DreamExplorerInput(
        cycle_id="01JTEST123456789ABCDEFGH",
        tenant_id="tenant-test",
        space_id="space-test",
        recent_episodes=[],
        kg_entities=[],
        kg_edges=[],
        event_states=events,
    )


# =============================================================================
# Test: DreamExplorerOutput.intent_signals field
# =============================================================================


class TestDreamExplorerOutputIntentSignals:
    """Test intent_signals field in DreamExplorerOutput."""

    def test_output_has_intent_signals_field(self) -> None:
        """DreamExplorerOutput should have intent_signals field."""
        output = DreamExplorerOutput()
        assert hasattr(output, "intent_signals")
        assert output.intent_signals == []

    def test_total_outputs_includes_intent_signals(self) -> None:
        """total_outputs property should include intent_signals count."""
        output = DreamExplorerOutput()
        assert output.total_outputs == 0

        # Add a signal
        signal = ReminderSignal(
            signal_type=IntentSignalType.REMINDER,
            event_id="evt_1",
            confidence=0.8,
            source_text="Remind me",
            action_description="test",
            target_date=None,
        )
        output.intent_signals.append(signal)
        assert output.total_outputs == 1

    def test_is_empty_with_only_intent_signals(self) -> None:
        """is_empty should be False when only intent_signals present."""
        output = DreamExplorerOutput()
        assert output.is_empty is True

        signal = ReminderSignal(
            signal_type=IntentSignalType.REMINDER,
            event_id="evt_1",
            confidence=0.8,
            source_text="Remind me",
            action_description="test",
            target_date=None,
        )
        output.intent_signals.append(signal)
        assert output.is_empty is False


# =============================================================================
# Test: DreamExplorer.explore() Intent Detection
# =============================================================================


class TestDreamExplorerIntentDetection:
    """Test DreamExplorer.explore() detects intent signals."""

    @pytest.mark.asyncio
    async def test_explore_detects_all_intent_types(
        self,
        explorer: DreamExplorer,
        sample_input_with_intents: DreamExplorerInput,
    ) -> None:
        """explore() should detect all 6 intent signal types."""
        output = await explorer.explore(sample_input_with_intents)

        assert len(output.intent_signals) == 6

        signal_types = {s.signal_type for s in output.intent_signals}
        expected_types = {
            IntentSignalType.REMINDER,
            IntentSignalType.DECISION,
            IntentSignalType.LESSON,
            IntentSignalType.EMOTIONAL_TREND,
            IntentSignalType.MILESTONE,
            IntentSignalType.QUERY_BOOST,
        }
        assert signal_types == expected_types

    @pytest.mark.asyncio
    async def test_explore_no_signals_for_unsupported_intents(
        self,
        explorer: DreamExplorer,
        sample_input_no_intents: DreamExplorerInput,
    ) -> None:
        """explore() should return empty intent_signals for unsupported intents."""
        output = await explorer.explore(sample_input_no_intents)
        assert len(output.intent_signals) == 0

    @pytest.mark.asyncio
    async def test_explore_empty_events_no_crash(
        self,
        explorer: DreamExplorer,
    ) -> None:
        """explore() should handle empty event_states without crashing."""
        input_data = DreamExplorerInput(
            cycle_id="01JTEST123456789ABCDEFGH",
            tenant_id="tenant-test",
            space_id="space-test",
            event_states=[],
        )
        output = await explorer.explore(input_data)
        assert output.intent_signals == []

    @pytest.mark.asyncio
    async def test_explore_signal_types_correct(
        self,
        explorer: DreamExplorer,
        sample_input_with_intents: DreamExplorerInput,
    ) -> None:
        """explore() should return correct signal type instances."""
        output = await explorer.explore(sample_input_with_intents)

        # Find each signal type
        reminder = next((s for s in output.intent_signals if isinstance(s, ReminderSignal)), None)
        decision = next((s for s in output.intent_signals if isinstance(s, DecisionSignal)), None)
        lesson = next((s for s in output.intent_signals if isinstance(s, LessonSignal)), None)
        emotional = next((s for s in output.intent_signals if isinstance(s, EmotionalSignal)), None)
        milestone = next((s for s in output.intent_signals if isinstance(s, MilestoneSignal)), None)
        query = next((s for s in output.intent_signals if isinstance(s, QueryBoostSignal)), None)

        assert reminder is not None
        assert reminder.event_id == "evt_1"
        assert "call Mom" in reminder.action_description

        assert decision is not None
        assert decision.event_id == "evt_2"
        assert len(decision.options_mentioned) >= 1

        assert lesson is not None
        assert lesson.event_id == "evt_3"
        assert "patience" in lesson.lesson_description

        assert emotional is not None
        assert emotional.event_id == "evt_4"

        assert milestone is not None
        assert milestone.event_id == "evt_5"

        assert query is not None
        assert query.event_id == "evt_6"


# =============================================================================
# Test: R5PhaseOutputs.intent_signals field
# =============================================================================


class TestR5PhaseOutputsIntentSignals:
    """Test R5PhaseOutputs includes intent_signals field."""

    def test_r5_phase_outputs_has_intent_signals(self) -> None:
        """R5PhaseOutputs should have intent_signals field."""
        outputs = R5PhaseOutputs(
            insights=[],
            counterfactuals=[],
            routine_optimizations=[],
            prospective_memories=[],
        )
        assert hasattr(outputs, "intent_signals")
        assert outputs.intent_signals == []

    def test_r5_phase_outputs_accepts_signals(self) -> None:
        """R5PhaseOutputs should accept intent_signals in constructor."""
        signal = ReminderSignal(
            signal_type=IntentSignalType.REMINDER,
            event_id="evt_1",
            confidence=0.8,
            source_text="Remind me",
            action_description="test",
            target_date=None,
        )
        outputs = R5PhaseOutputs(
            insights=[],
            counterfactuals=[],
            routine_optimizations=[],
            prospective_memories=[],
            intent_signals=[signal],
        )
        assert len(outputs.intent_signals) == 1
        assert outputs.intent_signals[0].event_id == "evt_1"


# =============================================================================
# Test: P03PhaseOutputs.r5_intent_signals field
# =============================================================================


class TestP03PhaseOutputsIntentSignals:
    """Test P03PhaseOutputs includes r5_intent_signals field."""

    def test_p03_phase_outputs_has_r5_intent_signals(self) -> None:
        """P03PhaseOutputs should have r5_intent_signals field."""
        outputs = P03PhaseOutputs()
        assert hasattr(outputs, "r5_intent_signals")
        assert outputs.r5_intent_signals == []

    def test_total_insights_includes_intent_signals(self) -> None:
        """total_insights() should include r5_intent_signals count."""
        outputs = P03PhaseOutputs()
        assert outputs.total_insights() == 0

        signal = ReminderSignal(
            signal_type=IntentSignalType.REMINDER,
            event_id="evt_1",
            confidence=0.8,
            source_text="Remind me",
            action_description="test",
            target_date=None,
        )
        outputs.r5_intent_signals.append(signal)
        assert outputs.total_insights() == 1

    def test_to_summary_dict_includes_intent_signals(self) -> None:
        """to_summary_dict() should include intent_signals count."""
        outputs = P03PhaseOutputs()
        summary = outputs.to_summary_dict()
        assert "intent_signals" in summary["r5"]
        assert summary["r5"]["intent_signals"] == 0

        signal = ReminderSignal(
            signal_type=IntentSignalType.REMINDER,
            event_id="evt_1",
            confidence=0.8,
            source_text="Remind me",
            action_description="test",
            target_date=None,
        )
        outputs.r5_intent_signals.append(signal)
        summary = outputs.to_summary_dict()
        assert summary["r5"]["intent_signals"] == 1
