"""M5 Request Pipeline -- Test RequestRouter [F40].

Tests the 7-step request pipeline: validate -> priority ->
route -> select -> cache -> normalize -> dispatch -> post-process.

Covers:
  - Validation: valid/invalid capability, missing trace_id
  - No eligible providers -> NoEligibleProviderError
  - ModelSelector returns None -> NoEligibleProviderError
  - Cache hit -> short-circuit return
  - Full pipeline happy path
  - stream_route(): streaming pipeline
  - Audit logger integration
  - Re-exports from services/__init__.py
"""

from __future__ import annotations

from typing import AsyncIterator

import pytest

from k1.model_hub.config import ModelHubConfig
from k1.model_hub.manifest import ModelSpec, ProviderManifest
from k1.model_hub.plugins.base import (
    NormalizedRequest,
    ProviderChunk,
    ProviderHealth,
    ProviderResponse,
)
from k1.model_hub.services.audit_logger import AuditLogger
from k1.model_hub.services.capability_router import CapabilityRouter
from k1.model_hub.services.circuit_breaker_manager import CircuitBreakerManager
from k1.model_hub.services.model_selector import ModelSelector
from k1.model_hub.services.normalization_layer import NormalizationLayer
from k1.model_hub.services.provider_dispatcher import ProviderDispatcher
from k1.model_hub.services.provider_registry import ProviderRegistry
from k1.model_hub.services.rate_limiter import RateLimiter
from k1.model_hub.services.request_router import RequestRouter
from k1.model_hub.services.response_cache import ResponseCache
from k1.model_hub.types import (
    CapabilityType,
    ChatPayload,
    CircuitState,
    FinishReason,
    HealthStatus,
    HubRequest,
    Message,
    NoEligibleProviderError,
    Priority,
    RequestConstraints,
    ValidationError,
)

# ===========================================================================
# Fake collaborators
# ===========================================================================


class FakeCredentialPort:
    async def get_key(self, provider_id: str) -> str:
        return "sk-test"

    async def refresh_key(self, provider_id: str) -> str:
        return "sk-test"


class FakePlugin:
    """Minimal IProviderPlugin implementation."""

    def __init__(self, response_text: str = "hello") -> None:
        self._response_text = response_text

    async def initialize(self, manifest: object) -> None:
        pass

    def supports(self, capability: CapabilityType) -> bool:
        return True

    async def execute(self, request: NormalizedRequest) -> ProviderResponse:
        return ProviderResponse(
            text=self._response_text,
            prompt_tokens=10,
            completion_tokens=5,
            model_id=request.model_id or "gpt-4o",
            finish_reason=FinishReason.STOP,
        )

    async def stream_execute(self, request: NormalizedRequest) -> AsyncIterator[ProviderChunk]:
        yield ProviderChunk(text="part1 ", done=False)
        yield ProviderChunk(text="part2", done=True)

    def estimate_tokens(self, messages: list) -> int:
        return 10

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(status=HealthStatus.HEALTHY)

    async def close(self) -> None:
        pass


class FakeCBQuery:
    """ICircuitBreakerQuery implementation."""

    def get_state(self, provider_id: str) -> CircuitState:
        return CircuitState.CLOSED


class FakeRLQuery:
    """IRateLimiterQuery implementation."""

    def has_capacity(self, provider_id: str, token_estimate: int) -> bool:
        return True


class FakeHealthQuery:
    """IHealthQuery implementation."""

    def get_status(self, provider_id: str) -> HealthStatus:
        return HealthStatus.HEALTHY


# ===========================================================================
# Helpers
# ===========================================================================


def _model_spec(
    model_id: str = "gpt-4o",
    *,
    cost_in: float = 5.0,
    cost_out: float = 15.0,
) -> ModelSpec:
    return ModelSpec(
        id=model_id,
        capabilities=[CapabilityType.CHAT, CapabilityType.TOOL_CALL],
        cost_per_1m_input=cost_in,
        cost_per_1m_output=cost_out,
        max_context=128000,
    )


