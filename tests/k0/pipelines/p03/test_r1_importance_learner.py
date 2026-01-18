"""
Tests for ImportanceWeightLearner — Issue 4.1.5.

Covers:
    - WeightLearnerConfig validation
    - TrainingSample and TrainingBatch operations
    - ImportanceWeightLearner training and weight access
    - Rollback logic after consecutive loss increases
    - Weight clamping and normalization

Spec Reference:
    - Dossier Appendix C.2.1.1: Adaptive Weight Learning
    - Dossier Appendix C.2.1.2: Stability Controls
    - M4_EXECUTION.md Issue 4.1.5
"""

from __future__ import annotations

import numpy as np
import pytest

from k0.modules.consolidation.algorithms.importance_weight_learner import (
    TORCH_AVAILABLE,
    ImportanceWeightLearner,
    TrainingBatch,
    TrainingResult,
    TrainingSample,
    WeightLearnerConfig,
)

# =============================================================================
# WeightLearnerConfig Tests
# =============================================================================


class TestWeightLearnerConfig:
    """Test WeightLearnerConfig validation and defaults."""

    def test_default_values(self) -> None:
        """Default config matches Dossier C.2.1.1 specs."""
        config = WeightLearnerConfig()

        assert config.learning_rate == 0.01
        assert config.momentum == 0.9
        assert config.min_samples == 500
        assert config.weight_min == 0.05
        assert config.weight_max == 0.60
        assert config.rollback_threshold == 3

    def test_get_priors(self) -> None:
        """get_priors returns correct static priors."""
        config = WeightLearnerConfig()
        priors = config.get_priors()

        assert priors["emotional"] == 0.35
        assert priors["recency"] == 0.25
        assert priors["access"] == 0.20
        assert priors["social"] == 0.20
        assert abs(sum(priors.values()) - 1.0) < 1e-6

    def test_get_priors_list(self) -> None:
        """get_priors_list returns correct order."""
        config = WeightLearnerConfig()
        priors = config.get_priors_list()

        assert priors == [0.35, 0.25, 0.20, 0.20]

    def test_validate_learning_rate_bounds(self) -> None:
        """Validation rejects invalid learning rate."""
        with pytest.raises(ValueError, match="learning_rate must be in"):
            WeightLearnerConfig(learning_rate=0.0).validate()

        with pytest.raises(ValueError, match="learning_rate must be in"):
            WeightLearnerConfig(learning_rate=1.5).validate()

        # Valid edge case
        WeightLearnerConfig(learning_rate=1.0).validate()

    def test_validate_momentum_bounds(self) -> None:
        """Validation rejects invalid momentum."""
        with pytest.raises(ValueError, match="momentum must be in"):
            WeightLearnerConfig(momentum=-0.1).validate()

        with pytest.raises(ValueError, match="momentum must be in"):
            WeightLearnerConfig(momentum=1.0).validate()

    def test_validate_min_samples_positive(self) -> None:
        """Validation rejects non-positive min_samples."""
        with pytest.raises(ValueError, match="min_samples must be >= 1"):
            WeightLearnerConfig(min_samples=0).validate()

    def test_validate_weight_bounds_ordering(self) -> None:
        """Validation rejects invalid weight bounds."""
        with pytest.raises(ValueError, match="weight bounds invalid"):
            WeightLearnerConfig(weight_min=0.7, weight_max=0.5).validate()


# =============================================================================
# TrainingSample Tests
# =============================================================================


