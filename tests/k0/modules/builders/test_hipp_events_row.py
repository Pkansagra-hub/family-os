"""
Tests for M13 (HippEvents Row Builder)

Test Coverage:
- Column group assembly (9 groups × 3-4 tests each = ~30 tests)
- JSON serialization (3 tests)
- Validation (required fields, value ranges, enums) (6 tests)
- Error handling (missing outputs, malformed data) (4 tests)
- Performance (<10ms P95 budget) (2 tests)
- Metrics (2 tests)
- End-to-end integration (3 tests)

Total: ~50 tests

**Contract**: k0/contracts/modules/builders.hipp_events_row.v1.yaml
**ADR**: docs/architecture/decisions-K0/modules/k009.1-hipp-events-builder.md
"""

import json
import time
from typing import Any, Dict
from unittest.mock import Mock

import pytest

from k0.modules.builders.hipp_events_row import (
    get_metrics,
    map_actor_device_group,
    map_affect_salience_group,
    map_embeddings_kg_group,
    map_hippocampus_group,
    map_identity_group,
    map_integrity_group,
    map_policy_group,
    map_semantic_activity_group,
    map_social_group,
    map_spatial_group,
    map_temporal_group,
    reset_metrics,
    run,
    serialize_to_json,
    validate_enum_values,
    validate_required_fields,
    validate_value_ranges,
)

# =============================================================================
# Test Helpers
# =============================================================================


class MockMessage:
    """Mock BusMessage for testing"""

    def __init__(self, payload: Any, trace_id: str = "test_trace"):
        self.payload = json.dumps(payload) if isinstance(payload, dict) else payload
        self.trace_id = trace_id
        self.offset = 0


class MockContext:
    """Mock PipelineContext for testing"""

    def __init__(self):
        self.logger = Mock()
        self.syscalls = Mock()
        self.config = {}


def make_test_call(envelope: Dict[str, Any], **config: Any):
    """Create test call with Phase 2 signature"""
    return MockMessage(envelope), MockContext(), config


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def base_envelope() -> Dict[str, Any]:
    """Base envelope with P02 hybrid structure (identity flat, body/policy nested)"""
    return {
        # Identity & Trace (flat at top level)
        "cognitive_trace_id": "trace_abc123",
        "wal_pos": 1001,
        "tenant_id": "tenant_family123",
        "space_id": "space_personal_dad",
        "topic": "cognitive.memory.write.v1",
        "uow_id": "uow_xyz789",
        "schema_version": "1.0.0",
        # Integrity & Audit (flat at top level)
        "envelope_sha256": "sha256_hash_here",
        "sig_alg": "ECDSA_P256_SHA256",
        "sig_kid": "key_2025_01",
        "idem_key": "idem_123",
        "ingested_at": 1700000000,
        "clock_skew_ms": 50,
        # Device and actor at top level (used by map_actor_device_group)
        "device_id": "device_iphone_dad",
        "actor": "person_dad",  # Note: field is 'actor' not 'actor_id'
        "actor_role": "SELF",
        # Body fields (NESTED structure still used by social/semantic modules)
        "body": {
            "actor": "person_dad",
            "actor_role": "SELF",
            "text": "Had dinner with family at Olive Garden",
            "language": "en",
            "participants": ["person_dad", "person_mom", "person_sharvi"],
            "is_meal": True,
            "is_outing": True,
        },
        # Policy stamp (NESTED structure still used by module)
        "policy_stamp": {
            "decision": "ALLOW",
            "band": "GREEN",
            "version": "1.0.0",
            "obligations": ["mask.location.precision"],
        },
    }


