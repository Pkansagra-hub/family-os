"""IModelHubPort -- THE single gateway port [F10].

All LLM traffic flows through this port (MH-16).

Import graph (Layer 1)
----------------------
k1.model_hub.ports.hub_port
  -> k1.model_hub.types (Layer 0 only)
"""

from __future__ import annotations

from typing import AsyncIterator, Dict, List, Protocol, runtime_checkable

from k1.model_hub.types import (
    CapabilityType,
    HubChunk,
    HubHealthReport,
    HubRequest,
    HubResponse,
    ModelInfo,
)


@runtime_checkable
class IModelHubPort(Protocol):
    """THE single gateway for all LLM traffic (MH-16).

    All LLM consumers call execute() or stream_execute().
    No direct provider access allowed.
    """

    async def execute(self, request: HubRequest) -> HubResponse:
        """Execute a request synchronously (request-reply)."""
        ...

    async def stream_execute(self, request: HubRequest) -> AsyncIterator[HubChunk]:
        """Execute a request with streaming response."""
        ...

    async def discover_capabilities(self) -> Dict[CapabilityType, List[str]]:
        """Discover available capabilities and their provider IDs."""
        ...

    async def discover_models(self, capability: CapabilityType | None = None) -> List[ModelInfo]:
        """Discover available models, optionally filtered by capability."""
        ...

    async def health(self) -> HubHealthReport:
        """Return aggregate hub health report."""
        ...


__all__ = ["IModelHubPort"]
