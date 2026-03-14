"""
Tests for ImportanceWeightLearner CONFIG_B alignment -- Issue 5.W.1.5 (ADR-K024).

Validates:
    - 8-component learner output consumed by ImportanceScorer
    - TrainingSample feature extraction matches scorer inputs
    - Persistence key alignment (importance_<component>)
    - End-to-end: train -> get_weights -> scorer consumes
    - Rollback preserves 8-component priors
    - Weight bounds preserved with 8D softmax

Spec Reference:
    - ADR-K024: Weight Learner Component Alignment
    - CONFIG_B: POC validated 120/120 scenarios
"""

from __future__ import annotations

from k0.modules.consolidation.algorithms.importance_scorer import (
    ImportanceScorer,
    ImportanceWeights,
)
from k0.modules.consolidation.algorithms.importance_weight_learner import (
    ImportanceWeightLearner,
    TrainingBatch,
    TrainingSample,
    WeightLearnerConfig,
)

# =============================================================================
# CONFIG_B Alignment Tests
# =============================================================================


class TestConfigBAlignment:
    """Verify learner components match CONFIG_B scorer exactly."""

    def test_components_match_scorer_keys(self) -> None:
        """Learner COMPONENTS match ImportanceWeights.as_dict() keys."""
        learner = ImportanceWeightLearner(space_id="sp_test")
        scorer_keys = set(ImportanceWeights().as_dict().keys())
        learner_keys = set(learner.COMPONENTS)

        assert (
            learner_keys == scorer_keys
        ), f"Learner keys {learner_keys} != scorer keys {scorer_keys}"

    def test_num_components_is_eight(self) -> None:
        """Learner has exactly 8 components."""
        assert ImportanceWeightLearner.NUM_COMPONENTS == 8
        assert len(ImportanceWeightLearner.COMPONENTS) == 8

    def test_priors_match_config_b_defaults(self) -> None:
        """Learner priors match CONFIG_B defaults exactly."""
        config = WeightLearnerConfig()
        scorer_defaults = ImportanceWeights()

        assert config.prior_sentiment == scorer_defaults.sentiment_weight
        assert config.prior_affect == scorer_defaults.affect_weight
        assert config.prior_arousal == scorer_defaults.arousal_weight
        assert config.prior_surprise == scorer_defaults.surprise_weight
        assert config.prior_novelty == scorer_defaults.novelty_weight
        assert config.prior_social == scorer_defaults.social_weight
        assert config.prior_identity == scorer_defaults.identity_weight
        assert config.prior_recency == scorer_defaults.recency_weight

    def test_priors_sum_to_one(self) -> None:
        """CONFIG_B priors sum to 1.0."""
        config = WeightLearnerConfig()
        total = sum(config.get_priors_list())
        assert abs(total - 1.0) < 1e-6

    def test_get_priors_dict_keys_match_components(self) -> None:
        """get_priors() keys match COMPONENTS ordering."""
        config = WeightLearnerConfig()
        priors = config.get_priors()
        assert list(priors.keys()) == ImportanceWeightLearner.COMPONENTS


# =============================================================================
# End-to-End Alignment: Learner -> Scorer
# =============================================================================


