"""
Fabric Audit Logging - Structured audit events for fabric calls.

All fabric invocations are logged with structured JSON for auditability.
Per ADR-K004, all fabric calls cross trust boundaries and must be auditable.

Related:
- k0/fabric/fabric.py: CapabilityFabric
- docs/architecture/decisions-K0/k004-capability-mesh-architecture.md
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

# Dedicated audit logger - separate namespace for filtering/routing
audit_logger = logging.getLogger("k0.fabric.audit")


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """Base audit event structure."""

    event: str
    timestamp: str
    trace_id: str | None
    correlation_id: str | None


@dataclass(frozen=True, slots=True)
class FabricInvokeStart(AuditEvent):
    """Logged before provider resolution."""

    capability: str
    caller_id: str | None


@dataclass(frozen=True, slots=True)
class FabricInvokeComplete(AuditEvent):
    """Logged after handler returns successfully."""

    capability: str
    provider_id: str
    caller_id: str | None
    latency_ms: float
    success: bool = True


@dataclass(frozen=True, slots=True)
class FabricInvokeError(AuditEvent):
    """Logged on handler exception."""

    capability: str
    provider_id: str | None
    caller_id: str | None
    error_type: str
    error_msg: str
    latency_ms: float
    success: bool = False


@dataclass(frozen=True, slots=True)
class FabricInvokeTimeout(AuditEvent):
    """Logged on request timeout."""

    capability: str
    provider_id: str | None
    caller_id: str | None
    timeout_ms: float
    elapsed_ms: float
    success: bool = False


@dataclass(frozen=True, slots=True)
class FabricContextPolicy(AuditEvent):
    """Logged when context policy is enforced."""

    capability: str
    provider_id: str
    policy: str
    caller_caps_count: int
    effective_caps_count: int


class FabricAuditor:
    """
    Audit logger for fabric invocations.

    All fabric calls are logged with structured events for:
    - Security auditing (who called what capability)
    - Performance monitoring (latency tracking)
    - Debugging (trace_id correlation)
    - Compliance (full audit trail)

    Example:
        auditor = get_fabric_auditor()
        start_time = auditor.log_invoke_start("score_salience", "P02", trace_id)
        try:
            result = handler(**payload)
            auditor.log_invoke_complete("score_salience", "module.salience", "P02", start_time, trace_id, request_id)
        except Exception as e:
            auditor.log_invoke_error("score_salience", "module.salience", "P02", e, start_time, trace_id, request_id)
    """

    def __init__(self, logger: logging.Logger | None = None):
        """
        Initialize the auditor.

        Args:
            logger: Optional custom logger (uses k0.fabric.audit by default)
        """
        self._logger = logger or audit_logger

    def _now_iso(self) -> str:
        """Return current UTC time in ISO format."""
        return datetime.now(timezone.utc).isoformat()

    def _log_event(self, event: Any, level: int = logging.INFO) -> None:
        """Log an event as structured dict."""
        self._logger.log(level, asdict(event))

    def log_invoke_start(
        self,
        capability: str,
        caller_id: str | None,
        trace_id: str | None,
        correlation_id: str | None,
    ) -> float:
        """
        Log invoke start, return start time for latency calculation.

        Args:
            capability: Capability being invoked
            caller_id: ID of the calling module/pipeline
            trace_id: Distributed trace ID
            correlation_id: Request ID for correlation

        Returns:
            Monotonic start time for latency calculation
        """
        event = FabricInvokeStart(
            event="fabric.invoke.start",
            timestamp=self._now_iso(),
            trace_id=trace_id,
            correlation_id=correlation_id,
            capability=capability,
            caller_id=caller_id,
        )
        self._log_event(event)
        return time.monotonic()

    def log_invoke_complete(
        self,
        capability: str,
        provider_id: str,
        caller_id: str | None,
        start_time: float,
        trace_id: str | None,
        correlation_id: str | None,
    ) -> None:
        """
        Log successful invoke completion.

        Args:
            capability: Capability that was invoked
            provider_id: Provider that handled the request
            caller_id: ID of the calling module/pipeline
            start_time: Monotonic start time from log_invoke_start
            trace_id: Distributed trace ID
            correlation_id: Request ID for correlation
        """
        latency_ms = (time.monotonic() - start_time) * 1000.0
        event = FabricInvokeComplete(
            event="fabric.invoke.complete",
            timestamp=self._now_iso(),
            trace_id=trace_id,
            correlation_id=correlation_id,
            capability=capability,
            provider_id=provider_id,
            caller_id=caller_id,
            latency_ms=round(latency_ms, 3),
        )
        self._log_event(event)

    def log_invoke_error(
        self,
        capability: str,
        provider_id: str | None,
        caller_id: str | None,
        error: Exception,
        start_time: float,
        trace_id: str | None,
        correlation_id: str | None,
    ) -> None:
        """
        Log invoke error.

        Args:
            capability: Capability that was invoked
            provider_id: Provider that handled the request (may be None if resolution failed)
            caller_id: ID of the calling module/pipeline
            error: Exception that was raised
            start_time: Monotonic start time from log_invoke_start
            trace_id: Distributed trace ID
            correlation_id: Request ID for correlation
        """
        latency_ms = (time.monotonic() - start_time) * 1000.0
        event = FabricInvokeError(
            event="fabric.invoke.error",
            timestamp=self._now_iso(),
            trace_id=trace_id,
            correlation_id=correlation_id,
            capability=capability,
            provider_id=provider_id,
            caller_id=caller_id,
            error_type=type(error).__name__,
            error_msg=str(error),
            latency_ms=round(latency_ms, 3),
        )
        self._log_event(event, level=logging.WARNING)

    def log_invoke_timeout(
        self,
        capability: str,
        provider_id: str | None,
        caller_id: str | None,
        timeout_ms: float,
        start_time: float,
        trace_id: str | None,
        correlation_id: str | None,
    ) -> None:
        """
        Log invoke timeout.

        Args:
            capability: Capability that was invoked
            provider_id: Provider that was handling the request
            caller_id: ID of the calling module/pipeline
            timeout_ms: Configured timeout in milliseconds
            start_time: Monotonic start time from log_invoke_start
            trace_id: Distributed trace ID
            correlation_id: Request ID for correlation
        """
        elapsed_ms = (time.monotonic() - start_time) * 1000.0
        event = FabricInvokeTimeout(
            event="fabric.invoke.timeout",
            timestamp=self._now_iso(),
            trace_id=trace_id,
            correlation_id=correlation_id,
            capability=capability,
            provider_id=provider_id,
            caller_id=caller_id,
            timeout_ms=timeout_ms,
            elapsed_ms=round(elapsed_ms, 3),
        )
        self._log_event(event, level=logging.WARNING)

    def log_context_policy(
        self,
        capability: str,
        provider_id: str,
        policy: str,
        caller_caps_count: int,
        effective_caps_count: int,
        trace_id: str | None,
        correlation_id: str | None,
    ) -> None:
        """
        Log context policy enforcement.

        Args:
            capability: Capability being invoked
            provider_id: Provider handling the request
            policy: Policy applied (inherit, isolated, synthetic)
            caller_caps_count: Number of capabilities in caller context
            effective_caps_count: Number of effective capabilities after policy
            trace_id: Distributed trace ID
            correlation_id: Request ID for correlation
        """
        event = FabricContextPolicy(
            event="fabric.context.policy",
            timestamp=self._now_iso(),
            trace_id=trace_id,
            correlation_id=correlation_id,
            capability=capability,
            provider_id=provider_id,
            policy=policy,
            caller_caps_count=caller_caps_count,
            effective_caps_count=effective_caps_count,
        )
        self._log_event(event, level=logging.DEBUG)


# Global auditor instance
_auditor: FabricAuditor | None = None


def get_fabric_auditor() -> FabricAuditor:
    """Get the global fabric auditor."""
    global _auditor
    if _auditor is None:
        _auditor = FabricAuditor()
    return _auditor


def reset_fabric_auditor() -> None:
    """Reset the global auditor (for testing)."""
    global _auditor
    _auditor = None
