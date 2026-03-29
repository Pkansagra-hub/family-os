"""
Epic 2.4 (GAP-002) -- M08 temporal_links parsing tests.

Tests parse_temporal_links() and M08 run() integration with:
- v2.1 atom: body.temporal_links list passed through
- v2.0 backward compat: body.temporal synthesized into single-element list
- Empty temporal_links -> None
- Max 5 links enforced (6th truncated)
- Invalid links filtered
- M08 run() output includes temporal_links_json
"""

import json
import time
from typing import Any
from unittest.mock import Mock

import pytest

from k0.modules.context import temporal_profile
from k0.modules.context.temporal_profile import parse_temporal_links
from k0.modules.context.temporal_profile import run as m08_run

# ============================================================================
# Mock Transport (same pattern as test_m08_conversation_anchor.py)
# ============================================================================


class MockMessage:
    def __init__(self, payload: dict[str, Any], trace_id: str = "test-epic24"):
        import json as _json

        self.payload = _json.dumps(payload)
        self.trace_id = trace_id
        self.offset = 0


class MockContext:
    def __init__(self):
        self.logger = Mock()
        self.logger.debug = Mock()
        self.logger.info = Mock()
        self.logger.warning = Mock()
        self.logger.error = Mock()
        self.syscalls = Mock()
        self.config = {}


@pytest.fixture(autouse=True)
def reset_module_state():
    temporal_profile.reset_metrics()
    yield
    temporal_profile.reset_metrics()


def _base_envelope(**overrides) -> dict[str, Any]:
    now_ts = int(time.time())
    env = {
        "event_id": "evt-epic24-001",
        "cognitive_trace_id": "ct-epic24-001",
        "tenant_id": "default",
        "actor_id": "actor-dad",
        "ts": now_ts,
        "body": {
            "text": "Yesterday we planned next Friday and Mom mentioned Christmas",
        },
        "enrichments": {},
    }
    env.update(overrides)
    return env


# ============================================================================
# UNIT: parse_temporal_links()
# ============================================================================


class TestParseTemporalLinks:
    """Test parse_temporal_links helper in isolation."""

    def test_v21_three_links(self):
        """v2.1 atom with 3 temporal_links -> JSON string with 3 elements."""
        body = {
            "temporal_links": [
                {
                    "mentioned_time": "yesterday",
                    "link_type": "RETROSPECTIVE",
                    "uncertainty_window_ms": 86400000,
                    "confidence": 0.95,
                },
                {
                    "mentioned_time": "next Friday",
                    "link_type": "PROSPECTIVE",
                    "uncertainty_window_ms": 86400000,
                    "confidence": 0.90,
                },
                {
                    "mentioned_time": "Christmas",
                    "link_type": "PROSPECTIVE",
                    "uncertainty_window_ms": 86400000,
                    "confidence": 0.85,
                },
            ]
        }
        result = parse_temporal_links(body)
        assert result is not None
        parsed = json.loads(result)
        assert len(parsed) == 3
        assert parsed[0]["mentioned_time"] == "yesterday"
        assert parsed[0]["link_type"] == "RETROSPECTIVE"
        assert parsed[1]["mentioned_time"] == "next Friday"
        assert parsed[2]["mentioned_time"] == "Christmas"

    def test_v21_empty_list(self):
        """v2.1 atom with empty temporal_links -> None."""
        body = {"temporal_links": []}
        assert parse_temporal_links(body) is None

    def test_v21_single_link(self):
        """v2.1 atom with 1 link -> JSON array with 1 element."""
        body = {
            "temporal_links": [
                {
                    "mentioned_time": "yesterday evening",
                    "link_type": "RETROSPECTIVE",
                    "resolved_epoch_ms": 1700000000000,
                    "uncertainty_window_ms": 14400000,
                    "confidence": 0.95,
                },
            ]
        }
        result = parse_temporal_links(body)
        parsed = json.loads(result)
        assert len(parsed) == 1
        assert parsed[0]["resolved_epoch_ms"] == 1700000000000
        assert parsed[0]["uncertainty_window_ms"] == 14400000

    def test_v21_max_five_links(self):
        """v2.1 atom with 6 links -> truncated to 5."""
        body = {
            "temporal_links": [
                {"mentioned_time": f"time_{i}", "link_type": "CONCURRENT"} for i in range(6)
            ]
        }
        result = parse_temporal_links(body)
        parsed = json.loads(result)
        assert len(parsed) == 5

    def test_v20_backward_compat_retrospective(self):
        """v2.0 atom with body.temporal (is_backdated=True) -> single RETROSPECTIVE link."""
        body = {
            "temporal": {
                "mentioned_time": "yesterday evening",
                "resolved_epoch_ms": 1700000000000,
                "is_backdated": True,
            }
        }
        result = parse_temporal_links(body)
        parsed = json.loads(result)
        assert len(parsed) == 1
        assert parsed[0]["mentioned_time"] == "yesterday evening"
        assert parsed[0]["link_type"] == "RETROSPECTIVE"
        assert parsed[0]["resolved_epoch_ms"] == 1700000000000

    def test_v20_backward_compat_concurrent(self):
        """v2.0 atom with body.temporal (is_backdated=False) -> single CONCURRENT link."""
        body = {
            "temporal": {
                "mentioned_time": "right now",
                "resolved_epoch_ms": 1700000000000,
                "is_backdated": False,
            }
        }
        result = parse_temporal_links(body)
        parsed = json.loads(result)
        assert len(parsed) == 1
        assert parsed[0]["link_type"] == "CONCURRENT"

    def test_v21_takes_precedence_over_v20(self):
        """When both temporal_links and temporal exist, v2.1 wins."""
        body = {
            "temporal_links": [
                {"mentioned_time": "next Friday", "link_type": "PROSPECTIVE"},
            ],
            "temporal": {
                "mentioned_time": "yesterday",
                "resolved_epoch_ms": 1700000000000,
                "is_backdated": True,
            },
        }
        result = parse_temporal_links(body)
        parsed = json.loads(result)
        assert len(parsed) == 1
        assert parsed[0]["mentioned_time"] == "next Friday"
        assert parsed[0]["link_type"] == "PROSPECTIVE"

    def test_no_temporal_data(self):
        """No temporal_links and no temporal -> None."""
        body = {"text": "Hello world"}
        assert parse_temporal_links(body) is None

    def test_invalid_link_filtered(self):
        """Link without mentioned_time is filtered out."""
        body = {
            "temporal_links": [
                {"link_type": "RETROSPECTIVE"},  # missing mentioned_time
                {"mentioned_time": "tomorrow", "link_type": "PROSPECTIVE"},
            ]
        }
        result = parse_temporal_links(body)
        parsed = json.loads(result)
        assert len(parsed) == 1
        assert parsed[0]["mentioned_time"] == "tomorrow"

    def test_invalid_link_type_corrected(self):
        """Invalid link_type defaults to CONCURRENT."""
        body = {
            "temporal_links": [
                {"mentioned_time": "yesterday", "link_type": "INVALID_TYPE"},
            ]
        }
        result = parse_temporal_links(body)
        parsed = json.loads(result)
        assert parsed[0]["link_type"] == "CONCURRENT"

    def test_confidence_clamped(self):
        """Confidence > 1.0 is clamped to 1.0, < 0.0 clamped to 0.0."""
        body = {
            "temporal_links": [
                {"mentioned_time": "yesterday", "link_type": "RETROSPECTIVE", "confidence": 1.5},
            ]
        }
        result = parse_temporal_links(body)
        parsed = json.loads(result)
        assert parsed[0]["confidence"] == 1.0

    def test_negative_uncertainty_clamped(self):
        """Negative uncertainty_window_ms is clamped to 0."""
        body = {
            "temporal_links": [
                {
                    "mentioned_time": "yesterday",
                    "link_type": "RETROSPECTIVE",
                    "uncertainty_window_ms": -100,
                },
            ]
        }
        result = parse_temporal_links(body)
        parsed = json.loads(result)
        assert parsed[0]["uncertainty_window_ms"] == 0

    def test_all_six_link_types_accepted(self):
        """All 6 TemporalLinkType values pass validation."""
        for lt in [
            "RETROSPECTIVE",
            "PROSPECTIVE",
            "CONCURRENT",
            "HABITUAL",
            "CONTEXTUAL",
            "CONDITIONAL",
        ]:
            body = {"temporal_links": [{"mentioned_time": "test", "link_type": lt}]}
            result = parse_temporal_links(body)
            parsed = json.loads(result)
            assert parsed[0]["link_type"] == lt


