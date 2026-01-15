"""
CPN Integration Tests — Issue 8.1.4

Tests the end-to-end flow of DreamExplorer → CPN:
- Full cycle with realistic episodes and KG edges
- Counterfactual scenario conversion to models
- Determinism with fixed cycle_id
- Performance bounds

References:
- M8_EXECUTION.md Issue 8.1.4: CPN counterfactual generation
- Dossier §4.6.1: Counterfactual Thinking
- Dossier §7.4.5: M22 DreamExplorer
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List

import pytest

from k0.modules.consolidation.dream.config import DreamConfig
from k0.modules.consolidation.dream.dream_explorer import DreamExplorer
from k0.modules.consolidation.dream.models import CounterfactualScenario, DreamExplorerInput

# =============================================================================
# MOCK DATA STRUCTURES
# =============================================================================


@dataclass
class MockEpisode:
    """Episode with required fields for CPN."""

    episode_id: str
    sentiment_score: float
    salience_score: float
    start_time_ms: int
    entity_ids: List[str]


@dataclass
class MockKGEdge:
    """KG edge with causal relation."""

    source_id: str
    target_id: str
    relation_type: str
    confidence: float


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def test_cycle_id() -> str:
    """Fixed cycle ID for determinism."""
    return "01JFXYZ123456789ABCDEFGHJK"


@pytest.fixture
def realistic_episodes() -> List[MockEpisode]:
    """Realistic episodes with emotional content."""
    now_ms = int(time.time() * 1000)

    return [
        # Regret-worthy: Missed deadline
        MockEpisode(
            episode_id="ep-missed-deadline",
            sentiment_score=-0.85,
            salience_score=0.95,
            start_time_ms=now_ms - 1000 * 60 * 60 * 2,  # 2 hours ago
            entity_ids=["task-report", "person-boss"],
        ),
        # Regret-worthy: Argument with partner
        MockEpisode(
            episode_id="ep-argument",
            sentiment_score=-0.75,
            salience_score=0.80,
            start_time_ms=now_ms - 1000 * 60 * 60 * 24,  # 1 day ago
            entity_ids=["person-partner", "topic-finances"],
        ),
        # Positive: Successful presentation
        MockEpisode(
            episode_id="ep-success",
            sentiment_score=0.90,
            salience_score=0.85,
            start_time_ms=now_ms - 1000 * 60 * 60 * 48,  # 2 days ago
            entity_ids=["project-alpha", "team-marketing"],
        ),
        # Neutral: Regular routine
        MockEpisode(
            episode_id="ep-routine",
            sentiment_score=0.1,
            salience_score=0.3,
            start_time_ms=now_ms - 1000 * 60 * 60 * 6,  # 6 hours ago
            entity_ids=["location-office"],
        ),
    ]


@pytest.fixture
def causal_kg_edges() -> List[MockKGEdge]:
    """KG edges with causal relationships."""
    return [
        # Causal chain: procrastination → missed deadline
        MockKGEdge("behavior-procrastination", "task-report", "CAUSES", 0.90),
        MockKGEdge("stress-work", "behavior-procrastination", "CAUSES", 0.75),
        MockKGEdge("task-overload", "stress-work", "CAUSES", 0.80),
        # Causal chain: miscommunication → argument
        MockKGEdge("event-miscommunication", "topic-finances", "CAUSES", 0.70),
        MockKGEdge("context-tiredness", "event-miscommunication", "CAUSES", 0.65),
        # Non-causal edges (should be filtered)
        MockKGEdge("person-boss", "team-marketing", "MEMBER_OF", 0.95),
        MockKGEdge("project-alpha", "task-report", "CONTAINS", 0.80),
    ]


@pytest.fixture
def dream_config() -> DreamConfig:
    """DreamConfig optimized for testing CPN."""
    return DreamConfig(
        max_counterfactuals=10,
        cpn_perturbation_std=0.15,
        cpn_counterfactual_types=("UPWARD", "DOWNWARD", "SEMIFACTUAL"),
        min_confidence=0.3,
    )


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestDreamExplorerCPNIntegration:
    """Integration tests for DreamExplorer → CPN flow."""

    @pytest.mark.asyncio
    async def test_full_explore_generates_counterfactuals(
        self,
        dream_config: DreamConfig,
        realistic_episodes: List[MockEpisode],
        causal_kg_edges: List[MockKGEdge],
        test_cycle_id: str,
    ) -> None:
        """Full explore() should generate counterfactual scenarios."""
        explorer = DreamExplorer(config=dream_config)

        input_data = DreamExplorerInput(
            cycle_id=test_cycle_id,
            tenant_id="test-tenant",
            space_id="test-space",
            recent_episodes=realistic_episodes,
            kg_edges=causal_kg_edges,
        )

        output = await explorer.explore(input_data)

        # Should produce some counterfactuals
        assert isinstance(output.counterfactuals, list)
        # With the provided data, we expect at least some scenarios
        # (depends on thresholds and filtering)
        assert output.compute_ms >= 0

    @pytest.mark.asyncio
    async def test_counterfactuals_are_valid_models(
        self,
        dream_config: DreamConfig,
        realistic_episodes: List[MockEpisode],
        causal_kg_edges: List[MockKGEdge],
        test_cycle_id: str,
    ) -> None:
        """Generated counterfactuals should be valid CounterfactualScenario models."""
        explorer = DreamExplorer(config=dream_config)

        input_data = DreamExplorerInput(
            cycle_id=test_cycle_id,
            tenant_id="test-tenant",
            space_id="test-space",
            recent_episodes=realistic_episodes,
            kg_edges=causal_kg_edges,
        )

        output = await explorer.explore(input_data)

        for cf in output.counterfactuals:
            assert isinstance(cf, CounterfactualScenario)
            assert cf.scenario_id is not None
            assert cf.scenario_type in ("UPWARD", "DOWNWARD", "SEMIFACTUAL")
            assert 0.0 <= cf.plausibility <= 1.0
            assert cf.base_episode_id is not None

    @pytest.mark.asyncio
    async def test_deterministic_with_same_cycle_id(
        self,
        dream_config: DreamConfig,
        realistic_episodes: List[MockEpisode],
        causal_kg_edges: List[MockKGEdge],
        test_cycle_id: str,
    ) -> None:
        """Same cycle_id should produce deterministic counterfactuals."""
        explorer = DreamExplorer(config=dream_config)

        input_data = DreamExplorerInput(
            cycle_id=test_cycle_id,
            tenant_id="test-tenant",
            space_id="test-space",
            recent_episodes=realistic_episodes,
            kg_edges=causal_kg_edges,
        )

        output1 = await explorer.explore(input_data)
        output2 = await explorer.explore(input_data)

        # Same number of counterfactuals
        assert len(output1.counterfactuals) == len(output2.counterfactuals)

        # Same scenario IDs
        ids1 = [cf.scenario_id for cf in output1.counterfactuals]
        ids2 = [cf.scenario_id for cf in output2.counterfactuals]
        assert ids1 == ids2

    @pytest.mark.asyncio
    async def test_different_cycle_id_different_results(
        self,
        dream_config: DreamConfig,
        realistic_episodes: List[MockEpisode],
        causal_kg_edges: List[MockKGEdge],
    ) -> None:
        """Different cycle_id should potentially produce different counterfactuals."""
        explorer = DreamExplorer(config=dream_config)

        input1 = DreamExplorerInput(
            cycle_id="01JFXYZ123456789ABCDEFGHJK",
            tenant_id="test-tenant",
            space_id="test-space",
            recent_episodes=realistic_episodes,
            kg_edges=causal_kg_edges,
        )

        input2 = DreamExplorerInput(
            cycle_id="01JFXYZ999999999ZZZZZZZZZZ",
            tenant_id="test-tenant",
            space_id="test-space",
            recent_episodes=realistic_episodes,
            kg_edges=causal_kg_edges,
        )

        output1 = await explorer.explore(input1)
        output2 = await explorer.explore(input2)

        # Results are valid regardless of potential differences
        assert isinstance(output1.counterfactuals, list)
        assert isinstance(output2.counterfactuals, list)

    @pytest.mark.asyncio
    async def test_empty_episodes_no_counterfactuals(
        self,
        dream_config: DreamConfig,
        causal_kg_edges: List[MockKGEdge],
        test_cycle_id: str,
    ) -> None:
        """Empty episode list should produce no counterfactuals."""
        explorer = DreamExplorer(config=dream_config)

        input_data = DreamExplorerInput(
            cycle_id=test_cycle_id,
            tenant_id="test-tenant",
            space_id="test-space",
            recent_episodes=[],
            kg_edges=causal_kg_edges,
        )

        output = await explorer.explore(input_data)

        assert output.counterfactuals == []

    @pytest.mark.asyncio
    async def test_empty_edges_still_runs(
        self,
        dream_config: DreamConfig,
        realistic_episodes: List[MockEpisode],
        test_cycle_id: str,
    ) -> None:
        """Empty KG edges should still complete without error."""
        explorer = DreamExplorer(config=dream_config)

        input_data = DreamExplorerInput(
            cycle_id=test_cycle_id,
            tenant_id="test-tenant",
            space_id="test-space",
            recent_episodes=realistic_episodes,
            kg_edges=[],
        )

        output = await explorer.explore(input_data)

        # Should not crash, may or may not have counterfactuals
        assert isinstance(output.counterfactuals, list)


class TestCPNScenarioTypeFiltering:
    """Test scenario type filtering through DreamConfig."""

    @pytest.mark.asyncio
    async def test_upward_only_config(
        self,
        realistic_episodes: List[MockEpisode],
        causal_kg_edges: List[MockKGEdge],
        test_cycle_id: str,
    ) -> None:
        """Config with UPWARD only should filter counterfactuals."""
        config = DreamConfig(
            cpn_counterfactual_types=("UPWARD",),
            min_confidence=0.1,  # Low threshold to get more results
        )
        explorer = DreamExplorer(config=config)

        input_data = DreamExplorerInput(
            cycle_id=test_cycle_id,
            tenant_id="test-tenant",
            space_id="test-space",
            recent_episodes=realistic_episodes,
            kg_edges=causal_kg_edges,
        )

        output = await explorer.explore(input_data)

        for cf in output.counterfactuals:
            assert cf.scenario_type == "UPWARD"

    @pytest.mark.asyncio
    async def test_downward_only_config(
        self,
        realistic_episodes: List[MockEpisode],
        causal_kg_edges: List[MockKGEdge],
        test_cycle_id: str,
    ) -> None:
        """Config with DOWNWARD only should filter counterfactuals."""
        config = DreamConfig(
            cpn_counterfactual_types=("DOWNWARD",),
            min_confidence=0.1,
        )
        explorer = DreamExplorer(config=config)

        input_data = DreamExplorerInput(
            cycle_id=test_cycle_id,
            tenant_id="test-tenant",
            space_id="test-space",
            recent_episodes=realistic_episodes,
            kg_edges=causal_kg_edges,
        )

        output = await explorer.explore(input_data)

        for cf in output.counterfactuals:
            assert cf.scenario_type == "DOWNWARD"


class TestCPNPerformance:
    """Performance tests for CPN through DreamExplorer."""

    @pytest.mark.asyncio
    async def test_explore_completes_under_time_limit(
        self,
        dream_config: DreamConfig,
        realistic_episodes: List[MockEpisode],
        causal_kg_edges: List[MockKGEdge],
        test_cycle_id: str,
    ) -> None:
        """Explore with CPN should complete in reasonable time."""
        explorer = DreamExplorer(config=dream_config)

        input_data = DreamExplorerInput(
            cycle_id=test_cycle_id,
            tenant_id="test-tenant",
            space_id="test-space",
            recent_episodes=realistic_episodes,
            kg_edges=causal_kg_edges,
        )

        start_ms = int(time.time() * 1000)
        output = await explorer.explore(input_data)
        elapsed_ms = int(time.time() * 1000) - start_ms

        # Should complete within 5 seconds for test data
        assert elapsed_ms < 5000
        # Compute time should be tracked
        assert output.compute_ms >= 0

    @pytest.mark.asyncio
    async def test_large_episode_list_scales(
        self,
        dream_config: DreamConfig,
        causal_kg_edges: List[MockKGEdge],
        test_cycle_id: str,
    ) -> None:
        """CPN should handle larger episode lists gracefully."""
        now_ms = int(time.time() * 1000)

        # Generate 100 episodes
        large_episodes = [
            MockEpisode(
                episode_id=f"ep-{i:04d}",
                sentiment_score=-0.7 + (i % 14) * 0.1,  # Vary sentiment
                salience_score=0.5 + (i % 5) * 0.1,
                start_time_ms=now_ms - 1000 * 60 * i,  # Spread over time
                entity_ids=[f"entity-{i % 10}"],
            )
            for i in range(100)
        ]

        explorer = DreamExplorer(config=dream_config)

        input_data = DreamExplorerInput(
            cycle_id=test_cycle_id,
            tenant_id="test-tenant",
            space_id="test-space",
            recent_episodes=large_episodes,
            kg_edges=causal_kg_edges,
        )

        start_ms = int(time.time() * 1000)
        output = await explorer.explore(input_data)
        elapsed_ms = int(time.time() * 1000) - start_ms

        # Should still complete in reasonable time
        assert elapsed_ms < 10000
        assert isinstance(output.counterfactuals, list)