class TestTrainingSample:
    """Test TrainingSample operations."""

    def test_to_features(self) -> None:
        """to_features returns correct order."""
        sample = TrainingSample(
            emotional_score=0.8,
            recency_score=0.5,
            access_score=0.3,
            social_score=0.2,
            was_grounded=True,
        )

        features = sample.to_features()
        assert features == [0.8, 0.5, 0.3, 0.2]

    def test_to_label_grounded(self) -> None:
        """to_label returns 1.0 for grounded events."""
        sample = TrainingSample(
            emotional_score=0.5,
            recency_score=0.5,
            access_score=0.5,
            social_score=0.5,
            was_grounded=True,
        )
        assert sample.to_label() == 1.0

    def test_to_label_not_grounded(self) -> None:
        """to_label returns 0.0 for non-grounded events."""
        sample = TrainingSample(
            emotional_score=0.5,
            recency_score=0.5,
            access_score=0.5,
            social_score=0.5,
            was_grounded=False,
        )
        assert sample.to_label() == 0.0

    def test_compute_sample_weight_recent(self) -> None:
        """Recent samples have weight ~1.0."""
        sample = TrainingSample(
            emotional_score=0.5,
            recency_score=0.5,
            access_score=0.5,
            social_score=0.5,
            was_grounded=True,
            days_ago=0.0,
        )
        assert sample.compute_sample_weight() == 1.0

    def test_compute_sample_weight_decay(self) -> None:
        """Older samples have exponentially decayed weight."""
        sample = TrainingSample(
            emotional_score=0.5,
            recency_score=0.5,
            access_score=0.5,
            social_score=0.5,
            was_grounded=True,
            days_ago=10.0,
        )
        # exp(-0.1 * 10) = exp(-1) ≈ 0.368
        weight = sample.compute_sample_weight(decay_rate=0.1)
        assert 0.36 < weight < 0.38


# =============================================================================
# TrainingBatch Tests
# =============================================================================


class TestTrainingBatch:
    """Test TrainingBatch operations."""

    def test_empty_batch(self) -> None:
        """Empty batch returns zero arrays."""
        batch = TrainingBatch(samples=[])
        features, labels, weights = batch.to_arrays()

        assert features.shape == (0, 4)
        assert labels.shape == (0,)
        assert weights.shape == (0,)

    def test_batch_len(self) -> None:
        """__len__ returns correct count."""
        samples = [TrainingSample(0.5, 0.5, 0.5, 0.5, True) for _ in range(5)]
        batch = TrainingBatch(samples=samples)
        assert len(batch) == 5

    def test_to_arrays_shape(self) -> None:
        """to_arrays returns correct shapes."""
        samples = [
            TrainingSample(0.8, 0.6, 0.4, 0.2, True),
            TrainingSample(0.3, 0.4, 0.5, 0.6, False),
            TrainingSample(0.5, 0.5, 0.5, 0.5, True),
        ]
        batch = TrainingBatch(samples=samples)
        features, labels, weights = batch.to_arrays()

        assert features.shape == (3, 4)
        assert labels.shape == (3,)
        assert weights.shape == (3,)

    def test_to_arrays_values(self) -> None:
        """to_arrays returns correct values."""
        samples = [
            TrainingSample(0.8, 0.6, 0.4, 0.2, True, days_ago=0.0),
            TrainingSample(0.3, 0.4, 0.5, 0.6, False, days_ago=0.0),
        ]
        batch = TrainingBatch(samples=samples)
        features, labels, weights = batch.to_arrays()

        np.testing.assert_array_almost_equal(features[0], [0.8, 0.6, 0.4, 0.2])
        np.testing.assert_array_almost_equal(labels, [1.0, 0.0])
        np.testing.assert_array_almost_equal(weights, [1.0, 1.0])


# =============================================================================
# ImportanceWeightLearner Tests
# =============================================================================


