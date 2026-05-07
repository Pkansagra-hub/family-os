"""Test-only stub adapters bundle (M0.E3.I2).

These doubles let higher-level services be unit-tested without pulling
in production crypto / bridge / prompt machinery. They are NOT shipped
in the runtime package — they live under ``tests/`` on purpose.

Stubs with a corresponding port (``ICredentialPort``, ``IPolicyPort``)
are structurally typed so ``isinstance(stub, IPort)`` passes.
The remaining stubs (capsule renderer, citation wrapper, amendment
sync) target adapters that ship in M4; they are simple recording /
passthrough doubles for now.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from k1.selfmodel.contracts.policy import (
    PolicyDecision,
    PolicyRequest,
    PolicyVerdict,
    RiskClass,
)
from k1.selfmodel.ports.identity import (
    CredentialPresentation,
    IdentityTier,
    VerificationResult,
)

__all__ = [
    "StubCredentialVerifier",
    "NullPolicyGate",
    "InMemoryAmendmentSync",
    "RecordingCapsuleRenderer",
    "PassthroughCitationWrapper",
]


# ---------------------------------------------------------------------
# Credential verifier — satisfies ``ICredentialPort``.
# ---------------------------------------------------------------------


@dataclass
class StubCredentialVerifier:
    """Always-accept verifier; promotes to ``promoted_to_tier``."""

    promoted_to_tier: IdentityTier = IdentityTier.PIN_VERIFIED
    accept: bool = True
    calls: list[tuple[str, CredentialPresentation]] = field(default_factory=list)

    def verify(self, profile_id: str, credential: CredentialPresentation) -> VerificationResult:
        self.calls.append((profile_id, credential))
        if not self.accept:
            return VerificationResult(accepted=False, reason="stub_reject")
        return VerificationResult(
            accepted=True, promoted_to_tier=self.promoted_to_tier, reason="stub_accept"
        )

    def max_tier_for(self, kind: str) -> IdentityTier:
        return self.promoted_to_tier


# ---------------------------------------------------------------------
# Policy gate — satisfies ``IPolicyPort``.
# ---------------------------------------------------------------------


@dataclass
class NullPolicyGate:
    """Always-ALLOW policy gate; records every request."""

    requests: list[PolicyRequest] = field(default_factory=list)

    def evaluate(self, request: PolicyRequest) -> PolicyVerdict:
        self.requests.append(request)
        return PolicyVerdict(decision=PolicyDecision.ALLOW, risk=RiskClass.LOW)

    def override_stale(self, pending_id: str, reason: str = "") -> PolicyVerdict:
        return PolicyVerdict(decision=PolicyDecision.ALLOW, risk=RiskClass.LOW)


# ---------------------------------------------------------------------
# Amendment sync — adapter port lands in M4.E3; stub records calls.
# ---------------------------------------------------------------------


@dataclass
class InMemoryAmendmentSync:
    """Records ``submit_delta`` calls without contacting a bridge."""

    submitted: list[dict[str, Any]] = field(default_factory=list)
    receipt_prefix: str = "stub-receipt-"

    def submit_delta(self, body: dict[str, Any], *, band: str = "GREEN") -> str:
        if band == "BLACK":
            from k1.selfmodel.contracts.privacy import BlackBandLeakError

            raise BlackBandLeakError("stub: BLACK refused at adapter")
        self.submitted.append({"body": body, "band": band})
        return f"{self.receipt_prefix}{len(self.submitted)}"


# ---------------------------------------------------------------------
# Capsule renderer — adapter ships in M4.E1; stub records inputs.
# ---------------------------------------------------------------------


@dataclass
class RecordingCapsuleRenderer:
    """Captures every capsule rendered for assertion in tests."""

    rendered: list[Any] = field(default_factory=list)

    def render(self, capsule: Any) -> str:
        self.rendered.append(capsule)
        return f"<capsule:{getattr(capsule, 'actor_block', '')!s}>"


# ---------------------------------------------------------------------
# Citation wrapper — adapter ships in M4.E2; stub passes recall through.
# ---------------------------------------------------------------------


@dataclass
class PassthroughCitationWrapper:
    """Returns the raw recall payload unchanged; records call counts."""

    calls: int = 0

    def wrap(self, raw_results: Any) -> Any:
        self.calls += 1
        return raw_results
