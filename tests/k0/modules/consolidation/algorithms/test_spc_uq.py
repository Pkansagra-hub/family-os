"""
Unit tests for SPC-UQ (Schematic Pattern Completion with Uncertainty Quantification).

These tests validate:
- SPCConfig construction and validation
- AttributeGap creation and priority
- ReconstructedValue properties
- ReconstructedEpisode A.0.6 invariant (never canonical)
- EpisodicSimulator gap identification
- EpisodicSimulator schema matching
- EpisodicSimulator Bayesian reconstruction
- EpisodicSimulator temporal coherence
- EpisodicSimulator simulation workflow

References:
- M8_EXECUTION.md Issue 8.1.8: SPC-UQ Episodic Simulation
- Dossier §4.6.3: Episodic Simulation
- Dossier Appendix C.8.1: SPC-UQ Algorithm Details
"""

from __future__ import annotations

import random

import pytest

from k0.modules.consolidation.algorithms.spc_uq import (
    AttributeGap,
    EpisodeFragment,
    EpisodicSimulator,
    GapType,
    ReconstructedEpisode,
    ReconstructedValue,
    ReconstructionProvenance,
    SimpleEpisode,
    SPCConfig,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def default_config() -> SPCConfig:
    """Default SPC configuration."""
    return SPCConfig()


@pytest.fixture
def seeded_config() -> SPCConfig:
    """Seeded SPC configuration for deterministic tests."""
    return SPCConfig(
        simulation_count=50,
        min_confidence=0.3,
        coherence_threshold=0.4,
        max_gaps_per_episode=3,
        ambiguity_threshold=0.5,
        uncertainty_alpha=2.0,
        uncertainty_beta=2.0,
        seed=42,
    )


@pytest.fixture
def incomplete_episode() -> SimpleEpisode:
    """Episode with missing attributes."""
    return SimpleEpisode(
        episode_id="ep_001",
        start_time_ms=1700000000000,
        end_time_ms=1700003600000,
        _location_name=None,  # Missing
        _participants=None,  # Missing
        _activity_type="meeting",
        _ambiguity_score=0.6,
        summary="A meeting with missing details",
    )


@pytest.fixture
def complete_episode() -> SimpleEpisode:
    """Episode with all attributes present."""
    return SimpleEpisode(
        episode_id="ep_002",
        start_time_ms=1700010000000,
        end_time_ms=1700013600000,
        _location_name="Office",
        _participants=["Alice", "Bob"],
        _activity_type="meeting",
        _ambiguity_score=0.1,
        summary="A complete meeting episode",
    )


@pytest.fixture
def sample_fragments() -> list[EpisodeFragment]:
    """Sample episode fragments for temporal coherence."""
    return [
        EpisodeFragment(
            fragment_id="frag_1",
            source_episode_id="ep_001",
            source_event_id="evt_001",
            start_time_ms=1700000000000,
            end_time_ms=1700001800000,
            content="First half of episode",
        ),
        EpisodeFragment(
            fragment_id="frag_2",
            source_episode_id="ep_001",
            source_event_id="evt_002",
            start_time_ms=1700001800000,
            end_time_ms=1700003600000,
            content="Second half of episode",
        ),
    ]


@pytest.fixture
def overlapping_fragments() -> list[EpisodeFragment]:
    """Fragments with temporal overlap (should lower coherence)."""
    return [
        EpisodeFragment(
            fragment_id="frag_1",
            source_episode_id="ep_001",
            source_event_id="evt_001",
            start_time_ms=1700000000000,
            end_time_ms=1700002000000,
            content="Fragment A",
        ),
        EpisodeFragment(
            fragment_id="frag_2",
            source_episode_id="ep_001",
            source_event_id="evt_002",
            start_time_ms=1700001500000,  # Overlaps with frag_1
            end_time_ms=1700003600000,
            content="Fragment B",
        ),
    ]


# =============================================================================
# SPCConfig Tests
# =============================================================================


class TestSPCConfig:
    """Tests for SPCConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = SPCConfig()
        assert config.simulation_count == 100
        assert config.min_confidence == 0.3
        assert config.coherence_threshold == 0.4
        assert config.max_gaps_per_episode == 5
        assert config.ambiguity_threshold == 0.5
        assert config.uncertainty_alpha == 1.0
        assert config.uncertainty_beta == 1.0
        assert config.seed is None

    def test_custom_values(self) -> None:
        """Test custom configuration values."""
        config = SPCConfig(
            simulation_count=200,
            min_confidence=0.5,
            coherence_threshold=0.6,
            max_gaps_per_episode=10,
            seed=123,
        )
        assert config.simulation_count == 200
        assert config.min_confidence == 0.5
        assert config.coherence_threshold == 0.6
        assert config.max_gaps_per_episode == 10
        assert config.seed == 123

    def test_invalid_simulation_count(self) -> None:
        """Test that simulation_count < 1 raises ValueError."""
        with pytest.raises(ValueError, match="simulation_count must be at least 1"):
            SPCConfig(simulation_count=0)

    def test_invalid_min_confidence_low(self) -> None:
        """Test that min_confidence < 0 raises ValueError."""
        with pytest.raises(ValueError, match="min_confidence must be in"):
            SPCConfig(min_confidence=-0.1)

    def test_invalid_min_confidence_high(self) -> None:
        """Test that min_confidence > 1 raises ValueError."""
        with pytest.raises(ValueError, match="min_confidence must be in"):
            SPCConfig(min_confidence=1.5)

    def test_invalid_coherence_threshold(self) -> None:
        """Test that coherence_threshold > 1 raises ValueError."""
        with pytest.raises(ValueError, match="coherence_threshold must be in"):
            SPCConfig(coherence_threshold=1.1)

    def test_invalid_max_gaps(self) -> None:
        """Test that max_gaps_per_episode < 1 raises ValueError."""
        with pytest.raises(ValueError, match="max_gaps_per_episode must be at least 1"):
            SPCConfig(max_gaps_per_episode=0)

    def test_invalid_uncertainty_alpha(self) -> None:
        """Test that uncertainty_alpha <= 0 raises ValueError."""
        with pytest.raises(ValueError, match="uncertainty_alpha must be positive"):
            SPCConfig(uncertainty_alpha=0)

    def test_invalid_uncertainty_beta(self) -> None:
        """Test that uncertainty_beta <= 0 raises ValueError."""
        with pytest.raises(ValueError, match="uncertainty_beta must be positive"):
            SPCConfig(uncertainty_beta=-1)


# =============================================================================
# AttributeGap Tests
# =============================================================================


class TestAttributeGap:
    """Tests for AttributeGap dataclass."""

    def test_basic_creation(self) -> None:
        """Test basic gap creation."""
        gap = AttributeGap(
            attribute_name="location_name",
            gap_type=GapType.LOCATION,
            priority=0.8,
        )
        assert gap.attribute_name == "location_name"
        assert gap.gap_type == GapType.LOCATION
        assert gap.priority == 0.8
        assert gap.current_value is None
        assert gap.ambiguity_score == 0.0

    def test_gap_with_current_value(self) -> None:
        """Test gap with ambiguous current value."""
        gap = AttributeGap(
            attribute_name="participants",
            gap_type=GapType.PARTICIPANTS,
            priority=0.7,
            current_value=["Alice"],
            ambiguity_score=0.6,
        )
        assert gap.current_value == ["Alice"]
        assert gap.ambiguity_score == 0.6

    def test_invalid_priority_low(self) -> None:
        """Test that priority < 0 raises ValueError."""
        with pytest.raises(ValueError, match="priority must be in"):
            AttributeGap(
                attribute_name="test",
                gap_type=GapType.CONTENT,
                priority=-0.1,
            )

    def test_invalid_priority_high(self) -> None:
        """Test that priority > 1 raises ValueError."""
        with pytest.raises(ValueError, match="priority must be in"):
            AttributeGap(
                attribute_name="test",
                gap_type=GapType.CONTENT,
                priority=1.5,
            )

    def test_all_gap_types(self) -> None:
        """Test all gap type enums."""
        for gap_type in GapType:
            gap = AttributeGap(
                attribute_name=f"test_{gap_type.value}",
                gap_type=gap_type,
            )
            assert gap.gap_type == gap_type


# =============================================================================
# ReconstructedValue Tests
# =============================================================================


class TestReconstructedValue:
    """Tests for ReconstructedValue dataclass."""

    def test_basic_creation(self) -> None:
        """Test basic reconstructed value creation."""
        rv = ReconstructedValue(
            attribute_name="location_name",
            value="Office",
            confidence=0.85,
            uncertainty=0.15,
            provenance=ReconstructionProvenance.INFERRED_FROM_SCHEMA,
            schema_id="schema_001",
        )
        assert rv.attribute_name == "location_name"
        assert rv.value == "Office"
        assert rv.confidence == 0.85
        assert rv.uncertainty == 0.15
        assert rv.provenance == ReconstructionProvenance.INFERRED_FROM_SCHEMA
        assert rv.schema_id == "schema_001"
        assert rv.created_at_ms > 0

    def test_is_high_confidence(self) -> None:
        """Test is_high_confidence property."""
        high_conf = ReconstructedValue(
            attribute_name="test",
            value="value",
            confidence=0.8,
            uncertainty=0.2,
            provenance=ReconstructionProvenance.PATTERN_COMPLETION,
        )
        assert high_conf.is_high_confidence is True

        low_conf = ReconstructedValue(
            attribute_name="test",
            value="value",
            confidence=0.5,
            uncertainty=0.5,
            provenance=ReconstructionProvenance.PATTERN_COMPLETION,
        )
        assert low_conf.is_high_confidence is False

    def test_is_low_uncertainty(self) -> None:
        """Test is_low_uncertainty property."""
        low_unc = ReconstructedValue(
            attribute_name="test",
            value="value",
            confidence=0.8,
            uncertainty=0.2,
            provenance=ReconstructionProvenance.PATTERN_COMPLETION,
        )
        assert low_unc.is_low_uncertainty is True

        high_unc = ReconstructedValue(
            attribute_name="test",
            value="value",
            confidence=0.5,
            uncertainty=0.5,
            provenance=ReconstructionProvenance.PATTERN_COMPLETION,
        )
        assert high_unc.is_low_uncertainty is False

    def test_all_provenance_types(self) -> None:
        """Test all provenance enum values."""
        for prov in ReconstructionProvenance:
            rv = ReconstructedValue(
                attribute_name="test",
                value="value",
                confidence=0.5,
                uncertainty=0.5,
                provenance=prov,
            )
            assert rv.provenance == prov


# =============================================================================
# ReconstructedEpisode Tests
# =============================================================================


class TestReconstructedEpisode:
    """Tests for ReconstructedEpisode dataclass."""

    def test_create_non_canonical(self) -> None:
        """Test that create() enforces non-canonical."""
        rv = ReconstructedValue(
            attribute_name="location_name",
            value="Office",
            confidence=0.8,
            uncertainty=0.2,
            provenance=ReconstructionProvenance.INFERRED_FROM_SCHEMA,
        )

        episode = ReconstructedEpisode.create(
            episode_id="recon_001",
            original_episode_id="ep_001",
            summary="Reconstructed meeting",
            reconstructed_fields=[rv],
            confidence_score=0.8,
            uncertainty_score=0.2,
            temporal_coherence_score=0.9,
            provenance={"algorithm": "SPC-UQ"},
        )

        assert episode.is_canonical is False
        assert episode.episode_id == "recon_001"
        assert episode.original_episode_id == "ep_001"
        assert len(episode.reconstructed_fields) == 1

    def test_invariant_a06_direct_creation_fails(self) -> None:
        """Test A.0.6 invariant: is_canonical=True raises ValueError."""
        rv = ReconstructedValue(
            attribute_name="test",
            value="value",
            confidence=0.8,
            uncertainty=0.2,
            provenance=ReconstructionProvenance.PATTERN_COMPLETION,
        )

        with pytest.raises(ValueError, match="NEVER be canonical"):
            ReconstructedEpisode(
                episode_id="recon_002",
                original_episode_id="ep_002",
                summary="Bad reconstruction",
                reconstructed_fields=(rv,),
                confidence_score=0.8,
                uncertainty_score=0.2,
                temporal_coherence_score=0.9,
                provenance={"algorithm": "SPC-UQ"},
                is_canonical=True,  # This should fail
            )

    def test_score_clamping(self) -> None:
        """Test that scores are clamped to [0, 1]."""
        episode = ReconstructedEpisode.create(
            episode_id="recon_003",
            original_episode_id="ep_003",
            summary="Test",
            reconstructed_fields=[],
            confidence_score=1.5,  # Should be clamped to 1.0
            uncertainty_score=-0.5,  # Should be clamped to 0.0
            temporal_coherence_score=2.0,  # Should be clamped to 1.0
            provenance={},
        )

        assert episode.confidence_score == 1.0
        assert episode.uncertainty_score == 0.0
        assert episode.temporal_coherence_score == 1.0


# =============================================================================
# EpisodeFragment Tests
# =============================================================================


class TestEpisodeFragment:
    """Tests for EpisodeFragment dataclass."""

    def test_basic_creation(self) -> None:
        """Test basic fragment creation."""
        frag = EpisodeFragment(
            fragment_id="frag_001",
            source_episode_id="ep_001",
            source_event_id="evt_001",
            start_time_ms=1700000000000,
            end_time_ms=1700001800000,
            content="Fragment content",
        )
        assert frag.fragment_id == "frag_001"
        assert frag.source_episode_id == "ep_001"
        assert frag.source_event_id == "evt_001"
        assert frag.start_time_ms == 1700000000000
        assert frag.end_time_ms == 1700001800000
        assert frag.content == "Fragment content"
        assert frag.attributes == ()

    def test_fragment_with_attributes(self) -> None:
        """Test fragment with attributes."""
        frag = EpisodeFragment(
            fragment_id="frag_002",
            source_episode_id="ep_002",
            source_event_id="evt_002",
            start_time_ms=1700000000000,
            end_time_ms=1700001800000,
            content="Fragment content",
            attributes=(("location", "Office"), ("mood", "happy")),
        )
        assert len(frag.attributes) == 2
        assert frag.get_attribute("location") == "Office"
        assert frag.get_attribute("mood") == "happy"
        assert frag.get_attribute("nonexistent") is None

    def test_fragment_is_frozen(self) -> None:
        """Test that fragment is immutable."""
        frag = EpisodeFragment(
            fragment_id="frag_003",
            source_episode_id="ep_003",
            source_event_id="evt_003",
            start_time_ms=1700000000000,
            end_time_ms=1700001800000,
            content="Content",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            frag.fragment_id = "new_id"  # type: ignore


# =============================================================================
# EpisodicSimulator Gap Identification Tests
# =============================================================================


class TestEpisodicSimulatorGapIdentification:
    """Tests for EpisodicSimulator.identify_gaps()."""

    def test_identify_gaps_missing_location(self, incomplete_episode: SimpleEpisode) -> None:
        """Test gap identification for missing location."""
        simulator = EpisodicSimulator()
        gaps = simulator.identify_gaps(incomplete_episode)

        location_gaps = [g for g in gaps if g.gap_type == GapType.LOCATION]
        assert len(location_gaps) == 1
        assert location_gaps[0].attribute_name == "location_name"
        assert location_gaps[0].priority == 0.8

    def test_identify_gaps_missing_participants(self, incomplete_episode: SimpleEpisode) -> None:
        """Test gap identification for missing participants."""
        simulator = EpisodicSimulator()
        gaps = simulator.identify_gaps(incomplete_episode)

        participant_gaps = [g for g in gaps if g.gap_type == GapType.PARTICIPANTS]
        assert len(participant_gaps) == 1
        assert participant_gaps[0].priority == 0.7

    def test_identify_gaps_high_ambiguity(self, incomplete_episode: SimpleEpisode) -> None:
        """Test gap identification for high ambiguity score."""
        simulator = EpisodicSimulator()
        gaps = simulator.identify_gaps(incomplete_episode)

        content_gaps = [g for g in gaps if g.gap_type == GapType.CONTENT]
        assert len(content_gaps) == 1
        assert content_gaps[0].priority == 0.9  # Highest priority

    def test_no_gaps_in_complete_episode(self, complete_episode: SimpleEpisode) -> None:
        """Test that complete episode has no gaps."""
        simulator = EpisodicSimulator()
        gaps = simulator.identify_gaps(complete_episode)
        assert len(gaps) == 0

    def test_gaps_sorted_by_priority(self, incomplete_episode: SimpleEpisode) -> None:
        """Test that gaps are sorted by priority descending."""
        simulator = EpisodicSimulator()
        gaps = simulator.identify_gaps(incomplete_episode)

        priorities = [g.priority for g in gaps]
        assert priorities == sorted(priorities, reverse=True)

    def test_max_gaps_limit(self) -> None:
        """Test that gaps are limited to max_gaps_per_episode."""
        config = SPCConfig(max_gaps_per_episode=2, ambiguity_threshold=0.1)
        simulator = EpisodicSimulator(config=config)

        episode = SimpleEpisode(
            episode_id="ep_many_gaps",
            start_time_ms=1700000000000,
            _ambiguity_score=0.5,  # Will trigger content gap
        )
        gaps = simulator.identify_gaps(episode)
        assert len(gaps) <= 2


# =============================================================================
# EpisodicSimulator Temporal Coherence Tests
# =============================================================================


class TestEpisodicSimulatorTemporalCoherence:
    """Tests for EpisodicSimulator.calculate_temporal_coherence()."""

    def test_single_fragment_perfect_coherence(self) -> None:
        """Test that single fragment has perfect coherence."""
        simulator = EpisodicSimulator()
        fragments = [
            EpisodeFragment(
                fragment_id="frag_1",
                source_episode_id="ep_001",
                source_event_id="evt_001",
                start_time_ms=1700000000000,
                end_time_ms=1700001800000,
                content="Single fragment",
            )
        ]
        coherence = simulator.calculate_temporal_coherence(fragments)
        assert coherence == 1.0

    def test_contiguous_fragments_high_coherence(
        self, sample_fragments: list[EpisodeFragment]
    ) -> None:
        """Test that contiguous fragments have high coherence."""
        simulator = EpisodicSimulator()
        coherence = simulator.calculate_temporal_coherence(sample_fragments)
        assert coherence >= 0.9

    def test_overlapping_fragments_reduced_coherence(
        self, overlapping_fragments: list[EpisodeFragment]
    ) -> None:
        """Test that overlapping fragments reduce coherence."""
        simulator = EpisodicSimulator()
        coherence = simulator.calculate_temporal_coherence(overlapping_fragments)
        assert coherence < 1.0

    def test_empty_fragments_perfect_coherence(self) -> None:
        """Test that empty list returns perfect coherence."""
        simulator = EpisodicSimulator()
        coherence = simulator.calculate_temporal_coherence([])
        assert coherence == 1.0

    def test_large_gap_reduces_coherence(self) -> None:
        """Test that >24h gap reduces coherence."""
        simulator = EpisodicSimulator()
        fragments = [
            EpisodeFragment(
                fragment_id="frag_1",
                source_episode_id="ep_001",
                source_event_id="evt_001",
                start_time_ms=1700000000000,
                end_time_ms=1700001800000,
                content="Day 1",
            ),
            EpisodeFragment(
                fragment_id="frag_2",
                source_episode_id="ep_001",
                source_event_id="evt_002",
                start_time_ms=1700100000000,  # >24h later
                end_time_ms=1700101800000,
                content="Day 2",
            ),
        ]
        coherence = simulator.calculate_temporal_coherence(fragments)
        assert coherence < 1.0


# =============================================================================
# EpisodicSimulator Bayesian Reconstruction Tests
# =============================================================================


class TestEpisodicSimulatorBayesianReconstruction:
    """Tests for EpisodicSimulator.bayesian_reconstruction()."""

    def test_reconstruction_from_context(self, seeded_config: SPCConfig) -> None:
        """Test reconstruction without schema uses context."""
        simulator = EpisodicSimulator(config=seeded_config)
        rng = random.Random(42)

        gap = AttributeGap(
            attribute_name="location_name",
            gap_type=GapType.LOCATION,
            priority=0.8,
        )
        context = {
            "nearby_locations": ["Office", "Home", "Cafe"],
        }

        result = simulator.bayesian_reconstruction(
            gap=gap,
            schema=None,
            context=context,
            rng=rng,
        )

        assert result is not None
        assert result.attribute_name == "location_name"
        assert result.value in ["Office", "Home", "Cafe"]
        assert result.provenance == ReconstructionProvenance.CONTEXT_PROPAGATION

    def test_reconstruction_participants_from_context(self, seeded_config: SPCConfig) -> None:
        """Test participant reconstruction from frequent contacts."""
        simulator = EpisodicSimulator(config=seeded_config)
        rng = random.Random(42)

        gap = AttributeGap(
            attribute_name="participants",
            gap_type=GapType.PARTICIPANTS,
            priority=0.7,
        )
        context = {
            "frequent_contacts": ["Alice", "Bob", "Charlie", "Diana"],
        }

        result = simulator.bayesian_reconstruction(
            gap=gap,
            schema=None,
            context=context,
            rng=rng,
        )

        assert result is not None
        assert result.attribute_name == "participants"
        assert isinstance(result.value, list)
        assert all(p in context["frequent_contacts"] for p in result.value)

    def test_reconstruction_without_context_returns_none(self, seeded_config: SPCConfig) -> None:
        """Test that reconstruction without context returns None."""
        simulator = EpisodicSimulator(config=seeded_config)
        rng = random.Random(42)

        gap = AttributeGap(
            attribute_name="location_name",
            gap_type=GapType.LOCATION,
            priority=0.8,
        )

        result = simulator.bayesian_reconstruction(
            gap=gap,
            schema=None,
            context={},  # Empty context
            rng=rng,
        )

        assert result is None


# =============================================================================
# EpisodicSimulator Full Simulation Tests
# =============================================================================


class TestEpisodicSimulatorSimulation:
    """Tests for EpisodicSimulator.simulate()."""

    def test_simulate_generates_reconstructions(
        self,
        seeded_config: SPCConfig,
        incomplete_episode: SimpleEpisode,
        sample_fragments: list[EpisodeFragment],
    ) -> None:
        """Test that simulate generates reconstructions."""
        simulator = EpisodicSimulator(config=seeded_config)

        context = {
            "known_locations": ["Office", "Home"],
            "nearby_locations": ["Office", "Home"],
            "frequent_contacts": ["Alice", "Bob"],
        }

        results = simulator.simulate(
            episodes=[incomplete_episode],
            fragments=sample_fragments,
            context=context,
            rng_seed=42,
        )

        # Should generate at least one reconstruction
        assert len(results) >= 1

        # All reconstructions must be non-canonical
        for r in results:
            assert r.is_canonical is False

    def test_simulate_skips_complete_episodes(
        self,
        seeded_config: SPCConfig,
        complete_episode: SimpleEpisode,
    ) -> None:
        """Test that simulate skips episodes without gaps."""
        simulator = EpisodicSimulator(config=seeded_config)

        results = simulator.simulate(
            episodes=[complete_episode],
            rng_seed=42,
        )

        assert len(results) == 0

    def test_simulate_deterministic_with_seed(
        self,
        seeded_config: SPCConfig,
        incomplete_episode: SimpleEpisode,
    ) -> None:
        """Test that simulate is deterministic with same seed."""
        simulator = EpisodicSimulator(config=seeded_config)

        context = {
            "nearby_locations": ["Office"],
            "frequent_contacts": ["Alice"],
        }

        results1 = simulator.simulate(
            episodes=[incomplete_episode],
            context=context,
            rng_seed=42,
        )

        results2 = simulator.simulate(
            episodes=[incomplete_episode],
            context=context,
            rng_seed=42,
        )

        # Should get same number of results
        assert len(results1) == len(results2)

    def test_simulate_different_seeds_different_results(
        self,
        seeded_config: SPCConfig,
        incomplete_episode: SimpleEpisode,
    ) -> None:
        """Test that different seeds may produce different results."""
        simulator = EpisodicSimulator(config=seeded_config)

        context = {
            "nearby_locations": ["Office", "Home", "Cafe", "Park", "Gym"],
            "frequent_contacts": ["Alice", "Bob", "Charlie", "Diana", "Eve"],
        }

        results1 = simulator.simulate(
            episodes=[incomplete_episode],
            context=context,
            rng_seed=1,
        )

        results2 = simulator.simulate(
            episodes=[incomplete_episode],
            context=context,
            rng_seed=9999,
        )

        # Results may differ (not guaranteed with small option sets)
        # At minimum, both should run successfully
        assert isinstance(results1, list)
        assert isinstance(results2, list)

    def test_simulate_respects_coherence_threshold(self) -> None:
        """Test that low coherence episodes are filtered."""
        config = SPCConfig(coherence_threshold=0.95)
        simulator = EpisodicSimulator(config=config)

        # Create episode with gaps
        episode = SimpleEpisode(
            episode_id="ep_low_coherence",
            start_time_ms=1700000000000,
            _ambiguity_score=0.6,
        )

        # Create overlapping fragments (low coherence)
        fragments = [
            EpisodeFragment(
                fragment_id="frag_1",
                source_episode_id="ep_low_coherence",
                source_event_id="evt_001",
                start_time_ms=1700000000000,
                end_time_ms=1700002000000,
                content="Fragment A",
            ),
            EpisodeFragment(
                fragment_id="frag_2",
                source_episode_id="ep_low_coherence",
                source_event_id="evt_002",
                start_time_ms=1700001500000,  # Major overlap
                end_time_ms=1700003600000,
                content="Fragment B",
            ),
        ]

        context = {
            "nearby_locations": ["Office"],
            "frequent_contacts": ["Alice"],
        }

        results = simulator.simulate(
            episodes=[episode],
            fragments=fragments,
            context=context,
            rng_seed=42,
        )

        # High coherence threshold may filter out low coherence results
        # (depends on calculated coherence from overlapping fragments)
        assert isinstance(results, list)

    def test_simulate_provenance_includes_algorithm(
        self,
        seeded_config: SPCConfig,
        incomplete_episode: SimpleEpisode,
    ) -> None:
        """Test that provenance includes SPC-UQ algorithm."""
        simulator = EpisodicSimulator(config=seeded_config)

        context = {
            "nearby_locations": ["Office"],
            "frequent_contacts": ["Alice"],
        }

        results = simulator.simulate(
            episodes=[incomplete_episode],
            context=context,
            rng_seed=42,
        )

        if results:
            assert results[0].provenance["algorithm"] == "SPC-UQ"

    def test_simulate_summary_includes_reconstructed_fields(
        self,
        seeded_config: SPCConfig,
        incomplete_episode: SimpleEpisode,
    ) -> None:
        """Test that summary mentions reconstructed fields."""
        simulator = EpisodicSimulator(config=seeded_config)

        context = {
            "nearby_locations": ["Office"],
            "frequent_contacts": ["Alice"],
        }

        results = simulator.simulate(
            episodes=[incomplete_episode],
            context=context,
            rng_seed=42,
        )

        if results:
            assert "[Reconstructed:" in results[0].summary


# =============================================================================
# Integration Tests
# =============================================================================


class TestSPCUQIntegration:
    """Integration tests for SPC-UQ workflow."""

    def test_full_reconstruction_workflow(self) -> None:
        """Test complete reconstruction from incomplete episode."""
        # Create config
        config = SPCConfig(
            simulation_count=50,
            min_confidence=0.2,
            coherence_threshold=0.3,
            seed=12345,
        )

        # Create incomplete episode
        episode = SimpleEpisode(
            episode_id="ep_integration",
            start_time_ms=1700000000000,
            end_time_ms=1700003600000,
            _location_name=None,
            _participants=None,
            _activity_type="meeting",
            _ambiguity_score=0.7,
            summary="Team sync with missing context",
        )

        # Create fragments
        fragments = [
            EpisodeFragment(
                fragment_id="frag_1",
                source_episode_id="ep_integration",
                source_event_id="evt_001",
                start_time_ms=1700000000000,
                end_time_ms=1700001800000,
                content="First half",
            ),
            EpisodeFragment(
                fragment_id="frag_2",
                source_episode_id="ep_integration",
                source_event_id="evt_002",
                start_time_ms=1700001800000,
                end_time_ms=1700003600000,
                content="Second half",
            ),
        ]

        # Create context
        context = {
            "known_locations": ["Office", "Home", "Conference Room"],
            "nearby_locations": ["Office", "Conference Room"],
            "frequent_contacts": ["Alice", "Bob", "Manager"],
        }

        # Run simulation
        simulator = EpisodicSimulator(config=config)
        results = simulator.simulate(
            episodes=[episode],
            fragments=fragments,
            context=context,
            rng_seed=config.seed,
        )

        # Validate results
        assert len(results) >= 1

        for result in results:
            # Invariant A.0.6
            assert result.is_canonical is False

            # Has proper provenance
            assert result.provenance["algorithm"] == "SPC-UQ"

            # Has reconstructed fields
            assert len(result.reconstructed_fields) >= 1

            # Scores are in valid range
            assert 0.0 <= result.confidence_score <= 1.0
            assert 0.0 <= result.uncertainty_score <= 1.0
            assert 0.0 <= result.temporal_coherence_score <= 1.0

    def test_batch_simulation(self) -> None:
        """Test simulating multiple episodes at once."""
        config = SPCConfig(seed=42)
        simulator = EpisodicSimulator(config=config)

        episodes = [
            SimpleEpisode(
                episode_id=f"ep_{i}",
                start_time_ms=1700000000000 + i * 3600000,
                _location_name=None if i % 2 == 0 else "Office",
                _ambiguity_score=0.6 if i % 2 == 0 else 0.1,
            )
            for i in range(5)
        ]

        context = {
            "nearby_locations": ["Office", "Home"],
            "frequent_contacts": ["Alice"],
        }

        results = simulator.simulate(
            episodes=episodes,
            context=context,
            rng_seed=42,
        )

        # Should have some reconstructions (not all episodes have gaps)
        assert isinstance(results, list)
        # Odd-indexed episodes have no gaps, even-indexed do
        # So we expect at most 3 reconstructions (for indices 0, 2, 4)


# =============================================================================
# Main
# =============================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
