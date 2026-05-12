"""LLMGatewayAdapter -- V2 production LLM adapter [F29].

Implements ``ILLMPort`` (SS15.3) by routing ``PlannerLLMRequest`` messages
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
  -> k1.planner.types           (PlannerLLMRequest, PlannerLLMResponse,
                                  LLMTimeoutError, AdapterException)
  -> k1.model_hub.types         (HubRequest, HubResponse, CapabilityType,
                                  RequestConstraints, Priority)
  -> typing, asyncio, uuid
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import uuid
from typing import Any, Protocol, runtime_checkable

from k1.model_hub.types import CapabilityType, HubRequest, Priority, RequestConstraints
from k1.planner.types import (
    AdapterException,
    LLMTimeoutError,
    PlannerLLMRequest,
    PlannerLLMResponse,
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

    Routes ``PlannerLLMRequest`` envelopes through the LLM Request Bus to the
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

    async def execute(self, request: PlannerLLMRequest) -> PlannerLLMResponse:
        """Execute a single LLM inference call via the Model Hub.

        Stamps ``constraints.consumer_id`` for cost attribution before
        translating the planner-local envelope to ``model_hub.types.HubRequest``
        and dispatching through the bus.

        Error mapping:
            - Hub timeout -> ``LLMTimeoutError``
            - Network / bus failure -> ``AdapterException(DEGRADED)``
        """
        # Stamp consumer_id for cost tracking (MH-11).
        # PlannerLLMRequest.constraints is a frozen dataclass -- we create a
        # new constraints instance with the consumer_id set.
        stamped = _stamp_consumer_id(request, self._consumer_id)

        # Translate PlannerLLMRequest -> model_hub.HubRequest.
        # The planner uses str enums + simplified constraints; the Model Hub
        # router requires CapabilityType enum + RequestConstraints + non-empty
        # trace_id (MH-03). Without this translation the router rejects the
        # request at _validate() and crashes accessing request.request_id.
        hub_request = _to_hub_request(stamped)

        try:
            raw_response = await self._bus.request(hub_request)
            if isinstance(raw_response, PlannerLLMResponse):
                return raw_response
            # Coerce HubResponse (or any dict-like) into PlannerLLMResponse
            return _from_hub_response(raw_response)
        except asyncio.TimeoutError as exc:
            timeout_ms = getattr(request.constraints, "timeout_ms", 0)
            raise LLMTimeoutError(
                f"Model Hub timed out after {timeout_ms}ms",
                stage=_extract_stage(request),
            ) from exc
        except Exception as exc:
            msg = str(exc)
            raise AdapterException(
                f"LLM bus failure: {msg}",
                degraded=True,
                stage=_extract_stage(request),
            ) from exc


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _stamp_consumer_id(request: PlannerLLMRequest, consumer_id: str) -> PlannerLLMRequest:
    """Return a copy of the request with consumer_id stamped on constraints."""
    from dataclasses import replace as dc_replace

    try:
        new_constraints = dc_replace(request.constraints, consumer_id=consumer_id)
        return dc_replace(request, constraints=new_constraints)
    except (TypeError, AttributeError):
        # If constraints is not a proper dataclass, return as-is.
        logger.warning("Could not stamp consumer_id on PlannerLLMRequest constraints")
        return request


def _to_hub_request(request: PlannerLLMRequest) -> HubRequest:
    """Translate a planner-local ``PlannerLLMRequest`` into ``HubRequest``.

    - ``capability`` (str ``"CHAT"``/``"STRUCTURED"``) -> ``CapabilityType``.
    - ``constraints`` (``PlannerConstraints``) -> ``RequestConstraints``
      (priority str -> ``Priority`` enum, fields copied).
    - ``trace_id`` defaults to a fresh uuid4 when empty (MH-03 requires
      non-empty).
    """
    try:
        capability = CapabilityType(request.capability)
    except ValueError as exc:
        raise AdapterException(
            f"Unknown planner capability: {request.capability!r}",
            degraded=False,
            stage=_extract_stage(request),
        ) from exc

    try:
        priority = Priority(request.constraints.priority)
    except ValueError:
        priority = Priority.INTERACTIVE

    constraints = RequestConstraints(
        max_tokens=request.constraints.max_tokens,
        timeout_ms=request.constraints.timeout_ms,
        priority=priority,
        temperature=request.constraints.temperature,
        consumer_id=request.constraints.consumer_id,
    )

    trace_id = request.trace_id or str(uuid.uuid4())

    # Coerce the planner-side dict payload into the model_hub typed
    # payload dataclass (ChatPayload / StructuredOutputPayload / ...).
    # Public re-export of the shared dispatch table keeps payload construction
    # single-sourced without leaking a private name.
    from k1.model_hub.adapters import build_payload

    typed_payload = build_payload(capability, request.payload)

    return HubRequest(
        capability=capability,
        payload=typed_payload,
        constraints=constraints,
        trace_id=trace_id,
    )


def _from_hub_response(response: Any) -> PlannerLLMResponse:
    """Translate a model_hub ``HubResponse`` (or arbitrary object) into
    ``PlannerLLMResponse``.

    Field rules:
      - ``result``: prefer ``response.result`` as-is when dict; else
        attempt ``dataclasses.asdict``; else wrap in ``{"value": result}``.
      - ``metadata``: same coercion strategy applied to ``response.metadata``.

    Planner-side normalization:
      - All planner consumers (``sketch_service``, ``validate_service``,
        ``hil_coordinator``) read ``response.result["content"]``. Hub
        result dataclasses use capability-specific field names
        (``ChatResult.text``, ``StructuredResult.json_output``,
        ``ReasonResult.text``). We backfill ``content`` from those when
        absent so callers see a stable shape.
    """
    result = _coerce_to_dict(getattr(response, "result", {}))
    if "content" not in result:
        if "text" in result and result["text"] is not None:
            result["content"] = result["text"]
        elif "json_output" in result:
            result["content"] = result["json_output"]
    return PlannerLLMResponse(
        result=result,
        metadata=_coerce_to_dict(getattr(response, "metadata", {})),
    )


def _coerce_to_dict(value: Any) -> dict:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        try:
            return dataclasses.asdict(value)
        except Exception:  # noqa: BLE001
            pass
    if hasattr(value, "to_dict"):
        try:
            return value.to_dict()
        except Exception:  # noqa: BLE001
            pass
    return {"value": value}


def _extract_stage(request: PlannerLLMRequest) -> str:
    """Best-effort extraction of the pipeline stage from a PlannerLLMRequest."""
    try:
        return getattr(request.constraints, "consumer_id", "") or ""
    except AttributeError:
        return ""


__all__ = ["LLMGatewayAdapter", "ILLMRequestBus"]
