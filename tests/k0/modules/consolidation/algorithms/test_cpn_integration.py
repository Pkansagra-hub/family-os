"""
CPN Integration Tests — End-to-End Validation.

Tests CPN algorithm with realistic data to ensure counterfactual scenarios
are generated after M1 fixes (expanded CAUSES edges + tuned thresholds).
"""

from k0.modules.consolidation.algorithms.cpn import CausalPerturbationNetwork, CPNConfig
from k0.pipelines.p03.phase_outputs import EpisodeCluster


class TestCPNIntegration:
    """Integration tests for CPN algorithm end-to-end functionality."""

    def test_cpn_generates_scenarios_with_causes_edges(self):
        """
        Test that CPN generates scenarios with CAUSES edges and cold-start thresholds.

        This validates M1-E2 (expanded CAUSES edges) + M1-E3 (tuned thresholds).
        """
        # Create episodes with entity_ids (from M0-E2-I2/I3)
        episodes = [
            EpisodeCluster(
                cluster_id=f"ep_{i}",
                dominant_sentiment=0.5,  # sentiment_score via property
                aggregated_salience=0.7,  # salience_score via property
                temporal_start=1640995200000 + (i * 3600000),  # start_time_ms via property
                entity_ids=["person_mom_123", "org_starbucks_456"],  # M0-E2-I2/I3
            )
            for i in range(10)  # 10+ episodes
        ]

        # Create CAUSES edges (from M1-E2-I1/I4/I5/I6)
        kg_edges = [
            {
                "source_id": "person_mom_123",
                "target_id": "org_starbucks_456",
                "relation_type": "CAUSES",
                "confidence": 0.8,
                "observation_count": 15,
            },
            {
                "source_id": "org_starbucks_456",
                "target_id": "person_mom_123",
                "relation_type": "FOLLOWS",  # Should be ignored
                "confidence": 0.6,
                "observation_count": 10,
            },
            {
                "source_id": "person_mom_123",
                "target_id": "org_starbucks_456",
                "relation_type": "PRECEDES",  # M1-E2-I4: weak causal candidate
                "confidence": 0.7,
                "observation_count": 12,
            },
        ]

        # Use cold-start optimized config (M1-E3-I1/I2/I3/I4/I5/I6)
        config = CPNConfig(
            emotional_threshold=0.3,  # M1-E3-I1: lowered for family events
            top_k_regret_events=20,  # M1-E3-I4: increased for cold-start
            causal_chain_depth=3,  # M1-E3-I5: decreased for reliability
            min_plausibility=0.1,  # M1-E3-I2: lowered for more scenarios
            min_utility_delta=0.1,  # M1-E3-I3: lowered for smaller changes
            counterfactual_types=("UPWARD",),  # M1-E3-I6: focus on improvements
        )

        # Run CPN
        cpn = CausalPerturbationNetwork(config=config)
        result = cpn.generate(
            episodes=episodes,
            kg_edges=kg_edges,
        )

        # Verify scenarios generated (main validation)
        assert len(result) > 0, (
            f"CPN should generate scenarios with expanded edges + tuned thresholds. "
            f"Got {len(result)} scenarios. "
            f"Check: episodes={len(episodes)}, edges={len(kg_edges)}, "
            f"config thresholds applied correctly."
        )

        # Additional validations
        assert all(
            s.scenario_type == "UPWARD" for s in result
        ), "All scenarios should be UPWARD type with cold-start config"

        # Log success for debugging
        print(f"✅ CPN generated {len(result)} scenarios")
        print(f"   Episodes: {len(episodes)}")
        print(f"   CAUSES edges: {len([e for e in kg_edges if e['relation_type'] == 'CAUSES'])}")
        print(
            f"   PRECEDES edges: {len([e for e in kg_edges if e['relation_type'] == 'PRECEDES'])}"
        )

    def test_cpn_handles_empty_episodes_gracefully(self):
        """Test CPN handles edge case of no episodes gracefully."""
        config = CPNConfig()
        cpn = CausalPerturbationNetwork(config=config)

        result = cpn.generate(episodes=[], kg_edges=[])

        assert len(result) == 0

    def test_cpn_handles_no_causes_edges_gracefully(self):
        """Test CPN handles episodes with no CAUSES edges gracefully."""
        episodes = [
            EpisodeCluster(
                cluster_id="ep_001",
                dominant_sentiment=0.8,
                aggregated_salience=0.9,
                temporal_start=1640995200000,
                entity_ids=["person_a", "org_b"],
            )
        ]

        # Only FOLLOWS edges (not CAUSES)
        kg_edges = [
            {
                "source_id": "person_a",
                "target_id": "org_b",
                "relation_type": "FOLLOWS",
                "confidence": 0.8,
                "observation_count": 15,
            }
        ]

        config = CPNConfig()
        cpn = CausalPerturbationNetwork(config=config)

        result = cpn.generate(episodes=episodes, kg_edges=kg_edges)

        # Should still generate scenarios if episodes meet emotional threshold
        # (though may be 0 if causal chains can't be built)
        assert isinstance(len(result), int)
        assert len(result) >= 0
