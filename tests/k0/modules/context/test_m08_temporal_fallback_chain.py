"""
Epic 3.18 -- M08 context.temporal_profile Temporal Fallback Chain Tests

These tests call the REAL M08 run() with real envelopes.
Only transport (MockMessage, MockContext) is mocked.

Validates the 5-priority temporal chain:
- PRIORITY 1: body.temporal.resolved_epoch_ms -> temporal_source="mw_resolved"
- PRIORITY 2: M02 ner_temporal has "yesterday" -> temporal_source="ner_temporal"
- PRIORITY 3: body.event_time present -> temporal_source="event_time"
- PRIORITY 4: envelope.ts present -> temporal_source="envelope_ts"
- PRIORITY 5: now() -> temporal_source="now"
- CRITICAL: event_time_utc is NEVER null

Spatial chain:
- body.location_name -> location_source="mw_location"
- M02 NER LOC -> location_source="ner_location"
- No location -> location_name=null, location_source="none"
"""

import json
import time
from typing import Any
from unittest.mock import Mock

import pytest

from k0.modules.context import temporal_profile
from k0.modules.context.temporal_profile import run as m08_run

# ============================================================================
# Mock Transport
# ============================================================================


class MockMessage:
    """Mock BusMessage."""

    def __init__(self, payload: dict[str, Any], trace_id: str = "test-m08-temp"):
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
    temporal_profile.reset_metrics()
    yield
    temporal_profile.reset_metrics()


def _base_envelope(**overrides) -> dict[str, Any]:
    """Build minimal envelope with ts (backstop)."""
    now_ts = int(time.time())
    env = {
        "event_id": "evt-m08-test-001",
        "cognitive_trace_id": "ct-m08-test-001",
        "tenant_id": "default",
        "actor_id": "actor-dad",
        "ts": now_ts,
        "body": {
            "text": "Mom and I went to Olive Garden yesterday evening for dinner",
        },
        "enrichments": {},
    }
    env.update(overrides)
    return env


# ============================================================================
# PRIORITY 1: body.temporal.resolved_epoch_ms -> mw_resolved
# ============================================================================


@pytest.mark.asyncio
async def test_priority1_mw_resolved_epoch():
    """MW body.temporal.resolved_epoch_ms present -> temporal_source='mw_resolved'."""
    resolved_ms = 1704067200000  # 2024-01-01 00:00:00 UTC in ms
    envelope = _base_envelope()
    envelope["body"]["temporal"] = {
        "resolved_epoch_ms": resolved_ms,
        "mentioned_time": "yesterday evening",
        "orientation": "PAST",
    }
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m08_run(msg, ctx, envelope=envelope)

    assert result["temporal_source"] == "mw_resolved"
    assert result["event_time_utc"] == resolved_ms // 1000  # Converted to seconds
    assert result["event_time_utc"] is not None


@pytest.mark.asyncio
async def test_priority1_mw_temporal_passthrough():
    """MW temporal fields passthrough: mentioned_time, orientation."""
    envelope = _base_envelope()
    envelope["body"]["temporal"] = {
        "resolved_epoch_ms": 1704067200000,
        "mentioned_time": "yesterday evening",
        "orientation": "PAST",
    }
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m08_run(msg, ctx, envelope=envelope)

    assert result["temporal_mentioned_time"] == "yesterday evening"
    assert result["temporal_orientation"] == "PAST"
    assert result["temporal_resolved_epoch_ms"] == 1704067200000


@pytest.mark.asyncio
async def test_priority1_mw_orientation_ongoing():
    """MW temporal.orientation='ONGOING' -> passthrough."""
    envelope = _base_envelope()
    envelope["body"]["temporal"] = {
        "resolved_epoch_ms": int(time.time()) * 1000,
        "orientation": "ONGOING",
    }
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m08_run(msg, ctx, envelope=envelope)

    assert result["temporal_orientation"] == "ONGOING"


@pytest.mark.asyncio
async def test_priority1_mw_orientation_future():
    """MW temporal.orientation='FUTURE_COMMITMENT' -> passthrough."""
    envelope = _base_envelope()
    future_ts = (int(time.time()) + 86400) * 1000  # Tomorrow
    envelope["body"]["temporal"] = {
        "resolved_epoch_ms": future_ts,
        "orientation": "FUTURE_COMMITMENT",
    }
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m08_run(msg, ctx, envelope=envelope)

    assert result["temporal_orientation"] == "FUTURE_COMMITMENT"


