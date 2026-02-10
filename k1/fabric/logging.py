"""
Fabric Structured Logging
========================

IMPLEMENTATION PLAN REFERENCE: docs/plans/k1/fabric-implementation-plan.md
EPIC: 7.3 Tracing & Logging
ISSUE: 7.3.2

PURPOSE:
    Provide structured JSON logging for Fabric execution phases.
    All logs include trace_id for distributed tracing correlation.

LOG EVENTS (5 phases):
    1. resolve
    2. policy_check
    3. context_build
    4. execute
    5. result_return

FORMAT:
    All logs are JSON with these standard fields:
    - timestamp_iso: ISO 8601 timestamp
    - level: DEBUG, INFO, WARNING, ERROR
    - event: Event type (e.g., "resolve")
    - component: "fabric.{phase}"
    - trace_id: cognitive_trace_id for distributed tracing
    - request_id: CapabilityRequest.request_id
    - capability_name: CapabilityRequest.capability_name
    - provider_id: provider identifier (if known)
    - duration_ms: Duration of the phase in milliseconds
    - success: Boolean success flag (when applicable)
    - module: "fabric"
    - Additional context fields per event type
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, TextIO


class LogEventType(str, Enum):
    """All Fabric structured log event types."""

    RESOLVE = "resolve"
    POLICY_CHECK = "policy_check"
    CONTEXT_BUILD = "context_build"
    EXECUTE = "execute"
    RESULT_RETURN = "result_return"


@dataclass
class StructuredLogRecord:
    """
    Structured log record for JSON serialization.

    Standard fields present in every log:
    - timestamp_iso: ISO 8601 timestamp (UTC)
    - level: Log level (DEBUG, INFO, WARNING, ERROR)
    - event: Event type from LogEventType
    - component: "fabric.{phase}"
    - trace_id: cognitive_trace_id for distributed tracing
    - request_id: CapabilityRequest.request_id
    - capability_name: CapabilityRequest.capability_name
    - provider_id: provider identifier (if known)
    - duration_ms: phase duration in milliseconds
    - success: whether the phase completed successfully
    - module: Always "fabric"

    Context fields vary by event type.
    """

    event: str
    level: str = "INFO"
    component: str = "fabric"
    trace_id: str = ""
    request_id: str = ""
    capability_name: str = ""
    provider_id: str = ""
    duration_ms: Optional[float] = None
    success: Optional[bool] = None
    module: str = "fabric"
    timestamp_iso: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, flattening context fields."""
        result: Dict[str, Any] = {
            "timestamp_iso": self.timestamp_iso,
            "level": self.level,
            "event": self.event,
            "component": self.component,
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "capability_name": self.capability_name,
            "provider_id": self.provider_id,
            "module": self.module,
        }
        if self.duration_ms is not None:
            result["duration_ms"] = self.duration_ms
        if self.success is not None:
            result["success"] = self.success
        result.update(self.context)
        return result

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)


