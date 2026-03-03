"""
Epic 3.18 -- P02 Signal Fix End-to-End Integration Tests

These tests call REAL module run() functions in P02 pipeline order.
FULL PIPELINE: M02 -> M04 -> M07 -> M08 -> M06 -> M13
Each stage receives the enriched envelope from the previous stage.

Validates 3 scenarios:
1. FAST PATH E2E: Full MW v2 envelope -> all modules -> correct outputs
2. FALLBACK PATH E2E: Minimal envelope (body.text only) -> graceful degradation
3. PARTIAL MW E2E: Some MW fields present, others missing -> independent fast/fallback

NO MOCK THEATER: Real module logic executes on real envelopes.
"""

import json
import time
from typing import Any
from unittest.mock import Mock

import pytest

# Import REAL module run functions
from k0.modules.affect.analyze import reset_metrics as m04_reset
from k0.modules.affect.analyze import run as m04_run
from k0.modules.builders.hipp_events_row import reset_metrics as m13_reset
from k0.modules.builders.hipp_events_row import run as m13_run
from k0.modules.context.temporal_profile import reset_metrics as m08_reset
from k0.modules.context.temporal_profile import run as m08_run
from k0.modules.hippocampus.semantic_project import run as m02_run
from k0.modules.salience.score import reset_metrics as m06_reset
from k0.modules.salience.score import run as m06_run
from k0.modules.social.family_graph_resolve import clear_cache as m07_clear_cache
from k0.modules.social.family_graph_resolve import reset_metrics as m07_reset
from k0.modules.social.family_graph_resolve import run as m07_run

# ============================================================================
# Mock Transport (ONLY these are mocked -- module logic is REAL)
# ============================================================================


class MockMessage:
    """Mock BusMessage -- transport wrapper only."""

    def __init__(self, payload: dict[str, Any], trace_id: str = "test-e2e-p02"):
        self.payload = json.dumps(payload).encode("utf-8")
        self.trace_id = trace_id
        self.offset = 0
        self.topic = "cognitive.memory.write.committed.v1"
        self.space_id = "test_space"


class MockSyscalls:
    """Mock Syscalls -- empty KG for clean tests."""

    async def relationships_query(self, actor_id: str, cognitive_trace_id: str | None = None):
        return []


class MockContext:
    """Mock PipelineContext with real async syscalls."""

    def __init__(self):
        self.logger = Mock()
        self.logger.debug = Mock()
        self.logger.info = Mock()
        self.logger.warning = Mock()
        self.logger.error = Mock()
        self.syscalls = MockSyscalls()
        self.config = {}
        self.preloaded_models = None


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def reset_all_modules():
    """Reset ALL module metrics/caches before each test."""
    m04_reset()
    m06_reset()
    m07_reset()
    m07_clear_cache()
    m08_reset()
    m13_reset()
    yield
    m04_reset()
    m06_reset()
    m07_reset()
    m07_clear_cache()
    m08_reset()
    m13_reset()


