"""MS-3b Epic 3b.2 \u2014 Auto-derived DEGRADED matrix.

The matrix maps every ``(port, topic)`` to a :class:`DegradedBehavior`
*derived* from the manifest at runtime construction time. No code branch
elsewhere in the bridge is allowed to inspect the health state with a
hand-coded ``if degraded:`` \u2014 the
``degraded_mode_derived_only`` CI gate (also in this epic) walks the
source tree and fails on such patterns. All offline-policy decisions
flow through :meth:`DegradedMatrix.behavior_for`.

Behavior derivation rules (operative for the manifests that ship today
and the ones queued for MS-3c/d/e):

============================  ================================
Manifest signal               Derived behavior
============================  ================================
``delivery.online_required``  ``RAISE_OFFLINE_ERROR``
``= true``
----------------------------  --------------------------------
``online_required = false``   ``QUEUE_TO_OUTBOX``
+ ``max_queue_age`` set
----------------------------  --------------------------------
direction ``k0_to_k1`` +      ``MARK_STREAM_CLOSED``
SSE-class transport
----------------------------  --------------------------------
direction ``k0_to_k1``        ``N_A_SUBSCRIBER_SIDE``
(generic)
----------------------------  --------------------------------
``delivery.priority_drop``    ``DROP_WITH_METRIC_AFTER_TTL``
+ ``max_queue_age``
----------------------------  --------------------------------
fallback                      ``RAISE_OFFLINE_ERROR`` (safe)
============================  ================================

The legacy :class:`bridge.core.health.DegradedModeManager` is *not*
replaced by this module \u2014 it survives for ``SinkBridgeClient`` (the
offline fallback). New code (``OnlineFirstCommandPort``, drain worker,
runtime) uses :class:`DegradedMatrix`.
"""

from __future__ import annotations

import enum
import logging
from typing import TYPE_CHECKING, Any

from .health import K0HealthState

if TYPE_CHECKING:
    from .events import EventBus, HealthTransition

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Behavior enum
# ---------------------------------------------------------------------------


class DegradedBehavior(str, enum.Enum):
    """Per-``(port, topic)`` action when K0 is not ONLINE.

    String-valued so ``/healthz`` and metric labels render the value
    directly without an enum-dance.
    """

    QUEUE_TO_OUTBOX = "queue_to_outbox"
    RAISE_OFFLINE_ERROR = "raise_offline_error"
    MARK_STREAM_CLOSED = "mark_stream_closed"
    DROP_WITH_METRIC_AFTER_TTL = "drop_with_metric_after_ttl"
    N_A_SUBSCRIBER_SIDE = "n_a_subscriber_side"


# ---------------------------------------------------------------------------
# Port kind heuristic (manifest \u2192 port)
# ---------------------------------------------------------------------------


def _infer_port_kind(manifest_raw: dict[str, Any]) -> str:
    """Best-effort port classification from manifest fields.

    The meta-schema does not yet expose an explicit port enum, so we
    derive it from ``direction`` + ``delivery``. The MS-3b plan calls
    out an upcoming ``delivery.priority_tier`` field; we read it
    opportunistically.
    """
    direction = manifest_raw.get("direction", "")
    delivery = manifest_raw.get("delivery", {})
    transport = delivery.get("transport", "")
    if direction == "k0_to_k1":
        if transport == "sse" or "sse" in transport:
            return "sse"
        return "obs"  # subscriber-side default
    # k1_to_k0 family
    if delivery.get("kind") == "obs" or "obs" in transport:
        return "obs"
    if delivery.get("kind") == "query":
        return "query"
    if delivery.get("kind") == "gateway" or transport == "ifl":
        return "gateway"
    return "command"


def _derive_behavior(manifest_raw: dict[str, Any]) -> DegradedBehavior:
    """Compute the offline behavior for one manifest.

    Pure function over the manifest fields \u2014 no health state. The
    health state is consulted at *call* time inside
    :meth:`DegradedMatrix.behavior_for_state`.
    """
    direction = manifest_raw.get("direction", "")
    delivery = manifest_raw.get("delivery", {})
    online_required = bool(delivery.get("online_required", False))
    max_queue_age = delivery.get("max_queue_age")
    transport = delivery.get("transport", "")

    if direction == "k0_to_k1":
        if transport == "sse" or "sse" in transport:
            return DegradedBehavior.MARK_STREAM_CLOSED
        return DegradedBehavior.N_A_SUBSCRIBER_SIDE

    if online_required:
        return DegradedBehavior.RAISE_OFFLINE_ERROR

    # Obs-class with TTL drops (priority-tier-aware)
    if delivery.get("priority_drop") and max_queue_age is not None:
        return DegradedBehavior.DROP_WITH_METRIC_AFTER_TTL
    if delivery.get("kind") == "obs" and max_queue_age is not None:
        return DegradedBehavior.DROP_WITH_METRIC_AFTER_TTL

    if max_queue_age is not None:
        return DegradedBehavior.QUEUE_TO_OUTBOX

    # Safe fallback: raise rather than silently drop.
    return DegradedBehavior.RAISE_OFFLINE_ERROR


