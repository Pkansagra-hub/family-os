"""StubProviderPlugin -- in-process canned plugin for ``model_mode='test'``.

Registered by ``KernelService.startup`` when ``model_mode != 'hub'`` so that
the kernel boot path has at least one provider that satisfies every Hub
capability (``CHAT``, ``TOOL_CALL``, ``STRUCTURED``, ``REASON``,
``EMBED``, ``TOKEN_COUNT``, ...). Without this, the Concierge ReAct loop
explodes with ``NoEligibleProviderError`` on the first turn.

Design:
  - All capabilities supported by a single plugin (one provider, one model).
  - ``execute()`` returns a deterministic text response with FinishReason.STOP
    and never emits tool_calls — the ReAct loop, which forces ``required``
    tool_choice on iteration 0 with tools, will see ``finish_reason=STOP``
    and fall through to a normal text response on the next iteration.
  - ``stream_execute()`` emits a single done chunk so the streaming path
    works.
  - Token estimate is a coarse word count.

NOT for production. NOT for evaluation quality. Only smoke-tests the wire
plumbing: Concierge → Orchestrator → Fabric → Planner → MemoryWriter.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from k1.model_hub.manifest import ModelSpec, PlacementConfig, ProviderManifest
from k1.model_hub.plugins.base import (
    NormalizedRequest,
    ProviderChunk,
    ProviderHealth,
    ProviderResponse,
)
from k1.model_hub.types import CapabilityType, FinishReason, HealthStatus, ModelTier, PlacementType

_ALL_CAPABILITIES: list[CapabilityType] = list(CapabilityType)
_DEFAULT_MODEL_ID = "stub-canned-v1"
_DEFAULT_PROVIDER_ID = "stub"
_DEFAULT_RESPONSE_TEXT = "OK"


def build_stub_manifest(
    provider_id: str = _DEFAULT_PROVIDER_ID,
    model_id: str = _DEFAULT_MODEL_ID,
) -> ProviderManifest:
    """Construct a manifest claiming every capability for one in-proc model."""
    return ProviderManifest(
        provider_id=provider_id,
        display_name="Stub (canned)",
        capabilities=list(_ALL_CAPABILITIES),
        models=[
            ModelSpec(
                id=model_id,
                capabilities=list(_ALL_CAPABILITIES),
                cost_per_1m_input=0.0,
                cost_per_1m_output=0.0,
                max_context=128000,
                tier=ModelTier.STANDARD,
            ),
        ],
        placement=PlacementConfig(type=PlacementType.LOCAL_CPU),
    )


class StubProviderPlugin:
    """All-capability canned plugin used only in ``model_mode='test'``."""

    def __init__(self, response_text: str = _DEFAULT_RESPONSE_TEXT) -> None:
        self._response_text = response_text
        self._calls: list[NormalizedRequest] = []

    async def initialize(self, manifest: ProviderManifest) -> None:  # noqa: D401
        return None

    def supports(self, capability: CapabilityType) -> bool:
        return True

    async def execute(self, request: NormalizedRequest) -> ProviderResponse:
        self._calls.append(request)
        return ProviderResponse(
            text=self._response_text,
            tool_calls=None,
            prompt_tokens=10,
            completion_tokens=2,
            model_id=request.model_id or _DEFAULT_MODEL_ID,
            finish_reason=FinishReason.STOP,
        )

    async def stream_execute(self, request: NormalizedRequest) -> AsyncIterator[ProviderChunk]:
        self._calls.append(request)
        yield ProviderChunk(text=self._response_text, done=True)

    def estimate_tokens(self, messages: Any) -> int:
        if isinstance(messages, str):
            return max(1, len(messages.split()))
        if isinstance(messages, list):
            total = 0
            for m in messages:
                content = getattr(m, "content", None) or (
                    m.get("content") if isinstance(m, dict) else ""
                )
                if isinstance(content, str):
                    total += max(1, len(content.split()))
            return max(1, total)
        return 1

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(status=HealthStatus.HEALTHY, latency_ms=0)

    async def close(self) -> None:
        return None

    @property
    def calls(self) -> list[NormalizedRequest]:
        return list(self._calls)
