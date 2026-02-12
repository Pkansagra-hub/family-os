"""
k1.orchestrator.orchestration.constraint_resolver -- Pre-execution plan validation.

Validates a CommittedPlan before DAG execution begins. Ensures all
capabilities exist in Fabric Registry, params are satisfiable, safety
band is OK, and time budget is within bounds.

Issues: 3.1.1 (validate), 3.1.2 (check_capabilities),
        3.1.3 (find_alternatives), 3.1.4 (resolve_iteratively).

Validation call chain:
  validate(plan) -> check_capabilities(steps)
                 -> find_alternatives() for missing (3.1.3)
                 -> resolve_iteratively() for remaining (3.1.4)
                 -> compute_time_budget() for time pressure

Design:
  - Called by DAGExecutor.execute() BEFORE wave loop starts,
    NOT directly by OrchestratorService.
  - Stateless per call: clones CommittedPlan before substitutions.
  - Async: capability checks require Fabric Registry queries.
  - Thread safe: no mutable instance state beyond constructor deps.

References:
  - orchestrator-implementation-plan.md (Epic 3.1)
  - BUDGET-1 (time budget estimation)
  - ADR-1.1.12 (HIL async pattern)

Exports:
  ConstraintResolver
"""

from __future__ import annotations

import dataclasses
import logging
import uuid
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

if TYPE_CHECKING:
    from k1.orchestrator.ports.delta_emit_port import IDeltaEmitPort
    from k1.orchestrator.ports.event_subscription_port import IEventSubscriptionPort
    from k1.orchestrator.ports.fabric_gateway_port import IFabricGatewayPort

