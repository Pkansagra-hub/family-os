"""BusEnvelopeDeserializer -- Bus→ModelHub transport bridge [E-0.5.9].

Subscribes to ``TOPIC_HUB_EXECUTE`` on the K1 bus.  When an envelope
arrives the JSON payload is deserialized into a ``HubRequest`` and
dispatched to the wrapped ``LLMRequestBusAdapter``.  The resulting
``HubResponse`` is serialized back into an envelope and published on
``TOPIC_HUB_RESPONSE``.

Design
------
* IBus handlers are **synchronous** (``Callable[[Envelope], None]``).
  ``execute()`` is async, so we schedule the coroutine on the supplied
  event loop via ``asyncio.run_coroutine_threadsafe``.
* Payload must be ``PayloadFormat.JSON`` (hint=1).  OPAQUE/MSGPACK
  payloads are logged-and-dropped.
* Malformed payloads never crash the bus -- errors are logged.

Import graph (Layer 3 -- adapter)
---------------------------------
k1.model_hub.adapters.bus_envelope_deserializer
  -> k1.model_hub.adapters.llm_request_bus_adapter  (Layer 3)
  -> k1.model_hub.types                              (Layer 0)
  -> k1.bus.envelope                                 (external)
  -> k1.bus.ports.bus                                (external)
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict
from typing import Any, Dict, Optional

from k1.bus.envelope import Envelope, PayloadFormat
from k1.bus.ports.bus import IBus, SubscriptionHandle
from k1.model_hub.adapters.llm_request_bus_adapter import LLMRequestBusAdapter
from k1.model_hub.types import (
    CapabilityType,
    ChatPayload,
    HubRequest,
    HubResponse,
    Message,
    RequestConstraints,
    ToolCallPayload,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Topics
# ---------------------------------------------------------------------------

TOPIC_HUB_EXECUTE: str = "k1.model_hub.execute.v1"
"""Inbound topic: callers publish a JSON-serialised HubRequest here."""

TOPIC_HUB_RESPONSE: str = "k1.model_hub.execute.response.v1"
"""Outbound topic: deserializer publishes JSON-serialised HubResponse here."""

# ---------------------------------------------------------------------------
# Payload reconstruction helpers
# ---------------------------------------------------------------------------

#: Registry of capability → payload constructor.
#: Each entry maps CapabilityType to a callable that accepts a raw dict
#: and returns a typed payload dataclass.
_PAYLOAD_BUILDERS: Dict[CapabilityType, Any] = {
    CapabilityType.CHAT: lambda d: ChatPayload(
        messages=[Message(**m) for m in d.get("messages", [])],
        system_prompt=d.get("system_prompt"),
    ),
    CapabilityType.TOOL_CALL: lambda d: ToolCallPayload(
        messages=[Message(**m) for m in d.get("messages", [])],
        tools=d.get("tools", []),
        tool_choice=d.get("tool_choice", "auto"),
        parallel_tool_calls=d.get("parallel_tool_calls", True),
    ),
    # Other capability types pass the raw dict through as payload.
    # Production wiring for additional types can be added here.
}


def _build_payload(capability: CapabilityType, raw: Dict[str, Any]) -> Any:
    """Reconstruct a typed payload from a raw dict.

    Falls back to passing the raw dict if no builder is registered.
    """
    builder = _PAYLOAD_BUILDERS.get(capability)
    if builder is not None:
        return builder(raw)
    return raw


def _build_constraints(raw: Optional[Dict[str, Any]]) -> RequestConstraints:
    """Reconstruct ``RequestConstraints`` from a raw dict."""
    if raw is None:
        return RequestConstraints()
    # Map priority string → enum if present
    priority_val = raw.get("priority", "INTERACTIVE")
    from k1.model_hub.types import Priority

    try:
        priority = Priority(priority_val)
    except (ValueError, KeyError):
        priority = Priority.INTERACTIVE

    return RequestConstraints(
        max_tokens=raw.get("max_tokens", 65536),
        timeout_ms=raw.get("timeout_ms", 30000),
        priority=priority,
        temperature=raw.get("temperature", 0.7),
        provider_preference=raw.get("provider_preference"),
        cost_limit=raw.get("cost_limit"),
        consumer_id=raw.get("consumer_id", ""),
    )


def deserialize_hub_request(data: Dict[str, Any]) -> HubRequest:
    """Deserialize a JSON dict into a ``HubRequest``.

    Args:
        data: Dict with keys ``capability``, ``payload``, optionally
              ``constraints``, ``trace_id``, ``idempotency_key``,
              ``request_id``.

    Returns:
        Fully constructed ``HubRequest``.

    Raises:
        ValueError: If ``capability`` is missing or ``trace_id`` is empty.
        KeyError: If required fields are absent.
    """
    capability = CapabilityType(data["capability"])
    payload = _build_payload(capability, data.get("payload", {}))
    constraints = _build_constraints(data.get("constraints"))
    return HubRequest(
        capability=capability,
        payload=payload,
        constraints=constraints,
        trace_id=data.get("trace_id", ""),
        idempotency_key=data.get("idempotency_key"),
        request_id=data.get("request_id", ""),
    )


def serialize_hub_response(response: HubResponse) -> bytes:
    """Serialize a ``HubResponse`` to JSON bytes for bus payload.

    Uses ``dataclasses.asdict`` with enum-value coercion.
    """

    def _default(obj: Any) -> Any:
        if hasattr(obj, "value"):
            return obj.value
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    return json.dumps(asdict(response), default=_default).encode("utf-8")


# ---------------------------------------------------------------------------
# BusEnvelopeDeserializer
# ---------------------------------------------------------------------------


class BusEnvelopeDeserializer:
    """Subscribes to bus, deserializes envelopes → HubRequest, dispatches.

    Args:
        bus:     The K1 IBus instance.
        adapter: The LLMRequestBusAdapter that wraps the inner IModelHubPort.
        loop:    The asyncio event loop on which ``adapter.execute()`` will
                 be scheduled.  If *None*, ``asyncio.get_running_loop()``
                 is attempted at handler time.
    """

    def __init__(
        self,
        bus: IBus,
        adapter: LLMRequestBusAdapter,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        self._bus = bus
        self._adapter = adapter
        self._loop = loop
        self._handle: Optional[SubscriptionHandle] = None
        self._handle = bus.subscribe(TOPIC_HUB_EXECUTE, self._on_envelope)

    # -- Bus handler (sync) ------------------------------------------------

    def _on_envelope(self, envelope: Envelope) -> None:
        """Bus handler: deserialize envelope and dispatch to adapter."""
        if envelope.payload_format != PayloadFormat.JSON:
            logger.warning(
                "BusEnvelopeDeserializer: dropping non-JSON envelope "
                "(format=%s, topic=%s, envelope_id=%d)",
                envelope.payload_format,
                envelope.topic,
                envelope.envelope_id,
            )
            return

        try:
            raw = json.loads(envelope.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.error(
                "BusEnvelopeDeserializer: malformed JSON payload " "(envelope_id=%d): %s",
                envelope.envelope_id,
                exc,
            )
            return

        try:
            hub_request = deserialize_hub_request(raw)
        except (ValueError, KeyError, TypeError) as exc:
            logger.error(
                "BusEnvelopeDeserializer: failed to build HubRequest " "(envelope_id=%d): %s",
                envelope.envelope_id,
                exc,
            )
            return

        # Schedule the async execute on the event loop
        loop = self._loop
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                logger.error(
                    "BusEnvelopeDeserializer: no event loop available " "(envelope_id=%d)",
                    envelope.envelope_id,
                )
                return

        future = asyncio.run_coroutine_threadsafe(
            self._dispatch(hub_request, envelope),
            loop,
        )
        # Fire-and-forget -- errors handled inside _dispatch
        future.add_done_callback(self._on_dispatch_done)

    async def _dispatch(self, request: HubRequest, source_envelope: Envelope) -> None:
        """Execute the request and publish response back to bus."""
        try:
            response = await self._adapter.execute(request)
        except Exception:
            logger.exception(
                "BusEnvelopeDeserializer: adapter.execute() failed " "(request_id=%s)",
                request.request_id,
            )
            return

        # Publish response envelope
        try:
            response_payload = serialize_hub_response(response)
            response_envelope = Envelope(
                topic=TOPIC_HUB_RESPONSE,
                priority=source_envelope.priority,
                cognitive_trace_id=request.trace_id,
                session_id=source_envelope.session_id,
                request_id=request.request_id,
                parent_id=source_envelope.envelope_id,
                payload=response_payload,
                payload_format=PayloadFormat.JSON,
            )
            self._bus.publish(response_envelope)
        except Exception:
            logger.exception(
                "BusEnvelopeDeserializer: failed to publish response " "(request_id=%s)",
                request.request_id,
            )

    @staticmethod
    def _on_dispatch_done(future: asyncio.Future) -> None:
        """Log unhandled exceptions from dispatched coroutines."""
        exc = future.exception()
        if exc is not None:
            logger.error("BusEnvelopeDeserializer: unhandled dispatch error: %s", exc)

    # -- Lifecycle ---------------------------------------------------------

    def close(self) -> None:
        """Unsubscribe from bus. Call on shutdown."""
        if self._handle is not None:
            self._bus.unsubscribe(self._handle)
            self._handle = None

    @property
    def is_subscribed(self) -> bool:
        """True if currently subscribed to the bus."""
        return self._handle is not None


__all__ = [
    "BusEnvelopeDeserializer",
    "TOPIC_HUB_EXECUTE",
    "TOPIC_HUB_RESPONSE",
    "deserialize_hub_request",
    "serialize_hub_response",
]
