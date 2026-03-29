"""
Epic 1.2 (GAP-002) -- M08 Conversation Anchor & Dual Chain Tests

Tests the Chain A/B split introduced in normalize_timestamp v3:

Chain A -- CONVERSATION TIME (event_time_utc):
  1. body.conversation_anchor_ms -> "conversation_anchor"
  2. body.event_time -> "event_time"
  3. envelope.ts -> "envelope_ts"
  4. now() -> "now"

Chain B -- REFERRED TIME (temporal_resolved_epoch_ms):
  1. body.temporal.resolved_epoch_ms -> "mw_resolved"
  2. M02 NER temporal -> "ner_temporal"
  3. None -> "none"

Also validates:
- conversation_anchor_ms flows through to output
- Chain A and Chain B are independent
- MW resolved_epoch_ms does NOT overwrite event_time_utc (the original bug)
- M13 builder maps new columns
"""

import time
from typing import Any
from unittest.mock import Mock

import pytest

from k0.modules.builders.hipp_events_row import map_temporal_group
from k0.modules.context import temporal_profile
from k0.modules.context.temporal_profile import (
    _resolve_conversation_time,
    _resolve_referred_time,
    normalize_timestamp,
)
from k0.modules.context.temporal_profile import run as m08_run

# ============================================================================
# Mock Transport (same as test_m08_temporal_fallback_chain.py)
# ============================================================================


class MockMessage:
    def __init__(self, payload: dict[str, Any], trace_id: str = "test-epic12"):
        import json

        self.payload = json.dumps(payload)
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
        "event_id": "evt-epic12-001",
        "cognitive_trace_id": "ct-epic12-001",
        "tenant_id": "default",
        "actor_id": "actor-dad",
        "ts": now_ts,
        "body": {
            "text": "Mom and I went to Olive Garden yesterday evening",
        },
        "enrichments": {},
    }
    env.update(overrides)
    return env


# ============================================================================
# UNIT: _resolve_conversation_time (Chain A)
# ============================================================================


class TestResolveConversationTime:
    """Test Chain A priority order in isolation."""

    def test_priority1_conversation_anchor_ms(self):
        """body.conversation_anchor_ms present -> conversation_anchor."""
        anchor_ms = 1704067200000  # 2024-01-01 00:00:00 UTC in ms
        body = {"conversation_anchor_ms": anchor_ms}
        envelope = {"ts": int(time.time())}
        now_ts = int(time.time())

        seconds, source = _resolve_conversation_time(body, envelope, now_ts)

        assert source == "conversation_anchor"
        assert seconds == anchor_ms // 1000

    def test_priority1_anchor_ms_in_seconds(self):
        """conversation_anchor_ms as seconds (< 1e12) -> passed through."""
        anchor_s = 1704067200  # Already seconds
        body = {"conversation_anchor_ms": anchor_s}
        envelope = {"ts": int(time.time())}
        now_ts = int(time.time())

        seconds, source = _resolve_conversation_time(body, envelope, now_ts)

        assert source == "conversation_anchor"
        assert seconds == anchor_s

    def test_priority2_event_time_iso(self):
        """No anchor -> body.event_time -> event_time."""
        body = {"event_time": "2024-06-15T14:30:00Z"}
        envelope = {"ts": int(time.time())}
        now_ts = int(time.time())

        seconds, source = _resolve_conversation_time(body, envelope, now_ts)

        assert source == "event_time"
        # Verify it parsed to a reasonable epoch (mid-June 2024)
        assert 1718400000 <= seconds <= 1718500000

    def test_priority3_envelope_ts(self):
        """No anchor, no event_time -> envelope.ts."""
        ts = int(time.time())
        body = {}
        envelope = {"ts": ts}
        now_ts = ts

        seconds, source = _resolve_conversation_time(body, envelope, now_ts)

        assert source == "envelope_ts"
        assert seconds == ts

    def test_priority4_now_fallback(self):
        """No timestamps at all -> now()."""
        body = {}
        envelope = {}
        now_ts = int(time.time())

        seconds, source = _resolve_conversation_time(body, envelope, now_ts)

        assert source == "now"
        assert seconds == now_ts

    def test_anchor_ms_zero_skipped(self):
        """conversation_anchor_ms=0 -> skipped, falls to next priority."""
        body = {"conversation_anchor_ms": 0}
        envelope = {"ts": 1704067200}
        now_ts = int(time.time())

        seconds, source = _resolve_conversation_time(body, envelope, now_ts)

        assert source == "envelope_ts"

    def test_anchor_ms_negative_skipped(self):
        """Negative conversation_anchor_ms -> skipped."""
        body = {"conversation_anchor_ms": -100}
        envelope = {"ts": 1704067200}
        now_ts = int(time.time())

        seconds, source = _resolve_conversation_time(body, envelope, now_ts)

        assert source == "envelope_ts"


# ============================================================================
# UNIT: _resolve_referred_time (Chain B)
# ============================================================================


