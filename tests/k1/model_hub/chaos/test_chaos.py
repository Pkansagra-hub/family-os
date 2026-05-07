"""M9 Chaos Tests -- Resilience under failure [Epic 9.3.1].

Scenarios:
  1. Provider crash -> circuit breaker OPEN -> fallback
  2. All providers down -> ProviderError
  3. Budget exhaustion mid-request
  4. Rate limit overflow
  5. Plugin exception isolation
  6. Concurrent failures
  7. Circuit breaker recovery (half-open probe)
  8. Cascade failures across multiple providers

All services wired via ModelHubFactory.create_for_testing().
No unittest.mock imports.
"""

from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator

import pytest

from k1.model_hub.config import ModelHubConfig
from k1.model_hub.factory import ModelHubFactory
from k1.model_hub.manifest import (
    CircuitBreakerConfig,
    ModelSpec,
    PlacementConfig,
    ProviderManifest,
)
from k1.model_hub.plugins.base import (
    NormalizedRequest,
    ProviderChunk,
    ProviderHealth,
    ProviderResponse,
)
from k1.model_hub.services.circuit_breaker_manager import CircuitBreakerManager
from k1.model_hub.services.provider_registry import ProviderRegistry
from k1.model_hub.services.rate_limiter import RateLimiter
from k1.model_hub.types import (
    CapabilityType,
    ChatPayload,
    CircuitState,
    FinishReason,
    HealthStatus,
    HubRequest,
    Message,
    ModelTier,
    NoEligibleProviderError,
    PlacementType,
    ProviderError,
    RequestConstraints,
)

# ===========================================================================
# Chaos Plugins
# ===========================================================================


class _OkPlugin:
    """Always-succeeding plugin."""

    def __init__(self, text: str = "ok") -> None:
        self._text = text
        self._calls = 0

    async def initialize(self, manifest: object) -> None:
        pass

    def supports(self, capability: CapabilityType) -> bool:
        return True

    async def execute(self, request: NormalizedRequest) -> ProviderResponse:
        self._calls += 1
        return ProviderResponse(
            text=self._text,
            prompt_tokens=10,
            completion_tokens=5,
            model_id=request.model_id or "test-model",
            finish_reason=FinishReason.STOP,
        )

    async def stream_execute(self, request: NormalizedRequest) -> AsyncIterator[ProviderChunk]:
        yield ProviderChunk(text=self._text, done=True)
        return  # noqa: B901

    def estimate_tokens(self, messages: list) -> int:
        return 10

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(status=HealthStatus.HEALTHY)

    async def close(self) -> None:
        pass

    @property
    def call_count(self) -> int:
        return self._calls


class _CrashPlugin:
    """Plugin that always throws RuntimeError."""

    def __init__(self, error_msg: str = "CRASH") -> None:
        self._error_msg = error_msg

    async def initialize(self, manifest: object) -> None:
        pass

    def supports(self, capability: CapabilityType) -> bool:
        return True

    async def execute(self, request: NormalizedRequest) -> ProviderResponse:
        raise RuntimeError(self._error_msg)

    async def stream_execute(self, request: NormalizedRequest) -> AsyncIterator[ProviderChunk]:
        raise RuntimeError(self._error_msg)
        yield  # type: ignore[misc]  # noqa: B901

    def estimate_tokens(self, messages: list) -> int:
        return 10

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(status=HealthStatus.UNHEALTHY)

    async def close(self) -> None:
        pass


class _IntermittentPlugin:
    """Plugin that fails every N-th call."""

    def __init__(self, fail_every: int = 2) -> None:
        self._fail_every = fail_every
        self._calls = 0

    async def initialize(self, manifest: object) -> None:
        pass

    def supports(self, capability: CapabilityType) -> bool:
        return True

    async def execute(self, request: NormalizedRequest) -> ProviderResponse:
        self._calls += 1
        if self._calls % self._fail_every == 0:
            raise RuntimeError(f"Intermittent failure on call {self._calls}")
        return ProviderResponse(
            text="intermittent-ok",
            prompt_tokens=10,
            completion_tokens=5,
            model_id=request.model_id or "test-model",
            finish_reason=FinishReason.STOP,
        )

    async def stream_execute(self, request: NormalizedRequest) -> AsyncIterator[ProviderChunk]:
        self._calls += 1
        if self._calls % self._fail_every == 0:
            raise RuntimeError("Intermittent stream failure")
        yield ProviderChunk(text="ok", done=True)
        return  # noqa: B901

    def estimate_tokens(self, messages: list) -> int:
        return 10

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(status=HealthStatus.HEALTHY)

    async def close(self) -> None:
        pass


