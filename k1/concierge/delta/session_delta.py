"""
k1.concierge.delta.session_delta -- SessionDelta dataclass for SS mutations.

V2 Design Ref: Section 5 (DeltaAggregator, session delta structure)
V2 Design Ref: Section 5, DeltaAggregator Write Pipeline

A single mutation destined for a SessionState section.  Back emits
these as bus events.  DeltaAggregator collects them in 500ms windows
and forwards to FSM.apply_deltas().

Section ownership (V2 Section 5, Single Writer Invariant):
    task_state      -- FSM via DeltaAggregator from Back bus events
    task_artifacts  -- FSM via DeltaAggregator from k1.session.artifact.created.v1
    history_active  -- FSM at turn boundary events (append-only)
    control         -- FSM state transitions + Phase 1 writes
    meta            -- FSM at turn end

Mutation operations:
    set    -- overwrite key unconditionally
    append -- add to list-valued key
    update -- merge into dict-valued key
    delete -- remove key

Deduplication:
    Within a 500ms batch window, multiple deltas targeting the same
    section+key are deduplicated (last-write-wins) via dedup_key().

Causal ordering:
    parent_delta_id links child deltas to their causal parent.
    The aggregator orders parents before children in each batch.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

# =========================================================================
# Valid sections and operations (V2 Section 5, Read/Write Matrix)
# =========================================================================

VALID_DELTA_SECTIONS: frozenset[str] = frozenset(
    {
        "task_state",
        "task_artifacts",
        "history_active",
        "control",
        "meta",
    }
)

VALID_DELTA_OPERATIONS: frozenset[str] = frozenset(
    {
        "set",
        "append",
        "update",
        "delete",
    }
)


@dataclass
class SessionDelta:
    """A single mutation destined for a SessionState section.

    Back emits these as bus events.  DeltaAggregator collects them
    in 500ms windows and forwards to FSM.apply_deltas().

    Attributes:
        section:         Target SS section name.
        key:             Sub-key within the section (e.g., task_id for task_state).
        operation:       Mutation type: "set", "append", "update", "delete".
        data:            The payload to write.
        delta_id:        Unique delta identifier (auto-generated).
        source_task_id:  Originating task ID (for causal ordering).
        parent_delta_id: Causal parent delta (for ordering within a batch).
        timestamp_ns:    Monotonic timestamp when delta was created.
    """

    section: str
    key: str
    operation: str
    data: dict[str, Any]
    delta_id: str = field(default_factory=lambda: f"delta-{uuid.uuid4().hex[:8]}")
    source_task_id: str | None = None
    parent_delta_id: str | None = None
    timestamp_ns: int = 0

    def __post_init__(self) -> None:
        if self.section not in VALID_DELTA_SECTIONS:
            raise ValueError(
                f"SessionDelta.section must be one of "
                f"{sorted(VALID_DELTA_SECTIONS)}, got '{self.section}'"
            )
        if self.operation not in VALID_DELTA_OPERATIONS:
            raise ValueError(
                f"SessionDelta.operation must be one of "
                f"{sorted(VALID_DELTA_OPERATIONS)}, got '{self.operation}'"
            )

    def dedup_key(self) -> str:
        """Key for deduplication within a batch window: section + key.

        Two deltas with the same dedup_key() target the same SS entry.
        Within a batch, last-write-wins deduplication keeps only the
        final delta for each dedup_key.
        """
        return f"{self.section}:{self.key}"

    def to_payload(self) -> bytes:
        """Serialize to JSON bytes for bus envelope payload."""
        return json.dumps(self.to_dict(), separators=(",", ":")).encode("utf-8")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict.

        Only includes non-default optional fields to minimize payload.
        """
        d: dict[str, Any] = {
            "delta_id": self.delta_id,
            "section": self.section,
            "key": self.key,
            "operation": self.operation,
            "data": self.data,
        }
        if self.source_task_id is not None:
            d["source_task_id"] = self.source_task_id
        if self.parent_delta_id is not None:
            d["parent_delta_id"] = self.parent_delta_id
        if self.timestamp_ns != 0:
            d["timestamp_ns"] = self.timestamp_ns
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionDelta:
        """Deserialize from dict."""
        return cls(
            delta_id=data.get("delta_id", f"delta-{uuid.uuid4().hex[:8]}"),
            section=data["section"],
            key=data["key"],
            operation=data["operation"],
            data=data["data"],
            source_task_id=data.get("source_task_id"),
            parent_delta_id=data.get("parent_delta_id"),
            timestamp_ns=data.get("timestamp_ns", 0),
        )

    @classmethod
    def from_payload(cls, payload: bytes) -> SessionDelta:
        """Deserialize from bus envelope payload bytes."""
        return cls.from_dict(json.loads(payload.decode("utf-8")))
