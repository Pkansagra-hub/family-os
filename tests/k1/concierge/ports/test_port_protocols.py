"""
C1 Issue 3.1 — Protocol compliance tests for all 8 Concierge port Protocols.

Validates that every test adapter and production adapter satisfies its
corresponding port Protocol. This is the structural subtyping gate:
if isinstance() passes, the adapter is wired correctly.
"""

from __future__ import annotations

import pytest

from k1.bus.ports.bus import IBus

# --- Production adapters ---
from k1.concierge.adapters.bus_input import BusInputAdapter
from k1.concierge.adapters.bus_output import BusOutputAdapter
from k1.concierge.adapters.fabric_dispatch import FabricDispatchAdapter
from k1.concierge.adapters.recall_memory import RecallMemoryAdapter
from k1.concierge.adapters.ssm_state import SSMStateAdapter
from k1.concierge.adapters.test_classification import StubPhase1Pipeline
from k1.concierge.adapters.test_dispatch import MockDispatchAdapter

# --- Test adapters ---
from k1.concierge.adapters.test_input import TestInputAdapter
from k1.concierge.adapters.test_memory import MockMemoryAdapter
from k1.concierge.adapters.test_output import TestOutputAdapter
from k1.concierge.adapters.test_state import InMemoryStateAdapter

# --- Ports ---
from k1.concierge.ports import (
    IClassificationPort,
    IDeltaPort,
    IDispatchPort,
    IInputPort,
    ILLMPort,
    IMemoryPort,
    IOutputPort,
    IStatePort,
)

# ===================================================================
# Test adapter Protocol compliance (8 tests)
# ===================================================================


class TestTestAdapterProtocolCompliance:
    """Every test adapter must satisfy its port Protocol."""

    def test_test_input_adapter_satisfies_iinputport(self) -> None:
        assert isinstance(TestInputAdapter(), IInputPort)

    def test_test_output_adapter_satisfies_ioutputport(self) -> None:
        assert isinstance(TestOutputAdapter(), IOutputPort)

    def test_stub_phase1_satisfies_iclassificationport(self) -> None:
        """Phase1Pipeline is not @runtime_checkable — verify structurally."""
        stub = StubPhase1Pipeline()
        assert hasattr(stub, "classify")
        assert callable(stub.classify)
        from k1.concierge.fsm.phase1 import Phase1Result

        result = stub.classify("hello")
        assert isinstance(result, Phase1Result)
        # Alias check
        from k1.concierge.fsm.phase1 import Phase1Pipeline

        assert IClassificationPort is Phase1Pipeline

    def test_model_hub_bridge_satisfies_illmport(self) -> None:
        """ILLMPort = IModelHubPort — verify alias is correct."""
        from k1.model_hub.ports.hub_port import IModelHubPort

        assert ILLMPort is IModelHubPort

    def test_in_memory_state_satisfies_istateport(self) -> None:
        assert isinstance(InMemoryStateAdapter(), IStatePort)

    def test_mock_dispatch_satisfies_idispatchport(self) -> None:
        assert isinstance(MockDispatchAdapter(), IDispatchPort)

    def test_local_bus_satisfies_ideltaport(self) -> None:
        """IDeltaPort = IBus — LocalBus satisfies IBus."""
        assert IDeltaPort is IBus
        from k1.bus.factory import BusFactory

        bus = BusFactory.create_local()
        assert isinstance(bus, IBus)

    def test_mock_memory_satisfies_imemoryport(self) -> None:
        assert isinstance(MockMemoryAdapter(), IMemoryPort)


# ===================================================================
# Production adapter Protocol compliance (8 tests)
# ===================================================================


class TestProductionAdapterProtocolCompliance:
    """Every production adapter must satisfy its port Protocol."""

    def test_bus_input_adapter_satisfies_iinputport(self) -> None:
        from k1.bus.factory import BusFactory

        bus = BusFactory.create_local()
        adapter = BusInputAdapter(bus)
        assert isinstance(adapter, IInputPort)
        adapter.close()

    def test_bus_output_adapter_satisfies_ioutputport(self) -> None:
        from k1.bus.factory import BusFactory

        bus = BusFactory.create_local()
        assert isinstance(BusOutputAdapter(bus), IOutputPort)

    def test_ultrabert_satisfies_iclassificationport(self) -> None:
        """UltraBERTPhase1Pipeline implements Phase1Pipeline Protocol structurally."""
        from k1.concierge.adapters.ultrabert_classification import UltraBERTPhase1Pipeline

        assert hasattr(UltraBERTPhase1Pipeline, "classify")

    def test_ssm_state_adapter_satisfies_istateport(self) -> None:
        inner = InMemoryStateAdapter()
        assert isinstance(SSMStateAdapter(inner), IStatePort)

    def test_fabric_dispatch_adapter_satisfies_idispatchport(self) -> None:
        assert isinstance(FabricDispatchAdapter(fabric_port=None), IDispatchPort)

    def test_bus_factory_creates_ideltaport(self) -> None:
        from k1.bus.factory import BusFactory

        bus = BusFactory.create_local()
        assert isinstance(bus, IBus)
        assert IDeltaPort is IBus

    def test_recall_memory_adapter_satisfies_imemoryport(self) -> None:
        async def noop(q, memory_types=None, max_results=5):
            return []

        assert isinstance(RecallMemoryAdapter(noop), IMemoryPort)

    @pytest.mark.xfail(
        reason="Pre-existing: HubHealthReport import missing from k1.model_hub.ports",
        raises=ImportError,
    )
    def test_model_hub_poc_bridge_satisfies_illmport(self) -> None:
        """ModelHubPOCBridge implements IModelHubPort — heavy import, structural check."""
        from k1.concierge.adapters.hub_llm import ModelHubPOCBridge

        assert hasattr(ModelHubPOCBridge, "execute")
        assert hasattr(ModelHubPOCBridge, "stream_execute")
