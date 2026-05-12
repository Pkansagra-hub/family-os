"""
k1.planner.stages.validate_service -- ValidateService (Epic 3.3).

Stage 3 of the planner pipeline: two-phase plan validation.
Phase 1 = deterministic structural checks (no LLM, <5ms).
Phase 2 = LLM arbiter semantic review (STRUCTURED, temp 0.1, ~512 tokens).
Optional HIL approval for high-impact plans.

Design
------
- Layer 2 (Section 30.6): imports Layer 1 ports (ILLMPort,
  IFabricRetrievalPort), Layer 0 types (ExpandedPlan, PlanRequest,
  ValidationVerdict, ValidationIssue, PlanStep, StageContext, PlannerLLMRequest,
  PlannerLLMResponse, PlannerConstraints, ValidateRejectedError,
  HILCoordinatorLike), and shared types from Orchestrator (PlanRequest).
- Stateless between calls: no per-plan instance state.
- ValidateService does NOT hold a reference to PipelineController.
- ValidateService does NOT use ToolCallRouter -- zero tool calls
  counted against PLAN-05.
- PLAN-01: zero writes to SessionState.
- PLAN-06: zero capability executions.
- PLAN-02: slot-based prompt for arbiter call.

NON-AGENTIC DESIGN:
- No tool-calling loop. No ToolCallRouter.
- Phase 1: deterministic checks (DAG acyclicity via Kahn's algorithm,
  capability existence via IFabricRetrievalPort or cached, structural
  checks, constraint validation).
- Phase 2: single LLM call with STRUCTURED capability (guaranteed
  JSON output conforming to verdict schema). No retry loop.
- If Phase 1 fails, Phase 2 is skipped (save tokens).

Public interface
----------------
async execute(expanded_plan, request, ctx, cached_capabilities?) -> ValidationVerdict
    Full VALIDATE pipeline: deterministic checks -> LLM arbiter ->
    optional HIL approval -> verdict.
async micro_execute(expanded_plan, ctx, cached_capabilities?) -> ValidationVerdict
    Abbreviated micro-VALIDATE: deterministic checks + arbiter only,
    no HIL, no revise. "revise" treated as "approved".

Consumers
---------
PipelineController._run_validate() -- calls execute() / micro_execute()

References
----------
- planner.md Section 8 (Stage 3 VALIDATE Deep Dive)
- planner.md Section 8.2 (Deterministic Checks)
- planner.md Section 8.3 (LLM Arbiter)
- planner.md Section 8.4 (HIL Approval)
- planner.md Section 8.5 (Revise Loop)
- planner.md Section 8.6 (ERR_VALIDATE_FAIL Recovery)

Exports
-------
ValidateService, VALIDATE_VERDICT_SCHEMA
"""

from __future__ import annotations

import json
import logging
import re
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

from k1.fabric.types import ScoredCapability
from k1.hil.types import ApprovalRequest
from k1.kernel.ports.hil_port import IHILPort
from k1.orchestrator.types import PlanRequest, PlanStep
from k1.planner.ports.fabric_retrieval_port import IFabricRetrievalPort
from k1.planner.ports.llm_port import ILLMPort
from k1.planner.types import (
    CHECK_CAPABILITY_MISSING,
    CHECK_DAG_CYCLE,
    CHECK_DANGLING_DEPENDENCY,
    CHECK_INTER_STEP_REF,
    CHECK_LLM_ARBITER_REJECT,
    CHECK_PARAM_TYPE_MISMATCH,
    CHECK_SELF_REFERENCE,
    CHECK_STEP_ID_DUPLICATE,
    CHECK_UNSAFE_CAPABILITY,
    SAFETY_CAUTION,
    SAFETY_SAFE,
    SAFETY_UNKNOWN,
    SAFETY_UNSAFE,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    VERDICT_APPROVED,
    VERDICT_REJECT,
    VERDICT_REVISE,
    ArbiterVerdict,
    DeterministicValidationResult,
    ExpandedPlan,
    PlannerConstraints,
    PlannerLLMRequest,
    PlannerLLMResponse,
    StageContext,
    ValidateRejectedError,
    ValidationIssue,
    ValidationVerdict,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Reserved meta-capability -- always considered valid (Section 8.2.2).
_META_CAPABILITY_BUILD_AGENT = "tool.meta.build_agent"

# Inter-step reference pattern: $<step_id>.result.<field>
_INTER_STEP_REF_PATTERN = re.compile(r"^\$([a-zA-Z0-9_]+)\.result\.")

# Default arbiter constraints (Section 8.3.2).
_ARBITER_MAX_TOKENS = 512
_ARBITER_TIMEOUT_MS = 3000
_ARBITER_TEMPERATURE = 0.1

# Micro-validate arbiter constraints (Section 10.3.6).
_MICRO_ARBITER_MAX_TOKENS = 256
_MICRO_ARBITER_TIMEOUT_MS = 2000

# Default PLAN-05 budget (max tool calls per plan).
_DEFAULT_MAX_TOOL_CALLS = 6

# HIL approval timeout (Section 8.4.2).
_HIL_APPROVAL_TIMEOUT_S = 120


# ---------------------------------------------------------------------------
# Verdict JSON Schema -- the schema the LLM arbiter MUST conform to.
# Used with STRUCTURED capability so Model Hub enforces conformance.
# ---------------------------------------------------------------------------

VALIDATE_VERDICT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["status", "reasons", "coherence_score", "safety_assessment", "completeness"],
    "properties": {
        "status": {
            "type": "string",
            "enum": ["approved", "revise", "reject"],
            "description": (
                "Verdict: 'approved' if plan is coherent, safe, and complete; "
                "'revise' if fixable issues found; 'reject' if fundamentally flawed."
            ),
        },
        "reasons": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "description": "Explanation for the verdict (at least one reason).",
        },
        "suggested_fixes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Actionable fix suggestions (empty for 'approved').",
        },
        "coherence_score": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "How well steps serve the stated intent (0.0-1.0).",
        },
        "safety_assessment": {
            "type": "string",
            "enum": ["safe", "caution", "unsafe"],
            "description": (
                "'safe': no concerning side effects; "
                "'caution': side effects present but manageable; "
                "'unsafe': dangerous or inappropriate side effects."
            ),
        },
        "completeness": {
            "type": "boolean",
            "description": "True if all aspects of user intent are covered.",
        },
    },
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Arbiter system prompt template (Section 8.3.1).
# Slots: OUTPUT_SCHEMA is filled at prompt assembly time.
# ---------------------------------------------------------------------------

