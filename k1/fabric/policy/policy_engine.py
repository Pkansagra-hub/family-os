"""
k1.fabric.policy.policy_engine -- Composite PolicyEngine (3.2.5).

Composes the four policy dimensions into a single evaluation step
called by the Resolver (3.1.5) during provider resolution.

Dimension composition:
  1. SecurityContext (hard gate) -- FIRST.  If rejected, candidate is
     immediately excluded (allowed=False, score=0.0).
  2. AffectiveRouting (soft, +0.0 to +0.2) -- request-level, same for all.
  3. CognitiveLoadRouting (soft, +0.0 to +0.15) -- request-level, same for all.
  4. QoSIntegration (soft, +0.0 to +0.2) -- per-provider, cost/latency aware.

Composite score formula::

    final_score = base_relevance + affective + cognitive + qos

Where ``base_relevance = 1.0`` for single-provider capabilities (most cases)
and ``soft_ranking_score`` for multi-provider.  This implementation uses
1.0 as the base for all candidates.

Satisfies ``PolicyEnginePort`` Protocol defined in resolver.py::

    evaluate(candidates, contract, request) -> List[ScoredCandidate]

Deterministic per FAB-10.

References:
  - fabric_discussion.md Section 10 (Four Policy Dimensions, Composite Score)
  - Epic 3.2.5 in fabric-implementation-plan.md
  - resolver.py PolicyEnginePort Protocol

Exports:
  PolicyEngine -- Composite policy evaluator
"""

from __future__ import annotations

import logging
import time
from typing import FrozenSet, List, Optional, Union

from k1.fabric.logging import get_default_logger as get_fabric_logger
from k1.fabric.metrics import get_default_metrics
from k1.fabric.policy.affective_routing import AffectiveRouting, AffectiveScore
from k1.fabric.policy.cognitive_load_routing import CognitiveLoadRouting, CognitiveScore
from k1.fabric.policy.qos_integration import QoSIntegration, QoSScore
from k1.fabric.policy.security_context import SecurityCheckResult, SecurityContext

# Avoid circular import: ScoredCandidate is in provider_selector.py.
# Import at module level since provider_selector does NOT import policy_engine.
from k1.fabric.provider_resolution.provider_selector import ScoredCandidate
from k1.fabric.types import (
    AgentContract,
    CapabilityContract,
    CapabilityRequest,
    PolicyResult,
    PromptContract,
    ProviderConfig,
    WorkflowContract,
)

logger = logging.getLogger(__name__)

# Type alias (matches resolver.py)
ContractUnion = Union[CapabilityContract, AgentContract, PromptContract, WorkflowContract]

# Base relevance score for all candidates
_BASE_RELEVANCE = 1.0


