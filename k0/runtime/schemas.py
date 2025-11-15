"""
Runtime Schema Definitions - Pydantic Models for Declarative DAGs

This module defines the contract schemas for:
- Module contracts (what each module does)
- Pipeline specifications (DAG of module calls)
- Stage specifications (individual DAG nodes)

These schemas are loaded from YAML files in k0/contracts/ and validated at startup.

Related:
- MIGRATION_PLAN.md: Phase 2 - Runtime Layer
- k0/contracts/modules/*.yaml: Module contract files
- k0/contracts/pipelines/*.yaml: Pipeline spec files
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class FailurePolicy(str, Enum):
    """How to handle module failures."""

    DROP = "drop"  # Drop message, log error
    RETRY = "retry"  # Retry with exponential backoff
    DLQ = "dlq"  # Send to dead letter queue


class ModuleContract(BaseModel):
    """
    Contract specification for a reusable module.

    Loaded from k0/contracts/modules/<module_id>.v<version>.yaml

    Example:
        hippocampus.pattern_separate.v1.yaml:
            module_id: hippocampus.pattern_separate
            version: v1
            input_event_types:
              - p02.write.requested.v1
            output_event_types:
              - p02.hippocampus.pattern_separated.v1
            latency_budget_ms: 15
            side_effects:
              - read:st_hipp_store
              - write:st_hipp_store
            idempotent: true
            failure_modes:
              - code: NOVELTY_SCORE_MISSING
                policy: drop
    """

    module_id: str = Field(
        ...,
        description="Unique module identifier (e.g., 'hippocampus.pattern_separate')",
        pattern=r"^[a-z_]+\.[a-z_]+$",
    )

    version: str = Field(
        ...,
        description="Semantic version (e.g., 'v1', 'v2')",
        pattern=r"^v\d+$",
    )

    input_event_types: list[str] = Field(
        default_factory=list,
        description="Event types this module accepts as input",
    )

    output_event_types: list[str] = Field(
        default_factory=list,
        description="Event types this module may emit",
    )

    latency_budget_ms: int = Field(
        ...,
        ge=1,
        le=10000,
        description="P95 latency budget in milliseconds",
    )

    side_effects: list[str] = Field(
        default_factory=list,
        description="Storage operations (e.g., 'read:st_hipp_store', 'write:st_wal')",
    )

    idempotent: bool = Field(
        default=True,
        description="Whether module can be safely retried",
    )

    failure_modes: list[dict[str, str]] = Field(
        default_factory=list,
        description="Known failure codes and handling policies",
    )

    description: str | None = Field(
        default=None,
        description="Human-readable module description",
    )

    @field_validator("side_effects")
    @classmethod
    def validate_side_effects(cls, v: list[str]) -> list[str]:
        """Validate side effect format: operation:resource."""
        for effect in v:
            if ":" not in effect:
                raise ValueError(
                    f"Invalid side effect format: {effect} (expected 'operation:resource')"
                )
            op, resource = effect.split(":", 1)
            if op not in ("read", "write", "emit"):
                raise ValueError(
                    f"Invalid operation in side effect: {op} (expected read/write/emit)"
                )
        return v

    @property
    def full_id(self) -> str:
        """Return fully qualified module ID with version."""
        return f"{self.module_id}:{self.version}"


class StageSpec(BaseModel):
    """
    Specification for a single DAG stage (module invocation).

    Example:
        - id: stage_30_hippocampus
          module: hippocampus.pattern_separate:v1
          after: [stage_20_space]
          config:
            novelty_threshold: 0.7
    """

    id: str = Field(
        ...,
        description="Unique stage identifier within pipeline",
        pattern=r"^[a-z0-9_]+$",
    )

    module: str = Field(
        ...,
        description="Module reference (module_id:version)",
        pattern=r"^[a-z_]+\.[a-z_]+(:[a-z0-9]+)?$",
    )

    after: list[str] = Field(
        default_factory=list,
        description="Stage IDs that must complete before this stage",
    )

    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Stage-specific configuration overrides",
    )

    condition: str | None = Field(
        default=None,
        description="Optional condition to evaluate before running (future)",
    )

    @field_validator("module")
    @classmethod
    def validate_module_ref(cls, v: str) -> str:
        """Add default version if not specified."""
        if ":" not in v:
            return f"{v}:v1"
        return v


class PipelineSpec(BaseModel):
    """
    Declarative pipeline specification (DAG of modules).

    Loaded from k0/contracts/pipelines/<pipeline_id>.v<version>.yaml

    Example:
        p02_write.v1.yaml:
            pipeline_id: P02_WRITE
            version: v1
            entry_topic: cognitive.memory.write.committed.v1
            exit_topic: p02.write.complete.v1
            concurrency: 1
            max_queue: 512
            dag:
              - id: stage_10_affect
                module: affect.analyze:v1
                after: []
              - id: stage_20_space
                module: space.resolve_visibility:v1
                after: [stage_10_affect]
              - id: stage_30_hippocampus
                module: hippocampus.pattern_separate:v1
                after: [stage_20_space]
    """

    pipeline_id: str = Field(
        ...,
        description="Unique pipeline identifier (e.g., 'P02_WRITE')",
        pattern=r"^P[0-9]{2}_[A-Z_]+$",
    )

    version: str = Field(
        ...,
        description="Semantic version (e.g., 'v1', 'v2')",
        pattern=r"^v\d+$",
    )

    entry_topic: str = Field(
        ...,
        description="Event topic that triggers this pipeline",
    )

    exit_topic: str | None = Field(
        default=None,
        description="Event topic emitted on successful completion",
    )

    concurrency: int = Field(
        default=1,
        ge=1,
        le=100,
        description="Max concurrent pipeline executions",
    )

    max_queue: int = Field(
        default=512,
        ge=1,
        le=10000,
        description="Max queued messages before backpressure",
    )

    dag: list[StageSpec] = Field(
        ...,
        min_length=1,
        description="Ordered list of pipeline stages",
    )

    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Pipeline-level configuration",
    )

    description: str | None = Field(
        default=None,
        description="Human-readable pipeline description",
    )

    @field_validator("dag")
    @classmethod
    def validate_dag_structure(cls, v: list[StageSpec]) -> list[StageSpec]:
        """Validate DAG has no cycles and all dependencies exist."""
        stage_ids = {stage.id for stage in v}

        # Check all dependencies exist
        for stage in v:
            for dep in stage.after:
                if dep not in stage_ids:
                    raise ValueError(f"Stage '{stage.id}' depends on non-existent stage '{dep}'")

        # Simple cycle detection (topological sort simulation)
        visited = set()
        visiting = set()

        def visit(stage_id: str, stage_map: dict[str, StageSpec]) -> None:
            if stage_id in visited:
                return
            if stage_id in visiting:
                raise ValueError(f"Cycle detected involving stage '{stage_id}'")

            visiting.add(stage_id)
            stage = stage_map[stage_id]
            for dep in stage.after:
                visit(dep, stage_map)
            visiting.remove(stage_id)
            visited.add(stage_id)

        stage_map = {stage.id: stage for stage in v}
        for stage in v:
            visit(stage.id, stage_map)

        return v

    @property
    def declared_topics(self) -> tuple[str, ...]:
        """Return topics for PipelineProtocol compatibility."""
        return (self.entry_topic,)

    @property
    def required_caps(self) -> tuple[str, ...]:
        """Return required capabilities (computed from modules)."""
        # TODO: Aggregate from module contracts when registry is available
        return ()

    @property
    def contract_version(self) -> int:
        """Return contract version for PipelineProtocol compatibility."""
        return 1

    @classmethod
    def load(cls, path: str | Path) -> "PipelineSpec":
        """Load pipeline specification from YAML file.

        Args:
            path: Path to YAML specification file

        Returns:
            Validated PipelineSpec instance

        Example:
            >>> spec = PipelineSpec.load("k0/contracts/pipelines/p02_write.v1.yaml")
            >>> spec.pipeline_id
            'P02_WRITE'
        """
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(**data)


class PipelineExecutionState(BaseModel):
    """
    Runtime state for a single pipeline execution.

    Tracks progress through DAG stages, intermediate results, and errors.
    """

    pipeline_id: str
    execution_id: str
    trace_id: str | None = None
    offset: int
    envelope: dict[str, Any]  # Initial message payload
    artifacts: dict[str, Any] = Field(default_factory=dict)  # Stage outputs
    completed_stages: set[str] = Field(default_factory=set)
    failed_stages: dict[str, str] = Field(default_factory=dict)  # stage_id -> error
    start_time: float | None = None
    end_time: float | None = None

    class Config:
        """Pydantic config."""

        arbitrary_types_allowed = True


# Type aliases for convenience
ModuleID = str
StageID = str
PipelineID = str
