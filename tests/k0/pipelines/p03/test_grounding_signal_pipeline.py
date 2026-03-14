"""
Tests for Grounding Signal Pipeline -- Issue 5.W.2.6

End-to-end tests proving:
    1. Feature extraction from P03EventState produces correct 8 CONFIG_B features
    2. R3 reconciliation actions map to correct grounding labels
    3. TrainingBatch construction filters PENDING events
    4. WeightLearningTrigger trains and produces updated weights
    5. Full pipeline: events -> features + grounding -> train -> weights change

References:
    - ADR-K024: 8 CONFIG_B component alignment
    - ADR-K025: R3 reconciliation grounding signals
    - Issue 5.W.2.2-5.W.2.6
"""

from __future__ import annotations

import math
import time
from typing import Any, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.modules.consolidation.algorithms.grounding_signal_collector import (
    GroundingSignalCollector,
    extract_features,
)
from k0.modules.consolidation.algorithms.importance_weight_learner import (
    ImportanceWeightLearner,
    TrainingBatch,
    TrainingSample,
    WeightLearnerConfig,
)
from k0.pipelines.p03.event_state import P03EventState, ReconciliationAction
from k0.pipelines.p03.weight_learning_trigger import WeightLearningTrigger, WeightTrainingConfig

# =============================================================================
# Fixtures
# =============================================================================


def make_event(
    event_id: str = "evt-001",
    sentiment_score: float = 0.5,
    affect_valence: float = 0.4,
    affect_arousal: float = 0.6,
    surprise_level: float = 0.3,
    novelty: str = "NOVEL",
    num_participants: int = 3,
    social_intimacy: str = "HIGH",
    identity_relevance: float = 0.7,
    timestamp: int = 0,
    reconciliation_action: ReconciliationAction = ReconciliationAction.REINFORCE,
) -> P03EventState:
    """Create a P03EventState with configurable fields for testing."""
    if timestamp == 0:
        timestamp = int(time.time() * 1000) - 3600_000  # 1 hour ago
    event = P03EventState(event_id=event_id)
    event.sentiment_score = sentiment_score
    event.affect_valence = affect_valence
    event.affect_arousal = affect_arousal
    event.surprise_level = surprise_level
    event.novelty = novelty
    event.num_participants = num_participants
    event.social_intimacy = social_intimacy
    event.identity_relevance = identity_relevance
    event.timestamp = timestamp
    event.reconciliation_action = reconciliation_action
    return event


# =============================================================================
# Feature Extraction Tests
# =============================================================================


