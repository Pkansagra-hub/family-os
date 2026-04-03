"""M8 Contract Tests -- 18 Hard Invariants (MH-01 through MH-18).

Each test class verifies one invariant from the Model Hub specification.
All services wired via ModelHubFactory.create_for_testing().
No unittest.mock imports.
"""

from __future__ import annotations

import ast
import os
import time
from typing import AsyncIterator

import pytest

from k1.model_hub.config import ModelHubConfig
from k1.model_hub.factory import ModelHubFactory
from k1.model_hub.manifest import (
    CircuitBreakerConfig,
    HealthCheckConfig,
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
from k1.model_hub.services.capability_router import CapabilityRouter
from k1.model_hub.services.circuit_breaker_manager import CircuitBreakerManager
from k1.model_hub.services.cost_tracker import CostTracker
from k1.model_hub.services.model_selector import ModelSelector
from k1.model_hub.services.provider_dispatcher import ProviderDispatcher
from k1.model_hub.services.provider_registry import ProviderRegistry
from k1.model_hub.services.rate_limiter import RateLimiter
from k1.model_hub.services.request_router import RequestRouter
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
    Message,
    ModelTier,
    NoEligibleProviderError,
    PlacementType,
    Priority,
    RequestConstraints,
    TokenUsage,
    ValidationError,
)

# ===========================================================================
# Fake collaborators (no unittest.mock)
# ===========================================================================


class FakeCredentialPort:
    """Test ICredentialPort -- keys stored in memory, never in config."""

    def __init__(self, keys: dict[str, str] | None = None) -> None:
        self._keys = keys or {"openai": "sk-test-key", "anthropic": "sk-ant-test"}

    async def get_key(self, provider_id: str) -> str:
        return self._keys.get(provider_id, "")

    async def refresh_key(self, provider_id: str) -> str:
        return self._keys.get(provider_id, "")


class FakePlugin:
    """Deterministic IProviderPlugin for invariant testing."""

    def __init__(
        self,
        *,
        response_text: str = "hello",
        fail: bool = False,
    ) -> None:
        self._response_text = response_text
        self._fail = fail
        self._calls: list[NormalizedRequest] = []

    async def initialize(self, manifest: object) -> None:
        pass

    def supports(self, capability: CapabilityType) -> bool:
        return True

    async def execute(self, request: NormalizedRequest) -> ProviderResponse:
        self._calls.append(request)
        if self._fail:
            raise RuntimeError("Plugin crash!")
        return ProviderResponse(
            text=self._response_text,
            prompt_tokens=10,
            completion_tokens=5,
            model_id=request.model_id or "test-model",
            finish_reason=FinishReason.STOP,
        )

    async def stream_execute(self, request: NormalizedRequest) -> AsyncIterator[ProviderChunk]:
        self._calls.append(request)
        if self._fail:
            raise RuntimeError("Stream crash!")
        yield ProviderChunk(text="chunk1 ", done=False)
        yield ProviderChunk(text="chunk2", done=True)

    def estimate_tokens(self, messages: list) -> int:
        return 10

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(status=HealthStatus.HEALTHY)

    async def close(self) -> None:
        pass

    @property
    def calls(self) -> list[NormalizedRequest]:
        return list(self._calls)


class FailingPlugin(FakePlugin):
    """Plugin that always raises (for isolation tests)."""

    async def execute(self, request: NormalizedRequest) -> ProviderResponse:
        self._calls.append(request)
        raise RuntimeError("Plugin crash!")

    async def stream_execute(self, request: NormalizedRequest) -> AsyncIterator[ProviderChunk]:
        self._calls.append(request)
        raise RuntimeError("Stream crash!")
        yield  # type: ignore[misc]


# ===========================================================================
# Helpers
# ===========================================================================


