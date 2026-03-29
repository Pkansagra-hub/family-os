"""
k1.fabric.retrieval.hard_filter -- Pre-ranking elimination filter (4.1.2).

Three hard rules. ANY failure => capability ELIMINATED from the candidate set.
Survivors proceed to SoftRanker (4.1.3).

Rules:
  1. Safety Band:  ``contract.safety_band_min <= user_band``
  2. Availability:  NOT OFFLINE  (DEGRADED kept; penalised later by SoftRanker)
  3. Input Satisfiability:  MOST ``required_inputs`` satisfiable from
     ``params``, ``session_keys``, or ``planner_can_ask=True`` (relaxed check).

Filter is stateless -- all data passed in per call or read from
injected protocols.

Thread safety: Stateless; no mutable state. Safe for concurrent calls.

References:
  - fabric_discussion.md Section 8 (Retrieval Pipeline, step [2])
  - Epic 4.1.2 spec in fabric-implementation-plan.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Protocol

# ---------------------------------------------------------------------------
# Protocols -- declared locally to avoid circular imports
# ---------------------------------------------------------------------------


class IAvailabilitySource(Protocol):
    """
    Provides per-provider availability.

    Production: AvailabilityTracker (3.6.2) or CapabilityRegistry (2.2).
    Test: any object with a matching ``get_availability`` method.
    """

    def get_availability(self, contract_name: str) -> str:
        """
        Return availability string for *contract_name*.

        Returns 'ONLINE' if unknown / not tracked.
        """
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Safety band ordering (value = numeric level)
_BAND_ORDER: Dict[str, int] = {
    "GREEN": 0,
    "AMBER": 1,
    "RED": 2,
    "CRISIS": 3,
}

DEFAULT_SATISFIABILITY_THRESHOLD: float = 0.5
"""Fraction of required_inputs that must be satisfiable to keep a capability.

