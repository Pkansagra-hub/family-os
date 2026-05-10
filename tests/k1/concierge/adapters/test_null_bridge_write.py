"""
C2-prep Issue 4.4 — NullBridgeWriteAdapter tests.

Validates null adapter satisfies IBridgeWritePort — drops writes, empty reads.
"""

from __future__ import annotations

import asyncio

from k1.concierge.adapters.null_bridge_write import NullBridgeWriteAdapter
from k1.orchestrator.ports.bridge_write_port import IBridgeWritePort


class TestNullBridgeWriteProtocol:
    def test_satisfies_ibridgewriteport(self) -> None:
        assert isinstance(NullBridgeWriteAdapter(), IBridgeWritePort)


class TestNullBridgeWriteBehaviour:
    def test_submit_audit_no_op(self) -> None:
        adapter = NullBridgeWriteAdapter()
        asyncio.run(
            adapter.submit_audit({"plan_id": "p1"}, "trace-1")
        )

    def test_write_wal_no_op(self) -> None:
        adapter = NullBridgeWriteAdapter()
        asyncio.run(
            adapter.write_wal("dag-1", "PLAN_START", {"steps": []}, "trace-1")
        )

    def test_read_wal_returns_none(self) -> None:
        adapter = NullBridgeWriteAdapter()
        result = asyncio.run(adapter.read_wal("dag-1"))
        assert result is None

    def test_list_wal_ids_returns_empty(self) -> None:
        adapter = NullBridgeWriteAdapter()
        result = asyncio.run(adapter.list_wal_ids())
        assert result == []

    def test_submit_deferred_result_no_op(self) -> None:
        adapter = NullBridgeWriteAdapter()
        asyncio.run(
            adapter.submit_deferred_result({"data": 1}, "wf-1", "trace-1")
        )

