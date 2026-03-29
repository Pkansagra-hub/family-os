"""
Tests for DeltaEmitAdapter (6.1.5) and BridgeWriteAdapter (6.1.6).

Covers:
  - DeltaEmitAdapter: emit, emit_progress, emit_hil_request,
    dual-publish semantics, fire-and-forget error swallowing, ORCH-09 trace_id.
  - BridgeWriteAdapter: submit_audit, write_wal, read_wal, list_wal_ids,
    submit_deferred_result, fire-and-forget writes, AdapterException reads.
  - Re-exports from adapters __init__.

References:
  - Issues 6.1.5 and 6.1.6 in orchestrator-implementation-plan.md
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pytest

from k1.orchestrator.adapters.bridge_write_adapter import BridgeWriteAdapter
from k1.orchestrator.adapters.delta_emit_adapter import DeltaEmitAdapter
from k1.orchestrator.orchestration.orchestrator_service import AdapterException
from k1.orchestrator.types import HILRequest

# ===================================================================
# Fakes -- DeltaEmitAdapter
# ===================================================================


class FakeEventPort:
    """In-memory IEventPort fake that records emit() calls."""

    def __init__(self, *, fail: bool = False) -> None:
        self.emitted: List[Tuple[str, Dict[str, Any]]] = []
        self._fail = fail

    def emit(self, topic: str, payload: Dict[str, Any]) -> None:
        if self._fail:
            raise RuntimeError("event_port.emit boom")
        self.emitted.append((topic, dict(payload)))

    def subscribe(self, topic, handler):
        pass  # Not used by DeltaEmitAdapter

    def unsubscribe(self, handle):
        pass  # Not used by DeltaEmitAdapter


class FakeDeltaBus:
    """In-memory IDeltaBusPort fake that records emit_delta() calls."""

    def __init__(self, *, fail: bool = False) -> None:
        self.deltas: List[Dict[str, Any]] = []
        self._fail = fail

    def emit_delta(
        self,
        agent_id: str,
        delta_type: str,
        section: str,
        data: Dict[str, Any],
    ) -> None:
        if self._fail:
            raise RuntimeError("delta_bus.emit_delta boom")
        self.deltas.append(
            {
                "agent_id": agent_id,
                "delta_type": delta_type,
                "section": section,
                "data": dict(data),
            }
        )


# ===================================================================
# Fakes -- BridgeWriteAdapter
# ===================================================================


class FakeBridgeClient:
    """In-memory bridge client that records write/read calls."""

    def __init__(
        self,
        *,
        write_fail: bool = False,
        read_fail: bool = False,
        read_data: Any = None,
    ) -> None:
        self.writes: List[Tuple[str, Dict[str, Any], str]] = []
        self.reads: List[Tuple[str, str]] = []
        self._write_fail = write_fail
        self._read_fail = read_fail
        self._read_data = read_data

    async def write(
        self,
        channel: str,
        payload: Dict[str, Any],
        *,
        trace_id: str,
    ) -> None:
        if self._write_fail:
            raise ConnectionError("bridge write boom")
        self.writes.append((channel, dict(payload), trace_id))

    async def read(self, channel: str, key: str) -> Any:
        self.reads.append((channel, key))
        if self._read_fail:
            raise ConnectionError("bridge read boom")
        return self._read_data


# ===================================================================
# DeltaEmitAdapter tests
# ===================================================================


class TestDeltaEmitAdapterEmit:
    """Tests for DeltaEmitAdapter.emit()."""

    @pytest.mark.asyncio
    async def test_emit_internal_event(self) -> None:
        """Internal events go to event_port only, not delta_bus."""
        ep = FakeEventPort()
        db = FakeDeltaBus()
        adapter = DeltaEmitAdapter(event_port=ep, delta_bus=db)

        await adapter.emit("k1.internal.something.v1", {"key": "val"}, "t-1")

        assert len(ep.emitted) == 1
        topic, payload = ep.emitted[0]
        assert topic == "k1.internal.something.v1"
        assert payload["trace_id"] == "t-1"
        assert payload["key"] == "val"
        # NOT dual-published
        assert len(db.deltas) == 0

    @pytest.mark.asyncio
    async def test_emit_hil_topic_dual_publish(self) -> None:
        """Topics starting with k1.hil. go to BOTH event_port and delta_bus."""
        ep = FakeEventPort()
        db = FakeDeltaBus()
        adapter = DeltaEmitAdapter(event_port=ep, delta_bus=db)

        await adapter.emit("k1.hil.progress.v1", {"step": "s1"}, "t-2")

        assert len(ep.emitted) == 1
        assert len(db.deltas) == 1
        delta = db.deltas[0]
        assert delta["agent_id"] == "orchestrator"
        assert delta["delta_type"] == "k1.hil.progress.v1"
        assert delta["section"] == "orchestration"
        assert delta["data"]["trace_id"] == "t-2"

    @pytest.mark.asyncio
    async def test_emit_orchestration_topic_dual_publish(self) -> None:
        """Topics starting with k1.orchestration. go to BOTH."""
        ep = FakeEventPort()
        db = FakeDeltaBus()
        adapter = DeltaEmitAdapter(event_port=ep, delta_bus=db)

        await adapter.emit("k1.orchestration.dag.complete.v1", {}, "t-3")

        assert len(ep.emitted) == 1
        assert len(db.deltas) == 1

    @pytest.mark.asyncio
    async def test_emit_trace_id_injected(self) -> None:
        """ORCH-09: trace_id is always injected into the payload."""
        ep = FakeEventPort()
        db = FakeDeltaBus()
        adapter = DeltaEmitAdapter(event_port=ep, delta_bus=db)

        await adapter.emit("k1.hil.test.v1", {}, "trace-abc")

        _, payload = ep.emitted[0]
        assert payload["trace_id"] == "trace-abc"

    @pytest.mark.asyncio
    async def test_emit_event_port_failure_swallowed(self) -> None:
        """event_port failure is swallowed silently."""
        ep = FakeEventPort(fail=True)
        db = FakeDeltaBus()
        adapter = DeltaEmitAdapter(event_port=ep, delta_bus=db)

        # Should NOT raise
        await adapter.emit("k1.hil.x.v1", {}, "t-err")

        assert len(db.deltas) == 0  # delta_bus not reached

    @pytest.mark.asyncio
    async def test_emit_delta_bus_failure_swallowed(self) -> None:
        """delta_bus failure is swallowed silently."""
        ep = FakeEventPort()
        db = FakeDeltaBus(fail=True)
        adapter = DeltaEmitAdapter(event_port=ep, delta_bus=db)

        # Should NOT raise even though delta_bus fails
        await adapter.emit("k1.hil.x.v1", {}, "t-err2")

        # event_port was called before delta_bus failed
        assert len(ep.emitted) == 1


class TestDeltaEmitAdapterEmitProgress:
    """Tests for DeltaEmitAdapter.emit_progress()."""

    @pytest.mark.asyncio
    async def test_emit_progress_basic(self) -> None:
        ep = FakeEventPort()
        db = FakeDeltaBus()
        adapter = DeltaEmitAdapter(event_port=ep, delta_bus=db)

        await adapter.emit_progress("step-1", "Doing stuff", "t-p1")

        assert len(ep.emitted) == 1
        topic, payload = ep.emitted[0]
        assert topic == "k1.hil.progress.v1"
        assert payload["step_id"] == "step-1"
        assert payload["summary"] == "Doing stuff"
        assert payload["trace_id"] == "t-p1"
        # k1.hil. prefix -> dual-publish
        assert len(db.deltas) == 1

    @pytest.mark.asyncio
    async def test_emit_progress_failure_swallowed(self) -> None:
        ep = FakeEventPort(fail=True)
        db = FakeDeltaBus()
        adapter = DeltaEmitAdapter(event_port=ep, delta_bus=db)

        await adapter.emit_progress("s", "x", "t")  # No raise


class TestDeltaEmitAdapterEmitHilRequest:
    """Tests for DeltaEmitAdapter.emit_hil_request()."""

    @pytest.mark.asyncio
    async def test_emit_hil_request_basic(self) -> None:
        ep = FakeEventPort()
        db = FakeDeltaBus()
        adapter = DeltaEmitAdapter(event_port=ep, delta_bus=db)

        hil = HILRequest(
            request_id="hil-1",
            question="Continue?",
            options=["yes", "no"],
        )
        await adapter.emit_hil_request(hil, "t-hil")

        assert len(ep.emitted) == 1
        topic, payload = ep.emitted[0]
        assert topic == "k1.hil.request.v1"
        assert payload["request_id"] == "hil-1"
        assert payload["question"] == "Continue?"
        assert payload["options"] == ["yes", "no"]
        assert payload["trace_id"] == "t-hil"
        # k1.hil. prefix -> dual-publish
        assert len(db.deltas) == 1

    @pytest.mark.asyncio
    async def test_emit_hil_request_failure_swallowed(self) -> None:
        ep = FakeEventPort(fail=True)
        db = FakeDeltaBus()
        adapter = DeltaEmitAdapter(event_port=ep, delta_bus=db)

        hil = HILRequest(request_id="x", question="?")
        await adapter.emit_hil_request(hil, "t")  # No raise


class TestDeltaEmitSlots:
    """Structural checks for DeltaEmitAdapter."""

    def test_has_slots(self) -> None:
        assert hasattr(DeltaEmitAdapter, "__slots__")
        assert "_event_port" in DeltaEmitAdapter.__slots__
        assert "_delta_bus" in DeltaEmitAdapter.__slots__


# ===================================================================
# BridgeWriteAdapter tests
# ===================================================================


class TestBridgeWriteSubmitAudit:
    """Tests for BridgeWriteAdapter.submit_audit()."""

    @pytest.mark.asyncio
    async def test_submit_audit_success(self) -> None:
        client = FakeBridgeClient()
        adapter = BridgeWriteAdapter(client)

        await adapter.submit_audit({"dag_id": "d1", "status": "COMPLETED"}, "t-a1")

        assert len(client.writes) == 1
        channel, payload, trace_id = client.writes[0]
        assert channel == "audit"
        assert payload["dag_id"] == "d1"
        assert trace_id == "t-a1"

    @pytest.mark.asyncio
    async def test_submit_audit_failure_swallowed(self) -> None:
        client = FakeBridgeClient(write_fail=True)
        adapter = BridgeWriteAdapter(client)

        # fire-and-forget -- no raise
        await adapter.submit_audit({"x": 1}, "t-fail")


class TestBridgeWriteWal:
    """Tests for BridgeWriteAdapter.write_wal()."""

    @pytest.mark.asyncio
    async def test_write_wal_success(self) -> None:
        client = FakeBridgeClient()
        adapter = BridgeWriteAdapter(client)

        await adapter.write_wal("dag-1", "PLAN_START", {"plan": "p1"}, "t-w1")

        assert len(client.writes) == 1
        channel, payload, trace_id = client.writes[0]
        assert channel == "wal"
        assert payload["dag_id"] == "dag-1"
        assert payload["entry_type"] == "PLAN_START"
        assert payload["payload"]["plan"] == "p1"
        assert trace_id == "t-w1"

    @pytest.mark.asyncio
    async def test_write_wal_all_entry_types(self) -> None:
        """All 4 valid entry types succeed."""
        client = FakeBridgeClient()
        adapter = BridgeWriteAdapter(client)

        for et in ("PLAN_START", "WAVE_COMPLETE", "STEP_COMPLETE", "DAG_COMPLETE"):
            await adapter.write_wal("d", et, {}, "t")

        assert len(client.writes) == 4

    @pytest.mark.asyncio
    async def test_write_wal_unknown_entry_type_still_writes(self) -> None:
        """Unknown entry types log a warning but still write (forward compat)."""
        client = FakeBridgeClient()
        adapter = BridgeWriteAdapter(client)

        await adapter.write_wal("d", "CUSTOM_TYPE", {}, "t")

        # Still written (forward compatibility)
        assert len(client.writes) == 1

    @pytest.mark.asyncio
    async def test_write_wal_failure_swallowed(self) -> None:
        client = FakeBridgeClient(write_fail=True)
        adapter = BridgeWriteAdapter(client)

        await adapter.write_wal("d", "PLAN_START", {}, "t")  # No raise


class TestBridgeReadWal:
    """Tests for BridgeWriteAdapter.read_wal()."""

    @pytest.mark.asyncio
    async def test_read_wal_success(self) -> None:
        entries = [{"entry_type": "PLAN_START"}, {"entry_type": "STEP_COMPLETE"}]
        client = FakeBridgeClient(read_data=entries)
        adapter = BridgeWriteAdapter(client)

        result = await adapter.read_wal("dag-1")

        assert result == entries
        assert len(client.reads) == 1
        assert client.reads[0] == ("wal", "dag-1")

    @pytest.mark.asyncio
    async def test_read_wal_none(self) -> None:
        client = FakeBridgeClient(read_data=None)
        adapter = BridgeWriteAdapter(client)

        result = await adapter.read_wal("dag-x")

        assert result is None

    @pytest.mark.asyncio
    async def test_read_wal_failure_raises_adapter_exception(self) -> None:
        client = FakeBridgeClient(read_fail=True)
        adapter = BridgeWriteAdapter(client)

        with pytest.raises(AdapterException) as exc_info:
            await adapter.read_wal("dag-err")

        assert exc_info.value.adapter_name == "bridge_write"
        assert exc_info.value.severity.value == "DEGRADED"
        assert "K0_UNREACHABLE" in exc_info.value.error_code


class TestBridgeListWalIds:
    """Tests for BridgeWriteAdapter.list_wal_ids()."""

    @pytest.mark.asyncio
    async def test_list_wal_ids_success(self) -> None:
        client = FakeBridgeClient(read_data=["dag-1", "dag-2"])
        adapter = BridgeWriteAdapter(client)

        result = await adapter.list_wal_ids()

        assert result == ["dag-1", "dag-2"]

    @pytest.mark.asyncio
    async def test_list_wal_ids_empty(self) -> None:
        client = FakeBridgeClient(read_data=None)
        adapter = BridgeWriteAdapter(client)

        result = await adapter.list_wal_ids()

        assert result == []

    @pytest.mark.asyncio
    async def test_list_wal_ids_failure_raises(self) -> None:
        client = FakeBridgeClient(read_fail=True)
        adapter = BridgeWriteAdapter(client)

        with pytest.raises(AdapterException) as exc_info:
            await adapter.list_wal_ids()

        assert exc_info.value.adapter_name == "bridge_write"
        assert "K0_UNREACHABLE" in exc_info.value.error_code


class TestBridgeDeferredResult:
    """Tests for BridgeWriteAdapter.submit_deferred_result()."""

    @pytest.mark.asyncio
    async def test_submit_deferred_result_success(self) -> None:
        client = FakeBridgeClient()
        adapter = BridgeWriteAdapter(client)

        await adapter.submit_deferred_result({"output": "ok"}, "wf-1", "t-dr")

        assert len(client.writes) == 1
        channel, payload, trace_id = client.writes[0]
        assert channel == "deferred_result"
        assert payload["workflow_id"] == "wf-1"
        assert payload["result"]["output"] == "ok"
        assert trace_id == "t-dr"

    @pytest.mark.asyncio
    async def test_submit_deferred_result_failure_swallowed(self) -> None:
        client = FakeBridgeClient(write_fail=True)
        adapter = BridgeWriteAdapter(client)

        await adapter.submit_deferred_result({}, "w", "t")  # No raise


class TestBridgeSlots:
    """Structural checks for BridgeWriteAdapter."""

    def test_has_slots(self) -> None:
        assert hasattr(BridgeWriteAdapter, "__slots__")
        assert "_bridge" in BridgeWriteAdapter.__slots__


# ===================================================================
# Re-export tests
# ===================================================================


class TestAdaptersReExports:
    """Verify adapters are importable from the package."""

    def test_delta_emit_adapter_importable(self) -> None:
        from k1.orchestrator.adapters import DeltaEmitAdapter as DEA

        assert DEA is DeltaEmitAdapter

    def test_bridge_write_adapter_importable(self) -> None:
        from k1.orchestrator.adapters import BridgeWriteAdapter as BWA

        assert BWA is BridgeWriteAdapter
