"""Structured trace logging for Model Hub [9.1.2].

Provides lightweight, dependency-free helpers to emit structured JSON log
events for all Model Hub operations. Every log event includes:
  - trace_id, request_id, consumer_id (correlation)
  - capability, model_id, provider_id (context)
  - timestamp, level, phase (structure)

Privacy enforcement:
  - NEVER log raw prompts or API keys.
  - message content replaced with ``<REDACTED>`` in all log events.

34 log event phases covering the 9-step pipeline + lifecycle events.

Import graph (Layer 0 -- no internal deps)
------------------------------------------
k1.model_hub.tracing
  -> stdlib only

NEVER import from any service, port, adapter, or plugin module.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from typing import Any, Dict, Optional

logger = logging.getLogger("k1.model_hub")

# ===========================================================================
# Log phases (34 structured event types)
# ===========================================================================

# Pipeline phases (Steps 1-9)
PHASE_REQUEST_RECEIVED = "request.received"
PHASE_VALIDATE_OK = "validate.ok"
PHASE_VALIDATE_FAILED = "validate.failed"
PHASE_BUDGET_CHECK = "budget.check"
PHASE_BUDGET_REJECTED = "budget.rejected"
PHASE_BUDGET_DEGRADED = "budget.degraded"
PHASE_PRIORITY_CLASSIFIED = "priority.classified"
PHASE_ROUTE_START = "route.start"
PHASE_ROUTE_ELIGIBLE = "route.eligible"
PHASE_ROUTE_NO_PROVIDER = "route.no_eligible_provider"
PHASE_SELECT_MODEL = "select.model"
PHASE_SELECT_FALLBACK = "select.fallback_chain"
PHASE_CACHE_HIT = "cache.hit"
PHASE_CACHE_MISS = "cache.miss"
PHASE_CACHE_PUT = "cache.put"
PHASE_NORMALIZE = "normalize.request"
PHASE_DISPATCH_START = "dispatch.start"
PHASE_DISPATCH_OK = "dispatch.ok"
PHASE_DISPATCH_RETRY = "dispatch.retry"
PHASE_DISPATCH_FAILED = "dispatch.failed"
PHASE_DISPATCH_FALLBACK = "dispatch.fallback"
PHASE_STREAM_START = "stream.start"
PHASE_STREAM_CHUNK = "stream.chunk"
PHASE_STREAM_DONE = "stream.done"
PHASE_POSTPROCESS_COST = "postprocess.cost"
PHASE_POSTPROCESS_AUDIT = "postprocess.audit"
PHASE_RESPONSE_SENT = "response.sent"

# Lifecycle phases
PHASE_INIT = "lifecycle.init"
PHASE_HEALTH_CHECK = "lifecycle.health_check"
PHASE_READY = "lifecycle.ready"
PHASE_DEGRADED = "lifecycle.degraded"
PHASE_SHUTDOWN = "lifecycle.shutdown"

# Circuit breaker events
PHASE_CIRCUIT_OPEN = "circuit.open"
PHASE_CIRCUIT_CLOSE = "circuit.close"

ALL_PHASES = [
    PHASE_REQUEST_RECEIVED,
    PHASE_VALIDATE_OK,
    PHASE_VALIDATE_FAILED,
    PHASE_BUDGET_CHECK,
    PHASE_BUDGET_REJECTED,
    PHASE_BUDGET_DEGRADED,
    PHASE_PRIORITY_CLASSIFIED,
    PHASE_ROUTE_START,
    PHASE_ROUTE_ELIGIBLE,
    PHASE_ROUTE_NO_PROVIDER,
    PHASE_SELECT_MODEL,
    PHASE_SELECT_FALLBACK,
    PHASE_CACHE_HIT,
    PHASE_CACHE_MISS,
    PHASE_CACHE_PUT,
    PHASE_NORMALIZE,
    PHASE_DISPATCH_START,
    PHASE_DISPATCH_OK,
    PHASE_DISPATCH_RETRY,
    PHASE_DISPATCH_FAILED,
    PHASE_DISPATCH_FALLBACK,
    PHASE_STREAM_START,
    PHASE_STREAM_CHUNK,
    PHASE_STREAM_DONE,
    PHASE_POSTPROCESS_COST,
    PHASE_POSTPROCESS_AUDIT,
    PHASE_RESPONSE_SENT,
    PHASE_INIT,
    PHASE_HEALTH_CHECK,
    PHASE_READY,
    PHASE_DEGRADED,
    PHASE_SHUTDOWN,
    PHASE_CIRCUIT_OPEN,
    PHASE_CIRCUIT_CLOSE,
]


# ===========================================================================
# Structured log builder
# ===========================================================================


def build_trace_log(
    *,
    level: int = logging.INFO,
    phase: str,
    trace_id: Optional[str] = None,
    request_id: Optional[str] = None,
    consumer_id: Optional[str] = None,
    capability: Optional[str] = None,
    model_id: Optional[str] = None,
    provider_id: Optional[str] = None,
    duration_ms: Optional[float] = None,
    success: Optional[bool] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a structured trace log payload.

    Returns a dict suitable for JSON serialization. NEVER includes
    raw prompts, API keys, or PII.

    Args:
        level: Log level (logging.INFO, etc.).
        phase: Event phase from ALL_PHASES.
        trace_id: Cross-request correlation ID.
        request_id: Per-request unique ID.
        consumer_id: Consuming module ID.
        capability: Capability type string.
        model_id: Selected model ID.
        provider_id: Provider ID.
        duration_ms: Operation duration in ms.
        success: Whether the operation succeeded.
        extra: Additional structured data (must not contain secrets).

    Returns:
        Dict with structured log payload.
    """
    payload: Dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": logging.getLevelName(level),
        "component": "model_hub",
        "phase": phase,
    }

    # Correlation fields
    if trace_id is not None:
        payload["trace_id"] = trace_id
    if request_id is not None:
        payload["request_id"] = request_id
    if consumer_id is not None:
        payload["consumer_id"] = consumer_id

    # Context fields
    if capability is not None:
        payload["capability"] = capability
    if model_id is not None:
        payload["model_id"] = model_id
    if provider_id is not None:
        payload["provider_id"] = provider_id

    # Metrics
    if duration_ms is not None:
        payload["duration_ms"] = round(duration_ms, 2)
    if success is not None:
        payload["success"] = success

    # Extra (no secrets!)
    if extra:
        payload["extra"] = extra

    return payload


