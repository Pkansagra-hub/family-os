"""
Epic 3.18 -- M13 builders.hipp_events_row Column Count Integration Tests

These tests call the REAL M13 run() with a complete envelope.
Only transport (MockMessage, MockContext) is mocked.

Validates:
- Complete envelope -> M13 run() -> correct column count (130)
- All 17 new v2+ column keys present
- No None for NOT NULL columns with defaults
- Validation passes for well-formed envelopes
"""

import json
import time
from datetime import datetime, timezone
from typing import Any
from unittest.mock import Mock

import pytest

from k0.modules.builders import hipp_events_row
from k0.modules.builders.hipp_events_row import run as m13_run

# ============================================================================
# Mock Transport
# ============================================================================


class MockMessage:
    """Mock BusMessage."""

    def __init__(self, payload: dict[str, Any], trace_id: str = "test-m13-col"):
        self.payload = json.dumps(payload)
        self.trace_id = trace_id
        self.offset = 0


class MockContext:
    """Mock PipelineContext."""

    def __init__(self):
        self.logger = Mock()
        self.logger.debug = Mock()
        self.logger.info = Mock()
        self.logger.warning = Mock()
        self.logger.error = Mock()
        self.syscalls = Mock()
        self.config = {}


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def reset_module_state():
    """Reset metrics before each test."""
    hipp_events_row.reset_metrics()
    yield
    hipp_events_row.reset_metrics()