async def _run_p02_pipeline(envelope: dict[str, Any]) -> dict[str, Any]:
    """Run the real P02 pipeline stages in order.

    Pipeline stage order (from P02 dossier):
    Stage 20: M02 semantic_project (NER + embedding + KG)
    Stage 30: M04 affect.analyze (trust-then-fill affect)
    Stage 32: M07 social.family_graph_resolve (trust-then-fill social)
    Stage 33: M08 temporal_profile (temporal + spatial fallback chain)
    Stage 55: M06 salience.score (corrected salience from M04+M07 outputs)
    Stage 60: M13 hipp_events_row (assemble final row)
    """
    msg = MockMessage(envelope)
    ctx = MockContext()

    # Stage 20: M02 semantic_project
    enriched = await m02_run(msg, ctx, envelope=envelope)

    # Stage 30: M04 affect.analyze
    msg_m04 = MockMessage(enriched)
    enriched = await m04_run(msg_m04, ctx, envelope=enriched)

    # Stage 32: M07 social.family_graph_resolve
    msg_m07 = MockMessage(enriched)
    enriched = await m07_run(msg_m07, ctx, envelope=enriched)

    # Stage 33: M08 temporal_profile
    msg_m08 = MockMessage(enriched)
    enriched = await m08_run(msg_m08, ctx, envelope=enriched)

    # Stage 55: M06 salience.score
    # M06 needs event.social_context and affect_intensity in envelope
    if "event" not in enriched:
        enriched["event"] = {}
    enriched["event"]["social_context"] = enriched.get("social_context", "unknown")
    enriched["event"]["event_time_utc"] = enriched.get("event_time_utc")
    enriched["affect_intensity"] = enriched.get("affect_valence", 0.5)
    msg_m06 = MockMessage(enriched)
    enriched = await m06_run(msg_m06, ctx, envelope=enriched)

    # Stage 60: M13 hipp_events_row
    msg_m13 = MockMessage(enriched)
    result = await m13_run(msg_m13, ctx, envelope=enriched, validate_required_fields=False)

    # Return both the enriched envelope and the final row
    return {
        "enriched_envelope": enriched,
        "hipp_events_row": result.get("hipp_events_row", {}),
    }


# ============================================================================
# FAST PATH E2E: Full MW v2 envelope
# ============================================================================


def _fast_path_envelope() -> dict[str, Any]:
    """Build a FULL MW v2 envelope for fast path E2E."""
    now_ts = int(time.time())
    return {
        "event_id": "evt-e2e-fast-001",
        "cognitive_trace_id": "ct-e2e-fast-001",
        "tenant_id": "test-tenant",
        "actor_id": "actor-dad",
        "actor": "actor-dad",
        "space_id": "space-family",
        "ts": now_ts,
        "wal_pos": 1001,
        "device_id": "dev-001",
        "owner_id": "actor-dad",
        "retention_policy_id": "rp-standard",
        "body": {
            "text": "Mom and I went to Olive Garden yesterday evening for a wonderful family dinner",
            "language": "en",
            "participants": ["actor-dad", "person-mom"],
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
            ],
            # MW v2 narrative
            "narrative": {
                "thread_id": "uuid-1",
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
            # MW v2 cognitive dimensions
            "k1_signal_version": "2.0",
        },
        "enrichments": {},
    }


@pytest.mark.asyncio
async def test_fast_path_e2e_social_context():
    """Fast path E2E: social_context = 'nuclear_family' (not 'friends')."""
    envelope = _fast_path_envelope()
    result = await _run_p02_pipeline(envelope)
    enriched = result["enriched_envelope"]

    assert enriched["social_context"] == "nuclear_family"


@pytest.mark.asyncio
async def test_fast_path_e2e_salience_high():
    """Fast path E2E: salience_score > 0.70 (not 0.41)."""
    envelope = _fast_path_envelope()
    result = await _run_p02_pipeline(envelope)
    enriched = result["enriched_envelope"]

    assert enriched["salience_score"] > 0.70
    assert enriched["salience_band"] == "HIGH"


@pytest.mark.asyncio
async def test_fast_path_e2e_has_parent():
    """Fast path E2E: has_parent_present = True (not False)."""
    envelope = _fast_path_envelope()
    result = await _run_p02_pipeline(envelope)
    enriched = result["enriched_envelope"]

    assert enriched["has_parent_present"] is True


@pytest.mark.asyncio
async def test_fast_path_e2e_affect_dominance():
    """Fast path E2E: affect_dominance = 0.7, affect_source = 'mw_v2'."""
    envelope = _fast_path_envelope()
    result = await _run_p02_pipeline(envelope)
    enriched = result["enriched_envelope"]

    assert enriched["affect_dominance"] == 0.7
    assert enriched["affect_source"] == "mw_v2"


@pytest.mark.asyncio
async def test_fast_path_e2e_temporal_source():
    """Fast path E2E: temporal_source = 'mw_resolved'."""
    envelope = _fast_path_envelope()
    result = await _run_p02_pipeline(envelope)
    enriched = result["enriched_envelope"]

    assert enriched["temporal_source"] == "mw_resolved"


