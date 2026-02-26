"""
poc.k1_poc.task -- Task dispatch model for Concierge orchestration.

V2 Design Ref: Section 8.2 (TaskDispatch schemas, ComplexityTier)
V2 Design Ref: Section 8.4 (Bundled Intents)
V2 Design Ref: Section 8.5 (Chained Tasks, TaskDependencyQueue)
V2 Design Ref: Section 11.2.1 (ComplexityTier and TaskEnvelope)

This package provides the canonical data structures for task dispatch,
intent specification, complexity classification, intent classification,
envelope bridging, and dependency resolution.

Bus topic family:
    k1.orchestration.task.dispatch.v1   -- Front -> Back
    k1.orchestration.task.complete.v1   -- Back -> Front
    k1.orchestration.task.failed.v1     -- Back -> Front (error path)
    k1.orchestration.task.suspended.v1  -- Back -> Front (HITL path)
    k1.orchestration.task.cancel.v1     -- Front -> Back (cancel)
    k1.orchestration.task.resume.v1     -- Front -> Back (resume after HITL)

Public API:
    ComplexityTier          -- LOW / MEDIUM / HIGH enum
    TIER_BUDGET             -- tier -> max iterations mapping
    budget_for_tier         -- lookup helper

    TaskIntent              -- single intent within a dispatch
    TaskDispatch            -- canonical dispatch payload (Front -> Back)
    TaskComplete            -- completion payload (Back -> Front)
    TaskFailed              -- failure payload (Back -> Front)

    IntentClassification    -- SINGLE / BUNDLED / CHAINED enum
    classify_intents        -- classify intent list
    build_dispatches        -- build dispatch(es) from classified intents

    TaskDependencyQueue     -- chained task queue with $ref hydration

    dispatch_to_envelope    -- TaskDispatch -> bus envelope dict
    complete_to_envelope    -- TaskComplete -> bus envelope dict
    failed_to_envelope      -- TaskFailed -> bus envelope dict

    dispatch_task           -- Front control tool (async)
    DISPATCH_TASK_SCHEMA    -- LLM tool schema for dispatch_task

    TaskReceiver            -- Back actor task dispatch handler

    IntentResult            -- per-intent result within a bundle
    BundledExecutionPlan    -- bundled intent execution tracker

    PARALLEL_SAFE_GROUPS    -- tool groups safe for parallel execution
    ALWAYS_SEQUENTIAL       -- tools that must run one at a time
    is_parallel_safe        -- check if a tool is parallel-safe
    classify_tool_batch     -- split tool batch into parallel/sequential

    TASK_DISPATCH, TASK_COMPLETE, TASK_FAILED, TASK_CANCEL,
    TASK_SUSPENDED, TASK_RESUME, TASK_ACCEPTED, ORCHESTRATION_DELTA,
    DAG_COMPLETED, ALL_TASK_TOPICS  -- topic constants
"""

from poc.k1_poc.task.bundled_executor import BundledExecutionPlan, IntentResult
from poc.k1_poc.task.classifier import IntentClassification, build_dispatches, classify_intents
from poc.k1_poc.task.complexity import TIER_BUDGET, ComplexityTier, budget_for_tier
from poc.k1_poc.task.dependency_queue import TaskDependencyQueue
from poc.k1_poc.task.dispatch import TaskComplete, TaskDispatch, TaskFailed
from poc.k1_poc.task.envelope_bridge import (
    complete_to_envelope,
    dispatch_to_envelope,
    failed_to_envelope,
)
from poc.k1_poc.task.intent import TaskIntent
from poc.k1_poc.task.parallel_safety import (
    ALWAYS_SEQUENTIAL,
    PARALLEL_SAFE_GROUPS,
    classify_tool_batch,
    is_parallel_safe,
)
from poc.k1_poc.task.receiver import TaskReceiver
from poc.k1_poc.task.tools import DISPATCH_TASK_SCHEMA, dispatch_task
from poc.k1_poc.task.topics import (
    ALL_TASK_TOPICS,
    DAG_COMPLETED,
    ORCHESTRATION_DELTA,
    TASK_ACCEPTED,
    TASK_CANCEL,
    TASK_COMPLETE,
    TASK_DISPATCH,
    TASK_FAILED,
    TASK_RESUME,
    TASK_SUSPENDED,
)

__all__ = [
    # Complexity (Epic 10.1)
    "ComplexityTier",
    "TIER_BUDGET",
    "budget_for_tier",
    # Intent (Epic 10.2)
    "TaskIntent",
    # Dispatch payloads (Epic 10.3)
    "TaskDispatch",
    "TaskComplete",
    "TaskFailed",
    # Topics (Epic 10.4)
    "TASK_DISPATCH",
    "TASK_COMPLETE",
    "TASK_FAILED",
    "TASK_CANCEL",
    "TASK_SUSPENDED",
    "TASK_RESUME",
    "TASK_ACCEPTED",
    "ORCHESTRATION_DELTA",
    "DAG_COMPLETED",
    "ALL_TASK_TOPICS",
    # Envelope bridge (Epic 10.4)
    "dispatch_to_envelope",
    "complete_to_envelope",
    "failed_to_envelope",
    # Classifier (Epic 10.5)
    "IntentClassification",
    "classify_intents",
    "build_dispatches",
    # Dependency queue (Epic 10.6)
    "TaskDependencyQueue",
    # dispatch_task tool (Epic 10.7)
    "dispatch_task",
    "DISPATCH_TASK_SCHEMA",
    # TaskReceiver (Epic 10.8)
    "TaskReceiver",
    # Bundled executor (Epic 10.9)
    "IntentResult",
    "BundledExecutionPlan",
    # Parallel safety (Epic 10.14)
    "PARALLEL_SAFE_GROUPS",
    "ALWAYS_SEQUENTIAL",
    "is_parallel_safe",
    "classify_tool_batch",
]
