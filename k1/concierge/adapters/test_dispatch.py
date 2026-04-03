"""
k1.concierge.adapters.test_dispatch -- Test adapter for IDispatchPort.

Returns scripted results for both direct (LOW) and envelope (MED/HIGH) dispatch.
No Fabric, no Orchestrator -- pure in-memory for unit tests.
"""

from __future__ import annotations

from k1.concierge.orchestrator.types import AggregatedResult
from k1.concierge.orchestrator.types import CapabilityResult as POCCapabilityResult
from k1.concierge.orchestrator.types import TaskEnvelope
from k1.fabric.types import CapabilityRequest, CapabilityResult


class MockDispatchAdapter:
    """Test adapter for IDispatchPort — scripted dispatch results."""

    def __init__(self) -> None:
        self._direct_results: list[CapabilityResult] = []
        self._envelope_results: list[AggregatedResult] = []
        self.direct_calls: list[CapabilityRequest] = []
        self.envelope_calls: list[TaskEnvelope] = []

    async def dispatch_direct(self, request: CapabilityRequest) -> CapabilityResult:
        self.direct_calls.append(request)
        if self._direct_results:
            return self._direct_results.pop(0)
        return CapabilityResult.success_result(
            request_id="mock",
            data={},
            provider_id="mock",
        )

    async def dispatch_envelope(self, envelope: TaskEnvelope) -> AggregatedResult:
        self.envelope_calls.append(envelope)
        if self._envelope_results:
            return self._envelope_results.pop(0)
        # from_medium requires a POC CapabilityResult
        mock_cap = POCCapabilityResult(success=True, data={}, capability_name="mock")
        return AggregatedResult.from_medium(capability_result=mock_cap)

    # -- Test helpers ----------------------------------------------------------

    def script_direct(self, results: list[CapabilityResult]) -> None:
        """Queue scripted results for dispatch_direct calls."""
        self._direct_results = list(results)

    def script_envelope(self, results: list[AggregatedResult]) -> None:
        """Queue scripted results for dispatch_envelope calls."""
        self._envelope_results = list(results)
