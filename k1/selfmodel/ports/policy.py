"""``IPolicyPort`` — gate evaluator backed by SituationFrame + ConstitutionRules.

Implementation lands in M2 (``service/policy_evaluator.py``). The
``ConciergePolicyGate`` adapter wraps this port as step-0 of
``ToolDispatcher.dispatch``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from k1.selfmodel.contracts.policy import PolicyRequest, PolicyVerdict

__all__ = ["IPolicyPort"]


@runtime_checkable
class IPolicyPort(Protocol):
    """Issue a verdict for an actor + tool + args against the active rules."""

    def evaluate(self, request: PolicyRequest) -> PolicyVerdict:
        """Return a verdict.

        Empty-Set Invariant E6: any tool not in the actor's
        ``Capabilities.can_do`` results in ``DENY``.
        """
        ...

    def override_stale(self, pending_id: str, reason: str = "") -> PolicyVerdict:
        """Re-evaluate a previously DEFER_OFFLINE/stale verdict with override.

        Audit-logged; intended for the ``proceed_with_stale(...)`` kernel
        API entry point.
        """
        ...
