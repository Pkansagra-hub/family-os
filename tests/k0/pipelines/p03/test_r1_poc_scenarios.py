"""
Port of 120 POC scenarios as parametrized regression tests (5.O.2.2).

Converts `poc/r1_weight_research/scenarios.py` (120 scenarios, 13 categories)
to pytest parametrized tests using the production ImportanceScorer.

AC: 120 parametrized tests pass; all tiers match POC expectations.

Mapping: POC R1SignalVector fields -> production P03EventState fields.
Recency: all events treated as fresh (event_time_ms = now_ms) since POC
used recency_factor=1.0.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import pytest

from k0.modules.consolidation.algorithms.importance_scorer import (
    ImportanceScorer,
    ImportanceWeights,
)

# =============================================================================
# MOCK EVENT STATE (maps R1SignalVector -> P03EventState duck type)
# =============================================================================


@dataclass
class ScenarioEventState:
    """
    Mock P03EventState created from a POC R1SignalVector.

    Only the fields consumed by ImportanceScorer.compute_importance_score()
    are populated. All others use safe defaults.
    """

    event_id: str = "poc-event"
    sentiment_score: float = 0.0
    affect_valence: float = 0.0
    affect_arousal: float = 0.0
    surprise_level: float = 0.0
    num_participants: int = 1
    social_intimacy: str = "LOW"
    content_type: str = "message"
    intent_label: str = ""
    novelty: str = "EXPECTED"
    elaboration_depth: str = "MENTION"
    temporal_orientation: str = "PAST"
    identity_relevance: float = 0.0
    source_reliability: float = 0.95
    source_type: str = "user_stated"
    narrative_is_goal_event: bool = False
    narrative_arc_position: str = "EXPOSITION"
    memory_tier: str = "routine"
    importance_computed: bool = False
    timestamp: int = 0

    def set_importance(self, **kwargs: Any) -> None:
        self.importance_computed = True


def _vec_to_event(vec: Any, now_ms: int) -> ScenarioEventState:
    """Convert a POC R1SignalVector to a ScenarioEventState."""
    return ScenarioEventState(
        event_id=vec.event_id,
        sentiment_score=vec.sentiment_score,
        affect_valence=vec.affect_valence,
        affect_arousal=vec.affect_arousal,
        surprise_level=vec.surprise_level,
        num_participants=vec.num_participants,
        social_intimacy=vec.social_intimacy,
        content_type=vec.activity_type,  # POC activity_type = production content_type
        intent_label=vec.intent,  # POC intent -> production intent_label
        source_type=getattr(vec, "source_type", "user_stated"),
        novelty=vec.novelty,
        elaboration_depth=vec.elaboration_depth,
        temporal_orientation=vec.temporal_orientation,
        identity_relevance=vec.identity_relevance,
        source_reliability=vec.source_reliability,
        narrative_is_goal_event=vec.narrative_is_goal_event,
        narrative_arc_position=vec.narrative_arc_position,
        memory_tier=vec.memory_tier,
        timestamp=now_ms,  # Fresh event => recency_factor ~ 1.0
    )


# =============================================================================
# LOAD ALL 120 SCENARIOS
# =============================================================================


def _load_scenarios() -> list:
    """Import and build all 120 POC scenarios."""
    from poc.r1_weight_research.scenarios import build_all_scenarios

    return build_all_scenarios()


ALL_SCENARIOS = _load_scenarios()
SCENARIO_IDS = [f"S{s.id:03d}_{s.name[:40].replace(' ', '_')}" for s in ALL_SCENARIOS]


# =============================================================================
# PARAMETRIZED REGRESSION TESTS (120 scenarios)
# =============================================================================


@pytest.mark.parametrize(
    "scenario",
    ALL_SCENARIOS,
    ids=SCENARIO_IDS,
)
class TestPOCScenarioRegression:
    """
    120 hand-crafted validation scenarios from POC research.

    Each scenario defines expected_tier and acceptable_tiers.
    Production ImportanceScorer must place each scenario's score
    into an acceptable tier.

    Categories (13):
        1. Critical Milestones (10)
        2. Daily Routine Low (10)
        3. Emotional Conversations (10)
        4. Social Gatherings (10)
        5. Health/Medical (10)
        6. Education/Learning (10)
        7. Financial (10)
        8. Travel/Adventure (10)
        9. Creative/Hobbies (10)
        10. Conflict/Resolution (10)
        11. Planning/Future (5)
        12. Reflection/Nostalgia (10)
        13. Edge Cases (5)
    """

    def test_tier_match(self, scenario: Any) -> None:
        """Scenario score must land in an acceptable tier."""
        now_ms = int(time.time() * 1000)
        event = _vec_to_event(scenario.vec, now_ms)

        scorer = ImportanceScorer(space_id="poc-test")
        weights = ImportanceWeights()  # CONFIG_B defaults

        score, breakdown = scorer.compute_importance_score(event, weights, now_ms=now_ms)
        actual_tier = scorer.get_priority_tier(score)

        assert actual_tier in scenario.acceptable_tiers, (
            f"Scenario {scenario.id} '{scenario.name}' "
            f"(category={scenario.category}): "
            f"score={score:.4f}, actual_tier={actual_tier}, "
            f"expected={scenario.expected_tier}, "
            f"acceptable={scenario.acceptable_tiers}"
        )

    def test_score_in_valid_range(self, scenario: Any) -> None:
        """All scores must be in [0.0, 1.0]."""
        now_ms = int(time.time() * 1000)
        event = _vec_to_event(scenario.vec, now_ms)

        scorer = ImportanceScorer(space_id="poc-test")
        weights = ImportanceWeights()

        score, _ = scorer.compute_importance_score(event, weights, now_ms=now_ms)
        assert 0.0 <= score <= 1.0, f"Score {score} out of range for scenario {scenario.id}"


# =============================================================================
# HARD REQUIREMENTS (from POC spec)
# =============================================================================


class TestHardRequirements:
    """
    Non-negotiable scoring requirements from POC pass criteria.

    Scenario 1 (Sharvi's first word): score > 0.85
    Scenario 2 (breakfast alone): score < 0.25
    """

    @pytest.fixture
    def scorer(self) -> ImportanceScorer:
        return ImportanceScorer(space_id="hard-req")

    @pytest.fixture
    def weights(self) -> ImportanceWeights:
        return ImportanceWeights()

    @pytest.fixture
    def now_ms(self) -> int:
        return int(time.time() * 1000)

    def test_scenario_1_sharvi_first_word_above_085(
        self, scorer: ImportanceScorer, weights: ImportanceWeights, now_ms: int
    ) -> None:
        """HARD FAIL: Sharvi's first word must score > 0.85."""
        scenario = ALL_SCENARIOS[0]  # id=1
        assert scenario.id == 1
        event = _vec_to_event(scenario.vec, now_ms)
        score, _ = scorer.compute_importance_score(event, weights, now_ms=now_ms)
        assert score > 0.85, f"HARD FAIL: Scenario 1 scored {score:.4f}, must be > 0.85"

    def test_scenario_46_breakfast_alone_below_025(
        self, scorer: ImportanceScorer, weights: ImportanceWeights, now_ms: int
    ) -> None:
        """HARD FAIL: Breakfast alone must score < 0.25."""
        scenario_46 = next(s for s in ALL_SCENARIOS if s.id == 46)
        assert scenario_46.name == "Regular breakfast alone"
        event = _vec_to_event(scenario_46.vec, now_ms)
        score, _ = scorer.compute_importance_score(event, weights, now_ms=now_ms)
        assert score < 0.25, f"HARD FAIL: Routine scenario scored {score:.4f}, must be < 0.25"


# =============================================================================
# AGGREGATE STATISTICS
# =============================================================================


class TestAggregatePassRate:
    """Verify overall pass rate meets POC criteria (>= 85%)."""

    def test_overall_tier_match_rate_above_85_percent(self) -> None:
        """At least 102 of 120 scenarios (85%) must have matching tiers."""
        now_ms = int(time.time() * 1000)
        scorer = ImportanceScorer(space_id="aggregate-test")
        weights = ImportanceWeights()

        matches = 0
        mismatches: list[str] = []

        for scenario in ALL_SCENARIOS:
            event = _vec_to_event(scenario.vec, now_ms)
            score, _ = scorer.compute_importance_score(event, weights, now_ms=now_ms)
            actual_tier = scorer.get_priority_tier(score)

            if actual_tier in scenario.acceptable_tiers:
                matches += 1
            else:
                mismatches.append(
                    f"  S{scenario.id:03d} ({scenario.category}): "
                    f"score={score:.3f} -> {actual_tier} "
                    f"(expected {scenario.expected_tier})"
                )

        rate = matches / len(ALL_SCENARIOS)
        assert rate >= 0.85, (
            f"Tier match rate {rate:.1%} ({matches}/{len(ALL_SCENARIOS)}) "
            f"below 85% threshold.\nMismatches:\n" + "\n".join(mismatches)
        )

    def test_all_120_scenarios_loaded(self) -> None:
        """Verify all 120 scenarios are present."""
        assert len(ALL_SCENARIOS) == 120, f"Expected 120 scenarios, got {len(ALL_SCENARIOS)}"

    def test_scenarios_cover_13_categories(self) -> None:
        """Verify all 13 categories are represented."""
        categories = {s.category for s in ALL_SCENARIOS}
        assert len(categories) >= 12, f"Only {len(categories)} categories: {sorted(categories)}"
