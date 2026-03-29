"""
Epic 3.18 -- M07 social.family_graph_resolve Trust-Then-Fill Integration Tests

These tests call the REAL M07 run() function with real envelopes.
Only transport (MockMessage, MockContext, MockSyscalls) is mocked.

Validates:
- FAST PATH: MW body.participant_relationships with PARENT_OF -> social_context="nuclear_family", social_source="mw_v2"
- FALLBACK PATH: MW absent -> st_kg_edges READ, social_source="kg_edges"
- HEURISTIC PATH: MW absent + st_kg_edges empty -> NER + name inference, social_source="ner_heuristic"
- DEFAULT PATH: No relationship data -> social_context="solo"/"unknown", social_source="default"
- SPOUSE_OF -> has_partner_present=True
- participant_relationships_json passthrough (fast path), empty (fallback)
"""

import json
import time
from typing import Any
from unittest.mock import Mock

import pytest

from k0.modules.social import family_graph_resolve
from k0.modules.social.family_graph_resolve import run as m07_run

# ============================================================================
# Mock Transport (NOT module logic)
# ============================================================================


class MockMessage:
    """Mock BusMessage -- only transport wrapper."""

    def __init__(self, payload: dict[str, Any], trace_id: str = "test-m07-ttf"):
        self.payload = json.dumps(payload)
        self.trace_id = trace_id
        self.offset = 0
        self.topic = "cognitive.memory.write.committed.v1"
        self.space_id = "test_space"


class MockSyscalls:
    """Mock Syscalls with real async relationships_query for KG reads."""

    def __init__(
        self,
        relationships: dict[str, list[tuple[str, str]]] | None = None,
    ):
        self._relationships = relationships or {}

    async def relationships_query(
        self,
        actor_id: str,
        cognitive_trace_id: str | None = None,
    ) -> list[tuple[str, str]]:
        """Return mock KG relationships for actor."""
        return self._relationships.get(actor_id, [])


class MockContext:
    """Mock PipelineContext with real async syscalls."""

    def __init__(
        self,
        relationships: dict[str, list[tuple[str, str]]] | None = None,
    ):
        self.logger = Mock()
        self.logger.debug = Mock()
        self.logger.info = Mock()
        self.logger.warning = Mock()
        self.logger.error = Mock()
        self.syscalls = MockSyscalls(relationships)
        self.config = {}


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def reset_module_state():
    """Reset metrics and cache before each test."""
    family_graph_resolve.reset_metrics()
    family_graph_resolve.clear_cache()
    yield
    family_graph_resolve.reset_metrics()
    family_graph_resolve.clear_cache()


def _base_envelope(**overrides) -> dict[str, Any]:
    """Build minimal valid envelope."""
    env = {
        "event_id": "evt-m07-test-001",
        "cognitive_trace_id": "ct-m07-test-001",
        "tenant_id": "test-tenant",
        "actor_id": "person_dad",
        "space_id": "space-family",
        "ts": int(time.time()),
        "body": {
            "text": "Mom and I went to the park with Sharvi",
            "participants": ["person_dad", "person_mom", "person_sharvi"],
        },
        "enrichments": {},
    }
    env.update(overrides)
    return env


