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
from pydantic import BaseModel, Field, field_validator, model_validator


class FailurePolicy(str, Enum):
    """How to handle module failures."""

    DROP = "drop"  # Drop message, log error
    RETRY = "retry"  # Retry with exponential backoff
    DLQ = "dlq"  # Send to dead letter queue


class FailureMode(BaseModel):
    """
    Specification for a known failure mode and its handling policy.

    Example:
        code: GEO_LOOKUP_FAILED
        policy: retry
        max_retries: 3
    """

    code: str = Field(
        ...,
        description="Unique failure code identifier",
    )

    policy: str = Field(
        ...,
        description="Handling policy (retry, drop, dead_letter, alert)",
    )

    max_retries: int | None = Field(
        default=None,
        description="Maximum number of retry attempts (for retry policy)",
    )

    @field_validator("max_retries", mode="before")
    @classmethod
    def parse_max_retries(cls, v):
        """Parse max_retries from int or string for backward compatibility."""
        if v is None:
            return None
        if isinstance(v, int):
            return v
        # Allow "3" → 3 for backward compatibility
        return int(v)


# -----------------------------------------------------------------------------
# Trigger Types (Issue 1.1.1)
# -----------------------------------------------------------------------------


class TriggerType(str, Enum):
    """Types of pipeline triggers."""

    # Phase 1 trigger types
    INTERVAL = "interval"
    THRESHOLD = "threshold"
    MANUAL = "manual"
    # Phase 2 trigger types (not yet implemented)
    CRON = "cron"
    IDLE = "idle"


class TriggerSpec(BaseModel):
    """
    Specification for a pipeline trigger.

    Examples:
        # Interval trigger (every 5 minutes)
        - id: faiss_indexer_interval
          type: interval
          interval_seconds: 300

        # Threshold trigger (when 50+ records pending)
        - id: faiss_indexer_threshold
          type: threshold
          table: st_vec
          condition: "status = 'READY'"
          threshold_count: 50
    """

    id: str = Field(
        ...,
        description="Unique trigger identifier within pipeline",
        pattern=r"^[a-z0-9_]+$",
    )

    type: TriggerType = Field(
        ...,
        description="Trigger type (cron, interval, threshold, idle, manual)",
    )

    # Interval trigger fields
    interval_seconds: int | None = Field(
        default=None,
        ge=1,
        le=86400,
        description="Interval in seconds (for interval type)",
    )

    # Cron trigger fields
    cron_expression: str | None = Field(
        default=None,
        description="Cron expression (for cron type)",
    )

    # Threshold trigger fields
    table: str | None = Field(
        default=None,
        description="Table to monitor (for threshold type)",
    )

    condition: str | None = Field(
        default=None,
        description="SQL WHERE condition (for threshold type)",
    )

    threshold_count: int | None = Field(
        default=None,
        ge=1,
        description="Threshold count to trigger (for threshold type)",
    )

    check_interval_seconds: int | None = Field(
        default=60,
        ge=1,
        description="How often to check threshold (for threshold type)",
    )

    # Idle trigger fields
    idle_seconds: int | None = Field(
        default=None,
        ge=1,
        description="Idle time before trigger (for idle type)",
    )

    min_pending: int | None = Field(
        default=1,
        ge=1,
        description="Minimum pending items for idle trigger",
    )

    # Common fields
    batch_size: int | None = Field(
        default=None,
        ge=1,
        description="Batch size for triggered processing",
    )

    catch_up_enabled: bool = Field(
        default=True,
        description="Whether to catch up on missed triggers at startup",
    )

    @model_validator(mode="after")
    def validate_trigger_fields(self) -> "TriggerSpec":
        """Validate that required fields are present based on trigger type."""
        if self.type == TriggerType.INTERVAL:
            if not self.interval_seconds:
                raise ValueError("interval_seconds required for interval triggers")
        elif self.type == TriggerType.CRON:
            if not self.cron_expression:
                raise ValueError("cron_expression required for cron triggers")
        elif self.type == TriggerType.THRESHOLD:
            if not self.table:
                raise ValueError("table required for threshold triggers")
            if not self.threshold_count:
                raise ValueError("threshold_count required for threshold triggers")
        elif self.type == TriggerType.IDLE:
            if not self.idle_seconds:
                raise ValueError("idle_seconds required for idle triggers")
        # MANUAL type has no required fields
        return self


# -----------------------------------------------------------------------------
# Capability Provider Types (Issue 1.1.2)
# -----------------------------------------------------------------------------


