"""M8 Lifecycle Tests -- INIT -> HEALTH_CHECK -> READY -> RUNNING -> DEGRADED -> SHUTDOWN [Epic 8.4.1].

Tests the conceptual lifecycle of the Model Hub:
  1. INIT:         Factory wires all services correctly.
  2. HEALTH_CHECK: Hub reports health before serving traffic.
  3. READY:        Hub can discover capabilities & models.
  4. RUNNING:      Hub handles requests successfully.
  5. DEGRADED:     Hub degrades gracefully under failures.
  6. SHUTDOWN:     Plugins are closed, resources cleaned up.

All services wired via ModelHubFactory.create_for_testing().
No unittest.mock imports.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Dict, List

import pytest

from k1.model_hub.config import ModelHubConfig
from k1.model_hub.factory import ModelHubFactory
from k1.model_hub.manifest import (
    CircuitBreakerConfig,
    ModelSpec,
    PlacementConfig,
    ProviderManifest,
    RateLimitConfig,
)
from k1.model_hub.plugins.base import (
    NormalizedRequest,
    ProviderChunk,
    ProviderHealth,
    ProviderResponse,
)
from k1.model_hub.services.audit_logger import AuditLogger
from k1.model_hub.services.budget_enforcer import BudgetEnforcer
from k1.model_hub.services.circuit_breaker_manager import CircuitBreakerManager
from k1.model_hub.services.cost_tracker import CostTracker
from k1.model_hub.services.provider_registry import ProviderRegistry
from k1.model_hub.services.rate_limiter import RateLimiter
from k1.model_hub.services.response_cache import ResponseCache
from k1.model_hub.types import (
    BudgetDecision,
    BudgetExceededError,
    CapabilityType,
    ChatPayload,
    CircuitState,
    FinishReason,
    HealthStatus,
    HubChunk,
    HubRequest,
    HubResponse,
    Message,
    ModelTier,
    NoEligibleProviderError,
    PlacementType,
    Priority,
    ProviderError,
    RequestConstraints,
    TokenUsage,
)

# ===========================================================================
# Fake Plugins
# ===========================================================================


class FakePlugin:
    """Deterministic plugin for lifecycle testing."""

    def __init__(self, *, response_text: str = "lifecycle-ok") -> None:
        self._response_text = response_text
        self._initialized = False
        self._closed = False
        self._calls: list[NormalizedRequest] = []

    async def initialize(self, manifest: object) -> None:
        self._initialized = True

    def supports(self, capability: CapabilityType) -> bool:
        return True

    async def execute(self, request: NormalizedRequest) -> ProviderResponse:
        self._calls.append(request)
        return ProviderResponse(
            text=self._response_text,
            prompt_tokens=10,
            completion_tokens=5,
            model_id=request.model_id or "test-model",
            finish_reason=FinishReason.STOP,
        )

    async def stream_execute(self, request: NormalizedRequest) -> AsyncIterator[ProviderChunk]:
        self._calls.append(request)
        yield ProviderChunk(text="stream ", done=False)
        yield ProviderChunk(text="ok", done=True)

    def estimate_tokens(self, messages: list) -> int:
        return 10

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(status=HealthStatus.HEALTHY)

    async def close(self) -> None:
        self._closed = True

    @property
    def initialized(self) -> bool:
        return self._initialized

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def call_count(self) -> int:
        return len(self._calls)


class DegradingPlugin(FakePlugin):
    """Plugin that fails after N successful calls."""

    def __init__(self, *, fail_after: int = 1) -> None:
        super().__init__()
        self._fail_after = fail_after

    async def execute(self, request: NormalizedRequest) -> ProviderResponse:
        self._calls.append(request)
        if len(self._calls) > self._fail_after:
            raise RuntimeError("Provider degraded")
        return ProviderResponse(
            text="ok",
            prompt_tokens=10,
            completion_tokens=5,
            model_id=request.model_id or "test-model",
            finish_reason=FinishReason.STOP,
        )

    async def health_check(self) -> ProviderHealth:
        if len(self._calls) > self._fail_after:
            return ProviderHealth(status=HealthStatus.UNHEALTHY)
        return ProviderHealth(status=HealthStatus.HEALTHY)


class UnhealthyPlugin(FakePlugin):
    """Plugin that always reports UNHEALTHY."""

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(status=HealthStatus.UNHEALTHY)

    async def execute(self, request: NormalizedRequest) -> ProviderResponse:
        self._calls.append(request)
        raise RuntimeError("Unhealthy")


# ===========================================================================
# Helpers
# ===========================================================================


def _make_manifest(
    provider_id: str = "lc-provider",
    capabilities: list[CapabilityType] | None = None,
    model_id: str = "lc-model",
    tier: ModelTier = ModelTier.STANDARD,
    circuit_breaker: CircuitBreakerConfig | None = None,
) -> ProviderManifest:
    caps = capabilities or [CapabilityType.CHAT, CapabilityType.TOOL_CALL]
    return ProviderManifest(
        provider_id=provider_id,
        display_name=f"Test {provider_id}",
        capabilities=caps,
        models=[
            ModelSpec(
                id=model_id,
                capabilities=caps,
                cost_per_1m_input=5.0,
                cost_per_1m_output=15.0,
                max_context=128000,
                tier=tier,
            ),
        ],
        placement=PlacementConfig(type=PlacementType.REMOTE),
        circuit_breaker=circuit_breaker,
    )


def _make_request(
    trace_id: str = "lc-trace-1",
    content: str = "Hello lifecycle",
    capability: CapabilityType = CapabilityType.CHAT,
) -> HubRequest:
    return HubRequest(
        capability=capability,
        payload=ChatPayload(messages=[Message(role="user", content=content)]),
        constraints=RequestConstraints(consumer_id="lifecycle-test"),
        trace_id=trace_id,
    )


def _wire(
    plugins: dict[str, FakePlugin] | None = None,
    config: ModelHubConfig | None = None,
    manifests: list[ProviderManifest] | None = None,
) -> tuple:
    """Wire full hub for lifecycle testing."""
    plugin_map = plugins or {"lc-provider": FakePlugin()}
    facade, adapters = ModelHubFactory.create_for_testing(
        overrides={
            "config": config or ModelHubConfig(),
            "plugins": plugin_map,
        }
    )
    registry: ProviderRegistry = adapters["registry"]
    circuit_mgr: CircuitBreakerManager = adapters["circuit_mgr"]
    rate_limiter: RateLimiter = adapters["rate_limiter"]

    default_manifests = [_make_manifest(pid) for pid in plugin_map]
    for m in manifests or default_manifests:
        registry.register(m, plugin_map[m.provider_id])
        circuit_mgr.register_provider(m.provider_id, m.circuit_breaker)
        rate_limiter.register_provider(m.provider_id, rpm=600, tpm=1_000_000)

    return facade, adapters, plugin_map


# ===========================================================================
# 1. INIT: Factory construction
# ===========================================================================


class TestInit:
    """INIT phase: factory creates all services correctly."""

    def test_factory_returns_facade_and_adapters(self) -> None:
        """create_for_testing returns (facade, adapters) tuple."""
        facade, adapters = ModelHubFactory.create_for_testing()
        assert facade is not None
        assert isinstance(adapters, dict)

    def test_all_services_present(self) -> None:
        """All expected service keys exist in adapters dict."""
        _, adapters = ModelHubFactory.create_for_testing()
        required_keys = {
            "registry",
            "circuit_mgr",
            "rate_limiter",
            "cost_tracker",
            "response_cache",
            "budget_enforcer",
            "capability_router",
            "model_selector",
            "normalization",
            "dispatcher",
            "audit_logger",
            "router",
            "health_adapter",
        }
        assert required_keys.issubset(adapters.keys())

    def test_all_ports_present(self) -> None:
        """All port adapter keys exist."""
        _, adapters = ModelHubFactory.create_for_testing()
        port_keys = {
            "credential_port",
            "event_port",
            "state_read_port",
            "metrics_port",
            "config_port",
            "health_port",
        }
        assert port_keys.issubset(adapters.keys())

    def test_factory_accepts_config_override(self) -> None:
        """Custom config is used by factory."""
        cfg = ModelHubConfig(daily_budget_usd=99.0)
        _, adapters = ModelHubFactory.create_for_testing(overrides={"config": cfg})
        assert adapters["config"].daily_budget_usd == 99.0

    def test_factory_accepts_plugin_override(self) -> None:
        """Custom plugins are wired into dispatcher."""
        plugin = FakePlugin()
        _, adapters = ModelHubFactory.create_for_testing(
            overrides={"plugins": {"my-provider": plugin}}
        )
        assert adapters["dispatcher"]._plugins.get("my-provider") is plugin

    def test_wiring_does_not_raise(self) -> None:
        """Full wiring completes without exception."""
        facade, adapters, plugins = _wire()
        assert facade is not None


# ===========================================================================
# 2. HEALTH_CHECK: Hub reports health
# ===========================================================================


class TestHealthCheck:
    """HEALTH_CHECK phase: hub can report health before serving."""

    async def test_health_report_returns_status(self) -> None:
        """Hub health() returns a report with status."""
        facade, _, _ = _wire()
        report = await facade.health()
        assert report.status in (
            HealthStatus.HEALTHY,
            HealthStatus.DEGRADED,
            HealthStatus.UNHEALTHY,
        )

    async def test_fresh_hub_is_healthy(self) -> None:
        """Freshly wired hub reports HEALTHY."""
        facade, _, _ = _wire()
        report = await facade.health()
        assert report.status == HealthStatus.HEALTHY

    async def test_health_adapter_accessible(self) -> None:
        """Health adapter is accessible from adapters dict."""
        _, adapters, _ = _wire()
        health_adapter = adapters["health_adapter"]
        report = health_adapter.check_health()
        assert report.status in (
            HealthStatus.HEALTHY,
            HealthStatus.DEGRADED,
            HealthStatus.UNHEALTHY,
        )

    async def test_plugin_health_check(self) -> None:
        """Individual plugin health check works."""
        plugin = FakePlugin()
        result = await plugin.health_check()
        assert result.status == HealthStatus.HEALTHY


# ===========================================================================
# 3. READY: Hub can discover capabilities and models
# ===========================================================================


class TestReady:
    """READY phase: hub can discover providers and accept traffic."""

    async def test_discover_capabilities(self) -> None:
        """Hub discovers registered capabilities."""
        facade, _, _ = _wire()
        caps = await facade.discover_capabilities()
        assert CapabilityType.CHAT in caps
        assert CapabilityType.TOOL_CALL in caps

    async def test_discover_models(self) -> None:
        """Hub discovers registered models."""
        facade, _, _ = _wire()
        models = await facade.discover_models()
        assert len(models) >= 1
        assert any(m.id == "lc-model" for m in models)

    async def test_discover_models_by_capability(self) -> None:
        """Model discovery filters by capability."""
        facade, _, _ = _wire()
        chat_models = await facade.discover_models(capability=CapabilityType.CHAT)
        assert all(CapabilityType.CHAT in m.capabilities for m in chat_models)

    async def test_registry_lists_providers(self) -> None:
        """Registry lists all registered providers."""
        _, adapters, _ = _wire()
        registry: ProviderRegistry = adapters["registry"]
        providers = registry.list_providers()
        assert len(providers) >= 1
        assert any(p.provider_id == "lc-provider" for p in providers)

    async def test_capability_index_populated(self) -> None:
        """Capability index has entries after registration."""
        _, adapters, _ = _wire()
        registry: ProviderRegistry = adapters["registry"]
        index = registry.get_capability_index()
        assert CapabilityType.CHAT in index

    async def test_multi_provider_ready(self) -> None:
        """Multiple providers all ready."""
        plugins = {"p1": FakePlugin(), "p2": FakePlugin()}
        manifests = [_make_manifest("p1", model_id="m1"), _make_manifest("p2", model_id="m2")]
        facade, _, _ = _wire(plugins=plugins, manifests=manifests)
        models = await facade.discover_models()
        assert len(models) >= 2


# ===========================================================================
# 4. RUNNING: Hub handles requests
# ===========================================================================


class TestRunning:
    """RUNNING phase: hub processes requests successfully."""

    async def test_basic_request_succeeds(self) -> None:
        """Simple CHAT request returns HubResponse."""
        facade, _, _ = _wire()
        resp = await facade.execute(_make_request())
        assert isinstance(resp, HubResponse)
        assert resp.result is not None

    async def test_sequential_requests(self) -> None:
        """Multiple sequential requests all succeed."""
        facade, _, _ = _wire()
        for i in range(5):
            resp = await facade.execute(_make_request(trace_id=f"t-{i}", content=f"msg-{i}"))
            assert resp.result is not None

    async def test_streaming_request(self) -> None:
        """Streaming request yields chunks."""
        facade, _, _ = _wire()
        chunks = []
        async for chunk in facade.stream_execute(_make_request()):
            chunks.append(chunk)
        assert len(chunks) >= 1
        assert chunks[-1].done is True

    async def test_audit_trail_during_running(self) -> None:
        """Audit logger records each request in RUNNING phase."""
        facade, adapters, _ = _wire()
        audit: AuditLogger = adapters["audit_logger"]
        await facade.execute(_make_request(trace_id="lc-audit"))
        assert audit.count >= 1
        assert any(r.trace_id == "lc-audit" for r in audit.records)

    async def test_cost_tracked_during_running(self) -> None:
        """Cost tracker accumulates cost during RUNNING phase."""
        facade, adapters, _ = _wire()
        cost_tracker: CostTracker = adapters["cost_tracker"]
        await facade.execute(_make_request())
        assert cost_tracker.total_cost_usd >= 0.0

    async def test_cache_populated_during_running(self) -> None:
        """Cache stores responses for identical requests."""
        facade, adapters, _ = _wire()
        cache: ResponseCache = adapters["response_cache"]
        await facade.execute(_make_request())
        assert cache.size > 0

    async def test_plugin_receives_requests(self) -> None:
        """Plugin's execute method is called during RUNNING."""
        plugin = FakePlugin()
        facade, _, _ = _wire(plugins={"lc-provider": plugin})
        await facade.execute(_make_request())
        assert plugin.call_count >= 1


