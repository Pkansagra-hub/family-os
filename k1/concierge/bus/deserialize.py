"""
k1.concierge.bus.deserialize -- Envelope payload deserialization to canonical events.

M1 E1.1.6: Given an Envelope, deserialize the JSON payload bytes to a
typed canonical event using the EVENT_TYPE_REGISTRY.

This is the inverse of the builder serialization path:
    builder -> _serialize(payload) -> Envelope.payload (bytes)
    Envelope.payload (bytes) -> deserialize_envelope -> CanonicalEventMeta subclass

Usage::

    from k1.concierge.bus.deserialize import deserialize_envelope

    event = deserialize_envelope(envelope)
    if event is not None:
        # event is a typed CanonicalEventMeta subclass
        print(event.event_type, event.task_id)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from k1.concierge.events.base import CanonicalEventMeta
from k1.concierge.events.registry import deserialize_event

logger = logging.getLogger(__name__)


def deserialize_envelope(envelope: Any) -> CanonicalEventMeta | None:
    """Deserialize an Envelope's payload to a typed canonical event.

    Args:
        envelope: A k1.bus.envelope.Envelope instance with JSON payload.

    Returns:
        A typed CanonicalEventMeta subclass instance, or None if:
        - Payload is empty or not valid JSON
        - Payload has no event_type field (legacy payload)
        - event_type is not registered in EVENT_TYPE_REGISTRY
    """
    payload_bytes: bytes = getattr(envelope, "payload", b"")
    if not payload_bytes:
        return None

    try:
        payload: dict[str, Any] = json.loads(payload_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.debug("deserialize_envelope: failed to parse JSON from envelope")
        return None

    if not isinstance(payload, dict):
        return None

    if "event_type" not in payload:
        return None  # Legacy payload without canonical metadata

    return deserialize_event(payload)


def parse_payload(envelope: Any) -> dict[str, Any]:
    """Parse Envelope payload bytes to a dict (backward-compatible helper).

    This always returns a dict regardless of whether the payload is
    canonical or legacy. For canonical payloads, adds a ``_canonical``
    marker key.

    Args:
        envelope: A k1.bus.envelope.Envelope instance with JSON payload.

    Returns:
        Parsed payload dict, or empty dict on failure.
    """
    payload_bytes: bytes = getattr(envelope, "payload", b"")
    if not payload_bytes:
        return {}

    try:
        result: dict[str, Any] = json.loads(payload_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}

    if not isinstance(result, dict):
        return {}

    if "event_type" in result and "event_id" in result:
        result["_canonical"] = True

    return result


__all__ = [
    "deserialize_envelope",
    "parse_payload",
]