class FabricJsonFormatter(logging.Formatter):
    """
    JSON formatter for Python logging that produces structured logs.

    Usage:
        handler = logging.StreamHandler()
        handler.setFormatter(FabricJsonFormatter())
        logger.addHandler(handler)
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        structured: Dict[str, Any] = getattr(record, "structured", {})

        log_dict = {
            "timestamp_iso": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "event": structured.get("event", "log.message"),
            "component": structured.get("component", "fabric"),
            "trace_id": structured.get("trace_id", ""),
            "request_id": structured.get("request_id", ""),
            "capability_name": structured.get("capability_name", ""),
            "provider_id": structured.get("provider_id", ""),
            "duration_ms": structured.get("duration_ms"),
            "success": structured.get("success"),
            "module": "fabric",
            "message": record.getMessage(),
        }

        context = structured.get("context", {})
        log_dict.update(context)

        if record.exc_info:
            log_dict["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_dict, default=str)


class FabricLogger:
    """
    Structured logger for Fabric operations.

    Provides methods for logging each phase with consistent fields.
    """

    def __init__(
        self,
        name: str = "k1.fabric",
        level: int = logging.DEBUG,
        stream: Optional[TextIO] = None,
        use_json_format: bool = True,
    ) -> None:
        self._logger = logging.getLogger(name)
        self._logger.setLevel(level)
        self._use_json_format = use_json_format

        if not self._logger.handlers:
            handler = logging.StreamHandler(stream or sys.stdout)
            handler.setLevel(level)
            if use_json_format:
                handler.setFormatter(FabricJsonFormatter())
            else:
                handler.setFormatter(
                    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
                )
            self._logger.addHandler(handler)

    def _log(
        self,
        level: int,
        event: LogEventType,
        trace_id: str,
        request_id: str,
        capability_name: str,
        provider_id: str,
        message: str,
        duration_ms: Optional[float] = None,
        success: Optional[bool] = None,
        **context: Any,
    ) -> None:
        extra = {
            "structured": {
                "event": event.value,
                "component": f"fabric.{event.value}",
                "trace_id": trace_id,
                "request_id": request_id,
                "capability_name": capability_name,
                "provider_id": provider_id,
                "duration_ms": duration_ms,
                "success": success,
                "context": context,
            }
        }
        self._logger.log(level, message, extra=extra)

    def _phase_level(self, success: Optional[bool]) -> int:
        if success is None:
            return logging.INFO
        return logging.INFO if success else logging.WARNING

    def resolve(
        self,
        trace_id: str,
        request_id: str,
        capability_name: str,
        provider_id: str = "",
        duration_ms: Optional[float] = None,
        success: Optional[bool] = None,
        **context: Any,
    ) -> None:
        level = self._phase_level(success)
        self._log(
            level,
            LogEventType.RESOLVE,
            trace_id,
            request_id,
            capability_name,
            provider_id,
            "Resolve phase completed",
            duration_ms,
            success,
            **context,
        )

    def policy_check(
        self,
        trace_id: str,
        request_id: str,
        capability_name: str,
        provider_id: str = "",
        duration_ms: Optional[float] = None,
        success: Optional[bool] = None,
        **context: Any,
    ) -> None:
        level = self._phase_level(success)
        self._log(
            level,
            LogEventType.POLICY_CHECK,
            trace_id,
            request_id,
            capability_name,
            provider_id,
            "Policy check completed",
            duration_ms,
            success,
            **context,
        )

    def context_build(
        self,
        trace_id: str,
        request_id: str,
        capability_name: str,
        provider_id: str = "",
        duration_ms: Optional[float] = None,
        success: Optional[bool] = None,
        **context: Any,
    ) -> None:
        level = self._phase_level(success)
        self._log(
            level,
            LogEventType.CONTEXT_BUILD,
            trace_id,
            request_id,
            capability_name,
            provider_id,
            "Context build completed",
            duration_ms,
            success,
            **context,
        )

    def execute(
        self,
        trace_id: str,
        request_id: str,
        capability_name: str,
        provider_id: str = "",
        duration_ms: Optional[float] = None,
        success: Optional[bool] = None,
        **context: Any,
    ) -> None:
        level = self._phase_level(success)
        self._log(
            level,
            LogEventType.EXECUTE,
            trace_id,
            request_id,
            capability_name,
            provider_id,
            "Execution completed",
            duration_ms,
            success,
            **context,
        )

    def result_return(
        self,
        trace_id: str,
        request_id: str,
        capability_name: str,
        provider_id: str = "",
        duration_ms: Optional[float] = None,
        success: Optional[bool] = None,
        **context: Any,
    ) -> None:
        level = self._phase_level(success)
        self._log(
            level,
            LogEventType.RESULT_RETURN,
            trace_id,
            request_id,
            capability_name,
            provider_id,
            "Result returned",
            duration_ms,
            success,
            **context,
        )


_default_logger: Optional[FabricLogger] = None


def get_default_logger() -> FabricLogger:
    """Get the default FabricLogger singleton."""
    global _default_logger
    if _default_logger is None:
        _default_logger = FabricLogger()
    return _default_logger


def configure_logger(
    level: int = logging.DEBUG,
    stream: Optional[TextIO] = None,
    use_json_format: bool = True,
) -> FabricLogger:
    """Configure and return the default logger."""
    global _default_logger
    _default_logger = FabricLogger(
        level=level,
        stream=stream,
        use_json_format=use_json_format,
    )
    return _default_logger
