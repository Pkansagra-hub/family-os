"""
k1.orchestrator.orchestration.guards -- DAG guard pipeline.

Provides the DAGGuard abstract base class and concrete guard
implementations for the Orchestrator's adaptive DAG execution.

Guard pipeline phases (per Schema Whiteboard Section 8):
  - before_wave:  ConditionalEdgeEvaluator (3.2.2)
  - after_step:   OutputSchemaGuard (3.2.1)
  - after_wave:   MicroReplanCheckpoint (3.2.5), ExecutionMonitor (3.2.6)

Usage:
  Guards are instantiated by OrchestratorFactory (6.2.1 step 12)
  and injected into DAGExecutor as an ordered list.

Types used:
  GuardAction, GuardDecision -- from k1.orchestrator.types (1.2.24)
  ProcessingContext -- carries trace_id, dag_id, tier, merged_results
  Wave, PlanStep, StepResult, WaveResult -- DAG execution types

Exports:
  DAGGuard -- ABC for all DAG guards
  OutputSchemaGuard -- JSON Schema output validation (3.2.1)
  MicroReplanCheckpoint -- Mid-execution micro-replan (3.2.5)
  ExecutionMonitor -- Post-step interrupt + post-wave progress (3.2.6)
  SubStepObserver -- Sub-step observability pass-through (3.2.7)
  ConcurrencyGuard -- Single-DAG-at-a-time gate (3.2.9)
"""

from .base import DAGGuard
from .concurrency_guard import ConcurrencyGuard
from .conditional_eval import ConditionalEdgeEvaluator
from .execution_monitor import ExecutionMonitor, SubStepObserver
from .micro_replan import MicroReplanCheckpoint
from .output_schema_guard import OutputSchemaGuard

__all__ = [
    "ConcurrencyGuard",
    "ConditionalEdgeEvaluator",
    "DAGGuard",
    "ExecutionMonitor",
    "MicroReplanCheckpoint",
    "OutputSchemaGuard",
    "SubStepObserver",
]
