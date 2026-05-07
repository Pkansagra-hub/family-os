"""M0.E1.I2 — constitution contract dataclasses are frozen and minimal-construct."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from k1.selfmodel.contracts.constitution import (
    AmendmentProposal,
    AmendmentStatus,
    ConflictDescriptor,
    ConstitutionDiff,
    ConstitutionSnapshot,
    SigningProof,
)


def test_amendment_status_enum_members() -> None:
    expected = {
        "DRAFT",
        "PENDING",
        "APPROVED",
        "ACTIVE",
        "REJECTED",
        "EXPIRED",
        "CONFLICT_PENDING",
    }
    assert {m.name for m in AmendmentStatus} == expected


def test_signing_proof_min_construct() -> None:
    p = SigningProof(signer_id="alice", key_id="did:device:dev1#0")
    assert p.algorithm == "ed25519"
    assert p.signature_b64 == ""


def test_conflict_descriptor_min_construct() -> None:
    c = ConflictDescriptor(parent_version="v1")
    assert c.parent_version == "v1"
    assert c.sibling_amendment_ids == ()


def test_amendment_proposal_min_construct() -> None:
    a = AmendmentProposal(
        amendment_id="a-1",
        parent_version="v1",
        proposed_by="alice",
    )
    assert a.status == AmendmentStatus.DRAFT
    assert a.signatures == ()
    assert a.conflict is None


def test_constitution_diff_min_construct() -> None:
    d = ConstitutionDiff(from_version="v1", to_version="v2")
    assert d.added == ()
    assert d.removed == ()
    assert d.changed == ()


def test_constitution_snapshot_min_construct() -> None:
    s = ConstitutionSnapshot(constitution_id="c-1", version="v1")
    assert s.parent_version == ""
    assert s.body == {}
    assert s.signatures == ()


@pytest.mark.parametrize(
    "instance,field_name",
    [
        (SigningProof(signer_id="a", key_id="k"), "signer_id"),
        (ConflictDescriptor(parent_version="v1"), "parent_version"),
        (
            AmendmentProposal(amendment_id="a", parent_version="v", proposed_by="p"),
            "amendment_id",
        ),
        (ConstitutionDiff(from_version="v1", to_version="v2"), "from_version"),
        (ConstitutionSnapshot(constitution_id="c", version="v"), "constitution_id"),
    ],
)
def test_constitution_dataclasses_are_frozen(instance: object, field_name: str) -> None:
    with pytest.raises(FrozenInstanceError):
        setattr(instance, field_name, "tampered")
