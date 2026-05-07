"""
ModelHubAdapter -- Production IModelHubPort → Concierge-compatible adapter.
==========================================================================

Wraps a real ``ModelHubFactory.create_standalone()`` hub (``_HubCore``)
and ensures ``HubResponse.result`` uses the typed K1 dataclasses
(``ChatResult``, ``ToolCallResultSet``, etc.) that the Concierge
react loop's ``_unwrap_response`` expects.

The production ``NormalizationLayer.denormalize()`` returns raw
``str``/``dict`` as result.  This adapter normalises them to the
proper dataclasses without touching any internal hub or concierge code.

Usage (composition root only -- e.g. chat_repl.py)::

    from k1.model_hub.factory import ModelHubFactory
    from k1.concierge.llm.model_hub_adapter import ModelHubAdapter

    hub = ModelHubFactory.create_standalone(plugins={"google": plugin})
    adapter = ModelHubAdapter(hub)
    runtime.model = adapter  # swap at the composition root
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from k1.model_hub.types import (
    CapabilityType,
    ChatResult,
    HubChunk,
    HubHealthReport,
    HubRequest,
    HubResponse,
    ModelInfo,
    ReasonResult,
    StructuredResult,
    ToolCallResult,
    ToolCallResultSet,
)

logger = logging.getLogger(__name__)


class ModelHubAdapter:
    """Thin adapter ensuring HubResponse.result uses typed K1 dataclasses.

    Delegates all calls to the inner IModelHubPort (e.g. _HubCore from
    ModelHubFactory).  Only post-processes the ``result`` field of
    ``HubResponse`` so that ``_unwrap_response`` in the react loop
    can rely on ``isinstance`` checks.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    # -- IModelHubPort: execute ------------------------------------------------

    async def execute(self, request: HubRequest) -> HubResponse:
        response = await self._inner.execute(request)
        return _fix_result(response, request.capability)

    # -- IModelHubPort: stream_execute -----------------------------------------

    async def stream_execute(self, request: HubRequest) -> AsyncIterator[HubChunk]:
        async for chunk in self._inner.stream_execute(request):
            yield chunk

    # -- IModelHubPort: discovery / health (pass-through) ----------------------

    async def discover_capabilities(self) -> Dict[CapabilityType, List[str]]:
        return await self._inner.discover_capabilities()

    async def discover_models(self, capability: Optional[CapabilityType] = None) -> List[ModelInfo]:
        return await self._inner.discover_models(capability)

    async def health(self) -> HubHealthReport:
        return await self._inner.health()

    # -- Lifecycle (optional) --------------------------------------------------

    async def close(self) -> None:
        if hasattr(self._inner, "close"):
            await self._inner.close()


# ---------------------------------------------------------------------------
# Result normalisation helpers
# ---------------------------------------------------------------------------


def _fix_result(response: HubResponse, capability: CapabilityType) -> HubResponse:
    """Ensure response.result is a typed dataclass, not raw str/dict."""
    result = response.result

    # Already a typed dataclass -- nothing to do
    if isinstance(result, (ChatResult, ToolCallResultSet, StructuredResult, ReasonResult)):
        return response

    fixed = _coerce_result(result, capability)

    # HubResponse is frozen dataclass -- rebuild
    return HubResponse(result=fixed, metadata=response.metadata)


def _coerce_result(result: Any, capability: CapabilityType) -> Any:
    """Coerce raw result to the appropriate K1 dataclass."""

    if capability == CapabilityType.TOOL_CALL:
        if isinstance(result, dict):
            text = result.get("text", "")
            raw_calls = result.get("tool_calls", [])
            calls = [
                ToolCallResult(
                    id=tc.get("id", ""),
                    name=tc.get("name", ""),
                    arguments=tc.get("arguments", "{}"),
                )
                for tc in raw_calls
            ]
            return ToolCallResultSet(text=text, tool_calls=calls)
        return ChatResult(text=str(result) if result else "")

    if capability == CapabilityType.STRUCTURED:
        if isinstance(result, dict):
            return StructuredResult(json_output=result)
        return ChatResult(text=str(result) if result else "")

    if capability == CapabilityType.REASON:
        if isinstance(result, str):
            return ReasonResult(text=result)
        if isinstance(result, dict):
            return ReasonResult(
                text=result.get("text", ""),
                thinking=result.get("thinking", ""),
            )
        return ReasonResult(text=str(result) if result else "")

    # Default: CHAT or unknown capability
    if isinstance(result, str):
        return ChatResult(text=result)
    if isinstance(result, dict):
        return ChatResult(text=result.get("text", str(result)))
    return ChatResult(text=str(result) if result else "")
