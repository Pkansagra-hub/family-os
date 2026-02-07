"""
k1.fabric.policy.security_context -- SecurityContext hard gate (3.2.1).

The FIRST check in every policy evaluation.  If it fails, the
provider candidate is immediately rejected -- no soft scoring runs.

Three checks:
  1. Safety band access:  ``user_band >= contract.safety_band_min``
     Band ordering: GREEN < AMBER < RED < CRISIS.
  2. Sub-agent tool scoping:  if ``tools_granted`` is provided,
     ``capability_name`` must be in the set.
  3. Rate limiting:  per-capability invocation limits (sliding window).

Enforces FAB-06: safety band access is ALWAYS checked before execution.

Design:
  - Stateless except for optional rate-limit counters.
  - Accept user_band from ``CapabilityRequest.safety_band`` and
    capability band from ``contract.safety_band_min``.
  - Returns ``SecurityCheckResult(allowed, reasons)``.
  - Thread-safe: rate-limit uses threading.Lock.

References:
  - fabric_discussion.md Section 10 (Dimension 1: Security Context)
  - FAB-06 invariant
  - Epic 3.2.1 in fabric-implementation-plan.md

Exports:
  SecurityContext       -- Hard-gate security evaluator
  SecurityCheckResult   -- Frozen result dataclass
  SecurityContextError  -- Base exception
  AccessDeniedError     -- Safety/scope/rate check failed
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Union

from k1.fabric.types import (
    AgentContract,
    CapabilityContract,
    CapabilityRequest,
    PromptContract,
    SafetyBand,
    WorkflowContract,
)

logger = logging.getLogger(__name__)

# Type alias
ContractUnion = Union[CapabilityContract, AgentContract, PromptContract, WorkflowContract]

# Safety band ordering map (higher = more privileged)
_BAND_ORDER: Dict[str, int] = {
    SafetyBand.GREEN.value: 0,
    SafetyBand.AMBER.value: 1,
    SafetyBand.RED.value: 2,
    SafetyBand.CRISIS.value: 3,
}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SecurityCheckResult:
    """
    Outcome of a SecurityContext evaluation.

    Attributes:
        allowed: True if all checks passed, False if any hard-gate failed.
        reasons: Human-readable list of check outcomes / rejection reasons.
    """

    allowed: bool = True
    reasons: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class SecurityContextError(Exception):
    """Base exception for SecurityContext operations."""


class AccessDeniedError(SecurityContextError):
    """Raised when a hard-gate check fails."""

    def __init__(self, check: str, detail: str) -> None:
        self.check = check
        self.detail = detail
        super().__init__(f"Access denied [{check}]: {detail}")


# ---------------------------------------------------------------------------
# SecurityContext
# ---------------------------------------------------------------------------


class SecurityContext:
    """
    Hard-gate security evaluation (3.2.1).

    Evaluates three security dimensions for a capability request:
      1. Safety band access (FAB-06)
      2. Sub-agent tool-scope enforcement
      3. Per-capability rate limiting (optional)

    Usage::

        sec = SecurityContext(rate_limits={"tool.execute.weather": 60})
        result = sec.evaluate(request, contract)
        if not result.allowed:
            # reject immediately
    """

    __slots__ = ("_rate_limits", "_rate_counters", "_lock")

    def __init__(
        self,
        *,
        rate_limits: Optional[Dict[str, int]] = None,
    ) -> None:
        """
        Args:
            rate_limits: Optional per-capability invocation limits.
                Maps capability_name -> max invocations per 60-second window.
                If None or empty, rate limiting is disabled.
        """
        self._rate_limits: Dict[str, int] = dict(rate_limits) if rate_limits else {}
        self._rate_counters: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    # ======================================================================
    # Public API
    # ======================================================================

    def evaluate(
        self,
        request: CapabilityRequest,
        contract: ContractUnion,
        *,
        tools_granted: Optional[FrozenSet[str]] = None,
    ) -> SecurityCheckResult:
        """
        Run all hard-gate checks.  Returns immediately on first failure.

        Args:
            request: The capability request (contains user safety_band).
            contract: The capability contract (contains safety_band_min).
            tools_granted: If provided, the sub-agent's allowed capability set.
                When None, tool-scope check is skipped (caller is not a sub-agent).

        Returns:
            SecurityCheckResult with allowed=True/False and reasons.
        """
        reasons: List[str] = []

        # --- Check 1: Safety band (FAB-06) ---
        band_result = self.check_band(request.safety_band, self._contract_band(contract))
        reasons.append(band_result.reasons[0] if band_result.reasons else "band_check_ok")
        if not band_result.allowed:
            return SecurityCheckResult(allowed=False, reasons=reasons)

        # --- Check 2: Sub-agent tool scoping ---
        if tools_granted is not None:
            scope_result = self.check_tool_scope(request.capability_name, tools_granted)
            reasons.append(scope_result.reasons[0] if scope_result.reasons else "scope_check_ok")
            if not scope_result.allowed:
                return SecurityCheckResult(allowed=False, reasons=reasons)

        # --- Check 3: Rate limiting ---
        if self._rate_limits:
            rate_result = self.check_rate_limit(request.capability_name)
            reasons.append(rate_result.reasons[0] if rate_result.reasons else "rate_check_ok")
            if not rate_result.allowed:
                return SecurityCheckResult(allowed=False, reasons=reasons)

        return SecurityCheckResult(allowed=True, reasons=reasons)

    def check_band(
        self,
        user_band: str,
        capability_band_min: str,
    ) -> SecurityCheckResult:
        """
        Verify ``user_band >= capability_band_min``.

        Band ordering: GREEN(0) < AMBER(1) < RED(2) < CRISIS(3).

        Args:
            user_band: The user's current safety band string.
            capability_band_min: The capability's minimum required band.

        Returns:
            SecurityCheckResult.
        """
        user_level = _BAND_ORDER.get(user_band)
        cap_level = _BAND_ORDER.get(capability_band_min)

        if user_level is None:
            return SecurityCheckResult(
                allowed=False,
                reasons=[f"invalid user_band: '{user_band}'"],
            )
        if cap_level is None:
            return SecurityCheckResult(
                allowed=False,
                reasons=[f"invalid capability_band_min: '{capability_band_min}'"],
            )

        if user_level >= cap_level:
            return SecurityCheckResult(
                allowed=True,
                reasons=[f"band_ok: {user_band}>={capability_band_min}"],
            )
        return SecurityCheckResult(
            allowed=False,
            reasons=[f"band_denied: {user_band}<{capability_band_min}"],
        )

    def check_tool_scope(
        self,
        capability_name: str,
        tools_granted: FrozenSet[str],
    ) -> SecurityCheckResult:
        """
        Verify that ``capability_name`` is in the sub-agent's allowed set.

        Args:
            capability_name: The capability being requested.
            tools_granted: Set of capabilities the sub-agent is allowed to invoke.

        Returns:
            SecurityCheckResult.
        """
        if capability_name in tools_granted:
            return SecurityCheckResult(
                allowed=True,
                reasons=[f"scope_ok: '{capability_name}' in tools_granted"],
            )
        return SecurityCheckResult(
            allowed=False,
            reasons=[f"scope_denied: '{capability_name}' not in tools_granted"],
        )

    def check_rate_limit(
        self,
        capability_name: str,
    ) -> SecurityCheckResult:
        """
        Enforce per-capability invocation rate limits.

        Uses a 60-second sliding window.  If ``capability_name`` has no
        configured limit, returns allowed=True immediately.

        Args:
            capability_name: The capability being invoked.

        Returns:
            SecurityCheckResult.
        """
        limit = self._rate_limits.get(capability_name)
        if limit is None:
            return SecurityCheckResult(
                allowed=True,
                reasons=["rate_ok: no limit configured"],
            )

        now = time.monotonic()
        window_start = now - 60.0

        with self._lock:
            timestamps = self._rate_counters.get(capability_name, [])
            # Prune entries outside the window
            timestamps = [t for t in timestamps if t > window_start]

            if len(timestamps) >= limit:
                self._rate_counters[capability_name] = timestamps
                return SecurityCheckResult(
                    allowed=False,
                    reasons=[
                        f"rate_denied: '{capability_name}' "
                        f"hit {limit}/60s limit ({len(timestamps)} invocations)"
                    ],
                )

            timestamps.append(now)
            self._rate_counters[capability_name] = timestamps

        return SecurityCheckResult(
            allowed=True,
            reasons=[f"rate_ok: '{capability_name}' " f"{len(timestamps)}/{limit} in window"],
        )

    # ======================================================================
    # Internal helpers
    # ======================================================================

    @staticmethod
    def _contract_band(contract: ContractUnion) -> str:
        """
        Extract ``safety_band_min`` from any contract type.

        PromptContract may not have safety_band_min; default to GREEN.
        """
        return getattr(contract, "safety_band_min", SafetyBand.GREEN.value)
