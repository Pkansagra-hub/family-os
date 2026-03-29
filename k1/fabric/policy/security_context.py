"""
k1.fabric.policy.security_context -- SecurityContext hard gate (3.2.1) and
MetaOperationValidator (4.5.5).

The FIRST check in every policy evaluation.  If it fails, the
provider candidate is immediately rejected -- no soft scoring runs.

Three checks (SecurityContext 3.2.1):
  1. Safety band access:  ``user_band >= contract.safety_band_min``
     Band ordering: GREEN < AMBER < RED < CRISIS.
  2. Sub-agent tool scoping:  if ``tools_granted`` is provided,
     ``capability_name`` must be in the set.
  3. Rate limiting:  per-capability invocation limits (sliding window).

Five hard gates (MetaOperationValidator 4.5.5):
  1. Capability band gate: caller SafetyBand >= AMBER.
  2. Safety band inheritance: no escalation (GREEN caller cannot create AMBER agent).
  3. Restricted domain gate: domain cannot contain META, SECURITY, or ADMIN.
  4. Tool grant recursion gate: tools_granted cannot contain tool.write.* meta-tools.
  5. Agent depth gate: tools_granted cannot contain provider_type=AGENT tools.

Enforces FAB-06: safety band access is ALWAYS checked before execution.

Design:
  - Stateless except for optional rate-limit counters (SecurityContext).
  - MetaOperationValidator is stateless: pure function over inputs + registry.
  - Accept user_band from ``CapabilityRequest.safety_band`` and
    capability band from ``contract.safety_band_min``.
  - Returns ``SecurityCheckResult(allowed, reasons)``.
  - Thread-safe: rate-limit uses threading.Lock, registry has RLock.

References:
  - fabric_discussion.md Section 10 (Dimension 1: Security Context)
  - FAB-06 invariant
  - Epic 3.2.1, 4.5.5 in fabric-implementation-plan.md
  - meta-agent-creation-integration-proposal.md PART 1

Exports:
  SecurityContext            -- Hard-gate security evaluator (3.2.1)
  SecurityCheckResult        -- Frozen result dataclass
  SecurityContextError       -- Base exception
  AccessDeniedError          -- Safety/scope/rate check failed
  MetaOperationValidator     -- 5-gate meta-operation policy (4.5.5)
  RESTRICTED_DOMAINS         -- Frozen set of forbidden domain tags
  META_TOOL_PATTERN          -- Regex for tool.write.* meta-tools
"""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Protocol, Union, runtime_checkable

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


# ---------------------------------------------------------------------------
# 4.5.5 -- MetaOperationValidator constants
# ---------------------------------------------------------------------------

# Domains that cannot be assigned to dynamically created agents
RESTRICTED_DOMAINS: FrozenSet[str] = frozenset({"META", "SECURITY", "ADMIN"})

# Pattern matching meta-tools (tool.write.* prefix)
META_TOOL_PATTERN = re.compile(r"^tool\.write\.")

# Minimum caller band required for build_agent
_META_OP_MIN_BAND = SafetyBand.AMBER.value


# ---------------------------------------------------------------------------
# 4.5.5 -- Registry lookup protocol (structural subtyping)
# ---------------------------------------------------------------------------


@runtime_checkable
class RegistryLookupLike(Protocol):
    """
    Minimal protocol for registry lookup in MetaOperationValidator.

    Satisfied by CapabilityRegistry (2.2.1). Only needs lookup()
    to check provider_type for gate 5 (agent depth).
    """

    def lookup(self, name: str) -> Any: ...


# ---------------------------------------------------------------------------
# 4.5.5 -- MetaOperationValidator
# ---------------------------------------------------------------------------


