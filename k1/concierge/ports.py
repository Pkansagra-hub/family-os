"""
k1.concierge.ports -- 8 Hexagonal Port Protocols for the Concierge subsystem.

Every signature below was traced from ACTUAL call sites in the codebase.
4 ports are re-exports of existing Protocols; 4 are new thin wrappers.

Existing (re-exported as aliases):
    ILLMPort            = IModelHubPort    (k1.model_hub.ports.hub_port)
    IDeltaPort          = IBus             (k1.bus.ports.bus)
    IFabricPort         (k1.concierge.fabric.ports) -- not aliased, re-exported

New (thin Protocols wrapping actual duck-typed surfaces):
    IInputPort   -- wraps bus→FSM user input path
    IOutputPort  -- wraps front→bus output emission path
    IStatePort   -- wraps the ss: Any duck-typed read surface
    IDispatchPort -- unifies IFabricPort + OrchestratorStub
    IMemoryPort  -- wraps the recall_fn: Callable closure
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Imports from canonical locations (NOT concierge.types -- avoid circular)
# ---------------------------------------------------------------------------
from k1.bus.envelope import Envelope
from k1.bus.ports.bus import IBus
from k1.concierge.fabric.ports import IFabricPort
from k1.concierge.orchestrator.types import AggregatedResult, TaskEnvelope
from k1.fabric.types import CapabilityRequest, CapabilityResult
from k1.model_hub.ports.hub_port import IModelHubPort
from k1.model_hub.types import HubChunk, HubRequest, HubResponse

# ===================================================================
# Re-exported Protocols (ALREADY EXIST — just aliased)
# ===================================================================

#: LLM port -- IModelHubPort Protocol from k1.model_hub.ports.hub_port.
#: Methods: execute(HubRequest)->HubResponse, stream_execute()->AsyncIterator[HubChunk]
#: Production: ModelHubPOCBridge(GeminiConciergeAdapter) | Test: TestModelHubBridge
ILLMPort = IModelHubPort

#: Delta/Bus port -- IBus Protocol from k1.bus.ports.bus.
#: Methods: publish(Envelope), subscribe(pattern, handler)->SubscriptionHandle, unsubscribe(handle)
#: Production: LocalBus (via BusFactory.create_local) | Test: LocalBus (same impl)
IDeltaPort = IBus


# ===================================================================
# New Protocols (thin wrappers around actual code surfaces)
# ===================================================================


@runtime_checkable
class IInputPort(Protocol):
    """Abstracts the transport→bus user input path.

    Reality: transport calls build_user_input() → Envelope → bus.publish()
             → FSM._on_user_input(envelope: Envelope)
    Source: k1/concierge/fsm/controller.py L1104, k1/concierge/bus/builders.py L214
    """

    async def receive(self) -> Envelope:
        """Block until next user input envelope arrives."""
        ...

    def has_buffered(self) -> bool:
        """True if there's a buffered envelope ready for immediate receive()."""
        ...


@runtime_checkable
class IOutputPort(Protocol):
    """Abstracts the front→bus response emission path.

    Reality: front.py calls bus.publish(build_final_response({...})) and
             bus.publish(build_response_stream({...}))
    Source: k1/concierge/actors/front.py L927, k1/concierge/bus/builders.py L244
    """

    async def send(self, envelope: Envelope) -> None:
        """Emit a response envelope to the output transport."""
        ...


@runtime_checkable
class IStatePort(Protocol):
    """Abstracts the SessionState read surface (ss: Any everywhere).

    Reality: ss.get_section(name) → section object with .to_prompt(), .get_all(), etc.
             Writes go through ctx.writer_port (MutationRequest-based), NOT here.
    Source: k1/concierge/tools/implementations.py L57, k1/concierge/actors/front.py
    """

    def get_section(self, name: str) -> Any:
        """Return a section object (supports .to_prompt(), .get_all(), etc.)."""
        ...

    def get_snapshot(self) -> dict[str, Any]:
        """Return all sections as a dict snapshot."""
        ...


@runtime_checkable
class IDispatchPort(Protocol):
    """Unifies Fabric (LOW tier) + Orchestrator (MED/HIGH tier) dispatch.

    Reality:
      LOW:  ctx.dispatch.dispatch_direct(CapabilityRequest) → CapabilityResult
      MED+: OrchestratorStub.handle_task(TaskEnvelope) → AggregatedResult
    Source: k1/concierge/fabric/ports.py, k1/concierge/orchestrator/stub.py
    """

    async def dispatch_direct(self, request: CapabilityRequest) -> CapabilityResult:
        """Execute a single capability via Fabric (LOW tier path)."""
        ...

    async def dispatch_envelope(self, envelope: TaskEnvelope) -> AggregatedResult:
        """Execute a task envelope via Orchestrator (MED/HIGH tier path)."""
        ...


@runtime_checkable
class IMemoryPort(Protocol):
    """Abstracts the recall_fn: Callable closure into a proper Protocol.

    Reality: recall_fn(query, memory_types, max_results) → list[dict]
             Built by _build_recall_fn() in bootstrap.py L726
    Source: k1/concierge/tools/implementations.py L553, k1/concierge/kernel/bootstrap.py L726
    """

    async def recall(
        self,
        query: str,
        memory_types: list[str] | None = None,
        max_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Recall memories matching query, filtered by type."""
        ...


# ===================================================================
# __all__ -- complete port surface
# ===================================================================

__all__ = [
    # Re-exported existing Protocols
    "ILLMPort",
    "IDeltaPort",
    "IFabricPort",
    # New Protocols
    "IInputPort",
    "IOutputPort",
    "IStatePort",
    "IDispatchPort",
    "IMemoryPort",
    # Re-exported types used in signatures
    "Envelope",
    "HubRequest",
    "HubResponse",
    "HubChunk",
    "CapabilityRequest",
    "CapabilityResult",
    "TaskEnvelope",
    "AggregatedResult",
]