# ============================================================================
# INTEGRATION: M08 run() with temporal_links
# ============================================================================


class TestM08RunTemporalLinks:
    """Integration tests: M08 run() outputs temporal_links_json."""

    @pytest.mark.asyncio
    async def test_v21_temporal_links_in_output(self):
        """v2.1 atom -> temporal_links_json in M08 output."""
        envelope = _base_envelope()
        envelope["body"]["temporal_links"] = [
            {
                "mentioned_time": "yesterday",
                "link_type": "RETROSPECTIVE",
                "uncertainty_window_ms": 86400000,
                "confidence": 0.95,
            },
        ]
        msg = MockMessage(envelope)
        ctx = MockContext()

        result = await m08_run(msg, ctx, envelope=envelope)

        assert "temporal_links_json" in result
        parsed = json.loads(result["temporal_links_json"])
        assert len(parsed) == 1
        assert parsed[0]["mentioned_time"] == "yesterday"

    @pytest.mark.asyncio
    async def test_v20_backward_compat_in_output(self):
        """v2.0 atom with body.temporal -> temporal_links_json synthesized."""
        envelope = _base_envelope()
        envelope["body"]["temporal"] = {
            "mentioned_time": "last week",
            "resolved_epoch_ms": 1700000000000,
            "is_backdated": True,
        }
        msg = MockMessage(envelope)
        ctx = MockContext()

        result = await m08_run(msg, ctx, envelope=envelope)

        assert "temporal_links_json" in result
        parsed = json.loads(result["temporal_links_json"])
        assert len(parsed) == 1
        assert parsed[0]["link_type"] == "RETROSPECTIVE"

    @pytest.mark.asyncio
    async def test_no_temporal_data_none_output(self):
        """No temporal data -> temporal_links_json is None."""
        envelope = _base_envelope()
        msg = MockMessage(envelope)
        ctx = MockContext()

        result = await m08_run(msg, ctx, envelope=envelope)

        assert result["temporal_links_json"] is None

    @pytest.mark.asyncio
    async def test_temporal_links_in_enrichments(self):
        """temporal_links_json also in nested enrichments.temporal_profiler."""
        envelope = _base_envelope()
        envelope["body"]["temporal_links"] = [
            {"mentioned_time": "tomorrow", "link_type": "PROSPECTIVE"},
        ]
        msg = MockMessage(envelope)
        ctx = MockContext()

        result = await m08_run(msg, ctx, envelope=envelope)

        enrichments = result["enrichments"]["temporal_profiler"]
        assert "temporal_links_json" in enrichments
        parsed = json.loads(enrichments["temporal_links_json"])
        assert parsed[0]["mentioned_time"] == "tomorrow"
