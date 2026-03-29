"""
k1.orchestrator.workflows -- Workflow subsystem package.

Re-exports workflow types and registry for the Orchestrator.

Epic 4.1: Workflow Registry + Compiler
Epic 4.2: Workflow Scheduler + Supervisor + Cross-Workflow

Usage::

    from k1.orchestrator.workflows import (
        WorkflowSpec,
        DynamicExpr,
        WorkflowVersionPointer,
        VersionEntry,
        WorkflowRegistry,
    )
"""

from k1.orchestrator.workflows.cross_workflow_resolver import (
    CrossWorkflowResolver,
    MaxDepthError,
    WorkflowCycleError,
    WorkflowDepthGuard,
)
from k1.orchestrator.workflows.gap_detector import ProactiveGapDetector
from k1.orchestrator.workflows.system_clock import FrozenClock, SystemClock
from k1.orchestrator.workflows.workflow_compiler import WorkflowCompiler
from k1.orchestrator.workflows.workflow_engine import WorkflowEngine
from k1.orchestrator.workflows.workflow_registry import WorkflowRegistry
from k1.orchestrator.workflows.workflow_scheduler import WorkflowScheduler, compute_next_fire
from k1.orchestrator.workflows.workflow_supervisor import (
    StartRunResult,
    WorkflowNotFoundError,
    WorkflowRunSupervisor,
)
from k1.orchestrator.workflows.workflow_types import (
    CompilationResult,
    DynamicExpr,
    RunManifest,
    RunStatus,
    TriggerSpec,
    TriggerType,
    VersionEntry,
    WorkflowSpec,
    WorkflowVersionPointer,
)

__all__ = [
    # Types (4.1.2 + 4.1.4 + 4.2.4)
    "CompilationResult",
    "DynamicExpr",
    "RunManifest",
    "RunStatus",
    "TriggerSpec",
    "TriggerType",
    "VersionEntry",
    "WorkflowSpec",
    "WorkflowVersionPointer",
    # Clock (4.2.2)
    "FrozenClock",
    "SystemClock",
    # Services (4.1.1 + 4.1.3 + 4.2.1)
    "WorkflowCompiler",
    "WorkflowEngine",
    "WorkflowRegistry",
    "WorkflowScheduler",
    "compute_next_fire",
    # Supervisor + Cross-Workflow + Gap (4.2.3 + 4.2.5 + 4.2.6 + 4.2.7)
    "CrossWorkflowResolver",
    "MaxDepthError",
    "ProactiveGapDetector",
    "StartRunResult",
    "WorkflowCycleError",
    "WorkflowDepthGuard",
    "WorkflowNotFoundError",
    "WorkflowRunSupervisor",
]
