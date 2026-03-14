"""
Tests for KG Relationship Boost -- Issue 5.F.1.9

Tests proving:
    1. Entity extraction from ner_entities_json parses all formats
    2. Entity pair formation produces correct combinations
    3. Edge cache loads and lookups work correctly
    4. Boost computation follows ADR-K026 formula
    5. Feature flag disables boost (relationship_boost=1.0)
    6. Integration with ImportanceScorer: events with KG edges score higher
    7. No KG data = no penalty (boost >= 1.0 always)
    8. Boost cap prevents runaway

References:
    - ADR-K026: KG Relationship Boost for R1 Importance Scoring
    - Issue 5.F.1.2-5.F.1.9
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.modules.consolidation.algorithms.importance_scorer import (
    ImportanceScorer,
    ImportanceWeights,
)
from k0.modules.consolidation.algorithms.kg_relationship_boost import (
    KGBoostConfig,
    KGEdgeCache,
    compute_relationship_boost,
    extract_entity_ids,
    extract_entity_pairs,
)

# =============================================================================
# Mock Event
# =============================================================================


@dataclass
class MockEvent:
    """Mock event for KG boost testing."""

    event_id: str = "evt_test_001"
    sentiment_score: float = 0.5
    affect_valence: float = 0.3
    affect_arousal: float = 0.4
    surprise_level: float = 0.2
    novelty: str = "NOVEL"
    salience_score: float = 0.0
    num_participants: int = 2
    social_intimacy: str = "HIGH"
    identity_relevance: float = 0.5
    identity_domains_json: str = "[]"
    timestamp: int = 0
    content_type: str = "message"
    activity_type_ultrabert: str = ""
    intent_label: str = ""
    intent_ultrabert: str = ""
    elaboration_depth: str = ""
    narrative_is_goal_event: bool = False
    narrative_arc_position: str = ""
    temporal_orientation: str = ""
    source_reliability: float = 1.0
    source_type: str = ""
    memory_tier: str = "routine"
    ner_entities_json: str = "[]"
    importance_score: float = 0.0
    importance_computed: bool = False

    def set_importance(
        self,
        score: float,
        recency: float,
        affect: float,
        social: float,
        novelty: float,
        surprise: float = 0.0,
        identity: float = 0.0,
    ) -> None:
        self.importance_score = score
        self.importance_computed = True


# =============================================================================
# Entity Extraction Tests
# =============================================================================


class TestEntityExtraction:
    """Test extract_entity_ids from NER JSON."""

    def test_empty_json(self) -> None:
        """Empty array returns no entities."""
        assert extract_entity_ids("[]") == []

    def test_empty_string(self) -> None:
        """Empty string returns no entities."""
        assert extract_entity_ids("") == []

    def test_invalid_json(self) -> None:
        """Invalid JSON returns no entities."""
        assert extract_entity_ids("not json") == []

    def test_entity_id_format(self) -> None:
        """Entities with entity_id field are extracted."""
        json_str = '[{"entity_id": "e1"}, {"entity_id": "e2"}]'
        result = extract_entity_ids(json_str)
        assert result == ["e1", "e2"]

    def test_canonical_name_format(self) -> None:
        """Entities with canonical_name field are extracted."""
        json_str = '[{"canonical_name": "Mom"}, {"canonical_name": "Dad"}]'
        result = extract_entity_ids(json_str)
        assert result == ["Mom", "Dad"]

    def test_text_format(self) -> None:
        """NER output with text field is extracted."""
        json_str = '[{"text": "Mom", "label": "PERSON"}, {"text": "Dad", "label": "PERSON"}]'
        result = extract_entity_ids(json_str)
        assert result == ["Mom", "Dad"]

    def test_priority_entity_id_over_name(self) -> None:
        """entity_id takes priority over canonical_name."""
        json_str = '[{"entity_id": "e1", "canonical_name": "Mom"}]'
        result = extract_entity_ids(json_str)
        assert result == ["e1"]

    def test_deduplication(self) -> None:
        """Duplicate entities are removed."""
        json_str = '[{"entity_id": "e1"}, {"entity_id": "e1"}, {"entity_id": "e2"}]'
        result = extract_entity_ids(json_str)
        assert result == ["e1", "e2"]

    def test_none_input(self) -> None:
        """None input returns no entities."""
        assert extract_entity_ids(None) == []  # type: ignore[arg-type]

    def test_whitespace_stripped(self) -> None:
        """Entity IDs have whitespace stripped."""
        json_str = '[{"entity_id": " e1 "}, {"entity_id": "e2"}]'
        result = extract_entity_ids(json_str)
        assert result == ["e1", "e2"]

    def test_empty_entities_skipped(self) -> None:
        """Entities with empty ID are skipped."""
        json_str = '[{"entity_id": ""}, {"entity_id": "e2"}, {"text": ""}]'
        result = extract_entity_ids(json_str)
        assert result == ["e2"]

    def test_non_dict_entries_skipped(self) -> None:
        """Non-dict entries in array are skipped."""
        json_str = '["not_a_dict", {"entity_id": "e1"}, 42]'
        result = extract_entity_ids(json_str)
        assert result == ["e1"]

    def test_mixed_formats(self) -> None:
        """Mix of entity_id, canonical_name, and text works."""
        json_str = '[{"entity_id": "e1"}, {"canonical_name": "Mom"}, {"text": "Home"}]'
        result = extract_entity_ids(json_str)
        assert result == ["e1", "Mom", "Home"]


# =============================================================================
# Entity Pair Formation Tests
# =============================================================================


class TestEntityPairs:
    """Test extract_entity_pairs combinations."""

    def test_no_entities(self) -> None:
        """No entities = no pairs."""
        assert extract_entity_pairs([]) == []

    def test_single_entity(self) -> None:
        """Single entity = no pairs."""
        assert extract_entity_pairs(["e1"]) == []

    def test_two_entities(self) -> None:
        """Two entities = one pair (sorted)."""
        pairs = extract_entity_pairs(["e2", "e1"])
        assert pairs == [("e1", "e2")]

    def test_three_entities(self) -> None:
        """Three entities = three pairs."""
        pairs = extract_entity_pairs(["e1", "e2", "e3"])
        assert len(pairs) == 3
        assert ("e1", "e2") in pairs
        assert ("e1", "e3") in pairs
        assert ("e2", "e3") in pairs

    def test_four_entities(self) -> None:
        """Four entities = six pairs (4 choose 2)."""
        pairs = extract_entity_pairs(["a", "b", "c", "d"])
        assert len(pairs) == 6

    def test_pairs_are_sorted(self) -> None:
        """Each pair has elements in sorted order."""
        pairs = extract_entity_pairs(["z", "a", "m"])
        for a, b in pairs:
            assert a <= b


# =============================================================================
# Edge Cache Tests
# =============================================================================


class TestKGEdgeCache:
    """Test KGEdgeCache loading and lookup."""

    @pytest.mark.asyncio
    async def test_load_empty(self) -> None:
        """Loading with no syscalls results in empty cache."""
        cache = KGEdgeCache()
        await cache.load_edges(tenant_id="t1", space_id="s1")
        assert cache.loaded is True
        assert cache.edge_count == 0

    @pytest.mark.asyncio
    async def test_load_from_syscalls(self) -> None:
        """Load edges from mock syscalls."""
        syscalls = MagicMock()
        syscalls.kg_edges_query = AsyncMock(
            return_value={
                "edges": [
                    {"source_entity_id": "e1", "target_entity_id": "e2", "weight": 0.8},
                    {"source_entity_id": "e3", "target_entity_id": "e4", "weight": 0.5},
                ],
                "count": 2,
            }
        )
        cache = KGEdgeCache()
        await cache.load_edges(tenant_id="t1", space_id="s1", syscalls=syscalls)
        assert cache.loaded is True
        assert cache.edge_count == 2

    @pytest.mark.asyncio
    async def test_bidirectional_lookup(self) -> None:
        """Edge weight lookup works in both directions."""
        syscalls = MagicMock()
        syscalls.kg_edges_query = AsyncMock(
            return_value={
                "edges": [
                    {"source_entity_id": "Mom", "target_entity_id": "Dad", "weight": 0.9},
                ],
                "count": 1,
            }
        )
        cache = KGEdgeCache()
        await cache.load_edges(tenant_id="t1", space_id="s1", syscalls=syscalls)
        # Both orderings return same weight
        assert cache.get_edge_weight("Mom", "Dad") == 0.9
        assert cache.get_edge_weight("Dad", "Mom") == 0.9

    @pytest.mark.asyncio
    async def test_missing_edge_returns_none(self) -> None:
        """Lookup for non-existent pair returns None."""
        cache = KGEdgeCache()
        await cache.load_edges(tenant_id="t1", space_id="s1")
        assert cache.get_edge_weight("e1", "e2") is None

    @pytest.mark.asyncio
    async def test_keeps_highest_weight(self) -> None:
        """Multiple edges between same pair keeps highest weight."""
        syscalls = MagicMock()
        syscalls.kg_edges_query = AsyncMock(
            return_value={
                "edges": [
                    {"source_entity_id": "e1", "target_entity_id": "e2", "weight": 0.3},
                    {"source_entity_id": "e1", "target_entity_id": "e2", "weight": 0.8},
                ],
                "count": 2,
            }
        )
        cache = KGEdgeCache()
        await cache.load_edges(tenant_id="t1", space_id="s1", syscalls=syscalls)
        assert cache.get_edge_weight("e1", "e2") == 0.8

    @pytest.mark.asyncio
    async def test_load_survives_exception(self) -> None:
        """Cache handles syscall exceptions gracefully."""
        syscalls = MagicMock()
        syscalls.kg_edges_query = AsyncMock(side_effect=RuntimeError("DB error"))
        cache = KGEdgeCache()
        await cache.load_edges(tenant_id="t1", space_id="s1", syscalls=syscalls)
        assert cache.loaded is True
        assert cache.edge_count == 0

    @pytest.mark.asyncio
    async def test_zero_weight_edges_excluded(self) -> None:
        """Edges with weight=0 are excluded."""
        syscalls = MagicMock()
        syscalls.kg_edges_query = AsyncMock(
            return_value={
                "edges": [
                    {"source_entity_id": "e1", "target_entity_id": "e2", "weight": 0.0},
                    {"source_entity_id": "e3", "target_entity_id": "e4", "weight": 0.5},
                ],
                "count": 2,
            }
        )
        cache = KGEdgeCache()
        await cache.load_edges(tenant_id="t1", space_id="s1", syscalls=syscalls)
        assert cache.edge_count == 1
        assert cache.get_edge_weight("e1", "e2") is None
        assert cache.get_edge_weight("e3", "e4") == 0.5


# =============================================================================
# Boost Computation Tests
# =============================================================================


class TestComputeRelationshipBoost:
    """Test compute_relationship_boost formula."""

    def _make_cache(self, edges: dict[str, float]) -> KGEdgeCache:
        """Create cache with pre-loaded edges."""
        cache = KGEdgeCache()
        cache._loaded = True
        for pair_key, weight in edges.items():
            cache._edges[pair_key] = weight
        cache._edge_count = len(edges)
        return cache

    def test_disabled_config(self) -> None:
        """Disabled config returns 1.0 boost."""
        config = KGBoostConfig(enabled=False)
        cache = self._make_cache({"a:b": 0.9})
        boost, max_w = compute_relationship_boost(["a", "b"], cache, config)
        assert boost == 1.0
        assert max_w == 0.0

    def test_no_entities(self) -> None:
        """No entities returns 1.0 boost."""
        config = KGBoostConfig(enabled=True)
        cache = self._make_cache({})
        boost, max_w = compute_relationship_boost([], cache, config)
        assert boost == 1.0

    def test_single_entity(self) -> None:
        """Single entity (no pairs) returns 1.0 boost."""
        config = KGBoostConfig(enabled=True)
        cache = self._make_cache({})
        boost, max_w = compute_relationship_boost(["e1"], cache, config)
        assert boost == 1.0

    def test_no_matching_edges(self) -> None:
        """Entity pairs with no KG edges returns 1.0 boost."""
        config = KGBoostConfig(enabled=True)
        cache = self._make_cache({"x:y": 0.9})  # Different entities
        boost, max_w = compute_relationship_boost(["a", "b"], cache, config)
        assert boost == 1.0
        assert max_w == 0.0

    def test_basic_boost_formula(self) -> None:
        """boost = 1.0 + boost_scale * max_edge_weight."""
        config = KGBoostConfig(enabled=True, boost_scale=0.15)
        cache = self._make_cache({"a:b": 0.8})
        boost, max_w = compute_relationship_boost(["a", "b"], cache, config)
        expected = 1.0 + 0.15 * 0.8  # 1.12
        assert abs(boost - expected) < 0.001
        assert max_w == 0.8

    def test_max_edge_among_pairs(self) -> None:
        """Uses maximum edge weight across all entity pairs."""
        config = KGBoostConfig(enabled=True, boost_scale=0.15)
        cache = self._make_cache({"a:b": 0.3, "a:c": 0.9, "b:c": 0.5})
        boost, max_w = compute_relationship_boost(["a", "b", "c"], cache, config)
        expected = 1.0 + 0.15 * 0.9  # Max is 0.9
        assert abs(boost - expected) < 0.001
        assert max_w == 0.9

    def test_boost_cap(self) -> None:
        """Boost is capped at 1.0 + max_boost_cap."""
        config = KGBoostConfig(
            enabled=True,
            boost_scale=0.50,  # Aggressive scale
            max_boost_cap=0.20,  # But capped at 0.20
        )
        cache = self._make_cache({"a:b": 1.0})
        boost, max_w = compute_relationship_boost(["a", "b"], cache, config)
        # 0.50 * 1.0 = 0.50, but capped to 0.20
        assert abs(boost - 1.20) < 0.001

    def test_min_edge_weight_filter(self) -> None:
        """Edges below min_edge_weight are ignored."""
        config = KGBoostConfig(enabled=True, boost_scale=0.15, min_edge_weight=0.10)
        cache = self._make_cache({"a:b": 0.03})  # Below threshold
        boost, max_w = compute_relationship_boost(["a", "b"], cache, config)
        assert boost == 1.0
        assert max_w == 0.0

    def test_boost_never_below_one(self) -> None:
        """Boost is always >= 1.0 (never penalizes)."""
        config = KGBoostConfig(enabled=True, boost_scale=0.15)
        cache = self._make_cache({"a:b": 0.001})  # Very small weight
        boost, max_w = compute_relationship_boost(["a", "b"], cache, config)
        assert boost >= 1.0

    def test_full_strength_edge(self) -> None:
        """Edge weight = 1.0 gives maximum boost."""
        config = KGBoostConfig(enabled=True, boost_scale=0.15, max_boost_cap=0.20)
        cache = self._make_cache({"a:b": 1.0})
        boost, _ = compute_relationship_boost(["a", "b"], cache, config)
        expected = 1.0 + min(0.15 * 1.0, 0.20)  # 1.15
        assert abs(boost - expected) < 0.001


# =============================================================================
# Integration with ImportanceScorer
# =============================================================================


class TestScorerKGBoostIntegration:
    """Test KG boost integrated into ImportanceScorer."""

    @pytest.mark.asyncio
    async def test_boost_disabled_no_effect(self) -> None:
        """With KG boost disabled, scores are unchanged."""
        scorer_no_boost = ImportanceScorer(space_id="sp_test")
        scorer_with_config = ImportanceScorer(
            space_id="sp_test",
            kg_boost_config=KGBoostConfig(enabled=False),
        )
        now_ms = int(time.time() * 1000)
        event = MockEvent(timestamp=now_ms - 3600_000)
        weights = ImportanceWeights()
        score1, _ = scorer_no_boost.compute_importance_score(event, weights, now_ms)
        score2, _ = scorer_with_config.compute_importance_score(event, weights, now_ms)
        assert abs(score1 - score2) < 0.0001

    @pytest.mark.asyncio
    async def test_no_edge_cache_no_effect(self) -> None:
        """With no edge cache, relationship_boost=1.0."""
        config = KGBoostConfig(enabled=True, boost_scale=0.15)
        scorer = ImportanceScorer(
            space_id="sp_test",
            kg_boost_config=config,
            kg_edge_cache=None,  # No cache
        )
        now_ms = int(time.time() * 1000)
        event = MockEvent(
            timestamp=now_ms - 3600_000,
            ner_entities_json='[{"entity_id": "e1"}, {"entity_id": "e2"}]',
        )
        weights = ImportanceWeights()
        _, breakdown = scorer.compute_importance_score(event, weights, now_ms)
        assert breakdown.relationship_boost == 1.0
        assert breakdown.max_edge_weight == 0.0

    @pytest.mark.asyncio
    async def test_strong_edge_boosts_score(self) -> None:
        """Event with strong KG edge scores higher than without."""
        now_ms = int(time.time() * 1000)
        event = MockEvent(
            timestamp=now_ms - 3600_000,
            sentiment_score=0.5,
            affect_valence=0.4,
            affect_arousal=0.3,
            surprise_level=0.3,
            novelty="NOVEL",
            num_participants=2,
            social_intimacy="HIGH",
            identity_relevance=0.5,
            ner_entities_json='[{"entity_id": "Mom"}, {"entity_id": "Dad"}]',
        )
        weights = ImportanceWeights()

        # Score without boost
        scorer_no = ImportanceScorer(space_id="sp_test")
        score_no, _ = scorer_no.compute_importance_score(event, weights, now_ms)

        # Score with boost (strong Mom-Dad edge)
        cache = KGEdgeCache()
        cache._loaded = True
        cache._edges = {"Dad:Mom": 0.9}
        cache._edge_count = 1
        config = KGBoostConfig(enabled=True, boost_scale=0.15)
        scorer_yes = ImportanceScorer(
            space_id="sp_test",
            kg_boost_config=config,
            kg_edge_cache=cache,
        )
        score_yes, breakdown = scorer_yes.compute_importance_score(event, weights, now_ms)

        # Boosted score should be higher
        assert score_yes > score_no
        assert breakdown.relationship_boost > 1.0
        assert breakdown.max_edge_weight == 0.9

    @pytest.mark.asyncio
    async def test_no_entities_no_boost(self) -> None:
        """Event with no NER entities gets no boost."""
        now_ms = int(time.time() * 1000)
        cache = KGEdgeCache()
        cache._loaded = True
        cache._edges = {"a:b": 0.9}
        cache._edge_count = 1
        config = KGBoostConfig(enabled=True, boost_scale=0.15)
        scorer = ImportanceScorer(
            space_id="sp_test",
            kg_boost_config=config,
            kg_edge_cache=cache,
        )
        event = MockEvent(
            timestamp=now_ms - 3600_000,
            ner_entities_json="[]",
        )
        weights = ImportanceWeights()
        _, breakdown = scorer.compute_importance_score(event, weights, now_ms)
        assert breakdown.relationship_boost == 1.0

    @pytest.mark.asyncio
    async def test_weak_edge_small_boost(self) -> None:
        """Weak edge gives small boost."""
        now_ms = int(time.time() * 1000)
        cache = KGEdgeCache()
        cache._loaded = True
        cache._edges = {"Dad:Mom": 0.2}
        cache._edge_count = 1
        config = KGBoostConfig(enabled=True, boost_scale=0.15)
        scorer = ImportanceScorer(
            space_id="sp_test",
            kg_boost_config=config,
            kg_edge_cache=cache,
        )
        event = MockEvent(
            timestamp=now_ms - 3600_000,
            ner_entities_json='[{"entity_id": "Mom"}, {"entity_id": "Dad"}]',
        )
        weights = ImportanceWeights()
        _, breakdown = scorer.compute_importance_score(event, weights, now_ms)
        expected_boost = 1.0 + 0.15 * 0.2  # 1.03
        assert abs(breakdown.relationship_boost - expected_boost) < 0.001

    @pytest.mark.asyncio
    async def test_breakdown_includes_boost_fields(self) -> None:
        """ImportanceBreakdown to_dict includes relationship_boost and max_edge_weight."""
        now_ms = int(time.time() * 1000)
        cache = KGEdgeCache()
        cache._loaded = True
        cache._edges = {"Dad:Mom": 0.7}
        cache._edge_count = 1
        config = KGBoostConfig(enabled=True, boost_scale=0.15)
        scorer = ImportanceScorer(
            space_id="sp_test",
            kg_boost_config=config,
            kg_edge_cache=cache,
        )
        event = MockEvent(
            timestamp=now_ms - 3600_000,
            ner_entities_json='[{"entity_id": "Mom"}, {"entity_id": "Dad"}]',
        )
        weights = ImportanceWeights()
        _, breakdown = scorer.compute_importance_score(event, weights, now_ms)
        d = breakdown.to_dict()
        assert "relationship_boost" in d
        assert "max_edge_weight" in d
        assert d["relationship_boost"] > 1.0
        assert d["max_edge_weight"] == 0.7

    @pytest.mark.asyncio
    async def test_score_still_clamped_to_one(self) -> None:
        """Even with boost, final score never exceeds 1.0."""
        now_ms = int(time.time() * 1000)
        cache = KGEdgeCache()
        cache._loaded = True
        cache._edges = {"Dad:Mom": 1.0}
        cache._edge_count = 1
        # Aggressive config
        config = KGBoostConfig(enabled=True, boost_scale=0.50, max_boost_cap=0.50)
        scorer = ImportanceScorer(
            space_id="sp_test",
            kg_boost_config=config,
            kg_edge_cache=cache,
        )
        # High-scoring event
        event = MockEvent(
            timestamp=now_ms - 1000,  # Very recent
            sentiment_score=1.0,
            affect_valence=1.0,
            affect_arousal=1.0,
            surprise_level=1.0,
            novelty="SURPRISING",
            num_participants=5,
            social_intimacy="HIGH",
            identity_relevance=1.0,
            memory_tier="landmark",
            ner_entities_json='[{"entity_id": "Mom"}, {"entity_id": "Dad"}]',
        )
        weights = ImportanceWeights()
        score, _ = scorer.compute_importance_score(event, weights, now_ms)
        assert score <= 1.0


# =============================================================================
# R1 Phase Config Tests
# =============================================================================


class TestR1ConfigKGBoost:
    """Test R1Config KG boost settings."""

    def test_default_disabled(self) -> None:
        """KG boost is disabled by default."""
        from k0.pipelines.p03.phases.r1_importance_scorer import R1Config

        config = R1Config()
        assert config.enable_kg_boost is False

    def test_boost_scale_default(self) -> None:
        """Default boost scale is 0.15."""
        from k0.pipelines.p03.phases.r1_importance_scorer import R1Config

        config = R1Config()
        assert config.kg_boost_scale == 0.15

    def test_boost_cap_default(self) -> None:
        """Default max boost cap is 0.20."""
        from k0.pipelines.p03.phases.r1_importance_scorer import R1Config

        config = R1Config()
        assert config.kg_max_boost_cap == 0.20

    def test_enable_kg_boost(self) -> None:
        """KG boost can be enabled via config."""
        from k0.pipelines.p03.phases.r1_importance_scorer import R1Config

        config = R1Config(enable_kg_boost=True, kg_boost_scale=0.20, kg_max_boost_cap=0.25)
        assert config.enable_kg_boost is True
        assert config.kg_boost_scale == 0.20
        assert config.kg_max_boost_cap == 0.25
