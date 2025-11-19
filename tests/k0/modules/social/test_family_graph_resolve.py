"""
Tests for M07: social.family_graph_resolve - Family Graph Resolver

Test Coverage:
- Solo events
- Nuclear family (spouse, parents, children)
- Extended family (caregivers, siblings)
- Friends (no family relationships)
- Participant role mapping
- Social context classification
- Intimacy scoring
- Boolean flags (partner/parent present)
- Cache hit/miss performance
- Error handling
- Edge cases
"""

import json
import time
from typing import Any
from unittest.mock import Mock

import pytest

from k0.modules.social import family_graph_resolve

# ============================================================================
# Mock Classes for Phase 2 Signature Testing
# ============================================================================


class MockMessage:
    """Mock BusMessage for testing Phase 2 signature."""

    def __init__(self, payload: dict[str, Any], trace_id: str = "test_trace"):
        self.payload = json.dumps(payload)
        self.trace_id = trace_id
        self.offset = 0
        self.topic = "cognitive.memory.write.committed.v1"
        self.space_id = "test_space"


class MockContext:
    """Mock PipelineContext for testing Phase 2 signature."""

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
    """Reset metrics and cache before each test."""
    family_graph_resolve.reset_metrics()
    yield
    family_graph_resolve.reset_metrics()


def make_test_call(envelope: dict[str, Any], **config) -> tuple[MockMessage, MockContext]:
    """Helper to create message and context objects for test calls."""
    message = MockMessage(payload=envelope, trace_id="test_trace")
    context = MockContext()
    return message, context


@pytest.fixture
def sample_envelope_solo():
    """Solo event envelope (no participants)."""
    return {
        "actor_id": "person_dad",
        "body": {
            "text": "Morning coffee alone",
            "participants": [],
            "event_time": "2025-11-17T08:00:00Z",
        },
    }


@pytest.fixture
def sample_envelope_nuclear_family():
    """Nuclear family event envelope (spouse + child)."""
    return {
        "actor_id": "person_dad",
        "body": {
            "text": "Family dinner at home",
            "participants": ["person_dad", "person_mom", "person_sharvi"],
            "event_time": "2025-11-17T18:00:00Z",
        },
    }


@pytest.fixture
def sample_envelope_spouse_only():
    """Event with spouse only."""
    return {
        "actor_id": "person_dad",
        "body": {
            "text": "Date night with spouse",
            "participants": ["person_dad", "person_mom"],
            "event_time": "2025-11-17T19:00:00Z",
        },
    }


@pytest.fixture
def sample_envelope_friends():
    """Event with friends (no family relationships)."""
    return {
        "actor_id": "person_dad",
        "body": {
            "text": "Coffee with colleague",
            "participants": ["person_dad", "person_friend_john"],
            "event_time": "2025-11-17T15:00:00Z",
        },
    }


# ============================================================================
# Test: Solo Events
# ============================================================================


@pytest.mark.asyncio
async def test_solo_event_empty_participants(sample_envelope_solo):
    """Test solo event with empty participants list."""
    message, context = make_test_call(sample_envelope_solo)
    result = await family_graph_resolve.run(message, context)

    assert result["num_participants"] == 1
    assert result["is_solo_event"] is True
    assert result["social_context"] == "solo"
    assert result["social_intimacy"] == "LOW"
    assert result["has_partner_present"] is False
    assert result["has_parent_present"] is False
    assert "social_resolved_at_utc" in result


@pytest.mark.asyncio
async def test_solo_event_actor_only_in_participants():
    """Test solo event with only actor in participants list."""
    envelope = {
        "actor_id": "person_dad",
        "body": {
            "text": "Solo walk",
            "participants": ["person_dad"],  # Only actor
        },
    }

    message, context = make_test_call(envelope)
    result = await family_graph_resolve.run(message, context)

    assert result["is_solo_event"] is True
    assert result["social_context"] == "solo"
    assert result["num_participants"] == 1


@pytest.mark.asyncio
async def test_solo_event_no_body():
    """Test solo event with missing body."""
    envelope = {"actor_id": "person_dad"}  # No body at all

    message, context = make_test_call(envelope)
    result = await family_graph_resolve.run(message, context)

    assert result["is_solo_event"] is True
    assert result["social_context"] == "solo"


