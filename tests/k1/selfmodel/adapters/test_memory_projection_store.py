"""Tests for ``InMemoryProjectionStore`` (M0.E3.I1)."""

from __future__ import annotations

import pytest

from k1.selfmodel.adapters.memory_projection_store import InMemoryProjectionStore
from k1.selfmodel.contracts.constitution import (
    AmendmentProposal,
    AmendmentStatus,
    ConstitutionSnapshot,
    SigningProof,
)
from k1.selfmodel.contracts.family_model import FamilySelfModelSnapshot
from k1.selfmodel.contracts.self_model import K1SelfModelSnapshot
from k1.selfmodel.ports.projection_store import (
    IProjectionStorePort,
    ProjectionFreshness,
)

# ---------------------------------------------------------------------
# Port satisfaction
# ---------------------------------------------------------------------


def test_store_satisfies_port() -> None:
    store = InMemoryProjectionStore()
    assert isinstance(store, IProjectionStorePort)


# ---------------------------------------------------------------------
# Self round-trip
# ---------------------------------------------------------------------


def test_self_round_trip_and_l4_l5_dropped() -> None:
    store = InMemoryProjectionStore()
    snap = K1SelfModelSnapshot(
        actor_id="a1",
        L1_core={"name": "Aanya"},
        L2_identity={"role": "guardian"},
        L3_pattern={"morning_routine": True},
        L4_context={"in_kitchen": True},  # transient — must be dropped
        L5_state={"mood": "focused"},  # transient — must be dropped
    )
    write = store.write_self(snap, writer_id="selfmodel:test")
    assert write.accepted
    assert write.revision.revision

    got, read = store.read_self("a1")
    assert read.found
    assert got is not None
    assert got.L1_core == {"name": "Aanya"}
    assert got.L3_pattern == {"morning_routine": True}
    # Empty-Set Invariant: L4/L5 are RAM-only.
    assert got.L4_context == {}
    assert got.L5_state == {}
    assert read.revision.revision == write.revision.revision
    assert read.freshness == ProjectionFreshness.FRESH


def test_self_missing_actor_returns_none() -> None:
    store = InMemoryProjectionStore()
    got, read = store.read_self("ghost")
    assert got is None
    assert not read.found


def test_self_second_write_chains_parent_revision() -> None:
    store = InMemoryProjectionStore()
    first = store.write_self(K1SelfModelSnapshot(actor_id="a1"), writer_id="selfmodel:test")
    second = store.write_self(K1SelfModelSnapshot(actor_id="a1"), writer_id="selfmodel:test")
    assert second.revision.parent_revision == first.revision.revision
    assert second.revision.revision != first.revision.revision


# ---------------------------------------------------------------------
# Family round-trip
# ---------------------------------------------------------------------


def test_family_round_trip() -> None:
    store = InMemoryProjectionStore()
    snap = FamilySelfModelSnapshot(family_space_id="fs1")
    write = store.write_family(snap, writer_id="selfmodel:test")
    assert write.accepted

    got, read = store.read_family("fs1")
    assert read.found
    assert got is not None
    assert got.family_space_id == "fs1"


# ---------------------------------------------------------------------
# Constitution round-trip
# ---------------------------------------------------------------------


def test_constitution_round_trip() -> None:
    store = InMemoryProjectionStore()
    snap = ConstitutionSnapshot(
        constitution_id="c1",
        version="v1",
        body={"max_tier_for_amendment": 3},
    )
    write = store.write_constitution(snap, writer_id="selfmodel:test")
    assert write.accepted

    got, read = store.read_constitution("c1")
    assert read.found
    assert got is not None
    assert got.version == "v1"


# ---------------------------------------------------------------------
# Amendments + signatures
# ---------------------------------------------------------------------


def test_amendment_upsert_and_signature_append() -> None:
    store = InMemoryProjectionStore()
    a = AmendmentProposal(
        amendment_id="am1",
        parent_version="v1",
        proposed_by="g1",
        body={"add_rule": "no_screens_after_9pm"},
        status=AmendmentStatus.DRAFT,
    )
    assert store.upsert_amendment(a, writer_id="selfmodel:test").accepted
    sig = SigningProof(signer_id="g1", key_id="did:device:hub#1", signature_b64="sig")
    assert store.append_signature("am1", sig, writer_id="selfmodel:test").accepted

    fetched = store.get_amendment("am1")
    assert fetched is not None
    assert fetched.signatures == (sig,)


def test_signature_on_unknown_amendment_rejected() -> None:
    store = InMemoryProjectionStore()
    sig = SigningProof(signer_id="g1", key_id="k", signature_b64="x")
    res = store.append_signature("nope", sig, writer_id="selfmodel:test")
    assert not res.accepted
    assert "not_found" in res.reason


# ---------------------------------------------------------------------
# Conflict-pending detection
# ---------------------------------------------------------------------


