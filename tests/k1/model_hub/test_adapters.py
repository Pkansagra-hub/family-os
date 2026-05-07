"""M6 Epic 6.1 -- Test Adapters & TestProviderPlugin [6.1.1-6.1.8].

Tests all 7 test adapters + TestProviderPlugin:
  - isinstance check against their Protocol
  - Happy-path method calls
  - Capture/inspection verification
  - reset() clears state
  - No unittest.mock anywhere

Category F acceptance criteria.
"""

from __future__ import annotations

import pytest

from k1.model_hub.manifest import ModelSpec, ProviderManifest
from k1.model_hub.plugins.base import (
    IProviderPlugin,
    NormalizedRequest,
    ProviderChunk,
    ProviderHealth,
    ProviderResponse,
)
from k1.model_hub.plugins.test_plugin import (
    ExecuteCall,
    HealthCheckCall,
    StreamCall,
    TestProviderPlugin,
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
    FinishReason,
    HealthStatus,
    HubChunk,
    HubHealthReport,
    HubRequest,
    HubResponse,
    Message,
    ProviderError,
)
from tests.k1.model_hub.adapters.test_config_adapter import TestConfigAdapter
from tests.k1.model_hub.adapters.test_credential_adapter import TestCredentialAdapter
from tests.k1.model_hub.adapters.test_event_adapter import CapturedEvent, TestEventAdapter
from tests.k1.model_hub.adapters.test_health_adapter import CapturedHealthReport, TestHealthAdapter
from tests.k1.model_hub.adapters.test_llm_request_adapter import TestLLMRequestAdapter
from tests.k1.model_hub.adapters.test_metrics_adapter import CapturedMetric, TestMetricsAdapter
from tests.k1.model_hub.adapters.test_state_read_adapter import TestStateReadAdapter

# ===========================================================================
# Helpers
# ===========================================================================


def _make_hub_request(**overrides) -> HubRequest:
    defaults = dict(
        request_id="req-1",
        capability=CapabilityType.CHAT,
        payload={"messages": [Message(role="user", content="hello")]},
        trace_id="trace-1",
    )
    defaults.update(overrides)
    return HubRequest(**defaults)


def _make_normalized_request(**overrides) -> NormalizedRequest:
    defaults = dict(
        capability=CapabilityType.CHAT,
        model_id="test-model",
        messages=[Message(role="user", content="hello")],
    )
    defaults.update(overrides)
    return NormalizedRequest(**defaults)


# ===========================================================================
# 6.1.1 -- TestLLMRequestAdapter
# ===========================================================================


class TestLLMRequestAdapterSuite:
    """Tests for TestLLMRequestAdapter [6.1.1]."""

    def test_isinstance_imodelhubport(self) -> None:
        adapter = TestLLMRequestAdapter()
        assert isinstance(adapter, IModelHubPort)

    async def test_execute_returns_hub_response(self) -> None:
        adapter = TestLLMRequestAdapter(response_text="ok")
        req = _make_hub_request()
        resp = await adapter.execute(req)
        assert isinstance(resp, HubResponse)
        assert resp.result == "ok"
        assert resp.metadata.model_id == "test-model"
        assert resp.metadata.provider_id == "test-provider"

    async def test_execute_captures_request(self) -> None:
        adapter = TestLLMRequestAdapter()
        req = _make_hub_request()
        await adapter.execute(req)
        assert len(adapter.execute_requests) == 1
        assert adapter.execute_requests[0] is req

    async def test_execute_captures_response(self) -> None:
        adapter = TestLLMRequestAdapter()
        await adapter.execute(_make_hub_request())
        assert len(adapter.responses) == 1

    async def test_stream_execute_yields_chunks(self) -> None:
        adapter = TestLLMRequestAdapter()
        req = _make_hub_request()
        chunks = [c async for c in adapter.stream_execute(req)]
        assert len(chunks) == 2
        assert isinstance(chunks[0], HubChunk)
        assert chunks[0].done is False
        assert chunks[1].done is True

    async def test_stream_execute_captures_request(self) -> None:
        adapter = TestLLMRequestAdapter()
        req = _make_hub_request()
        _ = [c async for c in adapter.stream_execute(req)]
        assert len(adapter.stream_requests) == 1

    async def test_discover_capabilities(self) -> None:
        adapter = TestLLMRequestAdapter()
        caps = await adapter.discover_capabilities()
        assert isinstance(caps, dict)

    async def test_discover_models(self) -> None:
        adapter = TestLLMRequestAdapter()
        models = await adapter.discover_models()
        assert isinstance(models, list)

    async def test_health_returns_healthy(self) -> None:
        adapter = TestLLMRequestAdapter()
        report = await adapter.health()
        assert isinstance(report, HubHealthReport)
        assert report.status == HealthStatus.HEALTHY

    async def test_reset_clears_captures(self) -> None:
        adapter = TestLLMRequestAdapter()
        await adapter.execute(_make_hub_request())
        _ = [c async for c in adapter.stream_execute(_make_hub_request())]
        adapter.reset()
        assert adapter.execute_requests == []
        assert adapter.stream_requests == []
        assert adapter.responses == []

    async def test_custom_model_and_provider(self) -> None:
        adapter = TestLLMRequestAdapter(model_id="gpt-4", provider_id="openai")
        resp = await adapter.execute(_make_hub_request())
        assert resp.metadata.model_id == "gpt-4"
        assert resp.metadata.provider_id == "openai"