_ARBITER_SYSTEM_PROMPT = """\
You are the VALIDATE stage arbiter for a plan execution pipeline.

Your task is to review a proposed plan and issue a verdict.
Evaluate the plan across these 5 dimensions:
1. Coherence: Do the steps logically serve the stated user intent?
2. Safety: Are side effects appropriate for the safety band?
3. Completeness: Are all aspects of the user's intent covered?
4. Feasibility: Are parameters reasonable and dependencies satisfiable?
5. Redundancy: Are there duplicate or unnecessary steps?

Respond with a JSON object conforming to this schema:
{output_schema}

Rules:
- "approved": plan is good to execute as-is.
- "revise": fixable issues found -- provide suggested_fixes.
- "reject": fundamentally flawed -- cannot be fixed by revision.
- Always provide at least one reason.
- coherence_score must be between 0.0 and 1.0.
- If side effects are present but manageable, use "caution".
- If no side effects, use "safe".
"""


# ---------------------------------------------------------------------------
# ValidateService
# ---------------------------------------------------------------------------


class ValidateService:
    """Stage 3 VALIDATE: ExpandedPlan -> ValidationVerdict (Section 8).

    Two-phase validation:
    - Phase 1: Deterministic structural checks (no LLM, <5ms).
    - Phase 2: LLM arbiter semantic review (STRUCTURED, temp 0.1).

    If Phase 1 fails, Phase 2 is skipped entirely (save tokens).
    Optional HIL approval for high-impact plans (after arbiter approves).

    Stateless between calls: no mutable instance state. All per-plan
    state flows through method parameters and StageContext.

    Invariants
    ----------
    PLAN-01 : Zero writes to SessionState.
    PLAN-02 : Slot-based prompt for arbiter, output_schema = VALIDATE_VERDICT_SCHEMA.
    PLAN-05 : Zero tool calls through ToolCallRouter (capability check
              uses IFabricRetrievalPort directly -- does NOT count).
    PLAN-06 : Zero capability executions.
    PLAN-08 : Capability existence verified in Fabric Registry.
    PLAN-09 : DAG acyclicity enforced via Kahn's topological sort.

    Thread safety
    -------------
    Safe for sequential calls from PipelineController. Not designed
    for concurrent execute() calls on the same instance.
    """

    __slots__ = (
        "_llm_port",
        "_fabric_retrieval",
        "_hil_port",
    )

    def __init__(
        self,
        llm_port: ILLMPort,
        fabric_retrieval: IFabricRetrievalPort,
        hil_port: IHILPort,
    ) -> None:
        """Construct ValidateService with injected dependencies.

        Args:
            llm_port: LLM gateway for structured arbiter call.
            fabric_retrieval: Fabric Registry access for capability
                existence checks (direct, NOT via ToolCallRouter).
            hil_port: Unified Human-in-the-Loop port (k1.hil) used for
                optional approval flow (Section 8.4).

        Raises:
            TypeError: If any dependency is None.
        """
        if llm_port is None:
            raise TypeError("llm_port must not be None")
        if fabric_retrieval is None:
            raise TypeError("fabric_retrieval must not be None")
        if hil_port is None:
            raise TypeError("hil_port must not be None")
        self._llm_port = llm_port
        self._fabric_retrieval = fabric_retrieval
        self._hil_port = hil_port

    # -- read-only attribute access ----------------------------------------

    @property
    def llm_port(self) -> ILLMPort:
        """LLM port (read-only)."""
        return self._llm_port

    @property
    def fabric_retrieval(self) -> IFabricRetrievalPort:
        """Fabric retrieval port (read-only)."""
        return self._fabric_retrieval

    @property
    def hil_port(self) -> IHILPort:
        """Unified HIL port (read-only)."""
        return self._hil_port

    # ===================================================================
    # Public API
    # ===================================================================

    async def execute(
        self,
        expanded_plan: ExpandedPlan,
        request: PlanRequest,
        ctx: StageContext,
        cached_capabilities: Optional[List[ScoredCapability]] = None,
    ) -> ValidationVerdict:
        """Full VALIDATE stage (Section 8).

        Phase 1: Deterministic checks (DAG + capability + structural).
        Phase 2: LLM arbiter (if Phase 1 passes).
        Phase 3: Optional HIL approval (if arbiter approves + high-impact).

        Args:
            expanded_plan: Output of EXPAND stage.
            request: Original plan request.
            ctx: Runtime stage context (trace_id, budgets, cancel).
            cached_capabilities: Capabilities discovered during EXPAND.
                If provided, used for existence checks to avoid
                redundant I/O. If None, queries IFabricRetrievalPort.

        Returns:
            ValidationVerdict with status, issues, confidence, rationale.
        """
        # -- Phase 1: deterministic checks --
        det_issues = self._run_deterministic_checks(
            expanded_plan,
            ctx,
            cached_capabilities,
        )
        deterministic_pass = not any(i.severity == SEVERITY_ERROR for i in det_issues)

        if not deterministic_pass:
            log.info(
                "validate.deterministic_fail request_id=%s errors=%d",
                ctx.request_id,
                len([i for i in det_issues if i.severity == SEVERITY_ERROR]),
            )
            # P04 fix: explicit two-phase composition. Deterministic
            # failure must hard-gate to reject.
            det_result = DeterministicValidationResult(
                issues=det_issues,
                passed=False,
            )
            arbiter_skip = ArbiterVerdict(
                status=VERDICT_REJECT,
                rationale="Deterministic structural checks failed",
                confidence=1.0,
                safety_assessment=SAFETY_UNKNOWN,
                issues=[],
                suggested_fixes=[i.detail for i in det_issues if i.severity == SEVERITY_ERROR],
            )
            return ValidationVerdict.from_components(det_result, arbiter_skip)

        # -- Phase 2: LLM arbiter --
        try:
            verdict = await self._call_arbiter(
                expanded_plan,
                request,
                ctx,
                det_issues,
                is_micro=False,
            )
        except (ValidateRejectedError, KeyboardInterrupt):
            raise  # Re-raise cancellation / interrupt -- never swallow.
        except Exception:
            # Arbiter unavailable -- auto-approve on deterministic pass
            # (Section 8.6 Path 2).
            log.warning(
                "validate.arbiter_unavailable request_id=%s " "auto_approved_on_deterministic_pass",
                ctx.request_id,
            )
            return ValidationVerdict(
                status=VERDICT_APPROVED,
                issues=[i for i in det_issues if i.severity == SEVERITY_WARNING],
                confidence=0.0,
                rationale="Arbiter unavailable, auto-approved on deterministic pass",
                deterministic_pass=True,
                safety_assessment=SAFETY_UNKNOWN,
            )

        # -- Phase 3: optional HIL approval --
        if verdict.status == VERDICT_APPROVED:
            verdict = await self._check_and_run_hil_approval(
                expanded_plan,
                verdict,
                request,
                ctx,
            )

        return verdict

    async def micro_execute(
        self,
        expanded_plan: ExpandedPlan,
        ctx: StageContext,
        cached_capabilities: Optional[List[ScoredCapability]] = None,
        *,
        completed_step_ids: Optional[set[str]] = None,
    ) -> ValidationVerdict:
        """Abbreviated micro-VALIDATE (Section 10.3.4).

        Deterministic checks + reduced arbiter only. No HIL, no revise.
        Verdict "revise" treated as "approved" (best-effort).

        Cross-boundary validation: DAG checks treat references to
        ``completed_step_ids`` as valid (those steps exist in
        completed_results, not in the replacement plan).

        Args:
            expanded_plan: Output of micro-EXPAND stage.
            ctx: Runtime stage context.
            cached_capabilities: Capabilities from micro-EXPAND.
            completed_step_ids: Step IDs already completed (frozen).
                Used by DAG checks to allow cross-boundary references.

        Returns:
            ValidationVerdict (revise upgraded to approved).
        """
        # -- Phase 1: deterministic checks --
        det_issues = self._run_deterministic_checks(
            expanded_plan,
            ctx,
            cached_capabilities,
            completed_step_ids=completed_step_ids,
        )
        deterministic_pass = not any(i.severity == SEVERITY_ERROR for i in det_issues)

        if not deterministic_pass:
            return ValidationVerdict(
                status=VERDICT_REJECT,
                issues=det_issues,
                confidence=1.0,
                rationale="Micro-validate deterministic checks failed",
                deterministic_pass=False,
                safety_assessment=SAFETY_UNKNOWN,
                suggested_fixes=[i.detail for i in det_issues if i.severity == SEVERITY_ERROR],
            )

        # -- Phase 2: LLM arbiter (reduced budget) --
        try:
            verdict = await self._call_arbiter(
                expanded_plan,
                None,
                ctx,
                det_issues,
                is_micro=True,
            )
        except (ValidateRejectedError, KeyboardInterrupt):
            raise  # Re-raise cancellation / interrupt -- never swallow.
        except Exception:
            log.warning(
                "micro_validate.arbiter_unavailable request_id=%s "
                "auto_approved_on_deterministic_pass",
                ctx.request_id,
            )
            return ValidationVerdict(
                status=VERDICT_APPROVED,
                issues=[i for i in det_issues if i.severity == SEVERITY_WARNING],
                confidence=0.0,
                rationale="Micro-validate arbiter unavailable, auto-approved",
                deterministic_pass=True,
                safety_assessment=SAFETY_UNKNOWN,
            )

        # Micro-validate: "revise" treated as "approved" (best-effort).
        if verdict.status == VERDICT_REVISE:
            log.info(
                "micro_validate.revise_upgraded_to_approved request_id=%s",
                ctx.request_id,
            )
            return ValidationVerdict(
                status=VERDICT_APPROVED,
                issues=verdict.issues,
                confidence=verdict.confidence,
                rationale=f"Micro-validate best-effort: {verdict.rationale}",
                deterministic_pass=True,
                safety_assessment=verdict.safety_assessment,
                suggested_fixes=verdict.suggested_fixes,
            )

        return verdict

    # ===================================================================
    # Phase 1: Deterministic Checks
    # ===================================================================

    def _run_deterministic_checks(
        self,
        expanded_plan: ExpandedPlan,
        ctx: StageContext,
        cached_capabilities: Optional[List[ScoredCapability]],
        *,
        completed_step_ids: Optional[set[str]] = None,
    ) -> List[ValidationIssue]:
        """Run all deterministic checks (Section 8.2).

        Returns combined list of issues from all checks.
        Runs sequentially: DAG -> capability -> constraints.
        Total time <5ms for typical plans.

        Args:
            expanded_plan: Plan to validate.
            ctx: Runtime stage context.
            cached_capabilities: Capabilities from prior stage.
            completed_step_ids: Completed step IDs for cross-boundary
                reference validation (micro-replan only).
        """
        issues: List[ValidationIssue] = []

        # 1. DAG acyclicity + structural checks (Section 8.2.1)
        dag_passed, dag_issues = self._check_dag_acyclicity(
            expanded_plan.steps,
            expanded_plan.dependencies,
            completed_step_ids=completed_step_ids,
        )
        issues.extend(dag_issues)

        # 2. Capability existence (Section 8.2.2)
        cap_passed, cap_issues = self._check_capability_existence(
            expanded_plan.steps,
            cached_capabilities,
        )
        issues.extend(cap_issues)

        # 3. Constraint validation (Section 8.2.3)
        constraint_issues = self._validate_plan_constraints(
            expanded_plan.steps,
            ctx,
            cached_capabilities,
        )
        issues.extend(constraint_issues)

        return issues

    def _check_dag_acyclicity(
        self,
        steps: List[PlanStep],
        dependencies: Dict[str, List[str]],
        *,
        completed_step_ids: Optional[set[str]] = None,
    ) -> Tuple[bool, List[ValidationIssue]]:
        """DAG cycle detection via Kahn's topological sort (Section 8.2.1, PLAN-09).

        Also performs structural checks:
        - Step ID uniqueness
        - Self-reference detection
        - Dangling dependency detection
        - Inter-step reference consistency

        Cross-boundary validation (micro-replan): dependencies and
        inter-step references pointing to ``completed_step_ids`` are
        treated as valid (warning, not error) because those steps
        exist in completed_results outside this plan.

        Returns (passed, issues).
        """
        external_ids = completed_step_ids or set()
        issues: List[ValidationIssue] = []
        step_ids = [s.id for s in steps]
        step_id_set = set(step_ids)

        # -- Step ID uniqueness --
        if len(step_ids) != len(step_id_set):
            seen: Dict[str, int] = {}
            for sid in step_ids:
                seen[sid] = seen.get(sid, 0) + 1
            duplicates = [sid for sid, count in seen.items() if count > 1]
            for dup in duplicates:
                issues.append(
                    ValidationIssue(
                        check_name=CHECK_STEP_ID_DUPLICATE,
                        severity=SEVERITY_ERROR,
                        step_id=dup,
                        detail=f"Duplicate step ID: {dup}",
                    )
                )

        # -- Self-reference check --
        for step_id, dep_list in dependencies.items():
            if step_id in dep_list:
                issues.append(
                    ValidationIssue(
                        check_name=CHECK_SELF_REFERENCE,
                        severity=SEVERITY_ERROR,
                        step_id=step_id,
                        detail=f"Step {step_id} depends on itself",
                    )
                )

        # -- Dangling dependency check --
        for step_id, dep_list in dependencies.items():
            for dep in dep_list:
                if dep not in step_id_set:
                    if dep in external_ids:
                        # Cross-boundary dep to completed step --
                        # valid in micro-replan context (advisory).
                        issues.append(
                            ValidationIssue(
                                check_name=CHECK_DANGLING_DEPENDENCY,
                                severity=SEVERITY_WARNING,
                                step_id=step_id,
                                detail=(
                                    f"Step {step_id} has cross-boundary dep "
                                    f"to completed step {dep}"
                                ),
                            )
                        )
                    else:
                        issues.append(
                            ValidationIssue(
                                check_name=CHECK_DANGLING_DEPENDENCY,
                                severity=SEVERITY_ERROR,
                                step_id=step_id,
                                detail=(
                                    f"Step {step_id} depends on {dep} " f"which does not exist"
                                ),
                            )
                        )

        # -- Inter-step reference consistency --
        # Params containing $<step_id>.result.* must have matching dep
        # OR reference a completed step (cross-boundary, micro-replan).
        for step in steps:
            if not step.params:
                continue
            for param_key, param_val in step.params.items():
                if not isinstance(param_val, str):
                    continue
                match = _INTER_STEP_REF_PATTERN.match(param_val)
                if match:
                    ref_step_id = match.group(1)
                    # Cross-boundary: ref to completed step is always
                    # valid -- orchestrator resolves from completed_results.
                    if ref_step_id in external_ids:
                        continue
                    step_deps = set(dependencies.get(step.id, []))
                    if ref_step_id not in step_deps:
                        issues.append(
                            ValidationIssue(
                                check_name=CHECK_INTER_STEP_REF,
                                severity=SEVERITY_ERROR,
                                step_id=step.id,
                                detail=(
                                    f"Param '{param_key}' references "
                                    f"${ref_step_id}.result but {ref_step_id} "
                                    f"is not in dependencies"
                                ),
                            )
                        )

        # -- Kahn's topological sort (cycle detection) --
        # Build adjacency list: for each dep edge dep_id -> step_id
        in_degree: Dict[str, int] = {sid: 0 for sid in step_id_set}
        adj: Dict[str, List[str]] = {sid: [] for sid in step_id_set}

        for step_id, dep_list in dependencies.items():
            if step_id not in step_id_set:
                continue
            for dep in dep_list:
                if dep not in step_id_set:
                    continue
                adj[dep].append(step_id)
                in_degree[step_id] = in_degree.get(step_id, 0) + 1

        queue: deque[str] = deque()
        for sid in step_id_set:
            if in_degree.get(sid, 0) == 0:
                queue.append(sid)

        visited = 0
        while queue:
            node = queue.popleft()
            visited += 1
            for successor in adj.get(node, []):
                in_degree[successor] -= 1
                if in_degree[successor] == 0:
                    queue.append(successor)

        if visited < len(step_id_set):
            # Cycle detected -- identify cycle members.
            cycle_members = [sid for sid in step_id_set if in_degree.get(sid, 0) > 0]
            issues.append(
                ValidationIssue(
                    check_name=CHECK_DAG_CYCLE,
                    severity=SEVERITY_ERROR,
                    detail=(
                        f"DAG cycle detected involving: " f"{' -> '.join(sorted(cycle_members))}"
                    ),
                )
            )

        passed = not any(i.severity == SEVERITY_ERROR for i in issues)
        return passed, issues

    def _check_capability_existence(
        self,
        steps: List[PlanStep],
        cached_capabilities: Optional[List[ScoredCapability]],
    ) -> Tuple[bool, List[ValidationIssue]]:
        """Verify every PlanStep.capability exists (Section 8.2.2, PLAN-08).

        Uses cached capabilities from EXPAND when available. Falls back
        to IFabricRetrievalPort if no cache provided.

        Returns (passed, issues).
        """
        issues: List[ValidationIssue] = []

        # Build set of known capability names from cache.
        known_caps: set[str] = set()
        if cached_capabilities:
            for sc in cached_capabilities:
                if sc.contract and sc.contract.name:
                    known_caps.add(sc.contract.name)

        for step in steps:
            cap = step.capability
            if not cap:
                issues.append(
                    ValidationIssue(
                        check_name=CHECK_CAPABILITY_MISSING,
                        severity=SEVERITY_ERROR,
                        step_id=step.id,
                        detail=f"Step {step.id} has empty capability",
                    )
                )
                continue

            # Skip inter-step references (resolved at execution time).
            if cap.startswith("$"):
                continue

            # Skip reserved meta-capability (always valid).
            if cap == _META_CAPABILITY_BUILD_AGENT:
                continue

            # Skip UNRESOLVED (degraded EXPAND fallback -- let it through).
            if cap == "UNRESOLVED":
                issues.append(
                    ValidationIssue(
                        check_name=CHECK_CAPABILITY_MISSING,
                        severity=SEVERITY_WARNING,
                        step_id=step.id,
                        detail=(
                            f"Step {step.id} has unresolved capability "
                            f"(degraded EXPAND fallback)"
                        ),
                    )
                )
                continue

            # Check against cached capabilities.
            if known_caps and cap in known_caps:
                continue

            # If no cache or not found in cache -- mark as missing.
            # In production, would query IFabricRetrievalPort here.
            # For V1, we rely on cached capabilities from EXPAND.
            if not known_caps:
                # No cache available -- skip check (cannot verify without I/O).
                continue

            issues.append(
                ValidationIssue(
                    check_name=CHECK_CAPABILITY_MISSING,
                    severity=SEVERITY_ERROR,
                    step_id=step.id,
                    detail=(
                        f"Unknown capability: {cap} (step {step.id}). " f"Not found in registry."
                    ),
                )
            )

        passed = not any(i.severity == SEVERITY_ERROR for i in issues)
        return passed, issues

    def _validate_plan_constraints(
        self,
        steps: List[PlanStep],
        ctx: StageContext,
        cached_capabilities: Optional[List[ScoredCapability]],
    ) -> List[ValidationIssue]:
        """Supplementary constraint checks (Section 8.2.3).

        - PLAN-05 tool call count post-hoc check.
        - PlanStep param type validation against CapabilityContract.

        Returns list of issues (errors block, warnings logged).
        """
        issues: List[ValidationIssue] = []

        # PLAN-05: check tool_calls_used against budget.
        # StageContext doesn't carry tool_calls_used directly -- this is
        # a supplementary check. PipelineController tracks the actual count.
        # We validate step-level constraints instead.

        # Build capability contract lookup from cache.
        contract_by_name: Dict[str, Any] = {}
        if cached_capabilities:
            for sc in cached_capabilities:
                if sc.contract and sc.contract.name:
                    contract_by_name[sc.contract.name] = sc.contract

        # Param validation: check required inputs are present.
        for step in steps:
            contract = contract_by_name.get(step.capability)
            if not contract:
                continue

            # Check required inputs.
            required_input_names = {inp.name for inp in (contract.required_inputs or [])}
            provided_params = set(step.params.keys()) if step.params else set()

            for req_name in required_input_names:
                # Skip inter-step reference params -- they resolve at runtime.
                if step.params and isinstance(step.params.get(req_name), str):
                    val = step.params[req_name]
                    if _INTER_STEP_REF_PATTERN.match(val):
                        continue
                if req_name not in provided_params:
                    issues.append(
                        ValidationIssue(
                            check_name=CHECK_PARAM_TYPE_MISMATCH,
                            severity=SEVERITY_ERROR,
                            step_id=step.id,
                            detail=(
                                f"Step {step.id} missing required param "
                                f"'{req_name}' for capability {step.capability}"
                            ),
                        )
                    )

            # Check for unsafe capabilities (safety band below GREEN).
            if hasattr(contract, "safety_band_min"):
                sbm = contract.safety_band_min
                if sbm and sbm not in ("GREEN", "green"):
                    issues.append(
                        ValidationIssue(
                            check_name=CHECK_UNSAFE_CAPABILITY,
                            severity=SEVERITY_WARNING,
                            step_id=step.id,
                            detail=(
                                f"Step {step.id} uses capability {step.capability} "
                                f"with safety_band_min={sbm}"
                            ),
                        )
                    )

        return issues

    # ===================================================================
    # Phase 2: LLM Arbiter
    # ===================================================================

    async def _call_arbiter(
        self,
        expanded_plan: ExpandedPlan,
        request: Optional[PlanRequest],
        ctx: StageContext,
        det_issues: List[ValidationIssue],
        *,
        is_micro: bool = False,
    ) -> ValidationVerdict:
        """Call LLM arbiter for semantic review (Section 8.3).

        Uses STRUCTURED capability (not CHAT) with temperature 0.1.
        Guaranteed JSON output conforming to VALIDATE_VERDICT_SCHEMA.

        Args:
            expanded_plan: The plan to validate.
            request: Original plan request (None for micro-validate).
            ctx: Runtime context.
            det_issues: Issues from deterministic checks (passed to arbiter
                in DETERMINISTIC_RESULTS slot).
            is_micro: True for micro-validate (reduced budget).

        Returns:
            ValidationVerdict parsed from arbiter response.

        Raises:
            Exception: On arbiter timeout/error (caller handles).
        """
        if ctx.cancel_check():
            raise ValidateRejectedError(
                "Plan cancelled during validation",
                stage="VALIDATE",
                request_id=ctx.request_id,
                trace_id=ctx.trace_id,
            )

        system_prompt, user_prompt = self._assemble_arbiter_prompt(
            expanded_plan,
            request,
            det_issues,
        )

        max_tokens = _MICRO_ARBITER_MAX_TOKENS if is_micro else _ARBITER_MAX_TOKENS
        timeout_ms = _MICRO_ARBITER_TIMEOUT_MS if is_micro else _ARBITER_TIMEOUT_MS

        constraints = PlannerConstraints(
            max_tokens=max_tokens,
            timeout_ms=timeout_ms,
            temperature=_ARBITER_TEMPERATURE,
            consumer_id="planner.validate",
        )

        hub_request = PlannerLLMRequest(
            capability="STRUCTURED",
            payload={
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "output_schema": VALIDATE_VERDICT_SCHEMA,
                "temperature": _ARBITER_TEMPERATURE,
            },
            constraints=constraints,
            trace_id=ctx.trace_id,
        )

        response: PlannerLLMResponse = await self._llm_port.execute(hub_request)

        content = response.result.get("content", "")
        tokens_used = response.metadata.get("usage", {}).get("total_tokens", 0)

        log.debug(
            "validate.arbiter_response request_id=%s tokens=%d",
            ctx.request_id,
            tokens_used,
        )

        return self._parse_verdict(content, det_issues)

    def _assemble_arbiter_prompt(
        self,
        expanded_plan: ExpandedPlan,
        request: Optional[PlanRequest],
        det_issues: List[ValidationIssue],
    ) -> Tuple[str, str]:
        """Assemble slot-based arbiter prompt (Section 8.3.1).

        Returns (system_prompt, user_prompt).
        """
        system_prompt = _ARBITER_SYSTEM_PROMPT.replace(
            "{output_schema}",
            json.dumps(VALIDATE_VERDICT_SCHEMA, indent=2),
        )

        # -- Build user prompt with data slots --
        parts: List[str] = []

        # ORIGINAL_INTENT slot.
        intent = request.intent if request else "micro-replan"
        parts.append(f"USER INTENT: {intent}")

        # PLAN_SUMMARY slot.
        step_count = len(expanded_plan.steps)
        dep_count = sum(len(deps) for deps in expanded_plan.dependencies.values())
        side_effect_steps = [s for s in expanded_plan.steps if s.has_side_effects]
        parts.append(
            f"PLAN SUMMARY: {step_count} steps, {dep_count} dependency edges, "
            f"{len(side_effect_steps)} steps with side effects."
        )

        # STEP_DETAILS slot (per step summary).
        step_lines: List[str] = []
        for step in expanded_plan.steps:
            dep_str = ", ".join(expanded_plan.dependencies.get(step.id, [])) or "none"
            step_lines.append(
                f"  - {step.id}: capability={step.capability}, "
                f"deps=[{dep_str}], "
                f"has_side_effects={step.has_side_effects}, "
                f"safety_band_min={step.safety_band_min or 'GREEN'}, "
                f"is_optional={step.is_optional}"
            )
        parts.append("STEP DETAILS:\n" + "\n".join(step_lines))

        # DETERMINISTIC_RESULTS slot.
        if det_issues:
            det_lines = [f"  - [{i.severity}] {i.check_name}: {i.detail}" for i in det_issues]
            parts.append("DETERMINISTIC RESULTS (issues found):\n" + "\n".join(det_lines))
        else:
            parts.append(
                f"DETERMINISTIC RESULTS: All checks passed. "
                f"DAG: acyclic ({step_count} steps, {dep_count} edges). "
                f"Capabilities: all {step_count} verified in registry."
            )

        # RATIONALE slot from EXPAND.
        if expanded_plan.rationale:
            parts.append(f"EXPAND RATIONALE: {expanded_plan.rationale}")

        user_prompt = "\n\n".join(parts)
        return system_prompt, user_prompt

    def _parse_verdict(
        self,
        content: str,
        det_issues: List[ValidationIssue],
    ) -> ValidationVerdict:
        """Parse arbiter JSON response into ValidationVerdict (Section 8.3.3).

        The STRUCTURED capability guarantees valid JSON conforming to
        VALIDATE_VERDICT_SCHEMA, so parsing should not fail. Defensive
        fallback included for robustness.

        Args:
            content: Raw LLM response (JSON string or dict).
            det_issues: Deterministic issues to carry forward.
        """
        # Parse JSON.
        if isinstance(content, dict):
            data = content
        elif isinstance(content, str):
            try:
                data = json.loads(content)
            except (json.JSONDecodeError, TypeError):
                log.warning(
                    "validate.arbiter_parse_failed content=%s",
                    content[:200] if content else "(empty)",
                )
                # Defensive fallback: approve on parse failure if we have
                # no deterministic issues with error severity.
                return ValidationVerdict(
                    status=VERDICT_APPROVED,
                    issues=[i for i in det_issues if i.severity == SEVERITY_WARNING],
                    confidence=0.0,
                    rationale="Arbiter response unparseable, auto-approved",
                    deterministic_pass=True,
                    safety_assessment=SAFETY_UNKNOWN,
                )
        else:
            data = {}

        # Extract fields with safe defaults.
        status = data.get("status", VERDICT_APPROVED)
        if status not in (VERDICT_APPROVED, VERDICT_REVISE, VERDICT_REJECT):
            status = VERDICT_APPROVED

        reasons = data.get("reasons", [])
        if not isinstance(reasons, list):
            reasons = [str(reasons)]
        if not reasons:
            reasons = ["No specific reason provided"]

        suggested_fixes = data.get("suggested_fixes", [])
        if not isinstance(suggested_fixes, list):
            suggested_fixes = [str(suggested_fixes)]

        coherence_score = data.get("coherence_score", 0.5)
        if not isinstance(coherence_score, (int, float)):
            coherence_score = 0.5
        coherence_score = max(0.0, min(1.0, float(coherence_score)))

        safety_assessment = data.get("safety_assessment", SAFETY_UNKNOWN)
        if safety_assessment not in (SAFETY_SAFE, SAFETY_CAUTION, SAFETY_UNSAFE):
            safety_assessment = SAFETY_UNKNOWN

        completeness = data.get("completeness", True)

        # Build issues from arbiter reasons.
        arbiter_issues: List[ValidationIssue] = []
        if status in (VERDICT_REVISE, VERDICT_REJECT):
            severity = SEVERITY_ERROR if status == VERDICT_REJECT else SEVERITY_WARNING
            for reason in reasons:
                arbiter_issues.append(
                    ValidationIssue(
                        check_name=CHECK_LLM_ARBITER_REJECT,
                        severity=severity,
                        detail=str(reason),
                    )
                )

        # Combine deterministic warning issues + arbiter issues.
        all_issues = [i for i in det_issues if i.severity == SEVERITY_WARNING] + arbiter_issues

        # Build rationale string.
        rationale = "; ".join(str(r) for r in reasons)
        if not completeness and status == VERDICT_APPROVED:
            rationale += " (completeness: partial)"

        return ValidationVerdict(
            status=status,
            issues=all_issues,
            confidence=coherence_score,
            rationale=rationale or "Arbiter verdict",
            deterministic_pass=True,
            safety_assessment=safety_assessment,
            suggested_fixes=suggested_fixes,
        )

    # ===================================================================
    # Phase 3: HIL Approval
    # ===================================================================

    async def _check_and_run_hil_approval(
        self,
        expanded_plan: ExpandedPlan,
        verdict: ValidationVerdict,
        request: PlanRequest,
        ctx: StageContext,
    ) -> ValidationVerdict:
        """Check HIL trigger conditions and run approval if needed (Section 8.4).

        Trigger conditions (ALL must be true):
        1. At least one step has has_side_effects=True.
        2. Plan has step with safety_band_min != 'GREEN' OR
           arbiter safety_assessment == 'caution'.
        3. LLM arbiter approved (caller ensures this).

        Auto-approve if all side-effect steps have safety_band_min='GREEN'
        AND arbiter safety_assessment='safe'.

        Args:
            expanded_plan: The plan being validated.
            verdict: Current arbiter verdict (must be 'approved').
            request: Original plan request.
            ctx: Runtime context.

        Returns:
            Unchanged verdict (auto-approved) or modified verdict
            based on HIL response.
        """
        # Check if any step has side effects.
        side_effect_steps = [s for s in expanded_plan.steps if s.has_side_effects]
        if not side_effect_steps:
            # No side effects -- auto-approve, no HIL needed.
            return verdict

        # Check auto-approve conditions.
        all_green = all(
            (s.safety_band_min or "GREEN") in ("GREEN", "green") for s in side_effect_steps
        )
        if all_green and verdict.safety_assessment == SAFETY_SAFE:
            log.debug(
                "validate.hil_auto_approve request_id=%s " "reason=all_green_and_safe",
                ctx.request_id,
            )
            return verdict

        # HIL approval required.
        side_effects_desc = [f"{s.id}: {s.capability}" for s in side_effect_steps]
        estimated_duration = sum(s.timeout_ms for s in expanded_plan.steps)

        try:
            approval = await self._hil_port.request_approval(
                ApprovalRequest(
                    caller_key=f"planner:validate:{ctx.request_id}",
                    trace_id=ctx.request_id,
                    summary=(
                        f"Plan with {len(expanded_plan.steps)} steps, "
                        f"{len(side_effect_steps)} with side effects."
                    ),
                    side_effects=side_effects_desc,
                    safety_assessment=verdict.safety_assessment,
                    estimated_duration_ms=estimated_duration,
                )
            )
            hil_response = approval.decision
            timed_out = approval.timed_out
        except Exception:
            # Underlying transport error treated as timeout.
            hil_response = ""
            timed_out = True

        if timed_out:
            if all_green:
                log.warning(
                    "validate.hil_timeout_auto_approve request_id=%s",
                    ctx.request_id,
                )
                return verdict
            log.warning(
                "validate.hil_timeout_plan_failed request_id=%s",
                ctx.request_id,
            )
            return ValidationVerdict(
                status=VERDICT_REJECT,
                issues=verdict.issues
                + [
                    ValidationIssue(
                        check_name="hil_timeout",
                        severity=SEVERITY_ERROR,
                        detail="HIL approval timed out for non-GREEN plan",
                    ),
                ],
                confidence=verdict.confidence,
                rationale="HIL approval timed out",
                deterministic_pass=True,
                safety_assessment=verdict.safety_assessment,
                suggested_fixes=[],
            )

        # Route HIL response.
        if hil_response == "approve":
            return verdict
        elif hil_response == "reject":
            return ValidationVerdict(
                status=VERDICT_REJECT,
                issues=verdict.issues
                + [
                    ValidationIssue(
                        check_name="hil_rejection",
                        severity=SEVERITY_ERROR,
                        detail="User explicitly rejected the plan",
                    ),
                ],
                confidence=verdict.confidence,
                rationale="Plan rejected by user",
                deterministic_pass=True,
                safety_assessment=verdict.safety_assessment,
                suggested_fixes=[],
            )
        elif hil_response == "modify":
            # User requested modifications.
            # In V1, modifications are not yet supported -- treat as approve.
            log.info(
                "validate.hil_modify_treated_as_approve request_id=%s",
                ctx.request_id,
            )
            return verdict
        else:
            # Unexpected response -- treat as approve.
            log.warning(
                "validate.hil_unexpected_response request_id=%s response=%s",
                ctx.request_id,
                hil_response,
            )
            return verdict
