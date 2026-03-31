"""
k1.concierge.orchestrator.ports -- Port protocols for hexagonal architecture.

V2 Design Ref: Section 11.3 (OrchestratorStub constructor ports)
V2 Design Ref: Section 11.4.1 (HIGH tier deferred interfaces)

Production Reference: k1/orchestrator/ports/ (9 Protocol classes)

The POC defines simplified port protocols that mirror the production
k1/orchestrator/ports/ structure. These are runtime_checkable Protocol
classes following the hexagonal architecture pattern:

  - IFabricGatewayPort -- execute capabilities via Fabric
  - IStateReadPort     -- read-only Session State access (ORCH-01)
  - IDeltaEmitPort     -- emit events to the bus (fire-and-forget)

HIGH tier deferred ports (interface only, not used in MEDIUM):
  - IPlannerPort       -- request plans from the Planner
  - IWorkflowPort      -- run saved workflows
  - IConnectorPort     -- register MCP servers
  - IConstraintPort    -- resolve runtime parameters
  - ISagaPort          -- compensate on partial failure
  - IDispatchPort      -- dispatch TaskEnvelope to Orchestrator

Key design decisions:
  - All ports are Protocol classes (structural subtyping, no inheritance)
  - runtime_checkable for isinstance checks in tests
  - Methods are async to match production patterns
  - No k1.fabric imports -- POC uses its own CapabilityRequest/CapabilityResult
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from k1.concierge.orchestrator.types import (
    CapabilityRequest,
    CapabilityResult,
    PlanRequest,
    PlanStep,
    TaskEnvelope,
)

# =========================================================================
# Core ports -- used by OrchestratorStub (MEDIUM tier)
# =========================================================================


@runtime_checkable
class IFabricGatewayPort(Protocol):
    """Port for executing capabilities via the Fabric gateway.

    V2 Design Ref: Section 11.3 (step 4: execute via Fabric)
    Production Reference: k1/orchestrator/ports/fabric_gateway_port.py

    ORCH-04: Every execution step goes through Fabric.
    ORCH-10: Max 2 calls for MEDIUM tier.
    """

    async def execute(self, request: CapabilityRequest) -> CapabilityResult:
        """Execute a single capability request.

        Returns CapabilityResult with success flag and data/error.
        """
        ...

    async def execute_batch(self, requests: List[CapabilityRequest]) -> List[CapabilityResult]:
        """Execute multiple capability requests.

        Production reference: k1/orchestrator/ports/fabric_gateway_port.py
        """
        ...


@runtime_checkable
class IStateReadPort(Protocol):
    """Port for read-only Session State access.

    V2 Design Ref: Section 11.3 (step 2: read context snapshot)
    Production Reference: k1/orchestrator/ports/state_read_port.py

    CRITICAL INVARIANT: ORCH-01 -- NO write methods on this port.
    The Orchestrator NEVER writes to Session State. This is enforced
    structurally: there is no IStateWritePort injected into the
    OrchestratorStub.
    """

    async def snapshot(self, sections: List[str]) -> Dict[str, Any]:
        """Read a snapshot of the specified Session State sections.

        Args:
            sections: List of SS section names (e.g. ["beliefs_active",
                      "task_artifacts"]).

        Returns:
            Dict mapping section name to section data. Missing sections
            return empty dict values.
        """
        ...

    async def read_section(self, session_id: str, section: str) -> Optional[Dict[str, Any]]:
        """Read a single Session State section.

        Production reference: k1/orchestrator/ports/state_read_port.py
        """
        ...


@runtime_checkable
class IDeltaEmitPort(Protocol):
    """Port for emitting events to the bus (fire-and-forget).

    V2 Design Ref: Section 11.3 (step 1: emit acceptance, step 6: emit completion)
    Production Reference: k1/orchestrator/ports/delta_emit_port.py

    Fire-and-forget semantics. The caller does not wait for delivery
    confirmation. Events are best-effort.
    """

    async def emit(self, event_topic: str, payload: Any, trace_id: str = "") -> None:
        """Emit an event to the bus.

        Args:
            event_topic: Event topic string (e.g. "k1.orchestration.task.accepted")
            payload: Event payload (dict or dataclass)
            trace_id: Trace identifier for correlation
        """
        ...


# =========================================================================
# Dispatch port -- route TaskEnvelope to Orchestrator
# =========================================================================


@runtime_checkable
class IDispatchPort(Protocol):
    """Port for dispatching TaskEnvelope to the Orchestrator.

    V2 Design Ref: Section 11.2 (route_task dispatches via dispatch_port)
    """

    async def dispatch_envelope(self, envelope: TaskEnvelope) -> None:
        """Dispatch a TaskEnvelope for execution.

        MEDIUM: handled by OrchestratorStub
        HIGH: handled by full Orchestrator (future)
        """
        ...


# =========================================================================
# HIGH Tier Deferred Ports (interface only -- not implemented in POC)
# =========================================================================


@runtime_checkable
class IPlannerPort(Protocol):
    """Port for requesting plans from the Planner.

    V2 Design Ref: Section 11.4.1 (Planner interface)
    Production Reference: k1/orchestrator/ports/planner_port.py

    POC: interface only, not implemented. HIGH tier only.

    Event flow (HIGH tier, future):
      Orchestrator -> PlanRequest -> Planner Mailbox
      Planner: SKETCH -> EXPAND -> VALIDATE -> COMMIT
      Planner emits: k1.planner.plan.ready.v1 (CommittedPlan)
    """

    async def request_plan(self, request: PlanRequest) -> str:
        """Submit a PlanRequest. Returns request_id (PlanAck).

        Result arrives async via k1.planner.plan.ready.v1 event.
        """
        ...

    async def cancel_plan(self, request_id: str) -> None:
        """Cancel a pending plan request."""
        ...


@runtime_checkable
class IWorkflowPort(Protocol):
    """Port for running saved workflows.

    V2 Design Ref: Section 11.4.1 (WorkflowEngine interface)
    POC: interface only.
    """

    async def run(self, request: Any) -> Any:
        """Execute a saved workflow."""
        ...


@runtime_checkable
class IConnectorPort(Protocol):
    """Port for registering MCP servers.

    V2 Design Ref: Section 11.4.1 (ConnectorManager interface)
    POC: interface only.
    """

    async def register(self, mcp_server: dict) -> None:
        """Register an MCP server with the connector manager."""
        ...


@runtime_checkable
class IConstraintPort(Protocol):
    """Port for resolving runtime parameters.

    V2 Design Ref: Section 11.4.1 (ConstraintResolver interface)
    POC: interface only.
    """

    async def resolve(self, step: PlanStep, context: dict) -> dict:
        """Resolve runtime parameters for a plan step."""
        ...


@runtime_checkable
class ISagaPort(Protocol):
    """Port for compensating on partial failure.

    V2 Design Ref: Section 11.4.1 (Saga Recovery interface)
    POC: interface only.
    """

    async def compensate(self, failed_step: PlanStep, completed_steps: List[PlanStep]) -> None:
        """Compensate (rollback) after a step failure.

        Executes the compensation capability for each completed step
        that has side effects and a defined compensation action.
        """
        ...