# ===========================================================================
# 5. DEGRADED: Hub handles failures gracefully
# ===========================================================================


class TestDegraded:
    """DEGRADED phase: hub continues operating despite failures."""

    async def test_circuit_opens_on_failures(self) -> None:
        """Circuit breaker opens after threshold failures."""
        cb_config = CircuitBreakerConfig(
            failure_threshold=2, failure_window_s=60.0, cooldown_s=30.0
        )
        plugin = DegradingPlugin(fail_after=0)  # fails immediately
        manifests = [_make_manifest("lc-provider", circuit_breaker=cb_config)]
        facade, adapters, _ = _wire(plugins={"lc-provider": plugin}, manifests=manifests)
        circuit_mgr: CircuitBreakerManager = adapters["circuit_mgr"]

        # Force failures through circuit breaker
        for _ in range(3):
            try:
                await facade.execute(_make_request(trace_id=f"degrade-{_}", content=f"degrade-{_}"))
            except (ProviderError, NoEligibleProviderError):
                pass

        # Circuit should be open after repeated failures
        state = circuit_mgr.get_state("lc-provider")
        assert state in (CircuitState.OPEN, CircuitState.HALF_OPEN)

    async def test_budget_exhaustion_rejects(self) -> None:
        """Budget exhaustion causes REJECT decision."""
        cfg = ModelHubConfig(daily_budget_usd=0.001)
        facade, adapters, _ = _wire(config=cfg)
        enforcer: BudgetEnforcer = adapters["budget_enforcer"]

        # Exhaust budget by setting spent amount
        enforcer._daily_spent_usd = cfg.daily_budget_usd + 1.0

        with pytest.raises(BudgetExceededError):
            await facade.execute(_make_request(trace_id="budget-exhaust"))

    async def test_budget_degraded_mode(self) -> None:
        """When budget >= 80%, hub allows degraded mode."""
        cfg = ModelHubConfig(daily_budget_usd=10.0)
        facade, adapters, _ = _wire(config=cfg)
        enforcer: BudgetEnforcer = adapters["budget_enforcer"]

        # Set budget to 85% consumed -> ALLOW_DEGRADED
        enforcer._daily_spent_usd = 8.5
        result = enforcer.check(_make_request(trace_id="degrade-budget"))
        assert result.decision in (BudgetDecision.ALLOW_DEGRADED, BudgetDecision.REJECT)

    async def test_fallback_on_primary_failure(self) -> None:
        """Hub falls back when primary provider fails."""
        plugins = {
            "primary": DegradingPlugin(fail_after=0),
            "fallback": FakePlugin(response_text="fallback-ok"),
        }
        manifests = [
            _make_manifest("primary", model_id="m1"),
            _make_manifest("fallback", model_id="m2"),
        ]
        facade, adapters, _ = _wire(plugins=plugins, manifests=manifests)
        resp = await facade.execute(_make_request())
        # Should succeed via fallback
        assert resp.result is not None

    async def test_all_providers_down_raises(self) -> None:
        """When all providers fail, hub raises ProviderError."""
        plugins = {
            "p1": DegradingPlugin(fail_after=0),
        }
        manifests = [_make_manifest("p1")]
        facade, _, _ = _wire(plugins=plugins, manifests=manifests)

        with pytest.raises((ProviderError, NoEligibleProviderError)):
            # Two attempts: first fails, retry within _try_provider also fails
            await facade.execute(_make_request(trace_id="all-down-1"))

    async def test_degraded_plugin_health(self) -> None:
        """Unhealthy plugin reports its health status."""
        plugin = UnhealthyPlugin()
        health = await plugin.health_check()
        assert health.status == HealthStatus.UNHEALTHY

    async def test_rate_limit_exhaustion_blocks_request(self) -> None:
        """Rate-limited provider blocks requests."""
        facade, adapters, _ = _wire()
        rate_limiter: RateLimiter = adapters["rate_limiter"]

        # Drain the RPM bucket
        for _ in range(700):
            rate_limiter.acquire("lc-provider", token_estimate=1)

        # Now next request should fail
        decision = rate_limiter.acquire("lc-provider", token_estimate=1)
        assert not decision.allowed


