"""Concrete IKernelObsPort — K1→K0 observability: telemetry + feedback.

Implements fire-and-forget emission of metrics, logs, and feedback with
priority-based offline queueing (LOW=drop, NORMAL/HIGH=queue).

Issue 3.9.5 (MS-3): Scaffold adapter — transport calls are wired but
K0 obs endpoint does not exist yet.  Offline queueing fully functional.

References:
  - bridge/ports/obs_port_protocol.py (IKernelObsPort)
  - bridge/client.py (IBridgeClient.emit_obs / emit_feedback)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..core.transport import HttpTransport
from ..ports.obs_port_protocol import FeedbackEnvelope, ObsPriority

logger = logging.getLogger(__name__)

# K0 obs endpoint (MS-3+: not yet deployed on K0 side)
_OBS_PATH = "/k0/obs.emit"


class KernelObsPort:
    """Bridge-side observability port for K1→K0 telemetry and feedback.

    Offline behaviour:
        LOW priority emissions are silently dropped.
        NORMAL/HIGH priority emissions are queued to LocalOutbox.
        Feedback envelopes are always HIGH priority.

    Parameters
    ----------
    transport : HttpTransport
        HTTP client for K0 communication.  Must be opened before use.
    outbox : LocalOutbox | None
        Offline queue for NORMAL/HIGH priority emissions.
    """

    __slots__ = ("_transport", "_outbox")

    def __init__(
        self,
        transport: HttpTransport,
        outbox: Any | None = None,
    ) -> None:
        self._transport = transport
        self._outbox = outbox

    async def emit(
        self,
        kind: str,
        body: dict[str, Any],
        *,
        priority: str = "NORMAL",
        trace_id: str = "",
    ) -> None:
        """Emit a single observability payload to K0.

        Fire-and-forget: never raises to caller.
        LOW priority is dropped when transport fails.
        NORMAL/HIGH is queued to outbox when transport fails.
        """
        payload = {
            "kind": kind,
            "body": body,
            "priority": priority,
            "trace_id": trace_id,
        }

        try:
            client = self._transport._ensure_client()
            response = await client.post(
                _OBS_PATH,
                content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            if response.status_code == 200:
                logger.debug("KernelObsPort.emit: accepted kind=%s", kind)
                return
            raise ConnectionError(f"K0 obs returned status={response.status_code}")
        except Exception:
            self._handle_offline(payload, priority, kind)

    async def emit_feedback(
        self,
        envelope: FeedbackEnvelope,
    ) -> None:
        """Emit a structured feedback envelope to K0 System 2.

        Always HIGH priority — queued when offline.
        """
        payload = {
            "kind": "feedback",
            "body": {
                "feedback_id": envelope.feedback_id,
                "pipeline_id": envelope.pipeline_id,
                "signal_class": envelope.signal_class,
                "correlation": envelope.correlation,
                "provenance": envelope.provenance,
                "payload": envelope.payload,
            },
            "priority": "HIGH",
            "trace_id": envelope.trace_id,
        }

        try:
            client = self._transport._ensure_client()
            response = await client.post(
                _OBS_PATH,
                content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            if response.status_code == 200:
                logger.debug(
                    "KernelObsPort.emit_feedback: accepted feedback_id=%s",
                    envelope.feedback_id,
                )
                return
            raise ConnectionError(f"K0 obs returned status={response.status_code}")
        except Exception:
            self._handle_offline(payload, "HIGH", "feedback")

    def _handle_offline(
        self,
        payload: dict[str, Any],
        priority: str,
        kind: str,
    ) -> None:
        """Handle offline: drop LOW, queue NORMAL/HIGH."""
        try:
            priority_level = ObsPriority[priority]
        except KeyError:
            priority_level = ObsPriority.NORMAL

        if priority_level == ObsPriority.LOW:
            logger.debug(
                "KernelObsPort: dropping LOW priority %s emission (offline)",
                kind,
            )
            return

        if self._outbox is not None:
            self._outbox.enqueue(
                envelope_json=json.dumps(payload, ensure_ascii=False),
                topic=f"obs.{kind}",
                priority=priority_level.value,
            )
            logger.warning(
                "KernelObsPort: queued %s %s emission to outbox (offline)",
                priority,
                kind,
            )
        else:
            logger.warning(
                "KernelObsPort: dropping %s %s emission (offline, no outbox)",
                priority,
                kind,
            )
