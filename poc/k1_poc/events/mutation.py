"""
poc.k1_poc.events.mutation -- V3 canonical mutation audit events.

M4 E4.5.4: TurnMutationSummaryEvent captures per-turn mutation statistics
from DirectWriterAdapter. Appended to the ledger at turn completion for
observability, adaptive policy, and crash recovery.

Topic mapping: emitted via ledger, not bus (no transport topic needed).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from poc.k1_poc.events.base import CanonicalEventMeta


@dataclass
class TurnMutationSummary(CanonicalEventMeta):
    """Per-turn mutation audit summary.

    Emitted at turn completion with aggregate mutation statistics
    from the DirectWriterAdapter.

    Attributes:
        turn_number:       The turn this summary covers.
        approved_count:    Mutations applied in this turn.
        rejected_count:    Mutations rejected in this turn.
        failed_count:      Mutations that failed (exception) in this turn.
        by_section:        Dict of section_name -> {approved, rejected} counts.
        by_rejection_reason: Dict of reason_string -> count.
        total_bytes_delta: Net bytes change across all approved mutations.
        total_duration_ms: Sum of mutation processing time in this turn.
    """

    event_type: str = field(default="mutation.turn_summary", init=False)
    turn_number: int = 0
    approved_count: int = 0
    rejected_count: int = 0
    failed_count: int = 0
    by_section: dict[str, Any] = field(default_factory=dict)
    by_rejection_reason: dict[str, int] = field(default_factory=dict)
    total_bytes_delta: int = 0
    total_duration_ms: float = 0.0
    device_id: str | None = None  # M5 E5.5.6: device that triggered the turn

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["turn_number"] = self.turn_number
        d["approved_count"] = self.approved_count
        d["rejected_count"] = self.rejected_count
        d["failed_count"] = self.failed_count
        d["by_section"] = self.by_section
        d["by_rejection_reason"] = self.by_rejection_reason
        d["total_bytes_delta"] = self.total_bytes_delta
        d["total_duration_ms"] = self.total_duration_ms
        if self.device_id is not None:
            d["device_id"] = self.device_id
        else:
            d.pop("device_id", None)
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> TurnMutationSummary:
        return cls(
            event_id=data.get("event_id", ""),
            session_id=data.get("session_id", ""),
            correlation_id=data.get("correlation_id", ""),
            causation_id=data.get("causation_id", ""),
            parent_event_id=data.get("parent_event_id", ""),
            task_id=data.get("task_id", ""),
            actor=data.get("actor", ""),
            ts_utc=data.get("ts_utc", ""),
            priority=data.get("priority", 1),
            payload_schema_version=data.get("payload_schema_version", "1.0.0"),
            turn_number=data.get("turn_number", 0),
            approved_count=data.get("approved_count", 0),
            rejected_count=data.get("rejected_count", 0),
            failed_count=data.get("failed_count", 0),
            by_section=data.get("by_section", {}),
            by_rejection_reason=data.get("by_rejection_reason", {}),
            total_bytes_delta=data.get("total_bytes_delta", 0),
            total_duration_ms=data.get("total_duration_ms", 0.0),
            device_id=data.get("device_id"),
        )


__all__ = ["TurnMutationSummary"]