@pytest.fixture
def complete_module_outputs() -> Dict[str, Any]:
    """Complete outputs from all 13 enrichment modules - flat fields to merge into envelope"""
    return {
        # M01 pattern_separate outputs (flat)
        "simhash_hex": "a1b2c3d4e5f60708",
        "minhash32": json.dumps([1234, 5678, 9012, 3456] * 8),
        # M02 semantic_project outputs (flat)
        "embedding_id": "emb_uuid_123",
        "entities_json": json.dumps(["Olive_Garden", "person_mom", "person_sharvi"]),
        "kg_triples_json": json.dumps(
            [
                ["person_dad", "had_dinner_with", "person_mom"],
                ["person_dad", "dined_at", "Olive_Garden"],
            ]
        ),
        # M03 policy_stamp outputs (flat)
        "effective_band": "GREEN",
        "policy_obligations": ["mask.location.precision"],
        # M04 affect_analyze outputs (flat)
        "valence": 0.8,
        "arousal": 0.6,
        "sentiment_score": 0.8,
        "sentiment_label": "positive",
        "dominant_emotions_json": json.dumps(["joy", "contentment"]),
        "affect_band": "GREEN",
        # M05 space_resolve outputs (flat)
        "owner_id": "person_dad",
        "effective_space_id": "space_personal_dad",
        "visible_to_json": json.dumps(["person_dad", "person_mom"]),
        "visibility_scope": "SPACE_DEFAULT",
        "co_owners_json": json.dumps(["person_mom"]),
        # M06 salience_score outputs (flat)
        "salience_score": 0.85,
        "salience_reasons_json": json.dumps(
            ["social_family", "positive_affect", "meal_outside_home"]
        ),
        "salience_band": "HIGH",
        # M07 family_graph_resolve outputs (flat)
        "num_participants": 3,
        "participant_roles_json": json.dumps(
            {"person_dad": "SELF", "person_mom": "SPOUSE", "person_sharvi": "CHILD"}
        ),
        "has_partner_present": True,
        "has_parent_present": False,
        "is_solo_event": False,
        "social_context": "nuclear_family",
        "social_intimacy": "HIGH",
        # M08 temporal_profile outputs (flat)
        "event_time_utc": 1700000000,
        "write_time_utc": 1700000100,
        "write_lag_ms": 100,
        "local_date": "2023-11-15",
        "local_time": "18:30:00",
        "day_of_week": "wednesday",
        "is_weekend": False,
        "time_of_day_bucket": "evening",
        "circadian_slot": "dinner",
        "is_backdated": False,
        # M09 device_profile outputs (flat)
        "device_kind": "phone",
        "device_os": "iOS",
        # M10 ingress_classify outputs (flat)
        "ingress_topic": "write",
        "activity_type": "meal",
        "activity_category": "episodic",
        "ingress_source": "mobile_app",
        # M11 retention_lookup outputs (flat)
        "retention_policy_id": "policy_green_7y",
        "retention_bucket": "STANDARD",
        # M12 geo_metadata outputs (flat)
        "geohash_6": "9q8yy9",
        "location_name": "Olive Garden, Market St",
        "location_type": "restaurant",
        "geo_precision_external": "full",
        "geo_masking_reason": "none",
    }


# =============================================================================
# Column Group Tests (9 groups)
# =============================================================================


@pytest.mark.asyncio
async def test_identity_group_assembly(base_envelope, complete_module_outputs):
    """Test identity & trace column group (9 columns)"""
    # Merge outputs into envelope (P02 flat format)
    envelope = {**base_envelope, **complete_module_outputs}
    # Extract space output from flat envelope
    space_output = {
        "effective_space_id": envelope.get("effective_space_id"),
    }
    result = map_identity_group(envelope, space_output)

    assert result["event_id"] == "trace_abc123"  # event_id is cognitive_trace_id
    assert result["wal_pos"] == 1001
    assert result["cognitive_trace_id"] == "trace_abc123"
    assert result["tenant_id"] == "tenant_family123"
    assert result["space_id"] == "space_personal_dad"
    assert result["effective_space_id"] == "space_personal_dad"
    assert result["topic"] == "cognitive.memory.write.v1"
    assert result["uow_id"] == "uow_xyz789"
    assert result["schema_version"] == "1.0.0"


