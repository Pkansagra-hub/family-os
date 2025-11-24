"""
Hippocampus Events Row Builder Module (M13)

Assembles complete st_hipp_events row from all enrichment module outputs.

**Purpose**: Convergence point for P02 write pipeline - maps 13 module outputs
to 60-70 column st_hipp_events table structure.

**Performance**: <10ms P95 (pure assembly, no I/O)

**Contract**: k0/contracts/modules/builders.hipp_events_row.v1.yaml
**ADR**: docs/architecture/decisions-K0/modules/k009.1-hipp-events-builder.md
**Schema**: docs/pipelines/P02_data_schema.md (lines 45-185)

**Inputs** (from 13 enrichment modules):
- M01 (DG Pattern Separation): simhash_hex, minhash32
- M02 (CA1 Semantic Projection): entities_json, kg_triples_json, embedding_id
- M03 (Policy Stamp): effective_band, obligations, policy_version
- M04 (Affect Analysis): valence, arousal, sentiment, emotions
- M05 (Space Visibility): owner_id, visible_to, visibility_scope
- M06 (Salience Scoring): salience_score, salience_reasons, salience_band
- M07 (Family Graph): social_context, participant_roles, intimacy
- M08 (Temporal Profile): 11 temporal columns (event_time_utc, local_date, etc.)
- M09 (Device Profile): device_kind, device_os, client_version
- M10 (Ingress Classify): ingress_topic, activity_type, content_type
- M11 (Retention Lookup): retention_policy_id, retention_bucket
- M12 (Geo Metadata): geohash_6, location_name, geo_precision
- M15 (Spatial Minimal): truncated geohash (privacy-preserving)

**Output**: Dictionary with 60-70 columns ready for st_hipp_events INSERT

**CA3 Deferred Columns** (set to NULL in P02, populated by P03):
- is_near_duplicate
- novelty_score
- episode_cluster_id
- cluster_confidence
- clustering_version

**Version**: 1.0.0
**Last Updated**: 2025-11-17
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict

# =============================================================================
# Metrics Tracking
# =============================================================================


@dataclass
class BuilderMetrics:
    """Metrics for row assembly operations"""

    rows_built: int = 0
    json_serialization_ms: float = 0.0
    validation_failures: int = 0
    column_group_counts: Dict[str, int] = field(default_factory=dict)
    missing_optional_fields: Dict[str, int] = field(default_factory=dict)


_metrics = BuilderMetrics()


# =============================================================================
# JSON Serialization
# =============================================================================


def serialize_to_json(data: Any, field_name: str) -> str:
    """
    Serialize Python object to JSON string for TEXT column storage.

    Args:
        data: Python object (list, dict, etc.)
        field_name: Column name (for error reporting)

    Returns:
        JSON string (compact, no pretty-printing), or None if data is None

    Raises:
        ValueError: If serialization fails
    """
    if data is None:
        return None  # type: ignore

    try:
        start_time = time.perf_counter()
        json_str = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        _metrics.json_serialization_ms += elapsed_ms
        return json_str
    except (TypeError, ValueError) as e:
        raise ValueError(f"JSON serialization failed for {field_name}: {e}")


# =============================================================================
# Column Group Mappers (9 groups)
# =============================================================================


def map_identity_group(envelope: Dict[str, Any], space_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Identity & Trace columns (9 columns)

    From: envelope (flat P02 dossier structure) + M05 space resolution

    Note: event_id in st_hipp_events is populated with cognitive_trace_id per P02 dossier.
    """
    return {
        "event_id": envelope.get("cognitive_trace_id"),  # cognitive_trace_id IS the event_id
        "wal_pos": envelope.get("wal_pos"),
        "cognitive_trace_id": envelope.get("cognitive_trace_id"),
        "tenant_id": envelope.get("tenant_id"),
        "space_id": envelope.get("space_id"),
        "effective_space_id": space_output.get("effective_space_id"),
        "topic": envelope.get("topic"),
        "uow_id": envelope.get("uow_id"),
        "schema_version": envelope.get("schema_version", "1.0.0"),
    }


