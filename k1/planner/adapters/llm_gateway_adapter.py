"""LLMGatewayAdapter -- V2 production LLM adapter [F29].

Implements ``ILLMPort`` (SS15.3) by routing ``HubRequest`` messages
through an async ``ILLMRequestBus`` to the Model Hub.

V1 NOTE (SS16.1.2):
    V1 runs ``TestLLMAdapter`` in ALL environments.
    ``LLMGatewayAdapter`` is the V2 production path when Model Hub is live.

Adapter wiring (SS16.1.2, SS16.3):
    ILLMPort -> LLMGatewayAdapter -> ILLMRequestBus -> Model Hub

Import graph (Layer 2)
----------------------
k1.planner.adapters.llm_gateway_adapter
  -> k1.planner.ports.llm_port  (ILLMPort)
  -> k1.planner.types           (HubRequest, HubResponse, LLMTimeoutError,
                                  BudgetExceededError, AdapterException)
  -> typing, asyncio
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol, runtime_checkable

from k1.planner.types import (
    AdapterException,
    BudgetExceededError,
    HubRequest,
    HubResponse,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bus protocol -- the async request-reply channel to Model Hub.
# Concrete implementation provided by the Model Hub module (V2).
# ---------------------------------------------------------------------------


@runtime_checkable
class ILLMRequestBus(Protocol):
    """Async request-reply bus protocol for LLM requests.

    The concrete implementation lives in the Model Hub module.
    This protocol exists so that ``LLMGatewayAdapter`` has a typed
    dependency without importing Model Hub code directly.
    """

    async def request(self, hub_request: Any) -> Any:
        """Send a HubRequest and await a HubResponse."""
        ...  # pragma: no cover


class LLMGatewayAdapter:
    """V2 production LLM adapter (SS16.1.2).

    Routes ``HubRequest`` envelopes through the LLM Request Bus to the
    Model Hub.  Stamps ``consumer_id`` for cost attribution (MH-11).
    The Planner does NOT select models -- the Model Hub's ModelSelector
    chooses (SS13.4).
    """

    __slots__ = ("_bus", "_consumer_id")

    def __init__(
        self,
        llm_request_bus: ILLMRequestBus,
        consumer_id: str = "planner",
    ) -> None:
        self._bus: ILLMRequestBus = llm_request_bus
        self._consumer_id: str = consumer_id

    # ------------------------------------------------------------------
    # ILLMPort implementation
    # ------------------------------------------------------------------

    async def execute(self, request: HubRequest) -> HubResponse:
        """Execute a single LLM inference call via the Model Hub.

        Stamps ``constraints.consumer_id`` for cost attribution before
        dispatching through the bus.

        Error mapping:
            - Hub timeout -> ``LLMTimeoutError``
            - Hub budget rejection -> ``BudgetExceededError``
            - Network / bus failure -> ``AdapterException(DEGRADED)``
        """
        # Stamp consumer_id for cost tracking (MH-11).
        # HubRequest.constraints is a frozen dataclass -- we create a new
        # constraints instance with the consumer_id set.
        stamped = _stamp_consumer_id(request, self._consumer_id)

        try:
            raw_response = await self._bus.request(stamped)
            if isinstance(raw_response, HubResponse):
                return raw_response
            # Coerce dict-like response into HubResponse
            return HubResponse(
                result=getattr(raw_response, "result", {}),
                metadata=getattr(raw_response, "metadata", {}),
            )
        except asyncio.TimeoutError as exc:
            timeout_ms = getattr(request.constraints, "timeout_ms", 0)
            raise LLMTimeoutError(
                f"Model Hub timed out after {timeout_ms}ms",
                stage=_extract_stage(request),
            ) from exc
        except Exception as exc:
            msg = str(exc)
            if "budget" in msg.lower():
                raise BudgetExceededError(
                    f"Model Hub budget exceeded: {msg}",
                    stage=_extract_stage(request),
                ) from exc
            raise AdapterException(
                f"LLM bus failure: {msg}",
                degraded=True,
                stage=_extract_stage(request),
            ) from exc


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _stamp_consumer_id(request: HubRequest, consumer_id: str) -> HubRequest:
    """Return a copy of the request with consumer_id stamped on constraints."""
    from dataclasses import replace as dc_replace

    try:
        new_constraints = dc_replace(request.constraints, consumer_id=consumer_id)
        return dc_replace(request, constraints=new_constraints)
    except (TypeError, AttributeError):
        # If constraints is not a proper dataclass, return as-is.
        logger.warning("Could not stamp consumer_id on HubRequest constraints")
        return request


def _extract_stage(request: HubRequest) -> str:
    """Best-effort extraction of the pipeline stage from a HubRequest."""
    try:
        return getattr(request.constraints, "consumer_id", "") or ""
    except AttributeError:
        return ""


__all__ = ["LLMGatewayAdapter", "ILLMRequestBus"]
