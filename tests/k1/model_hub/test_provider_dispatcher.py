"""M5 Request Pipeline -- Test ProviderDispatcher [F44].

Tests dispatch pipeline with circuit breaker, rate limiter, credential
fetch, plugin execution, fallback chain, and plugin isolation (MH-17).

Covers:
  - DispatchResult: construction, frozen
  - dispatch(): happy path, CB rejection, rate limit rejection, plugin error
  - Fallback chain: primary fail -> fallback success
  - Plugin isolation (MH-17): plugin crash doesn't crash hub
  - Retry: 1 retry on failure
  - stream(): happy path, fallback
  - Re-exports from services/__init__.py
"""

from __future__ import annotations

from typing import AsyncIterator

import pytest

from k1.model_hub.plugins.base import (
    NormalizedRequest,
    ProviderChunk,
    ProviderHealth,
    ProviderResponse,
)
from k1.model_hub.services.circuit_breaker_manager import CircuitBreakerManager
from k1.model_hub.services.provider_dispatcher import DispatchResult, ProviderDispatcher
from k1.model_hub.services.rate_limiter import RateLimiter
from k1.model_hub.types import CapabilityType, FinishReason, HealthStatus, Message, ProviderError

# ===========================================================================
# Fake collaborators (no unittest.mock)
# ===========================================================================


class FakeCredentialPort:
    """Fake ICredentialPort for testing."""

    def __init__(self, keys: dict[str, str] | None = None) -> None:
        self._keys = keys or {"openai": "sk-test", "anthropic": "sk-ant-test"}

    async def get_key(self, provider_id: str) -> str:
        return self._keys.get(provider_id, "")

    async def refresh_key(self, provider_id: str) -> str:
        return self._keys.get(provider_id, "")


class FakePlugin:
    """Fake IProviderPlugin for deterministic testing."""

    def __init__(
        self,
        *,
        response_text: str = "hello",
        fail_count: int = 0,
        stream_chunks: list[str] | None = None,
    ) -> None:
        self._response_text = response_text
        self._fail_count = fail_count
        self._call_count = 0
        self._stream_chunks = stream_chunks or ["chunk1", "chunk2"]
        self._calls: list[NormalizedRequest] = []

    async def initialize(self, manifest: object) -> None:
        pass

    def supports(self, capability: CapabilityType) -> bool:
        return True

    async def execute(self, request: NormalizedRequest) -> ProviderResponse:
        self._call_count += 1
        self._calls.append(request)
        if self._call_count <= self._fail_count:
            raise RuntimeError(f"Fake failure #{self._call_count}")
        return ProviderResponse(
            text=self._response_text,
            prompt_tokens=10,
            completion_tokens=5,
            model_id=request.model_id or "gpt-4o",
            finish_reason=FinishReason.STOP,
        )

    async def stream_execute(self, request: NormalizedRequest) -> AsyncIterator[ProviderChunk]:
        self._call_count += 1
        if self._call_count <= self._fail_count:
            raise RuntimeError(f"Fake stream failure #{self._call_count}")
        for i, text in enumerate(self._stream_chunks):
            is_last = i == len(self._stream_chunks) - 1
            yield ProviderChunk(text=text, done=is_last)

    def estimate_tokens(self, messages: list) -> int:
        return 10

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(status=HealthStatus.HEALTHY)

    @property
    def calls(self) -> list[NormalizedRequest]:
        return list(self._calls)


class FailingPlugin(FakePlugin):
    """Plugin that always fails (MH-17 isolation test)."""

    async def execute(self, request: NormalizedRequest) -> ProviderResponse:
        raise RuntimeError("Plugin crash!")

    async def stream_execute(self, request: NormalizedRequest) -> AsyncIterator[ProviderChunk]:
        raise RuntimeError("Stream crash!")
        yield  # type: ignore[misc]  # Make it an async generator


# ===========================================================================
# Fixtures
# ===========================================================================


def _make_request(model_id: str = "gpt-4o") -> NormalizedRequest:
    return NormalizedRequest(
        capability=CapabilityType.CHAT,
        messages=[Message(role="user", content="hi")],
        model_id=model_id,
        trace_id="t-1",
    )


@pytest.fixture
def cb() -> CircuitBreakerManager:
    cbm = CircuitBreakerManager()
    cbm.register_provider("openai")
    cbm.register_provider("anthropic")
    return cbm


