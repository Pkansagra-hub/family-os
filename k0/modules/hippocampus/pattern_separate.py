"""
M01: hippocampus.pattern_separate - DG Pattern Separation (Phase 2)

Computes SimHash (64-bit) and MinHash (32 permutations) fingerprints for episodic events.
Pure function, no shared state, capability-gated via syscalls.

Performance target: ≤15ms P95
Contract: k0/contracts/modules/hippocampus.pattern_separate.v1.yaml
ADR: docs/architecture/decisions-K0/modules/k003.1-dg-pattern-separation.md

Usage (called by PipelineRunner):
    result = await run(message, context, **config)
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


# Module entry point (Phase 2 signature)
async def run(message: Any, context: Any, **config) -> dict[str, Any]:
    """
    Phase 2 module entry point for DG pattern separation.

    Args:
        message: BusMessage with envelope payload
        context: PipelineContext with logger, syscalls, trace_id
        **config: Stage-specific configuration from pipeline YAML

    Returns:
        dict with simhash_hex, minhash32, fingerprint_computed_at_utc

    Raises:
        ValueError: If envelope is malformed or text extraction fails
    """
    # Extract configuration
    hash_seed = config.get("hash_seed", 42)
    minhash_permutations = config.get("minhash_permutations", 32)
    # Note: novelty_threshold in config is not used in P02 (deferred to P03 for neighbor queries)

    # Parse envelope
    try:
        envelope = (
            json.loads(message.payload) if isinstance(message.payload, str) else message.payload
        )
    except (json.JSONDecodeError, AttributeError) as e:
        context.logger.error(
            "Failed to parse envelope payload",
            extra={
                "module": "hippocampus.pattern_separate",
                "error": str(e),
                "trace_id": message.trace_id,
            },
        )
        raise ValueError(f"Invalid envelope payload: {e}")

    # Extract text components for fingerprinting
    text_content = _extract_text_for_fingerprinting(envelope)

    if not text_content:
        context.logger.warning(
            "Empty text content for fingerprinting",
            extra={
                "module": "hippocampus.pattern_separate",
                "event_id": envelope.get("cognitive_trace_id"),
                "trace_id": message.trace_id,
            },
        )
        # Return default fingerprint for empty content
        return {
            "simhash_hex": "0000000000000000",
            "minhash32": json.dumps([0] * minhash_permutations),
            "fingerprint_computed_at_utc": _now_utc_iso(),
        }

    # Compute SimHash (64-bit)
    simhash_hex = _compute_simhash(text_content, hash_seed)

    # Compute MinHash (32 permutations)
    minhash_signature = _compute_minhash(text_content, hash_seed, minhash_permutations)

    # Log completion
    context.logger.info(
        "DG pattern separation complete",
        extra={
            "module": "hippocampus.pattern_separate",
            "simhash_hex": simhash_hex,
            "minhash_perms": len(minhash_signature),
            "trace_id": message.trace_id,
            "event_id": envelope.get("cognitive_trace_id"),
        },
    )

    return {
        "simhash_hex": simhash_hex,
        "minhash32": json.dumps(minhash_signature),  # JSON array for database storage
        "fingerprint_computed_at_utc": _now_utc_iso(),
    }


def _extract_text_for_fingerprinting(envelope: dict[str, Any]) -> str:
    """
    Extract and concatenate text components for fingerprinting.

    Components (in order):
    1. body.text (primary content)
    2. body.participants (social context)
    3. body.location_name (spatial context)
    4. body.activity_type (activity classification)
    5. body.event_time (temporal bucketing by hour)

    Args:
        envelope: Parsed envelope dict

    Returns:
        Concatenated text string for fingerprinting
    """
    body = envelope.get("body", {})
    components = []

    # 1. Text content (primary signal)
    if text := body.get("text"):
        components.append(text.strip().lower())

    # 2. Participants (social context)
    if participants := body.get("participants"):
        if isinstance(participants, list):
            components.extend(sorted(participants))  # Sort for determinism

    # 3. Location (spatial context)
    if location := body.get("location_name"):
        components.append(location.strip().lower())

    # 4. Activity type (activity classification)
    if activity := body.get("activity_type"):
        components.append(activity.strip().lower())

    # 5. Event time (hour-level bucketing for temporal similarity)
    if event_time := body.get("event_time"):
        try:
            # Extract hour bucket (e.g., "2025-11-16T18:00:00Z" -> "2025-11-16T18")
            dt = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
            hour_bucket = dt.strftime("%Y-%m-%dT%H")
            components.append(hour_bucket)
        except (ValueError, AttributeError):
            pass  # Skip if invalid timestamp

    return " ".join(components)


def _compute_simhash(text: str, seed: int = 42) -> str:
    """
    Compute 64-bit SimHash using Charikar's algorithm.

    Algorithm:
    1. Generate 3-gram shingles from text
    2. For each shingle, compute SHA-256 hash
    3. Build 64-bit vector: +1 if bit set, -1 if unset
    4. Threshold: fingerprint[i] = 1 if vector[i] > 0

    Args:
        text: Input text (already normalized/lowercased)
        seed: Random seed for reproducibility (default: 42)

    Returns:
        16-character hex string representing 64-bit fingerprint

    Performance:
        <10ms for typical event text (~500 chars)
    """
    shingles = _generate_shingles(text, k=3)

    if not shingles:
        return "0000000000000000"

    # Initialize 64-bit vector
    bit_vector = [0] * 64

    # Hash each shingle and update bit vector
    for shingle in shingles:
        # Use SHA-256 for stable hashing (seeded for reproducibility)
        h = hashlib.sha256(f"{seed}:{shingle}".encode()).digest()
        hash_int = int.from_bytes(h[:8], byteorder="big")  # Use first 64 bits

        for i in range(64):
            if hash_int & (1 << i):
                bit_vector[i] += 1
            else:
                bit_vector[i] -= 1

    # Threshold to create fingerprint
    fingerprint = 0
    for i in range(64):
        if bit_vector[i] > 0:
            fingerprint |= 1 << i

    return f"{fingerprint:016x}"


def _compute_minhash(text: str, seed: int = 42, num_perms: int = 32) -> list[int]:
    """
    Compute MinHash signature using Broder's algorithm.

    Algorithm:
    1. Generate 3-gram shingles from text
    2. For each of k permutations:
       - Hash each shingle with permutation seed
       - Take minimum hash value
    3. Return signature as list of k integers

    Args:
        text: Input text (already normalized/lowercased)
        seed: Random seed for reproducibility (default: 42)
        num_perms: Number of hash permutations (default: 32)

    Returns:
        List of num_perms integers (MinHash signature)

    Performance:
        <5ms for 32 permutations on typical text
    """
    shingles = _generate_shingles(text, k=3)

    if not shingles:
        return [0] * num_perms

    signature = []

    for perm_idx in range(num_perms):
        min_hash = float("inf")

        for shingle in shingles:
            # Hash with permutation index for unique hash family
            h = hashlib.sha256(f"{seed}:{perm_idx}:{shingle}".encode()).digest()
            hash_val = int.from_bytes(h[:8], byteorder="big", signed=False)
            min_hash = min(min_hash, hash_val)

        # Store as signed 64-bit integer (PostgreSQL BIGINT compatible)
        signature.append(int(min_hash) if min_hash != float("inf") else 0)

    return signature


def _generate_shingles(text: str, k: int = 3) -> set[str]:
    """
    Generate k-gram word shingles from text.

    Args:
        text: Input text (space-separated words)
        k: Shingle size (default: 3-grams)

    Returns:
        Set of k-gram strings

    Example:
        "hello world foo" with k=2 -> {"hello world", "world foo"}
    """
    words = text.split()

    if len(words) < k:
        # If text shorter than k, return as single shingle
        return {text} if text else set()

    shingles = set()
    for i in range(len(words) - k + 1):
        shingle = " ".join(words[i : i + k])
        shingles.add(shingle)

    return shingles


def _now_utc_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()
