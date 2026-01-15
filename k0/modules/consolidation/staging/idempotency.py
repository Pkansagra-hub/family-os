"""
IdempotencyKeyGenerator — Deterministic idempotency key generation for R6.

Generates deterministic, unique idempotency keys following dossier format
for all R6 staged writes, R7 truth writes, and R8 event emissions.

Issue: 5.1.5
Spec Reference:
    - Dossier §12.2.3 (Idempotency Key Design)
    - Dossier Appendix G (R0-R8 State Machine Specification)
    - M5_EXECUTION.md Issue 5.1.5

Key Formats:
    - R6 event update: p03:staging:{cycle_ulid}:{event_id}
    - R7 truth write: p03:write:{cycle_ulid}:{table}:{record_id}
    - R8 event emit: p03:emit:{cycle_ulid}:{topic}:{offset}
    - Batch phase: p03:{phase}:{cycle_ulid}:{batch_hash}

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

# =============================================================================
# Constants
# =============================================================================

# Key format patterns for validation
KEY_PATTERNS = {
    "staging": re.compile(r"^p03:staging:([A-Za-z0-9]{26}):(.+)$"),
    "write": re.compile(r"^p03:write:([A-Za-z0-9]{26}):([a-z_]+):(.+)$"),
    "emit": re.compile(r"^p03:emit:([A-Za-z0-9]{26}):([a-zA-Z0-9_.]+):(.+)$"),
    "phase": re.compile(r"^p03:(R[0-8]|r[0-8]):([A-Za-z0-9]{26}):([a-f0-9]{12})$"),
}

# Maximum key length (reasonable for storage)
MAX_KEY_LENGTH = 200

# Batch hash length (SHA-256 truncated)
BATCH_HASH_LENGTH = 12


# =============================================================================
# ParsedKey Dataclass
# =============================================================================


@dataclass
class ParsedKey:
    """
    Parsed idempotency key components.

    Attributes:
        pipeline: Always "p03"
        key_type: "staging", "write", "emit", or phase name
        cycle_ulid: The cycle ULID
        entity_id: Event ID, record ID, or batch hash
        extra: Additional component (table name, topic, offset, etc.)
    """

    pipeline: str
    key_type: str
    cycle_ulid: str
    entity_id: str
    extra: Optional[str] = None


# =============================================================================
# IdempotencyKeyGenerator Class
# =============================================================================


class IdempotencyKeyGenerator:
    """
    Generates deterministic idempotency keys for P03 pipeline operations.

    All keys include the cycle_ulid to ensure uniqueness across cycles.
    Keys are deterministic: same inputs always produce the same key.

    Usage:
        gen = IdempotencyKeyGenerator(cycle_ulid="01HXYZ123456789ABCDEFGHJ")

        # R6: Event status update
        key = gen.for_event_update("evt_001")
        # => "p03:staging:01HXYZ123456789ABCDEFGHJ:evt_001"

        # R7: Truth layer write
        key = gen.for_truth_write("st_epi", "epi-001")
        # => "p03:write:01HXYZ123456789ABCDEFGHJ:st_epi:epi-001"

        # R8: Outbox event
        key = gen.for_event_emit("p03.pattern.detected.v1", 42)
        # => "p03:emit:01HXYZ123456789ABCDEFGHJ:p03.pattern.detected.v1:42"
    """

    def __init__(self, cycle_ulid: str) -> None:
        """
        Initialize the generator with a cycle ULID.

        Args:
            cycle_ulid: The ULID for this consolidation cycle

        Raises:
            ValueError: If cycle_ulid is invalid
        """
        if not cycle_ulid:
            raise ValueError("cycle_ulid is required")
        if len(cycle_ulid) != 26:
            raise ValueError(f"Invalid ULID length: {len(cycle_ulid)} (expected 26)")

        self.cycle_ulid = cycle_ulid

    def for_event_update(self, event_id: str) -> str:
        """
        Generate key for st_hipp_events update in R6.

        Format: p03:staging:{cycle_ulid}:{event_id}

        Args:
            event_id: The event being updated

        Returns:
            Idempotency key string
        """
        if not event_id:
            raise ValueError("event_id is required")

        return f"p03:staging:{self.cycle_ulid}:{event_id}"

    def for_truth_write(self, table: str, record_id: str) -> str:
        """
        Generate key for truth layer write in R7.

        Format: p03:write:{cycle_ulid}:{table}:{record_id}

        Args:
            table: Target table (st_epi, st_sem, st_vec, etc.)
            record_id: Primary key of the record

        Returns:
            Idempotency key string
        """
        if not table:
            raise ValueError("table is required")
        if not record_id:
            raise ValueError("record_id is required")

        return f"p03:write:{self.cycle_ulid}:{table}:{record_id}"

    def for_event_emit(self, topic: str, offset: int) -> str:
        """
        Generate key for outbox event in R8.

        Format: p03:emit:{cycle_ulid}:{topic}:{offset}

        Args:
            topic: Event topic name
            offset: Sequence offset within cycle

        Returns:
            Idempotency key string
        """
        if not topic:
            raise ValueError("topic is required")
        if offset < 0:
            raise ValueError("offset must be non-negative")

        return f"p03:emit:{self.cycle_ulid}:{topic}:{offset}"

    def for_batch_phase(self, phase: str, event_ids: List[str]) -> str:
        """
        Generate key for R1-R5 phase processing.

        Format: p03:{phase}:{cycle_ulid}:{batch_hash}

        The batch_hash is a deterministic hash of the sorted event IDs,
        ensuring the key is stable regardless of processing order.

        Args:
            phase: Phase name (R1, R2, R3, R4, R5)
            event_ids: List of event IDs in the batch

        Returns:
            Idempotency key string
        """
        if not phase:
            raise ValueError("phase is required")
        if not event_ids:
            raise ValueError("event_ids is required")

        batch_hash = self.compute_batch_hash(event_ids)
        return f"p03:{phase}:{self.cycle_ulid}:{batch_hash}"

    def for_outbox_event(
        self,
        topic: str,
        event_id: str,
        sequence: int = 0,
    ) -> str:
        """
        Generate key for a specific outbox event tied to source event.

        Format: p03:emit:{cycle_ulid}:{topic}:{event_id}:{sequence}

        Args:
            topic: Event topic name
            event_id: Source event that triggered this emission
            sequence: Sequence number if multiple events per source

        Returns:
            Idempotency key string
        """
        if sequence == 0:
            return f"p03:emit:{self.cycle_ulid}:{topic}:{event_id}"
        return f"p03:emit:{self.cycle_ulid}:{topic}:{event_id}:{sequence}"

    @staticmethod
    def compute_batch_hash(event_ids: List[str]) -> str:
        """
        Compute deterministic hash of event ID list.

        The hash is stable regardless of input order (sorted internally).
        Uses SHA-256 truncated to 12 hex characters.

        Args:
            event_ids: List of event IDs

        Returns:
            12-character hex hash string
        """
        # Sort for determinism
        sorted_ids = sorted(event_ids)
        # Join with null separator (unlikely in event IDs)
        combined = "\x00".join(sorted_ids)
        # SHA-256 and truncate
        hash_bytes = hashlib.sha256(combined.encode("utf-8")).hexdigest()
        return hash_bytes[:BATCH_HASH_LENGTH]


# =============================================================================
# Key Parsing and Validation
# =============================================================================


def parse_idempotency_key(key: str) -> Optional[ParsedKey]:
    """
    Parse an idempotency key into components.

    Args:
        key: Idempotency key string

    Returns:
        ParsedKey if valid, None if invalid
    """
    if not key or not key.startswith("p03:"):
        return None

    parts = key.split(":", 3)
    if len(parts) < 3:
        return None

    pipeline, key_type = parts[0], parts[1]

    if key_type == "staging":
        match = KEY_PATTERNS["staging"].match(key)
        if match:
            return ParsedKey(
                pipeline=pipeline,
                key_type=key_type,
                cycle_ulid=match.group(1),
                entity_id=match.group(2),
            )

    elif key_type == "write":
        match = KEY_PATTERNS["write"].match(key)
        if match:
            return ParsedKey(
                pipeline=pipeline,
                key_type=key_type,
                cycle_ulid=match.group(1),
                entity_id=match.group(3),
                extra=match.group(2),  # table name
            )

    elif key_type == "emit":
        match = KEY_PATTERNS["emit"].match(key)
        if match:
            return ParsedKey(
                pipeline=pipeline,
                key_type=key_type,
                cycle_ulid=match.group(1),
                entity_id=match.group(3),  # offset
                extra=match.group(2),  # topic
            )

    elif key_type.upper().startswith("R"):
        match = KEY_PATTERNS["phase"].match(key)
        if match:
            return ParsedKey(
                pipeline=pipeline,
                key_type=match.group(1),
                cycle_ulid=match.group(2),
                entity_id=match.group(3),  # batch_hash
            )

    return None


def validate_idempotency_key(key: str) -> Tuple[bool, str]:
    """
    Validate an idempotency key format.

    Args:
        key: Idempotency key to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not key:
        return False, "Key is empty"

    if len(key) > MAX_KEY_LENGTH:
        return False, f"Key exceeds max length ({len(key)} > {MAX_KEY_LENGTH})"

    if not key.startswith("p03:"):
        return False, "Key must start with 'p03:'"

    parsed = parse_idempotency_key(key)
    if not parsed:
        return False, "Key format not recognized"

    return True, ""


def extract_cycle_ulid(key: str) -> Optional[str]:
    """
    Extract cycle ULID from an idempotency key.

    Args:
        key: Idempotency key string

    Returns:
        Cycle ULID if valid key, None otherwise
    """
    parsed = parse_idempotency_key(key)
    return parsed.cycle_ulid if parsed else None


def keys_same_cycle(key1: str, key2: str) -> bool:
    """
    Check if two keys belong to the same cycle.

    Args:
        key1: First idempotency key
        key2: Second idempotency key

    Returns:
        True if both keys have the same cycle_ulid
    """
    ulid1 = extract_cycle_ulid(key1)
    ulid2 = extract_cycle_ulid(key2)
    return ulid1 is not None and ulid1 == ulid2
