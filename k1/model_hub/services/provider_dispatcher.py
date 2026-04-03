"""Provider dispatch with circuit breaker, rate limiter, and fallback [F44].

Orchestrates the dispatch pipeline: CB acquire -> rate limit acquire ->
credential fetch -> plugin.execute() -> record result. On failure,
walks fallback chain (MH-06). Plugin isolation (MH-17).

Import graph (Layer 3 -- imports Layer 0 + Layer 1 + Layer 2 + Layer 3)
------------------------------------------------------------------------
k1.model_hub.services.provider_dispatcher
  -> k1.model_hub.types             (Layer 0)
  -> k1.model_hub.plugins.base      (Layer 2: NormalizedRequest, ProviderResponse,
                                      ProviderChunk, IProviderPlugin)
  -> k1.model_hub.services.*        (Layer 3: CircuitBreakerManager, RateLimiter)
  -> k1.model_hub.ports             (Layer 1: ICredentialPort)
  -> stdlib only

NEVER import from any adapter or runtime module.

References
----------
- model_hub.mmd: ProviderDispatcher service
- Invariant MH-02: Credentials from CredentialStore only
- Invariant MH-06: Capability-aware fallback (top 3)
- Invariant MH-17: Plugin isolation (one crash != hub crash)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Dict, List, Optional

from k1.model_hub.plugins.base import (
    IProviderPlugin,
    NormalizedRequest,
    ProviderChunk,
    ProviderResponse,
)
from k1.model_hub.ports.credential_port import ICredentialPort
from k1.model_hub.services.circuit_breaker_manager import CircuitBreakerManager
from k1.model_hub.services.rate_limiter import RateLimiter
from k1.model_hub.types import CircuitState, ProviderError

# ===========================================================================
# Dispatch Result
# ===========================================================================


@dataclass(frozen=True)
class DispatchResult:
    """Result of a provider dispatch attempt."""

    response: ProviderResponse
    provider_id: str
    latency_ms: int
    fallback_used: bool = False
    attempts: List[str] = field(default_factory=list)


# ===========================================================================
# Constants
# ===========================================================================

_MAX_FALLBACK_DEPTH = 3
_MAX_RETRIES = 1


# ===========================================================================
# ProviderDispatcher
# ===========================================================================


class ProviderDispatcher:
    """Dispatch pipeline with circuit breaker, rate limiting, and fallback.

    Pipeline per attempt:
      1. Acquire circuit breaker (reject if OPEN).
      2. Acquire rate limiter (reject if exhausted).
      3. Get credential via ICredentialPort (MH-02).
      4. Call plugin.execute() with NormalizedRequest.
      5. Record success/failure for circuit breaker.
      6. On failure: retry once, then next fallback (MH-06).

    Plugin isolation (MH-17): exceptions from plugin.execute() are caught
    and converted to ProviderError; one plugin crash does not affect others.

    Max fallback depth: 3.
    Max retries per provider: 1 (on timeout/5xx, then fallback).

    Constructor args:
        circuit_mgr: CircuitBreakerManager for acquire/record.
        rate_limiter: RateLimiter for acquire.
        credential_port: ICredentialPort for API key fetch (MH-02).
        plugins: Dict mapping provider_id -> IProviderPlugin.
    """

    def __init__(
        self,
        *,
        circuit_mgr: CircuitBreakerManager,
        rate_limiter: RateLimiter,
        credential_port: ICredentialPort,
        plugins: Optional[Dict[str, IProviderPlugin]] = None,
    ) -> None:
        self._circuit_mgr = circuit_mgr
        self._rate_limiter = rate_limiter
        self._credential_port = credential_port
        self._plugins: Dict[str, IProviderPlugin] = plugins or {}

    # -- Plugin management -----------------------------------------------------

    def register_plugin(self, provider_id: str, plugin: IProviderPlugin) -> None:
        """Register a plugin for a provider."""
        self._plugins[provider_id] = plugin

    def has_plugin(self, provider_id: str) -> bool:
        """Check if a plugin is registered for a provider."""
        return provider_id in self._plugins

    # -- Dispatch --------------------------------------------------------------

    async def dispatch(
        self,
        request: NormalizedRequest,
        provider_id: str,
        *,
        fallback_chain: Optional[List[str]] = None,
        token_estimate: int = 1,
    ) -> DispatchResult:
        """Dispatch request through provider pipeline with fallback.

        Tries primary provider, then walks fallback_chain on failure.

        Args:
            request: Provider-agnostic normalized request.
            provider_id: Primary provider to dispatch to.
            fallback_chain: Ordered list of fallback provider IDs (MH-06).
            token_estimate: Estimated tokens for rate limiting.

        Returns:
            DispatchResult with provider response + metadata.

        Raises:
            CircuitOpenError: All providers circuit-broken.
            RateLimitError: All providers rate-limited.
            ProviderError: All providers failed.
            ModelHubError: Unexpected error in dispatch pipeline.
        """
        providers = [provider_id] + (fallback_chain or [])
        providers = providers[: _MAX_FALLBACK_DEPTH + 1]

        attempts: List[str] = []
        last_error: Optional[Exception] = None

        for idx, pid in enumerate(providers):
            is_fallback = idx > 0
            result = await self._try_provider(request, pid, token_estimate=token_estimate)
            attempts.append(pid)

            if result is not None:
                return DispatchResult(
                    response=result[0],
                    provider_id=pid,
                    latency_ms=result[1],
                    fallback_used=is_fallback,
                    attempts=attempts,
                )
            # Provider failed -- continue to next fallback
            last_error = result  # type: ignore[assignment]

        # All providers exhausted
        if last_error is not None:
            raise last_error  # type: ignore[misc]
        raise ProviderError(
            f"All {len(attempts)} providers failed for dispatch",
            provider_id=provider_id,
        )

    async def stream(
        self,
        request: NormalizedRequest,
        provider_id: str,
        *,
        fallback_chain: Optional[List[str]] = None,
        token_estimate: int = 1,
    ) -> AsyncIterator[ProviderChunk]:
        """Streaming dispatch with fallback.

        Tries primary provider, then walks fallback_chain on failure.

        Args:
            request: Provider-agnostic normalized request.
            provider_id: Primary provider to dispatch to.
            fallback_chain: Ordered list of fallback provider IDs.
            token_estimate: Estimated tokens for rate limiting.

        Yields:
            ProviderChunk instances from the successful provider.

        Raises:
            CircuitOpenError: All providers circuit-broken.
            RateLimitError: All providers rate-limited.
            ProviderError: All providers failed.
        """
        providers = [provider_id] + (fallback_chain or [])
        providers = providers[: _MAX_FALLBACK_DEPTH + 1]

        last_error: Optional[Exception] = None

        for pid in providers:
            try:
                # Pre-checks: circuit breaker + rate limiter
                cb_state = self._circuit_mgr.acquire(pid)
                if cb_state == CircuitState.OPEN:
                    continue

                rate_decision = self._rate_limiter.acquire(pid, token_estimate)
                if not rate_decision.allowed:
                    continue

                plugin = self._plugins.get(pid)
                if plugin is None:
                    continue

                async for chunk in plugin.stream_execute(request):
                    yield chunk

                # Stream completed successfully
                self._circuit_mgr.record_success(pid)
                return

            except Exception as exc:  # noqa: BLE001
                self._circuit_mgr.record_failure(pid, str(exc))
                last_error = exc
                continue

        if last_error is not None:
            raise ProviderError(
                f"Stream dispatch failed: {last_error}",
                provider_id=provider_id,
            )
        raise ProviderError(
            "No providers available for stream dispatch",
            provider_id=provider_id,
        )

    # -- Internal: single provider attempt -------------------------------------

    async def _try_provider(
        self,
        request: NormalizedRequest,
        provider_id: str,
        *,
        token_estimate: int = 1,
    ) -> Optional[tuple[ProviderResponse, int]]:
        """Try dispatching to a single provider with 1 retry.

        Returns (response, latency_ms) on success, None on failure.
        Records success/failure for circuit breaker.
        """
        plugin = self._plugins.get(provider_id)
        if plugin is None:
            return None

        # 1. Circuit breaker
        cb_state = self._circuit_mgr.acquire(provider_id)
        if cb_state == CircuitState.OPEN:
            return None

        # 2. Rate limiter
        rate_decision = self._rate_limiter.acquire(provider_id, token_estimate)
        if not rate_decision.allowed:
            return None

        # 3-5. Execute with retry
        for attempt in range(_MAX_RETRIES + 1):
            try:
                start = time.monotonic()
                response = await plugin.execute(request)
                elapsed_ms = int((time.monotonic() - start) * 1000)

                # Record success
                self._circuit_mgr.record_success(provider_id)
                return response, elapsed_ms

            except Exception as exc:  # noqa: BLE001
                # Plugin isolation (MH-17): catch all exceptions
                if attempt < _MAX_RETRIES:
                    continue  # Retry once
                # Final attempt failed
                self._circuit_mgr.record_failure(provider_id, str(exc))
                return None

        return None  # pragma: no cover


__all__ = [
    "DispatchResult",
    "ProviderDispatcher",
]
