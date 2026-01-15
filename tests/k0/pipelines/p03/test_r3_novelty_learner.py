"""
Tests for AdaptiveNoveltyBonusLearner.

Issue: 4.3.8
Spec Reference: M4_EXECUTION.md, Dossier §4.4.2.1
"""

from __future__ import annotations

import pytest

from k0.modules.consolidation.algorithms.novelty_bonus_learner import (
    BONUS_MAX,
    BONUS_MIN,
    DEFAULT_FIRST_OCCURRENCE_BONUS,
    DEFAULT_MILESTONE_BONUS,
    DEFAULT_RARE_PATTERN_BONUS,
    DEFAULT_TEMPORAL_ANOMALY_BONUS,
    AdaptiveNoveltyBonusLearner,
    InMemoryLearnedWeightsStore,
    NoveltyBonusConfig,
    NoveltyBonusType,
    NoveltyFeedbackSignal,
    clamp_bonus,
    get_default_bonus,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def learner() -> AdaptiveNoveltyBonusLearner:
    """Default learner fixture."""
    return AdaptiveNoveltyBonusLearner()


@pytest.fixture
def store() -> InMemoryLearnedWeightsStore:
    """In-memory store fixture."""
    return InMemoryLearnedWeightsStore()


# =============================================================================
# 4.3.8.T1: NOVEL_EVENT_GROUNDED Increases Bonus
# =============================================================================


class TestNovelEventGrounded:
    """Test NOVEL_EVENT_GROUNDED signal."""

    def test_grounded_signal_increases_bonus(self, learner: AdaptiveNoveltyBonusLearner) -> None:
        """+0.01 on NOVEL_EVENT_GROUNDED."""
        current = 0.15

        result = learner.adjust_bonus(
            bonus_type=NoveltyBonusType.FIRST_OCCURRENCE,
            feedback_signal=NoveltyFeedbackSignal.NOVEL_EVENT_GROUNDED,
            current_bonus=current,
        )

        assert result.old_value == 0.15
        assert result.new_value == pytest.approx(0.16, abs=0.001)
        assert result.adjustment == 0.01
        assert result.clamped is False

    @pytest.mark.asyncio
    async def test_grounded_persisted(
        self,
        learner: AdaptiveNoveltyBonusLearner,
        store: InMemoryLearnedWeightsStore,
    ) -> None:
        """NOVEL_EVENT_GROUNDED persists to store."""
        result = await learner.process_feedback_signal(
            signal_type="NOVEL_EVENT_GROUNDED",
            space_id="space_1",
            store=store,
        )

        assert result is not None
        assert result.new_value == pytest.approx(0.16, abs=0.001)

        # Check persisted
        stored = await store.get_weight("novelty_bonus_first_occurrence", "space_1")
        assert stored == pytest.approx(0.16, abs=0.001)


# =============================================================================
# 4.3.8.T2: NOVEL_EVENT_NEVER_QUERIED Decreases Bonus
# =============================================================================


class TestNovelEventNeverQueried:
    """Test NOVEL_EVENT_NEVER_QUERIED signal."""

    def test_never_queried_decreases_bonus(self, learner: AdaptiveNoveltyBonusLearner) -> None:
        """-0.02 on NOVEL_EVENT_NEVER_QUERIED."""
        current = 0.15

        result = learner.adjust_bonus(
            bonus_type=NoveltyBonusType.FIRST_OCCURRENCE,
            feedback_signal=NoveltyFeedbackSignal.NOVEL_EVENT_NEVER_QUERIED,
            current_bonus=current,
        )

        assert result.old_value == 0.15
        assert result.new_value == pytest.approx(0.13, abs=0.001)
        assert result.adjustment == -0.02
        assert result.clamped is False


# =============================================================================
# 4.3.8.T3: USER_SAYS_NOT_NEW Decreases Bonus
# =============================================================================


class TestUserSaysNotNew:
    """Test USER_SAYS_NOT_NEW signal."""

    def test_user_says_not_new_decreases_bonus(self, learner: AdaptiveNoveltyBonusLearner) -> None:
        """-0.03 on USER_SAYS_NOT_NEW."""
        current = 0.15

        result = learner.adjust_bonus(
            bonus_type=NoveltyBonusType.FIRST_OCCURRENCE,
            feedback_signal=NoveltyFeedbackSignal.USER_SAYS_NOT_NEW,
            current_bonus=current,
        )

        assert result.old_value == 0.15
        assert result.new_value == pytest.approx(0.12, abs=0.001)
        assert result.adjustment == -0.03
        assert result.clamped is False


# =============================================================================
# 4.3.8.T4: MILESTONE_GROUNDED Increases Milestone Bonus
# =============================================================================


class TestMilestoneGrounded:
    """Test MILESTONE_GROUNDED signal."""

    def test_milestone_grounded_increases_milestone(
        self, learner: AdaptiveNoveltyBonusLearner
    ) -> None:
        """+0.01 on MILESTONE_GROUNDED."""
        current = 0.20

        result = learner.adjust_bonus(
            bonus_type=NoveltyBonusType.MILESTONE,
            feedback_signal=NoveltyFeedbackSignal.MILESTONE_GROUNDED,
            current_bonus=current,
        )

        assert result.old_value == 0.20
        assert result.new_value == pytest.approx(0.21, abs=0.001)
        assert result.adjustment == 0.01

    @pytest.mark.asyncio
    async def test_milestone_persisted(
        self,
        learner: AdaptiveNoveltyBonusLearner,
        store: InMemoryLearnedWeightsStore,
    ) -> None:
        """MILESTONE_GROUNDED updates milestone bonus."""
        result = await learner.process_feedback_signal(
            signal_type="MILESTONE_GROUNDED",
            space_id="space_1",
            store=store,
        )

        assert result is not None
        assert result.bonus_type == NoveltyBonusType.MILESTONE
        assert result.new_value == pytest.approx(0.21, abs=0.001)


# =============================================================================
# 4.3.8.T5: RARE_PATTERN_USEFUL Increases Rare Bonus
# =============================================================================


class TestRarePatternUseful:
    """Test RARE_PATTERN_USEFUL signal."""

    def test_rare_pattern_useful_increases_rare(self, learner: AdaptiveNoveltyBonusLearner) -> None:
        """+0.01 on RARE_PATTERN_USEFUL."""
        current = 0.10

        result = learner.adjust_bonus(
            bonus_type=NoveltyBonusType.RARE_PATTERN,
            feedback_signal=NoveltyFeedbackSignal.RARE_PATTERN_USEFUL,
            current_bonus=current,
        )

        assert result.old_value == 0.10
        assert result.new_value == pytest.approx(0.11, abs=0.001)
        assert result.adjustment == 0.01


# =============================================================================
# 4.3.8.T6: Clamped at Minimum
# =============================================================================


class TestClampedAtMinimum:
    """Test bonus clamping at minimum."""

    def test_clamped_at_minimum(self, learner: AdaptiveNoveltyBonusLearner) -> None:
        """Cannot go below 0.05."""
        current = 0.06  # Near minimum

        result = learner.adjust_bonus(
            bonus_type=NoveltyBonusType.FIRST_OCCURRENCE,
            feedback_signal=NoveltyFeedbackSignal.USER_SAYS_NOT_NEW,  # -0.03
            current_bonus=current,
        )

        # 0.06 - 0.03 = 0.03 → clamped to 0.05
        assert result.new_value == BONUS_MIN
        assert result.clamped is True

    def test_already_at_minimum(self, learner: AdaptiveNoveltyBonusLearner) -> None:
        """At minimum stays at minimum."""
        current = 0.05

        result = learner.adjust_bonus(
            bonus_type=NoveltyBonusType.FIRST_OCCURRENCE,
            feedback_signal=NoveltyFeedbackSignal.NOVEL_EVENT_NEVER_QUERIED,  # -0.02
            current_bonus=current,
        )

        assert result.new_value == BONUS_MIN
        assert result.clamped is True


# =============================================================================
# 4.3.8.T7: Clamped at Maximum
# =============================================================================


class TestClampedAtMaximum:
    """Test bonus clamping at maximum."""

    def test_clamped_at_maximum(self, learner: AdaptiveNoveltyBonusLearner) -> None:
        """Cannot exceed 0.30."""
        current = 0.29

        result = learner.adjust_bonus(
            bonus_type=NoveltyBonusType.FIRST_OCCURRENCE,
            feedback_signal=NoveltyFeedbackSignal.NOVEL_EVENT_GROUNDED,  # +0.01
            current_bonus=current,
        )

        # 0.29 + 0.01 = 0.30 → exactly at max, not clamped
        assert result.new_value == BONUS_MAX
        assert result.clamped is False

    def test_exceeding_maximum_clamped(self, learner: AdaptiveNoveltyBonusLearner) -> None:
        """Exceeding max clamps to 0.30."""
        current = 0.30

        result = learner.adjust_bonus(
            bonus_type=NoveltyBonusType.FIRST_OCCURRENCE,
            feedback_signal=NoveltyFeedbackSignal.NOVEL_EVENT_GROUNDED,  # +0.01
            current_bonus=current,
        )

        # 0.30 + 0.01 = 0.31 → clamped to 0.30
        assert result.new_value == BONUS_MAX
        assert result.clamped is True


# =============================================================================
# 4.3.8.T8: Persistence Tests
# =============================================================================


class TestPersistence:
    """Test persistence to store."""

    @pytest.mark.asyncio
    async def test_persisted_to_st_learned_weights(
        self,
        learner: AdaptiveNoveltyBonusLearner,
        store: InMemoryLearnedWeightsStore,
    ) -> None:
        """Correct row upserted."""
        await learner.process_feedback_signal(
            signal_type="NOVEL_EVENT_GROUNDED",
            space_id="space_1",
            store=store,
        )

        value = await store.get_weight("novelty_bonus_first_occurrence", "space_1")
        assert value is not None
        assert value == pytest.approx(0.16, abs=0.001)

    @pytest.mark.asyncio
    async def test_sample_count_incremented(
        self,
        learner: AdaptiveNoveltyBonusLearner,
        store: InMemoryLearnedWeightsStore,
    ) -> None:
        """Sample count increases on update."""
        # First signal
        await learner.process_feedback_signal(
            signal_type="NOVEL_EVENT_GROUNDED",
            space_id="space_1",
            store=store,
        )

        # Second signal
        await learner.process_feedback_signal(
            signal_type="NOVEL_EVENT_GROUNDED",
            space_id="space_1",
            store=store,
        )

        count = store.get_sample_count("novelty_bonus_first_occurrence", "space_1")
        assert count == 2


# =============================================================================
# 4.3.8.T9: Default Used When No Learned Value
# =============================================================================


class TestDefaults:
    """Test default values."""

    @pytest.mark.asyncio
    async def test_default_used_when_no_learned_value(
        self,
        learner: AdaptiveNoveltyBonusLearner,
        store: InMemoryLearnedWeightsStore,
    ) -> None:
        """Returns defaults when no stored value."""
        bonuses = await learner.get_all_bonuses("space_1", store)

        assert bonuses[NoveltyBonusType.FIRST_OCCURRENCE] == DEFAULT_FIRST_OCCURRENCE_BONUS
        assert bonuses[NoveltyBonusType.MILESTONE] == DEFAULT_MILESTONE_BONUS
        assert bonuses[NoveltyBonusType.RARE_PATTERN] == DEFAULT_RARE_PATTERN_BONUS
        assert bonuses[NoveltyBonusType.TEMPORAL_ANOMALY] == DEFAULT_TEMPORAL_ANOMALY_BONUS

    def test_default_constants_match_spec(self) -> None:
        """Verify default constants from spec."""
        assert DEFAULT_FIRST_OCCURRENCE_BONUS == 0.15
        assert DEFAULT_MILESTONE_BONUS == 0.20
        assert DEFAULT_RARE_PATTERN_BONUS == 0.10
        assert DEFAULT_TEMPORAL_ANOMALY_BONUS == 0.10

    def test_bonus_bounds_match_spec(self) -> None:
        """Verify bound constants from spec."""
        assert BONUS_MIN == 0.05
        assert BONUS_MAX == 0.30


# =============================================================================
# 4.3.8.T10: Get All Bonuses
# =============================================================================


class TestGetAllBonuses:
    """Test get_all_bonuses method."""

    @pytest.mark.asyncio
    async def test_get_all_bonuses_mixed(
        self,
        learner: AdaptiveNoveltyBonusLearner,
        store: InMemoryLearnedWeightsStore,
    ) -> None:
        """Returns mix of learned and default values."""
        # Learn first_occurrence
        await learner.process_feedback_signal(
            signal_type="NOVEL_EVENT_GROUNDED",
            space_id="space_1",
            store=store,
        )

        bonuses = await learner.get_all_bonuses("space_1", store)

        # Learned
        assert bonuses[NoveltyBonusType.FIRST_OCCURRENCE] == pytest.approx(0.16, abs=0.001)
        # Defaults
        assert bonuses[NoveltyBonusType.MILESTONE] == DEFAULT_MILESTONE_BONUS
        assert bonuses[NoveltyBonusType.RARE_PATTERN] == DEFAULT_RARE_PATTERN_BONUS
        assert bonuses[NoveltyBonusType.TEMPORAL_ANOMALY] == DEFAULT_TEMPORAL_ANOMALY_BONUS

    @pytest.mark.asyncio
    async def test_get_bonuses_as_dict(
        self,
        learner: AdaptiveNoveltyBonusLearner,
        store: InMemoryLearnedWeightsStore,
    ) -> None:
        """Returns string-keyed dict for config."""
        bonuses = await learner.get_bonuses_as_dict("space_1", store)

        assert "first_occurrence" in bonuses
        assert "milestone" in bonuses
        assert "rare_pattern" in bonuses
        assert "temporal_anomaly" in bonuses
        assert bonuses["first_occurrence"] == DEFAULT_FIRST_OCCURRENCE_BONUS


# =============================================================================
# 4.3.8.T11: Space Isolation
# =============================================================================


class TestSpaceIsolation:
    """Test space isolation."""

    @pytest.mark.asyncio
    async def test_different_spaces_isolated(
        self,
        learner: AdaptiveNoveltyBonusLearner,
        store: InMemoryLearnedWeightsStore,
    ) -> None:
        """Different spaces have isolated values."""
        # Learn in space_1
        await learner.process_feedback_signal(
            signal_type="NOVEL_EVENT_GROUNDED",
            space_id="space_1",
            store=store,
        )

        # space_1 has learned value
        bonuses_1 = await learner.get_all_bonuses("space_1", store)
        assert bonuses_1[NoveltyBonusType.FIRST_OCCURRENCE] == pytest.approx(0.16, abs=0.001)

        # space_2 has default
        bonuses_2 = await learner.get_all_bonuses("space_2", store)
        assert bonuses_2[NoveltyBonusType.FIRST_OCCURRENCE] == DEFAULT_FIRST_OCCURRENCE_BONUS


# =============================================================================
# 4.3.8.T12: Unknown Signal Handling
# =============================================================================


class TestUnknownSignal:
    """Test unknown signal handling."""

    @pytest.mark.asyncio
    async def test_unknown_signal_returns_none(
        self,
        learner: AdaptiveNoveltyBonusLearner,
        store: InMemoryLearnedWeightsStore,
    ) -> None:
        """Unknown signal type returns None."""
        result = await learner.process_feedback_signal(
            signal_type="UNKNOWN_SIGNAL",
            space_id="space_1",
            store=store,
        )

        assert result is None


# =============================================================================
# 4.3.8.T13: Configuration
# =============================================================================


class TestNoveltyBonusConfig:
    """Test configuration."""

    def test_default_config_valid(self) -> None:
        """Default config is valid."""
        config = NoveltyBonusConfig()
        config.validate()  # Should not raise

    def test_invalid_bonus_min(self) -> None:
        """Invalid bonus_min raises ValueError."""
        config = NoveltyBonusConfig(bonus_min=-0.1)
        with pytest.raises(ValueError, match="bonus_min"):
            config.validate()

    def test_invalid_bonus_max(self) -> None:
        """bonus_max <= bonus_min raises ValueError."""
        config = NoveltyBonusConfig(bonus_min=0.3, bonus_max=0.2)
        with pytest.raises(ValueError, match="bonus_max"):
            config.validate()


# =============================================================================
# 4.3.8.T14: Utility Functions
# =============================================================================


class TestUtilityFunctions:
    """Test utility functions."""

    def test_clamp_bonus(self) -> None:
        """Test clamp_bonus utility."""
        assert clamp_bonus(0.15) == 0.15  # In range
        assert clamp_bonus(0.02) == BONUS_MIN  # Too low
        assert clamp_bonus(0.35) == BONUS_MAX  # Too high

    def test_get_default_bonus(self) -> None:
        """Test get_default_bonus utility."""
        assert get_default_bonus(NoveltyBonusType.FIRST_OCCURRENCE) == 0.15
        assert get_default_bonus(NoveltyBonusType.MILESTONE) == 0.20
        assert get_default_bonus(NoveltyBonusType.RARE_PATTERN) == 0.10
        assert get_default_bonus(NoveltyBonusType.TEMPORAL_ANOMALY) == 0.10
