"""M6 Epic 6.2 -- Production Adapters Tests [6.2.1-6.2.7].

Tests all 7 production adapters:
  - isinstance check against their Protocol
  - Happy-path method calls
  - Error handling (never crash hub)
  - Re-exports from adapters/__init__.py

NO unittest.mock.
"""

from __future__ import annotations

import pytest

from k1.model_hub.adapters import (
    ConfigAdapter,
    CredentialStoreAdapter,
    EventBusAdapter,
    HealthReportAdapter,
    LLMRequestBusAdapter,
    PrometheusAdapter,
    SessionStateReadAdapter,
)
from k1.model_hub.ports import (
    IConfigPort,
    ICredentialPort,
    IEventPort,
    IHealthPort,
    IMetricsPort,
    IModelHubPort,
    IStateReadPort,
)
from k1.model_hub.ports.config_port import ConfigSubscription
from k1.model_hub.ports.event_port import Subscription
from k1.model_hub.ports.health_port import HealthReport
from k1.model_hub.ports.state_read_port import StateSnapshot
from k1.model_hub.types import (
    CapabilityType,
    HealthStatus,
    HubHealthReport,
    HubRequest,
    HubResponse,
    Message,
    ResponseMetadata,
    TokenUsage,
)

# -- Helper: minimal HubRequest factory ----------------------------------------


def _hub_request() -> HubRequest:
    return HubRequest(
        capability=CapabilityType.CHAT,
        payload={"messages": [Message(role="user", content="hi")]},
        trace_id="trace-1",
    )


def _hub_response() -> HubResponse:
    metadata = ResponseMetadata(
        request_id="req-1",
        model_id="test-model",
        provider_id="test-provider",
        usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        cost_usd=0.001,
        latency_ms=50,
        cache_hit=False,
        capability=CapabilityType.CHAT,
        trace_id="trace-1",
    )
    return HubResponse(result="hello", metadata=metadata)


# -- Helper: simple inner IModelHubPort ----------------------------------------


class _StubHub:
    """Minimal IModelHubPort stub for LLMRequestBusAdapter tests."""

    def __init__(self, response: HubResponse) -> None:
        self._response = response

    async def execute(self, request: HubRequest) -> HubResponse:
        return self._response

    async def stream_execute(self, request):
        from k1.model_hub.types import HubChunk

        yield HubChunk(content="chunk-1", done=False)
        yield HubChunk(content="chunk-2", done=True)

    async def discover_capabilities(self):
        return {}

    async def discover_models(self, capability=None):
        return []

    async def health(self):
        return HubHealthReport(status=HealthStatus.HEALTHY)


# ===========================================================================
# 6.2.1 -- LLMRequestBusAdapter
# ===========================================================================


class TestLLMRequestBusAdapter:
    """Tests for LLMRequestBusAdapter [6.2.1]."""

    def test_isinstance_imodelhubport(self) -> None:
        stub = _StubHub(_hub_response())
        adapter = LLMRequestBusAdapter(stub)
        assert isinstance(adapter, IModelHubPort)

    async def test_execute_delegates(self) -> None:
        resp = _hub_response()
        stub = _StubHub(resp)
        adapter = LLMRequestBusAdapter(stub)
        result = await adapter.execute(_hub_request())
        assert result is resp

    async def test_stream_execute_delegates(self) -> None:
        stub = _StubHub(_hub_response())
        adapter = LLMRequestBusAdapter(stub)
        chunks = [c async for c in adapter.stream_execute(_hub_request())]
        assert len(chunks) == 2
        assert chunks[1].done is True

    async def test_discover_capabilities(self) -> None:
        stub = _StubHub(_hub_response())
        adapter = LLMRequestBusAdapter(stub)
        caps = await adapter.discover_capabilities()
        assert isinstance(caps, dict)

    async def test_discover_models(self) -> None:
        stub = _StubHub(_hub_response())
        adapter = LLMRequestBusAdapter(stub)
        models = await adapter.discover_models()
        assert isinstance(models, list)

    async def test_health_delegates(self) -> None:
        stub = _StubHub(_hub_response())
        adapter = LLMRequestBusAdapter(stub)
        report = await adapter.health()
        assert report.status == HealthStatus.HEALTHY

    async def test_health_never_crashes(self) -> None:
        """If inner.health() raises, adapter returns UNHEALTHY."""

        class _BrokenHub(_StubHub):
            async def health(self):
                raise RuntimeError("boom")

        adapter = LLMRequestBusAdapter(_BrokenHub(_hub_response()))
        report = await adapter.health()
        assert report.status == HealthStatus.UNHEALTHY