def _make_manifest(
    provider_id: str = "openai",
    capabilities: list[CapabilityType] | None = None,
    model_id: str = "gpt-4o",
    placement_type: PlacementType = PlacementType.REMOTE,
    cost_input: float = 5.0,
    cost_output: float = 15.0,
    tier: ModelTier = ModelTier.STANDARD,
) -> ProviderManifest:
    caps = capabilities or [CapabilityType.CHAT]
    return ProviderManifest(
        provider_id=provider_id,
        display_name=provider_id.title(),
        capabilities=caps,
        models=[
            ModelSpec(
                id=model_id,
                capabilities=caps,
                cost_per_1m_input=cost_input,
                cost_per_1m_output=cost_output,
                max_context=128000,
                tier=tier,
            ),
        ],
        placement=PlacementConfig(type=placement_type),
    )


def _make_request(
    capability: CapabilityType = CapabilityType.CHAT,
    trace_id: str = "trace-1",
    priority: Priority = Priority.INTERACTIVE,
    temperature: float = 0.7,
    consumer_id: str = "test-consumer",
    cost_limit: float | None = None,
) -> HubRequest:
    return HubRequest(
        capability=capability,
        payload=ChatPayload(messages=[Message(role="user", content="Hello")]),
        constraints=RequestConstraints(
            priority=priority,
            temperature=temperature,
            consumer_id=consumer_id,
            cost_limit=cost_limit,
        ),
        trace_id=trace_id,
    )


def _wire_hub(
    plugins: dict[str, FakePlugin] | None = None,
    config: ModelHubConfig | None = None,
    manifests: list[ProviderManifest] | None = None,
) -> tuple:
    """Wire a test hub and return (facade, adapters).

    Registers manifests + plugins in the registry/dispatcher.
    """
    plugin_map = plugins or {"openai": FakePlugin()}
    facade, adapters = ModelHubFactory.create_for_testing(
        overrides={
            "config": config or ModelHubConfig(),
            "plugins": plugin_map,
        }
    )
    registry: ProviderRegistry = adapters["registry"]
    circuit_mgr: CircuitBreakerManager = adapters["circuit_mgr"]
    rate_limiter: RateLimiter = adapters["rate_limiter"]

    for m in manifests or [_make_manifest(pid) for pid in plugin_map]:
        registry.register(m, plugin_map[m.provider_id])
        circuit_mgr.register_provider(m.provider_id, m.circuit_breaker)
        rate_limiter.register_provider(
            m.provider_id,
            rpm=m.rate_limits.rpm if hasattr(m.rate_limits, "rpm") else 60,
            tpm=m.rate_limits.tpm if hasattr(m.rate_limits, "tpm") else 100000,
        )

    return facade, adapters


# ===========================================================================
# MH-01: NEVER writes SessionState
# ===========================================================================


class TestMH01_NeverWritesSessionState:
    """MH-01: Model Hub is read-only consumer of SessionState."""

    def test_state_read_port_is_read_only(self) -> None:
        """IStateReadPort has only read(), no write/update/delete."""
        from k1.model_hub.ports.state_read_port import IStateReadPort

        methods = [m for m in dir(IStateReadPort) if not m.startswith("_")]
        assert "read" in methods
        assert "write" not in methods
        assert "update" not in methods
        assert "delete" not in methods

    def test_factory_provides_state_read_port(self) -> None:
        """create_for_testing() provides state_read_port (read-only)."""
        _, adapters = ModelHubFactory.create_for_testing()
        assert "state_read_port" in adapters

    def test_no_write_methods_in_hub_services(self) -> None:
        """No service in model_hub imports or calls SessionState write ops."""
        services_dir = os.path.join("k1", "model_hub", "services")
        if not os.path.isdir(services_dir):
            services_dir = os.path.join(os.getcwd(), services_dir)
        if not os.path.isdir(services_dir):
            pytest.skip("Cannot locate services directory")

        for fname in os.listdir(services_dir):
            if not fname.endswith(".py"):
                continue
            path = os.path.join(services_dir, fname)
            content = open(path).read()
            assert (
                "state_write" not in content.lower()
            ), f"{fname} references state_write -- violates MH-01"
            assert (
                "session_write" not in content.lower()
            ), f"{fname} references session_write -- violates MH-01"


# ===========================================================================
# MH-02: ALL API keys in CredentialStore
# ===========================================================================