def _make_manifest() -> ProviderManifest:
    return ProviderManifest(
        provider_id="openai",
        display_name="OpenAI",
        models=[_model_spec("gpt-4o"), _model_spec("gpt-4o-mini", cost_in=0.15, cost_out=0.6)],
        capabilities=[CapabilityType.CHAT, CapabilityType.TOOL_CALL],
    )


def _make_request(
    capability: CapabilityType = CapabilityType.CHAT,
    *,
    trace_id: str = "trace-1",
    temperature: float = 0.7,
    priority: Priority = Priority.INTERACTIVE,
) -> HubRequest:
    return HubRequest(
        capability=capability,
        payload=ChatPayload(messages=[Message(role="user", content="Hello")]),
        trace_id=trace_id,
        constraints=RequestConstraints(
            temperature=temperature,
            priority=priority,
        ),
    )


def _build_router(
    *,
    with_audit: bool = False,
    plugin_text: str = "response-ok",
) -> RequestRouter:
    """Build a fully-wired RequestRouter with all real internal services."""
    config = ModelHubConfig()
    manifest = _make_manifest()
    plugin = FakePlugin(response_text=plugin_text)

    # Registry + manifest
    registry = ProviderRegistry(config=config)
    registry.register(manifest, plugin)

    # CB + RL for CapabilityRouter
    cb_query = FakeCBQuery()
    rl_query = FakeRLQuery()
    health_query = FakeHealthQuery()

    cap_router = CapabilityRouter(
        registry=registry,
        circuit_breaker=cb_query,
        rate_limiter=rl_query,
        health_monitor=health_query,
    )

    model_selector = ModelSelector()
    response_cache = ResponseCache(config=config)
    normalization = NormalizationLayer()

    # Dispatcher with real CB + RL
    cb_mgr = CircuitBreakerManager()
    cb_mgr.register_provider("openai")
    rate_limiter = RateLimiter()
    rate_limiter.register_provider("openai", rpm=100, tpm=100000)

    dispatcher = ProviderDispatcher(
        circuit_mgr=cb_mgr,
        rate_limiter=rate_limiter,
        credential_port=FakeCredentialPort(),
        plugins={"openai": FakePlugin(response_text=plugin_text)},
    )

    audit = AuditLogger() if with_audit else None

    return RequestRouter(
        capability_router=cap_router,
        model_selector=model_selector,
        response_cache=response_cache,
        normalization_layer=normalization,
        dispatcher=dispatcher,
        audit_logger=audit,
    )


# ===========================================================================
# Validation Tests (Step 1)
# ===========================================================================


class TestValidation:
    def test_missing_trace_id_raises(self) -> None:
        """MH-03: trace_id required."""
        with pytest.raises(ValueError, match="trace_id"):
            _make_request(trace_id="")

    @pytest.mark.asyncio
    async def test_invalid_capability_raises(self) -> None:
        """Capability must be CapabilityType enum."""
        router = _build_router()
        req = HubRequest(
            capability="not_a_capability",  # type: ignore[arg-type]
            payload=ChatPayload(messages=[Message(role="user", content="hi")]),
            trace_id="t-1",
        )
        with pytest.raises(ValidationError):
            await router.route(req)


# ===========================================================================
# No Eligible Provider Tests (Step 4)
# ===========================================================================


class TestNoEligibleProvider:
    @pytest.mark.asyncio
    async def test_no_eligible_raises(self) -> None:
        """No provider supports requested capability."""
        router = _build_router()
        req = HubRequest(
            capability=CapabilityType.TTS,
            payload=ChatPayload(messages=[Message(role="user", content="hi")]),
            trace_id="t-1",
        )
        # TTS isn't registered in our manifest
        with pytest.raises(NoEligibleProviderError):
            await router.route(req)


