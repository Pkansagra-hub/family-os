"""
k1.orchestrator.ports.admin_port -- IAdminPort (6.3.1).

Protocol interface for the Orchestrator admin/operational API.

Provides health probes, DAG inspection, circuit breaker management,
scheduler visibility, graceful drain, and read-only config access.

Endpoint groups (per Schema Whiteboard Section 5 + Section 6):
  1. Health       -- liveness, readiness, detailed status
  2. DAG          -- list active, detail, cancel
  3. Circuit Breakers -- list, force state
  4. Scheduler    -- list triggers, get trigger
  5. Drain        -- graceful drain with timeout
  6. Config       -- read-only config view
  7. Mailbox      -- depth, stats
  8. MCP          -- server list, rediscovery
  9. Metrics      -- aggregated metrics
  10. Version     -- build/version info

Production adapter: AdminHttpAdapter (6.3.2) in adapters/admin_http_adapter.py
Test adapter: direct method calls (no HTTP layer needed in tests).

References:
  - Schema Whiteboard Section 5 (Admin API -- 18 endpoints)
  - Schema Whiteboard Section 6 (Health Check Probes)
  - Admin types in types.py (1.2.25, 1.2.23)
  - orchestrator-implementation-plan.md Issue 6.3.1

Exports:
  IAdminPort
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from k1.orchestrator.types import (
    ActiveDAGInfo,
    CircuitBreakerState,
    DrainResult,
    HealthStatus,
)


@runtime_checkable
class IAdminPort(Protocol):
    """Protocol for operational admin access to the Orchestrator.

    All methods are async. Implementations must honour the read-only
    semantics (inspection only) except for the targeted write
    operations: cancel_dag, set_cb_state, drain, trigger_mcp_rediscovery.

    Health probes (health_live, health_ready) are designed for
    Kubernetes liveness/readiness checks and MUST be lightweight
    (no IO, no locks, sub-1ms response).

    Thread safety:
      Implementations MUST support concurrent calls from the
      aiohttp event loop (admin HTTP server) while the mailbox
      loop is running on the same asyncio event loop.
    """

    # ------------------------------------------------------------------
    # 1. Health probes (WB Section 6)
    # ------------------------------------------------------------------

    async def health_live(self) -> Dict[str, Any]:
        """Liveness check -- always 200 if the process is running.

        Returns:
            {"status": "alive"} -- constant response.
        """
        ...

    async def health_ready(self) -> Dict[str, Any]:
        """Readiness check -- 200 only after init() completes.

        Returns:
            {"ready": True/False, "initialized": bool, "running": bool}
        """
        ...

    async def health_status(self) -> HealthStatus:
        """Detailed health status including CB states, mailbox depth, uptime.

        HEALTHY:   CB_PLANNER closed, mailbox < 80%.
        DEGRADED:  CB_PLANNER open/half-open or consumed CB issues.
        UNHEALTHY: CB_PLANNER open AND mailbox at capacity.

        Returns:
            HealthStatus frozen dataclass.
        """
        ...

    # ------------------------------------------------------------------
    # 2. DAG inspection (WB Section 5)
    # ------------------------------------------------------------------

    async def list_active_dags(self) -> List[ActiveDAGInfo]:
        """List all currently active DAG executions.

        Returns:
            List of ActiveDAGInfo (may be empty if no DAG running).
        """
        ...

    async def get_dag_detail(self, dag_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific DAG execution.

        Args:
            dag_id: The DAG identifier to look up.

        Returns:
            Dict with DAG details, or None if not found.
        """
        ...

    async def cancel_dag(self, dag_id: str) -> bool:
        """Cancel an active DAG execution.

        Args:
            dag_id: The DAG identifier to cancel.

        Returns:
            True if cancellation was initiated, False if DAG not found.
        """
        ...

    # ------------------------------------------------------------------
    # 3. Circuit breakers (WB Section 5)
    # ------------------------------------------------------------------

    async def list_circuit_breakers(self) -> Dict[str, CircuitBreakerState]:
        """List all circuit breakers and their current state.

        Returns:
            Dict mapping CB name -> CircuitBreakerState.
        """
        ...

    async def set_cb_state(self, name: str, state: str) -> bool:
        """Force a circuit breaker to a specific state.

        Args:
            name: Circuit breaker name (e.g. "CB_PLANNER").
            state: Target state -- "OPEN", "CLOSED", or "HALF_OPEN".

        Returns:
            True if state was set, False if CB not found.
        """
        ...

    # ------------------------------------------------------------------
    # 4. Scheduler (WB Section 5)
    # ------------------------------------------------------------------

    async def list_triggers(self) -> List[Dict[str, Any]]:
        """List all workflow triggers and their schedule state.

        Returns:
            List of trigger info dicts.
        """
        ...

    async def get_trigger(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get trigger details for a specific workflow.

        Args:
            workflow_id: The workflow identifier.

        Returns:
            Trigger info dict, or None if not found.
        """
        ...

    # ------------------------------------------------------------------
    # 5. Drain (WB Section 5)
    # ------------------------------------------------------------------

    async def drain(self, timeout_ms: int = 30000) -> DrainResult:
        """Initiate graceful drain of active work.

        Stops accepting new messages and waits for in-flight DAGs
        to complete (up to timeout_ms).

        Args:
            timeout_ms: Maximum time to wait for drain (default 30s).

        Returns:
            DrainResult with drain status.
        """
        ...

    # ------------------------------------------------------------------
    # 6. Config (WB Section 5)
    # ------------------------------------------------------------------

    async def get_config(self) -> Dict[str, Any]:
        """Return read-only view of the OrchestratorConfig.

        Returns:
            Config as a JSON-serializable dict.
        """
        ...

    # ------------------------------------------------------------------
    # 7. Mailbox (WB Section 5)
    # ------------------------------------------------------------------

    async def get_mailbox_depth(self) -> Dict[str, Any]:
        """Return current mailbox queue depth.

        Returns:
            {"depth": int, "capacity": int}
        """
        ...

    async def get_mailbox_stats(self) -> Dict[str, Any]:
        """Return mailbox statistics.

        Returns:
            {"depth": int, "capacity": int, "pending_plans": int}
        """
        ...

    # ------------------------------------------------------------------
    # 8. MCP (WB Section 5)
    # ------------------------------------------------------------------

    async def list_mcp_servers(self) -> List[Dict[str, Any]]:
        """List registered MCP servers and their status.

        Returns:
            List of MCP server info dicts.
        """
        ...

    async def trigger_mcp_rediscovery(self) -> Dict[str, Any]:
        """Trigger MCP tool re-discovery.

        Returns:
            {"triggered": True, "message": str}
        """
        ...

    # ------------------------------------------------------------------
    # 9. Metrics (WB Section 5)
    # ------------------------------------------------------------------

    async def get_metrics(self) -> Dict[str, Any]:
        """Return aggregated operational metrics.

        Returns:
            Metrics dict (counters, gauges, histograms).
        """
        ...

    # ------------------------------------------------------------------
    # 10. Version (WB Section 5)
    # ------------------------------------------------------------------

    async def get_version(self) -> Dict[str, Any]:
        """Return Orchestrator version and build info.

        Returns:
            {"version": str, "build": str, "python": str}
        """
        ...
