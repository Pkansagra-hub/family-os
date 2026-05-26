"""Idempotency helpers for section-update plans."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any


def stable_json(value: Any) -> str:
    """Return deterministic JSON for hashing/idempotency."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def operation_hash(section: str, operation: str, data: Any) -> str:
    """Hash the mutation target and payload."""

    payload = {"section": section, "operation": operation, "data": data}
    return hashlib.sha256(stable_json(payload).encode("utf-8")).hexdigest()[:24]


def build_plan_idempotency_key(
    *,
    session_id: str,
    turn_id: str,
    snapshot_version: str,
    classifier_version: str,
) -> str:
    """Build the stable plan key defined by M1."""

    return f"{session_id}:{turn_id}:{snapshot_version}:{classifier_version}"


def build_mutation_idempotency_key(
    *,
    plan_idempotency_key: str,
    index: int,
    section: str,
    operation: str,
    data: Any,
) -> str:
    """Build a stable per-mutation key under a plan key."""

    return f"{plan_idempotency_key}:{index}:{operation_hash(section, operation, data)}"


@dataclass(frozen=True)
class IdempotencyRecord:
    """Cached compile/apply decision for a plan key."""

    key: str
    status: str
    plan_id: str
    result_summary: dict[str, Any] = field(default_factory=dict)
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))


class SectionUpdateIdempotencyStore:
    """Small in-memory idempotency store for M1 tests and M2 handoff."""

    def __init__(self) -> None:
        self._records: dict[str, IdempotencyRecord] = {}

    def get(self, key: str) -> IdempotencyRecord | None:
        return self._records.get(key)

    def seen(self, key: str) -> bool:
        return key in self._records

    def remember(
        self,
        *,
        key: str,
        status: str,
        plan_id: str,
        result_summary: dict[str, Any] | None = None,
    ) -> IdempotencyRecord:
        record = IdempotencyRecord(
            key=key,
            status=status,
            plan_id=plan_id,
            result_summary=dict(result_summary or {}),
        )
        self._records[key] = record
        return record

    def clear(self) -> None:
        self._records.clear()

    def __len__(self) -> int:
        return len(self._records)