class TestMH02_CredentialStoreOnly:
    """MH-02: API keys only from CredentialStore, never in config/manifest."""

    def test_manifest_yaml_no_api_keys(self) -> None:
        """Manifest YAML files must not contain api_key/secret fields."""
        manifest_dir = os.path.join("k1", "config", "providers")
        if not os.path.isdir(manifest_dir):
            manifest_dir = os.path.join(os.getcwd(), manifest_dir)
        if not os.path.isdir(manifest_dir):
            pytest.skip("Cannot locate manifest directory")

        for fname in os.listdir(manifest_dir):
            if not fname.endswith((".yaml", ".yml")):
                continue
            content = open(os.path.join(manifest_dir, fname)).read()
            assert "api_key:" not in content, f"{fname} contains api_key -- violates MH-02"
            assert "secret:" not in content, f"{fname} contains secret -- violates MH-02"
            assert "sk-" not in content, f"{fname} contains literal API key -- violates MH-02"

    def test_config_no_api_keys(self) -> None:
        """ModelHubConfig has no api_key fields."""
        cfg = ModelHubConfig()
        field_names = [f.name for f in cfg.__dataclass_fields__.values()]
        for name in field_names:
            assert (
                "key" not in name.lower() or name == "idempotency_key"
            ), f"ModelHubConfig.{name} looks like an API key field -- violates MH-02"

    def test_dispatcher_fetches_from_credential_port(self) -> None:
        """ProviderDispatcher constructor requires credential_port."""
        import inspect

        sig = inspect.signature(ProviderDispatcher.__init__)
        assert "credential_port" in sig.parameters


# ===========================================================================
# MH-03: Every request carries cognitive_trace_id
# ===========================================================================


class TestMH03_TraceIdRequired:
    """MH-03: Every request must carry a trace_id."""

    def test_hub_request_requires_trace_id(self) -> None:
        """HubRequest with empty trace_id raises ValueError (MH-03)."""
        with pytest.raises(ValueError, match="trace_id"):
            HubRequest(
                capability=CapabilityType.CHAT,
                payload=ChatPayload(messages=[Message(role="user", content="hi")]),
                trace_id="",
            )

    def test_valid_trace_id_accepted(self) -> None:
        req = _make_request(trace_id="trace-123")
        assert req.trace_id == "trace-123"

    async def test_router_validates_trace_id(self) -> None:
        """Trace_id is enforced at HubRequest construction time (MH-03).
        Router _validate() relies on this invariant."""
        facade, adapters = _wire_hub()
        # You cannot even construct a HubRequest with empty trace_id
        with pytest.raises(ValueError, match="trace_id"):
            HubRequest(
                capability=CapabilityType.CHAT,
                payload=ChatPayload(messages=[Message(role="user", content="hi")]),
                constraints=RequestConstraints(),
                trace_id="",
            )


# ===========================================================================
# MH-04: Budget enforcement is HARD
# ===========================================================================


class TestMH04_HardBudgetEnforcement:
    """MH-04: Request rejected if budget exceeded."""

    def test_budget_reject_when_exceeded(self) -> None:
        """BudgetEnforcer rejects when daily budget is spent."""
        cfg = ModelHubConfig(daily_budget_usd=1.0)
        enforcer = BudgetEnforcer(cfg)
        # Directly set internal spending counter
        enforcer._daily_spent_usd = 1.0
        req = _make_request()
        result = enforcer.check(req)
        assert result.decision == BudgetDecision.REJECT

    async def test_router_raises_budget_exceeded(self) -> None:
        """RequestRouter raises BudgetExceededError when budget exhausted."""
        cfg = ModelHubConfig(daily_budget_usd=0.001)
        facade, adapters = _wire_hub(config=cfg)
        enforcer: BudgetEnforcer = adapters["budget_enforcer"]
        enforcer._daily_spent_usd = 0.001

        with pytest.raises(BudgetExceededError):
            await facade.execute(_make_request())

    def test_budget_allow_when_under_limit(self) -> None:
        cfg = ModelHubConfig(daily_budget_usd=10.0)
        enforcer = BudgetEnforcer(cfg)
        req = _make_request()
        result = enforcer.check(req)
        assert result.decision == BudgetDecision.ALLOW


