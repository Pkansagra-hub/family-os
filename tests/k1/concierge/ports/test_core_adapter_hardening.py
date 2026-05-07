"""
E-1.2 I-1.2.2 — Core adapter hardening tests.

Extends existing SSMStateAdapter, FabricDispatchAdapter, RecallMemoryAdapter
tests with full behavioural coverage: snapshot delegation, orchestrator
dispatch, memory_types/max_results passthrough, Protocol conformance.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from k1.concierge.adapters.fabric_dispatch import FabricDispatchAdapter
from k1.concierge.adapters.recall_memory import RecallMemoryAdapter
from k1.concierge.adapters.ssm_state import SSMStateAdapter
from k1.concierge.ports import IDispatchPort, IMemoryPort, IStatePort

# ===================================================================
# SSMStateAdapter — production state read surface
# ===================================================================


class _FakeSectionWithToDict:
    """Duck-typed section object with to_dict()."""

    def __init__(self, data: dict) -> None:
        self._data = data

    def to_dict(self) -> dict:
        return self._data


class _FakeSSMWithSections:
    """Duck-typed SessionStateManager with .sections dict."""

    def __init__(self, sections: dict[str, Any]) -> None:
        self.sections = sections

    def get_section(self, name: str) -> Any:
        return self.sections.get(name)


class _FakeSSMWithPrivateSections:
    """Duck-typed SSM using ._sections (alternate access pattern)."""

    def __init__(self, sections: dict[str, Any]) -> None:
        self._sections = sections

    def get_section(self, name: str) -> Any:
        return self._sections.get(name)


class _BareSSM:
    """Duck-typed SSM with no .sections or ._sections."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def get_section(self, name: str) -> Any:
        return self._data.get(name)


class TestSSMStateAdapterProtocol:
    """SSMStateAdapter satisfies IStatePort."""

    def test_satisfies_istateport(self) -> None:
        inner = _BareSSM({})
        assert isinstance(SSMStateAdapter(inner), IStatePort)


class TestSSMStateAdapterGetSection:
    """get_section() delegates to inner SSM."""

    def test_delegates_to_inner(self) -> None:
        inner = _BareSSM({"control": {"intent": "greet"}})
        adapter = SSMStateAdapter(inner)
        assert adapter.get_section("control") == {"intent": "greet"}

    def test_missing_section_returns_none(self) -> None:
        inner = _BareSSM({})
        adapter = SSMStateAdapter(inner)
        assert adapter.get_section("nonexistent") is None

    def test_returns_arbitrary_types(self) -> None:
        inner = _BareSSM({"counter": 42})
        adapter = SSMStateAdapter(inner)
        assert adapter.get_section("counter") == 42


class TestSSMStateAdapterGetSnapshot:
    """get_snapshot() builds dict from sections."""

    def test_snapshot_with_to_dict_sections(self) -> None:
        """Sections with to_dict() are serialized."""
        ssm = _FakeSSMWithSections(
            {
                "control": _FakeSectionWithToDict({"intent": "greet"}),
                "affective": _FakeSectionWithToDict({"emotion": "happy"}),
            }
        )
        adapter = SSMStateAdapter(ssm)
        snap = adapter.get_snapshot()
        assert snap == {
            "control": {"intent": "greet"},
            "affective": {"emotion": "happy"},
        }

    def test_snapshot_with_raw_sections(self) -> None:
        """Sections WITHOUT to_dict() are returned raw."""
        ssm = _FakeSSMWithSections(
            {
                "simple": "raw_value",
                "number": 42,
            }
        )
        adapter = SSMStateAdapter(ssm)
        snap = adapter.get_snapshot()
        assert snap == {"simple": "raw_value", "number": 42}

    def test_snapshot_mixed_to_dict_and_raw(self) -> None:
        ssm = _FakeSSMWithSections(
            {
                "typed": _FakeSectionWithToDict({"a": 1}),
                "raw": "plain",
            }
        )
        adapter = SSMStateAdapter(ssm)
        snap = adapter.get_snapshot()
        assert snap["typed"] == {"a": 1}
        assert snap["raw"] == "plain"

    def test_snapshot_from_private_sections(self) -> None:
        """Falls back to ._sections when .sections missing."""
        ssm = _FakeSSMWithPrivateSections(
            {
                "s1": _FakeSectionWithToDict({"x": 1}),
            }
        )
        adapter = SSMStateAdapter(ssm)
        snap = adapter.get_snapshot()
        assert snap == {"s1": {"x": 1}}

    def test_snapshot_empty_ssm(self) -> None:
        ssm = _FakeSSMWithSections({})
        adapter = SSMStateAdapter(ssm)
        assert adapter.get_snapshot() == {}

    def test_snapshot_no_sections_attr(self) -> None:
        """SSM with neither .sections nor ._sections returns empty dict."""
        ssm = _BareSSM({"x": 1})
        adapter = SSMStateAdapter(ssm)
        assert adapter.get_snapshot() == {}


