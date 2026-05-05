"""Structural-typing tests for the 6 ``Protocol`` ports of k1.selfmodel.

Acceptance for M0.E2.I1: trivial stubs that implement the methods are
recognized via ``isinstance(stub, IPort)`` (``@runtime_checkable``).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import pytest

from k1.selfmodel.contracts.constitution import (
    AmendmentProposal,
    AmendmentStatus,
    ConstitutionDiff,
    ConstitutionSnapshot,
    SigningProof,
)
from k1.selfmodel.contracts.family_model import FamilySelfModelSnapshot
from k1.selfmodel.contracts.policy import (
    PolicyDecision,
    PolicyRequest,
    PolicyVerdict,
    RiskClass,
)
from k1.selfmodel.contracts.self_model import K1SelfModelSnapshot, LayerObservation
from k1.selfmodel.contracts.situation import (
    ApplicableRules,
    Capabilities,
    ProjectedSelf,
    RelationsSubset,
    SituationFrame,
    Visibility,
)
from k1.selfmodel.ports import (
    CredentialPresentation,
    DeviceContext,
    IConstitutionPort,
    ICredentialPort,
    IdentitySession,
    IdentityTier,
    IIdentityPort,
    IPolicyPort,
    ISelfFamilyPort,
    ISituationFramePort,
    ProfileSummary,
    VerificationResult,
)

# -- Stubs --------------------------------------------------------------


class _IdentityStub:
    def list_eligible_profiles(self, device: DeviceContext) -> tuple[ProfileSummary, ...]:
        return ()

    def start_session(
        self,
        profile_id: str,
        device: DeviceContext,
        proof: CredentialPresentation | None = None,
    ) -> IdentitySession:
        return IdentitySession(
            session_token="t",
            profile_id=profile_id,
            tier=IdentityTier.ANONYMOUS,
            device_id=device.device_id,
        )

    def present_credential(
        self, session_token: str, credential: CredentialPresentation
    ) -> VerificationResult:
        return VerificationResult(accepted=False)

    def end_session(self, session_token: str) -> None:
        return None

    def get_session_tier(self, session_token: str) -> IdentityTier:
        return IdentityTier.ANONYMOUS


class _CredentialStub:
    def verify(self, profile_id: str, credential: CredentialPresentation) -> VerificationResult:
        return VerificationResult(accepted=False)

    def max_tier_for(self, kind: str) -> IdentityTier:
        return IdentityTier.ANONYMOUS


class _ConstitutionStub:
    def get_active(self) -> ConstitutionSnapshot:
        return ConstitutionSnapshot(
            constitution_id="c",
            version="v0",
            parent_version="",
            body={},
            signatures=(),
        )

    def get_diff(self, constitution_id: str, version_a: str, version_b: str) -> ConstitutionDiff:
        return ConstitutionDiff(
            constitution_id=constitution_id,
            from_version=version_a,
            to_version=version_b,
        )

    def propose(
        self,
        proposed_by: str,
        parent_version: str,
        body: dict[str, object],
    ) -> AmendmentProposal:
        return AmendmentProposal(
            amendment_id="a",
            constitution_id="c",
            parent_version=parent_version,
            proposed_by=proposed_by,
            body=body,
            status=AmendmentStatus.DRAFT,
        )

    def submit(self, amendment_id: str) -> AmendmentProposal:
        return AmendmentProposal(
            amendment_id=amendment_id,
            constitution_id="c",
            parent_version="",
            proposed_by="",
            body={},
            status=AmendmentStatus.PENDING,
        )

    def sign(self, amendment_id: str, proof: SigningProof) -> AmendmentProposal:
        return AmendmentProposal(
            amendment_id=amendment_id,
            constitution_id="c",
            parent_version="",
            proposed_by="",
            body={},
            status=AmendmentStatus.PENDING,
        )

    def decline(self, amendment_id: str, reason: str = "") -> AmendmentProposal:
        return AmendmentProposal(
            amendment_id=amendment_id,
            constitution_id="c",
            parent_version="",
            proposed_by="",
            body={},
            status=AmendmentStatus.REJECTED,
        )

    def list_pending(self) -> tuple[AmendmentProposal, ...]:
        return ()

    def list_history(self, status: AmendmentStatus | None = None) -> tuple[AmendmentProposal, ...]:
        return ()


class _SelfFamilyStub:
    def get_self(self, actor_id: str, T_ms: int, device_id: str) -> K1SelfModelSnapshot | None:
        return None

    def get_family_view(self, actor_id: str, T_ms: int, device_id: str) -> FamilySelfModelSnapshot:
        return FamilySelfModelSnapshot(
            family_space_id="fs",
            members=(),
            edges=(),
            routines=(),
        )

    def update_layer(self, layer: str, observation: LayerObservation) -> None:
        return None


class _SituationStub:
    def compose(
        self,
        actor_id: str,
        T_ms: int,
        device_id: str,
        situation_kind: str,
    ) -> SituationFrame:
        return SituationFrame(
            actor_id=actor_id,
            T_ms=T_ms,
            device_id=device_id,
            situation_kind=situation_kind,
            self_view=ProjectedSelf(actor_id=actor_id),
            relations=RelationsSubset(),
            rules=ApplicableRules(constitution_id="c", version="v0"),
            capabilities=Capabilities(),
            visibility=Visibility(),
        )


class _PolicyStub:
    def evaluate(self, request: PolicyRequest) -> PolicyVerdict:
        return PolicyVerdict(
            decision=PolicyDecision.DENY,
            risk=RiskClass.LOW,
            reasons=(),
        )

    def override_stale(self, pending_id: str, reason: str = "") -> PolicyVerdict:
        return PolicyVerdict(
            decision=PolicyDecision.DENY,
            risk=RiskClass.LOW,
            reasons=(),
        )


# -- Tests --------------------------------------------------------------


_PORTS: tuple[tuple[type, type], ...] = (
    (IIdentityPort, _IdentityStub),
    (ICredentialPort, _CredentialStub),
    (IConstitutionPort, _ConstitutionStub),
    (ISelfFamilyPort, _SelfFamilyStub),
    (ISituationFramePort, _SituationStub),
    (IPolicyPort, _PolicyStub),
)


@pytest.mark.parametrize(("port", "stub_cls"), _PORTS, ids=lambda v: getattr(v, "__name__", str(v)))
def test_port_is_runtime_checkable_protocol(port: type, stub_cls: type) -> None:
    # Protocol subclass
    assert issubclass(port, Protocol)  # type: ignore[arg-type]
    # @runtime_checkable
    assert getattr(port, "_is_runtime_protocol", False) is True


@pytest.mark.parametrize(("port", "stub_cls"), _PORTS, ids=lambda v: getattr(v, "__name__", str(v)))
def test_stub_satisfies_port_isinstance(port: type, stub_cls: type) -> None:
    assert isinstance(stub_cls(), port)


def test_empty_stub_does_not_satisfy_port() -> None:
    @runtime_checkable
    class _Marker(Protocol):
        def x(self) -> None: ...

    class _NoMethods:
        pass

    # Sanity: our negative pattern works.
    assert not isinstance(_NoMethods(), _Marker)
    # And none of the real ports accept an empty object.
    for port, _ in _PORTS:
        assert not isinstance(_NoMethods(), port)
