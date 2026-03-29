"""
k1.fabric.ports.delta_bus -- IDeltaBusPort port (5.1.6).

Delta emission port for agent state change broadcasting.

Design:
  - Agents emit deltas when their internal state changes (plan updates,
    context changes, tool results, etc.).
  - DeltaEmitter in agent_provider.py wraps this port, calling
    ``emit_delta()`` for each state mutation.
  - DeltaPayload: frozen dataclass carrying one delta event.
  - The bus itself (event routing, subscribers) is implemented by
    the adapter -- this port defines only the emission interface.

Consumers:
  - DeltaEmitter (k1/fabric/providers/agent_provider.py)
  - Agent internal loops (emit state changes via DeltaEmitter)

Production adapter: Delta Bus adapter (5.2)
Test adapter: CollectingDeltaBusAdapter (collects deltas for assertions)

References:
  - Agent Provider inline preview (agent_provider.py IDeltaBusPort)
  - DeltaEmitter class (agent_provider.py ~line 825)

Exports:
  IDeltaBusPort
  DeltaPayload
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Supporting types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeltaPayload:
    """
    A single delta event emitted by an agent.

    Attributes:
        agent_id: ID of the agent that produced the delta.
        delta_type: Type of delta (e.g. "plan_update", "context_change",
            "tool_result", "status_change").
        section: Section name this delta affects (e.g. "plan",
            "context", "tools").
        data: Arbitrary delta payload data.
        trace_id: Optional trace ID for observability (FAB-09).
    """

    agent_id: str = ""
    delta_type: str = ""
    section: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "agent_id": self.agent_id,
            "delta_type": self.delta_type,
            "section": self.section,
            "data": dict(self.data),
            "trace_id": self.trace_id,
        }

    @staticmethod
    def from_args(
        agent_id: str,
        delta_type: str,
        section: str,
        data: Dict[str, Any],
        trace_id: str = "",
    ) -> "DeltaPayload":
        """Build a DeltaPayload from positional args (matches emit_delta signature)."""
        return DeltaPayload(
            agent_id=agent_id,
            delta_type=delta_type,
            section=section,
            data=data,
            trace_id=trace_id,
        )


# ---------------------------------------------------------------------------
# Port protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class IDeltaBusPort(Protocol):
    """
    Delta emission port for agent state changes.

    This is the canonical port interface (5.1.6).  Any object with
    a matching ``emit_delta()`` signature satisfies this protocol
    (structural subtyping via ``typing.Protocol``).

    Agent Provider integration:
      DeltaEmitter wraps this port.  When an agent changes state,
      DeltaEmitter calls ``delta_bus.emit_delta(agent_id, delta_type,
      section, data)`` (see agent_provider.py ~line 702).

    Thread safety:
      ``emit_delta()`` MUST be safe for concurrent calls from
      multiple agents / asyncio tasks.

    Fire-and-forget semantics:
      ``emit_delta()`` is synchronous and must not block.  The bus
      adapter is responsible for buffering, batching, or async
      dispatch internally.
    """

    def emit_delta(
        self,
        agent_id: str,
        delta_type: str,
        section: str,
        data: Dict[str, Any],
    ) -> None:
        """
        Emit a delta event from an agent.

        Args:
            agent_id: The agent that produced the delta.
            delta_type: Type of state change (e.g. "plan_update").
            section: Which section of agent state changed.
            data: Arbitrary payload describing the change.
        """
        ...  # pragma: no cover