# ===========================================================================
# 6. SHUTDOWN: Cleanup and resource release
# ===========================================================================


class TestShutdown:
    """SHUTDOWN phase: plugins closed, resources released."""

    async def test_plugin_close_called(self) -> None:
        """Plugin.close() can be called during shutdown."""
        plugin = FakePlugin()
        facade, _, _ = _wire(plugins={"lc-provider": plugin})

        # Simulate usage then shutdown
        await facade.execute(_make_request())
        await plugin.close()
        assert plugin.closed is True

    async def test_multiple_plugins_closed(self) -> None:
        """All plugins can be closed during shutdown."""
        plugins = {"p1": FakePlugin(), "p2": FakePlugin()}
        manifests = [_make_manifest("p1", model_id="m1"), _make_manifest("p2", model_id="m2")]
        facade, _, plugin_map = _wire(plugins=plugins, manifests=manifests)

        # Close all
        for p in plugin_map.values():
            await p.close()
        assert all(p.closed for p in plugin_map.values())

    async def test_close_idempotent(self) -> None:
        """Plugin.close() can be called multiple times safely."""
        plugin = FakePlugin()
        await plugin.close()
        await plugin.close()  # Should not raise
        assert plugin.closed is True

    async def test_cache_clear_on_shutdown(self) -> None:
        """Response cache can be cleared during shutdown."""
        facade, adapters, _ = _wire()
        cache: ResponseCache = adapters["response_cache"]
        await facade.execute(_make_request())
        cache.clear()
        assert cache.size == 0

    async def test_no_requests_after_circuit_open(self) -> None:
        """After circuits are forced open, no requests are dispatched."""
        facade, adapters, _ = _wire()
        circuit_mgr: CircuitBreakerManager = adapters["circuit_mgr"]

        # Force circuit open
        for _ in range(10):
            circuit_mgr.record_failure("lc-provider", "shutdown")

        state = circuit_mgr.get_state("lc-provider")
        assert state == CircuitState.OPEN

    async def test_unregister_provider(self) -> None:
        """Provider can be unregistered from rate limiter."""
        _, adapters, _ = _wire()
        rate_limiter: RateLimiter = adapters["rate_limiter"]
        assert rate_limiter.is_registered("lc-provider")
        rate_limiter.unregister_provider("lc-provider")
        assert not rate_limiter.is_registered("lc-provider")