class PolicyEngine:
    """
    Composite policy evaluator (3.2.5).

    Composes Security (hard gate), Affective (soft), Cognitive (soft),
    and QoS (soft) dimensions into a unified evaluation that the
    Resolver (3.1.5) consumes via the ``PolicyEnginePort`` Protocol.

    Each candidate provider is evaluated independently.  Security
    failures produce allowed=False immediately.  The three soft
    dimensions contribute additive scores to the composite.

    Usage::

        engine = PolicyEngine(
            security=SecurityContext(),
            affective=AffectiveRouting(state_reader=reader),
            cognitive=CognitiveLoadRouting(state_reader=reader),
            qos=QoSIntegration(),
        )
        scored = engine.evaluate(candidates, contract, request)
    """

    __slots__ = ("_security", "_affective", "_cognitive", "_qos", "_tools_granted")

    def __init__(
        self,
        *,
        security: SecurityContext,
        affective: Optional[AffectiveRouting] = None,
        cognitive: Optional[CognitiveLoadRouting] = None,
        qos: Optional[QoSIntegration] = None,
        tools_granted: Optional[FrozenSet[str]] = None,
    ) -> None:
        """
        Args:
            security: SecurityContext instance (REQUIRED, hard gate).
            affective: Optional AffectiveRouting instance.
                If None, affective dimension returns 0.0.
            cognitive: Optional CognitiveLoadRouting instance.
                If None, cognitive dimension returns 0.0.
            qos: Optional QoSIntegration instance.
                If None, QoS dimension returns 0.0.
            tools_granted: Optional frozen set of allowed capability names
                for sub-agent tool scoping.  Passed to SecurityContext.
        """
        if security is None:
            raise ValueError("SecurityContext is required (hard gate)")
        self._security = security
        self._affective = affective
        self._cognitive = cognitive
        self._qos = qos
        self._tools_granted = tools_granted

    # ======================================================================
    # PolicyEnginePort Protocol method
    # ======================================================================

    def evaluate(
        self,
        candidates: List[ProviderConfig],
        contract: ContractUnion,
        request: CapabilityRequest,
    ) -> List[ScoredCandidate]:
        """
        Evaluate all four policy dimensions for each candidate.

        This method satisfies the ``PolicyEnginePort`` Protocol used by
        Resolver (3.1.5).

        Steps per candidate:
          1. SecurityContext.evaluate() -- hard gate
          2. If security passes:
             a. AffectiveRouting.score() (request-level, computed once)
             b. CognitiveLoadRouting.score() (request-level, computed once)
             c. QoSIntegration.score() (per-provider)
          3. Compose: final_score = base + affective + cognitive + qos

        Args:
            candidates: List of matched ProviderConfig instances.
            contract: The capability contract being fulfilled.
            request: The original capability request.

        Returns:
            List of ScoredCandidates, one per input candidate.
            Rejected candidates have allowed=False, score=0.0.
        """
        start = time.perf_counter()
        success = True
        results: List[ScoredCandidate] = []
        try:
            # Compute request-level soft scores ONCE (same for all candidates)
            affective_score = self._eval_affective(request)
            cognitive_score = self._eval_cognitive(request)

            for cfg in candidates:
                scored = self._evaluate_candidate(
                    cfg, contract, request, affective_score, cognitive_score
                )
                results.append(scored)

            return results
        except Exception as exc:
            success = False
            logger.error("Policy evaluation error: %s", exc, exc_info=True)
            raise
        finally:
            duration_s = time.perf_counter() - start
            try:
                get_default_metrics().observe_policy_evaluation(duration_s)
            except Exception:
                logger.warning("Failed to record policy evaluation metric", exc_info=True)
            try:
                allowed_count = sum(1 for r in results if r.policy_result.allowed) if success else 0
                get_fabric_logger().policy_check(
                    trace_id=request.trace_id,
                    request_id=request.request_id,
                    capability_name=request.capability_name,
                    duration_ms=round(duration_s * 1000.0, 3),
                    success=success,
                    candidate_count=len(candidates),
                    allowed_count=allowed_count,
                )
            except Exception:
                logger.warning("Failed to record policy structured log", exc_info=True)

    # ======================================================================
    # Internal: per-candidate evaluation
    # ======================================================================

    def _evaluate_candidate(
        self,
        cfg: ProviderConfig,
        contract: ContractUnion,
        request: CapabilityRequest,
        affective_score: AffectiveScore,
        cognitive_score: CognitiveScore,
    ) -> ScoredCandidate:
        """Evaluate a single candidate through all 4 dimensions."""
        reasons: List[str] = []

        # --- Dimension 1: Security (hard gate) ---
        sec_result = self._eval_security(request, contract)
        if not sec_result.allowed:
            reasons.extend(sec_result.reasons)
            return ScoredCandidate(
                provider_config=cfg,
                contract=contract,
                policy_result=PolicyResult(
                    allowed=False,
                    score=0.0,
                    reasons=reasons,
                ),
            )
        reasons.extend(sec_result.reasons)

        # --- Dimension 2: Affective (soft, request-level) ---
        reasons.append(f"affective={affective_score.score:.4f}({affective_score.reason})")

        # --- Dimension 3: Cognitive (soft, request-level) ---
        reasons.append(f"cognitive={cognitive_score.score:.4f}({cognitive_score.reason})")

        # --- Dimension 4: QoS (soft, per-provider) ---
        qos_score = self._eval_qos(request, cfg)
        reasons.append(f"qos={qos_score.score:.4f}({qos_score.reason})")

        # --- Composite score ---
        final = _BASE_RELEVANCE + affective_score.score + cognitive_score.score + qos_score.score
        final = round(final, 4)

        return ScoredCandidate(
            provider_config=cfg,
            contract=contract,
            policy_result=PolicyResult(
                allowed=True,
                score=final,
                reasons=reasons,
            ),
        )

    # ======================================================================
    # Dimension wrappers (fault-isolated)
    # ======================================================================

    def _eval_security(
        self, request: CapabilityRequest, contract: ContractUnion
    ) -> SecurityCheckResult:
        """Run security hard gate.  Catches unexpected errors as rejection."""
        try:
            return self._security.evaluate(request, contract, tools_granted=self._tools_granted)
        except Exception as exc:
            logger.error("SecurityContext error: %s", exc, exc_info=True)
            return SecurityCheckResult(
                allowed=False,
                reasons=[f"security_error: {exc}"],
            )

    def _eval_affective(self, request: CapabilityRequest) -> AffectiveScore:
        """Run affective soft score.  Returns neutral on error or missing."""
        if self._affective is None:
            return AffectiveScore(score=0.0, reason="no_affective_router")
        try:
            return self._affective.score(request)
        except Exception as exc:
            logger.warning("AffectiveRouting error: %s", exc, exc_info=True)
            return AffectiveScore(score=0.0, reason=f"error: {exc}")

    def _eval_cognitive(self, request: CapabilityRequest) -> CognitiveScore:
        """Run cognitive soft score.  Returns neutral on error or missing."""
        if self._cognitive is None:
            return CognitiveScore(score=0.0, reason="no_cognitive_router")
        try:
            return self._cognitive.score(request)
        except Exception as exc:
            logger.warning("CognitiveLoadRouting error: %s", exc, exc_info=True)
            return CognitiveScore(score=0.0, reason=f"error: {exc}")

    def _eval_qos(self, request: CapabilityRequest, cfg: ProviderConfig) -> QoSScore:
        """Run QoS soft score per-provider.  Returns neutral on error or missing."""
        if self._qos is None:
            return QoSScore(score=0.0, reason="no_qos_integration")
        try:
            # Extract cost/latency from provider config metadata.
            # ProviderConfig has max_execution_ms; use as avg_latency proxy.
            avg_latency_ms = cfg.max_execution_ms if cfg.max_execution_ms > 0 else None
            # Cost is not in ProviderConfig yet; pass None.
            # Future: extract from contract pricing metadata.
            return self._qos.score(
                request,
                cost_per_call=None,
                avg_latency_ms=avg_latency_ms,
            )
        except Exception as exc:
            logger.warning("QoSIntegration error: %s", exc, exc_info=True)
            return QoSScore(score=0.0, reason=f"error: {exc}")