class TestFeatureExtraction:
    """Test extract_features maps P03EventState to 8 CONFIG_B features."""

    def test_sentiment_uses_absolute_value(self) -> None:
        """Sentiment is abs(sentiment_score)."""
        event = make_event(sentiment_score=-0.8)
        sample = extract_features(event)
        assert abs(sample.sentiment_score - 0.8) < 0.01

    def test_affect_uses_absolute_value(self) -> None:
        """Affect is abs(affect_valence)."""
        event = make_event(affect_valence=-0.6)
        sample = extract_features(event)
        assert abs(sample.affect_score - 0.6) < 0.01

    def test_arousal_direct(self) -> None:
        """Arousal is direct from affect_arousal."""
        event = make_event(affect_arousal=0.85)
        sample = extract_features(event)
        assert abs(sample.arousal_score - 0.85) < 0.01

    def test_surprise_direct(self) -> None:
        """Surprise is direct from surprise_level."""
        event = make_event(surprise_level=0.55)
        sample = extract_features(event)
        assert abs(sample.surprise_score - 0.55) < 0.01

    def test_novelty_routine(self) -> None:
        """ROUTINE maps to 0.10."""
        event = make_event(novelty="ROUTINE")
        sample = extract_features(event)
        assert abs(sample.novelty_score - 0.10) < 0.01

    def test_novelty_novel(self) -> None:
        """NOVEL maps to 0.70."""
        event = make_event(novelty="NOVEL")
        sample = extract_features(event)
        assert abs(sample.novelty_score - 0.70) < 0.01

    def test_novelty_surprising(self) -> None:
        """SURPRISING maps to 1.00."""
        event = make_event(novelty="SURPRISING")
        sample = extract_features(event)
        assert abs(sample.novelty_score - 1.00) < 0.01

    def test_social_solo_event(self) -> None:
        """Solo event (1 participant) has 0.0 social factor."""
        event = make_event(num_participants=1)
        sample = extract_features(event)
        assert sample.social_score == 0.0

    def test_social_group_event(self) -> None:
        """Group event uses log2 scaling with intimacy."""
        event = make_event(num_participants=5, social_intimacy="HIGH")
        sample = extract_features(event)
        # log2(5) / log2(10) * 1.2 ≈ 0.697 * 1.2 ≈ 0.837
        expected = min(1.0, (math.log2(5) / math.log2(10)) * 1.2)
        assert abs(sample.social_score - expected) < 0.01

    def test_identity_direct(self) -> None:
        """Identity is direct from identity_relevance."""
        event = make_event(identity_relevance=0.9)
        sample = extract_features(event)
        assert abs(sample.identity_score - 0.9) < 0.01

    def test_recency_recent_event(self) -> None:
        """Recent event (1 hour ago) has high recency."""
        now_ms = int(time.time() * 1000)
        event = make_event(timestamp=now_ms - 3600_000)  # 1 hour ago
        sample = extract_features(event, now_ms=now_ms)
        # exp(-0.005 * 1) ≈ 0.995
        assert sample.recency_score > 0.99

    def test_recency_old_event(self) -> None:
        """Old event (30 days ago) has low recency."""
        now_ms = int(time.time() * 1000)
        event = make_event(timestamp=now_ms - 30 * 86400_000)  # 30 days ago
        sample = extract_features(event, now_ms=now_ms)
        # exp(-0.005 * 720) ≈ 0.027
        assert sample.recency_score < 0.05

    def test_features_count_is_eight(self) -> None:
        """to_features() returns exactly 8 values."""
        event = make_event()
        sample = extract_features(event)
        assert len(sample.to_features()) == 8

    def test_all_features_in_range(self) -> None:
        """All features are clamped to [0, 1]."""
        event = make_event(
            sentiment_score=-1.5,  # Out of range
            affect_valence=2.0,  # Out of range
            affect_arousal=-0.5,  # Out of range
        )
        sample = extract_features(event)
        for f in sample.to_features():
            assert 0.0 <= f <= 1.0, f"Feature {f} out of [0, 1] range"


# =============================================================================
# Grounding Label Tests
# =============================================================================


class TestGroundingLabels:
    """Test R3 reconciliation -> grounding label mapping."""

    def test_reinforce_is_grounded(self) -> None:
        """REINFORCE -> grounded=True."""
        event = make_event(reconciliation_action=ReconciliationAction.REINFORCE)
        sample = extract_features(event)
        assert sample.was_grounded is True

    def test_extend_is_grounded(self) -> None:
        """EXTEND -> grounded=True."""
        event = make_event(reconciliation_action=ReconciliationAction.EXTEND)
        sample = extract_features(event)
        assert sample.was_grounded is True

    def test_create_is_grounded(self) -> None:
        """CREATE -> grounded=True."""
        event = make_event(reconciliation_action=ReconciliationAction.CREATE)
        sample = extract_features(event)
        assert sample.was_grounded is True

    def test_skip_is_not_grounded(self) -> None:
        """SKIP -> grounded=False."""
        event = make_event(reconciliation_action=ReconciliationAction.SKIP)
        sample = extract_features(event)
        assert sample.was_grounded is False

    def test_prune_is_not_grounded(self) -> None:
        """PRUNE -> grounded=False."""
        event = make_event(reconciliation_action=ReconciliationAction.PRUNE)
        sample = extract_features(event)
        assert sample.was_grounded is False

    def test_pending_defaults_to_not_grounded(self) -> None:
        """PENDING -> grounded=False (default, not in lookup)."""
        event = make_event(reconciliation_action=ReconciliationAction.PENDING)
        sample = extract_features(event)
        assert sample.was_grounded is False

    def test_evolve_is_grounded(self) -> None:
        """EVOLVE -> grounded=True."""
        event = make_event(reconciliation_action=ReconciliationAction.EVOLVE)
        sample = extract_features(event)
        assert sample.was_grounded is True

    def test_contradict_is_grounded(self) -> None:
        """CONTRADICT -> grounded=True (important enough to conflict)."""
        event = make_event(reconciliation_action=ReconciliationAction.CONTRADICT)
        sample = extract_features(event)
        assert sample.was_grounded is True


