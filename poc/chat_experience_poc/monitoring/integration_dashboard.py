"""
Integration Health Dashboard

Provides real-time visibility into all system components for debugging integration issues.
Displays component health, latency (P95), and operational details in a formatted table.

Usage:
    from monitoring.integration_dashboard import get_integration_dashboard

    dashboard = get_integration_dashboard()
    status = await dashboard.display_status()
    print(status)

Architecture:
- Queries actual component instances for status/metrics
- Calculates P95 latency from component statistics
- Color-codes status: ✅ Green (healthy), ⚠️ Yellow (degraded), ❌ Red (failed)
- Alerts on unhealthy components (>30s), multiple failures, degraded performance
- Supports auto-refresh mode (5s interval)

Components Monitored:
- Layer 1: Intent Router
- Layer 3: Concierge Agent, Orchestrator, Specialists
- Layer 4: SessionState Manager, DeltaBus, Writer Agents, Temporal Module, ProactiveAgent
- Layer 5: K0 Bridge (Query & Batch), Tool Call Handler, User KG
- Mock Services: Mock MCP Server (external tools)

References:
- Issue 6.5.5.2 - Integration Health Dashboard
- docs/whiteboard/chat_experience.md - Observability requirements
- config/perf.yml - Performance budgets
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)


class ComponentStatus(Enum):
    """Component health status."""

    HEALTHY = "HEALTHY"
    ACTIVE = "ACTIVE"
    READY = "READY"
    RUNNING = "RUNNING"
    UP = "UP"
    DEGRADED = "DEGRADED"
    WARNING = "WARNING"
    ERROR = "ERROR"
    DOWN = "DOWN"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


@dataclass
class ComponentHealth:
    """Health information for a single component."""

    name: str
    status: ComponentStatus
    latency_p95_ms: float
    details: str
    last_check: datetime
    status_emoji: str = "✅"

    def __post_init__(self):
        """Set emoji based on status."""
        if self.status in {
            ComponentStatus.HEALTHY,
            ComponentStatus.ACTIVE,
            ComponentStatus.READY,
            ComponentStatus.RUNNING,
            ComponentStatus.UP,
        }:
            self.status_emoji = "✅"
        elif self.status in {ComponentStatus.DEGRADED, ComponentStatus.WARNING}:
            self.status_emoji = "⚠️"
        else:
            self.status_emoji = "❌"


class IntegrationDashboard:
    """
    Integration Health Dashboard for monitoring system components.

    Monitors all components and provides formatted status display with:
    - Health status (Healthy/Degraded/Failed)
    - P95 latency metrics
    - Operational details (request counts, queue depths, etc.)
    - Color-coded status indicators
    - Alerting for unhealthy components
    """

    def __init__(self):
        """Initialize Integration Dashboard."""
        self.unhealthy_start_times: Dict[str, datetime] = {}
        self.alert_threshold_seconds = 30
        self.performance_degradation_factor = 2.0

        # Component registry for tracking initialized components
        self.components: Dict[str, any] = {}

        # Performance budgets (from config/perf.yml or hardcoded)
        self.performance_budgets = {
            "Intent Router": 5.0,  # ms
            "Concierge Agent": 150.0,
            "Orchestrator": 50.0,
            "SessionState Manager": 1.0,
            "DeltaBus": 1.0,
            "MemoryWriterAgent": 15.0,
            "K0 Bridge (Query)": 50.0,
            "K0 Bridge (Batch)": 50.0,
            "Temporal Module": 5.0,
            "ProactiveAgent (SSE)": 5.0,
            "Mock MCP Server": 10.0,
            "User KG Database": 10.0,
        }

        logger.info("integration_dashboard_initialized")

    def register_component(self, name: str, component: any) -> None:
        """
        Register a component for health monitoring.

        Args:
            name: Component name (e.g., "Intent Router", "Concierge Agent")
            component: Component instance
        """
        self.components[name] = component
        logger.debug("dashboard_component_registered", name=name)

    async def display_status(self, refresh: bool = False) -> str:
        """
        Display system status table.

        Args:
            refresh: If True, continuously refresh every 5s

        Returns:
            Formatted status table as string
        """
        if refresh:
            # Auto-refresh mode
            while True:
                status = await self._generate_status_table()
                print("\033[2J\033[H")  # Clear screen
                print(status)
                await asyncio.sleep(5)
        else:
            # Single display
            return await self._generate_status_table()

    async def _generate_status_table(self) -> str:
        """
        Generate formatted status table.

        Returns:
            Formatted table string with all component statuses
        """
        # Collect health info for all components
        components = await self._check_all_components()

        # Build table
        lines = []
        lines.append("╔══════════════════════════════════════════════════════════════════╗")
        lines.append("║            K1 Intelligence Module - System Status                ║")
        lines.append("╠══════════════════════════════════════════════════════════════════╣")
        lines.append("║ Component                │ Status    │ Latency (P95) │ Details   ║")
        lines.append("╠══════════════════════════╪═══════════╪═══════════════╪═══════════╣")

        for comp in components:
            # Format component name (25 chars)
            name = comp.name.ljust(24)
            # Format status (9 chars with emoji)
            status = f"{comp.status_emoji} {comp.status.value}".ljust(9)
            # Format latency (13 chars)
            latency = f"{comp.latency_p95_ms:.1f}ms".ljust(13)
            # Format details (9 chars)
            details = comp.details[:9].ljust(9)

            line = f"║ {name} │ {status} │ {latency} │ {details} ║"
            lines.append(line)

        lines.append("╠══════════════════════════╧═══════════╧═══════════════╧═══════════╣")

        # Overall health summary
        overall_status = self._calculate_overall_health(components)
        lines.append(f"║ Overall System Health: {overall_status}                ║")
        lines.append("╚══════════════════════════════════════════════════════════════════╝")

        # Check for alerts
        await self._check_alerts(components)

        return "\n".join(lines)

    async def _check_all_components(self) -> List[ComponentHealth]:
        """
        Check health of all components.

        Returns:
            List of ComponentHealth objects
        """
        components = []

        # Try ComponentRegistry first
        try:
            from monitoring.component_registry import ComponentRegistry

            reg = ComponentRegistry.inst()
            registry_components = reg.all()

            # Convert registry components to ComponentHealth
            for comp_state in registry_components:
                status_map = {
                    "STARTING": ComponentStatus.WARNING,
                    "RUNNING": ComponentStatus.RUNNING,
                    "DEGRADED": ComponentStatus.DEGRADED,
                    "SHUTTING_DOWN": ComponentStatus.WARNING,
                    "DOWN": ComponentStatus.DOWN,
                    "UNKNOWN": ComponentStatus.UNKNOWN,
                }
                status = status_map.get(comp_state.status, ComponentStatus.UNKNOWN)

                components.append(
                    ComponentHealth(
                        name=comp_state.name,
                        status=status,
                        latency_p95_ms=comp_state.p95_ms or 0.0,
                        details=comp_state.details or "N/A",
                        last_check=datetime.utcnow(),
                    )
                )

            # If we got components from registry, return them
            if components:
                # Also check mock services (not in registry)
                components.append(await self._check_mock_mcp_server())
                return components

        except Exception as e:
            logger.debug("component_registry_check_failed", error=str(e))

        # Fallback: Individual checks
        # Layer 1: Intent Router
        components.append(await self._check_intent_router())

        # Layer 3: Agents
        components.append(await self._check_concierge_agent())
        components.append(await self._check_orchestrator())

        # Layer 4: Runtime Infrastructure
        components.append(await self._check_session_state_manager())
        components.append(await self._check_deltabus())
        components.append(await self._check_memory_writer_agent())
        components.append(await self._check_temporal_module())
        components.append(await self._check_proactive_agent())

        # Layer 5: Infrastructure
        components.append(await self._check_k0_bridge_query())
        components.append(await self._check_k0_bridge_batch())
        components.append(await self._check_user_kg())

        # Mock Services (monitored but marked as mock)
        components.append(await self._check_mock_mcp_server())

        return components

    # ========================================================================
    # Component Health Checks
    # ========================================================================

    async def _check_intent_router(self) -> ComponentHealth:
        """Check Intent Router health."""
        # Try ComponentRegistry first
        try:
            from monitoring.component_registry import get_component_registry

            registry = get_component_registry()
            comp_status = registry.get_status("Intent Router")
            if comp_status:
                router = comp_status.handle
                if router and hasattr(router, "get_stats"):
                    stats = router.get_stats()
                    latency = stats.get("avg_latency_ms", 0.0)
                    requests = stats.get("requests_total", 0)
                    return ComponentHealth(
                        name="Intent Router",
                        status=(
                            ComponentStatus.RUNNING
                            if comp_status.status == "RUNNING"
                            else ComponentStatus.DEGRADED
                        ),
                        latency_p95_ms=latency * 1.2,  # Estimate P95 from avg
                        details=f"{requests} req",
                        last_check=datetime.utcnow(),
                    )
        except Exception:
            pass

        # Fallback: Check if component is registered
        if "Intent Router" in self.components:
            router = self.components["Intent Router"]
            try:
                if hasattr(router, "get_stats"):
                    stats = router.get_stats()
                    latency = stats.get("avg_latency_ms", 0.0)
                    requests = stats.get("requests_total", 0)
                    return ComponentHealth(
                        name="Intent Router",
                        status=ComponentStatus.HEALTHY,
                        latency_p95_ms=latency * 1.2,  # Estimate P95 from avg
                        details=f"{requests} req",
                        last_check=datetime.utcnow(),
                    )
            except Exception as e:
                logger.debug("intent_router_check_failed", error=str(e))

        # Fallback: Try to import and get stats
        try:
            from l1_input.intent_router import get_intent_router

            router = get_intent_router()
            if hasattr(router, "get_stats"):
                stats = router.get_stats()
                latency = stats.get("avg_latency_ms", 0.0)
                requests = stats.get("requests_total", 0)
                return ComponentHealth(
                    name="Intent Router",
                    status=ComponentStatus.HEALTHY,
                    latency_p95_ms=latency * 1.2,  # Estimate P95 from avg
                    details=f"{requests} req",
                    last_check=datetime.utcnow(),
                )
        except Exception as e:
            logger.debug("intent_router_check_failed", error=str(e))

        return ComponentHealth(
            name="Intent Router",
            status=ComponentStatus.UNKNOWN,
            latency_p95_ms=0.0,
            details="Not init",
            last_check=datetime.utcnow(),
        )

    async def _check_concierge_agent(self) -> ComponentHealth:
        """Check Concierge Agent health."""
        # Check if component is registered
        if "Concierge Agent" in self.components:
            concierge = self.components["Concierge Agent"]
            try:
                if hasattr(concierge, "get_stats"):
                    stats = concierge.get_stats()
                    state = stats.get("lifecycle_state", "UNKNOWN")
                    turn_count = stats.get("turn_count", 0)
                    latency = stats.get("avg_latency_ms", 0.0)

                    status = (
                        ComponentStatus.ACTIVE if state == "ACTIVE" else ComponentStatus.WARNING
                    )

                    return ComponentHealth(
                        name="Concierge Agent",
                        status=status,
                        latency_p95_ms=latency * 1.2,
                        details=f"Turn {turn_count}",
                        last_check=datetime.utcnow(),
                    )
            except Exception as e:
                logger.debug("concierge_check_failed", error=str(e))

        # Fallback: Try to get active Concierge from Agent Pool
        try:
            from l4_runtime.agent_fabric.agent_pool import get_agent_pool

            pool = get_agent_pool()
            concierge = pool.get_agent_by_type("concierge")

            if concierge:
                stats = concierge.get_stats()
                state = stats.get("lifecycle_state", "UNKNOWN")
                turn_count = stats.get("turn_count", 0)
                latency = stats.get("avg_latency_ms", 0.0)

                status = ComponentStatus.ACTIVE if state == "ACTIVE" else ComponentStatus.WARNING

                return ComponentHealth(
                    name="Concierge Agent",
                    status=status,
                    latency_p95_ms=latency * 1.2,
                    details=f"Turn {turn_count}",
                    last_check=datetime.utcnow(),
                )
        except Exception as e:
            logger.debug("concierge_check_failed", error=str(e))

        return ComponentHealth(
            name="Concierge Agent",
            status=ComponentStatus.UNKNOWN,
            latency_p95_ms=0.0,
            details="Not init",
            last_check=datetime.utcnow(),
        )

    async def _check_orchestrator(self) -> ComponentHealth:
        """Check Orchestrator health."""
        try:
            from l2_orchestration.orchestrator.orchestrator import get_orchestrator

            orchestrator = get_orchestrator()
            if hasattr(orchestrator, "get_stats"):
                stats = orchestrator.get_stats()
                tasks = stats.get("tasks_completed", 0)
                latency = stats.get("avg_latency_ms", 0.0)

                return ComponentHealth(
                    name="Orchestrator",
                    status=ComponentStatus.READY,
                    latency_p95_ms=latency * 1.2,
                    details=f"{tasks} tasks",
                    last_check=datetime.utcnow(),
                )
        except Exception as e:
            logger.debug("orchestrator_check_failed", error=str(e))

        return ComponentHealth(
            name="Orchestrator",
            status=ComponentStatus.UNKNOWN,
            latency_p95_ms=0.0,
            details="Not init",
            last_check=datetime.utcnow(),
        )

    async def _check_session_state_manager(self) -> ComponentHealth:
        """Check SessionState Manager health."""
        try:
            from l4_runtime.session_state.session_state_manager import get_session_state_manager

            manager = get_session_state_manager()
            if hasattr(manager, "get_stats"):
                stats = manager.get_stats()
                sessions = stats.get("active_sessions", 0)
                latency = stats.get("avg_latency_ms", 0.0)

                return ComponentHealth(
                    name="SessionState Manager",
                    status=ComponentStatus.HEALTHY,
                    latency_p95_ms=latency * 1.2,
                    details=f"{sessions} sess",
                    last_check=datetime.utcnow(),
                )
        except Exception as e:
            logger.debug("session_state_manager_check_failed", error=str(e))

        return ComponentHealth(
            name="SessionState Manager",
            status=ComponentStatus.UNKNOWN,
            latency_p95_ms=0.0,
            details="Not init",
            last_check=datetime.utcnow(),
        )

    async def _check_deltabus(self) -> ComponentHealth:
        """Check DeltaBus health."""
        # Check if component is registered
        if "DeltaBus" in self.components:
            bus = self.components["DeltaBus"]
            try:
                if hasattr(bus, "get_stats"):
                    stats = bus.get_stats()
                    events = stats.get("events_published", 0)
                    latency = stats.get("avg_latency_ms", 0.0)

                    return ComponentHealth(
                        name="DeltaBus",
                        status=ComponentStatus.RUNNING,
                        latency_p95_ms=latency * 1.2,
                        details=f"{events} evt",
                        last_check=datetime.utcnow(),
                    )
            except Exception as e:
                logger.debug("deltabus_check_failed", error=str(e))

        # Fallback: Try to import
        try:
            from l4_runtime.deltabus.deltabus import get_deltabus

            bus = get_deltabus()
            if hasattr(bus, "get_stats"):
                stats = bus.get_stats()
                events = stats.get("events_published", 0)
                latency = stats.get("avg_latency_ms", 0.0)

                return ComponentHealth(
                    name="DeltaBus",
                    status=ComponentStatus.RUNNING,
                    latency_p95_ms=latency * 1.2,
                    details=f"{events} evt",
                    last_check=datetime.utcnow(),
                )
        except Exception as e:
            logger.debug("deltabus_check_failed", error=str(e))

        return ComponentHealth(
            name="DeltaBus",
            status=ComponentStatus.UNKNOWN,
            latency_p95_ms=0.0,
            details="Not init",
            last_check=datetime.utcnow(),
        )

    async def _check_memory_writer_agent(self) -> ComponentHealth:
        """Check MemoryWriter Agent health."""
        try:
            from l4_runtime.lifecycle.agent_pool import get_agent_pool

            pool = get_agent_pool()
            writer = pool.get_agent_by_type("memory_writer")

            if writer:
                stats = writer.get_stats()
                state = stats.get("lifecycle_state", "UNKNOWN")
                queue_depth = stats.get("mailbox_depth", 0)
                latency = stats.get("avg_latency_ms", 0.0)

                status = ComponentStatus.ACTIVE if state == "ACTIVE" else ComponentStatus.WARNING

                return ComponentHealth(
                    name="MemoryWriterAgent",
                    status=status,
                    latency_p95_ms=latency * 1.2,
                    details=f"Q: {queue_depth}",
                    last_check=datetime.utcnow(),
                )
        except Exception as e:
            logger.debug("memory_writer_check_failed", error=str(e))

        return ComponentHealth(
            name="MemoryWriterAgent",
            status=ComponentStatus.UNKNOWN,
            latency_p95_ms=0.0,
            details="Not init",
            last_check=datetime.utcnow(),
        )

    async def _check_temporal_module(self) -> ComponentHealth:
        """Check Temporal Module health."""
        try:
            from l5_infrastructure.temporal.temporal_module import get_temporal_module

            temporal = get_temporal_module()
            if hasattr(temporal, "get_stats"):
                stats = temporal.get_stats()
                triggers = stats.get("active_triggers", 0)
                latency = stats.get("avg_latency_ms", 0.0)

                return ComponentHealth(
                    name="Temporal Module",
                    status=ComponentStatus.RUNNING,
                    latency_p95_ms=latency * 1.2,
                    details=f"{triggers} trig",
                    last_check=datetime.utcnow(),
                )
        except Exception as e:
            logger.debug("temporal_module_check_failed", error=str(e))

        return ComponentHealth(
            name="Temporal Module",
            status=ComponentStatus.UNKNOWN,
            latency_p95_ms=0.0,
            details="Not init",
            last_check=datetime.utcnow(),
        )

    async def _check_proactive_agent(self) -> ComponentHealth:
        """Check ProactiveAgent SSE connection health."""
        try:
            from l4_runtime.lifecycle.agent_pool import get_agent_pool

            pool = get_agent_pool()
            proactive = pool.get_agent_by_type("proactive")

            if proactive:
                stats = proactive.get_stats()
                state = stats.get("lifecycle_state", "UNKNOWN")
                connected = stats.get("sse_connected", False)
                latency = stats.get("avg_latency_ms", 0.0)

                status = (
                    ComponentStatus.ACTIVE
                    if state == "ACTIVE" and connected
                    else ComponentStatus.WARNING
                )
                details = "Connected" if connected else "Disconn"

                return ComponentHealth(
                    name="ProactiveAgent (SSE)",
                    status=status,
                    latency_p95_ms=latency * 1.2,
                    details=details,
                    last_check=datetime.utcnow(),
                )
        except Exception as e:
            logger.debug("proactive_agent_check_failed", error=str(e))

        return ComponentHealth(
            name="ProactiveAgent (SSE)",
            status=ComponentStatus.UNKNOWN,
            latency_p95_ms=0.0,
            details="Not init",
            last_check=datetime.utcnow(),
        )

    async def _check_k0_bridge_query(self) -> ComponentHealth:
        """Check K0 Bridge Query Client health."""
        try:
            from l5_infrastructure.k0_bridge.k0_query_client import get_k0_query_client

            client = get_k0_query_client()
            if hasattr(client, "get_stats"):
                stats = client.get_stats()
                latency = stats.get("avg_latency_ms", 0.0)
                cache_hit_rate = stats.get("cache_hit_rate", 0.0)

                return ComponentHealth(
                    name="K0 Bridge (Query)",
                    status=ComponentStatus.HEALTHY,
                    latency_p95_ms=latency * 1.2,
                    details=f"Hit: {cache_hit_rate:.0%}",
                    last_check=datetime.utcnow(),
                )
        except Exception as e:
            logger.debug("k0_bridge_query_check_failed", error=str(e))

        return ComponentHealth(
            name="K0 Bridge (Query)",
            status=ComponentStatus.UNKNOWN,
            latency_p95_ms=0.0,
            details="Not init",
            last_check=datetime.utcnow(),
        )

    async def _check_k0_bridge_batch(self) -> ComponentHealth:
        """Check K0 Bridge Batch Client health."""
        try:
            from l5_infrastructure.k0_bridge.batch_client import get_batch_client

            client = get_batch_client()
            if hasattr(client, "get_stats"):
                stats = client.get_stats()
                batches = stats.get("batches_sent", 0)
                latency = stats.get("avg_latency_ms", 0.0)

                return ComponentHealth(
                    name="K0 Bridge (Batch)",
                    status=ComponentStatus.HEALTHY,
                    latency_p95_ms=latency * 1.2,
                    details=f"{batches} batch",
                    last_check=datetime.utcnow(),
                )
        except Exception as e:
            logger.debug("k0_bridge_batch_check_failed", error=str(e))

        return ComponentHealth(
            name="K0 Bridge (Batch)",
            status=ComponentStatus.UNKNOWN,
            latency_p95_ms=0.0,
            details="Not init",
            last_check=datetime.utcnow(),
        )

    async def _check_user_kg(self) -> ComponentHealth:
        """Check User KG Database health."""
        try:
            from l5_infrastructure.user_kg import get_user_kg

            kg = get_user_kg()
            if hasattr(kg, "get_stats"):
                stats = kg.get_stats()
                nodes = stats.get("total_nodes", 0)
                latency = stats.get("avg_latency_ms", 0.0)

                return ComponentHealth(
                    name="User KG Database",
                    status=ComponentStatus.HEALTHY,
                    latency_p95_ms=latency * 1.2,
                    details=f"{nodes} nodes",
                    last_check=datetime.utcnow(),
                )
        except Exception as e:
            logger.debug("user_kg_check_failed", error=str(e))

        return ComponentHealth(
            name="User KG Database",
            status=ComponentStatus.UNKNOWN,
            latency_p95_ms=0.0,
            details="Not init",
            last_check=datetime.utcnow(),
        )

    async def _check_mock_mcp_server(self) -> ComponentHealth:
        """Check Mock MCP Server health (external tools)."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get("http://localhost:8001/health")
                if response.status_code == 200:
                    return ComponentHealth(
                        name="Mock MCP Server (8001)",
                        status=ComponentStatus.UP,
                        latency_p95_ms=5.0,  # Mock estimate
                        details="Mock svc",
                        last_check=datetime.utcnow(),
                    )
        except Exception as e:
            logger.debug("mock_mcp_server_check_failed", error=str(e))

        return ComponentHealth(
            name="Mock MCP Server (8001)",
            status=ComponentStatus.DOWN,
            latency_p95_ms=0.0,
            details="Down",
            last_check=datetime.utcnow(),
        )

    # ========================================================================
    # Health Analysis & Alerting
    # ========================================================================

    def _calculate_overall_health(self, components: List[ComponentHealth]) -> str:
        """
        Calculate overall system health.

        Args:
            components: List of component health info

        Returns:
            Overall health status string with emoji
        """
        unhealthy_count = 0
        degraded_count = 0
        unknown_count = 0

        for comp in components:
            if comp.status in {
                ComponentStatus.ERROR,
                ComponentStatus.DOWN,
                ComponentStatus.FAILED,
            }:
                unhealthy_count += 1
            elif comp.status in {ComponentStatus.DEGRADED, ComponentStatus.WARNING}:
                degraded_count += 1
            elif comp.status == ComponentStatus.UNKNOWN:
                unknown_count += 1

        # UNKNOWN/DOWN treated as degraded unless they're mock services
        if unhealthy_count > 0:
            return f"❌ {unhealthy_count} SYSTEM(S) FAILED"
        elif degraded_count > 0 or unknown_count > 0:
            total_issues = degraded_count + unknown_count
            return f"⚠️ {total_issues} SYSTEM(S) DEGRADED/UNKNOWN"
        else:
            return "✅ ALL SYSTEMS OPERATIONAL"

    async def _check_alerts(self, components: List[ComponentHealth]) -> None:
        """
        Check for alert conditions and log warnings/errors.

        Conditions:
        - Component unhealthy >30s: Log ERROR
        - Multiple components unhealthy: Trigger shutdown warning
        - Performance degraded (P95 >2x budget): Log WARNING

        Args:
            components: List of component health info
        """
        now = datetime.utcnow()
        unhealthy_components = []

        for comp in components:
            # Check if unhealthy
            is_unhealthy = comp.status in {
                ComponentStatus.ERROR,
                ComponentStatus.DOWN,
                ComponentStatus.FAILED,
                ComponentStatus.WARNING,
            }

            if is_unhealthy:
                # Track start time
                if comp.name not in self.unhealthy_start_times:
                    self.unhealthy_start_times[comp.name] = now
                    logger.warning(
                        "component_became_unhealthy",
                        component=comp.name,
                        status=comp.status.value,
                    )
                else:
                    # Check duration
                    duration = (now - self.unhealthy_start_times[comp.name]).total_seconds()
                    if duration > self.alert_threshold_seconds:
                        logger.error(
                            "component_unhealthy_too_long",
                            component=comp.name,
                            status=comp.status.value,
                            duration_seconds=duration,
                        )
                        unhealthy_components.append(comp.name)
            else:
                # Clear unhealthy tracking
                if comp.name in self.unhealthy_start_times:
                    logger.info(
                        "component_recovered",
                        component=comp.name,
                        status=comp.status.value,
                    )
                    del self.unhealthy_start_times[comp.name]

            # Check performance degradation
            budget = self.performance_budgets.get(comp.name, float("inf"))
            if comp.latency_p95_ms > budget * self.performance_degradation_factor:
                logger.warning(
                    "component_performance_degraded",
                    component=comp.name,
                    latency_p95_ms=comp.latency_p95_ms,
                    budget_ms=budget,
                    factor=self.performance_degradation_factor,
                )

        # Multiple unhealthy components
        if len(unhealthy_components) >= 2:
            logger.error(
                "multiple_components_unhealthy_shutdown_recommended",
                unhealthy_components=unhealthy_components,
                count=len(unhealthy_components),
            )


# Singleton instance
_dashboard: Optional[IntegrationDashboard] = None


def get_integration_dashboard() -> IntegrationDashboard:
    """
    Get singleton Integration Dashboard instance.

    Returns:
        Global IntegrationDashboard instance
    """
    global _dashboard
    if _dashboard is None:
        _dashboard = IntegrationDashboard()
    return _dashboard