# ===================================================================
# FabricDispatchAdapter — production Fabric + Orchestrator dispatch
# ===================================================================


class _FakeFabricPort:
    """Fake IFabricPort: records execute() calls, returns scripted results."""

    def __init__(self, result: Any = None) -> None:
        from k1.fabric.types import CapabilityResult as FabResult

        self._result = result or FabResult(success=True, data={"ok": True})
        self.calls: list = []

    async def execute(self, request: Any) -> Any:
        self.calls.append(request)
        return self._result


class _FakeOrchestrator:
    """Fake OrchestratorStub: records handle_task() calls."""

    def __init__(self, result: Any = None) -> None:
        # Use a simple namespace stub since dispatch adapter does not
        # introspect the AggregatedResult; only ``.success`` is asserted.
        from types import SimpleNamespace

        self._result = result or SimpleNamespace(success=True)
        self.calls: list = []

    async def handle_task(self, envelope: Any) -> Any:
        self.calls.append(envelope)
        return self._result


class TestFabricDispatchAdapterProtocol:
    """FabricDispatchAdapter satisfies IDispatchPort."""

    def test_satisfies_idispatchport(self) -> None:
        adapter = FabricDispatchAdapter(fabric_port=None)
        assert isinstance(adapter, IDispatchPort)


class TestFabricDispatchDirect:
    """dispatch_direct() delegates to IFabricPort.execute()."""

    def test_delegates_to_fabric(self) -> None:
        from k1.fabric.types import CapabilityRequest, CapabilityResult

        fabric = _FakeFabricPort()
        adapter = FabricDispatchAdapter(fabric_port=fabric)
        req = CapabilityRequest(capability_name="test_cap", params={"x": 1})
        result = asyncio.get_event_loop().run_until_complete(adapter.dispatch_direct(req))
        assert len(fabric.calls) == 1
        assert fabric.calls[0] is req
        assert result.success is True

    def test_returns_fabric_result(self) -> None:
        from k1.fabric.types import CapabilityRequest, CapabilityResult

        expected = CapabilityResult(success=False, data={"error": "fail"})
        fabric = _FakeFabricPort(result=expected)
        adapter = FabricDispatchAdapter(fabric_port=fabric)
        req = CapabilityRequest(capability_name="fail_cap")
        result = asyncio.get_event_loop().run_until_complete(adapter.dispatch_direct(req))
        assert result is expected

    def test_multiple_direct_dispatches(self) -> None:
        from k1.fabric.types import CapabilityRequest

        fabric = _FakeFabricPort()
        adapter = FabricDispatchAdapter(fabric_port=fabric)
        for i in range(3):
            req = CapabilityRequest(capability_name=f"cap_{i}")
            asyncio.get_event_loop().run_until_complete(adapter.dispatch_direct(req))
        assert len(fabric.calls) == 3


