"""``PolicyEvaluator`` — apply conscience ∧ matrix ∧ tier → verdict.

Pure, synchronous, no I/O. The evaluator never touches the bus, never
calls HIL, and never serializes anything. Those are the
``ConciergePolicyGate``'s responsibilities.

E6 Empty-Set Invariant (M8 restatement)
=======================================
The original M2 statement said "any tool not in
``capabilities.can_do`` is denied." The M6/M7/M8 inversion replaces
that with a **conscience-first** semantics:

* If ``frame.conscience`` is present:
    - tool ∈ ``conscience.forbidden_acts`` → **DENY**
    - tool ∈ ``conscience.must_ask_acts``  → **REQUIRE_CONFIRMATION**
    - ``conscience.tier_floor[tool]`` not satisfied → **REQUIRE_IDENTITY**
    - ``conscience.risk_overrides[tool]`` raises baseline risk
    - everything else → matrix lookup, default-ALLOW
* If ``frame.conscience`` is ``None`` (legacy v0 frames in tests):
    - fall back to the original ``Capabilities``-based E6 check.

Both paths converge on the same matrix lookup once the conscience /
capability check passes.
"""

from __future__ import annotations

import logging

from k1.selfmodel.contracts.policy import (
    DEFAULT_DECISION_MATRIX,
    FreshnessState,
    PolicyDecision,
    PolicyRequest,
    PolicyVerdict,
    ReasonCode,
    RiskClass,
    decision_for,
)
from k1.selfmodel.contracts.situation import SituationFrame

__all__ = ["PolicyEvaluator"]

logger = logging.getLogger(__name__)


# Mapping for risk_overrides string → RiskClass. Unknown strings are
# ignored (the override is treated as absent).
_RISK_BY_NAME: dict[str, RiskClass] = {
    "low": RiskClass.LOW,
    "medium": RiskClass.MEDIUM,
    "high": RiskClass.HIGH,
    "safety_sensitive": RiskClass.SAFETY_SENSITIVE,
}


def _coerce_override(value: str) -> RiskClass | None:
    if not isinstance(value, str):
        return None
    return _RISK_BY_NAME.get(value.strip().lower())


