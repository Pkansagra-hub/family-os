"""HILLedgerAdapter (E1.M1.6).

Wraps an injected `LedgerWriter` so the HIL service can persist
request/resolve/timeout/blocked events without importing concierge
event types.

The adapter is no-op when constructed with `writer=None` (test/dev
mode without ledger).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from k1.hil.types import (
    HILBlockedEvent,
    HILEnvelope,
    HILRequestedEvent,
    HILResolvedEvent,
    HILResponseEnvelope,
    HILTimedOutEvent,
)

logger = logging.getLogger(__name__)


class HILLedgerAdapter:
    """Best-effort persistence wrapper. Failures logged, not raised."""

    __slots__ = ("_writer",)

    def __init__(self, writer: Any | None) -> None:
        self._writer = writer

    def write_requested(self, env: HILEnvelope) -> None:
        if self._writer is None:
            return
        ev = HILRequestedEvent(
            hil_request_id=env.hil_request_id,
            kind=env.kind.value,
            caller_key=env.caller_key,
            trace_id=env.trace_id,
            timestamp_ms=env.created_at_ms,
        )
        self._safe_write("hil.requested", ev.to_dict())

    def write_resolved(self, env: HILEnvelope, resp: HILResponseEnvelope) -> None:
        if self._writer is None:
            return
        ev = HILResolvedEvent(
            hil_request_id=env.hil_request_id,
            kind=env.kind.value,
            decision_summary=_summarize_decision(resp),
            timestamp_ms=resp.responded_at_ms,
            duration_ms=max(0, resp.responded_at_ms - env.created_at_ms),
        )
        self._safe_write("hil.resolved", ev.to_dict())

    def write_timed_out(self, env: HILEnvelope) -> None:
        if self._writer is None:
            return
        ev = HILTimedOutEvent(
            hil_request_id=env.hil_request_id,
            kind=env.kind.value,
            caller_key=env.caller_key,
            timestamp_ms=int(time.time() * 1000),
            timeout_ms=env.timeout_ms,
        )
        self._safe_write("hil.timed_out", ev.to_dict())

    def write_blocked(self, env: HILEnvelope, reason: str) -> None:
        if self._writer is None:
            return
        ev = HILBlockedEvent(
            hil_request_id=env.hil_request_id,
            kind=env.kind.value,
            caller_key=env.caller_key,
            reason=reason,
            timestamp_ms=int(time.time() * 1000),
        )
        self._safe_write("hil.blocked", ev.to_dict())

    # --- internals ---

    def _safe_write(self, event_type: str, payload: dict) -> None:
        try:
            # LedgerWriter has multiple shapes across the codebase. We
            # try the most common interfaces in order; any AttributeError
            # is logged and swallowed (best-effort persistence).
            writer = self._writer
            if hasattr(writer, "write_event"):
                writer.write_event(event_type=event_type, payload=payload)
            elif hasattr(writer, "append"):
                writer.append({"event_type": event_type, "payload": payload})
            elif hasattr(writer, "write"):
                writer.write({"event_type": event_type, "payload": payload})
            else:  # pragma: no cover -- unknown writer shape
                logger.warning(
                    "hil_ledger_unknown_writer_shape event_type=%s writer_type=%s",
                    event_type,
                    type(writer).__name__,
                )
        except Exception as exc:  # noqa: BLE001 -- best-effort
            logger.warning(
                "hil_ledger_write_failed event_type=%s error=%s",
                event_type,
                exc,
            )


def _summarize_decision(resp: HILResponseEnvelope) -> str:
    if resp.timed_out:
        return "timed_out"
    payload = resp.payload or {}
    for key in ("decision", "choice", "answer", "outcome"):
        if key in payload and payload[key] is not None:
            return f"{key}={payload[key]!s:.40}"
    return "answered"