@pytest.mark.asyncio
async def test_fast_path_e2e_narrative():
    """Fast path E2E: narrative_thread_id = 'uuid-1'."""
    envelope = _fast_path_envelope()
    result = await _run_p02_pipeline(envelope)
    row = result["hipp_events_row"]

    assert row["narrative_thread_id"] == "uuid-1"


@pytest.mark.asyncio
async def test_fast_path_e2e_k1_signal_version():
    """Fast path E2E: k1_signal_version = '2.0'."""
    envelope = _fast_path_envelope()
    result = await _run_p02_pipeline(envelope)
    row = result["hipp_events_row"]

    assert row["k1_signal_version"] == "2.0"


@pytest.mark.asyncio
async def test_fast_path_e2e_provenance_fields():
    """Fast path E2E: all provenance fields populated."""
    envelope = _fast_path_envelope()
    result = await _run_p02_pipeline(envelope)
    enriched = result["enriched_envelope"]

    assert enriched["affect_source"] == "mw_v2"
    assert enriched["social_source"] == "mw_v2"
    assert enriched["temporal_source"] == "mw_resolved"


# ============================================================================
# FALLBACK PATH E2E: Minimal envelope (body.text only)
# ============================================================================


def _fallback_path_envelope() -> dict[str, Any]:
    """Build a MINIMAL envelope with body.text only -- NO MW signals."""
    now_ts = int(time.time())
    return {
        "event_id": "evt-e2e-fallback-001",
        "cognitive_trace_id": "ct-e2e-fallback-001",
        "tenant_id": "test-tenant",
        "actor_id": "actor-dad",
        "actor": "actor-dad",
        "space_id": "space-family",
        "ts": now_ts,
        "wal_pos": 1002,
        "device_id": "dev-002",
        "owner_id": "actor-dad",
        "retention_policy_id": "rp-standard",
        "body": {
            "text": "Mom and I went to Olive Garden yesterday evening for dinner",
            # NO body.affect
            # NO body.participant_relationships
            # NO body.temporal
            # NO body.location_name
        },
        "enrichments": {},
    }


@pytest.mark.asyncio
async def test_fallback_e2e_no_crash():
    """Fallback path E2E: pipeline does NOT crash on missing MW fields."""
    envelope = _fallback_path_envelope()
    result = await _run_p02_pipeline(envelope)

    # Must complete without exception
    assert result["enriched_envelope"] is not None
    assert result["hipp_events_row"] is not None


@pytest.mark.asyncio
async def test_fallback_e2e_event_time_not_null():
    """Fallback path E2E: event_time_utc is NOT null."""
    envelope = _fallback_path_envelope()
    result = await _run_p02_pipeline(envelope)
    enriched = result["enriched_envelope"]

    assert enriched["event_time_utc"] is not None


@pytest.mark.asyncio
async def test_fallback_e2e_m04_not_mw_v2():
    """Fallback path E2E: M04 ran full inference (not MW passthrough)."""
    envelope = _fallback_path_envelope()
    result = await _run_p02_pipeline(envelope)
    enriched = result["enriched_envelope"]

    # No MW affect -> should NOT be mw_v2
    assert enriched["affect_source"] in ("ultrabert", "vader", "default")


@pytest.mark.asyncio
async def test_fallback_e2e_m02_ner_ran():
    """Fallback path E2E: M02 NER detected entities from text."""
    envelope = _fallback_path_envelope()
    result = await _run_p02_pipeline(envelope)
    enriched = result["enriched_envelope"]

    # M02 should have NER outputs
    assert "ner_temporal_entities" in enriched
    assert "ner_loc_entities" in enriched
    assert "ner_per_entities" in enriched


@pytest.mark.asyncio
async def test_fallback_e2e_provenance_fields():
    """Fallback path E2E: all provenance fields populated (not mw_v2)."""
    envelope = _fallback_path_envelope()
    result = await _run_p02_pipeline(envelope)
    enriched = result["enriched_envelope"]

    assert enriched["affect_source"] in ("ultrabert", "vader", "default")
    assert enriched["social_source"] in ("kg_edges", "ner_heuristic", "default")
    assert enriched["temporal_source"] in ("ner_temporal", "envelope_ts", "event_time", "now")