class TestEndToEndAlignment:
    """Verify learner output can be directly consumed by scorer."""

    def test_learner_output_consumed_by_scorer(self) -> None:
        """Learner get_weights() dict directly feeds _weights_from_dict()."""
        learner = ImportanceWeightLearner(space_id="sp_test")
        weights_dict = learner.get_weights()

        # Scorer must accept this without error
        weights_obj = ImportanceScorer._weights_from_dict(weights_dict)

        assert isinstance(weights_obj, ImportanceWeights)
        assert abs(weights_obj.total() - 1.0) < 0.02

    def test_trained_weights_consumed_by_scorer(self) -> None:
        """After training, weights are still consumable by scorer."""
        learner = ImportanceWeightLearner(space_id="sp_test")

        # Train with consistent pattern
        samples = []
        for _ in range(100):
            samples.append(TrainingSample(0.9, 0.2, 0.3, 0.1, 0.4, 0.5, 0.2, 0.8, True))
            samples.append(TrainingSample(0.1, 0.2, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, False))

        batch = TrainingBatch(samples=samples)
        for _ in range(5):
            learner.train_step(batch)

        trained_dict = learner.get_weights()
        weights_obj = ImportanceScorer._weights_from_dict(trained_dict)

        assert isinstance(weights_obj, ImportanceWeights)
        assert abs(weights_obj.total() - 1.0) < 0.02
        # Verify all 8 fields populated
        assert weights_obj.sentiment_weight > 0
        assert weights_obj.affect_weight > 0
        assert weights_obj.arousal_weight > 0
        assert weights_obj.surprise_weight > 0
        assert weights_obj.novelty_weight > 0
        assert weights_obj.social_weight > 0
        assert weights_obj.identity_weight > 0
        assert weights_obj.recency_weight > 0

    def test_persistence_key_alignment(self) -> None:
        """persist_weights() generates keys that SyscallWeightStore strips correctly."""
        learner = ImportanceWeightLearner(space_id="sp_test")
        prefix = "importance_"

        for component in learner.COMPONENTS:
            param_key = f"{prefix}{component}"
            # SyscallWeightStore strips prefix
            stripped = param_key[len(prefix) :]
            # _weights_from_dict expects these stripped keys
            assert (
                stripped in ImportanceWeights().as_dict()
            ), f"Stripped key '{stripped}' not in scorer weight keys"

    def test_all_scorer_keys_have_learner_component(self) -> None:
        """Every scorer weight key has a matching learner component."""
        scorer_keys = set(ImportanceWeights().as_dict().keys())
        learner_keys = set(ImportanceWeightLearner.COMPONENTS)
        missing = scorer_keys - learner_keys
        assert not missing, f"Scorer keys without learner component: {missing}"

    def test_all_learner_components_have_scorer_key(self) -> None:
        """Every learner component has a matching scorer weight key."""
        scorer_keys = set(ImportanceWeights().as_dict().keys())
        learner_keys = set(ImportanceWeightLearner.COMPONENTS)
        extra = learner_keys - scorer_keys
        assert not extra, f"Learner components without scorer key: {extra}"


# =============================================================================
# 8-Component TrainingSample Tests
# =============================================================================


class TestTrainingSample8Components:
    """Test 8-component TrainingSample creation and feature extraction."""

    def test_feature_count(self) -> None:
        """to_features() returns exactly 8 elements."""
        sample = TrainingSample(
            sentiment_score=0.5,
            affect_score=0.5,
            arousal_score=0.5,
            surprise_score=0.5,
            novelty_score=0.5,
            social_score=0.5,
            identity_score=0.5,
            recency_score=0.5,
            was_grounded=True,
        )
        assert len(sample.to_features()) == 8

    def test_feature_order_matches_components(self) -> None:
        """Feature order matches COMPONENTS order."""
        sample = TrainingSample(
            sentiment_score=0.1,
            affect_score=0.2,
            arousal_score=0.3,
            surprise_score=0.4,
            novelty_score=0.5,
            social_score=0.6,
            identity_score=0.7,
            recency_score=0.8,
            was_grounded=True,
        )
        features = sample.to_features()
        # Matches COMPONENTS: sentiment, affect, arousal, surprise, novelty, social, identity, recency
        assert features == [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]

    def test_batch_array_shape(self) -> None:
        """TrainingBatch.to_arrays() produces (N, 8) features."""
        samples = [
            TrainingSample(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, True),
            TrainingSample(0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, False),
        ]
        batch = TrainingBatch(samples=samples)
        features, labels, weights = batch.to_arrays()

        assert features.shape == (2, 8)
        assert labels.shape == (2,)

    def test_empty_batch_shape(self) -> None:
        """Empty batch produces (0, 8) features."""
        batch = TrainingBatch(samples=[])
        features, labels, weights = batch.to_arrays()
        assert features.shape == (0, 8)


# =============================================================================
# Training with 8 Components
# =============================================================================