class ProviderType(str, Enum):
    """Types of capability providers."""

    MODULE = "module"
    PIPELINE = "pipeline"


class FabricContextPolicy(str, Enum):
    """How fabric calls inherit caller context."""

    INHERIT = "inherit"  # Inherit caller's syscalls (capability intersection)
    ISOLATED = "isolated"  # Provider uses its own context only
    SYNTHETIC = "synthetic"  # Fabric creates synthetic context


class CapabilityProvider(BaseModel):
    """
    Configuration for a capability provider.

    Example:
        providers:
          - type: module
            module_id: salience.score:v1
            priority: 1
            condition: always
    """

    type: ProviderType = Field(
        ...,
        description="Provider type (module or pipeline)",
    )

    # Module provider fields
    module_id: str | None = Field(
        default=None,
        description="Module ID (for module providers)",
        pattern=r"^[a-z_]+\.[a-z_]+(:[a-z0-9]+)?$",
    )

    # Pipeline provider fields
    pipeline_id: str | None = Field(
        default=None,
        description="Pipeline ID (for pipeline providers)",
    )

    request_topic: str | None = Field(
        default=None,
        description="Request topic (for pipeline providers)",
    )

    response_topic: str | None = Field(
        default=None,
        description="Response topic (for pipeline providers)",
    )

    # Common fields
    priority: int = Field(
        default=1,
        ge=1,
        le=100,
        description="Provider priority (lower = higher priority)",
    )

    condition: str = Field(
        default="always",
        description="Condition for using this provider",
    )

    latency_budget_ms: int | None = Field(
        default=None,
        ge=1,
        le=10000,
        description="Latency budget for this provider",
    )

    timeout_ms: int | None = Field(
        default=None,
        ge=1,
        le=60000,
        description="Timeout for provider response",
    )

    @model_validator(mode="after")
    def validate_provider_fields(self) -> "CapabilityProvider":
        """Validate that required fields are present based on provider type."""
        if self.type == ProviderType.MODULE:
            if not self.module_id:
                raise ValueError("module_id required for module providers")
        elif self.type == ProviderType.PIPELINE:
            if not self.pipeline_id:
                raise ValueError("pipeline_id required for pipeline providers")
            if not self.request_topic or not self.response_topic:
                raise ValueError("request_topic and response_topic required for pipeline providers")
        return self


class CapabilityDefinition(BaseModel):
    """
    Definition of a capability with its providers.

    Example:
        score_salience:
          description: "Compute salience score"
          providers:
            - type: module
              module_id: salience.score:v1
    """

    description: str = Field(
        ...,
        description="Human-readable capability description",
    )

    providers: list[CapabilityProvider] = Field(
        ...,
        min_length=1,
        description="Ordered list of providers for this capability",
    )

    default_timeout_ms: int = Field(
        default=100,
        ge=1,
        le=60000,
        description="Default timeout for capability requests",
    )


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
                            - read:st_hipp_events
                            - write:st_hipp_events
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
        description="Storage operations (e.g., 'read:st_hipp_events', 'write:st_wal')",
    )

    idempotent: bool = Field(
        default=True,
        description="Whether module can be safely retried",
    )

    failure_modes: list[FailureMode] = Field(
        default_factory=list,
        description="Known failure codes and handling policies",
    )

    description: str | None = Field(
        default=None,
        description="Human-readable module description",
    )

    # Fabric integration fields (Issue 1.1.3)
    fabric_callable: bool = Field(
        default=False,
        description="Whether module can be invoked via CapabilityFabric",
    )

    fabric_capabilities: list[str] = Field(
        default_factory=list,
        description="Capabilities this module provides",
    )

    fabric_context_policy: FabricContextPolicy = Field(
        default=FabricContextPolicy.INHERIT,
        description="How fabric calls inherit caller context",
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

    entry_topic: str | None = Field(
        default=None,
        description="Event topic that triggers this pipeline (None for scheduled pipelines)",
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

    required_capabilities: list[str] = Field(
        default_factory=list,
        description="Required storage capabilities (e.g., st_hipp_events.write)",
    )

    # Trigger configuration (Issue 1.1.4)
    triggers: list[TriggerSpec] = Field(
        default_factory=list,
        description="Declarative triggers for scheduled activation",
    )

    # Fabric actions this pipeline provides
    fabric_actions: list[str] = Field(
        default_factory=list,
        description="Fabric capabilities this pipeline exposes",
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
        """Return required capabilities for PipelineProtocol compatibility."""
        return tuple(self.required_capabilities)

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
