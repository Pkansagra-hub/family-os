"""
k1.orchestrator.ports.fabric_gateway_port -- IFabricGatewayPort port (1.4.2).

Async gateway to the Capability Fabric for step execution and registry queries.

Design:
  - All methods ASYNC (Fabric calls involve I/O).
  - Adapter is pure pass-through that translates Fabric errors into
    AdapterError(DEGRADED). Adapter does NOT own a circuit breaker
    (per PROTOCOL-4: Concierge owns CB_FABRIC).
  - V1: no spawn() method. Meta-agent spawn flows through regular
    execute() with ``agent.build`` capability.

Consumers:
  - OrchestratorService.dispatch_medium() (2.1.3) -- direct execute/execute_batch
  - DAGExecutor.execute_wave() (2.2.2) -- step dispatch via StepRunner
  - StepRunner.run() (2.3.1) -- single step execution
  - ConstraintResolver (3.1.1) -- query_registry for validation
  - Saga compensation (2.2.5) -- execute compensation capabilities

Production adapter: FabricGatewayAdapter (6.1.2) in adapters/fabric_gateway_adapter.py
Test adapter: MockFabricAdapter (6.1.9) in adapters/mock_fabric_adapter.py

References:
  - ORCH-004 (all steps via Fabric)
  - ORCH-002 (hexagonal port/adapter)

Exports:
  IFabricGatewayPort
"""

from __future__ import annotations

from typing import List, Optional, Protocol, runtime_checkable

from k1.fabric.types import CapabilityRequest, CapabilityResult
from k1.orchestrator.types import RegistryEntry

# ---------------------------------------------------------------------------
# Port protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class IFabricGatewayPort(Protocol):
    """
    Async gateway port to the Capability Fabric.

    Provides step execution and capability registry queries. All
    capability invocations flow through this port (ORCH-04: all
    steps via Fabric).

    The adapter implementation translates Fabric-side errors into
    ``AdapterError(DEGRADED)`` for the ErrorRouter. The adapter
    does NOT own a circuit breaker -- CB_FABRIC is owned by the
    Concierge-side FabricOrchestratorAdapter (PROTOCOL-4).

    Thread safety:
      Implementations MUST support concurrent ``execute()`` calls
      from multiple asyncio tasks (DAG wave parallel dispatch).
    """

    async def execute(
        self,
        request: CapabilityRequest,
    ) -> CapabilityResult:
        """
        Execute a single capability via Fabric.

        Args:
            request: The capability request to execute.

        Returns:
            CapabilityResult from Fabric.

        Raises:
            AdapterError: With severity DEGRADED if Fabric returns
                an error or is unreachable.
        """
        ...  # pragma: no cover

    async def execute_batch(
        self,
        requests: List[CapabilityRequest],
    ) -> List[CapabilityResult]:
        """
        Execute multiple capabilities in parallel via Fabric.

        Uses ``asyncio.gather()`` internally. Order of results
        matches order of requests. If one request fails, others
        still complete (partial failure model).

        Args:
            requests: List of capability requests to execute.

        Returns:
            List of CapabilityResult in the same order as requests.
            Failed requests have ``success=False`` in their result.

        Raises:
            AdapterError: With severity DEGRADED if Fabric is
                completely unreachable (all requests fail).
        """
        ...  # pragma: no cover

    async def query_registry(
        self,
        capability_name: str,
    ) -> Optional[RegistryEntry]:
        """
        Check the Fabric CapabilityRegistry for a capability.

        Args:
            capability_name: The capability name to look up
                (e.g. ``"tool.calendar.search"``).

        Returns:
            RegistryEntry with capability metadata if found,
            ``None`` if the capability is not registered.

        Raises:
            AdapterError: With severity DEGRADED if the registry
                is unreachable.
        """
        ...  # pragma: no cover

    async def query_registry_by_category(
        self,
        category_prefix: str,
    ) -> List[RegistryEntry]:
        """
        Query the Fabric CapabilityRegistry for capabilities in a category.

        Used by ConstraintResolver.find_alternatives() (3.1.3) to discover
        same-category alternatives for missing capabilities.

        Category is derived from capability naming convention:
        ``tool.{type}.{domain}.*`` -> prefix ``tool.{type}.{domain}``.

        Args:
            category_prefix: The category prefix to search for
                (e.g. ``"tool.calendar"`` to find all calendar tools).

        Returns:
            List of RegistryEntry for capabilities matching the
            category prefix. Empty list if no matches found.

        Raises:
            AdapterError: With severity DEGRADED if the registry
                is unreachable.
        """
        ...  # pragma: no cover
