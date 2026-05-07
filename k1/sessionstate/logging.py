"""
SessionState Structured Logging
================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 5.3 Tracing & Logging
ISSUE: 5.3.2

PURPOSE:
    Provide structured JSON logging for all SessionState operations.
    All logs include cognitive_trace_id for distributed tracing correlation.

LOG EVENTS (8 types - aligned with event payloads):
    1. mutation.requested - Before preflight check
    2. mutation.approved  - After successful mutation
    3. mutation.rejected  - When preflight rejects mutation
    4. eviction.triggered - When eviction starts
    5. eviction.completed - After eviction completes
    6. emergency.activated - When capacity >90%
    7. emergency.resolved  - When capacity drops below threshold
    8. reconstruction.started - When restoring from COLD

ADDITIONAL LOG EVENTS (lifecycle + operations):
    9. lifecycle.started  - Session started
    10. lifecycle.stopped  - Session stopped
    11. checkpoint.created - Checkpoint saved
    12. checkpoint.restored - Session restored from checkpoint
    13. migration.started  - HOT↔WARM migration started
    14. migration.completed - Migration completed
    15. pressure.changed   - Pressure level transition

FORMAT:
    All logs are JSON with these standard fields:
    - timestamp_iso: ISO 8601 timestamp
    - level: DEBUG, INFO, WARNING, ERROR
    - event: Event type (e.g., "mutation.approved")
    - session_id: Session identifier
    - trace_id: cognitive_trace_id for distributed tracing
    - module: "sessionstate"
    - Additional context fields per event type

ARCHITECTURE DIAGRAMS:
    - k1/sessionstate/sessionstate.mmd (external view)
    - k1/sessionstate/sessionstate_internal.mmd (internal structure)
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, TextIO

# =============================================================================
# LOG EVENT TYPES
# =============================================================================


class LogEventType(str, Enum):
    """All SessionState structured log event types."""

    # Mutation events
    MUTATION_REQUESTED = "mutation.requested"
    MUTATION_APPROVED = "mutation.approved"
    MUTATION_REJECTED = "mutation.rejected"

    # Eviction events
    EVICTION_TRIGGERED = "eviction.triggered"
    EVICTION_COMPLETED = "eviction.completed"

    # Emergency events
    EMERGENCY_ACTIVATED = "emergency.activated"
    EMERGENCY_RESOLVED = "emergency.resolved"

    # Reconstruction events
    RECONSTRUCTION_STARTED = "reconstruction.started"
    RECONSTRUCTION_COMPLETED = "reconstruction.completed"

    # Lifecycle events
    LIFECYCLE_STARTED = "lifecycle.started"
    LIFECYCLE_STOPPED = "lifecycle.stopped"

    # Checkpoint events
    CHECKPOINT_CREATED = "checkpoint.created"
    CHECKPOINT_RESTORED = "checkpoint.restored"

    # Migration events
    MIGRATION_STARTED = "migration.started"
    MIGRATION_COMPLETED = "migration.completed"

    # Pressure events
    PRESSURE_CHANGED = "pressure.changed"


# =============================================================================
# LOG RECORD DATACLASS
# =============================================================================


@dataclass
class StructuredLogRecord:
    """
    Structured log record for JSON serialization.

    Standard fields present in every log:
    - timestamp_iso: ISO 8601 timestamp (UTC)
    - level: Log level (DEBUG, INFO, WARNING, ERROR)
    - event: Event type from LogEventType
    - session_id: Session identifier
    - trace_id: cognitive_trace_id for distributed tracing
    - module: Always "sessionstate"

    Context fields vary by event type.
    """

    event: str
    level: str = "INFO"
    session_id: str = ""
    trace_id: str = ""
    module: str = "sessionstate"
    timestamp_iso: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, flattening context fields."""
        result = {
            "timestamp_iso": self.timestamp_iso,
            "level": self.level,
            "event": self.event,
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "module": self.module,
        }
        # Flatten context into top-level
        result.update(self.context)
        return result

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)


# =============================================================================
# JSON FORMATTER FOR PYTHON LOGGING
# =============================================================================