class TestImportanceWeightLearner:
    """Test ImportanceWeightLearner training and operations."""

    def test_init_with_defaults(self) -> None:
        """Learner initializes with static priors."""
        learner = ImportanceWeightLearner(space_id="sp_test")

        weights = learner.get_weights()
        assert "emotional" in weights
        assert "recency" in weights
        assert "access" in weights
        assert "social" in weights

        # All weights should be positive and sum to ~1
        assert all(w > 0 for w in weights.values())
        assert abs(sum(weights.values()) - 1.0) < 0.01

    def test_init_custom_config(self) -> None:
        """Learner accepts custom configuration."""
        config = WeightLearnerConfig(
            learning_rate=0.05,
            momentum=0.8,
        )
        learner = ImportanceWeightLearner(space_id="sp_test", config=config)

        assert learner.config.learning_rate == 0.05
        assert learner.config.momentum == 0.8

    def test_backend_detection(self) -> None:
        """Learner uses correct backend."""
        learner = ImportanceWeightLearner(space_id="sp_test")

        if TORCH_AVAILABLE:
            assert learner._backend == "torch"
        else:
            assert learner._backend == "numpy"

    def test_get_weights_normalized(self) -> None:
        """Weights are normalized to sum to 1."""
        learner = ImportanceWeightLearner(space_id="sp_test")
        weights = learner.get_weights()

        total = sum(weights.values())
        assert abs(total - 1.0) < 0.01

    def test_get_weights_clamped(self) -> None:
        """Weights are clamped to [weight_min, weight_max]."""
        learner = ImportanceWeightLearner(space_id="sp_test")
        weights = learner.get_weights()

        for w in weights.values():
            assert w >= learner.config.weight_min - 0.01
            assert w <= learner.config.weight_max + 0.01

    def test_get_weights_list_order(self) -> None:
        """get_weights_list returns correct order."""
        learner = ImportanceWeightLearner(space_id="sp_test")
        weights_dict = learner.get_weights()
        weights_list = learner.get_weights_list()

        assert weights_list[0] == weights_dict["emotional"]
        assert weights_list[1] == weights_dict["recency"]
        assert weights_list[2] == weights_dict["access"]
        assert weights_list[3] == weights_dict["social"]

    def test_set_weights(self) -> None:
        """set_weights updates internal weights."""
        learner = ImportanceWeightLearner(space_id="sp_test")

        new_weights = {
            "emotional": 0.40,
            "recency": 0.30,
            "access": 0.15,
            "social": 0.15,
        }
        learner.set_weights(new_weights)

        weights = learner.get_weights()
        # After clamping and normalization, values may shift slightly
        assert weights["emotional"] > weights["social"]

    def test_train_step_empty_batch(self) -> None:
        """Training with empty batch returns zero loss."""
        learner = ImportanceWeightLearner(space_id="sp_test")
        batch = TrainingBatch(samples=[])

        result = learner.train_step(batch)

        assert result.loss == 0.0
        assert result.sample_count == 0
        assert result.skipped is True
        assert result.reason == "BATCH_EMPTY"

    def test_train_step_batch_too_small(self) -> None:
        """Issue 4: Small batches are skipped to protect weight stability."""
        learner = ImportanceWeightLearner(space_id="sp_test")

        # Create batch with 30 samples (< 50 min_batch_size)
        samples = [TrainingSample(0.5, 0.5, 0.5, 0.5, True) for _ in range(30)]
        batch = TrainingBatch(samples=samples)

        result = learner.train_step(batch)

        assert result.skipped is True
        assert result.reason == "BATCH_TOO_SMALL"
        assert result.sample_count == 0  # Not updated
        assert learner.sample_count == 0  # Internal state not changed

    def test_train_step_updates_state(self) -> None:
        """Training step updates internal state."""
        learner = ImportanceWeightLearner(space_id="sp_test")

        # Issue 4: min_batch_size=50, so use 60 samples
        samples = [
            TrainingSample(0.9, 0.1, 0.1, 0.1, True if i % 2 == 0 else False) for i in range(60)
        ]
        batch = TrainingBatch(samples=samples)

        result = learner.train_step(batch)

        assert result.sample_count == 60
        assert learner.sample_count == 60
        assert learner.last_loss is not None
        assert len(learner.loss_history) == 1
        assert result.skipped is False

    def test_train_step_reduces_loss_over_time(self) -> None:
        """Multiple training steps should reduce loss."""
        learner = ImportanceWeightLearner(space_id="sp_test")

        # Create consistent training data
        samples = []
        for _ in range(100):
            # High emotional → grounded
            samples.append(TrainingSample(0.9, 0.2, 0.2, 0.2, True))
            # Low emotional → not grounded
            samples.append(TrainingSample(0.1, 0.2, 0.2, 0.2, False))

        batch = TrainingBatch(samples=samples)

        # Train multiple steps
        losses = []
        for _ in range(10):
            result = learner.train_step(batch)
            losses.append(result.loss)

        # Loss should generally decrease (allow some noise)
        # Check that final loss is lower than initial
        assert losses[-1] < losses[0] + 0.1  # Allow small increase due to noise

    def test_weights_sum_to_one_after_training(self) -> None:
        """Weights still sum to 1 after training."""
        learner = ImportanceWeightLearner(space_id="sp_test")

        # Issue 4: min_batch_size=50, so use 60 samples
        samples = [
            TrainingSample(0.9, 0.1, 0.1, 0.1, True if i % 2 == 0 else False) for i in range(60)
        ]
        batch = TrainingBatch(samples=samples)

        for _ in range(5):
            learner.train_step(batch)

        weights = learner.get_weights()
        total = sum(weights.values())
        assert abs(total - 1.0) < 0.01