# ============================================================================
# Test: Nuclear Family Events
# ============================================================================


@pytest.mark.asyncio
async def test_nuclear_family_spouse_present(sample_envelope_spouse_only):
    """Test nuclear family context with spouse present."""
    message, context = make_test_call(sample_envelope_spouse_only)
    result = await family_graph_resolve.run(message, context)

    assert result["num_participants"] == 2
    assert result["social_context"] == "nuclear_family"
    assert result["social_intimacy"] == "HIGH"
    assert result["has_partner_present"] is True
    assert result["has_parent_present"] is False
    assert result["is_solo_event"] is False

    # Check participant roles
    roles = json.loads(result["participant_roles_json"])
    assert roles["person_dad"] == "SELF"
    assert roles["person_mom"] == "SPOUSE"


@pytest.mark.asyncio
async def test_nuclear_family_full(sample_envelope_nuclear_family):
    """Test nuclear family with spouse and child."""
    message, context = make_test_call(sample_envelope_nuclear_family)
    result = await family_graph_resolve.run(message, context)

    assert result["social_context"] == "nuclear_family"
    assert result["social_intimacy"] == "HIGH"
    assert result["has_partner_present"] is True
    assert result["num_participants"] == 3

    # Check participant roles
    roles = json.loads(result["participant_roles_json"])
    assert roles["person_dad"] == "SELF"
    assert roles["person_mom"] == "SPOUSE"
    assert roles["person_sharvi"] == "CHILD"


@pytest.mark.asyncio
async def test_nuclear_family_child_perspective():
    """Test nuclear family from child's perspective (sees parents)."""
    envelope = {
        "actor_id": "person_sharvi",
        "body": {
            "text": "Family dinner",
            "participants": ["person_sharvi", "person_dad", "person_mom"],
        },
    }

    message, context = make_test_call(envelope)
    result = await family_graph_resolve.run(message, context)

    assert result["social_context"] == "nuclear_family"
    assert result["social_intimacy"] == "HIGH"
    assert result["has_parent_present"] is True  # Sees parents

    # Check participant roles from child's perspective
    roles = json.loads(result["participant_roles_json"])
    assert roles["person_sharvi"] == "SELF"
    assert roles["person_dad"] == "PARENT"
    assert roles["person_mom"] == "PARENT"


# ============================================================================
# Test: Extended Family Events
# ============================================================================


@pytest.mark.asyncio
async def test_extended_family_caretaker():
    """Test extended family context with caretaker."""
    # Add caretaker relationship to database for this test
    family_graph_resolve._RELATIONSHIP_DB["person_grandpa"] = [("person_sharvi", "CARETAKER_OF")]

    envelope = {
        "actor_id": "person_grandpa",
        "body": {
            "text": "Watching grandchild",
            "participants": ["person_grandpa", "person_sharvi"],
        },
    }

    message, context = make_test_call(envelope)
    result = await family_graph_resolve.run(message, context)

    assert result["social_context"] == "extended_family"
    assert result["social_intimacy"] == "MED"

    # Check roles
    roles = json.loads(result["participant_roles_json"])
    assert roles["person_sharvi"] == "CAREGIVER"

    # Cleanup
    del family_graph_resolve._RELATIONSHIP_DB["person_grandpa"]


@pytest.mark.asyncio
async def test_extended_family_sibling():
    """Test extended family context with sibling."""
    # Add sibling relationship
    family_graph_resolve._RELATIONSHIP_DB["person_alice"] = [("person_bob", "SIBLING_OF")]

    envelope = {
        "actor_id": "person_alice",
        "body": {
            "text": "Hanging out with sibling",
            "participants": ["person_alice", "person_bob"],
        },
    }

    message, context = make_test_call(envelope)
    result = await family_graph_resolve.run(message, context)

    assert result["social_context"] == "extended_family"
    assert result["social_intimacy"] == "MED"

    # Cleanup
    del family_graph_resolve._RELATIONSHIP_DB["person_alice"]


# ============================================================================
# Test: Friends Events (No Family Relationships)
# ============================================================================


