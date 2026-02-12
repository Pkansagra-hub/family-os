"""
k1.orchestrator.adapters.mock_bridge_adapter -- MockBridgeAdapter (6.1.13).

Test/mock adapter for IBridgeWritePort.

Design:
  - In-memory audit log and WAL entries.
  - Optional pre-populated wal_store for crash recovery tests.
  - submit_audit and write_wal are fire-and-forget (never raise).
  - read_wal returns stored entries or None.
  - list_wal_ids returns all dag_ids with entries.
  - submit_deferred_result stores results for later assertion.

References:
  - Issue 6.1.13 in orchestrator-implementation-plan.md
  - k1/orchestrator/ports/bridge_write_port.py (IBridgeWritePort)

Exports:
  MockBridgeAdapter
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 6.1.13 -- MockBridgeAdapter
# ---------------------------------------------------------------------------


class MockBridgeAdapter:
    """
    Test IBridgeWritePort adapter with in-memory WAL and audit log.

    Pre-populate WAL via constructor ``wal_store`` or ``inject_wal()``
    for crash recovery tests.
    """

    def __init__(self, wal_store: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> None:
        self.audit_log: List[Tuple[Dict[str, Any], str]] = []
        self.wal_entries: Dict[str, List[Dict[str, Any]]] = (
            wal_store if wal_store is not None else {}
        )
        self.deferred_results: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # IBridgeWritePort.submit_audit
    # ------------------------------------------------------------------

    async def submit_audit(
        self,
        run_manifest: Dict[str, Any],
        trace_id: str,
    ) -> None:
        """Capture audit record. Fire-and-forget."""
        self.audit_log.append((run_manifest, trace_id))

    # ------------------------------------------------------------------
    # IBridgeWritePort.write_wal
    # ------------------------------------------------------------------

    async def write_wal(
        self,
        dag_id: str,
        entry_type: str,
        payload: Dict[str, Any],
        trace_id: str,
    ) -> None:
        """Write a WAL entry. Fire-and-forget."""
        self.wal_entries.setdefault(dag_id, []).append(
            {
                "entry_type": entry_type,
                "payload": payload,
                "trace_id": trace_id,
            }
        )

    # ------------------------------------------------------------------
    # IBridgeWritePort.read_wal
    # ------------------------------------------------------------------

    async def read_wal(
        self,
        dag_id: str,
    ) -> Optional[List[Dict[str, Any]]]:
        """Return WAL entries for dag_id or None."""
        entries = self.wal_entries.get(dag_id)
        return list(entries) if entries else None

    # ------------------------------------------------------------------
    # IBridgeWritePort.list_wal_ids
    # ------------------------------------------------------------------

    async def list_wal_ids(self) -> List[str]:
        """Return all dag_ids with WAL entries."""
        return list(self.wal_entries.keys())

    # ------------------------------------------------------------------
    # IBridgeWritePort.submit_deferred_result
    # ------------------------------------------------------------------

    async def submit_deferred_result(
        self,
        result: Dict[str, Any],
        workflow_id: str,
        trace_id: str,
    ) -> None:
        """Capture deferred result. Fire-and-forget."""
        self.deferred_results.append(
            {
                "result": result,
                "workflow_id": workflow_id,
                "trace_id": trace_id,
            }
        )

    # ------------------------------------------------------------------
    # Test helpers -- data setup
    # ------------------------------------------------------------------

    def inject_wal(
        self,
        dag_id: str,
        entries: List[Dict[str, Any]],
    ) -> None:
        """Pre-populate WAL entries for crash recovery tests."""
        self.wal_entries[dag_id] = list(entries)

    # ------------------------------------------------------------------
    # Test helpers -- assertions
    # ------------------------------------------------------------------

    def assert_audit_written(self, count: int = 1) -> None:
        """Assert that submit_audit was called *count* times."""
        actual = len(self.audit_log)
        assert actual == count, f"Expected {count} audit write(s), got {actual}"

    def assert_wal_written(self, dag_id: str, entry_type: str) -> None:
        """Assert that a WAL entry of *entry_type* exists for *dag_id*."""
        entries = self.wal_entries.get(dag_id, [])
        found = any(e["entry_type"] == entry_type for e in entries)
        assert found, (
            f"Expected WAL entry '{entry_type}' for dag '{dag_id}', "
            f"got {[e['entry_type'] for e in entries]}"
        )

    def get_wal(self, dag_id: str) -> List[Dict[str, Any]]:
        """Return WAL entries for dag_id (empty list if none)."""
        return list(self.wal_entries.get(dag_id, []))

    def reset(self) -> None:
        """Clear all logs and WAL entries."""
        self.audit_log.clear()
        self.wal_entries.clear()
        self.deferred_results.clear()