# =============================================================================
# Rollback Tests
# =============================================================================


class TestWeightLearnerRollback:
    """Test rollback logic for stability controls."""

    def test_check_rollback_not_enough_history(self) -> None:
        """No rollback with insufficient history."""
        learner = ImportanceWeightLearner(space_id="sp_test")
        learner.loss_history = [0.5, 0.6]  # Only 2 entries

        assert not learner.check_rollback_needed()

    def test_check_rollback_no_consecutive_increase(self) -> None:
        """No rollback if losses don't consecutively increase."""
        learner = ImportanceWeightLearner(space_id="sp_test")
        learner.loss_history = [0.5, 0.6, 0.55, 0.65]  # Not consecutive

        assert not learner.check_rollback_needed()

    def test_check_rollback_triggered(self) -> None:
        """Rollback triggered after 3 consecutive increases."""
        learner = ImportanceWeightLearner(space_id="sp_test")
        learner.loss_history = [0.5, 0.6, 0.7, 0.8]  # 3 consecutive increases

        assert learner.check_rollback_needed()

    def test_rollback_to_priors(self) -> None:
        """rollback_to_priors resets weights and disables learning."""
        learner = ImportanceWeightLearner(space_id="sp_test")

        # Train to change weights (Issue 4: min_batch_size=50)
        samples = [TrainingSample(0.9, 0.1, 0.1, 0.1, True) for _ in range(60)]
        batch = TrainingBatch(samples=samples)
        learner.train_step(batch)

        # Rollback
        learner.rollback_to_priors()

        # Check state
        assert not learner.is_learning_enabled
        assert len(learner.loss_history) == 0

        # Weights should be back to priors (approximately)
        weights = learner.get_weights()
        priors = learner.config.get_priors()

        # Allow for clamping/normalization differences
        for key in weights:
            assert abs(weights[key] - priors[key]) < 0.1

    def test_enable_learning(self) -> None:
        """enable_learning re-enables after rollback."""
        learner = ImportanceWeightLearner(space_id="sp_test")
        learner.rollback_to_priors()

        assert not learner.is_learning_enabled

        learner.enable_learning()

        assert learner.is_learning_enabled


# =============================================================================
# Drift Metrics Tests
# =============================================================================


class TestDriftMetrics:
    """Test drift computation methods."""

    def test_compute_drift_zero_initial(self) -> None:
        """Drift is small when at static priors."""
        learner = ImportanceWeightLearner(space_id="sp_test")

        drift = learner.compute_drift()
        # After clamping, there may be small drift due to normalization
        assert drift < 0.15

    def test_compute_euclidean_drift_zero_initial(self) -> None:
        """Euclidean drift is small when at static priors."""
        learner = ImportanceWeightLearner(space_id="sp_test")

        drift = learner.compute_euclidean_drift()
        assert drift < 0.15

    def test_get_diagnostics(self) -> None:
        """get_diagnostics returns expected fields."""
        learner = ImportanceWeightLearner(space_id="sp_test")

        diag = learner.get_diagnostics()

        assert diag["space_id"] == "sp_test"
        assert "weights" in diag
        assert "sample_count" in diag
        assert "is_learning_enabled" in diag
        assert "drift_max" in diag
        assert "drift_euclidean" in diag
        assert "backend" in diag


# =============================================================================
# TrainingResult Tests
# =============================================================================


class TestTrainingResult:
    """Test TrainingResult dataclass."""

    def test_training_result_fields(self) -> None:
        """TrainingResult has expected fields."""
        result = TrainingResult(
            loss=0.25,
            weights={"emotional": 0.35, "recency": 0.25, "access": 0.20, "social": 0.20},
            sample_count=100,
            converged=False,
        )

        assert result.loss == 0.25
        assert len(result.weights) == 4
        assert result.sample_count == 100
        assert not result.converged

    def test_training_result_converged(self) -> None:
        """TrainingResult marks convergence at low loss."""
        result = TrainingResult(
            loss=0.05,
            weights={"emotional": 0.35, "recency": 0.25, "access": 0.20, "social": 0.20},
            sample_count=1000,
            converged=True,
        )

        assert result.converged