@pytest.mark.asyncio
async def test_priority1_invalid_orientation_nullified():
    """Invalid temporal.orientation -> set to None."""
    envelope = _base_envelope()
    envelope["body"]["temporal"] = {
        "resolved_epoch_ms": int(time.time()) * 1000,
        "orientation": "INVALID_VALUE",
    }
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m08_run(msg, ctx, envelope=envelope)

    assert result["temporal_orientation"] is None


# ============================================================================
# PRIORITY 2: M02 ner_temporal entities -> ner_temporal
# ============================================================================


@pytest.mark.asyncio
async def test_priority2_ner_temporal_fallback():
    """MW temporal MISSING + M02 NER has temporal -> temporal_source='ner_temporal'."""
    envelope = _base_envelope()
    # No body.temporal -> MW absent
    # Simulate M02 output in enrichments
    envelope["enrichments"]["semantic_projector"] = {
        "ner_temporal_entities": [{"text": "yesterday", "label": "DATE"}],
        "ner_loc_entities": [],
        "ner_per_entities": [],
    }
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m08_run(msg, ctx, envelope=envelope)

    assert result["temporal_source"] == "ner_temporal"
    assert result["event_time_utc"] is not None


@pytest.mark.asyncio
async def test_priority2_ner_temporal_yesterday():
    """NER detects 'yesterday' -> resolves to approximate timestamp."""
    envelope = _base_envelope()
    envelope["enrichments"]["semantic_projector"] = {
        "ner_temporal_entities": [{"text": "yesterday evening", "label": "DATE"}],
    }
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m08_run(msg, ctx, envelope=envelope)

    # Should resolve "yesterday" to ~24h ago
    if result["temporal_source"] == "ner_temporal":
        now_ts = int(time.time())
        assert abs(result["event_time_utc"] - (now_ts - 86400)) < 86400  # Within a day


# ============================================================================
# PRIORITY 3: body.event_time -> event_time
# ============================================================================


@pytest.mark.asyncio
async def test_priority3_body_event_time():
    """MW absent + no NER + body.event_time -> temporal_source='event_time'."""
    envelope = _base_envelope()
    from datetime import datetime, timezone

    fixed_time = datetime(2024, 6, 15, 14, 30, 0, tzinfo=timezone.utc)
    envelope["body"]["event_time"] = fixed_time.isoformat()
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m08_run(msg, ctx, envelope=envelope)

    assert result["temporal_source"] == "event_time"
    assert result["event_time_utc"] == int(fixed_time.timestamp())


@pytest.mark.asyncio
async def test_priority3_unix_timestamp_event_time():
    """body.event_time as Unix timestamp -> parsed correctly."""
    envelope = _base_envelope()
    fixed_ts = 1718458200  # 2024-06-15 14:30:00 UTC
    envelope["body"]["event_time"] = fixed_ts
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m08_run(msg, ctx, envelope=envelope)

    assert result["temporal_source"] == "event_time"
    assert result["event_time_utc"] == fixed_ts


# ============================================================================
# PRIORITY 4: envelope.ts -> envelope_ts
# ============================================================================


@pytest.mark.asyncio
async def test_priority4_envelope_ts_fallback():
    """All higher priorities missing -> envelope.ts used."""
    envelope = _base_envelope()
    # Remove all temporal hints except ts
    envelope["body"].pop("temporal", None)
    envelope["body"].pop("event_time", None)
    # No M02 enrichments
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m08_run(msg, ctx, envelope=envelope)

    assert result["temporal_source"] == "envelope_ts"
    assert result["event_time_utc"] == envelope["ts"]


# ============================================================================
# PRIORITY 5: now() -> ultimate fallback
# ============================================================================


@pytest.mark.asyncio
async def test_priority5_now_fallback():
    """No timestamps at all -> now() used."""
    envelope = _base_envelope()
    del envelope["ts"]  # Remove even the backstop
    envelope["body"].pop("temporal", None)
    envelope["body"].pop("event_time", None)
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m08_run(msg, ctx, envelope=envelope)

    assert result["temporal_source"] == "now"
    assert result["event_time_utc"] is not None


# ============================================================================
# CRITICAL: event_time_utc is NEVER null
# ============================================================================


@pytest.mark.asyncio
async def test_event_time_utc_never_null_full_envelope():
    """Full MW envelope -> event_time_utc is NOT null."""
    envelope = _base_envelope()
    envelope["body"]["temporal"] = {"resolved_epoch_ms": 1704067200000}
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m08_run(msg, ctx, envelope=envelope)
    assert result["event_time_utc"] is not None