The plan says 'if MOST are satisfiable, keep it'. We interpret MOST as > 50%.
"""

# Availability values -- mirrored from k1.fabric.types.Availability
_OFFLINE = "OFFLINE"
_DEGRADED = "DEGRADED"
_ONLINE = "ONLINE"


# ---------------------------------------------------------------------------
# Rejection reasons (frozen strings for determinism / testability)
# ---------------------------------------------------------------------------

REASON_SAFETY_BAND = "safety_band"
REASON_OFFLINE = "offline"
REASON_INPUT_UNSATISFIABLE = "input_unsatisfiable"


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FilterCandidate:
    """
    Input to the hard filter -- one capability to evaluate.

    Callers construct this from a registry contract + runtime metadata.

    Attributes:
        contract_name: Canonical capability name.
        safety_band_min: Minimum safety band required (GREEN/AMBER/RED/CRISIS).
        availability: Current availability (ONLINE/DEGRADED/OFFLINE).
        required_input_names: Set of input names the capability requires.
        contract: Optional reference to the full contract object (opaque).
    """

    contract_name: str = ""
    safety_band_min: str = "GREEN"
    availability: str = _ONLINE
    required_input_names: FrozenSet[str] = field(default_factory=frozenset)
    contract: Any = None  # original contract, carried through for convenience

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_name": self.contract_name,
            "safety_band_min": self.safety_band_min,
            "availability": self.availability,
            "required_input_names": sorted(self.required_input_names),
        }


@dataclass(frozen=True)
class FilterResult:
    """
    Output of the hard filter for a single candidate.

    Attributes:
        contract_name: Capability name.
        passed: True if the candidate survived all hard rules.
        rejection_reason: If not passed, which rule eliminated it.
        contract: Opaque reference to the original contract (carried through).
    """

    contract_name: str = ""
    passed: bool = False
    rejection_reason: str = ""
    contract: Any = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "contract_name": self.contract_name,
            "passed": self.passed,
        }
        if self.rejection_reason:
            d["rejection_reason"] = self.rejection_reason
        return d


@dataclass(frozen=True)
class HardFilterConfig:
    """
    Configuration for the HardFilter.

    Attributes:
        satisfiability_threshold: Fraction of required_inputs that must be
            satisfiable (0.0 - 1.0).  Default 0.5 ('most').
        planner_can_ask: When True, count any unsatisfied input as
            potentially satisfiable by the Planner (relaxed mode).
            Default True per spec: 'Planner can ask'.
        check_safety: Enable/disable Rule 1.
        check_availability: Enable/disable Rule 2.
        check_inputs: Enable/disable Rule 3.
    """

    satisfiability_threshold: float = DEFAULT_SATISFIABILITY_THRESHOLD
    planner_can_ask: bool = True
    check_safety: bool = True
    check_availability: bool = True
    check_inputs: bool = True


# ---------------------------------------------------------------------------
# HardFilter
# ---------------------------------------------------------------------------


class HardFilter:
    """
    Eliminates non-candidate capabilities before soft ranking.

    Three independent hard rules are applied in order (short-circuit on
    first failure):

    1. **Safety band** -- contract.safety_band_min must be <= user band.
    2. **Availability** -- must NOT be OFFLINE.
    3. **Input satisfiability** -- enough required_inputs must be satisfiable
       from known sources (params, session keys, planner ask).

    The filter is stateless: all runtime context is passed per call.

    Constructor Args:
        config: Optional HardFilterConfig.
    """

    __slots__ = ("_config",)

    def __init__(self, config: Optional[HardFilterConfig] = None) -> None:
        self._config = config or HardFilterConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def filter(
        self,
        candidates: List[FilterCandidate],
        *,
        user_band: str = "GREEN",
        available_param_names: Optional[FrozenSet[str]] = None,
        session_keys: Optional[FrozenSet[str]] = None,
    ) -> List[FilterResult]:
        """
        Apply all three hard rules to every candidate.

        Args:
            candidates: List of FilterCandidate to evaluate.
            user_band: Caller's current safety band (default GREEN).
            available_param_names: Input names satisfiable from request params.
            session_keys: Input names satisfiable from SessionState sections.

        Returns:
            List of FilterResult (one per candidate, same order).
        """
        param_names = available_param_names or frozenset()
        sess_keys = session_keys or frozenset()
        results: List[FilterResult] = []

        for c in candidates:
            reason = self._evaluate(c, user_band, param_names, sess_keys)
            results.append(
                FilterResult(
                    contract_name=c.contract_name,
                    passed=(reason == ""),
                    rejection_reason=reason,
                    contract=c.contract,
                )
            )
        return results

    def filter_passed(
        self,
        candidates: List[FilterCandidate],
        *,
        user_band: str = "GREEN",
        available_param_names: Optional[FrozenSet[str]] = None,
        session_keys: Optional[FrozenSet[str]] = None,
    ) -> List[FilterCandidate]:
        """
        Convenience: return only candidates that pass all three rules.

        Same args as ``filter()``.
        """
        results = self.filter(
            candidates,
            user_band=user_band,
            available_param_names=available_param_names,
            session_keys=session_keys,
        )
        passed_names = {r.contract_name for r in results if r.passed}
        return [c for c in candidates if c.contract_name in passed_names]

    @property
    def config(self) -> HardFilterConfig:
        return self._config

    def __repr__(self) -> str:
        return (
            f"HardFilter(safety={self._config.check_safety}, "
            f"avail={self._config.check_availability}, "
            f"inputs={self._config.check_inputs}, "
            f"threshold={self._config.satisfiability_threshold})"
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _evaluate(
        self,
        candidate: FilterCandidate,
        user_band: str,
        param_names: FrozenSet[str],
        session_keys: FrozenSet[str],
    ) -> str:
        """
        Evaluate a single candidate against all rules.

        Returns:
            Empty string if passed, else the rejection reason constant.
        """
        # Rule 1: Safety band
        if self._config.check_safety:
            if not self._check_safety_band(candidate.safety_band_min, user_band):
                return REASON_SAFETY_BAND

        # Rule 2: Availability
        if self._config.check_availability:
            if not self._check_availability(candidate.availability):
                return REASON_OFFLINE

        # Rule 3: Input satisfiability
        if self._config.check_inputs:
            if not self._check_inputs(
                candidate.required_input_names,
                param_names,
                session_keys,
            ):
                return REASON_INPUT_UNSATISFIABLE

        return ""

    # -- Rule 1 ----------------------------------------------------------

    @staticmethod
    def _check_safety_band(capability_band_min: str, user_band: str) -> bool:
        """
        Return True if the user's band is >= the capability's minimum.

        Band ordering: GREEN(0) < AMBER(1) < RED(2) < CRISIS(3).

        E.g. user=GREEN, cap_min=AMBER => GREEN(0) >= AMBER(1)? No => FAIL.
             user=CRISIS, cap_min=RED  => CRISIS(3) >= RED(2)? Yes => PASS.
        """
        user_level = _BAND_ORDER.get(user_band, 0)
        cap_level = _BAND_ORDER.get(capability_band_min, 0)
        return user_level >= cap_level

    # -- Rule 2 ----------------------------------------------------------

    @staticmethod
    def _check_availability(availability: str) -> bool:
        """Return True if not OFFLINE."""
        return availability != _OFFLINE

    # -- Rule 3 ----------------------------------------------------------

    def _check_inputs(
        self,
        required: FrozenSet[str],
        param_names: FrozenSet[str],
        session_keys: FrozenSet[str],
    ) -> bool:
        """
        Return True if enough required inputs are satisfiable.

        An input is 'satisfiable' if it is in param_names, session_keys,
        or ``planner_can_ask`` is True (relaxed).

        Threshold: at least ``satisfiability_threshold`` fraction of
        required_inputs must be satisfiable.
        """
        if not required:
            return True  # no requirements => trivially satisfied

        known = param_names | session_keys
        satisfied = 0
        for inp_name in required:
            if inp_name in known:
                satisfied += 1
            elif self._config.planner_can_ask:
                satisfied += 1
            # else: not satisfiable

        ratio = satisfied / len(required)
        return ratio >= self._config.satisfiability_threshold