# ===========================================================================
# 6.1.2 -- TestEventAdapter
# ===========================================================================


class TestEventAdapterSuite:
    """Tests for TestEventAdapter [6.1.2]."""

    def test_isinstance_ieventport(self) -> None:
        adapter = TestEventAdapter()
        assert isinstance(adapter, IEventPort)

    async def test_publish_captures_event(self) -> None:
        adapter = TestEventAdapter()
        await adapter.publish("topic.a", {"key": "value"})
        assert len(adapter.published) == 1
        assert isinstance(adapter.published[0], CapturedEvent)
        assert adapter.published[0].topic == "topic.a"
        assert adapter.published[0].payload == {"key": "value"}

    async def test_published_for_filters(self) -> None:
        adapter = TestEventAdapter()
        await adapter.publish("topic.a", 1)
        await adapter.publish("topic.b", 2)
        await adapter.publish("topic.a", 3)
        assert len(adapter.published_for("topic.a")) == 2
        assert len(adapter.published_for("topic.b")) == 1

    async def test_subscribe_returns_subscription(self) -> None:
        adapter = TestEventAdapter()

        async def handler(t: str, p: object) -> None:
            pass

        sub = await adapter.subscribe(["topic.x"], handler)
        assert isinstance(sub, Subscription)
        assert sub.topics == ["topic.x"]
        assert len(adapter.subscriptions) == 1

    async def test_subscribe_handler_receives_events(self) -> None:
        adapter = TestEventAdapter()
        received: list = []

        async def handler(t: str, p: object) -> None:
            received.append((t, p))

        await adapter.subscribe(["topic.x"], handler)
        await adapter.publish("topic.x", "payload")
        assert len(received) == 1
        assert received[0] == ("topic.x", "payload")

    async def test_reset_clears_all(self) -> None:
        adapter = TestEventAdapter()
        await adapter.publish("t", "p")

        async def handler(t: str, p: object) -> None:
            pass

        await adapter.subscribe(["t"], handler)
        adapter.reset()
        assert adapter.published == []
        assert adapter.subscriptions == []


# ===========================================================================
# 6.1.3 -- TestStateReadAdapter
# ===========================================================================


class TestStateReadAdapterSuite:
    """Tests for TestStateReadAdapter [6.1.3]."""

    def test_isinstance_istatereadport(self) -> None:
        adapter = TestStateReadAdapter()
        assert isinstance(adapter, IStateReadPort)

    async def test_read_returns_state_snapshot(self) -> None:
        adapter = TestStateReadAdapter(sections={"persona": {"pref": "gpt-4"}})
        snap = await adapter.read(["persona"])
        assert isinstance(snap, StateSnapshot)
        assert snap.sections["persona"] == {"pref": "gpt-4"}

    async def test_read_captures_calls(self) -> None:
        adapter = TestStateReadAdapter()
        await adapter.read(["persona", "control"])
        assert len(adapter.read_calls) == 1
        assert adapter.read_calls[0] == ["persona", "control"]

    async def test_read_missing_section_excluded(self) -> None:
        adapter = TestStateReadAdapter(sections={"persona": "data"})
        snap = await adapter.read(["persona", "missing"])
        assert "missing" not in snap.sections

    async def test_set_section(self) -> None:
        adapter = TestStateReadAdapter()
        adapter.set_section("control", {"band": "adult"})
        snap = await adapter.read(["control"])
        assert snap.sections["control"] == {"band": "adult"}

    async def test_reset_clears_calls(self) -> None:
        adapter = TestStateReadAdapter()
        await adapter.read(["x"])
        adapter.reset()
        assert adapter.read_calls == []