class _SlowCrashPlugin:
    """Plugin that takes a long time then crashes."""

    def __init__(self, delay_s: float = 0.1) -> None:
        self._delay = delay_s

    async def initialize(self, manifest: object) -> None:
        pass

    def supports(self, capability: CapabilityType) -> bool:
        return True

    async def execute(self, request: NormalizedRequest) -> ProviderResponse:
        await asyncio.sleep(self._delay)
        raise RuntimeError("Slow crash")

    async def stream_execute(self, request: NormalizedRequest) -> AsyncIterator[ProviderChunk]:
        await asyncio.sleep(self._delay)
        raise RuntimeError("Slow stream crash")
        yield  # type: ignore[misc]  # noqa: B901

    def estimate_tokens(self, messages: list) -> int:
        return 10

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(status=HealthStatus.UNHEALTHY)

    async def close(self) -> None:
        pass


# ===========================================================================
# Helpers
# ===========================================================================


def _make_manifest(
    provider_id: str,
    circuit_breaker: CircuitBreakerConfig | None = None,
    model_id: str | None = None,
) -> ProviderManifest:
    caps = [CapabilityType.CHAT, CapabilityType.TOOL_CALL]
    return ProviderManifest(
        provider_id=provider_id,
        display_name=f"Chaos {provider_id}",
        capabilities=caps,
        models=[
            ModelSpec(
                id=model_id or f"model-{provider_id}",
                capabilities=caps,
                cost_per_1m_input=5.0,
                cost_per_1m_output=15.0,
                max_context=128000,
                tier=ModelTier.STANDARD,
            ),
        ],
        placement=PlacementConfig(type=PlacementType.REMOTE),
        circuit_breaker=circuit_breaker,
    )


def _make_request(
    trace_id: str = "chaos-1",
    content: str = "chaos test",
) -> HubRequest:
    return HubRequest(
        capability=CapabilityType.CHAT,
        payload=ChatPayload(messages=[Message(role="user", content=content)]),
        constraints=RequestConstraints(consumer_id="chaos-test"),
        trace_id=trace_id,
    )


def _wire(
    plugins: dict,
    config: ModelHubConfig | None = None,
    manifests: list[ProviderManifest] | None = None,
    cb_config: CircuitBreakerConfig | None = None,
):
    """Wire hub for chaos testing."""
    facade, adapters = ModelHubFactory.create_for_testing(
        overrides={
            "config": config or ModelHubConfig(),
            "plugins": plugins,
        }
    )
    registry: ProviderRegistry = adapters["registry"]
    circuit_mgr: CircuitBreakerManager = adapters["circuit_mgr"]
    rate_limiter: RateLimiter = adapters["rate_limiter"]

    default_manifests = [_make_manifest(pid, circuit_breaker=cb_config) for pid in plugins]
    for m in manifests or default_manifests:
        registry.register(m, plugins[m.provider_id])
        circuit_mgr.register_provider(m.provider_id, m.circuit_breaker)
        rate_limiter.register_provider(m.provider_id, rpm=600, tpm=1_000_000)

    return facade, adapters


# ===========================================================================
# 1. Provider crash -> circuit breaker OPEN -> fallback
# ===========================================================================


class TestProviderCrashFallback:
    """Provider crash triggers circuit breaker then fallback."""

    async def test_crash_opens_circuit(self) -> None:
        """Crashing provider opens its circuit breaker."""
        cb = CircuitBreakerConfig(failure_threshold=2, failure_window_s=60.0, cooldown_s=30.0)
        facade, adapters = _wire({"crash": _CrashPlugin()}, cb_config=cb)
        circuit_mgr: CircuitBreakerManager = adapters["circuit_mgr"]

        for i in range(3):
            try:
                await facade.execute(_make_request(trace_id=f"crash-{i}", content=f"c-{i}"))
            except (ProviderError, NoEligibleProviderError):
                pass

        assert circuit_mgr.get_state("crash") == CircuitState.OPEN

    async def test_fallback_after_crash(self) -> None:
        """When primary crashes, hub falls back to secondary."""
        plugins = {
            "primary": _CrashPlugin(),
            "backup": _OkPlugin(text="backup-response"),
        }
        facade, _ = _wire(plugins)
        resp = await facade.execute(_make_request())
        assert resp.result is not None

    async def test_crash_does_not_affect_other_providers(self) -> None:
        """One provider crash does not contaminate another (MH-17)."""
        plugins = {
            "bad": _CrashPlugin(),
            "good": _OkPlugin(text="still-working"),
        }
        facade, adapters = _wire(plugins)
        circuit_mgr: CircuitBreakerManager = adapters["circuit_mgr"]

        # Make requests -- should succeed via "good" provider
        for i in range(5):
            resp = await facade.execute(_make_request(trace_id=f"isolate-{i}", content=f"i-{i}"))
            assert resp.result is not None

        # "bad" circuit should be open, "good" should be closed
        assert circuit_mgr.get_state("good") == CircuitState.CLOSED