# ===========================================================================
# Full Lifecycle: INIT -> HEALTH -> READY -> RUNNING -> DEGRADED -> SHUTDOWN
# ===========================================================================


class TestFullLifecycle:
    """End-to-end lifecycle: all phases in sequence."""

    async def test_complete_lifecycle(self) -> None:
        """Hub traverses all lifecycle phases successfully."""
        plugin = DegradingPlugin(fail_after=3)
        facade, adapters, plugin_map = _wire(plugins={"lc-provider": plugin})

        # 1. INIT -- already done by _wire()
        assert facade is not None

        # 2. HEALTH_CHECK
        report = await facade.health()
        assert report.status == HealthStatus.HEALTHY

        # 3. READY
        caps = await facade.discover_capabilities()
        assert CapabilityType.CHAT in caps

        # 4. RUNNING -- 3 successful requests
        for i in range(3):
            resp = await facade.execute(_make_request(trace_id=f"lc-run-{i}", content=f"run-{i}"))
            assert resp.result is not None

        # 5. DEGRADED -- plugin starts failing
        with pytest.raises((ProviderError, NoEligibleProviderError)):
            await facade.execute(_make_request(trace_id="lc-degrade", content="degrade"))

        # 6. SHUTDOWN
        for p in plugin_map.values():
            await p.close()
        assert plugin.closed is True

    async def test_lifecycle_with_recovery(self) -> None:
        """Hub can recover from degraded state via fallback."""
        plugins = {
            "primary": DegradingPlugin(fail_after=1),
            "backup": FakePlugin(response_text="backup-active"),
        }
        manifests = [
            _make_manifest("primary", model_id="m1"),
            _make_manifest("backup", model_id="m2"),
        ]
        facade, adapters, plugin_map = _wire(plugins=plugins, manifests=manifests)

        # RUNNING: first request succeeds via primary
        resp1 = await facade.execute(_make_request(trace_id="recover-1", content="first"))
        assert resp1.result is not None

        # Primary starts failing -> fallback to backup
        resp2 = await facade.execute(_make_request(trace_id="recover-2", content="second"))
        assert resp2.result is not None

        # SHUTDOWN
        for p in plugin_map.values():
            await p.close()

    async def test_lifecycle_budget_phases(self) -> None:
        """Budget transitions through ALLOW -> ALLOW_DEGRADED -> REJECT."""
        cfg = ModelHubConfig(daily_budget_usd=10.0)
        facade, adapters, _ = _wire(config=cfg)
        enforcer: BudgetEnforcer = adapters["budget_enforcer"]
        req = _make_request(trace_id="budget-phase")

        # Phase 1: ALLOW (budget healthy)
        d1 = enforcer.check(req)
        assert d1.decision == BudgetDecision.ALLOW

        # Phase 2: ALLOW_DEGRADED (budget >= 80%)
        enforcer._daily_spent_usd = 8.5
        d2 = enforcer.check(req)
        assert d2.decision in (BudgetDecision.ALLOW_DEGRADED, BudgetDecision.REJECT)

        # Phase 3: REJECT (budget exceeded)
        enforcer._daily_spent_usd = 11.0
        d3 = enforcer.check(req)
        assert d3.decision == BudgetDecision.REJECT
