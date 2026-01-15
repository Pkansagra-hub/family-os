"""
Tests for UnifiedDecayEngine.

Issue: 4.3.3
Spec Reference: M4_EXECUTION.md, Dossier 4.4.1.1
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pytest

from k0.modules.consolidation.algorithms.decay_engine import (
    LAYER_LAMBDAS,
    MS_PER_DAY,
    DecayClassification,
    DecayConfig,
    UnifiedDecayEngine,
)

if TYPE_CHECKING:
    pass


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def engine() -> UnifiedDecayEngine:
    """Default engine fixture."""
    return UnifiedDecayEngine()


@pytest.fixture
def custom_engine() -> UnifiedDecayEngine:
    """Engine with custom config."""
    config = DecayConfig(
        base_lambda=0.05,
        importance_modifier=0.4,
        confidence_modifier=0.2,
        archive_threshold=0.15,
        tombstone_threshold=0.02,
    )
    return UnifiedDecayEngine(config)


# =============================================================================
# 4.3.3.T1: Base λ Lookup Tests
# =============================================================================


class TestBaseLambdaLookup:
    """Test base λ lookup for all 8 tables."""

    def test_st_hipp_events_lambda(self, engine: UnifiedDecayEngine) -> None:
        """st_hipp_events has λ=0.100 (fastest decay)."""
        assert engine.get_base_lambda("st_hipp_events") == 0.100

    def test_st_prospective_lambda(self, engine: UnifiedDecayEngine) -> None:
        """st_prospective has λ=0.020."""
        assert engine.get_base_lambda("st_prospective") == 0.020

    def test_st_procedural_lambda(self, engine: UnifiedDecayEngine) -> None:
        """st_procedural has λ=0.010."""
        assert engine.get_base_lambda("st_procedural") == 0.010

    def test_st_kg_edges_lambda(self, engine: UnifiedDecayEngine) -> None:
        """st_kg_edges has λ=0.008."""
        assert engine.get_base_lambda("st_kg_edges") == 0.008

    def test_st_epi_lambda(self, engine: UnifiedDecayEngine) -> None:
        """st_epi has λ=0.005."""
        assert engine.get_base_lambda("st_epi") == 0.005

    def test_st_sem_lambda(self, engine: UnifiedDecayEngine) -> None:
        """st_sem has λ=0.003."""
        assert engine.get_base_lambda("st_sem") == 0.003

    def test_st_social_lambda(self, engine: UnifiedDecayEngine) -> None:
        """st_social has λ=0.002."""
        assert engine.get_base_lambda("st_social") == 0.002

    def test_st_kg_dom_lambda(self, engine: UnifiedDecayEngine) -> None:
        """st_kg_dom has λ=0.001 (slowest decay)."""
        assert engine.get_base_lambda("st_kg_dom") == 0.001

    def test_unknown_table_uses_default(self, engine: UnifiedDecayEngine) -> None:
        """Unknown table falls back to base_lambda (0.01)."""
        assert engine.get_base_lambda("st_unknown") == 0.01

    def test_layer_lambdas_dict_complete(self) -> None:
        """LAYER_LAMBDAS contains all 8 expected tables."""
        expected_tables = {
            "st_epi",
            "st_sem",
            "st_procedural",
            "st_social",
            "st_kg_dom",
            "st_kg_edges",
            "st_prospective",
            "st_hipp_events",
        }
        assert set(LAYER_LAMBDAS.keys()) == expected_tables


# =============================================================================
# 4.3.3.T2: Decay Formula Tests
# =============================================================================


class TestDecayFormula:
    """Test exponential decay formula: decay = exp(-λ_effective × days)."""

    def test_no_time_passed_returns_one(self, engine: UnifiedDecayEngine) -> None:
        """decay_factor=1.0 when no time has passed."""
        now = 1700000000000
        decay = engine.compute_decay_factor(
            table_name="st_epi",
            last_observed_at=now,
            current_time=now,
        )
        assert decay == 1.0

    def test_negative_time_returns_one(self, engine: UnifiedDecayEngine) -> None:
        """decay_factor=1.0 when current_time < last_observed_at (clock skew)."""
        decay = engine.compute_decay_factor(
            table_name="st_epi",
            last_observed_at=1700000000000,
            current_time=1699000000000,
        )
        assert decay == 1.0

    def test_st_hipp_events_7_days_with_reinforcement(self, engine: UnifiedDecayEngine) -> None:
        """st_hipp_events after 7 days with default reinforcement factor."""
        now = 1700000000000
        seven_days_ago = now - (7 * MS_PER_DAY)

        decay = engine.compute_decay_factor(
            table_name="st_hipp_events",
            last_observed_at=seven_days_ago,
            current_time=now,
        )

        # λ_effective = 0.100 × reinforcement_factor
        # reinforcement_factor = 1.0 / (1.0 + 0.1 × 1) = 0.909...
        # λ_effective ≈ 0.0909
        # decay = exp(-0.0909 × 7) ≈ 0.529
        effective_lambda = 0.100 * (1.0 / 1.1)
        expected = math.exp(-effective_lambda * 7)
        assert abs(decay - expected) < 0.001

    def test_st_epi_139_days_halflife(self, engine: UnifiedDecayEngine) -> None:
        """st_epi with λ=0.005 has ~139-day half-life (base λ only)."""
        half_life = engine.get_half_life_days("st_epi")
        # ln(2) / 0.005 ≈ 138.6
        assert 138 < half_life < 140

    def test_one_year_decay_st_sem_with_reinforcement(self, engine: UnifiedDecayEngine) -> None:
        """Semantic memory after 1 year with default reinforcement."""
        now = 1700000000000
        one_year_ago = now - (365 * MS_PER_DAY)

        decay = engine.compute_decay_factor(
            table_name="st_sem",
            last_observed_at=one_year_ago,
            current_time=now,
        )

        # λ_effective = 0.003 × (1/1.1) ≈ 0.00273
        effective_lambda = 0.003 * (1.0 / 1.1)
        expected = math.exp(-effective_lambda * 365)
        assert abs(decay - expected) < 0.001

    def test_decay_clamped_to_zero_minimum(self, engine: UnifiedDecayEngine) -> None:
        """Decay factor never goes below 0.0."""
        now = 1700000000000
        very_long_ago = now - (10000 * MS_PER_DAY)  # ~27 years

        decay = engine.compute_decay_factor(
            table_name="st_hipp_events",
            last_observed_at=very_long_ago,
            current_time=now,
        )

        assert decay >= 0.0
        # After 10000 days: exp(-λ × 10000) ≈ 0
        assert decay < 0.0001


# =============================================================================
# 4.3.3.T3: Effective λ Modifier Tests
# =============================================================================


class TestEffectiveLambdaModifiers:
    """Test λ adjustment for importance, confidence, observation count."""

    def test_high_importance_reduces_lambda(self, engine: UnifiedDecayEngine) -> None:
        """importance_score=1.0 halves λ (before reinforcement factor)."""
        base_lambda = engine.get_base_lambda("st_epi")  # 0.005

        effective = engine.compute_effective_lambda(
            table_name="st_epi",
            importance_score=1.0,
            confidence_score=0.0,
            observation_count=1,
        )

        # importance_factor = 1.0 - (1.0 × 0.5) = 0.5
        # reinforcement_factor = 1.0 / (1.0 + 0.1 × 1) = 0.909...
        expected = base_lambda * 0.5 * (1.0 / 1.1)
        assert abs(effective - expected) < 0.0001

    def test_high_confidence_reduces_lambda(self, engine: UnifiedDecayEngine) -> None:
        """confidence_score=1.0 reduces λ by 30% (before reinforcement factor)."""
        base_lambda = engine.get_base_lambda("st_epi")  # 0.005

        effective = engine.compute_effective_lambda(
            table_name="st_epi",
            importance_score=0.0,
            confidence_score=1.0,
            observation_count=1,
        )

        # confidence_factor = 1.0 - (1.0 × 0.3) = 0.7
        # reinforcement_factor = 1.0 / 1.1 = 0.909...
        expected = base_lambda * 0.7 * (1.0 / 1.1)
        assert abs(effective - expected) < 0.0001

    def test_high_observation_count_reduces_lambda(self, engine: UnifiedDecayEngine) -> None:
        """observation_count=10 produces reinforcement_factor=0.5."""
        base_lambda = engine.get_base_lambda("st_epi")  # 0.005

        effective = engine.compute_effective_lambda(
            table_name="st_epi",
            importance_score=0.0,
            confidence_score=0.0,
            observation_count=10,
        )

        # reinforcement_factor = 1.0 / (1.0 + 0.1 × 10) = 0.5
        expected = base_lambda * 0.5
        assert abs(effective - expected) < 0.0001

    def test_combined_modifiers(self, engine: UnifiedDecayEngine) -> None:
        """All modifiers combine multiplicatively."""
        base_lambda = engine.get_base_lambda("st_epi")  # 0.005

        effective = engine.compute_effective_lambda(
            table_name="st_epi",
            importance_score=1.0,  # factor=0.5
            confidence_score=1.0,  # factor=0.7
            observation_count=10,  # factor=0.5
        )

        expected = base_lambda * 0.5 * 0.7 * 0.5
        assert abs(effective - expected) < 0.0001

    def test_space_modifier(self, engine: UnifiedDecayEngine) -> None:
        """space_modifier=2.0 doubles λ (with default reinforcement)."""
        base_lambda = engine.get_base_lambda("st_epi")

        effective = engine.compute_effective_lambda(
            table_name="st_epi",
            space_modifier=2.0,
        )

        # reinforcement_factor = 1.0 / 1.1 (default observation_count=1)
        expected = base_lambda * 2.0 * (1.0 / 1.1)
        assert abs(effective - expected) < 0.0001

    def test_entity_type_modifier(self, engine: UnifiedDecayEngine) -> None:
        """entity_type_modifier=0.5 halves λ (with default reinforcement)."""
        base_lambda = engine.get_base_lambda("st_epi")

        effective = engine.compute_effective_lambda(
            table_name="st_epi",
            entity_type_modifier=0.5,
        )

        # reinforcement_factor = 1.0 / 1.1
        expected = base_lambda * 0.5 * (1.0 / 1.1)
        assert abs(effective - expected) < 0.0001

    def test_input_clamping_importance(self, engine: UnifiedDecayEngine) -> None:
        """importance_score clamped to [0, 1]."""
        base_lambda = engine.get_base_lambda("st_epi")

        # Negative gets clamped to 0 (importance_factor=1.0)
        effective_neg = engine.compute_effective_lambda(
            table_name="st_epi",
            importance_score=-0.5,
        )
        # Only reinforcement_factor applies
        expected_neg = base_lambda * (1.0 / 1.1)
        assert abs(effective_neg - expected_neg) < 0.0001

        # >1 gets clamped to 1 (importance_factor=0.5)
        effective_high = engine.compute_effective_lambda(
            table_name="st_epi",
            importance_score=1.5,
        )
        expected = base_lambda * 0.5 * (1.0 / 1.1)
        assert abs(effective_high - expected) < 0.0001


# =============================================================================
# 4.3.3.T4: Classification Tests
# =============================================================================


class TestDecayClassification:
    """Test decay factor classification into lifecycle states."""

    def test_active_above_archive_threshold(self, engine: UnifiedDecayEngine) -> None:
        """decay_factor >= 0.10 → ACTIVE."""
        assert engine.classify_record(1.0) == DecayClassification.ACTIVE
        assert engine.classify_record(0.5) == DecayClassification.ACTIVE
        assert engine.classify_record(0.10) == DecayClassification.ACTIVE

    def test_archive_candidate_between_thresholds(self, engine: UnifiedDecayEngine) -> None:
        """0.01 <= decay_factor < 0.10 → ARCHIVE_CANDIDATE."""
        assert engine.classify_record(0.09) == DecayClassification.ARCHIVE_CANDIDATE
        assert engine.classify_record(0.05) == DecayClassification.ARCHIVE_CANDIDATE
        assert engine.classify_record(0.01) == DecayClassification.ARCHIVE_CANDIDATE

    def test_prune_candidate_below_tombstone(self, engine: UnifiedDecayEngine) -> None:
        """decay_factor < 0.01 → PRUNE_CANDIDATE."""
        assert engine.classify_record(0.009) == DecayClassification.PRUNE_CANDIDATE
        assert engine.classify_record(0.001) == DecayClassification.PRUNE_CANDIDATE
        assert engine.classify_record(0.0) == DecayClassification.PRUNE_CANDIDATE

    def test_boundary_at_archive_threshold(self, engine: UnifiedDecayEngine) -> None:
        """Boundary: 0.10 is ACTIVE, 0.099 is ARCHIVE_CANDIDATE."""
        assert engine.classify_record(0.10) == DecayClassification.ACTIVE
        assert engine.classify_record(0.099) == DecayClassification.ARCHIVE_CANDIDATE

    def test_boundary_at_tombstone_threshold(self, engine: UnifiedDecayEngine) -> None:
        """Boundary: 0.01 is ARCHIVE_CANDIDATE, 0.009 is PRUNE_CANDIDATE."""
        assert engine.classify_record(0.01) == DecayClassification.ARCHIVE_CANDIDATE
        assert engine.classify_record(0.009) == DecayClassification.PRUNE_CANDIDATE

    def test_custom_thresholds(self, custom_engine: UnifiedDecayEngine) -> None:
        """Custom config uses different thresholds."""
        # Custom: archive=0.15, tombstone=0.02
        assert custom_engine.classify_record(0.15) == DecayClassification.ACTIVE
        assert custom_engine.classify_record(0.14) == DecayClassification.ARCHIVE_CANDIDATE
        assert custom_engine.classify_record(0.02) == DecayClassification.ARCHIVE_CANDIDATE
        assert custom_engine.classify_record(0.019) == DecayClassification.PRUNE_CANDIDATE


# =============================================================================
# 4.3.3.T5: Configuration Tests
# =============================================================================


class TestDecayConfig:
    """Test DecayConfig validation."""

    def test_default_config_valid(self) -> None:
        """Default config is valid."""
        config = DecayConfig()
        config.validate()  # Should not raise

    def test_negative_lambda_raises(self) -> None:
        """base_lambda <= 0 raises ValueError."""
        config = DecayConfig(base_lambda=-0.01)
        with pytest.raises(ValueError, match="base_lambda must be > 0"):
            config.validate()

    def test_zero_lambda_raises(self) -> None:
        """base_lambda = 0 raises ValueError."""
        config = DecayConfig(base_lambda=0)
        with pytest.raises(ValueError, match="base_lambda must be > 0"):
            config.validate()

    def test_importance_modifier_out_of_range(self) -> None:
        """importance_modifier outside [0, 1] raises ValueError."""
        config = DecayConfig(importance_modifier=1.5)
        with pytest.raises(ValueError, match="importance_modifier must be in"):
            config.validate()

    def test_confidence_modifier_out_of_range(self) -> None:
        """confidence_modifier outside [0, 1] raises ValueError."""
        config = DecayConfig(confidence_modifier=-0.1)
        with pytest.raises(ValueError, match="confidence_modifier must be in"):
            config.validate()

    def test_tombstone_greater_than_archive_raises(self) -> None:
        """tombstone_threshold >= archive_threshold raises ValueError."""
        config = DecayConfig(archive_threshold=0.10, tombstone_threshold=0.15)
        with pytest.raises(ValueError, match="tombstone_threshold"):
            config.validate()

    def test_config_to_dict(self) -> None:
        """to_dict() returns all config fields."""
        config = DecayConfig()
        d = config.to_dict()

        assert d["base_lambda"] == 0.01
        assert d["importance_modifier"] == 0.5
        assert d["confidence_modifier"] == 0.3
        assert d["archive_threshold"] == 0.10
        assert d["tombstone_threshold"] == 0.01


# =============================================================================
# 4.3.3.T6: Convenience Method Tests
# =============================================================================


class TestConvenienceMethods:
    """Test compute_and_classify, days_until_archive, get_layer_info."""

    def test_compute_and_classify(self, engine: UnifiedDecayEngine) -> None:
        """compute_and_classify returns tuple of (decay, classification)."""
        now = 1700000000000
        seven_days_ago = now - (7 * MS_PER_DAY)

        decay, classification = engine.compute_and_classify(
            table_name="st_epi",
            last_observed_at=seven_days_ago,
            current_time=now,
        )

        # st_epi λ=0.005 with reinforcement_factor = 1/1.1
        # λ_effective ≈ 0.00455
        effective_lambda = 0.005 * (1.0 / 1.1)
        expected_decay = math.exp(-effective_lambda * 7)
        assert abs(decay - expected_decay) < 0.001
        assert classification == DecayClassification.ACTIVE

    def test_days_until_archive_fresh(self, engine: UnifiedDecayEngine) -> None:
        """Fresh record (decay=1.0): days until archive with reinforcement."""
        days = engine.days_until_archive(
            table_name="st_epi",
            current_decay=1.0,
        )

        # λ_effective = 0.005 × (1/1.1) ≈ 0.00455
        # Solve: 0.10 = 1.0 × exp(-λ_eff × days)
        # days = -ln(0.10) / λ_eff = ln(10) / 0.00455 ≈ 507 days
        effective_lambda = 0.005 * (1.0 / 1.1)
        expected = math.log(10) / effective_lambda
        assert abs(days - expected) < 1

    def test_days_until_archive_already_archived(self, engine: UnifiedDecayEngine) -> None:
        """Already below threshold returns 0."""
        days = engine.days_until_archive(
            table_name="st_epi",
            current_decay=0.05,  # Already ARCHIVE_CANDIDATE
        )
        assert days == 0.0

    def test_get_layer_info(self, engine: UnifiedDecayEngine) -> None:
        """get_layer_info returns layer details."""
        info = engine.get_layer_info("st_epi")

        assert info["table_name"] == "st_epi"
        assert info["base_lambda"] == 0.005
        assert 138 < info["half_life_days"] < 140
        assert info["archive_threshold"] == 0.10
        assert info["tombstone_threshold"] == 0.01

    def test_get_all_layers_info(self, engine: UnifiedDecayEngine) -> None:
        """get_all_layers_info returns info for all 8 tables."""
        all_info = engine.get_all_layers_info()

        assert len(all_info) == 8
        assert "st_epi" in all_info
        assert "st_hipp_events" in all_info
        assert all_info["st_hipp_events"]["base_lambda"] == 0.100


# =============================================================================
# 4.3.3.T7: Realistic Scenario Tests
# =============================================================================


class TestRealisticScenarios:
    """Test realistic memory decay scenarios."""

    def test_birthday_memory_one_year_later(self, engine: UnifiedDecayEngine) -> None:
        """
        Birthday episodic memory after 1 year.
        High importance (0.9), high confidence (0.8), accessed 5 times.
        """
        now = 1700000000000
        one_year_ago = now - (365 * MS_PER_DAY)

        decay = engine.compute_decay_factor(
            table_name="st_epi",
            last_observed_at=one_year_ago,
            current_time=now,
            importance_score=0.9,
            confidence_score=0.8,
            observation_count=5,
        )

        # Should still be healthy due to high importance
        assert decay > 0.5  # Still well above archive threshold
        assert engine.classify_record(decay) == DecayClassification.ACTIVE

    def test_grocery_list_one_week_later(self, engine: UnifiedDecayEngine) -> None:
        """
        Short-term grocery list in st_hipp_events after 1 week.
        Low importance (0.1), no reinforcement.
        """
        now = 1700000000000
        one_week_ago = now - (7 * MS_PER_DAY)

        decay = engine.compute_decay_factor(
            table_name="st_hipp_events",
            last_observed_at=one_week_ago,
            current_time=now,
            importance_score=0.1,
            confidence_score=0.5,
            observation_count=1,
        )

        # Should be quite decayed (near half-life)
        assert decay < 0.6
        assert decay > 0.3

    def test_core_concept_five_years_later(self, engine: UnifiedDecayEngine) -> None:
        """
        Core concept in st_kg_dom after 5 years.
        High importance (1.0), many observations (100).
        """
        now = 1700000000000
        five_years_ago = now - (1825 * MS_PER_DAY)

        decay = engine.compute_decay_factor(
            table_name="st_kg_dom",
            last_observed_at=five_years_ago,
            current_time=now,
            importance_score=1.0,
            confidence_score=1.0,
            observation_count=100,
        )

        # st_kg_dom has slowest decay (λ=0.001)
        # With modifiers, should persist for very long
        assert decay > 0.5
        assert engine.classify_record(decay) == DecayClassification.ACTIVE