@pytest.mark.asyncio
async def test_integrity_group_assembly(base_envelope):
    """Test integrity & audit column group (6 columns)"""
    result = map_integrity_group(base_envelope)

    assert result["envelope_sha256"] == "sha256_hash_here"
    assert result["sig_alg"] == "ECDSA_P256_SHA256"
    assert result["sig_kid"] == "key_2025_01"
    assert result["idem_key"] == "idem_123"
    assert result["ingested_at"] == 1700000000
    assert result["clock_skew_ms"] == 50


@pytest.mark.asyncio
async def test_policy_group_assembly(base_envelope, complete_module_outputs):
    """Test policy & visibility column group (10 columns)"""
    # Merge outputs into envelope (P02 flat format)
    envelope = {**base_envelope, **complete_module_outputs}
    # Extract structured outputs from flat envelope
    policy_output = {"obligations": envelope.get("policy_obligations", [])}
    space_output = {
        "visible_to": json.loads(envelope.get("visible_to_json", "[]")),
        "visibility_scope": envelope.get("visibility_scope"),
        "owner_id": envelope.get("owner_id"),
        "co_owners": json.loads(envelope.get("co_owners_json", "[]")),
    }
    retention_output = {
        "retention_policy_id": envelope.get("retention_policy_id"),
        "retention_bucket": envelope.get("retention_bucket"),
    }

    result = map_policy_group(envelope, policy_output, space_output, retention_output)

    assert result["policy_decision"] == "ALLOW"
    assert result["policy_band"] == "GREEN"
    assert result["policy_version"] == "1.0.0"
    assert json.loads(result["obligations_json"]) == ["mask.location.precision"]
    assert json.loads(result["visible_to_json"]) == ["person_dad", "person_mom"]
    assert result["visibility_scope"] == "SPACE_DEFAULT"
    assert result["owner_id"] == "person_dad"
    assert json.loads(result["co_owners_json"]) == ["person_mom"]
    assert result["retention_policy_id"] == "policy_green_7y"
    assert result["retention_bucket"] == "STANDARD"


@pytest.mark.asyncio
async def test_actor_device_group_assembly(base_envelope, complete_module_outputs):
    """Test actor & device column group (6 columns)"""
    # Merge outputs into envelope (P02 flat format)
    envelope = {**base_envelope, **complete_module_outputs}
    # Extract structured outputs from flat envelope
    device_output = {
        "device_kind": envelope.get("device_kind"),
        "device_os": envelope.get("device_os"),
    }
    ingress_output = {"ingress_topic": envelope.get("ingress_topic")}

    result = map_actor_device_group(envelope, device_output, ingress_output)

    assert result["actor_id"] == "person_dad"
    assert result["actor_role"] == "SELF"
    assert result["device_id"] == "device_iphone_dad"
    assert result["device_kind"] == "phone"
    assert result["device_os"] == "iOS"
    assert result["ingress_channel"] == "write"


