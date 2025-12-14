"""
Enrichment Helper Utilities

Provides utility functions for accessing and managing module enrichments
in envelopes. Supports both nested and flat structures during migration.

Phase 1 of Envelope Enrichment Structure Migration Plan.
See: docs/plans/envelope_enrichment_migration_plan.md

Author: Intelligence Kernel Team
Date: 2025-12-12
"""

from typing import Any


def get_enrichment(
    envelope: dict[str, Any],
    module_name: str,
    field: str | None = None,
    default: Any = None,
) -> Any:
    """
    Get enrichment value with fallback to flat structure.

    Supports dual-mode access during migration:
    1. Try nested structure: envelope["enrichments"][module_name][field]
    2. Fallback to flat: envelope[flat_field_name]

    Args:
        envelope: Envelope dict with enrichments
        module_name: Module enrichment key (e.g., "affect_analyzer")
        field: Specific field to extract (optional, returns whole enrichment if None)
        default: Default value if not found

    Returns:
        Enrichment value or default

    Examples:
        >>> # Nested access
        >>> valence = get_enrichment(envelope, "affect_analyzer", "valence", default=0.5)

        >>> # Get whole enrichment
        >>> affect = get_enrichment(envelope, "affect_analyzer")

        >>> # Fallback to flat
        >>> # If nested doesn't exist, tries envelope["affect_valence"]
    """
    # Try nested structure first
    enrichments = envelope.get("enrichments", {})
    if module_name in enrichments:
        if field is None:
            return enrichments[module_name]
        return enrichments[module_name].get(field, default)

    # Fallback to flat structure (backward compatibility)
    if field is None:
        # Can't extract whole enrichment from flat, return default
        return default

    # Map common module names to flat field prefixes
    flat_prefix_map = {
        "affect_analyzer": "affect_",
        "salience_scorer": "salience_",
        "hippocampus_pattern_separate": "",  # simhash_hex, minhash32 (no prefix)
        "hippocampus_semantic_project": "",  # entities_json, kg_triples_json, embedding_id
        "space_resolver": "",  # Various space fields
        "temporal_profiler": "",  # event_time_utc, write_time_utc, etc.
        "device_profiler": "device_",
        "ingress_classifier": "activity_",
        "social_resolver": "",  # participants_json, social_context
        "geo_metadata": "geo_",
        "spatial_resolver": "location_",
    }

    prefix = flat_prefix_map.get(module_name, "")
    flat_key = f"{prefix}{field}" if prefix else field

    return envelope.get(flat_key, default)


