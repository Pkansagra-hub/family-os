"""
k1.orchestrator.adapters.fabric_gateway_adapter -- FabricGatewayAdapter (6.1.2).

Production adapter for IFabricGatewayPort.

Design:
  - Wraps the ``Fabric`` facade class (``k1.fabric.fabric.Fabric``).
  - ``execute()`` delegates to ``Fabric.execute(request)``.
  - ``execute_batch()`` delegates to ``Fabric.execute_batch(requests, PARALLEL)``.
    Falls back to ``asyncio.gather`` if Fabric batch raises.
  - ``query_registry()`` maps ``CapabilityContract`` -> ``RegistryEntry``
    (Orchestrator's lightweight view).
  - ``query_registry_by_category()`` uses ``Fabric.registry_api.list_all()``
    and filters by capability name prefix.
  - Adapter is pure pass-through: translates errors, no circuit breaking
    (per PROTOCOL-4: Concierge owns CB_FABRIC).

Error Mapping:
  - FabricError / timeout    -> AdapterError(DEGRADED, "Fabric timeout")
  - ConnectionError          -> AdapterError(DEGRADED, "Fabric unreachable")
  - Unknown exception        -> AdapterError(TERMINAL, str(e))

References:
  - Issue 6.1.2 in orchestrator-implementation-plan.md
  - ORCH-004 (all steps via Fabric)
  - PROTOCOL-4 (CB_FABRIC owned by Concierge)

Exports:
  FabricGatewayAdapter
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, List, Optional

from k1.fabric.fabric import BatchStrategy, Fabric, FabricError
from k1.fabric.types import CapabilityRequest, CapabilityResult
from k1.orchestrator.orchestration.orchestrator_service import AdapterException
from k1.orchestrator.types import AdapterError, ErrorSeverity, RegistryEntry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 6.1.2 -- FabricGatewayAdapter
# ---------------------------------------------------------------------------


class FabricGatewayAdapter:
    """
    Production IFabricGatewayPort adapter wrapping the Fabric facade.

    Pure pass-through: translates Fabric errors into ``AdapterError``
    for the ErrorRouter.  Does NOT own a circuit breaker (PROTOCOL-4).

    Constructor Args:
        fabric: Fully-constructed ``Fabric`` instance (created by
            FabricFactory and injected by OrchestratorFactory).

    Thread Safety:
        Safe for concurrent ``execute()`` calls from multiple asyncio
        tasks (DAG wave parallel dispatch).  Fabric itself is thread-safe.
    """

    __slots__ = ("_fabric",)

    def __init__(self, fabric: Fabric) -> None:
        self._fabric = fabric

    # ==================================================================
    # IFabricGatewayPort implementation
    # ==================================================================

    async def execute(
        self,
        request: CapabilityRequest,
    ) -> CapabilityResult:
        """
        Execute a single capability via Fabric.

        Delegates to ``Fabric.execute(request)``.  On error, maps
        to AdapterError with appropriate severity.

        Args:
            request: The capability request to execute.

        Returns:
            CapabilityResult from Fabric.

        Raises:
            AdapterError: DEGRADED on Fabric error/timeout,
                TERMINAL on unknown errors.
        """
        try:
            return await self._fabric.execute(request)
        except (FabricError, asyncio.TimeoutError) as exc:
            raise AdapterException(
                AdapterError(
                    severity=ErrorSeverity.DEGRADED,
                    adapter_name="fabric_gateway",
                    operation="execute",
                    error_code="FABRIC_ERROR",
                    error_message=f"Fabric error: {exc}",
                    original_exception=exc,
                    trace_id=getattr(request, "trace_id", ""),
                )
            ) from exc
        except ConnectionError as exc:
            raise AdapterException(
                AdapterError(
                    severity=ErrorSeverity.DEGRADED,
                    adapter_name="fabric_gateway",
                    operation="execute",
                    error_code="FABRIC_UNREACHABLE",
                    error_message=f"Fabric unreachable: {exc}",
                    original_exception=exc,
                    trace_id=getattr(request, "trace_id", ""),
                )
            ) from exc
        except Exception as exc:
            raise AdapterException(
                AdapterError(
                    severity=ErrorSeverity.TERMINAL,
                    adapter_name="fabric_gateway",
                    operation="execute",
                    error_code="FABRIC_UNKNOWN",
                    error_message=str(exc),
                    original_exception=exc,
                    trace_id=getattr(request, "trace_id", ""),
                )
            ) from exc

    async def execute_batch(
        self,
        requests: List[CapabilityRequest],
    ) -> List[CapabilityResult]:
        """
        Execute multiple capabilities in parallel via Fabric.

        Delegates to ``Fabric.execute_batch(requests, PARALLEL)``.
        Falls back to ``asyncio.gather`` if Fabric batch API raises.
        Order preserved.  Partial failures: failed requests get
        ``CapabilityResult(success=False)``.

        Args:
            requests: List of capability requests.

        Returns:
            List of CapabilityResult in request order.
        """
        if not requests:
            return []

        try:
            return await self._fabric.execute_batch(
                requests,
                BatchStrategy.PARALLEL,
            )
        except Exception:
            logger.warning(
                "Fabric batch API failed; falling back to asyncio.gather",
                exc_info=True,
            )
            # Fallback: parallel gather with individual error handling
            results = await asyncio.gather(
                *(self._execute_single_safe(r) for r in requests),
                return_exceptions=False,
            )
            return list(results)

    async def query_registry(
        self,
        capability_name: str,
    ) -> Optional[RegistryEntry]:
        """
        Look up a capability in Fabric's registry.

        Delegates to ``Fabric.lookup(capability_name)``.  Maps the
        full ``CapabilityContract`` to ``RegistryEntry`` (Orchestrator's
        lightweight view).

        Args:
            capability_name: Canonical capability name.

        Returns:
            RegistryEntry if found, ``None`` otherwise.

        Raises:
            AdapterError: DEGRADED if registry is unreachable.
        """
        try:
            contract = self._fabric.lookup(capability_name)
            if contract is None:
                return None
            return self._contract_to_entry(contract)
        except Exception as exc:
            raise AdapterException(
                AdapterError(
                    severity=ErrorSeverity.DEGRADED,
                    adapter_name="fabric_gateway",
                    operation="query_registry",
                    error_code="REGISTRY_ERROR",
                    error_message=f"Registry lookup failed: {exc}",
                    original_exception=exc,
                )
            ) from exc

    async def query_registry_by_category(
        self,
        category_prefix: str,
    ) -> List[RegistryEntry]:
        """
        Search Fabric's registry for capabilities in a category.

        Filters by capability name prefix (e.g. ``"tool.calendar"``
        matches ``"tool.calendar.search"``, ``"tool.calendar.create"``).

        Uses ``Fabric.registry_api.list_all()`` and filters by prefix.

        Args:
            category_prefix: Name prefix to match.

        Returns:
            List of matching RegistryEntry.  Empty if none found.

        Raises:
            AdapterError: DEGRADED if registry is unreachable.
        """
        try:
            all_contracts = self._fabric.registry_api.list_all()
            matches: List[RegistryEntry] = []
            for contract in all_contracts:
                name = getattr(contract, "name", "")
                if name.startswith(category_prefix):
                    matches.append(self._contract_to_entry(contract))
            return matches
        except Exception as exc:
            raise AdapterException(
                AdapterError(
                    severity=ErrorSeverity.DEGRADED,
                    adapter_name="fabric_gateway",
                    operation="query_registry_by_category",
                    error_code="REGISTRY_ERROR",
                    error_message=f"Registry category query failed: {exc}",
                    original_exception=exc,
                )
            ) from exc

    # ==================================================================
    # Internal helpers
    # ==================================================================

    @staticmethod
    def _contract_to_entry(contract: Any) -> RegistryEntry:
        """
        Map a Fabric CapabilityContract to an Orchestrator RegistryEntry.

        Extracts the subset of fields the Orchestrator layer needs.

        Args:
            contract: CapabilityContract (or similar ContractUnion).

        Returns:
            RegistryEntry with mapped fields.
        """
        return RegistryEntry(
            name=getattr(contract, "name", ""),
            provider_type=getattr(contract, "provider_type", ""),
            safety_band_min=getattr(contract, "safety_band_min", "GREEN"),
            availability=getattr(contract, "availability", "ONLINE"),
            compensation_capability=None,
            estimated_duration_ms=getattr(contract, "avg_latency_ms", None) or None,
            required_inputs=[
                inp.name if hasattr(inp, "name") else str(inp)
                for inp in getattr(contract, "required_inputs", [])
            ],
            output=getattr(contract, "output", {}) or {},
            cost_per_call=getattr(contract, "cost_per_call", 0.0) or 0.0,
        )

    async def _execute_single_safe(
        self,
        request: CapabilityRequest,
    ) -> CapabilityResult:
        """
        Execute a single request, catching errors and returning a
        failed CapabilityResult instead of raising.

        Used as fallback for execute_batch when Fabric's native
        batch API fails.

        Args:
            request: Single capability request.

        Returns:
            CapabilityResult -- success or failure.
        """
        try:
            return await self._fabric.execute(request)
        except Exception as exc:
            logger.warning(
                "Batch fallback: single execute failed for '%s': %s",
                getattr(request, "capability_name", "unknown"),
                exc,
            )
            return CapabilityResult(
                request_id=getattr(request, "request_id", ""),
                trace_id=getattr(request, "trace_id", ""),
                success=False,
                error=None,
                data=None,
            )