@pytest.mark.asyncio
async def test_temporal_group_assembly(complete_module_outputs):
    """Test temporal column group (11 columns)"""
    # Extract temporal fields from flat envelope
    temporal_output = {
        k: complete_module_outputs.get(k)
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

    result = map_temporal_group(temporal_output)

    assert result["event_time_utc"] == 1700000000
    assert result["write_time_utc"] == 1700000100
    assert result["write_lag_ms"] == 100
    assert result["local_date"] == "2023-11-15"
    assert result["local_time"] == "18:30:00"
    assert result["day_of_week"] == "wednesday"
    assert result["is_weekend"] is False
    assert result["time_of_day_bucket"] == "evening"
    assert result["circadian_slot"] == "dinner"
    assert result["is_backdated"] is False
    assert "created_at" in result


@pytest.mark.asyncio
async def test_spatial_group_assembly(complete_module_outputs):
    """Test spatial & place column group (5 columns)"""
    # Extract spatial fields from flat envelope
    geo_output = {
        "geo_precision_external": complete_module_outputs.get("geo_precision_external"),
        "geo_masking_reason": complete_module_outputs.get("geo_masking_reason"),
        "location_name": complete_module_outputs.get("location_name"),
        "location_type": complete_module_outputs.get("location_type"),
        "geohash_6": complete_module_outputs.get("geohash_6"),
    }
    spatial_output = {
        "geohash_6": complete_module_outputs.get("geohash_6"),
        "location_name": complete_module_outputs.get("location_name"),
        "location_type": complete_module_outputs.get("location_type"),
    }

    result = map_spatial_group(geo_output, spatial_output)

    assert result["location_name"] == "Olive Garden, Market St"
    assert result["location_type"] == "restaurant"
    assert result["geohash_6"] == "9q8yy9"
    assert result["geo_precision_external"] == "full"
    assert result["geo_masking_reason"] == "none"


@pytest.mark.asyncio
async def test_social_group_assembly(base_envelope, complete_module_outputs):
    """Test social & relationships column group (7 columns)"""
    # Merge outputs into envelope
    envelope = {**base_envelope, **complete_module_outputs}
    # Extract social fields from flat envelope
    social_output = {
        "num_participants": envelope.get("num_participants"),
        "has_partner_present": envelope.get("has_partner_present"),
        "has_parent_present": envelope.get("has_parent_present"),
        "is_solo_event": envelope.get("is_solo_event"),
        "social_context": envelope.get("social_context"),
        "social_intimacy": envelope.get("social_intimacy"),
        "participant_roles_json": envelope.get("participant_roles_json"),
    }

    result = map_social_group(envelope, social_output)

    participants = json.loads(result["participants_json"])
    assert participants == ["person_dad", "person_mom", "person_sharvi"]
    assert result["num_participants"] == 3
    assert result["has_partner_present"] is True
    assert result["has_parent_present"] is False
    assert result["is_solo_event"] is False
    assert result["social_context"] == "nuclear_family"
    assert result["social_intimacy"] == "HIGH"


@pytest.mark.asyncio
async def test_semantic_activity_group_assembly(base_envelope, complete_module_outputs):
    """Test semantic & activity column group (9 columns)"""
    # Merge outputs into envelope
    envelope = {**base_envelope, **complete_module_outputs}
    # Extract ingress fields from flat envelope
    ingress_output = {
        "activity_type": envelope.get("activity_type"),
        "activity_category": envelope.get("activity_category"),
        "ingress_source": envelope.get("ingress_source"),
    }

    result = map_semantic_activity_group(envelope, ingress_output)

    assert result["text"] == "Had dinner with family at Olive Garden"
    assert result["text_normalized"] == "had dinner with family at olive garden"
    assert result["char_count"] == 38  # Actual length counted by module
    assert result["token_count"] == 7
    assert result["language"] == "en"
    assert result["activity_type"] == "meal"
    assert result["activity_category"] == "episodic"
    assert result["is_meal"] is True
    assert result["is_outing"] is True
    assert result["ingress_source"] == "mobile_app"


@pytest.mark.asyncio
async def test_hippocampus_group_assembly(complete_module_outputs):
    """Test hippocampus column group (8 columns) - CA3 deferred"""
    # Extract DG and CA1 fields from flat envelope
    dg_output = {
        "simhash_hex": complete_module_outputs.get("simhash_hex"),
        "minhash32": complete_module_outputs.get("minhash32"),
    }
    ca1_output = {
        "embedding_id": complete_module_outputs.get("embedding_id"),
    }

    result = map_hippocampus_group(dg_output, ca1_output)

    assert result["simhash_hex"] == "a1b2c3d4e5f60708"
    assert result["minhash32"] == json.dumps([1234, 5678, 9012, 3456] * 8)
    # CA3 outputs deferred to P03
    assert result["novelty_score"] is None
    assert result["near_duplicates_json"] is None
    assert result["is_near_duplicate"] is None
    assert result["episode_cluster_id"] is None
    assert result["cluster_confidence"] is None
    assert result["clustering_version"] is None


@pytest.mark.asyncio
async def test_embeddings_kg_group_assembly(complete_module_outputs):
    """Test embeddings & KG column group (4 columns)"""
    # Extract CA1 fields from flat envelope - keep as JSON strings (not parsed)
    ca1_output = {
        "embedding_id": complete_module_outputs.get("embedding_id"),
        "entities_json": complete_module_outputs.get("entities_json", "[]"),
        "kg_triples_json": complete_module_outputs.get("kg_triples_json", "[]"),
    }

    result = map_embeddings_kg_group(ca1_output)

    assert result["embedding_id"] == "emb_uuid_123"
    assert result["embedding_status"] == "PENDING"
    entities = json.loads(result["entities_json"])
    assert entities == ["Olive_Garden", "person_mom", "person_sharvi"]
    kg_triples = json.loads(result["kg_triples_json"])
    assert len(kg_triples) == 2


@pytest.mark.asyncio
async def test_affect_salience_group_assembly(complete_module_outputs):
    """Test affect & salience column group (9 columns)"""
    # Extract affect and salience fields from flat envelope
    affect_output = {
        "sentiment_score": complete_module_outputs.get("sentiment_score"),
        "sentiment_label": complete_module_outputs.get("sentiment_label"),
        "dominant_emotions": json.loads(
            complete_module_outputs.get("dominant_emotions_json", "[]")
        ),
        "valence": complete_module_outputs.get("valence"),
        "arousal": complete_module_outputs.get("arousal"),
        "affect_band": complete_module_outputs.get("affect_band"),
    }
    salience_output = {
        "salience_score": complete_module_outputs.get("salience_score"),
        "salience_reasons": json.loads(complete_module_outputs.get("salience_reasons_json", "[]")),
        "salience_band": complete_module_outputs.get("salience_band"),
    }

    result = map_affect_salience_group(affect_output, salience_output)

    assert result["sentiment_score"] == 0.8
    assert result["sentiment_label"] == "positive"
    emotions = json.loads(result["dominant_emotions_json"])
    assert emotions == ["joy", "contentment"]
    assert result["affect_valence"] == 0.8
    assert result["affect_arousal"] == 0.6
    assert result["affect_band"] == "GREEN"
    assert result["salience_score"] == 0.85
    reasons = json.loads(result["salience_reasons_json"])
    assert reasons == ["social_family", "positive_affect", "meal_outside_home"]
    assert result["salience_band"] == "HIGH"


# =============================================================================
# JSON Serialization Tests
# =============================================================================


@pytest.mark.asyncio
async def test_json_serialization_list():
    """Test JSON serialization for list data"""
    data = ["item1", "item2", "item3"]
    result = serialize_to_json(data, "test_list")

    assert isinstance(result, str)
    assert json.loads(result) == data


@pytest.mark.asyncio
async def test_json_serialization_dict():
    """Test JSON serialization for dict data"""
    data = {"key1": "value1", "key2": "value2"}
    result = serialize_to_json(data, "test_dict")

    assert isinstance(result, str)
    assert json.loads(result) == data


@pytest.mark.asyncio
async def test_json_serialization_none():
    """Test JSON serialization for None"""
    result = serialize_to_json(None, "test_none")
    assert result is None


# =============================================================================
# Validation Tests
# =============================================================================


@pytest.mark.asyncio
async def test_validation_required_fields_success(base_envelope, complete_module_outputs):
    """Test validation passes with all required fields"""
    enriched_envelope = {**base_envelope, **complete_module_outputs}
    message, context, config = make_test_call(enriched_envelope, validate_required_fields=True)
    result = await run(message, context, **config)
    row = result["hipp_events_row"]

    # Should not raise
    validate_required_fields(row)


@pytest.mark.asyncio
async def test_validation_required_fields_missing():
    """Test validation fails with missing required field"""
    row = {"event_id": "evt_123"}  # Missing many required fields

    with pytest.raises(ValueError, match="Missing required field"):
        validate_required_fields(row)


@pytest.mark.asyncio
async def test_validation_value_ranges_success():
    """Test value range validation passes"""
    row = {
        "affect_valence": 0.8,
        "affect_arousal": 0.6,
        "salience_score": 0.85,
        "sentiment_score": 0.75,
    }

    # Should not raise
    validate_value_ranges(row)


@pytest.mark.asyncio
async def test_validation_value_ranges_out_of_bounds():
    """Test value range validation fails for out-of-bounds values"""
    row = {"affect_valence": 1.5}  # Out of [-1.0, 1.0]

    with pytest.raises(ValueError, match="affect_valence out of range"):
        validate_value_ranges(row)


@pytest.mark.asyncio
async def test_validation_enum_values_success():
    """Test enum validation passes"""
    row = {"policy_band": "GREEN", "affect_band": "AMBER", "salience_band": "HIGH"}

    # Should not raise
    validate_enum_values(row)


@pytest.mark.asyncio
async def test_validation_enum_values_invalid():
    """Test enum validation fails for invalid values"""
    row = {"policy_band": "INVALID"}

    with pytest.raises(ValueError, match="Invalid policy_band"):
        validate_enum_values(row)


# =============================================================================
# End-to-End Integration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_full_row_assembly(base_envelope, complete_module_outputs):
    """Test complete row assembly from all modules"""
    reset_metrics()
    enriched_envelope = {**base_envelope, **complete_module_outputs}

    message, context, config = make_test_call(enriched_envelope, validate_required_fields=True)
    result = await run(message, context, **config)
    row = result["hipp_events_row"]

    # Verify all major column groups present
    assert "event_id" in row
    assert "simhash_hex" in row
    assert "embedding_id" in row
    assert "affect_valence" in row
    assert "salience_score" in row
    assert "social_context" in row
    assert "location_name" in row

    # Verify CA3 deferred columns are NULL
    assert row["is_near_duplicate"] is None
    assert row["episode_cluster_id"] is None
    assert row["cluster_confidence"] is None

    # Check metrics
    metrics = get_metrics()
    assert metrics["rows_built"] == 1
    assert metrics["validation_failures"] == 0


@pytest.mark.asyncio
async def test_row_assembly_with_missing_optional_outputs(base_envelope):
    """Test row assembly handles missing optional module outputs"""
    reset_metrics()

    # Only provide required outputs (flat structure)
    minimal_outputs = {
        "simhash_hex": "abc123",
        "minhash32": "[]",
        "embedding_id": "emb_123",
        "entities_json": "[]",
        "kg_triples_json": "[]",
        "effective_band": "GREEN",
        "policy_obligations": [],
        "valence": 0.5,
        "arousal": 0.5,
        "affect_band": "GREEN",
        "owner_id": "person_dad",
        "visible_to_json": "[]",
        "visibility_scope": "OWNER_ONLY",
        "salience_score": 0.5,
        "salience_reasons_json": "[]",
        "salience_band": "MED",
        "social_context": "solo",
        "is_solo_event": True,
        "event_time_utc": 1700000000,
        "write_time_utc": 1700000000,
        "device_kind": "unknown",
        "ingress_topic": "write",
        "activity_type": "unknown",
        "retention_policy_id": "policy_default",
        "retention_bucket": "STANDARD",
        "geo_metadata": {},
        "spatial_minimal": {},
    }
    enriched_envelope = {**base_envelope, **minimal_outputs}

    message, context, config = make_test_call(enriched_envelope, validate_required_fields=True)
    result = await run(message, context, **config)
    row = result["hipp_events_row"]

    # Should succeed with defaults
    assert row["event_id"] == "trace_abc123"  # Module uses cognitive_trace_id as event_id
    assert row["salience_score"] == 0.5


@pytest.mark.asyncio
async def test_row_assembly_idempotency(base_envelope, complete_module_outputs):
    """Test row assembly is idempotent"""
    reset_metrics()
    enriched_envelope = {**base_envelope, **complete_module_outputs}

    message1, context1, config1 = make_test_call(enriched_envelope, validate_required_fields=True)
    result1 = await run(message1, context1, **config1)
    row1 = result1["hipp_events_row"]

    message2, context2, config2 = make_test_call(enriched_envelope, validate_required_fields=True)
    result2 = await run(message2, context2, **config2)
    row2 = result2["hipp_events_row"]

    # Ignore created_at (timestamp varies)
    row1_copy = {k: v for k, v in row1.items() if k != "created_at"}
    row2_copy = {k: v for k, v in row2.items() if k != "created_at"}

    assert row1_copy == row2_copy


# =============================================================================
# Error Handling Tests
# =============================================================================


@pytest.mark.asyncio
async def test_error_missing_module_output(base_envelope):
    """Test error handling when critical module output missing"""
    reset_metrics()
    # No module outputs merged - base_envelope alone is incomplete

    message, context, config = make_test_call(base_envelope, validate_required_fields=True)
    with pytest.raises(ValueError, match="Missing required field"):
        await run(message, context, **config)


@pytest.mark.asyncio
async def test_error_invalid_json_data():
    """Test error handling for invalid JSON data"""

    # Create object that can't be JSON serialized
    class NonSerializable:
        pass

    with pytest.raises(ValueError, match="JSON serialization failed"):
        serialize_to_json(NonSerializable(), "test_field")


@pytest.mark.asyncio
async def test_error_missing_envelope_header(complete_module_outputs):
    """Test error handling when envelope header missing"""
    reset_metrics()
    bad_envelope = {
        **{"body": {}},
        **complete_module_outputs,
    }  # Missing cognitive_trace_id, wal_pos, etc.

    message, context, config = make_test_call(bad_envelope, validate_required_fields=True)
    with pytest.raises(ValueError, match="Missing required field"):
        await run(message, context, **config)


@pytest.mark.asyncio
async def test_error_malformed_module_output(base_envelope, complete_module_outputs):
    """Test error handling with malformed module output"""
    reset_metrics()
    # Break temporal output by removing required field
    broken_outputs = {**complete_module_outputs}
    del broken_outputs["event_time_utc"]  # Remove required temporal field
    enriched_envelope = {**base_envelope, **broken_outputs}

    message, context, config = make_test_call(enriched_envelope, validate_required_fields=True)
    with pytest.raises(ValueError, match="Missing required field"):
        await run(message, context, **config)


# =============================================================================
# Performance Tests
# =============================================================================


@pytest.mark.asyncio
async def test_performance_under_10ms(base_envelope, complete_module_outputs):
    """Test row assembly meets <10ms P95 budget"""
    reset_metrics()
    enriched_envelope = {**base_envelope, **complete_module_outputs}

    latencies = []
    for _ in range(100):
        message, context, config = make_test_call(enriched_envelope, validate_required_fields=True)
        start = time.perf_counter()
        await run(message, context, **config)
        elapsed_ms = (time.perf_counter() - start) * 1000
        latencies.append(elapsed_ms)

    latencies_sorted = sorted(latencies)
    p50 = latencies_sorted[49]
    p95 = latencies_sorted[94]
    p99 = latencies_sorted[98]

    print("\nRow Assembly Performance:")
    print(f"  P50: {p50:.4f}ms")
    print(f"  P95: {p95:.4f}ms")
    print(f"  P99: {p99:.4f}ms")

    assert p95 < 10.0, f"P95 latency {p95:.4f}ms exceeds 10ms budget"


@pytest.mark.asyncio
async def test_performance_json_serialization():
    """Test JSON serialization performance"""
    reset_metrics()

    # Large data structure
    large_data = [{"key": f"value_{i}"} for i in range(1000)]

    start = time.perf_counter()
    for _ in range(100):
        serialize_to_json(large_data, "large_data")
    elapsed_ms = (time.perf_counter() - start) * 1000

    avg_ms = elapsed_ms / 100
    print("\nJSON Serialization (1000 items):")
    print(f"  Avg: {avg_ms:.4f}ms per call")

    assert avg_ms < 1.0, f"JSON serialization {avg_ms:.4f}ms too slow"


# =============================================================================
# Metrics Tests
# =============================================================================


@pytest.mark.asyncio
async def test_metrics_tracking(base_envelope, complete_module_outputs):
    """Test that metrics are tracked correctly"""
    reset_metrics()
    enriched_envelope = {**base_envelope, **complete_module_outputs}

    message1, context1, config1 = make_test_call(enriched_envelope, validate_required_fields=True)
    await run(message1, context1, **config1)

    message2, context2, config2 = make_test_call(enriched_envelope, validate_required_fields=True)
    await run(message2, context2, **config2)

    metrics = get_metrics()
    assert metrics["rows_built"] == 2
    assert metrics["validation_failures"] == 0
    assert metrics["column_group_counts"]["identity"] == 2
    assert metrics["column_group_counts"]["social"] == 2


@pytest.mark.asyncio
async def test_metrics_reset():
    """Test metrics can be reset"""
    reset_metrics()

    metrics = get_metrics()
    assert metrics["rows_built"] == 0
    assert metrics["validation_failures"] == 0
    assert len(metrics["column_group_counts"]) == 0


# =============================================================================
# Edge Cases
# =============================================================================


@pytest.mark.asyncio
async def test_edge_case_solo_event(base_envelope, complete_module_outputs):
    """Test row assembly for solo event (no participants)"""
    reset_metrics()
    base_envelope["body"]["participants"] = []
    # Override family_graph_resolve outputs for solo event
    solo_outputs = {
        "num_participants": 0,
        "is_solo_event": True,
        "social_context": "solo",
        "social_intimacy": "LOW",
        "has_partner_present": False,
        "has_parent_present": False,
    }
    enriched_envelope = {**base_envelope, **complete_module_outputs, **solo_outputs}

    message, context, config = make_test_call(enriched_envelope, validate_required_fields=True)
    result = await run(message, context, **config)
    row = result["hipp_events_row"]

    assert row["num_participants"] == 0
    assert row["is_solo_event"] is True
    assert row["social_context"] == "solo"


@pytest.mark.asyncio
async def test_edge_case_red_band_event(base_envelope, complete_module_outputs):
    """Test row assembly for RED band event"""
    reset_metrics()
    base_envelope["policy_stamp"]["band"] = "RED"
    base_envelope["band"] = "RED"  # Module reads 'band' from envelope root level
    enriched_envelope = {**base_envelope, **complete_module_outputs}

    message, context, config = make_test_call(enriched_envelope, validate_required_fields=True)
    result = await run(message, context, **config)
    row = result["hipp_events_row"]

    assert row["policy_band"] == "RED"


@pytest.mark.asyncio
async def test_edge_case_empty_text(base_envelope, complete_module_outputs):
    """Test row assembly with empty text"""
    reset_metrics()
    base_envelope["body"]["text"] = ""
    enriched_envelope = {**base_envelope, **complete_module_outputs}

    message, context, config = make_test_call(enriched_envelope, validate_required_fields=True)
    result = await run(message, context, **config)
    row = result["hipp_events_row"]

    assert row["text"] == ""
    assert row["char_count"] == 0
    assert row["token_count"] == 0


@pytest.mark.asyncio
async def test_edge_case_missing_geohash(base_envelope, complete_module_outputs):
    """Test row assembly with missing geohash (privacy)"""
    reset_metrics()
    # Override geo outputs with masked values and remove geohash fields
    masked_outputs = {**complete_module_outputs}
    # Remove geohash fields to test missing location scenario
    masked_outputs.pop("geohash_6", None)
    masked_outputs.pop("geohash_9", None)
    masked_outputs["geo_masking_reason"] = "band_policy"  # Module reads from envelope root
    enriched_envelope = {**base_envelope, **masked_outputs}

    message, context, config = make_test_call(enriched_envelope, validate_required_fields=True)
    result = await run(message, context, **config)
    row = result["hipp_events_row"]

    assert row["geohash_6"] is None
    assert row["geo_masking_reason"] == "band_policy"
    assert row["geo_masking_reason"] == "band_policy"
