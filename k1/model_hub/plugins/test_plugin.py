"""TestProviderPlugin -- deterministic test plugin [F26].

Implements IProviderPlugin with fully configurable, deterministic behavior.
Used in all test environments as a stand-in for real provider plugins.
Records all calls for post-test assertion.

NO real HTTP calls. NO real API keys. NO external dependencies.

Import graph (Layer 4 -- imports Layer 0 + Layer 2)
-----------------------------------------------------
k1.model_hub.plugins.test_plugin
  -> k1.model_hub.types          (Layer 0)
  -> k1.model_hub.manifest       (Layer 0)
  -> k1.model_hub.plugins.base   (Layer 2: IProviderPlugin, dataclasses)
  -> stdlib only

NEVER import from any adapter, service, or runtime module.

References
----------
- model_hub.mmd: TestProviderPlugin (test isolation)
- Invariant MH-17: Plugin isolation
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import AsyncIterator, List, Optional

from k1.model_hub.manifest import ProviderManifest
from k1.model_hub.plugins.base import (
    NormalizedRequest,
    ProviderChunk,
    ProviderHealth,
    ProviderResponse,
)
from k1.model_hub.types import (
    CapabilityType,
    FinishReason,
    HealthStatus,
    Message,
    ProviderError,
    ToolCallResult,
)

# ===========================================================================
# Call Records (for post-test assertion)
# ===========================================================================


@dataclass(frozen=True)
class ExecuteCall:
    """Captured execute() call."""

    request: NormalizedRequest
    timestamp: float


@dataclass(frozen=True)
class StreamCall:
    """Captured stream_execute() call."""

    request: NormalizedRequest
    timestamp: float


@dataclass(frozen=True)
class HealthCheckCall:
    """Captured health_check() call."""

    timestamp: float


# ===========================================================================
# TestProviderPlugin
# ===========================================================================


class TestProviderPlugin:
    """Deterministic test plugin implementing IProviderPlugin.

    Configurable:
      - response_text: Text returned from execute() (default "test-response").
      - prompt_tokens / completion_tokens: Token counts.
      - model_id: Model ID in response.
      - finish_reason: FinishReason in response.
      - tool_calls: Optional tool calls in response.
      - stream_chunks: List of strings for streaming (default ["chunk-1", "chunk-2"]).
      - latency_ms: Simulated latency per call (default 0).
      - fail_count: Number of initial calls that raise ProviderError (default 0).
      - health_status: Status from health_check() (default HEALTHY).
      - capabilities: Supported capabilities (default [CHAT]).
      - token_estimate: Value from estimate_tokens() (default 10).

    Call Recording:
      - execute_calls: list of ExecuteCall
      - stream_calls: list of StreamCall
      - health_calls: list of HealthCheckCall
      - total_calls: total execute + stream count

    Registered as any provider_id for test isolation.
    """

    def __init__(
        self,
        *,
        response_text: str = "test-response",
        prompt_tokens: int = 10,
        completion_tokens: int = 5,
        model_id: str = "test-model",
        finish_reason: FinishReason = FinishReason.STOP,
        tool_calls: Optional[List[ToolCallResult]] = None,
        stream_chunks: Optional[List[str]] = None,
        latency_ms: int = 0,
        fail_count: int = 0,
        fail_error: Optional[Exception] = None,
        health_status: HealthStatus = HealthStatus.HEALTHY,
        capabilities: Optional[List[CapabilityType]] = None,
        token_estimate: int = 10,
    ) -> None:
        self._response_text = response_text
        self._prompt_tokens = prompt_tokens
        self._completion_tokens = completion_tokens
        self._model_id = model_id
        self._finish_reason = finish_reason
        self._tool_calls = tool_calls
        self._stream_chunks = stream_chunks or ["chunk-1", "chunk-2"]
        self._latency_ms = latency_ms
        self._fail_count = fail_count
        self._fail_error = fail_error
        self._health_status = health_status
        self._capabilities = set(capabilities or [CapabilityType.CHAT])
        self._token_estimate = token_estimate

        # Call tracking
        self._execute_calls: List[ExecuteCall] = []
        self._stream_calls: List[StreamCall] = []
        self._health_calls: List[HealthCheckCall] = []
        self._call_count = 0
        self._initialized = False
        self._closed = False

    # -- IProviderPlugin methods -----------------------------------------------

    async def initialize(self, manifest: ProviderManifest) -> None:
        """Initialize plugin (no-op for test, marks initialized)."""
        self._initialized = True

    def supports(self, capability: CapabilityType) -> bool:
        """Check if capability is in configured set."""
        return capability in self._capabilities

    async def execute(self, request: NormalizedRequest) -> ProviderResponse:
        """Return deterministic response, optionally simulating failure/latency."""
        self._call_count += 1
        self._execute_calls.append(ExecuteCall(request=request, timestamp=time.monotonic()))

        # Simulate latency
        if self._latency_ms > 0:
            await asyncio.sleep(self._latency_ms / 1000.0)

        # Simulate failure
        if self._call_count <= self._fail_count:
            error = self._fail_error or ProviderError(
                f"Test failure #{self._call_count}",
                provider_id="test",
            )
            raise error

        return ProviderResponse(
            text=self._response_text,
            tool_calls=self._tool_calls,
            prompt_tokens=self._prompt_tokens,
            completion_tokens=self._completion_tokens,
            model_id=request.model_id or self._model_id,
            finish_reason=self._finish_reason,
        )

    async def stream_execute(self, request: NormalizedRequest) -> AsyncIterator[ProviderChunk]:
        """Yield deterministic chunks, optionally simulating failure/latency."""
        self._call_count += 1
        self._stream_calls.append(StreamCall(request=request, timestamp=time.monotonic()))

        # Simulate latency
        if self._latency_ms > 0:
            await asyncio.sleep(self._latency_ms / 1000.0)

        # Simulate failure
        if self._call_count <= self._fail_count:
            error = self._fail_error or ProviderError(
                f"Test stream failure #{self._call_count}",
                provider_id="test",
            )
            raise error

        for i, text in enumerate(self._stream_chunks):
            is_last = i == len(self._stream_chunks) - 1
            yield ProviderChunk(text=text, done=is_last)

    def estimate_tokens(self, messages: List[Message]) -> int:
        """Return configured token estimate."""
        return self._token_estimate

    async def health_check(self) -> ProviderHealth:
        """Return configured health status."""
        self._health_calls.append(HealthCheckCall(timestamp=time.monotonic()))
        return ProviderHealth(status=self._health_status)

    async def close(self) -> None:
        """Mark plugin as closed."""
        self._closed = True

    # -- Test inspection properties --------------------------------------------

    @property
    def execute_calls(self) -> List[ExecuteCall]:
        """All captured execute() calls."""
        return list(self._execute_calls)

    @property
    def stream_calls(self) -> List[StreamCall]:
        """All captured stream_execute() calls."""
        return list(self._stream_calls)

    @property
    def health_calls(self) -> List[HealthCheckCall]:
        """All captured health_check() calls."""
        return list(self._health_calls)

    @property
    def total_calls(self) -> int:
        """Total execute + stream calls."""
        return len(self._execute_calls) + len(self._stream_calls)

    @property
    def initialized(self) -> bool:
        """Whether initialize() was called."""
        return self._initialized

    @property
    def closed(self) -> bool:
        """Whether close() was called."""
        return self._closed

    def reset(self) -> None:
        """Reset all call records and counters."""
        self._execute_calls.clear()
        self._stream_calls.clear()
        self._health_calls.clear()
        self._call_count = 0


__all__ = [
    "ExecuteCall",
    "HealthCheckCall",
    "StreamCall",
    "TestProviderPlugin",
]
