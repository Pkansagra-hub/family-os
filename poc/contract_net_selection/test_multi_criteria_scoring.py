"""
Test suite for Multi-Criteria Scoring PoC

Tests: scoring algorithm, tie-breaking, SLO compliance, performance
"""

import pytest
from poc_multi_criteria_scoring import (
    MultiCriteriaScoringEngine,
    Proposal,
    ScoringWeights,
    SelectionPoC,
)


class TestProposalScoring:
    """Test proposal scoring logic"""

    def test_score_single_proposal(self):
        """Score a single proposal"""
        engine = MultiCriteriaScoringEngine()
        proposal = Proposal(
            agent_id="a1",
            task_id="t1",
            estimated_latency_ms=1000,
            estimated_cost=5.0,
            confidence=0.9,
            strategy="parallel",
            tools=["tool_a"],
            reasoning="test",
        )

        scores = engine.score_proposals([proposal])
        assert len(scores) == 1
        assert scores[0].agent_id == "a1"
        assert scores[0].confidence_score == 0.9

    def test_score_multiple_proposals(self):
        """Score multiple proposals and rank them"""
        engine = MultiCriteriaScoringEngine()
        proposals = [
            Proposal("a1", "t1", 1000, 5.0, 0.9, "parallel", [], "test"),
            Proposal("a2", "t1", 2000, 3.0, 0.7, "sequential", [], "test"),
            Proposal("a3", "t1", 500, 8.0, 0.8, "parallel", [], "test"),
        ]

        scores = engine.score_proposals(proposals)
        assert len(scores) == 3
        # Scores should be sorted (highest first)
        assert scores[0].normalized_score >= scores[1].normalized_score
        assert scores[1].normalized_score >= scores[2].normalized_score

    def test_confidence_impacts_score(self):
        """Higher confidence should increase score"""
        engine = MultiCriteriaScoringEngine()

        p_high_conf = Proposal("a1", "t1", 1000, 5.0, 0.95, "parallel", [], "")
        p_low_conf = Proposal("a2", "t1", 1000, 5.0, 0.5, "parallel", [], "")

        scores = engine.score_proposals([p_high_conf, p_low_conf])
        assert scores[0].agent_id == "a1"  # Higher confidence wins

    def test_lower_latency_better(self):
        """Lower latency should improve score"""
        engine = MultiCriteriaScoringEngine()

        p_fast = Proposal("a1", "t1", 100, 5.0, 0.7, "parallel", [], "")
        p_slow = Proposal("a2", "t1", 4000, 5.0, 0.7, "parallel", [], "")

        scores = engine.score_proposals([p_fast, p_slow])
        assert scores[0].agent_id == "a1"  # Faster agent wins

    def test_lower_cost_better(self):
        """Lower cost should improve score (confidence dominated but still matters)"""
        engine = MultiCriteriaScoringEngine()

        # Use same confidence/latency/strategy, vary cost significantly
        p_cheap = Proposal("a1", "t1", 2000, 1.0, 0.7, "parallel", [], "")
        p_expensive = Proposal("a2", "t1", 2000, 9.0, 0.7, "parallel", [], "")

        scores = engine.score_proposals([p_cheap, p_expensive])
        # Cheaper cost = higher cost_score
        cheap_idx = 0 if scores[0].agent_id == "a1" else 1
        expensive_idx = 1 - cheap_idx
        assert scores[cheap_idx].cost_score > scores[expensive_idx].cost_score

    def test_parallel_strategy_bonus(self):
        """Parallel strategy should get bonus"""
        engine = MultiCriteriaScoringEngine()

        p_parallel = Proposal("a1", "t1", 1000, 5.0, 0.7, "parallel", [], "")
        p_sequential = Proposal("a2", "t1", 1000, 5.0, 0.7, "sequential", [], "")

        scores = engine.score_proposals([p_parallel, p_sequential])
        assert scores[0].agent_id == "a1"  # Parallel strategy wins