# ===========================================================================
# 6.1.4 -- TestMetricsAdapter
# ===========================================================================


class TestMetricsAdapterSuite:
    """Tests for TestMetricsAdapter [6.1.4]."""

    def test_isinstance_imetricsport(self) -> None:
        adapter = TestMetricsAdapter()
        assert isinstance(adapter, IMetricsPort)

    def test_emit_captures_metric(self) -> None:
        adapter = TestMetricsAdapter()
        adapter.emit("latency_ms", 42.0, {"provider": "openai"})
        assert adapter.count == 1
        assert isinstance(adapter.metrics[0], CapturedMetric)
        assert adapter.metrics[0].metric_name == "latency_ms"
        assert adapter.metrics[0].value == 42.0
        assert adapter.metrics[0].labels == {"provider": "openai"}

    def test_emit_default_labels(self) -> None:
        adapter = TestMetricsAdapter()
        adapter.emit("tokens", 15.0)
        assert adapter.metrics[0].labels == {}

    def test_metrics_for_filters(self) -> None:
        adapter = TestMetricsAdapter()
        adapter.emit("latency_ms", 10.0)
        adapter.emit("tokens", 100.0)
        adapter.emit("latency_ms", 20.0)
        assert len(adapter.metrics_for("latency_ms")) == 2
        assert len(adapter.metrics_for("tokens")) == 1

    def test_reset_clears_metrics(self) -> None:
        adapter = TestMetricsAdapter()
        adapter.emit("x", 1.0)
        adapter.reset()
        assert adapter.count == 0
        assert adapter.metrics == []


# ===========================================================================
# 6.1.5 -- TestConfigAdapter
# ===========================================================================


class TestConfigAdapterSuite:
    """Tests for TestConfigAdapter [6.1.5]."""

    def test_isinstance_iconfigport(self) -> None:
        adapter = TestConfigAdapter()
        assert isinstance(adapter, IConfigPort)

    def test_get_returns_value(self) -> None:
        adapter = TestConfigAdapter(data={"budget": 100})
        assert adapter.get("budget") == 100

    def test_get_missing_returns_none(self) -> None:
        adapter = TestConfigAdapter()
        assert adapter.get("missing") is None

    def test_get_captures_calls(self) -> None:
        adapter = TestConfigAdapter()
        adapter.get("a")
        adapter.get("b")
        assert adapter.get_calls == ["a", "b"]

    def test_watch_returns_subscription(self) -> None:
        adapter = TestConfigAdapter()
        sub = adapter.watch("key", lambda k, v: None)
        assert isinstance(sub, ConfigSubscription)
        assert sub.key == "key"
        assert len(adapter.watch_calls) == 1

    def test_set_notifies_watchers(self) -> None:
        adapter = TestConfigAdapter()
        received: list = []
        adapter.watch("budget", lambda k, v: received.append((k, v)))
        adapter.set("budget", 200)
        assert received == [("budget", 200)]

    def test_set_updates_value(self) -> None:
        adapter = TestConfigAdapter()
        adapter.set("timeout", 5000)
        assert adapter.get("timeout") == 5000

    def test_reset_clears_captures(self) -> None:
        adapter = TestConfigAdapter(data={"x": 1})
        adapter.get("x")
        adapter.watch("x", lambda k, v: None)
        adapter.reset()
        assert adapter.get_calls == []
        assert adapter.watch_calls == []


# ===========================================================================
# 6.1.6 -- TestCredentialAdapter
# ===========================================================================


