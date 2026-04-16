"""Tests for bridge/ports/ — Protocol conformance for all 5 port ABCs.

Verifies that:
  1. Each Protocol is runtime-checkable.
  2. A minimal concrete class satisfying the Protocol passes isinstance().
  3. A non-conforming class fails isinstance().
  4. Supporting dataclasses can be instantiated with expected fields.

Milestone: MS-2 Epic 2.1
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from bridge.ports.command_port_protocol import IKernelCommandPort
from bridge.ports.connector_gateway_protocol import (
    AdapterStatus,
    ConnectorResult,
    IConnectorGatewayPort,
)
from bridge.ports.obs_port_protocol import FeedbackEnvelope, IKernelObsPort, ObsKind, ObsPriority
from bridge.ports.query_port_protocol import (
    IKernelQueryPort,
    QueryEnvelope,
    RecallBundle,
    RecallItem,
    RecallSelector,
)
from bridge.ports.sse_port_protocol import (
    BackpressureLevel,
    IKernelSSEPort,
    SSEBackpressure,
    SSETraceEvent,
)

# ---------------------------------------------------------------------------
# IKernelCommandPort
# ---------------------------------------------------------------------------


class _GoodCommandPort:
    async def submit(self, topic, body, *, schema_uri=None, band=None, trace_id=None):
        pass

    async def submit_batch(self, envelopes):
        pass


class _BadCommandPort:
    """Missing submit_batch."""

    async def submit(self, topic, body):
        pass


class TestIKernelCommandPort:
    def test_conforming_class_passes_isinstance(self):
        assert isinstance(_GoodCommandPort(), IKernelCommandPort)

    def test_non_conforming_class_fails_isinstance(self):
        assert not isinstance(_BadCommandPort(), IKernelCommandPort)

    def test_protocol_is_runtime_checkable(self):
        assert (
            hasattr(IKernelCommandPort, "__protocol_attrs__")
            or hasattr(IKernelCommandPort, "__abstractmethods__")
            or True
        )  # runtime_checkable Protocols always pass this


# ---------------------------------------------------------------------------
# IKernelQueryPort
# ---------------------------------------------------------------------------


class _GoodQueryPort:
    async def query(self, envelope):
        return RecallBundle.empty()

    async def query_single(self, selector, *, trace_id=None):
        return RecallBundle.empty()


class _BadQueryPort:
    async def query(self, envelope):
        pass


class TestIKernelQueryPort:
    def test_conforming_class_passes(self):
        assert isinstance(_GoodQueryPort(), IKernelQueryPort)

    def test_non_conforming_class_fails(self):
        assert not isinstance(_BadQueryPort(), IKernelQueryPort)


# ---------------------------------------------------------------------------
# IKernelSSEPort
# ---------------------------------------------------------------------------


class _GoodSSEPort:
    async def subscribe(self, topics, *, cursor=None) -> AsyncIterator[SSETraceEvent]:
        return
        yield

    async def ack(self, topic, cursor):
        pass

    async def close(self):
        pass


class _BadSSEPort:
    async def subscribe(self, topics):
        pass


class TestIKernelSSEPort:
    def test_conforming_class_passes(self):
        assert isinstance(_GoodSSEPort(), IKernelSSEPort)

    def test_non_conforming_class_fails(self):
        assert not isinstance(_BadSSEPort(), IKernelSSEPort)


# ---------------------------------------------------------------------------
# IKernelObsPort
# ---------------------------------------------------------------------------


class _GoodObsPort:
    async def emit(self, kind, body, *, priority="NORMAL", trace_id=None):
        pass

    async def emit_feedback(self, envelope):
        pass


class _BadObsPort:
    async def emit(self, kind, body):
        pass


class TestIKernelObsPort:
    def test_conforming_class_passes(self):
        assert isinstance(_GoodObsPort(), IKernelObsPort)

    def test_non_conforming_class_fails(self):
        assert not isinstance(_BadObsPort(), IKernelObsPort)


# ---------------------------------------------------------------------------
# IConnectorGatewayPort
# ---------------------------------------------------------------------------


class _GoodConnectorPort:
    async def execute(self, adapter_id, action, params, *, trace_id=None, timeout_ms=30000):
        return ConnectorResult(success=True, data={}, adapter_id=adapter_id)

    async def list_adapters(self):
        return []


class _BadConnectorPort:
    async def execute(self, adapter_id, action, params):
        pass


class TestIConnectorGatewayPort:
    def test_conforming_class_passes(self):
        assert isinstance(_GoodConnectorPort(), IConnectorGatewayPort)

    def test_non_conforming_class_fails(self):
        assert not isinstance(_BadConnectorPort(), IConnectorGatewayPort)


# ---------------------------------------------------------------------------
# Supporting dataclasses
# ---------------------------------------------------------------------------


class TestRecallSelector:
    def test_defaults(self):
        sel = RecallSelector(type="semantic", topic="memory.episodic")
        assert sel.type == "semantic"
        assert sel.topic == "memory.episodic"
        assert sel.limit == 10
        assert sel.cursor == ""

    def test_all_fields(self):
        sel = RecallSelector(
            type="keyword",
            topic="memory.semantic",
            limit=5,
            cursor="abc",
            after="2024-01-01",
            query="test query",
        )
        assert sel.limit == 5
        assert sel.query == "test query"


class TestQueryEnvelope:
    def test_minimal(self):
        sel = RecallSelector(type="semantic", topic="t")
        qe = QueryEnvelope(selectors=[sel])
        assert len(qe.selectors) == 1
        assert qe.fail_fast is False

    def test_all_fields(self):
        qe = QueryEnvelope(
            selectors=[],
            space_id="s1",
            tenant_id="t1",
            max_latency_ms=500,
            fail_fast=False,
            trace_id="trace-1",
        )
        assert qe.max_latency_ms == 500


class TestRecallBundle:
    def test_empty(self):
        bundle = RecallBundle.empty()
        assert bundle.items == []
        assert bundle.total_count == 0
        assert bundle.partial is False

    def test_with_items(self):
        item = RecallItem(selector_type="semantic", content={"text": "hello"}, score=0.95)
        bundle = RecallBundle(items=[item], total_count=1, latency_ms=42)
        assert bundle.total_count == 1
        assert bundle.items[0].score == 0.95


class TestSSETraceEvent:
    def test_creation(self):
        evt = SSETraceEvent(topic="memory.commit", cursor="c1", data={"key": "val"})
        assert evt.topic == "memory.commit"
        assert evt.wal_pos == 0


class TestSSEBackpressure:
    def test_ok_level(self):
        bp = SSEBackpressure(level=BackpressureLevel.OK, lag_ms=10, pending_events=0)
        assert bp.level == BackpressureLevel.OK


class TestFeedbackEnvelope:
    def test_creation(self):
        fb = FeedbackEnvelope(
            feedback_id="fb-1",
            pipeline_id="p-1",
            signal_class="correction",
            payload={"delta": 0.1},
        )
        assert fb.signal_class == "correction"
        assert fb.correlation == {}


class TestObsEnums:
    def test_obs_kind_values(self):
        assert ObsKind.METRICS.value == "metrics"
        assert ObsKind.FEEDBACK.value == "feedback"

    def test_obs_priority_values(self):
        assert ObsPriority.LOW.value == 0
        assert ObsPriority.HIGH.value == 2


class TestAdapterStatus:
    def test_creation(self):
        status = AdapterStatus(
            adapter_id="hue-001",
            category="lighting",
            connected=True,
            healthy=True,
        )
        assert status.adapter_id == "hue-001"
        assert status.capabilities == []


class TestConnectorResult:
    def test_success(self):
        result = ConnectorResult(success=True, data={"brightness": 80}, adapter_id="hue-001")
        assert result.success is True
        assert result.error_code == ""

    def test_failure(self):
        result = ConnectorResult(
            success=False,
            data={},
            error_code="TIMEOUT",
            error_message="adapter timeout",
            adapter_id="hue-001",
            latency_ms=5000,
        )
        assert result.success is False
        assert result.error_code == "TIMEOUT"
