"""
k1.planner.stages.commit_service -- CommitService (Epic 3.4).

Stage 4 of the planner pipeline: purely deterministic CommittedPlan
assembly, WAL persistence, plan delivery event emission, and delta
emissions.

PLAN-03 ENFORCEMENT
-------------------
This module does NOT import ILLMPort, IFabricRetrievalPort,
IStateReadPort, ToolCallRouter, or HILCoordinator.  Zero LLM calls
by design -- enforced at constructor level (no llm_port parameter),
at module level (no LLM import), and at test level.

Design
------
- Layer 2 (Section 30.6): imports Layer 1 ports (IBridgePort,
  IDeltaEmitPort, IEventPort), Layer 0 types (ExpandedPlan, PlanRequest,
  CommittedPlan, PlanStep, ValidationVerdict, StageContext, DeltaPayload,
  CommitFailedError), and TOPIC_PLAN_READY from events.py.
- Stateless between calls: no per-plan instance state.
- CommitService does NOT hold a reference to PipelineController.
- PLAN-01: zero writes to SessionState.
- PLAN-03: zero LLM calls, zero tokens consumed.
- PLAN-05: zero tool calls through ToolCallRouter.
- PLAN-06: zero capability executions.

Public interface
----------------
async execute(expanded_plan, request, verdict, ctx) -> CommittedPlan
    Full COMMIT stage: assemble -> persist WAL -> deliver event ->
    emit deltas. Same method for normal plans and micro-replans.

Consumers
---------
PipelineController._run_commit() -- calls execute()

References
----------
- planner.md Section 9 (Stage 4 COMMIT Deep Dive)
- planner.md Section 9.2 (CommittedPlan Assembly)
- planner.md Section 9.3 (K0 WAL Persistence)
- planner.md Section 9.4 (Plan Delivery)
- planner.md Section 9.5 (Delta Emissions)
- planner.md Section 9.6 (ERR_COMMIT_FAIL Recovery)
- planner.md Section 17.6 (CommitService ~30 tests)

Exports
-------
CommitService
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import deque
from typing import Dict, List

from k1.orchestrator.types import CommittedPlan, PlanRequest, PlanStep
from k1.planner.events import TOPIC_PLAN_READY
from k1.planner.ports.bridge_port import IPlannerWritePort
from k1.planner.ports.delta_emit_port import IDeltaEmitPort
from k1.planner.ports.event_port import IEventPort
from k1.planner.types import (
    DELTA_PLAN_END,
    DELTA_STAGE_TRANSITION,
    PLANNER_AGENT_ID,
    SECTION_PIPELINE,
    CommitFailedError,
    DeltaPayload,
    ExpandedPlan,
    StageContext,
    ValidationVerdict,
)

log = logging.getLogger(__name__)


class CommitService:
    """Stage 4 COMMIT: ExpandedPlan + PlanRequest + ValidationVerdict -> CommittedPlan.

    Purely deterministic -- zero LLM calls (PLAN-03).

    11-step assembly sequence (Section 9.2.1):
    1. plan_id = uuid4()
    2. created_at = time.time()
    3. steps = expanded_plan.steps (frozen, no modification)
    4. dependencies = expanded_plan.dependencies (frozen)
    5. estimated_duration_ms = critical path sum of step.timeout_ms
    6. Assemble CommittedPlan
    7. CommittedPlan.__post_init__() defensive validation
    8. Persist WAL (fire-and-forget)
    9. Publish plan.ready.v1 event
    10. Emit stage_transition delta
    11. Emit plan_end delta

    Error recovery (Section 9.6):
    - WAL persist failure -> retry once, proceed anyway
    - Event publish failure -> retry once, on second failure plan is
      completed but undeliverable
    - CommittedPlan validation error -> CommitFailedError (indicates
      VALIDATE bug)

    Invariants
    ----------
    PLAN-01 : Zero writes to SessionState.
    PLAN-03 : Zero LLM calls (no ILLMPort parameter, no LLM import).
    PLAN-05 : Zero tool calls through ToolCallRouter.
    PLAN-06 : Zero capability executions.

    Thread safety
    -------------
    Safe for sequential calls from PipelineController. Not designed
    for concurrent execute() calls on the same instance.
    """

    __slots__ = (
        "_bridge_port",
        "_delta_port",
        "_event_port",
    )

    def __init__(
        self,
        bridge_port: IPlannerWritePort,
        delta_port: IDeltaEmitPort,
        event_port: IEventPort,
    ) -> None:
        """Construct CommitService with injected dependencies.

        PLAN-03 enforcement: there is NO llm_port parameter.  Zero LLM
        calls by design, enforced at interface level.

        Args:
            bridge_port: K0 Bridge access for WAL persistence.
            delta_port: Delta Bus emission for observability.
            event_port: Event Bus for plan delivery event.

        Raises:
            TypeError: If any dependency is None.
        """
        if bridge_port is None:
            raise TypeError("bridge_port must not be None")
        if delta_port is None:
            raise TypeError("delta_port must not be None")
        if event_port is None:
            raise TypeError("event_port must not be None")
        self._bridge_port = bridge_port
        self._delta_port = delta_port
        self._event_port = event_port

    # -- read-only attribute access ----------------------------------------

    @property
    def bridge_port(self) -> IPlannerWritePort:
        """Bridge port (read-only)."""
        return self._bridge_port

    @property
    def delta_port(self) -> IDeltaEmitPort:
        """Delta emit port (read-only)."""
        return self._delta_port

    @property
    def event_port(self) -> IEventPort:
        """Event port (read-only)."""
        return self._event_port

    # ===================================================================
    # Public API
    # ===================================================================

    async def execute(
        self,
        expanded_plan: ExpandedPlan,
        request: PlanRequest,
        verdict: ValidationVerdict,
        ctx: StageContext,
    ) -> CommittedPlan:
        """Full COMMIT stage (Section 9).

        Deterministic assembly -> WAL persist -> event delivery -> deltas.
        Same method for normal plans and micro-replans (Section 10.1.3).

        Args:
            expanded_plan: Output of EXPAND stage (validated by VALIDATE).
            request: Original plan request (correlation source).
            verdict: VALIDATE stage output (approved or best-effort).
            ctx: Runtime stage context (trace_id, budgets, cancel).

        Returns:
            CommittedPlan ready for Orchestrator execution.

        Raises:
            CommitFailedError: If CommittedPlan assembly fails (indicates
                VALIDATE bug -- should never happen on approved plan).
        """
        commit_start = time.monotonic()

        # -- Cancellation check --
        if ctx.cancel_check():
            raise CommitFailedError(
                "Plan cancelled during COMMIT",
                stage="COMMIT",
                request_id=ctx.request_id,
                trace_id=ctx.trace_id,
            )

        # -- Step 1-7: Deterministic assembly --
        committed_plan = self._build_committed_plan(expanded_plan, request)

        # -- Step 8: WAL persist (fire-and-forget) --
        wal_persisted = await self._persist_to_wal(committed_plan, ctx)

        # -- Step 9: Plan delivery event --
        await self._deliver_plan(committed_plan, ctx)

        commit_wall_time_ms = int((time.monotonic() - commit_start) * 1000)

        # -- Step 10: Stage delta --
        self._emit_stage_delta(committed_plan, wal_persisted, commit_wall_time_ms, ctx)

        # -- Step 11: Plan-end delta --
        self._emit_plan_end_delta(committed_plan, commit_wall_time_ms, ctx)

        log.info(
            "commit.completed plan_id=%s request_id=%s duration_ms=%d " "wal_persisted=%s",
            committed_plan.plan_id,
            committed_plan.request_id,
            commit_wall_time_ms,
            wal_persisted,
        )

        return committed_plan

    # ===================================================================
    # Private: Assembly
    # ===================================================================

    def _build_committed_plan(
        self,
        expanded_plan: ExpandedPlan,
        request: PlanRequest,
    ) -> CommittedPlan:
        """Build CommittedPlan from ExpandedPlan + PlanRequest (Section 9.2.1).

        Steps 1-7: plan_id, created_at, steps, dependencies,
        estimated_duration_ms, assemble, validate via __post_init__.

        Args:
            expanded_plan: Validated expanded plan.
            request: Original plan request.

        Returns:
            CommittedPlan (frozen dataclass).

        Raises:
            CommitFailedError: If CommittedPlan.__post_init__ validation
                fails (indicates VALIDATE bug).
        """
        plan_id = str(uuid.uuid4())
        created_at = time.time()

        # Steps and dependencies are already frozen (frozen dataclass
        # steps, immutable dict values). No modification in COMMIT --
        # VALIDATE approved as-is.
        steps = expanded_plan.steps
        dependencies = expanded_plan.dependencies

        # Compute estimated duration via critical path analysis.
        estimated_duration_ms = self._compute_critical_path_duration(
            steps,
            dependencies,
        )

        try:
            committed_plan = CommittedPlan(
                plan_id=plan_id,
                request_id=request.request_id,
                intent=request.intent,
                steps=steps,
                trace_id=request.trace_id,
                dependencies=dependencies,
                estimated_duration_ms=estimated_duration_ms,
                created_at=created_at,
            )
        except (ValueError, TypeError) as exc:
            # CommittedPlan.__post_init__ validation failed.
            # This indicates a VALIDATE bug -- should never happen.
            raise CommitFailedError(
                f"CommittedPlan assembly failed: {exc}",
                stage="COMMIT",
                request_id=request.request_id,
                trace_id=request.trace_id,
            ) from exc

        return committed_plan

    def _compute_critical_path_duration(
        self,
        steps: List[PlanStep],
        dependencies: Dict[str, List[str]],
    ) -> int:
        """Compute estimated duration as longest path through the DAG.

        Uses topological sort (Kahn's algorithm) with dynamic programming
        to find the critical path -- the longest chain of sequential
        step.timeout_ms sums.

        For plans with no dependencies, returns the max single step timeout
        (all steps run in parallel).

        For linear chains, returns sum of all step timeouts.

        Returns:
            Estimated duration in milliseconds.
        """
        step_timeout: Dict[str, int] = {}
        for step in steps:
            step_timeout[step.id] = step.timeout_ms or 0

        step_ids = {s.id for s in steps}

        if not dependencies:
            # No dependencies -- all steps can run in parallel.
            # Critical path is the single longest step.
            return max(step_timeout.values()) if step_timeout else 0

        # Build adjacency list and in-degree for Kahn's algorithm.
        in_degree: Dict[str, int] = {sid: 0 for sid in step_ids}
        adj: Dict[str, List[str]] = {sid: [] for sid in step_ids}

        for step_id, dep_list in dependencies.items():
            for dep in dep_list:
                if dep in step_ids and step_id in step_ids:
                    adj[dep].append(step_id)
                    in_degree[step_id] = in_degree.get(step_id, 0) + 1

        # Dynamic programming: dist[node] = longest path ending at node.
        dist: Dict[str, int] = {sid: step_timeout.get(sid, 0) for sid in step_ids}

        queue: deque[str] = deque()
        for sid in step_ids:
            if in_degree.get(sid, 0) == 0:
                queue.append(sid)

        while queue:
            node = queue.popleft()
            for successor in adj.get(node, []):
                # Longest path to successor = max(existing, path through node).
                candidate = dist[node] + step_timeout.get(successor, 0)
                if candidate > dist[successor]:
                    dist[successor] = candidate
                in_degree[successor] -= 1
                if in_degree[successor] == 0:
                    queue.append(successor)

        return max(dist.values()) if dist else 0

    # ===================================================================
    # Private: WAL Persistence
    # ===================================================================

    async def _persist_to_wal(
        self,
        committed_plan: CommittedPlan,
        ctx: StageContext,
    ) -> bool:
        """Persist committed plan to K0 WAL (Section 9.3).

        Fire-and-forget with retry-once on failure.  WAL failure NEVER
        blocks plan delivery.

        Args:
            committed_plan: The plan to persist.
            ctx: Runtime context for trace_id.

        Returns:
            True if persisted, False on failure.
        """
        for attempt in range(2):  # Try + 1 retry.
            try:
                await self._bridge_port.persist_plan(
                    committed_plan,
                    trace_id=ctx.trace_id,
                )
                log.debug(
                    "commit.wal_persisted plan_id=%s attempt=%d",
                    committed_plan.plan_id,
                    attempt + 1,
                )
                return True
            except Exception:
                if attempt == 0:
                    log.warning(
                        "commit.wal_persist_failed plan_id=%s attempt=1 retrying",
                        committed_plan.plan_id,
                    )
                else:
                    log.error(
                        "commit.wal_persist_failed plan_id=%s attempt=2 " "proceeding_without_wal",
                        committed_plan.plan_id,
                    )

        return False

    # ===================================================================
    # Private: Plan Delivery
    # ===================================================================

    async def _deliver_plan(
        self,
        committed_plan: CommittedPlan,
        ctx: StageContext,
    ) -> None:
        """Deliver plan via IEventPort (Section 9.4).

        Publishes plan.ready.v1 with CommittedPlan.to_dict() payload.
        Retry once on failure.

        Args:
            committed_plan: The plan to deliver.
            ctx: Runtime context for trace_id.
        """
        for attempt in range(2):  # Try + 1 retry.
            try:
                self._event_port.emit(
                    TOPIC_PLAN_READY,
                    committed_plan.to_dict(),
                )
                log.debug(
                    "commit.plan_delivered plan_id=%s attempt=%d",
                    committed_plan.plan_id,
                    attempt + 1,
                )
                return
            except Exception:
                if attempt == 0:
                    log.warning(
                        "commit.plan_delivery_failed plan_id=%s attempt=1 retrying",
                        committed_plan.plan_id,
                    )
                else:
                    log.error(
                        "commit.plan_delivery_failed plan_id=%s attempt=2 " "plan_undeliverable",
                        committed_plan.plan_id,
                    )

    # ===================================================================
    # Private: Delta Emissions
    # ===================================================================

    def _emit_stage_delta(
        self,
        committed_plan: CommittedPlan,
        wal_persisted: bool,
        commit_wall_time_ms: int,
        ctx: StageContext,
    ) -> None:
        """Emit stage_transition delta for COMMIT (Section 9.5).

        Synchronous, fire-and-forget, NEVER raises.
        """
        try:
            self._delta_port.emit(
                DeltaPayload(
                    agent_id=PLANNER_AGENT_ID,
                    delta_type=DELTA_STAGE_TRANSITION,
                    section=SECTION_PIPELINE,
                    data={
                        "stage": "COMMIT",
                        "status": "completed",
                        "plan_id": committed_plan.plan_id,
                        "tokens_used": 0,
                        "tool_calls_used": 0,
                        "duration_ms": commit_wall_time_ms,
                        "wal_persisted": wal_persisted,
                    },
                    trace_id=ctx.trace_id,
                )
            )
        except Exception:
            log.warning(
                "commit.stage_delta_failed plan_id=%s",
                committed_plan.plan_id,
            )

    def _emit_plan_end_delta(
        self,
        committed_plan: CommittedPlan,
        commit_wall_time_ms: int,
        ctx: StageContext,
    ) -> None:
        """Emit plan_end delta summarizing the entire plan (Section 9.5).

        Synchronous, fire-and-forget, NEVER raises.

        Note: total_tokens, total_duration_ms, etc. are collected from
        StageContext by PipelineController and passed here.  In V1,
        CommitService emits with the information available to it.
        PipelineController may emit a more complete plan_end delta
        separately.
        """
        try:
            self._delta_port.emit(
                DeltaPayload(
                    agent_id=PLANNER_AGENT_ID,
                    delta_type=DELTA_PLAN_END,
                    section=SECTION_PIPELINE,
                    data={
                        "plan_id": committed_plan.plan_id,
                        "request_id": committed_plan.request_id,
                        "total_tokens": 0,  # COMMIT stage: 0 tokens.
                        "total_duration_ms": commit_wall_time_ms,
                        "total_tool_calls": 0,
                        "total_hil_rounds": 0,
                        "revise_loops": 0,
                        "stages_completed": [
                            "SKETCH",
                            "EXPAND",
                            "VALIDATE",
                            "COMMIT",
                        ],
                    },
                    trace_id=ctx.trace_id,
                )
            )
        except Exception:
            log.warning(
                "commit.plan_end_delta_failed plan_id=%s",
                committed_plan.plan_id,
            )


__all__ = ["CommitService"]
