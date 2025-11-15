"""
Runtime Layer - Declarative Pipeline Infrastructure

Provides runtime support for declarative YAML-based pipelines:
- Schema validation (Pydantic models)
- Module registry (contract loading + lazy imports)
- DAG builder (topological sort + cycle detection)
- Generic pipeline runner (PipelineProtocol implementation)

Usage:
    >>> from k0.runtime import ModuleRegistry, PipelineRunner, PipelineSpec
    >>>
    >>> # Load module contracts
    >>> registry = ModuleRegistry()
    >>> await registry.load_contracts("k0/contracts/modules")
    >>>
    >>> # Create pipeline from YAML spec
    >>> spec = PipelineSpec.load("k0/contracts/pipelines/p02_write.v1.yaml")
    >>> runner = PipelineRunner(spec, registry)
    >>>
    >>> # Initialize and run
    >>> await runner.on_startup(context)
    >>> await runner.handle(bus_message)

Related:
- k0/pipelines/MIGRATION_PLAN.md: Phase 2 - Runtime Layer
- k0/pipelines/protocol.py: PipelineProtocol interface
- k0/contracts/modules/: Module contract YAML files
- k0/contracts/pipelines/: Pipeline specification YAML files
"""

from .dag_builder import DAG, DAGCycleError, DAGValidationError, build_dag
from .module_registry import ModuleCallable, ModuleRegistry
from .pipeline_runner import PipelineRunner, create_pipeline_runner
from .schemas import (
    ModuleContract,
    ModuleID,
    PipelineExecutionState,
    PipelineSpec,
    StageID,
    StageSpec,
)

__all__ = [
    # Schemas
    "ModuleContract",
    "PipelineSpec",
    "StageSpec",
    "PipelineExecutionState",
    "ModuleID",
    "StageID",
    "ModuleCallable",
    # Module Registry
    "ModuleRegistry",
    # DAG Builder
    "DAG",
    "build_dag",
    "DAGCycleError",
    "DAGValidationError",
    # Pipeline Runner
    "PipelineRunner",
    "create_pipeline_runner",
]