# ---------------------------------------------------------------------------
# DegradedMatrix
# ---------------------------------------------------------------------------


class DegradedMatrix:
    """Auto-derived ``(port, topic) \u2192 DegradedBehavior`` lookup.

    Built once at runtime construction from the loaded manifest list.
    Subscribes to :class:`bridge.core.events.HealthTransition` to keep a
    live ``degraded_topics()`` view for ``/healthz`` rendering. The
    decision functions are pure lookups \u2014 no health-state branching.

    Parameters
    ----------
    manifests:
        Sequence of :class:`bridge.contracts` manifest objects (anything
        exposing ``.topic`` and ``.raw``) or raw dicts.
    event_bus:
        Optional bus to subscribe to health transitions. If omitted,
        ``degraded_topics()`` derives the active set from a manually
        injected health state via :meth:`set_health_state`.
    initial_state:
        Health state to start in (defaults to ``OFFLINE`` \u2014 the
        runtime hasn't probed yet).
    """

    def __init__(
        self,
        manifests: list[Any],
        *,
        event_bus: "EventBus | None" = None,
        initial_state: K0HealthState = K0HealthState.OFFLINE,
    ) -> None:
        self._matrix: dict[tuple[str, str], DegradedBehavior] = {}
        self._behavior_per_topic: dict[str, DegradedBehavior] = {}
        self._port_per_topic: dict[str, str] = {}
        for m in manifests:
            raw = getattr(m, "raw", None) or (m if isinstance(m, dict) else {})
            topic = raw.get("topic") or getattr(m, "topic", None)
            if not topic:
                continue
            port = _infer_port_kind(raw)
            behavior = _derive_behavior(raw)
            self._matrix[(port, topic)] = behavior
            self._behavior_per_topic[topic] = behavior
            self._port_per_topic[topic] = port

        self._state = initial_state
        self._event_bus = event_bus
        self._subscriber_queue = None
        self._subscriber_task = None
        if event_bus is not None:
            from .events import HealthTransition

            self._subscriber_queue = event_bus.subscribe(HealthTransition)

    # -- decision API ------------------------------------------------------

    def behavior_for(self, port: str, topic: str) -> DegradedBehavior:
        """O(1) lookup. Raises :class:`KeyError` for unknown ``(port, topic)``."""
        try:
            return self._matrix[(port, topic)]
        except KeyError:
            # Be lenient on port (callers may pass "command" for a contract
            # we classified as "query" because the schema lacks an explicit
            # port field). Fall back to topic-only lookup.
            if topic in self._behavior_per_topic:
                return self._behavior_per_topic[topic]
            raise

    def behavior_for_state(
        self, port: str, topic: str, state: K0HealthState
    ) -> DegradedBehavior | None:
        """Behavior to apply *given a particular state*.

        Returns ``None`` when the matrix has no opinion (state ONLINE or
        the topic is subscriber-side). Used by the OnlineFirst decorator
        and the SSE consumer.
        """
        if state is K0HealthState.ONLINE:
            return None
        return self.behavior_for(port, topic)

    # -- live view --------------------------------------------------------

    def set_health_state(self, state: K0HealthState) -> None:
        """Manual state override (tests + the runtime when no bus is wired)."""
        self._state = state

    @property
    def health_state(self) -> K0HealthState:
        return self._state

    def consume_pending_events(self) -> None:
        """Drain queued :class:`HealthTransition` events into ``_state``.

        Called synchronously by ``/healthz`` and by tests; the runtime
        also calls this on transition. Avoids spawning a long-running
        background task here \u2014 the bus delivers events into a queue,
        and this method advances the matrix in lock-step.
        """
        if self._subscriber_queue is None:
            return
        latest_state = self._state
        while not self._subscriber_queue.empty():
            try:
                evt = self._subscriber_queue.get_nowait()
            except Exception:  # pragma: no cover \u2014 defensive
                break
            try:
                latest_state = K0HealthState(evt.to_state)
            except ValueError:
                continue
        self._state = latest_state

    def degraded_topics(self) -> set[str]:
        """Set of topics whose behavior is *currently* applied.

        Empty when the health state is ONLINE; otherwise every
        producer-side topic with a non-``N_A_SUBSCRIBER_SIDE`` behavior.
        """
        self.consume_pending_events()
        if self._state is K0HealthState.ONLINE:
            return set()
        return {
            topic
            for topic, behavior in self._behavior_per_topic.items()
            if behavior is not DegradedBehavior.N_A_SUBSCRIBER_SIDE
        }

    def topics(self) -> list[str]:
        """All topics the matrix knows about (sorted)."""
        return sorted(self._behavior_per_topic)

    def healthz_payload(self) -> dict[str, Any]:
        """Render the live view for the ``/healthz`` JSON body."""
        self.consume_pending_events()
        return {
            "health_state": self._state.value,
            "degraded_topics": sorted(self.degraded_topics()),
            "behaviors": {
                topic: behavior.value
                for topic, behavior in sorted(self._behavior_per_topic.items())
            },
        }
