"""Per-merge-rule tests for MergeEngine (M9.5).

Covers validation criteria V3-V11, V24 from the M9.5 spec.
Each of the 16 MergeRule values gets at least one test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from k0.modules.consolidation.reconciliation.merge_engine import MergeEngine
from k0.modules.consolidation.truth_layer_registry import (
    ColumnSpec,
    MergeRule,
    ReconciliationThresholds,
    TemporalSpec,
    TruthLayerRegistry,
    TruthLayerSpec,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_CONTRACTS_DIR = Path(__file__).resolve().parents[5] / "k0" / "contracts" / "schemas"


@pytest.fixture()
def registry() -> TruthLayerRegistry:
    return TruthLayerRegistry.from_contracts(_CONTRACTS_DIR)


@pytest.fixture()
def sem_spec(registry: TruthLayerRegistry) -> TruthLayerSpec:
    return registry.get("st_sem")


def _minimal_spec(columns: dict[str, ColumnSpec]) -> TruthLayerSpec:
    """Build a TruthLayerSpec with only the columns we want to test."""
    return TruthLayerSpec(
        layer_name="st_test",
        pk_column="test_id",
        version_column="version",
        supersedes_column="supersedes_id",
        canonical_column="is_canonical",
        observation_count_column="observation_count",
        confidence_column="confidence",
        confidence_boost_strategy="none",
        archival_status_column="archival_status",
        active_status_value="ACTIVE",
        decay_lambda=0.001,
        embedding_fk_column="embedding_id",
        supports_embedding_match=True,
        supports_key_match=False,
        identity_columns=(),
        write_order=1,
        temporal=TemporalSpec(
            start=None,
            end=None,
            last_observed="last_observed_at",
            first_observed=None,
        ),
        thresholds=ReconciliationThresholds(
            reinforce=0.85,
            extend=0.60,
            evolve=0.40,
        ),
        columns=columns,
    )


# =========================================================================
# V10: IMMUTABLE skipped
# =========================================================================


class TestImmutable:
    def test_immutable_skipped(self) -> None:
        spec = _minimal_spec(
            {
                "pk_col": ColumnSpec(
                    name="pk_col",
                    sql_type="TEXT",
                    nullable=False,
                    merge=MergeRule.IMMUTABLE,
                ),
            }
        )
        result = MergeEngine.build_extend_data(spec, {"pk_col": "val"}, "rec-1")
        assert "pk_col" not in result


# =========================================================================
# V6: COUNTER
# =========================================================================


class TestCounter:
    def test_counter_increment(self) -> None:
        spec = _minimal_spec(
            {
                "view_count": ColumnSpec(
                    name="view_count",
                    sql_type="INTEGER",
                    nullable=False,
                    merge=MergeRule.COUNTER,
                ),
            }
        )
        result = MergeEngine.build_extend_data(spec, {"view_count": 3}, "rec-1")
        assert result["view_count"] == 3

    def test_counter_one(self) -> None:
        spec = _minimal_spec(
            {
                "hit_count": ColumnSpec(
                    name="hit_count",
                    sql_type="INTEGER",
                    nullable=False,
                    merge=MergeRule.COUNTER,
                ),
            }
        )
        result = MergeEngine.build_extend_data(spec, {"hit_count": 1}, "rec-1")
        assert result["hit_count"] == 1


# =========================================================================
# REPLACED
# =========================================================================


class TestReplaced:
    def test_replaced(self) -> None:
        spec = _minimal_spec(
            {
                "label": ColumnSpec(
                    name="label",
                    sql_type="TEXT",
                    nullable=True,
                    merge=MergeRule.REPLACED,
                ),
            }
        )
        result = MergeEngine.build_extend_data(spec, {"label": "new"}, "rec-1")
        assert result["label"] == "new"


# =========================================================================
# COALESCE
# =========================================================================


class TestCoalesce:
    def test_coalesce(self) -> None:
        spec = _minimal_spec(
            {
                "summary": ColumnSpec(
                    name="summary",
                    sql_type="TEXT",
                    nullable=True,
                    merge=MergeRule.COALESCE,
                ),
            }
        )
        result = MergeEngine.build_extend_data(spec, {"summary": "updated"}, "rec-1")
        assert result["summary"] == "updated"


# =========================================================================
# V3: APPENDABLE_DISTINCT
# =========================================================================


class TestAppendableDistinct:
    def test_appendable_distinct_dedup(self) -> None:
        spec = _minimal_spec(
            {
                "tags": ColumnSpec(
                    name="tags",
                    sql_type="JSONB",
                    nullable=True,
                    merge=MergeRule.APPENDABLE_DISTINCT,
                ),
            }
        )
        result = MergeEngine.build_extend_data(
            spec,
            {"tags": ["a", "b"]},
            "rec-1",
        )
        assert result["tags"] == ["a", "b"]


# =========================================================================
# APPENDABLE_ALL
# =========================================================================


class TestAppendableAll:
    def test_appendable_all(self) -> None:
        spec = _minimal_spec(
            {
                "events": ColumnSpec(
                    name="events",
                    sql_type="JSONB",
                    nullable=True,
                    merge=MergeRule.APPENDABLE_ALL,
                ),
            }
        )
        result = MergeEngine.build_extend_data(
            spec,
            {"events": ["e1", "e2"]},
            "rec-1",
        )
        assert result["events"] == ["e1", "e2"]


# =========================================================================
# V8: APPENDABLE_CAPPED
# =========================================================================


class TestAppendableCapped:
    def test_appendable_capped_limit(self) -> None:
        spec = _minimal_spec(
            {
                "trajectory": ColumnSpec(
                    name="trajectory",
                    sql_type="JSONB",
                    nullable=True,
                    merge=MergeRule.APPENDABLE_CAPPED,
                    cap=20,
                ),
            }
        )
        result = MergeEngine.build_extend_data(
            spec,
            {"trajectory": [0.5, 0.6]},
            "rec-1",
        )
        assert result["trajectory"] == [0.5, 0.6]
        assert result["_trajectory_cap"] == 20

    def test_appendable_capped_cap_key(self) -> None:
        spec = _minimal_spec(
            {
                "history": ColumnSpec(
                    name="history",
                    sql_type="JSONB",
                    nullable=True,
                    merge=MergeRule.APPENDABLE_CAPPED,
                    cap=10,
                ),
            }
        )
        result = MergeEngine.build_extend_data(
            spec,
            {"history": ["x"]},
            "rec-1",
        )
        assert "_history_cap" in result
        assert result["_history_cap"] == 10


# =========================================================================
# ADDITIVE_MERGE
# =========================================================================


class TestAdditiveMerge:
    def test_additive_merge(self) -> None:
        spec = _minimal_spec(
            {
                "emotions_json": ColumnSpec(
                    name="emotions_json",
                    sql_type="JSONB",
                    nullable=True,
                    merge=MergeRule.ADDITIVE_MERGE,
                ),
            }
        )
        result = MergeEngine.build_extend_data(
            spec,
            {"emotions_json": {"joy": 3}},
            "rec-1",
        )
        assert result["emotions_json"] == {"joy": 3}


# =========================================================================
# V9: SHALLOW_MERGE
# =========================================================================


class TestShallowMerge:
    def test_shallow_merge(self) -> None:
        spec = _minimal_spec(
            {
                "attrs": ColumnSpec(
                    name="attrs",
                    sql_type="JSONB",
                    nullable=True,
                    merge=MergeRule.SHALLOW_MERGE,
                ),
            }
        )
        result = MergeEngine.build_extend_data(
            spec,
            {"attrs": {"color": "red"}},
            "rec-1",
        )
        assert result["attrs"] == {"color": "red"}


# =========================================================================
# V4: TEMPORAL_MIN
# =========================================================================


class TestTemporalMin:
    def test_temporal_min(self) -> None:
        spec = _minimal_spec(
            {
                "first_seen": ColumnSpec(
                    name="first_seen",
                    sql_type="BIGINT",
                    nullable=True,
                    merge=MergeRule.TEMPORAL_MIN,
                ),
            }
        )
        result = MergeEngine.build_extend_data(
            spec,
            {"first_seen": 1000},
            "rec-1",
        )
        assert result["first_seen"] == 1000


# =========================================================================
# V5: TEMPORAL_MAX
# =========================================================================


class TestTemporalMax:
    def test_temporal_max(self) -> None:
        spec = _minimal_spec(
            {
                "last_seen": ColumnSpec(
                    name="last_seen",
                    sql_type="BIGINT",
                    nullable=True,
                    merge=MergeRule.TEMPORAL_MAX,
                ),
            }
        )
        result = MergeEngine.build_extend_data(
            spec,
            {"last_seen": 2000},
            "rec-1",
        )
        assert result["last_seen"] == 2000


# =========================================================================
# V7: EMA
# =========================================================================


class TestEma:
    def test_ema_with_alpha(self) -> None:
        spec = _minimal_spec(
            {
                "avg_val": ColumnSpec(
                    name="avg_val",
                    sql_type="FLOAT",
                    nullable=True,
                    merge=MergeRule.EMA,
                    ema_alpha=0.1,
                ),
            }
        )
        result = MergeEngine.build_extend_data(
            spec,
            {"avg_val": 0.75},
            "rec-1",
        )
        assert result["avg_val"] == 0.75
        assert result["_avg_val_alpha"] == pytest.approx(0.1)


# =========================================================================
# TREND
# =========================================================================


class TestTrend:
    def test_trend(self) -> None:
        spec = _minimal_spec(
            {
                "trend_val": ColumnSpec(
                    name="trend_val",
                    sql_type="FLOAT",
                    nullable=True,
                    merge=MergeRule.TREND,
                    trend_alpha=0.3,
                ),
            }
        )
        result = MergeEngine.build_extend_data(
            spec,
            {"trend_val": 1.5},
            "rec-1",
        )
        assert result["trend_val"] == 1.5


# =========================================================================
# V11: DERIVED skipped
# =========================================================================


class TestDerived:
    def test_derived_skipped(self) -> None:
        spec = _minimal_spec(
            {
                "duration_minutes": ColumnSpec(
                    name="duration_minutes",
                    sql_type="FLOAT",
                    nullable=True,
                    merge=MergeRule.DERIVED,
                ),
            }
        )
        result = MergeEngine.build_extend_data(
            spec,
            {"duration_minutes": 42.0},
            "rec-1",
        )
        assert "duration_minutes" not in result


# =========================================================================
# PG_ARRAY_CONCAT
# =========================================================================


class TestPgArrayConcat:
    def test_pg_array_concat(self) -> None:
        spec = _minimal_spec(
            {
                "evidence_ids": ColumnSpec(
                    name="evidence_ids",
                    sql_type="TEXT[]",
                    nullable=True,
                    merge=MergeRule.PG_ARRAY_CONCAT,
                ),
            }
        )
        result = MergeEngine.build_extend_data(
            spec,
            {"evidence_ids": ["x", "y"]},
            "rec-1",
        )
        assert result["evidence_ids"] == ["x", "y"]


# =========================================================================
# STATUS
# =========================================================================


class TestStatus:
    def test_status(self) -> None:
        spec = _minimal_spec(
            {
                "lifecycle": ColumnSpec(
                    name="lifecycle",
                    sql_type="TEXT",
                    nullable=False,
                    merge=MergeRule.STATUS,
                ),
            }
        )
        result = MergeEngine.build_extend_data(
            spec,
            {"lifecycle": "COMPLETED"},
            "rec-1",
        )
        assert result["lifecycle"] == "COMPLETED"


# =========================================================================
# Observation count and last_observed always included
# =========================================================================


class TestAlwaysIncluded:
    def test_observation_count_always(self) -> None:
        spec = _minimal_spec({})
        result = MergeEngine.build_extend_data(spec, {}, "rec-1")
        assert result["observation_count"] == 1

    def test_last_observed_always(self) -> None:
        spec = _minimal_spec({})
        result = MergeEngine.build_extend_data(spec, {}, "rec-1")
        assert "last_observed_at" in result
        assert isinstance(result["last_observed_at"], int)


# =========================================================================
# Missing candidate data -> column skipped
# =========================================================================


class TestMissingData:
    def test_absent_column_skipped(self) -> None:
        spec = _minimal_spec(
            {
                "label": ColumnSpec(
                    name="label",
                    sql_type="TEXT",
                    nullable=True,
                    merge=MergeRule.REPLACED,
                ),
            }
        )
        # candidate_data has no "label" key
        result = MergeEngine.build_extend_data(spec, {}, "rec-1")
        assert "label" not in result

    def test_only_present_columns_merged(self) -> None:
        spec = _minimal_spec(
            {
                "a": ColumnSpec(
                    name="a",
                    sql_type="TEXT",
                    nullable=True,
                    merge=MergeRule.REPLACED,
                ),
                "b": ColumnSpec(
                    name="b",
                    sql_type="TEXT",
                    nullable=True,
                    merge=MergeRule.REPLACED,
                ),
            }
        )
        result = MergeEngine.build_extend_data(spec, {"a": "x"}, "rec-1")
        assert result["a"] == "x"
        assert "b" not in result


# =========================================================================
# V24: All 16 merge rules have at least one test (summary check)
# =========================================================================


class TestAllRulesCovered:
    """Meta-test: verify every MergeRule enum value has a test class above."""

    TESTED_RULES = {
        MergeRule.IMMUTABLE,
        MergeRule.COUNTER,
        MergeRule.REPLACED,
        MergeRule.COALESCE,
        MergeRule.APPENDABLE_DISTINCT,
        MergeRule.APPENDABLE_ALL,
        MergeRule.APPENDABLE_CAPPED,
        MergeRule.ADDITIVE_MERGE,
        MergeRule.SHALLOW_MERGE,
        MergeRule.TEMPORAL_MIN,
        MergeRule.TEMPORAL_MAX,
        MergeRule.EMA,
        MergeRule.TREND,
        MergeRule.DERIVED,
        MergeRule.PG_ARRAY_CONCAT,
        MergeRule.STATUS,
    }

    def test_all_rules_covered(self) -> None:
        all_rules = set(MergeRule)
        assert all_rules == self.TESTED_RULES


# =========================================================================
# Real layer spec (integration-style)
# =========================================================================


class TestRealSpec:
    def test_sem_extend(self, sem_spec: TruthLayerSpec) -> None:
        """Feed real st_sem spec with some candidate data."""
        candidate_data = {
            "pattern_name": "evening routine",
            "source_texts_json": ["text1", "text2"],
        }
        result = MergeEngine.build_extend_data(sem_spec, candidate_data, "rec-1")
        # pattern_name is REPLACED in st_sem
        assert "pattern_name" in result
        assert result["pattern_name"] == "evening routine"
        # observation_count always present
        assert result[sem_spec.observation_count_column] == 1
