"""
P03 QoS integration module.

Provides P03-specific wrappers around K0 QoS infrastructure:
- P03SchedulerIntegration: Token-based resource management
- P03QoSContext: Fanout/top_k budget management
- P03AdaptiveBatchSizer: K0-aware batch size optimization
- P03PhaseMetrics: Phase latency tracking with SLO validation
- P03ThroughputTracker: Throughput SLO tracking
- P03ResourceMetrics: Resource utilization tracking (memory/CPU/DB/vector queries)
- P03QueryMetrics: Database query optimization metrics
- P03LearningBudget: Learning compute budget tracking (<5% cycle time)

Dossier Reference: Section 15 Performance Tuning
K0 Reference: k0/qos/
"""

from __future__ import annotations

from .adaptive_batch_sizer import (
    BATCH_SIZE_PROFILES,
    BatchSizeCategory,
    BatchSizeProfile,
    BatchSizeResult,
    P03AdaptiveBatchSizer,
)
from .context_integration import P03_QOS_DEFAULTS, P03QoSContext, create_p03_qos_context
from .learning_budget import (
    P03_LEARNING_BUDGET_CONFIG,
    LearningBudgetConfig,
    LearningBudgetSummary,
    LearningOperation,
    LearningOperationStats,
    P03LearningBudget,
)
from .phase_metrics import (
    PHASE_LATENCY_TARGETS,
    LatencyTarget,
    P03PhaseMetrics,
    SLOCheckResult,
    SLOComplianceLevel,
)
from .query_metrics import (
    P03_QUERY_THRESHOLDS,
    QUERY_DURATION_BUCKETS,
    P03QueryMetrics,
    QueryStats,
    QuerySummary,
    QueryThresholds,
    QueryType,
)
from .resource_metrics import (
    MEMORY_THRESHOLDS,
    P03_RESOURCE_TARGETS,
    MemoryPressureLevel,
    P03ResourceMetrics,
    ResourceSnapshot,
    ResourceTarget,
)
from .scheduler_integration import (
    P03_SCHEDULER_PROFILES,
    P03SchedulerIntegration,
    P03SchedulerProfile,
)
from .throughput_tracker import (
    P03_THROUGHPUT_TARGETS,
    P03ThroughputTracker,
    ThroughputComplianceLevel,
    ThroughputSnapshot,
    ThroughputTargets,
)

__all__ = [
    # Issue 6.4.1 - Scheduler Integration
    "P03SchedulerIntegration",
    "P03SchedulerProfile",
    "P03_SCHEDULER_PROFILES",
    # Issue 6.4.2 - QoS Context
    "P03QoSContext",
    "P03_QOS_DEFAULTS",
    "create_p03_qos_context",
    # Issue 6.4.3 - Adaptive Batch Sizer
    "P03AdaptiveBatchSizer",
    "BatchSizeCategory",
    "BatchSizeProfile",
    "BatchSizeResult",
    "BATCH_SIZE_PROFILES",
    # Issue 6.4.4 - Phase Metrics
    "P03PhaseMetrics",
    "LatencyTarget",
    "SLOCheckResult",
    "SLOComplianceLevel",
    "PHASE_LATENCY_TARGETS",
    # Issue 6.4.5 - Throughput Tracker
    "P03ThroughputTracker",
    "ThroughputTargets",
    "ThroughputSnapshot",
    "ThroughputComplianceLevel",
    "P03_THROUGHPUT_TARGETS",
    # Issue 6.4.6 - Resource Metrics
    "P03ResourceMetrics",
    "MemoryPressureLevel",
    "ResourceTarget",
    "ResourceSnapshot",
    "P03_RESOURCE_TARGETS",
    "MEMORY_THRESHOLDS",
    # Issue 6.4.7 - Query Metrics
    "P03QueryMetrics",
    "QueryType",
    "QueryThresholds",
    "QueryStats",
    "QuerySummary",
    "P03_QUERY_THRESHOLDS",
    "QUERY_DURATION_BUCKETS",
    # Issue 6.4.8 - Learning Budget
    "P03LearningBudget",
    "LearningOperation",
    "LearningBudgetConfig",
    "LearningOperationStats",
    "LearningBudgetSummary",
    "P03_LEARNING_BUDGET_CONFIG",
]
