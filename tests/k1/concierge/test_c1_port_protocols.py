"""
C1 — Port Protocol compliance + adapter tests.

Validates:
    1. All 8 port Protocols exist and are runtime_checkable
    2. Test adapters satisfy their port Protocols (isinstance checks)
    3. Production adapters satisfy their port Protocols (isinstance checks)
    4. Adapter behaviour: input/output/state/dispatch/memory
"""

from __future__ import annotations

import asyncio

import pytest

from k1.bus.envelope import Envelope, Priority
from k1.bus.ports.bus import IBus

# --- Production adapters ---
from k1.concierge.adapters.bus_input import BusInputAdapter
from k1.concierge.adapters.bus_output import BusOutputAdapter
from k1.concierge.adapters.fabric_dispatch import FabricDispatchAdapter
from k1.concierge.adapters.recall_memory import RecallMemoryAdapter
from k1.concierge.adapters.ssm_state import SSMStateAdapter

# --- Test adapters ---
from k1.concierge.adapters.test_dispatch import MockDispatchAdapter
from k1.concierge.adapters.test_input import TestInputAdapter
from k1.concierge.adapters.test_memory import MockMemoryAdapter
from k1.concierge.adapters.test_output import TestOutputAdapter
from k1.concierge.adapters.test_state import InMemoryStateAdapter

# --- Existing impls for re-exported port compliance ---
from k1.concierge.fsm.phase1 import StubPhase1Pipeline

# --- Ports ---
from k1.concierge.ports import (
    IClassificationPort,
    IDeltaPort,
    IDispatchPort,
    IFabricPort,
    IInputPort,
    ILLMPort,
    IMemoryPort,
    IOutputPort,
    IStatePort,
)

# ===================================================================
# Helpers
# ===================================================================


def _make_envelope(topic: str = "k1.test.v1", payload: bytes = b'{"text":"hi"}') -> Envelope:
    """Build a minimal Envelope for testing."""
    return Envelope(
        topic=topic,
        priority=Priority.INTERACTIVE,
        payload=payload,
    )


# ===================================================================
# 1. Protocol compliance — test adapters
# ===================================================================


class TestInputAdapterCompliance:
    def test_satisfies_iinputport(self) -> None:
        adapter = TestInputAdapter()
        assert isinstance(adapter, IInputPort)

    def test_receive_returns_injected_envelope(self) -> None:
        adapter = TestInputAdapter()
        env = _make_envelope()
        adapter.inject(env)
        result = asyncio.get_event_loop().run_until_complete(adapter.receive())
        assert result is env

    def test_has_buffered_empty(self) -> None:
        adapter = TestInputAdapter()
        assert adapter.has_buffered() is False

    def test_has_buffered_after_inject(self) -> None:
        adapter = TestInputAdapter()
        adapter.inject(_make_envelope())
        assert adapter.has_buffered() is True

    def test_inject_text_creates_envelope(self) -> None:
        adapter = TestInputAdapter()
        adapter.inject_text("hello world")
        assert adapter.has_buffered() is True
        env = asyncio.get_event_loop().run_until_complete(adapter.receive())
        assert env.topic == "k1.session.user.input.v1"

    def test_fifo_ordering(self) -> None:
        adapter = TestInputAdapter()
        e1 = _make_envelope(payload=b'{"n":1}')
        e2 = _make_envelope(payload=b'{"n":2}')
        adapter.inject(e1)
        adapter.inject(e2)
        loop = asyncio.get_event_loop()
        assert loop.run_until_complete(adapter.receive()) is e1
        assert loop.run_until_complete(adapter.receive()) is e2


class TestOutputAdapterCompliance:
    def test_satisfies_ioutputport(self) -> None:
        adapter = TestOutputAdapter()
        assert isinstance(adapter, IOutputPort)

    def test_send_captures_envelope(self) -> None:
        adapter = TestOutputAdapter()
        env = _make_envelope()
        asyncio.get_event_loop().run_until_complete(adapter.send(env))
        assert len(adapter.sent) == 1
        assert adapter.sent[0] is env

    def test_get_sent_no_filter(self) -> None:
        adapter = TestOutputAdapter()
        asyncio.get_event_loop().run_until_complete(adapter.send(_make_envelope("t1")))
        asyncio.get_event_loop().run_until_complete(adapter.send(_make_envelope("t2")))
        assert len(adapter.get_sent()) == 2

    def test_get_sent_with_topic_filter(self) -> None:
        adapter = TestOutputAdapter()
        asyncio.get_event_loop().run_until_complete(adapter.send(_make_envelope("t1")))
        asyncio.get_event_loop().run_until_complete(adapter.send(_make_envelope("t2")))
        asyncio.get_event_loop().run_until_complete(adapter.send(_make_envelope("t1")))
        assert len(adapter.get_sent("t1")) == 2
        assert len(adapter.get_sent("t2")) == 1

    def test_last_returns_most_recent(self) -> None:
        adapter = TestOutputAdapter()
        e1 = _make_envelope(payload=b'{"n":1}')
        e2 = _make_envelope(payload=b'{"n":2}')
        asyncio.get_event_loop().run_until_complete(adapter.send(e1))
        asyncio.get_event_loop().run_until_complete(adapter.send(e2))
        assert adapter.last() is e2

    def test_last_empty(self) -> None:
        adapter = TestOutputAdapter()
        assert adapter.last() is None

    def test_clear_resets(self) -> None:
        adapter = TestOutputAdapter()
        asyncio.get_event_loop().run_until_complete(adapter.send(_make_envelope()))
        adapter.clear()
        assert len(adapter.sent) == 0


