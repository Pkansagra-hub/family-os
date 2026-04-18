"""
k1.orchestrator.adapters.admin_http_adapter -- AdminHttpAdapter (6.3.2).

Production adapter for IAdminPort.

Lightweight aiohttp HTTP server providing 18 endpoints per Schema
Whiteboard Section 5 + Section 6 (health probes). Runs on a separate
port (default 8081) and does NOT share the mailbox loop.

Design:
  - Wraps OrchestratorService internal state for read-only admin access.
  - All responses are JSON with X-Trace-Id header.
  - Auth: None in V1 (localhost-only, per WB Section 5 security note).
  - start()/stop() lifecycle managed by OrchestratorFactory (6.3.3).
  - aiohttp lightweight -- uses web.Application, web.AppRunner, web.TCPSite.
    No middleware, no sessions, no CORS.

Endpoint mapping (18 routes, WB Section 5):
  GET  /health/live              -> health_live()
  GET  /health/ready             -> health_ready()
  GET  /health/status            -> health_status()
  GET  /admin/dags               -> list_active_dags()
  GET  /admin/dags/{dag_id}      -> get_dag_detail(dag_id)
  POST /admin/dags/{dag_id}/cancel -> cancel_dag(dag_id)
  GET  /admin/circuit-breakers   -> list_circuit_breakers()
  POST /admin/circuit-breakers/{name}/state -> set_cb_state(name, state)
  GET  /admin/scheduler/triggers -> list_triggers()
  GET  /admin/scheduler/triggers/{workflow_id} -> get_trigger(workflow_id)
  POST /admin/drain              -> drain(timeout_ms)
  GET  /admin/config             -> get_config()
  GET  /admin/mailbox/depth      -> get_mailbox_depth()
  GET  /admin/mailbox/stats      -> get_mailbox_stats()
  GET  /admin/mcp/servers        -> list_mcp_servers()
  POST /admin/mcp/rediscover     -> trigger_mcp_rediscovery()
  GET  /admin/metrics            -> get_metrics()
  GET  /admin/version            -> get_version()

References:
  - orchestrator-implementation-plan.md Issue 6.3.2
  - Schema Whiteboard Section 5 (Admin API)
  - Schema Whiteboard Section 6 (Health Check Probes)
  - Admin types in types.py (1.2.25, 1.2.23)

Exports:
  AdminHttpAdapter
"""

from __future__ import annotations

import logging
import platform
import sys
import time
from dataclasses import asdict
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from uuid import uuid4

from aiohttp import web

from k1.orchestrator.degradation import CircuitBreaker
from k1.orchestrator.types import (
    ActiveDAGInfo,
    CircuitBreakerConfig,
    CircuitBreakerState,
    DrainResult,
    HealthStatus,
)

if TYPE_CHECKING:
    from k1.orchestrator.config import OrchestratorConfig
    from k1.orchestrator.orchestration.orchestrator_service import OrchestratorService

logger = logging.getLogger(__name__)

_VERSION = "0.1.0"


