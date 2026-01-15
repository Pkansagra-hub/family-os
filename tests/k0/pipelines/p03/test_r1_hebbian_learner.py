"""
Tests for HebbianLearner — co-occurrence extraction and edge weight updates.

Test coverage for M4 Issues 4.1.3 (Hebbian) and 4.1.4 (Anti-Hebbian).

Spec Reference:
    - Dossier Appendix C.2.2: Hebbian Learning Algorithm
    - Dossier Appendix C.2.2.1: Anti-Hebbian Decay
    - M4_EXECUTION.md Issues 4.1.3, 4.1.4
"""

import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List

import pytest

from k0.modules.consolidation.algorithms.hebbian_learner import (
    HebbianConfig,
    HebbianLearner,
    KGEdge,
    RelationType,
    parse_ner_entities,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@dataclass
class MockEvent:
    """Mock event for testing HebbianLearner."""

    event_id: str
    importance_score: float = 0.5
    ner_entities_json: str = "[]"
    hebbian_updates: List[Dict[str, Any]] = field(default_factory=list)

    def add_hebbian_update(
        self,
        source_entity_id: str,
        target_entity_id: str,
        old_weight: float,
        new_weight: float,
        update_type: str,
    ) -> None:
        """Record a Hebbian edge update."""
        self.hebbian_updates.append(
            {
                "source_entity_id": source_entity_id,
                "target_entity_id": target_entity_id,
                "old_weight": old_weight,
                "new_weight": new_weight,
                "update_type": update_type,
            }
        )


@pytest.fixture
def default_config() -> HebbianConfig:
    """Default Hebbian configuration."""
    return HebbianConfig()


@pytest.fixture
def learner(default_config: HebbianConfig) -> HebbianLearner:
    """HebbianLearner with default configuration."""
    return HebbianLearner(config=default_config)


@pytest.fixture
def custom_learner() -> HebbianLearner:
    """HebbianLearner with custom configuration for edge case testing."""
    config = HebbianConfig(
        learning_rate=0.2,
        decay_rate=0.05,
        max_weight=0.9,
        min_weight=0.02,
        anti_learning_rate=0.2,
        prune_threshold=0.08,
    )
    return HebbianLearner(config=config)


def make_edge(
    edge_id: str = "edge-1",
    source_id: str = "actor-a",
    target_id: str = "actor-b",
    relation_type: str = "INTERACTS_WITH",
    weight: float = 0.5,
    count: int = 10,
) -> KGEdge:
    """Create a KGEdge for testing."""
    return KGEdge(
        edge_id=edge_id,
        source_id=source_id,
        target_id=target_id,
        relation_type=relation_type,
        weight=weight,
        co_occurrence_count=count,
    )


# =============================================================================
# Test HebbianConfig
# =============================================================================


class TestHebbianConfig:
    """Tests for HebbianConfig validation."""

    def test_default_config_values(self):
        """Default config has expected values from Dossier C.2.2."""
        config = HebbianConfig()
        assert config.learning_rate == 0.1
        assert config.decay_rate == 0.01
        assert config.max_weight == 1.0
        assert config.min_weight == 0.01
        assert config.anti_learning_rate == 0.15
        assert config.explicit_correction_multiplier == 1.3
        assert config.prune_threshold == 0.05

    def test_config_validation_passes(self):
        """Valid config passes validation."""
        config = HebbianConfig(learning_rate=0.5, decay_rate=0.1, max_weight=0.8, min_weight=0.05)
        config.validate()  # Should not raise

    def test_config_invalid_learning_rate_zero(self):
        """Learning rate of 0 fails validation."""
        config = HebbianConfig(learning_rate=0.0)
        with pytest.raises(ValueError, match="learning_rate"):
            config.validate()

    def test_config_invalid_learning_rate_negative(self):
        """Negative learning rate fails validation."""
        config = HebbianConfig(learning_rate=-0.1)
        with pytest.raises(ValueError, match="learning_rate"):
            config.validate()

    def test_config_invalid_min_weight_exceeds_max(self):
        """min_weight >= max_weight fails validation."""
        config = HebbianConfig(min_weight=0.9, max_weight=0.8)
        with pytest.raises(ValueError, match="min_weight"):
            config.validate()


# =============================================================================
# Test NER Entity Parsing
# =============================================================================


class TestParseNerEntities:
    """Tests for parse_ner_entities helper."""

    def test_empty_json(self):
        """Empty JSON array returns empty list."""
        assert parse_ner_entities("[]") == []

    def test_empty_string(self):
        """Empty string returns empty list."""
        assert parse_ner_entities("") == []

    def test_none_string(self):
        """None-ish input returns empty list."""
        assert parse_ner_entities(None) == []  # type: ignore

    def test_parse_person_entities(self):
        """Parse PERSON entities from NER JSON."""
        ner_json = json.dumps(
            [
                {"entity_id": "person-1", "type": "PERSON", "text": "Alice"},
                {"entity_id": "person-2", "type": "PERSON", "text": "Bob"},
            ]
        )
        entities = parse_ner_entities(ner_json)
        assert len(entities) == 2
        assert entities[0].entity_id == "person-1"
        assert entities[0].entity_type == "PERSON"
        assert entities[0].text == "Alice"
        assert entities[1].entity_id == "person-2"

    def test_parse_location_entity(self):
        """Parse LOCATION entity from NER JSON."""
        ner_json = json.dumps([{"entity_id": "loc-1", "type": "LOCATION", "text": "Home"}])
        entities = parse_ner_entities(ner_json)
        assert len(entities) == 1
        assert entities[0].entity_type == "LOCATION"

    def test_parse_mixed_entities(self):
        """Parse mixed entity types."""
        ner_json = json.dumps(
            [
                {"entity_id": "p1", "type": "PERSON", "text": "Alice"},
                {"entity_id": "l1", "type": "LOCATION", "text": "Office"},
                {"entity_id": "o1", "type": "ORG", "text": "Acme Corp"},
            ]
        )
        entities = parse_ner_entities(ner_json)
        assert len(entities) == 3
        assert [e.entity_type for e in entities] == ["PERSON", "LOCATION", "ORG"]

    def test_parse_alternative_field_names(self):
        """Handle alternative field names (id vs entity_id, entity_type vs type)."""
        ner_json = json.dumps([{"id": "alt-1", "entity_type": "person", "name": "Charlie"}])
        entities = parse_ner_entities(ner_json)
        assert len(entities) == 1
        assert entities[0].entity_id == "alt-1"
        assert entities[0].entity_type == "PERSON"
        assert entities[0].text == "Charlie"

    def test_parse_string_entities(self):
        """Handle simple string entity IDs (legacy format)."""
        ner_json = json.dumps(["entity-1", "entity-2"])
        entities = parse_ner_entities(ner_json)
        assert len(entities) == 2
        assert entities[0].entity_id == "entity-1"
        assert entities[0].entity_type == "UNKNOWN"

    def test_parse_invalid_json(self):
        """Invalid JSON returns empty list with warning."""
        entities = parse_ner_entities("not valid json")
        assert entities == []

    def test_parse_skips_missing_entity_id(self):
        """Entities without entity_id are skipped."""
        ner_json = json.dumps(
            [
                {"entity_id": "valid-1", "type": "PERSON"},
                {"type": "PERSON", "text": "No ID"},  # Missing entity_id
            ]
        )
        entities = parse_ner_entities(ner_json)
        assert len(entities) == 1
        assert entities[0].entity_id == "valid-1"


# =============================================================================
# Test Co-occurrence Extraction (Issue 4.1.3)
# =============================================================================


class TestExtractCooccurrences:
    """Tests for extract_cooccurrences method."""

    def test_empty_event_no_cooccurrences(self, learner: HebbianLearner):
        """Event with no entities has no co-occurrences."""
        event = MockEvent(event_id="e1", importance_score=0.5)
        cooccurrences = learner.extract_cooccurrences(event)
        assert cooccurrences == []

    def test_single_actor_no_cooccurrences(self, learner: HebbianLearner):
        """Single actor has no actor-actor co-occurrences."""
        ner_json = json.dumps([{"entity_id": "p1", "type": "PERSON", "text": "Alice"}])
        event = MockEvent(event_id="e1", ner_entities_json=ner_json)
        cooccurrences = learner.extract_cooccurrences(event)
        # No actor-actor pairs, no location, no topics
        assert len(cooccurrences) == 0

    def test_two_actors_one_pair(self, learner: HebbianLearner):
        """Two actors yield one INTERACTS_WITH pair."""
        ner_json = json.dumps(
            [
                {"entity_id": "p1", "type": "PERSON"},
                {"entity_id": "p2", "type": "PERSON"},
            ]
        )
        event = MockEvent(event_id="e1", importance_score=0.7, ner_entities_json=ner_json)
        cooccurrences = learner.extract_cooccurrences(event)

        assert len(cooccurrences) == 1
        assert cooccurrences[0].source_id == "p1"
        assert cooccurrences[0].target_id == "p2"
        assert cooccurrences[0].relation_type == RelationType.INTERACTS_WITH
        assert cooccurrences[0].event_importance == 0.7

    def test_three_actors_three_pairs(self, learner: HebbianLearner):
        """Three actors yield 3 pairs (combinations C(3,2) = 3)."""
        ner_json = json.dumps(
            [
                {"entity_id": "p1", "type": "PERSON"},
                {"entity_id": "p2", "type": "PERSON"},
                {"entity_id": "p3", "type": "PERSON"},
            ]
        )
        event = MockEvent(event_id="e1", ner_entities_json=ner_json)
        cooccurrences = learner.extract_cooccurrences(event)

        # Filter to INTERACTS_WITH only
        interactions = [c for c in cooccurrences if c.relation_type == RelationType.INTERACTS_WITH]
        assert len(interactions) == 3

        pairs = {(c.source_id, c.target_id) for c in interactions}
        assert pairs == {("p1", "p2"), ("p1", "p3"), ("p2", "p3")}

    def test_actor_location_frequents(self, learner: HebbianLearner):
        """Actor + Location yields FREQUENTS pair."""
        ner_json = json.dumps(
            [
                {"entity_id": "p1", "type": "PERSON"},
                {"entity_id": "loc1", "type": "LOCATION"},
            ]
        )
        event = MockEvent(event_id="e1", ner_entities_json=ner_json)
        cooccurrences = learner.extract_cooccurrences(event)

        assert len(cooccurrences) == 1
        assert cooccurrences[0].relation_type == RelationType.FREQUENTS
        assert cooccurrences[0].source_id == "p1"
        assert cooccurrences[0].target_id == "loc1"

    def test_actor_topic_discusses(self, learner: HebbianLearner):
        """Actor + Topic (ORG) yields DISCUSSES pair."""
        ner_json = json.dumps(
            [
                {"entity_id": "p1", "type": "PERSON"},
                {"entity_id": "org1", "type": "ORG"},
            ]
        )
        event = MockEvent(event_id="e1", ner_entities_json=ner_json)
        cooccurrences = learner.extract_cooccurrences(event)

        assert len(cooccurrences) == 1
        assert cooccurrences[0].relation_type == RelationType.DISCUSSES
        assert cooccurrences[0].source_id == "p1"
        assert cooccurrences[0].target_id == "org1"

    def test_complex_event_all_types(self, learner: HebbianLearner):
        """Complex event with actors, location, and topics."""
        ner_json = json.dumps(
            [
                {"entity_id": "alice", "type": "PERSON"},
                {"entity_id": "bob", "type": "PERSON"},
                {"entity_id": "office", "type": "LOCATION"},
                {"entity_id": "project", "type": "ORG"},
            ]
        )
        event = MockEvent(event_id="e1", importance_score=0.8, ner_entities_json=ner_json)
        cooccurrences = learner.extract_cooccurrences(event)

        # Expected: 1 INTERACTS_WITH + 2 FREQUENTS + 2 DISCUSSES = 5
        assert len(cooccurrences) == 5

        by_type = {}
        for c in cooccurrences:
            by_type.setdefault(c.relation_type, []).append(c)

        assert len(by_type[RelationType.INTERACTS_WITH]) == 1
        assert len(by_type[RelationType.FREQUENTS]) == 2
        assert len(by_type[RelationType.DISCUSSES]) == 2

    def test_explicit_actor_ids_override(self, learner: HebbianLearner):
        """Explicit actor_ids parameter overrides NER extraction."""
        ner_json = json.dumps(
            [
                {"entity_id": "loc1", "type": "LOCATION"},
            ]
        )
        event = MockEvent(event_id="e1", ner_entities_json=ner_json)

        # Provide explicit actor IDs
        cooccurrences = learner.extract_cooccurrences(event, actor_ids=["explicit-a", "explicit-b"])

        # 1 INTERACTS_WITH + 2 FREQUENTS
        assert len(cooccurrences) == 3

        interactions = [c for c in cooccurrences if c.relation_type == RelationType.INTERACTS_WITH]
        assert len(interactions) == 1
        assert interactions[0].source_id == "explicit-a"
        assert interactions[0].target_id == "explicit-b"

    def test_explicit_location_override(self, learner: HebbianLearner):
        """Explicit location_entity_id parameter adds FREQUENTS pairs."""
        ner_json = json.dumps([{"entity_id": "p1", "type": "PERSON"}])
        event = MockEvent(event_id="e1", ner_entities_json=ner_json)

        cooccurrences = learner.extract_cooccurrences(event, location_entity_id="explicit-loc")

        assert len(cooccurrences) == 1
        assert cooccurrences[0].relation_type == RelationType.FREQUENTS
        assert cooccurrences[0].target_id == "explicit-loc"


# =============================================================================
# Test Edge Weight Updates (Issue 4.1.3)
# =============================================================================


class TestUpdateEdgeWeight:
    """Tests for update_edge_weight method."""

    def test_basic_update(self, learner: HebbianLearner):
        """Basic weight update increases weight."""
        new_weight, new_count = learner.update_edge_weight(
            current_weight=0.5,
            current_count=10,
            event_importance=0.8,
        )

        # delta = 0.1 * (1.0 - 0.5) * 0.8 = 0.04
        assert new_weight == pytest.approx(0.54, rel=0.01)
        assert new_count == 11

    def test_soft_saturation_high_weight(self, learner: HebbianLearner):
        """High weights approach max asymptotically (soft saturation)."""
        new_weight, _ = learner.update_edge_weight(
            current_weight=0.9,
            current_count=100,
            event_importance=1.0,
        )

        # delta = 0.1 * (1.0 - 0.9) * 1.0 = 0.01
        # Expected: 0.91
        assert new_weight == pytest.approx(0.91, rel=0.01)
        assert new_weight <= 1.0

    def test_weight_capped_at_max(self, learner: HebbianLearner):
        """Weight never exceeds max_weight."""
        new_weight, _ = learner.update_edge_weight(
            current_weight=0.99,
            current_count=1000,
            event_importance=1.0,
        )

        assert new_weight <= 1.0

    def test_low_importance_small_delta(self, learner: HebbianLearner):
        """Low importance yields small delta."""
        new_weight, _ = learner.update_edge_weight(
            current_weight=0.5,
            current_count=10,
            event_importance=0.1,
        )

        # delta = 0.1 * 0.5 * 0.1 = 0.005
        assert new_weight == pytest.approx(0.505, rel=0.01)

    def test_high_importance_large_delta(self, learner: HebbianLearner):
        """High importance yields larger delta."""
        new_weight, _ = learner.update_edge_weight(
            current_weight=0.5,
            current_count=10,
            event_importance=0.9,
        )

        # delta = 0.1 * 0.5 * 0.9 = 0.045
        assert new_weight == pytest.approx(0.545, rel=0.01)

    def test_zero_weight_starts_fresh(self, learner: HebbianLearner):
        """Zero weight gets initial boost."""
        new_weight, new_count = learner.update_edge_weight(
            current_weight=0.0,
            current_count=0,
            event_importance=0.8,
        )

        # delta = 0.1 * 1.0 * 0.8 = 0.08
        assert new_weight == pytest.approx(0.08, rel=0.01)
        assert new_count == 1

    def test_custom_learning_rate(self, custom_learner: HebbianLearner):
        """Custom learning rate affects delta."""
        new_weight, _ = custom_learner.update_edge_weight(
            current_weight=0.5,
            current_count=10,
            event_importance=1.0,
        )

        # custom lr=0.2, delta = 0.2 * (0.9 - 0.5) * 1.0 = 0.08
        assert new_weight == pytest.approx(0.58, rel=0.01)

    def test_compute_initial_weight(self, learner: HebbianLearner):
        """Initial weight for new edge."""
        initial = learner.compute_initial_weight(avg_importance=0.7)

        # 0.1 * 0.7 = 0.07
        assert initial == pytest.approx(0.07, rel=0.01)


# =============================================================================
# Test Decay (Issue 4.1.3)
# =============================================================================


class TestApplyDecay:
    """Tests for apply_decay method."""

    def test_no_decay_zero_days(self, learner: HebbianLearner):
        """Zero days means no decay."""
        edges = [make_edge(weight=0.5)]
        surviving, pruned = learner.apply_decay(edges, days_since_update=0)

        assert len(surviving) == 1
        assert surviving[0].weight == 0.5
        assert pruned == []

    def test_decay_preserves_strong_edges(self, learner: HebbianLearner):
        """Strong edges survive decay."""
        edges = [make_edge(weight=0.8)]
        surviving, pruned = learner.apply_decay(edges, days_since_update=30)

        # decay_factor = exp(-0.01 * 30) ≈ 0.74
        # new_weight = 0.8 * 0.74 ≈ 0.59 > 0.01
        assert len(surviving) == 1
        assert surviving[0].weight > 0.01
        assert pruned == []

    def test_decay_prunes_weak_edges(self, learner: HebbianLearner):
        """Weak edges are pruned after decay."""
        edges = [make_edge(edge_id="weak-edge", weight=0.05)]
        surviving, pruned = learner.apply_decay(edges, days_since_update=100)

        # decay_factor = exp(-0.01 * 100) ≈ 0.37
        # new_weight = 0.05 * 0.37 ≈ 0.018 > 0.01, but let's check
        # Actually 0.0185 > 0.01, so it survives with default config
        # Need to test with higher decay or lower weight

        edges2 = [make_edge(edge_id="very-weak", weight=0.02)]
        surviving2, pruned2 = learner.apply_decay(edges2, days_since_update=100)
        # 0.02 * 0.37 ≈ 0.007 < 0.01 → pruned

        assert len(surviving2) == 0
        assert "very-weak" in pruned2

    def test_decay_formula_exponential(self, learner: HebbianLearner):
        """Decay follows exponential formula."""
        edges = [make_edge(weight=0.5)]
        surviving, _ = learner.apply_decay(edges, days_since_update=10)

        # decay_factor = exp(-0.01 * 10) = exp(-0.1) ≈ 0.9048
        expected = 0.5 * math.exp(-0.01 * 10)
        assert surviving[0].weight == pytest.approx(expected, rel=0.01)

    def test_decay_multiple_edges(self, learner: HebbianLearner):
        """Multiple edges decay independently."""
        edges = [
            make_edge(edge_id="strong", weight=0.9),
            make_edge(edge_id="medium", weight=0.3),
            make_edge(edge_id="weak", weight=0.015),
        ]
        surviving, pruned = learner.apply_decay(edges, days_since_update=50)

        # decay_factor = exp(-0.5) ≈ 0.606
        # strong: 0.9 * 0.606 ≈ 0.55 > 0.01 ✓
        # medium: 0.3 * 0.606 ≈ 0.18 > 0.01 ✓
        # weak: 0.015 * 0.606 ≈ 0.009 < 0.01 ✗

        assert len(surviving) == 2
        assert len(pruned) == 1
        assert "weak" in pruned


# =============================================================================
# Test Anti-Hebbian Decay (Issue 4.1.4)
# =============================================================================


class TestApplyAntiDecay:
    """Tests for apply_anti_decay method."""

    def test_entity_merge_rejected_penalty(self, learner: HebbianLearner):
        """ENTITY_MERGE_REJECTED applies ~20% penalty."""
        edge = make_edge(weight=0.5)
        new_weight, should_prune = learner.apply_anti_decay(
            edge,
            signal_type="ENTITY_MERGE_REJECTED",
            confidence=1.0,
        )

        # delta = -0.15 * 0.5 * 1.0 * 0.2 * 1.0 = -0.015
        # new_weight = 0.5 - 0.015 = 0.485
        assert new_weight == pytest.approx(0.485, rel=0.01)
        assert not should_prune

    def test_association_wrong_stronger_penalty(self, learner: HebbianLearner):
        """ASSOCIATION_WRONG applies stronger penalty (0.3)."""
        edge = make_edge(weight=0.5)
        new_weight, _ = learner.apply_anti_decay(
            edge,
            signal_type="ASSOCIATION_WRONG",
            confidence=1.0,
        )

        # delta = -0.15 * 0.5 * 1.0 * 0.3 = -0.0225
        assert new_weight == pytest.approx(0.4775, rel=0.01)

    def test_mutual_exclusion_strongest_penalty(self, learner: HebbianLearner):
        """MUTUAL_EXCLUSION applies strongest penalty (0.4)."""
        edge = make_edge(weight=0.5)
        new_weight, _ = learner.apply_anti_decay(
            edge,
            signal_type="MUTUAL_EXCLUSION",
            confidence=1.0,
        )

        # delta = -0.15 * 0.5 * 1.0 * 0.4 = -0.03
        assert new_weight == pytest.approx(0.47, rel=0.01)

    def test_contradiction_moderate_penalty(self, learner: HebbianLearner):
        """CONTRADICTION applies moderate penalty (0.15)."""
        edge = make_edge(weight=0.5)
        new_weight, _ = learner.apply_anti_decay(
            edge,
            signal_type="CONTRADICTION",
            confidence=1.0,
        )

        # delta = -0.15 * 0.5 * 1.0 * 0.15 = -0.01125
        assert new_weight == pytest.approx(0.48875, rel=0.01)

    def test_explicit_correction_multiplier(self, learner: HebbianLearner):
        """Explicit corrections apply 1.3× multiplier."""
        edge = make_edge(weight=0.5)

        # Without explicit
        weight_implicit, _ = learner.apply_anti_decay(
            edge, signal_type="ASSOCIATION_WRONG", confidence=1.0, is_explicit_correction=False
        )

        edge.weight = 0.5  # Reset

        # With explicit
        weight_explicit, _ = learner.apply_anti_decay(
            edge, signal_type="ASSOCIATION_WRONG", confidence=1.0, is_explicit_correction=True
        )

        # Explicit should have larger reduction
        assert weight_explicit < weight_implicit
        # Ratio should be ~1.3
        delta_implicit = 0.5 - weight_implicit
        delta_explicit = 0.5 - weight_explicit
        assert delta_explicit / delta_implicit == pytest.approx(1.3, rel=0.01)

    def test_prune_threshold_low_weight(self, learner: HebbianLearner):
        """Edge below prune threshold (0.05) is marked for archive."""
        edge = make_edge(weight=0.06)
        new_weight, should_prune = learner.apply_anti_decay(
            edge,
            signal_type="MUTUAL_EXCLUSION",  # 0.4 penalty
            confidence=1.0,
        )

        # delta = -0.15 * 0.06 * 1.0 * 0.4 = -0.0036
        # new_weight = 0.0564 → still > 0.05, not pruned

        # Try with lower weight
        edge2 = make_edge(weight=0.04)
        new_weight2, should_prune2 = learner.apply_anti_decay(
            edge2,
            signal_type="MUTUAL_EXCLUSION",
            confidence=1.0,
        )
        # 0.04 - 0.0024 = 0.0376 < 0.05 → should prune
        assert should_prune2 is True

    def test_weight_clamped_to_zero(self, learner: HebbianLearner):
        """Weight never goes negative."""
        edge = make_edge(weight=0.01)
        new_weight, should_prune = learner.apply_anti_decay(
            edge,
            signal_type="MUTUAL_EXCLUSION",
            confidence=1.0,
            is_explicit_correction=True,
        )

        assert new_weight >= 0.0
        assert should_prune is True

    def test_confidence_scales_decay(self, learner: HebbianLearner):
        """Lower confidence reduces decay magnitude."""
        edge = make_edge(weight=0.5)

        # Full confidence
        weight_full, _ = learner.apply_anti_decay(
            edge, signal_type="ASSOCIATION_WRONG", confidence=1.0
        )

        edge.weight = 0.5  # Reset

        # Half confidence
        weight_half, _ = learner.apply_anti_decay(
            edge, signal_type="ASSOCIATION_WRONG", confidence=0.5
        )

        # Half confidence = half decay
        delta_full = 0.5 - weight_full
        delta_half = 0.5 - weight_half
        assert delta_half / delta_full == pytest.approx(0.5, rel=0.01)

    def test_unknown_signal_type_default_penalty(self, learner: HebbianLearner):
        """Unknown signal type uses default penalty (0.1)."""
        edge = make_edge(weight=0.5)
        new_weight, _ = learner.apply_anti_decay(
            edge,
            signal_type="UNKNOWN_SIGNAL",
            confidence=1.0,
        )

        # delta = -0.15 * 0.5 * 1.0 * 0.1 = -0.0075
        assert new_weight == pytest.approx(0.4925, rel=0.01)

    def test_get_penalty_for_signal(self, learner: HebbianLearner):
        """Test penalty lookup helper."""
        assert learner.get_penalty_for_signal("ENTITY_MERGE_REJECTED") == 0.2
        assert learner.get_penalty_for_signal("ASSOCIATION_WRONG") == 0.3
        assert learner.get_penalty_for_signal("MUTUAL_EXCLUSION") == 0.4
        assert learner.get_penalty_for_signal("CONTRADICTION") == 0.15
        assert learner.get_penalty_for_signal("UNKNOWN") == 0.1


# =============================================================================
# Test Batch Processing (Issue 4.1.3)
# =============================================================================


class TestProcessBatch:
    """Tests for process_batch method."""

    def test_empty_batch(self, learner: HebbianLearner):
        """Empty batch returns empty updates."""
        edge_updates = learner.process_batch([])
        assert edge_updates == {}

    def test_single_event_single_pair(self, learner: HebbianLearner):
        """Single event with two actors yields one edge update."""
        ner_json = json.dumps(
            [
                {"entity_id": "alice", "type": "PERSON"},
                {"entity_id": "bob", "type": "PERSON"},
            ]
        )
        event = MockEvent(event_id="e1", importance_score=0.7, ner_entities_json=ner_json)

        edge_updates = learner.process_batch([event])

        assert len(edge_updates) == 1
        key = ("alice", "bob", "INTERACTS_WITH")
        assert key in edge_updates
        assert edge_updates[key].cooccurrence_count == 1
        assert edge_updates[key].importance_sum == 0.7

    def test_multiple_events_aggregates_counts(self, learner: HebbianLearner):
        """Multiple events with same pair aggregate co-occurrences."""
        ner_json = json.dumps(
            [
                {"entity_id": "alice", "type": "PERSON"},
                {"entity_id": "bob", "type": "PERSON"},
            ]
        )

        events = [
            MockEvent(event_id="e1", importance_score=0.5, ner_entities_json=ner_json),
            MockEvent(event_id="e2", importance_score=0.7, ner_entities_json=ner_json),
            MockEvent(event_id="e3", importance_score=0.9, ner_entities_json=ner_json),
        ]

        edge_updates = learner.process_batch(events)

        key = ("alice", "bob", "INTERACTS_WITH")
        assert edge_updates[key].cooccurrence_count == 3
        assert edge_updates[key].importance_sum == pytest.approx(2.1, rel=0.01)
        assert edge_updates[key].avg_importance == pytest.approx(0.7, rel=0.01)

    def test_batch_updates_event_state(self, learner: HebbianLearner):
        """Processing batch records updates in event state."""
        ner_json = json.dumps(
            [
                {"entity_id": "alice", "type": "PERSON"},
                {"entity_id": "bob", "type": "PERSON"},
            ]
        )
        event = MockEvent(event_id="e1", importance_score=0.7, ner_entities_json=ner_json)

        learner.process_batch([event])

        assert len(event.hebbian_updates) == 1
        update = event.hebbian_updates[0]
        assert update["source_entity_id"] == "alice"
        assert update["target_entity_id"] == "bob"
        assert update["update_type"] == "INTERACTS_WITH"

    def test_batch_with_actor_ids_map(self, learner: HebbianLearner):
        """Explicit actor_ids_map overrides NER extraction."""
        event = MockEvent(event_id="e1", importance_score=0.8, ner_entities_json="[]")

        actor_ids_map = {"e1": ["actor-x", "actor-y"]}
        edge_updates = learner.process_batch([event], actor_ids_map=actor_ids_map)

        key = ("actor-x", "actor-y", "INTERACTS_WITH")
        assert key in edge_updates
        assert edge_updates[key].cooccurrence_count == 1

    def test_batch_with_location_ids_map(self, learner: HebbianLearner):
        """Explicit location_ids_map adds FREQUENTS pairs."""
        ner_json = json.dumps([{"entity_id": "alice", "type": "PERSON"}])
        event = MockEvent(event_id="e1", importance_score=0.6, ner_entities_json=ner_json)

        location_ids_map = {"e1": "location-z"}
        edge_updates = learner.process_batch([event], location_ids_map=location_ids_map)

        key = ("alice", "location-z", "FREQUENTS")
        assert key in edge_updates

    def test_new_edge_initial_weight_calculation(self, learner: HebbianLearner):
        """New edge initial weight = learning_rate × avg_importance."""
        ner_json = json.dumps(
            [
                {"entity_id": "alice", "type": "PERSON"},
                {"entity_id": "bob", "type": "PERSON"},
            ]
        )
        events = [
            MockEvent(event_id="e1", importance_score=0.6, ner_entities_json=ner_json),
            MockEvent(event_id="e2", importance_score=0.8, ner_entities_json=ner_json),
        ]

        edge_updates = learner.process_batch(events)
        key = ("alice", "bob", "INTERACTS_WITH")

        # avg_importance = (0.6 + 0.8) / 2 = 0.7
        # initial_weight = 0.1 * 0.7 = 0.07
        initial_weight = learner.compute_initial_weight(edge_updates[key].avg_importance)
        assert initial_weight == pytest.approx(0.07, rel=0.01)


# =============================================================================
# Test Utility Methods
# =============================================================================


class TestUtilityMethods:
    """Tests for utility methods."""

    def test_normalize_weight(self, learner: HebbianLearner):
        """Weight normalization clamps to [0, 1]."""
        assert learner.normalize_weight(-0.5) == 0.0
        assert learner.normalize_weight(0.5) == 0.5
        assert learner.normalize_weight(1.5) == 1.0

    def test_weight_interpretation(self, learner: HebbianLearner):
        """Weight interpretation returns correct category."""
        assert learner.weight_interpretation(0.95) == "Very Strong"
        assert learner.weight_interpretation(0.80) == "Very Strong"
        assert learner.weight_interpretation(0.65) == "Strong"
        assert learner.weight_interpretation(0.50) == "Strong"
        assert learner.weight_interpretation(0.35) == "Moderate"
        assert learner.weight_interpretation(0.20) == "Moderate"
        assert learner.weight_interpretation(0.10) == "Weak"
        assert learner.weight_interpretation(0.01) == "Weak"
        assert learner.weight_interpretation(0.005) == "Negligible"


# =============================================================================
# Integration Test: Complete Hebbian Workflow
# =============================================================================


class TestHebbianWorkflow:
    """End-to-end workflow tests."""

    def test_full_hebbian_cycle(self, learner: HebbianLearner):
        """Complete cycle: extract → update → decay → anti-decay."""
        # 1. Create events with co-occurring actors
        ner_json = json.dumps(
            [
                {"entity_id": "alice", "type": "PERSON"},
                {"entity_id": "bob", "type": "PERSON"},
                {"entity_id": "office", "type": "LOCATION"},
            ]
        )

        events = [
            MockEvent(event_id="e1", importance_score=0.6, ner_entities_json=ner_json),
            MockEvent(event_id="e2", importance_score=0.8, ner_entities_json=ner_json),
            MockEvent(event_id="e3", importance_score=0.7, ner_entities_json=ner_json),
        ]

        # 2. Process batch to get edge updates
        edge_updates = learner.process_batch(events)

        # Should have: 1 INTERACTS_WITH + 2 FREQUENTS = 3 unique edges
        assert len(edge_updates) == 3

        # 3. Calculate new weight for alice-bob edge
        alice_bob_key = ("alice", "bob", "INTERACTS_WITH")
        update = edge_updates[alice_bob_key]

        # Start with no existing edge
        initial_weight = learner.compute_initial_weight(update.avg_importance)
        assert initial_weight > 0

        # Apply cumulative updates (simulate 3 co-occurrences)
        current_weight = 0.0
        current_count = 0
        for _ in range(update.cooccurrence_count):
            current_weight, current_count = learner.update_edge_weight(
                current_weight, current_count, update.avg_importance
            )

        assert current_weight > initial_weight
        assert current_count == 3

        # 4. Apply time decay (30 days)
        edge = make_edge(edge_id="alice-bob", weight=current_weight, count=current_count)
        surviving, pruned = learner.apply_decay([edge], days_since_update=30)

        assert len(surviving) == 1
        assert surviving[0].weight < current_weight
        assert pruned == []

        # 5. Apply anti-Hebbian decay (user correction)
        new_weight, should_prune = learner.apply_anti_decay(
            surviving[0],
            signal_type="ASSOCIATION_WRONG",
            confidence=0.9,
            is_explicit_correction=True,
        )

        assert new_weight < surviving[0].weight
        # Should still be above prune threshold
        assert not should_prune

    def test_hebbian_with_anti_hebbian_until_prune(self, learner: HebbianLearner):
        """Repeated anti-Hebbian eventually prunes edge."""
        edge = make_edge(weight=0.3)

        # Apply anti-decay repeatedly
        iterations = 0
        while edge.weight >= learner.config.prune_threshold and iterations < 50:
            new_weight, should_prune = learner.apply_anti_decay(
                edge,
                signal_type="ASSOCIATION_WRONG",
                confidence=1.0,
            )
            edge.weight = new_weight
            iterations += 1

            if should_prune:
                break

        assert edge.weight < learner.config.prune_threshold
        assert iterations > 1  # Should take multiple iterations