class TestFabricDispatchEnvelope:
    """dispatch_envelope() delegates to OrchestratorStub.handle_task()."""

    def test_delegates_to_orchestrator(self) -> None:
        orch = _FakeOrchestrator()
        adapter = FabricDispatchAdapter(fabric_port=None, orchestrator=orch)
        env = object()  # adapter does not introspect envelope
        result = asyncio.get_event_loop().run_until_complete(adapter.dispatch_envelope(env))
        assert len(orch.calls) == 1
        assert orch.calls[0] is env
        assert result.success is True

    def test_raises_without_orchestrator(self) -> None:
        adapter = FabricDispatchAdapter(fabric_port=None, orchestrator=None)
        env = object()
        with pytest.raises(RuntimeError, match="no orchestrator"):
            asyncio.get_event_loop().run_until_complete(adapter.dispatch_envelope(env))

    def test_returns_orchestrator_result(self) -> None:
        from types import SimpleNamespace

        expected = SimpleNamespace(success=False)
        orch = _FakeOrchestrator(result=expected)
        adapter = FabricDispatchAdapter(fabric_port=None, orchestrator=orch)
        env = object()
        result = asyncio.get_event_loop().run_until_complete(adapter.dispatch_envelope(env))
        assert result is expected


# ===================================================================
# RecallMemoryAdapter — production memory recall
# ===================================================================


class TestRecallMemoryAdapterProtocol:
    """RecallMemoryAdapter satisfies IMemoryPort."""

    def test_satisfies_imemoryport(self) -> None:
        async def noop(q, memory_types=None, max_results=5):
            return []

        assert isinstance(RecallMemoryAdapter(noop), IMemoryPort)


class TestRecallMemoryAdapterRecall:
    """recall() delegates to the wrapped closure."""

    def test_delegates_query(self) -> None:
        calls: list = []

        async def tracked(query, memory_types=None, max_results=5):
            calls.append((query, memory_types, max_results))
            return [{"type": "fact", "content": "result"}]

        adapter = RecallMemoryAdapter(tracked)
        result = asyncio.get_event_loop().run_until_complete(adapter.recall("test query"))
        assert len(calls) == 1
        assert calls[0][0] == "test query"
        assert len(result) == 1

    def test_passes_memory_types(self) -> None:
        calls: list = []

        async def tracked(query, memory_types=None, max_results=5):
            calls.append(memory_types)
            return []

        adapter = RecallMemoryAdapter(tracked)
        asyncio.get_event_loop().run_until_complete(
            adapter.recall("q", memory_types=["episodic", "semantic"])
        )
        assert calls[0] == ["episodic", "semantic"]

    def test_passes_max_results(self) -> None:
        calls: list = []

        async def tracked(query, memory_types=None, max_results=5):
            calls.append(max_results)
            return []

        adapter = RecallMemoryAdapter(tracked)
        asyncio.get_event_loop().run_until_complete(adapter.recall("q", max_results=10))
        assert calls[0] == 10

    def test_default_memory_types_none(self) -> None:
        calls: list = []

        async def tracked(query, memory_types=None, max_results=5):
            calls.append(memory_types)
            return []

        adapter = RecallMemoryAdapter(tracked)
        asyncio.get_event_loop().run_until_complete(adapter.recall("q"))
        assert calls[0] is None

    def test_default_max_results_five(self) -> None:
        calls: list = []

        async def tracked(query, memory_types=None, max_results=5):
            calls.append(max_results)
            return []

        adapter = RecallMemoryAdapter(tracked)
        asyncio.get_event_loop().run_until_complete(adapter.recall("q"))
        assert calls[0] == 5

    def test_returns_closure_result(self) -> None:
        memories = [
            {"type": "fact", "content": "sky is blue"},
            {"type": "event", "content": "birthday party"},
        ]

        async def fn(query, memory_types=None, max_results=5):
            return memories

        adapter = RecallMemoryAdapter(fn)
        result = asyncio.get_event_loop().run_until_complete(adapter.recall("anything"))
        assert result == memories

    def test_returns_empty_list(self) -> None:
        async def fn(query, memory_types=None, max_results=5):
            return []

        adapter = RecallMemoryAdapter(fn)
        result = asyncio.get_event_loop().run_until_complete(adapter.recall("nothing"))
        assert result == []