@pytest.mark.asyncio
async def test_friends_no_relationships(sample_envelope_friends):
    """Test friends context (no family relationships found)."""
    message, context = make_test_call(sample_envelope_friends)
    result = await family_graph_resolve.run(message, context)

    assert result["social_context"] == "friends"
    assert result["social_intimacy"] == "LOW"
    assert result["has_partner_present"] is False
    assert result["has_parent_present"] is False

    # Check roles
    roles = json.loads(result["participant_roles_json"])
    assert roles["person_dad"] == "SELF"
    assert roles["person_friend_john"] == "OTHER"  # Unknown relationship


# ============================================================================
# Test: Participant Role Mapping
# ============================================================================


def test_map_participant_roles_spouse():
    """Test participant role mapping for spouse."""
    relationships = [("person_mom", "SPOUSE_OF")]
    roles = family_graph_resolve._map_participant_roles(
        "person_dad", ["person_dad", "person_mom"], relationships
    )

    assert roles["person_dad"] == "SELF"
    assert roles["person_mom"] == "SPOUSE"


def test_map_participant_roles_parent():
    """Test participant role mapping for parent-child."""
    relationships = [("person_sharvi", "PARENT_OF")]
    roles = family_graph_resolve._map_participant_roles(
        "person_dad", ["person_dad", "person_sharvi"], relationships
    )

    assert roles["person_sharvi"] == "CHILD"


def test_map_participant_roles_child():
    """Test participant role mapping from child's perspective."""
    relationships = [("person_dad", "CHILD_OF")]
    roles = family_graph_resolve._map_participant_roles(
        "person_sharvi", ["person_sharvi", "person_dad"], relationships
    )

    assert roles["person_dad"] == "PARENT"


def test_map_participant_roles_unknown():
    """Test participant role mapping for unknown relationships."""
    relationships = []  # No relationships
    roles = family_graph_resolve._map_participant_roles(
        "person_dad", ["person_dad", "person_stranger"], relationships
    )

    assert roles["person_stranger"] == "OTHER"


# ============================================================================
# Test: Social Context Classification
# ============================================================================


def test_classify_social_context_solo():
    """Test solo social context classification."""
    roles = {"person_dad": "SELF"}
    context = family_graph_resolve._classify_social_context(roles)
    assert context == "solo"


def test_classify_social_context_nuclear():
    """Test nuclear family social context."""
    roles = {"person_dad": "SELF", "person_mom": "SPOUSE"}
    context = family_graph_resolve._classify_social_context(roles)
    assert context == "nuclear_family"


def test_classify_social_context_extended():
    """Test extended family social context."""
    roles = {"person_grandpa": "SELF", "person_sharvi": "CAREGIVER"}
    context = family_graph_resolve._classify_social_context(roles)
    assert context == "extended_family"


def test_classify_social_context_friends():
    """Test friends social context."""
    roles = {"person_dad": "SELF", "person_friend": "OTHER"}
    context = family_graph_resolve._classify_social_context(roles)
    assert context == "friends"


# ============================================================================
# Test: Intimacy Scoring
# ============================================================================


def test_intimacy_high_nuclear():
    """Test HIGH intimacy for nuclear family."""
    intimacy = family_graph_resolve._score_social_intimacy("nuclear_family")
    assert intimacy == "HIGH"


def test_intimacy_med_extended():
    """Test MED intimacy for extended family."""
    intimacy = family_graph_resolve._score_social_intimacy("extended_family")
    assert intimacy == "MED"


def test_intimacy_low_friends():
    """Test LOW intimacy for friends."""
    intimacy = family_graph_resolve._score_social_intimacy("friends")
    assert intimacy == "LOW"


def test_intimacy_low_solo():
    """Test LOW intimacy for solo events."""
    intimacy = family_graph_resolve._score_social_intimacy("solo")
    assert intimacy == "LOW"


# ============================================================================
# Test: Boolean Flags
# ============================================================================


def test_has_partner_present_true():
    """Test partner present flag = True."""
    roles = {"person_dad": "SELF", "person_mom": "SPOUSE"}
    assert family_graph_resolve._check_partner_present(roles) is True


