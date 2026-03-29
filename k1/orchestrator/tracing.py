"""
k1.orchestrator.tracing -- Structured trace logging helpers (8.3.1).

Provides lightweight, dependency-free helpers to emit JSON logs for
request-correlated orchestrator phases.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any, Dict, Optional
from uuid import uuid4


def new_trace_id() -> str:
    """Return a fresh UUID4 trace identifier string."""
    return str(uuid4())


def ensure_trace_id(trace_id: Optional[str]) -> str:
    """Return the provided trace_id when present, else generate a UUID4."""
    if trace_id:
        return trace_id
    return new_trace_id()


def _level_name(level: int) -> str:
    name = logging.getLevelName(level)
    return name if isinstance(name, str) else "INFO"


def build_trace_log(
    *,
    level: int,
    phase: str,
    trace_id: Optional[str],
    request_id: Optional[str] = None,
    tier: Optional[str] = None,
    step_id: Optional[str] = None,
    wave: Optional[int] = None,
    duration_ms: Optional[float] = None,
    success: Optional[bool] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a structured trace log payload for orchestrator phases."""
    payload: Dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": _level_name(level),
        "component": f"orchestrator.{phase}",
        "trace_id": ensure_trace_id(trace_id),
    }

    if request_id:
        payload["request_id"] = request_id
    if tier:
        payload["tier"] = tier
    if step_id:
        payload["step_id"] = step_id
    if wave is not None:
        payload["wave"] = wave
    if duration_ms is not None:
        payload["duration_ms"] = float(duration_ms)
    if success is not None:
        payload["success"] = bool(success)
    if extra:
        payload.update(extra)

    return payload


def trace_phase(
    logger: logging.Logger,
    phase: str,
    *,
    trace_id: Optional[str],
    request_id: Optional[str] = None,
    tier: Optional[str] = None,
    step_id: Optional[str] = None,
    wave: Optional[int] = None,
    duration_ms: Optional[float] = None,
    success: Optional[bool] = None,
    level: int = logging.INFO,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Emit one structured JSON log line for an orchestrator phase."""
    payload = build_trace_log(
        level=level,
        phase=phase,
        trace_id=trace_id,
        request_id=request_id,
        tier=tier,
        step_id=step_id,
        wave=wave,
        duration_ms=duration_ms,
        success=success,
        extra=extra,
    )
    logger.log(level, json.dumps(payload, separators=(",", ":"), sort_keys=True))