class AdminHttpAdapter:
    """Lightweight aiohttp admin HTTP server for the Orchestrator.

    Implements IAdminPort protocol. Wraps OrchestratorService internal
    state for read-only access plus targeted write operations (cancel,
    drain, CB state, MCP rediscovery).

    Lifecycle:
      - Created by OrchestratorFactory step 15.5 (after service).
      - start(port) called during init() step 9.5.
      - stop() called during shutdown() before port disconnect.
    """

    __slots__ = (
        "_service",
        "_config",
        "_app",
        "_runner",
        "_site",
        "_started_at",
    )

    def __init__(
        self,
        service: "OrchestratorService",
        config: "OrchestratorConfig",
    ) -> None:
        self._service = service
        self._config = config
        self._app = web.Application()
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._started_at: float = time.time()
        self._register_routes()

    # ==================================================================
    # Route registration
    # ==================================================================

    def _register_routes(self) -> None:
        """Register all 18 admin endpoints."""
        self._app.router.add_get("/health/live", self._handle_health_live)
        self._app.router.add_get("/health/ready", self._handle_health_ready)
        self._app.router.add_get("/health/status", self._handle_health_status)
        self._app.router.add_get("/admin/dags", self._handle_list_dags)
        self._app.router.add_get("/admin/dags/{dag_id}", self._handle_get_dag)
        self._app.router.add_post("/admin/dags/{dag_id}/cancel", self._handle_cancel_dag)
        self._app.router.add_get("/admin/circuit-breakers", self._handle_list_cbs)
        self._app.router.add_post("/admin/circuit-breakers/{name}/state", self._handle_set_cb_state)
        self._app.router.add_get("/admin/scheduler/triggers", self._handle_list_triggers)
        self._app.router.add_get(
            "/admin/scheduler/triggers/{workflow_id}",
            self._handle_get_trigger,
        )
        self._app.router.add_post("/admin/drain", self._handle_drain)
        self._app.router.add_get("/admin/config", self._handle_get_config)
        self._app.router.add_get("/admin/mailbox/depth", self._handle_mailbox_depth)
        self._app.router.add_get("/admin/mailbox/stats", self._handle_mailbox_stats)
        self._app.router.add_get("/admin/mcp/servers", self._handle_list_mcp_servers)
        self._app.router.add_post("/admin/mcp/rediscover", self._handle_mcp_rediscovery)
        self._app.router.add_get("/admin/metrics", self._handle_get_metrics)
        self._app.router.add_get("/admin/version", self._handle_get_version)

    # ==================================================================
    # Lifecycle
    # ==================================================================

    async def start(self, port: int) -> None:
        """Start the admin HTTP server on the given port.

        Args:
            port: TCP port to bind (default 8081 from config).
        """
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "127.0.0.1", port)
        await self._site.start()
        self._started_at = time.time()
        logger.info(
            "admin_http.started",
            extra={"port": port, "host": "127.0.0.1"},
        )

    async def stop(self) -> None:
        """Stop the admin HTTP server gracefully."""
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
            self._site = None
            logger.info("admin_http.stopped")

    # ==================================================================
    # Helper: JSON response with trace_id header
    # ==================================================================

    @staticmethod
    def _json_response(
        data: Any,
        *,
        status: int = 200,
        trace_id: Optional[str] = None,
    ) -> web.Response:
        """Build a JSON response with X-Trace-Id header."""
        tid = trace_id or str(uuid4())
        return web.json_response(
            data,
            status=status,
            headers={"X-Trace-Id": tid},
        )

    # ==================================================================
    # 1. Health endpoints
    # ==================================================================

    async def health_live(self) -> Dict[str, Any]:
        """IAdminPort.health_live -- always alive if process running."""
        return {"status": "alive"}

    async def health_ready(self) -> Dict[str, Any]:
        """IAdminPort.health_ready -- ready only after init() completes."""
        return {
            "ready": self._service.initialized and self._service.running,
            "initialized": self._service.initialized,
            "running": self._service.running,
        }

    async def health_status(self) -> HealthStatus:
        """IAdminPort.health_status -- detailed health."""
        uptime_ms = int((time.time() - self._started_at) * 1000)
        depth = self._service._mailbox.depth()
        capacity = self._config.mailbox_capacity

        # CB states -- V1 only CB_PLANNER is Orchestrator-owned.
        cb_states: Dict[str, str] = {}
        planner_adapter = self._service._planner_port
        cb = getattr(planner_adapter, "_cb", None)
        if cb is not None:
            cb_states["CB_PLANNER"] = getattr(cb, "state", "UNKNOWN")

        # Determine status
        cb_planner_state = cb_states.get("CB_PLANNER", "CLOSED")
        if cb_planner_state == "CLOSED" and depth < capacity * 0.8:
            status = "HEALTHY"
        elif cb_planner_state == "OPEN" and depth >= capacity:
            status = "UNHEALTHY"
        else:
            status = "DEGRADED"

        # Active DAGs = 1 if concurrency guard active, else 0.
        active_dags = 1 if getattr(self._service._concurrency_guard, "active", False) else 0

        return HealthStatus(
            status=status,
            uptime_ms=uptime_ms,
            active_dags=active_dags,
            mailbox_depth=depth,
            circuit_breakers=cb_states,
        )

    async def _handle_health_live(self, request: web.Request) -> web.Response:
        data = await self.health_live()
        return self._json_response(data)

    async def _handle_health_ready(self, request: web.Request) -> web.Response:
        data = await self.health_ready()
        status_code = 200 if data.get("ready") else 503
        return self._json_response(data, status=status_code)

    async def _handle_health_status(self, request: web.Request) -> web.Response:
        hs = await self.health_status()
        return self._json_response(asdict(hs))

    # ==================================================================
    # 2. DAG inspection
    # ==================================================================

    async def list_active_dags(self) -> List[ActiveDAGInfo]:
        """IAdminPort.list_active_dags -- list running DAGs."""
        # V1: max 1 concurrent DAG. Check concurrency guard.
        if not getattr(self._service._concurrency_guard, "active", False):
            return []
        # DAG details are not stored on OrchestratorService directly
        # in V1. Return minimal info from DAGExecutor if available.
        executor = self._service._dag_executor
        current = getattr(executor, "_current_dag_info", None)
        if current is not None and isinstance(current, ActiveDAGInfo):
            return [current]
        return []

    async def get_dag_detail(self, dag_id: str) -> Optional[Dict[str, Any]]:
        """IAdminPort.get_dag_detail -- get DAG details."""
        dags = await self.list_active_dags()
        for dag in dags:
            if dag.dag_id == dag_id:
                return asdict(dag)
        return None

    async def cancel_dag(self, dag_id: str) -> bool:
        """IAdminPort.cancel_dag -- cancel active DAG."""
        dags = await self.list_active_dags()
        for dag in dags:
            if dag.dag_id == dag_id:
                # Set interrupt flag on DAGExecutor (cooperative cancel).
                executor = self._service._dag_executor
                if hasattr(executor, "interrupt_flag"):
                    executor.interrupt_flag = True
                return True
        return False

    async def _handle_list_dags(self, request: web.Request) -> web.Response:
        dags = await self.list_active_dags()
        return self._json_response([asdict(d) for d in dags])

    async def _handle_get_dag(self, request: web.Request) -> web.Response:
        dag_id = request.match_info["dag_id"]
        detail = await self.get_dag_detail(dag_id)
        if detail is None:
            return self._json_response({"error": "DAG not found", "dag_id": dag_id}, status=404)
        return self._json_response(detail)

    async def _handle_cancel_dag(self, request: web.Request) -> web.Response:
        dag_id = request.match_info["dag_id"]
        cancelled = await self.cancel_dag(dag_id)
        if not cancelled:
            return self._json_response({"error": "DAG not found", "dag_id": dag_id}, status=404)
        return self._json_response({"cancelled": True, "dag_id": dag_id})

    # ==================================================================
    # 3. Circuit breakers
    # ==================================================================

    async def list_circuit_breakers(self) -> Dict[str, CircuitBreakerState]:
        """IAdminPort.list_circuit_breakers -- list CB states."""
        result: Dict[str, CircuitBreakerState] = {}
        planner_adapter = self._service._planner_port
        cb = getattr(planner_adapter, "_cb", None)
        if cb is not None and isinstance(cb, CircuitBreaker):
            result["CB_PLANNER"] = CircuitBreakerState(
                config=CircuitBreakerConfig(
                    name=cb.name,
                    failure_threshold=cb._failure_threshold,
                    reset_timeout_ms=cb._half_open_after_ms,
                ),
                state=cb.state.value,
                failure_count=cb.failure_count,
            )
        return result

    async def set_cb_state(self, name: str, state: str) -> bool:
        """IAdminPort.set_cb_state -- force CB to specific state."""
        if name != "CB_PLANNER":
            return False
        planner_adapter = self._service._planner_port
        cb = getattr(planner_adapter, "_cb", None)
        if cb is None or not isinstance(cb, CircuitBreaker):
            return False
        if state not in ("OPEN", "CLOSED", "HALF_OPEN"):
            return False
        if state == "CLOSED":
            cb.reset()
        elif state == "OPEN":
            cb.trip()
        return True

    async def _handle_list_cbs(self, request: web.Request) -> web.Response:
        cbs = await self.list_circuit_breakers()
        serialized: Dict[str, Any] = {}
        for name, cb_state in cbs.items():
            serialized[name] = {
                "state": cb_state.state,
                "failure_count": cb_state.failure_count,
                "last_failure_at": cb_state.last_failure_at,
                "last_success_at": cb_state.last_success_at,
                "opened_at": cb_state.opened_at,
            }
        return self._json_response(serialized)

    async def _handle_set_cb_state(self, request: web.Request) -> web.Response:
        name = request.match_info["name"]
        try:
            body = await request.json()
            target_state = body.get("state", "")
        except Exception:
            return self._json_response({"error": "Invalid JSON body"}, status=400)
        ok = await self.set_cb_state(name, target_state)
        if not ok:
            return self._json_response(
                {"error": f"CB '{name}' not found or invalid state"},
                status=404,
            )
        return self._json_response({"name": name, "state": target_state, "updated": True})

    # ==================================================================
    # 4. Scheduler
    # ==================================================================

    async def list_triggers(self) -> List[Dict[str, Any]]:
        """IAdminPort.list_triggers -- list workflow triggers."""
        scheduler = getattr(self._service._workflow_engine, "scheduler", None)
        if scheduler is None:
            return []
        # V1: scheduler does not expose trigger listing directly.
        # Return basic info if available.
        triggers = getattr(scheduler, "_triggers", {})
        result: List[Dict[str, Any]] = []
        for wf_id, trigger_info in triggers.items():
            result.append(
                {
                    "workflow_id": wf_id,
                    "trigger": str(trigger_info),
                }
            )
        return result

    async def get_trigger(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """IAdminPort.get_trigger -- get trigger for a workflow."""
        triggers = await self.list_triggers()
        for t in triggers:
            if t.get("workflow_id") == workflow_id:
                return t
        return None

    async def _handle_list_triggers(self, request: web.Request) -> web.Response:
        triggers = await self.list_triggers()
        return self._json_response(triggers)

    async def _handle_get_trigger(self, request: web.Request) -> web.Response:
        wf_id = request.match_info["workflow_id"]
        trigger = await self.get_trigger(wf_id)
        if trigger is None:
            return self._json_response(
                {"error": "Trigger not found", "workflow_id": wf_id},
                status=404,
            )
        return self._json_response(trigger)

    # ==================================================================
    # 5. Drain
    # ==================================================================

    async def drain(self, timeout_ms: int = 30000) -> DrainResult:
        """IAdminPort.drain -- graceful drain."""
        import asyncio

        t0 = time.monotonic()
        deadline = t0 + (timeout_ms / 1000.0)

        # Stop accepting new messages.
        self._service._running = False

        # Wait for active DAGs to complete.
        timed_out = False
        while getattr(self._service._concurrency_guard, "active", False):
            if time.monotonic() >= deadline:
                timed_out = True
                break
            await asyncio.sleep(0.1)

        active_remaining = 1 if getattr(self._service._concurrency_guard, "active", False) else 0
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        return DrainResult(
            drained=active_remaining == 0,
            active_dags_remaining=active_remaining,
            timeout_reached=timed_out,
            duration_ms=elapsed_ms,
        )

    async def _handle_drain(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
            timeout_ms = body.get("timeout_ms", 30000)
        except Exception:
            timeout_ms = 30000
        result = await self.drain(timeout_ms=timeout_ms)
        return self._json_response(asdict(result))

    # ==================================================================
    # 6. Config
    # ==================================================================

    async def get_config(self) -> Dict[str, Any]:
        """IAdminPort.get_config -- read-only config view."""
        return self._config.to_dict()

    async def _handle_get_config(self, request: web.Request) -> web.Response:
        cfg = await self.get_config()
        return self._json_response(cfg)

    # ==================================================================
    # 7. Mailbox
    # ==================================================================

    async def get_mailbox_depth(self) -> Dict[str, Any]:
        """IAdminPort.get_mailbox_depth -- current queue depth."""
        return {
            "depth": self._service._mailbox.depth(),
            "capacity": self._config.mailbox_capacity,
        }

    async def get_mailbox_stats(self) -> Dict[str, Any]:
        """IAdminPort.get_mailbox_stats -- queue stats."""
        return {
            "depth": self._service._mailbox.depth(),
            "capacity": self._config.mailbox_capacity,
            "pending_plans": len(self._service.pending_plans),
            "pending_hil": len(self._service.pending_hil),
        }

    async def _handle_mailbox_depth(self, request: web.Request) -> web.Response:
        data = await self.get_mailbox_depth()
        return self._json_response(data)

    async def _handle_mailbox_stats(self, request: web.Request) -> web.Response:
        data = await self.get_mailbox_stats()
        return self._json_response(data)

    # ==================================================================
    # 8. MCP
    # ==================================================================

    async def list_mcp_servers(self) -> List[Dict[str, Any]]:
        """IAdminPort.list_mcp_servers -- list registered MCP servers."""
        lifecycle = self._service._connector_lifecycle
        # V1: ConnectorLifecycleManager stores discovery results.
        last_result = getattr(lifecycle, "_last_registration", None)
        if last_result is None:
            return []
        # RegistrationResult has registered, skipped, errors, tools fields.
        return [
            {
                "registered": getattr(last_result, "registered", 0),
                "skipped": getattr(last_result, "skipped", 0),
                "errors": getattr(last_result, "errors", []),
                "tools": [str(t) for t in getattr(last_result, "tools", [])],
            }
        ]

    async def trigger_mcp_rediscovery(self) -> Dict[str, Any]:
        """IAdminPort.trigger_mcp_rediscovery -- trigger rediscovery."""
        try:
            result = await self._service._connector_lifecycle.discover_and_register()  # type: ignore[union-attr]
            return {
                "triggered": True,
                "registered": result.registered,
                "skipped": result.skipped,
                "errors": result.errors,
            }
        except Exception as exc:
            return {
                "triggered": False,
                "error": str(exc),
            }

    async def _handle_list_mcp_servers(self, request: web.Request) -> web.Response:
        servers = await self.list_mcp_servers()
        return self._json_response(servers)

    async def _handle_mcp_rediscovery(self, request: web.Request) -> web.Response:
        result = await self.trigger_mcp_rediscovery()
        return self._json_response(result)

    # ==================================================================
    # 9. Metrics
    # ==================================================================

    async def get_metrics(self) -> Dict[str, Any]:
        """IAdminPort.get_metrics -- aggregated metrics."""
        uptime_ms = int((time.time() - self._started_at) * 1000)
        return {
            "uptime_ms": uptime_ms,
            "mailbox_depth": self._service._mailbox.depth(),
            "pending_plans": len(self._service.pending_plans),
            "pending_hil": len(self._service.pending_hil),
            "executed_plans_count": len(self._service.executed_plans),
            "initialized": self._service.initialized,
            "running": self._service.running,
        }

    async def _handle_get_metrics(self, request: web.Request) -> web.Response:
        data = await self.get_metrics()
        return self._json_response(data)

    # ==================================================================
    # 10. Version
    # ==================================================================

    async def get_version(self) -> Dict[str, Any]:
        """IAdminPort.get_version -- build/version info."""
        return {
            "version": _VERSION,
            "build": "k1-orchestrator",
            "python": platform.python_version(),
            "platform": sys.platform,
        }

    async def _handle_get_version(self, request: web.Request) -> web.Response:
        data = await self.get_version()
        return self._json_response(data)
