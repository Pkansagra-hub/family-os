"""
K0 Scheduler - Pipeline scheduling and trigger management.

This module provides declarative trigger-based pipeline activation
as part of the Capability Mesh Architecture (ADR-K004).

Key Components:
    - TriggerEngine: Base class for trigger implementations
    - PipelineScheduler: Central coordinator for scheduled pipelines
    - TriggerEvent: Event emitted when a trigger fires

Trigger Types (Phase 1):
    - INTERVAL: Fire at fixed time intervals
    - THRESHOLD: Fire when table row count exceeds threshold
    - MANUAL: Fire only on explicit request

Example:
    from k0.scheduler import PipelineScheduler, TriggerEvent

    scheduler = PipelineScheduler(syscalls)
    scheduler.register_pipeline(pipeline_spec)
    await scheduler.start()
"""

from .audit import (
    PipelineRunCompleteEvent,
    PipelineRunStartEvent,
    SchedulerAuditor,
    TriggerFiredEvent,
    TriggerQueuedEvent,
    TriggerSkippedEvent,
    get_scheduler_auditor,
    reset_scheduler_auditor,
)
from .concurrency import (
    OverlapPolicy,
    PendingRun,
    RunStats,
    SingleFlightGate,
    get_single_flight_gate,
    reset_single_flight_gate,
)
from .scheduler import (
    HotReloadResult,
    PipelineExecutor,
    PipelineScheduler,
    PipelineState,
    ScheduledPipeline,
    get_pipeline_scheduler,
    reset_pipeline_scheduler,
    set_pipeline_scheduler,
)
from .triggers import (
    IntervalTriggerEngine,
    ManualTriggerEngine,
    ThresholdTriggerEngine,
    TriggerCallback,
    TriggerEngine,
    TriggerEvent,
    create_trigger_engine,
)

__all__ = [
    # Scheduler
    "PipelineScheduler",
    "ScheduledPipeline",
    "PipelineState",
    "PipelineExecutor",
    "HotReloadResult",
    "get_pipeline_scheduler",
    "set_pipeline_scheduler",
    "reset_pipeline_scheduler",
    # Triggers
    "TriggerEngine",
    "TriggerEvent",
    "TriggerCallback",
    "IntervalTriggerEngine",
    "ThresholdTriggerEngine",
    "ManualTriggerEngine",
    "create_trigger_engine",
    # Concurrency
    "SingleFlightGate",
    "OverlapPolicy",
    "PendingRun",
    "RunStats",
    "get_single_flight_gate",
    "reset_single_flight_gate",
    # Audit
    "SchedulerAuditor",
    "TriggerFiredEvent",
    "TriggerSkippedEvent",
    "TriggerQueuedEvent",
    "PipelineRunStartEvent",
    "PipelineRunCompleteEvent",
    "get_scheduler_auditor",
    "reset_scheduler_auditor",
]