class TestCredentialAdapterSuite:
    """Tests for TestCredentialAdapter [6.1.6]."""

    def test_isinstance_icredentialport(self) -> None:
        adapter = TestCredentialAdapter()
        assert isinstance(adapter, ICredentialPort)

    async def test_get_key_returns_fake_key(self) -> None:
        adapter = TestCredentialAdapter()
        key = await adapter.get_key("openai")
        assert key == "sk-test-openai"

    async def test_get_key_missing_provider(self) -> None:
        adapter = TestCredentialAdapter()
        key = await adapter.get_key("unknown")
        assert key == ""

    async def test_get_key_captures_calls(self) -> None:
        adapter = TestCredentialAdapter()
        await adapter.get_key("openai")
        await adapter.get_key("anthropic")
        assert adapter.get_key_calls == ["openai", "anthropic"]

    async def test_refresh_key_returns_same_key(self) -> None:
        adapter = TestCredentialAdapter()
        key = await adapter.refresh_key("openai")
        assert key == "sk-test-openai"

    async def test_refresh_key_captures_calls(self) -> None:
        adapter = TestCredentialAdapter()
        await adapter.refresh_key("google")
        assert adapter.refresh_key_calls == ["google"]

    async def test_set_key(self) -> None:
        adapter = TestCredentialAdapter()
        adapter.set_key("custom", "sk-custom")
        key = await adapter.get_key("custom")
        assert key == "sk-custom"

    async def test_custom_keys(self) -> None:
        adapter = TestCredentialAdapter(keys={"my_provider": "my-key"})
        assert await adapter.get_key("my_provider") == "my-key"
        assert await adapter.get_key("openai") == ""

    async def test_reset_clears_captures(self) -> None:
        adapter = TestCredentialAdapter()
        await adapter.get_key("openai")
        await adapter.refresh_key("openai")
        adapter.reset()
        assert adapter.get_key_calls == []
        assert adapter.refresh_key_calls == []


# ===========================================================================
# 6.1.7 -- TestHealthAdapter
# ===========================================================================


class TestHealthAdapterSuite:
    """Tests for TestHealthAdapter [6.1.7]."""

    def test_isinstance_ihealthport(self) -> None:
        adapter = TestHealthAdapter()
        assert isinstance(adapter, IHealthPort)

    def test_report_health_captures(self) -> None:
        adapter = TestHealthAdapter()
        adapter.report_health("router", HealthStatus.HEALTHY)
        assert adapter.count == 1
        assert isinstance(adapter.reports[0], CapturedHealthReport)
        assert adapter.reports[0].component == "router"
        assert adapter.reports[0].status == HealthStatus.HEALTHY

    def test_check_health_returns_report(self) -> None:
        adapter = TestHealthAdapter()
        report = adapter.check_health()
        assert isinstance(report, HealthReport)
        assert report.status == HealthStatus.HEALTHY
        assert report.component == "model_hub"

    def test_check_health_includes_reported_components(self) -> None:
        adapter = TestHealthAdapter()
        adapter.report_health("router", HealthStatus.DEGRADED)
        adapter.report_health("cache", HealthStatus.HEALTHY)
        report = adapter.check_health()
        assert report.details["router"] == "DEGRADED"
        assert report.details["cache"] == "HEALTHY"

    def test_reports_for_filters(self) -> None:
        adapter = TestHealthAdapter()
        adapter.report_health("router", HealthStatus.HEALTHY)
        adapter.report_health("cache", HealthStatus.DEGRADED)
        adapter.report_health("router", HealthStatus.UNHEALTHY)
        assert len(adapter.reports_for("router")) == 2
        assert len(adapter.reports_for("cache")) == 1

    def test_set_default_status(self) -> None:
        adapter = TestHealthAdapter()
        adapter.set_default_status(HealthStatus.UNHEALTHY)
        report = adapter.check_health()
        assert report.status == HealthStatus.UNHEALTHY

    def test_custom_defaults(self) -> None:
        adapter = TestHealthAdapter(
            default_status=HealthStatus.DEGRADED,
            default_component="subsystem",
        )
        report = adapter.check_health()
        assert report.status == HealthStatus.DEGRADED
        assert report.component == "subsystem"

    def test_reset_clears_all(self) -> None:
        adapter = TestHealthAdapter()
        adapter.report_health("x", HealthStatus.HEALTHY)
        adapter.reset()
        assert adapter.count == 0
        assert adapter.reports == []


# ===========================================================================
# 6.1.8 -- TestProviderPlugin
# ===========================================================================


