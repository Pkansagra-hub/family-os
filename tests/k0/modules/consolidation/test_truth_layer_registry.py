"""Tests for TruthLayerRegistry (M9.1 D10).

Validates the Python registry module: loading, querying, merge rules,
and write ordering.
"""

from __future__ import annotations

import pytest

from k0.modules.consolidation.truth_layer_registry import MergeRule, TruthLayerRegistry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def registry() -> TruthLayerRegistry:
    """Load the registry from the real contracts directory."""
    return TruthLayerRegistry.from_contracts()


# ---------------------------------------------------------------------------
# Registry Loading
# ---------------------------------------------------------------------------


class TestRegistryLoading:

    def test_loads_all_seven_layers(self, registry: TruthLayerRegistry) -> None:
        assert len(registry) == 7

    def test_truth_layer_names(self, registry: TruthLayerRegistry) -> None:
        expected = frozenset(
            {
                "st_epi",
                "st_sem",
                "st_procedural",
                "st_social",
                "st_prospective",
                "st_kg_dom",
                "st_kg_edges",
            }
        )
        assert registry.truth_layer_names() == expected

    def test_contains(self, registry: TruthLayerRegistry) -> None:
        assert "st_epi" in registry
        assert "st_vec" not in registry
        assert "st_hipp_events" not in registry

    def test_get_unknown_raises_key_error(self, registry: TruthLayerRegistry) -> None:
        with pytest.raises(KeyError, match="Unknown truth layer"):
            registry.get("st_nonexistent")

    def test_repr(self, registry: TruthLayerRegistry) -> None:
        r = repr(registry)
        assert "TruthLayerRegistry" in r
        assert "st_epi" in r


# ---------------------------------------------------------------------------
# Write Ordering
# ---------------------------------------------------------------------------


class TestWriteOrder:

    def test_all_layers_sorted_by_write_order(self, registry: TruthLayerRegistry) -> None:
        layers = registry.all_layers()
        orders = [l.write_order for l in layers]
        assert orders == sorted(orders)

    def test_write_order_values(self, registry: TruthLayerRegistry) -> None:
        """Verify write order: kg_dom(2) < kg_edges(3) < epi(4) < sem(5) < ..."""
        expected = {
            "st_kg_dom": 2,
            "st_kg_edges": 3,
            "st_epi": 4,
            "st_sem": 5,
            "st_procedural": 6,
            "st_social": 7,
            "st_prospective": 8,
        }
        for name, order in expected.items():
            assert registry.get(name).write_order == order, f"{name} write_order"


# ---------------------------------------------------------------------------
# Per-Layer Metadata
# ---------------------------------------------------------------------------


class TestLayerMetadata:

    @pytest.mark.parametrize(
        "layer, pk",
        [
            ("st_epi", "episode_id"),
            ("st_sem", "pattern_id"),
            ("st_procedural", "routine_id"),
            ("st_social", "relationship_id"),
            ("st_prospective", "intention_id"),
            ("st_kg_dom", "entity_id"),
            ("st_kg_edges", "edge_id"),
        ],
    )
    def test_pk_columns(self, registry: TruthLayerRegistry, layer: str, pk: str) -> None:
        assert registry.get(layer).pk_column == pk

    @pytest.mark.parametrize(
        "layer, expected_lambda",
        [
            ("st_epi", 0.005),
            ("st_sem", 0.003),
            ("st_procedural", 0.010),
            ("st_social", 0.002),
            ("st_prospective", 0.020),
            ("st_kg_dom", 0.001),
            ("st_kg_edges", 0.008),
        ],
    )
    def test_decay_lambdas(
        self,
        registry: TruthLayerRegistry,
        layer: str,
        expected_lambda: float,
    ) -> None:
        assert registry.get(layer).decay_lambda == pytest.approx(expected_lambda)

    def test_version_column_is_version(self, registry: TruthLayerRegistry) -> None:
        for spec in registry.all_layers():
            assert spec.version_column == "version", f"{spec.layer_name}"

    def test_all_have_archival_status(self, registry: TruthLayerRegistry) -> None:
        for spec in registry.all_layers():
            assert spec.archival_status_column == "archival_status"
            assert spec.active_status_value == "ACTIVE"

    def test_epi_temporal(self, registry: TruthLayerRegistry) -> None:
        t = registry.get("st_epi").temporal
        assert t.start == "start_time_utc"
        assert t.end == "end_time_utc"
        assert t.last_observed == "last_observed_at"

    def test_social_temporal(self, registry: TruthLayerRegistry) -> None:
        t = registry.get("st_social").temporal
        assert t.last_observed == "last_interaction_at"
        assert t.first_observed == "first_interaction_at"

    def test_confidence_boost_strategies(self, registry: TruthLayerRegistry) -> None:
        assert registry.get("st_epi").confidence_boost_strategy == "none"
        assert registry.get("st_sem").confidence_boost_strategy == "additive_0.05"
        assert registry.get("st_procedural").confidence_boost_strategy == "multiplicative_1.1"
        assert registry.get("st_prospective").confidence_boost_strategy == "coalesce"