def _complete_envelope() -> dict[str, Any]:
    """Build a COMPLETE envelope with all MW v2 fields populated.

    This simulates an envelope that has passed through all P02 stages:
    M02 (semantic), M04 (affect), M07 (social), M08 (temporal), M06 (salience)
    with MW v2 signals present.
    """
    now = int(time.time())
    now_iso = datetime.now(timezone.utc).isoformat()

    return {
        # Identity
        "cognitive_trace_id": "ct-m13-test-001",
        "event_id": "evt-m13-test-001",
        "tenant_id": "test-tenant",
        "space_id": "space-family",
        "topic": "cognitive.memory.write.committed.v1",
        "uow_id": "uow-001",
        "schema_version": "2.0.0",
        "wal_pos": 12345,
        # Integrity
        "envelope_sha256": "abc123def456",
        "sig_alg": "HMAC-SHA256",
        "sig_kid": "key-001",
        "idem_key": "idem-001",
        "ingested_at": now,
        "clock_skew_ms": 5,
        # Policy
        "band": "GREEN",
        "policy_stamp": {
            "decision": "ALLOW",
            "version": "2.0.0",
        },
        "policy_version": "2.0.0",
        # Actor & Device
        "actor": "actor-dad",
        "actor_id": "actor-dad",
        "actor_role": "SELF",
        "device_id": "device-001",
        "device": {"os": "iOS"},
        # Timestamps
        "ts": now,
        # Body (MW v2 full)
        "body": {
            "text": "Mom and I went to Olive Garden yesterday evening for dinner",
            "language": "en",
            "is_meal": True,
            "is_outing": True,
            "participants": ["actor-dad", "person-mom", "person-sharvi"],
            # MW v2 affect
            "affect": {
                "valence": 0.82,
                "arousal": 0.6,
                "dominance": 0.7,
                "dominant_emotions": ["joy", "contentment"],
            },
            # MW v2 participant_relationships
            "participant_relationships": [
                {"person": "Mom", "relationship_type": "PARENT_OF", "confidence": 0.95},
                {"person": "Sharvi", "relationship_type": "PARENT_OF", "confidence": 0.92},
            ],
            # MW v2 narrative
            "narrative": {
                "thread_id": "thread-uuid-001",
                "arc_position": "RISING_ACTION",
                "is_goal_event": False,
            },
            # MW v2 temporal
            "temporal": {
                "resolved_epoch_ms": 1704067200000,
                "mentioned_time": "yesterday evening",
                "orientation": "PAST",
            },
            # MW v2 location
            "location_name": "Olive Garden",
            "location_type": "restaurant",
            "location_hierarchy": ["restaurant", "Market St", "Seattle"],
            "transition_from_place": "home",
            "transition_mode": "drove",
            # MW v2 cognitive dimensions
            "intent_type": "log_memory",
            "goal_context": "family bonding",
            "source_type": "user_stated",
            "novelty": "EXPECTED",
            "elaboration_depth": "DISCUSSED",
            "identity_domains": ["family", "food"],
            "entity_salience": {"Mom": 0.9, "Olive Garden": 0.7},
            "k1_signal_version": "2.0",
            "extraction_sequence": 2,
        },
        # M02 outputs (semantic projection)
        "embedding_id": "emb-uuid-001",
        "entities_json": '["Mom", "Olive Garden"]',
        "kg_triples_json": '[["actor-dad", "PARENT_OF", "Mom"]]',
        "semantic_projected_at_utc": now_iso,
        "ner_entities_json": '{"ner_family": [], "ner_general": []}',
        "temporal_json": '{"temporal": []}',
        "intent_category": "memory",
        "ingress_category": "diary",
        "ultrabert_version": "v2.1.0",
        "extracted_relations_json": "[]",
        "safety_familyos_band": "GREEN",
        "safety_familyos_subcategory": None,
        "nli_label": None,
        "nli_confidence": None,
        "sentiment_confidence": 0.92,
        "ner_temporal_entities": [{"text": "yesterday evening", "type": "TEMPORAL"}],
        "ner_loc_entities": [{"text": "Olive Garden", "type": "LOC"}],
        "ner_per_entities": [{"text": "Mom", "type": "PER"}],
        # M01 outputs (pattern separation)
        "simhash_hex": "a1b2c3d4",
        "minhash32": "[1, 2, 3, 4]",
        # M04 outputs (affect)
        "affect_valence": 0.82,
        "affect_arousal": 0.6,
        "affect_dominance": 0.7,
        "dominant_emotions": ["joy", "contentment"],
        "affect_band": "GREEN",
        "band_reasons": ["positive_valence"],
        "model_version": "mw_v2_passthrough",
        "affect_tier": "MW_V2",
        "confidence": 0.9,
        "clinical_safety_risk": False,
        "clinical_safety_severity": None,
        "clinical_safety_summary": None,
        "affect_source": "mw_v2",
        # M07 outputs (social)
        "num_participants": 3,
        "participant_roles_json": '{"actor-dad": "SELF", "person-mom": "SPOUSE"}',
        "has_partner_present": True,
        "has_parent_present": True,
        "is_solo_event": False,
        "social_context": "nuclear_family",
        "social_intimacy": "HIGH",
        "social_resolved_at_utc": now_iso,
        "participant_relationships_json": json.dumps(
            [
                {"person": "Mom", "relationship_type": "PARENT_OF", "confidence": 0.95},
            ]
        ),
        "social_source": "mw_v2",
        # M08 outputs (temporal)
        "event_time_utc": now,
        "write_time_utc": now,
        "write_lag_ms": 50,
        "local_date": "2024-06-15",
        "local_time": "14:30:00",
        "day_of_week": "Saturday",
        "is_weekend": True,
        "time_of_day_bucket": "afternoon",
        "circadian_slot": "lunch",
        "is_backdated": False,
        "created_at": now,
        "timezone_used": "America/Chicago",
        "temporal_mentioned_time": "yesterday evening",
        "temporal_resolved_epoch_ms": 1704067200000,
        "temporal_orientation": "PAST",
        "temporal_source": "mw_resolved",
        "location_name": "Olive Garden",
        "location_type": "restaurant",
        "location_source": "mw_location",
        # M06 outputs (salience)
        "salience_score": 0.95,
        "salience_band": "HIGH",
        "salience_reasons_json": '["High social importance: nuclear_family"]',
        "component_scores_json": '{"social": 1.0, "affect": 0.93, "recency": 1.0}',
        "salience_computed_at_utc": now_iso,
        "entity_salience_discrepancy": 0.05,
        # M05 outputs (space)
        "owner_id": "actor-dad",
        "visible_to_json": '["actor-dad"]',
        "co_owners_json": "[]",
        "visibility_scope": "SPACE_DEFAULT",
        # M09 device
        "device_kind": "smartphone",
        "device_os": "iOS",
        # M10 ingress
        "ingress_topic": "write",
        "activity_type": "diary",
        "content_type": "episodic",
        "ingress_source": "mobile_app",
        # M11 retention
        "retention_policy_id": "policy-standard",
        "retention_bucket": "STANDARD",
        # M12 geo
        "geo_precision_external": "city",
        "geo_masking_reason": None,
        # M15 spatial
        "geohash_6": "9vk1h2",
        # Enrichments
        "enrichments": {
            "affect_analyzer": {
                "valence": 0.82,
                "arousal": 0.6,
                "dominance": 0.7,
                "dominant_emotions": ["joy", "contentment"],
                "band": "GREEN",
                "band_reasons": ["positive_valence"],
                "model_version": "mw_v2_passthrough",
                "tier": "MW_V2",
                "confidence": 0.9,
                "affect_source": "mw_v2",
                "clinical_safety_risk": False,
                "clinical_safety_severity": None,
                "module_version": "v2",
            },
            "salience_scorer": {
                "score": 0.95,
                "band": "HIGH",
                "reasons": ["High social importance"],
                "component_scores": {"social": 1.0, "affect": 0.93, "recency": 1.0},
                "module_version": "v2",
            },
        },
    }


# ============================================================================
# COLUMN COUNT
# ============================================================================


@pytest.mark.asyncio
async def test_complete_envelope_column_count():
    """Complete envelope -> M13 produces 130 columns."""
    envelope = _complete_envelope()
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m13_run(msg, ctx, envelope=envelope, validate_required_fields=False)

    row = result["hipp_events_row"]
    assert len(row) == 132, f"Expected 132 columns, got {len(row)}: {sorted(row.keys())}"


