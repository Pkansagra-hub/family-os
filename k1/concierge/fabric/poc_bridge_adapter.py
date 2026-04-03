"""
k1.concierge.fabric.poc_bridge_adapter -- POCMockBridgeAdapter.

Implements IBridgePort so the K1 BridgeProvider can dispatch capability
requests to POC mock handler functions through the standard Fabric
execution pipeline.

The adapter wraps the existing POC CapabilityRegistry and translates
between IBridgePort's ``send_command``/``query`` interface and the
POC handler's ``async (params: dict) -> dict`` signature.

M6 E6.2.1
"""

from __future__ import annotations

import inspect
import logging
import time
from typing import Any, Dict

from k1.concierge.fabric.capability_registry import CapabilityRegistry
from k1.fabric.ports.bridge_port import BridgeCommandResult, BridgeHealth, IFLRoute

logger = logging.getLogger(__name__)


class POCMockBridgeAdapter:
    """IBridgePort implementation backed by POC CapabilityRegistry handlers.

    All 40 POC capabilities route through this adapter when the real
    K1 Fabric dispatches via BridgeProvider.

    Structural subtyping: satisfies ``IBridgePort`` protocol without
    explicit inheritance (``typing.Protocol``).
    """

    def __init__(self, registry: CapabilityRegistry) -> None:
        self._registry = registry

    # ------------------------------------------------------------------
    # IBridgePort: send_command
    # ------------------------------------------------------------------

    async def send_command(
        self,
        operation: str,
        payload: Dict[str, Any],
        *,
        trace_id: str = "",
        timeout_ms: int = 0,
    ) -> BridgeCommandResult:
        """Dispatch a command to a POC handler by operation name.

        The ``operation`` is the capability name (e.g.
        ``"tool.execute.hotel_search"``).  The ``payload`` is the
        params dict passed straight to the handler.
        """
        handler = self._registry._handlers.get(operation)
        if handler is None:
            return BridgeCommandResult.fail(
                "not_found",
                f"No handler for operation: {operation}",
                k0_mode="K0_FULL",
                trace_id=trace_id,
            )

        start = time.monotonic()
        try:
            result = handler(payload)
            if inspect.isawaitable(result):
                result = await result

            latency = int((time.monotonic() - start) * 1000)

            if not isinstance(result, dict):
                result = {"result": result}

            return BridgeCommandResult.ok(
                data=result,
                latency_ms=latency,
                trace_id=trace_id,
            )
        except Exception as exc:
            latency = int((time.monotonic() - start) * 1000)
            logger.error("POCMockBridgeAdapter handler error: %s — %s", operation, exc)
            return BridgeCommandResult.fail(
                "handler_error",
                str(exc),
                k0_mode="K0_FULL",
                trace_id=trace_id,
            )

    # ------------------------------------------------------------------
    # IBridgePort: query
    # ------------------------------------------------------------------

    async def query(
        self,
        operation: str,
        selectors: Dict[str, Any],
        *,
        trace_id: str = "",
        timeout_ms: int = 0,
    ) -> BridgeCommandResult:
        """Read-only query — delegates to send_command (POC has no distinction)."""
        return await self.send_command(
            operation, selectors, trace_id=trace_id, timeout_ms=timeout_ms
        )

    # ------------------------------------------------------------------
    # IBridgePort: route_ifl
    # ------------------------------------------------------------------

    async def route_ifl(
        self,
        route: IFLRoute,
        payload: Dict[str, Any],
        *,
        trace_id: str = "",
    ) -> BridgeCommandResult:
        """Route an IFL-addressed request to the matching handler."""
        return await self.send_command(route.address, payload, trace_id=trace_id)

    # ------------------------------------------------------------------
    # IBridgePort: availability
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """POC mock bridge is always available."""
        return True

    def get_health(self) -> BridgeHealth:
        """POC mock bridge always reports full health."""
        return BridgeHealth(available=True, mode="K0_FULL")