# ---------------------------------------------------------------------------
# Merge Rules
# ---------------------------------------------------------------------------


class TestMergeRules:

    def test_merge_rules_for_returns_dict(self, registry: TruthLayerRegistry) -> None:
        rules = registry.merge_rules_for("st_epi")
        assert isinstance(rules, dict)
        assert rules["episode_id"] == MergeRule.IMMUTABLE
        assert rules["version"] == MergeRule.COUNTER
        assert rules["source_events_json"] == MergeRule.APPENDABLE_DISTINCT

    def test_kg_edges_pg_array_concat(self, registry: TruthLayerRegistry) -> None:
        rules = registry.merge_rules_for("st_kg_edges")
        assert rules["evidence_event_ids"] == MergeRule.PG_ARRAY_CONCAT
        assert rules["evidence_episode_ids"] == MergeRule.PG_ARRAY_CONCAT

    def test_social_ema(self, registry: TruthLayerRegistry) -> None:
        spec = registry.get("st_social")
        avg = spec.columns["avg_sentiment"]
        assert avg.merge == MergeRule.EMA
        assert avg.ema_alpha == pytest.approx(0.1)

    def test_social_trend(self, registry: TruthLayerRegistry) -> None:
        spec = registry.get("st_social")
        trend = spec.columns["emotional_valence_trend"]
        assert trend.merge == MergeRule.TREND
        assert trend.trend_alpha == pytest.approx(0.3)

    def test_social_appendable_capped(self, registry: TruthLayerRegistry) -> None:
        spec = registry.get("st_social")
        traj = spec.columns["sentiment_trajectory_json"]
        assert traj.merge == MergeRule.APPENDABLE_CAPPED
        assert traj.cap == 20

    def test_kg_dom_shallow_merge(self, registry: TruthLayerRegistry) -> None:
        rules = registry.merge_rules_for("st_kg_dom")
        assert rules["attributes_json"] == MergeRule.SHALLOW_MERGE

    def test_social_additive_merge(self, registry: TruthLayerRegistry) -> None:
        rules = registry.merge_rules_for("st_social")
        assert rules["emotions_json"] == MergeRule.ADDITIVE_MERGE

    def test_procedural_appendable_all(self, registry: TruthLayerRegistry) -> None:
        rules = registry.merge_rules_for("st_procedural")
        assert rules["action_sequence_json"] == MergeRule.APPENDABLE_ALL

    def test_epi_derived(self, registry: TruthLayerRegistry) -> None:
        rules = registry.merge_rules_for("st_epi")
        assert rules["duration_minutes"] == MergeRule.DERIVED

    def test_epi_temporal_min_max(self, registry: TruthLayerRegistry) -> None:
        rules = registry.merge_rules_for("st_epi")
        assert rules["start_time_utc"] == MergeRule.TEMPORAL_MIN
        assert rules["end_time_utc"] == MergeRule.TEMPORAL_MAX