class TestStateAdapterCompliance:
    def test_satisfies_istateport(self) -> None:
        adapter = InMemoryStateAdapter()
        assert isinstance(adapter, IStatePort)

    def test_get_section_missing_returns_none(self) -> None:
        adapter = InMemoryStateAdapter()
        assert adapter.get_section("nonexistent") is None

    def test_get_section_returns_seeded(self) -> None:
        adapter = InMemoryStateAdapter()
        adapter.seed("control", {"intent": "greet"})
        assert adapter.get_section("control") == {"intent": "greet"}

    def test_get_snapshot_all_sections(self) -> None:
        adapter = InMemoryStateAdapter()
        adapter.seed("a", 1)
        adapter.seed("b", 2)
        snap = adapter.get_snapshot()
        assert snap == {"a": 1, "b": 2}

    def test_seed_dict_allows_attr_access(self) -> None:
        adapter = InMemoryStateAdapter()
        adapter.seed_dict("control", {"intent": "greet", "domain": "social"})
        section = adapter.get_section("control")
        assert section.intent == "greet"
        assert section.domain == "social"

    def test_clear(self) -> None:
        adapter = InMemoryStateAdapter()
        adapter.seed("x", 1)
        adapter.clear()
        assert adapter.get_snapshot() == {}


class TestDispatchAdapterCompliance:
    def test_satisfies_idispatchport(self) -> None:
        adapter = MockDispatchAdapter()
        assert isinstance(adapter, IDispatchPort)

    def test_dispatch_direct_records_call(self) -> None:
        from k1.fabric.types import CapabilityRequest

        adapter = MockDispatchAdapter()
        req = CapabilityRequest(capability_name="test_cap", params={"x": 1})
        asyncio.get_event_loop().run_until_complete(adapter.dispatch_direct(req))
        assert len(adapter.direct_calls) == 1
        assert adapter.direct_calls[0] is req

    def test_dispatch_direct_returns_success(self) -> None:
        from k1.fabric.types import CapabilityRequest

        adapter = MockDispatchAdapter()
        req = CapabilityRequest(capability_name="test_cap")
        result = asyncio.get_event_loop().run_until_complete(adapter.dispatch_direct(req))
        assert result.success is True

    def test_dispatch_envelope_records_call(self) -> None:
        from k1.concierge.orchestrator.types import TaskEnvelope

        adapter = MockDispatchAdapter()
        env = TaskEnvelope(intent="test", task_id="t1")
        asyncio.get_event_loop().run_until_complete(adapter.dispatch_envelope(env))
        assert len(adapter.envelope_calls) == 1

    def test_dispatch_envelope_returns_aggregated(self) -> None:
        from k1.concierge.orchestrator.types import TaskEnvelope

        adapter = MockDispatchAdapter()
        env = TaskEnvelope(intent="test", task_id="t1")
        result = asyncio.get_event_loop().run_until_complete(adapter.dispatch_envelope(env))
        assert result.success is True


