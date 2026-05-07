"""MS-3b Epic 3b.4 \u2014 ``OnlineFirstClient`` decorator.

Wraps a generated K1 client (e.g. ``MemoryWriteV1Client``) and adds
offline-first semantics:

* ONLINE  \u2192 dispatch through the inner client; on transient ``5xx`` /
  transport error, queue if the matrix says so, otherwise propagate.
* OFFLINE / DEGRADED \u2192 consult the auto-derived
  :class:`bridge.core.degraded.DegradedMatrix`:
  - ``QUEUE_TO_OUTBOX``         \u2192 build + sign the envelope NOW and
                                  enqueue (drain worker replays later).
  - ``RAISE_OFFLINE_ERROR``     \u2192 raise :class:`OfflineError`.
  - ``DROP_WITH_METRIC_AFTER_TTL`` \u2192 enqueue with TTL; drain prunes
                                  if K0 stays away past ``max_queue_age``.
  - ``MARK_STREAM_CLOSED`` /
    ``N_A_SUBSCRIBER_SIDE``    \u2192 raise :class:`OfflineError` (this
                                  decorator is producer-side only).

Per global rule R10 (DEGRADED policy auto-derived only): this decorator
contains no hand-coded ``if state == OFFLINE:`` business branches \u2014 it
delegates every per-call decision to ``DegradedMatrix.behavior_for_state``.
The ``health_state == K0HealthState.ONLINE`` early-return is a structural
invariant of the decorator, not a policy branch.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from .degraded import DegradedBehavior, DegradedMatrix
from .health import K0HealthState
from .transport import BridgeTransportError

if TYPE_CHECKING:  # pragma: no cover \u2014 typing only
    from pydantic import BaseModel

    from ..sync.local_outbox import LocalOutbox
    from .health import K0HealthChecker
    from .transport import HttpTransport


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# OfflineError
# ---------------------------------------------------------------------------


class OfflineError(RuntimeError):
    """Raised when an ``online_required`` contract is published while K0
    is not :class:`K0HealthState.ONLINE`.

    Attributes
    ----------
    topic:
        The contract topic that was being published.
    current_state:
        The K0 health state at the time of the call.
    behavior:
        The matrix-derived :class:`DegradedBehavior` (helps the caller
        understand whether the contract was meant to queue or raise).
    """

    def __init__(
        self,
        *,
        topic: str,
        current_state: K0HealthState,
        behavior: DegradedBehavior | None = None,
    ) -> None:
        self.topic = topic
        self.current_state = current_state
        self.behavior = behavior
        msg = (
            f"OfflineError: cannot publish topic={topic!r} \u2014 "
            f"K0 is {current_state.value}; behavior={behavior.value if behavior else 'n/a'}"
        )
        super().__init__(msg)


# ---------------------------------------------------------------------------
# OnlineFirstClient
# ---------------------------------------------------------------------------

# Parse ISO-8601 PT...H/M/S duration strings used by the manifest's
# ``delivery.max_queue_age`` field. The set is small \u2014 PTnH, PTnM, PTnS,
# combined like PT1H30M \u2014 so a tiny regex suffices.
_DURATION_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def _parse_iso8601_duration_to_s(text: str | None) -> int | None:
    if not text:
        return None
    m = _DURATION_RE.fullmatch(text)
    if not m:
        return None
    h, mn, s = (int(g) if g else 0 for g in m.groups())
    total = h * 3600 + mn * 60 + s
    return total if total > 0 else None


class OnlineFirstClient:
    """Producer-side offline-first wrapper for a single contract client.

    Parameters
    ----------
    inner:
        Generated client object exposing ``async publish(payload)`` (e.g.
        :class:`bridge._generated.k1.clients.memory_write_v1.MemoryWriteV1Client`).
    topic:
        Contract topic (must match ``inner.__topic__``).
    schema_uri:
        Schema URI for envelope construction (must match
        ``inner.__schema_uri__``).
    port_kind:
        Port classification (``"command"``/``"query"``/...). Used to key
        into :class:`DegradedMatrix`.
    transport:
        :class:`HttpTransport` used to build envelopes when queueing.
    outbox:
        :class:`LocalOutbox` to enqueue offline envelopes into.
    health:
        :class:`K0HealthChecker` whose ``status`` drives the decision.
    matrix:
        :class:`DegradedMatrix` whose ``behavior_for_state`` selects the
        per-call policy.
    max_queue_age_s:
        Optional per-row TTL forwarded to ``LocalOutbox.enqueue``.
    """

    def __init__(
        self,
        *,
        inner: Any,
        topic: str,
        schema_uri: str,
        port_kind: str,
        transport: "HttpTransport",
        outbox: "LocalOutbox",
        health: "K0HealthChecker",
        matrix: DegradedMatrix,
        max_queue_age_s: int | None = None,
    ) -> None:
        self._inner = inner
        self._topic = topic
        self._schema_uri = schema_uri
        self._port_kind = port_kind
        self._transport = transport
        self._outbox = outbox
        self._health = health
        self._matrix = matrix
        self._max_queue_age_s = max_queue_age_s

    # -- factory ---------------------------------------------------------

    @classmethod
    def from_manifest(
        cls,
        *,
        inner: Any,
        manifest_raw: dict[str, Any],
        port_kind: str,
        transport: "HttpTransport",
        outbox: "LocalOutbox",
        health: "K0HealthChecker",
        matrix: DegradedMatrix,
    ) -> "OnlineFirstClient":
        """Construct from the raw manifest dict (handles ``max_queue_age``)."""
        delivery = manifest_raw.get("delivery", {})
        max_queue_age_s = _parse_iso8601_duration_to_s(delivery.get("max_queue_age"))
        return cls(
            inner=inner,
            topic=getattr(inner, "__topic__", manifest_raw.get("topic")),
            schema_uri=getattr(inner, "__schema_uri__", ""),
            port_kind=port_kind,
            transport=transport,
            outbox=outbox,
            health=health,
            matrix=matrix,
            max_queue_age_s=max_queue_age_s,
        )

    # -- API mirror -----------------------------------------------------

    async def publish(self, payload: "BaseModel") -> Any:
        state = self._health.status
        behavior_when_offline = self._matrix.behavior_for_state(self._port_kind, self._topic, state)

        if behavior_when_offline is None:  # ONLINE \u2014 try the wire.
            try:
                return await self._inner.publish(payload)
            except BridgeTransportError as exc:
                if exc.status_code == 0 or exc.status_code >= 500:
                    online_behavior = self._matrix.behavior_for(self._port_kind, self._topic)
                    if online_behavior is DegradedBehavior.QUEUE_TO_OUTBOX:
                        self._enqueue(payload)
                        logger.warning(
                            "OnlineFirstClient: queued topic=%s after transient %d",
                            self._topic,
                            exc.status_code,
                        )
                        return None
                # 4xx \u2014 contract violation, never queue. Propagate.
                raise

        if behavior_when_offline in (
            DegradedBehavior.QUEUE_TO_OUTBOX,
            DegradedBehavior.DROP_WITH_METRIC_AFTER_TTL,
        ):
            self._enqueue(payload)
            return None

        raise OfflineError(
            topic=self._topic,
            current_state=state,
            behavior=behavior_when_offline,
        )

    # -- helpers --------------------------------------------------------

    def _enqueue(self, payload: "BaseModel") -> int:
        envelope_bytes = self._transport.build_envelope_bytes(
            topic=self._topic,
            schema_uri=self._schema_uri,
            payload=payload,
        )
        return self._outbox.enqueue(
            envelope_bytes.decode("utf-8"),
            self._topic,
            max_queue_age_s=self._max_queue_age_s,
        )