class MetaOperationValidator:
    """
    5-gate meta-operation security policy (4.5.5).

    Validates that a dynamic agent creation request satisfies all
    security constraints before allowing the agent to be composed.

    5 hard gates (ANY fail -> SecurityCheckResult(allowed=False)):
      1. Capability band gate: caller SafetyBand >= AMBER
      2. Safety band inheritance: agent cannot exceed caller band
      3. Restricted domain gate: no META, SECURITY, ADMIN domains
      4. Tool grant recursion gate: no tool.write.* in tools_granted
      5. Agent depth gate: no provider_type=AGENT tools (depth=1 only)

    Satisfies SecurityGateLike protocol from agent_builder.py (4.5.2).

    Constructor injection:
      registry: CapabilityRegistry (2.2.1) for gate 5 provider_type lookup.

    Thread-safe: validate_meta_operation is a pure function over inputs
    plus registry lookups (registry has RLock).

    References:
      - fabric-implementation-plan.md Issue 4.5.5
      - meta-agent-creation-integration-proposal.md (security gates)
    """

    __slots__ = ("_registry",)

    def __init__(self, registry: RegistryLookupLike) -> None:
        """
        Args:
            registry: CapabilityRegistry (2.2.1) for provider_type lookup.
        """
        self._registry = registry

    # -- Public API (SecurityGateLike) ------------------------------------

    def validate_meta_operation(
        self,
        request_band: str,
        agent_spec: Dict[str, Any],
    ) -> SecurityCheckResult:
        """
        Validate a meta-operation (dynamic agent creation) against 5 hard gates.

        ALL gates are evaluated; all violations are collected before returning.
        If ANY gate fails, returns SecurityCheckResult(allowed=False, reasons=[...]).

        Args:
            request_band: Caller's current safety band string (e.g., "AMBER").
            agent_spec: Agent specification dict from BuildAgentHandler._parse_inputs().
                Expected keys: safety_band_min, domain, tools_granted.

        Returns:
            SecurityCheckResult with allowed=True if all gates pass,
            or allowed=False with list of violation reasons.
        """
        reasons: List[str] = []

        # Gate 1: Capability band gate -- caller must be >= AMBER
        self._check_capability_band(request_band, reasons)

        # Gate 2: Safety band inheritance -- no escalation
        spec_band = agent_spec.get("safety_band_min", SafetyBand.GREEN.value)
        self._check_band_inheritance(request_band, spec_band, reasons)

        # Gate 3: Restricted domain gate
        domains = agent_spec.get("domain", [])
        self._check_restricted_domains(domains, reasons)

        # Gate 4: Tool grant recursion gate
        tools_granted = agent_spec.get("tools_granted", [])
        self._check_tool_grant_recursion(tools_granted, reasons)

        # Gate 5: Agent depth gate
        self._check_agent_depth(tools_granted, reasons)

        if reasons:
            return SecurityCheckResult(allowed=False, reasons=reasons)

        return SecurityCheckResult(allowed=True, reasons=["meta_operation_allowed"])

    # -- Gate implementations (private) ------------------------------------

    def _check_capability_band(
        self,
        request_band: str,
        reasons: List[str],
    ) -> None:
        """
        Gate 1: Caller SafetyBand must be >= AMBER.

        tool.write.build_agent is an AMBER-band capability.
        GREEN callers cannot invoke meta-operations.
        """
        caller_level = _BAND_ORDER.get(request_band, -1)
        required_level = _BAND_ORDER.get(_META_OP_MIN_BAND, 1)

        if caller_level < required_level:
            reasons.append(
                f"capability_band_denied: caller band {request_band} "
                f"< required {_META_OP_MIN_BAND} for meta-operations"
            )

    def _check_band_inheritance(
        self,
        request_band: str,
        spec_band: str,
        reasons: List[str],
    ) -> None:
        """
        Gate 2: Agent safety_band_min cannot exceed caller band.

        Prevents privilege escalation: a GREEN caller cannot create
        an AMBER agent, an AMBER caller cannot create a RED agent.
        """
        caller_level = _BAND_ORDER.get(request_band, -1)
        spec_level = _BAND_ORDER.get(spec_band, 0)

        if spec_level > caller_level:
            reasons.append(
                f"band_escalation_denied: agent band {spec_band} "
                f"exceeds caller band {request_band}"
            )

    def _check_restricted_domains(
        self,
        domains: List[str],
        reasons: List[str],
    ) -> None:
        """
        Gate 3: Agent domain cannot contain META, SECURITY, or ADMIN.

        Prevents creation of meta-agents that could recursively
        create more agents or bypass security controls.
        """
        for domain in domains:
            if domain.upper() in RESTRICTED_DOMAINS:
                reasons.append(
                    f"restricted_domain_denied: domain {domain!r} is forbidden "
                    f"for dynamically created agents"
                )

    def _check_tool_grant_recursion(
        self,
        tools_granted: List[str],
        reasons: List[str],
    ) -> None:
        """
        Gate 4: tools_granted cannot contain tool.write.* meta-tools.

        Prevents recursive agent creation: a dynamically created agent
        cannot itself create other agents or invoke write meta-tools.
        """
        for tool in tools_granted:
            if META_TOOL_PATTERN.match(tool):
                reasons.append(
                    f"tool_recursion_denied: {tool!r} is a meta-tool "
                    f"(tool.write.*) and cannot be granted to created agents"
                )

    def _check_agent_depth(
        self,
        tools_granted: List[str],
        reasons: List[str],
    ) -> None:
        """
        Gate 5: tools_granted cannot contain provider_type=AGENT tools.

        Enforces depth=1 (leaf nodes only). Dynamically created agents
        can only invoke tool/workflow capabilities, not other agents.
        Checked via Registry.lookup() for provider_type.
        """
        for tool in tools_granted:
            contract = self._registry.lookup(tool)
            if contract is not None:
                provider_type = getattr(contract, "provider_type", "")
                if provider_type == "AGENT":
                    reasons.append(
                        f"agent_depth_denied: {tool!r} has provider_type=AGENT; "
                        f"created agents cannot invoke other agents (depth=1)"
                    )

    # -- Repr --------------------------------------------------------------

    def __repr__(self) -> str:
        return f"MetaOperationValidator(registry={self._registry!r})"