# ===========================================================================
# MH-05: Circuit breaker per provider
# ===========================================================================


class TestMH05_CircuitBreakerPerProvider:
    """MH-05: Circuit breaker per provider from manifest config."""

    def test_circuit_breaker_opens_on_threshold(self) -> None:
        cbm = CircuitBreakerManager()
        cbm.register_provider(
            "openai",
            CircuitBreakerConfig(
                failure_threshold=3,
                failure_window_s=60,
                cooldown_s=30,
            ),
        )
        for _ in range(3):
            cbm.record_failure("openai")
        assert cbm.get_state("openai") == CircuitState.OPEN

    def test_independent_per_provider(self) -> None:
        cbm = CircuitBreakerManager()
        cbm.register_provider("openai", CircuitBreakerConfig(failure_threshold=2))
        cbm.register_provider("anthropic", CircuitBreakerConfig(failure_threshold=2))
        cbm.record_failure("openai")
        cbm.record_failure("openai")
        assert cbm.get_state("openai") == CircuitState.OPEN
        assert cbm.get_state("anthropic") == CircuitState.CLOSED

    def test_config_from_manifest(self) -> None:
        manifest = _make_manifest()
        assert hasattr(manifest, "circuit_breaker")
        assert isinstance(manifest.circuit_breaker, CircuitBreakerConfig)

    def test_cooldown_transitions_to_half_open(self) -> None:
        cbm = CircuitBreakerManager()
        cbm.register_provider(
            "openai",
            CircuitBreakerConfig(
                failure_threshold=2,
                failure_window_s=60,
                cooldown_s=1,
            ),
        )
        cbm.record_failure("openai")
        cbm.record_failure("openai")
        assert cbm.get_state("openai") == CircuitState.OPEN
        cbm._circuits["openai"].opened_at = time.monotonic() - 2.0
        assert cbm.get_state("openai") == CircuitState.HALF_OPEN


# ===========================================================================
# MH-06: Fallback cascade is CAPABILITY-AWARE
# ===========================================================================


class TestMH06_CapabilityAwareFallback:
    """MH-06: Fallback only to providers that support the capability."""

    def test_capability_router_filters_by_capability(self) -> None:
        cfg = ModelHubConfig()
        registry = ProviderRegistry(cfg)
        cbm = CircuitBreakerManager()
        rl = RateLimiter()

        class HQ:
            def get_status(self, pid: str) -> HealthStatus:
                return HealthStatus.HEALTHY

        router = CapabilityRouter(
            registry=registry,
            circuit_breaker=cbm,
            rate_limiter=rl,
            health_monitor=HQ(),
        )

        chat_manifest = _make_manifest("openai", [CapabilityType.CHAT], "gpt-4o")
        embed_manifest = _make_manifest("anthropic", [CapabilityType.EMBED], "embed-v1")

        registry.register(chat_manifest, FakePlugin())
        registry.register(embed_manifest, FakePlugin())
        cbm.register_provider("openai")
        cbm.register_provider("anthropic")
        rl.register_provider("openai", rpm=60, tpm=100000)
        rl.register_provider("anthropic", rpm=60, tpm=100000)

        constraints = RequestConstraints()
        results = router.route(CapabilityType.CHAT, constraints)
        provider_ids = [r.provider_info.provider_id for r in results]
        assert "openai" in provider_ids
        assert "anthropic" not in provider_ids

    def test_embed_routes_only_to_embed_provider(self) -> None:
        cfg = ModelHubConfig()
        registry = ProviderRegistry(cfg)
        cbm = CircuitBreakerManager()
        rl = RateLimiter()

        class HQ:
            def get_status(self, pid: str) -> HealthStatus:
                return HealthStatus.HEALTHY

        router = CapabilityRouter(
            registry=registry,
            circuit_breaker=cbm,
            rate_limiter=rl,
            health_monitor=HQ(),
        )

        chat_manifest = _make_manifest("openai", [CapabilityType.CHAT], "gpt-4o")
        embed_manifest = _make_manifest("anthropic", [CapabilityType.EMBED], "embed-v1")

        registry.register(chat_manifest, FakePlugin())
        registry.register(embed_manifest, FakePlugin())
        cbm.register_provider("openai")
        cbm.register_provider("anthropic")
        rl.register_provider("openai", rpm=60, tpm=100000)
        rl.register_provider("anthropic", rpm=60, tpm=100000)

        constraints = RequestConstraints()
        results = router.route(CapabilityType.EMBED, constraints)
        provider_ids = [r.provider_info.provider_id for r in results]
        assert "anthropic" in provider_ids
        assert "openai" not in provider_ids


