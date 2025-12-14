"""
DAG Executor - Parallel Wave Execution with Saga Pattern

ADR: 0006c - Parallel DAG Execution
ADR: 0008 - Saga Pattern Error Recovery
Location: docs/architecture/decisions/03-layer2-orchestration/

Implements:
- Issue 6.3.1: DAG Parser & Wave Computation
- Issue 6.3.2: Wave Execution with Barriers
- Issue 6.3.3: Saga Pattern Compensation
"""

from .dag_executor import CompensationResult, DAGExecutor, ExecutionError, StepResult

__all__ = [
    "DAGExecutor",
    "StepResult",
    "CompensationResult",
    "ExecutionError",
]