def map_integrity_group(envelope: Dict[str, Any]) -> Dict[str, Any]:
    """
    Integrity & Audit columns (6 columns)

    From: envelope (flat P02 dossier structure - audit trail)
    """
    return {
        "envelope_sha256": envelope.get("envelope_sha256"),
        "sig_alg": envelope.get("sig_alg", "NONE"),
        "sig_kid": envelope.get("sig_kid", "unsigned"),
        "idem_key": envelope.get("idem_key"),
        "ingested_at": envelope.get("ingested_at") or int(time.time()),
        "clock_skew_ms": envelope.get("clock_skew_ms", 0),
    }


def map_policy_group(
    envelope: Dict[str, Any],
    policy_output: Dict[str, Any],
    space_output: Dict[str, Any],
    retention_output: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Policy & Visibility columns (10 columns)

    From: M03 policy_stamp + M05 space visibility + M11 retention
    """
    policy_stamp = envelope.get("policy_stamp", {})

    return {
        "policy_decision": policy_stamp.get("decision", "ALLOW"),
        "policy_band": envelope.get("band", "GREEN"),  # band is at envelope root level
        "policy_version": policy_stamp.get("version", envelope.get("policy_version", "1.0.0")),
        "obligations_json": serialize_to_json(
            policy_output.get("obligations", []), "obligations_json"
        ),
        "visible_to_json": serialize_to_json(space_output.get("visible_to", []), "visible_to_json"),
        "visibility_scope": space_output.get("visibility_scope", "SPACE_DEFAULT"),
        "owner_id": space_output.get("owner_id"),
        "co_owners_json": serialize_to_json(space_output.get("co_owners", []), "co_owners_json"),
        "retention_policy_id": retention_output.get("retention_policy_id"),
        "retention_bucket": retention_output.get("retention_bucket", "STANDARD"),
    }


def map_actor_device_group(
    envelope: Dict[str, Any], device_output: Dict[str, Any], ingress_output: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Actor & Device columns (6 columns)

    From: envelope (flat structure per P02 dossier) + M09 device profile + M10 ingress classify
    """
    return {
        "actor_id": envelope.get("actor"),  # Aligned with Envelope schema
        "actor_role": envelope.get("actor_role", "SELF"),
        "device_id": envelope.get("device_id"),
        "device_kind": device_output.get("device_kind", "unknown"),
        "device_os": device_output.get("device_os"),
        "ingress_channel": ingress_output.get("ingress_topic", "write"),
    }


def map_temporal_group(temporal_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Temporal columns (11 columns)

    From: M08 temporal_profile
    """
    return {
        "event_time_utc": temporal_output.get("event_time_utc"),
        "write_time_utc": temporal_output.get("write_time_utc"),
        "write_lag_ms": temporal_output.get("write_lag_ms"),
        "local_date": temporal_output.get("local_date"),
        "local_time": temporal_output.get("local_time"),
        "day_of_week": temporal_output.get("day_of_week"),
        "is_weekend": temporal_output.get("is_weekend"),
        "time_of_day_bucket": temporal_output.get("time_of_day_bucket"),
        "circadian_slot": temporal_output.get("circadian_slot"),
        "is_backdated": temporal_output.get("is_backdated"),
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
    }


def map_spatial_group(geo_output: Dict[str, Any], spatial_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Spatial & Place columns (5 columns)

    From: M12 geo_metadata + M15 spatial_minimal
    """
    return {
        "location_name": spatial_output.get("location_name") or geo_output.get("location_name"),
        "location_type": spatial_output.get("location_type") or geo_output.get("location_type"),
        "geohash_6": spatial_output.get("geohash_6") or geo_output.get("geohash_6"),
        "geo_precision_external": geo_output.get("geo_precision_external"),
        "geo_masking_reason": geo_output.get("geo_masking_reason"),
    }


def map_social_group(envelope: Dict[str, Any], social_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Social & Relationships columns (7 columns)

    From: envelope body + M07 family_graph_resolve
    """
    body = envelope.get("body", {})
    participants = body.get("participants", [])

    return {
        "participants_json": serialize_to_json(participants, "participants_json"),
        "num_participants": social_output.get("num_participants", len(participants)),
        "has_partner_present": social_output.get("has_partner_present", False),
        "has_parent_present": social_output.get("has_parent_present", False),
        "is_solo_event": social_output.get("is_solo_event", len(participants) <= 1),
        "participant_roles_json": social_output.get("participant_roles_json"),
        "social_context": social_output.get("social_context", "solo"),
        "social_intimacy": social_output.get("social_intimacy", "LOW"),
    }


def map_semantic_activity_group(
    envelope: Dict[str, Any], ingress_output: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Semantic & Activity columns (9 columns)

    From: envelope body + M10 ingress_classify
    """
    body = envelope.get("body", {})
    text = body.get("text", "")

    return {
        "text": text,
        "text_normalized": text.lower().strip() if text else None,
        "char_count": len(text) if text else 0,
        "token_count": len(text.split()) if text else 0,
        "language": body.get("language", "en"),
        "activity_type": ingress_output.get("activity_type", "unknown"),
        "activity_category": ingress_output.get("activity_category", "episodic"),
        "is_meal": body.get("is_meal", False),
        "is_outing": body.get("is_outing", False),
        "ingress_source": ingress_output.get("ingress_source", "mobile_app"),
    }


def map_hippocampus_group(dg_output: Dict[str, Any], ca1_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Hippocampus: Pattern Separation & Novelty columns (8 columns)

    From: M01 pattern_separate + M02 semantic_project

    NOTE: CA3 deferred columns (is_near_duplicate, episode_cluster_id, etc.)
    are set to NULL in P02 and populated by P03 consolidation pipeline.
    """
    return {
        "simhash_hex": dg_output.get("simhash_hex"),
        "minhash32": dg_output.get("minhash32"),
        # CA3 outputs (deferred to P03)
        "novelty_score": None,
        "near_duplicates_json": None,
        "is_near_duplicate": None,
        "episode_cluster_id": None,
        "cluster_confidence": None,
        "clustering_version": None,
    }


def map_embeddings_kg_group(ca1_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Embeddings & Knowledge Graph columns (4 columns)

    From: M02 semantic_project
    """
    return {
        "embedding_id": ca1_output.get("embedding_id"),
        "embedding_status": "PENDING",  # P08 will update to IN_PROGRESS/READY
        "entities_json": serialize_to_json(ca1_output.get("entities", []), "entities_json"),
        "kg_triples_json": serialize_to_json(ca1_output.get("kg_triples", []), "kg_triples_json"),
    }


def map_affect_salience_group(
    affect_output: Dict[str, Any], salience_output: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Affect & Salience columns (9 columns)

    From: M04 affect.analyze + M06 salience.score
    """
    # Map affect_valence to sentiment_score for backward compat
    valence = affect_output.get("valence")  # Key is "valence" not "affect_valence"
    arousal = affect_output.get("arousal")  # Key is "arousal" not "affect_arousal"
    sentiment_label = None
    if valence is not None:
        if valence >= 0.2:
            sentiment_label = "positive"
        elif valence <= -0.2:
            sentiment_label = "negative"
        else:
            sentiment_label = "neutral"

    return {
        "sentiment_score": valence,  # affect_valence IS sentiment_score
        "sentiment_label": sentiment_label,
        "dominant_emotions_json": serialize_to_json(
            affect_output.get("dominant_emotions", []), "dominant_emotions_json"
        ),
        "affect_valence": valence,
        "affect_arousal": arousal,
        "affect_band": affect_output.get("affect_band", "GREEN"),
        "salience_score": salience_output.get("salience_score", 0.0),
        "salience_reasons_json": serialize_to_json(
            salience_output.get("salience_reasons", []), "salience_reasons_json"
        ),
        "salience_band": salience_output.get("salience_band", "LOW"),
    }


# =============================================================================
# Validation
# =============================================================================


def validate_required_fields(row: Dict[str, Any]) -> None:
    """
    Validate all NOT NULL columns are present and non-null.

    Raises:
        ValueError: If validation fails
    """
    required_fields = [
        "event_id",
        "wal_pos",
        "tenant_id",
        "space_id",
        "policy_decision",
        "policy_band",
        "owner_id",
        "retention_policy_id",
        "actor_id",
        "device_id",
        "event_time_utc",
        "write_time_utc",
        "simhash_hex",
        "minhash32",
        "embedding_id",
        "salience_score",
    ]

    for field_name in required_fields:
        if field_name not in row or row[field_name] is None:
            _metrics.validation_failures += 1
            raise ValueError(f"Missing required field: {field_name}")


def validate_value_ranges(row: Dict[str, Any]) -> None:
    """
    Validate value ranges for numeric columns.

    Raises:
        ValueError: If validation fails
    """
    # Affect columns: [-1.0, 1.0] or [0.0, 1.0] depending on column
    if row.get("affect_valence") is not None:
        val = row["affect_valence"]
        if not (-1.0 <= val <= 1.0):
            _metrics.validation_failures += 1
            raise ValueError(f"affect_valence out of range: {val}")

    if row.get("affect_arousal") is not None:
        val = row["affect_arousal"]
        if not (0.0 <= val <= 1.0):
            _metrics.validation_failures += 1
            raise ValueError(f"affect_arousal out of range: {val}")

    # Salience score: [0.0, 1.0]
    if row.get("salience_score") is not None:
        val = row["salience_score"]
        if not (0.0 <= val <= 1.0):
            _metrics.validation_failures += 1
            raise ValueError(f"salience_score out of range: {val}")

    # Sentiment score: [-1.0, 1.0]
    if row.get("sentiment_score") is not None:
        val = row["sentiment_score"]
        if not (-1.0 <= val <= 1.0):
            _metrics.validation_failures += 1
            raise ValueError(f"sentiment_score out of range: {val}")


def validate_enum_values(row: Dict[str, Any]) -> None:
    """
    Validate enum column values match allowed sets.

    Raises:
        ValueError: If validation fails
    """
    band_values = {"GREEN", "AMBER", "RED"}
    if row.get("policy_band") and row["policy_band"] not in band_values:
        _metrics.validation_failures += 1
        raise ValueError(f"Invalid policy_band: {row['policy_band']}")

    if row.get("affect_band") and row["affect_band"] not in band_values:
        _metrics.validation_failures += 1
        raise ValueError(f"Invalid affect_band: {row['affect_band']}")

    salience_band_values = {"HIGH", "MED", "LOW"}
    if row.get("salience_band") and row["salience_band"] not in salience_band_values:
        _metrics.validation_failures += 1
        raise ValueError(f"Invalid salience_band: {row['salience_band']}")


# =============================================================================
# Main Assembly Function
# =============================================================================


async def run(message: Any, context: Any, **config: Any) -> Dict[str, Any]:
    """
    Assemble complete st_hipp_events row from all enrichment module outputs.

    **Phase 2 Signature**:
        message: BusMessage with .payload (envelope JSON) and .trace_id
        context: PipelineContext with .logger and .syscalls
        **config: Stage configuration
            - validate_required_fields (bool): Enable validation (default: True)

    **Required Inputs** (from envelope['outputs'] or envelope['body']):
    - pattern_separate (M01): simhash_hex, minhash32
    - semantic_project (M02): entities, kg_triples, embedding_id
    - policy_stamp (M03): effective_band, obligations
    - affect_analyze (M04): valence, arousal, sentiment, emotions
    - space_resolve (M05): owner_id, visible_to, visibility_scope
    - salience_score (M06): salience_score, salience_reasons, salience_band
    - family_graph_resolve (M07): social_context, participant_roles
    - temporal_profile (M08): 11 temporal columns
    - device_profile (M09): device_kind, device_os
    - ingress_classify (M10): ingress_topic, activity_type
    - retention_lookup (M11): retention_policy_id, retention_bucket
    - geo_metadata (M12): geohash_6, location_name
    - spatial_minimal (M15): truncated geohash

    Returns:
        Enriched envelope with "hipp_events_row" containing 60-70 columns

    Raises:
        ValueError: If validation fails or required fields missing
    """
    import json

    # Use enriched envelope from pipeline_runner, with fallback to message.payload
    envelope = config.get("envelope")
    if envelope is None:
        # Fallback: parse from message.payload (only for first stage or if enrichment fails)
        envelope = (
            json.loads(message.payload)
            if isinstance(message.payload, (str, bytes))
            else message.payload
        )

    # Extract configuration
    validate_fields = config.get("validate_required_fields", True)

    # Log start
    context.logger.debug(
        "M13 hipp_events_row starting",
        extra={
            "trace_id": message.trace_id,
            "cognitive_trace_id": envelope.get("cognitive_trace_id"),
        },
    )

    # Extract module outputs from envelope (flat P02 structure - enrichments at top level)
    dg_output = {
        "simhash_hex": envelope.get("simhash_hex"),
        "minhash32": envelope.get("minhash32"),
    }
    ca1_output = {
        "embedding_id": envelope.get("embedding_id"),
        "entities_json": envelope.get("entities_json"),
        "kg_triples_json": envelope.get("kg_triples_json"),
    }
    policy_output = envelope.get("policy_stamp", {})

    # Debug: Check if affect fields are in envelope
    affect_keys_present = [
        k
        for k in ["affect_valence", "affect_arousal", "dominant_emotions", "affect_band"]
        if k in envelope
    ]
    if not affect_keys_present:
        context.logger.warning(
            f"M13 builder: NO AFFECT FIELDS in envelope! Keys present: {list(envelope.keys())[:30]}"
        )

    affect_output = {
        "valence": envelope.get("affect_valence"),
        "arousal": envelope.get("affect_arousal"),
        "dominant_emotions": envelope.get("dominant_emotions"),
        "affect_band": envelope.get("affect_band"),
        "band_reasons": envelope.get("band_reasons"),
        "model_version": envelope.get("model_version"),
        "confidence": envelope.get("confidence"),
    }
    # M05 space.resolve_visibility returns flattened fields at envelope top level
    space_output = {
        "owner_id": envelope.get("owner_id"),
        "co_owners": envelope.get("co_owners_json"),
        "visible_to": envelope.get("visible_to_json"),
        "visibility_scope": envelope.get("visibility_scope"),
        "effective_space_id": envelope.get("space_id"),  # May be enriched later
    }

    salience_output = {"salience_score": envelope.get("salience_score")}
    social_output = {
        "num_participants": envelope.get("num_participants"),
        "social_context": envelope.get("social_context"),
        "participant_roles_json": envelope.get("participant_roles_json"),
    }
    temporal_output = {
        k: envelope.get(k)
        for k in [
            "event_time_utc",
            "write_time_utc",
            "write_lag_ms",
            "local_date",
            "local_time",
            "day_of_week",
            "is_weekend",
            "time_of_day_bucket",
            "circadian_slot",
            "is_backdated",
        ]
    }
    device_output = {
        "device_kind": envelope.get("device_kind"),
        "device_os": envelope.get("device_os"),
    }
    ingress_output = {"ingress_channel": envelope.get("ingress_channel")}
    retention_output = {
        "retention_policy_id": envelope.get("retention_policy_id"),
        "retention_bucket": envelope.get("retention_bucket"),
    }
    geo_output = {
        "geo_precision_external": envelope.get("geo_precision_external"),
        "geo_masking_reason": envelope.get("geo_masking_reason"),
    }
    spatial_output = {
        "geohash_6": envelope.get("geohash_6"),
        "location_name": envelope.get("location_name"),
    }

    # Assemble row by column groups (9 groups)
    row = {}

    # Group 1: Identity & Trace (9 columns)
    row.update(map_identity_group(envelope, space_output))
    _metrics.column_group_counts["identity"] = _metrics.column_group_counts.get("identity", 0) + 1

    # Group 2: Integrity & Audit (6 columns)
    row.update(map_integrity_group(envelope))
    _metrics.column_group_counts["integrity"] = _metrics.column_group_counts.get("integrity", 0) + 1

    # Group 3: Policy & Visibility (10 columns)
    row.update(map_policy_group(envelope, policy_output, space_output, retention_output))
    _metrics.column_group_counts["policy"] = _metrics.column_group_counts.get("policy", 0) + 1

    # Group 4: Actor & Device (6 columns)
    row.update(map_actor_device_group(envelope, device_output, ingress_output))
    _metrics.column_group_counts["actor_device"] = (
        _metrics.column_group_counts.get("actor_device", 0) + 1
    )

    # Group 5: Temporal (11 columns)
    row.update(map_temporal_group(temporal_output))
    _metrics.column_group_counts["temporal"] = _metrics.column_group_counts.get("temporal", 0) + 1

    # Group 6: Spatial & Place (5 columns)
    row.update(map_spatial_group(geo_output, spatial_output))
    _metrics.column_group_counts["spatial"] = _metrics.column_group_counts.get("spatial", 0) + 1

    # Group 7: Social & Relationships (7 columns)
    row.update(map_social_group(envelope, social_output))
    _metrics.column_group_counts["social"] = _metrics.column_group_counts.get("social", 0) + 1

    # Group 8: Semantic & Activity (9 columns)
    row.update(map_semantic_activity_group(envelope, ingress_output))
    _metrics.column_group_counts["semantic_activity"] = (
        _metrics.column_group_counts.get("semantic_activity", 0) + 1
    )

    # Group 9: Hippocampus (8 columns)
    row.update(map_hippocampus_group(dg_output, ca1_output))
    _metrics.column_group_counts["hippocampus"] = (
        _metrics.column_group_counts.get("hippocampus", 0) + 1
    )

    # Group 10: Embeddings & KG (4 columns)
    row.update(map_embeddings_kg_group(ca1_output))
    _metrics.column_group_counts["embeddings_kg"] = (
        _metrics.column_group_counts.get("embeddings_kg", 0) + 1
    )

    # Group 11: Affect & Salience (9 columns)
    row.update(map_affect_salience_group(affect_output, salience_output))
    _metrics.column_group_counts["affect_salience"] = (
        _metrics.column_group_counts.get("affect_salience", 0) + 1
    )

    # Conditional validation based on config
    if validate_fields:
        validate_required_fields(row)
        validate_value_ranges(row)
        validate_enum_values(row)

    _metrics.rows_built += 1

    # Log completion
    context.logger.debug(
        "M13 hipp_events_row completed",
        extra={"trace_id": message.trace_id, "columns": len(row), "validated": validate_fields},
    )

    # Return ONLY the new enrichment (hipp_events_row key)
    # Pipeline runner will merge this into shared envelope
    return {"hipp_events_row": row}


# =============================================================================
# Metrics & Observability
# =============================================================================


def get_metrics() -> Dict[str, Any]:
    """Return current metrics for observability"""
    return {
        "rows_built": _metrics.rows_built,
        "json_serialization_ms_total": round(_metrics.json_serialization_ms, 4),
        "json_serialization_ms_avg": round(
            _metrics.json_serialization_ms / max(_metrics.rows_built, 1), 4
        ),
        "validation_failures": _metrics.validation_failures,
        "column_group_counts": _metrics.column_group_counts,
        "missing_optional_fields": _metrics.missing_optional_fields,
    }


def reset_metrics() -> None:
    """Reset metrics (for testing)"""
    global _metrics
    _metrics = BuilderMetrics()
