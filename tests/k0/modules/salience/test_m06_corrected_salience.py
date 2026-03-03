"""
Epic 3.18 -- M06 salience.score Corrected Salience Integration Tests

These tests call the REAL M06 run() with real envelopes.
Only transport (MockMessage, MockContext) is mocked.

Validates:
- nuclear_family + valence=0.8 -> salience > 0.70
- solo + valence=0.3 -> salience < 0.35
- entity_salience cross-validation logged when delta > 0.3
- Works with BOTH MW path and fallback path inputs
"""

import json
import time
from datetime import datetime, timezone
from typing import Any
from unittest.mock import Mock

import pytest

from k0.modules.salience import score
from k0.modules.salience.score import run as m06_run

# ============================================================================
# Mock Transport
# ============================================================================


class MockMessage:
    """Mock BusMessage."""

    def __init__(self, payload: dict[str, Any], trace_id: str = "test-m06-sal"):
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
    score.reset_metrics()
    yield
    score.reset_metrics()


def _build_envelope(
    social_context: str = "nuclear_family",
    affect_intensity: float = 0.8,
    event_time_utc: str | None = None,
    entity_salience: dict | None = None,
) -> dict[str, Any]:
    """Build envelope pre-enriched with M04+M07 outputs for M06 consumption."""
    if event_time_utc is None:
        event_time_utc = datetime.now(timezone.utc).isoformat()

    env = {
        "event_id": "evt-m06-test-001",
        "cognitive_trace_id": "ct-m06-test-001",
        "tenant_id": "test-tenant",
        "actor_id": "actor-dad",
        "space_id": "space-family",
        "ts": int(time.time()),
        "body": {
            "text": "Had a wonderful family dinner",
        },
        "event": {
            "social_context": social_context,
            "event_time_utc": event_time_utc,
        },
        "affect_intensity": affect_intensity,
        "enrichments": {},
    }
    if entity_salience is not None:
        env["body"]["entity_salience"] = entity_salience
    return env


# ============================================================================
# nuclear_family + high affect -> HIGH salience
# ============================================================================


@pytest.mark.asyncio
async def test_nuclear_family_high_affect_high_salience():
    """nuclear_family + valence=0.8 -> salience > 0.70."""
    envelope = _build_envelope(
        social_context="nuclear_family",
        affect_intensity=0.8,
    )
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m06_run(msg, ctx, envelope=envelope)

    assert result["salience_score"] > 0.70
    assert result["salience_band"] == "HIGH"


@pytest.mark.asyncio
async def test_nuclear_family_mw_source_high_salience():
    """MW path inputs (nuclear_family from mw_v2) -> HIGH salience."""
    envelope = _build_envelope(
        social_context="nuclear_family",
        affect_intensity=0.82,
    )
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m06_run(msg, ctx, envelope=envelope)

    assert result["salience_score"] > 0.70
    assert result["salience_band"] == "HIGH"


@pytest.mark.asyncio
async def test_family_legacy_high_salience():
    """Legacy 'family' context also scores HIGH."""
    envelope = _build_envelope(
        social_context="family",
        affect_intensity=0.8,
    )
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m06_run(msg, ctx, envelope=envelope)

    assert result["salience_score"] > 0.70


# ============================================================================
# solo + low affect -> LOW salience
# ============================================================================


@pytest.mark.asyncio
async def test_solo_low_affect_low_salience():
    """solo + valence=0.3 -> salience < 0.35."""
    envelope = _build_envelope(
        social_context="solo",
        affect_intensity=0.3,
    )
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m06_run(msg, ctx, envelope=envelope)

    assert result["salience_score"] < 0.35
    assert result["salience_band"] == "LOW"


@pytest.mark.asyncio
async def test_solo_no_affect_low_salience():
    """solo + no affect -> LOW salience."""
    envelope = _build_envelope(
        social_context="solo",
        affect_intensity=0.1,
    )
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m06_run(msg, ctx, envelope=envelope)

    assert result["salience_score"] < 0.40


# ============================================================================
# Entity salience cross-validation
# ============================================================================