class TestResolveReferredTime:
    """Test Chain B priority order in isolation."""

    def test_priority1_mw_resolved(self):
        """body.temporal.resolved_epoch_ms -> mw_resolved."""
        resolved_ms = 1704067200000
        body = {"temporal": {"resolved_epoch_ms": resolved_ms}}
        now_ts = int(time.time())

        ms, source = _resolve_referred_time(body, None, now_ts)

        assert source == "mw_resolved"
        assert ms == resolved_ms

    def test_priority2_ner_temporal(self):
        """No MW temporal + M02 NER temporal -> ner_temporal (ms)."""
        body = {}
        m02_output = {
            "ner_temporal_entities": [{"text": "yesterday", "label": "DATE"}],
        }
        now_ts = int(time.time())

        ms, source = _resolve_referred_time(body, m02_output, now_ts)

        assert source == "ner_temporal"
        assert ms is not None
        # Should be approximately 24h ago in ms
        expected_ms = (now_ts - 86400) * 1000
        assert abs(ms - expected_ms) < 86400_000

    def test_priority3_none(self):
        """No MW temporal, no NER -> None, 'none'."""
        body = {}
        now_ts = int(time.time())

        ms, source = _resolve_referred_time(body, None, now_ts)

        assert source == "none"
        assert ms is None

    def test_mw_resolved_zero_skipped(self):
        """resolved_epoch_ms=0 -> skipped."""
        body = {"temporal": {"resolved_epoch_ms": 0}}
        now_ts = int(time.time())

        ms, source = _resolve_referred_time(body, None, now_ts)

        assert source == "none"
        assert ms is None

    def test_ner_empty_list_skipped(self):
        """Empty ner_temporal_entities list -> no match."""
        body = {}
        m02_output = {"ner_temporal_entities": []}
        now_ts = int(time.time())

        ms, source = _resolve_referred_time(body, m02_output, now_ts)

        assert source == "none"
        assert ms is None


# ============================================================================
# UNIT: normalize_timestamp (dual chain, 4-tuple return)
# ============================================================================


class TestNormalizeTimestamp:
    """Test the public normalize_timestamp 4-tuple return."""

    def test_returns_4_tuple(self):
        """normalize_timestamp returns (int, str, Optional[int], str)."""
        envelope = _base_envelope()
        result = normalize_timestamp(envelope, now_ts=int(time.time()))

        assert len(result) == 4
        event_time, conv_src, ref_ms, ref_src = result
        assert isinstance(event_time, int)
        assert isinstance(conv_src, str)
        assert ref_ms is None or isinstance(ref_ms, int)
        assert isinstance(ref_src, str)

    def test_chain_a_and_b_independent(self):
        """Chain A (conversation_anchor) and Chain B (mw_resolved) are independent."""
        anchor_ms = 1704067200000  # Jan 1 2024 00:00 UTC
        resolved_ms = 1700000000000  # Nov 14 2023 (referred time)
        envelope = _base_envelope()
        envelope["body"]["conversation_anchor_ms"] = anchor_ms
        envelope["body"]["temporal"] = {"resolved_epoch_ms": resolved_ms}

        event_time, conv_src, ref_ms, ref_src = normalize_timestamp(
            envelope, now_ts=int(time.time())
        )

        # Chain A: conversation_anchor_ms
        assert conv_src == "conversation_anchor"
        assert event_time == anchor_ms // 1000
        # Chain B: MW resolved
        assert ref_src == "mw_resolved"
        assert ref_ms == resolved_ms
        # The bug fix: event_time_utc != resolved time
        assert event_time != resolved_ms // 1000

    def test_mw_resolved_does_not_overwrite_event_time(self):
        """CRITICAL: MW resolved_epoch_ms must NOT overwrite event_time_utc.

        This is the original bug that Epic 1.2 fixes.
        """
        ts = int(time.time())
        resolved_ms = 1700000000000  # Some past referred time
        envelope = _base_envelope()
        envelope["ts"] = ts
        envelope["body"]["temporal"] = {"resolved_epoch_ms": resolved_ms}

        event_time, conv_src, ref_ms, ref_src = normalize_timestamp(envelope, now_ts=ts)

        # event_time_utc should be envelope.ts (conversation time), NOT resolved
        assert event_time == ts
        assert conv_src == "envelope_ts"
        # referred time is separate
        assert ref_ms == resolved_ms

    def test_no_temporal_data(self):
        """No temporal data -> Chain A=envelope.ts, Chain B=None."""
        ts = int(time.time())
        envelope = {"ts": ts, "body": {"text": "hello"}}

        event_time, conv_src, ref_ms, ref_src = normalize_timestamp(envelope, now_ts=ts)

        assert event_time == ts
        assert conv_src == "envelope_ts"
        assert ref_ms is None
        assert ref_src == "none"


# ============================================================================
# INTEGRATION: M08 run() with conversation_anchor_ms
# ============================================================================