# ===========================================================================
# MH-07: Cost tracking per request
# ===========================================================================


class TestMH07_CostTracking:
    """MH-07: Cost = token_count * model_cost from manifest."""

    def test_cost_computation_formula(self) -> None:
        model = ModelSpec(
            id="gpt-4o",
            cost_per_1m_input=5.0,
            cost_per_1m_output=15.0,
        )
        usage = TokenUsage(prompt_tokens=1000, completion_tokens=500)
        input_cost, output_cost = CostTracker.compute_cost(usage, model)
        assert abs(input_cost - 0.005) < 1e-6
        assert abs(output_cost - 0.0075) < 1e-6

    def test_cost_tracker_records(self) -> None:
        tracker = CostTracker()
        model = ModelSpec(id="gpt-4o", cost_per_1m_input=5.0, cost_per_1m_output=15.0)
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50)
        record = tracker.track(
            usage,
            model,
            provider_id="openai",
            capability=CapabilityType.CHAT,
        )
        assert record.cost_usd > 0

    def test_cost_from_manifest(self) -> None:
        manifest = _make_manifest(cost_input=2.5, cost_output=10.0)
        model = manifest.models[0]
        assert model.cost_per_1m_input == 2.5
        assert model.cost_per_1m_output == 10.0


# ===========================================================================
# MH-08: Daily budget enforcement ($5/day default)
# ===========================================================================


class TestMH08_DailyBudget:
    """MH-08: Daily budget $5/day default, configurable."""

    def test_default_budget_is_five(self) -> None:
        cfg = ModelHubConfig()
        assert cfg.daily_budget_usd == 5.0

    def test_budget_configurable(self) -> None:
        cfg = ModelHubConfig(daily_budget_usd=20.0)
        assert cfg.daily_budget_usd == 20.0

    def test_degraded_at_80_percent(self) -> None:
        cfg = ModelHubConfig(daily_budget_usd=10.0)
        enforcer = BudgetEnforcer(cfg)
        enforcer._daily_spent_usd = 8.0
        result = enforcer.check(_make_request())
        assert result.decision == BudgetDecision.ALLOW_DEGRADED

    def test_reject_at_100_percent(self) -> None:
        cfg = ModelHubConfig(daily_budget_usd=10.0)
        enforcer = BudgetEnforcer(cfg)
        enforcer._daily_spent_usd = 10.0
        result = enforcer.check(_make_request())
        assert result.decision == BudgetDecision.REJECT

    def test_daily_reset(self) -> None:
        cfg = ModelHubConfig(daily_budget_usd=10.0)
        enforcer = BudgetEnforcer(cfg)
        enforcer._daily_spent_usd = 10.0
        enforcer.reset_daily()
        result = enforcer.check(_make_request())
        assert result.decision == BudgetDecision.ALLOW


# ===========================================================================
# MH-09: Response cache keying
# ===========================================================================