def test_sibling_amendments_mark_conflict_pending() -> None:
    store = InMemoryProjectionStore()
    store.write_constitution(
        ConstitutionSnapshot(constitution_id="c1", version="v1"),
        writer_id="selfmodel:test",
    )
    store.upsert_amendment(
        AmendmentProposal(amendment_id="am1", parent_version="v1", proposed_by="g1"),
        writer_id="selfmodel:test",
    )
    second = store.upsert_amendment(
        AmendmentProposal(amendment_id="am2", parent_version="v1", proposed_by="g2"),
        writer_id="selfmodel:test",
    )
    assert second.reason == "conflict_pending"
    assert store.freshness("constitution:c1") == ProjectionFreshness.CONFLICT_PENDING


# ---------------------------------------------------------------------
# Freshness state transitions
# ---------------------------------------------------------------------


def test_freshness_transitions() -> None:
    store = InMemoryProjectionStore()
    store.write_self(K1SelfModelSnapshot(actor_id="a1"), writer_id="selfmodel:test")
    assert store.freshness("self:a1") == ProjectionFreshness.FRESH

    store.mark_stale("self:a1")
    _, read = store.read_self("a1")
    assert read.freshness == ProjectionFreshness.STALE

    store.mark_offline_local_only("self:a1")
    _, read = store.read_self("a1")
    assert read.freshness == ProjectionFreshness.OFFLINE_LOCAL_ONLY

    # New write clears freshness override.
    store.write_self(K1SelfModelSnapshot(actor_id="a1"), writer_id="selfmodel:test")
    assert store.freshness("self:a1") == ProjectionFreshness.FRESH


# ---------------------------------------------------------------------
# Writer-id authorization
# ---------------------------------------------------------------------


def test_unauthorized_writer_rejected_when_allowlist_set() -> None:
    store = InMemoryProjectionStore(allowed_writers=("selfmodel:service",))
    res = store.write_self(K1SelfModelSnapshot(actor_id="a1"), writer_id="rogue:writer")
    assert not res.accepted
    assert "not_allowed" in res.reason

    ok = store.write_self(K1SelfModelSnapshot(actor_id="a1"), writer_id="selfmodel:service")
    assert ok.accepted


def test_open_store_accepts_any_writer() -> None:
    store = InMemoryProjectionStore()
    assert store.write_self(K1SelfModelSnapshot(actor_id="a1"), writer_id="anyone").accepted


# ---------------------------------------------------------------------
# Freshness for unknown key
# ---------------------------------------------------------------------


@pytest.mark.parametrize("key", ["self:unknown", "family:unknown", "constitution:unknown"])
def test_freshness_defaults_to_fresh_for_unknown_key(key: str) -> None:
    store = InMemoryProjectionStore()
    assert store.freshness(key) == ProjectionFreshness.FRESH


def test_missing_family_and_constitution_reads() -> None:
    store = InMemoryProjectionStore()
    fam, fr = store.read_family("ghost")
    assert fam is None and not fr.found
    con, cr = store.read_constitution("ghost")
    assert con is None and not cr.found


def test_freshness_override_propagates_to_family_and_constitution_reads() -> None:
    store = InMemoryProjectionStore()
    store.write_family(FamilySelfModelSnapshot(family_space_id="fs1"), writer_id="selfmodel:test")
    store.write_constitution(
        ConstitutionSnapshot(constitution_id="c1", version="v1"),
        writer_id="selfmodel:test",
    )
    store.mark_stale("family:fs1")
    store.mark_offline_local_only("constitution:c1")

    _, fr = store.read_family("fs1")
    assert fr.freshness == ProjectionFreshness.STALE
    _, cr = store.read_constitution("c1")
    assert cr.freshness == ProjectionFreshness.OFFLINE_LOCAL_ONLY


def test_missing_family_and_constitution_freshness_override_on_unknown_key() -> None:
    store = InMemoryProjectionStore()
    store.mark_stale("family:none")
    store.mark_offline_local_only("constitution:none")
    _, fr = store.read_family("none")
    assert fr.freshness == ProjectionFreshness.STALE
    _, cr = store.read_constitution("none")
    assert cr.freshness == ProjectionFreshness.OFFLINE_LOCAL_ONLY


def test_clear_freshness_helper() -> None:
    store = InMemoryProjectionStore()
    store.write_self(K1SelfModelSnapshot(actor_id="a1"), writer_id="selfmodel:test")
    store.mark_stale("self:a1")
    assert store.freshness("self:a1") == ProjectionFreshness.STALE
    store.clear_freshness("self:a1")
    assert store.freshness("self:a1") == ProjectionFreshness.FRESH


def test_get_amendment_missing_returns_none() -> None:
    store = InMemoryProjectionStore()
    assert store.get_amendment("nope") is None