def test_has_partner_present_false():
    """Test partner present flag = False."""
    roles = {"person_dad": "SELF", "person_friend": "OTHER"}
    assert family_graph_resolve._check_partner_present(roles) is False


def test_has_parent_present_true():
    """Test parent present flag = True (from child's perspective)."""
    roles = {"person_sharvi": "SELF", "person_dad": "PARENT"}
    assert family_graph_resolve._check_parent_present(roles) is True


def test_has_parent_present_false():
    """Test parent present flag = False."""
    roles = {"person_dad": "SELF", "person_sharvi": "CHILD"}
    assert family_graph_resolve._check_parent_present(roles) is False


# ============================================================================
# Test: Cache Performance
# ============================================================================


@pytest.mark.asyncio
async def test_cache_hit_performance():
    """Test cache hit improves performance on repeated lookups."""
    envelope = {
        "actor_id": "person_dad",
        "body": {"participants": ["person_dad", "person_mom"]},
    }

    # First call (cache miss)
    message, context = make_test_call(envelope)
    result = await family_graph_resolve.run(message, context)
    metrics1 = family_graph_resolve.get_metrics()
    assert metrics1["cache_misses"] == 1
    assert metrics1["db_queries"] == 1

    # Second call (cache hit)
    message, context = make_test_call(envelope)
    result = await family_graph_resolve.run(message, context)
    metrics2 = family_graph_resolve.get_metrics()
    assert metrics2["cache_hits"] == 1
    assert metrics2["db_queries"] == 1  # No additional DB query


@pytest.mark.asyncio
async def test_cache_miss_fallback():
    """Test cache miss falls back to database query."""
    envelope = {
        "actor_id": "person_new_user",  # Not in cache
        "body": {"participants": ["person_new_user", "person_unknown"]},
    }

    message, context = make_test_call(envelope)
    result = await family_graph_resolve.run(message, context)

    # Should still work (fallback to friends context)
    assert result["social_context"] == "friends"
    assert result["social_intimacy"] == "LOW"

    # Check DB query happened
    metrics = family_graph_resolve.get_metrics()
    assert metrics["db_queries"] >= 1


@pytest.mark.asyncio
async def test_performance_under_8ms():
    """Test that average latency is under 8ms P95 budget."""
    envelope = {
        "actor_id": "person_dad",
        "body": {"participants": ["person_dad", "person_mom", "person_sharvi"]},
    }

    # Warm up cache
    message, context = make_test_call(envelope)
    result = await family_graph_resolve.run(message, context)

    # Measure cached performance
    latencies = []
    for _ in range(100):
        start = time.perf_counter()
        message, context = make_test_call(envelope)
        result = await family_graph_resolve.run(message, context)
        latencies.append((time.perf_counter() - start) * 1000)  # ms

    # Check P95 latency
    latencies.sort()
    p95_latency = latencies[94]  # 95th percentile

    assert p95_latency < 8.0, f"P95 latency {p95_latency:.2f}ms exceeds 8ms budget"


# ============================================================================
# Test: Error Handling
# ============================================================================


@pytest.mark.asyncio
async def test_missing_actor_id():
    """Test handling of missing actor_id (fallback to unknown_actor)."""
    envelope = {"body": {"participants": ["person_someone"]}}  # No actor_id

    message, context = make_test_call(envelope)
    result = await family_graph_resolve.run(message, context)

    # Should not crash, use default context
    assert result["social_context"] in ["solo", "friends"]


@pytest.mark.asyncio
async def test_max_participants_limit():
    """Test that max_participants_to_resolve config is respected."""
    # Create envelope with many participants
    many_participants = [f"person_{i}" for i in range(50)]

    envelope = {
        "actor_id": "person_dad",
        "body": {"participants": many_participants},
    }

    # Set max_participants to 5
    message, context = make_test_call(envelope)
    result = await family_graph_resolve.run(message, context, max_participants_to_resolve=5)

    # Should only process first 5
    assert result["num_participants"] == 5


# ============================================================================
# Test: Metrics & Observability
# ============================================================================


def test_get_metrics():
    """Test metrics retrieval."""
    metrics = family_graph_resolve.get_metrics()

    assert "cache_hits" in metrics
    assert "cache_misses" in metrics
    assert "cache_hit_rate" in metrics
    assert "db_queries" in metrics
    assert "relationship_type_counts" in metrics
    assert "lru_cache_size" in metrics