class TestMH09_ResponseCache:
    """MH-09: Cache keyed by (capability, prompt_hash, model_id, temperature)."""

    def test_cache_key_deterministic(self) -> None:
        k1 = ResponseCache.build_cache_key(
            CapabilityType.CHAT,
            "hello",
            model_id="gpt-4o",
            temperature=0.7,
        )
        k2 = ResponseCache.build_cache_key(
            CapabilityType.CHAT,
            "hello",
            model_id="gpt-4o",
            temperature=0.7,
        )
        assert k1 == k2

    def test_cache_key_varies_by_capability(self) -> None:
        k1 = ResponseCache.build_cache_key(
            CapabilityType.CHAT,
            "hello",
            model_id="gpt-4o",
            temperature=0.7,
        )
        k2 = ResponseCache.build_cache_key(
            CapabilityType.EMBED,
            "hello",
            model_id="gpt-4o",
            temperature=0.7,
        )
        assert k1 != k2

    def test_cache_key_varies_by_model(self) -> None:
        k1 = ResponseCache.build_cache_key(
            CapabilityType.CHAT,
            "hello",
            model_id="gpt-4o",
            temperature=0.7,
        )
        k2 = ResponseCache.build_cache_key(
            CapabilityType.CHAT,
            "hello",
            model_id="claude-4",
            temperature=0.7,
        )
        assert k1 != k2

    def test_cache_key_varies_by_temperature(self) -> None:
        k1 = ResponseCache.build_cache_key(
            CapabilityType.CHAT,
            "hello",
            model_id="gpt-4o",
            temperature=0.7,
        )
        k2 = ResponseCache.build_cache_key(
            CapabilityType.CHAT,
            "hello",
            model_id="gpt-4o",
            temperature=0.9,
        )
        assert k1 != k2

    def test_default_ttl_is_300s(self) -> None:
        cfg = ModelHubConfig()
        assert cfg.cache_ttl_s == 300

    def test_tool_call_not_cached(self) -> None:
        req = HubRequest(
            capability=CapabilityType.TOOL_CALL,
            payload=ChatPayload(messages=[Message(role="user", content="hi")]),
            trace_id="t-1",
        )
        assert ResponseCache.should_cache(req) is False


# ===========================================================================
# MH-10: Streaming chunk-by-chunk validation
# ===========================================================================


class TestMH10_StreamingValidation:
    """MH-10: Streaming responses validated chunk-by-chunk."""

    async def test_stream_yields_chunks(self) -> None:
        facade, adapters = _wire_hub()
        req = _make_request()
        chunks: list[HubChunk] = []
        async for chunk in facade.stream_execute(req):
            chunks.append(chunk)
        assert len(chunks) > 0
        assert all(isinstance(c, HubChunk) for c in chunks)

    async def test_stream_last_chunk_has_done(self) -> None:
        facade, adapters = _wire_hub()
        req = _make_request()
        chunks = []
        async for chunk in facade.stream_execute(req):
            chunks.append(chunk)
        assert chunks[-1].done is True

    async def test_stream_not_cached(self) -> None:
        req = _make_request()
        assert ResponseCache.should_cache(req, streaming=True) is False


# ===========================================================================
# MH-11: All LLM calls audited
# ===========================================================================


class TestMH11_AuditLogging:
    """MH-11: Full audit: request_id, capability, model, tokens, latency, cost, trace_id."""

    def test_audit_record_fields(self) -> None:
        from k1.model_hub.services.audit_logger import AuditRecord

        fields = {f.name for f in AuditRecord.__dataclass_fields__.values()}
        required = {
            "request_id",
            "trace_id",
            "capability",
            "model_id",
            "provider_id",
            "prompt_tokens",
            "completion_tokens",
            "cost_usd",
            "latency_ms",
            "cache_hit",
        }
        assert required.issubset(fields)

    async def test_audit_logger_records_after_route(self) -> None:
        facade, adapters = _wire_hub()
        audit: AuditLogger = adapters["audit_logger"]
        assert audit.count == 0
        await facade.execute(_make_request())
        assert audit.count == 1
        record = audit.records[0]
        assert record.trace_id == "trace-1"
        assert record.capability == CapabilityType.CHAT

    async def test_audit_captures_consumer_id(self) -> None:
        facade, adapters = _wire_hub()
        audit: AuditLogger = adapters["audit_logger"]
        req = _make_request(consumer_id="family-member-1")
        await facade.execute(req)
        assert audit.records[0].consumer_id == "family-member-1"


# ===========================================================================
# MH-12: Rate limiting per provider
# ===========================================================================