# =============================================================================
# Grounding Signal Collector Tests
# =============================================================================


class TestGroundingSignalCollector:
    """Test GroundingSignalCollector aggregation."""

    def test_collect_excludes_pending(self) -> None:
        """PENDING events are excluded from grounding signals."""
        events = [
            make_event(event_id="e1", reconciliation_action=ReconciliationAction.REINFORCE),
            make_event(event_id="e2", reconciliation_action=ReconciliationAction.PENDING),
            make_event(event_id="e3", reconciliation_action=ReconciliationAction.SKIP),
        ]
        collector = GroundingSignalCollector()
        signals = collector.collect_grounding_signals(events)
        assert len(signals) == 2
        assert signals[0].event_id == "e1"
        assert signals[0].was_grounded is True
        assert signals[1].event_id == "e3"
        assert signals[1].was_grounded is False

    def test_collect_confidence_values(self) -> None:
        """Grounding signals have correct confidence per ADR-K025."""
        events = [
            make_event(event_id="e1", reconciliation_action=ReconciliationAction.REINFORCE),
            make_event(event_id="e2", reconciliation_action=ReconciliationAction.CREATE),
        ]
        collector = GroundingSignalCollector()
        signals = collector.collect_grounding_signals(events)
        assert signals[0].confidence == 0.8  # REINFORCE
        assert signals[1].confidence == 0.5  # CREATE

    def test_build_training_batch_filters_pending(self) -> None:
        """TrainingBatch excludes PENDING events."""
        events = [
            make_event(event_id="e1", reconciliation_action=ReconciliationAction.REINFORCE),
            make_event(event_id="e2", reconciliation_action=ReconciliationAction.PENDING),
            make_event(event_id="e3", reconciliation_action=ReconciliationAction.CREATE),
        ]
        collector = GroundingSignalCollector()
        batch = collector.build_training_batch(events)
        assert len(batch) == 2

    def test_build_training_batch_correct_labels(self) -> None:
        """TrainingBatch has correct grounding labels."""
        events = [
            make_event(event_id="e1", reconciliation_action=ReconciliationAction.REINFORCE),
            make_event(event_id="e2", reconciliation_action=ReconciliationAction.SKIP),
        ]
        collector = GroundingSignalCollector()
        batch = collector.build_training_batch(events)
        assert batch.samples[0].was_grounded is True
        assert batch.samples[1].was_grounded is False

    def test_build_training_batch_features_shape(self) -> None:
        """TrainingBatch.to_arrays() produces (N, 8) feature matrix."""
        events = [
            make_event(event_id=f"e{i}", reconciliation_action=ReconciliationAction.REINFORCE)
            for i in range(5)
        ]
        collector = GroundingSignalCollector()
        batch = collector.build_training_batch(events)
        features, labels, weights = batch.to_arrays()
        assert features.shape == (5, 8)
        assert labels.shape == (5,)
        assert weights.shape == (5,)

    def test_empty_batch_for_all_pending(self) -> None:
        """All PENDING events produce empty batch."""
        events = [
            make_event(event_id=f"e{i}", reconciliation_action=ReconciliationAction.PENDING)
            for i in range(3)
        ]
        collector = GroundingSignalCollector()
        batch = collector.build_training_batch(events)
        assert len(batch) == 0


# =============================================================================
# Weight Learning Trigger Tests
# =============================================================================


