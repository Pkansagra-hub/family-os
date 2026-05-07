"""
k1.fabric.adapters.delta_bus_prod -- Production DeltaBusProdAdapter.

Implements IDeltaBusPort for production by forwarding delta emissions
to the K1 bus (IBus) as serialized Envelopes.

Design:
  - Wraps an IBus instance (typed as ``Any`` for loose coupling).
  - ``emit_delta()`` builds an Envelope with topic
    ``k1.agent.{agent_id}.delta.v1`` and JSON-serialized DeltaPayload.
  - Fire-and-forget: never raises, logs on serialization error.
  - Thread-safe: delegates to IBus which is thread-safe.

Consumers:
  - DeltaEmitter (k1/fabric/providers/agent_provider.py)
  - Injected via FabricFactory.create_with_ports(delta_bus=...)

Structural subtyping:
  Satisfies IDeltaBusPort protocol without inheriting from it.

References:
  - IDeltaBusPort (5.1.6)
  - FabricBusAdapter (k1/bus/adapters/fabric_adapter.py) -- same
    serialization pattern, but this adapter lives in Fabric's layer.
  - TestDeltaBusAdapter (5.2.6) -- test counterpart

Exports:
  DeltaBusProdAdapter
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Dict

logger = logging.getLogger(__name__)


class DeltaBusProdAdapter:
    """
    Production delta bus adapter for Fabric's IDeltaBusPort.

    Wraps an IBus instance and forwards ``emit_delta()`` calls as
    serialized Envelopes on the bus.  Thread-safe.

    Implements ``IDeltaBusPort`` via structural subtyping:
      - emit_delta(agent_id, delta_type, section, data) -> None
    """

    __slots__ = ("_bus", "_lock", "_emit_count")

    def __init__(self, bus: Any) -> None:
        """
        Initialize with a bus instance.

        Args:
            bus: An IBus-compatible object with ``publish(envelope)``
                method.  Typed as ``Any`` for loose coupling --
                the bus layer is an external dependency.
        """
        self._bus = bus
        self._lock = threading.RLock()
        self._emit_count = 0

    # ------------------------------------------------------------------
    # IDeltaBusPort protocol method
    # ------------------------------------------------------------------

    def emit_delta(
        self,
        agent_id: str,
        delta_type: str,
        section: str,
        data: Dict[str, Any],
    ) -> None:
        """
        Emit a delta event from an agent to the bus.

        Publishes to topic ``k1.agent.{agent_id}.delta.v1`` with the
        delta payload serialized as JSON bytes inside an Envelope.

        Fire-and-forget: never raises.  Serialization errors are logged
        and silently dropped.

        Args:
            agent_id:   The agent that produced the delta.
            delta_type: Type of state change (e.g. "plan_update").
            section:    Which section of agent state changed.
            data:       Arbitrary payload describing the change.
        """
        with self._lock:
            self._emit_count += 1

        topic = f"k1.agent.{agent_id}.delta.v1"
        payload_dict = {
            "agent_id": agent_id,
            "delta_type": delta_type,
            "section": section,
            "data": data,
        }

        try:
            raw = json.dumps(payload_dict, separators=(",", ":"), default=str).encode("utf-8")
        except (TypeError, ValueError):
            logger.warning(
                "DeltaBusProdAdapter: failed to serialize delta for "
                "agent=%s delta_type=%s section=%s",
                agent_id,
                delta_type,
                section,
                exc_info=True,
            )
            return

        try:
            from k1.bus.envelope.envelope import Envelope, Priority

            self._bus.publish(
                Envelope(
                    topic=topic,
                    payload=raw,
                    priority=Priority.REALTIME,
                )
            )
        except Exception:
            logger.warning(
                "DeltaBusProdAdapter: failed to publish delta for " "agent=%s topic=%s",
                agent_id,
                topic,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def emit_count(self) -> int:
        """Number of emit_delta() calls made."""
        with self._lock:
            return self._emit_count

    @property
    def bus(self) -> Any:
        """Access the underlying bus instance."""
        return self._bus

    def __repr__(self) -> str:
        with self._lock:
            return f"DeltaBusProdAdapter(bus={self._bus!r}, " f"emits={self._emit_count})"


__all__ = ["DeltaBusProdAdapter"]