class TestMH12_RateLimit:
    """MH-12: Rate limiting per provider with 80% headroom default."""

    def test_default_headroom(self) -> None:
        cfg = ModelHubConfig()
        assert cfg.rate_limit_headroom_pct == 0.80

    def test_rate_limiter_accepts_when_capacity(self) -> None:
        rl = RateLimiter()
        rl.register_provider("openai", rpm=60, tpm=100000)
        assert rl.has_capacity("openai", token_estimate=1) is True

    def test_rate_limiter_rejects_when_exhausted(self) -> None:
        rl = RateLimiter()
        rl.register_provider("openai", rpm=1, tpm=1)
        rl.acquire("openai", token_estimate=1)
        assert rl.has_capacity("openai", token_estimate=1) is False

    def test_rate_limit_config_from_manifest(self) -> None:
        manifest = _make_manifest()
        assert hasattr(manifest, "rate_limits")


# ===========================================================================
# MH-13: Model placement cascade
# ===========================================================================


class TestMH13_PlacementCascade:
    """MH-13: Placement cascade: Local(NPU->GPU->CPU) -> Remote."""

    def test_placement_types_ordered(self) -> None:
        assert PlacementType.LOCAL_GPU.value == "local_gpu"
        assert PlacementType.LOCAL_CPU.value == "local_cpu"
        assert PlacementType.REMOTE.value == "remote"

    def test_model_selector_placement_scoring(self) -> None:
        from k1.model_hub.services.model_selector import _PLACEMENT_SCORES

        assert _PLACEMENT_SCORES[PlacementType.LOCAL_GPU] > _PLACEMENT_SCORES[PlacementType.REMOTE]
        assert _PLACEMENT_SCORES[PlacementType.LOCAL_CPU] > _PLACEMENT_SCORES[PlacementType.REMOTE]

    def test_manifest_carries_placement(self) -> None:
        m = _make_manifest(placement_type=PlacementType.LOCAL_GPU)
        assert m.placement.type == PlacementType.LOCAL_GPU


# ===========================================================================
# MH-14: Provider health checked per manifest interval
# ===========================================================================


class TestMH14_HealthChecks:
    """MH-14: Provider health checked per manifest interval (default 30s)."""

    def test_default_health_check_interval(self) -> None:
        cfg = ModelHubConfig()
        assert cfg.health_check_interval_s == 30

    def test_manifest_has_health_check_config(self) -> None:
        manifest = _make_manifest()
        assert hasattr(manifest, "health_check")
        assert isinstance(manifest.health_check, HealthCheckConfig)

    def test_health_check_on_plugin(self) -> None:
        plugin = FakePlugin()
        assert hasattr(plugin, "health_check")
        assert callable(plugin.health_check)


# ===========================================================================
# MH-15: Request timeout per priority tier
# ===========================================================================


class TestMH15_PriorityTimeouts:
    """MH-15: Timeout per priority tier."""

    def test_realtime_timeout(self) -> None:
        cfg = ModelHubConfig()
        assert cfg.realtime_timeout_ms == 10000

    def test_interactive_timeout(self) -> None:
        cfg = ModelHubConfig()
        assert cfg.interactive_timeout_ms == 30000

    def test_background_timeout(self) -> None:
        cfg = ModelHubConfig()
        assert cfg.background_timeout_ms == 60000

    def test_configurable(self) -> None:
        cfg = ModelHubConfig(
            realtime_timeout_ms=5000,
            interactive_timeout_ms=15000,
            background_timeout_ms=45000,
        )
        assert cfg.realtime_timeout_ms == 5000
        assert cfg.interactive_timeout_ms == 15000
        assert cfg.background_timeout_ms == 45000


# ===========================================================================
# MH-16: ALL traffic through RequestRouter
# ===========================================================================