# ---------------------------------------------------------------------------
# Appendable Columns
# ---------------------------------------------------------------------------


class TestAppendableColumns:

    def test_epi_appendable(self, registry: TruthLayerRegistry) -> None:
        cols = registry.appendable_columns("st_epi")
        assert "source_events_json" in cols
        assert "participants_json" in cols
        assert "source_texts_json" in cols

    def test_procedural_appendable_includes_all(self, registry: TruthLayerRegistry) -> None:
        cols = registry.appendable_columns("st_procedural")
        assert "action_sequence_json" in cols
        assert "source_episodes_json" in cols
        assert "source_texts_json" in cols

    def test_social_appendable_capped(self, registry: TruthLayerRegistry) -> None:
        cols = registry.appendable_columns("st_social")
        assert "sentiment_trajectory_json" in cols

    def test_kg_edges_no_appendable(self, registry: TruthLayerRegistry) -> None:
        cols = registry.appendable_columns("st_kg_edges")
        # st_kg_edges uses pg_array_concat and shallow_merge, not appendable
        # source_episodes_json is appendable_all
        assert "source_episodes_json" in cols


# ---------------------------------------------------------------------------
# Column Counts
# ---------------------------------------------------------------------------


class TestColumnCounts:

    @pytest.mark.parametrize(
        "layer, expected_count",
        [
            ("st_epi", 52),
            ("st_sem", 31),
            ("st_procedural", 32),
            ("st_social", 42),
            ("st_prospective", 26),
            ("st_kg_dom", 30),
            ("st_kg_edges", 31),
        ],
    )
    def test_column_counts(
        self,
        registry: TruthLayerRegistry,
        layer: str,
        expected_count: int,
    ) -> None:
        spec = registry.get(layer)
        assert len(spec.columns) == expected_count, (
            f"{layer}: expected {expected_count} columns, " f"got {len(spec.columns)}"
        )


# ---------------------------------------------------------------------------
# Identity Columns
# ---------------------------------------------------------------------------


class TestIdentityColumns:

    def test_epi_identity(self, registry: TruthLayerRegistry) -> None:
        spec = registry.get("st_epi")
        assert spec.identity_columns == ("narrative_thread_id",)

    def test_sem_identity(self, registry: TruthLayerRegistry) -> None:
        spec = registry.get("st_sem")
        assert spec.identity_columns == ("pattern_type",)

    def test_procedural_identity(self, registry: TruthLayerRegistry) -> None:
        spec = registry.get("st_procedural")
        assert spec.identity_columns == ("routine_name",)

    def test_social_identity(self, registry: TruthLayerRegistry) -> None:
        spec = registry.get("st_social")
        assert spec.identity_columns == ("actor_a_id", "actor_b_id")

    def test_prospective_identity(self, registry: TruthLayerRegistry) -> None:
        spec = registry.get("st_prospective")
        assert spec.identity_columns == ()

    def test_kg_dom_identity(self, registry: TruthLayerRegistry) -> None:
        spec = registry.get("st_kg_dom")
        assert spec.identity_columns == ("entity_type", "canonical_name")

    def test_kg_edges_identity(self, registry: TruthLayerRegistry) -> None:
        spec = registry.get("st_kg_edges")
        assert spec.identity_columns == (
            "source_entity_id",
            "target_entity_id",
            "relation_type",
        )


# ---------------------------------------------------------------------------
# MergeRule Enum
# ---------------------------------------------------------------------------


class TestMergeRuleEnum:

    def test_has_sixteen_members(self) -> None:
        assert len(MergeRule) == 16

    def test_all_values_are_lowercase(self) -> None:
        for rule in MergeRule:
            assert rule.value == rule.value.lower()

    def test_round_trip(self) -> None:
        for rule in MergeRule:
            assert MergeRule(rule.value) is rule