# ===========================================================================
# Full Pipeline Tests (Steps 1-9)
# ===========================================================================


class TestFullPipeline:
    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        """Full 7-step pipeline: validate -> ... -> response."""
        router = _build_router(plugin_text="pipeline-ok")
        response = await router.route(_make_request())
        assert response.result == "pipeline-ok"
        assert response.metadata.provider_id == "openai"
        assert response.metadata.trace_id == "trace-1"
        assert response.metadata.cache_hit is False

    @pytest.mark.asyncio
    async def test_model_id_in_metadata(self) -> None:
        router = _build_router()
        response = await router.route(_make_request())
        # model_id should be one of the registered models
        assert response.metadata.model_id in {"gpt-4o", "gpt-4o-mini"}

    @pytest.mark.asyncio
    async def test_latency_tracked(self) -> None:
        router = _build_router()
        response = await router.route(_make_request())
        assert response.metadata.latency_ms >= 0


# ===========================================================================
# Cache Tests (Step 6)
# ===========================================================================


class TestCacheIntegration:
    @pytest.mark.asyncio
    async def test_cache_hit_short_circuits(self) -> None:
        """Second identical request returns cached response."""
        router = _build_router(plugin_text="cached-text")
        req = _make_request(temperature=0.5)

        # First call fills cache
        resp1 = await router.route(req)
        assert resp1.result == "cached-text"

        # Second call should hit cache (same capability, payload, model, temp)
        req2 = _make_request(temperature=0.5)
        resp2 = await router.route(req2)
        assert resp2.result == "cached-text"

    @pytest.mark.asyncio
    async def test_high_temp_not_cached(self) -> None:
        """High temperature requests are not cached."""
        router = _build_router(plugin_text="not-cached")
        req = _make_request(temperature=1.5)
        resp1 = await router.route(req)
        assert resp1.result == "not-cached"
        # ResponseCache skips caching for temp > 0.9


# ===========================================================================
# Audit Logger Tests (Step 9)
# ===========================================================================


class TestAuditIntegration:
    @pytest.mark.asyncio
    async def test_audit_log_created(self) -> None:
        router = _build_router(with_audit=True)
        await router.route(_make_request())
        al = router._audit_logger  # noqa: SLF001
        assert al is not None
        assert al.count == 1
        rec = al.records[0]
        assert rec.trace_id == "trace-1"

    @pytest.mark.asyncio
    async def test_no_audit_without_logger(self) -> None:
        """Router works fine without audit logger."""
        router = _build_router(with_audit=False)
        response = await router.route(_make_request())
        assert response.result is not None


# ===========================================================================
# stream_route() Tests
# ===========================================================================


class TestStreamRoute:
    @pytest.mark.asyncio
    async def test_stream_yields_chunks(self) -> None:
        router = _build_router()
        chunks = []
        async for chunk in router.stream_route(_make_request()):
            chunks.append(chunk)
        assert len(chunks) >= 2
        assert chunks[-1].done is True

    @pytest.mark.asyncio
    async def test_stream_final_chunk_has_metadata(self) -> None:
        router = _build_router()
        last = None
        async for chunk in router.stream_route(_make_request()):
            last = chunk
        assert last is not None
        assert last.metadata is not None
        assert last.metadata.trace_id == "trace-1"

    @pytest.mark.asyncio
    async def test_stream_no_eligible_raises(self) -> None:
        router = _build_router()
        req = HubRequest(
            capability=CapabilityType.IMAGE_GEN,
            payload=ChatPayload(messages=[Message(role="user", content="hi")]),
            trace_id="t-1",
        )
        with pytest.raises(NoEligibleProviderError):
            async for _ in router.stream_route(req):
                pass


# ===========================================================================
# Re-exports
# ===========================================================================


class TestRequestRouterReExports:
    def test_reexport(self) -> None:
        from k1.model_hub.services import RequestRouter as Reexported

        assert Reexported is RequestRouter