class TestMemoryAdapterCompliance:
    def test_satisfies_imemoryport(self) -> None:
        adapter = MockMemoryAdapter()
        assert isinstance(adapter, IMemoryPort)

    def test_recall_empty(self) -> None:
        adapter = MockMemoryAdapter()
        result = asyncio.get_event_loop().run_until_complete(adapter.recall("anything"))
        assert result == []

    def test_recall_returns_seeded(self) -> None:
        memories = [
            {"type": "fact", "content": "sky is blue", "tags": ["sky"]},
            {"type": "event", "content": "birthday", "tags": ["family"]},
        ]
        adapter = MockMemoryAdapter(memories=memories)
        result = asyncio.get_event_loop().run_until_complete(adapter.recall("query"))
        assert len(result) == 2

    def test_recall_filters_by_type(self) -> None:
        memories = [
            {"type": "fact", "content": "sky is blue"},
            {"type": "event", "content": "birthday"},
        ]
        adapter = MockMemoryAdapter(memories=memories)
        result = asyncio.get_event_loop().run_until_complete(
            adapter.recall("query", memory_types=["fact"])
        )
        assert len(result) == 1
        assert result[0]["type"] == "fact"

    def test_recall_max_results(self) -> None:
        memories = [{"type": "fact", "content": f"item {i}"} for i in range(10)]
        adapter = MockMemoryAdapter(memories=memories)
        result = asyncio.get_event_loop().run_until_complete(adapter.recall("query", max_results=3))
        assert len(result) == 3

    def test_recall_records_calls(self) -> None:
        adapter = MockMemoryAdapter()
        asyncio.get_event_loop().run_until_complete(
            adapter.recall("q", memory_types=["fact"], max_results=2)
        )
        assert len(adapter.recall_calls) == 1
        assert adapter.recall_calls[0] == ("q", ["fact"], 2)


# ===================================================================
# 2. Protocol compliance — re-exported existing ports
# ===================================================================


class TestReExportedPortCompliance:
    def test_stub_phase1_satisfies_iclassificationport(self) -> None:
        """Phase1Pipeline is not @runtime_checkable, so verify structurally."""
        stub = StubPhase1Pipeline()
        assert hasattr(stub, "classify")
        assert callable(stub.classify)
        # Verify it returns Phase1Result
        from k1.concierge.fsm.phase1 import Phase1Result

        result = stub.classify("hello")
        assert isinstance(result, Phase1Result)
        # Verify IClassificationPort alias is Phase1Pipeline
        from k1.concierge.fsm.phase1 import Phase1Pipeline

        assert IClassificationPort is Phase1Pipeline

    def test_ideltaport_is_ibus(self) -> None:
        """IDeltaPort is just an alias for IBus."""
        assert IDeltaPort is IBus


# ===================================================================
# 3. Protocol compliance — production adapters
# ===================================================================


class TestProductionInputAdapterCompliance:
    def test_satisfies_iinputport(self) -> None:
        from k1.bus.factory import BusFactory

        bus = BusFactory.create_local()
        adapter = BusInputAdapter(bus)
        assert isinstance(adapter, IInputPort)
        adapter.close()

    def test_receives_published_envelope(self) -> None:
        from k1.bus.factory import BusFactory
        from k1.concierge.bus.builders import build_user_input

        bus = BusFactory.create_local()
        adapter = BusInputAdapter(bus)
        env = build_user_input({"text": "hello", "device_id": "test"})
        bus.publish(env)
        assert adapter.has_buffered() is True
        result = asyncio.get_event_loop().run_until_complete(adapter.receive())
        assert result.topic == "k1.session.user.input.v1"
        adapter.close()


class TestProductionOutputAdapterCompliance:
    def test_satisfies_ioutputport(self) -> None:
        from k1.bus.factory import BusFactory

        bus = BusFactory.create_local()
        adapter = BusOutputAdapter(bus)
        assert isinstance(adapter, IOutputPort)


class TestProductionStateAdapterCompliance:
    def test_satisfies_istateport(self) -> None:
        # Use InMemoryStateAdapter as the inner SSM mock (it has get_section)
        inner = InMemoryStateAdapter()
        inner.seed("control", {"intent": "greet"})
        adapter = SSMStateAdapter(inner)
        assert isinstance(adapter, IStatePort)

    def test_delegates_get_section(self) -> None:
        inner = InMemoryStateAdapter()
        inner.seed("control", {"intent": "greet"})
        adapter = SSMStateAdapter(inner)
        assert adapter.get_section("control") == {"intent": "greet"}


class TestProductionDispatchAdapterCompliance:
    def test_satisfies_idispatchport(self) -> None:
        adapter = FabricDispatchAdapter(fabric_port=None, orchestrator=None)
        assert isinstance(adapter, IDispatchPort)


class TestProductionMemoryAdapterCompliance:
    def test_satisfies_imemoryport(self) -> None:
        async def dummy_recall(query, memory_types=None, max_results=5):
            return []

        adapter = RecallMemoryAdapter(dummy_recall)
        assert isinstance(adapter, IMemoryPort)

    def test_delegates_to_closure(self) -> None:
        calls = []

        async def tracked_recall(query, memory_types=None, max_results=5):
            calls.append((query, memory_types, max_results))
            return [{"type": "fact", "content": "result"}]

        adapter = RecallMemoryAdapter(tracked_recall)
        result = asyncio.get_event_loop().run_until_complete(adapter.recall("test query"))
        assert len(calls) == 1
        assert calls[0][0] == "test query"
        assert len(result) == 1
