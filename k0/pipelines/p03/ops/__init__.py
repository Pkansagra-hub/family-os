"""P03 Operational Integration — Metrics, Tracing, and Observability.

This subpackage provides P03-specific operational integration with K0 kernel
services. It does NOT duplicate kernel functionality — it integrates with it.

Modules:
    metrics: P03 metrics registry (integrates with k0/obs/metrics.py)
    tracing: P03 span hierarchy (integrates with k0/obs/tracing.py)
    context_propagation: Trace context propagation with baggage
    logging: Structured logging schema and context
    phase_logger: Phase-appropriate log levels
    security: Cross-space leakage detection
    formula_tracing: Three-level formula debug tracing
    shadow_comparator: Shadow mode comparison logic
    formula_comparison: Formula version statistical comparison
    module_metrics: Module performance instrumentation
    error_classifier: Error classification for routing (6.2.1)
    error_handler: Central error handler with DLQ integration (6.2.2)
    dlq_store: P03-specific DLQ record format (6.2.3)
    retry_config: Phase-aware retry configuration (6.2.4)
    circuit_breaker: Circuit breaker state machine (6.2.5)
    p08_circuit: P08 embedding circuit breaker (6.2.6)
    bus_circuit: Bus dispatcher circuit breaker (6.2.7)
    faiss_circuit: FAISS index circuit breaker (6.2.8) [REMOVED M4 — pgvector native]
    partial_failure: Partial failure handling strategies (6.2.9)

M6 Reference: docs/TEMP_EXECUTION_DOCS/M6_EXECUTION.md Epic 6.1, 6.2
Dossier Reference: docs/pipelines/P03_consolidation_dossier_v2.md Section 8, 13
"""

from k0.pipelines.p03.ops.alerting import (
    P03_ALERT_THRESHOLDS,
    P03_SLO_TARGETS,
    build_p03_alert_rules,
)
from k0.pipelines.p03.ops.bus_circuit import (
    BusDispatcherCircuitBreaker,
    EmissionResult,
    EventPriority,
    create_bus_circuit_breaker,
)
from k0.pipelines.p03.ops.circuit_breaker import (
    BUS_DISPATCHER_CONFIG,
    P08_EMBEDDING_CONFIG,
    P03CircuitBreaker,
    P03CircuitBreakerConfig,
    P03CircuitBreakerRegistry,
    P03CircuitBreakerState,
    create_p03_circuit_breakers,
)
from k0.pipelines.p03.ops.context_propagation import (
    P03BaggageKeys,
    P03ContextSnapshot,
    P03TraceContextPropagator,
)
from k0.pipelines.p03.ops.dlq_store import P03DLQRecord, P03DLQStore
from k0.pipelines.p03.ops.edge_case_handler import (
    EdgeCaseResult,
    EdgeCaseType,
    HealthCheckResult,
    P03EdgeCaseHandler,
    P03HealthCheck,
    create_edge_case_handler,
    create_health_check,
)
from k0.pipelines.p03.ops.error_classifier import (
    ASYNCPG_FATAL_NAMES,
    ASYNCPG_TRANSIENT_NAMES,
    ASYNCPG_VALIDATION_NAMES,
    ERROR_TYPE_MAPPING,
    FATAL_EXCEPTIONS,
    TRANSIENT_EXCEPTIONS,
    VALIDATION_EXCEPTIONS,
    ErrorClassifier,
    P03ErrorCategory,
)
from k0.pipelines.p03.ops.error_handler import P03ErrorContext, P03ErrorHandler
from k0.pipelines.p03.ops.formula_comparison import FormulaComparator, FormulaComparisonResult
from k0.pipelines.p03.ops.formula_tracing import (
    FormulaTracer,
    NoOpTraceContext,
    TraceContext,
    TraceLevel,
)
from k0.pipelines.p03.ops.logging import P03LogContextManager
from k0.pipelines.p03.ops.metrics import P03MetricsRegistry
from k0.pipelines.p03.ops.module_metrics import (
    ModuleMetricContext,
    emit_clustering_metrics,
    module_metric,
    module_metric_sync,
)
from k0.pipelines.p03.ops.p08_circuit import P08EmbeddingCircuitBreaker, create_p08_circuit_breaker
from k0.pipelines.p03.ops.partial_failure import (
    ORDERING_CRITICAL_PHASES,
    QUARANTINE_THRESHOLD,
    P03BatchResult,
    P03EventResult,
    P03PartialFailureStrategy,
    PartialFailureHandler,
    PartialFailureOutcome,
    create_partial_failure_handler,
)
from k0.pipelines.p03.ops.phase_logger import PhaseLogger
from k0.pipelines.p03.ops.quarantine_metrics import (
    QUARANTINE_ALERT_THRESHOLDS,
    QuarantineMetricsCollector,
    QuarantineMetricsJob,
    QuarantineStats,
    create_quarantine_metrics_collector,
    create_quarantine_metrics_job,
    emit_decision_metric,
    emit_quarantine_metric,
)
from k0.pipelines.p03.ops.retry_config import (
    PHASE_RETRY_OVERRIDES,
    P03RetryConfig,
    P03RetryScheduler,
    create_p03_retry_scheduler,
)
from k0.pipelines.p03.ops.security import CrossSpaceAuditor
from k0.pipelines.p03.ops.shadow_comparator import ShadowModeComparator
from k0.pipelines.p03.ops.tracing import P03ConsolidationTracer

