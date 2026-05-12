"""
k1.tools.family.events -- ``EventEmitter`` for family-tool audit emission.

Every state-changing family-tool action is required to publish a
canonical event envelope.  ``EventEmitter`` is the one place that
formats those envelopes and dispatches them to the surfaces that care:

* **SSE publisher** (mandatory) -- in-process pub/sub feeding K1's
  realtime subscribers (planner, supervision UI, audit log).  Delivery
  is fire-and-forget; backpressure errors are logged and swallowed.

* **K0 sync outbox** (optional) -- under the K1-hot / K0-optional pivot
  the outbox is *not* on the hot path.  When wired, ``EventEmitter``
  enqueues a serialisable envelope for asynchronous transmission via
  the existing M14 bridge outbox.  When ``None`` is supplied the
  emitter operates K0-free and the family tools still function -- they
  simply do not produce a K0 mirror.

The emitter does **not** import from ``bridge.*`` or ``scripts.*``;
the bridge outbox is reached strictly through the ``ISyncOutbox``
protocol so the cross-kernel CI rule (R-7 P10) remains intact.

Envelope shape
--------------
``{
   "id": <uuid4>,
   "topic": <topic>,
   "ts": <iso8601 utc>,
   "trace_id": <ctx.trace_id>,
   "actor": {"user_id", "role", "session_id"},
   "adapter": <adapter_id>,
   "action": <action_name>,
   "kind": <"write" | "delete" | "compute" | "read">,
   "payload": <redacted payload>,
}``

References
----------
* docs/plans/KERNEL_BOOTUP_PLAN.md §E15.0.4
* Plan revision R-2 (K1-hot / K0-optional storage pivot).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from k1.tools.family.base import BaseEntity, WriteContext
from k1.tools.family.definition import ActionSpec, ToolDefinition
from k1.tools.family.ports import ISsePublisher, ISyncOutbox

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _redact(payload: dict[str, Any], redact_fields: list[str]) -> dict[str, Any]:
    """Return a shallow copy of ``payload`` with redacted fields removed.

    Nested-key redaction is intentionally out of scope: adapters that
    need to redact within a sub-object should pre-redact before calling
    ``emit_write``.
    """

    if not redact_fields:
        return dict(payload)
    redacted = dict(payload)
    for key in redact_fields:
        redacted.pop(key, None)
    return redacted


# ---------------------------------------------------------------------------
# EventEmitter
# ---------------------------------------------------------------------------


class EventEmitter:
    """Audit-event emitter shared by all family tools in a session.

    Lifecycle
    ---------
    The emitter is constructed once per K1 process (or once per session,
    depending on the wiring strategy chosen at §E15.0.10) and injected
    into every ``IToolService`` via its constructor.  Services call
    ``emit_write(...)`` after committing a mutation; the emitter
    handles envelope construction + fan-out and never raises into the
    caller.

    Construction
    ------------
    ``sse_publisher`` is required because audit emission is a
    correctness contract.  ``sync_outbox`` is optional so K0-free
    deployments remain valid.
    """

    __slots__ = ("_sse", "_outbox")

    def __init__(
        self,
        sse_publisher: ISsePublisher,
        sync_outbox: Optional[ISyncOutbox] = None,
    ) -> None:
        if sse_publisher is None:
            raise ValueError("EventEmitter requires a non-None sse_publisher.")
        self._sse: ISsePublisher = sse_publisher
        self._outbox: Optional[ISyncOutbox] = sync_outbox

    # ------------------------------------------------------------------ #
    # Topic resolution
    # ------------------------------------------------------------------ #

    @staticmethod
    def topic_for(adapter_id: str, action: ActionSpec) -> str:
        """Return the canonical event topic for an action.

        The conventional shape is
        ``family.<adapter_id>.<action_name>.<kind>.v1`` so subscribers
        can subscribe with wildcards (e.g. ``family.calendar.*``) and
        version evolution is explicit.
        """

        return f"family.{adapter_id}.{action.name}.{action.kind}.v1"

    # ------------------------------------------------------------------ #
    # Emission
    # ------------------------------------------------------------------ #

    def emit_write(
        self,
        definition: ToolDefinition,
        action: ActionSpec,
        payload: dict[str, Any],
        ctx: WriteContext,
        *,
        topic: Optional[str] = None,
    ) -> str:
        """Build, publish, and (optionally) enqueue an audit envelope.

        Args
        ----
        definition:
            The owning service's ``ToolDefinition`` (provides
            ``adapter_id`` + category for the envelope).
        action:
            The ``ActionSpec`` describing what was executed.
        payload:
            Result/effect data to embed in the envelope.  Fields listed
            in ``action.sse.redact_fields`` are stripped before publish.
        ctx:
            The active ``WriteContext`` (provides actor + trace).
        topic:
            Optional explicit override for the topic; when ``None`` the
            canonical ``topic_for(...)`` is used.

        Returns
        -------
        The newly minted envelope id (uuid4 hex), useful for downstream
        correlation and tests.
        """

        envelope_id = uuid.uuid4().hex
        resolved_topic = topic or self.topic_for(definition.adapter_id, action)
        envelope: dict[str, Any] = {
            "id": envelope_id,
            "topic": resolved_topic,
            "ts": datetime.now(timezone.utc).isoformat(),
            "trace_id": ctx.trace_id,
            "actor": {
                "user_id": ctx.user_id,
                "role": ctx.role,
                "session_id": ctx.session_id,
            },
            "adapter": definition.adapter_id,
            "action": action.name,
            "kind": action.kind,
            "payload": _redact(payload, action.sse.redact_fields),
        }

        # SSE publish (best-effort).
        try:
            self._sse.publish(resolved_topic, envelope)
        except Exception as exc:  # pragma: no cover -- defensive
            logger.warning(
                "EventEmitter SSE publish failed: topic=%s id=%s err=%r",
                resolved_topic,
                envelope_id,
                exc,
            )

        # K0 cold-sync hand-off (best-effort, optional).
        if self._outbox is not None:
            try:
                self._outbox.enqueue(envelope)
            except Exception as exc:  # pragma: no cover -- defensive
                logger.warning(
                    "EventEmitter sync outbox enqueue failed: topic=%s id=%s err=%r",
                    resolved_topic,
                    envelope_id,
                    exc,
                )

        return envelope_id

    # ------------------------------------------------------------------ #
    # Typed convenience for entity writes
    # ------------------------------------------------------------------ #

    def emit_entity_write(
        self,
        definition: ToolDefinition,
        action: ActionSpec,
        op: str,
        entity: BaseEntity,
        ctx: WriteContext,
    ) -> str:
        """Convenience wrapper used by :class:`BaseToolService` for entity ops.

        Builds the standard payload shape ``{"op", "entity"}`` (with
        ``entity`` as a JSON dict via ``model_dump(mode='json')``) and
        delegates to :meth:`emit_write`.  ``op`` is one of
        ``"create" | "update" | "delete"`` per plan §E15.0.6.
        """

        payload: dict[str, Any] = {
            "op": op,
            "entity": entity.model_dump(mode="json"),
        }
        return self.emit_write(definition, action, payload, ctx)