from k1.orchestrator.types import (
    AlternativeCapability,
    AlternativeMapping,
    CapabilityCheck,
    CommittedPlan,
    HILRequest,
    PlanStep,
    RegistryEntry,
    ResolutionResult,
    ValidationResult,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# HIGH tier time budget target (10 seconds). BUDGET-1.
HIGH_TIER_TIME_BUDGET_MS: int = 10_000

# Default max resolution cycles before HIL fallback.
DEFAULT_MAX_CYCLES: int = 3

# Minimum alternative score to consider (3.1.3). Below this, too noisy.
MIN_ALTERNATIVE_SCORE: float = 0.3

# V1: no schema data from RegistryEntry, use neutral assumption for scoring.
SCHEMA_OVERLAP_DEFAULT_V1: float = 0.5

# Maximum alternatives to return per missing capability.
TOP_N_ALTERNATIVES: int = 3

# Safety band ordering: GREEN (strictest/safest=1) < AMBER=2 < RED=3 (most lenient).
# "candidate <= step" means candidate is same strictness or stricter.
SAFETY_BAND_RANK: Dict[str, int] = {
    "GREEN": 1,
    "AMBER": 2,
    "RED": 3,
}

# Scoring weights for alternative candidates (3.1.3).
W_SCHEMA: float = 0.6
W_SAFETY: float = 0.2
W_NAME: float = 0.2

# HIL constraint fallback timeout (3.1.5).
HIL_TIMEOUT_MS: int = 60_000


# ---------------------------------------------------------------------------
# Module-level helpers (pure functions)
# ---------------------------------------------------------------------------


def _derive_category(capability: str) -> str:
    """Derive category prefix from capability naming convention.

    Convention: tool.{type}.{action} or tool.{type}.{domain}.{action}
    Category: all segments except the last (the action name).

    Examples:
        "tool.calendar.search" -> "tool.calendar"
        "tool.read.lookup"     -> "tool.read"
        "agent.summarize"      -> "agent"
        "single"               -> "single"
    """
    parts = capability.split(".")
    if len(parts) >= 2:
        return ".".join(parts[:-1])
    return capability


def _safety_band_rank(band: str) -> int:
    """Get numeric rank for safety band string. Lower = stricter.

    GREEN=1 (strictest), AMBER=2, RED=3 (most lenient).
    Unknown bands return 999 (treated as very lenient).
    """
    return SAFETY_BAND_RANK.get(band.upper(), 999)


def _levenshtein(a: str, b: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(a) < len(b):
        return _levenshtein(b, a)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(
                min(
                    prev[j + 1] + 1,  # delete
                    curr[j] + 1,  # insert
                    prev[j] + (0 if ca == cb else 1),  # substitute
                )
            )
        prev = curr
    return prev[-1]


def _name_similarity(a: str, b: str) -> float:
    """Normalized string similarity (1.0 = identical, 0.0 = no overlap).

    Uses Levenshtein edit distance normalized by max string length.
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    dist = _levenshtein(a, b)
    return 1.0 - dist / max(len(a), len(b))


def format_constraint_question(unresolved: List[CapabilityCheck]) -> str:
    """Build human-readable summary of unresolved constraint issues (3.1.5).

    Used by trigger_hil_fallback() to compose the HILRequest question.
    Each unresolved capability is listed with its step and any known
    alternatives. The question ends with a prompt for user action.

    Args:
        unresolved: CapabilityChecks still unresolved after auto-resolution.

    Returns:
        Multi-line string suitable for user display.
    """
    if not unresolved:
        return "No unresolved constraints."

    lines = ["The following capabilities could not be resolved automatically:"]
    for check in unresolved:
        line = f"  - '{check.capability}' (step '{check.step_id}')"
        if check.alternatives:
            alt_list = ", ".join(check.alternatives)
            line += f" [available alternatives: {alt_list}]"
        lines.append(line)
    lines.append("")
    lines.append("How would you like to proceed?")
    return "\n".join(lines)


def build_options(unresolved: List[CapabilityCheck]) -> List[str]:
    """Build option labels for HIL constraint question (3.1.5).

    Generates one "skip" option per unresolved step, one "use alternative"
    option per alternative per step, and a final "cancel plan" option.

    Args:
        unresolved: CapabilityChecks still unresolved after auto-resolution.

    Returns:
        List of human-readable option strings for HILRequest.options.
    """
    options: List[str] = []
    for check in unresolved:
        options.append(f"Skip step '{check.step_id}'")
        for alt in check.alternatives:
            options.append(
                f"Use '{alt}' instead of '{check.capability}' " f"for step '{check.step_id}'"
            )
    options.append("Cancel plan")
    return options


# ---------------------------------------------------------------------------
# ConstraintResolver
# ---------------------------------------------------------------------------


class ConstraintResolver:
    """Pre-execution validator for CommittedPlan.

    Orchestrates:
      1. check_capabilities() -- Fabric Registry existence checks
      2. find_alternatives() -- same-category alternative discovery (3.1.3)
      3. resolve_iteratively() -- 3-cycle auto-resolution state machine (3.1.4)
      4. compute_time_budget() -- BUDGET-1 time pressure estimation

    Constructor injection:
      fabric: IFabricGatewayPort -- for query_registry() / query_registry_by_category()
      delta: IDeltaEmitPort -- for HIL request emission (3.1.5)
      events: IEventSubscriptionPort -- for HIL response subscription
      max_cycles: int -- max auto-resolution cycles (default 3)
    """

    __slots__ = ("_fabric", "_delta", "_events", "_max_cycles")

    def __init__(
        self,
        fabric: IFabricGatewayPort,
        delta: Optional[IDeltaEmitPort] = None,
        events: Optional[IEventSubscriptionPort] = None,
        max_cycles: int = DEFAULT_MAX_CYCLES,
    ) -> None:
        self._fabric = fabric
        self._delta = delta
        self._events = events
        self._max_cycles = max_cycles

    # ------------------------------------------------------------------
    # Primary method (3.1.1)
    # ------------------------------------------------------------------

    async def validate(
        self,
        plan: CommittedPlan,
    ) -> ValidationResult:
        """Validate a CommittedPlan before DAG execution.

        Orchestrates the full validation pipeline:
          1. check_capabilities() for all steps
          2. resolve_iteratively() for unavailable capabilities
             (internally calls find_alternatives per cycle)
          3. compute_time_budget() for time pressure estimation

        Args:
            plan: CommittedPlan from Planner (validated, acyclic).

        Returns:
            ValidationResult with valid=True if all checks pass,
            errors/warnings lists, alternatives_applied, and flags
            for time_pressure and hil_required.

        Gotchas:
          - Clones plan before substitutions (original preserved for audit).
          - If hil_required=True, DAGExecutor returns control to
            OrchestratorService for async HIL parking.
        """
        errors: List[str] = []
        warnings: List[str] = []
        alternatives_applied: List[AlternativeMapping] = []

        # Step 1: Check all capabilities exist in Fabric Registry
        checks = await self.check_capabilities(plan.steps)

        # Step 2: Attempt auto-resolution for unavailable capabilities
        hil_required = False
        hil_request = None
        if checks:
            unavailable = [c for c in checks if not c.available]
            if unavailable:
                resolution = await self.resolve_iteratively(plan, unavailable)
                alternatives_applied = list(resolution.alternatives_applied)

                if not resolution.resolved:
                    # Build errors from final unresolved checks
                    for check in resolution.unresolved:
                        if not check.available:
                            errors.append(
                                f"Capability '{check.capability}' not found in "
                                f"registry (step '{check.step_id}')"
                            )
                    if resolution.hil_requested:
                        hil_required = True
                        # Step 2b: Trigger HIL fallback (3.1.5)
                        hil_request = await self.trigger_hil_fallback(resolution.unresolved, plan)

        # Step 3: Compute time budget estimation (BUDGET-1)
        time_pressure = self._compute_time_budget(plan)
        if time_pressure:
            warnings.append(
                "Estimated critical-path duration exceeds HIGH tier "
                f"time budget ({HIGH_TIER_TIME_BUDGET_MS}ms). "
                "Optional steps may be skipped proactively."
            )

        valid = len(errors) == 0
        return ValidationResult(
            valid=valid,
            errors=errors,
            warnings=warnings,
            alternatives_applied=alternatives_applied,
            time_pressure=time_pressure,
            hil_required=hil_required,
            hil_request=hil_request,
        )

    # ------------------------------------------------------------------
    # Capability availability check (3.1.2)
    # ------------------------------------------------------------------

    async def check_capabilities(
        self,
        steps: List[PlanStep],
    ) -> List[CapabilityCheck]:
        """Check capability availability for all plan steps.

        Deduplicates capability names across steps (a 10-step plan may
        reference same capability multiple times). Performs one
        query_registry() call per unique capability name. For unavailable
        capabilities, calls find_alternatives() once per unique name.

        Args:
            steps: List of PlanStep from CommittedPlan.

        Returns:
            List of CapabilityCheck for steps with issues ONLY.
            Empty list = all capabilities valid.

        Gotcha:
          Uses the 14-field Orchestrator PlanStep (from types.py),
          NOT the Fabric 6-field PlanStep.
        """
        # 1. Collect unique capability names (dedup)
        unique_caps: Set[str] = set()
        cap_to_steps: Dict[str, List[PlanStep]] = {}
        for step in steps:
            cap = step.capability
            unique_caps.add(cap)
            cap_to_steps.setdefault(cap, []).append(step)

        # 2. Batch query: one registry lookup per unique capability
        registry_cache: Dict[str, Optional[RegistryEntry]] = {}
        for cap in unique_caps:
            try:
                entry = await self._fabric.query_registry(cap)
                registry_cache[cap] = entry
            except Exception as exc:
                logger.warning(
                    "[ConstraintResolver] Registry query failed for '%s': %s",
                    cap,
                    exc,
                )
                registry_cache[cap] = None

        # 3. Find alternatives for missing capabilities (one query per unique cap)
        alt_cache: Dict[str, List[str]] = {}
        for cap in unique_caps:
            if registry_cache[cap] is None:
                # Use first step referencing this capability as representative
                rep_step = cap_to_steps[cap][0]
                alts = await self.find_alternatives(cap, rep_step)
                alt_cache[cap] = [a.capability_id for a in alts]

        # 4. Build CapabilityCheck for each step with issues
        issues: List[CapabilityCheck] = []
        for step in steps:
            cap = step.capability
            entry = registry_cache.get(cap)
            available = entry is not None

            if not available:
                issues.append(
                    CapabilityCheck(
                        step_id=step.id,
                        capability=cap,
                        available=False,
                        contract_entry=None,
                        alternatives=alt_cache.get(cap, []),
                    )
                )

        return issues

    # ------------------------------------------------------------------
    # Time budget estimation (BUDGET-1)
    # ------------------------------------------------------------------

    def _compute_time_budget(
        self,
        plan: CommittedPlan,
    ) -> bool:
        """Estimate if critical-path duration exceeds HIGH tier budget.

        Sums estimated_duration_ms from capability contracts for
        critical-path steps.

        V1: advisory only, not a hard gate. Uses rough estimates
        (p50 latency from contracts). Falls back to 0 for steps
        without estimated_duration_ms.

        Args:
            plan: CommittedPlan to estimate.

        Returns:
            True if estimated duration exceeds HIGH_TIER_TIME_BUDGET_MS.
        """
        total_ms = 0
        if plan.estimated_duration_ms is not None:
            total_ms = plan.estimated_duration_ms
        else:
            # No plan-level estimate: sum step timeouts as proxy
            for step in plan.steps:
                if step.timeout_ms is not None:
                    total_ms += step.timeout_ms

        if total_ms > HIGH_TIER_TIME_BUDGET_MS:
            logger.info(
                "[ConstraintResolver] Time pressure: estimated %dms > %dms budget",
                total_ms,
                HIGH_TIER_TIME_BUDGET_MS,
            )
            return True
        return False

    # ------------------------------------------------------------------
    # HIL fallback trigger (3.1.5)
    # ------------------------------------------------------------------

    async def trigger_hil_fallback(
        self,
        unresolved: List[CapabilityCheck],
        plan: CommittedPlan,
    ) -> HILRequest:
        """Build and emit HIL request for unresolved constraints (3.1.5).

        Non-blocking: builds HILRequest, emits via delta_port, and
        returns immediately. Caller (DAGExecutor / OrchestratorService)
        is responsible for parking PendingHILContext with the returned
        request_id.

        Async pattern (ADR-1.1.12):
          1. format_constraint_question() -- human-readable summary
          2. build_options() -- skip / choose alternative / cancel
          3. HILRequest construction with uuid4 request_id
          4. delta_port.emit_hil_request() -- fire-and-forget
          5. Return HILRequest for caller to park context

        Args:
            unresolved: CapabilityChecks that could not be auto-resolved.
            plan: CommittedPlan for context (plan_id, trace_id).

        Returns:
            HILRequest that was emitted. Caller uses request_id
            to create PendingHILContext and park in pending_hil dict.

        Gotchas:
          - Does NOT block waiting for user response.
          - Does NOT park PendingHILContext (caller responsibility).
          - trace_id from plan.trace_id for correlation.
          - Timeout 60s (HIL_TIMEOUT_MS). Default action: GRACEFUL_FAIL.
        """
        question = format_constraint_question(unresolved)
        options = build_options(unresolved)

        hil_request = HILRequest(
            request_id=str(uuid.uuid4()),
            question=question,
            options=options,
            context={
                "plan_id": plan.plan_id,
                "unresolved_capabilities": [c.capability for c in unresolved],
                "unresolved_step_ids": [c.step_id for c in unresolved],
            },
            timeout_ms=HIL_TIMEOUT_MS,
        )

        if self._delta is not None:
            await self._delta.emit_hil_request(hil_request, plan.trace_id)
            logger.info(
                "[ConstraintResolver] HIL fallback emitted: request_id=%s, "
                "unresolved=%d capabilities, timeout=%dms",
                hil_request.request_id,
                len(unresolved),
                HIL_TIMEOUT_MS,
            )
        else:
            logger.warning(
                "[ConstraintResolver] HIL fallback skipped: no delta_port "
                "configured. %d unresolved capabilities.",
                len(unresolved),
            )

        return hil_request

    # ------------------------------------------------------------------
    # find_alternatives (3.1.3)
    # ------------------------------------------------------------------

    async def find_alternatives(
        self,
        missing_capability: str,
        step: PlanStep,
    ) -> List[AlternativeCapability]:
        """Find alternative capabilities for a missing capability (3.1.3).

        Queries Fabric Registry for capabilities in the same category
        (derived from naming convention: all segments except the last).
        Filters by safety band, scores candidates, returns top 3.

        Scoring (3 weighted components):
          - schema_overlap_ratio (0.6): V1 uses neutral 0.5 (no schema
            data in RegistryEntry). Full introspection deferred to V2.
          - safety_band_match (0.2): exact=1.0, stricter=0.8.
          - name_similarity (0.2): normalized Levenshtein distance.

        Args:
            missing_capability: The unavailable capability name.
            step: PlanStep that needs the capability (for safety_band context).

        Returns:
            List of AlternativeCapability sorted by score descending.
            Empty list if no suitable alternatives found.
            Candidates with score < MIN_ALTERNATIVE_SCORE (0.3) are filtered.

        V1 scope: Same-category alternatives only. Cross-category deferred.
        """
        # 1. Derive category from naming convention
        category = _derive_category(missing_capability)

        # 2. Query Fabric Registry for same-category capabilities
        try:
            candidates = await self._fabric.query_registry_by_category(category)
        except Exception as exc:
            logger.warning(
                "[ConstraintResolver] Category query failed for '%s': %s",
                category,
                exc,
            )
            return []

        if not candidates:
            return []

        # 3. Filter out the missing capability itself
        candidates = [c for c in candidates if c.name != missing_capability]

        if not candidates:
            return []

        # 4. Filter by safety band (candidate <= step: same or stricter only)
        step_band = step.safety_band_min
        if step_band:
            step_rank = _safety_band_rank(step_band)
            candidates = [
                c for c in candidates if _safety_band_rank(c.safety_band_min) <= step_rank
            ]

        if not candidates:
            return []

        # 5. Score candidates
        scored: List[Tuple[RegistryEntry, float]] = []
        for candidate in candidates:
            # V1: no schema data in RegistryEntry, use neutral assumption
            schema_score = SCHEMA_OVERLAP_DEFAULT_V1

            # Safety band match: exact=1.0, stricter=0.8
            if step_band:
                cand_rank = _safety_band_rank(candidate.safety_band_min)
                step_rank_val = _safety_band_rank(step_band)
                safety_score = 1.0 if cand_rank == step_rank_val else 0.8
            else:
                # No band requirement on step, full match
                safety_score = 1.0

            name_score = _name_similarity(missing_capability, candidate.name)

            total = W_SCHEMA * schema_score + W_SAFETY * safety_score + W_NAME * name_score
            scored.append((candidate, total))

        # 6. Sort descending, filter below minimum score
        scored.sort(key=lambda x: x[1], reverse=True)
        scored = [(c, s) for c, s in scored if s >= MIN_ALTERNATIVE_SCORE]

        # 7. Return top N with param_mapping
        result: List[AlternativeCapability] = []
        for candidate, score in scored[:TOP_N_ALTERNATIVES]:
            # V1: identity param mapping (assume alternative takes same params)
            param_mapping = {k: k for k in step.params}
            result.append(
                AlternativeCapability(
                    capability_id=candidate.name,
                    score=round(score, 4),
                    param_mapping=param_mapping,
                    safety_band=candidate.safety_band_min,
                )
            )

        return result

    # ------------------------------------------------------------------
    # resolve_iteratively (3.1.4)
    # ------------------------------------------------------------------

    async def resolve_iteratively(
        self,
        plan: CommittedPlan,
        initial_checks: List[CapabilityCheck],
    ) -> ResolutionResult:
        """3-cycle state machine for iterative constraint resolution (3.1.4).

        Cycle 1 (auto-resolve):
          For each unavailable capability with alternatives (score >= 0.3):
          clone plan, apply best-scored substitution.

        Cycle 2 (re-validate):
          Re-run check_capabilities() on modified plan. If new issues,
          attempt one more find_alternatives() round.

        Cycle 3 (HIL fallback):
          If unresolved issues remain: set hil_requested=True, return.

        Early termination:
          (a) All checks pass -> resolved=True, exit.
          (b) No alternatives found in cycle 1 -> skip to HIL.
          (c) Cycle 2 introduces MORE issues than started -> abort, HIL.

        Each cycle MUST re-run full check_capabilities() because
        substitutions can cascade.

        Args:
            plan: CommittedPlan to resolve against.
            initial_checks: CapabilityChecks with issues.

        Returns:
            ResolutionResult with outcome, modified plan, and tracking.
        """
        if not initial_checks:
            return ResolutionResult(resolved=True, cycles_used=0)

        current_plan = plan
        all_applied: List[AlternativeMapping] = []
        current_checks = initial_checks
        issues_at_start = len(initial_checks)

        # --- Cycle 1: Auto-resolve with best alternatives ---
        modified_plan, applied, remaining = await self._apply_alternatives(
            current_plan, current_checks
        )
        all_applied.extend(applied)

        if not applied:
            # Early termination (b): no alternatives found at all -> HIL
            return ResolutionResult(
                resolved=False,
                unresolved=current_checks,
                hil_requested=True,
                cycles_used=1,
                alternatives_applied=all_applied,
            )

        current_plan = modified_plan

        # Re-validate after cycle 1 substitutions (MUST re-run full check)
        current_checks = await self.check_capabilities(current_plan.steps)
        if not current_checks:
            # Early termination (a): all issues resolved
            return ResolutionResult(
                resolved=True,
                modified_plan=current_plan,
                cycles_used=1,
                alternatives_applied=all_applied,
            )

        if self._max_cycles < 2:
            return ResolutionResult(
                resolved=False,
                modified_plan=current_plan,
                unresolved=current_checks,
                hil_requested=True,
                cycles_used=1,
                alternatives_applied=all_applied,
            )

        # --- Cycle 2: Re-validate and attempt one more round ---
        if len(current_checks) > issues_at_start:
            # Early termination (c): MORE issues than we started with -> HIL
            return ResolutionResult(
                resolved=False,
                modified_plan=None,
                unresolved=current_checks,
                hil_requested=True,
                cycles_used=2,
                alternatives_applied=all_applied,
            )

        # Try one more alternatives round
        modified_plan2, applied2, _remaining2 = await self._apply_alternatives(
            current_plan, current_checks
        )
        all_applied.extend(applied2)

        if applied2:
            current_plan = modified_plan2
            # Re-validate after cycle 2 substitutions
            current_checks = await self.check_capabilities(current_plan.steps)
            if not current_checks:
                return ResolutionResult(
                    resolved=True,
                    modified_plan=current_plan,
                    cycles_used=2,
                    alternatives_applied=all_applied,
                )

        if self._max_cycles < 3:
            return ResolutionResult(
                resolved=False,
                modified_plan=current_plan if all_applied else None,
                unresolved=current_checks,
                hil_requested=True,
                cycles_used=2,
                alternatives_applied=all_applied,
            )

        # --- Cycle 3: HIL fallback ---
        return ResolutionResult(
            resolved=False,
            modified_plan=current_plan if all_applied else None,
            unresolved=current_checks,
            hil_requested=True,
            cycles_used=3,
            alternatives_applied=all_applied,
        )

    # ------------------------------------------------------------------
    # Internal: apply alternatives to plan (used by resolve_iteratively)
    # ------------------------------------------------------------------

    async def _apply_alternatives(
        self,
        plan: CommittedPlan,
        checks: List[CapabilityCheck],
    ) -> Tuple[CommittedPlan, List[AlternativeMapping], List[CapabilityCheck]]:
        """Apply best-scored alternatives for unavailable capabilities.

        For each unavailable CapabilityCheck, calls find_alternatives()
        and substitutes the best-scored candidate into the plan.
        Caches alternatives per capability to avoid redundant queries.

        Args:
            plan: Current plan state.
            checks: CapabilityChecks with issues to resolve.

        Returns:
            Tuple of (modified_plan, applied_mappings, remaining_checks).
            modified_plan has substitutions applied via dataclasses.replace().
            remaining_checks are issues that had no viable alternatives.
        """
        step_lookup = {step.id: step for step in plan.steps}
        new_steps = list(plan.steps)
        applied: List[AlternativeMapping] = []
        remaining: List[CapabilityCheck] = []

        # Cache alternatives per capability to avoid redundant queries
        alt_cache: Dict[str, List[AlternativeCapability]] = {}

        for check in checks:
            if check.available:
                continue

            step = step_lookup.get(check.step_id)
            if step is None:
                remaining.append(check)
                continue

            # Use cached alternatives or query
            if check.capability not in alt_cache:
                alt_cache[check.capability] = await self.find_alternatives(check.capability, step)
            alts = alt_cache[check.capability]

            if alts and alts[0].score >= MIN_ALTERNATIVE_SCORE:
                best = alts[0]
                idx = next(
                    (i for i, s in enumerate(new_steps) if s.id == check.step_id),
                    None,
                )
                if idx is not None:
                    new_steps[idx] = dataclasses.replace(
                        new_steps[idx], capability=best.capability_id
                    )
                    applied.append(
                        AlternativeMapping(
                            original_capability=check.capability,
                            replacement_capability=best.capability_id,
                            reason=f"Auto-resolved (score={best.score})",
                        )
                    )
                else:
                    remaining.append(check)
            else:
                remaining.append(check)

        modified_plan = dataclasses.replace(plan, steps=new_steps)
        return modified_plan, applied, remaining

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"ConstraintResolver(fabric={self._fabric!r}, " f"max_cycles={self._max_cycles})"
