"""Normalize Google Calendar IFL events into ``MemoryAtom`` rows.

This module is the K0-side counterpart of the GCal MCP adapter
(:mod:`bridge.ifl.adapters.google_calendar.server`). Each event
returned by the adapter becomes one ``MemoryAtom`` payload that
the existing P02 write-ingest pipeline can consume.

Lossy normalization is **intentional**: only the fields needed to
render an event back to the user end up in the atom. Extension
work for richer attendee/recurrence semantics lands in MS-7.
"""

from __future__ import annotations

from typing import Any, Iterable

# All atoms produced here are tagged with this canonical source so K0
# downstream filters (retention, audit, recall) can recognize the
# upstream provenance without re-parsing free-form fields.
SOURCE_TYPE = "device_observed"
TOPIC = "ifl.google_calendar.events.list.v1"


def _event_text(event: dict[str, Any]) -> str:
    """Stable human-readable summary used as the atom's primary
    text. Aligns with how the recall surface re-narrates events
    back to the user."""
    summary = event.get("summary") or "(untitled event)"
    start = event.get("start") or {}
    when = start.get("date_time") or start.get("date") or ""
    location = event.get("location")
    base = f"{summary} on {when}".strip()
    if location:
        return f"{base} at {location}"
    return base


def normalize_event(
    event: dict[str, Any],
    *,
    account_id: str,
    session_id: str,
) -> dict[str, Any]:
    """Convert one IFL event → MemoryAtom v2.2 payload."""
    if not isinstance(event, dict):
        raise TypeError("event must be a dict")
    if not event.get("id"):
        raise ValueError("event.id is required")

    text = _event_text(event)
    return {
        "schema_version": "2.2",
        "operation": "UPSERT",
        "text": text,
        "topics": ["calendar", "schedule"],
        "sentiment_label": "neutral",
        "affect": {"valence": 0.0, "arousal": 0.0, "dominance": 0.5},
        "source_type": SOURCE_TYPE,
        "novelty": "EXPECTED",
        "elaboration_depth": "MENTION",
        "temporal_orientation": "FUTURE_COMMITMENT",
        "confidence": 0.95,
        # Encode provenance into session_id so the strict v2.2 schema
        # (`extra: forbid`) accepts the payload without a custom field.
        "session_id": (f"ifl_gcal_{account_id}_{event['id']}_{session_id}"),
        "conversation_turn": 0,
        "language": "en",
    }


def normalize_response(
    response: dict[str, Any],
    *,
    account_id: str,
    session_id: str,
) -> list[dict[str, Any]]:
    """Normalize the full adapter response (``{"events": [...]}``)
    into a list of MemoryAtom payloads."""
    if not isinstance(response, dict):
        raise TypeError("response must be a dict")
    events: Iterable[dict[str, Any]] = response.get("events") or []
    return [normalize_event(ev, account_id=account_id, session_id=session_id) for ev in events]
