"""
k1.orchestrator.workflows.workflow_types -- Workflow domain types (4.1.2 + 4.1.4).

Frozen dataclasses for the workflow subsystem. These are the data
structures used by WorkflowRegistry, WorkflowCompiler, WorkflowScheduler,
and WorkflowRunSupervisor.

Design decisions:
  - ORCH-002: Hexagonal port/adapter with 8 ports
  - ADR-1.1.9: K1 SQLite LOCAL COLD for persistence

Anti-hallucination rules:
  - WorkflowSpec is FROZEN -- bump_version() creates NEW instance.
  - steps[] uses the 14-field Orchestrator PlanStep (from k1.orchestrator.types),
    NOT Fabric PlanStep.
  - DynamicExpr appears inside PlanStep.params values -- WorkflowCompiler
    resolves before execution.
  - All datetime stored as float (time.time()) NOT ISO string.
  - TriggerSpec and TriggerType live in k1.orchestrator.types -- imported here
    and re-exported for workflow subsystem convenience.
  - Use ``zoneinfo`` (stdlib Python 3.9+), not ``pytz``, for timezone handling.

Import graph:
  - k1.orchestrator.workflows.workflow_types -> k1.orchestrator.types
  - NEVER import from service or port modules (no circular deps)

Exports:
  WorkflowSpec, DynamicExpr, WorkflowVersionPointer, VersionEntry,
  TriggerType (re-export), TriggerSpec (re-export)
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from k1.orchestrator.types import CommittedPlan, PlanStep, ProactiveGap, TriggerSpec, TriggerType

# Re-exports for workflow subsystem convenience
__all__ = [
    "CompilationResult",
    "DynamicExpr",
    "RunManifest",
    "RunStatus",
    "TriggerSpec",
    "TriggerType",
    "VersionEntry",
    "WorkflowSpec",
    "WorkflowVersionPointer",
]

# ---------------------------------------------------------------------------
# Semver pattern for version validation
# ---------------------------------------------------------------------------
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")

# ---------------------------------------------------------------------------
# DynamicExpr (4.1.2) -- ${namespace.field [+/- duration]}
# ---------------------------------------------------------------------------
_DYNEXPR_RE = re.compile(r"\$\{(\w+)\.(\w+)(?:\s*([+-])\s*(\d+[dhms]))?\}")


@dataclass(frozen=True)
class DynamicExpr:
    """Dynamic expression placeholder in PlanStep.params values.

    Syntax: ``${<namespace>.<field> [+/- <duration>]}``

    V1 namespaces:
      - ``date``: today, now
      - ``user``: timezone, locale

    Extensible via resolver registry in WorkflowCompiler.
    """

    raw: str
    namespace: str
    field: str
    offset: Optional[str] = None

    @staticmethod
    def parse(value: str) -> Optional[DynamicExpr]:
        """Parse a string into a DynamicExpr, or return None if plain value.

        Regex: ``\\$\\{(\\w+)\\.(\\w+)(?:\\s*([+-])\\s*(\\d+[dhms]))?\\}``
        """
        if not isinstance(value, str):
            return None
        m = _DYNEXPR_RE.fullmatch(value)
        if m is None:
            return None
        sign = m.group(3) or ""
        duration = m.group(4) or ""
        offset_str = f"{sign}{duration}" if sign else None
        return DynamicExpr(
            raw=value,
            namespace=m.group(1),
            field=m.group(2),
            offset=offset_str,
        )


# ---------------------------------------------------------------------------
# WorkflowSpec (4.1.2) -- frozen, immutable workflow definition
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkflowSpec:
    """Frozen specification of a saved workflow.

    Created from a CommittedPlan + WorkflowSaveRequest. Persisted via
    IWorkflowStoragePort. Compiled at execution time by WorkflowCompiler.

    Validation (``__post_init__``):
      - ``name`` non-empty
      - ``steps`` non-empty
      - ``version`` matches semver pattern (``^\\d+\\.\\d+\\.\\d+$``)
    """

    workflow_id: str
    name: str
    source_plan_id: str
    version: str
    trigger: TriggerSpec
    steps: List[PlanStep] = field(default_factory=list)
    dependencies: Dict[str, List[str]] = field(default_factory=dict)
    active: bool = True
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    created_by: str = "system"

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("WorkflowSpec.name is required")
        if len(self.steps) == 0:
            raise ValueError("WorkflowSpec.steps must be non-empty")
        if not _SEMVER_RE.match(self.version):
            raise ValueError(
                f"WorkflowSpec.version must be semver (e.g. '1.0.0'), " f"got '{self.version}'"
            )


# ---------------------------------------------------------------------------
# VersionEntry + WorkflowVersionPointer (4.1.4) -- version tracking
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VersionEntry:
    """Single entry in the version history of a workflow.

    Recorded each time bump_version() is called.
    """

    version: str
    created_at: float
    source_plan_id: str
    step_count: int
    change_summary: str


@dataclass
class WorkflowVersionPointer:
    """Tracks the active version and full history for a workflow.

    Mutable: ``active_version`` updated on bump, ``version_history``
    appended to.

    Embedded in WorkflowRegistry -- not a separate service.
    """

    workflow_id: str
    active_version: str
    version_history: List[VersionEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# CompilationResult (4.1.3) -- output of WorkflowCompiler.compile()
# ---------------------------------------------------------------------------


@dataclass
class CompilationResult:
    """Result of WorkflowCompiler.compile().

    success=True when all gaps are SMALL/auto-resolved and a
    CommittedPlan was built successfully.

    success=False when any LARGE gap is detected or a required
    capability is missing from the registry.
    """

    success: bool
    compiled_plan: Optional[CommittedPlan] = None
    gaps: List[ProactiveGap] = field(default_factory=list)
    auto_resolved: List[str] = field(default_factory=list)
    compiled_hash: Optional[str] = None


# ---------------------------------------------------------------------------
# RunStatus + RunManifest (4.2.4) -- workflow execution tracking
# ---------------------------------------------------------------------------


class RunStatus(Enum):
    """Status of a workflow run.

    Terminal states: COMPLETED, FAILED, ABORTED.
    No transition from terminal states.

    Transitions:
      RUNNING   -> COMPLETED  (DAG finished successfully)
      RUNNING   -> FAILED     (DAG failed or compilation failed)
      RUNNING   -> ABORTED    (concurrent run policy aborted this run)
    """

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


_TERMINAL_STATUSES = frozenset({RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.ABORTED})


@dataclass(frozen=True)
class RunManifest:
    """Immutable record of a single workflow execution.

    Created by WorkflowRunSupervisor.start_run(). Status transitions
    produce NEW instances (frozen dataclass). Storage adapter handles
    upsert by run_id.

    Fields:
      run_id         -- unique execution identifier
      workflow_id    -- which workflow was executed
      version        -- WorkflowSpec.version at execution time
      compiled_hash  -- SHA-256 of the compiled CommittedPlan (dedup key)
      trigger_type   -- what triggered the run (CRON / EVENT / MANUAL)
      status         -- current RunStatus
      started_at     -- execution start timestamp (float)
      completed_at   -- execution end timestamp (None while RUNNING)
      result_summary -- serialized AggregatedResult summary (on COMPLETED)
      error_message  -- error details (on FAILED)
      steps_completed -- progress counter
      steps_total    -- total steps in the CommittedPlan
    """

    run_id: str
    workflow_id: str
    version: str
    compiled_hash: str
    trigger_type: str
    status: RunStatus
    started_at: float
    completed_at: Optional[float] = None
    result_summary: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    steps_completed: int = 0
    steps_total: int = 0

    # -- Factory -------------------------------------------------------------

    @staticmethod
    def create(
        workflow_id: str,
        version: str,
        compiled_hash: str,
        trigger_type: str,
        total_steps: int,
    ) -> "RunManifest":
        """Create a new RunManifest in RUNNING status.

        Sets run_id to a fresh UUID and started_at to current time.
        """
        return RunManifest(
            run_id=str(uuid.uuid4()),
            workflow_id=workflow_id,
            version=version,
            compiled_hash=compiled_hash,
            trigger_type=trigger_type,
            status=RunStatus.RUNNING,
            started_at=time.time(),
            steps_total=total_steps,
        )

    # -- Status transitions --------------------------------------------------

    def complete(self, result_summary: Optional[Dict[str, Any]] = None) -> "RunManifest":
        """Transition RUNNING -> COMPLETED. Returns new instance.

        Raises:
            ValueError: If current status is terminal.
        """
        self._assert_not_terminal()
        from dataclasses import replace as _replace

        return _replace(
            self,
            status=RunStatus.COMPLETED,
            completed_at=time.time(),
            result_summary=result_summary,
            steps_completed=self.steps_total,
        )

    def fail(self, error: str) -> "RunManifest":
        """Transition RUNNING -> FAILED. Returns new instance.

        Raises:
            ValueError: If current status is terminal.
        """
        self._assert_not_terminal()
        from dataclasses import replace as _replace

        return _replace(
            self,
            status=RunStatus.FAILED,
            completed_at=time.time(),
            error_message=error,
        )

    def abort(self) -> "RunManifest":
        """Transition RUNNING -> ABORTED. Returns new instance.

        Raises:
            ValueError: If current status is terminal.
        """
        self._assert_not_terminal()
        from dataclasses import replace as _replace

        return _replace(
            self,
            status=RunStatus.ABORTED,
            completed_at=time.time(),
        )

    # -- Helpers -------------------------------------------------------------

    def _assert_not_terminal(self) -> None:
        """Raise if current status is terminal (COMPLETED/FAILED/ABORTED)."""
        if self.status in _TERMINAL_STATUSES:
            raise ValueError(f"Cannot transition from terminal status {self.status.value}")