# ===========================================================================
# 2. All providers down
# ===========================================================================


class TestAllProvidersDown:
    """Hub behavior when all providers are unavailable."""

    async def test_single_provider_down(self) -> None:
        """Single crashing provider raises ProviderError."""
        facade, _ = _wire({"crash": _CrashPlugin()})
        with pytest.raises((ProviderError, NoEligibleProviderError)):
            await facade.execute(_make_request())

    async def test_all_providers_down_raises(self) -> None:
        """All providers crashing raises ProviderError."""
        plugins = {
            "a": _CrashPlugin("crash-a"),
            "b": _CrashPlugin("crash-b"),
        }
        facade, _ = _wire(plugins)
        with pytest.raises((ProviderError, NoEligibleProviderError)):
            await facade.execute(_make_request())

    async def test_slow_crash_all_down(self) -> None:
        """Slow-crashing providers still result in error."""
        facade, _ = _wire({"slow": _SlowCrashPlugin(delay_s=0.01)})
        with pytest.raises((ProviderError, NoEligibleProviderError)):
            await facade.execute(_make_request())


# ===========================================================================
# 3. Budget exhaustion mid-request
# ===========================================================================


# RIP-OUT: BudgetEnforcer deleted (family-os).


# ===========================================================================
# 4. Rate limit overflow
# ===========================================================================


class TestRateLimitOverflow:
    """Rate limiting under high load."""

    async def test_rate_limit_blocks_requests(self) -> None:
        """Exhausting rate limit blocks further requests."""
        facade, adapters = _wire({"ok": _OkPlugin()})
        rate_limiter: RateLimiter = adapters["rate_limiter"]

        # Drain the RPM bucket
        for _ in range(700):
            rate_limiter.acquire("ok", token_estimate=1)

        # Rate limiter should be exhausted
        decision = rate_limiter.acquire("ok", token_estimate=1)
        assert not decision.allowed

    async def test_rate_limit_has_retry_after(self) -> None:
        """Rate-limited response includes retry_after_s."""
        _, adapters = _wire({"ok": _OkPlugin()})
        rate_limiter: RateLimiter = adapters["rate_limiter"]

        # Drain bucket
        for _ in range(700):
            rate_limiter.acquire("ok", token_estimate=1)

        decision = rate_limiter.acquire("ok", token_estimate=1)
        assert decision.retry_after_s > 0


# ===========================================================================
# 5. Plugin exception isolation (MH-17)
# ===========================================================================


class TestPluginIsolation:
    """One plugin crash doesn't affect the hub or other plugins."""

    async def test_exception_caught_in_dispatch(self) -> None:
        """Plugin exception is caught; hub doesn't crash."""
        plugins = {
            "crash": _CrashPlugin(),
            "good": _OkPlugin(),
        }
        facade, _ = _wire(plugins)
        # Should succeed via "good" provider
        resp = await facade.execute(_make_request())
        assert resp.result is not None

    async def test_intermittent_failures_recoverable(self) -> None:
        """Intermittent plugin failures are retried/tolerated."""
        plugins = {
            "flaky": _IntermittentPlugin(fail_every=3),
            "stable": _OkPlugin(),
        }
        facade, _ = _wire(plugins)

        for i in range(10):
            resp = await facade.execute(_make_request(trace_id=f"flaky-{i}", content=f"flaky-{i}"))
            assert resp.result is not None

    async def test_slow_crash_doesnt_block_forever(self) -> None:
        """Slow-crashing plugin doesn't block hub indefinitely."""
        plugins = {
            "slow": _SlowCrashPlugin(delay_s=0.01),
            "fast": _OkPlugin(),
        }
        facade, _ = _wire(plugins)

        start = time.monotonic()
        resp = await facade.execute(_make_request())
        elapsed = time.monotonic() - start

        assert resp.result is not None
        assert elapsed < 2.0  # Should not block for long


# ===========================================================================
# 6. Concurrent failures
# ===========================================================================