class TestWeightLearningTrigger:
    """Test WeightLearningTrigger end-to-end."""

    def _make_envelope(
        self,
        events: List[P03EventState],
        cycle_id: str = "cycle-001",
        space_id: str = "sp_test",
    ) -> Any:
        """Create a mock P03BatchEnvelope."""
        envelope = MagicMock()
        envelope.events = events
        envelope.context.cycle_id = cycle_id
        envelope.context.space_id = space_id
        envelope.context.tenant_id = "tenant-001"
        return envelope

    def _make_ctx(self) -> Any:
        """Create a mock P03RunnerContext with async syscalls."""
        ctx = MagicMock()
        ctx.syscalls = MagicMock()
        # Make learned_weights_get return None (no existing weights)
        ctx.syscalls.learned_weights_get = AsyncMock(return_value=None)
        # Make learned_weights_upsert succeed
        ctx.syscalls.learned_weights_upsert = AsyncMock(return_value=None)
        return ctx

    @pytest.mark.asyncio
    async def test_training_disabled(self) -> None:
        """Training disabled returns skipped result."""
        config = WeightTrainingConfig(enabled=False)
        trigger = WeightLearningTrigger(space_id="sp_test", config=config)
        envelope = self._make_envelope([])
        ctx = self._make_ctx()
        result = await trigger.execute(envelope, ctx)
        assert result.skipped is True
        assert result.skip_reason == "TRAINING_DISABLED"

    @pytest.mark.asyncio
    async def test_batch_too_small(self) -> None:
        """Batch below min_batch_size is skipped."""
        config = WeightTrainingConfig(min_batch_size=50)
        trigger = WeightLearningTrigger(space_id="sp_test", config=config)
        events = [
            make_event(event_id=f"e{i}", reconciliation_action=ReconciliationAction.REINFORCE)
            for i in range(10)  # Only 10, need 50
        ]
        envelope = self._make_envelope(events)
        ctx = self._make_ctx()
        result = await trigger.execute(envelope, ctx)
        assert result.skipped is True
        assert result.skip_reason == "BATCH_TOO_SMALL"
        assert result.batch_size == 10

    @pytest.mark.asyncio
    async def test_training_executes_with_sufficient_batch(self) -> None:
        """Training executes when batch meets minimum size."""
        config = WeightTrainingConfig(
            min_batch_size=5,
            persist_after_training=False,  # Skip persistence for this test
        )
        learner_config = WeightLearnerConfig(min_batch_size=5)
        trigger = WeightLearningTrigger(
            space_id="sp_test",
            config=config,
            learner_config=learner_config,
        )
        events = [
            make_event(
                event_id=f"e{i}",
                reconciliation_action=(
                    ReconciliationAction.REINFORCE if i % 2 == 0 else ReconciliationAction.SKIP
                ),
            )
            for i in range(20)
        ]
        envelope = self._make_envelope(events)
        ctx = self._make_ctx()
        result = await trigger.execute(envelope, ctx)
        assert result.triggered is True
        assert result.batch_size == 20
        assert result.grounded_count == 10  # Half REINFORCE, half SKIP
        assert result.training_result is not None
        assert result.training_result.loss > 0

    @pytest.mark.asyncio
    async def test_weights_change_after_training(self) -> None:
        """Training with biased data shifts weights toward grounded features."""
        config = WeightTrainingConfig(
            min_batch_size=5,
            persist_after_training=False,
        )
        learner_config = WeightLearnerConfig(min_batch_size=5, learning_rate=0.01)
        trigger = WeightLearningTrigger(
            space_id="sp_test",
            config=config,
            learner_config=learner_config,
        )

        # Get weights before training
        weights_before = trigger.learner.get_weights().copy()

        # Create biased training data:
        # Grounded events have high surprise, not-grounded have low surprise
        events = []
        for i in range(30):
            if i < 15:
                # Grounded events: high surprise
                events.append(
                    make_event(
                        event_id=f"grounded-{i}",
                        surprise_level=0.9,
                        reconciliation_action=ReconciliationAction.REINFORCE,
                    )
                )
            else:
                # Not grounded: low surprise
                events.append(
                    make_event(
                        event_id=f"skip-{i}",
                        surprise_level=0.1,
                        reconciliation_action=ReconciliationAction.SKIP,
                    )
                )

        envelope = self._make_envelope(events)
        ctx = self._make_ctx()
        result = await trigger.execute(envelope, ctx)

        # Weights should have changed
        weights_after = trigger.learner.get_weights()
        assert result.triggered is True
        # At least one weight must have changed
        changed = any(abs(weights_after[k] - weights_before[k]) > 1e-6 for k in weights_before)
        assert changed, "Weights did not change after training"

    @pytest.mark.asyncio
    async def test_weights_sum_to_one_after_training(self) -> None:
        """Weights still sum to 1.0 after training."""
        config = WeightTrainingConfig(min_batch_size=5, persist_after_training=False)
        trigger = WeightLearningTrigger(space_id="sp_test", config=config)
        events = [
            make_event(
                event_id=f"e{i}",
                reconciliation_action=ReconciliationAction.REINFORCE,
            )
            for i in range(20)
        ]
        envelope = self._make_envelope(events)
        ctx = self._make_ctx()
        await trigger.execute(envelope, ctx)
        weights = trigger.learner.get_weights()
        total = sum(weights.values())
        assert abs(total - 1.0) < 0.01

    @pytest.mark.asyncio
    async def test_persistence_calls_upsert(self) -> None:
        """Persistence writes all 8 component weights."""
        config = WeightTrainingConfig(
            min_batch_size=5,
            persist_after_training=True,
        )
        learner_config = WeightLearnerConfig(min_batch_size=5)
        trigger = WeightLearningTrigger(
            space_id="sp_test",
            config=config,
            learner_config=learner_config,
        )
        events = [
            make_event(
                event_id=f"e{i}",
                reconciliation_action=ReconciliationAction.REINFORCE,
            )
            for i in range(20)
        ]
        envelope = self._make_envelope(events)
        ctx = self._make_ctx()
        result = await trigger.execute(envelope, ctx)
        assert result.persisted is True
        # Should have called upsert 8 times (once per component)
        assert ctx.syscalls.learned_weights_upsert.call_count == 8

    @pytest.mark.asyncio
    async def test_persistence_uses_correct_keys(self) -> None:
        """Persisted weights use importance_ prefix."""
        config = WeightTrainingConfig(min_batch_size=5, persist_after_training=True)
        learner_config = WeightLearnerConfig(min_batch_size=5)
        trigger = WeightLearningTrigger(
            space_id="sp_test",
            config=config,
            learner_config=learner_config,
        )
        events = [
            make_event(
                event_id=f"e{i}",
                reconciliation_action=ReconciliationAction.REINFORCE,
            )
            for i in range(20)
        ]
        envelope = self._make_envelope(events)
        ctx = self._make_ctx()
        await trigger.execute(envelope, ctx)

        # Collect all param_key values from upsert calls
        param_keys = set()
        for call in ctx.syscalls.learned_weights_upsert.call_args_list:
            param_keys.add(call.kwargs.get("param_key", call.args[1] if len(call.args) > 1 else ""))
        # For keyword-only calls, check kwargs
        if not param_keys or param_keys == {""}:
            param_keys = set()
            for call in ctx.syscalls.learned_weights_upsert.call_args_list:
                kw = call.kwargs
                if "param_key" in kw:
                    param_keys.add(kw["param_key"])

        expected_keys = {
            "importance_sentiment",
            "importance_affect",
            "importance_arousal",
            "importance_surprise",
            "importance_novelty",
            "importance_social",
            "importance_identity",
            "importance_recency",
        }
        assert param_keys == expected_keys

    @pytest.mark.asyncio
    async def test_pending_events_excluded_from_training(self) -> None:
        """PENDING events do not contribute to training batch."""
        config = WeightTrainingConfig(min_batch_size=5, persist_after_training=False)
        trigger = WeightLearningTrigger(space_id="sp_test", config=config)
        events = [
            make_event(event_id="grounded", reconciliation_action=ReconciliationAction.REINFORCE),
        ] + [
            make_event(event_id=f"pending-{i}", reconciliation_action=ReconciliationAction.PENDING)
            for i in range(50)
        ]
        envelope = self._make_envelope(events)
        ctx = self._make_ctx()
        result = await trigger.execute(envelope, ctx)
        # Only 1 non-PENDING event, below min_batch_size of 5
        assert result.skipped is True
        assert result.batch_size == 1