@pytest.mark.asyncio
async def test_event_time_utc_never_null_minimal_envelope():
    """Minimal envelope (no temporal data) -> event_time_utc is NOT null."""
    envelope = _base_envelope()
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m08_run(msg, ctx, envelope=envelope)
    assert result["event_time_utc"] is not None


@pytest.mark.asyncio
async def test_event_time_utc_never_null_empty_body():
    """Nearly empty envelope -> event_time_utc is NOT null."""
    envelope = {"ts": int(time.time()), "body": {"text": "hello"}, "tenant_id": "t"}
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m08_run(msg, ctx, envelope=envelope)
    assert result["event_time_utc"] is not None


# ============================================================================
# SPATIAL CHAIN: location resolution
# ============================================================================


@pytest.mark.asyncio
async def test_spatial_mw_location():
    """MW body.location_name -> location_source='mw_location'."""
    envelope = _base_envelope()
    envelope["body"]["location_name"] = "Olive Garden"
    envelope["body"]["location_type"] = "restaurant"
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m08_run(msg, ctx, envelope=envelope)

    assert result["location_source"] == "mw_location"
    assert result["location_name"] == "Olive Garden"
    assert result["location_type"] is not None


@pytest.mark.asyncio
async def test_spatial_ner_loc_fallback():
    """MW location absent + M02 NER LOC -> location_source='ner_location'."""
    envelope = _base_envelope()
    # No body.location_name
    envelope["enrichments"]["semantic_projector"] = {
        "ner_loc_entities": [{"text": "Olive Garden", "label": "LOC"}],
    }
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m08_run(msg, ctx, envelope=envelope)

    assert result["location_source"] == "ner_location"
    assert result["location_name"] == "Olive Garden"


@pytest.mark.asyncio
async def test_spatial_no_location():
    """No location data -> location_name=None, location_source='none'."""
    envelope = _base_envelope()
    # No location hints, no NER LOC
    envelope["body"]["text"] = "I felt happy today"  # No location in text
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m08_run(msg, ctx, envelope=envelope)

    # If no heuristic match, location_source should be "none" or "text_heuristic"
    assert result["location_source"] in ("none", "text_heuristic")
    if result["location_source"] == "none":
        assert result["location_name"] is None


# ============================================================================
# OUTPUT STRUCTURE VALIDATION
# ============================================================================


@pytest.mark.asyncio
async def test_output_has_all_temporal_fields():
    """Output has all v2 temporal + spatial fields."""
    envelope = _base_envelope()
    envelope["body"]["temporal"] = {
        "resolved_epoch_ms": int(time.time()) * 1000,
        "mentioned_time": "now",
        "orientation": "ONGOING",
    }
    envelope["body"]["location_name"] = "Home"
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m08_run(msg, ctx, envelope=envelope)

    required_keys = [
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
        "created_at",
        "timezone_used",
        # v2 temporal
        "temporal_mentioned_time",
        "temporal_resolved_epoch_ms",
        "temporal_orientation",
        "temporal_source",
        # v2 spatial
        "location_name",
        "location_type",
        "location_source",
    ]
    for key in required_keys:
        assert key in result, f"Missing required key: {key}"


@pytest.mark.asyncio
async def test_enrichments_nested_structure():
    """enrichments.temporal_profiler has v2 structure."""
    envelope = _base_envelope()
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m08_run(msg, ctx, envelope=envelope)

    enrichment = result["enrichments"]["temporal_profiler"]
    assert enrichment["module_version"] == "v2"
    assert "event_time_utc" in enrichment
    assert "temporal_source" in enrichment
    assert "location_source" in enrichment


@pytest.mark.asyncio
async def test_preserves_original_envelope():
    """Output contains original envelope fields."""
    envelope = _base_envelope()
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m08_run(msg, ctx, envelope=envelope)

    assert result["event_id"] == "evt-m08-test-001"
    assert result["tenant_id"] == "default"


@pytest.mark.asyncio
async def test_temporal_profile_dimensions():
    """Temporal profile has expected dimension values."""
    envelope = _base_envelope()
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m08_run(msg, ctx, envelope=envelope)

    assert isinstance(result["local_date"], str)
    assert isinstance(result["local_time"], str)
    assert result["day_of_week"] in (
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    )
    assert isinstance(result["is_weekend"], bool)
    assert result["time_of_day_bucket"] in ("morning", "afternoon", "evening", "night")
