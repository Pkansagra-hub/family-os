"""
Fabric Metrics - Prometheus Metrics for SLI/SLO Measurement
==========================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/fabric-implementation-plan.md
EPIC: 7.2 Metrics Implementation
ISSUES: 7.2.1, 7.2.2, 7.2.3

This module implements Prometheus metrics for Fabric SLI measurement:
- Latency histograms (execution, retrieval, lookup, context build, policy eval)
- Gauges (registry size, circuit breaker state, agent pool size, active executions)
- Counters (executions, retrievals, registrations, CB trips, agent spawns, retries)

All metrics follow the naming convention: fabric_<metric_name>
Labels align with the implementation plan for consistent observability.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from time import perf_counter
from typing import Iterator, Optional

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

__all__ = [
    "CONTEXT_BUILD_DURATION_BUCKETS",
    "EXECUTION_DURATION_BUCKETS",
    "POLICY_EVALUATION_DURATION_BUCKETS",
    "REGISTRY_LOOKUP_DURATION_BUCKETS",
    "RETRIEVAL_DURATION_BUCKETS",
    "FabricMetrics",
    "get_default_metrics",
]

logger = logging.getLogger(__name__)

# =============================================================================
# BUCKET DEFINITIONS
# =============================================================================

EXECUTION_DURATION_BUCKETS = (
    0.005,
    0.01,
    0.02,
    0.05,
    0.1,
    0.2,
    0.5,
    1.0,
    2.0,
    5.0,
    10.0,
)

RETRIEVAL_DURATION_BUCKETS = (
    0.001,
    0.005,
    0.01,
    0.02,
    0.05,
    0.1,
    0.2,
    0.5,
    1.0,
)

REGISTRY_LOOKUP_DURATION_BUCKETS = (
    0.0001,
    0.0005,
    0.001,
    0.002,
    0.005,
    0.01,
)

CONTEXT_BUILD_DURATION_BUCKETS = (
    0.001,
    0.005,
    0.01,
    0.02,
    0.05,
    0.1,
    0.2,
    0.5,
    1.0,
)

POLICY_EVALUATION_DURATION_BUCKETS = (
    0.0001,
    0.0005,
    0.001,
    0.002,
    0.005,
    0.01,
    0.02,
    0.05,
)


# =============================================================================
# METRICS CLASS
# =============================================================================


class FabricMetrics:
    """
    Prometheus metrics exporter for Fabric SLI/SLO measurement.

    Thread-safe implementation using lazy metric creation with RLock.
    Metrics follow the implementation plan in fabric-implementation-plan.md.
    """

    __slots__ = (
        "_registry",
        "_namespace",
        "_lock",
        # Histograms
        "_execution_duration",
        "_retrieval_duration",
        "_registry_lookup_duration",
        "_context_build_duration",
        "_policy_eval_duration",
        # Counters
        "_executions_total",
        "_retrievals_total",
        "_registrations_total",
        "_cb_trips_total",
        "_agent_spawns_total",
        "_retries_total",
        # Gauges
        "_registry_size",
        "_cb_state",
        "_agent_pool_size",
        "_active_executions",
    )

    def __init__(
        self,
        *,
        namespace: str = "",
        registry: Optional[CollectorRegistry] = None,
    ) -> None:
        self._registry = registry or CollectorRegistry(auto_describe=True)
        self._namespace = namespace
        self._lock = threading.RLock()

        # Histograms
        self._execution_duration: Optional[Histogram] = None
        self._retrieval_duration: Optional[Histogram] = None
        self._registry_lookup_duration: Optional[Histogram] = None
        self._context_build_duration: Optional[Histogram] = None
        self._policy_eval_duration: Optional[Histogram] = None

        # Counters
        self._executions_total: Optional[Counter] = None
        self._retrievals_total: Optional[Counter] = None
        self._registrations_total: Optional[Counter] = None
        self._cb_trips_total: Optional[Counter] = None
        self._agent_spawns_total: Optional[Counter] = None
        self._retries_total: Optional[Counter] = None

        # Gauges
        self._registry_size: Optional[Gauge] = None
        self._cb_state: Optional[Gauge] = None
        self._agent_pool_size: Optional[Gauge] = None
        self._active_executions: Optional[Gauge] = None

    # =====================================================================
    # Histograms (lazy properties)
    # =====================================================================

    @property
    def execution_duration(self) -> Histogram:
        with self._lock:
            if self._execution_duration is None:
                self._execution_duration = Histogram(
                    "fabric_execution_duration_seconds",
                    "Execution duration by capability, provider type, and tier",
                    labelnames=["capability_name", "provider_type", "tier"],
                    buckets=EXECUTION_DURATION_BUCKETS,
                    namespace=self._namespace,
                    registry=self._registry,
                )
            return self._execution_duration

    @property
    def retrieval_duration(self) -> Histogram:
        with self._lock:
            if self._retrieval_duration is None:
                self._retrieval_duration = Histogram(
                    "fabric_retrieval_duration_seconds",
                    "Retrieval duration by query type",
                    labelnames=["query_type"],
                    buckets=RETRIEVAL_DURATION_BUCKETS,
                    namespace=self._namespace,
                    registry=self._registry,
                )
            return self._retrieval_duration

    @property
    def registry_lookup_duration(self) -> Histogram:
        with self._lock:
            if self._registry_lookup_duration is None:
                self._registry_lookup_duration = Histogram(
                    "fabric_registry_lookup_duration_seconds",
                    "Registry lookup duration",
                    buckets=REGISTRY_LOOKUP_DURATION_BUCKETS,
                    namespace=self._namespace,
                    registry=self._registry,
                )
            return self._registry_lookup_duration

    @property
    def context_build_duration(self) -> Histogram:
        with self._lock:
            if self._context_build_duration is None:
                self._context_build_duration = Histogram(
                    "fabric_context_build_duration_seconds",
                    "Context build duration by capability",
                    labelnames=["capability_name"],
                    buckets=CONTEXT_BUILD_DURATION_BUCKETS,
                    namespace=self._namespace,
                    registry=self._registry,
                )
            return self._context_build_duration

    @property
    def policy_evaluation_duration(self) -> Histogram:
        with self._lock:
            if self._policy_eval_duration is None:
                self._policy_eval_duration = Histogram(
                    "fabric_policy_evaluation_duration_seconds",
                    "Policy evaluation duration",
                    buckets=POLICY_EVALUATION_DURATION_BUCKETS,
                    namespace=self._namespace,
                    registry=self._registry,
                )
            return self._policy_eval_duration

    # =====================================================================
    # Counters (lazy properties)
    # =====================================================================

    @property
    def executions_total(self) -> Counter:
        with self._lock:
            if self._executions_total is None:
                self._executions_total = Counter(
                    "fabric_executions_total",
                    "Total executions by result",
                    labelnames=["result"],
                    namespace=self._namespace,
                    registry=self._registry,
                )
            return self._executions_total

    @property
    def retrievals_total(self) -> Counter:
        with self._lock:
            if self._retrievals_total is None:
                self._retrievals_total = Counter(
                    "fabric_retrievals_total",
                    "Total retrieval requests",
                    namespace=self._namespace,
                    registry=self._registry,
                )
            return self._retrievals_total

    @property
    def registrations_total(self) -> Counter:
        with self._lock:
            if self._registrations_total is None:
                self._registrations_total = Counter(
                    "fabric_registrations_total",
                    "Total capability registrations",
                    namespace=self._namespace,
                    registry=self._registry,
                )
            return self._registrations_total

    @property
    def circuit_breaker_trips_total(self) -> Counter:
        with self._lock:
            if self._cb_trips_total is None:
                self._cb_trips_total = Counter(
                    "fabric_circuit_breaker_trips_total",
                    "Total circuit breaker open transitions",
                    labelnames=["provider_id"],
                    namespace=self._namespace,
                    registry=self._registry,
                )
            return self._cb_trips_total

    @property
    def agent_spawns_total(self) -> Counter:
        with self._lock:
            if self._agent_spawns_total is None:
                self._agent_spawns_total = Counter(
                    "fabric_agent_spawns_total",
                    "Total agent spawns",
                    namespace=self._namespace,
                    registry=self._registry,
                )
            return self._agent_spawns_total

    @property
    def retries_total(self) -> Counter:
        with self._lock:
            if self._retries_total is None:
                self._retries_total = Counter(
                    "fabric_retries_total",
                    "Total retries by capability name",
                    labelnames=["capability_name"],
                    namespace=self._namespace,
                    registry=self._registry,
                )
            return self._retries_total

    # =====================================================================
    # Gauges (lazy properties)
    # =====================================================================

    @property
    def registry_size(self) -> Gauge:
        with self._lock:
            if self._registry_size is None:
                self._registry_size = Gauge(
                    "fabric_registry_size",
                    "Registry size by capability type",
                    labelnames=["capability_type"],
                    namespace=self._namespace,
                    registry=self._registry,
                )
            return self._registry_size

    @property
    def circuit_breaker_state(self) -> Gauge:
        with self._lock:
            if self._cb_state is None:
                self._cb_state = Gauge(
                    "fabric_circuit_breaker_state",
                    "Circuit breaker state (1=active state)",
                    labelnames=["provider_id", "state"],
                    namespace=self._namespace,
                    registry=self._registry,
                )
            return self._cb_state

    @property
    def agent_pool_size(self) -> Gauge:
        with self._lock:
            if self._agent_pool_size is None:
                self._agent_pool_size = Gauge(
                    "fabric_agent_pool_size",
                    "Agent pool size by contract",
                    labelnames=["contract_name"],
                    namespace=self._namespace,
                    registry=self._registry,
                )
            return self._agent_pool_size

    @property
    def active_executions(self) -> Gauge:
        with self._lock:
            if self._active_executions is None:
                self._active_executions = Gauge(
                    "fabric_active_executions",
                    "Number of active executions",
                    namespace=self._namespace,
                    registry=self._registry,
                )
            return self._active_executions

    # =====================================================================
    # Histogram observation helpers
    # =====================================================================

    def observe_execution_duration(
        self,
        capability_name: str,
        provider_type: str,
        tier: str,
        duration_seconds: float,
    ) -> None:
        self.execution_duration.labels(
            capability_name=capability_name,
            provider_type=provider_type,
            tier=tier,
        ).observe(duration_seconds)

    def observe_retrieval_duration(self, query_type: str, duration_seconds: float) -> None:
        self.retrieval_duration.labels(query_type=query_type).observe(duration_seconds)

    def observe_registry_lookup(self, duration_seconds: float) -> None:
        self.registry_lookup_duration.observe(duration_seconds)

    def observe_context_build(self, capability_name: str, duration_seconds: float) -> None:
        self.context_build_duration.labels(capability_name=capability_name).observe(
            duration_seconds
        )

    def observe_policy_evaluation(self, duration_seconds: float) -> None:
        self.policy_evaluation_duration.observe(duration_seconds)

    # =====================================================================
    # Context managers for timing
    # =====================================================================

    @contextmanager
    def time_execution(
        self,
        capability_name: str,
        provider_type: str,
        tier: str,
    ) -> Iterator[None]:
        start = perf_counter()
        try:
            yield
        finally:
            self.observe_execution_duration(
                capability_name=capability_name,
                provider_type=provider_type,
                tier=tier,
                duration_seconds=perf_counter() - start,
            )

    @contextmanager
    def time_retrieval(self, query_type: str) -> Iterator[None]:
        start = perf_counter()
        try:
            yield
        finally:
            self.observe_retrieval_duration(query_type, perf_counter() - start)

    @contextmanager
    def time_lookup(self) -> Iterator[None]:
        start = perf_counter()
        try:
            yield
        finally:
            self.observe_registry_lookup(perf_counter() - start)

    @contextmanager
    def time_context_build(self, capability_name: str) -> Iterator[None]:
        start = perf_counter()
        try:
            yield
        finally:
            self.observe_context_build(capability_name, perf_counter() - start)

    @contextmanager
    def time_policy_evaluation(self) -> Iterator[None]:
        start = perf_counter()
        try:
            yield
        finally:
            self.observe_policy_evaluation(perf_counter() - start)

    # =====================================================================
    # Counter helpers
    # =====================================================================

    def inc_executions(self, result: str, count: int = 1) -> None:
        self.executions_total.labels(result=result).inc(count)

    def inc_retrievals(self, count: int = 1) -> None:
        self.retrievals_total.inc(count)

    def inc_registrations(self, count: int = 1) -> None:
        self.registrations_total.inc(count)

    def inc_circuit_breaker_trips(self, provider_id: str, count: int = 1) -> None:
        self.circuit_breaker_trips_total.labels(provider_id=provider_id).inc(count)

    def inc_agent_spawns(self, count: int = 1) -> None:
        self.agent_spawns_total.inc(count)

    def inc_retries(self, capability_name: str, count: int = 1) -> None:
        self.retries_total.labels(capability_name=capability_name).inc(count)

    # =====================================================================
    # Gauge helpers
    # =====================================================================

    def set_registry_size(self, capability_type: str, size: int) -> None:
        self.registry_size.labels(capability_type=capability_type).set(size)

    def set_circuit_breaker_state(self, provider_id: str, state: str, value: int) -> None:
        self.circuit_breaker_state.labels(provider_id=provider_id, state=state).set(value)

    def set_agent_pool_size(self, contract_name: str, size: int) -> None:
        self.agent_pool_size.labels(contract_name=contract_name).set(size)

    def inc_active_executions(self) -> None:
        self.active_executions.inc()

    def dec_active_executions(self) -> None:
        self.active_executions.dec()

    # =====================================================================
    # Export
    # =====================================================================

    def latest(self) -> bytes:
        """Serialize metrics using Prometheus text exposition format."""
        return generate_latest(self._registry)


# =============================================================================
# DEFAULT SINGLETON
# =============================================================================

_default_metrics: Optional[FabricMetrics] = None
_default_lock = threading.Lock()


def get_default_metrics() -> FabricMetrics:
    """
    Get the default FabricMetrics singleton.

    Thread-safe lazy initialization.
    """
    global _default_metrics
    if _default_metrics is None:
        with _default_lock:
            if _default_metrics is None:
                _default_metrics = FabricMetrics()
    return _default_metrics
