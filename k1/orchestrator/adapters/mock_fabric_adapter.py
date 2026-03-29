"""
k1.orchestrator.adapters.mock_fabric_adapter -- MockFabricAdapter (6.1.9).

Test/mock adapter for IFabricGatewayPort.

Design:
  - Scriptable: pre-configure results, errors, and timeouts per capability.
  - Logs all execute() calls for assertion.
  - Default: returns generic success CapabilityResult for unknown capabilities.
  - script_timeout() uses asyncio.sleep (not time.sleep) for async compat.
  - query_registry() returns from an in-memory registry dict.

References:
  - Issue 6.1.9 in orchestrator-implementation-plan.md
  - k1/orchestrator/ports/fabric_gateway_port.py (IFabricGatewayPort)

Exports:
  MockFabricAdapter
"""

from __future__ import annotations

import asyncio
from typing import Dict, List, Optional

from k1.fabric.types import CapabilityRequest, CapabilityResult
from k1.orchestrator.orchestration.orchestrator_service import AdapterException
from k1.orchestrator.types import AdapterError, RegistryEntry

# ---------------------------------------------------------------------------
# 6.1.9 -- MockFabricAdapter
# ---------------------------------------------------------------------------


class MockFabricAdapter:
    """
    Test IFabricGatewayPort adapter with scriptable results and errors.

    Pre-configure per-capability behavior:
      - ``script_result(cap, result)`` -- return specific CapabilityResult
      - ``script_error(cap, error)`` -- raise specific AdapterException
      - ``script_timeout(cap, delay_s)`` -- asyncio.sleep then return success

    Default behavior (no script): returns a generic success CapabilityResult.

    All ``execute()`` calls are logged to ``call_log`` for assertion.
    """

    def __init__(self) -> None:
        self.scripted_results: Dict[str, CapabilityResult] = {}
        self.scripted_errors: Dict[str, AdapterError] = {}
        self.scripted_timeouts: Dict[str, float] = {}
        self.call_log: List[CapabilityRequest] = []
        self.cancel_log: List[str] = []
        self.registry: Dict[str, RegistryEntry] = {}

    # ------------------------------------------------------------------
    # IFabricGatewayPort.execute
    # ------------------------------------------------------------------

    async def execute(self, request: CapabilityRequest) -> CapabilityResult:
        """Execute a capability. Returns scripted result or generic success."""
        self.call_log.append(request)
        cap = request.capability_name

        # Check scripted error first
        if cap in self.scripted_errors:
            raise AdapterException(self.scripted_errors[cap])

        # Check scripted timeout (asyncio.sleep then return)
        if cap in self.scripted_timeouts:
            await asyncio.sleep(self.scripted_timeouts[cap])

        # Check scripted result
        if cap in self.scripted_results:
            return self.scripted_results[cap]

        # Default: generic success
        return CapabilityResult.success_result(
            request_id=request.request_id,
            data={},
            provider_id="mock",
            trace_id=request.trace_id,
        )

    # ------------------------------------------------------------------
    # IFabricGatewayPort.execute_batch
    # ------------------------------------------------------------------

    async def execute_batch(self, requests: List[CapabilityRequest]) -> List[CapabilityResult]:
        """Execute a batch by calling execute() per request."""
        results: List[CapabilityResult] = []
        for req in requests:
            results.append(await self.execute(req))
        return results

    # ------------------------------------------------------------------
    # IFabricGatewayPort.query_registry
    # ------------------------------------------------------------------

    async def query_registry(self, capability_name: str) -> Optional[RegistryEntry]:
        """Return scripted registry entry or None."""
        return self.registry.get(capability_name)

    # ------------------------------------------------------------------
    # IFabricGatewayPort.query_registry_by_category
    # ------------------------------------------------------------------

    async def query_registry_by_category(self, category_prefix: str) -> List[RegistryEntry]:
        """Return all registry entries matching the category prefix."""
        return [entry for name, entry in self.registry.items() if name.startswith(category_prefix)]

    # ------------------------------------------------------------------
    # Test helpers -- scripting
    # ------------------------------------------------------------------

    def script_result(self, capability: str, result: CapabilityResult) -> None:
        """Pre-configure a specific result for a capability."""
        self.scripted_results[capability] = result

    def script_error(self, capability: str, error: AdapterError) -> None:
        """Pre-configure a specific error for a capability."""
        self.scripted_errors[capability] = error

    def script_timeout(self, capability: str, delay_s: float) -> None:
        """Pre-configure an asyncio.sleep delay before returning success."""
        self.scripted_timeouts[capability] = delay_s

    def register_capability(self, name: str, entry: RegistryEntry) -> None:
        """Add a capability to the mock registry."""
        self.registry[name] = entry

    # ------------------------------------------------------------------
    # Test helpers -- assertions
    # ------------------------------------------------------------------

    def assert_called(self, capability: str, times: int = 1) -> None:
        """Assert that *capability* was called exactly *times* times."""
        actual = sum(1 for r in self.call_log if r.capability_name == capability)
        assert actual == times, f"Expected {capability} called {times} time(s), got {actual}"

    def assert_not_called(self, capability: str) -> None:
        """Assert that *capability* was never called."""
        self.assert_called(capability, times=0)

    def reset(self) -> None:
        """Clear all scripts and logs."""
        self.scripted_results.clear()
        self.scripted_errors.clear()
        self.scripted_timeouts.clear()
        self.call_log.clear()
        self.cancel_log.clear()
        self.registry.clear()
