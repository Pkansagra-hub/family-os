"""ModelHubRequestBus -- ILLMRequestBus shim for ModelHub (Issue 2.2.6).

Bridges the Planner's ``ILLMRequestBus`` Protocol (``async request()``)
to ModelHub's ``IModelHubPort`` (``async execute()``).

``LLMGatewayAdapter`` (V2) expects an ``ILLMRequestBus`` with::

    async def request(self, hub_request: Any) -> Any

ModelHub exposes::

    async def execute(self, hub_request: HubRequest) -> HubResponse

This adapter maps ``request()`` → ``execute()`` so the Planner can use
the production ``LLMGatewayAdapter`` against a real ModelHub without
a full LLM Request Bus transport layer.
"""

from __future__ import annotations

from typing import Any


class ModelHubRequestBus:
    """Adapts ModelHub.execute() to ILLMRequestBus.request()."""

    __slots__ = ("_hub",)

    def __init__(self, hub: Any) -> None:
        self._hub = hub

    async def request(self, hub_request: Any) -> Any:
        """Delegate to ModelHub.execute()."""
        return await self._hub.execute(hub_request)
