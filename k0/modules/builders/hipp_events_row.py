"""
Hippocampus Events Row Builder Module (M13)

Assembles complete st_hipp_events row from all enrichment module outputs.

**Purpose**: Convergence point for P02 write pipeline - maps 13 module outputs
to 60-70 column st_hipp_events table structure.

**Performance**: <10ms P95 (pure assembly, no I/O)

**Contract**: k0/contracts/modules/builders.hipp_events_row.v1.yaml
**ADR**: docs/architecture/decisions-K0/modules/k009.1-hipp-events-builder.md
**Schema**: docs/pipelines/P02_data_schema.md (lines 45-185)

**Inputs** (from 14 enrichment modules):
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
- M22 (Embedding Extract): embedding, embedding_id, vector_dim, model_id, source (ADR-K003)

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

    Note: visible_to_json and co_owners_json from space module are already JSON strings.
    We must NOT double-encode them.
    """
    policy_stamp = envelope.get("policy_stamp", {})

    # Handle visible_to_json - may already be JSON string from M05 space.resolve_visibility
    visible_to = space_output.get("visible_to_json") or space_output.get("visible_to")
    if visible_to is None:
        visible_to_json = "[]"
    elif isinstance(visible_to, str):
        # Already a JSON string - use as-is
        visible_to_json = visible_to
    else:
        # List/tuple - serialize it
        visible_to_json = serialize_to_json(visible_to, "visible_to_json")

    # Handle co_owners_json - may already be JSON string from M05 space.resolve_visibility
    co_owners = space_output.get("co_owners_json") or space_output.get("co_owners")
    if co_owners is None:
        co_owners_json = "[]"
    elif isinstance(co_owners, str):
        # Already a JSON string - use as-is
        co_owners_json = co_owners
    else:
        # List/tuple - serialize it
        co_owners_json = serialize_to_json(co_owners, "co_owners_json")

    return {
        "policy_decision": policy_stamp.get("decision", "ALLOW"),
        "policy_band": envelope.get("band", "GREEN"),  # band is at envelope root level
        "policy_version": policy_stamp.get("version", envelope.get("policy_version", "1.0.0")),
        "obligations_json": serialize_to_json(
            policy_output.get("obligations", []), "obligations_json"
        ),
        "visible_to_json": visible_to_json,
        "visibility_scope": space_output.get("visibility_scope", "SPACE_DEFAULT"),
        "owner_id": space_output.get("owner_id"),
        "co_owners_json": co_owners_json,
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
    # device_os can come from device_output.device_os or device_output.device_platform
    # or fallback to envelope.device.os
    device_os = (
        device_output.get("device_os")
        or device_output.get("device_platform")
        or envelope.get("device", {}).get("os")
    )

    return {
        "actor_id": envelope.get("actor"),  # Aligned with Envelope schema
        "actor_role": envelope.get("actor_role", "SELF"),
        "device_id": envelope.get("device_id"),
        "device_kind": device_output.get("device_kind", "unknown"),
        "device_os": device_os,
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

    Note: participants_json and participant_roles_json may already be JSON strings
    from M07 family_graph_resolve. We must NOT double-encode them.
    """
    body = envelope.get("body", {})
    participants = body.get("participants", [])

    # Handle participants_json - may already be JSON string from M07
    participants_json_raw = social_output.get("participants_json")
    if participants_json_raw is not None and isinstance(participants_json_raw, str):
        # Already a JSON string - use as-is
        participants_json = participants_json_raw
    elif participants:
        # Have participants list from body - serialize it
        participants_json = serialize_to_json(participants, "participants_json")
    else:
        participants_json = "[]"

    # Handle participant_roles_json - may already be JSON string from M07
    participant_roles_json = social_output.get("participant_roles_json")
    if participant_roles_json is None:
        participant_roles_json = "{}"
    elif not isinstance(participant_roles_json, str):
        # Not a string - serialize it
        participant_roles_json = serialize_to_json(participant_roles_json, "participant_roles_json")
    # else: already a JSON string - use as-is

    return {
        "participants_json": participants_json,
        "num_participants": social_output.get("num_participants", len(participants)),
        "has_partner_present": social_output.get("has_partner_present", False),
        "has_parent_present": social_output.get("has_parent_present", False),
        "is_solo_event": social_output.get("is_solo_event", len(participants) <= 1),
        "participant_roles_json": participant_roles_json,
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


def map_embeddings_kg_group(
    ca1_output: Dict[str, Any], embedding_output: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Embeddings & Knowledge Graph columns (6 columns)

    From: M02 semantic_project (entities, kg_triples)
          M22 extract_from_cache (embedding, embedding_id, status)

    ADR-K003: Inline embedding via M22 (UltraBERT cache extraction)
    - embedding_status = READY if M22 returned embedding
    - embedding_status = PENDING if M22 failed (no text, model unavailable, etc.)
    """
    # entities_json and kg_triples_json are already JSON strings from semantic_project
    entities_json = ca1_output.get("entities_json")
    kg_triples_json = ca1_output.get("kg_triples_json")

    # If they're None, use empty array string
    if entities_json is None:
        entities_json = "[]"
    if kg_triples_json is None:
        kg_triples_json = "[]"

    # M22 embedding data (ADR-K003)
    embedding_id = embedding_output.get("embedding_id") or ca1_output.get("embedding_id")
    embedding_exists = embedding_output.get("embedding") is not None
    embedding_status = "READY" if embedding_exists else "PENDING"

    return {
        "embedding_id": embedding_id,
        "embedding_status": embedding_status,
        "entities_json": entities_json,
        "kg_triples_json": kg_triples_json,
    }


def map_affect_salience_group(
    affect_output: Dict[str, Any], salience_output: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Affect & Salience columns (9 columns)

    From: M04 affect.analyze + M06 salience.score

    Clinical Safety Integration (Issue 3.1.2):
    - affect_band: Overridden to RED/AMBER by M04 if clinical risk detected
    - salience_score: Boosted when clinical safety risk present
    - salience_reasons_json: Includes clinical_safety_* reasons
    - dominant_emotions_json: May include crisis-related emotions
    """
    # Map affect_valence to sentiment_score for backward compat
    # Note: Valence is on 0-1 scale where 0=negative, 0.5=neutral, 1=positive
    valence = affect_output.get("valence")  # Key is "valence" not "affect_valence"
    arousal = affect_output.get("arousal")  # Key is "arousal" not "affect_arousal"
    sentiment_label = None
    if valence is not None:
        if valence >= 0.6:
            sentiment_label = "positive"
        elif valence <= 0.4:
            sentiment_label = "negative"
        else:
            sentiment_label = "neutral"

    # Get base salience from M06
    base_salience = salience_output.get("salience_score", 0.0)
    salience_reasons = list(salience_output.get("salience_reasons", []))
    salience_band = salience_output.get("salience_band", "LOW")

    # Clinical safety integration: boost salience for safety-critical content
    clinical_safety_risk = affect_output.get("clinical_safety_risk", False)
    clinical_safety_severity = affect_output.get("clinical_safety_severity")

    if clinical_safety_risk and clinical_safety_severity:
        # Add clinical safety to salience reasons
        salience_reasons.append(f"clinical_safety_{clinical_safety_severity.lower()}")

        # Boost salience score based on severity (safety = high importance)
        # CRITICAL: force to 1.0, HIGH: min 0.9, MEDIUM: min 0.7, LOW: min 0.5
        severity_boost = {
            "CRITICAL": 1.0,
            "HIGH": 0.9,
            "MEDIUM": 0.7,
            "LOW": 0.5,
        }
        min_salience = severity_boost.get(clinical_safety_severity, base_salience)
        base_salience = max(base_salience, min_salience)

        # Upgrade salience band for clinical safety
        if clinical_safety_severity in ("CRITICAL", "HIGH"):
            salience_band = "HIGH"
        elif clinical_safety_severity == "MEDIUM" and salience_band == "LOW":
            salience_band = "MED"

    # Get dominant emotions, potentially enriched with crisis indicators
    dominant_emotions = affect_output.get("dominant_emotions", [])
    if clinical_safety_risk and clinical_safety_severity in ("CRITICAL", "HIGH"):
        # Add crisis emotion if not already present
        if "crisis" not in dominant_emotions and "distress" not in dominant_emotions:
            dominant_emotions = list(dominant_emotions) + ["distress"]

    return {
        "sentiment_score": valence,  # affect_valence IS sentiment_score
        "sentiment_label": sentiment_label,
        "dominant_emotions_json": serialize_to_json(dominant_emotions, "dominant_emotions_json"),
        "affect_valence": valence,
        "affect_arousal": arousal,
        "affect_band": affect_output.get("affect_band", "GREEN"),  # Already overridden by M04
        "salience_score": base_salience,
        "salience_reasons_json": serialize_to_json(salience_reasons, "salience_reasons_json"),
        "salience_band": salience_band,
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
        "embedding_status",
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

    # Extract module outputs from envelope (Phase 3: prefer nested, fallback to flat)
    enrichments = envelope.get("enrichments", {})

    # DG pattern separation (M01)
    dg_enrichment = enrichments.get("hippocampus_pattern_separate", {})
    # Nested returns array, flat returns JSON string - serialize if needed
    minhash_value = dg_enrichment.get("minhash32") or envelope.get("minhash32")
    if isinstance(minhash_value, list):
        minhash_value = serialize_to_json(minhash_value, "minhash32")
    dg_output = {
        "simhash_hex": dg_enrichment.get("simhash_hex") or envelope.get("simhash_hex"),
        "minhash32": minhash_value,
    }

    # CA1 semantic projection (M02)
    ca1_enrichment = enrichments.get("hippocampus_semantic_project", {})
    ca1_output = {
        "embedding_id": ca1_enrichment.get("embedding_id") or envelope.get("embedding_id"),
        "entities_json": ca1_enrichment.get("entities_json") or envelope.get("entities_json"),
        "kg_triples_json": ca1_enrichment.get("kg_triples_json") or envelope.get("kg_triples_json"),
    }

    # M22 embedding extraction (ADR-K003)
    # M22 wraps output under "extract_from_cache" key for namespace isolation
    # Pipeline runner merges M22 output into envelope as {"extract_from_cache": {...}}
    extract_from_cache = envelope.get("extract_from_cache", {})
    embedding_output = {
        "embedding": extract_from_cache.get("embedding") or envelope.get("embedding"),
        "embedding_id": extract_from_cache.get("embedding_id") or envelope.get("embedding_id"),
        "model_id": extract_from_cache.get("model_id")
        or envelope.get("model_id", "ultrabert_v2.1.0"),
        "vector_dim": extract_from_cache.get("vector_dim") or envelope.get("vector_dim", 768),
        "source": extract_from_cache.get("source") or envelope.get("source", "unknown"),
    }

    policy_output = envelope.get("policy_stamp", {})

    # Affect analysis (M04) - Phase 3: prefer nested, fallback to flat
    affect_enrichment = enrichments.get("affect_analyzer", {})
    affect_output = {
        "valence": affect_enrichment.get("valence") or envelope.get("affect_valence"),
        "arousal": affect_enrichment.get("arousal") or envelope.get("affect_arousal"),
        "dominant_emotions": affect_enrichment.get("dominant_emotions")
        or envelope.get("dominant_emotions"),
        "affect_band": affect_enrichment.get("band") or envelope.get("affect_band"),
        "band_reasons": affect_enrichment.get("band_reasons") or envelope.get("band_reasons"),
        "model_version": affect_enrichment.get("model_version") or envelope.get("model_version"),
        "confidence": affect_enrichment.get("confidence") or envelope.get("confidence"),
        "clinical_safety_risk": affect_enrichment.get("clinical_safety_risk")
        or envelope.get("clinical_safety_risk", False),
        "clinical_safety_severity": affect_enrichment.get("clinical_safety_severity")
        or envelope.get("clinical_safety_severity"),
    }
    # Space visibility (M05) - Phase 3: prefer nested, fallback to flat
    space_enrichment = enrichments.get("space_resolver", {})
    space_output = {
        "owner_id": space_enrichment.get("owner_id") or envelope.get("owner_id"),
        "co_owners": (
            serialize_to_json(space_enrichment.get("co_owners"), "co_owners")
            if space_enrichment.get("co_owners")
            else envelope.get("co_owners_json")
        ),
        "visible_to": (
            serialize_to_json(space_enrichment.get("visible_to"), "visible_to")
            if space_enrichment.get("visible_to")
            else envelope.get("visible_to_json")
        ),
        "visibility_scope": space_enrichment.get("visibility_scope")
        or envelope.get("visibility_scope"),
        "effective_space_id": envelope.get("space_id"),  # May be enriched later
    }

    # Salience scoring (M06) - Phase 3: prefer nested, fallback to flat
    salience_enrichment = enrichments.get("salience_scorer", {})

    # Handle reasons: nested gives array, flat gives JSON string
    if salience_enrichment.get("reasons"):
        salience_reasons = salience_enrichment.get("reasons", [])
    else:
        salience_reasons_json = envelope.get("salience_reasons_json", "[]")
        try:
            if isinstance(salience_reasons_json, str):
                salience_reasons = json.loads(salience_reasons_json)
            else:
                salience_reasons = salience_reasons_json or []
        except (json.JSONDecodeError, TypeError):
            salience_reasons = []

    salience_output = {
        "salience_score": salience_enrichment.get("score") or envelope.get("salience_score"),
        "salience_band": salience_enrichment.get("band") or envelope.get("salience_band", "LOW"),
        "salience_reasons": salience_reasons,
    }

    # M07 family_graph_resolve (still flat - not migrated yet)
    # M07 social.family_graph_resolve - Phase 4: prefer nested, fallback to flat
    social_enrichment = enrichments.get("social_resolver", {})
    social_output = {
        "num_participants": social_enrichment.get("num_participants")
        or envelope.get("num_participants"),
        "social_context": social_enrichment.get("social_context") or envelope.get("social_context"),
        "participant_roles_json": social_enrichment.get("participant_roles_json")
        or envelope.get("participant_roles_json"),
        "has_partner_present": (
            social_enrichment.get("has_partner_present")
            if social_enrichment.get("has_partner_present") is not None
            else envelope.get("has_partner_present", False)
        ),
        "has_parent_present": (
            social_enrichment.get("has_parent_present")
            if social_enrichment.get("has_parent_present") is not None
            else envelope.get("has_parent_present", False)
        ),
        "is_solo_event": (
            social_enrichment.get("is_solo_event")
            if social_enrichment.get("is_solo_event") is not None
            else envelope.get("is_solo_event", True)
        ),
        "social_intimacy": social_enrichment.get("social_intimacy")
        or envelope.get("social_intimacy", "LOW"),
    }

    # M08 temporal_profile - Phase 4: prefer nested, fallback to flat
    temporal_enrichment = enrichments.get("temporal_profiler", {})
    temporal_output = {
        "event_time_utc": temporal_enrichment.get("event_time_utc")
        or envelope.get("event_time_utc"),
        "write_time_utc": temporal_enrichment.get("write_time_utc")
        or envelope.get("write_time_utc"),
        "write_lag_ms": temporal_enrichment.get("write_lag_ms") or envelope.get("write_lag_ms"),
        "local_date": temporal_enrichment.get("local_date") or envelope.get("local_date"),
        "local_time": temporal_enrichment.get("local_time") or envelope.get("local_time"),
        "day_of_week": temporal_enrichment.get("day_of_week") or envelope.get("day_of_week"),
        "is_weekend": (
            temporal_enrichment.get("is_weekend")
            if temporal_enrichment.get("is_weekend") is not None
            else envelope.get("is_weekend")
        ),
        "time_of_day_bucket": temporal_enrichment.get("time_of_day_bucket")
        or envelope.get("time_of_day_bucket"),
        "circadian_slot": temporal_enrichment.get("circadian_slot")
        or envelope.get("circadian_slot"),
        "is_backdated": (
            temporal_enrichment.get("is_backdated")
            if temporal_enrichment.get("is_backdated") is not None
            else envelope.get("is_backdated")
        ),
    }

    # M09 device_profile - Phase 4: prefer nested, fallback to flat
    device_enrichment = enrichments.get("device_profiler", {})
    device_output = {
        "device_kind": device_enrichment.get("device_kind") or envelope.get("device_kind"),
        "device_os": device_enrichment.get("device_platform") or envelope.get("device_os"),
    }

    # M10 ingress_classify - Phase 4: prefer nested, fallback to flat
    ingress_enrichment = enrichments.get("ingress_classifier", {})
    ingress_output = {
        "ingress_channel": ingress_enrichment.get("ingress_topic")
        or envelope.get("ingress_topic", envelope.get("ingress_channel")),
        "ingress_topic": ingress_enrichment.get("ingress_topic") or envelope.get("ingress_topic"),
        "activity_type": ingress_enrichment.get("activity_type")
        or envelope.get("activity_type", "unknown"),
        "activity_category": ingress_enrichment.get("content_type")
        or envelope.get("content_type", "episodic"),
        "ingress_source": ingress_enrichment.get("ingress_source")
        or envelope.get("ingress_source", "mobile_app"),
    }

    # M11 retention_lookup - Phase 4: prefer nested, fallback to flat
    retention_enrichment = enrichments.get("retention_policy", {})
    retention_output = {
        "retention_policy_id": retention_enrichment.get("retention_policy_id")
        or envelope.get("retention_policy_id"),
        "retention_bucket": retention_enrichment.get("retention_bucket")
        or envelope.get("retention_bucket"),
    }

    # M12 geo_metadata - Phase 4: prefer nested, fallback to flat
    geo_enrichment = enrichments.get("geo_metadata", {})
    geo_output = {
        "geo_precision_external": geo_enrichment.get("geo_precision_external")
        or envelope.get("geo_precision_external"),
        "geo_masking_reason": geo_enrichment.get("geo_masking_reason")
        or envelope.get("geo_masking_reason"),
    }

    # M15 spatial_minimal - Phase 4: prefer nested, fallback to flat
    spatial_enrichment = enrichments.get("spatial_resolver", {})
    spatial_output = {
        "geohash_6": spatial_enrichment.get("geohash_6") or envelope.get("geohash_6"),
        "location_name": spatial_enrichment.get("location_name") or envelope.get("location_name"),
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

    # Group 10: Embeddings & KG (6 columns) - ADR-K003: now includes M22 embedding data
    row.update(map_embeddings_kg_group(ca1_output, embedding_output))
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
