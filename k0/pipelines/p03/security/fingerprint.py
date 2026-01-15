"""Content fingerprinting for deduplication.

Secure hashing for detecting duplicate content on device.
Uses SHA-256 for content fingerprinting to:
- Avoid storing duplicate memories
- Detect near-duplicate content for consolidation
- Save device storage space
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContentFingerprint:
    """Fingerprint of content for deduplication."""

    hash: str  # SHA-256 hex digest
    content_type: str  # Type of content fingerprinted
    length: int  # Original content length


def fingerprint_text(text: str) -> ContentFingerprint:
    """Create fingerprint for text content.

    Args:
        text: Text to fingerprint

    Returns:
        ContentFingerprint with SHA-256 hash
    """
    # Normalize: lowercase, strip whitespace
    normalized = text.lower().strip()
    content_bytes = normalized.encode("utf-8")

    return ContentFingerprint(
        hash=hashlib.sha256(content_bytes).hexdigest(),
        content_type="text",
        length=len(content_bytes),
    )


def fingerprint_structured(data: dict[str, Any]) -> ContentFingerprint:
    """Create fingerprint for structured data.

    Args:
        data: Dict to fingerprint

    Returns:
        ContentFingerprint with SHA-256 hash
    """
    # Sort keys for consistent hashing
    json_bytes = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")

    return ContentFingerprint(
        hash=hashlib.sha256(json_bytes).hexdigest(),
        content_type="structured",
        length=len(json_bytes),
    )


def fingerprint_event(
    event_type: str,
    content: str,
    *,
    actor_id: str | None = None,
    timestamp_ms: int | None = None,
) -> ContentFingerprint:
    """Create fingerprint for an event.

    Combines event type, content, and optional metadata for
    comprehensive duplicate detection.

    Args:
        event_type: Type of event
        content: Event content
        actor_id: Optional actor identifier
        timestamp_ms: Optional timestamp (excluded from hash for same-content detection)

    Returns:
        ContentFingerprint for the event
    """
    # Build canonical representation
    parts = [
        f"type:{event_type}",
        f"content:{content.lower().strip()}",
    ]
    if actor_id:
        parts.append(f"actor:{actor_id}")

    canonical = "|".join(parts)
    content_bytes = canonical.encode("utf-8")

    return ContentFingerprint(
        hash=hashlib.sha256(content_bytes).hexdigest(),
        content_type="event",
        length=len(content_bytes),
    )


def fingerprint_memory(
    entity_type: str,
    canonical_name: str,
    layer: str,
) -> ContentFingerprint:
    """Create fingerprint for a memory entity.

    Used to detect duplicate entities during consolidation.

    Args:
        entity_type: Type of entity (PERSON, PLACE, etc.)
        canonical_name: Canonical name of entity
        layer: Memory layer (st_epi, st_sem, etc.)

    Returns:
        ContentFingerprint for the memory
    """
    canonical = f"{entity_type}|{canonical_name.lower().strip()}|{layer}"
    content_bytes = canonical.encode("utf-8")

    return ContentFingerprint(
        hash=hashlib.sha256(content_bytes).hexdigest(),
        content_type="memory",
        length=len(content_bytes),
    )


class DuplicateDetector:
    """Detect duplicate content using fingerprints.

    Simple in-memory set for batch processing.
    For persistent dedup, query fingerprint column in database.
    """

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def is_duplicate(self, fingerprint: ContentFingerprint) -> bool:
        """Check if content is a duplicate.

        Args:
            fingerprint: Fingerprint to check

        Returns:
            True if already seen, False if new
        """
        if fingerprint.hash in self._seen:
            return True
        self._seen.add(fingerprint.hash)
        return False

    def reset(self) -> None:
        """Clear seen fingerprints."""
        self._seen.clear()

    @property
    def count(self) -> int:
        """Number of unique fingerprints seen."""
        return len(self._seen)


async def deduplicate_events(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Remove duplicate events from a list.

    Args:
        events: List of event dicts

    Returns:
        Deduplicated list (preserves first occurrence)
    """
    detector = DuplicateDetector()
    unique: list[dict[str, Any]] = []

    for event in events:
        fp = fingerprint_event(
            event_type=event.get("event_type", "unknown"),
            content=event.get("content", ""),
            actor_id=event.get("actor_id"),
        )
        if not detector.is_duplicate(fp):
            unique.append(event)

    if len(events) != len(unique):
        logger.info(
            "Deduplicated events",
            extra={
                "original_count": len(events),
                "unique_count": len(unique),
                "duplicates_removed": len(events) - len(unique),
            },
        )

    return unique
