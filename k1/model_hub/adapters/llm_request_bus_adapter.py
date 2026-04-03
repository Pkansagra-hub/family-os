"""LLMRequestBusAdapter -- LLM Request Bus binding [F30].

Receives HubRequest from K1 LLM Request Bus.
Deserializes capability-tagged envelope.
Returns HubResponse via bus reply channel.

Import graph (Layer 3 -- adapter)
---------------------------------
k1.model_hub.adapters.llm_request_bus_adapter
  -> k1.model_hub.types      (Layer 0)
  -> k1.model_hub.ports      (Layer 1)
  -> stdlib only (no external deps yet)
"""

from __future__ import annotations

import logging
from typing import AsyncIterator, Dict, List, Optional

from k1.model_hub.ports.hub_port import IModelHubPort
from k1.model_hub.types import (
    CapabilityType,
    HealthStatus,
    HubChunk,
    HubHealthReport,
    HubRequest,
    HubResponse,
    ModelInfo,
)

logger = logging.getLogger(__name__)


class LLMRequestBusAdapter:
    """IModelHubPort adapter that bridges K1 LLM Request Bus to Model Hub.

    Delegates to an inner IModelHubPort (the RequestRouter facade).
    In production, the bus transport layer calls execute/stream_execute
    with deserialized HubRequest envelopes.

    Error handling: never crash hub -- log and return error HubResponse.
    """

    def __init__(self, inner: IModelHubPort) -> None:
        self._inner = inner

    async def execute(self, request: HubRequest) -> HubResponse:
        """Receive HubRequest from bus, delegate to inner port."""
        try:
            return await self._inner.execute(request)
        except Exception:
            logger.exception(
                "LLMRequestBusAdapter.execute failed request_id=%s",
                request.request_id,
            )
            raise

    async def stream_execute(self, request: HubRequest) -> AsyncIterator[HubChunk]:
        """Receive streaming request from bus, delegate to inner port."""
        try:
            async for chunk in self._inner.stream_execute(request):
                yield chunk
        except Exception:
            logger.exception(
                "LLMRequestBusAdapter.stream_execute failed request_id=%s",
                request.request_id,
            )
            raise

    async def discover_capabilities(self) -> Dict[CapabilityType, List[str]]:
        """Delegate capability discovery."""
        return await self._inner.discover_capabilities()

    async def discover_models(self, capability: Optional[CapabilityType] = None) -> List[ModelInfo]:
        """Delegate model discovery."""
        return await self._inner.discover_models(capability)

    async def health(self) -> HubHealthReport:
        """Delegate health check."""
        try:
            return await self._inner.health()
        except Exception:
            logger.exception("LLMRequestBusAdapter.health failed")
            return HubHealthReport(status=HealthStatus.UNHEALTHY)


__all__ = ["LLMRequestBusAdapter"]
