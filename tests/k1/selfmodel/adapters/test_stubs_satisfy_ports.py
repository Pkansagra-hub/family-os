"""Stubs satisfy their corresponding port (M0.E3.I2)."""

from __future__ import annotations

from k1.selfmodel.ports.credential import ICredentialPort
from k1.selfmodel.ports.policy import IPolicyPort
from tests.k1.selfmodel.adapters._stubs import (
    InMemoryAmendmentSync,
    NullPolicyGate,
    PassthroughCitationWrapper,
    RecordingCapsuleRenderer,
    StubCredentialVerifier,
)


def test_stub_credential_verifier_satisfies_port() -> None:
    assert isinstance(StubCredentialVerifier(), ICredentialPort)


def test_null_policy_gate_satisfies_port() -> None:
    assert isinstance(NullPolicyGate(), IPolicyPort)


def test_amendment_sync_records_calls() -> None:
    sync = InMemoryAmendmentSync()
    receipt = sync.submit_delta({"k": "v"}, band="GREEN")
    assert receipt.startswith("stub-receipt-")
    assert sync.submitted[0]["band"] == "GREEN"


def test_amendment_sync_refuses_black_band() -> None:
    import pytest

    from k1.selfmodel.contracts.privacy import BlackBandLeakError

    sync = InMemoryAmendmentSync()
    with pytest.raises(BlackBandLeakError):
        sync.submit_delta({"k": "v"}, band="BLACK")


def test_recording_capsule_renderer_captures() -> None:
    r = RecordingCapsuleRenderer()
    out = r.render(object())
    assert isinstance(out, str)
    assert len(r.rendered) == 1


def test_passthrough_citation_wrapper_returns_input() -> None:
    w = PassthroughCitationWrapper()
    payload = [{"x": 1}]
    assert w.wrap(payload) is payload
    assert w.calls == 1
