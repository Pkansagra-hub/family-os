"""
poc.k1_poc.events.validator -- V3 event schema validation infrastructure.

M1 E1.3.1: Runtime validator for canonical event payloads.

Provides:
    EVENT_SCHEMA_REGISTRY  -- maps event_type string to canonical class
                              (delegates to events.registry.EVENT_TYPE_REGISTRY)
    validate_event         -- validates payload has required canonical + type-specific fields
    validate_event_chain   -- validates causation chain integrity

The existing ``validate_canonical_metadata()`` in ``events.base`` checks that
the 8 REQUIRED canonical fields are present and non-empty.  This validator
adds type-specific field validation (each subclass has domain fields beyond
the base) and causation chain integrity checking.

Usage::

    from poc.k1_poc.events.validator import validate_event, validate_event_chain

    ok, errors = validate_event(payload_dict)
    ok, errors = validate_event_chain([evt1, evt2, evt3])
"""

from __future__ import annotations

import dataclasses
from typing import Any

from poc.k1_poc.events.base import CanonicalEventMeta, validate_canonical_metadata
from poc.k1_poc.events.registry import EVENT_TYPE_REGISTRY

# Re-export the existing registry under the milestone-specified name.
# This avoids duplication: EVENT_SCHEMA_REGISTRY IS EVENT_TYPE_REGISTRY.
EVENT_SCHEMA_REGISTRY: dict[str, type[CanonicalEventMeta]] = EVENT_TYPE_REGISTRY


def _get_type_specific_fields(cls: type[CanonicalEventMeta]) -> frozenset[str]:
    """Return the set of field names that a subclass adds beyond CanonicalEventMeta.

    Uses dataclass introspection so this stays in sync with the actual
    class definitions without manual maintenance.
    """
    base_fields = {f.name for f in dataclasses.fields(CanonicalEventMeta)}
    all_fields = {f.name for f in dataclasses.fields(cls)}
    return frozenset(all_fields - base_fields)


def validate_event(payload: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate that a payload dict conforms to its canonical event schema.

    Performs two layers of validation:
        1. Canonical metadata validation (delegates to ``validate_canonical_metadata``).
        2. Type-specific field presence (checks that all domain fields declared
           on the canonical dataclass are present in the payload).

    Args:
        payload: Dict to validate.  Must contain at least an ``event_type`` field.

    Returns:
        Tuple of (is_valid, list_of_error_messages).
    """
    errors: list[str] = []

    # Layer 1: canonical metadata
    meta_ok, meta_errors = validate_canonical_metadata(payload)
    errors.extend(meta_errors)

    # Resolve event_type -> class
    event_type = payload.get("event_type", "")
    if not event_type:
        errors.append("Missing or empty event_type field")
        return (len(errors) == 0, errors)

    cls = EVENT_SCHEMA_REGISTRY.get(event_type)
    if cls is None:
        errors.append(f"Unknown event_type: {event_type}")
        return (len(errors) == 0, errors)

    # Layer 2: type-specific field presence
    required_domain_fields = _get_type_specific_fields(cls)
    for field_name in sorted(required_domain_fields):
        if field_name not in payload:
            errors.append(
                f"Missing type-specific field '{field_name}' " f"for event_type '{event_type}'"
            )

    return (len(errors) == 0, errors)


def validate_event_chain(
    events: list[dict[str, Any]],
) -> tuple[bool, list[str]]:
    """Validate causation chain integrity across a list of event payloads.

    Checks:
        1. Every event has an ``event_id``.
        2. For every event with a non-empty ``causation_id``, the referenced
           event_id must exist earlier in the chain (or be a root/external ref).
        3. No duplicate ``event_id`` values.

    Root events (those with empty ``causation_id``) are always valid.

    Args:
        events: Ordered list of event payload dicts.

    Returns:
        Tuple of (is_valid, list_of_error_messages).
    """
    errors: list[str] = []
    seen_ids: set[str] = set()

    for idx, evt in enumerate(events):
        event_id = evt.get("event_id", "")
        if not event_id:
            errors.append(f"Event at index {idx} has no event_id")
            continue

        if event_id in seen_ids:
            errors.append(f"Duplicate event_id '{event_id}' at index {idx}")
        seen_ids.add(event_id)

        causation_id = evt.get("causation_id", "")
        if causation_id and causation_id not in seen_ids:
            errors.append(
                f"Event '{event_id}' at index {idx} references "
                f"causation_id '{causation_id}' which is not in the chain"
            )

    return (len(errors) == 0, errors)


__all__ = [
    "EVENT_SCHEMA_REGISTRY",
    "validate_event",
    "validate_event_chain",
]
