"""Simple debug audit trail for P03 consolidation.

This is for DEBUGGING and EXPLAINABILITY, not compliance.
On-device deployment doesn't need GDPR audit logs - this is YOUR data.

Use cases:
- Debug why a memory was consolidated a certain way
- Explain P03 decisions to users
- Track consolidation performance over time
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class AuditAction(str, Enum):
    """Actions tracked in audit trail."""

    # Consolidation actions
    CONSOLIDATE = "CONSOLIDATE"
    LINK = "LINK"
    MERGE = "MERGE"
    PRUNE = "PRUNE"
    ARCHIVE = "ARCHIVE"

    # Learning actions
    WEIGHT_UPDATE = "WEIGHT_UPDATE"
    DECAY_ADJUST = "DECAY_ADJUST"

    # User actions
    RESURRECT = "RESURRECT"  # User brought back pruned memory
    FEEDBACK = "FEEDBACK"  # User gave feedback


@dataclass
class AuditEntry:
    """Single audit trail entry."""

    action: AuditAction
    entity_id: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for logging/storage."""
        return {
            "action": self.action.value,
            "entity_id": self.entity_id,
            "details": self.details,
            "timestamp_ms": self.timestamp_ms,
        }


class P03AuditTrail:
    """Simple in-memory audit trail for debugging.

    Not persisted - just for current session debugging.
    For persistent audit, use st_consolidation_audit table.
    """

    def __init__(self, max_entries: int = 1000) -> None:
        self._entries: list[AuditEntry] = []
        self._max_entries = max_entries

    def log(
        self,
        action: AuditAction,
        entity_id: str,
        **details: Any,
    ) -> None:
        """Log an audit entry.

        Args:
            action: What action was taken
            entity_id: What entity was affected
            **details: Additional context
        """
        entry = AuditEntry(
            action=action,
            entity_id=entity_id,
            details=details,
        )
        self._entries.append(entry)

        # Keep bounded
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries :]

        # Also log via standard logger for debugging
        logger.debug(
            "P03 audit: %s on %s",
            action.value,
            entity_id,
            extra={"audit": entry.to_dict()},
        )

    def log_consolidation(
        self,
        entity_id: str,
        source_events: list[str],
        formula: str,
        confidence: float,
    ) -> None:
        """Log a consolidation action."""
        self.log(
            AuditAction.CONSOLIDATE,
            entity_id,
            source_events=source_events,
            formula=formula,
            confidence=confidence,
        )

    def log_link(
        self,
        source_id: str,
        target_id: str,
        link_type: str,
        score: float,
    ) -> None:
        """Log a linking action."""
        self.log(
            AuditAction.LINK,
            source_id,
            target_id=target_id,
            link_type=link_type,
            score=score,
        )

    def log_prune(
        self,
        entity_id: str,
        reason: str,
        decay_factor: float,
    ) -> None:
        """Log a pruning action."""
        self.log(
            AuditAction.PRUNE,
            entity_id,
            reason=reason,
            decay_factor=decay_factor,
        )

    def get_recent(self, n: int = 10) -> list[AuditEntry]:
        """Get n most recent entries."""
        return self._entries[-n:]

    def get_for_entity(self, entity_id: str) -> list[AuditEntry]:
        """Get all entries for an entity."""
        return [e for e in self._entries if e.entity_id == entity_id]

    def explain_decision(self, entity_id: str) -> str:
        """Generate human-readable explanation for entity decisions.

        Args:
            entity_id: Entity to explain

        Returns:
            Human-readable explanation
        """
        entries = self.get_for_entity(entity_id)
        if not entries:
            return f"No audit trail for {entity_id}"

        lines = [f"Decision trail for {entity_id}:"]
        for entry in entries:
            ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(entry.timestamp_ms / 1000))
            lines.append(f"  [{ts}] {entry.action.value}: {entry.details}")

        return "\n".join(lines)

    def clear(self) -> None:
        """Clear audit trail."""
        self._entries.clear()

    @property
    def count(self) -> int:
        """Number of entries in trail."""
        return len(self._entries)


# Global instance for current session
_audit_trail: P03AuditTrail | None = None


def get_audit_trail() -> P03AuditTrail:
    """Get global audit trail instance."""
    global _audit_trail
    if _audit_trail is None:
        _audit_trail = P03AuditTrail()
    return _audit_trail


def log_audit(
    action: AuditAction,
    entity_id: str,
    **details: Any,
) -> None:
    """Convenience function to log to global audit trail."""
    get_audit_trail().log(action, entity_id, **details)