# ===========================================================================
# 6.2.2 -- EventBusAdapter
# ===========================================================================


class TestEventBusAdapter:
    """Tests for EventBusAdapter [6.2.2]."""

    def test_isinstance_ieventport(self) -> None:
        adapter = EventBusAdapter()
        assert isinstance(adapter, IEventPort)

    async def test_publish_dispatches_to_handler(self) -> None:
        adapter = EventBusAdapter()
        received: list = []

        async def handler(t: str, p: object) -> None:
            received.append((t, p))

        await adapter.subscribe(["topic.a"], handler)
        await adapter.publish("topic.a", {"key": "val"})
        assert len(received) == 1
        assert received[0] == ("topic.a", {"key": "val"})

    async def test_subscribe_returns_subscription(self) -> None:
        adapter = EventBusAdapter()

        async def handler(t: str, p: object) -> None:
            pass

        sub = await adapter.subscribe(["t1", "t2"], handler)
        assert isinstance(sub, Subscription)
        assert sub.topics == ["t1", "t2"]

    async def test_publish_no_handler_no_error(self) -> None:
        adapter = EventBusAdapter()
        await adapter.publish("no.handler", {})  # should not raise


# ===========================================================================
# 6.2.3 -- SessionStateReadAdapter
# ===========================================================================


class TestSessionStateReadAdapter:
    """Tests for SessionStateReadAdapter [6.2.3]."""

    def test_isinstance_istatereadport(self) -> None:
        adapter = SessionStateReadAdapter()
        assert isinstance(adapter, IStateReadPort)

    async def test_read_returns_snapshot(self) -> None:
        adapter = SessionStateReadAdapter(
            state_source={"persona": {"pref": "gpt-4"}, "control": {"band": "adult"}}
        )
        snap = await adapter.read(["persona"])
        assert isinstance(snap, StateSnapshot)
        assert snap.sections["persona"] == {"pref": "gpt-4"}

    async def test_read_missing_section(self) -> None:
        adapter = SessionStateReadAdapter()
        snap = await adapter.read(["missing"])
        assert snap.sections == {}

    async def test_read_empty_returns_empty_snapshot(self) -> None:
        adapter = SessionStateReadAdapter()
        snap = await adapter.read([])
        assert isinstance(snap, StateSnapshot)


# ===========================================================================
# 6.2.4 -- PrometheusAdapter
# ===========================================================================


class TestPrometheusAdapter:
    """Tests for PrometheusAdapter [6.2.4]."""

    def test_isinstance_imetricsport(self) -> None:
        adapter = PrometheusAdapter()
        assert isinstance(adapter, IMetricsPort)

    def test_emit_accumulates(self) -> None:
        adapter = PrometheusAdapter()
        adapter.emit("latency_ms", 42.0, {"provider": "openai"})
        adapter.emit("latency_ms", 10.0, {"provider": "openai"})
        assert adapter._counters["latency_ms{provider=openai}"] == 52.0

    def test_emit_no_labels(self) -> None:
        adapter = PrometheusAdapter()
        adapter.emit("requests_total", 1.0)
        assert adapter._counters["requests_total"] == 1.0

    def test_emit_never_crashes(self) -> None:
        adapter = PrometheusAdapter()
        # Should not raise even with unusual inputs
        adapter.emit("metric", 0.0, None)
        adapter.emit("metric", 1.0, {})


# ===========================================================================
# 6.2.5 -- ConfigAdapter
# ===========================================================================