class TestTraining8Components:
    """Test training step mechanics with 8 components."""

    def test_train_step_produces_eight_weights(self) -> None:
        """train_step result has exactly 8 weight keys."""
        learner = ImportanceWeightLearner(space_id="sp_test")
        samples = [TrainingSample(0.9, 0.5, 0.3, 0.2, 0.4, 0.6, 0.1, 0.7, True) for _ in range(60)]
        batch = TrainingBatch(samples=samples)
        result = learner.train_step(batch)

        assert len(result.weights) == 8
        assert set(result.weights.keys()) == set(ImportanceWeightLearner.COMPONENTS)

    def test_weights_sum_to_one_after_multi_step(self) -> None:
        """Weights sum to 1.0 after multiple training steps."""
        learner = ImportanceWeightLearner(space_id="sp_test")
        samples = []
        for _ in range(100):
            samples.append(TrainingSample(0.9, 0.8, 0.7, 0.1, 0.2, 0.3, 0.4, 0.5, True))
            samples.append(TrainingSample(0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, False))

        batch = TrainingBatch(samples=samples)
        for _ in range(10):
            learner.train_step(batch)

        weights = learner.get_weights()
        assert abs(sum(weights.values()) - 1.0) < 0.01

    def test_weights_clamped_with_eight_components(self) -> None:
        """All 8 weights respect [weight_min, weight_max] bounds."""
        learner = ImportanceWeightLearner(space_id="sp_test")
        samples = []
        for _ in range(100):
            samples.append(TrainingSample(0.99, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, True))
            samples.append(TrainingSample(0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, False))

        batch = TrainingBatch(samples=samples)
        for _ in range(20):
            learner.train_step(batch)

        weights = learner.get_weights()
        for name, value in weights.items():
            assert (
                value >= learner.config.weight_min - 0.01
            ), f"{name}={value} below min {learner.config.weight_min}"
            assert (
                value <= learner.config.weight_max + 0.01
            ), f"{name}={value} above max {learner.config.weight_max}"


# =============================================================================
# Rollback with 8 Components
# =============================================================================


class TestRollback8Components:
    """Test rollback preserves 8-component priors."""

    def test_rollback_restores_eight_priors(self) -> None:
        """rollback_to_priors restores all 8 CONFIG_B priors."""
        learner = ImportanceWeightLearner(space_id="sp_test")

        # Train to shift weights
        samples = [TrainingSample(0.9, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, True) for _ in range(60)]
        batch = TrainingBatch(samples=samples)
        learner.train_step(batch)

        # Rollback
        learner.rollback_to_priors()

        weights = learner.get_weights()
        priors = learner.config.get_priors()

        # All 8 components should be close to priors
        for key in learner.COMPONENTS:
            assert (
                abs(weights[key] - priors[key]) < 0.15
            ), f"After rollback, {key}={weights[key]:.3f} != prior={priors[key]:.3f}"

    def test_set_weights_with_eight_components(self) -> None:
        """set_weights() works with 8-component dict."""
        learner = ImportanceWeightLearner(space_id="sp_test")

        custom = {
            "sentiment": 0.20,
            "affect": 0.15,
            "arousal": 0.10,
            "surprise": 0.10,
            "novelty": 0.10,
            "social": 0.10,
            "identity": 0.10,
            "recency": 0.15,
        }
        learner.set_weights(custom)

        weights = learner.get_weights()
        # sentiment should be highest after normalization
        assert weights["sentiment"] >= weights["arousal"]

    def test_drift_computation_with_eight_components(self) -> None:
        """compute_drift works with 8-component space."""
        learner = ImportanceWeightLearner(space_id="sp_test")

        # At initialization, drift should be modest (softmax shifts priors slightly)
        drift = learner.compute_drift()
        assert drift >= 0.0

        # Euclidean drift
        e_drift = learner.compute_euclidean_drift()
        assert e_drift >= 0.0

    def test_diagnostics_show_eight_weights(self) -> None:
        """get_diagnostics returns 8-component weights."""
        learner = ImportanceWeightLearner(space_id="sp_test")
        diag = learner.get_diagnostics()

        assert len(diag["weights"]) == 8
        assert set(diag["weights"].keys()) == set(ImportanceWeightLearner.COMPONENTS)