def set_enrichment(
    envelope: dict[str, Any],
    module_name: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """
    Set enrichment in nested structure.

    Creates enrichments namespace if needed and merges module data.

    Args:
        envelope: Envelope dict to update
        module_name: Module enrichment key (e.g., "affect_analyzer")
        data: Module enrichment data

    Returns:
        Updated envelope dict

    Example:
        >>> result = set_enrichment(envelope, "affect_analyzer", {
        ...     "valence": 0.9,
        ...     "arousal": 0.5,
        ...     "module_version": "v1"
        ... })
    """
    if "enrichments" not in envelope:
        envelope["enrichments"] = {}

    envelope["enrichments"][module_name] = data
    return envelope


def has_enrichment(envelope: dict[str, Any], module_name: str) -> bool:
    """
    Check if module enrichment exists (nested structure only).

    Args:
        envelope: Envelope dict
        module_name: Module enrichment key

    Returns:
        True if enrichment exists in nested structure
    """
    enrichments = envelope.get("enrichments", {})
    return module_name in enrichments


def validate_enrichment_schema(
    enrichment: dict[str, Any],
    required_fields: list[str],
    module_name: str,
) -> None:
    """
    Validate enrichment has required fields.

    Args:
        enrichment: Module enrichment data
        required_fields: List of required field names
        module_name: Module name (for error messages)

    Raises:
        ValueError: If validation fails

    Example:
        >>> validate_enrichment_schema(
        ...     enrichment,
        ...     ["valence", "arousal", "module_version"],
        ...     "affect_analyzer"
        ... )
    """
    for field in required_fields:
        if field not in enrichment:
            raise ValueError(f"Module '{module_name}' enrichment missing required field: '{field}'")


def extract_flat_enrichments(envelope: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """
    Extract enrichments from flat envelope structure.

    Used by event_emitter as fallback when nested enrichments don't exist.
    Maps flat fields to nested enrichment structure.

    Args:
        envelope: Envelope with flat fields

    Returns:
        Dict of module enrichments: {module_name: {fields...}}

    Example:
        >>> enrichments = extract_flat_enrichments(envelope)
        >>> affect = enrichments.get("affect_analyzer")
        >>> valence = affect.get("valence")
    """
    enrichments = {}

    # Extract affect_analyzer enrichment
    if "affect_valence" in envelope or "affect_arousal" in envelope:
        enrichments["affect_analyzer"] = {
            "valence": envelope.get("affect_valence"),
            "arousal": envelope.get("affect_arousal"),
            "dominant_emotions": envelope.get("dominant_emotions", []),
            "band": envelope.get("affect_band"),
            "clinical_safety_risk": envelope.get("clinical_safety_risk", False),
            "clinical_safety_severity": envelope.get("clinical_safety_severity"),
        }

    # Extract salience_scorer enrichment
    if "salience_score" in envelope:
        enrichments["salience_scorer"] = {
            "score": envelope.get("salience_score"),
            "band": envelope.get("salience_band"),
            "reasons": envelope.get("salience_reasons", []),
        }

    # Extract space_resolver enrichment
    if "space_id" in envelope:
        enrichments["space_resolver"] = {
            "space_id": envelope.get("space_id"),
            "tenant_id": envelope.get("tenant_id"),
            "effective_space_id": envelope.get("effective_space_id"),
            "visibility_scope": envelope.get("visibility_scope"),
            "visible_to": envelope.get("visible_to_json") or envelope.get("visible_to", []),
            "owner_id": envelope.get("owner_id"),
        }

    # Extract hippocampus_pattern_separate enrichment
    if "simhash_hex" in envelope:
        enrichments["hippocampus_pattern_separate"] = {
            "simhash_hex": envelope.get("simhash_hex"),
            "minhash32": envelope.get("minhash32"),
        }

    # Extract hippocampus_semantic_project enrichment
    if "embedding_id" in envelope:
        enrichments["hippocampus_semantic_project"] = {
            "embedding_id": envelope.get("embedding_id"),
            "embedding_status": envelope.get("embedding_status"),
            "entities_json": envelope.get("entities_json"),
            "kg_triples_json": envelope.get("kg_triples_json"),
        }

    # Extract temporal_profiler enrichment
    if "event_time_utc" in envelope:
        enrichments["temporal_profiler"] = {
            "event_time_utc": envelope.get("event_time_utc"),
            "write_time_utc": envelope.get("write_time_utc"),
            "local_date": envelope.get("local_date"),
            "local_time": envelope.get("local_time"),
            "time_of_day_bucket": envelope.get("time_of_day_bucket"),
        }

    # Extract device_profiler enrichment
    if "device_id" in envelope:
        enrichments["device_profiler"] = {
            "device_id": envelope.get("device_id"),
            "device_kind": envelope.get("device_kind"),
            "device_os": envelope.get("device_os"),
        }

    # Extract social_resolver enrichment
    if "social_context" in envelope or "participants_json" in envelope:
        enrichments["social_resolver"] = {
            "social_context": envelope.get("social_context"),
            "social_intimacy": envelope.get("social_intimacy"),
            "participants_json": envelope.get("participants_json"),
            "num_participants": envelope.get("num_participants", 0),
        }

    # Extract ingress_classifier enrichment
    if "activity_type" in envelope:
        enrichments["ingress_classifier"] = {
            "activity_type": envelope.get("activity_type"),
            "activity_category": envelope.get("activity_category"),
        }

    # Extract hipp_row_builder enrichment (if hipp_events_row was populated)
    if "event_id" in envelope and "cognitive_trace_id" in envelope:
        enrichments["hipp_row_builder"] = {
            "event_id": envelope.get("event_id"),
            "cognitive_trace_id": envelope.get("cognitive_trace_id"),
        }

    return enrichments


def merge_flat_and_nested(
    envelope: dict[str, Any],
    module_output: dict[str, Any],
    module_name: str,
) -> dict[str, Any]:
    """
    Merge module output into both flat and nested structures (dual-mode).

    During migration, modules can return enrichment data which gets
    written to both locations for backward compatibility.

    Args:
        envelope: Existing envelope
        module_output: Module's returned enrichment data
        module_name: Module enrichment key

    Returns:
        Updated envelope with both flat and nested enrichments

    Example:
        >>> envelope = merge_flat_and_nested(
        ...     envelope,
        ...     {"valence": 0.9, "arousal": 0.5},
        ...     "affect_analyzer"
        ... )
        >>> # Creates both envelope["affect_valence"] and
        >>> # envelope["enrichments"]["affect_analyzer"]["valence"]
    """
    # Set nested structure
    set_enrichment(envelope, module_name, module_output)

    # Also set flat fields for backward compatibility (temporary during migration)
    flat_map = {
        "affect_analyzer": {
            "valence": "affect_valence",
            "arousal": "affect_arousal",
            "band": "affect_band",
            "dominant_emotions": "dominant_emotions",
        },
        "salience_scorer": {
            "score": "salience_score",
            "band": "salience_band",
            "reasons": "salience_reasons",
        },
    }

    if module_name in flat_map:
        for nested_key, flat_key in flat_map[module_name].items():
            if nested_key in module_output:
                envelope[flat_key] = module_output[nested_key]

    return envelope
