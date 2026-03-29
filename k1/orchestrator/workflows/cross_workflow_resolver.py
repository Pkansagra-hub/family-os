"""
k1.orchestrator.workflows.cross_workflow_resolver -- CrossWorkflowResolver + WorkflowDepthGuard (4.2.5 + 4.2.6).

Resolves sub-workflow capability references (``workflow.run.<workflow_id>``)
into CommittedPlans for recursive DAG execution. Includes depth and cycle
guards to prevent unbounded nesting.

Design:
  - StepRunner detects ``workflow.run.*`` capability and delegates to
    CrossWorkflowResolver instead of IFabricGatewayPort.
  - Resolved CommittedPlan is executed recursively by a nested
    ``DAGExecutor.execute()`` call (shares ConcurrencyGuard -- no second lock).
  - Sub-workflow results are wrapped in a single StepResult for the parent DAG.
  - Depth guard (ORCH-08): max 3 levels (root -> sub -> sub-sub).
  - Cycle detection: ancestor_ids propagated through resolution chain.
  - Parameter override (ADR-1.1.11 Q6): merge precedence is
    parent_params > step.params > spec defaults (via step params).

Constructor deps:
  registry   -- WorkflowRegistry (lookup sub-workflow spec)
  compiler   -- WorkflowCompiler (compile sub-workflow)
  depth_guard -- WorkflowDepthGuard (enforce nesting limit)

Anti-hallucination rules:
  - CrossWorkflowResolver does NOT acquire ConcurrencyGuard -- already
    inside DAG execution context.
  - MaxDepthError and WorkflowCycleError are TERMINAL -- non-recoverable.
  - Cycle detection is at resolve time, NOT save time.
  - WorkflowSpec does NOT have default_params() -- defaults come from
    the step's own params (set at workflow save time). Merge uses step.params
    as the base.

Exports:
  CrossWorkflowResolver, WorkflowDepthGuard, MaxDepthError, WorkflowCycleError
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional, Set

from k1.orchestrator.types import CommittedPlan, PlanStep
from k1.orchestrator.workflows.workflow_compiler import WorkflowCompiler
from k1.orchestrator.workflows.workflow_registry import WorkflowRegistry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Capability pattern for sub-workflow references
# ---------------------------------------------------------------------------
_WORKFLOW_RUN_RE = re.compile(r"^workflow\.run\.(.+)$")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class MaxDepthError(Exception):
    """Raised when workflow nesting depth exceeds the configured maximum.

    Non-recoverable (TERMINAL). Subclass of Exception (not AdapterError)
    because it is a domain-level constraint, not an infrastructure error.
    """

    def __init__(self, current_depth: int, max_depth: int) -> None:
        self.current_depth = current_depth
        self.max_depth = max_depth
        super().__init__(f"Workflow nesting depth {current_depth} exceeds max {max_depth}")


class WorkflowCycleError(Exception):
    """Raised when a sub-workflow reference creates a cycle.

    Non-recoverable (TERMINAL). Detected by checking workflow_id
    against ancestor_ids at resolve time.
    """

    def __init__(self, workflow_id: str) -> None:
        self.workflow_id = workflow_id
        super().__init__(
            f"Workflow cycle detected: '{workflow_id}' is already an ancestor "
            f"in the current resolution chain"
        )


# ---------------------------------------------------------------------------
# WorkflowDepthGuard (4.2.6)
# ---------------------------------------------------------------------------


class WorkflowDepthGuard:
    """Enforce maximum workflow nesting depth (ORCH-08).

    Depth tracking:
      Root workflow = depth 1.
      Each sub-workflow increments by 1.
      Max 3 means: root -> sub -> sub-sub (3 levels).

    Methods:
      check(current_depth)             -- raises MaxDepthError if exceeded.
      detect_cycle(workflow_id, ancestors) -- raises WorkflowCycleError if cycle.
    """

    def __init__(self, max_depth: int = 3) -> None:
        if max_depth < 1:
            raise ValueError(f"max_depth must be >= 1, got {max_depth}")
        self._max_depth = max_depth

    @property
    def max_depth(self) -> int:
        """The configured maximum nesting depth."""
        return self._max_depth

    def check(self, current_depth: int) -> None:
        """Raise ``MaxDepthError`` if *current_depth* exceeds the maximum.

        Args:
            current_depth: The depth of the sub-workflow about to be resolved.
                Root workflow is 1, first sub-workflow is 2, etc.

        Raises:
            MaxDepthError: If current_depth > max_depth.
        """
        if current_depth > self._max_depth:
            raise MaxDepthError(current_depth, self._max_depth)

    def detect_cycle(self, workflow_id: str, ancestor_ids: Set[str]) -> None:
        """Raise ``WorkflowCycleError`` if *workflow_id* is an ancestor.

        Args:
            workflow_id: The workflow about to be resolved.
            ancestor_ids: Set of workflow_ids in the current resolution chain.

        Raises:
            WorkflowCycleError: If workflow_id is in ancestor_ids.
        """
        if workflow_id in ancestor_ids:
            raise WorkflowCycleError(workflow_id)


# ---------------------------------------------------------------------------
# CrossWorkflowResolver (4.2.5)
# ---------------------------------------------------------------------------


class CrossWorkflowResolver:
    """Resolve sub-workflow capability references into CommittedPlans (4.2.5).

    A step with capability ``workflow.run.<workflow_id>`` is detected
    and compiled into a sub-CommittedPlan for recursive DAG execution.

    Integration with DAGExecutor:
      StepRunner detects ``workflow.run.*`` capability, delegates to
      ``CrossWorkflowResolver.resolve()`` instead of IFabricGatewayPort.
      The resolved CommittedPlan is executed by a nested
      ``DAGExecutor.execute()`` call.

    Parameter merge precedence (ADR-1.1.11 Q6):
      parent_params[step.id] > step.params > (spec step params as-is)
    """

    def __init__(
        self,
        registry: WorkflowRegistry,
        compiler: WorkflowCompiler,
        depth_guard: WorkflowDepthGuard,
    ) -> None:
        self._registry = registry
        self._compiler = compiler
        self._depth_guard = depth_guard

    @staticmethod
    def is_workflow_step(step: PlanStep) -> bool:
        """Check if a step references a sub-workflow capability.

        Returns True if ``step.capability`` matches ``workflow.run.*``.
        """
        return _WORKFLOW_RUN_RE.match(step.capability) is not None

    @staticmethod
    def extract_workflow_id(capability: str) -> Optional[str]:
        """Extract the workflow_id from a ``workflow.run.<id>`` capability.

        Returns None if the capability does not match the pattern.
        """
        m = _WORKFLOW_RUN_RE.match(capability)
        return m.group(1) if m else None

    async def resolve(
        self,
        step: PlanStep,
        parent_params: Dict[str, Any],
        current_depth: int,
        ancestor_ids: Optional[Set[str]] = None,
    ) -> Optional[CommittedPlan]:
        """Resolve a sub-workflow step into a CommittedPlan.

        Args:
            step: The PlanStep with a ``workflow.run.<id>`` capability.
            parent_params: Parameter overrides keyed by step_id from the parent.
            current_depth: Current nesting depth (root = 1).
            ancestor_ids: Set of workflow_ids in the resolution chain
                (for cycle detection). Defaults to empty set.

        Returns:
            The compiled CommittedPlan for the sub-workflow, or None if:
              - The step is not a workflow reference.
              - The referenced workflow does not exist.
              - Compilation produced gaps (returned as step failure upstream).

        Raises:
            MaxDepthError: If depth exceeds the configured maximum.
            WorkflowCycleError: If a cycle is detected.
        """
        # 1 -- Check capability pattern
        workflow_id = self.extract_workflow_id(step.capability)
        if workflow_id is None:
            return None  # Not a sub-workflow step

        ancestors = ancestor_ids or set()

        # 2 -- Cycle detection
        self._depth_guard.detect_cycle(workflow_id, ancestors)

        # 3 -- Depth check (next level)
        self._depth_guard.check(current_depth + 1)

        # 4 -- Lookup
        spec = await self._registry.get(workflow_id)
        if spec is None:
            logger.warning(
                "CrossWorkflowResolver: workflow '%s' not found " "(referenced by step '%s')",
                workflow_id,
                step.id,
            )
            return None

        if not spec.active:
            logger.warning(
                "CrossWorkflowResolver: workflow '%s' is inactive " "(referenced by step '%s')",
                workflow_id,
                step.id,
            )
            return None

        # 5 -- Parameter merge (ADR-1.1.11 Q6)
        #    base = step.params (set at parent workflow save time)
        #    override = parent_params[step.id] (runtime overrides)
        step_overrides = parent_params.get(step.id, {})
        merged_params = {**step.params, **step_overrides}

        logger.debug(
            "CrossWorkflowResolver: resolving workflow '%s' at depth %d " "(merged %d params)",
            workflow_id,
            current_depth + 1,
            len(merged_params),
        )

        # 6 -- Compile sub-workflow
        compilation = await self._compiler.compile(spec)

        if not compilation.success:
            logger.warning(
                "CrossWorkflowResolver: compilation failed for sub-workflow " "'%s' (%d gaps)",
                workflow_id,
                len(compilation.gaps),
            )
            return None  # Propagated as step failure upstream

        # 7 -- Return compiled plan
        # The compiled_plan's steps already have resolved DynamicExpr values.
        # Parameter merging is handled by the caller (DAGExecutor injects params).
        return compilation.compiled_plan