def test_reset_metrics():
    """Test metrics reset."""
    # Perform some operations
    family_graph_resolve._lookup_relationships("person_dad")

    # Reset
    family_graph_resolve.reset_metrics()

    # Check all metrics reset to 0
    metrics = family_graph_resolve.get_metrics()
    assert metrics["cache_hits"] == 0
    assert metrics["cache_misses"] == 0
    assert metrics["db_queries"] == 0


# ============================================================================
# Test: Edge Cases
# ============================================================================


@pytest.mark.asyncio
async def test_empty_envelope():
    """Test handling of empty envelope."""
    message, context = make_test_call({})
    result = await family_graph_resolve.run(message, context)

    # Should return solo event
    assert result["is_solo_event"] is True
    assert result["social_context"] == "solo"


@pytest.mark.asyncio
async def test_malformed_participants_not_list():
    """Test handling of malformed participants (not a list)."""
    envelope = {
        "actor_id": "person_dad",
        "body": {"participants": "not_a_list"},  # Wrong type
    }

    message, context = make_test_call(envelope)
    result = await family_graph_resolve.run(message, context)

    # Should handle gracefully (fallback to default)
    assert "social_context" in result


@pytest.mark.asyncio
async def test_json_serialization_valid():
    """Test that participant_roles_json is valid JSON."""
    envelope = {
        "actor_id": "person_dad",
        "body": {"participants": ["person_dad", "person_mom"]},
    }

    message, context = make_test_call(envelope)
    result = await family_graph_resolve.run(message, context)

    # Should be valid JSON
    roles = json.loads(result["participant_roles_json"])
    assert isinstance(roles, dict)
    assert "person_dad" in roles


@pytest.mark.asyncio
async def test_timestamp_format():
    """Test that social_resolved_at_utc is valid ISO 8601."""
    envelope = {"actor_id": "person_dad", "body": {"participants": []}}

    message, context = make_test_call(envelope)
    result = await family_graph_resolve.run(message, context)

    # Should be valid ISO 8601 timestamp
    timestamp = result["social_resolved_at_utc"]
    assert "T" in timestamp
    assert timestamp.endswith("Z") or "+" in timestamp


# ============================================================================
# Test: Integration Scenarios
# ============================================================================


@pytest.mark.asyncio
async def test_full_envelope_social_resolution():
    """Test full envelope processing (integration test)."""
    envelope = {
        "cognitive_trace_id": "trace-123",
        "tenant_id": "family-smith",
        "actor_id": "person_dad",
        "body": {
            "text": "Family game night",
            "participants": ["person_dad", "person_mom", "person_sharvi"],
            "event_time": "2025-11-17T20:00:00Z",
        },
    }

    message, context = make_test_call(envelope)
    result = await family_graph_resolve.run(message, context)

    # Verify complete output schema
    assert result["num_participants"] == 3
    assert result["participant_roles_json"]
    assert result["has_partner_present"] is True
    assert result["has_parent_present"] is False
    assert result["is_solo_event"] is False
    assert result["social_context"] == "nuclear_family"
    assert result["social_intimacy"] == "HIGH"
    assert result["social_resolved_at_utc"]

    # Verify participant roles
    roles = json.loads(result["participant_roles_json"])
    assert len(roles) == 3


@pytest.mark.asyncio
async def test_idempotency():
    """Test that running the same envelope multiple times produces same result."""
    envelope = {
        "actor_id": "person_dad",
        "body": {"participants": ["person_dad", "person_mom"]},
    }

    message, context = make_test_call(envelope)
    result1 = await family_graph_resolve.run(message, context)
    message, context = make_test_call(envelope)
    result2 = await family_graph_resolve.run(message, context)

    # Results should be identical (except timestamp)
    assert result1["num_participants"] == result2["num_participants"]
    assert result1["social_context"] == result2["social_context"]
    assert result1["social_intimacy"] == result2["social_intimacy"]
    assert result1["participant_roles_json"] == result2["participant_roles_json"]
    assert result1["participant_roles_json"] == result2["participant_roles_json"]