# ============================================================================
# V2 COLUMN KEYS PRESENT
# ============================================================================


V2_NEW_COLUMNS = [
    # Epic 3.15/4.1: Group 12 MW v2 signals (12)
    "narrative_thread_id",
    "narrative_arc_position",
    "narrative_is_goal_event",
    "intent_type",
    "goal_context",
    "source_type",
    "novelty",
    "elaboration_depth",
    "identity_domains_json",
    "entity_salience_json",
    "k1_signal_version",
    "extraction_sequence",
    # Epic 4.2: Spatial hierarchy (1)
    "location_hierarchy_json",
    # Epic 4.3: Spatial transition context (1)
    "spatial_context_json",
    # Epic 3.16: Existing group updates (5)
    "affect_dominance",
    "participant_relationships_json",
    "temporal_mentioned_time",
    "temporal_resolved_epoch_ms",
    "temporal_orientation",
]


@pytest.mark.asyncio
async def test_all_v2_column_keys_present():
    """All 17 new v2+ column keys are present in row."""
    envelope = _complete_envelope()
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m13_run(msg, ctx, envelope=envelope, validate_required_fields=False)
    row = result["hipp_events_row"]

    for col in V2_NEW_COLUMNS:
        assert col in row, f"Missing v2 column: {col}"


@pytest.mark.asyncio
async def test_v2_mw_signal_values():
    """MW v2 signal values are correctly mapped."""
    envelope = _complete_envelope()
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m13_run(msg, ctx, envelope=envelope, validate_required_fields=False)
    row = result["hipp_events_row"]

    assert row["narrative_thread_id"] == "thread-uuid-001"
    assert row["narrative_arc_position"] == "RISING_ACTION"
    assert row["narrative_is_goal_event"] is False
    assert row["intent_type"] == "log_memory"
    assert row["source_type"] == "user_stated"
    assert row["novelty"] == "EXPECTED"
    assert row["elaboration_depth"] == "DISCUSSED"
    assert row["k1_signal_version"] == "2.0"


@pytest.mark.asyncio
async def test_v2_affect_dominance_mapped():
    """affect_dominance from M04 v2 is mapped into row."""
    envelope = _complete_envelope()
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m13_run(msg, ctx, envelope=envelope, validate_required_fields=False)
    row = result["hipp_events_row"]

    assert row["affect_dominance"] == 0.7


@pytest.mark.asyncio
async def test_v2_temporal_orientation_mapped():
    """temporal_orientation from M08 v2 is mapped into row."""
    envelope = _complete_envelope()
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m13_run(msg, ctx, envelope=envelope, validate_required_fields=False)
    row = result["hipp_events_row"]

    assert row["temporal_orientation"] == "PAST"
    assert row["temporal_mentioned_time"] == "yesterday evening"
    assert row["temporal_resolved_epoch_ms"] == 1704067200000


# ============================================================================
# NOT NULL COLUMNS WITH DEFAULTS
# ============================================================================


@pytest.mark.asyncio
async def test_not_null_columns_have_defaults():
    """Columns with NOT NULL + DEFAULT constraints have non-None values."""
    envelope = _complete_envelope()
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m13_run(msg, ctx, envelope=envelope, validate_required_fields=False)
    row = result["hipp_events_row"]

    # Columns that should ALWAYS have values (NOT NULL with defaults)
    default_columns = {
        "k1_signal_version": "2.0",
        "policy_decision": "ALLOW",
        "policy_band": "GREEN",
        "retention_bucket": "STANDARD",
        "schema_version": "2.0.0",
        "narrative_is_goal_event": False,
    }

    for col, expected_default in default_columns.items():
        assert row.get(col) is not None, f"NOT NULL column {col} is None"


@pytest.mark.asyncio
async def test_json_columns_are_valid_json():
    """JSON columns contain valid JSON strings."""
    envelope = _complete_envelope()
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m13_run(msg, ctx, envelope=envelope, validate_required_fields=False)
    row = result["hipp_events_row"]

    json_columns = [
        "entities_json",
        "kg_triples_json",
        "salience_reasons_json",
        "dominant_emotions_json",
        "participants_json",
        "participant_roles_json",
        "participant_relationships_json",
        "identity_domains_json",
        "entity_salience_json",
        "ner_entities_json",
        "temporal_json",
        "extracted_relations_json",
    ]

    for col in json_columns:
        val = row.get(col)
        if val is not None:
            try:
                json.loads(val)
            except (json.JSONDecodeError, TypeError):
                pytest.fail(f"Column {col} has invalid JSON: {val!r}")


@pytest.mark.asyncio
async def test_effective_safety_band_present():
    """effective_safety_band is computed and present in row."""
    envelope = _complete_envelope()
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m13_run(msg, ctx, envelope=envelope, validate_required_fields=False)
    row = result["hipp_events_row"]

    assert "effective_safety_band" in row