class PolicyEvaluator:
    """Pure-function policy evaluator. Stateless except for the matrix."""

    __slots__ = ("_matrix",)

    def __init__(
        self,
        *,
        matrix=DEFAULT_DECISION_MATRIX,  # type: ignore[assignment]
    ) -> None:
        self._matrix = matrix

    # ------------------------------------------------------------------
    def evaluate(
        self,
        request: PolicyRequest,
        frame: SituationFrame,
        *,
        freshness_state: FreshnessState = FreshnessState.FRESH,
        current_tier: int = 0,
    ) -> PolicyVerdict:
        """Return the verdict for ``request`` against ``frame``."""
        if not isinstance(request, PolicyRequest):
            raise TypeError("request must be a PolicyRequest")
        if not isinstance(frame, SituationFrame):
            raise TypeError("frame must be a SituationFrame")
        if not isinstance(freshness_state, FreshnessState):
            raise TypeError("freshness_state must be a FreshnessState")

        if frame.conscience is not None:
            return self._evaluate_with_conscience(
                request, frame, freshness_state=freshness_state, current_tier=current_tier
            )
        return self._evaluate_legacy(
            request, frame, freshness_state=freshness_state, current_tier=current_tier
        )

    # ------------------------------------------------------------------
    # M6/M7/M8 conscience-first path
    # ------------------------------------------------------------------
    def _evaluate_with_conscience(
        self,
        request: PolicyRequest,
        frame: SituationFrame,
        *,
        freshness_state: FreshnessState,
        current_tier: int,
    ) -> PolicyVerdict:
        tool = request.tool_name
        digest = frame.conscience
        assert digest is not None  # narrowed by caller

        # Step 1: forbidden → DENY.
        if digest.is_forbidden(tool):
            return PolicyVerdict(
                decision=PolicyDecision.DENY,
                reason=ReasonCode.CAPABILITY_NOT_GRANTED,
                detail=(
                    f"act '{tool}' is in conscience.forbidden_acts "
                    "(constitution forbids this action)"
                ),
            )

        # Step 2: tier_floor → REQUIRE_IDENTITY.
        required_tier = int(digest.tier_floor.get(tool, 0))
        if required_tier > current_tier:
            return PolicyVerdict(
                decision=PolicyDecision.REQUIRE_IDENTITY,
                reason=ReasonCode.IDENTITY_TIER_TOO_LOW,
                detail=(
                    f"act '{tool}' requires identity tier {required_tier} "
                    f"(current={current_tier})"
                ),
                requires_tier=required_tier,
            )

        # Step 3: apply risk_overrides → bump baseline risk.
        risk = request.risk_class if isinstance(request.risk_class, RiskClass) else RiskClass.LOW
        override = _coerce_override(digest.risk_overrides.get(tool, ""))
        if override is not None:
            risk = override

        # Step 4: matrix lookup.
        decision, reason = decision_for(risk, freshness_state)

        # Step 5: must_ask upgrade — if base ALLOW but conscience says
        # ASK, escalate to REQUIRE_CONFIRMATION.
        if decision == PolicyDecision.ALLOW and digest.is_must_ask(tool):
            return PolicyVerdict(
                decision=PolicyDecision.REQUIRE_CONFIRMATION,
                reason=ReasonCode.NEEDS_CONFIRMATION,
                detail=(
                    f"act '{tool}' is in conscience.must_ask_acts "
                    "(constitution tightens base ALLOW)"
                ),
            )

        # Step 4.5 (M14.E1.I4): soft_warn — if base ALLOW and the act is
        # in soft_warn_acts, downgrade to ALLOW_WITH_CAUTION so the gate
        # can surface a cautionary note without blocking.
        if decision == PolicyDecision.ALLOW and digest.is_soft_warn(tool):
            return PolicyVerdict(
                decision=PolicyDecision.ALLOW_WITH_CAUTION,
                reason=ReasonCode.SOFT_WARN,
                detail=(
                    f"act '{tool}' is in conscience.soft_warn_acts " "(allowed but cautionary)"
                ),
            )

        # Step 6: emergency override (safety_sensitive only).
        if (
            risk == RiskClass.SAFETY_SENSITIVE
            and request.emergency
            and decision == PolicyDecision.DEFER_OFFLINE
        ):
            return PolicyVerdict(
                decision=PolicyDecision.ALLOW,
                reason=ReasonCode.EMERGENCY_OVERRIDE,
                detail=(
                    f"emergency override for safety_sensitive act '{tool}' "
                    f"in state={freshness_state.value}; audit required"
                ),
                audit_required=True,
            )

        return PolicyVerdict(decision=decision, reason=reason)

    # ------------------------------------------------------------------
    # Legacy v0 path (kept for tests that build SituationFrame without
    # a conscience digest). Removed in M9.
    # ------------------------------------------------------------------
    def _evaluate_legacy(
        self,
        request: PolicyRequest,
        frame: SituationFrame,
        *,
        freshness_state: FreshnessState,
        current_tier: int,
    ) -> PolicyVerdict:
        tool = request.tool_name
        caps = frame.capabilities

        if tool not in caps.can_do and tool not in caps.requires_confirmation:
            return PolicyVerdict(
                decision=PolicyDecision.DENY,
                reason=ReasonCode.CAPABILITY_NOT_GRANTED,
                detail=(
                    f"tool '{tool}' is not in actor capabilities "
                    f"(can_do or requires_confirmation)"
                ),
            )

        required_tier = int(caps.requires_identity_tier.get(tool, 0))
        if required_tier > current_tier:
            return PolicyVerdict(
                decision=PolicyDecision.REQUIRE_IDENTITY,
                reason=ReasonCode.IDENTITY_TIER_TOO_LOW,
                detail=(
                    f"tool '{tool}' requires identity tier {required_tier} "
                    f"(current={current_tier})"
                ),
                requires_tier=required_tier,
            )

        risk = request.risk_class if isinstance(request.risk_class, RiskClass) else RiskClass.LOW
        decision, reason = decision_for(risk, freshness_state)

        if decision == PolicyDecision.ALLOW and tool in caps.requires_confirmation:
            return PolicyVerdict(
                decision=PolicyDecision.REQUIRE_CONFIRMATION,
                reason=ReasonCode.NEEDS_CONFIRMATION,
                detail=(
                    f"tool '{tool}' is in requires_confirmation "
                    f"(constitution tightens base ALLOW)"
                ),
            )

        if (
            risk == RiskClass.SAFETY_SENSITIVE
            and request.emergency
            and decision == PolicyDecision.DEFER_OFFLINE
        ):
            return PolicyVerdict(
                decision=PolicyDecision.ALLOW,
                reason=ReasonCode.EMERGENCY_OVERRIDE,
                detail=(
                    f"emergency override for safety_sensitive tool '{tool}' "
                    f"in state={freshness_state.value}; audit required"
                ),
                audit_required=True,
            )

        return PolicyVerdict(decision=decision, reason=reason)
