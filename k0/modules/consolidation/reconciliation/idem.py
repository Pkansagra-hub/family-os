"""RouterIdempotencyKey -- deterministic key gen for router writes (M9.5).

Produces ``p03:reconcile:`` prefixed keys that are collision-free with
existing ``p03:write:`` keys from IdempotencyKeyGenerator.
"""

from __future__ import annotations

import hashlib


class RouterIdempotencyKey:
    """Deterministic idempotency key generation for router-produced StagedWrites."""

    @staticmethod
    def for_write(
        cycle_id: str,
        layer: str,
        record_id: str,
        action_suffix: str,
    ) -> str:
        """Generate idempotency key for a single write.

        Args:
            cycle_id: P03 cycle ULID (26 chars).
            layer: Truth layer name (st_epi, st_sem, etc.).
            record_id: Target record PK.
            action_suffix: One of create, reinforce, extend,
                evolve_archive, evolve_create, contradict, prune.
        """
        return f"p03:reconcile:{cycle_id}:{layer}:{record_id}:{action_suffix}"

    @staticmethod
    def for_batch(cycle_id: str, layer: str, event_ids: list[str]) -> str:
        """Idempotency key for batch-level operations."""
        batch_hash = hashlib.sha256(
            "\x00".join(sorted(event_ids)).encode("utf-8"),
        ).hexdigest()[:12]
        return f"p03:reconcile:{cycle_id}:{layer}:batch:{batch_hash}"
