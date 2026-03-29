"""
k1.orchestrator.ports.bridge_write_port -- IBridgeWritePort port (1.4.6).

Async fire-and-forget port for K0 Bridge writes (audit, WAL, deferred results).

Design:
  - All methods ASYNC, fire-and-forget for writes (K0 is best-effort,
    Edge-First architecture).
  - Write methods (submit_audit, write_wal, submit_deferred_result)
    catch exceptions, log warning, and return silently. K0 offline =
    data lost (V1 limitation).
  - Read methods (read_wal, list_wal_ids) raise AdapterError(DEGRADED)
    if K0 is unreachable. crash_recovery() handles this gracefully.

WAL entry_type values:
  - ``"PLAN_START"``     -- before wave 0, full plan persisted
  - ``"STEP_COMPLETE"``  -- after each step completes
  - ``"WAVE_COMPLETE"``  -- after each wave finishes
  - ``"DAG_COMPLETE"``   -- final, marks DAG as done

Consumers:
  - DAGExecutor (2.2.2, 2.2.6) -- WAL writes at each checkpoint
  - OrchestratorService.receive_plan() (2.1.4) -- submit_audit
  - crash_recovery() (6.2.4) -- read_wal, list_wal_ids
  - WorkflowScheduler (4.2.1) -- submit_deferred_result for cron results

Production adapter: BridgeWriteAdapter (6.1.6) in adapters/bridge_write_adapter.py
Test adapter: MockBridgeAdapter (6.1.13) in adapters/mock_bridge_adapter.py

References:
  - Edge-First architecture (K0 writes are best-effort)
  - docs/whiteboard/schema_whiteboard.md (S7 -- CB_BRIDGE)

Exports:
  IBridgeWritePort
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Port protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class IBridgeWritePort(Protocol):
    """
    Async port for K0 Bridge writes (audit trail, WAL, deferred results).

    Write operations are fire-and-forget: if K0 is offline, writes
    silently fail and data is lost. This is acceptable for Edge-First
    architecture where local execution takes priority over audit
    persistence.

    Read operations (read_wal, list_wal_ids) raise AdapterError(DEGRADED)
    if K0 is unreachable, allowing crash_recovery() to skip recovery
    gracefully.

    Thread safety:
      Implementations MUST support concurrent write calls from
      multiple asyncio tasks.
    """

    async def submit_audit(
        self,
        run_manifest: Dict[str, Any],
        trace_id: str,
    ) -> None:
        """
        Write a completed DAG execution record to K0 for audit trail.

        The run_manifest is ``AggregatedResult.to_dict()`` combined
        with CommittedPlan metadata.

        Args:
            run_manifest: Serialized execution record.
            trace_id: Cognitive trace identifier for correlation.

        Returns:
            None. Fire-and-forget -- catches exceptions internally.
        """
        ...  # pragma: no cover

    async def write_wal(
        self,
        dag_id: str,
        entry_type: str,
        payload: Dict[str, Any],
        trace_id: str,
    ) -> None:
        """
        Write a WAL entry for crash recovery.

        Called at each DAG checkpoint: PLAN_START, STEP_COMPLETE,
        WAVE_COMPLETE, DAG_COMPLETE.

        Args:
            dag_id: The DAG execution identifier (plan_id).
            entry_type: One of ``"PLAN_START"``, ``"STEP_COMPLETE"``,
                ``"WAVE_COMPLETE"``, ``"DAG_COMPLETE"``.
            payload: Checkpoint data for recovery.
            trace_id: Cognitive trace identifier for correlation.

        Returns:
            None. Fire-and-forget -- catches exceptions internally.
        """
        ...  # pragma: no cover

    async def read_wal(
        self,
        dag_id: str,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Read WAL entries for a specific DAG execution.

        Used by crash_recovery() (6.2.4) to determine where to
        resume a DAG that was interrupted by a crash.

        Args:
            dag_id: The DAG execution identifier to read WAL for.

        Returns:
            List of WAL entry dicts in chronological order, or
            ``None`` if no entries exist for this dag_id.

        Raises:
            AdapterError: With severity DEGRADED if K0 is unreachable.
        """
        ...  # pragma: no cover

    async def list_wal_ids(self) -> List[str]:
        """
        List all dag_ids with active WAL entries.

        Active means not yet ``DAG_COMPLETE`` or not cleaned up.
        Used by crash_recovery() (6.2.4) to scan for in-flight
        DAGs after restart.

        Returns:
            List of dag_id strings with pending WAL entries.

        Raises:
            AdapterError: With severity DEGRADED if K0 is unreachable.
                crash_recovery() skips recovery on this error.
        """
        ...  # pragma: no cover

    async def submit_deferred_result(
        self,
        result: Dict[str, Any],
        workflow_id: str,
        trace_id: str,
    ) -> None:
        """
        Persist a workflow execution result for later retrieval.

        Used when no user session is active (PROD-4: cron at 3 AM).
        Concierge checks for pending deferred results on next
        session start.

        Args:
            result: Serialized execution result.
            workflow_id: The workflow that produced this result.
            trace_id: Cognitive trace identifier for correlation.

        Returns:
            None. Fire-and-forget -- if K0 offline, result is lost
            (V1 limitation, logged).
        """
        ...  # pragma: no cover