class TestConcurrentFailures:
    """Hub resilience under concurrent chaotic requests."""

    async def test_concurrent_mixed_success_failure(self) -> None:
        """Mix of crashing and working providers handles concurrent requests."""
        plugins = {
            "crash": _CrashPlugin(),
            "ok": _OkPlugin(),
        }
        facade, _ = _wire(plugins)

        async def send(i: int):
            try:
                resp = await facade.execute(
                    _make_request(trace_id=f"conc-{i}", content=f"conc-{i}")
                )
                return resp.result is not None
            except (ProviderError, NoEligibleProviderError):
                return False

        results = await asyncio.gather(*[send(i) for i in range(10)])
        # At least some should succeed (via "ok" provider)
        assert any(results)


# ===========================================================================
# 7. Circuit breaker recovery
# ===========================================================================


class TestCircuitBreakerRecovery:
    """Circuit breaker half-open probe and recovery."""

    async def test_circuit_opens_and_blocks(self) -> None:
        """After failures, circuit opens and blocks requests."""
        cb = CircuitBreakerConfig(failure_threshold=2, failure_window_s=60.0, cooldown_s=0.1)
        facade, adapters = _wire({"crash": _CrashPlugin()}, cb_config=cb)
        circuit_mgr: CircuitBreakerManager = adapters["circuit_mgr"]

        for i in range(3):
            try:
                await facade.execute(_make_request(trace_id=f"open-{i}", content=f"o-{i}"))
            except (ProviderError, NoEligibleProviderError):
                pass

        assert circuit_mgr.get_state("crash") == CircuitState.OPEN

    async def test_half_open_after_cooldown(self) -> None:
        """Circuit transitions to HALF_OPEN after cooldown."""
        cb = CircuitBreakerConfig(failure_threshold=2, failure_window_s=60.0, cooldown_s=0.05)
        _, adapters = _wire({"test": _CrashPlugin()}, cb_config=cb)
        circuit_mgr: CircuitBreakerManager = adapters["circuit_mgr"]

        # Force failures to open circuit
        for _ in range(3):
            circuit_mgr.record_failure("test", "crash")

        assert circuit_mgr.get_state("test") == CircuitState.OPEN

        # Wait for cooldown
        await asyncio.sleep(0.1)

        # Should transition to HALF_OPEN on next acquire
        state = circuit_mgr.acquire("test")
        assert state in (CircuitState.HALF_OPEN, CircuitState.CLOSED)

    async def test_circuit_closes_on_success(self) -> None:
        """Circuit closes when half-open probe succeeds."""
        cb = CircuitBreakerConfig(failure_threshold=2, failure_window_s=60.0, cooldown_s=0.05)
        _, adapters = _wire({"test": _OkPlugin()}, cb_config=cb)
        circuit_mgr: CircuitBreakerManager = adapters["circuit_mgr"]

        # Force open
        for _ in range(3):
            circuit_mgr.record_failure("test", "temporary")

        assert circuit_mgr.get_state("test") == CircuitState.OPEN

        # Wait for cooldown
        await asyncio.sleep(0.1)

        # Probe should succeed, closing circuit
        circuit_mgr.acquire("test")  # Transitions to HALF_OPEN
        circuit_mgr.record_success("test")

        assert circuit_mgr.get_state("test") == CircuitState.CLOSED


# ===========================================================================
# 8. Cascade failures
# ===========================================================================


class TestCascadeFailures:
    """Multiple providers failing in sequence."""

    async def test_cascade_through_all_providers(self) -> None:
        """Failures cascade through fallback chain."""
        plugins = {
            "p1": _CrashPlugin("p1-down"),
            "p2": _CrashPlugin("p2-down"),
            "p3": _OkPlugin(text="p3-saved-it"),
        }
        facade, _ = _wire(plugins)

        resp = await facade.execute(_make_request())
        assert resp.result is not None

    async def test_all_cascade_fails(self) -> None:
        """When all providers in cascade fail, error raised."""
        plugins = {
            "p1": _CrashPlugin("p1"),
            "p2": _CrashPlugin("p2"),
            "p3": _CrashPlugin("p3"),
        }
        facade, _ = _wire(plugins)

        with pytest.raises((ProviderError, NoEligibleProviderError)):
            await facade.execute(_make_request())

    async def test_partial_cascade_with_intermittent(self) -> None:
        """Intermittent failures handled within cascade."""
        plugins = {
            "flaky": _IntermittentPlugin(fail_every=2),
            "backup": _OkPlugin(text="backup"),
        }
        facade, _ = _wire(plugins)

        successes = 0
        for i in range(10):
            resp = await facade.execute(
                _make_request(trace_id=f"cascade-{i}", content=f"cascade-{i}")
            )
            if resp.result is not None:
                successes += 1

        assert successes == 10  # All should succeed via fallback