class TestProviderPluginSuite:
    """Tests for TestProviderPlugin [F26 / 6.1.8]."""

    def test_isinstance_iproviderplugin(self) -> None:
        plugin = TestProviderPlugin()
        assert isinstance(plugin, IProviderPlugin)

    async def test_initialize_marks_initialized(self) -> None:
        plugin = TestProviderPlugin()
        assert plugin.initialized is False
        manifest = ProviderManifest(
            provider_id="test",
            display_name="Test Provider",
            capabilities=[CapabilityType.CHAT],
            models=[ModelSpec(id="test-model")],
        )
        await plugin.initialize(manifest)
        assert plugin.initialized is True

    def test_supports_chat_by_default(self) -> None:
        plugin = TestProviderPlugin()
        assert plugin.supports(CapabilityType.CHAT) is True

    def test_supports_custom_capability(self) -> None:
        plugin = TestProviderPlugin(capabilities=[CapabilityType.EMBED])
        assert plugin.supports(CapabilityType.EMBED) is True
        assert plugin.supports(CapabilityType.CHAT) is False

    async def test_execute_returns_provider_response(self) -> None:
        plugin = TestProviderPlugin(response_text="hello")
        req = _make_normalized_request()
        resp = await plugin.execute(req)
        assert isinstance(resp, ProviderResponse)
        assert resp.text == "hello"
        assert resp.prompt_tokens == 10
        assert resp.completion_tokens == 5
        assert resp.finish_reason == FinishReason.STOP

    async def test_execute_records_call(self) -> None:
        plugin = TestProviderPlugin()
        req = _make_normalized_request()
        await plugin.execute(req)
        assert len(plugin.execute_calls) == 1
        assert isinstance(plugin.execute_calls[0], ExecuteCall)
        assert plugin.execute_calls[0].request is req

    async def test_stream_execute_yields_chunks(self) -> None:
        plugin = TestProviderPlugin(stream_chunks=["a", "b", "c"])
        req = _make_normalized_request()
        chunks = [c async for c in plugin.stream_execute(req)]
        assert len(chunks) == 3
        assert isinstance(chunks[0], ProviderChunk)
        assert chunks[0].text == "a"
        assert chunks[0].done is False
        assert chunks[2].done is True

    async def test_stream_execute_records_call(self) -> None:
        plugin = TestProviderPlugin()
        req = _make_normalized_request()
        _ = [c async for c in plugin.stream_execute(req)]
        assert len(plugin.stream_calls) == 1
        assert isinstance(plugin.stream_calls[0], StreamCall)

    def test_estimate_tokens(self) -> None:
        plugin = TestProviderPlugin(token_estimate=42)
        msgs = [Message(role="user", content="test")]
        assert plugin.estimate_tokens(msgs) == 42

    async def test_health_check_returns_status(self) -> None:
        plugin = TestProviderPlugin(health_status=HealthStatus.DEGRADED)
        health = await plugin.health_check()
        assert isinstance(health, ProviderHealth)
        assert health.status == HealthStatus.DEGRADED

    async def test_health_check_records_call(self) -> None:
        plugin = TestProviderPlugin()
        await plugin.health_check()
        assert len(plugin.health_calls) == 1
        assert isinstance(plugin.health_calls[0], HealthCheckCall)

    async def test_close_marks_closed(self) -> None:
        plugin = TestProviderPlugin()
        assert plugin.closed is False
        await plugin.close()
        assert plugin.closed is True

    async def test_total_calls_counts_execute_and_stream(self) -> None:
        plugin = TestProviderPlugin()
        req = _make_normalized_request()
        await plugin.execute(req)
        _ = [c async for c in plugin.stream_execute(req)]
        assert plugin.total_calls == 2

    async def test_fail_count_raises_then_succeeds(self) -> None:
        plugin = TestProviderPlugin(fail_count=1)
        req = _make_normalized_request()
        with pytest.raises(ProviderError):
            await plugin.execute(req)
        # Second call should succeed
        resp = await plugin.execute(req)
        assert resp.text == "test-response"

    async def test_custom_fail_error(self) -> None:
        custom_err = ProviderError("custom failure", provider_id="test")
        plugin = TestProviderPlugin(fail_count=1, fail_error=custom_err)
        req = _make_normalized_request()
        with pytest.raises(ProviderError, match="custom failure"):
            await plugin.execute(req)

    async def test_reset_clears_all(self) -> None:
        plugin = TestProviderPlugin()
        req = _make_normalized_request()
        await plugin.execute(req)
        _ = [c async for c in plugin.stream_execute(req)]
        await plugin.health_check()
        plugin.reset()
        assert plugin.execute_calls == []
        assert plugin.stream_calls == []
        assert plugin.health_calls == []
        assert plugin.total_calls == 0

    async def test_model_id_from_request(self) -> None:
        plugin = TestProviderPlugin()
        req = _make_normalized_request(model_id="gpt-4o")
        resp = await plugin.execute(req)
        assert resp.model_id == "gpt-4o"
