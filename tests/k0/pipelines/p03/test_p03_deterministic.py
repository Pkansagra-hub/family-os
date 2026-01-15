"""
Tests for P03 Deterministic Cycle Seeding and Skip Rule Policy — Issue 1.2.7

Tests cover:
1. Seed derivation (derive_cycle_seed, derive_phase_seed)
2. Seeded RNG (P03SeededRNG) - determinism and phase isolation
3. Skip rule evaluation (evaluate_r5_skip, evaluate_minimal_work_skip)
4. Skip policy manager (P03SkipPolicy)
5. Deterministic context (P03DeterministicContext)
6. Helper functions
7. Error handling

Test Naming Convention:
    test_<component>_<behavior>

References:
    - Issue: docs/TEMP_EXECUTION_DOCS/M1_EXECUTION.md Issue 1.2.7
    - Spec: docs/pipelines/P03_consolidation_dossier_v2.md Appendix G
"""

from __future__ import annotations

import random

import pytest

from k0.pipelines.p03 import (
    DEFAULT_MINIMAL_WORK_THRESHOLD,
    DEFAULT_R5_BACKLOG_THRESHOLD,
    MINIMAL_WORK_SKIP_PHASES,
    R5_SKIP_PHASES,
    P03DeterministicContext,
    P03PhaseId,
    P03SeededRNG,
    P03SkipPolicy,
    SkipDecision,
    SkipPolicyConfig,
    SkipReason,
    derive_cycle_seed,
    derive_phase_seed,
    evaluate_minimal_work_skip,
    evaluate_r5_skip,
    get_phases_to_skip_for_fast_path,
    validate_skip_transition,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def sample_cycle_id() -> str:
    """Sample ULID for testing."""
    return "01JFXYZ123ABC456DEF789GHJ"


@pytest.fixture
def sample_batch_id() -> str:
    """Sample batch hash (SHA256[:16])."""
    return "a1b2c3d4e5f67890"


@pytest.fixture
def sample_cycle_seed(sample_cycle_id: str, sample_batch_id: str) -> int:
    """Derived seed for testing."""
    return derive_cycle_seed(sample_cycle_id, sample_batch_id)


@pytest.fixture
def default_config() -> SkipPolicyConfig:
    """Default skip policy configuration."""
    return SkipPolicyConfig()


@pytest.fixture
def r5_disabled_config() -> SkipPolicyConfig:
    """Configuration with R5 disabled."""
    return SkipPolicyConfig(r5_enabled=False)


@pytest.fixture
def custom_threshold_config() -> SkipPolicyConfig:
    """Configuration with custom thresholds."""
    return SkipPolicyConfig(
        r5_backlog_threshold=1000,
        minimal_work_threshold=3,
    )


# =============================================================================
# SEED DERIVATION TESTS
# =============================================================================


class TestDeriveCycleSeed:
    """Tests for derive_cycle_seed function."""

    def test_deterministic_same_inputs(
        self,
        sample_cycle_id: str,
        sample_batch_id: str,
    ) -> None:
        """Same inputs produce same seed."""
        seed1 = derive_cycle_seed(sample_cycle_id, sample_batch_id)
        seed2 = derive_cycle_seed(sample_cycle_id, sample_batch_id)
        assert seed1 == seed2

    def test_different_cycle_ids_produce_different_seeds(
        self,
        sample_batch_id: str,
    ) -> None:
        """Different cycle_ids produce different seeds."""
        seed1 = derive_cycle_seed("01JFXYZ111111111111111111", sample_batch_id)
        seed2 = derive_cycle_seed("01JFXYZ222222222222222222", sample_batch_id)
        assert seed1 != seed2

    def test_different_batch_ids_produce_different_seeds(
        self,
        sample_cycle_id: str,
    ) -> None:
        """Different batch_ids produce different seeds."""
        seed1 = derive_cycle_seed(sample_cycle_id, "aaaaaaaaaaaaaaaa")
        seed2 = derive_cycle_seed(sample_cycle_id, "bbbbbbbbbbbbbbbb")
        assert seed1 != seed2

    def test_seed_is_64_bit_integer(
        self,
        sample_cycle_id: str,
        sample_batch_id: str,
    ) -> None:
        """Seed should be a positive 64-bit integer."""
        seed = derive_cycle_seed(sample_cycle_id, sample_batch_id)
        assert isinstance(seed, int)
        assert seed >= 0
        assert seed < 2**64

    def test_empty_cycle_id_raises_error(
        self,
        sample_batch_id: str,
    ) -> None:
        """Empty cycle_id should raise ValueError."""
        with pytest.raises(ValueError, match="cycle_id cannot be empty"):
            derive_cycle_seed("", sample_batch_id)

    def test_empty_batch_id_raises_error(
        self,
        sample_cycle_id: str,
    ) -> None:
        """Empty batch_id should raise ValueError."""
        with pytest.raises(ValueError, match="batch_id cannot be empty"):
            derive_cycle_seed(sample_cycle_id, "")


class TestDerivePhaseSeed:
    """Tests for derive_phase_seed function."""

    def test_deterministic_same_inputs(
        self,
        sample_cycle_seed: int,
    ) -> None:
        """Same cycle_seed and phase produce same phase seed."""
        seed1 = derive_phase_seed(sample_cycle_seed, P03PhaseId.R5_DREAM)
        seed2 = derive_phase_seed(sample_cycle_seed, P03PhaseId.R5_DREAM)
        assert seed1 == seed2

    def test_different_phases_produce_different_seeds(
        self,
        sample_cycle_seed: int,
    ) -> None:
        """Different phases produce different seeds from same cycle seed."""
        seeds = []
        for phase in P03PhaseId.execution_order():
            seeds.append(derive_phase_seed(sample_cycle_seed, phase))

        # All seeds should be unique
        assert len(set(seeds)) == len(seeds)

    def test_different_cycle_seeds_produce_different_phase_seeds(
        self,
    ) -> None:
        """Different cycle seeds produce different phase seeds."""
        seed1 = derive_phase_seed(12345, P03PhaseId.R5_DREAM)
        seed2 = derive_phase_seed(67890, P03PhaseId.R5_DREAM)
        assert seed1 != seed2


# =============================================================================
# SEEDED RNG TESTS
# =============================================================================


class TestP03SeededRNG:
    """Tests for P03SeededRNG class."""

    def test_create_from_identifiers(
        self,
        sample_cycle_id: str,
        sample_batch_id: str,
    ) -> None:
        """Create RNG from cycle identifiers."""
        rng = P03SeededRNG.create(sample_cycle_id, sample_batch_id)
        assert rng.cycle_id == sample_cycle_id
        assert rng.batch_id == sample_batch_id
        assert isinstance(rng.cycle_seed, int)

    def test_deterministic_random_sequence(
        self,
        sample_cycle_id: str,
        sample_batch_id: str,
    ) -> None:
        """Two RNGs with same identifiers produce same random sequence."""
        rng1 = P03SeededRNG.create(sample_cycle_id, sample_batch_id)
        rng2 = P03SeededRNG.create(sample_cycle_id, sample_batch_id)

        # Generate 10 random values from each
        values1 = [rng1.random() for _ in range(10)]
        values2 = [rng2.random() for _ in range(10)]

        assert values1 == values2

    def test_phase_rng_isolation(
        self,
        sample_cycle_id: str,
        sample_batch_id: str,
    ) -> None:
        """Phase RNGs are isolated from each other."""
        rng = P03SeededRNG.create(sample_cycle_id, sample_batch_id)

        # Get phase-specific RNGs
        r3_rng = rng.get_phase_rng(P03PhaseId.R3_PRUNE)
        r5_rng = rng.get_phase_rng(P03PhaseId.R5_DREAM)

        # Generate values - they should be different
        r3_values = [r3_rng.random() for _ in range(5)]
        r5_values = [r5_rng.random() for _ in range(5)]

        assert r3_values != r5_values

    def test_phase_rng_deterministic(
        self,
        sample_cycle_id: str,
        sample_batch_id: str,
    ) -> None:
        """Same phase from same RNG produces same sequence."""
        rng1 = P03SeededRNG.create(sample_cycle_id, sample_batch_id)
        rng2 = P03SeededRNG.create(sample_cycle_id, sample_batch_id)

        # Get R5 RNG from both
        r5_rng1 = rng1.get_phase_rng(P03PhaseId.R5_DREAM)
        r5_rng2 = rng2.get_phase_rng(P03PhaseId.R5_DREAM)

        values1 = [r5_rng1.random() for _ in range(10)]
        values2 = [r5_rng2.random() for _ in range(10)]

        assert values1 == values2

    def test_phase_rng_cached(
        self,
        sample_cycle_id: str,
        sample_batch_id: str,
    ) -> None:
        """Phase RNG is cached and reused."""
        rng = P03SeededRNG.create(sample_cycle_id, sample_batch_id)

        r5_rng_first = rng.get_phase_rng(P03PhaseId.R5_DREAM)
        r5_rng_second = rng.get_phase_rng(P03PhaseId.R5_DREAM)

        assert r5_rng_first is r5_rng_second

    def test_randint_method(
        self,
        sample_cycle_id: str,
        sample_batch_id: str,
    ) -> None:
        """randint produces deterministic integers."""
        rng1 = P03SeededRNG.create(sample_cycle_id, sample_batch_id)
        rng2 = P03SeededRNG.create(sample_cycle_id, sample_batch_id)

        values1 = [rng1.randint(1, 100) for _ in range(10)]
        values2 = [rng2.randint(1, 100) for _ in range(10)]

        assert values1 == values2

    def test_choice_method(
        self,
        sample_cycle_id: str,
        sample_batch_id: str,
    ) -> None:
        """choice produces deterministic selections."""
        rng1 = P03SeededRNG.create(sample_cycle_id, sample_batch_id)
        rng2 = P03SeededRNG.create(sample_cycle_id, sample_batch_id)

        options = ["a", "b", "c", "d", "e"]
        choices1 = [rng1.choice(options) for _ in range(10)]
        choices2 = [rng2.choice(options) for _ in range(10)]

        assert choices1 == choices2

    def test_sample_method(
        self,
        sample_cycle_id: str,
        sample_batch_id: str,
    ) -> None:
        """sample produces deterministic samples."""
        rng1 = P03SeededRNG.create(sample_cycle_id, sample_batch_id)
        rng2 = P03SeededRNG.create(sample_cycle_id, sample_batch_id)

        population = list(range(100))
        sample1 = rng1.sample(population, 10)
        sample2 = rng2.sample(population, 10)

        assert sample1 == sample2

    def test_shuffle_method(
        self,
        sample_cycle_id: str,
        sample_batch_id: str,
    ) -> None:
        """shuffle produces deterministic permutations."""
        rng1 = P03SeededRNG.create(sample_cycle_id, sample_batch_id)
        rng2 = P03SeededRNG.create(sample_cycle_id, sample_batch_id)

        list1 = list(range(10))
        list2 = list(range(10))

        rng1.shuffle(list1)
        rng2.shuffle(list2)

        assert list1 == list2

    def test_to_dict_serialization(
        self,
        sample_cycle_id: str,
        sample_batch_id: str,
    ) -> None:
        """to_dict produces valid serialization."""
        rng = P03SeededRNG.create(sample_cycle_id, sample_batch_id)
        # Access a phase RNG to populate the cache
        rng.get_phase_rng(P03PhaseId.R5_DREAM)

        result = rng.to_dict()

        assert "cycle_seed" in result
        assert "cycle_id" in result
        assert "batch_id" in result
        assert "phase_seeds" in result
        assert result["cycle_id"] == sample_cycle_id
        assert result["batch_id"] == sample_batch_id


# =============================================================================
# SKIP RULE EVALUATION TESTS
# =============================================================================


class TestEvaluateR5Skip:
    """Tests for evaluate_r5_skip function."""

    def test_no_skip_below_threshold(
        self,
        default_config: SkipPolicyConfig,
    ) -> None:
        """R5 should not skip when pending < threshold."""
        decision = evaluate_r5_skip(
            pending_count=1000,
            config=default_config,
        )
        assert decision.should_skip is False
        assert decision.phase_id == P03PhaseId.R5_DREAM

    def test_skip_above_threshold(
        self,
        default_config: SkipPolicyConfig,
    ) -> None:
        """R5 should skip when pending > threshold."""
        decision = evaluate_r5_skip(
            pending_count=DEFAULT_R5_BACKLOG_THRESHOLD + 1,
            config=default_config,
        )
        assert decision.should_skip is True
        assert decision.reason == SkipReason.R5_BACKLOG_EXCEEDED
        assert decision.threshold_value == DEFAULT_R5_BACKLOG_THRESHOLD
        assert decision.actual_value == DEFAULT_R5_BACKLOG_THRESHOLD + 1

    def test_no_skip_at_exact_threshold(
        self,
        default_config: SkipPolicyConfig,
    ) -> None:
        """R5 should NOT skip when pending == threshold (>= not >)."""
        decision = evaluate_r5_skip(
            pending_count=DEFAULT_R5_BACKLOG_THRESHOLD,
            config=default_config,
        )
        assert decision.should_skip is False

    def test_skip_when_r5_disabled(
        self,
        r5_disabled_config: SkipPolicyConfig,
    ) -> None:
        """R5 should skip when globally disabled."""
        decision = evaluate_r5_skip(
            pending_count=100,  # Below any threshold
            config=r5_disabled_config,
        )
        assert decision.should_skip is True
        assert decision.reason == SkipReason.R5_DISABLED

    def test_custom_threshold(
        self,
        custom_threshold_config: SkipPolicyConfig,
    ) -> None:
        """R5 respects custom threshold configuration."""
        # Custom threshold is 1000
        decision = evaluate_r5_skip(
            pending_count=1001,
            config=custom_threshold_config,
        )
        assert decision.should_skip is True
        assert decision.threshold_value == 1000

    def test_skip_disabled_via_config(self) -> None:
        """R5 skip can be disabled via r5_skip_on_backlog=False."""
        config = SkipPolicyConfig(
            r5_enabled=True,
            r5_skip_on_backlog=False,
        )
        decision = evaluate_r5_skip(
            pending_count=100000,  # Very high
            config=config,
        )
        assert decision.should_skip is False

    def test_default_config_when_none(self) -> None:
        """Uses default config when None provided."""
        decision = evaluate_r5_skip(pending_count=100, config=None)
        assert decision.should_skip is False


class TestEvaluateMinimalWorkSkip:
    """Tests for evaluate_minimal_work_skip function."""

    def test_no_skip_normal_batch(
        self,
        default_config: SkipPolicyConfig,
    ) -> None:
        """Normal batch size should not skip."""
        decision = evaluate_minimal_work_skip(
            batch_size=100,
            config=default_config,
        )
        assert decision.should_skip is False
        assert decision.phase_id == P03PhaseId.R2_CLUSTER

    def test_skip_single_event(
        self,
        default_config: SkipPolicyConfig,
    ) -> None:
        """Single event triggers micro-episode skip."""
        decision = evaluate_minimal_work_skip(
            batch_size=1,
            config=default_config,
        )
        assert decision.should_skip is True
        assert decision.reason == SkipReason.SINGLE_EVENT_MICRO_EPISODE
        assert decision.actual_value == 1

    def test_skip_below_threshold(
        self,
        custom_threshold_config: SkipPolicyConfig,
    ) -> None:
        """Batch below threshold triggers skip."""
        # Custom threshold is 3
        decision = evaluate_minimal_work_skip(
            batch_size=2,
            config=custom_threshold_config,
        )
        assert decision.should_skip is True
        assert decision.reason == SkipReason.BATCH_TOO_SMALL
        assert decision.threshold_value == 3

    def test_no_skip_at_threshold(
        self,
        default_config: SkipPolicyConfig,
    ) -> None:
        """Batch at threshold should not skip."""
        # Default threshold is 2
        decision = evaluate_minimal_work_skip(
            batch_size=DEFAULT_MINIMAL_WORK_THRESHOLD,
            config=default_config,
        )
        assert decision.should_skip is False

    def test_reason_detail_populated(self) -> None:
        """Skip decision includes reason detail."""
        decision = evaluate_minimal_work_skip(batch_size=1)
        assert decision.reason_detail is not None
        assert "micro-episode" in decision.reason_detail.lower()


class TestSkipDecision:
    """Tests for SkipDecision dataclass."""

    def test_to_dict_no_skip(self) -> None:
        """Serialization for non-skip decision."""
        decision = SkipDecision(
            should_skip=False,
            phase_id=P03PhaseId.R5_DREAM,
        )
        result = decision.to_dict()
        assert result["should_skip"] is False
        assert result["phase"] == "R5"
        assert "reason" not in result

    def test_to_dict_with_skip(self) -> None:
        """Serialization for skip decision."""
        decision = SkipDecision(
            should_skip=True,
            phase_id=P03PhaseId.R5_DREAM,
            reason=SkipReason.R5_BACKLOG_EXCEEDED,
            reason_detail="Pending 6000 > threshold 5000",
            threshold_value=5000,
            actual_value=6000,
        )
        result = decision.to_dict()
        assert result["should_skip"] is True
        assert result["reason"] == "r5_backlog_exceeded"
        assert result["threshold_value"] == 5000
        assert result["actual_value"] == 6000


# =============================================================================
# SKIP POLICY MANAGER TESTS
# =============================================================================


class TestP03SkipPolicy:
    """Tests for P03SkipPolicy class."""

    def test_create_factory(self) -> None:
        """Factory creates valid policy."""
        policy = P03SkipPolicy.create(
            pending_count=1000,
            batch_size=50,
        )
        assert policy.pending_count == 1000
        assert policy.batch_size == 50

    def test_should_skip_phase_r5(self) -> None:
        """Evaluates R5 skip correctly."""
        policy = P03SkipPolicy.create(
            pending_count=10000,  # Above threshold
            batch_size=50,
        )
        decision = policy.should_skip_phase(P03PhaseId.R5_DREAM)
        assert decision.should_skip is True

    def test_should_skip_phase_r2(self) -> None:
        """Evaluates R2 skip correctly."""
        policy = P03SkipPolicy.create(
            pending_count=100,
            batch_size=1,  # Single event
        )
        decision = policy.should_skip_phase(P03PhaseId.R2_CLUSTER)
        assert decision.should_skip is True

    def test_should_skip_phase_required(self) -> None:
        """Required phases never skip."""
        policy = P03SkipPolicy.create(
            pending_count=100,
            batch_size=50,
        )
        # R0, R1, R3, R4, R6, R7, R8 are required
        for phase in [
            P03PhaseId.R0_INIT,
            P03PhaseId.R1_SCORE,
            P03PhaseId.R3_PRUNE,
            P03PhaseId.R4_KG,
            P03PhaseId.R6_STAGE,
            P03PhaseId.R7_WRITE,
            P03PhaseId.R8_EMIT,
        ]:
            decision = policy.should_skip_phase(phase)
            assert decision.should_skip is False

    def test_decision_caching(self) -> None:
        """Decisions are cached for consistency."""
        policy = P03SkipPolicy.create(
            pending_count=100,
            batch_size=50,
        )
        decision1 = policy.should_skip_phase(P03PhaseId.R5_DREAM)
        decision2 = policy.should_skip_phase(P03PhaseId.R5_DREAM)
        assert decision1 is decision2

    def test_get_skip_transition_r5(self) -> None:
        """R5 skip transitions to R6."""
        policy = P03SkipPolicy.create(
            pending_count=10000,
            batch_size=50,
        )
        target = policy.get_skip_transition(P03PhaseId.R5_DREAM)
        assert target == P03PhaseId.R6_STAGE

    def test_get_skip_transition_r2(self) -> None:
        """R2 skip transitions to R6."""
        policy = P03SkipPolicy.create(
            pending_count=100,
            batch_size=1,
        )
        target = policy.get_skip_transition(P03PhaseId.R2_CLUSTER)
        assert target == P03PhaseId.R6_STAGE

    def test_get_skip_transition_no_skip(self) -> None:
        """No skip target when phase should not skip."""
        policy = P03SkipPolicy.create(
            pending_count=100,
            batch_size=50,
        )
        target = policy.get_skip_transition(P03PhaseId.R5_DREAM)
        assert target is None

    def test_get_all_decisions(self) -> None:
        """Get all cached decisions."""
        policy = P03SkipPolicy.create(
            pending_count=100,
            batch_size=50,
        )
        policy.should_skip_phase(P03PhaseId.R5_DREAM)
        policy.should_skip_phase(P03PhaseId.R2_CLUSTER)

        decisions = policy.get_all_decisions()
        assert P03PhaseId.R5_DREAM in decisions
        assert P03PhaseId.R2_CLUSTER in decisions

    def test_get_skip_summary(self) -> None:
        """Get summary for observability."""
        policy = P03SkipPolicy.create(
            pending_count=10000,
            batch_size=50,
        )
        policy.should_skip_phase(P03PhaseId.R5_DREAM)

        summary = policy.get_skip_summary()
        assert summary["pending_count"] == 10000
        assert summary["batch_size"] == 50
        assert "R5" in summary["phases_skipped"]

    def test_to_dict_serialization(self) -> None:
        """Full serialization for checkpointing."""
        policy = P03SkipPolicy.create(
            pending_count=100,
            batch_size=50,
            config=SkipPolicyConfig(r5_backlog_threshold=1000),
        )
        policy.should_skip_phase(P03PhaseId.R5_DREAM)

        result = policy.to_dict()
        assert result["config"]["r5_backlog_threshold"] == 1000
        assert result["pending_count"] == 100
        assert result["batch_size"] == 50


# =============================================================================
# DETERMINISTIC CONTEXT TESTS
# =============================================================================


class TestP03DeterministicContext:
    """Tests for P03DeterministicContext class."""

    def test_create_factory(
        self,
        sample_cycle_id: str,
        sample_batch_id: str,
    ) -> None:
        """Factory creates valid context."""
        ctx = P03DeterministicContext.create(
            cycle_id=sample_cycle_id,
            batch_id=sample_batch_id,
            pending_count=100,
            batch_size=50,
        )
        assert ctx.cycle_id == sample_cycle_id
        assert ctx.batch_id == sample_batch_id
        assert ctx.rng is not None
        assert ctx.skip_policy is not None

    def test_get_phase_rng(
        self,
        sample_cycle_id: str,
        sample_batch_id: str,
    ) -> None:
        """Get phase-specific RNG through context."""
        ctx = P03DeterministicContext.create(
            cycle_id=sample_cycle_id,
            batch_id=sample_batch_id,
            pending_count=100,
            batch_size=50,
        )
        rng = ctx.get_phase_rng(P03PhaseId.R5_DREAM)
        assert isinstance(rng, random.Random)

    def test_should_skip_phase(
        self,
        sample_cycle_id: str,
        sample_batch_id: str,
    ) -> None:
        """Check skip through context."""
        ctx = P03DeterministicContext.create(
            cycle_id=sample_cycle_id,
            batch_id=sample_batch_id,
            pending_count=10000,
            batch_size=50,
        )
        decision = ctx.should_skip_phase(P03PhaseId.R5_DREAM)
        assert decision.should_skip is True

    def test_to_dict_serialization(
        self,
        sample_cycle_id: str,
        sample_batch_id: str,
    ) -> None:
        """Full serialization of context."""
        ctx = P03DeterministicContext.create(
            cycle_id=sample_cycle_id,
            batch_id=sample_batch_id,
            pending_count=100,
            batch_size=50,
        )
        result = ctx.to_dict()
        assert result["cycle_id"] == sample_cycle_id
        assert result["batch_id"] == sample_batch_id
        assert "rng" in result
        assert "skip_policy" in result


# =============================================================================
# HELPER FUNCTION TESTS
# =============================================================================


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_get_phases_to_skip_r2_to_r6(self) -> None:
        """R2→R6 skips R3, R4, R5."""
        skipped = get_phases_to_skip_for_fast_path(
            P03PhaseId.R2_CLUSTER,
            P03PhaseId.R6_STAGE,
        )
        assert skipped == (
            P03PhaseId.R3_PRUNE,
            P03PhaseId.R4_KG,
            P03PhaseId.R5_DREAM,
        )

    def test_get_phases_to_skip_r4_to_r6(self) -> None:
        """R4→R6 skips R5 only."""
        skipped = get_phases_to_skip_for_fast_path(
            P03PhaseId.R4_KG,
            P03PhaseId.R6_STAGE,
        )
        assert skipped == (P03PhaseId.R5_DREAM,)

    def test_get_phases_to_skip_r5_to_r6(self) -> None:
        """R5→R6 skips nothing (adjacent phases)."""
        skipped = get_phases_to_skip_for_fast_path(
            P03PhaseId.R5_DREAM,
            P03PhaseId.R6_STAGE,
        )
        assert skipped == ()

    def test_get_phases_to_skip_invalid_direction(self) -> None:
        """Backward transition returns empty tuple."""
        skipped = get_phases_to_skip_for_fast_path(
            P03PhaseId.R6_STAGE,
            P03PhaseId.R2_CLUSTER,
        )
        assert skipped == ()

    def test_validate_skip_transition_r2_to_r6(self) -> None:
        """R2→R6 is valid skip transition."""
        assert validate_skip_transition(P03PhaseId.R2_CLUSTER, P03PhaseId.R6_STAGE) is True

    def test_validate_skip_transition_r4_to_r6(self) -> None:
        """R4→R6 is valid skip transition."""
        assert validate_skip_transition(P03PhaseId.R4_KG, P03PhaseId.R6_STAGE) is True

    def test_validate_skip_transition_r5_to_r6(self) -> None:
        """R5→R6 is valid skip transition."""
        assert validate_skip_transition(P03PhaseId.R5_DREAM, P03PhaseId.R6_STAGE) is True

    def test_validate_skip_transition_invalid(self) -> None:
        """R1→R6 is not valid skip transition."""
        assert validate_skip_transition(P03PhaseId.R1_SCORE, P03PhaseId.R6_STAGE) is False

    def test_validate_skip_transition_r0_to_r6(self) -> None:
        """R0→R6 is not valid skip transition."""
        assert validate_skip_transition(P03PhaseId.R0_INIT, P03PhaseId.R6_STAGE) is False


# =============================================================================
# CONFIG VALIDATION TESTS
# =============================================================================


class TestSkipPolicyConfig:
    """Tests for SkipPolicyConfig validation."""

    def test_valid_config(self) -> None:
        """Valid configuration creates successfully."""
        config = SkipPolicyConfig(
            r5_enabled=True,
            r5_skip_on_backlog=True,
            r5_backlog_threshold=1000,
            minimal_work_threshold=2,
        )
        assert config.r5_backlog_threshold == 1000

    def test_negative_backlog_threshold_raises(self) -> None:
        """Negative backlog threshold raises ValueError."""
        with pytest.raises(ValueError, match="non-negative"):
            SkipPolicyConfig(r5_backlog_threshold=-1)

    def test_zero_minimal_threshold_raises(self) -> None:
        """Zero minimal threshold raises ValueError."""
        with pytest.raises(ValueError, match=">= 1"):
            SkipPolicyConfig(minimal_work_threshold=0)

    def test_from_dict(self) -> None:
        """Create config from dictionary."""
        config_dict = {
            "r5_dream_enabled": False,
            "r5_skip_on_backlog": True,
            "r5_backlog_threshold": 2000,
            "minimal_work_threshold": 5,
        }
        config = SkipPolicyConfig.from_dict(config_dict)
        assert config.r5_enabled is False
        assert config.r5_backlog_threshold == 2000
        assert config.minimal_work_threshold == 5


# =============================================================================
# CONSTANTS TESTS
# =============================================================================


class TestConstants:
    """Tests for module constants."""

    def test_default_r5_threshold(self) -> None:
        """Default R5 threshold is 5000."""
        assert DEFAULT_R5_BACKLOG_THRESHOLD == 5000

    def test_default_minimal_threshold(self) -> None:
        """Default minimal work threshold is 2."""
        assert DEFAULT_MINIMAL_WORK_THRESHOLD == 2

    def test_r5_skip_phases(self) -> None:
        """R5 skip phases contains only R5."""
        assert R5_SKIP_PHASES == frozenset({P03PhaseId.R5_DREAM})

    def test_minimal_work_skip_phases(self) -> None:
        """Minimal work skip phases contains R3, R4, R5."""
        assert MINIMAL_WORK_SKIP_PHASES == frozenset(
            {
                P03PhaseId.R3_PRUNE,
                P03PhaseId.R4_KG,
                P03PhaseId.R5_DREAM,
            }
        )


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestDeterministicIntegration:
    """Integration tests for deterministic behavior."""

    def test_full_cycle_determinism(
        self,
        sample_cycle_id: str,
        sample_batch_id: str,
    ) -> None:
        """Full cycle with same inputs produces identical results."""
        # Create two identical contexts
        ctx1 = P03DeterministicContext.create(
            cycle_id=sample_cycle_id,
            batch_id=sample_batch_id,
            pending_count=100,
            batch_size=50,
        )
        ctx2 = P03DeterministicContext.create(
            cycle_id=sample_cycle_id,
            batch_id=sample_batch_id,
            pending_count=100,
            batch_size=50,
        )

        # Generate random values from each phase
        results1 = {}
        results2 = {}

        for phase in P03PhaseId.execution_order():
            rng1 = ctx1.get_phase_rng(phase)
            rng2 = ctx2.get_phase_rng(phase)

            results1[phase] = [rng1.random() for _ in range(5)]
            results2[phase] = [rng2.random() for _ in range(5)]

        # All results must match
        for phase in P03PhaseId.execution_order():
            assert results1[phase] == results2[phase], f"Phase {phase} mismatch"

    def test_skip_decisions_deterministic(
        self,
        sample_cycle_id: str,
        sample_batch_id: str,
    ) -> None:
        """Skip decisions are deterministic for same inputs."""
        ctx1 = P03DeterministicContext.create(
            cycle_id=sample_cycle_id,
            batch_id=sample_batch_id,
            pending_count=10000,
            batch_size=1,
        )
        ctx2 = P03DeterministicContext.create(
            cycle_id=sample_cycle_id,
            batch_id=sample_batch_id,
            pending_count=10000,
            batch_size=1,
        )

        # Evaluate all skippable phases
        for phase in [P03PhaseId.R2_CLUSTER, P03PhaseId.R5_DREAM]:
            decision1 = ctx1.should_skip_phase(phase)
            decision2 = ctx2.should_skip_phase(phase)

            assert decision1.should_skip == decision2.should_skip
            assert decision1.reason == decision2.reason

    def test_different_cycles_different_results(
        self,
        sample_batch_id: str,
    ) -> None:
        """Different cycle_ids produce different random sequences."""
        ctx1 = P03DeterministicContext.create(
            cycle_id="01JFXYZ111111111111111111",
            batch_id=sample_batch_id,
            pending_count=100,
            batch_size=50,
        )
        ctx2 = P03DeterministicContext.create(
            cycle_id="01JFXYZ222222222222222222",
            batch_id=sample_batch_id,
            pending_count=100,
            batch_size=50,
        )

        # Same phase should produce different values
        rng1 = ctx1.get_phase_rng(P03PhaseId.R5_DREAM)
        rng2 = ctx2.get_phase_rng(P03PhaseId.R5_DREAM)

        values1 = [rng1.random() for _ in range(10)]
        values2 = [rng2.random() for _ in range(10)]

        assert values1 != values2


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================


class TestErrorHandling:
    """Tests for error conditions."""

    def test_derive_seed_empty_cycle_id(self) -> None:
        """Empty cycle_id raises ValueError."""
        with pytest.raises(ValueError):
            derive_cycle_seed("", "batch123")

    def test_derive_seed_empty_batch_id(self) -> None:
        """Empty batch_id raises ValueError."""
        with pytest.raises(ValueError):
            derive_cycle_seed("cycle123", "")

    def test_invalid_config_negative_threshold(self) -> None:
        """Negative threshold in config raises ValueError."""
        with pytest.raises(ValueError):
            SkipPolicyConfig(r5_backlog_threshold=-100)