@pytest.fixture
def rl() -> RateLimiter:
    limiter = RateLimiter()
    limiter.register_provider("openai", rpm=100, tpm=100000, headroom_pct=1.0)
    limiter.register_provider("anthropic", rpm=100, tpm=100000, headroom_pct=1.0)
    return limiter


@pytest.fixture
def dispatcher(cb: CircuitBreakerManager, rl: RateLimiter) -> ProviderDispatcher:
    return ProviderDispatcher(
        circuit_mgr=cb,
        rate_limiter=rl,
        credential_port=FakeCredentialPort(),
        plugins={
            "openai": FakePlugin(response_text="openai-reply"),
            "anthropic": FakePlugin(response_text="anthropic-reply"),
        },
    )


# ===========================================================================
# DispatchResult Tests
# ===========================================================================


class TestDispatchResult:
    def test_construction(self) -> None:
        r = DispatchResult(
            response=ProviderResponse(text="hi"),
            provider_id="openai",
            latency_ms=100,
        )
        assert r.provider_id == "openai"
        assert r.fallback_used is False
        assert r.attempts == []

    def test_frozen(self) -> None:
        r = DispatchResult(
            response=ProviderResponse(text="hi"),
            provider_id="openai",
            latency_ms=100,
        )
        with pytest.raises(AttributeError):
            r.provider_id = "x"  # type: ignore[misc]


# ===========================================================================
# dispatch() Tests
# ===========================================================================


class TestDispatch:
    @pytest.mark.asyncio
    async def test_happy_path(self, dispatcher: ProviderDispatcher) -> None:
        result = await dispatcher.dispatch(_make_request(), "openai")
        assert result.response.text == "openai-reply"
        assert result.provider_id == "openai"
        assert result.latency_ms >= 0
        assert result.fallback_used is False

    @pytest.mark.asyncio
    async def test_unknown_plugin_raises(self, cb: CircuitBreakerManager, rl: RateLimiter) -> None:
        d = ProviderDispatcher(
            circuit_mgr=cb,
            rate_limiter=rl,
            credential_port=FakeCredentialPort(),
            plugins={},
        )
        with pytest.raises(ProviderError):
            await d.dispatch(_make_request(), "unknown")

    @pytest.mark.asyncio
    async def test_circuit_open_skips_provider(
        self, dispatcher: ProviderDispatcher, cb: CircuitBreakerManager
    ) -> None:
        """If primary is circuit-broken, falls back."""
        # Open circuit for openai
        for _ in range(3):
            cb.record_failure("openai")
        result = await dispatcher.dispatch(_make_request(), "openai", fallback_chain=["anthropic"])
        assert result.provider_id == "anthropic"
        assert result.fallback_used is True

    @pytest.mark.asyncio
    async def test_rate_limit_skips_provider(self, cb: CircuitBreakerManager) -> None:
        """If primary is rate-limited, falls back."""
        rl = RateLimiter()
        rl.register_provider("openai", rpm=1, tpm=1, headroom_pct=1.0)
        rl.register_provider("anthropic", rpm=100, tpm=100000, headroom_pct=1.0)
        # Exhaust openai
        rl.acquire("openai", 1)

        d = ProviderDispatcher(
            circuit_mgr=cb,
            rate_limiter=rl,
            credential_port=FakeCredentialPort(),
            plugins={
                "openai": FakePlugin(response_text="openai"),
                "anthropic": FakePlugin(response_text="anthropic"),
            },
        )
        result = await d.dispatch(_make_request(), "openai", fallback_chain=["anthropic"])
        assert result.provider_id == "anthropic"

    @pytest.mark.asyncio
    async def test_attempts_tracked(self, dispatcher: ProviderDispatcher) -> None:
        result = await dispatcher.dispatch(_make_request(), "openai")
        assert "openai" in result.attempts


# ===========================================================================
# Fallback Tests (MH-06)
# ===========================================================================


