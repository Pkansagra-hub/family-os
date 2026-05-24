"""
C1 Issue 3.5 — Dispatch adapter behavioural tests.

Covers MockDispatchAdapter + FabricDispatchAdapter behaviour.
"""

from __future__ import annotations

import asyncio

# ===================================================================
# MockDispatchAdapter
# ===================================================================


class TestMockDispatchAdapterBehaviour:
    def test_dispatch_direct_records_call(self) -> None:
        from k1.concierge.adapters.test_dispatch import MockDispatchAdapter
        from k1.fabric.types import CapabilityRequest

        adapter = MockDispatchAdapter()
        req = CapabilityRequest(capability_name="test_cap", params={"x": 1})
        asyncio.run(adapter.dispatch_direct(req))
        assert len(adapter.direct_calls) == 1
        assert adapter.direct_calls[0] is req

    def test_dispatch_direct_returns_success(self) -> None:
        from k1.concierge.adapters.test_dispatch import MockDispatchAdapter
        from k1.fabric.types import CapabilityRequest

        adapter = MockDispatchAdapter()
        req = CapabilityRequest(capability_name="test_cap")
        result = asyncio.run(adapter.dispatch_direct(req))
        assert result.success is True

    def test_dispatch_envelope_records_call(self) -> None:
        from k1.concierge.adapters.test_dispatch import MockDispatchAdapter

        adapter = MockDispatchAdapter()
        env = object()  # adapter does not introspect envelope
        asyncio.run(adapter.dispatch_envelope(env))
        assert len(adapter.envelope_calls) == 1

    def test_dispatch_envelope_returns_aggregated(self) -> None:
        from k1.concierge.adapters.test_dispatch import MockDispatchAdapter

        adapter = MockDispatchAdapter()
        env = object()
        result = asyncio.run(adapter.dispatch_envelope(env))
        assert result.success is True


# ===================================================================
# FabricDispatchAdapter (production)
# ===================================================================


class TestFabricDispatchAdapterBehaviour:
    def test_raises_without_orchestrator(self) -> None:
        """dispatch_envelope raises RuntimeError if orchestrator is None."""
        import pytest

        from k1.concierge.adapters.fabric_dispatch import FabricDispatchAdapter

        adapter = FabricDispatchAdapter(fabric_port=None, orchestrator=None)
        env = object()
        with pytest.raises(RuntimeError, match="no orchestrator"):
            asyncio.run(adapter.dispatch_envelope(env))

    def test_execute_batch_delegates_to_fabric_batch(self) -> None:
        from k1.concierge.adapters.fabric_dispatch import FabricDispatchAdapter
        from k1.fabric.fabric import BatchStrategy
        from k1.fabric.types import CapabilityRequest, CapabilityResult

        class Fabric:
            def __init__(self) -> None:
                self.calls = []

            async def execute_batch(self, requests, strategy=BatchStrategy.PARALLEL):  # type: ignore[no-untyped-def]
                self.calls.append((list(requests), strategy))
                return [
                    CapabilityResult.success_result(
                        request_id=request.request_id,
                        data={"capability_name": request.capability_name},
                        provider_id="fabric",
                    )
                    for request in requests
                ]

        fabric = Fabric()
        adapter = FabricDispatchAdapter(fabric_port=fabric)
        requests = [
            CapabilityRequest(capability_name="tool.read.tasks.list_tasks", caller="test"),
            CapabilityRequest(capability_name="tool.read.calendar.list_events", caller="test"),
        ]

        results = asyncio.run(adapter.execute_batch(requests, strategy="PARALLEL"))

        assert [result.success for result in results] == [True, True]
        assert fabric.calls[0][1] is BatchStrategy.PARALLEL
        assert fabric.calls[0][0] == requests