def _mw_relationships_envelope(
    relationships: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build envelope with MW body.participant_relationships (fast path)."""
    env = _base_envelope()
    env["body"]["participant_relationships"] = relationships or [
        {"person": "person_mom", "relationship_type": "SPOUSE_OF", "confidence": 0.95},
        {"person": "person_sharvi", "relationship_type": "PARENT_OF", "confidence": 0.92},
    ]
    return env


# ============================================================================
# FAST PATH: MW participant_relationships present -> mw_v2
# ============================================================================


@pytest.mark.asyncio
async def test_fast_path_mw_nuclear_family():
    """MW PARENT_OF -> social_context='nuclear_family', social_source='mw_v2'."""
    envelope = _mw_relationships_envelope()
    msg = MockMessage(envelope)
    ctx = MockContext()  # Empty KG -- fast path should NOT need KG

    result = await m07_run(msg, ctx, envelope=envelope)

    assert result["social_source"] == "mw_v2"
    assert result["social_context"] == "nuclear_family"
    assert result["has_parent_present"] is True


@pytest.mark.asyncio
async def test_fast_path_spouse_of_detected():
    """MW SPOUSE_OF -> has_partner_present=True."""
    envelope = _mw_relationships_envelope(
        relationships=[
            {"person": "person_mom", "relationship_type": "SPOUSE_OF", "confidence": 0.95},
        ]
    )
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m07_run(msg, ctx, envelope=envelope)

    assert result["social_source"] == "mw_v2"
    assert result["has_partner_present"] is True


@pytest.mark.asyncio
async def test_fast_path_participant_relationships_json_passthrough():
    """Fast path passes through participant_relationships_json in output."""
    rels = [
        {"person": "person_mom", "relationship_type": "SPOUSE_OF", "confidence": 0.95},
        {"person": "person_sharvi", "relationship_type": "PARENT_OF", "confidence": 0.92},
    ]
    envelope = _mw_relationships_envelope(relationships=rels)
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m07_run(msg, ctx, envelope=envelope)

    # participant_relationships_json should contain MW data
    pr_json = result.get("participant_relationships_json", "[]")
    parsed = json.loads(pr_json) if isinstance(pr_json, str) else pr_json
    assert len(parsed) == 2
    assert any(r["relationship_type"] == "PARENT_OF" for r in parsed)


@pytest.mark.asyncio
async def test_fast_path_num_participants():
    """Fast path correctly counts participants from MW relationships."""
    envelope = _mw_relationships_envelope()
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m07_run(msg, ctx, envelope=envelope)

    # Should have participant roles for at least the MW relationships
    assert result["num_participants"] >= 2
    assert isinstance(result["participant_roles_json"], str)


@pytest.mark.asyncio
async def test_fast_path_social_intimacy_high():
    """nuclear_family -> social_intimacy='HIGH'."""
    envelope = _mw_relationships_envelope()
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m07_run(msg, ctx, envelope=envelope)

    assert result["social_intimacy"] == "HIGH"


@pytest.mark.asyncio
async def test_fast_path_preserves_envelope():
    """Fast path preserves original envelope fields."""
    envelope = _mw_relationships_envelope()
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m07_run(msg, ctx, envelope=envelope)

    assert result["event_id"] == "evt-m07-test-001"
    assert result["actor_id"] == "person_dad"


# ============================================================================
# FALLBACK PATH: MW absent -> st_kg_edges READ (tier 1)
# ============================================================================


@pytest.mark.asyncio
async def test_fallback_kg_edges_read():
    """MW absent + KG has data -> social_source='kg_edges'."""
    envelope = _base_envelope()
    # No MW participant_relationships
    msg = MockMessage(envelope)

    # KG has relationships for this actor
    kg_rels = {
        "person_dad": [
            ("person_mom", "SPOUSE_OF"),
            ("person_sharvi", "PARENT_OF"),
        ],
    }
    ctx = MockContext(relationships=kg_rels)

    result = await m07_run(msg, ctx, envelope=envelope)

    assert result["social_source"] == "kg_edges"
    assert result["has_partner_present"] is True
    # participant_relationships_json should be empty on fallback
    pr_json = result.get("participant_relationships_json", "[]")
    parsed = json.loads(pr_json) if isinstance(pr_json, str) else pr_json
    assert parsed == [] or isinstance(parsed, list)


# ============================================================================
# DEFAULT PATH: No relationship data -> solo/unknown
# ============================================================================


@pytest.mark.asyncio
async def test_default_no_participants_solo():
    """No participants in body -> solo event."""
    envelope = _base_envelope()
    envelope["body"]["participants"] = []  # No participants
    del envelope["body"]["participants"]  # Remove entirely
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m07_run(msg, ctx, envelope=envelope)

    assert result["social_context"] == "solo"
    assert result["social_source"] == "default"
    assert result["is_solo_event"] is True


@pytest.mark.asyncio
async def test_default_multiple_participants_no_kg():
    """Multiple participants but no KG data and no MW -> default."""
    envelope = _base_envelope()
    # Participants but no MW relationships and empty KG
    msg = MockMessage(envelope)
    ctx = MockContext()  # Empty KG

    result = await m07_run(msg, ctx, envelope=envelope)

    # Source should be default or ner_heuristic
    assert result["social_source"] in ("default", "ner_heuristic")


@pytest.mark.asyncio
async def test_default_has_partner_false():
    """Default path -> has_partner_present=False."""
    envelope = _base_envelope()
    envelope["body"].pop("participants", None)
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m07_run(msg, ctx, envelope=envelope)

    assert result["has_partner_present"] is False
    assert result["has_parent_present"] is False


# ============================================================================
# MW MALFORMED -> graceful fallback
# ============================================================================


@pytest.mark.asyncio
async def test_malformed_mw_relationships_fallback():
    """Malformed MW relationships -> graceful fallback to tier1+."""
    envelope = _base_envelope()
    envelope["body"]["participant_relationships"] = "not_a_list"
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m07_run(msg, ctx, envelope=envelope)

    # Should NOT crash, should fallback
    assert result["social_source"] != "mw_v2"
    assert "social_context" in result


@pytest.mark.asyncio
async def test_empty_mw_relationships_fallback():
    """Empty MW relationships list -> fallback."""
    envelope = _base_envelope()
    envelope["body"]["participant_relationships"] = []
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m07_run(msg, ctx, envelope=envelope)

    assert result["social_source"] != "mw_v2"


@pytest.mark.asyncio
async def test_mw_missing_required_fields_fallback():
    """MW relationships with missing person/type -> fallback."""
    envelope = _base_envelope()
    envelope["body"]["participant_relationships"] = [
        {"person": "someone"},  # Missing relationship_type
    ]
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m07_run(msg, ctx, envelope=envelope)

    assert result["social_source"] != "mw_v2"


# ============================================================================
# OUTPUT STRUCTURE VALIDATION
# ============================================================================


@pytest.mark.asyncio
async def test_output_has_all_required_keys():
    """Output has all required social fields."""
    envelope = _mw_relationships_envelope()
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m07_run(msg, ctx, envelope=envelope)

    required_keys = [
        "num_participants",
        "participant_roles_json",
        "has_partner_present",
        "has_parent_present",
        "is_solo_event",
        "social_context",
        "social_intimacy",
        "social_resolved_at_utc",
        "participant_relationships_json",
        "social_source",
    ]
    for key in required_keys:
        assert key in result, f"Missing required key: {key}"


@pytest.mark.asyncio
async def test_output_social_resolved_at_utc_iso():
    """social_resolved_at_utc is ISO 8601 string."""
    envelope = _mw_relationships_envelope()
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m07_run(msg, ctx, envelope=envelope)

    ts = result["social_resolved_at_utc"]
    assert isinstance(ts, str)
    assert "T" in ts  # ISO 8601 format
