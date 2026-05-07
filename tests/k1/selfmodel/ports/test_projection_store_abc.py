"""ABC contract tests for ``IProjectionStorePort`` (M0.E2.I2)."""

from __future__ import annotations

import pytest

from k1.selfmodel.contracts.constitution import (
    AmendmentProposal,
    ConstitutionSnapshot,
    SigningProof,
)
from k1.selfmodel.contracts.family_model import FamilySelfModelSnapshot
from k1.selfmodel.contracts.self_model import K1SelfModelSnapshot
from k1.selfmodel.ports.projection_store import (
    IProjectionStorePort,
    ProjectionFreshness,
    ProjectionRevision,
    StoreReadResult,
    StoreWriteResult,
)


def test_abstract_instantiation_fails() -> None:
    with pytest.raises(TypeError):
        IProjectionStorePort()  # type: ignore[abstract]


def test_partial_subclass_still_abstract() -> None:
    class _Partial(IProjectionStorePort):
        def read_self(self, actor_id):  # type: ignore[override]
            return (None, StoreReadResult(found=False))

    with pytest.raises(TypeError):
        _Partial()  # type: ignore[abstract]


class _CompleteStore(IProjectionStorePort):
    def read_self(self, actor_id):  # type: ignore[override]
        return (None, StoreReadResult(found=False))

    def write_self(self, snapshot: K1SelfModelSnapshot, *, writer_id: str):  # type: ignore[override]
        return StoreWriteResult(revision=ProjectionRevision(revision="r1"))

    def read_family(self, family_space_id):  # type: ignore[override]
        return (None, StoreReadResult(found=False))

    def write_family(self, snapshot: FamilySelfModelSnapshot, *, writer_id: str):  # type: ignore[override]
        return StoreWriteResult(revision=ProjectionRevision(revision="r1"))

    def read_constitution(self, constitution_id):  # type: ignore[override]
        return (None, StoreReadResult(found=False))

    def write_constitution(self, snapshot: ConstitutionSnapshot, *, writer_id: str):  # type: ignore[override]
        return StoreWriteResult(revision=ProjectionRevision(revision="r1"))

    def upsert_amendment(self, amendment: AmendmentProposal, *, writer_id: str):  # type: ignore[override]
        return StoreWriteResult(revision=ProjectionRevision(revision="r1"))

    def append_signature(self, amendment_id: str, signature: SigningProof, *, writer_id: str):  # type: ignore[override]
        return StoreWriteResult(revision=ProjectionRevision(revision="r1"))

    def freshness(self, projection_key: str) -> ProjectionFreshness:  # type: ignore[override]
        return ProjectionFreshness.FRESH


def test_complete_subclass_instantiates() -> None:
    store = _CompleteStore()
    assert isinstance(store, IProjectionStorePort)


def test_freshness_enum_values() -> None:
    assert {e.value for e in ProjectionFreshness} == {
        "fresh",
        "stale",
        "offline_local_only",
        "conflict_pending",
    }


def test_revision_and_results_are_frozen() -> None:
    rev = ProjectionRevision(revision="r1")
    with pytest.raises(Exception):
        rev.revision = "r2"  # type: ignore[misc]

    rr = StoreReadResult(found=True)
    with pytest.raises(Exception):
        rr.found = False  # type: ignore[misc]

    wr = StoreWriteResult(revision=rev)
    with pytest.raises(Exception):
        wr.accepted = False  # type: ignore[misc]
