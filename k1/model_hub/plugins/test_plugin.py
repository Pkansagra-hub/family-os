"""
TestProviderPlugin -- Deterministic Test Provider
===================================================

Spec: k1/model_hub/model_hub.mmd — ADAPTERS_TEST section

No real LLM calls. Configurable per capability:
  - Fixed responses
  - Response sequences for multi-call tests
  - Configurable latency, errors, token counts
  - Records all calls for test assertions

Can be registered as any provider_id for test isolation.
"""

from __future__ import annotations

from typing import AsyncIterator

from k1.model_hub.plugins.base import (
    IProviderPlugin,
    NormalizedRequest,
    ProviderChunk,
    ProviderHealth,
    ProviderManifest,
    ProviderResponse,
)
from k1.model_hub.types import CapabilityType, Message


class TestProviderPlugin:
    """Deterministic test provider. Satisfies IProviderPlugin.

    Usage:
        plugin = TestProviderPlugin()
        plugin.set_response(CapabilityType.CHAT, ProviderResponse(text="Hello!"))
        resp = await plugin.execute(NormalizedRequest(capability=CapabilityType.CHAT))
        assert resp.text == "Hello!"
        assert plugin.call_count == 1
    """

    def __init__(self, provider_id: str = "test") -> None:
        self.provider_id = provider_id
        self._manifest: ProviderManifest | None = None
        self._capabilities: set[CapabilityType] = set(CapabilityType)
        self._responses: dict[CapabilityType, ProviderResponse] = {}
        self._sequences: dict[CapabilityType, list[ProviderResponse]] = {}
        self._sequence_idx: dict[CapabilityType, int] = {}
        self._default_response = ProviderResponse(
            text="test response",
            model_id="test-model",
            prompt_tokens=10,
            completion_tokens=5,
        )
        self.calls: list[NormalizedRequest] = []

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def set_response(self, capability: CapabilityType, response: ProviderResponse) -> None:
        """Set a fixed response for a capability."""
        self._responses[capability] = response

    def set_response_sequence(
        self, capability: CapabilityType, responses: list[ProviderResponse]
    ) -> None:
        """Set a sequence of responses. After exhaustion, last response repeats."""
        self._sequences[capability] = responses
        self._sequence_idx[capability] = 0

    def set_default_response(self, response: ProviderResponse) -> None:
        """Set fallback response when no capability match."""
        self._default_response = response

    def set_capabilities(self, caps: set[CapabilityType]) -> None:
        """Override which capabilities this test plugin reports."""
        self._capabilities = caps

    # ------------------------------------------------------------------
    # IProviderPlugin implementation
    # ------------------------------------------------------------------

    async def initialize(self, manifest: ProviderManifest) -> None:
        self._manifest = manifest
        if manifest.capabilities:
            self._capabilities = set(manifest.capabilities)

    def supports(self, capability: CapabilityType) -> bool:
        return capability in self._capabilities

    async def execute(self, request: NormalizedRequest) -> ProviderResponse:
        self.calls.append(request)
        cap = request.capability

        # Sequence first
        if cap in self._sequences:
            seq = self._sequences[cap]
            idx = self._sequence_idx[cap]
            resp = seq[min(idx, len(seq) - 1)]
            self._sequence_idx[cap] = idx + 1
            return resp

        # Fixed response
        if cap in self._responses:
            return self._responses[cap]

        return self._default_response

    async def stream_execute(self, request: NormalizedRequest) -> AsyncIterator[ProviderChunk]:
        resp = await self.execute(request)

        if resp.text:
            words = resp.text.split(" ")
            for i, word in enumerate(words):
                chunk_text = word if i == len(words) - 1 else word + " "
                yield ProviderChunk(chunk_type="text_delta", text=chunk_text)

        yield ProviderChunk(chunk_type="done", response=resp)

    async def estimate_tokens(self, messages: list[Message]) -> int:
        return sum(len(m.content.split()) * 2 for m in messages)

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(status="HEALTHY", latency_ms=1)

    async def close(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Assertion helpers
    # ------------------------------------------------------------------

    @property
    def call_count(self) -> int:
        return len(self.calls)

    @property
    def last_call(self) -> NormalizedRequest | None:
        return self.calls[-1] if self.calls else None

    def calls_for(self, capability: CapabilityType) -> list[NormalizedRequest]:
        return [c for c in self.calls if c.capability == capability]

    def reset(self) -> None:
        self.calls.clear()
        self._responses.clear()
        self._sequences.clear()
        self._sequence_idx.clear()
