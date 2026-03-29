"""TruthCandidateQueryBuilder -- M9.3 SQL generation.

Builds parameterized SQL for truth candidate queries.  Uses
TruthLayerSpec (M9.1) to determine per-layer column names,
JOIN patterns, and filter clauses.  Never interpolates values
into SQL -- all dynamic values are passed as positional params.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from k0.modules.consolidation.query import QueryMode, TruthCandidateRequest

if TYPE_CHECKING:
    from k0.modules.consolidation.truth_layer_registry import TruthLayerRegistry, TruthLayerSpec

# ---- Per-layer extra columns selected into TruthRecord.metadata -----------
# Keys are truth layer names, values are column lists.
# These are layer-specific columns beyond the common fields
# (record_id, layer, similarity, confidence, version, observation_count,
#  last_observed_ms).

EXTRA_COLUMNS: dict[str, tuple[str, ...]] = {
    "st_epi": (
        "participants_json",
        "primary_location",
        "episode_type",
        "start_time_utc",
        "end_time_utc",
        "narrative_thread_id",
        "dominant_social_context",
        "activity_type_ultrabert",
        "source_events_json",
    ),
    "st_sem": (
        "pattern_type",
        "pattern_name",
        "pattern_attributes_json",
        "temporal_regularity",
    ),
    "st_procedural": (
        "routine_name",
        "routine_category",
        "temporal_anchor",
        "day_pattern",
        "action_sequence_json",
    ),
    "st_social": (
        "actor_a_id",
        "actor_b_id",
        "relationship_type",
        "avg_sentiment",
        "relationship_strength",
    ),
    "st_prospective": (
        "intention_type",
        "intention_description",
        "status",
        "target_date",
    ),
    "st_kg_dom": (
        "canonical_name",
        "entity_type",
        "entity_subtype",
        "aliases_json",
        "attributes_json",
    ),
    "st_kg_edges": (
        "source_entity_id",
        "target_entity_id",
        "relation_type",
        "relation_subtype",
        "edge_weight",
        "properties_json",
    ),
}


class TruthCandidateQueryBuilder:
    """Builds parameterized SQL for truth candidate queries.

    Uses TruthLayerSpec (M9.1) to determine per-layer column names,
    JOIN patterns, and filter clauses.
    """

    def __init__(self, registry: TruthLayerRegistry) -> None:
        self._registry = registry

    def build(
        self,
        layer: str,
        mode: QueryMode,
        request: TruthCandidateRequest,
    ) -> tuple[str, list[Any]]:
        """Generate (sql, params) for one layer.

        Returns:
            Tuple of (parameterized SQL string, ordered parameter list).
        """
        spec = self._registry.get(layer)
        if mode == QueryMode.EMBEDDING:
            return self._build_embedding(spec, request)
        elif mode == QueryMode.KEY:
            return self._build_key(spec, request)
        else:
            return self._build_hybrid(spec, request)

    # ------------------------------------------------------------------
    # EMBEDDING mode (st_epi, st_sem, st_procedural, st_social, st_prospective)
    # ------------------------------------------------------------------

    def _build_embedding(
        self, spec: TruthLayerSpec, req: TruthCandidateRequest
    ) -> tuple[str, list[Any]]:
        layer = spec.layer_name
        pk = spec.pk_column
        conf = spec.confidence_column
        emb_fk = spec.embedding_fk_column
        obs = spec.observation_count_column
        last_obs = spec.temporal.last_observed

        extras = self._extra_select(layer, "t")
        archival_clause = self._archival_clause(spec, "t")

        sql = (
            f"SELECT\n"
            f"    t.{pk} AS record_id,\n"
            f"    '{layer}' AS layer,\n"
            f"    1 - (v.vector <=> $1::vector) AS similarity,\n"
            f"    t.{conf} AS confidence,\n"
            f"    t.{spec.version_column} AS version,\n"
            f"    t.{obs} AS observation_count,\n"
            f"    t.{last_obs} AS last_observed_ms\n"
            f"{extras}"
            f"FROM {layer} t\n"
            f"JOIN st_vec v ON t.{emb_fk} = v.embedding_id\n"
            f"WHERE t.tenant_id = $2\n"
            f"  AND t.space_id = $3\n"
            f"{archival_clause}"
            f"  AND v.vector IS NOT NULL\n"
            f"  AND 1 - (v.vector <=> $1::vector) >= $4\n"
            f"ORDER BY v.vector <=> $1::vector ASC\n"
            f"LIMIT $5"
        )

        embedding_str = _format_embedding(req.query_embedding)
        params: list[Any] = [
            embedding_str,
            req.tenant_id,
            req.space_id,
            req.min_similarity,
            req.top_k,
        ]
        return sql, params

    # ------------------------------------------------------------------
    # KEY mode (st_kg_edges)
    # ------------------------------------------------------------------

    def _build_key(self, spec: TruthLayerSpec, req: TruthCandidateRequest) -> tuple[str, list[Any]]:
        layer = spec.layer_name
        pk = spec.pk_column
        conf = spec.confidence_column
        obs = spec.observation_count_column
        last_obs = spec.temporal.last_observed

        extras = self._extra_select(layer, "t")
        archival_clause = self._archival_clause(spec, "t")

        param_idx = 1
        params: list[Any] = []

        # Scope
        scope_clause = f"WHERE t.tenant_id = ${param_idx}\n"
        params.append(req.tenant_id)
        param_idx += 1
        scope_clause += f"  AND t.space_id = ${param_idx}\n"
        params.append(req.space_id)
        param_idx += 1

        # Key filters (only for columns in spec.identity_columns)
        key_clause = ""
        for col in spec.identity_columns:
            if col in req.key_filters:
                key_clause += f"  AND t.{col} = ${param_idx}\n"
                params.append(req.key_filters[col])
                param_idx += 1

        # Limit
        limit_clause = f"LIMIT ${param_idx}"
        params.append(req.top_k)

        sql = (
            f"SELECT\n"
            f"    t.{pk} AS record_id,\n"
            f"    '{layer}' AS layer,\n"
            f"    0.0 AS similarity,\n"
            f"    t.{conf} AS confidence,\n"
            f"    t.{spec.version_column} AS version,\n"
            f"    t.{obs} AS observation_count,\n"
            f"    t.{last_obs} AS last_observed_ms\n"
            f"{extras}"
            f"FROM {layer} t\n"
            f"{scope_clause}"
            f"{archival_clause}"
            f"{key_clause}"
            f"ORDER BY t.{obs} DESC\n"
            f"{limit_clause}"
        )
        return sql, params

    # ------------------------------------------------------------------
    # HYBRID mode (st_kg_dom)
    # ------------------------------------------------------------------

    def _build_hybrid(
        self, spec: TruthLayerSpec, req: TruthCandidateRequest
    ) -> tuple[str, list[Any]]:
        layer = spec.layer_name
        pk = spec.pk_column
        conf = spec.confidence_column
        emb_fk = spec.embedding_fk_column
        obs = spec.observation_count_column
        last_obs = spec.temporal.last_observed

        extras = self._extra_select(layer, "t")
        archival_clause = self._archival_clause(spec, "t")

        param_idx = 1
        params: list[Any] = []

        # $1 = embedding
        embedding_str = _format_embedding(req.query_embedding)
        params.append(embedding_str)
        param_idx += 1

        # Scope
        scope_clause = f"WHERE t.tenant_id = ${param_idx}\n"
        params.append(req.tenant_id)
        param_idx += 1
        scope_clause += f"  AND t.space_id = ${param_idx}\n"
        params.append(req.space_id)
        param_idx += 1

        # Key filters
        key_clause = ""
        for col in spec.identity_columns:
            if col in req.key_filters:
                val = req.key_filters[col]
                if col == "canonical_name":
                    # Fuzzy match for entity name
                    pattern = f"%{val.lower()}%"
                    key_clause += (
                        f"  AND (LOWER(t.canonical_name) LIKE ${param_idx}"
                        f" OR LOWER(t.aliases_json::text) LIKE ${param_idx})\n"
                    )
                    params.append(pattern)
                    param_idx += 1
                else:
                    key_clause += f"  AND t.{col} = ${param_idx}\n"
                    params.append(val)
                    param_idx += 1

        # Limit
        limit_clause = f"LIMIT ${param_idx}"
        params.append(req.top_k)

        sql = (
            f"SELECT\n"
            f"    t.{pk} AS record_id,\n"
            f"    '{layer}' AS layer,\n"
            f"    CASE WHEN v.vector IS NOT NULL\n"
            f"         THEN 1 - (v.vector <=> $1::vector)\n"
            f"         ELSE 0.0\n"
            f"    END AS similarity,\n"
            f"    t.{conf} AS confidence,\n"
            f"    t.{spec.version_column} AS version,\n"
            f"    t.{obs} AS observation_count,\n"
            f"    t.{last_obs} AS last_observed_ms\n"
            f"{extras}"
            f"FROM {layer} t\n"
            f"LEFT JOIN st_vec v ON t.{emb_fk} = v.embedding_id\n"
            f"{scope_clause}"
            f"{archival_clause}"
            f"{key_clause}"
            f"ORDER BY\n"
            f"    CASE WHEN v.vector IS NOT NULL\n"
            f"         THEN v.vector <=> $1::vector\n"
            f"         ELSE 999.0\n"
            f"    END ASC,\n"
            f"    t.{obs} DESC\n"
            f"{limit_clause}"
        )
        return sql, params

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extra_select(layer: str, alias: str) -> str:
        """Build the extra column SELECT fragment for a layer."""
        cols = EXTRA_COLUMNS.get(layer, ())
        if not cols:
            return ""
        return "".join(f"    , {alias}.{c}\n" for c in cols)

    @staticmethod
    def _archival_clause(spec: TruthLayerSpec, alias: str) -> str:
        """Build the archival_status = 'ACTIVE' clause if the layer has it."""
        col = spec.archival_status_column
        val = spec.active_status_value
        if col:
            return f"  AND {alias}.{col} = '{val}'\n"
        return ""


def _format_embedding(embedding: list[float] | None) -> str:
    """Convert list[float] to pgvector string format for $1::vector cast."""
    if embedding is None:
        return "[]"
    return "[" + ",".join(str(f) for f in embedding) + "]"