class SessionStateJsonFormatter(logging.Formatter):
    """
    JSON formatter for Python logging that produces structured logs.

    Usage:
        handler = logging.StreamHandler()
        handler.setFormatter(SessionStateJsonFormatter())
        logger.addHandler(handler)
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        # Extract structured fields if present
        structured: Dict[str, Any] = getattr(record, "structured", {})

        log_dict = {
            "timestamp_iso": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "event": structured.get("event", "log.message"),
            "session_id": structured.get("session_id", ""),
            "trace_id": structured.get("trace_id", ""),
            "module": "sessionstate",
            "message": record.getMessage(),
        }

        # Add context fields
        context = structured.get("context", {})
        log_dict.update(context)

        # Add exception info if present
        if record.exc_info:
            log_dict["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_dict, default=str)


# =============================================================================
# STRUCTURED LOGGER
# =============================================================================


class SessionStateLogger:
    """
    Structured logger for SessionState operations.

    Provides type-safe methods for logging each event type with
    proper context fields. All methods accept session_id and trace_id
    for distributed tracing.

    Usage:
        logger = SessionStateLogger()

        # Log mutation approved
        logger.mutation_approved(
            session_id="sess-123",
            trace_id="trace-456",
            section="beliefs_active",
            operation="append",
            bytes_delta=256,
            new_size_bytes=1024,
            pressure="normal",
        )

        # Log eviction triggered
        logger.eviction_triggered(
            session_id="sess-123",
            trace_id="trace-456",
            tier="warm",
            target_bytes=4096,
            pressure="critical",
            candidates=["telemetry", "beliefs_history"],
        )
    """

    def __init__(
        self,
        name: str = "poc.k1_poc.sessionstate",
        level: int = logging.DEBUG,
        stream: Optional[TextIO] = None,
        use_json_format: bool = True,
    ):
        """
        Initialize structured logger.

        Args:
            name: Logger name
            level: Logging level
            stream: Output stream (default: sys.stdout)
            use_json_format: Whether to use JSON formatting
        """
        self._logger = logging.getLogger(name)
        self._logger.setLevel(level)
        self._use_json_format = use_json_format

        # Only add handler if logger has none
        if not self._logger.handlers:
            handler = logging.StreamHandler(stream or sys.stdout)
            handler.setLevel(level)
            if use_json_format:
                handler.setFormatter(SessionStateJsonFormatter())
            else:
                handler.setFormatter(
                    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
                )
            self._logger.addHandler(handler)

    def _log(
        self,
        level: int,
        event: LogEventType,
        session_id: str,
        trace_id: str,
        message: str,
        **context: Any,
    ) -> None:
        """
        Internal logging method.

        Args:
            level: Log level
            event: Event type
            session_id: Session identifier
            trace_id: cognitive_trace_id
            message: Human-readable message
            **context: Additional context fields
        """
        extra = {
            "structured": {
                "event": event.value,
                "session_id": session_id,
                "trace_id": trace_id,
                "context": context,
            }
        }
        self._logger.log(level, message, extra=extra)

    # =========================================================================
    # MUTATION EVENTS
    # =========================================================================

    def mutation_requested(
        self,
        session_id: str,
        trace_id: str,
        section: str,
        operation: str,
        estimated_bytes: int,
        writer_id: str = "concierge",
    ) -> None:
        """Log mutation requested event (before preflight)."""
        self._log(
            logging.DEBUG,
            LogEventType.MUTATION_REQUESTED,
            session_id,
            trace_id,
            f"Mutation requested: section={section}, op={operation}, "
            f"estimated_bytes={estimated_bytes}",
            section=section,
            operation=operation,
            estimated_bytes=estimated_bytes,
            writer_id=writer_id,
        )

    def mutation_approved(
        self,
        session_id: str,
        trace_id: str,
        section: str,
        operation: str,
        bytes_delta: int,
        new_size_bytes: int,
        tier_utilization_pct: float = 0.0,
        total_utilization_pct: float = 0.0,
        pressure: str = "normal",
    ) -> None:
        """Log mutation approved event (after successful apply)."""
        self._log(
            logging.INFO,
            LogEventType.MUTATION_APPROVED,
            session_id,
            trace_id,
            f"Mutation approved: section={section}, op={operation}, "
            f"delta={bytes_delta}, new_size={new_size_bytes}",
            section=section,
            operation=operation,
            bytes_delta=bytes_delta,
            new_size_bytes=new_size_bytes,
            tier_utilization_pct=tier_utilization_pct,
            total_utilization_pct=total_utilization_pct,
            pressure=pressure,
        )

    def mutation_rejected(
        self,
        session_id: str,
        trace_id: str,
        section: str,
        operation: str,
        reason: str,
        available_bytes: int = 0,
    ) -> None:
        """Log mutation rejected event."""
        self._log(
            logging.WARNING,
            LogEventType.MUTATION_REJECTED,
            session_id,
            trace_id,
            f"Mutation rejected: section={section}, op={operation}, reason={reason}",
            section=section,
            operation=operation,
            reason=reason,
            available_bytes=available_bytes,
        )

    # =========================================================================
    # EVICTION EVENTS
    # =========================================================================

    def eviction_triggered(
        self,
        session_id: str,
        trace_id: str,
        tier: str,
        target_bytes: int,
        pressure: str,
        candidates: List[str],
    ) -> None:
        """Log eviction triggered event."""
        self._log(
            logging.INFO,
            LogEventType.EVICTION_TRIGGERED,
            session_id,
            trace_id,
            f"Eviction triggered: tier={tier}, target={target_bytes}B, "
            f"pressure={pressure}, candidates={candidates}",
            tier=tier,
            target_bytes=target_bytes,
            pressure=pressure,
            candidates=candidates,
        )

    def eviction_completed(
        self,
        session_id: str,
        trace_id: str,
        tier: str,
        sections_evicted: List[str],
        bytes_freed: int,
        bytes_archived: int,
        new_pressure: str,
        duration_ms: float,
    ) -> None:
        """Log eviction completed event."""
        self._log(
            logging.INFO,
            LogEventType.EVICTION_COMPLETED,
            session_id,
            trace_id,
            f"Eviction completed: freed={bytes_freed}B, archived={bytes_archived}B, "
            f"sections={sections_evicted}, duration={duration_ms:.2f}ms",
            tier=tier,
            sections_evicted=sections_evicted,
            bytes_freed=bytes_freed,
            bytes_archived=bytes_archived,
            new_pressure=new_pressure,
            duration_ms=duration_ms,
        )

    # =========================================================================
    # EMERGENCY EVENTS
    # =========================================================================

    def emergency_activated(
        self,
        session_id: str,
        trace_id: str,
        level: str,
        total_size_bytes: int,
        utilization_pct: float,
        writes_blocked: bool = False,
    ) -> None:
        """Log emergency mode activated."""
        log_level = logging.ERROR if level == "critical" else logging.WARNING
        self._log(
            log_level,
            LogEventType.EMERGENCY_ACTIVATED,
            session_id,
            trace_id,
            f"EMERGENCY ACTIVATED: level={level}, size={total_size_bytes}B, "
            f"utilization={utilization_pct:.1f}%, writes_blocked={writes_blocked}",
            emergency_level=level,
            total_size_bytes=total_size_bytes,
            utilization_pct=utilization_pct,
            writes_blocked=writes_blocked,
        )

    def emergency_resolved(
        self,
        session_id: str,
        trace_id: str,
        previous_level: str,
        resolution_method: str,
        new_utilization_pct: float,
        duration_ms: float,
    ) -> None:
        """Log emergency mode resolved."""
        self._log(
            logging.INFO,
            LogEventType.EMERGENCY_RESOLVED,
            session_id,
            trace_id,
            f"Emergency resolved: previous={previous_level}, "
            f"method={resolution_method}, new_util={new_utilization_pct:.1f}%",
            previous_level=previous_level,
            resolution_method=resolution_method,
            new_utilization_pct=new_utilization_pct,
            duration_ms=duration_ms,
        )

    # =========================================================================
    # RECONSTRUCTION EVENTS
    # =========================================================================

    def reconstruction_started(
        self,
        session_id: str,
        trace_id: str,
        source: str,
        sections_requested: List[str],
    ) -> None:
        """Log reconstruction started."""
        self._log(
            logging.INFO,
            LogEventType.RECONSTRUCTION_STARTED,
            session_id,
            trace_id,
            f"Reconstruction started: source={source}, sections={sections_requested}",
            source=source,
            sections_requested=sections_requested,
        )

    def reconstruction_completed(
        self,
        session_id: str,
        trace_id: str,
        source: str,
        sections_restored: List[str],
        duration_ms: float,
        bytes_loaded: int,
    ) -> None:
        """Log reconstruction completed."""
        self._log(
            logging.INFO,
            LogEventType.RECONSTRUCTION_COMPLETED,
            session_id,
            trace_id,
            f"Reconstruction completed: source={source}, "
            f"sections={sections_restored}, duration={duration_ms:.2f}ms",
            source=source,
            sections_restored=sections_restored,
            duration_ms=duration_ms,
            bytes_loaded=bytes_loaded,
        )

    # =========================================================================
    # LIFECYCLE EVENTS
    # =========================================================================

    def lifecycle_started(
        self,
        session_id: str,
        trace_id: str,
        hot_sections: int,
        warm_sections: int,
        total_size_bytes: int,
    ) -> None:
        """Log session started."""
        self._log(
            logging.INFO,
            LogEventType.LIFECYCLE_STARTED,
            session_id,
            trace_id,
            f"Session started: hot_sections={hot_sections}, "
            f"warm_sections={warm_sections}, size={total_size_bytes}B",
            hot_sections=hot_sections,
            warm_sections=warm_sections,
            total_size_bytes=total_size_bytes,
        )

    def lifecycle_stopped(
        self,
        session_id: str,
        trace_id: str,
        duration_ms: float,
        mutation_count: int,
        final_size_bytes: int,
    ) -> None:
        """Log session stopped."""
        self._log(
            logging.INFO,
            LogEventType.LIFECYCLE_STOPPED,
            session_id,
            trace_id,
            f"Session stopped: duration={duration_ms:.0f}ms, "
            f"mutations={mutation_count}, final_size={final_size_bytes}B",
            duration_ms=duration_ms,
            mutation_count=mutation_count,
            final_size_bytes=final_size_bytes,
        )

    # =========================================================================
    # CHECKPOINT EVENTS
    # =========================================================================

    def checkpoint_created(
        self,
        session_id: str,
        trace_id: str,
        checkpoint_id: str,
        sections_saved: int,
        bytes_saved: int,
        duration_ms: float,
    ) -> None:
        """Log checkpoint created."""
        self._log(
            logging.INFO,
            LogEventType.CHECKPOINT_CREATED,
            session_id,
            trace_id,
            f"Checkpoint created: id={checkpoint_id}, "
            f"sections={sections_saved}, bytes={bytes_saved}",
            checkpoint_id=checkpoint_id,
            sections_saved=sections_saved,
            bytes_saved=bytes_saved,
            duration_ms=duration_ms,
        )

    def checkpoint_restored(
        self,
        session_id: str,
        trace_id: str,
        checkpoint_id: str,
        sections_restored: int,
        bytes_loaded: int,
        duration_ms: float,
    ) -> None:
        """Log checkpoint restored."""
        self._log(
            logging.INFO,
            LogEventType.CHECKPOINT_RESTORED,
            session_id,
            trace_id,
            f"Checkpoint restored: id={checkpoint_id}, "
            f"sections={sections_restored}, bytes={bytes_loaded}",
            checkpoint_id=checkpoint_id,
            sections_restored=sections_restored,
            bytes_loaded=bytes_loaded,
            duration_ms=duration_ms,
        )

    # =========================================================================
    # MIGRATION EVENTS
    # =========================================================================

    def migration_started(
        self,
        session_id: str,
        trace_id: str,
        direction: str,
        sections: List[str],
        bytes_to_migrate: int,
    ) -> None:
        """Log migration started (HOT↔WARM)."""
        self._log(
            logging.INFO,
            LogEventType.MIGRATION_STARTED,
            session_id,
            trace_id,
            f"Migration started: direction={direction}, "
            f"sections={sections}, bytes={bytes_to_migrate}",
            direction=direction,
            sections=sections,
            bytes_to_migrate=bytes_to_migrate,
        )

    def migration_completed(
        self,
        session_id: str,
        trace_id: str,
        direction: str,
        sections_migrated: List[str],
        bytes_migrated: int,
        duration_ms: float,
    ) -> None:
        """Log migration completed."""
        self._log(
            logging.INFO,
            LogEventType.MIGRATION_COMPLETED,
            session_id,
            trace_id,
            f"Migration completed: direction={direction}, "
            f"sections={sections_migrated}, bytes={bytes_migrated}",
            direction=direction,
            sections_migrated=sections_migrated,
            bytes_migrated=bytes_migrated,
            duration_ms=duration_ms,
        )

    # =========================================================================
    # PRESSURE EVENTS
    # =========================================================================

    def pressure_changed(
        self,
        session_id: str,
        trace_id: str,
        previous_level: str,
        new_level: str,
        utilization_pct: float,
        tier: str = "total",
    ) -> None:
        """Log pressure level change."""
        # Log level depends on new pressure
        if new_level == "emergency":
            log_level = logging.ERROR
        elif new_level in ("critical", "elevated"):
            log_level = logging.WARNING
        else:
            log_level = logging.INFO

        self._log(
            log_level,
            LogEventType.PRESSURE_CHANGED,
            session_id,
            trace_id,
            f"Pressure changed: {previous_level} -> {new_level}, "
            f"utilization={utilization_pct:.1f}%, tier={tier}",
            previous_level=previous_level,
            new_level=new_level,
            utilization_pct=utilization_pct,
            tier=tier,
        )


# =============================================================================
# MODULE-LEVEL LOGGER INSTANCE
# =============================================================================

# Default singleton logger for module use
_default_logger: Optional[SessionStateLogger] = None


def get_default_logger() -> SessionStateLogger:
    """
    Get the default SessionStateLogger singleton.

    Returns:
        SessionStateLogger instance
    """
    global _default_logger
    if _default_logger is None:
        _default_logger = SessionStateLogger()
    return _default_logger


def configure_logger(
    level: int = logging.DEBUG,
    stream: Optional[TextIO] = None,
    use_json_format: bool = True,
) -> SessionStateLogger:
    """
    Configure and return the default logger.

    Args:
        level: Logging level
        stream: Output stream
        use_json_format: Whether to use JSON format

    Returns:
        Configured SessionStateLogger
    """
    global _default_logger
    _default_logger = SessionStateLogger(
        level=level,
        stream=stream,
        use_json_format=use_json_format,
    )
    return _default_logger