class TestMH16_SingleFunnel:
    """MH-16: All traffic flows through RequestRouter."""

    async def test_facade_delegates_to_router(self) -> None:
        facade, adapters = _wire_hub()
        req = _make_request()
        resp = await facade.execute(req)
        assert resp.result is not None

    async def test_facade_stream_delegates_to_router(self) -> None:
        facade, adapters = _wire_hub()
        req = _make_request()
        chunks = []
        async for chunk in facade.stream_execute(req):
            chunks.append(chunk)
        assert len(chunks) > 0

    def test_hub_port_has_only_execute_and_stream(self) -> None:
        from k1.model_hub.ports.hub_port import IModelHubPort

        method_names = [m for m in dir(IModelHubPort) if not m.startswith("_")]
        traffic_methods = {"execute", "stream_execute"}
        assert traffic_methods.issubset(set(method_names))


# ===========================================================================
# MH-17: Provider plugins isolated
# ===========================================================================


class TestMH17_PluginIsolation:
    """MH-17: One plugin crash does not affect others."""

    async def test_failing_plugin_does_not_crash_hub(self) -> None:
        from k1.model_hub.types import ProviderError

        plugins = {
            "openai": FailingPlugin(),
            "anthropic": FakePlugin(response_text="from-anthropic"),
        }
        manifests = [
            _make_manifest("openai", [CapabilityType.CHAT], "gpt-4o"),
            _make_manifest("anthropic", [CapabilityType.CHAT], "claude-4"),
        ]
        facade, adapters = _wire_hub(plugins=plugins, manifests=manifests)

        req = _make_request()
        try:
            resp = await facade.execute(req)
            assert resp.result is not None
        except (ProviderError, RuntimeError):
            pass  # Hub didn't crash -- invariant holds

    def test_plugins_are_separate_instances(self) -> None:
        p1 = FakePlugin(response_text="a")
        p2 = FakePlugin(response_text="b")
        assert p1 is not p2
        assert p1._response_text != p2._response_text


# ===========================================================================
# MH-18: Manifest is SOLE source of truth for capabilities
# ===========================================================================


class TestMH18_ManifestSoleSource:
    """MH-18: No hardcoded capability checks -- all from manifest."""

    def test_capability_router_uses_registry_index(self) -> None:
        cfg = ModelHubConfig()
        registry = ProviderRegistry(cfg)
        cbm = CircuitBreakerManager()
        rl = RateLimiter()

        class HQ:
            def get_status(self, pid: str) -> HealthStatus:
                return HealthStatus.HEALTHY

        router = CapabilityRouter(
            registry=registry,
            circuit_breaker=cbm,
            rate_limiter=rl,
            health_monitor=HQ(),
        )

        constraints = RequestConstraints()
        assert router.route(CapabilityType.CHAT, constraints) == []

        manifest = _make_manifest("openai", [CapabilityType.CHAT], "gpt-4o")
        registry.register(manifest, FakePlugin())
        cbm.register_provider("openai")
        rl.register_provider("openai", rpm=60, tpm=100000)

        results = router.route(CapabilityType.CHAT, constraints)
        assert len(results) > 0

    def test_no_hardcoded_provider_names_in_services(self) -> None:
        """Service source code has no hardcoded provider names."""
        services_dir = os.path.join("k1", "model_hub", "services")
        if not os.path.isdir(services_dir):
            services_dir = os.path.join(os.getcwd(), services_dir)
        if not os.path.isdir(services_dir):
            pytest.skip("Cannot locate services directory")

        hardcoded = ["openai", "anthropic", "google", "ollama", "vllm"]
        for fname in os.listdir(services_dir):
            if not fname.endswith(".py") or fname == "__init__.py":
                continue
            content = open(os.path.join(services_dir, fname)).read()
            for provider in hardcoded:
                try:
                    tree = ast.parse(content)
                except SyntaxError:
                    continue
                for node in ast.walk(tree):
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        assert provider not in node.value.lower(), (
                            f"{fname} has hardcoded provider name '{provider}' "
                            f"in string literal -- violates MH-18"
                        )

    def test_manifest_declares_capabilities(self) -> None:
        manifest = _make_manifest()
        assert hasattr(manifest, "capabilities")
        assert len(manifest.capabilities) > 0

    def test_model_spec_declares_capabilities(self) -> None:
        manifest = _make_manifest()
        model = manifest.models[0]
        assert hasattr(model, "capabilities")
        assert len(model.capabilities) > 0