class TestConfigAdapter:
    """Tests for ConfigAdapter [6.2.5]."""

    def test_isinstance_iconfigport(self) -> None:
        adapter = ConfigAdapter()
        assert isinstance(adapter, IConfigPort)

    def test_get_returns_value(self) -> None:
        adapter = ConfigAdapter(data={"budget": 100})
        assert adapter.get("budget") == 100

    def test_get_missing_returns_none(self) -> None:
        adapter = ConfigAdapter()
        assert adapter.get("missing") is None

    def test_watch_returns_subscription(self) -> None:
        adapter = ConfigAdapter()
        sub = adapter.watch("key", lambda k, v: None)
        assert isinstance(sub, ConfigSubscription)
        assert sub.key == "key"

    def test_reload_notifies_watchers(self) -> None:
        adapter = ConfigAdapter(data={"budget": 100})
        received: list = []
        adapter.watch("budget", lambda k, v: received.append((k, v)))
        adapter.reload({"budget": 200})
        assert received == [("budget", 200)]

    def test_reload_no_notification_if_unchanged(self) -> None:
        adapter = ConfigAdapter(data={"budget": 100})
        received: list = []
        adapter.watch("budget", lambda k, v: received.append((k, v)))
        adapter.reload({"budget": 100})
        assert received == []


# ===========================================================================
# 6.2.6 -- CredentialStoreAdapter
# ===========================================================================


class TestCredentialStoreAdapter:
    """Tests for CredentialStoreAdapter [6.2.6]."""

    def test_isinstance_icredentialport(self) -> None:
        adapter = CredentialStoreAdapter()
        assert isinstance(adapter, ICredentialPort)

    async def test_get_key_from_overrides(self) -> None:
        adapter = CredentialStoreAdapter(key_overrides={"openai": "sk-test"})
        key = await adapter.get_key("openai")
        assert key == "sk-test"

    async def test_get_key_missing_returns_empty(self) -> None:
        adapter = CredentialStoreAdapter()
        key = await adapter.get_key("nonexistent")
        assert key == ""

    async def test_refresh_key_same_as_get_key(self) -> None:
        adapter = CredentialStoreAdapter(key_overrides={"openai": "sk-test"})
        key = await adapter.refresh_key("openai")
        assert key == "sk-test"

    async def test_get_key_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MH_KEY_GOOGLE", "goog-key")
        adapter = CredentialStoreAdapter()
        key = await adapter.get_key("google")
        assert key == "goog-key"


# ===========================================================================
# 6.2.7 -- HealthReportAdapter
# ===========================================================================


class TestHealthReportAdapter:
    """Tests for HealthReportAdapter [6.2.7]."""

    def test_isinstance_ihealthport(self) -> None:
        adapter = HealthReportAdapter()
        assert isinstance(adapter, IHealthPort)

    def test_report_and_check_health(self) -> None:
        adapter = HealthReportAdapter()
        adapter.report_health("router", HealthStatus.HEALTHY)
        adapter.report_health("cache", HealthStatus.HEALTHY)
        report = adapter.check_health()
        assert isinstance(report, HealthReport)
        assert report.status == HealthStatus.HEALTHY

    def test_degraded_propagates(self) -> None:
        adapter = HealthReportAdapter()
        adapter.report_health("router", HealthStatus.HEALTHY)
        adapter.report_health("cache", HealthStatus.DEGRADED)
        report = adapter.check_health()
        assert report.status == HealthStatus.DEGRADED

    def test_unhealthy_propagates(self) -> None:
        adapter = HealthReportAdapter()
        adapter.report_health("router", HealthStatus.UNHEALTHY)
        report = adapter.check_health()
        assert report.status == HealthStatus.UNHEALTHY

    def test_empty_is_healthy(self) -> None:
        adapter = HealthReportAdapter()
        report = adapter.check_health()
        assert report.status == HealthStatus.HEALTHY

    def test_details_include_components(self) -> None:
        adapter = HealthReportAdapter()
        adapter.report_health("router", HealthStatus.DEGRADED)
        report = adapter.check_health()
        assert report.details["router"] == "DEGRADED"

    def test_custom_component_name(self) -> None:
        adapter = HealthReportAdapter(component="subsystem")
        report = adapter.check_health()
        assert report.component == "subsystem"


# ===========================================================================
# Re-export validation
# ===========================================================================


class TestAdaptersReExport:
    """All 7 production adapters re-exported from k1.model_hub.adapters."""

    def test_all_importable(self) -> None:
        from k1.model_hub.adapters import __all__

        expected = {
            "ConfigAdapter",
            "CredentialStoreAdapter",
            "EventBusAdapter",
            "HealthReportAdapter",
            "LLMRequestBusAdapter",
            "PrometheusAdapter",
            "SessionStateReadAdapter",
        }
        assert set(__all__) == expected