__all__ = [
    # Metrics (6.1.1-6.1.9)
    "P03MetricsRegistry",
    # Module Metrics (6.1.7)
    "module_metric",
    "module_metric_sync",
    "ModuleMetricContext",
    "emit_clustering_metrics",
    # Tracing (6.1.10-6.1.11)
    "P03ConsolidationTracer",
    "P03TraceContextPropagator",
    "P03BaggageKeys",
    "P03ContextSnapshot",
    # Logging (6.1.12-6.1.13)
    "P03LogContextManager",
    "PhaseLogger",
    # Security (6.1.14)
    "CrossSpaceAuditor",
    # Formula tracing (6.1.15)
    "FormulaTracer",
    "TraceLevel",
    "TraceContext",
    "NoOpTraceContext",
    # Formula comparison (6.1.16)
    "FormulaComparator",
    "FormulaComparisonResult",
    # Shadow mode (6.1.8)
    "ShadowModeComparator",
    # Alerting (6.1.18)
    "build_p03_alert_rules",
    "P03_ALERT_THRESHOLDS",
    "P03_SLO_TARGETS",
    # Error Classification (6.2.1)
    "ErrorClassifier",
    "P03ErrorCategory",
    "TRANSIENT_EXCEPTIONS",
    "VALIDATION_EXCEPTIONS",
    "FATAL_EXCEPTIONS",
    "ERROR_TYPE_MAPPING",
    "ASYNCPG_TRANSIENT_NAMES",
    "ASYNCPG_VALIDATION_NAMES",
    "ASYNCPG_FATAL_NAMES",
    # Error Handler (6.2.2)
    "P03ErrorHandler",
    "P03ErrorContext",
    # DLQ Store (6.2.3)
    "P03DLQRecord",
    "P03DLQStore",
    # Retry Config (6.2.4)
    "P03RetryConfig",
    "P03RetryScheduler",
    "create_p03_retry_scheduler",
    "PHASE_RETRY_OVERRIDES",
    # Circuit Breaker (6.2.5)
    "P03CircuitBreaker",
    "P03CircuitBreakerConfig",
    "P03CircuitBreakerState",
    "P03CircuitBreakerRegistry",
    "create_p03_circuit_breakers",
    "P08_EMBEDDING_CONFIG",
    "BUS_DISPATCHER_CONFIG",
    # P08 Embedding Circuit Breaker (6.2.6)
    "P08EmbeddingCircuitBreaker",
    "create_p08_circuit_breaker",
    # Bus Dispatcher Circuit Breaker (6.2.7)
    "BusDispatcherCircuitBreaker",
    "EventPriority",
    "EmissionResult",
    "create_bus_circuit_breaker",
    # FAISS Index Circuit Breaker (6.2.8) — REMOVED M4 (pgvector native)
    # Partial Failure Handling (6.2.9)
    "P03PartialFailureStrategy",
    "P03EventResult",
    "P03BatchResult",
    "PartialFailureHandler",
    "PartialFailureOutcome",
    "create_partial_failure_handler",
    "ORDERING_CRITICAL_PHASES",
    "QUARANTINE_THRESHOLD",
    # Edge Case Handler (6.2.18)
    "EdgeCaseType",
    "EdgeCaseResult",
    "P03EdgeCaseHandler",
    "P03HealthCheck",
    "HealthCheckResult",
    "create_edge_case_handler",
    "create_health_check",
    # Quarantine Metrics (6.2.19)
    "QuarantineMetricsCollector",
    "QuarantineMetricsJob",
    "QuarantineStats",
    "QUARANTINE_ALERT_THRESHOLDS",
    "emit_quarantine_metric",
    "emit_decision_metric",
    "create_quarantine_metrics_collector",
    "create_quarantine_metrics_job",
]