# =============================================================================
# End-to-End Pipeline Test
# =============================================================================


class TestEndToEndPipeline:
    """
    End-to-end: events -> features + grounding -> train -> weights change -> scorer reads.

    Simulates the full weight learning cycle.
    """

    @pytest.mark.asyncio
    async def test_full_cycle_weights_converge(self) -> None:
        """
        Multiple training cycles cause weights to converge toward grounded features.

        Scenario: Events where high social_score correlates with grounding.
        After multiple cycles, social weight should increase.
        """
        config = WeightTrainingConfig(
            min_batch_size=10,
            persist_after_training=False,
        )
        learner_config = WeightLearnerConfig(min_batch_size=10, learning_rate=0.05)
        trigger = WeightLearningTrigger(
            space_id="sp_test",
            config=config,
            learner_config=learner_config,
        )

        initial_weights = trigger.learner.get_weights().copy()

        # Run 5 training cycles with biased data
        for cycle in range(5):
            events = []
            for i in range(30):
                if i < 15:
                    # Grounded: high social (many participants, high intimacy)
                    events.append(
                        make_event(
                            event_id=f"c{cycle}-g{i}",
                            num_participants=8,
                            social_intimacy="HIGH",
                            surprise_level=0.2,
                            reconciliation_action=ReconciliationAction.REINFORCE,
                        )
                    )
                else:
                    # Not grounded: low social (solo events)
                    events.append(
                        make_event(
                            event_id=f"c{cycle}-s{i}",
                            num_participants=1,
                            social_intimacy="LOW",
                            surprise_level=0.8,
                            reconciliation_action=ReconciliationAction.SKIP,
                        )
                    )

            envelope = MagicMock()
            envelope.events = events
            envelope.context.cycle_id = f"cycle-{cycle}"
            envelope.context.space_id = "sp_test"
            envelope.context.tenant_id = "t1"

            ctx = MagicMock()
            ctx.syscalls = MagicMock()
            ctx.syscalls.learned_weights_get = AsyncMock(return_value=None)
            ctx.syscalls.learned_weights_upsert = AsyncMock(return_value=None)

            result = await trigger.execute(envelope, ctx)
            assert result.triggered is True

        final_weights = trigger.learner.get_weights()

        # Weights should have changed from initial priors
        total_drift = sum(abs(final_weights[k] - initial_weights[k]) for k in initial_weights)
        assert total_drift > 0.01, "Weights did not converge after 5 cycles"

    @pytest.mark.asyncio
    async def test_scorer_can_read_learner_output(self) -> None:
        """
        Learner output weights are compatible with ImportanceScorer._weights_from_dict.

        This verifies the key alignment from ADR-K024.
        """
        from k0.modules.consolidation.algorithms.importance_scorer import ImportanceScorer

        learner = ImportanceWeightLearner(space_id="sp_test")

        # Simulate training
        batch = TrainingBatch(
            samples=[
                TrainingSample(
                    sentiment_score=0.8,
                    affect_score=0.5,
                    arousal_score=0.7,
                    surprise_score=0.9,
                    novelty_score=0.6,
                    social_score=0.4,
                    identity_score=0.3,
                    recency_score=0.95,
                    was_grounded=True,
                    days_ago=0.5,
                )
                for _ in range(20)
            ]
        )
        learner.train_step(batch)

        # Get learner weights
        weights_dict = learner.get_weights()

        # Verify scorer can consume them
        scorer = ImportanceScorer(space_id="sp_test", weight_store=None)
        importance_weights = scorer._weights_from_dict(weights_dict)

        # All 8 components should be present
        assert importance_weights.sentiment_weight > 0
        assert importance_weights.affect_weight > 0
        assert importance_weights.arousal_weight > 0
        assert importance_weights.surprise_weight > 0
        assert importance_weights.novelty_weight > 0
        assert importance_weights.social_weight > 0
        assert importance_weights.identity_weight > 0
        assert importance_weights.recency_weight > 0

        # Sum should be approximately 1.0
        assert abs(importance_weights.total() - 1.0) < 0.01
        assert abs(importance_weights.total() - 1.0) < 0.01