class TestFallback:
    @pytest.mark.asyncio
    async def test_fallback_on_plugin_failure(
        self, cb: CircuitBreakerManager, rl: RateLimiter
    ) -> None:
        """Plugin crash -> fallback to next provider."""
        d = ProviderDispatcher(
            circuit_mgr=cb,
            rate_limiter=rl,
            credential_port=FakeCredentialPort(),
            plugins={
                "openai": FailingPlugin(),
                "anthropic": FakePlugin(response_text="fallback-ok"),
            },
        )
        result = await d.dispatch(_make_request(), "openai", fallback_chain=["anthropic"])
        assert result.provider_id == "anthropic"
        assert result.fallback_used is True

    @pytest.mark.asyncio
    async def test_all_providers_fail_raises(
        self, cb: CircuitBreakerManager, rl: RateLimiter
    ) -> None:
        d = ProviderDispatcher(
            circuit_mgr=cb,
            rate_limiter=rl,
            credential_port=FakeCredentialPort(),
            plugins={
                "openai": FailingPlugin(),
                "anthropic": FailingPlugin(),
            },
        )
        with pytest.raises(ProviderError):
            await d.dispatch(_make_request(), "openai", fallback_chain=["anthropic"])


# ===========================================================================
# Plugin Isolation Tests (MH-17)
# ===========================================================================


class TestPluginIsolation:
    @pytest.mark.asyncio
    async def test_plugin_crash_does_not_crash_hub(
        self, cb: CircuitBreakerManager, rl: RateLimiter
    ) -> None:
        """MH-17: One plugin crash doesn't affect others."""
        d = ProviderDispatcher(
            circuit_mgr=cb,
            rate_limiter=rl,
            credential_port=FakeCredentialPort(),
            plugins={
                "openai": FailingPlugin(),
                "anthropic": FakePlugin(response_text="ok"),
            },
        )
        result = await d.dispatch(_make_request(), "openai", fallback_chain=["anthropic"])
        assert result.response.text == "ok"


# ===========================================================================
# Retry Tests
# ===========================================================================


class TestRetry:
    @pytest.mark.asyncio
    async def test_retry_once_on_failure(self, cb: CircuitBreakerManager, rl: RateLimiter) -> None:
        """Plugin fails once, succeeds on retry."""
        plugin = FakePlugin(response_text="retried-ok", fail_count=1)
        d = ProviderDispatcher(
            circuit_mgr=cb,
            rate_limiter=rl,
            credential_port=FakeCredentialPort(),
            plugins={"openai": plugin},
        )
        result = await d.dispatch(_make_request(), "openai")
        assert result.response.text == "retried-ok"


# ===========================================================================
# stream() Tests
# ===========================================================================


class TestStream:
    @pytest.mark.asyncio
    async def test_stream_happy_path(self, dispatcher: ProviderDispatcher) -> None:
        chunks = []
        async for chunk in dispatcher.stream(_make_request(), "openai"):
            chunks.append(chunk)
        assert len(chunks) == 2
        assert chunks[-1].done is True

    @pytest.mark.asyncio
    async def test_stream_fallback(self, cb: CircuitBreakerManager, rl: RateLimiter) -> None:
        d = ProviderDispatcher(
            circuit_mgr=cb,
            rate_limiter=rl,
            credential_port=FakeCredentialPort(),
            plugins={
                "openai": FailingPlugin(),
                "anthropic": FakePlugin(stream_chunks=["fb1", "fb2"]),
            },
        )
        chunks = []
        async for chunk in d.stream(_make_request(), "openai", fallback_chain=["anthropic"]):
            chunks.append(chunk)
        assert len(chunks) == 2
        assert chunks[0].text == "fb1"


# ===========================================================================
# register_plugin Tests
# ===========================================================================


class TestRegisterPlugin:
    def test_register_and_has(self, dispatcher: ProviderDispatcher) -> None:
        assert dispatcher.has_plugin("openai")
        assert not dispatcher.has_plugin("google")

    def test_register_new_plugin(self, dispatcher: ProviderDispatcher) -> None:
        dispatcher.register_plugin("google", FakePlugin())
        assert dispatcher.has_plugin("google")


# ===========================================================================
# Re-exports
# ===========================================================================


class TestProviderDispatcherReExports:
    def test_dispatcher_reexport(self) -> None:
        from k1.model_hub.services import ProviderDispatcher as Reexported

        assert Reexported is ProviderDispatcher

    def test_dispatch_result_reexport(self) -> None:
        from k1.model_hub.services import DispatchResult as Reexported

        assert Reexported is DispatchResult