@pytest.mark.asyncio
async def test_fallback_e2e_graceful_degradation():
    """Fallback path E2E: all modules produce valid outputs despite missing MW."""
    envelope = _fallback_path_envelope()
    result = await _run_p02_pipeline(envelope)
    enriched = result["enriched_envelope"]

    # All modules produced results
    assert isinstance(enriched.get("affect_valence"), float)
    assert enriched.get("social_context") is not None
    assert enriched.get("event_time_utc") is not None
    assert isinstance(enriched.get("salience_score"), float)
    assert 0.0 <= enriched["salience_score"] <= 1.0


# ============================================================================
# PARTIAL MW E2E: Some MW fields present, others missing
# ============================================================================


def _partial_mw_envelope() -> dict[str, Any]:
    """Build envelope with SOME MW fields present, others missing."""
    now_ts = int(time.time())
    return {
        "event_id": "evt-e2e-partial-001",
        "cognitive_trace_id": "ct-e2e-partial-001",
        "tenant_id": "test-tenant",
        "actor_id": "actor-dad",
        "actor": "actor-dad",
        "space_id": "space-family",
        "ts": now_ts,
        "wal_pos": 1003,
        "device_id": "dev-003",
        "owner_id": "actor-dad",
        "retention_policy_id": "rp-standard",
        "body": {
            "text": "Sharvi and I played at the park this morning",
            # body.affect PRESENT (MW fast path for M04)
            "affect": {
                "valence": 0.75,
                "arousal": 0.5,
                "dominance": 0.6,
            },
            # body.participant_relationships MISSING (fallback for M07)
            # body.temporal MISSING (fallback for M08)
            # body.location_name PRESENT (MW fast path for spatial)
            "location_name": "Central Park",
            "location_type": "park",
        },
        "enrichments": {},
    }


@pytest.mark.asyncio
async def test_partial_mw_e2e_affect_fast_social_fallback():
    """Partial MW: M04 uses MW affect (fast), M07 uses fallback."""
    envelope = _partial_mw_envelope()
    result = await _run_p02_pipeline(envelope)
    enriched = result["enriched_envelope"]

    # M04 should use MW affect (fast path)
    assert enriched["affect_source"] == "mw_v2"

    # M07 should use fallback (no MW relationships)
    assert enriched["social_source"] != "mw_v2"


@pytest.mark.asyncio
async def test_partial_mw_e2e_temporal_fallback_location_fast():
    """Partial MW: M08 temporal uses fallback, spatial uses MW location."""
    envelope = _partial_mw_envelope()
    result = await _run_p02_pipeline(envelope)
    enriched = result["enriched_envelope"]

    # Temporal: no body.temporal -> fallback to envelope.ts or NER
    assert enriched["temporal_source"] != "mw_resolved"

    # Spatial: body.location_name present -> MW location
    assert enriched["location_source"] == "mw_location"
    assert enriched["location_name"] == "Central Park"


@pytest.mark.asyncio
async def test_partial_mw_e2e_independent_decisions():
    """Partial MW: each module independently decides fast/fallback."""
    envelope = _partial_mw_envelope()
    result = await _run_p02_pipeline(envelope)
    enriched = result["enriched_envelope"]

    # All modules completed
    assert enriched.get("affect_source") is not None
    assert enriched.get("social_source") is not None
    assert enriched.get("temporal_source") is not None

    # Salience still computes correctly
    assert 0.0 <= enriched.get("salience_score", 0) <= 1.0


@pytest.mark.asyncio
async def test_partial_mw_e2e_row_built():
    """Partial MW: M13 still builds complete row."""
    envelope = _partial_mw_envelope()
    result = await _run_p02_pipeline(envelope)
    row = result["hipp_events_row"]

    # Row should be complete
    assert len(row) > 100  # At least 100+ columns
    assert "k1_signal_version" in row
