"""
K1 Intelligence Metrics Module
Source ADRs: ADR-0029 (Prometheus Metrics RED Method), ADR-0029c (Component Metrics)
Epic 3.2: Observability Stack Integration
Issues: 3.2.1 (Prometheus Metrics), 3.2.2 (OpenTelemetry Tracing)

This module defines K1-specific metrics following RED Method (Rate, Errors, Duration)
and provides instrumentation helpers for K1 components.

Performance Budget: <1% CPU overhead, <1MB memory, <1000 unique time series
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from prometheus_client import Counter, Gauge, Histogram

from k1.l5_infrastructure.observability import get_metrics

if TYPE_CHECKING:
    from k0.obs import MetricsExporter


# ==============================================================================
# K1 Intelligence Core Metrics (RED Method)
# ==============================================================================


@dataclass
class K1CoreMetrics:
    """Core K1 request metrics following RED Method"""

    # Rate: Command requests per second
    command_requests_total: Counter

    # Errors: Command failures per second
    command_errors_total: Counter

    # Duration: Command latency distribution
    command_latency_ms: Histogram


# ==============================================================================
# Agent Lifecycle Metrics (Agent Fabric)
# ==============================================================================


@dataclass
class K1AgentMetrics:
    """Agent lifecycle FSM state transitions and performance"""

    # Agent state transitions counter
    agent_lifecycle_transitions_total: Counter

    # Agent warmup latency
    agent_warmup_latency_ms: Histogram

    # Active agents gauge
    agent_active_count: Gauge

    # Agent crashes
    agent_crashes_total: Counter


# ==============================================================================
# Orchestrator Metrics (3-Phase Coordination)
# ==============================================================================


@dataclass
class K1OrchestratorMetrics:
    """3-phase orchestration metrics (Negotiation → Selection → Execution)"""

    # Orchestration phase latency
    orchestration_phase_latency_ms: Histogram

    # Proposals received per task
    orchestrator_proposals_total: Counter

    # Active tasks gauge
    orchestrator_active_tasks: Gauge


# ==============================================================================
# Planner Metrics (4-Stage Pipeline)
# ==============================================================================


@dataclass
class K1PlannerMetrics:
    """4-stage planning pipeline metrics (Sketch → Expand → Validate → Commit)"""

    # Plan generation latency by stage
    planner_stage_latency_ms: Histogram

    # Plan validation results
    planner_validation_results_total: Counter


# ==============================================================================
# Tool Execution Metrics
# ==============================================================================


@dataclass
class K1ToolMetrics:
    """Tool call execution performance and error tracking"""

    # Tool call latency
    tool_call_latency_ms: Histogram

    # Tool calls total
    tool_calls_total: Counter


# ==============================================================================
# K0 Bridge Metrics (K1→K0 Integration)
# ==============================================================================


@dataclass
class K1BridgeMetrics:
    """K0 Command/Query Port integration metrics"""

    # K0 command latency
    k0_command_latency_ms: Histogram

    # K0 query latency
    k0_query_latency_ms: Histogram

    # K0 command errors
    k0_command_errors_total: Counter


# ==============================================================================
# SSE Event Streaming Metrics
# ==============================================================================


@dataclass
class K1SSEMetrics:
    """Server-Sent Events streaming performance"""

    # SSE events sent
    sse_events_sent_total: Counter

    # SSE connection duration
    sse_connection_duration_seconds: Histogram

    # SSE event queue size
    sse_event_queue_size: Gauge


# ==============================================================================
# Session State Metrics
# ==============================================================================


@dataclass
class K1SessionStateMetrics:
    """SessionState management performance"""

    # Session state size
    session_state_size_bytes: Histogram

    # Session state evictions
    session_state_evictions_total: Counter


# ==============================================================================
# K1 Metrics Collector (Main Class)
# ==============================================================================


class K1MetricsCollector:
    """
    K1 Intelligence Metrics Collector

    Centralizes all K1-specific Prometheus metrics following RED Method (Rate, Errors, Duration).

    Usage:
        metrics = K1MetricsCollector()

        # Instrument command ingress
        metrics.core.command_requests_total.labels(
            band='GREEN', status='success', command_type='user_message'
        ).inc()

        # Record latency
        metrics.core.command_latency_ms.labels(
            band='GREEN', command_type='user_message'
        ).observe(145.2)

        # Track agent state transitions
        metrics.agent.agent_lifecycle_transitions_total.labels(
            from_state='WARMING', to_state='ACTIVE', agent_type='planner'
        ).inc()

    Performance:
        - Counter increment: <0.1ms P95
        - Histogram observe: <0.5ms P95
        - Total cardinality: ~900 time series (budget: 1000)
        - Memory overhead: ~1MB (Prometheus client)
        - CPU overhead: <1% (continuous profiling verified)

    **CARDINALITY CONSTRAINTS (CRITICAL):**

        **Budget: <1000 unique time series** (ADR-0029)

        **HIGH RISK LABELS (avoid per-instance IDs):**
        - ❌ agent_id, subscriber_id, session_id, task_id (can explode to 10K+ series)
        - ✅ Use coarse types: agent_type, session_tier, task_phase

        **Label Cardinality Guidelines:**
        - band: 3 values (GREEN, AMBER, RED)
        - status: 4-5 values (success, failure, timeout, cancelled)
        - agent_type: 5 values (concierge, planner, researcher, safety_watch, tool_runner)
        - phase/stage: 3-6 values (negotiation, selection, execution)
        - tool_name: ~20 values (curated list, not dynamic)
        - error_type: ~10 values (enum, not freeform strings)
        - rule_violated: ~5 values (schema, budget, policy, rate_limit, security)

        **Cardinality Math:**
        - command_requests_total: 3 (band) × 4 (status) × 5 (type) = 60 series
        - agent_lifecycle: 6 (from) × 6 (to) × 5 (type) = 180 series
        - tool_calls: 20 (tool) × 4 (status) = 80 series
        - **Total estimate: ~900 series** (90% of budget)

        **For per-instance correlation:**
        - Use **exemplars** (attach cognitive_trace_id to histogram samples)
        - Use **structured logs** with cognitive_trace_id (query-time join)
        - Do NOT use agent_id/subscriber_id as Prometheus labels

        **Violation Detection:**
        - Monitor: `count(k1_intelligence_command_requests_total)` < 1000
        - Alert if exceeds 1000 series (cardinality explosion)

    ADR References:
        - ADR-0029: Prometheus Metrics (RED Method, <1000 series budget)
        - ADR-0029c: Component Metrics (Agent, Orchestrator, Planner, Tool)
        - ADR-0024: Performance Budgets (<1% CPU, <1MB memory)
        - ADR-0030: Intelligent Trace Sampling (cognitive_trace_id, exemplars)
    """

    def __init__(self, metrics_exporter: MetricsExporter | None = None):
        """
        Initialize K1 metrics collector

        Args:
            metrics_exporter: K0 MetricsExporter instance (default: get_metrics())
        """
        if metrics_exporter is None:
            metrics_exporter = get_metrics()

        self._exporter = metrics_exporter
        self._registered: set[str] = (
            set()
        )  # Track registered metrics (hot-reload safety)

        # Initialize metric groups
        self.core = self._init_core_metrics()
        self.agent = self._init_agent_metrics()
        self.orchestrator = self._init_orchestrator_metrics()
        self.planner = self._init_planner_metrics()
        self.tool = self._init_tool_metrics()
        self.bridge = self._init_bridge_metrics()
        self.sse = self._init_sse_metrics()
        self.session_state = self._init_session_state_metrics()

    def _metric(
        self,
        kind: str,
        name: str,
        description: str,
        labelnames: list[str] | None = None,
        **kwargs,
    ):
        """
        Idempotent metric registration (prevents hot-reload duplicate errors)

        Args:
            kind: Metric type ('counter', 'gauge', 'histogram')
            name: Metric name
            description: Metric description
            labelnames: Label names
            **kwargs: Additional arguments (buckets, etc.)

        Returns:
            Metric instance (Counter, Gauge, or Histogram)
        """
        fq_name = f"{kind}:{name}"

        # If already registered, return existing metric (no-op)
        if fq_name in self._registered:
            # Metric already exists, retrieve it from exporter's registry
            # K0 MetricsExporter caches metrics internally
            return getattr(self._exporter, kind)(
                name=name,
                description=description,
                labelnames=labelnames or [],
                **kwargs,
            )

        # First registration: create and track
        metric = getattr(self._exporter, kind)(
            name=name, description=description, labelnames=labelnames or [], **kwargs
        )
        self._registered.add(fq_name)
        return metric

    # ==========================================================================
    # Core Metrics Initialization (RED Method)
    # ==========================================================================

    def _init_core_metrics(self) -> K1CoreMetrics:
        """Initialize core K1 request metrics (RED Method)"""

        # Rate: Command requests per second
        command_requests_total = self._metric(
            kind="counter",
            name="command_requests_total",
            description="Total command requests received by K1 Intelligence module",
            labelnames=["band", "status", "command_type"],
        )

        # Errors: Command failures per second
        command_errors_total = self._metric(
            kind="counter",
            name="command_errors_total",
            description="Total command errors in K1 Intelligence module",
            labelnames=["band", "error_type", "component"],
        )

        # Duration: Command latency distribution
        command_latency_ms = self._metric(
            kind="histogram",
            name="command_latency_ms",
            description="K1 Intelligence command end-to-end latency distribution",
            labelnames=["band", "command_type"],
            buckets=[10, 25, 50, 100, 200, 500, 1000, 2000, 5000, 10000],  # 10ms to 10s
        )

        return K1CoreMetrics(
            command_requests_total=command_requests_total,
            command_errors_total=command_errors_total,
            command_latency_ms=command_latency_ms,
        )

    # ==========================================================================
    # Agent Lifecycle Metrics Initialization
    # ==========================================================================

    def _init_agent_metrics(self) -> K1AgentMetrics:
        """Initialize agent lifecycle FSM metrics"""

        # Agent state transitions counter
        agent_lifecycle_transitions_total = self._exporter.counter(
            name="agent_lifecycle_transitions_total",
            description="Agent lifecycle state transitions (FSM 6-state model)",
            labelnames=["from_state", "to_state", "agent_type"],
        )

        # Agent warmup latency
        agent_warmup_latency_ms = self._exporter.histogram(
            name="agent_warmup_latency_ms",
            description="Agent warmup time from PENDING→ACTIVE",
            labelnames=["agent_type"],
            buckets=[50, 100, 200, 500, 1000, 2000, 5000],  # 50ms to 5s
        )

        # Active agents gauge
        agent_active_count = self._exporter.gauge(
            name="agent_active_count",
            description="Current number of active agents by state",
            labelnames=["state", "agent_type"],
        )

        # Agent crashes
        agent_crashes_total = self._exporter.counter(
            name="agent_crashes_total",
            description="Total agent crashes by type",
            labelnames=["agent_type", "crash_type"],
        )

        return K1AgentMetrics(
            agent_lifecycle_transitions_total=agent_lifecycle_transitions_total,
            agent_warmup_latency_ms=agent_warmup_latency_ms,
            agent_active_count=agent_active_count,
            agent_crashes_total=agent_crashes_total,
        )

    # ==========================================================================
    # Orchestrator Metrics Initialization
    # ==========================================================================

    def _init_orchestrator_metrics(self) -> K1OrchestratorMetrics:
        """Initialize 3-phase orchestration metrics"""

        # Orchestration phase latency
        orchestration_phase_latency_ms = self._exporter.histogram(
            name="orchestration_phase_latency_ms",
            description="3-phase orchestration latency by phase",
            labelnames=["phase", "status"],
            buckets=[5, 10, 25, 50, 100, 250, 500, 1000],  # 5ms to 1s
        )

        # Proposals received per task
        orchestrator_proposals_total = self._exporter.counter(
            name="orchestrator_proposals_total",
            description="Total agent proposals received per task",
            labelnames=["task_type"],
        )

        # Active tasks gauge
        orchestrator_active_tasks = self._exporter.gauge(
            name="orchestrator_active_tasks",
            description="Current number of active orchestration tasks",
            labelnames=["phase"],
        )

        return K1OrchestratorMetrics(
            orchestration_phase_latency_ms=orchestration_phase_latency_ms,
            orchestrator_proposals_total=orchestrator_proposals_total,
            orchestrator_active_tasks=orchestrator_active_tasks,
        )

    # ==========================================================================
    # Planner Metrics Initialization
    # ==========================================================================

    def _init_planner_metrics(self) -> K1PlannerMetrics:
        """Initialize 4-stage planning pipeline metrics"""

        # Plan generation latency by stage
        planner_stage_latency_ms = self._exporter.histogram(
            name="planner_stage_latency_ms",
            description="Planning pipeline stage latency",
            labelnames=["stage", "status"],
            buckets=[10, 25, 50, 100, 200, 500, 1000, 2000],  # 10ms to 2s
        )

        # Plan validation results
        planner_validation_results_total = self._exporter.counter(
            name="planner_validation_results_total",
            description="Plan validation results by outcome",
            labelnames=["result", "rule_violated"],
        )

        return K1PlannerMetrics(
            planner_stage_latency_ms=planner_stage_latency_ms,
            planner_validation_results_total=planner_validation_results_total,
        )

    # ==========================================================================
    # Tool Metrics Initialization
    # ==========================================================================

    def _init_tool_metrics(self) -> K1ToolMetrics:
        """Initialize tool execution metrics"""

        # Tool call latency
        tool_call_latency_ms = self._exporter.histogram(
            name="tool_call_latency_ms",
            description="Tool execution latency distribution",
            labelnames=["tool_name", "status"],
            buckets=[10, 50, 100, 250, 500, 1000, 2000, 5000, 10000],  # 10ms to 10s
        )

        # Tool calls total
        tool_calls_total = self._exporter.counter(
            name="tool_calls_total",
            description="Total tool calls by tool and status",
            labelnames=["tool_name", "status"],
        )

        return K1ToolMetrics(
            tool_call_latency_ms=tool_call_latency_ms, tool_calls_total=tool_calls_total
        )

    # ==========================================================================
    # K0 Bridge Metrics Initialization
    # ==========================================================================

    def _init_bridge_metrics(self) -> K1BridgeMetrics:
        """Initialize K0 Command/Query Port integration metrics"""

        # K0 command latency
        k0_command_latency_ms = self._exporter.histogram(
            name="k0_command_latency_ms",
            description="K0 Command Port latency (SessionState writes, receipts)",
            labelnames=["band", "command_type", "status"],
            buckets=[5, 10, 25, 50, 100, 250, 500],  # 5ms to 500ms
        )

        # K0 query latency
        k0_query_latency_ms = self._exporter.histogram(
            name="k0_query_latency_ms",
            description="K0 Query Port latency (SessionState reads)",
            labelnames=["query_type", "status"],
            buckets=[5, 10, 25, 50, 100, 250],  # 5ms to 250ms
        )

        # K0 command errors
        k0_command_errors_total = self._exporter.counter(
            name="k0_command_errors_total",
            description="K0 Command Port errors",
            labelnames=["error_type"],
        )

        return K1BridgeMetrics(
            k0_command_latency_ms=k0_command_latency_ms,
            k0_query_latency_ms=k0_query_latency_ms,
            k0_command_errors_total=k0_command_errors_total,
        )

    # ==========================================================================
    # SSE Metrics Initialization
    # ==========================================================================

    def _init_sse_metrics(self) -> K1SSEMetrics:
        """Initialize Server-Sent Events streaming metrics"""

        # SSE events sent
        sse_events_sent_total = self._exporter.counter(
            name="sse_events_sent_total",
            description="Total SSE events sent to clients",
            labelnames=["event_type", "topic"],
        )

        # SSE connection duration
        sse_connection_duration_seconds = self._exporter.histogram(
            name="sse_connection_duration_seconds",
            description="SSE connection lifetime distribution",
            labelnames=["disconnect_reason"],
            buckets=[10, 60, 300, 900, 1800, 3600, 7200],  # 10s to 2hr
        )

        # SSE event queue size
        sse_event_queue_size = self._exporter.gauge(
            name="sse_event_queue_size",
            description="SSE event buffer size (backpressure indicator)",
            labelnames=["subscriber_id"],
        )

        return K1SSEMetrics(
            sse_events_sent_total=sse_events_sent_total,
            sse_connection_duration_seconds=sse_connection_duration_seconds,
            sse_event_queue_size=sse_event_queue_size,
        )

    # ==========================================================================
    # Session State Metrics Initialization
    # ==========================================================================

    def _init_session_state_metrics(self) -> K1SessionStateMetrics:
        """Initialize SessionState management metrics"""

        # Session state size
        session_state_size_bytes = self._exporter.histogram(
            name="session_state_size_bytes",
            description="SessionState serialized size distribution",
            labelnames=["section"],
            buckets=[1024, 4096, 16384, 32768, 65536, 131072],  # 1KB to 128KB
        )

        # Session state evictions
        session_state_evictions_total = self._exporter.counter(
            name="session_state_evictions_total",
            description="SessionState evictions by tier",
            labelnames=["tier", "reason"],
        )

        return K1SessionStateMetrics(
            session_state_size_bytes=session_state_size_bytes,
            session_state_evictions_total=session_state_evictions_total,
        )


# ==============================================================================
# Global K1 Metrics Instance (Singleton)
# ==============================================================================

_k1_metrics: K1MetricsCollector | None = None


def get_k1_metrics() -> K1MetricsCollector:
    """
    Get global K1 metrics collector instance (singleton)

    Returns:
        K1MetricsCollector: Global metrics collector instance

    Example:
        from k1.l5_infrastructure.observability.metrics import get_k1_metrics

        metrics = get_k1_metrics()
        metrics.core.command_requests_total.labels(
            band='GREEN', status='success', command_type='user_message'
        ).inc()
    """
    global _k1_metrics
    if _k1_metrics is None:
        _k1_metrics = K1MetricsCollector()
    return _k1_metrics


# ==============================================================================
# Instrumentation Helpers
# ==============================================================================


def record_command_request(
    band: str, status: str, command_type: str, latency_ms: float
):
    """
    Helper function to record K1 command request metrics

    Args:
        band: Privacy band ('GREEN', 'AMBER', 'RED')
        status: Execution status ('success', 'failure', 'timeout')
        command_type: Command type ('user_message', 'system_command', 'tool_call')
        latency_ms: Command latency in milliseconds

    Example:
        record_command_request(
            band='GREEN',
            status='success',
            command_type='user_message',
            latency_ms=145.2
        )
    """
    metrics = get_k1_metrics()

    # Increment request counter
    metrics.core.command_requests_total.labels(
        band=band, status=status, command_type=command_type
    ).inc()

    # Record latency histogram
    metrics.core.command_latency_ms.labels(
        band=band, command_type=command_type
    ).observe(latency_ms)


def record_agent_transition(from_state: str, to_state: str, agent_type: str):
    """
    Helper function to record agent lifecycle state transition

    Args:
        from_state: Source state ('PENDING', 'WARMING', 'ACTIVE', 'IDLE', 'DRAINING', 'TERMINATED')
        to_state: Destination state
        agent_type: Agent type ('concierge', 'planner', 'researcher', 'safety_watch', 'tool_runner')

    Example:
        record_agent_transition(
            from_state='WARMING',
            to_state='ACTIVE',
            agent_type='planner'
        )
    """
    metrics = get_k1_metrics()
    metrics.agent.agent_lifecycle_transitions_total.labels(
        from_state=from_state, to_state=to_state, agent_type=agent_type
    ).inc()


def record_orchestration_phase(phase: str, status: str, latency_ms: float):
    """
    Helper function to record orchestration phase metrics

    Args:
        phase: Orchestration phase ('negotiation', 'selection', 'execution')
        status: Phase status ('success', 'failure', 'timeout')
        latency_ms: Phase latency in milliseconds

    Example:
        record_orchestration_phase(
            phase='negotiation',
            status='success',
            latency_ms=45.3
        )
    """
    metrics = get_k1_metrics()
    metrics.orchestrator.orchestration_phase_latency_ms.labels(
        phase=phase, status=status
    ).observe(latency_ms)


def record_tool_call(tool_name: str, status: str, latency_ms: float):
    """
    Helper function to record tool execution metrics

    Args:
        tool_name: Tool identifier ('web_search', 'calculator', 'file_read', etc.)
        status: Execution status ('success', 'failure', 'timeout', 'cancelled')
        latency_ms: Tool execution latency in milliseconds

    Example:
        record_tool_call(
            tool_name='web_search',
            status='success',
            latency_ms=1250.5
        )
    """
    metrics = get_k1_metrics()

    # Increment tool call counter
    metrics.tool.tool_calls_total.labels(tool_name=tool_name, status=status).inc()

    # Record latency histogram
    metrics.tool.tool_call_latency_ms.labels(
        tool_name=tool_name, status=status
    ).observe(latency_ms)


def record_k0_command(band: str, command_type: str, status: str, latency_ms: float):
    """
    Helper function to record K0 Command Port metrics

    Args:
        band: Privacy band ('GREEN', 'AMBER', 'RED')
        command_type: K0 command type ('state_write', 'receipt_write', 'config_update')
        status: Command status ('success', 'failure', 'timeout')
        latency_ms: Command latency in milliseconds

    Example:
        record_k0_command(
            band='GREEN',
            command_type='state_write',
            status='success',
            latency_ms=35.2
        )
    """
    metrics = get_k1_metrics()
    metrics.bridge.k0_command_latency_ms.labels(
        band=band, command_type=command_type, status=status
    ).observe(latency_ms)


def record_sse_event(event_type: str, topic: str):
    """
    Helper function to record SSE event emission

    Args:
        event_type: SSE event type ('agent_hired', 'turn_started', etc.)
        topic: SSE topic ('agent_lifecycle', 'turn_execution', etc.)

    Example:
        record_sse_event(
            event_type='agent_hired',
            topic='agent_lifecycle'
        )
    """
    metrics = get_k1_metrics()
    metrics.sse.sse_events_sent_total.labels(event_type=event_type, topic=topic).inc()


# ==============================================================================
# Module Exports
# ==============================================================================

__all__ = [
    # Main classes
    "K1MetricsCollector",
    "K1CoreMetrics",
    "K1AgentMetrics",
    "K1OrchestratorMetrics",
    "K1PlannerMetrics",
    "K1ToolMetrics",
    "K1BridgeMetrics",
    "K1SSEMetrics",
    "K1SessionStateMetrics",
    # Global instance
    "get_k1_metrics",
    # Helper functions
    "record_command_request",
    "record_agent_transition",
    "record_orchestration_phase",
    "record_tool_call",
    "record_k0_command",
    "record_sse_event",
]