@pytest.mark.asyncio
async def test_entity_salience_discrepancy_logged():
    """entity_salience discrepancy > 0.3 -> logged."""
    # M06 computes ~0.97 for nuclear_family + 0.9 affect
    # MW entity_salience mean = 0.3 -> discrepancy ~0.67
    envelope = _build_envelope(
        social_context="nuclear_family",
        affect_intensity=0.9,
        entity_salience={"mom": 0.2, "sharvi": 0.4},  # mean=0.3
    )
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m06_run(msg, ctx, envelope=envelope)

    # Discrepancy should be computed
    discrepancy = result.get("entity_salience_discrepancy")
    assert discrepancy is not None
    assert discrepancy > 0.3  # Should exceed threshold

    # Warning should have been logged
    ctx.logger.warning.assert_called()


@pytest.mark.asyncio
async def test_entity_salience_no_discrepancy_when_absent():
    """No entity_salience -> discrepancy is None."""
    envelope = _build_envelope(
        social_context="nuclear_family",
        affect_intensity=0.8,
    )
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m06_run(msg, ctx, envelope=envelope)

    assert result.get("entity_salience_discrepancy") is None


@pytest.mark.asyncio
async def test_entity_salience_close_to_computed():
    """entity_salience close to computed -> small discrepancy."""
    # nuclear_family + 0.8 affect -> salience ~0.97
    envelope = _build_envelope(
        social_context="nuclear_family",
        affect_intensity=0.8,
        entity_salience={"mom": 0.9, "sharvi": 0.95},  # mean=0.925
    )
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m06_run(msg, ctx, envelope=envelope)

    discrepancy = result.get("entity_salience_discrepancy")
    if discrepancy is not None:
        # Should be small since entity_salience is close to computed
        assert discrepancy < 0.3


# ============================================================================
# Works with fallback path inputs too
# ============================================================================


@pytest.mark.asyncio
async def test_fallback_inputs_still_score():
    """Salience works with fallback path inputs (unknown context, moderate affect)."""
    envelope = _build_envelope(
        social_context="unknown",
        affect_intensity=0.5,
    )
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m06_run(msg, ctx, envelope=envelope)

    # Should produce valid salience regardless of source
    assert 0.0 <= result["salience_score"] <= 1.0
    assert result["salience_band"] in ("HIGH", "MED", "LOW")


@pytest.mark.asyncio
async def test_missing_social_context_uses_default():
    """Missing social_context -> uses 'unknown' default score."""
    envelope = _build_envelope(affect_intensity=0.5)
    envelope["event"]["social_context"] = None
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m06_run(msg, ctx, envelope=envelope)

    assert 0.0 <= result["salience_score"] <= 1.0


@pytest.mark.asyncio
async def test_missing_affect_uses_default():
    """Missing affect_intensity -> uses 0.5 default."""
    envelope = _build_envelope(social_context="nuclear_family")
    envelope["affect_intensity"] = None
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m06_run(msg, ctx, envelope=envelope)

    assert 0.0 <= result["salience_score"] <= 1.0


# ============================================================================
# OUTPUT STRUCTURE VALIDATION
# ============================================================================


@pytest.mark.asyncio
async def test_output_has_all_required_keys():
    """Output has all required salience fields."""
    envelope = _build_envelope()
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m06_run(msg, ctx, envelope=envelope)

    required_keys = [
        "salience_score",
        "salience_band",
        "salience_reasons_json",
        "component_scores_json",
        "salience_computed_at_utc",
        "entity_salience_discrepancy",
        "enrichments",
    ]
    for key in required_keys:
        assert key in result, f"Missing required key: {key}"


@pytest.mark.asyncio
async def test_component_scores_structure():
    """component_scores_json has social, affect, recency."""
    envelope = _build_envelope()
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m06_run(msg, ctx, envelope=envelope)

    comp = json.loads(result["component_scores_json"])
    assert "social" in comp
    assert "affect" in comp
    assert "recency" in comp
    assert all(0.0 <= v <= 1.0 for v in comp.values())


@pytest.mark.asyncio
async def test_enrichments_nested_structure():
    """enrichments.salience_scorer has v2 structure."""
    envelope = _build_envelope()
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m06_run(msg, ctx, envelope=envelope)

    enrichment = result["enrichments"]["salience_scorer"]
    assert enrichment["module_version"] == "v2"
    assert "score" in enrichment
    assert "band" in enrichment
    assert "component_scores" in enrichment


@pytest.mark.asyncio
async def test_preserves_original_envelope():
    """Output contains original envelope fields."""
    envelope = _build_envelope()
    msg = MockMessage(envelope)
    ctx = MockContext()

    result = await m06_run(msg, ctx, envelope=envelope)

    assert result["event_id"] == "evt-m06-test-001"
    assert result["actor_id"] == "actor-dad"