class TestM08RunConversationAnchor:
    """Integration tests: M08 run() with Epic 1.2 conversation_anchor_ms."""

    @pytest.mark.asyncio
    async def test_conversation_anchor_drives_event_time(self):
        """body.conversation_anchor_ms -> event_time_utc via Chain A."""
        anchor_ms = 1704067200000  # 2024-01-01 00:00:00 UTC
        envelope = _base_envelope()
        envelope["body"]["conversation_anchor_ms"] = anchor_ms
        msg = MockMessage(envelope)
        ctx = MockContext()

        result = await m08_run(msg, ctx, envelope=envelope)

        assert result["temporal_source"] == "conversation_anchor"
        assert result["event_time_utc"] == anchor_ms // 1000

    @pytest.mark.asyncio
    async def test_anchor_plus_mw_resolved_independent(self):
        """conversation_anchor_ms + temporal.resolved_epoch_ms -> independent chains."""
        anchor_ms = 1704067200000  # Conversation: Jan 1 2024
        resolved_ms = 1700000000000  # Referred: Nov 14 2023
        envelope = _base_envelope()
        envelope["body"]["conversation_anchor_ms"] = anchor_ms
        envelope["body"]["temporal"] = {
            "resolved_epoch_ms": resolved_ms,
            "mentioned_time": "last November",
        }
        msg = MockMessage(envelope)
        ctx = MockContext()

        result = await m08_run(msg, ctx, envelope=envelope)

        # Chain A: conversation time from anchor
        assert result["temporal_source"] == "conversation_anchor"
        assert result["event_time_utc"] == anchor_ms // 1000
        # Chain B: referred time from MW resolved
        assert result["temporal_resolved_epoch_ms"] == resolved_ms
        # Passthrough
        assert result["temporal_mentioned_time"] == "last November"

    @pytest.mark.asyncio
    async def test_conversation_anchor_ms_in_output(self):
        """conversation_anchor_ms propagates to output dict."""
        anchor_ms = 1704067200000
        envelope = _base_envelope()
        envelope["body"]["conversation_anchor_ms"] = anchor_ms
        msg = MockMessage(envelope)
        ctx = MockContext()

        result = await m08_run(msg, ctx, envelope=envelope)

        assert result["conversation_anchor_ms"] == anchor_ms

    @pytest.mark.asyncio
    async def test_no_anchor_ms_null_in_output(self):
        """No conversation_anchor_ms -> output field is None."""
        envelope = _base_envelope()
        msg = MockMessage(envelope)
        ctx = MockContext()

        result = await m08_run(msg, ctx, envelope=envelope)

        assert result["conversation_anchor_ms"] is None

    @pytest.mark.asyncio
    async def test_conversation_anchor_in_enrichments(self):
        """conversation_anchor_ms in nested enrichments dict."""
        anchor_ms = 1704067200000
        envelope = _base_envelope()
        envelope["body"]["conversation_anchor_ms"] = anchor_ms
        msg = MockMessage(envelope)
        ctx = MockContext()

        result = await m08_run(msg, ctx, envelope=envelope)

        profiler = result["enrichments"]["temporal_profiler"]
        assert profiler["conversation_anchor_ms"] == anchor_ms


# ============================================================================
# INTEGRATION: M13 builder map_temporal_group with new columns
# ============================================================================


class TestM13BuilderEpic12:
    """Test map_temporal_group includes conversation_anchor_ms and temporal_source."""

    def test_new_columns_present(self):
        """map_temporal_group output has conversation_anchor_ms and temporal_source."""
        temporal_output = {
            "event_time_utc": int(time.time()),
            "write_time_utc": int(time.time()),
            "write_lag_ms": 50,
            "local_date": "2024-01-01",
            "local_time": "12:00:00",
            "day_of_week": "Monday",
            "is_weekend": False,
            "time_of_day_bucket": "afternoon",
            "circadian_slot": "lunch",
            "is_backdated": False,
            "temporal_mentioned_time": "yesterday",
            "temporal_resolved_epoch_ms": 1704067200000,
            "temporal_orientation": "PAST",
            "conversation_anchor_ms": 1704153600000,
            "temporal_source": "conversation_anchor",
        }

        result = map_temporal_group(temporal_output)

        assert result["conversation_anchor_ms"] == 1704153600000
        assert result["temporal_source"] == "conversation_anchor"

    def test_new_columns_null_when_absent(self):
        """map_temporal_group returns None for missing new columns."""
        temporal_output = {
            "event_time_utc": int(time.time()),
            "write_time_utc": int(time.time()),
        }

        result = map_temporal_group(temporal_output)

        assert result["conversation_anchor_ms"] is None
        assert result["temporal_source"] is None

    def test_column_count(self):
        """map_temporal_group returns 18 keys (16 temporal + created_at + updated_at)."""
        temporal_output = {
            "event_time_utc": int(time.time()),
            "write_time_utc": int(time.time()),
        }

        result = map_temporal_group(temporal_output)

        assert len(result) == 18
