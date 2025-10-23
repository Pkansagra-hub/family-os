"""
Agent Observability & Metrics (ADR-0086h)

Purpose:
    Export 25+ Prometheus metrics and OpenTelemetry traces for dynamic agent
    lifecycle, resource usage, and performance. Enables Grafana dashboards for
    agent health monitoring and performance analysis.

Architecture:
    - 25+ Prometheus metrics (counters, histograms, gauges)
    - OpenTelemetry tracing (4-level span hierarchy)
    - 3 Grafana dashboards (Performance, Resources, Lifecycle)
    - Cardinality management: <10K active time series

Performance Targets:
    - Metric emission: <1ms P95
    - Trace overhead: <5% CPU
    - Cardinality: <10K active time series
    - Dashboard query: <500ms P95

Key Metrics:
    1. Creation: agent_creation_total, agent_creation_latency_ms
    2. Termination: agent_termination_total (by policy)
    3. Reuse: agent_reuse_total, agent_reuse_latency_ms
    4. Performance: agent_execution_latency_ms, agent_ttft_ms
    5. Resources: agent_memory_allocated_mb, agent_accelerator_usage

Related ADRs:
    - ADR-0086: Dynamic Agent Creation Subsystem (parent)
    - ADR-0086a: Agent Factory (creation metrics)
    - ADR-0086f: Lifecycle Integration (reuse metrics)
    - ADR-0086c: Resource Reservation (resource metrics)

Research Foundation:
    - Prometheus Best Practices (CNCF)
    - OpenTelemetry Specification (CNCF)
    - RED Method (Weaver 2015)

Implementation Status: STUB (M2 - 4 days planned)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from opentelemetry import trace
from opentelemetry.trace import Span, Tracer  # type: ignore
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram


class AcceleratorType(Enum):
    """Accelerator types for resource tracking."""

    NPU = "NPU"
    GPU = "GPU"
    CPU = "CPU"
    REMOTE = "REMOTE"


class TerminationPolicy(Enum):
    """Termination policies for metric labels."""

    IDLE_TIMEOUT = "IDLE_TIMEOUT"
    SESSION_END = "SESSION_END"
    RESOURCE_PRESSURE = "RESOURCE_PRESSURE"
    CRASH = "CRASH"
    MANUAL = "MANUAL"


@dataclass
class MetricsConfig:
    """Configuration for agent metrics.

    Attributes:
        enable_traces: Enable OpenTelemetry tracing
        trace_sample_rate: Trace sampling rate (0.0-1.0)
        cardinality_limit: Max active time series
        histogram_buckets: Latency histogram buckets (ms)
    """

    enable_traces: bool = True
    trace_sample_rate: float = 0.1
    cardinality_limit: int = 10_000
    histogram_buckets: Optional[List[float]] = None

    def __post_init__(self):
        if self.histogram_buckets is None:
            # Standard latency buckets (ms)
            self.histogram_buckets = [1, 5, 10, 25, 50, 100, 250, 500, 1000, 2000]


class AgentMetrics:
    """Prometheus metrics and OpenTelemetry traces for agents.

    Responsibilities:
        - Export 25+ Prometheus metrics
        - Create 4-level OpenTelemetry spans
        - Manage cardinality (<10K time series)
        - Support 3 Grafana dashboards

    Performance: <1ms emission, <5% CPU overhead

    Metrics Exported:
        Creation:
        - agent_creation_total (counter, labels: agent_type, session_id)
        - agent_creation_latency_ms (histogram, labels: agent_type)
        - agent_creation_errors_total (counter, labels: agent_type, error_type)

        Termination:
        - agent_termination_total (counter, labels: agent_type, policy)
        - agent_lifetime_seconds (histogram, labels: agent_type)

        Reuse:
        - agent_reuse_total (counter, labels: agent_type)
        - agent_reuse_latency_ms (histogram, labels: agent_type)
        - agent_pool_hit_rate (gauge, labels: agent_type)

        Performance:
        - agent_execution_latency_ms (histogram, labels: agent_type)
        - agent_ttft_ms (histogram, labels: agent_type)
        - agent_tokens_generated_total (counter, labels: agent_type)

        Resources:
        - agent_memory_allocated_mb (gauge, labels: agent_type, session_id)
        - agent_accelerator_usage (gauge, labels: accelerator_type, slot)
        - agent_resource_reservation_latency_ms (histogram)

        Registry:
        - agent_registry_size (gauge, labels: state)
        - agent_registry_lookup_latency_ms (histogram, labels: index_type)

    Trace Hierarchy:
        1. agent.lifecycle (root span)
           ├─ 2. agent.creation
           │    ├─ 3. factory.create
           │    ├─ 3. resource.reserve
           │    └─ 3. composition.compose
           ├─ 2. agent.execution
           │    ├─ 3. model.inference
           │    ├─ 3. tool.call
           │    └─ 3. memory.access
           └─ 2. agent.termination
                ├─ 3. resource.release
                └─ 3. pool.eviction

    Example:
        metrics = AgentMetrics(config)

        # Track creation
        with metrics.trace_creation("health_specialist", "session_abc") as span:
            agent = factory.create_agent(...)
            metrics.record_creation(
                agent_type="health_specialist",
                session_id="session_abc",
                latency_ms=95,
                memory_mb=128,
                accelerator="NPU"
            )

        # Track reuse
        metrics.record_reuse(
            agent_type="health_specialist",
            latency_ms=8,
            from_pool=True
        )
    """

    def __init__(
        self,
        config: Optional[MetricsConfig] = None,
        registry: Optional[CollectorRegistry] = None,
    ):
        """Initialize agent metrics.

        Args:
            config: Metrics configuration (defaults if None)
            registry: Prometheus registry (default registry if None)
        """
        self.config = config or MetricsConfig()
        self.registry = registry

        # Initialize Prometheus metrics
        self._init_prometheus_metrics()

        # Initialize OpenTelemetry tracer
        if self.config.enable_traces:
            self._tracer: Optional[Tracer] = trace.get_tracer("k1.agent_metrics")
        else:
            self._tracer: Optional[Tracer] = None

    def _init_prometheus_metrics(self) -> None:
        """Initialize all Prometheus metrics."""
        # Creation metrics
        self.creation_total = Counter(
            "agent_creation_total",
            "Total agent creations",
            labelnames=["agent_type", "session_id"],
            registry=self.registry,
        )

        self.creation_latency_ms = Histogram(
            "agent_creation_latency_ms",
            "Agent creation latency in milliseconds",
            labelnames=["agent_type"],
            buckets=self.config.histogram_buckets,
            registry=self.registry,
        )

        self.creation_errors_total = Counter(
            "agent_creation_errors_total",
            "Total agent creation errors",
            labelnames=["agent_type", "error_type"],
            registry=self.registry,
        )

        # Termination metrics
        self.termination_total = Counter(
            "agent_termination_total",
            "Total agent terminations",
            labelnames=["agent_type", "policy"],
            registry=self.registry,
        )

        self.lifetime_seconds = Histogram(
            "agent_lifetime_seconds",
            "Agent lifetime in seconds",
            labelnames=["agent_type"],
            buckets=[1, 5, 10, 30, 60, 300, 600, 1800, 3600],
            registry=self.registry,
        )

        # Reuse metrics
        self.reuse_total = Counter(
            "agent_reuse_total",
            "Total agent reuses from pool",
            labelnames=["agent_type"],
            registry=self.registry,
        )

        self.reuse_latency_ms = Histogram(
            "agent_reuse_latency_ms",
            "Agent reuse latency in milliseconds",
            labelnames=["agent_type"],
            buckets=[1, 5, 10, 25, 50],
            registry=self.registry,
        )

        self.pool_hit_rate = Gauge(
            "agent_pool_hit_rate",
            "Agent pool hit rate (0.0-1.0)",
            labelnames=["agent_type"],
            registry=self.registry,
        )

        # Performance metrics
        self.execution_latency_ms = Histogram(
            "agent_execution_latency_ms",
            "Agent execution latency in milliseconds",
            labelnames=["agent_type"],
            buckets=self.config.histogram_buckets,
            registry=self.registry,
        )

        self.ttft_ms = Histogram(
            "agent_ttft_ms",
            "Agent time-to-first-token in milliseconds",
            labelnames=["agent_type"],
            buckets=[10, 25, 50, 100, 150, 200, 300, 500],
            registry=self.registry,
        )

        self.tokens_generated_total = Counter(
            "agent_tokens_generated_total",
            "Total tokens generated by agents",
            labelnames=["agent_type"],
            registry=self.registry,
        )

        # Resource metrics
        self.memory_allocated_mb = Gauge(
            "agent_memory_allocated_mb",
            "Memory allocated to agents in MB",
            labelnames=["agent_type", "session_id"],
            registry=self.registry,
        )

        self.accelerator_usage = Gauge(
            "agent_accelerator_usage",
            "Accelerator usage by agents",
            labelnames=["accelerator_type", "slot"],
            registry=self.registry,
        )

        self.resource_reservation_latency_ms = Histogram(
            "agent_resource_reservation_latency_ms",
            "Resource reservation latency in milliseconds",
            buckets=[1, 5, 10, 25, 50, 100],
            registry=self.registry,
        )

        # Registry metrics
        self.registry_size = Gauge(
            "agent_registry_size",
            "Number of agents in registry",
            labelnames=["state"],
            registry=self.registry,
        )

        self.registry_lookup_latency_ms = Histogram(
            "agent_registry_lookup_latency_ms",
            "Registry lookup latency in milliseconds",
            labelnames=["index_type"],
            buckets=[0.1, 0.5, 1, 2, 5, 10],
            registry=self.registry,
        )

    def record_creation(
        self,
        agent_type: str,
        session_id: str,
        latency_ms: float,
        memory_mb: int,
        accelerator: str,
    ) -> None:
        """Record agent creation metrics.

        Args:
            agent_type: Type of agent created
            session_id: Session ID
            latency_ms: Creation latency
            memory_mb: Allocated memory
            accelerator: Assigned accelerator
        """
        # TODO: Implement creation recording
        # 1. Increment creation_total
        # 2. Observe creation_latency_ms
        # 3. Set memory_allocated_mb
        # 4. Update accelerator_usage
        raise NotImplementedError("record_creation not yet implemented (M2)")

    def record_termination(
        self, agent_type: str, policy: TerminationPolicy, lifetime_seconds: float
    ) -> None:
        """Record agent termination metrics.

        Args:
            agent_type: Type of agent terminated
            policy: Termination policy
            lifetime_seconds: Agent lifetime
        """
        # TODO: Implement termination recording
        raise NotImplementedError("record_termination not yet implemented (M2)")

    def record_reuse(self, agent_type: str, latency_ms: float, from_pool: bool) -> None:
        """Record agent reuse metrics.

        Args:
            agent_type: Type of agent reused
            latency_ms: Reuse latency
            from_pool: Whether from pool (True) or created (False)
        """
        # TODO: Implement reuse recording
        raise NotImplementedError("record_reuse not yet implemented (M2)")

    def trace_creation(self, agent_type: str, session_id: str) -> Span:
        """Create trace span for agent creation.

        Args:
            agent_type: Agent type
            session_id: Session ID

        Returns:
            OpenTelemetry span (4-level hierarchy)

        Example:
            with metrics.trace_creation("health_specialist", "session_abc") as span:
                # Creation logic here
                span.set_attribute("agent.memory_mb", 128)
        """
        if not self._tracer:
            # TODO: Return no-op span
            raise NotImplementedError("trace_creation not yet implemented (M2)")

        # TODO: Create span hierarchy
        # 1. agent.lifecycle (root)
        # 2. agent.creation (child)
        # 3. factory.create, resource.reserve, composition.compose (grandchildren)
        raise NotImplementedError("trace_creation not yet implemented (M2)")

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get metrics summary for health checks.

        Returns:
            Dict with metric counts and rates
        """
        # TODO: Implement summary
        raise NotImplementedError("get_metrics_summary not yet implemented (M2)")


# TODO: Implement Grafana dashboard JSON
# Dashboard 1: Agent Performance
# - Creation latency over time
# - Reuse rate over time
# - Pool hit rate by type
# - TTFT by agent type
# - Execution latency by type
#
# Dashboard 2: Resource Utilization
# - Memory allocated by type
# - Accelerator usage heatmap
# - Resource reservation latency
# - Memory pressure events
#
# Dashboard 3: Lifecycle Health
# - Active agents by type
# - Terminations by policy
# - Agent lifetime distribution
# - Registry size over time
# - Error rate by type
#
# TODO: Integration
# - Emit metrics from AgentFactory (ADR-0086a)
# - Emit metrics from ResourceReserver (ADR-0086c)
# - Emit metrics from IDLEPoolManager (ADR-0086f)
# - Emit metrics from DynamicAgentRegistry (ADR-0086g)
# - WARD test cases (3 test cases planned)
# - WARD test cases (3 test cases planned)
# - WARD test cases (3 test cases planned)