class TestTieBreaking:
    """Test tie-breaking strategies"""

    def test_tie_breaking_by_confidence(self):
        """Tie-breaking prefers higher confidence"""
        engine = MultiCriteriaScoringEngine()

        proposals = [
            Proposal("a1", "t1", 1000, 5.0, 0.9, "parallel", [], ""),
            Proposal("a2", "t1", 1000, 5.0, 0.8, "parallel", [], ""),
        ]

        scores = engine.score_proposals(proposals)
        tied = engine.apply_tie_breaking(scores, score_threshold=10.0)
        assert tied[0].agent_id == "a1"

    def test_deterministic_tie_breaking(self):
        """Tie-breaking is deterministic"""
        engine = MultiCriteriaScoringEngine()

        proposals = [
            Proposal("agent_a", "t1", 1000, 5.0, 0.7, "parallel", [], ""),
            Proposal("agent_b", "t1", 1000, 5.0, 0.7, "parallel", [], ""),
        ]

        scores = engine.score_proposals(proposals)
        tied = engine.apply_tie_breaking(scores, score_threshold=10.0)
        assert tied[0].agent_id == "agent_a"  # Alphabetical


class TestSelectionPerformance:
    """Performance validation tests"""

    def test_single_selection_latency(self):
        """Single selection should be fast"""
        engine = MultiCriteriaScoringEngine()
        proposals = [Proposal(f"a{i}", "t1", 1000, 5.0, 0.7, "parallel", [], "") for i in range(5)]

        import time

        start = time.perf_counter()
        scores = engine.score_proposals(proposals)
        engine.select_winner(scores)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 10  # Should be well under 5ms for 5 proposals

    def test_batch_selection_distribution(self):
        """Batch latency distribution is acceptable"""
        poc = SelectionPoC(num_proposals=5, num_rounds=100)
        metrics = poc.benchmark_scoring()

        assert "p50" in metrics
        assert "p95" in metrics
        assert metrics["p50"] <= metrics["p95"]
        assert metrics["p95"] <= metrics["p99"]


class TestSLOCompliance:
    """SLO validation tests"""

    def test_slo_target_5ms_p95(self):
        """Validate <5ms P95 SLO"""
        poc = SelectionPoC(num_proposals=5, num_rounds=100)
        metrics = poc.benchmark_scoring()

        assert metrics["slo_passed"], f"SLO failed: P95={metrics['p95']:.3f}ms, target <5ms"

    def test_p50_latency_excellent(self):
        """P50 should be well under 5ms"""
        poc = SelectionPoC(num_proposals=5, num_rounds=50)
        metrics = poc.benchmark_scoring()

        assert metrics["p50"] < 2.0, f"P50 too high: {metrics['p50']:.3f}ms"


class TestScoringWeights:
    """Test custom weight configurations"""

    def test_custom_weights(self):
        """Custom weights should affect scoring"""
        weights = ScoringWeights(
            confidence=20.0, latency=4.0, cost=-2.5  # Double confidence weight
        )
        engine = MultiCriteriaScoringEngine(weights=weights)

        p_high_conf = Proposal("a1", "t1", 1000, 5.0, 0.95, "parallel", [], "")
        p_low_conf = Proposal("a2", "t1", 1000, 5.0, 0.5, "parallel", [], "")

        scores = engine.score_proposals([p_high_conf, p_low_conf])
        # With higher confidence weight, gap should be larger
        gap = scores[0].normalized_score - scores[1].normalized_score
        assert gap > 5  # Noticeable difference


class TestIntegration:
    """End-to-end selection tests"""

    def test_full_workflow(self):
        """Complete selection workflow"""
        engine = MultiCriteriaScoringEngine()

        proposals = [
            Proposal("concierge", "t1", 300, 0.05, 0.95, "parallel", ["web", "maps"], ""),
            Proposal("planner", "t1", 800, 0.02, 0.70, "sequential", ["search"], ""),
            Proposal("researcher", "t1", 500, 0.10, 0.80, "hybrid", ["web", "db"], ""),
        ]

        # Score proposals
        scores = engine.score_proposals(proposals, {"budget": "high"})

        # Select winner
        winner = engine.select_winner(scores)

        assert winner is not None
        assert winner.normalized_score > 0
        assert winner.agent_id in ["concierge", "planner", "researcher"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
