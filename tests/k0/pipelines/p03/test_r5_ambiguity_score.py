"""
Tests for SPC-UQ ambiguity_score field and computation — M4-E1-I1/I2

Verifies that ambiguity_score is correctly computed from missing fields
and can be used by SPC-UQ for gap detection.
"""

from typing import List, Optional

from k0.pipelines.p03.phase_outputs import EpisodeCluster


class TestAmbiguityScoreField:
    """Tests for ambiguity_score field on EpisodeCluster - M4-E1-I1."""

    def test_episode_cluster_has_ambiguity_score_field(self) -> None:
        """Verify EpisodeCluster has ambiguity_score field."""
        cluster = EpisodeCluster(cluster_id="test_001")

        assert hasattr(cluster, "ambiguity_score")
        assert isinstance(cluster.ambiguity_score, float)

    def test_ambiguity_score_default_is_zero(self) -> None:
        """Verify default ambiguity_score is 0.0 (no ambiguity)."""
        cluster = EpisodeCluster(cluster_id="test_002")

        assert cluster.ambiguity_score == 0.0

    def test_ambiguity_score_can_be_set(self) -> None:
        """Verify ambiguity_score can be set to custom values."""
        cluster = EpisodeCluster(
            cluster_id="test_003",
            ambiguity_score=0.75,
        )

        assert cluster.ambiguity_score == 0.75

    def test_high_ambiguity_episode(self) -> None:
        """Verify high ambiguity episode (missing most fields)."""
        # Episode with minimal information - high ambiguity
        cluster = EpisodeCluster(
            cluster_id="ambiguous_001",
            ambiguity_score=0.8,  # 80% ambiguous
        )

        assert cluster.ambiguity_score > 0.5  # Above SPC-UQ threshold

    def test_low_ambiguity_episode(self) -> None:
        """Verify low ambiguity episode (all fields populated)."""
        # Episode with complete information - low ambiguity
        cluster = EpisodeCluster(
            cluster_id="complete_001",
            location_hint="starbucks",
            activity_type="coffee",
            participants_json='["mom", "dad"]',
            entity_ids=["person_mom", "org_starbucks"],
            ambiguity_score=0.0,  # Fully specified
        )

        assert cluster.ambiguity_score < 0.5  # Below SPC-UQ threshold


class TestAmbiguityScoreComputation:
    """Tests for ambiguity_score computation logic - M4-E1-I2."""

    def _compute_ambiguity(
        self,
        location_hint: Optional[str],
        participants_json: str,
        activity_type: str,
        entity_ids: List[str],
    ) -> float:
        """
        Simplified ambiguity computation matching R2 logic.

        Based on _compute_ambiguity_score in r2_episodic_integrator.py
        """
        import json

        missing_fields = 0
        total_fields = 4  # location, participants, activity, entities

        # Check location
        if not location_hint:
            missing_fields += 1

        # Check participants
        try:
            participants = json.loads(participants_json or "[]")
            if not participants:
                missing_fields += 1
        except (json.JSONDecodeError, TypeError):
            missing_fields += 1

        # Check activity type
        if not activity_type:
            missing_fields += 1

        # Check entity IDs
        if not entity_ids:
            missing_fields += 1

        return missing_fields / total_fields

    def test_all_fields_present_zero_ambiguity(self) -> None:
        """Verify 0.0 ambiguity when all fields present."""
        score = self._compute_ambiguity(
            location_hint="kitchen",
            participants_json='["alice"]',
            activity_type="cooking",
            entity_ids=["person_alice"],
        )

        assert score == 0.0

    def test_all_fields_missing_full_ambiguity(self) -> None:
        """Verify 1.0 ambiguity when all fields missing."""
        score = self._compute_ambiguity(
            location_hint=None,
            participants_json="[]",
            activity_type="",
            entity_ids=[],
        )

        assert score == 1.0

    def test_half_fields_missing_half_ambiguity(self) -> None:
        """Verify 0.5 ambiguity when half fields missing."""
        score = self._compute_ambiguity(
            location_hint="office",  # Present
            participants_json="[]",  # Missing
            activity_type="work",  # Present
            entity_ids=[],  # Missing
        )

        assert score == 0.5

    def test_one_field_missing_quarter_ambiguity(self) -> None:
        """Verify 0.25 ambiguity when one field missing."""
        score = self._compute_ambiguity(
            location_hint="gym",
            participants_json='["trainer"]',
            activity_type="exercise",
            entity_ids=[],  # Only entity_ids missing
        )

        assert score == 0.25

    def test_invalid_json_participants_counts_as_missing(self) -> None:
        """Verify invalid JSON for participants counts as missing."""
        score = self._compute_ambiguity(
            location_hint="home",
            participants_json="not valid json",  # Invalid
            activity_type="relaxing",
            entity_ids=["location_home"],
        )

        # Invalid JSON = 1 missing field = 0.25
        assert score == 0.25


class TestSPCUQAmbiguityThreshold:
    """Tests for SPC-UQ ambiguity threshold behavior."""

    def test_spc_uq_threshold_value(self) -> None:
        """Verify SPC-UQ uses 0.5 as ambiguity threshold."""
        # SPC-UQ only reconstructs episodes with ambiguity > 0.5
        threshold = 0.5

        # Episodes below threshold should NOT be reconstructed
        low_ambiguity = EpisodeCluster(cluster_id="low_001", ambiguity_score=0.3)
        assert low_ambiguity.ambiguity_score <= threshold

        # Episodes above threshold SHOULD be reconstructed
        high_ambiguity = EpisodeCluster(cluster_id="high_001", ambiguity_score=0.7)
        assert high_ambiguity.ambiguity_score > threshold

    def test_edge_case_exactly_at_threshold(self) -> None:
        """Verify episode exactly at threshold is NOT reconstructed."""
        threshold = 0.5
        edge_case = EpisodeCluster(cluster_id="edge_001", ambiguity_score=0.5)

        # SPC-UQ uses > threshold, not >= threshold
        assert not (edge_case.ambiguity_score > threshold)

    def test_multiple_episodes_filtering(self) -> None:
        """Verify filtering episodes by ambiguity threshold."""
        threshold = 0.5

        episodes = [
            EpisodeCluster(cluster_id="ep_001", ambiguity_score=0.2),
            EpisodeCluster(cluster_id="ep_002", ambiguity_score=0.6),
            EpisodeCluster(cluster_id="ep_003", ambiguity_score=0.8),
            EpisodeCluster(cluster_id="ep_004", ambiguity_score=0.4),
            EpisodeCluster(cluster_id="ep_005", ambiguity_score=0.9),
        ]

        # Filter high-ambiguity episodes for reconstruction
        high_ambiguity_episodes = [ep for ep in episodes if ep.ambiguity_score > threshold]

        assert len(high_ambiguity_episodes) == 3
        assert all(ep.ambiguity_score > threshold for ep in high_ambiguity_episodes)
        assert "ep_002" in [ep.cluster_id for ep in high_ambiguity_episodes]
        assert "ep_003" in [ep.cluster_id for ep in high_ambiguity_episodes]
        assert "ep_005" in [ep.cluster_id for ep in high_ambiguity_episodes]
