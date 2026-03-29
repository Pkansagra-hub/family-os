"""Tests for TruthCandidateQueryBuilder -- M9.3 D8.

SQL generation tests for all 3 modes x 7 layers.
Validates: parameterised placeholders, pgvector <=> operator,
archival_status filter, extra columns, ORDER BY, LIMIT.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from k0.modules.consolidation.query import QueryMode, TruthCandidateRequest
from k0.modules.consolidation.query.builder import (
    EXTRA_COLUMNS,
    TruthCandidateQueryBuilder,
    _format_embedding,
)
from k0.modules.consolidation.truth_layer_registry import TruthLayerRegistry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CONTRACTS_DIR = Path(__file__).resolve().parents[5] / "k0" / "contracts" / "schemas"


@pytest.fixture(scope="module")
def registry() -> TruthLayerRegistry:
    return TruthLayerRegistry.from_contracts(CONTRACTS_DIR)


@pytest.fixture(scope="module")
def builder(registry: TruthLayerRegistry) -> TruthCandidateQueryBuilder:
    return TruthCandidateQueryBuilder(registry)


def _make_request(**overrides) -> TruthCandidateRequest:
    defaults = {
        "tenant_id": "t1",
        "space_id": "s1",
        "layers": ("st_epi",),
        "query_embedding": [0.1] * 768,
        "top_k": 10,
        "min_similarity": 0.35,
    }
    defaults.update(overrides)
    return TruthCandidateRequest(**defaults)


# ===========================================================================
# Helper: _format_embedding
# ===========================================================================


class TestFormatEmbedding:
    def test_none_produces_empty_brackets(self):
        assert _format_embedding(None) == "[]"

    def test_list_of_floats(self):
        result = _format_embedding([0.1, 0.2, 0.3])
        assert result == "[0.1,0.2,0.3]"

    def test_768_dim(self):
        vec = [float(i) / 768 for i in range(768)]
        result = _format_embedding(vec)
        assert result.startswith("[")
        assert result.endswith("]")
        assert result.count(",") == 767


# ===========================================================================
# EMBEDDING mode
# ===========================================================================


EMBEDDING_LAYERS = ("st_epi", "st_sem", "st_procedural", "st_social", "st_prospective")


class TestEmbeddingMode:
    @pytest.mark.parametrize("layer", EMBEDDING_LAYERS)
    def test_embedding_sql_contains_pgvector_operator(self, builder, layer):
        req = _make_request(layers=(layer,))
        sql, params = builder.build(layer, QueryMode.EMBEDDING, req)
        assert "<=> $1::vector" in sql

    @pytest.mark.parametrize("layer", EMBEDDING_LAYERS)
    def test_embedding_sql_has_order_by(self, builder, layer):
        req = _make_request(layers=(layer,))
        sql, _ = builder.build(layer, QueryMode.EMBEDDING, req)
        assert "ORDER BY v.vector <=> $1::vector ASC" in sql

    @pytest.mark.parametrize("layer", EMBEDDING_LAYERS)
    def test_embedding_sql_has_limit(self, builder, layer):
        req = _make_request(layers=(layer,))
        sql, params = builder.build(layer, QueryMode.EMBEDDING, req)
        assert "LIMIT $5" in sql
        assert params[4] == 10  # top_k

    @pytest.mark.parametrize("layer", EMBEDDING_LAYERS)
    def test_embedding_sql_has_min_similarity_filter(self, builder, layer):
        req = _make_request(layers=(layer,), min_similarity=0.4)
        sql, params = builder.build(layer, QueryMode.EMBEDDING, req)
        assert ">= $4" in sql
        assert params[3] == 0.4

    @pytest.mark.parametrize("layer", EMBEDDING_LAYERS)
    def test_embedding_sql_has_scope_params(self, builder, layer):
        req = _make_request(layers=(layer,))
        sql, params = builder.build(layer, QueryMode.EMBEDDING, req)
        assert "t.tenant_id = $2" in sql
        assert "t.space_id = $3" in sql
        assert params[1] == "t1"
        assert params[2] == "s1"

    @pytest.mark.parametrize("layer", EMBEDDING_LAYERS)
    def test_embedding_sql_has_similarity_column(self, builder, layer):
        req = _make_request(layers=(layer,))
        sql, _ = builder.build(layer, QueryMode.EMBEDDING, req)
        assert "1 - (v.vector <=> $1::vector) AS similarity" in sql

    @pytest.mark.parametrize("layer", EMBEDDING_LAYERS)
    def test_embedding_sql_has_archival_filter(self, builder, registry, layer):
        req = _make_request(layers=(layer,))
        sql, _ = builder.build(layer, QueryMode.EMBEDDING, req)
        spec = registry.get(layer)
        assert f"t.{spec.archival_status_column} = '{spec.active_status_value}'" in sql

    @pytest.mark.parametrize("layer", EMBEDDING_LAYERS)
    def test_embedding_sql_has_vec_join(self, builder, registry, layer):
        req = _make_request(layers=(layer,))
        sql, _ = builder.build(layer, QueryMode.EMBEDDING, req)
        spec = registry.get(layer)
        assert f"JOIN st_vec v ON t.{spec.embedding_fk_column} = v.embedding_id" in sql

    @pytest.mark.parametrize("layer", EMBEDDING_LAYERS)
    def test_embedding_sql_has_null_vector_filter(self, builder, layer):
        req = _make_request(layers=(layer,))
        sql, _ = builder.build(layer, QueryMode.EMBEDDING, req)
        assert "v.vector IS NOT NULL" in sql

    @pytest.mark.parametrize("layer", EMBEDDING_LAYERS)
    def test_embedding_sql_selects_extra_columns(self, builder, layer):
        req = _make_request(layers=(layer,))
        sql, _ = builder.build(layer, QueryMode.EMBEDDING, req)
        for col in EXTRA_COLUMNS[layer]:
            assert f"t.{col}" in sql

    @pytest.mark.parametrize("layer", EMBEDDING_LAYERS)
    def test_embedding_params_count(self, builder, layer):
        req = _make_request(layers=(layer,))
        _, params = builder.build(layer, QueryMode.EMBEDDING, req)
        # $1=embedding, $2=tenant, $3=space, $4=min_sim, $5=top_k
        assert len(params) == 5

    @pytest.mark.parametrize("layer", EMBEDDING_LAYERS)
    def test_embedding_param_1_is_formatted_vector(self, builder, layer):
        req = _make_request(layers=(layer,))
        _, params = builder.build(layer, QueryMode.EMBEDDING, req)
        assert isinstance(params[0], str)
        assert params[0].startswith("[")

    @pytest.mark.parametrize("layer", EMBEDDING_LAYERS)
    def test_embedding_sql_has_layer_literal(self, builder, layer):
        req = _make_request(layers=(layer,))
        sql, _ = builder.build(layer, QueryMode.EMBEDDING, req)
        assert f"'{layer}' AS layer" in sql

    @pytest.mark.parametrize("layer", EMBEDDING_LAYERS)
    def test_embedding_sql_selects_common_columns(self, builder, registry, layer):
        req = _make_request(layers=(layer,))
        sql, _ = builder.build(layer, QueryMode.EMBEDDING, req)
        spec = registry.get(layer)
        assert f"t.{spec.pk_column} AS record_id" in sql
        assert "AS confidence" in sql
        assert "AS version" in sql
        assert "AS observation_count" in sql
        assert "AS last_observed_ms" in sql


# ===========================================================================
# KEY mode
# ===========================================================================


class TestKeyMode:
    def test_key_sql_for_kg_edges(self, builder):
        req = _make_request(
            layers=("st_kg_edges",),
            query_embedding=None,
            key_filters={
                "source_entity_id": "ent_1",
                "target_entity_id": "ent_2",
                "relation_type": "KNOWS",
            },
        )
        sql, params = builder.build("st_kg_edges", QueryMode.KEY, req)
        assert "st_kg_edges t" in sql
        assert "0.0 AS similarity" in sql
        assert "source_entity_id = $" in sql
        assert "target_entity_id = $" in sql
        assert "relation_type = $" in sql
        assert "ent_1" in params
        assert "ent_2" in params
        assert "KNOWS" in params

    def test_key_sql_no_pgvector_join(self, builder):
        req = _make_request(
            layers=("st_kg_edges",),
            query_embedding=None,
            key_filters={"source_entity_id": "ent_1"},
        )
        sql, _ = builder.build("st_kg_edges", QueryMode.KEY, req)
        assert "st_vec" not in sql
        assert "<=>" not in sql

    def test_key_sql_order_by_observation_count(self, builder):
        req = _make_request(
            layers=("st_kg_edges",),
            query_embedding=None,
            key_filters={},
        )
        sql, _ = builder.build("st_kg_edges", QueryMode.KEY, req)
        assert "ORDER BY" in sql
        assert "observation_count DESC" in sql

    def test_key_sql_has_archival_filter(self, builder):
        req = _make_request(
            layers=("st_kg_edges",),
            query_embedding=None,
            key_filters={},
        )
        sql, _ = builder.build("st_kg_edges", QueryMode.KEY, req)
        assert "archival_status = 'ACTIVE'" in sql

    def test_key_sql_has_limit(self, builder):
        req = _make_request(
            layers=("st_kg_edges",),
            query_embedding=None,
            key_filters={},
            top_k=5,
        )
        sql, params = builder.build("st_kg_edges", QueryMode.KEY, req)
        assert "LIMIT" in sql
        assert params[-1] == 5

    def test_key_sql_selects_extra_columns(self, builder):
        req = _make_request(
            layers=("st_kg_edges",),
            query_embedding=None,
            key_filters={},
        )
        sql, _ = builder.build("st_kg_edges", QueryMode.KEY, req)
        for col in EXTRA_COLUMNS["st_kg_edges"]:
            assert f"t.{col}" in sql

    def test_key_sql_partial_filters(self, builder):
        """Only some identity columns provided."""
        req = _make_request(
            layers=("st_kg_edges",),
            query_embedding=None,
            key_filters={"source_entity_id": "ent_1"},
        )
        sql, params = builder.build("st_kg_edges", QueryMode.KEY, req)
        assert "source_entity_id = $" in sql
        assert (
            "target_entity_id" not in sql.split("WHERE")[1].split("ORDER")[0]
            or "target_entity_id = $" not in sql
        )

    def test_key_mode_no_filters(self, builder):
        """No key_filters provided = no extra WHERE clauses."""
        req = _make_request(
            layers=("st_kg_edges",),
            query_embedding=None,
            key_filters={},
        )
        sql, params = builder.build("st_kg_edges", QueryMode.KEY, req)
        # Should still have scope and archival
        assert "tenant_id = $1" in sql
        assert "space_id = $2" in sql
        # params: tenant, space, limit
        assert len(params) == 3


# ===========================================================================
# HYBRID mode
# ===========================================================================


class TestHybridMode:
    def test_hybrid_sql_for_kg_dom(self, builder):
        req = _make_request(
            layers=("st_kg_dom",),
            key_filters={"entity_type": "PERSON", "canonical_name": "Maya"},
        )
        sql, params = builder.build("st_kg_dom", QueryMode.HYBRID, req)
        assert "st_kg_dom t" in sql
        assert "LEFT JOIN st_vec v" in sql
        assert "<=> $1::vector" in sql
        assert "entity_type = $" in sql
        assert "LOWER(t.canonical_name) LIKE $" in sql

    def test_hybrid_sql_has_case_similarity(self, builder):
        req = _make_request(layers=("st_kg_dom",), key_filters={})
        sql, _ = builder.build("st_kg_dom", QueryMode.HYBRID, req)
        assert "CASE WHEN v.vector IS NOT NULL" in sql
        assert "ELSE 0.0" in sql

    def test_hybrid_sql_order_by_with_fallback(self, builder):
        req = _make_request(layers=("st_kg_dom",), key_filters={})
        sql, _ = builder.build("st_kg_dom", QueryMode.HYBRID, req)
        assert "ELSE 999.0" in sql
        assert "observation_count DESC" in sql

    def test_hybrid_sql_fuzzy_name_matching(self, builder):
        req = _make_request(
            layers=("st_kg_dom",),
            key_filters={"canonical_name": "Maya"},
        )
        sql, params = builder.build("st_kg_dom", QueryMode.HYBRID, req)
        assert "LOWER(t.canonical_name) LIKE" in sql
        assert "LOWER(t.aliases_json::text) LIKE" in sql
        # Pattern should be lowercased with wildcards
        assert "%maya%" in params

    def test_hybrid_sql_has_archival_filter(self, builder):
        req = _make_request(layers=("st_kg_dom",), key_filters={})
        sql, _ = builder.build("st_kg_dom", QueryMode.HYBRID, req)
        assert "archival_status = 'ACTIVE'" in sql

    def test_hybrid_sql_selects_extra_columns(self, builder):
        req = _make_request(layers=("st_kg_dom",), key_filters={})
        sql, _ = builder.build("st_kg_dom", QueryMode.HYBRID, req)
        for col in EXTRA_COLUMNS["st_kg_dom"]:
            assert f"t.{col}" in sql

    def test_hybrid_no_key_filters(self, builder):
        """HYBRID with no key_filters = just embedding search + LEFT JOIN."""
        req = _make_request(layers=("st_kg_dom",), key_filters={})
        sql, params = builder.build("st_kg_dom", QueryMode.HYBRID, req)
        # $1=embedding, $2=tenant, $3=space, $4=limit
        assert len(params) == 4
        assert "LEFT JOIN st_vec v" in sql


# ===========================================================================
# Cross-mode tests
# ===========================================================================


class TestCrossMode:
    def test_no_string_interpolation_of_values(self, builder):
        """Verify no user values are interpolated into SQL (only $N params)."""
        req = _make_request(
            layers=("st_kg_edges",),
            query_embedding=None,
            key_filters={"source_entity_id": "'; DROP TABLE st_epi; --"},
        )
        sql, params = builder.build("st_kg_edges", QueryMode.KEY, req)
        assert "DROP TABLE" not in sql
        assert "'; DROP TABLE st_epi; --" in params

    def test_all_layers_produce_valid_sql(self, builder, registry):
        """Every registered layer builds SQL without error."""
        all_layers = registry.truth_layer_names()
        for layer in all_layers:
            spec = registry.get(layer)
            from k0.modules.consolidation.query import resolve_query_mode

            mode = resolve_query_mode(spec.supports_embedding_match, spec.supports_key_match)
            req = _make_request(
                layers=(layer,),
                query_embedding=[0.1] * 768 if spec.supports_embedding_match else None,
                key_filters={col: "test" for col in spec.identity_columns},
            )
            sql, params = builder.build(layer, mode, req)
            assert isinstance(sql, str)
            assert len(sql) > 50
            assert isinstance(params, list)
            assert (
                len(params) >= 3
            )  # At minimum: scope + limit (or embedding + scope + min_sim + limit)

    def test_embedding_mode_requires_embedding_string_param(self, builder):
        """EMBEDDING mode $1 is always a formatted embedding string."""
        req = _make_request(layers=("st_epi",))
        _, params = builder.build("st_epi", QueryMode.EMBEDDING, req)
        assert isinstance(params[0], str)
        assert params[0].startswith("[")
        assert params[0].endswith("]")

    @pytest.mark.parametrize(
        "layer,expected_mode",
        [
            ("st_epi", QueryMode.EMBEDDING),
            ("st_sem", QueryMode.EMBEDDING),
            ("st_procedural", QueryMode.HYBRID),
            ("st_social", QueryMode.HYBRID),
            ("st_prospective", QueryMode.EMBEDDING),
            ("st_kg_dom", QueryMode.HYBRID),
            ("st_kg_edges", QueryMode.KEY),
        ],
    )
    def test_resolve_query_mode_from_spec(self, registry, layer, expected_mode):
        from k0.modules.consolidation.query import resolve_query_mode

        spec = registry.get(layer)
        mode = resolve_query_mode(spec.supports_embedding_match, spec.supports_key_match)
        assert mode == expected_mode

    def test_extra_columns_covers_all_layers(self, registry):
        """Every registered layer has an entry in EXTRA_COLUMNS."""
        for layer in registry.truth_layer_names():
            assert layer in EXTRA_COLUMNS, f"Missing EXTRA_COLUMNS for {layer}"
            assert len(EXTRA_COLUMNS[layer]) >= 1