def emit_trace_log(
    *,
    level: int = logging.INFO,
    phase: str,
    trace_id: Optional[str] = None,
    request_id: Optional[str] = None,
    consumer_id: Optional[str] = None,
    capability: Optional[str] = None,
    model_id: Optional[str] = None,
    provider_id: Optional[str] = None,
    duration_ms: Optional[float] = None,
    success: Optional[bool] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build and emit a structured trace log.

    Emits via the ``k1.model_hub`` logger at the given level.
    Returns the payload for testing/inspection.
    """
    payload = build_trace_log(
        level=level,
        phase=phase,
        trace_id=trace_id,
        request_id=request_id,
        consumer_id=consumer_id,
        capability=capability,
        model_id=model_id,
        provider_id=provider_id,
        duration_ms=duration_ms,
        success=success,
        extra=extra,
    )

    logger.log(level, json.dumps(payload, default=str))
    return payload


# ===========================================================================
# Privacy helpers
# ===========================================================================


def redact_messages(messages: list[Dict[str, Any]]) -> list[Dict[str, str]]:
    """Redact message content for safe logging.

    Replaces all ``content`` values with ``<REDACTED>``.
    Preserves ``role`` for debugging.
    """
    return [{"role": m.get("role", "unknown"), "content": "<REDACTED>"} for m in messages]


def safe_labels(labels: Dict[str, Any]) -> Dict[str, str]:
    """Sanitize label dict -- strip anything that looks like a secret."""
    safe: Dict[str, str] = {}
    secret_keys = {"api_key", "key", "token", "secret", "password", "credential"}
    for k, v in labels.items():
        if k.lower() in secret_keys:
            safe[k] = "<REDACTED>"
        else:
            safe[k] = str(v)
    return safe


__all__ = [
    # Builder
    "build_trace_log",
    "emit_trace_log",
    # Privacy
    "redact_messages",
    "safe_labels",
    # Phase constants
    "ALL_PHASES",
    "PHASE_REQUEST_RECEIVED",
    "PHASE_VALIDATE_OK",
    "PHASE_VALIDATE_FAILED",
    "PHASE_BUDGET_CHECK",
    "PHASE_BUDGET_REJECTED",
    "PHASE_BUDGET_DEGRADED",
    "PHASE_PRIORITY_CLASSIFIED",
    "PHASE_ROUTE_START",
    "PHASE_ROUTE_ELIGIBLE",
    "PHASE_ROUTE_NO_PROVIDER",
    "PHASE_SELECT_MODEL",
    "PHASE_SELECT_FALLBACK",
    "PHASE_CACHE_HIT",
    "PHASE_CACHE_MISS",
    "PHASE_CACHE_PUT",
    "PHASE_NORMALIZE",
    "PHASE_DISPATCH_START",
    "PHASE_DISPATCH_OK",
    "PHASE_DISPATCH_RETRY",
    "PHASE_DISPATCH_FAILED",
    "PHASE_DISPATCH_FALLBACK",
    "PHASE_STREAM_START",
    "PHASE_STREAM_CHUNK",
    "PHASE_STREAM_DONE",
    "PHASE_POSTPROCESS_COST",
    "PHASE_POSTPROCESS_AUDIT",
    "PHASE_RESPONSE_SENT",
    "PHASE_INIT",
    "PHASE_HEALTH_CHECK",
    "PHASE_READY",
    "PHASE_DEGRADED",
    "PHASE_SHUTDOWN",
    "PHASE_CIRCUIT_OPEN",
    "PHASE_CIRCUIT_CLOSE",
]
